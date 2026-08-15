# Adaptive Learning Path — Design

**Date:** 2026-07-25
**Status:** Approved

## Purpose

Add an adaptive mastery engine to Study Buddy: the student names an exam goal, the
system builds a concept graph bound to their own notes, measures mastery through
short diagnostics and drills, finds knowledge gaps and missing prerequisites, plans
each day's session, schedules revision against a forgetting model, and reports
progress through six charts.

This is a single vertical slice covering all fourteen workflow steps at demo depth.
Each subsystem is deliberately simple but complete and end-to-end.

## Decisions

| Question | Choice |
|---|---|
| Concept graph source | Exam name → LLM, each concept bound to the student's chunks by vector search |
| Question source | Generated on demand by the LLM, with the next item prefetched during answering |
| Mastery model | Bayesian Knowledge Tracing |
| Forgetting model | Exponential decay / memory half-life |
| Navigation | One `/learn` section as a linear journey: goal → gaps → improve → report |
| Session selection | Planner-built session by default, plus per-concept drill from the gap list |
| Misconceptions | Distractors carry misconception tags written at generation time |
| Charts | Concept map, mastery over time, weak-area bars, forgetting-risk curves, misconception frequency, weekly delta |
| Chart rendering | Hand-rolled inline SVG on Axiom CSS variables; no chart library |
| Motion | CSS transitions and keyframes only; no framer-motion |

### Rejected

- SM-2 / FSRS scheduling — no continuous risk value to plot (SM-2), or 17 parameters
  with nothing to fit them on (FSRS).
- Elo / IRT mastery — needs a population of students to estimate item difficulty.
- Post-hoc embedding clustering of wrong answers — needs weeks of data before
  clusters mean anything; tagged distractors work from the first wrong answer.
- Persisting the learning path — it is the ordered output of gap ranking, recomputed
  on demand. Storing it would only create a cache to invalidate.
- Streak heatmap — shows effort, not learning.

## Theme constraint

The existing Axiom design language is fixed. No new colors, no new typography, no
new component vocabulary. Every mark in every chart uses
`color-mix(in srgb, var(--accent) N%, transparent)` for fills, `var(--line)` for
gridlines, `var(--dim)`/`var(--faint)` for labels, and `var(--warn)` for weak and
at-risk states. No SVG carries a hardcoded hex. Charts render inside the existing
`Panel` surface with `SectionHeader` and `MonoLabel`. Both light and dark themes
are supported by construction, since every value derives from a token.

One token is added: `--warn`, the foreground form of the rose already behind
`--chip-orange`. The `--chip-*` tokens are ~16% transparent because they are chip
*backgrounds*; strokes, text, and bar fills marking a weak state need the solid
hue, and compositing a chip token again yields an unreadable grey. `--warn` is
`#fda4af` on dark (exactly the hue `--chip-orange` is mixed from) and a deepened
`#be3455` on light, where the pale rose would not carry against the page. This is
a naming addition, not a palette change — no new hue enters the system.

The mastery ramp floors at 25% accent rather than 0 so a weak concept remains
visible against the light theme's pale panels.

## Data model

Ten tables appended to the `SCHEMA` string in `backend/core/db.py`, created by the
same idempotent `init_db()` path as everything else.

| Table | Columns (essential) |
|---|---|
| `exam_goals` | id, name, slug, status (`building`/`ready`/`error`), error, created_at |
| `concepts` | id, goal_id, name, blurb, tier |
| `concept_edges` | prereq_id, concept_id (the prerequisite DAG) |
| `concept_sources` | concept_id, chunk_id, score |
| `mastery` | concept_id PK, p_known, attempts, correct, half_life, last_review_at, in_srs |
| `mastery_history` | id, concept_id, p_known, created_at |
| `questions` | id, concept_id, stem, options_json, answer_index, explanation, created_at |
| `attempts` | id, session_id, question_id, concept_id, chosen_index, correct, misconception, latency_ms, created_at |
| `sessions` | id, goal_id, kind (`diagnostic`/`study`/`review`), status, created_at, completed_at |
| `session_items` | id, session_id, position, concept_id, question_id, kind (`read`/`quiz`), done |

Two deliberate choices:

- `mastery_history` is append-only rather than derived from `attempts`, so the
  learning-curve chart is one indexed read instead of a replay of the BKT chain.
- Misconception tags live on the option inside `questions.options_json`; `attempts`
  records the tag by copy, so grouping stays a plain `GROUP BY` even if a question
  is regenerated.

## Backend modules

Added under `backend/core/`, following the one-file-one-job convention.

- **`concepts.py`** — build the concept graph from an exam name via `llm.chat_json`,
  assign tiers by topological depth, bind each concept to note chunks with
  `vectorstore.search`. Runs in a background thread; the goal row carries the status.
- **`mastery.py`** — BKT posterior update, half-life growth and decay, `recall()`
  and `risk()`. Pure functions over numbers plus thin persistence helpers.
- **`gaps.py`** — rank weak concepts, walk `concept_edges` upward for missing
  prerequisites.
- **`quiz.py`** — on-demand MCQ generation grounded in a concept's bound chunks,
  with a misconception tag per distractor; grading and attempt logging.
- **`planner.py`** — assemble a session queue.
- **`report.py`** — weekly aggregation: mastery deltas, misconception counts,
  remaining gaps.

Step 13's assistant adds no module: it calls `core/rag.py` with the active concept's
bound chunk ids, so answers stay cited and scoped to the student's own materials.

## Algorithms

