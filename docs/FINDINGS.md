# What we learned building this

Notes written so the next build can skip the dead ends. Ordered by subject, not by when
things went wrong.

The short version, twice over. In the first build the hard parts were not the parts that
looked hard: Manim rendered on day one, the provenance gate worked on its first live paper,
and what ate the time was upstream services that had quietly died and a dozen places where
a caption disagreed with the paper beside it. In the second build the pattern held. The
architecture was mostly right on paper; nearly every real bug was found by opening the page
and looking at it.

---

# The design

## 1. Medical papers are a better ingest target than arXiv

Everything else depends on this. PubMed Central serves JATS XML with sections, tables,
captions and figures already marked up, and every paragraph and table cell has an id.

That means a number can carry an address: `t2/r4/c3`, `sc2.2/p1`. Which means you can check
it. arXiv gives you a PDF and a prayer.

Get the JATS parser right before anything else. Stable locator ids are the foundation of
the whole design, and a parser that renumbers sections between runs silently breaks every
citation.

Publisher gotcha: some put a `<sec>` with a title and no prose (NEJM does this for "Methods"
and "Results"). Keep any section with a title.

## 2. The provenance gate is the whole idea, and it is simple

Every plotted value carries a locator and a verbatim quote. Three deterministic string
checks: the locator exists, the quote appears there, the number appears in the quote. No
second model, no judgment, a few milliseconds.

It is the one component that survived both builds untouched. Things it caught that nothing
else would have:

- **Sign inversion.** The paper printed "12.4%", the extractor wrote `-12.4`. Keep the gate
  strict and fix the instruction.
- **Split citations.** Papers state "11 cases vs 185" in one sentence and the denominators
  in another. Adding a separate `total_provenance` took one build from 81% to 100%.
- **The paper's minus sign.** Publishers set a negative with a typographic minus (U+2212)
  or an en dash. The normaliser folded those for the quote match, but the number reader
  ran on the raw quote, so a printed "minus 8.7" read as 8.7 and every negative value in
  SELECT failed against the very sentence that printed it. Three rebuilds and a repair
  round could not fix what was a gate bug: fold the dashes before reading numbers. When
  a whole class of values keeps failing, suspect the gate before the model.
- **Precision drift.** A formatter turned 0.83 into 0.8. Only ever add precision, never
  round.

Normalise before matching: publishers use seven kinds of dash, four kinds of quote and six
kinds of space.

## 3. Show the paper's own sentence next to the number

Hovering any mark shows the span the gate matched against. This is not decoration. It is
the difference between "trust me" and "here is the sentence, judge for yourself", and it
costs one field on the datum.

## 4. Do not render the paper. Rewrite it

Two phases: summarise the whole paper to about a third, then organise that into at most five
titled sections. Summarise-then-organise beats section-by-section, because a per-section
summary cannot know what the paper is for.

## 5. Removing the renderer removed most of the failure surface

Chart specs as data instead of generated Manim code deletes the code generator, the static
gate, the spatial validator, the render tester, the repair loop, the subprocess and the MP4.
A build went from minutes of rendering to one LLM call plus a deterministic check. Nothing
downstream can invent a number or produce an unrenderable scene, because the frontend draws
from a validated schema.

This is also why generated SVG is a trap. It is the same shape of problem under a new name.

---

# Ingest and sources

## 6. Assume every hardcoded NCBI URL is stale

Three moved or died across two builds.

- The PMC OA Web Service (`oa.fcgi`) now returns a 404 diagnostic page.
- The ID converter moved to `pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/`. The old
  path still 301s, and the ingest only worked because httpx was constructed with
  `follow_redirects=True`. A redirect is not a contract.
- `/pmc/articles/PMCxxxx/bin/<file>` 404s for figure images.

Check the endpoint before debugging anything downstream of it.

## 7. A PMC record is not a paper

PMC serves plenty of records with metadata only: editorials, author manuscripts still
embargoed, deposits where only the abstract was released. `fetch_jats` accepted anything
containing `<article>`, which those do, so a body-less record sailed through, produced an
explainer with zero sections and got **stored** — caching the emptiness so a retry returned
it instantly.

