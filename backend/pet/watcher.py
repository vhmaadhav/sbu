"""What is in front of the user right now.

Cocoa gives the frontmost application; the active tab needs AppleScript, which
the user must approve once per browser. Every failure here is expected at some
point — permission denied, no window open, a browser mid-launch — so this
module never raises: it returns a smaller sample and lets the classifier work
with the app name alone.
"""
import subprocess
from urllib.parse import urlparse

from pet.models import ActivitySample

SEPARATOR = "\t"
APPLESCRIPT_TIMEOUT = 2.0

BROWSER_SCRIPTS: dict[str, str] = {
    "Safari": (
        'tell application "Safari"\n'
        "  set t to name of current tab of front window\n"
        "  set u to URL of current tab of front window\n"
        "  return t & (ASCII character 9) & u\n"
        "end tell"
    ),
    "Google Chrome": (
        'tell application "Google Chrome"\n'
        "  set t to title of active tab of front window\n"
        "  set u to URL of active tab of front window\n"
        "  return t & (ASCII character 9) & u\n"
        "end tell"
    ),
    "Arc": (
        'tell application "Arc"\n'
        "  set t to title of active tab of front window\n"
        "  set u to URL of active tab of front window\n"
        "  return t & (ASCII character 9) & u\n"
        "end tell"
    ),
    "Brave Browser": (
        'tell application "Brave Browser"\n'
        "  set t to title of active tab of front window\n"
        "  set u to URL of active tab of front window\n"
        "  return t & (ASCII character 9) & u\n"
        "end tell"
    ),
}


def parse_tab_output(raw: str) -> tuple[str | None, str | None]:
    text = (raw or "").strip()
    if not text or SEPARATOR not in text:
        return None, None
    title, _, url = text.rpartition(SEPARATOR)
    title = title.strip()
    url = url.strip()
    return (title or None), (url or None)


def host_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def _run_applescript(script: str) -> str:
    completed = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=APPLESCRIPT_TIMEOUT,
        check=True,
    )
    return completed.stdout


def browser_tab(app: str) -> tuple[str | None, str | None]:
    """Return (tab_title, host) for a supported browser, or (None, None)."""
    script = BROWSER_SCRIPTS.get(app)
    if script is None:
        return None, None
    try:
        raw = _run_applescript(script)
    except Exception:
        return None, None
    title, url = parse_tab_output(raw)
    return title, host_of(url)


def frontmost() -> tuple[str, str]:
    """Return (application name, frontmost window title)."""
    import AppKit
    import Quartz

    application = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    name = str(application.localizedName() or "") if application else ""
    pid = int(application.processIdentifier()) if application else -1

    title = ""
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    ) or []
    for window in windows:
        if window.get("kCGWindowOwnerPID") == pid:
            title = str(window.get("kCGWindowName") or "")
            if title:
                break
    return name, title


def sample(at: float) -> ActivitySample:
    try:
        app, title = frontmost()
    except Exception:
        return ActivitySample(at=at, app="")
    tab_title, host = browser_tab(app)
    return ActivitySample(at=at, app=app, title=title, host=host, tab_title=tab_title)
