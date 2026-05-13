# EchoFrame

EchoFrame is a local conversational digital-human orchestrator:

```text
avatar image -> LLM reply plan -> TTS audio -> base video -> lip sync -> MP4
```

The repository is intentionally lightweight. It contains the EchoFrame UI/API, workflow code, service health checks, and small voice reference presets. It does not install or vendor heavy AI runtimes for pull-repo users.

## Two Distributions

**Repo profile**

- Default `APP_PROFILE=repo`.
- EchoFrame checks external services and calls them through configured URLs/paths.
- It does not resolve CUDA, torch, ComfyUI, MuseTalk, CosyVoice, or model dependencies.
- `MODEL_DOWNLOADS_ENABLED=false` by default.

**Windows portable profile**

- Release package that ships prepared runtimes, engines, ffmpeg, and launch scripts.
- Model weights are still not bundled in git or in the initial portable folder.
- First run checks GPU/disk, extracts runtime archives, downloads required models into package-relative `models/`, writes config, starts services, then runs health checks.
- Build the portable package skeleton with `.\packaging\windows\New-PortablePackage.ps1`; build the local release package with `.\packaging\windows\Build-LocalPortablePackage.ps1`.
- See [packaging/windows/README.md](packaging/windows/README.md).

## Default Services

| Service | Default | Required For | Config |
|---|---:|---|---|
| EchoFrame UI/API | `7860` | browser UI and API | `APP_HOST`, `APP_PORT` |
| LM Studio | `1234` | LLM reply planning | `LLM_BASE_URL`; `LLM_MODEL` is optional |
| CosyVoice HTTP | `9880` | speech synthesis in repo profile | `TTS_BACKEND`, `TTS_URL` |
| ComfyUI | `8000` | `wan_loop` and `wan` modes | `COMFY_URL`, `COMFY_ROOT` |
| MuseTalk | on-demand process | final lip sync | `MUSETALK_ROOT`, `MUSETALK_PYTHON` |
| ffmpeg | `PATH` | probing/trim/encoding | `FFMPEG_BIN`, `FFPROBE_BIN` |

Run this to print the machine-readable service manifest:

```powershell
python -m app.stack_control manifest
```

EchoFrame also checks services at app startup and writes a snapshot to `data/logs/startup_health.json`.

## Configuration

Copy `.env.example` to `.env` and adjust it locally. Do not commit `.env`.

Portable builds keep user config at `config/.env` and launch EchoFrame with `ECHOFRAME_ENV_FILE` pointing to that file. Repo users normally do not need this variable.

The repo profile expects you to run external services yourself:

- LM Studio OpenAI-compatible API at `LLM_BASE_URL`.
- A CosyVoice-compatible HTTP service at `TTS_URL`, unless you explicitly set `TTS_BACKEND=native`.
- ComfyUI with the required Wan2.2 workflow nodes and models.
- A MuseTalk checkout/environment for on-demand lip sync.
- ffmpeg/ffprobe on PATH or configured through `FFMPEG_BIN` and `FFPROBE_BIN`.

Native CosyVoice support remains in the code for portable builds or advanced local setups. It uses `tools/native_cosyvoice_tts.py`, `TTS_ROOT`, `TTS_PYTHON`, and `TTS_PRESETS_FILE`, but repo users are not expected to make EchoFrame solve those dependencies.

## Voice Presets

The repo includes small CosyVoice zero-shot reference clips under `assets/voices/`. Current defaults are English-friendly:

- `TTS_FEMALE_VOICE_ID=d36d10b9`
- `TTS_MALE_VOICE_ID=c715d869`

These are reference audio files, not model weights. Replace `assets/voices/presets.json` or point `TTS_PRESETS_FILE` elsewhere if you want different voices.

## No Models In Git

EchoFrame does not store model weights in this repository. The repo ignores:

- `engines/`
- `models/`
- `pretrained_models/`
- common model weights such as `.safetensors`, `.gguf`, `.pth`, `.pt`, `.ckpt`, `.bin`
- generated media such as `.mp4`, `.wav`, `.mp3`

The only committed wav files are the small reference clips in `assets/voices/`.

## Daily Run

Start the lightweight UI/API and run health checks:

```powershell
.\restart_stack.ps1
```

Check services without generating media:

```powershell
python -m app.stack_control status lm_studio cosyvoice comfyui musetalk ffmpeg gpu
```

Check model/service manifests without downloading:

```powershell
python -m app.bootstrap --health
```

`bootstrap_stack.ps1 -Download` is disabled in repo profile unless you set `MODEL_DOWNLOADS_ENABLED=true`. Model downloads belong to the portable first-run flow by default.

## API

- `GET /api/service-manifest`
- `GET /api/startup-health`
- `GET /api/services`
- `POST /api/services/{name}/start`
- `POST /api/services/{name}/stop`
- `POST /api/services/{name}/restart`
- `GET /api/services/{name}/logs`

`fast` mode does not require ComfyUI. `wan_loop` and `wan` require ComfyUI.

## Model Lifecycle

- EchoFrame uses the LLM currently loaded in LM Studio. Leave `LLM_MODEL` empty for this default behavior; set it only as an explicit override.
- Repo profile uses external TTS by default.
- Portable profile can use native CosyVoice worker.
- Wan I2V defaults to the official ComfyUI Wan2.2 14B I2V graph with the 4-step LightX2V LoRA enabled. `WAN_PROFILE=wan22_5b_ti2v` is kept as an experimental benchmark profile only; current EchoFrame talking-head tests showed visible color banding/artifacts, so it is not recommended for production output.
- Wan generation calls ComfyUI `/free` after use when `COMFY_UNLOAD_AFTER_WAN=true`.
- MuseTalk runs as an on-demand child process for each lip-sync job.
