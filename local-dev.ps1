param(
    [ValidateSet("setup", "start", "stop", "status")]
    [string]$Action = "status",
    [string]$PackageIndexUrl = ""
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$SystemDir = Join-Path $Root "system"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$DataDir = Join-Path $Root ".pgsql\data"
$RuntimeDir = Join-Path $Root ".local-runtime"
$DbLog = Join-Path $Root ".pgsql\postgres.log"
$DjangoOut = Join-Path $RuntimeDir "django.stdout.log"
$DjangoErr = Join-Path $RuntimeDir "django.stderr.log"
$DjangoPid = Join-Path $RuntimeDir "django.pid"
$DbPort = 55432
$AppPort = 8000
$DatabaseUrl = "postgresql://audit_user:audit_pass@localhost:$DbPort/audit_budget_system"

function Get-PostgresBin {
    $base = "C:\Program Files\PostgreSQL"
    $installation = Get-ChildItem $base -Directory -ErrorAction Stop |
        Where-Object { $_.Name -match "^\d+$" } |
        Sort-Object { [int]$_.Name } -Descending |
        Where-Object { Test-Path (Join-Path $_.FullName "bin\pg_ctl.exe") } |
        Select-Object -First 1
    if (-not $installation) {
        throw "PostgreSQL is not installed under $base."
    }
    return Join-Path $installation.FullName "bin"
}

function Get-BootstrapPython {
    $codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $codexPython) {
        return $codexPython
    }
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        return "py"
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }
    throw "Python 3.11+ is required."
}

function Test-LocalDatabaseConnection {
    param([string]$PgBin)
    & (Join-Path $PgBin "psql.exe") -w -h localhost -p $DbPort -U postgres -d postgres -tAc "SELECT 1" *> $null
    return $LASTEXITCODE -eq 0
}

function Start-LocalDatabase {
    $pgBin = Get-PostgresBin
    New-Item -ItemType Directory -Force -Path (Split-Path $DataDir), $RuntimeDir | Out-Null
    if (-not (Test-Path (Join-Path $DataDir "PG_VERSION"))) {
        & (Join-Path $pgBin "initdb.exe") -D $DataDir -U postgres -A trust --encoding=UTF8 --no-locale
    }
    if (-not (Test-LocalDatabaseConnection -PgBin $pgBin)) {
        & (Join-Path $pgBin "pg_ctl.exe") start -D $DataDir -l $DbLog -o "-p $DbPort -h localhost" -w
    }
    $env:PGHOST = "localhost"
    $env:PGPORT = "$DbPort"
    $env:PGUSER = "postgres"
    $role = (& (Join-Path $pgBin "psql.exe") -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='audit_user'") -join ""
    if ($role.Trim() -ne "1") {
        & (Join-Path $pgBin "psql.exe") -d postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE audit_user LOGIN PASSWORD 'audit_pass' CREATEDB;"
    }
    $database = (& (Join-Path $pgBin "psql.exe") -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='audit_budget_system'") -join ""
    if ($database.Trim() -ne "1") {
        & (Join-Path $pgBin "createdb.exe") -O audit_user audit_budget_system
    }
}

function Set-DjangoEnvironment {
    $env:DATABASE_URL = $DatabaseUrl
    $env:DJANGO_SETTINGS_MODULE = "config.settings.development"
    $env:DJANGO_DEV_HTTPS_COOKIES = "false"
    $env:SYSTEM_MODE = "operational"
    $env:SUPABASE_PROJECT_REF = "doehmumbdoaxppqxhnwt"
}

function Start-Django {
    if (-not (Test-Path $VenvPython)) {
        throw "Run .\local-dev.ps1 setup first."
    }
    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$AppPort/" -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            return
        }
    } catch {}
    Set-DjangoEnvironment
    $process = Start-Process -FilePath $VenvPython -ArgumentList @("manage.py", "runserver", "127.0.0.1:$AppPort", "--noreload") -WorkingDirectory $SystemDir -WindowStyle Hidden -PassThru -RedirectStandardOutput $DjangoOut -RedirectStandardError $DjangoErr
    Set-Content -LiteralPath $DjangoPid -Value $process.Id -Encoding ascii
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$AppPort/" -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) {
                return
            }
        } catch {}
    }
    throw "Django did not become ready. Review $DjangoErr."
}

function Stop-Django {
    if (Test-Path $DjangoPid) {
        $processId = [int](Get-Content $DjangoPid -Raw)
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $processId -Force
        }
        Remove-Item -LiteralPath $DjangoPid -Force
    }
}

function Stop-LocalDatabase {
    if (-not (Test-Path (Join-Path $DataDir "PG_VERSION"))) {
        return
    }
    $pgBin = Get-PostgresBin
    & (Join-Path $pgBin "pg_ctl.exe") status -D $DataDir *> $null
    if ($LASTEXITCODE -eq 0) {
        & (Join-Path $pgBin "pg_ctl.exe") stop -D $DataDir -m fast -w
    }
}

function Initialize-LocalEnvironment {
    if (-not (Test-Path $VenvPython)) {
        $bootstrap = Get-BootstrapPython
        if ($bootstrap -eq "py") {
            & py -3.12 -m venv (Join-Path $Root ".venv")
        } else {
            & $bootstrap -m venv (Join-Path $Root ".venv")
        }
    }
    $requirements = Get-Content (Join-Path $SystemDir "requirements.txt") |
        Where-Object { $_ -and -not $_.TrimStart().StartsWith("#") -and $_.Trim() -ne "pgserver" }
    $pipArguments = @("-m", "pip", "install", "--disable-pip-version-check")
    if ($PackageIndexUrl) {
        $pipArguments += @("--index-url", $PackageIndexUrl)
    }
    $pipArguments += $requirements
    & $VenvPython @pipArguments
    Start-LocalDatabase
    Set-DjangoEnvironment
    Push-Location $SystemDir
    try {
        & $VenvPython manage.py migrate --noinput
        & $VenvPython manage.py collectstatic --noinput
        & $VenvPython manage.py check
    } finally {
        Pop-Location
    }
}

function Show-Status {
    $databaseStatus = "stopped"
    if (Test-Path (Join-Path $DataDir "PG_VERSION")) {
        $pgBin = Get-PostgresBin
        if (Test-LocalDatabaseConnection -PgBin $pgBin) {
            $databaseStatus = "running on localhost:$DbPort"
        }
    }
    $applicationStatus = "stopped"
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$AppPort/" -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            $applicationStatus = "running at http://127.0.0.1:$AppPort/"
        }
    } catch {}
    Write-Host "PostgreSQL: $databaseStatus"
    Write-Host "Django:     $applicationStatus"
}

switch ($Action) {
    "setup" {
        Initialize-LocalEnvironment
        Start-Django
        Show-Status
    }
    "start" {
        Start-LocalDatabase
        Start-Django
        Show-Status
    }
    "stop" {
        Stop-Django
        Stop-LocalDatabase
        Show-Status
    }
    "status" {
        Show-Status
    }
}
