$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$streamlit = Join-Path $projectRoot ".venv\Scripts\streamlit.exe"
$app = Join-Path $projectRoot "app.py"

if (-not (Test-Path -LiteralPath $streamlit)) {
    throw "Project environment not found. Run the setup commands in README.md first."
}

Set-Location -LiteralPath $projectRoot
& $streamlit run $app --server.headless=true --browser.gatherUsageStats=false

