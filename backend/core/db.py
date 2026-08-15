"""SQLite metadata store: items, subjects, notes, chunks."""
import logging
import sqlite3
import time
import json
from contextlib import contextmanager
from pathlib import Path

from core.config import DB_PATH

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    title TEXT,
    subject_id INTEGER REFERENCES subjects(id),
    metadata_text TEXT,
    capture_date TEXT,
    created_at REAL NOT NULL,
    processed_at REAL
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    markdown TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS audiobook_jobs (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    error TEXT,
    file TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    due TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    google_event_id TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS hw_pages (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    image_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    error TEXT,
    item_id INTEGER REFERENCES items(id),
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS hw_lines (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES hw_pages(id),
    line_index INTEGER NOT NULL,
    bbox TEXT,
    crop_path TEXT NOT NULL,
    pred_text TEXT NOT NULL DEFAULT '',
    corrected_text TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    text TEXT NOT NULL,
    source_label TEXT NOT NULL,
    ts_start REAL,
    page INTEGER,
    image_path TEXT
);
CREATE TABLE IF NOT EXISTS video_frames (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    timestamp REAL NOT NULL,
    frame_path TEXT NOT NULL,
    stability REAL NOT NULL DEFAULT 0,
    sharpness REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'awaiting_review',
    consolidated_text TEXT,
    formatted_markdown TEXT,
    created_at REAL NOT NULL,
    reviewed_at REAL
);
CREATE TABLE IF NOT EXISTS doc_figures (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    page INTEGER,
    caption TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS video_ocr_segments (
    id INTEGER PRIMARY KEY,
    frame_id INTEGER NOT NULL REFERENCES video_frames(id),
    segment_index INTEGER NOT NULL,
    bbox TEXT NOT NULL,
    crop_path TEXT NOT NULL,
    raw_text TEXT NOT NULL DEFAULT '',
    table_markdown TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    UNIQUE(frame_id, segment_index)
);
CREATE TABLE IF NOT EXISTS calendar_reminders (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    title TEXT NOT NULL,
    event_date TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    all_day INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'proposed',
    google_event_id TEXT,
    error TEXT,
    created_at REAL NOT NULL,
    UNIQUE(item_id, title, event_date, start_time)
);
CREATE TABLE IF NOT EXISTS calendar_reschedule_plans (
    id INTEGER PRIMARY KEY,
    reminder_id INTEGER NOT NULL REFERENCES calendar_reminders(id),
    status TEXT NOT NULL DEFAULT 'proposed',
    plan_json TEXT NOT NULL,
    error TEXT,
    created_at REAL NOT NULL,
    applied_at REAL
);
CREATE TABLE IF NOT EXISTS chat_turns (
    id INTEGER PRIMARY KEY,
    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
    content TEXT NOT NULL,
    sources_json TEXT NOT NULL DEFAULT '[]',
    videos_json TEXT NOT NULL DEFAULT '[]',
    images_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS flashcard_decks (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    topic TEXT NOT NULL,
    subject TEXT,
    sources_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS flashcards (
    id INTEGER PRIMARY KEY,
    deck_id INTEGER NOT NULL REFERENCES flashcard_decks(id),
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    position INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_flashcards_deck_position
    ON flashcards(deck_id, position);
CREATE TABLE IF NOT EXISTS question_papers (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    total_marks INTEGER NOT NULL,
    instructions TEXT NOT NULL,
    sources_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS question_paper_questions (
    id INTEGER PRIMARY KEY,
    paper_id INTEGER NOT NULL REFERENCES question_papers(id) ON DELETE CASCADE,
    question_type TEXT NOT NULL,
    prompt TEXT NOT NULL,
    options_json TEXT NOT NULL DEFAULT '[]',
    answer TEXT NOT NULL,
    explanation TEXT NOT NULL DEFAULT '',
    marks INTEGER NOT NULL,
    position INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_question_paper_questions_position
    ON question_paper_questions(paper_id, position);
CREATE TABLE IF NOT EXISTS question_paper_jobs (
    id INTEGER PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'processing',
    request_json TEXT NOT NULL,
    paper_id INTEGER REFERENCES question_papers(id),
    error TEXT,
    created_at REAL NOT NULL,
    finished_at REAL
);

-- ── Adaptive learning path ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS exam_goals (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'building',
    error TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS concepts (
    id INTEGER PRIMARY KEY,
    goal_id INTEGER NOT NULL REFERENCES exam_goals(id),
    name TEXT NOT NULL,
    blurb TEXT NOT NULL DEFAULT '',
    tier INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_concepts_goal ON concepts(goal_id, tier, position);
CREATE TABLE IF NOT EXISTS concept_edges (
    prereq_id INTEGER NOT NULL REFERENCES concepts(id),
    concept_id INTEGER NOT NULL REFERENCES concepts(id),
    PRIMARY KEY (prereq_id, concept_id)
);
CREATE TABLE IF NOT EXISTS concept_sources (
    concept_id INTEGER NOT NULL REFERENCES concepts(id),
    chunk_id INTEGER NOT NULL REFERENCES chunks(id),
    score REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (concept_id, chunk_id)
);
CREATE TABLE IF NOT EXISTS mastery (
    concept_id INTEGER PRIMARY KEY REFERENCES concepts(id),
    p_known REAL NOT NULL DEFAULT 0.25,
    attempts INTEGER NOT NULL DEFAULT 0,
    correct INTEGER NOT NULL DEFAULT 0,
    half_life REAL NOT NULL DEFAULT 1.0,
    last_review_at REAL,
    in_srs INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mastery_history (
    id INTEGER PRIMARY KEY,
    concept_id INTEGER NOT NULL REFERENCES concepts(id),
    p_known REAL NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mastery_history_concept
    ON mastery_history(concept_id, created_at);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    concept_id INTEGER NOT NULL REFERENCES concepts(id),
    stem TEXT NOT NULL,
    options_json TEXT NOT NULL,
    answer_index INTEGER NOT NULL,
    explanation TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_questions_concept ON questions(concept_id, id);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    goal_id INTEGER NOT NULL REFERENCES exam_goals(id),
    kind TEXT NOT NULL CHECK(kind IN ('diagnostic','study','review')),
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL,
    completed_at REAL
);
CREATE TABLE IF NOT EXISTS session_items (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    position INTEGER NOT NULL,
    concept_id INTEGER NOT NULL REFERENCES concepts(id),
    question_id INTEGER REFERENCES questions(id),
    kind TEXT NOT NULL CHECK(kind IN ('read','quiz')),
    done INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_session_items_session
    ON session_items(session_id, position);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id),
    question_id INTEGER NOT NULL REFERENCES questions(id),
    concept_id INTEGER NOT NULL REFERENCES concepts(id),
    chosen_index INTEGER NOT NULL,
    correct INTEGER NOT NULL,
    misconception TEXT,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_concept ON attempts(concept_id, created_at);
"""


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=30000")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init_db():
    with conn() as c:
        # WAL permits API reads while the ingestion worker is writing.
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.executescript(SCHEMA)
        try:  # migration for hw_pages created before the ingest integration
            c.execute("ALTER TABLE hw_pages ADD COLUMN item_id INTEGER REFERENCES items(id)")
        except sqlite3.OperationalError:
            pass
        columns = {row["name"] for row in c.execute("PRAGMA table_info(items)").fetchall()}
        if "metadata_text" not in columns:
            c.execute("ALTER TABLE items ADD COLUMN metadata_text TEXT")
        if "capture_date" not in columns:
            c.execute("ALTER TABLE items ADD COLUMN capture_date TEXT")
        task_columns = {row["name"] for row in c.execute("PRAGMA table_info(tasks)").fetchall()}
        if "google_event_id" not in task_columns:
            c.execute("ALTER TABLE tasks ADD COLUMN google_event_id TEXT")
        # Chat turns gained media so "Play from timestamp" / image results survive reloads.
        chat_columns = {row["name"] for row in c.execute("PRAGMA table_info(chat_turns)").fetchall()}
        if "videos_json" not in chat_columns:
            c.execute("ALTER TABLE chat_turns ADD COLUMN videos_json TEXT NOT NULL DEFAULT '[]'")
        if "images_json" not in chat_columns:
            c.execute("ALTER TABLE chat_turns ADD COLUMN images_json TEXT NOT NULL DEFAULT '[]'")
        # Older versions queued extracted events automatically. Make any
        # unsynced legacy entries explicitly reviewable instead.
        c.execute("UPDATE calendar_reminders SET status='proposed' WHERE status='pending'")
    logger.info("database ready", extra={"path": str(DB_PATH)})


def add_item(filename: str, stored_path: str, kind: str,
             metadata_text: str | None = None, capture_date: str | None = None) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO items "
            "(filename, stored_path, kind, metadata_text, capture_date, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (filename, stored_path, kind, metadata_text, capture_date, time.time()),
        )
        return cur.lastrowid


def get_item(item_id: int):
    with conn() as c:
        row = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        return dict(row) if row else None


def set_status(item_id: int, status: str, error: str | None = None):
    with conn() as c:
        c.execute(
            "UPDATE items SET status=?, error=?, processed_at=? WHERE id=?",
            (status, error, time.time() if status in ("done", "error") else None, item_id),
        )


def retry_item(item_id: int) -> None:
    with conn() as c:
        c.execute(
            "UPDATE items SET status='pending', error=NULL, processed_at=NULL WHERE id=?",
            (item_id,),
        )


def index_rows_for_item(item_id: int) -> list[dict]:
    """Return persisted SQLite chunks in the shape expected by LanceDB."""
    with conn() as c:
        rows = c.execute(
            "SELECT chunks.id AS chunk_id, chunks.item_id, "
            "COALESCE(subjects.name, 'General') AS subject, "
            "chunks.source_label, chunks.text, chunks.ts_start, chunks.page, "
            "chunks.image_path "
            "FROM chunks JOIN items ON items.id=chunks.item_id "
            "LEFT JOIN subjects ON subjects.id=items.subject_id "
            "WHERE chunks.item_id=? ORDER BY chunks.id",
            (item_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def set_item_meta(item_id: int, title: str, subject_id: int):
    with conn() as c:
        c.execute("UPDATE items SET title=?, subject_id=? WHERE id=?", (title, subject_id, item_id))


def get_or_create_subject(name: str) -> int:
    name = name.strip() or "General"
    with conn() as c:
        row = c.execute("SELECT id FROM subjects WHERE name=?", (name,)).fetchone()
        if row:
            return row["id"]
        return c.execute(
            "INSERT INTO subjects (name, created_at) VALUES (?,?)", (name, time.time())
        ).lastrowid


def list_subjects():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM subjects ORDER BY name").fetchall()]


def list_items(subject_id: int | None = None):
    q = "SELECT items.*, subjects.name AS subject FROM items LEFT JOIN subjects ON subjects.id = items.subject_id"
    args: tuple = ()
    if subject_id is not None:
        q += " WHERE subject_id=?"
        args = (subject_id,)
    q += " ORDER BY items.created_at DESC"
    with conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def next_pending_item():
    with conn() as c:
        row = c.execute(
            "SELECT * FROM items WHERE status='pending' ORDER BY created_at LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def claim_next_pending_item():
    """Atomically claim one queue item across bot/server worker processes."""
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute(
            "SELECT * FROM items WHERE status='pending' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        c.execute(
            "UPDATE items SET status='processing', error=NULL, processed_at=NULL "
            "WHERE id=? AND status='pending'",
            (row["id"],),
        )
        claimed = dict(row)
        claimed["status"] = "processing"
        return claimed


def add_note(item_id: int, markdown: str) -> int:
    with conn() as c:
        return c.execute(
            "INSERT INTO notes (item_id, markdown, created_at) VALUES (?,?,?)",
            (item_id, markdown, time.time()),
        ).lastrowid


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
    """Delete an item's figure rows; return the image file paths to unlink."""
    with conn() as c:
        paths = [r["image_path"] for r in c.execute(
            "SELECT image_path FROM doc_figures WHERE item_id=?", (item_id,)).fetchall()]
        c.execute("DELETE FROM doc_figures WHERE item_id=?", (item_id,))
    return paths


def notes_for_item(item_id: int):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM notes WHERE item_id=? ORDER BY created_at", (item_id,)
        ).fetchall()]


def notes_for_subject(subject_id: int):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT notes.*, items.title FROM notes JOIN items ON items.id = notes.item_id "
            "WHERE items.subject_id=? ORDER BY notes.created_at", (subject_id,)
        ).fetchall()]


def add_audiobook_job(name: str) -> int:
    with conn() as c:
        return c.execute(
            "INSERT INTO audiobook_jobs (name, created_at) VALUES (?,?)", (name, time.time())
        ).lastrowid


def finish_audiobook_job(job_id: int, file: str | None, error: str | None = None):
    with conn() as c:
        c.execute(
            "UPDATE audiobook_jobs SET status=?, file=?, error=? WHERE id=?",
            ("error" if error else "done", file, error, job_id),
        )


def list_audiobook_jobs(limit: int = 10):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM audiobook_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()]


def list_tasks():
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM tasks ORDER BY done, created_at DESC"
        ).fetchall()]


def add_task(label: str, due: str | None) -> int:
    with conn() as c:
        return c.execute(
            "INSERT INTO tasks (label, due, created_at) VALUES (?,?,?)",
            (label, due, time.time()),
        ).lastrowid


def set_task_done(task_id: int, done: bool) -> bool:
    with conn() as c:
        return c.execute(
            "UPDATE tasks SET done=? WHERE id=?", (int(done), task_id)
        ).rowcount > 0


def delete_task(task_id: int) -> bool:
    with conn() as c:
        return c.execute("DELETE FROM tasks WHERE id=?", (task_id,)).rowcount > 0


def add_hw_page(filename: str, image_path: str, item_id: int | None = None) -> int:
    with conn() as c:
        return c.execute(
            "INSERT INTO hw_pages (filename, image_path, item_id, created_at) VALUES (?,?,?,?)",
            (filename, image_path, item_id, time.time()),
        ).lastrowid


def set_hw_page_status(page_id: int, status: str, error: str | None = None):
    with conn() as c:
        c.execute("UPDATE hw_pages SET status=?, error=? WHERE id=?", (status, error, page_id))


def list_hw_pages():
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT hw_pages.*, COUNT(hw_lines.id) AS line_count, "
            "SUM(hw_lines.corrected_text IS NOT NULL) AS corrected_count "
            "FROM hw_pages LEFT JOIN hw_lines ON hw_lines.page_id = hw_pages.id "
            "GROUP BY hw_pages.id ORDER BY hw_pages.created_at DESC"
        ).fetchall()]


def get_hw_page(page_id: int):
    with conn() as c:
        row = c.execute("SELECT * FROM hw_pages WHERE id=?", (page_id,)).fetchone()
        return dict(row) if row else None


def add_hw_line(page_id: int, line_index: int, bbox: str | None,
                crop_path: str, pred_text: str) -> int:
    with conn() as c:
        return c.execute(
            "INSERT INTO hw_lines (page_id, line_index, bbox, crop_path, pred_text, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (page_id, line_index, bbox, crop_path, pred_text, time.time()),
        ).lastrowid


def list_hw_lines(page_id: int):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM hw_lines WHERE page_id=? ORDER BY line_index", (page_id,)
        ).fetchall()]


