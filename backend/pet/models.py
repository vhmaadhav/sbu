"""Value types shared by the pet's units. No behaviour lives here."""
from dataclasses import dataclass
from enum import Enum
from typing import Literal


class Stage(str, Enum):
    """How far the escalation ladder has climbed."""

    CALM = "calm"
    NOTICE = "notice"
    CONCERNED = "concerned"
    NAG = "nag"
    PLEAD = "plead"


STAGE_ORDER: tuple[Stage, ...] = (
    Stage.CALM,
    Stage.NOTICE,
    Stage.CONCERNED,
    Stage.NAG,
    Stage.PLEAD,
)


class Mood(str, Enum):
    """Which sprite strip the window should be playing."""

    IDLE = "idle"
    WALK = "walk"
    CONCERNED = "concerned"
    SAD = "sad"
    ALERT = "alert"


Label = Literal["study", "distraction", "neutral"]


@dataclass(frozen=True, slots=True)
class ActivitySample:
    at: float
    app: str
    title: str = ""
    host: str | None = None
    tab_title: str | None = None


@dataclass(frozen=True, slots=True)
class NudgeEvent:
    at: float
    stage: Stage
    mood: Mood
    speak: bool
    recovered: bool
    sample: ActivitySample


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    next_deadline: str | None = None
    open_task_count: int = 0
    weakest_concepts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Seconds of distraction dwell required to reach each stage."""

    notice: float
    concerned: float
    nag: float
    plead: float
    recovery: float
    bubble_cooldown: float
    plead_repeat: float
    poll: float

    @classmethod
    def from_config(cls) -> "Thresholds":
        from core import config

        return cls(
            notice=float(config.PET_NOTICE_SECONDS),
            concerned=float(config.PET_CONCERNED_SECONDS),
            nag=float(config.PET_NAG_SECONDS),
            plead=float(config.PET_PLEAD_SECONDS),
            recovery=float(config.PET_RECOVERY_SECONDS),
            bubble_cooldown=float(config.PET_BUBBLE_COOLDOWN),
            plead_repeat=float(config.PET_PLEAD_REPEAT_SECONDS),
            poll=float(config.PET_POLL_SECONDS),
        )
