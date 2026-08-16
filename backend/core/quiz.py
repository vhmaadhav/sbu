"""On-demand multiple-choice generation, grading, and misconception logging.

Every distractor carries a misconception label written at generation time, so
grouping repeated errors is a plain GROUP BY rather than a second inference pass,
and the student can be told *why* they were wrong the instant they answer.
"""
from __future__ import annotations

import json
import logging
import random
import time

from core import concepts, db, llm, mastery

logger = logging.getLogger(__name__)

OPTION_COUNT = 4
CONTEXT_CHARS = 2400

QUESTION_SYSTEM = """You write one exam-quality multiple-choice question at a time.

Return one JSON object with this exact shape:
{"stem": "The question.",
 "options": [{"text": "An answer", "correct": true, "misconception": ""},
             {"text": "A wrong answer", "correct": false,
              "misconception": "short label for the specific error this represents"}],
 "explanation": "Two sentences on why the correct answer is correct."}

Rules:
- Exactly four options. Exactly one has "correct": true.
- Every wrong option needs a "misconception": a short, reusable label naming the
  error a student makes when they pick it, such as "confuses velocity with
  acceleration" or "forgets to convert units". Never leave it empty.
- The correct option's "misconception" is an empty string.
- Wrong options must be plausible, similar in length and form to the correct one.
- The question must be answerable from the supplied source notes alone. Never test
  a fact, formula, or case the notes do not contain, even if it is standard for
  the subject.
- Test understanding, not recall of trivia.
"""


def _context_for(concept_id: int) -> tuple[str, list[dict]]:
    chunks = concepts.source_chunks(concept_id)
    if not chunks:
        return "", []
    blocks, used, budget = [], [], CONTEXT_CHARS
    for chunk in chunks:
        text = (chunk["text"] or "")[:budget]
        if not text:
            break
        blocks.append(f"[{chunk['source_label']}]\n{text}")
        used.append(chunk)
        budget -= len(text)
        if budget <= 0:
            break
    return "\n\n---\n\n".join(blocks), used


def _parse(payload: dict) -> dict:
    options = payload.get("options") or []
    cleaned = []
    for option in options:
        if not isinstance(option, dict):
            continue
        text = str(option.get("text") or "").strip()
        if not text:
            continue
        cleaned.append({
            "text": text[:300],
            "correct": bool(option.get("correct")),
            "misconception": str(option.get("misconception") or "").strip()[:120],
        })
    correct = [o for o in cleaned if o["correct"]]
    if len(cleaned) < 2 or len(correct) != 1:
        raise ValueError("the model did not return exactly one correct option")

    cleaned = cleaned[:OPTION_COUNT]
    if not any(o["correct"] for o in cleaned):  # truncation dropped the answer
        cleaned = cleaned[: OPTION_COUNT - 1] + [correct[0]]

    # Shuffle so the answer is not always in the position the model emitted it.
    random.shuffle(cleaned)
    for option in cleaned:
        if not option["correct"] and not option["misconception"]:
            option["misconception"] = "unclassified error"

    stem = str(payload.get("stem") or "").strip()
    if not stem:
        raise ValueError("the model returned no question stem")
    return {
        "stem": stem[:600],
        "options": cleaned,
        "answer_index": next(i for i, o in enumerate(cleaned) if o["correct"]),
        "explanation": str(payload.get("explanation") or "").strip()[:800],
    }


def _persist(concept_id: int, parsed: dict) -> int:
    with db.conn() as c:
        return c.execute(
            "INSERT INTO questions (concept_id, stem, options_json, answer_index, "
            "explanation, created_at) VALUES (?,?,?,?,?,?)",
            (
                concept_id,
                parsed["stem"],
                json.dumps(parsed["options"]),
                parsed["answer_index"],
                parsed["explanation"],
                time.time(),
            ),
        ).lastrowid


def generate(concept_id: int) -> int:
    """Write one new question for a concept and return its id."""
    concept = concepts.get_concept(concept_id)
    if concept is None:
        raise ValueError(f"unknown concept {concept_id}")
    context, _ = _context_for(concept_id)
    if not context:
        # Without the student's own notes there is nothing legitimate to test, and
        # inventing a question from general knowledge is exactly what this must not do.
        raise ValueError(f"concept {concept_id} has no source notes to write from")

    prompt = (
        f"Concept: {concept['name']}\n{concept['blurb']}\n\n"
        f"Source notes:\n\n{context}"
    )
    payload = llm.chat_json(QUESTION_SYSTEM, prompt, max_tokens=900)
    return _persist(concept_id, _parse(payload))


