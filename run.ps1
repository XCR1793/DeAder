$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path ".\.venv")) {
  py -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not $env:DEADER_BIND) { $env:DEADER_BIND = "0.0.0.0" }
if (-not $env:DEADER_PORT) { $env:DEADER_PORT = "8787" }

Write-Host "Starting server on http://$($env:DEADER_BIND):$($env:DEADER_PORT)"
.\.venv\Scripts\python.exe -m uvicorn app.server:app --host $env:DEADER_BIND --port $env:DEADER_PORT

