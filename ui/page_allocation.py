"""
fos/ui/page_allocation.py
Checkpoint 1 — Review AI allocations, confirm or override, commit to GL.
"""

from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QComboBox,
    QWidget, QFrame, QScrollArea, QSpacerItem,
    QSizePolicy, QGroupBox, QLineEdit, QListWidget,
    QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ui.widgets import (
    BasePage, Card, PrimaryButton, SecondaryButton, StatusBadge,
    ComboField, make_table, set_row,
    info, error, confirm,
    ACCENT, DARK, TEXT, MUTED, WHITE, BG, SUCCESS, WARN, DANGER, BORDER, PURPLE
)
from core.models import EntityModel, ImportModel, CoAModel
from core.ai_engine import confidence_band

BAND_BG = {
    "High":         "#E8F5EE",
    "Medium":       "#FEF3E2",
    "Low":          "#FDECEA",
    "Unclassified": "#F0EAF9",
}
BAND_FG = {
    "High":         "#27AE60",
    "Medium":       "#E67E22",
    "Low":          "#C0392B",
    "Unclassified": "#8E44AD",
}


class AllocationPage(BasePage):
    committed = pyqtSignal(str)   # emits entity_id after GL post

    def __init__(self):
        super().__init__("AI Allocation Review",
                         "Review AI-suggested account allocations — confirm, override, then commit to GL")
        self._entity_map: dict = {}
        self._coa_map: dict = {}       # code → name
        self._staged: list = []
        self._decisions: dict = {}     # tx_id → {account_code, vat_code, override}
        self._build()

    def _build(self):
        # Entity selector + stats bar
        top = QHBoxLayout()
        lbl = QLabel("Company:")
        lbl.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.cbo_entity = ComboField(["— select company —"])
        self.cbo_entity.setMinimumWidth(280)
        self.cbo_entity.currentIndexChanged.connect(self._load)

        self.btn_refresh = SecondaryButton("⟳  Refresh")
        self.btn_refresh.clicked.connect(self._load)

        top.addWidget(lbl)
        top.addWidget(self.cbo_entity)
        top.addStretch()
        top.addWidget(self.btn_refresh)
        self.layout_.addLayout(top)

        # Confidence summary cards
        self.summary_row = QHBoxLayout()
        self._band_labels = {}
        for band in ["High", "Medium", "Low", "Unclassified"]:
            card = QFrame()
            card.setFixedHeight(72)
            card.setStyleSheet(
                f"QFrame {{ background:{BAND_BG[band]}; border-radius:8px; "
                f"border:2px solid {BAND_FG[band]}; }}"
            )
            lay = QVBoxLayout(card)
            lay.setContentsMargins(14,6,14,6)
            lay.setSpacing(2)
            cnt = QLabel("0")
            cnt.setStyleSheet(f"font-size:22px; font-weight:bold; color:{BAND_FG[band]};")
            lbl2 = QLabel(band)
            lbl2.setStyleSheet(f"font-size:11px; color:{BAND_FG[band]};")
            lay.addWidget(cnt)
            lay.addWidget(lbl2)
            self._band_labels[band] = cnt
            self.summary_row.addWidget(card)
        self.layout_.addLayout(self.summary_row)

        # Main transaction table
        tbl_card = Card("Staged Transactions — AI Allocations")

        filter_row = QHBoxLayout()
        lbl_f = QLabel("Show:")
        lbl_f.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.cbo_filter = ComboField(["All", "High Confidence", "Medium Confidence",
                                       "Low Confidence", "Unclassified"])
        self.cbo_filter.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(lbl_f)
        filter_row.addWidget(self.cbo_filter)
        filter_row.addStretch()
        tbl_card.body().addLayout(filter_row)

        self.tbl = make_table(
            ["Date", "Payee / Description", "Amount £",
             "AI Account", "VAT", "Confidence", "Override"],
            stretch_col=1
        )
        self.tbl.setMinimumHeight(360)
        self.tbl.setColumnWidth(0, 90)
        self.tbl.setColumnWidth(2, 100)
        self.tbl.setColumnWidth(5, 100)
        self.tbl.setColumnWidth(6, 90)
        tbl_card.body().addWidget(self.tbl)
        self.layout_.addWidget(tbl_card)

        # Override panel (shown when low-confidence row selected)
        self.override_card = Card("Override Allocation")
        self.override_card.setVisible(False)
        self._build_override_panel(self.override_card.body())
        self.layout_.addWidget(self.override_card)

        # Commit bar
        commit_card = Card("Commit to General Ledger")
        c_lay = commit_card.body()
        note = QLabel(
            "Committing posts all approved allocations to the GL. "
            "This action cannot be undone — use journal corrections for any errors after commit."
        )
        note.setStyleSheet(f"color:{MUTED}; font-size:12px;")
        note.setWordWrap(True)
        c_lay.addWidget(note)

        approver_row = QHBoxLayout()
        lbl_ap = QLabel("Approver name:")
        lbl_ap.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        lbl_ap.setFixedWidth(140)
        self.f_approver = QLineEdit()
        self.f_approver.setPlaceholderText("Pulled from company profile — override if needed")
        self.f_approver.setFixedHeight(34)
        self.f_approver.setStyleSheet(
            f"border:1px solid {BORDER}; border-radius:4px; padding:0 10px; font-size:13px;"
        )
        approver_row.addWidget(lbl_ap)
        approver_row.addWidget(self.f_approver)
        c_lay.addLayout(approver_row)

        self.btn_commit = PrimaryButton("✓  Approve and Commit to GL",
                                        colour=SUCCESS)
        self.btn_commit.setEnabled(False)
        self.btn_commit.clicked.connect(self._commit)
        c_lay.addWidget(self.btn_commit)

        self.layout_.addWidget(commit_card)
        self.layout_.addStretch()

        self.tbl.itemSelectionChanged.connect(self._row_selected)
        self.refresh_entities()

    def _build_override_panel(self, layout: QVBoxLayout):
        layout.setSpacing(8)
        lbl = QLabel("Selected transaction — change allocation:")
        lbl.setStyleSheet(f"color:{DARK}; font-size:13px; font-weight:bold;")
        layout.addWidget(lbl)

        row = QHBoxLayout()
        lbl_acc = QLabel("Account:")
        lbl_acc.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        lbl_acc.setFixedWidth(80)

        acc_col = QVBoxLayout()
        acc_col.setSpacing(2)
        self.f_acc_search = QLineEdit()
        self.f_acc_search.setPlaceholderText("Type to search — e.g. fuel, meals, charity…")
        self.f_acc_search.setFixedHeight(34)
        self.f_acc_search.setStyleSheet(
            f"border:1px solid {BORDER}; border-radius:4px; padding:0 10px; font-size:13px;"
        )
        self.f_acc_search.textChanged.connect(self._filter_accounts)

        self.lst_acc = QListWidget()
        self.lst_acc.setFixedHeight(130)
        self.lst_acc.setStyleSheet(
            f"QListWidget {{ border:1px solid {BORDER}; border-radius:4px; "
            f"font-size:13px; background:white; color:{TEXT}; }}"
            f"QListWidget::item:selected {{ background:{ACCENT}; color:white; }}"
        )
        self.lst_acc.itemClicked.connect(self._acc_selected)
        acc_col.addWidget(self.f_acc_search)
        acc_col.addWidget(self.lst_acc)

        lbl_vat = QLabel("   VAT:")
        lbl_vat.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.cbo_override_vat = ComboField(
            ["SR-I","SR-O","ZR","EX","OS","FRO"], width=100
        )
        row.addWidget(lbl_acc)
        row.addLayout(acc_col)
        row.addWidget(lbl_vat)
        row.addWidget(self.cbo_override_vat)
        row.addStretch()
        layout.addLayout(row)

        self._override_acc_code = None

        reason_row = QHBoxLayout()
        lbl_r = QLabel("Reason:")
        lbl_r.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        lbl_r.setFixedWidth(80)
        self.f_reason = QLineEdit()
        self.f_reason.setPlaceholderText("Optional — why did you change this?")
        self.f_reason.setFixedHeight(34)
        self.f_reason.setStyleSheet(
            f"border:1px solid {BORDER}; border-radius:4px; padding:0 10px; font-size:13px;"
        )
        reason_row.addWidget(lbl_r)
        reason_row.addWidget(self.f_reason)
        layout.addLayout(reason_row)

        save_row = QHBoxLayout()
        self.btn_save_override = PrimaryButton("Apply Override", colour=WARN)
        self.btn_save_override.clicked.connect(self._save_override)
        save_row.addStretch()
        save_row.addWidget(self.btn_save_override)
        layout.addLayout(save_row)

        self._override_tx_id = None

    # ── Load data ─────────────────────────────────────────────────────────────

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
        entity_id = self._current_entity_id()
        if not entity_id:
            return

        # Load CoA for override dropdown
        coa_rows = CoAModel.get_for_entity(entity_id)
        self._coa_map = {r["code"]: r["name"] for r in coa_rows}

        # Load staged
        self._staged = ImportModel.get_staged(entity_id)

        # Build decisions dict (default = AI allocation)
        self._decisions = {}
        for tx in self._staged:
            self._decisions[tx["tx_id"]] = {
                "tx_id":          tx["tx_id"],
                "account_code":   tx.get("account_code") or "5620",
                "vat_code":       tx.get("vat_code") or "SR-I",
                "override":       bool(tx.get("override")),
                "override_reason":"",
            }

        # Prefill approver from profile
        e = EntityModel.get(entity_id)
        if e and e.get("approver"):
            ap = e["approver"]
            self.f_approver.setText(f"{ap['name']} — {ap['role']}")

        self._update_summary()
        self._apply_filter()
        self.btn_commit.setEnabled(len(self._staged) > 0)

    def _apply_filter(self):
        f = self.cbo_filter.currentText()
        self.tbl.setRowCount(0)
        for i, tx in enumerate(self._staged):
            score = float(tx.get("confidence") or 0)
            band, colour, _ = confidence_band(score)
            if f != "All" and f.lower() not in band.lower():
                continue
            dec = self._decisions.get(tx["tx_id"], {})
            acc_code = dec.get("account_code","")
            acc_name = self._coa_map.get(acc_code, acc_code)
            amt = float(tx.get("amount",0))
            amt_str = f"£{amt:,.2f}" if amt >= 0 else f"-£{abs(amt):,.2f}"
            override_str = "✏️ Override" if dec.get("override") else ""

            row_fill = BAND_BG.get(band, WHITE)
            set_row(self.tbl, self.tbl.rowCount(), [
                tx.get("date","")[:10],
                (tx.get("payee") or tx.get("description") or "")[:80],
                amt_str,
                f"{acc_code}  {acc_name}",
                dec.get("vat_code",""),
                f"{score:.0f}% ({band})",
                override_str,
            ], row_colour=row_fill)
            # Store tx_id in item user data
            self.tbl.item(self.tbl.rowCount()-1, 0).setData(
                Qt.ItemDataRole.UserRole, tx["tx_id"]
            )

    def _update_summary(self):
        counts = {"High": 0, "Medium": 0, "Low": 0, "Unclassified": 0}
        for tx in self._staged:
            score = float(tx.get("confidence") or 0)
            band, _, _ = confidence_band(score)
            counts[band] = counts.get(band, 0) + 1
        for band, cnt in counts.items():
            if band in self._band_labels:
                self._band_labels[band].setText(str(cnt))

    # ── Override ──────────────────────────────────────────────────────────────

    def _row_selected(self):
        rows = self.tbl.selectedItems()
        if not rows:
            self.override_card.setVisible(False)
            return
        row_idx = self.tbl.currentRow()
        date_item = self.tbl.item(row_idx, 0)
        if not date_item:
            return
        tx_id = date_item.data(Qt.ItemDataRole.UserRole)
        if not tx_id:
            return
        self._override_tx_id = tx_id
        dec = self._decisions.get(tx_id, {})

        # Populate search list and pre-select current allocation
        self._override_acc_code = dec.get("account_code")
        self._filter_accounts("")
        self.lst_acc.setVisible(True)
        acc_name = self._coa_map.get(self._override_acc_code, "")
        self.f_acc_search.setText(f"{self._override_acc_code}  {acc_name}" if acc_name else "")
        for i in range(self.lst_acc.count()):
            if self.lst_acc.item(i).data(Qt.ItemDataRole.UserRole) == self._override_acc_code:
                self.lst_acc.setCurrentRow(i)
                break
        vat_idx = self.cbo_override_vat.findText(dec.get("vat_code","SR-I"))
        if vat_idx >= 0:
            self.cbo_override_vat.setCurrentIndex(vat_idx)
        self.f_reason.clear()
        self.override_card.setVisible(True)

    def _filter_accounts(self, text: str):
        text = text.lower().strip()
        self.lst_acc.clear()
        for code, name in sorted(self._coa_map.items()):
            if not text or text in code.lower() or text in name.lower():
                item = QListWidgetItem(f"{code}  {name}")
                item.setData(Qt.ItemDataRole.UserRole, code)
                self.lst_acc.addItem(item)

    def _acc_selected(self, item):
        self._override_acc_code = item.data(Qt.ItemDataRole.UserRole)
        self.f_acc_search.setText(item.text())
        self.lst_acc.setVisible(False)

    def _save_override(self):
        if not self._override_tx_id:
            return
        acc_code = self._override_acc_code
        if not acc_code:
            # fall back to whatever is highlighted in list
            items = self.lst_acc.selectedItems()
            if items:
                acc_code = items[0].data(Qt.ItemDataRole.UserRole)
        if not acc_code:
            error(self, "No account selected", "Please select an account from the list.")
            return
        vat_code = self.cbo_override_vat.currentText()
        reason   = self.f_reason.text().strip()

        self._decisions[self._override_tx_id].update({
            "account_code":   acc_code,
            "vat_code":       vat_code,
            "override":       True,
            "override_reason": reason,
        })
        self._apply_filter()   # refresh table to show override marker

    # ── Commit to GL ──────────────────────────────────────────────────────────

    def _commit(self):
        entity_id = self._current_entity_id()
        if not entity_id:
            return

        if not self._decisions:
            error(self, "Nothing to commit", "No staged transactions.")
            return

        approver = self.f_approver.text().strip()
        if not approver:
            error(self, "Approver required",
                  "Enter the approver name before committing.")
            return

        n = len(self._decisions)
        if not confirm(self, "Confirm Commit",
                       f"Commit {n} transactions to the General Ledger?\n\n"
                       "This cannot be undone. "
                       "Corrections after this point require journal entries."):
            return

        try:
            from datetime import datetime
            period = datetime.utcnow().strftime("%Y-%m")
            # Parse name / role
            if " — " in approver:
                name, role = approver.split(" — ", 1)
            else:
                name, role = approver, "Director"

            ImportModel.approve_and_post(
                entity_id     = entity_id,
                tx_decisions  = list(self._decisions.values()),
                approver_name = name.strip(),
                approver_role = role.strip(),
                period        = period,
            )
            info(self, "Committed",
                 f"✓  {n} transactions posted to the General Ledger.\n\n"
                 "Approval record saved with document hash.")
            self.override_card.setVisible(False)
            self.committed.emit(entity_id)
            self._load()
        except Exception as exc:
            error(self, "Commit Failed", str(exc))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _current_entity_id(self) -> str:
        return self._entity_map.get(self.cbo_entity.currentText(), "")
