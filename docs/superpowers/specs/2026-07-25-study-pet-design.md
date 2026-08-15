# Study Pet — Design

Date: 2026-07-25

## Summary

A floating desktop creature for macOS that watches which application and browser
tab is in front, notices when the user drifts into distraction, and nudges them
back to studying. The pet walks along the bottom of the screen toward the
offending window and speaks in a bubble. Its lines are grounded in the user's
real Study Buddy data: upcoming deadlines, open tasks, and weakest concepts.

Escalation is rule-driven and deterministic. The local LLM writes only the
dialogue. Everything runs on the machine; no activity data leaves it and none is
written to disk.

## Goals

- Detect distraction from frontmost app plus active browser tab.
- Escalate visibly and predictably over minutes, not instantly.
- Ground nudges in real study context so they are specific, not generic.
- Run as its own process next to the existing menu-bar app, reusing its stack.

## Non-goals

- Blocking, closing, or interfering with any application.
- Full-screen takeovers or any escalation the user cannot ignore.
- Screenshots or vision-model analysis of screen content.
- Windows, Linux, Android, or web surfaces.

## Architecture

A new `backend/pet/` package run as `python -m pet`, separate from
`python -m buddy.menubar`. Six units, each with one responsibility, plus a
runner that drives them.

| Unit | Responsibility | Depends on |
|---|---|---|
| `watcher.py` | Every `PET_POLL_SECONDS`, produce an `ActivitySample`: frontmost app name, window title, and for Safari/Chrome/Arc the active tab title and URL host. | PyObjC `NSWorkspace`, AppleScript |
| `classifier.py` | `ActivitySample -> "study" \| "distraction" \| "neutral"`. Rules table first; unmatched app/host pairs go to the local LLM once and are cached. | `core.llm`, rules config |
| `state.py` | Escalation state machine. Consumes labelled samples, owns dwell timers and the stage ladder, emits `NudgeEvent`s. Pure functions over a timeline, no I/O. | none |
| `context.py` | Fetch study context from the backend over HTTP, cached, degrading to empty on failure. | `httpx` |
| `voice.py` | Turn `NudgeEvent` + context + current activity into one line of dialogue. | `core.llm` |
| `window.py` | The floating pet: borderless transparent always-on-top `NSWindow` with `NSImageView`, sprite animation, walking, speech bubble. Renders `(mood, position, bubble_text)`. | PyObjC |

`runner.py` owns the 5-second loop and wires the units together.

The pet talks to the backend over HTTP rather than importing `core.db`, because
`compose.yaml` means the backend may run in a container while the pet runs
natively on the Mac.

### Data flow

```
watcher (tick) -> ActivitySample
               -> classifier -> label
               -> state       -> NudgeEvent(stage, mood, target_window)
                              -> voice (+ context snapshot) -> line
                              -> window.render(mood, walk_to, bubble)
```

`context.py` refreshes on a background interval; `voice.py` reads only its last
good snapshot, so a slow or unavailable backend can never stall the loop. The
LLM call in `voice.py` has a 1.5-second timeout and falls back to a canned line.

## Detection

`watcher.py` returns:

```python
@dataclass(frozen=True)
class ActivitySample:
    at: float            # monotonic seconds
    app: str             # frontmost application name
    title: str           # frontmost window title, may be ""
    host: str | None     # active tab URL host, browsers only
    tab_title: str | None
```

Frontmost app comes from `NSWorkspace.sharedWorkspace().frontmostApplication()`.
For Safari, Chrome, and Arc the active tab title and URL are read via
AppleScript; if automation permission is denied the sample carries `host=None`
and classification falls back to app name alone.

`classifier.py` resolves a label in this order:

1. Explicit user rules from config (`PET_STUDY_APPS`, `PET_DISTRACT_HOSTS`).
2. Built-in defaults: Study Buddy, Preview, Notes, Obsidian, terminals, IDEs,
   and known learning domains as study; known video, social, and gaming hosts
   as distraction.
3. Cached LLM verdict keyed by `(app, host)`.
4. One LLM call classifying the app/host pair, result cached in memory for the
   process lifetime.

`neutral` is the label for anything the LLM declines to place, and for system
UI such as Finder or the lock screen.

## Escalation

`state.py` tracks distraction dwell in seconds. Study resets dwell to zero.
Neutral neither resets nor increases dwell: for each second of neutral, dwell
decreases by half a second, floored at zero.

| Dwell | Stage | Behaviour |
|---|---|---|
| 0–90s | `calm` | Idle at screen edge, happy sprite, silent. |
| 90s | `notice` | Concerned sprite, stands and turns to face the offending window. No dialogue. |
| 3 min | `concerned` | Walks to the x-centre of the distracting window, speech bubble with a light, specific line. |
| 6 min | `nag` | Bubble carries study context: nearest deadline or weakest concept. |
| 10 min | `plead` | Sad sprite, sits under the window, repeats every 4 min while distraction continues. |

