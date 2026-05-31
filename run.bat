@echo off
REM ═══════════════════════════════════════════════════════════════════════════
REM  FOS — Multi-Company Accounting System
REM  Setup and Build Script for Windows
REM
REM  First time:  double-click this file or run from command prompt
REM  Thereafter:  run FOS.exe from the dist\ folder
REM ═══════════════════════════════════════════════════════════════════════════

echo.
echo  FOS — Setup and Build
echo  =====================
echo.

REM ── Check Python ─────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found.
    echo  Install Python 3.11+ from https://python.org and ensure it is on your PATH.
    pause
    exit /b 1
)

echo  Python found. Installing dependencies...
echo.

REM ── Install dependencies ─────────────────────────────────────────────────
pip install PyQt6 pandas openpyxl pdfplumber scikit-learn pyinstaller cryptography

REM ── SQLCipher — attempt install, note if it fails ────────────────────────
echo.
echo  Attempting sqlcipher3 install (encrypted database)...
pip install sqlcipher3-binary
if errorlevel 1 (
    echo.
    echo  NOTE: sqlcipher3 could not be installed automatically.
    echo  FOS will run in UNENCRYPTED development mode.
    echo  For production use, install sqlcipher3 manually.
    echo  See: https://github.com/coleifer/sqlcipher3
    echo.
)

REM ── Run directly (development mode) ──────────────────────────────────────
echo.
echo  Starting FOS in development mode...
echo  (Close this window to stop the application)
echo.
cd /d "%~dp0"
python app.py

REM ── To build .exe instead, uncomment the lines below ─────────────────────
REM echo  Building FOS.exe...
REM pyinstaller fos.spec
REM echo.
REM echo  Done. Run: dist\FOS.exe
REM pause
