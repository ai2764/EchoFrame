import asyncio
from pathlib import Path

from app.config import Settings
from app.services.musetalk import MuseTalkClient
from app.services.run_control import RunState
from app.services.service_manager import ServiceManager


class LipSyncModule:
    def __init__(self, settings: Settings, services: ServiceManager | None = None):
        self.client = MuseTalkClient(settings)
        self.services = services

    async def lip_sync(
        self,
        audio_path: Path,
        video_path: Path,
        run_dir: Path,
        run_state: RunState | None = None,
    ) -> Path:
        if self.services:
            await self.services.ensure("musetalk")
        return await asyncio.to_thread(
            self.client.lip_sync,
            audio_path=audio_path,
            video_path=video_path,
            run_dir=run_dir,
            run_state=run_state,
        )
