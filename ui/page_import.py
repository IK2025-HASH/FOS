"""
fos/ui/page_import.py
Import bank statement files (CSV / Excel / PDF) and run AI allocation.
"""

import os
from datetime import date
from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QFileDialog,
    QProgressBar, QWidget, QPushButton
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from ui.widgets import (
    BasePage, Card, PrimaryButton, SecondaryButton,
    ComboField, LineField, FormRow, make_table, set_row,
    info, error, ACCENT, DARK, TEXT, MUTED, WHITE, BG, SUCCESS, WARN, DANGER
)
from core.models import EntityModel, ImportModel
from core.file_parser import parse_file
from core.ai_engine import AllocationEngine, confidence_band


# ── Background worker ─────────────────────────────────────────────────────────

class ImportWorker(QThread):
    progress  = pyqtSignal(str)
    finished  = pyqtSignal(int, int, list)
    failed    = pyqtSignal(str)

    def __init__(self, entity_id, filepaths, bank_name):
        super().__init__()
        self.entity_id  = entity_id
        self.filepaths  = filepaths   # list of file paths
        self.bank_name  = bank_name

    def run(self):
        try:
            total_staged = 0
            total_allocs = 0
            all_warnings = []

            for fp in self.filepaths:
                fname = os.path.basename(fp)
                self.progress.emit(f"Parsing {fname}…")
                rows, fmt, warnings = parse_file(fp)
                if not rows:
                    all_warnings.append(f"{fname}: no transactions found")
                    continue

                # Tag bank name into description prefix if provided
                if self.bank_name:
                    for r in rows:
                        r["description"] = f"[{self.bank_name}] {r.get('description','')}"

                self.progress.emit(f"{fname}: {len(rows)} rows found. Staging…")
                batch_id = ImportModel.create_batch(
                    self.entity_id, fname, fmt, len(rows)
                )
                staged = ImportModel.stage_transactions(self.entity_id, batch_id, rows)
                total_staged += staged
                all_warnings.extend(warnings)

            self.progress.emit(f"Running AI allocation on {total_staged} transactions…")
            engine = AllocationEngine(self.entity_id)
            engine.train()
            staged_txs = ImportModel.get_staged(self.entity_id)
            unallocated = [t for t in staged_txs if t.get("account_code") is None]
            allocs = engine.allocate_batch(unallocated)
            total_allocs = len(allocs)

            self.progress.emit("Done.")
            self.finished.emit(total_staged, total_allocs, all_warnings)
        except Exception as exc:
            self.failed.emit(str(exc))


# ── Page ──────────────────────────────────────────────────────────────────────

