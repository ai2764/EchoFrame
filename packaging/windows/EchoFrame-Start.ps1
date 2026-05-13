param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = if (Test-Path (Join-Path $PSScriptRoot "EchoFrame")) { $PSScriptRoot } else { Split-Path -Parent $PSScriptRoot }
$AppRoot = Join-Path $Root "EchoFrame"
$ConfigDir = Join-Path $Root "config"
$EnvPath = Join-Path $ConfigDir ".env"
$PortableEnvFile = "../config/.env"
$python = Join-Path $Root "runtime/app-python/python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

function Get-DotEnvValue {
    param(
        [string]$Path,
        [string]$Name,
        [string]$Default = ""
    )
    if (-not (Test-Path $Path)) {
        return $Default
    }
    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) {
            continue
        }
        $parts = $trimmed.Split("=", 2)
        if ($parts.Count -eq 2 -and $parts[0].Trim() -eq $Name) {
            return $parts[1].Trim()
        }
    }
    return $Default
}

if (-not (Test-Path $EnvPath)) {
    throw "Portable config was not found at $EnvPath. Run EchoFrame-FirstRun.ps1 first."
}

Push-Location $AppRoot
try {
    $env:ECHOFRAME_ENV_FILE = $PortableEnvFile
    & .\restart_stack.ps1 -Python $python
    if ($LASTEXITCODE -ne 0) {
        throw "EchoFrame start failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

if (-not $NoBrowser) {
    $port = Get-DotEnvValue -Path $EnvPath -Name "APP_PORT" -Default "7860"
    Start-Process "http://127.0.0.1:$port"
}
