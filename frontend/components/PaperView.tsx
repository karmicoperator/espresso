"use client";

import { useEffect, useRef, useState } from "react";

/**
 * The paper itself, opened at a sentence.
 *
 * Two sources, one behaviour. When the paper's PDF is stored, the page it is on renders
 * and the sentence is marked on it. Otherwise the paper's own text, as fetched, renders
 * section by section and the sentence is marked where it stands. A click on any sentence
 * of the concise version, any charted value or the bottom line lands here, so "the paper
 * says" is always one click from the paper.
 */
export type Target = { locator: string; quote: string; page?: number };

export function PaperView({
  paperId,
  target,
  hasPdf,
  pdfVersion = 0,
  onClose,
}: {
  paperId: string;
  target: Target;
  hasPdf: boolean;
  pdfVersion?: number;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<"pdf" | "text">(hasPdf ? "pdf" : "text");
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside
      role="dialog"
      aria-label="The paper"
      className="print-hide fixed inset-x-0 bottom-0 z-40 flex max-h-[85vh] flex-col border-t border-white/[0.14] bg-[#0b0b0b]/97 backdrop-blur-xl lg:inset-y-0 lg:right-0 lg:left-auto lg:max-h-none lg:w-[640px] lg:border-t-0 lg:border-l"
    >
      <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-3">
        <div className="min-w-0">
          <p className="text-[11px] tracking-[0.16em] text-white/30 uppercase">In the paper</p>
          <p className="num mt-1 truncate text-xs text-white/50">{target.locator || "full text"}</p>
        </div>
        <div className="flex items-center gap-2">
          {hasPdf && (
            <>
              <button type="button" className={`pill ${mode === "pdf" ? "pill-strong" : ""}`} onClick={() => setMode("pdf")}>PDF</button>
              <button type="button" className={`pill ${mode === "text" ? "pill-strong" : ""}`} onClick={() => setMode("text")}>Text</button>
            </>
          )}
          <button type="button" onClick={onClose} aria-label="Close"
                  className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-white/[0.12] text-white/60 hover:text-white">
            ×
          </button>
        </div>
      </div>
      <div data-pdf-scroll className="min-h-0 flex-1 overflow-y-auto px-6 pb-6">
        {mode === "pdf" ? (
          <PdfPage paperId={paperId} target={target} version={pdfVersion} />
        ) : (
          <TextView paperId={paperId} target={target} hasPdf={hasPdf} />
        )}
      </div>
    </aside>
  );
}

/* ----------------------------------------------------------------------------------
   Matching a quote against text that was set by a typesetter: dashes, quotes, ligatures,
   line-break hyphens and runs of whitespace all differ from the JATS text the quote came
   from. Both sides are folded to the same form, and the fold keeps a map back to the
   original characters so the marks land on the right ones.
   ---------------------------------------------------------------------------------- */
function foldChar(c: string): string {
  if (/[‐-―−]/.test(c)) return "-";
  if (/[‘’‚]/.test(c)) return "'";
  if (/[“”„]/.test(c)) return '"';
  if (c === "ﬁ") return "fi";
  if (c === "ﬂ") return "fl";
  if (/\s/.test(c)) return " ";
  return c.toLowerCase();
}

function foldNeedle(s: string): string {
  return [...s].map(foldChar).join("").replace(/ +/g, " ").trim();
}

/**
 * Where the needle sits in the folded haystack: the whole of it, else a window from its
 * middle, else its first eight words. A window locates the sentence; the span returned
 * is then the whole sentence's length from where the window sits inside it, clamped to
 * the text, so a sentence found by its middle is still marked from end to end.
 */
function findFolded(hay: string, needle: string): [number, number] | null {
  const n = foldNeedle(needle);
  if (n.length < 3) return null;
  const whole = hay.indexOf(n);
  if (whole >= 0) return [whole, whole + n.length];
  const midStart = Math.max(0, Math.floor(n.length / 2) - 30);
  const probes: [string, number][] = [
    [n.slice(midStart, Math.floor(n.length / 2) + 30), midStart],
    [n.split(" ").slice(0, 8).join(" "), 0],
  ];
  for (const [probe, offset] of probes) {
    if (probe.length < 16) continue;
    const at = hay.indexOf(probe);
    if (at < 0) continue;
    const start = Math.max(0, at - offset);
    return [start, Math.min(hay.length, start + n.length)];
  }
  return null;
}

/* ---------------------------------------- text ---------------------------------------- */
type Paper = {
  title: string;
  abstract: string;
  sections: { id: string; title: string; content: string; tables: { id: string; caption: string; headers: string[]; rows: string[][] }[] }[];
};

