"""FFmpeg render engine — parallel two-pass pipeline (fast).

Pass 1 (parallel): every scene is rendered as a short Ken Burns clip by
multiple ffmpeg processes running simultaneously (one CPU core each).
Pass 2 (single fast pass): clips are joined — xfade crossfade chain (or an
instant `-c copy` concat for hard cuts) — lyrics subtitles are burned in and
the song is muxed to the final MP4.

Why not MoviePy? It wraps the same ffmpeg but adds Python frame plumbing in
the hot loop; driving ffmpeg's filtergraphs directly is 5-20x faster and
keeps memory flat. The parallelism here scales with CPU cores.
"""
import os
import re
import shutil
import subprocess
import tempfile
import time

import concurrent.futures as cf

from ..config import SETTINGS

MOTIONS = ("slow_zoom_in", "slow_zoom_out", "pan_left", "pan_right", "static")


def _zoompan_expr(motion: str, frames: int):
    if motion == "slow_zoom_in":
        return (f"z='1+0.13*on/{max(1, frames)}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'")
    if motion == "slow_zoom_out":
        return (f"z='max(1.13-0.13*on/{max(1, frames)},1)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'")
    if motion == "pan_left":
        return f"z='1.12':x='(iw-iw/zoom)*(1-on/{max(1, frames)})':y='(ih-ih/zoom)/2'"
    if motion == "pan_right":
        return f"z='1.12':x='(iw-iw/zoom)*(on/{max(1, frames)})':y='(ih-ih/zoom)/2'"
    return "z='1.001':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"


def _run_progress(cmd, total_duration, progress_cb=None, phase="Rendering", cancel_check=None,
                  pct_from=0.0, pct_to=100.0):
    """Run ffmpeg, stream `-progress` output into progress_cb (pct range mapped)."""
    cmd = cmd + ["-progress", "pipe:1", "-nostats", "-y", "-nostdin"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, errors="replace")
    last = [0.0, 0.0]
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        m = re.search(r"out_time_us=(\d+)", line)
        if m and total_duration > 0:
            t = int(m.group(1)) / 1_000_000
            now = time.time()
            pct = pct_from + (pct_to - pct_from) * min(1.0, t / total_duration)
            if now - last[1] > 0.8:
                last[1] = now
                if progress_cb:
                    progress_cb(pct, phase)
        if cancel_check and cancel_check():
            proc.kill()
            return None, "cancelled"
    stderr = proc.stderr.read()
    rc = proc.wait()
    if rc != 0:
        return None, (stderr.splitlines()[-25:] and "\n".join(stderr.splitlines()[-25:]) or f"exit {rc}")[-2500:]
    if progress_cb:
        progress_cb(pct_to, phase)
    return True, None


