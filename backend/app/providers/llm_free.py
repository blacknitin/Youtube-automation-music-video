"""Free AI provider — real AI model prompt-writing at zero cost.

Chat-completions compatible, so it works with every popular FREE tier:
  preset=groq       https://api.groq.com/openai/v1        (console.groq.com — free key)
  preset=gemini     Google AI Studio OpenAI-compatible    (aistudio.google.com — free key)
  preset=openrouter https://openrouter.ai/api/v1          (`:free` models — free key)
  preset=custom     your own FREE_LLM_BASE_URL/MODEL

Configure in backend/.env:
  FREE_LLM_PRESET=groq
  FREE_LLM_API_KEY=gsk_...

With no key set, the provider reports unavailable and the registry chain
(ollama -> free -> mock) falls back gracefully — nothing ever hard-fails
because of the LLM.
"""
import httpx

from .base import ProviderUnavailable
from .llm_common import StructuredLLMMixin
from ..config import SETTINGS

# name -> (base_url, default model)
PRESETS = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
    "openrouter": ("https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free"),
}

# Where users get a free key (shown in /api/system/providers + docs)
KEY_URLS = {
    "groq": "https://console.groq.com/keys",
    "gemini": "https://aistudio.google.com/apikey",
    "openrouter": "https://openrouter.ai/keys",
}


def _extract_json(text: str) -> dict:
    import json
    import re
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # strip markdown fences if present
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    raise ValueError("LLM did not return valid JSON")


class FreeLLMProvider(StructuredLLMMixin):
    """Free cloud LLM (free-tier key) for ALL AI writing: scene video prompts,
    storyboards, lyrics, feedback parsing, YouTube metadata."""

    name = "free"

    def __init__(self):
        self.preset = (SETTINGS.free_llm_preset or "groq").lower()
        if self.preset in PRESETS:
            base_default, model_default = PRESETS[self.preset]
        else:
            base_default, model_default = "", ""
        self.base_url = (SETTINGS.free_llm_base_url or base_default).rstrip("/")
        self.model = SETTINGS.free_llm_model or model_default or "default"
        self.api_key = SETTINGS.free_llm_api_key

    def available(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def generate_scene_prompts(self, scenes: list, style_bible: dict, idea: str, genre: str) -> list:
        """Per-scene cinematic video prompts (40-70 words each) — the exact
        contract h_render consumes (scene.prompt only)."""
        from .llm_common import scene_prompt_messages
        system, user = scene_prompt_messages(scenes, style_bible, idea, genre)
        data = self.complete_json(system, user, max_tokens=2800)
        out = data.get("prompts") or []
        return out if isinstance(out, list) else []

    def info(self) -> dict:
        return {
            "preset": self.preset,
            "base_url": self.base_url,
            "model": self.model,
            "key_set": bool(self.api_key),
            "key_url": KEY_URLS.get(self.preset, ""),
        }

    def complete_json(self, system: str, user: str, max_tokens: int = 2400) -> dict:
        if not self.available():
            raise ProviderUnavailable("free LLM not configured (set FREE_LLM_API_KEY)")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if "openrouter" in self.base_url:
            headers["HTTP-Referer"] = "https://github.com/blacknitin/Youtube-automation-music-video"
            headers["X-Title"] = "SongForge"
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": SETTINGS.llm_temperature,
            "max_tokens": max_tokens,
        }
        with httpx.Client(timeout=600.0) as client:
            r = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            if r.status_code in (400, 404, 422):
                # some free endpoints reject response_format — already omitted; retry bare
                r = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise ProviderUnavailable(f"unexpected free-LLM response: {data}") from exc
        return _extract_json(content)
