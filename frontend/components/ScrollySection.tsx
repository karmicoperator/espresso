"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, useMotionValue, useMotionTemplate } from "framer-motion";
import { VideoPlayer } from "@/components/VideoPlayer";
import { MarkdownContent } from "@/components/MarkdownContent";
import { cn } from "@/lib/utils";

export type ScrollySectionModel = {
  id: string;
  title: string;
  content: string;
  level?: 1 | 2 | 3;
  equations?: string[];
  videoUrl?: string;
};

/**
 * Merge content and equations into a single markdown string.
 * Equations are intelligently integrated - either inline or as display blocks.
 */
function mergeContentWithEquations(content: string, equations?: string[]): string {
  if (!equations || equations.length === 0) {
    return content;
  }

  let result = content;
  const equationsToAppend: string[] = [];

  for (const eq of equations) {
    const normalizedEq = eq.replace(/\s+/g, '');
    const normalizedContent = result.replace(/\s+/g, '');
    
    const alreadyPresent = 
      normalizedContent.includes(normalizedEq) ||
      normalizedContent.includes(`$${normalizedEq}$`) ||
      normalizedContent.includes(`$$${normalizedEq}$$`);
    
    if (!alreadyPresent) {
      equationsToAppend.push(eq);
    }
  }

  if (equationsToAppend.length > 0) {
    const equationBlocks = equationsToAppend.map(eq => {
      const trimmed = eq.trim();
      if (trimmed.startsWith('$$') && trimmed.endsWith('$$')) {
        return trimmed;
      }
      if (trimmed.startsWith('$') && trimmed.endsWith('$') && !trimmed.startsWith('$$')) {
        return `$${trimmed}$`;
      }
      return `$$${trimmed}$$`;
    }).join('\n\n');
    
    result = `${result}\n\n${equationBlocks}`;
  }

  return result;
}

export function ScrollySection({
  section,
  index,
  onActiveChange,
}: {
  section: ScrollySectionModel;
  index?: number;
  onActiveChange?: (sectionId: string, isActive: boolean) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  const [hasEntered, setHasEntered] = useState(false);
  const [isActive, setIsActive] = useState(false);
  const activeRef = useRef(false);

  // Mouse position for spotlight effect
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  function handleMouseMove({
    currentTarget,
    clientX,
    clientY,
  }: React.MouseEvent<HTMLElement>) {
    const { left, top } = currentTarget.getBoundingClientRect();
    mouseX.set(clientX - left);
    mouseY.set(clientY - top);
  }

  const headingClass = useMemo(() => {
    const level = section.level ?? 1;
    if (level === 1) return "text-2xl sm:text-3xl";
    if (level === 2) return "text-xl sm:text-2xl";
    return "text-lg sm:text-xl";
  }, [section.level]);

  const unifiedContent = useMemo(
    () => mergeContentWithEquations(section.content, section.equations),
    [section.content, section.equations]
  );

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry) return;

        if (entry.isIntersecting) setHasEntered(true);
        const nextActive =
          entry.isIntersecting && entry.intersectionRatio >= 0.55;

        if (activeRef.current !== nextActive) {
          activeRef.current = nextActive;
          setIsActive(nextActive);
          onActiveChange?.(section.id, nextActive);
        }
      },
      {
        threshold: [0.15, 0.35, 0.55, 0.75],
        rootMargin: "0px 0px -35% 0px",
      }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [onActiveChange, section.id]);

  return (
    <motion.section
      ref={ref}
      data-section-id={section.id}
      initial={{ opacity: 0, y: 30 }}
      animate={{
        opacity: hasEntered ? 1 : 0,
        y: hasEntered ? 0 : 30,
      }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      onMouseMove={handleMouseMove}
      className={cn(
        "group relative rounded-2xl ring-1 backdrop-blur-sm overflow-hidden scroll-mt-24",
        isActive
          ? "bg-white/[0.08] ring-white/25 shadow-lg shadow-blue-500/5"
          : "bg-white/[0.04] ring-white/10",
        "transition-all duration-500 ease-out"
      )}
    >
      {/* Spotlight gradient overlay */}
      <motion.div
        className="pointer-events-none absolute -inset-px rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"
        style={{
          background: useMotionTemplate`
            radial-gradient(
              500px circle at ${mouseX}px ${mouseY}px,
              ${isActive ? "rgba(59, 130, 246, 0.12)" : "rgba(120, 119, 198, 0.08)"},
              transparent 40%
            )
          `,
        }}
      />

      {/* Active indicator bar */}
      <motion.div
        className={cn(
          "absolute left-0 top-0 bottom-0 w-1 rounded-l-2xl",
          "bg-gradient-to-b from-blue-500 to-violet-500"
        )}
        initial={{ scaleY: 0 }}
        animate={{ scaleY: isActive ? 1 : 0 }}
        transition={{ duration: 0.3 }}
        style={{ transformOrigin: "top" }}
      />

      <div className="relative px-6 py-6 sm:px-8 sm:py-8">
        <div className="flex items-start gap-4 sm:gap-5">
          {/* Section number badge */}
          <motion.div
            whileHover={{ scale: 1.1 }}
            className={cn(
              "mt-1 grid h-10 w-10 shrink-0 place-items-center rounded-xl transition-all duration-300",
              isActive
                ? "bg-gradient-to-br from-blue-500/20 to-violet-500/20 ring-1 ring-blue-400/30"
                : "bg-white/[0.06] ring-1 ring-white/10"
            )}
          >
            <span
              className={cn(
                "text-sm font-semibold transition-colors duration-300",
                isActive ? "text-blue-300" : "text-white/60"
              )}
            >
              {(index ?? 0) + 1}
            </span>
          </motion.div>

          <div className="min-w-0 flex-1">
            {/* Section title */}
            <motion.h2
              className={cn(
                "text-balance font-semibold tracking-tight transition-colors duration-300",
                headingClass,
                isActive ? "text-white" : "text-white/90"
              )}
              layout
            >
              {section.title}
            </motion.h2>

            {/* Section content */}
            <div className="mt-4 text-sm leading-7 text-white/65 sm:text-base sm:leading-8">
              <MarkdownContent content={unifiedContent} />
            </div>

            {/* Video player with enhanced styling */}
            {section.videoUrl && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2, duration: 0.4 }}
                className="mt-6"
              >
                <div className="rounded-xl overflow-hidden ring-1 ring-white/10 bg-black/30">
                  <VideoPlayer src={section.videoUrl} title="Visualization" />
                </div>
              </motion.div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom gradient for depth */}
      <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
    </motion.section>
  );
}
