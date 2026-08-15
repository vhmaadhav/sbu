import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.video import optimize_for_streaming


class OptimizeForStreamingTests(unittest.TestCase):
    def test_mp4_is_remuxed_and_atomically_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "lecture.mp4"
            source.write_bytes(b"original")

            def fake_ffmpeg(command, **kwargs):
                self.assertEqual(command[command.index("-i") + 1], str(source))
                self.assertIn("+faststart", command)
                self.assertEqual(kwargs, {"check": True, "capture_output": True})
                Path(command[-1]).write_bytes(b"optimized")

            with patch("core.video.subprocess.run", side_effect=fake_ffmpeg) as run:
                changed = optimize_for_streaming(source)

            self.assertTrue(changed)
            self.assertEqual(source.read_bytes(), b"optimized")
            self.assertEqual(run.call_count, 1)
            self.assertEqual(list(Path(folder).glob(".*-streaming-*")), [])

    def test_failed_remux_preserves_original_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "lecture.mov"
            source.write_bytes(b"original")

            failure = subprocess.CalledProcessError(1, ["ffmpeg"])
            with patch("core.video.subprocess.run", side_effect=failure):
                with self.assertRaises(subprocess.CalledProcessError):
                    optimize_for_streaming(source)

            self.assertEqual(source.read_bytes(), b"original")
            self.assertEqual(list(Path(folder).glob(".*-streaming-*")), [])

    def test_non_mp4_container_is_left_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "lecture.webm"
            source.write_bytes(b"original")

            with patch("core.video.subprocess.run") as run:
                changed = optimize_for_streaming(source)

            self.assertFalse(changed)
            self.assertEqual(source.read_bytes(), b"original")
            run.assert_not_called()

    def test_missing_video_has_an_actionable_error(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "missing.mp4"
            with self.assertRaisesRegex(FileNotFoundError, "Video file not found"):
                optimize_for_streaming(missing)


if __name__ == "__main__":
    unittest.main()
