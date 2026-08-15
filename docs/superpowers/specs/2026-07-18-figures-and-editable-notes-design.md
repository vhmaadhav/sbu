# Rich notes: embedded figures, inline visuals, editable notes, linked sources

**Date:** 2026-07-18
**Status:** Approved design → implementation

## Problem

Study Buddy synthesizes Markdown study notes from uploaded material (audio, video,
PDF, images, text). Four gaps make the notes lose important information and feel
static:

1. **Document figures are discarded.** `extract_pdf` renders each page and pulls
   *text* out via OCR, but the actual embedded picture — a photographed flowchart,
   a screenshot, a diagram — never reaches the note. A page image is kept only when
   the page is handwriting. Standalone image uploads are OCR'd but the picture is
   never shown in its note.
2. **Video frames don't reach the note when added.** `verify_video_frame`
   (`server.py:568`) turns a captured board frame into a searchable RAG chunk but
   never edits the note Markdown, so "adding" a frame does nothing visible in the
   note.
3. **Notes are not editable.** The note body is rendered read-only. The only
   `PATCH /api/notes/{id}` changes the note's subject folder, not its content.
4. **Source references are dead text.** Notes keep real markers like `[@ 12:40]`
   and `[p. 3]`, but they render as plain, unclickable text. The reader cannot jump
   to the cited moment/page or see what the source is.

## Goals

- Extract meaningful **figures** (raster *and* vector diagrams) from PDFs and
  standalone images and place them **inline** in the note, at the position of the
  text that discusses them.
- Place **video frames inline** in the note the same way (replacing the current
  trailing "Important lecture visuals" appendix), both at note-generation time and
  when a frame is added later.
- Let the user **edit a note** with a toolbar-driven editor and live rendered
  preview.
- Turn the existing **`[@ mm:ss]` / `[p. N]` markers into compact hover
  hyperlinks** that jump to the source in place and show source identity on hover.
- Keep notes and the RAG index consistent through **one shared update path**.

## Non-goals

- No change to STT, classification, calendar extraction, or the handwriting
  pipeline.
- No footnote-style LLM-authored citations (only existing markers are linkified).
- No hover text snippets from the source (identity + location only).
- No WYSIWYG contenteditable that round-trips Markdown (see Editor rationale).

## Architecture overview

A single principle unifies documents and video: **every visual carries an anchor
(a page number or a timestamp) and a caption, and is placed inline by one token
mechanism.** A single helper owns all note mutations so the note Markdown and its
RAG chunks never drift.

New/changed units:

| Unit | Responsibility |
| --- | --- |
| `core/figures.py` (new) | Detect + vision-gate + persist document figures. |
| `core/notes.py` (new) | `update_note_markdown()` + inline token/marker placement helpers. |
| `core/ingest.py` | Feed a unified visual manifest to note generation; inline placement replaces the appendix. |
| `core/video.py` | Unchanged capture; frames become manifest entries. |
| `core/db.py` | `update_note`, `doc_figures` table + accessors. |
| `core/config.py` | `FIGURES_DIR`. |
| `server.py` | `PUT /api/notes/{id}`, `GET /api/doc/figures/{name}`, `GET /api/items/{id}/file`; `verify_video_frame` routes through the shared helper. |
| `web` notes page | Editor (toolbar + live preview); source-marker linkifier with hover card + jump. |

## Component design

### 1. Figure detection — `core/figures.py`

`extract_figures(pdf_path, item_id) -> list[Figure]` where a `Figure` is
`{figure_id, page, caption, image_path}`.

Per page (PyMuPDF):

- **Raster candidates:** `page.get_image_info(xrefs=True)` → bounding boxes of
  embedded raster images.
- **Vector candidates:** `page.get_drawings()` → cluster nearby paths into bounding
  boxes. Drop clusters that are tiny, extremely thin (rules/underlines/borders), or
  cover almost the whole page (page frame). Merge overlapping clusters.