**BKT** with `p_init=0.25`, `p_learn=0.15`, `p_slip=0.10`, `p_guess=0.25` (matching a
four-option MCQ's guess floor):

```
correct: post = p(1-slip) / (p(1-slip) + (1-p)·guess)
wrong:   post = p·slip    / (p·slip    + (1-p)(1-guess))
p' = post + (1-post)·p_learn
```

`p'` is written to `mastery` and appended to `mastery_history`.

**Confidence** = `1 - exp(-attempts/3)`. BKT has no variance of its own; this proxy
separates "tested and weak" from "never tested" for the gap list and the diagnostic
sampler.

**Forgetting.** A concept enters the SRS queue at `p_known >= 0.85` with
`half_life = 1 day`. A successful review doubles the half-life; a failure cuts it to
40% and applies the normal BKT wrong-answer update, which can eject it from the
queue. `recall = 2^(-elapsed_days / half_life)`, `risk = 1 - recall`, due when
`recall < 0.85`.

**Gap detection.** Weak at `p_known < 0.6`. For each weak concept, walk edges upward;
prerequisites under 0.5 are flagged *foundation missing* and inherit their
dependant's urgency. Ranking key: `(tier asc, p_known asc, downstream_count desc)`.

**Diagnostic.** Twelve questions, breadth-first across tiers, one per sampled
concept, biased toward low confidence. A wrong answer drops the next question to a
prerequisite; a right answer climbs a tier.

**Planner.** An eight-item queue: missing prerequisites (a `read` item plus two
quizzes each) → weakest concepts → concepts due for review. Concept-drill mode is
the same builder with a single-concept filter.

## API

All routes under `/api/learn/` in `backend/server.py`.

| Route | Purpose |
|---|---|
| `POST /api/learn/goal` | create goal, start background graph build |
| `GET /api/learn/goal` | goal and build status |
| `DELETE /api/learn/goal` | reset |
| `GET /api/learn/graph` | nodes, edges, mastery for the concept map |
| `POST /api/learn/diagnostic` | start a diagnostic session |
| `POST /api/learn/session` | `{mode: "auto" \| "concept", concept_id?}` |
| `GET /api/learn/session/{id}` | session state and queue |
| `GET /api/learn/session/{id}/next` | next item, served from prefetch |
| `POST /api/learn/attempt` | grade, update mastery, return correctness + misconception + explanation |
| `GET /api/learn/gaps` | ranked weak concepts and missing prerequisites |
| `GET /api/learn/review` | due queue and decay curve points |
| `GET /api/learn/history` | mastery-over-time series |
| `GET /api/learn/report/weekly` | deltas, misconceptions, remaining gaps |
| `POST /api/learn/ask` | RAG scoped to a concept's bound chunks |

## Error handling

- Graph build failure leaves the goal in `error` with a retry action. A half-built
  graph is never shown.
- Question generation retries once, then serves the most recent cached question for
  that concept. If none exists, the planner skips the item rather than stalling.
- LM Studio unreachable shows a banner and puts the session in read-only mode. The
  map, gaps and report still render, since they read only from SQLite.

## Frontend

One sidebar entry ("Adaptive path") and five routes under `web/src/app/learn/`:

| Route | Screen |
|---|---|
| `/learn` | goal setup, or the hub: mastery summary, **Find knowledge gaps**, **Start today's session** |
| `/learn/gaps` | "You're weak on these areas" — ranked, clickable to drill |
| `/learn/session/[id]` | study/quiz runner, also used for the diagnostic |
| `/learn/map` | full-screen concept map |
| `/learn/report` | weekly report |

Feature components in `web/src/components/learn/`, charts in
`web/src/components/charts/`. All charts share one `scale.ts` and one `ChartFrame`
owning axes, gridlines and empty state, so each chart file only draws its marks.

### Charts

- **Concept map** — tiers computed server-side, so layout is deterministic (`y` =
  tier, `x` = index within tier) with quadratic-bezier edges. No force simulation:
  no jitter, identical every run. Node radius = downstream count, fill = mastery,
  weak nodes ringed. Pan/zoom via viewBox; click to drill.
- **Mastery over time** — multi-series line over `mastery_history`, overall bold and
  per-concept faint, hover crosshair with a shared tooltip.
- **Weak-area bars** — horizontal bars; the confidence band renders as a lighter
  extent behind the fill, so "weak" and "barely tested" look different.
- **Forgetting-risk curves** — 14-day decay curves with the 0.85 threshold as a
  dashed rule; the crossing point is the scheduled review date.
- **Misconception frequency** — grouped bars, tag on the axis, click to see attempts.
- **Weekly delta** — slope chart, before → after, upward in accent, flat/down in rose.

### Motion

CSS only. Bars and lines animate via `stroke-dashoffset`, `transform` and `opacity`
with staggered `animation-delay`; question transitions cross-fade with the next item
already prefetched, so no spinner appears between questions. All animation is wrapped
in `prefers-reduced-motion: reduce` guards that collapse it to instant. Charts are
pure `viewBox` + `preserveAspectRatio` so they resize without JS measurement; the
concept map is the one exception and uses a `ResizeObserver`.

### Data flow

All fetches go through `web/src/lib/api.ts`. The session runner holds the queue
client-side and only round-trips on `POST /api/learn/attempt`, so answering feels
instant; mastery updates optimistically from the response.

## Testing

Matches the existing `unittest` + temporary `db.DB_PATH` pattern in `backend/tests/`.
`mastery.py`, `gaps.py` and `planner.py` are pure functions over fixed inputs and are
tested directly with no mocking: BKT convergence, decay math, prerequisite walk on a
hand-built DAG, queue ordering. `concepts.py` and `quiz.py` have their LLM call
patched the way `test_flashcards.py` does, asserting on parse and persist behaviour
rather than model output.
