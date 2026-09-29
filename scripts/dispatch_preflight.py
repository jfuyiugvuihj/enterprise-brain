#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R491 · 派工词落笔前的机器校尺（全程只读）：件名 / 行号 / 号账三档。

病根（09-29 一天四犯，事故 #82/#85/#90/#91）：派工词里写进不存在的件名、不存在的
venv 路径、从没立过的单号，下一班照着跑就白烧一轮。这台尺子把「落笔前先机器校一遍」
从自觉变成能失败的牙。

三档检查：
  A 件名  —— 文本里所有 repo-relative 路径引用逐枚对「磁盘 + git ls-files」双层核验，
             MISSING（两样都没）与 UNTRACKED_BUT_ON_DISK（盘上有、库里没）分开报，
             TRACKED_BUT_OFF_DISK（库里在、这棵树没 checkout）再单列一档；
             绝对路径 / `%TEMP%` / 反斜杠路径立 NOT_IN_REPO 一档，只报不判死（附 EXISTS/ABSENT）。
  B 行号  —— 每枚 `path:NNN` 用**现读磁盘字节**的行数判 IN_RANGE / OUT_OF_RANGE；
             行数以「三种换行（CRLF/LF/CR）全展开」为口径（最大那一档，对任何编辑器口径都不冤），
             换行不纯的件附注 MIXED_EOL。脚本内不存任何行数常量。
  C 号账  —— 每枚 `R\\d{2,3}` 现取 `git log --all -F --grep=<号>` 与 docs 提及两路证据，
             分 HAS_COMMIT / PAPER_ONLY / NEVER_FILED 三档，不许塌档。

纪律：只读。子进程白名单只有 `git log` 与 `git ls-files`，零网络、零写盘、不起服务、不碰模型。
退出码：0 全绿 / 1 咬到红牙 / 2 环境或输入错。

用法：
    python scripts/dispatch_preflight.py docs/handoff/xxx.md
    python scripts/dispatch_preflight.py - < dispatch.txt
    python scripts/dispatch_preflight.py --text "派工词一句话，引用 tests/test_x.py:1"
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: 分隔符一律 chr()/bytes() 现取，不写转义字面量（换行与 NUL 走样就是本单要治的那族病）。
LF = chr(10)
SOH = chr(1)
NUL_B = bytes((0,))
CRLF_B = bytes((13, 10))

#: 子进程白名单：除这两枚 git 子命令之外，本件不许起任何进程。
ALLOWED_GIT = ("log", "ls-files")

#: 哪些顶层目录算「repo-relative 引用」。列在这里的必须是仓里真存在的顶层目录（有钉咬）。
SCOPE_DIRS = ("app", "data", "deploy", "docs", "documents", "frontend",
              "migrations", "scripts", "static", "tests")

OK = "OK"
DIR_OK = "DIR_OK"
TREE_SELF = "WORKTREE_SELF"
UNTRACKED = "UNTRACKED_BUT_ON_DISK"
OFFDISK = "TRACKED_BUT_OFF_DISK"
MISSING = "MISSING"
DIR_MISSING = "DIR_MISSING"
NOT_IN_REPO = "NOT_IN_REPO"
IN_RANGE = "IN_RANGE"
OUT_OF_RANGE = "OUT_OF_RANGE"
UNVERIFIABLE = "UNVERIFIABLE"
HAS_COMMIT = "HAS_COMMIT"
PAPER_ONLY = "PAPER_ONLY"
NEVER_FILED = "NEVER_FILED"

#: 红档（判死）与警档（只报）。
RED_STATUSES = (MISSING, DIR_MISSING, UNTRACKED, OFFDISK, OUT_OF_RANGE, NEVER_FILED)
WARN_STATUSES = (NOT_IN_REPO, PAPER_ONLY, UNVERIFIABLE)

# ---------------------------------------------------------------------------
# 抽取：件名 / 行号 / 单号
# ---------------------------------------------------------------------------

