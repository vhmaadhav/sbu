# Figures & Editable Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Embed meaningful figures (document + video) inline in study notes, make notes editable, and turn source markers into hover links that jump to the source.

**Architecture:** A unified "visual manifest" (each visual carries a page or timestamp anchor + caption) is placed inline by one token mechanism during note generation. One shared `update_note_markdown` helper owns every note mutation (edit, frame-add) and keeps the RAG index in sync. Source markers `[@ mm:ss]`/`[p. N]` are linkified client-side.

**Tech Stack:** Python 3, FastAPI, SQLite, LanceDB, PyMuPDF (fitz), Pillow, local LM Studio vision LLM; Next 16 + React + react-markdown frontend.

## Global Constraints

- Frontend is a **modified Next 16** — read `node_modules/next/dist/docs/` before writing frontend code (`web/AGENTS.md`); watch LAN hydration + restart-after-install traps.
- LLM must be available before processing an item (`llm.require_available()`); never silently degrade notes.
- Note↔RAG consistency: note sections are indexed with `source_label` ending in `" — notes"`.
- Figures persisted **during extraction** (before note generation) so URLs have stable ids.
- Never create a visuals *section*; visuals and unplaced stragglers go **inline**.

---

### Task 1: Config + DB — figures storage & note update

**Files:**
- Modify: `core/config.py` (add `FIGURES_DIR`)
- Modify: `core/db.py` (schema `doc_figures`; `update_note`, `add_doc_figure`, `get_doc_figure`, `list_doc_figures`, `delete_doc_figures_for_item`)
- Test: `tests/test_db_figures.py`

**Produces:**
- `db.update_note(note_id: int, markdown: str) -> None`
- `db.add_doc_figure(item_id: int, page: int|None, caption: str, image_path: str) -> int`
- `db.get_doc_figure(figure_id: int) -> dict|None`
- `db.list_doc_figures(item_id: int) -> list[dict]`
- `config.FIGURES_DIR: Path`

- [ ] Add to `core/config.py`: `FIGURES_DIR = DATA_DIR / "figures"` and include it in the `mkdir` loop.
- [ ] Add `doc_figures` table to `SCHEMA`:
```sql
CREATE TABLE IF NOT EXISTS doc_figures (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    page INTEGER,
    caption TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL,
    created_at REAL NOT NULL
);
```
- [ ] Add accessors to `core/db.py`:
```python
def update_note(note_id: int, markdown: str) -> None:
    with conn() as c:
        c.execute("UPDATE notes SET markdown=? WHERE id=?", (markdown, note_id))

def add_doc_figure(item_id: int, page: int | None, caption: str, image_path: str) -> int:
    with conn() as c:
        return c.execute(
            "INSERT INTO doc_figures (item_id, page, caption, image_path, created_at) "
            "VALUES (?,?,?,?,?)", (item_id, page, caption, image_path, time.time()),
        ).lastrowid

def get_doc_figure(figure_id: int):
    with conn() as c:
        row = c.execute("SELECT * FROM doc_figures WHERE id=?", (figure_id,)).fetchone()
        return dict(row) if row else None

def list_doc_figures(item_id: int):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM doc_figures WHERE item_id=? ORDER BY page, id", (item_id,)
        ).fetchall()]

def delete_doc_figures_for_item(item_id: int) -> list[str]:
    with conn() as c:
        paths = [r["image_path"] for r in c.execute(
            "SELECT image_path FROM doc_figures WHERE item_id=?", (item_id,)).fetchall()]
        c.execute("DELETE FROM doc_figures WHERE item_id=?", (item_id,))
    return paths
```
- [ ] Test: create item, add figure, list/get returns it; `update_note` changes markdown. Run `pytest tests/test_db_figures.py -v`.
- [ ] Commit: `feat: doc_figures table, note update + figure db accessors`.

---

### Task 2: `core/notes.py` — placement + shared update helper

**Files:**
- Create: `core/notes.py`
- Test: `tests/test_notes_placement.py`

**Consumes:** `db.update_note`, existing `ingest._split`, `vectorstore.delete_chunks/add_chunks`, `db.add_chunk`, `db.conn`.

**Produces:**
- `VISUAL_TOKEN` regex, `build_manifest_block(visuals) -> str`
- `place_visuals(markdown: str, visuals: list[dict]) -> str`
- `update_note_markdown(note_id: int, item_id: int, markdown: str, source_label: str, subject: str) -> str`

