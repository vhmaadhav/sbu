"""Extract meaningful figures (diagrams, flowcharts, charts, photos) from
documents so they can be embedded inline in study notes.

PDF pages yield two kinds of candidate region: embedded raster images
(``page.get_image_info``) and clusters of vector drawing paths
(``page.get_drawings`` — a natively drawn flowchart). Geometry heuristics prune
obvious noise (rules, borders, page frames); a vision-LLM gate is the backstop
that rejects logos/decoration and captions what remains. Standalone image
uploads are registered directly, since the user chose to study that picture.
"""
import base64
import traceback
import uuid
from pathlib import Path

from core import db, llm
from core.config import FIGURES_DIR

# All thresholds are in PDF points (72 per inch).
MIN_SIDE = 42.0            # drop slivers: a figure is at least ~0.6"
MERGE_GAP = 14.0           # union vector paths closer than this into one figure
MAX_AREA_FRACTION = 0.92   # ignore near-full-page boxes (page frames/backgrounds)
MAX_CANDIDATES_PER_PAGE = 6
DEDUPE_IOU = 0.8
RENDER_DPI = 150

GATE_PROMPT = (
    "You are curating figures for study notes. Look at this image cropped from a "
    "document. If it is a meaningful diagram, flowchart, chart, graph, illustration, "
    "or photograph that helps understanding, reply with a single short caption line "
    "(no more than 12 words, no quotes). If it is only decoration, a logo, a page "
    "border, plain body text, or noise, reply with exactly NO_RELEVANT_CONTENT."
)

SENTINEL = "NO_RELEVANT_CONTENT"


def _b64(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode()


def _gate(png_bytes: bytes) -> str | None:
    """Return a short caption if the crop is a real figure, else None."""
    reply = llm.chat_vision(GATE_PROMPT, [_b64(png_bytes)], max_tokens=48).strip()
    caption = "\n".join(
        line for line in reply.splitlines() if line.strip() != SENTINEL
    ).strip()
    if not caption:
        return None
    return caption[:120]


def _rect_ok(rect, page_area: float) -> bool:
    width, height = rect[2] - rect[0], rect[3] - rect[1]
    if width < MIN_SIDE or height < MIN_SIDE:
        return False
    if width * height > page_area * MAX_AREA_FRACTION:
        return False
    return True


def _iou(a, b) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def _merge_boxes(boxes: list[tuple]) -> list[tuple]:
    """Union boxes whose gap-expanded rectangles overlap (repeat to fixpoint)."""
    boxes = [tuple(b) for b in boxes]
    changed = True
    while changed:
        changed = False
        merged: list[tuple] = []
        for box in boxes:
            for i, other in enumerate(merged):
                if _overlaps_within_gap(box, other):
                    merged[i] = (min(box[0], other[0]), min(box[1], other[1]),
                                 max(box[2], other[2]), max(box[3], other[3]))
                    changed = True
                    break
            else:
                merged.append(box)
        boxes = merged
    return boxes


def _overlaps_within_gap(a, b) -> bool:
    return (a[0] - MERGE_GAP < b[2] and b[0] - MERGE_GAP < a[2]
            and a[1] - MERGE_GAP < b[3] and b[1] - MERGE_GAP < a[3])


def _page_candidates(page) -> list[tuple]:
    page_rect = page.rect
    page_area = page_rect.width * page_rect.height
    raw: list[tuple] = []
    try:
        for info in page.get_image_info():
            raw.append(tuple(info["bbox"]))
    except Exception:
        pass
    try:
        vector = [tuple(d["rect"]) for d in page.get_drawings() if d.get("rect")]
        raw.extend(_merge_boxes(vector))
    except Exception:
        pass

    candidates: list[tuple] = []
    for box in raw:
        if not _rect_ok(box, page_area):
            continue
        if any(_iou(box, kept) > DEDUPE_IOU for kept in candidates):
            continue
        candidates.append(box)
    return candidates[:MAX_CANDIDATES_PER_PAGE]


def _persist(item_id: int, page: int | None, caption: str, png_bytes: bytes) -> dict:
    name = f"fig_{item_id}_{'img' if page is None else page}_{uuid.uuid4().hex[:8]}.png"
    path = FIGURES_DIR / name
    path.write_bytes(png_bytes)
    figure_id = db.add_doc_figure(item_id, page, caption, str(path))
    return {"figure_id": figure_id, "page": page, "caption": caption, "filename": name}


def extract_pdf_figures(pdf_path: str, item_id: int) -> list[dict]:
    """Vision-gated figures from a PDF: [{figure_id, page, caption, filename}]."""
    import fitz

    figures: list[dict] = []
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        traceback.print_exc()
        return figures
    with doc:
        for number, page in enumerate(doc, start=1):
            for box in _page_candidates(page):
                try:
                    import fitz as _fitz
                    pix = page.get_pixmap(clip=_fitz.Rect(box), dpi=RENDER_DPI, alpha=False)
                    png_bytes = pix.tobytes("png")
                    caption = _gate(png_bytes)
                    if caption:
                        figures.append(_persist(item_id, number, caption, png_bytes))
                except Exception:
                    traceback.print_exc()  # one bad crop must not stop extraction
    return figures


def _to_png_bytes(image_path: str) -> bytes:
    """Normalize any supported upload (jpg/heic/png/…) to PNG bytes."""
    import io

    from PIL import Image

    with Image.open(image_path) as image:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        return buffer.getvalue()


def register_image_figure(image_path: str, item_id: int) -> dict | None:
    """Register a standalone uploaded image as a figure (always kept)."""
    try:
        png_bytes = _to_png_bytes(image_path)
    except Exception:
        traceback.print_exc()
        return None
    try:
        caption = _gate(png_bytes) or "Uploaded image"
    except Exception:
        traceback.print_exc()
        caption = "Uploaded image"
    return _persist(item_id, None, caption, png_bytes)
