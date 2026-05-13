from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_host: str = "0.0.0.0"
    app_port: int = 7860
    data_dir: Path = Path("data")
    avatar_size: int = 512
    output_size: int = 320
    resolution_min: int = 120
    resolution_max: int = 512

    llm_base_url: str = "http://127.0.0.1:1234/v1"
    llm_model: str = "openai/gpt-oss-20b"
    llm_api_key: str = ""
    llm_allow_fallback: bool = True
    llm_timeout_seconds: float = 120.0
    max_reply_chars: int = 90
    llm_load_before_request: bool = True
    llm_unload_after_request: bool = True
    llm_context_length: int = 16384
    llm_flash_attention: bool = True
    llm_offload_kv_cache_to_gpu: bool = True
    lms_bin: str = "lms"
    lms_server_host: str = "127.0.0.1"
    lms_server_port: int = 1234
    lms_gpu: str = "max"

    tts_url: str = "http://127.0.0.1:9880"
    tts_secret: str = ""
    tts_default_voice_id: str = "4988cee6"
    tts_use_llm_instruct: bool = False
    tts_fixed_instruct: str = ""
    tts_speed: float = 1.0
    tts_timeout_seconds: float = 180.0
    tts_trim_start_seconds: float = 0.8
    tts_fade_in_seconds: float = 0.04
    tts_root: Path = Path("engines/cosyvoice")
    tts_python: str = "python"
    tts_script: str = "tts_server.py"
    tts_port: int = 9880
    tts_start_timeout_seconds: int = 180

    comfy_url: str = "http://127.0.0.1:8000"
    comfy_root: Path = Path("engines/comfyui")
    comfy_python: str = "python"
    comfy_base_dir: Path | None = None
    comfy_input_dir: Path = Path("engines/comfyui/input")
    comfy_output_dir: Path = Path("engines/comfyui/output")
    comfy_models_dir: Path | None = None
    comfy_timeout_seconds: int = 900
    comfy_unload_after_wan: bool = True
    comfy_start_timeout_seconds: int = 240
    wan_width: int = 320
    wan_height: int = 320
    wan_fps: int = 12
    wan_loop_seconds: float = 2.75
    wan_high_model: str = "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"
    wan_low_model: str = "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"
    wan_clip_model: str = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    wan_vae_model: str = "wan_2.1_vae.safetensors"
    wan_weight_dtype: str = "default"

    musetalk_root: Path = Path("engines/musetalk")
    musetalk_python: str = "python"
    musetalk_ffmpeg_dir: str = ""
    musetalk_use_float16: bool = True
    musetalk_cuda_visible_devices: str = "0"
    musetalk_timeout_seconds: int = 1200
    musetalk_fps: int = 12
    musetalk_batch_size: int = 16
    musetalk_fast_image_input: bool = False
    musetalk_bbox_shift: int = 0
    musetalk_extra_margin: int = 10
    musetalk_parsing_mode: str = "jaw"
    musetalk_left_cheek_width: int = 90
    musetalk_right_cheek_width: int = 90

    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def abs_data_dir(self) -> Path:
        return self.data_dir.resolve()


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.abs_data_dir.mkdir(parents=True, exist_ok=True)
    return s
