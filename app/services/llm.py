import json
import re

import httpx

from app.config import Settings
from app.services.chinese import to_simplified_chinese


VIDEO_IDENTITY_ANCHOR = (
    "Preserve the same identity as the reference image, front-facing head-and-shoulders bust shot "
    "in stable 1:1 framing, full head, hairline, chin, neck, and shoulders visible, clean studio lighting."
)
VIDEO_MOTION_ANCHOR = (
    "Visible but realistic motion throughout: lips part, the mouth opens and closes naturally with "
    "moderate speech articulation, and lips, jaw, cheeks, and chin move in sync with the supplied "
    "voice audio; clear vowel and consonant mouth shapes without exaggeration; natural blinks and "
    "eyebrow micro-expressions; gentle head turns and nods; breathing, small shoulder and torso "
    "shifts; locked-off camera, stable framing, and consistent head size throughout. Looks like live "
    "video, not a static portrait or frozen frame."
)


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
                elif not self.settings.llm_model.strip():
                    detail += "; no loaded LLM"
                return True, detail
            return False, f"HTTP {r.status_code}"
        except Exception as exc:
            return False, str(exc)

    async def plan_reply(self, message: str) -> dict:
        prompt = self._prompt(message)
        model = self.settings.llm_model.strip()
        instance_id = ""
        loaded_by_us = False
        url = self.settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
        try:
            if self.settings.llm_load_before_request:
                instance_id = await self.load_model()
                model = instance_id or model
                loaded_by_us = True
            if not model:
                model = await self.active_model()
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
                "max_tokens": 1200,
            }
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
            if self.settings.llm_unload_after_request and loaded_by_us:
                await self.unload_model(instance_id)
        return self._normalize(data)

    async def active_model(self) -> str:
        loaded = await self.loaded_instances()
        if loaded:
            return loaded[0]
        raise RuntimeError("LM Studio has no loaded LLM. Load a model in LM Studio or set LLM_MODEL.")

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
            if model.get("type") not in (None, "llm"):
                continue
            for inst in model.get("loaded_instances", []) or []:
                if isinstance(inst, dict):
                    loaded.append(str(inst.get("instance_id") or inst.get("id") or model.get("key")))
                else:
                    loaded.append(str(inst))
        return loaded

    async def load_model(self) -> str:
        if not self.settings.llm_model.strip():
            raise RuntimeError("LLM_MODEL is required when LLM_LOAD_BEFORE_REQUEST=true")
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
            return
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
The user says:
{message}

Return strict JSON only. No markdown.
Schema:
{{
  "reply": "spoken reply in the same language as the user's input, max {self.settings.max_reply_chars} characters",
  "cosyvoice_instruct": "voice delivery style in the same language as the user's input, short",
  "wan_prompt": "English video prompt for an image-and-audio-to-video talking avatar"
}}

Rules:
- Do not add a persona, occupation, backstory, or role-play identity.
- Reply directly to the user's message.
- Match the user's input language. If the user mixes languages, use the main language.
- Keep reply natural, concise, and conversational.
- cosyvoice_instruct should describe delivery style only, short and conservative.
- Prefer stable styles such as calm, natural, and clear. Avoid dramatic emotion,
  broadcasting voice, exaggerated delivery, seductive delivery, shouting,
  whispered delivery, or role-playing.
- wan_prompt must preserve the same person from the input image and use the supplied
  voice audio as the speech timing.
- wan_prompt must explicitly request visible but realistic motion throughout. Include
  lips parting, the mouth opening and closing naturally with moderate speech articulation,
  lips, jaw, cheeks, and chin moving in sync with the supplied audio, clear vowel and
  consonant mouth shapes, natural blinks, eyebrow micro-expressions, gentle head turns
  and nods, breathing, and small shoulder and torso shifts.
- wan_prompt must keep stable 1:1 head-and-shoulders framing with full head, hairline,
  chin, neck, and shoulders visible. Use a locked-off camera and consistent head size.