class ImportPage(BasePage):
    import_done = pyqtSignal()

    def __init__(self):
        super().__init__("Import Transactions",
                         "Load CSV, Excel, or PDF bank statements")
        self._entity_map: dict = {}
        self._worker = None
        self._selected_files = []
        self._build()

    def _build(self):
        # ── File import card ──────────────────────────────────────────────────
        sel_card = Card("Select Company and Files")
        sel_body = sel_card.body()

        # Company selector
        row1 = QHBoxLayout()
        lbl_e = QLabel("Company:")
        lbl_e.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.cbo_entity = ComboField(["— select company —"])
        self.cbo_entity.setMinimumWidth(280)
        self.cbo_entity.currentIndexChanged.connect(self._on_entity_changed)
        row1.addWidget(lbl_e)
        row1.addWidget(self.cbo_entity)
        row1.addStretch()
        sel_body.addLayout(row1)

        # Bank account — editable so any name can be typed freely
        row_bank = QHBoxLayout()
        lbl_bank = QLabel("Bank Account:")
        lbl_bank.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.cbo_bank = ComboField(["— select company first —"])
        self.cbo_bank.setEditable(True)
        self.cbo_bank.setMinimumWidth(280)
        self.cbo_bank.setPlaceholderText("Type or select bank name (e.g. Wise, Revolut…)")
        tip = QLabel("Type any bank name — registered banks shown as suggestions")
        tip.setStyleSheet(f"color:{MUTED}; font-size:11px; font-style:italic;")
        row_bank.addWidget(lbl_bank)
        row_bank.addWidget(self.cbo_bank)
        row_bank.addStretch()
        sel_body.addLayout(row_bank)
        sel_body.addWidget(tip)

        # File picker
        row2 = QHBoxLayout()
        self.lbl_files = QLabel("No files selected")
        self.lbl_files.setStyleSheet(f"color:{MUTED}; font-size:13px;")
        self.btn_browse = SecondaryButton("Browse…")
        self.btn_browse.clicked.connect(self._browse)
        row2.addWidget(self.lbl_files)
        row2.addStretch()
        row2.addWidget(self.btn_browse)
        sel_body.addLayout(row2)

        note = QLabel(
            "Supported formats: CSV (Barclays, HSBC, Lloyds, NatWest, Starling, Monzo, generic)  "
            "|  Excel .xlsx/.xls  |  PDF (table-based bank exports)  —  You can select multiple files at once."
        )
        note.setStyleSheet(f"color:{MUTED}; font-size:11px; font-style:italic;")
        note.setWordWrap(True)
        sel_body.addWidget(note)

        self.btn_import = PrimaryButton("Import and Run AI Allocation")
        self.btn_import.setEnabled(False)
        self.btn_import.clicked.connect(self._run_import)
        sel_body.addWidget(self.btn_import)

        self.layout_.addWidget(sel_card)

        # ── Progress card ─────────────────────────────────────────────────────
        prog_card = Card("Import Progress")
        self.lbl_progress = QLabel("Ready.")
        self.lbl_progress.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ border:1px solid #D0D8E0; border-radius:4px; height:8px; }}"
            f"QProgressBar::chunk {{ background:{ACCENT}; border-radius:4px; }}"
        )
        prog_card.body().addWidget(self.lbl_progress)
        prog_card.body().addWidget(self.progress_bar)
        self.layout_.addWidget(prog_card)

        # ── Recent imports ────────────────────────────────────────────────────
        hist_card = Card("Recent Imports")
        self.tbl_hist = make_table(
            ["Company", "Filename", "Type", "Rows", "Time", "Status"],
            stretch_col=1
        )
        self.tbl_hist.setFixedHeight(180)
        hist_card.body().addWidget(self.tbl_hist)
        self.layout_.addWidget(hist_card)

        # ── Manual entry card ─────────────────────────────────────────────────
        manual_card = Card("Manual Entry — Personal Account / Cash Payment")
        mb = manual_card.body()

        note2 = QLabel(
            "Use this for business expenses paid from your personal bank account, "
            "credit card, or petty cash. They will be staged for AI allocation "
            "alongside your bank imports."
        )
        note2.setStyleSheet(f"color:{MUTED}; font-size:12px; font-style:italic;")
        note2.setWordWrap(True)
        mb.addWidget(note2)

        row_e = QHBoxLayout()
        lbl_me = QLabel("Company:")
        lbl_me.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.cbo_manual_entity = ComboField(["— select company —"])
        self.cbo_manual_entity.setMinimumWidth(280)
        row_e.addWidget(lbl_me)
        row_e.addWidget(self.cbo_manual_entity)
        row_e.addStretch()
        mb.addLayout(row_e)

        self.f_m_date   = LineField(str(date.today()))
        self.f_m_amount = LineField("e.g. -45.00  (negative = expense, positive = income)")
        self.f_m_desc   = LineField("e.g. Stationery from Staples")
        self.f_m_payee  = LineField("e.g. Staples")
        self.f_m_source = ComboField([
            "Personal Account", "Personal Credit Card",
            "Petty Cash", "Cash", "Director Card",
        ])

        for lbl, w in [
            ("Date *",           self.f_m_date),
            ("Amount (£) *",     self.f_m_amount),
            ("Description *",    self.f_m_desc),
            ("Payee",            self.f_m_payee),
            ("Payment Source *", self.f_m_source),
        ]:
            mb.addLayout(FormRow(lbl, w))

        btn_row = QHBoxLayout()
        self.btn_add_manual = SecondaryButton("+ Add to Queue")
        self.btn_add_manual.clicked.connect(self._add_manual_row)
        self.btn_submit_manual = PrimaryButton("Submit Queue for AI Allocation")
        self.btn_submit_manual.clicked.connect(self._submit_manual)
        self.btn_submit_manual.setEnabled(False)
        btn_row.addWidget(self.btn_add_manual)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_submit_manual)
        mb.addLayout(btn_row)

        self.tbl_manual = make_table(
            ["Date", "Amount", "Description", "Payee", "Source"], stretch_col=2
        )
        self.tbl_manual.setFixedHeight(160)
        mb.addWidget(self.tbl_manual)
        self._manual_queue = []

        self.layout_.addWidget(manual_card)
        self.layout_.addStretch()
        self.refresh_entities()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def refresh_entities(self):
        self._entity_map = {}
        entities = EntityModel.list_all()
        for cbo in (self.cbo_entity, self.cbo_manual_entity):
            cbo.blockSignals(True)
            cbo.clear()
            if not entities:
                cbo.addItem("— no companies yet —")
            else:
                cbo.addItem("— select company —")
                for e in entities:
                    cbo.addItem(e["legal_name"])
                    self._entity_map[e["legal_name"]] = e["entity_id"]
            cbo.blockSignals(False)

    def _on_entity_changed(self):
        entity_id = self._entity_map.get(self.cbo_entity.currentText())
        self.cbo_bank.blockSignals(True)
        self.cbo_bank.clear()
        if entity_id:
            from core.database import db
            banks = db.fetchall(
                "SELECT account_name FROM entity_banks WHERE entity_id=? ORDER BY is_primary DESC",
                (entity_id,)
            )
            for b in banks:
                self.cbo_bank.addItem(b["account_name"])
        self.cbo_bank.setCurrentText("")   # clear so user types or picks
        self.cbo_bank.blockSignals(False)
        self._check_ready()

    def _browse(self):
        fps, _ = QFileDialog.getOpenFileNames(
            self, "Select Bank Statements",
            "", "Bank Statements (*.csv *.xlsx *.xls *.pdf);;All Files (*)"
        )
        if fps:
            self._selected_files = fps
            if len(fps) == 1:
                self.lbl_files.setText(os.path.basename(fps[0]))
            else:
                self.lbl_files.setText(f"{len(fps)} files selected")
            self.lbl_files.setStyleSheet(f"color:{TEXT}; font-size:13px;")
            self._check_ready()

    def _check_ready(self):
        entity = self._entity_map.get(self.cbo_entity.currentText())
        self.btn_import.setEnabled(bool(entity and self._selected_files))

    def _run_import(self):
        entity_id = self._entity_map.get(self.cbo_entity.currentText())
        if not entity_id or not self._selected_files:
            return

        bank_name = self.cbo_bank.currentText().strip()

        self.btn_import.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.lbl_progress.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.lbl_progress.setText("Starting import…")

        self._worker = ImportWorker(entity_id, self._selected_files, bank_name)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        self.lbl_progress.setText(msg)

    def _on_done(self, tx_count: int, alloc_count: int, warnings: list):
        self.progress_bar.setVisible(False)
        self.btn_import.setEnabled(True)
        self._selected_files = []
        self.lbl_files.setText("No files selected")
        self.lbl_files.setStyleSheet(f"color:{MUTED}; font-size:13px;")
        msg = f"✓  Import complete — {tx_count} transactions staged, {alloc_count} AI allocations made."
        if warnings:
            msg += f"  ({len(warnings)} warnings)"
        self.lbl_progress.setText(msg)
        self.lbl_progress.setStyleSheet(f"color:{SUCCESS}; font-size:13px; font-weight:bold;")
        self._load_history()
        self.import_done.emit()

    def _on_error(self, msg: str):
        self.progress_bar.setVisible(False)
        self.btn_import.setEnabled(True)
        self.lbl_progress.setText(f"✗  {msg}")
        self.lbl_progress.setStyleSheet(f"color:{DANGER}; font-size:13px;")

    def _add_manual_row(self):
        date_val   = self.f_m_date.text().strip()
        amount_str = self.f_m_amount.text().strip()
        desc       = self.f_m_desc.text().strip()
        if not date_val or not amount_str or not desc:
            error(self, "Validation", "Date, Amount and Description are required.")
            return
        try:
            amount = float(amount_str.replace(",", "").replace("£", ""))
        except ValueError:
            error(self, "Validation", "Amount must be a number, e.g. -45.00")
            return

        row = {
            "date":        date_val,
            "amount":      amount,
            "description": desc,
            "payee":       self.f_m_payee.text().strip(),
            "source":      self.f_m_source.currentText(),
        }
        self._manual_queue.append(row)
        i = self.tbl_manual.rowCount()
        set_row(self.tbl_manual, i, [
            date_val, f"£{amount:,.2f}", desc, row["payee"], row["source"]
        ])
        self.f_m_amount.clear()
        self.f_m_desc.clear()
        self.f_m_payee.clear()
        self.btn_submit_manual.setEnabled(True)

    def _submit_manual(self):
        entity_id = self._entity_map.get(self.cbo_manual_entity.currentText())
        if not entity_id:
            error(self, "Validation", "Please select a company.")
            return
        if not self._manual_queue:
            return
        try:
            batch_id = ImportModel.create_batch(
                entity_id, f"Manual entry — {date.today()}", "MANUAL",
                len(self._manual_queue)
            )
            rows_to_stage = [{
                "date":        r["date"],
                "amount":      r["amount"],
                "description": f"[{r['source']}] {r['description']}",
                "payee":       r["payee"],
            } for r in self._manual_queue]
            ImportModel.stage_transactions(entity_id, batch_id, rows_to_stage)

            engine = AllocationEngine(entity_id)
            engine.train()
            staged_txs = ImportModel.get_staged(entity_id)
            unallocated = [t for t in staged_txs if t.get("account_code") is None]
            engine.allocate_batch(unallocated)

            count = len(self._manual_queue)
            self._manual_queue.clear()
            self.tbl_manual.setRowCount(0)
            self.btn_submit_manual.setEnabled(False)
            self._load_history()
            info(self, "Submitted",
                 f"{count} manual transaction(s) staged for review.\n\n"
                 "Go to AI Allocation to review and approve.")
            self.import_done.emit()
        except Exception as exc:
            error(self, "Error", str(exc))

    def _load_history(self):
        from core.database import db
        batches = db.fetchall(
            """SELECT b.*, e.legal_name
               FROM import_batches b
               JOIN entities e ON e.entity_id = b.entity_id
               ORDER BY b.import_time DESC LIMIT 20"""
        )
        self.tbl_hist.setRowCount(0)
        for i, b in enumerate(batches):
            set_row(self.tbl_hist, i, [
                b.get("legal_name", ""),
                b["filename"],
                b["file_type"],
                str(b["row_count"]),
                b["import_time"][:16],
                b["status"],
            ])
