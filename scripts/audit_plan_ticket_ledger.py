#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R262 · 计划书台账归真：把「哪些单真落地了」做成机器可校验的账。

这台尺子只出三档：LANDED（产物在树且无点名欠账）／PARTIAL（产物在树但欠某条判据，
欠的那条从出处文件逐字切出）／ZERO（HEAD 祖先链上全史零产物）。

纪律长在代码里，不是长在回执里：
- 只读：只调 git 子命令与读文件，不写任何东西、不联网、不起服务、不碰模型、不跑测试。
- 逐字：判据原文一律运行时按锚点从出处切段，脚本内不存一份转述；锚点不唯一就当场停。
- 稳定：同一 HEAD 连跑两次 stdout 逐字节相同（无时间戳、路径一律正斜杠、按号排序）。
- 反证：判 LANDED 而证据提交不在 HEAD 祖先链上 ⇒ 非零退出并点名那一号。

用法：
    python scripts/audit_plan_ticket_ledger.py
    python scripts/audit_plan_ticket_ledger.py --timing     # 耗时只打 stderr
    python scripts/audit_plan_ticket_ledger.py --fault R46=LANDED@deadbeef

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

VERDICTS = ("LANDED", "PARTIAL", "ZERO")
CLAUSE_MARKS = "①②③④⑤⑥⑦⑧⑨"
PRIMARY_RE = re.compile(r"(?<![A-Za-z0-9])R(\d{1,3})([a-z]?)(?![0-9A-Za-z])")
CATCH_UP_RE = re.compile(r"catch up|追平|保活")
SECTION_21 = ("## 21. 性能与架构线正式立单", "### 21.1")


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
        rc, _, _ = self._run(["cat-file", "-e", rev + "^{commit}"])
        if rc != 0:
            return None
        return self.out("rev-parse", rev + "^{commit}").strip()

    def is_ancestor(self, full_sha):
        return self._run(["merge-base", "--is-ancestor", full_sha, "HEAD"])[0] == 0

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
    T("R39", "ZERO", [],
      [{"file": PLAN, "anchor": "| ~~R39~~ |", "cell": 2, "seq": 1, "label": "计划书 §5.2 主表行（一句话列）"},
       {"file": FOLLOWUP, "span": SECTION_21, "anchor": "**R39 不建，沿用 R17**",
        "label": "跟进单 §21 裁定", "seq": 2}],
      "裁定不建（沿用 R17）；HEAD 上 R39 名下零提交"),
    T("R40", "PARTIAL", [A("dc31a44", "施工", "app/api/v1/intelligence.py"), A("8585315", "并树")],
      [S21(40, "③")], "③ 前端硬编 standard 仍在（写域归 V 前端线）"),
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
    T("R49", "PARTIAL", [A("8680f43", "施工", "app/documents/index_policy.py"), A("c26afda", "并树")],
      [S21(49, "②")], "②「未索引」那张脸 UI 还没有"),
    T("R50", "PARTIAL", [A("090c820", "施工", "scripts/rebuild_index.py"), A("94f7fa1", "并树")],
      [S21(50, "②")], "增量与可续跑在树；「低峰」那半句没挂进排程",
      note="计划书 L468 那句「真零产物只剩 R50」是假账：R50 名下两枚产物提交都在主干"),
    T("R51", "PARTIAL", [A("6833140", "施工", "app/common/stage_timing.py"), A("cef08bf", "并树")],
      [S21(51, "②")], "② 加总误差 <1% 未量；rewrite/reflect 两格插桩后置"),
    T("R52", "PARTIAL", [A("8c888c7", "施工", "scripts/check_airgap_readiness.py"), A("1b84fb2", "闸门自修")],
      [S21(52, "①")], "①②③ 全是墙上事实，E 行已整行移出 V1"),
    T("R141", "LANDED", [A("1cbd164", "并树", "frontend/src/router/lane-choice.js")], [],
      "档位标签第一次真改派工作腿；看板 §4BF 记「R141 达标并树」"),
    T("R142", "LANDED", [A("19761a5", "施工", "tests/test_r142_error_code_table_sync.py"), A("b58a5b9", "并树")],
      [], "契约错误码表机械化对账上岗（并树记 +12 用例）"),
    T("R143", "ZERO", [], [P52(143)],
      "R143 名下全史零提交；它点名的脚本早在 R58 名下就有（`a896cf6`），那一次预跑至今记在 R58③ 真机欠账",
      note="在册无产物：计划书 §5.2 那行今天仍写「待派」"),
    T("R144", "ZERO", [], [S85("业主明令避开 R141", "一")],
      "R144 从没立过单——它是业主建议号里被避开的那一枚，也不在计划书 §5.2 表内",
      note="派工词把 R144 算进在册号是范围错，本账按实列示"),
    T("R145", "LANDED", [A("e2de245", "施工", "scripts/audit_vector_mirror_sets.py"), A("f747109", "并树")],
      [], "向量镜像集合面对账台上岗（并树记 +91 用例）"),
    T("R146", "LANDED", [A("77cd8b4", "施工", "app/trace/spans.py"), A("25a08f0", "并树")],
      [], "cached-token 论述与记账归真（并树记 +16 用例）"),
    T("R253", "PARTIAL", [A("ea2a539", "并树", "tests/test_r253_no_test_rewrites_a_tracked_file.py")],
      [S101("**R253 `ea2a539`**", "二（已结案三枚的对账口径）")],
      "④「同一 HEAD 连跑三次 -n 8 零漂移」在本 HEAD 上仍未满",
      note="主干 `8051897` 已记该格转绿；本账钉在 03beca8，下班重跑会自动翻成 LANDED"),
    T("R254", "LANDED", [A("8f89def", "并树", "app/api/v1/chat.py"), A("c70548a", "R254b 总控补口")],
      [], "六条判据逐条有码有钉（§101.2 记已结案）"),
    T("R255", "LANDED", [A("3bf271d", "并树", "app/common/model_budget.py")], [],
      "窗口与预算同一处推导，撞顶报错自报差额"),
    T("R256", "LANDED", [A("ff0f4ec", "并树", "migrations/0015_dataset_version_scope_columns.sql"),
                         A("d853153", "R256b 总控补口")], [],
      "五条判据逐条对账，④ 首次在隔离 PG 真库跑到底并留凭据"),
    T("R257", "ZERO", [], [S101("**R257 Trace 兜底两笔**（波次二，施工", "一（新立单判据原文）")],
      "R257 名下全史零提交（工作树 be-r257 停在基点 c70548a）"),
    T("R258", "LANDED", [A("6b4f04c", "总控自办", "docs/handoff/2026-09-17-eval-real-run-runbook.md")], [],
      "runbook 三枚假零入册", classes=("文书",),
      note="本单交付物就是那枚运维手册：判据①「产品码或契约」在这里不适用，例外已在账上具名"),
    T("R259", "ZERO", [], [S101("- ① 量具见到", "一（R259 判据原文）")],
      "本 HEAD 上零产物；主干 `67ea193`（并树 R259）不在 03beca8 的祖先链上"),
    T("R260", "ZERO", [], [S101("- ① `frontend/src/components/ChatPanel.vue", "一（R260 判据原文）")],
      "R260 名下全史零提交（工作树 be-r260 停在基点 c70548a）"),
    T("R261", "ZERO", [], [S101("- 判据六条：① 在站点上方插无关行", "一（R261 判据原文）")],
      "本 HEAD 上零产物；主干 `c9ad493`（并树 R261）不在 03beca8 的祖先链上",
      note="`c70548a`/`d853153` 那两笔改账在 R254b/R256b 名下，正是本单要消灭的 path:line 税，不算它的产物"),
]

