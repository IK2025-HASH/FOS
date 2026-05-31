"""
fos/ui/widgets.py
Shared UI components used across all pages.
"""

from PyQt6.QtWidgets import (
    QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QComboBox, QCheckBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QDialog, QDialogButtonBox, QTextEdit, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

# ── Palette ──────────────────────────────────────────────────────────────────
ACCENT  = "#2E6DA4"
DARK    = "#1B3A5C"
BG      = "#F4F7FB"
WHITE   = "#FFFFFF"
TEXT    = "#2C3E50"
MUTED   = "#7F8C8D"
SUCCESS = "#27AE60"
WARN    = "#E67E22"
DANGER  = "#E74C3C"
PURPLE  = "#8E44AD"
BORDER  = "#D5E8F7"

BAND_COLOURS = {
    "High":          ("#E8F5EE", "#27AE60"),
    "Medium":        ("#FEF3E2", "#E67E22"),
    "Low":           ("#FDECEA", "#E74C3C"),
    "Unclassified":  ("#F0EAF9", "#8E44AD"),
}

# ── Base page ────────────────────────────────────────────────────────────────

class BasePage(QWidget):
    """Every screen inherits from this."""

    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Page header
        hdr = QFrame()
        hdr.setFixedHeight(72)
        hdr.setStyleSheet(f"background:{WHITE}; border-bottom:2px solid {BORDER};")
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(28, 10, 28, 10)
        hdr_lay.setSpacing(2)

        t = QLabel(title)
        t.setStyleSheet(f"font-size:20px; font-weight:bold; color:{DARK};")
        hdr_lay.addWidget(t)

        if subtitle:
            s = QLabel(subtitle)
            s.setStyleSheet(f"font-size:12px; color:{MUTED};")
            hdr_lay.addWidget(s)

        outer.addWidget(hdr)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background:{BG};")

        self.content = QWidget()
        self.content.setStyleSheet(f"background:{BG};")
        self.layout_ = QVBoxLayout(self.content)
        self.layout_.setContentsMargins(28, 20, 28, 20)
        self.layout_.setSpacing(16)

        scroll.setWidget(self.content)
        outer.addWidget(scroll)


# ── Card ─────────────────────────────────────────────────────────────────────

class Card(QFrame):
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background:{WHITE}; border-radius:8px; "
            f"border:1px solid {BORDER}; }}"
        )
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(20, 16, 20, 16)
        self._outer.setSpacing(12)

        if title:
            lbl = QLabel(title)
            lbl.setStyleSheet(
                f"font-size:14px; font-weight:bold; color:{DARK}; "
                f"border:none; padding-bottom:6px; "
                f"border-bottom:1px solid {BORDER};"
            )
            self._outer.addWidget(lbl)

    def body(self) -> QVBoxLayout:
        return self._outer


# ── Primary button ────────────────────────────────────────────────────────────

def PrimaryButton(label: str, colour: str = ACCENT) -> QPushButton:
    btn = QPushButton(label)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedHeight(36)
    btn.setStyleSheet(
        f"QPushButton {{ background:{colour}; color:white; border:none; "
        f"border-radius:4px; padding:0 20px; font-size:13px; font-weight:bold; }}"
        f"QPushButton:hover {{ background:#1C5A8A; }}"
        f"QPushButton:disabled {{ background:#B0BEC5; }}"
    )
    return btn


def SecondaryButton(label: str) -> QPushButton:
    btn = QPushButton(label)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedHeight(36)
    btn.setStyleSheet(
        f"QPushButton {{ background:white; color:{ACCENT}; "
        f"border:2px solid {ACCENT}; border-radius:4px; "
        f"padding:0 20px; font-size:13px; }}"
        f"QPushButton:hover {{ background:{BG}; }}"
    )
    return btn


# ── Form field helpers ────────────────────────────────────────────────────────

def FormRow(label_text: str, widget: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    lbl = QLabel(label_text)
    lbl.setFixedWidth(200)
    lbl.setStyleSheet(f"color:{TEXT}; font-size:13px;")
    row.addWidget(lbl)
    row.addWidget(widget)
    return row


def LineField(placeholder: str = "", width: int = 0) -> QLineEdit:
    f = QLineEdit()
    f.setPlaceholderText(placeholder)
    f.setFixedHeight(34)
    if width:
        f.setFixedWidth(width)
    f.setStyleSheet(
        f"QLineEdit {{ border:1px solid {BORDER}; border-radius:4px; "
        f"padding:0 10px; font-size:13px; background:white; color:{TEXT}; }}"
        f"QLineEdit:focus {{ border:1px solid {ACCENT}; }}"
    )
    return f


def ComboField(options: list, width: int = 0) -> QComboBox:
    c = QComboBox()
    c.addItems(options)
    if width:
        c.setFixedWidth(width)
    c.setFixedHeight(34)
    c.setStyleSheet(
        f"QComboBox {{ border:1px solid {BORDER}; border-radius:4px; "
        f"padding:0 10px; font-size:13px; background:white; color:{TEXT}; }}"
        f"QComboBox:focus {{ border:1px solid {ACCENT}; }}"
    )
    return c


# ── Status badge ──────────────────────────────────────────────────────────────

def StatusBadge(text: str, bg: str, fg: str = "white") -> QLabel:
    lbl = QLabel(f"  {text}  ")
    lbl.setStyleSheet(
        f"background:{bg}; color:{fg}; border-radius:10px; "
        f"font-size:11px; font-weight:bold; padding:2px 0;"
    )
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setFixedHeight(20)
    return lbl


# ── Styled table ─────────────────────────────────────────────────────────────

def make_table(headers: list, stretch_col: int = -1) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.setShowGrid(False)
    t.setStyleSheet(
        f"QTableWidget {{ border:1px solid {BORDER}; border-radius:6px; "
        f"background:white; alternate-background-color:#F8FBFF; font-size:13px; }}"
        f"QHeaderView::section {{ background:{DARK}; color:white; "
        f"font-weight:bold; font-size:12px; padding:6px; border:none; }}"
        f"QTableWidget::item {{ padding:4px 8px; }}"
        f"QTableWidget::item:selected {{ background:{ACCENT}; color:white; }}"
    )
    hdr = t.horizontalHeader()
    if stretch_col >= 0:
        hdr.setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)
    return t


def set_row(table: QTableWidget, row: int, values: list,
            row_colour: str = None) -> None:
    table.setRowCount(max(table.rowCount(), row + 1))
    for col, val in enumerate(values):
        item = QTableWidgetItem(str(val))
        item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        if row_colour:
            item.setBackground(QColor(row_colour))
        table.setItem(row, col, item)


# ── Simple confirm dialog ─────────────────────────────────────────────────────

def confirm(parent, title: str, message: str) -> bool:
    dlg = QMessageBox(parent)
    dlg.setWindowTitle(title)
    dlg.setText(message)
    dlg.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    dlg.setDefaultButton(QMessageBox.StandardButton.No)
    return dlg.exec() == QMessageBox.StandardButton.Yes


def info(parent, title: str, message: str) -> None:
    QMessageBox.information(parent, title, message)


def error(parent, title: str, message: str) -> None:
    QMessageBox.critical(parent, title, message)
