"use client";

import { useRef, useState } from "react";
import { Bold, Heading2, Italic, Link2, List, Save, X } from "lucide-react";
import NoteMarkdown from "@/components/NoteMarkdown";
import { NoteContext } from "@/lib/noteLinks";

interface NoteEditorProps {
  initialMarkdown: string;
  ctx: NoteContext;
  saving: boolean;
  onSave: (markdown: string) => void;
  onCancel: () => void;
}

export default function NoteEditor({ initialMarkdown, ctx, saving, onSave, onCancel }: NoteEditorProps) {
  const [text, setText] = useState(initialMarkdown);
  const areaRef = useRef<HTMLTextAreaElement>(null);

  function surround(before: string, after: string, placeholder: string) {
    const area = areaRef.current;
    if (!area) return;
    const { selectionStart: start, selectionEnd: end } = area;
    const selected = text.slice(start, end) || placeholder;
    const next = text.slice(0, start) + before + selected + after + text.slice(end);
    setText(next);
    requestAnimationFrame(() => {
      area.focus();
      area.selectionStart = start + before.length;
      area.selectionEnd = start + before.length + selected.length;
    });
  }

  function prefixLine(prefix: string) {
    const area = areaRef.current;
    if (!area) return;
    const { selectionStart: start } = area;
    const lineStart = text.lastIndexOf("\n", start - 1) + 1;
    const next = text.slice(0, lineStart) + prefix + text.slice(lineStart);
    setText(next);
    requestAnimationFrame(() => {
      area.focus();
      area.selectionStart = area.selectionEnd = start + prefix.length;
    });
  }

  const toolClass = "rounded-lg border border-line p-2 text-muted transition hover:border-brand/40 hover:text-brand";

  return (
    <div className="not-prose mx-auto max-w-5xl">
      <div className="mb-3 flex flex-wrap items-center gap-1">
        <button type="button" onClick={() => surround("**", "**", "bold text")} title="Bold" aria-label="Bold" className={toolClass}>
          <Bold className="h-4 w-4" />
        </button>
        <button type="button" onClick={() => surround("*", "*", "italic text")} title="Italic" aria-label="Italic" className={toolClass}>
          <Italic className="h-4 w-4" />
        </button>
        <button type="button" onClick={() => prefixLine("## ")} title="Heading" aria-label="Heading" className={toolClass}>
          <Heading2 className="h-4 w-4" />
        </button>
        <button type="button" onClick={() => prefixLine("- ")} title="Bullet list" aria-label="Bullet list" className={toolClass}>
          <List className="h-4 w-4" />
        </button>
        <button type="button" onClick={() => surround("[", "](https://)", "link text")} title="Link" aria-label="Link" className={toolClass}>
          <Link2 className="h-4 w-4" />
        </button>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => onSave(text)}
            disabled={saving || !text.trim()}
            className="button-primary disabled:opacity-60"
          >
            <Save className="h-4 w-4" />
            {saving ? "Saving…" : "Save"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="button-secondary disabled:opacity-60"
          >
            <X className="h-4 w-4" />
            Cancel
          </button>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <textarea
          ref={areaRef}
          value={text}
          onChange={(event) => setText(event.target.value)}
          spellCheck
          className="min-h-[420px] w-full resize-y rounded-xl border border-line bg-panel p-4 font-mono text-sm leading-relaxed outline-none focus:border-brand/40"
        />
        <div className="min-h-[420px] overflow-auto rounded-xl border border-line bg-page/35 p-4">
          <article className="study-note">
            <NoteMarkdown markdown={text} ctx={ctx} onSeek={() => {}} />
          </article>
        </div>
      </div>
    </div>
  );
}
