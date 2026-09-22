"""Local HuggingFace LLM — fully offline, keyless AI writing.

Uses EleutherAI/gpt-neo (github.com/EleutherAI/gpt-neo) via transformers so
storyboard + scene video prompts + lyrics can be written with ZERO cloud
services and ZERO keys. Quality is below Gemini/Ollama-chat models, so it
sits BELOW them in the chain and is opt-in:

  LLM_PROVIDER=hf                # force
  HF_LLM_MODEL=EleutherAI/gpt-neo-125M   # or 1.3B / 2.7B if you have RAM

Auto mode never selects it (tiny models are unreliable at strict JSON) —
chain stays: ollama -> free (Gemini/Groq key) -> offline templates.
Every parse failure falls back to the offline template writer, so nothing
ever hard-fails.
"""
import json
import re

from .base import LLMProvider, ProviderUnavailable
from ..config import SETTINGS

DEFAULT_MODEL = "EleutherAI/gpt-neo-125M"


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
    raise ValueError("no JSON in model output")


class HFLocalLLMProvider(LLMProvider):
    name = "hf"

    def __init__(self, model: str | None = None):
        self.model = model or SETTINGS.hf_llm_model or DEFAULT_MODEL
        self._gen = None

    def available(self) -> bool:
        try:
            import transformers  # noqa: F401
            return True
        except Exception:
            return False

    def _pipeline(self):
        if self._gen is None:
            from transformers import pipeline
            self._gen = pipeline("text-generation", model=self.model,
                                 do_sample=True, temperature=min(1.0, SETTINGS.llm_temperature))
        return self._gen

    def _complete(self, prompt: str, max_new_tokens: int = 300) -> str:
        out = self._pipeline()(prompt, max_new_tokens=max_new_tokens,
                               pad_token_id=50256, return_full_text=False)
        return out[0]["generated_text"] if out else ""

    def complete_json(self, system: str, user: str, max_tokens: int = 2400) -> dict:
        if not self.available():
            raise ProviderUnavailable("transformers not installed")
        prompt = f"{system}\n\n{user}\n\nJSON output only:\n"
        text = self._complete(prompt, max_new_tokens=min(500, max_tokens))
        return _extract_json(text)

    def generate_scene_prompts(self, scenes: list, style_bible: dict, idea: str, genre: str) -> list:
        """Tiny local models can't reliably emit strict JSON for many scenes,
        so we generate one short cinematic prompt per scene and assemble the
        contract ourselves. Any scene that fails keeps the offline template."""
        from .llm_mock import MockLLMProvider
        fallback = MockLLMProvider().generate_scene_prompts(scenes, style_bible, idea, genre)
        style = ", ".join(str(v) for v in (style_bible or {}).values() if v)[:120]
        out = []
        for s in scenes:
            base = fallback[s["index"]] if s["index"] < len(fallback) else {}
            try:
                lyric = (s.get("lyrics") or s.get("lyrics_text") or "")[:90]
                prompt = (f"Question: describe one cinematic video shot for a {genre or 'music'} song "
                          f"({style}). Lyric line: \"{lyric}\".\nAnswer:")
                text = self._complete(prompt, max_new_tokens=60).strip().split("\n")[0][:220]
                if len(text.split()) >= 8:
                    base = dict(base)
                    base["prompt"] = text
            except Exception:
                pass
            out.append(base)
        return out
