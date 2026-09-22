"""AI song generation with MusicGen (facebookresearch/audiocraft's model,
Apache-2.0 — run free via HuggingFace transformers on CPU or GPU).

Generates original instrumental music from an AI-written text description.
Vocals still come from your Suno imports (MusicGen is instrumental-only);
this powers the "AI song" button so a project can start with ZERO uploads.

Music description prompts are written by the active LLM (never hardcoded);
if the LLM is unavailable a genre/mood template is used.
"""
import wave

import numpy as np

from ..config import SETTINGS

SR = 32000  # musicgen output sample rate


def musicgen_available() -> bool:
    try:
        import torch  # noqa: F401
        from transformers import MusicgenForConditionalGeneration  # noqa: F401
        return True
    except Exception:
        return False


def write_wav(path, audio: np.ndarray, sr: int = SR):
    audio = np.clip(audio, -1.0, 1.0)
    data = (audio * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def music_description_prompt(idea: str, genre: str, mood: str) -> str:
    """The active LLM writes the music description; template fallback."""
    try:
        from .registry import get_llm
        llm = get_llm()
        data = llm.complete_json(
            "You are a music director. Describe instrumental music in ONE vivid "
            "English sentence for a text-to-music model. Include: genre, tempo "
            "(BPM), key instruments, mood, energy arc. 25-40 words. "
            'Respond ONLY with JSON: {"description": "..."}',
            f"Song idea: {idea}\nGenre: {genre or 'any'}\nMood: {mood or 'uplifting'}",
            max_tokens=200)
        d = (data.get("description") or "").strip()
        if d:
            return d
    except Exception:
        pass
    g = (genre or "devotional").strip()
    m = (mood or "uplifting").strip()
    return (f"A {m} {g} instrumental at a gentle tempo, warm tabla and harmonium, "
            f"soaring flute melody, soft strings, cinematic build, {idea[:80]}")


class MusicgenProvider:
    """Local MusicGen — free, original, royalty-free instrumentals."""
    name = "musicgen"

    def available(self) -> bool:
        return musicgen_available()

    def info(self) -> dict:
        return {"model": SETTINGS.musicgen_model,
                "seconds": SETTINGS.musicgen_seconds,
                "installed": musicgen_available()}

    def generate(self, out_path, description: str, seconds: float | None = None,
                 guidance: float = 3.0) -> str:
        import torch
        from transformers import AutoProcessor, MusicgenForConditionalGeneration
        seconds = float(seconds or SETTINGS.musicgen_seconds)
        seconds = max(5.0, min(seconds, 60.0))
        tokens = min(int(seconds * 50), 3000)  # musicgen frame rate = 50 Hz

        proc = AutoProcessor.from_pretrained(SETTINGS.musicgen_model)
        model = MusicgenForConditionalGeneration.from_pretrained(SETTINGS.musicgen_model)
        model.eval()
        inputs = proc(text=[description], padding=True, return_tensors="pt")
        with torch.no_grad():
            audio = model.generate(**inputs, max_new_tokens=tokens,
                                   guidance_scale=guidance, do_sample=True)
        wav = audio[0, 0].cpu().numpy()
        write_wav(out_path, wav)
        del model
        return str(out_path)


class SynthMusicProvider:
    """Fallback: built-in numpy demo loop (always available, instant)."""
    name = "synth"

    def available(self) -> bool:
        return True

    def info(self) -> dict:
        return {"model": "builtin-demo-loop", "seconds": 38, "installed": True}

    def generate(self, out_path, description: str, seconds: float | None = None,
                 guidance: float = 3.0) -> str:
        from ..services.audio import synthesize_demo_song
        return synthesize_demo_song(out_path)


def get_music_provider():
    p = (SETTINGS.music_provider or "auto").lower()
    mg = MusicgenProvider()
    if p in ("musicgen", "ai") or (p == "auto" and mg.available()):
        return mg
    return SynthMusicProvider()
