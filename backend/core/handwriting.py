"""Handwritten-notes recognition via the LM Studio vision model.

Pipeline: page image -> line segmentation (Apple Vision boxes, projection-profile
fallback) -> each line crop is zoomed and sent to the vision model, which replies
with the transcribed text -> the user edits any line. Corrections are kept and
fed back as vocabulary hints, so the model resolves the writer's ambiguous words
toward what they've written before (a local model in LM Studio can't be
fine-tuned, so this text-hint personalization is how it "learns" a hand).

This replaced an on-device TrOCR model, which was unusable on real, messy
handwriting; a general vision LLM reads cursive and mixed print far better.
"""
import base64
import io
import json
import uuid
from pathlib import Path

from core import db, llm
from core.config import HW_CROPS_DIR

LINE_PAD = 6            # px of context around each line crop
MERGE_OVERLAP = 0.4    # vertical-overlap ratio to merge fragments into one line
MIN_LINE_HEIGHT = 8    # px; ignore specks
ZOOM_TARGET_HEIGHT = 120  # px; upscale short line crops so the model sees detail
ZOOM_MAX_WIDTH = 1800     # px; cap the sent image so payloads stay reasonable
VOCAB_HINT_WORDS = 60     # how many past corrected words to offer as hints

TRANSCRIBE_PROMPT = (
    "You are transcribing a single line of handwritten notes. "
    "Read the handwriting in the image and reply with exactly what is written — "
    "the literal text, on one line. Do not translate, summarize, explain, or add "
    "quotation marks or labels. If a word is unclear, give your best single guess. "
    "Reply with the transcription only."
)


# ---------------------------------------------------------------- segmentation

def _vision_line_boxes(image_path: str) -> list[tuple]:
    """Line boxes (x1,y1,x2,y2) from Apple Vision, merged by vertical overlap."""
    try:
        from ocrmac import ocrmac
        annotations = ocrmac.OCR(image_path, recognition_level="accurate").recognize(px=True)
    except Exception:
        return []
    boxes = []
    for _text, _conf, bbox in annotations:
        x1, y1, x2, y2 = (float(v) for v in bbox)
        if y2 - y1 >= MIN_LINE_HEIGHT:
            boxes.append([x1, y1, x2, y2])
    if not boxes:
        return []
    # merge fragments that share a text line (handwriting rarely detects as one box)
    boxes.sort(key=lambda b: (b[1], b[0]))
    lines: list[list[float]] = []
    for b in boxes:
        for line in lines:
            overlap = min(line[3], b[3]) - max(line[1], b[1])
            if overlap > MERGE_OVERLAP * min(line[3] - line[1], b[3] - b[1]):
                line[0] = min(line[0], b[0])
                line[1] = min(line[1], b[1])
                line[2] = max(line[2], b[2])
                line[3] = max(line[3], b[3])
                break
        else:
            lines.append(list(b))
    lines.sort(key=lambda l: l[1])
    return [tuple(l) for l in lines]


def _projection_line_boxes(img) -> list[tuple]:
    """Fallback: split on horizontal whitespace gaps in the ink profile."""
    import numpy as np

    gray = np.asarray(img.convert("L"), dtype=np.float32)
    ink = gray < (gray.mean() - 0.25 * gray.std())  # darker-than-page pixels
    profile = ink.sum(axis=1)
    threshold = max(2.0, 0.02 * profile.max()) if profile.max() else 0
    rows = profile > threshold

    lines, start = [], None
    for y, on in enumerate(rows):
        if on and start is None:
            start = y
        elif not on and start is not None:
            if y - start >= MIN_LINE_HEIGHT:
                cols = ink[start:y].any(axis=0).nonzero()[0]
                if cols.size:
                    lines.append((float(cols[0]), float(start), float(cols[-1] + 1), float(y)))
            start = None
    if start is not None and img.height - start >= MIN_LINE_HEIGHT:
        cols = ink[start:].any(axis=0).nonzero()[0]
        if cols.size:
            lines.append((float(cols[0]), float(start), float(cols[-1] + 1), float(img.height)))
    return lines


