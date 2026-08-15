"""Bayesian Knowledge Tracing and the exponential-decay forgetting model.

The arithmetic here is deliberately pure: `update`, `recall` and `risk` take
numbers and return numbers, so they are testable without a database. The
`record_attempt` helper is the only part that touches SQLite.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from core import db

# BKT parameters. P_GUESS matches the 25% floor of a four-option MCQ; without
# that, a lucky guess would move the posterior as much as real knowledge does.
P_INIT = 0.25
P_LEARN = 0.15
P_SLIP = 0.10
P_GUESS = 0.25

WEAK_THRESHOLD = 0.6           # below this, a concept is a gap
FOUNDATION_THRESHOLD = 0.5     # below this, a prerequisite is "missing"
MASTERED_THRESHOLD = 0.85      # at or above this, a concept enters the SRS queue

INITIAL_HALF_LIFE_DAYS = 1.0
HALF_LIFE_GROWTH = 2.0         # a successful review doubles the interval
HALF_LIFE_PENALTY = 0.4        # a failed review cuts it back
RECALL_DUE_THRESHOLD = 0.85    # surface a concept when predicted recall drops here
DAY_SECONDS = 86400.0


@dataclass(frozen=True)
class MasteryState:
    concept_id: int
    p_known: float
    attempts: int
    correct: int
    half_life: float
    last_review_at: float | None
    in_srs: bool

    @property
    def confidence(self) -> float:
        return confidence(self.attempts)

    def recall_at(self, at: float | None = None) -> float:
        return recall(self.half_life, self.last_review_at, at)


def posterior(p: float, correct: bool) -> float:
    """P(knows | this observation), before accounting for learning."""
    if correct:
        num = p * (1 - P_SLIP)
        den = num + (1 - p) * P_GUESS
    else:
        num = p * P_SLIP
        den = num + (1 - p) * (1 - P_GUESS)
    return num / den if den else p


def update(p: float, correct: bool) -> float:
    """Full BKT step: observe, then allow for learning from the attempt itself."""
    post = posterior(p, correct)
    return min(0.999, post + (1 - post) * P_LEARN)


def confidence(attempts: int) -> float:
    """How much the posterior can be trusted.

    BKT carries no variance of its own, so attempt count stands in for it. This
    is what separates "tested and weak" from "never tested" in the gap list.
    """
    return 1 - math.exp(-attempts / 3)


def recall(half_life: float, last_review_at: float | None, at: float | None = None) -> float:
    """Predicted probability of recall right now, under exponential decay."""
    if last_review_at is None:
        return 1.0
    elapsed_days = max(0.0, ((at or time.time()) - last_review_at) / DAY_SECONDS)
    return 2 ** (-elapsed_days / max(0.05, half_life))


def risk(half_life: float, last_review_at: float | None, at: float | None = None) -> float:
    return 1 - recall(half_life, last_review_at, at)


def days_until_due(half_life: float, last_review_at: float | None,
                   at: float | None = None) -> float:
    """Days until predicted recall falls to the review threshold (0 if overdue)."""
    if last_review_at is None:
        return 0.0
    full_life = half_life * math.log2(1 / RECALL_DUE_THRESHOLD)
    elapsed_days = max(0.0, ((at or time.time()) - last_review_at) / DAY_SECONDS)
    return max(0.0, full_life - elapsed_days)


def next_half_life(current: float, correct: bool) -> float:
    if correct:
        return min(180.0, current * HALF_LIFE_GROWTH)
    return max(0.25, current * HALF_LIFE_PENALTY)


# ── Persistence ───────────────────────────────────────────────────────────

def _row_to_state(row) -> MasteryState:
    return MasteryState(
        concept_id=row["concept_id"],
        p_known=row["p_known"],
        attempts=row["attempts"],
        correct=row["correct"],
        half_life=row["half_life"],
        last_review_at=row["last_review_at"],
        in_srs=bool(row["in_srs"]),
    )


def ensure_rows(concept_ids: list[int]) -> None:
    """Give every concept a mastery row at the prior, so charts have a baseline."""
    now = time.time()
    with db.conn() as c:
        c.executemany(
            "INSERT OR IGNORE INTO mastery (concept_id, p_known, half_life, updated_at) "
            "VALUES (?,?,?,?)",
            [(cid, P_INIT, INITIAL_HALF_LIFE_DAYS, now) for cid in concept_ids],
        )
        c.executemany(
            "INSERT INTO mastery_history (concept_id, p_known, created_at) VALUES (?,?,?)",
            [(cid, P_INIT, now) for cid in concept_ids],
        )


def get(concept_id: int) -> MasteryState | None:
    with db.conn() as c:
        row = c.execute("SELECT * FROM mastery WHERE concept_id=?", (concept_id,)).fetchone()
    return _row_to_state(row) if row else None


def all_for_goal(goal_id: int) -> dict[int, MasteryState]:
    with db.conn() as c:
        rows = c.execute(
            "SELECT m.* FROM mastery m JOIN concepts c ON c.id = m.concept_id "
            "WHERE c.goal_id=?",
            (goal_id,),
        ).fetchall()
    return {row["concept_id"]: _row_to_state(row) for row in rows}


def apply_attempt(concept_id: int, correct: bool) -> MasteryState:
    """Run one BKT step for a concept and persist the result plus a history point."""
    now = time.time()
    with db.conn() as c:
        row = c.execute("SELECT * FROM mastery WHERE concept_id=?", (concept_id,)).fetchone()
        if row is None:
            c.execute(
                "INSERT INTO mastery (concept_id, p_known, half_life, updated_at) "
                "VALUES (?,?,?,?)",
                (concept_id, P_INIT, INITIAL_HALF_LIFE_DAYS, now),
            )
            row = c.execute(
                "SELECT * FROM mastery WHERE concept_id=?", (concept_id,)
            ).fetchone()

        p_new = update(row["p_known"], correct)
        was_in_srs = bool(row["in_srs"])

        if was_in_srs:
            half_life = next_half_life(row["half_life"], correct)
        else:
            half_life = INITIAL_HALF_LIFE_DAYS
        in_srs = p_new >= MASTERED_THRESHOLD

        c.execute(
            "UPDATE mastery SET p_known=?, attempts=attempts+1, correct=correct+?, "
            "half_life=?, last_review_at=?, in_srs=?, updated_at=? WHERE concept_id=?",
            (p_new, 1 if correct else 0, half_life, now, 1 if in_srs else 0, now, concept_id),
        )
        c.execute(
            "INSERT INTO mastery_history (concept_id, p_known, created_at) VALUES (?,?,?)",
            (concept_id, p_new, now),
        )
        row = c.execute("SELECT * FROM mastery WHERE concept_id=?", (concept_id,)).fetchone()
    return _row_to_state(row)


def history(goal_id: int, limit_per_concept: int = 200) -> list[dict]:
    """Every mastery point for a goal, oldest first, for the learning curve."""
    with db.conn() as c:
        rows = c.execute(
            "SELECT h.concept_id, c.name, h.p_known, h.created_at "
            "FROM mastery_history h JOIN concepts c ON c.id = h.concept_id "
            "WHERE c.goal_id=? ORDER BY h.created_at ASC",
            (goal_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def due_queue(goal_id: int, at: float | None = None) -> list[dict]:
    """Mastered concepts sorted by how close they are to being forgotten."""
    now = at or time.time()
    states = all_for_goal(goal_id)
    with db.conn() as c:
        names = {
            row["id"]: row["name"]
            for row in c.execute(
                "SELECT id, name FROM concepts WHERE goal_id=?", (goal_id,)
            ).fetchall()
        }
    queue = []
    for state in states.values():
        if not state.in_srs:
            continue
        r = state.recall_at(now)
        queue.append({
            "concept_id": state.concept_id,
            "name": names.get(state.concept_id, ""),
            "p_known": state.p_known,
            "half_life": state.half_life,
            "last_review_at": state.last_review_at,
            "recall": r,
            "risk": 1 - r,
            "due": r < RECALL_DUE_THRESHOLD,
            "days_until_due": days_until_due(state.half_life, state.last_review_at, now),
        })
    queue.sort(key=lambda row: row["recall"])
    return queue
