"use client";

import { useState } from "react";
import type { Delta } from "@/lib/learn";
import { clip, formatPercent, linear } from "./scale";

const WIDTH = 720;
const ROW_HEIGHT = 300;
const PAD = { top: 26, bottom: 30, left: 130, right: 130 };
const MIN_LABEL_GAP = 13;

/** Before → after, one line per concept. Upward slopes read as progress at a
 *  glance; flat lines are the concepts the week didn't touch. */
export default function SlopeChart({
  deltas,
  max = 12,
  height = 300,
}: {
  deltas: Delta[];
  max?: number;
  height?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const rows = deltas.filter((row) => row.attempts > 0).slice(0, max);

  if (rows.length === 0) {
    return (
      <div
        style={{
          height: 200,
          display: "grid",
          placeItems: "center",
          color: "var(--faint)",
          fontFamily: "var(--font-jetbrains-mono), monospace",
          fontSize: 11,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
        }}
      >
        Nothing practised this week
      </div>
    );
  }

  const y = (p: number) => linear(p, 0, 1, ROW_HEIGHT - PAD.bottom, PAD.top);
  const xLeft = PAD.left;
  const xRight = WIDTH - PAD.right;

  // Concepts that end up at similar mastery would otherwise stack their labels
  // on top of each other, so labels are nudged apart while the lines stay put.
  const labelY = (values: number[]): number[] => {
    const order = values.map((value, index) => ({ index, y: y(value) }));
    order.sort((a, b) => a.y - b.y);
    const out = new Array<number>(values.length);
    let previous = -Infinity;
    order.forEach((entry) => {
      const placed = Math.max(entry.y, previous + MIN_LABEL_GAP);
      out[entry.index] = placed;
      previous = placed;
    });
    return out;
  };

  const beforeLabels = labelY(rows.map((row) => row.before));
  const afterLabels = labelY(rows.map((row) => row.after));

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${ROW_HEIGHT}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: "100%", height, display: "block", overflow: "visible" }}
      role="img"
    >
      {[0, 0.5, 1].map((value) => (
        <line
          key={value}
          x1={xLeft}
          x2={xRight}
          y1={y(value)}
          y2={y(value)}
          stroke="var(--line)"
        />
      ))}

      <text
        x={xLeft}
        y={PAD.top - 12}
        textAnchor="middle"
        fill="var(--faint)"
        fontFamily="var(--font-jetbrains-mono), monospace"
        fontSize={9}
        letterSpacing="0.16em"
      >
        7 DAYS AGO
      </text>
      <text
        x={xRight}
        y={PAD.top - 12}
        textAnchor="middle"
        fill="var(--faint)"
        fontFamily="var(--font-jetbrains-mono), monospace"
        fontSize={9}
        letterSpacing="0.16em"
      >
        NOW
      </text>

      {rows.map((row, index) => {
        const rose = row.delta <= 0.01;
        const stroke = rose ? "var(--warn)" : "var(--accent)";
        const active = hover === index;
        const opacity = hover === null ? 0.8 : active ? 1 : 0.15;
        return (
          <g
            key={row.concept_id}
            onMouseEnter={() => setHover(index)}
            onMouseLeave={() => setHover(null)}
            style={{ cursor: "default" }}
          >
            <line
              x1={xLeft}
              x2={xRight}
              y1={y(row.before)}
              y2={y(row.after)}
              stroke={stroke}
              strokeWidth={active ? 2.5 : 1.5}
              strokeOpacity={opacity}
              pathLength={1}
              className="chart-draw"
              style={{ animationDelay: `${index * 45}ms` }}
            />
            <circle cx={xLeft} cy={y(row.before)} r={3} fill={stroke} fillOpacity={opacity} />
            <circle cx={xRight} cy={y(row.after)} r={3.5} fill={stroke} fillOpacity={opacity} />
            <text
              x={xLeft - 10}
              y={beforeLabels[index] + 3}
              textAnchor="end"
              fill={active ? "var(--text)" : "var(--dim)"}
              fontSize={10}
              opacity={opacity}
            >
              {clip(row.name, 18)}
            </text>
            <text
              x={xRight + 10}
              y={afterLabels[index] + 3}
              fill={active ? "var(--text)" : "var(--dim)"}
              fontFamily="var(--font-jetbrains-mono), monospace"
              fontSize={10}
              opacity={opacity}
            >
              {formatPercent(row.after)}
              {row.delta > 0.01 ? ` (+${Math.round(row.delta * 100)})` : ""}
            </text>
            <line x1={xLeft} x2={xRight} y1={y(row.before)} y2={y(row.after)} stroke="transparent" strokeWidth={12} />
          </g>
        );
      })}
    </svg>
  );
}
