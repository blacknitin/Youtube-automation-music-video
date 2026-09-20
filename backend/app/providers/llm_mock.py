"""Offline rule-based LLM — lets the whole pipeline run with zero external
services (great for development and for testing the full workflow).

It produces template-based Hindi (or English) lyrics, a section-aware
storyboard, heuristic feedback interpretation and YouTube metadata.
"""
import re

from .base import LLMProvider, LyricRequest, AnalysisSummary

# ---------------------------- lyric templates --------------------------------
DEVOTIONAL = {
    "title": ["शंखनाद", "दिव्य ज्योति", "भक्ति की गंगा", "जय जय जयकारा"],
    "intro": ["॥ जय हो जय हो जय हो ॥"],
    "verses": [
        ["हिमालय की ऊँचाइयों से गूँजता है नाम तेरा",
         "भक्त के मन मंदिर में जलता है दीप एक परा",
         "शंख की ध्वनि संग जो शांति का संदेश आया",
         "तेरे चरणों में झुक गया जग सारा"],
        ["मुश्किलें जब घेर लें, तू ही सहारा है",
         "तेरे नाम से ही यह हृदय निराला है",
         "जो तेरी राह में झुके, उसका हाल क्या बिगड़े",
         "तू ही मालिक, तू ही दुलारा है"],
    ],
    "chorus": ["जय जय जयकारा हो, नाम तेरा भारा हो",
               "भक्ति के इस सागर में हम भी उतर जाएँ",
               "जय जय जयकारा हो, दिल से पुकारा हो",
               "तेरी कृपा के साए में हम भी मुस्कुराएँ"],
    "chorus2": ["जय हो जय हो जय हो, नाम सुमिरन कर",
                "भक्ति की इस धारा में बहते हम रहें",
                "जय हो जय हो जय हो, शरण तेरी हम धरें",
                "तेरा नाम सुन ये आँखें भीगी रहें"],
    "verses3": [
        ["सुन ले मेरी पुकार, हे प्रभु के प्यारे",
         "डाल दो आशीर्वाद यही, सिर पे हमारे",
         "जो दुख सताए जग में, वो दूर हो जाए",
         "तेरे नाम के पंख लगा, मैं तो उड़ जाऊँ"],
    ],
    "bridge": ["भक्ति की ये धारा, बहती रहे संसार में"],
    "outro": ["॥ जय हो ॥"],
}
ROMANTIC = {
    "title": ["चाँदनी रातें", "दिल की डोर", "तेरे ख्वाब", "पहली मुलाक़ात"],
    "intro": ["हम्म… तेरे बारे में सोचता हूँ…"],
    "verses": [
        ["चाँदनी की रातों में तेरा नाम लिख गया",
         "टूटे ख्वाबों की गली में खुशी का दीया जला",
         "तेरी हँसी की धुन पे जो दिल भी था मुस्कुराया",
         "ये लम्हा भी क्या लम्हा है, मैं क्या से क्या बन गया"],
        ["रातों की बातों के साए अब पुराने हो गए",
         "तेरे बिन लगे जो मौसम, अब सुहाने हो गए",
         "दिल ने कहा जो एक दिन, तूने सुन भी लिया",
         "जो टूटा था सितारा, फिर से जवाँ हो गया"],
    ],
    "chorus": ["तू है तो मैं हूँ, ये गीत तेरा ही है",
               "धड़कनों में बसा जो सपना वही सच होगा",
               "तू है तो मैं हूँ, ये सफ़र तेरा ही है",
               "चाहे जो भी हो दूरी, मैं तेरे पास ही रहूँगा"],
    "chorus2": ["तेरे संग तेरे संग, हर सुबह हर शाम",
                "जो धड़के दिल में छुपी, वो तुझको सुना दूँ",
                "तेरे संग तेरे संग, ये वादा रहे",
                "जहाँ तू वहाँ मैं, बस यूँ ही रहें"],
    "verses3": [
        ["तेरी आँखों के पानी में बरसातें बसती हैं",
         "तेरे चेहरे की हसी में ये बातें बसती हैं",
         "जो लम्हे हमने गँवाए, वो गीत बन जाएँगे",
         "जो अधूरे थे सपने, वो पूरे हो जाएँगे"],
    ],
    "bridge": ["तेरे नाम की ये धुन, बजती रहे हर सुबह"],
    "outro": ["तेरे बारे में सोचता हूँ…"],
}
MOTIVATIONAL = {
    "title": ["उड़ान", "हौसले बुलंद", "राख से चाँद", "आगे बढ़ेंगे"],
    "intro": ["ये कहानी है हिम्मत की…"],
    "verses": [
        ["मुश्किलें तो आएँगी, हौसले बुलंद रख",
         "राहों में अंधेरा हो तो दिल में चाँद रख",
         "जो टूट के बिखर गए, वो फिर से जुड़ेंगे",
         "अपने सपनों के ये दीप, तू हवा में जला रख"],
        ["गिरते हैं तो उठना भी तो क़िस्सा है ज़िंदगी का",
         "ख़्वाब बड़े बुनने हैं तो धागे चुन ले अपने",
         "राख से उगा है चाँद, यकीन रख अपने ऊपर",
         "तू वो दीया है जो अंधेरों में जलता है"],
    ],
    "chorus": ["उड़ चलें आसमाँ पे, हौसले हैं जब यारो",
               "राख से चाँद बनेंगे, मानो ना मानो",
               "उड़ चलें आसमाँ पे, हौसले हैं जब यारो",
               "हार के जीतने वाले, खिताब हम ही को मिलेगा"],
    "bridge": ["हिम्मत की ये आग, जलती रहे हर ओर"],
    "outro": ["ये कहानी अभी बाक़ी है…"],
}
EN_FALLBACK = {
    "title": ["Neon Dreams", "Afterglow", "Rise Again"],
    "intro": ["(humming)…"],
    "verses": [
        ["City lights are calling out my name tonight",
         "Every broken road has taught me how to fight",
         "Shadows on the wall, they whisper, hold on tight",
         "I will rise again, like morning after night"],
        ["Every scar I carry is a story that I own",
         "Every quiet tear has grown a seed I've sown",
         "When the world gets heavy, I won't walk alone",
         "Deep inside my heart I've built a solid home"],
    ],
    "chorus": ["We will rise, we will shine, we will light the sky",
               "Nothing's gonna break the flame that will never die",
               "We will rise, we will shine, hand in hand we fly",
               "Dreams we chase tonight will echo through the time"],
    "bridge": ["This fire in my soul keeps burning on"],
    "outro": ["(fade out)…"],
}

