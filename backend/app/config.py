"""SongForge backend configuration (env-driven, local-first defaults)."""
import os
from pathlib import Path

def _bool(v, d=False):
    if v is None:
        return d
    return str(v).strip().lower() in ("1", "true", "yes", "on")

def _load_dotenv(path):
    """Tiny .env loader (KEY=VALUE lines) — no extra dependency."""
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass


class Settings:
    def __init__(self):
        root = Path(__file__).resolve().parent.parent
        _load_dotenv(root / ".env")
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "8000"))
        self.data_dir = Path(os.getenv("DATA_DIR", root / "data")).resolve()
        self.db_url = os.getenv("DATABASE_URL", f"sqlite:///{self.data_dir / 'songforge.db'}")
        self.storage_dir = self.data_dir / "projects"
        self.fonts_dir = Path(os.getenv("FONTS_DIR", root / "fonts"))

        # --- AI providers ("auto" = prefer real local provider, fall back to built-in mock) ---
        self.llm_provider = os.getenv("LLM_PROVIDER", "auto")        # ollama | free | openai | mock | auto
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1")
        # Free AI (free-tier keys: groq | gemini | openrouter, or any custom endpoint)
        self.free_llm_preset = os.getenv("FREE_LLM_PRESET", "groq")
        self.free_llm_api_key = os.getenv("FREE_LLM_API_KEY", "")
        self.free_llm_base_url = os.getenv("FREE_LLM_BASE_URL", "")
        self.free_llm_model = os.getenv("FREE_LLM_MODEL", "")
        # Local HuggingFace Transformers (offline NLP: gpt-neo LLM, sentiment, summarization)
        self.hf_llm_model = os.getenv("HF_LLM_MODEL", "EleutherAI/gpt-neo-125M")
        self.nlp_enabled = os.getenv("NLP_ENABLED", "")          # "1" forces NLP on
        self.nlp_auto = os.getenv("NLP_AUTO", "0") == "1"        # auto-on if transformers installed
        # AI song generation — MusicGen (audiocraft model via transformers, free)
        self.music_provider = os.getenv("MUSIC_PROVIDER", "auto")   # musicgen | synth | auto
        self.musicgen_model = os.getenv("MUSICGEN_MODEL", "facebook/musicgen-small")
        self.musicgen_seconds = int(os.getenv("MUSICGEN_SECONDS", "20"))
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.llm_temperature = float(os.getenv("LLM_TEMPERATURE", "0.9"))

        self.image_provider = os.getenv("IMAGE_PROVIDER", "auto")    # openmontage | comfyui | placeholder | auto
        self.comfy_url = os.getenv("COMFY_URL", "http://localhost:8188")
        self.comfy_workflow = os.getenv("COMFY_WORKFLOW", "")        # optional path to workflow JSON
        self.image_width = int(os.getenv("IMAGE_WIDTH", "1280"))
        self.image_height = int(os.getenv("IMAGE_HEIGHT", "720"))

        self.aligner = os.getenv("ALIGNER", "auto")                  # whisperx | estimate | auto
        self.whisperx_model = os.getenv("WHISPERX_MODEL", "small")
        self.asr_provider = os.getenv("ASR_PROVIDER", "auto")        # faster-whisper | mock | auto
        self.asr_model = os.getenv("ASR_MODEL", "base")
        self.video_provider = os.getenv("VIDEO_PROVIDER", "auto")    # char-animated | comfyui | ffmpeg | auto
        self.comfy_video_workflow = os.getenv("COMFY_VIDEO_WORKFLOW", "")  # API-format workflow JSON
        # character animation via facebookresearch/AnimatedDrawings (free, MIT)
        self.char_anim_repo = os.getenv("CHAR_ANIM_REPO", "")        # path to the cloned repo
        self.char_anim_python = os.getenv("CHAR_ANIM_PYTHON", "")    # python that has its deps (default: this env)
        # OpenMontage (github.com/calesthio/OpenMontage) — agentic open-source video studio
        self.openmontage_repo = os.getenv("OPENMONTAGE_REPO", "")      # path to the cloned repo
        self.openmontage_engine = os.getenv("OPENMONTAGE_ENGINE", "ltx2-local")
        self.openmontage_python = os.getenv("OPENMONTAGE_PYTHON", "")  # python with diffusers
        # diffusers-based video models (SVD / AnimateDiff / LTX-Video / CogVideoX / Wan)
        self.video_diffusers_model = os.getenv("VIDEO_DIFFUSERS_MODEL", "")   # svd|animatediff|ltx|cogvideox|wan
        self.video_diffusers_python = os.getenv("VIDEO_DIFFUSERS_PYTHON", "") # python with diffusers installed
        self.video_diffusers_steps = int(os.getenv("VIDEO_DIFFUSERS_STEPS", "25"))
        self.video_diffusers_guidance = float(os.getenv("VIDEO_DIFFUSERS_GUIDANCE", "3.5"))
        # workflow defaults: extracted lyrics are auto-approved (edit + re-approve anytime)
        self.auto_approve_lyrics = os.getenv("AUTO_APPROVE_LYRICS", "1") == "1"

        # --- media / rendering ---
        self.ffmpeg_bin = os.getenv("FFMPEG_BIN", "ffmpeg")
        self.ffprobe_bin = os.getenv("FFPROBE_BIN", "ffprobe")
        self.subtitle_font = os.getenv("SUBTITLE_FONT", "Noto Sans Devanagari")
        self.render_crf = int(os.getenv("RENDER_CRF", "20"))
        self.render_preset = os.getenv("RENDER_PRESET", "veryfast")

        # --- youtube ---
        self.youtube_client_id = os.getenv("YOUTUBE_CLIENT_ID", "")
        self.youtube_client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "")
        self.youtube_redirect_uri = os.getenv(
            "YOUTUBE_REDIRECT_URI", f"http://localhost:{self.port}/api/youtube/callback")

        # Hard safety guard. Uploads happen ONLY through the explicit
        # "Approve & Upload" endpoint after the user's final approval.
        self.auto_upload_enabled = False

SETTINGS = Settings()
