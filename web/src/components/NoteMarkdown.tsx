"use client";

import { memo, useMemo } from "react";
import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { API } from "@/lib/api";
import { cleanStudyMarkdown } from "@/lib/markdown";
import { linkifySources, makeSourceAnchor, NoteContext } from "@/lib/noteLinks";
import remarkHighlights from "@/lib/remarkHighlights";
import MermaidDiagram from "@/components/MermaidDiagram";

interface NoteMarkdownProps {
  markdown: string;
  ctx: NoteContext;
  onSeek: (seconds: number) => void;
}

// Plugin lists and the renderers that don't close over props are hoisted so
// they keep a stable identity across renders — react-markdown treats a new
// array/object as new configuration and re-parses the whole document.
const REMARK_PLUGINS = [remarkGfm, remarkMath, remarkHighlights];
const REHYPE_PLUGINS = [rehypeKatex];

// Preserve our internal jump-to-source scheme; react-markdown would
// otherwise strip the unknown protocol and blank the href.
const urlTransform = (url: string) =>
  url.startsWith("studysrc:") ? url : defaultUrlTransform(url);

const staticComponents = {
  mark: ({ children }) => <mark className="study-note-highlight">{children}</mark>,
  img: ({ src, alt }: { src?: string | Blob; alt?: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={typeof src === "string" && src.startsWith("/api/") ? `${API}${src}` : src}
      alt={alt ?? "Figure"}
      className="max-h-[560px] rounded-xl object-contain"
    />
  ),
  code: ({ className, children, ...props }) => {
    const language = /language-(\w+)/.exec(className ?? "")?.[1];
    const source = String(children).replace(/\n$/, "");
    return language === "mermaid" ? (
      <MermaidDiagram source={source} />
    ) : (
      <code className={className} {...props}>{children}</code>
    );
  },
  table: ({ children }) => <div className="study-note-table"><table>{children}</table></div>,
} satisfies Components;

/** Canonical study-note renderer: figure images, tables, and source links. */
function NoteMarkdown({ markdown, ctx, onSeek }: NoteMarkdownProps) {
  // Study notes routinely run to hundreds of KB. Preparing the source and
  // rebuilding the component map on every render made unrelated state changes
  // on the notes page (typing in the filter, a toast, a poll) re-parse the
  // whole document and reconcile its entire tree.
  const prepared = useMemo(
    () => linkifySources(cleanStudyMarkdown(markdown), ctx.kind),
    [markdown, ctx.kind],
  );

  const components = useMemo<Components>(
    () => ({ ...staticComponents, a: makeSourceAnchor(ctx, onSeek) }),
    [ctx, onSeek],
  );

  return (
    <ReactMarkdown
      remarkPlugins={REMARK_PLUGINS}
      rehypePlugins={REHYPE_PLUGINS}
      urlTransform={urlTransform}
      components={components}
    >
      {prepared}
    </ReactMarkdown>
  );
}

// Callers pass a memoised `ctx`/`onSeek`, so this skips the parse entirely
// when only unrelated page state changed.
export default memo(NoteMarkdown);
