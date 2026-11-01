@echo off
title Job Accelerator Dashboard
cd /d "C:\Users\PC\Documents\antigravity\resilient-pasteur\tmp\job-accelerator-actions-migration"
echo ========================================================
echo       Starting Job Accelerator Local Dashboard...
echo ========================================================
python run.py
if errorlevel 1 (
    echo [!] Server exited with an error.
    pause
)
