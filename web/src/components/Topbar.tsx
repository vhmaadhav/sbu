"use client";

import { Menu } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getJSON, askText, type AskResult } from "@/lib/api";
import MonoLabel from "@/components/ui/MonoLabel";

function screenName(pathname: string): string {
  if (pathname === "/") return "DASHBOARD";
  const seg = pathname.split("/").filter(Boolean)[0] ?? "";
  return seg.toUpperCase();
}

const SUGGESTIONS = [
  "what's due today?",
  "summarize my last note",
  "what should I review?",
];

export default function Topbar({ onMenu }: { onMenu: () => void }) {
  const pathname = usePathname();
  const inputRef = useRef<HTMLInputElement>(null);

  const [q, setQ] = useState("");
  const [online, setOnline] = useState<boolean | null>(null);
  const [clock, setClock] = useState("");
  const [aiOpen, setAiOpen] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [answer, setAnswer] = useState("");
  const [lastQ, setLastQ] = useState("");

  useEffect(() => {
    const check = () =>
      getJSON<{ ok: boolean }>("/api/health")
        .then((r) => setOnline(r.ok))
        .catch(() => setOnline(false));
    check();
    const timer = window.setInterval(check, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const tick = () =>
      setClock(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);

  async function ask(text: string) {
    const question = text.trim();
    if (!question) return;
    setAiOpen(true);
    setThinking(true);
    setAnswer("");
    setLastQ(question);
    try {
      const result: AskResult = await askText(question);
      setAnswer(result.answer);
    } catch {
      setAnswer("The local AI could not answer right now. Check that the backend and LM Studio are running.");
    } finally {
      setThinking(false);
    }
  }

  const hasAnswer = !thinking && !!answer;

  return (
    <header
      style={{
        height: 60,
        borderBottom: "1px solid var(--line)",
        display: "flex",
        alignItems: "center",
        gap: 24,
        justifyContent: "space-between",
        padding: "0 28px",
        background: "var(--panel)",
        backdropFilter: "var(--blur)",
        WebkitBackdropFilter: "var(--blur)",
        position: "sticky",
        top: 0,
        zIndex: 20,
      }}
    >
      <button
        onClick={onMenu}
        className="xl:hidden"
        style={{ color: "var(--dim)", padding: 6 }}
        aria-label="Open navigation"
      >
        <Menu className="h-5 w-5" />
      </button>

      <MonoLabel size={11} spacing="0.2em" className="hidden sm:inline" style={{ flexShrink: 0 }}>
        AXIOM / {screenName(pathname)}
      </MonoLabel>

      {/* Ask bar */}
      <div style={{ flex: 1, maxWidth: 540, position: "relative" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            border: `1px solid ${aiOpen ? "var(--accent)" : "var(--line)"}`,
            background: "var(--panel2)",
            padding: "8px 14px",
            transition: "border-color 0.25s",
            boxShadow: aiOpen ? "0 0 30px -16px var(--accent)" : "none",
          }}
        >
          <span
            style={{
              fontFamily: "var(--font-jetbrains-mono), monospace",
              fontSize: 13,
              color: "var(--accent)",
            }}
          >
            ›
          </span>
          <input
            ref={inputRef}
            aria-label="Ask Axiom"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onFocus={() => {
              if (answer || thinking) setAiOpen(true);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") ask(q);
            }}
            placeholder={`Ask Axiom — "${SUGGESTIONS[0]}"`}
            style={{
              flex: 1,
              background: "transparent",
              border: "none",
              outline: "none",
              color: "var(--text)",
              fontFamily: "var(--font-body)",
              fontSize: 13,
              minWidth: 0,
            }}
          />
          <MonoLabel size={9} spacing="0.14em" dim style={{ border: "1px solid var(--line2)", padding: "2px 6px" }}>
            AI
          </MonoLabel>
        </div>

        {aiOpen && (
          <div
            className="axscreen"
            style={{
              position: "absolute",
              top: "calc(100% + 8px)",
              left: 0,
              right: 0,
              zIndex: 30,
              border: "1px solid var(--accent)",
              background: "var(--panel)",
              backdropFilter: "var(--blur)",
              WebkitBackdropFilter: "var(--blur)",
              boxShadow: "0 24px 50px -24px rgba(0,0,0,0.7), 0 0 40px -22px var(--accent)",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "12px 18px",
                borderBottom: "1px solid var(--line)",
              }}
            >
              <MonoLabel size={10} spacing="0.2em" style={{ color: "var(--accent)" }}>
                AXIOM AI{lastQ ? ` · ${lastQ.toUpperCase().slice(0, 40)}` : ""}
              </MonoLabel>
              <button
                onClick={() => setAiOpen(false)}
                style={{ color: "var(--dim)", fontFamily: "var(--font-jetbrains-mono), monospace", fontSize: 11 }}
                aria-label="Close AI panel"
              >
                ✕
              </button>
            </div>
            <div style={{ padding: 18, fontSize: 14, lineHeight: 1.65, color: "var(--text)", minHeight: 22 }}>
              {thinking ? (
                <MonoLabel size={12} spacing="0.16em">
                  ANALYZING
                  <span style={{ animation: "pulse 1s infinite" }}>…</span>
                </MonoLabel>
              ) : (
                answer
              )}
            </div>
            {hasAnswer && (
              <div style={{ display: "flex", gap: 8, padding: "0 18px 16px", flexWrap: "wrap" }}>
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => {
                      setQ(s);
                      ask(s);
                    }}
                    style={{
                      fontFamily: "var(--font-jetbrains-mono), monospace",
                      fontSize: 10,
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                      color: "var(--dim)",
                      border: "1px solid var(--line2)",
                      padding: "6px 11px",
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Status */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 18,
          fontFamily: "var(--font-jetbrains-mono), monospace",
          fontSize: 11,
          color: "var(--dim)",
          flexShrink: 0,
        }}
        className="hidden md:flex"
      >
        <span style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: online === false ? "#f87171" : "var(--accent)",
              animation: "pulse 2.4s infinite",
            }}
          />
          {online === false ? "OFFLINE" : "SYNCED"}
        </span>
        <span>{clock}</span>
      </div>
    </header>
  );
}
