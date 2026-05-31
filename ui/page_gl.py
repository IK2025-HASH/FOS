"""
fos/ui/page_gl.py
General Ledger and Trial Balance viewer.
"""

from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QLabel, QWidget
from PyQt6.QtCore import Qt

from ui.widgets import (
    BasePage, Card, SecondaryButton, ComboField,
    make_table, set_row,
    ACCENT, DARK, TEXT, MUTED, WHITE, BG, SUCCESS, DANGER, BORDER
)
from core.models import EntityModel, GLModel


class GLPage(BasePage):
    def __init__(self):
        super().__init__("General Ledger",
                         "View all committed transactions by account")
        self._entity_map: dict = {}
        self._build()

    def _build(self):
        bar = QHBoxLayout()
        lbl = QLabel("Company:")
        lbl.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.cbo_entity = ComboField(["— select company —"])
        self.cbo_entity.setMinimumWidth(260)
        self.cbo_entity.currentIndexChanged.connect(self._load)
        self.cbo_period = ComboField(["All Periods"])
        self.cbo_period.setMinimumWidth(140)
        self.cbo_period.currentIndexChanged.connect(self._load)
        self.btn_refresh = SecondaryButton("⟳  Refresh")
        self.btn_refresh.clicked.connect(self._load)
        bar.addWidget(lbl)
        bar.addWidget(self.cbo_entity)
        bar.addWidget(QLabel("  Period:"))
        bar.addWidget(self.cbo_period)
        bar.addStretch()
        bar.addWidget(self.btn_refresh)
        self.layout_.addLayout(bar)

        # Summary
        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet(f"color:{MUTED}; font-size:12px;")
        self.layout_.addWidget(self.lbl_summary)

        gl_card = Card("GL Entries")
        self.tbl = make_table(
            ["Date","Account","Description","Debit £","Credit £","VAT","Source","Period"],
            stretch_col=2
        )
        self.tbl.setMinimumHeight(450)
        self.tbl.setColumnWidth(0, 90)
        self.tbl.setColumnWidth(1, 120)
        self.tbl.setColumnWidth(3, 90)
        self.tbl.setColumnWidth(4, 90)
        self.tbl.setColumnWidth(5, 60)
        self.tbl.setColumnWidth(6, 90)
        self.tbl.setColumnWidth(7, 70)
        gl_card.body().addWidget(self.tbl)
        self.layout_.addWidget(gl_card)
        self.layout_.addStretch()
        self.refresh_entities()

    def refresh_entities(self):
        self.cbo_entity.blockSignals(True)
        self.cbo_entity.clear()
        self._entity_map = {}
        for e in EntityModel.list_all():
            self.cbo_entity.addItem(e["legal_name"])
            self._entity_map[e["legal_name"]] = e["entity_id"]
        if not self._entity_map:
            self.cbo_entity.addItem("— no companies yet —")
        self.cbo_entity.blockSignals(False)
        self._load()

    def _load(self):
        entity_id = self._entity_map.get(self.cbo_entity.currentText(),"")
        if not entity_id:
            return

        period = self.cbo_period.currentText()
        if period == "All Periods":
            period = None

        entries = GLModel.get_entries(entity_id, period)

        # Refresh period dropdown
        from core.database import db
        periods = db.fetchall(
            "SELECT DISTINCT period FROM gl WHERE entity_id=? ORDER BY period DESC",
            (entity_id,)
        )
        self.cbo_period.blockSignals(True)
        cur = self.cbo_period.currentText()
        self.cbo_period.clear()
        self.cbo_period.addItem("All Periods")
        for p in periods:
            self.cbo_period.addItem(p["period"])
        idx = self.cbo_period.findText(cur)
        if idx >= 0:
            self.cbo_period.setCurrentIndex(idx)
        self.cbo_period.blockSignals(False)

        self.tbl.setRowCount(0)
        total_debit = 0.0
        total_credit = 0.0
        for i, e in enumerate(entries):
            debit  = float(e.get("debit",0))
            credit = float(e.get("credit",0))
            total_debit  += debit
            total_credit += credit
            set_row(self.tbl, i, [
                e["date"][:10],
                e["account_code"],
                (e.get("description") or "")[:70],
                f"{debit:,.2f}"  if debit  else "",
                f"{credit:,.2f}" if credit else "",
                e.get("vat_code",""),
                e.get("source",""),
                e.get("period",""),
            ])

        diff = total_debit - total_credit
        colour = SUCCESS if abs(diff) < 0.01 else DANGER
        self.lbl_summary.setText(
            f"Entries: {len(entries)}    "
            f"Total Debit: £{total_debit:,.2f}    "
            f"Total Credit: £{total_credit:,.2f}    "
            f"Difference: £{diff:,.2f}"
        )
        self.lbl_summary.setStyleSheet(f"color:{colour}; font-size:12px; font-weight:bold;")


