#!/usr/bin/env python3
"""Run diagram extraction for existing image items and update their notes."""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import db, figures, notes  # noqa: E402
from core.diagrams import analyze_diagram  # noqa: E402


def retrofit(item_id: int) -> int:
    item = db.get_item(item_id)
    if not item or item["kind"] != "image" or not Path(item["stored_path"]).exists():
        raise ValueError(f"item {item_id} is not an available image")
    existing_notes = db.notes_for_item(item_id)
    if not existing_notes:
        raise ValueError(f"item {item_id} has no note to update")

    result = analyze_diagram(item["stored_path"])
    if not result["graph"].get("is_diagram") or not result["graph"].get("nodes"):
        raise ValueError(f"item {item_id} was not detected as a diagram")

    # Replace an earlier retrofit section and overlay, making the operation
    # safe to repeat while tuning the pipeline.
    note = existing_notes[-1]
    markdown = re.split(r"\n+## Editable diagram\s*\n", note["markdown"], maxsplit=1)[0].rstrip()
    with db.conn() as connection:
        old = connection.execute(
            "SELECT id,image_path FROM doc_figures "
            "WHERE item_id=? AND caption='Detected diagram nodes'",
            (item_id,),
        ).fetchall()
        connection.execute(
            "DELETE FROM doc_figures WHERE item_id=? AND caption='Detected diagram nodes'",
            (item_id,),
        )
    for row in old:
        Path(row["image_path"]).unlink(missing_ok=True)

    overlay = figures._persist(
        item_id, None, "Detected diagram nodes", Path(result["overlay"]).read_bytes()
    )
    overlay_url = f"/api/doc/figures/{overlay['filename']}"
    pipeline = "\n".join(
        f"- **{stage['name'].replace('_', ' ').title()}:** "
        f"{stage['status']} via {stage['implementation']}"
        for stage in result["stages"]
    )
    markdown += (
        "\n\n## Editable diagram\n\n"
        f"![Detected diagram nodes]({overlay_url})\n\n"
        f"```mermaid\n{result['mermaid']}\n```\n\n"
        f"## Diagram pipeline\n\n{pipeline}\n\n"
        f"### Extracted labels\n\n{result['ocr_markdown']}"
    )

    capture_date = item.get("capture_date") or datetime.fromtimestamp(
        item["created_at"]
    ).date().isoformat()
    source = f"{item.get('title') or item['filename']} — {capture_date} ({item['filename']})"
    with db.conn() as connection:
        subject = connection.execute(
            "SELECT name FROM subjects WHERE id=?", (item["subject_id"],)
        ).fetchone()
    notes.update_note_markdown(
        note["id"], item_id, markdown, source,
        subject["name"] if subject else "General",
    )
    return note["id"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("item_ids", type=int, nargs="+")
    args = parser.parse_args()
    for item_id in args.item_ids:
        print(f"item {item_id} -> note {retrofit(item_id)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
