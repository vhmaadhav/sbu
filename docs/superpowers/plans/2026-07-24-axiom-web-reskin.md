# Axiom Web Reskin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Study Buddy `web/` frontend UI in the Axiom design language, in place, with every existing backend feature wired and no mock data.

**Architecture:** Keep the Next.js 16 / React 19 / Tailwind v4 app, its `lib/api.ts` client, and the Next→FastAPI rewrites proxy. Replace the design token set and shell, add a small `ui/` primitive layer, then rebuild each of the 11 route pages against real endpoints. Delivered in 4 review-gated phases; Phase 1 establishes the token/primitive/shell contract every later screen consumes.

**Tech Stack:** Next.js 16 (App Router), React 19, Tailwind CSS v4 (`@theme inline` tokens in `globals.css`), `next/font/google` (Space Grotesk + JetBrains Mono), Framer Motion, lucide-react, react-markdown/katex (existing).

## Global Constraints

- No backend/API changes. Frontend only.
- No new runtime dependencies except the JetBrains Mono font (via `next/font/google`, no package install).
- Keep the existing API proxy: all data calls go through same-origin `/api/*` (see `web/next.config.ts` rewrites). Do not hardcode `http://127.0.0.1:8010`.
- Keep `web/src/lib/api.ts` `getJSON`/`postJSON` signatures; extend with new helpers, don't rewrite existing ones.
- Dark theme is the SSR default; `theme`/`accent`/`grid` prefs persist in `localStorage` and apply before hydration to avoid flash.
- All animation (blobDrift, grid, screenIn, pulse) must be disabled under `@media (prefers-reduced-motion: reduce)`.
- Verification per task/phase: `bun --cwd web run lint` and `bun --cwd web run build` pass clean; changed screens load in the browser against the live backend (port 8010) and render real data. No mock/hardcoded content ships in a screen.
- Axiom palette values (copy verbatim): `--bg:#070b11`; `--panel:rgba(12,18,27,0.55)`; `--panel2:rgba(18,27,41,0.7)`; `--line:rgba(140,175,215,0.14)`; `--line2:rgba(140,175,215,0.28)`; `--text:#dce7f3`; `--dim:#677c93`; `--faint:#3d4d60`; `--blur:blur(16px) saturate(1.4)`; `--g2:rgba(120,190,255,0.16)`. Light: `--bg:#eef2f7`; `--panel:rgba(255,255,255,0.6)`; `--panel2:rgba(233,238,245,0.72)`; `--line:rgba(30,60,95,0.14)`; `--line2:rgba(30,60,95,0.28)`; `--text:#17222f`; `--dim:#5b6c7f`; `--faint:#9fb0c2`; `--g2:rgba(90,150,230,0.14)`.
- Accent swatches: teal `#5eead4`, sky `#7dd3fc`, violet `#c4b5fd`, rose `#fda4af`. Default teal.
- Fonts: Space Grotesk (body/display), JetBrains Mono (mono labels, weights 300/400/500). Mono label style: uppercase, `letter-spacing:0.16–0.24em`, 9–11px, color `--dim`/`--faint`.

---

## Reference: existing files & the backend contract

Implementers should read these before starting a task; they are the source of truth for data shapes and current behavior.

- Shell: `web/src/components/AppShell.tsx`, `Sidebar.tsx`, `Topbar.tsx`.
- Pages: `web/src/app/{page,notes,flashcards,search,files,tasks,calendar,audiobooks,handwriting,video,settings}/*` and `layout.tsx`, `globals.css`.
- API client + types: `web/src/lib/api.ts` (exports `getJSON`, `postJSON`, and interfaces `Stats`, `NotePreview`, `Subject`, `Item`, `RetryResult`, `ActivityEvent`, `Audiobook`, `HwPage`, `HwLine`, `HwPageDetail`, `HwStatus`, `VideoSegment`, `VideoFrame`, plus `timeAgo`/`shortDate`). Reuse these; add new ones alongside.
- Backend routes: `backend/server.py`. Endpoint list per screen is in the spec's screen-mapping table (`docs/superpowers/specs/2026-07-24-axiom-web-reskin-design.md`). Confirm exact request/response shapes against `server.py` before wiring — do not assume field names.

