"""R382: inject the generated reading tables into the doc at {{Tn}} placeholders.

The doc must not contain a hand-typed number, so every table comes out of
r382_digest.py and is pasted here by this script. Output is pure CRLF, no BOM.
"""
from __future__ import annotations

import os
import re
import sys

TABLES = sys.argv[1]
PROSE = sys.argv[2]
DOC = sys.argv[3]

with open(TABLES, encoding="utf-8") as handle:
    raw = handle.read().replace("\r\n", "\n")

sections = {}
for block in re.split(r"(?m)^### ", raw)[1:]:
    lines = block.split("\n")
    sections[lines[0].split()[0]] = "### " + block.strip("\n")

with open(PROSE, encoding="utf-8") as handle:
    prose = handle.read().replace("\r\n", "\n")

missing = [key for key in re.findall(r"\{\{(\w+)\}\}", prose) if key not in sections]
if missing:
    raise SystemExit(f"no generated table named {missing}")

text = re.sub(r"\{\{(\w+)\}\}", lambda m: sections[m.group(1)], prose)
destination = os.path.abspath(DOC)
assert destination.startswith(os.path.abspath("docs" + os.sep + "perf")), destination
with open(destination, "wb") as handle:
    handle.write(text.replace("\n", "\r\n").encode("utf-8"))
with open(destination, "rb") as handle:
    data = handle.read()
lone = len(re.findall(rb"(?<!\r)\n", data))
crlf = data.count(b"\r\n")
bom = data[:3] == b"\xef\xbb\xbf"
print(f"{destination}: {len(data)} bytes, CRLF={crlf}, lone LF={lone}, BOM={bom}")