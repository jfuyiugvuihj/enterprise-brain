#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R262 · 计划书台账归真：把「哪些单真落地了」做成机器可校验的账。

R640 起这把尺出六档，且新档只许派生——写死单号名单会被自己的牙咬（见 C11/C13）：
- LANDED／PARTIAL／ZERO＝老三档，口径不变（产物在树＋欠账逐字点名／HEAD 祖先链上全史零产物）。
- CLOSED＝账面有结案裁定句（形状为「R<号> 结案（R<量具> …）」），且那枚量具的货真在仓内：
  结案笔在 HEAD 祖先链上、它带进主干的产物文件仍在盘上、且同笔带来一枚 docs/perf 或 docs/testing 取证纸。
- FOREIGN＝外来号：计划书表格里没有它的行、跟进单 §21 判据表没有它的行、主干归集零产物、
  台账也不许给它挂产物 ⇒ 「从没立过后端单」不是一种「零提交」，它该被单列而不是计入 ZERO 分子。
- NOTBUILT＝裁定不建：计划书把那行划了删除线，且跟进单 §21 里读得到「不建，沿用」那句裁定；
  两边只剩一边＝不可判定，当场红，不许悄悄掉回 ZERO 去凑分子。
- 理由句同样从出处派生：取证纸以 `G-R<号>-<序>` 认领某一格欠账时，那格的判语按纸面内容现取；
  纸上的结论与台账里写死的理由句打架 ⇒ 红（读的是纸的内容，不是提交标题）。

纪律长在代码里，不是长在回执里：
- 只读：只调 git 子命令与读文件，不写任何东西、不联网、不起服务、不碰模型、不跑测试。
- 逐字：判据原文一律运行时按锚点从出处文件逐字切段，脚本内不存一份转述；锚点不唯一就当场停。
- 稳定：同一 HEAD 连跑两次 stdout 逐字节相同（无时间戳、路径一律正斜杠、按号排序）。
- 反证：判 LANDED 而证据提交不在 HEAD 祖先链上 ⇒ 非零退出并点名那一号。
- 派生不靠仓外：`%TEMP%` 里的工件一律不作派生源，只认仓内路径与祖先链上的提交（换机器还在）。

用法：
    python scripts/audit_plan_ticket_ledger.py
    python scripts/audit_plan_ticket_ledger.py --timing     # 耗时只打 stderr
    python scripts/audit_plan_ticket_ledger.py --fault R46=LANDED@deadbeef
    python scripts/audit_plan_ticket_ledger.py --fault R143=CLOSED@deadbeef   # 反证：喂假 sha

