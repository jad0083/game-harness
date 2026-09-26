#!/usr/bin/env python3
"""Capture a known-screen template from a live frame and measure how distinctive it is.

    scripts/play/capture-template.py FRAME X0 Y0 X1 Y1 NAME [--against FRAME ...] [--corpus stellaris]

FRAME is a 1568x882 screenshot (e.g. play/current_screen.jpg); the box is in its pixels.
Writes corpora/<corpus>/templates/NAME.png (default corpus: galciv4) and prints the normalized
`template_roi` to paste into a [screens.*] entry in that corpus's manifest.toml. With --against, prints the template
distance on other frames (the same box on frames WITHOUT the screen should be >= 0.10; the
manifest default match threshold is 0.08, use 0.05-0.06 for small text).

Pick a box that is unique to the screen and static: a dialog title, a fixed button label, or an
icon. Avoid areas with animation, the map behind a dialog, or text that changes (names, numbers).
"""
import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[2]


def diff(a: Image.Image, b: Image.Image) -> float:
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3 / 255


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("frame")
    ap.add_argument("box", nargs=4, type=int, metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("name")
    ap.add_argument("--against", nargs="*", default=[])
    ap.add_argument("--corpus", default="galciv4", help="corpus folder under corpora/ (galciv4, stellaris)")
    a = ap.parse_args()
    im = Image.open(a.frame).convert("RGB")
    w, h = im.size
    x0, y0, x1, y1 = a.box
    tpl = im.crop((x0, y0, x1, y1))
    out = ROOT / "corpora" / a.corpus / "templates" / f"{a.name}.png"
    tpl.save(out)
    roi = [round(x0 / w, 4), round(y0 / h, 4), round((x1 - x0) / w, 4), round((y1 - y0) / h, 4)]
    print(f"wrote {out.relative_to(ROOT)}  ({x1 - x0}x{y1 - y0} px)")
    print(f'template = "templates/{a.name}.png"')
    print(f"template_roi = {roi}")
    for f in a.against:
        other = Image.open(f).convert("RGB").crop((x0, y0, x1, y1))
        print(f"  distance on {f}: {diff(other, tpl):.3f}")


if __name__ == "__main__":
    main()
