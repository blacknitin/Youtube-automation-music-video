"""Simple DB-backed job queue with a single background worker thread.

Long-running generation (lyrics, analysis, storyboard, scene images, video
render, uploads) runs here so API calls stay instant and the UI can poll
progress. Swap for Celery/RQ/ARQ later — the interface is just job rows.
"""
import json
import threading
import time
import traceback

from .config import SETTINGS
from .db import SessionLocal
from .models import (AudioAnalysis, FeedbackItem, Job, Lyrics, Project, Render,
                     Scene, Song, Status, Storyboard, YouTubeMeta, YouTubeUpload, PJ)

_worker = None
_stop = threading.Event()

# ---------------------------------------------------------------------------
# Handlers — each receives (db, payload, progress). Raise to fail the job.
# ---------------------------------------------------------------------------

def h_lyrics_generate(db, payload, progress):
    from .providers.registry import get_llm
    from .providers.base import LyricRequest
    project = db.query(Project).get(payload["project_id"])
    progress(10, "Writing lyrics with AI…")
    llm = get_llm()
    req = LyricRequest(idea=project.idea, language=project.language, genre=project.genre,
                       mood=project.mood, title_hint=project.title)
    data = llm.generate_lyrics(req)
    progress(80, "Structuring lyrics…")
    lyr = Lyrics(project_id=project.id,
                 content_json=json.dumps(data, ensure_ascii=False),
                 language=project.language, status="draft", source="ai")
    db.add(lyr)
    project.status = Status.LYRICS_DRAFT
    db.add(project)
    db.commit()  # commit BEFORE next progress() — never write+progress uncommitted
    progress(100, "Lyrics ready for your review")
    return {"lyrics_id": lyr.id}


def h_song_demo(db, payload, progress):
    from .storage import song_path
    from .services.audio import analyze, synthesize_demo_song
    project = db.query(Project).get(payload["project_id"])
    progress(10, "Synthesizing a demo track locally…")
    dest = song_path(project.id, "demo_track.wav")
    synthesize_demo_song(dest)
    _attach_song(db, project, dest, title="Demo Track (local synth)", source="demo", progress=progress)


def h_song_upload(db, payload, progress):
    """payload: {project_id, path, original_name, mime, title, source}"""
    project = db.query(Project).get(payload["project_id"])
    _attach_song(db, project, payload["path"], payload.get("title") or payload.get("original_name", "Imported song"),
                 payload.get("source", "suno_import"), progress=progress)


def _attach_song(db, project, path, title, source, progress):
    from .models import Song as SongM
    from .services.audio import analyze
    progress(40, "Analyzing audio (BPM, energy, sections)…")
    info = analyze(path)
    db.query(SongM).filter(SongM.project_id == project.id).delete()
    song = SongM(project_id=project.id, title=title, source=source, original_name=title,
                 path=str(path), mime="audio/wav" if str(path).endswith(".wav") else "audio/mpeg",
                 duration=info["duration"])
    db.add(song)
    db.commit()  # song rows deleted; now safe to delete orphan analyses
    db.query(AudioAnalysis).filter(~AudioAnalysis.song_id.in_(db.query(SongM.id))).delete(
        synchronize_session=False)
    an = AudioAnalysis(song_id=song.id, duration=info["duration"], bpm=info["bpm"],
                       beat_offset=info["beat_offset"],
                       sections_json=json.dumps(info["sections"]),
                       peaks_json=json.dumps(info["peaks"]),
                       energy_json=json.dumps(info["energy"]))
    db.add(an)
    if project.status in (Status.CREATED, Status.LYRICS_APPROVED, Status.SONG_ADDED, Status.ANALYZED):
        project.status = Status.ANALYZED
    db.add(project)
    db.commit()
    progress(100, f"Song ready — {info['duration']:.0f}s @ {info['bpm']:.0f} BPM")
    return {"song_id": song.id, "analysis_id": an.id, **{k: info[k] for k in ("duration", "bpm")}}