A `visual` dict: `{"token_id": int, "url": str, "caption": str, "anchor": ("ts", seconds) | ("page", n) | None}`.

- [ ] Write failing tests in `tests/test_notes_placement.py`:
  - token `[[FIG:1]]` on its own line → replaced with `![caption](url)`.
  - omitted token with `("ts", 760)` anchor → image inserted right after the line containing `[@ 12:40]`.
  - omitted token with `("page", 3)` anchor → inserted after line containing `[p. 3]`.
  - omitted token, no anchor marker anywhere → appended at end; **no `##` heading added**.
- [ ] Implement `core/notes.py`:
```python
"""Inline visual placement + the single note-mutation path (keeps RAG in sync)."""
import re
from core import db, vectorstore

_TOKEN = re.compile(r"^[ \t]*\[\[FIG:(\d+)\]\][ \t]*$", re.MULTILINE)
_TS = re.compile(r"\[@\s*(\d+):(\d{2})(?::(\d{2}))?\]")
_PAGE = re.compile(r"\[p\.\s*(\d+)\]")

def _img(v: dict) -> str:
    return f"![{v['caption']}]({v['url']})"

def build_manifest_block(visuals: list[dict]) -> str:
    if not visuals:
        return ""
    lines = ["", "Available visuals — place each token on its own line where you discuss it:"]
    for v in visuals:
        loc = ""
        if v.get("anchor") and v["anchor"][0] == "ts":
            m, s = divmod(int(v["anchor"][1]), 60)
            loc = f" (@ {m}:{s:02d})"
        elif v.get("anchor") and v["anchor"][0] == "page":
            loc = f" (p.{v['anchor'][1]})"
        lines.append(f"[[FIG:{v['token_id']}]] {v['caption']}{loc}")
    return "\n".join(lines)

def _seconds_at(line: str) -> int | None:
    m = _TS.search(line)
    if not m:
        return None
    h = int(m.group(3)) if m.group(3) else 0  # group order below is m:s or m:s:? — see impl note
    return None  # replaced by real impl in code

def place_visuals(markdown: str, visuals: list[dict]) -> str:
    by_id = {v["token_id"]: v for v in visuals}
    placed: set[int] = set()

    def sub(match: "re.Match") -> str:
        vid = int(match.group(1))
        v = by_id.get(vid)
        if not v:
            return ""
        placed.add(vid)
        return _img(v)
    out = _TOKEN.sub(sub, markdown)

    leftovers = [v for v in visuals if v["token_id"] not in placed]
    if not leftovers:
        return out
    lines = out.split("\n")
    trailing = []
    for v in leftovers:
        idx = _anchor_index(lines, v.get("anchor"))
        if idx is None:
            trailing.append(v)
        else:
            lines.insert(idx + 1, "")
            lines.insert(idx + 2, _img(v))
    out = "\n".join(lines)
    if trailing:
        out = out.rstrip() + "\n\n" + "\n\n".join(_img(v) for v in trailing)
    return out
```
  Implement `_anchor_index(lines, anchor)`: for `("ts", secs)` find the last line whose `[@ mm:ss]` parses to a value `<= secs` (fallback: last line with any `[@`); for `("page", n)` the last line containing `[p. n]` (fallback: last `[p.`); `None` when no marker present. Parse `[@ h:mm:ss]`/`[@ m:ss]` correctly (hours optional).
- [ ] Implement `update_note_markdown`:
```python
def update_note_markdown(note_id, item_id, markdown, source_label, subject) -> str:
    from core.ingest import _split
    db.update_note(note_id, markdown)
    with db.conn() as c:
        old = [r["id"] for r in c.execute(
            "SELECT id FROM chunks WHERE item_id=? AND source_label LIKE '% — notes'",
            (item_id,)).fetchall()]
        if old:
            ph = ",".join("?" for _ in old)
            c.execute(f"DELETE FROM chunks WHERE id IN ({ph})", old)
    try:
        vectorstore.delete_chunks(old)
        rows = []
        for section in _split(markdown):
            cid = db.add_chunk(item_id, section, source_label + " — notes")
            rows.append({"chunk_id": cid, "item_id": item_id, "subject": subject,
                         "source_label": source_label + " — notes", "text": section})
        vectorstore.add_chunks(rows)
    except Exception:
        import logging; logging.exception("note reindex failed")
    return markdown
```
- [ ] Run tests green. Commit: `feat: inline visual placement + shared note update helper`.