def delete_hw_lines(page_id: int):
    import pathlib
    with conn() as c:
        for r in c.execute("SELECT crop_path FROM hw_lines WHERE page_id=?", (page_id,)).fetchall():
            pathlib.Path(r["crop_path"]).unlink(missing_ok=True)
        c.execute("DELETE FROM hw_lines WHERE page_id=?", (page_id,))


def set_hw_correction(line_id: int, corrected_text: str | None) -> bool:
    with conn() as c:
        return c.execute(
            "UPDATE hw_lines SET corrected_text=? WHERE id=?", (corrected_text, line_id)
        ).rowcount > 0


def hw_corrected_lines():
    """User-corrected lines, used as vocabulary hints for the vision model."""
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id, crop_path, corrected_text FROM hw_lines "
            "WHERE corrected_text IS NOT NULL AND TRIM(corrected_text) != '' "
            "ORDER BY created_at"
        ).fetchall()]


def add_chunk(item_id: int, text: str, source_label: str,
              ts_start: float | None = None, page: int | None = None,
              image_path: str | None = None) -> int:
    with conn() as c:
        return c.execute(
            "INSERT INTO chunks (item_id, text, source_label, ts_start, page, image_path) "
            "VALUES (?,?,?,?,?,?)",
            (item_id, text, source_label, ts_start, page, image_path),
        ).lastrowid


