"""
fos/ui/page_allocation.py
Checkpoint 1 — Review AI allocations, confirm or override inline, commit to GL.
Account and VAT editable directly in the table row — no separate panel.
"""

from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QComboBox,
    QWidget, QFrame, QLineEdit, QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.widgets import (
    BasePage, Card, PrimaryButton, SecondaryButton,
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
VAT_CODES = ["SR-I", "SR-O", "ZR", "EX", "OS", "FRO"]


class _AccountPopup(QFrame):
    """Floating searchable account picker — appears near the clicked cell."""
    selected = pyqtSignal(str, str)   # code, name

    def __init__(self, coa_map: dict, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFixedWidth(360)
        self.setStyleSheet(
            f"QFrame {{ background:white; border:2px solid {ACCENT}; border-radius:6px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Type to filter — e.g. wages, fuel, meals…")
        self.search.setFixedHeight(32)
        self.search.setStyleSheet(
            f"border:1px solid {BORDER}; border-radius:4px; padding:0 8px; font-size:12px;"
        )
        lay.addWidget(self.search)

        self.lst = QListWidget()
        self.lst.setFixedHeight(200)
        self.lst.setStyleSheet(
            f"QListWidget {{ border:1px solid {BORDER}; border-radius:4px; "
            f"font-size:12px; background:white; color:{TEXT}; }}"
            f"QListWidget::item {{ padding:4px 6px; }}"
            f"QListWidget::item:selected {{ background:{ACCENT}; color:white; }}"
            f"QListWidget::item:hover {{ background:#EEF4FB; }}"
        )
        lay.addWidget(self.lst)

        self._coa_map = coa_map
        self._fill("")
        self.search.textChanged.connect(self._fill)
        self.lst.itemClicked.connect(self._pick)
        self.search.returnPressed.connect(self._pick_first)

    def _fill(self, text: str):
        text = text.lower().strip()
        self.lst.clear()
        for code, name in sorted(self._coa_map.items()):
            if not text or text in code.lower() or text in name.lower():
                item = QListWidgetItem(f"{code}  {name}")
                item.setData(Qt.ItemDataRole.UserRole, (code, name))
                self.lst.addItem(item)

    def _pick(self, item=None):
        if item is None:
            item = self.lst.currentItem()
        if item:
            code, name = item.data(Qt.ItemDataRole.UserRole)
            self.selected.emit(code, name)
            self.hide()

    def _pick_first(self):
        if self.lst.count():
            self.lst.setCurrentRow(0)
            self._pick()

    def show_near(self, gpos):
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._fill("")          # uses self._coa_map which is already updated by caller
        self.move(gpos)
        self.show()
        self.raise_()
        self.search.setFocus()


class AllocationPage(BasePage):
    committed = pyqtSignal(str)

    def __init__(self):
        super().__init__("AI Allocation Review",
                         "Click any row to edit account or VAT inline — then commit to GL")
        self._entity_map: dict = {}
        self._coa_map: dict = {}
        self._staged: list = []
        self._decisions: dict = {}
        self._active_row: int = -1
        self._popup = None
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        # Hidden entity combo — driven by global sidebar context
        self.cbo_entity = ComboField(["— select company —"])
        self.cbo_entity.setVisible(False)
        self.cbo_entity.currentIndexChanged.connect(self._load)

        top = QHBoxLayout()
        self.btn_rerun = PrimaryButton("🤖  Re-run AI Allocation")
        self.btn_rerun.clicked.connect(self._rerun_ai)
        self.btn_refresh = SecondaryButton("⟳  Refresh")
        self.btn_refresh.clicked.connect(self._load)
        top.addStretch()
        top.addWidget(self.btn_rerun)
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
            lay.setContentsMargins(14, 6, 14, 6)
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

        # Table card
        tbl_card = Card("Staged Transactions — click Account or VAT cell to edit inline")
        filter_row = QHBoxLayout()
        lbl_f = QLabel("Show:")
        lbl_f.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.cbo_filter = ComboField(
            ["All", "High Confidence", "Medium Confidence",
             "Low Confidence", "Unclassified", "Internal Transfers"]
        )
        self.cbo_filter.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(lbl_f)
        filter_row.addWidget(self.cbo_filter)
        filter_row.addStretch()
        hint = QLabel("💡 Click the Account or VAT cell to change it directly")
        hint.setStyleSheet(f"color:{MUTED}; font-size:11px; font-style:italic;")
        filter_row.addWidget(hint)
        tbl_card.body().addLayout(filter_row)

        self.tbl = make_table(
            ["Date", "Payee / Description", "Amount £",
             "Account  ✎", "VAT  ✎", "Confidence", "Flag"],
            stretch_col=1
        )
        self.tbl.setMinimumHeight(400)
        self.tbl.setColumnWidth(0, 90)
        self.tbl.setColumnWidth(2, 100)
        self.tbl.setColumnWidth(3, 200)
        self.tbl.setColumnWidth(4, 70)
        self.tbl.setColumnWidth(5, 110)
        self.tbl.setColumnWidth(6, 90)
        self.tbl.cellClicked.connect(self._cell_clicked)
        tbl_card.body().addWidget(self.tbl)
        self.layout_.addWidget(tbl_card)

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

        self.btn_commit = PrimaryButton("✓  Approve and Commit to GL", colour=SUCCESS)
        self.btn_commit.setEnabled(False)
        self.btn_commit.clicked.connect(self._commit)
        c_lay.addWidget(self.btn_commit)
        self.layout_.addWidget(commit_card)
        self.layout_.addStretch()

        self.refresh_entities()

    # ── Inline cell editing ───────────────────────────────────────────────────

    def _cell_clicked(self, row: int, col: int):
        date_item = self.tbl.item(row, 0)
        if not date_item:
            return
        tx_id = date_item.data(Qt.ItemDataRole.UserRole)
        if not tx_id:
            return

        if col == 3:   # Account cell → searchable popup
            self._active_row = row
            self._active_tx_id = tx_id
            if self._popup is None:
                self._popup = _AccountPopup(self._coa_map, self)
                self._popup.selected.connect(self._on_account_selected)
            # Always refresh the map — a new dict may have been assigned since creation
            self._popup._coa_map = self._coa_map
            rect = self.tbl.visualItemRect(self.tbl.item(row, col))
            gpos = self.tbl.viewport().mapToGlobal(rect.bottomLeft())
            self._popup.show_near(gpos)

        elif col == 4:  # VAT cell → inline combo widget
            self._active_tx_id = tx_id
            existing = self.tbl.cellWidget(row, 4)
            if existing:
                return
            vat_cbo = QComboBox()
            vat_cbo.addItems(VAT_CODES)
            dec = self._decisions.get(tx_id, {})
            idx = vat_cbo.findText(dec.get("vat_code", "SR-I"))
            if idx >= 0:
                vat_cbo.setCurrentIndex(idx)
            vat_cbo.setStyleSheet(
                f"QComboBox {{ border:1px solid {ACCENT}; border-radius:3px; "
                f"font-size:12px; background:white; color:{TEXT}; }}"
                f"QComboBox QAbstractItemView {{ background:white; color:{TEXT}; "
                f"selection-background-color:{ACCENT}; selection-color:white; }}"
            )
            vat_cbo.currentTextChanged.connect(
                lambda val, r=row, t=tx_id: self._on_vat_changed(r, t, val)
            )
            self.tbl.setCellWidget(row, 4, vat_cbo)

    def _on_account_selected(self, code: str, name: str):
        row = self._active_row
        tx_id = self._active_tx_id
        if tx_id not in self._decisions:
            return
        self._decisions[tx_id].update({
            "account_code": code,
            "override": True,
        })
        # Update cell text directly
        item = self.tbl.item(row, 3)
        if item:
            item.setText(f"{code}  {name}")
        # Mark flag column
        flag_item = self.tbl.item(row, 6)
        if flag_item:
            flag_item.setText("✏️ Edited")

    def _on_vat_changed(self, row: int, tx_id: str, vat_code: str):
        if tx_id in self._decisions:
            self._decisions[tx_id].update({
                "vat_code": vat_code,
                "override": True,
            })
            flag_item = self.tbl.item(row, 6)
            if flag_item:
                flag_item.setText("✏️ Edited")

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

    def _rerun_ai(self):
        entity_id = self._current_entity_id()
        if not entity_id:
            return
        from core.ai_engine import AllocationEngine
        try:
            self.btn_rerun.setEnabled(False)
            self.btn_rerun.setText("🤖  Running…")
            engine = AllocationEngine(entity_id)
            engine.train()
            staged = ImportModel.get_staged(entity_id)
            if not staged:
                info(self, "Nothing to do", "No staged transactions to allocate.")
                return
            engine.allocate_batch(staged)
            self._load()
            info(self, "Done", f"AI re-allocation complete — {len(staged)} transactions updated.")
        except Exception as exc:
            error(self, "Error", str(exc))
        finally:
            self.btn_rerun.setEnabled(True)
            self.btn_rerun.setText("🤖  Re-run AI Allocation")

    def _load(self):
        entity_id = self._current_entity_id()
        if not entity_id:
            return

        coa_rows = CoAModel.get_for_entity(entity_id)
        self._coa_map = {r["code"]: r["name"] for r in coa_rows}

        self._staged = ImportModel.get_staged(entity_id)
        self._decisions = {}
        for tx in self._staged:
            self._decisions[tx["tx_id"]] = {
                "tx_id":           tx["tx_id"],
                "account_code":    tx.get("account_code") or "5620",
                "vat_code":        tx.get("vat_code") or "SR-I",
                "override":        bool(tx.get("override")),
                "override_reason": "",
            }

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
        for tx in self._staged:
            score = float(tx.get("confidence") or 0)
            band, _, _ = confidence_band(score)
            dec = self._decisions.get(tx["tx_id"], {})
            acc_code = dec.get("account_code", "")
            is_transfer = acc_code == "9000"

            if f == "Internal Transfers" and not is_transfer:
                continue
            elif f != "All" and f != "Internal Transfers" and f.lower() not in band.lower():
                continue

            acc_name = self._coa_map.get(acc_code, acc_code)
            amt = float(tx.get("amount", 0))
            amt_str = f"£{amt:,.2f}" if amt >= 0 else f"-£{abs(amt):,.2f}"

            # Flag column
            if is_transfer:
                flag = "🔄 Transfer"
                row_fill = "#EAF0FB"
            elif dec.get("override"):
                flag = "✏️ Edited"
                row_fill = "#FFF8E1"
            else:
                flag = ""
                row_fill = BAND_BG.get(band, WHITE)

            row_idx = self.tbl.rowCount()
            set_row(self.tbl, row_idx, [
                tx.get("date", "")[:10],
                (tx.get("payee") or tx.get("description") or "")[:80],
                amt_str,
                f"{acc_code}  {acc_name}",
                dec.get("vat_code", ""),
                f"{score:.0f}% ({band})",
                flag,
            ], row_colour=row_fill)
            self.tbl.item(row_idx, 0).setData(Qt.ItemDataRole.UserRole, tx["tx_id"])
            self._active_tx_id = None

    def _update_summary(self):
        counts = {"High": 0, "Medium": 0, "Low": 0, "Unclassified": 0}
        for tx in self._staged:
            score = float(tx.get("confidence") or 0)
            band, _, _ = confidence_band(score)
            counts[band] = counts.get(band, 0) + 1
        for band, cnt in counts.items():
            if band in self._band_labels:
                self._band_labels[band].setText(str(cnt))

    # ── Commit ────────────────────────────────────────────────────────────────

    def _commit(self):
        entity_id = self._current_entity_id()
        if not entity_id:
            return
        if not self._decisions:
            error(self, "Nothing to commit", "No staged transactions.")
            return
        approver = self.f_approver.text().strip()
        if not approver:
            error(self, "Approver required", "Enter the approver name before committing.")
            return

        n = len(self._decisions)
        if not confirm(self, "Confirm Commit",
                       f"Commit {n} transactions to the General Ledger?\n\n"
                       "This cannot be undone."):
            return
        try:
            from datetime import datetime
            period = datetime.utcnow().strftime("%Y-%m")
            if " — " in approver:
                name, role = approver.split(" — ", 1)
            else:
                name, role = approver, "Director"
            ImportModel.approve_and_post(
                entity_id=entity_id,
                tx_decisions=list(self._decisions.values()),
                approver_name=name.strip(),
                approver_role=role.strip(),
                period=period,
            )
            info(self, "Committed",
                 f"✓  {n} transactions posted to the General Ledger.")
            self.committed.emit(entity_id)
            self._load()
        except Exception as exc:
            error(self, "Commit Failed", str(exc))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _current_entity_id(self) -> str:
        import core.context as ctx
        eid = ctx.get_entity_id()
        return eid or self._entity_map.get(self.cbo_entity.currentText(), "")

    def set_active_entity(self, entity_id: str) -> None:
        for name, eid in self._entity_map.items():
            if eid == entity_id:
                self.cbo_entity.blockSignals(True)
                self.cbo_entity.setCurrentText(name)
                self.cbo_entity.blockSignals(False)
                break
        self._load()
