"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import Link from "next/link";
import type { ExplainerSummary, Health, Job } from "@/lib/types";

// Three papers that show the range: a 17,604-patient drug trial's four-year data, the
// landmark surgery-versus-rehabilitation trial in orthopaedics, and a 9,361-patient
// blood-pressure trial whose paper runs to dozens of pages.
const EXAMPLES = [
  { paste: "https://pubmed.ncbi.nlm.nih.gov/38740993/", label: "Semaglutide, 4 years (SELECT)" },
  { paste: "https://pubmed.ncbi.nlm.nih.gov/23349407/", label: "ACL tear: surgery or rehab (KANON)" },
  { paste: "https://pubmed.ncbi.nlm.nih.gov/40380811/", label: "Liver transplant for cancer (review)" },
];

/** Mirrors backend/builds.py STEPS: the stages a build reports, in order. */
const STEPS: [string, string][] = [
  ["resolve", "Resolving the paper"],
  ["fetch", "Reading the full text"],
  ["plan", "Writing the sections and choosing the charts"],
  ["verify", "Checking every value against the source"],
  ["figures", "Fetching the paper's own figures"],
];

const POLL_MS = 2000;

function isPdf(file: File) {
  return file.type === "application/pdf" || /\.pdf$/i.test(file.name);
}

