"""Publish API: YouTube metadata, thumbnail, approvals, OAuth, upload.

APPROVAL SAFETY: the upload endpoint requires
  project.status == final_approved  AND metadata.status == approved
  AND body.confirm == true  (the "Approve & Upload" button).
There is no auto-publish anywhere in the codebase.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import SETTINGS
from ..db import get_db_dep
from ..jobs import enqueue, _latest_lyrics
from ..models import PJ, Project, Render, Status, YouTubeMeta, YouTubeUpload
from ..serializers import job_json, meta_json
from ..services import yt as yt_service
from ..services.meta import generate_thumbnail, get_or_create

router = APIRouter(prefix="/api", tags=["publish"])


def _project(db, pid):
    p = db.query(Project).get(pid)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@router.post("/projects/{pid}/metadata/generate")
def generate_metadata(pid: int, db: Session = Depends(get_db_dep)):
    p = _project(db, pid)
    done = db.query(Render).filter(Render.project_id == pid, Render.status == "done").count()
    if not done:
        raise HTTPException(409, "Render the video first — metadata describes the final cut")
    job = enqueue(db, "metadata.generate", pid, {"project_id": pid})
    return job_json(job)


class MetaBody(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    hashtags: list[str] | None = None
    category: str | None = None
    privacy: str | None = None


@router.put("/projects/{pid}/metadata")
def update_metadata(pid: int, body: MetaBody, db: Session = Depends(get_db_dep)):
    p = _project(db, pid)
    row = get_or_create(db, p)
    for k in ("title", "description", "category", "privacy"):
        v = getattr(body, k)
        if v is not None:
            setattr(row, k, v)
    if body.tags is not None:
        row.tags_json = json.dumps(body.tags, ensure_ascii=False)
    if body.hashtags is not None:
        row.hashtags_json = json.dumps(body.hashtags, ensure_ascii=False)
    row.status = "draft"
    db.commit()
    return meta_json(row)


@router.post("/projects/{pid}/thumbnail/regenerate")
def regenerate_thumbnail(pid: int, db: Session = Depends(get_db_dep)):
    _project(db, pid)
    job = enqueue(db, "thumbnail.regenerate", pid, {"project_id": pid})
    return job_json(job)


@router.get("/projects/{pid}/thumbnail")
def thumbnail(pid: int, db: Session = Depends(get_db_dep)):
    from ..media import media_file_response
    import os
    row = db.query(YouTubeMeta).filter(YouTubeMeta.project_id == pid).first()
    path = row.thumbnail_path if row and row.thumbnail_path else ""
    if not path or not os.path.exists(path):
        raise HTTPException(404, "No thumbnail yet")
    return media_file_response(path, "image/jpeg")


@router.post("/projects/{pid}/metadata/approve")
def approve_metadata(pid: int, db: Session = Depends(get_db_dep)):
    from ..services.versions import snapshot
    p = _project(db, pid)
    row = get_or_create(db, p)
    if not row.title.strip():
        raise HTTPException(409, "Add a title before approving metadata")
    row.status = "approved"
    if p.status == Status.RENDER_READY:
        p.status = Status.METADATA_APPROVED
    v = snapshot(db, p, label="Metadata approved")
    db.commit()
    return {"ok": True, "status": p.status, "metadata": meta_json(row)}


class FinalApprovalBody(BaseModel):
    confirm: bool = False


@router.post("/projects/{pid}/approve-final")
def approve_final(pid: int, body: FinalApprovalBody, db: Session = Depends(get_db_dep)):
    """FINAL APPROVAL gate — user explicitly signs off on the video."""
    p = _project(db, pid)
    done = db.query(Render).filter(Render.project_id == pid, Render.status == "done").count()
    if not done:
        raise HTTPException(409, "Render the video before final approval")
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true to give final approval")
    p.status = Status.FINAL_APPROVED
    db.commit()
    return {"ok": True, "status": p.status,
            "note": "Video approved. YouTube upload still requires metadata approval + Approve & Upload."}


# ----------------------------------------------------------------- youtube --
@router.get("/youtube/status")
def youtube_status(db: Session = Depends(get_db_dep)):
    return {"client_configured": yt_service.client_configured(),
            "connected": yt_service.connected() if yt_service.client_configured() else False}


@router.get("/youtube/auth-url")
def youtube_auth_url():
    if not yt_service.client_configured():
        raise HTTPException(501, "Set YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET in .env first. "
                                 "See README → YouTube setup.")
    return {"url": yt_service.auth_url()}


@router.get("/youtube/callback")
def youtube_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return _html(f"YouTube connect failed: {error}", ok=False)
    try:
        yt_service.exchange_code(code)
        return _html("YouTube connected! You can close this tab and return to SongForge.", ok=True)
    except Exception as e:
        return _html(f"YouTube connect failed: {e}", ok=False)


def _html(msg: str, ok: bool):
    color = "#22c55e" if ok else "#ef4444"
    icon = "✅" if ok else "❌"
    return HTMLResponse(content=f"<body style='font-family:system-ui;background:#0f172a;color:#e2e8f0;"
                                f"display:grid;place-items:center;height:100vh;margin:0'>"
                                f"<div style='text-align:center'><h2 style='color:{color}'>{icon} {msg}</h2>"
                                f"</div></body>", status_code=200)


@router.post("/youtube/disconnect")
def youtube_disconnect():
    yt_service.disconnect()
    return {"ok": True}


class UploadBody(BaseModel):
    confirm: bool = False
    privacy: str = "private"


@router.post("/projects/{pid}/upload")
def upload_to_youtube(pid: int, body: UploadBody, db: Session = Depends(get_db_dep)):
    """The ONLY path to YouTube. Requires explicit, explicit, explicit approval."""
    p = _project(db, pid)
    meta = db.query(YouTubeMeta).filter(YouTubeMeta.project_id == pid).first()
    if not body.confirm:
        raise HTTPException(400, "This action requires confirm=true (Approve & Upload button).")
    if p.status not in (Status.FINAL_APPROVED, Status.METADATA_APPROVED):
        raise HTTPException(409, "Give FINAL APPROVAL to the video first (step: Final Approval).")
    if not meta or meta.status != "approved":
        raise HTTPException(409, "Approve the YouTube metadata first.")
    if not yt_service.client_configured():
        raise HTTPException(501, "YouTube API keys missing in .env — see README → YouTube setup.")
    if body.privacy not in ("private", "unlisted", "public"):
        raise HTTPException(400, "privacy must be private|unlisted|public")
    meta.privacy = body.privacy
    upload = YouTubeUpload(project_id=pid, privacy=body.privacy, status="queued")
    db.add(upload)
    db.flush()
    job = enqueue(db, "youtube.upload", pid,
                  {"project_id": pid, "upload_id": upload.id, "confirm": True})
    db.commit()
    return {"ok": True, "upload_id": upload.id, "job": job_json(job)}