- Cap candidates per page (e.g. 6) and dedupe near-identical boxes.
- Render each candidate region to PNG via a clipped pixmap at readable DPI.
- **Vision gate + caption** (reuse the `consolidate_frame` pattern): one
  `llm.chat_vision` call — *"Is this a meaningful diagram/flowchart/chart/figure? If
  yes, reply with a one-line caption. If it is decorative, a logo, or noise, reply
  exactly `NO_RELEVANT_CONTENT`."* Reject `NO_RELEVANT_CONTENT`; keep the caption.
- Survivors are saved to `FIGURES_DIR` with a filename carrying `item_id`
  (`fig_{item_id}_{page}_{uuid}.png`) and persisted via `db.add_doc_figure(...)`
  returning `figure_id`.

**Standalone image upload** (`kind == "image"`): register the uploaded image as a
single `Figure` (`page=None`, caption from the vision gate or a default), so the
picture appears in its note.

Failures are swallowed per-candidate (`traceback.print_exc()`); a figure that can't
be processed simply doesn't appear — text extraction is never blocked.

### 2. Inline placement — `core/notes.py` + `core/ingest.py`

**At generation time** (`_generate_notes`): build one manifest of all visuals for
the item (document figures with a page anchor; video frames with a timestamp
anchor). For each note-generation part, include only the visuals whose anchor falls
in that part's span, appended to the prompt:

```
Available visuals — place each token on its own line where you discuss it:
[[FIG:1]] Flowchart of the TCP handshake (p.3)
[[FIG:2]] Board diagram of the call stack (@ 12:40)
```

After the note is assembled, `place_visuals(markdown, manifest)`:

1. Replace each emitted `[[FIG:n]]` token with the visual's Markdown image:
   - document figure → `![caption](/api/doc/figures/{filename})`
   - video frame → `![caption](/api/video/frames/{frame_id}/image)`
2. **Fallback for tokens the local model omitted:** insert the straggler inline at
   its anchor — immediately after the nearest preceding `[@ mm:ss]` (timestamp) or
   `[p. N]` (page) marker in the note body. Only if no anchor marker exists at all
   is it appended at the very end. **No visuals section is ever created.**

This **replaces** the current `## Important lecture visuals` appendix in
`_generate_notes` entirely; video frames now sit inline next to the transcript
passage that discusses them, exactly like document figures.

**Shared mutation helper** `update_note_markdown(note_id, markdown)`:

1. `db.update_note(note_id, markdown)`.
2. Delete the note's existing RAG chunks (`source_label LIKE '% — notes'`) from
   SQLite and `vectorstore.delete_chunks(...)` — same pattern as `delete_note`.
3. Re-split the new Markdown (`_split`) and re-index the sections
   (`vectorstore.add_chunks`) under `source_label + " — notes"`.

Every note change — manual edit and frame-add — goes through this helper.

### 3. Video frame added later — `verify_video_frame`

Keep the existing chunk creation (searchable board text). Additionally:

1. Build the frame's inline image Markdown
   (`![caption](/api/video/frames/{frame_id}/image)`).
2. Load the item's current note; insert the image inline at the nearest preceding
   `[@ mm:ss]` marker (the note always contains the full timestamped transcript for
   videos, so an anchor exists). If the frame is already present, no-op.
3. Route the updated Markdown through `update_note_markdown`.

### 4. Editable notes

**Backend:** `PUT /api/notes/{note_id}` with body `{ "markdown": str }` →
`update_note_markdown`. Returns the saved note. Validate non-empty, cap length.

**Frontend (notes page):** an "Edit" control on the open note. Rationale for the
chosen realization of "rendered edit + toolbar": a true contenteditable WYSIWYG that
round-trips Markdown **plus** KaTeX math, GFM tables, and embedded figure images is
fragile — and this is the project's modified Next 16 with known install/hydration
traps. So the editor is a **formatting toolbar + live rendered preview**: toolbar
buttons (bold, italic, headings, list, link, etc.) insert Markdown into an editable
area, and the existing `ReactMarkdown` pipeline renders a live preview beside/under
it. Markdown stays the source of truth, so math/tables/images never corrupt. Save
calls `PUT`; Cancel restores. This delivers "use a toolbar, see the result" without
the round-trip breakage.

### 5. Source markers as hover links

Turn the existing `[@ mm:ss]` and `[p. N]` markers already present in note Markdown
into compact hyperlinks.

