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
    finished  = pyqtSignal(int, int, list)   # tx_count, alloc_count, warnings
    failed    = pyqtSignal(str)

    def __init__(self, entity_id, filepath):
        super().__init__()
        self.entity_id = entity_id
        self.filepath  = filepath

    def run(self):
        try:
            self.progress.emit("Parsing file…")
            rows, fmt, warnings = parse_file(self.filepath)
            if not rows:
                self.failed.emit("No transactions found in file.")
                return

            self.progress.emit(f"Found {len(rows)} rows ({fmt}). Staging…")
            batch_id = ImportModel.create_batch(
                self.entity_id,
                os.path.basename(self.filepath),
                fmt,
                len(rows)
            )
            staged = ImportModel.stage_transactions(self.entity_id, batch_id, rows)

            self.progress.emit(f"Running AI allocation on {staged} transactions…")
            engine = AllocationEngine(self.entity_id)
            engine.train()   # no-op if not enough history yet

            staged_txs = ImportModel.get_staged(self.entity_id)
            # Only allocate unallocated ones from this batch
            unallocated = [t for t in staged_txs if t.get("account_code") is None]
            allocs = engine.allocate_batch(unallocated)

            self.progress.emit("Done.")
            self.finished.emit(staged, len(allocs), warnings)
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
        self._build()

    def _build(self):
        # Entity + file selector
        sel_card = Card("Select Company and File")
        sel_body = sel_card.body()

        row1 = QHBoxLayout()
        lbl_e = QLabel("Company:")
        lbl_e.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.cbo_entity = ComboField(["— select company —"])
        self.cbo_entity.setMinimumWidth(280)
        row1.addWidget(lbl_e)
        row1.addWidget(self.cbo_entity)
        row1.addStretch()
        sel_body.addLayout(row1)

        row2 = QHBoxLayout()
        self.lbl_file = QLabel("No file selected")
        self.lbl_file.setStyleSheet(f"color:{MUTED}; font-size:13px;")
        self.btn_browse = SecondaryButton("Browse…")
        self.btn_browse.clicked.connect(self._browse)
        row2.addWidget(self.lbl_file)
        row2.addStretch()
        row2.addWidget(self.btn_browse)
        sel_body.addLayout(row2)

        # Supported formats note
        note = QLabel(
            "Supported formats: CSV (Barclays, HSBC, Lloyds, NatWest, Starling, Monzo, generic)  "
            "|  Excel .xlsx/.xls  |  PDF (table-based bank exports)"
        )
        note.setStyleSheet(f"color:{MUTED}; font-size:11px; font-style:italic;")
        note.setWordWrap(True)
        sel_body.addWidget(note)

        self.btn_import = PrimaryButton("Import and Run AI Allocation")
        self.btn_import.setEnabled(False)
        self.btn_import.clicked.connect(self._run_import)
        sel_body.addWidget(self.btn_import)

        self.layout_.addWidget(sel_card)

        # Progress
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

        # Recent imports
        hist_card = Card("Recent Imports")
        self.tbl_hist = make_table(
            ["Company", "Filename", "Type", "Rows", "Time", "Status"],
            stretch_col=1
        )
        self.tbl_hist.setFixedHeight(180)
        hist_card.body().addWidget(self.tbl_hist)
        self.layout_.addWidget(hist_card)

        # ── Manual entry — personal / cash payments ───────────────────────────
        manual_card = Card("Manual Entry — Personal Account / Cash Payment")
        mb = manual_card.body()

        note = QLabel(
            "Use this for business expenses paid from your personal bank account, "
            "credit card, or petty cash. They will be staged for AI allocation "
            "alongside your bank imports."
        )
        note.setStyleSheet(f"color:{MUTED}; font-size:12px; font-style:italic;")
        note.setWordWrap(True)
        mb.addWidget(note)

        # Company selector (separate from file import selector)
        row_e = QHBoxLayout()
        lbl_me = QLabel("Company:")
        lbl_me.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        self.cbo_manual_entity = ComboField(["— select company —"])
        self.cbo_manual_entity.setMinimumWidth(280)
        row_e.addWidget(lbl_me)
        row_e.addWidget(self.cbo_manual_entity)
        row_e.addStretch()
        mb.addLayout(row_e)

        # Entry fields
        self.f_m_date   = LineField(str(date.today()))
        self.f_m_amount = LineField("e.g. -45.00  (negative = expense, positive = income)")
        self.f_m_desc   = LineField("e.g. Stationery from Staples")
        self.f_m_payee  = LineField("e.g. Staples")
        self.f_m_source = ComboField([
            "Personal Account",
            "Personal Credit Card",
            "Petty Cash",
            "Cash",
            "Director Card",
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

        # Queue table
        self.tbl_manual = make_table(
            ["Date", "Amount", "Description", "Payee", "Source"], stretch_col=2
        )
        self.tbl_manual.setFixedHeight(160)
        mb.addWidget(self.tbl_manual)
        self._manual_queue = []   # list of dicts

        self.layout_.addWidget(manual_card)

        self.layout_.addStretch()
        self._selected_file = None
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

    def _browse(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, "Select Bank Statement",
            "", "Bank Statements (*.csv *.xlsx *.xls *.pdf);;All Files (*)"
        )
        if fp:
            self._selected_file = fp
            self.lbl_file.setText(os.path.basename(fp))
            self.lbl_file.setStyleSheet(f"color:{TEXT}; font-size:13px;")
            self._check_ready()

    def _check_ready(self):
        entity = self._entity_map.get(self.cbo_entity.currentText())
        self.btn_import.setEnabled(bool(entity and self._selected_file))

    def _run_import(self):
        entity_id = self._entity_map.get(self.cbo_entity.currentText())
        if not entity_id or not self._selected_file:
            return

        self.btn_import.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.lbl_progress.setText("Starting import…")

        self._worker = ImportWorker(entity_id, self._selected_file)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        self.lbl_progress.setText(msg)

    def _on_done(self, tx_count: int, alloc_count: int, warnings: list):
        self.progress_bar.setVisible(False)
        self.btn_import.setEnabled(True)
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
        date_val = self.f_m_date.text().strip()
        amount_str = self.f_m_amount.text().strip()
        desc = self.f_m_desc.text().strip()
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
            date_val,
            f"£{amount:,.2f}",
            desc,
            row["payee"],
            row["source"],
        ])
        # Clear entry fields for next row
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
                entity_id,
                f"Manual entry — {date.today()}",
                "MANUAL",
                len(self._manual_queue)
            )
            # Tag each row with its payment source in the description
            rows_to_stage = []
            for r in self._manual_queue:
                rows_to_stage.append({
                    "date":        r["date"],
                    "amount":      r["amount"],
                    "description": f"[{r['source']}] {r['description']}",
                    "payee":       r["payee"],
                })
            ImportModel.stage_transactions(entity_id, batch_id, rows_to_stage)

            # Run AI allocation
            from core.ai_engine import AllocationEngine
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
        from core.models import EntityModel
        batches = db.fetchall(
            """SELECT b.*, e.legal_name
               FROM import_batches b
               JOIN entities e ON e.entity_id = b.entity_id
               ORDER BY b.import_time DESC LIMIT 20"""
        )
        self.tbl_hist.setRowCount(0)
        for i, b in enumerate(batches):
            set_row(self.tbl_hist, i, [
                b.get("legal_name",""),
                b["filename"],
                b["file_type"],
                str(b["row_count"]),
                b["import_time"][:16],
                b["status"],
            ])
