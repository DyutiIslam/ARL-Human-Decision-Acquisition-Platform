@echo off
setlocal
TITLE ARL V13.2 - Remote Media Fix
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
echo ================================================================
echo ARL V13.2 - Moderator Server
echo ================================================================
echo Starting plain HTTP on all interfaces, port 8000.
echo Moderator opens locally at http://127.0.0.1:8000/
echo Remote participants MUST use the supplied Participant_Launchers.
echo Do NOT open participant pages from a normal browser tab.
echo ================================================================
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

echo.
echo ARL server stopped.
pause
endlocal
