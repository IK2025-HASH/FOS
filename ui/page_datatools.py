"""
fos/ui/page_datatools.py
Data Tools — user-controlled cleanup and maintenance operations.
All operations require explicit confirmation. Nothing runs automatically.
"""

from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QFrame, QLineEdit, QWidget
)
from PyQt6.QtCore import Qt

from ui.widgets import (
    BasePage, Card, PrimaryButton, SecondaryButton, ComboField,
    make_table, set_row,
    info, error, confirm,
    ACCENT, DARK, TEXT, MUTED, WHITE, BG, SUCCESS, WARN, DANGER, BORDER
)
from core.models import EntityModel
from core.database import db


class DataToolsPage(BasePage):
    def __init__(self):
        super().__init__("Data Tools",
                         "User-controlled cleanup and maintenance — nothing runs automatically")
        self._entity_id   = ""
        self._entity_name = ""
        self._entity_map  = {}
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        warn_bar = QLabel(
            "⚠  All operations below are permanent and cannot be undone. "
            "Each action requires your explicit confirmation before any data is changed."
        )
        warn_bar.setWordWrap(True)
        warn_bar.setStyleSheet(
            f"background:#FFF3CD; color:#856404; border:1px solid #FFEAA7; "
            f"border-radius:6px; padding:10px 14px; font-size:12px;"
        )
        self.layout_.addWidget(warn_bar)

        # ── Summary card ──────────────────────────────────────────────────────
        sum_card = Card("Data Summary — Current Company")
        self.tbl_summary = make_table(
            ["Period", "GL Entries", "Staged Tx", "Approved Tx"],
            stretch_col=0
        )
        self.tbl_summary.setFixedHeight(220)
        self.btn_refresh_summary = SecondaryButton("⟳  Refresh Summary")
        self.btn_refresh_summary.clicked.connect(self._refresh_summary)
        sum_card.body().addWidget(self.tbl_summary)
        sum_card.body().addWidget(self.btn_refresh_summary)
        self.layout_.addWidget(sum_card)

        # ── Two-column tool grid ───────────────────────────────────────────────
        grid = QHBoxLayout()
        grid.setSpacing(12)

        left  = QVBoxLayout()
        right = QVBoxLayout()

        # ── Deduplicate GL ────────────────────────────────────────────────────
        dedup_card = Card("Remove Duplicate GL Entries")
        dedup_body = dedup_card.body()
        dedup_body.addWidget(QLabel(
            "Finds GL rows with identical account, date, amount and description "
            "posted more than once, and removes the extras keeping one copy."
        ))
        dedup_body.itemAt(0).widget().setStyleSheet(f"color:{MUTED}; font-size:12px;")
        dedup_body.itemAt(0).widget().setWordWrap(True)
        btn_dedup = PrimaryButton("Remove GL Duplicates")
        btn_dedup.clicked.connect(self._dedup_gl)
        dedup_body.addWidget(btn_dedup)
        left.addWidget(dedup_card)

        # ── Delete GL by period ───────────────────────────────────────────────
        period_card = Card("Delete GL Entries for a Period")
        period_body = period_card.body()
        period_body.addWidget(QLabel("Select a period to permanently delete all GL entries:"))
        period_body.itemAt(0).widget().setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.cbo_period_del = ComboField(["— refresh summary first —"])
        self.cbo_period_del.setMinimumWidth(160)
        period_body.addWidget(self.cbo_period_del)
        btn_del_period = PrimaryButton("Delete All GL for This Period", colour=DANGER)
        btn_del_period.clicked.connect(self._delete_gl_period)
        period_body.addWidget(btn_del_period)
        left.addWidget(period_card)

        # ── Clear staged transactions ─────────────────────────────────────────
        staged_card = Card("Clear Staged Transactions")
        staged_body = staged_card.body()
        staged_body.addWidget(QLabel(
            "Removes all unprocessed (staged) transactions for this company. "
            "Use when you want to re-import clean files from scratch."
        ))
        staged_body.itemAt(0).widget().setStyleSheet(f"color:{MUTED}; font-size:12px;")
        staged_body.itemAt(0).widget().setWordWrap(True)
        btn_clear_staged = PrimaryButton("Clear All Staged Transactions", colour=WARN)
        btn_clear_staged.clicked.connect(self._clear_staged)
        staged_body.addWidget(btn_clear_staged)
        right.addWidget(staged_card)

        # ── Delete GL by description filter ──────────────────────────────────
        filter_card = Card("Delete GL Entries by Description Filter")
        filter_body = filter_card.body()
        filter_body.addWidget(QLabel(
            "Deletes all GL entries whose description contains the text below.\n"
            "Example: type '[Monzo]' to remove all Monzo entries."
        ))
        filter_body.itemAt(0).widget().setStyleSheet(f"color:{MUTED}; font-size:12px;")
        filter_body.itemAt(0).widget().setWordWrap(True)
        self.f_filter = QLineEdit()
        self.f_filter.setPlaceholderText("e.g.  [Monzo]  or  salary")
        self.f_filter.setFixedHeight(34)
        self.f_filter.setStyleSheet(
            f"border:1px solid {BORDER}; border-radius:4px; padding:0 10px; font-size:13px;"
        )
        filter_body.addWidget(self.f_filter)
        btn_preview = SecondaryButton("Preview Matches")
        btn_preview.clicked.connect(self._preview_filter)
        btn_del_filter = PrimaryButton("Delete Matching GL Entries", colour=DANGER)
        btn_del_filter.clicked.connect(self._delete_gl_filter)
        row = QHBoxLayout()
        row.addWidget(btn_preview)
        row.addWidget(btn_del_filter)
        filter_body.addLayout(row)

        self.lbl_preview = QLabel("")
        self.lbl_preview.setStyleSheet(f"color:{ACCENT}; font-size:12px;")
        filter_body.addWidget(self.lbl_preview)
        right.addWidget(filter_card)

        # ── Reset entire company GL ───────────────────────────────────────────
        reset_card = Card("Reset All GL for This Company")
        reset_body = reset_card.body()
        reset_body.addWidget(QLabel(
            "⚠  DANGER: Deletes ALL General Ledger entries and ALL transactions "
            "(staged and approved) for the currently selected company. "
            "Use only to start fresh after a bad import."
        ))
        reset_body.itemAt(0).widget().setStyleSheet(
            f"color:{DANGER}; font-size:12px; font-weight:bold;"
        )
        reset_body.itemAt(0).widget().setWordWrap(True)
        btn_reset = PrimaryButton("Reset Entire Company GL", colour=DANGER)
        btn_reset.clicked.connect(self._reset_company_gl)
        reset_body.addWidget(btn_reset)
        right.addWidget(reset_card)

        left.addStretch()
        right.addStretch()
        grid.addLayout(left, 1)
        grid.addLayout(right, 1)
        self.layout_.addLayout(grid)
        self.layout_.addStretch()

    # ── Entity wiring ─────────────────────────────────────────────────────────

    def set_active_entity(self, entity_id: str) -> None:
        self._entity_id = entity_id
        e = EntityModel.get(entity_id) if entity_id else None
        self._entity_name = e["legal_name"] if e else ""
        self.lbl_preview.setText("")
        self._refresh_summary()

    def refresh_entities(self):
        import core.context as ctx
        eid = ctx.get_entity_id()
        if eid:
            self.set_active_entity(eid)

    # ── Summary ───────────────────────────────────────────────────────────────

    def _refresh_summary(self):
        if not self._entity_id:
            return
        rows = db.fetchall(
            """SELECT period,
                      COUNT(*) AS gl_count
               FROM gl WHERE entity_id=?
               GROUP BY period ORDER BY period DESC""",
            (self._entity_id,)
        )
        staged = db.fetchall(
            """SELECT substr(date,1,7) AS period, COUNT(*) AS cnt
               FROM transactions WHERE entity_id=? AND status='staged'
               GROUP BY period ORDER BY period DESC""",
            (self._entity_id,)
        )
        approved = db.fetchall(
            """SELECT substr(date,1,7) AS period, COUNT(*) AS cnt
               FROM transactions WHERE entity_id=? AND status='approved'
               GROUP BY period ORDER BY period DESC""",
            (self._entity_id,)
        )
        staged_map   = {r["period"]: r["cnt"] for r in staged}
        approved_map = {r["period"]: r["cnt"] for r in approved}

        all_periods = sorted(
            set([r["period"] for r in rows] + list(staged_map) + list(approved_map)),
            reverse=True
        )
        self.tbl_summary.setRowCount(0)
        for i, p in enumerate(all_periods):
            gl_cnt = next((r["gl_count"] for r in rows if r["period"] == p), 0)
            set_row(self.tbl_summary, i, [
                p,
                str(gl_cnt),
                str(staged_map.get(p, 0)),
                str(approved_map.get(p, 0)),
            ])

        # Populate period delete dropdown
        self.cbo_period_del.blockSignals(True)
        self.cbo_period_del.clear()
        for p in all_periods:
            self.cbo_period_del.addItem(p)
        if not all_periods:
            self.cbo_period_del.addItem("— no data —")
        self.cbo_period_del.blockSignals(False)

    # ── Operations ────────────────────────────────────────────────────────────

    def _require_entity(self) -> bool:
        if not self._entity_id:
            error(self, "No Company", "Select a company from the sidebar first.")
            return False
        return True

    def _dedup_gl(self):
        if not self._require_entity():
            return
        preview = db.fetchone(
            """SELECT COUNT(*) AS cnt FROM gl
               WHERE entity_id=? AND gl_id NOT IN (
                   SELECT MIN(gl_id)
                   FROM gl WHERE entity_id=?
                   GROUP BY account_code, date, description, debit, credit, period
               )""",
            (self._entity_id, self._entity_id)
        )
        n = preview["cnt"] if preview else 0
        if n == 0:
            info(self, "No Duplicates", f"No duplicate GL entries found for {self._entity_name}.")
            return
        if not confirm(self, "Remove Duplicates",
                       f"Found {n} duplicate GL entries for {self._entity_name}.\n\n"
                       f"Remove them now?"):
            return
        db.execute(
            """DELETE FROM gl WHERE entity_id=? AND gl_id NOT IN (
                   SELECT MIN(gl_id) FROM gl WHERE entity_id=?
                   GROUP BY account_code, date, description, debit, credit, period
               )""",
            (self._entity_id, self._entity_id)
        )
        db.commit()
        info(self, "Done", f"Removed {n} duplicate GL entries.")
        self._refresh_summary()

    def _delete_gl_period(self):
        if not self._require_entity():
            return
        period = self.cbo_period_del.currentText().strip()
        if not period or period.startswith("—"):
            error(self, "No Period", "Select a period first.")
            return
        n = db.fetchone(
            "SELECT COUNT(*) AS cnt FROM gl WHERE entity_id=? AND period=?",
            (self._entity_id, period)
        )["cnt"]
        if n == 0:
            info(self, "Nothing Found", f"No GL entries for {period}.")
            return
        if not confirm(self, "Delete GL Period",
                       f"Permanently delete {n} GL entries for {self._entity_name} — {period}?\n\n"
                       f"Staged/approved transactions for this period are NOT deleted "
                       f"so you can re-allocate and re-commit if needed."):
            return
        db.execute("DELETE FROM gl WHERE entity_id=? AND period=?",
                   (self._entity_id, period))
        db.commit()
        info(self, "Deleted", f"{n} GL entries for {period} removed.")
        self._refresh_summary()

    def _clear_staged(self):
        if not self._require_entity():
            return
        n = db.fetchone(
            "SELECT COUNT(*) AS cnt FROM transactions WHERE entity_id=? AND status='staged'",
            (self._entity_id,)
        )["cnt"]
        if n == 0:
            info(self, "Nothing to Clear", "No staged transactions.")
            return
        if not confirm(self, "Clear Staged",
                       f"Delete {n} staged transactions for {self._entity_name}?\n\n"
                       f"GL entries are NOT affected. You can re-import files after this."):
            return
        db.execute(
            "DELETE FROM transactions WHERE entity_id=? AND status='staged'",
            (self._entity_id,)
        )
        db.commit()
        info(self, "Cleared", f"{n} staged transactions removed.")
        self._refresh_summary()

    def _preview_filter(self):
        if not self._require_entity():
            return
        text = self.f_filter.text().strip()
        if not text:
            error(self, "No Filter", "Enter a description filter first.")
            return
        n = db.fetchone(
            "SELECT COUNT(*) AS cnt FROM gl WHERE entity_id=? AND description LIKE ?",
            (self._entity_id, f"%{text}%")
        )["cnt"]
        self.lbl_preview.setText(
            f"→  {n} GL entries match '{text}' in {self._entity_name}"
        )

    def _delete_gl_filter(self):
        if not self._require_entity():
            return
        text = self.f_filter.text().strip()
        if not text:
            error(self, "No Filter", "Enter a description filter first.")
            return
        n = db.fetchone(
            "SELECT COUNT(*) AS cnt FROM gl WHERE entity_id=? AND description LIKE ?",
            (self._entity_id, f"%{text}%")
        )["cnt"]
        if n == 0:
            info(self, "No Matches", f"No GL entries matching '{text}'.")
            return
        if not confirm(self, "Delete Filtered GL",
                       f"Delete {n} GL entries containing '{text}' for {self._entity_name}?\n\n"
                       f"This cannot be undone."):
            return
        db.execute(
            "DELETE FROM gl WHERE entity_id=? AND description LIKE ?",
            (self._entity_id, f"%{text}%")
        )
        db.commit()
        self.lbl_preview.setText("")
        info(self, "Deleted", f"{n} GL entries matching '{text}' removed.")
        self._refresh_summary()

    def _reset_company_gl(self):
        if not self._require_entity():
            return
        gl_n = db.fetchone(
            "SELECT COUNT(*) AS cnt FROM gl WHERE entity_id=?", (self._entity_id,)
        )["cnt"]
        tx_n = db.fetchone(
            "SELECT COUNT(*) AS cnt FROM transactions WHERE entity_id=?", (self._entity_id,)
        )["cnt"]
        if not confirm(self, "⚠ FULL RESET — Are you absolutely sure?",
                       f"This will permanently delete:\n\n"
                       f"  • {gl_n} GL entries\n"
                       f"  • {tx_n} transactions (staged + approved)\n\n"
                       f"for {self._entity_name}.\n\n"
                       f"Type of data lost: all periods, all years.\n"
                       f"Chart of Accounts is NOT affected.\n\n"
                       f"THIS CANNOT BE UNDONE. Proceed?"):
            return
        db.execute("DELETE FROM gl WHERE entity_id=?", (self._entity_id,))
        db.execute("DELETE FROM transactions WHERE entity_id=?", (self._entity_id,))
        db.commit()
        info(self, "Reset Complete",
             f"All GL and transaction data for {self._entity_name} has been cleared.\n"
             f"You can now re-import clean bank statements.")
        self._refresh_summary()
