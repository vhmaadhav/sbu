// Shared chart maths. Every chart draws into a fixed viewBox and scales with
// preserveAspectRatio, so nothing here needs to measure the DOM.

export interface Plot {
  width: number;
  height: number;
  pad: { top: number; right: number; bottom: number; left: number };
}

export const DEFAULT_PLOT: Plot = {
  width: 720,
  height: 300,
  pad: { top: 16, right: 20, bottom: 34, left: 46 },
};

export function innerBox(plot: Plot) {
  return {
    x0: plot.pad.left,
    y0: plot.pad.top,
    x1: plot.width - plot.pad.right,
    y1: plot.height - plot.pad.bottom,
    width: plot.width - plot.pad.left - plot.pad.right,
    height: plot.height - plot.pad.top - plot.pad.bottom,
  };
}

/** Map a value in [min,max] onto [from,to]. Degenerate domains map to the start. */
export function linear(value: number, min: number, max: number, from: number, to: number) {
  if (max === min) return from;
  const t = (value - min) / (max - min);
  return from + t * (to - from);
}

/** Round tick values for an axis; `count` is a target, not a guarantee. */
export function ticks(min: number, max: number, count = 5): number[] {
  if (max === min) return [min];
  const raw = (max - min) / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? magnitude * 10;
  const start = Math.ceil(min / step) * step;
  const out: number[] = [];
  for (let v = start; v <= max + step / 1000; v += step) out.push(Number(v.toFixed(10)));
  return out;
}

/** A smooth path through points, using a monotone-ish cubic that never overshoots. */
export function linePath(points: { x: number; y: number }[]): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  const d = [`M ${points[0].x} ${points[0].y}`];
  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1];
    const curr = points[i];
    const cx = (prev.x + curr.x) / 2;
    d.push(`C ${cx} ${prev.y}, ${cx} ${curr.y}, ${curr.x} ${curr.y}`);
  }
  return d.join(" ");
}

export function formatPercent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatDay(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

/** Truncate a label to fit an axis slot without wrapping. */
export function clip(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}
