"""Telegram UI for Study Buddy.

Run with: .venv/bin/python telegram_bot.py
The bot talks directly to the local core modules, so the web UI is optional.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import mimetypes
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from core import db, flashcards, llm, rag
from core.config import (
    AUDIOBOOKS_DIR,
    FILES_DIR,
    TELEGRAM_ALLOWED_CHAT_IDS,
    TELEGRAM_ALLOWED_USER_IDS,
    TELEGRAM_ALLOW_ALL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_MAX_UPLOAD_MB,
    kind_of,
)
from core.dates import capture_date_from_text, event_date_from_due_text
from core.ingest import start_worker

log = logging.getLogger("study_buddy.telegram")
PAGE_SIZE = 7
MESSAGE_LIMIT = 3900


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_button("📊 Dashboard", "dashboard"), _button("📝 Notes", "notes:0")],
        [_button("📎 Files & capture", "files"), _button("🔎 Ask my notes", "ask")],
        [_button("✅ Tasks", "tasks"), _button("🎧 Audiobooks", "audiobooks")],
        [_button("📅 Calendar", "calendar"), _button("⚙️ Settings", "settings")],
    ])


def _back(data: str = "menu") -> list[InlineKeyboardButton]:
    return [_button("‹ Back", data), _button("🏠 Menu", "menu")]


def _is_allowed(update: Update) -> bool:
    if TELEGRAM_ALLOW_ALL:
        return True
    user = update.effective_user
    chat = update.effective_chat
    user_ok = bool(user and user.id in TELEGRAM_ALLOWED_USER_IDS)
    chat_ok = bool(chat and chat.id in TELEGRAM_ALLOWED_CHAT_IDS)
    if TELEGRAM_ALLOWED_USER_IDS and TELEGRAM_ALLOWED_CHAT_IDS:
        return user_ok and chat_ok
    if TELEGRAM_ALLOWED_USER_IDS:
        return user_ok
    if TELEGRAM_ALLOWED_CHAT_IDS:
        return chat_ok
    return False


async def _deny(update: Update) -> None:
    user_id = update.effective_user.id if update.effective_user else "unknown"
    chat_id = update.effective_chat.id if update.effective_chat else "unknown"
    text = (
        "Study Buddy is locked. Add this value to your local .env and restart the bot:\n\n"
        f"TELEGRAM_ALLOWED_USER_IDS={user_id}\n\nChat ID: {chat_id}"
    )
    if update.callback_query:
        await update.callback_query.answer("This bot is locked.", show_alert=True)
    elif update.effective_message:
        await update.effective_message.reply_text(text)


async def _show(update: Update, text: str, keyboard: InlineKeyboardMarkup | None = None) -> None:
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text[:4096], reply_markup=keyboard)
            return
        except BadRequest as error:
            if "message is not modified" in str(error).lower():
                return
    if update.effective_message:
        await update.effective_message.reply_text(text[:4096], reply_markup=keyboard)


async def _send_long(message, text: str, keyboard: InlineKeyboardMarkup | None = None) -> None:
    clean = text.strip() or "(empty)"
    parts = []
    while len(clean) > MESSAGE_LIMIT:
        split_at = clean.rfind("\n", 0, MESSAGE_LIMIT)
        if split_at < MESSAGE_LIMIT // 2:
            split_at = MESSAGE_LIMIT
        parts.append(clean[:split_at])
        clean = clean[split_at:].lstrip()
    parts.append(clean)
    for index, part in enumerate(parts):
        await message.reply_text(part, reply_markup=keyboard if index == len(parts) - 1 else None)


def _safe_name(value: str | None, suffix: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "", value or "note").strip(" .") or "note"
    return f"{stem[:80]}{suffix}"


def _note_row(note_id: int):
    with db.conn() as c:
        row = c.execute(
            "SELECT notes.*, items.title, subjects.name AS subject FROM notes "
            "JOIN items ON items.id=notes.item_id "
            "LEFT JOIN subjects ON subjects.id=items.subject_id WHERE notes.id=?",
            (note_id,),
        ).fetchone()
    return dict(row) if row else None


def _item_row(item_id: int):
    with db.conn() as c:
        row = c.execute(
            "SELECT items.*, subjects.name AS subject FROM items "
            "LEFT JOIN subjects ON subjects.id=items.subject_id WHERE items.id=?",
            (item_id,),
        ).fetchone()
    return dict(row) if row else None


def _recent_notes(limit: int = 1000) -> list[dict]:
    with db.conn() as c:
        rows = c.execute(
            "SELECT notes.id, notes.item_id, notes.markdown, notes.created_at, "
            "items.title, subjects.name AS subject FROM notes "
            "JOIN items ON items.id=notes.item_id "
            "LEFT JOIN subjects ON subjects.id=items.subject_id "
            "ORDER BY notes.created_at DESC LIMIT ?", (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    context.user_data.pop("mode", None)
    await update.effective_message.reply_text(
        "Study Buddy is ready. Capture material, search your notes, manage tasks, "
        "review calendar suggestions, and generate audiobooks here.",
        reply_markup=_menu_keyboard(),
    )


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else "unknown"
    chat_id = update.effective_chat.id if update.effective_chat else "unknown"
    await update.effective_message.reply_text(f"User ID: {user_id}\nChat ID: {chat_id}")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    context.user_data.pop("mode", None)
    await update.effective_message.reply_text("Cancelled.", reply_markup=_menu_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    await update.effective_message.reply_text(
        "Commands\n"
        "/menu — open the UI\n"
        "/ask question — ask your notes\n"
        "/capture text — save text as a note capture\n"
        "/task label | due date — add a task\n"
        "/status — processing status\n"
        "/cancel — leave the current input mode\n"
        "/id — show IDs for access configuration\n\n"
        "You can also send voice messages, video notes, audio/video files, PDFs, images, "
        "or text documents. Add a caption to provide date or topic context."
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    await _files(update, context)


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    question = " ".join(context.args).strip()
    if not question:
        context.user_data["mode"] = "ask"
        await update.effective_message.reply_text("Send your question. Use /cancel to stop.")
        return
    await _answer_question(update.effective_message, question, context.user_data.get("ask_subject"))


async def capture_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    value = " ".join(context.args).strip()
    if not value:
        context.user_data["mode"] = "capture"
        await update.effective_message.reply_text("Send the text you want to capture. Use /cancel to stop.")
        return
    await _queue_text(update.effective_message, value, context)


async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    value = " ".join(context.args).strip()
    if not value:
        context.user_data["mode"] = "task"
        await update.effective_message.reply_text("Send: task label | due date (the date is optional).")
        return
    await _create_task_from_text(update.effective_message, value)


async def _dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with db.conn() as c:
        notes = c.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        files = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE done=0").fetchone()[0]
        active = c.execute("SELECT COUNT(*) FROM items WHERE status IN ('pending','processing')").fetchone()[0]
    books = len(list(AUDIOBOOKS_DIR.glob("*.wav")))
    await _show(
        update,
        f"📊 Dashboard\n\n📝 {notes} notes\n📎 {files} files\n"
        f"✅ {tasks} open tasks\n🎧 {books} audiobooks\n⚙️ {active} processing",
        InlineKeyboardMarkup([_back()]),
    )


async def _notes(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    notes = _recent_notes()
    pages = max(1, (len(notes) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    visible = notes[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    rows = [[_button(f"📝 {(n['title'] or 'Untitled')[:42]}", f"note:{n['id']}")] for n in visible]
    nav = []
    if page:
        nav.append(_button("‹ Newer", f"notes:{page - 1}"))
    if page + 1 < pages:
        nav.append(_button("Older ›", f"notes:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.extend([
        [_button("⬇️ Export all", "export"), _button("⬆️ Import", "import")],
        _back(),
    ])
    text = f"📝 Notes — page {page + 1}/{pages}"
    if not notes:
        text += "\n\nNo notes yet. Send a capture to get started."
    await _show(update, text, InlineKeyboardMarkup(rows))


async def _note(update: Update, context: ContextTypes.DEFAULT_TYPE, note_id: int) -> None:
    row = _note_row(note_id)
    if not row:
        await _show(update, "Note not found.", InlineKeyboardMarkup([_back("notes:0")]))
        return
    keyboard = InlineKeyboardMarkup([
        [_button("⬇️ Download Markdown", f"notedl:{note_id}"), _button("🎧 Make audiobook", f"noteab:{note_id}")],
        _back("notes:0"),
    ])
    header = f"📝 {row['title'] or 'Untitled'}\nSubject: {row['subject'] or 'Unsorted'}\n\n"
    if len(header) + len(row["markdown"]) <= 4096:
        await _show(update, header + row["markdown"], keyboard)
    else:
        await _show(update, header + row["markdown"][:3400] + "\n\n…continued below", keyboard)
        await _send_long(update.effective_message, row["markdown"][3400:])


async def _download_note(update: Update, note_id: int) -> None:
    row = _note_row(note_id)
    if not row:
        await update.effective_message.reply_text("Note not found.")
        return
    data = io.BytesIO(row["markdown"].encode("utf-8"))
    data.name = _safe_name(row["title"], ".md")
    await update.effective_message.reply_document(data, filename=data.name, caption=row["title"] or "Study Buddy note")


async def _files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    items = db.list_items()[:10]
    icon = {"pending": "⏳", "processing": "⚙️", "done": "✅", "error": "❌"}
    lines = ["📎 Recent files"]
    rows = []
    for item in items:
        title = item["title"] or item["filename"]
        lines.append(f"{icon.get(item['status'], '•')} {title[:55]} — {item['status']}")
        rows.append([_button(f"{icon.get(item['status'], '•')} {title[:40]}", f"file:{item['id']}")])
    if not items:
        lines.append("\nNothing captured yet.")
    rows.extend([[_button("➕ How to capture", "capture")], _back()])
    await _show(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def _file_detail(update: Update, item_id: int) -> None:
    row = _item_row(item_id)
    if not row:
        await _show(update, "File not found.", InlineKeyboardMarkup([_back("files")]))
        return
    text = (
        f"📎 {row['title'] or row['filename']}\n\nOriginal: {row['filename']}\n"
        f"Type: {row['kind']}\nStatus: {row['status']}\nSubject: {row['subject'] or 'Unsorted'}"
    )
    if row.get("error"):
        text += f"\nError: {row['error']}"
    buttons = []
    if row.get("stored_path") and Path(row["stored_path"]).is_file():
        buttons.append([_button("⬇️ Download original", f"filedl:{item_id}")])
    note_id = db.note_id_for_item(item_id)
    if note_id:
        buttons.append([_button("📝 Open generated note", f"note:{note_id}")])
    buttons.append(_back("files"))
    await _show(update, text, InlineKeyboardMarkup(buttons))


async def _download_file(update: Update, item_id: int) -> None:
    row = _item_row(item_id)
    path = Path(row["stored_path"]) if row and row.get("stored_path") else None
    if not path or not path.is_file():
        await update.effective_message.reply_text("The original file is unavailable.")
        return
    if path.stat().st_size > 50 * 1024 * 1024:
        await update.effective_message.reply_text("This file is larger than Telegram's 50 MB send limit.")
        return
    with path.open("rb") as handle:
        await update.effective_message.reply_document(handle, filename=row["filename"])


async def _ask_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    subject_id = context.user_data.get("ask_subject_id")
    subjects = db.list_subjects()
    rows = [[_button("All subjects" + (" ✓" if subject_id is None else ""), "asksub:all")]]
    rows += [[_button(s["name"][:45] + (" ✓" if s["id"] == subject_id else ""), f"asksub:{s['id']}")] for s in subjects[:15]]
    rows.extend([[_button("🗑 Clear chat history", "askclear")], _back()])
    context.user_data["mode"] = "ask"
    subject = context.user_data.get("ask_subject") or "all subjects"
    await _show(update, f"🔎 Ask my notes\n\nCurrent scope: {subject}\nSend your question now.", InlineKeyboardMarkup(rows))


async def _answer_question(message, question: str, subject: str | None) -> None:
    await message.chat.send_action(ChatAction.TYPING)
    db.add_chat_turn("user", question)
    try:
        result = await asyncio.to_thread(flashcards.maybe_create_from_chat, question, subject)
        if result is None:
            result = await asyncio.to_thread(rag.ask, question, subject)
    except Exception as error:
        await message.reply_text(f"I could not answer that: {error}")
        return
    db.add_chat_turn("assistant", result["answer"], result["sources"])
    answer = re.sub(r"\[\[source: ([^]]+)\]\]\([^)]*\)", r"[source: \1]", result["answer"])
    answer = answer.replace("[Study the deck](/flashcards)", "Open the Flashcards page in the web app to study it.")
    if result["sources"]:
        labels = "\n".join(f"• {s['label']}" for s in result["sources"][:8])
        answer += f"\n\nSources\n{labels}"
    await _send_long(message, answer, InlineKeyboardMarkup([_back("ask")]))
    for image_path in result.get("images", [])[:5]:
        path = Path(image_path)
        if path.is_file():
            with path.open("rb") as image:
                await message.reply_photo(image)


async def _tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tasks = db.list_tasks()
    rows = []
    lines = ["✅ Tasks"]
    for task in tasks[:20]:
        mark = "☑" if task["done"] else "☐"
        due = f" — {task['due']}" if task.get("due") else ""
        lines.append(f"{mark} {task['label']}{due}")
        rows.append([
            _button(mark, f"tasktog:{task['id']}"),
            _button(task["label"][:34], f"tasktog:{task['id']}"),
            _button("🗑", f"taskdel:{task['id']}"),
        ])
    if not tasks:
        lines.append("\nNo tasks yet.")
    rows.extend([[_button("➕ Add task", "taskadd")], _back()])
    await _show(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def _create_task_from_text(message, value: str) -> None:
    label, separator, due = value.partition("|")
    label, due = label.strip(), due.strip() if separator else ""
    if not label:
        await message.reply_text("A task label is required. Send: task label | due date")
        return
    task_id = db.add_task(label, due or None)
    rows = []
    if due:
        rows.append([_button("📅 Add to Google Calendar", f"taskcal:{task_id}")])
    rows.append(_back("tasks"))
    await message.reply_text(
        f"Task saved locally: {label}" + (f"\nDue: {due}" if due else ""),
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def _audiobooks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    paths = sorted(AUDIOBOOKS_DIR.glob("*.wav"), key=lambda p: -p.stat().st_mtime)[:10]
    mapping = {str(index): str(path) for index, path in enumerate(paths)}
    context.user_data["audio_files"] = mapping
    rows = [[_button(f"▶️ {path.stem[:42]}", f"absend:{index}")] for index, path in enumerate(paths)]
    rows.extend([[_button("➕ Generate from notes", "abpick")], _back()])
    text = "🎧 Audiobooks"
    if not paths:
        text += "\n\nNo audiobooks yet."
    await _show(update, text, InlineKeyboardMarkup(rows))


async def _audiobook_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    selected = set(context.user_data.get("ab_selected", []))
    notes = _recent_notes(20)
    rows = [[_button(("✓ " if n["id"] in selected else "○ ") + (n["title"] or "Untitled")[:40], f"absel:{n['id']}")] for n in notes]
    if selected:
        rows.append([_button(f"🎧 Generate ({len(selected)})", "abgo")])
    rows.append(_back("audiobooks"))
    await _show(update, "Select one or more notes for the audiobook.", InlineKeyboardMarkup(rows))


async def _generate_audiobook(message, note_ids: list[int], name: str) -> None:
    placeholders = ",".join("?" for _ in note_ids)
    with db.conn() as c:
        rows = c.execute(f"SELECT markdown FROM notes WHERE id IN ({placeholders})", note_ids).fetchall()
    combined = "\n\n".join(row["markdown"] for row in rows)
    if not combined.strip():
        await message.reply_text("No valid notes were selected.")
        return
    job_id = db.add_audiobook_job(name)
    try:
        from core.audiobook import generate
        path = await asyncio.to_thread(generate, combined, name)
        db.finish_audiobook_job(job_id, path.name)
        await message.reply_text("Audiobook ready.")
        await _send_audio(message, path)
    except Exception as error:
        db.finish_audiobook_job(job_id, None, str(error)[:500])
        await message.reply_text(f"Audiobook generation failed: {error}")


async def _send_audio(message, path: Path) -> None:
    if not path.is_file():
        await message.reply_text("Audiobook file not found.")
        return
    mp3_path = Path(tempfile.gettempdir()) / f"study-buddy-{uuid4().hex}.mp3"
    try:
        await asyncio.to_thread(
            subprocess.run,
            ["ffmpeg", "-y", "-i", str(path), "-codec:a", "libmp3lame", "-q:a", "4", str(mp3_path)],
            check=True, capture_output=True,
        )
        with mp3_path.open("rb") as audio:
            await message.reply_audio(audio, filename=f"{path.stem}.mp3", title=path.stem)
    except (subprocess.CalledProcessError, FileNotFoundError):
        with path.open("rb") as audio:
            await message.reply_document(audio, filename=path.name, caption="Audiobook (WAV)")
    finally:
        mp3_path.unlink(missing_ok=True)


async def _calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from core import google_calendar
    configured = google_calendar.is_configured()
    connected = await asyncio.to_thread(lambda: google_calendar.credentials() is not None)
    proposals = db.list_calendar_proposals()
    counts = db.calendar_reminder_counts()
    text = (
        "📅 Google Calendar\n\n"
        f"Configured: {'yes' if configured else 'no'}\nConnected: {'yes' if connected else 'no'}\n"
        f"Suggestions to review: {len(proposals)}\nCreated reminders: {counts.get('created', 0)}"
    )
    rows = []
    if configured and not connected:
        try:
            url = google_calendar.authorization_url()
            rows.append([InlineKeyboardButton("🔗 Connect Google Calendar", url=url)])
        except Exception:
            pass
    if connected:
        rows.append([_button("🗓 Next 30 days", "calevents"), _button("🔄 Sync", "calsync")])
    for proposal in proposals[:10]:
        label = f"{proposal['event_date']} · {proposal['title']}"
        rows.append([_button(f"✅ {label[:35]}", f"calapprove:{proposal['id']}"), _button("Dismiss", f"caldismiss:{proposal['id']}")])
    rows.append(_back())
    await _show(update, text, InlineKeyboardMarkup(rows))


async def _calendar_events(update: Update) -> None:
    from core import google_calendar
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=30)
    try:
        events = await asyncio.to_thread(google_calendar.list_events, start.isoformat(), end.isoformat())
    except Exception as error:
        await _show(update, f"Could not load events: {error}", InlineKeyboardMarkup([_back("calendar")]))
        return
    lines = ["🗓 Next 30 days"]
    for event in events[:30]:
        lines.append(f"• {event['start']} — {event['summary']}")
    if not events:
        lines.append("\nNo events found.")
    await _show(update, "\n".join(lines)[:4000], InlineKeyboardMarkup([_back("calendar")]))


async def _settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with db.conn() as c:
        database_ok = c.execute("SELECT 1").fetchone()[0] == 1
    await _show(
        update,
        "⚙️ Settings\n\n"
        f"Local database: {'connected' if database_ok else 'unavailable'}\n"
        f"LM Studio: {'connected' if llm.is_available() else 'not reachable'}\n"
        "Speech-to-text: Moonshine (local)\nEmbeddings: MiniLM (local)\n"
        "Text-to-speech: Kokoro (local)\n"
        f"Telegram upload limit: {TELEGRAM_MAX_UPLOAD_MB} MB",
        InlineKeyboardMarkup([_back()]),
    )


async def _export_notes(update: Update) -> None:
    notes = _recent_notes()
    payload = {
        "format": "study-buddy-notes", "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "notes": [{
            "title": n.get("title"), "subject": n.get("subject"),
            "markdown": n["markdown"], "created_at": n["created_at"],
        } for n in reversed(notes)],
    }
    data = io.BytesIO(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    filename = f"study-buddy-notes-{datetime.now().date().isoformat()}.json"
    data.name = filename
    await update.effective_message.reply_document(data, filename=filename, caption=f"{len(notes)} notes exported")


def _import_notes(raw: bytes, filename: str) -> tuple[int, int]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        payload = {"notes": [{"title": Path(filename).stem, "subject": "Imported", "markdown": raw.decode("utf-8")}]}
    else:
        payload = json.loads(raw.decode("utf-8"))
        if payload.get("format") != "study-buddy-notes" or payload.get("version") != 1:
            raise ValueError("This is not a supported Study Buddy backup")
    entries = payload.get("notes")
    if not isinstance(entries, list):
        raise ValueError("The backup does not contain a notes list")
    imported = skipped = 0
    now = time.time()
    with db.conn() as c:
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("markdown"), str):
                raise ValueError("The backup contains an invalid note")
            markdown = entry["markdown"]
            if not markdown.strip():
                skipped += 1
                continue
            title = entry.get("title") if isinstance(entry.get("title"), str) else None
            subject = entry.get("subject") if isinstance(entry.get("subject"), str) else None
            duplicate = c.execute(
                "SELECT 1 FROM notes JOIN items ON items.id=notes.item_id "
                "LEFT JOIN subjects ON subjects.id=items.subject_id "
                "WHERE notes.markdown=? AND COALESCE(items.title,'')=? "
                "AND COALESCE(subjects.name,'')=? LIMIT 1",
                (markdown, title or "", subject or ""),
            ).fetchone()
            if duplicate:
                skipped += 1
                continue
            subject_id = None
            if subject and subject.strip():
                subject_name = subject.strip()
                found = c.execute("SELECT id FROM subjects WHERE name=?", (subject_name,)).fetchone()
                subject_id = found["id"] if found else c.execute(
                    "INSERT INTO subjects(name,created_at) VALUES(?,?)", (subject_name, now)
                ).lastrowid
            created = entry.get("created_at") if isinstance(entry.get("created_at"), (int, float)) else now
            item_id = c.execute(
                "INSERT INTO items(filename,stored_path,kind,status,title,subject_id,created_at,processed_at) "
                "VALUES(?,?,?,'done',?,?,?,?)",
                (_safe_name(title, ".md"), "", "imported note", title, subject_id, created, now),
            ).lastrowid
            c.execute("INSERT INTO notes(item_id,markdown,created_at) VALUES(?,?,?)", (item_id, markdown, created))
            imported += 1
    return imported, skipped


async def _queue_text(message, value: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(value) > 1_000_000:
        await message.reply_text("Text captures are limited to 1 MB.")
        return
    dated = capture_date_from_text(value)
    filename = f"telegram-text-{dated}-{uuid4().hex[:8]}.txt"
    path = FILES_DIR / filename
    path.write_text(value, encoding="utf-8")
    item_id = db.add_item(filename, str(path), "text", None, dated)
    await message.reply_text(f"Queued text capture with citation date {dated}.", reply_markup=_menu_keyboard())
    context.application.create_task(_watch_item(context.application, message.chat_id, item_id))


def _media_details(message):
    if message.voice:
        return message.voice, f"voice-{message.message_id}.ogg", message.voice.mime_type
    if message.video_note:
        return message.video_note, f"video-note-{message.message_id}.mp4", "video/mp4"
    if message.audio:
        return message.audio, message.audio.file_name or f"audio-{message.message_id}.mp3", message.audio.mime_type
    if message.video:
        return message.video, message.video.file_name or f"video-{message.message_id}.mp4", message.video.mime_type
    if message.document:
        return message.document, message.document.file_name or f"document-{message.message_id}", message.document.mime_type
    if message.photo:
        return message.photo[-1], f"photo-{message.message_id}.jpg", "image/jpeg"
    return None, "", None


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    message = update.effective_message
    media, original_name, mime_type = _media_details(message)
    if not media:
        return
    if context.user_data.get("mode") == "import" and message.document:
        if (media.file_size or 0) > 100 * 1024 * 1024:
            await message.reply_text("Imports are limited to 100 MB.")
            return
        try:
            telegram_file = await media.get_file()
            raw = bytes(await telegram_file.download_as_bytearray())
            imported, skipped = await asyncio.to_thread(_import_notes, raw, original_name)
            context.user_data.pop("mode", None)
            await message.reply_text(f"Imported {imported} notes; skipped {skipped} duplicates/empty notes.", reply_markup=_menu_keyboard())
        except Exception as error:
            await message.reply_text(f"Import failed: {error}")
        return

    max_bytes = TELEGRAM_MAX_UPLOAD_MB * 1024 * 1024
    if (media.file_size or 0) > max_bytes:
        await message.reply_text(f"This upload exceeds the configured {TELEGRAM_MAX_UPLOAD_MB} MB limit.")
        return
    safe_original = Path(original_name).name
    suffix = Path(safe_original).suffix.lower()
    if not suffix and mime_type:
        suffix = mimetypes.guess_extension(mime_type.split(";", 1)[0]) or ""
        safe_original += suffix
    if kind_of(Path(safe_original)) is None:
        await message.reply_text("Unsupported type. Send audio/video, PDF, image, TXT, or Markdown.")
        return
    path = FILES_DIR / f"{time.time_ns()}_{uuid4().hex[:8]}{suffix}"
    try:
        await message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
        telegram_file = await media.get_file()
        await telegram_file.download_to_drive(custom_path=path)
    except TelegramError as error:
        path.unlink(missing_ok=True)
        await message.reply_text(f"Telegram could not download this file: {error}")
        return
    caption = (message.caption or "").strip()
    dated = capture_date_from_text(caption)
    item_id = db.add_item(safe_original, str(path), kind_of(path), caption or None, dated)
    await message.reply_text(
        f"Queued {kind_of(path)} capture: {safe_original}\nCitation date: {dated}\n"
        "I’ll message you when the generated note is ready.",
        reply_markup=_menu_keyboard(),
    )
    context.application.create_task(_watch_item(context.application, message.chat_id, item_id))


async def _watch_item(application: Application, chat_id: int, item_id: int) -> None:
    for _ in range(1200):
        await asyncio.sleep(3)
        row = _item_row(item_id)
        if not row:
            return
        if row["status"] == "done":
            note_id = db.note_id_for_item(item_id)
            keyboard = InlineKeyboardMarkup([[_button("📝 Open note", f"note:{note_id}")], [_button("🏠 Menu", "menu")]]) if note_id else _menu_keyboard()
            await application.bot.send_message(chat_id, f"✅ Note ready: {row['title'] or row['filename']}", reply_markup=keyboard)
            return
        if row["status"] == "error":
            await application.bot.send_message(chat_id, f"❌ Processing failed for {row['filename']}: {row['error']}")
            return


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    message = update.effective_message
    value = (message.text or "").strip()
    mode = context.user_data.get("mode")
    if mode == "ask":
        await _answer_question(message, value, context.user_data.get("ask_subject"))
    elif mode == "capture":
        context.user_data.pop("mode", None)
        await _queue_text(message, value, context)
    elif mode == "task":
        context.user_data.pop("mode", None)
        await _create_task_from_text(message, value)
    elif mode == "import":
        await message.reply_text("Send a Study Buddy JSON backup or a Markdown/TXT document, or /cancel.")
    else:
        await message.reply_text("Choose what you want to do, or use /ask, /capture, or /task.", reply_markup=_menu_keyboard())


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await _deny(update)
        return
    query = update.callback_query
    await query.answer()
    data = str(query.data or "")
    if data not in {"ask", "capture", "taskadd", "import"} and not data.startswith("asksub:") and data != "askclear":
        context.user_data.pop("mode", None)
    try:
        if data == "menu":
            context.user_data.pop("mode", None)
            await _show(update, "Study Buddy", _menu_keyboard())
        elif data == "dashboard":
            await _dashboard(update, context)
        elif data.startswith("notes:"):
            await _notes(update, context, int(data.split(":", 1)[1]))
        elif data.startswith("note:"):
            await _note(update, context, int(data.split(":", 1)[1]))
        elif data.startswith("notedl:"):
            await _download_note(update, int(data.split(":", 1)[1]))
        elif data.startswith("noteab:"):
            note_id = int(data.split(":", 1)[1])
            row = _note_row(note_id)
            if row:
                await query.message.reply_text("Generating audiobook in the background. This may take a few minutes.")
                context.application.create_task(_generate_audiobook(query.message, [note_id], row["title"] or "Audiobook"))
        elif data == "files":
            await _files(update, context)
        elif data.startswith("file:"):
            await _file_detail(update, int(data.split(":", 1)[1]))
        elif data.startswith("filedl:"):
            await _download_file(update, int(data.split(":", 1)[1]))
        elif data == "capture":
            context.user_data["mode"] = "capture"
            await _show(update, "Send text, a voice message, video note, audio/video file, PDF, image, TXT, or Markdown. A caption can include context and a date.", InlineKeyboardMarkup([_back("files")]))
        elif data == "ask":
            await _ask_menu(update, context)
        elif data.startswith("asksub:"):
            raw = data.split(":", 1)[1]
            if raw == "all":
                context.user_data.pop("ask_subject_id", None)
                context.user_data.pop("ask_subject", None)
            else:
                subject_id = int(raw)
                subject = next((s for s in db.list_subjects() if s["id"] == subject_id), None)
                if subject:
                    context.user_data["ask_subject_id"] = subject_id
                    context.user_data["ask_subject"] = subject["name"]
            await _ask_menu(update, context)
        elif data == "askclear":
            db.clear_chat_turns()
            await query.answer("Chat history cleared.", show_alert=True)
        elif data == "tasks":
            await _tasks(update, context)
        elif data == "taskadd":
            context.user_data["mode"] = "task"
            await _show(update, "Send: task label | due date\n\nExample: Revise chapter 4 | August 20", InlineKeyboardMarkup([_back("tasks")]))
        elif data.startswith("tasktog:"):
            task_id = int(data.split(":", 1)[1])
            task = next((t for t in db.list_tasks() if t["id"] == task_id), None)
            if task:
                db.set_task_done(task_id, not bool(task["done"]))
            await _tasks(update, context)
        elif data.startswith("taskdel:"):
            db.delete_task(int(data.split(":", 1)[1]))
            await _tasks(update, context)
        elif data.startswith("taskcal:"):
            task_id = int(data.split(":", 1)[1])
            task = next((t for t in db.list_tasks() if t["id"] == task_id), None)
            if not task or not task.get("due"):
                raise ValueError("This task has no due date")
            event_date = event_date_from_due_text(task["due"])
            if event_date is None:
                raise ValueError("Use a date such as 2026-08-20, August 20, today, or tomorrow")
            from core import google_calendar
            event_id = await asyncio.to_thread(google_calendar.create_task_event, task, event_date)
            db.set_task_google_event(task_id, event_id)
            await query.answer("Added to Google Calendar.", show_alert=True)
        elif data == "audiobooks":
            await _audiobooks(update, context)
        elif data == "abpick":
            context.user_data["ab_selected"] = []
            await _audiobook_picker(update, context)
        elif data.startswith("absel:"):
            note_id = int(data.split(":", 1)[1])
            selected = set(context.user_data.get("ab_selected", []))
            selected.symmetric_difference_update({note_id})
            context.user_data["ab_selected"] = list(selected)
            await _audiobook_picker(update, context)
        elif data == "abgo":
            selected = list(context.user_data.get("ab_selected", []))
            if not selected:
                raise ValueError("Select at least one note")
            context.user_data["ab_selected"] = []
            await _show(update, "Generating audiobook in the background. I’ll send it here when ready.", InlineKeyboardMarkup([_back("audiobooks")]))
            context.application.create_task(_generate_audiobook(query.message, selected, "Study Buddy"))
        elif data.startswith("absend:"):
            path = Path(context.user_data.get("audio_files", {}).get(data.split(":", 1)[1], ""))
            await _send_audio(query.message, path)
        elif data == "calendar":
            await _calendar(update, context)
        elif data == "calevents":
            await _calendar_events(update)
        elif data == "calsync":
            from core import google_calendar
            result = await asyncio.to_thread(google_calendar.sync_pending_reminders)
            await query.answer(f"Created {result.get('created', 0)} reminders.", show_alert=True)
            await _calendar(update, context)
        elif data.startswith("calapprove:"):
            reminder_id = int(data.split(":", 1)[1])
            from core import google_calendar
            if not google_calendar.credentials():
                raise PermissionError("Connect Google Calendar first")
            db.set_calendar_reminder_status(reminder_id, "approved")
            await asyncio.to_thread(google_calendar.sync_pending_reminders)
            await _calendar(update, context)
        elif data.startswith("caldismiss:"):
            db.set_calendar_reminder_status(int(data.split(":", 1)[1]), "dismissed")
            await _calendar(update, context)
        elif data == "settings":
            await _settings(update, context)
        elif data == "export":
            await _export_notes(update)
        elif data == "import":
            context.user_data["mode"] = "import"
            await _show(update, "Send a Study Buddy JSON backup or a Markdown/TXT document now.", InlineKeyboardMarkup([_back("notes:0")]))
    except Exception as error:
        log.exception("Telegram action failed: %s", data)
        await query.message.reply_text(f"That action failed: {error}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled Telegram update error", exc_info=context.error)


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands([
        BotCommand("menu", "Open Study Buddy"),
        BotCommand("ask", "Ask your notes"),
        BotCommand("capture", "Capture text"),
        BotCommand("task", "Add a task"),
        BotCommand("status", "Show processing status"),
        BotCommand("cancel", "Cancel current input"),
        BotCommand("help", "Show help"),
        BotCommand("id", "Show your Telegram IDs"),
    ])


def build_application() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing from .env")
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).concurrent_updates(False).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("ask", ask_command))
    application.add_handler(CommandHandler("capture", capture_command))
    application.add_handler(CommandHandler("task", task_command))
    application.add_handler(CallbackQueryHandler(callback))
    media_filter = filters.VOICE | filters.VIDEO_NOTE | filters.AUDIO | filters.VIDEO | filters.Document.ALL | filters.PHOTO
    application.add_handler(MessageHandler(media_filter, handle_media))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    if os.getenv("STUDY_BUDDY_MANAGED") == "1":
        from study_buddy.logging import configure_logging

        configure_logging()
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    # httpx includes the Bot API token in request URLs at INFO level.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    db.init_db()
    if os.getenv("STUDY_BUDDY_MANAGED") != "1":
        start_worker()
    application = build_application()
    log.info("Study Buddy Telegram bot is polling")
    application.run_polling(drop_pending_updates=False, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
