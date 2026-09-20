"""Character animation provider — facebookresearch/AnimatedDrawings (MIT).

github.com/facebookresearch/AnimatedDrawings detects the character in an
image, rigs a skeleton onto it and retargets real motion-capture clips
(dance, jump, wave, ...) onto it — 100% free, runs on CPU.

Setup (on a machine with a display — the renderer needs OpenGL):
  git clone https://github.com/facebookresearch/AnimatedDrawings
  pip install -e AnimatedDrawings
  pip install opencv-python          # or opencv-python-headless on servers
Then set in .env:
  CHAR_ANIM_REPO=/path/to/AnimatedDrawings
  VIDEO_PROVIDER=char-animated       # or "auto"

Every scene image that contains a character gets ANIMATED with a motion clip
chosen from the scene text (dance / jump / wave / zombie ...); the clip is
normalized to the scene's exact duration. Scenes where no character is found
automatically fall back to FFmpeg Ken-Burns motion — a render never fails.

Modern diffusion-based character animators (MimicMotion, MusePose,
MagicAnimate, LivePortrait) work through the ComfyUI provider instead — see
README section "Character animation".
"""
import os
import shutil
import subprocess
from pathlib import Path

from .base import VideoProvider, ProviderUnavailable
from ..config import SETTINGS

# scene text keywords -> motion config shipped with AnimatedDrawings
_MOTION_MAP = [
    (("danc", "nach", "disco"), "jesse_dance"),
    (("jump", "leap"), "jumping"),
    (("jack", "energ", "fitness", "exercis"), "jumping_jacks"),
    (("wave", "hello", "greet", "welcome", "bless"), "wave_hello"),
    (("zombie", "spook", "horr", "haunt"), "zombie"),
    (("dab", "celebrat", "party"), "dab"),
]

_DEFAULT_MOTION = "wave_hello"


def pick_motion(text: str) -> str:
    low = (text or "").lower()
    for keys, motion in _MOTION_MAP:
        if any(k in low for k in keys):
            return motion
    return _DEFAULT_MOTION


class AnimatedDrawingsProvider(VideoProvider):
    name = "char-animated"

    def available(self) -> bool:
        if not SETTINGS.char_anim_repo:
            return False
        repo = Path(SETTINGS.char_anim_repo)
        runner = repo / "examples" / "image_to_animation.py"
        if not runner.is_file():
            return False
        py = SETTINGS.char_anim_python
        if py and not Path(py).exists():
            return False
        return True

    def animate(self, image_path, duration, fps, prompt, out_path, seed=0,
                width=1280, height=720, progress=None):
        repo = Path(SETTINGS.char_anim_repo)
        runner = repo / "examples" / "image_to_animation.py"
        retarget = repo / "examples" / "config" / "retarget" / "fair1_ppf.yaml"
        if not runner.is_file():
            raise ProviderUnavailable("AnimatedDrawings repo not found "
                                      f"({SETTINGS.char_anim_repo!r})")

        workdir = Path(out_path).parent / (Path(out_path).stem + "_ad")
        if workdir.exists():
            shutil.rmtree(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        src_img = workdir / "character.png"
        shutil.copy(str(image_path), src_img)

        motion = pick_motion(prompt)
        motion_yaml = self._motion_cfg(repo, motion, workdir)
        if progress:
            progress(20, f"Rigging character ({motion} motion)…")

        py = SETTINGS.char_anim_python or "python3"
        cmd = [py, str(runner), str(src_img), str(workdir),
               str(motion_yaml), str(retarget)]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               errors="replace", timeout=900,
                               cwd=str(repo))
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"AnimatedDrawings timed out after 900s")
        gif = workdir / "character" / "video.gif"
        if not gif.is_file():
            tail = ((p.stderr or "") + (p.stdout or ""))[-300:]
            raise RuntimeError(f"AnimatedDrawings failed: {tail}")
        if progress:
            progress(75, "Normalizing animated character clip…")

        frames = max(8, int(round(duration * fps)))
        vf = (f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,"
              f"crop={width}:{height},format=yuv420p")
        enc = [SETTINGS.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-nostdin",
               "-stream_loop", "-1", "-i", str(gif),
               "-vf", vf, "-frames:v", str(frames), "-an",
               "-c:v", "libx264", "-preset", "ultrafast", "-crf", "14",
               "-pix_fmt", "yuv420p", str(out_path)]
        r = subprocess.run(enc, capture_output=True, text=True, errors="replace")
        if r.returncode != 0 or not Path(out_path).is_file():
            raise RuntimeError(f"clip encode failed: {(r.stderr or '')[-300:]}")
        return str(out_path)

    def _motion_cfg(self, repo: Path, motion: str, workdir: Path) -> Path:
        """Copy the motion config into the workdir (keeps repo read-only)."""
        src = repo / "examples" / "config" / "motion" / f"{motion}.yaml"
        if not src.is_file():
            src = repo / "examples" / "config" / "motion" / f"{_DEFAULT_MOTION}.yaml"
        dst = workdir / f"motion_{motion}.yaml"
        shutil.copy(src, dst)
        return dst