- wan_prompt should say the result looks like live video, not a static portrait or
  frozen frame.
- Avoid words such as zoom in, camera push-in, cropped face, extreme close-up,
  wide open mouth, exaggerated speaking, yelling, distorted face.
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
        reply = to_simplified_chinese(reply)
        if len(reply) > self.settings.max_reply_chars:
            reply = reply[: self.settings.max_reply_chars].rstrip(" ,.;:!?")
        if not instruct:
            instruct = "\u5e73\u7a33\u3001\u81ea\u7136\u3001\u6e05\u6670"
        instruct = to_simplified_chinese(instruct)
        if not wan_prompt:
            wan_prompt = self._fallback("")["wan_prompt"]
        return {
            "reply": reply,
            "cosyvoice_instruct": instruct,
            "wan_prompt": self._sanitize_wan_prompt(wan_prompt),
        }

    def default_video_prompt(self) -> str:
        return f"{VIDEO_IDENTITY_ANCHOR} {VIDEO_MOTION_ANCHOR}"

    def video_prompt_for_reply(self, prompt: str, spoken_text: str) -> str:
        prompt = self._sanitize_wan_prompt(prompt)
        prompt = re.sub(
            r'\s*The person clearly speaks this exact line from start to finish: ".*?"\. '
            r"The mouth opens and closes naturally, with visible lip shapes matching this line "
            r"and the supplied voice audio\.",
            "",
            prompt,
            flags=re.I,
        )
        line = re.sub(r"\s+", " ", spoken_text or "").strip()
        if not line:
            return prompt
        max_line_chars = 180
        if len(line) > max_line_chars:
            line = line[:max_line_chars].rstrip(" ,.;:!?，。；：！？") + "..."
        line = line.replace('"', "'")
        spoken_anchor = (
            f' The person clearly speaks this exact line from start to finish: "{line}". '
            "The mouth opens and closes naturally, with visible lip shapes matching this line "
            "and the supplied voice audio."
        )
        return re.sub(r"\s+", " ", f"{prompt} {spoken_anchor}").strip()

    def _sanitize_wan_prompt(self, prompt: str) -> str:
        banned = [
            "camera push-in",
            "camera push in",
            "push-in",
            "push in",
            "zoom in",
            "zooming in",
            "zoomin",
            "mild parallax",
            "parallax",
            "close-up crop",
            "cropped face",
            "extreme close-up",
            "wide open mouth",
            "yelling",
            "screaming",
            "exaggerated speaking",
            "distorted face",
        ]
        clean = prompt
        for word in banned:
            clean = re.sub(re.escape(word), "", clean, flags=re.I)
        clean_lower = clean.lower()
        if "preserve" not in clean_lower and "same identity" not in clean_lower:
            clean += " " + VIDEO_IDENTITY_ANCHOR
        if "visible but realistic motion" not in clean_lower or "locked-off camera" not in clean_lower:
            clean += " " + VIDEO_MOTION_ANCHOR
        return re.sub(r"\s+", " ", clean).strip()

    def _fallback(self, message: str) -> dict:
        msg = (message or "").strip()
        if self._looks_english(msg):
            reply = "I understand. Here is a direct, concise response to what you said."
            instruct = "calm, natural, clear"
        else:
            reply = "\u6211\u7406\u89e3\u4e86\uff0c\u6211\u4f1a\u76f4\u63a5\u3001\u7b80\u6d01\u5730\u56de\u5e94\u4f60\u7684\u5185\u5bb9\u3002"
            instruct = "\u5e73\u7a33\u3001\u81ea\u7136\u3001\u6e05\u6670"
        return {
            "reply": reply,
            "cosyvoice_instruct": instruct,
            "wan_prompt": self.default_video_prompt(),
        }

    def _looks_english(self, text: str) -> bool:
        letters = sum(1 for ch in text if "a" <= ch.lower() <= "z")
        cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        return letters > cjk
