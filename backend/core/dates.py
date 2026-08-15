"""Shared parsing helpers for capture and task dates."""
import re
from datetime import date, datetime, timedelta


def capture_date_from_text(text: str) -> str:
    """Resolve a date mentioned in capture context, defaulting to local today."""
    today = date.today()
    lowered = text.lower()
    if re.search(r"\byesterday(?:'s|’s)?\b", lowered):
        return (today - timedelta(days=1)).isoformat()
    if re.search(r"\btoday(?:'s|’s)?\b", lowered):
        return today.isoformat()

    iso = re.search(r"\b(\d{4}-\d{1,2}-\d{1,2})\b", text)
    if iso:
        try:
            return datetime.strptime(iso.group(1), "%Y-%m-%d").date().isoformat()
        except ValueError:
            pass

    numeric = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
    if numeric:
        try:
            return date(int(numeric.group(3)), int(numeric.group(2)), int(numeric.group(1))).isoformat()
        except ValueError:
            pass

    month_names = (
        r"January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    )
    written = re.search(
        rf"\b(?:({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?|"
        rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names}))[,]?\s+(\d{{4}})\b",
        text,
        re.IGNORECASE,
    )
    if written:
        month = written.group(1) or written.group(4)
        day = written.group(2) or written.group(3)
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(f"{day} {month} {written.group(5)}", fmt).date().isoformat()
            except ValueError:
                pass
    return today.isoformat()


def event_date_from_due_text(text: str) -> date | None:
    """Parse a task date without silently treating unknown text as today."""
    lowered = text.lower()
    today = date.today()
    if re.search(r"\btoday\b", lowered):
        return today
    if re.search(r"\btomorrow\b", lowered):
        return today + timedelta(days=1)
    iso = re.search(r"\b(\d{4}-\d{1,2}-\d{1,2})\b", text)
    if iso:
        try:
            return date.fromisoformat(iso.group(1))
        except ValueError:
            return None
    numeric = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
    if numeric:
        try:
            return date(int(numeric.group(3)), int(numeric.group(2)), int(numeric.group(1)))
        except ValueError:
            return None
    written = re.search(r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?(?:[,]?\s+(\d{4}))?\b", text)
    if written:
        year = int(written.group(3) or today.year)
        parsed = None
        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                parsed = datetime.strptime(
                    f"{written.group(1)} {written.group(2)} {year}", fmt
                ).date()
                break
            except ValueError:
                pass
        if parsed is None:
            return None
        return parsed.replace(year=parsed.year + 1) if not written.group(3) and parsed < today else parsed
    return None
