import unittest

from pet.models import ActivitySample, ContextSnapshot, Mood, Stage, Thresholds
from pet.runner import RING_SIZE, PetRunner

T = Thresholds(
    notice=10.0,
    concerned=20.0,
    nag=30.0,
    plead=40.0,
    recovery=10.0,
    bubble_cooldown=10.0,
    plead_repeat=20.0,
    poll=5.0,
)


class FakeWindow:
    def __init__(self):
        self.renders = []
        self.ticks = 0

    def render(self, mood, walk_to=None, bubble=None):
        self.renders.append((mood, walk_to, bubble))

    def tick(self):
        self.ticks += 1


class FakeContext:
    def snapshot(self):
        return ContextSnapshot(next_deadline="OS exam tomorrow")


def runner(window, labels, *, locate=lambda sample: 400.0):
    schedule = iter(labels)

    def sampler(at):
        return ActivitySample(at=at, app="Safari", host="youtube.com")

    return PetRunner(
        window=window,
        sampler=sampler,
        classify=lambda sample: next(schedule),
        context=FakeContext(),
        speak=lambda event, snapshot: f"line:{event.stage.value}",
        thresholds=T,
        locate=locate,
    )


class TickTests(unittest.TestCase):
    def test_a_quiet_tick_still_animates_the_window(self):
        window = FakeWindow()
        target = runner(window, ["study"] * 3)
        for step in range(3):
            target.tick(now=step * 5.0)
        self.assertEqual(window.ticks, 3)
        self.assertEqual(window.renders, [])

    def test_crossing_a_threshold_renders_the_new_mood(self):
        window = FakeWindow()
        target = runner(window, ["distraction"] * 5)
        for step in range(5):
            target.tick(now=step * 5.0)
        moods = [render[0] for render in window.renders]
        self.assertIn(Mood.ALERT, moods)

    def test_a_speaking_event_renders_the_line_and_a_walk_target(self):
        window = FakeWindow()
        target = runner(window, ["distraction"] * 8)
        for step in range(8):
            target.tick(now=step * 5.0)
        spoken = [render for render in window.renders if render[2] is not None]
        self.assertTrue(spoken)
        mood, walk_to, bubble = spoken[0]
        self.assertEqual(walk_to, 400.0)
        self.assertTrue(bubble.startswith("line:"))

    def test_an_unlocatable_window_still_nudges_without_walking(self):
        window = FakeWindow()
        target = runner(window, ["distraction"] * 8, locate=lambda sample: None)
        for step in range(8):
            target.tick(now=step * 5.0)
        spoken = [render for render in window.renders if render[2] is not None]
        self.assertTrue(spoken)
        self.assertIsNone(spoken[0][1])

    def test_a_failing_sampler_does_not_stop_the_loop(self):
        window = FakeWindow()
        target = PetRunner(
            window=window,
            sampler=lambda at: (_ for _ in ()).throw(RuntimeError("no window server")),
            classify=lambda sample: "distraction",
            context=FakeContext(),
            speak=lambda event, snapshot: "x",
            thresholds=T,
            locate=lambda sample: None,
        )
        target.tick(now=0.0)
        target.tick(now=5.0)
        self.assertEqual(window.ticks, 2)

    def test_a_failing_speak_falls_back_to_silence_not_a_crash(self):
        window = FakeWindow()

        def boom(event, snapshot):
            raise RuntimeError("voice down")

        target = runner(window, ["distraction"] * 8)
        target._speak = boom
        for step in range(8):
            target.tick(now=step * 5.0)
        self.assertGreaterEqual(window.ticks, 8)


class RingBufferTests(unittest.TestCase):
    def test_keeps_only_the_most_recent_samples(self):
        window = FakeWindow()
        target = runner(window, ["neutral"] * (RING_SIZE + 50))
        for step in range(RING_SIZE + 50):
            target.tick(now=step * 5.0)
        self.assertEqual(len(target.recent), RING_SIZE)
        self.assertEqual(target.recent[-1].at, (RING_SIZE + 49) * 5.0)


if __name__ == "__main__":
    unittest.main()
