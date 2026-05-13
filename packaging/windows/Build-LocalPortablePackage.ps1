param(
    [string]$OutputDir = "dist/EchoFramePortable",
    [switch]$Clean,
    [string]$AppPythonSource = "$env:APPDATA\uv\python\cpython-3.12.9-windows-x86_64-none",
    [string]$CosyVoiceEnvPrefix = "$env:USERPROFILE\anaconda3\envs\cosyvoice",
    [string]$MuseTalkEnvPrefix = "$env:USERPROFILE\anaconda3\envs\musetalk",
    [string]$ComfyPythonBase = "$env:APPDATA\uv\python\cpython-3.12.9-windows-x86_64-none",
    [string]$ComfyVenv = "$env:USERPROFILE\Desktop\GEN-ART\ComfyUI\.venv",
    [string]$CosyVoiceRoot = "",
    [string]$MuseTalkRoot = "",
    [string]$ComfySourceRoot = "$env:LOCALAPPDATA\Programs\ComfyUI\resources\ComfyUI",
    [string]$ComfyUserRoot = "",
    [string]$FfmpegDir = "",
    [string[]]$ComfyCustomNodeNames = @("comfyui-kjnodes", "comfyui-videohelpersuite")
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "../..")
$CondaPack = Join-Path $env:USERPROFILE "anaconda3\Scripts\conda-pack.exe"

if ([System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutPath = [System.IO.Path]::GetFullPath($OutputDir)
}
else {
    $OutPath = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDir))
}

function Assert-PathExists {
    param([string]$Path, [string]$Label)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label was not found: $Path"
    }
}

function Get-DotEnvValue {
    param([string]$Name)
    $path = Join-Path $RepoRoot ".env"
    if (-not (Test-Path -LiteralPath $path)) {
        return ""
    }
    foreach ($line in Get-Content -LiteralPath $path) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) {
            continue
        }
        $parts = $trimmed.Split("=", 2)
        if ($parts.Count -eq 2 -and $parts[0].Trim() -eq $Name) {
            return $parts[1].Trim()
        }
    }
    return ""
}

