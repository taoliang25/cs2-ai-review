$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$streamlit = Join-Path $projectRoot ".venv\Scripts\streamlit.exe"
$app = Join-Path $projectRoot "app.py"
$appUrl = "http://localhost:8501"
$healthUrl = "$appUrl/_stcore/health"

function Test-AppHealth {
    try {
        $status = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        return $status -eq "ok"
    }
    catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $streamlit)) {
    throw "Project environment not found. Install dependencies as described in README.md."
}

if (-not (Test-AppHealth)) {
    $runtimeDir = Join-Path $projectRoot "data\runtime"
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

    $arguments = @(
        "run",
        $app,
        "--server.headless=true",
        "--server.address=localhost",
        "--server.port=8501",
        "--browser.gatherUsageStats=false"
    )

    Start-Process `
        -FilePath $streamlit `
        -ArgumentList $arguments `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runtimeDir "streamlit.out.log") `
        -RedirectStandardError (Join-Path $runtimeDir "streamlit.err.log") | Out-Null

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (Test-AppHealth) {
            $ready = $true
            break
        }
    }

    if (-not $ready) {
        throw "The app did not start within 15 seconds. Check data\runtime\streamlit.err.log."
    }
}

Start-Process $appUrl
