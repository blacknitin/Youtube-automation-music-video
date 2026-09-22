"""Project CRUD + detail."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db_dep
from ..models import Project, Status
from ..serializers import project_brief, project_detail

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    title: str = ""
    idea: str = Field(min_length=3)
    language: str = "hi"
    genre: str = ""
    mood: str = ""
    visual_style: str = ""


class ProjectUpdate(BaseModel):
    title: str | None = None
    idea: str | None = None
    language: str | None = None
    genre: str | None = None
    mood: str | None = None
    visual_style: str | None = None
    settings: dict | None = None


@router.get("")
def list_projects(db: Session = Depends(get_db_dep)):
    rows = db.query(Project).order_by(Project.updated_at.desc()).all()
    return [{"brief": project_brief(p)} for p in rows]


@router.post("")
def create_project(body: ProjectCreate, db: Session = Depends(get_db_dep)):
    p = Project(title=body.title.strip() or (body.idea.strip()[:70]), idea=body.idea.strip(),
                language=body.language, genre=body.genre, mood=body.mood,
                visual_style=body.visual_style, status=Status.CREATED)
    db.add(p)
    db.commit()
    return project_brief(p)


@router.get("/{pid}")
def get_project(pid: int, db: Session = Depends(get_db_dep)):
    p = db.query(Project).get(pid)
    if not p:
        raise HTTPException(404, "Project not found")
    return project_detail(db, p)


@router.put("/{pid}")
def update_project(pid: int, body: ProjectUpdate, db: Session = Depends(get_db_dep)):
    p = db.query(Project).get(pid)
    if not p:
        raise HTTPException(404, "Project not found")
    for k in ("title", "idea", "language", "genre", "mood", "visual_style"):
        v = getattr(body, k)
        if v is not None:
            setattr(p, k, v)
    if body.settings is not None:
        p.settings_json = json.dumps(body.settings)
    db.commit()
    return project_brief(p)


@router.delete("/{pid}")
def delete_project(pid: int, db: Session = Depends(get_db_dep)):
    p = db.query(Project).get(pid)
    if not p:
        raise HTTPException(404, "Project not found")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.get("/{pid}/subtitles.srt")
def export_subtitles_srt(pid: int, db: Session = Depends(get_db_dep)):
    """Export the song's lyric lines as an .srt subtitle file (pysrt).
    Timings come from the approved lyrics' alignment (same source the
    karaoke burn-in uses)."""
    import pysrt
    from fastapi import Response
    from ..models import Scene

    p = db.query(Project).get(pid)
    if not p:
        raise HTTPException(404, "Project not found")
    scenes = (db.query(Scene)
              .filter(Scene.project_id == pid)
              .order_by(Scene.idx).all())
    if not scenes:
        raise HTTPException(404, "No scenes/timings yet — approve lyrics first")

    subs = pysrt.SubRipFile()
    for sc in scenes:
        text = (sc.lyrics_text or "").strip()
        if not text:
            continue
        subs.append(pysrt.SubRipItem(
            index=len(subs) + 1,
            start=pysrt.SubRipTime(seconds=float(sc.start or 0)),
            end=pysrt.SubRipTime(seconds=float(sc.end or (sc.start or 0) + 3)),
            text=text))
    body = "\n".join(str(s) for s in subs)
    safe = "".join(c if c.isalnum() else "_" for c in p.title)[:40] or f"project_{pid}"
    return Response(content=body, media_type="application/x-subrip",
                    headers={"Content-Disposition": f'attachment; filename="{safe}.srt"'})
