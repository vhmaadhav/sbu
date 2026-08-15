"use client";

import { useMemo, useState } from "react";
import type { HistoryPoint } from "@/lib/learn";
import ChartFrame from "./ChartFrame";
import { DEFAULT_PLOT, formatDay, formatPercent, innerBox, linear, linePath } from "./scale";

/** The learning curve: overall mastery bold, individual concepts faint behind it. */
export default function MasteryCurve({
  points,
  height = 260,
}: {
  points: HistoryPoint[];
  height?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const plot = { ...DEFAULT_PLOT, height: 300 };
  const box = innerBox(plot);

  const model = useMemo(() => {
    if (points.length === 0) return null;
    const sorted = [...points].sort((a, b) => a.created_at - b.created_at);
    const tMin = sorted[0].created_at;
    const tMax = sorted[sorted.length - 1].created_at;
    const span = tMax - tMin || 1;

    const x = (t: number) => linear(t, tMin, tMin + span, box.x0, box.x1);
    const y = (p: number) => linear(p, 0, 1, box.y1, box.y0);

    // Per-concept series.
    const byConcept = new Map<number, HistoryPoint[]>();
    sorted.forEach((point) => {
      const list = byConcept.get(point.concept_id) ?? [];
      list.push(point);
      byConcept.set(point.concept_id, list);
    });

    const series = [...byConcept.entries()].map(([id, list]) => ({
      id,
      name: list[0].name,
      d: linePath(list.map((p) => ({ x: x(p.created_at), y: y(p.p_known) }))),
    }));

    // Overall = running mean across every concept seen so far.
    const latest = new Map<number, number>();
    const overallPoints = sorted.map((point) => {
      latest.set(point.concept_id, point.p_known);
      const values = [...latest.values()];
      const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
      return { t: point.created_at, value: mean };
    });

    const overall = linePath(overallPoints.map((p) => ({ x: x(p.t), y: y(p.value) })));

    return {
      series,
      overall,
      overallPoints: overallPoints.map((p) => ({ ...p, cx: x(p.t), cy: y(p.value) })),
      tMin,
      tMax,
      x,
      y,
    };
  }, [points, box.x0, box.x1, box.y0, box.y1]);

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((value) => ({
    value,
    y: linear(value, 0, 1, box.y1, box.y0),
  }));

  const xTicks = model
    ? [model.tMin, (model.tMin + model.tMax) / 2, model.tMax].map((t) => ({
        label: formatDay(t),
        x: model.x(t),
      }))
    : [];

  const hovered = hover !== null && model ? model.overallPoints[hover] : null;

  return (
    <ChartFrame
      plot={plot}
      height={height}
      yTicks={yTicks}
      xTicks={xTicks}
      formatY={(v) => formatPercent(v)}
      empty={!model}
      emptyLabel="Answer a few questions to start the curve"
    >
      {model ? (
        <g>
          {/* Mastery threshold */}
          <line
            x1={box.x0}
            x2={box.x1}
            y1={model.y(0.85)}
            y2={model.y(0.85)}
            stroke="var(--accent)"
            strokeOpacity={0.35}
            strokeDasharray="3 5"
          />

          {model.series.map((series, index) => (
            <path
              key={series.id}
              d={series.d}
              fill="none"
              stroke="var(--accent)"
              strokeOpacity={0.16}
              strokeWidth={1.25}
              pathLength={1}
              className="chart-draw"
              style={{ animationDelay: `${Math.min(index * 20, 400)}ms` }}
            />
          ))}

          <path
            d={model.overall}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={2.25}
            strokeLinecap="round"
            pathLength={1}
              className="chart-draw"
          />

          {hovered ? (
            <g>
              <line
                x1={hovered.cx}
                x2={hovered.cx}
                y1={box.y0}
                y2={box.y1}
                stroke="var(--line2)"
              />
              <circle cx={hovered.cx} cy={hovered.cy} r={4} fill="var(--accent)" />
              <text
                x={Math.min(hovered.cx + 8, box.x1 - 60)}
                y={Math.max(hovered.cy - 10, box.y0 + 10)}
                fill="var(--text)"
                fontFamily="var(--font-jetbrains-mono), monospace"
                fontSize={10}
              >
                {formatPercent(hovered.value, 1)}
              </text>
            </g>
          ) : null}

          {/* Invisible hit targets keep hover working without measuring the DOM. */}
          {model.overallPoints.map((point, index) => (
            <rect
              key={`hit-${index}`}
              x={point.cx - 6}
              y={box.y0}
              width={12}
              height={box.height}
              fill="transparent"
              onMouseEnter={() => setHover(index)}
              onMouseLeave={() => setHover(null)}
            />
          ))}
        </g>
      ) : null}
    </ChartFrame>
  );
}
