"""Seed a deterministic Computer Science story for the Axiom Trace demo.

Run from ``backend/`` with ``uv run python scripts/seed_axiom_trace_demo.py``.
Only records marked ``axiom-trace-demo`` are replaced; personal library data is
left untouched.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import concepts, db, mastery
from core.config import FILES_DIR

DEMO_MARKER = "axiom-trace-demo"
DEMO_GOAL_SLUG = "axiom-trace-computer-science-demo"
DEMO_SUBJECT = "Axiom Trace Demo — Computer Science"

CONCEPTS = [
    ("Arrays", "Use indexed contiguous storage and explain access cost.", 0, 0, 0.82, 5, 4),
    ("Algorithmic Complexity", "Compare runtime and space growth with Big-O.", 0, 1, 0.72, 4, 3),
    ("Recursion", "Trace a recursive call stack and its base case.", 0, 2, 0.38, 3, 1),
    ("Stacks", "Apply last-in, first-out behavior to algorithms.", 1, 0, 0.42, 4, 2),
    ("Queues", "Apply first-in, first-out behavior to algorithms.", 1, 1, 0.55, 3, 2),
    ("Depth-First Search", "Traverse a graph deeply using recursion or a stack.", 2, 0, 0.31, 3, 1),
    ("Breadth-First Search", "Traverse a graph level by level using a queue.", 2, 1, 0.61, 4, 3),
    ("Graph Traversal", "Choose and justify a traversal strategy for a problem.", 3, 0, 0.28, 2, 0),
]

EDGES = [
    ("Arrays", "Stacks"),
    ("Arrays", "Queues"),
    ("Stacks", "Depth-First Search"),
    ("Recursion", "Depth-First Search"),
    ("Queues", "Breadth-First Search"),
    ("Algorithmic Complexity", "Graph Traversal"),
    ("Depth-First Search", "Graph Traversal"),
    ("Breadth-First Search", "Graph Traversal"),
]

SOURCES = [
    {
        "title": "Data Structures — Arrays, Stacks, and Queues",
        "uri": "https://demo.axiom-trace.local/data-structures",
        "dwell_ms": 92_000,
        "text": (
            "Arrays provide constant-time indexed access. A stack follows last-in, first-out "
            "ordering, while a queue follows first-in, first-out ordering. These structures "
            "determine which frontier item a traversal visits next."
        ),
        "concepts": ["Arrays", "Stacks", "Queues"],
    },
    {
        "title": "Tracing Recursive Calls",
        "uri": "https://demo.axiom-trace.local/recursion",
        "dwell_ms": 68_000,
        "text": (
            "Recursion solves a problem through smaller calls and must reach a base case. "
            "Each active call is stored on the call stack, which is why recursive depth-first "
            "search behaves like an explicit stack implementation."
        ),
        "concepts": ["Recursion", "Stacks", "Depth-First Search"],
    },
    {
        "title": "DFS and BFS Compared",
        "uri": "https://demo.axiom-trace.local/graph-traversal",
        "dwell_ms": 134_000,
        "text": (
            "Depth-first search explores one branch before backtracking. Breadth-first search "
            "uses a queue to visit vertices level by level and finds shortest paths in an "
            "unweighted graph. Both run in O(V + E) with adjacency lists."
        ),
        "concepts": [
            "Algorithmic Complexity",
            "Depth-First Search",
            "Breadth-First Search",
            "Graph Traversal",
        ],
    },
]


def _remove_previous_demo() -> None:
    with db.conn() as connection:
        row = connection.execute(
            "SELECT id FROM exam_goals WHERE slug=? ORDER BY id DESC LIMIT 1",
            (DEMO_GOAL_SLUG,),
        ).fetchone()
    if row:
        concepts.delete_goal(int(row["id"]))

    with db.conn() as connection:
        item_ids = [
            int(row["id"])
            for row in connection.execute(
                "SELECT id FROM items WHERE metadata_text=?", (DEMO_MARKER,)
            )
        ]
        for item_id in item_ids:
            connection.execute("DELETE FROM capture_events WHERE item_id=?", (item_id,))
            connection.execute("DELETE FROM notes WHERE item_id=?", (item_id,))
            connection.execute("DELETE FROM chunks WHERE item_id=?", (item_id,))
            connection.execute("DELETE FROM items WHERE id=?", (item_id,))


def seed(files_dir: Path = FILES_DIR) -> dict:
    db.init_db()
    files_dir.mkdir(parents=True, exist_ok=True)
    _remove_previous_demo()
    now = time.time()
    captured_at = datetime.now(UTC).isoformat()

    subject_id = db.get_or_create_subject(DEMO_SUBJECT)
    chunks_by_concept: dict[str, list[int]] = {name: [] for name, *_ in CONCEPTS}
    item_ids: list[int] = []
    with db.conn() as connection:
        for index, source in enumerate(SOURCES, start=1):
            filename = f"axiom-trace-demo-{index}.txt"
            stored_path = files_dir / filename
            stored_path.write_text(source["text"], encoding="utf-8")
            item_id = connection.execute(
                "INSERT INTO items "
                "(filename, stored_path, kind, status, title, subject_id, metadata_text, "
                "capture_date, created_at, processed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    filename,
                    str(stored_path),
                    "text",
                    "done",
                    source["title"],
                    subject_id,
                    DEMO_MARKER,
                    captured_at,
                    now + index,
                    now + index,
                ),
            ).lastrowid
            item_ids.append(int(item_id))
            connection.execute(
                "INSERT INTO notes (item_id, markdown, created_at) VALUES (?,?,?)",
                (item_id, f"# {source['title']}\n\n{source['text']}", now + index),
            )
            chunk_id = connection.execute(
                "INSERT INTO chunks (item_id, text, source_label) VALUES (?,?,?)",
                (item_id, source["text"], source["title"]),
            ).lastrowid
            for concept_name in source["concepts"]:
                chunks_by_concept[concept_name].append(int(chunk_id))
            connection.execute(
                "INSERT INTO capture_events "
                "(event_id, item_id, source_uri, title, content_hash, dwell_ms, captured_at, "
                "metadata_json, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    f"axiom-trace-demo-{index}",
                    item_id,
                    source["uri"],
                    source["title"],
                    hashlib.sha256(source["text"].encode("utf-8")).hexdigest(),
                    source["dwell_ms"],
                    captured_at,
                    json.dumps({"language": "en", "demo": True}),
                    now + index,
                ),
            )

        goal_id = connection.execute(
            "INSERT INTO exam_goals (name, slug, status, created_at) VALUES (?,?,?,?)",
            ("Computer Science Fundamentals", DEMO_GOAL_SLUG, "ready", now + 10),
        ).lastrowid
        concept_ids: dict[str, int] = {}
        for name, blurb, tier, position, *_ in CONCEPTS:
            concept_ids[name] = int(
                connection.execute(
                    "INSERT INTO concepts (goal_id, name, blurb, tier, position, created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (goal_id, name, blurb, tier, position, now + 10),
                ).lastrowid
            )
        connection.executemany(
            "INSERT INTO concept_edges (prereq_id, concept_id) VALUES (?,?)",
            [(concept_ids[parent], concept_ids[child]) for parent, child in EDGES],
        )
        connection.executemany(
            "INSERT INTO concept_sources (concept_id, chunk_id, score) VALUES (?,?,?)",
            [
                (concept_ids[name], chunk_id, 0.05)
                for name, chunk_ids in chunks_by_concept.items()
                for chunk_id in chunk_ids
            ],
        )

    mastery.ensure_rows(list(concept_ids.values()))
    with db.conn() as connection:
        for name, _blurb, _tier, _position, p_known, attempts, correct in CONCEPTS:
            concept_id = concept_ids[name]
            connection.execute(
                "UPDATE mastery SET p_known=?, attempts=?, correct=?, updated_at=? "
                "WHERE concept_id=?",
                (p_known, attempts, correct, now + 20, concept_id),
            )
            connection.execute(
                "INSERT INTO mastery_history (concept_id, p_known, created_at) VALUES (?,?,?)",
                (concept_id, p_known, now + 20),
            )

    return {
        "goal_id": int(goal_id),
        "concepts": len(concept_ids),
        "edges": len(EDGES),
        "sources": len(item_ids),
        "focus_concept_id": concept_ids["Depth-First Search"],
    }


if __name__ == "__main__":
    result = seed()
    print(
        "Axiom Trace demo seeded: "
        f"{result['concepts']} concepts, {result['edges']} edges, "
        f"{result['sources']} evidence sources."
    )
