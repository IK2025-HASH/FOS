"""
fos/ui/main_window.py
Main application shell — navigation sidebar + stacked content area.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QStackedWidget, QLabel, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QColor, QPalette

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

        spacer_top = QWidget()
        spacer_top.setFixedHeight(16)
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
        ]
        for key, label in nav_items:
            btn = self._make_nav_btn(label, key)
            self._nav_buttons[key] = btn
            sb_layout.addWidget(btn)

        sb_layout.addStretch()

        version = QLabel("v1.1 · Network Logic")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setFixedHeight(36)
        version.setStyleSheet("color:#506070; font-size:9px; background:#16314F;")
        sb_layout.addWidget(version)

        root.addWidget(self.sidebar)

        # ── Content area ─────────────────────────────────────────────────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background:{BG};")
        root.addWidget(self.stack)

        # Pages are injected by app.py after construction
        self._pages: dict = {}

    def add_page(self, key: str, widget: QWidget) -> None:
        self._pages[key] = widget
        self.stack.addWidget(widget)

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
