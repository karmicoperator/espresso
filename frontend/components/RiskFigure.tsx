"use client";

import { useState } from "react";
import type { AbsoluteRisk, AbsoluteRiskDerived, Provenance } from "@/lib/types";

/**
 * The primary outcome as people.
 *
 * A rate ratio of 0.83 means nothing to most readers. A hundred people, with the ones
 * who die either way in one colour and the ones the treatment spares in another, means
 * something to everyone. This is the Cochrane icon array, the one medical visualization
 * with evidence behind it, and it is drawn from exactly two numbers, both verified
 * against the paper. Everything computed from them (the difference, the number needed
 * to treat) is marked as derived, because the paper did not print it.
 */
export function RiskFigure({
  risk,
  derived,
  onOpen,
}: {
  risk: AbsoluteRisk;
  derived: AbsoluteRiskDerived;
  onOpen: (prov: Provenance, value?: number) => void;
}) {
  const [mode, setMode] = useState<"absolute" | "relative">("absolute");
  const [people, setPeople] = useState<100 | 1000 | 10000>(100);

  const c = risk.comparator;
  const i = risk.intervention;
  const lowerIsGood = !risk.higher_is_better;
  // Per 100: whoever has the outcome under both arms, then the ones the intervention
  // changes. The direction says whether that change is a gain or a harm.
  const both = Math.min(c.value, i.value);
  const changed = Math.abs(c.value - i.value);
  const bothN = Math.round(both);
  const changedN = Math.max(0, Math.round(both + changed) - bothN);
  const good = derived.favours_intervention;
  const scale = people / 100;
  const n = (v: number) => Math.round(v * scale).toLocaleString();
  // The words depend on which way is good. "Spared" is right for deaths avoided and
  // wrong for people who reach a weight-loss target because of the drug.
  const words = wording(lowerIsGood, derived.direction);

  return (
    <div className="mx-auto max-w-[1180px] px-8 pt-8">
      <div className="rounded-2xl border border-white/[0.10] bg-white/[0.04] px-7 py-6 backdrop-blur-xl">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <p className="text-[11px] tracking-[0.16em] text-white/30 uppercase">The effect, as people</p>
            <h3 className="mt-1 text-[14px] font-medium text-[#e8e8e8]">
              {risk.outcome}
              {risk.timeframe && <span className="text-white/40"> · {risk.timeframe}</span>}
            </h3>
          </div>
          <div className="flex items-center gap-2 text-[11px]">
            <Toggle active={mode === "absolute"} onClick={() => setMode("absolute")}>Absolute</Toggle>
            <Toggle active={mode === "relative"} onClick={() => setMode("relative")}>Relative</Toggle>
          </div>
        </div>

        <div className="mt-5 grid gap-8 lg:grid-cols-[auto_minmax(0,1fr)]">
          <IconArray both={bothN} changed={changedN} good={good} words={words} />

          <div className="min-w-0 text-[14px] leading-relaxed text-white/60">
            {mode === "absolute" ? (
              <>
                <p className="text-[#e8e8e8]">
                  Of <span className="num">{people.toLocaleString()}</span> people like these,{" "}
                  {lowerIsGood ? "it happens to " : ""}
                  <span className="num" style={{ color: "#c98a7a" }}>{n(c.value)}</span>{lowerIsGood ? "" : " reach it"} with{" "}
                  <QuoteButton prov={c.provenance} value={c.value} onOpen={onOpen}>{c.label}</QuoteButton>{" "}
                  and {lowerIsGood ? "to " : ""}<span className="num" style={{ color: "#7fb5a6" }}>{n(i.value)}</span> with{" "}
                  <QuoteButton prov={i.provenance} value={i.value} onOpen={onOpen}>{i.label}</QuoteButton>.
                </p>
                <p className="mt-2">
                  That is <span className="num text-[#e8e8e8]">{n(changed)}</span> {derived.direction} per {people.toLocaleString()}
                  {derived.number_needed && (
                    <>
                      : treat <span className="num text-[#e8e8e8]">{derived.number_needed}</span> people for one {words.one} (number needed {derived.number_needed_kind}).
                    </>
                  )}
                  {!derived.number_needed && "."}
                </p>
              </>
            ) : (
              <>
                <p className="text-[#e8e8e8]">
                  {derived.relative_change_pct !== null && (
                    <>
                      A <span className="num">{Math.abs(derived.relative_change_pct)}%</span>{" "}
                      {derived.relative_change_pct < 0 ? "lower" : "higher"} relative rate with{" "}
                      {i.label}: {i.value}% against {c.value}%.
                    </>
                  )}
                </p>
                <p className="mt-2">
                  Relative numbers sound larger than they are. The same result in absolute terms is{" "}
                  <span className="num text-[#e8e8e8]">{n(changed)}</span> {derived.direction} per {people.toLocaleString()} people.
                </p>
              </>
            )}

            <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px] text-white/35">
              <span>Imagine</span>
              {([100, 1000, 10000] as const).map((k) => (
                <Toggle key={k} active={people === k} onClick={() => setPeople(k)}>
                  {k.toLocaleString()} people
                </Toggle>
              ))}
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-white/30">
              The two rates are the paper&rsquo;s, each checked against its sentence (click an arm to
              read it). The counts, the difference and the number needed to treat are worked out
              from them here and are not printed in the paper.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

type Words = { either: string; changed: string; neither: string; one: string };

/** What to call the three groups of people, given which way is good and which way it went. */
function wording(lowerIsGood: boolean, direction: "fewer" | "more"): Words {
  if (lowerIsGood) {
    return direction === "fewer"
      ? { either: "have the outcome either way", changed: "spared by the treatment", neither: "do not have it either way", one: "to be spared" }
      : { either: "have the outcome either way", changed: "added by the treatment", neither: "do not have it either way", one: "extra case" };
  }
  return direction === "more"
    ? { either: "reach it either way", changed: "reach it because of the treatment", neither: "do not reach it either way", one: "more to reach it" }
    : { either: "reach it either way", changed: "miss it because of the treatment", neither: "do not reach it either way", one: "more to miss it" };
}

/** A hundred people in ten rows. Reading order is left to right, top to bottom. */
function IconArray({
  both,
  changed,
  good,
  words,
}: {
  both: number;
  changed: number;
  /** Whether the change is a gain; it decides the colour of the changed people. */
  good: boolean | null;
  words: Words;
}) {
  const cell = 22;
  const size = cell * 10;
  const cells = Array.from({ length: 100 }, (_, k) => k);
  // Colours: outcome either way in the comparator's rust; the people the intervention
  // changes in teal when that is a gain, amber when it is a harm; everyone else faint.
  const colour = (k: number) => {
    if (k < both) return "#c98a7a";
    if (k < both + changed) return good ? "#7fb5a6" : "#d9a441";
    return "rgba(255,255,255,0.16)";
  };
  const legend = [
    { c: "#c98a7a", t: words.either },
    { c: good ? "#7fb5a6" : "#d9a441", t: words.changed },
    { c: "rgba(255,255,255,0.16)", t: words.neither },
  ];
  return (
    <div>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} className="block" role="img"
           aria-label={`${both} of 100 ${words.either}, ${changed} ${words.changed}`}>
        {cells.map((k) => {
          const x = (k % 10) * cell + cell / 2;
          const y = Math.floor(k / 10) * cell + cell / 2;
          return (
            <g key={k} fill={colour(k)} className="r-fade" style={{ transitionDelay: `${k * 6}ms` }}>
              <circle cx={x} cy={y - 5} r={3.4} />
              <path d={`M ${x - 5.5} ${y + 9} a 5.5 5.5 0 0 1 11 0 z`} />
            </g>
          );
        })}
      </svg>
      <ul className="mt-3 space-y-1 text-[11px] text-white/45">
        {legend.filter((l, idx) => idx !== 1 || changed > 0).map((l) => (
          <li key={l.t} className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: l.c }} />
            {l.t}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Toggle({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-2.5 py-1 transition-colors ${
        active ? "border-white/30 bg-white/[0.10] text-[#e8e8e8]" : "border-white/[0.10] text-white/40 hover:text-white"
      }`}
    >
      {children}
    </button>
  );
}

function QuoteButton({
  prov,
  value,
  onOpen,
  children,
}: {
  prov: Provenance;
  value?: number;
  onOpen: (prov: Provenance, value?: number) => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(prov, value)}
      className="underline decoration-white/25 decoration-dotted underline-offset-4 hover:decoration-white"
      title="Read the paper's sentence"
    >
      {children}
    </button>
  );
}
