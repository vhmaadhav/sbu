"""Shared FastAPI backend for Study Buddy web and mobile clients.

The normal startup path is ``make backend`` from the repository root.
"""
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.routing import APIRoute
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from core import (
    concepts, db, flashcards, gaps, llm, mastery, note_pdf,
    notes as notes_module, planner, question_papers, quiz, rag, report, vectorstore,
)
from core.config import (
    AUDIOBOOKS_DIR, DATA_DIR, FIGURES_DIR, FILES_DIR, HW_CROPS_DIR, HW_PAGES_DIR,
    INBOX_DIR, kind_of, settings,
)
from core.dates import capture_date_from_text, event_date_from_due_text
from core.ingest import start_worker, stop_worker
from study_buddy import __version__

logger = logging.getLogger(__name__)

# Backward-compatible names for callers that imported the original server helpers.
_capture_date_from_text = capture_date_from_text
_event_date_from_due_text = event_date_from_due_text

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialize and stop process-owned services exactly once."""
    started_at = time.monotonic()
    logger.info("initializing API services")
    db.init_db()
    worker = start_worker()
    application.state.started_at = started_at
    application.state.ingestion_worker = worker
    logger.info(
        "API services ready",
        extra={
            "version": application.version,
            "environment": settings.environment,
            "ingestion_worker": worker.name,
        },
    )
    try:
        yield
    finally:
        logger.info("shutting down API services")
        stop_worker()


app = FastAPI(
    title="Study Buddy API",
    description=(
        "The stable, shared HTTP contract for Study Buddy web and mobile clients."
    ),
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    openapi_tags=[
        {"name": "system", "description": "Service metadata, health, and activity."},
        {"name": "library", "description": "Subjects, source items, and uploads."},
        {"name": "notes", "description": "Portable and editable study notes."},
        {"name": "chat", "description": "Grounded questions and conversation history."},
        {"name": "video", "description": "Lecture video review and board extraction."},
        {"name": "flashcards", "description": "Generated study decks."},
        {"name": "question-papers", "description": "Grounded assessments generated from notes."},
        {"name": "audiobooks", "description": "Generated audio study material."},
        {"name": "calendar", "description": "Calendar connection and reminder proposals."},
        {"name": "tasks", "description": "Student tasks and completion state."},
        {"name": "handwriting", "description": "Handwriting recognition and correction."},
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts))


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a trace identifier and emit one concise access event."""
    request_id = request.headers.get("X-Request-ID", "").strip()[:128] or uuid.uuid4().hex
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "unhandled request failure",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
    response.headers["X-API-Version"] = app.version
    logger.info(
        "request completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": elapsed_ms,
        },
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, _: Exception):
    """Return a stable public error shape without exposing internals."""
    request_id = request.headers.get("X-Request-ID", "").strip()[:128]
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected server error occurred",
            "request_id": request_id or None,
        },
    )


@app.get("/api", tags=["system"], summary="Describe the API")
def api_metadata():
    """Stable discovery endpoint shared by web and mobile clients."""
    return {
        "service": settings.service_name,
        "version": app.version,
        "docs": "/api/docs",
        "openapi": "/api/openapi.json",
        "health": {
            "live": "/api/health/live",
            "ready": "/api/health/ready",
        },
    }


@app.get("/api/health")
def health():
    """Compatibility readiness check used by existing clients."""
    vector_index = True
    try:
        vectorstore.ensure_ready()
    except Exception:
        vector_index = False
        logging.exception("LanceDB health check failed")
    return {
        "ok": vector_index,
        "service": "study-buddy-api",
        "version": app.version,
        "llm": llm.is_available(),
        "storage": DATA_DIR.exists() and os.access(DATA_DIR, os.W_OK),
        "vector_index": vector_index,
    }


@app.get("/api/health/live", include_in_schema=False)
def liveness():
    """Cheap orchestration probe: the HTTP process can answer requests."""
    return {
        "ok": True,
        "service": settings.service_name,
        "version": app.version,
        "uptime_seconds": round(time.monotonic() - app.state.started_at, 1)
        if hasattr(app.state, "started_at")
        else 0,
    }


@app.get("/api/health/ready", include_in_schema=False)
def readiness():
    """Dependency-aware probe suitable for traffic readiness checks."""
    payload = health()
    status_code = 200 if payload["ok"] and payload["storage"] else 503
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/api/stats")
def stats():
    with db.conn() as c:
        notes = c.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        files = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        chunks = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        flashcard_total = c.execute("SELECT COUNT(*) FROM flashcards").fetchone()[0]
    audiobooks = len(list(AUDIOBOOKS_DIR.glob("*.wav")))
    usage = shutil.disk_usage(DATA_DIR)
    return {
        "notes": notes, "files": files, "chunks": chunks,
        "flashcards": flashcard_total, "audiobooks": audiobooks,
        "disk_used_gb": round((usage.total - usage.free) / 1e9, 1),
        "disk_total_gb": round(usage.total / 1e9, 1),
    }


@app.get("/api/subjects")
def subjects():
    return db.list_subjects()


class SubjectCreate(BaseModel):
    name: str


@app.post("/api/subjects")
def create_subject(req: SubjectCreate):
    name = " ".join(req.name.split())
    if not name:
        raise HTTPException(400, "Folder name is required")
    if len(name) > 80:
        raise HTTPException(400, "Folder name must be 80 characters or fewer")
    with db.conn() as c:
        existing = c.execute(
            "SELECT id, name, created_at FROM subjects WHERE name=? COLLATE NOCASE", (name,)
        ).fetchone()
        if existing:
            return dict(existing)
        subject_id = c.execute(
            "INSERT INTO subjects (name, created_at) VALUES (?,?)", (name, time.time())
        ).lastrowid
        row = c.execute("SELECT * FROM subjects WHERE id=?", (subject_id,)).fetchone()
    return dict(row)


@app.get("/api/items")
def items(subject_id: int | None = None):
    return db.list_items(subject_id)


@app.post("/api/items/{item_id}/retry")
def retry_item(item_id: int):
    item = db.get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    if item["status"] != "error":
        raise HTTPException(409, "Only failed items can be retried")

    rows = db.index_rows_for_item(item_id)
    with db.conn() as c:
        has_note = c.execute(
            "SELECT 1 FROM notes WHERE item_id=? LIMIT 1", (item_id,)
        ).fetchone() is not None

    # Ingestion writes notes and SQLite chunks before the vector index. If both
    # are present, repair only the missing final step so retrying cannot create
    # duplicate notes, reminders, or chunks.
    if has_note and rows:
        try:
            vectorstore.add_chunks(rows)
        except Exception as error:
            db.set_status(item_id, "error", f"Vector indexing failed: {error}"[:500])
            raise HTTPException(503, "The vector index could not be repaired")
        db.set_status(item_id, "done")
        return {"ok": True, "status": "done", "recovered": "vector_index"}

    db.retry_item(item_id)
    return {"ok": True, "status": "pending", "recovered": "requeued"}


