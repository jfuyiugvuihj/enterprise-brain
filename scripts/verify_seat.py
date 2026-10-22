#!/usr/bin/env python
"""verify_seat.py -- 收席取证与搬运：把总控的手工动作变成脚本（2026-10-06 改章后补的 CI 替身）。

跑法：
    python scripts/verify_seat.py --tree ../be-r724 --allow app/api/v1/chat.py,deploy/queue_worker.py
    再加 --apply-check                          在主树 git apply --check（只验能不能落，不落地）
    再加 --stage dirty --tests tests/test_x.py   跑同名件并标明这是哪一态；commit 后再 --stage clean 跑一遍
    再加 --patch-out <file>                      patch 导出点（缺省 %TEMP% 下 evalrun/seat-<树名>.patch）

默认不写盘、不 commit、不 apply。它只干两件事：**在收席那一刻同时现取三枚读数**
（diff --numstat HEAD / ls-files --others / rev-list --count），以及**把越出写域的文件逐枚点名**。
引用几分钟前的旧账就收席＝事故 #107 的形状，那枚「留在别人树上的独有牙」会被当成零写入扔掉。
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VENV_PY = REPO / ".venv" / "Scripts" / "python.exe"


def sh(cwd, *args):
    proc = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=str(cwd),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def norm(path):
    return path.replace(chr(92), "/")


def hit(name, pat):
    """写域匹配：目录前缀必须以斜杠收尾才算前缀，glob 走 fnmatch。"""
    if pat.endswith("/"):
        return name.startswith(pat)
    if pat.endswith("*"):
        return name.startswith(pat[:-1])
    return name == pat or fnmatch.fnmatch(name, pat)


def resolve_tree(raw):
    """席位树可能是 worktree 根，也可能是其下的项目目录；两处都试，取不到就报话。"""
    for cand in (Path(raw).resolve(), Path(raw).resolve() / REPO.name):
        if cand.is_dir():
            rc, _out = sh(cand, "rev-parse", "HEAD")
            if rc == 0:
                return cand, None
    return None, ("这枚路径不是能用的工作树：" + str(raw)
                  + "（用 git worktree list 现取路径，新席位一般在 .codex/worktrees/<树名>/"
                  + REPO.name + "）")


def changed_files(tree, base, head):
    """席位独有的改动＝base..HEAD 提交里的 ＋ 工作树脏的 ＋ 未跟踪的。"""
    found = set()
    _rc, listed = sh(tree, "log", base + ".." + head, "--name-only", "--pretty=format:")
    for line in listed.splitlines():
        if line.strip():
            found.add(norm(line.strip()))
    _rc2, numstat = sh(tree, "diff", "--numstat", "HEAD")
    _rc3, others = sh(tree, "ls-files", "--others", "--exclude-standard")
    return found, numstat, others


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tree", required=True, help="席位那棵工作树")
    ap.add_argument("--base", default="auto", help="基点 sha；auto＝与主树 HEAD 的 merge-base")
    ap.add_argument("--allow", default="", help="写域，逗号分隔的路径或 glob；不填则不做越界判定")
    ap.add_argument("--apply-check", action="store_true", help="在主树 git apply --check，不落地")
    ap.add_argument("--patch-out", default="", help="patch 导出路径")
    ap.add_argument("--stage", default="", help="这一遍是哪一态：dirty / clean")
    ap.add_argument("--tests", default="", help="同名件清单，逗号分隔")
    args = ap.parse_args()

    tree, why = resolve_tree(args.tree)
    if tree is None:
        print("[verify_seat] " + why, flush=True)
        return 2
    head = sh(tree, "rev-parse", "HEAD")[1].strip()

    if args.base == "auto":
        rc_mb, mb = sh(REPO, "merge-base", "HEAD", head)
        if rc_mb != 0:
            print("[verify_seat] 问不到基点（merge-base 失败）：" + mb.strip()[:160], flush=True)
            return 2
        base = mb.strip()
    else:
        base = args.base

    rc_c, cnt_raw = sh(tree, "rev-list", "--count", base + ".." + head)
    cnt = cnt_raw.strip()
    own = int(cnt) if cnt.isdigit() else -1

    committed, numstat, others = changed_files(tree, base, head)
    dirty = [ln for ln in numstat.splitlines() if ln.strip()]
    untracked = [ln for ln in others.splitlines() if ln.strip()]
    everything = sorted(committed | {norm(ln.split(chr(9))[2]) for ln in dirty
                                     if len(ln.split(chr(9))) >= 3} | {norm(ln) for ln in untracked})

    print("[verify_seat] 席位 " + tree.name + " HEAD " + head[:10] + " 基点 " + base[:10], flush=True)
    print("  1 三枚读数（同一刻现取）：独有提交 " + str(own) + " 笔 / 工作树脏 " + str(len(dirty))
          + " 枚 / 未跟踪 " + str(len(untracked)) + " 枚", flush=True)
    print("  2 独有改动 " + str(len(everything)) + " 枚文件，逐枚点名＋内容 sha256：", flush=True)
    for name in everything:
        handle = tree / name
        digest = "已删除或目录" if not handle.is_file() else hashlib.sha256(handle.read_bytes()).hexdigest()[:16]
        print("      " + name + "  " + digest, flush=True)

    blocked = 0
    allow = [norm(p.strip()) for p in args.allow.split(",") if p.strip()]
    if allow:
        outside = [name for name in everything
                   if not any(hit(name, pat) for pat in allow)]
        if outside:
            blocked = 1
            print("  [越界] 这几枚不在写域里，不许顺手收：退回重切，或由新单承接——" + "、".join(outside), flush=True)
        else:
            print("  写域校验通过（全部命中：" + "，".join(allow) + "）", flush=True)

    patch_dir = Path(args.patch_out) if args.patch_out else Path(tempfile.gettempdir()) / "evalrun"
    patch_dir.mkdir(parents=True, exist_ok=True)
    label = tree.name if tree.name != REPO.name else tree.parent.name
    patch_path = patch_dir / ("seat-" + (label or "seat") + "-" + head[:8] + ".patch")
    _rc_p, patch = sh(tree, "diff", base + ".." + head)
    patch_path.write_text(patch, encoding="utf-8", newline="\n")
    print("  3 patch " + str(patch_path) + "（" + str(len(patch)) + " 字符，sha256 "
          + hashlib.sha256(patch.encode("utf-8")).hexdigest()[:16]
          + "）。未跟踪文件不在 patch 里——那几枚必须逐枚点名搬，漏件过一次（事故 #121 同族）", flush=True)

    if args.apply_check:
        rc_a, err = sh(REPO, "apply", "--check", str(patch_path))
        print("  4 apply --check rc=" + str(rc_a) + ("（能落主树）" if rc_a == 0 else
              "（落不下：" + err.strip()[:180] + "）"), flush=True)
        if rc_a != 0:
            blocked = 1

    tests = [t.strip() for t in args.tests.split(",") if t.strip()]
    if tests:
        py = str(VENV_PY) if VENV_PY.is_file() else sys.executable
        cmd = [py, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "-o", "addopts="] + tests
        print("  5 同名件 态=" + (args.stage or "未标（必须标，两态各跑一遍）") + "：" + "、".join(tests), flush=True)
        started = time.time()
        rc_t = subprocess.call(cmd, cwd=str(REPO))
        print("     rc=" + str(rc_t) + " 墙钟 " + str(round(time.time() - started, 1)) + " s", flush=True)
        if rc_t != 0:
            blocked = 1

    print("  回滚这一笔＝git revert -n <那笔 sha> 之后重建镜像＋--force-recreate backend worker scheduler；"
          "回滚验过之前别 archive 这棵树", flush=True)
    print("[verify_seat] " + ("收席阻塞：见上面带方括号的每一行" if blocked else "取证齐、无越界、无落不下"), flush=True)
    return blocked


if __name__ == "__main__":
    raise SystemExit(main())
