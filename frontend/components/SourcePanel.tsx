"use client";

import { useEffect } from "react";
import type { Provenance } from "@/lib/types";

/**
 * The paper's own paragraph, with the sentence a value came from marked inside it.
 *
 * The tooltip shows the sentence; this shows where the sentence lives. A number checked
 * against a quote is only as trustworthy as the reader's ability to see the quote in
 * context, so this is the trust argument made visible: the paragraph as printed, the
 * span the gate matched, and a link to the same paragraph at the source.
 */
export function SourcePanel({
  prov,
  value,
  text,
  sourceUrl,
  onClose,
}: {
  prov: Provenance;
  value?: number;
  text: string | undefined;
  sourceUrl: string | null | undefined;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Citation markers were removed at ingest and left their brackets behind; the reader
  // does not need to see "()" in the paper's sentence.
  const clean = text?.replace(/\s*\(\s*\)/g, "").replace(/\s{2,}/g, " ");
  const parts = split(clean, prov.quote);

  return (
    <aside
      role="dialog"
      aria-label="The paper's paragraph"
      className="print-hide fixed inset-x-0 bottom-0 z-40 max-h-[72vh] overflow-y-auto border-t border-white/[0.14] bg-[#0b0b0b]/95 backdrop-blur-xl lg:inset-y-0 lg:right-0 lg:left-auto lg:max-h-none lg:w-[440px] lg:border-t-0 lg:border-l"
    >
      <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-3">
        <div className="min-w-0">
          <p className="text-[11px] tracking-[0.16em] text-white/30 uppercase">From the paper</p>
          <p className="num mt-1 truncate text-xs text-white/50">
            {prov.section || prov.locator}
            {prov.section && <span className="text-white/25"> · {prov.locator}</span>}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-white/[0.12] text-white/60 hover:text-white"
        >
          ×
        </button>
      </div>

      <div className="px-6 pb-6 text-[14px] leading-[1.7] text-white/55">
        {parts ? (
          <p>
            {parts[0]}
            <mark className="rounded-[3px] bg-[#7fb5a6]/20 px-0.5 text-[#e8e8e8]">{parts[1]}</mark>
            {parts[2]}
          </p>
        ) : (
          <>
            <p className="text-[#e8e8e8]">&ldquo;{prov.quote}&rdquo;</p>
            {clean && <p className="mt-4 text-white/40">{clean}</p>}
            {!clean && (
              <p className="mt-3 text-xs text-white/30">
                This paper was built before source paragraphs were stored. Rebuild it to see the
                sentence in context.
              </p>
            )}
          </>
        )}
        {value !== undefined && (
          <p className="num mt-4 text-xs text-white/35">Plotted value: {value}</p>
        )}
        {sourceUrl && (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noreferrer"
            className="mt-5 inline-block text-xs text-white/60 underline decoration-white/20 underline-offset-4 hover:text-white"
          >
            Open the paper at the source ↗
          </a>
        )}
      </div>
    </aside>
  );
}

/** The paragraph around the quote, matched loosely enough to survive publisher typography. */
function split(text: string | undefined, quote: string): [string, string, string] | null {
  if (!text) return null;
  const fold = (s: string) =>
    s.replace(/[‐-―−]/g, "-").replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/\s+/g, " ").toLowerCase();
  const hay = fold(text);
  const needle = fold(quote).trim();
  // Folding keeps length, so indexes carry over to the original text.
  const at = hay.indexOf(needle);
  if (at < 0 || needle.length < 3) return null;
  return [text.slice(0, at), text.slice(at, at + needle.length), text.slice(at + needle.length)];
}
