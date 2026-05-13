# EchoFrame

EchoFrame is a local conversational digital human stack:

```text
avatar image -> LLM reply plan -> TTS audio -> base video -> lip sync -> MP4
```

The app is organized into four generation modules:

- `llm`: reply text, CosyVoice delivery prompt, and Wan motion prompt.
- `tts`: speech synthesis and audio cleanup.
- `video`: still video, Wan loop, or Wan full base video.
- `lipsync`: MuseTalk lip synchronization.

## Configuration

Copy `.env.example` to `.env` and set your local engine paths there. Do not commit `.env`; it is ignored by git.

Important local paths are configured through environment variables:

- `TTS_ROOT`
- `COMFY_ROOT`
- `COMFY_BASE_DIR`
- `COMFY_INPUT_DIR`
- `COMFY_OUTPUT_DIR`
- `COMFY_MODELS_DIR`
- `MUSETALK_ROOT`
- `MUSETALK_PYTHON`

The committed defaults use generic `engines/...` placeholders so machine-specific paths and secrets stay local.

## No Models In Git

EchoFrame is designed to run locally without storing model weights in the repository. Keep engines and model files in external local folders, then point `.env` to them.

The repository ignores:

- `engines/`
- `models/`
- `pretrained_models/`
- common model weights such as `.safetensors`, `.gguf`, `.pth`, `.pt`, `.ckpt`, `.bin`
- generated media such as `.mp4`, `.wav`, `.mp3`

Use `bootstrap_stack.ps1 -Health` to check whether the local machine has the required models. Use `bootstrap_stack.ps1 -Download` only on a machine with enough disk space.

## Daily Run

Lightweight UI/API start:

```powershell
.\restart_stack.ps1
```

This starts EchoFrame and runs health checks. Heavy services are not started unless you request them from the UI or run the full stack command.

Start every resident service:

```powershell
.\restart_stack.ps1 -All
```

Stop EchoFrame plus resident TTS/ComfyUI services:

```powershell
.\kill_stack.ps1
```

Also unload/stop LM Studio server:

```powershell
.\kill_stack.ps1 -UnloadLlm
```

## Bootstrap

Check required model files without downloading:

```powershell
.\bootstrap_stack.ps1 -Health
```

Download missing model files only when you explicitly request it:

```powershell
.\bootstrap_stack.ps1 -Download -Health
```

Bootstrap is idempotent: it checks the manifest first and downloads only missing model groups. Keep using the check-only command when disk space is tight.

## Low-Disk Script Tests

These commands do not download models or generate media:

```powershell
python -m app.bootstrap
python -m app.stack_control status lm_studio cosyvoice comfyui musetalk ffmpeg gpu
python -m pytest -q
```

Use the lightweight restart command only when you want to test the UI/API process:

```powershell
.\restart_stack.ps1
```

Avoid these until you have enough free space:

```powershell
.\bootstrap_stack.ps1 -Download
.\restart_stack.ps1 -All
```

Managed model groups:

- LM Studio model from `LLM_MODEL`
- CosyVoice2 TTS model
- official ComfyUI Wan2.2 I2V fp8_scaled files
- MuseTalk model files

## Services API

EchoFrame exposes service-control endpoints for the UI:

- `GET /api/services`
- `POST /api/services/{name}/start`
- `POST /api/services/{name}/stop`
- `POST /api/services/{name}/restart`
- `GET /api/services/{name}/logs`

Supported service names:

- `lm_studio`
- `cosyvoice`
- `comfyui`
- `musetalk`
- `ffmpeg`
- `gpu`

`fast` mode does not require ComfyUI. `wan_loop` and `wan` start/check ComfyUI before generating the base video.

## Model Lifecycle

- LLM model loading and unloading is still handled per request by the LM Studio client.
- TTS and ComfyUI can be started or stopped from the UI.
- Wan generation calls ComfyUI `/free` after use when `COMFY_UNLOAD_AFTER_WAN=true`.
- MuseTalk runs as an on-demand child process for each lip-sync job.
