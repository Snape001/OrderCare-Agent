$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" +
    [Environment]::GetEnvironmentVariable("PATH", "Machine")
$env:PYTHONUTF8 = "1"

Write-Host "Evaluating lexical, dense, and hybrid RAG retrieval..." -ForegroundColor Cyan
uv run --frozen python scripts/evaluate_rag.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Detailed report: data\evaluation\rag\runs\<run-id>\summary.md" -ForegroundColor Green