@app.get("/api/notes")
def notes(limit: int = 20):
    limit = max(1, min(limit, 200))
    with db.conn() as c:
        rows = c.execute(
            "SELECT notes.id, notes.item_id, notes.markdown, notes.created_at, "
            "items.title, items.kind, items.subject_id, subjects.name AS subject "
            "FROM notes JOIN items ON items.id = notes.item_id "
            "LEFT JOIN subjects ON subjects.id = items.subject_id "
            "ORDER BY notes.created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        body = d.pop("markdown")
        d["preview"] = " ".join(body.replace("#", "").replace("*", "").split())[:120]
        out.append(d)
    return out


def _download_name(title: str | None, suffix: str) -> str:
    """Build a safe, readable filename for a Content-Disposition header."""
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "", title or "note").strip(" .") or "note"
    return f"{stem[:80]}{suffix}"


@app.get("/api/notes/export")
def export_notes():
    with db.conn() as c:
        rows = c.execute(
            "SELECT items.title, subjects.name AS subject, notes.markdown, notes.created_at "
            "FROM notes JOIN items ON items.id = notes.item_id "
            "LEFT JOIN subjects ON subjects.id = items.subject_id "
            "ORDER BY notes.created_at"
        ).fetchall()
    backup = {
        "format": "study-buddy-notes",
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "notes": [dict(row) for row in rows],
    }
    stamp = datetime.now().strftime("%Y-%m-%d")
    return Response(
        content=json.dumps(backup, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="study-buddy-notes-{stamp}.json"'},
    )


@app.post("/api/notes/import")
async def import_notes(backup: UploadFile):
    raw = await backup.read(100_000_001)
    if len(raw) > 100_000_000:
        raise HTTPException(413, "Import file is larger than 100 MB")
    filename = backup.filename or ""
    if Path(filename).suffix.lower() in {".md", ".markdown", ".txt"}:
        try:
            markdown = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(400, "Markdown notes must use UTF-8 text encoding")
        payload = {
            "format": "study-buddy-notes",
            "version": 1,
            "notes": [{
                "title": Path(filename).stem.strip() or "Imported note",
                "subject": "Imported",
                "markdown": markdown,
            }],
        }
    else:
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise HTTPException(400, "Choose a Study Buddy JSON backup or a Markdown note")

        if not isinstance(payload, dict) or payload.get("format") != "study-buddy-notes":
            raise HTTPException(400, "This is not a Study Buddy notes backup")
        if payload.get("version") != 1 or not isinstance(payload.get("notes"), list):
            raise HTTPException(400, "This backup version is not supported")

    imported = 0
    skipped = 0
    now = time.time()
    with db.conn() as c:
        for entry in payload["notes"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("markdown"), str):
                raise HTTPException(400, "The backup contains an invalid note")
            markdown = entry["markdown"]
            if not markdown.strip():
                skipped += 1
                continue
            title = entry.get("title") if isinstance(entry.get("title"), str) else None
            subject = entry.get("subject") if isinstance(entry.get("subject"), str) else None
            created_at = entry.get("created_at")
            if not isinstance(created_at, (int, float)) or created_at <= 0:
                created_at = now

            duplicate = c.execute(
                "SELECT 1 FROM notes JOIN items ON items.id = notes.item_id "
                "LEFT JOIN subjects ON subjects.id = items.subject_id "
                "WHERE notes.markdown=? AND COALESCE(items.title, '')=? "
                "AND COALESCE(subjects.name, '')=? LIMIT 1",
                (markdown, title or "", subject or ""),
            ).fetchone()
            if duplicate:
                skipped += 1
                continue

            subject_id = None
            if subject and subject.strip():
                clean_subject = subject.strip()
                row = c.execute("SELECT id FROM subjects WHERE name=?", (clean_subject,)).fetchone()
                subject_id = row["id"] if row else c.execute(
                    "INSERT INTO subjects (name, created_at) VALUES (?,?)", (clean_subject, now)
                ).lastrowid
            filename = _download_name(title, ".md")
            item_id = c.execute(
                "INSERT INTO items "
                "(filename, stored_path, kind, status, title, subject_id, created_at, processed_at) "
                "VALUES (?,?,?,'done',?,?,?,?)",
                (filename, "", "imported note", title, subject_id, created_at, now),
            ).lastrowid
            c.execute(
                "INSERT INTO notes (item_id, markdown, created_at) VALUES (?,?,?)",
                (item_id, markdown, created_at),
            )
            imported += 1
    return {"imported": imported, "skipped": skipped}


@app.get("/api/notes/{note_id}/download")
def download_note(note_id: int):
    with db.conn() as c:
        row = c.execute(
            "SELECT notes.markdown, notes.created_at, items.id AS item_id, items.title, "
            "subjects.name AS subject FROM notes "
            "JOIN items ON items.id = notes.item_id "
            "LEFT JOIN subjects ON subjects.id = items.subject_id "
            "WHERE notes.id=?", (note_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Note not found")
    return Response(
        content=note_pdf.to_pdf(
            row["markdown"],
            title=row["title"],
            subject=row["subject"],
            created_at=row["created_at"],
            image_paths=note_pdf.image_paths_for_item(row["item_id"]),
        ),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{_download_name(row["title"], ".pdf")}"'
        },
    )


@app.get("/api/notes/{note_id}")
def note_detail(note_id: int):
    with db.conn() as c:
        row = c.execute(
            "SELECT notes.*, items.title, subjects.name AS subject "
            "FROM notes JOIN items ON items.id = notes.item_id "
            "LEFT JOIN subjects ON subjects.id = items.subject_id "
            "WHERE notes.id=?", (note_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Note not found")
    detail = dict(row)
    images = [
        {
            "id": figure["id"],
            "page": figure["page"],
            "caption": figure["caption"],
            "url": f"/api/doc/figures/{Path(figure['image_path']).name}",
        }
        for figure in db.list_doc_figures(detail["item_id"])
        if Path(figure["image_path"]).exists()
    ]
    known_urls = {image["url"] for image in images}
    for caption, url in re.findall(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+[^)]*)?\)", detail["markdown"]):
        if url.startswith("/api/") and url not in known_urls:
            images.append({"id": None, "page": None, "caption": caption, "url": url})
            known_urls.add(url)
    detail["images"] = images
    return detail


class NoteMove(BaseModel):
    subject_id: int


@app.patch("/api/notes/{note_id}")
def move_note(note_id: int, req: NoteMove):
    with db.conn() as c:
        subject = c.execute(
            "SELECT id, name FROM subjects WHERE id=?", (req.subject_id,)
        ).fetchone()
        if not subject:
            raise HTTPException(404, "Subject folder not found")
        note = c.execute(
            "SELECT notes.item_id FROM notes WHERE notes.id=?", (note_id,)
        ).fetchone()
        if not note:
            raise HTTPException(404, "Note not found")
        c.execute(
            "UPDATE items SET subject_id=? WHERE id=?", (subject["id"], note["item_id"])
        )
    try:
        vectorstore.update_item_subject(note["item_id"], subject["name"])
    except Exception:
        logging.exception("Could not synchronize moved note with the vector index")
    return {"ok": True, "subject_id": subject["id"], "subject": subject["name"]}


class NoteEdit(BaseModel):
    markdown: str


@app.put("/api/notes/{note_id}")
def edit_note(note_id: int, req: NoteEdit):
    markdown = req.markdown.strip()
    if not markdown:
        raise HTTPException(400, "Note cannot be empty")
    with db.conn() as c:
        row = c.execute(
            "SELECT notes.item_id, items.title, items.filename, items.capture_date, "
            "items.created_at, subjects.name AS subject FROM notes "
            "JOIN items ON items.id = notes.item_id "
            "LEFT JOIN subjects ON subjects.id = items.subject_id WHERE notes.id=?",
            (note_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Note not found")
    capture_date = row["capture_date"] or datetime.fromtimestamp(
        row["created_at"]
    ).date().isoformat()
    source = f"{row['title'] or row['filename']} — {capture_date} ({row['filename']})"
    notes_module.update_note_markdown(
        note_id, row["item_id"], markdown, source, row["subject"] or "General",
    )
    return {"ok": True, "markdown": markdown}


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: int):
    with db.conn() as c:
        note = c.execute(
            "SELECT notes.item_id, items.kind FROM notes "
            "JOIN items ON items.id=notes.item_id WHERE notes.id=?", (note_id,)
        ).fetchone()
        if not note:
            raise HTTPException(404, "Note not found")
        indexed_note_chunks = [row["id"] for row in c.execute(
            "SELECT id FROM chunks WHERE item_id=? AND source_label LIKE '% — notes'",
            (note["item_id"],),
        ).fetchall()]
        c.execute("DELETE FROM notes WHERE id=?", (note_id,))
        if indexed_note_chunks:
            placeholders = ",".join("?" for _ in indexed_note_chunks)
            c.execute(f"DELETE FROM chunks WHERE id IN ({placeholders})", indexed_note_chunks)
        remaining = c.execute(
            "SELECT COUNT(*) FROM notes WHERE item_id=?", (note["item_id"],)
        ).fetchone()[0]
        if note["kind"] == "imported note" and remaining == 0:
            c.execute("DELETE FROM items WHERE id=?", (note["item_id"],))
    if remaining == 0:
        # No note references this item's figures any more — reclaim them.
        for figure_path in db.delete_doc_figures_for_item(note["item_id"]):
            try:
                Path(figure_path).unlink(missing_ok=True)
            except OSError:
                pass
    try:
        vectorstore.delete_chunks(indexed_note_chunks)
    except Exception:
        logging.exception("Could not synchronize deleted note with the vector index")
    return {"ok": True}


@app.post("/api/upload")
async def upload(
    files: list[UploadFile] | None = File(default=None),
    text: str = Form(default=""),
):
    """Stream uploads to permanent storage and queue them immediately."""
    clean_text = text.strip()
    if not files and not clean_text:
        raise HTTPException(400, "Add at least one file or some text")
    if len(clean_text) > 1_000_000:
        raise HTTPException(413, "Text is larger than 1 MB")
    dated = capture_date_from_text(clean_text)

    queued = []
    for upload_file in files or []:
        filename = Path(upload_file.filename or "upload").name
        extension_kind = kind_of(Path(filename))
        if extension_kind is None:
            raise HTTPException(415, f"Unsupported file type: {filename}")
        # MediaRecorder commonly produces audio-only WebM files. The .webm
        # extension alone is ambiguous, so prefer the browser-provided media
        # family after the extension has passed the supported-file allowlist.
        content_type = (upload_file.content_type or "").lower()
        upload_kind = (
            "audio" if content_type.startswith("audio/")
            else "video" if content_type.startswith("video/")
            else extension_kind
        )
        token = uuid.uuid4().hex
        destination = FILES_DIR / f"{int(time.time() * 1000)}_{token}_{filename}"
        partial = destination.with_suffix(destination.suffix + ".part")
        size = 0
        try:
            with partial.open("wb") as output:
                while block := await upload_file.read(1024 * 1024):
                    size += len(block)
                    if size > settings.max_upload_mb * 1024 * 1024:
                        raise HTTPException(
                            413,
                            f"{filename} is larger than {settings.max_upload_mb} MB",
                        )
                    output.write(block)
            if size == 0:
                raise HTTPException(400, f"{filename} is empty")
            os.replace(partial, destination)
            item_id = db.add_item(filename, str(destination), upload_kind, clean_text or None, dated)
            queued.append({"id": item_id, "filename": filename, "size": size, "kind": upload_kind})
        except Exception:
            partial.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise
        finally:
            await upload_file.close()

    if not files:
        filename = f"text-capture-{dated}-{uuid4().hex[:6]}.txt"
        dest = FILES_DIR / filename
        dest.write_text(clean_text, encoding="utf-8")
        item_id = db.add_item(filename, str(dest), "text", None, dated)
        queued.append({"id": item_id, "filename": filename, "size": len(clean_text)})

    return {"queued": len(queued), "items": queued, "capture_date": dated}


class AskRequest(BaseModel):
    question: str
    subject: str | None = None


def _answer_question(question: str, subject: str | None = None):
    question = question.strip()
    if not question:
        raise HTTPException(400, "Question cannot be empty")
    try:
        result = flashcards.maybe_create_from_chat(question, subject)
        if result is None:
            result = rag.ask(question, subject, k=7)
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Ask workflow failed")
        raise HTTPException(503, "The local AI could not answer right now. Check LM Studio and try again")
    # Persist the pair only after an answer succeeds, avoiding orphaned user
    # turns when the local model or retrieval service is temporarily unavailable.
    db.add_chat_turn(role="user", content=question)
    db.add_chat_turn(
        role="assistant",
        content=result["answer"],
        sources=result.get("sources"),
        videos=result.get("videos"),
        images=result.get("images"),
    )
    return result


@app.post("/api/ask")
def ask_question(req: AskRequest):
    return _answer_question(req.question, req.subject)


@app.post("/api/ask/audio")
async def ask_audio(audio: UploadFile = File(...), subject: str = Form(default="")):
    """Transcribe a short spoken question, then run the normal ask workflow."""
    filename = Path(audio.filename or "question.webm").name
    content_type = (audio.content_type or "").lower()
    if not content_type.startswith("audio/"):
        raise HTTPException(415, "Record or upload an audio question")

    suffix = Path(filename).suffix.lower() or ".webm"
    temporary = Path(tempfile.NamedTemporaryFile(suffix=suffix, delete=False).name)
    size = 0
    try:
        with temporary.open("wb") as output:
            while block := await audio.read(1024 * 1024):
                size += len(block)
                if size > 25 * 1024 * 1024:
                    raise HTTPException(413, "Voice question is larger than 25 MB")
                output.write(block)
        if size == 0:
            raise HTTPException(400, "Voice question is empty")

        from core.stt import transcribe_media
        try:
            segments = await run_in_threadpool(transcribe_media, str(temporary))
        except FileNotFoundError:
            raise HTTPException(503, "ffmpeg is required for voice questions")
        except Exception:
            logging.getLogger(__name__).exception("Voice question transcription failed")
            raise HTTPException(422, "The voice question could not be transcribed")
        transcript = " ".join(segment["text"].strip() for segment in segments if segment.get("text")).strip()
        if not transcript:
            raise HTTPException(422, "No speech was detected. Please try again closer to the microphone")
        result = await run_in_threadpool(_answer_question, transcript, subject.strip() or None)
        return {**result, "transcript": transcript}
    finally:
        await audio.close()
        temporary.unlink(missing_ok=True)


@app.get("/api/chat")
def chat_history(limit: int = 200):
    return db.list_chat_turns(max(1, min(limit, 1000)))


@app.delete("/api/chat")
def clear_chat_history():
    db.clear_chat_turns()
    return {"ok": True}


@app.get("/api/video/items/{item_id}/frames")
def list_video_frames(item_id: int):
    return db.list_video_frames(item_id)



@app.get("/api/video/frames/{frame_id}/segments")
def list_video_segments(frame_id: int):
    return db.list_video_segments(frame_id)


def _video_frame_payload(frame: dict) -> dict:
    frame["image_url"] = f"/api/video/frames/{frame['id']}/image"
    frame["video_url"] = f"/api/video/items/{frame['item_id']}/file"
    return frame


@app.get("/api/video/frames")
def video_frames(item_id: int | None = None):
    return [_video_frame_payload(frame) for frame in db.list_video_frames(item_id)]


@app.get("/api/video/frames/{frame_id}")
def video_frame(frame_id: int):
    frame = db.get_video_frame(frame_id)
    if not frame:
        raise HTTPException(404, "Video frame not found")
    frame["segments"] = db.list_video_segments(frame_id)
    for segment in frame["segments"]:
        segment["crop_url"] = f"/api/video/segments/{segment['id']}/image"
    return _video_frame_payload(frame)


@app.get("/api/video/frames/{frame_id}/image")
def video_frame_image(frame_id: int):
    frame = db.get_video_frame(frame_id)
    if not frame or not Path(frame["frame_path"]).exists():
        raise HTTPException(404, "Video frame image not found")
    return FileResponse(frame["frame_path"], media_type="image/jpeg")


@app.get("/api/video/items/{item_id}/file")
def video_file(item_id: int):
    with db.conn() as c:
        row = c.execute("SELECT stored_path, kind FROM items WHERE id=?", (item_id,)).fetchone()
    if not row or row["kind"] != "video" or not Path(row["stored_path"]).exists():
        raise HTTPException(404, "Video not found")
    return FileResponse(row["stored_path"])


@app.get("/api/doc/figures/{name}")
def doc_figure_image(name: str):
    path = (FIGURES_DIR / Path(name).name).resolve()
    if path.parent != FIGURES_DIR.resolve() or not path.exists():
        raise HTTPException(404, "Figure not found")
    return FileResponse(path, media_type="image/png")


@app.get("/api/items/{item_id}/file")
def item_file(item_id: int):
    """Serve the original uploaded source for jump-to-source (non-video kinds)."""
    with db.conn() as c:
        row = c.execute("SELECT stored_path, kind FROM items WHERE id=?", (item_id,)).fetchone()
    if not row or row["kind"] not in ("pdf", "image", "text") or not Path(row["stored_path"]).exists():
        raise HTTPException(404, "Source file not found")
    return FileResponse(row["stored_path"])


@app.get("/api/chunks/{chunk_id}/image")
def chunk_image(chunk_id: int):
    with db.conn() as c:
        row = c.execute("SELECT image_path FROM chunks WHERE id=?", (chunk_id,)).fetchone()
    if not row or not row["image_path"] or not Path(row["image_path"]).exists():
        raise HTTPException(404, "image not found")
    return FileResponse(row["image_path"])


@app.get("/api/video/segments/{segment_id}/image")
def video_segment_image(segment_id: int):
    with db.conn() as c:
        row = c.execute("SELECT crop_path FROM video_ocr_segments WHERE id=?", (segment_id,)).fetchone()
    if not row or not Path(row["crop_path"]).exists():
        raise HTTPException(404, "Video segment image not found")
    return FileResponse(row["crop_path"], media_type="image/png")


@app.get("/api/video/frames/{frame_id}/ocr-stream")
def video_ocr_stream(frame_id: int):
    """SSE: one small board crop result per event, never one final batch."""
    def events():
        try:
            from core.video import prepare_segments, run_segment_ocr
            segments = prepare_segments(frame_id)
            for segment in segments:
                if segment["status"] == "done":
                    result = segment
                else:
                    result = run_segment_ocr(segment)
                result = dict(result)
                result["crop_url"] = f"/api/video/segments/{result['id']}/image"
                yield f"event: segment\ndata: {json.dumps(result)}\n\n"
            yield "event: complete\ndata: {}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)[:400]})}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/api/video/frames/{frame_id}/verify")
def verify_video_frame(frame_id: int):
    from core import vectorstore
    from core.video import consolidate_frame
    result = consolidate_frame(frame_id)
    frame = result["frame"]
    chunk_id = db.add_chunk(frame["item_id"], result["markdown"], f"{frame['title'] or frame['filename']} — verified board",
                            ts_start=frame["timestamp"], image_path=frame["frame_path"])
    vectorstore.add_chunks([{
        "chunk_id": chunk_id, "item_id": frame["item_id"], "subject": frame["subject"] or "General",
        "source_label": f"{frame['title'] or frame['filename']} — verified board",
        "text": result["markdown"], "ts_start": frame["timestamp"], "image_path": frame["frame_path"],
    }])
    _add_frame_to_note(frame, result["markdown"])
    return {"markdown": result["markdown"], "frame": _video_frame_payload(frame)}


def _add_frame_to_note(frame: dict, markdown: str) -> None:
    """Insert a verified board frame inline into the item's note at its timestamp."""
    existing = db.notes_for_item(frame["item_id"])
    if not existing:
        return
    latest = existing[-1]
    url = f"/api/video/frames/{frame['id']}/image"
    if url in latest["markdown"]:
        return  # already present — adding a frame twice is a no-op
    caption = (markdown.splitlines() or ["Lecture visual"])[0].lstrip("# ").strip()[:120]
    visual = {"token_id": -1, "url": url, "caption": caption or "Lecture visual",
              "anchor": ("ts", int(frame["timestamp"]))}
    updated = notes_module.place_visuals(latest["markdown"], [visual])
    source = f"{frame['title'] or frame['filename']} — board"
    notes_module.update_note_markdown(
        latest["id"], frame["item_id"], updated, source, frame["subject"] or "General",
    )


@app.delete("/api/video/frames/{frame_id}")
def delete_video_frame(frame_id: int):
    if not db.delete_video_frame(frame_id):
        raise HTTPException(404, "Frame not found")
    return {"ok": True}


@app.get("/api/flashcards")
def flashcard_decks():
    return db.list_flashcard_decks()


@app.get("/api/flashcards/{deck_id}")
def flashcard_deck(deck_id: int):
    deck = db.get_flashcard_deck(deck_id)
    if deck is None:
        raise HTTPException(404, "Flashcard deck not found")
    return deck


@app.delete("/api/flashcards/{deck_id}")
def remove_flashcard_deck(deck_id: int):
    if not db.delete_flashcard_deck(deck_id):
        raise HTTPException(404, "Flashcard deck not found")
    return {"ok": True}


class QuestionPaperRequest(BaseModel):
    note_ids: list[int]
    title: str = ""
    difficulty: str = "medium"
    duration_minutes: int = 60
    mcq_count: int = 10
    short_count: int = 5
    long_count: int = 2


@app.get("/api/question-papers")
def list_question_papers():
    return db.list_question_papers()


@app.post("/api/question-papers")
def create_question_paper(request: QuestionPaperRequest):
    paper_request = question_papers.PaperRequest(
        note_ids=request.note_ids,
        title=request.title,
        difficulty=request.difficulty.strip().casefold(),
        duration_minutes=request.duration_minutes,
        mcq_count=request.mcq_count,
        short_count=request.short_count,
        long_count=request.long_count,
    )
    try:
        question_papers.validate_request(paper_request)
        llm.require_available()
    except llm.LocalLLMUnavailable as error:
        raise HTTPException(503, str(error))
    except ValueError as error:
        raise HTTPException(400, str(error))
    job_id = db.add_question_paper_job(request.model_dump())

    def run():
        try:
            paper = question_papers.generate(paper_request)
            db.finish_question_paper_job(job_id, paper_id=paper["id"])
        except Exception as error:
            logger.exception(
                "question paper generation job failed", extra={"job_id": job_id}
            )
            detail = str(error).strip() or type(error).__name__
            db.finish_question_paper_job(job_id, error=detail[:1000])

    threading.Thread(
        target=run, daemon=True, name=f"question-paper-{job_id}",
    ).start()
    return {"job_id": job_id, "status": "processing"}


@app.get("/api/question-papers/jobs")
def question_paper_jobs():
    return db.list_question_paper_jobs()


@app.get("/api/question-papers/{paper_id}")
def get_question_paper(paper_id: int):
    paper = db.get_question_paper(paper_id)
    if paper is None:
        raise HTTPException(404, "Question paper not found")
    return paper


@app.get("/api/question-papers/{paper_id}/download")
def download_question_paper(paper_id: int, answers: bool = False):
    paper = db.get_question_paper(paper_id)
    if paper is None:
        raise HTTPException(404, "Question paper not found")
    suffix = "-answer-key" if answers else ""
    filename = re.sub(r"[^a-zA-Z0-9_-]+", "-", paper["title"]).strip("-") or "question-paper"
    return Response(
        question_papers.to_pdf(paper, include_answers=answers),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}{suffix}.pdf"'
        },
    )


