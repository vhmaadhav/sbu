"use client";

import { useEffect, useId, useState } from "react";

interface MermaidDiagramProps {
  source: string;
}

/** Render Mermaid lazily in the browser and retain its editable source. */
export default function MermaidDiagram({ source }: MermaidDiagramProps) {
  const reactId = useId();
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const render = async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "base",
          themeVariables: {
            primaryColor: "#eef4ff",
            primaryBorderColor: "#4c7dff",
            primaryTextColor: "#162033",
            lineColor: "#65748b",
            fontFamily: "var(--font-jetbrains-mono), monospace",
          },
          flowchart: { htmlLabels: false, curve: "basis" },
        });
        const id = `mermaid-${reactId.replace(/[^a-zA-Z0-9_-]/g, "")}`;
        const result = await mermaid.render(id, source);
        if (!cancelled) {
          setSvg(result.svg);
          setError("");
        }
      } catch (reason) {
        if (!cancelled) {
          setSvg("");
          setError(reason instanceof Error ? reason.message : "Could not render this diagram");
        }
      }
    };
    render();
    return () => {
      cancelled = true;
    };
  }, [reactId, source]);

  return (
    <div className="mermaid-note">
      {svg ? (
        <div
          className="mermaid-canvas"
          aria-label="Rendered Mermaid diagram"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      ) : error ? (
        <p className="mermaid-error">Diagram preview unavailable: {error}</p>
      ) : (
        <p className="mermaid-loading">Rendering diagram…</p>
      )}
      <details>
        <summary>Editable Mermaid source</summary>
        <pre>
          <code>{source}</code>
        </pre>
      </details>
    </div>
  );
}
