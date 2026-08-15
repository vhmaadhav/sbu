"""Build an exam's concept graph and bind each concept to the student's notes.

The graph is extracted *from the student's own notes* — the exam name only picks
which notes to read. Every concept is then bound to real chunks by vector search,
and anything that binds to nothing is dropped. So the map never grows topics the
student has no material for, and study/RAG steps always have something to cite.
"""
from __future__ import annotations

import logging
import re
import threading
import time

from core import db, llm, mastery, vectorstore

logger = logging.getLogger(__name__)

MAX_CONCEPTS = 60
SOURCES_PER_CONCEPT = 5
MAX_TIER_DEPTH = 12

NOTE_CHARS = 2600      # how much of one note goes into the digest
BATCH_CHARS = 12000    # how much material goes to the model in one pass
MAX_BATCHES = 6        # a ceiling on build time for a large library

GRAPH_SYSTEM = """You read a student's own study notes and map what those notes
teach into a prerequisite graph of concepts.

Return one JSON object with this exact shape:
{"concepts": [{"name": "Concept name",
               "blurb": "One sentence on what the student must be able to do.",
               "prerequisites": ["Other concept name", ...]}]}

Rules:
- Every concept MUST be taught by the supplied notes. Never add a topic from your
  own knowledge of the subject, however standard or expected it is: if the notes
  do not cover it, it does not belong in the graph.
- Do not broaden a concept beyond what the notes say, and do not split one idea
  into a syllabus of sub-topics the notes never mention.
- Returning few concepts is correct when the notes teach few. Never pad the list
  to look complete.
- Name each concept with the wording the notes use. Names are short noun phrases,
  unique, and title-cased.
- "prerequisites" lists ONLY names that also appear in this same concepts array.
- The prerequisite relation must be acyclic: a concept never depends on something
  that depends on it, directly or indirectly.
- Foundational concepts have an empty prerequisites array. Include several.
"""


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "exam"


# ── Goal lifecycle ────────────────────────────────────────────────────────

