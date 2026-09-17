"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Chart, Datum } from "@/lib/types";

/**
 * Draws a chart spec as live SVG.
 *
 * Geometry is computed from the data, never hardcoded: the forest plot in particular has
 * to place marks by log(v) or a halving and a doubling stop looking like equal moves.
 *
 * Two things every chart does. It reveals as it enters view, in the order a reader needs
 * the parts, which is what replaces the old rendered build-up. And hovering any mark shows
 * the paper's own sentence, because that quote is the span the provenance gate matched the
 * number against.
 */

const A = "#7fb5a6"; // intervention
const B = "#c98a7a"; // comparator
const C = "#8f9bb8"; // third series
const SERIES = [A, B, C, "#b9a56f"];

/** "95%" but "162 cases": symbols close up to the number, words do not. */
function withUnit(s: string, unit: string): string {
  if (!unit) return s;
  return /^[%°×\u00b0]/.test(unit) ? `${s}${unit}` : `${s} ${unit}`;
}

function fmt(v: number, unit = "", dp?: number): string {
  if (Math.abs(v) >= 1000) return withUnit(v.toLocaleString(), unit);
  const s = dp === undefined ? String(Number(v.toFixed(2))) : v.toFixed(dp);
  return withUnit(s, unit);
}

/**
 * Decimal places shared by every value in a chart, taken from the most precise one.
 * The paper prints 14.0% beside 41.4%; rendering it as "14%" silently reports a different
 * number of significant figures than the source did.
 */
function decimals(data: Datum[]): number {
  return Math.max(
    0,
    ...data.map((d) => {
      const frac = String(d.value).split(".")[1];
      return frac ? Math.min(frac.length, 3) : 0;
    }),
  );
}

/** Nice round gridline steps, so the axis reads 0/10/20 rather than 0/8.3/16.6. */
function ticks(max: number, count = 4): number[] {
  if (max <= 0) return [0];
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => mag * m).find((s) => raw <= s) ?? mag * 10;
  const out: number[] = [];
  for (let v = 0; v <= max + step * 0.001; v += step) out.push(Number(v.toFixed(6)));
  return out;
}

/**
 * Breaks a label into lines at word boundaries. SVG text does not wrap, and the obvious
 * alternative -- truncating with an ellipsis -- hides exactly the thing a reader came for.
 * "Invasive mechanical ventilation" and "Invasive mechanical venti…" are not the same
 * label. Only a single word longer than the budget is ever cut.
 */
function wrapLabel(text: string, perLine: number, maxLines = 2): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let line = "";
  for (const w of words) {
    const next = line ? `${line} ${w}` : w;
    if (next.length <= perLine || !line) {
      line = next;
    } else {
      lines.push(line);
      line = w;
      if (lines.length === maxLines - 1) break;
    }
  }
  const used = lines.join(" ").split(/\s+/).filter(Boolean).length;
  const rest = words.slice(used).join(" ");
  if (rest) lines.push(rest);
  else if (line) lines.push(line);

  // Last line absorbs any overflow; cut only if one unbreakable run still exceeds the box.
  const last = lines[lines.length - 1];
  if (last && last.length > perLine * 1.5) {
    lines[lines.length - 1] = `${last.slice(0, Math.floor(perLine * 1.5) - 1)}…`;
  }
  return lines.filter(Boolean);
}

function useReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [on, setOn] = useState(false);

  useEffect(() => {
    if (on) return;

    // A scroll listener plus getBoundingClientRect: "has this entered view" is a position
    // question, and computing it directly needs no threshold tuning.
    const check = () => {
      const el = ref.current;
      if (!el) return;
      if (el.getBoundingClientRect().top < window.innerHeight * 0.85) setOn(true);
    };
    check();
    window.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check, { passive: true });

    // A chart whose reveal never fires is an invisible chart, because the marks start at
    // opacity 0. Scroll events can be throttled or missed entirely depending on the
    // browser, so the animation gets a deadline: after this the chart shows regardless.
    // The reveal is a flourish; the data is not.
    const deadline = window.setTimeout(() => setOn(true), 2500);

    return () => {
      window.clearTimeout(deadline);
      window.removeEventListener("scroll", check);
      window.removeEventListener("resize", check);
    };
  }, [on]);

  return { ref, on };
}

type TipState =
  | { x: number; y: number; quote: string; section: string; value?: number }
  | null;

