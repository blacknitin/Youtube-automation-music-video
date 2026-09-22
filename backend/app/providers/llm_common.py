"""Shared prompt plumbing for real LLM providers (Ollama, OpenAI-compatible).

Providers only implement `complete_json()`; this mixin turns it into the four
high-level capabilities the app needs.
"""
import json

from .base import LLMProvider


class StructuredLLMMixin(LLMProvider):

    # ---------------- lyrics ----------------
    def generate_lyrics(self, req) -> dict:
        system = (
            "You are an award-winning songwriter and lyricist (Bollywood, devotional, "
            "folk and pop traditions). You write lyrics that singers can actually sing: "
            "\n"
            "CRAFT RULES — follow all of them:\n"
            "1. SINGABILITY: 6-10 words per line, consistent syllable count across the "
            "lines of one section (a steady meter the composer can loop), lines end on "
            "open vowels or resonant consonants.\n"
            "2. RHYME: end-rhyme scheme AABB or ABAB inside every verse and chorus; the "
            "rhymes must be real rhymes in the target language, not near-misses.\n"
            "3. HOOK: the Chorus opens with the song title as its first line and repeats "
            "word-for-word every time the chorus returns.\n"
            "4. IMAGERY: concrete pictures (places, objects, actions, weather, light) "
            "drawn from the idea - never abstract filler like 'I feel something special'.\n"
            "5. LANGUAGE PURITY: write ONLY in the requested language (no English words "
            "inside Hindi lines), except brand/title hints.\n"
            "6. ARC: verse 1 = the situation, chorus = the emotional peak, verse 2 = "
            "development or turn, bridge = one twist or prayer, outro = resolution.\n"
            "7. STRUCTURE (default 7 sections): Intro(2 lines), Verse 1(4), Chorus(4), "
            "Verse 2(4), Chorus-2 (identical words to Chorus), Bridge(2-4), Outro(2). "
            "Name repeated choruses exactly 'Chorus-2' etc.\n" + self._json_rule()
        )
        user = {
            "task": "write_song_lyrics",
            "idea": req.idea,
            "language": req.language,
            "genre": req.genre or "any",
            "mood": req.mood or "emotional",
            "title_hint": req.title_hint or "",
            "format": {
                "title": "song title in the target language",
                "language": "the language code",
                "sections": [
                    {"name": "Intro|Verse 1|Chorus|Verse 2|Chorus-2|Bridge|Outro",
                     "type": "intro|verse|chorus|bridge|outro",
                     "lines": ["the singable lines of this section"]}
                ],
            },
            "rules": ["max 8 sections", "repeated choruses keep identical hook lines",
                      "6-10 words per line", "true end-rhymes (AABB/ABAB) in every section",
                      "chorus first line = song title"],
        }
        data = self.complete_json(system, json.dumps(user, ensure_ascii=False), max_tokens=2200)
        data.setdefault("title", req.title_hint or req.idea[:60])
        data.setdefault("language", req.language)
        data.setdefault("sections", [])
        return data

    # ---------------- storyboard ----------------
    def generate_storyboard(self, lyrics: dict, analysis, visual_style: str, idea: str) -> dict:
        secs = [{"name": s.get("name"), "type": s.get("type"), "lines": s.get("lines", [])}
                for s in lyrics.get("sections", [])]
        system = ("You are a music-video creative director. Given Hindi song lyrics and timing info, "
                  "you design a consistent visual story: a style bible (characters, locations, palette) "
                  "and a scene list. Character/location descriptions MUST stay reusable word-for-word "
                  "across scenes for visual consistency. " + self._json_rule())
        user = {
            "task": "create_storyboard",
            "song_idea": idea,
            "visual_style_requested": visual_style or "cinematic",
            "song_sections": secs,
            "audio": {"duration_seconds": round(analysis.duration, 1), "bpm": round(analysis.bpm, 1),
                      "sections": analysis.sections},
            "format": {
                "style_bible": {
                    "visual_style": "one-paragraph art direction",
                    "color_palette": ["#hex", "#hex", "#hex"],
                    "characters": [{"name": "Name", "description": "...",
                                    "prompt_token": "reusable image-model descriptor of the character"}],
                    "locations": ["reusable image-model descriptors of places"],
                    "global_negative": "things to avoid",
                },
                "scenes": [
                    {"section": "song section name this scene plays during",
                     "lyrics_text": "one lyric line (or empty for intros)",
                     "description": "what happens, in film language",
                     "prompt": "full image-generation prompt, embedding the character/location prompt_tokens",
                     "negative": "", "shot": "wide|medium|close-up",
                     "motion": "slow_zoom_in|slow_zoom_out|pan_left|pan_right"}
                ],
            },
            "rules": ["one scene per lyric line for verses and choruses (the scene's lyrics_text is that exact line)",
                      "one establishing scene each for intro, bridge and outro",
                      "keep total scenes under 40", "keep the same characters and locations across scenes",
                      "scene sections must reference the given song section names"],
        }
        data = self.complete_json(system, json.dumps(user, ensure_ascii=False), max_tokens=3000)
        data.setdefault("style_bible", {})
        data.setdefault("scenes", [])
        return data

    # ---------------- feedback ----------------
    def interpret_feedback(self, text: str, context: dict) -> dict:
        system = ("You are a music-video edit assistant. The director gives feedback in natural language. "
                  "You decide the MINIMAL set of changes required — never regenerate the whole video unless asked. "
                  + self._json_rule())
        user = {
            "task": "interpret_feedback",
            "feedback": text,
            "project": {"idea": context.get("idea"), "visual_style": context.get("visual_style"),
                        "characters": context.get("characters", [])},
            "scenes": [{"id": s["id"], "idx": s["idx"] + 1, "description": s["description"],
                        "prompt": s["prompt"][:300]} for s in context.get("scenes", [])],
            "format": {
                "summary": "one sentence: what you understood",
                "ops": [
                    {"op": "scene_image", "scene_id": 0, "prompt_adjust": "additions/modifications for the image prompt"},
                    {"op": "style_bible", "patch": {"visual_style": "optional new style"}},
                    {"op": "render_settings", "patch": {"transition": "crossfade|fade|none"}}
                ],
            },
            "rules": ["scene_id must be one of the given scene ids (0-based)",
                      "only include ops that are needed",
                      "if the user mentions 'scene 3' use the scene with idx 3 (id field)",
                      "for character/style changes, patch style_bible AND list affected scene_image ops"],
        }
        data = self.complete_json(system, json.dumps(user, ensure_ascii=False), max_tokens=1500)
        data.setdefault("summary", "Applied your feedback.")
        data.setdefault("ops", [])
        return data

    # ---------------- metadata ----------------
    def generate_metadata(self, context: dict) -> dict:
        system = ("You are a YouTube growth expert for Indian music channels. "
                  "Write SEO-friendly metadata in a mix of Hindi and English. " + self._json_rule())
        user = {
            "task": "youtube_metadata",
            "song_title": context.get("title"),
            "idea": context.get("idea"),
            "genre": context.get("genre"), "mood": context.get("mood"),
            "lyrics_excerpt": (context.get("lyrics") or "")[:1200],
            "format": {
                "title": "<=100 chars, catchy, with a hook",
                "description": "3-6 paragraphs: hook, about, lyrics excerpt, credits ('created with SongForge local AI pipeline'), call to action",
                "tags": ["15-20 search tags"],
                "hashtags": ["5-8 hashtags starting with #"],
                "thumbnail_prompt": "image-model prompt for a bold, high-CTR thumbnail (no text in image)",
            },
        }
        data = self.complete_json(system, json.dumps(user, ensure_ascii=False), max_tokens=1200)
        data.setdefault("title", context.get("title") or "AI Song")
        data.setdefault("description", "")
        data.setdefault("tags", [])
        data.setdefault("hashtags", [])
        data.setdefault("thumbnail_prompt", "bold cinematic music thumbnail, dramatic lighting, high contrast")
        return data

    def _json_rule(self) -> str:
        return "Respond with ONLY a valid JSON object."


