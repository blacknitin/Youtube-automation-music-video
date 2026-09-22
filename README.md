# 🎵 SongForge — Local-First AI YouTube Song Studio

**Turn a song idea into a complete, ready-to-upload YouTube music video — 100% free and local.**

SongForge runs an entire production pipeline on your machine: AI lyrics → your approval → music (Suno import or a free local demo track) → audio analysis (BPM, sections, beats) → AI storyboard → scene generation → FFmpeg render with synchronized karaoke subtitles → natural-language revision ("make scene 3 more emotional") → YouTube metadata → **explicit approval** → upload.

> 🔒 **Safety first:** SongForge *never* publishes anything by itself. Uploading requires (1) your final approval of the video, (2) your approval of the metadata, and (3) a click on **Approve & Upload** with an explicit confirmation checkbox. Every stage asserts this in code.

---

## ✨ Features

| | |
|---|---|
| 📝 **AI Hindi lyrics** | Section-structured, editable, with a human **approval gate** |
| 🎵 **Music (MVP)** | Import your **Suno** MP3/WAV (or any audio), or use the built-in **free local demo track** |
| 🎚️ **Audio analysis** | Duration, BPM + beat phase, energy curve, waveform peaks, coarse sections |
| 🎬 **AI storyboard** | Style bible (characters, locations, palette) + scene list kept **consistent** across scenes |
| 🖼️ **Scene generation** | ComfyUI/Stable Diffusion locally, or automatic offline placeholder art |
| ⏱️ **Lyric sync** | WhisperX word-level alignment, or dependency-free beat-weighted estimation |
| 🎞️ **FFmpeg render** | Ken Burns motion, crossfades, burned-in **karaoke subtitles**, AAC audio, MP4/H.264 |
| 💬 **Feedback revisions** | "Change scene 3", "make it more emotional", "make Hanuman look realistic" → **only affected scenes regenerate** |
| 🗂️ **Versions** | Every storyboard approval / revision / restore creates a numbered snapshot |
| 📺 **YouTube kit** | AI title/description/tags/hashtags/thumbnail + OAuth + resumable upload (gated) |
| 🧩 **Provider system** | Every AI capability is behind an interface — swap in cloud APIs anytime |

## 🚀 Quick start (works offline, zero API keys)

```bash
cd songforge
python -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt     # Windows: backend\.venv\Scripts\pip install -r backend\requirements.txt
cd backend
../backend/.venv/bin/python -m uvicorn app.main:app --port 8000
```

Open **http://localhost:8000** → *New Song Project* → the built-in offline LLM writes template Hindi lyrics, the demo track provides music, placeholder art fills scenes, FFmpeg renders a real video. Connect the real providers below whenever you want.

> **Windows:** just run `scripts\setup.bat` once, then `scripts\run.bat`.

## 🛠️ Full setup for the best quality (all free)

### 1. FFmpeg (required for rendering)
```bat
winget install Gyan.FFmpeg        :: Windows
brew install ffmpeg               :: macOS
sudo apt install ffmpeg           :: Linux
```

### 2. Free AI — real AI prompt writing at zero cost (no install)
Paste a **free** API key and every AI step (scene video prompts, storyboard, lyrics,
feedback, YouTube metadata) runs on a real model. `auto` mode uses it whenever Ollama
isn't running — chain: `ollama → free → mock`.

| Preset | Get free key | Default model | `backend/.env` |
|---|---|---|---|
| **Groq** (fastest) | console.groq.com/keys | `llama-3.3-70b-versatile` | `FREE_LLM_PRESET=groq` + `FREE_LLM_API_KEY=gsk_…` |
| **Google Gemini** | aistudio.google.com/apikey | `gemini-3.6-flash` | `FREE_LLM_PRESET=gemini` + `FREE_LLM_API_KEY=…` |
| **OpenRouter** `:free` | openrouter.ai/keys | `meta-llama/llama-3.3-70b-instruct:free` | `FREE_LLM_PRESET=openrouter` + `FREE_LLM_API_KEY=sk-or-…` |
| Custom endpoint | any OpenAI-compatible URL | your choice | `FREE_LLM_PRESET=custom` + `FREE_LLM_BASE_URL` / `FREE_LLM_MODEL` / `FREE_LLM_API_KEY` |

