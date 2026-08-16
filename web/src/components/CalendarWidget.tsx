"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { MonoLabel } from "@/components/ui";

const DAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

export interface GoogleCalendarEvent {
  id: string;
  summary: string;
  description: string;
  location: string;
  start: string;
  end: string;
  all_day: boolean;
  html_link: string | null;
}

function dateKey(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export default function CalendarWidget({
  month,
  events = [],
  onMonthChange,
}: {
  month?: Date;
  events?: GoogleCalendarEvent[];
  onMonthChange?: (month: Date) => void;
} = {}) {
  const now = new Date();
  const [localMonth, setLocalMonth] = useState(new Date(now.getFullYear(), now.getMonth(), 1));
  const visibleMonth = month ?? localMonth;
  const changeMonth = onMonthChange ?? setLocalMonth;
  const first = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), 1);
  const last = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 0);
  const gridStart = new Date(first);
  gridStart.setDate(first.getDate() - first.getDay());
  const gridEnd = new Date(last);
  gridEnd.setDate(last.getDate() + (6 - last.getDay()));

  const cells: Date[] = [];
  for (const cursor = new Date(gridStart); cursor <= gridEnd; cursor.setDate(cursor.getDate() + 1)) {
    cells.push(new Date(cursor));
  }
  const eventCounts = events.reduce<Record<string, number>>((counts, event) => {
    const key = event.all_day ? event.start.slice(0, 10) : dateKey(new Date(event.start));
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});

  return (
    <div style={{ border: "1px solid var(--line)", background: "var(--panel)", backdropFilter: "var(--blur)", WebkitBackdropFilter: "var(--blur)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: "1px solid var(--line)" }}>
        <MonoLabel size={12} spacing="0.16em">
          {visibleMonth.toLocaleDateString("en-US", { month: "long", year: "numeric" }).toUpperCase()}
        </MonoLabel>
        <div style={{ display: "flex", gap: 4 }}>
          <button
            onClick={() => changeMonth(new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() - 1, 1))}
            style={{ padding: 6, color: "var(--dim)" }}
            aria-label="Previous month"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            onClick={() => changeMonth(new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 1))}
            style={{ padding: 6, color: "var(--dim)" }}
            aria-label="Next month"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 1, background: "var(--line)", borderTop: "1px solid var(--line)" }}>
        {DAYS.map((day, index) => (
          <div key={index} style={{ background: "var(--panel)", padding: "8px 0", textAlign: "center" }}>
            <MonoLabel size={9} spacing="0.12em" dim>
              {day}
            </MonoLabel>
          </div>
        ))}
        {cells.map((cell) => {
          const current = cell.getMonth() === visibleMonth.getMonth();
          const today = dateKey(cell) === dateKey(now);
          const count = eventCounts[dateKey(cell)] ?? 0;
          return (
            <div
              key={dateKey(cell)}
              title={count ? `${count} Google Calendar event${count === 1 ? "" : "s"}` : undefined}
              style={{
                background: today ? "var(--panel2)" : "var(--panel)",
                minHeight: 56,
                padding: 8,
                borderLeft: today ? "2px solid var(--accent)" : "2px solid transparent",
                position: "relative",
              }}
            >
              <span
                style={{
                  fontFamily: "var(--font-jetbrains-mono), monospace",
                  fontSize: 12,
                  color: today ? "var(--accent)" : current ? "var(--text)" : "var(--faint)",
                }}
              >
                {String(cell.getDate()).padStart(2, "0")}
              </span>
              {count > 0 && (
                <span
                  style={{
                    position: "absolute",
                    bottom: 8,
                    right: 8,
                    width: 5,
                    height: 5,
                    borderRadius: "50%",
                    background: "var(--accent)",
                  }}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
