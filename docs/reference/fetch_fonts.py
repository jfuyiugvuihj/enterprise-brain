"""Download the two variable fonts the login reference needs, self-hosted.

This is the concrete fix for the P0 font bug: theme.css:1 pulls Manrope and
DM Mono from fonts.googleapis.com, which never resolves on a customer intranet,
so the whole screen silently falls back to the browser default.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

BASE = "https://cdn.jsdelivr.net/fontsource/fonts/"
FILES = {
    "manrope-latin-wght.woff2": "manrope:vf@latest/latin-wght-normal.woff2",
    "manrope-latin-ext-wght.woff2": "manrope:vf@latest/latin-ext-wght-normal.woff2",
    "jetbrainsmono-latin-wght.woff2": "jetbrains-mono:vf@latest/latin-wght-normal.woff2",
    "jetbrainsmono-latin-ext-wght.woff2": "jetbrains-mono:vf@latest/latin-ext-wght-normal.woff2",
}

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"}

for name, rel in FILES.items():
    target = OUT / name
    if target.exists() and target.stat().st_size > 1000:
        print("cached", name, target.stat().st_size)
        continue
    req = urllib.request.Request(BASE + rel, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = resp.read()
    target.write_bytes(data)
    print("saved", name, len(data))
