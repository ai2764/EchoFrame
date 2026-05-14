import math
import subprocess
from pathlib import Path

from PIL import Image

from app.config import Settings


class MediaTools:
    def __init__(self, settings: Settings):
        self.settings = settings

    def save_square_avatar(self, src: Path, dst: Path, size: int | None = None) -> None:
        target_size = size or self.settings.avatar_size
        dst.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im = im.convert("RGB")
            w, h = im.size
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            im = im.crop((left, top, left + side, top + side))
            if im.size != (target_size, target_size):
                im = im.resize((target_size, target_size), Image.Resampling.LANCZOS)
            im.save(dst, "PNG")

    def duration(self, path: Path) -> float:
        cmd = [
            self.settings.ffprobe_bin,
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-500:] or "ffprobe failed")
        return float(result.stdout.strip())

    def make_still_video(
        self,
        image_path: Path,
        duration: float,
        output_path: Path,
        fps: int = 25,
        size: int | None = None,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        safe_duration = max(0.25, float(duration))
        cmd = [
            self.settings.ffmpeg_bin,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            f"{safe_duration:.3f}",
            "-vf",
            self._video_filter(fps, size),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        self._run(cmd, timeout=120)

    def normalize_video(
        self,
        input_path: Path,
        duration: float,
        output_path: Path,
        fps: int = 25,
        size: int | None = None,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.settings.ffmpeg_bin,
            "-y",
            "-i",
            str(input_path),
            "-t",
            f"{max(0.25, float(duration)):.3f}",
            "-vf",
            self._video_filter(fps, size),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        self._run(cmd, timeout=300)

    def loop_video_to_duration(
        self,
        input_path: Path,
        duration: float,
        output_path: Path,
        fps: int = 25,
        size: int | None = None,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pingpong_path = output_path.with_name(f"{output_path.stem}_pingpong{output_path.suffix}")
        pingpong_cmd = [
            self.settings.ffmpeg_bin,
            "-y",
            "-i",
            str(input_path),
            "-filter_complex",
            "[0:v]split=2[forward][reverse];"
            "[reverse]reverse,setpts=PTS-STARTPTS[reverse];"
            "[forward]setpts=PTS-STARTPTS[forward];"
            "[forward][reverse]concat=n=2:v=1:a=0,format=yuv420p[v]",
            "-map",
            "[v]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(pingpong_path),
        ]
        self._run(pingpong_cmd, timeout=120)
        cmd = [
            self.settings.ffmpeg_bin,
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(pingpong_path),
            "-t",
            f"{max(0.25, float(duration)):.3f}",
            "-vf",
            self._video_filter(fps, size),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        try:
            self._run(cmd, timeout=300)
        finally:
            pingpong_path.unlink(missing_ok=True)

    def mux_audio(self, video_path: Path, audio_path: Path, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.settings.ffmpeg_bin,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        self._run(cmd, timeout=300)

    def wan_length_for_duration(self, duration: float) -> int:
        frames = max(17, int(math.ceil(duration * self.settings.wan_fps)))
        return int(math.ceil((frames - 1) / 4) * 4 + 1)

    def wan_loop_length(self) -> int:
        return self.wan_length_for_duration(self.settings.wan_loop_seconds)

    def _video_filter(self, fps: int, size: int | None = None) -> str:
        target_size = size or self.settings.output_size
        return f"scale={target_size}:{target_size}:flags=lanczos,fps={fps},format=yuv420p"

    def _run(self, cmd: list[str], timeout: int) -> None:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            msg = result.stderr[-1000:] or result.stdout[-1000:] or "media command failed"
            raise RuntimeError(msg)
