"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import LearnNav from "@/components/learn/LearnNav";
import ConceptMap from "@/components/charts/ConceptMap";
import { GlowButton, MonoLabel, Panel, SectionHeader } from "@/components/ui";
import { learn, masteryFill, masteryLabel, type ConceptNode, type Graph } from "@/lib/learn";

export default function ConceptMapPage() {
  const router = useRouter();
  const [graph, setGraph] = useState<Graph | null>(null);
  const [selected, setSelected] = useState<ConceptNode | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(
    () =>
      learn
        .graph()
        .then(setGraph)
        .catch(() => setError("Set an exam goal first — there's no concept graph to draw yet.")),
    [],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function drill(node: ConceptNode) {
    setBusy(true);
    try {
      const result = await learn.startSession(node.id);
      router.push(`/learn/session/${result.session_id}`);
    } catch {
      setError("Couldn't start a drill for that concept.");
      setBusy(false);
    }
  }

  return (
    <div className="axscreen" style={{ padding: "28px 30px 60px", maxWidth: 1280 }}>
      <LearnNav />

      {error ? (
        <Panel style={{ padding: "16px 20px", borderColor: "var(--warn)" }}>
          <div style={{ fontSize: 13, marginBottom: 12 }}>{error}</div>
          <GlowButton variant="ghost" href="/learn">
            Set an exam goal
          </GlowButton>
        </Panel>
      ) : null}

      {graph ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <Panel>
            <SectionHeader
              title="Concept map"
              action={
                <MonoLabel size={9} dim>
                  {graph.nodes.length} concepts · {graph.edges.length} prerequisites
                </MonoLabel>
              }
            />
            <ConceptMap graph={graph} onSelect={setSelected} height={520} />
            <div
              style={{
                display: "flex",
                gap: 20,
                padding: "14px 22px",
                borderTop: "1px solid var(--line)",
                flexWrap: "wrap",
              }}
            >
              {[
                { label: "Weak", fill: masteryFill(0.2), ring: "var(--warn)" },
                { label: "Learning", fill: masteryFill(0.6), ring: "var(--accent)" },
                { label: "Mastered", fill: masteryFill(0.95), ring: "var(--accent)" },
              ].map((key) => (
                <div key={key.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span
                    style={{
                      width: 13,
                      height: 13,
                      borderRadius: "50%",
                      background: key.fill,
                      border: `1px solid ${key.ring}`,
                    }}
                  />
                  <MonoLabel size={9} dim>
                    {key.label}
                  </MonoLabel>
                </div>
              ))}
              <MonoLabel size={9} dim>
                Node size = concepts unlocked · dashed ring = in revision
              </MonoLabel>
            </div>
          </Panel>

          {selected ? (
            <Panel accent className="reveal" style={{ padding: "24px 26px" }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 18,
                  flexWrap: "wrap",
                }}
              >
                <div style={{ maxWidth: 620 }}>
                  <MonoLabel size={9}>
                    {masteryLabel(selected.p_known)} · TIER {selected.tier}
                  </MonoLabel>
                  <h2 style={{ fontSize: 21, margin: "10px 0 8px" }}>{selected.name}</h2>
                  <p style={{ fontSize: 13.5, color: "var(--dim)", lineHeight: 1.65 }}>
                    {selected.blurb}
                  </p>
                  <div style={{ fontSize: 12, color: "var(--faint)", marginTop: 10 }}>
                    {Math.round(selected.p_known * 100)}% mastery · {selected.attempts} attempt
                    {selected.attempts === 1 ? "" : "s"} · unlocks {selected.downstream} concept
                    {selected.downstream === 1 ? "" : "s"}
                  </div>
                </div>
                <GlowButton onClick={() => void drill(selected)} disabled={busy}>
                  Drill this concept
                </GlowButton>
              </div>
            </Panel>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
