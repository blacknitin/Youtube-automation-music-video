# SongForge Frontend

Two ways to run the studio UI:

## Default — zero build (recommended)

The whole app lives in **`index.html`**: React 18 (UMD) + Babel standalone +
hand-rolled Tailwind-style CSS. The FastAPI backend serves it automatically at
`http://localhost:8000` — nothing to install, nothing to compile.

> Note: the in-browser Babel compile is perfect for local/single-user use.
> For heavy daily use you can switch to the Vite build below.

## Optional — Vite build

```bash
cd frontend
npm install
npm run dev      # dev server on :5173, /api proxied to :8000
npm run build    # outputs dist/ — served by FastAPI if you move it next to index.html
```

Tailwind CSS is included as a devDependency for extending the design system in
`index.html` (CSS variables in `:root` — colors, radii, badges, chips).

## Screens

- **Sidebar** — projects, live provider chips (LLM / art / FFmpeg / YouTube)
- **Stepper** — Idea → Lyrics → Song → Storyboard → Scenes → Video → Review → Publish
- **Lyrics editor** — per-section editing, regenerate, ✅ approve gate
- **Song** — drag-and-drop Suno MP3/WAV import, waveform, BPM readout
- **Storyboard** — style-bible editing (characters keep scenes consistent), scene plan
- **Scenes** — grid + per-scene regenerate / prompt editor / camera motion / timing
- **Video** — render settings, inline player, download
- **Review** — natural-language feedback with AI plans, apply revision, versions, ✋ final approval
- **Publish** — metadata editor, thumbnail, OAuth connect, 🚀 Approve & Upload (triple-gated)
