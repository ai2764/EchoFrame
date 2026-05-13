param(
    [int]$Port = 0
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

$pids = @()
$matches = netstat -ano | Select-String ":$Port"
foreach ($match in $matches) {
    $parts = ($match.Line -split "\s+") | Where-Object { $_ }
    if ($parts.Count -ge 5 -and $parts[1] -match ":$Port$" -and $parts[3] -eq "LISTENING") {
        $pids += [int]$parts[4]
    }
}

$pids = $pids | Select-Object -Unique
if (-not $pids -or $pids.Count -eq 0) {
    Write-Output "NO_LISTENER port=$Port"
    exit 0
}

foreach ($pidValue in $pids) {
    try {
        Stop-Process -Id $pidValue -Force
        Write-Output "STOPPED pid=$pidValue port=$Port"
    }
    catch {
        Write-Output "STOP_FAILED pid=$pidValue port=$Port error=$($_.Exception.Message)"
        exit 1
    }
}

