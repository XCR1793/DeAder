@echo off
setlocal

REM Canonical launcher (double-click).
REM Advanced switches: DeAder.bat --restart / --multi

set "SCRIPT_DIR=%~dp0"

REM Ensure venv exists + deps are up-to-date (run hidden).
REM We keep a simple stamp file so subsequent launches are fast.
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ^
  "Set-Location '%SCRIPT_DIR%'; " ^
  "if (-not (Test-Path '.\.venv')) { py -m venv .venv }; " ^
  "$stamp='.\.venv\.deader_deps_stamp'; " ^
  "$need=$true; " ^
  "if (Test-Path $stamp) { " ^
  "  $rt=(Get-Item '.\requirements.txt').LastWriteTimeUtc; " ^
  "  $st=(Get-Item $stamp).LastWriteTimeUtc; " ^
  "  if ($st -ge $rt) { $need=$false } " ^
  "}; " ^
  "if ($need) { " ^
  "  .\.venv\Scripts\python.exe -m pip install -r requirements.txt | Out-Null; " ^
  "  New-Item -ItemType File -Force $stamp | Out-Null " ^
  "}"

REM Start tray controller hidden via powershell Start-Process
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ^
  "Start-Process -FilePath '%SCRIPT_DIR%\.venv\Scripts\pythonw.exe' -ArgumentList 'tray_launcher.py %*' -WorkingDirectory '%SCRIPT_DIR%' -WindowStyle Hidden"

echo DeAder started from: %SCRIPT_DIR%
echo Look for the DeAder icon in the system tray.
exit /b 0

