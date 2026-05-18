# EchoFrame

EchoFrame is a local conversational digital-human orchestrator:

```text
avatar image -> LLM reply plan -> TTS audio -> base video -> lip sync -> MP4
```

The UI exposes four generation workflows:

- `LTX IA2V`: LLM/manual text -> CosyVoice TTS -> LTX image+audio-to-video -> MP4.
- `LTX IA2V Q4`: experimental resident path. Prepare clears VRAM, preloads CosyVoice TTS, then preloads the LTX Q4_K_M GGUF path so both can stay resident for a test run.
- `LTX Native A/V`: LLM/manual text -> LTX image-to-video with generated speech audio -> MP4. This skips external TTS and MuseTalk.
- `Wan + MuseTalk`: LLM/manual text -> CosyVoice TTS -> still/Wan base video -> MuseTalk lip sync -> MP4.

The repository is intentionally lightweight. It contains the EchoFrame UI/API, workflow code, service health checks, and small voice reference presets. It does not install or vendor heavy AI runtimes for pull-repo users.

## Sample Outputs

These short clips use the same Xiaomei avatar image and map to the main output families. `LTX IA2V Q4` produces the same kind of output as `LTX IA2V`; it exists to test resident Q4 loading and is not shown as a separate sample. GIF previews render inline on GitHub; click a preview to open the MP4 with audio.

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

## External Dependencies

Repo users bring their own AI runtimes. EchoFrame is the orchestrator: it uploads inputs, calls HTTP/local tools, watches health, assembles media, and manages model unload/preload where supported. It does not create CUDA environments, install PyTorch, install ComfyUI custom nodes, or download large model weights in the repo profile.

