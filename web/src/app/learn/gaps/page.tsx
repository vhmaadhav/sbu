"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Compass, Zap } from "lucide-react";
import LearnNav from "@/components/learn/LearnNav";
import WeakAreaBars from "@/components/charts/WeakAreaBars";
import ForgettingCurves from "@/components/charts/ForgettingCurves";
import { GlowButton, MonoLabel, Panel, SectionHeader, StatTile } from "@/components/ui";
import { learn, type Gap, type GoalSummary, type ReviewRow } from "@/lib/learn";

export default function GapsPage() {
  const router = useRouter();
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [summary, setSummary] = useState<GoalSummary | null>(null);
  const [review, setReview] = useState<{ queue: ReviewRow[]; threshold: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(
    () =>
      Promise.all([learn.gaps(), learn.review()])
        .then(([gapResult, reviewResult]) => {
          setGaps(gapResult.gaps);
          setSummary(gapResult.summary);
          setReview({ queue: reviewResult.queue, threshold: reviewResult.threshold });
        })
        .catch(() =>
          setError(
            "Set an exam goal first — the concept graph has to exist before gaps can be found.",
          ),
        )
        .finally(() => setLoading(false)),
    [],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function drill(gap: Gap) {
    setBusy(true);
    try {
      const result = await learn.startSession(gap.concept_id);
      router.push(`/learn/session/${result.session_id}`);
    } catch {
      setError("Couldn't start a drill for that concept.");
      setBusy(false);
    }
  }

  async function start(kind: "diagnostic" | "session") {
    setBusy(true);
    try {
      const result =
        kind === "diagnostic" ? await learn.startDiagnostic() : await learn.startSession();
      router.push(`/learn/session/${result.session_id}`);
    } catch {
      setError("Couldn't start that session.");
      setBusy(false);
    }
  }

  const foundations = gaps.filter((gap) => gap.missing_prerequisite);

  return (
    <div className="axscreen" style={{ padding: "28px 30px 60px", maxWidth: 1180 }}>
      <LearnNav />

      {error ? (
        <Panel style={{ padding: "16px 20px", borderColor: "var(--warn)" }}>
          <div style={{ fontSize: 13, color: "var(--text)", marginBottom: 12 }}>{error}</div>
          <GlowButton variant="ghost" href="/learn">
            Set an exam goal
          </GlowButton>
        </Panel>
      ) : null}

      {!error && !loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <Panel accent style={{ padding: "26px 30px" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                gap: 20,
                flexWrap: "wrap",
              }}
            >
              <div style={{ maxWidth: 560 }}>
                <MonoLabel size={10}>Step 02 — Knowledge gaps</MonoLabel>
                <h1 style={{ fontSize: 24, margin: "10px 0 8px" }}>
                  {gaps.length === 0
                    ? "No gaps detected"
                    : `You're weak on ${gaps.length} area${gaps.length === 1 ? "" : "s"}`}
                </h1>
                <p style={{ fontSize: 13.5, color: "var(--dim)", lineHeight: 1.6 }}>
                  {gaps.length === 0
                    ? "Run a diagnostic to measure where you actually stand."
                    : foundations.length > 0
                      ? `${foundations.length} of these are foundations holding up other concepts — they're listed first, and fixing them lifts everything above them.`
                      : "Ranked by how much each one is holding back. Click any area to drill it on its own."}
                </p>
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <GlowButton onClick={() => void start("session")} disabled={busy || gaps.length === 0}>
                  <Zap className="h-3.5 w-3.5" />
                  Improve these areas
                </GlowButton>
                <GlowButton variant="ghost" onClick={() => void start("diagnostic")} disabled={busy}>
                  <Compass className="h-3.5 w-3.5" />
                  Re-run diagnostic
                </GlowButton>
              </div>
            </div>
          </Panel>

          {summary ? (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
                gap: 1,
                background: "var(--line)",
                border: "1px solid var(--line)",
              }}
            >
              <StatTile label="Gaps" value={gaps.length} accent sub="below 60% mastery" />
              <StatTile
                label="Missing foundations"
                value={foundations.length}
                sub="blocking other concepts"
              />
              <StatTile label="Untested" value={summary.untested} sub="no attempts yet" />
              <StatTile label="Mastered" value={summary.mastered} sub={`of ${summary.concepts}`} />
            </div>
          ) : null}

          <Panel>
            <SectionHeader
              title="Weak areas — click one to drill it"
              action={<MonoLabel size={9} dim>Mastery · confidence</MonoLabel>}
            />
            <WeakAreaBars gaps={gaps} onSelect={(gap) => void drill(gap)} max={12} />
          </Panel>

          <Panel>
            <SectionHeader
              title="Forgetting risk"
              action={<MonoLabel size={9} dim>Next 14 days</MonoLabel>}
            />
            <div style={{ padding: "18px 16px 8px" }}>
              <ForgettingCurves
                rows={review?.queue ?? []}
                threshold={review?.threshold ?? 0.85}
              />
            </div>
          </Panel>
        </div>
      ) : null}
    </div>
  );
}
