"""System / provider status API."""
from fastapi import APIRouter

from ..providers.registry import system_status, reset_cache
from ..config import SETTINGS

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"ok": True, "app": "SongForge", "version": "0.1.0"}


@router.get("/system/providers")
def providers():
    reset_cache()  # re-probe so config changes show up without restart
    return system_status()
