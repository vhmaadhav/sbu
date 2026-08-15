"use client";

import { useState } from "react";
import type { Misconception } from "@/lib/learn";
import { clip } from "./scale";

/** How often each error pattern repeats. Bars are horizontal because the labels
 *  are sentences, not categories. */
export default function MisconceptionBars({ rows }: { rows: Misconception[] }) {
  const [open, setOpen] = useState<string | null>(null);

  if (rows.length === 0) {
    return (
      <div
        style={{
          padding: "36px 22px",
          textAlign: "center",
          color: "var(--faint)",
          fontFamily: "var(--font-jetbrains-mono), monospace",
          fontSize: 11,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
        }}
      >
        No repeated errors yet
      </div>
    );
  }

  const max = Math.max(...rows.map((row) => row.count));

  return (
    <div style={{ padding: "6px 0" }}>
      {rows.map((row, index) => {
        const expanded = open === row.tag;
        return (
          <div key={row.tag} style={{ borderBottom: "1px solid var(--line)" }}>
            <button
              type="button"
              onClick={() => setOpen(expanded ? null : row.tag)}
              className="gap-row"
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "12px 22px",
                background: "transparent",
                cursor: "pointer",
                animationDelay: `${index * 40}ms`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 12,
                  marginBottom: 7,
                }}
              >
                <span style={{ fontSize: 13, color: "var(--text)" }}>{clip(row.tag, 52)}</span>
                <span
                  style={{
                    fontFamily: "var(--font-jetbrains-mono), monospace",
                    fontSize: 11,
                    color: "var(--warn)",
                  }}
                >
                  ×{row.count}
                </span>
              </div>
              <div style={{ height: 5, background: "var(--panel2)" }}>
                <div
                  className="bar-grow"
                  style={{
                    height: "100%",
                    width: `${Math.max(4, (row.count / max) * 100)}%`,
                    background: "var(--warn)",
                    animationDelay: `${index * 40}ms`,
                  }}
                />
              </div>
            </button>
            {expanded ? (
              <div
                className="reveal"
                style={{ padding: "0 22px 14px", fontSize: 11, color: "var(--faint)" }}
              >
                Seen across {row.concepts} concept{row.concepts === 1 ? "" : "s"}:{" "}
                {row.concept_names.filter(Boolean).join(", ")}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