#: 出现即截断件名：`*` 是通配、`:` `#` 是行号尾的起点、引号与中文标点是词的边界。
_STOP_CHARS = " `<>|?*\"'，。、；：！？（）「」『』【】《》…—{}:#＃"
_TAIL = "[^\\s" + re.escape(_STOP_CHARS) + "]"
_PREFIX = r"(?:" + "|".join(SCOPE_DIRS) + r")/"

#: repo-relative 件名，可带 `:NNN`／`：NNN-NNN`／`#LNNN` 行号尾（第三段冒号按列号忽略）。
REL_RE = re.compile(
    r"(?<![A-Za-z0-9_.\-/\\%])"
    r"(?P<path>" + _PREFIX + _TAIL + r"*(?:/" + _TAIL + r"*)*)"
    r"(?P<spec>(?::|：)[0-9]+(?:[-~][0-9]+)?(?:(?::|：)[0-9]+)?|[#＃][Ll]?[0-9]+(?:[-~][Ll]?[0-9]+)?)?"
)

#: 库外路径四式：盘符、`%VAR%`、UNC／裸反斜杠、POSIX 绝对。
_SPEC_TAIL = r"(?:(?::|：)[0-9]+(?:[-~][0-9]+)?)?"
DRIVE_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]" + _TAIL + r"*" + _SPEC_TAIL)
PERCENT_RE = re.compile(r"%[A-Za-z_][A-Za-z0-9_]*%[\\/]" + _TAIL + r"*(?:[\\/]" + _TAIL + r"*)*" + _SPEC_TAIL)
BACKSLASH_RE = re.compile(r"(?<![A-Za-z0-9_.\\-])" + _TAIL + r"*(?:\\+" + _TAIL + r"*)+" + _SPEC_TAIL)
POSIX_RE = re.compile(r"(?<![A-Za-z0-9_.\-~%])(?:~/|/(?!/))" + _TAIL + r"*(?:/" + _TAIL + r"*)+" + _SPEC_TAIL)
EXTERNAL_RES = (DRIVE_RE, PERCENT_RE, BACKSLASH_RE, POSIX_RE)

#: 单号：R + 2~3 位数字，可带一枚小写字母后缀（R205a），前后不许再粘字母数字。
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_])R[0-9]{2,3}[a-z]?(?![0-9A-Za-z])")
NUMBER_RE_B = re.compile(rb"(?<![A-Za-z0-9_])R[0-9]{2,3}[a-z]?(?![0-9A-Za-z])")

_TRAILING_SPEC = re.compile(r"[:：#＃]{1,2}[Ll]?([0-9]+(?:[-~][0-9]+)?)$")
_LINE_BREAK = re.compile(rb"\r\n|\r|\n")


class SourceError(Exception):
    """环境或出处读不到：不是「账错」，不许混进红牙。"""


def looks_like_path(token):
    """反斜杠那一族太容易误抓（`\\d{2,3}` 之类），过一道闸再认。"""
    if "\\" in token:
        if token.count("\\") >= 2:
            return True
        tail = re.split(r"\\+", token)[-1]
        return bool(re.search(r"[A-Za-z0-9_.\-.]+\.[A-Za-z0-9]{1,8}$", tail))
    if "/" in token:
        return token.count("/") >= 2 or bool(re.search(r"\.[A-Za-z0-9]{1,8}$", token.split("/")[-1]))
    return False


def split_trailing_spec(token):
    """把绝对路径尾巴上的 `:NNN` 摘下来当行号，别让它污染件名。"""
    match = _TRAILING_SPEC.search(token)
    if not match:
        return token, None
    body = token[:match.start()]
    if not body or (len(body) == 2 and body[1] == ":"):
        return token, None
    return body, match.group(0)


def parse_spec(spec):
    """`:623-655` / `：490` / `#L10-L20` → (start, end)；第三段冒号是列号，忽略。"""
    if not spec:
        return None
    nums = re.findall(r"[0-9]+", spec)
    if not nums:
        return None
    start = int(nums[0])
    end = start
    if re.search(r"[-~]", spec) and len(nums) > 1:
        end = int(nums[1])
    return (min(start, end), max(start, end))


