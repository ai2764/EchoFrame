import argparse
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


PROMPT = (
    "Front-facing bust shot of the same person, subtle blinking, slight nodding, "
    "small shoulder movement, steady camera, clean studio lighting, natural neutral mouth."
)


async def wait_for_comfy_idle(client: ComfyClient, timeout: float) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        try:
            import httpx

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


async def run_once(client: ComfyClient, avatar: Path, label: str, length: int, cold: bool) -> dict:
    free_seconds = 0.0
    if cold:
        start = time.perf_counter()
        await client.free_memory()
        free_seconds = time.perf_counter() - start
        await asyncio.sleep(3)

    run_id = new_id(f"bench_{label}")
    out_dir = run_dir(client.settings, run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    start_gpu = gpu_summary()
    start = time.perf_counter()
    video = await client.generate_wan_base(
        image_path=avatar,
        prompt=PROMPT,
        length=length,
        run_id=run_id,
        run_dir=out_dir,
    )
    elapsed = time.perf_counter() - start
    end_gpu = gpu_summary()
    return {
        "label": label,
        "cold": cold,
        "length": length,
        "seconds": round(elapsed, 3),
        "free_seconds": round(free_seconds, 3),
        "video": str(video),
        "gpu_before": start_gpu,
        "gpu_after": end_gpu,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--length", type=int, default=17)
    parser.add_argument("--idle-timeout", type=float, default=1800)
    parser.add_argument("--keep-loaded-after", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    settings.comfy_unload_after_wan = False
    client = ComfyClient(settings)
    avatar = latest_avatar()

    await wait_for_comfy_idle(client, args.idle_timeout)
    results = []
    results.append(await run_once(client, avatar, "cold_1", args.length, cold=True))
    results.append(await run_once(client, avatar, "warm_1", args.length, cold=False))
    results.append(await run_once(client, avatar, "warm_2", args.length, cold=False))
    results.append(await run_once(client, avatar, "cold_2", args.length, cold=True))

    if not args.keep_loaded_after:
        await client.free_memory()

    cold = [r["seconds"] for r in results if r["cold"]]
    warm = [r["seconds"] for r in results if not r["cold"]]
    summary = {
        "avatar": str(avatar),
        "wan": {
            "width": settings.wan_width,
            "height": settings.wan_height,
            "fps": settings.wan_fps,
            "length": args.length,
        },
        "results": results,
        "summary": {
            "cold_avg_seconds": round(sum(cold) / len(cold), 3),
            "warm_avg_seconds": round(sum(warm) / len(warm), 3),
            "estimated_model_residency_saving_seconds": round(
                (sum(cold) / len(cold)) - (sum(warm) / len(warm)),
                3,
            ),
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
