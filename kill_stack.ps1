param(
    [switch]$UnloadLlm,
    [int]$Port = 0,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Python) {
    $Python = if ($env:APP_PYTHON) { $env:APP_PYTHON } else { "python" }
}

Push-Location $Root
try {
    & (Join-Path $Root "kill_app.ps1") -Port $Port
    & $Python -m app.stack_control stop cosyvoice comfyui
    if ($UnloadLlm) {
        & $Python -m app.stack_control stop lm_studio
    }
}
finally {
    Pop-Location
}