function TextView({ paperId, target, hasPdf }: { paperId: string; target: Target; hasPdf: boolean }) {
  const [paper, setPaper] = useState<Paper | null | undefined>(undefined);
  const markRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let live = true;
    fetch(`/api/paper/${encodeURIComponent(paperId)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((p) => live && setPaper(p))
      .catch(() => live && setPaper(null));
    return () => {
      live = false;
    };
  }, [paperId]);

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center" });
  }, [paper, target]);

  if (paper === undefined) return <p className="text-xs text-white/40">Opening the paper…</p>;
  if (paper === null) {
    return (
      <div className="text-sm text-white/55">
        <p className="text-[#e8e8e8]">&ldquo;{target.quote}&rdquo;</p>
        <p className="mt-3 text-xs text-white/35">
          The source text for this paper was not kept, so only the quoted sentence can be shown.
          {!hasPdf && " Drop the paper's PDF on this page to open sentences in it."}
        </p>
      </div>
    );
  }

  // The locator names a section or a paragraph inside it. The quote is marked in the
  // first paragraph, in reading order, that holds it: the locator's paragraph first, then
  // the rest of its section, then anywhere. Decided before rendering, once.
  const [locSection, locPara] = target.locator.split("/");
  const paras: { key: string; text: string; sid: string; idx: number }[] = [
    { key: "abstract", text: paper.abstract, sid: "abstract", idx: 0 },
    ...paper.sections.flatMap((s) =>
      s.content.split(/\n\n+/).filter((p) => p.trim()).map((p, i) => ({ key: `${s.id}-${i}`, text: p, sid: s.id, idx: i })),
    ),
  ];
  const rank = (p: { sid: string; idx: number }) =>
    p.sid === locSection && (!locPara || locPara === `p${p.idx + 1}`) ? 0 : p.sid === locSection ? 1 : 2;
  let mark: { key: string; from: number; to: number } | null = null;
  for (const p of [...paras].sort((a, b) => rank(a) - rank(b))) {
    const hit = findFolded(foldNeedle(p.text), target.quote);
    if (hit) {
      mark = { key: p.key, from: unfoldIndex(p.text, hit[0]), to: unfoldIndex(p.text, hit[1]) };
      break;
    }
  }
  const renderPara = (text: string, key: string) => {
    if (mark && mark.key === key) {
      return (
        <p key={key} className="mb-3">
          {text.slice(0, mark.from)}
          <mark ref={markRef} className="rounded-[3px] bg-[#00e676]/25 px-0.5 text-white">{text.slice(mark.from, mark.to)}</mark>
          {text.slice(mark.to)}
        </p>
      );
    }
    return <p key={key} className="mb-3">{text}</p>;
  };

  return (
    <div className="text-[14px] leading-[1.7] text-white/55">
      <h2 className="mb-4 text-base font-medium text-[#e8e8e8]">{paper.title}</h2>
      <h3 className="mt-5 mb-2 text-[11px] tracking-[0.16em] text-white/30 uppercase">Abstract</h3>
      {renderPara(paper.abstract, "abstract")}
      {paper.sections.map((s) => (
        <section key={s.id} id={`paper-${s.id}`}>
          <h3 className="mt-6 mb-2 text-[11px] tracking-[0.16em] text-white/30 uppercase">{s.title}</h3>
          {paras.filter((p) => p.sid === s.id).map((p) => renderPara(p.text, p.key))}
          {s.tables.map((t) => (
            <div key={t.id} className="mt-3 mb-4 overflow-x-auto">
              <p className="mb-1 text-xs text-white/40">{t.caption}</p>
              <table className="num text-[12px]">
                <thead><tr>{t.headers.map((h, k) => <th key={k} className="pr-4 text-left font-medium text-white/60">{h}</th>)}</tr></thead>
                <tbody>{t.rows.map((r, ri) => <tr key={ri}>{r.map((c, ci) => <td key={ci} className="pr-4 align-top">{c}</td>)}</tr>)}</tbody>
              </table>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}

/** The original index that a folded index corresponds to. */
function unfoldIndex(text: string, folded: number): number {
  let f = 0;
  let lastSpace = false;
  for (let i = 0; i < text.length; i++) {
    const c = foldChar(text[i]);
    const isSpace = c === " ";
    if (isSpace && (lastSpace || f === 0)) continue;
    if (f >= folded) return i;
    f += c.length;
    lastSpace = isSpace;
  }
  return text.length;
}

/* ---------------------------------------- pdf ---------------------------------------- */
type Rect = { left: number; top: number; width: number; height: number };

function PdfPage({ paperId, target, version }: { paperId: string; target: Target; version: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [state, setState] = useState<{ page: number; pages: number; rects: Rect[]; found: boolean; error?: string }>({
    page: target.page || 1, pages: 0, rects: [], found: false,
  });
  const [wanted, setWanted] = useState<number>(target.page || 0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
        const doc = await pdfjs.getDocument({ url: `/api/pdf/${encodeURIComponent(paperId)}?v=${version}` }).promise;
        if (cancelled) return;

        // The page: the stored hint, else the first page whose text holds the quote.
        let pageNo = wanted;
        let hit: [number, number] | null = null;
        let folded: { text: string; map: { item: number; offset: number }[] } | null = null;
        const foldPage = async (n: number) => {
          const p = await doc.getPage(n);
          const tc = await p.getTextContent();
          let text = "";
          const map: { item: number; offset: number }[] = [];
          const items = tc.items as { str: string; hasEOL?: boolean }[];
          items.forEach((it, idx) => {
            let s = it.str;
            // A word broken at a line end: "recon-" then "struction". Drop the hyphen.
            const next = items[idx + 1];
            if (it.hasEOL && s.endsWith("-") && next && /^[a-z]/.test(next.str)) s = s.slice(0, -1);
            for (let k = 0; k < s.length; k++) {
              const c = foldChar(s[k]);
              if (c === " " && text.endsWith(" ")) continue;
              for (const ch of c) { text += ch; map.push({ item: idx, offset: k }); }
            }
            const nxt = items[idx + 1];
            const breaks = it.hasEOL || (nxt && !/^[\s,.;:)\]]/.test(nxt.str) && !/[\s(\[-]$/.test(s));
            if (breaks && !text.endsWith(" ")) { text += " "; map.push({ item: idx, offset: s.length }); }
          });
          return { p, tc, text, map };
        };
        if (!pageNo) {
          for (let n = 1; n <= doc.numPages && !cancelled; n++) {
            const f = await foldPage(n);
            const h = findFolded(f.text, target.quote);
            if (h) { pageNo = n; hit = h; folded = { text: f.text, map: f.map }; break; }
          }
          if (!pageNo) pageNo = 1;
        }
        const page = await doc.getPage(pageNo);
        const f = folded ? null : await foldPage(pageNo);
        if (f) { folded = { text: f.text, map: f.map }; hit = findFolded(f.text, target.quote); }
        const tc = await page.getTextContent();

        const canvas = canvasRef.current;
        if (!canvas || cancelled) return;
        // The panel's scroll area sets the page width; the canvas's own box starts at 300px.
        const root = canvas.closest("[data-pdf-scroll]") as HTMLElement | null;
        const width = Math.min(600, (root?.clientWidth ?? 640) - 48);
        const base = page.getViewport({ scale: 1 });
        const scale = width / base.width;
        const viewport = page.getViewport({ scale });
        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * dpr);
        canvas.height = Math.floor(viewport.height * dpr);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        // Print intent: display rendering waits for an animation frame, and a tab that
        // is not visible (opened in the background, or behind another window) never gets
        // one, so the page would never appear. Print rendering draws the same page now.
        await page.render({
          canvas,
          viewport,
          intent: "print",
          transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined,
        } as Parameters<typeof page.render>[0]).promise;

        // Marks: one rectangle per text item the quote covers, in page space scaled.
        const rects: Rect[] = [];
        if (hit && folded) {
          const items = tc.items as { str: string; transform: number[]; width: number; height: number }[];
          const covered = new Set<number>();
          for (let i = hit[0]; i < hit[1] && i < folded.map.length; i++) covered.add(folded.map[i].item);
          for (const idx of covered) {
            const it = items[idx];
            if (!it || !it.transform) continue;
            const [a, , , d, e, fy] = it.transform;
            const h = Math.abs(d) || Math.abs(a) || 10;
            const x = e * scale;
            const yTop = viewport.height - (fy + h) * scale;
            rects.push({ left: x, top: yTop - 1, width: it.width * scale, height: h * scale + 2 });
          }
        }
        if (!cancelled) setState({ page: pageNo, pages: doc.numPages, rects, found: !!hit });
      } catch (err) {
        if (!cancelled) setState((s) => ({ ...s, error: err instanceof Error ? err.message : String(err) }));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [paperId, target, wanted, version]);

  useEffect(() => {
    if (state.rects.length && canvasRef.current) {
      const top = Math.max(0, state.rects[0].top - 160);
      canvasRef.current.parentElement?.parentElement?.scrollTo({ top, behavior: "smooth" });
    }
  }, [state]);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between text-[11px] text-white/40">
        <span className="num">
          {state.pages ? `Page ${state.page} of ${state.pages}` : "Opening the PDF…"}
          {state.pages > 0 && !state.found && " · sentence not found on this page; showing the page"}
        </span>
        <span className="flex gap-2">
          <button type="button" className="pill" disabled={state.page <= 1} onClick={() => setWanted(state.page - 1)}>←</button>
          <button type="button" className="pill" disabled={!state.pages || state.page >= state.pages} onClick={() => setWanted(state.page + 1)}>→</button>
        </span>
      </div>
      {state.error && <p className="mb-3 text-xs text-[#ff6259]">{state.error}</p>}
      <div data-pdf-root className="relative inline-block rounded-md bg-white shadow-[0_8px_40px_rgba(0,0,0,0.6)]">
        <canvas ref={canvasRef} className="block rounded-md" />
        {state.rects.map((r, i) => (
          <div key={i} aria-hidden className="pointer-events-none absolute rounded-[2px]"
               style={{ left: r.left, top: r.top, width: r.width, height: r.height, background: "rgba(0,230,118,0.35)", outline: "1px solid rgba(0,230,118,0.7)" }} />
        ))}
      </div>
    </div>
  );
}
