"""Cinematic prompt engine — turns a scene row into a modern image-model prompt.

Structure follows current SD/SDXL/Flux practice: camera + subject + concrete
metaphor imagery + environment + lighting arc + palette + style + quality
boosters, plus a strong shared negative. Fully deterministic (no API needed)
so it upgrades mock, Ollama and cloud LLM storyboards alike.
"""
import re

from ..models import PJ

# lyric keywords (en + devanagari) -> concrete visual clause
_METAPHOR = [
    (("mountain", "पर्वत", "पहाड़", "rise"), "a lone figure ascending Himalayan peaks through drifting mist"),
    (("flame", "दीप", "ज्योति", "जल"), "a burning ember torch casting warm sparks into the dark"),
    (("river", "नदी", "cross"), "a traveler crossing a glacial river on wet stones, spray in the air"),
    (("ocean", "समुद्र", "सागर", "wave"), "vast moonlit ocean waves crashing against timeless cliffs"),
    (("light", "रोशनी", "ज्योति", "sun"), "god-rays breaking through storm clouds onto the land below"),
    (("night", "रात", "dark", "अंधेर"), "deep indigo night lit by a canopy of stars and fireflies"),
    (("home", "घर", "compass", "path", "रास्ता"), "a winding lantern-lit path leading toward a distant glowing village"),
    (("faith", "भक्ति", "प्रार्थना", "pray"), "hands folded in prayer, incense smoke curling in a sunbeam"),
    (("dance", "नृत्य", "नाच"), "dynamic dancer mid-spin, fabric and dust catching the light"),
    (("forest", "जंगल", "वन"), "primeval forest with towering trees and volumetric fog"),
]

# lighting arc by section kind (verse / chorus / bridge / intro / outro)
_LIGHT = {
    "verse": ["soft dawn haze, cool blue-gold grade", "gentle overcast light, silver mist",
              "warm late-afternoon sun, long soft shadows"],
    "chorus": ["epic golden-hour god rays, glowing atmosphere", "radiant sunset blaze with warm rim light",
               "brilliant sunlit grandeur, luminous haze"],
    "bridge": ["moody chiaroscuro, dramatic storm light", "moonlit blue night with soft haze",
               "dim ember-lit darkness with a single warm glow"],
    "intro": ["pre-dawn stillness, pale gradient sky", "quiet morning fog, muted pastel tones"],
    "outro": ["serene dusk afterglow, amber-to-violet sky", "fading twilight, first stars appearing"],
}

_CAM = {
    "wide": "sweeping wide establishing shot, 24mm, layered landscape depth",
    "medium": "medium shot, 50mm, shallow depth of field",
    "close-up": "intimate close-up, 85mm portrait lens, razor-thin focus",
    "aerial": "aerial drone view, high vantage, vast parallax",
    "low": "low-angle hero shot, dramatic perspective",
}

_QUALITY = "ultra-detailed, cinematic composition, volumetric atmosphere, sharp focus, subtle film grain"

_NEG_BASE = ("blurry, low quality, jpeg artifacts, watermark, signature, text, logo, "
             "deformed anatomy, extra fingers, mutated hands, oversaturated, flat lighting, "
             "cropped subject, duplicate")

_meta_re = re.compile(r"(shot\s*[—-]|visualising the line|featuring)", re.I)


def _kind_of(section_name: str) -> str:
    low = (section_name or "").lower()
    if "chorus" in low:
        return "chorus"
    if "bridge" in low:
        return "bridge"
    if "intro" in low:
        return "intro"
    if "outro" in low:
        return "outro"
    return "verse"


def _subject_from_lyrics(lyrics_text: str) -> str:
    """Map a lyric line to concrete imagery via the metaphor table."""
    low = (lyrics_text or "").lower()
    for keys, clause in _METAPHOR:
        if any(k in low for k in keys):
            return clause
    return ""


def _clean_description(desc: str) -> str:
    """Strip meta/template phrasing, keep the visual content."""
    parts = _meta_re.split(desc or "")
    text = desc or ""
    text = re.sub(r"(?i)visualising the line[^;]*", "", text)
    text = re.sub(r"(?i)featuring[^;]*", "", text)
    text = re.sub(r"(?i)^(wide|medium|close-up|low|aerial)?\s*shot\s*[—-]\s*", "", text).strip()
    return text.strip(" ;,") or text


def enhance_prompt(scene, style_bible: dict, idx: int = 0) -> tuple:
    """Return (rich_prompt, strong_negative) for a scene (row or dict)."""
    get = (lambda k, d="": scene.get(k, d)) if isinstance(scene, dict) else \
          (lambda k, d="": getattr(scene, k, d) or d)
    shot = (get("shot") or "medium").lower()
    section = get("section") or ""
    kind = _kind_of(section)
    style = (style_bible or {}).get("visual_style", "cinematic")
    palette = (style_bible or {}).get("color_palette") or []

    subject = _subject_from_lyrics(get("lyrics_text"))
    if not subject:
        subject = _clean_description(get("description") or get("prompt") or "")

    cam = _CAM.get(shot, _CAM["medium"])
    lights = _LIGHT[kind]
    light = lights[idx % len(lights)]
    pal = ("color story " + " ".join(palette[:3])) if palette and idx % 2 == 0 else ""

    bits = [f"{cam} — {subject.strip(',. ')}", light]
    if pal:
        bits.append(pal)
    bits.append(style)
    bits.append(_QUALITY)
    prompt = ", ".join(b for b in bits if b)
    prompt = re.sub(r"\s+", " ", prompt).strip()
    prompt = prompt.replace("—,", "—")

    neg = ", ".join([_NEG_BASE] + [x for x in [(style_bible or {}).get("global_negative", "")] if x])
    return prompt[:1800], neg[:500]


def enhance_storyboard_prompts(scenes, style_bible: dict) -> int:
    """Rewrite scene prompts in place (Scene rows). Returns count updated."""
    n = 0
    for i, sc in enumerate(scenes):
        p, neg = enhance_prompt(sc, style_bible, i)
        if isinstance(sc, dict):
            sc["prompt"], sc["negative"] = p, neg
        else:
            sc.prompt = p[:2000]
            sc.negative = neg[:500]
        n += 1
    return n
