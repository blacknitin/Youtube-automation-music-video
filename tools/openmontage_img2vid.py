#!/usr/bin/env python3
"""OpenMontage local video bridge for SongForge.

Calls the free open-source engines of github.com/calesthio/OpenMontage
(AGPLv3) in THEIR repo — LTX-2 local, Wan 2.1/2.2, HunyuanVideo, CogVideoX —
through tools/video/_shared.generate_local_video. Running it as a separate
process keeps their code and heavy deps out of SongForge.

Usage:
  python openmontage_img2vid.py --repo /path/to/OpenMontage \
      --engine ltx2-local --image in.png --out out.mp4 \
      [--prompt "..."] [--seed 0] [--frames 121] [--steps 30]
"""
import argparse
import json
import sys
from pathlib import Path

VARIANT_FAMILIES = [
    ("ltx2-local", "LTX_LOCAL_VARIANTS"),
    ("hunyuan", "HUNYUAN_VARIANTS"),
    ("cogvideo", "COGVIDEO_VARIANTS"),
    ("wan", "WAN_VARIANTS"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--engine", required=True, help="e.g. ltx2-local | wan2.2-i2v-a14b | wan2.1-1.3b | hunyuan-1.5 | cogvideo-2b | cogvideo-5b")
    ap.add_argument("--image", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--frames", type=int, default=0)
    ap.add_argument("--steps", type=int, default=0)
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(json.dumps({"ok": False, "error": f"OpenMontage repo not found: {repo}"}))
        sys.exit(1)
    sys.path.insert(0, str(repo))

    from tools.video import _shared  # noqa: E402  (heavy imports happen inside)

    engine = args.engine.lower()
    variants = None
    for prefix, attr in VARIANT_FAMILIES:
        if engine.startswith(prefix):
            variants = getattr(_shared, attr)
            break
    if variants is None or engine not in variants:
        known = sorted({v for _p, a in VARIANT_FAMILIES for v in getattr(_shared, a)})
        print(json.dumps({"ok": False, "error": f"unknown engine {engine!r}. Known: {', '.join(known)}"}))
        sys.exit(1)

    meta = variants[engine]
    operation = "image_to_video" if (args.image and meta.get("i2v")) else "text_to_video"
    inputs = {
        "model_variant": engine,
        "operation": operation,
        "prompt": args.prompt or "cinematic scene, smooth motion",
        "seed": args.seed,
        "output_path": str(Path(args.out).resolve()),
    }
    if args.image:
        inputs["reference_image_path"] = str(Path(args.image).resolve())
    if args.frames > 0:
        inputs["num_frames"] = min(args.frames, int(meta.get("default_num_frames", 121)))
    if args.steps > 0:
        inputs["num_inference_steps"] = args.steps

    result = _shared.generate_local_video(
        tool_name="songforge_openmontage",
        variants=variants,
        default_variant=engine,
        inputs=inputs,
    )
    ok = bool(getattr(result, "success", False)) and Path(args.out).is_file()
    print(json.dumps({
        "ok": ok,
        "out": str(Path(args.out).resolve()) if ok else None,
        "operation": operation,
        "error": (getattr(result, "error", None) or (None if ok else "no output produced")),
    }))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