export function ChartFigure({ chart }: { chart: Chart }) {
  const { ref, on } = useReveal<HTMLDivElement>();
  const [tip, setTip] = useState<TipState>(null);

  // The paper's sentence has to be reachable without a mouse: a keyboard reaches it by
  // focus, a finger by tap, a screen reader through the label.
  const showQuote = (quote: string, section: string, value?: number) => ({
    onMouseMove: (e: React.MouseEvent) =>
      setTip({ x: e.clientX, y: e.clientY, quote, section, value }),
    onMouseLeave: () => setTip(null),
    onFocus: (e: React.FocusEvent) => {
      const r = e.currentTarget.getBoundingClientRect();
      setTip({ x: r.left + r.width / 2, y: r.bottom, quote, section, value });
    },
    onBlur: () => setTip(null),
    onClick: (e: React.MouseEvent) =>
      setTip((t) => (t && t.quote === quote ? null : { x: e.clientX, y: e.clientY, quote, section, value })),
    tabIndex: 0,
    role: "img" as const,
    "aria-label": `${value !== undefined ? `${fmt(value)}. ` : ""}The paper says: ${quote} (${section})`,
    style: { cursor: "default" as const, outline: "none" },
  });

  const hover = (datum: Datum) =>
    showQuote(datum.provenance.quote, datum.provenance.section || datum.provenance.locator, datum.value);

  return (
    <figure ref={ref} className={`chart ${on ? "on" : ""} my-8`}>
      <div className="rounded-2xl border border-white/[0.08] bg-white/[0.04] px-7 pt-6 pb-5 backdrop-blur-xl">
        <h3 className="text-[14px] font-medium text-[#e8e8e8]">{chart.title}</h3>
        {chart.subtitle && <p className="mt-0.5 text-[12px] text-white/30">{chart.subtitle}</p>}

        <div className="mt-5">
          {chart.kind === "stat" && <Stat chart={chart} hover={hover} />}
          {chart.kind === "bars" && <Bars chart={chart} hover={hover} />}
          {chart.kind === "forest" && <Forest chart={chart} hover={hover} />}
          {chart.kind === "line" && <Line chart={chart} hover={hover} />}
          {chart.kind === "dots" && <Dots chart={chart} hover={hover} />}
          {chart.kind === "flow" && <Flow chart={chart} hover={hover} />}
          {chart.kind === "diagram" && <Diagram chart={chart} showQuote={showQuote} />}
        </div>

        {(chart.source || chart.caveat) && (
          <footer className="mt-4 flex flex-wrap justify-between gap-3 border-t border-white/[0.08] pt-3 text-[11px]">
            <span className="num text-white/30">{chart.source}</span>
            {chart.caveat && <span className="text-[#d9a441]">{chart.caveat}</span>}
          </footer>
        )}
      </div>

      {tip && <QuoteTip tip={tip} />}
    </figure>
  );
}

/** The paper's own sentence, with the reported value lit up inside it. */
function QuoteTip({ tip }: { tip: NonNullable<TipState> }) {
  const parts = useMemo(() => {
    const q = tip.quote;
    if (tip.value === undefined) return [q, "", ""];
    for (const cand of [fmt(tip.value), String(tip.value), tip.value.toFixed(1)]) {
      const i = q.indexOf(cand);
      if (i >= 0) return [q.slice(0, i), cand, q.slice(i + cand.length)];
    }
    return [q, "", ""];
  }, [tip]);

  const style: React.CSSProperties = {
    left: Math.min(tip.x + 16, (typeof window !== "undefined" ? window.innerWidth : 1200) - 400),
    top: tip.y + 16,
  };

  return (
    <div
      className="pointer-events-none fixed z-30 max-w-[380px] rounded-[10px] border border-white/[0.14] bg-[#0d0d0d] px-3.5 py-3 text-[12px] leading-[1.55] text-white/55 shadow-[0_12px_40px_rgba(0,0,0,0.75)]"
      style={style}
    >
      {parts[0]}
      {parts[1] && <b className="font-semibold text-[#e8e8e8]">{parts[1]}</b>}
      {parts[2]}
      <span className="mt-2 block text-[11px] text-white/30">
        — {tip.section}
      </span>
    </div>
  );
}

type HoverFn = (d: Datum) => Record<string, unknown>;

