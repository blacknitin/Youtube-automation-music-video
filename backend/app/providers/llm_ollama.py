"""Ollama local LLM provider (default real provider — free & local)."""
import json
import re

import httpx

from .base import LLMProvider, LyricRequest, AnalysisSummary, ProviderUnavailable
from .llm_common import scene_prompt_messages
from ..config import SETTINGS


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    raise ValueError("LLM did not return valid JSON")


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, url=None, model=None):
        self.url = (url or SETTINGS.ollama_url).rstrip("/")
        self.model = model or SETTINGS.ollama_model

    def available(self) -> bool:
        try:
            r = httpx.get(f"{self.url}/api/tags", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    def generate_scene_prompts(self, scenes: list, style_bible: dict, idea: str, genre: str) -> list:
        system, user = scene_prompt_messages(scenes, style_bible, idea, genre)
        data = self.complete_json(system, user, max_tokens=2800)
        out = data.get("prompts") or []
        return out if isinstance(out, list) else []

    def complete_json(self, system: str, user: str, max_tokens: int = 2400) -> dict:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "format": "json",
            "options": {"temperature": SETTINGS.llm_temperature, "num_predict": max_tokens},
        }
        with httpx.Client(timeout=600.0) as client:
            r = client.post(f"{self.url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
        return _extract_json(data.get("message", {}).get("content", ""))


def _json_instructions() -> str:
    return "Respond with ONLY a valid JSON object. No markdown, no commentary."
