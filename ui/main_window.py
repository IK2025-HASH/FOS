"""
fos/ui/main_window.py
Main application shell — navigation sidebar + stacked content area.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QStackedWidget, QLabel, QFrame, QComboBox
)
from PyQt6.QtCore import Qt

NAV_W  = 200
ACCENT = "#2E6DA4"
DARK   = "#1B3A5C"
BG     = "#F4F7FB"
WHITE  = "#FFFFFF"
TEXT   = "#2C3E50"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FOS — Multi-Company Accounting System")
        self.setMinimumSize(1200, 750)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────────────────────
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(NAV_W)
        self.sidebar.setStyleSheet(f"background:{DARK};")
        sb_layout = QVBoxLayout(self.sidebar)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        # Logo area
        logo = QLabel("FOS")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedHeight(70)
        logo.setStyleSheet(
            f"color:white; font-size:28px; font-weight:bold;"
            f"background:{ACCENT}; letter-spacing:4px;"
        )
        sb_layout.addWidget(logo)

        subtitle = QLabel("Accounting System")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setFixedHeight(30)
        subtitle.setStyleSheet("color:#90B4D4; font-size:10px; background:#16314F;")
        sb_layout.addWidget(subtitle)

        # Active company picker
        co_frame = QFrame()
        co_frame.setStyleSheet(f"background:#16314F; border-bottom:1px solid #0F2438;")
        co_lay = QVBoxLayout(co_frame)
        co_lay.setContentsMargins(10, 8, 10, 8)
        co_lay.setSpacing(3)
        lbl_co = QLabel("Working on:")
        lbl_co.setStyleSheet("color:#90B4D4; font-size:10px; background:transparent; border:none;")
        self.cbo_active_company = QComboBox()
        self.cbo_active_company.setStyleSheet(
            "QComboBox { background:#0F2438; color:white; border:1px solid #2E6DA4; "
            "border-radius:4px; padding:4px 8px; font-size:12px; font-weight:bold; }"
            "QComboBox::drop-down { border:none; }"
            "QComboBox QAbstractItemView { background:#1B3A5C; color:white; "
            "selection-background-color:#2E6DA4; border:1px solid #2E6DA4; }"
        )
        self.cbo_active_company.setFixedHeight(32)
        co_lay.addWidget(lbl_co)
        co_lay.addWidget(self.cbo_active_company)
        sb_layout.addWidget(co_frame)

        spacer_top = QWidget()
        spacer_top.setFixedHeight(8)
        spacer_top.setStyleSheet(f"background:{DARK};")
        sb_layout.addWidget(spacer_top)

        # Nav buttons
        self._nav_buttons = {}
        nav_items = [
            ("dashboard",  "🏠  Dashboard"),
            ("company",    "🏢  Companies"),
            ("coa",        "📋  Chart of Accounts"),
            ("import",     "📥  Import Transactions"),
            ("allocation", "🤖  AI Allocation"),
            ("gl",         "📒  General Ledger"),
            ("tb",         "⚖️   Trial Balance"),
            ("reports",    "📄  Period Report"),
            ("datatools",  "🔧  Data Tools"),
        ]
        for key, label in nav_items:
            btn = self._make_nav_btn(label, key)
            self._nav_buttons[key] = btn
            sb_layout.addWidget(btn)

        sb_layout.addStretch()

        self.lbl_version = QLabel("v1.1")
        self.lbl_version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_version.setFixedHeight(28)
        self.lbl_version.setStyleSheet("color:#506070; font-size:9px; background:#16314F;")
        sb_layout.addWidget(self.lbl_version)

        import core.settings as _s
        self.lbl_app_mode = QLabel("🟢 TESTING" if _s.is_testing() else "🔴 LIVE")
        self.lbl_app_mode.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_app_mode.setFixedHeight(24)
        self.lbl_app_mode.setStyleSheet(
            "color:#A8D5A2; font-size:9px; font-weight:bold; background:#16314F;"
            if _s.is_testing() else
            "color:#F5A9A9; font-size:9px; font-weight:bold; background:#16314F;"
        )
        sb_layout.addWidget(self.lbl_app_mode)

        root.addWidget(self.sidebar)

        # ── Content area ─────────────────────────────────────────────────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background:{BG};")
        root.addWidget(self.stack)

        # Pages are injected by app.py after construction
        self._pages: dict = {}
        self._company_map: dict = {}
        self.cbo_active_company.currentIndexChanged.connect(self._on_company_changed)

    def add_page(self, key: str, widget: QWidget) -> None:
        self._pages[key] = widget
        self.stack.addWidget(widget)

    def refresh_companies(self) -> None:
        from core.models import EntityModel
        import core.context as ctx
        self.cbo_active_company.blockSignals(True)
        self.cbo_active_company.clear()
        self._company_map = {}
        for e in EntityModel.list_all():
            self.cbo_active_company.addItem(e["legal_name"])
            self._company_map[e["legal_name"]] = e["entity_id"]
        if not self._company_map:
            self.cbo_active_company.addItem("— add a company first —")
        # Restore previously selected entity if still available
        cur = ctx.get_entity_name()
        idx = self.cbo_active_company.findText(cur)
        if idx >= 0:
            self.cbo_active_company.setCurrentIndex(idx)
        self.cbo_active_company.blockSignals(False)
        self._on_company_changed()

    def _on_company_changed(self) -> None:
        import core.context as ctx
        name = self.cbo_active_company.currentText()
        eid  = self._company_map.get(name, "")
        ctx.set_entity(eid, name)
        self.lbl_version.setText(f"v1.1 · {name[:20]}" if eid else "v1.1")

    def navigate(self, key: str) -> None:
        if key in self._pages:
            self.stack.setCurrentWidget(self._pages[key])
            for k, btn in self._nav_buttons.items():
                active = k == key
                btn.setStyleSheet(self._btn_style(active))

    def _make_nav_btn(self, label: str, key: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedHeight(46)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(self._btn_style(False))
        btn.clicked.connect(lambda _, k=key: self.navigate(k))
        return btn

    @staticmethod
    def _btn_style(active: bool) -> str:
        bg  = ACCENT if active else "transparent"
        fg  = "white"
        lft = f"border-left: 3px solid {'white' if active else 'transparent'};"
        return (
            f"QPushButton {{ background:{bg}; color:{fg}; "
            f"border:none; {lft} text-align:left; "
            f"padding:0 18px; font-size:13px; }}"
            f"QPushButton:hover {{ background:{'#3A7EC4' if not active else ACCENT}; }}"
        )
