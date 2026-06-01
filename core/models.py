"""
fos/core/models.py
Business logic layer — entities, CoA seeding, transactions, GL posting.
All database interactions go through this layer, never directly from the UI.
"""

import uuid
import hashlib
import json
import logging
from datetime import datetime, date
from typing import Optional

from core.database import db

log = logging.getLogger(__name__)


def _uid() -> str:
    return str(uuid.uuid4())

def _now() -> str:
    return datetime.utcnow().isoformat()

def _period(date_str: str) -> str:
    """Convert any date string to YYYY-MM period."""
    try:
        d = date.fromisoformat(str(date_str)[:10])
        return d.strftime("%Y-%m")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m")


# ══════════════════════════════════════════════════════════════════════════════
# COMPANY PROFILE
# ══════════════════════════════════════════════════════════════════════════════

class EntityModel:

    @staticmethod
    def create(
        legal_name: str,
        trading_name: str,
        company_number: str,
        entity_type: str,
        fy_start: str,
        fy_end: str,
        reg_address: dict,
        trading_address: Optional[dict],
        vat_registered: bool,
        vat_number: str,
        vat_scheme: str,
        flat_rate_pct: Optional[float],
        quarter_start_month: int,
        banks: list,
        approver_name: str,
        approver_role: str,
        approver_email: str,
    ) -> str:
        entity_id = _uid()
        now = _now()

        db.execute(
            """INSERT INTO entities
               (entity_id,legal_name,trading_name,company_number,entity_type,
                fy_start,fy_end,status,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,'Active',?,?)""",
            (entity_id, legal_name, trading_name, company_number, entity_type,
             fy_start, fy_end, now, now)
        )

        # Registered address
        db.execute(
            """INSERT INTO entity_addresses
               (address_id,entity_id,address_type,line1,line2,town,county,postcode)
               VALUES (?,?,?,?,?,?,?,?)""",
            (_uid(), entity_id, "registered",
             reg_address.get("line1",""), reg_address.get("line2",""),
             reg_address.get("town",""), reg_address.get("county",""),
             reg_address.get("postcode",""))
        )

        # Trading address if different
        if trading_address:
            db.execute(
                """INSERT INTO entity_addresses
                   (address_id,entity_id,address_type,line1,line2,town,county,postcode)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (_uid(), entity_id, "trading",
                 trading_address.get("line1",""), trading_address.get("line2",""),
                 trading_address.get("town",""), trading_address.get("county",""),
                 trading_address.get("postcode",""))
            )

        # VAT config
        db.execute(
            """INSERT INTO entity_vat
               (vat_id,entity_id,vat_registered,vat_number,scheme,
                flat_rate_pct,quarter_start_month)
               VALUES (?,?,?,?,?,?,?)""",
            (_uid(), entity_id, int(vat_registered), vat_number, vat_scheme,
             flat_rate_pct, quarter_start_month)
        )

        # Bank accounts
        for i, bank in enumerate(banks):
            db.execute(
                """INSERT INTO entity_banks
                   (bank_id,entity_id,account_name,sort_code,account_number,is_primary)
                   VALUES (?,?,?,?,?,?)""",
                (_uid(), entity_id,
                 bank.get("account_name",""), bank.get("sort_code",""),
                 bank.get("account_number",""), int(i == 0))
            )

        # Approval authority
        db.execute(
            """INSERT INTO approval_auth
               (auth_id,entity_id,name,role,email)
               VALUES (?,?,?,?,?)""",
            (_uid(), entity_id, approver_name, approver_role, approver_email)
        )

        db.commit()

        # Seed the standard Chart of Accounts
        CoAModel.seed_standard(entity_id)

        log.info("Entity created: %s (%s)", legal_name, entity_id)
        return entity_id

    @staticmethod
    def list_all() -> list:
        return db.fetchall(
            "SELECT entity_id, legal_name, trading_name, entity_type, "
            "fy_start, fy_end, status FROM entities ORDER BY legal_name"
        )

    @staticmethod
    def get(entity_id: str) -> Optional[dict]:
        e = db.fetchone(
            "SELECT * FROM entities WHERE entity_id=?", (entity_id,)
        )
        if not e:
            return None
        e["vat"] = db.fetchone(
            "SELECT * FROM entity_vat WHERE entity_id=?", (entity_id,)
        )
        e["addresses"] = db.fetchall(
            "SELECT * FROM entity_addresses WHERE entity_id=?", (entity_id,)
        )
        e["banks"] = db.fetchall(
            "SELECT * FROM entity_banks WHERE entity_id=?", (entity_id,)
        )
        e["approver"] = db.fetchone(
            "SELECT * FROM approval_auth WHERE entity_id=?", (entity_id,)
        )
        return e


# ══════════════════════════════════════════════════════════════════════════════
# CHART OF ACCOUNTS
# ══════════════════════════════════════════════════════════════════════════════

STANDARD_COA = [
    # code, name, type, normal_balance, vat_applicable, vat_rate, system_locked
    ("1000","Bank — Current Account",    "Asset",    "Debit",  "No",      None,  1),
    ("1010","Bank — Savings / Reserve",  "Asset",    "Debit",  "No",      None,  0),
    ("1020","Petty Cash",                "Asset",    "Debit",  "No",      None,  0),
    ("1100","Trade Debtors",             "Asset",    "Debit",  "No",      None,  1),
    ("1110","Prepayments",               "Asset",    "Debit",  "No",      None,  0),
    ("1200","VAT Reclaim Receivable",    "Asset",    "Debit",  "No",      None,  1),
    ("1300","Fixed Assets — Equipment",  "Asset",    "Debit",  "No",      None,  0),
    ("1310","Fixed Assets — Vehicles",   "Asset",    "Debit",  "No",      None,  0),
    ("1390","Accumulated Depreciation",  "Asset",    "Credit", "No",      None,  0),
    ("2000","Trade Creditors",           "Liability","Credit", "No",      None,  1),
    ("2100","VAT Liability",             "Liability","Credit", "No",      None,  1),
    ("2110","VAT Control Account",       "Liability","Credit", "No",      None,  1),
    ("2200","PAYE / NIC Payable",        "Liability","Credit", "No",      None,  0),
    ("2300","Corporation Tax Provision", "Liability","Credit", "No",      None,  0),
    ("2400","Director Loan Account",     "Liability","Credit", "No",      None,  0),
    ("2500","Bank Loan",                 "Liability","Credit", "No",      None,  0),
    ("2600","Accruals",                  "Liability","Credit", "No",      None,  0),
    ("3000","Share Capital",             "Equity",   "Credit", "No",      None,  1),
    ("3100","Retained Earnings",         "Equity",   "Credit", "No",      None,  1),
    ("3200","Owner Drawings",            "Equity",   "Debit",  "No",      None,  0),
    ("3300","Current Year Profit/Loss",  "Equity",   "Credit", "No",      None,  1),
    ("4000","Sales — Standard Rated",    "Income",   "Credit", "Yes",     20.0,  1),
    ("4010","Sales — Zero Rated",        "Income",   "Credit", "Yes",      0.0,  0),
    ("4020","Sales — Exempt",            "Income",   "Credit", "Exempt",  None,  0),
    ("4030","Sales — Outside Scope",     "Income",   "Credit", "No",      None,  0),
    ("4100","Grant Income",              "Income",   "Credit", "No",      None,  0),
    ("4200","Other Income",              "Income",   "Credit", "No",      None,  0),
    ("4300","Interest Received",         "Income",   "Credit", "No",      None,  0),
    ("5000","Direct Materials",          "CoS",      "Debit",  "Yes",     20.0,  0),
    ("5010","Subcontractors",            "CoS",      "Debit",  "Yes",     20.0,  0),
    ("5020","Direct Wages",              "CoS",      "Debit",  "No",      None,  0),
    ("5030","Carriage / Delivery",       "CoS",      "Debit",  "Yes",     20.0,  0),
    ("5500","Rent and Rates",            "Overhead", "Debit",  "Yes",     20.0,  0),
    ("5510","Utilities",                 "Overhead", "Debit",  "Yes",     20.0,  0),
    ("5520","Telephone and Internet",    "Overhead", "Debit",  "Yes",     20.0,  0),
    ("5530","Insurance",                 "Overhead", "Debit",  "Exempt",  None,  0),
    ("5540","Subscriptions and Software","Overhead", "Debit",  "Yes",     20.0,  0),
    ("5550","Marketing and Advertising", "Overhead", "Debit",  "Yes",     20.0,  0),
    ("5560","Travel and Accommodation",  "Overhead", "Debit",  "Yes",     20.0,  0),
    ("5570","Meals and Entertainment",   "Overhead", "Debit",  "Yes",     20.0,  0),
    ("5580","Motor Expenses",            "Overhead", "Debit",  "Yes",     20.0,  0),
    ("5590","Professional Fees",         "Overhead", "Debit",  "Yes",     20.0,  0),
    ("5600","Bank Charges and Interest", "Overhead", "Debit",  "Exempt",  None,  0),
    ("5610","Depreciation",              "Overhead", "Debit",  "No",      None,  0),
    ("5620","Sundry Expenses",           "Overhead", "Debit",  "Yes",     20.0,  0),
    ("5630","Bad Debt Write-Off",        "Overhead", "Debit",  "No",      None,  0),
    ("5700","Salaries and Wages",        "Overhead", "Debit",  "No",      None,  0),
    ("5710","Employer NIC",              "Overhead", "Debit",  "No",      None,  0),
    ("5720","Pension Contributions",     "Overhead", "Debit",  "No",      None,  0),
    ("5730","Directors Remuneration",    "Overhead", "Debit",  "No",      None,  0),
    ("6000","Corporation Tax Charge",    "Tax",      "Debit",  "No",      None,  0),
    ("9000","Internal Bank Transfer",    "Asset",    "Debit",  "No",      None,  1),
    ("6010","Deferred Tax",              "Tax",      "Debit",  "No",      None,  0),
]


class CoAModel:

    @staticmethod
    def seed_standard(entity_id: str) -> None:
        for row in STANDARD_COA:
            db.execute(
                """INSERT OR IGNORE INTO coa
                   (account_id,entity_id,code,name,type,normal_balance,
                    vat_applicable,vat_rate,system_locked,active)
                   VALUES (?,?,?,?,?,?,?,?,?,1)""",
                (_uid(), entity_id, *row)
            )
        db.commit()
        log.info("Standard CoA seeded for entity %s (%d accounts)", entity_id, len(STANDARD_COA))

    @staticmethod
    def get_for_entity(entity_id: str, active_only: bool = True) -> list:
        q = "SELECT * FROM coa WHERE entity_id=?"
        if active_only:
            q += " AND active=1"
        q += " ORDER BY code"
        return db.fetchall(q, (entity_id,))

    @staticmethod
    def add_account(entity_id: str, code: str, name: str, acct_type: str,
                    normal_balance: str, vat_applicable: str, vat_rate: Optional[float]) -> str:
        account_id = _uid()
        db.execute(
            """INSERT INTO coa
               (account_id,entity_id,code,name,type,normal_balance,
                vat_applicable,vat_rate,system_locked,active)
               VALUES (?,?,?,?,?,?,?,?,0,1)""",
            (account_id, entity_id, code, name, acct_type,
             normal_balance, vat_applicable, vat_rate)
        )
        db.commit()
        return account_id

    @staticmethod
    def import_from_rows(entity_id: str, rows: list) -> tuple:
        """
        Import CoA from a list of dicts. Required keys: code, name, type.
        Returns (imported_count, skipped_count, errors).
        """
        imported, skipped, errors = 0, 0, []
        for row in rows:
            try:
                code = str(row.get("code","")).strip()
                name = str(row.get("name","")).strip()
                acct_type = str(row.get("type","Overhead")).strip()
                if not code or not name:
                    skipped += 1
                    continue
                existing = db.fetchone(
                    "SELECT account_id FROM coa WHERE entity_id=? AND code=?",
                    (entity_id, code)
                )
                if existing:
                    skipped += 1
                    continue
                db.execute(
                    """INSERT INTO coa
                       (account_id,entity_id,code,name,type,normal_balance,
                        vat_applicable,vat_rate,system_locked,active)
                       VALUES (?,?,?,?,?,?,?,?,0,1)""",
                    (_uid(), entity_id, code, name, acct_type,
                     row.get("normal_balance","Debit"),
                     row.get("vat_applicable","No"),
                     row.get("vat_rate"), )
                )
                imported += 1
            except Exception as exc:
                errors.append(str(exc))
        db.commit()
        return imported, skipped, errors


# ══════════════════════════════════════════════════════════════════════════════
# IMPORT PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

class ImportModel:

    @staticmethod
    def create_batch(entity_id: str, filename: str, file_type: str, row_count: int) -> str:
        batch_id = _uid()
        db.execute(
            """INSERT INTO import_batches
               (batch_id,entity_id,filename,file_type,import_time,row_count,status)
               VALUES (?,?,?,?,?,?,'imported')""",
            (batch_id, entity_id, filename, file_type, _now(), row_count)
        )
        db.commit()
        return batch_id

    @staticmethod
    def stage_transactions(entity_id: str, batch_id: str, rows: list) -> int:
        """
        rows: list of dicts with keys: date, amount, description, payee
        Returns count of rows staged.
        """
        count = 0
        for row in rows:
            try:
                db.execute(
                    """INSERT INTO transactions
                       (tx_id,entity_id,batch_id,date,amount,
                        description,payee,source,status,created_at)
                       VALUES (?,?,?,?,?,?,?,'CSV_IMPORT','staged',?)""",
                    (_uid(), entity_id, batch_id,
                     str(row.get("date",""))[:10],
                     float(row.get("amount", 0)),
                     str(row.get("description","")),
                     str(row.get("payee","")),
                     _now())
                )
                count += 1
            except Exception as exc:
                log.warning("Skipped row during staging: %s — %s", row, exc)
        db.commit()
        return count

    @staticmethod
    def get_staged(entity_id: str) -> list:
        return db.fetchall(
            """SELECT t.*, a.account_code, a.vat_code, a.confidence, a.method, a.override
               FROM transactions t
               LEFT JOIN ai_allocations a ON a.tx_id = t.tx_id
               WHERE t.entity_id=? AND t.status='staged'
               ORDER BY t.date, t.tx_id""",
            (entity_id,)
        )

    @staticmethod
    def approve_and_post(entity_id: str, tx_decisions: list, approver_name: str,
                         approver_role: str, period: str) -> str:
        """
        tx_decisions: list of dicts:
          {tx_id, account_code, vat_code, override, override_reason}
        Posts to GL and creates approval record.
        Returns approval_id.
        """
        approval_id = _uid()
        now = _now()

        gl_rows = []
        for d in tx_decisions:
            tx = db.fetchone("SELECT * FROM transactions WHERE tx_id=?", (d["tx_id"],))
            if not tx:
                continue
            amount = float(tx["amount"])
            vat_rate = _vat_rate_for_code(d["vat_code"])
            vat_amount = round(abs(amount) * vat_rate / (1 + vat_rate), 2) if vat_rate > 0 else 0.0
            abs_amt = abs(amount)
            period  = _period(tx["date"])

            # Money out (negative amount): debit expense, credit bank
            # Money in  (positive amount): debit bank, credit income
            if amount < 0:
                exp_debit, exp_credit  = abs_amt, 0.0
                bank_debit, bank_credit = 0.0, abs_amt
            else:
                exp_debit, exp_credit  = 0.0, abs_amt
                bank_debit, bank_credit = abs_amt, 0.0

            # Expense / income line
            gl_rows.append((_uid(), entity_id, d["account_code"], tx["date"],
                             tx["description"],
                             exp_debit, exp_credit,
                             d["vat_code"], vat_amount,
                             tx["source"], tx["batch_id"], approval_id, period, 0))

            # Bank counterpart line (always OS / no VAT on bank movement)
            gl_rows.append((_uid(), entity_id, "1000", tx["date"],
                             tx["description"],
                             bank_debit, bank_credit,
                             "OS", 0.0,
                             tx["source"], tx["batch_id"], approval_id, period, 0))

            # Update allocation override if user changed it
            if d.get("override"):
                db.execute(
                    """UPDATE ai_allocations SET override=1, override_reason=?
                       WHERE tx_id=?""",
                    (d.get("override_reason",""), d["tx_id"])
                )
            db.execute(
                "UPDATE transactions SET status='approved' WHERE tx_id=?",
                (d["tx_id"],)
            )

        db.executemany(
            """INSERT INTO gl
               (gl_id,entity_id,account_code,date,description,debit,credit,
                vat_code,vat_amount,source,batch_id,approval_id,period,locked)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            gl_rows
        )

        # Checkpoint 1 approval record
        doc_hash = hashlib.sha256(
            json.dumps([r[2:] for r in gl_rows], sort_keys=True).encode()
        ).hexdigest()

        db.execute(
            """INSERT INTO approvals
               (approval_id,entity_id,checkpoint,period,approver_name,
                approver_role,timestamp,action,document_hash)
               VALUES (?,?,1,?,?,?,?,'APPROVED',?)""",
            (approval_id, entity_id, period, approver_name, approver_role, now, doc_hash)
        )
        db.commit()
        log.info("Posted %d GL entries for entity %s, approval %s",
                 len(gl_rows), entity_id, approval_id)
        return approval_id


