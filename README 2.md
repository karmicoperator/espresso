# MedScroll

Paste a link to an open-access medical paper. Get back a scrollytelling explainer with
narrated Manim animations built from the paper's own numbers.

An arXivisual-style pipeline rebuilt for clinical evidence — same art direction, black
ground and monochrome glass — with one structural difference:
**no number reaches the screen unless it was matched back to a quoted span in the source
text.** Values that cannot be traced are dropped, and the pass rate is shown on the page.

```
./setup.command     # once — installs system deps, Python env, node modules
./start.command     # every time — API on :8000, reader on :3000
```

Then open <http://localhost:3000> and paste a PubMed link.

**No API key needed.** It runs on your Claude Code subscription by default, driving
headless `claude -p` calls. Set `MEDSCROLL_LLM_PROVIDER=anthropic_api` in `backend/.env`
if you'd rather use a metered API key — that path is roughly twice as fast.

A trial paper takes four to seven minutes: reading the numbers out of the paper is the
long pole, rendering adds two to four.

## What it accepts

PubMed links (`pubmed.ncbi.nlm.nih.gov/33378609/`), PMC links, Europe PMC links, bare
PMCIDs or PMIDs, DOIs, and direct PDF URLs. Anything with a PubMed Central record uses JATS full text; everything
else falls back to PDF parsing with lower-confidence provenance.

## Requirements

macOS with Homebrew. `setup.command` installs ffmpeg, cairo, pango, sox, IBM Plex, `uv`
and node. No Docker, no LaTeX, no cloud services. Narration uses the macOS speech
synthesiser, so it works offline and costs nothing.

Architecture, design decisions and known limits: [`OVERVIEW.md`](OVERVIEW.md).
What the first build taught us, including the dead ends: [`docs/FINDINGS.md`](docs/FINDINGS.md).
