<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/wordmark-dark.png">
    <img alt="espresso" src="docs/assets/wordmark-light.png" width="280">
  </picture>
</p>

<p align="center"><b>Catch up on papers, and stay awake.</b></p>

<p align="center">
  <a href="https://github.com/karmicoperator/espresso/releases/latest/download/espresso-macOS.dmg">Download for macOS</a>
  &nbsp;·&nbsp;
  <a href="https://github.com/karmicoperator/espresso/releases/latest/download/espresso-windows.zip">Download for Windows</a>
</p>

Ever got bored halfway through a paper? espresso turns a medical paper into a five-minute
read with charts. Paste a PubMed link and the paper comes back as short prose in sections,
charts drawn from its own numbers, and a bottom line. Every charted value is checked
against the paper's text before it is drawn, and a click on any sentence opens the paper
at the line it came from. It runs on your computer; nothing leaves it except the request
for the paper.

espresso is an unofficial fork of [arXivisual](https://github.com/rajshah6/arXivisual) by
Raj Shah, which does the same for arXiv papers. The idea and the reader's look are his; the
rest was rebuilt for medical papers.

## Install

### macOS

1. Download [espresso-macOS.dmg](https://github.com/karmicoperator/espresso/releases/latest/download/espresso-macOS.dmg).
2. Open it and drag **espresso** onto **Applications**.
3. Open espresso from your Applications folder. The first time, macOS says it could not
   verify the app, because espresso is not yet signed with an Apple Developer ID. Click
   **Done**, open **System Settings**, go to **Privacy & Security**, scroll down to the note
   about espresso and click **Open Anyway**, then enter your password. This happens once.
4. The first start takes a few minutes while espresso fetches Python and Node.js into its
   own folder and builds itself. Then your browser opens on espresso, with nine papers
   already in the library.

### Windows

The Windows launcher has not been run on a real Windows machine yet. Reports are welcome.

1. Download [espresso-windows.zip](https://github.com/karmicoperator/espresso/releases/latest/download/espresso-windows.zip).
2. Right-click it, choose **Extract All**, and open the extracted **espresso** folder.
3. Double-click **Start espresso.bat**. If Windows warns that it cannot verify the
   publisher, choose **Run**, or **More info** and then **Run anyway**.
4. The first start takes a few minutes, as on macOS. Keep the window open while you use
   espresso and press Ctrl-C in it to stop. If a step fails,
   `%LOCALAPPDATA%\espresso\logs\setup.log` says which one.

### Then pick a model

Open **Settings** in espresso and choose how it reaches a model:

- **Claude Code**, if it is installed and signed in on this computer. No key needed.
- **An API key** from Anthropic, OpenAI or any OpenAI-compatible endpoint, Azure, DeepSeek,
  Kimi, Qwen or GLM.

Settings tests the choice with one small call. Nothing else is asked for, not even an email.

### Browser extension (optional)

One click on a paper's page builds it and hands espresso the PDF your browser can see,
fetched with your own access. The extension is the `extension` folder of the Windows zip
or of a clone. On a Mac it is at `~/Library/Application Support/espresso/repo/extension`
after the first start (in Finder: Go, Go to Folder). [extension/README.md](extension/README.md)
covers loading it in Chrome, Edge, Brave, Firefox and Safari.

### From source

```
git clone https://github.com/karmicoperator/espresso
cd espresso
./start.command           # macOS
windows\espresso.bat      # Windows
```

Both launchers fetch uv and Node when the machine has neither, reuse servers already
running, step past taken ports, and rebuild the web app when a source file changed.
`scripts/package-mac.sh` builds the disk image and `scripts/package-windows.sh` the zip.
With `ESPRESSO_SIGN_ID` and `ESPRESSO_NOTARY_PROFILE` set, the disk image is signed with a
Developer ID and notarized, and the approval step on first open goes away.

## What a paper becomes

A build takes two to four minutes: two model calls, run side by side. The page has:

- A bottom line: the question, the answer, and the one figure that is the finding, named
  by the planner and verified by the gate. Green when the treatment did better, red when
  worse, white for no difference.
- Prose in at most five sections. Each sentence is anchored to the source sentence that
  prints its numbers and shares its terms, or marked as untraced. Click a sentence and the
  paper opens at it, highlighted: in the PDF when one is stored, else in the paper's text.
- Charts from a fixed catalogue (`stat`, `bars`, `forest`, `line`, `flow`, `diagram`), each
  with one layout and hard limits. The model fills them and never touches layout, and every
  built page is checked for overlapping text. As the sentence that states a value scrolls
  into view, its mark lights. Every value shows the paper's sentence on hover.
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
windows/    PowerShell launcher.
scripts/    launchers, bootstrap, the two packagers (mac/ holds the disk image's parts),
            and the generators for the logo and the README header.
backend/examples/   the shipped library (explainers, source text, figures) with its
                    licences; seeded into backend/data/ on first start, which is not in git.
docs/FINDINGS.md    what was tried, what failed, and why.
```

## Status

117 backend tests; ruff, tsc and eslint clean. Limits, each one observed: a paper neither
in PMC nor available to you as a PDF cannot be built; a PDF build cannot cite table cells;
the anchoring cannot judge a paraphrase that keeps the numbers and the terms and changes
the meaning, which is why the paper is one click away.

## Licence

MIT, see `LICENSE`. That covers the work in this repository. The upstream
[arXivisual](https://github.com/rajshah6/arXivisual) ships no licence file, so the parts
that survive from it (the idea and the reader's look) stay with their author until he
puts a licence on them.
