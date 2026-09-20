"""ComfyUI (local Stable Diffusion / SDXL) image provider.

Posts a graph to ComfyUI's /prompt API and downloads the result.
Default workflow targets SDXL text-to-image; override with COMFY_WORKFLOW
pointing at your exported API-format workflow JSON containing the literal
strings "__PROMPT__", "__NEGATIVE__", "__SEED__", "__WIDTH__", "__HEIGHT__".
"""
import json
import time
import uuid

import httpx

from .base import ImageProvider, ProviderUnavailable
from ..config import SETTINGS

DEFAULT_WORKFLOW = {
    "3": {"class_type": "KSampler", "inputs": {
        "seed": 0, "steps": 26, "cfg": 6.5, "sampler_name": "dpmpp_2m",
        "scheduler": "karras", "denoise": 1.0,
        "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1280, "height": 720, "batch_size": 1}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "__PROMPT__", "clip": ["4", 1]}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "__NEGATIVE__", "clip": ["4", 1]}},
    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "songforge", "images": ["8", 0]}},
}


class ComfyUIImageProvider(ImageProvider):
    name = "comfyui"

    def __init__(self, url=None, workflow_path=None):
        self.url = (url or SETTINGS.comfy_url).rstrip("/")
        self.workflow_path = workflow_path or SETTINGS.comfy_workflow

    def available(self) -> bool:
        try:
            r = httpx.get(f"{self.url}/system_stats", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    def _load_workflow(self):
        if self.workflow_path:
            with open(self.workflow_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return json.loads(json.dumps(DEFAULT_WORKFLOW))

    def generate(self, prompt, negative, out_path, seed=0, width=1280, height=720):
        wf = self._load_workflow()
        raw = json.dumps(wf)
        raw = (raw.replace("__PROMPT__", json.dumps(prompt)[1:-1])
                  .replace("__NEGATIVE__", json.dumps(negative or "")[1:-1])
                  .replace("__SEED__", str(seed))
                  .replace("__WIDTH__", str(width))
                  .replace("__HEIGHT__", str(height)))
        wf = json.loads(raw)
        # fill seeds where the template didn't have a placeholder
        for node in wf.values():
            inputs = node.get("inputs", {})
            if node.get("class_type") in ("KSampler", "KSamplerAdvanced") and inputs.get("seed") in (0, -1):
                inputs["seed"] = seed
            if node.get("class_type") == "EmptyLatentImage":
                inputs.setdefault("width", width)
                inputs.setdefault("height", height)
                inputs.setdefault("batch_size", 1)
        with httpx.Client(timeout=30.0) as client:
            r = client.post(f"{self.url}/prompt", json={"prompt": wf, "client_id": uuid.uuid4().hex})
            r.raise_for_status()
            pid = r.json()["prompt_id"]
            # poll history
            for _ in range(600):  # up to ~10 min
                time.sleep(1.0)
                h = client.get(f"{self.url}/history/{pid}").json()
                if pid in h:
                    outputs = h[pid].get("outputs", {})
                    for node_out in outputs.values():
                        for img in node_out.get("images", []):
                            if img.get("type") == "output":
                                data = client.get(f"{self.url}/view",
                                                  params={"filename": img["filename"],
                                                          "subfolder": img.get("subfolder", ""),
                                                          "type": img.get("type", "output")}).content
                                with open(out_path, "wb") as f:
                                    f.write(data)
                                return str(out_path)
        raise ProviderUnavailable("ComfyUI timed out generating the image")
