"use client";

import {
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  motion,
  useScroll,
  useSpring,
  useTransform,
  useMotionValueEvent,
  type MotionValue,
} from "framer-motion";
import { StackCard } from "@/components/StackCard";
import type { ScrollySectionModel } from "@/components/ScrollySection";
import { cn } from "@/lib/utils";

// --- Deck layout constants ---
const SCROLL_PER_SECTION = 2; // 200vh scroll per section
const EXIT_THRESHOLD = 0.75; // 0–0.75 = content phase, 0.75–1.0 = exit phase
const STACK_GAP_X = 12; // px rightward offset per deck position
const STACK_GAP_Y = 10; // px downward offset per deck position
const STACK_SCALE_STEP = 0.03; // scale shrinks per position
const STACK_OPACITY_STEP = 0.15; // opacity dims per position

/**
 * Compute deck position transforms for a single card.
 * Uses deck-position model: 0 = top/active, 1 = second, 2 = third, etc.
 */
function CardSlot({
  section,
  index,
  totalSections,
  scrollYProgress,
  activeIndex,
  contentHeightsRef,
  onContentHeight,
}: {
  section: ScrollySectionModel;
  index: number;
  totalSections: number;
  scrollYProgress: MotionValue<number>;
  activeIndex: number;
  contentHeightsRef: React.RefObject<number[]>;
  onContentHeight: (index: number, height: number) => void;
}) {
  const N = totalSections;
  const segStart = index / N;
  const segEnd = (index + 1) / N;
  const segLen = segEnd - segStart;
  const exitStart = segStart + segLen * EXIT_THRESHOLD;

  // Helper: get effective deck position for this card given scroll progress
  function getDeckState(v: number) {
    const currentActive = Math.min(Math.floor(v * N), N - 1);
    const rawDeckPos = index - currentActive;

    // Exit progress for the currently-active card's exit phase
    const activeSegStart = currentActive / N;
    const activeSegEnd = (currentActive + 1) / N;
    const activeExitStart =
      activeSegStart + (activeSegEnd - activeSegStart) * EXIT_THRESHOLD;
    const exitProgress =
      v >= activeExitStart && v < activeSegEnd
        ? (v - activeExitStart) / (activeSegEnd - activeExitStart)
        : 0;

    return { rawDeckPos, currentActive, exitProgress };
  }

  // --- Card X (horizontal: stack offset + slide-left exit) ---
  const cardX = useTransform(scrollYProgress, (v) => {
    const { rawDeckPos, currentActive, exitProgress } = getDeckState(v);

    // This card is the one currently exiting
    if (index === currentActive && exitProgress > 0) {
      // Slide left: 0 → -110vw
      const vw = typeof window !== "undefined" ? window.innerWidth : 1000;
      return -exitProgress * 1.1 * vw;
    }

    // Exited cards: hide off-screen
    if (rawDeckPos < 0) {
      const vw = typeof window !== "undefined" ? window.innerWidth : 1000;
      return -1.1 * vw;
    }

    // Cards in the deck: interpolate toward their target position
    let deckPos = rawDeckPos;

    // If the active card is exiting, cards behind it shift forward
    if (exitProgress > 0 && rawDeckPos > 0) {
      deckPos = rawDeckPos - exitProgress; // smoothly shift forward
    }

    return deckPos * STACK_GAP_X;
  });

  // --- Card Y (vertical: stack offset) ---
  const cardY = useTransform(scrollYProgress, (v) => {
    const { rawDeckPos, currentActive, exitProgress } = getDeckState(v);

    if (index === currentActive && exitProgress > 0) {
      return 0; // stays level while sliding left
    }
    if (rawDeckPos < 0) return 0;

    let deckPos = rawDeckPos;
    if (exitProgress > 0 && rawDeckPos > 0) {
      deckPos = rawDeckPos - exitProgress;
    }

    return deckPos * STACK_GAP_Y;
  });

  // --- Card Scale ---
  const cardScale = useTransform(scrollYProgress, (v) => {
    const { rawDeckPos, currentActive, exitProgress } = getDeckState(v);

    if (index === currentActive && exitProgress > 0) {
      return 1 - exitProgress * 0.05; // 1.0 → 0.95
    }
    if (rawDeckPos < 0) return 0.95;

    let deckPos = rawDeckPos;
    if (exitProgress > 0 && rawDeckPos > 0) {
      deckPos = rawDeckPos - exitProgress;
    }

    return Math.max(0.88, 1 - deckPos * STACK_SCALE_STEP);
  });

  // --- Card Opacity ---
  const cardOpacity = useTransform(scrollYProgress, (v) => {
    const { rawDeckPos, currentActive, exitProgress } = getDeckState(v);

    if (index === currentActive && exitProgress > 0) {
      return 1 - exitProgress; // fade out as it slides
    }
    if (rawDeckPos < 0) return 0;

    let deckPos = rawDeckPos;
    if (exitProgress > 0 && rawDeckPos > 0) {
      deckPos = rawDeckPos - exitProgress;
    }

    return Math.max(0.25, 1 - deckPos * STACK_OPACITY_STEP);
  });

  // --- Card Rotate (slight tilt during exit) ---
  const cardRotate = useTransform(scrollYProgress, (v) => {
    const { currentActive, exitProgress } = getDeckState(v);

    if (index === currentActive && exitProgress > 0) {
      return -3 * exitProgress; // 0 → -3deg
    }
    return 0;
  });

  // --- Content Y (scroll content within active card) ---
  const contentY = useTransform(scrollYProgress, (v) => {
    if (v < segStart || v >= segEnd) return 0;
    const localProgress = (v - segStart) / segLen;
    const contentPhaseProgress = Math.min(localProgress / EXIT_THRESHOLD, 1);

    const contentHeight = contentHeightsRef.current?.[index] || 0;
    const cardViewportHeight =
      typeof window !== "undefined" ? window.innerHeight - 96 : 600;
    const maxScroll = Math.max(0, contentHeight - cardViewportHeight);

    return -contentPhaseProgress * maxScroll;
  });

  // --- Z-index (reactive: top of deck = highest) ---
  const [zIndex, setZIndex] = useState(() => N - index);

  useMotionValueEvent(scrollYProgress, "change", (v) => {
    const { rawDeckPos, currentActive, exitProgress } = getDeckState(v);

    let z: number;
    if (rawDeckPos < 0) {
      z = 0; // exited
    } else if (index === currentActive && exitProgress > 0) {
      z = N + 1; // exiting card stays on top during animation
    } else {
      z = N - rawDeckPos;
    }
    if (z !== zIndex) setZIndex(z);
  });

  return (
    <StackCard
      section={section}
      index={index}
      totalSections={N}
      isActive={index === activeIndex}
      cardScale={cardScale}
      cardX={cardX}
      cardY={cardY}
      cardRotate={cardRotate}
      cardOpacity={cardOpacity}
      contentY={contentY}
      zIndex={zIndex}
      onContentHeight={onContentHeight}
    />
  );
}

