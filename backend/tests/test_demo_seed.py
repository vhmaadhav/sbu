import tempfile
import unittest
from pathlib import Path

from core import db, graph_rag
from scripts import seed_axiom_trace_demo


class DemoSeedTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "demo.db"

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_seed_is_repeatable_and_exposes_a_weak_prerequisite_path(self):
        files = Path(self.temp_dir.name) / "files"
        first = seed_axiom_trace_demo.seed(files)
        second = seed_axiom_trace_demo.seed(files)

        self.assertEqual(first["concepts"], 8)
        self.assertEqual(second["concepts"], 8)
        self.assertEqual(len(db.list_capture_events()), 3)
        scope = graph_rag.neighborhood(second["focus_concept_id"])
        self.assertEqual(scope["target"]["name"], "Depth-First Search")
        self.assertIn("Stacks -> Depth-First Search", scope["paths"])
        self.assertIn("Recursion -> Depth-First Search", scope["paths"])


if __name__ == "__main__":
    unittest.main()