Count words inside `<body>` rather than trusting the tag. Try both sources and keep the one
with more body text, because E-utilities returns body-less articles where Europe PMC
sometimes has the text. Below 250 body words, refuse and say why.

Related: an empty build is an error, not a result. No sections and no charts returns 502
rather than storing a blank page.

## 8. Open access is not the same as deposited in PMC

Sampling 104 papers carrying PubMed's "free full text" flag across 26 subspecialties:

    buildable    62.5%
    not in PMC   26.9%
    refused       7.7%   (metadata-only records)
    thin          2.9%

Within the open-access filter proper it is 76/76 across 38 subspecialties. Papers **in PMC
but outside the OA subset** also work: `efetch` returns a full body for them. Coverage is
"in PMC at all", which is wider than the OA subset.

For the 27% that are not in PMC, five routes were tried against ~70 papers. Unpaywall gave
a working PDF for 2 of 50; retried properly with a browser User-Agent and redirects
followed, **0 of 8** — all 403 from Wiley, Oxford, Elsevier, Healio, Hogrefe,
Bioscientifica. OpenAlex knows they are gold or diamond OA under CC-BY and lists no PDF.
Europe PMC returns 404 by PubMed id. Crossref advertises text-mining links that point at
the same blocked endpoints.

So the papers are open access and the full text is not machine-reachable. Making it
reachable would mean defeating bot protection, which is not a thing to build.

Say this accurately when it happens. The old message ended "Try an open-access paper" at a
reader whose paper already was one. Ask OpenAlex and name the actual case. The DOI needed
for that lookup arrives empty exactly when it is needed, because the id converter has no
record for a paper PMC never took, so fetch it from PubMed on the failure path.

## 9. Publishers block programs, not people

The way through is that the restriction is not on the reader. They can open any of these in
a browser and download the PDF, because that is what "free downloadable" means. So they hand
over the file and the same pipeline runs on it.

JATS gives stable ids for every paragraph and table cell. A PDF gives a stream of text, so
locators are synthesised per paragraph and **table cells are not addressable**: a number
printed only inside a table cannot be cited and will not survive the gate. The gate and the
output contract are unchanged. The page says which tier it came from.

## 10. One PDF is not a test of PDF support

The tier worked on the first file tried, a PLOS trial, so it looked finished. Across six
publishers, only PLOS worked.

- **Markdown leaking into the text the gate matches against.** The serious one. A phrase
  left as `**significant**`, a heading as `# Results`, a link as `[Figure 1](https://...)`
  cannot be quoted by anything, so every number inside fails the gate. The paper builds,
  looks fine, and quietly charts less than it should. Strip markdown before the text goes
  anywhere. Turn table pipes into spaces rather than dropping them, so a sentence quoting a
  table number can still match.
- **A crash is not a reason to refuse a paper.** pymupdf4llm raised `no font file for
  digest` on eLife. Falling back to plain page text loses heading levels and keeps
  everything else: exception to 16,000 words and four verified charts.
- **Publishers disagree about what a heading looks like** — markdown, bold, or capitals.
  Recognising only the first put the whole body of three papers into one section.
- **The first long line on page one is the running citation.** "Gerum et al. eLife
  2022;11:e78823" is stamped on every page, and a real title wraps over two or three lines
  beneath it. Prefer the PDF's own metadata, which publishers fill in reliably; when empty,
  skip running heads and rejoin wrapped lines until the author list starts.
- **A correction is not a paper.** "Author Correction: ..." parses perfectly, clears the
  word threshold by a handful of words, and produces an explainer of nothing.

After: PLOS, BMC, Frontiers, eLife, Nature and Scientific Reports all extract with correct
titles and no markdown leakage, verifying 11/13 to 23/23 — where JATS lands, which is the
number that says the gate still works on synthesised locators.

## 11. The paper's own figures are fetchable again

The first build concluded they were not. Half right: the routes it tried are dead, but the
PMC article page references its figures on a CDN at
`cdn.ncbi.nlm.nih.gov/pmc/blobs/<hash>/<id>/<hash>/<file>`. The hashes are not derivable, so
read the page and match blob URLs by filename against the JATS `<graphic xlink:href>` values
— which the parser had been discarding entirely. Europe PMC's `supplementaryFiles` zip is
the fallback for publishers who bundle figures into it.

