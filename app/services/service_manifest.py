from __future__ import annotations

from dataclasses import dataclass, asdict

from app.config import Settings


@dataclass(frozen=True)
class ServiceDefinition:
    name: str
    label: str
    kind: str
    default: str
    required_for: str
    health: str
    config_keys: list[str]
    repo_note: str
    portable_note: str

    def to_dict(self) -> dict:
        return asdict(self)


def service_definitions(settings: Settings) -> list[ServiceDefinition]:
    tts_default = "native worker" if settings.tts_backend == "native" else settings.tts_url
    tts_repo_note = (
        "External CosyVoice-compatible HTTP service. EchoFrame only calls it."
        if settings.tts_backend == "http"
        else "Native CosyVoice worker. Requires a prepared CosyVoice Python environment."
    )
    services = [
        ServiceDefinition(
            name="lm_studio",
            label="LM Studio",
            kind="openai-compatible-llm",
            default=f"http://{settings.lms_server_host}:{settings.lms_server_port}/v1",
            required_for="reply planning unless manual reply is used",
            health="GET /v1/models",
            config_keys=["LLM_BASE_URL", "LMS_SERVER_HOST", "LMS_SERVER_PORT", "LLM_MODEL"],
            repo_note="Run LM Studio yourself and load the model you want; LLM_MODEL is only an optional override.",
            portable_note="Portable launcher can start LM Studio only when a compatible CLI is configured; the active LM Studio model is used by default.",
        ),
        ServiceDefinition(
            name="cosyvoice",
            label="CosyVoice",
            kind="tts",
            default=tts_default,
            required_for="LTX IA2V, LTX IA2V Q4, and Wan + MuseTalk workflows; not required for LTX native-audio mode",
            health="HTTP /health when TTS_BACKEND=http; file/model checks when TTS_BACKEND=native",
            config_keys=[
                "TTS_BACKEND",
                "TTS_URL",
                "TTS_ROOT",
                "TTS_PYTHON",
                "TTS_PRESETS_FILE",
                "TTS_FEMALE_VOICE_ID",
                "TTS_MALE_VOICE_ID",
                "TTS_ZH_FEMALE_VOICE_ID",
                "TTS_ZH_MALE_VOICE_ID",
                "TTS_EN_FEMALE_VOICE_ID",
                "TTS_EN_MALE_VOICE_ID",
            ],
            repo_note=tts_repo_note,
            portable_note="Portable profile uses the bundled CosyVoice environment and native worker.",
        ),
        ServiceDefinition(
            name="comfyui",
            label="ComfyUI",
            kind="image/audio-to-video and image-to-video",
            default=settings.comfy_url,
            required_for="LTX native audio, LTX IA2V, LTX IA2V Q4, and Wan base video modes",
            health="GET /system_stats",
            config_keys=["COMFY_URL", "COMFY_ROOT", "COMFY_BASE_DIR", "COMFY_MODELS_DIR"],
            repo_note="Run ComfyUI yourself with the required LTX IA2V and Wan2.2 workflow nodes and models.",
            portable_note="Portable package owns the ComfyUI runtime; first run downloads configured models.",
        ),
        ServiceDefinition(
            name="musetalk",
            label="MuseTalk",
            kind="lip-sync",
            default="on-demand process",
            required_for="Wan + MuseTalk workflow",
            health="local model files and runner checks",
            config_keys=["MUSETALK_ROOT", "MUSETALK_PYTHON", "MUSETALK_FFMPEG_DIR"],
            repo_note="Provide an existing MuseTalk checkout/environment in config.",
            portable_note="Portable package owns the MuseTalk environment; first run downloads configured models.",
        ),
        ServiceDefinition(
            name="ffmpeg",
            label="ffmpeg",
            kind="media-tool",
            default="PATH",
            required_for="audio probing and video assembly",
            health="ffmpeg -version and ffprobe -version",
            config_keys=["FFMPEG_BIN", "FFPROBE_BIN"],
            repo_note="Install ffmpeg yourself or set explicit binary paths.",
            portable_note="Portable package ships ffmpeg and points config at the bundled binaries.",
        ),
        ServiceDefinition(
            name="gpu",
            label="NVIDIA GPU",
            kind="hardware",
            default="nvidia-smi",
            required_for="practical local generation speed",
            health="nvidia-smi query",
            config_keys=["TTS_CUDA_VISIBLE_DEVICES", "MUSETALK_CUDA_VISIBLE_DEVICES", "LMS_GPU"],
            repo_note="EchoFrame reports GPU status but does not install drivers or CUDA.",
            portable_note="Portable first run checks driver/GPU availability before model downloads.",
        ),
    ]
    return services


def service_manifest(settings: Settings) -> dict:
    return {
        "profile": settings.app_profile,
        "policy": (
            "repo checks external services only"
            if settings.app_profile == "repo"
            else "portable owns packaged runtimes and downloads models on first run"
        ),
        "services": [definition.to_dict() for definition in service_definitions(settings)],
    }