function Stat({ chart, hover }: { chart: Chart; hover: HoverFn }) {
  const d = chart.data[0];
  if (!d) return null;
  const interval = d.low !== null && d.high !== null ? `95% CI ${fmt(d.low)}–${fmt(d.high)}` : "";
  return (
    <div className="flex flex-wrap items-start gap-7" {...hover(d)}>
      <div>
        <div className="r-stat num text-[64px] leading-none font-light tracking-tight text-[#7fb5a6]">
          {fmt(d.value, chart.unit)}
        </div>
        {interval && <div className="num mt-2 text-[11px] text-white/30">{interval}</div>}
      </div>
      <p className="r-fade min-w-[240px] flex-1 border-l-2 border-white/[0.18] pl-4 text-[13px] leading-[1.65] text-white/55">
        {d.provenance.quote}
        <span className="mt-2 block text-[11px] text-white/30">
          — {d.provenance.section || d.provenance.locator}
        </span>
      </p>
    </div>
  );
}

function Bars({ chart, hover }: { chart: Chart; hover: HoverFn }) {
  const W = 520;
  const [L, R, T] = [48, 40, 26];
  const data = chart.data.slice(0, 8);

  // Grouped data means the same category appears once per arm. Drawing those as eight
  // independent bars repeats every category label and makes the comparison the chart
  // exists for -- this arm against that one, within a category -- something the reader has
  // to reconstruct. Pair them instead, label the category once, and name the arms in a key.
  const groups = [...new Set(data.map((d) => d.group).filter(Boolean))] as string[];
  const grouped = groups.length > 1;
  const cats = [...new Set(data.map((d) => d.label))];

  const labelLines = Math.max(
    ...cats.map((c) => wrapLabel(c, Math.floor(((W - L - R) / cats.length) / 6.4)).length),
  );
  const Bo = 34 + labelLines * 13;
  const H = 250 + (labelLines - 1) * 13 + (grouped ? 16 : 0);

  const max = Math.max(...data.flatMap((d) => [d.value, d.high ?? 0])) * 1.15 || 1;
  const gl = ticks(max);
  const plotW = W - L - R;
  const plotH = H - T - Bo;
  const y = (v: number) => T + plotH - (v / max) * plotH;

  const slot = plotW / cats.length;
  const perCat = grouped ? groups.length : 1;
  const barW = Math.min(grouped ? 46 : 72, (slot * 0.72) / perCat);
  const perLine = Math.floor(slot / 6.4);

  const dp = decimals(data);
  const annotated = chart.annotation ? cats.indexOf(chart.annotation.target) : -1;
  const annotatedValue = chart.annotation
    ? Math.max(...data.filter((d) => d.label === chart.annotation!.target).map((d) => d.value))
    : 0;

  /**
   * The annotation sits inside the plot, in whichever top corner the tall bars are not
   * using. Writing it past the right edge put it outside the viewBox, where
   * overflow-visible let it escape the card and run off the page.
   */
  const barNote = () => {
    if (annotated < 0 || !chart.annotation) return null;
    const targetX = L + slot * annotated + slot / 2;
    const targetTop = y(annotatedValue);

    // Anchor away from the tallest bar so the note never lands on top of the data.
    const tallest = cats
      .map((c) => Math.max(...data.filter((d) => d.label === c).map((d) => d.value)))
      .reduce((best, v, i, arr) => (v > arr[best] ? i : best), 0);
    const right = tallest < cats.length / 2;

    const lines = wrapLabel(chart.annotation.text, 30, 3);
    const tx = right ? L + plotW : L;
    const ty = T + 6;
    const anchor = right ? "end" : "start";
    const elbowY = ty + lines.length * 13 + 4;

    return (
      <g className="r-rise" style={{ transitionDelay: "0.95s" }}>
        <text x={tx} y={ty} textAnchor={anchor} className="note">
          {lines.map((ln, k) => (
            <tspan key={k} x={tx} dy={k === 0 ? 0 : 13}>
              {ln}
            </tspan>
          ))}
        </text>
        <path
          className="lead"
          d={`M ${tx} ${elbowY} L ${tx} ${Math.max(elbowY + 8, targetTop - 32)} L ${targetX} ${Math.max(elbowY + 8, targetTop - 32)} L ${targetX} ${targetTop - 26}`}
          fill="none"
        />
      </g>
    );
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full overflow-visible">
      {grouped && (
        <g>
          {groups.map((g, gi) => (
            <g key={g} transform={`translate(${L + gi * 150}, 0)`}>
              <rect x={0} y={2} width={9} height={9} rx={2} fill={SERIES[gi % SERIES.length]} />
              <text x={14} y={11} className="tick">
                {g}
              </text>
            </g>
          ))}
        </g>
      )}

      {gl.map((v) => (
        <g key={v}>
          <line x1={L} x2={L + plotW} y1={y(v)} y2={y(v)} className="grid" />
          <text x={L - 8} y={y(v) + 4} textAnchor="end" className="tick">
            {fmt(v)}
          </text>
        </g>
      ))}
      <line x1={L} x2={L + plotW} y1={y(0)} y2={y(0)} className="axis" />

      {cats.map((cat, ci) => {
        const centre = L + slot * ci + slot / 2;
        const members = data.filter((d) => d.label === cat);
        return (
          <g key={cat}>
            {members.map((d, mi) => {
              const gi = grouped ? groups.indexOf(d.group as string) : mi;
              const offset = grouped ? (gi - (groups.length - 1) / 2) * (barW + 6) : 0;
              const cx = centre + offset;
              // Ungrouped bars stay one colour. Cycling the palette across categories would
              // reuse the same teal/rust that means "dexamethasone vs usual care" in the
              // grouped chart above, so a reader would read a grouping that is not there.
              const colour = grouped ? SERIES[gi % SERIES.length] : A;
              const top = y(d.value);
              const delay = ci * 0.1 + gi * 0.05;
              return (
                <g key={`${cat}-${gi}`} {...hover(d)}>
                  <rect
                    className="r-bar"
                    x={cx - barW / 2}
                    y={top}
                    width={barW}
                    height={Math.max(1, y(0) - top)}
                    rx={2}
                    fill={colour}
                    opacity={0.85}
                    style={{ transformOrigin: `${cx}px ${y(0)}px`, transitionDelay: `${delay}s` }}
                  />
                  <text
                    className="r-rise val"
                    x={cx}
                    y={(d.high !== null ? y(d.high) : top) - 10}
                    textAnchor="middle"
                    fill={colour}
                    style={{ transitionDelay: `${0.4 + delay}s` }}
                  >
                    {fmt(d.value, chart.unit, dp)}
                  </text>
                  {d.low !== null && d.high !== null && (
                    <g className="r-fade whisker" style={{ transitionDelay: `${0.55 + delay}s` }}>
                      <line x1={cx} x2={cx} y1={y(d.high)} y2={y(d.low)} />
                      <line x1={cx - 8} x2={cx + 8} y1={y(d.high)} y2={y(d.high)} />
                      <line x1={cx - 8} x2={cx + 8} y1={y(d.low)} y2={y(d.low)} />
                    </g>
                  )}
                </g>
              );
            })}

            <text x={centre} y={y(0) + 20} textAnchor="middle" className="cat">
              {wrapLabel(cat, perLine).map((ln, k) => (
                <tspan key={k} x={centre} dy={k === 0 ? 0 : 13}>
                  {ln}
                </tspan>
              ))}
            </text>
            {members[0]?.note && (
              <text x={centre} y={y(0) + 22 + labelLines * 13} textAnchor="middle" className="tick">
                {members[0].note}
              </text>
            )}
          </g>
        );
      })}

      {barNote()}
    </svg>
  );
}