Europe PMC answers the licensing question by itself with "Article with id ... is not open
access one". Both routes serve the open-access subset only, the same set the ingest already
requires, so there is no separate licence check to write.

---

# What goes on the page

## 12. What earns a figure a place is whether you could redraw it

The first rule said: take imaging and schematics, skip data figures because charts handle
data. Wrong in an instructive way. A Kaplan-Meier plot *is* data, but the paper prints a
hazard ratio and a final percentage, never the curve. The shape of the separation exists
only in the figure.

The rule that works: could you rebuild this from numbers the paper actually prints? CONSORT
diagram, forest plot, bar chart — yes, so chart it. Radiograph, histology, mechanism
diagram, Kaplan-Meier curve — no, so show the figure.

Given that rule the planner chose correctly on both trials unprompted: it took the survival
curve and declined the enrolment diagram and the subgroup forest it was already charting.

Two smaller points. Choosing figures belongs in the chart-planning call, because the model
that just decided to draw a forest plot is best placed to know not to also show the paper's.
And the caption must be copied from the JATS rather than written by the model: structural,
not checked, so no generated sentence can reach the page wearing the paper's voice.

Name the classification vocabulary carefully, because the badge is user-facing. Offering
`imaging | schematic | data` made the model label Kaplan-Meier curves "schematic", a word
that means something else to a clinical reader.

## 13. An arrow is a claim, so it can carry a citation

A mechanism is a graph. Nodes are things, edges are claims about how they relate, and a
claim is exactly the object the gate was built for. So a diagram is a chart kind with nodes
and edges rather than data, rendered deterministically. No generated code, no pixels.

Each edge carries provenance and is checked with the same machinery, plus one addition:
**one sentence inside the quote must name both ends of the arrow.** Requiring a single
sentence is what makes it worth anything — two terms three sentences apart are two topics,
not a relationship. Term matching is prefix-based at five characters, so "inflammation"
finds "inflammatory" without a stemmer.

If an edge fails, the whole diagram goes. A mechanism with a hole in it is a claim about the
paper that the paper does not make.

## 14. Hedging and negation are the two ways a diagram lies

Neither is about wrong data. Both are a clean picture saying more than the sentence behind
it.

**Hedging.** Papers write "may reflect", "suggests", "is consistent with". A solid arrow does
not hedge. So `hedged` is derived from the quoted wording, never supplied by the model, and
drives a dashed arrow. The model cannot forget to flag a hedge because it is not asked to.

**Negation.** Found by writing the adversarial test, not by reasoning. "We found no evidence
that corticosteroids reduce mortality" contains both endpoint terms in one sentence, passes
the link check, and draws the arrow backwards. Drop any edge whose only linking sentence is
negated — drop rather than hedge, because string matching cannot tell whether the model read
the negation or missed it.

Still unchecked: whether the sentence asserts the *direction* the arrow points. That stays
the model's assertion, which is why the hover is load-bearing rather than a nicety.

## 15. A chart's encoding is a claim, and claims need checking

The gate verifies numbers. Nothing verifies what the picture says about them.

- **Direction is per-row, not per-chart.** A secondary-outcomes forest held "discharged alive
  within 28 days" (a benefit above 1) beside three mortality ratios (benefits below it). One
  chart-level flag painted the best result as a harm.
- **Colour means something across the page, not within one chart.** Teal and rust meant
  "dexamethasone vs usual care" in one chart and "ventilated vs oxygen only" two charts
  later.
- **Grouped data drawn flat repeats every label.** Three categories in two arms became six
  independent bars, each labelled, colliding.
- **Precision should be shared across a chart.** The paper printed 14.0% beside 41.4%;
  trimming the trailing zero reports a different number of significant figures than the
  source.

## 16. A prompt can be so careful it produces nothing

The first diagram guidance was written to prevent invention and worked perfectly: two
papers, zero diagrams, including one that argues a textbook mechanism in its Discussion.

