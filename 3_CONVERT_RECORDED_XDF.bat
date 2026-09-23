@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ARL V13.2 - XDF Converter
if not exist "ARL_Runtime\SETUP_COMPLETE.txt" goto :not_setup
if not exist "ARL_System\.venv\Scripts\python.exe" goto :not_setup
if not exist "ARL_System\app\xdf_to_csv_gui.py" goto :missing_files
cd /d "%~dp0ARL_System"
".venv\Scripts\python.exe" app\xdf_to_csv_gui.py
if errorlevel 1 (
  echo.
  echo Converter closed with an error. Take a screenshot and contact the ARL lead.
)
pause
exit /b
:not_setup
echo ARL computer setup is not complete. Run 1_SETUP_THIS_COMPUTER.bat first.
pause
exit /b 1
:missing_files
echo Converter files are missing. Re-extract the complete ARL package.
pause
exit /b 1
