"""YouTube metadata + thumbnail generation."""
import json

from ..models import Lyrics, Song, YouTubeMeta, PJ
from ..providers.registry import get_image_provider, get_llm
from ..storage import thumbnail_path


def get_or_create(db, project) -> YouTubeMeta:
    row = db.query(YouTubeMeta).filter(YouTubeMeta.project_id == project.id).first()
    if not row:
        row = YouTubeMeta(project_id=project.id)
        db.add(row)
        db.flush()
    return row


def generate(db, project, lyrics: Lyrics | None, progress=None) -> YouTubeMeta:
    llm = get_llm()
    lyrics_text = ""
    if lyrics:
        content = PJ(lyrics.content_json) or {}
        lyrics_text = "\n".join(l for sec in content.get("sections", [])
                                for l in sec.get("lines", []))
    ctx = {"title": (PJ(lyrics.content_json) or {}).get("title") if lyrics else None,
           "idea": project.idea, "genre": project.genre, "mood": project.mood,
           "lyrics": lyrics_text}
    if progress:
        progress(20, "Writing title, description and tags with AI…")
    data = llm.generate_metadata(ctx)
    row = get_or_create(db, project)
    row.title = data.get("title", "")[:200]
    desc = data.get("description", "")
    tags = data.get("tags", []) or []
    hashtags = [h if str(h).startswith("#") else f"#{h}" for h in (data.get("hashtags", []) or [])]
    if hashtags and hashtags[-1] not in desc:
        desc = desc + "\n" + " ".join(hashtags[:8])
    row.description = desc[:4900]
    row.tags_json = json.dumps(tags, ensure_ascii=False)
    row.hashtags_json = json.dumps(hashtags, ensure_ascii=False)
    row.status = "draft"
    db.add(row)
    db.commit()  # commit before any further progress() calls
    if progress:
        progress(60, "Generating thumbnail art…")
    try:
        generate_thumbnail(db, project, row, data.get("thumbnail_prompt", ""))
        db.commit()
    except Exception:
        db.rollback()
        pass  # thumbnail is best-effort; scene art still available
    if progress:
        progress(100, "Metadata ready")
    return row


def generate_thumbnail(db, project, row: YouTubeMeta, prompt: str = ""):
    title = row.title or project.title
    img = get_image_provider()
    out = thumbnail_path(project.id)
    seed = abs(hash(f"{project.id}|{prompt}|{title}")) % (2**31)
    img.generate(prompt or "bold cinematic music video thumbnail, dramatic key art, high contrast",
                 "text, watermark, blurry", out, seed=seed, width=1280, height=720)
    from ..providers.image_placeholder import render_placeholder
    render_placeholder(prompt or "bold cinematic music thumbnail", out, seed=seed,
                       width=1280, height=720, title_text=title)
    row.thumbnail_path = str(out)
    db.add(row)
    return str(out)