The cause was tone across three places. "Returning no diagram is the right answer far more
often than not" sat inside a prompt opening "You are a transcriber, not an analyst", with
the option buried seventh in a list.

What fixed it without loosening a rule: qualify the opener, say where mechanisms live, give
a worked example of the shape, and cut the discouragement while keeping the guardrail. The
vaccine paper still declines, because its Discussion argues no mechanism. That
discrimination is the point.

Guardrails and discouragement are different things, and it is easy to write the second while
intending the first. Zero is a suspicious number.

## 17. Layout bugs only appear with real content

Every one of these looked fine on demo data.

- **A stretched grid column with one chart in it is mostly void.** Prose ran 618–1387px
  against charts of 270–500px. Pin a lone chart while its prose scrolls; two charts in a
  column are close enough to prose height to leave alone.
- **A figure needs the width a chart does not.** A plate authored at 1600px says nothing at
  590, and a case report's prose is far shorter than its imaging is tall. Full content
  width, bounded height, on a white plate that hugs the image, because radiographs are
  authored on white and dimming them changes what the reader sees.
- **Sizing a container by item count breaks when items merge.** The flow chart reserved a row
  per datum, then drew a split pair as one row, leaving a screen of black.
- **Circular sizing deadlocks.** A plate sized to its content holding an image sized to the
  plate: an unloaded image has no width, so the plate collapsed to its padding, so the image
  never grew enough to enter the viewport and start loading.
- **`overflow-visible` lets text escape the card.** An annotation written past the viewBox
  edge ran off the page.
- **Ellipsis truncation is never the answer.** "Invasive mechanical venti…" is not the same
  label. Wrap at word boundaries and give the container the height.
- **Units need a space unless they are symbols**: "162 cases", "95%".

## 17a. Measure overlap in the DOM, then fix the layout, then measure again

"The charts overlap when packed" is a report, not a finding. The finding came from a
script run on every built page: for every chart, every text element's bounding box, every
pair checked for intersection, plus anything outside its card. Twenty pages, seven
distinct causes, none of which a screenshot would have separated:

- **Five or more categories, or long names, under vertical bars.** Wrapping cannot save
  labels that share 90px. Packed charts go horizontal: a label column, a row per category,
  values at the bar's end. Nothing in a row can touch anything in another.
- **Dots drawn for grouped data** repeated every category label once per arm. Two arms is
  a comparison, so it is bars.
- **Value labels wider than their bar** collided within a grouped pair. Lift every second
  one a line.
- **Negative values** hung below the axis into the category labels. Horizontal bars draw
  from a zero line in either direction.
- **The line chart placed ticks by unique values rather than timepoints**, and centred
  the last label on the right edge. Timepoints from labels, ends anchored inwards.
- **Diagram edge labels** sat at the elbow between rows and reached the row below when a
  gap held three of them. Each label now sits in the gap under its own source box, the
  gaps grow to hold what they carry, and the horizontal run sits just above the target.
- **A bar chart's annotation** lived in a plot corner and met a value label. It has a band
  of its own above the plot.

Two more from the same pass that were not overlaps: a figure with no reported width and
height rendered at native size and ran over two screens (cap the image at 74vh whatever
the metadata says), and the rewrite emitted a markdown table that the prose renderer
showed as pipes (render pipe tables). The audit script is the regression test; the fix
is not done until it reports nothing on every page.

## 17b. Link prose to charts by the printed number, never by a model

The scrollytelling pattern everyone copies from the Pudding is "as this paragraph arrives,
that mark lights up". The temptation is to ask the model which sentence goes with which
mark. Do not. The chart value and the sentence both carry the printed number, so the link
is a string match: the sentence contains the value, and either names what the value is
(a label word, prefix-matched) or sits in the chart's own section. One link per sentence,
best score wins, and a sentence that only shares a number with a chart in another section
does not link, or "22.9 years" lights the mortality bar. On SPRINT this finds 8 sentences
across 4 charts with no false links; on the dexamethasone paper 11.

The band that counts as "being read" matters more than it looks. Centre ±7% of the
viewport lit nothing when a sentence sat where the eye actually rests; 30% to 60% down
the screen does. Only the section that lit a chart may put it out, or two sections'
observers fight over one state at the boundary.

