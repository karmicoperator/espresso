"use client";

import { useCallback, useState, useMemo, useEffect } from "react";
import { motion, AnimatePresence, PanInfo } from "framer-motion";
import { VideoPlayer } from "@/components/VideoPlayer";
import { MarkdownContent } from "@/components/MarkdownContent";
import { FloatingDock } from "@/components/ui/floating-dock";
import { cn } from "@/lib/utils";

export type SectionModel = {
  id: string;
  title: string;
  content: string;
  level?: 1 | 2 | 3;
  equations?: string[];
  videoUrl?: string;
};

function mergeContentWithEquations(content: string, equations?: string[]): string {
  if (!equations || equations.length === 0) return content;

  let result = content;
  const equationsToAppend: string[] = [];

  for (const eq of equations) {
    const normalizedEq = eq.replace(/\s+/g, "");
    const normalizedContent = result.replace(/\s+/g, "");

    const alreadyPresent =
      normalizedContent.includes(normalizedEq) ||
      normalizedContent.includes(`$${normalizedEq}$`) ||
      normalizedContent.includes(`$$${normalizedEq}$$`);

    if (!alreadyPresent) {
      equationsToAppend.push(eq);
    }
  }

  if (equationsToAppend.length > 0) {
    const equationBlocks = equationsToAppend
      .map((eq) => {
        const trimmed = eq.trim();
        if (trimmed.startsWith("$$") && trimmed.endsWith("$$")) return trimmed;
        if (trimmed.startsWith("$") && trimmed.endsWith("$") && !trimmed.startsWith("$$")) {
          return `$${trimmed}$`;
        }
        return `$$${trimmed}$$`;
      })
      .join("\n\n");

    result = `${result}\n\n${equationBlocks}`;
  }

  return result;
}

const SectionIcon = ({ index }: { index: number }) => (
  <span className="text-sm font-semibold">{index + 1}</span>
);

