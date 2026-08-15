"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarPlus, Plus, Trash2 } from "lucide-react";
import { Panel, MonoLabel, GlowButton, SectionHeader } from "@/components/ui";
import { API, getJSON, postJSON, type Task } from "@/lib/api";

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [label, setLabel] = useState("");
  const [due, setDue] = useState("");
  const [confirmCalendar, setConfirmCalendar] = useState(false);
  const [message, setMessage] = useState("");

  const refresh = useCallback(() => {
    getJSON<Task[]>("/api/tasks").then(setTasks).catch(() => {});
  }, []);

  useEffect(refresh, [refresh]);

  async function create(addToCalendar: boolean) {
    if (!label.trim()) return;
    try {
      const result = await postJSON<{ calendar_added: boolean }>("/api/tasks", {
        label: label.trim(),
        due: due || null,
        add_to_calendar: addToCalendar,
      });
      setLabel("");
      setDue("");
      setConfirmCalendar(false);
      setMessage(result.calendar_added ? "Task added to Google Calendar." : "Task added locally.");
      refresh();
    } catch {
      setMessage(
        addToCalendar
          ? "The task was saved locally, but could not be added to Google Calendar. Check the Calendar connection and date."
          : "Could not add the task.",
      );
    }
  }

  function add() {
    if (!label.trim()) return;
    if (due.trim()) setConfirmCalendar(true);
    else void create(false);
  }

  async function toggle(t: Task) {
    await fetch(`${API}/api/tasks/${t.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ done: !t.done }),
    });
    refresh();
  }

  async function remove(id: number) {
    await fetch(`${API}/api/tasks/${id}`, { method: "DELETE" });
    refresh();
  }

  const fieldStyle: React.CSSProperties = {
    background: "var(--panel2)",
    border: "1px solid var(--line)",
    color: "var(--text)",
    padding: "10px 12px",
    fontSize: 14,
    outline: "none",
  };

  return (
    <section className="axscreen" style={{ padding: 32, display: "flex", flexDirection: "column", gap: 22, maxWidth: 820 }}>
      <div>
        <MonoLabel size={11} spacing="0.24em" style={{ color: "var(--accent)", display: "block", marginBottom: 8 }}>
          FOCUS
        </MonoLabel>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 500 }}>Tasks</h1>
        <p style={{ margin: "8px 0 0", color: "var(--dim)", fontSize: 14 }}>
          Plan what matters, keep deadlines visible, and optionally add dated work to Google Calendar.
        </p>
      </div>

      <Panel>
        <SectionHeader title="Add a task" />
        <div style={{ padding: 18 }}>
          {message && (
            <p
              role="status"
              style={{ margin: "0 0 14px", fontSize: 13, color: "var(--accent)", border: "1px solid var(--line2)", padding: "8px 12px" }}
            >
              {message}
            </p>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 160px auto", gap: 8 }}>
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && add()}
              placeholder="Add a task…"
              style={fieldStyle}
            />
            <input
              value={due}
              onChange={(e) => setDue(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && add()}
              placeholder="Due (e.g. May 18)"
              style={fieldStyle}
            />
            <GlowButton onClick={add}>
              <Plus className="h-4 w-4" /> ADD
            </GlowButton>
          </div>
        </div>

        <div style={{ borderTop: "1px solid var(--line)" }}>
          {tasks.length === 0 && (
            <div style={{ padding: "36px 0", textAlign: "center" }}>
              <p style={{ margin: 0, fontSize: 14, fontWeight: 500 }}>Your list is clear</p>
              <MonoLabel size={10} spacing="0.14em" dim style={{ marginTop: 6, display: "block" }}>
                ADD THE NEXT USEFUL THING WHEN IT COMES UP
              </MonoLabel>
            </div>
          )}
          {tasks.map((t) => (
            <div
              key={t.id}
              style={{ display: "flex", alignItems: "center", gap: 16, padding: "15px 22px", borderBottom: "1px solid var(--line)" }}
            >
              <button
                onClick={() => toggle(t)}
                aria-label={t.done ? "Mark incomplete" : "Mark complete"}
                style={{
                  width: 16,
                  height: 16,
                  border: `1px solid ${t.done ? "var(--accent)" : "var(--line2)"}`,
                  background: t.done ? "var(--accent)" : "transparent",
                  flexShrink: 0,
                  display: "grid",
                  placeItems: "center",
                  color: "var(--bg)",
                  fontSize: 11,
                }}
              >
                {t.done ? "✓" : ""}
              </button>
              <span
                style={{
                  flex: 1,
                  fontSize: 14,
                  color: t.done ? "var(--faint)" : "var(--text)",
                  textDecoration: t.done ? "line-through" : "none",
                }}
              >
                {t.label}
              </span>
              {t.due && (
                <MonoLabel size={10} spacing="0.1em" dim>
                  {t.due}
                </MonoLabel>
              )}
              <button onClick={() => remove(t.id)} style={{ padding: 6, color: "var(--dim)" }} aria-label="Delete task">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      </Panel>

      {confirmCalendar && (
        <Panel accent style={{ padding: 20 }}>
          <p style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, fontWeight: 500, margin: 0 }}>
            <CalendarPlus className="h-4 w-4" style={{ color: "var(--accent)" }} /> Add this dated task to Google Calendar?
          </p>
          <p style={{ margin: "6px 0 0", fontSize: 13, color: "var(--dim)" }}>
            &ldquo;{label.trim()}&rdquo; is due {due.trim()}. Your choice is required before a calendar event is created.
          </p>
          <div style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 8 }}>
            <GlowButton onClick={() => void create(true)}>YES, ADD IT</GlowButton>
            <GlowButton variant="ghost" onClick={() => void create(false)}>
              NO, KEEP LOCAL
            </GlowButton>
            <button onClick={() => setConfirmCalendar(false)} style={{ padding: "0 8px", fontSize: 13, color: "var(--dim)" }}>
              Cancel
            </button>
          </div>
        </Panel>
      )}
    </section>
  );
}