def current_goal() -> dict | None:
    with db.conn() as c:
        row = c.execute(
            "SELECT * FROM exam_goals ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_goal(goal_id: int) -> dict | None:
    with db.conn() as c:
        row = c.execute("SELECT * FROM exam_goals WHERE id=?", (goal_id,)).fetchone()
    return dict(row) if row else None


def create_goal(name: str) -> dict:
    """Create a goal in `building` state and start the graph build in the background."""
    name = name.strip()[:120]
    if not name:
        raise ValueError("an exam name is required")
    now = time.time()
    with db.conn() as c:
        goal_id = c.execute(
            "INSERT INTO exam_goals (name, slug, status, created_at) VALUES (?,?,?,?)",
            (name, _slug(name), "building", now),
        ).lastrowid

    thread = threading.Thread(target=_build_safely, args=(goal_id, name), daemon=True)
    thread.start()
    return get_goal(goal_id)


def delete_goal(goal_id: int) -> None:
    """Remove a goal and everything derived from it, newest dependants first."""
    with db.conn() as c:
        concept_ids = [
            row["id"]
            for row in c.execute("SELECT id FROM concepts WHERE goal_id=?", (goal_id,))
        ]
        session_ids = [
            row["id"]
            for row in c.execute("SELECT id FROM sessions WHERE goal_id=?", (goal_id,))
        ]
        if session_ids:
            marks = ",".join("?" * len(session_ids))
            c.execute(f"DELETE FROM session_items WHERE session_id IN ({marks})", session_ids)
            c.execute(f"DELETE FROM attempts WHERE session_id IN ({marks})", session_ids)
        if concept_ids:
            marks = ",".join("?" * len(concept_ids))
            c.execute(f"DELETE FROM attempts WHERE concept_id IN ({marks})", concept_ids)
            c.execute(f"DELETE FROM questions WHERE concept_id IN ({marks})", concept_ids)
            c.execute(f"DELETE FROM mastery_history WHERE concept_id IN ({marks})", concept_ids)
            c.execute(f"DELETE FROM mastery WHERE concept_id IN ({marks})", concept_ids)
            c.execute(f"DELETE FROM concept_sources WHERE concept_id IN ({marks})", concept_ids)
            c.execute(
                f"DELETE FROM concept_edges WHERE concept_id IN ({marks}) "
                f"OR prereq_id IN ({marks})",
                concept_ids + concept_ids,
            )
        c.execute("DELETE FROM sessions WHERE goal_id=?", (goal_id,))
        c.execute("DELETE FROM concepts WHERE goal_id=?", (goal_id,))
        c.execute("DELETE FROM exam_goals WHERE id=?", (goal_id,))


def _build_safely(goal_id: int, name: str) -> None:
    try:
        build(goal_id, name)
    except Exception as exc:  # a half-built graph is never shown
        logger.exception("concept graph build failed", extra={"goal_id": goal_id})
        with db.conn() as c:
            c.execute(
                "UPDATE exam_goals SET status='error', error=? WHERE id=?",
                (str(exc)[:400], goal_id),
            )


# ── Graph construction ────────────────────────────────────────────────────

def _assign_tiers(names: list[str], prereqs: dict[str, list[str]]) -> dict[str, int]:
    """Longest-path depth from a root, so a concept always sits below its prerequisites.

    Cycles the model may have emitted are broken by the depth cap rather than
    rejected: a slightly flattened graph is far better than no graph at all.
    """
    tiers: dict[str, int] = {}

    def depth(name: str, seen: frozenset[str]) -> int:
        if name in tiers:
            return tiers[name]
        if name in seen or len(seen) > MAX_TIER_DEPTH:
            return 0
        parents = [p for p in prereqs.get(name, []) if p in prereqs]
        value = 0 if not parents else 1 + max(
            depth(p, seen | {name}) for p in parents
        )
        value = min(value, MAX_TIER_DEPTH)
        tiers[name] = value
        return value

    for name in names:
        depth(name, frozenset())
    return tiers


def _parse_entries(payload: dict) -> list[dict]:
    """The usable concepts in one model response, deduplicated within that response."""
    entries: dict[str, dict] = {}
    for entry in payload.get("concepts") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()[:120]
        if not name or name.lower() in entries:
            continue
        entries[name.lower()] = {
            "name": name,
            "blurb": str(entry.get("blurb") or "").strip()[:300],
            "prerequisites": [
                str(p).strip()[:120]
                for p in (entry.get("prerequisites") or [])
                if str(p).strip()
            ],
        }
    return list(entries.values())


def _resolve_prereqs(entries: list[dict]) -> dict[str, list[str]]:
    """Drop prerequisite names that no concept in the graph answers to."""
    canonical = {entry["name"].lower(): entry["name"] for entry in entries}
    return {
        entry["name"]: [
            canonical[p.lower()]
            for p in entry["prerequisites"]
            if p.lower() in canonical and canonical[p.lower()] != entry["name"]
        ]
        for entry in entries
    }


# ── The student's material ────────────────────────────────────────────────

def _condense(markdown: str, budget: int) -> str:
    """A note squeezed into `budget` characters, headings first.

    Headings are the note's own topic list, so they survive truncation even when
    the body does not.
    """
    lines = markdown.splitlines()
    headings = [line.strip() for line in lines if line.lstrip().startswith("#")]
    head = "\n".join(headings)[: budget // 2]
    body = " ".join(markdown.split())[: max(0, budget - len(head))]
    return f"{head}\n{body}".strip()


def _study_material(name: str) -> list[str]:
    """The student's notes as digest blocks, narrowed to the goal's folder if one matches."""
    with db.conn() as c:
        rows = c.execute(
            "SELECT notes.markdown, items.title, subjects.name AS subject "
            "FROM notes JOIN items ON items.id = notes.item_id "
            "LEFT JOIN subjects ON subjects.id = items.subject_id "
            "ORDER BY notes.created_at"
        ).fetchall()

    needle = name.strip().lower()
    scoped = [
        row for row in rows
        if row["subject"] and (
            needle in row["subject"].lower() or row["subject"].lower() in needle
        )
    ]
    # Only narrow when the folder holds enough to build a map from.
    if len(scoped) >= 2:
        rows = scoped

    blocks = []
    for row in rows:
        text = _condense(row["markdown"] or "", NOTE_CHARS)
        if not text:
            continue
        label = row["title"] or "Untitled note"
        blocks.append(f"### {label}\n{text}")
    return blocks


def _batches(blocks: list[str]) -> list[str]:
    """Group note digests into passes that each fit comfortably in one prompt."""
    batches: list[str] = []
    current: list[str] = []
    size = 0
    for block in blocks:
        if current and size + len(block) > BATCH_CHARS:
            batches.append("\n\n".join(current))
            current, size = [], 0
        current.append(block)
        size += len(block)
    if current:
        batches.append("\n\n".join(current))
    return batches[:MAX_BATCHES]


def _extract(name: str, batches: list[str]) -> list[dict]:
    """Walk the notes and collect the concepts they teach, carrying names forward."""
    found: dict[str, dict] = {}
    for index, batch in enumerate(batches):
        prompt = (
            f"The student is revising for: {name}\n\n"
            f"Their notes (part {index + 1} of {len(batches)}):\n\n{batch}\n\n"
        )
        if found:
            prompt += (
                "Concepts already extracted from earlier parts — reuse these names "
                "exactly when the same idea reappears and cite them as prerequisites "
                "where they apply, but do not list them again as new concepts:\n"
                + ", ".join(entry["name"] for entry in found.values())
                + "\n\n"
            )
        prompt += "Extract only the concepts these notes actually teach."

        try:
            payload = llm.chat_json(GRAPH_SYSTEM, prompt, max_tokens=3000)
        except Exception:  # one bad pass must not lose the rest of the library
            logger.warning("concept extraction failed for notes batch %d", index + 1)
            continue

        for entry in _parse_entries(payload):
            found.setdefault(entry["name"].lower(), entry)
            if len(found) >= MAX_CONCEPTS:
                return list(found.values())
    return list(found.values())


def build(goal_id: int, name: str) -> None:
    """Extract the graph from the student's notes, persist it, and bind its sources."""
    blocks = _study_material(name)
    if not blocks:
        raise ValueError(
            "There are no notes to build a map from. Add study material first, "
            "then set the goal."
        )

    entries = _extract(name, _batches(blocks))
    if not entries:
        raise ValueError("the model found no usable concepts in your notes")
    prereqs = _resolve_prereqs(entries)
    tiers = _assign_tiers([e["name"] for e in entries], prereqs)

    ordered = sorted(entries, key=lambda e: (tiers.get(e["name"], 0), e["name"]))
    now = time.time()
    position_in_tier: dict[int, int] = {}
    ids: dict[str, int] = {}

    with db.conn() as c:
        for entry in ordered:
            tier = tiers.get(entry["name"], 0)
            position = position_in_tier.get(tier, 0)
            position_in_tier[tier] = position + 1
            ids[entry["name"]] = c.execute(
                "INSERT INTO concepts (goal_id, name, blurb, tier, position, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (goal_id, entry["name"], entry["blurb"], tier, position, now),
            ).lastrowid
        c.executemany(
            "INSERT OR IGNORE INTO concept_edges (prereq_id, concept_id) VALUES (?,?)",
            [
                (ids[parent], ids[child])
                for child, parents in prereqs.items()
                for parent in parents
                if child in ids and parent in ids
            ],
        )

    bind_sources(goal_id)
    _prune_ungrounded(goal_id)

    surviving = [row["id"] for row in list_concepts(goal_id)]
    if not surviving:
        raise ValueError("none of the extracted concepts matched your notes")
    mastery.ensure_rows(surviving)

    with db.conn() as c:
        c.execute("UPDATE exam_goals SET status='ready', error=NULL WHERE id=?", (goal_id,))


def _prune_ungrounded(goal_id: int) -> int:
    """Drop concepts no note chunk supports, so nothing untestable reaches a session.

    When *nothing* bound — an empty or unbuilt vector index rather than a concept
    the notes do not cover — the graph is kept whole: that is a search problem,
    not evidence about the material.
    """
    with db.conn() as c:
        rows = c.execute(
            "SELECT c.id, COUNT(cs.chunk_id) AS sources FROM concepts c "
            "LEFT JOIN concept_sources cs ON cs.concept_id = c.id "
            "WHERE c.goal_id=? GROUP BY c.id",
            (goal_id,),
        ).fetchall()
        ungrounded = [row["id"] for row in rows if not row["sources"]]
        if not ungrounded or len(ungrounded) == len(rows):
            return 0
        marks = ",".join("?" * len(ungrounded))
        c.execute(
            f"DELETE FROM concept_edges WHERE concept_id IN ({marks}) "
            f"OR prereq_id IN ({marks})",
            ungrounded + ungrounded,
        )
        c.execute(f"DELETE FROM concepts WHERE id IN ({marks})", ungrounded)
    logger.info("dropped %d concepts with no supporting notes", len(ungrounded))
    return len(ungrounded)


def bind_sources(goal_id: int) -> int:
    """Attach the closest note chunks to each concept. Absence of notes is not an error."""
    with db.conn() as c:
        rows = c.execute(
            "SELECT id, name, blurb FROM concepts WHERE goal_id=?", (goal_id,)
        ).fetchall()
    bound = 0
    for row in rows:
        query = f"{row['name']}. {row['blurb']}".strip()
        try:
            hits = vectorstore.search(query, k=SOURCES_PER_CONCEPT)
        except Exception:  # empty or unbuilt index — the map still works without it
            logger.warning("vector search unavailable while binding concepts")
            return bound
        pairs = [
            (row["id"], int(hit["chunk_id"]), float(hit.get("_distance") or 0.0))
            for hit in hits
            if hit.get("chunk_id") is not None
        ]
        if not pairs:
            continue
        with db.conn() as c:
            c.executemany(
                "INSERT OR REPLACE INTO concept_sources (concept_id, chunk_id, score) "
                "VALUES (?,?,?)",
                pairs,
            )
        bound += len(pairs)
    return bound


# ── Reads ─────────────────────────────────────────────────────────────────

def list_concepts(goal_id: int) -> list[dict]:
    with db.conn() as c:
        rows = c.execute(
            "SELECT * FROM concepts WHERE goal_id=? ORDER BY tier, position", (goal_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_concept(concept_id: int) -> dict | None:
    with db.conn() as c:
        row = c.execute("SELECT * FROM concepts WHERE id=?", (concept_id,)).fetchone()
    return dict(row) if row else None


def list_edges(goal_id: int) -> list[dict]:
    with db.conn() as c:
        rows = c.execute(
            "SELECT e.prereq_id, e.concept_id FROM concept_edges e "
            "JOIN concepts c ON c.id = e.concept_id WHERE c.goal_id=?",
            (goal_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def prerequisites_of(concept_id: int) -> list[int]:
    with db.conn() as c:
        rows = c.execute(
            "SELECT prereq_id FROM concept_edges WHERE concept_id=?", (concept_id,)
        ).fetchall()
    return [row["prereq_id"] for row in rows]


def downstream_counts(goal_id: int) -> dict[int, int]:
    """How many concepts each concept unlocks, transitively — used to rank urgency."""
    edges = list_edges(goal_id)
    children: dict[int, list[int]] = {}
    for edge in edges:
        children.setdefault(edge["prereq_id"], []).append(edge["concept_id"])

    counts: dict[int, int] = {}

    def walk(node: int, seen: set[int]) -> set[int]:
        reached: set[int] = set()
        for child in children.get(node, []):
            if child in seen:
                continue
            reached.add(child)
            reached |= walk(child, seen | {child})
        return reached

    for concept in list_concepts(goal_id):
        counts[concept["id"]] = len(walk(concept["id"], {concept["id"]}))
    return counts


def source_chunks(concept_id: int, limit: int = SOURCES_PER_CONCEPT) -> list[dict]:
    """The note excerpts bound to a concept, for the `read` step and scoped RAG."""
    with db.conn() as c:
        rows = c.execute(
            "SELECT ch.id AS chunk_id, ch.text, ch.source_label, ch.item_id, "
            "       ch.ts_start, ch.page, cs.score "
            "FROM concept_sources cs JOIN chunks ch ON ch.id = cs.chunk_id "
            "WHERE cs.concept_id=? ORDER BY cs.score ASC LIMIT ?",
            (concept_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def graph(goal_id: int) -> dict:
    """Nodes, edges and mastery in one payload — everything the concept map needs."""
    states = mastery.all_for_goal(goal_id)
    counts = downstream_counts(goal_id)
    nodes = []
    for concept in list_concepts(goal_id):
        state = states.get(concept["id"])
        nodes.append({
            "id": concept["id"],
            "name": concept["name"],
            "blurb": concept["blurb"],
            "tier": concept["tier"],
            "position": concept["position"],
            "p_known": state.p_known if state else mastery.P_INIT,
            "attempts": state.attempts if state else 0,
            "confidence": state.confidence if state else 0.0,
            "in_srs": state.in_srs if state else False,
            "downstream": counts.get(concept["id"], 0),
        })
    return {"nodes": nodes, "edges": list_edges(goal_id)}
