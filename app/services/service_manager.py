from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException

from app.config import Settings
from app.paths import command_for_cwd, path_for_cwd
from app.schemas import EngineActionResponse, EngineStatus
from app.services.comfy import ComfyClient
from app.services.gpu import gpu_status
from app.services.llm import LLMClient
from app.services.model_manifest import ModelManifest
from app.services.musetalk import MuseTalkClient
from app.services.tts import TTSClient


SERVICE_NAMES = {"lm_studio", "cosyvoice", "comfyui", "musetalk", "ffmpeg", "gpu"}


class ServiceManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.models = ModelManifest(settings)

    async def statuses(self) -> dict[str, EngineStatus]:
        model_checks = self.models.check_all()
        result = {}
        for name in ("lm_studio", "cosyvoice", "comfyui", "musetalk", "ffmpeg", "gpu"):
            result[name] = await self._status(name, model_checks)
        return result

    async def status(self, name: str) -> EngineStatus:
        return await self._status(name, self.models.check_all())

    async def _status(self, name: str, model_checks: dict) -> EngineStatus:
        self._validate_name(name)
        models_ok = model_checks.get(name).ok if name in model_checks else None
        installed = self._installed(name)
        pid = self._pid_for_service(name)
        port = self._port_for_service(name)
        ok, detail = await self._health(name)
        if ok and name in {"cosyvoice", "comfyui"}:
            installed = True
            if models_ok is False:
                models_ok = True
        return EngineStatus(
            name=name,
            ok=ok and installed and (models_ok is not False),
            detail=detail,
            installed=installed,
            online=ok,
            models_ok=models_ok,
            startable=self._startable(name),
            pid=pid,
            port=port,
        )

    async def start(self, name: str) -> EngineActionResponse:
        self._validate_name(name)
        if (
            name not in {"lm_studio", "cosyvoice", "comfyui"}
            or (name == "cosyvoice" and not self._startable("cosyvoice"))
        ):
            status = await self.status(name)
            return EngineActionResponse(ok=status.ok, name=name, action="start", detail="external or on-demand component", status=status)
        status = await self.status(name)
        if status.online:
            return EngineActionResponse(ok=True, name=name, action="start", detail="already online", status=status)
        if not status.installed:
            return EngineActionResponse(ok=False, name=name, action="start", detail="not installed", status=status)
        if status.models_ok is False:
            return EngineActionResponse(ok=False, name=name, action="start", detail="required model files are missing", status=status)

        if name == "lm_studio":
            self._start_lm_studio()
            timeout = 30
        elif name == "cosyvoice":
            self._start_tts()
            timeout = self.settings.tts_start_timeout_seconds
        else:
            self._start_comfy()
            timeout = self.settings.comfy_start_timeout_seconds
        ready = await self._wait_online(name, timeout)
        return EngineActionResponse(
            ok=ready.ok,
            name=name,
            action="start",
            detail=ready.detail,
            status=ready,
        )

    async def stop(self, name: str) -> EngineActionResponse:
        self._validate_name(name)
        if name == "lm_studio":
            self._run_quiet([self.settings.lms_bin, "unload", "--all"])
            self._run_quiet([self.settings.lms_bin, "server", "stop"])
        elif name == "cosyvoice" and self.settings.tts_backend == "native":
            status = await self.status(name)
            return EngineActionResponse(ok=status.ok, name=name, action="stop", detail="no resident service", status=status)
        elif name in {"cosyvoice", "comfyui"}:
            port = self._port_for_service(name)
            if port:
                self._kill_port(port)
        else:
            status = await self.status(name)
            return EngineActionResponse(ok=status.ok, name=name, action="stop", detail="no resident service", status=status)
        await asyncio.sleep(1.0)
        status = await self.status(name)
        return EngineActionResponse(ok=not status.online, name=name, action="stop", detail=status.detail, status=status)

    async def restart(self, name: str) -> EngineActionResponse:
        self._validate_name(name)
        await self.stop(name)
        return await self.start(name)

    async def ensure(self, name: str) -> EngineStatus:
        status = await self.status(name)
        if status.ok:
            return status
        if name in {"lm_studio", "comfyui"} or (name == "cosyvoice" and self.settings.tts_backend == "http"):
            action = await self.start(name)
            if action.status and action.status.ok:
                return action.status
            raise RuntimeError(action.detail or f"{name} is not ready")
        raise RuntimeError(status.detail or f"{name} is not ready")

    def logs(self, name: str, lines: int = 120) -> str:
        self._validate_name(name)
        path = self._log_path(name)
        if not path.exists():
            return ""
        try:
            content = path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(content[-lines:])
        except Exception as exc:
            return str(exc)

    def _validate_name(self, name: str) -> None:
        if name not in SERVICE_NAMES:
            raise HTTPException(status_code=404, detail="unknown service")

    async def _health(self, name: str) -> tuple[bool, str]:
        if name == "lm_studio":
            return await LLMClient(self.settings).health()
        if name == "cosyvoice":
            return await TTSClient(self.settings).health()
        if name == "comfyui":
            return await ComfyClient(self.settings).health()
        if name == "musetalk":
            return MuseTalkClient(self.settings).health()
        if name == "ffmpeg":
            return self._ffmpeg_health()
        if name == "gpu":
            status = gpu_status()
            return bool(status["ok"]), str(status["detail"])
        return False, "unknown"

    def _installed(self, name: str) -> bool:
        if name == "lm_studio":
            return self._command_exists(self.settings.lms_bin)
        if name == "cosyvoice":
            if self.settings.tts_backend == "native":
                return self.settings.tts_root.exists() and TTSClient(self.settings)._cosyvoice_source_present()
            if not self.settings.tts_manage_http_service:
                return True
            return self.settings.tts_root.exists() and (self.settings.tts_root / self.settings.tts_script).exists()
        if name == "comfyui":
            return self.settings.comfy_root.exists() and (self.settings.comfy_root / "main.py").exists()
        if name == "musetalk":
            return self.settings.musetalk_root.exists()
        if name == "ffmpeg":
            return self._command_exists(self.settings.ffmpeg_bin) and self._command_exists(self.settings.ffprobe_bin)
        return True

    def _start_lm_studio(self) -> None:
        self._run_quiet(
            [
                self.settings.lms_bin,
                "server",
                "start",
                "--port",
                str(self.settings.lms_server_port),
                "--bind",
                self.settings.lms_server_host,
            ]
        )

    def _start_tts(self) -> None:
        env = os.environ.copy()
        if self.settings.tts_secret:
            env["TTS_SECRET"] = self.settings.tts_secret
        env["TTS_PORT"] = str(self.settings.tts_port)
        env["FOR_DISABLE_CONSOLE_CTRL_HANDLER"] = "1"
        self._popen(
            "cosyvoice",
            [self.settings.tts_python, self.settings.tts_script],
            cwd=self.settings.tts_root,
            env=env,
        )

    def _start_comfy(self) -> None:
        args = [
            self.settings.comfy_python,
            "main.py",
            "--listen",
            "127.0.0.1",
            "--port",
            str(self._port_for_service("comfyui") or 8000),
            "--disable-auto-launch",
        ]
        if self.settings.comfy_base_dir:
            args += ["--base-directory", path_for_cwd(self.settings.comfy_base_dir, self.settings.comfy_root)]
        extra_model_paths = self.settings.comfy_root / "extra_model_paths.yaml"
        if extra_model_paths.exists():
            args += ["--extra-model-paths-config", path_for_cwd(extra_model_paths, self.settings.comfy_root)]
        self._popen("comfyui", args, cwd=self.settings.comfy_root, env=os.environ.copy())

    async def _wait_online(self, name: str, timeout: int) -> EngineStatus:
        deadline = asyncio.get_running_loop().time() + max(1, timeout)
        latest = await self.status(name)
        while asyncio.get_running_loop().time() < deadline:
            latest = await self.status(name)
            if latest.ok:
                return latest
            await asyncio.sleep(2.0)
        return latest

    def _popen(self, name: str, cmd: list[str], cwd: Path, env: dict[str, str]) -> None:
        log_path = self._log_path(name)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("a", encoding="utf-8", errors="replace")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            [command_for_cwd(cmd[0], cwd), *cmd[1:]],
            cwd=str(cwd),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags,
        )

    def _run_quiet(self, cmd: list[str]) -> None:
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except Exception:
            pass

    def _ffmpeg_health(self) -> tuple[bool, str]:
        try:
            ff = subprocess.run(
                [self.settings.ffmpeg_bin, "-version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            fp = subprocess.run(
                [self.settings.ffprobe_bin, "-version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if ff.returncode == 0 and fp.returncode == 0:
                return True, "ready"
            return False, "ffmpeg or ffprobe failed"
        except Exception as exc:
            return False, str(exc)

    def _command_exists(self, command: str) -> bool:
        if Path(command).exists():
            return True
        return shutil.which(command) is not None

    def _startable(self, name: str) -> bool:
        if name == "cosyvoice":
            return self.settings.tts_backend == "http" and self.settings.tts_manage_http_service
        return name in {"lm_studio", "comfyui"}

    def _log_path(self, name: str) -> Path:
        return self.settings.abs_data_dir / "logs" / "engines" / f"{name}.log"

    def _port_for_service(self, name: str) -> int | None:
        if name == "lm_studio":
            return self.settings.lms_server_port
        if name == "cosyvoice":
            if self.settings.tts_backend == "native":
                return None
            return self._port_from_url(self.settings.tts_url) or self.settings.tts_port
        if name == "comfyui":
            return self._port_from_url(self.settings.comfy_url)
        return None

    def _port_from_url(self, url: str) -> int | None:
        try:
            return urlparse(url).port
        except Exception:
            return None

    def _pid_for_service(self, name: str) -> int | None:
        port = self._port_for_service(name)
        if not port:
            return None
        pids = self._pids_on_port(port)
        return pids[0] if pids else None

    def _pids_on_port(self, port: int) -> list[int]:
        try:
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=10)
        except Exception:
            return []
        pids: list[int] = []
        needle = f":{port}"
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(needle) and parts[3].upper() == "LISTENING":
                try:
                    pids.append(int(parts[4]))
                except ValueError:
                    pass
        return sorted(set(pids))

    def _kill_port(self, port: int) -> None:
        for pid in self._pids_on_port(port):
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, text=True)
