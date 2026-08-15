"use client";

import type { ReactNode } from "react";
import { DEFAULT_PLOT, innerBox, type Plot } from "./scale";

/** Axes, gridlines, and the empty state — shared by every chart so each chart
 *  file only draws its own marks. Colours come from Axiom tokens only. */
export default function ChartFrame({
  plot = DEFAULT_PLOT,
  yTicks = [],
  xTicks = [],
  formatY = (v: number) => String(v),
  empty = false,
  emptyLabel = "No data yet",
  height,
  children,
}: {
  plot?: Plot;
  yTicks?: { value: number; y: number }[];
  xTicks?: { label: string; x: number }[];
  formatY?: (value: number) => string;
  empty?: boolean;
  emptyLabel?: string;
  height?: number;
  children?: ReactNode;
}) {
  const box = innerBox(plot);

  if (empty) {
    return (
      <div
        style={{
          height: height ?? 240,
          display: "grid",
          placeItems: "center",
          color: "var(--faint)",
          fontFamily: "var(--font-jetbrains-mono), monospace",
          fontSize: 11,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
        }}
      >
        {emptyLabel}
      </div>
    );
  }

  return (
    <svg
      viewBox={`0 0 ${plot.width} ${plot.height}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: "100%", height: height ?? "auto", display: "block", overflow: "visible" }}
      role="img"
    >
      {yTicks.map((tick) => (
        <g key={`y-${tick.value}`}>
          <line
            x1={box.x0}
            x2={box.x1}
            y1={tick.y}
            y2={tick.y}
            stroke="var(--line)"
            strokeWidth={1}
          />
          <text
            x={box.x0 - 10}
            y={tick.y + 3.5}
            textAnchor="end"
            fill="var(--faint)"
            fontFamily="var(--font-jetbrains-mono), monospace"
            fontSize={9}
          >
            {formatY(tick.value)}
          </text>
        </g>
      ))}

      {xTicks.map((tick, index) => (
        <text
          key={`x-${tick.label}-${index}`}
          x={tick.x}
          y={box.y1 + 18}
          textAnchor="middle"
          fill="var(--faint)"
          fontFamily="var(--font-jetbrains-mono), monospace"
          fontSize={9}
        >
          {tick.label}
        </text>
      ))}

      <line x1={box.x0} x2={box.x1} y1={box.y1} y2={box.y1} stroke="var(--line2)" strokeWidth={1} />
      {children}
    </svg>
  );
}
