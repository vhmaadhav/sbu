"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, CircleAlert, Loader2, PenLine, Send, Upload } from "lucide-react";
import { Panel, MonoLabel, GlowButton } from "@/components/ui";
import { API, getJSON, HwLine, HwPage, HwPageDetail, HwStatus, postJSON, timeAgo } from "@/lib/api";

function LineEditor({ line, onSaved }: { line: HwLine; onSaved: () => void }) {
  const [text, setText] = useState(line.corrected_text ?? line.pred_text);
  const [saved, setSaved] = useState(false);
  const corrected = line.corrected_text !== null;

  async function save() {
    const trimmed = text.trim();
    if (!corrected && trimmed === line.pred_text.trim()) return;
    await fetch(`${API}/api/handwriting/lines/${line.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ corrected_text: trimmed }),
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
    onSaved();
  }

  return (
    <Panel style={{ padding: 12 }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`${API}${line.crop_url}`}
        alt={`Handwritten line ${line.line_index + 1}`}
        style={{ maxHeight: 96, width: "100%", border: "1px solid var(--line)", background: "var(--panel2)", objectFit: "contain" }}
      />
      <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8 }}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onBlur={save}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          placeholder="(empty — type what this line says)"
          style={{ flex: 1, background: "var(--panel2)", border: "1px solid var(--line)", color: "var(--text)", padding: "8px 12px", fontSize: 14, outline: "none" }}
        />
        {saved ? (
          <Check className="h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} />
        ) : corrected ? (
          <MonoLabel size={9} spacing="0.12em" style={{ color: "var(--accent)", border: "1px solid var(--line2)", padding: "3px 7px", flexShrink: 0 }}>
            CORRECTED
          </MonoLabel>
        ) : null}
      </div>
    </Panel>
  );
}

export default function HandwritingPage() {
  const [pages, setPages] = useState<HwPage[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<HwPageDetail | null>(null);
  const [status, setStatus] = useState<HwStatus | null>(null);
  const [sentToNotes, setSentToNotes] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    getJSON<HwPage[]>("/api/handwriting/pages").then(setPages).catch(() => {});
    getJSON<HwStatus>("/api/handwriting/status").then(setStatus).catch(() => {});
  }, []);

  const loadDetail = useCallback((id: number) => {
    getJSON<HwPageDetail>(`/api/handwriting/pages/${id}`).then(setDetail).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  function selectPage(id: number) {
    setSentToNotes(false);
    setSelected(id);
    loadDetail(id);
  }

  // keep polling the open page while it is still being recognized
  useEffect(() => {
    if (selected === null || detail?.status !== "processing") return;
    const t = setInterval(() => loadDetail(selected), 2000);
    return () => clearInterval(t);
  }, [selected, detail?.status, loadDetail]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    const form = new FormData();
    for (const f of Array.from(files)) form.append("files", f);
    const res = await fetch(`${API}/api/handwriting/upload`, { method: "POST", body: form });
    const data = await res.json();
    refresh();
    if (data.page_ids?.length) selectPage(data.page_ids[0]);
  }

  async function toNotes() {
    if (selected === null) return;
    await postJSON(`/api/handwriting/pages/${selected}/to-notes`, {});
    setSentToNotes(true);
  }

  const corrected = status?.corrected_lines ?? 0;

  return (
    <section className="axscreen" style={{ padding: 32, display: "flex", flexDirection: "column", gap: 20, maxWidth: 1120 }}>
      <div>
        <MonoLabel size={11} spacing="0.24em" style={{ color: "var(--accent)", display: "block", marginBottom: 8 }}>
          RECOGNITION
        </MonoLabel>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 500 }}>Handwriting</h1>
        <p style={{ margin: "8px 0 0", color: "var(--dim)", fontSize: 14 }}>
          Read handwritten pages with your local vision model — correct a line and it learns your words.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "320px minmax(0, 1fr)", gap: 20, alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Panel style={{ padding: 18 }}>
            <MonoLabel style={{ display: "block", marginBottom: 6 }}>UPLOAD A PAGE</MonoLabel>
            <p style={{ margin: "0 0 12px", fontSize: 12, color: "var(--dim)" }}>
              Photos or scans of handwritten notes (multi-line pages are fine).
            </p>
            <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={(e) => upload(e.target.files)} />
            <GlowButton onClick={() => fileRef.current?.click()} style={{ width: "100%" }}>
              <Upload className="h-4 w-4" /> CHOOSE IMAGES
            </GlowButton>
          </Panel>

          <Panel style={{ padding: 18 }}>
            <MonoLabel style={{ display: "block", marginBottom: 8 }}>LEARNS YOUR WORDS</MonoLabel>
            <p style={{ margin: 0, fontSize: 12, color: "var(--dim)", lineHeight: 1.6 }}>
              Every line you correct is remembered and passed to the vision model as a hint on the next page.
            </p>
            <div style={{ marginTop: 12, border: "1px solid var(--line2)", padding: "8px 12px", fontSize: 13, color: "var(--accent)" }}>
              {corrected} corrected line{corrected === 1 ? "" : "s"} learned
            </div>
          </Panel>

          <Panel>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--line)" }}>
              <MonoLabel>PAGES</MonoLabel>
            </div>
            <div style={{ maxHeight: 384, overflowY: "auto" }}>
              {pages.length === 0 && <p style={{ padding: "12px 16px", fontSize: 12, color: "var(--dim)" }}>No pages yet.</p>}
              {pages.map((p) => {
                const on = selected === p.id;
                return (
                  <button
                    key={p.id}
                    onClick={() => selectPage(p.id)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      width: "100%",
                      textAlign: "left",
                      padding: "12px 16px",
                      borderBottom: "1px solid var(--line)",
                      borderLeft: `2px solid ${on ? "var(--accent)" : "transparent"}`,
                      background: on ? "var(--panel2)" : "transparent",
                    }}
                  >
                    {p.status === "processing" ? (
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin" style={{ color: "var(--accent)" }} />
                    ) : p.status === "error" ? (
                      <CircleAlert className="h-4 w-4 shrink-0" style={{ color: "#f87171" }} />
                    ) : (
                      <PenLine className="h-4 w-4 shrink-0" style={{ color: "var(--dim)" }} />
                    )}
                    <span style={{ minWidth: 0, flex: 1 }}>
                      <span style={{ display: "block", fontSize: 13, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {p.filename}
                      </span>
                      <MonoLabel size={9} spacing="0.1em" dim style={{ marginTop: 3, display: "block" }}>
                        {p.line_count ?? 0} LINES · {p.corrected_count ?? 0} CORRECTED · {timeAgo(p.created_at).toUpperCase()}
                      </MonoLabel>
                    </span>
                  </button>
                );
              })}
            </div>
          </Panel>
        </div>

        <div>
          {!detail ? (
            <div style={{ display: "grid", placeItems: "center", height: 256, border: "1px dashed var(--line2)", fontSize: 14, color: "var(--dim)" }}>
              Upload a page or pick one from the list.
            </div>
          ) : detail.status === "processing" ? (
            <Panel style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, height: 256, fontSize: 14, color: "var(--dim)" }}>
              <Loader2 className="h-6 w-6 animate-spin" style={{ color: "var(--accent)" }} />
              Reading your handwriting line by line…
            </Panel>
          ) : detail.status === "error" ? (
            <Panel style={{ padding: 24, fontSize: 14, color: "#f87171" }}>Recognition failed: {detail.error}</Panel>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <h2 style={{ margin: 0, minWidth: 0, flex: 1, fontSize: 16, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {detail.filename}
                </h2>
                <GlowButton variant="ghost" onClick={toNotes} disabled={sentToNotes}>
                  {sentToNotes ? (
                    <>
                      <Check className="h-4 w-4" style={{ color: "var(--accent)" }} /> SENT
                    </>
                  ) : (
                    <>
                      <Send className="h-4 w-4" /> SEND TO NOTES
                    </>
                  )}
                </GlowButton>
              </div>
              <p style={{ margin: 0, fontSize: 12, color: "var(--dim)" }}>
                Fix any line below — edits save when you leave the field and become training examples for your personal model.
              </p>
              {detail.lines.map((line) => (
                <LineEditor key={line.id} line={line} onSaved={() => refresh()} />
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
