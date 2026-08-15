"use client";

import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { normalizeMath } from "@/lib/mathMarkdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { Check, LoaderCircle, Play, ScanText, Table2, Trash2 } from "lucide-react";
import VideoModal from "@/components/VideoModal";
import { Panel, MonoLabel, GlowButton } from "@/components/ui";
import { API, getJSON, postJSON, VideoFrame, VideoSegment } from "@/lib/api";

function timestamp(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

export default function VideoReviewPage() {
  const [frames, setFrames] = useState<VideoFrame[]>([]);
  const [selected, setSelected] = useState<VideoFrame | null>(null);
  const [segments, setSegments] = useState<VideoSegment[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [consolidating, setConsolidating] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");

  const loadFrames = useCallback(() => {
    getJSON<VideoFrame[]>("/api/video/frames").then(setFrames).catch(() => {});
  }, []);
  useEffect(() => {
    loadFrames();
  }, [loadFrames]);

  async function choose(frame: VideoFrame) {
    setError("");
    const detail = await getJSON<VideoFrame>(`/api/video/frames/${frame.id}`);
    setSelected(detail);
    setSegments(detail.segments ?? []);
  }

  function startStreaming() {
    if (!selected || streaming) return;
    setStreaming(true);
    setError("");
    const stream = new EventSource(`${API}/api/video/frames/${selected.id}/ocr-stream`);
    stream.addEventListener("segment", (event) => {
      const next = JSON.parse((event as MessageEvent).data) as VideoSegment;
      setSegments((current) =>
        [...current.filter((part) => part.id !== next.id), next].sort((a, b) => a.segment_index - b.segment_index),
      );
    });
    stream.addEventListener("complete", () => {
      stream.close();
      setStreaming(false);
      loadFrames();
    });
    stream.addEventListener("error", (event) => {
      const message = (event as MessageEvent).data ? JSON.parse((event as MessageEvent).data).error : "OCR stream disconnected";
      setError(message);
      stream.close();
      setStreaming(false);
    });
  }

  async function verify() {
    if (!selected || consolidating) return;
    setConsolidating(true);
    setError("");
    const approvedId = selected.id;
    try {
      await postJSON<{ markdown: string; frame: VideoFrame }>(`/api/video/frames/${approvedId}/verify`, {});
      setFrames((current) => current.filter((frame) => frame.id !== approvedId));
      setSelected(null);
      setSegments([]);
    } catch {
      setError("Couldn't consolidate this board. Check that the local vision model is running.");
    } finally {
      setConsolidating(false);
    }
  }

  async function deleteFrame(frame: VideoFrame) {
    if (!window.confirm("Delete this recommended frame? This can't be undone.")) return;
    setError("");
    try {
      const res = await fetch(`${API}/api/video/frames/${frame.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      setFrames((current) => current.filter((f) => f.id !== frame.id));
      if (selected?.id === frame.id) {
        setSelected(null);
        setSegments([]);
      }
    } catch {
      setError("Couldn't delete this frame. Is the Study Buddy API running?");
    }
  }

  const pending = frames.filter((frame) => frame.status !== "reviewed");

  return (
    <section className="axscreen" style={{ padding: 32, display: "flex", flexDirection: "column", gap: 20, maxWidth: 1180 }}>
      <div>
        <MonoLabel size={11} spacing="0.24em" style={{ color: "var(--accent)", display: "block", marginBottom: 8 }}>
          BOARD REVIEW
        </MonoLabel>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 500 }}>Video review</h1>
        <p style={{ margin: "8px 0 0", color: "var(--dim)", fontSize: 14 }}>
          Stable lecture-board frames are saved for your approval. OCR streams crop by crop; approved boards become timestamped sources.
        </p>
      </div>

      {pending.length === 0 ? (
        <div style={{ border: "1px dashed var(--line2)", padding: 40, textAlign: "center", fontSize: 14, color: "var(--dim)" }}>
          No boards awaiting review. Upload a lecture video in Library — stable board states appear here after transcription.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "280px minmax(0, 1fr)", gap: 20, alignItems: "start" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {pending.map((frame) => {
              const on = selected?.id === frame.id;
              return (
                <button
                  key={frame.id}
                  onClick={() => choose(frame)}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    border: `1px solid ${on ? "var(--accent)" : "var(--line)"}`,
                    background: "var(--panel)",
                    boxShadow: on ? "0 0 24px -14px var(--accent)" : undefined,
                  }}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img style={{ aspectRatio: "16 / 9", width: "100%", objectFit: "cover" }} src={`${API}${frame.image_url}`} alt={`Board at ${timestamp(frame.timestamp)}`} />
                  <div style={{ padding: 12 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{frame.title ?? frame.filename}</div>
                    <div style={{ marginTop: 5, display: "flex", justifyContent: "space-between" }}>
                      <MonoLabel size={9} spacing="0.1em" dim>@ {timestamp(frame.timestamp)}</MonoLabel>
                      <MonoLabel size={9} spacing="0.1em" dim>{frame.status === "reviewed" ? "INDEXED" : "REVIEW"}</MonoLabel>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          <Panel style={{ padding: 20, minWidth: 0 }}>
            {!selected ? (
              <p style={{ padding: "80px 0", textAlign: "center", fontSize: 14, color: "var(--dim)" }}>Choose a captured board frame to review it.</p>
            ) : (
              <>
                <div style={{ marginBottom: 16, display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                  <div>
                    <h2 style={{ margin: 0, fontSize: 16, fontWeight: 500 }}>{selected.title ?? selected.filename}</h2>
                    <MonoLabel size={9} spacing="0.12em" dim style={{ marginTop: 4, display: "block" }}>
                      CAPTURED AT {timestamp(selected.timestamp)} — REVIEW THE FULL IMAGE BEFORE INDEXING
                    </MonoLabel>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <GlowButton variant="ghost" onClick={() => setPlaying(true)}>
                      <Play className="h-4 w-4" /> PLAY
                    </GlowButton>
                    <GlowButton variant="ghost" onClick={() => deleteFrame(selected)}>
                      <Trash2 className="h-4 w-4" /> DELETE
                    </GlowButton>
                  </div>
                </div>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img style={{ maxHeight: 520, width: "100%", background: "var(--panel2)", objectFit: "contain", border: "1px solid var(--line)" }} src={`${API}${selected.image_url}`} alt="Full board capture" />
                {selected.status !== "reviewed" && (
                  <div style={{ marginTop: 16, display: "flex", flexWrap: "wrap", gap: 12 }}>
                    <GlowButton onClick={startStreaming} disabled={streaming}>
                      {streaming ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ScanText className="h-4 w-4" />}
                      {streaming ? "READING CROPS…" : segments.length ? "RE-RUN CROP OCR" : "READ BOARD IN PIECES"}
                    </GlowButton>
                    <GlowButton variant="ghost" onClick={verify} disabled={consolidating || streaming || segments.length === 0}>
                      {consolidating ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                      {consolidating ? "RECONCILING…" : selected.status === "auto_processed" ? "VERIFY RESULT" : "CONSOLIDATE & INDEX"}
                    </GlowButton>
                  </div>
                )}
                {error && <p style={{ marginTop: 12, fontSize: 13, color: "#f87171" }}>{error}</p>}
                {selected.formatted_markdown && (
                  <div className="study-note" style={{ marginTop: 24, background: "var(--panel2)", padding: 20, fontSize: 14 }}>
                    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>{normalizeMath(selected.formatted_markdown)}</ReactMarkdown>
                  </div>
                )}
                {segments.length > 0 && (
                  <div style={{ marginTop: 24 }}>
                    <MonoLabel style={{ display: "block", marginBottom: 12 }}>PROGRESSIVE OCR RESULTS</MonoLabel>
                    <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(2, 1fr)" }}>
                      {segments.map((segment) => (
                        <article key={segment.id} style={{ border: "1px solid var(--line)" }}>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={`${API}${segment.crop_url}`} style={{ height: 96, width: "100%", objectFit: "cover" }} alt={`Board crop ${segment.segment_index + 1}`} />
                          <div style={{ padding: 12, fontSize: 14, whiteSpace: "pre-wrap" }}>
                            {segment.raw_text || <span style={{ color: "var(--dim)" }}>Reading crop…</span>}
                            {segment.table_markdown && (
                              <div style={{ marginTop: 12, display: "flex", gap: 8, borderTop: "1px solid var(--line)", paddingTop: 8, fontSize: 12, color: "var(--dim)" }}>
                                <Table2 className="h-4 w-4 shrink-0" />
                                Table detected; included in final reconciliation.
                              </div>
                            )}
                          </div>
                        </article>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
            {playing && selected && (
              <VideoModal
                src={`${API}${selected.video_url}`}
                timestamp={selected.timestamp}
                label={selected.title ?? selected.filename}
                onClose={() => setPlaying(false)}
              />
            )}
          </Panel>
        </div>
      )}
    </section>
  );
}
