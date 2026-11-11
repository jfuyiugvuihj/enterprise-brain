"""R531 铺树器：把一枚执行层工作树的改动搬进主树，按「每枚文件各自的行尾惯例」落盘。

为什么要有它（09-30 现取事故形状）：本仓主树是混排的——脚本与测试件多为 CRLF，部分
`docs/**` 是 LF（blob 内无 CR）。而各执行层工作树在 `core.autocrlf=true` 下把 LF 文件
**检出成 CRLF**，于是「整片拷贝铺树」会把 CRLF 混进 LF 本，当场踩响逐字节钉
（`tests/test_r469_readout_is_generated.py` 就是这么红的：blob 237481 字节无 CR，盘上 244675）。
归位口径（R531 定、R552 补）：在册件按**主树盘上现在那一版行尾**，新件按**这枚 blob 被 git 检出之后盘上会长成的那一版**（`checkout_form`）。两者都不许「顺手统一」，也不许拿同目录 blob 多数去猜——blob 的行尾不等于检出的形态。

用法：
  python scripts/r531_worktree_merge.py --tree ../be-r523 --list
  python scripts/r531_worktree_merge.py --tree ../be-r523 --apply migrations/0018_x.sql app/trace/schema.py
退出码：0 搬完且逐字节自证过 / 1 至少一枚拒绝搬（不存在、混合行尾、目标惯例判不出）/ 2 用法或环境错。
🔴 它只写工作树文件，绝不 `git add`、绝不 commit——显式列路径提交是总控的活。
"""
from __future__ import annotations

import argparse
import os
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


def native_form() -> str:
    """这台机的「平台行尾」：Windows 是 crlf，其余是 lf（git 的 core.eol=native 就这么算）。"""
    return "crlf" if os.name == "nt" else "lf"


def git_attr(path: str, *attrs: str) -> dict | None:
    """git 对这枚路径的 text/eol 判定；问不到（仓外、报错）就是 None，这条道上不许猜。"""
    code, out = git(ROOT, "check-attr", *attrs, "--", path)
    if code != 0:
        return None
    found = {}
    for line in out.splitlines():
        parts = line.split(": ")
        if len(parts) >= 3:
            found[parts[-2].strip()] = parts[-1].strip()
    return found or None


def git_config(name: str) -> str | None:
    """生效配置（system/global/local 逐层覆盖之后剩下的那一枚）。未设=""，读不到=None。"""
    code, out = git(ROOT, "config", "--get", name)
    if code == 0:
        return out.strip()
    return "" if code == 1 else None