LEDGER = LEDGER_A + LEDGER_EXTRA


def scan_history(git, rows):
    """按「提交标题里第一枚单号」自动归集主干产物，用来反证 ZERO 那笔账。"""
    scope = set(row["id"] for row in rows)
    attributed = dict((tid, []) for tid in scope)
    catch_up = dict((tid, []) for tid in scope)
    for sha, commit in sorted(git.commits().items()):
        base, suffix = primary_token(commit["subject"])
        if base not in attributed:
            continue
        count = len(product_files(git.files(sha), ("产品码", "契约")))
        if not count:
            continue
        bucket = (catch_up if CATCH_UP_RE.search(commit["subject"]) else attributed)[base]
        bucket.append((sha[:7], count, suffix))
    return attributed, catch_up


def plan_status(quoter, tid):
    try:
        lines, index = quoter.locate({"file": PLAN, "anchor": "> | %s |" % tid})
    except SourceError:
        return None
    return Quoter.cell(lines[index], 3)


def resolve_artifacts(git, row):
    resolved = []
    for art in row["artifacts"]:
        item = dict(art)
        full = git.resolve(art["sha"])
        item["full"] = full
        if full:
            files = git.files(full)
            item["files"] = files
            item["product"] = product_files(files, row["classes"])
            item["ancestor"] = full in git.ancestors()
            item["mention"] = bool(re.search(
                r"(?<![A-Za-z0-9])" + re.escape(row["id"]) + r"[a-z]?(?![0-9A-Za-z])",
                git.message(full)))
        else:
            item["files"] = []
            item["product"] = []
            item["ancestor"] = False
            item["mention"] = False
        resolved.append(item)
    return resolved


