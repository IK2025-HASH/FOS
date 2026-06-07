@echo off
REM ═══════════════════════════════════════════════════════════════════════════
REM  FOS — Multi-Company Accounting System
REM  Run this from Command Prompt to sync latest code and launch FOS.
REM
REM  First time:  double-click or run from Command Prompt
REM  Every time after:  same — it pulls latest changes then starts the app
REM ═══════════════════════════════════════════════════════════════════════════

echo.
echo  FOS — Sync and Run
echo  ==================
echo.

cd /d "%~dp0"

REM ── Sync latest code from GitHub ─────────────────────────────────────────
echo  Checking for latest updates from GitHub...
git --version >nul 2>&1
if errorlevel 1 (
    echo  WARNING: Git not found — skipping update check.
    echo  Install Git from https://git-scm.com if you want auto-updates.
    echo.
) else (
    git pull origin claude/al-khwarizmi
    if errorlevel 1 (
        echo  WARNING: Could not pull latest code. Running with current version.
        echo.
    ) else (
        echo  Code is up to date.
        echo.
    )
)

REM ── Check Python ─────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found.
    echo  Install Python 3.11+ from https://python.org
    echo  Make sure to tick "Add Python to PATH" during install.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do echo  Found: %%i
echo.

REM ── Install / update dependencies ────────────────────────────────────────
echo  Installing dependencies (skipped if already up to date)...
pip install --quiet PyQt6 pandas openpyxl pdfplumber scikit-learn cryptography reportlab

REM ── SQLCipher (encrypted DB) — optional, graceful fallback ───────────────
pip install --quiet sqlcipher3-binary >nul 2>&1
if errorlevel 1 (
    pip install --quiet sqlcipher3 >nul 2>&1
)

echo  Dependencies ready.
echo.

REM ── Launch FOS ────────────────────────────────────────────────────────────
echo  Starting FOS...
echo  -------------------------------------------------------
python app.py

if errorlevel 1 (
    echo.
    echo  FOS exited with an error. See messages above.
    pause
)
