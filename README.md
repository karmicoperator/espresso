<div align="center">
  <img alt="espresso" src="frontend/public/icon.png" width="80" />
</div>

# espresso

Ever got bored halfway through a paper? espresso turns a medical paper into a
five-minute read with charts. Catch up on papers, and stay awake.

The page is prose in sections, charts drawn from the paper's own numbers, and a bottom
line. Every charted value is checked against the paper's text before it is drawn, and
every sentence of the prose is tied to the sentence of the paper it came from, so a click
opens the paper at that line. Local, single user; nothing leaves the machine except
requests for the paper.

This is an unofficial fork of [arXivisual](https://github.com/rajshah6/arXivisual) by
Raj Shah, which does the same thing for arXiv papers. The idea and the reader's look are
his. The rest was rebuilt for medical papers.

Papers come from PubMed Central's JATS, or from a PDF when PMC doesn't have them. A
deterministic gate sits between the model and the page: each plotted value carries a
locator and a verbatim quote, three string checks decide whether it gets drawn, and
anything that fails is dropped and listed. The model fills a fixed set of chart blocks
and never touches layout; each built page gets a DOM check for overlapping text. Trial
results turn into a hundred people, the bottom line names a finding the gate verifies,
and every sentence of the prose is anchored to the source sentence that prints its
numbers, so a click opens the paper right there, PDF or text. Builds take about two
minutes on Claude, OpenAI, Azure, DeepSeek, Kimi, Qwen or GLM. The app installs itself on
an empty machine, and the browser extension hands it whatever PDF your session can see.
Things that were measured and didn't make it are in `docs/FINDINGS.md`.

## What it does

Paste a PubMed or PMC link, a DOI or a PMID, or drop a PDF. Two to four minutes later
(two model calls, run side by side) the paper opens as a page:

- A bottom line: the question, the answer, and the one figure that is the finding, named
  by the planner and verified by the gate. Green when the treatment did better, red when
  worse, white for no difference.
- Prose in at most five sections. Each sentence is anchored to the source sentence that
  prints its numbers and shares its terms, or marked as untraced. Click a sentence and the
  paper opens at it, highlighted: in the PDF when one is stored, else in the paper's text.
- Charts from a fixed catalogue (`stat`, `bars`, `forest`, `line`, `flow`, `diagram`), each
  with one layout and hard limits. As the sentence that states a value scrolls into view,
  its mark lights. Every value shows the paper's sentence on hover.
- The primary outcome as a hundred people, when the paper prints it as a rate per arm,
  with number needed to treat worked out from those two numbers and marked as derived.
- The paper's own figures where a chart could not be rebuilt from printed numbers.

## How the numbers are kept honest

The planner is a transcriber. Every value it returns carries a locator and a verbatim
quote, and three string checks decide whether it is drawn: the locator exists in the
paper, the quote appears there, the number appears in the quote. A value that fails is
handed back once with the paper's paragraph, then dropped and listed. There is no second
model judging the first. Diagram arrows are checked the same way plus one rule: a single
sentence in the quote must name both ends. The prose is checked by the same machinery,
sentence by sentence, and the page states the counts ("All 24 charted values verified",
"66 of 89 sentences anchored"). What is not checked is said too: the summary is a
model's, and it is not clinical advice.

Two things were measured before being trusted. A direction-word check (lower against
higher between a sentence and its anchor) flagged five sentences across the library, all
five false alarms, so it stays in the data and off the page. And the regex that picked
the bottom line's key figure lit "95%" in "95% CI"; it was replaced by a figure the
planner names and the gate verifies. `docs/FINDINGS.md` keeps this kind of record.

## Getting it

macOS: download `espresso-mac.zip` from the latest release, unzip, move the app to
Applications, right-click, Open (the bundle is unsigned, so the first open asks). First
run fetches `uv` and Node into `~/Library/Application Support/espresso`, builds, and
opens the browser on a library of twenty papers. Then Settings, to pick a model.

Windows: download the source, double-click `windows\espresso.bat`. Same first run,
into `%LOCALAPPDATA%\espresso`. Not yet run on a Windows machine; `logs\setup.log`
says which step failed if one does.

From a clone: `./start.command` on macOS or the Windows launcher above. Both fetch `uv`
and Node when the machine has neither, reuse servers already running, step past taken
ports, and rebuild the web app when a source file changed.

Models: a signed-in Claude Code session (no key), or a key from Anthropic, OpenAI or any
OpenAI-compatible endpoint, Azure, DeepSeek, Kimi, Qwen or GLM. Settings tests the model
with one small call. DeepSeek and Qwen refuse requests over 8k output tokens; the app
caps them. Nothing else is asked for.

Browser extension: `extension/` adds a button for Chrome, Edge, Brave and Firefox
(Safari via Xcode's converter). One click on a paper's page builds it and hands the app
the PDF the page offers, fetched with your own session. Publishers block programs, not
people; this is how a PMC paper gets its PDF.

## Where the paper comes from

PubMed Central's JATS XML, which gives paragraph and table-cell locators. A PDF gives
paragraph locators only, so a number printed only inside a table cannot be cited from a
PDF; the page says when it was built that way. The PDF itself is fetched at build time
from a publisher that serves it (Unpaywall names the location by DOI; Nature and several
society journals do, NEJM, BMJ, Springer, Elsevier, SAGE and MDPI do not), else attached
when you drop it on the paper's page.

## Layout

```
backend/    FastAPI. ingestion/ (JATS, PDF, PDF fetch), agents/ (blocks, planner, gate,
            anchors, pipeline), api/, store.py, scripts/ (relink, reanchor, fetch_pdfs)
frontend/   Next.js reader. ChartFigure.tsx draws every block; PaperView.tsx opens the
            paper (PDF.js or text) at a sentence.
extension/  WebExtension, Manifest V3.
windows/    PowerShell launcher.   scripts/   launchers, bootstrap, macOS packager.
backend/examples/   the shipped library (explainers, source text, figures); seeded into
                    backend/data/ on first start, which is not in git.
docs/FINDINGS.md    what was tried, what failed, and why.
```

## Status

117 backend tests; ruff, tsc and eslint clean. Limits, each one observed: a paper neither in PMC nor available to you as a PDF cannot be built; a PDF build cannot
cite table cells; the anchoring cannot judge a paraphrase that keeps the numbers and the
terms and changes the meaning, which is why the paper is one click away.

## Licence

MIT, see `LICENSE`. That covers the work in this repository. The upstream
[arXivisual](https://github.com/rajshah6/arXivisual) ships no licence file, so the parts
that survive from it (the idea and the reader's look) stay with their author until he
puts a licence on them.