function Forest({ chart, hover }: { chart: Chart; hover: HoverFn }) {
  const W = 560;
  const rowH = 44;
  const data = chart.data.slice(0, 9);
  const H = data.length * rowH + 74;
  const [plotL, plotR] = [214, 396];
  const nullV = chart.null_value ?? (chart.log_scale ? 1 : 0);
  const log = chart.log_scale !== false && data.every((d) => d.value > 0);

  const all = data.flatMap((d) => [d.value, d.low ?? d.value, d.high ?? d.value]).concat(nullV);
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (log) {
    lo /= 1.35;
    hi *= 1.35;
  } else {
    const pad = (hi - lo) * 0.2 || 1;
    lo -= pad;
    hi += pad;
  }
  // Position by log(v) when the measure is a ratio: on a linear axis a halving and a
  // doubling are wildly different distances, which misreads the plot.
  const x = (v: number) =>
    log
      ? plotL + ((Math.log(Math.max(v, 1e-9)) - Math.log(lo)) / (Math.log(hi) - Math.log(lo))) * (plotR - plotL)
      : plotL + ((v - lo) / (hi - lo)) * (plotR - plotL);

  const axisTicks = (log ? [0.25, 0.5, 0.75, 1, 1.5, 2, 3] : ticks(hi)).filter(
    (t) => t >= lo && t <= hi,
  );
  const baseY = data.length * rowH + 18;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full overflow-visible">
      <line x1={x(nullV)} x2={x(nullV)} y1={6} y2={baseY - 8} className="grid" strokeDasharray="3 4" />

      {data.map((d, i) => {
        const cy = 22 + i * rowH;
        // Direction is a property of the outcome, not of the chart. A secondary-outcomes
        // plot can hold "discharged alive" (good above 1) next to "death" (good below it),
        // so a row may override the chart's own sense of which side is the good one.
        const lowerIsBetter =
          d.higher_is_better === null || d.higher_is_better === undefined
            ? chart.lower_is_better
            : !d.higher_is_better;
        const favourable = d.value < nullV === lowerIsBetter;
        const colour = favourable ? A : C;
        return (
          <g key={`${d.label}-${i}`} {...hover(d)}>
            <text
              x={198}
              y={cy + 4 - (wrapLabel(d.label, 24).length - 1) * 6}
              textAnchor="end"
              className="cat"
            >
              {wrapLabel(d.label, 24).map((ln, k) => (
                <tspan key={k} x={198} dy={k === 0 ? 0 : 12}>
                  {ln}
                </tspan>
              ))}
            </text>
            {d.low !== null && d.high !== null && (
              <g
                className="r-grow whisker"
                style={{ transformOrigin: `${x(d.value)}px ${cy}px`, transitionDelay: `${0.15 + i * 0.12}s` }}
              >
                <line x1={x(d.low)} x2={x(d.high)} y1={cy} y2={cy} />
                <line x1={x(d.low)} x2={x(d.low)} y1={cy - 5} y2={cy + 5} />
                <line x1={x(d.high)} x2={x(d.high)} y1={cy - 5} y2={cy + 5} />
              </g>
            )}
            <rect
              className="r-rise"
              x={x(d.value) - 6}
              y={cy - 6}
              width={12}
              height={12}
              fill={colour}
              opacity={0.9}
              style={{ transitionDelay: `${0.3 + i * 0.12}s` }}
            />
            <text
              className="r-fade tick"
              x={W - 8}
              y={cy + 4}
              textAnchor="end"
              style={{ transitionDelay: `${0.5 + i * 0.12}s` }}
            >
              {fmt(d.value)}
              {d.low !== null && d.high !== null ? ` (${fmt(d.low)}–${fmt(d.high)})` : ""}
            </text>
          </g>
        );
      })}

      <line x1={plotL - 4} x2={plotR + 4} y1={baseY} y2={baseY} className="axis" />
      {axisTicks.map((t) => (
        <text key={t} x={x(t)} y={baseY + 16} textAnchor="middle" className="tick">
          {fmt(t)}
        </text>
      ))}
      {/* Anchored away from the null line, not centred in whatever room is left on each
          side: when most estimates sit below 1 the right-hand room is a few pixels wide,
          and two centred labels ran into each other. */}
      {chart.favours_left && (
        <text x={x(nullV) - 8} y={baseY + 34} textAnchor="end" className="tick" fill={A}>
          {chart.favours_left} ←
        </text>
      )}
      {chart.favours_right && (
        <text x={x(nullV) + 8} y={baseY + 34} textAnchor="start" className="tick" fill={B}>
          → {chart.favours_right}
        </text>
      )}
    </svg>
  );
}

