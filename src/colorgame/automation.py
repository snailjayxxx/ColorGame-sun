from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import dist

from .detector import DetectionResult


@dataclass(frozen=True)
class BoardSignature:
    """Stable fingerprint used to decide whether the game advanced."""

    rows: int
    cols: int
    target_row: int
    target_col: int
    common_rgb: tuple[int, int, int]
    target_rgb: tuple[int, int, int]

    @classmethod
    def from_result(cls, result: DetectionResult) -> "BoardSignature":
        return cls(
            rows=result.rows,
            cols=result.cols,
            target_row=result.target.row,
            target_col=result.target.col,
            common_rgb=result.common_rgb,
            target_rgb=result.target.rgb,
        )


class ClickDecision(str, Enum):
    """Next action after checking the board following a click."""

    WAIT = "wait"
    NEXT_LEVEL = "next_level"
    RETRY = "retry"
    STOP = "stop"


def board_has_changed(
    before: BoardSignature,
    after: BoardSignature,
    *,
    rgb_threshold: float = 4.0,
) -> bool:
    """Return True when the detected grid is likely a new level.

    A wrong click usually leaves the grid unchanged and only removes a heart.
    Checking the grid avoids depending on the site's current heart icon/theme.
    """

    if (before.rows, before.cols) != (after.rows, after.cols):
        return True
    if (before.target_row, before.target_col) != (after.target_row, after.target_col):
        return True
    if dist(before.common_rgb, after.common_rgb) >= rgb_threshold:
        return True
    if dist(before.target_rgb, after.target_rgb) >= rgb_threshold:
        return True
    return False


def decide_click_action(
    *,
    board_changed: bool,
    click_number: int,
    poll_count: int,
    max_polls: int,
    max_clicks: int = 2,
) -> ClickDecision:
    """Choose a bounded action after a click.

    A changed board always advances to the next level. An unchanged board is
    polled for a bounded period. Only the first failed click may be retried;
    reaching the per-level click limit always stops the continuous session.
    """

    if board_changed:
        return ClickDecision.NEXT_LEVEL
    if poll_count < max_polls:
        return ClickDecision.WAIT
    if click_number < max_clicks:
        return ClickDecision.RETRY
    return ClickDecision.STOP
