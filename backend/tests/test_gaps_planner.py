import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core import concepts, db, gaps, mastery, planner


class GraphFixture(unittest.TestCase):
    """A three-tier chain plus a sibling:

        Arithmetic ──► Algebra ──► Calculus
        Arithmetic ──► Geometry
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "test.db"
        db.init_db()
        now = time.time()
        with db.conn() as c:
            self.goal_id = c.execute(
                "INSERT INTO exam_goals (name, slug, status, created_at) VALUES (?,?,?,?)",
                ("Maths", "maths", "ready", now),
            ).lastrowid
            self.ids = {}
            for name, tier, position in [
                ("Arithmetic", 0, 0), ("Algebra", 1, 0),
                ("Geometry", 1, 1), ("Calculus", 2, 0),
            ]:
                self.ids[name] = c.execute(
                    "INSERT INTO concepts (goal_id, name, blurb, tier, position, created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (self.goal_id, name, "", tier, position, now),
                ).lastrowid
            c.executemany(
                "INSERT INTO concept_edges (prereq_id, concept_id) VALUES (?,?)",
                [
                    (self.ids["Arithmetic"], self.ids["Algebra"]),
                    (self.ids["Arithmetic"], self.ids["Geometry"]),
                    (self.ids["Algebra"], self.ids["Calculus"]),
                ],
            )
        mastery.ensure_rows(list(self.ids.values()))

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def set_mastery(self, name: str, p_known: float) -> None:
        with db.conn() as c:
            c.execute(
                "UPDATE mastery SET p_known=?, attempts=5 WHERE concept_id=?",
                (p_known, self.ids[name]),
            )


class DownstreamTests(GraphFixture):
    def test_transitive_reach_is_counted(self):
        counts = concepts.downstream_counts(self.goal_id)
        self.assertEqual(counts[self.ids["Arithmetic"]], 3)  # Algebra, Geometry, Calculus
        self.assertEqual(counts[self.ids["Algebra"]], 1)
        self.assertEqual(counts[self.ids["Calculus"]], 0)


class GapTests(GraphFixture):
    def test_a_strong_graph_reports_no_gaps(self):
        for name in self.ids:
            self.set_mastery(name, 0.9)
        self.assertEqual(gaps.rank(self.goal_id), [])

    def test_a_weak_prerequisite_is_flagged_as_a_missing_foundation(self):
        self.set_mastery("Arithmetic", 0.2)
        self.set_mastery("Algebra", 0.3)
        self.set_mastery("Geometry", 0.9)
        self.set_mastery("Calculus", 0.9)

        missing = gaps.missing_prerequisites(self.goal_id)
        self.assertEqual([row["name"] for row in missing], ["Arithmetic"])
        self.assertIn("Algebra", missing[0]["blocking"])

    def test_gaps_are_ordered_foundations_first(self):
        for name in self.ids:
            self.set_mastery(name, 0.2)
        ranked = gaps.rank(self.goal_id)
        self.assertEqual(ranked[0]["name"], "Arithmetic")
        self.assertEqual(ranked[-1]["name"], "Calculus")

    def test_a_never_tested_concept_says_so(self):
        reasons = {row["name"]: row["reason"] for row in gaps.rank(self.goal_id)}
        self.assertEqual(reasons["Calculus"], "Not yet tested")

    def test_summary_counts_mastered_and_weak(self):
        self.set_mastery("Arithmetic", 0.95)
        summary = gaps.summary(self.goal_id)
        self.assertEqual(summary["concepts"], 4)
        self.assertEqual(summary["mastered"], 1)
        self.assertEqual(summary["weak"], 3)


class PlannerTests(GraphFixture):
    def test_the_diagnostic_sweeps_across_tiers_before_going_deep(self):
        ordered = planner._diagnostic_concepts(self.goal_id)
        names = [concepts.get_concept(cid)["name"] for cid in ordered]
        self.assertEqual(names[:3], ["Arithmetic", "Algebra", "Calculus"])
        self.assertLessEqual(len(names), planner.DIAGNOSTIC_LENGTH)

    def test_a_session_puts_missing_prerequisites_first(self):
        self.set_mastery("Arithmetic", 0.2)
        self.set_mastery("Algebra", 0.3)
        self.set_mastery("Geometry", 0.9)
        self.set_mastery("Calculus", 0.9)

        plan = planner._study_plan(self.goal_id)
        first = concepts.get_concept(plan[0][0])["name"]
        self.assertEqual(first, "Arithmetic")
        self.assertEqual(plan[0][1], "read")

    def test_a_concept_drill_stays_on_one_concept(self):
        plan = planner._study_plan(self.goal_id, concept_id=self.ids["Geometry"])
        self.assertTrue(all(cid == self.ids["Geometry"] for cid, _ in plan))
        self.assertEqual(plan[0][1], "read")

    def test_a_fully_mastered_graph_still_produces_a_session(self):
        for name in self.ids:
            self.set_mastery(name, 0.95)
        self.assertTrue(planner._study_plan(self.goal_id))

    def test_a_session_never_exceeds_its_length(self):
        for name in self.ids:
            self.set_mastery(name, 0.1)
        self.assertLessEqual(len(planner._study_plan(self.goal_id)), planner.SESSION_LENGTH)

    def test_an_item_is_skipped_rather_than_stalling_when_no_question_exists(self):
        session_id = planner.start_session(self.goal_id)
        with patch("core.quiz.question_for", return_value=None):
            item = planner.next_item(session_id)
            # Reading needs no model, so it is still served; every quiz after it
            # is skipped rather than left waiting on an unreachable LLM.
            while item is not None and item["kind"] == "read":
                planner.mark_read(item["item_id"])
                item = planner.next_item(session_id)
            self.assertIsNone(item)
        self.assertEqual(planner.state(session_id)["status"], "complete")


if __name__ == "__main__":
    unittest.main()
