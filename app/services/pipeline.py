import json
import re
import shutil
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
from app.schemas import AvatarResponse, ChatRequest, ChatResponse, RegenerateRequest
from app.services.media import MediaTools
from app.services.run_control import RunState
from app.services.service_manager import ServiceManager


LTX_IA2V_BACKENDS = {"ltx_ia2v", "ltx_ia2v_q4"}


class TalkingAvatarPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.media = MediaTools(settings)
        self.services = ServiceManager(settings)
        self.llm = LLMModule(settings, self.services)
        self.tts = TTSModule(settings, self.services)
        self.video = VideoGenerationModule(settings, self.services)
        self.lipsync = LipSyncModule(settings, self.services)
        self._background_tasks: set[asyncio.Task] = set()

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

    async def regenerate(self, req: RegenerateRequest) -> ChatResponse:
        result = None
        async for event in self.regenerate_events(req):
            if event.get("type") == "result":
                result = ChatResponse(**event["data"])
        if result is None:
            raise RuntimeError("regeneration finished without result")
        return result

    async def chat_events(self, req: ChatRequest, run_state: RunState | None = None) -> AsyncIterator[dict]:
        total_start = time.perf_counter()
        timings: dict[str, float] = {}
        resolution = self._output_resolution(req.resolution)
        wan_resolution = self._wan_resolution(resolution)
        final_video_backend = req.final_video_backend or self.settings.final_video_backend
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

        if final_video_backend == "musetalk":
            yield {"type": "stage", "stage": "pre_wan_comfy_release", "status": "running"}
            await asyncio.sleep(0.01)
            await self._release_comfy_for_musetalk(timings, "pre_wan_comfy_release", run_state)
            yield {
                "type": "stage",
                "stage": "pre_wan_comfy_release",
                "status": "done",
                "duration": timings["pre_wan_comfy_release"],
            }
            await asyncio.sleep(0.01)

        self._check_cancel(run_state)
        start = time.perf_counter()
        yield {"type": "stage", "stage": "llm", "status": "running"}
        await asyncio.sleep(0.01)
        plan = await self.llm.plan(user_message, manual_reply)
        timings["llm"] = round(time.perf_counter() - start, 3)
        yield {"type": "stage", "stage": "llm", "status": "done", "duration": timings["llm"]}
        await asyncio.sleep(0.01)
        voice_id = self._voice_id(req, plan["reply"])
        video_prompt = plan["wan_prompt"]

        native_ltx_audio = final_video_backend == "ltx_native_audio"
        audio_path = out_dir / ("voice.m4a" if native_ltx_audio else "voice.wav")
        if native_ltx_audio:
            audio_duration = self._estimate_ltx_native_audio_duration(plan["reply"])
            tts_instruct = "LTX native audio (no external TTS)"
        else:
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
            if audio_duration < 0.2:
                raise RuntimeError("TTS audio is too short for video generation")
            timings["audio_probe"] = round(time.perf_counter() - start, 3)
            yield {"type": "stage", "stage": "audio_probe", "status": "done", "duration": timings["audio_probe"]}
            await asyncio.sleep(0.01)

        actual_resolution = resolution
        if final_video_backend == "ltx_native_audio":
            video_prompt = self.llm.native_audio_prompt_for_reply(plan["wan_prompt"], plan["reply"])
            self._check_cancel(run_state)
            yield {"type": "stage", "stage": "ltx_native_audio", "status": "running"}
            await asyncio.sleep(0.01)
            start = time.perf_counter()
            ltx_resolution = self.video.ltx_output_size(resolution)
            base_path = await self.video.generate_ltx_native_audio_video(
                avatar_path=avatar_path,
                prompt=video_prompt,
                duration=audio_duration,
                run_id=run_id,
                run_dir=out_dir,
                resolution=resolution,
                run_state=run_state,
            )
            talk_path = out_dir / "final.mp4"
            shutil.copy2(base_path, talk_path)
            timings["ltx_native_audio"] = round(time.perf_counter() - start, 3)
            yield {
                "type": "stage",
                "stage": "ltx_native_audio",
                "status": "done",
                "duration": timings["ltx_native_audio"],
            }
            await asyncio.sleep(0.01)

            start = time.perf_counter()
            yield {"type": "stage", "stage": "native_audio_export", "status": "running"}
            await asyncio.sleep(0.01)
            self._check_cancel(run_state)
            await asyncio.to_thread(self.media.extract_audio, talk_path, audio_path)
            audio_duration = await asyncio.to_thread(self.media.duration, audio_path)
            if audio_duration < 0.2:
                raise RuntimeError("LTX native audio is too short for video generation")
            timings["native_audio_export"] = round(time.perf_counter() - start, 3)
            yield {
                "type": "stage",
                "stage": "native_audio_export",
                "status": "done",
                "duration": timings["native_audio_export"],
            }
            await asyncio.sleep(0.01)

            actual_resolution = ltx_resolution
            base_meta = {
                "ltx_audio_mode": "native",
                "ltx_generated_audio": audio_path.name,
                "ltx_native_audio_estimated_duration": round(self._estimate_ltx_native_audio_duration(plan["reply"]), 3),
                "ltx_width": ltx_resolution,
                "ltx_height": ltx_resolution,
                "ltx_fps": self.settings.ltx_fps,
            }
        elif final_video_backend in LTX_IA2V_BACKENDS:
            ltx_q4_mode = final_video_backend == "ltx_ia2v_q4"
            video_prompt = self.llm.video_prompt_for_reply(plan["wan_prompt"], plan["reply"])
            self._check_cancel(run_state)
            yield {"type": "stage", "stage": "pre_ltx_vram_release", "status": "running"}
            await asyncio.sleep(0.01)
            await self._release_vram_for_ltx(timings, run_state, unload_tts=not ltx_q4_mode)
            yield {
                "type": "stage",
                "stage": "pre_ltx_vram_release",
                "status": "done",
                "duration": timings.get("pre_ltx_vram_release", 0.0),
            }
            await asyncio.sleep(0.01)
            yield {"type": "stage", "stage": "ltx_ia2v", "status": "running"}
            await asyncio.sleep(0.01)
            start = time.perf_counter()
            ltx_resolution = self.video.ltx_output_size(resolution)
            base_path = await self.video.generate_ltx_ia2v_video(
                avatar_path=avatar_path,
                audio_path=audio_path,
                prompt=video_prompt,
                audio_duration=audio_duration,
                run_id=run_id,
                run_dir=out_dir,
                resolution=resolution,
                run_state=run_state,
                ltx_model_format="gguf" if ltx_q4_mode else None,
                unload_after=False if ltx_q4_mode else None,
            )
            talk_path = out_dir / "final.mp4"
            await asyncio.to_thread(self.media.mux_audio, base_path, audio_path, talk_path)
            timings["ltx_ia2v"] = round(time.perf_counter() - start, 3)
            yield {"type": "stage", "stage": "ltx_ia2v", "status": "done", "duration": timings["ltx_ia2v"]}
            await asyncio.sleep(0.01)

            actual_resolution = ltx_resolution
            base_meta = {
                "ltx_audio_mode": "external_tts",
                "ltx_input_audio": audio_path.name,
                "ltx_width": ltx_resolution,
                "ltx_height": ltx_resolution,
                "ltx_fps": self.settings.ltx_fps,
                "ltx_model_format": "gguf" if ltx_q4_mode else self.settings.ltx_model_format,
            }
        else:
            start = time.perf_counter()
            yield {"type": "stage", "stage": "base_video", "status": "running"}
            await asyncio.sleep(0.01)
            self._check_cancel(run_state)
            base_result = await self.video.generate_base_video(
                mode=req.mode,
                avatar_path=avatar_path,
                prompt=video_prompt,
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

            if req.mode in {"wan", "wan_loop"}:
                yield {"type": "stage", "stage": "post_wan_comfy_release", "status": "running"}
                await asyncio.sleep(0.01)
                await self._release_comfy_for_musetalk(timings, "post_wan_comfy_release", run_state)
                yield {
                    "type": "stage",
                    "stage": "post_wan_comfy_release",
                    "status": "done",
                    "duration": timings["post_wan_comfy_release"],
                }
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
            base_path = base_result.base_path
            base_meta = {
                "musetalk_input": str(base_result.lip_sync_input_path.name),
                "musetalk_fps": base_result.fps,
                "musetalk_batch_size": self.settings.musetalk_batch_size,
            }
        timings["total"] = round(time.perf_counter() - total_start, 3)
        yield {"type": "stage", "stage": "total", "status": "done", "duration": timings["total"]}
        await asyncio.sleep(0.01)

        meta = {
            "run_id": run_id,
            "avatar_id": req.avatar_id,
            "message": user_message,
            "llm_skipped": bool(manual_reply),
            "mode": req.mode,
            "final_video_backend": final_video_backend,
            "voice_id": voice_id,
            "resolution": actual_resolution,
            "wan_render_resolution": wan_resolution,
            "reply": plan["reply"],
            "cosyvoice_instruct": plan["cosyvoice_instruct"],
            "tts_instruct_sent": tts_instruct,
            "wan_prompt": video_prompt,
            "audio_duration": audio_duration,
            "timings": timings,
        }
        meta.update(base_meta)
        (out_dir / "reply.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        response = ChatResponse(
            run_id=run_id,
            reply=plan["reply"],
            cosyvoice_instruct=plan["cosyvoice_instruct"],
            tts_instruct_sent=tts_instruct,
            wan_prompt=video_prompt,
            audio_duration=round(audio_duration, 3),
            timings=dict(timings),
            audio_url=media_url(self.settings, audio_path),
            base_video_url=media_url(self.settings, base_path),
            video_url=media_url(self.settings, talk_path),
            mode=req.mode,
            resolution=actual_resolution,
            final_video_backend=final_video_backend,
        )
        yield {"type": "result", "data": response.model_dump()}
        if final_video_backend == "ltx_ia2v":
            self._schedule_tts_reload_after_ltx(timings, run_state)

    async def regenerate_events(self, req: RegenerateRequest, run_state: RunState | None = None) -> AsyncIterator[dict]:
        previous = self._load_run_meta(req.run_id)
        total_start = time.perf_counter()
        timings: dict[str, float] = {}
        avatar_id = str(previous.get("avatar_id") or "")
        av_dir = avatar_dir(self.settings, avatar_id)
        avatar_path = av_dir / "source.png"
        if not avatar_path.exists():
            raise HTTPException(status_code=404, detail="avatar not found")

        run_id = new_id("run")
        if run_state:
            run_state.set_run_id(run_id)
        out_dir = run_dir(self.settings, run_id)
        out_dir.mkdir(parents=True, exist_ok=True)

        user_message = str(previous.get("message") or "").strip()
        mode = str(previous.get("mode") or "fast")
        final_video_backend = self._run_backend(previous)
        requested_resolution = self._output_resolution(int(previous.get("resolution") or self.settings.output_size))
        wan_resolution = int(previous.get("wan_render_resolution") or self._wan_resolution(requested_resolution))
        voice_id = str(previous.get("voice_id") or self.settings.tts_default_voice_id)
        plan = {
            "reply": str(previous.get("reply") or "").strip(),
            "cosyvoice_instruct": str(previous.get("cosyvoice_instruct") or "").strip(),
            "wan_prompt": str(previous.get("wan_prompt") or self.llm.client.default_video_prompt()).strip(),
        }
        if not plan["reply"]:
            raise HTTPException(status_code=400, detail="previous run has no reply to reuse")

        if final_video_backend == "musetalk":
            yield {"type": "stage", "stage": "pre_wan_comfy_release", "status": "running"}
            await asyncio.sleep(0.01)
            await self._release_comfy_for_musetalk(timings, "pre_wan_comfy_release", run_state)
            yield {
                "type": "stage",
                "stage": "pre_wan_comfy_release",
                "status": "done",
                "duration": timings["pre_wan_comfy_release"],
            }
            await asyncio.sleep(0.01)

        self._check_cancel(run_state)
        if req.stage == "llm":
            if not user_message:
                raise HTTPException(status_code=400, detail="previous run has no chat message for LLM regeneration")
            start = time.perf_counter()
            yield {"type": "stage", "stage": "llm", "status": "running"}
            await asyncio.sleep(0.01)
            plan = await self.llm.plan(user_message, "")
            timings["llm"] = round(time.perf_counter() - start, 3)
            yield {"type": "stage", "stage": "llm", "status": "done", "duration": timings["llm"]}
            await asyncio.sleep(0.01)
        else:
            timings["llm"] = 0.0
            yield {"type": "stage", "stage": "llm", "status": "done", "duration": 0.0}
            await asyncio.sleep(0.01)

        native_ltx_audio = final_video_backend == "ltx_native_audio"
        audio_path = out_dir / ("voice.m4a" if native_ltx_audio else "voice.wav")
        if native_ltx_audio:
            previous_duration = float(previous.get("audio_duration") or 0.0)
            if req.stage in {"llm", "tts"} or previous_duration <= 0:
                audio_duration = self._estimate_ltx_native_audio_duration(plan["reply"])
            else:
                audio_duration = previous_duration
            tts_instruct = "LTX native audio (no external TTS)"
        else:
            if req.stage in {"llm", "tts"}:
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
            else:
                previous_audio = self._previous_artifact(req.run_id, str(previous.get("ltx_input_audio") or "voice.wav"))
                if not previous_audio.exists():
                    raise HTTPException(status_code=404, detail="previous run audio was not found")
                shutil.copy2(previous_audio, audio_path)
                tts_instruct = str(previous.get("tts_instruct_sent") or "")
                timings["tts"] = 0.0
                yield {"type": "stage", "stage": "tts", "status": "done", "duration": 0.0}
                await asyncio.sleep(0.01)

            start = time.perf_counter()
            yield {"type": "stage", "stage": "audio_probe", "status": "running"}
            await asyncio.sleep(0.01)
            self._check_cancel(run_state)
            audio_duration = await asyncio.to_thread(self.media.duration, audio_path)
            if audio_duration < 0.2:
                raise RuntimeError("TTS audio is too short for video generation")
            timings["audio_probe"] = round(time.perf_counter() - start, 3)
            yield {"type": "stage", "stage": "audio_probe", "status": "done", "duration": timings["audio_probe"]}
            await asyncio.sleep(0.01)

        actual_resolution = requested_resolution
        video_prompt = plan["wan_prompt"]
        if final_video_backend == "ltx_native_audio":
            ltx_requested_resolution = self._previous_ltx_resolution(previous, requested_resolution)
            video_prompt = self.llm.native_audio_prompt_for_reply(plan["wan_prompt"], plan["reply"])
            self._check_cancel(run_state)
            yield {"type": "stage", "stage": "ltx_native_audio", "status": "running"}
            await asyncio.sleep(0.01)
            start = time.perf_counter()
            ltx_resolution = self.video.ltx_output_size(ltx_requested_resolution)
            base_path = await self.video.generate_ltx_native_audio_video(
                avatar_path=avatar_path,
                prompt=video_prompt,
                duration=audio_duration,
                run_id=run_id,
                run_dir=out_dir,
                resolution=ltx_requested_resolution,
                run_state=run_state,
            )
            talk_path = out_dir / "final.mp4"
            shutil.copy2(base_path, talk_path)
            timings["ltx_native_audio"] = round(time.perf_counter() - start, 3)
            yield {
                "type": "stage",
                "stage": "ltx_native_audio",
                "status": "done",
                "duration": timings["ltx_native_audio"],
            }
            await asyncio.sleep(0.01)

            start = time.perf_counter()
            yield {"type": "stage", "stage": "native_audio_export", "status": "running"}
            await asyncio.sleep(0.01)
            self._check_cancel(run_state)
            await asyncio.to_thread(self.media.extract_audio, talk_path, audio_path)
            audio_duration = await asyncio.to_thread(self.media.duration, audio_path)
            if audio_duration < 0.2:
                raise RuntimeError("LTX native audio is too short for video generation")
            timings["native_audio_export"] = round(time.perf_counter() - start, 3)
            yield {
                "type": "stage",
                "stage": "native_audio_export",
                "status": "done",
                "duration": timings["native_audio_export"],
            }
            await asyncio.sleep(0.01)

            actual_resolution = ltx_resolution
            base_meta = {
                "ltx_audio_mode": "native",
                "ltx_generated_audio": audio_path.name,
                "ltx_native_audio_estimated_duration": round(self._estimate_ltx_native_audio_duration(plan["reply"]), 3),
                "ltx_width": ltx_resolution,
                "ltx_height": ltx_resolution,
                "ltx_fps": self.settings.ltx_fps,
            }
        elif final_video_backend in LTX_IA2V_BACKENDS:
            ltx_q4_mode = final_video_backend == "ltx_ia2v_q4"
            ltx_requested_resolution = self._previous_ltx_resolution(previous, requested_resolution)
            video_prompt = self.llm.video_prompt_for_reply(plan["wan_prompt"], plan["reply"])
            self._check_cancel(run_state)
            yield {"type": "stage", "stage": "pre_ltx_vram_release", "status": "running"}
            await asyncio.sleep(0.01)
            await self._release_vram_for_ltx(timings, run_state, unload_tts=not ltx_q4_mode)
            yield {
                "type": "stage",
                "stage": "pre_ltx_vram_release",
                "status": "done",
                "duration": timings.get("pre_ltx_vram_release", 0.0),
            }
            await asyncio.sleep(0.01)
            yield {"type": "stage", "stage": "ltx_ia2v", "status": "running"}
            await asyncio.sleep(0.01)
            start = time.perf_counter()
            ltx_resolution = self.video.ltx_output_size(ltx_requested_resolution)
            base_path = await self.video.generate_ltx_ia2v_video(
                avatar_path=avatar_path,
                audio_path=audio_path,
                prompt=video_prompt,
                audio_duration=audio_duration,
                run_id=run_id,
                run_dir=out_dir,
                resolution=ltx_requested_resolution,
                run_state=run_state,
                ltx_model_format="gguf" if ltx_q4_mode else None,
                unload_after=False if ltx_q4_mode else None,
            )
            talk_path = out_dir / "final.mp4"
            await asyncio.to_thread(self.media.mux_audio, base_path, audio_path, talk_path)
            timings["ltx_ia2v"] = round(time.perf_counter() - start, 3)
            yield {"type": "stage", "stage": "ltx_ia2v", "status": "done", "duration": timings["ltx_ia2v"]}
            await asyncio.sleep(0.01)

            actual_resolution = ltx_resolution
            base_meta = {
                "ltx_audio_mode": "external_tts",
                "ltx_input_audio": audio_path.name,
                "ltx_width": ltx_resolution,
                "ltx_height": ltx_resolution,
                "ltx_fps": self.settings.ltx_fps,
                "ltx_model_format": "gguf" if ltx_q4_mode else self.settings.ltx_model_format,
            }
        else:
            start = time.perf_counter()
            yield {"type": "stage", "stage": "base_video", "status": "running"}
            await asyncio.sleep(0.01)
            self._check_cancel(run_state)
            base_result = await self.video.generate_base_video(
                mode=mode,
                avatar_path=avatar_path,
                prompt=video_prompt,
                audio_duration=audio_duration,
                run_id=run_id,
                run_dir=out_dir,
                run_state=run_state,
                resolution=requested_resolution,
                wan_resolution=wan_resolution,
            )
            timings["base_video"] = round(time.perf_counter() - start, 3)
            yield {"type": "stage", "stage": "base_video", "status": "done", "duration": timings["base_video"]}
            await asyncio.sleep(0.01)

            if mode in {"wan", "wan_loop"}:
                yield {"type": "stage", "stage": "post_wan_comfy_release", "status": "running"}
                await asyncio.sleep(0.01)
                await self._release_comfy_for_musetalk(timings, "post_wan_comfy_release", run_state)
                yield {
                    "type": "stage",
                    "stage": "post_wan_comfy_release",
                    "status": "done",
                    "duration": timings["post_wan_comfy_release"],
                }
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
            base_path = base_result.base_path
            base_meta = {
                "musetalk_input": str(base_result.lip_sync_input_path.name),
                "musetalk_fps": base_result.fps,
                "musetalk_batch_size": self.settings.musetalk_batch_size,
            }

        timings["total"] = round(time.perf_counter() - total_start, 3)
        yield {"type": "stage", "stage": "total", "status": "done", "duration": timings["total"]}
        await asyncio.sleep(0.01)

        meta = {
            "run_id": run_id,
            "source_run_id": req.run_id,
            "regenerated_stage": req.stage,
            "avatar_id": avatar_id,
            "message": user_message,
            "llm_skipped": req.stage != "llm",
            "mode": mode,
            "final_video_backend": final_video_backend,
            "voice_id": voice_id,
            "resolution": actual_resolution,
            "wan_render_resolution": wan_resolution,
            "reply": plan["reply"],
            "cosyvoice_instruct": plan["cosyvoice_instruct"],
            "tts_instruct_sent": tts_instruct,
            "wan_prompt": video_prompt,
            "audio_duration": audio_duration,
            "timings": timings,
        }
        meta.update(base_meta)
        (out_dir / "reply.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        response = ChatResponse(
            run_id=run_id,
            reply=plan["reply"],
            cosyvoice_instruct=plan["cosyvoice_instruct"],
            tts_instruct_sent=tts_instruct,
            wan_prompt=video_prompt,
            audio_duration=round(audio_duration, 3),
            timings=dict(timings),
            audio_url=media_url(self.settings, audio_path),
            base_video_url=media_url(self.settings, base_path),
            video_url=media_url(self.settings, talk_path),
            mode=mode,
            resolution=actual_resolution,
            final_video_backend=final_video_backend,
        )
        yield {"type": "result", "data": response.model_dump()}
        if final_video_backend == "ltx_ia2v":
            self._schedule_tts_reload_after_ltx(timings, run_state)

    def _check_cancel(self, run_state: RunState | None) -> None:
        if run_state:
            run_state.check()

    async def _release_vram_for_ltx(
        self,
        timings: dict[str, float],
        run_state: RunState | None = None,
        unload_tts: bool | None = None,
    ) -> None:
        should_unload_tts = self.settings.ltx_unload_tts_before_video if unload_tts is None else unload_tts
        if not (self.settings.ltx_unload_llm_before_video or should_unload_tts):
            return
        start = time.perf_counter()
        self._check_cancel(run_state)
        if self.settings.ltx_unload_llm_before_video:
            await self.services.unload_llm_for_ltx()
        self._check_cancel(run_state)
        if should_unload_tts:
            await self.services.unload_tts_for_ltx()
        timings["pre_ltx_vram_release"] = round(time.perf_counter() - start, 3)
        self._check_cancel(run_state)

    async def _release_comfy_for_musetalk(
        self,
        timings: dict[str, float],
        key: str,
        run_state: RunState | None = None,
    ) -> None:
        start = time.perf_counter()
        self._check_cancel(run_state)
        await self.video.comfy.free_memory()
        timings[key] = round(time.perf_counter() - start, 3)
        self._check_cancel(run_state)

    def _schedule_tts_reload_after_ltx(self, timings: dict[str, float], run_state: RunState | None = None) -> None:
        stage = "post_ltx_tts_preload"
        if not self.settings.ltx_reload_tts_after_video:
            timings[stage] = 0.0
            if run_state:
                run_state.record_stage({"stage": stage, "status": "done", "duration": 0.0})
            return
        if run_state:
            run_state.record_stage({"stage": stage, "status": "running"})
        task = asyncio.create_task(self._reload_tts_after_ltx_background(timings, run_state))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _reload_tts_after_ltx_background(
        self,
        timings: dict[str, float],
        run_state: RunState | None = None,
    ) -> None:
        status, duration = await self._reload_tts_after_ltx(timings)
        if run_state:
            run_state.record_stage(
                {
                    "stage": "post_ltx_tts_preload",
                    "status": status,
                    "duration": duration,
                }
            )

    async def _reload_tts_after_ltx(self, timings: dict[str, float]) -> tuple[str, float]:
        if not self.settings.ltx_reload_tts_after_video:
            timings["post_ltx_tts_preload"] = 0.0
            return "done", 0.0
        start = time.perf_counter()
        try:
            await self.services.preload_tts_after_ltx()
        except Exception:
            duration = round(time.perf_counter() - start, 3)
            timings["post_ltx_tts_preload_failed"] = duration
            return "failed", duration
        duration = round(time.perf_counter() - start, 3)
        timings["post_ltx_tts_preload"] = duration
        return "done", duration

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

    def _voice_id(self, req: ChatRequest, spoken_text: str = "") -> str:
        if req.voice_id:
            return req.voice_id
        language = self._voice_language(spoken_text or req.reply_override or req.message)
        if language == "zh":
            if req.voice == "male":
                return self.settings.tts_zh_male_voice_id or self.settings.tts_male_voice_id
            return self.settings.tts_zh_female_voice_id or self.settings.tts_female_voice_id
        if req.voice == "male":
            return self.settings.tts_en_male_voice_id or self.settings.tts_male_voice_id
        return self.settings.tts_en_female_voice_id or self.settings.tts_female_voice_id or self.settings.tts_default_voice_id

    def _voice_language(self, text: str) -> str:
        return "zh" if any("\u4e00" <= char <= "\u9fff" for char in text) else "en"

    def _estimate_ltx_native_audio_duration(self, text: str) -> float:
        cleaned = re.sub(r"\s+", " ", text or "").strip()
        cjk_chars = sum(1 for char in cleaned if "\u4e00" <= char <= "\u9fff")
        latin_words = len(re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", cleaned))
        punctuation_pauses = len(re.findall(r"[,.!?;:\u3002\uff0c\uff01\uff1f\uff1b\uff1a]", cleaned)) * 0.18
        estimated = (cjk_chars / 4.6) + (latin_words / 2.45) + punctuation_pauses + 0.45
        minimum = max(0.5, float(self.settings.ltx_native_audio_min_seconds))
        maximum = max(minimum, float(self.settings.ltx_native_audio_max_seconds))
        return round(max(minimum, min(maximum, estimated)), 3)

    def _run_backend(self, previous: dict) -> str:
        backend = str(previous.get("final_video_backend") or "").strip()
        if backend in {"ltx_ia2v", "ltx_ia2v_q4", "ltx_native_audio", "musetalk"}:
            return backend
        if previous.get("ltx_audio_mode") == "native" or previous.get("ltx_generated_audio"):
            return "ltx_native_audio"
        if previous.get("ltx_input_audio") or previous.get("ltx_width") or previous.get("ltx_height"):
            return "ltx_ia2v"
        return "musetalk"

    def _previous_ltx_resolution(self, previous: dict, fallback: int) -> int:
        for key in ("ltx_width", "ltx_height", "resolution"):
            value = previous.get(key)
            if value:
                return self.video.ltx_output_size(int(value))
        return self.video.ltx_output_size(fallback)

    def _load_run_meta(self, run_id: str) -> dict:
        path = self._previous_artifact(run_id, "reply.json")
        if not path.exists():
            raise HTTPException(status_code=404, detail="previous run was not found")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="previous run metadata is invalid") from exc

    def _previous_artifact(self, run_id: str, name: str) -> Path:
        if Path(run_id).name != run_id or "/" in run_id or "\\" in run_id:
            raise HTTPException(status_code=400, detail="previous run id is invalid")
        base = run_dir(self.settings, run_id).resolve()
        target = (base / name).resolve()
        try:
            target.relative_to(base)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="previous run artifact path is invalid") from exc
        return target