function mmss(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export default function Home() {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [built, setBuilt] = useState<ExplainerSummary[]>([]);
  const [query, setQuery] = useState("");
  const [order, setOrder] = useState<"newest" | "title" | "shortest">("newest");
  const [removing, setRemoving] = useState<string | null>(null);
  const shown = built
    .filter((p) => {
      const q = query.trim().toLowerCase();
      return !q || `${p.title} ${p.journal ?? ""} ${p.published ?? ""}`.toLowerCase().includes(q);
    })
    .sort((a, b) =>
      order === "title" ? a.title.localeCompare(b.title)
      : order === "shortest" ? (a.reading_minutes ?? 0) - (b.reading_minutes ?? 0)
      : 0,
    );
  async function removePaper(paperId: string) {
    try {
      await api.remove(paperId);
      setBuilt((b) => b.filter((p) => p.paper_id !== paperId));
    } finally {
      setRemoving(null);
    }
  }
  const [health, setHealth] = useState<Health | null>(null);
  // A start that failed before there was a job: bad input, or a file that is not a PDF.
  const [error, setError] = useState<ApiError | null>(null);
  const [dragging, setDragging] = useState(false);
  // dragenter/dragleave fire for every child crossed; only a balanced count means "left".
  const dragDepth = useRef(0);
  // Jobs started from this page. The latest one is followed to its paper when it is done;
  // failures of any of them are shown. Builds started elsewhere just appear as progress.
  const [mine, setMine] = useState<string[]>([]);
  const watching = useRef<string | null>(null);
  const knownDone = useRef(new Set<string>());

  const refreshBuilt = useCallback(() => {
    api.list().then(setBuilt).catch(() => setBuilt([]));
  }, []);

  useEffect(refreshBuilt, [refreshBuilt]);
  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  // The build runs on the API, so this page only watches. Polling while anything is
  // active is what makes a reload harmless: the job is still there to be found.
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function tick() {
      try {
        const latest = await api.jobs();
        if (cancelled) return;
        setJobs(latest);
        for (const job of latest) {
          if (job.status !== "done" || knownDone.current.has(job.id)) continue;
          knownDone.current.add(job.id);
          refreshBuilt();
          if (job.id === watching.current && job.paper_id) {
            router.push(`/paper/${encodeURIComponent(job.paper_id)}`);
          }
        }
        const active = latest.some((j) => j.status === "queued" || j.status === "running");
        timer = setTimeout(tick, active ? POLL_MS : POLL_MS * 5);
      } catch {
        timer = setTimeout(tick, POLL_MS * 3);
      }
    }
    void tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [router, refreshBuilt]);

  async function start(begin: () => Promise<Job>) {
    setError(null);
    try {
      const job = await begin();
      setMine((ids) => [...ids, job.id]);
      watching.current = job.id;
      setJobs((prev) => (prev.some((j) => j.id === job.id) ? prev : [job, ...prev]));
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(e instanceof Error ? e.message : String(e)));
    }
  }

  function submit(reference: string) {
    setInput("");
    void start(() => api.startBuild(reference));
  }

  /**
   * The other way in. A quarter of PubMed's free full text was never deposited in PubMed
   * Central, and the publishers hosting it refuse automated downloads. They do not refuse
   * people, so a paper the reader can open they can also drop here.
   */
  function submitPdf(file: File) {
    if (!isPdf(file)) {
      setError(new ApiError(`${file.name} is not a PDF.`));
      return;
    }
    void start(() => api.startPdfBuild(file));
  }

  // Dropping a PDF anywhere on the page is the same as choosing it. The browser would
  // otherwise navigate to the file.
  const dragProps = {
    onDragEnter: (e: React.DragEvent) => {
      e.preventDefault();
      if (dragDepth.current++ === 0) setDragging(true);
    },
    onDragOver: (e: React.DragEvent) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    },
    onDragLeave: () => {
      if (--dragDepth.current === 0) setDragging(false);
    },
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      dragDepth.current = 0;
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) submitPdf(file);
    },
  };

  const active = jobs.filter((j) => j.status === "queued" || j.status === "running");
  const failures = jobs.filter((j) => j.status === "failed" && mine.includes(j.id));

  return (
    <main
      {...dragProps}
      className="relative mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center px-6 py-20 text-center"
    >
      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-40 grid place-items-center bg-black/70 backdrop-blur-sm">
          <div className="rounded-3xl border-2 border-dashed border-white/40 px-14 py-12">
            <p className="text-2xl font-medium text-[#e8e8e8]">Drop the PDF to build it</p>
          </div>
        </div>
      )}

      {/* The cup above the word: the logo is the brand, the word is its name. A plain img:
          the file is 37 KB and already the size it is shown at. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/icon.png" alt="" width={96} height={96} className="mb-5 h-24 w-24 rounded-[22px] shadow-[0_18px_50px_rgba(0,0,0,0.55)]" />
      <h1 className="text-6xl font-semibold tracking-tight text-[#e8e8e8] sm:text-7xl">
        espresso
      </h1>
      <p className="mt-6 max-w-xl text-[15px] leading-relaxed text-white/55">
        Paste a PubMed link. It comes back as a short explainer with interactive charts built
        from the paper&rsquo;s own numbers, every value checked against the source before it is
        drawn.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (input.trim()) submit(input.trim());
        }}
        className="mt-10 w-full max-w-xl"
      >
        <div className="flex items-center gap-2 rounded-full border border-white/[0.10] bg-white/[0.04] py-2 pr-2 pl-6 backdrop-blur-xl transition-colors focus-within:border-white/25">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="https://pubmed.ncbi.nlm.nih.gov/38740993/"
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

      {/* How to start, in two sentences a reader can take in at a glance: what to paste,
          and what to do when the paper is not in PubMed Central. The key words are
          brighter than the sentence; the one action is a pill. */}
      <div className="mt-6 max-w-xl space-y-2.5 text-[15px] leading-relaxed text-white/55">
        <p>
          Paste a <span className="text-[#e8e8e8]">PubMed</span> or <span className="text-[#e8e8e8]">PMC</span> link,
          a <span className="text-[#e8e8e8]">DOI</span> or a <span className="text-[#e8e8e8]">PMID</span>.
          The full text is read from PubMed Central.
        </p>
        <p className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1.5">
          <span>Not in PubMed Central?</span>
          <PdfPicker onPick={submitPdf} className="pill pill-strong">Open a PDF</PdfPicker>
          <span>or drop one anywhere on this page.</span>
        </p>
      </div>

      <ProviderLine health={health} />

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

      {error && <Failure message={error.message} kind={error.kind} url={error.url} onPick={submitPdf} />}
      {failures.map((job) => (
        <Failure
          key={job.id}
          label={job.label}
          message={job.error?.message ?? "The build failed."}
          kind={job.error?.kind ?? ""}
          url={job.error?.url ?? ""}
          onPick={submitPdf}
        />
      ))}

      {active.length > 0 && (
        <section className="mt-12 w-full text-left">
          <h2 className="mb-3 text-center text-[11px] tracking-[0.16em] text-white/25 uppercase">
            Building
          </h2>
          <div className="space-y-2">
            {active.map((job, i) => (
              <BuildCard key={job.id} job={job} queuedBehind={i} />
            ))}
          </div>
          <p className="mt-3 text-center text-xs text-white/30">
            Builds run one at a time on the API and carry on if you leave this page. Three to
            five minutes each: the model reads the whole paper to choose the charts.
          </p>
        </section>
      )}

      {built.length > 0 && (
        <section className="mt-16 w-full text-left">
          <h2 className="mb-3 text-center text-[11px] tracking-[0.16em] text-white/25 uppercase">
            Already built
          </h2>
          {/* A library past a dozen papers needs a filter and an order; both stay out of the
              way until there is something to type. */}
          {built.length > 5 && (
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter by title, journal or year"
                className="min-w-0 flex-1 rounded-full border border-white/[0.10] bg-white/[0.04] px-4 py-2 text-sm text-[#e8e8e8] placeholder:text-white/25 focus:border-white/25 focus:outline-none"
              />
              {(["newest", "title", "shortest"] as const).map((k) => (
                <button key={k} type="button" onClick={() => setOrder(k)} className={`pill ${order === k ? "pill-strong" : ""}`}>
                  {k === "newest" ? "Newest" : k === "title" ? "A to Z" : "Shortest read"}
                </button>
              ))}
            </div>
          )}
          <div className="space-y-2">
            {shown.map((p) => (
              <div
                key={p.paper_id}
                className="group flex w-full items-baseline justify-between gap-4 rounded-2xl border border-white/[0.08] bg-white/[0.04] px-5 py-3.5 text-left backdrop-blur-xl transition-colors hover:border-white/[0.14] hover:bg-white/[0.07]"
              >
                <button
                  type="button"
                  onClick={() => router.push(`/paper/${encodeURIComponent(p.paper_id)}`)}
                  className="min-w-0 flex-1 text-left"
                >
                  {/* Wraps rather than truncating. A paper is identified by its title, and the
                      half that gets cut is usually the half that distinguishes it. */}
                  <span className="block text-sm leading-snug text-[#e8e8e8]">{p.title}</span>
                  <span className="block text-xs text-white/30">
                    {[p.journal, p.published?.slice(0, 4), p.source === "pdf" ? "from a PDF" : null]
                      .filter(Boolean)
                      .join(" · ")}
                    {p.has_pdf && <span className="ml-2 rounded-full border border-white/[0.14] px-1.5 py-px text-[10px] text-white/50" title="The original PDF is stored; sentences open in it">PDF</span>}
                    {p.source === "pdf" && !p.has_text && <span className="ml-2 text-[#d9a441]" title="Built before the paper's text was kept; drop its PDF on the paper's page to rebuild">rebuild</span>}
                  </span>
                </button>
                <span className="num shrink-0 text-right text-xs text-white/40">
                  {p.chart_count} chart{p.chart_count === 1 ? "" : "s"}
                  {p.reading_minutes ? <span className="block text-white/25">{p.reading_minutes} min</span> : null}
                  {/* Removing is two clicks, in place, so no dialog and no accident. */}
                  {removing === p.paper_id ? (
                    <span className="mt-1 flex justify-end gap-1">
                      <button type="button" className="pill" onClick={() => void removePaper(p.paper_id)}>Remove</button>
                      <button type="button" className="pill" onClick={() => setRemoving(null)}>Keep</button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setRemoving(p.paper_id)}
                      className="mt-1 block w-full text-right text-[11px] text-white/25 opacity-0 transition-opacity group-hover:opacity-100 hover:text-white/60"
                    >
                      remove
                    </button>
                  )}
                </span>
              </div>
            ))}
            {shown.length === 0 && <p className="text-center text-xs text-white/30">Nothing matches.</p>}
          </div>
        </section>
      )}
    </main>
  );
}

