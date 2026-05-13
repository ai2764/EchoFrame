from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings


WAN_REPO = "Comfy-Org/Wan_2.2_ComfyUI_Repackaged"
WAN_FILES = [
    ("diffusion_models", "split_files/diffusion_models/{name}", "wan_high_model"),
    ("diffusion_models", "split_files/diffusion_models/{name}", "wan_low_model"),
    ("text_encoders", "split_files/text_encoders/{name}", "wan_clip_model"),
    ("vae", "split_files/vae/{name}", "wan_vae_model"),
]


@dataclass(frozen=True)
class ModelCheck:
    name: str
    ok: bool
    detail: str = ""


class ModelManifest:
    def __init__(self, settings: Settings):
        self.settings = settings

    def check_all(self) -> dict[str, ModelCheck]:
        return {
            "lm_studio": self.check_llm(),
            "cosyvoice": self.check_tts(),
            "comfyui": self.check_wan(),
            "musetalk": self.check_musetalk(),
        }

    def check_llm(self) -> ModelCheck:
        try:
            result = subprocess.run(
                [self.settings.lms_bin, "ls"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
            if result.returncode != 0:
                return ModelCheck("lm_studio", False, "lms ls failed")
            ok = self.settings.llm_model in result.stdout
            return ModelCheck("lm_studio", ok, "model present" if ok else "model missing")
        except Exception as exc:
            return ModelCheck("lm_studio", False, str(exc))

    def check_tts(self) -> ModelCheck:
        model_dir = self.settings.tts_root / "pretrained_models" / "CosyVoice2-0.5B"
        ok = model_dir.exists() and any(model_dir.iterdir())
        if not ok and self._http_ok(self.settings.tts_url.rstrip("/") + "/health"):
            return ModelCheck("cosyvoice", True, "server online")
        return ModelCheck("cosyvoice", ok, "model present" if ok else "CosyVoice2-0.5B missing")

    def check_wan(self) -> ModelCheck:
        missing = []
        for folder, _, setting_name in WAN_FILES:
            name = str(getattr(self.settings, setting_name))
            target = self.comfy_models_dir / folder / name
            if not target.exists():
                missing.append(f"{folder}/{name}")
        ok = not missing
        return ModelCheck("comfyui", ok, "model present" if ok else "missing: " + ", ".join(missing[:4]))

    def check_musetalk(self) -> ModelCheck:
        required = [
            "models/musetalkV15/unet.pth",
            "models/musetalkV15/musetalk.json",
            "models/sd-vae/config.json",
            "models/whisper/config.json",
        ]
        missing = [rel for rel in required if not (self.settings.musetalk_root / rel).exists()]
        ok = not missing
        return ModelCheck("musetalk", ok, "model present" if ok else "missing: " + ", ".join(missing[:4]))

    def download_missing(self) -> list[str]:
        completed: list[str] = []
        if not self.check_llm().ok:
            self._run([self.settings.lms_bin, "get", self.settings.llm_model, "--gguf", "-y"])
            completed.append("lm_studio")
        if not self.check_tts().ok:
            self._download_tts()
            completed.append("cosyvoice")
        if not self.check_wan().ok:
            self._download_wan()
            completed.append("comfyui")
        if not self.check_musetalk().ok:
            self._download_musetalk()
            completed.append("musetalk")
        return completed

    @property
    def comfy_models_dir(self) -> Path:
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

    def _download_tts(self) -> None:
        script = self.settings.tts_root / "download_model.py"
        if not script.exists():
            raise RuntimeError("TTS download_model.py is missing")
        self._run([self.settings.tts_python, str(script)], cwd=self.settings.tts_root)

    def _download_musetalk(self) -> None:
        root = self.settings.musetalk_root
        script = root / "download_weights.bat"
        if script.exists():
            self._run(["cmd", "/c", str(script)], cwd=root)
            return
        script = root / "download_weights.sh"
        if script.exists():
            self._run(["bash", str(script)], cwd=root)
            return
        raise RuntimeError("MuseTalk download script is missing")

    def _download_wan(self) -> None:
        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            self._run([sys.executable, "-m", "pip", "install", "huggingface_hub"])
            from huggingface_hub import hf_hub_download

        for folder, repo_pattern, setting_name in WAN_FILES:
            filename = str(getattr(self.settings, setting_name))
            target = self.comfy_models_dir / folder / filename
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = hf_hub_download(repo_id=WAN_REPO, filename=repo_pattern.format(name=filename))
            shutil.copy2(source, target)

    def _run(self, cmd: list[str], cwd: Path | None = None) -> None:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-1200:] or result.stdout[-1200:] or f"command failed: {cmd[0]}")

    def _http_ok(self, url: str) -> bool:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return response.status == 200
        except Exception:
            return False