export function CardStack({
  sections,
  heroContent,
  onProgressChange,
}: {
  sections: ScrollySectionModel[];
  heroContent?: ReactNode;
  onProgressChange?: (progress: number) => void;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const N = sections.length;
  const totalScrollVh = N * SCROLL_PER_SECTION * 100;

  const contentHeightsRef = useRef<number[]>(new Array(N).fill(0));

  const handleContentHeight = useCallback(
    (index: number, height: number) => {
      contentHeightsRef.current[index] = height;
    },
    []
  );

  const { scrollYProgress } = useScroll({
    target: trackRef,
    offset: ["start start", "end end"],
  });

  // Spring-smoothed scroll progress for fluid card transforms
  const smoothProgress = useSpring(scrollYProgress, {
    stiffness: 120,
    damping: 30,
    mass: 0.5,
  });

  const [activeIndex, setActiveIndex] = useState(0);

  useMotionValueEvent(scrollYProgress, "change", (latest) => {
    const newActive = Math.min(Math.floor(latest * N), N - 1);
    if (newActive >= 0 && newActive !== activeIndex) {
      setActiveIndex(newActive);
    }
  });

  useEffect(() => {
    if (onProgressChange && N > 1) {
      onProgressChange(activeIndex / (N - 1));
    }
  }, [activeIndex, N, onProgressChange]);

  const indicatorOpacity = useTransform(
    scrollYProgress,
    [0, 0.95, 1],
    [1, 1, 0]
  );

  return (
    <div>
      {heroContent}

      {/* Scroll track */}
      <div
        ref={trackRef}
        style={{ height: `${totalScrollVh}vh` }}
        className="relative"
      >
        {/* Sticky viewport — holds all cards, clips exit animation */}
        <div className="sticky top-0 h-screen overflow-hidden">
          {sections.map((section, i) => (
            <CardSlot
              key={section.id}
              section={section}
              index={i}
              totalSections={N}
              scrollYProgress={smoothProgress}
              activeIndex={activeIndex}
              contentHeightsRef={contentHeightsRef}
              onContentHeight={handleContentHeight}
            />
          ))}

          {/* Stack count indicator */}
          <motion.div
            className="absolute bottom-3 left-1/2 -translate-x-1/2 z-[100]"
            style={{ opacity: indicatorOpacity }}
          >
            <div className="flex items-center gap-2.5 rounded-full bg-black/60 backdrop-blur-xl px-4 py-2 border border-white/[0.08]">
              <span className="text-xs font-mono text-white/40">
                {activeIndex + 1} / {N}
              </span>
              <div className="flex gap-1">
                {sections.map((_, i) => (
                  <div
                    key={i}
                    className={cn(
                      "h-1 rounded-full transition-all duration-300",
                      i === activeIndex
                        ? "w-4 bg-white/50"
                        : i < activeIndex
                          ? "w-1 bg-white/20"
                          : "w-1.5 bg-white/10"
                    )}
                  />
                ))}
              </div>
            </div>
          </motion.div>
        </div>
      </div>

      {/* End of content */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
        className="mt-16 flex flex-col items-center gap-4 py-8"
      >
        <div className="flex items-center gap-3 w-full max-w-3xl mx-auto text-sm text-white/25 px-6">
          <div className="h-px flex-1 bg-gradient-to-r from-transparent to-white/[0.06]" />
          <span>End of paper</span>
          <div className="h-px flex-1 bg-gradient-to-l from-transparent to-white/[0.06]" />
        </div>

        <button
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          className="mt-2 text-xs text-white/30 hover:text-white/60 transition-colors"
        >
          Back to top
        </button>
      </motion.div>
    </div>
  );
}