def _vat_rate_for_code(vat_code: str) -> float:
    mapping = {"SR-I": 0.20, "SR-O": 0.20, "RR": 0.05, "ZR": 0.0,
               "EX": 0.0, "OS": 0.0, "FRO": 0.0}
    return mapping.get(vat_code, 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# GL QUERIES
# ══════════════════════════════════════════════════════════════════════════════

class GLModel:

    @staticmethod
    def get_entries(entity_id: str, period: Optional[str] = None) -> list:
        if period:
            return db.fetchall(
                "SELECT * FROM gl WHERE entity_id=? AND period=? ORDER BY date, gl_id",
                (entity_id, period)
            )
        return db.fetchall(
            "SELECT * FROM gl WHERE entity_id=? ORDER BY date, gl_id",
            (entity_id,)
        )

    @staticmethod
    def get_trial_balance(entity_id: str, period: Optional[str] = None) -> list:
        where = "WHERE g.entity_id=?"
        params = [entity_id]
        if period:
            where += " AND g.period=?"
            params.append(period)
        return db.fetchall(
            f"""SELECT c.code, c.name, c.type, c.normal_balance,
                       COALESCE(SUM(g.debit),0)  AS total_debit,
                       COALESCE(SUM(g.credit),0) AS total_credit,
                       COALESCE(SUM(g.debit),0) - COALESCE(SUM(g.credit),0) AS balance
                FROM coa c
                LEFT JOIN gl g ON g.entity_id=c.entity_id AND g.account_code=c.code
                {where}
                GROUP BY c.code, c.name, c.type, c.normal_balance
                HAVING total_debit != 0 OR total_credit != 0
                ORDER BY c.code""",
            params
        )


class DataUtils:
    @staticmethod
    def clear_transactions(entity_id: str) -> int:
        """Delete all staged/posted transaction data for an entity, keeping companies and CoA intact."""
        n = db.fetchone("SELECT COUNT(*) as n FROM transactions WHERE entity_id=?", (entity_id,))["n"]
        db.execute("DELETE FROM gl WHERE entity_id=?", (entity_id,))
        db.execute("DELETE FROM approvals WHERE entity_id=?", (entity_id,))
        db.execute(
            "DELETE FROM ai_allocations WHERE tx_id IN "
            "(SELECT tx_id FROM transactions WHERE entity_id=?)", (entity_id,)
        )
        db.execute("DELETE FROM transactions WHERE entity_id=?", (entity_id,))
        db.execute("DELETE FROM import_batches WHERE entity_id=?", (entity_id,))
        db.commit()
        return n
