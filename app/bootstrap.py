import argparse
import json

from app.config import get_settings
from app.services.model_manifest import ModelManifest
from app.services.service_manager import ServiceManager


async def _health() -> dict:
    return {name: status.model_dump() for name, status in (await ServiceManager(get_settings()).statuses()).items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="EchoFrame model bootstrap and health checks")
    parser.add_argument("--download", action="store_true", help="download missing models")
    parser.add_argument("--health", action="store_true", help="print service health")
    args = parser.parse_args()

    manifest = ModelManifest(get_settings())
    if args.download:
        try:
            completed = manifest.download_missing()
            print(json.dumps({"downloaded": completed}, ensure_ascii=False, indent=2))
        except RuntimeError as exc:
            print(json.dumps({"downloaded": [], "ok": False, "detail": str(exc)}, ensure_ascii=False, indent=2))
            return 2
    else:
        checks = {name: check.__dict__ for name, check in manifest.check_all().items()}
        print(json.dumps({"models": checks}, ensure_ascii=False, indent=2))

    if args.health:
        import asyncio

        print(json.dumps({"services": asyncio.run(_health())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
