import math
import random
import shutil
import struct
import time
import zlib
from pathlib import Path

import httpx

from app.config import Settings
from app.services.run_control import RunState


class ComfyClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def health(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(self.settings.comfy_url.rstrip("/") + "/queue")
            if r.status_code == 200:
                return True, "online"
            return False, f"HTTP {r.status_code}"
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def ltx_frame_count(duration: float, fps: int) -> int:
        raw_frames = max(9, int(math.ceil(max(0.25, duration) * fps)) + 1)
        remainder = (raw_frames - 1) % 8
        if remainder:
            raw_frames += 8 - remainder
        return raw_frames

    def _ltx_checkpoint_name(self) -> str:
        if self.settings.ltx_profile == "fast":
            return self.settings.ltx_fast_checkpoint
        return self.settings.ltx_checkpoint

    def _ltx_uses_gguf(self) -> bool:
        return self.settings.ltx_model_format == "gguf" or self._ltx_checkpoint_name().lower().endswith(".gguf")

    def _ltx_gguf_name(self) -> str:
        if self._ltx_checkpoint_name().lower().endswith(".gguf"):
            return self._ltx_checkpoint_name()
        return self.settings.ltx_gguf_model

    def _ltx_lora_name(self) -> str:
        if self.settings.ltx_profile != "quality" or self.settings.ltx_lora_strength <= 0:
            return ""
        candidates = []
        for name in (self.settings.ltx_lora, self.settings.ltx_lora_fallback):
            name = str(name).strip()
            if name and name not in candidates:
                candidates.append(name)
        models_dir = self._comfy_models_dir()
        for name in candidates:
            if (models_dir / "loras" / name).exists():
                return name
        return candidates[0] if candidates else ""

    def _comfy_models_dir(self) -> Path:
        if self.settings.comfy_models_dir:
            return self.settings.comfy_models_dir
        if self.settings.comfy_base_dir:
            return self.settings.comfy_base_dir / "models"
        input_parent = self.settings.comfy_input_dir.parent
        if input_parent.name.lower() == "input":
            input_parent = input_parent.parent
        if (input_parent / "models").exists():
            return input_parent / "models"
        return self.settings.comfy_root / "models"

    async def generate_wan_base(
        self,
        image_path: Path,
        prompt: str,
        length: int,
        run_id: str,
        run_dir: Path,
        run_state: RunState | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> Path:
        if run_state:
            run_state.check()
        self.settings.comfy_input_dir.mkdir(parents=True, exist_ok=True)
        image_name = f"{run_id}_avatar.png"
        shutil.copy2(image_path, self.settings.comfy_input_dir / image_name)
        prefix = f"{run_id}_wan"
        workflow = self._wan_workflow(
            image_name=image_name,
            prompt=prompt,
            video_prefix=prefix,
            length=length,
            seed=random.randint(1, 999999999),
            width=width,
            height=height,
        )
        try:
            if run_state:
                run_state.check()
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(self.settings.comfy_url.rstrip("/") + "/prompt", json=workflow)
            if r.status_code != 200:
                raise RuntimeError(f"ComfyUI HTTP {r.status_code}: {r.text[:500]}")
            body = r.json()
            prompt_id = body.get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"ComfyUI rejected workflow: {body}")
            if run_state:
                run_state.set_comfy_prompt(self.settings.comfy_url, prompt_id)
            outputs = await self._poll(prompt_id, run_state)
            output = self._find_video(outputs)
            if not output:
                raise RuntimeError("ComfyUI completed but no video output was found")
            dst = run_dir / "wan_raw.mp4"
            shutil.copy2(output, dst)
            return dst
        finally:
            if self.settings.comfy_unload_after_wan:
                await self.free_memory()

    async def generate_ltx_ia2v(
        self,
        image_path: Path,
        audio_path: Path,
        prompt: str,
        audio_duration: float,
        run_id: str,
        run_dir: Path,
        run_state: RunState | None = None,
        width: int | None = None,
        height: int | None = None,
        fps: int | None = None,
        unload_after: bool | None = None,
    ) -> Path:
        if run_state:
            run_state.check()
        self.settings.comfy_input_dir.mkdir(parents=True, exist_ok=True)
        image_name = f"{run_id}_avatar.png"
        audio_name = f"{run_id}_voice{audio_path.suffix or '.wav'}"
        shutil.copy2(image_path, self.settings.comfy_input_dir / image_name)
        shutil.copy2(audio_path, self.settings.comfy_input_dir / audio_name)
        prefix = f"{run_id}_ltx_ia2v"
        workflow = self._ltx_ia2v_workflow(
            image_name=image_name,
            audio_name=audio_name,
            prompt=prompt,
            video_prefix=prefix,
            duration=audio_duration,
            seed=random.randint(1, 999999999),
            width=width,
            height=height,
            fps=fps,
        )
        try:
            if run_state:
                run_state.check()
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(self.settings.comfy_url.rstrip("/") + "/prompt", json=workflow)
            if r.status_code != 200:
                raise RuntimeError(f"ComfyUI HTTP {r.status_code}: {r.text[:500]}")
            body = r.json()
            prompt_id = body.get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"ComfyUI rejected workflow: {body}")
            if run_state:
                run_state.set_comfy_prompt(self.settings.comfy_url, prompt_id)
            outputs = await self._poll(prompt_id, run_state)
            output = self._find_video(outputs)
            if not output:
                raise RuntimeError("ComfyUI completed but no LTX video output was found")
            dst = run_dir / "ltx_raw.mp4"
            shutil.copy2(output, dst)
            return dst
        finally:
            should_unload = self.settings.ltx_unload_after_video if unload_after is None else unload_after
            if should_unload:
                await self.free_memory()

    async def generate_ltx_native_audio(
        self,
        image_path: Path,
        prompt: str,
        duration: float,
        run_id: str,
        run_dir: Path,
        run_state: RunState | None = None,
        width: int | None = None,
        height: int | None = None,
        fps: int | None = None,
        unload_after: bool | None = None,
    ) -> Path:
        if run_state:
            run_state.check()
        self.settings.comfy_input_dir.mkdir(parents=True, exist_ok=True)
        image_name = f"{run_id}_avatar.png"
        shutil.copy2(image_path, self.settings.comfy_input_dir / image_name)
        prefix = f"{run_id}_ltx_native_audio"
        workflow = self._ltx_ia2v_workflow(
            image_name=image_name,
            audio_name="",
            prompt=prompt,
            video_prefix=prefix,
            duration=duration,
            seed=random.randint(1, 999999999),
            width=width,
            height=height,
            fps=fps,
            native_audio=True,
        )
        try:
            if run_state:
                run_state.check()
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(self.settings.comfy_url.rstrip("/") + "/prompt", json=workflow)
            if r.status_code != 200:
                raise RuntimeError(f"ComfyUI HTTP {r.status_code}: {r.text[:500]}")
            body = r.json()
            prompt_id = body.get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"ComfyUI rejected workflow: {body}")
            if run_state:
                run_state.set_comfy_prompt(self.settings.comfy_url, prompt_id)
            outputs = await self._poll(prompt_id, run_state)
            output = self._find_video(outputs)
            if not output:
                raise RuntimeError("ComfyUI completed but no native-audio LTX video output was found")
            dst = run_dir / "ltx_native_audio.mp4"
            shutil.copy2(output, dst)
            return dst
        finally:
            should_unload = self.settings.ltx_unload_after_video if unload_after is None else unload_after
            if should_unload:
                await self.free_memory()

    async def prepare_ltx_native_audio(self, resolution: int | None = None) -> None:
        run_dir = self.settings.abs_data_dir / "prepare"
        run_dir.mkdir(parents=True, exist_ok=True)
        image_path = run_dir / "ltx_prepare_avatar.png"
        self._write_solid_png(image_path, 256, 256)
        size = max(256, int(resolution or min(self.settings.ltx_width, self.settings.ltx_height)))
        if size % 2:
            size -= 1
        await self.generate_ltx_native_audio(
            image_path=image_path,
            prompt=(
                "front-facing talking portrait warmup, clean frame, no subtitles, no captions, "
                "no on-screen text, no watermark"
            ),
            duration=0.25,
            run_id=f"prepare_ltx_{int(time.time())}",
            run_dir=run_dir,
            width=size,
            height=size,
            fps=self.settings.ltx_fps,
            unload_after=False,
        )

    async def _poll(self, prompt_id: str, run_state: RunState | None = None) -> dict:
        deadline = time.time() + self.settings.comfy_timeout_seconds
        async with httpx.AsyncClient(timeout=10.0) as client:
            while time.time() < deadline:
                if run_state:
                    run_state.check()
                await self._sleep(1.0)
                if run_state:
                    run_state.check()
                try:
                    r = await client.get(self.settings.comfy_url.rstrip("/") + f"/history/{prompt_id}")
                    data = r.json()
                except Exception:
                    continue
                if prompt_id not in data:
                    continue
                entry = data[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI generation failed: {status.get('messages', [])}")
                if status.get("completed"):
                    return entry.get("outputs", {})
        raise RuntimeError("Timed out waiting for ComfyUI")

    async def _sleep(self, seconds: float) -> None:
        import asyncio

        await asyncio.sleep(seconds)

    async def free_memory(self) -> None:
        payload = {"unload_models": True, "free_memory": True}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(self.settings.comfy_url.rstrip("/") + "/free", json=payload)
        except Exception:
            pass

    async def interrupt_and_free(self) -> None:
        base = self.settings.comfy_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(base + "/interrupt")
        except Exception:
            pass
        await self.free_memory()

    def _write_solid_png(self, path: Path, width: int, height: int) -> None:
        def chunk(tag: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + tag
                + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
            )

        row = b"\x00" + bytes([128, 128, 128]) * width
        raw = row * height
        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b"")
        )
        path.write_bytes(png)

    def _find_video(self, outputs: dict) -> Path | None:
        for node in outputs.values():
            for key in ("gifs", "videos"):
                for item in node.get(key, []) or []:
                    path = self.settings.comfy_output_dir / item.get("subfolder", "") / item["filename"]
                    if path.exists():
                        return path
        candidates = sorted(
            self.settings.comfy_output_dir.glob("**/*.mp4"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return candidates[0] if candidates else None

    def _wan_workflow(
        self,
        image_name: str,
        prompt: str,
        video_prefix: str,
        length: int,
        seed: int,
        width: int | None = None,
        height: int | None = None,
    ) -> dict:
        if self.settings.wan_profile == "wan22_5b_ti2v":
            return self._wan_5b_ti2v_workflow(image_name, prompt, video_prefix, length, seed, width, height)
        return self._wan_14b_i2v_workflow(image_name, prompt, video_prefix, length, seed, width, height)

    def _wan_14b_i2v_workflow(
        self,
        image_name: str,
        prompt: str,
        video_prefix: str,
        length: int,
        seed: int,
        width: int | None = None,
        height: int | None = None,
    ) -> dict:
        neg = (
            "blurry, bad quality, deformed, ugly, static, motionless, still frame, "
            "worst quality, extra limbs, glitch, watermark, text"
        )
        width = width or self.settings.wan_width
        height = height or self.settings.wan_height
        use_4step_lora = self.settings.wan_use_4step_lora
        high_model = ["18", 0] if use_4step_lora else ["1", 0]
        low_model = ["19", 0] if use_4step_lora else ["2", 0]
        steps = 4 if use_4step_lora else 6
        split_step = 2 if use_4step_lora else 3
        sampler_name = "euler" if use_4step_lora else "euler_ancestral"
        shift = 5.0 if use_4step_lora else 8.0
        workflow = {
            "prompt": {
                "1": {
                    "class_type": "UNETLoader",
                    "inputs": {"unet_name": self.settings.wan_high_model, "weight_dtype": self.settings.wan_weight_dtype},
                },
                "2": {
                    "class_type": "UNETLoader",
                    "inputs": {"unet_name": self.settings.wan_low_model, "weight_dtype": self.settings.wan_weight_dtype},
                },
                "3": {"class_type": "ModelSamplingSD3", "inputs": {"model": high_model, "shift": shift}},
                "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": low_model, "shift": shift}},
                "5": {"class_type": "CLIPLoader", "inputs": {"clip_name": self.settings.wan_clip_model, "type": "wan"}},
                "6": {"class_type": "VAELoader", "inputs": {"vae_name": self.settings.wan_vae_model}},
                "8": {"class_type": "LoadImage", "inputs": {"image": image_name}},
                "9": {
                    "class_type": "ImageResizeKJv2",
                    "inputs": {
                        "image": ["8", 0],
                        "width": width,
                        "height": height,
                        "upscale_method": "lanczos",
                        "keep_proportion": "resize",
                        "pad_color": "0, 0, 0",
                        "crop_position": "center",
                        "divisible_by": 16,
                    },
                },
                "11": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["5", 0], "text": prompt}},
                "12": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["5", 0], "text": neg}},
                "13": {
                    "class_type": "WanImageToVideo",
                    "inputs": {
                        "positive": ["11", 0],
                        "negative": ["12", 0],
                        "vae": ["6", 0],
                        "start_image": ["9", 0],
                        "width": ["9", 1],
                        "height": ["9", 2],
                        "length": length,
                        "batch_size": 1,
                    },
                },
                "14": {
                    "class_type": "KSamplerAdvanced",
                    "inputs": {
                        "model": ["3", 0],
                        "positive": ["13", 0],
                        "negative": ["13", 1],
                        "latent_image": ["13", 2],
                        "add_noise": "enable",
                        "noise_seed": seed,
                        "steps": steps,
                        "cfg": 1.0,
                        "sampler_name": sampler_name,
                        "scheduler": "simple",
                        "start_at_step": 0,
                        "end_at_step": split_step,
                        "return_with_leftover_noise": "enable",
                    },
                },
                "15": {
                    "class_type": "KSamplerAdvanced",
                    "inputs": {
                        "model": ["4", 0],
                        "positive": ["13", 0],
                        "negative": ["13", 1],
                        "latent_image": ["14", 0],
                        "add_noise": "disable",
                        "noise_seed": 0,
                        "steps": steps,
                        "cfg": 1.0,
                        "sampler_name": sampler_name,
                        "scheduler": "simple",
                        "start_at_step": split_step,
                        "end_at_step": steps,
                        "return_with_leftover_noise": "disable",
                    },
                },
                "16": {"class_type": "VAEDecode", "inputs": {"samples": ["15", 0], "vae": ["6", 0]}},
                "17": {
                    "class_type": "VHS_VideoCombine",
                    "inputs": {
                        "images": ["16", 0],
                        "frame_rate": self.settings.wan_fps,
                        "loop_count": 0,
                        "filename_prefix": video_prefix,
                        "format": "video/h264-mp4",
                        "pingpong": False,
                        "save_output": True,
                        "pix_fmt": "yuv420p",
                        "crf": 19,
                        "save_metadata": False,
                        "trim_to_audio": False,
                    },
                },
            }
        }
        if use_4step_lora:
            workflow["prompt"]["18"] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": ["1", 0],
                    "lora_name": self.settings.wan_high_lora,
                    "strength_model": self.settings.wan_lora_strength,
                },
            }
            workflow["prompt"]["19"] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": ["2", 0],
                    "lora_name": self.settings.wan_low_lora,
                    "strength_model": self.settings.wan_lora_strength,
                },
            }
        return workflow

    def _wan_5b_ti2v_workflow(
        self,
        image_name: str,
        prompt: str,
        video_prefix: str,
        length: int,
        seed: int,
        width: int | None = None,
        height: int | None = None,
    ) -> dict:
        neg = (
            "oversaturated, overexposed, static, blurry details, subtitles, style, artwork, "
            "painting, still image, gray overall, worst quality, low quality, jpeg artifacts, "
            "ugly, broken, bad hands, bad face, deformed, disfigured, extra fingers, fused fingers, "
            "motionless frame, cluttered background, watermark, text"
        )
        width = width or self.settings.wan_width
        height = height or self.settings.wan_height
        return {
            "prompt": {
                "1": {
                    "class_type": "UNETLoader",
                    "inputs": {
                        "unet_name": self.settings.wan_5b_model,
                        "weight_dtype": self.settings.wan_weight_dtype,
                    },
                },
                "2": {
                    "class_type": "ModelSamplingSD3",
                    "inputs": {"model": ["1", 0], "shift": self.settings.wan_5b_shift},
                },
                "3": {
                    "class_type": "CLIPLoader",
                    "inputs": {"clip_name": self.settings.wan_clip_model, "type": "wan"},
                },
                "4": {"class_type": "VAELoader", "inputs": {"vae_name": self.settings.wan_5b_vae_model}},
                "5": {"class_type": "LoadImage", "inputs": {"image": image_name}},
                "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
                "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": neg}},
                "8": {
                    "class_type": "Wan22ImageToVideoLatent",
                    "inputs": {
                        "vae": ["4", 0],
                        "start_image": ["5", 0],
                        "width": width,
                        "height": height,
                        "length": length,
                        "batch_size": 1,
                    },
                },
                "9": {
                    "class_type": "KSampler",
                    "inputs": {
                        "model": ["2", 0],
                        "positive": ["6", 0],
                        "negative": ["7", 0],
                        "latent_image": ["8", 0],
                        "seed": seed,
                        "steps": self.settings.wan_5b_steps,
                        "cfg": self.settings.wan_5b_cfg,
                        "sampler_name": self.settings.wan_5b_sampler,
                        "scheduler": self.settings.wan_5b_scheduler,
                        "denoise": 1.0,
                    },
                },
                "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["4", 0]}},
                "11": {"class_type": "CreateVideo", "inputs": {"images": ["10", 0], "fps": self.settings.wan_fps}},
                "12": {
                    "class_type": "SaveVideo",
                    "inputs": {
                        "video": ["11", 0],
                        "filename_prefix": video_prefix,
                        "format": "mp4",
                        "codec": "h264",
                    },
                },
            }
        }

    def _ltx_ia2v_workflow(
        self,
        image_name: str,
        audio_name: str,
        prompt: str,
        video_prefix: str,
        duration: float,
        seed: int,
        width: int | None = None,
        height: int | None = None,
        fps: int | None = None,
        native_audio: bool = False,
    ) -> dict:
        width = int(width or self.settings.ltx_width)
        height = int(height or self.settings.ltx_height)
        fps = int(fps or self.settings.ltx_fps)
        duration = max(0.25, float(duration))
        latent_width = max(64, width // 2)
        latent_height = max(64, height // 2)
        frame_count = self.ltx_frame_count(duration, fps)
        ckpt = self._ltx_checkpoint_name()
        uses_gguf = self._ltx_uses_gguf()
        lora_name = self._ltx_lora_name()
        base_model_ref = ["317", 0]
        model_ref = ["293", 0] if lora_name else base_model_ref
        video_vae_ref = ["336", 0] if uses_gguf else ["317", 2]
        audio_vae_ref = ["335", 0]
        workflow = {
            "prompt": {
                "900": {"class_type": "LoadImage", "inputs": {"image": image_name}},
                "901": {"class_type": "LoadAudio", "inputs": {"audio": audio_name}},
                "285": {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}},
                "286": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
                "287": {
                    "class_type": "LTXVConcatAVLatent",
                    "inputs": {"video_latent": ["296", 0], "audio_latent": ["309", 1]},
                },
                "288": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_cfg_pp"}},
                "289": {"class_type": "ManualSigmas", "inputs": {"sigmas": "0.85, 0.7250, 0.4219, 0.0"}},
                "290": {
                    "class_type": "CFGGuider",
                    "inputs": {"model": model_ref, "positive": ["292", 0], "negative": ["292", 1], "cfg": 1},
                },
                "291": {
                    "class_type": "SamplerCustomAdvanced",
                    "inputs": {
                        "noise": ["286", 0],
                        "guider": ["315", 0],
                        "sampler": ["298", 0],
                        "sigmas": ["308", 0],
                        "latent_image": ["326", 0],
                    },
                },
                "292": {
                    "class_type": "LTXVCropGuides",
                    "inputs": {"positive": ["307", 0], "negative": ["307", 1], "latent": ["309", 0]},
                },
                "294": {"class_type": "ResizeImagesByLongerEdge", "inputs": {"images": ["297", 0], "longer_edge": 1536}},
                "295": {
                    "class_type": "LTXVLatentUpsampler",
                    "inputs": {"samples": ["309", 0], "upscale_model": ["313", 0], "vae": video_vae_ref},
                },
                "296": {
                    "class_type": "LTXVImgToVideoInplace",
                    "inputs": {"vae": video_vae_ref, "image": ["334", 0], "latent": ["295", 0], "bypass": ["305", 0], "strength": 1},
                },
                "297": {
                    "class_type": "ResizeImageMaskNode",
                    "inputs": {
                        "input": ["900", 0],
                        "resize_type": "scale dimensions",
                        "resize_type.width": ["330", 0],
                        "resize_type.height": ["324", 0],
                        "resize_type.crop": "center",
                        "scale_method": "lanczos",
                    },
                },
                "298": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral_cfg_pp"}},
                "302": {
                    "class_type": "EmptyLTXVLatentVideo",
                    "inputs": {"width": latent_width, "height": latent_height, "length": frame_count, "batch_size": 1},
                },
                "303": {"class_type": "LTXVAudioVAEDecode", "inputs": {"samples": ["311", 1], "audio_vae": audio_vae_ref}},
                "305": {"class_type": "PrimitiveBoolean", "inputs": {"value": False}},
                "306": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["318", 0], "text": ["319", 0]}},
                "307": {
                    "class_type": "LTXVConditioning",
                    "inputs": {"positive": ["306", 0], "negative": ["314", 0], "frame_rate": fps},
                },
                "308": {
                    "class_type": "ManualSigmas",
                    "inputs": {"sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"},
                },
                "309": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["291", 0]}},
                "310": {
                    "class_type": "SamplerCustomAdvanced",
                    "inputs": {
                        "noise": ["285", 0],
                        "guider": ["290", 0],
                        "sampler": ["288", 0],
                        "sigmas": ["289", 0],
                        "latent_image": ["287", 0],
                    },
                },
                "311": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["310", 0]}},
                "312": {"class_type": "CreateVideo", "inputs": {"images": ["316", 0], "audio": ["303", 0], "fps": fps}},
                "313": {"class_type": "LatentUpscaleModelLoader", "inputs": {"model_name": self.settings.ltx_upscale_model}},
                "314": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["318", 0], "text": self.settings.ltx_negative_prompt}},
                "315": {
                    "class_type": "CFGGuider",
                    "inputs": {"model": model_ref, "positive": ["307", 0], "negative": ["307", 1], "cfg": 1},
                },
                "316": {
                    "class_type": "VAEDecodeTiled",
                    "inputs": {
                        "samples": ["311", 0],
                        "vae": video_vae_ref,
                        "tile_size": 768,
                        "overlap": 64,
                        "temporal_size": 4096,
                        "temporal_overlap": 4,
                    },
                },
                "319": {"class_type": "PrimitiveStringMultiline", "inputs": {"value": prompt}},
                "324": {"class_type": "PrimitiveInt", "inputs": {"value": height}},
                "325": {
                    "class_type": "LTXVImgToVideoInplace",
                    "inputs": {
                        "vae": video_vae_ref,
                        "image": ["334", 0],
                        "latent": ["302", 0],
                        "bypass": ["305", 0],
                        "strength": 0.7,
                    },
                },
                "326": {
                    "class_type": "LTXVConcatAVLatent",
                    "inputs": {"video_latent": ["325", 0], "audio_latent": ["327", 0]},
                },
                "327": {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["328", 0], "mask": ["333", 0]}},
                "328": {"class_type": "LTXVAudioVAEEncode", "inputs": {"audio": ["901", 0], "audio_vae": audio_vae_ref}},
                "330": {"class_type": "PrimitiveInt", "inputs": {"value": width}},
                "333": {"class_type": "SolidMask", "inputs": {"value": 0, "width": ["330", 0], "height": ["324", 0]}},
                "334": {"class_type": "LTXVPreprocess", "inputs": {"image": ["294", 0], "img_compression": 18}},
                "999": {
                    "class_type": "SaveVideo",
                    "inputs": {"video": ["312", 0], "filename_prefix": video_prefix, "format": "mp4", "codec": "h264"},
                },
            }
        }
        if lora_name:
            workflow["prompt"]["293"] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": base_model_ref,
                    "lora_name": lora_name,
                    "strength_model": self.settings.ltx_lora_strength,
                },
            }
        if uses_gguf:
            workflow["prompt"]["317"] = {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": self._ltx_gguf_name()}}
            workflow["prompt"]["318"] = {
                "class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": self.settings.ltx_text_encoder,
                    "clip_name2": self.settings.ltx_text_projection,
                    "type": "ltxv",
                    "device": "default",
                },
            }
            workflow["prompt"]["335"] = {
                "class_type": "VAELoaderKJ",
                "inputs": {"vae_name": self.settings.ltx_audio_vae, "device": "main_device", "weight_dtype": "bf16"},
            }
            workflow["prompt"]["336"] = {
                "class_type": "VAELoaderKJ",
                "inputs": {"vae_name": self.settings.ltx_video_vae, "device": "main_device", "weight_dtype": "bf16"},
            }
        else:
            workflow["prompt"]["317"] = {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}}
            workflow["prompt"]["318"] = {
                "class_type": "LTXAVTextEncoderLoader",
                "inputs": {"text_encoder": self.settings.ltx_text_encoder, "ckpt_name": ckpt, "device": "default"},
            }
            workflow["prompt"]["335"] = {"class_type": "LTXVAudioVAELoader", "inputs": {"ckpt_name": ckpt}}
        if native_audio:
            prompt_nodes = workflow["prompt"]
            prompt_nodes.pop("901", None)
            prompt_nodes.pop("327", None)
            prompt_nodes.pop("333", None)
            prompt_nodes["326"]["inputs"]["audio_latent"] = ["328", 0]
            prompt_nodes["328"] = {
                "class_type": "LTXVEmptyLatentAudio",
                "inputs": {
                    "frames_number": frame_count,
                    "frame_rate": fps,
                    "batch_size": 1,
                    "audio_vae": audio_vae_ref,
                },
            }
        return workflow