The Cochrane icon array is the one medical visualization with evidence behind it, and it
is worth its own contract: two arms, each with its own quote, both through the gate, and
everything derived from them (per 1,000, difference, number needed to treat) computed
once on the API and carried as derived. The words have to follow the outcome's
direction: "spared by the treatment" is right for deaths avoided and wrong for people
who reach a weight-loss target because of the drug.

Colour is the relation, and it has to be scarce to be one. The first pass coloured every
arm name on the page in the arm's colour, gave the comparator its own hue (rust) and put
a coloured bar beside every linked sentence. It looked coloured and meant nothing: on
SPRINT the prose said "intensive" in teal and "standard" in rust beside a forest plot that
used neither, and the numbers the sentence was about carried no colour at all. Two
findings from the literature explain why. Readers look first at the most saturated thing
in view, and de-emphasising with a second hue reads as a second category rather than as
"less important"; grey is what says "context" (Datawrapper, "Emphasize what you want
readers to see with color"). And highlighting in text helps recall only when it is
selective, one or two marks per paragraph; paint everything and the benefit is gone
(Dunlosky et al. 2013; Yue, Storm, Kornell and Bjork on the amount of highlighting).

So the rule is now three colours with three meanings and nothing else. The treatment and
whatever favours it in a strong green; the comparison in grey, so the treatment bar is what the eye
lands on; harm and caveats in a strong red. A single-series bar whose label names an arm takes
that arm's colour, a forest plot saturates its primary row and desaturates the rest (same
hue, never a new one), and the icon array greys the people the outcome reaches either
way. In the prose, colour appears in exactly two places: inside a sentence joined to a
chart, where the charted figures and the arm they belong to take the mark's colour, and
once in the bottom line, where the effect (the percentage when there is one) is the
page's single highlight. Arm names elsewhere are plain. The linked-sentence bar is grey
until the sentence is read, then takes the mark's colour with the wash and the card edge,
so at any moment one sentence on the page holds colour. The text variants are brighter
twins of the fills, because a fill that reads on a bar reads dim as type, and the colour
comes from the same function the chart draws with, so the two cannot drift apart.
Anything pressable is a pill with a lift on hover; only the bottom line's is strong.

The lit relation looked broken for a reason that was not in the CSS. The pipeline linked
prose to charts before it attached charts to sections, so at link time no section had a
chart and "the chart beside this section" was never true; and the planner pins a chart by
topic while the sentences that print its numbers sit elsewhere (SPRINT's hazard-ratio
chart beside "the question", the three sentences quoting 0.75 two sections down). The
reader rightly refuses to light a mark two screens away, so 6 of 8 links died on the
page. Now charts are attached first, the linker prefers a chart on screen over a
better-named one elsewhere, and a chart whose own section never mentions it moves to the
section that does, then the linker runs again. All string work, so `scripts/relink.py`
applies it to every stored paper without a model call: SPRINT 2 to 8 sentences shown,
and the sixteen older papers went from none to real links.

A chart the model is free to shape is a chart that will be cluttered. Diagrams came back
with six nodes, crossing arrows and arrow labels a sentence long, and the renderer's
layered layout put three labels in one gap and let a label overflow its box (the last
wrapped line was allowed to run 1.5 times the box width). The fix is not a smarter
layout. It is a catalogue of blocks, each with one fixed layout and hard limits, shown to
the model as one line of what, one of limits and one example, so it fills a block with
quoted numbers and never decides how anything is drawn. `fit_to_block` trims an over-full
proposal before validation, one chart at a time, so one bad chart no longer costs the
whole planning call, and a diagram is reduced to the shape that keeps the most arrows:
chain, fork or join. Three shapes, three layouts, nothing to collide. The prompt lost
about a third of its chart section in the process, which is tokens the model spent
choosing shapes it could not draw well.

The lit relation also had a behaviour bug on top of the linking one: a sentence was lit
only while inside a band from 30% to 60% of the viewport, so the chart blinked on and off
as the reader scrolled, and on a diagram the lit thing was a label glow. Now the last
linked sentence stays lit until the next takes over or its section leaves the screen, and
a lit arrow turns green and thick while the rest fade; the nodes never fade, because a
diagram with its boxes dimmed cannot be read.

