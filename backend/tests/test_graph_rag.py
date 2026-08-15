import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core import db, graph_rag, mastery


class GraphGuidedRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "graph-rag.db"
        db.init_db()
        now = time.time()
        with db.conn() as c:
            goal_id = c.execute(
                "INSERT INTO exam_goals (name, slug, status, created_at) VALUES (?,?,?,?)",
                ("Computer Science", "computer-science", "ready", now),
            ).lastrowid
            self.arrays = self._concept(c, goal_id, "Arrays", 0, 0, now)
            self.stacks = self._concept(c, goal_id, "Stacks", 1, 0, now)
            self.traversal = self._concept(c, goal_id, "Graph Traversal", 2, 0, now)
            c.executemany(
                "INSERT INTO concept_edges (prereq_id, concept_id) VALUES (?,?)",
                [(self.arrays, self.stacks), (self.stacks, self.traversal)],
            )
        mastery.ensure_rows([self.arrays, self.stacks, self.traversal])
        with db.conn() as c:
            c.execute("UPDATE mastery SET p_known=0.20 WHERE concept_id=?", (self.arrays,))
            c.execute("UPDATE mastery SET p_known=0.45 WHERE concept_id=?", (self.stacks,))
            c.execute("UPDATE mastery SET p_known=0.35 WHERE concept_id=?", (self.traversal,))
            for concept_id, label, text in [
                (self.arrays, "Arrays note", "Arrays store indexed values."),
                (self.stacks, "Stacks note", "Stacks use last-in first-out order."),
                (self.traversal, "Traversal note", "DFS uses an explicit or implicit stack."),
            ]:
                item_id = c.execute(
                    "INSERT INTO items (filename, stored_path, kind, status, created_at) "
                    "VALUES (?,?,?,?,?)",
                    (f"{concept_id}.txt", f"/{concept_id}.txt", "text", "done", now),
                ).lastrowid
                chunk_id = c.execute(
                    "INSERT INTO chunks (item_id, text, source_label) VALUES (?,?,?)",
                    (item_id, text, label),
                ).lastrowid
                c.execute(
                    "INSERT INTO concept_sources (concept_id, chunk_id, score) VALUES (?,?,?)",
                    (concept_id, chunk_id, 0.1),
                )

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    @staticmethod
    def _concept(connection, goal_id, name, tier, position, now):
        return connection.execute(
            "INSERT INTO concepts (goal_id, name, blurb, tier, position, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (goal_id, name, f"Learn {name}.", tier, position, now),
        ).lastrowid

    def test_neighborhood_exposes_prerequisite_target_and_dependent(self):
        scope = graph_rag.neighborhood(self.stacks)

        self.assertEqual(
            [(row["name"], row["role"]) for row in scope["expanded"]],
            [
                ("Arrays", "prerequisite"),
                ("Stacks", "target"),
                ("Graph Traversal", "dependent"),
            ],
        )
        self.assertEqual(
            scope["paths"],
            ["Arrays -> Stacks", "Stacks -> Graph Traversal"],
        )

    @patch("core.graph_rag.reranker.rerank", side_effect=lambda _q, hits, top_k: hits[:top_k])
    @patch("core.graph_rag.vectorstore.search", return_value=[])
    def test_retrieval_organizes_graph_evidence_and_explains_it(self, _search, _rerank):
        result = graph_rag.retrieve(self.stacks, "Why does DFS use a stack?")

        self.assertEqual(
            [hit["graph_role"] for hit in result["hits"]],
            ["prerequisite", "target", "dependent"],
        )
        trace = result["retrieval_trace"]
        self.assertEqual(trace["mode"], "graph_guided")
        self.assertEqual(trace["seed_concept"]["name"], "Stacks")
        self.assertEqual(len(trace["evidence_reasons"]), 3)


if __name__ == "__main__":
    unittest.main()
