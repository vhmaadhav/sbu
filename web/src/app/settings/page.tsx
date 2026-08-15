"use client";

import { useEffect, useState } from "react";
import { Panel, MonoLabel } from "@/components/ui";
import { useTheme } from "@/components/ThemeProvider";
import { ACCENTS } from "@/lib/prefs";
import { getJSON } from "@/lib/api";

interface Health {
  ok: boolean;
  llm: boolean;
  storage?: boolean;
  version?: string;
}

const MODELS: { label: string; value: string; desc: string }[] = [
  { label: "Speech to text", value: "MOONSHINE BASE", desc: "Lecture transcription" },
  { label: "Embeddings", value: "MINILM L6 V2", desc: "Semantic note search" },
  { label: "Text to speech", value: "KOKORO 82M", desc: "Audiobook generation" },
  { label: "Local storage", value: "SQLITE + LANCEDB", desc: "Stored in ./data" },
];

function Row({ label, desc, control }: { label: string; desc: string; control: React.ReactNode }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "15px 22px", borderBottom: "1px solid var(--line)", gap: 20 }}>
      <div>
        <div style={{ fontSize: 14 }}>{label}</div>
        <div style={{ fontSize: 12, color: "var(--dim)", marginTop: 3 }}>{desc}</div>
      </div>
      {control}
    </div>
  );
}

function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => onChange(!on)}
      style={{
        width: 38,
        height: 20,
        border: `1px solid ${on ? "var(--accent)" : "var(--line2)"}`,
        borderRadius: 20,
        position: "relative",
        background: "transparent",
        cursor: "pointer",
        flexShrink: 0,
      }}
    >
      <span
        style={{
          position: "absolute",
          top: 2,
          left: on ? 20 : 2,
          width: 14,
          height: 14,
          borderRadius: "50%",
          background: on ? "var(--accent)" : "var(--dim)",
          transition: "left 0.25s, background 0.25s",
          boxShadow: on ? "0 0 10px -2px var(--accent)" : "none",
        }}
      />
    </button>
  );
}

function Group({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <Panel>
      <div style={{ padding: "14px 22px", borderBottom: "1px solid var(--line)" }}>
        <MonoLabel>{name}</MonoLabel>
      </div>
      {children}
    </Panel>
  );
}

export default function SettingsPage() {
  const { theme, accent, grid, dyslexic, setTheme, setAccent, setGrid, setDyslexic } = useTheme();
  const [health, setHealth] = useState<Health | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getJSON<Health>("/api/health")
      .then((result) => {
        setHealth(result);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  const apiValue = failed ? "OFFLINE" : health ? `ONLINE${health.version ? ` · V${health.version}` : ""}` : "CONNECTING";
  const apiColor = failed ? "#f87171" : health ? "var(--accent)" : "#fbbf24";
  const llmValue = health?.llm ? "CONNECTED" : "OFFLINE";
  const llmColor = health?.llm ? "var(--accent)" : "#fbbf24";

  return (
    <section className="axscreen" style={{ padding: 32, maxWidth: 720, display: "flex", flexDirection: "column", gap: 26 }}>
      <div>
        <MonoLabel size={11} spacing="0.24em" style={{ color: "var(--accent)", display: "block", marginBottom: 8 }}>
          SETTINGS
        </MonoLabel>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 500 }}>System &amp; appearance</h1>
        <p style={{ margin: "8px 0 0", color: "var(--dim)", fontSize: 14 }}>
          Local services power your workspace. Model and storage configuration lives in the project .env file.
        </p>
      </div>

      {/* Appearance — functional */}
      <Group name="APPEARANCE">
        <Row
          label="Interface theme"
          desc="Dark or light mode"
          control={
            <div style={{ display: "flex", gap: 8 }}>
              {(["dark", "light"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTheme(t)}
                  style={{
                    fontFamily: "var(--font-jetbrains-mono), monospace",
                    fontSize: 11,
                    letterSpacing: "0.12em",
                    padding: "6px 12px",
                    border: `1px solid ${theme === t ? "var(--accent)" : "var(--line2)"}`,
                    color: theme === t ? "var(--accent)" : "var(--dim)",
                    background: "transparent",
                    textTransform: "uppercase",
                  }}
                >
                  {t}
                </button>
              ))}
            </div>
          }
        />
        <Row
          label="Accent color"
          desc="Highlight and glow color"
          control={
            <div style={{ display: "flex", gap: 10 }}>
              {ACCENTS.map((a) => (
                <button
                  key={a.value}
                  onClick={() => setAccent(a.value)}
                  aria-label={a.label}
                  title={a.label}
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: "50%",
                    background: a.value,
                    border: accent === a.value ? "2px solid var(--text)" : "2px solid transparent",
                    boxShadow: accent === a.value ? `0 0 12px -2px ${a.value}` : "none",
                    cursor: "pointer",
                  }}
                />
              ))}
            </div>
          }
        />
        <Row
          label="Grid overlay"
          desc="Background reference grid"
          control={<Toggle on={grid} onChange={setGrid} label="Toggle grid overlay" />}
        />
      </Group>

      {/* Reading — accessibility */}
      <Group name="READING">
        <Row
          label="Dyslexia-friendly reading"
          desc="OpenDyslexic typeface with wider letter and word spacing, taller lines, and a narrower column for notes"
          control={
            <Toggle
              on={dyslexic}
              onChange={setDyslexic}
              label="Toggle dyslexia-friendly reading"
            />
          }
        />
      </Group>

      {/* System status — real */}
      <Group name="SYSTEM">
        <Row
          label="Study Buddy API"
          desc={failed ? "Unreachable — start the backend (uvicorn server:app)." : "Local processing runtime"}
          control={
            <MonoLabel size={11} spacing="0.12em" style={{ color: apiColor, border: `1px solid ${apiColor}`, padding: "6px 12px", whiteSpace: "nowrap" }}>
              {apiValue}
            </MonoLabel>
          }
        />
        <Row
          label="LM Studio"
          desc="Local language model server"
          control={
            <MonoLabel size={11} spacing="0.12em" style={{ color: llmColor, border: `1px solid ${llmColor}`, padding: "6px 12px", whiteSpace: "nowrap" }}>
              {llmValue}
            </MonoLabel>
          }
        />
      </Group>

      {/* Models — reference */}
      <Group name="LOCAL MODELS">
        {MODELS.map((m) => (
          <Row
            key={m.label}
            label={m.label}
            desc={m.desc}
            control={
              <MonoLabel size={11} spacing="0.12em" style={{ color: "var(--accent)", border: "1px solid var(--line2)", padding: "6px 12px", whiteSpace: "nowrap" }}>
                {m.value}
              </MonoLabel>
            }
          />
        ))}
      </Group>

      <Panel accent style={{ padding: 22 }}>
        <MonoLabel style={{ display: "block", marginBottom: 10, color: "var(--accent)" }}>PRIVATE BY DEFAULT</MonoLabel>
        <p style={{ margin: 0, fontSize: 13, color: "var(--dim)", lineHeight: 1.6 }}>
          Notes, recordings, model calls, and search indexes stay on your local machine.
        </p>
      </Panel>
    </section>
  );
}