def add_video_frame(item_id: int, timestamp: float, frame_path: str,
                    stability: float, sharpness: float) -> int:
    with conn() as c:
        return c.execute(
            "INSERT INTO video_frames (item_id, timestamp, frame_path, stability, sharpness, created_at) "
            "VALUES (?,?,?,?,?,?)", (item_id, timestamp, frame_path, stability, sharpness, time.time())
        ).lastrowid


def list_video_frames(item_id: int | None = None):
    query = ("SELECT video_frames.*, items.title, items.filename, COUNT(video_ocr_segments.id) AS segment_count, "
             "SUM(video_ocr_segments.status = 'done') AS done_segments FROM video_frames "
             "JOIN items ON items.id = video_frames.item_id "
             "LEFT JOIN video_ocr_segments ON video_ocr_segments.frame_id = video_frames.id")
    args: tuple = ()
    if item_id is not None:
        query += " WHERE video_frames.item_id=?"
        args = (item_id,)
    query += " GROUP BY video_frames.id ORDER BY video_frames.created_at DESC, video_frames.timestamp"
    with conn() as c:
        return [dict(r) for r in c.execute(query, args).fetchall()]


def get_video_frame(frame_id: int):
    with conn() as c:
        row = c.execute("SELECT video_frames.*, items.title, items.filename, items.stored_path, subjects.name AS subject "
                        "FROM video_frames JOIN items ON items.id=video_frames.item_id "
                        "LEFT JOIN subjects ON subjects.id=items.subject_id "
                        "WHERE video_frames.id=?", (frame_id,)).fetchone()
        return dict(row) if row else None


