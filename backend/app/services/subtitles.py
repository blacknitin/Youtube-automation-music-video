"""ASS subtitle builder — synchronized animated lyrics.

Line-level fade-in captions; karaoke word-fill when word timings exist.
"""
import json

from ..config import SETTINGS


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(alignment: list, duration: float, width=1280, height=720,
              font: str | None = None, karaoke: bool = True) -> str:
    font = font or SETTINGS.subtitle_font
    font_size = max(28, int(height / 22))
    margin_v = max(24, int(height / 12))
    header = f"""[Script Info]
Title: SongForge Lyrics
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Lyrics,{font},{font_size},&H00FFFFFF,&H00F59E0B,&HA0000000,&H80000000,0,0,0,0,100,100,0,0,1,2.4,1.4,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for line in alignment:
        s, e = line.get("start"), line.get("end")
        if s is None or e is None or e <= s:
            continue
        text = (line.get("text") or "").strip()
        if not text:
            continue
        words = line.get("words") or []
        if karaoke and len(words) >= 2:
            parts, prev = [], s
            for w in words:
                ws, we = w.get("start"), w.get("end")
                if ws is None or we is None:
                    continue
                gap = max(0, int((ws - prev) * 100))
                dur = max(6, int((we - max(ws, prev)) * 100))
                if gap:
                    parts.append(f"{{\\k{gap}}} ")
                token = str(w.get("w") or w.get("word") or "").strip()
                parts.append(f"{{\\kf{dur}}}{token}")
                prev = we
            body = " ".join(p.strip() if p.startswith("{\\k") and not p.endswith("}") else p for p in parts).strip()
            if not body:
                body = f"{{\\fad(180,180)}}{text}"
            else:
                body = f"{{\\fad(150,150)}}{body}"
        else:
            body = f"{{\\fad(180,180)}}{text}"
        events.append(f"Dialogue: 0,{_ass_time(s)},{_ass_time(e)},Lyrics,,0,0,0,,{body}")
    return header + "\n".join(events) + "\n"


def write_ass(path, alignment: list, duration: float, width=1280, height=720,
              font: str | None = None, karaoke: bool = True):
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_ass(alignment, duration, width, height, font, karaoke))
    return str(path)
