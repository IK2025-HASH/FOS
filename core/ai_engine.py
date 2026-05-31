"""
fos/core/ai_engine.py
AI Transaction Allocation Engine.
Priority: Rule library → ML classifier → Heuristics → Unclassified.
Fully local — no external API calls.
"""

import re
import logging
import pickle
from typing import Optional
from datetime import datetime

from core.database import db

log = logging.getLogger(__name__)

# ── VAT code heuristics ──────────────────────────────────────────────────────
VAT_CODE_MAP = {
    "Asset":    "OS",
    "Liability":"OS",
    "Equity":   "OS",
    "Income":   "SR-O",
    "CoS":      "SR-I",
    "Overhead": "SR-I",
    "Tax":      "OS",
}

EXEMPT_KEYWORDS = ["insurance","stamp duty","rates","council tax","interest","bank charge",
                   "mortgage","loan repayment","dividend","salary","wages","payroll","hmrc",
                   "paye","national insurance","pension"]

ZERO_RATED_KEYWORDS = ["postage","royal mail","food","children","books","newspaper"]

OS_KEYWORDS = ["transfer","savings","investment","loan","salary","wages","payroll",
               "dividends","drawings","hmrc","tax payment","corporation tax","vat payment"]

# ── Common UK payee → account code rules ─────────────────────────────────────
BUILTIN_RULES = [
    # (payee_pattern_regex, keyword_regex, account_code, vat_code)
    (r"amazon web services|aws\b",          None,               "5540", "SR-I"),
    (r"microsoft|office 365|m365",          None,               "5540", "SR-I"),
    (r"google workspace|gsuite",            None,               "5540", "SR-I"),
    (r"zoom|teams|slack|notion",            None,               "5540", "SR-I"),
    (r"xero|quickbooks|sage",              None,               "5540", "SR-I"),
    (r"bt |virgin media|sky broadband|vodafone|o2|ee\b|three\b", None, "5520", "SR-I"),
    (r"british gas|eon\b|edf|npower|bulb",  None,               "5510", "SR-I"),
    (r"royal mail|parcelforce|hermes|dpd|ups\b|fedex", None,    "5030", "SR-I"),
    (r"barclays|lloyds|natwest|hsbc|monzo|starling|santander",
                                            r"charge|fee",      "5600", "EX"),
    (r"council|rates",                      None,               "5500", "EX"),
    (r"hmrc|hm revenue",                    r"vat|paye|tax",    "2200", "OS"),
    (r"insurance",                          None,               "5530", "EX"),
    (r"companies house",                    None,               "5590", "EX"),
    (r"linkedin|facebook ads|google ads|meta ads", None,        "5550", "SR-I"),
    (r"uber|lyft|trainline|national rail|avanti|gwr", None,     "5560", "SR-I"),
    (r"tesco|sainsbury|asda|waitrose|costa|starbucks|pret", None,"5570", "SR-I"),
]