def _render_segment(image, dur, out_path, width, height, fps, motion, clip_path=None):
    """Render one scene clip. Returns (ok, err, exact_duration).

    With clip_path (AI video from a VideoProvider): normalize the clip —
    target fps, size crop, yuv420p — looping it if the model produced fewer
    frames than the scene needs. `-frames:v` keeps the duration exact.
    Without one: Ken Burns (zoompan note below).

    Feed zoompan a SINGLE frame and let it generate the motion (`d=frames`
    capped by -frames:v). Piping a looped still into zoompan multiplies
    frames (inputs x d) — 30x slower with a bloated duration.
    Intermediates use `-preset ultrafast -crf 14` (re-encoded in the final
    pass) and ~1.5x zoom headroom for sub-pixel smoothness.
    """
    frames = max(2, int(round(dur * fps)))
    if clip_path:
        vf = (f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,"
              f"crop={width}:{height},format=yuv420p")
        cmd = [SETTINGS.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-nostdin",
               "-stream_loop", "-1", "-i", str(clip_path),
               "-vf", vf, "-frames:v", str(frames),
               "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "14",
               "-threads", "1", "-g", str(fps * 2), "-pix_fmt", "yuv420p",
               out_path]
    else:
        sw = min(int(width * 1.5) // 2 * 2, 1920)
        sh = max(2, round(sw * height / width / 2) * 2)
        vf = (f"scale={sw}:{sh}:force_original_aspect_ratio=increase,"
              f"crop={sw}:{sh},"
              f"zoompan={_zoompan_expr(motion, frames)}:d={frames}:s={width}x{height}:fps={fps},"
              f"format=yuv420p")
        cmd = [SETTINGS.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-nostdin",
               "-i", str(image),
               "-vf", vf, "-frames:v", str(frames),
               "-c:v", "libx264", "-preset", "ultrafast", "-crf", "14",
               "-threads", "1", "-g", str(fps * 2), "-pix_fmt", "yuv420p",
               out_path]
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if p.returncode != 0:
        return False, (p.stderr or f"segment failed: {out_path}")[-1200:], None
    return True, None, frames / fps


def _xfade_chain(pairs, td, out_path, width, height, fps, crf, preset,
                 ass_path=None, audio_path=None, fonts_dir=None, threads=0,
                 progress_cb=None, cancel_check=None, pct_from=0.0, pct_to=100.0):
    """Crossfade-join [(path, exact_duration)] pairs in ONE ffmpeg graph.

    Offsets are computed LOCALLY: xfade output duration = offset + duration of
    the newly added input, so offset_k = acc_end - td and the accumulated
    length stays exact. (Absolute-timeline offsets are wrong across files:
    joining a 4s input at absolute offset 30s truncates instead of appending.)
    Returns (ok, err, accumulated_duration).
    """
    n = len(pairs)
    inputs = []
    fc = []
    for i, (p, _d) in enumerate(pairs):
        inputs += ["-i", p]
        fc.append(f"[{i}:v]settb=AVTB,format=yuv420p[v{i}]")
    acc = pairs[0][1]
    if n == 1:
        last = "v0"
    else:
        prev = "v0"
        for k in range(1, n):
            out = f"x{k}"
            offset = max(0.0, acc - td)
            fc.append(f"[{prev}][v{k}]xfade=transition=fade:duration={td:.3f}:offset={offset:.3f}[{out}]")
            acc = offset + pairs[k][1]
            prev = out
        last = prev
    vmap = f"[{last}]"
    if ass_path:
        ass = str(ass_path).replace("\\", "/").replace(":", "\\:")
        fd = str(fonts_dir or SETTINGS.fonts_dir).replace(chr(92), "/")
        fc.append(f"[{last}]ass='{ass}':fontsdir='{fd}'[vf]")
        vmap = "[vf]"
    has_audio = bool(audio_path)
    if has_audio:
        inputs += ["-i", str(audio_path)]
    cmd = [SETTINGS.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-nostdin"] + inputs
    cmd += ["-filter_complex", ";".join(fc), "-map", vmap]
    if has_audio:
        cmd += ["-map", f"{n}:a", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-r", str(fps)]
    if threads:
        cmd += ["-threads", str(threads)]
    if has_audio:
        cmd += ["-shortest"]
    cmd += ["-movflags", "+faststart", str(out_path)]
    ok, err = _run_progress(cmd, max(1.0, acc), progress_cb, "Joining scenes + encoding…",
                            cancel_check, pct_from=pct_from, pct_to=pct_to)
    return ok, err, acc


def render_video(scene_list, audio_path, out_path, ass_path=None,
                 width=1280, height=720, fps=30, transition="crossfade",
                 transition_duration=0.6, crf=None, preset=None,
                 progress_cb=None, cancel_check=None) -> str:
    """scene_list: [{image, start, end, motion}] with contiguous times."""
    crf = crf or SETTINGS.render_crf
    preset = preset or SETTINGS.render_preset
    scene_list = [s for s in scene_list if s.get("image")]
    if not scene_list:
        raise ValueError("No scene images to render — generate scenes first.")
    total = scene_list[-1]["end"]
    td = transition_duration if transition == "crossfade" else 0.0
    fps = max(24, min(60, int(fps)))
    out_path = str(out_path)
    workdir = tempfile.mkdtemp(prefix="sf_render_", dir=os.path.dirname(out_path) or None)

    try:
        # ---------------- PASS 1: parallel scene clips ----------------
        segs = []
        for i, s in enumerate(scene_list):
            dur = (s["end"] - s["start"]) + (td if s is not scene_list[-1] else 0.0)
            if s is scene_list[-1]:
                dur += 0.6  # tail pad: frame rounding must never clip the song; -shortest trims to audio
            segs.append((i, max(0.3, dur), s.get("motion", "slow_zoom_in")))
        seg_dur = {}
        workers = max(1, min(len(segs), os.cpu_count() or 2, 8))
        done = [0]
        lock = __import__("threading").Lock()
        cancel_flag = [False]

        def work(item):
            if cancel_flag[0]:
                return False
            i, dur, motion = item
            ok, err, actual = _render_segment(scene_list[i]["image"], dur,
                                              os.path.join(workdir, f"seg_{i:03d}.mp4"),
                                              width, height, fps, motion,
                                              clip_path=scene_list[i].get("clip"))
            if actual:
                seg_dur[i] = actual
            with lock:
                done[0] += 1
                if progress_cb:
                    progress_cb(2 + 56 * done[0] / len(segs),
                                f"Rendering scenes {done[0]}/{len(segs)} (parallel x{workers})…")
            if cancel_check and cancel_check():
                cancel_flag[0] = True
            return ok

        with cf.ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(work, segs))
        if cancel_flag[0] or not all(results):
            bad = [i for i, ok in enumerate(results) if not ok]
            raise RuntimeError(f"Scene clip rendering failed for scene(s) {bad[:5]}")

        if progress_cb:
            progress_cb(60, "Joining scenes, burning lyrics, muxing audio…")

        # ---------------- PASS 2: hierarchical crossfade join ----------------
        # Chunks keep each ffmpeg graph at <= CHUNK live decoders (memory-safe);
        # chunk graphs themselves render in parallel.
        seg_paths = [os.path.join(workdir, f"seg_{i:03d}.mp4") for i in range(len(segs))]

        if transition != "crossfade" or len(seg_paths) == 1:
            # hard cuts: instant concat (no re-encode), then one light pass for subs/audio
            concat_list = os.path.join(workdir, "list.txt")
            with open(concat_list, "w") as f:
                for sp in seg_paths:
                    f.write(f"file '{sp}'\n")
            joined = os.path.join(workdir, "joined.mp4")
            c1 = [SETTINGS.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-nostdin",
                  "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", joined]
            subprocess.run(c1, capture_output=True, text=True)
            vf_sub = (f"ass='{str(ass_path).replace(chr(92), '/').replace(':', chr(92) + ':')}'"
                      f":fontsdir='{str(SETTINGS.fonts_dir).replace(chr(92), '/')}'") if ass_path else None
            cmd = [SETTINGS.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-nostdin",
                   "-i", joined, "-i", str(audio_path)]
            if vf_sub:
                cmd += ["-vf", vf_sub]
            cmd += ["-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                    "-pix_fmt", "yuv420p", "-r", str(fps),
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                    out_path]
            ok, err = _run_progress(cmd, total, progress_cb, "Encoding final video…",
                                    cancel_check, pct_from=62, pct_to=99)
            if not ok:
                raise RuntimeError(f"FFmpeg render failed:\n{err}")
            if progress_cb:
                progress_cb(100, "Render complete")
            return out_path

        # crossfade path — hierarchical (pairs carry EXACT segment durations)
        CHUNK = 4
        current = [(sp, seg_dur[i]) for i, sp in enumerate(seg_paths)]
        level, span = 0, 38.0  # progress span for pass 2 = 60..98

        while len(current) > CHUNK:
            nxt = []
            groups = [current[i:i + CHUNK] for i in range(0, len(current), CHUNK)]
            for gi, g in enumerate(groups):
                out = os.path.join(workdir, f"chunk_{level}_{gi:02d}.mp4")
                ok, err, acc = _xfade_chain(g, td, out, width, height, fps, 14, "ultrafast",
                                            threads=1,
                                            progress_cb=progress_cb, cancel_check=cancel_check,
                                            pct_from=60 + span * 0.5 * (gi / len(groups)),
                                            pct_to=60 + span * 0.5 * ((gi + 1) / len(groups)))
                if not ok:
                    raise RuntimeError(f"FFmpeg join failed:\n{err}")
                nxt.append((out, acc))
            current = nxt
            level += 1

        final_ok, final_err, _acc = _xfade_chain(
            current, td, out_path, width, height, fps, crf, preset,
            ass_path=ass_path, audio_path=audio_path, threads=2,
            progress_cb=progress_cb, cancel_check=cancel_check, pct_from=93, pct_to=99)
        if not final_ok:
            raise RuntimeError(f"FFmpeg render failed:\n{final_err}")

        if progress_cb:
            progress_cb(100, "Render complete")
        return out_path
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
