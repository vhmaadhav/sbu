import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from buddy.menubar import BuddyApp


class MenubarScreenshotTests(unittest.TestCase):
    def test_screenshot_is_queued_as_png_for_diagram_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "screenshot.png"

            def capture(command):
                output.write_bytes(b"png")
                return None

            with (
                patch("buddy.menubar._stamp", return_value=output),
                patch("buddy.menubar.subprocess.run", side_effect=capture) as run,
                patch("buddy.menubar.rumps.notification") as notification,
            ):
                BuddyApp.screenshot(object(), None)

            self.assertEqual(run.call_args.args[0], ["screencapture", "-i", str(output)])
            notification.assert_called_once()
            self.assertIn("checking for a diagram", notification.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