function Assert-Inside {
    param([string]$Base, [string]$Path)
    $baseFull = [System.IO.Path]::GetFullPath($Base).TrimEnd("\") + "\"
    $pathFull = [System.IO.Path]::GetFullPath($Path)
    if (-not $pathFull.StartsWith($baseFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to write outside ${baseFull}: $pathFull"
    }
}

function Invoke-Robocopy {
    param(
        [string]$Source,
        [string]$Destination,
        [string[]]$ExcludeDirs = @(),
        [string[]]$ExcludeFiles = @()
    )
    Assert-PathExists -Path $Source -Label "Source"
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $args = @($Source, $Destination, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:2", "/W:2")
    if ($ExcludeDirs.Count) {
        $args += "/XD"
        $args += $ExcludeDirs
    }
    if ($ExcludeFiles.Count) {
        $args += "/XF"
        $args += $ExcludeFiles
    }
    & robocopy @args | Out-Host
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed from $Source to $Destination with exit code $LASTEXITCODE"
    }
}

function New-ZipFromDirectory {
    param([string]$Source, [string]$Archive)
    if (Test-Path -LiteralPath $Archive) {
        Remove-Item -LiteralPath $Archive -Force
    }
    Push-Location $Source
    try {
        & tar.exe -a -cf $Archive .
        if ($LASTEXITCODE -ne 0) {
            throw "tar failed while creating $Archive"
        }
    }
    finally {
        Pop-Location
    }
}

function New-CondaRuntimeArchive {
    param([string]$Prefix, [string]$Archive)
    Assert-PathExists -Path $Prefix -Label "Conda environment"
    Assert-PathExists -Path $CondaPack -Label "conda-pack"
    if (Test-Path -LiteralPath $Archive) {
        Remove-Item -LiteralPath $Archive -Force
    }
    & $CondaPack -p $Prefix -o $Archive --format zip --force --ignore-missing-files --ignore-editable-packages --compress-level 4 `
        --exclude "Scripts/pip-script.py" `
        --exclude "Scripts/pip3-script.py" `
        --exclude "Scripts/pip3.10-script.py"
    if ($LASTEXITCODE -ne 0) {
        throw "conda-pack failed for $Prefix"
    }
}

if (-not $CosyVoiceRoot) {
    $CosyVoiceRoot = Get-DotEnvValue "TTS_ROOT"
}
if (-not $MuseTalkRoot) {
    $MuseTalkRoot = Get-DotEnvValue "MUSETALK_ROOT"
}
if (-not $FfmpegDir) {
    $FfmpegDir = Get-DotEnvValue "MUSETALK_FFMPEG_DIR"
}
if (-not $ComfyUserRoot) {
    $comfyInput = Get-DotEnvValue "COMFY_INPUT_DIR"
    if ($comfyInput) {
        $ComfyUserRoot = Split-Path -Parent $comfyInput
    }
    else {
        $ComfyUserRoot = Join-Path $env:USERPROFILE "Desktop\GEN-ART\ComfyUI"
    }
}

foreach ($required in @(
    @{ Path = $AppPythonSource; Label = "App Python source" },
    @{ Path = $CosyVoiceEnvPrefix; Label = "CosyVoice conda environment" },
    @{ Path = $MuseTalkEnvPrefix; Label = "MuseTalk conda environment" },
    @{ Path = $ComfyPythonBase; Label = "ComfyUI Python base" },
    @{ Path = $ComfyVenv; Label = "ComfyUI venv" },
    @{ Path = $CosyVoiceRoot; Label = "CosyVoice source root" },
    @{ Path = $MuseTalkRoot; Label = "MuseTalk source root" },
    @{ Path = $ComfySourceRoot; Label = "ComfyUI source root" },
    @{ Path = $FfmpegDir; Label = "ffmpeg directory" }
)) {
    Assert-PathExists -Path $required.Path -Label $required.Label
}

& (Join-Path $PSScriptRoot "New-PortablePackage.ps1") -OutputDir $OutputDir -Clean:$Clean

$ArchiveDir = Join-Path $OutPath "runtime-archives"
$StageDir = Join-Path $OutPath "build-staging"
Assert-Inside -Base $OutPath -Path $ArchiveDir
Assert-Inside -Base $OutPath -Path $StageDir
New-Item -ItemType Directory -Force -Path $ArchiveDir | Out-Null
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

Write-Output "Preparing app Python runtime..."
$AppPythonTarget = Join-Path $OutPath "runtime/app-python"
Invoke-Robocopy -Source $AppPythonSource -Destination $AppPythonTarget -ExcludeDirs @("__pycache__")
& (Join-Path $AppPythonTarget "python.exe") -m pip install --upgrade --break-system-packages --no-warn-script-location fastapi uvicorn httpx pydantic-settings python-multipart Pillow huggingface_hub
if ($LASTEXITCODE -ne 0) {
    throw "Installing app Python dependencies failed"
}

Write-Output "Packing CosyVoice Python runtime..."
New-CondaRuntimeArchive -Prefix $CosyVoiceEnvPrefix -Archive (Join-Path $ArchiveDir "cosyvoice-python.zip")

Write-Output "Packing MuseTalk Python runtime..."
New-CondaRuntimeArchive -Prefix $MuseTalkEnvPrefix -Archive (Join-Path $ArchiveDir "musetalk-python.zip")

Write-Output "Packing ComfyUI Python runtime..."
$ComfyStage = Join-Path $StageDir "comfyui-python"
Assert-Inside -Base $OutPath -Path $ComfyStage
if (Test-Path -LiteralPath $ComfyStage) {
    Remove-Item -LiteralPath $ComfyStage -Recurse -Force
}
Invoke-Robocopy -Source $ComfyPythonBase -Destination $ComfyStage -ExcludeDirs @("__pycache__")
Invoke-Robocopy -Source (Join-Path $ComfyVenv "Lib/site-packages") -Destination (Join-Path $ComfyStage "Lib/site-packages") -ExcludeDirs @("__pycache__")
New-ZipFromDirectory -Source $ComfyStage -Archive (Join-Path $ArchiveDir "comfyui-python.zip")
Remove-Item -LiteralPath $ComfyStage -Recurse -Force

Write-Output "Copying engines..."
Invoke-Robocopy -Source $CosyVoiceRoot -Destination (Join-Path $OutPath "engines/cosyvoice") -ExcludeDirs @(
    ".git", ".pytest_cache", ".venv", "__pycache__", "data", "logs", "pretrained_models", "tmp_data"
)
Invoke-Robocopy -Source $MuseTalkRoot -Destination (Join-Path $OutPath "engines/musetalk") -ExcludeDirs @(
    ".git", ".echoframe", "__pycache__", "data", "models", "results"
)
Invoke-Robocopy -Source $ComfySourceRoot -Destination (Join-Path $OutPath "engines/comfyui") -ExcludeDirs @(
    ".git", "__pycache__", "input", "models", "output", "temp", "tests", "tests-unit", "user"
)
foreach ($node in $ComfyCustomNodeNames) {
    $source = Join-Path $ComfyUserRoot "custom_nodes/$node"
    if (Test-Path -LiteralPath $source) {
        Invoke-Robocopy -Source $source -Destination (Join-Path $OutPath "engines/comfyui/custom_nodes/$node") -ExcludeDirs @(
            ".git", "__pycache__", "tests", "test", "example", "examples"
        )
    }
    else {
        Write-Warning "ComfyUI custom node was not found and was skipped: $node"
    }
}
foreach ($dir in @("input", "output", "user", "models")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $OutPath "engines/comfyui/$dir") | Out-Null
}

Write-Output "Copying ffmpeg..."
foreach ($file in @("ffmpeg.exe", "ffprobe.exe")) {
    Copy-Item -LiteralPath (Join-Path $FfmpegDir $file) -Destination (Join-Path $OutPath "runtime/ffmpeg/$file") -Force
}

Remove-Item -LiteralPath $StageDir -Recurse -Force
Write-Output "Built local portable package: $OutPath"
Write-Output "First run will extract runtime archives, then download models into the package."
