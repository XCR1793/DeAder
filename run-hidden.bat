@echo off
setlocal

REM Launch DeAder tray controller (no visible terminal).
REM Default: single instance. Pass --multi to allow multiple instances.

set "SCRIPT_DIR=%~dp0"

REM Ensure venv + deps exist (this opens briefly in some setups; tray runs hidden)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Set-Location '%SCRIPT_DIR%'; if (-not (Test-Path '.\.venv')) { py -m venv .venv }; .\.venv\Scripts\python.exe -m pip install -r requirements.txt | Out-Null"

REM Start tray controller hidden via powershell Start-Process
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process -FilePath '%SCRIPT_DIR%\.venv\Scripts\pythonw.exe' -ArgumentList 'tray_launcher.py %*' -WorkingDirectory '%SCRIPT_DIR%' -WindowStyle Hidden"

echo DeAder started. Look for the DeAder icon in the system tray.
exit /b 0

