param(
    [int]$Port = 0,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Get-EnvValue {
    param(
        [string]$Name,
        [string]$Default = ""
    )
    $envPath = Join-Path $Root ".env"
    if (-not (Test-Path $envPath)) {
        return $Default
    }
    foreach ($line in Get-Content $envPath) {
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

if ($Port -le 0) {
    $Port = [int](Get-EnvValue -Name "APP_PORT" -Default "7860")
}

if (-not $Python) {
    if ($env:APP_PYTHON) {
        $Python = $env:APP_PYTHON
    }
    else {
        $Python = "python"
    }
}

& (Join-Path $Root "kill_app.ps1") -Port $Port
Start-Sleep -Seconds 1

$out = Join-Path $Root "server.log"
$err = Join-Path $Root "server.err"
$process = Start-Process `
    -WindowStyle Hidden `
    -FilePath $Python `
    -ArgumentList @("-m", "app.main") `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $out `
    -RedirectStandardError $err `
    -PassThru

Start-Sleep -Seconds 3

$listener = netstat -ano | Select-String ":$Port" | Where-Object {
    $parts = ($_.Line -split "\s+") | Where-Object { $_ }
    $parts.Count -ge 5 -and $parts[1] -match ":$Port$" -and $parts[3] -eq "LISTENING" -and [int]$parts[4] -eq $process.Id
}

if ($listener) {
    Write-Output "STARTED pid=$($process.Id) port=$Port"
    Write-Output "URL http://127.0.0.1:$Port"
    exit 0
}

if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
    Write-Output "STARTING pid=$($process.Id) port=$Port"
    Write-Output "Check logs: $out and $err"
    exit 0
}

Write-Output "START_FAILED port=$Port"
if (Test-Path $err) {
    Get-Content $err -Tail 40
}
exit 1
