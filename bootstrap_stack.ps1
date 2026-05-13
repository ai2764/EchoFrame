param(
    [switch]$Health
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:APP_PYTHON) { $env:APP_PYTHON } else { "python" }

Push-Location $Root
try {
    $argsList = @("-m", "app.bootstrap", "--download")
    if ($Health) {
        $argsList += "--health"
    }
    & $Python @argsList
}
finally {
    Pop-Location
}
