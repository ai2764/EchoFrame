from app.config import Settings
from app.services.llm import LLMClient
from app.services.service_manager import ServiceManager


class LLMModule:
    def __init__(self, settings: Settings, services: ServiceManager | None = None):
        self.settings = settings
        self.client = LLMClient(settings)
        self.services = services

    async def plan(self, message: str, manual_reply: str = "") -> dict[str, str]:
        reply = manual_reply.strip()
        if reply:
            return self._manual_plan(reply)
        if self.services:
            await self.services.ensure("lm_studio")
        return await self.client.plan_reply(message)

    def _manual_plan(self, reply: str) -> dict[str, str]:
        return {
            "reply": reply,
            "cosyvoice_instruct": "\u5e73\u7a33\u3001\u81ea\u7136\u3001\u6e05\u6670",
            "wan_prompt": (
                "Preserve the same identity as the reference image, front-facing bust shot, "
                "subtle blinking, slight nodding, small shoulder movement, steady camera, "
                "clean studio lighting, natural neutral mouth before lip-sync."
            ),
        }

