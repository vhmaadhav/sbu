"""The escalation ladder.

Pure functions over a timeline of labelled samples. No clock, no I/O: the
caller supplies timestamps, which makes every threshold, decay and cooldown
rule testable against a synthetic timeline.
"""
from dataclasses import dataclass, replace

from pet.models import (
    ActivitySample,
    Label,
    Mood,
    NudgeEvent,
    STAGE_ORDER,
    Stage,
    Thresholds,
)

MOOD_FOR_STAGE: dict[Stage, Mood] = {
    Stage.CALM: Mood.IDLE,
    Stage.NOTICE: Mood.ALERT,
    Stage.CONCERNED: Mood.CONCERNED,
    Stage.NAG: Mood.CONCERNED,
    Stage.PLEAD: Mood.SAD,
}

SPEAKING_STAGES = frozenset({Stage.CONCERNED, Stage.NAG, Stage.PLEAD})

# A neutral second undoes half a second of accumulated distraction, so stepping
# away from the desk walks the ladder back down instead of freezing it.
NEUTRAL_DECAY = 0.5

# A sample far in the future means the machine slept. Trusting it would jump
# straight to the top of the ladder, so the gap is clamped to a few polls.
MAX_GAP_POLLS = 3


@dataclass(frozen=True, slots=True)
class PetState:
    dwell: float = 0.0
    stage: Stage = Stage.CALM
    study_run: float = 0.0
    last_sample_at: float | None = None
    last_bubble_at: float | None = None


def _elapsed(state: PetState, sample: ActivitySample, thresholds: Thresholds) -> float:
    if state.last_sample_at is None:
        return 0.0
    gap = sample.at - state.last_sample_at
    if gap <= 0:
        return 0.0
    return min(gap, MAX_GAP_POLLS * thresholds.poll)


def _stage_for_dwell(dwell: float, thresholds: Thresholds) -> Stage:
    if dwell >= thresholds.plead:
        return Stage.PLEAD
    if dwell >= thresholds.nag:
        return Stage.NAG
    if dwell >= thresholds.concerned:
        return Stage.CONCERNED
    if dwell >= thresholds.notice:
        return Stage.NOTICE
    return Stage.CALM


def _one_step_toward(current: Stage, target: Stage) -> Stage:
    current_index = STAGE_ORDER.index(current)
    target_index = STAGE_ORDER.index(target)
    if target_index <= current_index:
        return current
    return STAGE_ORDER[current_index + 1]


def _may_speak(state: PetState, at: float, thresholds: Thresholds) -> bool:
    if state.last_bubble_at is None:
        return True
    return at - state.last_bubble_at >= thresholds.bubble_cooldown


def advance(
    state: PetState,
    sample: ActivitySample,
    label: Label,
    thresholds: Thresholds,
) -> tuple[PetState, NudgeEvent | None]:
    """Fold one labelled sample into the state, optionally emitting an event."""
    elapsed = _elapsed(state, sample, thresholds)
    dwell = state.dwell
    study_run = state.study_run

    if label == "study":
        dwell = 0.0
        study_run += elapsed
    elif label == "distraction":
        dwell += elapsed
        study_run = 0.0
    else:
        dwell = max(0.0, dwell - elapsed * NEUTRAL_DECAY)

    state = replace(state, dwell=dwell, study_run=study_run, last_sample_at=sample.at)

    if label == "study" and state.stage is not Stage.CALM and study_run >= thresholds.recovery:
        speak = _may_speak(state, sample.at, thresholds)
        state = replace(
            state,
            stage=Stage.CALM,
            study_run=0.0,
            last_bubble_at=sample.at if speak else state.last_bubble_at,
        )
        return state, NudgeEvent(
            at=sample.at,
            stage=Stage.CALM,
            mood=Mood.IDLE,
            speak=speak,
            recovered=True,
            sample=sample,
        )

    target = _stage_for_dwell(dwell, thresholds)
    next_stage = _one_step_toward(state.stage, target)

    if next_stage is not state.stage:
        speak = next_stage in SPEAKING_STAGES and _may_speak(state, sample.at, thresholds)
        state = replace(
            state,
            stage=next_stage,
            last_bubble_at=sample.at if speak else state.last_bubble_at,
        )
        return state, NudgeEvent(
            at=sample.at,
            stage=next_stage,
            mood=MOOD_FOR_STAGE[next_stage],
            speak=speak,
            recovered=False,
            sample=sample,
        )

    repeat_due = (
        state.stage is Stage.PLEAD
        and state.last_bubble_at is not None
        and sample.at - state.last_bubble_at >= thresholds.plead_repeat
    )
    if repeat_due and _may_speak(state, sample.at, thresholds):
        state = replace(state, last_bubble_at=sample.at)
        return state, NudgeEvent(
            at=sample.at,
            stage=Stage.PLEAD,
            mood=Mood.SAD,
            speak=True,
            recovered=False,
            sample=sample,
        )

    return state, None
