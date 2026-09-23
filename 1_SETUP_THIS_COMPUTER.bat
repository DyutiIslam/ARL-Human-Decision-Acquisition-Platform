@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title ARL V13.2 - First-Time ARL Runtime Setup

set "PYVER=3.11.9"
set "PYEXE="
set "MANAGED_PY=%~dp0ARL_Runtime\Python311\python.exe"
set "VENV_PY=%~dp0ARL_System\.venv\Scripts\python.exe"
set "INSTALLER=%TEMP%\python-%PYVER%-amd64.exe"
set "PYURL=https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe"
set "INSTALL_LOG=%~dp0ARL_Runtime\python_install.log"
set "AUTO_MODE=0"
if /I "%~1"=="--auto" set "AUTO_MODE=1"

echo =============================================================
echo  ARL V13.2 - FIRST-TIME ARL RUNTIME SETUP
echo =============================================================
echo.
echo This setup prepares ONLY the ARL Python environment and packages.
echo It does NOT install Consensys Pro, EMOTIV PRO, LabRecorder,
echo or hardware/vendor drivers.
echo.
echo Internet access is required the first time packages are installed.
echo Do not close this window while setup is running.
echo.

if not exist "ARL_System\app\main.py" goto :missing_files
if not exist "ARL_System\requirements.txt" goto :missing_files
if not exist "ARL_Runtime" mkdir "ARL_Runtime"

echo [1/6] ARL software files found.

rem -------------------------------------------------------------
rem Prefer an existing compatible Python 3.11 installation.
rem This avoids trying to reinstall Python on computers that
rem already have Python 3.11 registered with Windows.
rem -------------------------------------------------------------
if exist "%MANAGED_PY%" (
  set "PYEXE=%MANAGED_PY%"
  echo [2/6] Existing ARL-managed Python 3.11 found.
  goto :python_found
)

for /f "usebackq delims=" %%P in (`py -3.11 -c "import sys; print(sys.executable)" 2^>nul`) do if not defined PYEXE set "PYEXE=%%P"
if defined PYEXE (
  if exist "!PYEXE!" (
    echo [2/6] Compatible existing Python 3.11 found.
    goto :python_found
  )
)
set "PYEXE="

for /f "usebackq delims=" %%P in (`python -c "import sys; print(sys.executable if sys.version_info[:2] == (3,11) else '')" 2^>nul`) do if not defined PYEXE set "PYEXE=%%P"
if defined PYEXE (
  if exist "!PYEXE!" (
    echo [2/6] Compatible existing Python 3.11 found.
    goto :python_found
  )
)
set "PYEXE="

echo [2/6] Compatible Python 3.11 was not found. Preparing managed runtime...
echo       Downloading Python %PYVER% from python.org...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -UseBasicParsing -Uri '%PYURL%' -OutFile '%INSTALLER%' } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 goto :download_failed
if not exist "%INSTALLER%" goto :download_failed

echo       Installing Python %PYVER% inside this ARL package...
echo       Waiting for the Python installer to finish...
start /wait "" "%INSTALLER%" /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Include_doc=0 Include_tcltk=1 Include_pip=1 Include_dev=1 Include_exe=1 Include_lib=1 Include_tools=1 Shortcuts=0 TargetDir="%~dp0ARL_Runtime\Python311" /log "%INSTALL_LOG%"
set "PY_INSTALL_EXIT=!ERRORLEVEL!"
if not "!PY_INSTALL_EXIT!"=="0" goto :python_install_failed
if not exist "%MANAGED_PY%" goto :python_missing_after_install
set "PYEXE=%MANAGED_PY%"
del /q "%INSTALLER%" >nul 2>nul

:python_found
"%PYEXE%" -c "import sys; assert sys.version_info[:2] == (3,11); print('Using Python:', sys.executable); print('Python version:', sys.version.split()[0])"
if errorlevel 1 goto :python_incompatible

echo [3/6] Compatible Python 3.11 runtime verified.

