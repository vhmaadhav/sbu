// Client for the adaptive learning path API (/api/learn/*).
import { getJSON, postJSON, API } from "./api";

export interface Goal {
  id: number;
  name: string;
  slug: string;
  status: "building" | "ready" | "error";
  error: string | null;
  created_at: number;
}

export interface GoalSummary {
  concepts: number;
  mastered: number;
  weak: number;
  untested: number;
  average: number;
}

export interface SessionSummary {
  id: number;
  kind: "diagnostic" | "study" | "review";
  status: string;
  created_at: number;
  completed_at: number | null;
  answered: number | null;
  correct: number | null;
}

export interface GoalResponse {
  goal: Goal | null;
  summary: GoalSummary | null;
  sessions?: SessionSummary[];
  llm_available?: boolean;
}

export interface ConceptNode {
  id: number;
  name: string;
  blurb: string;
  tier: number;
  position: number;
  p_known: number;
  attempts: number;
  confidence: number;
  in_srs: boolean;
  downstream: number;
}

export interface ConceptEdge {
  prereq_id: number;
  concept_id: number;
}

export interface Graph {
  nodes: ConceptNode[];
  edges: ConceptEdge[];
}

export interface Gap extends ConceptNode {
  concept_id: number;
  missing_prerequisite: boolean;
  blocking: string[];
  reason: string;
}

export interface SourceChunk {
  chunk_id: number;
  text: string;
  source_label: string;
  item_id: number;
  ts_start: number | null;
  page: number | null;
}

export interface Question {
  id: number;
  concept_id: number;
  concept_name: string;
  stem: string;
  options: string[];
}

export interface SessionItem {
  item_id: number;
  kind: "read" | "quiz";
  position: number;
  concept: { id: number; name: string; blurb: string; tier: number };
  sources?: SourceChunk[];
  question?: Question;
  progress: { done: number; total: number };
}

export interface NextResponse {
  done: boolean;
  item?: SessionItem;
  session?: SessionState;
}

export interface SessionState {
  id: number;
  kind: "diagnostic" | "study" | "review";
  status: string;
  created_at: number;
  items: { id: number; concept_name: string; kind: string; done: number }[];
  answered: number;
  correct: number;
}

export interface AttemptResult {
  correct: boolean;
  answer_index: number;
  explanation: string;
  misconception: string | null;
  concept_id: number;
  p_known: number;
  attempts: number;
  in_srs: boolean;
}

export interface ReviewRow {
  concept_id: number;
  name: string;
  p_known: number;
  half_life: number;
  last_review_at: number | null;
  recall: number;
  risk: number;
  due: boolean;
  days_until_due: number;
}

export interface HistoryPoint {
  concept_id: number;
  name: string;
  p_known: number;
  created_at: number;
}

export interface Misconception {
  tag: string;
  count: number;
  concepts: number;
  concept_names: string[];
  last_seen: number;
}

export interface Delta {
  concept_id: number;
  name: string;
  before: number;
  after: number;
  delta: number;
  attempts: number;
}

export interface WeeklyReport {
  generated_at: number;
  window_days: number;
  summary: GoalSummary & {
    sessions: number;
    answered: number;
    correct: number;
    accuracy: number;
    improved: number;
  };
  deltas: Delta[];
  gaps: Gap[];
  misconceptions: Misconception[];
  review: ReviewRow[];
}

async function del(path: string): Promise<void> {
  const res = await fetch(`${API}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
}

export const learn = {
  goal: () => getJSON<GoalResponse>("/api/learn/goal"),
  createGoal: (name: string) => postJSON<{ goal: Goal }>("/api/learn/goal", { name }),
  deleteGoal: () => del("/api/learn/goal"),
  graph: () => getJSON<Graph>("/api/learn/graph"),
  gaps: () => getJSON<{ gaps: Gap[]; summary: GoalSummary }>("/api/learn/gaps"),
  startDiagnostic: () => postJSON<{ session_id: number }>("/api/learn/diagnostic", {}),
  startSession: (conceptId?: number) =>
    postJSON<{ session_id: number }>("/api/learn/session", {
      concept_id: conceptId ?? null,
    }),
  session: (id: number) => getJSON<SessionState>(`/api/learn/session/${id}`),
  next: (id: number) => getJSON<NextResponse>(`/api/learn/session/${id}/next`),
  markRead: (id: number, itemId: number) =>
    postJSON<{ ok: boolean }>(`/api/learn/session/${id}/read`, { item_id: itemId }),
  attempt: (body: {
    question_id: number;
    chosen_index: number;
    session_id?: number;
    latency_ms?: number;
  }) => postJSON<AttemptResult>("/api/learn/attempt", body),
  review: () =>
    getJSON<{ queue: ReviewRow[]; due: ReviewRow[]; threshold: number }>("/api/learn/review"),
  history: () => getJSON<{ points: HistoryPoint[] }>("/api/learn/history"),
  report: () => getJSON<WeeklyReport>("/api/learn/report/weekly"),
  ask: (conceptId: number, question: string) =>
    postJSON<{ answer: string; sources: { label: string }[] }>("/api/learn/ask", {
      concept_id: conceptId,
      question,
    }),
};

/** Mastery → an accent tint. One ramp shared by every chart and every list row.
 *  The floor sits at 25% rather than 0 so a weak concept is still visible against
 *  the light theme's pale panels, while the top stays clearly stronger. */
export function masteryFill(p: number, alpha = 1): string {
  const pct = Math.round(25 + Math.max(0, Math.min(1, p)) * 70);
  return `color-mix(in srgb, var(--accent) ${Math.round(pct * alpha)}%, transparent)`;
}

export function masteryLabel(p: number): string {
  if (p >= 0.85) return "MASTERED";
  if (p >= 0.6) return "SOLID";
  if (p >= 0.35) return "SHAKY";
  return "WEAK";
}

export const WEAK_THRESHOLD = 0.6;
export const MASTERED_THRESHOLD = 0.85;