def h_realign(db, payload, progress):
    """Re-run line alignment + scene timing (e.g. after lyrics edits)."""
    from .services.arrange import align_lines, assign_scene_times
    project = db.query(Project).get(payload["project_id"])
    analysis = _latest_analysis(db, project)
    lyrics = _latest_lyrics(db, project)
    sb = _latest_storyboard(db, project)
    if not (analysis and lyrics and sb):
        return {"skipped": True}
    progress(30, "Aligning lyrics…")
    align_lines(db, project, analysis, PJ(lyrics.content_json) or {})
    db.commit()
    scenes = db.query(Scene).filter(Scene.storyboard_id == sb.id).order_by(Scene.idx).all()
    progress(70, "Re-timing scenes…")
    assign_scene_times(db, project, sb, scenes, analysis, PJ(lyrics.content_json) or {})
    db.commit()
    progress(100, "Timing updated")


def h_storyboard_generate(db, payload, progress):
    from .services.storyboard import create_storyboard
    project = db.query(Project).get(payload["project_id"])
    analysis = _latest_analysis(db, project)
    lyrics = _latest_lyrics(db, project)
    if not lyrics or lyrics.status != "approved":
        raise RuntimeError("Approve the lyrics before generating the storyboard.")
    sb = create_storyboard(db, project, analysis, PJ(lyrics.content_json) or {}, progress)
    db.commit()  # persist & release lock
    project.status = Status.STORYBOARD_DRAFT
    db.add(project)
    db.commit()
    return {"storyboard_id": sb.id}


def h_scenes_generate(db, payload, progress):
    """Generate images for pending scenes (all, or just payload['scene_ids'])."""
    from .services.storyboard import build_image_prompt
    from .providers.registry import get_image_provider
    from .storage import scene_image_path
    project = db.query(Project).get(payload["project_id"])
    q = db.query(Scene).filter(Scene.project_id == project.id)
    ids = payload.get("scene_ids")
    if ids:
        q = q.filter(Scene.id.in_(ids))
    scenes = q.order_by(Scene.idx).all()
    sb = _latest_storyboard(db, project)
    style = PJ(sb.style_json) if sb else {}
    img = get_image_provider()
    done = failed = 0
    for n, sc in enumerate(scenes):
        if sc.image_status == "done" and not ids:
            continue
        prompt, neg = build_image_prompt(style, sc)
        out = scene_image_path(project.id, sc.idx)
        try:
            img.generate(prompt, neg, out, seed=sc.seed or 1,
                         width=SETTINGS.image_width, height=SETTINGS.image_height)
            sc.image_path = str(out)
            sc.image_status = "done"
            sc.image_error = ""
            done += 1
        except Exception as e:
            sc.image_status = "failed"
            sc.image_error = str(e)[:900]
            failed += 1
        db.add(sc)
        db.commit()  # per-scene commit: crash-safe + never write+progress uncommitted
        progress(5 + 90 * (n + 1) / max(1, len(scenes)),
                 f"Scene {sc.idx + 1}/{len(scenes)} — {'ok' if sc.image_status == 'done' else 'failed'}")
    all_done = db.query(Scene).filter(Scene.project_id == project.id,
                                      Scene.image_status != "done").count() == 0
    if all_done:
        project.status = Status.SCENES_READY if project.status in (
            Status.STORYBOARD_DRAFT, Status.STORYBOARD_APPROVED, Status.SCENES_READY) else project.status
        db.add(project)
    db.commit()
    return {"generated": done, "failed": failed}


