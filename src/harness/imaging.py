"""Screenshot post-processing: downscale for the model, grid overlay, coordinate mapping."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

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


def render(png: bytes, left: int = 0, top: int = 0, max_side: int = MAX_SIDE,
           max_upscale: float = 1.0, grid: bool = False, quality: int = 85) -> tuple[bytes, View]:
    """Resize a captured PNG to fit max_side, optionally draw a grid, and encode as JPEG."""
    img = Image.open(io.BytesIO(png)).convert("RGB")
    sw, sh = img.size
    factor = min(max_side / max(sw, sh), max_upscale)
    iw, ih = max(round(sw * factor), 1), max(round(sh * factor), 1)
    if (iw, ih) != (sw, sh):
        img = img.resize((iw, ih), Image.LANCZOS)
    if grid:
        img = draw_grid(img)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality)
    return out.getvalue(), View(left, top, sw / iw, iw, ih)


def draw_grid(img: Image.Image, step: int = 100) -> Image.Image:
    """Overlay labelled gridlines every `step` image pixels to help pick coordinates."""
    base = img.convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = ImageFont.load_default()
    w, h = base.size
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
    return Image.alpha_composite(base, layer).convert("RGB")
