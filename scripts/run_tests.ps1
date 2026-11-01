$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" +
    [Environment]::GetEnvironmentVariable("PATH", "Machine")

Write-Host "Running unit tests..." -ForegroundColor Cyan
uv run pytest tests/customer_support -q

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Real LLM HTTP checks are opt-in: uv run python scripts/demo_check.py"
Write-Host "These checks require a running provider and may incur API charges."
