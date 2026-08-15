"""One sentence for the speech bubble.

The model writes the words; this module guarantees their shape. Every path,
including the model's, goes through sanitize, and anything that comes back
unusable falls through to a canned pool so the pet is never speechless.
"""
import random
import re

from core import llm

from pet.models import ContextSnapshot, NudgeEvent, Stage

MAX_CHARS = 120
# Measured against qwen3-4b on this machine: 1.5s fell back to canned lines
# often enough to be noticeable. Must stay comfortably under one poll so a slow
# model delays a bubble rather than stalling the loop.
TIMEOUT = 2.5

CANNED: dict[str, tuple[str, ...]] = {
    Stage.CONCERNED.value: (
        "That doesn't look like studying.",
        "Just checking: is this on the syllabus?",
        "One more video, was it?",
    ),
    Stage.NAG.value: (
        "Your notes are still open, you know.",
        "This is the part where you go back.",
        "The deadline is not moving for either of us.",
    ),
    Stage.PLEAD.value: (
        "Please. Ten minutes of real work.",
        "I'm not going anywhere until you do.",
        "We both know how this ends.",
    ),
    "recovered": (
        "There we go.",
        "Good. I'll be quiet now.",
        "That's more like it.",
    ),
}

# Small local models happily answer with a paraphrase of their own instructions
# ("I am warm and a little pointed..."), so the tone is described in the third
# person and the reply format is stated last, where it sticks best.
_TONE = (
    "A small desktop pet nudges a student back to studying. It speaks warmly, "
    "with a light edge, and never insults the student. It refers only to the "
    "activity and coursework it is given.\n\n"
    "Write the single sentence the pet says out loud. Under 90 characters. "
    "No markdown, no quotes, no emoji, no preamble, no mention of these "
    "instructions. Reply with that sentence and nothing else."
)

_STAGE_INTENT = {
    Stage.CONCERNED.value: "You just noticed the drift. Be light and specific about it.",
    Stage.NAG.value: "The drift has gone on. Name what is actually due or weak.",
    Stage.PLEAD.value: "You have been ignored for a while. Be plaintive, not angry.",
    "recovered": "The student came back to work. Acknowledge it briefly and warmly.",
}

_MARKDOWN = re.compile(r"[*_`#>\[\]]")


def sanitize(text: str) -> str:
    cleaned = _MARKDOWN.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.strip("\"'").strip()
    if len(cleaned) <= MAX_CHARS:
        return cleaned
    clipped = cleaned[:MAX_CHARS]
    spaced = clipped.rsplit(" ", 1)[0]
    return (spaced if spaced else clipped).strip()


def _pool_key(event: NudgeEvent) -> str:
    return "recovered" if event.recovered else event.stage.value


def _prompt(event: NudgeEvent, context: ContextSnapshot) -> str:
    sample = event.sample
    lines = [
        _STAGE_INTENT.get(_pool_key(event), _STAGE_INTENT[Stage.NAG.value]),
        "",
        f"Right now the student is in: {sample.app}",
    ]
    if sample.host:
        lines.append(f"Website: {sample.host}")
    if sample.tab_title:
        lines.append(f"Page: {sample.tab_title}")
    elif sample.title:
        lines.append(f"Window: {sample.title}")
    if context.next_deadline:
        lines.append(f"Nearest commitment: {context.next_deadline}")
    if context.weakest_concepts:
        lines.append(f"Weakest topics: {', '.join(context.weakest_concepts)}")
    if context.open_task_count:
        lines.append(f"Open tasks: {context.open_task_count}")
    return "\n".join(lines)


def line(event: NudgeEvent, context: ContextSnapshot, rng=random) -> str:
    key = _pool_key(event)
    try:
        raw = llm.chat(
            _TONE,
            _prompt(event, context),
            temperature=0.8,
            max_tokens=60,
            timeout=TIMEOUT,
        )
        spoken = sanitize(raw)
        if spoken:
            return spoken
    except Exception:
        pass
    return rng.choice(CANNED.get(key, CANNED[Stage.NAG.value]))
