import tempfile
import unittest
from pathlib import Path

from core import db


class DocFigureDbTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._orig = db.DB_PATH
        db.DB_PATH = Path(self._tmp.name)
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self._orig
        Path(self._tmp.name).unlink(missing_ok=True)

    def test_add_list_and_get_figure(self):
        item_id = db.add_item("lecture.pdf", "/tmp/lecture.pdf", "pdf")
        fig_id = db.add_doc_figure(item_id, page=3, caption="Flowchart", image_path="/tmp/f.png")

        got = db.get_doc_figure(fig_id)
        self.assertEqual(got["page"], 3)
        self.assertEqual(got["caption"], "Flowchart")
        self.assertEqual([f["id"] for f in db.list_doc_figures(item_id)], [fig_id])

    def test_delete_returns_paths_and_clears_rows(self):
        item_id = db.add_item("x.pdf", "/tmp/x.pdf", "pdf")
        db.add_doc_figure(item_id, page=1, caption="a", image_path="/tmp/a.png")
        db.add_doc_figure(item_id, page=None, caption="b", image_path="/tmp/b.png")

        paths = db.delete_doc_figures_for_item(item_id)

        self.assertCountEqual(paths, ["/tmp/a.png", "/tmp/b.png"])
        self.assertEqual(db.list_doc_figures(item_id), [])

    def test_update_note_changes_markdown(self):
        item_id = db.add_item("n.txt", "/tmp/n.txt", "text")
        note_id = db.add_note(item_id, "# Original")

        db.update_note(note_id, "# Edited")

        self.assertEqual(db.notes_for_item(item_id)[0]["markdown"], "# Edited")


if __name__ == "__main__":
    unittest.main()
