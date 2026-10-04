@echo off
setlocal
cd /d "%~dp0"
echo Starting the local PostgreSQL database and AuditDash...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-dev.ps1" start
if errorlevel 1 (
  echo.
  echo Startup failed. Run: powershell -ExecutionPolicy Bypass -File .\local-dev.ps1 setup
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8000/"
echo AuditDash is available offline at http://127.0.0.1:8000/
endlocal