DEV_WORDS = re.compile(r"hanuman|हनुमान|bajrang|शिव|shiv|mahadev|महादेव|krishna|कृष्ण|rama?|राम|mata|माता|devi|देवी|bhakti|भक्ति|mandir|मंदिर|bhajan|भजन|aarti|आरती|god|भगवान", re.I)
ROM_WORDS = re.compile(r"pyaar|प्यार|ishq|इश्क|mohabbat|मोहब्बत|dil|दिल|love|romantic|चाँद|chaand|yaad|याद|girl|boy|ladka|ladki", re.I)

def _pick(rng, arr):
    return arr[int(rng.randrange(len(arr)))]

class MockLLMProvider(LLMProvider):
    name = "mock"

    # ---- lyrics ----
    def generate_lyrics(self, req: LyricRequest) -> dict:
        import random
        rng = random.Random()  # unseeded -> every generation is a fresh variation
        if req.language.startswith("en"):
            bank = EN_FALLBACK
        elif DEV_WORDS.search(req.idea):
            bank = DEVOTIONAL
        elif ROM_WORDS.search(req.idea):
            bank = ROMANTIC
        else:
            bank = MOTIVATIONAL
        title = req.title_hint.strip() or _pick(rng, bank["title"])
        # pick 2 distinct verses out of the available pool (3 for Hindi banks)
        verse_pool = list(bank["verses"]) + list(bank.get("verses3", []))
        verses = rng.sample(verse_pool, k=min(2, len(verse_pool)))
        chorus = bank["chorus"] if rng.random() < 0.5 else bank.get("chorus2", bank["chorus"])
        v1, v2 = verses[0], verses[1]
        sections = [
            {"name": "Intro", "type": "intro", "lines": bank["intro"]},
            {"name": "Verse 1", "type": "verse", "lines": list(v1)},
            {"name": "Chorus", "type": "chorus", "lines": list(chorus)},
            {"name": "Verse 2", "type": "verse", "lines": list(v2)},
            {"name": "Chorus", "type": "chorus", "lines": list(chorus)},
            {"name": "Bridge", "type": "bridge", "lines": bank["bridge"]},
            {"name": "Chorus", "type": "chorus", "lines": list(chorus)},
            {"name": "Outro", "type": "outro", "lines": bank["outro"]},
        ]
        return {"title": title, "language": req.language, "sections": sections}

    # ---- storyboard ----
    LOCATION_POOLS = {
        "devotional": ["ancient stone temple on a Himalayan cliff at golden hour",
                       "misty river ghat with hundreds of floating oil lamps",
                       "sunlit forest clearing with marigold petals in the wind",
                       "grand temple courtyard during evening aarti, bells swinging"],
        "romantic": ["rain-soaked city street glowing with warm streetlights",
                     "rooftop terrace at dusk with paper lanterns",
                     "quiet beach at sunrise with soft golden waves",
                     "old bookshop cafe with dust motes in window light"],
        "default": ["winding mountain road above clouds at sunrise",
                    "vast desert dunes under a purple twilight sky",
                    "neon-lit rooftop overlooking a sleeping city",
                    "open wheat field swaying under a stormy golden sky"],
    }
    ACTION_POOLS = {
        "devotional": ["a lone devotee climbs stone steps with folded hands",
                       "close-up of hands lighting a brass oil lamp",
                       "saffron flags flutter against dramatic clouds",
                       "crowd sways together, eyes closed, bathed in warm light"],
        "romantic": ["two silhouettes share an umbrella under the rain",
                     "close-up of a smile reflected in a raindrop-covered window",
                     "a handwritten letter is folded beside a cup of chai",
                     "the couple walks away down a lamp-lit lane"],
        "default": ["the hero stands on a cliff edge, coat flapping in wind",
                    "determined close-up, eyes reflecting sunrise",
                    "crowd of dreamers walking toward the light",
                    "hands release a paper lantern into the night sky"],
    }

    def generate_scene_prompts(self, scenes: list, style_bible: dict, idea: str, genre: str) -> list:
        """Offline writer: builds each prompt from the scene's OWN description,
        camera and section mood (no external service, no unrelated templates)."""
        style = (style_bible or {}).get("visual_style", "cinematic")
        cam = {"wide": "sweeping wide shot, 24mm", "medium": "medium shot, 50mm, shallow depth of field",
               "close-up": "close-up, 85mm lens", "aerial": "aerial view, vast parallax",
               "low": "low-angle hero shot"}
        light = {"verse": "soft natural light, cool grade", "chorus": "epic golden-hour glow, warm rim light",
                 "bridge": "moody dramatic light", "intro": "quiet pre-dawn light",
                 "outro": "serene dusk afterglow"}
        move = {"slow_zoom_in": "gentle push-in on the subject", "slow_zoom_out": "slow reveal pull-back",
                "pan_left": "smooth left pan across the scene", "pan_right": "smooth right pan across the scene",
                "static": "locked-off steady frame"}
        def kind(section):
            s = (section or "").lower()
            for k in ("chorus", "bridge", "intro", "outro"):
                if k in s: return k
            return "verse"
        import re as _re
        out = []
        for i, s in enumerate(scenes):
            desc = _re.sub(r"(?i)^(wide|medium|close-up|low|aerial)\s*shot\s*[—\-]\s*",
                           "", (s.get("description") or "")).strip(" ;,")
            k = kind(s.get("section"))
            prompt = (f"{cam.get((s.get('shot') or 'medium').lower(), cam['medium'])} of {desc}, "
                      f"{move.get(s.get('motion', 'slow_zoom_in'), move['slow_zoom_in'])}, "
                      f"{light[k]}, {style}, ultra-detailed, cinematic composition, sharp focus")
            out.append({"index": s.get("index", i), "prompt": prompt[:1000],
                        "negative": "blurry, low quality, watermark, text, deformed anatomy, extra limbs",
                        "motion": s.get("motion", "slow_zoom_in")})
        return out

    def generate_storyboard(self, lyrics, analysis: AnalysisSummary, visual_style: str, idea: str) -> dict:
        import random
        rng = random.Random(idea)
        all_text = (idea or "") + " " + " ".join(l.get("lines", [])[0] if l.get("lines") else "" for l in lyrics.get("sections", []))
        key = "devotional" if DEV_WORDS.search(all_text) else "romantic" if ROM_WORDS.search(all_text) else "default"
        style = visual_style or ("epic cinematic devotional painting, golden light, intricate detail" if key == "devotional"
                                 else "cinematic film look, shallow depth of field, warm teal-orange grade")
        style_bible = {
            "visual_style": style,
            "color_palette": ["#f59e0b", "#7c2d12", "#1e293b", "#fef3c7"],
            "characters": [{"name": "Protagonist", "description": "the singer/hero of the song",
                            "prompt_token": "heroic protagonist, expressive eyes, detailed costume"}],
            "locations": [f"a {loc}" for loc in self.LOCATION_POOLS[key][:3]],
            "global_negative": "blurry, low quality, watermark, text, deformed hands, extra limbs",
        }
        # character detection
        char_map = {"hanuman": "Hanuman", "हनुमान": "Hanuman", "shiv": "Shiva", "mahadev": "Shiva",
                    "महादेव": "Shiva", "krishna": "Krishna", "कृष्ण": "Krishna", "rama": "Rama", "राम": "Rama"}
        low = all_text.lower()
        seen = set()
        for token, name in char_map.items():
            if token in low and name not in seen:
                seen.add(name)
                style_bible["characters"].append({
                    "name": name, "description": f"{name} as depicted in the song",
                    "prompt_token": f"{name}, divine presence, traditional iconography, consistent face"})
        scenes, idx = [], 0
        dur = analysis.duration or 180.0
        for sec in lyrics.get("sections", []):
            lines = [l for l in sec.get("lines", []) if str(l).strip()]
            t = sec.get("type", "verse")
            if t in ("intro", "outro", "bridge"):
                line_groups = [lines[:1]]  # single establishing scene
            else:
                line_groups = [[l] for l in lines]  # ONE SCENE PER LYRIC LINE
            for line in line_groups:
                # location: match the lyric's own imagery first, else rotate
                # (no fixed stride -> neighbouring scenes never repeat)
                low_l = lytext.lower() if 'lytext' in dir() else ""
                loc = self.LOCATION_POOLS[key][idx % len(self.LOCATION_POOLS[key])]
                act = self.ACTION_POOLS[key][(idx * 3 + 1) % len(self.ACTION_POOLS[key])]
                lytext = line[0] if line else ""
                low_l = (lytext or "").lower()
                kw_map = [("mountain", "ancient stone temple on a Himalayan cliff at golden hour"),
                          ("river", "misty river ghat with hundreds of floating oil lamps"),
                          ("ocean", "moonlit ocean ghat with waves and floating diyas"),
                          ("flame", "grand temple courtyard during evening aarti, bells swinging"),
                          ("night", "temple steps at night under a canopy of stars and oil lamps"),
                          ("light", "sunlit temple terrace with god-rays through incense smoke")]
                for kw, hero_loc in kw_map:
                    if kw in low_l:
                        loc = hero_loc
                        break
                shot = ["wide", "medium", "close-up", "medium"][idx % 4]
                motion = ["slow_zoom_in", "pan_right", "slow_zoom_out", "pan_left"][idx % 4]
                desc = f"{shot.capitalize()} shot — {loc}; {act}"
                if seen:
                    desc += f"; featuring {', '.join(sorted(seen))}"
                if lytext:
                    desc += f"; visualising the line \"{lytext[:80]}\""
                scenes.append({
                    "section": sec.get("name", ""), "lyrics_text": lytext, "description": desc,
                    "prompt": f"{desc}, {style}", "negative": "", "shot": shot, "motion": motion})
                idx += 1
        return {"style_bible": style_bible, "scenes": scenes}

    # ---- feedback ----
    def interpret_feedback(self, text: str, context: dict) -> dict:
        low = text.lower()
        scenes = context.get("scenes", [])
        ops, summary = [], []
        m = re.findall(r"scene\s*#?(\d+)", low)
        targets = set()
        for n in m:
            i = int(n) - 1
            if 0 <= i < len(scenes):
                targets.add(scenes[i]["id"])
        patch = {}
        if any(w in low for w in ("emotion", "emotional", "sad", "दुख", "भावुक")):
            patch["prompt_adjust"] = "more emotional, tearful expressions, softer melancholic light, slow rain, warm rim light"
            summary.append("heightened emotion: lighting + expression cues")
        if "realistic" in low or "असली" in low:
            patch["prompt_adjust"] = "photorealistic, ultra detailed skin and fabric texture, natural lighting, 50mm lens"
            summary.append("switch affected scenes to a photorealistic look")
        if "background" in low or "पृष्ठभूमि" in low:
            patch["prompt_adjust"] = "changed background: new environment keeping the subject and story"
            summary.append("replace backgrounds")
        if "bright" in low or "उजाला" in low:
            patch["prompt_adjust"] = "brighter airy lighting, sunlit frame"
        if "dark" in low or "अंधेरा" in low or "night" in low:
            patch["prompt_adjust"] = "darker moody night lighting, deep shadows, moonlight"
        if not targets:
            if patch:
                targets = {s["id"] for s in scenes}
            else:
                targets = {s["id"] for s in scenes[:1]}
                patch["prompt_adjust"] = patch.get("prompt_adjust", "general polish: better composition and detail")
        for sid in targets:
            op = {"op": "scene_image", "scene_id": sid}
            op.update(patch)
            ops.append(op)
        return {"summary": "; ".join(summary) or "applied your note to the affected scenes",
                "ops": ops}

    # ---- metadata ----
    def generate_metadata(self, ctx: dict) -> dict:
        title_hint = ctx.get("title") or ctx.get("idea") or "AI Song"
        mood = ctx.get("mood") or "Emotional"
        genre = ctx.get("genre") or "Hindi Song"
        title = f"{title_hint} | {mood} {genre} (Official AI Music Video)"[:100]
        lyrics = ctx.get("lyrics") or ""
        first_lines = "\n".join([l for l in lyrics.splitlines() if l.strip()][:6])
        description = (f"🎬 {title_hint} — an AI-crafted {genre.lower()} created 100% locally with SongForge.\n\n"
                       f"🎶 Lyrics (excerpt):\n{first_lines}\n\n"
                       "✨ Made with a fully local pipeline: Ollama lyrics, ComfyUI art, FFmpeg render.\n"
                       "Lyrics, music and visuals generated with AI assistance. Like & subscribe for more!\n\n")
        tags = ["hindi song", "ai music", genre.lower(), mood.lower(), "ai generated song",
                "hindi gaana", "new hindi song 2026", "local ai", "songforge", "music video",
                "bhakti song" if DEV_WORDS.search(title_hint + lyrics) else "emotional song",
                "ai music video", "generated music", "hindi lyrics", "official video"]
        hashtags = ["#hindisong", "#aimusic", "#musicvideo", "#aigenerated", "#newmusic", "#songforge"]
        thumbnail_prompt = ("bold cinematic YouTube thumbnail, dramatic key art, glowing title area, "
                            "high contrast, emotional hero shot, no text")
        return {"title": title, "description": description, "tags": tags,
                "hashtags": hashtags, "thumbnail_prompt": thumbnail_prompt}
