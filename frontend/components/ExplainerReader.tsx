"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";
import { ChartFigure } from "./ChartFigure";
import { FigureFigure } from "./FigureFigure";
import type { Chart, Explainer, FigurePlate } from "@/lib/types";

/**
 * The explainer: at most five rewritten sections, each with the charts that belong to it.
 *
 * Prose in a narrow column on the left, charts wide on the right, with a full-bleed rule
 * and a serif title between sections. Borrowed from Nature's immersive layout, which uses
 * the section break to reset attention rather than to decorate.
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
  const pct = v.checked ? Math.round((v.passed / v.checked) * 100) : null;
  const proseMisses = v.prose_unmatched?.length ?? 0;

  return (
    <main>
      <header className="border-b border-white/[0.08]">
        <div className="mx-auto max-w-[1180px] px-8 py-12">
          <div className="print-hide flex items-baseline justify-between gap-4">
            <Link href="/" className="text-xs text-white/50 transition-colors hover:text-white">
              ← Build another paper
            </Link>
            <button
              type="button"
              onClick={() => window.print()}
              className="text-xs text-white/50 transition-colors hover:text-white"
            >
              Print or save as PDF
            </button>
          </div>
          <h1 className="mt-5 max-w-4xl text-3xl leading-snug font-medium tracking-tight text-[#e8e8e8]">
            {explainer.title}
          </h1>
          <p className="num mt-3 text-xs text-white/30">{meta.join(" · ")}</p>
          {explainer.authors.length > 0 && (
            <p className="mt-2 max-w-3xl text-xs text-white/40">
              {explainer.authors.slice(0, 6).join(", ")}
              {explainer.authors.length > 6 && ` and ${explainer.authors.length - 6} others`}
            </p>
          )}
          <div className="num mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
            {explainer.source_url && (
              <a
                href={explainer.source_url}
                target="_blank"
                rel="noreferrer"
                className="text-white/60 transition-colors hover:text-white hover:underline"
              >
                Read the original
              </a>
            )}
            {explainer.doi && <span className="text-white/30">doi:{explainer.doi}</span>}
            {pct !== null && (
              <span
                className="rounded-full border px-2.5 py-0.5"
                style={{
                  color: pct >= 90 ? "#7dd19b" : pct >= 70 ? "#d9a441" : "#f27066",
                  borderColor: "rgba(255,255,255,0.10)",
                }}
                title={`${v.passed} of ${v.checked} charted values were matched to a quoted span in the paper`}
              >
                {pct}% of charted values verified
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
            <p className="mt-2 text-xl leading-snug text-[#e8e8e8]">{explainer.bottom_line.answer}</p>
            <p className="mt-4 border-t border-white/[0.08] pt-3 text-xs leading-relaxed text-white/45">
              The paper: &ldquo;{explainer.bottom_line.provenance.quote}&rdquo;
              <span className="text-white/30"> — {explainer.bottom_line.provenance.section || explainer.bottom_line.provenance.locator}</span>
            </p>
          </div>
        </div>
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
        <section key={section.id}>
          <div className="my-2 border-y border-white/[0.08] px-8 py-11">
            <h2 className="serif mx-auto max-w-[1180px] text-center text-[34px] leading-tight font-medium tracking-tight">
              {section.title}
            </h2>
          </div>

          <div className="mx-auto max-w-[1180px] px-8 pb-6">
            <div className="grid gap-11 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
              <Prose markdown={section.markdown} unprinted={unprinted.get(section.id) ?? []} />
              <ChartColumn
                charts={[
                  ...section.chart_ids.map((id) => byId.get(id)).filter((c): c is Chart => Boolean(c)),
                  ...(i === explainer.sections.length - 1 ? orphans : []),
                ]}
              />
            </div>

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
    </main>
  );
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
 */
function ChartColumn({ charts }: { charts: Chart[] }) {
  const pin = charts.length === 1;
  return (
    <div className="min-w-0">
      <div className={pin ? "lg:sticky lg:top-16" : undefined}>
        {charts.map((chart) => (
          <ChartFigure key={chart.id} chart={chart} />
        ))}
      </div>
    </div>
  );
}

/** Minimal markdown: paragraphs, bold, and bullets. The rewrite emits little else. */
function Prose({ markdown, unprinted }: { markdown: string; unprinted: string[] }) {
  const blocks = markdown.split(/\n{2,}/).map(deLatex).filter(Boolean);
  const mark = useMemo(() => marker(unprinted), [unprinted]);
  return (
    <div className="text-[15px] leading-[1.75] text-white/60">
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        if (lines.every((l) => /^\s*[-*]\s+/.test(l))) {
          return (
            <ul key={i} className="mb-5 space-y-1.5">
              {lines.map((l, j) => (
                <li key={j} className="flex gap-2.5">
                  <span className="mt-2.5 h-1 w-1 shrink-0 rounded-full bg-white/25" aria-hidden />
                  <span>{inline(l.replace(/^\s*[-*]\s+/, ""), mark)}</span>
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
            {inline(block, mark)}
          </p>
        );
      })}
    </div>
  );
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

const UNPRINTED_TITLE =
  "This number is not printed in the paper as such. It may be arithmetic or rounding the summary did; the charts beside the text are checked, this is not.";

/** A splitter for the numbers to mark in one section, or null when there are none. */
function marker(unprinted: string[]): RegExp | null {
  if (unprinted.length === 0) return null;
  const alts = [...new Set(unprinted)].map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return new RegExp(`((?<![\\d.])(?:${alts.join("|")})(?![\\d.]))`, "g");
}

function withMarks(text: string, mark: RegExp | null, key: string) {
  if (!mark) return text;
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

function inline(text: string, mark: RegExp | null) {
  // Bold before italic, so the ** in "**x**" is never read as a single emphasis marker.
  return text.split(/(\*\*[^*]+\*\*|\*[^*\n]+\*)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="font-medium text-[#e8e8e8]">
          {withMarks(part.slice(2, -2), mark, `b${i}`)}
        </strong>
      );
    }
    if (part.length > 2 && part.startsWith("*") && part.endsWith("*")) {
      return (
        <em key={i} className="text-white/75 italic">
          {withMarks(part.slice(1, -1), mark, `i${i}`)}
        </em>
      );
    }
    return <span key={i}>{withMarks(part, mark, `t${i}`)}</span>;
  });
}
