"""Ingestion pipeline: inbox watcher + queue worker.

Flow per item: extract text (STT/OCR/PDF) -> LLM classify + notes -> store
chunks in SQLite + LanceDB.
"""
import shutil
import logging
import re
import subprocess
import tempfile
import threading
import time
import traceback
from datetime import date, datetime
from pathlib import Path

from core import db, llm, mathmd, vectorstore
from core.config import FILES_DIR, INBOX_DIR, kind_of

logger = logging.getLogger(__name__)

CHUNK_CHARS = 900
NOTES_INPUT_CHARS = 5000
# Every source part costs one sequential LLM call, so an unbounded part count
# turns a long lecture into an hour of generation that eventually times out and
# fails the whole item. Past this target parts widen instead of multiplying,
# up to the largest prompt worth sending. Source material is never dropped, so
# something longer than the two multiplied together still adds calls.
NOTES_MAX_PARTS = 10
NOTES_MAX_PART_CHARS = 14000
# A note-sized generation legitimately outruns the default chat timeout on a
# local model; a part that times out costs the entire ingestion.
NOTES_CALL_TIMEOUT = 180.0
# Apple Vision reports quantized confidences (1.0 printed, ~0.3-0.5 handwriting)
HANDWRITING_CONF_THRESHOLD = 0.8

CLASSIFY_SYSTEM = (
    "You organize study material for a student. Given content from a lecture or "
    "document, return JSON: {\"subject\": <short subject/course name>, "
    "\"title\": <short descriptive title>}. Reuse one of the existing subjects "
    "only when the material clearly belongs to it; otherwise invent a concise new one. "
    "Never put material into an unrelated existing subject."
)

NOTES_SYSTEM = (
    "You are a careful study-note editor. Write accurate, highly readable Markdown using only facts "
    "explicitly present in the supplied material. Never invent background, examples, definitions, "
    "formulas, or context. If the source is short, keep the note short. "
    "Use only the useful sections among these exact level-two headings: '## Summary', "
    "'## Key concepts', '## Detailed notes', and '## Formulas and definitions'. Do not write a title "
    "or any level-one heading; the application adds it. Start with a heading and omit empty sections. "
    "Write a compact 2-5 sentence Summary. Under other sections, use short bullets with bold lead terms "
    "when that improves scanning. Use numbered lists only for real sequences or procedures, and tables "
    "only for genuine comparisons with consistent columns. Put mathematical notation in valid LaTeX "
    "delimiters. Avoid repetitive points, filler conclusions, emojis, decorative symbols, and excessive "
    "bold text. While writing, identify the most important technical terms, named concepts, laws, methods, "
    "variables, key phrases, and high-value statements. Highlight an essential word or phrase at its most "
    "useful occurrence, or a short sentence when the complete statement is important to remember, by "
    "wrapping it in double equals; for example ==Ohm's law== or ==Current is the same at every point in a "
    "series circuit.== Use highlights sparingly (normally 3-8 per source part); never highlight a heading, "
    "long passage, timestamp, page reference, or Markdown/LaTeX syntax, and do not combine ==highlighting== "
    "with bold or code markers. "
    "Preserve only exact timestamps or page references already present in the source. Never "
    "output placeholders such as '[@ mm:ss]' or '[p. N]'. "
    "If the material lists 'Available visuals' with tokens like [[FIG:1]], place the relevant tokens on "
    "their own line at the point you discuss that visual; output each token at most once and never invent "
    "tokens that were not listed. Output only the Markdown section body."
)

NOTE_SECTION_ORDER = (
    "Summary",
    "Key concepts",
    "Detailed notes",
    "Formulas and definitions",
)
NOTE_SECTION_ALIASES = {section.casefold(): section for section in NOTE_SECTION_ORDER}

