param(
    [switch]$All,
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
    if ($All) {
        & $Python -m app.stack_control start lm_studio cosyvoice comfyui
    }
    & (Join-Path $Root "restart_app.ps1") -Port $Port -Python $Python
    & $Python -m app.stack_control status lm_studio cosyvoice comfyui musetalk ffmpeg gpu
}
finally {
    Pop-Location
}