Showing the whole chart (no fading) is what made the linker's false matches visible, and
there were five kinds. A shared interval bound (0.64 on two forest rows); a row whose
estimate equals another sentence's bound (stroke 0.89); the nulls 0 and 1 ("the whole
interval lies below 1" lit the row whose estimate is 1); a digit glued to a name (KOOS4
read as 4, 44.9 points read as 45 events under the rounding tolerance); and small counts
that coincide (13 knees with arthritis, 13 knees with a normal Lachman test; 8% against 8
events). The rules now: a link needs the estimate or a count, never a bound alone and
never 0 or 1; estimates get rounding tolerance, counts are exact; a digit joined to a
letter is part of a name; a count never matches a percentage; a small count alone links
only when the sentence names the datum; every shared number counts double; and two shared
numbers link on their own, after which the chart moves beside the sentence. Each rule
has a test with the sentence that broke it.

The finding in the bottom line was picked by a regex (first percentage, else first decimal,
else first number), and on KANON it lit "95%" in "95% CI". A guess about which number is
the finding cannot be made reliable, so it is no longer made: the planner names the
`effect` (the figure in the answer that states the finding, copied as printed) and a
`verdict` (better, worse, no_difference, mixed, as the paper concludes), the gate keeps
the effect only when it is in the answer and its number is in the quote, and the page
highlights that or nothing, green for better, red for worse, white for no difference.
The three examples came back with "2.0 points" (no difference), "25%" (better) and
"-8.7%" (better).

The prose is now held to the charts' standard, sentence by sentence. Each sentence of the
concise version is anchored to the source sentence that prints its numbers and shares
its terms, or marked as unsupported, and opposite direction words are flagged. Across
the fourteen PubMed papers, 66 to 76 percent of sentences anchor; the rest are the
model's connective tissue or paraphrases that keep no number and fewer than four terms.
The badge says the count, and a click on an anchored sentence opens the paper at that
sentence, highlighted.

The paper itself was the hard part. PubMed Central blocks scripted PDF downloads on
every endpoint tried (Europe PMC's render service 403, both PMC PDF links return HTML,
with a browser user agent too), which is finding 9 again. So the viewer has two sources:
the PDF when the reader supplies it (uploaded, or dropped onto the page later) and the
paper's verbatim text otherwise, which we always hold. Both open at the sentence. Two
things about PDF.js cost an hour: text items split mid-line and need a space between
them before the quote can be found, and display rendering waits for an animation frame
that a hidden tab never gets, so the page rendered never; print intent draws at once.
The synthetic PDF used to exercise the viewer was made from the paper's own text with
PyMuPDF and removed afterwards; no real PDF was fetched.

"100% of charted values verified" is a rule, not a rate. A value that fails the gate is
never drawn, so the badge now says "All N charted values verified" and counts dropped
proposals separately; "65% verified" had read as though a third of the page were
unchecked. What can still be raised is how many of the model's values survive, and the
commonest failures (a quote from the wrong sentence, a sign the paper does not print)
are fixable by showing the model where the number actually is. One repair round hands
the rejected values back with the paper's own paragraphs and runs the gate again on the
same terms. It only ever adds verified values; the bar does not move. The bottom line gets
the same second chance, and may be shortened to drop a number the paper does not print,
never lengthened. On SELECT the first rebuild after this lost its bottom line to a
"week 65" absent from the quote; that is the case the round exists for.

A watcher that outlives its own timeout takes the servers with it. The harness kills a
timed-out background task's process group, and a server started from the same shell is
in that group. Start servers in their own session, and keep polling loops shorter than
the limit that would kill them.

A section with nothing to draw beside it reads as one wide column at a measure the eye
can follow, and a chart column is pinned whenever it fits on screen, measured rather than
counted: two short charts beside a long section used to leave a screen of black.

A popover that is invisible is still laid out. Three closed term popovers, 300px each,
beside terms near the right edge gave a phone a horizontal scroll. `display: none` until
open, and on a phone a sheet at the bottom rather than a box beside the word.