@app.delete("/api/question-papers/{paper_id}")
def delete_question_paper(paper_id: int):
    if not db.delete_question_paper(paper_id):
        raise HTTPException(404, "Question paper not found")
    return {"ok": True}


@app.get("/api/audiobooks/jobs")
def audiobook_jobs():
    return db.list_audiobook_jobs()


@app.get("/api/audiobooks")
def audiobooks():
    return [
        {"name": p.name, "created_at": p.stat().st_mtime, "size_mb": round(p.stat().st_size / 1e6, 1)}
        for p in sorted(AUDIOBOOKS_DIR.glob("*.wav"), key=lambda p: -p.stat().st_mtime)
    ]


@app.get("/api/audiobooks/{name}")
def audiobook_file(name: str):
    path = (AUDIOBOOKS_DIR / Path(name).name).resolve()
    if path.parent != AUDIOBOOKS_DIR.resolve() or not path.exists():
        raise HTTPException(404, "Audiobook not found")
    return FileResponse(path, media_type="audio/wav")


@app.get("/api/calendar/google/status")
def google_calendar_status():
    from core import google_calendar

    counts = db.calendar_reminder_counts()
    return {
        "configured": google_calendar.is_configured(),
        "connected": google_calendar.credentials() is not None,
        "oauth_error": google_calendar.last_oauth_error(),
        "reminders": {
            "pending": counts.get("approved", 0) + counts.get("error", 0),
            "proposed": counts.get("proposed", 0),
            "created": counts.get("created", 0),
        },
    }


