"""Attention-aware browser captures adapted from Glean into Axiom Trace."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from core import db


def _safe_stem(title: str | None) -> str:
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", title or "browser-reading").strip("-")
    return (stem[:60] or "browser-reading").lower()


def ingest_browser_event(event: dict, files_dir: Path) -> dict:
    """Persist a capture as a normal queued text item, exactly once by event ID."""
    event_id = str(event["event_id"])
    existing = db.get_capture_event(event_id)
    if existing:
        return {
            "event_id": event_id,
            "item_id": int(existing["item_id"]),
            "status": "duplicate_event",
        }

    text = str(event["text"]).strip()
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    filename = f"browser-{_safe_stem(event.get('title'))}-{event_id[:8]}.txt"
    files_dir.mkdir(parents=True, exist_ok=True)
    destination = files_dir / filename
    partial = destination.with_suffix(destination.suffix + ".part")
    partial.write_text(text, encoding="utf-8")
    os.replace(partial, destination)

    try:
        item_id, created = db.add_browser_capture(
            event_id=event_id,
            filename=filename,
            stored_path=str(destination),
            source_uri=str(event["source_uri"]),
            title=event.get("title"),
            content_hash=content_hash,
            dwell_ms=int(event["dwell_ms"]),
            captured_at=str(event["captured_at"]),
            metadata=event.get("metadata") or {},
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    return {
        "event_id": event_id,
        "item_id": item_id,
        "status": "queued" if created else "duplicate_event",
    }
