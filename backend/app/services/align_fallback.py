"""Last-resort alignment used only if the configured aligner throws."""


def fallback_align(lines: list, duration: float) -> list:
    n = max(1, len(lines))
    out = []
    start = 0.5
    span = max(2.0, (duration - 1.0) / n) if duration > 2 else 4.0
    for i, line in enumerate(lines):
        s = start + i * span
        e = min(duration - 0.2, s + span * 0.9)
        words = [{"w": w, "start": s + (e - s) * k / max(1, len(line.split())),
                  "end": s + (e - s) * (k + 1) / max(1, len(line.split()))}
                 for k, w in enumerate(line.split())]
        out.append({"start": round(s, 2), "end": round(e, 2), "text": line, "words": words})
    return out
