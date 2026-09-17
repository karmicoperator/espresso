"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { A_FILL, ArmsContext, B_FILL, C_FILL, ChartFigure, datumColour, textColour, type Lit } from "./ChartFigure";
import { FigureFigure } from "./FigureFigure";
import { ReadingRail } from "./ReadingRail";
import { RiskFigure } from "./RiskFigure";
import { SourcePanel } from "./SourcePanel";
import type { Chart, Explainer, FigurePlate, Link as ProseLink, Provenance, Term } from "@/lib/types";

/**
 * The explainer: at most five rewritten sections, each with the charts that belong to it.
 *
 * Prose in a narrow column on the left, charts wide on the right, with a full-bleed rule
 * and a serif title between sections. Borrowed from Nature's immersive layout, which uses
 * the section break to reset attention rather than to decorate.
 *
 * The prose and the charts are joined: a sentence that states a plotted value is linked
 * to that mark on the API (by the printed number, not by a model), and as the sentence
 * reaches the middle of the screen the mark stays lit while the rest of its chart steps
 * back. Clicking a mark, an arm of the risk figure or the bottom line opens the paper's
 * own paragraph in a side panel.
 */
export function ExplainerReader({ explainer }: { explainer: Explainer }) {
  const byId = useMemo(
    () => new Map(explainer.charts.map((c) => [c.id, c])),
    [explainer.charts],
  );

  // Charts the planner never pinned to a section still have to appear somewhere.
  const placed = new Set(explainer.sections.flatMap((s) => s.chart_ids));
  const orphans = explainer.charts.filter((c) => !placed.has(c.id));

  const figById = useMemo(
    () => new Map((explainer.figures ?? []).map((f) => [f.id, f])),
    [explainer.figures],
  );

  // Numbers the prose uses that the paper does not print, per section, for marking.
  const unprinted = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const u of explainer.verification.prose_unmatched ?? []) {
      m.set(u.section_id, [...(m.get(u.section_id) ?? []), u.number]);
    }
    return m;
  }, [explainer.verification.prose_unmatched]);

  const linksBySection = useMemo(() => {
    const m = new Map<string, ProseLink[]>();
    for (const l of explainer.links ?? []) m.set(l.section_id, [...(m.get(l.section_id) ?? []), l]);
    return m;
  }, [explainer.links]);

  const terms = useMemo(() => explainer.terms ?? [], [explainer.terms]);

  // The page's arms, intervention first: from the verified risk pair when there is one,
  // else the first chart that compares two groups. Every chart and every mention in the
  // prose colours by this order.
  const arms = useMemo(() => armsOf(explainer), [explainer]);

  const words = explainer.sections.reduce((n, s) => n + s.markdown.split(/\s+/).length, 0);
  const minutes = Math.max(1, Math.ceil(words / 230));

  const [lit, setLit] = useState<Lit | null>(null);
  const [source, setSource] = useState<{ prov: Provenance; value?: number } | null>(null);
  const openSource = useCallback((prov: Provenance, value?: number) => setSource({ prov, value }), []);
  const closeSource = useCallback(() => setSource(null), []);

  const meta = [
    explainer.journal,
    explainer.published?.slice(0, 4),
    explainer.paper_id,
  ].filter(Boolean);

  // The tab should say which paper this is, not only which app.
  useEffect(() => {
    document.title = `${explainer.title} · Paper in Five`;
    return () => {
      document.title = "Paper in Five";
    };
  }, [explainer.title]);

  const v = explainer.verification;
  const proseMisses = v.prose_unmatched?.length ?? 0;

  return (
    <ArmsContext.Provider value={arms}>
    <main>
      <ReadingRail sections={explainer.sections.map((s) => ({ id: s.id, title: s.title }))} minutes={minutes} />

      <header className="border-b border-white/[0.08]">
        <div className="mx-auto max-w-[1180px] px-8 py-12">
          <div className="print-hide flex items-baseline justify-between gap-4">
            <Link href="/" className="pill">
              ← Build another paper
            </Link>
            <button type="button" onClick={() => window.print()} className="pill">
              Print or save as PDF
            </button>
          </div>
          <h1 className="mt-5 max-w-4xl text-3xl leading-snug font-medium tracking-tight text-[#e8e8e8]">
            {explainer.title}
          </h1>
          <p className="num mt-3 text-xs text-white/30">
            {meta.join(" · ")}
            <span className="text-white/20"> · {minutes} min read</span>
          </p>
          {explainer.authors.length > 0 && (
            <p className="mt-2 max-w-3xl text-xs text-white/40">
              {explainer.authors.slice(0, 6).join(", ")}
              {explainer.authors.length > 6 && ` and ${explainer.authors.length - 6} others`}
            </p>
          )}
          <div className="num mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
            {explainer.source_url && (
              <a href={explainer.source_url} target="_blank" rel="noreferrer" className="pill">
                Read the original ↗
              </a>
            )}
            {explainer.doi && <span className="text-white/30">doi:{explainer.doi}</span>}
            {/* Every value drawn passed the check; that is a rule, not a rate. What varies
                is how many of the model's proposed values survived, which is said
                separately so the badge never reads as "a third of this page is unverified". */}
            {v.checked > 0 && (
              <span
                className="rounded-full border px-2.5 py-0.5 text-[#7dd19b]"
                style={{ borderColor: "rgba(255,255,255,0.10)" }}
                title="A value that fails the check against the paper is never drawn"
              >
                All {v.passed} charted values verified
              </span>
            )}
            {v.checked > v.passed && (
              <span className="text-white/35" title="Proposed by the model, not found in the paper as stated, and left out">
                {v.checked - v.passed} proposed {v.checked - v.passed === 1 ? "value" : "values"} dropped
              </span>
            )}
          </div>
          {/* What was checked and what was not, in one line, because "verified" on its own
              reads as a claim about the whole page. */}
          <p className="mt-4 max-w-3xl text-xs leading-relaxed text-white/40">
            The summary below was written by a model from the paper. Every charted value was
            checked against the paper&rsquo;s own text before it was drawn
            {v.prose_checked
              ? proseMisses
                ? `; ${proseMisses} of the ${v.prose_checked} numbers in the prose ${
                    proseMisses === 1 ? "is" : "are"
                  } not printed in the paper as such and ${proseMisses === 1 ? "is" : "are"} `
                : `; all ${v.prose_checked} numbers in the prose are printed in the paper`
              : ""}
            {v.prose_checked && proseMisses ? (
              <span className="unprinted">marked like this</span>
            ) : null}
            . Not clinical advice.
          </p>
        </div>
      </header>

      {explainer.bottom_line && (
        <div className="mx-auto max-w-[1180px] px-8 pt-10">
          <div className="rounded-2xl border border-white/[0.10] bg-white/[0.04] px-7 py-6 backdrop-blur-xl">
            <p className="text-[11px] tracking-[0.16em] text-white/30 uppercase">Bottom line</p>
            <p className="mt-2 text-sm text-white/50">{explainer.bottom_line.question}</p>
            <p className="mt-2 text-xl leading-snug text-[#e8e8e8]">{keyFigure(explainer.bottom_line.answer)}</p>
            <div className="mt-4 flex flex-wrap items-end justify-between gap-3 border-t border-white/[0.08] pt-3">
              <p className="min-w-0 flex-1 text-xs leading-relaxed text-white/45">
                The paper: &ldquo;{explainer.bottom_line.provenance.quote}&rdquo;
                <span className="text-white/30"> — {explainer.bottom_line.provenance.section || explainer.bottom_line.provenance.locator}</span>
              </p>
              <button
                type="button"
                onClick={() => openSource(explainer.bottom_line!.provenance)}
                className="pill pill-strong shrink-0"
              >
                Read in the paper ↗
              </button>
            </div>
          </div>
        </div>
      )}

      {explainer.absolute_risk && explainer.absolute_risk_derived && (
        <RiskFigure risk={explainer.absolute_risk} derived={explainer.absolute_risk_derived} onOpen={openSource} />
      )}

      {explainer.notes.length > 0 && (
        <div className="mx-auto max-w-[1180px] px-8 pt-8">
          <ul className="space-y-2 rounded-xl border border-[#d9a441]/25 bg-[#d9a441]/[0.06] px-5 py-4">
            {explainer.notes.map((n, i) => (
              <li key={i} className="text-xs leading-relaxed text-[#d9a441]">
                {n}
              </li>
            ))}
          </ul>
        </div>
      )}

      {explainer.sections.map((section, i) => (
        <section key={section.id} id={`section-${section.id}`}>
          <div className="my-2 border-y border-white/[0.08] px-8 py-11">
            <h2 className="serif mx-auto max-w-[1180px] text-center text-[34px] leading-tight font-medium tracking-tight">
              {section.title}
            </h2>
          </div>

          <div className="mx-auto max-w-[1180px] px-8 pb-6">
            {(() => {
              const charts = [
                ...section.chart_ids.map((id) => byId.get(id)).filter((c): c is Chart => Boolean(c)),
                ...(i === explainer.sections.length - 1 ? orphans : []),
              ];
              // Only links to charts drawn beside this section count: lighting a mark two
              // screens away lights nothing the reader can see.
              const here = new Set(charts.map((c) => c.id));
              const prose = (
                <Prose
                  arms={arms}
                  sectionId={section.id}
                  markdown={section.markdown}
                  unprinted={unprinted.get(section.id) ?? []}
                  links={(linksBySection.get(section.id) ?? []).filter((l) => here.has(l.chart_id))}
                  terms={terms}
                  charts={byId}
                  wide={charts.length === 0}
                  onActive={setLit}
                  onOpen={openSource}
                />
              );
              // A section with nothing to draw beside it reads as one wide column, at a
              // measure the eye can still follow, rather than text down one side of a void.
              if (charts.length === 0) {
                return <div className="mx-auto max-w-[760px]">{prose}</div>;
              }
              return (
                <div className="grid gap-11 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
                  {prose}
                  <ChartColumn charts={charts} lit={lit} onOpen={openSource} />
                </div>
              );
            })()}

            {/* Figures take the full column width rather than the chart gutter. A chest
                plate authored at 1600px says nothing useful at 590, and the prose it
                would sit beside is usually much shorter than the image is tall. */}
            {(section.figure_ids ?? [])
              .map((id) => figById.get(id))
              .filter((f): f is FigurePlate => Boolean(f))
              .map((figure) => (
                <FigureFigure key={figure.id} figure={figure} paperId={explainer.paper_id} />
              ))}
          </div>
        </section>
      ))}

      {terms.length > 0 && (
        <div className="mx-auto max-w-[1180px] px-8 py-12">
          <h2 className="text-[11px] tracking-[0.16em] text-white/30 uppercase">Terms used above</h2>
          <dl className="mt-4 grid gap-x-10 gap-y-4 sm:grid-cols-2">
            {terms.map((t) => (
              <div key={t.term}>
                <dt className="text-sm text-[#e8e8e8]">{t.term}</dt>
                <dd className="mt-0.5 text-[13px] leading-relaxed text-white/50">
                  {t.provenance ? (
                    <button
                      type="button"
                      onClick={() => openSource(t.provenance!)}
                      className="text-left hover:text-white/75"
                      title="Read this in the paper"
                    >
                      &ldquo;{t.provenance.quote}&rdquo; <span className="text-white/30">— the paper ↗</span>
                    </button>
                  ) : (
                    <>
                      {t.definition} <span className="text-white/30">— our wording</span>
                    </>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {v.rejections.length > 0 && (
        <div className="mx-auto max-w-[1180px] px-8 py-16">
          <details className="rounded-xl border border-white/[0.08] bg-white/[0.02] px-6 py-5">
            <summary className="cursor-pointer text-xs text-white/50 hover:text-white">
              {v.rejections.length} value
              {v.rejections.length === 1 ? "" : "s"} were dropped before
              anything was drawn
            </summary>
            <ul className="mt-4 space-y-2 border-t border-white/[0.08] pt-4">
              {v.rejections.map((r, i) => (
                <li key={i} className="text-xs">
                  <span className="num text-[#e8e8e8]">{r.what}</span>
                  <span className="num ml-2 text-white/30">@ {r.locator}</span>
                  <p className="text-white/50">{r.reason}</p>
                </li>
              ))}
            </ul>
          </details>
        </div>
      )}

      {source && (
        <SourcePanel
          prov={source.prov}
          value={source.value}
          text={explainer.sources?.[source.prov.locator]}
          sourceUrl={explainer.source_url}
          onClose={closeSource}
        />
      )}
    </main>
    </ArmsContext.Provider>
  );
}

/** The page's arms, intervention first: the verified risk pair, else the first two-group chart. */
function armsOf(explainer: Explainer): string[] {
  if (explainer.absolute_risk) {
    return [explainer.absolute_risk.intervention.label, explainer.absolute_risk.comparator.label];
  }
  for (const c of explainer.charts) {
    const groups = [...new Set(c.data.map((d) => d.group).filter(Boolean))] as string[];
    if (groups.length > 1) return groups.slice(0, 2);
  }
  return [];
}

/**
 * The charts beside a section's prose.
 *
 * A section's text usually runs two or three times the height of its chart, and the grid
 * stretches the chart column to match, so a single chart sits at the top with a screen of
 * black under it. Pinning it fixes the hole and gives the reader the thing the prose is
 * describing while they read about it.
 *
 * Only when there is one chart. Two stuck to the same offset would land on top of each
 * other, and a column with two charts is close enough to the prose height not to gap.
 *
 * On a phone the column comes first and the single chart sticks to the top of the screen
 * as a strip, so the sentence being read and the mark it lights are on screen together.
 */
function ChartColumn({
  charts,
  lit,
  onOpen,
}: {
  charts: Chart[];
  lit: Lit | null;
  onOpen: (prov: Provenance, value?: number) => void;
}) {
  // Pinned whenever the whole column fits on screen, measured rather than assumed: two
  // short charts beside a long section left a screen of black under them, and a count
  // cannot know how tall a chart is.
  const inner = useRef<HTMLDivElement>(null);
  const [fits, setFits] = useState(charts.length === 1);
  useEffect(() => {
    const el = inner.current;
    if (!el) return;
    const measure = () => setFits(el.getBoundingClientRect().height <= window.innerHeight - 96);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    window.addEventListener("resize", measure, { passive: true });
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [charts]);
  const strip = charts.length === 1;
  return (
    <div className="min-w-0 max-lg:order-first">
      <div
        ref={inner}
        className={[
          fits ? "lg:sticky lg:top-16" : "",
          strip
            ? "max-lg:sticky max-lg:top-0 max-lg:z-20 max-lg:-mx-8 max-lg:max-h-[46vh] max-lg:overflow-y-auto max-lg:bg-black/90 max-lg:px-8 max-lg:backdrop-blur"
            : "",
        ].join(" ")}
      >
        {charts.map((chart) => (
          <ChartFigure key={chart.id} chart={chart} lit={lit} onOpen={onOpen} />
        ))}
      </div>
    </div>
  );
}

/** Minimal markdown: paragraphs, bold, bullets, pipe tables. The rewrite emits little else. */
function Prose({
  arms,
  sectionId,
  markdown,
  unprinted,
  links,
  terms,
  charts,
  wide = false,
  onActive,
  onOpen,
}: {
  arms: string[];
  sectionId: string;
  markdown: string;
  unprinted: string[];
  links: ProseLink[];
  terms: Term[];
  charts: Map<string, Chart>;
  wide?: boolean;
  onActive: (lit: Lit | null) => void;
  onOpen: (prov: Provenance, value?: number) => void;
}) {
  const blocks = markdown.split(/\n{2,}/).map(deLatex).filter(Boolean);
  const mark = useMemo(() => marker(unprinted), [unprinted]);
  const termRe = useMemo(() => termMatcher(terms), [terms]);
  const armTint = useMemo(() => armMatcher(arms, charts), [arms, charts]);
  const seen = new Set<string>();
  const root = useRef<HTMLDivElement>(null);

  // The sentence in the band where a reader's eye rests, 30% to 60% down the screen,
  // decides which mark is lit. A band rather than the whole viewport, so only one
  // sentence is "read" at a time and the chart does not flicker as the reader scrolls.
  useEffect(() => {
    const el = root.current;
    if (!el || links.length === 0) return;
    const spans = [...el.querySelectorAll<HTMLElement>("[data-link]")];
    if (spans.length === 0) return;
    const visible = new Set<HTMLElement>();
    let mine = false;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) visible.add(e.target as HTMLElement);
          else visible.delete(e.target as HTMLElement);
        }
        const top = spans.find((s) => visible.has(s));
        spans.forEach((s) => s.classList.toggle("sentence-lit", s === top));
        if (top) {
          mine = true;
          const [chart_id, kind, index] = (top.dataset.link ?? "").split("|");
          onActive({ chart_id, kind: kind as Lit["kind"], index: Number(index) });
        } else if (mine) {
          // Only the section that lit the chart may put it out, or two sections' observers
          // fight over one state as the reader crosses from one to the next.
          mine = false;
          onActive(null);
        }
      },
      { rootMargin: "-30% 0px -40% 0px", threshold: 0 },
    );
    spans.forEach((s) => io.observe(s));
    return () => io.disconnect();
  }, [links, sectionId, onActive]);

  const render = (text: string, key: string) =>
    withLinks(text, links, charts, arms, (piece, k, tint) =>
      // Arm names take colour only inside a sentence joined to a chart, where the colour
      // points at a mark. Coloured everywhere, they were decoration, and the figures the
      // sentence is about stopped standing out.
      inline(piece, mark, termRe, terms, seen, onOpen, `${key}-${k}`, tint, tint ? armTint : null),
    );

  return (
    <div ref={root} className={`${wide ? "text-[16px] leading-[1.8]" : "text-[15px] leading-[1.75]"} text-white/60`}>
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        const table = pipeTable(block);
        if (table) {
          return (
            <table key={i} className="mb-5 w-full border-collapse text-[13px]">
              <thead>
                <tr>
                  {table.head.map((h, k) => (
                    <th key={k} className="border-b border-white/[0.14] py-1.5 pr-3 text-left font-medium text-[#e8e8e8]">
                      {render(h, `h${i}${k}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, r) => (
                  <tr key={r}>
                    {row.map((c, k) => (
                      <td key={k} className="num border-b border-white/[0.06] py-1.5 pr-3 align-top">
                        {render(c, `c${i}${r}${k}`)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          );
        }
        if (lines.every((l) => /^\s*[-*]\s+/.test(l))) {
          return (
            <ul key={i} className="mb-5 space-y-1.5">
              {lines.map((l, j) => (
                <li key={j} className="flex gap-2.5">
                  <span className="mt-2.5 h-1 w-1 shrink-0 rounded-full bg-white/25" aria-hidden />
                  <span>{render(l.replace(/^\s*[-*]\s+/, ""), `l${i}${j}`)}</span>
                </li>
              ))}
            </ul>
          );
        }
        if (/^#{1,4}\s+/.test(block)) {
          return (
            <h3 key={i} className="mt-7 mb-2 text-base text-[#e8e8e8]">
              {block.replace(/^#{1,4}\s+/, "")}
            </h3>
          );
        }
        return (
          <p key={i} className="mb-5">
            {render(block, `p${i}`)}
          </p>
        );
      })}
    </div>
  );
}

/**
 * Wraps the linked sentences of a paragraph. The link carries the sentence text the API
 * matched, so finding it is a substring search; anything not found renders as plain text.
 */
/** What to colour inside a linked sentence: the datum's numbers and its arm's name. */
type Tint = { colour: string; re: RegExp } | null;

function tintFor(link: ProseLink, charts: Map<string, Chart>, arms: string[]): Tint {
  if (link.kind !== "datum") return null;
  const chart = charts.get(link.chart_id);
  const d = chart?.data[link.index];
  if (!chart || !d) return null;
  const colour = datumColour(chart, link.index, arms);
  const nums = [d.value, d.low, d.high, d.events, d.n]
    .filter((v): v is number => v !== null && v !== undefined)
    .flatMap((v) => [String(v), v.toFixed(1), v.toFixed(2), v.toLocaleString()])
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const names = [d.group].filter((t): t is string => Boolean(t && t.length > 2))
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const alts = [...new Set([...nums.map((n) => `(?<![\\d.])${n}(?![\\d.])`), ...names.map((n) => `\\b${n}\\b`)])];
  if (alts.length === 0) return null;
  return { colour, re: new RegExp(`(${alts.join("|")})`, "gi") };
}

function withLinks(
  text: string,
  links: ProseLink[],
  charts: Map<string, Chart>,
  arms: string[],
  render: (piece: string, k: number, tint: Tint) => React.ReactNode,
): React.ReactNode {
  const hits = links
    .map((l) => ({ l, at: text.indexOf(l.sentence.slice(0, 80)) }))
    .filter((h) => h.at >= 0)
    .sort((a, b) => a.at - b.at);
  if (hits.length === 0) return render(text, 0, null);
  const out: React.ReactNode[] = [];
  let pos = 0;
  let k = 0;
  for (const { l, at } of hits) {
    if (at < pos) continue;
    const end = Math.min(text.length, at + l.sentence.length);
    if (at > pos) out.push(<span key={k++}>{render(text.slice(pos, at), k, null)}</span>);
    const tint = tintFor(l, charts, arms);
    out.push(
      <span
        key={k++}
        className="sentence"
        data-link={`${l.chart_id}|${l.kind}|${l.index}`}
        style={tint ? ({ ["--lit" as string]: tint.colour } as React.CSSProperties) : undefined}
      >
        {render(text.slice(at, end), k, tint)}
      </span>,
    );
    pos = end;
  }
  if (pos < text.length) out.push(<span key={k++}>{render(text.slice(pos), k, null)}</span>);
  return out;
}

/** The numbers a chart plots, in the chart's colour, inside a linked sentence. */
function withTint(nodes: React.ReactNode[], tint: Tint, key: string): React.ReactNode[] {
  if (!tint) return nodes;
  return nodes.flatMap((node, i): React.ReactNode[] => {
    if (typeof node !== "string") return [node];
    return node.split(tint.re).map((part, j) =>
      j % 2 === 1 ? (
        <span key={`${key}-${i}-${j}`} className="num figure" style={{ color: textColour(tint.colour) }}>
          {part}
        </span>
      ) : (
        part
      ),
    );
  });
}

/**
 * The one number the page is about, in the treatment colour: the effect in the bottom
 * line. It is the only highlight outside a linked sentence, so it is the first thing seen.
 */
function keyFigure(answer: string): React.ReactNode {
  // The effect is a percentage when there is one, else a ratio or rate with a decimal,
  // else the first number. "Below 120 mm Hg" is the target, not the finding.
  const m =
    answer.match(/\d[\d.,]*\s?(?:%|percent(?:age points?)?\b)/) ??
    answer.match(/\b\d+\.\d+\b/) ??
    answer.match(/\d[\d.,]*/);
  if (!m || m.index === undefined) return answer;
  const end = m.index + m[0].length;
  return (
    <>
      {answer.slice(0, m.index)}
      <span className="num key">{m[0]}</span>
      {answer.slice(end)}
    </>
  );
}

/** The arms' names in the arms' colours, inside a sentence that is joined to a chart. */
type ArmTint = { re: RegExp; colour: (name: string) => string } | null;

/**
 * The names an arm goes by in the text: its full label, the parenthetical in it ("Target
 * below 120 mm Hg (intensive treatment)"), and the group names the charts use for it
 * ("Intensive treatment", "Semaglutide"). Not the label's first word: on SPRINT that was
 * "Target", which coloured every "target" in the prose as if it were an arm.
 */
function armMatcher(arms: string[], charts: Map<string, Chart>): ArmTint {
  if (arms.length === 0) return null;
  const fills = [A_FILL, B_FILL, C_FILL];
  const groupNames = new Set<string>();
  for (const c of charts.values()) for (const d of c.data) if (d.group) groupNames.add(d.group);
  const same = (g: string, a: string) => {
    const x = g.toLowerCase(), y = a.toLowerCase();
    return x === y || y.includes(x) || x.includes(y);
  };
  const entries = arms.slice(0, 3).map((arm, i) => {
    const inParens = arm.match(/\(([^)]+)\)/)?.[1];
    const fromCharts = [...groupNames].filter((g) => same(g, arm));
    const names = [...new Set([arm, inParens, ...fromCharts].filter((n): n is string => Boolean(n && n.length > 3)))];
    return { names, colour: textColour(fills[i]) };
  });
  // A space in a name also matches a hyphen: the prose writes "intensive-treatment group".
  const alts = entries.flatMap((e) => e.names).sort((a, b) => b.length - a.length)
    .map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "[\\s-]+"));
  if (alts.length === 0) return null;
  const re = new RegExp(`(\\b(?:${alts.join("|")})\\b)`, "gi");
  const fold = (t: string) => t.toLowerCase().replace(/[\s-]+/g, " ");
  const colour = (name: string) =>
    entries.find((e) => e.names.some((n) => fold(n) === fold(name)))?.colour ?? "#e8e8e8";
  return { re, colour };
}

function withArms(nodes: React.ReactNode[], armTint: ArmTint, key: string): React.ReactNode[] {
  if (!armTint) return nodes;
  return nodes.flatMap((node, i): React.ReactNode[] => {
    if (typeof node !== "string") return [node];
    return node.split(armTint.re).map((part, j) =>
      j % 2 === 1 ? (
        <span key={`${key}-${i}-${j}`} className="arm" style={{ color: armTint.colour(part) }}>
          {part}
        </span>
      ) : (
        part
      ),
    );
  });
}

/**
 * Nothing here renders math, and a reader should not be shown "$$\\text{VE} = 100 \\times
 * (1 - \\text{IRR})$$". The rewrite is now told to write formulas in plain arithmetic;
 * this keeps explainers built before that readable instead of leaking backslashes.
 */
function deLatex(text: string): string {
  return text
    .replace(/\$\$?/g, "")
    .replace(/\\(?:text|mathrm|mathbf|textbf|textsc)\{([^{}]*)\}/g, "$1")
    .replace(/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, "($1) / ($2)")
    .replace(/\\times/g, "×")
    .replace(/\\cdot/g, "·")
    .replace(/\\pm/g, "±")
    .replace(/\\approx/g, "≈")
    .replace(/\\leq?\b/g, "≤")
    .replace(/\\geq?\b/g, "≥")
    .replace(/\\%/g, "%")
    .replace(/\\[,;:!]/g, " ")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

/**
 * A markdown pipe table, as the rewrite sometimes emits for a small results table. Rows
 * may arrive on their own lines or run together on one, so a row boundary is a closing
 * pipe followed by an opening one either way. Returns null for anything else.
 */
function pipeTable(block: string): { head: string[]; rows: string[][] } | null {
  if (!/\|\s*:?-{2,}/.test(block)) return null;
  const rows = block
    .split(/\n|\|\s*(?=\|)/)
    .map((r) => r.trim())
    .filter((r) => r.startsWith("|"))
    .map((r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim()))
    .filter((cells) => !cells.every((c) => /^:?-+:?$/.test(c)));
  if (rows.length < 2) return null;
  return { head: rows[0], rows: rows.slice(1) };
}

const UNPRINTED_TITLE =
  "This number is not printed in the paper as such. It may be arithmetic or rounding the summary did; the charts beside the text are checked, this is not.";

/** A splitter for the numbers to mark in one section, or null when there are none. */
function marker(unprinted: string[]): RegExp | null {
  if (unprinted.length === 0) return null;
  const alts = [...new Set(unprinted)].map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return new RegExp(`((?<![\\d.])(?:${alts.join("|")})(?![\\d.]))`, "g");
}

/** Matches any defined term, longest first, at word boundaries, any case. */
function termMatcher(terms: Term[]): RegExp | null {
  if (terms.length === 0) return null;
  const alts = [...terms]
    .sort((a, b) => b.term.length - a.term.length)
    .map((t) => t.term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return new RegExp(`(\\b(?:${alts.join("|")})\\b)`, "gi");
}

function withMarks(text: string, mark: RegExp | null, key: string): React.ReactNode[] {
  if (!mark) return [text];
  return text.split(mark).map((part, i) =>
    i % 2 === 1 ? (
      <mark key={`${key}-${i}`} className="unprinted" title={UNPRINTED_TITLE}>
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

/**
 * Text with unprinted numbers marked and defined terms made into popovers, the first time
 * each term appears in a section. A term's popover shows the paper's own sentence when
 * the gate confirmed one, otherwise the definition marked as ours.
 */
function withTerms(
  text: string,
  mark: RegExp | null,
  termRe: RegExp | null,
  terms: Term[],
  seen: Set<string>,
  onOpen: (prov: Provenance, value?: number) => void,
  key: string,
  tint: Tint = null,
  armTint: ArmTint = null,
): React.ReactNode[] {
  const plain = (t: string, k: string) => withArms(withTint(withMarks(t, mark, k), tint, k), armTint, k);
  if (!termRe) return plain(text, key);
  return text.split(termRe).flatMap((part, i): React.ReactNode[] => {
    if (i % 2 === 0) return plain(part, `${key}-${i}`);
    const t = terms.find((x) => x.term.toLowerCase() === part.toLowerCase());
    // A term that is also an arm ("intensive treatment" on SPRINT) keeps the arm's colour,
    // whether it gets a popover or was already explained once.
    if (!t || seen.has(t.term.toLowerCase())) return withArms([part], armTint, `${key}-${i}`);
    seen.add(t.term.toLowerCase());
    return [
      <span key={`${key}-${i}`} className="term" tabIndex={0}>
        {withArms([part], armTint, `${key}-${i}a`)}
        <span role="tooltip" className="term-pop">
          {t.provenance ? (
            <>
              <span className="block text-[#e8e8e8]">&ldquo;{t.provenance.quote}&rdquo;</span>
              <button
                type="button"
                onClick={() => onOpen(t.provenance!)}
                className="pill mt-2"
              >
                The paper&rsquo;s words · read in context ↗
              </button>
            </>
          ) : (
            <>
              <span className="block text-[#e8e8e8]">{t.definition}</span>
              <span className="mt-1.5 block text-[11px] text-white/40">our wording, not the paper&rsquo;s</span>
            </>
          )}
        </span>
      </span>,
    ];
  });
}

function inline(
  text: string,
  mark: RegExp | null,
  termRe: RegExp | null,
  terms: Term[],
  seen: Set<string>,
  onOpen: (prov: Provenance, value?: number) => void,
  key: string,
  tint: Tint = null,
  armTint: ArmTint = null,
) {
  // Bold before italic, so the ** in "**x**" is never read as a single emphasis marker.
  return text.split(/(\*\*[^*]+\*\*|\*[^*\n]+\*)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="font-medium text-[#e8e8e8]">
          {withTerms(part.slice(2, -2), mark, termRe, terms, seen, onOpen, `${key}b${i}`, tint, armTint)}
        </strong>
      );
    }
    if (part.length > 2 && part.startsWith("*") && part.endsWith("*")) {
      return (
        <em key={i} className="text-white/75 italic">
          {withTerms(part.slice(1, -1), mark, termRe, terms, seen, onOpen, `${key}i${i}`, tint, armTint)}
        </em>
      );
    }
    return <span key={i}>{withTerms(part, mark, termRe, terms, seen, onOpen, `${key}t${i}`, tint, armTint)}</span>;
  });
}
