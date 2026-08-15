import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core import concepts, db, mastery, quiz

GRAPH_PAYLOAD = {
    "concepts": [
        {"name": "Arithmetic", "blurb": "Numbers.", "prerequisites": []},
        {"name": "Algebra", "blurb": "Symbols.", "prerequisites": ["Arithmetic"]},
        {"name": "Calculus", "blurb": "Change.", "prerequisites": ["Algebra"]},
    ]
}

QUESTION_PAYLOAD = {
    "stem": "What is the derivative of x^2?",
    "options": [
        {"text": "2x", "correct": True, "misconception": ""},
        {"text": "x", "correct": False, "misconception": "drops the exponent"},
        {"text": "x^3/3", "correct": False, "misconception": "integrates instead"},
        {"text": "2", "correct": False, "misconception": "differentiates twice"},
    ],
    "explanation": "Apply the power rule.",
}


class TempDbTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "test.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()


def seed_note(markdown: str, title: str = "Note", subject: str | None = None) -> int:
    """One ingested note, so a graph build has material to read. Returns the item id."""
    now = time.time()
    with db.conn() as c:
        subject_id = None
        if subject:
            subject_id = c.execute(
                "INSERT INTO subjects (name, created_at) VALUES (?,?)", (subject, now)
            ).lastrowid
        item_id = c.execute(
            "INSERT INTO items (filename, stored_path, kind, status, title, subject_id, "
            "created_at) VALUES (?,?,?,'done',?,?,?)",
            (f"{title}.md", "", "note", title, subject_id, now),
        ).lastrowid
        c.execute(
            "INSERT INTO notes (item_id, markdown, created_at) VALUES (?,?,?)",
            (item_id, markdown, now),
        )
    return item_id


