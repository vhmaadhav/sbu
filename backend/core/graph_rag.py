"""Knowledge-graph-guided retrieval for personalized concept explanations."""
from __future__ import annotations

from core import concepts, rag, reranker, vectorstore

MAX_NEIGHBORS_PER_ROLE = 4
SOURCES_PER_NODE = 3
MAX_CANDIDATES = 24

_ROLE_STRENGTH = {"semantic_seed": 0, "dependent": 1, "prerequisite": 2, "target": 3}
_CONTEXT_ORDER = {"prerequisite": 0, "target": 1, "dependent": 2, "semantic_seed": 3}


def _evidence_reason(hit: dict) -> str:
    role = hit.get("graph_role", "semantic_seed")
    concept = hit.get("graph_concept_name")
    if role == "prerequisite":
        return f"Supports the prerequisite {concept}."
    if role == "target":
        return f"Directly supports the target concept {concept}."
    if role == "dependent":
        return f"Shows where {concept} is used next."
    return "Matched the student's question semantically."


def neighborhood(concept_id: int) -> dict:
    """Return the target and its weakest immediate graph neighbors."""
    target = concepts.get_concept(concept_id)
    if target is None:
        raise ValueError("concept not found")

    graph = concepts.graph(target["goal_id"])
    nodes = {node["id"]: node for node in graph["nodes"]}
    prerequisite_ids = {
        edge["prereq_id"] for edge in graph["edges"] if edge["concept_id"] == concept_id
    }
    dependent_ids = {
        edge["concept_id"] for edge in graph["edges"] if edge["prereq_id"] == concept_id
    }

    def weakest(ids: set[int]) -> list[dict]:
        rows = [nodes[node_id] for node_id in ids if node_id in nodes]
        rows.sort(key=lambda row: (row["p_known"], row["tier"], row["name"]))
        return rows[:MAX_NEIGHBORS_PER_ROLE]

    prerequisites = weakest(prerequisite_ids)
    dependents = weakest(dependent_ids)
    target_node = nodes.get(concept_id, {**target, "p_known": 0.25})
    expanded = [
        *[{**node, "role": "prerequisite"} for node in prerequisites],
        {**target_node, "role": "target"},
        *[{**node, "role": "dependent"} for node in dependents],
    ]
    paths = [
        f"{node['name']} -> {target_node['name']}" for node in prerequisites
    ] + [
        f"{target_node['name']} -> {node['name']}" for node in dependents
    ]
    return {"target": target_node, "expanded": expanded, "paths": paths}


def _graph_candidates(expanded: list[dict]) -> list[dict]:
    by_chunk: dict[int, dict] = {}
    for node in expanded:
        for hit in concepts.source_chunks(node["id"], limit=SOURCES_PER_NODE):
            candidate = {
                **hit,
                "graph_role": node["role"],
                "graph_concept_id": node["id"],
                "graph_concept_name": node["name"],
            }
            chunk_id = int(hit["chunk_id"])
            current = by_chunk.get(chunk_id)
            if current is None or _ROLE_STRENGTH[node["role"]] > _ROLE_STRENGTH[
                current["graph_role"]
            ]:
                by_chunk[chunk_id] = candidate
    return list(by_chunk.values())


def retrieve(concept_id: int, question: str, top_k: int = 8) -> dict:
    """Retrieve semantic seeds, expand through the KG, rerank, and organize context."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    scope = neighborhood(concept_id)
    graph_hits = _graph_candidates(scope["expanded"])

    try:
        semantic_hits = vectorstore.search(question, k=MAX_CANDIDATES)
    except (OSError, RuntimeError, ValueError):
        semantic_hits = []

    candidates: list[dict] = []
    positions: dict[int, int] = {}
    for hit in [*graph_hits, *semantic_hits]:
        candidate = dict(hit)
        candidate.setdefault("graph_role", "semantic_seed")
        candidate.setdefault("graph_concept_id", None)
        candidate.setdefault("graph_concept_name", None)
        chunk_id = int(candidate["chunk_id"])
        if chunk_id in positions:
            existing = candidates[positions[chunk_id]]
            if _ROLE_STRENGTH[candidate["graph_role"]] > _ROLE_STRENGTH[
                existing["graph_role"]
            ]:
                existing.update(candidate)
            continue
        positions[chunk_id] = len(candidates)
        candidates.append(candidate)
        if len(candidates) >= MAX_CANDIDATES:
            break

    ranked = reranker.rerank(question, candidates, top_k=top_k)
    rank_position = {int(hit["chunk_id"]): index for index, hit in enumerate(ranked)}
    organized = sorted(
        ranked,
        key=lambda hit: (
            _CONTEXT_ORDER[hit.get("graph_role", "semantic_seed")],
            rank_position[int(hit["chunk_id"])],
        ),
    )
    mode = "graph_guided" if any(
        hit.get("graph_role") != "semantic_seed" for hit in organized
    ) else "vector_fallback"
    trace = {
        "mode": mode,
        "seed_concept": {
            "id": scope["target"]["id"],
            "name": scope["target"]["name"],
            "p_known": scope["target"].get("p_known", 0.25),
        },
        "expanded_concepts": [
            {
                "id": node["id"],
                "name": node["name"],
                "role": node["role"],
                "p_known": node.get("p_known", 0.25),
            }
            for node in scope["expanded"]
        ],
        "graph_paths": scope["paths"],
        "evidence_reasons": [
            {
                "chunk_id": int(hit["chunk_id"]),
                "label": hit["source_label"],
                "source": hit["source_label"],
                "role": hit.get("graph_role", "semantic_seed"),
                "concept": hit.get("graph_concept_name"),
                "reason": _evidence_reason(hit),
            }
            for hit in organized
        ],
    }
    return {"hits": organized, "retrieval_trace": trace}


def ask(concept_id: int, question: str, top_k: int = 8) -> dict:
    scope = neighborhood(concept_id)
    retrieval = retrieve(concept_id, question, top_k=top_k)
    prompt = f"In the context of {scope['target']['name']}: {question}"
    result = rag.answer_from_hits(prompt, retrieval["hits"])
    result["retrieval_trace"] = retrieval["retrieval_trace"]
    return result