class AllocationEngine:

    def __init__(self, entity_id: str):
        self.entity_id = entity_id
        self._coa: dict = {}        # code → type
        self._rules: list = []      # from rule_library table
        self._ml_model = None       # lazy-loaded
        self._refresh()

    # ── Public interface ──────────────────────────────────────────────────────

    def allocate_batch(self, transactions: list) -> list:
        """
        transactions: list of dicts with tx_id, description, payee, amount
        Returns list of allocation dicts ready to insert into ai_allocations.
        Also writes directly to ai_allocations table.
        """
        self._refresh()
        results = []
        for tx in transactions:
            alloc = self._allocate_one(tx)
            self._write_allocation(alloc)
            results.append(alloc)
        db.commit()
        return results

    def _allocate_one(self, tx: dict) -> dict:
        from core.database import _uid as uid
        tx_id      = tx["tx_id"]
        desc       = str(tx.get("description","")).lower().strip()
        payee      = str(tx.get("payee","")).lower().strip()
        amount     = float(tx.get("amount", 0))
        combined   = f"{payee} {desc}".strip()

        # 1. Rule library (user-created rules — highest priority)
        rule_match = self._match_rules(payee, desc)
        if rule_match:
            return self._result(tx_id, rule_match["account_code"],
                                rule_match["vat_code"], 98.0, "rule",
                                rule_match["rule_id"])

        # 2. Built-in payee rules
        builtin = self._match_builtin(payee, desc)
        if builtin:
            return self._result(tx_id, builtin[0], builtin[1], 92.0, "builtin_rule")

        # 3. ML classifier
        if self._ml_model:
            code, confidence = self._ml_predict(combined)
            if confidence >= 0.70:
                vat_code = self._infer_vat(code, combined)
                return self._result(tx_id, code, vat_code,
                                    round(confidence * 100, 1), "ml")

        # 4. Heuristics
        h = self._heuristic(combined, amount)
        if h:
            return self._result(tx_id, h[0], h[1], h[2], "heuristic")

        # 5. Unclassified
        return self._result(tx_id, "5620", "SR-I", 15.0, "heuristic")

    # ── Rule matching ─────────────────────────────────────────────────────────

    def _match_rules(self, payee: str, desc: str) -> Optional[dict]:
        """Check rule_library table — entity-specific then global."""
        for rule in self._rules:
            pp = rule.get("payee_pattern","") or ""
            kp = rule.get("keyword_pattern","") or ""
            payee_ok = bool(re.search(pp, payee, re.I)) if pp else True
            kw_ok    = bool(re.search(kp, desc, re.I)) if kp else True
            if pp and not payee_ok:
                continue
            if kp and not kw_ok:
                continue
            if payee_ok and kw_ok and (pp or kp):
                return rule
        return None

    def _match_builtin(self, payee: str, desc: str) -> Optional[tuple]:
        combined = f"{payee} {desc}"
        for pp, kp, code, vat in BUILTIN_RULES:
            if pp and not re.search(pp, combined, re.I):
                continue
            if kp and not re.search(kp, combined, re.I):
                continue
            return (code, vat)
        return None

    # ── Heuristics ────────────────────────────────────────────────────────────

    def _heuristic(self, text: str, amount: float) -> Optional[tuple]:
        # Outside scope signals
        for kw in OS_KEYWORDS:
            if kw in text:
                return ("2200" if "paye" in text or "payroll" in text else "5600",
                        "OS", 55.0)
        # Exempt signals
        for kw in EXEMPT_KEYWORDS:
            if kw in text:
                return ("5530" if "insurance" in text else "5600", "EX", 52.0)
        # Zero rated
        for kw in ZERO_RATED_KEYWORDS:
            if kw in text:
                return ("5000", "ZR", 50.0)
        # Credits → income
        if amount > 0:
            return ("4000", "SR-O", 40.0)
        # Debits → overhead catch-all
        return ("5620", "SR-I", 30.0)

    def _infer_vat(self, account_code: str, text: str) -> str:
        acct_type = self._coa.get(account_code, "Overhead")
        for kw in OS_KEYWORDS:
            if kw in text: return "OS"
        for kw in EXEMPT_KEYWORDS:
            if kw in text: return "EX"
        for kw in ZERO_RATED_KEYWORDS:
            if kw in text: return "ZR"
        return VAT_CODE_MAP.get(acct_type, "SR-I")

    # ── ML ────────────────────────────────────────────────────────────────────

    def train(self) -> bool:
        """
        Train (or retrain) the ML classifier from approved GL history.
        Returns True if trained successfully.
        """
        rows = db.fetchall(
            """SELECT g.description, g.account_code
               FROM gl g WHERE g.entity_id=? AND g.description IS NOT NULL
               AND g.description != ''""",
            (self.entity_id,)
        )
        if len(rows) < 20:
            log.info("Not enough GL history to train ML (%d rows)", len(rows))
            return False

        from sklearn.pipeline import Pipeline
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression

        X = [r["description"].lower() for r in rows]
        y = [r["account_code"] for r in rows]

        # Need at least 2 classes
        if len(set(y)) < 2:
            return False

        model = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1,2), max_features=2000,
                                      sublinear_tf=True)),
            ("clf",   LogisticRegression(max_iter=500, C=5.0))
        ])
        model.fit(X, y)
        self._ml_model = model
        log.info("ML model trained on %d samples, %d classes", len(X), len(set(y)))
        return True

    def _ml_predict(self, text: str) -> tuple:
        proba = self._ml_model.predict_proba([text])[0]
        best_idx = proba.argmax()
        return self._ml_model.classes_[best_idx], float(proba[best_idx])

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _result(self, tx_id, account_code, vat_code, confidence,
                method, rule_id=None) -> dict:
        import uuid
        return {
            "alloc_id":     str(uuid.uuid4()),
            "tx_id":        tx_id,
            "account_code": account_code,
            "vat_code":     vat_code,
            "confidence":   confidence,
            "method":       method,
            "rule_id":      rule_id,
            "override":     0,
        }

    def _write_allocation(self, alloc: dict) -> None:
        db.execute("DELETE FROM ai_allocations WHERE tx_id=?", (alloc["tx_id"],))
        db.execute(
            """INSERT INTO ai_allocations
               (alloc_id,tx_id,account_code,vat_code,confidence,method,rule_id,override)
               VALUES (?,?,?,?,?,?,?,?)""",
            (alloc["alloc_id"], alloc["tx_id"], alloc["account_code"],
             alloc["vat_code"], alloc["confidence"], alloc["method"],
             alloc["rule_id"], alloc["override"])
        )

    def _refresh(self) -> None:
        """Reload CoA and rule library from DB."""
        rows = db.fetchall(
            "SELECT code, type FROM coa WHERE entity_id=? AND active=1",
            (self.entity_id,)
        )
        self._coa = {r["code"]: r["type"] for r in rows}

        self._rules = db.fetchall(
            """SELECT * FROM rule_library
               WHERE entity_id=? OR scope='global'
               ORDER BY scope DESC""",
            (self.entity_id,)
        )

    # ── Rule saving ───────────────────────────────────────────────────────────

    def save_rule(self, payee_pattern: str, keyword_pattern: str,
                  account_code: str, vat_code: str,
                  tx_id: Optional[str] = None,
                  scope: str = "entity") -> str:
        import uuid
        rule_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        db.execute(
            """INSERT INTO rule_library
               (rule_id,entity_id,scope,payee_pattern,keyword_pattern,
                account_code,vat_code,created_from_tx_id,created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (rule_id,
             self.entity_id if scope == "entity" else None,
             scope, payee_pattern, keyword_pattern,
             account_code, vat_code, tx_id, now)
        )
        db.commit()
        self._refresh()
        return rule_id


# ── Confidence band helper ───────────────────────────────────────────────────

def confidence_band(score: float) -> tuple:
    """Returns (band_name, colour_hex, requires_individual_review)."""
    if score >= 90:
        return ("High",   "#27AE60", False)
    elif score >= 70:
        return ("Medium", "#E67E22", True)
    elif score >= 50:
        return ("Low",    "#E74C3C", True)
    else:
        return ("Unclassified", "#8E44AD", True)
