"""Policy-bounded calendar conflict planning.

The planner is deliberately deterministic. The local LLM extracts events, while
this module owns the safety rules that decide what may move.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from core.config import GOOGLE_CALENDAR_TIMEZONE

WORKDAY_START = time(7, 0)
WORKDAY_END = time(22, 0)
SEARCH_DAYS = 7
SLOT_MINUTES = 30

HIGH_PRIORITY_WORDS = {
    "exam": 95, "test": 90, "interview": 90, "flight": 95,
    "medical": 95, "doctor": 95, "appointment": 80, "deadline": 85,
    "class": 70, "meeting": 65, "lecture": 65,
}
LOW_PRIORITY_WORDS = {
    "reminder": 25, "study": 45, "focus": 40, "workout": 35,
    "exercise": 35, "reading": 30, "errand": 30,
}
PROTECTED_WORDS = ("flight", "doctor", "medical", "interview", "wedding", "funeral")


def _parse(value: str, zone: ZoneInfo) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=zone) if parsed.tzinfo is None else parsed.astimezone(zone)


def priority_for(title: str, default: int = 60) -> int:
    lowered = title.casefold()
    scores = [
        score for word, score in {**LOW_PRIORITY_WORDS, **HIGH_PRIORITY_WORDS}.items()
        if word in lowered
    ]
    return max(scores) if scores else default


def _overlaps(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> bool:
    return start < other_end and end > other_start


def _event_interval(event: dict, zone: ZoneInfo) -> tuple[datetime, datetime] | None:
    if event.get("all_day") or not event.get("start") or not event.get("end"):
        return None
    return _parse(event["start"], zone), _parse(event["end"], zone)


def _event_policy(event: dict) -> dict:
    attendees = event.get("attendees") or []
    title = event.get("summary") or "Untitled event"
    protected = (
        bool(event.get("recurring_event_id"))
        or bool(attendees)
        or any(word in title.casefold() for word in PROTECTED_WORDS)
        or event.get("agent_movable") is False
    )
    return {
        "priority": priority_for(title),
        "movable": not protected,
        "reason": (
            "has other attendees" if attendees else
            "is recurring" if event.get("recurring_event_id") else
            "is protected by scheduling policy" if protected else
            "is a flexible solo event"
        ),
    }


def _candidate_slots(
    original_start: datetime, duration: timedelta, occupied: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    zone = original_start.tzinfo
    candidates: list[tuple[datetime, datetime]] = []
    for day_offset in range(SEARCH_DAYS + 1):
        day = (original_start + timedelta(days=day_offset)).date()
        cursor = datetime.combine(day, WORKDAY_START, zone)
        day_end = datetime.combine(day, WORKDAY_END, zone)
        if day_offset == 0:
            cursor = max(cursor, original_start + timedelta(minutes=SLOT_MINUTES))
            minutes = cursor.minute % SLOT_MINUTES
            if minutes:
                cursor += timedelta(minutes=SLOT_MINUTES - minutes)
            cursor = cursor.replace(second=0, microsecond=0)
        while cursor + duration <= day_end:
            end = cursor + duration
            if not any(_overlaps(cursor, end, start, finish) for start, finish in occupied):
                candidates.append((cursor, end))
            cursor += timedelta(minutes=SLOT_MINUTES)
    return candidates


def build_plan(reminder: dict, events: list[dict]) -> dict:
    """Return a serializable proposal that creates one event and moves conflicts."""
    zone = ZoneInfo(GOOGLE_CALENDAR_TIMEZONE)
    event_day = datetime.fromisoformat(reminder["event_date"]).date()
    all_day = bool(reminder.get("all_day"))
    if all_day:
        new_start = datetime.combine(event_day, time.min, zone)
        new_end = new_start + timedelta(days=1)
    else:
        new_start = datetime.combine(
            event_day, datetime.strptime(reminder["start_time"], "%H:%M").time(), zone
        )
        end_text = reminder.get("end_time")
        new_end = datetime.combine(
            event_day,
            datetime.strptime(end_text, "%H:%M").time() if end_text else
            (new_start + timedelta(hours=1)).time(),
            zone,
        )
        if new_end <= new_start:
            new_end += timedelta(days=1)

    timed = [(event, _event_interval(event, zone)) for event in events]
    timed = [(event, interval) for event, interval in timed if interval]
    conflicts = [
        (event, interval) for event, interval in timed
        if not all_day and _overlaps(new_start, new_end, interval[0], interval[1])
    ]

    moves: list[dict] = []
    blocked: list[dict] = []
    new_priority = priority_for(reminder["title"])
    occupied = [
        interval for event, interval in timed
        if not any(event.get("id") == conflict.get("id") for conflict, _ in conflicts)
    ]
    occupied.append((new_start, new_end))

    # Lowest-priority flexible work moves first, allowing higher-value events to
    # retain the closest replacement slots.
    for event, (old_start, old_end) in sorted(
        conflicts, key=lambda pair: _event_policy(pair[0])["priority"]
    ):
        policy = _event_policy(event)
        if not policy["movable"] or policy["priority"] >= new_priority:
            reason = (
                policy["reason"] if not policy["movable"]
                else "has the same or higher priority"
            )
            blocked.append({
                "event_id": event["id"], "summary": event["summary"],
                "reason": reason, "start": old_start.isoformat(),
                "end": old_end.isoformat(),
            })
            occupied.append((old_start, old_end))
            continue
        slots = _candidate_slots(old_start, old_end - old_start, occupied)
        if not slots:
            blocked.append({
                "event_id": event["id"], "summary": event["summary"],
                "reason": "has no open slot in the next seven days",
                "start": old_start.isoformat(), "end": old_end.isoformat(),
            })
            occupied.append((old_start, old_end))
            continue
        new_slot = slots[0]
        occupied.append(new_slot)
        moves.append({
            "event_id": event["id"],
            "summary": event["summary"],
            "priority": policy["priority"],
            "reason": policy["reason"],
            "old_start": old_start.isoformat(),
            "old_end": old_end.isoformat(),
            "new_start": new_slot[0].isoformat(),
            "new_end": new_slot[1].isoformat(),
            "crosses_day": new_slot[0].date() != old_start.date(),
        })

    complex_reasons = []
    if blocked:
        complex_reasons.append("one or more fixed conflicts need a decision")
    if any(move["crosses_day"] for move in moves):
        complex_reasons.append("an event moves to another day")
    if len(moves) > 3:
        complex_reasons.append("more than three events would move")

    return {
        "reminder_id": reminder["id"],
        "new_event": {
            "title": reminder["title"],
            "start": new_start.isoformat(),
            "end": new_end.isoformat(),
            "all_day": all_day,
            "source": reminder.get("filename"),
        },
        "moves": moves,
        "blocked": blocked,
        "needs_confirmation": bool(complex_reasons),
        "complex_reasons": complex_reasons,
        "summary": (
            f"Add {reminder['title']} and move {len(moves)} event"
            f"{'' if len(moves) == 1 else 's'}"
        ),
    }