- **Rendering:** a small transform (remark plugin or a pre-render Markdown pass)
  converts each marker into a link node tagged with `{kind: "timestamp"|"page",
  value}`. A custom renderer displays a compact chip (e.g. a small link glyph /
  the word "link") rather than the raw marker.
- **Hover:** a tooltip/hover card showing **source identity + location** — the
  note's title, subject, and the location label (`@ 12:40` or `page 3`). All of
  this is already available on the note detail (`title`, `subject`, `kind`,
  `item_id`); no snippet lookup endpoint is needed.
- **Click — jump to source in place:**
  - video/audio → open the existing `VideoModal` seeked to the timestamp (reuses
    the LAN-robust seek logic in `src/components/VideoModal.tsx`).
  - pdf → open the original file at the page via `GET /api/items/{item_id}/file`
    plus the browser `#page=N` fragment.
  - image → open the original image via the same endpoint.
- **New endpoint** `GET /api/items/{item_id}/file`: serves the original
  `stored_path` for non-video kinds (pdf/image/text), guarded to existing files.
  (Video keeps its existing dedicated endpoint.)

`cleanStudyMarkdown` already strips only the *literal placeholder* tokens
(`[@ mm:ss]`, `[p. N]`), so real markers survive to be linkified. The linkifier
must run on real markers only.

## Data model & serving

- **`doc_figures` table:** `id, item_id, page (nullable), caption, image_path,
  created_at`. Accessors: `add_doc_figure(...) -> int`, `get_doc_figure(id)`,
  `list_doc_figures(item_id)`, and cleanup on item/note delete.
- **`FIGURES_DIR`** in `core/config.py`, created at import like the other dirs.
- **`GET /api/doc/figures/{filename}`:** serve from `FIGURES_DIR` with a
  path-traversal guard (mirror the hw-crops route at `server.py:855`).
- Note generation happens **before** chunks are persisted, so figures must be
  persisted during extraction to obtain a stable id for the note URL — exactly how
  video frames already get a `frame_id` before notes are generated.

## Data flow (PDF with a figure)

1. Worker picks up the item → `_extract`.
2. `extract_pdf` returns page text (unchanged). `extract_figures` returns
   vision-gated figures, each persisted with a `figure_id`.
3. `_classify` → subject/title.
4. `_generate_notes` builds the visual manifest (figures + any video frames), feeds
   per-part manifests to the LLM, assembles the note, and `place_visuals` inlines
   the images.
5. `db.add_note` stores the Markdown; chunks + note sections are indexed.
6. In the UI the note renders the figure inline; `[p. 3]` markers are hover links
   that open the PDF at page 3.

## Error handling

- Figure detection/gating failures are per-candidate and swallowed; text is never
  blocked.
- Vision gate returning `NO_RELEVANT_CONTENT` → figure dropped.
- LLM omitting a `[[FIG:n]]` token → inline anchor fallback, never lost, never a
  section.
- `update_note_markdown` re-index failure is logged; the Markdown save still
  succeeds (RAG can be rebuilt).
- Missing figure file → image 404s in the browser like any other; note text
  unaffected.

## Testing

- `tests/test_figures.py`: vector/raster candidate extraction and noise filtering
  on a small synthetic PDF; standalone-image figure registration; vision gate
  mocked.
- `core/notes.py`: `place_visuals` token replacement; anchor-fallback for omitted
  tokens (timestamp and page); no-section guarantee; `update_note_markdown`
  re-index (delete + re-add) with a fake vectorstore.
- `verify_video_frame`: frame inserted inline at the right anchor; idempotent on
  repeat; note + RAG updated.
- API: `PUT /api/notes/{id}` persists and re-indexes; `GET /api/items/{id}/file`
  serves pdf/image and rejects traversal / missing files.
- Existing `tests/test_notes.py` and `tests/test_server_api.py` extended;
  reconcile with the already-modified `tests/test_ocr.py` / `tests/test_video.py`.

## Open implementation notes

- Follow `web/AGENTS.md`: this is a modified Next 16 — read the bundled docs before
  writing frontend code; watch the install/hydration traps recorded in memory.
- Vector clustering thresholds will need tuning against real lecture PDFs; the
  vision gate is the backstop against false positives.
