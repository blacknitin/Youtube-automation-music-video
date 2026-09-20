"""FasterWhisper ASR — free, local lyrics extraction (CPU-friendly).

Install with:  pip install -r requirements-asr.txt
Set ASR_PROVIDER=faster-whisper (or leave "auto" — it is used when importable).
The first run downloads the whisper model (~75–150 MB for tiny/base) into the
standard HuggingFace cache; afterwards it works fully offline.
"""
import os

from .base import ASRProvider
from ..config import SETTINGS


class FasterWhisperASR(ASRProvider):
    name = "faster-whisper"

    def __init__(self, model_size=None):
        self.model_size = model_size or SETTINGS.asr_model
        self._model = None

    def available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except Exception:
            return False

    def _load(self, progress=None):
        if self._model is None:
            from faster_whisper import WhisperModel
            if progress:
                progress(15, f"Loading whisper '{self.model_size}' (first run downloads it)…")
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8",
                                       cpu_threads=max(1, os.cpu_count() or 2))
        return self._model

    def transcribe(self, audio_path, language: str | None = None, progress=None) -> dict:
        model = self._load(progress)
        if progress:
            progress(35, "Listening for vocals…")
        segments, info = model.transcribe(
            str(audio_path),
            language=(language or None),
            beam_size=1,
            word_timestamps=True,               # lets us split segments into lines
            vad_filter=True,                    # skip instrumental-only parts
            condition_on_previous_text=False,   # more robust against music hallucinations
        )
        segs = []
        total = float(getattr(info, "duration", 0.0) or 0.0)
        for seg in segments:  # generator — the actual transcription happens here
            segs.append({"start": float(seg.start), "end": float(seg.end),
                         "text": (seg.text or "").strip(),
                         "words": [{"start": w.start, "end": w.end, "word": w.word}
                                   for w in (seg.words or [])
                                   if w.start is not None and w.end is not None]})
            if progress and total > 0:
                progress(min(88.0, 35 + 50 * min(1.0, float(seg.end) / total)),
                         "Transcribing vocals…")
        return {"language": getattr(info, "language", None) or language or "en",
                "segments": segs}

    def unload(self):
        """Free the whisper model — on small (2GB) boxes the resident model
        otherwise starves the final video encode (ffmpeg exit -9)."""
        if self._model is not None:
            self._model = None
            import gc
            gc.collect()
