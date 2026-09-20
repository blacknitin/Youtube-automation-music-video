"""Mock ASR — deterministic demo lyrics for instrumental/demo tracks.

Used when no real ASR provider is installed (see requirements-asr.txt for the
real one). Produces clearly-structured demo lines with a repeated chorus so
the whole downstream flow (sections, per-line scenes, timed subtitles) can be
demonstrated without a microphone-quality vocal stem.
"""
from .base import ASRProvider


class MockASRProvider(ASRProvider):
    name = "mock"

    _LINES = [
        "Rise like the mountain, shine like the sun",
        "Carry the flame till the dark is done",
        "Jai Jai Hanuman, ocean of might",
        "Jai Jai Hanuman, guide us with light",
        "Cross every river, unafraid, alone",
        "Faith is the compass that leads us home",
        "Jai Jai Hanuman, ocean of might",
        "Jai Jai Hanuman, guide us with light",
    ]

    def available(self) -> bool:
        return True

    def transcribe(self, audio_path, language: str | None = None, progress=None) -> dict:
        if progress:
            progress(40, "Demo extractor: laying out timed demo lines…")
        import wave
        duration = 0.0
        try:
            with wave.open(str(audio_path), "rb") as w:
                duration = w.getnframes() / max(1, w.getframerate())
        except Exception:
            duration = 0.0
        if duration <= 0:
            from .align_estimate import norm_text  # noqa: F401  (kept for parity)
            duration = 38.0
        segs = []
        intro = duration * 0.06
        span = (duration * 0.88) / len(self._LINES)
        for i, text in enumerate(self._LINES):
            s = intro + i * span
            segs.append({"start": round(s, 2), "end": round(s + span * 0.92, 2), "text": text})
        return {"language": language or "en", "segments": segs}