def tidy(token):
    """尾巴上的散文标点不算件名的一部分：句读与孤右括号剥掉，通配号本就落在黑名单里。"""
    token = token.rstrip(".,;:")
    if token.endswith(")") and "(" not in token:
        token = token[:-1].rstrip()
    return token


def line_counts(data):
    """现读字节 → 三种换行口径的行数。text = CRLF/LF/CR 全展开（最大口径）。"""
    def count(parts, drop_trailing_empty=True):
        if drop_trailing_empty and parts and parts[-1] == b"":
            parts = parts[:-1]
        return len(parts)

    text = count(_LINE_BREAK.split(data))
    lf = count(re.split(rb"\n", data))
    crlf = data.count(CRLF_B)
    return {"text": text, "lf": lf, "crlf": crlf, "mixed": text != lf}


def collect_refs(text):
    """扫一遍派工词，切成引用清单（保序、去重前不判档）。"""
    refs = []
    external_spans = []
    for pattern in EXTERNAL_RES:
        for hit in pattern.finditer(text):
            if any(lo <= hit.start() < hi for lo, hi in external_spans):
                continue
            token = tidy(hit.group(0))
            if not looks_like_path(token):
                continue
            body, spec = split_trailing_spec(token)
            external_spans.append((hit.start(), hit.start() + len(token)))
            refs.append({
                "kind": "external", "raw": token, "rel": body, "spec": spec,
                "start": hit.start(), "src_line": text.count(LF, 0, hit.start()) + 1,
            })
    for hit in REL_RE.finditer(text):
        if any(lo <= hit.start() < hi for lo, hi in external_spans):
            continue
        path = tidy(hit.group("path"))
        if not path:
            continue
        spec = hit.group("spec")
        refs.append({
            "kind": "dir" if path.endswith("/") else "repo",
            "raw": path + (spec or ""), "rel": path, "spec": spec,
            "placeholder": bool(re.match(r"[:：#＃]?[<>*?{]", text[hit.end():hit.end() + 1])),
            "start": hit.start(), "src_line": text.count(LF, 0, hit.start()) + 1,
        })
    return sorted(refs, key=lambda r: (r["start"], r["raw"]))


def message_names_token(message, token):
    """提交文本里真出现过这枚号（按号边界），不是 `--grep=R47` 顺手蒙中 R478。"""
    return token in NUMBER_RE.findall(message)


def extract_numbers(text):
    """派工词里出现的每一枚单号（去重保序）。"""
    found = []
    for match in NUMBER_RE.finditer(text):
        if match.group(0) not in found:
            found.append(match.group(0))
    return found


# ---------------------------------------------------------------------------
# 尺子本体
# ---------------------------------------------------------------------------

