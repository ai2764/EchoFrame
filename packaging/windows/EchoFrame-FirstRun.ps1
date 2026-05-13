param(
    [string]$ModelDir = "models",
    [switch]$SkipDownload,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$Root = if (Test-Path (Join-Path $PSScriptRoot "EchoFrame")) { $PSScriptRoot } else { Split-Path -Parent $PSScriptRoot }
$AppRoot = Join-Path $Root "EchoFrame"
$ConfigDir = Join-Path $Root "config"
$EnvPath = Join-Path $ConfigDir ".env"
$DataDir = Join-Path $Root "data"
$RuntimeDir = Join-Path $Root "runtime"
$EnginesDir = Join-Path $Root "engines"
$PortableEnvFile = "../config/.env"

function ConvertTo-AppRelativeEnvPath {
    param([string]$PackageRelativePath)
    $clean = ($PackageRelativePath -replace "\\", "/").Trim("/")
    if (-not $clean) {
        return "."
    }
    return "../$clean"
}

function Resolve-PackagePath {
    param([string]$PackageRelativePath)
    if ([System.IO.Path]::IsPathRooted($PackageRelativePath)) {
        throw "Use a package-relative path for portable builds, not an absolute path: $PackageRelativePath"
    }
    $clean = ($PackageRelativePath -replace "\\", "/").Trim("/")
    if (($clean -split "/") -contains "..") {
        throw "Portable package paths must stay inside the package: $PackageRelativePath"
    }
    return Join-Path $Root ($clean -replace "/", "\")
}

function Set-DotEnvValue {
    param(
        [string]$Path,
        [string]$Name,
        [string]$Value
    )
    $lines = @()
    if (Test-Path $Path) {
        $lines = @(Get-Content $Path)
    }
    $pattern = "^\s*$([regex]::Escape($Name))\s*="
    $lines = @($lines | Where-Object { $_ -notmatch $pattern })
    $lines += "$Name=$Value"
    Set-Content -Path $Path -Value $lines -Encoding utf8
}

New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

$ModelDirRel = ($ModelDir -replace "\\", "/").Trim("/")
if (-not $ModelDirRel) {
    $ModelDirRel = "models"
}
$ModelDirPath = Resolve-PackagePath $ModelDirRel
New-Item -ItemType Directory -Force -Path $ModelDirPath | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ModelDirPath "comfyui") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ModelDirPath "cosyvoice") | Out-Null

if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    Write-Warning "nvidia-smi was not found. Install NVIDIA drivers before running GPU workflows."
}

$modelDrive = Get-PSDrive -Name ([System.IO.Path]::GetPathRoot((Resolve-Path $ModelDirPath).Path).Substring(0, 1)) -ErrorAction SilentlyContinue
if ($modelDrive -and $modelDrive.Free -lt 50GB) {
    Write-Warning "The selected model drive has less than 50 GB free. Wan and MuseTalk models may need more space."
}

$templateCandidates = @(
    (Join-Path $PSScriptRoot "portable.env.example"),
    (Join-Path $ConfigDir "portable.env.example")
)
$template = $templateCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $template) {
    throw "portable.env.example was not found"
}
Copy-Item -LiteralPath $template -Destination $EnvPath -Force

Set-DotEnvValue -Path $EnvPath -Name "APP_PROFILE" -Value "portable"
Set-DotEnvValue -Path $EnvPath -Name "DATA_DIR" -Value "../data"
Set-DotEnvValue -Path $EnvPath -Name "MODEL_DOWNLOADS_ENABLED" -Value "true"
Set-DotEnvValue -Path $EnvPath -Name "TTS_ROOT" -Value "../engines/cosyvoice"
Set-DotEnvValue -Path $EnvPath -Name "TTS_PYTHON" -Value "../runtime/cosyvoice-python/python.exe"
Set-DotEnvValue -Path $EnvPath -Name "TTS_PRESETS_FILE" -Value "assets/voices/presets.json"
Set-DotEnvValue -Path $EnvPath -Name "TTS_MODEL_DIR" -Value "$(ConvertTo-AppRelativeEnvPath $ModelDirRel)/cosyvoice/CosyVoice2-0.5B"
Set-DotEnvValue -Path $EnvPath -Name "COMFY_ROOT" -Value "../engines/comfyui"
Set-DotEnvValue -Path $EnvPath -Name "COMFY_PYTHON" -Value "../runtime/comfyui-python/python.exe"
Set-DotEnvValue -Path $EnvPath -Name "COMFY_BASE_DIR" -Value "../engines/comfyui"
Set-DotEnvValue -Path $EnvPath -Name "COMFY_INPUT_DIR" -Value "../engines/comfyui/input"
Set-DotEnvValue -Path $EnvPath -Name "COMFY_OUTPUT_DIR" -Value "../engines/comfyui/output"
Set-DotEnvValue -Path $EnvPath -Name "COMFY_MODELS_DIR" -Value "$(ConvertTo-AppRelativeEnvPath $ModelDirRel)/comfyui"
Set-DotEnvValue -Path $EnvPath -Name "MUSETALK_ROOT" -Value "../engines/musetalk"
Set-DotEnvValue -Path $EnvPath -Name "MUSETALK_PYTHON" -Value "../runtime/musetalk-python/python.exe"
Set-DotEnvValue -Path $EnvPath -Name "MUSETALK_FFMPEG_DIR" -Value "../runtime/ffmpeg"
Set-DotEnvValue -Path $EnvPath -Name "FFMPEG_BIN" -Value "../runtime/ffmpeg/ffmpeg.exe"
Set-DotEnvValue -Path $EnvPath -Name "FFPROBE_BIN" -Value "../runtime/ffmpeg/ffprobe.exe"

Push-Location $AppRoot
try {
    $python = Join-Path $Root "runtime/app-python/python.exe"
    if (-not (Test-Path $python)) {
        $python = "python"
    }
    $env:ECHOFRAME_ENV_FILE = $PortableEnvFile
    if (-not $SkipDownload) {
        & $python -m app.bootstrap --download --health
    }
    else {
        & $python -m app.bootstrap --health
    }
    if ($LASTEXITCODE -ne 0) {
        throw "EchoFrame bootstrap failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

if (-not $NoStart) {
    & (Join-Path $Root "EchoFrame-Start.ps1")
}