# Each source part is summarized independently, so a long lecture yields one
# near-identical Summary (and overlapping Key concepts) per part. Concatenating
# them makes a note many times longer than the material warrants, so multi-part
# notes get a merge pass per section before assembly.
NOTES_CONDENSE_SYSTEM = (
    "You merge draft study-note fragments that were written independently from consecutive parts "
    "of one document, so they overlap heavily and restate the same points in different words. "
    "Rewrite them as a single non-repetitive section using only facts present in the fragments — "
    "never add background, examples, or context of your own. Merge restatements into one "
    "statement, keep every genuinely distinct fact, and drop filler and conclusions. Preserve the "
    "fragments' formatting: prose stays prose, bullets stay bullets with their bold lead terms, "
    "mathematical notation stays in its LaTeX delimiters, and existing timestamps or page "
    "references stay on the fact they belong to. Keep any [[FIG:n]] token on its own line, at most "
    "once each, and never invent one. Write no heading. Output only the merged Markdown body."
)
# Per-section shape rules for the merge pass. Every section carries an explicit
# ceiling: without one on Detailed notes it simply accumulated each part's
# fragments, and that section alone reached 32 KB on a 16-minute lecture.
# Together these target roughly 1500-2500 words for a typical lecture.
NOTE_CONDENSE_GUIDANCE = {
    "Summary": "Write one paragraph of 3-5 sentences covering the whole document. No bullets.",
    "Key concepts": "Output at most 12 bullets, one distinct concept each, with a bold lead term.",
    "Detailed notes": (
        "Output at most 30 bullets in source order, one distinct point each. Group them under "
        "short '### ' sub-headings when the material has clear topics. Merge every restatement "
        "into a single bullet and drop anything already stated in another bullet."
    ),
    "Formulas and definitions": (
        "Output one bullet per distinct formula or definition. Drop exact repeats, and keep each "
        "formula verbatim."
    ),
}
NOTE_CONDENSE_FALLBACK = (
    "Merge only the points that repeat each other. Keep every distinct detail, in the order "
    "given, as short bullets."
)
CONDENSE_INPUT_CHARS = 12000
CONDENSE_WINDOW_CHARS = 8000

