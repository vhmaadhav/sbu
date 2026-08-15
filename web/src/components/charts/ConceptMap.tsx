"use client";

import { useMemo, useRef, useState } from "react";
import { masteryFill, WEAK_THRESHOLD, type ConceptNode, type Graph } from "@/lib/learn";
import { clip, formatPercent } from "./scale";

const TIER_GAP = 130;
const NODE_GAP = 168;
const MARGIN = 90;

interface Placed extends ConceptNode {
  x: number;
  y: number;
  r: number;
}

/** The concept graph. Tiers come from the server, so layout is deterministic:
 *  no force simulation, no jitter, identical on every render. */
export default function ConceptMap({
  graph,
  onSelect,
  height = 420,
}: {
  graph: Graph;
  onSelect?: (node: ConceptNode) => void;
  height?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  // The origin lives in a ref (it changes on every pointer move and must not
  // re-render); `dragging` is state because the cursor is rendered from it.
  const drag = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  const { placed, byId, width, mapHeight } = useMemo(() => {
    const tiers = new Map<number, ConceptNode[]>();
    graph.nodes.forEach((node) => {
      const list = tiers.get(node.tier) ?? [];
      list.push(node);
      tiers.set(node.tier, list);
    });
    const tierKeys = [...tiers.keys()].sort((a, b) => a - b);
    const widest = Math.max(1, ...[...tiers.values()].map((list) => list.length));
    const w = MARGIN * 2 + (widest - 1) * NODE_GAP;
    const h = MARGIN * 2 + Math.max(0, tierKeys.length - 1) * TIER_GAP;

    const out: Placed[] = [];
    tierKeys.forEach((tier, tierIndex) => {
      const list = [...(tiers.get(tier) ?? [])].sort((a, b) => a.position - b.position);
      const rowWidth = (list.length - 1) * NODE_GAP;
      list.forEach((node, index) => {
        out.push({
          ...node,
          x: w / 2 - rowWidth / 2 + index * NODE_GAP,
          y: MARGIN + tierIndex * TIER_GAP,
          r: 15 + Math.min(11, node.downstream * 2),
        });
      });
    });

    return {
      placed: out,
      byId: new Map(out.map((node) => [node.id, node])),
      width: w,
      mapHeight: h,
    };
  }, [graph]);

  if (graph.nodes.length === 0) {
    return (
      <div
        style={{
          height,
          display: "grid",
          placeItems: "center",
          color: "var(--faint)",
          fontFamily: "var(--font-jetbrains-mono), monospace",
          fontSize: 11,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
        }}
      >
        No concept graph yet
      </div>
    );
  }

  const viewWidth = width / zoom;
  const viewHeight = mapHeight / zoom;
  const hovered = hover !== null ? byId.get(hover) : null;

  return (
    <div
      style={{ position: "relative", height, overflow: "hidden", cursor: dragging ? "grabbing" : "grab" }}
      onPointerDown={(event) => {
        drag.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
        setDragging(true);
        (event.target as Element).setPointerCapture?.(event.pointerId);
      }}
      onPointerMove={(event) => {
        if (!drag.current) return;
        const scale = viewWidth / event.currentTarget.clientWidth;
        setPan({
          x: drag.current.panX - (event.clientX - drag.current.x) * scale,
          y: drag.current.panY - (event.clientY - drag.current.y) * scale,
        });
      }}
      onPointerUp={() => {
        drag.current = null;
        setDragging(false);
      }}
      onPointerLeave={() => {
        drag.current = null;
        setDragging(false);
        setHover(null);
      }}
      onWheel={(event) => {
        setZoom((current) =>
          Math.min(3, Math.max(0.6, current * (event.deltaY < 0 ? 1.08 : 0.93))),
        );
      }}
    >
      <svg
        viewBox={`${pan.x} ${pan.y} ${viewWidth} ${viewHeight}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ width: "100%", height: "100%", display: "block", touchAction: "none" }}
        role="img"
        aria-label="Concept map"
      >
        {/* Edges first so nodes sit on top of them. */}
        <g>
          {graph.edges.map((edge) => {
            const from = byId.get(edge.prereq_id);
            const to = byId.get(edge.concept_id);
            if (!from || !to) return null;
            const midY = (from.y + to.y) / 2;
            const active =
              hover !== null && (hover === edge.prereq_id || hover === edge.concept_id);
            return (
              <path
                key={`${edge.prereq_id}-${edge.concept_id}`}
                d={`M ${from.x} ${from.y + from.r} C ${from.x} ${midY}, ${to.x} ${midY}, ${to.x} ${to.y - to.r}`}
                fill="none"
                stroke={active ? "var(--accent)" : "var(--line2)"}
                strokeWidth={active ? 1.6 : 1}
                strokeOpacity={active ? 0.9 : 0.5}
              />
            );
          })}
        </g>

        {placed.map((node, index) => {
          const weak = node.p_known < WEAK_THRESHOLD;
          const active = hover === node.id;
          return (
            <g
              key={node.id}
              className="node-in"
              style={{ animationDelay: `${Math.min(index * 25, 600)}ms`, cursor: "pointer" }}
              onMouseEnter={() => setHover(node.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onSelect?.(node)}
            >
              {active ? (
                <circle cx={node.x} cy={node.y} r={node.r + 7} fill="var(--accent)" opacity={0.12} />
              ) : null}
              <circle
                cx={node.x}
                cy={node.y}
                r={node.r}
                fill={masteryFill(node.p_known)}
                stroke={weak ? "var(--warn)" : "var(--accent)"}
                strokeOpacity={weak ? 0.9 : 0.55}
                strokeWidth={weak ? 1.6 : 1}
                style={{ transition: "fill 0.3s" }}
              />
              {node.in_srs ? (
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={node.r + 4}
                  fill="none"
                  stroke="var(--accent)"
                  strokeOpacity={0.35}
                  strokeDasharray="2 4"
                />
              ) : null}
              <text
                x={node.x}
                y={node.y + node.r + 15}
                textAnchor="middle"
                fill={active ? "var(--text)" : "var(--dim)"}
                fontSize={11}
              >
                {clip(node.name, 20)}
              </text>
            </g>
          );
        })}
      </svg>

      {hovered ? (
        <div
          className="reveal"
          style={{
            position: "absolute",
            left: 14,
            bottom: 14,
            maxWidth: 320,
            padding: "12px 14px",
            border: "1px solid var(--line2)",
            background: "var(--panel2)",
            backdropFilter: "var(--blur)",
            pointerEvents: "none",
          }}
        >
          <div style={{ fontSize: 13, color: "var(--text)", marginBottom: 5 }}>{hovered.name}</div>
          <div
            style={{
              fontFamily: "var(--font-jetbrains-mono), monospace",
              fontSize: 10,
              color: "var(--accent)",
              letterSpacing: "0.14em",
            }}
          >
            {formatPercent(hovered.p_known)} · TIER {hovered.tier} ·{" "}
            {hovered.attempts} ATTEMPT{hovered.attempts === 1 ? "" : "S"}
          </div>
          {hovered.blurb ? (
            <div style={{ fontSize: 11, color: "var(--faint)", marginTop: 7 }}>{hovered.blurb}</div>
          ) : null}
        </div>
      ) : null}

      <div
        style={{
          position: "absolute",
          right: 14,
          bottom: 14,
          fontFamily: "var(--font-jetbrains-mono), monospace",
          fontSize: 9,
          letterSpacing: "0.16em",
          color: "var(--faint)",
          pointerEvents: "none",
        }}
      >
        DRAG TO PAN · SCROLL TO ZOOM
      </div>
    </div>
  );
}