def checkout_form(path: str, data: bytes) -> tuple:
    """R531/R552：新件落盘该长成「这枚 blob 被 git 检出之后盘上的样子」，不再按同目录多数决猜。

    为什么必须换掉 siblings 那一格：`sibling_convention()` 数的是 **blob** 行尾（它经
    `blob_convention()` 取 `git show HEAD:<path>` 的字节），而本仓 core.autocrlf=true 且没有
    .gitattributes ⇒ 文本件的 blob 恒为 LF，于是同目录抽十二枚永远数出 crlf 零枚。09-30 实测：
    新件按那个读数铺成 LF，而一次全新检出会把它们改回 CRLF——盘上 LF 根本不是稳定态，拿「纸的
    换行符成对」当判据的钉当场红十二枚，最后只能由总控手工归 CRLF；手工归位恰恰是本器存在的
    理由所要消灭的东西。

    判据照 git 自己的规则排（convert.c 的口径，收成用得上的一串分支）：
      ① 前 8000 字节含 NUL ⇒ git 判二进制，检出不做行尾转换 ⇒ asis（按源件字节原样落）；
      ② -text（text=unset）⇒ 同上 asis；
      ③ 显式 eol 属性优先：crlf / lf / native（native ⇒ 平台行尾）；
      ④ 无 eol 时由**生效的** core.autocrlf 支配：true ⇒ 检出补 CRLF，input ⇒ 留 LF，
         false 或未设 ⇒ 不转换（asis）；显式 text（set/auto）而无 eol 时取 core.eol（缺省 native）。
    问不到答案 ⇒ 交回 (None, 理由)：本器对「判不出」一律拒绝搬，从不猜。
    """
    if b"\0" in data[:8000]:
        return "asis", "检出形态=原样字节（前 8000 字节含 NUL，git 判二进制，不做行尾转换）"
    attrs = git_attr(path, "text", "eol")
    autocrlf_cfg, eol_cfg = git_config("core.autocrlf"), git_config("core.eol")
    if attrs is None or autocrlf_cfg is None or eol_cfg is None:
        return None, "判不出：git 问不到 text/eol 属性或 core.autocrlf/core.eol（" + path + "）"
    text_attr = attrs.get("text", "unspecified")
    eol_attr = attrs.get("eol", "unspecified")
    if text_attr == "unset":
        return "asis", "检出形态=原样字节（-text 属性，git 不做转换）"
    if eol_attr in ("crlf", "lf"):
        return eol_attr, "检出形态=eol=" + eol_attr + " 属性"
    if eol_attr == "native":
        return native_form(), "检出形态=eol=native ⇒ 平台行尾 " + native_form()
    autocrlf = autocrlf_cfg.lower()
    if autocrlf == "true":
        return "crlf", "检出形态=crlf（core.autocrlf=true 且无 text/eol 属性 ⇒ 检出补 CR）"
    if autocrlf == "input":
        return "lf", "检出形态=lf（core.autocrlf=input ⇒ 检出不补 CR）"
    if text_attr in ("set", "auto"):
        if eol_cfg in ("crlf", "lf"):
            return eol_cfg, "检出形态=core.eol=" + eol_cfg + "（text=" + text_attr + "）"
        return native_form(), ("检出形态=text=" + text_attr
                               + " 且 core.eol 缺省 native ⇒ 平台行尾 " + native_form())
    return "asis", "检出形态=原样字节（无 text/eol 属性，core.autocrlf=" + (autocrlf or "未设") + "）"


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
        conv = target_convention(path)[0]
        if conv is None:
            conv, note = checkout_form(path, src.read_bytes())
            if conv is None:
                conv, note = "?", "新件" + note
            else:
                note = "新件 " + note
        else:
            note = "在册惯例 " + conv
        flag = "混合行尾!" if found == "mixed" else ""
        rows.append((state, path, found + "->" + conv, note + (" " + flag if flag else "")))
    return rows


def target_convention(path: str):
    """在册件一律按主树盘上现在那一版行尾归位，不按 blob。

    为什么不是 blob：这台机 core.autocrlf=true 且没有 .gitattributes，检出出来的
    在册件盘上是 CRLF（现取 git ls-files --eol：app/api/v1/chat.py = i/lf w/crlf）。
    而被跟踪件里有一族钉直接读盘上那份文件、并拿 CR-LF 拼锚点去改它做反证——最典型就是
    tests/test_r48_headline_never_enters_the_text_ledger.py 的 D1：_crlf(CALL_ANCHOR)。
    上一班本器按 blob 把 chat.py 铺成纯 LF，那枚锚当场命中 0 处，r48 的 D1 反证红在
    「找不到锚」上——那枚红是铺树器的形状造成的，不是执行层改坏了产品。
    规则改成正解：盘上是什么行尾就铺成什么行尾；盘上没有这枚文件（新件）才退回
    blob 惯例，再退回同目录多数决（平票仍拒绝搬）。
    """
    dst = ROOT / path
    if dst.is_file():
        found = detect(dst.read_bytes())
        if found in ("crlf", "lf"):
            return found, "盘上惯例 " + found
    conv = conv = blob_convention(path)
    if conv is not None:
        return conv, "blob 惯例 " + conv + "（盘上读不到）"
    return None, ""


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
        conv, _why = target_convention(path)
        asis = False
        if conv is None:
            conv, note = checkout_form(path, data)
            if conv is None:
                print("REJECT " + path + " : 新件判不出检出形态（" + note + "），不许猜")
                failures += 1
                continue
            _guess, tally = sibling_convention(path)
            print("  note " + path + " : " + note + "；siblings → " + tally + "（只作诊断，不决策）")
            asis = conv == "asis"
        out = data if asis else normalize(data, conv)
        dst = ROOT / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(out)
        back = detect(dst.read_bytes())
        ok = back == (detect(data) if asis else conv)
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