---

# PHASE 1 — Foundation, shell, Dashboard

Establishes the design system, theme/accent state, `ui/` primitives, the Axiom sidebar/topbar/ask-bar, and the fully-wired Dashboard. Everything after depends on this.

### Task 1.1: Design tokens & global styles

**Files:**
- Modify: `web/src/app/globals.css`

**Interfaces:**
- Produces: CSS variables on `[data-theme="dark"|"light"]` and root `--accent`; keyframes `blobDrift`, `screenIn`, `pulse`; utility class `.axscreen`. Consumed by every component via `var(--...)`.

- [ ] **Step 1: Replace the token blocks.** In `globals.css`, keep `@import "tailwindcss";`. Replace the `:root`/`[data-theme="dark"]` token blocks with Axiom's values (see Global Constraints). Make `[data-theme="dark"]` the primary set and `[data-theme="light"]` the alternate; set `--accent:#5eead4` as a root default so it exists before JS applies the stored value. Keep the existing `@theme inline` block but repoint/extend it to expose the Axiom tokens as Tailwind colors: `--color-bg`, `--color-panel`, `--color-panel2`, `--color-line`, `--color-line2`, `--color-text`, `--color-dim`, `--color-faint`, `--color-accent`. Set `--font-display: var(--font-space-grotesk)` and add `--font-mono: var(--font-jetbrains-mono)`.

- [ ] **Step 2: Add keyframes + base rules.** Append:

```css
html, body { margin:0; padding:0; height:100%; background: var(--bg); }
body { color: var(--text); font-family: var(--font-space-grotesk), sans-serif; }
a { color: var(--accent); text-decoration: none; } a:hover { color: #99f6e4; }
::-webkit-scrollbar { width:8px; height:8px; }
::-webkit-scrollbar-thumb { background: var(--line2); border-radius:4px; }
::-webkit-scrollbar-track { background: transparent; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.35} }
@keyframes screenIn { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:none} }
@keyframes blobDrift { 0%,100%{transform:translate(0,0)} 50%{transform:translate(40px,-30px)} }
.axscreen { animation: screenIn .4s cubic-bezier(.2,.7,.2,1); }
@media (prefers-reduced-motion: reduce) { .axscreen, [data-blob] { animation: none !important; } }
```

- [ ] **Step 3: Verify.** Run `bun --cwd web run lint` → clean. (Build verified after fonts in Task 1.2.)

### Task 1.2: Fonts (add JetBrains Mono)

**Files:**
- Modify: `web/src/app/layout.tsx`

**Interfaces:**
- Produces: CSS vars `--font-space-grotesk`, `--font-jetbrains-mono` on `<html>`.

- [ ] **Step 1:** In `layout.tsx`, add `JetBrains_Mono` to the `next/font/google` import and instantiate it:

```tsx
import { Space_Grotesk, JetBrains_Mono } from "next/font/google";
const spaceGrotesk = Space_Grotesk({ subsets: ["latin"], variable: "--font-space-grotesk" });
const jetbrainsMono = JetBrains_Mono({ subsets: ["latin"], weight: ["300","400","500"], variable: "--font-jetbrains-mono" });
```

Remove the Manrope import/instantiation (no longer used). Update `<html className={...}>` to include both font variables and default dark theme: `className={`${spaceGrotesk.variable} ${jetbrainsMono.variable} h-full antialiased`}` and add `data-theme="dark"` to `<html>`.

- [ ] **Step 2: Verify.** `bun --cwd web run lint && bun --cwd web run build` → clean.

### Task 1.3: Theme & accent provider

**Files:**
- Create: `web/src/components/ThemeProvider.tsx`
- Create: `web/src/lib/prefs.ts`
- Modify: `web/src/app/layout.tsx`

**Interfaces:**
- Produces:
  - `lib/prefs.ts`: `type Accent = "#5eead4"|"#7dd3fc"|"#c4b5fd"|"#fda4af"`; `type ThemePref = "dark"|"light"`; `const ACCENTS: {value:Accent;label:string}[]`; `readPrefs(): {theme:ThemePref;accent:Accent;grid:boolean}`; `writePrefs(p)`.
  - `ThemeProvider.tsx`: default-exported client component wrapping children; React context hook `useTheme()` returning `{theme, accent, grid, setTheme, setAccent, setGrid}`. On mount it reads `localStorage` and applies `data-theme` + `--accent` + a `--grid-opacity` var to `document.documentElement`.