class TrialBalancePage(BasePage):
    def __init__(self):
        super().__init__("Trial Balance",
                         "Debit and credit balances by account — must agree before year-end")
        self._entity_map: dict = {}
        self._build()

    def _build(self):
        bar = QHBoxLayout()
        lbl = QLabel("Company:")
        lbl.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.cbo_entity = ComboField(["— select company —"])
        self.cbo_entity.setMinimumWidth(260)
        self.cbo_entity.currentIndexChanged.connect(self._load)
        self.cbo_period = ComboField(["All Periods"])
        self.cbo_period.setMinimumWidth(140)
        self.cbo_period.currentIndexChanged.connect(self._load)
        self.btn_refresh = SecondaryButton("⟳  Refresh")
        self.btn_refresh.clicked.connect(self._load)
        bar.addWidget(lbl)
        bar.addWidget(self.cbo_entity)
        bar.addWidget(QLabel("  Period:"))
        bar.addWidget(self.cbo_period)
        bar.addStretch()
        bar.addWidget(self.btn_refresh)
        self.layout_.addLayout(bar)

        self.lbl_agree = QLabel("")
        self.lbl_agree.setStyleSheet("font-size:14px; font-weight:bold;")
        self.layout_.addWidget(self.lbl_agree)

        tb_card = Card("Trial Balance")
        self.tbl = make_table(
            ["Code","Account","Type","Normal Bal.","Total Debit £","Total Credit £","Balance £"],
            stretch_col=1
        )
        self.tbl.setMinimumHeight(450)
        self.tbl.setColumnWidth(0, 70)
        self.tbl.setColumnWidth(2, 100)
        self.tbl.setColumnWidth(3, 90)
        self.tbl.setColumnWidth(4, 110)
        self.tbl.setColumnWidth(5, 110)
        self.tbl.setColumnWidth(6, 110)
        tb_card.body().addWidget(self.tbl)
        self.layout_.addWidget(tb_card)
        self.layout_.addStretch()
        self.refresh_entities()

    def refresh_entities(self):
        self.cbo_entity.blockSignals(True)
        self.cbo_entity.clear()
        self._entity_map = {}
        for e in EntityModel.list_all():
            self.cbo_entity.addItem(e["legal_name"])
            self._entity_map[e["legal_name"]] = e["entity_id"]
        if not self._entity_map:
            self.cbo_entity.addItem("— no companies yet —")
        self.cbo_entity.blockSignals(False)
        self._load()

    def _load(self):
        entity_id = self._entity_map.get(self.cbo_entity.currentText(),"")
        if not entity_id:
            return

        period = self.cbo_period.currentText()
        if period == "All Periods":
            period = None

        rows = GLModel.get_trial_balance(entity_id, period)

        self.tbl.setRowCount(0)
        total_dr = 0.0
        total_cr = 0.0
        for i, r in enumerate(rows):
            dr   = float(r.get("total_debit",0))
            cr   = float(r.get("total_credit",0))
            bal  = float(r.get("balance",0))
            total_dr += dr
            total_cr += cr
            set_row(self.tbl, i, [
                r["code"], r["name"], r["type"], r["normal_balance"],
                f"{dr:,.2f}", f"{cr:,.2f}",
                f"{bal:,.2f}",
            ])

        diff = total_dr - total_cr
        agrees = abs(diff) < 0.01
        if agrees:
            self.lbl_agree.setText(
                f"✓  Trial Balance agrees — Total Debit = Total Credit = £{total_dr:,.2f}"
            )
            self.lbl_agree.setStyleSheet(f"font-size:14px; font-weight:bold; color:{SUCCESS};")
        else:
            self.lbl_agree.setText(
                f"✗  Trial Balance does NOT agree — Difference: £{diff:,.2f}"
            )
            self.lbl_agree.setStyleSheet(f"font-size:14px; font-weight:bold; color:{DANGER};")
