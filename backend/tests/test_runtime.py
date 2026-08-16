import signal
import unittest

from axiom_trace.runtime import shutdown_signals


class RuntimePortabilityTests(unittest.TestCase):
    def test_shutdown_signals_match_the_current_platform(self):
        available = shutdown_signals()

        self.assertIn(signal.SIGTERM, available)
        if hasattr(signal, "SIGHUP"):
            self.assertIn(signal.SIGHUP, available)
        else:
            self.assertEqual(available, (signal.SIGTERM,))


if __name__ == "__main__":
    unittest.main()