class ConceptGraphTests(TempDbTest):
    def setUp(self):
        super().setUp()
        seed_note("# Arithmetic\nNumbers.\n# Algebra\nSymbols.\n# Calculus\nChange.")

    def _goal(self) -> int:
        with db.conn() as c:
            return c.execute(
                "INSERT INTO exam_goals (name, slug, status, created_at) VALUES (?,?,?,?)",
                ("Maths", "maths", "building", time.time()),
            ).lastrowid

    def test_build_persists_concepts_edges_and_tiers(self):
        goal_id = self._goal()
        with patch("core.llm.chat_json", return_value=GRAPH_PAYLOAD), \
             patch("core.concepts.bind_sources", return_value=0):
            concepts.build(goal_id, "Maths")

        rows = concepts.list_concepts(goal_id)
        self.assertEqual([row["name"] for row in rows], ["Arithmetic", "Algebra", "Calculus"])
        self.assertEqual([row["tier"] for row in rows], [0, 1, 2])
        self.assertEqual(len(concepts.list_edges(goal_id)), 2)
        self.assertEqual(concepts.get_goal(goal_id)["status"], "ready")

    def test_build_seeds_mastery_so_charts_have_a_baseline(self):
        goal_id = self._goal()
        with patch("core.llm.chat_json", return_value=GRAPH_PAYLOAD), \
             patch("core.concepts.bind_sources", return_value=0):
            concepts.build(goal_id, "Maths")
        states = mastery.all_for_goal(goal_id)
        self.assertEqual(len(states), 3)
        self.assertTrue(all(state.p_known == mastery.P_INIT for state in states.values()))

    def test_prerequisites_the_model_invented_are_dropped(self):
        goal_id = self._goal()
        payload = {"concepts": [
            {"name": "Algebra", "blurb": "", "prerequisites": ["Nonexistent Topic"]},
        ]}
        with patch("core.llm.chat_json", return_value=payload), \
             patch("core.concepts.bind_sources", return_value=0):
            concepts.build(goal_id, "Maths")
        self.assertEqual(concepts.list_edges(goal_id), [])

    def test_a_cycle_is_flattened_rather_than_rejected(self):
        goal_id = self._goal()
        payload = {"concepts": [
            {"name": "A", "blurb": "", "prerequisites": ["B"]},
            {"name": "B", "blurb": "", "prerequisites": ["A"]},
        ]}
        with patch("core.llm.chat_json", return_value=payload), \
             patch("core.concepts.bind_sources", return_value=0):
            concepts.build(goal_id, "Maths")
        self.assertEqual(len(concepts.list_concepts(goal_id)), 2)

    def test_an_empty_response_leaves_the_goal_in_error(self):
        goal_id = self._goal()
        with patch("core.llm.chat_json", return_value={"concepts": []}):
            concepts._build_safely(goal_id, "Maths")
        goal = concepts.get_goal(goal_id)
        self.assertEqual(goal["status"], "error")
        self.assertTrue(goal["error"])

    def test_the_notes_are_what_the_model_is_asked_about(self):
        goal_id = self._goal()
        with patch("core.llm.chat_json", return_value=GRAPH_PAYLOAD) as chat, \
             patch("core.concepts.bind_sources", return_value=0):
            concepts.build(goal_id, "Maths")
        prompt = chat.call_args.args[1]
        self.assertIn("Arithmetic", prompt)  # the note's own headings reached the model
        self.assertIn("only the concepts these notes actually teach", prompt)

    def test_a_goal_with_no_notes_behind_it_is_refused(self):
        with db.conn() as c:
            c.execute("DELETE FROM notes")
        goal_id = self._goal()
        with patch("core.llm.chat_json", return_value=GRAPH_PAYLOAD) as chat:
            concepts._build_safely(goal_id, "Maths")
        chat.assert_not_called()
        goal = concepts.get_goal(goal_id)
        self.assertEqual(goal["status"], "error")
        self.assertIn("no notes", goal["error"])

    def test_concepts_no_note_supports_are_dropped(self):
        goal_id = self._goal()

        def bind(_goal_id):
            # Only "Algebra" finds material; the other two are the model's invention.
            with db.conn() as c:
                item_id = c.execute(
                    "SELECT id FROM items ORDER BY id LIMIT 1"
                ).fetchone()["id"]
                chunk_id = c.execute(
                    "INSERT INTO chunks (item_id, text, source_label) VALUES (?,?,?)",
                    (item_id, "Symbols stand for numbers.", "Note"),
                ).lastrowid
                concept_id = c.execute(
                    "SELECT id FROM concepts WHERE goal_id=? AND name='Algebra'", (goal_id,)
                ).fetchone()["id"]
                c.execute(
                    "INSERT INTO concept_sources (concept_id, chunk_id, score) VALUES (?,?,?)",
                    (concept_id, chunk_id, 0.2),
                )
            return 1

        with patch("core.llm.chat_json", return_value=GRAPH_PAYLOAD), \
             patch("core.concepts.bind_sources", side_effect=bind):
            concepts.build(goal_id, "Maths")

        self.assertEqual([row["name"] for row in concepts.list_concepts(goal_id)], ["Algebra"])
        self.assertEqual(concepts.list_edges(goal_id), [])

    def test_the_graph_survives_a_vector_index_that_bound_nothing(self):
        goal_id = self._goal()
        with patch("core.llm.chat_json", return_value=GRAPH_PAYLOAD), \
             patch("core.concepts.bind_sources", return_value=0):
            concepts.build(goal_id, "Maths")
        self.assertEqual(len(concepts.list_concepts(goal_id)), 3)

    def test_deleting_a_goal_removes_everything_derived_from_it(self):
        goal_id = self._goal()
        with patch("core.llm.chat_json", return_value=GRAPH_PAYLOAD), \
             patch("core.concepts.bind_sources", return_value=0):
            concepts.build(goal_id, "Maths")
        concepts.delete_goal(goal_id)
        self.assertIsNone(concepts.get_goal(goal_id))
        self.assertEqual(concepts.list_concepts(goal_id), [])


