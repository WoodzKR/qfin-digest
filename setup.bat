@echo off
rem ---------------------------------------------------------------------------
rem  Quant digest - one-time setup.
rem
rem  Run once on a machine. Installs what the pipeline needs and checks that
rem  every piece actually answers. After this, `update.bat` is all you need.
rem ---------------------------------------------------------------------------
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set MISSING=0

echo ===========================================================
echo   Quant digest - setup
echo ===========================================================
echo.

echo [1/5] Checking Python
where python >nul 2>&1 || (
  echo     [!] Python not found. Install 3.10+ from https://python.org
  echo         and tick "Add python.exe to PATH".
  set MISSING=1
  goto :node
)
python --version

:node
echo.
echo [2/5] Checking Node.js
where node >nul 2>&1 || (
  echo     [!] Node.js not found. Install LTS from https://nodejs.org
  set MISSING=1
  goto :check
)
node --version

:check
if "%MISSING%"=="1" (
  echo.
  echo   Install the missing pieces above, then run setup.bat again.
  goto :end
)

echo.
echo [3/5] Installing Python packages
python -m pip install --quiet --upgrade pip
python -m pip install --quiet requests playwright pypdf
if errorlevel 1 goto :fail
echo     requests, playwright, pypdf
python -m playwright install chromium
if errorlevel 1 goto :fail

echo.
echo [4/5] Installing the Claude Code CLI
call npm i -g @anthropic-ai/claude-code
if errorlevel 1 goto :fail
call "%APPDATA%\npm\claude.cmd" --version

echo.
echo [5/5] Checking the Claude login
call "%APPDATA%\npm\claude.cmd" auth status >nul 2>&1
if errorlevel 1 (
  echo     Not signed in. A browser will open.
  call "%APPDATA%\npm\claude.cmd" auth login
) else (
  echo     Already signed in.
)

echo.
echo -----------------------------------------------------------
echo   Chrome or Edge is also needed, for SSRN and Macrosynergy.
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
  echo   Chrome: found
) else if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
  echo   Edge: found - Chrome is preferred but Edge works
) else (
  echo   [!] Neither found. Those two sources will be skipped;
  echo       everything else still works.
)
echo -----------------------------------------------------------
echo.
echo   Setup done. Now run:  update.bat
echo.
goto :end

:fail
echo.
echo [!] An install step failed. Scroll up for the reason.

:end
echo.
pause