- Consumes: nothing.

- [ ] **Step 1: Write `lib/prefs.ts`** with the types/constants above; `readPrefs` guards `typeof window === "undefined"` (returns dark/teal/grid-on) and parses `localStorage.getItem("axiom-prefs")`; `writePrefs` JSON-stringifies to the same key.

- [ ] **Step 2: Write `ThemeProvider.tsx`.** A `"use client"` component holding `theme/accent/grid` state (initialized from `readPrefs()` in a lazy `useState`), a `useEffect` that applies `document.documentElement.setAttribute("data-theme", theme)`, sets `style.setProperty("--accent", accent)`, `style.setProperty("--grid-opacity", grid ? "0.35" : "0")`, and calls `writePrefs`. Expose via context + `useTheme()`.

- [ ] **Step 3: Add a pre-hydration flash guard.** In `layout.tsx` `<head>` (or before `<body>` content), add a Next.js inline script that reads `axiom-prefs` and sets `data-theme`/`--accent` on `documentElement` before paint:

```tsx
<script dangerouslySetInnerHTML={{ __html: `try{var p=JSON.parse(localStorage.getItem('axiom-prefs')||'{}');document.documentElement.setAttribute('data-theme',p.theme||'dark');if(p.accent)document.documentElement.style.setProperty('--accent',p.accent);document.documentElement.style.setProperty('--grid-opacity',p.grid===false?'0':'0.35');}catch(e){}` }} />
```

- [ ] **Step 4:** Wrap `<AppShell>` in `<ThemeProvider>` in `layout.tsx`.

- [ ] **Step 5: Verify.** `bun --cwd web run lint && bun --cwd web run build` → clean.

### Task 1.4: UI primitives

**Files:**
- Create: `web/src/components/ui/Panel.tsx`
- Create: `web/src/components/ui/MonoLabel.tsx`
- Create: `web/src/components/ui/SectionHeader.tsx`
- Create: `web/src/components/ui/StatTile.tsx`
- Create: `web/src/components/ui/GlowButton.tsx`
- Create: `web/src/components/ui/index.ts`

**Interfaces:**
- Produces (import from `@/components/ui`):
  - `Panel({ children, accent?: boolean, className?, style? })` — glass card: 1px border (`--line`, or `--accent` when `accent`), `background:var(--panel)`, `backdrop-filter:var(--blur)`, no radius; accent variant adds `box-shadow:0 0 34px -18px var(--accent)`.
  - `MonoLabel({ children, className?, dim?, size? })` — `<span>` uppercase JetBrains Mono, `letter-spacing:0.2em`, color `--dim` (or `--faint` when `dim`), default size 11px.
  - `SectionHeader({ title, action? })` — flex row: `<MonoLabel>{title}</MonoLabel>` + optional right-aligned action node; 1px bottom border, padding `16px 22px`.
  - `StatTile({ label, value, unit?, sub?, accent? })` — the dashboard metric tile (mono label, big mono value, sub caption).
  - `GlowButton({ children, onClick?, variant?: "solid"|"ghost", href?, type?, disabled? })` — accent-bordered button, hover fills accent/inverts text; `ghost` uses `--line2`. Renders `<a>` if `href` given.

