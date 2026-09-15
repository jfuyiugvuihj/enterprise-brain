"""Build the screen-blend earth element from the de-texted plate.

Output is meant to be composited with mix-blend-mode: screen over a CSS base,
so every dark pixel becomes transparent automatically. Left/right edges are
feathered to black so the element melts into the base with no visible seam.
"""
import sys
import cv2
import numpy as np

SRC = sys.argv[1] if len(sys.argv) > 1 else r"art\login-plate.png"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"art\login-earth"

im = cv2.imread(SRC, cv2.IMREAD_COLOR)
h, w = im.shape[:2]
x0, x1 = int(w * 0.205), int(w * 0.815)
crop = im[:, x0:x1].copy()
ch, cw = crop.shape[:2]
print("crop", cw, "x", ch)

g = np.linspace(0.0, 1.0, cw, dtype=np.float32)
FEATHER_L, FEATHER_R = 0.30, 0.22
left = np.clip(g / FEATHER_L, 0.0, 1.0)
right = np.clip((1.0 - g) / FEATHER_R, 0.0, 1.0)
ramp = np.minimum(left, right)
ramp = ramp * ramp * (3.0 - 2.0 * ramp)  # smoothstep
ramp = ramp ** 0.85

top = np.linspace(0.0, 1.0, ch, dtype=np.float32)
top_ramp = np.clip((1.0 - top) / 0.10, 0.0, 1.0)
ramp2 = np.minimum(ramp[None, :], top_ramp[:, None])

f = crop.astype(np.float32) * ramp2[..., None] * 1.06
f = np.clip(f, 0, 255).astype(np.uint8)

cv2.imwrite(OUT + ".png", f)
ok = cv2.imwrite(OUT + ".webp", f, [cv2.IMWRITE_WEBP_QUALITY, 82])
print("webp ok:", ok)
