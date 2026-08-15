"""Run the pet: python -m pet

Everything happens on the main thread via a rumps timer, because AppKit window
updates must. The menu bar carries a Pause so the pet can be silenced during a
screen share without quitting it.
"""
import time

import rumps

from core.config import PET_POLL_SECONDS

from pet.runner import PetRunner
from pet.window import PetWindow


class PetApp(rumps.App):
    def __init__(self):
        super().__init__("🐾", quit_button=rumps.MenuItem("Quit Study Pet"))
        self.pause_item = rumps.MenuItem("⏸ Pause", callback=self.toggle_pause)
        self.menu = [self.pause_item]
        self._paused = False
        self._window = PetWindow()
        self._runner = PetRunner(window=self._window)
        self._window.show()
        self._timer = rumps.Timer(self.tick, PET_POLL_SECONDS)
        self._timer.start()

    def toggle_pause(self, _):
        self._paused = not self._paused
        if self._paused:
            self._window.hide()
            self.pause_item.title = "▶ Resume"
            self.title = "💤"
        else:
            self._window.show()
            self.pause_item.title = "⏸ Pause"
            self.title = "🐾"

    def tick(self, _):
        if self._paused:
            return
        self._runner.tick(now=time.monotonic())


if __name__ == "__main__":
    PetApp().run()