class Ruler:
    """对着一棵工作树读账。同一枚 Ruler 复用 git 读数，不落盘、不缓存到盘上。"""

    def __init__(self, repo=REPO):
        self.repo = Path(repo).resolve()
        self._tracked = None
        self._commits = {}
        self._paper = None
        self._lines = {}

    # -- 只读读口 ---------------------------------------------------------
    def git(self, *args):
        if args[0] not in ALLOWED_GIT:
            raise SourceError("越界子命令：" + " ".join(args))
        run = subprocess.run(("git", "-C", str(self.repo)) + tuple(args), capture_output=True)
        if run.returncode != 0:
            raise SourceError("git {0} rc={1} {2}".format(
                args[0], run.returncode, run.stderr.decode("utf-8", "replace").strip()))
        return run.stdout

    def head(self):
        return self.git("log", "-1", "--format=%H").decode("ascii", "replace").strip()

    def tracked(self):
        if self._tracked is None:
            raw = self.git("ls-files", "-z")
            self._tracked = {one.decode("utf-8", "replace") for one in raw.split(NUL_B) if one}
        return self._tracked

    def paper_index(self):
        """docs/** 里每枚单号被哪些账面提到（在册 + 未忽略的工作区件，同 rg 口径）。"""
        if self._paper is None:
            raw = self.git("ls-files", "-z", "-c", "-o", "--exclude-standard", "docs")
            index = {}
            for one in raw.split(NUL_B):
                if not one:
                    continue
                rel = one.decode("utf-8", "replace")
                try:
                    data = (self.repo / rel).read_bytes()
                except OSError:
                    continue
                for token in set(m.group(0).decode("ascii") for m in NUMBER_RE_B.finditer(data)):
                    index.setdefault(token, []).append(rel)
            self._paper = index
        return self._paper

    def commit_hits(self, token):
        """现取 `git log --all -F --grep=<号>`，再按号边界复核（防 R47 冒充 R478）。"""
        if token not in self._commits:
            out = self.git("log", "--all", "-F", "--grep=" + token, "--format=%x01%H%n%B")
            hits = []
            for record in out.decode("utf-8", "replace").split(SOH):
                if not record.strip():
                    continue
                sha, _, body = record.partition(LF)
                if message_names_token(body, token):
                    hits.append((sha[:7], (body.splitlines() or [""])[0]))
            self._commits[token] = sorted(hits, reverse=True)
        return self._commits[token]

    def read(self, rel):
        try:
            return (self.repo / rel).read_bytes()
        except OSError:
            return None

    def count_lines(self, rel):
        if rel not in self._lines:
            data = self.read(rel)
            self._lines[rel] = None if data is None else line_counts(data)
        return self._lines[rel]

    def inside_repo(self, token):
        """绝对路径若落在本树内，归一成 repo-relative；否则回 None（只报不判死）。"""
        expanded = os.path.expandvars(os.path.expanduser(token))
        norm = os.path.normpath(expanded)
        root = os.path.normpath(str(self.repo))
        if os.path.normcase(norm) == os.path.normcase(root):
            return ""
        head = os.path.normcase(root) + os.sep
        if os.path.normcase(norm).startswith(head):
            return norm[len(root) + 1:].replace(os.sep, "/")
        return None

    # -- 三档判定 ---------------------------------------------------------
    def name_status(self, ref):
        rel = os.path.normpath(ref["rel"]).replace(os.sep, "/") if ref["rel"] else ""
        if rel in ("", "."):
            return TREE_SELF, "指向工作树自身"
        tracked = self.tracked()
        on_disk = (self.repo / rel).exists()
        if ref["kind"] == "dir" or (on_disk and (self.repo / rel).is_dir()):
            under = sum(1 for one in tracked if one.startswith(rel.rstrip("/") + "/"))
            if on_disk:
                return DIR_OK, "目录在位，在册件 {0} 枚".format(under)
            return DIR_MISSING, "目录不在位，在册件 {0} 枚".format(under)
        if rel in tracked:
            return (OK, "") if on_disk else (OFFDISK, "库里在册，这棵树没 checkout")
        if on_disk:
            return UNTRACKED, "盘上有，库里没（#82 那一族）"
        if any(one.startswith(rel.rstrip("/") + "/") for one in tracked):
            return DIR_OK, "按目录认，在册件 {0} 枚".format(
                sum(1 for one in tracked if one.startswith(rel.rstrip("/") + "/")))
        return MISSING, "盘上无 · 库里无"

    def line_status(self, ref):
        rng = parse_spec(ref["spec"])
        if rng is None:
            return None
        rel = os.path.normpath(ref["rel"]).replace(os.sep, "/") if ref["rel"] else ""
        counts = self.count_lines(rel)
        if counts is None:
            return (UNVERIFIABLE, rng, None, "件本身读不到（见 A 档），行号无法核")
        base = "现读行数 {0}".format(counts["text"])
        if counts["mixed"]:
            base += " MIXED_EOL（LF 口径 {0}）".format(counts["lf"])
        if rng[0] < 1:
            return (OUT_OF_RANGE, rng, counts, "行号 {0} 不是正整数 · {1}".format(rng[0], base))
        if rng[1] > counts["text"]:
            return (OUT_OF_RANGE, rng, counts, "行号 {0} 超出 · {1}".format(rng[1], base))
        span = "{0}-{1}".format(*rng) if rng[0] != rng[1] else str(rng[0])
        return (IN_RANGE, rng, counts, "行号 {0} · {1}".format(span, base))

    def ticket_status(self, token):
        commits = self.commit_hits(token)
        paper = self.paper_index().get(token, [])
        if commits:
            return HAS_COMMIT, commits, paper
        if paper:
            return PAPER_ONLY, commits, paper
        return NEVER_FILED, commits, paper

    # -- 总账 -------------------------------------------------------------
    def check(self, text, label="<text>", strict_external=False):
        rows_a, rows_b = [], []
        index_a, index_b = {}, {}
        for ref in collect_refs(text):
            key = (ref["kind"], ref["raw"])
            if key in index_a:
                index_a[key]["count"] += 1
                if key in index_b:
                    index_b[key]["count"] += 1
                continue
            note = ""
            if ref["kind"] == "external":
                inner = self.inside_repo(ref["rel"])
                if inner is None:
                    expanded = os.path.expandvars(os.path.expanduser(ref["raw"]))
                    verdict = "EXISTS" if os.path.lexists(expanded) else "ABSENT"
                    status = NOT_IN_REPO
                    note = "库外路径 {0}".format(verdict)
                    if strict_external and verdict == "ABSENT":
                        status = MISSING
                        note += "（--strict-external 判死）"
                    row = {"status": status, "raw": ref["raw"], "spec": ref["spec"],
                           "line": ref["src_line"], "count": 1, "note": note}
                    rows_a.append(row)
                    index_a[key] = row
                    continue
                ref = dict(ref, kind="dir" if inner.endswith("/") or inner == "" else "repo",
                           rel=inner, via_abs=True)
                note = "绝对路径归一 → " + (inner or ".")
            status, why = self.name_status(ref)
            if ref.get("via_abs") and status == MISSING:
                why += " · 绝对路径归一后仍无，可能校的是别棵树"
            if ref.get("placeholder"):
                why += " · 引用尾部像占位符/通配（<…> 或 *），已按前缀核"
            row = {"status": status, "raw": ref["raw"], "spec": ref["spec"],
                   "line": ref["src_line"], "count": 1,
                   "note": "; ".join(x for x in (note, why) if x)}
            rows_a.append(row)
            index_a[key] = row
            if ref["spec"]:
                checked = self.line_status(ref)
                if checked:
                    lstatus, rng, counts, ldetail = checked
                    brows = {"status": lstatus, "raw": ref["raw"], "line": ref["src_line"],
                             "range": rng, "detail": ldetail, "count": 1}
                    rows_b.append(brows)
                    index_b[key] = brows
        for row in rows_a + rows_b:
            row["red"] = row["status"] in RED_STATUSES
            row["warn"] = row["status"] in WARN_STATUSES

        numbers = []
        for token in extract_numbers(text):
            status, commits, paper = self.ticket_status(token)
            numbers.append({
                "token": token, "status": status, "commits": len(commits),
                "docs": len(paper), "first": commits[0][0] if commits else "",
                "red": status in RED_STATUSES, "warn": status in WARN_STATUSES,
            })
        reds = sum(1 for row in rows_a + rows_b if row["red"]) + sum(1 for n in numbers if n["red"])
        warns = (sum(1 for row in rows_a + rows_b if row["warn"])
                 + sum(1 for n in numbers if n["warn"]))
        return {
            "label": label, "repo": self.repo.as_posix(), "head": self.head(),
            "chars": len(text), "names": rows_a, "lines": rows_b, "numbers": numbers,
            "red": reds, "warn": warns, "exit_code": 1 if reds else 0,
        }


