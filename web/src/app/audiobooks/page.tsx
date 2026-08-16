"use client";

import { useCallback, useEffect, useState } from "react";
import { CircleAlert, Headphones, Loader2 } from "lucide-react";
import { Panel, MonoLabel, GlowButton, SectionHeader } from "@/components/ui";
import { API, Audiobook, getJSON, NotePreview, postJSON, timeAgo } from "@/lib/api";

interface Job {
  id: number;
  name: string;
  status: "processing" | "done" | "error";
  error: string | null;
  file: string | null;
  created_at: number;
}

export default function AudiobooksPage() {
  const [books, setBooks] = useState<Audiobook[]>([]);
  const [notes, setNotes] = useState<NotePreview[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [picked, setPicked] = useState<number[]>([]);

  const refresh = useCallback(() => {
    getJSON<Audiobook[]>("/api/audiobooks").then(setBooks).catch(() => {});
    getJSON<NotePreview[]>("/api/notes?limit=50").then(setNotes).catch(() => {});
    getJSON<Job[]>("/api/audiobooks/jobs").then(setJobs).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  const busy = jobs.some((j) => j.status === "processing");
  const pendingJobs = jobs.filter((j) => j.status !== "done");

  async function generate() {
    if (!picked.length) return;
    const name = notes.find((n) => n.id === picked[0])?.title ?? "audiobook";
    await postJSON("/api/audiobooks", { note_ids: picked, name });
    setPicked([]);
    refresh();
  }

  return (
    <section className="axscreen" style={{ padding: 32, display: "flex", flexDirection: "column", gap: 24, maxWidth: 900 }}>
      <div>
        <MonoLabel size={11} spacing="0.24em" style={{ color: "var(--accent)", display: "block", marginBottom: 8 }}>
          AUDIO
        </MonoLabel>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 500 }}>Audiobooks</h1>
        <p style={{ margin: "8px 0 0", color: "var(--dim)", fontSize: 14 }}>
          Turn your notes into narrated audio with Kokoro.
        </p>
      </div>

      {/* Generate */}
      <Panel>
        <SectionHeader title="Generate from notes" />
        <div style={{ padding: 18 }}>
          {notes.length === 0 ? (
            <p style={{ margin: 0, fontSize: 14, color: "var(--dim)" }}>No notes yet — process some material first.</p>
          ) : (
            <>
              <div style={{ maxHeight: 224, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8 }}>
                {notes.map((n) => {
                  const on = picked.includes(n.id);
                  return (
                    <label key={n.id} style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 14, cursor: "pointer" }}>
                      <button
                        type="button"
                        onClick={() => setPicked((p) => (on ? p.filter((x) => x !== n.id) : [...p, n.id]))}
                        aria-label={on ? "Deselect note" : "Select note"}
                        style={{
                          width: 16,
                          height: 16,
                          border: `1px solid ${on ? "var(--accent)" : "var(--line2)"}`,
                          background: on ? "var(--accent)" : "transparent",
                          flexShrink: 0,
                          display: "grid",
                          placeItems: "center",
                          color: "var(--bg)",
                          fontSize: 11,
                        }}
                      >
                        {on ? "✓" : ""}
                      </button>
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n.title ?? "Untitled"}</span>
                      {n.subject && (
                        <MonoLabel size={9} spacing="0.12em" dim>
                          {n.subject.toUpperCase()}
                        </MonoLabel>
                      )}
                    </label>
                  );
                })}
              </div>
              <GlowButton onClick={generate} disabled={!picked.length} style={{ marginTop: 16 }}>
                <Headphones className="h-4 w-4" /> GENERATE AUDIOBOOK
              </GlowButton>
            </>
          )}
        </div>
      </Panel>

      {/* Queue */}
      {pendingJobs.length > 0 && (
        <div>
          <MonoLabel style={{ display: "block", marginBottom: 12 }}>GENERATION QUEUE</MonoLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {pendingJobs.map((j) => (
              <Panel key={j.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px" }}>
                {j.status === "processing" ? (
                  <Loader2 className="h-4 w-4 animate-spin" style={{ color: "var(--accent)" }} />
                ) : (
                  <CircleAlert className="h-4 w-4" style={{ color: "#f87171" }} />
                )}
                <span style={{ flex: 1, fontSize: 14, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{j.name}</span>
                <span style={{ fontSize: 12, color: "var(--dim)" }}>
                  {j.status === "processing" ? "Synthesizing… this takes a few minutes" : j.error}
                </span>
              </Panel>
            ))}
          </div>
        </div>
      )}

      {/* Library */}
      <div>
        <MonoLabel style={{ display: "block", marginBottom: 12 }}>YOUR AUDIOBOOKS</MonoLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {books.length === 0 && !busy && <p style={{ margin: 0, fontSize: 14, color: "var(--dim)" }}>Nothing here yet.</p>}
          {books.map((b) => (
            <Panel key={b.name} style={{ padding: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ width: 40, height: 40, display: "grid", placeItems: "center", border: "1px solid var(--line2)", color: "var(--accent)" }}>
                  <Headphones className="h-5 w-5" />
                </span>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {b.name.replace(/_\d+\.wav$/, "").replaceAll("_", " ")}
                  </div>
                  <MonoLabel size={9} spacing="0.12em" dim style={{ marginTop: 3, display: "block" }}>
                    {b.size_mb} MB · {timeAgo(b.created_at).toUpperCase()}
                  </MonoLabel>
                </div>
              </div>
              <audio controls preload="none" style={{ marginTop: 12, width: "100%" }} src={`${API}/api/audiobooks/${b.name}`} />
            </Panel>
          ))}
        </div>
      </div>
    </section>
  );
}
