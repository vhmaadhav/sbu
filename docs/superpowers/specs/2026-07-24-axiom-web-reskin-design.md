# Axiom Web Reskin — Design

**Date:** 2026-07-24
**Status:** Approved for planning
**Scope:** Rebuild the Study Buddy `web/` frontend UI in the Axiom design language, in place, with every existing backend feature wired. No backend changes.

## Problem

The `web/` Next.js app works and covers the full backend, but the user wants its
look-and-feel replaced with the "Axiom" design. Axiom ships only as a
self-contained HTML mockup built on a proprietary `dc-runtime` component format
(`<x-dc>` templates + a `DCLogic` class, all data hardcoded). It defines **5
screens** (Dashboard, Notes, Flashcards, Planner, Settings) plus a header "Ask
Axiom" AI bar. The real product has **11 feature areas** backed by ~50 FastAPI
routes. A literal port would drop most of the product. The task is therefore a
*reskin*: adopt Axiom's visual language and extend it across all real features.

## Decisions (locked with user)

1. **Approach:** Reskin the existing Next.js 16 + React 19 + Tailwind v4 app *in
   place*. Keep the working API client (`web/src/lib/api.ts`) and the Next
   rewrites proxy to FastAPI. Do **not** port `dc-runtime`.
2. **Scope:** All 11 feature areas, delivered in **4 reviewable phases**.
3. **Fidelity:** Faithful to Axiom's 5 defined screens; extend the same language
   to the other 6 screens so the product feels cohesive.

## Axiom design language (source of truth)

Extracted from the decoded mockup. Reproduce these as the design system:

- **Palette (dark-first).** `--bg:#070b11`; glass panels
  `--panel:rgba(12,18,27,.55)` / `--panel2:rgba(18,27,41,.7)` with
  `backdrop-filter: blur(16px) saturate(1.4)`; borders
  `--line:rgba(140,175,215,.14)` / `--line2:rgba(140,175,215,.28)`; text
  `--text:#dce7f3`, `--dim:#677c93`, `--faint:#3d4d60`. Light theme variant:
  `--bg:#eef2f7`, panels on white, `--text:#17222f` (values in mockup).
- **Accent.** A single `--accent` CSS variable. Four swatches offered:
  teal `#5eead4`, sky `#7dd3fc`, violet `#c4b5fd`, rose `#fda4af`.
  User-selectable; persisted to `localStorage`.
- **Type.** Space Grotesk for body/display (already loaded); **add JetBrains
  Mono** (via `next/font/google`) for all-caps labels, numerals, breadcrumbs,
  tags, and metadata. Mono labels use `letter-spacing` ~`0.16–0.24em`, sizes
  9–11px, color `--dim`/`--faint`.
- **Ambience.** Two fixed drifting radial-gradient blobs
  (`@keyframes blobDrift`); an optional 56px grid overlay (toggle in Settings);
  `@keyframes screenIn` for page/section entry; `@keyframes pulse` for live
  status dots. All gated behind `@media (prefers-reduced-motion: reduce)`.
- **Surface style.** Square corners (no border-radius on panels), 1px hairline
  borders, accent left-edge (2px) to mark active/selected rows, subtle accent
  glow (`box-shadow: 0 0 Npx -Mpx var(--accent)`) on primary/active elements.

## Architecture

Unchanged app architecture; the work is UI-layer. Layers:

- **Tokens & globals** — `web/src/app/globals.css` (+ `layout.tsx` for fonts):
  the Axiom token set, keyframes, and `[data-theme]` / `--accent` wiring.
- **Primitives** — a small shared set under `web/src/components/ui/` so screens
  stay consistent and files stay focused:
  - `Panel` — glass card wrapper (header slot + body).
  - `MonoLabel` — all-caps JetBrains-Mono label.
  - `StatTile` — dashboard/metric tile.
  - `SectionHeader` — panel header row (mono title + optional action link).
  - `GlowButton` — accent-bordered button with hover-fill + glow.
  - `AccentToggle` / `ThemeToggle` — appearance controls.
  These wrap real data; no hardcoded content lives in primitives.
- **Shell** — `AppShell`, `Sidebar`, `Topbar` rebuilt to Axiom's rail + header.
- **Screens** — the 11 route pages under `web/src/app/*`, each wired to its
  real endpoints via `lib/api.ts` (extend the client with typed helpers as
  needed; keep `getJSON`/`postJSON` and add put/patch/delete/upload helpers).

### Theme & accent state

A tiny client provider (or `AppShell`-level state) reads `theme` and `accent`
from `localStorage` on mount, applies `data-theme` + `--accent` to the root, and
exposes setters used by the Settings screen and the sidebar toggle. Default:
dark theme, teal accent, grid on. Avoids hydration flash by reading in a
`beforeInteractive`-style inline script or defaulting server render to dark.

## Shell design

- **Sidebar (224px glass rail).** `A` logo mark + `AXIOM` / `STUDY SYSTEM`
  wordmark. Numbered nav items (`01`–`NN`), accent left-edge + `--panel2`
  background on active, `--dim`→`--text` on hover. Retains the existing
  `Workspace` / `Learn` group labels rendered as Axiom mono section headers.
  Bottom: theme toggle (mono label + knob switch) and user chip. All 11
  destinations present. Existing mobile-drawer open/close behavior preserved.
