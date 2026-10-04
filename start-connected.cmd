@echo off
setlocal
cd /d "%~dp0"
echo Restarting AuditDash in connected mode using the Supabase database...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-dev.ps1" stop
if errorlevel 1 goto :failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-dev.ps1" start -DataSource cloud
if errorlevel 1 goto :failed
start "" "http://127.0.0.1:8000/"
echo.
echo Connected mode is active. Local and Vercel now use the same Supabase data.
echo Internet access is required while this mode is running.
exit /b 0

:failed
echo.
echo Connected startup failed. Confirm SUPABASE_DATABASE_URL in system\.env.
pause
exit /b 1