def h_render(db, payload, progress):
    from .services.render import render_video
    from .services.subtitles import write_ass
    from .storage import render_path
    from .models import Render as RenderM
    project = db.query(Project).get(payload["project_id"])
    render = db.query(RenderM).get(payload["render_id"])
    render.status = "running"
    db.add(render)
    db.commit()  # commit immediately — progress() and ffmpeg must not hit our lock

    settings = PJ(render.settings_json) or {}
    width, height = map(int, settings.get("resolution", "1280x720").split("x"))
    fps = int(settings.get("fps", 30))
    transition = settings.get("transition", "crossfade")
    td = float(settings.get("transition_duration", 0.6))
    burn = bool(settings.get("burn_subtitles", True))
    karaoke = bool(settings.get("karaoke", True))

    scenes = [s for s in db.query(Scene).filter(Scene.project_id == project.id)
              .order_by(Scene.idx).all() if s.image_status == "done"]
    if not scenes:
        raise RuntimeError("No scene images available. Generate scenes first.")
    missing = db.query(Scene).filter(Scene.project_id == project.id,
                                     Scene.image_status == "failed").count()
    note = f"note: {missing} scene(s) failed image generation and were skipped" if missing else ""

    song = db.query(Song).filter(Song.project_id == project.id).order_by(Song.id.desc()).first()
    if not song:
        raise RuntimeError("No song attached to this project.")

    analysis = _latest_analysis(db, project)
    alignment = PJ(analysis.alignment_json) if analysis else None
    progress(2, "Preparing subtitles…")
    ass = None
    if burn and alignment:
        ass = write_ass(render_path(project.id, f"subs_v{render.id}").with_suffix(".ass"),
                        alignment, analysis.duration or scenes[-1].end,
                        width=width, height=height, karaoke=karaoke)

    out = render_path(project.id, f"v{render.id}")
    progress(5, "Rendering video…")

    def cb(pct, msg=None):
        progress(max(5.0, min(99.0, pct * 0.98 + 1)), msg or "Rendering video…")

    scene_dicts = [{"image": s.image_path, "start": s.start, "end": s.end,
                    "motion": s.motion, "lyrics_text": s.lyrics_text,
                    "prompt": s.prompt or s.description, "seed": s.seed}
                   for s in scenes]

    # Real AI animation (optional): free open-source image-to-video models via
    # ComfyUI — Stable Video Diffusion, AnimateDiff, Wan, LTX-Video (see
    # providers/video_comfyui.py). Falls back per-scene to FFmpeg motion.
    from .providers.registry import get_video_provider
    from .config import SETTINGS as _S
    strict_openmontage = (_S.video_provider or "auto").lower() in ("openmontage", "montage")
    vp = get_video_provider()
    if strict_openmontage and vp.name != "openmontage":
        raise RuntimeError("VIDEO_PROVIDER=openmontage but OpenMontage is not configured — "
                           "set OPENMONTAGE_REPO to a clone of calesthio/OpenMontage "
                           "(no other video generator is used in this mode).")
    if vp.name != "ffmpeg-motion":
        import os as _os
        anim_dir = str(render_path(project.id, f"v{render.id}").parent / f"anim_v{render.id}")
        _os.makedirs(anim_dir, exist_ok=True)
        total = len(scene_dicts)
        for i, sd in enumerate(scene_dicts):
            if progress:
                progress(5 + 30 * i / max(1, total),
                         f"Animating scene {i + 1}/{total} with {vp.name}…")
            clip_out = _os.path.join(anim_dir, f"clip_{i:03d}.mp4")
            try:
                # the AI-written scene prompt IS the generation prompt
                hint = sd.get("prompt") or ""
                vp.animate(sd["image"], sd["end"] - sd["start"], fps,
                           hint, clip_out, seed=sd.get("seed", 0),
                           width=width, height=height)
                sd["clip"] = clip_out
            except Exception as e:
                if strict_openmontage:
                    raise RuntimeError(
                        f"OpenMontage failed on scene {i + 1} (strict mode — no other "
                        f"video generator allowed): {str(e)[:200]}")
                if progress:
                    progress(5 + 30 * (i + 1) / max(1, total),
                             f"Scene {i + 1}: AI animation unavailable — using motion "
                             f"fallback ({str(e)[:80]})")

    render_video(
        scene_dicts,
        song.path, out, ass_path=ass, width=width, height=height, fps=fps,
        transition=transition, transition_duration=td, progress_cb=cb)

    render = db.query(RenderM).get(render.id)  # fresh read after the long render
    render.path = str(out)
    render.status = "done"
    render.progress = 100.0
    render.message = note or "Render complete"
    render.finished_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    db.add(render)
    project.status = Status.RENDER_READY
    db.add(project)
    db.commit()
    return {"render_id": render.id, "path": render.path}


def h_feedback_interpret(db, payload, progress):
    from .services.revision import interpret
    project = db.query(Project).get(payload["project_id"])
    fb = db.query(FeedbackItem).get(payload["feedback_id"])
    scenes = db.query(Scene).filter(Scene.project_id == project.id).order_by(Scene.idx).all()
    progress(40, "Understanding your feedback…")
    plan = interpret(db, project, fb, scenes)
    db.commit()
    progress(100, plan.get("summary", "Plan ready"))
    return {"plan": plan}


