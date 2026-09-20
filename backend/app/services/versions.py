"""Project version snapshots — lyrics + storyboard + scenes in one immutable JSON."""
import json

from ..models import Lyrics, Scene, Storyboard, ProjectVersion, PJ


def snapshot(db, project, label: str = "") -> ProjectVersion:
    lyrics = db.query(Lyrics).filter(Lyrics.project_id == project.id).order_by(Lyrics.id.desc()).first()
    sb = db.query(Storyboard).filter(Storyboard.project_id == project.id,
                                     Storyboard.status != "archived").order_by(Storyboard.id.desc()).first()
    scenes = []
    if sb:
        rows = db.query(Scene).filter(Scene.storyboard_id == sb.id).order_by(Scene.idx).all()
        scenes = [{
            "idx": s.idx, "section": s.section, "lyrics_text": s.lyrics_text,
            "description": s.description, "prompt": s.prompt, "negative": s.negative,
            "shot": s.shot, "motion": s.motion, "start": s.start, "end": s.end,
            "seed": s.seed, "image_status": s.image_status} for s in rows]
    last = db.query(ProjectVersion).filter(ProjectVersion.project_id == project.id)\
        .order_by(ProjectVersion.number.desc()).first()
    number = (last.number + 1) if last else 1
    snap = {
        "lyrics": PJ(lyrics.content_json) if lyrics else None,
        "storyboard": {"version": sb.version if sb else 0,
                       "style_bible": PJ(sb.style_json) if sb else None},
        "scenes": scenes,
        "label": label,
    }
    v = ProjectVersion(project_id=project.id, number=number, label=label[:290],
                       snapshot_json=json.dumps(snap, ensure_ascii=False))
    db.add(v)
    db.flush()
    return v


def list_versions(db, project) -> list:
    rows = db.query(ProjectVersion).filter(ProjectVersion.project_id == project.id)\
        .order_by(ProjectVersion.number.desc()).all()
    return [{"id": r.id, "number": r.number, "label": r.label, "created_at": r.created_at.isoformat(),
             "scene_count": len(PJ(r.snapshot_json).get("scenes", []) if PJ(r.snapshot_json) else [])}
            for r in rows]
