"""SongForge CPU bridge for the OpenMontage engine interface.

The REAL engines live in github.com/calesthio/OpenMontage (LTX-2, Wan 2.1/2.2,
HunyuanVideo, CogVideoX — GPU). This package implements the SAME interface
(tools/video/_shared.py: generate_local_video + variant catalogs) for
CPU-only machines: it renders each scene image into a motion clip. Point
OPENMONTAGE_REPO at the real clone on a GPU box for full diffusion quality.
"""
LTX_LOCAL_VARIANTS = {"ltx2-local": {"name": "LTX-2 local (CPU bridge)", "i2v": True, "hf_id": "bridge", "pipeline_class": "LTXImageToVideoPipeline", "default_width": 1280, "default_height": 720, "default_num_frames": 121, "fps": 30}}
HUNYUAN_VARIANTS = {"hunyuan-1.5": {"name": "HunyuanVideo (CPU bridge)", "i2v": True, "hf_id": "bridge", "pipeline_class": "P", "default_width": 960, "default_height": 544, "default_num_frames": 121, "fps": 24}}
COGVIDEO_VARIANTS = {"cogvideo-2b": {"name": "CogVideoX-2b (CPU bridge)", "i2v": True, "hf_id": "bridge", "pipeline_class": "P", "default_width": 720, "default_height": 480, "default_num_frames": 49, "fps": 8}, "cogvideo-5b": {"name": "CogVideoX-5b (CPU bridge)", "i2v": True, "hf_id": "bridge", "pipeline_class": "P", "default_width": 720, "default_height": 480, "default_num_frames": 49, "fps": 8}}
WAN_VARIANTS = {"wan2.2-i2v-a14b": {"name": "Wan2.2 I2V (CPU bridge)", "i2v": True, "hf_id": "bridge", "pipeline_class": "P", "default_width": 1280, "default_height": 704, "default_num_frames": 81, "fps": 16}, "wan2.1-1.3b": {"name": "Wan2.1 1.3B (CPU bridge)", "i2v": True, "hf_id": "bridge", "pipeline_class": "P", "default_width": 832, "default_height": 480, "default_num_frames": 81, "fps": 16}}

class ToolResult:
    def __init__(self, success=True, error=None):
        self.success, self.error = success, error

def generate_local_video(*, tool_name, variants, default_variant, inputs):
    """Motion-camera render of the reference image — interface-identical."""
    import subprocess
    meta = variants[inputs.get("model_variant", default_variant)]
    img, out = inputs.get("reference_image_path"), inputs["output_path"]
    n = int(inputs.get("num_frames") or meta["default_num_frames"])
    fps, w, h = meta["fps"], int(inputs.get("width") or meta["default_width"]), int(inputs.get("height") or meta["default_height"])
    if not img:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
               "-i", f"testsrc2=size={w}x{h}:rate={fps}", "-t", str(n / fps), out]
    else:
        W, H = int(w * 1.25) // 2 * 2, int(h * 1.25) // 2 * 2
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"zoompan=z='min(1.0+0.22*on/{max(1,n)},1.22)':d={n}"
              f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps},format=yuv420p")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", img,
               "-vf", vf, "-frames:v", str(n), "-c:v", "libx264",
               "-preset", "ultrafast", "-crf", "18", out]
    subprocess.run(cmd, check=True)
    return ToolResult(success=True)
