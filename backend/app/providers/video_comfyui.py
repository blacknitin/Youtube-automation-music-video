"""ComfyUI video provider — free open-source image-to-video models.

ComfyUI (github.com/comfyanonymous/ComfyUI) runs the big free video models:
Stable Video Diffusion (built in), AnimateDiff, Wan 2.1/2.2, LTX-Video,
CogVideoX and HunyuanVideo (via custom nodes) — all open-source / open
weights, on YOUR machine.

Setup:
  1. Install ComfyUI with video support and its video custom nodes.
  2. Export your graph in "API format" (Settings -> Dev mode -> Save API format).
  3. Put the literal tokens in it:
       __IMAGE__   -> LoadImage node input  (SongForge uploads the scene image)
       __PROMPT__  -> prompt text node      (scene description)
       __NEGATIVE__-> negative text node
       __SEED__    -> sampler seed
       __FRAMES__  -> frame count node      (scene length in frames)
       __FPS__     -> fps node
       __WIDTH__ / __HEIGHT__ -> video size
  4. Set COMFY_VIDEO_WORKFLOW=/path/to/workflow.json in .env and restart.
  5. Test with "Test connection" — status shows  video: comfyui.

Without this, scenes get the built-in FFmpeg Ken-Burns motion (zero setup).
"""
import base64
import json
import re
import time

import httpx

from .base import VideoProvider, ProviderUnavailable
from ..config import SETTINGS


_token_only = re.compile(r"^__([A-Za-z_]+)__$")

def apply_workflow_tokens(workflow: dict, **tokens) -> dict:
    """Replace __TOKEN__ placeholders (recursively) in an API-format workflow.

    A field that IS exactly one token (e.g. "length": "__FRAMES__") gets the
    value's native type (int/float) - ComfyUI's API rejects JSON strings where
    it expects numbers. Mixed strings get textual substitution.
    """
    lower = {k.lower(): v for k, v in tokens.items()}
    def sub(v):
        if isinstance(v, str):
            m = _token_only.fullmatch(v.strip())
            if m and m.group(1).lower() in lower:
                return lower[m.group(1).lower()]
            for k, val in tokens.items():
                ph = f"__{k.upper()}__"
                if ph in v:
                    v = v.replace(ph, str(val))
            return v
        if isinstance(v, list):
            return [sub(x) for x in v]
        if isinstance(v, dict):
            return {k: sub(x) for k, x in v.items()}
        return v
    return sub(workflow)


def _pick_output(history: dict) -> tuple:
    """Return (filename, subfolder, type) of the first media output."""
    for entry in history.values():
        for item in (entry.get("outputs") or {}).values():
            for key in ("images", "gifs", "videos"):
                for media in item.get(key, []) or []:
                    if media.get("filename"):
                        return (media["filename"], media.get("subfolder", ""),
                                media.get("type", "output"))
    return None


class ComfyUIVideoProvider(VideoProvider):
    name = "comfyui"

    def __init__(self):
        self.workflow_path = SETTINGS.comfy_video_workflow

    def available(self) -> bool:
        if not self.workflow_path:
            return False
        try:
            return httpx.get(f"{SETTINGS.comfy_url.rstrip('/')}/system_stats",
                             timeout=2).status_code == 200
        except Exception:
            return False

    def animate(self, image_path, duration, fps, prompt, out_path, seed=0,
                width=1280, height=720, progress=None):
        if not self.workflow_path:
            raise ProviderUnavailable(
                "Set COMFY_VIDEO_WORKFLOW to an API-format ComfyUI workflow "
                "(see providers/video_comfyui.py docstring or README).")
        try:
            wf = json.load(open(self.workflow_path, encoding="utf-8"))
        except Exception as e:
            raise ProviderUnavailable(f"Cannot read workflow: {e}")

        frames = max(8, min(241, int(round(duration * fps))))
        base = f"{SETTINGS.comfy_url.rstrip('/')}"

        # 1. upload the scene image
        if progress:
            progress(10, "Uploading scene image to ComfyUI…")
        image_bytes = open(image_path, "rb").read()
        r = httpx.post(f"{base}/upload/image",
                       files={"image": (f"sf_scene_{seed}.png", image_bytes, "image/png")},
                       data={"overwrite": "true"}, timeout=60)
        r.raise_for_status()
        up = r.json()
        # LoadImage (API format) takes the plain uploaded filename
        image_ref = up.get("name")

        # 2. queue the prompt with tokens applied
        wf = apply_workflow_tokens(
            wf, IMAGE=image_ref, PROMPT=prompt or "", NEGATIVE="",
            SEED=int(seed) % 2**31, FRAMES=frames, FPS=fps,
            WIDTH=width, HEIGHT=height)
        if progress:
            progress(25, "Queuing video generation…")
        r = httpx.post(f"{base}/prompt", json={"prompt": wf}, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"ComfyUI rejected the workflow: {r.text[:400]}")
        pid = r.json()["prompt_id"]

        # 3. poll until finished
        deadline = time.time() + max(600.0, duration * 40)
        poll = 0
        while time.time() < deadline:
            time.sleep(2)
            poll += 2
            if progress:
                progress(min(88.0, 25 + 60 * poll / max(60.0, duration * 12)),
                         "Generating video with ComfyUI (open-source model)…")
            h = httpx.get(f"{base}/history/{pid}", timeout=30).json()
            if pid in h:
                entry = h[pid]
                if entry.get("status", {}).get("status_str") == "error":
                    raise RuntimeError("ComfyUI reported an execution error "
                                       "(check the ComfyUI console).")
                out = _pick_output(entry)
                if out:
                    break
        else:
            raise RuntimeError("ComfyUI video generation timed out.")

        # 4. download the result
        filename, subfolder, ftype = out
        r = httpx.get(f"{base}/view", params={"filename": filename,
                                              "subfolder": subfolder,
                                              "type": ftype}, timeout=300)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(r.content)
        return str(out_path)
