"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import LearnNav from "@/components/learn/LearnNav";
import SlopeChart from "@/components/charts/SlopeChart";
import MisconceptionBars from "@/components/charts/MisconceptionBars";
import WeakAreaBars from "@/components/charts/WeakAreaBars";
import ForgettingCurves from "@/components/charts/ForgettingCurves";
import MasteryCurve from "@/components/charts/MasteryCurve";
import { GlowButton, MonoLabel, Panel, SectionHeader, StatTile } from "@/components/ui";
import { learn, type Gap, type HistoryPoint, type WeeklyReport } from "@/lib/learn";

export default function ReportPage() {
  const router = useRouter();
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [error, setError] = useState("");

  const refresh = useCallback(
    () =>
      Promise.all([learn.report(), learn.history()])
        .then(([weekly, points]) => {
          setReport(weekly);
          setHistory(points.points);
        })
        .catch(() => setError("Set an exam goal first — there's nothing to report on yet.")),
    [],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function drill(gap: Gap) {
    const result = await learn.startSession(gap.concept_id).catch(() => null);
    if (result) router.push(`/learn/session/${result.session_id}`);
  }

  return (
    <div className="axscreen" style={{ padding: "28px 30px 60px", maxWidth: 1180 }}>
      <LearnNav />

      {error ? (
        <Panel style={{ padding: "16px 20px", borderColor: "var(--warn)" }}>
          <div style={{ fontSize: 13, marginBottom: 12 }}>{error}</div>
          <GlowButton variant="ghost" href="/learn">
            Set an exam goal
          </GlowButton>
        </Panel>
      ) : null}

      {report ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <Panel accent style={{ padding: "26px 30px" }}>
            <MonoLabel size={10}>Last 7 days</MonoLabel>
            <h1 style={{ fontSize: 24, margin: "10px 0 8px" }}>
              {report.summary.improved > 0
                ? `${report.summary.improved} concept${report.summary.improved === 1 ? "" : "s"} moved forward`
                : "No movement this week"}
            </h1>
            <p style={{ fontSize: 13.5, color: "var(--dim)", lineHeight: 1.6 }}>
              {report.summary.sessions} session{report.summary.sessions === 1 ? "" : "s"} ·{" "}
              {report.summary.answered} question{report.summary.answered === 1 ? "" : "s"} answered ·{" "}
              {Math.round(report.summary.accuracy * 100)}% accuracy
            </p>
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
              value={Math.round(report.summary.average * 100)}
              unit="%"
              accent
            />
            <StatTile label="Mastered" value={report.summary.mastered} sub={`of ${report.summary.concepts}`} />
            <StatTile label="Remaining gaps" value={report.summary.weak} />
            <StatTile label="Due for review" value={report.review.filter((r) => r.due).length} />
          </div>

          <Panel>
            <SectionHeader
              title="What moved this week"
              action={<MonoLabel size={9} dim>Before → after</MonoLabel>}
            />
            <div style={{ padding: "18px 16px 10px" }}>
              <SlopeChart deltas={report.deltas} />
            </div>
          </Panel>

          <Panel>
            <SectionHeader title="Mastery over time" />
            <div style={{ padding: "18px 16px 8px" }}>
              <MasteryCurve points={history} />
            </div>
          </Panel>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
              gap: 22,
            }}
          >
            <Panel>
              <SectionHeader
                title="Misconceptions"
                action={<MonoLabel size={9} dim>Repeated errors</MonoLabel>}
              />
              <MisconceptionBars rows={report.misconceptions} />
            </Panel>

            <Panel>
              <SectionHeader
                title="Remaining gaps"
                action={<MonoLabel size={9} dim>Click to drill</MonoLabel>}
              />
              <WeakAreaBars gaps={report.gaps} onSelect={(gap) => void drill(gap)} max={6} />
            </Panel>
          </div>

          <Panel>
            <SectionHeader
              title="Revision schedule"
              action={<MonoLabel size={9} dim>Forgetting risk</MonoLabel>}
            />
            <div style={{ padding: "18px 16px 8px" }}>
              <ForgettingCurves rows={report.review} />
            </div>
            {report.review.length > 0 ? (
              <div style={{ borderTop: "1px solid var(--line)" }}>
                {report.review.slice(0, 6).map((row) => (
                  <div
                    key={row.concept_id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "12px 22px",
                      borderBottom: "1px solid var(--line)",
                      gap: 14,
                    }}
                  >
                    <span style={{ fontSize: 13.5, color: "var(--text)" }}>{row.name}</span>
                    <span
                      style={{
                        fontFamily: "var(--font-jetbrains-mono), monospace",
                        fontSize: 10,
                        letterSpacing: "0.14em",
                        color: row.due ? "var(--warn)" : "var(--dim)",
                      }}
                    >
                      {row.due
                        ? "DUE NOW"
                        : `IN ${row.days_until_due < 1 ? "<1" : Math.round(row.days_until_due)}D`}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </Panel>
        </div>
      ) : null}
    </div>
  );
}
