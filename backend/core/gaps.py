"""Find weak concepts and the missing prerequisites underneath them.

The learning path is not stored anywhere: it is the ordered output of `rank()`
recomputed against current mastery, so every attempt reshapes it implicitly.
"""
from __future__ import annotations

from core import concepts, mastery


def _reason(p_known: float, attempts: int, missing_for: list[str]) -> str:
    if missing_for:
        return f"Foundation for {missing_for[0]}" + (
            f" and {len(missing_for) - 1} more" if len(missing_for) > 1 else ""
        )
    if attempts == 0:
        return "Not yet tested"
    if p_known < 0.35:
        return "Repeatedly missed"
    return "Shaky — answers are inconsistent"


def rank(goal_id: int) -> list[dict]:
    """Weak concepts, most worth fixing first.

    Ordering is (tier, mastery, downstream reach): the shallowest, weakest, most
    depended-on concept comes first, so a student is never sent at a concept
    whose foundation is still missing.
    """
    nodes = {node["id"]: node for node in concepts.graph(goal_id)["nodes"]}
    if not nodes:
        return []

    weak = {
        cid: node for cid, node in nodes.items()
        if node["p_known"] < mastery.WEAK_THRESHOLD
    }

    # A prerequisite under the foundation threshold is flagged, and inherits the
    # urgency of everything sitting on top of it.
    missing_for: dict[int, list[str]] = {}
    for cid, node in weak.items():
        for prereq_id in concepts.prerequisites_of(cid):
            parent = nodes.get(prereq_id)
            if parent and parent["p_known"] < mastery.FOUNDATION_THRESHOLD:
                missing_for.setdefault(prereq_id, []).append(node["name"])

    candidates = dict(weak)
    for prereq_id in missing_for:
        candidates.setdefault(prereq_id, nodes[prereq_id])

    ranked = []
    for cid, node in candidates.items():
        blocking = missing_for.get(cid, [])
        ranked.append({
            **node,
            "concept_id": cid,
            "missing_prerequisite": bool(blocking),
            "blocking": blocking,
            "reason": _reason(node["p_known"], node["attempts"], blocking),
        })

    ranked.sort(key=lambda row: (
        row["tier"],
        row["p_known"],
        -row["downstream"],
    ))
    return ranked


def missing_prerequisites(goal_id: int) -> list[dict]:
    return [row for row in rank(goal_id) if row["missing_prerequisite"]]


def summary(goal_id: int) -> dict:
    """Headline numbers for the hub screen."""
    nodes = concepts.graph(goal_id)["nodes"]
    if not nodes:
        return {"concepts": 0, "mastered": 0, "weak": 0, "untested": 0, "average": 0.0}
    mastered = sum(1 for n in nodes if n["p_known"] >= mastery.MASTERED_THRESHOLD)
    weak = sum(1 for n in nodes if n["p_known"] < mastery.WEAK_THRESHOLD)
    untested = sum(1 for n in nodes if n["attempts"] == 0)
    return {
        "concepts": len(nodes),
        "mastered": mastered,
        "weak": weak,
        "untested": untested,
        "average": sum(n["p_known"] for n in nodes) / len(nodes),
    }