class QuizTests(TempDbTest):
    def setUp(self):
        super().setUp()
        now = time.time()
        with db.conn() as c:
            self.goal_id = c.execute(
                "INSERT INTO exam_goals (name, slug, status, created_at) VALUES (?,?,?,?)",
                ("Maths", "maths", "ready", now),
            ).lastrowid
            self.concept_id = c.execute(
                "INSERT INTO concepts (goal_id, name, blurb, tier, position, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (self.goal_id, "Derivatives", "Rates of change.", 0, 0, now),
            ).lastrowid
        mastery.ensure_rows([self.concept_id])
        # Questions are written from the student's own notes, so bind one.
        item_id = seed_note("# Derivatives\nThe power rule.")
        with db.conn() as c:
            chunk_id = c.execute(
                "INSERT INTO chunks (item_id, text, source_label) VALUES (?,?,?)",
                (item_id, "The derivative of x^n is n*x^(n-1).", "Derivatives note"),
            ).lastrowid
            c.execute(
                "INSERT INTO concept_sources (concept_id, chunk_id, score) VALUES (?,?,?)",
                (self.concept_id, chunk_id, 0.1),
            )

    def _generate(self) -> int:
        with patch("core.llm.chat_json", return_value=QUESTION_PAYLOAD):
            return quiz.generate(self.concept_id)

    def test_a_generated_question_hides_its_answer_from_the_client(self):
        question_id = self._generate()
        payload = quiz.get_question(question_id)
        self.assertEqual(len(payload["options"]), 4)
        self.assertNotIn("answer_index", payload)
        self.assertNotIn("misconceptions", payload)

    def test_every_wrong_option_carries_a_misconception(self):
        question_id = self._generate()
        revealed = quiz.get_question(question_id, reveal=True)
        for index, tag in enumerate(revealed["misconceptions"]):
            if index == revealed["answer_index"]:
                self.assertEqual(tag, "")
            else:
                self.assertTrue(tag)

    def test_a_response_without_exactly_one_answer_is_rejected(self):
        payload = {
            "stem": "Broken",
            "options": [{"text": "a", "correct": True}, {"text": "b", "correct": True}],
            "explanation": "",
        }
        with patch("core.llm.chat_json", return_value=payload):
            with self.assertRaises(ValueError):
                quiz.generate(self.concept_id)

    def test_grading_a_correct_answer_raises_mastery(self):
        question_id = self._generate()
        answer = quiz.get_question(question_id, reveal=True)["answer_index"]
        result = quiz.grade(question_id, answer)
        self.assertTrue(result["correct"])
        self.assertIsNone(result["misconception"])
        self.assertGreater(result["p_known"], mastery.P_INIT)

    def test_grading_a_wrong_answer_records_its_misconception(self):
        question_id = self._generate()
        revealed = quiz.get_question(question_id, reveal=True)
        wrong = next(i for i in range(4) if i != revealed["answer_index"])
        result = quiz.grade(question_id, wrong)
        self.assertFalse(result["correct"])
        self.assertTrue(result["misconception"])
        self.assertLess(result["p_known"], mastery.P_INIT)

    def test_repeated_errors_group_into_misconceptions(self):
        question_id = self._generate()
        revealed = quiz.get_question(question_id, reveal=True)
        wrong = next(i for i in range(4) if i != revealed["answer_index"])
        quiz.grade(question_id, wrong)
        quiz.grade(question_id, wrong)

        grouped = quiz.misconception_counts(self.goal_id)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["count"], 2)
        self.assertEqual(grouped[0]["tag"], revealed["misconceptions"][wrong])

    def test_a_concept_with_no_notes_is_never_quizzed_from_general_knowledge(self):
        with db.conn() as c:
            c.execute("DELETE FROM concept_sources WHERE concept_id=?", (self.concept_id,))
        with patch("core.llm.chat_json", return_value=QUESTION_PAYLOAD) as chat:
            with self.assertRaises(ValueError):
                quiz.generate(self.concept_id)
        chat.assert_not_called()

    def test_a_cached_question_is_served_when_generation_fails(self):
        cached = self._generate()
        with patch("core.llm.chat_json", side_effect=RuntimeError("LM Studio is down")):
            self.assertEqual(quiz.question_for(self.concept_id), cached)

    def test_nothing_is_served_when_generation_fails_with_no_cache(self):
        with patch("core.llm.chat_json", side_effect=RuntimeError("LM Studio is down")):
            self.assertIsNone(quiz.question_for(self.concept_id))


if __name__ == "__main__":
    unittest.main()