Recovery: 60 continuous seconds classified as study emits a `recovered` event —
happy sprite, one acknowledgement bubble — and resets the ladder to `calm`.

Two invariants hold regardless of input: at most one bubble per 90 seconds, and
stages advance one step at a time (no skipping from `calm` to `nag`).

## Study context

`context.py` fetches and caches, refreshing every 5 minutes:

- `GET /api/tasks` — open tasks with due dates.
- `GET /api/learn/gaps` — weakest concepts.
- `GET /api/calendar/google/events` — upcoming events within 8 days.

It exposes a single `ContextSnapshot` with a small, flat shape: `next_deadline`,
`open_task_count`, `weakest_concepts` (up to three names). Any failed or
unconfigured endpoint contributes nothing; the snapshot is never partially
invalid, only less populated.

## Dialogue

`voice.py` builds a prompt from the stage, the current activity, and the context
snapshot, and calls `core.llm.chat`. Constraints enforced after generation:

- Single sentence, hard cap 120 characters, truncated at a word boundary.
- No newlines, no markdown, no quotes.
- Empty, over-long-after-truncation, or timed-out results fall back to a canned
  line pool keyed by stage.

Tone is warm and a little pointed; it never insults the user and never
references anything outside the current activity and the context snapshot.

## Rendering

`window.py` owns a borderless, transparent, non-activating, always-on-top
`NSWindow` at `NSStatusWindowLevel`, ignoring mouse events except on the pet
itself.

Sprites are horizontal strips at `assets/pet/<mood>.png` with 64×64 frames, plus
`assets/pet/meta.json` giving frame count and fps per mood. Moods: `idle`,
`walk`, `concerned`, `sad`, `alert`.

`scripts/gen_pet_sprites.py` generates placeholder strips with Pillow so the
system is runnable and testable before any artwork exists. Replacing the art is
a file swap with no code change.

Walk targeting uses `CGWindowListCopyWindowInfo` to get the frontmost window's
bounds and walks along the bottom of that display to its horizontal centre. When
bounds are unavailable the target degrades to the nearest screen edge through
the same code path.

## Control

The pet's process exposes a small menu-bar item with `Pause` and `Quit`. Pause
stops the loop and hides the window; the rationale is that an always-on-top
window that speaks during a screen-shared presentation would otherwise be
uninterruptible.

## Configuration

Added to `core/config.py`, read from the environment like the rest of the
project:

| Name | Default | Meaning |
|---|---|---|
| `PET_POLL_SECONDS` | `5` | Sampling interval. |
| `PET_NOTICE_SECONDS` | `90` | Dwell before `notice`. |
| `PET_CONCERNED_SECONDS` | `180` | Dwell before `concerned`. |
| `PET_NAG_SECONDS` | `360` | Dwell before `nag`. |
| `PET_PLEAD_SECONDS` | `600` | Dwell before `plead`. |
| `PET_RECOVERY_SECONDS` | `60` | Study time before reset. |
| `PET_BUBBLE_COOLDOWN` | `90` | Minimum seconds between bubbles. |
| `PET_BACKEND_URL` | `http://127.0.0.1:8010` | Backend base URL. |
| `PET_STUDY_APPS` | `""` | Comma-separated app names forced to study. |
| `PET_DISTRACT_HOSTS` | `""` | Comma-separated hosts forced to distraction. |

## Privacy

Activity samples live in an in-memory ring buffer of the last 200 entries and
are never written to disk. Classification uses local LM Studio only. No window
titles, URLs, or study context are sent anywhere off the machine.

## Testing

Tests live in `backend/tests/`, following `test_menubar.py`.

- `test_pet_classifier.py` — rules precedence, host matching, LLM called once
  per pair and cached, unknown input yields neutral when LLM unavailable.
- `test_pet_state.py` — synthetic timelines asserting each threshold, neutral
  pausing without resetting, study resetting, recovery emission, bubble cooldown
  under a hostile timeline, no stage skipping.
- `test_pet_voice.py` — length cap and truncation, newline and markdown
  stripping, canned fallback when the LLM raises or times out.
- `test_pet_context.py` — snapshot assembly, per-endpoint failure degrading to
  empty rather than raising, cache respected within the refresh interval.

`window.py` and `watcher.py` wrap platform APIs and are kept thin enough that
all decision logic sits upstream of them; they are exercised manually.

## Risks

- **Sprite art.** Placeholder generation removes the blocking dependency, but
  the pet looks like a placeholder until real art lands.
- **AppleScript automation permission.** First run prompts for control of the
  browser. Denied permission degrades detection to app-name only, which cannot
  distinguish a lecture from a music video in the same browser.
