from __future__ import annotations

import json
import time
from pathlib import Path

from app.config import Settings
from app.services.service_manager import ServiceManager


class StartupHealth:
    def __init__(self) -> None:
        self.checked_at: float | None = None
        self.statuses: dict = {}
        self.error: str = ""

    async def run(self, settings: Settings) -> dict:
        self.checked_at = time.time()
        self.error = ""
        try:
            manager = ServiceManager(settings)
            self.statuses = {name: status.model_dump() for name, status in (await manager.statuses()).items()}
        except Exception as exc:
            self.statuses = {}
            self.error = str(exc)
        self._write(settings)
        return self.snapshot()

    def snapshot(self) -> dict:
        return {
            "checked_at": self.checked_at,
            "ok": bool(self.statuses) and all(item.get("ok") for item in self.statuses.values()),
            "error": self.error,
            "services": self.statuses,
        }

    def _write(self, settings: Settings) -> None:
        path = self.path(settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def path(settings: Settings) -> Path:
        return settings.abs_data_dir / "logs" / "startup_health.json"


startup_health = StartupHealth()
