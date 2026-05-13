from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from app.config import Settings


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def avatar_dir(settings: Settings, avatar_id: str) -> Path:
    return settings.abs_data_dir / "avatars" / avatar_id


def run_dir(settings: Settings, run_id: str) -> Path:
    return settings.abs_data_dir / "runs" / run_id


def ensure_inside(base: Path, path: Path) -> Path:
    base_r = base.resolve()
    path_r = path.resolve()
    try:
        path_r.relative_to(base_r)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes data directory") from exc
    return path_r


def media_url(settings: Settings, path: Path) -> str:
    p = ensure_inside(settings.abs_data_dir, path)
    rel = p.relative_to(settings.abs_data_dir).as_posix()
    return f"/media/{rel}"

