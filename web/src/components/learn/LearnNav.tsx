"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import MonoLabel from "@/components/ui/MonoLabel";

const STEPS = [
  { href: "/learn", label: "Goal" },
  { href: "/learn/gaps", label: "Knowledge gaps" },
  { href: "/learn/map", label: "Concept map" },
  { href: "/learn/report", label: "Report" },
];

/** The journey strip. Numbered like the sidebar so it reads as the same system. */
export default function LearnNav() {
  const pathname = usePathname();

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 4,
        flexWrap: "wrap",
        borderBottom: "1px solid var(--line)",
        paddingBottom: 14,
        marginBottom: 22,
      }}
    >
      {STEPS.map((step, index) => {
        const active =
          step.href === "/learn" ? pathname === "/learn" : pathname.startsWith(step.href);
        return (
          <Link
            key={step.href}
            href={step.href}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "7px 13px",
              border: `1px solid ${active ? "var(--accent)" : "transparent"}`,
              background: active ? "var(--panel2)" : "transparent",
              transition: "border-color 0.2s, background 0.2s",
            }}
          >
            <MonoLabel size={9} spacing="0.18em" style={{ color: active ? "var(--accent)" : "var(--faint)" }}>
              {String(index + 1).padStart(2, "0")}
            </MonoLabel>
            <span style={{ fontSize: 12.5, color: active ? "var(--text)" : "var(--dim)" }}>
              {step.label}
            </span>
          </Link>
        );
      })}
    </div>
  );
}
