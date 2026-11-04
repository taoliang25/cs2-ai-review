$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Join-Path $projectRoot "data\runtime"
$statePath = Join-Path $runtimeDir "public_demo.json"
$tunnelOut = Join-Path $runtimeDir "tunnel.stdout.log"
$tunnelErr = Join-Path $runtimeDir "tunnel.stderr.log"
$appOut = Join-Path $runtimeDir "streamlit.stdout.log"
$appErr = Join-Path $runtimeDir "streamlit.stderr.log"
$streamlit = Join-Path $projectRoot ".venv\Scripts\streamlit.exe"

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
Set-Location -LiteralPath $projectRoot

$healthReady = $false
try {
    $health = Invoke-WebRequest -UseBasicParsing `
        -Uri "http://127.0.0.1:8501/_stcore/health" `
        -TimeoutSec 2
    $healthReady = $health.StatusCode -eq 200
} catch {
    $healthReady = $false
}

$streamlitProcess = $null
if (-not $healthReady) {
    $streamlitProcess = Start-Process `
        -FilePath $streamlit `
        -ArgumentList @(
            "run", "app.py",
            "--server.headless=true",
            "--server.port=8501",
            "--browser.gatherUsageStats=false"
        ) `
        -RedirectStandardOutput $appOut `
        -RedirectStandardError $appErr `
        -PassThru `
        -WindowStyle Hidden

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-WebRequest -UseBasicParsing `
                -Uri "http://127.0.0.1:8501/_stcore/health" `
                -TimeoutSec 2
            if ($health.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            $ready = $false
        }
    }
    if (-not $ready) {
        throw "Streamlit did not become ready. See $appErr"
    }
}

$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
if (-not (Test-Path -LiteralPath $ssh)) {
    throw "OpenSSH ssh.exe was not found."
}

$tunnelProcess = Start-Process `
    -FilePath $ssh `
    -ArgumentList @(
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-o", "ExitOnForwardFailure=yes",
        "-R", "80:localhost:8501",
        "serveo.net"
    ) `
    -RedirectStandardOutput $tunnelOut `
    -RedirectStandardError $tunnelErr `
    -PassThru `
    -WindowStyle Hidden

$publicUrl = $null
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 500
    if (Test-Path -LiteralPath $tunnelOut) {
        $match = Select-String `
            -LiteralPath $tunnelOut `
            -Pattern "https://[a-z0-9-]+\.serveousercontent\.com" `
            -AllMatches |
            Select-Object -First 1
        if ($match -and $match.Matches.Count -gt 0) {
            $publicUrl = $match.Matches[0].Value
            break
        }
    }
}

if (-not $publicUrl) {
    Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
    throw "Public tunnel URL was not received. See $tunnelOut and $tunnelErr"
}

$state = @{
    public_url = $publicUrl
    tunnel_pid = $tunnelProcess.Id
    streamlit_pid = if ($streamlitProcess) { $streamlitProcess.Id } else { $null }
    started_at = (Get-Date).ToString("o")
}
$state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8

Write-Host ""
Write-Host "Public URL: $publicUrl"
Write-Host "Access code: see APP_ACCESS_CODE in .env"
Write-Host "Keep this computer awake and connected."
Write-Host "Run .\stop_public_demo.ps1 to close the public service."