@app.get("/api/calendar/google/auth-url")
def google_calendar_auth_url():
    from core import google_calendar

    try:
        return {"url": google_calendar.authorization_url()}
    except RuntimeError as error:
        raise HTTPException(503, str(error))


@app.get("/api/calendar/google/callback")
def google_calendar_callback(code: str = "", state: str = "", error: str = ""):
    from core import google_calendar

    if error or not code or not state:
        return RedirectResponse(f"{settings.web_base_url}/calendar?google=denied")
    try:
        google_calendar.complete_authorization(code, state)
    except Exception as callback_error:
        import logging
        logging.getLogger(__name__).error(
            "Google Calendar OAuth callback failed: %s", callback_error, exc_info=True
        )
        google_calendar.record_oauth_error(callback_error)
        return RedirectResponse(f"{settings.web_base_url}/calendar?google=error")
    return RedirectResponse(f"{settings.web_base_url}/calendar?google=connected")


@app.get("/api/calendar/google/events")
def google_calendar_events(time_min: str, time_max: str):
    from core import google_calendar

    try:
        start = datetime.fromisoformat(time_min.replace("Z", "+00:00"))
        end = datetime.fromisoformat(time_max.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "Calendar range must use ISO date-time values")
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise HTTPException(400, "Calendar range is invalid")
    try:
        return google_calendar.list_events(time_min, time_max)
    except PermissionError as error:
        raise HTTPException(401, str(error))
    except Exception:
        raise HTTPException(502, "Google Calendar could not be reached")


