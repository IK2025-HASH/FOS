"""
fos/ui/dialog_unlock.py
Master password dialog — first run (set password) or subsequent opens (enter password).
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

DARK   = "#1B3A5C"
ACCENT = "#2E6DA4"
BG     = "#F4F7FB"
WHITE  = "#FFFFFF"
DANGER = "#C0392B"
BORDER = "#D5E8F7"
MUTED  = "#7F8C8D"


class UnlockDialog(QDialog):
    def __init__(self, is_new_db: bool):
        super().__init__()
        self.is_new_db = is_new_db
        self.setWindowTitle("FOS — Unlock")
        self.setFixedSize(420, 360)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(f"background:{BG};")
        self._password = ""
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 30, 40, 30)
        lay.setSpacing(16)

        # Logo
        logo = QLabel("FOS")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(
            f"font-size:36px; font-weight:bold; color:{DARK}; letter-spacing:4px;"
        )
        lay.addWidget(logo)

        title = QLabel(
            "Create Master Password" if self.is_new_db
            else "Enter Master Password"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size:16px; font-weight:bold; color:{DARK};")
        lay.addWidget(title)

        sub = QLabel(
            "Choose a strong password. There is no recovery mechanism.\n"
            "If you lose this password, the database cannot be opened."
            if self.is_new_db else
            "Enter the password to unlock your accounting database."
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size:11px; color:{MUTED};")
        lay.addWidget(sub)

        # Password field
        self.f_pw = QLineEdit()
        self.f_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.f_pw.setPlaceholderText("Master password")
        self.f_pw.setFixedHeight(40)
        self.f_pw.setStyleSheet(
            f"border:1px solid {BORDER}; border-radius:6px; "
            f"padding:0 14px; font-size:14px; background:white;"
        )
        self.f_pw.returnPressed.connect(self._accept)
        lay.addWidget(self.f_pw)

        # Confirm field (new db only)
        self.f_pw2 = QLineEdit()
        self.f_pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.f_pw2.setPlaceholderText("Confirm password")
        self.f_pw2.setFixedHeight(40)
        self.f_pw2.setStyleSheet(
            f"border:1px solid {BORDER}; border-radius:6px; "
            f"padding:0 14px; font-size:14px; background:white;"
        )
        self.f_pw2.returnPressed.connect(self._accept)
        self.f_pw2.setVisible(self.is_new_db)
        lay.addWidget(self.f_pw2)

        # Error label
        self.lbl_err = QLabel("")
        self.lbl_err.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_err.setStyleSheet(f"color:{DANGER}; font-size:12px;")
        lay.addWidget(self.lbl_err)

        # Unlock button
        btn = QPushButton(
            "Create Database" if self.is_new_db else "Unlock"
        )
        btn.setFixedHeight(44)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:white; border:none; "
            f"border-radius:6px; font-size:14px; font-weight:bold; }}"
            f"QPushButton:hover {{ background:#1C5A8A; }}"
        )
        btn.clicked.connect(self._accept)
        lay.addWidget(btn)

    def _accept(self):
        pw = self.f_pw.text()
        if not pw:
            self.lbl_err.setText("Password cannot be empty.")
            return
        if len(pw) < 8:
            self.lbl_err.setText("Password must be at least 8 characters.")
            return
        if self.is_new_db:
            pw2 = self.f_pw2.text()
            if pw != pw2:
                self.lbl_err.setText("Passwords do not match.")
                return
        self._password = pw
        self.accept()

    def password(self) -> str:
        return self._password
