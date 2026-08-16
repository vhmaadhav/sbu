import tempfile
import unittest
from pathlib import Path

from core import db, figures
from core.config import FIGURES_DIR


class FigureExtractionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._orig_db = db.DB_PATH
        db.DB_PATH = Path(self._tmp.name)
        db.init_db()
        self._orig_gate = figures._gate
        self._written = []

    def tearDown(self):
        db.DB_PATH = self._orig_db
        figures._gate = self._orig_gate
        Path(self._tmp.name).unlink(missing_ok=True)
        for path in self._written:
            Path(path).unlink(missing_ok=True)

    def _track(self, item_id):
        for fig in db.list_doc_figures(item_id):
            self._written.append(fig["image_path"])

    def _pdf_with_drawing(self) -> str:
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        rect = fitz.Rect(120, 120, 360, 320)  # a comfortably large box
        page.draw_rect(rect, width=2)
        page.draw_line(fitz.Point(140, 150), fitz.Point(340, 150))
        page.draw_line(fitz.Point(240, 130), fitz.Point(240, 300))
        out = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False).name
        doc.save(out)
        doc.close()
        return out

    def test_kept_when_gate_returns_caption(self):
        figures._gate = lambda png: "Flowchart of the process"
        pdf = self._pdf_with_drawing()
        item_id = db.add_item("d.pdf", pdf, "pdf")

        result = figures.extract_pdf_figures(pdf, item_id)
        self._track(item_id)

        self.assertTrue(result)
        self.assertEqual(result[0]["caption"], "Flowchart of the process")
        self.assertEqual(result[0]["page"], 1)
        stored = db.list_doc_figures(item_id)
        self.assertTrue(Path(stored[0]["image_path"]).exists())
        Path(pdf).unlink(missing_ok=True)

    def test_dropped_when_gate_rejects(self):
        figures._gate = lambda png: None
        pdf = self._pdf_with_drawing()
        item_id = db.add_item("d.pdf", pdf, "pdf")

        result = figures.extract_pdf_figures(pdf, item_id)

        self.assertEqual(result, [])
        self.assertEqual(db.list_doc_figures(item_id), [])
        Path(pdf).unlink(missing_ok=True)

    def test_register_standalone_image_kept_with_no_page(self):
        from PIL import Image

        figures._gate = lambda png: "A hand-drawn flowchart"
        img_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
        Image.new("RGB", (400, 300), "white").save(img_path)
        item_id = db.add_item("photo.png", img_path, "image")

        result = figures.register_image_figure(img_path, item_id)
        self._track(item_id)

        self.assertIsNotNone(result)
        self.assertIsNone(result["page"])
        self.assertEqual(result["caption"], "A hand-drawn flowchart")
        Path(img_path).unlink(missing_ok=True)

    def test_standalone_image_kept_even_when_gate_rejects(self):
        from PIL import Image

        figures._gate = lambda png: None
        img_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
        Image.new("RGB", (400, 300), "white").save(img_path)
        item_id = db.add_item("p.png", img_path, "image")

        result = figures.register_image_figure(img_path, item_id)
        self._track(item_id)

        self.assertIsNotNone(result)
        self.assertEqual(result["caption"], "Uploaded image")
        Path(img_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
