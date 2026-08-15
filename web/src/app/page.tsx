"use client";

import { useEffect, useState } from "react";
import { getJSON, type Stats, type Task, type Deck } from "@/lib/api";
import { Panel, MonoLabel, StatTile, SectionHeader, GlowButton } from "@/components/ui";
import FocusTimer from "@/components/dashboard/FocusTimer";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function todayLabel(): string {
  return new Date()
    .toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })
    .toUpperCase();
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [decks, setDecks] = useState<Deck[]>([]);

  useEffect(() => {
    getJSON<Stats>("/api/stats").then(setStats).catch(() => {});
    getJSON<Task[]>("/api/tasks").then(setTasks).catch(() => {});
    getJSON<Deck[]>("/api/flashcards").then(setDecks).catch(() => {});
  }, []);

  const openTasks = tasks.filter((t) => !t.done);
  const totalCards = decks.reduce((sum, d) => sum + d.card_count, 0);
  const diskPct =
    stats && stats.disk_total_gb ? Math.round((stats.disk_used_gb / stats.disk_total_gb) * 100) : 0;

  const subline = stats
    ? `${openTasks.length} open ${openTasks.length === 1 ? "task" : "tasks"} · ${totalCards} cards across ${decks.length} ${decks.length === 1 ? "deck" : "decks"}.`
    : "Loading your workspace…";

  return (
    <section
      className="axscreen"
      style={{ padding: "32px 32px 40px", display: "flex", flexDirection: "column", gap: 28, maxWidth: 1180 }}
    >
      {/* Greeting */}
      <div>
        <MonoLabel size={11} spacing="0.24em" style={{ color: "var(--accent)", display: "block", marginBottom: 8 }}>
          {todayLabel()}
        </MonoLabel>
        <h1 style={{ margin: 0, fontSize: 30, fontWeight: 500, letterSpacing: "-0.01em" }}>{greeting()}.</h1>
        <p style={{ margin: "8px 0 0", color: "var(--dim)", fontSize: 14 }}>{subline}</p>
      </div>

      {/* Stat tiles */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 1,
          background: "var(--line)",
          border: "1px solid var(--line)",
        }}
      >
        <StatTile label="Notes" value={stats?.notes ?? "—"} unit="notes" sub={`${stats?.chunks ?? 0} chunks indexed`} />
        <StatTile label="Library" value={stats?.files ?? "—"} unit="files" sub="ingested items" />
        <StatTile label="Cards" value={stats?.flashcards ?? "—"} unit="cards" sub={`${decks.length} decks`} accent />
        <StatTile
          label="Storage"
          value={stats?.disk_used_gb ?? "—"}
          unit={stats ? `/ ${Math.round(stats.disk_total_gb)} GB` : ""}
          sub={stats ? `${diskPct}% of disk used` : ""}
        />
      </div>

      {/* Plan + side column */}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.5fr) minmax(0, 1fr)", gap: 24, alignItems: "start" }}>
        <Panel>
          <SectionHeader
            title="Today's Plan"
            action={
              <MonoLabel size={10} spacing="0.14em" style={{ color: "var(--accent)" }}>
                <a href="/tasks">ALL TASKS →</a>
              </MonoLabel>
            }
          />
          <div style={{ display: "flex", flexDirection: "column" }}>
            {tasks.length === 0 ? (
              <div style={{ padding: "22px", fontSize: 14, color: "var(--dim)" }}>
                No tasks yet. Add one on the Tasks screen.
              </div>
            ) : (
              tasks.slice(0, 6).map((t) => (
                <div
                  key={t.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                    padding: "15px 22px",
                    borderBottom: "1px solid var(--line)",
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      border: `1px solid ${t.done ? "var(--accent)" : "var(--line2)"}`,
                      background: t.done ? "var(--accent)" : "transparent",
                      flexShrink: 0,
                    }}
                  />
                  <span
                    style={{
                      flex: 1,
                      fontSize: 14,
                      color: t.done ? "var(--faint)" : "var(--text)",
                      textDecoration: t.done ? "line-through" : "none",
                    }}
                  >
                    {t.label}
                  </span>
                  {t.due ? (
                    <MonoLabel size={10} spacing="0.1em" dim>
                      {t.due}
                    </MonoLabel>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </Panel>

        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <FocusTimer />
          <Panel style={{ padding: 22 }}>
            <MonoLabel style={{ display: "block", marginBottom: 14 }}>CARDS DUE</MonoLabel>
            <div style={{ fontSize: 14, color: "var(--dim)", lineHeight: 1.6 }}>
              {decks.length === 0 ? (
                "No decks yet. Generate flashcards from your notes."
              ) : (
                <>
                  {totalCards} cards across{" "}
                  {decks.slice(0, 2).map((d, i) => (
                    <span key={d.id}>
                      {i > 0 ? " and " : ""}
                      <span style={{ color: "var(--text)" }}>{d.title}</span>
                    </span>
                  ))}
                  {decks.length > 2 ? ` and ${decks.length - 2} more` : ""}.
                </>
              )}
            </div>
            <GlowButton href="/flashcards" variant="ghost" style={{ marginTop: 16, width: "100%" }}>
              BEGIN REVIEW →
            </GlowButton>
          </Panel>
        </div>
      </div>
    </section>
  );
}
