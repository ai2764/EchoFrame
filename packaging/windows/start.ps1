param(
    [string]$ModelDir = "models",
    [switch]$SkipDownload,
    [switch]$NoStart,
    [switch]$KeepRuntimeArchives
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

function Expand-RuntimeArchive {
    param(
        [string]$ArchiveName,
        [string]$TargetRelativePath,
        [string]$ExpectedRelativePath,
        [switch]$Conda
    )
    $target = Resolve-PackagePath $TargetRelativePath
    $expected = Resolve-PackagePath $ExpectedRelativePath
    $archive = Join-Path $Root "runtime-archives/$ArchiveName.zip"
    if (-not (Test-Path $expected)) {
        if (-not (Test-Path $archive)) {
            throw "Runtime archive is missing: $archive"
        }
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        & tar.exe -xf $archive -C $target
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to extract runtime archive: $archive"
        }
    }
    if ($Conda) {
        $unpack = Join-Path $target "Scripts/conda-unpack.exe"
        if (Test-Path $unpack) {
            & $unpack
            if ($LASTEXITCODE -ne 0) {
                throw "conda-unpack failed for $TargetRelativePath"
            }
        }
    }
    if (-not $KeepRuntimeArchives -and (Test-Path $expected) -and (Test-Path $archive)) {
        Remove-Item -LiteralPath $archive -Force
    }
}

New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

Expand-RuntimeArchive -ArchiveName "app-python" -TargetRelativePath "runtime/app-python" -ExpectedRelativePath "runtime/app-python/python.exe"
Expand-RuntimeArchive -ArchiveName "cosyvoice-python" -TargetRelativePath "runtime/cosyvoice-python" -ExpectedRelativePath "runtime/cosyvoice-python/python.exe" -Conda
Expand-RuntimeArchive -ArchiveName "musetalk-python" -TargetRelativePath "runtime/musetalk-python" -ExpectedRelativePath "runtime/musetalk-python/python.exe" -Conda
Expand-RuntimeArchive -ArchiveName "comfyui-python" -TargetRelativePath "runtime/comfyui-python" -ExpectedRelativePath "runtime/comfyui-python/python.exe"

$ModelDirRel = ($ModelDir -replace "\\", "/").Trim("/")
if (-not $ModelDirRel) {
    $ModelDirRel = "models"
}
$ModelDirPath = Resolve-PackagePath $ModelDirRel
New-Item -ItemType Directory -Force -Path $ModelDirPath | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ModelDirPath "comfyui") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ModelDirPath "cosyvoice") | Out-Null

$ComfyExtraModelPaths = Join-Path $Root "engines/comfyui/extra_model_paths.yaml"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ComfyExtraModelPaths) | Out-Null
@"
echoframe:
    base_path: ../../models/comfyui
    diffusion_models: diffusion_models
    text_encoders: text_encoders
    vae: vae
    loras: loras
"@ | Set-Content -Path $ComfyExtraModelPaths -Encoding utf8

$DownloadCacheDir = Join-Path $ModelDirPath ".download-cache"
$HfCacheDir = Join-Path $DownloadCacheDir "huggingface"
$ModelScopeCacheDir = Join-Path $DownloadCacheDir "modelscope"
New-Item -ItemType Directory -Force -Path $HfCacheDir | Out-Null
New-Item -ItemType Directory -Force -Path $ModelScopeCacheDir | Out-Null
$env:HF_HOME = $HfCacheDir
$env:HF_HUB_CACHE = Join-Path $HfCacheDir "hub"
$env:HUGGINGFACE_HUB_CACHE = $env:HF_HUB_CACHE
$env:MODELSCOPE_CACHE = $ModelScopeCacheDir
$env:MODELSCOPE_HOME = $ModelScopeCacheDir

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
Set-DotEnvValue -Path $EnvPath -Name "TTS_ZH_FEMALE_VOICE_ID" -Value "4988cee6"
Set-DotEnvValue -Path $EnvPath -Name "TTS_ZH_MALE_VOICE_ID" -Value "21897fae"
Set-DotEnvValue -Path $EnvPath -Name "TTS_EN_FEMALE_VOICE_ID" -Value "d36d10b9"
Set-DotEnvValue -Path $EnvPath -Name "TTS_EN_MALE_VOICE_ID" -Value "c715d869"
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
