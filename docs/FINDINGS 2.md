# What we learned building this

Notes from the first build, written so the second one can skip the dead ends. Ordered by
how much time each thing cost, not by where it sits in the pipeline.

The short version: the hard parts were not the parts that looked hard. Manim rendered on
day one. The provenance gate worked on its first live paper. What ate the time was
upstream services that had quietly died, a text renderer that drops spaces, and roughly a
dozen places where a caption disagreed with the paper it was quoting.

---

## 1. Medical papers are a much better ingest target than arXiv

This is the finding everything else depends on. PubMed Central serves JATS XML with
sections, tables, captions and figures already marked up. Every paragraph has an id.
Every table cell has a row and column.

That means a number can carry an address: `t2/r4/c3`, `sc2.2/p1`. Which means you can
check it. arXiv gives you a PDF and a prayer.

If you are rebuilding, get the JATS parser right before anything else. Stable locator ids
are the foundation of the whole design, and a parser that renumbers sections between runs
silently breaks every citation.

**Gotchas found:**

- Some publishers put a `<sec>` with a title and no prose (NEJM does this for "Methods"
  and "Results"). Dropping empty sections loses those headings. Keep any section with a
  title.
- Tables and figures often live in `<floats-group>` outside `<body>`. Parse both.
- `<table-wrap-foot>` matches a naive `<table-wrap` string count. Do not count tags to
  estimate table numbers.
- The NCBI ID converter returns `pmid` as a JSON number about half the time. Coerce it.
- Legacy PubMed URLs (`ncbi.nlm.nih.gov/pubmed/<id>`) need their own pattern. The current
  host pattern will not match them.

## 2. Two upstream services are dead. Plan around them

**PMC OA Web Service (`oa.fcgi`) was retired in February 2026.** It returned 404 for every
PMCID we tried, including a CC-BY PLOS article. There is no drop-in replacement documented.

**Direct figure fetches are blocked.** `pmc.ncbi.nlm.nih.gov/articles/PMC…/bin/foo.jpg`
returns HTTP 200 with a 21KB HTML interstitial, not the image. Content-type is `text/html`.
Easy to mistake for success if you only check the status code.

We spent about forty minutes on this before accepting it. The pivot turned out better than
the original plan: recreate every figure natively from extracted numbers. A recreated chart
carries provenance. A reused bitmap does not.

If you want paper figures in the rebuild, budget real time for it and check the AWS
`pmc-oa-opendata` bucket first. Note it holds XML and text, and we did not confirm images.

## 3. The provenance gate is the whole idea, and it is simple

For every number the model extracts, it must cite a locator and a verbatim quote. Then
plain string matching checks three things: the locator exists, the quote appears there, and
the number appears inside the quote. Anything that fails is dropped with a reason.

No second model. A model asked "is this right?" fails in the same places as the first one.
String matching against the source does not.

It worked on the first live paper: 52 out of 52 values verified on RECOVERY, 100% on the
Moderna trial. Against deliberately poisoned input it rejected a fabricated count, an
invented quote, and an invented confidence interval, while keeping a correct quote cited at
the wrong paragraph.

**Four refinements that mattered:**

**Counts need split citations.** Papers write "11 cases versus 185" in one sentence and the
per-protocol denominators a paragraph earlier. Requiring both in one quote threw away the
primary outcome of most vaccine trials. `Count` now carries an optional
`total_provenance`, verified the same way. This single change took the Moderna build from
81% to 100% and brought back the 2x2 scene.

**Never accept a sign the paper did not print.** The extractor wrote `-12.4` where the
paper says weight fell by "12.4%". Tempting to accept the magnitude and keep the sign as
metadata. Do not. Sign reversal changes clinical meaning. Fix the instruction instead:
transcribe the sign as printed, express direction through a separate field.

**Precision is part of the number.** `%g` renders 1.10 as "1.1", which then sits above a
quote saying "1.10". Match the precision the paper printed. When implementing this, only
ever *add* precision: our first version turned 0.83 into 0.8, because "0.8" is a substring
of "0.83".

**Not every verbatim span is worth showing.** A quote of `0.92 (0.84-1.01)` is technically
verbatim and completely useless. Require at least six words and forty characters before
putting a quote on screen.

## 4. Show the paper's own sentence next to the number

This is where the medical version diverges from arXivisual, and it took us until quite late
to see it.

A physics result stands as a bare number. A clinical one does not. "0.83" means nothing
without knowing it was a rate ratio, age-adjusted, for 28-day mortality, with an interval
clearing 1. The paper already says all of that in one sentence, hedged exactly as the
authors meant.

