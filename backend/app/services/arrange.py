"""Timing arrangement — the bridge between lyrics, audio analysis and scenes.

1. Align lyric lines to the music (WhisperX if available, else weighted estimate).
2. Give every lyric section a time range.
3. Give every scene a contiguous time range (boundaries snapped to beats).
"""
import math

from ..models import PJ
from ..providers.registry import get_aligner
from ..providers.align_estimate import norm_text


def align_lines(db, project, analysis, lyrics: dict) -> list:
    """Return [{start,end,text,words}] for every lyric line; persists to analysis row."""
    lines, sec_index = [], []
    for si, sec in enumerate(lyrics.get("sections", [])):
        sec.setdefault("line_count", len(sec.get("lines", [])))
        for line in sec.get("lines", []):
            if line and line.strip():
                lines.append(line.strip())
                sec_index.append(si)

    # If exact per-line timings are already stored (lyrics extraction wrote them),
    # reuse them instead of re-estimating — they are ground truth from the vocals.
    existing = PJ(analysis.alignment_json) if analysis else None
    if existing:
        pool = {}
        for a in existing:
            if a.get("text") and a.get("start") is not None:
                pool.setdefault(norm_text(a["text"]), []).append(a)
        if lines and pool:
            hits = sum(1 for l in lines if norm_text(l) in pool)
            if hits >= max(1, int(0.8 * len(lines))):
                aligned = []
                for l in lines:
                    arr = pool.get(norm_text(l))
                    if arr:
                        a = arr.pop(0)
                        aligned.append({"start": float(a["start"]), "end": float(a["end"]),
                                        "text": l, "words": a.get("words", [])})
                    else:
                        aligned.append({"start": None, "end": None, "text": l, "words": []})
                analysis.alignment_json = _dj(aligned)
                return aligned

    sections = PJ(analysis.sections_json) or []
    if not sections and analysis.duration:
        sections = [{"name": "Full", "type": "verse", "start": 0.0, "end": analysis.duration}]
    # attach line counts to analysis sections (for the estimate aligner)
    if sections:
        per = max(1, round(len(lines) / len(sections)))
        for i, s in enumerate(sections):
            s["line_count"] = min(per, max(0, len(lines) - i * per))
    aligner = get_aligner()
    try:
        if aligner.name == "estimate":
            aligned = aligner.align(None, lines, project.language, analysis.duration or 0.0, sections)
        else:
            aligned = aligner.align(str(_song_path(db, project)), lines, project.language,
                                    analysis.duration or 0.0, sections)
    except Exception:
        from .align_fallback import fallback_align  # never fail the pipeline here
        aligned = fallback_align(lines, analysis.duration or 0.0)
    analysis.alignment_json = _dj(aligned)
    return aligned


def _dj(v):
    import json
    return json.dumps(v, ensure_ascii=False)


def _song_path(db, project):
    from ..models import Song
    song = db.query(Song).filter(Song.project_id == project.id).order_by(Song.id.desc()).first()
    return song.path if song else ""


def section_ranges(lyrics: dict, alignment: list, analysis_sections: list, duration: float) -> dict:
    """Compute time range for each lyrics section -> {section_key: (start,end)}.

    section_key is "name#occurrence" so repeated sections (Chorus x3) are distinct.
    """
    ranges, cursor = {}, 0.0
    ai = 0
    line_ptr = 0
    sec_ranges = []
    for sec in lyrics.get("sections", []):
        n = len([l for l in sec.get("lines", []) if l and l.strip()])
        if n == 0:
            # instrumental section: use analysis section bounds if they fit the order
            if ai < len(analysis_sections):
                s = max(cursor, float(analysis_sections[ai].get("start", cursor)))
                e = max(s + 1.0, float(analysis_sections[ai].get("end", duration)))
                ai += 1
            else:
                s, e = cursor, min(duration, cursor + 8.0)
            sec_ranges.append((s, min(e, duration)))
            cursor = min(duration, e)
            continue
        sec_lines = alignment[line_ptr:line_ptr + n]
        line_ptr += n
        starts = [l["start"] for l in sec_lines if l and l.get("start") is not None]
        ends = [l["end"] for l in sec_lines if l and l.get("end") is not None]
        if starts and ends:
            s, e = min(starts), max(ends)
        else:
            s, e = cursor, min(duration, cursor + max(4.0, n * 6.0))
        sec_ranges.append((min(s, duration), min(max(e, s + 1.0), duration)))
        cursor = max(cursor, min(max(e, s + 1.0), duration))
    # build keyed ranges
    counts = {}
    keyed = []
    for sec, (s, e) in zip(lyrics.get("sections", []), sec_ranges):
        name = sec.get("name", "Section")
        counts[name] = counts.get(name, -1) + 1
        keyed.append((f"{name}#{counts[name]}", s, e, sec))
    return keyed


