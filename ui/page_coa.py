"""
fos/ui/page_coa.py
Chart of Accounts viewer — per-entity, filterable by type.
Add accounts, import from CSV/Excel.
"""

from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QComboBox,
    QFileDialog, QWidget
)
from PyQt6.QtCore import Qt

from ui.widgets import (
    BasePage, Card, PrimaryButton, SecondaryButton,
    ComboField, make_table, set_row,
    info, error, ACCENT, DARK, TEXT, MUTED, WHITE, BG
)
from core.models import EntityModel, CoAModel
from core.file_parser import parse_file

TYPE_COLOURS = {
    "Asset":    "#EBF5FB",
    "Liability":"#FDEDEC",
    "Equity":   "#F5EEF8",
    "Income":   "#EAFAF1",
    "CoS":      "#FEF9E7",
    "Overhead": "#FDF2E9",
    "Tax":      "#F2F3F4",
}


class CoAPage(BasePage):
    def __init__(self):
        super().__init__("Chart of Accounts",
                         "View and manage ledger accounts for each company")
        self._entity_map: dict = {}
        self._build()

    def _build(self):
        # Selector bar
        bar = QHBoxLayout()
        lbl = QLabel("Company:")
        lbl.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.cbo_entity = ComboField(["— select company —"])
        self.cbo_entity.setMinimumWidth(280)
        self.cbo_entity.currentIndexChanged.connect(self._load_coa)

        lbl_type = QLabel("  Filter:")
        lbl_type.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.cbo_type = ComboField(
            ["All Types","Asset","Liability","Equity",
             "Income","CoS","Overhead","Tax"]
        )
        self.cbo_type.currentIndexChanged.connect(self._load_coa)

        self.btn_import = SecondaryButton("Import CoA (CSV/Excel)")
        self.btn_import.clicked.connect(self._import_coa)
        self.btn_add    = PrimaryButton("+ Add Account")
        self.btn_add.clicked.connect(self._add_account)

        bar.addWidget(lbl)
        bar.addWidget(self.cbo_entity)
        bar.addWidget(lbl_type)
        bar.addWidget(self.cbo_type)
        bar.addStretch()
        bar.addWidget(self.btn_import)
        bar.addWidget(self.btn_add)
        self.layout_.addLayout(bar)

        # Summary row
        self.summary_card = Card("Account Summary")
        self._summary_row = QHBoxLayout()
        self.summary_card.body().addLayout(self._summary_row)
        self.layout_.addWidget(self.summary_card)

        # CoA table
        coa_card = Card("Accounts")
        self.tbl = make_table(
            ["Code","Account Name","Type","Normal Bal.","VAT","VAT Rate","Locked","Active"],
            stretch_col=1
        )
        self.tbl.setMinimumHeight(400)
        coa_card.body().addWidget(self.tbl)
        self.layout_.addWidget(coa_card)

        self.layout_.addStretch()

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh_entities(self):
        self.cbo_entity.blockSignals(True)
        self.cbo_entity.clear()
        self._entity_map = {}
        entities = EntityModel.list_all()
        if not entities:
            self.cbo_entity.addItem("— no companies yet —")
        else:
            self.cbo_entity.addItem("— select company —")
            for e in entities:
                display = e["legal_name"]
                self.cbo_entity.addItem(display)
                self._entity_map[display] = e["entity_id"]
        self.cbo_entity.blockSignals(False)
        self._load_coa()

    def _load_coa(self):
        self.tbl.setRowCount(0)
        entity_id = self._current_entity_id()
        if not entity_id:
            return

        type_filter = self.cbo_type.currentText()
        rows = CoAModel.get_for_entity(entity_id, active_only=False)
        if type_filter != "All Types":
            rows = [r for r in rows if r["type"] == type_filter]

        # Summary counts
        while self._summary_row.count():
            item = self._summary_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        type_counts: dict = {}
        for r in CoAModel.get_for_entity(entity_id, active_only=False):
            type_counts[r["type"]] = type_counts.get(r["type"], 0) + 1

        for t, cnt in sorted(type_counts.items()):
            badge = QLabel(f"  {t}: {cnt}  ")
            badge.setStyleSheet(
                f"background:{TYPE_COLOURS.get(t,'#F4F4F4')}; "
                f"color:{DARK}; border-radius:4px; font-size:12px; "
                f"border:1px solid #D0D8E0; padding:2px 0;"
            )
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._summary_row.addWidget(badge)
        self._summary_row.addStretch()

        # Populate table
        for i, r in enumerate(rows):
            fill = TYPE_COLOURS.get(r["type"], "#FFFFFF")
            locked = "🔒" if r["system_locked"] else ""
            active  = "✓" if r["active"] else "—"
            vat_rate = f"{r['vat_rate']:.0f}%" if r["vat_rate"] is not None else ""
            set_row(self.tbl, i, [
                r["code"], r["name"], r["type"],
                r["normal_balance"], r["vat_applicable"],
                vat_rate, locked, active
            ], row_colour=fill if i % 2 == 0 else None)

    # ── Import CoA ────────────────────────────────────────────────────────────

    def _import_coa(self):
        entity_id = self._current_entity_id()
        if not entity_id:
            error(self, "Select Company", "Please select a company first.")
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Chart of Accounts",
            "", "Spreadsheets (*.csv *.xlsx *.xls)"
        )
        if not filepath:
            return

        try:
            rows, fmt, warnings = parse_file(filepath)
            # rows here are transaction-format — re-parse for CoA
            # CoA CSV expected: code, name, type, normal_balance, vat_applicable, vat_rate
            imported, skipped, errs = CoAModel.import_from_rows(entity_id, rows)
            msg = (f"Import complete ({fmt})\n\n"
                   f"Imported: {imported}\nSkipped (duplicate/blank): {skipped}")
            if warnings:
                msg += f"\n\nWarnings:\n" + "\n".join(warnings[:5])
            if errs:
                msg += f"\n\nErrors:\n" + "\n".join(errs[:5])
            info(self, "Import Result", msg)
            self._load_coa()
        except Exception as exc:
            error(self, "Import Failed", str(exc))

    # ── Add account (inline quick-add) ────────────────────────────────────────

    def _add_account(self):
        entity_id = self._current_entity_id()
        if not entity_id:
            error(self, "Select Company", "Please select a company first.")
            return

        from PyQt6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Account")
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet(f"background:{WHITE};")
        lay = QVBoxLayout(dlg)
        lay.setSpacing(10)
        lay.setContentsMargins(20, 20, 20, 20)

        from ui.widgets import FormRow, LineField, ComboField as CF
        f_code = LineField("e.g. 5635")
        f_name = LineField("Account name")
        f_type = CF(["Asset","Liability","Equity","Income","CoS","Overhead","Tax"])
        f_nb   = CF(["Debit","Credit"])
        f_vat  = CF(["No","Yes","Exempt"])
        f_vr   = LineField("e.g. 20")

        for lbl, w in [
            ("Code *",          f_code),
            ("Name *",          f_name),
            ("Type *",          f_type),
            ("Normal Balance",  f_nb),
            ("VAT Applicable",  f_vat),
            ("VAT Rate %",      f_vr),
        ]:
            lay.addLayout(FormRow(lbl, w))

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            code = f_code.text().strip()
            name = f_name.text().strip()
            if not code or not name:
                error(self, "Validation", "Code and name are required.")
                return
            try:
                vr = float(f_vr.text()) if f_vr.text().strip() else None
                CoAModel.add_account(
                    entity_id, code, name,
                    f_type.currentText(),
                    f_nb.currentText(),
                    f_vat.currentText(),
                    vr
                )
                self._load_coa()
            except Exception as exc:
                error(self, "Error", str(exc))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _current_entity_id(self) -> str:
        text = self.cbo_entity.currentText()
        return self._entity_map.get(text, "")
