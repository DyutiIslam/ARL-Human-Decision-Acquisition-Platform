@echo off
title ARL V11 Clean One-Station

cd /d "C:\Users\dislam2\OneDrive - Kennesaw State University\1Projects\ARL"

call arl_env\Scripts\activate.bat

cd /d "C:\Users\dislam2\OneDrive - Kennesaw State University\1Projects\ARL\arl_acquisition_interface_v11_clean_one_station\arl_v11_clean_one_station"

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

pause