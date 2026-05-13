# EchoFrame Windows Portable

This folder defines the Windows portable release shape. The portable package owns runtime dependencies, but it still does not bundle model weights.

## Package Layout

```text
EchoFramePortable/
  EchoFrame/
    app/
    static/
    tools/
    assets/
    pyproject.toml
  runtime/
    app-python/
    cosyvoice-python/
    musetalk-python/
    comfyui-python/
    ffmpeg/
  engines/
    cosyvoice/
    musetalk/
    comfyui/
  models/
  data/
  config/
    .env
    service-manifest.json
    model-manifest.json
  EchoFrame-FirstRun.ps1
  EchoFrame-Start.ps1
  EchoFrame-Stop.ps1
```

## Policy

- Heavy Python/CUDA dependencies belong to the portable package, not to repo users.
- Model weights are downloaded on first run into package-relative `models/`.
- Each heavy module keeps its own environment to avoid dependency conflicts.
- The launcher writes `.env` from `portable.env.example`, then runs service health checks.
- LM Studio is not pinned to a model by default. EchoFrame uses whichever LLM is currently loaded in LM Studio; `LLM_MODEL` is only an optional override.

## Suggested Runtime Strategy

- Use `conda-pack`, `micromamba`, or prebuilt venv archives per module.
- Keep separate envs for app, CosyVoice, MuseTalk, and ComfyUI.
- Bundle ffmpeg/ffprobe.
- Start services through PowerShell launcher scripts.
- Use `python -m app.bootstrap --download --health` only after `MODEL_DOWNLOADS_ENABLED=true` is written in portable config.
- Wan2.2 I2V defaults to the official ComfyUI 14B I2V template with the high/low 4-step LightX2V LoRA files under `models/comfyui/loras/`. Keep portable builds on `WAN_PROFILE=wan22_14b_i2v` for current talking-head output; `wan22_5b_ti2v` is experimental and has shown visible color banding/artifacts in EchoFrame tests.

## Build Skeleton

From the repo root:

```powershell
.\packaging\windows\New-PortablePackage.ps1 -OutputDir dist\EchoFramePortable
```

The script copies only lightweight app code/assets into `EchoFrame/`, creates empty `runtime/`, `engines/`, `models/`, `data/`, and `config/` folders, and places the user-facing launchers at the package root. Prepared runtime archives are added after this step by the release builder.

## First Run

1. Check NVIDIA driver via `nvidia-smi`.
2. Check free disk space.
3. Use package `models/` unless a package-relative model directory is provided.
4. Write config `.env` with paths relative to `EchoFrame/`.
5. Download missing model groups.
6. Start services.
7. Run health check and open EchoFrame UI.

The scripts in this folder are scaffolding for release packaging. They intentionally avoid machine-specific paths.

`EchoFrame-FirstRun.ps1` writes `config/.env` with package-relative paths such as `../runtime/...`, `../engines/...`, and `../models/...`, then launches the app with `ECHOFRAME_ENV_FILE=../config/.env`. This keeps portable user config outside the repo-style app folder without baking one machine's install path into the package.