def add_video_segment(frame_id: int, segment_index: int, bbox: str, crop_path: str) -> int:
    with conn() as c:
        cur = c.execute("INSERT OR IGNORE INTO video_ocr_segments "
                        "(frame_id, segment_index, bbox, crop_path, created_at) VALUES (?,?,?,?,?)",
                        (frame_id, segment_index, bbox, crop_path, time.time()))
        if cur.lastrowid:
            return cur.lastrowid
        return c.execute("SELECT id FROM video_ocr_segments WHERE frame_id=? AND segment_index=?",
                         (frame_id, segment_index)).fetchone()["id"]


def set_video_segment_result(segment_id: int, raw_text: str, table_markdown: str | None):
    with conn() as c:
        c.execute("UPDATE video_ocr_segments SET raw_text=?, table_markdown=?, status='done' WHERE id=?",
                  (raw_text, table_markdown, segment_id))


def list_video_segments(frame_id: int):
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM video_ocr_segments WHERE frame_id=? "
                                            "ORDER BY segment_index", (frame_id,)).fetchall()]


def set_video_frame_review(frame_id: int, text: str, markdown: str, reviewed: bool = True):
    with conn() as c:
        c.execute("UPDATE video_frames SET status=?, consolidated_text=?, formatted_markdown=?, "
                  "reviewed_at=? WHERE id=?", ("reviewed" if reviewed else "auto_processed", text,
                                                markdown, time.time() if reviewed else None, frame_id))


