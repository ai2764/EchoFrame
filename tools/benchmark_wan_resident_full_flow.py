import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.paths import new_id, run_dir
from app.services.comfy import ComfyClient
from app.services.gpu import gpu_summary
from app.services.media import MediaTools
from app.services.musetalk import MuseTalkClient


PROMPT = (
    "Front-facing bust shot of the same person, subtle blinking, slight nodding, "
    "small shoulder movement, steady camera, clean studio lighting, natural neutral mouth."
)


async def wait_for_comfy_idle(client: ComfyClient, timeout: float = 900) -> None:
    import httpx

    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        async with httpx.AsyncClient(timeout=5.0) as http:
            r = await http.get(client.settings.comfy_url.rstrip("/") + "/queue")
        body = r.json()
        if not body.get("queue_running") and not body.get("queue_pending"):
            return
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


async def main() -> None:
    settings = get_settings()
    settings.comfy_unload_after_wan = False
    media = MediaTools(settings)
    comfy = ComfyClient(settings)
    musetalk = MuseTalkClient(settings)

    avatar = latest_avatar()
    audio = Path("data/tts_check/standard_female_no_instruct.wav")
    if not audio.exists():
        raise FileNotFoundError(f"missing test audio: {audio}")

    await wait_for_comfy_idle(comfy)
    await comfy.free_memory()
    await asyncio.sleep(3)

    run_id = new_id("bench_full_resident")
    out_dir = run_dir(settings, run_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "run_id": run_id,
        "avatar": str(avatar),
        "audio": str(audio),
        "gpu_start": gpu_summary(),
    }

    try:
        duration = media.duration(audio)
        length = media.wan_length_for_duration(duration)
        result["audio_duration"] = round(duration, 3)
        result["wan_length"] = length

        start = time.perf_counter()
        raw_base = await comfy.generate_wan_base(
            image_path=avatar,
            prompt=PROMPT,
            length=length,
            run_id=run_id,
            run_dir=out_dir,
        )
        result["wan_seconds"] = round(time.perf_counter() - start, 3)
        result["gpu_after_wan_resident"] = gpu_summary()

        base = out_dir / "base.mp4"
        start = time.perf_counter()
        media.normalize_video(raw_base, duration, base, 25)
        result["normalize_seconds"] = round(time.perf_counter() - start, 3)
        result["gpu_before_musetalk"] = gpu_summary()

        start = time.perf_counter()
        talk = musetalk.lip_sync(audio, base, out_dir)
        result["musetalk_seconds"] = round(time.perf_counter() - start, 3)
        result["gpu_after_musetalk"] = gpu_summary()
        result["talk_video"] = str(talk)
        result["ok"] = True
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)[-3000:]
        result["gpu_after_error"] = gpu_summary()
    finally:
        await comfy.free_memory()
        result["gpu_after_final_free"] = gpu_summary()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
