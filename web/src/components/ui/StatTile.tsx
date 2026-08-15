import type { ReactNode } from "react";

/** Dashboard metric tile: mono label, large mono value with optional unit,
 *  and a small caption. Meant to sit inside a 1px-gap grid on a --line bg. */
export default function StatTile({
  label,
  value,
  unit,
  sub,
  accent = false,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div style={{ background: "var(--panel)", padding: "20px 22px" }}>
      <div
        style={{
          fontFamily: "var(--font-jetbrains-mono), monospace",
          fontSize: 10,
          color: "var(--dim)",
          letterSpacing: "0.2em",
          textTransform: "uppercase",
          marginBottom: 12,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 28,
          fontWeight: 500,
          fontFamily: "var(--font-jetbrains-mono), monospace",
          color: accent ? "var(--accent)" : "var(--text)",
        }}
      >
        {value}
        {unit ? (
          <span style={{ fontSize: 13, color: "var(--dim)", marginLeft: 5 }}>{unit}</span>
        ) : null}
      </div>
      {sub ? (
        <div style={{ fontSize: 11, color: "var(--faint)", marginTop: 8 }}>{sub}</div>
      ) : null}
    </div>
  );
}
