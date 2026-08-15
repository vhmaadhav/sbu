// User appearance preferences, persisted to localStorage under one key.
// Read before hydration by an inline script in layout.tsx, and managed at
// runtime by ThemeProvider.

export type ThemePref = "dark" | "light";
export type Accent = "#5eead4" | "#7dd3fc" | "#c4b5fd" | "#fda4af";

export interface Prefs {
  theme: ThemePref;
  accent: Accent;
  grid: boolean;
  /** Dyslexia-friendly reading: OpenDyslexic + wider letter/word spacing. */
  dyslexic: boolean;
}

export const ACCENTS: { value: Accent; label: string }[] = [
  { value: "#5eead4", label: "Teal" },
  { value: "#7dd3fc", label: "Sky" },
  { value: "#c4b5fd", label: "Violet" },
  { value: "#fda4af", label: "Rose" },
];

export const DEFAULT_PREFS: Prefs = {
  theme: "dark",
  accent: "#5eead4",
  grid: true,
  dyslexic: false,
};

const KEY = "axiom-prefs";

export function readPrefs(): Prefs {
  if (typeof window === "undefined") return DEFAULT_PREFS;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as Partial<Prefs>;
    return {
      theme: parsed.theme === "light" ? "light" : "dark",
      accent: ACCENTS.some((a) => a.value === parsed.accent)
        ? (parsed.accent as Accent)
        : DEFAULT_PREFS.accent,
      grid: parsed.grid !== false,
      dyslexic: parsed.dyslexic === true,
    };
  } catch {
    return DEFAULT_PREFS;
  }
}

export function writePrefs(prefs: Prefs): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    /* storage unavailable — ignore */
  }
}
