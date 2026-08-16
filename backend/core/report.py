"""Weekly report: what moved, what didn't, and what is still missing."""
from __future__ import annotations

import time

from core import concepts, db, gaps, mastery, quiz

WEEK_SECONDS = 7 * 86400


def _mastery_at(goal_id: int, at: float) -> dict[int, float]:
    """Each concept's mastery as of a moment, from the last point at or before it."""
    with db.conn() as c:
        rows = c.execute(
            "SELECT h.concept_id, h.p_known FROM mastery_history h "
            "JOIN concepts c ON c.id = h.concept_id "
            "WHERE c.goal_id=? AND h.created_at <= ? ORDER BY h.created_at ASC",
            (goal_id, at),
        ).fetchall()
    snapshot: dict[int, float] = {}
    for row in rows:
        snapshot[row["concept_id"]] = row["p_known"]
    return snapshot


def weekly(goal_id: int, now: float | None = None) -> dict:
    now = now or time.time()
    week_ago = now - WEEK_SECONDS

    nodes = {node["id"]: node for node in concepts.graph(goal_id)["nodes"]}
    before = _mastery_at(goal_id, week_ago)

    deltas = []
    for cid, node in nodes.items():
        start = before.get(cid, mastery.P_INIT)
        deltas.append({
            "concept_id": cid,
            "name": node["name"],
            "before": start,
            "after": node["p_known"],
            "delta": node["p_known"] - start,
            "attempts": node["attempts"],
        })
    deltas.sort(key=lambda row: row["delta"], reverse=True)

    with db.conn() as c:
        activity = c.execute(
            "SELECT COUNT(*) AS answered, SUM(a.correct) AS correct "
            "FROM attempts a JOIN concepts c ON c.id = a.concept_id "
            "WHERE c.goal_id=? AND a.created_at >= ?",
            (goal_id, week_ago),
        ).fetchone()
        sessions = c.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE goal_id=? AND created_at >= ?",
            (goal_id, week_ago),
        ).fetchone()

    answered = activity["answered"] or 0
    correct = activity["correct"] or 0
    improved = [row for row in deltas if row["delta"] > 0.01]

    return {
        "generated_at": now,
        "window_days": 7,
        "summary": {
            **gaps.summary(goal_id),
            "sessions": sessions["n"] or 0,
            "answered": answered,
            "correct": correct,
            "accuracy": (correct / answered) if answered else 0.0,
            "improved": len(improved),
        },
        "deltas": deltas,
        "gaps": gaps.rank(goal_id)[:10],
        "misconceptions": quiz.misconception_counts(goal_id),
        "review": mastery.due_queue(goal_id, now)[:12],
    }
