"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, CircleAlert, Cog, Hourglass, Mic, RotateCcw, Square, UploadCloud } from "lucide-react";
import { Panel, MonoLabel, GlowButton } from "@/components/ui";
import { API, getJSON, Item, RetryResult, timeAgo } from "@/lib/api";

const STATUS_ICON: Record<string, React.ReactNode> = {
  pending: <Hourglass className="h-4 w-4" style={{ color: "#fbbf24" }} />,
  processing: <Cog className="h-4 w-4 animate-spin" style={{ color: "var(--accent)" }} />,
  done: <CheckCircle2 className="h-4 w-4" style={{ color: "var(--accent)" }} />,
  error: <CircleAlert className="h-4 w-4" style={{ color: "#f87171" }} />,
};

interface RecordedAudio {
  blob: Blob;
  url: string;
  extension: string;
}

interface UploadResult {
  queued: number;
  capture_date: string;
}

function recordingFormat() {
  const formats = [
    { mimeType: "audio/webm;codecs=opus", extension: "webm" },
    { mimeType: "audio/mp4", extension: "m4a" },
    { mimeType: "audio/ogg;codecs=opus", extension: "ogg" },
  ];
  return formats.find(({ mimeType }) => MediaRecorder.isTypeSupported(mimeType));
}

function elapsedTime(seconds: number) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remainder = (seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainder}`;
}

export default function FilesPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState("");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [captureText, setCaptureText] = useState("");
  const [captureMessage, setCaptureMessage] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [recordedAudio, setRecordedAudio] = useState<RecordedAudio | null>(null);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [recordingError, setRecordingError] = useState("");
  const [retryingItem, setRetryingItem] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);

  const refresh = useCallback(() => {
    return getJSON<Item[]>("/api/items").then(setItems).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }, []);

  async function upload(files: FileList | File[], text = "") {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    form.append("text", text);
    setUploading(true);
    setUploadProgress(0);
    setUploadError("");
    try {
      const result = await new Promise<UploadResult>((resolve, reject) => {
        const request = new XMLHttpRequest();
        request.open("POST", `${API}/api/upload`);
        request.upload.onprogress = (event) => {
          if (event.lengthComputable) setUploadProgress(Math.round((event.loaded / event.total) * 100));
        };
        request.onload = () => {
          if (request.status >= 200 && request.status < 300) {
            resolve(JSON.parse(request.responseText));
          } else {
            reject(new Error(JSON.parse(request.responseText || "{}").detail || `Upload failed (${request.status})`));
          }
        };
        request.onerror = () => reject(new Error("Could not reach the Study Buddy API"));
        request.send(form);
      });
      setUploadProgress(100);
      refresh();
      return result;
    } finally {
      setUploading(false);
    }
  }

  function chooseFiles(files: FileList | File[]) {
    setSelectedFiles(Array.from(files));
    setCaptureMessage("");
  }

  async function saveCapture() {
    if (!selectedFiles.length && !captureText.trim()) return;
    setCaptureMessage("");
    try {
      const result = await upload(selectedFiles, captureText.trim());
      setCaptureMessage(
        `Added ${result.queued} capture${result.queued === 1 ? "" : "s"} with citation date ${result.capture_date}.`,
      );
      setSelectedFiles([]);
      setCaptureText("");
      if (inputRef.current) inputRef.current.value = "";
    } catch (error) {
      setCaptureMessage(error instanceof Error ? error.message : "Could not save this capture.");
    }
  }

  function discardRecording() {
    if (recordedAudio) URL.revokeObjectURL(recordedAudio.url);
    setRecordedAudio(null);
    setRecordingSeconds(0);
    setRecordingError("");
  }

  async function startRecording() {
    discardRecording();
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setRecordingError("This browser does not support microphone recording.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      chunksRef.current = [];
      const format = recordingFormat();
      const recorder = new MediaRecorder(stream, format ? { mimeType: format.mimeType } : undefined);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        const extension = format?.extension ?? (blob.type.includes("mp4") ? "m4a" : "webm");
        setRecordedAudio({ blob, extension, url: URL.createObjectURL(blob) });
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      };
      recorder.start(1000);
      setIsRecording(true);
      setRecordingSeconds(0);
      const startedAt = Date.now();
      timerRef.current = window.setInterval(() => {
        setRecordingSeconds(Math.floor((Date.now() - startedAt) / 1000));
      }, 250);
    } catch (error) {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setRecordingError(
        error instanceof DOMException && error.name === "NotAllowedError"
          ? "Microphone permission was denied. Allow microphone access and try again."
          : "Could not start the microphone. Check that it is connected and available.",
      );
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    timerRef.current = null;
    setIsRecording(false);
  }

  async function saveRecording() {
    if (!recordedAudio) return;
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const file = new File([recordedAudio.blob], `live-recording-${stamp}.${recordedAudio.extension}`, {
      type: recordedAudio.blob.type,
    });
    try {
      await upload([file]);
      discardRecording();
    } catch {
      setRecordingError("The recording could not be saved. Please try again.");
    }
  }

  async function retryItem(item: Item) {
    setRetryingItem(item.id);
    setUploadError("");
    try {
      const response = await fetch(`${API}/api/items/${item.id}/retry`, { method: "POST" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Could not retry this item");
      const result = body as RetryResult;
      setCaptureMessage(
        result.recovered === "vector_index"
          ? `Repaired the search index for "${item.title ?? item.filename}".`
          : `Queued "${item.title ?? item.filename}" for processing again.`,
      );
      await refresh();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Could not retry this item");
    } finally {
      setRetryingItem(null);
    }
  }

  const fieldStyle: React.CSSProperties = {
    width: "100%",
    background: "var(--panel2)",
    border: "1px solid var(--line)",
    color: "var(--text)",
    padding: "10px 12px",
    fontSize: 14,
    outline: "none",
  };

  return (
    <section className="axscreen" style={{ padding: 32, display: "flex", flexDirection: "column", gap: 24, maxWidth: 1000 }}>
      <div>
        <MonoLabel size={11} spacing="0.24em" style={{ color: "var(--accent)", display: "block", marginBottom: 8 }}>
          LIBRARY
        </MonoLabel>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 500 }}>Capture &amp; upload</h1>
        <p style={{ margin: "8px 0 0", color: "var(--dim)", fontSize: 14 }}>
          Everything you capture or upload, processed locally.
        </p>
      </div>

      {/* Recorder */}
      <Panel style={{ padding: 22 }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 16 }}>
          <span
            style={{
              width: 44,
              height: 44,
              borderRadius: "50%",
              display: "grid",
              placeItems: "center",
              border: `1px solid ${isRecording ? "#f87171" : "var(--line2)"}`,
              color: isRecording ? "#f87171" : "var(--accent)",
              animation: isRecording ? "pulse 1.4s infinite" : undefined,
            }}
          >
            <Mic className="h-5 w-5" />
          </span>
          <div style={{ minWidth: 180, flex: 1 }}>
            <MonoLabel size={11}>RECORD A LECTURE OR VOICE NOTE</MonoLabel>
            <p style={{ margin: "6px 0 0", fontSize: 12, color: "var(--dim)" }}>
              {isRecording
                ? `Recording ${elapsedTime(recordingSeconds)} — keep this page open.`
                : recordedAudio
                  ? "Recording ready. Preview it, then save it for transcription."
                  : "Use your microphone and turn the recording into study notes."}
            </p>
          </div>
          {!isRecording && !recordedAudio && (
            <GlowButton onClick={startRecording}>
              <Mic className="h-4 w-4" /> START RECORDING
            </GlowButton>
          )}
          {isRecording && (
            <button
              onClick={stopRecording}
              style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "#ef4444", color: "#fff", padding: "10px 16px", fontSize: 12, fontFamily: "var(--font-jetbrains-mono), monospace", letterSpacing: "0.1em" }}
            >
              <Square className="h-3.5 w-3.5 fill-current" /> STOP
            </button>
          )}
        </div>
        {recordedAudio && (
          <div style={{ marginTop: 16, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, borderTop: "1px solid var(--line)", paddingTop: 16 }}>
            <audio controls src={recordedAudio.url} style={{ height: 40, minWidth: 240, flex: 1 }} />
            <GlowButton variant="ghost" onClick={startRecording}>
              <RotateCcw className="h-4 w-4" /> AGAIN
            </GlowButton>
            <GlowButton onClick={saveRecording} disabled={uploading}>
              <UploadCloud className="h-4 w-4" /> {uploading ? "SAVING…" : "SAVE & PROCESS"}
            </GlowButton>
          </div>
        )}
        {recordingError && <p style={{ marginTop: 12, fontSize: 13, color: "#f87171" }} role="alert">{recordingError}</p>}
      </Panel>

      {/* Upload */}
      <Panel style={{ padding: 22 }}>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            chooseFiles(e.dataTransfer.files);
          }}
          onClick={() => inputRef.current?.click()}
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 10,
            border: `1px dashed ${dragging ? "var(--accent)" : "var(--line2)"}`,
            background: dragging ? "color-mix(in srgb, var(--accent) 8%, transparent)" : "transparent",
            padding: "32px 0",
            cursor: "pointer",
          }}
        >
          <span style={{ width: 44, height: 44, borderRadius: "50%", display: "grid", placeItems: "center", border: "1px solid var(--line2)", color: "var(--accent)" }}>
            <UploadCloud className="h-5 w-5" />
          </span>
          <div style={{ fontSize: 14, fontWeight: 500 }}>
            {uploading
              ? `Uploading… ${uploadProgress}%`
              : selectedFiles.length
                ? `${selectedFiles.length} file${selectedFiles.length === 1 ? "" : "s"} selected`
                : "Drop files here or click to choose"}
          </div>
          <MonoLabel size={10} spacing="0.14em" dim>
            {selectedFiles.length ? selectedFiles.map((file) => file.name).join(" · ") : "AUDIO · VIDEO · PDF · IMAGES · TEXT"}
          </MonoLabel>
          <input ref={inputRef} type="file" multiple hidden onChange={(e) => e.target.files && chooseFiles(e.target.files)} />
        </div>

        <label htmlFor="capture-text" style={{ display: "block", marginTop: 16 }}>
          <MonoLabel size={10} spacing="0.16em">TEXT OR FILE CONTEXT</MonoLabel>
        </label>
        <textarea
          id="capture-text"
          value={captureText}
          onChange={(event) => {
            setCaptureText(event.target.value);
            setCaptureMessage("");
          }}
          rows={4}
          placeholder="Write or paste notes here, or describe the files — e.g. yesterday's biology notes from the cell-division lecture."
          style={{ ...fieldStyle, marginTop: 8, resize: "vertical" }}
        />
        <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <p style={{ fontSize: 12, color: "var(--dim)", maxWidth: 460 }}>
            Text alone is saved as study material. With files, it becomes their context. Dates mentioned here are used in citations.
          </p>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {selectedFiles.length > 0 && (
              <button onClick={() => setSelectedFiles([])} style={{ padding: "8px 12px", fontSize: 13, color: "var(--dim)" }}>
                Clear files
              </button>
            )}
            <GlowButton onClick={saveCapture} disabled={uploading || (!selectedFiles.length && !captureText.trim())}>
              {uploading ? "ADDING…" : "ADD TO LIBRARY"}
            </GlowButton>
          </div>
        </div>
        {captureMessage && <p style={{ marginTop: 12, fontSize: 13, color: "var(--dim)" }} role="status">{captureMessage}</p>}
      </Panel>
      {uploadError && <p style={{ fontSize: 13, color: "#f87171" }}>{uploadError}</p>}

      {/* Queue */}
      <div>
        <MonoLabel style={{ display: "block", marginBottom: 12 }}>PROCESSING QUEUE</MonoLabel>
        <Panel>
          {items.length === 0 && <p style={{ padding: 20, fontSize: 13, color: "var(--dim)" }}>No files yet.</p>}
          {items.map((it) => {
            const statusColor =
              it.status === "done" ? "var(--accent)" : it.status === "error" ? "#f87171" : "#fbbf24";
            return (
              <div key={it.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 20px", borderBottom: "1px solid var(--line)" }}>
                {STATUS_ICON[it.status] ?? null}
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {it.title ?? it.filename}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {it.kind} · {it.capture_date ?? timeAgo(it.created_at)}
                    {it.subject ? ` · ${it.subject}` : ""}
                    {it.metadata_text ? ` · ${it.metadata_text}` : ""}
                    {it.error ? ` · ${it.error}` : ""}
                  </div>
                </div>
                <MonoLabel size={9} spacing="0.14em" style={{ color: statusColor, border: `1px solid ${statusColor}`, padding: "3px 8px" }}>
                  {it.status}
                </MonoLabel>
                {it.status === "error" && (
                  <button
                    type="button"
                    onClick={() => retryItem(it)}
                    disabled={retryingItem === it.id}
                    style={{ display: "inline-flex", alignItems: "center", gap: 6, border: "1px solid var(--line2)", padding: "6px 10px", fontSize: 11, color: "var(--accent)", fontFamily: "var(--font-jetbrains-mono), monospace" }}
                  >
                    <RotateCcw className={`h-3.5 w-3.5 ${retryingItem === it.id ? "animate-spin" : ""}`} />
                    {retryingItem === it.id ? "…" : "RETRY"}
                  </button>
                )}
              </div>
            );
          })}
        </Panel>
      </div>
    </section>
  );
}
