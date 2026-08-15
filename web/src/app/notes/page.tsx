"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, FolderInput, Pencil, Play, Trash2, Upload, X } from "lucide-react";
import NoteMarkdown from "@/components/NoteMarkdown";
import NoteEditor from "@/components/NoteEditor";
import VideoModal from "@/components/VideoModal";
import { MonoLabel, GlowButton } from "@/components/ui";
import { API, getJSON, NotePreview, shortDate, Subject } from "@/lib/api";
import { cleanStudyMarkdown } from "@/lib/markdown";
import { NoteContext } from "@/lib/noteLinks";

interface VideoSeek {
  src: string;
  timestamp: number;
  label: string;
}

function noteContext(n: NotePreview): NoteContext {
  return { itemId: n.item_id, kind: n.kind, title: n.title ?? "Note", subjectName: n.subject };
}

interface NoteDetail {
  id: number;
  markdown: string;
}

interface ImportResult {
  imported: number;
  skipped: number;
}

export default function NotesPage() {
  const [notes, setNotes] = useState<NotePreview[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [active, setActive] = useState<number | null>(null);
  const [detail, setDetail] = useState<Record<number, string>>({});
  const [query, setQuery] = useState("");
  const [importing, setImporting] = useState(false);
  const [busyNote, setBusyNote] = useState<number | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [savingNote, setSavingNote] = useState(false);
  const [videoSeek, setVideoSeek] = useState<VideoSeek | null>(null);
  const [message, setMessage] = useState("");
  const importRef = useRef<HTMLInputElement>(null);
  const newFolderRef = useRef<HTMLInputElement>(null);

  const loadDetail = useCallback(
    async (id: number) => {
      const d = await getJSON<NoteDetail>(`/api/notes/${id}`);
      setDetail((prev) => ({ ...prev, [id]: d.markdown }));
    },
    [],
  );

  const refresh = useCallback(() => {
    Promise.all([
      getJSON<NotePreview[]>("/api/notes?limit=1000"),
      getJSON<Subject[]>("/api/subjects"),
    ])
      .then(async ([loaded, loadedSubjects]) => {
        setNotes(loaded);
        setSubjects(loadedSubjects);
        const requested = Number(new URLSearchParams(window.location.search).get("note"));
        const requestedNote = loaded.find((note) => note.id === requested);
        if (requested > 0 && requestedNote) {
          setActive(requested);
          const note = await getJSON<NoteDetail>(`/api/notes/${requested}`);
          setDetail((previous) => ({ ...previous, [requested]: note.markdown }));
        } else if (loaded.length > 0) {
          setActive((cur) => cur ?? loaded[0].id);
          loadDetail(loaded[0].id).catch(() => {});
        }
      })
      .catch(() => {});
  }, [loadDetail]);

  useEffect(refresh, [refresh]);

  function select(id: number) {
    setActive(id);
    setEditing(null);
    loadDetail(id).catch(() => {});
  }

  async function importBackup(file: File) {
    const form = new FormData();
    form.append("backup", file);
    setImporting(true);
    setMessage("");
    try {
      const res = await fetch(`${API}/api/notes/import`, { method: "POST", body: form });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? "Import failed");
      const result = body as ImportResult;
      setMessage(
        `Imported ${result.imported} note${result.imported === 1 ? "" : "s"}${
          result.skipped ? `; skipped ${result.skipped} already present or empty` : ""
        }.`,
      );
      refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Import failed");
    } finally {
      setImporting(false);
      if (importRef.current) importRef.current.value = "";
    }
  }

  async function createFolder() {
    const name = newFolderRef.current?.value.trim();
    if (!name) return;
    setMessage("");
    try {
      const res = await fetch(`${API}/api/subjects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? "Could not create folder");
      const subject = body as Subject;
      setSubjects((current) =>
        current.some((entry) => entry.id === subject.id)
          ? current
          : [...current, subject].sort((a, b) => a.name.localeCompare(b.name)),
      );
      if (newFolderRef.current) newFolderRef.current.value = "";
      setMessage(`Created "${subject.name}".`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not create folder");
    }
  }

  async function moveNote(note: NotePreview, subjectId: number) {
    const subject = subjects.find((entry) => entry.id === subjectId);
    if (!subject || note.subject_id === subjectId) return;
    setBusyNote(note.id);
    setMessage("");
    try {
      const res = await fetch(`${API}/api/notes/${note.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject_id: subjectId }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? "Could not move note");
      setNotes((current) =>
        current.map((entry) =>
          entry.id === note.id ? { ...entry, subject_id: subject.id, subject: subject.name } : entry,
        ),
      );
      setMessage(`Moved "${note.title ?? "Untitled"}" to ${subject.name}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not move note");
    } finally {
      setBusyNote(null);
    }
  }

  async function deleteNote(note: NotePreview) {
    if (
      !window.confirm(
        `Delete "${note.title ?? "Untitled"}"? The original uploaded material will stay in your Library.`,
      )
    )
      return;
    setBusyNote(note.id);
    setMessage("");
    try {
      const res = await fetch(`${API}/api/notes/${note.id}`, { method: "DELETE" });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? "Could not delete note");
      setNotes((current) => current.filter((entry) => entry.id !== note.id));
      setDetail((current) => {
        const next = { ...current };
        delete next[note.id];
        return next;
      });
      if (active === note.id) setActive(null);
      setMessage(`Deleted "${note.title ?? "Untitled"}".`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not delete note");
    } finally {
      setBusyNote(null);
    }
  }

  async function startEdit(note: NotePreview) {
    setActive(note.id);
    await loadDetail(note.id);
    setEditing(note.id);
  }

  async function saveNote(note: NotePreview, markdown: string) {
    setSavingNote(true);
    setMessage("");
    try {
      const res = await fetch(`${API}/api/notes/${note.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ markdown }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? "Could not save note");
      setDetail((prev) => ({ ...prev, [note.id]: body.markdown }));
      setEditing(null);
      setMessage(`Saved "${note.title ?? "Untitled"}".`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save note");
    } finally {
      setSavingNote(false);
    }
  }

  const q = query.trim().toLowerCase();
  const visible = q
    ? notes.filter(
        (n) =>
          (n.title ?? "").toLowerCase().includes(q) || n.preview.toLowerCase().includes(q),
      )
    : notes;
  const activeNote = notes.find((n) => n.id === active) ?? null;

  // NoteMarkdown is memoised, so these two props must keep a stable identity
  // across unrelated state changes or it re-parses the whole note every render.
  const activeCtx = useMemo(
    () => (activeNote ? noteContext(activeNote) : null),
    // noteContext is pure over these fields; activeNote's own identity is
    // stable while the notes list is unchanged.
    [activeNote],
  );

  const activeItemId = activeNote?.item_id;
  const activeTitle = activeNote?.title;
  const handleSeek = useCallback(
    (seconds: number) => {
      if (activeItemId === undefined) return;
      setVideoSeek({
        src: `${API}/api/video/items/${activeItemId}/file`,
        timestamp: seconds,
        label: activeTitle ?? "Lecture",
      });
    },
    [activeItemId, activeTitle],
  );

  return (
    <section className="axscreen" style={{ display: "flex", height: "calc(100vh - 60px)", minHeight: 0 }}>
      {/* List rail */}
      <div
        style={{
          width: 288,
          flexShrink: 0,
          borderRight: "1px solid var(--line)",
          background: "var(--panel)",
          backdropFilter: "var(--blur)",
          WebkitBackdropFilter: "var(--blur)",
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
        }}
      >
        <div style={{ padding: 16, borderBottom: "1px solid var(--line)", display: "flex", flexDirection: "column", gap: 10 }}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search notes…"
            style={{
              width: "100%",
              background: "var(--panel2)",
              border: "1px solid var(--line)",
              color: "var(--text)",
              padding: "8px 12px",
              fontFamily: "var(--font-jetbrains-mono), monospace",
              fontSize: 11,
              outline: "none",
            }}
          />
          <div style={{ display: "flex", gap: 8 }}>
            <a href={`${API}/api/notes/export`} style={{ flex: 1 }}>
              <GlowButton variant="ghost" style={{ width: "100%", padding: "7px 0", fontSize: 9 }}>
                <Download className="h-3.5 w-3.5" /> EXPORT
              </GlowButton>
            </a>
            <GlowButton
              variant="ghost"
              onClick={() => importRef.current?.click()}
              disabled={importing}
              style={{ flex: 1, padding: "7px 0", fontSize: 9 }}
            >
              <Upload className="h-3.5 w-3.5" /> {importing ? "…" : "IMPORT"}
            </GlowButton>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              createFolder();
            }}
            style={{ display: "flex", gap: 6 }}
          >
            <input
              ref={newFolderRef}
              placeholder="New folder…"
              maxLength={80}
              style={{
                flex: 1,
                minWidth: 0,
                background: "var(--panel2)",
                border: "1px solid var(--line)",
                color: "var(--text)",
                padding: "6px 10px",
                fontFamily: "var(--font-jetbrains-mono), monospace",
                fontSize: 10,
                outline: "none",
              }}
            />
            <button
              type="submit"
              aria-label="Create folder"
              style={{
                width: 30,
                border: "1px solid var(--accent)",
                color: "var(--accent)",
                display: "grid",
                placeItems: "center",
                fontSize: 15,
                background: "transparent",
              }}
            >
              +
            </button>
          </form>
          <input
            ref={importRef}
            type="file"
            accept="application/json,text/markdown,.json,.md,.markdown,.txt"
            hidden
            onChange={(event) => event.target.files?.[0] && importBackup(event.target.files[0])}
          />
        </div>
        <div style={{ overflowY: "auto", flex: 1, minHeight: 0 }}>
          {visible.length === 0 ? (
            <div style={{ padding: 16, fontSize: 12, color: "var(--dim)" }}>
              {notes.length === 0 ? "No notes yet — upload material on the Library page." : "No matches."}
            </div>
          ) : (
            visible.map((n) => {
              const on = n.id === active;
              return (
                <button
                  key={n.id}
                  onClick={() => select(n.id)}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "14px 16px",
                    borderBottom: "1px solid var(--line)",
                    borderLeft: `2px solid ${on ? "var(--accent)" : "transparent"}`,
                    background: on ? "var(--panel2)" : "transparent",
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 5, color: "var(--text)" }}>
                    {n.title ?? "Untitled"}
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: "var(--dim)",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {cleanStudyMarkdown(n.preview)}
                  </div>
                  <MonoLabel size={9} spacing="0.14em" dim style={{ marginTop: 7, display: "block" }}>
                    {(n.subject ?? "UNFILED").toUpperCase()} · {shortDate(n.created_at).toUpperCase()}
                  </MonoLabel>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Reader */}
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", minHeight: 0 }}>
        {message && (
          <p
            role="status"
            style={{ margin: 0, padding: "10px 40px", borderBottom: "1px solid var(--line)", fontSize: 13, color: "var(--dim)" }}
          >
            {message}
          </p>
        )}
        {!activeNote ? (
          <div style={{ padding: 40, color: "var(--dim)", fontSize: 14 }}>Select a note to read it.</div>
        ) : (
          <>
            <div style={{ padding: "28px 40px 0" }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
                <div>
                  <MonoLabel size={10} spacing="0.22em" style={{ color: "var(--accent)", display: "block", marginBottom: 10 }}>
                    {(activeNote.subject ?? "UNFILED").toUpperCase()} · {shortDate(activeNote.created_at).toUpperCase()}
                  </MonoLabel>
                  <h1 style={{ margin: "0 0 6px", fontSize: 26, fontWeight: 500 }}>{activeNote.title ?? "Untitled"}</h1>
                </div>
                {/* Actions */}
                <div style={{ display: "flex", alignItems: "center", gap: 2, flexShrink: 0 }}>
                  {editing === activeNote.id ? (
                    <button
                      onClick={() => setEditing(null)}
                      style={{ padding: 8, color: "var(--dim)" }}
                      aria-label="Cancel edit"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  ) : (
                    <button
                      onClick={() => startEdit(activeNote)}
                      disabled={busyNote === activeNote.id}
                      style={{ padding: 8, color: "var(--dim)" }}
                      aria-label="Edit note"
                      title="Edit"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                  )}
                  <label
                    style={{ position: "relative", display: "flex", alignItems: "center", color: "var(--dim)" }}
                    title="Move to folder"
                  >
                    <FolderInput className="pointer-events-none absolute left-2 h-4 w-4" />
                    <select
                      value=""
                      onChange={(e) => moveNote(activeNote, Number(e.target.value))}
                      disabled={busyNote === activeNote.id}
                      aria-label="Move note to folder"
                      style={{
                        appearance: "none",
                        background: "transparent",
                        border: "none",
                        color: "var(--dim)",
                        paddingLeft: 28,
                        paddingRight: 8,
                        height: 32,
                        fontSize: 12,
                        outline: "none",
                        cursor: "pointer",
                      }}
                    >
                      <option value="" disabled>
                        Move…
                      </option>
                      {subjects.map((subject) => (
                        <option key={subject.id} value={subject.id} disabled={subject.id === activeNote.subject_id}>
                          {subject.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <a
                    href={`${API}/api/notes/${activeNote.id}/download`}
                    style={{ padding: 8, color: "var(--dim)" }}
                    aria-label="Download as PDF"
                    title="Download PDF"
                  >
                    <Download className="h-4 w-4" />
                  </a>
                  <button
                    onClick={() => deleteNote(activeNote)}
                    disabled={busyNote === activeNote.id}
                    style={{ padding: 8, color: "var(--dim)" }}
                    aria-label="Delete note"
                    title="Delete"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
              {activeNote.subject ? (
                <div style={{ display: "flex", gap: 8, margin: "12px 0 20px" }}>
                  <MonoLabel size={10} spacing="0.12em" style={{ border: "1px solid var(--line2)", padding: "4px 10px" }}>
                    {activeNote.subject.toUpperCase()}
                  </MonoLabel>
                </div>
              ) : (
                <div style={{ height: 20 }} />
              )}
              <div style={{ height: 1, background: "var(--line)" }} />
            </div>

            <div style={{ padding: "24px 40px 48px", overflow: "auto", flex: 1, minHeight: 0 }}>
              {activeNote.kind === "video" && editing !== activeNote.id && (
                <div className="not-prose" style={{ marginBottom: 20, background: "#000", padding: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 8px 8px", color: "#fff", fontSize: 13 }}>
                    <Play className="h-4 w-4" /> Lecture video
                  </div>
                  <video
                    controls
                    style={{ maxHeight: "65vh", width: "100%" }}
                    src={`${API}/api/video/items/${activeNote.item_id}/file`}
                  />
                </div>
              )}
              {detail[activeNote.id] ? (
                editing === activeNote.id ? (
                  <NoteEditor
                    initialMarkdown={detail[activeNote.id]}
                    ctx={activeCtx ?? noteContext(activeNote)}
                    saving={savingNote}
                    onSave={(markdown) => saveNote(activeNote, markdown)}
                    onCancel={() => setEditing(null)}
                  />
                ) : (
                  <article className="study-note" style={{ maxWidth: 760 }}>
                    {activeCtx && (
                      <NoteMarkdown
                        markdown={detail[activeNote.id]}
                        ctx={activeCtx}
                        onSeek={handleSeek}
                      />
                    )}
                  </article>
                )
              ) : (
                <div className="note-loading" style={{ maxWidth: 760 }} aria-label="Loading note" role="status">
                  <span />
                  <span />
                  <span />
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {videoSeek && (
        <VideoModal
          src={videoSeek.src}
          timestamp={videoSeek.timestamp}
          label={videoSeek.label}
          onClose={() => setVideoSeek(null)}
        />
      )}
    </section>
  );
}