function Line({ chart, hover }: { chart: Chart; hover: HoverFn }) {
  const W = 520;
  const H = 240;
  const [L, R, T, Bo] = [50, 24, 20, 52];
  const groups = [...new Set(chart.data.map((d) => d.group || "series"))];
  const xs = [...new Set(chart.data.map((d) => d.value))];
  const maxX = chart.data.length;
  const values = chart.data.map((d) => d.value);
  const lo = Math.max(0, Math.min(...values) - (Math.max(...values) - Math.min(...values)) * 0.4 - 1);
  const hi = Math.max(...values);
  const plotW = W - L - R;
  const plotH = H - T - Bo;
  const y = (v: number) => T + plotH - ((v - lo) / (hi - lo || 1)) * plotH;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full overflow-visible">
      <line x1={L} x2={L + plotW} y1={T + plotH} y2={T + plotH} className="axis" />
      <line x1={L} x2={L} y1={T} y2={T + plotH} className="axis" />
      {groups.map((g, gi) => {
        const pts = chart.data.filter((d) => (d.group || "series") === g);
        const step = plotW / Math.max(1, pts.length - 1 || 1);
        const path = pts.map((d, i) => `${i ? "L" : "M"}${L + step * i},${y(d.value)}`).join(" ");
        return (
          <g key={g}>
            <path
              className="r-draw"
              d={path}
              fill="none"
              stroke={SERIES[gi % SERIES.length]}
              strokeWidth={2}
              style={{ ["--len" as string]: 600, transitionDelay: `${gi * 0.2}s` }}
            />
            {pts.map((d, i) => (
              <circle
                key={i}
                className="r-fade"
                cx={L + step * i}
                cy={y(d.value)}
                r={4}
                fill={SERIES[gi % SERIES.length]}
                style={{ transitionDelay: `${0.5 + gi * 0.2}s` }}
                {...hover(d)}
              />
            ))}
          </g>
        );
      })}
      {chart.data.slice(0, maxX).map((d, i) => (
        <text key={`${d.label}-${i}`} x={L + (plotW / Math.max(1, xs.length - 1)) * i} y={T + plotH + 20}
              textAnchor="middle" className="tick">
          {d.label}
        </text>
      ))}
    </svg>
  );
}

