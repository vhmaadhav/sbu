"""Local Google Calendar OAuth and read-only event access."""
import json
import logging
import os
import time
import base64
import hashlib
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from core import db
from core.config import (
    DATA_DIR,
    GOOGLE_CALENDAR_CLIENT_ID,
    GOOGLE_CALENDAR_CLIENT_SECRET,
    GOOGLE_CALENDAR_REDIRECT_URI,
    GOOGLE_CALENDAR_TIMEZONE,
)

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TOKEN_PATH = DATA_DIR / "google_calendar_token.json"
STATES_PATH = DATA_DIR / "google_calendar_states.json"
_last_oauth_error: str | None = None


def _load_states() -> dict[str, dict]:
    """Load pending OAuth states from disk (survives server restarts).

    Each entry maps a state string to {"expires": <timestamp>, "code_verifier": <str|None>}.
    """
    if not STATES_PATH.exists():
        return {}
    try:
        data = json.loads(STATES_PATH.read_text(encoding="utf-8"))
        now = time.time()
        # Prune expired states; handle both old (float) and new (dict) formats
        cleaned = {}
        for k, v in data.items():
            if isinstance(v, dict) and v.get("expires", 0) > now:
                cleaned[k] = v
            elif isinstance(v, (int, float)) and v > now:
                cleaned[k] = {"expires": v, "code_verifier": None}
        return cleaned
    except Exception:
        return {}


def _save_states(states: dict[str, dict]) -> None:
    """Persist pending OAuth states to disk."""
    STATES_PATH.write_text(json.dumps(states), encoding="utf-8")


def is_configured() -> bool:
    return bool(GOOGLE_CALENDAR_CLIENT_ID and GOOGLE_CALENDAR_CLIENT_SECRET)


def _client_config() -> dict:
    return {
        "web": {
            "client_id": GOOGLE_CALENDAR_CLIENT_ID,
            "client_secret": GOOGLE_CALENDAR_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_CALENDAR_REDIRECT_URI],
        }
    }


def _flow(state: str | None = None, code_verifier: str | None = None):
    from google_auth_oauthlib.flow import Flow

    # OAuthlib permits HTTP only for loopback development redirects.
    if GOOGLE_CALENDAR_REDIRECT_URI.startswith("http://localhost"):
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    # Google can return previously granted OpenID identity scopes alongside the
    # exact Calendar scope. OAuthlib otherwise rejects the valid token response.
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    flow = Flow.from_client_config(
        _client_config(), scopes=SCOPES, state=state,
        redirect_uri=GOOGLE_CALENDAR_REDIRECT_URI,
    )
    if code_verifier:
        flow.code_verifier = code_verifier
    return flow


def authorization_url() -> str:
    if not is_configured():
        raise RuntimeError("Google Calendar credentials are not configured")
    flow = _flow()
    url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    # Store state + code_verifier so complete_authorization can use them
    states = _load_states()
    states[state] = {
        "expires": time.time() + 600,
        "code_verifier": getattr(flow, "code_verifier", None),
    }
    _save_states(states)
    log.info("Generated OAuth URL with state=%s…", state[:8])
    return url


def complete_authorization(code: str, state: str) -> None:
    global _last_oauth_error
    states = _load_states()
    entry = states.pop(state, None)
    _save_states(states)

    if entry is None or entry.get("expires", 0) < time.time():
        log.warning("OAuth state not found or expired (state=%s…). "
                    "This usually means the server was restarted between "
                    "requesting the auth URL and the callback.", state[:8])
        raise ValueError("OAuth state is invalid or expired")

    code_verifier = entry.get("code_verifier")

    # Use the Flow object for token exchange so PKCE code_verifier is included
    flow = _flow(state=state, code_verifier=code_verifier)
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        log.error("Token exchange failed: %s", exc)
        raise RuntimeError(str(exc))

    creds = flow.credentials
    _save_credentials(creds)
    _last_oauth_error = None
    log.info("Google Calendar authorization completed successfully.")


def record_oauth_error(error: Exception) -> None:
    global _last_oauth_error
    message = str(error).lower()
    if "redirect_uri_mismatch" in message:
        _last_oauth_error = "redirect_uri_mismatch"
    elif "invalid_client" in message:
        _last_oauth_error = "invalid_client"
    elif "invalid_grant" in message:
        _last_oauth_error = "invalid_grant"
    elif "scope has changed" in message:
        _last_oauth_error = "scope_mismatch"
    else:
        _last_oauth_error = type(error).__name__


def last_oauth_error() -> str | None:
    return _last_oauth_error


def _save_credentials(credentials) -> None:
    TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")
    TOKEN_PATH.chmod(0o600)


