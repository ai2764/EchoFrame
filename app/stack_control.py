import argparse
import asyncio
import json

from app.config import get_settings
from app.services.service_manifest import service_manifest
from app.services.service_manager import ServiceManager


async def _run(action: str, names: list[str]) -> dict:
    manager = ServiceManager(get_settings())
    output = {}
    for name in names:
        if action == "start":
            result = await manager.start(name)
        elif action == "stop":
            result = await manager.stop(name)
        elif action == "restart":
            result = await manager.restart(name)
        else:
            result = await manager.status(name)
        output[name] = result.model_dump()
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="EchoFrame service control")
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "manifest"])
    parser.add_argument("services", nargs="*", default=["lm_studio", "cosyvoice", "comfyui"])
    args = parser.parse_args()
    if args.action == "manifest":
        print(json.dumps(service_manifest(get_settings()), ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(asyncio.run(_run(args.action, args.services)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
