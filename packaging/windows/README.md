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
  runtime-archives/
    cosyvoice-python.zip
    musetalk-python.zip
    comfyui-python.zip
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
  start.ps1
  EchoFrame-FirstRun.ps1
  EchoFrame-Start.ps1
  EchoFrame-Stop.ps1
```

## Policy

- Heavy Python/CUDA dependencies belong to the portable package, not to repo users.
- Model weights are downloaded on first run into package-relative `models/`.
- First run also points Hugging Face and ModelScope caches at `models/.download-cache/`, so downloads do not fall back to the user's system drive.
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

For a local release build on a prepared Windows machine, run:

```powershell
.\packaging\windows\Build-LocalPortablePackage.ps1 -OutputDir dist\EchoFramePortable -Clean
```

That builder copies only release assets into `dist/`, packs CosyVoice and MuseTalk conda envs as first-run archives, builds a portable ComfyUI Python archive, copies ffmpeg, and copies the required engines/custom nodes. It reads local engine paths from `.env` when parameters are not provided. `dist/` is ignored by git.

## Start

`start.ps1` is the user-facing entry point. It is safe to run on first launch and on later launches:

- On first launch it extracts missing runtimes, writes config, downloads missing models, starts services, and opens the UI.
- On later launches it skips already extracted runtimes and already downloaded models, refreshes package-relative config, starts services, and opens the UI.

The startup flow:

1. Check NVIDIA driver via `nvidia-smi`.
2. Check free disk space.
3. Extract bundled runtime archives when their target runtime folders are still empty.
4. Use package `models/` unless a package-relative model directory is provided.
5. Write config `.env` with paths relative to `EchoFrame/`.
6. Download missing model groups into package `models/`.
7. Start services.
8. Run health check and open EchoFrame UI.

The scripts in this folder are scaffolding for release packaging. They intentionally avoid machine-specific paths.

`start.ps1` writes `config/.env` with package-relative paths such as `../runtime/...`, `../engines/...`, and `../models/...`, then launches the app with `ECHOFRAME_ENV_FILE=../config/.env`. This keeps portable user config outside the repo-style app folder without baking one machine's install path into the package. `EchoFrame-FirstRun.ps1` remains as a compatibility wrapper.

## Tester Handoff

The current local test package is created at `dist\EchoFramePortable`. Do not commit or push that folder; hand it to testers as a folder copy or archive outside git.

Minimum tester machine expectations:

- Windows with NVIDIA driver and `nvidia-smi`.
- At least 80-100 GB free disk on the drive that contains `EchoFramePortable`.
- Internet access for first-run model downloads.
- LM Studio installed separately, with an LLM loaded before generating a reply. EchoFrame leaves `LLM_MODEL` empty and uses the loaded model.

Smoke test without downloading models:

```powershell
cd EchoFramePortable
.\start.ps1 -SkipDownload -NoStart
```

This should extract runtimes and write `config\.env`; missing model messages are expected in this mode.

Full tester flow:

```powershell
cd EchoFramePortable
.\start.ps1
```

After first run opens the UI, use a small 320px output test first. Keep `WAN_PROFILE=wan22_14b_i2v`; the 5B profile remains experimental because local tests showed visible image artifacts.
