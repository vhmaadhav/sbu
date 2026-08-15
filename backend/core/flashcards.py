"""Create and persist flashcard decks requested through chat."""
from __future__ import annotations

import re
from dataclasses import dataclass

from core import db, llm, vectorstore

DEFAULT_CARD_COUNT = 10
MAX_CARD_COUNT = 30
MAX_TOPIC_LENGTH = 200

GENERATION_SYSTEM = """You create effective study flashcards.
Make each front a single, unambiguous question or prompt and each back a concise,
factually accurate answer. Cover the topic broadly without duplicate cards. When
source notes are supplied, use them as the authority. When no source notes are
supplied, use accurate general knowledge. Return one JSON object with this exact
shape: {"title": "Deck title", "cards": [{"front": "...", "back": "..."}]}.
"""

_REQUEST = re.compile(
    r"^\s*(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?"
    r"(?:(?:i\s+)?(?:want|would\s+like)\s+you\s+to\s+)?"
    r"(?:create|make|generate|build)(?:\s+me)?\s+"
    r"(?:(?:a|some)\s+)?(?:(?:set|deck|batch)\s+of\s+)?"
    r"(?:(\d+)\s+)?(?:few\s+)?flash[\s-]*cards?\b"
    r"(?:\s+for\s+me)?(?:\s+(?:about|on|for|covering)\b)?\s*(.*?)\s*[.!?]*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FlashcardRequest:
    topic: str
    count: int


def parse_request(message: str) -> FlashcardRequest | None:
    """Return a flashcard command only for explicit creation requests."""
    match = _REQUEST.match(message)
    if not match:
        return None
    raw_count, raw_topic = match.groups()
    topic = re.sub(r"^(?:about|on|for|covering)\s+", "", raw_topic, flags=re.I)
    topic = topic.strip(" \t\r\n.!?")[:MAX_TOPIC_LENGTH]
    count = int(raw_count) if raw_count else DEFAULT_CARD_COUNT
    return FlashcardRequest(topic=topic, count=max(1, min(count, MAX_CARD_COUNT)))


def _source_context(topic: str, subject: str | None) -> tuple[str, list[dict]]:
    try:
        hits = vectorstore.search(topic, subject=subject, k=10)
    except Exception:
        hits = []
    blocks = []
    sources = []
    seen = set()
    for hit in hits:
        label = str(hit["source_label"])
        blocks.append(f"[source: {label}]\n{hit['text']}")
        item_id = int(hit["item_id"])
        key = (label, item_id)
        if key not in seen:
            sources.append({
                "label": label,
                "item_id": item_id,
                "note_id": db.note_id_for_item(item_id),
            })
            seen.add(key)
    return "\n\n---\n\n".join(blocks)[:16_000], sources


def _clean_cards(payload: dict, count: int) -> list[dict]:
    raw_cards = payload.get("cards")
    if not isinstance(raw_cards, list):
        raise ValueError("The model did not return a flashcard list")
    cards = []
    seen = set()
    for raw in raw_cards:
        if not isinstance(raw, dict):
            continue
        front = str(raw.get("front", "")).strip()
        back = str(raw.get("back", "")).strip()
        key = front.casefold()
        if not front or not back or key in seen:
            continue
        cards.append({"front": front[:1000], "back": back[:2000]})
        seen.add(key)
        if len(cards) == count:
            break
    if not cards:
        raise ValueError("The model did not return any usable flashcards")
    return cards


def create_deck(request: FlashcardRequest, subject: str | None = None) -> dict:
    if not request.topic:
        raise ValueError("A topic is required to create flashcards")
    context, sources = _source_context(request.topic, subject)
    material = f"\n\nSource notes:\n{context}" if context else "\n\nNo source notes were found."
    payload = llm.chat_json(
        GENERATION_SYSTEM,
        f"Create exactly {request.count} flashcards about: {request.topic}.{material}",
        max_tokens=3000,
    )
    if not isinstance(payload, dict):
        raise ValueError("The model returned an invalid flashcard deck")
    cards = _clean_cards(payload, request.count)
    title = str(payload.get("title", "")).strip() or request.topic
    deck_id = db.create_flashcard_deck(
        title=title[:160],
        topic=request.topic,
        cards=cards,
        subject=subject,
        sources=sources,
    )
    basis = " from your notes" if sources else ""
    return {
        "answer": (
            f"Created **{title[:160]}** with {len(cards)} flashcards{basis}. "
            f"[Study the deck](/flashcards)"
        ),
        "sources": sources,
        "images": [],
        "deck_id": deck_id,
    }


def maybe_create_from_chat(message: str, subject: str | None = None) -> dict | None:
    request = parse_request(message)
    if request is None:
        return None
    if not request.topic:
        return {
            "answer": "What topic should I use for the flashcards? For example: `Create flashcards about photosynthesis`.",
            "sources": [],
            "images": [],
            "deck_id": None,
        }
    return create_deck(request, subject)
