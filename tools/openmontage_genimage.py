#!/usr/bin/env python3
"""OpenMontage scene-art bridge for SongForge.

Calls the LOCAL image engine of github.com/calesthio/OpenMontage
(tools/graphics/local_diffusion.py — local Stable Diffusion via diffusers)
in the OpenMontage repo's own process. Keeps their code + heavy deps out of
SongForge, same pattern as the video bridge.

Usage:
  python openmontage_genimage.py --repo /path/to/OpenMontage --prompt "..." \
      --out scene.png [--negative "..."] [--seed 0] [--width 1280] [--height 720]
"""
import argparse
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--negative", default="")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--guidance", type=float, default=7.5)
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(json.dumps({"ok": False, "error": f"OpenMontage repo not found: {repo}"}))
        sys.exit(1)
    sys.path.insert(0, str(repo))

    try:
        from tools.graphics.local_diffusion import LocalDiffusion
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"local_diffusion unavailable: {e}"}))
        sys.exit(1)

    tool = LocalDiffusion()
    status = str(getattr(tool.get_status(), "name", tool.get_status()))
    if "AVAILABLE" not in status.upper():
        print(json.dumps({"ok": False,
                          "error": f"engine not ready ({status}) — pip install diffusers torch"}))
        sys.exit(1)

    result = tool.execute({
        "prompt": args.prompt,
        "negative_prompt": args.negative,
        "width": min(args.width, 1280),
        "height": min(args.height, 720),
        "seed": args.seed,
        "num_inference_steps": args.steps,
        "guidance_scale": args.guidance,
        "output_path": str(Path(args.out).resolve()),
    })
    ok = bool(getattr(result, "success", False)) and Path(args.out).is_file()
    print(json.dumps({
        "ok": ok,
        "out": str(Path(args.out).resolve()) if ok else None,
        "error": None if ok else (getattr(result, "error", None) or "generation failed"),
    }))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
