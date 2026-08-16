import unittest

from pet.models import (
    ActivitySample,
    ContextSnapshot,
    Mood,
    NudgeEvent,
    STAGE_ORDER,
    Stage,
    Thresholds,
)


class ModelTests(unittest.TestCase):
    def test_stage_order_runs_from_calm_to_plead(self):
        self.assertEqual(
            STAGE_ORDER,
            (Stage.CALM, Stage.NOTICE, Stage.CONCERNED, Stage.NAG, Stage.PLEAD),
        )
        self.assertEqual(STAGE_ORDER.index(Stage.NAG), 3)

    def test_activity_sample_is_frozen_and_defaults_to_no_browser_tab(self):
        sample = ActivitySample(at=10.0, app="Safari")
        self.assertEqual(sample.title, "")
        self.assertIsNone(sample.host)
        self.assertIsNone(sample.tab_title)
        with self.assertRaises(Exception):
            sample.app = "Chrome"

    def test_nudge_event_carries_the_sample_that_caused_it(self):
        sample = ActivitySample(at=10.0, app="Safari", host="youtube.com")
        event = NudgeEvent(
            at=10.0,
            stage=Stage.NAG,
            mood=Mood.CONCERNED,
            speak=True,
            recovered=False,
            sample=sample,
        )
        self.assertEqual(event.sample.host, "youtube.com")
        self.assertTrue(event.speak)

    def test_context_snapshot_defaults_are_empty_not_none(self):
        snapshot = ContextSnapshot()
        self.assertIsNone(snapshot.next_deadline)
        self.assertEqual(snapshot.open_task_count, 0)
        self.assertEqual(snapshot.weakest_concepts, ())

    def test_thresholds_from_config_uses_the_spec_defaults(self):
        thresholds = Thresholds.from_config()
        self.assertEqual(thresholds.notice, 90.0)
        self.assertEqual(thresholds.concerned, 180.0)
        self.assertEqual(thresholds.nag, 360.0)
        self.assertEqual(thresholds.plead, 600.0)
        self.assertEqual(thresholds.recovery, 60.0)
        self.assertEqual(thresholds.bubble_cooldown, 90.0)
        self.assertEqual(thresholds.plead_repeat, 240.0)
        self.assertEqual(thresholds.poll, 5.0)


class ConfigTests(unittest.TestCase):
    def test_pet_constants_are_exported_with_spec_defaults(self):
        from core import config

        self.assertEqual(config.PET_POLL_SECONDS, 5)
        self.assertEqual(config.PET_NOTICE_SECONDS, 90)
        self.assertEqual(config.PET_BACKEND_URL, "http://127.0.0.1:8010")
        self.assertIsInstance(config.PET_STUDY_APPS, tuple)
        self.assertIsInstance(config.PET_DISTRACT_HOSTS, tuple)


if __name__ == "__main__":
    unittest.main()
