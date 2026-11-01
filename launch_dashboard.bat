@echo off
title Job Accelerator Dashboard
cd /d "%~dp0"
echo ========================================================
echo       Starting Job Accelerator Local Dashboard...
echo ========================================================
python run.py
if errorlevel 1 (
    echo [!] Server exited with an error.
    pause
)
