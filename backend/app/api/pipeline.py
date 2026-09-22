"""The creation pipeline API: lyrics → song → analysis → storyboard → scenes →
render → feedback/revisions → versions. Every long step is a polled job."""
import json
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import SETTINGS
from ..db import get_db_dep
from ..jobs import enqueue, _latest_analysis, _latest_lyrics, _latest_storyboard
from ..models import (FeedbackItem, Job, Lyrics, Project, Render, Scene, Song,
                      Status, Storyboard, PJ)
from ..serializers import job_json, render_json
from ..storage import song_path

router = APIRouter(prefix="/api", tags=["pipeline"])

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus", ".wma"}


def _project(db, pid) -> Project:
    p = db.query(Project).get(pid)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def _lyrics(db, pid) -> Lyrics:
    l = _latest_lyrics(db, _project(db, pid))
    if not l:
        raise HTTPException(409, "No lyrics yet — generate them first")
    return l


# ---------------------------------------------------------------- lyrics ----
@router.post("/projects/{pid}/lyrics/generate")
def generate_lyrics(pid: int, db: Session = Depends(get_db_dep)):
    p = _project(db, pid)
    job = enqueue(db, "lyrics.generate", pid, {"project_id": pid})
    return job_json(job)


class LyricsBody(BaseModel):
    title: str | None = None
    sections: list


@router.put("/projects/{pid}/lyrics")
def save_lyrics(pid: int, body: LyricsBody, db: Session = Depends(get_db_dep)):
    p = _project(db, pid)
    old = _latest_lyrics(db, p)
    old_title = (PJ(old.content_json) or {}).get("title", "") if old else ""
    content = {"title": body.title or old_title, "language": p.language, "sections": body.sections}
    lyr = Lyrics(project_id=pid, content_json=json.dumps(content, ensure_ascii=False),
                 language=p.language, status="draft", source="manual")
    db.add(lyr)
    if p.status in (Status.CREATED, Status.LYRICS_DRAFT, Status.LYRICS_APPROVED):
        p.status = Status.LYRICS_DRAFT
    db.commit()
    return {"ok": True, "edited": True}


@router.post("/projects/{pid}/lyrics/extract")
def extract_lyrics(pid: int, db: Session = Depends(get_db_dep)):
    """Transcribe the song's vocals into editable lyrics with real timings."""
    _project(db, pid)
    from ..models import Song
    song = db.query(Song).filter(Song.project_id == pid).order_by(Song.id.desc()).first()
    if not song:
        raise HTTPException(409, "Add the song audio first — extraction listens to it")
    job = enqueue(db, "lyrics.extract", pid, {"project_id": pid})
    return job_json(job)


@router.post("/projects/{pid}/lyrics/approve")
def approve_lyrics(pid: int, db: Session = Depends(get_db_dep)):
    p = _project(db, pid)
    l = _lyrics(db, pid)
    l.status = "approved"
    p.status = Status.LYRICS_APPROVED
    db.commit()
    from ..jobs import enqueue
    job = enqueue(db, "audio.realign", pid, {"project_id": pid})
    return {"ok": True, "status": p.status, "job": job_json(job)}


# ----------------------------------------------------------------- songs ----
@router.post("/projects/{pid}/song/import")
async def import_song(pid: int, file: UploadFile = File(...), title: str = Form(""),
                      source: str = Form("suno_import"), db: Session = Depends(get_db_dep)):
    p = _project(db, pid)
    name = file.filename or "song.mp3"
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ".mp3"
    if ext not in AUDIO_EXT:
        raise HTTPException(400, f"Unsupported audio type {ext}. Use one of: {', '.join(sorted(AUDIO_EXT))}")
    dest = song_path(pid, name)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    payload = {"project_id": pid, "path": str(dest), "original_name": name,
               "title": title or name.rsplit(".", 1)[0], "source": source}
    job = enqueue(db, "song.upload", pid, payload)
    return job_json(job)


@router.post("/projects/{pid}/song/demo")
def demo_song(pid: int, db: Session = Depends(get_db_dep)):
    _project(db, pid)
    job = enqueue(db, "song.demo", pid, {"project_id": pid})
    return job_json(job)


@router.post("/projects/{pid}/song/generate")
def generate_song(pid: int, body: dict | None = None, db: Session = Depends(get_db_dep)):
    """AI song generation (MusicGen — original royalty-free instrumental)."""
    _project(db, pid)
    payload = {"project_id": pid}
    if body and body.get("seconds"):
        payload["seconds"] = float(body["seconds"])
    job = enqueue(db, "song.generate", pid, payload)
    return job_json(job)


@router.get("/songs/{sid}/file")
def song_file(sid: int, db: Session = Depends(get_db_dep)):
    from ..media import media_file_response
    s = db.query(Song).get(sid)
    if not s:
        raise HTTPException(404, "Song not found")
    return media_file_response(s.path, s.mime or "audio/mpeg")


