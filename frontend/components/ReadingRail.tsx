"use client";

import { useEffect, useState } from "react";

/**
 * Where you are in the paper, and how much is left.
 *
 * Distill's table of contents, reduced to what a five-minute read needs: a hairline of
 * progress along the top, and on wide screens a rail of section marks that names the
 * section under the cursor and the one being read. Nothing here scrolls the reader
 * anywhere on its own.
 */
export function ReadingRail({
  sections,
  minutes,
}: {
  sections: { id: string; title: string }[];
  minutes: number;
}) {
  const [progress, setProgress] = useState(0);
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    const els = sections.map((s) => document.getElementById(`section-${s.id}`));
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setProgress(max > 0 ? Math.min(1, window.scrollY / max) : 1);
      // The current section is the last one whose title has passed the upper part of the
      // viewport, which is where a reader's eye rests.
      let idx = 0;
      els.forEach((el, k) => {
        if (el && el.getBoundingClientRect().top < window.innerHeight * 0.35) idx = k;
      });
      setCurrent(idx);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [sections]);

  const left = Math.max(0, Math.round(minutes * (1 - progress)));

  return (
    <>
      <div className="print-hide fixed inset-x-0 top-0 z-30 h-[2px] bg-white/[0.06]" aria-hidden>
        <div className="h-full bg-white/70 transition-[width] duration-150" style={{ width: `${progress * 100}%` }} />
      </div>

      <nav
        aria-label="Sections"
        className="print-hide fixed top-1/2 left-5 z-30 hidden -translate-y-1/2 xl:block"
      >
        <ol className="space-y-3">
          {sections.map((s, k) => (
            <li key={s.id} className="group relative">
              <a
                href={`#section-${s.id}`}
                onClick={(e) => {
                  e.preventDefault();
                  document.getElementById(`section-${s.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
                }}
                className="flex items-center gap-3"
                aria-current={k === current ? "true" : undefined}
              >
                <span
                  className={`block h-1.5 w-1.5 rounded-full transition-all ${
                    k === current ? "scale-150 bg-white" : k < current ? "bg-white/55" : "bg-white/20 group-hover:bg-white/45"
                  }`}
                />
                {/* Names appear on hover only. The gutter beside the prose is narrow, and a
                    label that is always on would sit over the text. */}
                <span
                  className={`max-w-[220px] truncate rounded bg-[#0b0b0b] px-1.5 py-0.5 text-[11px] opacity-0 transition-opacity group-hover:opacity-100 ${
                    k === current ? "text-[#e8e8e8]" : "text-white/50"
                  }`}
                >
                  {s.title}
                </span>
              </a>
            </li>
          ))}
        </ol>
        <p className="num mt-5 text-[11px] text-white/30">
          {left > 0 ? `${left} min left` : "done"}
        </p>
      </nav>
    </>
  );
}
