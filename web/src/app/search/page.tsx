"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import { normalizeMath } from "@/lib/mathMarkdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { Mic, Play, SendHorizonal, Square, Trash2 } from "lucide-react";
import VideoModal from "@/components/VideoModal";
import { MonoLabel } from "@/components/ui";
import { API, getJSON, postJSON } from "@/lib/api";

interface Subject { id: number; name: string }
interface CitationSource { label: string; item_id: number; note_id: number | null; timestamp?: number | null }
interface VideoSource { item_id: number; timestamp: number; label: string }
interface ImageSource { chunk_id: number; item_id: number; timestamp: number | null; label: string; url: string }

interface AskResult {
    answer: string;
    sources: CitationSource[];
    images: ImageSource[];
    videos: VideoSource[];
    deck_id?: number | null;
    transcript?: string;
}

interface Turn {
  id?: number;
  role: "user" | "assistant";
  content: string;
  sources?: CitationSource[];
  videos?: VideoSource[];
  images?: ImageSource[];
  created_at?: number;
}

function historyTime(timestamp?: number) {
  if (!timestamp) return "Just now";
  return new Date(timestamp * 1000).toLocaleString([], {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

// Server turns carry a unique id; an optimistic (not-yet-saved) turn has none.
function turnKey(turn: Turn, index: number) {
  return turn.id != null ? `id-${turn.id}` : `idx-${index}`;
}

function timestampLabel(timestamp: number) {
  const totalSeconds = Math.floor(timestamp);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function videoHref(video: VideoSource) {
  const totalSeconds = Math.floor(video.timestamp);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `/search?video=${video.item_id}&t=${minutes}m${String(seconds).padStart(2, "0")}s`;
}

function timestampFromSourceLabel(label: string): number | null {
  const match = /@ (?:(\d+):)?(\d+):(\d{2})$/.exec(label);
  if (!match) return null;
  const hours = Number(match[1] ?? 0);
  const minutes = Number(match[2]);
  const seconds = Number(match[3]);
  return seconds < 60 ? hours * 3600 + minutes * 60 + seconds : null;
}

function sourceVideo(turn: Turn, source: CitationSource): VideoSource | null {
  if (source.timestamp != null) {
    return { item_id: source.item_id, timestamp: source.timestamp, label: source.label };
  }
  const savedVideo = turn.videos?.find((video) =>
    video.item_id === source.item_id && source.label.endsWith(`@ ${timestampLabel(video.timestamp)}`)
  );
  if (savedVideo) return savedVideo;
  const timestamp = timestampFromSourceLabel(source.label);
  return timestamp == null ? null : { item_id: source.item_id, timestamp, label: source.label };
}

function speechRecordingFormat() {
  const formats = [
    { mimeType: "audio/webm;codecs=opus", extension: "webm" },
    { mimeType: "audio/mp4", extension: "m4a" },
    { mimeType: "audio/ogg;codecs=opus", extension: "ogg" },
  ];
  return formats.find(({ mimeType }) => MediaRecorder.isTypeSupported(mimeType));
}

function SearchInner() {
  const params = useSearchParams();
  const router = useRouter();
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subject, setSubject] = useState("");
  const [chat, setChat] = useState<Turn[]>([]);
  const [input, setInput] = useState(params.get("q") ?? "");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [speechError, setSpeechError] = useState("");
  const [busyMessage, setBusyMessage] = useState("Searching your notes…");
  const bottomRef = useRef<HTMLDivElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const activeVideo = (() => {
    const itemId = Number(params.get("video"));
    const match = /^(\d+)m(\d{1,2})s$/.exec(params.get("t") ?? "");
    if (!Number.isInteger(itemId) || itemId <= 0 || !match || Number(match[2]) >= 60) return null;
    const timestamp = Number(match[1]) * 60 + Number(match[2]);
    return chat.flatMap((turn) => turn.videos ?? []).find((video) =>
      video.item_id === itemId && Math.floor(video.timestamp) === timestamp
    ) ?? { item_id: itemId, timestamp, label: `Lecture video at ${timestampLabel(timestamp)}` };
  })();

  useEffect(() => {
    getJSON<Subject[]>("/api/subjects").then(setSubjects).catch(() => {});
    getJSON<Turn[]>("/api/chat?limit=200").then(setChat).catch(() => {});
  }, []);

  useEffect(() => () => {
    const recorder = recorderRef.current;
    if (recorder?.state === "recording") {
      recorder.onstop = null;
      recorder.stop();
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat]);

  async function ask(q?: string) {
    const question = (q ?? input).trim();
    if (!question || busy) return;
    setInput("");
    setChat((c) => [...c, { role: "user", content: question }]);
    setBusyMessage(/(?:create|make|generate|build).*flash[\s-]*cards?/i.test(question)
      ? "Creating your flashcards…"
      : "Searching your notes…");
    setBusy(true);
    try {
      const r = await postJSON<AskResult>("/api/ask", {
        question,
        subject: subject || null,
      });
      const saved = await getJSON<Turn[]>("/api/chat?limit=200");
      setChat(saved.length ? saved : (c) => [...c, {
          role: "assistant",
          content: r.answer,
          sources: r.sources,
          videos: r.videos,
          images: r.images
      }]);
    } catch {
      setChat((c) => [...c, {
        role: "assistant",
        content: "Couldn't reach the Study Buddy API — is `uvicorn server:app` running?",
      }]);
    } finally {
      setBusy(false);
    }
  }

  async function submitVoice(blob: Blob, extension: string) {
    const form = new FormData();
    form.append("audio", new File([blob], `spoken-question.${extension}`, { type: blob.type }));
    form.append("subject", subject);
    setSpeechError("");
    setBusyMessage("Transcribing your question, then searching your notes…");
    setBusy(true);
    try {
      const response = await fetch(`${API}/api/ask/audio`, { method: "POST", body: form });
      const raw = await response.text();
      let result: (AskResult & { detail?: string }) | null = null;
      try {
        result = JSON.parse(raw) as AskResult & { detail?: string };
      } catch {
        if (!response.ok) {
          throw new Error(response.status >= 500
            ? "The local voice service failed. Check the backend and LM Studio, then try again."
            : "The voice service returned an unreadable response.");
        }
      }
      if (!response.ok) throw new Error(result?.detail ?? "The voice question could not be processed.");
      if (!result) throw new Error("The voice service returned an empty response.");
      const saved = await getJSON<Turn[]>("/api/chat?limit=200");
      setChat(saved.length ? saved : (current) => [
        ...current,
        { role: "user", content: result.transcript ?? "Spoken question" },
        { role: "assistant", content: result.answer, sources: result.sources, videos: result.videos, images: result.images },
      ]);
    } catch (error) {
      setSpeechError(error instanceof Error ? error.message : "The voice question could not be processed.");
    } finally {
      setBusy(false);
    }
  }

  async function startRecording() {
    if (busy || recording) return;
    setSpeechError("");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setSpeechError("This browser does not support microphone recording.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      chunksRef.current = [];
      const format = speechRecordingFormat();
      const recorder = new MediaRecorder(stream, format ? { mimeType: format.mimeType } : undefined);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const mimeType = recorder.mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: mimeType });
        const extension = format?.extension ?? (mimeType.includes("mp4") ? "m4a" : mimeType.includes("ogg") ? "ogg" : "webm");
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        recorderRef.current = null;
        setRecording(false);
        void submitVoice(blob, extension);
      };
      recorder.start(500);
      setRecording(true);
    } catch (error) {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setSpeechError(
        error instanceof DOMException && error.name === "NotAllowedError"
          ? "Microphone permission was denied. Allow access and try again."
          : "Could not start the microphone. Check that it is available.",
      );
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }

  async function clearHistory() {
    await fetch(`${API}/api/chat`, { method: "DELETE" });
    setChat([]);
  }

  const questions = chat.filter((turn) => turn.role === "user");

  return (
    <section className="axscreen" style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 60px)", minHeight: 0 }}>
      {/* Top bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "16px 32px",
          borderBottom: "1px solid var(--line)",
        }}
      >
        <MonoLabel size={11} spacing="0.2em" style={{ color: "var(--accent)" }}>ASK MY NOTES</MonoLabel>
        <select
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          style={{
            marginLeft: 12,
            background: "var(--panel2)",
            border: "1px solid var(--line)",
            color: "var(--text)",
            padding: "6px 10px",
            fontSize: 12,
            outline: "none",
          }}
        >
          <option value="">All subjects</option>
          {subjects.map((s) => (
            <option key={s.id} value={s.name}>{s.name}</option>
          ))}
        </select>
        {chat.length > 0 && (
          <button
            onClick={clearHistory}
            style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 8, color: "var(--dim)", fontSize: 12, border: "1px solid var(--line2)", padding: "6px 10px" }}
          >
            <Trash2 className="h-4 w-4" /> Clear history
          </button>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "240px minmax(0, 1fr)", flex: 1, minHeight: 0 }}>
        {/* History rail */}
        <div style={{ borderRight: "1px solid var(--line)", background: "var(--panel)", backdropFilter: "var(--blur)", WebkitBackdropFilter: "var(--blur)", overflowY: "auto", minHeight: 0 }}>
          <div style={{ position: "sticky", top: 0, padding: "12px 16px", borderBottom: "1px solid var(--line)", background: "var(--panel)" }}>
            <MonoLabel size={10} spacing="0.18em">CHAT HISTORY</MonoLabel>
          </div>
          {questions.length === 0 ? (
            <p style={{ padding: 16, fontSize: 12, color: "var(--dim)" }}>Your previous questions will appear here.</p>
          ) : (
            chat.map((turn, index) => turn.role === "user" && (
              <button
                key={turnKey(turn, index)}
                onClick={() => document.getElementById(`chat-turn-${turnKey(turn, index)}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}
                style={{ display: "block", width: "100%", textAlign: "left", padding: "12px 16px", borderBottom: "1px solid var(--line)" }}
              >
                <span style={{ display: "block", fontSize: 13, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{turn.content}</span>
                <MonoLabel size={9} spacing="0.12em" dim style={{ marginTop: 4, display: "block" }}>{historyTime(turn.created_at)}</MonoLabel>
              </button>
            ))
          )}
        </div>

        {/* Conversation */}
        <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div style={{ flex: 1, overflowY: "auto", padding: 24, display: "flex", flexDirection: "column", gap: 16, minHeight: 0 }}>
            {chat.length === 0 && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, padding: "64px 0", textAlign: "center" }}>
                <MonoLabel size={12} spacing="0.2em" style={{ color: "var(--accent)" }}>AXIOM AI</MonoLabel>
                <p style={{ fontSize: 14, color: "var(--dim)", maxWidth: 420 }}>
                  Ask about your notes, or say &ldquo;Create flashcards about…&rdquo; to build a study deck.
                </p>
              </div>
            )}
            {chat.map((t, i) =>
              t.role === "user" ? (
                <div
                  id={`chat-turn-${turnKey(t, i)}`}
                  key={turnKey(t, i)}
                  style={{ marginLeft: "auto", maxWidth: "75%", border: "1px solid var(--accent)", background: "color-mix(in srgb, var(--accent) 12%, transparent)", padding: "10px 14px", fontSize: 14, color: "var(--text)", scrollMarginTop: 16 }}
                >
                  {t.content}
                </div>
              ) : (
                <div key={turnKey(t, i)} style={{ maxWidth: "85%", border: "1px solid var(--line)", background: "var(--panel2)", padding: "14px 16px" }}>
                  <div className="study-note" style={{ fontSize: 14 }}>
                    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>{normalizeMath(t.content)}</ReactMarkdown>
                  </div>

                  {t.sources && t.sources.length > 0 && (
                    <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: "4px 8px", borderTop: "1px solid var(--line)", paddingTop: 8, fontSize: 12, color: "var(--dim)" }}>
                      <MonoLabel size={9} spacing="0.14em" dim>SOURCES</MonoLabel>
                      {t.sources.map((source, sourceIndex) => {
                        const video = sourceVideo(t, source);
                        return video ? (
                          <Link key={`${source.item_id}-${sourceIndex}`} href={videoHref(video)} style={{ color: "var(--accent)" }}>
                            {source.label}
                          </Link>
                        ) : source.note_id ? (
                          <Link key={`${source.item_id}-${sourceIndex}`} href={`/notes?note=${source.note_id}`} style={{ color: "var(--accent)" }}>
                            {source.label}
                          </Link>
                        ) : (
                          <span key={`${source.item_id}-${sourceIndex}`}>{source.label}</span>
                        );
                      })}
                    </div>
                  )}

                  {t.videos && t.videos.length > 0 && (
                    <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {t.videos.map((video) => (
                        <Link key={`${video.item_id}-${video.timestamp}`} href={videoHref(video)} style={{ display: "inline-flex", alignItems: "center", gap: 4, border: "1px solid var(--line2)", padding: "4px 8px", fontSize: 12, color: "var(--accent)" }}>
                          <Play className="h-3 w-3" />Play from {timestampLabel(video.timestamp)}
                        </Link>
                      ))}
                    </div>
                  )}
                  {t.images && t.images.length > 0 && (
                    <div style={{ marginTop: 12, display: "grid", gap: 8, gridTemplateColumns: "repeat(2, 1fr)" }}>
                      {t.images.map((picture) => (
                        <figure key={picture.chunk_id} style={{ border: "1px solid var(--line)", background: "var(--panel)" }}>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={`${API}${picture.url}`} alt={picture.label} style={{ maxHeight: 256, width: "100%", objectFit: "contain" }} />
                          <figcaption style={{ borderTop: "1px solid var(--line)", padding: "8px 12px", fontSize: 12, color: "var(--dim)" }}>
                            {picture.label}{picture.timestamp != null ? ` @ ${Math.floor(picture.timestamp / 60)}:${String(Math.floor(picture.timestamp % 60)).padStart(2, "0")}` : ""}
                          </figcaption>
                        </figure>
                      ))}
                    </div>
                  )}
                </div>
              ),
            )}

            {busy && <MonoLabel size={12} spacing="0.16em">{busyMessage.toUpperCase()}<span style={{ animation: "pulse 1s infinite" }}>…</span></MonoLabel>}
            <div ref={bottomRef} />
          </div>

          {/* Input row */}
          <div style={{ padding: "16px 24px", borderTop: "1px solid var(--line)" }}>
            <div style={{ display: "flex", gap: 10 }}>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && ask()}
                disabled={busy || recording}
                placeholder={recording ? "Listening… click stop when you finish" : "Ask about your notes or create flashcards…"}
                style={{ flex: 1, background: "var(--panel2)", border: "1px solid var(--line)", color: "var(--text)", padding: "12px 16px", fontSize: 14, outline: "none" }}
              />
              <button
                onClick={recording ? stopRecording : startRecording}
                disabled={busy}
                aria-label={recording ? "Stop recording and ask" : "Ask with microphone"}
                title={recording ? "Stop recording and ask" : "Ask with microphone"}
                style={{
                  width: 48,
                  display: "grid",
                  placeItems: "center",
                  border: `1px solid ${recording ? "#f87171" : "var(--line2)"}`,
                  color: recording ? "#fff" : "var(--accent)",
                  background: recording ? "#ef4444" : "transparent",
                  animation: recording ? "pulse 1.4s infinite" : undefined,
                }}
              >
                {recording ? <Square className="h-4 w-4 fill-current" /> : <Mic className="h-5 w-5" />}
              </button>
              <button
                onClick={() => ask()}
                disabled={busy || recording || !input.trim()}
                aria-label="Send"
                style={{ width: 48, display: "grid", placeItems: "center", border: "1px solid var(--accent)", color: "var(--accent)", background: "transparent", opacity: busy || recording || !input.trim() ? 0.5 : 1 }}
              >
                <SendHorizonal className="h-5 w-5" />
              </button>
            </div>
            {recording && <p style={{ marginTop: 8, textAlign: "center", fontSize: 12, color: "#f87171" }}>Listening… click the stop button when your question is complete.</p>}
            {speechError && <p style={{ marginTop: 8, textAlign: "center", fontSize: 12, color: "#f87171" }} role="alert">{speechError}</p>}
          </div>
        </div>
      </div>

      {activeVideo && (
        <VideoModal
          src={`${API}/api/video/items/${activeVideo.item_id}/file`}
          timestamp={activeVideo.timestamp}
          label={activeVideo.label}
          onClose={() => {
            if (params.has("video") || params.has("t")) router.replace("/search", { scroll: false });
          }}
        />
      )}
    </section>
  );
}

export default function SearchPage() {
  return (
    <Suspense>
      <SearchInner />
    </Suspense>
  );
}