# ---------------------------------------------------------------------------
# 出账（同一棵树上跑两次逐字节相同：无时间戳、路径正斜杠、逐档排序）
# ---------------------------------------------------------------------------

def mark(row):
    if row.get("red"):
        return "!!"
    if row.get("warn"):
        return " ~"
    return "  "


def place(row):
    """这枚引用落在派工词的第几行；同一枚重复出现时附上枚数。"""
    tail = " ×{0}".format(row["count"]) if row.get("count", 1) > 1 else ""
    return "L{0}{1}".format(row["line"], tail)


def render(report):
    out = []
    out.append("dispatch-preflight · 工作树={0} · HEAD={1}".format(report["repo"], report["head"][:7]))
    out.append("输入={0} · 字符={1} · 件名引用={2} · 行号引用={3} · 单号引用={4}".format(
        report["label"], report["chars"], len(report["names"]), len(report["lines"]),
        len(report["numbers"])))
    out.append("")
    out.append("[A] 件名（磁盘 + git ls-files 双层核验）")
    if not report["names"]:
        out.append("  （文本里没有 repo-relative 或库外路径引用）")
    for row in sorted(report["names"], key=lambda r: (not r["red"], not r["warn"], r["status"], r["raw"])):
        out.append("  {0} {1:<22} {2:<9} {3}{4}".format(
            mark(row), row["status"], place(row), row["raw"],
            "  · " + row["note"] if row["note"] else ""))
    out.append("")
    out.append("[B] 行号（现读磁盘行数，尺内不存行数常量）")
    if not report["lines"]:
        out.append("  （文本里没有 `件名:行号` 引用）")
    for row in sorted(report["lines"], key=lambda r: (not r["red"], r["status"], r["raw"])):
        out.append("  {0} {1:<22} {2:<9} {3}  · {4}".format(
            mark(row), row["status"], place(row), row["raw"], row["detail"]))
    out.append("")
    out.append("[C] 号账（git log --all -F --grep= 与 docs/** 提及，两路证据分三档）")
    if not report["numbers"]:
        out.append("  （文本里没有单号引用）")
    for row in sorted(report["numbers"], key=lambda r: (not r["red"], not r["warn"], r["token"])):
        out.append("  {0} {1:<22} {2:<8} commits={3} docs={4}{5}".format(
            mark(row), row["status"], row["token"], row["commits"], row["docs"],
            "  · 首笔 " + row["first"] if row["first"] else ""))
    out.append("")
    tally = ["A 件名红 {0}".format(sum(1 for r in report["names"] if r["red"])),
             "B 行号红 {0}".format(sum(1 for r in report["lines"] if r["red"])),
             "C 号账红 {0}".format(sum(1 for r in report["numbers"] if r["red"]))]
    out.append("RESULT={0} 红 {1} 枚 · 警 {2} 枚（{3}）".format(
        "FAIL" if report["red"] else "CLEAN", report["red"], report["warn"], " / ".join(tally)))
    return LF.join(out) + LF