---

### Task 3: `core/figures.py` — detect + vision-gate figures

**Files:**
- Create: `core/figures.py`
- Test: `tests/test_figures.py`

**Consumes:** `fitz`, `PIL`, `llm.chat_vision`, `config.FIGURES_DIR`, `db.add_doc_figure`.

**Produces:** `extract_pdf_figures(pdf_path: str, item_id: int) -> list[dict]` and `register_image_figure(image_path: str, item_id: int) -> dict|None`, each returning `{"figure_id", "page", "caption"}`.

- [ ] Failing tests (mock `llm.chat_vision`):
  - a synthetic 1-page PDF with a drawn rectangle+lines cluster yields ≥1 candidate; gate returning a caption → one persisted figure with that caption.
  - gate returning `NO_RELEVANT_CONTENT` → zero figures.
  - `register_image_figure` on a PNG → one figure, `page is None`.
- [ ] Implement candidate detection:
  - raster: `page.get_image_info()` → `bbox` rects.
  - vector: cluster `page.get_drawings()` item rects (union boxes within a gap threshold); drop boxes narrower/shorter than a min size, thinner than a min aspect (rules), or ≥ ~92% of page area.
  - cap 6/page, dedupe near-identical boxes (IoU > 0.8).
- [ ] For each candidate: render clipped pixmap (`page.get_pixmap(clip=rect, dpi=150)`), save temp PNG, call gate prompt (reuse `consolidate_frame` style): return one-line caption or `NO_RELEVANT_CONTENT`. On keep, move PNG to `FIGURES_DIR/fig_{item_id}_{page}_{uuid4().hex[:8]}.png`, `db.add_doc_figure(...)`.
- [ ] Wrap per-candidate work in try/except with `traceback.print_exc()`.
- [ ] Tests green. Commit: `feat: PDF/image figure extraction with vision gate`.

---

### Task 4: Wire figures + inline placement into ingest

**Files:**
- Modify: `core/ingest.py` (`_extract` image branch adds nothing new; `process_item`/`_generate_notes` build & place the manifest; drop the `## Important lecture visuals` appendix)
- Test: `tests/test_notes.py` (extend)

**Consumes:** `figures.extract_pdf_figures/register_image_figure`, `notes.build_manifest_block/place_visuals`, existing chunk/frame flow.

- [ ] In `process_item`, after `_extract`, collect visuals for the manifest:
  - video frames already captured (chunks with `frame_id`) → visual `{token_id, url:f"/api/video/frames/{fid}/image", caption:<first line of markdown>, anchor:("ts", ts)}`.
  - pdf → `figures.extract_pdf_figures(path, item_id)`; image → `figures.register_image_figure(path, item_id)` → visuals with `url:f"/api/doc/figures/{basename}"`, `anchor:("page", page)` or `None`.
  Assign sequential `token_id`s.
- [ ] Change `_generate_notes(full_text, chunks, title, visuals)`: append `build_manifest_block(<visuals whose anchor falls in this part>)` to each part prompt (for pdf, split full_text by `[p. N]`; simplest: pass all visuals to every part but only place once — `place_visuals` dedupes by placement). Keep the timestamped-transcript appendix for A/V. **Remove** the `## Important lecture visuals` block. After assembling, `return place_visuals(notes, visuals)`.
- [ ] Update `process_item` call site to pass `visuals`.
- [ ] Extend `tests/test_notes.py`: a fake item with one figure visual → generated note contains `![caption](/api/doc/figures/...)` and **no** `## Important lecture visuals`.
- [ ] Tests green. Commit: `feat: place document & video visuals inline in generated notes`.

---

### Task 5: Endpoints — serve figures, original files, edit note, frame→note

**Files:**
- Modify: `server.py`
- Modify: `core/config.py` import in server (`FIGURES_DIR`)
- Test: `tests/test_server_api.py` (extend)

