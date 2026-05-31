"""
fos/ui/page_company.py
Company Profile page — list entities, create new, view detail.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QCheckBox, QGroupBox, QScrollArea, QFrame,
    QPushButton, QSplitter, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.widgets import (
    BasePage, Card, PrimaryButton, SecondaryButton,
    FormRow, LineField, ComboField, make_table, set_row,
    info, error, ACCENT, DARK, TEXT, MUTED, BORDER, WHITE, BG
)
from core.models import EntityModel


class CompanyPage(BasePage):
    entity_created = pyqtSignal(str)   # emits entity_id

    def __init__(self):
        super().__init__("Companies", "Manage business entities and company profiles")
        self._build()

    def _build(self):
        # Top action bar
        bar = QHBoxLayout()
        self.btn_new = PrimaryButton("+ New Company")
        self.btn_new.clicked.connect(self._show_form)
        bar.addWidget(self.btn_new)
        bar.addStretch()
        self.layout_.addLayout(bar)

        # Company list card
        list_card = Card("Registered Companies")
        self.tbl = make_table(
            ["Legal Name", "Trading Name", "Type", "FY Start", "FY End", "Status"], stretch_col=0
        )
        self.tbl.setFixedHeight(220)
        self.tbl.doubleClicked.connect(self._view_selected)
        list_card.body().addWidget(self.tbl)
        self.layout_.addWidget(list_card)

        # New company form (hidden until + New pressed)
        self.form_card = Card("New Company Profile")
        self.form_card.setVisible(False)
        self._build_form(self.form_card.body())
        self.layout_.addWidget(self.form_card)

        self.layout_.addStretch()
        self.refresh()

    # ── Form ─────────────────────────────────────────────────────────────────

    def _build_form(self, layout: QVBoxLayout):
        # ── Core identity ────────────────────────────────────────────────────
        grp1 = QGroupBox("Company Identity")
        grp1.setStyleSheet(self._grp_style())
        g1 = QVBoxLayout(grp1)

        self.f_legal      = LineField("e.g. Network Logic Limited")
        self.f_trading    = LineField("Leave blank if same as legal name")
        self.f_comp_no    = LineField("e.g. 12345678")
        self.f_type       = ComboField(["Limited Company","Sole Trader","Partnership","LLP"])
        _months = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"]
        self.f_fy_start   = ComboField(_months)
        self.f_fy_start.setCurrentText("April")   # UK default
        self.f_fy_end     = ComboField(_months)
        self.f_fy_end.setCurrentText("March")     # UK default

        for lbl, w in [
            ("Legal Name *",       self.f_legal),
            ("Trading Name",       self.f_trading),
            ("Company Number",     self.f_comp_no),
            ("Entity Type *",      self.f_type),
            ("FY Start Month *",   self.f_fy_start),
            ("FY End Month *",     self.f_fy_end),
        ]:
            g1.addLayout(FormRow(lbl, w))
        layout.addWidget(grp1)

        # ── Registered address ───────────────────────────────────────────────
        grp2 = QGroupBox("Registered Address")
        grp2.setStyleSheet(self._grp_style())
        g2 = QVBoxLayout(grp2)
        self.f_r_line1  = LineField("Address Line 1 *")
        self.f_r_line2  = LineField("Address Line 2")
        self.f_r_town   = LineField("Town / City *")
        self.f_r_county = LineField("County")
        self.f_r_pc     = LineField("Postcode *")
        for lbl, w in [
            ("Line 1 *",    self.f_r_line1),
            ("Line 2",      self.f_r_line2),
            ("Town *",      self.f_r_town),
            ("County",      self.f_r_county),
            ("Postcode *",  self.f_r_pc),
        ]:
            g2.addLayout(FormRow(lbl, w))
        layout.addWidget(grp2)

        # ── VAT ───────────────────────────────────────────────────────────────
        grp3 = QGroupBox("VAT Configuration")
        grp3.setStyleSheet(self._grp_style())
        g3 = QVBoxLayout(grp3)
        self.f_vat_reg    = QCheckBox("VAT Registered")
        self.f_vat_reg.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.f_vat_reg.toggled.connect(self._vat_toggled)
        g3.addWidget(self.f_vat_reg)
        self.f_vat_no     = LineField("GB + 9 digits")
        self.f_vat_scheme = ComboField(["Standard Accrual","Cash Accounting","Flat Rate"])
        self.f_vat_scheme.currentTextChanged.connect(self._scheme_changed)
        self.f_flat_rate  = LineField("e.g. 14.5")
        self.f_vat_qstart = ComboField([str(i) for i in range(1,13)])
        self.vat_fields = [
            ("VAT Number",           self.f_vat_no),
            ("VAT Scheme",           self.f_vat_scheme),
            ("Flat Rate %",          self.f_flat_rate),
            ("Quarter Start Month",  self.f_vat_qstart),
        ]
        self._vat_rows = []
        for lbl, w in self.vat_fields:
            row_w = QWidget()
            row_lay = QHBoxLayout(row_w)
            row_lay.setContentsMargins(0,0,0,0)
            row_lay.addLayout(FormRow(lbl, w))
            g3.addWidget(row_w)
            self._vat_rows.append(row_w)
        self._vat_toggled(False)
        layout.addWidget(grp3)

        # ── Bank accounts ─────────────────────────────────────────────────────
        grp4 = QGroupBox("Primary Bank Account (for CSV matching)")
        grp4.setStyleSheet(self._grp_style())
        g4 = QVBoxLayout(grp4)
        self.f_bk_name = LineField("e.g. Barclays Business Current")
        self.f_bk_sort = LineField("e.g. 20-00-00")
        self.f_bk_acc  = LineField("e.g. 12345678")
        for lbl, w in [
            ("Account Name",   self.f_bk_name),
            ("Sort Code",      self.f_bk_sort),
            ("Account Number", self.f_bk_acc),
        ]:
            g4.addLayout(FormRow(lbl, w))
        layout.addWidget(grp4)

        # ── Approval authority ────────────────────────────────────────────────
        grp5 = QGroupBox("Approval Authority")
        grp5.setStyleSheet(self._grp_style())
        g5 = QVBoxLayout(grp5)
        self.f_ap_name  = LineField("Full name *")
        self.f_ap_role  = LineField("e.g. Director, Sole Trader *")
        self.f_ap_email = LineField("Email (optional)")
        for lbl, w in [
            ("Name *",  self.f_ap_name),
            ("Role *",  self.f_ap_role),
            ("Email",   self.f_ap_email),
        ]:
            g5.addLayout(FormRow(lbl, w))
        layout.addWidget(grp5)

        # ── Actions ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.btn_save   = PrimaryButton("Save Company Profile")
        self.btn_cancel = SecondaryButton("Cancel")
        self.btn_save.clicked.connect(self._save)
        self.btn_cancel.clicked.connect(lambda: self.form_card.setVisible(False))
        btn_row.addStretch()
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_save)
        layout.addLayout(btn_row)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _show_form(self):
        self.form_card.setVisible(True)

    def _vat_toggled(self, checked: bool):
        for w in self._vat_rows:
            w.setVisible(checked)
        # Flat rate only visible when scheme = Flat Rate
        self._scheme_changed(self.f_vat_scheme.currentText())

    def _scheme_changed(self, scheme: str):
        if not self.f_vat_reg.isChecked():
            return
        self._vat_rows[2].setVisible(scheme == "Flat Rate")

    def _save(self):
        if not self.f_legal.text().strip():
            error(self, "Validation", "Legal name is required.")
            return
        if not self.f_fy_start.currentText() or not self.f_fy_end.currentText():
            error(self, "Validation", "Financial year start and end months are required.")
            return
        if not self.f_ap_name.text().strip() or not self.f_ap_role.text().strip():
            error(self, "Validation", "Approval authority name and role are required.")
            return

        try:
            entity_id = EntityModel.create(
                legal_name       = self.f_legal.text().strip(),
                trading_name     = self.f_trading.text().strip() or None,
                company_number   = self.f_comp_no.text().strip(),
                entity_type      = self.f_type.currentText(),
                fy_start         = self.f_fy_start.currentText(),
                fy_end           = self.f_fy_end.currentText(),
                reg_address      = dict(
                    line1    = self.f_r_line1.text().strip(),
                    line2    = self.f_r_line2.text().strip(),
                    town     = self.f_r_town.text().strip(),
                    county   = self.f_r_county.text().strip(),
                    postcode = self.f_r_pc.text().strip(),
                ),
                trading_address  = None,
                vat_registered   = self.f_vat_reg.isChecked(),
                vat_number       = self.f_vat_no.text().strip(),
                vat_scheme       = self.f_vat_scheme.currentText(),
                flat_rate_pct    = float(self.f_flat_rate.text() or 0) or None,
                quarter_start_month = int(self.f_vat_qstart.currentText()),
                banks            = [dict(
                    account_name   = self.f_bk_name.text().strip(),
                    sort_code      = self.f_bk_sort.text().strip(),
                    account_number = self.f_bk_acc.text().strip(),
                )],
                approver_name    = self.f_ap_name.text().strip(),
                approver_role    = self.f_ap_role.text().strip(),
                approver_email   = self.f_ap_email.text().strip(),
            )
            info(self, "Saved",
                 f"Company profile created.\nChart of Accounts loaded automatically.")
            self.form_card.setVisible(False)
            self._clear_form()
            self.refresh()
            self.entity_created.emit(entity_id)
        except Exception as exc:
            error(self, "Error", str(exc))

    def _clear_form(self):
        self.f_fy_start.setCurrentText("April")
        self.f_fy_end.setCurrentText("March")
        for w in [self.f_legal, self.f_trading, self.f_comp_no,
                  self.f_r_line1, self.f_r_line2, self.f_r_town,
                  self.f_r_county, self.f_r_pc,
                  self.f_vat_no, self.f_flat_rate,
                  self.f_bk_name, self.f_bk_sort, self.f_bk_acc,
                  self.f_ap_name, self.f_ap_role, self.f_ap_email]:
            w.clear()
        self.f_vat_reg.setChecked(False)

    def _view_selected(self):
        row = self.tbl.currentRow()
        if row < 0:
            return
        # Could open a detail dialog — placeholder for v2
        info(self, "Company Profile",
             f"Selected: {self.tbl.item(row,0).text()}\n\n"
             "Full detail view coming in next sprint.")

    def refresh(self):
        self.tbl.setRowCount(0)
        for i, e in enumerate(EntityModel.list_all()):
            set_row(self.tbl, i, [
                e["legal_name"],
                e.get("trading_name") or "",
                e["entity_type"],
                e.get("fy_start") or "",
                e.get("fy_end") or "",
                e["status"],
            ])

    @staticmethod
    def _grp_style():
        return (
            f"QGroupBox {{ font-size:13px; font-weight:bold; color:{DARK}; "
            f"border:1px solid {BORDER}; border-radius:6px; "
            f"margin-top:10px; padding:10px; background:white; }}"
            f"QGroupBox::title {{ subcontrol-origin:margin; left:10px; padding:0 4px; }}"
        )
