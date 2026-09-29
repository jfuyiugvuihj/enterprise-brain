#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R491 · 派工词落笔前的机器校尺（全程只读）：件名 / 行号 / 号账。
R498 · 件名加「库内被 ignore」第四档；号账把「提及」与「并树」分家。

病根（09-29 一天四犯，事故 #82/#85/#90/#91）：派工词里写进不存在的件名、不存在的
venv 路径、从没立过的单号，下一班照着跑就白烧一轮。这台尺子把「落笔前先机器校一遍」
从自觉变成能失败的牙。

档位检查：
  A 件名  —— 文本里所有 repo-relative 路径引用逐枚对「磁盘 + git ls-files」双层核验，
             MISSING（两样都没）与 UNTRACKED_BUT_ON_DISK（盘上有、库里没）分开报，
             TRACKED_BUT_OFF_DISK（库里在、这棵树没 checkout）再单列一档；
             绝对路径 / `%TEMP%` / 反斜杠路径立 NOT_IN_REPO 一档，只报不判死（附 EXISTS/ABSENT）。
             R498：盘上有 · 库里没 · 但被 .gitignore 收着的运行期产物（`.venv/**`、
             `__pycache__/**`、`static/charts/**`）单列 IGNORED_IN_REPO，附 `git check-ignore -v`
             的出处；真假账两档一格没宽——盘上无库里无仍 MISSING 判红，盘上有库里没且没被
             ignore 仍 UNTRACKED_BUT_ON_DISK 判红。
  B 行号  —— 每枚 `path:NNN` 用**现读磁盘字节**的行数判 IN_RANGE / OUT_OF_RANGE；
             行数以「三种换行（CRLF/LF/CR）全展开」为口径（最大那一档，对任何编辑器口径都不冤），
             换行不纯的件附注 MIXED_EOL。脚本内不存任何行数常量。
  C 号账  —— 每枚 `R\\d{2,3}` 现取 `git log --all -F --grep=<号> --name-only`（逐枚按号边界
             复核，防 R26 蒙中 R260–R269）与 docs/** 提及两路证据，分七档，不许塌档：
             HAS_COMMIT / LANDING_OFF_TRUNK / LANDING_CONFLICT / SUBNUMBER_LANDED /
             MENTION_ONLY / PAPER_ONLY / NEVER_FILED。R498 起 HAS_COMMIT 只发给**真的动了本单的货**
             的提交（首行是本号在本树祖先链上的落地形状 + 实改非空且仍在册 + 与账面写域有交集）；
             只在正文里「另立 RNNN」一律读 MENTION_ONLY，声称并树却躺在别的 ref 上读 LANDING_OFF_TRUNK，
             首行与实改对不上读 LANDING_CONFLICT，父号名下零并树而货在 R26a/R26b 一类子号名下读
             SUBNUMBER_LANDED 并点名子号，绝不自动并号。

纪律：只读。子进程白名单只有 `git log`、`git ls-files`、`git check-ignore`（三枚都是查询），
零网络、零写盘、不起服务、不碰模型；写动词（commit/checkout/restore/add/clean/reset/gc/apply/
worktree 等）在 `Ruler.git()` 那道闸当场拒，另有钉逐枚咬；非 sha 形状的 rev 也出不了这道闸。
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
CR = chr(13)
TAB = chr(9)
#: git log 记录形状：SOH 起一条、STX 分字段、ETX 结束正文（其后即 --name-only 的文件清单）。
STX = chr(2)
ETX = chr(3)

#: 子进程白名单：除这三枚 git 查询之外，本件不许起任何进程。
ALLOWED_GIT = ("check-ignore", "log", "ls-files")

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
IGNORED = "IGNORED_IN_REPO"
IN_RANGE = "IN_RANGE"
OUT_OF_RANGE = "OUT_OF_RANGE"
UNVERIFIABLE = "UNVERIFIABLE"
HAS_COMMIT = "HAS_COMMIT"
LANDING_OFF_TRUNK = "LANDING_OFF_TRUNK"
LANDING_CONFLICT = "LANDING_CONFLICT"
SUBNUMBER_LANDED = "SUBNUMBER_LANDED"
MENTION_ONLY = "MENTION_ONLY"
PAPER_ONLY = "PAPER_ONLY"
NEVER_FILED = "NEVER_FILED"

#: 红档（判死）与警档（只报）。
RED_STATUSES = (MISSING, DIR_MISSING, UNTRACKED, OFFDISK, OUT_OF_RANGE, NEVER_FILED)
WARN_STATUSES = (NOT_IN_REPO, IGNORED, LANDING_OFF_TRUNK, LANDING_CONFLICT, MENTION_ONLY,
                 SUBNUMBER_LANDED, PAPER_ONLY, UNVERIFIABLE)

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
# 落地形状：把「提及」与「并树」分家（R498）
# ---------------------------------------------------------------------------

#: 本仓总控代提交的并树首行模板：`并树 RNNN[限定语]（施工 名字/id，树 be-rNNN@sha）：…`
#: 限定语那一格吃 R471 丙案 这种写法；号边界由 (?![0-9A-Za-z]) 钉住，不吃 R47 蒙 R478。
LANDING_HEAD_RE = re.compile(
    r"^并树[ \t]*(?P<tok>R[0-9]{2,3}[a-z]?)(?![0-9A-Za-z])[^\n（(]{0,24}（")
#: 拆单之前的旧约定首行：`feat(R26a): …`／`R260b（总控补口…）：…`／`R478 并树推后的行号账…`
BUILD_HEAD_RE = re.compile(
    r"^(?:[a-z]+[ \t]*\([ \t]*(?P<typed>R[0-9]{2,3}[a-z]?)[ \t]*\)|"
    r"(?P<bare>R[0-9]{2,3}[a-z]?)(?![0-9A-Za-z]))[ \t]*(?=[（(:：]|\s|$)")
#: 分支并树（merge）：`Merge codex/be-leg2: R26a …`——文件清单走第一父。
MERGE_HEAD_RE = re.compile(r"^Merge\b")
WORKTREE_RE = re.compile(r"be-[A-Za-z0-9_][A-Za-z0-9_.\-]*")
SHA7_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{7,40}(?![0-9a-f])")
SHA_REV_RE = re.compile(r"^[0-9a-f]{7,40}$")
SUB_TAIL_RE = re.compile(r"^[a-z]$")

#: 一枚声称落地的提交的四种读数。
LANDED = "landed"
EMPTY = "empty"
OFFLEDGER = "off-ledger"
UNMATCHED = "unmatched"

SHAPE_LANDING = "并树模板"
SHAPE_BUILD = "施工首行"
SHAPE_MERGE = "分支并树"

#: git log 一条命令同时带回 sha / 父 / 首行 / 正文 / 该提交的文件名清单。
RECORD_FORMAT = "--format=%x01%H%x02%P%x02%s%x02%B%x03"

#: 认「正文点过这枚件的名」所需的最短前缀；短于此就不足以认定写域。
MIN_DECL_PREFIX = 10


def parse_records(raw):
    """`git log --format=<SOH/STX/ETX> --name-only` 的字节 → 记录清单（纯函数，可喂影子样本）。"""
    records = []
    for chunk in raw.decode("utf-8", "replace").split(SOH):
        if not chunk.strip():
            continue
        head, _, tail = chunk.partition(ETX)
        fields = head.split(STX)
        if len(fields) != 4:
            continue
        sha, parents, subject, message = [one.strip(CR + LF) for one in fields]
        files = [one for one in tail.strip(CR + LF).split(LF) if one.strip()]
        records.append({"sha": sha, "parents": parents.split(), "subject": subject,
                        "message": message, "files": files})
    return records


def text_of(rec):
    return rec["subject"] + LF + rec["message"]


def subject_shape(subject, token):
    """首行相对这枚号是什么形状；None = 这枚提交只是把号写在文字里，不是它的落地。"""
    match = LANDING_HEAD_RE.match(subject)
    if match:
        return SHAPE_LANDING if match.group("tok") == token else None
    match = BUILD_HEAD_RE.match(subject)
    if match:
        tok = match.group("typed") or match.group("bare")
        return SHAPE_BUILD if tok == token else None
    if MERGE_HEAD_RE.match(subject) and token in NUMBER_RE.findall(subject):
        return SHAPE_MERGE
    return None


def missing_markers(subject):
    """并树模板该带的三枚标记，缺哪枚报哪枚——只点名，不改判（判权在实改那一腿）。"""
    missing = []
    if "施工" not in subject:
        missing.append("施工")
    if not WORKTREE_RE.search(subject):
        missing.append("be-rNNN")
    if not SHA7_RE.search(subject):
        missing.append("sha")
    return missing


def names_the_ticket(rel, token):
    """这枚文件按单号命名了吗（本仓产物一律挂号：`tests/test_r483_…`／`scripts/r483_…`／
    `docs/testing/r496-…`）。号后必须收在边界上，防 r483 蒙中 r4830。
    """
    digits = token[1:].lower()
    tail = digits[-1] if digits[-1].isalpha() else ""
    if tail:
        digits = digits[:-1]
    return re.search(r"(^|[^0-9a-z])r" + digits + re.escape(tail) + r"(?![0-9a-z])", rel) is not None


def declared_refs(message):
    """提交信息里点名的 repo-relative 件名；一枚都没有时，写域交集这一腿无法核，必须点名。"""
    return [hit.group("path") for hit in REL_RE.finditer(message) if hit.group("path")]


def declares_path(message, rel):
    """这枚在改的文件被提交信息点过名没有（写域交集那一腿的判据）。

    三种形状都算点名：
      ① 整条路径，或 ≥MIN_DECL_PREFIX 且带 `/` 的一段前缀——吃 `scripts/x.py(518 行)`
         这种尾巴挂字的写法；
      ② 正文自己写出来的那析路径是这枚件的前缀且 ≥MIN_DECL_PREFIX——吃 `tests/test_r491_*`
         这类 glob／省略写法（`*` 是停止符，抓到的就是 `tests/test_r491_` 这段前缀）；
      ③ 任一祖先目录加 glob／通配（`app/**`、`static/*`）——目录级写法本身就是写域声明。
    """
    parts = rel.split("/")
    for index in range(len(parts), 0, -1):
        head = "/".join(parts[:index])
        if len(head) >= MIN_DECL_PREFIX and "/" in head and head in message:
            return True
    for ref in declared_refs(message):
        if len(ref) >= MIN_DECL_PREFIX and rel.startswith(ref):
            return True
    for index in range(len(parts) - 1, 0, -1):
        head = "/".join(parts[:index])
        if message.startswith(head):
            continue
        for tail in ("/**", "/*"):
            if head + tail in message:
                return True
    return False


# ---------------------------------------------------------------------------
# 尺子本体
# ---------------------------------------------------------------------------

class Ruler:
    """对着一棵工作树读账。同一枚 Ruler 复用 git 读数，不落盘、不缓存到盘上。"""

    def __init__(self, repo=REPO):
        self.repo = Path(repo).resolve()
        self._tracked = None
        self._head = None
        self._records = {}
        self._files = {}
        self._reach = {}
        self._paper = None
        self._lines = {}

    # -- 只读读口 ---------------------------------------------------------
    def git(self, *args, stdin=None):
        if args[0] not in ALLOWED_GIT:
            raise SourceError("越界子命令：" + " ".join(args))
        #: `core.quotePath=false`：否则非 ASCII 件名被转义成 `"data/\346\212\245…"`，在册比对必漏。
        run = subprocess.run(("git", "-c", "core.quotePath=false", "-C", str(self.repo)) + tuple(args),
                             capture_output=True, input=stdin)
        #: `check-ignore` 用退出码说话：1 = 没有一条 ignore 规则命中，这是答案，不是故障。
        if run.returncode != 0 and not (args[0] == "check-ignore" and run.returncode == 1):
            raise SourceError("git {0} rc={1} {2}".format(
                args[0], run.returncode, run.stderr.decode("utf-8", "replace").strip()))
        return run.stdout

    def head(self):
        if self._head is None:
            self._head = self.git("log", "-1", "--format=%H").decode("ascii", "replace").strip()
        return self._head

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

    def records(self, token):
        """现取一枚号名下的提交记录（sha／父／首行／正文／该提交 --name-only 的文件清单）。

        `git log --all -F --grep=<号>` 是**子串**命中，R26 会一并捞回 R260–R269 那一族；
        所以每条记录还要过 `message_names_token` 的号边界复核，落档只认复核过的。
        """
        if token not in self._records:
            raw = self.git("log", "--all", "-F", "--grep=" + token,
                           RECORD_FORMAT, "--name-only")
            self._records[token] = parse_records(raw)
        return self._records[token]

    def first_parent_files(self, rev):
        """merge 提交的 --name-only 是空的：相对第一父补一次（仍走 git log，仍只读）。"""
        if not SHA_REV_RE.match(rev):
            raise SourceError("不是 sha 形状的落地凭据，不发给 git：" + rev)
        if rev not in self._files:
            records = parse_records(self.git("log", "-1", RECORD_FORMAT,
                                             "--name-only", "--first-parent", rev))
            self._files[rev] = records[0]["files"] if records else []
        return self._files[rev]

    def on_trunk(self, rev):
        """这枚提交在不在本树 HEAD 的祖先链上——只问 `git log HEAD..<rev>` 空不空，不外扩白名单。

        「并树 RNNN（…）」的首行加实改在册，只证明有一枚提交**声称**并了树；它若躺在
        别的 ref 上（本仓 09-29 的 R496 就是这个形状），这棵树的读路径里没有它的货。
        """
        if not SHA_REV_RE.match(rev):
            raise SourceError("不是 sha 形状的落地凭据，不发给 git：" + rev)
        if rev not in self._reach:
            try:
                out = self.git("log", "-1", "--format=%H", "HEAD.." + rev)
            except SourceError:
                self._reach[rev] = False
                return False
            self._reach[rev] = not out.strip()
        return self._reach[rev]

    def changed_files(self, rec):
        if rec["files"]:
            return rec["files"]
        if len(rec["parents"]) > 1:
            return self.first_parent_files(rec["sha"])
        return rec["files"]

    def goods(self, rec, shape, token):
        """首行声称落地之后还有两枚可失败的牙：

        ① 该提交相对第一父**实改非空**且这些文件今天仍在 `git ls-files` 在册
           （空提交、或并完又被撤掉的，都不算把货并了树）；
        ② 实改清单与该提交**自己正文点名的写域**有交集——整条路径、≥10 字前缀、目录 glob
           三种写法都算点名；或者实改里至少一枚文件**按本单号命名**（本仓产物一律挂号）。
           正文一枚件名都没点名时交集这一腿无法核，读数里明写「无法核」，不许静默放行。
        """
        files = self.changed_files(rec)
        if not files:
            return EMPTY, "首行是 {0} 形状而实改清单为空（空提交不能算并树）".format(shape), []
        in_ledger = [one for one in files if one in self.tracked()]
        if not in_ledger:
            return OFFLEDGER, "实改 {0} 枚今天一枚都不在 git ls-files 在册".format(len(files)), []
        text = text_of(rec)
        refs = declared_refs(text)
        hits = [one for one in files if declares_path(text, one)]
        named = [one for one in files if names_the_ticket(one, token)]
        tally = "实改 {0} 枚 · 在册 {1} 枚".format(len(files), len(in_ledger))
        if hits:
            return LANDED, tally + " · 正文点名 {0} 枚".format(len(hits)), in_ledger
        if named:
            return LANDED, tally + " · 按号命名 {0} 枚".format(len(named)), in_ledger
        if not refs:
            return LANDED, tally + "（正文未点名件名，交集这一腿无法核，已点名）", in_ledger
        return UNMATCHED, ("首行声称并树、实改 {0} 枚也在册，但与正文点名的 {1} 枚写域零交集，"
                           "也没有一枚按号命名").format(len(in_ledger), len(refs)), in_ledger

    def landing_hits(self, token):
        """四堆：在册并树凭据 / 声称并树却不在祖先链 / 号边界提及 / 声称落地被牙拒。"""
        landed, offtrunk, mentioned, refused = [], [], [], []
        for rec in self.records(token):
            if not message_names_token(text_of(rec), token):
                continue
            shape = subject_shape(rec["subject"], token)
            row = {"sha": rec["sha"][:7], "subject": rec["subject"], "shape": shape or "",
                   "markers": missing_markers(rec["subject"]) if shape else [],
                   "files": 0, "why": "", "kind": ""}
            mentioned.append(row)
            if not shape:
                continue
            kind, why, in_ledger = self.goods(rec, shape, token)
            row["why"] = why
            row["files"] = len(in_ledger)
            row["kind"] = kind
            if kind != LANDED:
                refused.append(row)
            elif not self.on_trunk(rec["sha"]):
                row["why"] = why + " · 但不在本树 HEAD 祖先链上（别的 ref）"
                row["kind"] = "off-trunk"
                offtrunk.append(row)
            else:
                landed.append(row)
        return landed, offtrunk, mentioned, refused

    def sibling_landings(self, token):
        """父号名下零并树时，看同族子号（R26a/R26b 一类）名下的并树凭据——只报，绝不并号。"""
        found = {}
        for rec in self.records(token):
            for tok in NUMBER_RE.findall(rec["subject"]):
                tail = tok[len(token):] if tok.startswith(token) else ""
                if not tail or not SUB_TAIL_RE.match(tail):
                    continue
                shape = subject_shape(rec["subject"], tok)
                if not shape:
                    continue
                kind, why, in_ledger = self.goods(rec, shape, tok)
                if kind == LANDED and self.on_trunk(rec["sha"]):
                    found.setdefault(tok, []).append((rec["sha"][:7], len(in_ledger)))
        return sorted((one, [sha for sha, _ in rows]) for one, rows in found.items())

    def ignore_evidence(self, rel):
        """`git check-ignore -v` 的出处附注（`.gitignore:2:__pycache__/` 这一串）。

        读不到就回 None：宁可不降噪，也不把「#82 那一族假账」放行——降噪必须有凭据。
        """
        try:
            out = self.git("check-ignore", "-v", "--stdin",
                           stdin=(rel + LF).encode("utf-8")).decode("utf-8", "replace")
        except SourceError:
            return None
        line = (out.splitlines() or [""])[0]
        source = line.split(TAB)[0].strip()
        return source or None

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
            evidence = self.ignore_evidence(rel)
            if evidence:
                return IGNORED, "盘上有 · 库里没 · 被 ignore（{0}）⇒ 只报不判红".format(evidence)
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
        """把一枚号读成六档之一，并交出「用的是哪一层、哪个名字」的凭据。"""
        landed, offtrunk, mentioned, refused = self.landing_hits(token)
        conflict = [one for one in refused if one["kind"] == UNMATCHED]
        paper = self.paper_index().get(token, [])
        if landed:
            shapes = "+".join(sorted(set(one["shape"] for one in landed)))
            note = "并树凭据 {0} 枚（{1}）· {2}".format(len(landed), shapes, landed[0]["why"])
            if landed[0]["markers"]:
                note += " · 模板标记缺：" + ",".join(landed[0]["markers"])
            if offtrunk:
                note += " · 另 {0} 枚声称并树不在祖先链：{1}".format(
                    len(offtrunk), offtrunk[0]["sha"])
            if refused:
                note += " · 另 {0} 枚同形状被牙拒：{1}".format(len(refused), refused[0]["why"])
            return HAS_COMMIT, landed, mentioned, paper, note
        if offtrunk:
            note = ("{0} 枚提交的首行是本号的落地形状、货也不空，但没有一枚在本树 HEAD 的祖先链上"
                    "（{1}）⇒ 这棵树读不到它的货，不许当已并树".format(
                        len(offtrunk), "/".join(one["sha"] for one in offtrunk)))
            return LANDING_OFF_TRUNK, landed, mentioned, paper, note
        if conflict:
            note = ("{0} 枚提交首行声称本号并树、实改也在册，却与账面写域对不上（{1}）"
                    "⇒ 声称与账面冲突：既不许记已并树，也不许记没并树，须人工定性"
                    .format(len(conflict), "/".join(one["sha"] for one in conflict)))
            return LANDING_CONFLICT, landed, mentioned, paper, note
        siblings = self.sibling_landings(token)
        if siblings:
            names = "、".join("{0}={1}".format(tok, "/".join(shas)) for tok, shas in siblings)
            note = ("按父号 {0} 号边界取账：并树 0 · 提及 {1} · docs {2}；货在同族子号名下：{3}"
                    "（层 = git log 首行形状 + 实改在册）⇒ 不自动并号，账面记 {0} 结案必须点分子号"
                    .format(token, len(mentioned), len(paper), names))
            return SUBNUMBER_LANDED, landed, mentioned, paper, note
        if mentioned:
            note = ("提及 {0} 枚、并树 0 枚：首行无一条是本号的落地形状（最新提及 {1}）· docs {2} 枚"
                    .format(len(mentioned), mentioned[0]["sha"], len(paper)))
            if refused:
                note += " · 另 {0} 枚声称落地被牙拒：{1}".format(len(refused), refused[0]["why"])
            return MENTION_ONLY, landed, mentioned, paper, note
        if paper:
            note = "git log 号边界零命中 · docs 提及 {0} 枚".format(len(paper))
            return PAPER_ONLY, landed, mentioned, paper, note
        return NEVER_FILED, landed, mentioned, paper, "git log 号边界与 docs/** 两路皆零命中"

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
            status, landed, mentioned, paper, note = self.ticket_status(token)
            #: `landing_hits` 与 `ticket_status` 共用缓存，这里取 off-trunk 枚数不重跑 git。
            numbers.append({
                "token": token, "status": status, "commits": len(landed),
                "mentions": len(mentioned), "docs": len(paper),
                "first": landed[0]["sha"] if landed else (mentioned[0]["sha"] if mentioned else ""),
                "files": landed[0]["files"] if landed else 0,
                "off_trunk": status == LANDING_OFF_TRUNK,
                "shapes": "+".join(sorted(set(one["shape"] for one in landed))) if landed else "",
                "note": note,
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
    out.append("[A] 件名（磁盘 + git ls-files + git check-ignore 三层核验）")
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
    out.append("[C] 号账（并树 = 首行落地形状 + 实改在册 + 写域有交集；正文提及不算并树）")
    if not report["numbers"]:
        out.append("  （文本里没有单号引用）")
    for row in sorted(report["numbers"], key=lambda r: (not r["red"], not r["warn"],
                                                         r["status"], r["token"])):
        tag = "  · " + ("并树 " if row["commits"] else "提及 ") + row["first"] if row["first"] else ""
        out.append("  {0} {1:<22} {2:<8} commits={3} mentions={4} docs={5}{6}  · {7}".format(
            mark(row), row["status"], row["token"], row["commits"], row["mentions"],
            row["docs"], tag, row["note"]))
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
