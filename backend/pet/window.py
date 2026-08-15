"""The floating pet.

Deliberately thin: it takes a mood, an optional target x and an optional line
of text, and draws them. It has no opinion about YouTube, thresholds or
deadlines — everything upstream decides, so everything upstream is testable.
"""
import json
from pathlib import Path

from pet.models import Mood

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "pet"

PET_SIZE = 96.0
BUBBLE_SECONDS = 8.0
BUBBLE_WIDTH = 260.0
BUBBLE_HEIGHT = 54.0
WALK_STEP = 28.0          # points per tick
BOTTOM_MARGIN = 12.0


class PetWindow:
    def __init__(self, assets_dir: Path | None = None, tick_seconds: float | None = None):
        import AppKit

        from core.config import PET_POLL_SECONDS

        # The bubble's lifetime is written in seconds but spent in ticks, and a
        # tick is one poll, so the conversion has to happen here or the bubble
        # silently stretches with the poll interval.
        self._tick_seconds = float(tick_seconds or PET_POLL_SECONDS)
        self._bubble_ticks = max(1, round(BUBBLE_SECONDS / self._tick_seconds))

        self._assets = assets_dir or ASSETS
        meta = json.loads((self._assets / "meta.json").read_text())
        self._frame_size = meta["frame_size"]
        self._moods = meta["moods"]

        self._strips = {
            name: AppKit.NSImage.alloc().initWithContentsOfFile_(
                str(self._assets / entry["file"])
            )
            for name, entry in self._moods.items()
        }

        screen = AppKit.NSScreen.mainScreen().frame()
        self._x = screen.size.width * 0.12
        self._y = BOTTOM_MARGIN
        self._target_x: float | None = None
        self._mood = Mood.IDLE
        self._requested_mood = Mood.IDLE
        self._frame_index = 0
        self._bubble_ticks_left = 0

        self._window = self._make_window(AppKit, self._x, self._y, PET_SIZE, PET_SIZE)
        self._view = AppKit.NSImageView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, PET_SIZE, PET_SIZE)
        )
        self._view.setImageScaling_(AppKit.NSImageScaleProportionallyUpOrDown)
        self._window.setContentView_(self._view)

        self._bubble = self._make_window(
            AppKit, self._x, self._y + PET_SIZE, BUBBLE_WIDTH, BUBBLE_HEIGHT
        )
        self._label = AppKit.NSTextField.alloc().initWithFrame_(
            AppKit.NSMakeRect(10, 8, BUBBLE_WIDTH - 20, BUBBLE_HEIGHT - 16)
        )
        self._label.setEditable_(False)
        self._label.setBezeled_(False)
        self._label.setDrawsBackground_(True)
        self._label.setBackgroundColor_(AppKit.NSColor.windowBackgroundColor())
        self._label.setFont_(AppKit.NSFont.systemFontOfSize_(13))
        self._bubble.setContentView_(self._label)

    @staticmethod
    def _make_window(AppKit, x, y, width, height):
        window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            AppKit.NSMakeRect(x, y, width, height),
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        window.setOpaque_(False)
        window.setBackgroundColor_(AppKit.NSColor.clearColor())
        window.setLevel_(AppKit.NSStatusWindowLevel)
        window.setIgnoresMouseEvents_(True)
        window.setHasShadow_(False)
        window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
        )
        return window

    def show(self) -> None:
        self._window.orderFrontRegardless()

    def hide(self) -> None:
        self._window.orderOut_(None)
        self._bubble.orderOut_(None)

    def render(
        self,
        mood: Mood,
        walk_to: float | None = None,
        bubble: str | None = None,
    ) -> None:
        self._requested_mood = mood
        if walk_to is not None:
            self._target_x = walk_to
            self._mood = Mood.WALK
        else:
            self._mood = mood
        if bubble:
            self._show_bubble(bubble)
        self._draw()

    def _show_bubble(self, text: str) -> None:
        self._label.setStringValue_(text)
        self._bubble.orderFrontRegardless()
        self._bubble_ticks_left = self._bubble_ticks

    def tick(self) -> None:
        entry = self._moods[self._mood.value]
        self._frame_index = (self._frame_index + 1) % entry["frames"]

        if self._target_x is not None:
            delta = self._target_x - self._x
            if abs(delta) <= WALK_STEP:
                self._x = self._target_x
                self._target_x = None
                self._mood = self._requested_mood
            else:
                self._x += WALK_STEP if delta > 0 else -WALK_STEP

        if self._bubble_ticks_left > 0:
            self._bubble_ticks_left -= 1
            if self._bubble_ticks_left == 0:
                self._bubble.orderOut_(None)

        self._draw()

    def _draw(self) -> None:
        import AppKit

        strip = self._strips.get(self._mood.value)
        if strip is not None:
            size = self._frame_size
            cropped = AppKit.NSImage.alloc().initWithSize_(AppKit.NSMakeSize(size, size))
            cropped.lockFocus()
            strip.drawInRect_fromRect_operation_fraction_(
                AppKit.NSMakeRect(0, 0, size, size),
                AppKit.NSMakeRect(self._frame_index * size, 0, size, size),
                AppKit.NSCompositingOperationSourceOver,
                1.0,
            )
            cropped.unlockFocus()
            self._view.setImage_(cropped)

        self._window.setFrameOrigin_(AppKit.NSMakePoint(self._x, self._y))
        self._bubble.setFrameOrigin_(
            AppKit.NSMakePoint(self._x - BUBBLE_WIDTH / 2 + PET_SIZE / 2, self._y + PET_SIZE)
        )


def window_center_x(app_pid: int) -> float | None:
    """Horizontal centre of that process's frontmost window, in screen points."""
    import Quartz

    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    ) or []
    for window in windows:
        if window.get("kCGWindowOwnerPID") != app_pid:
            continue
        bounds = window.get("kCGWindowBounds") or {}
        width = float(bounds.get("Width", 0))
        if width <= 0:
            continue
        return float(bounds.get("X", 0)) + width / 2
    return None
