param(
    [string]$ModelDir = "models",
    [switch]$SkipDownload,
    [switch]$NoStart,
    [switch]$KeepRuntimeArchives
)

$ErrorActionPreference = "Stop"
$StartScript = Join-Path $PSScriptRoot "start.ps1"
if (-not (Test-Path $StartScript)) {
    throw "start.ps1 was not found next to EchoFrame-FirstRun.ps1"
}

& $StartScript @PSBoundParameters
exit $LASTEXITCODE