def assign_scene_times(db, project, storyboard, scenes, analysis, lyrics: dict, snap_beats: bool = True):
    """Give each Scene row a contiguous [start,end] range. Returns updated count."""
    alignment = PJ(analysis.alignment_json) if analysis else []
    if alignment is None:
        alignment = []
    duration = (analysis.duration if analysis else 0.0) or _max_scene_end(scenes) or 120.0
    keyed = section_ranges(lyrics, alignment, PJ(analysis.sections_json) if analysis else [], duration)

    # group scenes into consecutive runs by section name, then number the runs
    # per name — this matches the occurrence numbering used by section_ranges
    # (Chorus scenes next to each other = one chorus lyric section).
    runs = []
    for sc in sorted(scenes, key=lambda s: s.idx):
        name = sc.section or "Section"
        if runs and runs[-1][0] == name:
            runs[-1][1].append(sc)
        else:
            runs.append((name, [sc]))
    seen_counts = {}
    groups = []  # [(key, [scenes])]
    for name, scs in runs:
        c = seen_counts.get(name, 0)
        seen_counts[name] = c + 1
        groups.append((f"{name}#{c}", scs))

    bpm = analysis.bpm if analysis and analysis.bpm else 100.0
    beat = 60.0 / bpm
    off = analysis.beat_offset if analysis else 0.0

    def snap(t, prev_floor=0.0, next_ceil=None):
        if not snap_beats or bpm <= 0:
            return t
        cand = off + round((t - off) / beat) * beat
        if cand < prev_floor:
            cand = off + math.ceil((t - off) / beat) * beat
        if next_ceil is not None and cand > next_ceil:
            cand = next_ceil
        return max(prev_floor, min(cand, duration))

    # scene ranges: split each section's range among its scenes by lyrics weight.
    # Scenes whose lyrics_text matches a timed line (extraction/whisper) get the
    # EXACT vocal timing of that line — occurrence order preserved for repeats.
    timing_index = {}
    for a in (alignment or []):
        if a.get("text") and a.get("start") is not None and a.get("end") is not None:
            timing_index.setdefault(norm_text(a["text"]), []).append(
                (float(a["start"]), float(a["end"])))

    result_ranges = []
    # decide exact-timing groups up front (occurrence order preserved for repeats)
    group_times = []
    for key, scs in groups:
        keys_norm = [norm_text(sc.lyrics_text or "") for sc in scs]
        if scs and all(timing_index.get(k) for k in keys_norm):
            group_times.append([timing_index[k].pop(0) for k in keys_norm])
        else:
            group_times.append(None)
    flat_starts = [float(t[0]) for gt in group_times if gt for t in gt]
    fi = -1
    for (key, scs), gt in zip(groups, group_times):
        if gt:
            for i, (sc, (ls, le)) in enumerate(zip(scs, gt)):
                fi += 1
                s = float(ls)
                if fi + 1 < len(flat_starts):
                    e = max(flat_starts[fi + 1], s + 0.5)   # run until the next sung line
                else:
                    e = max(float(le), min(duration, float(le) + 0.6))
                e = min(max(e, s + 0.5), duration)
                result_ranges.append((sc, round(s, 2), round(e, 2)))
            continue
        m = next((k for k in keyed if k[0] == key), None)
        if m:
            a, b = m[1], m[2]
        else:
            # fallback: interleave evenly across remaining time
            last_end = result_ranges[-1][1] if result_ranges else 0.0
            a, b = last_end, min(duration, last_end + max(6.0, 8.0 * len(scs)))
        weights = [max(6.0, len(s.lyrics_text or s.description or "x")) for s in scs]
        total = sum(weights)
        t = a
        for i, sc in enumerate(scs):
            raw_end = b if i == len(scs) - 1 else a + (b - a) * (sum(weights[:i + 1]) / total)
            end = snap(raw_end, t + 0.5, b if i < len(scs) - 1 else None)
            result_ranges.append((sc, round(max(0.0, t), 2), round(min(duration, max(t + 0.5, end)), 2)))
            t = end
    # enforce continuity & full coverage (monotonic clamp — no stale values)
    prev_end = 0.0
    for j in range(len(result_ranges)):
        sc, s, e = result_ranges[j]
        if j == 0:
            s = 0.0                                # cover the instrumental intro
        s = max(s, prev_end)                       # never start before the previous end
        e = max(e, min(duration, s + 0.6))         # never shorter than 0.6s
        if j == len(result_ranges) - 1:
            e = max(e, min(duration, s + 0.6), duration - 0.1)  # last scene covers the song end
        else:
            e = min(e, duration)
        result_ranges[j] = (sc, round(s, 2), round(e, 2))
        prev_end = e
    for sc, s, e in result_ranges:
        sc.start, sc.end = float(s), float(e)
        db.add(sc)
    return len(result_ranges)


def _max_scene_end(scenes):
    return max((s.end for s in scenes), default=0.0)