def delete_video_frame(frame_id: int) -> bool:
    """Remove a recommended frame plus its OCR segments and their image files."""
    with conn() as c:
        frame = c.execute("SELECT frame_path FROM video_frames WHERE id=?", (frame_id,)).fetchone()
        if frame is None:
            return False
        crops = [r["crop_path"] for r in c.execute(
            "SELECT crop_path FROM video_ocr_segments WHERE frame_id=?", (frame_id,)).fetchall()]
        c.execute("DELETE FROM video_ocr_segments WHERE frame_id=?", (frame_id,))
        c.execute("DELETE FROM video_frames WHERE id=?", (frame_id,))
    for path in [frame["frame_path"], *crops]:
        try:
            if path:
                Path(path).unlink(missing_ok=True)
        except OSError:
            pass
    return True


def add_calendar_reminder(item_id: int, title: str, event_date: str,
                          start_time: str | None, end_time: str | None,
                          description: str | None) -> int | None:
    with conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO calendar_reminders "
            "(item_id, title, event_date, start_time, end_time, all_day, description, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (item_id, title, event_date, start_time, end_time, int(not start_time),
            description, time.time()),
        )
        return cur.lastrowid or None


def set_task_google_event(task_id: int, google_event_id: str):
    with conn() as c:
        c.execute("UPDATE tasks SET google_event_id=? WHERE id=?", (google_event_id, task_id))


