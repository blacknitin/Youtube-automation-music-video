"""HuggingFace Transformers NLP — local, free lyric intelligence.

Models (all free, downloaded once from the HF Hub on first use):
  sentiment  nlptown/bert-base-multilingual-uncased-sentiment
             (github.com/nlptown/BERT-base-multilingual-uncased-sentiment)
             1-5 star sentiment in 6 languages incl. English; used to derive
             the song's mood automatically from its lyrics.
  summary    t5-small — summarization used for the storyboard's story logline.

Everything here is optional: if `transformers` isn't installed the app runs
exactly as before. Enable with  NLP_ENABLED=1  (or install transformers and
set NLP_AUTO=1).
"""
import os

from ..config import SETTINGS

_SENTIMENT_MODEL = "nlptown/bert-base-multilingual-uncased-sentiment"
_SUMMARY_MODEL = "t5-small"

# star rating -> mood tag used by storyboard + metadata
MOOD_BY_STARS = {
    1: "melancholy", 2: "emotional", 3: "heartfelt", 4: "uplifting", 5: "euphoric",
}

# Devotional/worship vocabulary — nlptown is review-trained, so praise words
# floor the star rating (a bhajan is never "melancholy" because it isn't a
# 5-star product review). Multi-language incl. Hindi (Devanagari) + translit.
_DEVOTIONAL_WORDS = (
    "भक्ति", "जय", "हर हर", "ओम", "प्रभु", "भगवान", "राम", "कृष्ण", "हनुमान",
    "शिव", "राधे", "श्याम", "गोविंद", "दर्शन", "आरती", "भजन", "दीया", "दीप",
    "bhakti", "jay", "jai", "om", "prabhu", "bhagwan", "ram", "krishna",
    "hanuman", "shiva", "radhe", "shyam", "darshan", "aarti", "bhajan", "diya",
    "lord", "god", "divine", "temple", "pray", "prayer", "bless", "soul",
)


def _pipe(task: str, model: str):
    from transformers import pipeline
    return pipeline(task, model=model)


def transformers_available() -> bool:
    try:
        import transformers  # noqa: F401
        return True
    except Exception:
        return False


def nlp_enabled() -> bool:
    if not transformers_available():
        return False
    flag = (SETTINGS.nlp_enabled or ("1" if SETTINGS.nlp_auto else "")).lower()
    return flag in ("1", "true", "yes", "on", "auto")


class HuggingFaceNLP:
    """Lazy-loading local NLP: sentiment->mood and summarization."""
    name = "hf-nlp"

    def __init__(self):
        self._sent = None
        self._summ = None

    def sentiment_mood(self, text: str) -> dict | None:
        """Return {'stars': 1-5, 'mood': 'uplifting', 'confidence': 0.0-1.0}."""
        if not text or not text.strip():
            return None
        try:
            if self._sent is None:
                self._sent = _pipe("text-classification", model=_SENTIMENT_MODEL)
            out = self._sent(text[:2000], truncation=True)[0]
            stars = int(out["label"][0])  # labels look like "4 stars"
            conf = float(out.get("score", 0.0))
            low = text.lower()
            if any(w in low for w in _DEVOTIONAL_WORDS):
                stars = max(stars, 3)  # praise vocabulary floors the rating
                conf = max(conf, 0.6)
            return {"stars": stars, "mood": MOOD_BY_STARS.get(stars, "emotional"),
                    "confidence": round(conf, 3)}
        except Exception as exc:
            print(f"[hf-nlp] sentiment failed: {exc}")
            return None

    def summarize(self, text: str, max_words: int = 30) -> str | None:
        """Short story/logline summary (t5-small via AutoModel — transformers
        5.x dropped the 'summarization' pipeline task name)."""
        if not text or not text.strip():
            return None
        try:
            if self._summ is None:
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
                self._summ_tok = AutoTokenizer.from_pretrained(_SUMMARY_MODEL)
                self._summ = AutoModelForSeq2SeqLM.from_pretrained(_SUMMARY_MODEL)
            words = text.split()
            inputs = self._summ_tok("summarize: " + " ".join(words[:400]),
                                    return_tensors="pt", truncation=True, max_length=512)
            ids = self._summ.generate(**inputs, max_new_tokens=max_words,
                                      min_new_tokens=8, do_sample=False)
            return self._summ_tok.decode(ids[0], skip_special_tokens=True).strip()
        except Exception as exc:
            print(f"[hf-nlp] summarize failed: {exc}")
            return None


def get_nlp() -> HuggingFaceNLP | None:
    if not nlp_enabled():
        return None
    global _nlp_instance
    try:
        return _nlp_instance
    except NameError:
        _nlp_instance = HuggingFaceNLP()
        return _nlp_instance
