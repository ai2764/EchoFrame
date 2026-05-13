$ErrorActionPreference = "Stop"
$Root = if (Test-Path (Join-Path $PSScriptRoot "EchoFrame")) { $PSScriptRoot } else { Split-Path -Parent $PSScriptRoot }
$AppRoot = Join-Path $Root "EchoFrame"
$EnvPath = Join-Path $Root "config/.env"
$PortableEnvFile = "../config/.env"
$python = Join-Path $Root "runtime/app-python/python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

Push-Location $AppRoot
try {
    if (Test-Path $EnvPath) {
        $env:ECHOFRAME_ENV_FILE = $PortableEnvFile
    }
    & .\kill_stack.ps1 -UnloadLlm -Python $python
    if ($LASTEXITCODE -ne 0) {
        throw "EchoFrame stop failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
