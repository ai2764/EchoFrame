import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_profile: Literal["repo", "portable"] = "repo"
    app_host: str = "0.0.0.0"
    app_port: int = 7860
    data_dir: Path = Path("data")
    model_downloads_enabled: bool = False
    avatar_size: int = 512
    output_size: int = 320
    resolution_min: int = 120
    resolution_max: int = 1028
    final_video_backend: Literal["ltx_ia2v", "ltx_ia2v_q4", "ltx_native_audio", "musetalk"] = "ltx_ia2v"

    llm_base_url: str = "http://127.0.0.1:1234/v1"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_allow_fallback: bool = True
    llm_timeout_seconds: float = 120.0
    max_reply_chars: int = 90
    llm_load_before_request: bool = False
    llm_unload_after_request: bool = False
    llm_context_length: int = 16384
    llm_flash_attention: bool = True
    llm_offload_kv_cache_to_gpu: bool = True
    lms_bin: str = "lms"
    lms_server_host: str = "127.0.0.1"
    lms_server_port: int = 1234
    lms_gpu: str = "max"

    tts_url: str = "http://127.0.0.1:9880"
    tts_backend: Literal["native", "http"] = "http"
    tts_secret: str = ""
    tts_manage_http_service: bool = False
    tts_default_voice_id: str = "d36d10b9"
    tts_female_voice_id: str = "d36d10b9"
    tts_male_voice_id: str = "c715d869"
    tts_zh_female_voice_id: str = "4988cee6"
    tts_zh_male_voice_id: str = "21897fae"
    tts_en_female_voice_id: str = "d36d10b9"
    tts_en_male_voice_id: str = "c715d869"
    tts_use_llm_instruct: bool = False
    tts_fixed_instruct: str = ""
    tts_speed: float = 1.0
    tts_timeout_seconds: float = 420.0
    tts_trim_start_seconds: float = 0.0
    tts_fade_in_seconds: float = 0.04
    tts_root: Path = Path("engines/cosyvoice")
    tts_model_dir: Path | None = None
    tts_presets_file: Path | None = Path("assets/voices/presets.json")
    tts_python: str = "python"
    tts_script: str = "tts_server.py"
    tts_port: int = 9880
    tts_start_timeout_seconds: int = 180
    tts_cuda_visible_devices: str = "0"
    tts_native_worker: bool = True
    tts_preload_on_startup: bool = True
    tts_native_unload_after_request: bool = False
    tts_use_float16: bool = True
    tts_text_frontend: bool = False

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
    wan_profile: Literal["wan22_14b_i2v", "wan22_5b_ti2v"] = "wan22_14b_i2v"
    wan_high_model: str = "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"
    wan_low_model: str = "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"
    wan_clip_model: str = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    wan_vae_model: str = "wan_2.1_vae.safetensors"
    wan_weight_dtype: str = "default"
    wan_use_4step_lora: bool = True
    wan_high_lora: str = "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"
    wan_low_lora: str = "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"
    wan_lora_strength: float = 1.0
    wan_5b_model: str = "wan2.2_ti2v_5B_fp16.safetensors"
    wan_5b_vae_model: str = "wan2.2_vae.safetensors"
    wan_5b_steps: int = 20
    wan_5b_cfg: float = 5.0
    wan_5b_shift: float = 8.0
    wan_5b_sampler: str = "uni_pc"
    wan_5b_scheduler: str = "simple"

    ltx_profile: Literal["quality", "fast"] = "quality"
    # Experimental: "unet" supports official LTX transformer-only models via split loaders.
    # Keep "checkpoint" as the product default so normal installs do not pull 20GB+ models.
    ltx_model_format: Literal["checkpoint", "gguf", "unet"] = "checkpoint"
    ltx_width: int = 768
    ltx_height: int = 768
    ltx_fps: int = 24
    ltx_native_audio_min_seconds: float = 2.4
    ltx_native_audio_max_seconds: float = 8.0
    ltx_unload_llm_before_video: bool = True
    ltx_unload_tts_before_video: bool = True
    ltx_reload_tts_after_video: bool = True
    ltx_unload_after_video: bool = True
    ltx_checkpoint: str = "ltx-2.3-22b-dev-fp8.safetensors"
    ltx_fast_checkpoint: str = "ltx-2.3-22b-distilled-fp8.safetensors"
    # Used only when ltx_model_format="unet".
    ltx_unet_model: str = "ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors"
    ltx_unet_weight_dtype: str = "default"
    ltx_gguf_model: str = "LTX-2.3-dev-Q4_K_M.gguf"
    ltx_text_encoder: str = "gemma_3_12B_it_fp4_mixed.safetensors"
    ltx_text_projection: str = "ltx-2.3_text_projection_bf16.safetensors"
    ltx_video_vae: str = "LTX23_video_vae_bf16.safetensors"
    ltx_audio_vae: str = "LTX23_audio_vae_bf16.safetensors"
    ltx_lora: str = "ltx-2.3-22b-distilled-lora-384-1.1.safetensors"
    ltx_lora_fallback: str = "ltx-2.3-22b-distilled-lora-384.safetensors"
    ltx_lora_strength: float = 0.5
    ltx_upscale_model: str = "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
    ltx_negative_prompt: str = "zoom in, zooming in, camera push-in, punch-in, face close-up, cropped face, head cropped, extreme close-up, static portrait, frozen frame, motionless, still image, subtitles, captions, closed captions, text overlay, on-screen text, title card, lower third, karaoke lyrics, logo, watermark, pc game, console game, video game, cartoon, childish, ugly"

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
    env_file = os.environ.get("ECHOFRAME_ENV_FILE")
    s = Settings(_env_file=env_file) if env_file else Settings()
    s.abs_data_dir.mkdir(parents=True, exist_ok=True)
    return s
