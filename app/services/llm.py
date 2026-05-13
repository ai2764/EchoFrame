import json
import re

import httpx

from app.config import Settings


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def health(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(self.settings.llm_base_url.rstrip("/") + "/models")
            if r.status_code == 200:
                loaded = await self.loaded_instances()
                detail = "online"
                if loaded:
                    detail += "; loaded: " + ", ".join(loaded)
                return True, detail
            return False, f"HTTP {r.status_code}"
        except Exception as exc:
            return False, str(exc)

    async def plan_reply(self, message: str) -> dict:
        prompt = self._prompt(message)
        url = self.settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
        payload = {
            "model": self.settings.llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
            "max_tokens": 1200,
        }
        instance_id = self.settings.llm_model
        try:
            if self.settings.llm_load_before_request:
                instance_id = await self.load_model()
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                raise RuntimeError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
            body = r.json()
            content = body["choices"][0]["message"]["content"]
            data = self._extract_json(content)
        except Exception:
            if not self.settings.llm_allow_fallback:
                raise
            data = self._fallback(message)
        finally:
            if self.settings.llm_unload_after_request:
                await self.unload_model(instance_id)
        return self._normalize(data)

    async def loaded_instances(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(self._native_base_url() + "/api/v1/models", headers=self._headers())
            if r.status_code != 200:
                return []
            body = r.json()
        except Exception:
            return []
        loaded = []
        for model in body.get("models", []):
            for inst in model.get("loaded_instances", []) or []:
                if isinstance(inst, dict):
                    loaded.append(str(inst.get("instance_id") or inst.get("id") or model.get("key")))
                else:
                    loaded.append(str(inst))
        return loaded

    async def load_model(self) -> str:
        payload = {
            "model": self.settings.llm_model,
            "context_length": self.settings.llm_context_length,
            "flash_attention": self.settings.llm_flash_attention,
            "offload_kv_cache_to_gpu": self.settings.llm_offload_kv_cache_to_gpu,
            "echo_load_config": True,
        }
        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
            r = await client.post(
                self._native_base_url() + "/api/v1/models/load",
                json=payload,
                headers=self._headers(),
            )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"LM Studio load failed: HTTP {r.status_code}: {r.text[:500]}")
        body = r.json()
        return str(body.get("instance_id") or self.settings.llm_model)

    async def unload_model(self, instance_id: str) -> None:
        if not instance_id:
            instance_id = self.settings.llm_model
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(
                    self._native_base_url() + "/api/v1/models/unload",
                    json={"instance_id": instance_id},
                    headers=self._headers(),
                )
        except Exception:
            pass

    def _native_base_url(self) -> str:
        base = self.settings.llm_base_url.rstrip("/")
        for suffix in ("/v1", "/api/v1"):
            if base.endswith(suffix):
                return base[: -len(suffix)]
        return base

    def _headers(self) -> dict:
        if self.settings.llm_api_key:
            return {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        return {}

    def _prompt(self, message: str) -> str:
        return f"""
You are the brain of a Chinese AI-news commentator digital avatar.
The user says:
{message}

Return strict JSON only. No markdown.
Schema:
{{
  "reply": "Simplified Chinese spoken reply, max {self.settings.max_reply_chars} Chinese chars",
  "cosyvoice_instruct": "Simplified Chinese voice style for CosyVoice, short",
  "wan_prompt": "English Wan2.2 image-to-video prompt for a square talking avatar base video"
}}

Rules:
- reply must sound conversational and analytical, not a news copy.
- cosyvoice_instruct should describe delivery style only, short and conservative.
- Prefer stable styles such as "平稳、自然、清晰". Avoid dramatic emotion, 播音腔, 夸张,
  撒娇, 喊叫, whispered delivery, or role-playing.
- wan_prompt must preserve the same person from the input image.
- wan_prompt should describe a front-facing bust shot, subtle blinking, slight nodding,
  small shoulder movement, steady camera, clean studio lighting.
- Do not ask Wan to animate detailed mouth speech. MuseTalk will handle the mouth.
- Avoid words such as wide open mouth, exaggerated speaking, yelling, distorted face.
""".strip()

    def _extract_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            if not match:
                raise
            return json.loads(match.group(0))

    def _normalize(self, data: dict) -> dict:
        reply = str(data.get("reply", "")).strip()
        instruct = str(data.get("cosyvoice_instruct", "")).strip()
        wan_prompt = str(data.get("wan_prompt", "")).strip()
        if not reply:
            reply = self._fallback("")["reply"]
        if len(reply) > self.settings.max_reply_chars:
            reply = reply[: self.settings.max_reply_chars].rstrip(" ,.;:!?")
        if not instruct:
            instruct = "\u5e73\u7a33\u3001\u81ea\u7136\u3001\u6e05\u6670"
        if not wan_prompt:
            wan_prompt = self._fallback("")["wan_prompt"]
        return {
            "reply": reply,
            "cosyvoice_instruct": instruct,
            "wan_prompt": self._sanitize_wan_prompt(wan_prompt),
        }

    def _sanitize_wan_prompt(self, prompt: str) -> str:
        banned = [
            "wide open mouth",
            "open mouth",
            "yelling",
            "screaming",
            "exaggerated speaking",
            "distorted face",
        ]
        clean = prompt
        for word in banned:
            clean = re.sub(re.escape(word), "", clean, flags=re.I)
        anchor = (
            " Preserve the same identity as the reference image, front-facing bust shot, "
            "subtle blinking, slight nodding, small shoulder movement, steady camera, "
            "clean studio lighting, natural neutral mouth before lip-sync."
        )
        if "preserve" not in clean.lower():
            clean += anchor
        return re.sub(r"\s+", " ", clean).strip()

    def _fallback(self, message: str) -> dict:
        msg = (message or "").strip()
        if msg:
            reply = (
                "\u6211\u7684\u521d\u6b65\u5224\u65ad\u662f\uff1a"
                "\u8fd9\u4ef6\u4e8b\u4e0d\u53ea\u770b\u70ed\u5ea6\uff0c"
                "\u66f4\u8981\u770b\u5b83\u4f1a\u6539\u53d8\u54ea\u4e2a\u5177\u4f53\u73af\u8282\u3002"
            )
        else:
            reply = (
                "\u6211\u7684\u5224\u65ad\u662f\uff1a"
                "\u5148\u770b\u5b9e\u9645\u843d\u5730\uff0c"
                "\u518d\u770b\u5b83\u662f\u4e0d\u662f\u771f\u6b63\u964d\u4f4e\u4e86\u6210\u672c\u3002"
            )
        return {
            "reply": reply,
            "cosyvoice_instruct": "\u5e73\u7a33\u3001\u81ea\u7136\u3001\u6e05\u6670",
            "wan_prompt": (
                "A front-facing AI news commentator avatar in a clean modern studio, "
                "medium close-up bust shot, subtle blinking, slight nodding, small shoulder movement, "
                "calm confident expression, steady camera, soft studio lighting."
            ),
        }
