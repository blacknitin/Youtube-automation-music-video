"""JSON serializers for API responses."""
from .models import (AudioAnalysis, FeedbackItem, Job, Lyrics, Project, Render,
                     Scene, Song, Status, Storyboard, YouTubeMeta, YouTubeUpload, PJ)


def project_brief(p: Project) -> dict:
    return {"id": p.id, "title": p.title, "idea": p.idea, "language": p.language,
            "genre": p.genre, "mood": p.mood, "visual_style": p.visual_style,
            "status": p.status, "created_at": p.created_at.isoformat(),
            "updated_at": p.updated_at.isoformat()}


def song_json(s: Song | None) -> dict | None:
    if not s:
        return None
    return {"id": s.id, "title": s.title, "source": s.source, "duration": s.duration,
            "mime": s.mime, "file_url": f"/api/songs/{s.id}/file"}


def analysis_json(a: AudioAnalysis | None) -> dict | None:
    if not a:
        return None
    return {"id": a.id, "duration": a.duration, "bpm": a.bpm, "beat_offset": a.beat_offset,
            "sections": PJ(a.sections_json) or [], "peaks": PJ(a.peaks_json) or [],
            "energy": PJ(a.energy_json) or [], "aligned": bool(PJ(a.alignment_json))}


def lyrics_json(l: Lyrics | None) -> dict | None:
    if not l:
        return None
    return {"id": l.id, "status": l.status, "source": l.source,
            "language": l.language, **(PJ(l.content_json) or {})}


def scene_json(s: Scene) -> dict:
    return {"id": s.id, "idx": s.idx, "section": s.section, "lyrics_text": s.lyrics_text,
            "description": s.description, "prompt": s.prompt, "negative": s.negative,
            "shot": s.shot, "motion": s.motion, "start": s.start, "end": s.end,
            "seed": s.seed, "image_status": s.image_status, "image_error": s.image_error,
            "image_url": f"/api/scenes/{s.id}/image" if s.image_path else None}


def storyboard_json(sb: Storyboard | None, scenes) -> dict | None:
    if not sb:
        return None
    return {"id": sb.id, "version": sb.version, "status": sb.status,
            "style_bible": PJ(sb.style_json) or {},
            "scenes": [scene_json(s) for s in scenes]}


def render_json(r: Render | None) -> dict | None:
    if not r:
        return None
    return {"id": r.id, "status": r.status, "progress": r.progress, "message": r.message,
            "error": r.error, "settings": PJ(r.settings_json) or {},
            "created_at": r.created_at.isoformat(),
            "file_url": f"/api/renders/{r.id}/file" if r.path and r.status == "done" else None}


def meta_json(m: YouTubeMeta | None) -> dict | None:
    if not m:
        return None
    return {"id": m.id, "title": m.title, "description": m.description,
            "tags": PJ(m.tags_json) or [], "hashtags": PJ(m.hashtags_json) or [],
            "category": m.category, "privacy": m.privacy, "status": m.status,
            "thumbnail_url": f"/api/projects/{m.project_id}/thumbnail" if m.thumbnail_path else None}


def job_json(j: Job) -> dict:
    return {"id": j.id, "type": j.type, "project_id": j.project_id, "status": j.status,
            "progress": j.progress, "message": j.message, "error": j.error,
            "result": PJ(j.result_json) or {}, "created_at": j.created_at.isoformat()}


def feedback_json(f: FeedbackItem) -> dict:
    return {"id": f.id, "text": f.text, "status": f.status, "plan": PJ(f.plan_json) or {},
            "created_at": f.created_at.isoformat()}


def upload_json(u: YouTubeUpload | None) -> dict | None:
    if not u:
        return None
    return {"id": u.id, "video_id": u.video_id, "url": u.url, "status": u.status,
            "privacy": u.privacy, "error": u.error, "created_at": u.created_at.isoformat()}


def project_detail(db, p: Project) -> dict:
    from .models import Scene as SceneM
    from .services.versions import list_versions
    from .jobs import _latest_analysis, _latest_lyrics, _latest_storyboard
    from .models import Song as SongM, YouTubeUpload as UplM
    song = db.query(SongM).filter(SongM.project_id == p.id).order_by(SongM.id.desc()).first()
    sb = _latest_storyboard(db, p)
    scenes = db.query(SceneM).filter(SceneM.storyboard_id == sb.id).order_by(SceneM.idx).all() if sb else []
    render = db.query(Render).filter(Render.project_id == p.id)\
        .order_by(Render.id.desc()).first()
    meta = db.query(YouTubeMeta).filter(YouTubeMeta.project_id == p.id).first()
    upload = db.query(UplM).filter(UplM.project_id == p.id).order_by(UplM.id.desc()).first()
    jobs = db.query(Job).filter(Job.project_id == p.id).order_by(Job.id.desc()).limit(12).all()
    fbs = db.query(FeedbackItem).filter(FeedbackItem.project_id == p.id)\
        .order_by(FeedbackItem.id.desc()).limit(25).all()
    return {
        **project_brief(p),
        "lyrics": lyrics_json(_latest_lyrics(db, p)),
        "song": song_json(song),
        "analysis": analysis_json(_latest_analysis(db, p)),
        "storyboard": storyboard_json(sb, scenes),
        "latest_render": render_json(render),
        "metadata": meta_json(meta),
        "upload": upload_json(upload),
        "feedback": [feedback_json(f) for f in fbs],
        "versions": list_versions(db, p),
        "jobs": [job_json(j) for j in jobs],
    }
