# ArXiviz

**Turn any arXiv ML/AI paper into 3Blue1Brown-style animated explainer videos with AI-generated voiceovers.**

ArXiviz is a multi-agent AI pipeline that reads academic papers, identifies the key concepts that are hard to understand from text alone, and generates [Manim](https://www.manim.community/) animation code with synchronized narration to visually explain them.

```
arxiv.org/abs/1706.03762  →  ArXiviz Pipeline  →  Animated Video Explainer
       (paper)                (AI agents)           (Manim + voiceover)
```

---

## Table of Contents

- [How It Works (High-Level)](#how-it-works-high-level)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [API Keys You Need](#api-keys-you-need)
- [Running the Pipeline](#running-the-pipeline)
- [What Goes In / What Comes Out](#what-goes-in--what-comes-out)
- [The Agent Pipeline (Detailed)](#the-agent-pipeline-detailed)
- [Team Architecture](#team-architecture)
- [File Reference](#file-reference)
- [How to Improve It](#how-to-improve-it)

---

## How It Works (High-Level)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        ArXiviz Pipeline Flow                            │
│                                                                          │
│   StructuredPaper (sections, equations, metadata)                       │
│         │                                                                │
│         ▼                                                                │
│   ┌─────────────────┐   Claude AI reads each section and decides:       │
│   │ SectionAnalyzer  │   "Does this need a visual? What kind?"          │
│   └────────┬────────┘   Outputs: VisualizationCandidate[]               │
│            │                                                             │
│            ▼                                                             │
│   ┌──────────────────┐   Claude AI creates a scene-by-scene plan:       │
│   │ VisualizationPlan│   "Scene 1: show title. Scene 2: show Q,K,V..." │
│   │     Planner      │   Outputs: VisualizationPlan with Scenes         │
│   └────────┬─────────┘                                                   │
│            │                                                             │
│            ▼                                                             │
│   ┌──────────────────┐   Claude AI writes actual Python Manim code      │
│   │ ManimGenerator   │   using few-shot examples matched to viz type    │
│   └────────┬─────────┘   Outputs: GeneratedCode (.py file)              │
│            │                                                             │
│            ▼                                                             │
│   ┌────────────────────────────────────────────┐                        │
│   │         3-Stage Validation (retries 3x)     │                        │
│   │  [1] CodeValidator    → syntax, imports      │                       │
│   │  [2] SpatialValidator → overlaps, bounds     │                       │
│   │  [3] RenderTester     → runtime import test  │                       │
│   │      ↳ Failures → feedback → ManimGenerator  │                       │
│   └────────┬───────────────────────────────────┘                        │
│            │                                                             │
│            ▼                                                             │
│   ┌──────────────────┐   Adds AI narration using ElevenLabs TTS         │
│   │ VoiceoverGen     │   Transforms Scene → VoiceoverScene              │
│   └────────┬─────────┘   Wraps animations with synced speech            │
│            │                                                             │
│            ▼                                                             │
│   ┌──────────────────┐                                                   │
│   │  Final Output:   │   Validated .py file with Manim code             │
│   │  Visualization   │   Ready to render: uv run manim -qm file.py     │
│   └──────────────────┘                                                   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
arxiviz/
├── README.md                    ← You are here
├── .gitignore
│
├── AgentDocs/                   # Documentation for all teams
│   ├── PROJECT_OVERVIEW.md      # Vision, architecture, tech stack
│   ├── TEAM1_INGESTION.md       # Team 1: Paper fetching & parsing
│   ├── TEAM2_GENERATION.md      # Team 2: AI pipeline (this codebase)
│   ├── TEAM3_RENDERING.md       # Team 3: Video rendering & frontend
│   ├── API_SPEC.md              # REST API specification
│   └── MANIM_PATTERNS.md        # Manim coding patterns & examples
│
├── backend/                     # Python backend (Team 2's scope)
│   ├── README.md                # Detailed backend docs ← READ THIS TOO
│   ├── pyproject.toml           # Project config & dependencies (uv)
│   ├── uv.lock                  # Locked dependency versions
│   ├── requirements.txt         # Pip-compatible dependency list
│   ├── .env.example             # Template for API keys
│   ├── .env                     # Your actual API keys (DO NOT COMMIT)
│   │
│   ├── agents/                  # AI agent implementations
│   │   ├── base.py              # Base agent: Anthropic client, prompts
│   │   ├── pipeline.py          # Orchestrator: ties all agents together
│   │   ├── section_analyzer.py  # Agent 1: identifies visualizable concepts
│   │   ├── visualization_planner.py  # Agent 2: creates storyboards
│   │   ├── manim_generator.py   # Agent 3: writes Manim Python code
│   │   ├── code_validator.py    # Validator 1: AST syntax checks
│   │   ├── spatial_validator.py # Validator 2: positioning/overlap checks
│   │   ├── render_tester.py     # Validator 3: runtime import test
│   │   └── voiceover_generator.py  # Agent 4: AI narration (ElevenLabs)
│   │
│   ├── models/                  # Pydantic data models
│   │   ├── paper.py             # StructuredPaper, Section, Equation
│   │   ├── generation.py        # VisualizationCandidate, Plan, Code
│   │   └── spatial.py           # Spatial validation issue models
│   │
│   ├── prompts/                 # Claude prompt templates (Markdown)
│   │   ├── section_analyzer.md  # "Which sections need visualization?"
│   │   ├── visualization_planner.md  # "Create a storyboard for this"
│   │   ├── manim_generator.md   # "Write Manim code from this plan"
│   │   ├── voiceover_generator.md   # "Generate narration script"
│   │   └── system/
│   │       └── manim_reference.md   # Curated Manim API reference (system prompt)
│   │
│   ├── examples/                # Few-shot Manim code examples
│   │   ├── equation_walkthrough.py   # Equation visualization pattern
│   │   ├── architecture_diagram.py   # Neural network architecture pattern
│   │   ├── data_flow.py              # Data flow animation pattern
│   │   ├── algorithm_steps.py        # Algorithm step-by-step pattern
│   │   ├── matrix_operations.py      # Matrix multiplication pattern
│   │   └── three_d_network.py        # 3D visualization pattern
│   │
│   ├── run_demo.py              # Demo: generate + optionally render
│   ├── test_pipeline.py         # Test harness: offline + online tests
│   ├── test_voiceover.py        # Voiceover-specific tests
│   └── generated_output/        # Generated .py files land here
│
└── .cursor/                     # IDE configuration
```

---

## Quick Start

### Prerequisites

- **Python 3.11+** (tested with 3.13/3.14)
- **[uv](https://docs.astral.sh/uv/)** - Fast Python package manager (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **An LLM API key** - Either Martian (recommended) or direct Anthropic
- **ElevenLabs API key** (optional) - For AI-generated voiceovers

### 1. Clone and enter the project

```bash
cd "New project"
git checkout team2
```

### 2. Set up API keys

```bash
cd backend
cp .env.example .env
# Edit .env and add your keys (see "API Keys You Need" section below)
```

### 3. Install dependencies

```bash
# uv handles everything - virtual env creation, dependency resolution, installation
cd backend
uv sync
```

### 4. Run offline tests (verify setup)

```bash
cd backend
uv run python test_pipeline.py
```

### 5. Run the full pipeline

```bash
cd backend
uv run python run_demo.py
```

### 6. Render a video (optional)

```bash
cd backend
uv run python run_demo.py --render --quality low
# Or render manually:
cd generated_output
uv run manim -ql <filename>.py
```

---

## API Keys You Need

### Required: LLM API Key (choose one)

The pipeline uses Claude (Anthropic's LLM) to analyze papers, plan visualizations, generate Manim code, and write voiceover scripts. You need **one** of these:

| Key | Where to Get It | Cost | Set In `.env` As |
|-----|-----------------|------|------------------|
| **Martian API Key** (recommended) | [withmartian.com](https://withmartian.com) | Unlimited for hackathon | `MARTIAN_API_KEY=sk-...` |
| **Anthropic API Key** | [console.anthropic.com](https://console.anthropic.com) | Pay per token | `ANTHROPIC_API_KEY=sk-ant-...` |

The code auto-detects which key is set and configures itself:
- **Martian** proxies to Anthropic but with unlimited usage for the hackathon
- Model names are auto-converted between formats (`anthropic/claude-opus-4-5-20251101` for Martian vs `claude-opus-4-5-20251101` for direct Anthropic)

### Optional: ElevenLabs API Key (for voiceovers)

| Key | Where to Get It | Cost | Set In `.env` As |
|-----|-----------------|------|------------------|
| **ElevenLabs API Key** | [elevenlabs.io](https://elevenlabs.io) | Free tier available | `ELEVEN_API_KEY=...` |

If not set, voiceovers are skipped and the pipeline still produces silent Manim animations.

### Your `.env` file should look like:

```env
# Pick ONE of these (Martian recommended):
MARTIAN_API_KEY=sk-your-martian-key-here
# ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here

# Optional - for AI voiceovers:
ELEVEN_API_KEY=your-elevenlabs-key-here
```

---

## Running the Pipeline

All commands run from the `backend/` directory using `uv run`:

```bash
cd backend

# ─── Tests ───────────────────────────────────────────────
uv run python test_pipeline.py                         # Offline tests (no API key needed)
uv run python test_pipeline.py --online                # Full pipeline test (needs API key)
uv run python test_pipeline.py --online --test analyzer    # Test just section analyzer
uv run python test_pipeline.py --online --test planner     # Test just visualization planner
uv run python test_pipeline.py --online --test generator   # Test just Manim generator
uv run python test_pipeline.py --online --test pipeline    # Test full pipeline (1 viz)

# ─── Demo ────────────────────────────────────────────────
uv run python run_demo.py                              # Generate 2 visualizations (default)
uv run python run_demo.py --max 3                      # Generate up to 3
uv run python run_demo.py --verbose                    # Show detailed agent logs
uv run python run_demo.py --render                     # Generate AND render videos
uv run python run_demo.py --render --quality low       # Render at 480p (fastest)
uv run python run_demo.py --render --quality high      # Render at 1080p

# ─── Manual Rendering ────────────────────────────────────
cd generated_output
uv run manim -ql filename.py                           # 480p (fast preview)
uv run manim -qm filename.py                           # 720p (good quality)
uv run manim -qh filename.py                           # 1080p (final render)
```

---

## What Goes In / What Comes Out

### Input: `StructuredPaper`

The pipeline expects a `StructuredPaper` object (defined in `backend/models/paper.py`). This is what Team 1's ingestion pipeline would produce from an arXiv paper. For now, we construct it manually in the test/demo scripts.

```python
StructuredPaper(
    meta=ArxivPaperMeta(
        arxiv_id="1706.03762",
        title="Attention Is All You Need",
        authors=["Vaswani", "Shazeer", ...],
        abstract="The dominant sequence transduction models...",
        pdf_url="https://arxiv.org/pdf/1706.03762",
    ),
    sections=[
        Section(
            id="section-3-2",
            title="Scaled Dot-Product Attention",
            content="An attention function can be described as...",
            equations=[
                Equation(
                    latex=r"\text{Attention}(Q,K,V) = \text{softmax}(\frac{QK^T}{\sqrt{d_k}})V",
                    context="The attention formula",
                ),
            ],
        ),
        # ... more sections
    ],
)
```

### Output: `list[Visualization]`

The pipeline outputs a list of `Visualization` objects (defined in `backend/models/generation.py`), each containing:

```python
Visualization(
    id="viz_abc12345",                    # Unique ID
    section_id="section-3-2",             # Which paper section this explains
    concept="Scaled Dot-Product Attention", # Human-readable concept name
    storyboard='{"scenes": [...]}',        # JSON storyboard from planner
    manim_code="from manim import *\n...", # Complete, validated Python code
    video_url=None,                        # Filled by Team 3 after rendering
    status="pending",                      # pending → rendering → complete
)
```

The `manim_code` field contains a complete, runnable `.py` file that can be rendered with:
```bash
uv run manim -qm generated_file.py
```

If voiceovers are enabled, the code includes `manim_voiceover` integration with ElevenLabs TTS, producing videos with synchronized AI narration.

---

## The Agent Pipeline (Detailed)

### Agent 1: SectionAnalyzer (`agents/section_analyzer.py`)

**Job:** Read each section of the paper and decide: "Does this need a visualization? What concepts should we visualize?"

- **Skips**: references, bibliography, acknowledgments, short sections (<100 chars)
- **Prioritizes**: attention mechanisms, architectures, equations, algorithms, data flows
- **Output**: `AnalyzerOutput` with `candidates: list[VisualizationCandidate]`
- **Prompt**: `prompts/section_analyzer.md` - tells Claude how to evaluate sections
- **LLM call**: 1 call per section (concurrent by default)

### Agent 2: VisualizationPlanner (`agents/visualization_planner.py`)

**Job:** For each candidate concept, create a detailed scene-by-scene storyboard.

- **Plans**: scene order, duration (target 15-30s), Manim elements to use, transitions
- **Creates**: narration points for each scene (used by VoiceoverGenerator later)
- **Output**: `VisualizationPlan` with `scenes: list[Scene]` and `narration_points`
- **Prompt**: `prompts/visualization_planner.md` - 3Blue1Brown-style planning guidance

### Agent 3: ManimGenerator (`agents/manim_generator.py`)

**Job:** Turn a storyboard into working Manim Python code.

- **Few-shot examples**: Automatically selects the right example based on viz type:
  - `equation` → `examples/equation_walkthrough.py`
  - `architecture` → `examples/architecture_diagram.py`
  - `data_flow` → `examples/data_flow.py`
  - `algorithm` → `examples/algorithm_steps.py`
  - `matrix` → `examples/matrix_operations.py`
  - `three_d` → `examples/three_d_network.py`
- **System prompt**: `prompts/system/manim_reference.md` - curated Manim API reference
- **Retry-aware**: `run_with_feedback()` method accepts validation errors and regenerates
- **Output**: `GeneratedCode` with complete Python code

### Validator 1: CodeValidator (`agents/code_validator.py`)

**Job:** Static analysis of the generated Manim code.

- **Checks**: Python syntax (AST parse), manim imports, Scene class, construct method
- **Auto-fixes**: Missing imports, color typos (GREY→GRAY), unclosed brackets
- **Detects**: Dangerous MathTex splitting patterns (e.g., splitting `\frac{}{}` across parts)
- **No LLM call** - pure Python static analysis

### Validator 2: SpatialValidator (`agents/spatial_validator.py`)

**Job:** Check positioning and layout of Manim elements.

- **Detects**: Off-screen elements (x>7 or y>4), overlapping elements, missing `buff` params
- **Heuristic**: Parses `shift()`, `move_to()`, `next_to()` calls to estimate positions
- **Suggests**: Using relative positioning (`next_to`) over absolute (`move_to`)
- **No LLM call** - regex-based static analysis

### Validator 3: RenderTester (`agents/render_tester.py`)

**Job:** Actually try to import the generated code as a Python module.

- **Catches**: ImportErrors, NameErrors, TypeErrors, AttributeErrors that static analysis misses
- **Method**: Writes code to temp file → `importlib` loads it → checks Scene class exists
- **Timeout**: 30 seconds (Manim imports can be slow)
- **No LLM call** - runtime validation

### Agent 4: VoiceoverGenerator (`agents/voiceover_generator.py`)

**Job:** Add AI-narrated voiceovers synchronized with animations.

- **Generates**: Educational narration script (concept-focused, not animation-describing)
- **Transforms**: `Scene` → `VoiceoverScene`, adds TTS setup, wraps `self.play()` with voiceover blocks
- **Places narration at scene boundaries**: Looks for `# Scene N:` comments, adds voiceover at the next `self.play()` call
- **Supports**: gTTS (free), Azure, ElevenLabs (best quality), Recorder (manual)
- **ElevenLabs config**: Uses `voice_id` (not name) to bypass API permission issues; `eleven_flash_v2_5` model for speed
- **Graceful fallback**: If voiceover fails, the visualization still works (silent)

### Pipeline Orchestrator (`agents/pipeline.py`)

**Job:** Coordinate all agents, run the full flow, handle retries.

- **Concurrent**: Analyzes all sections in parallel, generates all visualizations in parallel
- **Retry loop**: Up to 3 attempts per visualization; all validator feedback is combined and fed back to the generator
- **Config flags**: `ENABLE_SPATIAL_VALIDATION`, `ENABLE_RENDER_TESTING`, `ENABLE_VOICEOVER` (all on by default)
- **Limits**: `MAX_VISUALIZATIONS = 5` per paper (configurable)

---

## Team Architecture

ArXiviz is split into 3 teams for the hackathon:

| Team | Responsibility | Status in This Branch |
|------|---------------|----------------------|
| **Team 1** | Paper ingestion: fetch from arXiv API, parse PDF/HTML, extract sections/equations | Not yet built - currently using hardcoded mock papers |
| **Team 2** | AI generation pipeline: analyze sections, plan visualizations, generate Manim code | **Fully built and working** (this codebase) |
| **Team 3** | Rendering & display: run Manim on Modal.com, store videos, Next.js frontend | Not yet built - can render locally with `uv run manim` |

### What Team 2 Needs From Team 1

Team 1 should output a `StructuredPaper` object (see `backend/models/paper.py`):
- `meta`: arXiv ID, title, authors, abstract, PDF URL
- `sections`: list of `Section` objects with ID, title, content, equations, figures

### What Team 2 Gives to Team 3

Team 2 outputs a `list[Visualization]` (see `backend/models/generation.py`):
- `manim_code`: Complete, validated Python file ready to render
- `concept`: Human-readable name of what's being visualized
- `section_id`: Which paper section this belongs to
- `status`: "pending" (Team 3 changes to "rendering" → "complete")

---

## File Reference

### Models (the data that flows through the system)

| File | Key Classes | Purpose |
|------|-------------|---------|
| `models/paper.py` | `StructuredPaper`, `Section`, `Equation`, `ArxivPaperMeta` | Input from Team 1 |
| `models/generation.py` | `VisualizationCandidate`, `VisualizationPlan`, `Scene`, `GeneratedCode`, `ValidatorOutput`, `Visualization` | Data flowing between agents |
| `models/spatial.py` | `PositionInfo`, `BoundsIssue`, `OverlapIssue`, `SpacingIssue`, `SpatialValidatorOutput` | Spatial validation results |

### Prompts (what the AI sees)

| File | Used By | Controls |
|------|---------|----------|
| `prompts/section_analyzer.md` | SectionAnalyzer | How Claude evaluates which sections need visualization |
| `prompts/visualization_planner.md` | VisualizationPlanner | How Claude plans scene-by-scene storyboards |
| `prompts/manim_generator.md` | ManimGenerator | How Claude writes Manim code (includes LaTeX constraints, patterns) |
| `prompts/voiceover_generator.md` | VoiceoverGenerator | How Claude writes narration (concept-focused, not animation-focused) |
| `prompts/system/manim_reference.md` | All agents (system prompt) | Curated Manim API reference so Claude knows what's available |

### Few-Shot Examples (teach by example)

| File | Viz Type | Demonstrates |
|------|----------|-------------|
| `examples/equation_walkthrough.py` | `equation` | Highlighting equation parts, labels, step-by-step |
| `examples/architecture_diagram.py` | `architecture` | Stacked blocks, arrows, layer-by-layer building |
| `examples/data_flow.py` | `data_flow` | Q/K/V matrices, arrows, computation steps |
| `examples/algorithm_steps.py` | `algorithm` | Axes, curves, gradient descent animation |
| `examples/matrix_operations.py` | `matrix` | Matrix display, row/column highlighting |
| `examples/three_d_network.py` | `three_d` | 3D scene, camera rotation, fixed-in-frame labels |

---

## How to Improve It

### High-Impact Changes

1. **Connect to real arXiv papers** (Team 1 integration)
   - Build an arXiv fetcher that outputs `StructuredPaper`
   - Parse PDF or use ar5iv.org HTML for better section extraction
   - This makes the whole system dynamic for any paper

2. **Improve the few-shot examples** (`backend/examples/`)
   - More diverse examples = better generated code
   - Add examples for: GAN architectures, diffusion models, RL environments, loss landscapes
   - Each example teaches Claude a pattern it can reuse

3. **Tune the prompt templates** (`backend/prompts/`)
   - `manim_generator.md` has the most impact on code quality
   - Add more constraints, patterns, or anti-patterns you discover
   - The system prompt (`system/manim_reference.md`) controls what Manim APIs Claude knows about

4. **Switch models for speed vs quality**
   - Edit `backend/agents/base.py` line 25: `DEFAULT_MODEL_ANTHROPIC`
   - `claude-opus-4-5-20251101` = best quality, ~60-90s per visualization
   - `claude-sonnet-4-20250514` = good quality, ~20-30s per visualization

5. **Add more visualization types**
   - Current types: `equation`, `architecture`, `data_flow`, `algorithm`, `matrix`, `three_d`
   - Add: `comparison` (before/after), `training_loop`, `embedding_space`, `loss_landscape`
   - Update `models/generation.py` `VisualizationType` enum + add matching example file

### Lower-Impact / Polish

- Toggle pipeline features in `agents/pipeline.py` (lines 68-76)
- Add new ElevenLabs voices in `agents/voiceover_generator.py` `ELEVENLABS_VOICES`
- Improve spatial validator heuristics in `agents/spatial_validator.py`
- Add more auto-fixes to `agents/code_validator.py` `_fix_common_typos()`

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Package Manager | [uv](https://docs.astral.sh/uv/) | Fast, handles venvs + deps + lockfiles |
| LLM | Claude (Opus 4.5 / Sonnet 4) via Anthropic API | Best at code generation + reasoning |
| LLM Proxy | Martian API (optional) | Unlimited usage for hackathon |
| Animation | [Manim Community Edition](https://www.manim.community/) | 3Blue1Brown-style math animations |
| Voiceover | [manim-voiceover](https://docs.manim.community/en/stable/guides/add_voiceovers.html) + ElevenLabs | Synced AI narration |
| Data Models | [Pydantic v2](https://docs.pydantic.dev/) | Type-safe data validation |
| Python | 3.11+ | Async support, type hints |
