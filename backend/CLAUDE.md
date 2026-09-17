# MedScroll backend — agent context

FastAPI service that turns a PubMed link into a verified explainer. Local and single-user.
The `docs/FINDINGS.md` at the repo root is the useful history, including several things not
to try again.

## Shape

```
POST /api/jobs        {"input": "<PubMed link | PMCID | PMID | DOI>"}   202, a job to poll
POST /api/jobs/pdf    multipart file                                    for papers PMC lacks
GET  /api/jobs        GET /api/jobs/{id}    step, fraction, elapsed, then paper_id or error
POST /api/build, /api/build/pdf   the same builds as one long request, for scripts
GET  /api/explainer/{paper_id}   GET /api/explainers   GET /api/figure/{paper_id}/{file}
GET  /api/health      reports degraded, with the reason, when it cannot build

ingestion/  resolve → fetch JATS → parse to StructuredPaper → rewrite into ≤5 sections
agents/     chart_planner (one LLM call) → verify (deterministic gate) → pipeline assembles
models/     charts.py is the contract the frontend is built against
builds.py   the two build paths, and the in-memory job registry (one build at a time)
store.py    JSON per paper under data/explainers/
```

There is no database. An explainer is a JSON file, and a build is one request.

## The gate is the point

`agents/verify.py`. Every plotted value carries `provenance{locator, quote}`. Three string
checks: the locator exists, the quote appears there, the number appears in the quote. No
second model. Diagram edges are checked the same way plus one rule — a single sentence in
the quote must name both ends of the arrow — and `hedged` is derived from the quote's own
wording, never supplied by the model.

Values that fail are dropped and listed in the response. Do not soften this to raise a pass
rate; fix the extraction instruction instead.

**`paper.sections` is the source and stays verbatim.** The rewrite lands on
`paper.reader_sections`. Overwriting `.content` makes the gate verify against a paraphrase.

## Providers

`agents/base.py` resolves the provider: `claude_cli` (headless Claude Code, no key),
`anthropic` (official SDK, your key), `openai` (your key, or any OpenAI-compatible
endpoint via OPENAI_BASE_URL), `azure`. `settings.py` reads and writes `backend/.env`
for the Settings page (`/api/settings`, loopback-only), and `probe()` is the one tiny
call that says whether the configured provider actually answers; health uses it.

For `claude_cli`:

- Errors arrive on **stdout**, not stderr.
- `--max-turns 1` fails with `error_max_turns`; 4 works.
- Subprocesses get `USER`, `LOGNAME` and `HOME` filled in. Without `USER` the CLI cannot
  reach its credentials and reports "Not logged in", which is a GUI-launch failure mode.

## Ingest

Two tiers, one output contract.

- **JATS** (`ingestion/pubmed.py`) — the good tier. Stable locators for paragraphs and table
  cells. Try both E-utilities and Europe PMC and keep the one with more body text; an
  `<article>` with no `<body>` is a record, not a paper, and below `MIN_BODY_WORDS` the
  ingest refuses.
- **PDF** (`ingestion/pdf.py`) — the reader supplies the file. Paragraph locators only, no
  table cells. Strip markdown before the text goes anywhere: the gate matches quotes against
  it, and `**bold**` left in place silently fails every number inside.

Hardcoded NCBI URLs go stale. Three moved or died across two builds.

## Conventions

- Run `python -m ruff check .` and `python -m pytest tests/ -q` before calling anything done.
- An empty build is an error, not a result: no sections and no charts returns 502 rather
  than storing a blank page.
- User-facing strings follow the writing rules in the prompts: no em dashes, no
  "pivotal/crucial/robust", say the specific thing.
- Restart the API detached (`nohup ... & disown`). Long polling shells kill their process
  group and take the server with them.
