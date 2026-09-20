"""Lyrics extraction — listen to the song, transcribe the vocals, build lyrics.

ASR (faster-whisper when installed, else the demo provider) yields text
segments with timestamps. We merge them into lyric lines, detect structure
(repeated lines -> Chorus, leading/trailing instrumentals -> Intro/Outro) and
store the EXACT per-line timings in AudioAnalysis.alignment_json so the
storyboard, subtitles and final render stay locked to the real vocal timing.
"""
import json

from ..models import AudioAnalysis, Lyrics, PJ, Song, Status
from ..providers.align_estimate import norm_text
from ..providers.registry import get_asr
from ..config import SETTINGS


def _lines_from_segments(segments, word_gap=0.45, max_chars=80) -> list:
    """Turn ASR segments into lyric LINES using word timestamps.

    A new line starts when the singer pauses (>word_gap between words), when a
    sentence ends (./!/?) followed by a pause, or when the line gets long.
    Falls back to whole segments when no word timings exist.
    """
    lines = []

    def add(s, e, text):
        text = (text or "").strip()
        if text:
            lines.append({"start": max(0.0, s - 0.15), "end": e + 0.25, "text": text})

    for seg in segments:
        words = seg.get("words") or []
        if not words:
            add(float(seg.get("start", 0) or 0), float(seg.get("end", 0) or 0),
                seg.get("text"))
            continue
        cur_s, cur_t = None, ""
        prev_end = None
        for w in words:
            t = (w.get("word") or "").strip()
            if not t:
                continue
            ws, we = float(w["start"]), float(w["end"])
            pause = (ws - prev_end) if prev_end is not None else 0.0
            sentence_end = cur_t.rstrip().endswith((".", "!", "?"))
            n_words = len(cur_t.split())
            if cur_t and ((pause > word_gap and (n_words >= 5 or pause > 1.2))
                          or (sentence_end and pause > 0.3)
                          or len(cur_t) > max_chars):
                add(cur_s, prev_end, cur_t)
                cur_s, cur_t = None, ""
            if cur_s is None:
                cur_s = ws
                cur_t = t
            else:
                cur_t += " " + t
            prev_end = we
        add(cur_s, prev_end or float(seg.get("end", 0) or 0), cur_t)

    # merge micro-fragments (< 3 words) into the previous line when close
    merged = []
    for l in lines:
        if (merged and len(l["text"].split()) < 3
                and l["start"] - merged[-1]["end"] < 0.8
                and len(merged[-1]["text"]) < max_chars):
            merged[-1]["end"] = l["end"]
            merged[-1]["text"] += " " + l["text"]
        else:
            merged.append(l)
    return merged


# Backwards-compatible alias
def _merge_segments(segments, max_gap=0.45, max_chars=80) -> list:
    return _lines_from_segments(segments, word_gap=max_gap, max_chars=max_chars)


def _sectionize(lines: list, duration: float) -> list:
    """Group lines into Verse/Chorus sections; Intro/Outro for instrumentals."""
    keys = [norm_text(l["text"]) for l in lines]
    counts = {}
    for k in keys:
        if len(k.split()) >= 3:
            counts[k] = counts.get(k, 0) + 1
    chorus_keys = {k for k, c in counts.items() if c >= 2}

    sections = []  # [{name, lines:[str], kind}]
    verse_no = 0
    for l, k in zip(lines, keys):
        kind = "chorus" if k in chorus_keys else "verse"
        if sections and sections[-1]["kind"] == kind:
            sections[-1]["lines"].append(l["text"])
        else:
            if kind == "chorus":
                name = "Chorus"
            else:
                verse_no += 1
                name = f"Verse {verse_no}"
            sections.append({"name": name, "lines": [l["text"]], "kind": kind})

    out = []
    if lines and lines[0]["start"] >= 3.0:
        out.append({"name": "Intro", "lines": []})
    out += sections
    if lines and (duration or lines[-1]["end"]) - lines[-1]["end"] >= 3.0:
        out.append({"name": "Outro", "lines": []})
    return [{"name": s["name"], "lines": s["lines"]} for s in out]


def extract_lyrics_from_song(db, project, progress=None) -> dict:
    song = (db.query(Song).filter(Song.project_id == project.id)
              .order_by(Song.id.desc()).first())
    if not song or not song.path:
        raise RuntimeError("Import or create a song first — nothing to listen to.")

    analysis = (db.query(AudioAnalysis).filter(AudioAnalysis.song_id == song.id)
                  .order_by(AudioAnalysis.id.desc()).first())
    if not analysis or analysis.duration <= 0:
        from .audio import analyze
        if progress:
            progress(5, "Analyzing audio…")
        info = analyze(song.path)
        analysis = AudioAnalysis(
            song_id=song.id, duration=info["duration"], bpm=info["bpm"],
            beat_offset=info["beat_offset"],
            sections_json=json.dumps(info["sections"]),
            peaks_json=json.dumps(info["peaks"]), energy_json=json.dumps(info["energy"]))
        db.add(analysis)
        db.commit()  # commit before ASR progress() writes

    asr = get_asr()
    lang = project.language if project.language in ("en", "hi") else None
    try:
        res = asr.transcribe(song.path, language=lang, progress=progress)
    finally:
        unload = getattr(asr, "unload", None)   # free model RAM before rendering
        if unload:
            unload()
    lines = _lines_from_segments(res.get("segments", []))
    if not lines:
        raise RuntimeError("No vocals detected in this track — is it instrumental?")

    duration = analysis.duration or lines[-1]["end"]
    sections = _sectionize(lines, duration)
    timings = [{"start": round(l["start"], 2), "end": round(l["end"], 2), "text": l["text"]}
               for l in lines]

    data = {"title": project.title, "sections": sections,
            "meta": {"extraction": {"provider": asr.name,
                                    "language": res.get("language") or "",
                                    "lines": len(lines), "timings": timings}}}
    lyr = Lyrics(project_id=project.id, content_json=json.dumps(data, ensure_ascii=False),
                 language=(res.get("language") or project.language or "hi")[:12],
                 status="draft", source="extracted")
    db.add(lyr)

    # exact vocal timing — downstream (arrange/subtitles/render) reads this
    analysis.alignment_json = json.dumps(timings, ensure_ascii=False)
    db.add(analysis)

    # auto-approve extracted lyrics by default (extract -> approved flow; the
    # user can still edit and re-approve in the Lyrics step)
    auto = SETTINGS.auto_approve_lyrics
    if auto:
        lyr.status = "approved"
        import datetime as _dt
        lyr.approved_at = _dt.datetime.now(_dt.timezone.utc)
        if project.status in (Status.CREATED, Status.LYRICS_DRAFT):
            project.status = Status.LYRICS_APPROVED
    else:
        project.status = Status.LYRICS_DRAFT
    db.add(project)
    db.commit()
    if progress:
        progress(97, f"Extracted {len(lines)} lines "
                     f"({', '.join(s['name'] for s in sections)})"
                     + (" — auto-approved ✓" if auto else ""))
    return {"lyrics_id": lyr.id, "lines": len(lines), "language": lyr.language,
            "sections": [s["name"] for s in sections], "provider": asr.name}
