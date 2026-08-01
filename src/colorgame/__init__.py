"""ColorGame screen color-block outlier detector."""

from .detector import DetectionError, DetectionResult, TileInfo, detect_outlier

__all__ = ["DetectionError", "DetectionResult", "TileInfo", "detect_outlier"]
__version__ = "0.2.0"
