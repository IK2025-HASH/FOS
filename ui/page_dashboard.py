"""
fos/ui/page_dashboard.py
Dashboard — at-a-glance summary across all entities.
"""

from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QLabel, QGridLayout, QWidget
from PyQt6.QtCore import Qt

from ui.widgets import (
    BasePage, Card, PrimaryButton, SecondaryButton, ComboField,
    make_table, set_row, confirm, info,
    ACCENT, DARK, TEXT, MUTED, WHITE, BG, SUCCESS, WARN, DANGER, BORDER
)
from core.models import EntityModel, GLModel, DataUtils
from core.database import db


class DashboardPage(BasePage):
    def __init__(self, navigate_fn=None):
        super().__init__("Dashboard", "Overview across all business entities")
        self._navigate = navigate_fn
        self._build()

    def _build(self):
        # Quick action buttons
        btn_row = QHBoxLayout()
        for label, target in [
            ("+ New Company",         "company"),
            ("Import Transactions",   "import"),
            ("Review Allocations",    "allocation"),
            ("View Trial Balance",    "tb"),
        ]:
            btn = SecondaryButton(label)
            if self._navigate:
                btn.clicked.connect(lambda _, t=target: self._navigate(t))
            btn_row.addWidget(btn)
        btn_row.addStretch()

        btn_clear = SecondaryButton("🗑  Clear Test Data")
        btn_clear.setStyleSheet(
            btn_clear.styleSheet().replace(f"color:{ACCENT}", f"color:{DANGER}")
                                  .replace(f"border:2px solid {ACCENT}", f"border:2px solid {DANGER}")
        )
        btn_clear.clicked.connect(self._clear_test_data)
        btn_row.addWidget(btn_clear)

        self.layout_.addLayout(btn_row)

        # Entity summary grid
        self.grid_card = Card("Business Entities")
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(12)
        self.grid_card.body().addLayout(self.grid_layout)
        self.layout_.addWidget(self.grid_card)

        # Pending allocations
        pend_card = Card("Pending Allocations (Awaiting Review)")
        self.tbl_pending = make_table(
            ["Company", "Staged Transactions", "High", "Medium", "Low / Unclassified"],
            stretch_col=0
        )
        self.tbl_pending.setFixedHeight(160)
        pend_card.body().addWidget(self.tbl_pending)
        self.layout_.addWidget(pend_card)

        # Recent GL activity
        gl_card = Card("Recent GL Activity")
        self.tbl_gl = make_table(
            ["Date", "Company", "Account", "Description", "Debit £", "Credit £"],
            stretch_col=3
        )
        self.tbl_gl.setFixedHeight(200)
        gl_card.body().addWidget(self.tbl_gl)
        self.layout_.addWidget(gl_card)

        self.layout_.addStretch()
        self.refresh()

    def refresh(self):
        # Clear grid
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        entities = EntityModel.list_all()
        if not entities:
            placeholder = QLabel(
                "No companies yet.  Create your first company profile to get started."
            )
            placeholder.setStyleSheet(
                f"color:{MUTED}; font-size:13px; font-style:italic; padding:20px;"
            )
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid_layout.addWidget(placeholder, 0, 0)
        else:
            for idx, e in enumerate(entities):
                card = self._entity_card(e)
                self.grid_layout.addWidget(card, idx // 3, idx % 3)

        # Pending table
        self.tbl_pending.setRowCount(0)
        for i, e in enumerate(entities):
            staged = db.fetchall(
                """SELECT a.confidence FROM transactions t
                   LEFT JOIN ai_allocations a ON a.tx_id = t.tx_id
                   WHERE t.entity_id=? AND t.status='staged'""",
                (e["entity_id"],)
            )
            if not staged:
                continue
            high = sum(1 for r in staged if (r.get("confidence") or 0) >= 90)
            med  = sum(1 for r in staged if 70 <= (r.get("confidence") or 0) < 90)
            low  = len(staged) - high - med
            set_row(self.tbl_pending, self.tbl_pending.rowCount(), [
                e["legal_name"], str(len(staged)),
                str(high), str(med), str(low)
            ])

        # Recent GL
        gl_rows = db.fetchall(
            """SELECT g.date, e.legal_name, g.account_code, g.description,
                      g.debit, g.credit
               FROM gl g
               JOIN entities e ON e.entity_id = g.entity_id
               ORDER BY g.date DESC, g.gl_id DESC LIMIT 20"""
        )
        self.tbl_gl.setRowCount(0)
        for i, r in enumerate(gl_rows):
            set_row(self.tbl_gl, i, [
                r["date"][:10],
                r["legal_name"],
                r["account_code"],
                (r.get("description") or "")[:60],
                f"{float(r['debit']):,.2f}"  if float(r['debit'])  else "",
                f"{float(r['credit']):,.2f}" if float(r['credit']) else "",
            ])

    def _clear_test_data(self):
        entities = EntityModel.list_all()
        if not entities:
            return
        names = [e["legal_name"] for e in entities]
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox
        from ui.widgets import ComboField, _DIALOG_SS, DANGER, TEXT
        dlg = QDialog(self)
        dlg.setWindowTitle("Clear Test Data")
        dlg.setStyleSheet("QDialog { background:white; } QLabel { color:" + TEXT + "; }")
        lay = QVBoxLayout(dlg)
        lay.setSpacing(12)
        lay.setContentsMargins(20,20,20,20)
        lbl = QLabel("Select company to clear ALL transactions, GL and approvals from:\n(Companies and Chart of Accounts are kept.)")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        cbo = ComboField(names)
        lay.addWidget(cbo)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.setStyleSheet("QPushButton { background:" + DANGER + "; color:white; border:none; border-radius:4px; padding:6px 20px; font-weight:bold; }")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        chosen = cbo.currentText()
        entity = next((e for e in entities if e["legal_name"] == chosen), None)
        if not entity:
            return
        if not confirm(self, "Confirm Clear",
                       f"Delete ALL transactions and GL entries for:\n{chosen}\n\nThis cannot be undone."):
            return
        n = DataUtils.clear_transactions(entity["entity_id"])
        info(self, "Cleared", f"✓  {n} transactions and all GL/approval records deleted for {chosen}.")
        self.refresh()

    def _entity_card(self, e: dict) -> QWidget:
        frame = Card(e["legal_name"])
        body  = frame.body()

        # Type badge
        type_lbl = QLabel(e["entity_type"])
        type_lbl.setStyleSheet(
            f"color:{MUTED}; font-size:11px; padding-top:0;"
        )
        body.addWidget(type_lbl)

        # GL balance summary
        tb = GLModel.get_trial_balance(e["entity_id"])
        income   = sum(float(r["balance"]) for r in tb if r["type"] == "Income")
        expenses = sum(abs(float(r["balance"])) for r in tb
                      if r["type"] in ("CoS","Overhead","Tax"))
        profit   = income - expenses

        profit_lbl = QLabel(
            f"Income: £{income:,.0f}    Expenses: £{expenses:,.0f}    "
            f"Profit: £{profit:,.0f}"
        )
        colour = SUCCESS if profit >= 0 else DANGER
        profit_lbl.setStyleSheet(f"font-size:12px; color:{colour}; font-weight:bold;")
        body.addWidget(profit_lbl)

        staged_count = db.fetchone(
            "SELECT COUNT(*) as n FROM transactions WHERE entity_id=? AND status='staged'",
            (e["entity_id"],)
        )
        n = staged_count["n"] if staged_count else 0
        if n > 0:
            pending = QLabel(f"⚠  {n} transactions awaiting allocation review")
            pending.setStyleSheet(f"font-size:11px; color:{WARN};")
            body.addWidget(pending)

        return frame
