"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import {
  type Accent,
  type ThemePref,
  type Prefs,
  readPrefs,
  writePrefs,
} from "@/lib/prefs";

interface ThemeContextValue {
  theme: ThemePref;
  accent: Accent;
  grid: boolean;
  dyslexic: boolean;
  setTheme: (theme: ThemePref) => void;
  toggleTheme: () => void;
  setAccent: (accent: Accent) => void;
  setGrid: (grid: boolean) => void;
  setDyslexic: (dyslexic: boolean) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function apply(prefs: Prefs) {
  const root = document.documentElement;
  root.setAttribute("data-theme", prefs.theme);
  root.style.setProperty("--accent", prefs.accent);
  root.style.setProperty("--grid-opacity", prefs.grid ? "0.35" : "0");
  // Presence of the attribute drives the OpenDyslexic + spacing rules in
  // globals.css; removing it (rather than setting "false") keeps the
  // selector simple and stops the font from ever being fetched.
  if (prefs.dyslexic) root.setAttribute("data-dyslexic", "true");
  else root.removeAttribute("data-dyslexic");
}

export default function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Lazy init from storage. During SSR readPrefs returns the defaults; the
  // inline bootstrap script in layout.tsx has already applied the real values
  // to <html> before this runs, so there is no flash.
  const [prefs, setPrefs] = useState<Prefs>(readPrefs);

  useEffect(() => {
    apply(prefs);
    writePrefs(prefs);
  }, [prefs]);

  const setTheme = useCallback((theme: ThemePref) => setPrefs((p) => ({ ...p, theme })), []);
  const toggleTheme = useCallback(
    () => setPrefs((p) => ({ ...p, theme: p.theme === "dark" ? "light" : "dark" })),
    [],
  );
  const setAccent = useCallback((accent: Accent) => setPrefs((p) => ({ ...p, accent })), []);
  const setGrid = useCallback((grid: boolean) => setPrefs((p) => ({ ...p, grid })), []);
  const setDyslexic = useCallback(
    (dyslexic: boolean) => setPrefs((p) => ({ ...p, dyslexic })),
    [],
  );

  return (
    <ThemeContext.Provider
      value={{ ...prefs, setTheme, toggleTheme, setAccent, setGrid, setDyslexic }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