def list_pending_calendar_reminders():
    with conn() as c:
        return [dict(row) for row in c.execute(
            "SELECT calendar_reminders.*, items.filename FROM calendar_reminders "
            "JOIN items ON items.id = calendar_reminders.item_id "
            "WHERE calendar_reminders.status IN ('approved','error') "
            "ORDER BY calendar_reminders.event_date, calendar_reminders.start_time"
        ).fetchall()]


def list_calendar_proposals():
    with conn() as c:
        return [dict(row) for row in c.execute(
            "SELECT calendar_reminders.*, items.filename FROM calendar_reminders "
            "JOIN items ON items.id = calendar_reminders.item_id "
            "WHERE calendar_reminders.status='proposed' "
            "ORDER BY calendar_reminders.event_date, calendar_reminders.start_time"
        ).fetchall()]


def get_calendar_reminder(reminder_id: int):
    with conn() as c:
        row = c.execute(
            "SELECT calendar_reminders.*, items.filename FROM calendar_reminders "
            "JOIN items ON items.id = calendar_reminders.item_id "
            "WHERE calendar_reminders.id=?",
            (reminder_id,),
        ).fetchone()
    return dict(row) if row else None


def add_reschedule_plan(reminder_id: int, plan: dict) -> int:
    with conn() as c:
        c.execute(
            "UPDATE calendar_reschedule_plans SET status='superseded' "
            "WHERE reminder_id=? AND status='proposed'",
            (reminder_id,),
        )
        return c.execute(
            "INSERT INTO calendar_reschedule_plans "
            "(reminder_id, plan_json, created_at) VALUES (?,?,?)",
            (reminder_id, json.dumps(plan, ensure_ascii=False), time.time()),
        ).lastrowid