# ----------------------------------------------------------- storyboard ----
@router.post("/projects/{pid}/storyboard/generate")
def generate_storyboard(pid: int, db: Session = Depends(get_db_dep)):
    p = _project(db, pid)
    l = _latest_lyrics(db, p)
    if not l or l.status != "approved":
        raise HTTPException(409, "Approve the lyrics first")
    if not _latest_analysis(db, p):
        raise HTTPException(409, "Import a song first — analysis timings are needed")
    job = enqueue(db, "storyboard.generate", pid, {"project_id": pid})
    return job_json(job)


class StoryboardBody(BaseModel):
    style_bible: dict | None = None


@router.put("/projects/{pid}/storyboard")
def update_storyboard(pid: int, body: StoryboardBody, db: Session = Depends(get_db_dep)):
    p = _project(db, pid)
    sb = _latest_storyboard(db, p)
    if not sb:
        raise HTTPException(409, "No storyboard yet")
    if body.style_bible is not None:
        sb.style_json = json.dumps(body.style_bible, ensure_ascii=False)
        db.add(sb)
    db.commit()
    return {"ok": True}


@router.post("/projects/{pid}/storyboard/approve")
def approve_storyboard(pid: int, db: Session = Depends(get_db_dep)):
    from ..services.versions import snapshot
    p = _project(db, pid)
    sb = _latest_storyboard(db, p)
    if not sb:
        raise HTTPException(409, "No storyboard yet")
    sb.status = "approved"
    p.status = Status.STORYBOARD_APPROVED
    v = snapshot(db, p, label="Storyboard approved")
    db.commit()
    return {"ok": True, "status": p.status, "version": v.number}


# --------------------------------------------------------------- scenes ----
@router.post("/projects/{pid}/scenes/generate")
def generate_scenes(pid: int, db: Session = Depends(get_db_dep)):
    _project(db, pid)
    job = enqueue(db, "scenes.generate", pid, {"project_id": pid})
    return job_json(job)


class SceneBody(BaseModel):
    description: str | None = None
    prompt: str | None = None
    negative: str | None = None
    shot: str | None = None
    motion: str | None = None
    start: float | None = None
    end: float | None = None
    lyrics_text: str | None = None


@router.put("/scenes/{sid}")
def update_scene(sid: int, body: SceneBody, db: Session = Depends(get_db_dep)):
    sc = db.query(Scene).get(sid)
    if not sc:
        raise HTTPException(404, "Scene not found")
    for k in ("description", "prompt", "negative", "shot", "motion", "lyrics_text"):
        v = getattr(body, k)
        if v is not None:
            setattr(sc, k, v)
    if body.start is not None:
        sc.start = max(0.0, body.start)
    if body.end is not None:
        sc.end = max(sc.start + 0.3, body.end)
    sc.image_status = "pending" if (body.prompt or body.description) and sc.image_status == "failed" else sc.image_status
    db.commit()
    return {"ok": True}


@router.post("/scenes/{sid}/regenerate")
def regenerate_scene(sid: int, db: Session = Depends(get_db_dep)):
    sc = db.query(Scene).get(sid)
    if not sc:
        raise HTTPException(404, "Scene not found")
    job = enqueue(db, "scenes.generate", sc.project_id, {"project_id": sc.project_id, "scene_ids": [sid]})
    return job_json(job)


@router.get("/scenes/{sid}/image")
def scene_image(sid: int, db: Session = Depends(get_db_dep)):
    from ..media import media_file_response
    sc = db.query(Scene).get(sid)
    if not sc or not sc.image_path:
        raise HTTPException(404, "Scene image not generated yet")
    import os
    mime = "image/png" if sc.image_path.endswith(".png") else "image/jpeg"
    return media_file_response(sc.image_path, mime)


# --------------------------------------------------------------- render ----
class RenderBody(BaseModel):
    resolution: str = "1280x720"
    fps: int = 30
    transition: str = "crossfade"
    transition_duration: float = 0.6
    burn_subtitles: bool = True
    karaoke: bool = True


@router.post("/projects/{pid}/render")
def start_render(pid: int, body: RenderBody | None = None, db: Session = Depends(get_db_dep)):
    p = _project(db, pid)
    scenes = db.query(Scene).filter(Scene.project_id == pid, Scene.image_status == "done").count()
    if scenes == 0:
        raise HTTPException(409, "Generate scene images first")
    body = body or RenderBody()
    render = Render(project_id=pid, status="queued", settings_json=json.dumps(body.model_dump()))
    db.add(render)
    db.flush()
    job = enqueue(db, "video.render", pid, {"project_id": pid, "render_id": render.id})
    db.commit()
    return {"render": render_json(render), "job": job_json(job)}


