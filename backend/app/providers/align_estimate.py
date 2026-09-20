"""Estimate aligner — no external deps.

Distributes lyric lines across the song using section boundaries (from audio
analysis) and per-line character weights. Used when WhisperX isn't installed.
"""
import re

from .base import AlignerProvider

_norm = re.compile(r"[^\w\u0900-\u097F]+")

def norm_text(s: str) -> str:
    return _norm.sub(" ", (s or "").lower()).strip()


class EstimateAligner(AlignerProvider):
    name = "estimate"

    def align(self, audio_path, lines: list, language: str, duration: float,
              sections: list | None = None) -> list:
        n = len(lines)
        if n == 0:
            return []
        # map lines to analysis sections if available
        spans = []
        if sections:
            sec_list = [s for s in sections if s.get("end", 0) > s.get("start", 0)]
            if sec_list:
                sec_list[0]["start"] = 0.0
                sec_list[-1]["end"] = duration
                # weight of each section = its line count (falls back to equal)
                weights, k = [], 0
                for i, s in enumerate(sec_list):
                    weights.append(max(1, s.get("line_count", 1)))
                total = sum(weights)
                pos = 0.0
                for s, w in zip(sec_list, weights):
                    span = (s["end"] - s["start"]) * (w / total) if False else (s["end"] - s["start"])
                    spans.append((pos, pos + span))
                    pos += span
        if not spans:
            spans = [(0.0, duration)]
        # distribute lines across spans proportionally to character length
        weights = [max(4.0, len(norm_text(l))) for l in lines]
        total = sum(weights)
        out, cursor = [], spans[0][0]
        # build global timeline: allocate each line inside its target span
        sec_of_line = []
        if sections:
            sec_idx, counts = 0, 0
            per_sec = max(1, round(n / len(sections)))
            for i in range(n):
                sec_of_line.append(min(sec_idx, len(sections) - 1))
                counts += 1
                if counts >= per_sec and sec_idx < len(sections) - 1:
                    sec_idx += 1
                    counts = 0
        else:
            sec_of_line = [0] * n
        # group line indices by section index, then split each section span
        groups = {}
        for i, si in enumerate(sec_of_line):
            groups.setdefault(si, []).append(i)
        times = {}
        for si, idxs in groups.items():
            if sections and si < len(sections):
                a = max(0.0, sections[si].get("start", 0.0))
                b = min(duration, sections[si].get("end", duration))
            else:
                a, b = 0.0, duration
            gw = sum(max(4.0, len(norm_text(lines[i]))) for i in idxs)
            t = a
            for j, i in enumerate(idxs):
                w = max(4.0, len(norm_text(lines[i])))
                d = (b - a) * (w / gw)
                end = b if j == len(idxs) - 1 else min(b, t + d)
                times[i] = (t, max(t + 0.8, end))
                t = end
        for i, line in enumerate(lines):
            s, e = times.get(i, (i * duration / n, (i + 1) * duration / n))
            words = [{"w": w, "start": s + (e - s) * k / max(1, len(line.split())),
                      "end": s + (e - s) * (k + 1) / max(1, len(line.split()))}
                     for k, w in enumerate(line.split())]
            out.append({"start": round(s, 2), "end": round(e, 2), "text": line, "words": words})
        return out