def build_rows(git, quoter):
    attributed, catch_up = scan_history(git, LEDGER)
    rows = []
    for spec in LEDGER:
        row = dict(spec)
        row["artifacts_resolved"] = resolve_artifacts(git, row)
        row["gaps_resolved"] = [quoter.quote(gap, row["id"]) for gap in spec["gaps"]]
        row["auto"] = sorted(attributed[row["id"]])
        row["catch_up"] = sorted(catch_up[row["id"]])
        row["plan_status"] = plan_status(quoter, row["id"])
        row["faulted"] = False
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
    failures = []
    for row in rows:
        tid = row["id"]
        classes = "/".join(row["classes"])
        products = [art for art in row["artifacts_resolved"] if art["product"]]
        for art in row["artifacts_resolved"]:
            if art["full"] is None:
                failures.append("C2 %s：证据提交 `%s` 在仓库里根本不存在（引用假账）" % (tid, art["sha"]))
                continue
            if not art["ancestor"]:
                label = "🔴" if row["verdict"] == "LANDED" else "·"
                failures.append("%s C3 %s：证据提交 `%s`（%s）不在 HEAD 祖先链上＝未并树" %
                                (label, tid, art["sha"], art["via"]))
            if not art["mention"]:
                failures.append("C4 %s：`%s` 的提交信息里没有本单号＝张冠李戴" % (tid, art["sha"]))
            if art["expect"] and art["expect"] not in " ".join(art["files"]):
                failures.append("C5 %s：`%s` 没改到点名的落点 `%s`" % (tid, art["sha"], art["expect"]))
        if row["verdict"] == "LANDED":
            if not products:
                failures.append("C6 %s：判 LANDED 却没有一枚证据提交带来%s改动（纯 docs 记账不算）" % (tid, classes))
        elif row["verdict"] == "PARTIAL":
            if not products:
                failures.append("C7 %s：判 PARTIAL 却没有产物 ⇒ 按口径应改判 ZERO" % tid)
            if not row["gaps_resolved"]:
                failures.append("C8 %s：判 PARTIAL 却没点名欠哪条判据（判据原文必须逐字引用，不许转述）" % tid)
        elif row["verdict"] == "ZERO":
            if row["auto"]:
                failures.append("C9 %s：判 ZERO 是假账——自动归集在主干上逮到本号名下产物提交 %s" % (
                    tid, "、".join("`%s`(%d 枚)" % (sha, count) for sha, count, _ in row["auto"])))
            if products:
                failures.append("C10 %s：判 ZERO 却挂了产物提交 `%s`" % (
                    tid, "、".join(art["sha"] for art in products)))
        elif row["verdict"] not in VERDICTS:
            failures.append("C1 %s：判定词「%s」不在三档之内" % (tid, row["verdict"]))
    return failures


