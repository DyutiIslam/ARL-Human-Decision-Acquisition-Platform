@echo off
setlocal
TITLE ARL V12 Consolidated - P1 Multimodal Test

REM Run from this package folder. Prefer the shared ARL virtual environment one level up if present.
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
echo Starting ARL V12 Consolidated on http://127.0.0.1:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

echo.
echo ARL server stopped.
pause
endlocal
