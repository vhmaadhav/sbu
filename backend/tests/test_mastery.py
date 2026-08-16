import tempfile
import time
import unittest
from pathlib import Path

from core import db, mastery


class BktTests(unittest.TestCase):
    def test_correct_answer_raises_the_posterior(self):
        self.assertGreater(mastery.update(0.25, correct=True), 0.25)

    def test_wrong_answer_lowers_the_posterior(self):
        self.assertLess(mastery.update(0.60, correct=False), 0.60)

    def test_repeated_correct_answers_converge_toward_mastery(self):
        p = mastery.P_INIT
        for _ in range(8):
            p = mastery.update(p, correct=True)
        self.assertGreater(p, mastery.MASTERED_THRESHOLD)

    def test_posterior_stays_inside_the_unit_interval(self):
        p = 0.999
        for _ in range(20):
            p = mastery.update(p, correct=True)
        self.assertLess(p, 1.0)

        p = 0.001
        for _ in range(20):
            p = mastery.update(p, correct=False)
        self.assertGreater(p, 0.0)

    def test_a_guess_moves_less_than_certain_knowledge_would(self):
        # With a 25% guess floor, one correct answer from the prior must not by
        # itself declare mastery.
        self.assertLess(mastery.update(mastery.P_INIT, correct=True),
                        mastery.MASTERED_THRESHOLD)


class ConfidenceTests(unittest.TestCase):
    def test_untested_concepts_have_no_confidence(self):
        self.assertEqual(mastery.confidence(0), 0.0)

    def test_confidence_grows_with_attempts(self):
        self.assertLess(mastery.confidence(1), mastery.confidence(5))
        self.assertLess(mastery.confidence(5), mastery.confidence(20))
        self.assertLess(mastery.confidence(20), 1.0)


class ForgettingTests(unittest.TestCase):
    def test_recall_is_one_half_after_exactly_one_half_life(self):
        now = 1_000_000.0
        reviewed = now - mastery.DAY_SECONDS * 3
        self.assertAlmostEqual(mastery.recall(3.0, reviewed, now), 0.5, places=6)

    def test_recall_decays_with_elapsed_time(self):
        now = 1_000_000.0
        fresh = mastery.recall(2.0, now - mastery.DAY_SECONDS, now)
        stale = mastery.recall(2.0, now - mastery.DAY_SECONDS * 6, now)
        self.assertGreater(fresh, stale)

    def test_risk_is_the_complement_of_recall(self):
        now = 1_000_000.0
        reviewed = now - mastery.DAY_SECONDS * 2
        self.assertAlmostEqual(
            mastery.recall(2.0, reviewed, now) + mastery.risk(2.0, reviewed, now), 1.0
        )

    def test_a_longer_half_life_delays_the_due_date(self):
        now = 1_000_000.0
        short = mastery.days_until_due(1.0, now, now)
        long = mastery.days_until_due(8.0, now, now)
        self.assertGreater(long, short)

    def test_an_overdue_concept_reports_zero_days(self):
        now = 1_000_000.0
        self.assertEqual(mastery.days_until_due(1.0, now - mastery.DAY_SECONDS * 30, now), 0.0)

    def test_success_grows_the_half_life_and_failure_cuts_it(self):
        self.assertGreater(mastery.next_half_life(2.0, correct=True), 2.0)
        self.assertLess(mastery.next_half_life(2.0, correct=False), 2.0)


class MasteryPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "test.db"
        db.init_db()
        now = time.time()
        with db.conn() as c:
            self.goal_id = c.execute(
                "INSERT INTO exam_goals (name, slug, status, created_at) VALUES (?,?,?,?)",
                ("Test Exam", "test-exam", "ready", now),
            ).lastrowid
            self.concept_id = c.execute(
                "INSERT INTO concepts (goal_id, name, blurb, tier, position, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (self.goal_id, "Limits", "", 0, 0, now),
            ).lastrowid

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_ensure_rows_seeds_the_prior_and_a_history_point(self):
        mastery.ensure_rows([self.concept_id])
        state = mastery.get(self.concept_id)
        self.assertAlmostEqual(state.p_known, mastery.P_INIT)
        self.assertEqual(len(mastery.history(self.goal_id)), 1)

    def test_applying_attempts_records_history_for_the_curve(self):
        mastery.ensure_rows([self.concept_id])
        mastery.apply_attempt(self.concept_id, correct=True)
        mastery.apply_attempt(self.concept_id, correct=True)
        state = mastery.get(self.concept_id)
        self.assertEqual(state.attempts, 2)
        self.assertEqual(state.correct, 2)
        self.assertEqual(len(mastery.history(self.goal_id)), 3)  # prior + two updates

    def test_a_concept_enters_the_review_queue_once_mastered(self):
        mastery.ensure_rows([self.concept_id])
        for _ in range(8):
            mastery.apply_attempt(self.concept_id, correct=True)
        self.assertTrue(mastery.get(self.concept_id).in_srs)
        queue = mastery.due_queue(self.goal_id)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["name"], "Limits")

    def test_an_unmastered_concept_is_not_queued_for_review(self):
        mastery.ensure_rows([self.concept_id])
        mastery.apply_attempt(self.concept_id, correct=False)
        self.assertEqual(mastery.due_queue(self.goal_id), [])


if __name__ == "__main__":
    unittest.main()
