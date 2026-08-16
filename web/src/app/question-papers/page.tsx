"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, Eye, EyeOff, FilePlus2, Loader2, Trash2 } from "lucide-react";
import { API, getJSON, NotePreview } from "@/lib/api";
import { GlowButton, MonoLabel, Panel, SectionHeader } from "@/components/ui";

interface Source {
  note_id: number;
  title: string;
  subject: string | null;
}

interface PaperSummary {
  id: number;
  title: string;
  difficulty: "easy" | "medium" | "hard";
  duration_minutes: number;
  total_marks: number;
  question_count: number;
  sources: Source[];
  created_at: number;
}

interface Question {
  id: number;
  type: "mcq" | "short" | "long";
  prompt: string;
  options: string[];
  answer: string;
  explanation: string;
  marks: number;
  position: number;
}

interface Paper extends PaperSummary {
  instructions: string;
  questions: Question[];
}

interface GenerationJob {
  id: number;
  status: "processing" | "done" | "error";
  paper_id: number | null;
  error: string | null;
}

const TYPE_LABELS = { mcq: "MCQ", short: "SHORT ANSWER", long: "LONG ANSWER" };

function NumberField({
  label,
  value,
  onChange,
  min = 0,
  max = 30,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
}) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <MonoLabel size={9} spacing="0.12em" dim>{label}</MonoLabel>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Math.max(min, Math.min(max, Number(event.target.value) || 0)))}
        style={{ border: "1px solid var(--line2)", background: "var(--panel2)", padding: "9px 10px", color: "var(--text)", width: "100%" }}
      />
    </label>
  );
}

