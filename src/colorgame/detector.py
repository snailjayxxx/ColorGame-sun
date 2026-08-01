from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np


class DetectionError(RuntimeError):
    """Raised when a regular group of color blocks cannot be detected."""


@dataclass(frozen=True)
class TileInfo:
    row: int
    col: int
    box: tuple[int, int, int, int]
    center: tuple[int, int]
    rgb: tuple[int, int, int]
    brightness: float
    lab_score: float
    brightness_score: float
    combined_score: float


@dataclass(frozen=True)
class DetectionResult:
    target: TileInfo
    tiles: tuple[TileInfo, ...]
    common_rgb: tuple[int, int, int]
    common_brightness: float
    confidence: float
    rows: int
    cols: int


@dataclass(frozen=True)
class _Box:
    x: int
    y: int
    w: int
    h: int
    area: int

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass(frozen=True)
class _GridBox:
    row: int
    col: int
    x: int
    y: int
    w: int
    h: int


def relative_luminance(rgb: Iterable[float]) -> float:
    """Return WCAG relative luminance in the range 0..100."""
    values = np.asarray(tuple(rgb), dtype=np.float64) / 255.0
    linear = np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)
    return float(np.dot(linear, np.array([0.2126, 0.7152, 0.0722])) * 100.0)


def _clean_mask(mask: np.ndarray) -> np.ndarray:
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    return mask


