import unittest
from unittest.mock import patch

from pet import voice
from pet.models import ActivitySample, ContextSnapshot, Mood, NudgeEvent, Stage

SAMPLE = ActivitySample(
    at=200.0,
    app="Safari",
    title="YouTube",
    host="youtube.com",
    tab_title="10 hours of lofi drum solos",
)


def event(stage=Stage.NAG, recovered=False):
    return NudgeEvent(
        at=200.0,
        stage=stage,
        mood=Mood.CONCERNED,
        speak=True,
        recovered=recovered,
        sample=SAMPLE,
    )


CONTEXT = ContextSnapshot(
    next_deadline="DBMS exam in 2 days",
    open_task_count=4,
    weakest_concepts=("Normalization", "Indexing"),
)


class SanitizeTests(unittest.TestCase):
    def test_collapses_whitespace_and_newlines(self):
        self.assertEqual(voice.sanitize("  two\n lines\there "), "two lines here")

    def test_strips_markdown_and_surrounding_quotes(self):
        self.assertEqual(voice.sanitize('"**Get back** to _work_"'), "Get back to work")

    def test_truncates_at_a_word_boundary_within_the_cap(self):
        result = voice.sanitize("word " * 60)
        self.assertLessEqual(len(result), voice.MAX_CHARS)
        self.assertFalse(result.endswith("wor"))

    def test_a_single_unbroken_token_is_hard_truncated(self):
        result = voice.sanitize("x" * 400)
        self.assertLessEqual(len(result), voice.MAX_CHARS)


class LineTests(unittest.TestCase):
    def test_uses_the_llm_answer_when_it_is_usable(self):
        with patch("pet.voice.llm.chat", return_value="Normalization will not learn itself."):
            self.assertEqual(
                voice.line(event(), CONTEXT), "Normalization will not learn itself."
            )

    def test_prompt_carries_the_activity_and_the_context(self):
        with patch("pet.voice.llm.chat", return_value="ok") as chat:
            voice.line(event(), CONTEXT)
        prompt = chat.call_args.args[1]
        self.assertIn("youtube.com", prompt)
        self.assertIn("10 hours of lofi drum solos", prompt)
        self.assertIn("DBMS exam in 2 days", prompt)
        self.assertIn("Normalization", prompt)

    def test_llm_output_is_sanitized(self):
        with patch("pet.voice.llm.chat", return_value='  "**Back to it.**"\n\n'):
            self.assertEqual(voice.line(event(), CONTEXT), "Back to it.")

    def test_llm_failure_falls_back_to_a_canned_line_for_the_stage(self):
        with patch("pet.voice.llm.chat", side_effect=TimeoutError("slow")):
            result = voice.line(event(stage=Stage.PLEAD), CONTEXT)
        self.assertIn(result, voice.CANNED[Stage.PLEAD.value])

    def test_blank_llm_output_falls_back(self):
        with patch("pet.voice.llm.chat", return_value="   \n  "):
            result = voice.line(event(stage=Stage.CONCERNED), CONTEXT)
        self.assertIn(result, voice.CANNED[Stage.CONCERNED.value])

    def test_recovery_uses_the_recovered_pool_when_the_llm_is_down(self):
        with patch("pet.voice.llm.chat", side_effect=RuntimeError("down")):
            result = voice.line(event(stage=Stage.CALM, recovered=True), CONTEXT)
        self.assertIn(result, voice.CANNED["recovered"])

    def test_every_canned_line_respects_the_cap(self):
        for pool in voice.CANNED.values():
            for candidate in pool:
                self.assertLessEqual(len(candidate), voice.MAX_CHARS)

    def test_empty_context_still_produces_a_line(self):
        with patch("pet.voice.llm.chat", side_effect=RuntimeError("down")):
            result = voice.line(event(), ContextSnapshot())
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
