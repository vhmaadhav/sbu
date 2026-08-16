"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowRight, BookOpen, Check, LoaderCircle, X } from "lucide-react";
import ConceptAsk from "@/components/learn/ConceptAsk";
import { GlowButton, MonoLabel, Panel, StatTile } from "@/components/ui";
import {
  learn,
  masteryFill,
  masteryLabel,
  type AttemptResult,
  type SessionItem,
  type SessionState,
} from "@/lib/learn";

// Clock reads live at module scope: a component body must stay pure, and these
// are only ever called from promise callbacks and event handlers.
const now = () => Date.now();
const elapsedSince = (start: number) => now() - start;

const KIND_LABEL: Record<string, string> = {
  diagnostic: "Diagnostic",
  study: "Today’s session",
  review: "Revision",
};

export default function SessionPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const sessionId = Number(params.id);

  const [item, setItem] = useState<SessionItem | null>(null);
  const [session, setSession] = useState<SessionState | null>(null);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const shownAt = useRef<number>(0);

  // Fetching only: every state write happens in a promise callback, so mounting
  // this page never triggers a cascading render.
  const loadNext = useCallback(
    () =>
      learn
        .next(sessionId)
        .then((next) => {
          if (!next.done) {
            setItem(next.item ?? null);
            shownAt.current = now();
            return;
          }
          setDone(true);
          setItem(null);
          if (next.session) setSession(next.session);
          else return learn.session(sessionId).then(setSession);
        })
        .catch(() =>
          setError("Couldn't load the next item. The local model may be unavailable."),
        )
        .finally(() => setLoading(false)),
    [sessionId],
  );

  function advance() {
    setLoading(true);
    setResult(null);
    setChosen(null);
    setError("");
    void loadNext();
  }

  useEffect(() => {
    if (!Number.isFinite(sessionId)) return;
    learn.session(sessionId).then(setSession).catch(() => {});
    loadNext();
  }, [sessionId, loadNext]);

  async function answer(index: number) {
    if (!item?.question || result) return;
    setChosen(index);
    try {
      const graded = await learn.attempt({
        question_id: item.question.id,
        chosen_index: index,
        session_id: sessionId,
        latency_ms: elapsedSince(shownAt.current),
      });
      setResult(graded);
    } catch {
      setError("Couldn't grade that answer.");
      setChosen(null);
    }
  }

  async function finishReading() {
    if (!item) return;
    await learn.markRead(sessionId, item.item_id).catch(() => {});
    advance();
  }

  const progress = item?.progress;
  const pct = progress && progress.total ? (progress.done / progress.total) * 100 : 0;

  return (
    <div className="axscreen" style={{ padding: "28px 30px 60px", maxWidth: 900 }}>
      {/* Header + progress */}
      <div style={{ marginBottom: 22 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            gap: 14,
            marginBottom: 12,
          }}
        >
          <MonoLabel size={10}>{KIND_LABEL[session?.kind ?? "study"] ?? "Session"}</MonoLabel>
          {progress ? (
            <MonoLabel size={9} dim>
              {progress.done} / {progress.total}
            </MonoLabel>
          ) : null}
        </div>
        <div style={{ height: 2, background: "var(--line)" }}>
          <div
            style={{
              height: "100%",
              width: `${pct}%`,
              background: "var(--accent)",
              transition: "width 0.4s cubic-bezier(0.2,0.8,0.2,1)",
            }}
          />
        </div>
      </div>

      {error ? (
        <Panel style={{ padding: "16px 20px", marginBottom: 20, borderColor: "var(--warn)" }}>
          <div style={{ fontSize: 13, marginBottom: 12 }}>{error}</div>
          <GlowButton variant="ghost" onClick={advance}>
            Try again
          </GlowButton>
        </Panel>
      ) : null}

      {loading && !item ? (
        <Panel style={{ padding: "48px", textAlign: "center" }}>
          <LoaderCircle
            className="h-5 w-5 animate-spin"
            style={{ margin: "0 auto 14px", color: "var(--accent)" }}
          />
          <MonoLabel size={10} dim>
            Writing your next question
          </MonoLabel>
        </Panel>
      ) : null}

      {/* ── Read a resource ──────────────────────────────────────────── */}
      {item?.kind === "read" ? (
        <Panel accent className="reveal">
          <div style={{ padding: "24px 22px 6px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 12 }}>
              <BookOpen className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} />
              <MonoLabel size={9}>Study this first</MonoLabel>
            </div>
            <h1 style={{ fontSize: 22, marginBottom: 8 }}>{item.concept.name}</h1>
            <p style={{ fontSize: 14, color: "var(--dim)", lineHeight: 1.65 }}>
              {item.concept.blurb}
            </p>
          </div>

          <div style={{ padding: "14px 22px 20px" }}>
            {item.sources && item.sources.length > 0 ? (
              item.sources.slice(0, 3).map((chunk) => (
                <div
                  key={chunk.chunk_id}
                  style={{
                    padding: "14px 16px",
                    marginBottom: 10,
                    border: "1px solid var(--line)",
                    background: "var(--panel2)",
                  }}
                >
                  <MonoLabel size={9} dim>
                    {chunk.source_label}
                  </MonoLabel>
                  <p
                    style={{
                      fontSize: 13.5,
                      color: "var(--text)",
                      lineHeight: 1.7,
                      marginTop: 9,
                    }}
                  >
                    {chunk.text.slice(0, 700)}
                    {chunk.text.length > 700 ? "…" : ""}
                  </p>
                </div>
              ))
            ) : (
              <div style={{ fontSize: 13, color: "var(--faint)", padding: "8px 0 4px" }}>
                No notes are bound to this concept yet. Upload material on this topic and it will
                show up here.
              </div>
            )}
          </div>

          <ConceptAsk conceptId={item.concept.id} conceptName={item.concept.name} />

          <div style={{ padding: "16px 22px", borderTop: "1px solid var(--line)" }}>
            <GlowButton onClick={() => void finishReading()}>
              Got it — quiz me
              <ArrowRight className="h-3.5 w-3.5" />
            </GlowButton>
          </div>
        </Panel>
      ) : null}

      {/* ── Answer a question ────────────────────────────────────────── */}
      {item?.kind === "quiz" && item.question ? (
        <Panel className="reveal">
          <div style={{ padding: "24px 22px 18px" }}>
            <MonoLabel size={9} dim>
              {item.question.concept_name}
            </MonoLabel>
            <h1 style={{ fontSize: 19, lineHeight: 1.5, margin: "12px 0 0" }}>
              {item.question.stem}
            </h1>
          </div>

          <div style={{ padding: "0 22px 20px", display: "flex", flexDirection: "column", gap: 9 }}>
            {item.question.options.map((option, index) => {
              const isChosen = chosen === index;
              const isAnswer = result ? result.answer_index === index : false;
              const wrongChoice = Boolean(result) && isChosen && !result?.correct;

              const border = isAnswer
                ? "var(--accent)"
                : wrongChoice
                  ? "var(--warn)"
                  : "var(--line2)";

              return (
                <button
                  key={index}
                  type="button"
                  disabled={Boolean(result)}
                  onClick={() => void answer(index)}
                  className={`quiz-option${wrongChoice ? " quiz-wrong" : ""}`}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    textAlign: "left",
                    padding: "14px 16px",
                    border: `1px solid ${border}`,
                    background: isAnswer
                      ? "color-mix(in srgb, var(--accent) 10%, transparent)"
                      : wrongChoice
                        ? "color-mix(in srgb, var(--warn) 16%, transparent)"
                        : "var(--panel2)",
                    color: "var(--text)",
                    fontSize: 14,
                    cursor: result ? "default" : "pointer",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "var(--font-jetbrains-mono), monospace",
                      fontSize: 10,
                      color: isAnswer ? "var(--accent)" : "var(--faint)",
                      width: 14,
                    }}
                  >
                    {String.fromCharCode(65 + index)}
                  </span>
                  <span style={{ flex: 1 }}>{option}</span>
                  {result && isAnswer ? (
                    <Check className="h-4 w-4" style={{ color: "var(--accent)" }} />
                  ) : null}
                  {wrongChoice ? (
                    <X className="h-4 w-4" style={{ color: "var(--warn)" }} />
                  ) : null}
                </button>
              );
            })}
          </div>

          {result ? (
            <div
              className="reveal"
              style={{ borderTop: "1px solid var(--line)", padding: "18px 22px" }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                <MonoLabel
                  size={10}
                  style={{ color: result.correct ? "var(--accent)" : "var(--warn)" }}
                >
                  {result.correct ? "Correct" : "Not quite"}
                </MonoLabel>
                <span
                  style={{
                    fontFamily: "var(--font-jetbrains-mono), monospace",
                    fontSize: 10,
                    color: "var(--dim)",
                    letterSpacing: "0.14em",
                  }}
                >
                  {masteryLabel(result.p_known)} · {Math.round(result.p_known * 100)}%
                </span>
              </div>

              {/* Live mastery bar for the concept just answered. */}
              <div style={{ height: 5, background: "var(--panel2)", marginBottom: 14 }}>
                <div
                  style={{
                    height: "100%",
                    width: `${Math.max(2, result.p_known * 100)}%`,
                    background: masteryFill(result.p_known),
                    transition: "width 0.5s cubic-bezier(0.2,0.8,0.2,1)",
                  }}
                />
              </div>

              {result.misconception ? (
                <div
                  style={{
                    fontSize: 12.5,
                    color: "var(--warn)",
                    marginBottom: 10,
                  }}
                >
                  That answer reflects a common misconception: {result.misconception}.
                </div>
              ) : null}

              {result.explanation ? (
                <p style={{ fontSize: 13.5, color: "var(--dim)", lineHeight: 1.7 }}>
                  {result.explanation}
                </p>
              ) : null}

              <div style={{ marginTop: 18 }}>
                <GlowButton onClick={advance}>
                  Next
                  <ArrowRight className="h-3.5 w-3.5" />
                </GlowButton>
              </div>
            </div>
          ) : null}

          {!result && item.question ? (
            <ConceptAsk conceptId={item.concept.id} conceptName={item.concept.name} />
          ) : null}
        </Panel>
      ) : null}

      {/* ── Finished ─────────────────────────────────────────────────── */}
      {done ? (
        <div className="reveal" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <Panel accent style={{ padding: "34px 30px" }}>
            <MonoLabel size={10}>Session complete</MonoLabel>
            <h1 style={{ fontSize: 24, margin: "12px 0 8px" }}>
              {session?.kind === "diagnostic"
                ? "Diagnostic finished — your gaps are ready"
                : "Nice work"}
            </h1>
            <p style={{ fontSize: 14, color: "var(--dim)", lineHeight: 1.65 }}>
              Mastery has been updated and your learning path recalculated.
            </p>
            <div style={{ display: "flex", gap: 10, marginTop: 22, flexWrap: "wrap" }}>
              <GlowButton href="/learn/gaps">See where you’re weak</GlowButton>
              <GlowButton variant="ghost" href="/learn/map">
                View concept map
              </GlowButton>
              <GlowButton variant="ghost" onClick={() => router.push("/learn")}>
                Back to goal
              </GlowButton>
            </div>
          </Panel>

          {session ? (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
                gap: 1,
                background: "var(--line)",
                border: "1px solid var(--line)",
              }}
            >
              <StatTile label="Answered" value={session.answered} />
              <StatTile label="Correct" value={session.correct} accent />
              <StatTile
                label="Accuracy"
                value={
                  session.answered
                    ? Math.round((session.correct / session.answered) * 100)
                    : 0
                }
                unit="%"
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
