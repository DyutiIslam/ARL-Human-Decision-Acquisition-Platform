@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ARL V13.2 - Data Collection

set "VENV_PY=%~dp0ARL_System\.venv\Scripts\python.exe"
set "REQ=%~dp0ARL_System\requirements.txt"
set "STAMP=%~dp0ARL_Runtime\requirements.sha256"
set "NEED_SETUP=0"

if not exist "ARL_System\app\main.py" goto :missing_files
if not exist "%REQ%" goto :missing_files
if not exist "%VENV_PY%" set "NEED_SETUP=1"
if not exist "ARL_Runtime\SETUP_COMPLETE.txt" set "NEED_SETUP=1"

rem If a runtime exists, verify that this release uses the same dependency manifest.
if "%NEED_SETUP%"=="0" (
  for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath '%REQ%').Hash"`) do set "CURRENT_HASH=%%H"
  if not exist "%STAMP%" set "NEED_SETUP=1"
  if exist "%STAMP%" (
    set /p SAVED_HASH=<"%STAMP%"
    call if /I not "%%CURRENT_HASH%%"=="%%SAVED_HASH%%" set "NEED_SETUP=1"
  )
)

if "%NEED_SETUP%"=="1" goto :prepare_runtime

rem Quick import check catches a damaged/deleted environment even when the hash matches.
"%VENV_PY%" -c "import fastapi,uvicorn,sqlmodel,pydantic,pylsl,pyxdf,pandas,numpy" >nul 2>&1
if errorlevel 1 goto :prepare_runtime

goto :start_server

:prepare_runtime
echo =============================================================
echo  ARL V13.2 - RUNTIME UPDATE REQUIRED
echo =============================================================
echo This ARL release needs its runtime prepared or updated.
echo Setup will run automatically now.
echo.
call "%~dp01_SETUP_THIS_COMPUTER.bat" --auto
if errorlevel 1 goto :setup_failed
if not exist "%VENV_PY%" goto :setup_failed

:start_server
echo =============================================================
echo  ARL V13.2 - DATA COLLECTION
echo =============================================================
echo Runtime check: PASS
echo Starting the ARL server...
echo Keep this window OPEN for the entire session.
echo.
cd /d "%~dp0ARL_System"
start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8000/'"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000

echo.
echo ARL server has stopped.
pause
exit /b

:setup_failed
echo.
echo =============================================================
echo  ARL CANNOT START - RUNTIME UPDATE FAILED
echo =============================================================
echo Take a screenshot of the setup error and contact the ARL lead.
pause
exit /b 1

:missing_files
echo =============================================================
echo  ARL CANNOT START - SOFTWARE FILES ARE MISSING
echo =============================================================
echo Re-extract the complete ARL package and try again.
pause
exit /b 1
