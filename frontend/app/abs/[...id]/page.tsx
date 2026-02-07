"use client";

import Link from "next/link";
import { useEffect, useState, useCallback, use } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { SectionViewer, type SectionModel } from "@/components/SectionViewer";
import { HoverEffect } from "@/components/ui/card-hover-effect";
import type { Paper, ProcessingStatus } from "@/lib/types";
import {
  getPaper,
  processArxivPaper,
  getProcessingStatus,
  toProcessingStatus,
} from "@/lib/api";

function normalizeArxivId(segments: string[] | undefined): string {
  if (!segments || segments.length === 0) return "";
  const joined = segments.join("/");
  try {
    return decodeURIComponent(joined);
  } catch {
    return joined;
  }
}

type PageState =
  | { type: "loading" }
  | { type: "not_found"; arxivId: string }
  | { type: "processing"; status: ProcessingStatus }
  | { type: "ready"; paper: Paper }
  | { type: "error"; message: string };

// Helper to clamp heading levels
function clampLevel(level: number): 1 | 2 | 3 {
  if (level <= 1) return 1;
  if (level === 2) return 2;
  return 3;
}

export default function PaperPage({
  params,
}: {
  params: Promise<{ id?: string[] }>;
}) {
  const resolvedParams = use(params);
  const arxivId = normalizeArxivId(resolvedParams.id);
  const absUrl = arxivId ? `https://arxiv.org/abs/${arxivId}` : "https://arxiv.org";
  const pdfUrl = arxivId ? `https://arxiv.org/pdf/${arxivId}.pdf` : "https://arxiv.org";

  const [state, setState] = useState<PageState>({ type: "loading" });
  const [jobId, setJobId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"overview" | "reader">("overview");

  // Fetch the paper or start processing
  const loadPaper = useCallback(async () => {
    if (!arxivId) {
      setState({ type: "error", message: "No arXiv ID provided" });
      return;
    }

    try {
      const paper = await getPaper(arxivId);
      if (paper) {
        setState({ type: "ready", paper });
        return;
      }
      setState({ type: "not_found", arxivId });
    } catch (err) {
      console.error("Error loading paper:", err);
      setState({
        type: "error",
        message: err instanceof Error ? err.message : "Failed to load paper",
      });
    }
  }, [arxivId]);

  // Start processing the paper
  const startProcessing = useCallback(async () => {
    if (!arxivId) return;

    try {
      const response = await processArxivPaper(arxivId);
      setJobId(response.job_id);
      setState({
        type: "processing",
        status: {
          job_id: response.job_id,
          status: response.status,
          progress: 0,
          sections_completed: 0,
          sections_total: 0,
          current_step: "Starting...",
        },
      });
    } catch (err) {
      console.error("Error starting processing:", err);
      setState({
        type: "error",
        message: err instanceof Error ? err.message : "Failed to start processing",
      });
    }
  }, [arxivId]);

  // Poll for processing status
  useEffect(() => {
    if (state.type !== "processing" || !jobId) return;

    const pollInterval = setInterval(async () => {
      try {
        const response = await getProcessingStatus(jobId);
        const status = toProcessingStatus(response);

        if (response.status === "completed") {
          clearInterval(pollInterval);
          const paper = await getPaper(arxivId);
          if (paper) {
            setState({ type: "ready", paper });
          } else {
            setState({ type: "error", message: "Paper processing completed but paper not found" });
          }
        } else if (response.status === "failed") {
          clearInterval(pollInterval);
          setState({
            type: "error",
            message: response.error || "Processing failed",
          });
        } else {
          setState({ type: "processing", status });
        }
      } catch (err) {
        console.error("Error polling status:", err);
      }
    }, 2000);

    return () => clearInterval(pollInterval);
  }, [state.type, jobId, arxivId]);

  // Initial load
  useEffect(() => {
    loadPaper();
  }, [loadPaper]);

  return (
    <main className="min-h-dvh relative overflow-hidden bg-[#1c1c2e]">
      {/* Grid background */}
      <div className="absolute inset-0 grid-3b1b" />
      
      {/* Gradient orbs */}
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-[#58c4dd]/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-[400px] h-[400px] bg-[#cd8b62]/5 rounded-full blur-[100px] pointer-events-none" />

      <div className="relative z-10">
        {/* Fixed Header */}
        <motion.header
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="sticky top-0 z-40 bg-[#1c1c2e]/80 backdrop-blur-2xl border-b border-[#58c4dd]/10"
        >
          <div className="mx-auto w-full max-w-7xl px-6 py-4">
            <div className="flex items-center justify-between gap-4">
              <Link
                href="/"
                className="group inline-flex items-center gap-2 rounded-xl bg-[#58c4dd]/5 px-4 py-2.5 text-sm text-[#f4f1eb]/80 ring-1 ring-[#58c4dd]/20 transition-all hover:bg-[#58c4dd]/10 hover:ring-[#58c4dd]/30"
              >
                <motion.span
                  aria-hidden
                  className="transition-transform group-hover:-translate-x-1 text-[#58c4dd]"
                >
                  ←
                </motion.span>
                Back
              </Link>

              <div className="flex-1 flex items-center justify-center">
                <div className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-[#58c4dd]/5 ring-1 ring-[#58c4dd]/20">
                  <div className="w-2 h-2 rounded-full bg-[#83c167] animate-pulse" />
                  <span className="text-sm font-mono text-[#f4f1eb]/70">{arxivId || "Loading..."}</span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <motion.a
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  href={absUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-xl bg-[#58c4dd]/5 px-4 py-2.5 text-sm text-[#f4f1eb]/80 ring-1 ring-[#58c4dd]/20 transition hover:bg-[#58c4dd]/10"
                >
                  arXiv
                </motion.a>
                <motion.a
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  href={pdfUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-xl bg-gradient-to-r from-[#58c4dd]/20 to-[#cd8b62]/20 px-4 py-2.5 text-sm text-[#f4f1eb]/80 ring-1 ring-[#58c4dd]/30 transition hover:from-[#58c4dd]/30 hover:to-[#cd8b62]/30"
                >
                  PDF
                </motion.a>
              </div>
            </div>
          </div>
        </motion.header>

        {/* Content based on state */}
        <div className="min-h-[calc(100dvh-80px)]">
          {state.type === "loading" && <LoadingState message="Loading paper..." />}

          {state.type === "not_found" && (
            <NotFoundState arxivId={state.arxivId} onProcess={startProcessing} />
          )}

          {state.type === "processing" && <ProcessingState status={state.status} />}

          {state.type === "error" && (
            <ErrorState message={state.message} onRetry={loadPaper} />
          )}

          {state.type === "ready" && (
            <AnimatePresence mode="wait">
              {viewMode === "overview" ? (
                <OverviewMode
                  key="overview"
                  paper={state.paper}
                  onStartReading={() => setViewMode("reader")}
                />
              ) : (
                <ReaderMode
                  key="reader"
                  paper={state.paper}
                  onBack={() => setViewMode("overview")}
                />
              )}
            </AnimatePresence>
          )}
        </div>
      </div>
    </main>
  );
}

// === Overview Mode - Beautiful landing for the paper ===
function OverviewMode({
  paper,
  onStartReading,
}: {
  paper: Paper;
  onStartReading: () => void;
}) {
  const sectionsWithVideo = paper.sections.filter((s) => s.video_url);
  const totalEquations = paper.sections.reduce(
    (acc, s) => acc + (s.equations?.length || 0),
    0
  );

  const stats = [
    {
      title: "Sections",
      description: `${paper.sections.length} sections to explore`,
      icon: (
        <span className="text-2xl text-[#58c4dd]">§</span>
      ),
    },
    {
      title: "Visualizations",
      description: `${sectionsWithVideo.length} animated explanations`,
      icon: (
        <span className="text-2xl text-[#cd8b62]">▶</span>
      ),
    },
    {
      title: "Equations",
      description: `${totalEquations} mathematical expressions`,
      icon: (
        <span className="text-2xl text-[#f9c74f]">∑</span>
      ),
    },
  ];

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5 }}
      className="px-6 py-12"
    >
      <div className="max-w-6xl mx-auto space-y-12">
        {/* Hero section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="text-center space-y-6"
        >
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-r from-[#58c4dd]/10 to-[#cd8b62]/10 ring-1 ring-[#58c4dd]/20">
            <span className="w-2 h-2 rounded-full bg-[#58c4dd]" />
            <span className="text-sm text-[#f4f1eb]/70">Research Paper</span>
          </div>

          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-medium text-[#f4f1eb] leading-tight tracking-tight max-w-4xl mx-auto">
            {paper.title}
          </h1>

          <p className="text-[#f4f1eb]/50 max-w-2xl mx-auto">
            {paper.authors.join(", ")}
          </p>

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onStartReading}
            className="mt-4 inline-flex items-center gap-3 px-8 py-4 rounded-2xl bg-gradient-to-r from-[#58c4dd] to-[#cd8b62] text-[#1c1c2e] font-semibold shadow-xl shadow-[#58c4dd]/25 ring-1 ring-white/20 transition hover:shadow-[#58c4dd]/40"
          >
            Start Reading
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </motion.button>
        </motion.div>

        {/* Stats cards */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <HoverEffect items={stats} />
        </motion.div>

        {/* Abstract section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="rounded-3xl bg-gradient-to-br from-[#58c4dd]/5 to-[#cd8b62]/5 p-8 ring-1 ring-[#58c4dd]/10"
        >
          <h2 className="text-lg font-semibold text-[#f4f1eb] mb-4 flex items-center gap-3">
            <span className="w-8 h-8 rounded-lg bg-[#58c4dd]/20 flex items-center justify-center text-[#58c4dd]">
              ∴
            </span>
            Abstract
          </h2>
          <p className="text-[#f4f1eb]/60 leading-relaxed text-lg">
            {paper.abstract}
          </p>
        </motion.div>

        {/* Table of contents preview */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <h2 className="text-lg font-semibold text-[#f4f1eb] mb-6 flex items-center gap-3">
            <span className="w-8 h-8 rounded-lg bg-[#cd8b62]/20 flex items-center justify-center text-[#cd8b62]">
              ≡
            </span>
            Table of Contents
          </h2>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {[...paper.sections]
              .sort((a, b) => a.order_index - b.order_index)
              .map((section, idx) => (
                <motion.button
                  key={section.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.4 + idx * 0.05 }}
                  onClick={onStartReading}
                  className="group relative text-left p-4 rounded-xl bg-[#141421] ring-1 ring-[#58c4dd]/10 hover:ring-[#58c4dd]/30 hover:bg-[#58c4dd]/5 transition-all duration-200"
                >
                  <div className="flex items-start gap-3">
                    <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#58c4dd]/20 to-[#cd8b62]/20 flex items-center justify-center text-sm font-semibold text-[#f4f1eb]/70 ring-1 ring-[#58c4dd]/20 shrink-0">
                      {idx + 1}
                    </span>
                    <div className="min-w-0">
                      <h3 className="font-medium text-[#f4f1eb]/80 group-hover:text-[#f4f1eb] transition-colors truncate">
                        {section.title}
                      </h3>
                      <div className="mt-1 flex items-center gap-2 text-xs text-[#f4f1eb]/40">
                        {section.video_url && (
                          <span className="flex items-center gap-1 text-[#58c4dd]">
                            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                              <path d="M8 5v14l11-7z" />
                            </svg>
                            Video
                          </span>
                        )}
                        {section.equations && section.equations.length > 0 && (
                          <span>{section.equations.length} equations</span>
                        )}
                      </div>
                    </div>
                  </div>
                </motion.button>
              ))}
          </div>
        </motion.div>

        {/* Quick start CTA */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="text-center py-8"
        >
          <div className="inline-flex flex-col items-center gap-4 p-8 rounded-3xl bg-gradient-to-br from-[#58c4dd]/10 to-[#cd8b62]/10 ring-1 ring-[#58c4dd]/20">
            <div className="text-5xl">π</div>
            <h3 className="text-xl font-semibold text-[#f4f1eb]">Ready to dive in?</h3>
            <p className="text-[#f4f1eb]/50 max-w-md">
              Navigate through sections seamlessly with our interactive reader, complete with visualizations and equations.
            </p>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={onStartReading}
              className="mt-2 px-6 py-3 rounded-xl bg-[#58c4dd]/10 text-[#f4f1eb] font-medium ring-1 ring-[#58c4dd]/20 hover:bg-[#58c4dd]/20 transition-all"
            >
              Begin Reading Experience
            </motion.button>
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}

// === Reader Mode - Full section-by-section experience ===
function ReaderMode({
  paper,
  onBack,
}: {
  paper: Paper;
  onBack: () => void;
}) {
  const sections: SectionModel[] = [...paper.sections]
    .sort((a, b) => a.order_index - b.order_index)
    .map((s) => ({
      id: s.id,
      title: s.title,
      content: s.summary || s.content,
      level: clampLevel(s.level),
      equations: s.equations,
      videoUrl: s.video_url,
    }));

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
    >
      {/* Back to overview button */}
      <div className="sticky top-[73px] z-30 bg-[#1c1c2e]/80 backdrop-blur-xl border-b border-[#58c4dd]/5">
        <div className="max-w-6xl mx-auto px-6 py-2 flex items-center justify-between">
          <button
            onClick={onBack}
            className="group flex items-center gap-2 text-sm text-[#f4f1eb]/60 hover:text-[#58c4dd] transition-colors"
          >
            <svg
              className="w-4 h-4 group-hover:-translate-x-1 transition-transform"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back to Overview
          </button>
          <h2 className="text-sm font-medium text-[#f4f1eb]/80 truncate max-w-md">
            {paper.title}
          </h2>
        </div>
      </div>

      <SectionViewer sections={sections} />
    </motion.div>
  );
}

// === State Components ===

function LoadingState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-32 px-6">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="relative"
      >
        <div className="h-20 w-20 rounded-2xl bg-gradient-to-br from-[#58c4dd]/20 to-[#cd8b62]/20 ring-1 ring-[#58c4dd]/20" />
        <div className="absolute inset-0 h-20 w-20 animate-spin rounded-2xl border-4 border-transparent border-t-[#58c4dd]" style={{ animationDuration: '2s' }} />
        <div className="absolute inset-2 h-16 w-16 animate-spin rounded-xl border-4 border-transparent border-t-[#cd8b62]" style={{ animationDirection: 'reverse', animationDuration: '1.5s' }} />
      </motion.div>
      <motion.p
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="mt-8 text-[#f4f1eb]/60"
      >
        {message}
      </motion.p>
    </div>
  );
}

function NotFoundState({
  arxivId,
  onProcess,
}: {
  arxivId: string;
  onProcess: () => void;
}) {
  return (
    <div className="flex items-center justify-center py-20 px-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-lg text-center"
      >
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ delay: 0.2, type: "spring", stiffness: 200 }}
          className="mx-auto h-24 w-24 rounded-3xl bg-gradient-to-br from-[#58c4dd]/20 to-[#cd8b62]/20 grid place-items-center ring-1 ring-[#58c4dd]/20 shadow-2xl shadow-[#58c4dd]/10"
        >
          <span className="text-4xl text-[#58c4dd]">∫</span>
        </motion.div>

        <h2 className="mt-8 text-2xl font-medium text-[#f4f1eb]">Paper Not Yet Processed</h2>
        <p className="mt-4 text-[#f4f1eb]/50 leading-relaxed">
          This paper (<span className="font-mono text-[#58c4dd] bg-[#58c4dd]/10 px-2 py-0.5 rounded">{arxivId}</span>) hasn't been visualized yet.
          We'll parse the content and generate beautiful Manim animations for key concepts.
        </p>

        <div className="mt-8 space-y-4">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onProcess}
            className="w-full sm:w-auto rounded-2xl bg-gradient-to-r from-[#58c4dd] to-[#cd8b62] px-8 py-4 text-sm font-semibold text-[#1c1c2e] shadow-xl shadow-[#58c4dd]/25 ring-1 ring-white/20 transition hover:shadow-[#58c4dd]/40"
          >
            Start Processing
          </motion.button>

          <p className="text-xs text-[#f4f1eb]/30">
            This usually takes 1-3 minutes depending on paper length
          </p>
        </div>
      </motion.div>
    </div>
  );
}

function ProcessingState({ status }: { status: ProcessingStatus }) {
  const progressPercent = Math.round(status.progress * 100);

  const steps = [
    { label: "Fetching paper from arXiv", threshold: 10, icon: "∫" },
    { label: "Parsing sections and content", threshold: 30, icon: "∂" },
    { label: "Analyzing concepts for visualization", threshold: 50, icon: "∇" },
    { label: "Generating Manim animations", threshold: 70, icon: "λ" },
    { label: "Rendering videos", threshold: 90, icon: "∞" },
  ];

  return (
    <div className="flex items-center justify-center py-16 px-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-2xl"
      >
        <div className="rounded-3xl bg-gradient-to-br from-[#58c4dd]/5 to-[#cd8b62]/5 p-8 ring-1 ring-[#58c4dd]/10 backdrop-blur-sm">
          {/* Header */}
          <div className="flex items-center gap-5">
            <div className="relative">
              <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-[#58c4dd]/20 to-[#cd8b62]/20 ring-1 ring-[#58c4dd]/20" />
              <div className="absolute inset-0 h-16 w-16 animate-spin rounded-2xl border-4 border-transparent border-t-[#58c4dd]" style={{ animationDuration: '2s' }} />
            </div>
            <div>
              <h2 className="text-2xl font-medium text-[#f4f1eb]">Processing Paper</h2>
              <p className="mt-1 text-[#f4f1eb]/50">{status.current_step || "Preparing..."}</p>
            </div>
          </div>

          {/* Progress */}
          <div className="mt-8">
            <div className="flex items-center justify-between text-sm mb-3">
              <span className="text-[#f4f1eb]/50">Overall Progress</span>
              <span className="font-mono text-[#f4f1eb] font-medium">{progressPercent}%</span>
            </div>
            <div className="h-3 rounded-full bg-[#141421] overflow-hidden ring-1 ring-[#58c4dd]/10">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-[#58c4dd] to-[#cd8b62]"
                initial={{ width: 0 }}
                animate={{ width: `${progressPercent}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
          </div>

          {/* Sections */}
          {status.sections_total > 0 && (
            <div className="mt-4 flex items-center gap-3 text-sm">
              <span className="text-[#f4f1eb]/40">Sections processed:</span>
              <span className="font-mono text-[#f4f1eb]/70 bg-[#58c4dd]/10 px-2 py-0.5 rounded">
                {status.sections_completed} / {status.sections_total}
              </span>
            </div>
          )}

          {/* Steps */}
          <div className="mt-8 rounded-2xl bg-[#141421] p-6 ring-1 ring-[#58c4dd]/10">
            <div className="text-xs font-medium text-[#f4f1eb]/40 uppercase tracking-wider mb-4">Pipeline Progress</div>
            <ol className="space-y-3">
              {steps.map((step, i) => {
                const isActive = progressPercent >= step.threshold;
                const isCurrent = progressPercent >= step.threshold && (i === steps.length - 1 || progressPercent < steps[i + 1].threshold);

                return (
                  <motion.li
                    key={i}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.1 }}
                    className="flex items-center gap-4"
                  >
                    <span className={`text-xl transition-all duration-300 ${isActive ? 'text-[#58c4dd]' : 'text-[#f4f1eb]/20'}`}>
                      {step.icon}
                    </span>
                    <span className={`flex-1 text-sm transition-colors duration-300 ${isActive ? 'text-[#f4f1eb]/80' : 'text-[#f4f1eb]/30'}`}>
                      {step.label}
                    </span>
                    {isCurrent && (
                      <span className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-[#58c4dd] animate-pulse" />
                        <span className="text-xs text-[#58c4dd]">In progress</span>
                      </span>
                    )}
                    {isActive && !isCurrent && (
                      <span className="text-[#83c167]">✓</span>
                    )}
                  </motion.li>
                );
              })}
            </ol>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex items-center justify-center py-20 px-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-lg text-center"
      >
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", stiffness: 200 }}
          className="mx-auto h-24 w-24 rounded-3xl bg-[#fc6255]/10 grid place-items-center ring-1 ring-[#fc6255]/20"
        >
          <span className="text-4xl text-[#fc6255]">!</span>
        </motion.div>

        <h2 className="mt-8 text-2xl font-medium text-[#fc6255]">Something Went Wrong</h2>
        <p className="mt-4 text-[#f4f1eb]/50 leading-relaxed">{message}</p>

        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={onRetry}
          className="mt-8 rounded-2xl bg-[#58c4dd]/10 px-8 py-4 text-sm font-semibold text-[#f4f1eb] ring-1 ring-[#58c4dd]/20 transition hover:bg-[#58c4dd]/20"
        >
          Try Again
        </motion.button>
      </motion.div>
    </div>
  );
}
