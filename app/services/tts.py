from pathlib import Path
import subprocess

import httpx

from app.config import Settings


class TTSClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def health(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(self.settings.tts_url.rstrip("/") + "/health")
            if r.status_code == 200:
                return True, "online"
            return False, f"HTTP {r.status_code}"
        except Exception as exc:
            return False, str(exc)

    async def synthesize(self, text: str, instruct: str, voice_id: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        headers = {}
        if self.settings.tts_secret:
            headers["X-Shared-Secret"] = self.settings.tts_secret
        # Some local CosyVoice servers parse multipart fields with stdlib cgi.
        # UTF-8 BOM keeps Chinese text stable on that path.
        files = {
            "text": (None, text.encode("utf-8-sig")),
            "voice_id": (None, voice_id),
            "instruct": (None, instruct.encode("utf-8-sig")),
            "speed": (None, str(self.settings.tts_speed)),
        }
        async with httpx.AsyncClient(timeout=self.settings.tts_timeout_seconds) as client:
            r = await client.post(self.settings.tts_url.rstrip("/") + "/tts", headers=headers, files=files)
        if r.status_code != 200:
            raise RuntimeError(f"CosyVoice HTTP {r.status_code}: {r.text[:500]}")
        if self.settings.tts_trim_start_seconds > 0:
            raw_path = output_path.with_name(f"{output_path.stem}_raw{output_path.suffix}")
            raw_path.write_bytes(r.content)
            try:
                self._trim_start(raw_path, output_path)
            finally:
                raw_path.unlink(missing_ok=True)
        else:
            output_path.write_bytes(r.content)

    def _trim_start(self, input_path: Path, output_path: Path) -> None:
        trim = max(0.0, self.settings.tts_trim_start_seconds)
        fade = max(0.0, min(self.settings.tts_fade_in_seconds, 1.0))
        filters = [f"atrim=start={trim:.3f}", "asetpts=N/SR/TB"]
        if fade > 0:
            filters.append(f"afade=t=in:st=0:d={fade:.3f}")
        cmd = [
            self.settings.ffmpeg_bin,
            "-y",
            "-i",
            str(input_path),
            "-af",
            ",".join(filters),
            "-c:a",
            "pcm_f32le",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-1000:] or "TTS audio trim failed")
