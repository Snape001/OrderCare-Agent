param([switch]$CollectOnly)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$ProjectPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $ProjectPython)) {
    throw "Missing .venv. Install Python 3.12 and run: uv sync --frozen --python 3.12"
}
& $ProjectPython -c "import sys; assert (3, 12) <= sys.version_info[:2] < (3, 15), 'Python 3.12-3.14 required'"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($CollectOnly) {
    & $ProjectPython -m pytest --collect-only -q -p no:cacheprovider
    exit $LASTEXITCODE
}

New-Item -ItemType Directory -Path "reports" -Force | Out-Null
& $ProjectPython -m pytest -q -ra -p no:cacheprovider --junitxml=reports/phase1-tests.xml
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Deterministic evaluation only. Never select a paid model or enable tracing here.
$EvaluationEnvironment = @{
    USE_FAKE_MODEL = "true"
    DEFAULT_MODEL = "fake"
    CUSTOMER_SUPPORT_MODE = "mock"
    LANGFUSE_TRACING = "false"
    LANGCHAIN_TRACING_V2 = "false"
    LANGSMITH_TRACING = "false"
}
$PreviousEnvironment = @{}
foreach ($Key in $EvaluationEnvironment.Keys) {
    $PreviousEnvironment[$Key] = [Environment]::GetEnvironmentVariable($Key, "Process")
    [Environment]::SetEnvironmentVariable($Key, $EvaluationEnvironment[$Key], "Process")
}
try {
    & $ProjectPython scripts/evaluate_agent.py --report reports/phase1-agent.json
    $EvaluationExitCode = $LASTEXITCODE
}
finally {
    foreach ($Key in $EvaluationEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($Key, $PreviousEnvironment[$Key], "Process")
    }
}
exit $EvaluationExitCode
