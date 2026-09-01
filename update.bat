@echo off
rem ---------------------------------------------------------------------------
rem  Quant digest - the update.
rem
rem  Everything runs here. Collects every source, summarizes what is new,
rem  rebuilds the page, then pushes so the published site catches up.
rem
rem  Double-click it, or from a terminal:
rem      update.bat                 collect, summarize, publish
rem      update.bat --deep 3        ... and pre-build the top 3 deep reports
rem      update.bat --source ssrn   just one source
rem
rem  First time on a machine? Run setup.bat once.
rem ---------------------------------------------------------------------------
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

rem PortableGit lives under the user profile and is not always on PATH.
where git >nul 2>&1 || set "PATH=%LOCALAPPDATA%\Programs\PortableGit\cmd;%PATH%"
where git >nul 2>&1 || (
  echo [!] git not found. Install it, or check %%LOCALAPPDATA%%\Programs\PortableGit.
  goto :fail
)
where python >nul 2>&1 || (
  echo [!] python not found on PATH.
  goto :fail
)

echo ===========================================================
echo   Quant digest - full local update
echo   Chrome will flash for SSRN and Macrosynergy. It is parked
echo   off-screen; leave it alone and it closes itself.
echo ===========================================================
echo.

echo [1/3] Pulling anything published from another machine
git pull --rebase --autostash
if errorlevel 1 goto :conflict
echo.

echo [2/3] Collecting, summarizing, rebuilding
rem Defaults to every source. Anything you pass on the command line wins,
rem so `update.bat --source ssrn` overrides it.
python run.py all --source all %*
if errorlevel 1 goto :fail
echo.

echo [3/3] Publishing
python run.py publish
if errorlevel 1 goto :fail
echo.

echo ===========================================================
echo   Done.  https://woodzkr.github.io/qfin-digest/
echo   The live site takes a minute or two to catch up.
echo ===========================================================
goto :done

:conflict
echo.
echo [!] The pull did not apply cleanly - another machine published in between.
echo     Resolve with:
echo         git status
echo         git rebase --continue      (after fixing the listed files)
echo     Generated files under report\ and index.html can always be thrown away
echo     and rebuilt with:  python run.py report --all
goto :end

:fail
echo.
echo [!] Stopped on an error. Nothing was published.
echo     Whatever was already collected is saved in state\seen.json,
echo     so re-running picks up where this left off.

:end
echo.
pause
exit /b 1

:done
echo.
pause
exit /b 0
