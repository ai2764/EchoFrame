import json
import tempfile
import time
import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import Settings
from app.modules.lipsync import LipSyncModule
from app.modules.llm import LLMModule
from app.modules.tts import TTSModule
from app.modules.video import VideoGenerationModule
from app.paths import avatar_dir, media_url, new_id, run_dir
from app.schemas import AvatarResponse, ChatRequest, ChatResponse
from app.services.media import MediaTools
from app.services.run_control import RunState
from app.services.service_manager import ServiceManager


class TalkingAvatarPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.media = MediaTools(settings)
        self.services = ServiceManager(settings)
        self.llm = LLMModule(settings, self.services)
        self.tts = TTSModule(settings, self.services)
        self.video = VideoGenerationModule(settings, self.services)
        self.lipsync = LipSyncModule(settings, self.services)

    async def create_avatar(self, upload: UploadFile) -> AvatarResponse:
        suffix = Path(upload.filename or "avatar.png").suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise HTTPException(status_code=400, detail="upload a png, jpg, jpeg, or webp image")
        avatar_id = new_id("av")
        out_dir = avatar_dir(self.settings, avatar_id)
        source = out_dir / "source.png"
        out_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            while chunk := await upload.read(1024 * 1024):
                tmp.write(chunk)
            tmp_path = Path(tmp.name)
        try:
            self.media.save_square_avatar(tmp_path, source, size=self.settings.avatar_size)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"could not read image: {exc}") from exc
        finally:
            tmp_path.unlink(missing_ok=True)
        return AvatarResponse(avatar_id=avatar_id, image_url=media_url(self.settings, source))

    async def chat(self, req: ChatRequest) -> ChatResponse:
        result = None
        async for event in self.chat_events(req):
            if event.get("type") == "result":
                result = ChatResponse(**event["data"])
        if result is None:
            raise RuntimeError("generation finished without result")
        return result

    async def chat_events(self, req: ChatRequest, run_state: RunState | None = None) -> AsyncIterator[dict]:
        total_start = time.perf_counter()
        timings: dict[str, float] = {}
        resolution = self._output_resolution(req.resolution)
        wan_resolution = self._wan_resolution(resolution)
        av_dir = avatar_dir(self.settings, req.avatar_id)
        avatar_path = av_dir / "source.png"
        if not avatar_path.exists():
            raise HTTPException(status_code=404, detail="avatar not found")
        run_id = new_id("run")
        if run_state:
            run_state.set_run_id(run_id)
        out_dir = run_dir(self.settings, run_id)
        out_dir.mkdir(parents=True, exist_ok=True)

        manual_reply = (req.reply_override or "").strip()
        user_message = req.message.strip()
        if not manual_reply and not user_message:
            raise HTTPException(status_code=400, detail="message or manual reply is required")

        self._check_cancel(run_state)
        start = time.perf_counter()
        yield {"type": "stage", "stage": "llm", "status": "running"}
        await asyncio.sleep(0.01)
        plan = await self.llm.plan(user_message, manual_reply)
        timings["llm"] = round(time.perf_counter() - start, 3)
        yield {"type": "stage", "stage": "llm", "status": "done", "duration": timings["llm"]}
        await asyncio.sleep(0.01)
        voice_id = req.voice_id or self.settings.tts_default_voice_id

        audio_path = out_dir / "voice.wav"
        start = time.perf_counter()
        yield {"type": "stage", "stage": "tts", "status": "running"}
        await asyncio.sleep(0.01)
        self._check_cancel(run_state)
        tts_instruct = await self.tts.synthesize(
            text=plan["reply"],
            instruct=plan["cosyvoice_instruct"],
            voice_id=voice_id,
            output_path=audio_path,
        )
        timings["tts"] = round(time.perf_counter() - start, 3)
        yield {"type": "stage", "stage": "tts", "status": "done", "duration": timings["tts"]}
        await asyncio.sleep(0.01)

        start = time.perf_counter()
        yield {"type": "stage", "stage": "audio_probe", "status": "running"}
        await asyncio.sleep(0.01)
        self._check_cancel(run_state)
        audio_duration = await asyncio.to_thread(self.media.duration, audio_path)
        timings["audio_probe"] = round(time.perf_counter() - start, 3)
        yield {"type": "stage", "stage": "audio_probe", "status": "done", "duration": timings["audio_probe"]}
        await asyncio.sleep(0.01)

        start = time.perf_counter()
        yield {"type": "stage", "stage": "base_video", "status": "running"}
        await asyncio.sleep(0.01)
        self._check_cancel(run_state)
        base_result = await self.video.generate_base_video(
            mode=req.mode,
            avatar_path=avatar_path,
            prompt=plan["wan_prompt"],
            audio_duration=audio_duration,
            run_id=run_id,
            run_dir=out_dir,
            run_state=run_state,
            resolution=resolution,
            wan_resolution=wan_resolution,
        )
        timings["base_video"] = round(time.perf_counter() - start, 3)
        yield {"type": "stage", "stage": "base_video", "status": "done", "duration": timings["base_video"]}
        await asyncio.sleep(0.01)

        start = time.perf_counter()
        yield {"type": "stage", "stage": "musetalk", "status": "running"}
        await asyncio.sleep(0.01)
        self._check_cancel(run_state)
        talk_path = await self.lipsync.lip_sync(
            audio_path=audio_path,
            video_path=base_result.lip_sync_input_path,
            run_dir=out_dir,
            run_state=run_state,
        )
        timings["musetalk"] = round(time.perf_counter() - start, 3)
        yield {"type": "stage", "stage": "musetalk", "status": "done", "duration": timings["musetalk"]}
        await asyncio.sleep(0.01)
        timings["total"] = round(time.perf_counter() - total_start, 3)
        yield {"type": "stage", "stage": "total", "status": "done", "duration": timings["total"]}
        await asyncio.sleep(0.01)

        meta = {
            "run_id": run_id,
            "avatar_id": req.avatar_id,
            "message": user_message,
            "llm_skipped": bool(manual_reply),
            "mode": req.mode,
            "voice_id": voice_id,
            "resolution": resolution,
            "wan_render_resolution": wan_resolution,
            "musetalk_input": str(base_result.lip_sync_input_path.name),
            "musetalk_fps": base_result.fps,
            "musetalk_batch_size": self.settings.musetalk_batch_size,
            "reply": plan["reply"],
            "cosyvoice_instruct": plan["cosyvoice_instruct"],
            "tts_instruct_sent": tts_instruct,
            "wan_prompt": plan["wan_prompt"],
            "audio_duration": audio_duration,
            "timings": timings,
        }
        (out_dir / "reply.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        response = ChatResponse(
            run_id=run_id,
            reply=plan["reply"],
            cosyvoice_instruct=plan["cosyvoice_instruct"],
            tts_instruct_sent=tts_instruct,
            wan_prompt=plan["wan_prompt"],
            audio_duration=round(audio_duration, 3),
            timings=timings,
            audio_url=media_url(self.settings, audio_path),
            base_video_url=media_url(self.settings, base_result.base_path),
            video_url=media_url(self.settings, talk_path),
            mode=req.mode,
            resolution=resolution,
        )
        yield {"type": "result", "data": response.model_dump()}

    def _check_cancel(self, run_state: RunState | None) -> None:
        if run_state:
            run_state.check()

    def _output_resolution(self, requested: int | None) -> int:
        value = int(requested or self.settings.output_size)
        value = max(self.settings.resolution_min, min(self.settings.resolution_max, value))
        if value % 2:
            value -= 1
        return max(self.settings.resolution_min, value)

    def _wan_resolution(self, output_resolution: int) -> int:
        value = max(128, output_resolution)
        value = ((value + 15) // 16) * 16
        return min(self.settings.resolution_max, value)
