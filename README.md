<div align="center">
  <img alt="MedScroll" src="build/icon.png" width="96" />
</div>

<h1 align="center">MedScroll</h1>

<p align="center">Medical papers as scrollable explainers, with every number traceable to the source.</p>

---

Paste a PubMed link. It comes back as a short explainer with interactive charts built from
the paper's own numbers, **every value checked against the source before it is drawn**.

Private, local, single user. Nothing is published and nothing leaves the machine except
requests to PubMed Central for the paper itself.

## Running it

Double-click **`MedScroll.app`**, or run **`./start.command`** for the same thing with live
output. Both install what is missing on first run, build the web app, start what is down,
reuse what is already running, step past ports held by other programs, and open the
browser. When a source file changes, the next start rebuilds and restarts the web app.

Three tools have to be on the machine, and the launcher says which one is missing and how
to get it:

- [`uv`](https://docs.astral.sh/uv/) for the API. It fetches Python itself if needed.
- [Node.js](https://nodejs.org) for the web app.
- A model. By default a signed-in [Claude Code](https://claude.com/claude-code) session
  (`claude` once in a terminal), with no API key. Or open **Settings** in the app and
  paste your own key: the Anthropic API, OpenAI, any OpenAI-compatible endpoint (Ollama,
  Groq, OpenRouter) or Azure OpenAI. Settings tests the model with one tiny call. Without
  a working model, papers already built still open; the landing page says so.

Logs land in `logs/`. `MEDSCROLL_DEV=1 ./start.command` runs the web app's dev server
instead of a production build.

## What it does

A build takes three to five minutes, almost all of it in one model call. Builds run on the
API one at a time: paste several and they queue, the page shows the stage each is at,
and reloading or leaving the page loses nothing.

```
PubMed link ─→ resolve ─→ JATS from PubMed Central ─→ rewrite into ≤5 sections
                                                            │
                                    one planning call ──────┴──→ charts + figures + diagram
                                                            │
                                              PROVENANCE GATE (deterministic)
                                                            │
                                                    explainer JSON ─→ reader
```

The capitalised step is the one that makes the rest trustworthy. Every plotted value carries
a locator and a verbatim quote; three string checks confirm the locator exists, the quote
appears there, and the number appears in the quote. Values that fail are dropped and listed.
Nothing downstream can introduce a number the paper does not contain.

**Bottom line** opens the page: what the paper asked and what it found, one sentence each,
checked like a plotted value against the quoted span shown beneath it, and dropped if it
fails.

**Prose** is the model's summary, so every number in it is looked up in the paper. One
that is not printed there as such (a percentage the summary worked out from a rate ratio,
a rounded mean) is marked with a dotted underline rather than removed, and the header
says how many there are. The page also says plainly what was checked and what was not,
and that it is not clinical advice.

**Charts** are typed specs the browser draws: `stat`, `bars`, `dots`, `forest`, `line`,
`flow`, `diagram`. Hovering, tapping or tabbing to any mark shows the paper's own
sentence. "Print or save as PDF" gives a light handout with every chart drawn.

**Figures** are the paper's own images, taken only when a chart could not be rebuilt from
printed numbers: radiographs, micrographs, specimens, clinical photos, schematics, and
survival curves whose values are never tabulated. Captions are copied verbatim.

**Diagrams** are mechanisms the paper argues, drawn as nodes and cited edges. Every arrow
carries the sentence licensing it, and an arrow the paper only hedges is drawn dashed —
derived from the quoted wording, not from the model.

## Coverage

Within PubMed's open-access filter: **76/76 papers across 38 subspecialties**. Papers in PMC
but outside the open-access subset work too.

About a quarter of PubMed's "free full text" was never deposited in PMC. Those are often
genuinely open access, but the publishers hosting them answer 403 to anything that is not a
browser. They block programs, not people — so download the PDF and drop it anywhere on the
landing page, or use **"open the PDF"** there. When a pasted link turns out to be one of
these, the message says so and links to the publisher's page, with the PDF route beside it.
Same pipeline, same gate, with one honest cost: a PDF has no addressable
table cells, so a number printed only inside a table cannot be cited and will not appear.
The page says when it was built that way.

## Layout

```
backend/     FastAPI. ingestion/ (JATS + PDF), agents/ (planner, gate, pipeline), api/
frontend/    Next.js reader. components/ChartFigure.tsx draws every chart kind.
scripts/     launch-lib.sh — port resolution shared by both launchers
docs/        FINDINGS.md — what we learned, including what not to try
MedScroll.app, start.command
```

Papers are stored as JSON under `backend/data/explainers/`, figures under
`backend/data/figures/`.

## Status

Working. 65 tests, ruff and eslint clean.

Known limits, all verified rather than assumed:

- A paper neither in PMC nor downloadable by you cannot be built.
- PDF-derived papers cannot cite table cells.
- The diagram gate cannot check that a sentence asserts the *direction* an arrow points.
  That stays the model's assertion, which is why hovering shows the sentence.

## Provenance

Forked from [arXivisual](https://github.com/rajshah6/arXivisual) for the reader, the
sectioning and the visual language. The render pipeline, the ingest, the provenance gate and
the chart system are new. arXivisual ships no licence file; this fork is private, local and
undistributed.
