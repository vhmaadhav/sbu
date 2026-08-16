"""One poll of the loop, wiring the units together.

Every collaborator arrives through the constructor so the whole cycle can be
driven from a test with no PyObjC and no clock. Samples live in a bounded
in-memory ring and are never written anywhere.
"""
from collections import deque

from pet import classifier, voice, watcher
from pet.models import Thresholds
from pet.state import PetState, advance

RING_SIZE = 200


class PetRunner:
    def __init__(
        self,
        window,
        sampler=None,
        classify=None,
        context=None,
        speak=None,
        thresholds: Thresholds | None = None,
        locate=None,
    ):
        from pet.context import ContextFetcher

        self._window = window
        self._sampler = sampler or watcher.sample
        self._classify = classify or classifier.classify
        self._context = context or ContextFetcher()
        self._speak = speak or voice.line
        self._thresholds = thresholds or Thresholds.from_config()
        self._locate = locate if locate is not None else _default_locate
        self._state = PetState()
        self._samples: deque = deque(maxlen=RING_SIZE)

    @property
    def recent(self) -> tuple:
        return tuple(self._samples)

    def tick(self, now: float) -> None:
        try:
            self._poll(now)
        except Exception:
            # A single bad poll — a window server hiccup, a browser mid-quit —
            # must never end the session. The next tick tries again.
            pass
        self._window.tick()

    def _poll(self, now: float) -> None:
        sample = self._sampler(now)
        self._samples.append(sample)
        label = self._classify(sample)
        self._state, event = advance(self._state, sample, label, self._thresholds)
        if event is None:
            return

        bubble = None
        walk_to = None
        if event.speak:
            try:
                bubble = self._speak(event, self._context.snapshot())
            except Exception:
                bubble = None
            if not event.recovered:
                walk_to = self._locate(sample)

        self._window.render(event.mood, walk_to=walk_to, bubble=bubble)


def _default_locate(sample) -> float | None:
    """Screen x of the distracting window, resolved from the frontmost process."""
    try:
        import AppKit

        from pet.window import window_center_x

        application = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if application is None:
            return None
        return window_center_x(int(application.processIdentifier()))
    except Exception:
        return None
