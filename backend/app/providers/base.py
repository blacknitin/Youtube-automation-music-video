"""Provider interfaces.

Every AI capability is behind an interface so local providers (Ollama,
ComfyUI, WhisperX) can be swapped for cloud APIs later without touching
the rest of the app:

  LLMProvider      -> lyrics, storyboard, feedback interpretation, metadata
  ImageProvider    -> scene images + thumbnails
  AlignerProvider  -> lyric line timing (forced alignment)
  MusicProvider    -> (future) song generation; MVP uses Suno file import
"""
from dataclasses import dataclass, field

@dataclass
class LyricRequest:
    idea: str
    language: str = "hi"
    genre: str = ""
    mood: str = ""
    title_hint: str = ""

@dataclass
class AnalysisSummary:
    duration: float = 0.0
    bpm: float = 0.0
    sections: list = field(default_factory=list)   # [{name,type,start,end}]

class ProviderUnavailable(Exception):
    pass

class LLMProvider:
    name = "base"
    def available(self) -> bool:
        return True
    def complete_json(self, system: str, user: str, max_tokens: int = 2400) -> dict:
        raise NotImplementedError
    # --- high-level helpers (each returns plain dicts; see services/) ---
    def generate_lyrics(self, req: LyricRequest) -> dict:
        raise NotImplementedError
    def generate_storyboard(self, lyrics: dict, analysis: AnalysisSummary, visual_style: str, idea: str) -> dict:
        raise NotImplementedError
    def generate_scene_prompts(self, scenes: list, style_bible: dict, idea: str, genre: str) -> list:
        """AI-written image/video prompts. scenes: [{index, section, lyrics_text,
        description, shot, motion}] -> [{index, prompt, negative, motion}]."""
        raise NotImplementedError
    def interpret_feedback(self, text: str, context: dict) -> dict:
        raise NotImplementedError
    def generate_metadata(self, context: dict) -> dict:
        raise NotImplementedError

class ImageProvider:
    name = "base"
    def available(self) -> bool:
        return True
    def generate(self, prompt: str, negative: str, out_path, seed: int = 0,
                 width: int = 1280, height: int = 720) -> str:
        raise NotImplementedError

class VideoProvider:
    """Image-to-video — animates a scene image into a short video clip.

    Implementations: ComfyUIVideoProvider (free open-source models —
    Stable Video Diffusion, AnimateDiff, Wan, LTX-Video — via ComfyUI)
    and the built-in FFmpeg Ken-Burns motion fallback.
    """
    name = "base"
    def available(self) -> bool:
        return True
    def animate(self, image_path, duration: float, fps: int, prompt: str,
                out_path, seed: int = 0, width: int = 1280,
                height: int = 720, progress=None) -> str:
        """Produce a silent clip at out_path; return its path. Raise to fail."""
        raise NotImplementedError
    def unload(self):
        """Release any resident models (no-op by default)."""

class AlignerProvider:
    name = "base"
    def available(self) -> bool:
        return True
    def align(self, audio_path, lines: list, language: str, duration: float) -> list:
        """Return [{start, end, words:[{w,start,end}|...]}] per line."""
        raise NotImplementedError

class ASRProvider:
    """Speech-to-text — extracts lyrics (+ timings) FROM a song's vocals."""
    name = "base"
    def available(self) -> bool:
        return True
    def transcribe(self, audio_path, language: str | None = None, progress=None) -> dict:
        """Return {"language": "en", "segments": [{"start","end","text"}]}."""
        raise NotImplementedError
    def unload(self):
        """Release any resident models (no-op by default)."""

class MusicProvider:
    name = "base"
    def available(self) -> bool:
        return False
