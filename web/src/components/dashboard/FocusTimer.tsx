"use client";

import { useEffect, useState } from "react";
import { Panel, MonoLabel, GlowButton } from "@/components/ui";

const SESSION = 25 * 60;

/** Local-only Pomodoro focus timer. No backend. */
export default function FocusTimer() {
  const [secs, setSecs] = useState(SESSION);
  const [running, setRunning] = useState(false);

  // One-shot decrement that reschedules itself as `secs` changes. Stops when
  // paused or at zero, so no setState runs in the effect body.
  useEffect(() => {
    if (!running || secs === 0) return;
    const id = window.setTimeout(() => setSecs((s) => s - 1), 1000);
    return () => window.clearTimeout(id);
  }, [running, secs]);

  const mm = String(Math.floor(secs / 60)).padStart(2, "0");
  const ss = String(secs % 60).padStart(2, "0");
  const pct = (100 - (secs / SESSION) * 100).toFixed(1);

  return (
    <Panel accent style={{ padding: 24 }}>
      <MonoLabel style={{ display: "block", marginBottom: 16 }}>FOCUS TIMER</MonoLabel>
      <div
        style={{
          fontFamily: "var(--font-jetbrains-mono), monospace",
          fontSize: 46,
          fontWeight: 300,
          letterSpacing: "0.04em",
        }}
      >
        {mm}:{ss}
      </div>
      <div style={{ height: 2, background: "var(--line)", margin: "18px 0" }}>
        <div style={{ height: 2, background: "var(--accent)", width: `${pct}%`, transition: "width 1s linear" }} />
      </div>
      <div style={{ display: "flex", gap: 10 }}>
        <GlowButton onClick={() => setRunning((r) => !r)} style={{ flex: 1 }}>
          {running ? "PAUSE" : "START"}
        </GlowButton>
        <GlowButton
          variant="ghost"
          onClick={() => {
            setRunning(false);
            setSecs(SESSION);
          }}
        >
          RESET
        </GlowButton>
      </div>
    </Panel>
  );
}
