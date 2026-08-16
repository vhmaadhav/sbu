import subprocess
import unittest
from unittest.mock import patch

from pet import watcher


class ParseTabOutputTests(unittest.TestCase):
    def test_splits_title_and_url_on_the_tab_character(self):
        title, url = watcher.parse_tab_output("Lecture 4, part 2\thttps://youtube.com/watch?v=x\n")
        self.assertEqual(title, "Lecture 4, part 2")
        self.assertEqual(url, "https://youtube.com/watch?v=x")

    def test_a_title_containing_a_tab_keeps_the_url_intact(self):
        title, url = watcher.parse_tab_output("a\tb\thttps://example.com")
        self.assertEqual(url, "https://example.com")
        self.assertEqual(title, "a\tb")

    def test_empty_output_is_nothing(self):
        self.assertEqual(watcher.parse_tab_output(""), (None, None))
        self.assertEqual(watcher.parse_tab_output("   \n"), (None, None))

    def test_output_without_a_separator_is_nothing(self):
        self.assertEqual(watcher.parse_tab_output("just a title"), (None, None))


class HostOfTests(unittest.TestCase):
    def test_extracts_and_normalizes_the_host(self):
        self.assertEqual(watcher.host_of("https://WWW.YouTube.com/watch?v=1"), "youtube.com")

    def test_handles_a_port(self):
        self.assertEqual(watcher.host_of("http://localhost:3000/notes"), "localhost")

    def test_non_http_schemes_and_junk_are_none(self):
        self.assertIsNone(watcher.host_of("chrome://newtab"))
        self.assertIsNone(watcher.host_of("about:blank"))
        self.assertIsNone(watcher.host_of(""))
        self.assertIsNone(watcher.host_of(None))


class BrowserTabTests(unittest.TestCase):
    def test_non_browser_app_is_not_queried(self):
        with patch("pet.watcher._run_applescript") as run:
            self.assertEqual(watcher.browser_tab("Preview"), (None, None))
        run.assert_not_called()

    def test_browser_output_becomes_title_and_host(self):
        with patch(
            "pet.watcher._run_applescript",
            return_value="Redstone for beginners\thttps://www.youtube.com/watch?v=1",
        ):
            self.assertEqual(
                watcher.browser_tab("Safari"),
                ("Redstone for beginners", "youtube.com"),
            )

    def test_denied_automation_permission_degrades_to_nothing(self):
        error = subprocess.CalledProcessError(1, "osascript")
        with patch("pet.watcher._run_applescript", side_effect=error):
            self.assertEqual(watcher.browser_tab("Safari"), (None, None))

    def test_a_timeout_degrades_to_nothing(self):
        with patch(
            "pet.watcher._run_applescript",
            side_effect=subprocess.TimeoutExpired("osascript", 2),
        ):
            self.assertEqual(watcher.browser_tab("Google Chrome"), (None, None))


class SampleTests(unittest.TestCase):
    def test_sample_combines_frontmost_and_tab(self):
        with (
            patch("pet.watcher.frontmost", return_value=("Safari", "YouTube")),
            patch("pet.watcher.browser_tab", return_value=("Lofi mix", "youtube.com")),
        ):
            result = watcher.sample(at=42.0)
        self.assertEqual(result.at, 42.0)
        self.assertEqual(result.app, "Safari")
        self.assertEqual(result.title, "YouTube")
        self.assertEqual(result.tab_title, "Lofi mix")
        self.assertEqual(result.host, "youtube.com")

    def test_sample_survives_a_frontmost_failure(self):
        with patch("pet.watcher.frontmost", side_effect=RuntimeError("no window server")):
            result = watcher.sample(at=1.0)
        self.assertEqual(result.app, "")
        self.assertIsNone(result.host)


if __name__ == "__main__":
    unittest.main()