export function SectionViewer({ sections }: { sections: SectionModel[] }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeSection = sections[activeIndex];

  const unifiedContent = useMemo(
    () =>
      activeSection
        ? mergeContentWithEquations(activeSection.content, activeSection.equations)
        : "",
    [activeSection]
  );

  const goToSection = useCallback(
    (index: number) => {
      if (index >= 0 && index < sections.length) {
        setActiveIndex(index);
      }
    },
    [sections.length]
  );

  const goNext = useCallback(() => {
    if (activeIndex < sections.length - 1) {
      setActiveIndex(activeIndex + 1);
    }
  }, [activeIndex, sections.length]);

  const goPrev = useCallback(() => {
    if (activeIndex > 0) {
      setActiveIndex(activeIndex - 1);
    }
  }, [activeIndex]);

  const dockItems = sections.map((section, idx) => ({
    id: section.id,
    title: section.title,
    icon: <SectionIcon index={idx} />,
  }));

  const progress = sections.length > 1 ? (activeIndex / (sections.length - 1)) * 100 : 100;

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't capture if user is typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault();
        goNext();
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        goPrev();
      } else if (e.key === "Home") {
        e.preventDefault();
        goToSection(0);
      } else if (e.key === "End") {
        e.preventDefault();
        goToSection(sections.length - 1);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [goNext, goPrev, goToSection, sections.length]);

  // Swipe gesture handler
  const handleDragEnd = useCallback(
    (_: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
      const threshold = 50;
      if (info.offset.x < -threshold) {
        goNext();
      } else if (info.offset.x > threshold) {
        goPrev();
      }
    },
    [goNext, goPrev]
  );

  if (!activeSection) return null;

  return (
    <div className="relative">
      {/* Progress bar at top */}
      <div className="sticky top-0 z-30 bg-[#1c1c2e]/80 backdrop-blur-xl border-b border-[#58c4dd]/10">
        <div className="h-1 bg-[#141421]">
          <motion.div
            className="h-full bg-gradient-to-r from-[#58c4dd] to-[#cd8b62]"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.4, ease: "easeOut" }}
          />
        </div>
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-sm text-[#f4f1eb]/50">Section</span>
            <span className="font-mono text-[#f4f1eb] font-medium">
              {activeIndex + 1} / {sections.length}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={goPrev}
              disabled={activeIndex === 0}
              className={cn(
                "p-2 rounded-lg ring-1 transition-all duration-200",
                activeIndex === 0
                  ? "ring-[#58c4dd]/5 text-[#f4f1eb]/20 cursor-not-allowed"
                  : "ring-[#58c4dd]/20 text-[#f4f1eb]/70 hover:bg-[#58c4dd]/10 hover:text-[#58c4dd]"
              )}
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <button
              onClick={goNext}
              disabled={activeIndex === sections.length - 1}
              className={cn(
                "p-2 rounded-lg ring-1 transition-all duration-200",
                activeIndex === sections.length - 1
                  ? "ring-[#58c4dd]/5 text-[#f4f1eb]/20 cursor-not-allowed"
                  : "ring-[#58c4dd]/20 text-[#f4f1eb]/70 hover:bg-[#58c4dd]/10 hover:text-[#58c4dd]"
              )}
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Main content area */}
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="grid lg:grid-cols-12 gap-8">
          {/* Sidebar with mini-nav */}
          <aside className="lg:col-span-3">
            <div className="lg:sticky lg:top-24">
              <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                className="rounded-2xl bg-[#141421] p-4 ring-1 ring-[#58c4dd]/10"
              >
                <div className="text-xs font-medium text-[#f4f1eb]/50 uppercase tracking-wider mb-3">
                  Sections
                </div>
                <nav className="space-y-1 max-h-[60vh] overflow-y-auto scrollbar-thin scrollbar-thumb-[#58c4dd]/20">
                  {sections.map((section, idx) => {
                    const isActive = idx === activeIndex;
                    return (
                      <button
                        key={section.id}
                        onClick={() => goToSection(idx)}
                        className={cn(
                          "w-full text-left px-3 py-2 rounded-lg text-sm transition-all duration-200 flex items-center gap-2",
                          isActive
                            ? "bg-gradient-to-r from-[#58c4dd]/20 to-[#cd8b62]/20 text-[#f4f1eb] ring-1 ring-[#58c4dd]/30"
                            : "text-[#f4f1eb]/50 hover:text-[#f4f1eb]/80 hover:bg-[#58c4dd]/5"
                        )}
                      >
                        <span
                          className={cn(
                            "w-6 h-6 rounded-md flex items-center justify-center text-xs font-medium ring-1 shrink-0",
                            isActive
                              ? "bg-[#58c4dd]/20 text-[#58c4dd] ring-[#58c4dd]/30"
                              : "bg-[#1c1c2e] text-[#f4f1eb]/40 ring-[#58c4dd]/10"
                          )}
                        >
                          {idx + 1}
                        </span>
                        <span className="truncate">{section.title}</span>
                      </button>
                    );
                  })}
                </nav>
              </motion.div>

              {/* Navigation hints */}
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="mt-4 rounded-xl bg-[#141421] p-4 ring-1 ring-[#58c4dd]/10 space-y-4"
              >
                {/* Mobile swipe hint */}
                <div className="lg:hidden">
                  <div className="text-xs font-medium text-[#f4f1eb]/50 mb-2">Navigation</div>
                  <div className="flex items-center gap-2 text-xs text-[#f4f1eb]/40">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
                    </svg>
                    <span>Swipe left/right to navigate</span>
                  </div>
                </div>

                {/* Desktop keyboard hints */}
                <div className="hidden lg:block">
                  <div className="text-xs font-medium text-[#f4f1eb]/50 mb-3">Keyboard Shortcuts</div>
                  <div className="grid grid-cols-2 gap-2 text-xs text-[#f4f1eb]/40">
                    <div className="flex items-center gap-1.5">
                      <kbd className="px-1.5 py-0.5 rounded bg-[#58c4dd]/10 font-mono text-[10px] text-[#58c4dd]">←</kbd>
                      <span>Previous</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <kbd className="px-1.5 py-0.5 rounded bg-[#58c4dd]/10 font-mono text-[10px] text-[#58c4dd]">→</kbd>
                      <span>Next</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <kbd className="px-1.5 py-0.5 rounded bg-[#58c4dd]/10 font-mono text-[10px] text-[#58c4dd]">Home</kbd>
                      <span>First</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <kbd className="px-1.5 py-0.5 rounded bg-[#58c4dd]/10 font-mono text-[10px] text-[#58c4dd]">End</kbd>
                      <span>Last</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            </div>
          </aside>

          {/* Main section content */}
          <main className="lg:col-span-9">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeSection.id}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
                drag="x"
                dragConstraints={{ left: 0, right: 0 }}
                dragElastic={0.1}
                onDragEnd={handleDragEnd}
                className="space-y-6 cursor-grab active:cursor-grabbing"
              >
                {/* Section header */}
                <div className="rounded-2xl bg-gradient-to-br from-[#58c4dd]/5 to-[#cd8b62]/5 p-6 ring-1 ring-[#58c4dd]/10">
                  <div className="flex items-start gap-4">
                    <motion.div
                      initial={{ scale: 0.8 }}
                      animate={{ scale: 1 }}
                      className="h-12 w-12 rounded-xl bg-gradient-to-br from-[#58c4dd]/20 to-[#cd8b62]/20 flex items-center justify-center ring-1 ring-[#58c4dd]/20 shrink-0"
                    >
                      <span className="text-lg font-bold text-[#58c4dd]">{activeIndex + 1}</span>
                    </motion.div>
                    <div>
                      <h2 className="text-2xl sm:text-3xl font-medium text-[#f4f1eb] tracking-tight">
                        {activeSection.title}
                      </h2>
                      <div className="mt-2 flex items-center gap-3 text-sm text-[#f4f1eb]/50">
                        <span>
                          {activeSection.content.split(/\s+/).length} words
                        </span>
                        {activeSection.videoUrl && (
                          <>
                            <span className="w-1 h-1 rounded-full bg-[#f4f1eb]/30" />
                            <span className="text-[#58c4dd]">Has visualization</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Video section - prominent placement */}
                {activeSection.videoUrl && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.1 }}
                    className="rounded-2xl overflow-hidden ring-1 ring-[#58c4dd]/20 shadow-2xl shadow-[#58c4dd]/10"
                  >
                    <div className="bg-gradient-to-r from-[#58c4dd]/10 to-[#cd8b62]/10 px-4 py-3 border-b border-[#58c4dd]/10">
                      <div className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-full bg-[#fc6255]/80" />
                        <div className="w-3 h-3 rounded-full bg-[#f9c74f]/80" />
                        <div className="w-3 h-3 rounded-full bg-[#83c167]/80" />
                        <span className="ml-3 text-sm text-[#f4f1eb]/60">Manim Visualization</span>
                      </div>
                    </div>
                    <VideoPlayer src={activeSection.videoUrl} title="Concept Visualization" />
                  </motion.div>
                )}

                {/* Content section */}
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.2 }}
                  className="rounded-2xl bg-[#141421] p-6 sm:p-8 ring-1 ring-[#58c4dd]/10"
                >
                  <div className="prose prose-invert prose-lg max-w-none">
                    <div className="text-[#f4f1eb]/70 leading-relaxed">
                      <MarkdownContent content={unifiedContent} />
                    </div>
                  </div>
                </motion.div>

                {/* Navigation buttons */}
                <div className="flex items-center justify-between pt-4">
                  <button
                    onClick={goPrev}
                    disabled={activeIndex === 0}
                    className={cn(
                      "group flex items-center gap-3 px-5 py-3 rounded-xl transition-all duration-200",
                      activeIndex === 0
                        ? "opacity-40 cursor-not-allowed"
                        : "bg-[#141421] hover:bg-[#58c4dd]/10 ring-1 ring-[#58c4dd]/10 hover:ring-[#58c4dd]/30"
                    )}
                  >
                    <svg
                      className="w-5 h-5 text-[#f4f1eb]/70 group-hover:-translate-x-1 transition-transform"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                    </svg>
                    <div className="text-left">
                      <div className="text-xs text-[#f4f1eb]/50">Previous</div>
                      <div className="text-sm text-[#f4f1eb]/80 max-w-[150px] truncate">
                        {activeIndex > 0 ? sections[activeIndex - 1].title : "—"}
                      </div>
                    </div>
                  </button>

                  <button
                    onClick={goNext}
                    disabled={activeIndex === sections.length - 1}
                    className={cn(
                      "group flex items-center gap-3 px-5 py-3 rounded-xl transition-all duration-200",
                      activeIndex === sections.length - 1
                        ? "opacity-40 cursor-not-allowed"
                        : "bg-gradient-to-r from-[#58c4dd]/10 to-[#cd8b62]/10 hover:from-[#58c4dd]/20 hover:to-[#cd8b62]/20 ring-1 ring-[#58c4dd]/20"
                    )}
                  >
                    <div className="text-right">
                      <div className="text-xs text-[#f4f1eb]/50">Next</div>
                      <div className="text-sm text-[#f4f1eb]/80 max-w-[150px] truncate">
                        {activeIndex < sections.length - 1 ? sections[activeIndex + 1].title : "—"}
                      </div>
                    </div>
                    <svg
                      className="w-5 h-5 text-[#f4f1eb]/70 group-hover:translate-x-1 transition-transform"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </button>
                </div>
              </motion.div>
            </AnimatePresence>
          </main>
        </div>
      </div>

      {/* Floating dock for quick navigation */}
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50">
        <FloatingDock
          items={dockItems}
          activeId={activeSection.id}
          onItemClick={(id) => {
            const idx = sections.findIndex((s) => s.id === id);
            if (idx >= 0) goToSection(idx);
          }}
        />
      </div>

      {/* Spacer for floating dock */}
      <div className="h-24" />
    </div>
  );
}
