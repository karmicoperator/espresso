<div align="center">
    <img alt="Logo" src="frontend/public/icon.png" width=100 />
</div>
<h1 align="center">
  <a href="https://www.arxivisual.org/" target="_blank">ArXivisual</a>
</h1>
<p align="center">
   Transform research papers into visual stories
</p>

[![ArXivisual Video](frontend/public/demo.mp4)](https://github.com/user-attachments/assets/516d2217-53b9-435d-93b2-e50a6b32317e)

![ArXivisual Landing Page](frontend/public/landing.jpeg)

![ArXivisual Manim](frontend/public/manim.png)

## How It Works

1. **Ingest**: Paste any arXiv paper URL and watch as it's decomposed into digestible sections
2. **Analyze**: AI agents analyze each section to identify key concepts and visual opportunities
3. **Generate**: Multi-agent pipeline creates 3Blue1Brown-style Manim animations for complex ideas
4. **Validate**: Four-stage quality gates ensure syntactic correctness, spatial coherence, and runtime stability
5. **Experience**: Read through an interactive scrollytelling interface with embedded animated visualizations

## Quick Start

### Option A: Docker (recommended — zero system setup)

Only requires [Docker](https://docs.docker.com/get-docker/) and API keys.

```bash
# 1. Configure API keys
cp backend/.env.example backend/.env
# Edit backend/.env — add DEDALUS_API_KEY and ELEVEN_API_KEY

# 2. Start backend (builds image with all system deps automatically)
docker compose up

# 3. Start frontend (in a separate terminal)
cd frontend && npm install && npm run dev
```

Visit **http://localhost:3000** and paste any arXiv URL.

### Option B: Native install (faster dev loop)

#### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 18+
- Python 3.13 (3.14 is **not** supported — `manim-voiceover` needs `pkg_resources`, removed in 3.14)
- API keys: [Dedalus Labs](https://www.dedaluslabs.ai/dashboard/api-keys) and [ElevenLabs](https://elevenlabs.io)

#### 1. Install system dependencies

Manim renders videos using FFmpeg, LaTeX, Cairo, Pango, and SoX. These are **system binaries** that cannot be installed via pip.

**macOS (Homebrew):**
```bash
brew install ffmpeg sox cairo pango pkg-config
brew install --cask basictex
# After basictex, open a new terminal, then:
sudo tlmgr update --self && sudo tlmgr install standalone preview dvisvgm cm-super
```

**Linux (apt):**
```bash
sudo apt-get install -y ffmpeg sox libcairo2-dev libpango1.0-dev pkg-config \
  texlive-latex-base texlive-fonts-recommended texlive-latex-extra \
  texlive-fonts-extra cm-super dvipng
```

#### 2. Backend setup

```bash
cd backend
cp .env.example .env          # Then add your API keys (see below)
uv python pin 3.13            # Ensure correct Python version
uv sync                       # Install all Python dependencies
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Visit **http://localhost:3000** — paste an arXiv URL (e.g. `https://arxiv.org/abs/2501.12599`) and click through.

### Environment Variables (Backend)

Add these to `backend/.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `DEDALUS_API_KEY` | Yes | Dedalus Labs API key (LLM). Sign up at [dedaluslabs.ai](https://www.dedaluslabs.ai/dashboard/api-keys) |
| `ELEVEN_API_KEY` | Yes | ElevenLabs API key (voiceover) |
| `STORAGE_MODE` | No | `local` (default) or `r2` for cloud storage |
| `S3_*` | If R2 | `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_PUBLIC_URL` |

### Environment Variables (Frontend)

Optional. Create `frontend/.env.local` to override defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API URL |
| `NEXT_PUBLIC_USE_MOCK` | `false` | Set `true` for demo mode (no backend needed) |

## Troubleshooting

**Python 3.14 not working:**
`manim-voiceover` depends on `pkg_resources` (part of `setuptools`), which was removed from the Python stdlib in 3.14. Stick with Python 3.13:
```bash
uv python pin 3.13
```

**`uv sync` fails with setuptools errors:**
Python 3.13 also removed `pkg_resources` from the stdlib, but `setuptools` is listed as a project dependency so `uv sync` should install it. If it doesn't:
```bash
uv pip install setuptools
```

**`tlmgr` permission denied (macOS):**
BasicTeX's package manager requires sudo:
```bash
sudo tlmgr update --self && sudo tlmgr install standalone preview dvisvgm cm-super
```

**Port 8000 already in use:**
```bash
lsof -ti:8000 | xargs kill -9
```

**Videos not appearing after processing:**
Check that `STORAGE_MODE=local` is set in `backend/.env`. If using R2 cloud storage, all `S3_*` variables must also be configured.

## Inspiration

Research papers arrive as monoliths — dense, opaque, intimidating. Within them lies a mosaic of brilliant ideas waiting to be seen.

**ArXivisual** transforms fragments of academic text into animated visual explanations, making complex research accessible to everyone.