def _cached_question_id(concept_id: int, exclude: list[int] | None = None) -> int | None:
    clause, params = "", [concept_id]
    if exclude:
        clause = " AND id NOT IN (" + ",".join("?" * len(exclude)) + ")"
        params += exclude
    with db.conn() as c:
        row = c.execute(
            f"SELECT id FROM questions WHERE concept_id=?{clause} "
            "ORDER BY created_at DESC LIMIT 1",
            params,
        ).fetchone()
    return row["id"] if row else None


def question_for(concept_id: int, exclude: list[int] | None = None) -> int | None:
    """A question id for this concept: freshly generated, or the best cached fallback.

    Generation is retried once. If the LLM is unreachable entirely, a previously
    cached question keeps the session moving; if there is none, the caller skips
    this item rather than stalling.
    """
    for attempt in range(2):
        try:
            return generate(concept_id)
        except Exception:
            logger.warning(
                "question generation failed (attempt %d) for concept %s",
                attempt + 1, concept_id,
            )
    return _cached_question_id(concept_id, exclude)


def get_question(question_id: int, reveal: bool = False) -> dict | None:
    """A question shaped for the client. Without `reveal`, answers are withheld."""
    with db.conn() as c:
        row = c.execute(
            "SELECT q.*, c.name AS concept_name FROM questions q "
            "JOIN concepts c ON c.id = q.concept_id WHERE q.id=?",
            (question_id,),
        ).fetchone()
    if row is None:
        return None
    options = json.loads(row["options_json"])
    payload = {
        "id": row["id"],
        "concept_id": row["concept_id"],
        "concept_name": row["concept_name"],
        "stem": row["stem"],
        "options": [option["text"] for option in options],
    }
    if reveal:
        payload["answer_index"] = row["answer_index"]
        payload["explanation"] = row["explanation"]
        payload["misconceptions"] = [option["misconception"] for option in options]
    return payload


def grade(question_id: int, chosen_index: int, session_id: int | None = None,
          latency_ms: int = 0) -> dict:
    """Grade an answer, log the attempt, and run the BKT update for its concept."""
    with db.conn() as c:
        row = c.execute("SELECT * FROM questions WHERE id=?", (question_id,)).fetchone()
    if row is None:
        raise ValueError(f"unknown question {question_id}")

    options = json.loads(row["options_json"])
    correct = chosen_index == row["answer_index"]
    misconception = None
    if not correct and 0 <= chosen_index < len(options):
        misconception = options[chosen_index]["misconception"] or None

    with db.conn() as c:
        c.execute(
            "INSERT INTO attempts (session_id, question_id, concept_id, chosen_index, "
            "correct, misconception, latency_ms, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (session_id, question_id, row["concept_id"], chosen_index,
             1 if correct else 0, misconception, latency_ms, time.time()),
        )
        if session_id is not None:
            c.execute(
                "UPDATE session_items SET done=1 WHERE session_id=? AND question_id=?",
                (session_id, question_id),
            )

    state = mastery.apply_attempt(row["concept_id"], correct)
    return {
        "correct": correct,
        "answer_index": row["answer_index"],
        "explanation": row["explanation"],
        "misconception": misconception,
        "concept_id": row["concept_id"],
        "p_known": state.p_known,
        "attempts": state.attempts,
        "in_srs": state.in_srs,
    }


def misconception_counts(goal_id: int, limit: int = 12) -> list[dict]:
    """Repeated errors grouped into misconceptions, most frequent first."""
    with db.conn() as c:
        rows = c.execute(
            "SELECT a.misconception AS tag, COUNT(*) AS count, "
            "       COUNT(DISTINCT a.concept_id) AS concepts, "
            "       MAX(a.created_at) AS last_seen, "
            "       GROUP_CONCAT(DISTINCT c.name) AS concept_names "
            "FROM attempts a JOIN concepts c ON c.id = a.concept_id "
            "WHERE c.goal_id=? AND a.correct=0 AND a.misconception IS NOT NULL "
            "GROUP BY a.misconception ORDER BY count DESC, last_seen DESC LIMIT ?",
            (goal_id, limit),
        ).fetchall()
    return [
        {
            "tag": row["tag"],
            "count": row["count"],
            "concepts": row["concepts"],
            "concept_names": (row["concept_names"] or "").split(","),
            "last_seen": row["last_seen"],
        }
        for row in rows
    ]
