import type { CSSProperties, ReactNode } from "react";

/** All-caps JetBrains-Mono label used for section headers, tags, and metadata. */
export default function MonoLabel({
  children,
  dim = false,
  size = 11,
  spacing = "0.2em",
  className,
  style,
}: {
  children: ReactNode;
  dim?: boolean;
  size?: number;
  spacing?: string;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <span
      className={className}
      style={{
        fontFamily: "var(--font-jetbrains-mono), monospace",
        fontSize: size,
        letterSpacing: spacing,
        textTransform: "uppercase",
        color: dim ? "var(--faint)" : "var(--dim)",
        ...style,
      }}
    >
      {children}
    </span>
  );
}
