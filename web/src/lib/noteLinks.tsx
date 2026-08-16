"use client";

import type { Components } from "react-markdown";
import { Link2 } from "lucide-react";
import { API } from "@/lib/api";

// Turn the source markers the notes already contain — `[@ mm:ss]` in lecture
// transcripts, `[p. N]` in documents — into compact hover hyperlinks that jump
// to the exact spot in the source. We only linkify markers we can actually
// resolve for this note's kind, so a rendered link never goes nowhere.

export interface NoteContext {
  itemId: number;
  kind: string;
  title: string;
  subjectName: string | null;
}

const TS = /\[@\s*(?:(\d+):)?(\d+):(\d{2})\]/g;
const PAGE = /\[p\.\s*(\d+)\]/g;
const SCHEME = "studysrc:";

function tsSeconds(h: string | undefined, m: string, s: string): number {
  return (h ? parseInt(h, 10) : 0) * 3600 + parseInt(m, 10) * 60 + parseInt(s, 10);
}

function fmtTs(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const mm = h ? String(m).padStart(2, "0") : String(m);
  return `${h ? `${h}:` : ""}${mm}:${String(s).padStart(2, "0")}`;
}

/** Rewrite resolvable markers into markdown links using the studysrc: scheme. */
export function linkifySources(markdown: string, kind: string): string {
  if (kind === "video") {
    return markdown.replace(TS, (_all, h, m, s) => {
      const seconds = tsSeconds(h, m, s);
      return `[@ ${fmtTs(seconds)}](${SCHEME}ts:${seconds})`;
    });
  }
  if (kind === "pdf" || kind === "image") {
    return markdown.replace(PAGE, (_all, n) => `[p. ${n}](${SCHEME}page:${n})`);
  }
  return markdown;
}

function SourceLink({
  kind, value, ctx, onSeek,
}: {
  kind: "ts" | "page";
  value: number;
  ctx: NoteContext;
  onSeek: (seconds: number) => void;
}) {
  const location = kind === "ts" ? `@ ${fmtTs(value)}` : `page ${value}`;
  const label = kind === "ts" ? fmtTs(value) : `p.${value}`;
  const tooltip = [ctx.title, ctx.subjectName, location].filter(Boolean).join(" · ");

  const open = () => {
    if (kind === "ts") {
      onSeek(value);
    } else {
      const hash = ctx.kind === "pdf" ? `#page=${value}` : "";
      window.open(`${API}/api/items/${ctx.itemId}/file${hash}`, "_blank", "noopener");
    }
  };

  return (
    <span className="group relative inline-flex align-baseline">
      <button
        type="button"
        onClick={open}
        className="not-prose mx-0.5 inline-flex items-center gap-0.5 rounded-md bg-brand-soft px-1.5 py-0.5 align-baseline text-[0.72em] font-medium text-brand transition hover:bg-brand hover:text-white"
        aria-label={`Open source: ${tooltip}`}
      >
        <Link2 className="h-3 w-3" />
        {label}
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-1 hidden -translate-x-1/2 whitespace-nowrap rounded-lg border border-line bg-panel px-2.5 py-1.5 text-xs text-current shadow-[var(--shadow-float)] group-hover:block"
      >
        {tooltip}
      </span>
    </span>
  );
}

/** ReactMarkdown `a` renderer that upgrades studysrc: links into hover chips. */
export function makeSourceAnchor(
  ctx: NoteContext,
  onSeek: (seconds: number) => void,
): Components["a"] {
  return function Anchor({ href, children, ...rest }) {
    if (typeof href === "string" && href.startsWith(SCHEME)) {
      const [kind, raw] = href.slice(SCHEME.length).split(":");
      const value = Number(raw);
      if ((kind === "ts" || kind === "page") && Number.isFinite(value)) {
        return <SourceLink kind={kind} value={value} ctx={ctx} onSeek={onSeek} />;
      }
    }
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
        {children}
      </a>
    );
  };
}