const PROVIDER_LABELS: Record<string, string> = {
  claude_cli: "Claude Code",
  anthropic: "Anthropic API",
  openai: "OpenAI",
  azure: "Azure OpenAI",
};

/** Which model will do the building, and a way to change it. Says so when it cannot. */
function ProviderLine({ health }: { health: Health | null }) {
  if (!health) return null;
  const raw = health.services.llm_provider ?? "";
  const name = raw.split(" ")[0];
  const broken = raw.startsWith("unconfigured") || raw.includes("cannot build");
  if (broken) {
    const why = raw.includes("cannot build: ") ? raw.split("cannot build: ")[1].replace(/\)$/, "") : "No model is set up yet";
    return (
      <p className="mt-4 max-w-xl text-[13px] text-[#d9a441]">
        {why}. Papers already built still open.{" "}
        <Link href="/settings" className="underline decoration-[#d9a441]/40 underline-offset-4 hover:decoration-[#d9a441]">
          Set up a model
        </Link>
      </p>
    );
  }
  return (
    <p className="mt-4 flex items-center justify-center gap-2 text-[13px] text-white/40">
      <span>
        Model: <span className="text-white/70">{PROVIDER_LABELS[name] ?? name}</span>
      </span>
      <Link href="/settings" className="pill">Change</Link>
    </p>
  );
}

