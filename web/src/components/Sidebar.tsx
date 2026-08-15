"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useTheme } from "@/components/ThemeProvider";
import MonoLabel from "@/components/ui/MonoLabel";

const GROUPS: { label: string; items: { href: string; label: string }[] }[] = [
  {
    label: "Workspace",
    items: [
      { href: "/", label: "Overview" },
      { href: "/notes", label: "Notes" },
      { href: "/files", label: "Library" },
      { href: "/search", label: "Ask my notes" },
    ],
  },
  {
    label: "Learn",
    items: [
      { href: "/learn", label: "Adaptive path" },
      { href: "/tasks", label: "Tasks" },
      { href: "/calendar", label: "Calendar" },
      { href: "/flashcards", label: "Flashcards" },
      { href: "/question-papers", label: "Question papers" },
      { href: "/audiobooks", label: "Audiobooks" },
      { href: "/handwriting", label: "Handwriting" },
      { href: "/video", label: "Video review" },
    ],
  },
];

function isActive(pathname: string, href: string): boolean {
  return pathname === href || (href !== "/" && pathname.startsWith(`${href}/`));
}

function NavRow({
  num,
  label,
  href,
  active,
  onNavigate,
}: {
  num: string;
  label: string;
  href: string;
  active: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "11px 12px",
        borderLeft: `2px solid ${active ? "var(--accent)" : "transparent"}`,
        background: active ? "var(--panel2)" : "transparent",
        color: active ? "var(--text)" : "var(--dim)",
      }}
    >
      <span
        style={{
          fontFamily: "var(--font-jetbrains-mono), monospace",
          fontSize: 10,
          letterSpacing: "0.1em",
          color: active ? "var(--accent)" : "var(--faint)",
        }}
      >
        {num}
      </span>
      <span style={{ fontSize: 14, letterSpacing: "0.06em" }}>{label}</span>
    </Link>
  );
}

// Flatten groups into a single 01..NN numbering computed before render.
const NUMBERED = (() => {
  let n = 0;
  return GROUPS.map((group) => ({
    label: group.label,
    items: group.items.map((item) => {
      n += 1;
      return { ...item, num: String(n).padStart(2, "0") };
    }),
  }));
})();

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();

  return (
    <>
      {/* Wordmark */}
      <div
        style={{
          padding: "26px 22px 22px",
          borderBottom: "1px solid var(--line)",
          display: "flex",
          alignItems: "center",
          gap: 11,
        }}
      >
        <div
          style={{
            width: 30,
            height: 30,
            border: "1px solid var(--accent)",
            display: "grid",
            placeItems: "center",
            fontFamily: "var(--font-jetbrains-mono), monospace",
            fontSize: 13,
            color: "var(--accent)",
            boxShadow: "0 0 18px -6px var(--accent)",
          }}
        >
          A
        </div>
        <div>
          <div style={{ fontWeight: 600, letterSpacing: "0.14em", fontSize: 15 }}>AXIOM</div>
          <MonoLabel size={9} spacing="0.22em">STUDY SYSTEM</MonoLabel>
        </div>
      </div>

      {/* Nav */}
      <div style={{ padding: "18px 12px", display: "flex", flexDirection: "column", gap: 14, flex: 1, overflowY: "auto" }}>
        {NUMBERED.map((group) => (
          <div key={group.label} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <div style={{ padding: "0 12px 6px" }}>
              <MonoLabel size={9} spacing="0.18em" dim>{group.label}</MonoLabel>
            </div>
            {group.items.map((item) => (
              <NavRow
                key={item.href}
                num={item.num}
                label={item.label}
                href={item.href}
                active={isActive(pathname, item.href)}
                onNavigate={onNavigate}
              />
            ))}
          </div>
        ))}
      </div>

      {/* Footer: settings, theme toggle, user chip */}
      <div style={{ padding: "16px 18px", borderTop: "1px solid var(--line)", display: "flex", flexDirection: "column", gap: 14 }}>
        <NavRow
          num="12"
          label="Settings"
          href="/settings"
          active={isActive(pathname, "/settings")}
          onNavigate={onNavigate}
        />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 12px" }}>
          <MonoLabel size={10} spacing="0.18em">{theme === "dark" ? "DARK MODE" : "LIGHT MODE"}</MonoLabel>
          <button
            type="button"
            aria-label="Toggle theme"
            onClick={toggleTheme}
            style={{
              width: 38,
              height: 20,
              border: "1px solid var(--line2)",
              borderRadius: 20,
              position: "relative",
              background: "transparent",
              cursor: "pointer",
            }}
          >
            <span
              style={{
                position: "absolute",
                top: 2,
                left: theme === "dark" ? 2 : 20,
                width: 14,
                height: 14,
                borderRadius: "50%",
                background: "var(--accent)",
                transition: "left 0.25s",
                boxShadow: "0 0 10px -2px var(--accent)",
              }}
            />
          </button>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 12px" }}>
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: "50%",
              border: "1px solid var(--line2)",
              display: "grid",
              placeItems: "center",
              fontFamily: "var(--font-jetbrains-mono), monospace",
              fontSize: 10,
              color: "var(--dim)",
            }}
          >
            SB
          </div>
          <div style={{ fontSize: 12, color: "var(--dim)" }}>Study Buddy</div>
        </div>
      </div>
    </>
  );
}

export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <>
      <aside
        className="hidden xl:flex"
        style={{
          width: 224,
          flexShrink: 0,
          flexDirection: "column",
          borderRight: "1px solid var(--line)",
          background: "var(--panel)",
          backdropFilter: "var(--blur)",
          WebkitBackdropFilter: "var(--blur)",
          position: "sticky",
          top: 0,
          height: "100dvh",
          zIndex: 2,
        }}
      >
        <Navigation />
      </aside>

      <AnimatePresence>
        {open && (
          <>
            <motion.button
              type="button"
              aria-label="Close navigation"
              className="fixed inset-0 z-40 xl:hidden"
              style={{ background: "rgba(0,0,0,0.5)", backdropFilter: "blur(2px)" }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={onClose}
            />
            <motion.aside
              className="fixed inset-y-0 left-0 z-50 flex flex-col xl:hidden"
              style={{
                width: "min(86vw, 292px)",
                background: "var(--panel)",
                backdropFilter: "var(--blur)",
                WebkitBackdropFilter: "var(--blur)",
                borderRight: "1px solid var(--line)",
              }}
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 380, damping: 38 }}
            >
              <button
                onClick={onClose}
                className="absolute right-3 top-4 z-10 p-2"
                style={{ color: "var(--dim)" }}
                aria-label="Close navigation"
              >
                <X className="h-5 w-5" />
              </button>
              <Navigation onNavigate={onClose} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
