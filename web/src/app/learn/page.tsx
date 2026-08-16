"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Compass, Eye, Link2, LoaderCircle, RotateCcw, Target } from "lucide-react";
import LearnNav from "@/components/learn/LearnNav";
import MasteryCurve from "@/components/charts/MasteryCurve";
import { GlowButton, MonoLabel, Panel, SectionHeader, StatTile } from "@/components/ui";
import {
  learn,
  type GoalResponse,
  type HistoryPoint,
  type LearningEvidence,
} from "@/lib/learn";
import { getJSON, type Subject } from "@/lib/api";

function sourceHost(sourceUri: string): string {
  try {
    return new URL(sourceUri).hostname.replace(/^www\./, "");
  } catch {
    return "browser source";
  }
}

export default function LearnPage() {
  const router = useRouter();
  const [state, setState] = useState<GoalResponse | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [evidence, setEvidence] = useState<LearningEvidence[]>([]);
  // The map is built from your own notes, so your folders are the only
  // suggestions that can actually produce one.
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [next, recentEvidence] = await Promise.all([learn.goal(), learn.evidence(6)]);
      setState(next);
      setEvidence(recentEvidence.evidence);
      if (next.goal?.status === "ready") {
        const points = await learn.history();
        setHistory(points.points);
      }
    } catch {
      setError("Couldn't reach the Axiom Trace API.");
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    getJSON<Subject[]>("/api/subjects")
      .then((subjects) => setSuggestions(subjects.map((subject) => subject.name).slice(0, 6)))
      .catch(() => {});
  }, []);

  // While the graph is being generated, poll until it settles either way.
  useEffect(() => {
    if (state?.goal?.status !== "building") return;
    const timer = setInterval(refresh, 2000);
    return () => clearInterval(timer);
  }, [state?.goal?.status, refresh]);

  async function createGoal(goalName: string) {
    const trimmed = goalName.trim();
    if (!trimmed) return;
    setBusy(true);
    setError("");
    try {
      await learn.createGoal(trimmed);
      setName("");
      await refresh();
    } catch {
      setError(
        "Couldn't start the concept graph. Check that LM Studio is running with the configured model.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function begin(kind: "diagnostic" | "session") {
    setBusy(true);
    setError("");
    try {
      const result =
        kind === "diagnostic" ? await learn.startDiagnostic() : await learn.startSession();
      router.push(`/learn/session/${result.session_id}`);
    } catch {
      setError("Couldn't start that session.");
      setBusy(false);
    }
  }

  async function reset() {
    setBusy(true);
    await learn.deleteGoal().catch(() => {});
    setHistory([]);
    await refresh();
    setBusy(false);
  }

  async function linkEvidence() {
    setBusy(true);
    setError("");
    try {
      await learn.rebindEvidence();
      await refresh();
    } catch {
      setError("Couldn't link the latest browser evidence to this concept graph.");
    } finally {
      setBusy(false);
    }
  }

  const goal = state?.goal ?? null;
  const summary = state?.summary ?? null;

  return (
    <div className="axscreen" style={{ padding: "28px 30px 60px", maxWidth: 1180 }}>
      <LearnNav />

      {error ? (
        <Panel style={{ padding: "14px 20px", marginBottom: 20, borderColor: "var(--warn)" }}>
          <span style={{ fontSize: 13, color: "var(--text)" }}>{error}</span>
        </Panel>
      ) : null}

      {/* ── No goal yet: set one ─────────────────────────────────────── */}
      {!goal ? (
        <Panel accent style={{ padding: "40px 36px" }}>
          <MonoLabel size={10}>Step 01 — Set your goal</MonoLabel>
          <h1 style={{ fontSize: 27, margin: "16px 0 10px", letterSpacing: "0.01em" }}>
            What are you studying for?
          </h1>
          <p style={{ fontSize: 14, color: "var(--dim)", maxWidth: 620, lineHeight: 1.65 }}>
            Axiom Trace turns your notes and focused browser reading into a prerequisite graph,
            then tracks what you know with Bayesian mastery updates. Every explanation stays
            grounded in evidence you can inspect. Name a folder to map just that folder.
          </p>

          <div style={{ display: "flex", gap: 10, marginTop: 26, flexWrap: "wrap" }}>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void createGoal(name);
              }}
              placeholder="e.g. a folder or exam name your notes cover"
              style={{
                flex: "1 1 320px",
                padding: "12px 15px",
                border: "1px solid var(--line2)",
                background: "var(--panel2)",
                color: "var(--text)",
                fontSize: 14,
                outline: "none",
              }}
            />
            <GlowButton onClick={() => void createGoal(name)} disabled={busy || !name.trim()}>
              <Target className="h-3.5 w-3.5" />
              Build concept map
            </GlowButton>
          </div>

          <div
            style={{
              display: suggestions.length ? "flex" : "none",
              gap: 8,
              marginTop: 16,
              flexWrap: "wrap",
            }}
          >
            <MonoLabel size={9} dim>
              Your folders
            </MonoLabel>
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => setName(suggestion)}
                style={{
                  fontSize: 11,
                  color: "var(--dim)",
                  border: "1px solid var(--line)",
                  padding: "4px 9px",
                  cursor: "pointer",
                  background: "transparent",
                  transition: "border-color 0.2s, color 0.2s",
                }}
                className="quiz-option"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </Panel>
      ) : null}

      {/* ── Building ─────────────────────────────────────────────────── */}
      {goal?.status === "building" ? (
        <Panel style={{ padding: "44px 36px", textAlign: "center" }}>
          <LoaderCircle
            className="h-6 w-6 animate-spin"
            style={{ margin: "0 auto 18px", color: "var(--accent)" }}
          />
          <div style={{ fontSize: 17, marginBottom: 8 }}>Reading your notes for “{goal.name}”…</div>
          <MonoLabel size={10} dim>
            The local model is extracting concepts from your notes. This takes a minute.
          </MonoLabel>
        </Panel>
      ) : null}

      {/* ── Failed ───────────────────────────────────────────────────── */}
      {goal?.status === "error" ? (
        <Panel style={{ padding: "36px", borderColor: "var(--warn)" }}>
          <MonoLabel size={10} style={{ color: "var(--warn)" }}>
            Graph build failed
          </MonoLabel>
          <p style={{ fontSize: 14, color: "var(--dim)", margin: "14px 0 20px", lineHeight: 1.6 }}>
            {goal.error || "The model did not return a usable concept graph."}
          </p>
          <div style={{ display: "flex", gap: 10 }}>
            <GlowButton onClick={() => void createGoal(goal.name)} disabled={busy}>
              <RotateCcw className="h-3.5 w-3.5" />
              Try again
            </GlowButton>
            <GlowButton variant="ghost" onClick={() => void reset()} disabled={busy}>
              Start over
            </GlowButton>
          </div>
        </Panel>
      ) : null}

      {/* ── Ready: the hub ───────────────────────────────────────────── */}
      {goal?.status === "ready" && summary ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <Panel accent style={{ padding: "28px 30px" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                gap: 20,
                flexWrap: "wrap",
              }}
            >
              <div>
                <MonoLabel size={10}>Exam goal</MonoLabel>
                <h1 style={{ fontSize: 25, margin: "10px 0 6px" }}>{goal.name}</h1>
                <span style={{ fontSize: 13, color: "var(--dim)" }}>
                  {summary.concepts} concepts · {summary.mastered} mastered · {summary.weak} weak
                </span>
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <GlowButton onClick={() => void begin("diagnostic")} disabled={busy}>
                  <Compass className="h-3.5 w-3.5" />
                  Find knowledge gaps
                </GlowButton>
                <GlowButton variant="ghost" onClick={() => void begin("session")} disabled={busy}>
                  Start today’s session
                </GlowButton>
              </div>
            </div>
          </Panel>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
              gap: 1,
              background: "var(--line)",
              border: "1px solid var(--line)",
            }}
          >
            <StatTile
              label="Average mastery"
              value={`${Math.round(summary.average * 100)}`}
              unit="%"
              accent
            />
            <StatTile label="Mastered" value={summary.mastered} sub="in the revision queue" />
            <StatTile label="Weak" value={summary.weak} sub="below 60% mastery" />
            <StatTile label="Untested" value={summary.untested} sub="no attempts yet" />
          </div>

          <Panel>
            <SectionHeader
              title="Learning evidence"
              action={
                <GlowButton
                  variant="ghost"
                  onClick={() => void linkEvidence()}
                  disabled={busy}
                  style={{ padding: "6px 10px", fontSize: 9 }}
                >
                  <Link2 className="h-3.5 w-3.5" />
                  Link new evidence
                </GlowButton>
              }
            />
            {evidence.length ? (
              <div>
                {evidence.map((row) => (
                  <div
                    key={row.event_id}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "minmax(0, 1fr) auto",
                      gap: 18,
                      alignItems: "center",
                      padding: "13px 22px",
                      borderBottom: "1px solid var(--line)",
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: 13,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {row.processed_title || row.title}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 4 }}>
                        {sourceHost(row.source_uri)} · {Math.max(1, Math.round(row.dwell_ms / 1000))}s focused
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <MonoLabel size={8} style={{ color: row.status === "done" ? "var(--accent)" : "var(--dim)" }}>
                        {row.status}
                      </MonoLabel>
                      <div style={{ fontSize: 10, color: "var(--faint)", marginTop: 4 }}>
                        {row.linked_concepts} concept links
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ padding: "24px 22px", color: "var(--dim)", fontSize: 13 }}>
                <Eye className="h-4 w-4" style={{ display: "inline", marginRight: 8 }} />
                Focus on a page for 30 seconds with the Axiom Trace extension to add evidence.
              </div>
            )}
          </Panel>

          <Panel>
            <SectionHeader
              title="Mastery over time"
              action={<MonoLabel size={9} dim>BKT posterior</MonoLabel>}
            />
            <div style={{ padding: "18px 16px 8px" }}>
              <MasteryCurve points={history} />
            </div>
          </Panel>

          {state?.sessions && state.sessions.length > 0 ? (
            <Panel>
              <SectionHeader title="Recent sessions" />
              <div>
                {state.sessions.map((session) => (
                  <div
                    key={session.id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "13px 22px",
                      borderBottom: "1px solid var(--line)",
                      gap: 14,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <MonoLabel size={9} style={{ color: "var(--accent)" }}>
                        {session.kind}
                      </MonoLabel>
                      <span style={{ fontSize: 12.5, color: "var(--dim)" }}>
                        {new Date(session.created_at * 1000).toLocaleString(undefined, {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                      <span
                        style={{
                          fontFamily: "var(--font-jetbrains-mono), monospace",
                          fontSize: 11,
                          color: "var(--dim)",
                        }}
                      >
                        {session.correct ?? 0}/{session.answered ?? 0}
                      </span>
                      {session.status === "active" ? (
                        <GlowButton
                          variant="ghost"
                          href={`/learn/session/${session.id}`}
                          style={{ padding: "6px 11px", fontSize: 10 }}
                        >
                          Resume
                        </GlowButton>
                      ) : (
                        <MonoLabel size={9} dim>
                          Complete
                        </MonoLabel>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          ) : null}

          <div>
            <GlowButton variant="ghost" onClick={() => void reset()} disabled={busy}>
              Change exam goal
            </GlowButton>
          </div>
        </div>
      ) : null}
    </div>
  );
}