def load_input(args):
    if args.text is not None:
        return args.text, "--text"
    if args.source and args.source != "-":
        path = Path(args.source)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise SourceError("派工词读不出来：{0}（{1}）".format(args.source, exc))
        return data.decode("utf-8-sig", "replace"), args.source
    data = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else b""
    return data.decode("utf-8-sig", "replace"), "<stdin>"


def main(argv=None):
    parser = argparse.ArgumentParser(description="派工词落笔前的机器校尺（只读）")
    parser.add_argument("source", nargs="?", help="派工词文件；- 或省略则读 stdin")
    parser.add_argument("--text", help="直接给一段派工词文本")
    parser.add_argument("--repo", default=str(REPO), help="对哪棵工作树校验（默认本脚本所在树）")
    parser.add_argument("--json", action="store_true", help="出机器可读的账（stdout 换 JSON）")
    parser.add_argument("--strict-external", action="store_true",
                        help="库外路径读不到时也判死（默认只报不判死）")
    args = parser.parse_args(argv)
    try:
        text, label = load_input(args)
        if not text.strip():
            sys.stderr.write("空输入：没有可校的派工词。\n")
            return 2
        report = Ruler(args.repo).check(text, label=label, strict_external=args.strict_external)
    except SourceError as exc:
        sys.stderr.write("环境/出处错（不是账错）：{0}\n".format(exc))
        return 2
    if args.json:
        sys.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=1, default=str) + LF)
    else:
        sys.stdout.write(render(report))
    return report["exit_code"]


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline=LF)
    sys.exit(main())