function Dots({ chart, hover }: { chart: Chart; hover: HoverFn }) {
  const W = 520;
  const H = 150;
  const data = chart.data.slice(0, 12);
  const max = Math.max(...data.map((d) => d.value)) || 1;
  const step = W / (data.length + 1);
  // Area, not radius, encodes the value: a radius-scaled circle overstates by its square.
  const r = (v: number) => 6 + Math.sqrt(v / max) * 22;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full overflow-visible">
      {data.map((d, i) => (
        <g key={`${d.label}-${i}`} {...hover(d)}>
          <circle
            className="r-rise"
            cx={step * (i + 1)}
            cy={64}
            r={r(d.value)}
            fill={A}
            opacity={0.35}
            style={{ transitionDelay: `${i * 0.06}s` }}
          />
          <text x={step * (i + 1)} y={120} textAnchor="middle" className="tick">
            {d.label}
          </text>
        </g>
      ))}
    </svg>
  );
}

function Flow({ chart, hover }: { chart: Chart; hover: HoverFn }) {
  const data = chart.data.slice(0, 6);
  const W = 520;
  const boxH = 64;
  const gapH = 28;

  // Consecutive steps whose values sum to the step above them are arms of a split, so they
  // sit side by side. Everything else is a stage in the funnel and stacks vertically.
  //
  // The tolerance is deliberately tight. Trial counts rarely add up exactly (people
  // randomized but never dosed), so some slack is needed, but a false positive draws two
  // unrelated stages as sibling arms and says something about the trial that is not true.
  // A missed split only stacks them vertically, which is merely plainer. Bias to missing.
  const rows: number[][] = [];
  for (let i = 0; i < data.length; i++) {
    const parent = rows.length ? data[rows[rows.length - 1][0]] : null;
    const isSplit =
      i + 1 < data.length &&
      parent !== null &&
      Math.abs(data[i].value + data[i + 1].value - parent.value) <= Math.max(2, parent.value * 0.01);
    if (isSplit) {
      rows.push([i, i + 1]);
      i++;
    } else {
      rows.push([i]);
    }
  }

  const H = rows.length * (boxH + gapH) + 6;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full overflow-visible">
      {rows.map((row, r) => {
        const yTop = r * (boxH + gapH) + 6;
        const boxW = row.length > 1 ? 200 : 240;
        return (
          <g key={r}>
            {r > 0 && (
              <line
                className="r-draw axis"
                x1={W / 2}
                x2={W / 2}
                y1={yTop - gapH + 4}
                y2={yTop - 6}
                style={{ ["--len" as string]: gapH, transitionDelay: `${r * 0.18}s` }}
              />
            )}
            {row.map((idx, k) => {
              const d = data[idx];
              const cx =
                row.length > 1 ? W / 2 + (k - (row.length - 1) / 2) * (boxW + 24) : W / 2;
              const colour = row.length > 1 ? SERIES[k % SERIES.length] : "rgba(255,255,255,0.55)";
              const isSplit = row.length > 1;
              return (
                <g key={idx} {...hover(d)}>
                  <rect
                    className="r-rise"
                    x={cx - boxW / 2}
                    y={yTop}
                    width={boxW}
                    height={boxH}
                    rx={8}
                    fill={isSplit ? `${colour}1f` : "rgba(255,255,255,0.05)"}
                    stroke={isSplit ? colour : "rgba(255,255,255,0.18)"}
                    style={{ transitionDelay: `${r * 0.18 + k * 0.08}s` }}
                  />
                  <text x={cx} y={yTop + 25} textAnchor="middle" className="val" fill="#e8e8e8">
                    {fmt(d.value)}
                  </text>
                  <text x={cx} y={yTop + 42} textAnchor="middle" className="tick">
                    {wrapLabel(d.label, Math.floor(boxW / 6)).map((ln, k) => (
                      <tspan key={k} x={cx} dy={k === 0 ? 0 : 11}>
                        {ln}
                      </tspan>
                    ))}
                  </text>
                </g>
              );
            })}
          </g>
        );
      })}
    </svg>
  );
}


