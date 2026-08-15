"use client";

import { masteryFill, type Gap } from "@/lib/learn";
import { clip, formatPercent } from "./scale";

/** Ranked mastery bars. The confidence band sits behind the fill, so a concept
 *  that is genuinely weak looks different from one that is barely tested. */
export default function WeakAreaBars({
  gaps,
  onSelect,
  max = 10,
}: {
  gaps: Gap[];
  onSelect?: (gap: Gap) => void;
  max?: number;
}) {
  const rows = gaps.slice(0, max);

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
        No gaps found — run a diagnostic
      </div>
    );
  }

  return (
    <div>
      {rows.map((gap, index) => (
        <button
          key={gap.concept_id}
          type="button"
          onClick={() => onSelect?.(gap)}
          className="gap-row"
          style={{
            display: "block",
            width: "100%",
            textAlign: "left",
            padding: "14px 22px",
            borderBottom: "1px solid var(--line)",
            background: "transparent",
            cursor: onSelect ? "pointer" : "default",
            animationDelay: `${index * 40}ms`,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              gap: 12,
              marginBottom: 8,
            }}
          >
            <span style={{ fontSize: 14, color: "var(--text)" }}>{clip(gap.name, 46)}</span>
            <span
              style={{
                fontFamily: "var(--font-jetbrains-mono), monospace",
                fontSize: 11,
                color: gap.missing_prerequisite ? "var(--accent)" : "var(--dim)",
              }}
            >
              {formatPercent(gap.p_known)}
            </span>
          </div>

          {/* Track → confidence band → mastery fill, drawn back to front. */}
          <div style={{ position: "relative", height: 6, background: "var(--panel2)" }}>
            <div
              style={{
                position: "absolute",
                inset: 0,
                width: `${Math.max(2, gap.confidence * 100)}%`,
                background: "color-mix(in srgb, var(--accent) 12%, transparent)",
              }}
            />
            <div
              className="bar-grow"
              style={{
                position: "absolute",
                inset: 0,
                width: `${Math.max(2, gap.p_known * 100)}%`,
                background: masteryFill(gap.p_known),
                animationDelay: `${index * 40}ms`,
              }}
            />
          </div>

          <div
            style={{
              marginTop: 8,
              display: "flex",
              gap: 10,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <span
              style={{
                fontFamily: "var(--font-jetbrains-mono), monospace",
                fontSize: 9,
                letterSpacing: "0.16em",
                textTransform: "uppercase",
                padding: "3px 7px",
                border: `1px solid ${
                  gap.missing_prerequisite ? "var(--accent)" : "var(--line2)"
                }`,
                color: gap.missing_prerequisite ? "var(--accent)" : "var(--dim)",
              }}
            >
              {gap.missing_prerequisite ? "Foundation" : `Tier ${gap.tier}`}
            </span>
            <span style={{ fontSize: 11, color: "var(--faint)" }}>{gap.reason}</span>
            {gap.downstream > 0 ? (
              <span style={{ fontSize: 11, color: "var(--faint)" }}>
                · unlocks {gap.downstream}
              </span>
            ) : null}
          </div>
        </button>
      ))}
    </div>
  );
}