def get_reschedule_plan(plan_id: int):
    with conn() as c:
        row = c.execute(
            "SELECT * FROM calendar_reschedule_plans WHERE id=?", (plan_id,)
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["plan"] = json.loads(result.pop("plan_json"))
    return result


def set_reschedule_plan_status(plan_id: int, status: str, error: str | None = None) -> bool:
    with conn() as c:
        return c.execute(
            "UPDATE calendar_reschedule_plans SET status=?, error=?, applied_at=? WHERE id=?",
            (status, error, time.time() if status == "applied" else None, plan_id),
        ).rowcount > 0


def set_calendar_reminder_status(reminder_id: int, status: str) -> bool:
    with conn() as c:
        return c.execute(
            "UPDATE calendar_reminders SET status=?, error=NULL WHERE id=?",
            (status, reminder_id),
        ).rowcount > 0


def calendar_reminder_counts():
    with conn() as c:
        rows = c.execute(
            "SELECT status, COUNT(*) AS count FROM calendar_reminders GROUP BY status"
        ).fetchall()
    return {row["status"]: row["count"] for row in rows}


def set_calendar_reminder_result(reminder_id: int, google_event_id: str | None,
                                 error: str | None = None):
    with conn() as c:
        c.execute(
            "UPDATE calendar_reminders SET status=?, google_event_id=?, error=? WHERE id=?",
            ("error" if error else "created", google_event_id, error, reminder_id),
        )


def add_chat_turn(role: str, content: str, sources: list[dict] | None = None,
                  videos: list[dict] | None = None,
                  images: list[dict] | None = None) -> int:
    with conn() as c:
        return c.execute(
            "INSERT INTO chat_turns (role, content, sources_json, videos_json, images_json, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (role, content, json.dumps(sources or [], ensure_ascii=False),
             json.dumps(videos or [], ensure_ascii=False),
             json.dumps(images or [], ensure_ascii=False), time.time()),
        ).lastrowid


def list_chat_turns(limit: int = 200):
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM (SELECT * FROM chat_turns ORDER BY id DESC LIMIT ?) "
            "ORDER BY id", (limit,),
        ).fetchall()
    return [{
        "id": row["id"], "role": row["role"], "content": row["content"],
        "sources": json.loads(row["sources_json"]),
        "videos": json.loads(row["videos_json"]),
        "images": json.loads(row["images_json"]),
        "created_at": row["created_at"],
    } for row in rows]


def clear_chat_turns():
    with conn() as c:
        c.execute("DELETE FROM chat_turns")


def create_flashcard_deck(title: str, topic: str, cards: list[dict],
                          subject: str | None = None,
                          sources: list[dict] | None = None) -> int:
    """Save a complete deck in one transaction."""
    now = time.time()
    with conn() as c:
        deck_id = c.execute(
            "INSERT INTO flashcard_decks "
            "(title, topic, subject, sources_json, created_at) VALUES (?,?,?,?,?)",
            (title, topic, subject, json.dumps(sources or [], ensure_ascii=False), now),
        ).lastrowid
        c.executemany(
            "INSERT INTO flashcards (deck_id, front, back, position, created_at) "
            "VALUES (?,?,?,?,?)",
            [
                (deck_id, card["front"], card["back"], position, now)
                for position, card in enumerate(cards)
            ],
        )
    return deck_id


def list_flashcard_decks():
    with conn() as c:
        rows = c.execute(
            "SELECT flashcard_decks.*, COUNT(flashcards.id) AS card_count "
            "FROM flashcard_decks LEFT JOIN flashcards "
            "ON flashcards.deck_id=flashcard_decks.id "
            "GROUP BY flashcard_decks.id ORDER BY flashcard_decks.created_at DESC"
        ).fetchall()
    decks = []
    for row in rows:
        deck = dict(row)
        deck["sources"] = json.loads(deck.pop("sources_json"))
        decks.append(deck)
    return decks


def get_flashcard_deck(deck_id: int):
    with conn() as c:
        deck = c.execute(
            "SELECT * FROM flashcard_decks WHERE id=?", (deck_id,)
        ).fetchone()
        if deck is None:
            return None
        cards = c.execute(
            "SELECT id, front, back, position FROM flashcards "
            "WHERE deck_id=? ORDER BY position", (deck_id,)
        ).fetchall()
    result = dict(deck)
    result["sources"] = json.loads(result.pop("sources_json"))
    result["cards"] = [dict(card) for card in cards]
    result["card_count"] = len(cards)
    return result


def delete_flashcard_deck(deck_id: int) -> bool:
    with conn() as c:
        c.execute("DELETE FROM flashcards WHERE deck_id=?", (deck_id,))
        deleted = c.execute(
            "DELETE FROM flashcard_decks WHERE id=?", (deck_id,)
        ).rowcount
    return bool(deleted)


def flashcard_count() -> int:
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM flashcards").fetchone()[0]


