"""Screenshot post-processing: downscale for the model, grid overlay, coordinate mapping."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageDraw, ImageFont

# Long-edge size the vision model handles without further internal downscaling.
MAX_SIDE = 1568


@dataclass(frozen=True)
class View:
    """Maps pixel coordinates in a returned image back to screen pixels."""

    left: int
    top: int
    scale: float  # screen pixels per image pixel
    width: int  # image size
    height: int

    def to_screen(self, x: float, y: float) -> tuple[int, int]:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError(
                f"({x}, {y}) is outside the last image ({self.width}x{self.height}); "
                "use coordinates from the most recent screenshot/zoom"
            )
        return round(self.left + x * self.scale), round(self.top + y * self.scale)

    def rect_to_screen(self, x: float, y: float, w: float, h: float) -> tuple[int, int, int, int]:
        x0, y0 = self.to_screen(x, y)
        x1 = min(round(self.left + (x + w) * self.scale), round(self.left + self.width * self.scale))
        y1 = min(round(self.top + (y + h) * self.scale), round(self.top + self.height * self.scale))
        return x0, y0, max(x1 - x0, 1), max(y1 - y0, 1)


_GRID_CACHE: dict[tuple[int, int, int], Image.Image] = {}


def _get_grid_layer(w: int, h: int, step: int = 100) -> Image.Image:
    key = (w, h, step)
    layer = _GRID_CACHE.get(key)
    if layer is not None:
        return layer
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = ImageFont.load_default()
    for x in range(step, w, step):
        d.line([(x, 0), (x, h)], fill=(255, 255, 0, 90), width=1)
    for y in range(step, h, step):
        d.line([(0, y), (w, y)], fill=(255, 255, 0, 90), width=1)
    for x in range(0, w, step):
        for y in range(0, h, step):
            label = f"{x},{y}"
            box = d.textbbox((x + 2, y + 1), label, font=font)
            d.rectangle(box, fill=(0, 0, 0, 150))
            d.text((x + 2, y + 1), label, fill=(255, 255, 0, 255), font=font)
    _GRID_CACHE[key] = layer
    return layer


def draw_grid(img: Image.Image, step: int = 100) -> Image.Image:
    """Overlay labelled gridlines every `step` image pixels to help pick coordinates."""
    base = img.convert("RGBA")
    layer = _get_grid_layer(base.width, base.height, step)
    return Image.alpha_composite(base, layer).convert("RGB")


def render(png: bytes, left: int = 0, top: int = 0, max_side: int = MAX_SIDE,
           max_upscale: float = 1.0, grid: bool = False, quality: int = 80,
           orig_w: int | None = None, orig_h: int | None = None) -> tuple[bytes, View]:
    """Resize a captured PNG to fit max_side, optionally draw a grid, and encode as JPEG."""
    img = Image.open(io.BytesIO(png)).convert("RGB")
    sw, sh = img.size
    factor = min(max_side / max(sw, sh), max_upscale)
    iw, ih = max(round(sw * factor), 1), max(round(sh * factor), 1)
    if (iw, ih) != (sw, sh):
        img = img.resize((iw, ih), Image.BILINEAR)
    if grid:
        img = draw_grid(img)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality)
    scale = (orig_w / iw) if orig_w else (sw / iw)
    return out.getvalue(), View(left, top, scale, iw, ih)


def detect_change_bbox(before_bytes: bytes, after_bytes: bytes, threshold: int = 25,
                       padding: int = 8) -> tuple[int, int, int, int] | None:
    """Find the bounding box (x, y, w, h) of visual changes between two images.
    Returns None if no pixels changed beyond threshold.
    """
    im1 = Image.open(io.BytesIO(before_bytes)).convert("RGB")
    im2 = Image.open(io.BytesIO(after_bytes)).convert("RGB")
    if im1.size != im2.size:
        return (0, 0, im2.width, im2.height)
    diff = ImageChops.difference(im1, im2).convert("L")
    mask = diff.point(lambda p: 255 if p > threshold else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - padding)
    y0 = max(0, y0 - padding)
    x1 = min(im2.width, x1 + padding)
    y1 = min(im2.height, y1 + padding)
    return (x0, y0, max(1, x1 - x0), max(1, y1 - y0))


def highlight_changes(image_bytes: bytes, bbox: tuple[int, int, int, int],
                      outline: tuple[int, int, int] = (255, 0, 128),
                      width: int = 3, quality: int = 80) -> bytes:
    """Draw a highlighted bounding box on the image to show what changed."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    d = ImageDraw.Draw(img)
    x, y, w, h = bbox
    d.rectangle([x, y, x + w, y + h], outline=outline, width=width)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality)
    return out.getvalue()


def crop_region(image_bytes: bytes, x: int, y: int, w: int, h: int, quality: int = 85) -> bytes:
    """Crop a sub-region (x, y, w, h) from an image."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    cropped = img.crop((x, y, x + w, y + h))
    out = io.BytesIO()
    cropped.save(out, format="JPEG", quality=quality)
    return out.getvalue()