## 18. Never let content depend on an animation firing

Scroll-triggered reveals worked for the two charts above the fold and left four below it
invisible, because the browser never delivered a scroll event. The fix is not a better
trigger, it is a deadline: reveal on scroll, and turn everything on unconditionally after
2.5 seconds.

It bit twice. The second time the content behind the animation was a radiograph, stuck at a
`CSSTransition` frozen at `currentTime: 0` — image fully loaded, completely invisible.
Charts may animate their marks; a photograph may not wait on a transition.

---

# Operations

## 19. Inherited code carries the previous product's assumptions

A fork starts with someone else's decisions embedded where they do not announce themselves.

- The root layout shipped SEO for a public site: canonical host, `index: true`, the original
  authors' names, plus Vercel Analytics beaconing page views. On a private local tool that
  is an outbound leak of what you are reading.
- `create_async_engine` was called with `pool_size` under a comment saying it was "ignored
  for SQLite". SQLAlchemy raises, so the default local path failed at import.
- The rewrite prompt asked for LaTeX, right for arXiv and useless here: nothing renders math,
  so `$$\text{VE} = 100 \times (1 - \text{IRR})$$` reached the page verbatim.
- The prompt had no writing rules, so prose came back with "genuinely protective" and
  "pivotal clinical trial" in one paragraph.
- Section bodies were cut at a hard 3000 characters, mid-word.
- CORS listed dead public hosts, allowing an origin nobody controls any more to read the API.

Grep a fork for the old product's name before trusting anything, and read the prompts as
carefully as the code. They are the part most likely to be silently wrong for the new domain.

## 20. A health check that only proves a dependency is installed reports healthy through every interesting failure

Builds were failing everywhere with `"result": "Not logged in · Please run /login"`. Health
reported `claude_cli` and **healthy**, because the check was `shutil.which("claude")`.

The cause was a missing environment variable. With `HOME` and `PATH` alone the CLI says "not
logged in"; adding **`USER`** fixes it, and a GUI launch or stripped service environment is
exactly where `USER` goes missing. Fill in `USER`, `LOGNAME` and `HOME` for every subprocess,
and make health run a real authentication probe, cached per process. Failure is fast when it
fails, so the probe costs nothing in the broken case.

## 21. A GUI launcher runs in a different world than your terminal

Finder hands a GUI app `PATH=/usr/bin:/bin:/usr/sbin:/sbin`. No Homebrew, no `node`, no
`npm`, no `claude`. Test a launcher the way it will be launched:

    env -i HOME="$HOME" PATH=/usr/bin:/bin:/usr/sbin:/sbin ./App.app/Contents/MacOS/App

Nothing else reproduces it. And a GUI app has nowhere to print, so every failure path needs
`osascript` or it fails into a void.

## 22. A listening port is not your service

The launcher treated anything on 8000 or 3000 as "already running". Port 3000 is the default
for every Node dev server and 8000 for every Python one. With `python3 -m http.server` on
both, the app reported "already running" and would have opened the browser onto a stranger's
directory listing.

Identify the service, do not just knock: health carries `"app": "paperinfive"`. And step past
an occupied port rather than adopting it. Scan order matters — look for **our** instance
across the whole span first, then for a free port, or a second copy starts on the free base
port while the first keeps running.

Moving the port then broke CORS, and the way it failed is the lesson. Everything came up
healthy, the page loaded, looked completely normal, and listed **nothing**: `allow_origins`
was hardcoded to `http://localhost:3000`. A hardcoded origin is a hidden dependency on a port
number, invisible until the port moves.

## 23. Claude Code as an LLM backend

`claude -p --output-format json` works as a provider with no API key. Points that cost time:

- `--max-turns 1` fails with `error_max_turns`. Use 4.
- Errors arrive on **stdout**, not stderr. Reading only stderr made a login failure look like
  a concurrency problem.
- Strip the harness: `--strict-mcp-config`, an empty `--mcp-config`, and disallow every tool.
  It is a text task, and a model that can reach for Bash will.

## 24. Smaller things that cost time

