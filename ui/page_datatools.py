"""
fos/ui/page_datatools.py
Data Tools — user-controlled cleanup and maintenance.

Testing Mode : all operations freely available
Live Mode    : destructive operations require typed confirmation
"""

from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QFrame, QLineEdit,
    QDialog, QDialogButtonBox, QWidget
)
from PyQt6.QtCore import Qt

from ui.widgets import (
    BasePage, Card, PrimaryButton, SecondaryButton, ComboField,
    make_table, set_row,
    info, error, confirm,
    ACCENT, DARK, TEXT, MUTED, WHITE, BG, SUCCESS, WARN, DANGER, BORDER,
    _DIALOG_SS
)
from core.models import EntityModel
from core.database import db
import core.settings as settings


# ── Typed-confirmation dialog (Live Mode guard) ───────────────────────────────

class _TypeConfirmDialog(QDialog):
    """Requires the user to type a specific word before proceeding."""

    def __init__(self, parent, title: str, message: str, expected: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self.setStyleSheet(_DIALOG_SS)
        self._expected = expected.strip().lower()

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)

        lbl_msg = QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        lay.addWidget(lbl_msg)

        lbl_inst = QLabel(f'Type  <b>{expected}</b>  below to confirm:')
        lbl_inst.setStyleSheet(f"color:{DANGER}; font-size:13px;")
        lay.addWidget(lbl_inst)

        self.f_input = QLineEdit()
        self.f_input.setFixedHeight(36)
        self.f_input.setStyleSheet(
            f"border:2px solid {DANGER}; border-radius:4px; "
            f"padding:0 10px; font-size:14px; font-weight:bold;"
        )
        self.f_input.textChanged.connect(self._on_text)
        lay.addWidget(self.f_input)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Confirm Delete")
        btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            f"background:{DANGER}; color:white; border-radius:4px; padding:6px 16px;"
        )
        self._ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _on_text(self, text: str):
        self._ok_btn.setEnabled(text.strip().lower() == self._expected)

    def confirmed(self) -> bool:
        return self.exec() == QDialog.DialogCode.Accepted


# ── Main page ─────────────────────────────────────────────────────────────────

