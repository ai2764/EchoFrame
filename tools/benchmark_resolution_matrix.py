from __future__ import annotations

import argparse
import asyncio
import csv
import json
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.modules.video import VideoGenerationModule
from app.paths import new_id, run_dir
from app.services.comfy import ComfyClient
from app.services.media import MediaTools
from app.services.musetalk import MuseTalkClient


PROMPT = (
    "Front-facing bust shot of the same person, subtle blinking, slight nodding, "
    "small shoulder movement, steady camera, clean studio lighting, natural neutral mouth."
)

DEFAULT_RESOLUTIONS = [120, 160, 224, 320, 384, 448, 512]
DEFAULT_MODES = ["fast", "wan_loop"]


class GpuSampler:
    def __init__(self, interval: float):
        self.interval = interval
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "GpuSampler":
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._sample()

    @property
    def peak_used_mib(self) -> int:
        values = [s["used_mib"] for s in self.samples if s.get("used_mib") is not None]
        return max(values) if values else 0

    @property
    def baseline_used_mib(self) -> int:
        for sample in self.samples:
            if sample.get("used_mib") is not None:
                return sample["used_mib"]
        return 0

    @property
    def gpu_name(self) -> str:
        for sample in self.samples:
            if sample.get("name"):
                return sample["name"]
        return ""

    @property
    def total_mib(self) -> int:
        for sample in self.samples:
            if sample.get("total_mib") is not None:
                return sample["total_mib"]
        return 0

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._sample()
            self._stop.wait(self.interval)

    def _sample(self) -> None:
        cmd = [
            "nvidia-smi",
            "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
            "--format=csv,noheader,nounits",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except Exception:
            return
        if result.returncode != 0:
            return
        line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            return
        name, used, total, util, temp = parts[:5]
        self.samples.append(
            {
                "t": time.perf_counter(),
                "name": name,
                "used_mib": _to_int(used),
                "total_mib": _to_int(total),
                "utilization": _to_int(util),
                "temperature": _to_int(temp),
            }
        )


def _to_int(value: str) -> int | None:
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


async def wait_for_comfy_idle(client: ComfyClient, timeout: float) -> None:
    import httpx

    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        try:
            async with httpx.AsyncClient(timeout=5.0) as http:
                r = await http.get(client.settings.comfy_url.rstrip("/") + "/queue")
            body = r.json()
            if not body.get("queue_running") and not body.get("queue_pending"):
                return
        except Exception:
            pass
        await asyncio.sleep(5)
    raise TimeoutError("ComfyUI did not become idle")


def latest_avatar() -> Path:
    avatars = sorted(
        Path("data/avatars").glob("*/source.png"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not avatars:
        raise FileNotFoundError("No uploaded avatar found under data/avatars")
    return avatars[0]


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def output_resolution(value: int, minimum: int, maximum: int) -> int:
    value = max(minimum, min(maximum, int(value)))
    if value % 2:
        value -= 1
    return max(minimum, value)


def wan_resolution(value: int, maximum: int) -> int:
    value = max(128, value)
    value = ((value + 15) // 16) * 16
    return min(maximum, value)


async def run_case(
    *,
    mode: str,
    resolution: int,
    avatar: Path,
    audio: Path,
    audio_duration: float,
    sample_interval: float,
    idle_timeout: float,
) -> dict:
    settings = get_settings()
    settings.comfy_unload_after_wan = True
    media = MediaTools(settings)
    comfy = ComfyClient(settings)
    video = VideoGenerationModule(settings)
    musetalk = MuseTalkClient(settings)
    resolution = output_resolution(resolution, settings.resolution_min, settings.resolution_max)
    render_resolution = wan_resolution(resolution, settings.resolution_max)

    if mode in {"wan", "wan_loop"}:
        await wait_for_comfy_idle(comfy, idle_timeout)
        await comfy.free_memory()
        await asyncio.sleep(3)

    case_id = new_id(f"bench_{mode}_{resolution}")
    out_dir = run_dir(settings, case_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    base_seconds = 0.0
    muse_seconds = 0.0
    result = {
        "run_id": case_id,
        "mode": mode,
        "wan_profile": settings.wan_profile,
        "resolution": resolution,
        "wan_render_resolution": render_resolution,
        "audio_duration": round(audio_duration, 3),
        "ok": False,
        "error": "",
        "output_video": "",
    }

    start_total = time.perf_counter()
    with GpuSampler(sample_interval) as gpu:
        try:
            start = time.perf_counter()
            base = await video.generate_base_video(
                mode=mode,
                avatar_path=avatar,
                prompt=PROMPT,
                audio_duration=audio_duration,
                run_id=case_id,
                run_dir=out_dir,
                resolution=resolution,
                wan_resolution=render_resolution,
            )
            base_seconds = time.perf_counter() - start

            start = time.perf_counter()
            talk = musetalk.lip_sync(audio, base.lip_sync_input_path, out_dir)
            muse_seconds = time.perf_counter() - start
            result["ok"] = True
            result["output_video"] = rel(talk)
        except Exception as exc:
            result["error"] = str(exc)[-1200:]

    total_seconds = time.perf_counter() - start_total
    result.update(
        {
            "total_seconds": round(total_seconds, 3),
            "base_video_seconds": round(base_seconds, 3),
            "musetalk_seconds": round(muse_seconds, 3),
            "gpu_name": gpu.gpu_name,
            "gpu_total_mib": gpu.total_mib,
            "baseline_vram_mib": gpu.baseline_used_mib,
            "peak_vram_mib": gpu.peak_used_mib,
            "peak_delta_mib": max(0, gpu.peak_used_mib - gpu.baseline_used_mib),
            "sample_count": len(gpu.samples),
        }
    )
    if mode in {"wan", "wan_loop"}:
        await comfy.free_memory()
    return result


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "run_id",
        "mode",
        "wan_profile",
        "resolution",
        "wan_render_resolution",
        "audio_duration",
        "total_seconds",
        "base_video_seconds",
        "musetalk_seconds",
        "gpu_name",
        "gpu_total_mib",
        "baseline_vram_mib",
        "peak_vram_mib",
        "peak_delta_mib",
        "sample_count",
        "ok",
        "error",
        "output_video",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in columns})


def write_markdown(path: Path, rows: list[dict], avatar: Path, audio: Path, csv_path: Path) -> None:
    ok_rows = [row for row in rows if row.get("ok")]
    gpu_name = ok_rows[0].get("gpu_name", "") if ok_rows else ""
    gpu_total = ok_rows[0].get("gpu_total_mib", "") if ok_rows else ""
    lines = [
        "# EchoFrame Resolution Benchmark",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- GPU: {gpu_name} ({gpu_total} MiB)",
        f"- Avatar: `{rel(avatar)}`",
        f"- Audio: `{rel(audio)}`",
        f"- CSV: `{rel(csv_path)}`",
        "- Scope: fixed-audio media generation only; LLM and TTS are excluded so resolution effects are easier to compare.",
        "",
        "| Mode | Wan profile | Resolution | Wan render | Audio s | Total s | Base s | MuseTalk s | Peak VRAM MiB | Delta MiB | OK |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {mode} | {wan_profile} | {resolution} | {wan_render_resolution} | {audio_duration} | "
            "{total_seconds} | {base_video_seconds} | {musetalk_seconds} | "
            "{peak_vram_mib} | {peak_delta_mib} | {ok} |".format(**row)
        )
    lines += [
        "",
        "## Consumer GPU Read",
        "",
        "| VRAM tier | Practical read |",
        "|---:|---|",
        "| 8 GB | Not recommended. The current fast/MuseTalk-only path peaks around 8.2 GB on this run. |",
        "| 12 GB | Practical for fast/MuseTalk-only output; not enough for current Wan2.2 14B I2V. |",
        "| 16 GB | Comfortable for fast/MuseTalk-only output; still not enough for current Wan2.2 14B I2V. |",
        "| 24 GB | Minimum practical target for current Wan2.2 14B I2V plus MuseTalk, but headroom is tight. Keep Comfy/MuseTalk unloaded between stages. |",
        "| 32 GB | Comfortable headroom for longer batches, higher resolution experiments, and fewer unload/reload pauses. |",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark EchoFrame resolution vs total time and peak VRAM.")
    parser.add_argument("--modes", nargs="+", default=DEFAULT_MODES, choices=["fast", "wan_loop", "wan"])
    parser.add_argument("--resolutions", nargs="+", type=int, default=DEFAULT_RESOLUTIONS)
    parser.add_argument("--audio", type=Path, default=Path("data/tts_check/standard_female_no_instruct.wav"))
    parser.add_argument("--avatar", type=Path, default=None)
    parser.add_argument("--sample-interval", type=float, default=0.25)
    parser.add_argument("--idle-timeout", type=float, default=1800)
    parser.add_argument("--out-dir", type=Path, default=Path("data/benchmarks"))
    args = parser.parse_args()

    settings = get_settings()
    media = MediaTools(settings)
    audio = args.audio
    if not audio.exists():
        raise FileNotFoundError(f"audio not found: {audio}")
    avatar = args.avatar or latest_avatar()
    if not avatar.exists():
        raise FileNotFoundError(f"avatar not found: {avatar}")

    audio_duration = media.duration(audio)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rows = []
    for mode in args.modes:
        for resolution in args.resolutions:
            row = await run_case(
                mode=mode,
                resolution=resolution,
                avatar=avatar,
                audio=audio,
                audio_duration=audio_duration,
                sample_interval=args.sample_interval,
                idle_timeout=args.idle_timeout,
            )
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)

    csv_path = args.out_dir / f"resolution_matrix_{stamp}.csv"
    md_path = args.out_dir / f"resolution_matrix_{stamp}.md"
    write_csv(csv_path, rows)
    write_markdown(md_path, rows, avatar, audio, csv_path)
    print(json.dumps({"csv": rel(csv_path), "markdown": rel(md_path)}, ensure_ascii=False, indent=2))
    return 0 if all(row.get("ok") for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
