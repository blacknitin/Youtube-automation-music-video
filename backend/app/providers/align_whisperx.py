"""WhisperX aligner — word-level lyric timing (optional, heavy dependency).

Install with:  pip install -r requirements-whisperx.txt
Set ALIGNER=whisperx (or leave "auto" — it is used when importable).
Lyric lines are matched to WhisperX word timestamps via sequence alignment.
"""
import difflib

from .base import AlignerProvider, ProviderUnavailable
from ..config import SETTINGS
from .align_estimate import norm_text


class WhisperXAligner(AlignerProvider):
    name = "whisperx"

    def __init__(self, model_size=None):
        self.model_size = model_size or SETTINGS.whisperx_model

    def available(self) -> bool:
        try:
            import whisperx  # noqa: F401
            return True
        except Exception:
            return False

    def align(self, audio_path, lines: list, language: str, duration: float, sections=None):
        if not lines:
            return []
        try:
            import torch
            import whisperx
        except Exception as e:  # pragma: no cover
            raise ProviderUnavailable(f"whisperx not installed: {e}")

        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute = "float16" if device == "cuda" else "int8"
        model = whisperx.load_model(self.model_size, device, compute_type=compute)
        audio = whisperx.load_audio(str(audio_path))
        result = model.transcribe(audio, language=(language if language != "en" else "en"))
        lang_code = result.get("language", language or "en")
        align_model, meta = whisperx.load_align_model(lang_code, device)
        result = whisperx.align(result["segments"], align_model, meta, audio, device, return_char_alignments=False)

        words = [{"w": w.get("word", "").strip(), "start": w.get("start"), "end": w.get("end")}
                 for seg in result.get("segments", []) for w in seg.get("words", [])
                 if w.get("start") is not None]
        wtexts = [norm_text(w["w"]) for w in words]

        out, wi = [], 0
        for i, line in enumerate(lines):
            tokens = [t for t in norm_text(line).split() if t]
            if not tokens:
                out.append({"start": None, "end": None, "text": line, "words": []})
                continue
            # find best matching window in whisper words (simple greedy scan)
            best_j, best_score = None, -1.0
            for j in range(wi, min(len(words), wi + 60)):
                window = wtexts[j:j + len(tokens)]
                if not window:
                    break
                score = difflib.SequenceMatcher(None, tokens, window).ratio()
                if score > best_score:
                    best_score, best_j = score, j
            if best_j is None or best_score < 0.35:
                out.append({"start": None, "end": None, "text": line, "words": []})
                continue
            seg = words[best_j:best_j + len(tokens)]
            wi = best_j + 1
            wds = [{"w": tokens[k], "start": seg[k]["start"], "end": seg[k]["end"]}
                   for k in range(min(len(tokens), len(seg))) if seg[k]["start"] is not None]
            start = wds[0]["start"] if wds else None
            end = wds[-1]["end"] if wds else None
            out.append({"start": round(start, 2) if start is not None else None,
                        "end": round(end + 0.15, 2) if end is not None else None,
                        "text": line, "words": wds})
        # fill gaps by interpolation
        last = 0.0
        for item in out:
            if item["start"] is None:
                nxt = next((o["start"] for o in out[out.index(item) + 1:] if o["start"] is not None), duration)
                item["start"], item["end"] = last, max(last + 1.0, nxt - 0.1)
            last = item["end"]
        return out