@router.get("/projects/{pid}/renders")
def list_renders(pid: int, db: Session = Depends(get_db_dep)):
    rows = db.query(Render).filter(Render.project_id == pid).order_by(Render.id.desc()).limit(15).all()
    return [render_json(r) for r in rows]


@router.get("/renders/{rid}/file")
def render_file(rid: int, db: Session = Depends(get_db_dep)):
    from ..media import media_file_response
    r = db.query(Render).get(rid)
    if not r or not r.path or r.status != "done":
        raise HTTPException(404, "Render not ready")
    return media_file_response(r.path, "video/mp4")


# ------------------------------------------------------------- feedback ----
class FeedbackBody(BaseModel):
    text: str


@router.post("/projects/{pid}/feedback")
def give_feedback(pid: int, body: FeedbackBody, db: Session = Depends(get_db_dep)):
    _project(db, pid)
    fb = FeedbackItem(project_id=pid, text=body.text.strip())
    db.add(fb)
    db.flush()
    job = enqueue(db, "feedback.interpret", pid, {"project_id": pid, "feedback_id": fb.id})
    db.commit()
    return {"feedback_id": fb.id, "job": job_json(job)}


class ApplyBody(BaseModel):
    regenerate: bool = True


@router.post("/feedback/{fid}/apply")
def apply_feedback(fid: int, body: ApplyBody, db: Session = Depends(get_db_dep)):
    from ..services.versions import snapshot
    fb = db.query(FeedbackItem).get(fid)
    if not fb:
        raise HTTPException(404, "Feedback not found")
    if fb.status != "interpreted" and not (PJ(fb.plan_json) or {}).get("ops"):
        raise HTTPException(409, "Feedback not interpreted yet")
    p = db.query(Project).get(fb.project_id)
    v = snapshot(db, p, label=f"Revision: {fb.text[:80]}")
    job = enqueue(db, "revision.apply", p.id, {"project_id": p.id, "feedback_id": fid})
    db.commit()
    return {"ok": True, "version": v.number, "job": job_json(job)}


# ------------------------------------------------------------- versions ----
@router.get("/projects/{pid}/versions")
def versions(pid: int, db: Session = Depends(get_db_dep)):
    from ..services.versions import list_versions
    return list_versions(db, _project(db, pid))


@router.post("/versions/{vid}/restore")
def restore_version(vid: int, db: Session = Depends(get_db_dep)):
    from ..models import ProjectVersion
    from ..services.versions import snapshot
    v = db.query(ProjectVersion).get(vid)
    if not v:
        raise HTTPException(404, "Version not found")
    p = db.query(Project).get(v.project_id)
    snap = PJ(v.snapshot_json) or {}
    # restore lyrics
    if snap.get("lyrics"):
        db.add(Lyrics(project_id=p.id, content_json=json.dumps(snap["lyrics"], ensure_ascii=False),
                      language=p.language, status="approved", source="revision"))
    # restore storyboard + scenes
    sb_old = snap.get("storyboard") or {}
    count = db.query(Storyboard).filter(Storyboard.project_id == p.id).count()
    sb = Storyboard(project_id=p.id, version=count + 1,
                    style_json=json.dumps(sb_old.get("style_bible") or {}, ensure_ascii=False),
                    status="approved")
    db.add(sb)
    db.flush()
    db.query(Scene).filter(Scene.project_id == p.id).delete()
    for i, s in enumerate(snap.get("scenes", [])):
        db.add(Scene(project_id=p.id, storyboard_id=sb.id, idx=i, section=s.get("section", ""),
                     lyrics_text=s.get("lyrics_text", ""), description=s.get("description", ""),
                     prompt=s.get("prompt", ""), negative=s.get("negative", ""), shot=s.get("shot", "wide"),
                     motion=s.get("motion", "slow_zoom_in"), start=s.get("start", 0), end=s.get("end", 0),
                     seed=s.get("seed", 1), image_status="pending"))
    cur = snapshot(db, p, label=f"Restored v{v.number}")
    db.commit()
    return {"ok": True, "restored_from": v.number, "new_version": cur.number}


# ----------------------------------------------------------------- jobs ----
@router.get("/jobs/{jid}")
def get_job(jid: int, db: Session = Depends(get_db_dep)):
    j = db.query(Job).get(jid)
    if not j:
        raise HTTPException(404, "Job not found")
    return job_json(j)


@router.post("/jobs/{jid}/cancel")
def cancel_job(jid: int, db: Session = Depends(get_db_dep)):
    j = db.query(Job).get(jid)
    if not j:
        raise HTTPException(404, "Job not found")
    if j.status == "queued":
        j.status = "cancelled"
        db.commit()
    return {"ok": True, "status": j.status}
