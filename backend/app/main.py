"""SongForge — free/local-first AI music-video studio.

FastAPI app: REST API + job worker + static hosting of the built frontend.
"""
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import SETTINGS
from .db import init_db
from .api import pipeline, projects, publish, system

app = FastAPI(title="SongForge", version="0.1.0",
              description="Local-first AI YouTube song automation: lyrics → music → storyboard → scenes → video → YouTube (with approval gates).")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # local-first app; tighten for public deploys
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(projects.router)
app.include_router(pipeline.router)
app.include_router(publish.router)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


@app.on_event("startup")
def startup():
    init_db()
    from .jobs import start_worker
    start_worker()


@app.on_event("shutdown")
def shutdown():
    from .jobs import stop_worker
    stop_worker()


# ---- serve the frontend (single-server mode) -------------------------------
# The frontend is a dependency-free React single file; drop dist/ there if you
# build with Vite instead (npm run build output goes to frontend/dist).
FRONTEND_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
INDEX_HTML = os.path.join(FRONTEND_DIST, "index.html")

if os.path.isfile(INDEX_HTML):
    if os.path.isdir(os.path.join(FRONTEND_DIST, "assets")):
        app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        candidate = os.path.abspath(os.path.join(FRONTEND_DIST, full_path))
        if full_path and os.path.isfile(candidate) and candidate.startswith(FRONTEND_DIST):
            return FileResponse(candidate)
        return FileResponse(INDEX_HTML)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=SETTINGS.host, port=SETTINGS.port, reload=False)