class DataToolsPage(BasePage):
    def __init__(self):
        super().__init__("Data Tools",
                         "Cleanup and maintenance — behaviour depends on app mode")
        self._entity_id   = ""
        self._entity_name = ""
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        # Mode banner
        self.mode_bar = QFrame()
        self.mode_bar.setFixedHeight(48)
        mode_lay = QHBoxLayout(self.mode_bar)
        mode_lay.setContentsMargins(16, 0, 16, 0)

        self.lbl_mode = QLabel()
        self.lbl_mode.setStyleSheet("font-size:13px; font-weight:bold; border:none;")
        self.lbl_mode_desc = QLabel()
        self.lbl_mode_desc.setStyleSheet(f"font-size:12px; color:{MUTED}; border:none;")

        self.btn_switch_mode = SecondaryButton("")
        self.btn_switch_mode.setFixedWidth(180)
        self.btn_switch_mode.clicked.connect(self._switch_mode)

        mode_lay.addWidget(self.lbl_mode)
        mode_lay.addWidget(self.lbl_mode_desc)
        mode_lay.addStretch()
        mode_lay.addWidget(self.btn_switch_mode)
        self.layout_.addWidget(self.mode_bar)
        self._refresh_mode_banner()

        # Summary card
        sum_card = Card("Data Summary — Current Company")
        self.tbl_summary = make_table(
            ["Period", "GL Entries", "Staged Tx", "Approved Tx"], stretch_col=0
        )
        self.tbl_summary.setFixedHeight(200)
        btn_ref = SecondaryButton("⟳  Refresh Summary")
        btn_ref.clicked.connect(self._refresh_summary)
        sum_card.body().addWidget(self.tbl_summary)
        sum_card.body().addWidget(btn_ref)
        self.layout_.addWidget(sum_card)

        # Tool grid
        grid = QHBoxLayout()
        grid.setSpacing(12)
        left  = QVBoxLayout()
        right = QVBoxLayout()

        # ── Always safe ───────────────────────────────────────────────────────
        dedup_card = Card("Remove Duplicate GL Entries  ✓ Always available")
        dedup_body = dedup_card.body()
        lbl = QLabel("Finds GL rows with identical account/date/amount/description posted "
                     "more than once and removes the extras.")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{MUTED}; font-size:12px;")
        dedup_body.addWidget(lbl)
        btn_dedup = PrimaryButton("Remove GL Duplicates")
        btn_dedup.clicked.connect(self._dedup_gl)
        dedup_body.addWidget(btn_dedup)
        left.addWidget(dedup_card)

        staged_card = Card("Clear Staged Transactions  ✓ Always available")
        staged_body = staged_card.body()
        lbl2 = QLabel("Removes all unprocessed (not yet committed) transactions. "
                      "GL entries are unaffected. Re-import files afterwards.")
        lbl2.setWordWrap(True)
        lbl2.setStyleSheet(f"color:{MUTED}; font-size:12px;")
        staged_body.addWidget(lbl2)
        btn_staged = PrimaryButton("Clear Staged Transactions", colour=WARN)
        btn_staged.clicked.connect(self._clear_staged)
        staged_body.addWidget(btn_staged)
        left.addWidget(staged_card)
        left.addStretch()

        # ── Gated in Live Mode ────────────────────────────────────────────────
        period_card = Card("Delete GL for a Period  ⚠ Gated in Live Mode")
        period_body = period_card.body()
        lbl3 = QLabel("Permanently deletes all GL entries for one period. "
                      "Staged/approved transactions are kept so you can re-commit.")
        lbl3.setWordWrap(True)
        lbl3.setStyleSheet(f"color:{MUTED}; font-size:12px;")
        period_body.addWidget(lbl3)
        self.cbo_period_del = ComboField(["— refresh summary first —"])
        period_body.addWidget(self.cbo_period_del)
        btn_del_period = PrimaryButton("Delete GL for This Period", colour=DANGER)
        btn_del_period.clicked.connect(self._delete_gl_period)
        period_body.addWidget(btn_del_period)
        right.addWidget(period_card)

        filter_card = Card("Delete GL by Description Filter  ⚠ Gated in Live Mode")
        filter_body = filter_card.body()
        lbl4 = QLabel("Deletes GL entries whose description contains the text below. "
                      'Example: type "[Monzo]" to remove all Monzo entries.')
        lbl4.setWordWrap(True)
        lbl4.setStyleSheet(f"color:{MUTED}; font-size:12px;")
        filter_body.addWidget(lbl4)
        self.f_filter = QLineEdit()
        self.f_filter.setPlaceholderText("e.g.  [Monzo]  or  salary")
        self.f_filter.setFixedHeight(34)
        self.f_filter.setStyleSheet(
            f"border:1px solid {BORDER}; border-radius:4px; padding:0 10px; font-size:13px;"
        )
        filter_body.addWidget(self.f_filter)
        row_f = QHBoxLayout()
        btn_prev = SecondaryButton("Preview Matches")
        btn_prev.clicked.connect(self._preview_filter)
        btn_del_f = PrimaryButton("Delete Matching", colour=DANGER)
        btn_del_f.clicked.connect(self._delete_gl_filter)
        row_f.addWidget(btn_prev)
        row_f.addWidget(btn_del_f)
        filter_body.addLayout(row_f)
        self.lbl_preview = QLabel("")
        self.lbl_preview.setStyleSheet(f"color:{ACCENT}; font-size:12px;")
        filter_body.addWidget(self.lbl_preview)
        right.addWidget(filter_card)

        reset_card = Card("Reset Entire Company GL  🔴 Gated in Live Mode")
        reset_body = reset_card.body()
        lbl5 = QLabel("⚠  Deletes ALL GL entries and ALL transactions (staged + approved) "
                      "for this company. Chart of Accounts is NOT affected.")
        lbl5.setWordWrap(True)
        lbl5.setStyleSheet(f"color:{DANGER}; font-size:12px; font-weight:bold;")
        reset_body.addWidget(lbl5)
        btn_reset = PrimaryButton("Reset Entire Company GL", colour=DANGER)
        btn_reset.clicked.connect(self._reset_company_gl)
        reset_body.addWidget(btn_reset)
        right.addWidget(reset_card)
        right.addStretch()

        grid.addLayout(left, 1)
        grid.addLayout(right, 1)
        self.layout_.addLayout(grid)
        self.layout_.addStretch()

    # ── Mode banner ───────────────────────────────────────────────────────────

    def _refresh_mode_banner(self):
        live = settings.is_live()
        if live:
            self.mode_bar.setStyleSheet(
                f"background:#FDECEA; border-radius:6px; border:1px solid #F5C6CB;"
            )
            self.lbl_mode.setText("🔴  LIVE MODE")
            self.lbl_mode.setStyleSheet(f"font-size:13px; font-weight:bold; color:{DANGER}; border:none;")
            self.lbl_mode_desc.setText(
                "   Destructive operations require you to type the company name to confirm."
            )
            self.btn_switch_mode.setText("Switch to Testing Mode")
        else:
            self.mode_bar.setStyleSheet(
                f"background:#E8F5EE; border-radius:6px; border:1px solid #C3E6CB;"
            )
            self.lbl_mode.setText("🟢  TESTING MODE")
            self.lbl_mode.setStyleSheet(f"font-size:13px; font-weight:bold; color:{SUCCESS}; border:none;")
            self.lbl_mode_desc.setText(
                "   All operations are freely available. Switch to Live Mode before going live."
            )
            self.btn_switch_mode.setText("Switch to Live Mode")

    def _switch_mode(self):
        live = settings.is_live()
        if live:
            if confirm(self, "Switch to Testing Mode",
                       "Switching to Testing Mode removes the confirmation guards "
                       "on destructive data operations.\n\n"
                       "Only use this during development/testing.\n\nProceed?"):
                settings.set_("app_mode", "testing")
                self._refresh_mode_banner()
        else:
            if confirm(self, "Switch to Live Mode",
                       "Switching to Live Mode adds confirmation guards to all "
                       "destructive data operations.\n\n"
                       "Do this before importing real accounting data.\n\nProceed?"):
                settings.set_("app_mode", "live")
                self._refresh_mode_banner()

    # ── Live Mode gate ────────────────────────────────────────────────────────

    def _live_confirm(self, title: str, message: str) -> bool:
        """In Live Mode: require typed company name. In Testing Mode: simple confirm."""
        if settings.is_testing():
            return confirm(self, title, message)
        dlg = _TypeConfirmDialog(
            self, title,
            message + f"\n\nThis is a LIVE system. Type the company name below to confirm:",
            self._entity_name
        )
        return dlg.confirmed()

    # ── Entity wiring ─────────────────────────────────────────────────────────

    def set_active_entity(self, entity_id: str) -> None:
        self._entity_id   = entity_id
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
        gl_rows = db.fetchall(
            "SELECT period, COUNT(*) AS cnt FROM gl WHERE entity_id=? "
            "GROUP BY period ORDER BY period DESC",
            (self._entity_id,)
        )
        staged = {r["period"]: r["cnt"] for r in db.fetchall(
            "SELECT substr(date,1,7) AS period, COUNT(*) AS cnt "
            "FROM transactions WHERE entity_id=? AND status='staged' GROUP BY period",
            (self._entity_id,)
        )}
        approved = {r["period"]: r["cnt"] for r in db.fetchall(
            "SELECT substr(date,1,7) AS period, COUNT(*) AS cnt "
            "FROM transactions WHERE entity_id=? AND status='approved' GROUP BY period",
            (self._entity_id,)
        )}
        all_periods = sorted(
            set([r["period"] for r in gl_rows] + list(staged) + list(approved)),
            reverse=True
        )
        self.tbl_summary.setRowCount(0)
        for i, p in enumerate(all_periods):
            gl_cnt = next((r["cnt"] for r in gl_rows if r["period"] == p), 0)
            set_row(self.tbl_summary, i, [p, str(gl_cnt),
                                          str(staged.get(p, 0)),
                                          str(approved.get(p, 0))])
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
        n = db.fetchone(
            """SELECT COUNT(*) AS cnt FROM gl
               WHERE entity_id=? AND gl_id NOT IN (
                   SELECT MIN(gl_id) FROM gl WHERE entity_id=?
                   GROUP BY account_code, date, description, debit, credit, period
               )""",
            (self._entity_id, self._entity_id)
        )["cnt"]
        if n == 0:
            info(self, "No Duplicates", f"No duplicate GL entries for {self._entity_name}.")
            return
        if not confirm(self, "Remove Duplicates",
                       f"Found {n} duplicate GL entries. Remove them?"):
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
                       f"Delete {n} staged (unprocessed) transactions for {self._entity_name}?\n\n"
                       f"GL entries are not affected."):
            return
        db.execute("DELETE FROM transactions WHERE entity_id=? AND status='staged'",
                   (self._entity_id,))
        db.commit()
        info(self, "Cleared", f"{n} staged transactions removed.")
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
        if not self._live_confirm(
            "Delete GL Period",
            f"Permanently delete {n} GL entries for {self._entity_name} — {period}."
        ):
            return
        db.execute("DELETE FROM gl WHERE entity_id=? AND period=?",
                   (self._entity_id, period))
        db.commit()
        info(self, "Deleted", f"{n} GL entries for {period} removed.")
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
        self.lbl_preview.setText(f"→  {n} GL entries match '{text}' in {self._entity_name}")

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
        if not self._live_confirm(
            "Delete Filtered GL",
            f"Delete {n} GL entries containing '{text}' for {self._entity_name}."
        ):
            return
        db.execute("DELETE FROM gl WHERE entity_id=? AND description LIKE ?",
                   (self._entity_id, f"%{text}%"))
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
        if not self._live_confirm(
            "⚠ FULL RESET",
            f"This will permanently delete:\n\n"
            f"  • {gl_n} GL entries\n"
            f"  • {tx_n} transactions (staged + approved)\n\n"
            f"for {self._entity_name}.\n"
            f"Chart of Accounts is NOT affected."
        ):
            return
        db.execute("DELETE FROM gl WHERE entity_id=?", (self._entity_id,))
        db.execute("DELETE FROM transactions WHERE entity_id=?", (self._entity_id,))
        db.commit()
        info(self, "Reset Complete",
             f"All GL and transaction data for {self._entity_name} cleared.\n"
             f"You can now re-import clean bank statements.")
        self._refresh_summary()
