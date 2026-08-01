from __future__ import annotations

from dataclasses import dataclass
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