So the key-findings scene shows both: the number large, and the paper's own words beneath
it, with the value coloured where it appears in the sentence. The quote is the same span
the gate matched against, so a viewer is reading the literal evidence the figure was
allowed to be drawn from.

The quote was already being stored. We were checking it and then throwing it away for
display. Look for that pattern early.

## 5. Do not render the paper. Rewrite it

We shipped a reader that displayed all thirty original paragraphs verbatim. That is a PDF
with a video stapled to it.

arXivisual's `section_formatter.py` has the answer and we had not read it: summarise the
whole paper to roughly a third of its length, then reorganise into at most five sections
with titles that say what they contain. "How much weight actually came off", not "Results".

Measured on a narrative review: 4,375 words became 752 across five sections, about 17%.

Keep the original text one click away. The figures are verified against the source, never
against the rewrite, and a reader needs to be able to check.

## 6. Compose a deliberate arc, not whatever fits

Our first composer offered every template that matched the available data, sorted by
priority. For a trial report that produced six scenes with three of them restating each
other: a participant flow, a timeline, and a bar chart all saying what a design frame
already said.

The shape that works is the shape of the paper:

    the question  →  the method  →  the result  →  what the authors concluded

Supporting scenes get added only where they carry something the arc cannot. A forest plot
shows subgroup structure. A survival curve shows a time course. The full CONSORT flow earns
a slot when there is a screening funnel or more than 5% attrition, and not otherwise.

Two of the four arc scenes need no model at all. The design frame assembles from the
verified profile. The conclusion lifts verbatim from the abstract's own Conclusions block,
which is worth doing because a trial's conclusion is the sentence its authors chose most
carefully. Strip the trailing funding and registration parenthetical and nothing else.

## 7. Manim, in the order the problems appeared

**It renders fine.** A 5-animation 480p scene took 41 seconds cold, 3 to 6 seconds warm.
No Docker needed. Install `pango` alongside `cairo` or text rendering fails at import.

**Text loses its spaces below about 40pt.** "Usual care" renders as "Usualcare", and stray
gaps appear mid-word. This is the single most surprising thing we hit. The fix is to build
every `Text` at a fixed 72pt and scale the mobject down. Verified against IBM Plex and
Latin Modern at 15, 22 and 28pt.

**Manim only collects `Scene` subclasses whose `__module__` matches the file it scanned.**
A dynamically built class needs `Generated.__module__ = __name__` or you get "There are no
scenes inside that module" and an exit code of zero.

**Remux with `-movflags +faststart`.** Manim writes the index at the end of the file, which
stalls progressive playback over HTTP. It is a copy, not a re-encode.

**`t2c` must go in at construction.** Manim maps substrings to glyph indices during layout,
so calling `set_color_by_t2c` afterwards silently does nothing.

**No LaTeX needed for the 3blue1brown look.** Install the OpenType Latin Modern faces
(`brew install --cask font-latin-modern`). The family is `LMRoman10`, not "Latin Modern
Roman". It is Computer Modern, so titles match arXivisual without a TeX toolchain. You
lose real `MathTex`, which clinical papers rarely need.

**`pyttsx3` deadlocks under Manim's render loop on macOS.** It hangs indefinitely with no
error. Shell out to `say` instead and convert the AIFF with ffmpeg: about 1.4 seconds per
line, offline, free. Wrap it as a `manim-voiceover` `SpeechService` and everything else
works unchanged.

**SoX is a hidden dependency** of `manim-voiceover` for time-stretching audio.

## 8. Claude Code as an LLM backend

It works, and it means no API key. Each call is one `claude -p` with `--output-format json`.

**Strip the harness.** Replace the system prompt with `--system-prompt`, drop MCP servers
with `--strict-mcp-config --mcp-config <empty>`, and disable built-in tools. Left in, they
add about 34,000 tokens of irrelevant context to every call and invite the model to go read
files instead of answering. Stripped, the floor is around 18,500 tokens, and it is
cache-read, so on a subscription that is latency rather than billing.

**`--max-turns 1` is too strict.** A long structured reply spans turns internally and the
CLI exits with `error_max_turns`. Four is fine and still stops a runaway.

**Errors arrive on stdout, not stderr.** Our first error handler read only stderr and
reported "exit 1: no output" for a failure whose full JSON diagnosis was sitting in stdout.
We misdiagnosed it as a concurrency problem and serialised the calls for nothing. Read both
streams before concluding anything.

