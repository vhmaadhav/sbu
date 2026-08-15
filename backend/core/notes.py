"""Inline visual placement and the single note-mutation path.

A *visual* is a dict: ``{"token_id": int, "url": str, "caption": str,
"anchor": ("ts", seconds) | ("page", n) | None}``. Note generation offers the
model a manifest of ``[[FIG:n]]`` tokens; ``place_visuals`` swaps emitted tokens
for Markdown images and inlines any the model skipped at their anchor — never in a
section. Every note change (generation, edit, frame-add) routes through
``update_note_markdown`` so the note Markdown and its RAG chunks stay in sync.
"""
import logging
import re

from core import db, vectorstore

NOTES_SUFFIX = " — notes"

_TOKEN = re.compile(r"^[ \t]*\[\[FIG:(\d+)\]\][ \t]*$", re.MULTILINE)
# A token the model left mid-sentence, or echoed back as a manifest listing.
_ECHOED_TOKEN_LINE = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?\[\[FIG:\d+\]\].*$", re.MULTILINE)
_INLINE_TOKEN = re.compile(r"[ \t]*\[\[FIG:\d+\]\][ \t]*")
_TS = re.compile(r"\[@\s*(?:(\d+):)?(\d+):(\d{2})\]")
_PAGE_N = re.compile(r"\[p\.\s*(\d+)\]")


def _img(visual: dict) -> str:
    return f"![{visual['caption']}]({visual['url']})"


def _fmt_ts(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def build_manifest_block(visuals: list[dict]) -> str:
    """Prompt fragment offering each visual as a placeable ``[[FIG:n]]`` token."""
    if not visuals:
        return ""
    lines = ["", "Available visuals — place each token on its own line where you discuss it:"]
    for v in visuals:
        anchor = v.get("anchor")
        if anchor and anchor[0] == "ts":
            loc = f" (@ {_fmt_ts(anchor[1])})"
        elif anchor and anchor[0] == "page":
            loc = f" (p.{anchor[1]})"
        else:
            loc = ""
        lines.append(f"[[FIG:{v['token_id']}]] {v['caption']}{loc}")
    return "\n".join(lines)


def _line_seconds(line: str) -> int | None:
    match = _TS.search(line)
    if not match:
        return None
    hours = int(match.group(1)) if match.group(1) else 0
    return hours * 3600 + int(match.group(2)) * 60 + int(match.group(3))


def _anchor_index(lines: list[str], anchor) -> int | None:
    """Index of the note line the straggler should follow, or None for no anchor."""
    if not anchor:
        return None
    kind, value = anchor
    best = None
    if kind == "ts":
        fallback = None
        for i, line in enumerate(lines):
            seconds = _line_seconds(line)
            if seconds is None:
                continue
            fallback = i
            if seconds <= value:
                best = i
        return best if best is not None else fallback
    if kind == "page":
        fallback = None
        for i, line in enumerate(lines):
            pages = [int(n) for n in _PAGE_N.findall(line)]
            if not pages:
                continue
            fallback = i
            if value in pages:
                best = i
        return best if best is not None else fallback
    return None


def strip_placement_tokens(markdown: str) -> str:
    """Remove ``[[FIG:n]]`` markers the placement pass could not turn into images.

    A raw token is placement scaffolding, never something a reader should see.
    Lines that merely echo the manifest back are dropped whole; a token used
    mid-sentence is deleted in place so the sentence still reads.
    """
    cleaned = _ECHOED_TOKEN_LINE.sub("", markdown)
    cleaned = _INLINE_TOKEN.sub(" ", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned)


def place_visuals(markdown: str, visuals: list[dict]) -> str:
    """Swap emitted tokens for images; inline the rest at their anchor (no section)."""
    if not visuals:
        return strip_placement_tokens(markdown)
    by_id = {v["token_id"]: v for v in visuals}
    placed: set[int] = set()

    def _sub(match: "re.Match") -> str:
        vid = int(match.group(1))
        visual = by_id.get(vid)
        if visual is None or vid in placed:
            return ""  # unknown token, or a duplicate the model repeated
        placed.add(vid)
        return _img(visual)

    out = _TOKEN.sub(_sub, markdown)

    leftovers = [v for v in visuals if v["token_id"] not in placed]
    if not leftovers:
        return strip_placement_tokens(out)

    lines = strip_placement_tokens(out).split("\n")
    trailing = []
    for visual in leftovers:
        index = _anchor_index(lines, visual.get("anchor"))
        if index is None:
            trailing.append(visual)
        else:
            lines[index + 1: index + 1] = ["", _img(visual)]
    out = "\n".join(lines)
    if trailing:
        out = out.rstrip() + "\n\n" + "\n\n".join(_img(v) for v in trailing)
    return out


def update_note_markdown(note_id: int, item_id: int, markdown: str,
                         source_label: str, subject: str) -> str:
    """Persist edited note Markdown and rebuild its ``… — notes`` RAG chunks."""
    from core.ingest import _split

    db.update_note(note_id, markdown)
    with db.conn() as c:
        old_ids = [row["id"] for row in c.execute(
            "SELECT id FROM chunks WHERE item_id=? AND source_label LIKE '%" + NOTES_SUFFIX + "'",
            (item_id,),
        ).fetchall()]
        if old_ids:
            placeholders = ",".join("?" for _ in old_ids)
            c.execute(f"DELETE FROM chunks WHERE id IN ({placeholders})", old_ids)
    try:
        vectorstore.delete_chunks(old_ids)
        rows = []
        label = source_label + NOTES_SUFFIX
        for section in _split(markdown):
            chunk_id = db.add_chunk(item_id, section, label)
            rows.append({
                "chunk_id": chunk_id, "item_id": item_id, "subject": subject,
                "source_label": label, "text": section,
            })
        vectorstore.add_chunks(rows)
    except Exception:
        logging.exception("Could not reindex edited note %s", note_id)
    return markdown