if not exist "%VENV_PY%" (
  echo [4/6] Creating isolated ARL Python environment...
  "%PYEXE%" -m venv "%~dp0ARL_System\.venv"
  if errorlevel 1 goto :setup_failed
) else (
  echo [4/6] Existing isolated ARL environment found.
)

echo [5/6] Installing/verifying ARL Python packages...
"%VENV_PY%" -m pip install --disable-pip-version-check --upgrade pip
if errorlevel 1 goto :package_failed
"%VENV_PY%" -m pip install --disable-pip-version-check -r "%~dp0ARL_System\requirements.txt"
if errorlevel 1 goto :package_failed

echo [6/6] Running ARL dependency self-test...
"%VENV_PY%" -c "import fastapi,uvicorn,sqlmodel,pydantic,pylsl,pyxdf,pandas,numpy; import tkinter; print('ARL dependency self-test: PASS')"
if errorlevel 1 goto :selftest_failed

if not exist "Data" mkdir "Data"
>"ARL_Runtime\SETUP_COMPLETE.txt" echo ARL V13.2 setup completed successfully on %DATE% %TIME%
>"ARL_Runtime\PYTHON_USED.txt" echo %PYEXE%
for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath '%~dp0ARL_System\requirements.txt').Hash"`) do >"ARL_Runtime\requirements.sha256" echo %%H

echo.
echo =============================================================
echo  ARL V13.2 SETUP COMPLETE
echo =============================================================
echo This computer is ready to run the ARL application.
echo.
echo For normal sessions, double-click:
echo   2_START_ARL.bat
echo.
echo You do NOT need to install or use Python or pip manually.
echo =============================================================
if "%AUTO_MODE%"=="0" pause
exit /b 0

:download_failed
echo.
echo =============================================================
echo  SETUP STOPPED - PYTHON DOWNLOAD FAILED
echo =============================================================
echo Confirm this computer has internet access and can reach python.org,
echo then run 1_SETUP_THIS_COMPUTER.bat again.
pause
exit /b 1

:python_install_failed
echo.
echo =============================================================
echo  SETUP STOPPED - PYTHON INSTALLER RETURNED AN ERROR
echo =============================================================
echo Python installer exit code: !PY_INSTALL_EXIT!
echo Installer log:
echo   %INSTALL_LOG%
pause
exit /b 1

:python_missing_after_install
echo.
echo =============================================================
echo  SETUP STOPPED - PYTHON.EXE WAS NOT CREATED
echo =============================================================
echo The installer reported success, but this file is missing:
echo   %MANAGED_PY%
echo Installer log:
echo   %INSTALL_LOG%
pause
exit /b 1

:python_incompatible
echo.
echo =============================================================
echo  SETUP STOPPED - COMPATIBLE PYTHON 3.11 NOT VERIFIED
echo =============================================================
echo The detected Python executable did not report Python 3.11.
echo Take a screenshot and contact the ARL lead.
pause
exit /b 1

:package_failed
echo.
echo =============================================================
echo  SETUP STOPPED - ARL PACKAGES COULD NOT BE INSTALLED
echo =============================================================
echo Confirm internet access, then run this setup again.
pause
exit /b 1

:selftest_failed
echo.
echo =============================================================
echo  SETUP STOPPED - ARL SELF-TEST FAILED
echo =============================================================
echo The runtime was prepared, but one or more ARL components did not load.
echo Take a screenshot and contact the ARL lead. Do not continue to data collection.
pause
exit /b 1

:missing_files
echo.
echo =============================================================
echo  SETUP STOPPED - ARL SOFTWARE FILES ARE MISSING
echo =============================================================
echo Re-extract the complete ARL ZIP. Do not move files individually.
pause
exit /b 1

:setup_failed
echo.
echo =============================================================
echo  ARL SETUP FAILED
echo =============================================================
echo Do not edit software files. Take a screenshot of this window and
echo contact the ARL lead with the computer name and this error.
pause
exit /b 1
