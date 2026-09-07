[CmdletBinding()]
param(
    [ValidateSet("local", "sandbox")]
    [string]$ApiTarget = "local",

    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,

    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 8080,

    [string]$FlutterDevice = "web-server"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot "frontend"
$localApiBaseUrl = "http://127.0.0.1:$BackendPort/api/v1"
$sandboxApiBaseUrl = "https://avenqo-platform-sandbox.up.railway.app/api/v1"
$apiBaseUrl = if ($ApiTarget -eq "sandbox") { $sandboxApiBaseUrl } else { $localApiBaseUrl }
$healthUrl = "$apiBaseUrl/health"
$frontendUrl = "http://127.0.0.1:$FrontendPort"
$backendProcess = $null

function Test-HttpReady {
    param([Parameter(Mandatory)][string]$Uri)

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

function Test-PortInUse {
    param([Parameter(Mandatory)][int]$Port)

    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) {
    $venvPython
}
else {
    (Get-Command python -ErrorAction Stop).Source
}
$flutter = (Get-Command flutter -ErrorAction Stop).Source

if ($ApiTarget -eq "sandbox") {
    Write-Host "Checking Avenqo sandbox API at $apiBaseUrl"
    if (-not (Test-HttpReady -Uri $healthUrl)) {
        throw "The Avenqo sandbox API is not healthy at $healthUrl."
    }
    Write-Host "Avenqo sandbox API is ready."
}
else {
    if (Test-PortInUse -Port $BackendPort) {
        if (-not (Test-HttpReady -Uri $healthUrl)) {
            throw "Port $BackendPort is occupied, but the Avenqo API is not healthy at $healthUrl."
        }
        Write-Host "Avenqo API already running at $apiBaseUrl"
    }
    else {
        Write-Host "Starting Avenqo API at $apiBaseUrl"
        $backendArguments = @(
            "-m", "uvicorn", "backend.main:app",
            "--reload", "--reload-dir", "backend",
            "--host", "127.0.0.1", "--port", $BackendPort
        )
        $backendProcess = Start-Process -FilePath $python -ArgumentList $backendArguments `
            -WorkingDirectory $repoRoot -NoNewWindow -PassThru

        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        while (-not (Test-HttpReady -Uri $healthUrl)) {
            if ($backendProcess.HasExited) {
                throw "The Avenqo API stopped during startup with exit code $($backendProcess.ExitCode)."
            }
            if ([DateTime]::UtcNow -ge $deadline) {
                throw "The Avenqo API did not become ready within 30 seconds."
            }
            [Threading.Thread]::Sleep(250)
        }
        Write-Host "Avenqo API is ready."
    }
}

if (Test-PortInUse -Port $FrontendPort) {
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id
    }
    throw "Port $FrontendPort is already in use. Open $frontendUrl or stop the existing frontend first."
}

Write-Host "Starting Avenqo at $frontendUrl"
try {
    Push-Location $frontendRoot
    $flutterArguments = @(
        "run", "-d", $FlutterDevice,
        "--web-hostname", "127.0.0.1",
        "--web-port", $FrontendPort,
        "--dart-define=API_BASE_URL=$apiBaseUrl"
    )
    & $flutter @flutterArguments
}
finally {
    Pop-Location
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id
    }
}