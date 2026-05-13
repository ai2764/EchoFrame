param(
    [string]$OutputDir = "dist/EchoFramePortable",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "../..")

if ([System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutPath = $OutputDir
}
else {
    $OutPath = Join-Path $RepoRoot $OutputDir
}

if (Test-Path $OutPath) {
    if (-not $Clean) {
        throw "Output already exists: $OutPath. Re-run with -Clean to replace it."
    }
    Remove-Item -LiteralPath $OutPath -Recurse -Force
}

$AppRoot = Join-Path $OutPath "EchoFrame"
$ConfigDir = Join-Path $OutPath "config"

New-Item -ItemType Directory -Force -Path $AppRoot | Out-Null
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
foreach ($dir in @(
    "data",
    "models",
    "runtime-archives",
    "runtime/app-python",
    "runtime/cosyvoice-python",
    "runtime/musetalk-python",
    "runtime/comfyui-python",
    "runtime/ffmpeg",
    "engines/cosyvoice",
    "engines/musetalk",
    "engines/comfyui"
)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $OutPath $dir) | Out-Null
}

foreach ($dir in @("app", "static", "tools", "assets")) {
    Copy-Item -LiteralPath (Join-Path $RepoRoot $dir) -Destination (Join-Path $AppRoot $dir) -Recurse -Force
}
Get-ChildItem -LiteralPath $AppRoot -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force

foreach ($file in @(
    "pyproject.toml",
    "README.md",
    "bootstrap_stack.ps1",
    "bootstrap_stack.bat",
    "restart_stack.ps1",
    "restart_stack.bat",
    "restart_app.ps1",
    "restart_app.bat",
    "kill_stack.ps1",
    "kill_stack.bat",
    "kill_app.ps1",
    "kill_app.bat"
)) {
    Copy-Item -LiteralPath (Join-Path $RepoRoot $file) -Destination (Join-Path $AppRoot $file) -Force
}

foreach ($file in @("start.ps1", "EchoFrame-FirstRun.ps1", "EchoFrame-Start.ps1", "EchoFrame-Stop.ps1")) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination (Join-Path $OutPath $file) -Force
}

foreach ($file in @("portable.env.example", "service-manifest.json", "model-manifest.json")) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination (Join-Path $ConfigDir $file) -Force
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README.md") -Destination (Join-Path $OutPath "README-WindowsPortable.md") -Force

Write-Output "Created portable package skeleton: $OutPath"
Write-Output "Next: add prepared runtimes under runtime/ and engines/, then run start.ps1."
