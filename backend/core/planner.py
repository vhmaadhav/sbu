"""Session planning: what to study next, in what order.

Two builders share one queue shape. The diagnostic sweeps breadth-first across
the graph to seed mastery cheaply; the study planner puts missing prerequisites
before weak concepts before due reviews, so a student is never handed a concept
whose foundation is still missing.

Questions are generated when an item is served, and the *following* item is
generated on a background thread while the student answers — so only the first
question of a session ever waits on the model.
"""
from __future__ import annotations

import logging
import threading
import time

from core import concepts, db, gaps, mastery, quiz

logger = logging.getLogger(__name__)

DIAGNOSTIC_LENGTH = 12
SESSION_LENGTH = 8
QUIZZES_PER_PREREQUISITE = 2

# session_id -> {concept_id: question_id} produced by the prefetch thread.
_prefetched: dict[int, dict[int, int]] = {}
_prefetch_lock = threading.Lock()


# ── Queue construction ────────────────────────────────────────────────────

def _diagnostic_concepts(goal_id: int) -> list[int]:
    """One concept per tier in rotation, least-tested first within each tier."""
    nodes = concepts.graph(goal_id)["nodes"]
    if not nodes:
        return []
    by_tier: dict[int, list[dict]] = {}
    for node in nodes:
        by_tier.setdefault(node["tier"], []).append(node)
    for tier in by_tier.values():
        tier.sort(key=lambda n: (n["confidence"], -n["downstream"]))

    ordered: list[int] = []
    tiers = sorted(by_tier)
    depth = 0
    while len(ordered) < DIAGNOSTIC_LENGTH:
        added = False
        for tier in tiers:
            if depth < len(by_tier[tier]):
                ordered.append(by_tier[tier][depth]["id"])
                added = True
                if len(ordered) >= DIAGNOSTIC_LENGTH:
                    break
        if not added:
            break
        depth += 1
    return ordered


def _study_plan(goal_id: int, concept_id: int | None = None) -> list[tuple[int, str]]:
    """Ordered (concept_id, kind) pairs for a study session."""
    plan: list[tuple[int, str]] = []

    if concept_id is not None:
        plan.append((concept_id, "read"))
        plan += [(concept_id, "quiz")] * 4
        return plan[:SESSION_LENGTH]

    ranked = gaps.rank(goal_id)
    for row in ranked:
        if not row["missing_prerequisite"]:
            continue
        plan.append((row["concept_id"], "read"))
        plan += [(row["concept_id"], "quiz")] * QUIZZES_PER_PREREQUISITE
        if len(plan) >= SESSION_LENGTH:
            return plan[:SESSION_LENGTH]

    for row in ranked:
        if row["missing_prerequisite"]:
            continue
        if row["attempts"] == 0:
            plan.append((row["concept_id"], "read"))
        plan.append((row["concept_id"], "quiz"))
        if len(plan) >= SESSION_LENGTH:
            return plan[:SESSION_LENGTH]

    for row in mastery.due_queue(goal_id):
        if row["due"]:
            plan.append((row["concept_id"], "quiz"))
        if len(plan) >= SESSION_LENGTH:
            break

    if not plan:  # nothing weak and nothing due — revisit the least certain concepts
        nodes = sorted(concepts.graph(goal_id)["nodes"], key=lambda n: n["p_known"])
        plan = [(node["id"], "quiz") for node in nodes[:SESSION_LENGTH]]
    return plan[:SESSION_LENGTH]


def _create(goal_id: int, kind: str, plan: list[tuple[int, str]]) -> int:
    now = time.time()
    with db.conn() as c:
        session_id = c.execute(
            "INSERT INTO sessions (goal_id, kind, status, created_at) VALUES (?,?,?,?)",
            (goal_id, kind, "active", now),
        ).lastrowid
        c.executemany(
            "INSERT INTO session_items (session_id, position, concept_id, kind) "
            "VALUES (?,?,?,?)",
            [
                (session_id, position, concept_id, item_kind)
                for position, (concept_id, item_kind) in enumerate(plan)
            ],
        )
    return session_id


def start_diagnostic(goal_id: int) -> int:
    plan = [(concept_id, "quiz") for concept_id in _diagnostic_concepts(goal_id)]
    if not plan:
        raise ValueError("this goal has no concepts yet")
    return _create(goal_id, "diagnostic", plan)


def start_session(goal_id: int, concept_id: int | None = None) -> int:
    plan = _study_plan(goal_id, concept_id)
    if not plan:
        raise ValueError("nothing to study yet")
    return _create(goal_id, "study", plan)


# ── Serving items ─────────────────────────────────────────────────────────

def _session_row(session_id: int):
    with db.conn() as c:
        return c.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()


def _pending_items(session_id: int) -> list:
    with db.conn() as c:
        return c.execute(
            "SELECT * FROM session_items WHERE session_id=? AND done=0 ORDER BY position",
            (session_id,),
        ).fetchall()


def _take_prefetched(session_id: int, concept_id: int) -> int | None:
    with _prefetch_lock:
        return _prefetched.get(session_id, {}).pop(concept_id, None)


def _prefetch(session_id: int, concept_id: int) -> None:
    def run() -> None:
        try:
            question_id = quiz.generate(concept_id)
        except Exception:
            return  # the serving path will retry and fall back on its own
        with _prefetch_lock:
            _prefetched.setdefault(session_id, {})[concept_id] = question_id

    threading.Thread(target=run, daemon=True).start()