def create_question_paper(
    title: str,
    difficulty: str,
    duration_minutes: int,
    instructions: str,
    questions: list[dict],
    sources: list[dict],
) -> int:
    """Persist a complete generated paper and answer key atomically."""
    now = time.time()
    total_marks = sum(int(question["marks"]) for question in questions)
    with conn() as c:
        paper_id = c.execute(
            "INSERT INTO question_papers "
            "(title, difficulty, duration_minutes, total_marks, instructions, "
            "sources_json, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                title, difficulty, duration_minutes, total_marks, instructions,
                json.dumps(sources, ensure_ascii=False), now,
            ),
        ).lastrowid
        c.executemany(
            "INSERT INTO question_paper_questions "
            "(paper_id, question_type, prompt, options_json, answer, explanation, "
            "marks, position, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (
                    paper_id, question["type"], question["prompt"],
                    json.dumps(question.get("options", []), ensure_ascii=False),
                    question["answer"], question.get("explanation", ""),
                    question["marks"], position, now,
                )
                for position, question in enumerate(questions, start=1)
            ],
        )
    return paper_id


def list_question_papers():
    with conn() as c:
        rows = c.execute(
            "SELECT question_papers.*, COUNT(question_paper_questions.id) AS question_count "
            "FROM question_papers LEFT JOIN question_paper_questions "
            "ON question_paper_questions.paper_id=question_papers.id "
            "GROUP BY question_papers.id ORDER BY question_papers.created_at DESC"
        ).fetchall()
    papers = []
    for row in rows:
        paper = dict(row)
        paper["sources"] = json.loads(paper.pop("sources_json"))
        papers.append(paper)
    return papers


def get_question_paper(paper_id: int):
    with conn() as c:
        paper = c.execute(
            "SELECT * FROM question_papers WHERE id=?", (paper_id,)
        ).fetchone()
        if paper is None:
            return None
        questions = c.execute(
            "SELECT id, question_type, prompt, options_json, answer, explanation, "
            "marks, position FROM question_paper_questions "
            "WHERE paper_id=? ORDER BY position",
            (paper_id,),
        ).fetchall()
    result = dict(paper)
    result["sources"] = json.loads(result.pop("sources_json"))
    result["questions"] = [
        {
            **dict(question),
            "type": question["question_type"],
            "options": json.loads(question["options_json"]),
        }
        for question in questions
    ]
    for question in result["questions"]:
        question.pop("question_type")
        question.pop("options_json")
    result["question_count"] = len(result["questions"])
    return result


def delete_question_paper(paper_id: int) -> bool:
    with conn() as c:
        c.execute(
            "UPDATE question_paper_jobs SET paper_id=NULL WHERE paper_id=?", (paper_id,)
        )
        c.execute(
            "DELETE FROM question_paper_questions WHERE paper_id=?", (paper_id,)
        )
        return bool(c.execute(
            "DELETE FROM question_papers WHERE id=?", (paper_id,)
        ).rowcount)


def add_question_paper_job(request: dict) -> int:
    with conn() as c:
        return c.execute(
            "INSERT INTO question_paper_jobs (request_json, created_at) VALUES (?,?)",
            (json.dumps(request, ensure_ascii=False), time.time()),
        ).lastrowid


def finish_question_paper_job(
    job_id: int, paper_id: int | None = None, error: str | None = None,
) -> None:
    with conn() as c:
        c.execute(
            "UPDATE question_paper_jobs SET status=?, paper_id=?, error=?, finished_at=? "
            "WHERE id=?",
            ("error" if error else "done", paper_id, error, time.time(), job_id),
        )


def list_question_paper_jobs(limit: int = 20):
    with conn() as c:
        rows = c.execute(
            "SELECT id, status, paper_id, error, created_at, finished_at "
            "FROM question_paper_jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def note_id_for_item(item_id: int) -> int | None:
    with conn() as c:
        row = c.execute(
            "SELECT id FROM notes WHERE item_id=? ORDER BY created_at DESC LIMIT 1", (item_id,)
        ).fetchone()
    return row["id"] if row else None