/** One build in progress: the stages as a checklist, with the API's own detail and clock. */
function BuildCard({ job, queuedBehind }: { job: Job; queuedBehind: number }) {
  const current = job.step === "done" ? STEPS.length : Math.max(0, STEPS.findIndex(([k]) => k === job.step));
  return (
    <div className="rounded-2xl border border-white/[0.08] bg-white/[0.04] p-6 backdrop-blur-xl">
      <div className="flex items-baseline justify-between gap-4">
        <p className="min-w-0 truncate text-sm text-[#e8e8e8]">{job.title ?? job.label}</p>
        <span className="num shrink-0 text-sm text-white/70">{mmss(job.elapsed)}</span>
      </div>
      {job.status === "queued" ? (
        <p className="mt-3 text-xs text-white/40">
          Queued{queuedBehind > 0 && `, ${queuedBehind} ahead of it`}. Starts when the build before it finishes.
        </p>
      ) : (
        <>
          <ol className="mt-4 space-y-2">
            {STEPS.map(([key, label], i) => (
              <li key={key} className="flex items-start gap-3">
                <span
                  className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                    i < current ? "bg-white/70" : i === current ? "animate-pulse bg-white" : "bg-white/15"
                  }`}
                />
                <p className={i > current ? "text-sm text-white/30" : "text-sm text-[#e8e8e8]"}>
                  {label}
                  {i === current && job.detail && (
                    <span className="ml-2 text-xs text-white/40">{job.detail}</span>
                  )}
                </p>
              </li>
            ))}
          </ol>
          <div className="mt-4 h-px w-full bg-white/[0.08]">
            <div className="h-px bg-white/60 transition-[width] duration-700" style={{ width: `${Math.round(job.fraction * 100)}%` }} />
          </div>
        </>
      )}
    </div>
  );
}

/** A failure the reader can read, and for the not-in-PMC case, act on. */
function Failure({
  label,
  message,
  kind,
  url,
  onPick,
}: {
  label?: string;
  message: string;
  kind: string;
  url: string;
  onPick: (file: File) => void;
}) {
  return (
    <div
      role="alert"
      className="mt-6 w-full max-w-xl rounded-xl border border-[#f27066]/30 bg-[#f27066]/10 p-4 text-left text-sm text-[#f27066]"
    >
      {label && <p className="mb-1 text-xs text-[#f27066]/70">{label}</p>}
      <p className="leading-relaxed">{message}</p>
      {kind === "not_in_pmc" && (
        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-[#f27066]/20 pt-3 text-xs">
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-[#e8e8e8] underline decoration-white/30 underline-offset-4 hover:decoration-white"
            >
              Open the paper at the publisher ↗
            </a>
          )}
          <span className="text-[#e8e8e8]">
            then <PdfPicker onPick={onPick} className="cursor-pointer underline decoration-white/30 underline-offset-4 hover:decoration-white">choose the downloaded PDF</PdfPicker> or
            drop it on this page.
          </span>
        </div>
      )}
    </div>
  );
}

/** A file chooser that reads as a link. Clearing the value lets the same file be chosen twice. */
function PdfPicker({
  onPick,
  className,
  children,
}: {
  onPick: (file: File) => void;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label
      className={
        className ??
        "cursor-pointer text-white/60 underline decoration-white/20 underline-offset-4 transition-colors hover:text-white"
      }
    >
      {children}
      <input
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) onPick(file);
        }}
      />
    </label>
  );
}
