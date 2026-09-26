"""R305 反证驱动：逐把摘刀 -> 跑整本用例 -> 记录红了哪几条 -> 立即按字节还原并核对 sha256。

只读用：它把 app/rag/spreadsheets.py 临时改坏再按原始字节还原，跑完文件与跑前逐字节相等。
换行一律先归一成 \n 再摘刀（仓库工作树是 CRLF），写回时还原成 CRLF，所以 sha 与终稿同一枚。
重跑：`python tests/fixtures/r305_refutation_driver.py`。
"""
import hashlib
import io
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "app" / "rag" / "spreadsheets.py"
TESTS = "tests/test_r305_spreadsheets.py"

BLADES = [
    ("a 空行不再去掉", "        if not any(line):\n            grid.blank_rows += 1\n            continue\n",
     "        if not any(line):\n            grid.blank_rows += 1\n        if False:\n            continue\n"),
    ("b 合并区域不广播", "    for merge in worksheet.merged_cells.ranges:\n",
     "    for merge in []:\n"),
    ("c 表名里的锚点分隔符不替换", '    cleaned = _cell_text((name or "").replace(ANCHOR_JOIN, " "))\n',
     "    cleaned = _cell_text(name or \"\")\n"),
    ("d 读侧给浮点二次取整", "    return _cell_text(value)\n\n\n@dataclass\nclass _Grid:",
     "    return _cell_text(round(value, 2) if isinstance(value, float) else value)\n\n\n@dataclass\nclass _Grid:"),
    ("e 分隔符不 sniff，硬编逗号", "    chosen = delimiter or sniff_delimiter(text.splitlines())\n",
     "    chosen = delimiter or \",\"\n"),
    ("f 字符顶不裁行（整块照发）", "    if kept >= block.row_count:\n        return block, 0\n",
     "    return block, 0\n"),
    ("g CSV 不走 load_txt，自己按 utf-8 读", "    text = load_txt(str(path))\n",
     "    text = path.read_bytes().decode(\"utf-8\")\n"),
]


def run_tests():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = result.stdout
    names = sorted(re.findall(r"^FAILED .*::(\w+)", out, re.M))
    tally = re.search(r"(\d+) failed, (\d+) passed", out)
    error = re.search(r"^ERROR tests/\w+", out, re.M)
    passed = re.search(r"(\d+) passed", out)
    return (int(tally.group(1)) if tally else 0), len(names), names, bool(error), int(passed.group(1)) if passed else 0


def main():
    original = MODULE.read_bytes()
    base_sha = hashlib.sha256(original).hexdigest()
    print("终稿 sha256:", base_sha[:16], "bytes:", len(original))
    clean = run_tests()
    print("基线（未摘刀）: 红", clean[0], "/ 通过", clean[4], "/ collection error:", clean[3])

    for name, old, new in BLADES:
        text = original.decode("utf-8").replace("\r\n", "\n")
        assert old in text, f"{name}: 找不到刀口 {old[:32]!r}"
        MODULE.write_bytes(text.replace(old, new, 1).replace("\n", "\r\n").encode("utf-8"))
        failed, named, names, errored, _passed = run_tests()
        print(f"\n[{name}] -> 红 {failed} 枚" + ("（含 collection error）" if errored else ""))
        for item in names[:14]:
            print("    ·", item)
        mutated = MODULE.read_bytes()
        assert mutated != original, "刀没摘下去"
        MODULE.write_bytes(original)
        back = MODULE.read_bytes()
        assert hashlib.sha256(back).hexdigest() == base_sha, "还原失败"
        assert back == original
    print("\n还原后 sha256:", hashlib.sha256(MODULE.read_bytes()).hexdigest()[:16], "== 终稿 -> OK")


main()
