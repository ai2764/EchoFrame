from pathlib import Path

from app.config import Settings
from app.services.service_manager import ServiceManager
from app.services.tts import TTSClient


class TTSModule:
    def __init__(self, settings: Settings, services: ServiceManager | None = None):
        self.settings = settings
        self.client = TTSClient(settings)
        self.services = services

    async def synthesize(self, text: str, instruct: str, voice_id: str, output_path: Path) -> str:
        if self.services:
            await self.services.ensure("cosyvoice")
        sent_instruct = self.instruct_to_send(instruct)
        await self.client.synthesize(
            text=text,
            instruct=sent_instruct,
            voice_id=voice_id,
            output_path=output_path,
        )
        return sent_instruct

    def instruct_to_send(self, llm_instruct: str) -> str:
        if self.settings.tts_use_llm_instruct:
            return llm_instruct.strip()
        return self.settings.tts_fixed_instruct.strip()

