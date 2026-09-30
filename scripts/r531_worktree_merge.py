"""R531 铺树器：把一枚执行层工作树的改动搬进主树，按「每枚文件各自的行尾惯例」落盘。

为什么要有它（09-30 现取事故形状）：本仓主树是混排的——脚本与测试件多为 CRLF，部分
`docs/**` 是 LF（blob 内无 CR）。而各执行层工作树在 `core.autocrlf=true` 下把 LF 文件
**检出成 CRLF**，于是「整片拷贝铺树」会把 CRLF 混进 LF 本，当场踩响逐字节钉
（`tests/test_r469_readout_is_generated.py` 就是这么红的：blob 237481 字节无 CR，盘上 244675）。
本器一律以**主树 HEAD 里那枚 blob 的行尾**为准改写，绝不「顺手统一」。

用法：
  python scripts/r531_worktree_merge.py --tree ../be-r523 --list
  python scripts/r531_worktree_merge.py --tree ../be-r523 --apply migrations/0018_x.sql app/trace/schema.py
退出码：0 搬完且逐字节自证过 / 1 至少一枚拒绝搬（不存在、混合行尾、目标惯例判不出）/ 2 用法或环境错。
🔴 它只写工作树文件，绝不 `git add`、绝不 commit——显式列路径提交是总控的活。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORE_SUFFIX = (".bak", ".r57bak", ".orig", ".rej", ".tmp")
IGNORE_NAME_HINTS = ("probe.txt", "scratch", ".tmpfix/", ".tmp-")
IGNORE_PATH_HINTS = ("chroma_db/", ".venv/", "node_modules/")


def git(cwd: Path, *args: str) -> tuple[int, str]:
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def detect(data: bytes) -> str:
    """crlf / lf / mixed / empty —— 混合行尾是要挡的那一形。"""
    if not data:
        return "empty"
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n")
    if lf == 0:
        return "empty"
    if crlf == 0:
        return "lf"
    if crlf == lf:
        return "crlf"
    return "mixed"


def normalize(data: bytes, convention: str) -> bytes:
    """把整枚文件按目标惯例重写；LF 本里混进的 CRLF 会被剥掉，反之补上。"""
    if convention not in ("crlf", "lf"):
        raise ValueError("unknown convention " + convention)
    uniform = data.replace(b"\r\n", b"\n")
    trailing = uniform.endswith(b"\n")
    body = uniform[:-1] if trailing else uniform
    joiner = b"\r\n" if convention == "crlf" else b"\n"
    out = joiner.join(body.split(b"\n"))
    return out + (joiner if trailing else b"")


def blob_convention(path: str) -> str | None:
    """主树 HEAD 里那枚 blob 的行尾；不在 HEAD 里 = None（新件）。"""
    code, out = git(ROOT, "show", "HEAD:" + path)
    if code != 0:
        return None
    raw = subprocess.run(["git", "-C", str(ROOT), "show", "HEAD:" + path],
                         capture_output=True).stdout
    found = detect(raw)
    return found if found in ("crlf", "lf") else None


def sibling_convention(path: str) -> tuple[str | None, str]:
    """新件：按同目录同后缀的在册件多数决；判不出就拒绝搬（不许猜）。"""
    target = Path(path)
    code, out = git(ROOT, "ls-files", str(target.parent) + "/*" + target.suffix)
    names = [l.strip() for l in out.splitlines() if l.strip()]
    tally = {"crlf": 0, "lf": 0}
    for name in names[:12]:
        found = blob_convention(name)
        if found:
            tally[found] += 1
    if tally["crlf"] == tally["lf"]:
        return None, "siblings tie or none: " + str(tally)
    return ("crlf" if tally["crlf"] > tally["lf"] else "lf"), "siblings " + str(tally) + " of " + str(len(names))


def porcelain(tree: Path) -> list[tuple[str, str]]:
    code, out = git(tree, "status", "--porcelain")
    if code != 0:
        return []
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        state, _, path = line[:2], line[2:3], line[3:].strip().strip('"')
        rows.append((state, path))
    return rows


def listable(tree: Path) -> list[tuple[str, str, str, str]]:
    rows = []
    for state, path in porcelain(tree):
        if any(path.endswith(s) for s in IGNORE_SUFFIX) or any(h in path for h in IGNORE_NAME_HINTS) or any(h in path for h in IGNORE_PATH_HINTS):
            continue
        src = tree / path
        if not src.is_file():
            rows.append((state, path, "-", "目录或缺文件，跳过"))
            continue
        found = detect(src.read_bytes())
        conv = blob_convention(path)
        if conv is None:
            guess, note = sibling_convention(path)
            conv = guess or "?"
            note = "新件 " + note
        else:
            note = "在册惯例 " + conv
        flag = "混合行尾!" if found == "mixed" else ""
        rows.append((state, path, found + "->" + conv, note + (" " + flag if flag else "")))
    return rows


def apply_paths(tree: Path, paths: list[str]) -> int:
    failures = 0
    for path in paths:
        src = tree / path
        if not src.is_file():
            print("REJECT " + path + " : 工作树里没有这枚文件")
            failures += 1
            continue
        data = src.read_bytes()
        found = detect(data)
        if found == "mixed":
            print("REJECT " + path + " : 源文件行尾混合，先让执行层归一")
            failures += 1
            continue
        conv = blob_convention(path)
        if conv is None:
            conv, note = sibling_convention(path)
            if conv is None:
                print("REJECT " + path + " : 新件判不出惯例（" + note + "），不许猜")
                failures += 1
                continue
            print("  note " + path + " : " + note)
        out = normalize(data, conv)
        dst = ROOT / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(out)
        back = detect(dst.read_bytes())
        ok = back == conv
        print(("WROTE  " if ok else "BAD    ") + path + " " + str(len(out)) + "B " + conv + (" " + str(dst.stat().st_size) if not ok else ""))
        if not ok:
            failures += 1
    return 1 if failures else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tree", required=True)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--apply", nargs="*", default=None)
    opts = parser.parse_args(argv)
    tree = Path(opts.tree).resolve()
    if not tree.is_dir():
        print("tree missing: " + str(tree))
        return 2
    if opts.list or opts.apply is None:
        for state, path, shape, note in listable(tree):
            print(state.ljust(3) + path.ljust(62) + shape.ljust(16) + note)
        return 0
    return apply_paths(tree, [p for p in opts.apply if p])


if __name__ == "__main__":
    sys.exit(main())
