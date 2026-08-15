"use client";

import { useState } from "react";
import { LoaderCircle, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { normalizeMath } from "@/lib/mathMarkdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { MonoLabel } from "@/components/ui";
import { learn } from "@/lib/learn";

/** Ask the local assistant about the concept in front of you. Retrieval is
 *  scoped to this concept's bound chunks, so answers cite the same notes the
 *  question was written from. */
export default function ConceptAsk({
  conceptId,
  conceptName,
}: {
  conceptId: number;
  conceptName: string;
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function ask() {
    const trimmed = question.trim();
    if (!trimmed) return;
    setBusy(true);
    setError("");
    setAnswer("");
    try {
      const result = await learn.ask(conceptId, trimmed);
      setAnswer(result.answer);
    } catch {
      setError("The assistant is unavailable — check that LM Studio is running.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ borderTop: "1px solid var(--line)", padding: "16px 22px" }}>
      <MonoLabel size={9} dim>
        Ask about {conceptName}
      </MonoLabel>
      <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void ask();
          }}
          placeholder="Why does this work?"
          style={{
            flex: "1 1 260px",
            padding: "10px 13px",
            border: "1px solid var(--line2)",
            background: "var(--panel2)",
            color: "var(--text)",
            fontSize: 13,
            outline: "none",
          }}
        />
        <button
          type="button"
          onClick={() => void ask()}
          disabled={busy || !question.trim()}
          className="quiz-option"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 7,
            padding: "10px 14px",
            border: "1px solid var(--line2)",
            background: "transparent",
            color: "var(--dim)",
            fontFamily: "var(--font-jetbrains-mono), monospace",
            fontSize: 10,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            cursor: busy ? "not-allowed" : "pointer",
          }}
        >
          {busy ? (
            <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          Ask
        </button>
      </div>

      {error ? (
        <div className="reveal" style={{ marginTop: 12, fontSize: 12, color: "var(--warn)" }}>
          {error}
        </div>
      ) : null}

      {answer ? (
        <div
          className="reveal study-note"
          style={{
            marginTop: 14,
            padding: "14px 16px",
            border: "1px solid var(--line)",
            background: "var(--panel2)",
            fontSize: 13.5,
          }}
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[rehypeKatex]}
          >
            {normalizeMath(answer)}
          </ReactMarkdown>
        </div>
      ) : null}
    </div>
  );
}
