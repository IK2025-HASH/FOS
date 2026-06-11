"""
fos/core/file_parser.py
Parses bank statement files: CSV, Excel (.xlsx/.xls), PDF.
Returns a normalised list of transaction dicts:
  {date, amount, description, payee}

Amount convention:
  Positive = money in (credit to bank account)
  Negative = money out (debit from bank account)
"""

import re
import logging
from pathlib import Path
from typing import Optional
import pandas as pd

log = logging.getLogger(__name__)

SUPPORTED = {".csv", ".xlsx", ".xls", ".pdf"}


def parse_file(filepath: str) -> tuple:
    """
    Parse any supported bank statement file.
    Returns (list_of_tx_dicts, detected_format, list_of_warnings).
    """
    path = Path(filepath)
    ext  = path.suffix.lower()

    if ext not in SUPPORTED:
        raise ValueError(f"Unsupported file type: {ext}. Supported: CSV, Excel, PDF.")

    if ext == ".csv":
        return _parse_csv(path)
    elif ext in (".xlsx", ".xls"):
        return _parse_excel(path)
    elif ext == ".pdf":
        return _parse_pdf(path)


# ── CSV ───────────────────────────────────────────────────────────────────────

def _parse_csv(path: Path) -> tuple:
    warnings = []
    # Try common encodings
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            df = pd.read_csv(path, encoding=enc, thousands=",")
            break
        except Exception:
            continue
    else:
        raise ValueError("Could not read CSV with any common encoding.")

    df.columns = [str(c).strip().lower() for c in df.columns]
    detected, df = _detect_and_normalise(df, warnings)
    rows = _df_to_rows(df, warnings)
    return rows, f"CSV ({detected})", warnings


# ── Excel ─────────────────────────────────────────────────────────────────────

def _parse_excel(path: Path) -> tuple:
    warnings = []
    # Try each sheet — use first non-empty
    xl = pd.ExcelFile(path)
    df = None
    for sheet in xl.sheet_names:
        candidate = xl.parse(sheet, thousands=",")
        if len(candidate) > 0:
            df = candidate
            break
    if df is None:
        raise ValueError("No data found in Excel file.")

    df.columns = [str(c).strip().lower() for c in df.columns]
    detected, df = _detect_and_normalise(df, warnings)
    rows = _df_to_rows(df, warnings)
    return rows, f"Excel ({detected})", warnings


# ── PDF ───────────────────────────────────────────────────────────────────────