def segment_lines(image_path: str) -> list[dict]:
    """Returns [{bbox, image}] line crops, top to bottom."""
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    boxes = _vision_line_boxes(image_path)
    if not boxes:
        boxes = _projection_line_boxes(img)
    if not boxes:  # nothing detected: treat the whole page as one line
        boxes = [(0.0, 0.0, float(img.width), float(img.height))]

    crops = []
    for x1, y1, x2, y2 in boxes:
        x1 = max(0, int(x1) - LINE_PAD)
        y1 = max(0, int(y1) - LINE_PAD)
        x2 = min(img.width, int(x2) + LINE_PAD)
        y2 = min(img.height, int(y2) + LINE_PAD)
        crops.append({"bbox": (x1, y1, x2, y2), "image": img.crop((x1, y1, x2, y2))})
    return crops


# ---------------------------------------------------------------- recognition

def _zoom(img):
    """Upscale a short line crop so the vision model sees the strokes clearly."""
    from PIL import Image

    if img.height <= 0 or img.width <= 0:
        return img
    scale = ZOOM_TARGET_HEIGHT / img.height
    scale = min(scale, ZOOM_MAX_WIDTH / img.width) if img.width else scale
    if scale <= 1.0:
        return img
    return img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                      Image.LANCZOS)


def _to_b64(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _vocabulary_hint() -> str:
    """Distinct words the writer has previously corrected, most recent first."""
    words, seen = [], set()
    for row in reversed(db.hw_corrected_lines()):
        for raw in (row["corrected_text"] or "").split():
            w = raw.strip(".,:;\"'()[]!?").strip()
            key = w.lower()
            if w and key not in seen and any(c.isalpha() for c in w):
                seen.add(key)
                words.append(w)
            if len(words) >= VOCAB_HINT_WORDS:
                return ", ".join(words)
    return ", ".join(words)


def _clean(text: str) -> str:
    text = " ".join(text.split())
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def recognize_line(img, hint: str = "") -> str:
    prompt = TRANSCRIBE_PROMPT
    if hint:
        prompt += (
            "\n\nThis writer commonly uses these words; prefer them when a word "
            f"is ambiguous: {hint}."
        )
    text = llm.chat_vision(prompt, [_to_b64(_zoom(img))])
    return _clean(text)


def recognize_lines(images: list) -> list[str]:
    hint = _vocabulary_hint()
    return [recognize_line(img, hint) for img in images]


def process_page(page_id: int):
    """Segment the page image into lines, transcribe each, store results.

    Idempotent: any lines from a previous (possibly interrupted) run are
    replaced, so re-processing a page never duplicates rows.
    """
    page = db.get_hw_page(page_id)
    try:
        db.delete_hw_lines(page_id)
        crops = segment_lines(page["image_path"])
        hint = _vocabulary_hint()
        for i, crop in enumerate(crops):
            crop_path = HW_CROPS_DIR / f"p{page_id}_l{i}_{uuid.uuid4().hex[:6]}.png"
            crop["image"].save(crop_path)
            text = recognize_line(crop["image"], hint)
            db.add_hw_line(page_id, i, json.dumps(crop["bbox"]), str(crop_path), text)
        db.set_hw_page_status(page_id, "done")
    except Exception as e:
        db.set_hw_page_status(page_id, "error", str(e)[:500])
        raise


def recognize_item_page(item_id: int, image_path: str) -> str:
    """Ingestion-pipeline entry: register a captured image as a correctable
    handwriting page, transcribe it, and return the page text."""
    page_id = db.add_hw_page(Path(image_path).name, image_path, item_id=item_id)
    process_page(page_id)
    lines = db.list_hw_lines(page_id)
    return "\n".join(ln["pred_text"] for ln in lines if ln["pred_text"]).strip()
