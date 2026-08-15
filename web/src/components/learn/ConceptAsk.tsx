"use client";

import { useState } from "react";
import { LoaderCircle, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { normalizeMath } from "@/lib/mathMarkdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { MonoLabel } from "@/components/ui";
import { learn, type AskResponse } from "@/lib/learn";

/** Ask the local assistant about the concept in front of you. Retrieval expands
 *  through weak prerequisites and dependents, then exposes its evidence trace. */
export default function ConceptAsk({
  conceptId,
  conceptName,
}: {
  conceptId: number;
  conceptName: string;
}) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function ask() {
    const trimmed = question.trim();
    if (!trimmed) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await learn.ask(conceptId, trimmed));
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

      {result ? (
        <div className="reveal" style={{ marginTop: 14 }}>
          <div
            className="study-note"
            style={{
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
              {normalizeMath(result.answer)}
            </ReactMarkdown>
          </div>
          <details
            style={{
              border: "1px solid var(--line)",
              borderTop: 0,
              padding: "11px 14px",
              color: "var(--dim)",
            }}
          >
            <summary
              style={{
                cursor: "pointer",
                fontFamily: "var(--font-jetbrains-mono), monospace",
                fontSize: 10,
                letterSpacing: "0.16em",
                textTransform: "uppercase",
                color: "var(--accent)",
              }}
            >
              Why this answer?
            </summary>
            <div style={{ marginTop: 12, display: "grid", gap: 10, fontSize: 12 }}>
              <div>
                Retrieval mode: <strong>{result.retrieval_trace.mode.replaceAll("_", " ")}</strong>
                {result.retrieval_trace.seed_concept
                  ? ` · Seeded from ${result.retrieval_trace.seed_concept.name}`
                  : ""}
              </div>
              {result.retrieval_trace.graph_paths.length ? (
                <div>
                  <MonoLabel size={8} dim>Knowledge paths</MonoLabel>
                  <div style={{ marginTop: 5 }}>
                    {result.retrieval_trace.graph_paths.join(" · ")}
                  </div>
                </div>
              ) : null}
              <div>
                <MonoLabel size={8} dim>Selected evidence</MonoLabel>
                <div style={{ display: "grid", gap: 6, marginTop: 6 }}>
                  {result.retrieval_trace.evidence_reasons.map((evidence, index) => (
                    <div key={`${evidence.label}-${index}`}>
                      <span style={{ color: "var(--text)" }}>{evidence.label}</span>
                      {` — ${evidence.reason}`}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </details>
        </div>
      ) : null}
    </div>
  );
}
