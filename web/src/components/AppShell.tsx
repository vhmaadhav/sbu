"use client";

import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { usePathname } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [navigationOpen, setNavigationOpen] = useState(false);
  const pathname = usePathname();
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    document.body.style.overflow = navigationOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [navigationOpen]);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg)",
        color: "var(--text)",
        display: "flex",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Ambient glow. Deliberately static and unfiltered: every panel, the
          sidebar and the topbar are backdrop-filter surfaces stacked above
          this, so anything that moves back here forces the compositor to
          re-blur all of their backdrops on every frame, forever — the whole
          UI stayed busy while idle. A radial-gradient is already soft, so
          dropping the 30px blur costs nothing visually and removes two
          full-viewport filter passes. */}
      <div
        data-blob
        style={{
          position: "fixed",
          top: -140,
          left: 120,
          width: 520,
          height: 520,
          borderRadius: "50%",
          background: "radial-gradient(circle, var(--accent), transparent 68%)",
          opacity: 0.16,
          pointerEvents: "none",
          zIndex: 0,
        }}
      />
      <div
        data-blob
        style={{
          position: "fixed",
          bottom: -180,
          right: 80,
          width: 560,
          height: 560,
          borderRadius: "50%",
          background: "radial-gradient(circle, var(--g2), transparent 68%)",
          pointerEvents: "none",
          zIndex: 0,
        }}
      />
      {/* Grid overlay */}
      <div
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          backgroundImage:
            "linear-gradient(var(--line) 1px, transparent 1px), linear-gradient(90deg, var(--line) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          opacity: "var(--grid-opacity, 0.35)",
          zIndex: 0,
        }}
      />

      <Sidebar open={navigationOpen} onClose={() => setNavigationOpen(false)} />

      <div style={{ flex: 1, minWidth: 0, position: "relative", zIndex: 1, display: "flex", flexDirection: "column" }}>
        <Topbar onMenu={() => setNavigationOpen(true)} />
        <motion.main
          key={pathname}
          initial={reduceMotion ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.28, ease: [0.2, 0.8, 0.2, 1] }}
          style={{ flex: 1, minWidth: 0, overflow: "auto" }}
        >
          {children}
        </motion.main>
      </div>
    </div>
  );
}
