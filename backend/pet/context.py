"""What the user is supposed to be studying, read from the backend.

The pet runs natively while the backend may run in a container, so this talks
HTTP rather than importing core.db. Every call degrades to nothing: an
unconfigured Google Calendar, an absent learning goal and a stopped backend all
produce a smaller snapshot, never an exception.
"""
import time
from datetime import datetime, timedelta, timezone

import httpx

from core.config import PET_BACKEND_URL

from pet.models import ContextSnapshot

CALENDAR_WINDOW_DAYS = 8
MAX_CONCEPTS = 3
TIMEOUT = 3.0


def _parse_when(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _describe(label: str, when: datetime, now: datetime) -> str:
    days = (when.date() - now.date()).days
    if days <= 0:
        return f"{label} today"
    if days == 1:
        return f"{label} tomorrow"
    return f"{label} in {days} days"


class ContextFetcher:
    def __init__(
        self,
        base_url: str | None = None,
        refresh_seconds: float = 300.0,
        client=None,
        clock=time.monotonic,
        now=lambda: datetime.now(timezone.utc),
    ):
        self._base_url = (base_url or PET_BACKEND_URL).rstrip("/")
        self._refresh_seconds = refresh_seconds
        self._client = client or httpx.Client(timeout=TIMEOUT)
        self._clock = clock
        self._now = now
        self._snapshot = ContextSnapshot()
        self._fetched_at: float | None = None

    def snapshot(self) -> ContextSnapshot:
        current = self._clock()
        if (
            self._fetched_at is None
            or current - self._fetched_at >= self._refresh_seconds
        ):
            self._snapshot = self._fetch()
            self._fetched_at = current
        return self._snapshot

    def _get(self, path: str, params: dict | None = None):
        response = self._client.get(
            f"{self._base_url}{path}", params=params, timeout=TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    def _tasks(self, now: datetime) -> tuple[int, list[tuple[datetime, str]]]:
        try:
            payload = self._get("/api/tasks")
        except Exception:
            return 0, []
        if not isinstance(payload, list):
            return 0, []
        open_tasks = [
            row for row in payload
            if isinstance(row, dict) and not row.get("done")
        ]
        deadlines = []
        for row in open_tasks:
            when = _parse_when(row.get("due"))
            label = str(row.get("label") or "").strip()
            if when and label and when.date() >= now.date():
                deadlines.append((when, label))
        return len(open_tasks), deadlines

    def _gaps(self) -> tuple[str, ...]:
        try:
            payload = self._get("/api/learn/gaps")
        except Exception:
            return ()
        if not isinstance(payload, dict):
            return ()
        rows = payload.get("gaps")
        if not isinstance(rows, list):
            return ()
        names = [
            str(row["name"]).strip()
            for row in rows
            if isinstance(row, dict) and str(row.get("name") or "").strip()
        ]
        return tuple(names[:MAX_CONCEPTS])

    def _events(self, now: datetime) -> list[tuple[datetime, str]]:
        params = {
            "time_min": now.isoformat(),
            "time_max": (now + timedelta(days=CALENDAR_WINDOW_DAYS)).isoformat(),
        }
        try:
            payload = self._get("/api/calendar/google/events", params)
        except Exception:
            return []
        if not isinstance(payload, list):
            return []
        events = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            start = row.get("start")
            if isinstance(start, dict):
                start = start.get("dateTime") or start.get("date")
            when = _parse_when(start)
            label = str(row.get("summary") or "").strip()
            if when and label and when.date() >= now.date():
                events.append((when, label))
        return events

    def _fetch(self) -> ContextSnapshot:
        now = self._now()
        open_task_count, task_deadlines = self._tasks(now)
        concepts = self._gaps()
        deadlines = task_deadlines + self._events(now)
        next_deadline = None
        if deadlines:
            when, label = min(deadlines, key=lambda row: row[0])
            next_deadline = _describe(label, when, now)
        return ContextSnapshot(
            next_deadline=next_deadline,
            open_task_count=open_task_count,
            weakest_concepts=concepts,
        )