def h_revision_apply(db, payload, progress):
    """Re-generate ONLY the scenes affected by a feedback plan, then re-time them."""
    from .services.arrange import assign_scene_times
    from .services.revision import apply_plan
    project = db.query(Project).get(payload["project_id"])
    fb = db.query(FeedbackItem).get(payload["feedback_id"])
    progress(15, "Applying AI revision plan…")
    res = apply_plan(db, project, fb, regenerate=True)
    db.commit()
    if not res["scene_ids"]:
        progress(100, "Nothing needed changing — video already matches your feedback")
        return res
    analysis = _latest_analysis(db, project)
    lyrics = _latest_lyrics(db, project)
    sb = _latest_storyboard(db, project)
    if analysis and lyrics and sb:
        scenes = db.query(Scene).filter(Scene.storyboard_id == sb.id).order_by(Scene.idx).all()
        assign_scene_times(db, project, sb, scenes, analysis, PJ(lyrics.content_json) or {})
        db.commit()
    progress(30, f"Regenerating {len(res['scene_ids'])} affected scene(s) only…")
    h_scenes_generate(db, {"project_id": project.id, "scene_ids": res["scene_ids"]}, progress)
    return res


def h_metadata_generate(db, payload, progress):
    from .services.meta import generate as gen_meta
    project = db.query(Project).get(payload["project_id"])
    gen_meta(db, project, _latest_lyrics(db, project), progress)


def h_thumbnail_regenerate(db, payload, progress):
    from .services.meta import generate_thumbnail, get_or_create
    project = db.query(Project).get(payload["project_id"])
    row = get_or_create(db, project)
    generate_thumbnail(db, project, row, payload.get("prompt", ""))
    progress(100, "Thumbnail updated")


def h_youtube_upload(db, payload, progress):
    """FINAL GATE — asserts approval state before uploading."""
    from .services.yt import upload_video
    project = db.query(Project).get(payload["project_id"])
    meta = db.query(YouTubeMeta).filter(YouTubeMeta.project_id == project.id).first()
    upload = db.query(YouTubeUpload).get(payload["upload_id"])
    # Hard safety checks (defense in depth — the API already gated this)
    if not payload.get("confirm") or payload.get("confirm") is not True:
        raise RuntimeError("Upload refused: missing explicit confirmation.")
    if project.status not in (Status.FINAL_APPROVED, Status.METADATA_APPROVED) or \
            not meta or meta.status != "approved":
        raise RuntimeError("Upload refused: video/metadata not approved by the user.")
    SETTINGS.auto_upload_enabled = False  # uploads are never automatic
    render = db.query(Render).filter(
        Render.project_id == project.id, Render.status == "done")\
        .order_by(Render.id.desc()).first()
    if not render or not render.path:
        raise RuntimeError("No rendered video found.")
    upload.status = "running"
    db.add(upload)
    db.commit()  # release lock during the long network upload

    def cb(p):
        progress(min(99.0, p), "Uploading to YouTube…")

    result = upload_video(project, meta, render.path, meta.privacy or "private", cb)
    upload.video_id = result["video_id"]
    upload.url = result["url"]
    upload.status = "done"
    db.add(upload)
    project.status = Status.UPLOADED
    db.add(project)
    db.commit()
    progress(100, f"Uploaded: {result['url']}")
    return result


def h_lyrics_extract(db, payload, progress):
    """Listen to the project's song and extract lyrics (+ exact vocal timings)."""
    from .services.extract import extract_lyrics_from_song
    project = db.query(Project).get(payload["project_id"])
    res = extract_lyrics_from_song(db, project, progress)
    progress(100, f"Extracted {res['lines']} lyric lines — review & approve them")
    return res


HANDLERS = {
    "lyrics.generate": h_lyrics_generate,
    "lyrics.extract": h_lyrics_extract,
    "song.demo": h_song_demo,
    "song.upload": h_song_upload,
    "audio.realign": h_realign,
    "storyboard.generate": h_storyboard_generate,
    "scenes.generate": h_scenes_generate,
    "video.render": h_render,
    "feedback.interpret": h_feedback_interpret,
    "revision.apply": h_revision_apply,
    "metadata.generate": h_metadata_generate,
    "thumbnail.regenerate": h_thumbnail_regenerate,
    "youtube.upload": h_youtube_upload,
}

# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

