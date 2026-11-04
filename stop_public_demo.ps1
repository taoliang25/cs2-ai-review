$ErrorActionPreference = "SilentlyContinue"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$statePath = Join-Path $projectRoot "data\runtime\public_demo.json"

if (-not (Test-Path -LiteralPath $statePath)) {
    Write-Host "No public demo state file was found."
    exit 0
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if ($state.tunnel_pid) {
    Stop-Process -Id ([int]$state.tunnel_pid) -Force
}
if ($state.streamlit_pid) {
    Stop-Process -Id ([int]$state.streamlit_pid) -Force
}
Remove-Item -LiteralPath $statePath -Force
if ($state.streamlit_pid) {
    Write-Host "Public tunnel and project-owned Streamlit process were stopped."
} else {
    Write-Host "Public tunnel was stopped. The already-running local Streamlit server was left running."
}

