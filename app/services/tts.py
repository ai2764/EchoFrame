from __future__ import annotations

import asyncio
import json
import os
import queue
import subprocess
import threading
import time
import uuid
from pathlib import Path

import httpx

from app.config import Settings
from app.paths import command_for_cwd, path_for_cwd


_WORKER_LOCK = threading.Lock()
_WORKER: NativeCosyVoiceWorker | None = None


class NativeCosyVoiceWorker:
    def __init__(self, settings: Settings, script: Path, model_dir: Path, presets_file: Path):
        self.settings = settings
        self.script = script.resolve()
        self.model_dir = model_dir.resolve()
        self.presets_file = presets_file.resolve()
        self.signature = (
            self.settings.tts_python,
            str(self.settings.tts_root.resolve()),
            str(self.script),
            str(self.model_dir),
            str(self.presets_file),
            self.settings.tts_cuda_visible_devices,
        )
        self.process: subprocess.Popen | None = None
        self.log_file = None
        self.lines: queue.Queue[str] = queue.Queue()
        self.lock = threading.Lock()
        self.ready = False

    def synthesize(self, text: str, instruct: str, voice_id: str, output_path: Path) -> None:
        with self.lock:
            self._ensure_started()
            job_id = uuid.uuid4().hex
            self._write(
                {
                    "job_id": job_id,
                    "text": text,
                    "instruct": instruct,
                    "voice_id": voice_id,
                    "speed": self.settings.tts_speed,
                    "output": path_for_cwd(output_path, self.settings.tts_root),
                }
            )
            deadline = time.monotonic() + self.settings.tts_timeout_seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.stop()
                    raise TimeoutError("native CosyVoice worker timed out")
                try:
                    line = self.lines.get(timeout=min(1.0, remaining))
                except queue.Empty:
                    if self.process and self.process.poll() is not None:
                        raise RuntimeError("native CosyVoice worker exited unexpectedly")
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("event") == "ready":
                    self.ready = True
                    continue
                if payload.get("job_id") != job_id:
                    continue
                if payload.get("ok"):
                    return
                raise RuntimeError(payload.get("error") or "native CosyVoice worker failed")

    def stop(self) -> None:
        process = self.process
        if process and process.poll() is None:
            try:
                self._write({"action": "stop"})
                process.wait(timeout=5)
            except Exception:
                process.kill()
        if self.log_file:
            try:
                self.log_file.close()
            except Exception:
                pass
        self.process = None
        self.log_file = None
        self.ready = False

    def ensure_ready(self) -> None:
        with self.lock:
            self._ensure_started()
            if self.ready:
                return
            deadline = time.monotonic() + self.settings.tts_start_timeout_seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.stop()
                    raise TimeoutError("native CosyVoice worker preload timed out")
                try:
                    line = self.lines.get(timeout=min(1.0, remaining))
                except queue.Empty:
                    if self.process and self.process.poll() is not None:
                        raise RuntimeError("native CosyVoice worker exited during preload")
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("event") == "ready":
                    if payload.get("ok", True):
                        self.ready = True
                        return
                    raise RuntimeError(payload.get("error") or "native CosyVoice worker preload failed")

    def _ensure_started(self) -> None:
        if self.process and self.process.poll() is None:
            return
        self.ready = False
        log_path = self.settings.abs_data_dir / "logs" / "engines" / "cosyvoice_native.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_file = log_path.open("a", encoding="utf-8", errors="replace")
        env = _native_env(self.settings)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        cmd = [
            command_for_cwd(self.settings.tts_python, self.settings.tts_root),
            path_for_cwd(self.script, self.settings.tts_root),
            "--worker",
            "--root",
            path_for_cwd(self.settings.tts_root, self.settings.tts_root),
            "--model-dir",
            path_for_cwd(self.model_dir, self.settings.tts_root),
            "--presets",
            path_for_cwd(self.presets_file, self.settings.tts_root),
        ]
        if self.settings.tts_use_float16:
            cmd.append("--fp16")
        if self.settings.tts_text_frontend:
            cmd.append("--text-frontend")
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log_file,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            cwd=str(self.settings.tts_root),
            creationflags=creationflags,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()

    def _read_stdout(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            self.lines.put(line.strip())

    def _write(self, payload: dict) -> None:
        if not self.process or not self.process.stdin:
            raise RuntimeError("native CosyVoice worker is not running")
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.process.stdin.flush()


def _native_worker(settings: Settings, script: Path, model_dir: Path, presets_file: Path) -> NativeCosyVoiceWorker:
    global _WORKER
    candidate = NativeCosyVoiceWorker(settings, script, model_dir, presets_file)
    with _WORKER_LOCK:
        if _WORKER and _WORKER.signature != candidate.signature:
            _WORKER.stop()
            _WORKER = None
        if _WORKER is None:
            _WORKER = candidate
        return _WORKER


def _drop_native_worker(worker: NativeCosyVoiceWorker) -> None:
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is worker:
            worker.stop()
            _WORKER = None


def _drop_active_native_worker() -> None:
    global _WORKER
    with _WORKER_LOCK:
        worker = _WORKER
        _WORKER = None
    if worker:
        worker.stop()


def _native_env(settings: Settings) -> dict[str, str]:
    env = os.environ.copy()
    if settings.tts_cuda_visible_devices.strip():
        env["CUDA_VISIBLE_DEVICES"] = settings.tts_cuda_visible_devices.strip()
    cache_root = settings.abs_data_dir / "cache" / "tts"
    tmp_dir = cache_root / "tmp"
    numba_dir = cache_root / "numba"
    xdg_dir = cache_root / "xdg"
    modelscope_dir = settings.abs_data_dir / "cache" / "modelscope"
    for path in (tmp_dir, numba_dir, xdg_dir, modelscope_dir):
        path.mkdir(parents=True, exist_ok=True)
    env["TEMP"] = str(tmp_dir.resolve())
    env["TMP"] = str(tmp_dir.resolve())
    env["NUMBA_CACHE_DIR"] = str(numba_dir.resolve())
    env["XDG_CACHE_HOME"] = str(xdg_dir.resolve())
    env["MODELSCOPE_CACHE"] = str(modelscope_dir.resolve())
    env["MODELSCOPE_HOME"] = str(modelscope_dir.resolve())
    env["MODELSCOPE_OFFLINE"] = "1"
    env["FOR_DISABLE_CONSOLE_CTRL_HANDLER"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


class TTSClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def health(self) -> tuple[bool, str]:
        if self.settings.tts_backend == "native":
            return self._native_health()
        return await self._http_health()

    async def _http_health(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(self.settings.tts_url.rstrip("/") + "/health")
            if r.status_code == 200:
                return True, "online"
            return False, f"HTTP {r.status_code}"
        except Exception as exc:
            return False, str(exc)

    async def synthesize(self, text: str, instruct: str, voice_id: str, output_path: Path) -> None:
        if self.settings.tts_backend == "native":
            await asyncio.to_thread(self._synthesize_native, text, instruct, voice_id, output_path)
            return
        await self._synthesize_http(text, instruct, voice_id, output_path)

    async def preload(self) -> None:
        if self.settings.tts_backend != "native" or not self.settings.tts_native_worker:
            return
        await asyncio.to_thread(self._preload_native)

    async def unload(self) -> None:
        if self.settings.tts_backend != "native" or not self.settings.tts_native_worker:
            return
        await asyncio.to_thread(_drop_active_native_worker)

    async def _synthesize_http(self, text: str, instruct: str, voice_id: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        headers = {}
        if self.settings.tts_secret:
            headers["X-Shared-Secret"] = self.settings.tts_secret
        # Some local CosyVoice servers parse multipart fields with stdlib cgi.
        # UTF-8 BOM keeps Chinese text stable on that path.
        files = {
            "text": (None, text.encode("utf-8-sig")),
            "voice_id": (None, voice_id),
            "speed": (None, str(self.settings.tts_speed)),
        }
        if instruct.strip():
            files["instruct"] = (None, instruct.strip().encode("utf-8-sig"))
        async with httpx.AsyncClient(timeout=self.settings.tts_timeout_seconds) as client:
            r = await client.post(self.settings.tts_url.rstrip("/") + "/tts", headers=headers, files=files)
        if r.status_code != 200:
            raise RuntimeError(f"CosyVoice HTTP {r.status_code}: {r.text[:500]}")
        output_path.write_bytes(r.content)

    def _synthesize_native(self, text: str, instruct: str, voice_id: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        script = self._native_script()
        model_dir = self._model_dir()
        presets_file = self._presets_file()
        raw_path = output_path
        if self.settings.tts_native_worker:
            worker = _native_worker(self.settings, script, model_dir, presets_file)
            worker.synthesize(text, instruct.strip(), voice_id, raw_path)
            if self.settings.tts_native_unload_after_request:
                _drop_native_worker(worker)
        else:
            self._synthesize_native_once(text, instruct, voice_id, raw_path, script, model_dir, presets_file)
        if not raw_path.exists():
            raise RuntimeError("native CosyVoice did not produce an audio file")

    def _preload_native(self) -> None:
        worker = _native_worker(self.settings, self._native_script(), self._model_dir(), self._presets_file())
        worker.ensure_ready()

    def _synthesize_native_once(
        self,
        text: str,
        instruct: str,
        voice_id: str,
        raw_path: Path,
        script: Path,
        model_dir: Path,
        presets_file: Path,
    ) -> None:
        cmd = [
            command_for_cwd(self.settings.tts_python, self.settings.tts_root),
            path_for_cwd(script, self.settings.tts_root),
            "--root",
            path_for_cwd(self.settings.tts_root, self.settings.tts_root),
            "--model-dir",
            path_for_cwd(model_dir, self.settings.tts_root),
            "--presets",
            path_for_cwd(presets_file, self.settings.tts_root),
            "--text",
            text,
            "--voice-id",
            voice_id,
            "--speed",
            str(self.settings.tts_speed),
            "--output",
            path_for_cwd(raw_path, self.settings.tts_root),
        ]
        if self.settings.tts_use_float16:
            cmd.append("--fp16")
        if self.settings.tts_text_frontend:
            cmd.append("--text-frontend")
        if instruct.strip():
            cmd += ["--instruct", instruct.strip()]
        env = _native_env(self.settings)
        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.settings.tts_timeout_seconds,
                cwd=str(self.settings.tts_root),
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("native CosyVoice timed out") from exc
        if result.returncode != 0:
            detail = result.stderr[-1600:] or result.stdout[-1600:] or "native CosyVoice failed"
            raise RuntimeError(detail)

    def _native_health(self) -> tuple[bool, str]:
        missing = []
        if not self.settings.tts_root.exists():
            missing.append("engine root")
        if not self._native_script().exists():
            missing.append("native runner")
        if not self._cosyvoice_source_present():
            missing.append("CosyVoice source")
        model_dir = self._model_dir()
        if not (model_dir.exists() and any(model_dir.iterdir())):
            missing.append("CosyVoice2-0.5B")
        if not self._presets_file().exists():
            missing.append("voice presets")
        if missing:
            return False, "missing " + ", ".join(missing)
        return True, "native ready"

    def _native_script(self) -> Path:
        return Path(__file__).resolve().parents[2] / "tools" / "native_cosyvoice_tts.py"

    def _model_dir(self) -> Path:
        if self.settings.tts_model_dir:
            return self.settings.tts_model_dir
        return self.settings.tts_root / "pretrained_models" / "CosyVoice2-0.5B"

    def _presets_file(self) -> Path:
        if self.settings.tts_presets_file:
            return self.settings.tts_presets_file
        return self.settings.tts_root / "voices" / "presets.json"

    def _cosyvoice_source_present(self) -> bool:
        root = self.settings.tts_root
        candidates = [
            root / "cosyvoice",
            root / "vendor" / "cosyvoice" / "cosyvoice",
            root / "CosyVoice" / "cosyvoice",
        ]
        return any(path.exists() for path in candidates)
