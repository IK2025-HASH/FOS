"""
fos/core/database.py
Encrypted SQLite database layer using pysqlcipher3.
Falls back to standard sqlite3 if sqlcipher3 is unavailable (dev mode).
"""

import sqlite3
import os
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Try sqlcipher3, fall back to sqlite3 for development
try:
    from sqlcipher3 import dbapi2 as sqlcipher
    ENCRYPTED = True
except ImportError:
    log.warning("sqlcipher3 not available — using unencrypted sqlite3 (dev mode only)")
    import sqlite3 as sqlcipher
    ENCRYPTED = False

DB_PATH = Path(os.environ.get("APPDATA", Path.home() / ".local" / "share")) / "FOS" / "fos.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


class Database:
    """Single connection wrapper. Call open(password) before any operation."""

    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    # ── Connection ───────────────────────────────────────────────────────────

    def open(self, password: str) -> None:
        global _db_password
        _db_password = password
        self._conn = sqlcipher.connect(str(self.path), check_same_thread=False)
        if ENCRYPTED:
            # Set encryption key — must be first pragma on a new/existing db
            self._conn.execute(f"PRAGMA key='{password}'")
            self._conn.execute("PRAGMA cipher_page_size=4096")
            self._conn.execute("PRAGMA kdf_iter=200000")
            self._conn.execute("PRAGMA cipher_hmac_algorithm=HMAC_SHA256")
        self._conn.row_factory = sqlcipher.Row if ENCRYPTED else sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._initialise_schema()
        log.info("Database opened: %s (encrypted=%s)", self.path, ENCRYPTED)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def is_open(self) -> bool:
        return self._conn is not None

    # ── Query helpers ────────────────────────────────────────────────────────

    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, params_list) -> None:
        self._conn.executemany(sql, params_list)

    def fetchall(self, sql: str, params=()) -> list:
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def fetchone(self, sql: str, params=()) -> Optional[dict]:
        row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    # ── Schema ───────────────────────────────────────────────────────────────

    def _initialise_schema(self) -> None:
        stmts = [

            # ── entities ────────────────────────────────────────────────────
            """CREATE TABLE IF NOT EXISTS entities (
                entity_id       TEXT PRIMARY KEY,
                legal_name      TEXT NOT NULL,
                trading_name    TEXT,
                company_number  TEXT,
                entity_type     TEXT NOT NULL DEFAULT 'Limited Company',
                fy_start        TEXT NOT NULL,
                fy_end          TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'Active',
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )""",

            # ── entity_addresses ────────────────────────────────────────────
            """CREATE TABLE IF NOT EXISTS entity_addresses (
                address_id      TEXT PRIMARY KEY,
                entity_id       TEXT NOT NULL REFERENCES entities(entity_id),
                address_type    TEXT NOT NULL,
                line1           TEXT NOT NULL,
                line2           TEXT,
                town            TEXT NOT NULL,
                county          TEXT,
                postcode        TEXT NOT NULL
            )""",

            # ── entity_vat ──────────────────────────────────────────────────
            """CREATE TABLE IF NOT EXISTS entity_vat (
                vat_id              TEXT PRIMARY KEY,
                entity_id           TEXT NOT NULL REFERENCES entities(entity_id),
                vat_registered      INTEGER NOT NULL DEFAULT 0,
                vat_number          TEXT,
                scheme              TEXT DEFAULT 'Standard Accrual',
                flat_rate_pct       REAL,
                quarter_start_month INTEGER DEFAULT 1
            )""",

            # ── entity_banks ────────────────────────────────────────────────
            """CREATE TABLE IF NOT EXISTS entity_banks (
                bank_id         TEXT PRIMARY KEY,
                entity_id       TEXT NOT NULL REFERENCES entities(entity_id),
                account_name    TEXT NOT NULL,
                sort_code       TEXT,
                account_number  TEXT,
                is_primary      INTEGER NOT NULL DEFAULT 0
            )""",

            # ── approval_auth ────────────────────────────────────────────────
            """CREATE TABLE IF NOT EXISTS approval_auth (
                auth_id         TEXT PRIMARY KEY,
                entity_id       TEXT NOT NULL REFERENCES entities(entity_id),
                name            TEXT NOT NULL,
                role            TEXT NOT NULL,
                email           TEXT
            )""",

            # ── coa ─────────────────────────────────────────────────────────
            """CREATE TABLE IF NOT EXISTS coa (
                account_id      TEXT PRIMARY KEY,
                entity_id       TEXT NOT NULL REFERENCES entities(entity_id),
                code            TEXT NOT NULL,
                name            TEXT NOT NULL,
                type            TEXT NOT NULL,
                normal_balance  TEXT NOT NULL DEFAULT 'Debit',
                vat_applicable  TEXT NOT NULL DEFAULT 'No',
                vat_rate        REAL,
                system_locked   INTEGER NOT NULL DEFAULT 0,
                active          INTEGER NOT NULL DEFAULT 1,
                UNIQUE(entity_id, code)
            )""",

            # ── transactions (staging) ───────────────────────────────────────
            """CREATE TABLE IF NOT EXISTS transactions (
                tx_id           TEXT PRIMARY KEY,
                entity_id       TEXT NOT NULL REFERENCES entities(entity_id),
                batch_id        TEXT NOT NULL,
                date            TEXT NOT NULL,
                amount          REAL NOT NULL,
                description     TEXT,
                payee           TEXT,
                source          TEXT NOT NULL DEFAULT 'CSV_IMPORT',
                status          TEXT NOT NULL DEFAULT 'staged',
                created_at      TEXT NOT NULL
            )""",

            # ── ai_allocations ───────────────────────────────────────────────
            """CREATE TABLE IF NOT EXISTS ai_allocations (
                alloc_id        TEXT PRIMARY KEY,
                tx_id           TEXT NOT NULL REFERENCES transactions(tx_id),
                account_code    TEXT NOT NULL,
                vat_code        TEXT NOT NULL DEFAULT 'OS',
                confidence      REAL NOT NULL DEFAULT 0,
                method          TEXT NOT NULL DEFAULT 'heuristic',
                rule_id         TEXT,
                override        INTEGER NOT NULL DEFAULT 0,
                override_reason TEXT
            )""",

            # ── rule_library ─────────────────────────────────────────────────
            """CREATE TABLE IF NOT EXISTS rule_library (
                rule_id             TEXT PRIMARY KEY,
                entity_id           TEXT REFERENCES entities(entity_id),
                scope               TEXT NOT NULL DEFAULT 'entity',
                payee_pattern       TEXT,
                keyword_pattern     TEXT,
                account_code        TEXT NOT NULL,
                vat_code            TEXT NOT NULL DEFAULT 'OS',
                created_from_tx_id  TEXT,
                created_at          TEXT NOT NULL
            )""",

            # ── gl ───────────────────────────────────────────────────────────
            """CREATE TABLE IF NOT EXISTS gl (
                gl_id           TEXT PRIMARY KEY,
                entity_id       TEXT NOT NULL REFERENCES entities(entity_id),
                account_code    TEXT NOT NULL,
                date            TEXT NOT NULL,
                description     TEXT,
                debit           REAL NOT NULL DEFAULT 0,
                credit          REAL NOT NULL DEFAULT 0,
                vat_code        TEXT NOT NULL DEFAULT 'OS',
                vat_amount      REAL NOT NULL DEFAULT 0,
                source          TEXT NOT NULL,
                batch_id        TEXT,
                approval_id     TEXT,
                period          TEXT NOT NULL,
                locked          INTEGER NOT NULL DEFAULT 0
            )""",

            # ── approvals ────────────────────────────────────────────────────
            """CREATE TABLE IF NOT EXISTS approvals (
                approval_id     TEXT PRIMARY KEY,
                entity_id       TEXT NOT NULL REFERENCES entities(entity_id),
                checkpoint      INTEGER NOT NULL,
                period          TEXT NOT NULL,
                approver_name   TEXT NOT NULL,
                approver_role   TEXT NOT NULL,
                timestamp       TEXT NOT NULL,
                action          TEXT NOT NULL DEFAULT 'APPROVED',
                notes           TEXT,
                document_hash   TEXT
            )""",

            # ── import_batches ────────────────────────────────────────────────
            """CREATE TABLE IF NOT EXISTS import_batches (
                batch_id        TEXT PRIMARY KEY,
                entity_id       TEXT NOT NULL REFERENCES entities(entity_id),
                filename        TEXT NOT NULL,
                file_type       TEXT NOT NULL,
                import_time     TEXT NOT NULL,
                row_count       INTEGER NOT NULL DEFAULT 0,
                status          TEXT NOT NULL DEFAULT 'imported'
            )""",
        ]

        for stmt in stmts:
            self._conn.execute(stmt)
        self._conn.commit()

        # ── Migrations (safe to re-run) ───────────────────────────────────────
        migrations = [
            "ALTER TABLE entities ADD COLUMN vat_registered INTEGER NOT NULL DEFAULT 1",
        ]
        for m in migrations:
            try:
                self._conn.execute(m)
                self._conn.commit()
            except Exception:
                pass  # column already exists
        log.info("Schema initialised")


# ── Module-level singleton ───────────────────────────────────────────────────
db = Database()
_db_password: str = ""   # stored so worker threads can open their own connection


def open_thread_connection() -> "Database":
    """Open a fresh DB connection for use in a background thread."""
    conn = Database()
    conn.open(_db_password)
    return conn