def credentials():
    global _last_oauth_error
    if not is_configured() or not TOKEN_PATH.exists():
        return None
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds.expired and creds.refresh_token:
            log.info("Access token expired, refreshing using refresh token…")
            creds.refresh(Request())
            _save_credentials(creds)
            log.info("Token refreshed successfully.")
        if not creds.valid:
            log.warning("Credentials exist but are not valid (no refresh token?).")
            _last_oauth_error = "invalid_grant"
            return None
        return creds
    except Exception as exc:
        log.warning("Failed to load/refresh Google credentials: %s", exc)
        # Record the error so the UI can show a meaningful message.
        error_msg = str(exc).lower()
        if "invalid_grant" in error_msg or "token has been expired or revoked" in error_msg:
            _last_oauth_error = "invalid_grant"
        # Keep the refresh token file on transient network/API errors so a
        # page refresh cannot silently disconnect the account.
        return None


def list_events(time_min: str, time_max: str) -> list[dict]:
    creds = credentials()
    if not creds:
        raise PermissionError("Google Calendar is not connected")
    from googleapiclient.discovery import build

    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    page_token = None
    events: list[dict] = []
    while True:
        result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=250,
            pageToken=page_token,
        ).execute()
        for event in result.get("items", []):
            start = event.get("start", {})
            end = event.get("end", {})
            private = event.get("extendedProperties", {}).get("private", {})
            events.append({
                "id": event.get("id"),
                "summary": event.get("summary") or "Untitled event",
                "description": event.get("description") or "",
                "location": event.get("location") or "",
                "start": start.get("dateTime") or start.get("date"),
                "end": end.get("dateTime") or end.get("date"),
                "all_day": "date" in start,
                "html_link": event.get("htmlLink"),
                "attendees": [
                    {
                        "email": attendee.get("email"),
                        "display_name": attendee.get("displayName"),
                        "response_status": attendee.get("responseStatus"),
                    }
                    for attendee in event.get("attendees", [])
                    if not attendee.get("self")
                ],
                "recurring_event_id": event.get("recurringEventId"),
                "agent_movable": (
                    private.get("studyBuddyMovable") == "true"
                    if "studyBuddyMovable" in private else None
                ),
            })
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return events


def _google_event_id(reminder_id: int) -> str:
    digest = hashlib.sha256(f"study-buddy-reminder-{reminder_id}".encode()).digest()
    return "sb" + base64.b32hexencode(digest).decode().lower().rstrip("=")[:30]


def create_reminder(reminder: dict) -> str:
    creds = credentials()
    if not creds:
        raise PermissionError("Google Calendar is not connected")
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    event_date = date.fromisoformat(reminder["event_date"])
    if reminder["all_day"]:
        start = {"date": event_date.isoformat()}
        end = {"date": (event_date + timedelta(days=1)).isoformat()}
        reminder_minutes = 24 * 60
    else:
        zone = ZoneInfo(GOOGLE_CALENDAR_TIMEZONE)
        start_value = datetime.combine(
            event_date, datetime.strptime(reminder["start_time"], "%H:%M").time(), zone,
        )
        if reminder.get("end_time"):
            end_value = datetime.combine(
                event_date, datetime.strptime(reminder["end_time"], "%H:%M").time(), zone,
            )
            if end_value <= start_value:
                end_value += timedelta(days=1)
        else:
            end_value = start_value + timedelta(hours=1)
        start = {"dateTime": start_value.isoformat(), "timeZone": GOOGLE_CALENDAR_TIMEZONE}
        end = {"dateTime": end_value.isoformat(), "timeZone": GOOGLE_CALENDAR_TIMEZONE}
        reminder_minutes = 30

    event_id = _google_event_id(reminder["id"])
    body = {
        "id": event_id,
        "summary": reminder["title"],
        "description": reminder.get("description") or "Detected from Study Buddy notes.",
        "start": start,
        "end": end,
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": reminder_minutes}],
        },
        "extendedProperties": {"private": {"studyBuddyReminderId": str(reminder["id"])}},
    }
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    try:
        created = service.events().insert(calendarId="primary", body=body).execute()
        return created.get("id") or event_id
    except HttpError as error:
        if error.resp.status == 409:
            return event_id
        raise


def create_task_event(task: dict, event_date: date) -> str:
    """Create one idempotent, all-day calendar event for a confirmed task."""
    creds = credentials()
    if not creds:
        raise PermissionError("Google Calendar is not connected")
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    event_id = "sbt" + base64.b32hexencode(
        hashlib.sha256(f"study-buddy-task-{task['id']}".encode()).digest()
    ).decode().lower().rstrip("=")[:29]
    body = {
        "id": event_id,
        "summary": task["label"],
        "description": "Added from a confirmed Study Buddy task.",
        "start": {"date": event_date.isoformat()},
        "end": {"date": (event_date + timedelta(days=1)).isoformat()},
        "extendedProperties": {"private": {"studyBuddyTaskId": str(task["id"])}},
    }
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    try:
        created = service.events().insert(calendarId="primary", body=body).execute()
        return created.get("id") or event_id
    except HttpError as error:
        if error.resp.status == 409:
            return event_id
        raise


