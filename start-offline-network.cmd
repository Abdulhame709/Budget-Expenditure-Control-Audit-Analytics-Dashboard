@echo off
setlocal
cd /d "%~dp0"
echo Restarting AuditDash for local-network access...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-dev.ps1" stop
if errorlevel 1 goto :failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-dev.ps1" start -BindAddress 0.0.0.0
if errorlevel 1 goto :failed
for /f "usebackq delims=" %%I in (`powershell.exe -NoProfile -Command "$ip=(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue ^| Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } ^| Select-Object -First 1 -ExpandProperty IPAddress); if($ip){$ip}"`) do set "LAN_IP=%%I"
echo.
echo AuditDash is available on this computer at http://127.0.0.1:8000/
if defined LAN_IP (
  echo Other devices on the same private network can use http://%LAN_IP%:8000/
  start "" "http://%LAN_IP%:8000/"
) else (
  echo Could not detect the LAN address. Run ipconfig and use the IPv4 address with port 8000.
  start "" "http://127.0.0.1:8000/"
)
echo Internet access is not required. Windows Firewall may ask to allow Python on private networks.
exit /b 0

:failed
echo.
echo Network startup failed. Review .local-runtime\django.stderr.log
pause
exit /b 1