def _candidate_masks(image_rgb: np.ndarray) -> list[np.ndarray]:
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    _, bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    lab = cv2.cvtColor(image_rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)
    h, w = image_rgb.shape[:2]
    border = max(2, min(h, w) // 80)
    border_pixels = np.concatenate(
        [
            lab[:border].reshape(-1, 3),
            lab[-border:].reshape(-1, 3),
            lab[:, :border].reshape(-1, 3),
            lab[:, -border:].reshape(-1, 3),
        ]
    )
    background = np.median(border_pixels, axis=0)
    distance = np.linalg.norm(lab - background, axis=2)
    distance_u8 = cv2.normalize(distance, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    _, border_distance = cv2.threshold(
        distance_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    return [
        _clean_mask(bright),
        _clean_mask(cv2.bitwise_not(bright)),
        _clean_mask(border_distance),
        _clean_mask(cv2.bitwise_not(border_distance)),
    ]


def _extract_boxes(mask: np.ndarray) -> list[_Box]:
    h, w = mask.shape
    image_area = h * w
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    boxes: list[_Box] = []
    min_side = max(6, min(h, w) // 100)
    min_area = max(40, image_area // 15000)

    for index in range(1, count):
        x, y, bw, bh, area = (int(v) for v in stats[index])
        if bw < min_side or bh < min_side or area < min_area:
            continue
        if area > image_area * 0.45:
            continue
        aspect = bw / max(bh, 1)
        fill = area / max(bw * bh, 1)
        if not 0.60 <= aspect <= 1.65:
            continue
        if fill < 0.48:
            continue
        boxes.append(_Box(x, y, bw, bh, area))
    return boxes


def _cluster_axis(values: list[float], tolerance: float) -> list[float]:
    if not values:
        return []
    clusters: list[list[float]] = []
    for value in sorted(values):
        if not clusters or abs(value - float(np.mean(clusters[-1]))) > tolerance:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return [float(np.median(cluster)) for cluster in clusters]


def _grid_quality(boxes: list[_Box]) -> tuple[float, int, int]:
    if len(boxes) < 4:
        return 0.0, 0, 0
    med_w = float(np.median([b.w for b in boxes]))
    med_h = float(np.median([b.h for b in boxes]))
    xs = _cluster_axis([b.cx for b in boxes], med_w * 0.55)
    ys = _cluster_axis([b.cy for b in boxes], med_h * 0.55)
    if not xs or not ys:
        return 0.0, 0, 0
    expected = len(xs) * len(ys)
    occupancy = min(1.0, len(boxes) / max(expected, 1))
    if expected < len(boxes) or expected > len(boxes) + max(2, round(expected * 0.15)):
        occupancy *= 0.35

    residuals = []
    for box in boxes:
        dx = min(abs(box.cx - x) for x in xs) / max(med_w, 1)
        dy = min(abs(box.cy - y) for y in ys) / max(med_h, 1)
        residuals.append(dx + dy)
    alignment = max(0.0, 1.0 - float(np.median(residuals)) * 2.5)
    return occupancy * alignment, len(ys), len(xs)


def _best_family(boxes: list[_Box]) -> tuple[list[_Box], float]:
    if not boxes:
        return [], 0.0
    best: list[_Box] = []
    best_score = 0.0

    for seed in boxes:
        family = [
            box
            for box in boxes
            if abs(np.log(max(box.w, 1) / max(seed.w, 1))) <= 0.22
            and abs(np.log(max(box.h, 1) / max(seed.h, 1))) <= 0.22
        ]
        if len(family) < 4:
            continue
        widths = np.array([b.w for b in family], dtype=float)
        heights = np.array([b.h for b in family], dtype=float)
        areas = np.array([b.area for b in family], dtype=float)
        consistency = 1.0 / (
            1.0
            + np.std(widths) / max(np.mean(widths), 1)
            + np.std(heights) / max(np.mean(heights), 1)
            + np.std(areas) / max(np.mean(areas), 1)
        )
        grid_quality, _, _ = _grid_quality(family)
        size_weight = np.sqrt(float(np.median(areas)))
        score = len(family) * size_weight * consistency * (0.45 + 0.55 * grid_quality)
        if score > best_score:
            best = family
            best_score = score
    return best, best_score


def _infer_grid(boxes: list[_Box], image_shape: tuple[int, int, int]) -> tuple[list[_GridBox], int, int]:
    if len(boxes) < 4:
        raise DetectionError("检测到的方块数量不足，请重新框选并只保留游戏色块区域。")

    med_w = int(round(float(np.median([b.w for b in boxes]))))
    med_h = int(round(float(np.median([b.h for b in boxes]))))
    xs = _cluster_axis([b.cx for b in boxes], med_w * 0.55)
    ys = _cluster_axis([b.cy for b in boxes], med_h * 0.55)
    expected = len(xs) * len(ys)
    if len(xs) < 2 or len(ys) < 2:
        raise DetectionError("没有识别到规则的方块网格。")
    if expected > len(boxes) + max(2, round(expected * 0.15)):
        raise DetectionError("识别出的网格缺失过多，请缩小选择范围后重试。")

    image_h, image_w = image_shape[:2]
    grid: list[_GridBox] = []
    for row, cy in enumerate(ys):
        for col, cx in enumerate(xs):
            nearest = min(
                boxes,
                key=lambda b: ((b.cx - cx) / max(med_w, 1)) ** 2
                + ((b.cy - cy) / max(med_h, 1)) ** 2,
            )
            distance = np.hypot(
                (nearest.cx - cx) / max(med_w, 1),
                (nearest.cy - cy) / max(med_h, 1),
            )
            if distance <= 0.48:
                x, y, bw, bh = nearest.x, nearest.y, nearest.w, nearest.h
            else:
                bw, bh = med_w, med_h
                x = int(round(cx - bw / 2))
                y = int(round(cy - bh / 2))
            x = max(0, min(x, image_w - 1))
            y = max(0, min(y, image_h - 1))
            bw = max(1, min(bw, image_w - x))
            bh = max(1, min(bh, image_h - y))
            grid.append(_GridBox(row, col, x, y, bw, bh))

    return grid, len(ys), len(xs)


def _sample_rgb(image_rgb: np.ndarray, box: _GridBox) -> tuple[int, int, int]:
    inset = max(2, int(round(min(box.w, box.h) * 0.24)))
    x1 = min(box.x + inset, box.x + box.w - 1)
    y1 = min(box.y + inset, box.y + box.h - 1)
    x2 = max(x1 + 1, box.x + box.w - inset)
    y2 = max(y1 + 1, box.y + box.h - inset)
    crop = image_rgb[y1:y2, x1:x2]
    if crop.size == 0:
        crop = image_rgb[box.y : box.y + box.h, box.x : box.x + box.w]
    rgb = np.median(crop.reshape(-1, 3), axis=0)
    return tuple(int(round(v)) for v in rgb)


def _pairwise_median(values: np.ndarray) -> np.ndarray:
    distances = np.abs(values[:, None] - values[None, :])
    np.fill_diagonal(distances, np.nan)
    return np.nanmedian(distances, axis=1)


def detect_outlier(image_rgb: np.ndarray) -> DetectionResult:
    """Detect a regular block grid and return the tile whose color differs most."""
    if image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
        raise ValueError("image_rgb must be an RGB image with shape (height, width, 3)")
    if min(image_rgb.shape[:2]) < 40:
        raise DetectionError("选择区域太小。")

    best_boxes: list[_Box] = []
    best_score = 0.0
    for mask in _candidate_masks(image_rgb):
        family, score = _best_family(_extract_boxes(mask))
        if score > best_score:
            best_boxes, best_score = family, score

    if len(best_boxes) < 4:
        raise DetectionError("未找到复数规则色块，请只框选游戏方块区域后重试。")

    grid, rows, cols = _infer_grid(best_boxes, image_rgb.shape)
    rgb_values = np.array([_sample_rgb(image_rgb, box) for box in grid], dtype=np.float32)
    lab_values = cv2.cvtColor((rgb_values / 255.0).reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3)
    brightness_values = np.array([relative_luminance(rgb) for rgb in rgb_values], dtype=np.float32)

    lab_distances = np.linalg.norm(lab_values[:, None, :] - lab_values[None, :, :], axis=2)
    np.fill_diagonal(lab_distances, np.nan)
    lab_scores = np.nanmedian(lab_distances, axis=1)
    brightness_scores = _pairwise_median(brightness_values)
    combined_scores = lab_scores + brightness_scores * 0.18

    target_index = int(np.argmax(combined_scores))
    order = np.argsort(combined_scores)[::-1]
    top = float(combined_scores[order[0]])
    second = float(combined_scores[order[1]]) if len(order) > 1 else 0.0
    separation = max(0.0, (top - second) / max(top, 1e-6))
    magnitude = min(1.0, top / 2.5)
    confidence = float(np.clip((0.78 * separation + 0.22 * magnitude) * 100.0, 0.0, 100.0))

    common_mask = np.ones(len(grid), dtype=bool)
    common_mask[target_index] = False
    common_rgb_arr = np.median(rgb_values[common_mask], axis=0)
    common_rgb = tuple(int(round(v)) for v in common_rgb_arr)
    common_brightness = float(np.median(brightness_values[common_mask]))

    tile_infos: list[TileInfo] = []
    for index, box in enumerate(grid):
        tile_infos.append(
            TileInfo(
                row=box.row,
                col=box.col,
                box=(box.x, box.y, box.w, box.h),
                center=(box.x + box.w // 2, box.y + box.h // 2),
                rgb=tuple(int(v) for v in rgb_values[index]),
                brightness=float(brightness_values[index]),
                lab_score=float(lab_scores[index]),
                brightness_score=float(brightness_scores[index]),
                combined_score=float(combined_scores[index]),
            )
        )

    return DetectionResult(
        target=tile_infos[target_index],
        tiles=tuple(tile_infos),
        common_rgb=common_rgb,
        common_brightness=common_brightness,
        confidence=confidence,
        rows=rows,
        cols=cols,
    )
