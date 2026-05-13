import asyncio
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.services.comfy import ComfyClient
from app.services.media import MediaTools
from app.services.run_control import RunState
from app.services.service_manager import ServiceManager


@dataclass(frozen=True)
class BaseVideoResult:
    base_path: Path
    lip_sync_input_path: Path
    fps: int


class VideoGenerationModule:
    def __init__(self, settings: Settings, services: ServiceManager | None = None):
        self.settings = settings
        self.media = MediaTools(settings)
        self.comfy = ComfyClient(settings)
        self.services = services

    async def generate_base_video(
        self,
        mode: str,
        avatar_path: Path,
        prompt: str,
        audio_duration: float,
        run_id: str,
        run_dir: Path,
        resolution: int,
        wan_resolution: int,
        run_state: RunState | None = None,
    ) -> BaseVideoResult:
        output_fps = self.settings.musetalk_fps
        base_path = run_dir / "base.mp4"
        if mode in {"wan", "wan_loop"}:
            if self.services:
                await self.services.ensure("comfyui")
            wan_length = (
                self.media.wan_loop_length()
                if mode == "wan_loop"
                else self.media.wan_length_for_duration(audio_duration)
            )
            raw_base = await self.comfy.generate_wan_base(
                image_path=avatar_path,
                prompt=prompt,
                length=wan_length,
                run_id=run_id,
                run_dir=run_dir,
                run_state=run_state,
                width=wan_resolution,
                height=wan_resolution,
            )
            if run_state:
                run_state.check()
            if mode == "wan_loop":
                await asyncio.to_thread(
                    self.media.loop_video_to_duration,
                    raw_base,
                    audio_duration,
                    base_path,
                    output_fps,
                    resolution,
                )
            else:
                await asyncio.to_thread(
                    self.media.normalize_video,
                    raw_base,
                    audio_duration,
                    base_path,
                    output_fps,
                    resolution,
                )
        else:
            await asyncio.to_thread(
                self.media.make_still_video,
                avatar_path,
                audio_duration,
                base_path,
                output_fps,
                resolution,
            )

        lip_sync_input = base_path
        if mode == "fast" and self.settings.musetalk_fast_image_input:
            lip_sync_input = run_dir / "musetalk_input.png"
            await asyncio.to_thread(self.media.save_square_avatar, avatar_path, lip_sync_input, resolution)
        return BaseVideoResult(base_path=base_path, lip_sync_input_path=lip_sync_input, fps=output_fps)

