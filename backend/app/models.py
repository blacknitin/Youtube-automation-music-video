"""Database schema.

Tables
------
projects            one music-video project (the aggregate root)
project_versions    immutable snapshots (lyrics+storyboard+scenes) for versioning
lyrics              latest structured lyrics per project (draft/approved)
songs               imported/generated music tracks
audio_analyses      BPM, duration, beat grid, energy, waveform peaks, line alignment
storyboards         style bible + scene list (versioned)
scenes              individual scene rows: timing, prompts, generated image
renders             video render jobs/results
feedback_items      natural-language feedback + AI interpretation plan
jobs                background job queue (long-running generation)
youtube_metadata    generated/edited title, description, tags, thumbnail
youtube_uploads     upload attempts + resulting video ids
oauth_tokens        Google/YouTube OAuth credentials (single-user, local)
"""
import json
from datetime import datetime, timezone

from sqlalchemy import Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

def utcnow():
    return datetime.now(timezone.utc)

def J(v):  # json dump helper
    return json.dumps(v, ensure_ascii=False) if v is not None else None

def PJ(v):  # json parse helper
    if not v:
        return None
    try:
        return json.loads(v)
    except Exception:
        return None

# ---- workflow statuses -------------------------------------------------------
class Status:
    CREATED = "created"
    LYRICS_DRAFT = "lyrics_draft"
    LYRICS_APPROVED = "lyrics_approved"
    SONG_ADDED = "song_added"
    ANALYZED = "analyzed"
    STORYBOARD_DRAFT = "storyboard_draft"
    STORYBOARD_APPROVED = "storyboard_approved"
    SCENES_READY = "scenes_ready"
    RENDER_READY = "render_ready"
    FINAL_APPROVED = "final_approved"          # user gave final approval to the video
    METADATA_APPROVED = "metadata_approved"    # youtube metadata approved
    UPLOADED = "uploaded"

ORDER = [Status.CREATED, Status.LYRICS_DRAFT, Status.LYRICS_APPROVED, Status.SONG_ADDED,
         Status.ANALYZED, Status.STORYBOARD_DRAFT, Status.STORYBOARD_APPROVED,
         Status.SCENES_READY, Status.RENDER_READY, Status.FINAL_APPROVED,
         Status.METADATA_APPROVED, Status.UPLOADED]

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    idea: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(12), default="hi")
    genre: Mapped[str] = mapped_column(String(80), default="")
    mood: Mapped[str] = mapped_column(String(80), default="")
    visual_style: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(40), default=Status.CREATED, index=True)
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class ProjectVersion(Base):
    __tablename__ = "project_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer, default=1)
    label: Mapped[str] = mapped_column(String(300), default="")
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Lyrics(Base):
    __tablename__ = "lyrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    content_json: Mapped[str] = mapped_column(Text, default="{}")
    language: Mapped[str] = mapped_column(String(12), default="hi")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | approved
    source: Mapped[str] = mapped_column(String(20), default="ai")     # ai | manual | revision
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Song(Base):
    __tablename__ = "songs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    source: Mapped[str] = mapped_column(String(30), default="suno_import")  # suno_import | upload | demo
    original_name: Mapped[str] = mapped_column(String(300), default="")
    path: Mapped[str] = mapped_column(String(1000), default="")
    mime: Mapped[str] = mapped_column(String(100), default="audio/mpeg")
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class AudioAnalysis(Base):
    __tablename__ = "audio_analyses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"), index=True)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    bpm: Mapped[float] = mapped_column(Float, default=0.0)
    beat_offset: Mapped[float] = mapped_column(Float, default=0.0)
    sections_json: Mapped[str] = mapped_column(Text, default="[]")
    peaks_json: Mapped[str] = mapped_column(Text, default="[]")
    energy_json: Mapped[str] = mapped_column(Text, default="[]")
    alignment_json: Mapped[str] = mapped_column(Text, default="[]")  # per lyric line timings
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Storyboard(Base):
    __tablename__ = "storyboards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    style_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | approved
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Scene(Base):
    __tablename__ = "scenes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    storyboard_id: Mapped[int] = mapped_column(ForeignKey("storyboards.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer, default=0)
    section: Mapped[str] = mapped_column(String(100), default="")
    lyrics_text: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    negative: Mapped[str] = mapped_column(Text, default="")
    shot: Mapped[str] = mapped_column(String(40), default="wide")
    motion: Mapped[str] = mapped_column(String(40), default="slow_zoom_in")
    start: Mapped[float] = mapped_column(Float, default=0.0)
    end: Mapped[float] = mapped_column(Float, default=0.0)
    seed: Mapped[int] = mapped_column(Integer, default=0)
    image_path: Mapped[str] = mapped_column(String(1000), default="")
    image_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|done|failed
    image_error: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class Render(Base):
    __tablename__ = "renders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[int] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|done|failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(String(500), default="")
    path: Mapped[str] = mapped_column(String(1000), default="")
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

class FeedbackItem(Base):
    __tablename__ = "feedback_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    render_id: Mapped[int] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    plan_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|applied|dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(60))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued|running|done|failed|cancelled
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(String(500), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

class YouTubeMeta(Base):
    __tablename__ = "youtube_metadata"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    hashtags_json: Mapped[str] = mapped_column(Text, default="[]")
    category: Mapped[str] = mapped_column(String(10), default="10")  # 10 = Music
    privacy: Mapped[str] = mapped_column(String(20), default="private")  # private|unlisted|public
    thumbnail_path: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|approved
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class YouTubeUpload(Base):
    __tablename__ = "youtube_uploads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[str] = mapped_column(String(64), default="")
    url: Mapped[str] = mapped_column(String(300), default="")
    privacy: Mapped[str] = mapped_column(String(20), default="private")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default="youtube")
    cred_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
