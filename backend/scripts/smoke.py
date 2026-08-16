"""Smoke test: config, DB, embeddings and LanceDB round-trip.

Needs no LM Studio, microphone or media files. Run:  python scripts/smoke.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.config import DATA_DIR  # noqa: E402


def main():
    print(f"data dir: {DATA_DIR}")

    db.init_db()
    subj = db.get_or_create_subject("Smoke Test")
    item = db.add_item("smoke.txt", "/dev/null", "text")
    db.set_item_meta(item, "Smoke item", subj)
    chunk = db.add_chunk(item, "Photosynthesis converts light into chemical energy.", "smoke")
    print(f"sqlite ok (subject={subj}, item={item}, chunk={chunk})")

    from core import vectorstore
    vectorstore.add_chunks([{
        "chunk_id": chunk, "item_id": item, "subject": "Smoke Test",
        "source_label": "smoke", "text": "Photosynthesis converts light into chemical energy.",
    }])
    hits = vectorstore.search("how do plants make energy?", subject="Smoke Test", k=1)
    assert hits and "Photosynthesis" in hits[0]["text"], "vector search failed"
    print("embeddings + lancedb ok")

    print("smoke test passed")


if __name__ == "__main__":
    main()