**Next 16's Turbopack dev server silently ignores `rewrites`.** No warning. The first fix
was to call the API directly with CORS, which made the API port part of the build; the
lasting one is the route-handler proxy described below.

**Long-running polling shells kill their process group on timeout.** This killed the API and
its in-flight build several times, and once left a stale server holding port 8000 while we
believed we had restarted it.

**Placeholder API keys pass a truthiness check.** `sk-ant-...` from the env template reported
as configured and failed with a 401 seconds into a build. Validate the shape.

**Do not let one bad spec kill a build.** Validate per item, drop the failure with a note,
carry on.

**Next's rewrites are decided at build time.** `rewrites()` in `next.config` is evaluated
by `next build` and written into the routes manifest, so an API port read from the
environment at `next start` is ignored. A route handler under `app/api/[...path]` forwards
at request time instead, and the port becomes plain runtime configuration.

**Node's fetch will not forward an `Expect` header.** curl adds `Expect: 100-continue` to
any large POST, and the proxy answered 502 to every upload over a few hundred kilobytes
while browsers, which never send it, worked. Drop it with the other hop-by-hop headers.

**`-nt` compares whole seconds.** A stamp file touched right after `npm install` is not
newer than the lockfile npm rewrote in the same second, so the install ran on every start.
Record the lockfile's checksum instead.

**A bash trap waits for the foreground command.** `trap ... TERM; sleep 3600` holds the
signal until the sleep ends. Ctrl-C in a terminal only worked because it hit the sleep
too. `sleep 3600 & wait $!` returns as soon as the signal arrives.

**A label is not a React key.** The same category legitimately appears once per group, and
React then drops or duplicates marks. That duplicate-key warning was the grouped-bars bug
announcing itself in a form easy to dismiss as noise.

## 25. Verify in the browser, not in the typechecker

`tsc` and `eslint` were clean through every layout bug above. Read the console warnings, and
measure the DOM when something looks wrong rather than guessing from a screenshot. Two
minutes of `getBoundingClientRect` over every section found the stretched-column problem that
several screenshots had failed to explain.

The automation browser has its own limits: no rAF, so CSS transitions freeze at time zero;
screenshots do not follow JS scrolling; it cannot decode H.264. Real `computer` input does
fire handlers.

---

# From the first build, which rendered video

Kept because the lessons outlived the code.

**Manim drops inter-word spaces below about 40pt.** "Usual care" renders as "Usualcare".
Build every `Text` at 72pt and scale down.

**`t2c` applied after construction is a no-op.** It must be a constructor argument.

**pyttsx3 deadlocks under Manim on macOS.** Shell out to `say` and convert with ffmpeg.

**Rendering is not verifying.** Roughly half the bugs found by looking at frames were a
caption disagreeing with the paper beside it: wrong measure name, wrong precision,
duplicated timepoint, truncated outcome. The gate protects the numbers. Nothing was
protecting the words around them.

**Read the reference implementation properly before writing.** We read arXivisual's agent
pipeline and skipped `ingestion/section_formatter.py`, which held the answer to the biggest
complaint about our output.

**Store the verified evidence profile in the build output.** Debugging "why did this scene
not appear" meant re-running a five-minute extraction.

---

# Running it

Three ways in, all idempotent, all reusing whatever is already listening:

- **`PaperInFive.app`** — double-click, or keep it in the Dock. Starts what is down, opens the
  browser, and if everything is already up offers Open or Stop. Failures surface as dialogs.
- **`start.command`** — the same from Terminal, with live output and Ctrl-C to stop. Better
  when something is wrong and you want to watch it.
- **A PDF you downloaded** — "open the PDF" on the landing page, for the roughly quarter of
  PubMed's free full text that PubMed Central never took.

First run installs the API's packages with `uv`, the web app's with `npm`, and builds the
web app, each skipped afterwards while its lockfile checksum matches. A changed source file
triggers a rebuild on the next start, and the running web server is restarted onto it.

Both launchers resolve ports through `scripts/launch-lib.sh`: our own instance is reused
wherever it is, an occupied port is stepped over, and the web app is told which API port to
call. Defaults 8000 and 3000, twelve ports of headroom each. Logs in `logs/api.log` and
`logs/web.log`.
