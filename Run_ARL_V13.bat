@echo off
setlocal
TITLE ARL V13 - Master Sync + Organized Data
cd /d "%~dp0"
if exist "..\arl_env\Scripts\activate.bat" (
    call "..\arl_env\Scripts\activate.bat"
) else if exist "arl_env\Scripts\activate.bat" (
    call "arl_env\Scripts\activate.bat"
) else (
    echo [INFO] ARL virtual environment not found beside this package.
    echo [INFO] Using the Python environment currently available on PATH.
)
echo.
echo Starting ARL V13 on http://127.0.0.1:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
echo.
echo ARL server stopped.
pause
endlocal
