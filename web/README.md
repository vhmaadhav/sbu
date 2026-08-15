# Study Buddy web

> The responsive Next.js 16 workspace for Study Buddy — built with React 19,
> TypeScript, Tailwind CSS v4, Framer Motion, Manrope for interface copy, and
> Space Grotesk for display type.

The App Router pages cover the dashboard, files and capture, notes, cited
search, tasks, flashcards, handwriting review, video-board review, audiobooks,
question-paper generation, Google Calendar, and settings.

<table>
  <tr>
    <td align="center"><img src="../docs/images/notes.png" width="400" /><br /><strong>Notes</strong></td>
    <td align="center"><img src="../docs/images/search.png" width="400" /><br /><strong>Ask My Notes</strong></td>
  </tr>
  <tr>
    <td align="center"><img src="../docs/images/flashcards.png" width="400" /><br /><strong>Flashcards</strong></td>
    <td align="center"><img src="../docs/images/question-papers.png" width="400" /><br /><strong>Question Papers</strong></td>
  </tr>
</table>

## Development

From the repository root, start the frontend with one command:

```bash
make frontend
```

The first run installs dependencies when needed. Open
[http://localhost:3000](http://localhost:3000). The API is expected at port 8010
by default; set `STUDY_BUDDY_API_URL` to override it. `FRONTEND_HOST` and
`FRONTEND_PORT` control the development server bind address.

## Calendar

The Calendar page connects Google OAuth, renders monthly Google events, and
shows schedules extracted from uploaded notes, screenshots, and other source
material.

Selecting **Reschedule** asks the backend for a current conflict plan. Plans
with no complex consequences are applied immediately. Cross-day moves, large
cascades, and fixed or attendee conflicts are displayed with their proposed
old and new times before confirmation. Blocked plans explain which event must
be handled in Google Calendar before planning again.

The frontend never computes scheduling policy itself; it renders and confirms
the backend's persisted plan so web and future clients share the same rules.

## Question papers

The Question papers page lets users select one or more notes, choose difficulty
and duration, and configure the number of MCQ, short-answer, and long-answer
questions. It displays calculated marks before generation, stores completed
papers, toggles the answer key in place, and downloads separate print-ready PDF
files for students and answer keys. Generation is queued in the backend and polled
from the page, so long local-model runs continue if the user navigates away and
cannot fail because of an HTTP proxy timeout.

## Checks

```bash
bun --cwd web run lint
bun --cwd web run build
```

## Accessibility

**Dyslexia-friendly reading** (Settings → READING) sets `data-dyslexic="true"`
on `<html>`, which swaps `--font-body` to OpenDyslexic and opens up letter,
word, and line spacing; long-form surfaces (`.study-note`, `.axscreen`) also
get a 66ch measure. It is stored alongside the other appearance prefs under
`axiom-prefs` and applied pre-hydration by the bootstrap script in
`layout.tsx`, so there is no font flash on load.

Use `var(--font-body)` (or Tailwind's `font-sans` / `font-display`) for body
copy so it follows the toggle. `--font-mono` is deliberately never swapped —
the small uppercase labels and code stay clearer in JetBrains Mono.

OpenDyslexic ships via `@fontsource/opendyslexic` (SIL Open Font License) and is
self-hosted; the browser only fetches the files once the toggle is on.
