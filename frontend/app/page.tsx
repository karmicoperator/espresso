"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { ExplainerSummary } from "@/lib/types";

const EXAMPLES = [
  { paste: "https://pubmed.ncbi.nlm.nih.gov/32678530/", label: "Dexamethasone in Covid-19" },
  { paste: "https://pubmed.ncbi.nlm.nih.gov/33378609/", label: "mRNA-1273 vaccine" },
  { paste: "PMC2988224", label: "LDL meta-analysis" },
];

const STEPS = [
  "Resolving the paper",
  "Reading the full text",
  "Rewriting it into sections",
  "Choosing the charts",
  "Checking every value against the source",
];

export default function Home() {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [built, setBuilt] = useState<ExplainerSummary[]>([]);

  useEffect(() => {
    api.list().then(setBuilt).catch(() => setBuilt([]));
  }, []);

  // The build is one synchronous request, so the only honest progress signal is a clock
  // and a rough idea of where it is. Better than a spinner that says nothing.
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    const s = setInterval(() => setStep((n) => Math.min(n + 1, STEPS.length - 1)), 42000);
    return () => {
      clearInterval(t);
      clearInterval(s);
    };
  }, [busy]);

  async function submit(reference: string) {
    setError(null);
    setBusy(true);
    setStep(0);
    setElapsed(0);
    try {
      const explainer = await api.build(reference);
      router.push(`/paper/${encodeURIComponent(explainer.paper_id)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  /**
   * The other way in. A quarter of PubMed's free full text was never deposited in PubMed
   * Central, and the publishers hosting it refuse automated downloads. They do not refuse
   * people, so a paper the reader can open they can also drop here.
   */
  async function submitPdf(file: File) {
    setError(null);
    setBusy(true);
    setStep(0);
    setElapsed(0);
    try {
      const explainer = await api.buildFromPdf(file);
      router.push(`/paper/${encodeURIComponent(explainer.paper_id)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const mmss = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`;

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center px-6 py-20 text-center">
      <h1 className="text-6xl font-semibold tracking-tight text-[#e8e8e8] sm:text-7xl">
        Med<span className="text-white/45">Scroll</span>
      </h1>
      <p className="mt-6 max-w-xl text-[15px] leading-relaxed text-white/55">
        Paste a PubMed link. It comes back as a short explainer with interactive charts built
        from the paper&rsquo;s own numbers, every value checked against the source before it is
        drawn.
      </p>

      {busy ? (
        <div className="mt-12 w-full max-w-xl rounded-2xl border border-white/[0.08] bg-white/[0.04] p-7 text-left backdrop-blur-xl">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-medium text-[#e8e8e8]">{STEPS[step]}</h2>
            <span className="num text-sm text-white/70">{mmss}</span>
          </div>
          <ol className="mt-5 space-y-2.5">
            {STEPS.map((s, i) => (
              <li key={s} className="flex items-start gap-3">
                <span
                  className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                    i < step ? "bg-white/70" : i === step ? "animate-pulse bg-white" : "bg-white/15"
                  }`}
                />
                <p className={i > step ? "text-sm text-white/30" : "text-sm text-[#e8e8e8]"}>{s}</p>
              </li>
            ))}
          </ol>
          <p className="mt-5 border-t border-white/[0.08] pt-4 text-xs leading-relaxed text-white/55">
            Three to five minutes. Choosing the charts is the long pole: the model reads the
            whole paper, and there is no prompt caching on the Claude Code backend.
          </p>
        </div>
      ) : (
        <>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (input.trim()) void submit(input.trim());
            }}
            className="mt-10 w-full max-w-xl"
          >
            <div className="flex items-center gap-2 rounded-full border border-white/[0.10] bg-white/[0.04] py-2 pr-2 pl-6 backdrop-blur-xl transition-colors focus-within:border-white/25">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="https://pubmed.ncbi.nlm.nih.gov/32678530/"
                className="min-w-0 flex-1 bg-transparent py-2 text-sm text-[#e8e8e8] placeholder:text-white/25 focus:outline-none"
              />
              <button
                type="submit"
                disabled={!input.trim()}
                aria-label="Build explainer"
                className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-white/[0.12] bg-white/[0.06] text-white/70 transition-colors hover:border-white/30 hover:bg-white/[0.14] hover:text-white disabled:opacity-25"
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
                  <path d="M5.5 3.5 10 8l-4.5 4.5" stroke="currentColor" strokeWidth="1.6"
                        strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
          </form>

          <p className="mt-3 text-xs text-white/25">
            PubMed or PMC links, a DOI, or a bare PMID. The full text is read from PubMed
            Central.
          </p>

          <p className="mt-4 text-xs text-white/30">
            Not in PubMed Central?{" "}
            <label className="cursor-pointer text-white/60 underline decoration-white/20 underline-offset-4 transition-colors hover:text-white">
              open the PDF
              <input
                type="file"
                accept="application/pdf,.pdf"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  // Cleared so choosing the same file twice still fires a change event.
                  e.target.value = "";
                  if (file) void submitPdf(file);
                }}
              />
            </label>{" "}
            and it will be built from that instead.
          </p>

          <div className="mt-5 flex flex-wrap items-center justify-center gap-2 text-xs">
            <span className="text-white/25">Try these:</span>
            {EXAMPLES.map((ex) => (
              <button
                key={ex.paste}
                type="button"
                onClick={() => setInput(ex.paste)}
                className="rounded-full border border-white/[0.08] bg-white/[0.02] px-3.5 py-1.5 text-white/45 transition-colors hover:border-white/25 hover:text-white"
              >
                {ex.label}
              </button>
            ))}
          </div>

          {error && (
            <p className="mt-6 w-full max-w-xl rounded-xl border border-[#f27066]/30 bg-[#f27066]/10 p-3 text-sm text-[#f27066]">
              {error}
            </p>
          )}

          {built.length > 0 && (
            <section className="mt-16 w-full text-left">
              <h2 className="mb-3 text-center text-[11px] tracking-[0.16em] text-white/25 uppercase">
                Already built
              </h2>
              <div className="space-y-2">
                {built.map((p) => (
                  <button
                    key={p.paper_id}
                    onClick={() => router.push(`/paper/${encodeURIComponent(p.paper_id)}`)}
                    className="flex w-full items-baseline justify-between gap-4 rounded-2xl border border-white/[0.08] bg-white/[0.04] px-5 py-3.5 text-left backdrop-blur-xl transition-colors hover:border-white/[0.14] hover:bg-white/[0.07]"
                  >
                    <span className="min-w-0">
                      {/* Wraps rather than truncating. A paper is identified by its title, and the
                          half that gets cut is usually the half that distinguishes it. */}
                      <span className="block text-sm leading-snug text-[#e8e8e8]">{p.title}</span>
                      <span className="block text-xs text-white/30">
                        {[p.journal, p.published?.slice(0, 4)].filter(Boolean).join(" · ")}
                      </span>
                    </span>
                    <span className="num shrink-0 text-xs text-white/40">
                      {p.chart_count} chart{p.chart_count === 1 ? "" : "s"}
                    </span>
                  </button>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}
