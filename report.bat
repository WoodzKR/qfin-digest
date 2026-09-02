@echo off
rem ---------------------------------------------------------------------------
rem  Quant digest - deep report mode.
rem
rem  Starts the local server and opens the digest with the report buttons live.
rem  Click a card's KO or EN button and it builds on the spot - no terminal.
rem
rem  Close this window (or Ctrl+C) when you are done, then run update.bat to
rem  publish whatever was built.
rem ---------------------------------------------------------------------------
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

where python >nul 2>&1 || (
  echo [!] python not found on PATH. Run setup.bat first.
  pause
  exit /b 1
)

echo ===========================================================
echo   Deep report mode
echo   A browser tab will open. Click the KO / EN button on any
echo   card to build its report. Leave this window open.
echo   Close it when you are done.
echo ===========================================================
echo.

python run.py serve %*

echo.
echo Server stopped. Run update.bat to publish what you built.
pause
