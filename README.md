# EchoFrame

EchoFrame is a local conversational digital-human orchestrator:

```text
avatar image -> LLM reply plan -> TTS audio -> base video -> lip sync -> MP4
```

The UI exposes three generation workflows:

- `LTX IA2V`: LLM/manual text -> CosyVoice TTS -> LTX image+audio-to-video -> MP4.
- `LTX Native A/V`: LLM/manual text -> LTX image-to-video with generated speech audio -> MP4. This skips external TTS and MuseTalk.
- `Wan + MuseTalk`: LLM/manual text -> CosyVoice TTS -> still/Wan base video -> MuseTalk lip sync -> MP4.

The repository is intentionally lightweight. It contains the EchoFrame UI/API, workflow code, service health checks, and small voice reference presets. It does not install or vendor heavy AI runtimes for pull-repo users.

## Sample Outputs

These short clips use the same Xiaomei avatar image and map to the three UI workflows. GIF previews render inline on GitHub; click a preview to open the MP4 with audio.

| Workflow | Pipeline | Sample |
|---|---|---|
| `LTX IA2V` | CosyVoice TTS -> LTX image+audio-to-video -> MP4 | [![Xiaomei LTX IA2V sample](assets/samples/xiaomei-ltx-ia2v.gif)](assets/samples/xiaomei-ltx-ia2v.mp4) |
| `LTX Native A/V` | LTX image-to-video with generated speech audio -> MP4 | [![Xiaomei LTX Native A/V sample](assets/samples/xiaomei-ltx-native-av.gif)](assets/samples/xiaomei-ltx-native-av.mp4) |
| `Wan + MuseTalk` | CosyVoice TTS -> base video -> MuseTalk lip sync -> MP4 | [![Xiaomei Wan + MuseTalk sample](assets/samples/xiaomei-wan-musetalk.gif)](assets/samples/xiaomei-wan-musetalk.mp4) |

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
- Testers run `start.ps1` every time; it handles both first launch and later launches.
- Build the portable package skeleton with `.\packaging\windows\New-PortablePackage.ps1`; build the local release package with `.\packaging\windows\Build-LocalPortablePackage.ps1`.
- See [packaging/windows/README.md](packaging/windows/README.md).

## Default Services

| Service | Default | Required For | Config |
|---|---:|---|---|
| EchoFrame UI/API | `7860` | browser UI and API | `APP_HOST`, `APP_PORT` |
| LM Studio | `1234` | LLM reply planning | `LLM_BASE_URL`; `LLM_MODEL` is optional |
| CosyVoice HTTP | `9880` | speech synthesis in repo profile, except LTX Native A/V | `TTS_BACKEND`, `TTS_URL` |
| ComfyUI | `8000` | LTX workflows plus `wan_loop` and `wan` modes | `COMFY_URL`, `COMFY_ROOT` |
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
- A CosyVoice-compatible HTTP service at `TTS_URL`, unless you explicitly set `TTS_BACKEND=native` or only use the LTX Native A/V workflow.
- ComfyUI with the required Wan2.2 workflow nodes and models.
- A MuseTalk checkout/environment for on-demand lip sync.
- ffmpeg/ffprobe on PATH or configured through `FFMPEG_BIN` and `FFPROBE_BIN`.

Native CosyVoice support remains in the code for portable builds or advanced local setups. It uses `tools/native_cosyvoice_tts.py`, `TTS_ROOT`, `TTS_PYTHON`, and `TTS_PRESETS_FILE`, but repo users are not expected to make EchoFrame solve those dependencies.

## Voice Presets

The repo includes small CosyVoice zero-shot reference clips under `assets/voices/`. EchoFrame automatically selects language-matched presets from the final spoken text:

- Chinese female/male: `TTS_ZH_FEMALE_VOICE_ID=4988cee6`, `TTS_ZH_MALE_VOICE_ID=21897fae`
- English female/male: `TTS_EN_FEMALE_VOICE_ID=d36d10b9`, `TTS_EN_MALE_VOICE_ID=c715d869`

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

`fast` mode under Wan + MuseTalk does not require ComfyUI. `wan_loop`, `wan`, `LTX IA2V`, and `LTX Native A/V` require ComfyUI.

## Model Lifecycle