@app.delete("/api/calendar/google")
def google_calendar_disconnect():
    from core import google_calendar

    google_calendar.disconnect()
    return {"ok": True}


@app.post("/api/calendar/google/sync")
def google_calendar_sync():
    from core import google_calendar

    if not google_calendar.credentials():
        raise HTTPException(401, "Google Calendar is not connected")
    return google_calendar.sync_pending_reminders()


@app.get("/api/calendar/proposals")
def calendar_proposals():
    return db.list_calendar_proposals()


@app.post("/api/calendar/proposals/{reminder_id}/approve")
def approve_calendar_proposal(reminder_id: int):
    from core import google_calendar

    if not google_calendar.credentials():
        raise HTTPException(401, "Google Calendar is not connected")
    if not db.set_calendar_reminder_status(reminder_id, "approved"):
        raise HTTPException(404, "Calendar proposal not found")
    result = google_calendar.sync_pending_reminders()
    return {"ok": True, **result}


@app.post("/api/calendar/proposals/{reminder_id}/dismiss")
def dismiss_calendar_proposal(reminder_id: int):
    if not db.set_calendar_reminder_status(reminder_id, "dismissed"):
        raise HTTPException(404, "Calendar proposal not found")
    return {"ok": True}


@app.post("/api/calendar/proposals/{reminder_id}/plan")
def plan_calendar_proposal(reminder_id: int):
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    from core import calendar_planner, google_calendar
    from core.config import GOOGLE_CALENDAR_TIMEZONE

    if not google_calendar.credentials():
        raise HTTPException(401, "Google Calendar is not connected")
    reminder = db.get_calendar_reminder(reminder_id)
    if not reminder or reminder["status"] != "proposed":
        raise HTTPException(404, "Calendar proposal not found")
    zone = ZoneInfo(GOOGLE_CALENDAR_TIMEZONE)
    event_day = datetime.fromisoformat(reminder["event_date"]).date()
    start = datetime.combine(event_day, datetime.min.time(), zone)
    end = start + timedelta(days=8)
    try:
        events = google_calendar.list_events(start.isoformat(), end.isoformat())
        plan = calendar_planner.build_plan(reminder, events)
    except Exception as error:
        logger.exception("calendar planning failed", extra={"reminder_id": reminder_id})
        raise HTTPException(502, f"Could not prepare a calendar plan: {str(error)[:160]}")
    plan_id = db.add_reschedule_plan(reminder_id, plan)
    return {"id": plan_id, "status": "proposed", **plan}


