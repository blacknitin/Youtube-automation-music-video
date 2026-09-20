"""YouTube OAuth + resumable upload.

SAFETY: nothing in this module is ever called automatically. Uploads happen
ONLY through POST /api/projects/{id}/upload after BOTH:
  1. the user gave final approval to the video, and
  2. the user approved the YouTube metadata, and
  3. the request body contains confirm=true (the "Approve & Upload" button).
"""
import json

from ..config import SETTINGS
from ..db import SessionLocal
from ..models import OAuthToken

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

_state = {}

def client_configured() -> bool:
    return bool(SETTINGS.youtube_client_id and SETTINGS.youtube_client_secret)

def _client_config() -> dict:
    return {"installed": {
        "client_id": SETTINGS.youtube_client_id,
        "client_secret": SETTINGS.youtube_client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [SETTINGS.youtube_redirect_uri],
    }}

def auth_url() -> str:
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES,
                                   redirect_uri=SETTINGS.youtube_redirect_uri)
    url, state = flow.authorization_url(access_type="offline", include_granted_scopes="true",
                                        prompt="consent")
    _state["state"] = state
    return url

def exchange_code(code: str) -> dict:
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES,
                                   redirect_uri=SETTINGS.youtube_redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials
    info = {"token": creds.token, "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri, "client_id": creds.client_id,
            "client_secret": creds.client_secret, "scopes": creds.scopes}
    with SessionLocal() as db:
        row = db.query(OAuthToken).filter(OAuthToken.kind == "youtube").first()
        if not row:
            row = OAuthToken(kind="youtube")
        row.cred_json = json.dumps(info)
        db.add(row)
        db.commit()
    return info

def get_credentials():
    """Returns google credentials or None if not connected."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except Exception:
        return None
    with SessionLocal() as db:
        row = db.query(OAuthToken).filter(OAuthToken.kind == "youtube").first()
        if not row:
            return None
        info = json.loads(row.cred_json)
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        info = {"token": creds.token, "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri, "client_id": creds.client_id,
                "client_secret": creds.client_secret, "scopes": creds.scopes}
        with SessionLocal() as db:
            row = db.query(OAuthToken).filter(OAuthToken.kind == "youtube").first()
            row.cred_json = json.dumps(info)
            db.add(row)
            db.commit()
    return creds

def disconnect():
    with SessionLocal() as db:
        db.query(OAuthToken).filter(OAuthToken.kind == "youtube").delete()
        db.commit()

def connected() -> bool:
    try:
        return get_credentials() is not None
    except Exception:
        return False

def upload_video(project, meta, render_path, privacy="private", progress_cb=None) -> dict:
    creds = get_credentials()
    if not creds:
        raise RuntimeError("YouTube is not connected. Open Settings → Connect YouTube first.")
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except Exception as e:
        raise RuntimeError("Google API client missing. Run: pip install -r requirements-youtube.txt") from e

    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    tags = meta.tags_list or []
    body = {
        "snippet": {
            "title": (meta.title or project.title)[:100],
            "description": meta.description or "",
            "tags": tags[:30],
            "categoryId": meta.category or "10",
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(render_path), chunksize=8 * 1024 * 1024, resumable=True,
                            mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk(num_retries=3)
        if status and progress_cb:
            progress_cb(float(status.progress() * 100))
    vid = response.get("id", "")
    return {"video_id": vid, "url": f"https://www.youtube.com/watch?v={vid}"}