- [ ] `GET /api/doc/figures/{name}`: resolve within `FIGURES_DIR`, reject traversal (mirror `server.py:855`), `FileResponse`.
- [ ] `GET /api/items/{item_id}/file`: look up `stored_path`+`kind`; serve for `kind in {"pdf","image","text"}` when the file exists (video keeps its own route); 404 otherwise.
- [ ] `PUT /api/notes/{note_id}` with `class NoteEdit(BaseModel): markdown: str`: load note+item+subject; reject empty; `notes.update_note_markdown(note_id, item_id, markdown, source_label, subject)`; return `{ok, markdown}`. Build `source_label` from item title/date/filename like `process_item` (`f"{title} — {capture_date} ({filename})"`).
- [ ] Extend `verify_video_frame`: after building `result["markdown"]`, also insert the frame inline into the item's newest note and re-index:
```python
note = db.notes_for_item(frame["item_id"])
if note:
    from core.notes import place_visuals
    latest = note[-1]
    fig = {"token_id": -1, "url": f"/api/video/frames/{frame_id}/image",
           "caption": (result["markdown"].splitlines() or ["Lecture visual"])[0][:120],
           "anchor": ("ts", frame["timestamp"])}
    if fig["url"] not in latest["markdown"]:
        updated = place_visuals(latest["markdown"], [fig])
        db_note_source = f"{frame['title'] or frame['filename']} — board"
        notes.update_note_markdown(latest["id"], frame["item_id"], updated, db_note_source, frame["subject"] or "General")
```
- [ ] Extend `tests/test_server_api.py`: `PUT` persists + returns markdown; `GET /api/items/{id}/file` serves a pdf and 404s traversal.
- [ ] Tests green. Commit: `feat: figure/file serving, note editing, frame-to-note endpoints`.

---

### Task 6: Frontend — source-marker links with hover + jump

**Files:**
- Create: `web/src/lib/noteLinks.tsx` (marker → link transform + hover card)
- Modify: `web/src/app/notes/page.tsx` (use transform in ReactMarkdown; wire VideoModal / file open)
- Modify: `web/src/lib/api.ts` if a helper is needed

- [ ] Read `node_modules/next/dist/docs/` relevant pages first.
- [ ] Implement a remark-based or text-preprocess transform that converts `[@ mm:ss]` / `[p. N]` into anchor elements carrying `data-kind`/`data-value`. Render a compact chip (small link glyph + "link"). Hover shows title · subject · location.
- [ ] Click: video/audio → open existing `VideoModal` seeked to seconds; pdf → open `${API}/api/items/${item_id}/file#page=${n}` in a new tab; image → open the file.
- [ ] Pass note context (`item_id`, `kind`, `title`, `subject`) into the renderer.
- [ ] Verify in the browser preview (dev server): open a video note, click a `[@ mm:ss]` link → player seeks; hover shows the card.
- [ ] Commit: `feat: clickable hover source links in notes`.

---

### Task 7: Frontend — note editor (toolbar + live preview)

**Files:**
- Create: `web/src/components/NoteEditor.tsx`
- Modify: `web/src/app/notes/page.tsx` (Edit toggle, save via PUT)

- [ ] Edit button on the open note swaps render for `NoteEditor`: a textarea (Markdown source) + formatting toolbar (bold/italic/H2/list/link insert into the textarea) + live `ReactMarkdown` preview (reuse the note's existing components incl. figure `img` rewrite).
- [ ] Save → `PUT /api/notes/${id}` `{markdown}`; on success update `detail[id]` and close editor. Cancel restores.
- [ ] Verify in browser: edit a note, bold some text via toolbar, preview updates, save persists across reload.
- [ ] Commit: `feat: toolbar + live-preview note editor`.

---

### Task 8: Cleanup on delete + full test pass

**Files:**
- Modify: `server.py` `delete_note` / item deletion to also `db.delete_doc_figures_for_item` and unlink figure files.
- Run: full `pytest` + `web` typecheck/build.

- [ ] On note/item delete, remove figure rows + files for the item.
- [ ] Run `.venv/bin/pytest -q` — all green; reconcile with pre-existing `tests/test_ocr.py`, `tests/test_video.py`.
- [ ] `cd web && npm run build` (or lint) passes.
- [ ] Commit: `chore: figure cleanup on delete; test pass`.

---

## Self-Review

- **Spec coverage:** figures (T3,T4), inline placement incl. video (T2,T4), editable notes (T5,T7), source links (T6), shared update helper (T2), serving/cleanup (T5,T8) — all mapped.
- **Type consistency:** `update_note_markdown(note_id,item_id,markdown,source_label,subject)`, `place_visuals(markdown,visuals)`, visual dict shape `{token_id,url,caption,anchor}` used consistently across T2/T4/T5.
- **Note:** the `_seconds_at`/`_anchor_index` sketch in T2 is illustrative — implement real hour-optional `[@ h:mm:ss]` parsing.