退出码：0 自检全过 / 1 自检咬到 / 2 环境或出处错（git 读不到、锚点漂了、判据引用失真）。
"""

import argparse
import io
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLAN = "docs/handoff/2026-09-17-perf-architecture-plan.md"
FOLLOWUP = "docs/handoff/2026-09-15-backend-followup-requests.md"

CODE_DIRS = ("app/", "frontend/", "scripts/", "tests/", "migrations/", "deploy/", "static/")
CODE_SUFFIX = (".py", ".js", ".vue", ".css", ".html", ".sql", ".sh",
               ".toml", ".yml", ".yaml", ".json", ".example")
DOC_PREFIX = ("docs/", "README.md")

# 六档。DERIVED 是「本格判定（或理由句）由事实派生」的哨兵；新档写死＝C11 咬。
VERDICTS = ("LANDED", "PARTIAL", "CLOSED", "ZERO", "FOREIGN", "NOTBUILT")
DERIVED = "<派生>"
DERIVABLE_TIERS = ("CLOSED", "FOREIGN", "NOTBUILT")
CLEARED_TIERS = ("LANDED", "CLOSED", "FOREIGN", "NOTBUILT")   # 读法甲里不算「未清」的档
EVIDENCE_DIRS = ("docs/perf/", "docs/testing/")
CLAUSE_MARKS = "①②③④⑤⑥⑦⑧⑨"
PRIMARY_RE = re.compile(r"(?<![A-Za-z0-9])R(\d{1,3})([a-z]?)(?![0-9A-Za-z])")
CATCH_UP_RE = re.compile(r"catch up|追平|保活")
SECTION_21 = ("## 21. 性能与架构线正式立单", "### 21.1")

# 账面裁定句的形状（逐枚现读，脚本内不存单号名单）
CLOSURE_RE = re.compile(r"(?<![A-Za-z0-9])R(\d{1,3})\s*结案[（(]\s*(R\d{1,3})")
NOTBUILT_RE = re.compile(r"(?<![A-Za-z0-9])R(\d{1,3})[^R0-9]{0,6}不建[^R0-9]{0,6}沿用")
S21_ROW_RE = re.compile(r"^\|\s*\*\*R(\d{1,3})\*\*\s*\|")
MEASURED_MARKS = ("量到了", "FAIL", "PASS")
UNMEASURED_MARKS = ("量不到", "不可信", "未量", "没量")
GAP_KEY_RE = re.compile(r"G-(R\d{1,3})-(\d{1,2})")
BRACKET_RE = re.compile(r"[「]([^」]+)[」]")
NUMBER_RUN_RE = re.compile(r"([0-9]+(?:[／/,、][0-9]+)+)")
CELL_TICKET_RE = re.compile(r"^(?:\*\*)?(?:~~)?R(\d{1,3})(?![0-9A-Za-z])")
CELL_STRUCK_RE = re.compile(r"^~~R(\d{1,3})~~")
FAILING_HINT_RE = re.compile(r"failing|枚数")
# 只有标题行里写了 `G-<号>-<序>` 才算「认领」这一格；正文里的引用是转述，不许顶掉量具的判语
CLAIM_HEAD_RE = re.compile(r"^\s{0,3}#{1,6}\s")

class SourceError(Exception):
    pass


def classify(path):
    if path.startswith("docs/api/") or path == "migrations/manifest.json":
        return "契约"
    if path.startswith(DOC_PREFIX):
        return "文书"
    if path.startswith(CODE_DIRS) or path.endswith(CODE_SUFFIX):
        return "产品码"
    return "文书"


def product_files(paths, classes):
    return [path for path in paths if classify(path) in classes]


def primary_token(subject):
    match = PRIMARY_RE.search(subject)
    if not match:
        return None, ""
    return "R" + match.group(1), match.group(2) or ""


class Git:
    """只读 git 门面：所有事实都从这一层现取，缓存只为跑得快，不改变结果。"""

    def __init__(self, repo):
        self.repo = str(repo)
        self._cache = {}

    def _run(self, args):
        proc = subprocess.run(["git", "-C", self.repo] + list(args), capture_output=True)
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
        return proc.returncode, out, err

    def out(self, *args):
        rc, stdout, stderr = self._run(list(args))
        if rc != 0:
            first = stderr.strip().splitlines()[0] if stderr.strip() else str(rc)
            raise SourceError("git %s 读不到：%s" % (" ".join(args), first))
        return stdout

    def head(self):
        return self.out("rev-parse", "HEAD").strip()

    def worktree_state(self):
        lines = [l for l in self.out("status", "--porcelain", "-uall").splitlines() if l.strip()]
        return "clean" if not lines else "dirty:%d" % len(lines)

    def ancestors(self):
        if "revlist" not in self._cache:
            self._cache["revlist"] = set(self.out("rev-list", "HEAD").split())
        return self._cache["revlist"]

    def resolve(self, rev):
        """同一个引用串只问 git 一次：逐号解析在近千枚证据提交上是主要耗时（Windows 起子进程很贵）。"""
        key = ("resolve", rev)
        if key not in self._cache:
            rc, _, _ = self._run(["cat-file", "-e", rev + "^{commit}"])
            self._cache[key] = None if rc else self.out("rev-parse", rev + "^{commit}").strip()
        return self._cache[key]

    def is_ancestor(self, full_sha):
        return self._run(["merge-base", "--is-ancestor", full_sha, "HEAD"])[0] == 0
    def order(self):
        """rev-list 顺序（新→旧）：派生时要「同一枚账挑同一枚凭据」，不能靠字典序碰运气。"""
        if "order" not in self._cache:
            self._cache["order"] = self.out("rev-list", "HEAD").split()
        return self._cache["order"]

    def first_add(self, rel):
        """HEAD 祖先链上把某枚仓内路径带进仓库的那笔提交（现取，不抄账面 sha）。"""
        if ("add", rel) not in self._cache:
            raw = self.out("log", "--format=%H", "--diff-filter=A", "HEAD", "--", rel)
            found = [line.strip() for line in raw.splitlines() if line.strip()]
            self._cache[("add", rel)] = found[0] if found else None
        return self._cache[("add", rel)]
    def commits(self):
        if "commits" not in self._cache:
            raw = self.out("log", "--format=%H%x00%P%x00%s%x00%B%x01", "HEAD")
            table = {}
            for record in raw.split("\x01"):
                record = record.strip("\n")
                if not record:
                    continue
                sha, parents, subject, body = record.split("\x00")
                table[sha] = {"parents": parents.split(), "subject": subject, "body": body}
            self._cache["commits"] = table
        return self._cache["commits"]

    def message(self, full_sha):
        commit = self.commits().get(full_sha)
        if commit is not None:
            return commit["subject"] + "\n" + commit["body"]
        return self.out("show", "-s", "--format=%B", full_sha)

    def files(self, full_sha):
        """该提交相对第一父实改的文件清单（并树提交取它带进主干的净改动）。"""
        if full_sha in self._cache:
            return self._cache[full_sha]
        commit = self.commits().get(full_sha)
        if commit is None:
            parents = self.out("show", "-s", "--format=%P", full_sha).split()
        else:
            parents = commit["parents"]
        if parents:
            diff = self.out("diff-tree", "-r", "--numstat", "--no-commit-id", parents[0], full_sha)
        else:
            diff = self.out("show", "--numstat", "--format=", full_sha)
        paths = []
        for line in diff.splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                paths.append(parts[2])
        self._cache[full_sha] = paths
        return paths


class Quoter:
    """判据原文逐字切段器。

    锚点必须在指定窗口内恰命中一处，否则当场 SourceError：锚点漂了＝出处不可信，
    宁可不出货也不许把「转述」当「引用」（本项目栽过三次的地方）。
    """

    def __init__(self, repo):
        self.root = Path(repo)
        self._lines = {}

    def file_lines(self, rel):
        if rel not in self._lines:
            with open(self.root / rel, encoding="utf-8", newline="") as handle:
                text = handle.read()
            self._lines[rel] = [line.rstrip("\r") for line in text.split("\n")]
        return self._lines[rel]

    def window(self, rel, span):
        lines = self.file_lines(rel)
        starts = [i for i, line in enumerate(lines) if line.startswith(span[0])]
        ends = [i for i, line in enumerate(lines) if line.startswith(span[1])]
        if len(starts) != 1 or len(ends) != 1:
            raise SourceError("出处小节在 %s 里定位不唯一：%r（起点 %d 处／终点 %d 处）"
                              % (rel, span[0], len(starts), len(ends)))
        return starts[0], ends[0], lines

    def locate(self, spec):
        rel = spec["file"]
        anchor = spec["anchor"]
        if "span" in spec:
            low, high, lines = self.window(rel, spec["span"])
            hits = [i for i in range(low, high) if anchor in lines[i]]
            place = "小节内"
        else:
            lines = self.file_lines(rel)
            hits = [i for i, line in enumerate(lines) if anchor in line]
            place = "全文"
        if len(hits) != 1:
            raise SourceError("锚点在 %s（%s）命中 %d 处，要求恰 1 处：anchor=%r"
                              % (rel, place, len(hits), anchor))
        return lines, hits[0]

    @staticmethod
    def cell(line, index):
        parts = line.split("|")
        if len(parts) <= index or not parts[index].strip():
            raise SourceError("该行切不出第 %d 格：%s" % (index, line[:80]))
        return parts[index].strip()

    @staticmethod
    def clause(text, mark):
        pieces = re.split("([" + CLAUSE_MARKS + "])", text)
        for i in range(1, len(pieces), 2):
            if pieces[i] == mark:
                return (mark + pieces[i + 1]).strip().rstrip("；;").strip()
        raise SourceError("切段里找不到判据 %s：%s" % (mark, text[:80]))

    def quote(self, spec, tid):
        lines, index = self.locate(spec)
        line = lines[index]
        if "cell" in spec:
            text = self.cell(line, spec["cell"])
        else:
            text = line.strip()
        if "clause" in spec:
            text = self.clause(text, spec["clause"])
        if not text:
            raise SourceError("%s 的判据切段是空串" % tid)
        return {"key": "%s-%d" % (tid, spec.get("seq", 1)), "source": spec["label"],
                "file": spec["file"], "line": index + 1, "quote": text}


def first_cell(line):
    """表格行第一格（兼容 `> | R141 |` 这种引用块里的表）。"""
    text = line.strip()
    if text.startswith(">"):
        text = text[1:].strip()
    if not text.startswith("|"):
        return None
    parts = text.split("|")
    return parts[1].strip() if len(parts) > 1 else None


def short(sha):
    return (sha or "")[:7]


def safe(text):
    """表格格子里不许出现裸竖线：裁定句原文带 `|` 也得原样看得见，转义即可。"""
    return (text or "").replace("|", "\\|")


def polarity(text):
    """判语极性：量到了／判负／判绿＝MEASURED，量不到／不可信＝UNMEASURED，其余不表态。"""
    if any(mark in text for mark in UNMEASURED_MARKS):
        return "UNMEASURED"
    if any(mark in text for mark in MEASURED_MARKS):
        return "MEASURED"
    return None


def attribute(git, scope):
    """按「提交标题里第一枚单号」归集主干产物；只对 scope 里的号取文件清单（其余提交一枚 git 都不问）。

    scope ＝台账在册号 ∪ 账面结案句点名的量具号：量具号必须一起归集，
    否则「结案凭据」那一腿就没东西可查（在册号名下零枚、货色全在量具号名下，就是这样）。
    """
    owned = {}
    catch_up = {}
    for sha in git.order():
        subject = git.commits()[sha]["subject"]
        base, suffix = primary_token(subject)
        if base not in scope:
            continue
        products = product_files(git.files(sha), ("产品码", "契约"))
        if not products:
            continue
        bucket = catch_up if CATCH_UP_RE.search(subject) else owned
        bucket.setdefault(base, []).append((sha, tuple(sorted(products)), suffix))
    return owned, catch_up


class Deriver:
    """判定与理由句的派生层（R640）：结论从仓内事实现取，脚本内不存单号名单。

    只认四类派生源（判据 D1）：
      ① 祖先链上的提交——`merge-base --is-ancestor` 与 `rev-list` 现取，不抄账面 sha；
      ② 仓内产物路径仍在盘上——按工作树视图判存在；`%TEMP%` 里的工件不作数（换机器就没）；
      ③ 计划书表格行（含删除线形 `~~R39~~`）与跟进单 §21 判据表行；
      ④ 跟进单裁定句与 docs/perf／docs/testing 取证纸的内容——读纸的内容，不读提交标题。
    """

    def __init__(self, git, quoter, ids):
        self.git = git
        self.quoter = quoter
        self.root = quoter.root
        self.plan_lines = quoter.file_lines(PLAN)
        follow = quoter.file_lines(FOLLOWUP)
        self.follow_lines = follow
        self.plan_rows = self._table_tids(self.plan_lines)
        low, high, _ = quoter.window(FOLLOWUP, SECTION_21)
        self.s21_rows = {}
        for index in range(low, high):
            match = S21_ROW_RE.match(follow[index].strip())
            if match:
                self.s21_rows.setdefault("R" + match.group(1), []).append(index)
        self.closures = self._scan(follow, CLOSURE_RE, group=2)
        self.notbuilds_21 = self._scan(follow, NOTBUILT_RE, low=low, high=high)
        scope = set(ids) | {instrument for hits in self.closures.values()
                            for _, instrument, _ in hits if instrument}
        self.owned, self.catch_up = attribute(git, scope)
        self.papers, self.skipped_papers, self.quotings = self._paper_index()

    @staticmethod
    def _table_tids(lines):
        rows = {}
        for index, line in enumerate(lines):
            cell = first_cell(line)
            if not cell:
                continue
            match = CELL_TICKET_RE.match(cell)
            if not match:
                continue
            entry = rows.setdefault("R" + match.group(1), {"normal": [], "struck": []})
            entry["struck" if CELL_STRUCK_RE.match(cell) else "normal"].append(index)
        return rows

    @staticmethod
    def _scan(lines, regex, group=None, low=0, high=None):
        found = {}
        high = len(lines) if high is None else high
        for index in range(low, high):
            for match in regex.finditer(lines[index]):
                found.setdefault("R" + match.group(1), []).append(
                    (index, match.group(group) if group else None, lines[index]))
        return found

    def evidence_paths(self):
        """取证纸清单（只数 EVIDENCE_DIRS 下的 .md）；影子层换掉这枚枚举就能塞进不存在的纸。"""
        found = []
        for prefix in EVIDENCE_DIRS:
            root = self.root / prefix
            if not root.exists():
                continue
            found.extend(sorted(p.relative_to(self.root).as_posix() for p in root.rglob("*.md")))
        return found

    def _paper_index(self):
        """谁在说话：标题行写了 `G-<号>-<序>` 才叫认领，正文里的引用只算转述。

        账尺自己的取证纸、别的单号引到同一格的批注，都在正文里出现同一个欠账号——把它们
        当成认领，就等于「新写一枚纸能改写旧那张纸的判语」，那是另一族假账。转述照样数着，
        打进报表头，免得口径收窄之后悄悄漏了没人知道。
        """
        index, skipped, quoted = {}, [], []
        for rel in self.evidence_paths():
            try:
                lines = self.quoter.file_lines(rel)
            except (OSError, UnicodeDecodeError):
                skipped.append(rel)
                continue
            for where, line in enumerate(lines):
                if "G-R" not in line:
                    continue  # 先做廉价子串筛，再上正则：全库扫纸不能变成全库跑正则
                for match in GAP_KEY_RE.finditer(line):
                    key = "%s-%s" % (match.group(1), match.group(2))
                    if CLAIM_HEAD_RE.match(line):
                        index.setdefault(key, []).append((rel, where, line))
                    else:
                        quoted.append((key, rel))
        return index, skipped, quoted

    # ---- 派生：CLOSED／NOTBUILT／FOREIGN／ZERO -------------------------------------
    def closure(self, tid):
        hits = self.closures.get(tid)
        if not hits:
            return None
        instruments = sorted({extra for _, extra, _ in hits if extra})
        if len(instruments) != 1:
            return {"problem": "跟进单里 %s 的结案句点名了 %d 枚量具（%s）＝结案凭据不唯一"
                            % (tid, len(instruments), "、".join(instruments) or "零枚")}
        instrument = instruments[0]
        index, _, ruling_line = hits[-1]
        facts = {"instrument": instrument,
                 "ruling": {"file": FOLLOWUP, "line": index + 1, "quote": ruling_line.strip()}}
        commits = self.owned.get(instrument)
        if not commits:
            facts["problem"] = ("结案句点名量具 %s，主干归集里读不到它名下任何产物提交＝结案没有凭据" % instrument)
            return facts
        chosen = None
        for sha, products, _ in commits:
            papers = sorted(p for p in self.git.files(sha) if p.startswith(EVIDENCE_DIRS))
            if not papers:
                continue
            missing = sorted(p for p in list(products) + papers if not self.exists(p))
            if missing or not self.git.is_ancestor(sha):
                continue
            chosen = (sha, products, papers, missing)
            break
        if chosen is None:
            facts["problem"] = ("结案句点名量具 %s，但它名下没有一笔「取证纸＋产物仍在盘上＋在 HEAD 祖先链」齐的提交"
                                % instrument)
            return facts
        sha, products, papers, _ = chosen
        facts.update({"tier": "CLOSED", "commit": sha, "products": list(products), "papers": papers})
        return facts

    def notbuilt(self, tid):
        struck = self.plan_rows.get(tid, {}).get("struck") or []
        rulings = self.notbuilds_21.get(tid) or []
        if not struck and not rulings:
            return None
        if struck and rulings:
            plan_index = struck[-1]
            follow_index, _, ruling_line = rulings[-1]
            return {"tier": "NOTBUILT",
                    "plan": {"file": PLAN, "line": plan_index + 1,
                             "quote": self.plan_lines[plan_index].strip()},
                    "ruling": {"file": FOLLOWUP, "line": follow_index + 1,
                               "quote": ruling_line.strip()}}
        if struck:
            return {"problem": ("计划书把 %s 那行划了删除线（第 %d 行），跟进单 §21 却读不到「不建，沿用」裁定句"
                                "＝不可判定，不许掉回 ZERO 凑分子" % (tid, struck[-1] + 1))}
        return {"problem": ("跟进单 §21 里 %s 有「不建，沿用」裁定句（第 %d 行），计划书里却没有对应的删除线行"
                            "＝不可判定" % (tid, rulings[-1][0] + 1))}

    def foreign(self, row):
        tid = row["id"]
        if self.plan_rows.get(tid) or self.s21_rows.get(tid) or row["artifacts"] or self.owned.get(tid):
            return None
        return {"tier": "FOREIGN",
                "facts": ["计划书表格里读不到 %s 的行（含删除线形）" % tid,
                          "跟进单 §21 判据表里没有 %s 的行" % tid,
                          "主干归集：%s 名下 0 枚产物提交" % tid,
                          "台账未给它挂任何产物提交"]}

    def decide(self, row):
        tid = row["id"]
        candidates = [self.notbuilt(tid), self.closure(tid)]
        problems = [item["problem"] for item in candidates if item and item.get("problem")]
        tiers = [(item["tier"], item) for item in candidates if item and "tier" in item]
        if len({tier for tier, _ in tiers}) > 1:
            return None, {}, ["%s 同时读出不建裁定与结案裁定＝两条账面裁定打架" % tid]
        if not tiers:
            foreign = self.foreign(row)
            if foreign:
                tiers = [("FOREIGN", foreign)]
        if tiers:
            return tiers[0][0], tiers[0][1], problems
        if not self.owned.get(tid) and not row["artifacts"]:
            return "ZERO", {"note": "主干归集与台账产物都是空的，且没有任何账面裁定句"}, problems
        return None, {}, problems

    def exists(self, rel):
        """仓内路径判存在的唯一入口（反证刀要能在影子层把某一枚产物「拿走」而不碰真仓）。"""
        return (self.root / rel).exists()

    def basis(self, tid):
        """逐号点名「用了哪条事实」：表格行、§21 判据表行、主干归集，全部现取。"""
        plan = self.plan_rows.get(tid) or {"normal": [], "struck": []}
        if plan["struck"]:
            where = "计划书第 %d 行（删除线）" % (plan["struck"][-1] + 1)
        elif plan["normal"]:
            where = "计划书第 %d 行" % (plan["normal"][-1] + 1)
        else:
            where = "计划书无行"
        s21 = ("跟进单 §21 第 %d 行" % (self.s21_rows[tid][-1] + 1)) if self.s21_rows.get(tid) else "跟进单 §21 无行"
        owned = self.owned.get(tid) or []
        newest = ("主干归集 %d 枚产物提交（最新 %s·%d 枚）" % (len(owned), short(owned[0][0]), len(owned[0][1]))
                  if owned else "主干归集 0 枚产物提交")
        return [where, s21, newest]

    # ---- 派生：理由句（欠账那格纸面怎么说）
    def reason(self, key):
        hits = self.papers.get(key)
        if not hits:
            return None
        claimers = sorted({rel for rel, _, _ in hits})
        if len(claimers) > 1:
            return {"key": key,
                    "problem": "同一格 G-%s 被 %d 枚纸在标题里认领（%s）＝得先定谁说话" % (
                        key, len(claimers), "、".join(claimers))}
        # 认领看标题，判语看全纸：纸内自己订正过的，取最后一条带极性的判语（倒着扫）
        rel = claimers[0]
        lines = self.quoter.file_lines(rel)
        for index in range(len(lines) - 1, -1, -1):
            for phrase in reversed(BRACKET_RE.findall(lines[index])):
                flag = polarity(phrase)
                if flag:
                    sha = self.git.first_add(rel)
                    if sha is None:
                        return {"key": key, "paper": rel,
                                "problem": "取证纸 %s 读不到把它带进仓库的提交" % rel}
                    if not self.git.is_ancestor(sha):
                        return {"key": key, "paper": rel,
                                "problem": "取证纸 %s 的落盘提交 %s 不在 HEAD 祖先链上" % (rel, short(sha))}
                    return {"key": key, "paper": rel, "line": index + 1, "phrase": phrase,
                            "polarity": flag, "counts": self._counts(rel), "commit": sha}
        return {"key": key, "paper": rel,
                "problem": "认领了 %s 的取证纸（%s）里读不到带极性的判语句" % (key, rel)}

    def _counts(self, rel):
        found = None
        for line in self.quoter.file_lines(rel):
            if not FAILING_HINT_RE.search(line):
                continue
            for run in NUMBER_RUN_RE.findall(line):
                found = run
        return re.sub(r"[／、,．]", "/", found) if found else None


def closure_reason(facts):
    return "结案裁定现取：%s｜凭据 %s（量具 %s 并树）带进 %s，产物 %d 枚仍在盘上" % (
        facts["ruling"]["quote"], short(facts["commit"]), facts["instrument"],
        "、".join("`%s`" % path for path in facts["papers"]), len(facts["products"]))


def notbuilt_reason(facts):
    return "不建裁定现取：计划书第 %d 行划了删除线（%s）｜跟进单 §21 第 %d 行（%s）" % (
        facts["plan"]["line"], facts["plan"]["quote"], facts["ruling"]["line"], facts["ruling"]["quote"])


def foreign_reason(facts):
    return "外来号现取：" + "；".join(facts["facts"])


def derived_reason(facts):
    """欠账那格的现取判语拼成理由句：纸面结论＋未过线枚数＋仓内凭据（sha 由量具现取，不抄账面）。"""
    parts = ["%s（取证纸现取）" % facts["phrase"]]
    if facts.get("counts"):
        parts.append("未过线枚数＝母集 %s" % facts["counts"])
    parts.append("凭据 %s · %s" % (short(facts["commit"]), facts["paper"]))
    return "｜".join(parts)


def summarize_facts(facts):
    """把派生事实压成一句，供报错点名用（不许在报错里再抄一份成品账）。"""
    if not facts:
        return "无派生事实"
    if facts.get("problem"):
        return facts["problem"]
    tier = facts.get("tier")
    if tier == "CLOSED":
        return "结案句第 %d 行＋量具 %s 凭据 %s" % (
            facts["ruling"]["line"], facts["instrument"], short(facts["commit"]))
    if tier == "NOTBUILT":
        return "计划书删除线第 %d 行＋跟进单 §21 裁定第 %d 行" % (
            facts["plan"]["line"], facts["ruling"]["line"])
    if tier == "FOREIGN":
        return "；".join(facts["facts"])
    return facts.get("note", "无")


def T(tid, verdict, artifacts, gaps=(), why="", classes=("产品码", "契约"), note=""):
    return {"id": tid, "verdict": verdict, "artifacts": list(artifacts), "gaps": list(gaps),
            "why": why, "classes": classes, "note": note}


def A(sha, via, expect=None):
    return {"sha": sha, "via": via, "expect": expect}


def S21(tid, clause=None, seq=1):
    spec = {"file": FOLLOWUP, "span": SECTION_21, "anchor": "| **R%s** |" % tid,
            "cell": 3, "label": "跟进单 §21 判据表", "seq": seq}
    if clause:
        spec["clause"] = clause
    return spec


def P52(tid, cell=3, seq=1, label="计划书 §5.2 行（状态列）"):
    return {"file": PLAN, "anchor": "> | R%s |" % tid, "cell": cell,
            "label": label, "seq": seq}


def S101(anchor, label, seq=1):
    return {"file": FOLLOWUP, "anchor": anchor, "label": "跟进单 §101 · " + label, "seq": seq}


def S85(anchor, label, seq=1):
    return {"file": FOLLOWUP, "anchor": anchor, "label": "跟进单 §85 · " + label, "seq": seq}


LEDGER_A = [
    T("R25", "PARTIAL", [A("ad85821", "施工", "docker-compose.dev.yml"), A("b17b4dd", "并树")],
      [S21(25)], "两句判据都是容器内事实，从未在真机读过"),
    T("R26", "PARTIAL", [A("118801e", "R26a 施工"), A("11f9b1f", "R26a 并树"),
                         A("af027ce", "R26b 施工"), A("6ee2f79", "R26b 并树")],
      [S21(26, "①")], "②③④ 已落码，① 卡业主 H11 真机",
      note="本单产物全在拆单子号 R26a/R26b 名下；按裸号字面 grep 判它「没动过」是方法错（第三十六班已把这条写进规矩）"),
    T("R27", "PARTIAL", [A("ce0b041", "施工"), A("6a4f02b", "并树")],
      [S21(27, "③")], "③ 端到端 −≥35 s 等 A 门"),
    T("R28", "PARTIAL", [A("d2566e1", "施工"), A("1c0b08b", "并树")],
      [S21(28, "③")], "③ 30 题不退化等 A 门"),
    T("R29", "PARTIAL", [A("62c734d", "施工", "tests/test_r29_thinking_tax.py"), A("791568c", "并树")],
      [S21(29, "②")], "真机 A/B 判负：并的是「不迁腿」这个负结果与契约钉，30.6 s→≤22 s 一分没省"),
    T("R30", "LANDED", [A("3cb563b", "施工", "app/agents/contracts.py"), A("50aff1a", "并树")],
      [], "四条判据逐条有码有钉（结案核对 R224 判「达」）"),
    T("R31", "PARTIAL", [A("a7cd9b6", "施工", "app/agents/nodes.py"), A("eef642b", "并树")],
      [S21(31, "②")], "后端交出合格片序列；② 逐片无缺字等 A 门，端点多发那一半转出 R149"),
    T("R32", "LANDED", [A("0cfd86a", "施工", "app/api/v1/chat.py"), A("8a91f4e", "并树")],
      [], "①②③ 达；档位选择器按假控件禁令不交、拆 R141"),
    T("R33", "LANDED", [A("b35e10f", "施工", "app/memory/summarizer.py"), A("9678d21", "并树")],
      [], "短期记忆腿自本枚起零模型，①②③ 达"),
    T("R34", "LANDED", [A("b1d185e", "施工", "app/common/model_handler.py"), A("e4d0c1b", "并树")],
      [], "①②③ 达（① 引 09-19 真机落盘读数）"),
    T("R35", "PARTIAL", [A("63651f1", "施工", "app/common/cache.py"), A("90d029f", "并树")],
      [S21(35, "②")], "② 跨部门／跨密级 0 条命中待 C 门矩阵"),
    T("R36", "LANDED", [A("ef3d193", "施工", "tests/fixtures/business_evaluation_100.jsonl"), A("ac44d00", "并树")],
      [], "评测集 105 条在树，①②③ 达"),
    T("R37", "PARTIAL", [A("45b9720", "worker 半程", "deploy/queue_worker.py"), A("0c08209", "并树")],
      [S21(37, "③")], "产物在树、开关默认关；③ 终态原因码由 R227 改码后未重量"),
    T("R38", "PARTIAL", [A("c81fbb5", "施工", "app/trace/spans.py"), A("2e6abc6", "并树")],
      [S21(38)], "通路形状已修（原生腿读回 input_tokens、cached 归真）；「抽查一问非零」等真机 D-2",
      note="上一格派工词给的 `40e6789` 在本仓不存在——R38 的真凭据是 c81fbb5＋并树 2e6abc6"),
    T("R39", DERIVED, [], [],
      note="原判 ZERO 是假账：业主裁定不建的号不该计入零提交分子；判定与裁定引文都由 Deriver 现取（R640 判据 D1/D2）"),
    T("R40", "LANDED", [A("dc31a44", "施工", "app/api/v1/intelligence.py"), A("8585315", "并树"),
                        A("d0489e6", "并树 R237 收判据③", "frontend/src/devFixtures/approval-demo.js")],
      [], "①② 由本号落码；③ 前端 standard: 500 已由 R237 删除，牙在 r237-r40-standard-auto.test.js（含变体自证）"),
    T("R41", "LANDED", [A("e8d3200", "施工", "app/api/v1/chat.py"), A("571e0d6", "并树")], [], "①②③ 达"),
    T("R42", "LANDED", [A("5ff93cd", "施工", "app/agents/nodes.py"), A("89965d5", "并树")],
      [], "按 §27.2 改判口径达；业主驳回 H15 则本号自动回未达"),
    T("R43", "PARTIAL", [A("4586bb4", "R43a 并树", "app/common/model_handler.py"),
                         A("839c344", "R43b＝R167 并树", "tests/test_r167_answer_prefix_reuse.py")],
      [S21(43, "②")], "① 由 R43a 落码；② 真机 E3 读数与「cached 落库那一列」都还没有",
      note="R43b 交回的是尺子，结论「本写域可挪字节 = 0」——上一格派工词把 839c344 记成 R43 的并树提交是单号错位"),
    T("R44", "PARTIAL", [A("9940c13", "施工", "app/rag/hot_index.py"), A("39006b8", "并树"), A("564340e", "总控热修")],
      [S21(44, "①")], "① 的 105/105 是在 379 chunk 小库＋哈希桩上证的，真库 37 483 chunk 未测"),
    T("R45", "LANDED", [A("0276f78", "施工", "app/rag/retrieval_pipeline.py"), A("640ef08", "并树")],
      [], "按 §21.9／§21.10 重定义口径达"),
]

LEDGER_EXTRA = [
    T("R46", "PARTIAL", [A("c29ccf5", "R152 施工（后端半张）", "migrations/0011_document_activity_signals.sql"),
                         A("eaa9af8", "R152 并树"), A("484536c", "R195 并树（消费侧）", "frontend/src/lib/feedback.js")],
      [S21(46, "①")], "① 真库/真并发次序未证；按 filename 聚合无身份 ⇒ 强度校准另在 R153",
      note="计划书 L468 那句「真零产物只剩 R46 的消费侧」是假账：消费侧产物在 R195 名下已并树"),
    T("R47", "PARTIAL", [A("95a1cd9", "施工", "app/rag/retrieval_pipeline.py"), A("006c613", "并树")],
      [S21(47, "①")], "① 真实命中改进量 0/105（用例打桩）"),
    T("R48", "PARTIAL", [A("0ad3d3e", "并树 R48 路线甲", "frontend/src/components/AnswerHeadlineCard.vue")],
      [S21(48, "①")], "① 首屏 ≤1 s 在本机硬件口径上物理不可达（地板 11.0 s），B 行已整行移出 V1"),
    T("R49", "LANDED", [A("8680f43", "施工", "app/documents/index_policy.py"), A("c26afda", "并树"),
                         A("d0489e6", "并树 R237 收判据②", "frontend/src/components/DocPanel.vue")],
      [], "①③ 由本号落码；②「未索引」那张脸已由 R237 接上 index_status/excluded 字段，钉 r237-r49-index-face.test.js"),
    T("R50", "PARTIAL", [A("090c820", "施工", "scripts/rebuild_index.py"), A("94f7fa1", "并树")],
      [S21(50, "②")], "增量与可续跑在树；「低峰」那半句没挂进排程",
      note="计划书 L468 那句「真零产物只剩 R50」是假账：R50 名下两枚产物提交都在主干"),
    T("R51", "PARTIAL", [A("6833140", "施工", "app/common/stage_timing.py"), A("cef08bf", "并树")],
      [S21(51, "②")], DERIVED),
    T("R52", "PARTIAL", [A("8c888c7", "施工", "scripts/check_airgap_readiness.py"), A("1b84fb2", "闸门自修")],
      [S21(52, "①")], "①②③ 全是墙上事实，E 行已整行移出 V1"),
    T("R141", "LANDED", [A("1cbd164", "并树", "frontend/src/router/lane-choice.js")], [],
      "档位标签第一次真改派工作腿；看板 §4BF 记「R141 达标并树」"),
    T("R142", "LANDED", [A("19761a5", "施工", "tests/test_r142_error_code_table_sync.py"), A("b58a5b9", "并树")],
      [], "契约错误码表机械化对账上岗（并树记 +12 用例）"),
    T("R143", DERIVED, [], [],
      note="原判 ZERO 是假账：账面结案裁定与量具产物都在仓内；判定与结案笔都由 Deriver 现取（R640 判据 D1/D2）"),
    T("R144", DERIVED, [], [],
      note="原判 ZERO 是假账：外来号不是「零提交」；外来身份由 Deriver 从表格行与主干归集现取（R640 判据 D2）"),
    T("R145", "LANDED", [A("e2de245", "施工", "scripts/audit_vector_mirror_sets.py"), A("f747109", "并树")],
      [], "向量镜像集合面对账台上岗（并树记 +91 用例）"),
    T("R146", "LANDED", [A("77cd8b4", "施工", "app/trace/spans.py"), A("25a08f0", "并树")],
      [], "cached-token 论述与记账归真（并树记 +16 用例）"),
    T("R253", "LANDED", [A("ea2a539", "并树", "tests/test_r253_no_test_rewrites_a_tracked_file.py")], [],
      "反证钉变异只落影子副本；判据④ 同一 HEAD 连跑三次 -n 8 零漂移已由主树三跑满（d853153 三连 5260/49，账记 8051897）"),
    T("R254", "LANDED", [A("8f89def", "并树", "app/api/v1/chat.py"), A("c70548a", "R254b 总控补口")],
      [], "六条判据逐条有码有钉（§101.2 记已结案）"),
    T("R255", "LANDED", [A("3bf271d", "并树", "app/common/model_budget.py")], [],
      "窗口与预算同一处推导，撞顶报错自报差额"),
    T("R256", "LANDED", [A("ff0f4ec", "并树", "migrations/0015_dataset_version_scope_columns.sql"),
                         A("d853153", "R256b 总控补口")], [],
      "五条判据逐条对账，④ 首次在隔离 PG 真库跑到底并留凭据"),
    T("R257", "LANDED", [A("71aea57", "并树", "app/trace/store.py")], [],
      "兜底那卷 jsonl 会被结清且每行自报身份；承重前 24 行逐字节未动（§4CH 记已结案）"),
    T("R258", "LANDED", [A("6b4f04c", "总控自办", "docs/handoff/2026-09-17-eval-real-run-runbook.md")], [],
      "runbook 三枚假零入册", classes=("文书",),
      note="本单交付物就是那枚运维手册：判据①「产品码或契约」在这里不适用，例外已在账上具名"),
    T("R259", "LANDED", [A("67ea193", "并树", "scripts/eval_transport_ask_v2.py")], [],
      "量具认识 awaiting_approval 并把队列终态折进 queue.terminal（§4CH 记已结案）"),
    T("R260", "LANDED", [A("b8ea5a9", "并树", "frontend/src/components/ChatPanel.vue"),
                         A("9dd6eba", "R260b 总控补口")], [],
      "挂起轮前端停表并给可批准入口；它补的那枚名单带出 R260b（§4CH 记已结案）"),
    T("R261", "LANDED", [A("c9ad493", "并树", "tests/test_r238_bare_connect_ratchet.py")], [],
      "棘轮换 路径::作用域#序 身份记账，行号退出账本但留在报错里（§4CH 记已结案）",
      note="c70548a 与 d853153 那两笔改账在 R254b/R256b 名下，正是本单要消灭的 path:line 税，不算它的产物"),
]

LEDGER = LEDGER_A + LEDGER_EXTRA


def scan_history(deriver, rows):
    """把派生层的归集结果按在册号切片（归集本身见 attribute），用来反证 ZERO 那笔账。"""
    attributed = {}
    catch_up = {}
    for row in rows:
        tid = row["id"]
        attributed[tid] = [(short(sha), len(products), suffix)
                           for sha, products, suffix in deriver.owned.get(tid, [])]
        catch_up[tid] = [(short(sha), len(products), suffix)
                         for sha, products, suffix in deriver.catch_up.get(tid, [])]
    return attributed, catch_up


def plan_status(quoter, tid):
    try:
        lines, index = quoter.locate({"file": PLAN, "anchor": "> | %s |" % tid})
    except SourceError:
        return None
    return Quoter.cell(lines[index], 3)


def resolve_artifacts(git, row):
    """逐枚现取台账挂的证据提交；派生凭据可点名另一枚号（owner＝提交信息里必须出现的那枚单号）。"""
    resolved = []
    for art in row["artifacts"]:
        item = dict(art)
        token = item.get("owner") or row["id"]
        item["owner"] = token
        full = git.resolve(art["sha"])
        item["full"] = full
        if full:
            files = git.files(full)
            item["files"] = files
            item["product"] = product_files(files, row["classes"])
            item["ancestor"] = full in git.ancestors()
            item["mention"] = bool(re.search(
                r"(?<![A-Za-z0-9])" + re.escape(token) + r"[a-z]?(?![0-9A-Za-z])",
                git.message(full)))
        else:
            item["files"] = []
            item["product"] = []
            item["ancestor"] = False
            item["mention"] = False
        resolved.append(item)
    return resolved


def tier_reason(tier, facts):
    """新档的「一句话依据」也只许从派生事实拼出来，脚本里不存成品句。"""
    if tier == "CLOSED":
        return closure_reason(facts)
    if tier == "NOTBUILT":
        return notbuilt_reason(facts)
    if tier == "FOREIGN":
        return foreign_reason(facts)
    if tier == "ZERO":
        return "派生到的只有「全史零产物」这一条：%s" % facts.get("note", "")
    return ""


def build_rows(git, quoter, deriver):
    attributed, catch_up = scan_history(deriver, LEDGER)
    rows = []
    for spec in LEDGER:
        row = dict(spec)
        row["artifacts_resolved"] = resolve_artifacts(git, row)
        row["gaps_resolved"] = [quoter.quote(gap, row["id"]) for gap in spec["gaps"]]
        row["auto"] = sorted(attributed[row["id"]])
        row["catch_up"] = sorted(catch_up[row["id"]])
        row["plan_status"] = plan_status(quoter, row["id"])
        row["faulted"] = False
        row["declared"] = spec["verdict"]
        row["why_declared"] = spec["why"]
        tier, facts, problems = deriver.decide(row)
        row["derived_tier"] = tier
        row["derived_facts"] = facts
        row["derive_problems"] = problems
        row["verdict"] = (tier or "UNDECIDABLE") if spec["verdict"] == DERIVED else spec["verdict"]
        if row["verdict"] == "CLOSED" and facts.get("commit"):
            row["artifacts"] = list(spec["artifacts"]) + [{
                "sha": short(facts["commit"]), "via": "账面结案句现读（量具 %s）" % facts["instrument"],
                "expect": facts["papers"][0], "owner": facts["instrument"], "derived": True}]
            row["artifacts_resolved"] = resolve_artifacts(git, row)
        row["gap_reasons"] = []
        for gap in row["gaps_resolved"]:
            paper = deriver.reason(gap["key"])
            if paper:
                row["gap_reasons"].append((gap["key"], paper))
        row["why_problems"] = []
        derived_whys = []
        for key, paper in row["gap_reasons"]:
            if paper.get("problem"):
                row["why_problems"].append("G-%s：%s" % (key, paper["problem"]))
            else:
                derived_whys.append(derived_reason(paper))
        if spec["why"] == DERIVED:
            row["why"] = "；".join(derived_whys)
            if spec["gaps"] and not derived_whys:
                row["why_problems"].append("理由句标了派生，却没有取证纸以 G-%s 认领这一格" % row["gaps_resolved"][0]["key"])
        else:
            row["why"] = spec["why"] or (tier_reason(row["verdict"], facts) if spec["verdict"] == DERIVED else spec["why"])
        rows.append(row)
    return rows


def apply_faults(git, rows, faults):
    """反证自证入口：只改内存台账，不落盘、不出货（报表头会打上注入标记）。"""
    for row in rows:
        if row["id"] not in faults:
            continue
        verdict, shas = faults[row["id"]]
        row["verdict"] = verdict
        row["faulted"] = True
        row["gaps_resolved"] = []
        row["artifacts"] = [{"sha": sha, "via": "故障注入", "expect": None} for sha in shas]
        row["artifacts_resolved"] = resolve_artifacts(git, row)
        row["why"] = "本次判定系故障注入，不作账"
    return rows


def self_checks(rows):
    """这台尺子的牙：老三档的牙一枚不摘，新档再加五枚，全部对着「此刻的事实」咬。

    C11 新档判定写死＝红（派生哨兵不许退回头抄账）
    C12 标了派生却落不实地＝红（结案句与裁定句都不许断头）
    C13 台账档位与账面派生档打架＝红（尤其把已结案／外来／不建记成 ZERO 那族假账）
    C14 写死的理由句与取证纸现取的判语打架＝红（读纸的内容，不读提交标题）
    C15 取证纸已判达却仍挂欠账＝红
    C16 新档不许挂点名欠账（要么改判 PARTIAL，要么把凭据补齐）
    C17 CLOSED 必须有结案凭据那一笔在台账里；NOTBUILT／FOREIGN 不许有任何产物
    C18 同一格欠账只许一枚纸在标题里认领（正文转述不算认领，新写一枚纸不许顶掉量具的判语）
    """
    failures = []
    for row in rows:
        tid = row["id"]
        classes = "/".join(row["classes"])
        verdict = row["verdict"]
        products = [art for art in row["artifacts_resolved"] if art["product"]]
        for art in row["artifacts_resolved"]:
            if art["full"] is None:
                failures.append("C2 %s：证据提交 `%s` 在仓库里根本不存在（引用假账）" % (tid, art["sha"]))
                continue
            if not art["ancestor"]:
                label = "🔴" if verdict in ("LANDED", "CLOSED") else "·"
                failures.append("%s C3 %s：证据提交 `%s`（%s）不在 HEAD 祖先链上＝未并树" %
                                (label, tid, art["sha"], art["via"]))
            if not art["mention"]:
                failures.append("C4 %s：`%s` 的提交信息里没有单号 %s＝张冠李戴" % (tid, art["sha"], art["owner"]))
            if art["expect"] and art["expect"] not in " ".join(art["files"]):
                failures.append("C5 %s：`%s` 没改到点名的落点 `%s`" % (tid, art["sha"], art["expect"]))
        if row["declared"] in DERIVABLE_TIERS:
            failures.append("C11 %s：判定词「%s」是新档，只许由事实派生（本格要写 DERIVED 哨兵，写死＝台账退回手抄账）"
                            % (tid, row["declared"]))
        if (row["declared"] != DERIVED and row["derived_tier"] in DERIVABLE_TIERS
                and row["derived_tier"] != verdict):
            failures.append("C13 %s：台账记 %s，账面事实派生却是 %s（%s）" % (
                tid, verdict, row["derived_tier"], summarize_facts(row["derived_facts"])))
        if row["declared"] == DERIVED and not row["faulted"]:
            if row["derive_problems"] or verdict == "UNDECIDABLE":
                failures.append("C12 %s：判定标了派生却落不实地：%s" % (
                    tid, "；".join(row["derive_problems"]) or "没有任何账面事实可用"))
        if verdict in ("LANDED", "CLOSED") and not products:
            failures.append("C6 %s：判 %s 却没有一枚证据提交带来%s改动（纯 docs 记账不算）" % (tid, verdict, classes))
        if verdict == "PARTIAL":
            if not products:
                failures.append("C7 %s：判 PARTIAL 却没有产物 ⇒ 按口径应改判 ZERO" % tid)
            if not row["gaps_resolved"]:
                failures.append("C8 %s：判 PARTIAL 却没点名欠哪条判据（判据原文必须逐字引用，不许转述）" % tid)
        elif verdict == "ZERO":
            if row["auto"]:
                failures.append("C9 %s：判 ZERO 是假账——自动归集在主干上逮到本号名下产物提交 %s" % (
                    tid, "、".join("`%s`(%d 枚)" % (sha, count) for sha, count, _ in row["auto"])))
            if products:
                failures.append("C10 %s：判 ZERO 却挂了产物提交 `%s`" % (
                    tid, "、".join(art["sha"] for art in products)))
        elif verdict in ("CLOSED", "NOTBUILT", "FOREIGN"):
            if row["gaps_resolved"]:
                failures.append("C16 %s：判 %s 却还挂着点名欠账" % (tid, verdict))
            if row["auto"]:
                failures.append("C17 %s：判 %s 是假账——主干归集逮到本号名下产物提交 %s" % (
                    tid, verdict, "、".join("`%s`(%d 枚)" % (sha, count) for sha, count, _ in row["auto"])))
            if products and verdict in ("NOTBUILT", "FOREIGN"):
                failures.append("C17 %s：判 %s 却挂了产物提交 `%s`" % (
                    tid, verdict, "、".join(art["sha"] for art in products)))
            if verdict == "CLOSED" and not any(art.get("derived") for art in row["artifacts_resolved"]):
                failures.append("C17 %s：判 CLOSED 但台账里没有「结案凭据」那一笔（结案句点名的量具提交必须挂上来受 C2/C3/C5 管）" % tid)
        elif verdict not in VERDICTS:
            failures.append("C1 %s：判定词「%s」不在六档之内" % (tid, verdict))
        if verdict == "PARTIAL" and not row["faulted"]:
            for key, paper in row["gap_reasons"]:
                if paper.get("polarity") == "MEASURED" and "PASS" in paper.get("phrase", ""):
                    failures.append("C15 %s：取证纸已把 G-%s 判达（「%s」），这一格却仍挂在欠账里" % (tid, key, paper["phrase"]))
        if row["why_declared"] not in (DERIVED, "") and row["gap_reasons"] and not row["faulted"]:
            claim = polarity(row["why_declared"])
            for key, paper in row["gap_reasons"]:
                if claim and paper.get("polarity") and paper["polarity"] != claim:
                    failures.append(
                        "C14 %s：写死的理由句「%s」判为 %s，取证纸现取的 G-%s 判语却是「%s」＝%s"
                        "⇒ 理由句必须改判，从纸面派生（不许只读提交标题）" % (
                            tid, row["why_declared"], claim, key, paper.get("phrase", ""), paper.get("polarity", "")))
        for key, paper in row["gap_reasons"]:
            if paper.get("problem") and row["why_declared"] != DERIVED:
                failures.append("C18 %s：G-%s 的取证纸给不出唯一判语——%s" % (tid, key, paper["problem"]))
        if row["why_declared"] == DERIVED and not row["faulted"]:
            for problem in row["why_problems"]:
                failures.append("C12 %s：理由句派生落不实地——%s" % (tid, problem))
    return failures


def source_label(row):
    """判定与理由句各自的来源（派生／写死），报表里逐号点名。"""
    parts = ["判定派生" if row["declared"] == DERIVED else "判定写死"]
    if row["why_declared"] == DERIVED:
        parts.append("理由派生")
    elif row["why_declared"]:
        parts.append("理由写死")
    return "＋".join(parts)


def render_head(git, rows, faults, deriver):
    out = []
    emit = out.append
    emit("R262／R640 计划书台账归真 · 机器账（只读 git 与工作树；判据原文、裁定句、理由句一律现读现切）")
    if faults:
        emit("!! 本次运行注入故障台账：%s ⇒ 这份输出是反证演示，不是账" % "、".join(sorted(faults)))
    emit("head=%s commits_on_head=%d worktree=%s" % (git.head(), len(git.commits()), git.worktree_state()))
    emit("六档口径：LANDED＝产物在树且无点名欠账；PARTIAL＝产物在树但点名欠判据；"
         "CLOSED＝账面结案裁定句点名量具且其产物与取证纸都在仓内（派生）；ZERO＝HEAD 祖先链上全史零产物；"
         "FOREIGN＝计划书与跟进单 §21 都没有它的行（派生）；NOTBUILT＝计划书划删除线＋§21 不建裁定（派生）")
    emit("派生纪律：CLOSED／FOREIGN／NOTBUILT 只许从事实派生——判定写死咬 C11，把已结案／外来／不建记成 ZERO 咬 C13，"
         "理由句与取证纸打架咬 C14，取证纸已判达却仍挂欠账咬 C15，派生落不实地咬 C12")
    emit("归属口径：提交标题里第一枚单号＝该提交的归属号（拆单子号 R26a/R43a/R152 一类按账上具名挂靠，不自动并号）；"
         "标题含 catch up/追平/保活 的只记账不作产物证据")
    emit("产物口径：产品码＝app/frontend/scripts/tests/migrations/deploy/static 与代码类后缀；契约＝docs/api/** 与 migrations/manifest.json")
    emit("取证纸面：以标题行写 `G-<号>-<序>` 认领欠账格的仓内取证纸 %d 枚（读不到而跳过 %d 枚；"
         "正文里另有 %d 处转述——转述不认领，不许顶掉量具那张纸的判语）；%%TEMP%% 里的工件不作派生源" % (
             len(deriver.papers), len(deriver.skipped_papers), len(deriver.quotings)))
    emit("")
    emit("## 1. 逐号结论")
    emit("")
    emit("| 号 | 判定 | 判定来源 | 证据提交（归属·实改产物枚数） | 在 HEAD 祖先链 | 一句话依据 | 欠账引用 |")
    emit("|---|---|---|---|---|---|---|")
    for row in rows:
        if row["artifacts_resolved"]:
            evidence = "、".join("`%s`·%s[%d 枚]%s" % (
                art["sha"], art["via"], len(art["product"]), "" if art["ancestor"] else "†")
                for art in row["artifacts_resolved"])
            ancestor = "是" if any(art["ancestor"] for art in row["artifacts_resolved"]) else "—"
        else:
            evidence = "无（全史零产物）" if row["verdict"] == "ZERO" else "无（本格不认产物）"
            ancestor = "—"
        gaps = "、".join("G-%s" % gap["key"] for gap in row["gaps_resolved"]) or "—"
        emit("| %s | **%s** | %s | %s | %s | %s | %s |" % (
            row["id"], row["verdict"], source_label(row), safe(evidence), ancestor,
            safe(row["why"]) or "—", gaps))
    emit("")
    emit("†＝该提交存在但不在本 HEAD 的祖先链上（未并树或活在别的分支）。")
    emit("")
    emit("## 2. 证据提交实改文件（`git diff <第一父> <提交>` 逐枚现取）")
    emit("")
    for row in rows:
        if not row["artifacts_resolved"]:
            continue
        emit("- **%s**（%s）" % (row["id"], row["verdict"]))
        for art in row["artifacts_resolved"]:
            if art["full"] is None:
                emit("  - `%s`（%s）：仓库里查不到这枚提交" % (art["sha"], art["via"]))
                continue
            emit("  - `%s`（%s，祖先=%s）→ %s" % (
                art["sha"], art["via"], "是" if art["ancestor"] else "否",
                "、".join("%s:%s" % (classify(path), path) for path in art["files"]) or "（无文件）"))
    emit("")
    emit("## 3. 派生台账（逐号点名用了哪条事实）")
    emit("")
    for row in rows:
        emit("- **%s** ｜判定 %s｜来源 %s" % (row["id"], row["verdict"], source_label(row)))
        for bit in deriver.basis(row["id"]):
            emit("  - 基准事实：%s" % bit)
        facts = row["derived_facts"]
        if facts.get("tier") == "CLOSED":
            emit("  - 结案裁定：%s（第 %d 行）原文：%s" % (
                facts["ruling"]["file"].split("/")[-1], facts["ruling"]["line"], facts["ruling"]["quote"]))
            emit("  - 量具 %s 凭据 %s｜取证纸 %s｜仍在盘上的产物 %d 枚：%s" % (
                facts["instrument"], short(facts["commit"]), "、".join(facts["papers"]),
                len(facts["products"]), "、".join("`%s`" % path for path in facts["products"])))
        elif facts.get("tier") == "NOTBUILT":
            emit("  - 计划书删除线行（第 %d 行）原文：%s" % (facts["plan"]["line"], facts["plan"]["quote"]))
            emit("  - §21 不建裁定（第 %d 行）原文：%s" % (facts["ruling"]["line"], facts["ruling"]["quote"]))
        elif facts.get("tier") == "FOREIGN":
            for bit in facts["facts"]:
                emit("  - 外来身份：%s" % bit)
        elif facts.get("tier") == "ZERO":
            emit("  - 零提交依据：%s" % facts.get("note", ""))
        for problem in row["derive_problems"]:
            emit("  - 🔴 派生落不实地：%s" % problem)
        for key, paper in row["gap_reasons"]:
            if paper.get("problem"):
                emit("  - 🔴 G-%s 纸面：%s" % (key, paper["problem"]))
            else:
                emit("  - G-%s 纸面判语：%s（%s，第 %d 行）｜极性 %s%s｜落盘凭据 %s" % (
                    key, paper["phrase"], paper["paper"], paper["line"], paper["polarity"],
                    "｜未过线枚数＝母集 %s" % paper["counts"] if paper.get("counts") else "",
                    short(paper["commit"])))
    return out


def render_tail(git, rows, out):
    emit = out.append
    emit("")
    emit("## 4. 欠账与判据原文（机器从出处逐字切段，非转述）")
    emit("")
    for row in rows:
        for gap in row["gaps_resolved"]:
            emit("- G-%s ｜出处：%s ｜`%s` 第 %d 行（按 LF 计数）｜%s ｜原文：%s" % (
                gap["key"], gap["source"], gap["file"], gap["line"], row["verdict"], gap["quote"]))
    emit("")
    emit("## 5. 计划书那行现在的台账词（只列在册行；本尺只读账本，订正由人写段落笔）")
    emit("")
    for row in rows:
        if row["plan_status"]:
            drift = ""
            if row["verdict"] in DERIVABLE_TIERS and "待派" in row["plan_status"]:
                drift = "｜🔴 账面滞后：本尺派生为 %s，计划书那行仍写「待派」（改表归人，不归这把尺）" % row["verdict"]
            emit("- %s ｜台账现词：%s%s" % (row["id"], row["plan_status"], drift))
    emit("- 其余在册号在计划书表格里没有状态列——这张表**没有结案列**，被抄来抄去会被当成还剩这么多没做")
    emit("")
    emit("## 6. 反查：主干自动归集（专治「零提交」假账）")
    emit("")
    for row in rows:
        auto = "、".join("`%s`%s(%d 枚产品文件)" % (sha, ("/" + suffix if suffix else ""), count)
                         for sha, count, suffix in row["auto"]) or "0 枚"
        catch = "、".join("`%s`" % sha for sha, _, _ in row["catch_up"]) or "—"
        emit("- %s ｜自号产物提交：%s ｜追平/保活（不作证据）：%s" % (row["id"], auto, catch))
    emit("")
    counts = dict((verdict, 0) for verdict in VERDICTS)
    for row in rows:
        if row["verdict"] in counts:
            counts[row["verdict"]] += 1
    emit("## 7. 计数")
    emit("")
    emit("在册 %d 号：LANDED=%d · PARTIAL=%d · CLOSED=%d · ZERO=%d · FOREIGN=%d · NOTBUILT=%d" % (
        len(rows), counts["LANDED"], counts["PARTIAL"], counts["CLOSED"],
        counts["ZERO"], counts["FOREIGN"], counts["NOTBUILT"]))
    for verdict in VERDICTS:
        emit("- %s：%s" % (verdict, " ".join(row["id"] for row in rows if row["verdict"] == verdict) or "无"))
    emit("- 派生档合计 %d 号：%s" % (
        sum(1 for row in rows if row["declared"] == DERIVED),
        " ".join(row["id"] for row in rows if row["declared"] == DERIVED) or "无"))
    emit("")
    emit("## 8. V1 判据「计划书代码单清零」的距离")
    emit("")
    zeros = [row for row in rows if row["verdict"] == "ZERO"]
    partials = [row for row in rows if row["verdict"] == "PARTIAL"]
    parked = [row for row in rows if row["verdict"] in CLEARED_TIERS]
    emit("- 读法甲（产物在树即算清）：未清 %d 号：%s" % (len(zeros), " ".join(row["id"] for row in zeros) or "无"))
    emit("- 读法乙（判据全达才算清）：未清 %d 号（PARTIAL %d ＋ ZERO %d）" % (
        len(zeros) + len(partials), len(partials), len(zeros)))
    emit("- 不计入欠账的档：%s（CLOSED＝已结案有仓内凭据；NOTBUILT＝业主裁定不建；FOREIGN＝外来号从没立过后端单）" % (
        " ".join(row["id"] for row in parked if row["verdict"] in DERIVABLE_TIERS) or "无"))
    for row in partials + zeros:
        gaps = "；".join(gap["quote"] for gap in row["gaps_resolved"]) or row["why"]
        emit("  - %s（%s）差：%s" % (row["id"], row["verdict"], gaps))
    return counts


CHECKLIST = (
    "C1 判定词只许六档", "C2 证据提交必须存在", "C3 证据提交必须在 HEAD 祖先链上",
    "C4 提交信息必须含点名的那枚单号（派生凭据认量具号）", "C5 点名落点必须在该提交实改文件里",
    "C6 LANDED／CLOSED 必须有产品码或契约改动", "C7 PARTIAL 必须有产物",
    "C8 PARTIAL 必须逐字点名欠账", "C9 ZERO 不得被自动归集逮到产物", "C10 ZERO 不得挂产物提交",
    "C11 新档判定不许写死单号名单", "C12 标了派生必须落得了地（结案凭据与裁定句都不许断头）",
    "C13 台账档与派生档不许打架（尤其把已结案／外来／不建记成 ZERO）",
    "C14 写死的理由句不许与取证纸现取判语打架", "C15 取证纸已判达不许仍挂欠账",
    "C16 新档不许挂点名欠账", "C17 新档的凭据与产物口径",
    "C18 同一格只许一枚纸认领（标题行才算认领，正文转述不算）")


def main(argv=None):
    parser = argparse.ArgumentParser(description="R262 计划书台账归真（只读，不写任何东西）")
    parser.add_argument("--timing", action="store_true", help="耗时打到 stderr，stdout 保持逐字节稳定")
    parser.add_argument("--fault", action="append", default=[],
                        help="反证自证：--fault TICKET=VERDICT@SHA[,SHA…]（只改内存台账）")
    args = parser.parse_args(argv)

    faults = {}
    for item in args.fault:
        try:
            tid, rest = item.split("=", 1)
            verdict, shas = rest.split("@", 1)
        except ValueError:
            print("--fault 写法：R46=LANDED@deadbeef", file=sys.stderr)
            return 2
        faults[tid.strip()] = (verdict.strip().upper(), [s.strip() for s in shas.split(",") if s.strip()])

    started = time.monotonic()
    git = Git(REPO)
    try:
        quoter = Quoter(REPO)
        deriver = Deriver(git, quoter, [row["id"] for row in LEDGER])
        rows = build_rows(git, quoter, deriver)
        rows = apply_faults(git, rows, faults)
        out = render_head(git, rows, faults, deriver)
        counts = render_tail(git, rows, out)
    except SourceError as error:
        print("环境/出处错：%s" % error, file=sys.stderr)
        return 2
    failures = self_checks(rows)
    out.append("")
    out.append("## 9. 自检（这台尺子的牙）")
    out.append("")
    out.append("；".join(CHECKLIST))
    if failures:
        for failure in failures:
            out.append("🔴 %s" % failure)
        bitten = sorted(set(match.group(1) for failure in failures
                            for match in [re.search(r"(R\d+)", failure)] if match))
        out.append("")
        out.append("RESULT=FAIL（%d 条）· 咬到的单号：%s" % (len(failures), " ".join(bitten)))
    else:
        out.append("")
        out.append("RESULT=PASS（0 条违规，在册 %d 号逐条自证）" % len(rows))
    sys.stdout.write("\n".join(out) + "\n")
    if args.timing:
        print("elapsed=%.2fs" % (time.monotonic() - started), file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")
    sys.exit(main())
