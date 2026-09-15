"""Build a text-free L0 background plate for the login screen.

Two passes:
  1. inpaint the baked-in copy (brand lockup, headline, lead, capability tiles,
     tagline, latin track) out of the shipped artwork
  2. lay a smooth left-to-right vignette over the remaining half-tone residue so
     the left column becomes a clean dark field for real DOM text

The result is the asset the frontend should ship: artwork only, no type.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])

# (x0, y0, x1, y1, gray_threshold) - boxes cover baked-in copy only.
TEXT_BOXES = [
    (60, 80, 370, 165, 60),       # brand lockup (hex mark + wordmark + latin)
    (1275, 100, 1640, 150, 55),   # top-right tagline
    (60, 272, 590, 450, 90),      # headline, two lines
    (60, 445, 445, 505, 70),      # lead sentence
    (60, 522, 485, 662, 34),      # capability tiles + labels
    (60, 686, 420, 736, 40),      # ENTERPRISE BRAIN track
]

# Left vignette: fully opaque at x=0, gone by SCRIM_END * width.
SCRIM_END = 0.46
SCRIM_RGB = (22, 11, 6)  # BGR for #060b16


def main() -> None:
    img = cv2.imread(str(SRC), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit("cannot read " + str(SRC))
    h, w = img.shape[:2]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mask = np.zeros(gray.shape, np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    for x0, y0, x1, y1, thr in TEXT_BOXES:
        region = gray[y0:y1, x0:x1]
        hit = (region > thr).astype(np.uint8) * 255
        hit = cv2.dilate(hit, kernel)
        mask[y0:y1, x0:x1] = np.maximum(mask[y0:y1, x0:x1], hit)

    plate = cv2.inpaint(img, mask, 6, cv2.INPAINT_NS).astype(np.float32)

    # Flatten the repaired pixels toward their neighbourhood so the inpaint haze
    # does not read as a smudge on a near-black background.
    blur = cv2.GaussianBlur(plate, (0, 0), 21)
    soft = (mask.astype(np.float32) / 255.0)[..., None] * 0.6
    plate = plate * (1 - soft) + blur * soft

    # Left vignette with a smoothstep ramp.
    xs = np.linspace(0.0, 1.0, w) / SCRIM_END
    ramp = np.clip(xs, 0.0, 1.0)
    ramp = ramp * ramp * (3.0 - 2.0 * ramp)
    scrim = (1.0 - ramp)[None, :, None]
    plate = plate * (1.0 - scrim) + np.array(SCRIM_RGB, np.float32)[None, None, :] * scrim

    plate = np.clip(plate, 0, 255).astype(np.uint8)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT), plate)
    print(str(OUT) + " mask_px=" + str(int((mask > 0).sum())) + " size=" + str(w) + "x" + str(h))


if __name__ == "__main__":
    main()
