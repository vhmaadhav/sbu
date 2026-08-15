import tempfile
import unittest
from pathlib import Path

from core import db, notes
from core.notes import build_manifest_block, place_visuals


def _fig(token_id, anchor=None, url=None, caption="Diagram"):
    return {
        "token_id": token_id,
        "url": url or f"/api/doc/figures/fig_{token_id}.png",
        "caption": caption,
        "anchor": anchor,
    }


class PlaceVisualsTests(unittest.TestCase):
    def test_replaces_token_on_its_own_line(self):
        md = "## Notes\n\nThe handshake works like this.\n\n[[FIG:1]]\n\nMore text."
        out = place_visuals(md, [_fig(1, ("page", 3), caption="Handshake")])

        self.assertIn("![Handshake](/api/doc/figures/fig_1.png)", out)
        self.assertNotIn("[[FIG:1]]", out)

    def test_unplaced_timestamp_visual_inserted_after_marker(self):
        md = "Intro line.\n[@ 12:40] the stack grows here.\nClosing line."
        out = place_visuals(md, [_fig(2, ("ts", 760), caption="Stack")])

        lines = out.split("\n")
        marker = next(i for i, ln in enumerate(lines) if "[@ 12:40]" in ln)
        following = "\n".join(lines[marker + 1: marker + 3])
        self.assertIn("![Stack](/api/doc/figures/fig_2.png)", following)
        self.assertNotIn("## ", out)  # never creates a section

    def test_unplaced_page_visual_inserted_after_page_marker(self):
        md = "[p. 1] first page\n[p. 3] third page discussion\n[p. 5] later"
        out = place_visuals(md, [_fig(3, ("page", 3))])

        lines = out.split("\n")
        marker = next(i for i, ln in enumerate(lines) if "[p. 3]" in ln)
        self.assertIn("![Diagram]", "\n".join(lines[marker + 1: marker + 3]))

    def test_unplaced_without_anchor_appended_without_heading(self):
        md = "Just some notes with no markers at all."
        out = place_visuals(md, [_fig(4, None)])

        self.assertTrue(out.rstrip().endswith("![Diagram](/api/doc/figures/fig_4.png)"))
        self.assertNotIn("#", out)

    def test_hour_long_timestamp_anchor_parses(self):
        md = "[@ 1:02:03] deep into the lecture\ntail"
        out = place_visuals(md, [_fig(5, ("ts", 3723))])

        lines = out.split("\n")
        marker = next(i for i, ln in enumerate(lines) if "1:02:03" in ln)
        self.assertIn("![Diagram]", "\n".join(lines[marker + 1: marker + 3]))

    def test_manifest_block_lists_tokens_with_locations(self):
        block = build_manifest_block([
            _fig(1, ("page", 3), caption="Flowchart"),
            _fig(2, ("ts", 760), caption="Board"),
        ])
        self.assertIn("[[FIG:1]] Flowchart (p.3)", block)
        self.assertIn("[[FIG:2]] Board (@ 12:40)", block)

    def test_empty_manifest_is_blank(self):
        self.assertEqual(build_manifest_block([]), "")


class UpdateNoteMarkdownTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._orig_db = db.DB_PATH
        db.DB_PATH = Path(self._tmp.name)
        db.init_db()
        self._orig_vs = notes.vectorstore
        self.deleted, self.added = [], []
        notes.vectorstore = type("VS", (), {
            "delete_chunks": staticmethod(lambda ids: self.deleted.extend(ids)),
            "add_chunks": staticmethod(lambda rows: self.added.extend(rows)),
        })

    def tearDown(self):
        db.DB_PATH = self._orig_db
        notes.vectorstore = self._orig_vs
        Path(self._tmp.name).unlink(missing_ok=True)

    def test_replaces_old_note_chunks_and_reindexes(self):
        item_id = db.add_item("l.pdf", "/tmp/l.pdf", "pdf")
        note_id = db.add_note(item_id, "# Old")
        stale = db.add_chunk(item_id, "old body", "Src — notes")

        notes.update_note_markdown(note_id, item_id, "# New\n\nFresh body.",
                                   "Src", "Physics")

        self.assertEqual(db.notes_for_item(item_id)[0]["markdown"], "# New\n\nFresh body.")
        self.assertIn(stale, self.deleted)
        with db.conn() as c:
            labels = [r["source_label"] for r in c.execute(
                "SELECT source_label FROM chunks WHERE item_id=?", (item_id,)).fetchall()]
        self.assertTrue(all(l.endswith("— notes") for l in labels))
        self.assertTrue(self.added and all(r["subject"] == "Physics" for r in self.added))


if __name__ == "__main__":
    unittest.main()
