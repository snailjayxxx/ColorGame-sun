from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageDraw

from colorgame.detector import detect_outlier


def make_grid(
    rows: int,
    cols: int,
    common: tuple[int, int, int],
    different: tuple[int, int, int],
    target: tuple[int, int],
    tile: int = 72,
    gap: int = 9,
    margin: int = 18,
) -> Image.Image:
    width = margin * 2 + cols * tile + (cols - 1) * gap
    height = margin * 2 + rows * tile + (rows - 1) * gap
    image = Image.new("RGB", (width, height), (18, 25, 40))
    draw = ImageDraw.Draw(image)
    for row in range(rows):
        for col in range(cols):
            x = margin + col * (tile + gap)
            y = margin + row * (tile + gap)
            color = different if (row, col) == target else common
            draw.rounded_rectangle((x, y, x + tile - 1, y + tile - 1), radius=10, fill=color)
    return image


def jpeg_roundtrip(image: Image.Image, quality: int = 88) -> Image.Image:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def test_detects_small_rgb_difference() -> None:
    image = jpeg_roundtrip(make_grid(6, 6, (210, 185, 75), (205, 180, 75), (1, 2)))
    result = detect_outlier(np.asarray(image))
    assert (result.target.row, result.target.col) == (1, 2)
    assert result.rows == 6
    assert result.cols == 6


def test_detects_brightness_difference() -> None:
    image = make_grid(4, 5, (70, 155, 220), (66, 147, 209), (3, 4))
    result = detect_outlier(np.asarray(image))
    assert (result.target.row, result.target.col) == (3, 4)


def test_detects_hue_difference_with_similar_brightness() -> None:
    image = jpeg_roundtrip(make_grid(3, 4, (190, 90, 120), (188, 92, 120), (0, 1)), quality=92)
    result = detect_outlier(np.asarray(image))
    assert (result.target.row, result.target.col) == (0, 1)


def test_detects_on_two_by_two_grid() -> None:
    image = make_grid(2, 2, (115, 195, 105), (112, 188, 103), (1, 0), tile=95)
    result = detect_outlier(np.asarray(image))
    assert (result.target.row, result.target.col) == (1, 0)
