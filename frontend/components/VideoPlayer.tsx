"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Props = {
  src: string;
  title?: string;
  className?: string;
  autoPlay?: boolean;
};

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function VideoPlayer({
  src,
  title = "Visualization video",
  className,
  autoPlay = false,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const [hadError, setHadError] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const progressPct = useMemo(() => {
    if (!duration) return 0;
    return Math.max(0, Math.min(100, (currentTime / duration) * 100));
  }, [currentTime, duration]);

  useEffect(() => {
    // Reset state when src changes.
    setIsPlaying(false);
    setIsReady(false);
    setHadError(false);
    setProgress(0);
    setCurrentTime(0);
    setDuration(0);
  }, [src]);

  function togglePlay() {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      void v.play();
    } else {
      v.pause();
    }
  }

  function onTimeUpdate() {
    const v = videoRef.current;
    if (!v) return;
    setCurrentTime(v.currentTime);
    setDuration(v.duration || 0);
    setProgress((v.currentTime / (v.duration || 1)) * 100);
  }

  function onSeek(e: React.MouseEvent<HTMLDivElement>) {
    const v = videoRef.current;
    if (!v || !duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = (e.clientX - rect.left) / rect.width;
    v.currentTime = Math.max(0, Math.min(duration, pct * duration));
  }

  if (!src) return null;

  return (
    <div
      className={[
        "relative overflow-hidden rounded-xl bg-black ring-1 ring-white/10",
        className ?? "",
      ].join(" ")}
    >
      <video
        ref={videoRef}
        src={src}
        className="block w-full"
        playsInline
        preload="metadata"
        autoPlay={autoPlay}
        muted={autoPlay}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onLoadedData={() => setIsReady(true)}
        onLoadedMetadata={() => {
          const v = videoRef.current;
          if (!v) return;
          setDuration(v.duration || 0);
        }}
        onTimeUpdate={onTimeUpdate}
        onError={() => setHadError(true)}
      />

      {/* Overlay button */}
      <button
        type="button"
        onClick={togglePlay}
        aria-label={isPlaying ? "Pause video" : "Play video"}
        className="absolute inset-0 grid place-items-center bg-black/25 transition hover:bg-black/35"
      >
        {!isPlaying && (
          <div className="grid h-14 w-14 place-items-center rounded-full bg-white/90 text-black shadow-[0_18px_45px_-25px_rgba(0,0,0,0.9)]">
            <svg
              viewBox="0 0 24 24"
              className="h-7 w-7 translate-x-[1px]"
              fill="currentColor"
              aria-hidden
            >
              <path d="M8 5v14l11-7z" />
            </svg>
          </div>
        )}
      </button>

      {/* Top-left label */}
      <div className="pointer-events-none absolute left-3 top-3 rounded-lg bg-black/45 px-2.5 py-1 text-[11px] text-white/80 ring-1 ring-white/10">
        {title}
      </div>

      {/* Bottom gradient + controls */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/70 to-transparent" />

      <div className="absolute inset-x-3 bottom-3">
        {hadError ? (
          <div className="rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-200 ring-1 ring-rose-400/20">
            Couldn’t load this video. The URL may be temporary or blocked.
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <div className="rounded-md bg-black/45 px-2 py-1 text-[11px] text-white/75 ring-1 ring-white/10">
              {formatTime(currentTime)} / {formatTime(duration)}
            </div>
            <div
              role="progressbar"
              aria-label="Video progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progressPct)}
              onClick={onSeek}
              className="group h-2 flex-1 cursor-pointer rounded-full bg-white/15 ring-1 ring-white/10"
            >
              <div
                className="h-full rounded-full bg-gradient-to-r from-blue-400 to-violet-400 transition-[width] duration-100"
                style={{ width: `${progressPct}%` }}
              />
              <div
                className="mt-1 text-[10px] text-white/45"
                style={{ display: "none" }}
              >
                {progress.toFixed(1)}%
              </div>
            </div>
            <div className="rounded-md bg-black/45 px-2 py-1 text-[11px] text-white/60 ring-1 ring-white/10">
              {isReady ? "HD" : "Loading…"}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