| Dependency | Required For | Default | EchoFrame Expects | Upstream / Docs | Key Config |
|---|---|---:|---|---|---|
| Python app env | UI/API, tests, local orchestration | current Python | Python 3.10+ with `pyproject.toml` deps installed | [Python](https://www.python.org/) | `APP_HOST`, `APP_PORT`, `DATA_DIR` |
| NVIDIA GPU + driver | practical local generation | `nvidia-smi` | CUDA-capable NVIDIA GPU visible to `nvidia-smi` | [NVIDIA drivers](https://www.nvidia.com/Download/index.aspx) | `TTS_CUDA_VISIBLE_DEVICES`, `MUSETALK_CUDA_VISIBLE_DEVICES`, `LMS_GPU` |
| LM Studio or OpenAI-compatible LLM server | LLM reply planning when no spoken text override is supplied | `http://127.0.0.1:1234/v1` | `/v1/models` and `/v1/chat/completions` compatible API | [LM Studio API docs](https://lmstudio.ai/docs/api/) | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LMS_BIN` |
| CosyVoice-compatible TTS | `LTX IA2V`, `LTX IA2V Q4`, `Wan + MuseTalk` | `http://127.0.0.1:9880` | HTTP `/health` and `/tts`, or a prepared native CosyVoice worker | [CosyVoice](https://github.com/FunAudioLLM/CosyVoice) | `TTS_BACKEND`, `TTS_URL`, `TTS_ROOT`, `TTS_PYTHON`, `TTS_PRESETS_FILE` |
| ComfyUI | `LTX IA2V`, `LTX IA2V Q4`, `LTX Native A/V`, `wan_loop`, `wan` | `http://127.0.0.1:8000` | ComfyUI with required custom nodes and model files | [ComfyUI](https://github.com/Comfy-Org/ComfyUI), [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) | `COMFY_URL`, `COMFY_ROOT`, `COMFY_PYTHON`, `COMFY_BASE_DIR`, `COMFY_MODELS_DIR` |
| MuseTalk | `Wan + MuseTalk` final lip sync | on-demand process | Local MuseTalk checkout/environment and model files | [MuseTalk](https://github.com/TMElyralab/MuseTalk) | `MUSETALK_ROOT`, `MUSETALK_PYTHON`, `MUSETALK_FFMPEG_DIR` |
| ffmpeg + ffprobe | audio probing, muxing, frame/video processing | `PATH` | Working command-line binaries | [FFmpeg](https://www.ffmpeg.org/), [downloads](https://ffmpeg.org/download.html) | `FFMPEG_BIN`, `FFPROBE_BIN` |

### Workflow Dependency Matrix

| Workflow | LLM | TTS | ComfyUI | MuseTalk | ffmpeg/ffprobe | Notes |
|---|---|---|---|---|---|---|
| `LTX IA2V` | optional when spoken text is provided | required | required | no | required | Default external-audio LTX path. |
| `LTX IA2V Q4` | optional when spoken text is provided | required | required | no | required | Requires GGUF Q4 loader path and split LTX model files. Prepare keeps TTS + LTX resident. |
| `LTX Native A/V` | optional when spoken text is provided | no | required | no | required | LTX generates video and speech audio; review speech accuracy manually. |
| `Wan + MuseTalk` / `fast` | optional when spoken text is provided | required | no | required | required | Uses a still base video, then MuseTalk lip sync. |
| `Wan + MuseTalk` / `wan_loop` or `wan` | optional when spoken text is provided | required | required | required | required | ComfyUI creates the base video; MuseTalk applies lip sync. |

### Dependency Details

**LM Studio / LLM**

- Leave `LLM_MODEL` empty to use whatever model is already loaded in LM Studio.
- Set `LLM_MODEL` only when you want EchoFrame to request a specific model through LM Studio's native management API.
- Manual spoken text skips LLM generation, but the service can still be checked in the UI.

**CosyVoice / TTS**

- Repo default is `TTS_BACKEND=http`, meaning EchoFrame calls an external CosyVoice-compatible server at `TTS_URL`.
- Native worker mode is available for portable builds and advanced local setups: set `TTS_BACKEND=native`, `TTS_ROOT`, `TTS_PYTHON`, `TTS_MODEL_DIR`, and `TTS_PRESETS_FILE`.
- `LTX Native A/V` does not use CosyVoice. The other workflows do.
- EchoFrame does not trim generated audio. It probes duration with ffprobe and muxes the full audio into the final MP4.

**ComfyUI**

- LTX workflows require ComfyUI custom nodes that provide the LTXV image/audio/video nodes used by the generated graph, plus video save/create/audio load nodes.
- `LTX IA2V` and `LTX Native A/V` default to checkpoint loading with `LTX_CHECKPOINT` or `LTX_FAST_CHECKPOINT` and `LTX_TEXT_ENCODER`.
- `LTX IA2V Q4` forces `LTX_MODEL_FORMAT=gguf` for that run. It requires `UnetLoaderGGUF`, split text encoders, split video/audio VAE files, and the configured `LTX_GGUF_MODEL`.
- Wan modes require the Wan2.2 ComfyUI graph nodes and the configured Wan high/low/text/vae model files.
- If ComfyUI returns validation errors, first check custom node versions and whether old duplicate custom-node folders are still being loaded.

Expected ComfyUI model locations are under `COMFY_MODELS_DIR` when set, otherwise under the configured ComfyUI models directory:

| Feature | Required model folders |
|---|---|
| LTX checkpoint path | `checkpoints/`, `text_encoders/`, `latent_upscale_models/`, optional `loras/` |
| LTX Q4 GGUF path | `unet/`, `text_encoders/`, `vae/`, `latent_upscale_models/`, optional `loras/` |
| Wan 14B I2V | `diffusion_models/`, `text_encoders/`, `vae/`, optional `loras/` |
| Wan 5B TI2V experiment | `diffusion_models/`, `text_encoders/`, `vae/` |

**MuseTalk**

- MuseTalk is not a resident service in the normal repo profile; EchoFrame starts it as an on-demand child process for lip sync.
- `fast` mode under `Wan + MuseTalk` uses a still base video and does not require ComfyUI, but it still requires MuseTalk.
- `wan_loop` and `wan` generate a ComfyUI base video first, then run MuseTalk.

**ffmpeg**

- ffmpeg and ffprobe must be callable from `PATH`, or set explicit `FFMPEG_BIN` and `FFPROBE_BIN` values.
- EchoFrame uses them for audio duration checks, muxing, normalizing base videos, extracting native LTX audio, and small utility media operations.

**GPU / VRAM**

- EchoFrame reports GPU usage through `nvidia-smi` and Windows GPU process counters where available.
- Prepare always attempts to clear VRAM first by freeing ComfyUI models, unloading LM Studio models, and unloading/stopping the managed TTS path before preloading the selected workflow.
- Q4_K_M is a VRAM/residency experiment, not a guaranteed speedup. On RTX 4090, the FP8 checkpoint path can be faster because it better matches Ada Tensor Core acceleration, while GGUF Q4 may add unpack/dequantize overhead.

Run this to print the machine-readable service manifest:

```powershell
python -m app.stack_control manifest
```

EchoFrame also checks services at app startup and writes a snapshot to `data/logs/startup_health.json`.

## Configuration

Copy `.env.example` to `.env` and adjust it locally. Do not commit `.env`.

Portable builds keep user config at `config/.env` and launch EchoFrame with `ECHOFRAME_ENV_FILE` pointing to that file. Repo users normally do not need this variable.

The repo profile expects you to run external services yourself. See [External Dependencies](#external-dependencies) for the service contracts, model folders, and workflow-specific requirements.

Native CosyVoice support remains in the code for portable builds or advanced local setups. It uses `tools/native_cosyvoice_tts.py`, `TTS_ROOT`, `TTS_PYTHON`, `TTS_MODEL_DIR`, and `TTS_PRESETS_FILE`, but repo users are not expected to make EchoFrame solve those dependencies.

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

`fast` mode under Wan + MuseTalk does not require ComfyUI. `wan_loop`, `wan`, `LTX IA2V`, `LTX IA2V Q4`, and `LTX Native A/V` require ComfyUI.

## Model Lifecycle

- EchoFrame uses the LLM currently loaded in LM Studio. Leave `LLM_MODEL` empty for this default behavior; set it only as an explicit override.
- Repo profile uses external TTS by default.
- Portable profile can use native CosyVoice worker.
- `FINAL_VIDEO_BACKEND` accepts `ltx_ia2v`, `ltx_ia2v_q4`, `ltx_native_audio`, or `musetalk`. The UI can also choose the workflow per run.
- Wan I2V defaults to the official ComfyUI Wan2.2 14B I2V graph with the 4-step LightX2V LoRA enabled. `WAN_PROFILE=wan22_5b_ti2v` is kept as an experimental benchmark profile only; current EchoFrame talking-head tests showed visible color banding/artifacts, so it is not recommended for production output.
- LTX IA2V and LTX Native A/V can use either the full checkpoint loader or split GGUF components. Set `LTX_MODEL_FORMAT=gguf` with `LTX_GGUF_MODEL`, `LTX_TEXT_PROJECTION`, `LTX_VIDEO_VAE`, and `LTX_AUDIO_VAE` present under the ComfyUI model folders to run the Q4_K_M path globally. Q4_K_M requires current ComfyUI-GGUF and KJNodes builds; do not leave old ComfyUI-GGUF backup folders under `custom_nodes`, because ComfyUI will still load them.
- `LTX IA2V Q4` is a per-run UI workflow that forces the GGUF Q4 path without changing the global default. Its Prepare button clears VRAM, preloads TTS, then warms LTX Q4 and leaves both resident. During generation it keeps TTS loaded and leaves LTX resident after the run for hot-cache testing.
- LTX Native A/V estimates clip length from the spoken text using `LTX_NATIVE_AUDIO_MIN_SECONDS` and `LTX_NATIVE_AUDIO_MAX_SECONDS`, then probes the generated audio track after ComfyUI finishes. Use it as an experimental no-TTS path until speech accuracy is manually reviewed.
- Before normal LTX IA2V generation, EchoFrame unloads resident LM Studio models and the resident TTS worker/service when `LTX_UNLOAD_LLM_BEFORE_VIDEO=true` and `LTX_UNLOAD_TTS_BEFORE_VIDEO=true`. After the LTX video is finished, `LTX_RELOAD_TTS_AFTER_VIDEO=true` preloads TTS again; LLM is not automatically reloaded. Keep `LTX_UNLOAD_AFTER_VIDEO=true` for the safer default, or set it to `false` for resident LTX hot-cache tests.
- Prepare always starts with a VRAM clear attempt before preloading the selected workflow. This calls ComfyUI `/free`, unloads LM Studio models where supported, and unloads/stops the managed TTS path where supported.
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

Q4_K_M can fit as a resident experiment with TTS on a 24 GB card, but it was slower than the full checkpoint path in this benchmark. The practical bottleneck is not only whether weights fit in VRAM: the text encoder, VAE, LoRA, activations, buffers, mixed non-Q4 tensors, and GGUF unpack/dequantize overhead still matter. Keep the full checkpoint path as the quality/default benchmark unless local disk pressure or resident Q4 testing is the priority.

The UI/API resolution cap is 1028 for manual stress tests. LTX output dimensions are rounded down to the nearest multiple of 32, so a 1028 request produces 1024px output.