def render_head(git, rows, faults):
    out = []
    emit = out.append
    emit("R262 计划书台账归真 · 机器账（只读 git 与工作树；判据原文一律现读现切）")
    if faults:
        emit("!! 本次运行注入故障台账：%s ⇒ 这份输出是反证演示，不是账" % "、".join(sorted(faults)))
    emit("head=%s commits_on_head=%d worktree=%s" % (git.head(), len(git.commits()), git.worktree_state()))
    emit("三档口径：LANDED＝产物在树且无点名欠账；PARTIAL＝产物在树但点名欠判据；ZERO＝HEAD 祖先链上全史零产物")
    emit("归属口径：提交标题里第一枚单号＝该提交的归属号（拆单子号 R26a/R43a/R152 一类按账上具名挂靠，不自动并号）；"
         "标题含 catch up/追平/保活 的只记账不作产物证据")
    emit("产物口径：产品码＝app/frontend/scripts/tests/migrations/deploy/static 与代码类后缀；契约＝docs/api/** 与 migrations/manifest.json")
    emit("")
    emit("## 1. 逐号结论")
    emit("")
    emit("| 号 | 判定 | 证据提交（归属·实改产物枚数） | 在 HEAD 祖先链 | 一句话依据 | 欠账引用 |")
    emit("|---|---|---|---|---|---|")
    for row in rows:
        if row["artifacts_resolved"]:
            evidence = "、".join("`%s`·%s[%d 枚]%s" % (
                art["sha"], art["via"], len(art["product"]), "" if art["ancestor"] else "†")
                for art in row["artifacts_resolved"])
            ancestor = "是" if any(art["ancestor"] for art in row["artifacts_resolved"]) else "—"
        else:
            evidence = "无（全史零产物）"
            ancestor = "—"
        gaps = "、".join("G-%s" % gap["key"] for gap in row["gaps_resolved"]) or "—"
        emit("| %s | **%s** | %s | %s | %s | %s |" % (row["id"], row["verdict"], evidence, ancestor,
                                                      row["why"] or "—", gaps))
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
    return out


def render_tail(git, rows, out):
    emit = out.append
    emit("")
    emit("## 3. 欠账与判据原文（机器从出处逐字切段，非转述）")
    emit("")
    for row in rows:
        for gap in row["gaps_resolved"]:
            emit("- G-%s ｜出处：%s ｜`%s` 第 %d 行（按 LF 计数）｜%s ｜原文：%s" % (
                gap["key"], gap["source"], gap["file"], gap["line"], row["verdict"], gap["quote"]))
    emit("")
    emit("## 4. 计划书 §5.2 那行现在的台账词（只列在册行，订正由人写段落笔）")
    emit("")
    for row in rows:
        if row["plan_status"]:
            emit("- %s ｜台账现词：%s" % (row["id"], row["plan_status"]))
    emit("- 其余在册号在 §5.2 主表里没有状态列——计划书 L468 自己认了这句：这张表**没有结案列**，被抄来抄去会被当成还剩这么多没做")
    emit("")
    emit("## 5. 反查：主干自动归集（专治「零提交」假账）")
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
    emit("## 6. 计数")
    emit("")
    emit("在册 %d 号：LANDED=%d · PARTIAL=%d · ZERO=%d" % (len(rows), counts["LANDED"], counts["PARTIAL"], counts["ZERO"]))
    for verdict in VERDICTS:
        emit("- %s：%s" % (verdict, " ".join(row["id"] for row in rows if row["verdict"] == verdict) or "无"))
    emit("")
    emit("## 7. V1 判据「计划书代码单清零」的距离")
    emit("")
    zeros = [row for row in rows if row["verdict"] == "ZERO"]
    partials = [row for row in rows if row["verdict"] == "PARTIAL"]
    emit("- 读法甲（产物在树即算清）：未清 %d 号：%s" % (len(zeros), " ".join(row["id"] for row in zeros) or "无"))
    emit("- 读法乙（判据全达才算清）：未清 %d 号（PARTIAL %d ＋ ZERO %d）" % (len(zeros) + len(partials), len(partials), len(zeros)))
    for row in partials + zeros:
        gaps = "；".join(gap["quote"] for gap in row["gaps_resolved"]) or row["why"]
        emit("  - %s（%s）差：%s" % (row["id"], row["verdict"], gaps))
    return counts


CHECKLIST = ("C1 判定词只许三档", "C2 证据提交必须存在", "C3 判 LANDED 的证据必须在 HEAD 祖先链上",
             "C4 提交信息必须含本单号", "C5 点名落点必须在该提交实改文件里",
             "C6 LANDED 必须有产品码/契约改动", "C7 PARTIAL 必须有产物",
             "C8 PARTIAL 必须逐字点名欠账", "C9 ZERO 不得被自动归集逮到产物", "C10 ZERO 不得挂产物提交")


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
        rows = build_rows(git, quoter)
        rows = apply_faults(git, rows, faults)
        out = render_head(git, rows, faults)
        counts = render_tail(git, rows, out)
    except SourceError as error:
        print("环境/出处错：%s" % error, file=sys.stderr)
        return 2
    failures = self_checks(rows)
    out.append("")
    out.append("## 8. 自检（这台尺子的牙）")
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
