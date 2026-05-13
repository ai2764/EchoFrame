from typing import Literal

from pydantic import BaseModel, Field


class AvatarResponse(BaseModel):
    avatar_id: str
    image_url: str


class ChatRequest(BaseModel):
    avatar_id: str
    message: str = Field(default="", max_length=1000)
    reply_override: str | None = Field(default=None, max_length=2000)
    mode: Literal["fast", "wan_loop", "wan"] = "fast"
    voice_id: str | None = None
    resolution: int | None = Field(default=None, ge=120, le=512)


class ChatResponse(BaseModel):
    run_id: str
    reply: str
    cosyvoice_instruct: str
    tts_instruct_sent: str
    wan_prompt: str
    audio_duration: float
    timings: dict[str, float]
    audio_url: str
    base_video_url: str
    video_url: str
    mode: str
    resolution: int


class ServiceStatus(BaseModel):
    ok: bool
    detail: str = ""


class EngineStatus(BaseModel):
    name: str
    ok: bool
    detail: str = ""
    installed: bool = True
    online: bool = False
    models_ok: bool | None = None
    startable: bool = True
    pid: int | None = None
    port: int | None = None


class EngineActionResponse(BaseModel):
    ok: bool
    name: str
    action: str
    detail: str = ""
    status: EngineStatus | None = None


class HealthResponse(BaseModel):
    lm_studio: ServiceStatus
    cosyvoice: ServiceStatus
    comfyui: ServiceStatus
    musetalk: ServiceStatus
    ffmpeg: ServiceStatus
    gpu: ServiceStatus
