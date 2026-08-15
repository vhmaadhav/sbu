"""Label what the user is doing right now.

Rules resolve almost every sample without a model call. Anything genuinely
unknown is sent to the local LLM once and remembered for the life of the
process, so a long session costs a handful of tiny requests.
"""
from core import llm
from core.config import PET_DISTRACT_HOSTS, PET_STUDY_APPS

from pet.models import ActivitySample, Label

STUDY_APPS = frozenset({
    "Study Buddy", "Preview", "Notes", "Obsidian", "Notion", "Zotero",
    "Terminal", "iTerm2", "Ghostty", "Visual Studio Code", "PyCharm",
    "IntelliJ IDEA", "Xcode", "Books", "GoodNotes", "Anki",
})
DISTRACT_APPS = frozenset({
    "Steam", "Discord", "Messages", "WhatsApp", "Telegram", "Spotify",
    "TV", "Netflix", "Minecraft",
})
STUDY_HOSTS = frozenset({
    "wikipedia.org", "arxiv.org", "stackoverflow.com", "github.com",
    "docs.python.org", "khanacademy.org", "coursera.org", "nptel.ac.in",
    "scholar.google.com", "localhost",
})
DISTRACT_HOSTS = frozenset({
    "youtube.com", "netflix.com", "twitch.tv", "instagram.com", "tiktok.com",
    "reddit.com", "x.com", "twitter.com", "facebook.com", "primevideo.com",
    "hotstar.com", "9gag.com",
})
NEUTRAL_APPS = frozenset({"Finder", "System Settings", "loginwindow", "Dock"})

BROWSERS = frozenset({"Safari", "Google Chrome", "Arc", "Brave Browser", "Firefox"})

_VALID: frozenset[str] = frozenset({"study", "distraction", "neutral"})

_SYSTEM = (
    "You label a computer activity for a study assistant. Answer with exactly one "
    "word: study, distraction, or neutral. 'study' means learning or productive "
    "work. 'distraction' means entertainment, social media, or games. 'neutral' "
    "means you cannot tell."
)

_cache: dict[tuple[str, str | None], Label] = {}


def reset_cache() -> None:
    _cache.clear()


def normalize_host(host: str | None) -> str | None:
    if not host:
        return None
    cleaned = host.strip().lower()
    return cleaned[4:] if cleaned.startswith("www.") else cleaned


def _host_matches(host: str | None, rules: frozenset[str] | tuple[str, ...]) -> bool:
    if not host:
        return False
    return any(host == rule or host.endswith(f".{rule}") for rule in rules)


def _ask_llm(sample: ActivitySample, host: str | None) -> Label | None:
    user = "\n".join([
        f"Application: {sample.app}",
        f"Window title: {sample.title or 'unknown'}",
        f"Website: {host or 'none'}",
        f"Page title: {sample.tab_title or 'none'}",
    ])
    try:
        answer = llm.chat(_SYSTEM, user, temperature=0.0, max_tokens=8, timeout=2.0)
    except Exception:
        return None
    word = answer.strip().lower().strip(".").split()[0] if answer.strip() else ""
    return word if word in _VALID else "neutral"  # type: ignore[return-value]


def classify(sample: ActivitySample) -> Label:
    host = normalize_host(sample.host)

    # User configuration wins over everything, including the built-in tables.
    if sample.app in PET_STUDY_APPS:
        return "study"
    if _host_matches(host, PET_DISTRACT_HOSTS):
        return "distraction"

    if sample.app in NEUTRAL_APPS:
        return "neutral"
    if sample.app in DISTRACT_APPS:
        return "distraction"
    if _host_matches(host, DISTRACT_HOSTS):
        return "distraction"
    if _host_matches(host, STUDY_HOSTS):
        return "study"
    # Browsers are never in STUDY_APPS: a browser is only as studious as its tab.
    if sample.app in STUDY_APPS:
        return "study"

    key = (sample.app, host)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    verdict = _ask_llm(sample, host)
    if verdict is None:
        return "neutral"
    _cache[key] = verdict
    return verdict