def _adapt(session_id: int, items: list) -> list:
    """Follow a wrong answer down to its prerequisite.

    A student who misses a concept is usually missing something underneath it,
    so the next question drops a tier rather than asking the same thing again.
    """
    with db.conn() as c:
        last = c.execute(
            "SELECT concept_id, correct FROM attempts WHERE session_id=? "
            "ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    if last is None or last["correct"]:
        return items

    prereqs = concepts.prerequisites_of(last["concept_id"])
    if not prereqs:
        return items

    states = {pid: mastery.get(pid) for pid in prereqs}
    weakest = min(
        prereqs,
        key=lambda pid: states[pid].p_known if states[pid] else mastery.P_INIT,
    )
    queued = {item["concept_id"] for item in items}
    if weakest in queued:
        return items

    with db.conn() as c:
        c.execute(
            "UPDATE session_items SET position = position + 1 "
            "WHERE session_id=? AND done=0",
            (session_id,),
        )
        first = items[0]["position"] if items else 0
        c.execute(
            "INSERT INTO session_items (session_id, position, concept_id, kind) "
            "VALUES (?,?,?,?)",
            (session_id, first, weakest, "quiz"),
        )
    return _pending_items(session_id)


def next_item(session_id: int) -> dict | None:
    """The next thing to do, or None when the session is finished."""
    session = _session_row(session_id)
    if session is None:
        raise ValueError(f"unknown session {session_id}")

    items = _pending_items(session_id)
    if session["kind"] == "diagnostic":
        items = _adapt(session_id, items)

    while items:
        item = items[0]
        concept = concepts.get_concept(item["concept_id"])
        if concept is None:
            _mark_done(item["id"])
            items = items[1:]
            continue

        if item["kind"] == "read":
            payload = {
                "item_id": item["id"],
                "kind": "read",
                "position": item["position"],
                "concept": concept,
                "sources": concepts.source_chunks(item["concept_id"]),
            }
            if len(items) > 1:  # warm the model up for the question that follows
                _prefetch(session_id, items[1]["concept_id"])
            return _with_progress(session_id, payload)

        question_id = _take_prefetched(session_id, item["concept_id"])
        if question_id is None:
            asked = _asked_question_ids(session_id)
            question_id = quiz.question_for(item["concept_id"], exclude=asked)
        if question_id is None:  # model down and nothing cached — skip, never stall
            _mark_done(item["id"])
            items = items[1:]
            continue

        with db.conn() as c:
            c.execute(
                "UPDATE session_items SET question_id=? WHERE id=?",
                (question_id, item["id"]),
            )
        if len(items) > 1:
            _prefetch(session_id, items[1]["concept_id"])

        return _with_progress(session_id, {
            "item_id": item["id"],
            "kind": "quiz",
            "position": item["position"],
            "concept": concept,
            "question": quiz.get_question(question_id),
        })

    complete(session_id)
    return None


def _asked_question_ids(session_id: int) -> list[int]:
    with db.conn() as c:
        rows = c.execute(
            "SELECT question_id FROM attempts WHERE session_id=?", (session_id,)
        ).fetchall()
    return [row["question_id"] for row in rows]


def _mark_done(item_id: int) -> None:
    with db.conn() as c:
        c.execute("UPDATE session_items SET done=1 WHERE id=?", (item_id,))


def mark_read(item_id: int) -> None:
    _mark_done(item_id)


def _with_progress(session_id: int, payload: dict) -> dict:
    with db.conn() as c:
        row = c.execute(
            "SELECT COUNT(*) AS total, SUM(done) AS done FROM session_items "
            "WHERE session_id=?",
            (session_id,),
        ).fetchone()
    payload["progress"] = {"done": row["done"] or 0, "total": row["total"] or 0}
    return payload


def complete(session_id: int) -> None:
    with db.conn() as c:
        c.execute(
            "UPDATE sessions SET status='complete', completed_at=? WHERE id=?",
            (time.time(), session_id),
        )
    with _prefetch_lock:
        _prefetched.pop(session_id, None)


def state(session_id: int) -> dict | None:
    session = _session_row(session_id)
    if session is None:
        return None
    with db.conn() as c:
        items = c.execute(
            "SELECT si.*, c.name AS concept_name FROM session_items si "
            "JOIN concepts c ON c.id = si.concept_id "
            "WHERE si.session_id=? ORDER BY si.position",
            (session_id,),
        ).fetchall()
        attempts = c.execute(
            "SELECT COUNT(*) AS total, SUM(correct) AS correct FROM attempts "
            "WHERE session_id=?",
            (session_id,),
        ).fetchone()
    return {
        "id": session["id"],
        "kind": session["kind"],
        "status": session["status"],
        "created_at": session["created_at"],
        "items": [dict(item) for item in items],
        "answered": attempts["total"] or 0,
        "correct": attempts["correct"] or 0,
    }


def recent(goal_id: int, limit: int = 10) -> list[dict]:
    with db.conn() as c:
        rows = c.execute(
            "SELECT s.*, "
            "  (SELECT COUNT(*) FROM attempts a WHERE a.session_id = s.id) AS answered, "
            "  (SELECT SUM(correct) FROM attempts a WHERE a.session_id = s.id) AS correct "
            "FROM sessions s WHERE s.goal_id=? ORDER BY s.created_at DESC LIMIT ?",
            (goal_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]
