$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" +
    [Environment]::GetEnvironmentVariable("PATH", "Machine")

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv was not found. Run: winget install --id astral-sh.uv -e"
}

Write-Host "[1/4] Installing the project Python and dependencies..." -ForegroundColor Cyan
uv python install 3.12
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv sync --frozen --python 3.12
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/4] Checking the real LLM configuration..." -ForegroundColor Cyan
if (-not (Test-Path ".env")) {
    throw "Create .env from .env.ollama.example, .env.qwen.example or .env.deepseek.example first."
}

$env:PYTHONPATH = "src"
uv run python -c "from core import settings; print('Customer support provider:', settings.CUSTOMER_SUPPORT_MODE)"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[3/4] Initializing the sample order database..." -ForegroundColor Cyan
uv run python -c "from customer_support.store import initialize_database; print(initialize_database())"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[4/4] Initializing BGE and building the current policy RAG index..." -ForegroundColor Cyan
Write-Host "The first run downloads a Chinese embedding model of about 90 MB."
uv run python scripts/build_rag_index.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Setup complete. Next run: .\scripts\start_demo.cmd" -ForegroundColor Green
