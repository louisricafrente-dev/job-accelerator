@echo off
title Job Application Accelerator
echo ======================================================================
echo          JOB APPLICATION ACCELERATOR - COMMAND CENTER
echo ======================================================================
echo.
echo [*] Initializing workspace...
cd /d "C:\Users\PC\.gemini\antigravity\scratch\job-accelerator"

if exist "C:\Users\PC\AppData\Local\Programs\Python\Python312\python.exe" (
    "C:\Users\PC\AppData\Local\Programs\Python\Python312\python.exe" run.py
) else (
    python run.py
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo [!] Server exited with code %ERRORLEVEL%.
    pause
)