PLACEHOLDER_REFERENCE = re.compile(
    r"\s*\[(?:@\s*)?(?:mm:ss|p\.\s*N)\]",
    re.IGNORECASE,
)
DECORATIVE_SYMBOL = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # emoji and pictographs
    "\U00002600-\U000027BF"  # miscellaneous symbols and dingbats
    "]\ufe0f?"
)
DECORATIVE_BULLET = re.compile(r"^(\s*)[•●◦▪▫▸▹►‣]\s+", re.MULTILINE)
OUTER_MARKDOWN_FENCE = re.compile(
    r"^\s*```(?:markdown|md)?\s*\n(?P<body>.*)\n```\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _clean_generated_markdown(markdown: str) -> str:
    """Normalize generated notes while preserving real citations and formulas."""
    fenced = OUTER_MARKDOWN_FENCE.match(markdown)
    cleaned = fenced.group("body") if fenced else markdown
    cleaned = PLACEHOLDER_REFERENCE.sub("", cleaned)
    cleaned = DECORATIVE_SYMBOL.sub("", cleaned)
    cleaned = DECORATIVE_BULLET.sub(r"\1- ", cleaned)
    cleaned = re.sub(r"^(\s*)\*\s+", r"\1- ", cleaned, flags=re.MULTILINE)
    # Models mix $…$, \(…\), ```math fences and bare \frac{} in one document.
    # Every reader (web KaTeX, the PDF exporter, mobile) expects one dialect.
    cleaned = mathmd.normalize(cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _safe_markdown_title(title: str) -> str:
    """Keep a classified title on one plain Markdown heading line."""
    title = re.sub(r"\s+", " ", title.splitlines()[0] if title.splitlines() else "")
    title = title.strip().lstrip("#").strip()
    return title or "Study notes"


def _dedupe_lines(blocks: list[str]) -> list[str]:
    """Drop lines separate parts emitted verbatim, keeping first occurrence and order."""
    seen: set[str] = set()
    out = []
    for block in blocks:
        kept, fenced = [], False
        for line in block.split("\n"):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                kept.append(line)
                continue
            key = re.sub(r"[^a-z0-9]+", " ", line.casefold()).strip()
            # Blank lines, fenced content and very short lines are structural.
            if fenced or len(key) < 25:
                kept.append(line)
                continue
            if key in seen:
                continue
            seen.add(key)
            kept.append(line)
        body = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
        if body:
            out.append(body)
    return out


def _condense_windows(blocks: list[str]) -> list[str]:
    """Group fragments into merge-sized windows, keeping their original order."""
    windows, current = [], ""
    for block in blocks:
        if current and len(current) + len(block) > CONDENSE_WINDOW_CHARS:
            windows.append(current)
            current = block
        else:
            current = f"{current}\n\n{block}" if current else block
    if current:
        windows.append(current)
    return windows


def _condense_section(section: str, blocks: list[str]) -> str:
    """Merge one section's per-part fragments into a single non-repetitive body."""
    guidance = NOTE_CONDENSE_GUIDANCE.get(section)
    body = "\n\n".join(blocks)
    if len(blocks) < 2:
        return body

    # A section that fits gets one pass, so its ceiling applies to the whole
    # section. Anything longer is merged in windows rather than truncated to the
    # first CONDENSE_INPUT_CHARS, which silently dropped the tail of a section.
    windows = [body] if len(body) <= CONDENSE_INPUT_CHARS else _condense_windows(blocks)
    if guidance is None:
        # Without a ceiling to enforce there is nothing to gain from a pass that
        # merges a block with itself.
        guidance = NOTE_CONDENSE_FALLBACK
        if len(windows) == len(blocks):
            return body  # each block already stands alone

    merged = []
    for number, window in enumerate(windows, start=1):
        scope = "" if len(windows) == 1 else (
            f"\nThese are group {number} of {len(windows)} groups of fragments, so apply any "
            "stated limit proportionally to this group alone."
        )
        try:
            result = llm.chat(
                NOTES_CONDENSE_SYSTEM,
                f"Section: {section}\n{guidance}{scope}\n\nFragments:\n{window}",
                max_tokens=1200,
                timeout=NOTES_CALL_TIMEOUT,
            )
        except Exception:
            logger.exception("Could not condense note section %r; keeping fragments", section)
            return body
        result = _clean_generated_markdown(result)
        result = re.sub(r"^#{1,6}\s+.*$", "", result, flags=re.MULTILINE).strip()
        if not result:
            return body
        merged.append(result)
    return "\n\n".join(merged)


def _assemble_structured_notes(title: str, generated_parts: list[str],
                               condense: bool = False) -> str:
    """Merge repeated LLM section headings into one predictable note document."""
    collected = {section: [] for section in NOTE_SECTION_ORDER}

    for raw_part in generated_parts:
        part = _clean_generated_markdown(raw_part)
        # Local models sometimes ignore the no-title instruction. The application
        # owns the canonical title, so discard model-written level-one headings.
        part = re.sub(r"^#\s+.*(?:\n+|$)", "", part, count=1).strip()
        matches = list(re.finditer(r"^##\s+(.+?)\s*$", part, flags=re.MULTILINE))
        if not matches:
            if part:
                collected["Detailed notes"].append(part)
            continue

        for index, match in enumerate(matches):
            heading = re.sub(r"[*_`]", "", match.group(1)).strip().casefold()
            section = NOTE_SECTION_ALIASES.get(heading, "Detailed notes")
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(part)
            content = part[start:end].strip()
            if content:
                collected[section].append(content)

    document = [f"# {_safe_markdown_title(title)}"]
    for section in NOTE_SECTION_ORDER:
        blocks = _dedupe_lines(collected[section])
        if not blocks:
            continue
        body = _condense_section(section, blocks) if condense else "\n\n".join(blocks)
        if body:
            document.extend([f"## {section}", body])
    return "\n\n".join(document)

CALENDAR_SYSTEM = (
    "Extract actionable scheduled events from any uploaded material. Return JSON as "
    "{\"events\": [{\"title\": string, \"date\": \"YYYY-MM-DD\", "
    "\"start_time\": \"HH:MM\" or null, \"end_time\": \"HH:MM\" or null, "
    "\"description\": string}]}. Include any explicit upcoming commitment with a date: "
    "exams, deadlines, submissions, classes, meetings, appointments, travel, shifts, "
    "interviews, personal plans, or direct requests to remember a date. "
    "Do not treat the capture date, historical dates, source citations, or vague mentions as events. "
    "Resolve relative dates against the supplied capture date. Return an empty events list when unsure."
)


def _ffmpeg_to_wav(src: str) -> str:
    out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-ac", "1", "-ar", "16000", "-vn", out],
        check=True, capture_output=True,
    )
    return out


def _mmss(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _extract(item: dict) -> list[dict]:
    """Returns chunk dicts: {text, ts_start, page, image_path} with source refs inline."""
    path = item["stored_path"]
    kind = item["kind"]

    if kind in ("audio", "video"):
        if kind == "video":
            # Rewrite the stored file into a seekable progressive MP4 so the
            # web player can jump straight to a cited timestamp instead of
            # streaming a large lecture from the start. Rewritten in place, so
            # the serving path is unchanged.
            from core.video import optimize_for_streaming
            try:
                optimize_for_streaming(path)
            except Exception:
                traceback.print_exc()  # a non-optimized video still plays fine
        from core.stt import transcribe
        wav = _ffmpeg_to_wav(path)
        try:
            segments = transcribe(wav)
        finally:
            Path(wav).unlink(missing_ok=True)
        chunks, buf, buf_start = [], "", None
        for seg in segments:
            if buf_start is None:
                buf_start = seg["start"]
            buf += f" {seg['text']}"
            if len(buf) >= CHUNK_CHARS:
                chunks.append({"text": f"[@ {_mmss(buf_start)}]{buf}", "ts_start": buf_start})
                buf, buf_start = "", None
        if buf.strip():
            chunks.append({"text": f"[@ {_mmss(buf_start)}]{buf}", "ts_start": buf_start})
        if kind == "video":
            try:
                from core.video import analyze_frame, capture_stable_frames
                for frame_id in capture_stable_frames(item["id"], path):
                    result = analyze_frame(frame_id)
                    markdown = result["markdown"].strip()
                    frame = result["frame"]
                    if markdown != "NO_RELEVANT_CONTENT":
                        chunks.append({
                            "text": f"[@ {_mmss(frame['timestamp'])}] Visual from lecture:\n{markdown}",
                            "ts_start": frame["timestamp"], "image_path": frame["frame_path"],
                            "frame_id": frame_id,
                        })
            except Exception:
                traceback.print_exc()  # transcript remains useful even if board capture fails
        return chunks

    if kind == "pdf":
        from core.ocr import extract_pdf
        return [
            {
                "text": f"[p. {p['page']}] {chunk}",
                "page": p["page"],
                "image_path": p.get("image_path"),
            }
            for p in extract_pdf(path)
            for chunk in _split(p["text"])
        ]

    if kind == "image":
        # Flowcharts/architecture diagrams need graph-aware extraction. The
        # analyzer is intentionally attempted before generic OCR so its
        # PaddleOCR-VL transcription, connector topology, and Mermaid graph
        # travel together through note generation and RAG.
        try:
            from core.diagrams import analyze_diagram
            diagram = analyze_diagram(path)
            if diagram["graph"].get("is_diagram") and diagram["graph"].get("nodes"):
                graph = diagram["graph"]
                source_text = (
                    f"Diagram: {graph['title']}\n"
                    f"{graph.get('summary', '')}\n\n"
                    f"Extracted labels and tables:\n{diagram['ocr_markdown']}\n\n"
                    f"Validated Mermaid graph:\n```mermaid\n{diagram['mermaid']}\n```"
                )
                return [{
                    "text": source_text,
                    "image_path": path,
                    "diagram_result": diagram,
                }]
        except Exception:
            traceback.print_exc()  # ordinary image OCR remains available
        from core.ocr import ocr_image_annotations
        try:
            annotations = ocr_image_annotations(path)
        except Exception:
            annotations = []
        text = "\n".join(a[0] for a in annotations).strip()
        confidence = sum(a[1] for a in annotations) / len(annotations) if annotations else 0.0
        # Low Vision confidence (or nothing found) usually means handwriting:
        # run the personalized TrOCR pipeline instead. The page also lands in
        # the Handwriting tab where lines can be corrected (and train the model).
        if confidence < HANDWRITING_CONF_THRESHOLD:
            try:
                from core.handwriting import recognize_item_page
                hw_text = recognize_item_page(item["id"], path)
                if hw_text:
                    text = hw_text
            except Exception:
                traceback.print_exc()  # fall back to whatever Vision found
        if not text:
            return []
        return [{"text": text, "image_path": path}]

    if kind == "text":
        raw = Path(path).read_text(errors="ignore")
        return [{"text": t} for t in _split(raw)]

    return []


def _split(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts, buf = [], ""
    for para in text.split("\n\n"):
        if len(buf) + len(para) > CHUNK_CHARS and buf:
            parts.append(buf.strip())
            buf = ""
        buf += para + "\n\n"
    if buf.strip():
        parts.append(buf.strip())
    return parts


def _classify(full_text: str, filename: str) -> tuple[str, str]:
    existing = ", ".join(s["name"] for s in db.list_subjects()) or "(none yet)"
    result = llm.chat_json(
        CLASSIFY_SYSTEM,
        f"Filename: {filename}\nExisting subjects: {existing}\n\nContent:\n{full_text[:4000]}",
    )
    return str(result.get("subject", "General")), str(result.get("title", "Untitled"))


def _visual_caption(chunk_text: str) -> str:
    """A short caption for a captured video frame from its chunk text."""
    body = chunk_text.split("Visual from lecture:", 1)[-1]
    for line in body.splitlines():
        cleaned = re.sub(r"^[#>*\-\s]+", "", line).strip().strip("*_`")
        if cleaned:
            return cleaned[:120]
    return "Lecture visual"


def _collect_visuals(item: dict, chunks: list[dict]) -> list[dict]:
    """Unified inline-visual manifest: captured video frames + document figures."""
    from core import figures

    visuals: list[dict] = []
    token = 1
    for chunk in chunks:
        if chunk.get("frame_id") and chunk.get("ts_start") is not None:
            visuals.append({
                "token_id": token,
                "url": f"/api/video/frames/{chunk['frame_id']}/image",
                "caption": _visual_caption(chunk["text"]),
                "anchor": ("ts", int(chunk["ts_start"])),
            })
            token += 1
    try:
        if item["kind"] == "pdf":
            for fig in figures.extract_pdf_figures(item["stored_path"], item["id"]):
                visuals.append({
                    "token_id": token,
                    "url": f"/api/doc/figures/{fig['filename']}",
                    "caption": fig["caption"],
                    "anchor": ("page", fig["page"]),
                })
                token += 1
        elif item["kind"] == "image":
            fig = figures.register_image_figure(item["stored_path"], item["id"])
            if fig:
                visuals.append({
                    "token_id": token,
                    "url": f"/api/doc/figures/{fig['filename']}",
                    "caption": fig["caption"],
                    "anchor": None,
                })
                token += 1
            diagram = next(
                (chunk.get("diagram_result") for chunk in chunks if chunk.get("diagram_result")),
                None,
            )
            if diagram and Path(diagram["overlay"]).exists():
                overlay_bytes = Path(diagram["overlay"]).read_bytes()
                overlay = figures._persist(
                    item["id"], None, "Detected diagram nodes", overlay_bytes,
                )
                visuals.append({
                    "token_id": token,
                    "url": f"/api/doc/figures/{overlay['filename']}",
                    "caption": overlay["caption"],
                    "anchor": None,
                })
                token += 1
    except Exception:
        traceback.print_exc()  # notes must still generate without figures
    return visuals


def _note_part_chars(length: int) -> int:
    """Chars per generated section, widened to hold long sources to the target.

    Splitting purely by ``NOTES_INPUT_CHARS`` made the call count scale with the
    source: a 16-minute lecture became 31 sequential generations, which both
    timed out and produced 31 near-identical Summary paragraphs to merge back.
    Widening is capped at ``NOTES_MAX_PART_CHARS`` because coverage of the
    source matters more than the target — a source larger than the two
    multiplied together spends extra calls rather than losing its tail.
    """
    if length <= NOTES_INPUT_CHARS * NOTES_MAX_PARTS:
        return NOTES_INPUT_CHARS
    widened = (length + NOTES_MAX_PARTS - 1) // NOTES_MAX_PARTS
    return min(widened, NOTES_MAX_PART_CHARS)


def _generate_notes(full_text: str, chunks: list[dict], title: str = "Study notes",
                    visuals: list[dict] | None = None) -> str:
    from core.notes import build_manifest_block, place_visuals

    visuals = visuals or []
    manifest = build_manifest_block(visuals)
    sections = []
    part_chars = _note_part_chars(len(full_text))
    part_count = max(1, (len(full_text) + part_chars - 1) // part_chars)
    for part_number, i in enumerate(range(0, len(full_text), part_chars), start=1):
        part = full_text[i:i + part_chars]
        prompt = (
            f"Document title: {title}\nSource part: {part_number} of {part_count}\n\n"
            f"Source material:\n{part}{manifest}"
        )
        sections.append(llm.chat(
            NOTES_SYSTEM, prompt, max_tokens=1400, timeout=NOTES_CALL_TIMEOUT,
        ))
    # One part cannot repeat itself across parts, so skip the merge pass and its
    # cost for short sources.
    notes = _assemble_structured_notes(title, sections, condense=len(sections) > 1)
    diagrams = [
        chunk["diagram_result"] for chunk in chunks if chunk.get("diagram_result")
    ]
    for diagram in diagrams:
        notes += (
            "\n\n## Editable diagram\n\n```mermaid\n"
            + diagram["mermaid"]
            + "\n```\n\n## Diagram pipeline\n\n"
            + "\n".join(
                f"- **{stage['name'].replace('_', ' ').title()}:** "
                f"{stage['status']} via {stage['implementation']}"
                for stage in diagram["stages"]
            )
        )
    # The note is the study guide, not a copy of the source. The complete
    # timestamped transcript used to be appended here, which made it ~70% of a
    # lecture note; it is still stored verbatim as chunks, so RAG retrieval and
    # the timestamp links into the player are unaffected.
    # Visuals are placed inline at their page/timestamp anchor, never in a section.
    return place_visuals(notes, visuals)


def _extract_calendar_reminders(full_text: str, capture_date: str) -> list[dict]:
    result = llm.chat_json(
        CALENDAR_SYSTEM,
        f"Today: {date.today().isoformat()}\nCapture date: {capture_date}\n\nMaterial:\n{full_text[:8000]}",
    )
    raw_events = result.get("events", [])
    if not isinstance(raw_events, list):
        return []
    events = []
    for raw in raw_events[:20]:
        if not isinstance(raw, dict) or not str(raw.get("title", "")).strip():
            continue
        try:
            event_date = date.fromisoformat(str(raw.get("date", "")))
        except ValueError:
            continue
        if event_date < date.today():
            continue
        start_time = raw.get("start_time") or None
        end_time = raw.get("end_time") or None
        try:
            if start_time:
                start_time = datetime.strptime(str(start_time), "%H:%M").strftime("%H:%M")
            if end_time:
                end_time = datetime.strptime(str(end_time), "%H:%M").strftime("%H:%M")
        except ValueError:
            start_time = None
            end_time = None
        events.append({
            "title": str(raw["title"]).strip()[:200],
            "event_date": event_date.isoformat(),
            "start_time": start_time,
            "end_time": end_time if start_time else None,
            "description": str(raw.get("description", "")).strip()[:1000],
        })
    return events


def _queue_calendar_reminders(item_id: int, full_text: str, capture_date: str,
                              source: str) -> None:
    try:
        for event in _extract_calendar_reminders(full_text, capture_date):
            description = f"Detected from Study Buddy: {source}"
            if event["description"]:
                description += f"\n\n{event['description']}"
            reminder_id = db.add_calendar_reminder(
                item_id, event["title"], event["event_date"],
                event["start_time"], event["end_time"], description,
            )
            if reminder_id:
                try:
                    from core import google_calendar
                    google_calendar.auto_reschedule_reminder(reminder_id)
                except Exception:
                    # The event remains a proposal if Google is offline or the
                    # calendar changes while ingestion is running.
                    logging.exception(
                        "Automatic calendar rescheduling failed",
                        extra={"reminder_id": reminder_id},
                    )
    except Exception:
        # Calendar automation must never prevent the source notes from being saved.
        traceback.print_exc()


def process_item(item: dict):
    db.set_status(item["id"], "processing")
    # A queued item stays an explicit error when the LAN LLM is down; do not
    # silently create a weaker transcript-only or heuristic note.
    llm.require_available()
    chunks = _extract(item)
    if not chunks:
        raise ValueError("no text could be extracted from this file")

    capture_date = item.get("capture_date") or datetime.fromtimestamp(
        item["created_at"]
    ).date().isoformat()
    capture_context = [f"[Capture date: {capture_date}]"]
    if item.get("metadata_text"):
        capture_context.append(f"[Capture context: {item['metadata_text'].strip()}]")
    chunks.insert(0, {"text": "\n".join(capture_context)})

    full_text = "\n\n".join(c["text"] for c in chunks)
    subject_name, title = _classify(full_text, item["filename"])
    subject_id = db.get_or_create_subject(subject_name)
    db.set_item_meta(item["id"], title, subject_id)

    visuals = _collect_visuals(item, chunks)
    notes_md = _generate_notes(full_text, chunks, title, visuals)
    db.add_note(item["id"], notes_md)

    source = f"{title} — {capture_date} ({item['filename']})"
    _queue_calendar_reminders(item["id"], full_text, capture_date, source)
    rows = []
    for c in chunks:
        chunk_id = db.add_chunk(
            item["id"], c["text"], source,
            ts_start=c.get("ts_start"), page=c.get("page"), image_path=c.get("image_path"),
        )
        rows.append({
            "chunk_id": chunk_id, "item_id": item["id"], "subject": subject_name,
            "source_label": source, "text": c["text"], "ts_start": c.get("ts_start"),
            "page": c.get("page"), "image_path": c.get("image_path"),
        })
    # index note sections too, so answers can draw on the synthesized notes
    for section in _split(notes_md):
        chunk_id = db.add_chunk(item["id"], section, source + " — notes")
        rows.append({
            "chunk_id": chunk_id, "item_id": item["id"], "subject": subject_name,
            "source_label": source + " — notes", "text": section,
        })
    try:
        vectorstore.add_chunks(rows)
    except Exception as error:
        raise RuntimeError(f"Vector indexing failed: {error}") from error
    db.set_status(item["id"], "done")


def enqueue_file(src: Path) -> int | None:
    kind = kind_of(src)
    if kind is None:
        return None
    dest = FILES_DIR / f"{int(time.time()*1000)}_{src.name}"
    shutil.copy2(src, dest)
    return db.add_item(src.name, str(dest), kind)


def _sweep_inbox():
    for f in sorted(INBOX_DIR.iterdir()):
        if f.is_file() and not f.name.startswith("."):
            # skip files still being written (e.g. an in-progress recording)
            size = f.stat().st_size
            time.sleep(0.5)
            if f.stat().st_size != size:
                continue
            if enqueue_file(f) is not None:
                f.unlink()


def worker_loop(stop: threading.Event | None = None):
    db.init_db()
    logger.info("ingestion worker ready")
    while stop is None or not stop.is_set():
        try:
            _sweep_inbox()
            item = db.claim_next_pending_item()
            if item is None:
                if stop is None:
                    time.sleep(2)
                else:
                    stop.wait(2)
                continue
            try:
                logger.info(
                    "ingestion started",
                    extra={
                        "item_id": item["id"],
                        "source_filename": item["filename"],
                    },
                )
                process_item(item)
                logger.info("ingestion completed", extra={"item_id": item["id"]})
            except Exception as e:
                logger.exception("ingestion failed", extra={"item_id": item["id"]})
                db.set_status(item["id"], "error", str(e)[:500])
        except Exception:
            logger.exception("ingestion worker iteration failed")
            if stop is None:
                time.sleep(5)
            else:
                stop.wait(5)
    logger.info("ingestion worker stopped")


_worker_lock = threading.Lock()
_worker_thread: threading.Thread | None = None
_worker_stop: threading.Event | None = None


def start_worker() -> threading.Thread:
    """Start the process-wide ingestion worker exactly once."""
    global _worker_thread, _worker_stop
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return _worker_thread
        _worker_stop = threading.Event()
        _worker_thread = threading.Thread(
            target=worker_loop,
            args=(_worker_stop,),
            daemon=True,
            name="ingest-worker",
        )
        _worker_thread.start()
        return _worker_thread


def stop_worker(timeout: float = 10.0) -> None:
    """Request a clean worker shutdown and wait for its current unit of work."""
    global _worker_thread, _worker_stop
    with _worker_lock:
        thread = _worker_thread
        stop = _worker_stop
        if thread is None:
            return
        if stop is not None:
            stop.set()
    thread.join(timeout=timeout)
    if thread.is_alive():
        logger.warning("ingestion worker did not stop before timeout")
        return
    with _worker_lock:
        if _worker_thread is thread:
            _worker_thread = None
            _worker_stop = None