- **Topbar (60px glass header).** Left: breadcrumb `AXIOM / <SCREEN>` in mono.
  Center: **Ask bar** — `›` prompt glyph, text input, `AI` chip; wired to real
  `/api/ask` (Enter to submit) and the existing audio-ask (`/api/ask/audio`).
  Focus/submit opens the Axiom dropdown answer panel (`ANALYZING…` →
  answer → follow-up chips). Right: `SYNCED` pulse dot + live clock.

## Screen mapping (all wired to real endpoints)

| Screen | Route | Axiom pattern | Endpoints |
|---|---|---|---|
| Dashboard | `/` | greeting, 4 stat tiles, Today's Plan, Focus Timer, Cards Due | `/api/stats`, `/api/tasks`, `/api/flashcards`, `/api/activity`; timer local |
| Notes | `/notes` | list rail + reader with AI-summary block + tags | `/api/notes`, `/api/notes/{id}` (GET/PUT/PATCH/DELETE), download, export/import |
| Flashcards | `/flashcards` | flip card + SRS grade row + deck picker | `/api/flashcards`, `/api/flashcards/{deck}`, delete |
| Ask / Search | `/search` | full-page conversational treatment of the ask bar | `/api/ask`, `/api/ask/audio`, `/api/chat` (GET/DELETE) |
| Files / Library | `/files` | Axiom grid/list + upload/ingest + retry | `/api/items`, `/api/upload`, `/api/items/{id}/retry`, file/image endpoints, `/api/subjects` |
| Tasks | `/tasks` | Axiom plan-list styling, full CRUD | `/api/tasks` (GET/POST/PATCH/DELETE) |
| Calendar | `/calendar` | Axiom Planner week-grid + Google connect + proposals | `/api/calendar/google/*`, `/api/calendar/proposals*` |
| Audiobooks | `/audiobooks` | Axiom card list + generate + job status | `/api/audiobooks`, `/api/audiobooks/jobs`, POST generate, file stream |
| Handwriting | `/handwriting` | upload → line crops → correct → to-notes | `/api/handwriting/*` (upload, pages, lines PATCH, to-notes, status) |
| Video | `/video` | frame board → segments → OCR/verify | `/api/video/*` (frames, segments, image, ocr-stream, verify, delete) |
| Settings | `/settings` | Axiom grouped rows + theme/accent/grid controls | local prefs; real toggles where backend supports |

Notes on mapping:
- Axiom merges tasks/calendar into one "Planner." We keep **Tasks** and
  **Calendar** as separate routes (distinct backends) but render Calendar with
  Axiom's week-grid "Planner" visual.
- The Dashboard "Today's Plan," "Cards Due," and stats use real task/flashcard/
  stats data, not the mockup's canned strings. The Focus Timer stays a local
  client feature (no backend), matching Axiom.
- Any screen area Axiom didn't define (Files, Audiobooks, Handwriting, Video)
  is newly designed in the same language (glass `Panel`s, mono labels, accent
  edges), preserving the current pages' real functionality.

## Phasing

Each phase ends with lint + build clean and a live browser check against the
running backend; user reviews before the next phase starts.

1. **Foundation + shell + Dashboard** — tokens, JetBrains Mono, keyframes,
   theme/accent provider, `ui/` primitives, `Sidebar`/`Topbar`/`AppShell`, the
   Ask bar, and the Dashboard wired to real stats/tasks/flashcards/activity.
2. **Notes + Flashcards + Ask** — the Axiom-native content screens, wired
   including edit/move/delete/download and the full-page Ask/chat experience.
3. **Files/Upload + Tasks + Calendar** — data-entry-heavy screens: upload/
   ingest/retry, task CRUD, calendar week-grid + Google connect + proposals.
4. **Audiobooks + Handwriting + Video + Settings** — the net-new screens plus
   the appearance/preferences panel.

## Testing & verification

- **Static:** `bun --cwd web run lint` and `bun --cwd web run build` must pass
  clean at the end of every phase.
- **Runtime:** Start backend (port 8010) + frontend, load each new/changed
  screen in the browser, confirm real data renders and primary actions work
  (upload, ask, task CRUD, flashcard grade, note edit, calendar connect,
  audiobook generate, handwriting correct, video verify). No mock/hardcoded
  content may remain in shipped screens.
- **Accessibility/motion:** verify `prefers-reduced-motion` disables blob/grid/
  screenIn animation; verify keyboard focus is visible on the dark palette.

## Non-goals

- No backend/API changes.
- No new runtime dependencies beyond the JetBrains Mono font.
- No literal `dc-runtime` port.
- No new features beyond what the backend already exposes (the reskin surfaces
  existing capability; it does not invent product scope).

## Risks & mitigations

- **Hydration flash of theme.** Mitigate by defaulting SSR to dark and applying
  stored prefs in an inline pre-hydration script.
- **Contrast on glass panels.** Verify text tokens against panel backgrounds in
  both themes; adjust `--dim`/`--faint` if any label fails legibility.
- **Scope creep across 11 screens.** Phase gates + "no mock data" verification
  keep each screen honestly wired before moving on.
