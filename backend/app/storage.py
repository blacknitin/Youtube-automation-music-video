"""Local file storage layout (no cloud needed).

data/projects/<pid>/
    audio/        imported songs
    scenes/       generated scene images
    renders/      rendered videos
    meta/         thumbnail etc.
"""
import re
import uuid
from pathlib import Path

from .config import SETTINGS

SAFE = re.compile(r"[^A-Za-z0-9._-]+")

def project_dir(pid: int) -> Path:
    d = SETTINGS.storage_dir / str(pid)
    for sub in ("audio", "scenes", "renders", "meta"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d

def safe_name(name: str) -> str:
    name = SAFE.sub("_", Path(name).name)[:120] or "file"
    return name

def unique_name(name: str) -> str:
    return f"{uuid.uuid4().hex[:8]}_{safe_name(name)}"

def song_path(pid: int, name: str) -> Path:
    return project_dir(pid) / "audio" / unique_name(name)

def scenes_dir(pid: int) -> Path:
    return project_dir(pid) / "scenes"

def scene_image_path(pid: int, idx: int, ext: str = ".jpg") -> Path:
    return scenes_dir(pid) / f"scene_{idx:03d}{ext}"

def renders_dir(pid: int) -> Path:
    return project_dir(pid) / "renders"

def render_path(pid: int, tag: str) -> Path:
    return renders_dir(pid) / f"video_{tag}.mp4"

def meta_dir(pid: int) -> Path:
    return project_dir(pid) / "meta"

def thumbnail_path(pid: int) -> Path:
    return meta_dir(pid) / "thumbnail.jpg"
