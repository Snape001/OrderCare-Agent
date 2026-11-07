$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" +
    [Environment]::GetEnvironmentVariable("PATH", "Machine")
$UvPath = (Get-Command uv -ErrorAction Stop).Source
$env:PYTHONPATH = "src"

New-Item -ItemType Directory -Force -Path "data\logs" | Out-Null

function Test-Url([string]$Url) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Test-Redis {
    $PreviousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $UvPath run python -c 'from core import settings; from redis import Redis; Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2).ping()' *> $null
        return $LASTEXITCODE -eq 0
    }
    finally {
        $ErrorActionPreference = $PreviousPreference
    }
}

$MemoryJson = & $UvPath run python -c "import json; from urllib.parse import urlsplit; from core import settings; raw = settings.REDIS_URL or ''; url = urlsplit(raw); print(json.dumps({'enabled': settings.MEMORY_ENABLED, 'episodic': settings.EPISODIC_MEMORY_ENABLED, 'host': url.hostname, 'port': url.port or 6379, 'url': raw}))"
if ($LASTEXITCODE -ne 0) { throw "Unable to read Memory configuration." }
$MemoryConfig = $MemoryJson | ConvertFrom-Json
if ($MemoryConfig.enabled -and $MemoryConfig.host -eq "localhost") {
    # Docker publishes Redis on IPv4; asyncio may otherwise resolve localhost to IPv6.
    $RedisUri = [System.UriBuilder]::new($MemoryConfig.url)
    $RedisUri.Host = "127.0.0.1"
    $env:REDIS_URL = $RedisUri.Uri.AbsoluteUri
}
$RedisReady = -not $MemoryConfig.enabled -or (Test-Redis)
if ($MemoryConfig.enabled -and -not $RedisReady) {
    if ($MemoryConfig.host -in @("127.0.0.1", "localhost") -and $MemoryConfig.port -eq 6379 -and (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "Starting the Redis dependency with Docker Compose..." -ForegroundColor Cyan
        docker compose up -d redis
        if ($LASTEXITCODE -ne 0) { throw "Redis could not be started with Docker Compose." }
        for ($i = 0; $i -lt 30; $i++) {
            if (Test-Redis) { $RedisReady = $true; break }
            Start-Sleep -Seconds 1
        }
    }
    if (-not $RedisReady) {
        throw "Memory requires Redis at $($MemoryConfig.host):$($MemoryConfig.port). Start Redis or Docker Desktop, then retry."
    }
}

if (Test-Url "http://127.0.0.1:8080/health") {
    try { $ExistingReady = Invoke-RestMethod -Uri "http://127.0.0.1:8080/ready" -TimeoutSec 3 }
    catch { $ExistingReady = $null }
    if ($MemoryConfig.enabled -and
        (-not $ExistingReady -or $ExistingReady.memory.redis -ne "ready" -or
            ($MemoryConfig.episodic -and $ExistingReady.memory.episodic -ne "ready"))) {
        throw "An existing FastAPI service does not have ready Memory. Stop it with .\scripts\stop_demo.cmd and retry."
    }
}
else {
    Write-Host "Starting the FastAPI service..." -ForegroundColor Cyan
    $Service = Start-Process -FilePath $UvPath `
        -ArgumentList @("run", "python", "src/run_service.py") `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput "data\logs\service.out.log" `
        -RedirectStandardError "data\logs\service.err.log" `
        -WindowStyle Hidden `
        -PassThru
    Set-Content -LiteralPath "data\logs\service.pid" -Value $Service.Id
}

$ServiceReady = $false
for ($i = 0; $i -lt 180; $i++) {
    try {
        $Ready = Invoke-RestMethod -Uri "http://127.0.0.1:8080/ready" -TimeoutSec 3
    }
    catch { $Ready = $null }
    if ($Ready -and $Ready.status -eq "ready" -and
        (-not $MemoryConfig.enabled -or
            ($Ready.memory.redis -eq "ready" -and $Ready.memory.profile -eq "ready" -and
                (-not $MemoryConfig.episodic -or $Ready.memory.episodic -eq "ready")))) {
        $ServiceReady = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $ServiceReady) {
    if (Test-Path "data\logs\service.err.log") {
        Get-Content -LiteralPath "data\logs\service.err.log" -Tail 50
    }
    throw "FastAPI/Memory is not ready. If an older service is running, stop it with .\scripts\stop_demo.cmd and retry."
}

if (-not (Test-Url "http://127.0.0.1:8501/_stcore/health")) {
    Write-Host "Starting the Streamlit app..." -ForegroundColor Cyan
    $App = Start-Process -FilePath $UvPath `
        -ArgumentList @(
            "run", "streamlit", "run", "src/streamlit_app.py",
            "--server.address", "127.0.0.1",
            "--server.port", "8501",
            "--server.headless", "true"
        ) `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput "data\logs\app.out.log" `
        -RedirectStandardError "data\logs\app.err.log" `
        -WindowStyle Hidden `
        -PassThru
    Set-Content -LiteralPath "data\logs\app.pid" -Value $App.Id
}

$AppReady = $false
for ($i = 0; $i -lt 30; $i++) {
    if (Test-Url "http://127.0.0.1:8501/_stcore/health") {
        $AppReady = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $AppReady) {
    Get-Content -LiteralPath "data\logs\app.err.log" -Tail 50
    throw "Streamlit failed to start. Send the log above to Codex."
}

Write-Host ""
Write-Host "Demo started: http://127.0.0.1:8501" -ForegroundColor Green
Write-Host "Stop it with: .\scripts\stop_demo.cmd"
Start-Process "http://127.0.0.1:8501"
