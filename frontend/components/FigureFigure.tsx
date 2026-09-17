"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";
import type { FigurePlate } from "@/lib/types";

/**
 * A figure reproduced from the paper.
 *
 * Everything else on the page is redrawn from checked numbers. This is not: it is the
 * authors' own image, shown because a chest film or a mechanism diagram carries something
 * a bar chart cannot. So it is labelled as theirs, carries their caption word for word,
 * and sits under a different heading style than the charts, because the reader should
 * never be unsure which marks on the page are ours and which are the paper's.
 */
export function FigureFigure({ figure, paperId }: { figure: FigurePlate; paperId: string }) {
  const ref = useRef<HTMLElement>(null);
  const [on, setOn] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (on) return;
    const check = () => {
      const el = ref.current;
      if (!el) return;
      if (el.getBoundingClientRect().top < window.innerHeight * 0.9) setOn(true);
    };
    check();
    window.addEventListener("scroll", check, { passive: true });
    // Same deadline as the charts: a reveal that never fires must not hide the content.
    const deadline = window.setTimeout(() => setOn(true), 2500);
    return () => {
      window.clearTimeout(deadline);
      window.removeEventListener("scroll", check);
    };
  }, [on]);

  // A figure that will not load is removed rather than left as a broken frame with a
  // caption under it, which would describe something the reader cannot see.
  if (failed) return null;

  const src = `${API_BASE}/api/figure/${encodeURIComponent(paperId)}/${encodeURIComponent(figure.file)}`;
  const ratio = figure.width && figure.height ? figure.width / figure.height : undefined;

  return (
    <figure ref={ref} className={`chart ${on ? "on" : ""} my-8`}>
      <div className="overflow-hidden rounded-2xl border border-white/[0.08] bg-white/[0.04] backdrop-blur-xl">
        <div className="flex items-center justify-between px-7 pt-6 pb-4">
          <h3 className="text-[14px] font-medium text-[#e8e8e8]">
            {figure.label || "Figure"}
            <span className="ml-2 text-[12px] font-normal text-white/30">from the paper</span>
          </h3>
          {figure.kind && figure.kind !== "figure" && (
            <span className="rounded-full border border-white/[0.10] px-2.5 py-0.5 text-[11px] text-white/40">
              {figure.kind}
            </span>
          )}
        </div>

        {/* White plate: radiographs and histology are authored on white, and inverting or
            dimming them changes what the reader sees.

            The plate is bounded, not the image. Sizing the plate to its content while the
            image sized itself to the plate was circular: an image that had not loaded had
            no width, so the plate collapsed to its own padding, so the image never grew
            large enough to enter the viewport and start loading. The width cap is derived
            from the aspect ratio instead, which bounds the height without either box
            having to wait on the other. */}
        {/* No reveal class on the image. A chart's marks can animate in because the card
            around them already says what they are, but this is a photograph: if the
            transition stalls, and in a throttled or background tab it does, the reader
            gets a white rectangle where the radiograph should be. Content does not wait
            on an animation. */}
        {/* The image is capped at three quarters of the viewport whatever its metadata says:
            a figure whose width and height the source did not report used to render at
            its native size, and a tall multi-panel plate then ran over two screens. */}
        <div className="flex justify-center px-3">
          <div
            className="max-w-full rounded-[10px] bg-[#f4f4f4] p-3"
            style={ratio ? { maxWidth: `calc(74vh * ${ratio})` } : undefined}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={src}
              alt={figure.caption ? `${figure.label}. ${figure.caption}` : figure.label}
              width={figure.width ?? undefined}
              height={figure.height ?? undefined}
              onError={() => setFailed(true)}
              className="block h-auto max-h-[74vh] w-auto max-w-full rounded-[6px]"
              style={ratio ? { aspectRatio: String(ratio) } : undefined}
            />
          </div>
        </div>

        <div className="px-7 pt-5 pb-5">
          {figure.why && (
            <p className="mb-3 text-[12px] leading-relaxed text-[#7fb5a6]">{figure.why}</p>
          )}
          {figure.caption && (
            <p className="text-[12.5px] leading-[1.6] text-white/50">{figure.caption}</p>
          )}
        </div>
      </div>
    </figure>
  );
}
