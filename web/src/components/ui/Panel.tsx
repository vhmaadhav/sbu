import type { CSSProperties, ReactNode } from "react";

/** Glass card: 1px hairline border, translucent panel background, backdrop blur,
 *  square corners. `accent` outlines it in the accent color with a soft glow. */
export default function Panel({
  children,
  accent = false,
  className,
  style,
}: {
  children: ReactNode;
  accent?: boolean;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      className={className}
      style={{
        border: `1px solid ${accent ? "var(--accent)" : "var(--line)"}`,
        background: "var(--panel)",
        backdropFilter: "var(--blur)",
        WebkitBackdropFilter: "var(--blur)",
        boxShadow: accent ? "0 0 34px -18px var(--accent)" : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
}
