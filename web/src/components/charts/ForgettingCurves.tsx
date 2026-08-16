"use client";

import { useMemo, useState } from "react";
import type { ReviewRow } from "@/lib/learn";
import ChartFrame from "./ChartFrame";
import { DEFAULT_PLOT, clip, formatPercent, innerBox, linear, linePath } from "./scale";

const HORIZON_DAYS = 14;
const SAMPLES = 40;

/** Predicted recall decaying over the next fortnight. Where a curve crosses the
 *  threshold is exactly when that concept is scheduled for review. */
export default function ForgettingCurves({
  rows,
  threshold = 0.85,
  height = 260,
}: {
  rows: ReviewRow[];
  threshold?: number;
  height?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const plot = { ...DEFAULT_PLOT, height: 300 };
  const box = innerBox(plot);

  const x = (day: number) => linear(day, 0, HORIZON_DAYS, box.x0, box.x1);
  const y = (recall: number) => linear(recall, 0, 1, box.y1, box.y0);

  const curves = useMemo(
    () =>
      rows.slice(0, 10).map((row) => {
        // Recall is measured from now, so today's value is the row's current recall.
        const points = Array.from({ length: SAMPLES + 1 }, (_, index) => {
          const day = (index / SAMPLES) * HORIZON_DAYS;
          const recall = row.recall * 2 ** (-day / Math.max(0.05, row.half_life));
          return { x: x(day), y: y(recall) };
        });
        return { row, d: linePath(points), crossX: x(Math.min(row.days_until_due, HORIZON_DAYS)) };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rows],
  );

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((value) => ({ value, y: y(value) }));
  const xTicks = [0, 3, 7, 10, 14].map((day) => ({
    label: day === 0 ? "now" : `${day}d`,
    x: x(day),
  }));

  return (
    <ChartFrame
      plot={plot}
      height={height}
      yTicks={yTicks}
      xTicks={xTicks}
      formatY={(v) => formatPercent(v)}
      empty={curves.length === 0}
      emptyLabel="Master a concept to start the revision queue"
    >
      <g>
        <line
          x1={box.x0}
          x2={box.x1}
          y1={y(threshold)}
          y2={y(threshold)}
          stroke="var(--accent)"
          strokeOpacity={0.45}
          strokeDasharray="4 5"
        />
        <text
          x={box.x1}
          y={y(threshold) - 6}
          textAnchor="end"
          fill="var(--accent)"
          fontFamily="var(--font-jetbrains-mono), monospace"
          fontSize={9}
          opacity={0.7}
        >
          REVIEW THRESHOLD
        </text>

        {curves.map((curve, index) => {
          const active = hover === index;
          return (
            <g
              key={curve.row.concept_id}
              onMouseEnter={() => setHover(index)}
              onMouseLeave={() => setHover(null)}
            >
              <path
                d={curve.d}
                fill="none"
                stroke={curve.row.due ? "var(--warn)" : "var(--accent)"}
                strokeWidth={active ? 2.5 : 1.5}
                strokeOpacity={hover === null ? 0.7 : active ? 1 : 0.2}
                strokeLinecap="round"
                pathLength={1}
              className="chart-draw"
                style={{ animationDelay: `${index * 60}ms` }}
              />
              {/* Crossing marker: the scheduled review date. */}
              <circle
                cx={curve.crossX}
                cy={y(threshold)}
                r={active ? 4.5 : 3}
                fill={curve.row.due ? "var(--warn)" : "var(--accent)"}
                fillOpacity={hover === null ? 0.75 : active ? 1 : 0.2}
              />
              <path d={curve.d} fill="none" stroke="transparent" strokeWidth={14} />
            </g>
          );
        })}

        {hover !== null && curves[hover] ? (
          <text
            x={box.x0 + 6}
            y={box.y0 + 12}
            fill="var(--text)"
            fontFamily="var(--font-jetbrains-mono), monospace"
            fontSize={10}
          >
            {clip(curves[hover].row.name, 34).toUpperCase()} ·{" "}
            {curves[hover].row.due
              ? "DUE NOW"
              : `IN ${curves[hover].row.days_until_due.toFixed(1)}D`}
          </text>
        ) : null}
      </g>
    </ChartFrame>
  );
}