@app.get("/api/calendar/plans/{plan_id}")
def calendar_plan(plan_id: int):
    stored = db.get_reschedule_plan(plan_id)
    if not stored:
        raise HTTPException(404, "Calendar plan not found")
    plan = stored.pop("plan")
    return {**stored, **plan}


@app.post("/api/calendar/plans/{plan_id}/apply")
def apply_calendar_plan(plan_id: int):
    from core import google_calendar

    stored = db.get_reschedule_plan(plan_id)
    if not stored or stored["status"] != "proposed":
        raise HTTPException(404, "Active calendar plan not found")
    plan = stored["plan"]
    if plan.get("blocked"):
        raise HTTPException(
            409,
            "This plan has fixed conflicts. Move or cancel them in Google Calendar, then re-plan.",
        )
    reminder = db.get_calendar_reminder(stored["reminder_id"])
    if not reminder or reminder["status"] != "proposed":
        raise HTTPException(409, "The source event is no longer pending")
    try:
        event_id = google_calendar.apply_reschedule_plan(plan, reminder)
        db.set_calendar_reminder_result(reminder["id"], event_id)
        db.set_reschedule_plan_status(plan_id, "applied")
    except PermissionError as error:
        raise HTTPException(401, str(error))
    except Exception as error:
        db.set_reschedule_plan_status(plan_id, "error", str(error)[:500])
        raise HTTPException(409, str(error)[:200])
    return {"ok": True, "google_event_id": event_id, "moved": len(plan.get("moves", []))}


@app.post("/api/calendar/plans/{plan_id}/dismiss")
def dismiss_calendar_plan(plan_id: int):
    if not db.set_reschedule_plan_status(plan_id, "dismissed"):
        raise HTTPException(404, "Calendar plan not found")
    return {"ok": True}


class AudiobookRequest(BaseModel):
    note_ids: list[int]
    name: str


@app.post("/api/audiobooks")
def make_audiobook(req: AudiobookRequest):
    name = " ".join(req.name.split())
    if not req.note_ids:
        raise HTTPException(400, "Select at least one note")
    if not name:
        raise HTTPException(400, "Audiobook name is required")
    if len(name) > 100:
        raise HTTPException(400, "Audiobook name must be 100 characters or fewer")
    note_ids = list(dict.fromkeys(req.note_ids))
    with db.conn() as c:
        rows = c.execute(
            f"SELECT markdown FROM notes WHERE id IN ({','.join('?' * len(note_ids))})",
            note_ids,
        ).fetchall()
    combined = "\n\n".join(r["markdown"] for r in rows)
    if not combined.strip():
        raise HTTPException(404, "None of the selected notes exist")
    job_id = db.add_audiobook_job(name)

    def run():
        try:
            from core.audiobook import generate
            path = generate(combined, name)
            db.finish_audiobook_job(job_id, path.name)
        except Exception as e:
            logger.exception("audiobook generation failed", extra={"job_id": job_id})
            db.finish_audiobook_job(job_id, None, str(e)[:500])

    threading.Thread(target=run, daemon=True, name=f"audiobook-{job_id}").start()
    return {"job_id": job_id, "status": "processing"}


