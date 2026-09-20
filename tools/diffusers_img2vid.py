#!/usr/bin/env python3
"""Image-to-video runner for free open-source models via HuggingFace diffusers.

Used by SongForge's DiffusersVideoProvider (VIDEO_PROVIDER=diffusers). One
script covers several FREE GitHub projects / open-weight models:

  svd         stabilityai/stable-video-diffusion-img2vid-xt   (SVD img2vid)
  animatediff guoyww/animatediff-motion-adapter + SD1.5 base   (AnimateDiff)
  ltx         Lightricks/LTX-Video                             (very fast)
  cogvideox   THUDM/CogVideoX-2b (-5b)                         (open weights)
  wan         Wan-AI/Wan2.1-I2V-14B-480P (or 1.3B)             (Apache-2.0)

Usage:
  python tools/diffusers_img2vid.py --model ltx --image in.png --out out.mp4 \
      [--frames 48] [--fps 12] [--seed 0] [--width 1280] [--height 720] \
      [--steps 25] [--guidance 3.5] [--prompt "..."]

Models download once into the standard HuggingFace cache. Needs decent RAM/VRAM;
run on the machine that has the GPU. Errors exit non-zero with a message.
"""
import argparse
import json
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=["svd", "animatediff", "ltx", "cogvideox", "wan"])
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", type=int, default=48)
    ap.add_argument("--fps", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=576)
    ap.add_argument("--steps", type=int, default=25)
    ap.add_argument("--guidance", type=float, default=3.5)
    ap.add_argument("--prompt", default="")
    args = ap.parse_args()

    import importlib
    import torch
    from PIL import Image

    def load_pipe():
        if args.model == "svd":
            from diffusers import StableVideoDiffusionPipeline
            pipe = StableVideoDiffusionPipeline.from_pretrained(
                "stabilityai/stable-video-diffusion-img2vid-xt",
                torch_dtype=torch.float16, variant="fp16")
            return pipe, {"decode_chunk_size": 2, "num_frames": min(args.frames, 25)}
        if args.model == "animatediff":
            from diffusers import AnimateDiffPipeline, EulerDiscreteScheduler, MotionAdapter
            adapter = MotionAdapter.from_pretrained("guoyww/animatediff-motion-adapter-v1-5-2")
            pipe = AnimateDiffPipeline.from_pretrained(
                "emilianJR/epiCRealism", motion_adapter=adapter, torch_dtype=torch.float16)
            return pipe, {"num_frames": min(args.frames, 32)}
        if args.model == "ltx":
            from diffusers import LTXImageToVideoPipeline
            pipe = LTXImageToVideoPipeline.from_pretrained(
                "Lightricks/LTX-Video", torch_dtype=torch.bfloat16)
            return pipe, {"num_frames": min(args.frames, 161)}
        if args.model == "cogvideox":
            from diffusers import CogVideoXImageToVideoPipeline
            pipe = CogVideoXImageToVideoPipeline.from_pretrained(
                "THUDM/CogVideoX-2b", torch_dtype=torch.float16)
            return pipe, {"num_frames": min(args.frames, 49)}
        if args.model == "wan":
            from diffusers import WanImageToVideoPipeline
            pipe = WanImageToVideoPipeline.from_pretrained(
                "Wan-AI/Wan2.1-I2V-14B-480P", torch_dtype=torch.float16)
            return pipe, {"num_frames": min(args.frames, 81)}
        raise SystemExit(f"unknown model {args.model}")

    pipe, extra = load_pipe()
    pipe.enable_model_cpu_offload()  # fits big models on modest GPUs
    pipe.vae.enable_tiling()

    image = Image.open(args.image).convert("RGB")
    image = image.resize((args.width // 8 * 8, args.height // 8 * 8))
    gen = torch.Generator().manual_seed(args.seed)
    kw = dict(image=image, prompt=(args.prompt or None),
              guidance_scale=args.guidance, num_inference_steps=args.steps,
              generator=gen, **extra)
    if args.model in ("svd", "ltx"):  # these take no prompt
        kw.pop("prompt", None)
        kw.pop("guidance_scale", None) if args.model == "svd" else kw.update(
            guidance_scale=max(1.5, min(args.guidance, 5.0)))
    out = pipe(**kw)
    frames = out.frames[0]
    import os
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    from diffusers.utils import export_to_video
    export_to_video(frames, args.out, fps=args.fps)
    print(json.dumps({"ok": True, "out": args.out, "frames": len(frames)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)[:400]}), file=sys.stderr)
        sys.exit(1)