def enqueue(db, jtype: str, project_id=None, payload=None) -> Job:
    job = Job(type=jtype, project_id=project_id,
              payload_json=json.dumps(payload or {}))
    db.add(job)
    db.commit()
    return job

def _progress_saver(job_id):
    import datetime as _dt
    last = {"t": 0.0}

    def cb(pct, message=None):
        now = time.time()
        if now - last["t"] < 0.5 and pct < 100:
            return
        last["t"] = now
        for attempt in range(3):  # brief waits only — handlers commit before progress()
            try:
                with SessionLocal() as db:
                    job = db.query(Job).get(job_id)
                    if job and job.status == "running":
                        job.progress = float(pct)
                        if message:
                            job.message = str(message)[:480]
                        db.add(job)
                        db.commit()
                return
            except Exception:
                time.sleep(0.25 * (attempt + 1))
    return cb

def _commit_retry(db, attempts=6):
    for a in range(attempts):
        try:
            db.commit()
            return
        except Exception:
            db.rollback()
            time.sleep(0.3 * (a + 1))
    db.commit()

def _run_job(job_id):
    with SessionLocal() as db:
        job = db.query(Job).get(job_id)
        if not job or job.status != "queued":
            return
        job.status = "running"
        job.started_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        db.add(job)
        _commit_retry(db)
        payload = PJ(job.payload_json) or {}
        handler = HANDLERS.get(job.type)
        try:
            if not handler:
                raise RuntimeError(f"Unknown job type: {job.type}")
            result = handler(db, payload, _progress_saver(job_id))
            db.rollback()  # drop any stale read snapshot before final write
            job = db.query(Job).get(job_id)
            job.status = "done"
            job.progress = 100.0
            job.result_json = json.dumps(result or {}, ensure_ascii=False, default=str)
            job.finished_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            db.add(job)
            _commit_retry(db)
        except Exception as e:
            db.rollback()
            for attempt in range(6):
                try:
                    with SessionLocal() as db2:
                        job = db2.query(Job).get(job_id)
                        job.status = "failed"
                        job.error = "".join(traceback.format_exception(e))[-3500:]
                        job.finished_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                        db2.add(job)
                        db2.commit()
                    break
                except Exception:
                    time.sleep(0.3 * (attempt + 1))

def _worker_loop():
    while not _stop.is_set():
        try:
            with SessionLocal() as db:
                job = db.query(Job).filter(Job.status == "queued")\
                    .order_by(Job.id.asc()).first()
                jid = job.id if job else None
            if jid:
                _run_job(jid)
            else:
                _stop.wait(0.7)
        except Exception:
            traceback.print_exc()
            _stop.wait(2.0)

def start_worker():
    global _worker
    _recover_stale_jobs()
    if _worker and _worker.is_alive():
        return
    _stop.clear()
    _worker = threading.Thread(target=_worker_loop, name="songforge-worker", daemon=True)
    _worker.start()

def _recover_stale_jobs():
    """On startup: jobs left 'running' by a previous session died with it."""
    import datetime as _dt
    try:
        with SessionLocal() as db:
            stuck = db.query(Job).filter(Job.status == "running").all()
            for job in stuck:
                job.status = "failed"
                job.error = "Interrupted by an app restart — start it again."
                job.finished_at = _dt.datetime.now(_dt.timezone.utc)
                db.add(job)
            from .models import Render
            for r in db.query(Render).filter(Render.status.in_(["running", "queued"])).all():
                r.status = "failed"
                r.error = "Interrupted by an app restart — render again."
                db.add(r)
            db.commit()
    except Exception:
        pass

def stop_worker():
    _stop.set()

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _latest_lyrics(db, project):
    return db.query(Lyrics).filter(Lyrics.project_id == project.id)\
        .order_by(Lyrics.id.desc()).first()

def _latest_analysis(db, project):
    song = db.query(Song).filter(Song.project_id == project.id).order_by(Song.id.desc()).first()
    if not song:
        return None
    return db.query(AudioAnalysis).filter(AudioAnalysis.song_id == song.id)\
        .order_by(AudioAnalysis.id.desc()).first()

def _latest_storyboard(db, project):
    return db.query(Storyboard).filter(Storyboard.project_id == project.id,
                                       Storyboard.status != "archived")\
        .order_by(Storyboard.id.desc()).first()