def _parse_pdf(path: Path) -> tuple:
    warnings = []
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber is required for PDF parsing. Install: pip install pdfplumber")

    rows = []
    with pdfplumber.open(str(path)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                # Find header row
                header_row = None
                data_start = 0
                for i, row in enumerate(table):
                    row_str = " ".join(str(c or "").lower() for c in row)
                    if any(kw in row_str for kw in
                           ("date","description","amount","debit","credit","balance")):
                        header_row = row
                        data_start = i + 1
                        break

                if header_row is None:
                    warnings.append(f"Page {page_num+1}: could not identify table headers — skipped")
                    continue

                headers = [str(h or "").strip().lower() for h in header_row]
                for row in table[data_start:]:
                    if not row or all(c is None for c in row):
                        continue
                    row_dict = {headers[i]: str(row[i] or "").strip()
                                for i in range(min(len(headers), len(row)))}
                    tx = _parse_row_dict(row_dict, warnings)
                    if tx:
                        rows.append(tx)

    if not rows:
        warnings.append("No transactions extracted from PDF. "
                        "Try exporting as CSV from your bank instead.")

    return rows, "PDF (table extraction)", warnings


# ── Format detection and normalisation ───────────────────────────────────────

BANK_FORMATS = {
    "barclays":  {"date":"date","desc":"memo","debit":"money out","credit":"money in"},
    "hsbc":      {"date":"date","desc":"description","debit":"paid out","credit":"paid in"},
    "lloyds":    {"date":"transaction date","desc":"description","debit":"debit amount","credit":"credit amount"},
    "natwest":   {"date":"date","desc":"description","amount":"value"},
    "starling":  {"date":"date","desc":"reference","payee":"counter party","amount":"amount (gbp)"},
    "monzo":     {"date":"date","desc":"notes","payee":"name","amount":"amount"},
    "generic":   {"date":"date","desc":"description","amount":"amount"},
}


def _detect_and_normalise(df: pd.DataFrame, warnings: list) -> tuple:
    cols = set(df.columns)

    for bank, mapping in BANK_FORMATS.items():
        if all(v in cols for v in mapping.values() if v):
            log.info("Detected bank format: %s", bank)
            return bank, _normalise_df(df, mapping, bank, warnings)

    # Generic fallback — try to map by column name similarity
    warnings.append(
        "Bank format not recognised — attempting auto-map. "
        "Verify amounts after import."
    )
    return "generic (auto-mapped)", _auto_map(df, warnings)


def _normalise_df(df: pd.DataFrame, mapping: dict, bank: str, warnings: list) -> pd.DataFrame:
    out = pd.DataFrame()

    # Date — try explicit UK formats first, then fall back to dayfirst inference
    raw_dates = df[mapping["date"]].astype(str).str.strip()
    parsed = None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
                "%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
        try:
            parsed = pd.to_datetime(raw_dates, format=fmt, errors="raise")
            break
        except Exception:
            continue
    if parsed is None:
        parsed = pd.to_datetime(raw_dates, dayfirst=True, errors="coerce")
    out["date"] = parsed

    # Description
    out["description"] = df.get(mapping.get("desc",""), "").fillna("").astype(str)

    # Payee
    if "payee" in mapping and mapping["payee"] in df.columns:
        out["payee"] = df[mapping["payee"]].fillna("").astype(str)
    else:
        out["payee"] = out["description"]

    # Amount
    if "amount" in mapping and mapping["amount"] in df.columns:
        out["amount"] = _clean_amount(df[mapping["amount"]])
    elif "debit" in mapping and "credit" in mapping:
        debit  = _clean_amount(df.get(mapping["debit"], pd.Series(0, index=df.index)))
        credit = _clean_amount(df.get(mapping["credit"], pd.Series(0, index=df.index)))
        out["amount"] = credit.fillna(0) - debit.fillna(0)
    else:
        out["amount"] = 0.0
        warnings.append("Could not determine amount column — amounts set to 0.")

    out = out.dropna(subset=["date"])
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out


def _auto_map(df: pd.DataFrame, warnings: list) -> pd.DataFrame:
    """Fuzzy column mapping for unknown formats."""
    col_map = {}
    for col in df.columns:
        if re.search(r"\bdate\b", col): col_map["date"] = col
        elif re.search(r"desc|memo|narr|detail|ref", col): col_map["desc"] = col
        elif re.search(r"payee|merchant|name", col): col_map["payee"] = col
        elif re.search(r"^amount$|net amount|value$", col): col_map["amount"] = col
        elif re.search(r"debit|out|withdrawal|payment", col): col_map["debit"] = col
        elif re.search(r"credit|in|deposit", col): col_map["credit"] = col

    if "date" not in col_map:
        raise ValueError("Cannot find a date column in the file.")
    if "amount" not in col_map and not ("debit" in col_map or "credit" in col_map):
        raise ValueError("Cannot find an amount column in the file.")

    mapping = {
        "date": col_map.get("date"),
        "desc": col_map.get("desc", col_map.get("date")),
        "payee": col_map.get("payee"),
    }
    if "amount" in col_map:
        mapping["amount"] = col_map["amount"]
    else:
        mapping["debit"]  = col_map.get("debit")
        mapping["credit"] = col_map.get("credit")

    return _normalise_df(df, mapping, "auto", warnings)


def _df_to_rows(df: pd.DataFrame, warnings: list) -> list:
    rows = []
    for _, row in df.iterrows():
        try:
            amount = float(row.get("amount", 0) or 0)
            if amount == 0:
                warnings.append(f"Zero-amount row skipped: {row.get('description','')[:50]}")
                continue
            rows.append({
                "date":        str(row.get("date",""))[:10],
                "amount":      round(amount, 2),
                "description": str(row.get("description","")).strip()[:200],
                "payee":       str(row.get("payee","")).strip()[:100],
            })
        except Exception as exc:
            warnings.append(f"Row error: {exc}")
    return rows


def _parse_row_dict(row: dict, warnings: list) -> Optional[dict]:
    """Convert a raw dict (from PDF table) to a normalised tx dict."""
    date_val = (row.get("date") or row.get("transaction date") or "").strip()
    desc     = (row.get("description") or row.get("details") or row.get("narrative") or "").strip()
    payee    = (row.get("payee") or row.get("merchant") or desc).strip()

    # Amount: try single amount, or debit/credit
    amount = 0.0
    raw_amount = row.get("amount") or row.get("value") or ""
    if raw_amount:
        amount = _parse_amount_str(raw_amount)
    else:
        debit  = _parse_amount_str(row.get("debit","") or row.get("money out","") or "0")
        credit = _parse_amount_str(row.get("credit","") or row.get("money in","") or "0")
        amount = credit - debit

    if not date_val or amount == 0:
        return None

    try:
        d = pd.to_datetime(date_val, dayfirst=True)
        date_str = d.strftime("%Y-%m-%d")
    except Exception:
        return None

    return {"date": date_str, "amount": round(amount, 2),
            "description": desc[:200], "payee": payee[:100]}


def _clean_amount(series: pd.Series) -> pd.Series:
    return series.astype(str).str.replace(r"[£,\s]","",regex=True)\
                 .str.replace(r"\((.+)\)",r"-\1",regex=True)\
                 .pipe(pd.to_numeric, errors="coerce")


def _parse_amount_str(s: str) -> float:
    s = re.sub(r"[£,\s]", "", str(s))
    s = re.sub(r"\((.+)\)", r"-\1", s)
    try:
        return float(s)
    except Exception:
        return 0.0
