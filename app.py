"""
fos/app.py
Application entry point.
Handles master password unlock, wires all pages into the main window.
"""

import sys
import logging
from pathlib import Path

# ── Ensure project root is on sys.path ──────────────────────────────────────
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import Qt

from core.database import db, DB_PATH
from ui.main_window import MainWindow
from ui.dialog_unlock import UnlockDialog
from ui.page_dashboard import DashboardPage
from ui.page_company import CompanyPage
from ui.page_coa import CoAPage
from ui.page_import import ImportPage
from ui.page_allocation import AllocationPage
from ui.page_gl import GLPage, TrialBalancePage

import os
_LOG_DIR = Path(os.environ.get("APPDATA", Path.home() / ".local" / "share")) / "FOS"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_LOG_DIR / "fos.log", encoding="utf-8")
    ]
)
log = logging.getLogger("fos.app")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("FOS")
    app.setOrganizationName("Network Logic Limited")

    # Default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # ── Dev mode: skip password, auto-open (delete corrupt db if needed) ─────
    DEV_MODE = True   # set False when ready for production password prompt
    DEV_PASSWORD = "devpass"   # sqlcipher requires at least 1 character
    if DEV_MODE:
        if DB_PATH.exists():
            try:
                db.open(DEV_PASSWORD)
            except Exception:
                # Existing db is corrupt or from a different session — delete it
                log.warning("Existing database unreadable — resetting for dev mode.")
                try:
                    DB_PATH.unlink()
                except Exception:
                    pass
                db.open(DEV_PASSWORD)
        else:
            db.open(DEV_PASSWORD)
        log.info("Dev mode: opened database without password prompt")
    else:
        is_new = not DB_PATH.exists()
        dlg = UnlockDialog(is_new_db=is_new)
        if dlg.exec() != UnlockDialog.DialogCode.Accepted:
            sys.exit(0)
        password = dlg.password()
        try:
            db.open(password)
        except Exception as exc:
            QMessageBox.critical(
                None, "Cannot Open Database",
                f"Failed to open the database.\n\n"
                f"If this is an existing database, check your password.\n\n"
                f"Error: {exc}"
            )
            sys.exit(1)
        log.info("Database opened successfully (new_db=%s)", is_new)

    # ── Main window ───────────────────────────────────────────────────────────
    win = MainWindow()

    # Instantiate pages
    dashboard   = DashboardPage(navigate_fn=win.navigate)
    company_pg  = CompanyPage()
    coa_pg      = CoAPage()
    import_pg   = ImportPage()
    alloc_pg    = AllocationPage()
    gl_pg       = GLPage()
    tb_pg       = TrialBalancePage()

    # Register pages
    win.add_page("dashboard",  dashboard)
    win.add_page("company",    company_pg)
    win.add_page("coa",        coa_pg)
    win.add_page("import",     import_pg)
    win.add_page("allocation", alloc_pg)
    win.add_page("gl",         gl_pg)
    win.add_page("tb",         tb_pg)

    import core.context as ctx

    # ── Pages that respond to global company change ───────────────────────────
    pages_with_entity = [coa_pg, import_pg, alloc_pg, gl_pg, tb_pg]

    def _sync_all(entity_id: str):
        for pg in pages_with_entity:
            pg.set_active_entity(entity_id)
        dashboard.refresh()

    ctx.register(_sync_all)

    # ── Cross-page wiring ─────────────────────────────────────────────────────

    def on_entity_created(entity_id: str):
        for pg in pages_with_entity:
            pg.refresh_entities()
        win.refresh_companies()
        dashboard.refresh()
        win.navigate("coa")

    def on_import_done():
        alloc_pg.refresh_entities()
        dashboard.refresh()
        win.navigate("allocation")

    def on_committed(entity_id: str):
        gl_pg.refresh_entities()
        tb_pg.refresh_entities()
        dashboard.refresh()

    company_pg.entity_created.connect(on_entity_created)
    import_pg.import_done.connect(on_import_done)
    alloc_pg.committed.connect(on_committed)

    # ── Initial load ──────────────────────────────────────────────────────────
    for pg in pages_with_entity:
        pg.refresh_entities()
    dashboard.refresh()
    win.refresh_companies()   # sets context → triggers _sync_all

    # ── Launch ────────────────────────────────────────────────────────────────
    win.navigate("dashboard")
    win.show()
    log.info("FOS started")

    code = app.exec()
    db.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
