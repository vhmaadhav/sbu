"""Ask My Notes: retrieve, rerank, and answer from chunks with citations."""
from core import db, llm, reranker, vectorstore
from core.config import RERANKER_CANDIDATE_K

ANSWER_SYSTEM = (
    "You are a study assistant answering strictly from the student's own notes below. "
    "Cite sources inline using ONLY the exact bracketed source labels present in the supplied notes. "
    "Never invent a source, page number, filename, or timestamp. Prefer timestamped sources for video facts. "
    "If the notes don't contain the answer, say so plainly."
)


def _mmss(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _video_href(item_id: int, seconds: float) -> str:
    total_seconds = int(seconds)
    minutes, remaining_seconds = divmod(total_seconds, 60)
    return f"/search?video={item_id}&t={minutes}m{remaining_seconds:02d}s"


def ask(question: str, subject: str | None = None, k: int = 8) -> dict:
    llm.require_available()
    candidates = vectorstore.search(
        question,
        subject=subject,
        k=max(k, RERANKER_CANDIDATE_K),
    )
    hits = reranker.rerank(question, candidates, top_k=k)
    return answer_from_hits(question, hits)


def answer_from_hits(question: str, hits: list[dict]) -> dict:
    """Answer from an already-retrieved set of chunks.

    Split out from `ask` so callers that select their own chunks — the adaptive
    path scopes questions to one concept's bound sources — get identical
    citation, image, and video handling.
    """
    llm.require_available()
    if not hits:
        return {"answer": "No notes found yet — ingest some material first.",
                "sources": [], "images": [], "videos": []}

    context_blocks = []
    source_targets = []
    for h in hits:
        label = h["source_label"]
        if h.get("ts_start") is not None:
            label += f" @ {_mmss(h['ts_start'])}"
        elif h.get("page"):
            label += f" p. {h['page']}"
        context_blocks.append(f"[source: {label}]\n{h['text']}")
        source_targets.append({
            "label": label,
            "item_id": int(h["item_id"]),
            "note_id": db.note_id_for_item(int(h["item_id"])),
            "timestamp": h.get("ts_start"),
        })

    answer = llm.chat(
        ANSWER_SYSTEM,
        f"Notes:\n\n" + "\n\n---\n\n".join(context_blocks) + f"\n\nQuestion: {question}",
        max_tokens=1200,
    )
    for source in source_targets:
        citation = f"[source: {source['label']}]"
        target = (
            _video_href(source["item_id"], source["timestamp"])
            if source["timestamp"] is not None
            else f"/notes?note={source['note_id']}" if source["note_id"] else None
        )
        if target:
            answer = answer.replace(citation, f"[{citation}]({target})")

    images = []
    for h in hits:
        if h.get("image_path"):
            candidate = {
                "chunk_id": h["chunk_id"], "item_id": h["item_id"],
                "timestamp": h.get("ts_start"), "label": h["source_label"],
                "url": f"/api/chunks/{h['chunk_id']}/image",
            }
            if candidate not in images:
                images.append(candidate)

    videos = []
    for h in hits:
        if h.get("ts_start") is not None:
            candidate = {"item_id": h["item_id"], "timestamp": h["ts_start"], "label": h["source_label"]}
            if candidate not in videos:
                videos.append(candidate)

    sources = list({
        (source["label"], source["item_id"], source["note_id"], source["timestamp"]): source
        for source in source_targets
    }.values())

    return {"answer": answer, "sources": sources, "images": images, "videos": videos}