- EchoFrame uses the LLM currently loaded in LM Studio. Leave `LLM_MODEL` empty for this default behavior; set it only as an explicit override.
- Repo profile uses external TTS by default.
- Portable profile can use native CosyVoice worker.
- `FINAL_VIDEO_BACKEND` accepts `ltx_ia2v`, `ltx_native_audio`, or `musetalk`. The UI can also choose the workflow per run.
- Wan I2V defaults to the official ComfyUI Wan2.2 14B I2V graph with the 4-step LightX2V LoRA enabled. `WAN_PROFILE=wan22_5b_ti2v` is kept as an experimental benchmark profile only; current EchoFrame talking-head tests showed visible color banding/artifacts, so it is not recommended for production output.
- LTX IA2V and LTX Native A/V can use either the full checkpoint loader or split GGUF components. Set `LTX_MODEL_FORMAT=gguf` with `LTX_GGUF_MODEL`, `LTX_TEXT_PROJECTION`, `LTX_VIDEO_VAE`, and `LTX_AUDIO_VAE` present under the ComfyUI model folders to run the Q4_K_M path. Q4_K_M requires current ComfyUI-GGUF and KJNodes builds; do not leave old ComfyUI-GGUF backup folders under `custom_nodes`, because ComfyUI will still load them.
- LTX Native A/V estimates clip length from the spoken text using `LTX_NATIVE_AUDIO_MIN_SECONDS` and `LTX_NATIVE_AUDIO_MAX_SECONDS`, then probes the generated audio track after ComfyUI finishes. Use it as an experimental no-TTS path until speech accuracy is manually reviewed.
- Before LTX IA2V generation, EchoFrame unloads resident LM Studio models and the resident TTS worker/service when `LTX_UNLOAD_LLM_BEFORE_VIDEO=true` and `LTX_UNLOAD_TTS_BEFORE_VIDEO=true`. After the LTX video is finished, `LTX_RELOAD_TTS_AFTER_VIDEO=true` preloads TTS again; LLM is not automatically reloaded. Keep `LTX_UNLOAD_AFTER_VIDEO=true` for the safer default, or set it to `false` for resident LTX hot-cache tests.
- Wan generation calls ComfyUI `/free` after use when `COMFY_UNLOAD_AFTER_WAN=true`.
- MuseTalk runs as an on-demand child process for each lip-sync job.

## Local LTX Benchmark

Measured on May 14, 2026 with an NVIDIA RTX 4090 24 GB, the full-checkpoint LTX IA2V quality workflow, one 512px warmup run, and the same 3.36s Chinese voice clip for every measured run. Scope is direct LTX generation only; LLM, TTS, muxing, and UI/API streaming overhead are excluded.

| LTX resolution | Hot-cache LTX seconds | Observed peak VRAM MiB |
|---:|---:|---:|
| 256 | 46.99 | 23918 |
| 320 | 41.06 | 23886 |
| 384 | 40.95 | 23920 |
| 448 | 39.30 | 20464 |
| 512 | 39.93 | 21264 |
| 640 | 40.18 | 23056 |
| 768 | 45.87 | 23920 |

On this workflow the hot-cache speed sweet spot is around 448-512px. Higher resolutions are not faster, and the current 22B LTX graph should be treated as a 24 GB-class GPU path; observed peak VRAM is cache-sensitive and can still approach the full 4090 allocation.

Q4_K_M GGUF was measured on the same day with the same clip, current ComfyUI-GGUF/KJNodes, and a fresh `/free` between cases to avoid the low-VRAM slow path carrying over from a warmup run.

| LTX resolution | Q4_K_M direct LTX seconds | Observed peak VRAM MiB |
|---:|---:|---:|
| 256 | 55.13 | 23566 |
| 320 | 62.09 | 23600 |
| 384 | 70.37 | 23664 |
| 448 | 71.30 | 23696 |
| 512 | 74.15 | 23728 |
| 640 | 75.28 | 24016 |
| 768 | 87.63 | 23964 |

Q4_K_M reduces model file size but did not materially lower total runtime VRAM in this graph. It still behaves like a 24 GB-class path because the text encoder, VAE, LoRA, activations, buffers, and mixed non-Q4 tensors remain significant. Keep the full checkpoint path as the quality/default benchmark unless local disk pressure is the priority.

The UI/API resolution cap is 1028 for manual stress tests. LTX output dimensions are rounded down to the nearest multiple of 32, so a 1028 request produces 1024px output.
