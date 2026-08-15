"use client";

import { useEffect, useRef } from "react";
import { X } from "lucide-react";

interface VideoModalProps {
  src: string;
  timestamp: number;
  label: string;
  onClose: () => void;
}

export default function VideoModal({ src, timestamp, label, onClose }: VideoModalProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Seeking straight to the timestamp is flaky on large lecture files served over
  // the LAN: on `loadedmetadata` the media often isn't seekable yet, so a single
  // `currentTime = …` is dropped and the video plays from the start. Keep nudging
  // it to the target on every readiness event until it actually lands there.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    let done = false;

    const seek = () => {
      if (done) return;
      if (Math.abs(video.currentTime - timestamp) < 0.5) {
        done = true;
        return;
      }
      const seekable = video.seekable;
      const reachable = seekable.length === 0 || timestamp <= seekable.end(seekable.length - 1);
      if (reachable) {
        try {
          video.currentTime = timestamp;
        } catch {
          /* not seekable yet — a later event will retry */
        }
      }
      void video.play().catch(() => {});
    };

    video.addEventListener("loadedmetadata", seek);
    video.addEventListener("loadeddata", seek);
    video.addEventListener("canplay", seek);
    video.addEventListener("seeked", seek);
    return () => {
      video.removeEventListener("loadedmetadata", seek);
      video.removeEventListener("loadeddata", seek);
      video.removeEventListener("canplay", seek);
      video.removeEventListener("seeked", seek);
    };
  }, [src, timestamp]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/72 p-3 backdrop-blur-sm sm:p-5"
      onClick={onClose}
    >
      <div
        className="w-full max-w-4xl rounded-[24px] border border-line bg-panel p-4 shadow-[var(--shadow-float)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="truncate text-sm font-semibold">
            {label} · from {Math.floor(timestamp / 60)}:{String(Math.floor(timestamp % 60)).padStart(2, "0")}
          </p>
          <button
            onClick={onClose}
            aria-label="Close video"
            className="rounded-lg p-1.5 text-muted transition hover:bg-panel-muted"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <video
          ref={videoRef}
          key={`${src}#${timestamp}`}
          controls
          autoPlay
          preload="auto"
          className="max-h-[70vh] w-full rounded-xl bg-black"
          // The #t= media fragment asks the browser to open at the timestamp
          // natively; the effect above is the fallback when that is ignored.
          src={`${src}#t=${timestamp}`}
        />
      </div>
    </div>
  );
}