### 2b. AI song generation (MusicGen — no upload needed)
The song step now has three ways to get music:
1. **Import your Suno MP3** (vocals — the recommended main path)
2. **🤖 AI compose a song (MusicGen)** — the LLM writes a music brief, then audiocraft's
   MusicGen (via transformers) composes an original instrumental locally
   (`MUSIC_PROVIDER=auto`, ~3GB RAM, GPU = fast; small machines auto-fall-back to the built-in synth)
3. **🎹 Free local demo track** — instant numpy-synth loop

All three feed the same analysis pipeline (BPM, sections, energy).
All three presets have generous free tiers — a full song (storyboard + ~10-25 scene
prompts) costs nothing. Restart SongForge after editing `.env`; the sidebar chip shows
`LLM: free (groq)` style status via **System → providers**.

### 3. Ollama — real local LLM (lyrics, storyboard, feedback, metadata)
1. Install from **https://ollama.com** (`winget install Ollama.Ollama`)
2. `ollama pull llama3.1` (any model works — `qwen2.5`, `gemma2`, …)
3. Restart SongForge. The sidebar chip flips from `LLM: mock` to `LLM: ollama`.

### 4. OpenMontage — real local AI art AND animation (Stable Diffusion / LTX / Wan)
Scene **art** and scene **animation** both come from [OpenMontage](https://github.com/calesthio/OpenMontage):

```bash
git clone https://github.com/calesthio/OpenMontage
pip install diffusers torch transformers accelerate imageio imageio-ffmpeg
# .env
OPENMONTAGE_REPO=/path/to/OpenMontage
VIDEO_PROVIDER=openmontage
```
That single install gives you: AI-written scene prompts -> local Stable Diffusion scene art
(`tools/graphics/local_diffusion`) -> per-line video chunks (LTX-2 / Wan / Hunyuan / CogVideoX)
-> automatic lyric-locked assembly. Until it is connected, SongForge uses its built-in engines
(placeholder art + FFmpeg motion) so nothing ever blocks. ComfyUI remains supported as an
alternative art/animation engine.

Original ComfyUI notes (alternative path):1. Install **https://www.comfy.org** and download an SDXL checkpoint into `ComfyUI/models/checkpoints/`
2. Run ComfyUI (default port **8188**) and restart SongForge — scenes now generate with SD.
3. Custom workflow? Export it in **API format** and set `COMFY_WORKFLOW` in `.env`, embedding the literal tokens `__PROMPT__`, `__NEGATIVE__`, `__SEED__`, `__WIDTH__`, `__HEIGHT__`.

### 5. WhisperX — word-perfect lyric sync (optional, heavy)
```bash
pip install -r backend/requirements-whisperx.txt
```
Used automatically when installed. Without it, SongForge estimates timings from beats and section structure.

### 6. faster-whisper — extract lyrics FROM a song (optional, recommended)
```bash
pip install -r backend/requirements-asr.txt
```
Powers the **Song step → "Extract lyrics from song"** button: SongForge transcribes the vocals locally,
detects the structure (Verses / repeated Chorus / Intro / Outro) and stores the exact moment every line is
sung — scenes, subtitles and the final video are then locked to the real vocal timing. Without it a clearly
labelled demo extractor is used. Multilingual (Hindi works); the `base` model (~150 MB) downloads once.

## 🎤 The Suno workflow (MVP music)

1. Complete the **Lyrics** step and approve them.
2. Open **Suno** (free tier is fine) → *Custom mode* → paste your approved lyrics → generate.
3. Download the MP3/WAV and drop it into SongForge's **Song** step.
4. Analysis (BPM/sections) and lyric alignment run automatically, then the storyboard is timed to *your* audio.

**Got a song but no lyrics?** Skip straight to the Song step, import the audio and hit **Extract lyrics from song** —
review the transcription in the Lyrics step, approve, and continue exactly as above.

**Hands-free Autopilot (default ON):** after you import a song, SongForge runs the whole chain by
itself — **extract lyrics (auto-approved) → storyboard → storyboard approval → scene art → animated
video** — each step theme-matched to the song. Toggle it with the **⚡ Autopilot** chip in the header.
Lyrics written by the AI (idea flow) still always wait for your explicit approval, and YouTube upload
always requires your final click.

**Suno loop:** in the Lyrics step, **📋 Copy for Suno** formats your lyrics with proper
`[Intro] / [Verse 1] / [Chorus] / [Bridge] / [Outro]` tags — paste into suno.ai *Custom mode*, generate,
download the MP3, import it back in the Song step. SongForge then extracts + times those same lyrics
from the finished song.

### 7. Real AI video generation — free GitHub projects (optional)
By default scenes are animated with a fast FFmpeg "Ken Burns" motion (works everywhere, no GPU).
Want real AI animation? All of these are **free & open source** and plug into the existing ComfyUI provider:

| Project | Repo | Notes |
|---|---|---|
| ComfyUI | `comfyanonymous/ComfyUI` | the engine that runs the models below |
| Stable Video Diffusion | built into ComfyUI (`svd.safetensors`) | image-to-video, the default choice |
| Wan 2.1 / 2.2 | `Wan-Video/Wan2.2` (Apache-2.0) | best quality, text+image-to-video |
| LTX-Video | `Lightricks/LTX-Video` | very fast, real-time-ish |
| AnimateDiff | `guoyww/AnimateDiff` (Apache-2.0) | animates your SD scene images |
| CogVideoX | `THUDM/CogVideoX` (Apache-2.0) | strong open weights |
| **via diffusers** | `huggingface/diffusers` | ONE engine for SVD, AnimateDiff, LTX, CogVideoX, Wan — see below |
| **OpenMontage** | `calesthio/OpenMontage` (AGPLv3) | agentic video studio — LTX-2 / Wan 2.2 / Hunyuan / CogVideoX local engines |

**OpenMontage engine:** clone [OpenMontage](https://github.com/calesthio/OpenMontage), install diffusers, then
```
OPENMONTAGE_REPO=/path/to/OpenMontage
VIDEO_PROVIDER=openmontage            # or auto
OPENMONTAGE_ENGINE=ltx2-local         # wan2.2-i2v-a14b | wan2.1-1.3b | hunyuan-1.5 | cogvideo-2b
```
SongForge calls its local engines in a separate process with the project's own fallback chain
(ltx2 → wan-i2v → hunyuan → cogvideo) and its usual per-scene FFmpeg safety net.

**Diffusers engine (one install, five repos):** set `VIDEO_DIFFUSERS_MODEL=svd|animatediff|ltx|cogvideox|wan`
and `VIDEO_PROVIDER=diffusers`. SongForge runs `tools/diffusers_img2vid.py` locally — no ComfyUI needed.

```bash
pip install diffusers torch transformers accelerate imageio imageio-ffmpeg
# .env
VIDEO_PROVIDER=diffusers
VIDEO_DIFFUSERS_MODEL=ltx            # or svd / animatediff / cogvideox / wan
```

Setup: run ComfyUI (same install you use for scene art), export a video graph in **API format**
with the tokens `__IMAGE__ __PROMPT__ __SEED__ __FRAMES__ __FPS__ __WIDTH__ __HEIGHT__`,
save it (a ready SVD template ships in `examples/comfyui_video_workflow_svd.json`) and set
`COMFY_VIDEO_WORKFLOW` in `.env`. SongForge then animates every scene with the open-source model
before assembling the video — and automatically falls back to FFmpeg motion for any scene where
animation fails, so a render never dies because of the AI step.

## Open-source integrations matrix

Every free/open-source repo SongForge builds on (or intentionally doesn't), and where it sits in the pipeline:

| Repo | Role in SongForge | Status |
|---|---|---|
| [librosa/librosa](https://github.com/librosa/librosa) | Audio analysis: real beat-tracked BPM, beat offset, onset-novelty sections, RMS energy | ✅ integrated (`services/audio.py`, numpy fallback) |
| [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg) | Assembly: chunk concat, crossfades, karaoke burn-in, audio mux, i2v zoompan | ✅ core engine |
| [huggingface/transformers](https://github.com/huggingface/transformers) | Local NLP: lyric sentiment → mood, summarization → story logline; offline LLM host | ✅ integrated (`providers/nlp_hf.py`, `providers/llm_hf.py`, opt-in via `NLP_AUTO=1`) |
| [nlptown/bert-base-multilingual-uncased-sentiment](https://github.com/nlptown/BERT-base-multilingual-uncased-sentiment) | Lyric sentiment (1-5★, multilingual) → auto mood tag for storyboard + metadata | ✅ integrated |
| [EleutherAI/gpt-neo](https://github.com/EleutherAI/gpt-neo) | Fully-offline keyless AI writer (`LLM_PROVIDER=hf`) — prompts/lyrics on your CPU/GPU | ✅ integrated (opt-in) |
| [byroot/pysrt](https://github.com/byroot/pysrt) | `.srt` subtitle export of the approved lyric timings | ✅ integrated (`GET /api/projects/{id}/subtitles.srt`) |
| [Zulko/moviepy](https://github.com/Zulko/moviepy) | — | ⚠️ not used: native FFmpeg assembly is faster with fewer deps |
| [jiaaro/pydub](https://github.com/jiaaro/pydub) | Audio utility for future quick edits | ✅ available (installed with `requirements-ai.txt`) |
| [slhck/ffmpeg-normalize](https://github.com/slhck/ffmpeg-normalize) | Loudness normalization | ⚠️ optional add-on if you want broadcast loudness targets |
| [CompVis/stable-diffusion](https://github.com/CompVis/stable-diffusion) | Scene ART engine (via diffusers `StableDiffusionPipeline` behind OpenMontage's LocalDiffusion / ComfyUI) | ✅ integrated by proxy (real repo → GPU) |
| [facebookresearch/audiocraft](https://github.com/facebookresearch/audiocraft) (MusicGen) | **AI song generation**: "🤖 AI compose a song" writes an original royalty-free instrumental (LLM-written music brief → MusicGen) | ✅ integrated (`providers/music_musicgen.py`, `POST /projects/{id}/song/generate`; needs ~3GB RAM — auto-falls-back to the built-in synth on small machines) |
| [riffusion/riffusion](https://github.com/riffusion/riffusion) | Music generation alternative | ⚙️ optional future engine behind the provider interface |
| [FluidSynth/fluidsynth](https://github.com/FluidSynth/fluidsynth) | MIDI→WAV rendering for demo instrumentals | ⚙️ optional on your machine (`apt install fluidsynth`) |
| [svc-develop-team/so-vits-svc](https://github.com/svc-develop-team/so-vits-svc) | Voice conversion | ❌ out of scope: vocals come from Suno imports |
| Stability-AI/stable-video-diffusion, modelscope text-to-video, deforum, AnimateDiff | Video synthesis | ❌ not wired: **video generation is OpenMontage-exclusive by design** — these can run *inside* ComfyUI workflows you attach |
| [langchain-ai/langchain](https://github.com/langchain-ai/langchain), AutoGPT | Agentic orchestration | ❌ not used: the built-in Autopilot job chain covers orchestration with zero bloat |
| suno-api (unofficial) | Suno automation | ❌ not used: unofficial wrappers break ToS — SongForge uses the **Suno import loop** (copy → generate → download → import) |

Install all optional AI extras: `pip install -r requirements-ai.txt`

### Better image prompts (built in)
Every storyboard pass runs a **cinematic prompt engine** (`app/services/prompt.py`) that rewrites each
scene prompt into modern image-model structure: camera & lens -> concrete lyric imagery -> environment ->
lighting arc (verses soft dawn / choruses golden god-rays / bridges moody ember) -> palette -> style ->
quality boosters, plus a strong shared negative prompt. Works with the offline mock, Ollama and cloud
LLMs alike — no setup needed.

### 8. Character animation — AnimatedDrawings (free, CPU, MIT)Want the *character* in a scene to really move — dance, jump, wave — instead of just camera motion?
SongForge integrates Meta's **AnimatedDrawings** (`facebookresearch/AnimatedDrawings`, MIT):
it finds the character in the scene image, rigs a skeleton onto it and retargets real
motion-capture clips onto it.

```bash
git clone https://github.com/facebookresearch/AnimatedDrawings
pip install -e AnimatedDrawings
```
Then set in `.env`:
```
CHAR_ANIM_REPO=/path/to/AnimatedDrawings
VIDEO_PROVIDER=char-animated        # or auto
```
The motion clip is chosen from each scene's text (dance / jump / jumping jacks / wave / dab /
zombie). Clips are normalized to the scene's exact duration; scenes without a detectable
character fall back to FFmpeg motion automatically. Needs a display/OpenGL-capable machine
(Windows/macOS desktops are fine).

**Modern diffusion-based character animators** (2024 SOTA, heavier — GPU recommended) work
through the ComfyUI provider with their custom nodes:

| Project | Repo | What it does |
|---|---|---|
| MimicMotion | `Tencent-Hunyuan/MimicMotion` | pose-driven character video from a reference |
| MusePose | `TMElyralab/MusePose` | pose-driven dancing character |
| MagicAnimate | `majianhuaa/magic-animate` | temporal-consistent character animation |
| LivePortrait | `KwaiVGI/LivePortrait` | portrait/face animation, very fast |
| Animate Anyone | `HumanAIGC/AnimateAnyone` | character/fashion animation (official page, community ports) |

Point `COMFY_VIDEO_WORKFLOW` at a workflow containing those nodes and SongForge animates each
scene with them — same fallback guarantees as above.


> The `MusicProvider` interface is ready for future in-app generation providers (AudioCraft/MusicGen, etc.) without touching the rest of the app.

## 🔁 The approval workflow

```
IDEA → AI LYRICS → ✋ USER APPROVAL → SONG (Suno import / demo) → AUDIO ANALYSIS
     → AI STORYBOARD → ✋ APPROVE → SCENE GENERATION → VIDEO RENDER
     → ✋ USER REVIEW → FEEDBACK → AI REVISION (only changed scenes)
     → ✋ FINAL APPROVAL → YOUTUBE METADATA → ✋ APPROVE → 🚀 UPLOAD
```

Every ✋ is enforced by the API **and** re-asserted inside the upload job.

## 🏗️ Architecture

```
┌────────────────────────────── frontend/index.html ─────────────────────────────┐
│  React 18 + Tailwind-style CSS (CDN, no build step — or `npm run build` w/ Vite)│
│  Stepper UI · lyrics editor · scene grid + timeline · job progress bar · gates  │
└──────────────────────────────────┬─────────────────────────────────────────────┘
                                   │ REST (JSON) + media streaming (Range)
┌──────────────────────────────────▼─────────────────────────────────────────────┐
│  FastAPI  (backend/app/main.py)                                                │
│   /api/projects  /api/.../lyrics  /song  /storyboard  /scenes  /render         │
│   /feedback  /versions  /metadata  /youtube  /system                           │
│                                                                                │
│  Job queue (jobs.py) ── worker thread; DB-backed rows, progress %, failures    │
│   lyrics.generate · song.demo/upload · storyboard.generate · scenes.generate   │
│   video.render · feedback.interpret · revision.apply · metadata.generate       │
│   youtube.upload                                                               │
│                                                                                │
│  Provider registry (providers/registry.py) — "auto" fallbacks                  │
│   LLMProvider     → OllamaProvider │ OpenAICompatProvider │ MockLLMProvider    │
│   ImageProvider   → ComfyUIImageProvider │ PlaceholderImageProvider            │
│   AlignerProvider → WhisperXAligner │ EstimateAligner                          │
│   MusicProvider   → (reserved for future local/cloud song generation)          │
│                                                                                │
│  Services: audio.py (BPM/peaks) · arrange.py (timing) · subtitles.py (ASS)     │
│            render.py (FFmpeg) · storyboard.py · revision.py · meta.py · yt.py  │
│                                                                                │
│  SQLAlchemy: SQLite (default) or PostgreSQL                                    │
└────────────────────────────────────────────────────────────────────────────────┘
        │
        └─ data/projects/<id>/ audio/ scenes/ renders/ meta/   (local files)
```

### Database schema (SQLAlchemy models)
`projects` · `project_versions` (immutable snapshots) · `lyrics` · `songs` · `audio_analyses` (BPM, peaks, sections, alignment) · `storyboards` (style bible) · `scenes` (prompts, timing, image status) · `renders` · `feedback_items` (plan JSON) · `jobs` (queue) · `youtube_metadata` · `youtube_uploads` · `oauth_tokens`

### Project layout
```
songforge/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app + worker + static hosting
│   │   ├── config.py          env-driven settings (.env supported)
│   │   ├── db.py  models.py   SQLAlchemy schema (SQLite/PostgreSQL)
│   │   ├── jobs.py            queue + 12 job handlers (progress/crash-safe)
│   │   ├── providers/         ⭐ provider interfaces + implementations
│   │   ├── services/          audio, arrange, subtitles, render, storyboard,
│   │   │                      revision, versions, meta, yt
│   │   └── api/               projects, pipeline, publish, system routers
│   ├── fonts/                 Noto Sans (+ Devanagari) for subtitles/thumbnails
│   └── requirements*.txt
├── frontend/index.html        the whole studio UI (React, no build needed)
├── scripts/                   setup.bat · run.bat · run.sh
├── .env.example               every option documented
├── Dockerfile · docker-compose.yml
└── README.md
```

## 🤖 Provider system (swap in cloud APIs later)

All AI goes through four interfaces in `app/providers/base.py`:

| Interface | Local (default) | Cloud swap |
|---|---|---|
| `LLMProvider` | `OllamaProvider` | `OpenAICompatProvider` (OpenAI/Groq/OpenRouter/LM Studio/vLLM) |
| `ImageProvider` | `ComfyUIImageProvider` | any HTTP image API — implement `generate()` |
| `AlignerProvider` | `EstimateAligner` / `WhisperXAligner` | e.g. AssemblyAI alignment |
| `MusicProvider` | *file import (Suno MVP)* | AudioCraft/MusicGen, Suno API, etc. |

`registry.get_*()` resolves by env (`LLM_PROVIDER=ollama|openai|mock|auto` …). With `auto`, SongForge probes your machine (is Ollama up? is ComfyUI up? is whisperx importable?) and picks the best available, always falling back to the offline mock. **Adding a provider = one new file + one registry branch.**

## 📡 API overview (interactive docs at `/docs`)

```
POST /api/projects                                   create project (idea)
GET  /api/projects/{id}                              full detail (poll this)
POST /api/projects/{id}/lyrics/generate              → job
PUT  /api/projects/{id}/lyrics                       save edits
POST /api/projects/{id}/lyrics/approve               ✋ gate
POST /api/projects/{id}/song/import                  multipart (Suno MP3/WAV)
POST /api/projects/{id}/song/demo                    free local track
POST /api/projects/{id}/storyboard/generate          → job
POST /api/projects/{id}/storyboard/approve           ✋ gate (creates version)
POST /api/projects/{id}/scenes/generate              all pending scenes
PUT  /api/scenes/{id}                                edit prompt/motion/timing
POST /api/scenes/{id}/regenerate                     single-scene job
POST /api/projects/{id}/render                       FFmpeg job (settings JSON)
GET  /api/renders/{id}/file                          MP4 (Range-enabled)
POST /api/projects/{id}/feedback                     natural language
POST /api/feedback/{id}/apply                        targeted revision job
POST /api/projects/{id}/approve-final                ✋ gate (confirm:true)
POST /api/projects/{id}/metadata/generate            AI YouTube kit + thumbnail
POST /api/projects/{id}/metadata/approve             ✋ gate
POST /api/projects/{id}/upload                       🚀 ONLY gate to YouTube
GET  /api/youtube/auth-url → /api/youtube/callback   OAuth flow
GET  /api/system/providers                           live provider status
GET  /api/jobs/{id}                                  progress polling
```

## 📺 YouTube setup (one-time)

1. https://console.cloud.google.com → new project → enable **YouTube Data API v3**.
2. *OAuth consent screen*: External → add your Google account as a test user.
3. *Credentials* → **Create OAuth client ID → Desktop app**.
4. Put the client ID + secret into `.env` (copy from `.env.example`). Keep
   `YOUTUBE_REDIRECT_URI=http://localhost:8000/api/youtube/callback`.
5. Restart → Publish step → *Connect YouTube* → approve in the browser.
6. After **final approval** + **metadata approval**, the **Approve & Upload** button unlocks. Uploads are resumable and default to **private** — flip to public on YouTube when you're ready.

## 🐳 Docker

```bash
docker compose up --build                 # SongForge alone (offline providers)
docker compose --profile ollama up -d     # + local Ollama  (then: docker compose exec ollama ollama pull llama3.1)
docker compose --profile comfy up -d      # + GPU ComfyUI
```

All media/DB live in the `songforge-data` volume. For host-installed Ollama/ComfyUI just point `OLLAMA_URL`/`COMFY_URL` at `http://host.docker.internal:11434` / `:8188`.

## 🧰 Troubleshooting

| Symptom | Fix |
|---|---|
| `LLM: mock` in sidebar | Ollama not reachable — start it and `ollama pull llama3.1` |
| Scene images are abstract art | That's the placeholder provider — start ComfyUI on :8188 |
| Render fails: `ffmpeg: not found` | Install FFmpeg or set `FFMPEG_BIN` to the full path |
| Hindi subtitles show boxes | The bundled Noto fonts cover Devanagari; if you changed `SUBTITLE_FONT`, install that font |
| Upload button disabled | Needs: final approval + metadata approval + YouTube connected + confirmation tick |
| WhisperX install fails | It's optional — the estimate aligner works fine; try CPU-only torch |
| Song stuck at 0:00 | Only WAV/MP3/M4A/OGG/FLAC are accepted; check the job error in the project detail |

## 🗺️ Roadmap (architecture is ready)

- `MusicProvider` implementations (MusicGen/AudioCraft locally, cloud song APIs)
- `VideoProvider` for image-to-video scene motion (AnimateDiff/SVD via ComfyUI)
- Celery/Redis queue drop-in for multi-GPU boxes (job rows already exist)
- Multi-user auth layer + team approval chains
- YouTube playlist scheduling, premieres and end-screens

## ⚖️ Notes

- You are responsible for complying with YouTube's policies when uploading AI-generated content (disclosure requirements etc.).
- All generation happens on **your machine** by default; nothing leaves localhost except the optional YouTube OAuth/upload and any cloud provider *you* configure.

*Built with FastAPI · React · Ollama · ComfyUI · WhisperX · FFmpeg · SQLAlchemy — all free, all local-first.*