- [ ] **Step 1:** Implement each primitive as a `"use client"`-free (pure) component using inline `style` with the CSS vars (matches Axiom's inline-style approach and avoids Tailwind arbitrary-value churn). Keep each file focused; re-export all from `ui/index.ts`.

- [ ] **Step 2: Verify.** `bun --cwd web run lint && bun --cwd web run build` → clean. (Primitives are exercised by Task 1.7.)

### Task 1.5: Sidebar

**Files:**
- Modify: `web/src/components/Sidebar.tsx`

**Interfaces:**
- Consumes: `useTheme()` from `ThemeProvider`; `usePathname` (existing).
- Produces: same props (`{ open, onClose }`) so `AppShell` is unchanged in shape.

- [ ] **Step 1:** Rebuild the rail per the spec's Shell section: 224px, `background:var(--panel)`, `backdrop-filter:var(--blur)`, right border `--line`. Header = `A` logo mark (1px accent border, mono `A`, accent glow) + `AXIOM` / `STUDY SYSTEM` wordmark. Keep the existing nav data (the two groups `Workspace`/`Learn` with all 11 items incl. Overview `/`, Notes, Files, Search, Tasks, Calendar, Flashcards, Audiobooks, Handwriting, Video, and Settings in the footer). Render group labels as `MonoLabel`. Each item: mono index number (`01`…), label; active state (`pathname` match, existing logic) → 2px accent left-edge, `--panel2` bg, `--text` color; inactive `--dim`, hover `--text`.

- [ ] **Step 2:** Footer: theme toggle (mono `DARK MODE`/`LIGHT MODE` label + knob switch calling `setTheme`) and a user chip (initials circle + name; keep whatever the current app shows, else a static "Study Buddy" until a user endpoint exists — the backend has none, so this is UI-only). Preserve mobile drawer open/close (`open`/`onClose`) behavior and the overlay.

- [ ] **Step 3: Verify.** `bun --cwd web run lint && bun --cwd web run build` → clean; sidebar renders, active highlight tracks route, theme toggle flips the whole app and persists across reload.

### Task 1.6: Topbar + Ask bar

**Files:**
- Modify: `web/src/components/Topbar.tsx`
- Modify: `web/src/lib/api.ts` (add ask helpers if missing)

**Interfaces:**
- Consumes: `usePathname`; `postJSON`.
- Produces: `askText(question: string, subject?: string): Promise<{answer:string; ...}>` in `api.ts` (confirm response shape against `POST /api/ask` in `server.py`); Topbar keeps prop `{ onMenu }`.

- [ ] **Step 1:** Confirm `POST /api/ask` request/response shape in `backend/server.py` (`ask_question`/`AskRequest`) and add a typed `askText` helper to `api.ts` using `postJSON`.

- [ ] **Step 2:** Rebuild Topbar: 60px glass header. Left breadcrumb `AXIOM / <SCREEN>` (derive screen from `usePathname`) in mono. Center Ask bar: `›` glyph, controlled `<input>` (placeholder `Ask Axiom — "what's due today?"`), `AI` chip. Enter submits → call `askText`, show the Axiom dropdown answer panel (`ANALYZING…` pulse → answer text → up to 3 follow-up chips; wire chips to re-ask). Right: `SYNCED` pulse dot (`pulse` animation) + live clock (`toLocaleTimeString`, updated by a 1s interval in a `useEffect`, cleared on unmount). Keep the `onMenu` hamburger for mobile.

- [ ] **Step 3:** (Optional within this task) mic button for `/api/ask/audio` may be deferred to the `/search` screen (Phase 2); leave a placeholder-free note that audio ask lives on the Search page. Do **not** stub a non-functional mic here.

- [ ] **Step 4: Verify.** `bun --cwd web run lint && bun --cwd web run build` → clean; with backend running, typing a question + Enter returns a real answer from `/api/ask` in the dropdown.

### Task 1.7: Dashboard (wired)

**Files:**
- Modify: `web/src/app/page.tsx`
- Create: `web/src/components/dashboard/FocusTimer.tsx`
- Modify: `web/src/lib/api.ts` (add helpers as needed)

**Interfaces:**
- Consumes: `getJSON`, `Stats`, `ActivityEvent`, task + flashcard types; `Panel`, `StatTile`, `SectionHeader`, `GlowButton`, `MonoLabel`.
- Produces: `FocusTimer` (local-only Pomodoro, no backend).

- [ ] **Step 1:** Confirm shapes for `GET /api/stats`, `GET /api/tasks`, `GET /api/flashcards`, `GET /api/activity` in `server.py`. Add typed helpers/interfaces to `api.ts` for tasks and flashcard decks if not present (`Task`, `Deck`).

- [ ] **Step 2:** Rebuild `page.tsx` as a client component (data via `useEffect` + the api helpers, matching how the current pages fetch): greeting header (real date + a static or stats-derived subline — no invented streak copy; show real numbers only), a 4-tile stat grid from `/api/stats` (map real fields: notes/files/chunks/flashcards/etc. — pick the 4 most meaningful, labelled honestly), a "TODAY'S PLAN" panel from `/api/tasks` (today's tasks; empty-state if none), the `FocusTimer` panel, and a "CARDS DUE" panel from `/api/flashcards` (real deck counts) with a `GlowButton` → `/flashcards`. Use `Panel`/`StatTile`/`SectionHeader`. Wrap the screen in `.axscreen`.

- [ ] **Step 3: Write `FocusTimer.tsx`** — a `"use client"` 25:00 Pomodoro with START/PAUSE/RESET, progress bar (accent), `setInterval` in `useEffect` cleared on unmount. Purely local.

- [ ] **Step 4:** Add the fixed blob gradients + grid overlay to `AppShell.tsx` (two `data-blob` divs using `--accent`/`--g2`, and a grid div using `--grid-opacity`), positioned `fixed`, `pointer-events:none`, behind content. Confirm `AppShell` background is `var(--bg)`.

- [ ] **Step 5: Verify.** `bun --cwd web run lint && bun --cwd web run build` → clean; Dashboard loads real stats/tasks/decks against the live backend, timer works, blobs/grid render and vanish under reduced-motion, no mock strings remain.

**PHASE 1 GATE:** lint + build clean; app shell + Dashboard fully Axiom-styled and wired; theme/accent/grid persist. User reviews before Phase 2.

---

# PHASE 2 — Notes, Flashcards, Ask/Search

The Axiom-native content screens. Each task: confirm endpoint shapes in `server.py`, rebuild the page with `ui/` primitives in Axiom's layout, wire all real actions, keep `.axscreen`, verify lint+build+browser with real data.

### Task 2.1: Notes

**Files:** Modify `web/src/app/notes/page.tsx`; reuse `web/src/components/NoteEditor.tsx`, `NoteMarkdown.tsx`, `lib/noteLinks.tsx`, `lib/markdown.ts`; extend `api.ts`.

**Interfaces:** Consumes `NotePreview`, `getJSON`; add helpers for `GET /api/notes/{id}`, `PUT /api/notes/{id}` (edit), `PATCH /api/notes/{id}` (move), `DELETE /api/notes/{id}`, `GET /api/notes/{id}/download`, `GET /api/notes/export`, `POST /api/notes/import`. Confirm each shape in `server.py`.

- [ ] **Step 1:** Left list rail (270px glass): search input + `+` button; note buttons with title/preview/meta, accent left-edge on active (Axiom Notes layout). Data from `GET /api/notes`.
- [ ] **Step 2:** Reader pane: mono meta line, title, tag chips, a bordered **AI SUMMARY** block (only if the note actually has a summary field — otherwise omit; do not fabricate), and markdown body via the existing `NoteMarkdown`. Preserve existing editing (`NoteEditor`), move, delete, download, export/import actions, restyled to Axiom.
- [ ] **Step 3: Verify.** lint+build clean; list loads real notes, opening/editing/moving/deleting/downloading a note works against the backend.

### Task 2.2: Flashcards

**Files:** Modify `web/src/app/flashcards/page.tsx`; extend `api.ts`.

**Interfaces:** Add helpers for `GET /api/flashcards`, `GET /api/flashcards/{deck_id}`, `DELETE /api/flashcards/{deck_id}`. Confirm the card/deck shape (question/answer fields) in `server.py`.

- [ ] **Step 1:** Deck picker (list of real decks with counts). Selecting a deck loads its cards.
- [ ] **Step 2:** Axiom flip-card: progress bar, card counter, tap-to-flip (QUESTION/ANSWER), SRS grade row (AGAIN/HARD/GOOD/EASY). If the backend persists review grades, wire them; if grading is client-only (no endpoint), advance locally and label the screen honestly (no fake "scheduled in 4d" unless the backend returns intervals). Deck delete wired.
- [ ] **Step 3: Verify.** lint+build clean; real decks/cards load, flip + advance work, delete works.

### Task 2.3: Ask / Search (full page)

**Files:** Modify `web/src/app/search/page.tsx`; extend `api.ts`.

**Interfaces:** `askText` (from Task 1.6); add `askAudio(blob): Promise<...>` for `POST /api/ask/audio`; add `getChat()`/`clearChat()` for `GET`/`DELETE /api/chat`. Confirm shapes in `server.py`.

- [ ] **Step 1:** Full-page conversational Ask: history from `GET /api/chat`, input + submit (`/api/ask`), mic capture → `/api/ask/audio`, clear-history (`DELETE /api/chat`). Axiom styling (mono labels, glass message panels, accent user bubbles).
- [ ] **Step 2:** Subject filter if `AskRequest` supports `subject` (from `/api/subjects`).
- [ ] **Step 3: Verify.** lint+build clean; text + audio ask return real answers, history loads and clears.

**PHASE 2 GATE:** lint+build clean; Notes/Flashcards/Search Axiom-styled and wired with real data. User reviews.

---

# PHASE 3 — Files/Upload, Tasks, Calendar

### Task 3.1: Files / Library + Upload

**Files:** Modify `web/src/app/files/page.tsx`; extend `api.ts`.

**Interfaces:** Consumes `Item`, `Subject`, `RetryResult`; add helpers for `GET /api/items`, `POST /api/upload` (multipart), `POST /api/items/{id}/retry`, `GET /api/subjects`, `POST /api/subjects`, and the file/image stream URLs. Confirm `upload` form fields (file, subject, kind) in `server.py`.

- [ ] **Step 1:** Axiom-style item grid/list: filename, kind, status (pending/done/error with accent/red states), subject, created (`timeAgo`). Subject filter from `/api/subjects`.
- [ ] **Step 2:** Upload panel (drag/drop or file input) → `POST /api/upload` (multipart via `fetch`, not `postJSON`); show ingest status; `retry` button on failed items → `POST /api/items/{id}/retry`. Create-subject action.
- [ ] **Step 3: Verify.** lint+build clean; real items list, upload ingests a file, retry works.

### Task 3.2: Tasks

**Files:** Modify `web/src/app/tasks/page.tsx`; extend `api.ts`.

**Interfaces:** Add `Task` type + helpers for `GET/POST /api/tasks`, `PATCH /api/tasks/{id}`, `DELETE /api/tasks/{id}`. Confirm `TaskCreate`/`TaskPatch` fields in `server.py`.

- [ ] **Step 1:** Axiom plan-list: task rows (time/checkbox dot/title/tag) with create, toggle-complete (PATCH), edit, delete. Empty state.
- [ ] **Step 2: Verify.** lint+build clean; full task CRUD works against the backend.

### Task 3.3: Calendar (Planner week-grid)

**Files:** Modify `web/src/app/calendar/page.tsx`; reuse `web/src/components/CalendarWidget.tsx`; extend `api.ts`.

**Interfaces:** Add helpers for `GET /api/calendar/google/status`, `GET /api/calendar/google/auth-url`, `DELETE /api/calendar/google`, `POST /api/calendar/google/sync`, `GET /api/calendar/google/events?time_min&time_max`, `GET /api/calendar/proposals`, `POST /api/calendar/proposals/{id}/approve`, `POST .../dismiss`. Confirm shapes in `server.py`.

- [ ] **Step 1:** Axiom 7-column week grid (from Axiom Planner) rendering real events from `/api/calendar/google/events` for the visible week; today column highlighted with accent.
- [ ] **Step 2:** Google Calendar connect/disconnect/sync controls (status-driven); proposals list with approve/dismiss actions, Axiom-styled.
- [ ] **Step 3: Verify.** lint+build clean; week grid shows real events (when connected), connect flow reachable, proposals approve/dismiss work.

**PHASE 3 GATE:** lint+build clean; Files/Tasks/Calendar Axiom-styled and wired. User reviews.

---

# PHASE 4 — Audiobooks, Handwriting, Video, Settings

### Task 4.1: Audiobooks

**Files:** Modify `web/src/app/audiobooks/page.tsx`; extend `api.ts`.

**Interfaces:** Consumes `Audiobook`; add helpers for `GET /api/audiobooks`, `GET /api/audiobooks/jobs`, `POST /api/audiobooks` (generate), and the `GET /api/audiobooks/{name}` file stream. Confirm `AudiobookRequest` fields in `server.py`.

- [ ] **Step 1:** Axiom card list of audiobooks (name, created `timeAgo`, size) with an inline audio player. Generate panel (source selection per `AudiobookRequest`) + live job status from `/api/audiobooks/jobs`.
- [ ] **Step 2: Verify.** lint+build clean; list loads, generate starts a job, job status updates, playback works.

### Task 4.2: Handwriting

**Files:** Modify `web/src/app/handwriting/page.tsx`; extend `api.ts`.

**Interfaces:** Consumes `HwPage`, `HwLine`, `HwPageDetail`, `HwStatus`; add helpers for `POST /api/handwriting/upload`, `GET /api/handwriting/pages`, `GET /api/handwriting/pages/{id}`, `PATCH /api/handwriting/lines/{id}`, `POST /api/handwriting/pages/{id}/to-notes`, `GET /api/handwriting/status`, plus crop/page image URLs. Confirm in `server.py`.

- [ ] **Step 1:** Upload → pages list (status) → page detail with line crops + predicted text + editable correction (PATCH per line) → "to notes" action. Axiom styling.
- [ ] **Step 2: Verify.** lint+build clean; upload processes a page, corrections save, to-notes creates a note.

### Task 4.3: Video review

**Files:** Modify `web/src/app/video/page.tsx`; reuse `web/src/components/VideoModal.tsx`; extend `api.ts`.

**Interfaces:** Consumes `VideoFrame`, `VideoSegment`; add helpers for `GET /api/video/frames`, `GET /api/video/frames/{id}`, `GET /api/video/frames/{id}/segments`, `POST /api/video/frames/{id}/verify`, `DELETE /api/video/frames/{id}`, `GET /api/video/frames/{id}/ocr-stream` (SSE/EventSource), plus image URLs. Confirm in `server.py`.

- [ ] **Step 1:** Axiom frame board: frames grid (thumbnail, title, status awaiting_review/auto_processed/reviewed), open a frame → segments with OCR text/table markdown, live OCR stream via `EventSource`, verify + delete actions.
- [ ] **Step 2: Verify.** lint+build clean; frames load, segments/OCR render, verify + delete work.

### Task 4.4: Settings

**Files:** Modify `web/src/app/settings/page.tsx`.

**Interfaces:** Consumes `useTheme()` (`ThemeProvider`), `ACCENTS` (`lib/prefs.ts`).

- [ ] **Step 1:** Axiom grouped-rows settings. **APPEARANCE** group real and functional: theme (dark/light) toggle, accent swatch picker (4 options → `setAccent`), grid overlay toggle (`setGrid`) — all persisted. Other groups (STUDY/AI) only if backed by a real endpoint; otherwise omit rather than show non-functional toggles.
- [ ] **Step 2: Verify.** lint+build clean; changing theme/accent/grid updates the whole app live and survives reload.

**PHASE 4 GATE:** lint+build clean; all 11 screens Axiom-styled and wired; no mock data anywhere. Full app review.

---

## Self-Review (against the spec)

- **Spec coverage:** All 11 screen-mapping rows have a task (1.7 Dashboard, 2.1 Notes, 2.2 Flashcards, 2.3 Ask/Search, 3.1 Files, 3.2 Tasks, 3.3 Calendar, 4.1 Audiobooks, 4.2 Handwriting, 4.3 Video, 4.4 Settings). Design-system, shell, ask bar, theme/accent, blobs/grid, reduced-motion, and fonts all have tasks (1.1–1.6, 1.7 Step 4). ✔
- **Phasing** matches spec (4 phases, same groupings, same gates). ✔
- **Non-goals** honored: no backend changes; only new font dep; no dc-runtime port. ✔
- **Placeholder policy:** foundation tasks carry concrete code; screen tasks intentionally specify exact files/endpoints/types/layout/acceptance and instruct confirming shapes in `server.py` rather than hardcoding assumed JSON — deliberate, because final JSX depends on primitives and real response shapes established in Phase 1. This avoids fabricating field names (the user's stated concern). ✔
- **Type consistency:** helper names introduced once (`askText`, `askAudio`, `getChat`, `Task`, `Deck`) and reused; primitive names stable across tasks. ✔
