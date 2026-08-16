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
      {/* Ambient blobs */}
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
          filter: "blur(30px)",
          pointerEvents: "none",
          animation: "blobDrift 18s ease-in-out infinite",
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
          filter: "blur(30px)",
          pointerEvents: "none",
          animation: "blobDrift 22s ease-in-out infinite reverse",
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
