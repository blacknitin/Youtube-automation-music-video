"""OpenMontage provider — the agentic open-source video production system.

github.com/calesthio/OpenMontage (AGPLv3) ships local video engines on top of
diffusers: LTX-2 local, Wan 2.1/2.2, HunyuanVideo and CogVideoX. SongForge
calls them through tools/openmontage_img2vid.py in a separate process (their
code + heavy deps stay out of this app; per-scene fallback to FFmpeg motion
keeps renders safe).

Setup:
  git clone https://github.com/calesthio/OpenMontage
  pip install diffusers torch transformers accelerate imageio imageio-ffmpeg
  # .env
  OPENMONTAGE_REPO=/path/to/OpenMontage
  VIDEO_PROVIDER=openmontage            # or auto
  OPENMONTAGE_ENGINE=ltx2-local         # wan2.2-i2v-a14b | wan2.1-1.3b | hunyuan-1.5 | cogvideo-2b | cogvideo-5b
Models download once into the HuggingFace cache; needs a GPU-class machine.
"""
import json
import subprocess
from pathlib import Path

from .base import VideoProvider, ProviderUnavailable
from ..config import SETTINGS

_RUNNER = Path(__file__).resolve().parents[3] / "tools" / "openmontage_img2vid.py"

# fallback chain mirrors OpenMontage's own tool fallbacks (i2v-capable first)
_FALLBACKS = {
    "ltx2-local": ["ltx2-local", "wan2.2-i2v-a14b", "hunyuan-1.5", "cogvideo-2b"],
    "wan2.2-i2v-a14b": ["wan2.2-i2v-a14b", "hunyuan-1.5", "cogvideo-2b"],
    "wan2.1-1.3b": ["wan2.1-1.3b", "cogvideo-2b"],
    "hunyuan-1.5": ["hunyuan-1.5", "cogvideo-2b"],
    "cogvideo-2b": ["cogvideo-2b"],
    "cogvideo-5b": ["cogvideo-5b"],
}

_GEN_FPS = {"ltx2-local": 30, "hunyuan-1.5": 24, "wan2.2-i2v-a14b": 16,
            "wan2.1-1.3b": 16, "cogvideo-2b": 8, "cogvideo-5b": 8}
_MAX_FRAMES = {"ltx2-local": 121, "hunyuan-1.5": 121, "wan2.2-i2v-a14b": 81,
               "wan2.1-1.3b": 81, "cogvideo-2b": 49, "cogvideo-5b": 49}


class OpenMontageProvider(VideoProvider):
    name = "openmontage"

    @property
    def engine(self):
        return (SETTINGS.openmontage_engine or "ltx2-local").lower()

    def available(self) -> bool:
        return bool(SETTINGS.openmontage_repo) and _RUNNER.is_file()

    def animate(self, image_path, duration, fps, prompt, out_path, seed=0,
                width=1280, height=720, progress=None):
        if not self.available():
            raise ProviderUnavailable("Set OPENMONTAGE_REPO to a clone of "
                                      "github.com/calesthio/OpenMontage to enable this provider.")
        py = SETTINGS.openmontage_python or "python3"
        chain = _FALLBACKS.get(self.engine, [self.engine])
        last_err = None
        for engine in chain:
            gen_fps = _GEN_FPS.get(engine, 16)
            frames = max(9, min(_MAX_FRAMES.get(engine, 81),
                                int(round(min(duration, 6.0) * gen_fps))))
            if progress:
                progress(20, f"Generating clip with OpenMontage/{engine}…")
            cmd = [py, str(_RUNNER),
                   "--repo", SETTINGS.openmontage_repo,
                   "--engine", engine,
                   "--image", str(image_path),
                   "--out", str(out_path),
                   "--prompt", (prompt or "")[:400],
                   "--seed", str(int(seed) % 2**31),
                   "--frames", str(frames),
                   "--steps", str(SETTINGS.video_diffusers_steps)]
            try:
                p = subprocess.run(cmd, capture_output=True, text=True,
                                   errors="replace", timeout=2400)
            except subprocess.TimeoutExpired:
                last_err = f"{engine}: timed out (40 min)"
                continue
            try:
                payload = json.loads((p.stdout or "").strip().splitlines()[-1])
            except Exception:
                payload = {"ok": False, "error": ((p.stderr or p.stdout or "")[-200:])}
            if p.returncode == 0 and payload.get("ok") and Path(out_path).is_file():
                return str(out_path)
            last_err = f"{engine}: {payload.get('error') or 'failed'}"
            if progress and len(chain) > 1:
                progress(30, f"{engine} unavailable — trying the next OpenMontage engine…")
        raise RuntimeError(f"OpenMontage generation failed — {last_err}")
