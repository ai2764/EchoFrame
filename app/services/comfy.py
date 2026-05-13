import random
import shutil
import time
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
