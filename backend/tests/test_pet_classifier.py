import unittest
from unittest.mock import patch

from pet import classifier
from pet.models import ActivitySample


def sample(app="Safari", host=None, title="", tab_title=None):
    return ActivitySample(at=0.0, app=app, title=title, host=host, tab_title=tab_title)


class NormalizeHostTests(unittest.TestCase):
    def test_strips_www_and_lowercases(self):
        self.assertEqual(classifier.normalize_host("WWW.YouTube.com"), "youtube.com")

    def test_none_stays_none(self):
        self.assertIsNone(classifier.normalize_host(None))


class RuleTests(unittest.TestCase):
    def setUp(self):
        classifier.reset_cache()

    def test_builtin_distraction_host_needs_no_llm(self):
        with patch("pet.classifier.llm.chat") as chat:
            self.assertEqual(classifier.classify(sample(host="youtube.com")), "distraction")
        chat.assert_not_called()

    def test_distraction_host_matches_subdomain(self):
        with patch("pet.classifier.llm.chat") as chat:
            self.assertEqual(classifier.classify(sample(host="m.youtube.com")), "distraction")
        chat.assert_not_called()

    def test_lookalike_host_is_not_a_suffix_match(self):
        with patch("pet.classifier.llm.chat", return_value="neutral") as chat:
            classifier.classify(sample(host="notyoutube.com"))
        chat.assert_called_once()

    def test_builtin_study_app_needs_no_llm(self):
        with patch("pet.classifier.llm.chat") as chat:
            self.assertEqual(classifier.classify(sample(app="Preview")), "study")
        chat.assert_not_called()

    def test_user_study_app_overrides_the_llm(self):
        with (
            patch("pet.classifier.PET_STUDY_APPS", ("Figma",)),
            patch("pet.classifier.llm.chat") as chat,
        ):
            self.assertEqual(classifier.classify(sample(app="Figma")), "study")
        chat.assert_not_called()

    def test_user_distract_host_overrides_a_builtin_study_host(self):
        with (
            patch("pet.classifier.PET_DISTRACT_HOSTS", ("wikipedia.org",)),
            patch("pet.classifier.llm.chat") as chat,
        ):
            self.assertEqual(
                classifier.classify(sample(app="Safari", host="wikipedia.org")),
                "distraction",
            )
        chat.assert_not_called()


class LlmTests(unittest.TestCase):
    def setUp(self):
        classifier.reset_cache()

    def test_unknown_pair_is_classified_once_and_cached(self):
        unknown = sample(app="MysteryApp", host=None)
        with patch("pet.classifier.llm.chat", return_value="distraction") as chat:
            first = classifier.classify(unknown)
            second = classifier.classify(unknown)
        self.assertEqual((first, second), ("distraction", "distraction"))
        self.assertEqual(chat.call_count, 1)

    def test_llm_answer_is_parsed_from_a_noisy_response(self):
        with patch("pet.classifier.llm.chat", return_value="Distraction.\n"):
            self.assertEqual(classifier.classify(sample(app="MysteryApp")), "distraction")

    def test_unparseable_answer_is_neutral(self):
        with patch("pet.classifier.llm.chat", return_value="maybe?"):
            self.assertEqual(classifier.classify(sample(app="MysteryApp")), "neutral")

    def test_llm_failure_is_neutral_and_is_not_cached(self):
        with patch("pet.classifier.llm.chat", side_effect=RuntimeError("down")) as chat:
            self.assertEqual(classifier.classify(sample(app="MysteryApp")), "neutral")
        with patch("pet.classifier.llm.chat", return_value="study") as chat:
            self.assertEqual(classifier.classify(sample(app="MysteryApp")), "study")
        chat.assert_called_once()

    def test_cache_key_separates_two_hosts_in_the_same_browser(self):
        with patch("pet.classifier.llm.chat", side_effect=["distraction", "study"]) as chat:
            first = classifier.classify(sample(app="Safari", host="funhouse.example"))
            second = classifier.classify(sample(app="Safari", host="lecturenotes.example"))
        self.assertEqual((first, second), ("distraction", "study"))
        self.assertEqual(chat.call_count, 2)


if __name__ == "__main__":
    unittest.main()