class TaskCreate(BaseModel):
    label: str
    due: str | None = None
    add_to_calendar: bool = False


class TaskPatch(BaseModel):
    done: bool


@app.get("/api/tasks")
def tasks():
    return db.list_tasks()


@app.post("/api/tasks")
def create_task(req: TaskCreate):
    label = req.label.strip()
    if not label:
        raise HTTPException(400, "Task label is required")
    if len(label) > 300:
        raise HTTPException(400, "Task label must be 300 characters or fewer")
    due = req.due.strip() if req.due else None
    event_date = None
    if req.add_to_calendar:
        if not due:
            raise HTTPException(400, "A due date is required to add a task to Google Calendar")
        event_date = event_date_from_due_text(due)
        if event_date is None:
            raise HTTPException(400, "Enter a calendar date such as 2026-08-20, August 20, today, or tomorrow")
    task_id = db.add_task(label, due)
    result = {"id": task_id, "calendar_added": False}
    if req.add_to_calendar:
        from core import google_calendar
        try:
            event_id = google_calendar.create_task_event({"id": task_id, "label": label}, event_date)
        except PermissionError as error:
            db.delete_task(task_id)
            raise HTTPException(401, str(error))
        except Exception:
            db.delete_task(task_id)
            raise HTTPException(502, "Google Calendar could not create the task event")
        db.set_task_google_event(task_id, event_id)
        result["calendar_added"] = True
    return result


@app.patch("/api/tasks/{task_id}")
def patch_task(task_id: int, req: TaskPatch):
    if not db.set_task_done(task_id, req.done):
        raise HTTPException(404, "Task not found")
    return {"ok": True}


@app.delete("/api/tasks/{task_id}")
def remove_task(task_id: int):
    if not db.delete_task(task_id):
        raise HTTPException(404, "Task not found")
    return {"ok": True}


@app.post("/api/handwriting/upload")
async def handwriting_upload(files: list[UploadFile]):
    if not files:
        raise HTTPException(400, "Add at least one handwriting image")
    page_ids = []
    for f in files:
        filename = Path(f.filename or "handwriting.png").name
        if kind_of(Path(filename)) != "image":
            await f.close()
            raise HTTPException(415, f"Handwriting input must be an image: {filename}")
        destination = HW_PAGES_DIR / f"page_{int(time.time()*1000)}_{uuid.uuid4().hex}_{filename}"
        partial = destination.with_suffix(destination.suffix + ".part")
        size = 0
        try:
            with partial.open("wb") as output:
                while block := await f.read(1024 * 1024):
                    size += len(block)
                    if size > settings.max_upload_mb * 1024 * 1024:
                        raise HTTPException(
                            413,
                            f"{filename} is larger than {settings.max_upload_mb} MB",
                        )
                    output.write(block)
            if size == 0:
                raise HTTPException(400, f"{filename} is empty")
            os.replace(partial, destination)
        except Exception:
            partial.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise
        finally:
            await f.close()
        page_id = db.add_hw_page(filename, str(destination))
        page_ids.append(page_id)

        def run(pid=page_id):
            try:
                from core.handwriting import process_page
                process_page(pid)
            except Exception:
                logger.exception(
                    "handwriting processing failed", extra={"page_id": pid}
                )

        threading.Thread(target=run, daemon=True, name=f"hw-page-{page_id}").start()
    return {"page_ids": page_ids}


@app.get("/api/handwriting/pages")
def handwriting_pages():
    return db.list_hw_pages()


@app.get("/api/handwriting/pages/{page_id}")
def handwriting_page(page_id: int):
    page = db.get_hw_page(page_id)
    if not page:
        raise HTTPException(404, "Handwriting page not found")
    lines = db.list_hw_lines(page_id)
    for ln in lines:
        ln["crop_url"] = f"/api/handwriting/crops/{Path(ln['crop_path']).name}"
    page["lines"] = lines
    return page


@app.get("/api/handwriting/crops/{name}")
def handwriting_crop(name: str):
    path = (HW_CROPS_DIR / Path(name).name).resolve()
    if path.parent != HW_CROPS_DIR.resolve() or not path.exists():
        raise HTTPException(404, "Handwriting crop not found")
    return FileResponse(path, media_type="image/png")


@app.get("/api/handwriting/pageimage/{page_id}")
def handwriting_page_image(page_id: int):
    page = db.get_hw_page(page_id)
    if not page or not Path(page["image_path"]).exists():
        raise HTTPException(404, "Handwriting page image not found")
    return FileResponse(page["image_path"])


class LineCorrection(BaseModel):
    corrected_text: str | None


@app.patch("/api/handwriting/lines/{line_id}")
def correct_line(line_id: int, req: LineCorrection):
    text = req.corrected_text.strip() if req.corrected_text else None
    if not db.set_hw_correction(line_id, text or None):
        raise HTTPException(404, "Handwriting line not found")
    return {"ok": True}


@app.post("/api/handwriting/pages/{page_id}/to-notes")
def handwriting_to_notes(page_id: int):
    """Drop the page's text into the inbox so the normal pipeline makes notes."""
    page = db.get_hw_page(page_id)
    if not page:
        raise HTTPException(404, "Handwriting page not found")
    lines = db.list_hw_lines(page_id)
    text = "\n".join((ln["corrected_text"] or ln["pred_text"]) for ln in lines).strip()
    if not text:
        raise HTTPException(409, "Handwriting page has no recognized text yet")
    stem = Path(page["filename"]).stem or "handwriting"
    (INBOX_DIR / f"handwritten_{stem}_{page_id}.txt").write_text(
        text, encoding="utf-8"
    )
    return {"ok": True}


@app.get("/api/handwriting/status")
def handwriting_status():
    return {"corrected_lines": len(db.hw_corrected_lines())}


@app.get("/api/activity")
def activity(limit: int = 10):
    limit = max(1, min(limit, 100))
    with db.conn() as c:
        items_rows = c.execute(
            "SELECT filename, kind, status, created_at, title FROM items "
            "ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        notes_rows = c.execute(
            "SELECT notes.created_at, items.title FROM notes "
            "JOIN items ON items.id = notes.item_id "
            "ORDER BY notes.created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    events = [
        {"type": "file", "label": f"File added: {r['filename']}", "at": r["created_at"]}
        for r in items_rows
    ] + [
        {"type": "note", "label": f"Note created: {r['title'] or 'Untitled'}", "at": r["created_at"]}
        for r in notes_rows
    ]
    return sorted(events, key=lambda e: -e["at"])[:limit]