# ---------------------------------------------------------------------------
# AI scene-prompt writing (used for video/image generation prompts — NO
# hardcoded template prompts: the active LLM writes every prompt)
# ---------------------------------------------------------------------------

def scene_prompt_messages(scenes: list, style_bible: dict, idea: str, genre: str):
    """Return (system, user) messages asking the LLM for per-scene prompts."""
    system = (
        "You are a senior cinematographer and prompt engineer for modern "
        "text-to-image / text-to-video models (SDXL, Flux, LTX-Video, Wan). "
        "Write ONE production-ready prompt per scene.\n"
        "PROMPT FORMULA - every prompt must contain, in this order:\n"
        "1. SHOT & LENS matched to the shot type: wide=18-24mm establishing with "
        "foreground-midground-background layers; medium=35-50mm with shallow "
        "depth of field; close-up=85-100mm portrait with bokeh.\n"
        "2. SUBJECT ACTION grounded in that scene's lyric line - what the "
        "character concretely DOES (climbing, lighting a lamp, bowing, turning).\n"
        "3. CHARACTER CONTINUITY: copy the character's prompt_token description "
        "word-for-word (same wardrobe, same look) in every scene they appear in.\n"
        "4. ENVIRONMENT + LIGHTING: a motivated light source (low golden sun and "
        "god rays, flickering diya flames, cool moonlight), atmospheric haze or "
        "particles where fitting.\n"
        "5. MOOD + PALETTE words from the visual style; end with film-grade quality "
        "tags (cinematic still, 35mm film grain, ultra-detailed).\n"
        "VARIETY RULES: 45-75 words; consecutive scenes must differ in camera angle "
        "AND location detail; no abstract poetry, no quotes, no text/watermark.\n"
        "MOTION: pick per scene, never the same motion twice in a row.\n"
        "NEGATIVE per scene, at least: text, watermark, logo, deformed hands, "
        "extra limbs, low quality, oversaturated.\n"
        "Respond ONLY with JSON: {\"prompts\": [{\"index\": 0, \"prompt\": \"...\", "
        "\"negative\": \"...\", \"motion\": \"slow_zoom_in|slow_zoom_out|pan_left|"
        "pan_right|static\"}]}"
    )
    payload = {
        "idea": idea or "",
        "genre": genre or "",
        "visual_style": (style_bible or {}).get("visual_style", ""),
        "characters": [{"name": c.get("name"), "prompt_token": (c.get("prompt_token") or c.get("description") or "")}
                       for c in (style_bible or {}).get("characters", []) if c.get("name")],
        "scenes": [{"index": s.get("index", i), "section": s.get("section", ""),
                    "lyric_line": s.get("lyrics_text", ""), "shot": s.get("shot", ""),
                    "draft_description": s.get("description", "")}
                   for i, s in enumerate(scenes)],
    }
    import json as _json
    user = "Song brief:\n" + _json.dumps(payload, ensure_ascii=False)
    return system, user
