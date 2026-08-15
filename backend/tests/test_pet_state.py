import unittest

from pet.models import ActivitySample, Mood, Stage, Thresholds
from pet.state import PetState, advance

T = Thresholds(
    notice=90.0,
    concerned=180.0,
    nag=360.0,
    plead=600.0,
    recovery=60.0,
    bubble_cooldown=90.0,
    plead_repeat=240.0,
    poll=5.0,
)


def run(labels_over_time, state=None):
    """Feed (timestamp, label) pairs; return the final state and every event."""
    state = state or PetState()
    events = []
    for at, label in labels_over_time:
        sample = ActivitySample(at=at, app="Safari", host="youtube.com")
        state, event = advance(state, sample, label, T)
        if event is not None:
            events.append(event)
    return state, events


def steady(label, start, stop, step=5.0):
    at = start
    while at <= stop:
        yield (at, label)
        at += step


class LadderTests(unittest.TestCase):
    def test_stays_calm_and_silent_below_the_notice_threshold(self):
        state, events = run(list(steady("distraction", 0.0, 85.0)))
        self.assertEqual(state.stage, Stage.CALM)
        self.assertEqual(events, [])

    def test_reaches_notice_without_speaking(self):
        state, events = run(list(steady("distraction", 0.0, 95.0)))
        self.assertEqual(state.stage, Stage.NOTICE)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].stage, Stage.NOTICE)
        self.assertFalse(events[0].speak)
        self.assertEqual(events[0].mood, Mood.ALERT)

    def test_reaches_concerned_and_speaks(self):
        state, events = run(list(steady("distraction", 0.0, 185.0)))
        self.assertEqual(state.stage, Stage.CONCERNED)
        spoken = [event for event in events if event.speak]
        self.assertEqual(len(spoken), 1)
        self.assertEqual(spoken[0].stage, Stage.CONCERNED)

    def test_climbs_every_stage_in_order_over_a_long_distraction(self):
        _, events = run(list(steady("distraction", 0.0, 620.0)))
        stages = [event.stage for event in events]
        self.assertEqual(
            stages[:4],
            [Stage.NOTICE, Stage.CONCERNED, Stage.NAG, Stage.PLEAD],
        )

    def test_plead_uses_the_sad_mood(self):
        _, events = run(list(steady("distraction", 0.0, 605.0)))
        self.assertEqual(events[-1].mood, Mood.SAD)

    def test_a_single_huge_time_gap_cannot_skip_stages(self):
        state = PetState()
        first = ActivitySample(at=0.0, app="Safari", host="youtube.com")
        state, _ = advance(state, first, "distraction", T)
        # The laptop was closed for an hour.
        later = ActivitySample(at=3600.0, app="Safari", host="youtube.com")
        state, event = advance(state, later, "distraction", T)
        self.assertEqual(state.stage, Stage.CALM)
        self.assertIsNone(event)
        self.assertLessEqual(state.dwell, 3 * T.poll)


class DecayAndResetTests(unittest.TestCase):
    def test_study_resets_dwell_immediately(self):
        state, _ = run(list(steady("distraction", 0.0, 170.0)))
        self.assertGreater(state.dwell, 160.0)
        state, _ = run([(175.0, "study")], state=state)
        self.assertEqual(state.dwell, 0.0)

    def test_neutral_decays_dwell_at_half_rate(self):
        state, _ = run([(0.0, "distraction"), (10.0, "distraction")])
        self.assertEqual(state.dwell, 10.0)
        state, _ = run([(20.0, "neutral")], state=state)
        self.assertEqual(state.dwell, 5.0)

    def test_neutral_never_drives_dwell_negative(self):
        state, _ = run([(0.0, "neutral"), (600.0, "neutral"), (1200.0, "neutral")])
        self.assertEqual(state.dwell, 0.0)
        self.assertEqual(state.stage, Stage.CALM)

    def test_recovery_needs_a_full_run_of_study_then_resets_and_speaks(self):
        state, _ = run(list(steady("distraction", 0.0, 200.0)))
        self.assertEqual(state.stage, Stage.CONCERNED)
        state, events = run(list(steady("study", 205.0, 240.0)), state=state)
        self.assertEqual(state.stage, Stage.CONCERNED, "30s of study is not recovery yet")
        self.assertEqual(events, [])
        state, events = run(list(steady("study", 245.0, 280.0)), state=state)
        self.assertEqual(state.stage, Stage.CALM)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].recovered)
        self.assertEqual(events[0].mood, Mood.IDLE)

    def test_recovery_hard_on_the_heels_of_a_nag_resets_but_stays_quiet(self):
        # The bubble floor outranks the acknowledgement: the sprite turns happy
        # immediately, but the pet does not speak twice inside the cooldown.
        state, _ = run(list(steady("distraction", 0.0, 200.0)))
        state, events = run(list(steady("study", 205.0, 280.0)), state=state)
        self.assertEqual(state.stage, Stage.CALM)
        self.assertTrue(events[0].recovered)
        self.assertFalse(events[0].speak)

    def test_recovery_speaks_once_the_cooldown_has_passed(self):
        state, _ = run(list(steady("distraction", 0.0, 200.0)))
        state, _ = run(list(steady("neutral", 205.0, 290.0)), state=state)
        state, events = run(list(steady("study", 295.0, 360.0)), state=state)
        self.assertTrue(events[0].recovered)
        self.assertTrue(events[0].speak)

    def test_distraction_interrupts_a_recovery_run(self):
        state, _ = run(list(steady("distraction", 0.0, 200.0)))
        state, _ = run(list(steady("study", 205.0, 250.0)), state=state)
        state, _ = run([(255.0, "distraction")], state=state)
        self.assertEqual(state.study_run, 0.0)


class CooldownTests(unittest.TestCase):
    def test_plead_repeats_only_after_the_repeat_interval(self):
        _, events = run(list(steady("distraction", 0.0, 900.0)))
        plead_bubbles = [
            event for event in events if event.stage == Stage.PLEAD and event.speak
        ]
        self.assertGreaterEqual(len(plead_bubbles), 2)
        gaps = [
            second.at - first.at
            for first, second in zip(plead_bubbles, plead_bubbles[1:])
        ]
        for gap in gaps:
            self.assertGreaterEqual(gap, T.plead_repeat)

    def test_no_two_bubbles_are_closer_than_the_cooldown(self):
        _, events = run(list(steady("distraction", 0.0, 1200.0)))
        spoken = [event.at for event in events if event.speak]
        gaps = [second - first for first, second in zip(spoken, spoken[1:])]
        for gap in gaps:
            self.assertGreaterEqual(gap, T.bubble_cooldown)

    def test_a_hostile_flapping_timeline_still_respects_the_cooldown(self):
        timeline = []
        at = 0.0
        for index in range(400):
            timeline.append((at, "distraction" if index % 7 else "neutral"))
            at += 5.0
        _, events = run(timeline)
        spoken = [event.at for event in events if event.speak]
        gaps = [second - first for first, second in zip(spoken, spoken[1:])]
        for gap in gaps:
            self.assertGreaterEqual(gap, T.bubble_cooldown)


if __name__ == "__main__":
    unittest.main()