# ── Adaptive learning path ────────────────────────────────────────────────
# Goal → concept graph → diagnostic → gaps → session → mastery → revision.

class GoalCreate(BaseModel):
    name: str


class SessionCreate(BaseModel):
    concept_id: int | None = None


class AttemptCreate(BaseModel):
    question_id: int
    chosen_index: int
    session_id: int | None = None
    latency_ms: int = 0


class ReadDone(BaseModel):
    item_id: int


class ConceptAsk(BaseModel):
    concept_id: int
    question: str


def _require_goal() -> dict:
    goal = concepts.current_goal()
    if goal is None:
        raise HTTPException(404, "No exam goal set yet")
    return goal


def _require_ready_goal() -> dict:
    goal = _require_goal()
    if goal["status"] != "ready":
        raise HTTPException(409, f"The concept graph is {goal['status']}")
    return goal


@app.get("/api/learn/goal")
def learn_goal():
    goal = concepts.current_goal()
    if goal is None:
        return {"goal": None, "summary": None}
    payload = {"goal": goal, "summary": None, "llm_available": llm.is_available()}
    if goal["status"] == "ready":
        payload["summary"] = gaps.summary(goal["id"])
        payload["sessions"] = planner.recent(goal["id"], limit=5)
    return payload


@app.post("/api/learn/goal")
async def create_learn_goal(req: GoalCreate):
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "An exam or subject name is required")
    if not llm.is_available():
        raise HTTPException(503, "The local LLM is unavailable, so the concept graph cannot be built")
    existing = concepts.current_goal()
    if existing is not None:
        await run_in_threadpool(concepts.delete_goal, existing["id"])
    try:
        return {"goal": concepts.create_goal(name)}
    except ValueError as error:
        raise HTTPException(400, str(error))


@app.delete("/api/learn/goal")
async def delete_learn_goal():
    goal = _require_goal()
    await run_in_threadpool(concepts.delete_goal, goal["id"])
    return {"ok": True}


@app.get("/api/learn/graph")
async def learn_graph():
    goal = _require_ready_goal()
    return await run_in_threadpool(concepts.graph, goal["id"])


@app.get("/api/learn/gaps")
async def learn_gaps():
    goal = _require_ready_goal()
    ranked = await run_in_threadpool(gaps.rank, goal["id"])
    return {"gaps": ranked, "summary": gaps.summary(goal["id"])}


@app.post("/api/learn/diagnostic")
async def learn_diagnostic():
    goal = _require_ready_goal()
    try:
        session_id = await run_in_threadpool(planner.start_diagnostic, goal["id"])
    except ValueError as error:
        raise HTTPException(400, str(error))
    return {"session_id": session_id}


@app.post("/api/learn/session")
async def learn_session(req: SessionCreate):
    goal = _require_ready_goal()
    try:
        session_id = await run_in_threadpool(
            planner.start_session, goal["id"], req.concept_id
        )
    except ValueError as error:
        raise HTTPException(400, str(error))
    return {"session_id": session_id}


@app.get("/api/learn/session/{session_id}")
def learn_session_state(session_id: int):
    state = planner.state(session_id)
    if state is None:
        raise HTTPException(404, "Session not found")
    return state


@app.get("/api/learn/session/{session_id}/next")
async def learn_session_next(session_id: int):
    try:
        item = await run_in_threadpool(planner.next_item, session_id)
    except ValueError as error:
        raise HTTPException(404, str(error))
    if item is None:
        return {"done": True, "session": planner.state(session_id)}
    return {"done": False, "item": item}


@app.post("/api/learn/session/{session_id}/read")
def learn_session_read(session_id: int, req: ReadDone):
    planner.mark_read(req.item_id)
    return {"ok": True}


@app.post("/api/learn/attempt")
async def learn_attempt(req: AttemptCreate):
    try:
        return await run_in_threadpool(
            quiz.grade, req.question_id, req.chosen_index, req.session_id, req.latency_ms
        )
    except ValueError as error:
        raise HTTPException(404, str(error))


@app.get("/api/learn/review")
async def learn_review():
    goal = _require_ready_goal()
    queue = await run_in_threadpool(mastery.due_queue, goal["id"])
    return {
        "queue": queue,
        "due": [row for row in queue if row["due"]],
        "threshold": mastery.RECALL_DUE_THRESHOLD,
    }


@app.get("/api/learn/history")
async def learn_history():
    goal = _require_ready_goal()
    points = await run_in_threadpool(mastery.history, goal["id"])
    return {"points": points}


@app.get("/api/learn/report/weekly")
async def learn_report():
    goal = _require_ready_goal()
    return await run_in_threadpool(report.weekly, goal["id"])


@app.post("/api/learn/ask")
async def learn_ask(req: ConceptAsk):
    question = req.question.strip()
    if not question:
        raise HTTPException(400, "A question is required")
    concept = concepts.get_concept(req.concept_id)
    if concept is None:
        raise HTTPException(404, "Concept not found")
    chunks = concepts.source_chunks(req.concept_id, limit=8)
    try:
        result = await run_in_threadpool(
            rag.answer_from_hits,
            f"In the context of {concept['name']}: {question}",
            chunks,
        )
    except llm.LocalLLMUnavailable as error:
        raise HTTPException(503, str(error))
    return result


# Route domains are reflected in OpenAPI so both web and mobile can generate
# clear client surfaces from the same contract.
_ROUTE_TAGS = (
    ("/api/health", "system"),
    ("/api/stats", "system"),
    ("/api/activity", "system"),
    ("/api/notes", "notes"),
    ("/api/ask", "chat"),
    ("/api/chat", "chat"),
    ("/api/video", "video"),
    ("/api/flashcards", "flashcards"),
    ("/api/question-papers", "question-papers"),
    ("/api/audiobooks", "audiobooks"),
    ("/api/calendar", "calendar"),
    ("/api/tasks", "tasks"),
    ("/api/handwriting", "handwriting"),
    ("/api/learn", "learn"),
    ("/api/subjects", "library"),
    ("/api/items", "library"),
    ("/api/upload", "library"),
    ("/api/chunks", "library"),
    ("/api/doc", "library"),
)
for _route in app.routes:
    if not isinstance(_route, APIRoute) or _route.tags:
        continue
    _route.tags = [
        tag for prefix, tag in _ROUTE_TAGS if _route.path.startswith(prefix)
    ] or ["system"]