export default function QuestionPapersPage() {
  const [notes, setNotes] = useState<NotePreview[]>([]);
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [paper, setPaper] = useState<Paper | null>(null);
  const [picked, setPicked] = useState<number[]>([]);
  const [title, setTitle] = useState("");
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard">("medium");
  const [duration, setDuration] = useState(60);
  const [mcqCount, setMcqCount] = useState(10);
  const [shortCount, setShortCount] = useState(5);
  const [longCount, setLongCount] = useState(2);
  const [showAnswers, setShowAnswers] = useState(false);
  const [busy, setBusy] = useState(false);
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const [error, setError] = useState("");

  const loadPaper = useCallback(async (paperId: number) => {
    const detail = await getJSON<Paper>(`/api/question-papers/${paperId}`);
    setPaper(detail);
    setShowAnswers(false);
  }, []);

  const refresh = useCallback(async (selectFirst = false) => {
    const [nextNotes, nextPapers] = await Promise.all([
      getJSON<NotePreview[]>("/api/notes?limit=200"),
      getJSON<PaperSummary[]>("/api/question-papers"),
    ]);
    setNotes(nextNotes);
    setPapers(nextPapers);
    if (selectFirst && nextPapers.length) await loadPaper(nextPapers[0].id);
  }, [loadPaper]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getJSON<NotePreview[]>("/api/notes?limit=200"),
      getJSON<PaperSummary[]>("/api/question-papers"),
      getJSON<GenerationJob[]>("/api/question-papers/jobs"),
    ]).then(async ([nextNotes, nextPapers, jobs]) => {
      if (cancelled) return;
      setNotes(nextNotes);
      setPapers(nextPapers);
      const processing = jobs.find((job) => job.status === "processing");
      if (processing) setActiveJobId(processing.id);
      if (nextPapers.length) {
        const detail = await getJSON<Paper>(`/api/question-papers/${nextPapers[0].id}`);
        if (!cancelled) setPaper(detail);
      }
    }).catch(() => {
      if (!cancelled) setError("Could not reach the question paper service.");
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (activeJobId === null) return;
    const poll = async () => {
      try {
        const jobs = await getJSON<GenerationJob[]>("/api/question-papers/jobs");
        const job = jobs.find((candidate) => candidate.id === activeJobId);
        if (!job || job.status === "processing") return;
        if (job.status === "error") {
          setError(job.error || "Question paper generation failed.");
          setActiveJobId(null);
          return;
        }
        if (job.paper_id !== null) {
          const [created, nextPapers] = await Promise.all([
            getJSON<Paper>(`/api/question-papers/${job.paper_id}`),
            getJSON<PaperSummary[]>("/api/question-papers"),
          ]);
          setPaper(created);
          setPapers(nextPapers);
          setShowAnswers(false);
          setTitle("");
        }
        setActiveJobId(null);
      } catch {
        setError("Could not check question paper generation progress.");
      }
    };
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 2500);
    return () => window.clearInterval(timer);
  }, [activeJobId]);

  const questionCount = mcqCount + shortCount + longCount;
  const totalMarks = mcqCount + shortCount * 3 + longCount * 5;
  const generating = busy || activeJobId !== null;
  const selectedTitles = useMemo(
    () => notes.filter((note) => picked.includes(note.id)).map((note) => note.title ?? "Untitled"),
    [notes, picked],
  );

  async function generate() {
    if (!picked.length || questionCount < 1) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${API}/api/question-papers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          note_ids: picked,
          title,
          difficulty,
          duration_minutes: duration,
          mcq_count: mcqCount,
          short_count: shortCount,
          long_count: longCount,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "Question paper generation failed.");
      }
      const job = await response.json() as { job_id: number; status: "processing" };
      setActiveJobId(job.job_id);
    } catch (generationError) {
      setError(generationError instanceof Error ? generationError.message : "Question paper generation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function removePaper() {
    if (!paper || !window.confirm(`Delete "${paper.title}" and its answer key?`)) return;
    setBusy(true);
    try {
      const response = await fetch(`${API}/api/question-papers/${paper.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error();
      setPaper(null);
      await refresh(true);
    } catch {
      setError("Could not delete this question paper.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="axscreen" style={{ padding: 32, display: "flex", flexDirection: "column", gap: 24, maxWidth: 1180 }}>
      <div>
        <MonoLabel size={11} spacing="0.24em" style={{ color: "var(--accent)", display: "block", marginBottom: 8 }}>
          ASSESSMENT BUILDER
        </MonoLabel>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 500 }}>Question papers</h1>
        <p style={{ margin: "8px 0 0", color: "var(--dim)", fontSize: 14 }}>
          Generate grounded assessments and answer keys from selected notes.
        </p>
      </div>

      {error && (
        <p role="alert" style={{ margin: 0, border: "1px solid #f87171", color: "#f87171", padding: "10px 14px", fontSize: 13 }}>
          {error}
        </p>
      )}

      <Panel>
        <SectionHeader title="Build a paper" />
        <div style={{ padding: 18, display: "grid", gridTemplateColumns: "minmax(260px, 1.2fr) minmax(260px, 1fr)", gap: 24 }}>
          <div>
            <MonoLabel size={10} spacing="0.14em" style={{ display: "block", marginBottom: 10 }}>SOURCE NOTES</MonoLabel>
            {notes.length === 0 ? (
              <p style={{ color: "var(--dim)", fontSize: 13 }}>Create or upload notes before generating a paper.</p>
            ) : (
              <div style={{ maxHeight: 250, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8 }}>
                {notes.map((note) => {
                  const selected = picked.includes(note.id);
                  return (
                    <button
                      type="button"
                      key={note.id}
                      onClick={() => setPicked((current) => selected ? current.filter((id) => id !== note.id) : [...current, note.id])}
                      style={{
                        display: "flex", alignItems: "center", gap: 10, padding: "9px 10px",
                        border: `1px solid ${selected ? "var(--accent)" : "var(--line)"}`,
                        background: selected ? "var(--panel2)" : "transparent", textAlign: "left",
                      }}
                    >
                      <span style={{
                        width: 15, height: 15, border: `1px solid ${selected ? "var(--accent)" : "var(--line2)"}`,
                        background: selected ? "var(--accent)" : "transparent", color: "var(--bg)",
                        display: "grid", placeItems: "center", fontSize: 10, flexShrink: 0,
                      }}>{selected ? "✓" : ""}</span>
                      <span style={{ flex: 1, minWidth: 0, color: "var(--text)", fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {note.title ?? "Untitled"}
                      </span>
                      {note.subject && <MonoLabel size={8} dim>{note.subject.toUpperCase()}</MonoLabel>}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <MonoLabel size={9} spacing="0.12em" dim>TITLE (OPTIONAL)</MonoLabel>
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder={selectedTitles[0] ? `${selectedTitles[0]} assessment` : "Generated from note titles"}
                maxLength={180}
                style={{ border: "1px solid var(--line2)", background: "var(--panel2)", padding: "9px 10px", color: "var(--text)" }}
              />
            </label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <MonoLabel size={9} spacing="0.12em" dim>DIFFICULTY</MonoLabel>
                <select
                  value={difficulty}
                  onChange={(event) => setDifficulty(event.target.value as typeof difficulty)}
                  style={{ border: "1px solid var(--line2)", background: "var(--panel2)", padding: "9px 10px", color: "var(--text)" }}
                >
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </label>
              <NumberField label="DURATION (MIN)" value={duration} onChange={setDuration} min={15} max={300} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
              <NumberField label="MCQ · 1 MARK" value={mcqCount} onChange={setMcqCount} />
              <NumberField label="SHORT · 3 MARKS" value={shortCount} onChange={setShortCount} />
              <NumberField label="LONG · 5 MARKS" value={longCount} onChange={setLongCount} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "var(--dim)", fontSize: 12 }}>
              <span>{questionCount} questions</span>
              <span>{totalMarks} marks</span>
            </div>
            <GlowButton onClick={() => void generate()} disabled={generating || !picked.length || questionCount < 1 || questionCount > 30}>
              {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <FilePlus2 className="h-4 w-4" />}
              {generating ? "GENERATING IN BACKGROUND…" : "GENERATE QUESTION PAPER"}
            </GlowButton>
            {activeJobId !== null && (
              <span role="status" style={{ color: "var(--dim)", fontSize: 11, lineHeight: 1.5 }}>
                You can leave this page. The paper will be saved when the local model finishes.
              </span>
            )}
            {questionCount > 30 && <span style={{ color: "#f87171", fontSize: 11 }}>Maximum 30 questions per paper.</span>}
          </div>
        </div>
      </Panel>

      <div style={{ display: "grid", gridTemplateColumns: "260px minmax(0, 1fr)", gap: 20, alignItems: "start" }}>
        <Panel>
          <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--line)" }}><MonoLabel>SAVED PAPERS</MonoLabel></div>
          {papers.length === 0 && <p style={{ padding: 16, color: "var(--dim)", fontSize: 13 }}>No papers generated yet.</p>}
          {papers.map((saved) => (
            <button
              type="button"
              key={saved.id}
              onClick={() => void loadPaper(saved.id)}
              style={{
                display: "block", width: "100%", padding: "13px 16px", textAlign: "left",
                borderBottom: "1px solid var(--line)",
                borderLeft: `2px solid ${paper?.id === saved.id ? "var(--accent)" : "transparent"}`,
                background: paper?.id === saved.id ? "var(--panel2)" : "transparent",
              }}
            >
              <span style={{ display: "block", color: "var(--text)", fontSize: 13, fontWeight: 500 }}>{saved.title}</span>
              <MonoLabel size={8} spacing="0.1em" dim style={{ display: "block", marginTop: 4 }}>
                {saved.question_count} QUESTIONS · {saved.total_marks} MARKS
              </MonoLabel>
            </button>
          ))}
        </Panel>

        <Panel>
          {!paper ? (
            <p style={{ padding: 24, color: "var(--dim)", fontSize: 13 }}>Generate or select a question paper.</p>
          ) : (
            <>
              <div style={{ padding: 18, borderBottom: "1px solid var(--line)", display: "flex", flexWrap: "wrap", alignItems: "flex-start", justifyContent: "space-between", gap: 14 }}>
                <div>
                  <MonoLabel size={9} spacing="0.12em" style={{ color: "var(--accent)" }}>{paper.difficulty.toUpperCase()} · {paper.duration_minutes} MINUTES</MonoLabel>
                  <h2 style={{ margin: "6px 0 0", fontSize: 20, fontWeight: 500 }}>{paper.title}</h2>
                  <p style={{ margin: "6px 0 0", color: "var(--dim)", fontSize: 12 }}>{paper.instructions}</p>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <GlowButton variant="ghost" onClick={() => setShowAnswers((current) => !current)} style={{ padding: "8px 10px" }}>
                    {showAnswers ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    {showAnswers ? "HIDE KEY" : "SHOW KEY"}
                  </GlowButton>
                  <a href={`${API}/api/question-papers/${paper.id}/download`}>
                    <GlowButton variant="ghost" style={{ padding: "8px 10px" }}><Download className="h-4 w-4" /> PAPER</GlowButton>
                  </a>
                  <a href={`${API}/api/question-papers/${paper.id}/download?answers=true`}>
                    <GlowButton variant="ghost" style={{ padding: "8px 10px" }}><Download className="h-4 w-4" /> KEY</GlowButton>
                  </a>
                  <button onClick={() => void removePaper()} disabled={busy} aria-label="Delete question paper" style={{ color: "var(--dim)", padding: 8 }}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <div style={{ padding: 22, display: "flex", flexDirection: "column", gap: 22 }}>
                {paper.questions.map((question, index) => (
                  <article key={question.id}>
                    <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                      <span style={{ color: "var(--accent)", fontFamily: "var(--font-jetbrains-mono), monospace", fontSize: 12 }}>{String(index + 1).padStart(2, "0")}</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55 }}>{question.prompt}</p>
                          <MonoLabel size={8} spacing="0.08em" dim style={{ whiteSpace: "nowrap" }}>{TYPE_LABELS[question.type]} · {question.marks}M</MonoLabel>
                        </div>
                        {question.options.length > 0 && (
                          <ol type="A" style={{ margin: "10px 0 0", paddingLeft: 28, color: "var(--dim)", fontSize: 13, lineHeight: 1.8 }}>
                            {question.options.map((option) => <li key={option}>{option}</li>)}
                          </ol>
                        )}
                        {showAnswers && (
                          <div style={{ marginTop: 12, padding: "10px 12px", borderLeft: "2px solid var(--accent)", background: "var(--panel2)", fontSize: 13 }}>
                            <strong style={{ color: "var(--accent)" }}>Answer: </strong>{question.answer}
                            {question.explanation && <p style={{ margin: "6px 0 0", color: "var(--dim)", lineHeight: 1.5 }}>{question.explanation}</p>}
                          </div>
                        )}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
              <div style={{ padding: "12px 18px", borderTop: "1px solid var(--line)", color: "var(--dim)", fontSize: 11 }}>
                Grounded in {paper.sources.map((source) => source.title).join(", ")}
              </div>
            </>
          )}
        </Panel>
      </div>
    </section>
  );
}
