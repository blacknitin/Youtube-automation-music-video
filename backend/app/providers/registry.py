"""Provider registry — resolves the active providers with smart fallbacks.

LLM_PROVIDER / IMAGE_PROVIDER / ALIGNER = "auto" (default):
  LLM:    ollama (if reachable) -> free AI (if FREE_LLM_API_KEY set) -> mock
  IMAGE:  comfyui (if reachable) -> placeholder
  ALIGNER: whisperx (if importable) -> estimate
Set them explicitly via .env to force a provider (or to add cloud APIs).
"""
import threading

import httpx

from ..config import SETTINGS
from .base import LLMProvider, ImageProvider, AlignerProvider, ASRProvider, VideoProvider
from .llm_mock import MockLLMProvider
from .llm_ollama import OllamaProvider
from .llm_openai import OpenAICompatProvider
from .llm_free import FreeLLMProvider
from .image_placeholder import PlaceholderImageProvider
from .image_comfyui import ComfyUIImageProvider
from .image_openmontage import OpenMontageImageProvider
from .align_estimate import EstimateAligner
from .asr_mock import MockASRProvider
from .video_comfyui import ComfyUIVideoProvider
from .character_animated import AnimatedDrawingsProvider
from .video_diffusers import DiffusersVideoProvider
from .video_openmontage import OpenMontageProvider

_lock = threading.Lock()
_cache = {}

def _ollama_ok() -> bool:
    try:
        return httpx.get(f"{SETTINGS.ollama_url.rstrip('/')}/api/tags", timeout=1.5).status_code == 200
    except Exception:
        return False

def _comfy_ok() -> bool:
    try:
        return httpx.get(f"{SETTINGS.comfy_url.rstrip('/')}/system_stats", timeout=1.5).status_code == 200
    except Exception:
        return False

def _whisperx_ok() -> bool:
    try:
        import whisperx  # noqa: F401
        return True
    except Exception:
        return False

def _fw_ok() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False

def get_llm() -> LLMProvider:
    with _lock:
        if "llm" in _cache:
            return _cache["llm"]
        p = SETTINGS.llm_provider.lower()
        free = FreeLLMProvider()
        if p == "ollama" or (p == "auto" and _ollama_ok()):
            prov = OllamaProvider()
        elif free.available() and (p == "auto" or p in ("free", "groq", "gemini", "openrouter")):
            prov = free
        elif p == "openai":
            prov = OpenAICompatProvider()
        else:
            prov = MockLLMProvider()
        _cache["llm"] = prov
        return prov

def get_image_provider() -> ImageProvider:
    with _lock:
        if "image" in _cache:
            return _cache["image"]
        p = SETTINGS.image_provider.lower()
        om = OpenMontageImageProvider()
        if p in ("openmontage", "montage") or (p == "auto" and om.available()):
            prov = om
        elif p == "comfyui" or (p == "auto" and _comfy_ok()):
            prov = ComfyUIImageProvider()
        else:
            prov = PlaceholderImageProvider()
        _cache["image"] = prov
        return prov

def get_aligner() -> AlignerProvider:
    with _lock:
        if "aligner" in _cache:
            return _cache["aligner"]
        p = (SETTINGS.aligner or "auto").lower()
        if p == "whisperx" or (p == "auto" and _whisperx_ok()):
            try:
                from .align_whisperx import WhisperXAligner
                prov = WhisperXAligner()
            except Exception:
                prov = EstimateAligner()
        else:
            prov = EstimateAligner()
        _cache["aligner"] = prov
        return prov

def get_asr() -> ASRProvider:
    with _lock:
        if "asr" in _cache:
            return _cache["asr"]
        p = (SETTINGS.asr_provider or "auto").lower()
        if p in ("faster", "faster-whisper", "whisper") or (p == "auto" and _fw_ok()):
            try:
                from .asr_faster import FasterWhisperASR
                prov = FasterWhisperASR()
            except Exception:
                prov = MockASRProvider()
        else:
            prov = MockASRProvider()
        _cache["asr"] = prov
        return prov

class _FFmpegMotionVideoProvider(VideoProvider):
    """Built-in fallback: FFmpeg Ken-Burns motion (what render.py already does).
    Represented here so the UI can name the active video provider."""
    name = "ffmpeg-motion"
    def available(self) -> bool:
        return True

def get_video_provider() -> VideoProvider:
    """comfyui (free open-source video models) when reachable+configured, else
    the built-in ffmpeg-motion fallback used inside render_video."""
    with _lock:
        if "video" in _cache:
            return _cache["video"]
        p = (SETTINGS.video_provider or "auto").lower()
        ad = AnimatedDrawingsProvider()
        cv = ComfyUIVideoProvider()
        dv = DiffusersVideoProvider()
        if p in ("char", "char-animated", "animated-drawings") or (p == "auto" and ad.available()):
            prov = ad
        elif p == "comfyui" or (p == "auto" and cv.available()):
            prov = cv
        elif p in ("openmontage", "montage") or (p == "auto" and OpenMontageProvider().available()):
            prov = OpenMontageProvider()
        elif p == "diffusers" or (p == "auto" and dv.available()):
            prov = dv
        else:
            prov = _FFmpegMotionVideoProvider()
        _cache["video"] = prov
        return prov

def reset_cache():
    with _lock:
        _cache.clear()

def system_status() -> dict:
    llm = get_llm()
    img = get_image_provider()
    alg = get_aligner()
    import shutil
    return {
        "llm": {"active": llm.name, "configured": SETTINGS.llm_provider,
                "ollama_reachable": _ollama_ok(), "model": SETTINGS.ollama_model,
                "free": FreeLLMProvider().info()},
        "image": {"active": img.name, "configured": SETTINGS.image_provider,
                  "comfyui_reachable": _comfy_ok(),
                  "openmontage_art": isinstance(img, OpenMontageImageProvider)},
        "aligner": {"active": alg.name, "configured": SETTINGS.aligner,
                    "whisperx_installed": _whisperx_ok()},
        "asr": {"active": get_asr().name, "configured": SETTINGS.asr_provider,
                "faster_whisper_installed": _fw_ok(), "model": SETTINGS.asr_model},
        "video": {"active": get_video_provider().name,
                  "configured": SETTINGS.video_provider,
                  "comfyui_reachable": _comfy_ok(),
                  "workflow_set": bool(SETTINGS.comfy_video_workflow),
                  "char_anim_repo_set": bool(SETTINGS.char_anim_repo),
                  "diffusers_model": SETTINGS.video_diffusers_model or None,
                  "openmontage_repo_set": bool(SETTINGS.openmontage_repo),
                  "openmontage_engine": SETTINGS.openmontage_engine},
        "ffmpeg": {"ffmpeg_found": bool(shutil.which(SETTINGS.ffmpeg_bin)),
                   "ffprobe_found": bool(shutil.which(SETTINGS.ffprobe_bin))},
        "youtube": {"client_configured": bool(SETTINGS.youtube_client_id and SETTINGS.youtube_client_secret)},
        "data_dir": str(SETTINGS.data_dir),
    }
