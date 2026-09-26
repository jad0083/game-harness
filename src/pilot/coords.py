"""Coordinate conventions between the model and the game's 1568x882 image space."""

from __future__ import annotations

IMAGE_W, IMAGE_H = 1568, 882


def describe(space: str) -> str:
    if space == "norm1000":
        return ("Coordinates are normalized to 0-1000 on both axes of the screenshot "
                "(x: 0 = left edge, 1000 = right edge; y: 0 = top, 1000 = bottom).")
    return f"Coordinates are pixels of the {IMAGE_W}x{IMAGE_H} screenshot (x right, y down)."


def to_image(x: float, y: float, space: str) -> tuple[int, int]:
    """Model coordinates -> image pixels, clamped inside the frame."""
    if space == "norm1000":
        px, py = x / 1000 * IMAGE_W, y / 1000 * IMAGE_H
    elif space == "pixels":
        px, py = x, y
    else:
        raise ValueError(f"unknown coordinate space {space!r}")
    return min(max(round(px), 0), IMAGE_W - 1), min(max(round(py), 0), IMAGE_H - 1)


def to_norm(px: float, py: float) -> tuple[float, float]:
    """Image pixels -> manifest-normalized [0,1] coordinates."""
    return round(px / IMAGE_W, 4), round(py / IMAGE_H, 4)
