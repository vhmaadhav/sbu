"use client";

import { useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";

type Variant = "solid" | "ghost";

/** Accent-outlined button that fills with the accent (inverting text) on hover.
 *  `ghost` uses a neutral --line2 border. Renders a Next <Link> when `href` set. */
export default function GlowButton({
  children,
  onClick,
  href,
  variant = "solid",
  type = "button",
  disabled = false,
  className,
  style,
}: {
  children: ReactNode;
  onClick?: () => void;
  href?: string;
  variant?: Variant;
  type?: "button" | "submit" | "reset";
  disabled?: boolean;
  className?: string;
  style?: CSSProperties;
}) {
  const [hover, setHover] = useState(false);
  const solid = variant === "solid";
  const borderColor = solid ? "var(--accent)" : "var(--line2)";
  const baseColor = solid ? "var(--accent)" : "var(--text)";

  const css: CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    cursor: disabled ? "not-allowed" : "pointer",
    border: `1px solid ${hover && !disabled ? "var(--accent)" : borderColor}`,
    background: hover && !disabled && solid ? "var(--accent)" : "transparent",
    color: hover && !disabled ? (solid ? "var(--bg)" : "var(--accent)") : baseColor,
    fontFamily: "var(--font-jetbrains-mono), monospace",
    fontSize: 11,
    letterSpacing: "0.2em",
    textTransform: "uppercase",
    padding: "10px 16px",
    opacity: disabled ? 0.5 : 1,
    transition: "background 0.2s, color 0.2s, border-color 0.2s",
    ...style,
  };

  const handlers = {
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
  };

  if (href && !disabled) {
    return (
      <Link href={href} className={className} style={css} {...handlers}>
        {children}
      </Link>
    );
  }

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={className}
      style={css}
      {...handlers}
    >
      {children}
    </button>
  );
}
