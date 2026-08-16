"""Lecture-video board capture and progressive OCR review helpers."""
import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageStat

from core import db, llm, mathmd
from core.config import VIDEO_CROPS_DIR, VIDEO_FRAMES_DIR

SAMPLE_SECONDS = 1
STABLE_DELTA = 3.2
STABLE_SAMPLES = 3
MIN_CONTENT_DELTA = 7.0


def optimize_for_streaming(video_path: str | Path) -> bool:
    """Move MP4/MOV metadata to the front for reliable browser seeking.

    FFmpeg writes to a sibling temporary file first so an interrupted or failed
    remux can never corrupt the uploaded source. Other supported video
    containers do not use the MP4 ``moov`` atom and are already seekable via
    HTTP range requests, so they are left unchanged.
    """
    source = Path(video_path)
    if not source.is_file():
        raise FileNotFoundError(f"Video file not found: {source}")
    if source.suffix.lower() not in {".mp4", ".mov"}:
        return False

    with tempfile.NamedTemporaryFile(
        prefix=f".{source.stem}-streaming-",
        suffix=source.suffix,
        dir=source.parent,
        delete=False,
    ) as temporary:
        output = Path(temporary.name)

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-map_metadata",
                "0",
                "-map_chapters",
                "0",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output),
            ],
            check=True,
            capture_output=True,
        )
        if output.stat().st_size == 0:
            raise RuntimeError("FFmpeg produced an empty optimized video")
        os.chmod(output, source.stat().st_mode)
        os.replace(output, source)
        return True
    finally:
        output.unlink(missing_ok=True)


def _frame_samples(video_path: str):
    with tempfile.TemporaryDirectory(prefix="study-video-") as folder:
        pattern = str(Path(folder) / "frame_%06d.jpg")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video_path,
                        "-vf", f"fps=1/{SAMPLE_SECONDS},scale='min(1280,iw)':-2", "-q:v", "3", pattern],
                       check=True)
        for index, path in enumerate(sorted(Path(folder).glob("frame_*.jpg"))):
            with Image.open(path) as image:
                yield index * SAMPLE_SECONDS, image.convert("RGB").copy()


def _thumbnail(image: Image.Image) -> Image.Image:
    small = image.convert("L")
    small.thumbnail((240, 240))
    return small


def _difference(a: Image.Image, b: Image.Image) -> float:
    return float(ImageStat.Stat(ImageChops.difference(a, b)).mean[0])


def _sharpness(image: Image.Image) -> float:
    return float(ImageStat.Stat(image.convert("L").filter(ImageFilter.FIND_EDGES)).var[0])


def _save_candidate(item_id: int, candidate, last_saved: Image.Image | None, saved: list[int]):
    timestamp, image, stability = candidate
    thumb = _thumbnail(image)
    if last_saved is not None and _difference(last_saved, thumb) < MIN_CONTENT_DELTA:
        return last_saved
    path = VIDEO_FRAMES_DIR / f"video_{item_id}_{timestamp:07.2f}.jpg"
    image.save(path, quality=94)
    saved.append(db.add_video_frame(item_id, timestamp, str(path), stability, _sharpness(image)))
    return thumb


def capture_stable_frames(item_id: int, video_path: str) -> list[int]:
    """Retain the sharpest image after a board has been still for 3 seconds."""
    saved, stable, previous, last_saved = [], [], None, None
    for timestamp, image in _frame_samples(video_path):
        thumb = _thumbnail(image)
        delta = _difference(previous, thumb) if previous else 999.0
        if delta <= STABLE_DELTA:
            stable.append((timestamp, image, delta))
        else:
            if len(stable) >= STABLE_SAMPLES:
                last_saved = _save_candidate(item_id, max(stable, key=lambda f: _sharpness(f[1])), last_saved, saved)
            stable = []
        previous = thumb
    if len(stable) >= STABLE_SAMPLES:
        _save_candidate(item_id, max(stable, key=lambda f: _sharpness(f[1])), last_saved, saved)
    return saved


def _bbox_pixels(bbox, width: int, height: int) -> tuple[int, int, int, int]:
    x, y, w, h = bbox
    if max(abs(x), abs(y), abs(w), abs(h)) <= 1.5:
        # Vision/ocrmac coordinates are normalized with a lower-left origin;
        # Pillow crops use a top-left origin.
        x, y, w, h = x * width, height - (y + h) * height, w * width, h * height
    return max(0, int(x)), max(0, int(y)), min(width, int(x + w)), min(height, int(y + h))


