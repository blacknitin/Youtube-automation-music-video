"""Diffusers video provider — MORE free GitHub repos, one local engine.

Runs tools/diffusers_img2vid.py in a subprocess (heavy torch/diffusers deps
stay out of the app) against the free open-weight video models:

  svd         github.com/Stability-AI/generative-models (SVD img2vid)
  animatediff github.com/guoyww/AnimateDiff
  ltx         github.com/Lightricks/LTX-Video
  cogvideox   github.com/THUDM/CogVideoX
  wan         github.com/Wan-Video/Wan2.1 (Apache-2.0)

Setup:
  pip install diffusers torch transformers accelerate imageio imageio-ffmpeg
  # .env
  VIDEO_PROVIDER=diffusers
  VIDEO_DIFFUSERS_MODEL=ltx            # svd | animatediff | ltx | cogvideox | wan
  # VIDEO_DIFFUSERS_PYTHON=/path/to/python_with_diffusers
First run downloads the model (multi-GB); afterwards fully local & free.
Falls back per-scene to FFmpeg motion on any error.
"""
import json
import subprocess
from pathlib import Path

from .base import VideoProvider, ProviderUnavailable
from ..config import SETTINGS

_RUNNER = Path(__file__).resolve().parents[3] / "tools" / "diffusers_img2vid.py"


class DiffusersVideoProvider(VideoProvider):
    name = "diffusers"

    @property
    def model_key(self):
        return (SETTINGS.video_diffusers_model or "ltx").lower()

    def available(self) -> bool:
        return bool(SETTINGS.video_diffusers_model) and _RUNNER.is_file()

    def animate(self, image_path, duration, fps, prompt, out_path, seed=0,
                width=1280, height=720, progress=None):
        if not self.available():
            raise ProviderUnavailable("Set VIDEO_DIFFUSERS_MODEL (svd|animatediff|ltx|"
                                      "cogvideox|wan) to enable this provider.")
        py = SETTINGS.video_diffusers_python or "python3"
        # generation fps differs from scene fps; the render pass normalizes later
        gen_fps = {"svd": 12, "animatediff": 12, "ltx": 24, "cogvideox": 12, "wan": 16}.get(self.model_key, 12)
        frames = max(8, min(161, int(round(min(duration, 6.0) * gen_fps))))
        if progress:
            progress(20, f"Generating video with {self.model_key} (diffusers)…")
        cmd = [py, str(_RUNNER),
               "--model", self.model_key, "--image", str(image_path),
               "--out", str(out_path), "--frames", str(frames),
               "--fps", str(gen_fps), "--seed", str(int(seed) % 2**31),
               "--width", str(min(width, 1280)), "--height", str(min(height, 720)),
               "--steps", str(SETTINGS.video_diffusers_steps),
               "--guidance", str(SETTINGS.video_diffusers_guidance),
               "--prompt", (prompt or "")[:400]]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               errors="replace", timeout=1800)
        except subprocess.TimeoutExpired:
            raise RuntimeError("diffusers generation timed out (30 min)")
        if p.returncode != 0 or not Path(out_path).is_file():
            tail = ((p.stderr or "") + (p.stdout or ""))[-300:]
            raise RuntimeError(f"diffusers failed: {tail}")
        return str(out_path)
