// Use same-origin API paths by default. Next proxies them to FastAPI, which
// keeps server rendering and browser hydration identical and also works when
// the dashboard is opened from another device on the LAN.
export const API = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";

export async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export interface AskSource {
  note_id?: number;
  title?: string;
  subject?: string | null;
  [key: string]: unknown;
}

export interface AskResult {
  answer: string;
  sources?: AskSource[];
  videos?: unknown[];
  images?: unknown[];
  transcript?: string;
}

/** Ask the local AI a text question. Backed by POST /api/ask. */
export function askText(question: string, subject?: string): Promise<AskResult> {
  return postJSON<AskResult>("/api/ask", { question, subject: subject || undefined });
}

/** Ask with a recorded audio blob. Backed by POST /api/ask/audio (multipart). */
export async function askAudio(blob: Blob, subject?: string): Promise<AskResult> {
  const form = new FormData();
  form.append("audio", blob, "question.webm");
  if (subject) form.append("subject", subject);
  const res = await fetch(`${API}/api/ask/audio`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`/api/ask/audio: ${res.status}`);
  return res.json();
}

export interface Stats {
  notes: number;
  files: number;
  chunks: number;
  flashcards: number;
  audiobooks: number;
  disk_used_gb: number;
  disk_total_gb: number;
}

export interface NotePreview {
  id: number;
  item_id: number;
  created_at: number;
  title: string | null;
  kind: string;
  subject_id: number | null;
  subject: string | null;
  preview: string;
}

export interface Subject {
  id: number;
  name: string;
  created_at: number;
}

export interface Item {
  id: number;
  filename: string;
  kind: string;
  status: string;
  error: string | null;
  title: string | null;
  subject: string | null;
  metadata_text?: string | null;
  capture_date?: string | null;
  created_at: number;
}

export interface RetryResult {
  ok: boolean;
  status: "pending" | "done";
  recovered: "requeued" | "vector_index";
}

export interface ActivityEvent {
  type: string;
  label: string;
  at: number;
}

export interface Audiobook {
  name: string;
  created_at: number;
  size_mb: number;
}

export interface Task {
  id: number;
  label: string;
  due: string | null;
  done: number;
  google_event_id: string | null;
  created_at: number;
}

export interface Deck {
  id: number;
  title: string;
  topic: string;
  subject: string | null;
  sources: unknown[];
  card_count: number;
  created_at: number;
}

export interface HwPage {
  id: number;
  filename: string;
  status: "processing" | "done" | "error";
  error: string | null;
  item_id: number | null;
  created_at: number;
  line_count: number;
  corrected_count: number;
}

export interface HwLine {
  id: number;
  line_index: number;
  crop_url: string;
  pred_text: string;
  corrected_text: string | null;
}

export interface HwPageDetail extends Omit<HwPage, "line_count" | "corrected_count"> {
  lines: HwLine[];
}

export interface HwStatus {
  corrected_lines: number;
}

export interface VideoSegment {
  id: number;
  segment_index: number;
  crop_url: string;
  raw_text: string;
  table_markdown: string | null;
  status: "pending" | "done";
}

export interface VideoFrame {
  id: number;
  item_id: number;
  timestamp: number;
  title: string | null;
  filename: string;
  status: "awaiting_review" | "auto_processed" | "reviewed";
  segment_count: number;
  done_segments: number | null;
  image_url: string;
  video_url: string;
  formatted_markdown: string | null;
  segments?: VideoSegment[];
}

export function timeAgo(ts: number): string {
  const s = Math.max(1, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} minute${m > 1 ? "s" : ""} ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hour${h > 1 ? "s" : ""} ago`;
  const d = Math.floor(h / 24);
  return `${d} day${d > 1 ? "s" : ""} ago`;
}

export function shortDate(ts: number): string {
  const d = new Date(ts * 1000);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const fmtTime = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  if (d.toDateString() === today.toDateString()) return `Today, ${fmtTime}`;
  if (d.toDateString() === yesterday.toDateString()) return `Yesterday, ${fmtTime}`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