def sync_pending_reminders() -> dict:
    if not credentials():
        return {"created": 0, "pending": len(db.list_pending_calendar_reminders())}
    created = 0
    for reminder in db.list_pending_calendar_reminders():
        try:
            event_id = create_reminder(reminder)
            db.set_calendar_reminder_result(reminder["id"], event_id)
            created += 1
        except Exception as error:
            db.set_calendar_reminder_result(reminder["id"], None, str(error)[:500])
    return {"created": created, "pending": len(db.list_pending_calendar_reminders())}


def apply_reschedule_plan(plan: dict, reminder: dict) -> str:
    """Move events and create the captured event, rolling moves back on failure."""
    if plan.get("blocked"):
        raise ValueError("This plan still contains fixed conflicts")
    creds = credentials()
    if not creds:
        raise PermissionError("Google Calendar is not connected")
    from googleapiclient.discovery import build

    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    applied: list[dict] = []
    try:
        for move in plan.get("moves", []):
            current = service.events().get(
                calendarId="primary", eventId=move["event_id"],
            ).execute()
            current_start = current.get("start", {}).get("dateTime")
            current_end = current.get("end", {}).get("dateTime")
            if not current_start or not current_end:
                raise RuntimeError(f"{move['summary']} is no longer a timed event")
            if (
                datetime.fromisoformat(current_start).astimezone(timezone.utc)
                != datetime.fromisoformat(move["old_start"]).astimezone(timezone.utc)
                or datetime.fromisoformat(current_end).astimezone(timezone.utc)
                != datetime.fromisoformat(move["old_end"]).astimezone(timezone.utc)
            ):
                raise RuntimeError(
                    f"{move['summary']} changed after this plan was prepared; create a new plan"
                )
            original_private = current.get("extendedProperties", {}).get("private", {})
            body = {
                "start": {
                    "dateTime": move["new_start"],
                    "timeZone": GOOGLE_CALENDAR_TIMEZONE,
                },
                "end": {
                    "dateTime": move["new_end"],
                    "timeZone": GOOGLE_CALENDAR_TIMEZONE,
                },
                "extendedProperties": {
                    "private": {
                        **original_private,
                        "studyBuddyManaged": "true",
                        "studyBuddyOriginalStart": move["old_start"],
                        "studyBuddyOriginalEnd": move["old_end"],
                    }
                },
            }
            service.events().patch(
                calendarId="primary", eventId=move["event_id"],
                body=body, sendUpdates="none",
            ).execute()
            applied.append({**move, "_original_private": original_private})
        return create_reminder(reminder)
    except Exception:
        for move in reversed(applied):
            try:
                service.events().patch(
                    calendarId="primary", eventId=move["event_id"],
                    body={
                        "start": {
                            "dateTime": move["old_start"],
                            "timeZone": GOOGLE_CALENDAR_TIMEZONE,
                        },
                        "end": {
                            "dateTime": move["old_end"],
                            "timeZone": GOOGLE_CALENDAR_TIMEZONE,
                        },
                        "extendedProperties": {
                            "private": move["_original_private"],
                        },
                    },
                    sendUpdates="none",
                ).execute()
            except Exception:
                log.exception("Could not roll back calendar event %s", move["event_id"])
        raise


def auto_reschedule_reminder(reminder_id: int) -> dict | None:
    """Apply a routine plan during ingestion; persist complex plans for review."""
    if not credentials():
        return None
    from core import calendar_planner

    reminder = db.get_calendar_reminder(reminder_id)
    if not reminder or reminder["status"] != "proposed":
        return None
    zone = ZoneInfo(GOOGLE_CALENDAR_TIMEZONE)
    event_day = datetime.fromisoformat(reminder["event_date"]).date()
    start = datetime.combine(event_day, datetime.min.time(), zone)
    events = list_events(start.isoformat(), (start + timedelta(days=8)).isoformat())
    plan = calendar_planner.build_plan(reminder, events)
    plan_id = db.add_reschedule_plan(reminder_id, plan)
    if plan["needs_confirmation"] or plan["blocked"]:
        return {"plan_id": plan_id, "applied": False, **plan}
    event_id = apply_reschedule_plan(plan, reminder)
    db.set_calendar_reminder_result(reminder_id, event_id)
    db.set_reschedule_plan_status(plan_id, "applied")
    return {"plan_id": plan_id, "applied": True, **plan}


def disconnect() -> None:
    if TOKEN_PATH.exists():
        try:
            token = json.loads(TOKEN_PATH.read_text(encoding="utf-8")).get("token")
            if token:
                import requests
                requests.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": token},
                    headers={"content-type": "application/x-www-form-urlencoded"},
                    timeout=10,
                )
        finally:
            TOKEN_PATH.unlink(missing_ok=True)