def _regions(image_path: str):
    from core.ocr import ocr_image_annotations
    with Image.open(image_path) as image:
        width, height = image.size
    boxes = []
    try:
        annotations = ocr_image_annotations(image_path)
    except Exception:
        annotations = []
    for _, _, bbox in annotations:
        try:
            left, top, right, bottom = _bbox_pixels(bbox, width, height)
            if right - left > 12 and bottom - top > 8:
                boxes.append((max(0, left - 14), max(0, top - 14), min(width, right + 14), min(height, bottom + 14)))
        except Exception:
            continue
    if not boxes:
        step = max(1, height // 4)
        boxes = [(0, y, width, min(height, y + step)) for y in range(0, height, step)]
    return boxes


def prepare_segments(frame_id: int) -> list[dict]:
    frame = db.get_video_frame(frame_id)
    if not frame:
        raise ValueError("frame not found")
    existing = db.list_video_segments(frame_id)
    if existing:
        return existing
    with Image.open(frame["frame_path"]) as image:
        for index, box in enumerate(_regions(frame["frame_path"])):
            crop_path = VIDEO_CROPS_DIR / f"frame_{frame_id}_{index:03d}.png"
            image.crop(box).save(crop_path)
            db.add_video_segment(frame_id, index, json.dumps(box), str(crop_path))
    return db.list_video_segments(frame_id)


def _table_from_annotations(annotations) -> str | None:
    rows = []
    for text, _, bbox in annotations:
        try:
            rows.append((float(bbox[1]), float(bbox[0]), text.strip()))
        except Exception:
            pass
    rows.sort(key=lambda row: (-row[0], row[1]))  # Vision y=0 is image bottom
    grouped: list[list[tuple[float, float, str]]] = []
    for y, x, text in rows:
        if not text:
            continue
        if not grouped or abs(y - grouped[-1][0][0]) > 0.035:
            grouped.append([(y, x, text)])
        else:
            grouped[-1].append((y, x, text))
    values = [[text for _, _, text in sorted(row, key=lambda c: c[1])] for row in grouped]
    if len(values) < 2 or max(map(len, values)) < 2:
        return None
    columns = max(map(len, values))
    if sum(len(row) == columns for row in values) < 2:
        return None
    values = [row + [""] * (columns - len(row)) for row in values]
    return "| " + " | ".join(values[0]) + " |\n| " + " | ".join(["---"] * columns) + " |\n" + "\n".join("| " + " | ".join(row) + " |" for row in values[1:])


def run_segment_ocr(segment: dict) -> dict:
    from core.ocr import ocr_image_annotations
    annotations = ocr_image_annotations(segment["crop_path"])
    text = "\n".join(item[0] for item in annotations).strip()
    table = _table_from_annotations(annotations)
    db.set_video_segment_result(segment["id"], text, table)
    segment.update(raw_text=text, table_markdown=table, status="done")
    return segment


def consolidate_frame(frame_id: int, reviewed: bool = True) -> dict:
    """Reconcile crop OCR against the complete image."""
    frame = db.get_video_frame(frame_id)
    if not frame:
        raise ValueError("frame not found")
    segments = db.list_video_segments(frame_id)
    raw = "\n\n".join(f"Segment {s['segment_index']}:\n{s['raw_text']}" +
                       (f"\nDetected table:\n{s['table_markdown']}" if s["table_markdown"] else "")
                       for s in segments if s["raw_text"] or s["table_markdown"])
    image = base64.b64encode(Path(frame["frame_path"]).read_bytes()).decode()
    authority = "verified lecture-board" if reviewed else "candidate lecture"
    # The OCR is a hint, not a subject: earlier prompts asked for a
    # reconciliation report, and the model dutifully wrote paragraphs about
    # which words the OCR got wrong. Those reports averaged 3.5 KB per frame,
    # dwarfed the spoken transcript in note generation, and surfaced in notes
    # as commentary about OCR quality instead of about the lecture.
    prompt = (f"This {authority} image is the authority; the supplied OCR is only a hint that may "
              "contain errors. Write down what the board itself shows, correcting the OCR silently "
              "against the image and inventing nothing. Return only compact Markdown: one short "
              "'# ' title line, then the board's content — formulas verbatim, Markdown tables where "
              "the board has tables, and at most one brief line describing any diagram. Never "
              "comment on the OCR, its errors, or your own corrections, and never add a notes, "
              "reconciliation, or commentary section. "
              "If there is no educational writing, diagram, table, or slide, return exactly NO_RELEVANT_CONTENT. "
              "Output only Markdown.\n\nOCR hint:\n" +
              (raw or "(No legible OCR.)"))
    markdown = llm.chat_vision(prompt, [image], max_tokens=700)
    # Some local vision models append the sentinel after a useful answer even
    # when instructed to return it alone. Preserve useful analysis, but never
    # leak the control token into notes or RAG.
    markdown = "\n".join(
        line for line in markdown.splitlines()
        if line.strip() != "NO_RELEVANT_CONTENT"
    ).strip() or "NO_RELEVANT_CONTENT"
    # Board formulas arrive in whichever math dialect the vision model prefers,
    # and this Markdown is read directly and folded into notes.
    markdown = mathmd.normalize(markdown)
    db.set_video_frame_review(frame_id, raw, markdown, reviewed=reviewed)
    return {"frame": db.get_video_frame(frame_id), "markdown": markdown}


def analyze_frame(frame_id: int) -> dict:
    """Run every small OCR segment, then one full-image reconciliation."""
    segments = prepare_segments(frame_id)
    for segment in segments:
        if segment["status"] != "done":
            try:
                run_segment_ocr(segment)
            except Exception:
                # Vision reconciliation can still understand diagrams without OCR.
                db.set_video_segment_result(segment["id"], "", None)
    return consolidate_frame(frame_id, reviewed=False)
