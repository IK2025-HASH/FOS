@echo off
REM ═══════════════════════════════════════════════════════════════════════════
REM  FOS — Build Windows .exe
REM  Run this AFTER run.bat has succeeded at least once (dependencies installed)
REM ═══════════════════════════════════════════════════════════════════════════

echo.
echo  Building FOS.exe with PyInstaller...
echo.

cd /d "%~dp0"
pyinstaller fos.spec --clean

if errorlevel 1 (
    echo.
    echo  BUILD FAILED. Check the output above for errors.
    pause
    exit /b 1
)

echo.
echo  ======================================================
echo   SUCCESS
echo   Executable: dist\FOS.exe
echo   Double-click dist\FOS.exe to run.
echo  ======================================================
echo.
pause
