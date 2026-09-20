"""OpenAI-compatible chat provider.

Works with OpenAI, Groq, OpenRouter, Together, LM Studio, vLLM or any
endpoint that implements /chat/completions — this is the "cloud provider"
plug-in point for the LLM.
"""
import json
import re

import httpx

from .base import LLMProvider, ProviderUnavailable
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


class OpenAICompatProvider(LLMProvider):
    name = "openai"

    def __init__(self, base_url=None, api_key=None, model=None):
        self.base_url = (base_url or SETTINGS.openai_base_url).rstrip("/")
        self.api_key = api_key or SETTINGS.openai_api_key
        self.model = model or SETTINGS.openai_model

    def available(self) -> bool:
        return bool(self.api_key) or "localhost" in self.base_url or "127.0.0.1" in self.base_url

    def generate_scene_prompts(self, scenes: list, style_bible: dict, idea: str, genre: str) -> list:
        from .llm_common import scene_prompt_messages
        system, user = scene_prompt_messages(scenes, style_bible, idea, genre)
        data = self.complete_json(system, user, max_tokens=2800)
        out = data.get("prompts") or []
        return out if isinstance(out, list) else []

    def complete_json(self, system: str, user: str, max_tokens: int = 2400) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": SETTINGS.llm_temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=600.0) as client:
            r = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        return _extract_json(data["choices"][0]["message"]["content"])