**No structured output.** Append the JSON schema to the prompt, validate with Pydantic,
retry with the validation error fed back. The provenance gate makes this safe: a malformed
extraction costs a retry, and a wrong number still gets dropped.

**No prompt caching you control**, so the paper text is re-sent per call. Extraction on a
long trial report runs five to twelve minutes on Opus. Set the timeout to 1200 seconds and
show an elapsed clock in the UI, or a working build looks hung.

**Cost comparison for a trial paper:** 4 to 7 minutes on the CLI, 2 to 4 on the API.

## 9. Rendering is not verifying. Look at the frames

Manim exits zero on scenes with overlapping text, missing elements and truncated labels.
Every one of the following passed tests and looked broken on screen:

- Forest and ladder axis ticks were built and never animated in, so they never appeared.
- Label and value columns overlapped because both used hand-tuned x offsets.
- A caption said "Hazard ratio" directly above a quote saying "rate ratio". The enum's
  canonical name had overridden the paper's own wording.
- "Symptomatic Covid-19 with onset ≥14 days after the second injection (per-protocol,
  baselin", a hard character slice, mid-word.
- "STEP 1: weight loss at… — STEP 1: Semaglutide…", the trial prefix twice in one card.
- Duplicated timepoints: "All-cause mortality at 28 days at 28 days".

Build a gallery harness that renders every template from a fixture on one command, and
actually open the images. `tools/render_gallery.py` paid for itself several times over.

**On truncation specifically:** our display caps were solving a problem the layout already
solved. Templates wrap text and `fit_into` scales the group down, so a long metric name
should go onto a second line, not lose its tail. Raise the caps, widen the wraps, and only
trim where a string would genuinely dominate the frame. When trimming, cut on a word
boundary and drop a trailing parenthetical qualifier first.

## 10. The automation browser cannot verify a frontend

Worth knowing before you plan any UI verification. In the Chrome instance available to the
agent:

- H.264 does not decode. A control file created with ffmpeg fails identically to ours, so
  the files were fine and the pipeline was not the problem.
- `scroll` events do not fire.
- `requestAnimationFrame` never runs.
- `IntersectionObserver` never fires, not even the guaranteed initial callback.

The page scrolls and geometry is correct, so `getBoundingClientRect` works. Real input
events through the `computer` tool do fire handlers. Screenshots after a real scroll are
the only reliable check.

This cost real time and produced one good outcome: we replaced an IntersectionObserver with
a scroll-position calculation, which is a better fit anyway. "Which section owns the reading
line" is a position question.

## 11. Smaller things that cost time

**Next 16's Turbopack dev server silently ignores `rewrites`.** No warning, no error, the
config loads fine. A proxy that works in `next build` and not in `next dev` is worse than
none, so the frontend calls the API directly with CORS.

**Never fade content in from `opacity: 0`.** If motion fails to run, the content is
invisible. Start at 0.35.

**Do not let one bad spec kill a build.** A composer bug produced a CONSORT spec with nine
arms against a template capped at four, and the ValidationError took down five good scenes
with it. Validate per scene, drop the failure with a note, carry on.

**Placeholder API keys pass a truthiness check.** `sk-ant-...` from the env template
reported as configured and then failed with a 401 several seconds into a build. Validate
the shape.

**Long-running polling shells kill their process group on timeout.** This killed the API
server and its in-flight build three times, and once left a stale server holding port 8000
while we believed we had restarted it. Poll in short bursts and check what is actually
listening.

## 12. What we would do differently

**Read the reference implementation properly before writing.** We read arXivisual's agent
pipeline and skipped `ingestion/section_formatter.py`, which contained the answer to the
biggest complaint about our output. Two-phase summarise-then-organise, sitting there the
whole time.

**Design the scene arc before writing templates.** We built eight templates and then
discovered the composition needed to be four scenes in a fixed order plus supporting
extras. Starting from the arc would have produced a different and smaller set.

**Store the verified evidence profile in the build output.** We saved scenes and the
provenance report, but not the profile they came from. Debugging "why did this scene not
appear" meant re-running a five-minute extraction.

**Write the visual regression harness first.** It was the most useful tool in the project and we
built it after the third template.

**Treat every caption as a claim.** Roughly half the bugs found by looking at frames were a
caption disagreeing with the paper it sat next to: the wrong measure name, the wrong
precision, a duplicated timepoint, a truncated outcome. The provenance gate protects the
numbers. Nothing was protecting the words around them.