type QuoteFn = (quote: string, section: string, value?: number) => Record<string, unknown>;

/**
 * A mechanism the paper argues, drawn as the graph it is.
 *
 * Nodes are ranked by how far they sit from a starting point, which gives a reading order
 * without any layout hints from the model. Every arrow carries the sentence that licences
 * it: hover shows that sentence, so a reader can check the claim rather than take it.
 *
 * A dashed arrow is not decoration. It means the paper hedged, and the gate read that
 * hedge out of the quoted wording rather than asking the model to declare it. Papers say
 * "may reflect" all the time; a solid arrow would quietly upgrade a suggestion into a
 * finding, which is the main way a diagram like this can lie.
 */
function Diagram({ chart, showQuote }: { chart: Chart; showQuote: QuoteFn }) {
  const nodes = chart.nodes ?? [];
  const edges = chart.edges ?? [];
  if (nodes.length < 2 || edges.length === 0) return null;

  const W = 520;
  const rowGap = 104;

  // Rank by longest path from a node with nothing feeding it. The model never says where
  // anything goes; the shape falls out of the claims themselves.
  const rank = new Map<string, number>();
  nodes.forEach((n) => rank.set(n.id, 0));
  for (let pass = 0; pass < nodes.length; pass++) {
    let moved = false;
    for (const e of edges) {
      const want = (rank.get(e.source) ?? 0) + 1;
      if (want > (rank.get(e.target) ?? 0)) {
        rank.set(e.target, want);
        moved = true;
      }
    }
    if (!moved) break;
  }

  const rows: string[][] = [];
  nodes.forEach((n) => {
    const r = rank.get(n.id) ?? 0;
    (rows[r] ||= []).push(n.id);
  });
  const widest = Math.max(...rows.map((r) => r.length));
  const boxW = Math.min(190, (W - 40) / widest - 14);
  const chars = Math.floor(boxW / 6.2);

  // One height for every box, from whichever node needs the most lines. Boxes of differing
  // height in a row read as a hierarchy that is not there.
  const wrapped = new Map(
    nodes.map((n) => [
      n.id,
      { label: wrapLabel(n.label, chars, 2), note: n.note ? wrapLabel(n.note, chars, 2) : [] },
    ]),
  );
  const boxH = Math.max(
    52,
    ...[...wrapped.values()].map((w) => 22 + w.label.length * 13 + w.note.length * 12),
  );

  const pos = new Map<string, { x: number; y: number }>();
  rows.forEach((row, r) => {
    const step = Math.min(boxW + 26, (W - 30) / row.length);
    row.forEach((id, i) => {
      pos.set(id, {
        x: W / 2 + (i - (row.length - 1) / 2) * step,
        y: r * (boxH + rowGap) + 8,
      });
    });
  });

  const H = rows.length * (boxH + rowGap) - rowGap + 26;
  const anyHedged = edges.some((e) => e.hedged);

  // Several arrows crossing the same gap put their labels on the same line. Staggering by
  // position within the gap keeps them apart without a collision solver.
  const perGap = new Map<number, number>();

  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full overflow-visible">
        <defs>
          <marker id="dg-head" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7"
                  markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1 L 7 4 L 0 7 z" fill="rgba(255,255,255,0.5)" />
          </marker>
        </defs>

        {edges.map((e, i) => {
          const a = pos.get(e.source);
          const b = pos.get(e.target);
          if (!a || !b) return null;
          const gap = rank.get(e.source) ?? 0;
          const slot = perGap.get(gap) ?? 0;
          perGap.set(gap, slot + 1);

          const x1 = a.x;
          const y1 = a.y + boxH;
          const x2 = b.x;
          const y2 = b.y - 9;
          // Two lines, because taking the first line of a wrap and dropping the rest cuts
          // the claim in half without saying so: "benefit greatest with respiratory" is
          // not what the arrow asserts.
          const lines = e.label ? wrapLabel(e.label, 30, 2) : [];
          const elbow = y1 + 26 + slot * (lines.length * 12 + 6);
          const path = `M ${x1} ${y1} L ${x1} ${elbow} L ${x2} ${elbow} L ${x2} ${y2}`;
          const lx = (x1 + x2) / 2;
          const widest = Math.max(0, ...lines.map((l) => l.length));

          return (
            <g
              key={`${e.source}-${e.target}-${i}`}
              {...showQuote(e.provenance.quote, e.provenance.section || e.provenance.locator)}
            >
              {/* A wide invisible path so the arrow is hoverable without being thick. */}
              <path d={path} stroke="transparent" strokeWidth={16} fill="none" />
              <path
                className="r-draw"
                d={path}
                fill="none"
                stroke={e.hedged ? "rgba(255,255,255,0.34)" : "rgba(255,255,255,0.55)"}
                strokeWidth={1.3}
                strokeDasharray={e.hedged ? "5 4" : undefined}
                markerEnd="url(#dg-head)"
                style={{ ["--len" as string]: 500, transitionDelay: `${0.2 + i * 0.1}s` }}
              />
              {lines.length > 0 && (
                <>
                  {/* Sits on the ground colour so a label crossing a box stays readable. */}
                  <rect
                    x={lx - widest * 2.9}
                    y={elbow - 5 - lines.length * 12}
                    width={widest * 5.8}
                    height={lines.length * 12 + 3}
                    rx={3}
                    fill="#0a0a0a"
                  />
                  <text
                    x={lx}
                    y={elbow - 6 - (lines.length - 1) * 12}
                    textAnchor="middle"
                    className="tick"
                  >
                    {lines.map((ln, k) => (
                      <tspan key={k} x={lx} dy={k === 0 ? 0 : 12}>
                        {ln}
                      </tspan>
                    ))}
                  </text>
                </>
              )}
            </g>
          );
        })}

        {nodes.map((n, i) => {
          const p = pos.get(n.id);
          const w = wrapped.get(n.id);
          if (!p || !w) return null;
          const top = p.y + (boxH - (w.label.length * 13 + w.note.length * 12)) / 2 + 11;
          return (
            <g key={n.id} className="r-rise" style={{ transitionDelay: `${i * 0.08}s` }}>
              <rect
                x={p.x - boxW / 2}
                y={p.y}
                width={boxW}
                height={boxH}
                rx={9}
                fill="rgba(255,255,255,0.05)"
                stroke="rgba(255,255,255,0.18)"
              />
              <text x={p.x} y={top} textAnchor="middle" className="cat" fill="#e8e8e8">
                {w.label.map((ln, k) => (
                  <tspan key={k} x={p.x} dy={k === 0 ? 0 : 13}>
                    {ln}
                  </tspan>
                ))}
              </text>
              {w.note.length > 0 && (
                <text
                  x={p.x}
                  y={top + w.label.length * 13 + 1}
                  textAnchor="middle"
                  className="tick"
                >
                  {w.note.map((ln, k) => (
                    <tspan key={k} x={p.x} dy={k === 0 ? 0 : 12}>
                      {ln}
                    </tspan>
                  ))}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <p className="mt-4 text-[11px] leading-relaxed text-white/30">
        {anyHedged
          ? "Hover any arrow for the sentence it comes from. A dashed arrow is a link the paper suggests rather than reports."
          : "Hover any arrow for the sentence it comes from."}
      </p>
    </>
  );
}
