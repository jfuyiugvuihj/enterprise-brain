# -*- coding: utf-8 -*-
r"""R408：账面必须说这棵树今天做的事 —— 两枚 env 模板、两张波次纸、AGENTS.md 那半句。

本件一枚生产码都不碰，它只问三件事，每一件都落在**现算**上（不落"文件里出现过某句话"）：

一、`INDEX_BACKEND` 有没有可抄落点，且抄了之后默认态有没有被动过。
    模板解析出的有效环境（只取未注释的赋值）交给 `app.rag.indexing.read_backend()` 那枚真函数去读
    （它先问 env，再认 `chroma|pgvector`，认不出落回默认），答案必须仍是 `chroma`；模板里那行可抄
    的注释值也必须被同一枚真解析器认下，且等于今天的默认。⇒ 谁把示例值写成 `pgvector`（＝替业主
    翻闸，属越权）当场红；谁把键名写错（`pg_vetcor`，正是 `read_backend()` docstring 自己举的那
    个例子）也当场红 —— 因为它交回的不再是抄写者以为抄进去的那个值。再加一枚：注释里承诺的那条
    通路（compose 用 `env_file:` 把 `deploy/.env.server` 交给进程）由 compose 文件自己现算。

二、两张波次纸说的队列，和树上有没有提交，是不是同一件事。
    队列＝表头同时带「号」与「今天」的那张表；逐枚 R 号到 `git log --all --grep` 现查。
    纸说已并树 ⇒ 那一枚 sha 必须 ① `git cat-file -t` 是 commit ② 是 HEAD 的祖先
    ③ 其标题确实宣称并了这一枚单（拿一枚真实但无关的 sha 洗账躲不过）。
    纸说零提交而树上有提交 ⇒ 红。这一条**会随时间自己变红**：今天有人新写一行「R999 待派」，
    R999 并树的那天本件就喊 —— 那正是本仓事故 #14（同一枚单派两个人，账面记过九次）的形状。

三、AGENTS.md 与计划书 §13 不许把已经治好的量具写成"未派"。
    两枚量具到底治没治，不看任何文档，看它们自己：AST 扫「有没有把一枚候选宽度数字绑到
    ef_search 这个名字上」＋ 现场调用各自的 resolver，与 `pg_store.configured_hnsw_ef_search()`
    比同一个数。账面说已并树治过 ⇒ 那枚 sha 必须真在树上、且真改过**这两枚**脚本。
    🔴 判据一件没改：本件不把任何一格翻绿，也不许翻 `INDEX_BACKEND` 默认。

反证刀（逐把进门取 sha256、出门按字节复原再核 sha 相等，真盘零污染）：
  刀1 模板里那行取消注释写成 `pgvector`        → 钉一当场红（翻默认＝越权）。
  刀2 某枚已并树的单在纸里改回「零提交」        → 钉二当场红（纸与树不等）。
  刀3 两纸文末「作废」摘掉                      → 钉二文末那枚当场红。
  刀4 AGENTS.md 那半句后面塞回「未派」           → 钉三当场红（账面把已治的量具算成欠账）。
  刀5 拿一枚真实但与那枚单无关的 sha 冒充凭据    → 钉二当场红（sha 不宣称这一枚单）。
"""
from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

from app.rag import indexing, pg_store

REPO = Path(__file__).resolve().parents[1]
ENV_TEMPLATES = (REPO / ".env.example", REPO / "deploy" / ".env.server.example")
COMPOSE = REPO / "docker-compose.yml"
WAVE3 = REPO / "docs/handoff/2026-09-26-v2-wave3-dispatch-plan.md"
WAVE4 = REPO / "docs/handoff/2026-09-26-v2-wave4-dispatch-plan.md"
AGENTS = REPO / "AGENTS.md"
PLAN = REPO / "docs/handoff/2026-09-17-pgvector-adoption-plan.md"
GAUGE_A = REPO / "scripts" / "r59c_sandbox_corpus.py"
GAUGE_B = REPO / "scripts" / "r59_recall_compare.py"
GAUGES = (GAUGE_A, GAUGE_B)

KNOB = "INDEX_BACKEND"
VOID = "作废"
MERGED = "已并树"
ZERO = "零提交"
#: 派工面上一句「这一格还没人做」的说法。命中的那一格里点到的每一枚 R 号都得带今天的状态。
#: 为什么认这些**形状**而不是这些**词**：本仓「无主」还兼着一职 —— 数据行没有 owner（
# `data.py` 那句「同一把无主口径」），把它一律当派工承诺会把判据泡成噪声。所以只认
# 无主＋（可占／可改／可投／逗号短语）这一族，以及「排在 R<n> 之后」这种拿单号当闸门的说法。
DISPATCH_PATTERNS = (
    r"无主[，、]",
    r"无主可\S{0,3}",
    r"待派",
    r"待投",
    r"槽一空就投",
    r"施工中",
    r"候选",
    r"[排等]\s*`?\*{0,2}R\d+",
)
#: 说一枚在册量具仍然欠着的说法。
UNASSIGNED_WORDS = ("未派", "待派", "无主")
#: 认一句「未派」讲的到底是不是这两枚量具。
GAUGE_WORDS = ("量具", "窄档", "ef_search", "候选宽度", GAUGE_A.name, GAUGE_B.name)
SHA_TOKEN = re.compile(r"\b[0-9a-f]{7,12}\b")
MERGE_WORD = "并树"


# ------------------------------------------------------------------ git：现算，不抄任何纸


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ("git", *args), cwd=str(REPO), capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )


def declared_tickets(subject: str) -> list[str]:
    """一枚提交标题**宣称并了**哪几枚单。只认标题前缀，不认正文里的引用。

    「R341 并树（施工 …）：…」「并树 R409（施工 …）」「R353 + R354 并树…」「R306 第二棒并树…」
    都算；「总控落笔：… R337 `aefa3ce` …」不算 —— 那只是记账时提到别人的单。
    """
    if MERGE_WORD not in subject:
        return []
    if subject.startswith(MERGE_WORD):
        head = subject.split("（")[0]
    else:
        head = subject.split(MERGE_WORD)[0].split("：")[0]
    return re.findall(r"R\d+", head)


@lru_cache(maxsize=None)
def merged_commits(ticket: str) -> tuple:
    """`git log --all --grep=<单号>` 现查，只留真正宣称并了这枚单的提交。"""
    out = _git("log", "--all", "--grep=" + ticket,
               "--format=%h\x1f%ad\x1f%s", "--date=format:%Y-%m-%d").stdout
    hits = []
    for line in out.splitlines():
        parts = line.split("\x1f", 2)
        if len(parts) != 3:
            continue
        sha, day, subject = parts
        if ticket in declared_tickets(subject):
            hits.append((sha, day, subject))
    return tuple(hits)


def merge_lie(ticket: str, sha: str) -> str | None:
    """这枚 sha 能不能替这枚单作证。返回失败理由，None 表示作证成立。"""
    kind = _git("cat-file", "-t", sha)
    if kind.returncode != 0 or kind.stdout.strip() != "commit":
        return "git cat-file -t %s => %s（不是 commit，事故 #63 那一族）" % (
            sha, kind.stdout.strip() or "MISSING")
    if _git("merge-base", "--is-ancestor", sha, "HEAD").returncode != 0:
        return "%s 不是 HEAD 的祖先 ⇒ 它没在这条线上并树" % sha
    own = declared_tickets(_git("log", "-1", "--format=%s", sha).stdout.strip())
    if ticket not in own:
        return "%s 的标题宣称的是 %s，替 %s 作不了证" % (sha, own or "Nothing", ticket)
    return None


# ------------------------------------------------------------------ 纸：队列表


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _cells(line: str) -> list[str]:
    body = line.strip()
    if not body.startswith("|"):
        return []
    return [c.strip() for c in body.strip("|").split("|")]


def has_dispatch_promise(unit: str) -> bool:
    return any(re.search(pattern, unit) for pattern in DISPATCH_PATTERNS)


def queue_rows(text: str) -> list[dict]:
    """表头同时带「号」与「今天」的那张表 ⇒ 队列行；带 arity 记录列数漂移。"""
    rows = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        head = _cells(lines[i])
        id_col = next((k for k, c in enumerate(head) if c.startswith("号")), None)
        now_col = next((k for k, c in enumerate(head) if c.startswith("今天")), None)
        if head and id_col is not None and now_col is not None:
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = _cells(lines[j])
                rows.append({
                    "id_cell": cells[id_col] if len(cells) > id_col else "",
                    "status_cell": cells[now_col] if len(cells) > now_col else "",
                    "line": j + 1,
                    "line_text": lines[j],
                    "arity": None if len(cells) == len(head) else (
                        "第 %d 行列数 %d != 表头 %d" % (j + 1, len(cells), len(head))),
                })
                j += 1
            i = j
        else:
            i += 1
    return rows


# ------------------------------------------------------------------ 钉一：env 模板与真函数


def assignments(text: str) -> dict[str, str]:
    """模板里**未注释**的赋值 —— 一台机器真按这份文件配起来时它拿到什么。"""
    out = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        out[name.strip()] = value.strip()
    return out


def copyable_knob_lines(text: str) -> list[str]:
    """可抄落点：处于注释态、形状就是 `# INDEX_BACKEND=<值>` 的那些行。"""
    return re.findall(r"^#\s*" + KNOB + r"\s*=\s*(\S+)\s*$", text, re.M)


@pytest.mark.parametrize("template", ENV_TEMPLATES, ids=lambda p: p.name)
def test_the_shipped_templates_still_answer_the_legacy_engine(template, monkeypatch):
    """模板解析出的有效环境交给真函数读，答案必须仍是今天的 chroma。

    走的是 `read_backend()` 那条 env 优先的腿，不是正则：把示例值取消注释写成 `pgvector`，
    这一枚当场红（翻默认是业主动作，执行层越权）。
    """
    declared = assignments(_read(template))
    monkeypatch.delenv(KNOB, raising=False)
    for name, value in declared.items():
        monkeypatch.setenv(name, value)

    assert indexing.read_backend() == indexing.INDEX_BACKEND_DEFAULT
    assert indexing.pgvector_reads_enabled() is False
    #: 反证的另一半：不许有人用「改代码默认」来满足这一枚钉。
    assert indexing.INDEX_BACKEND_DEFAULT == "chroma"


@pytest.mark.parametrize("template", ENV_TEMPLATES, ids=lambda p: p.name)
def test_an_operator_can_copy_one_line_and_it_keeps_todays_default(template, monkeypatch):
    """两枚模板各得有一行能抄；抄进去的值要被真解析器认下，且等于今天的默认。"""
    text = _read(template)
    values = copyable_knob_lines(text)
    assert values, (
        "%s 里没有一行 INDEX_BACKEND 可抄 ⇒ 业主翻默认时只能凭记忆写键名，"
        "而写错一个字母的代价 read_backend() 的 docstring 自己就举了例子" % template.name)
    for value in values:
        monkeypatch.setenv(KNOB, value)
        answered = indexing.read_backend()
        assert answered == value, (
            "%s 里那行可抄的值 %r 根本不是真解析器认得的拼法：抄进去读到的是 %r" % (
                template.name, value, answered))
        assert value == indexing.INDEX_BACKEND_DEFAULT, (
            "%s 那行可抄的示例值是 %r，今天的默认是 %r ⇒ 示例面不许长成一台已经切读的机器" % (
                template.name, value, indexing.INDEX_BACKEND_DEFAULT))
    live = assignments(text).get(KNOB)
    assert live in (None, indexing.INDEX_BACKEND_DEFAULT), (
        "%s 把 %s=%s 放在了生效位（未注释），示例文件替这台机器改了默认态" % (template.name, KNOB, live))


def test_the_compose_path_the_comment_promises_reaches_the_process():
    """注释承诺「写进 deploy/.env.server 就够了」：这一句由 compose 文件自己现算。

    它成立，模板里那行才算落点；不成立的话本单写进去的就是第二张假账。
    """
    doc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8-sig"))
    for service in ("backend", "worker", "scheduler"):
        body = doc["services"][service]
        handed = [str(p) for p in (body.get("env_file") or [])]
        assert "deploy/.env.server" in handed, (
            "%s 不再从 deploy/.env.server 取环境（它拿到的是 %r）⇒ 模板里那句承诺对它不成立了"
            % (service, handed))
        assert KNOB not in (body.get("environment") or {}), (
            "%s 的 environment: 里立了第二处 %s，env_file 那条路会被它盖掉" % (service, KNOB))
    assert KNOB not in COMPOSE.read_text(encoding="utf-8"), (
        "compose 里出现了 INDEX_BACKEND：本单写域不含 compose 四枚，这算越界")


# ------------------------------------------------------------------ 钉二：两张波次纸


@pytest.mark.parametrize("paper", (WAVE3, WAVE4), ids=lambda p: p.name)
def test_a_void_stamp_sits_where_the_next_shift_will_read_it(paper):
    """文末同屏可见「作废」。这一格红＝下一班又照着过期纸给同一枚单派第二个人。"""
    tail = "\n".join(_read(paper).splitlines()[-30:])
    assert VOID in tail, "%s 文末 30 行里没有「作废」二字" % paper.name


@pytest.mark.parametrize("paper", (WAVE3, WAVE4), ids=lambda p: p.name)
def test_every_queued_ticket_carries_a_state_derived_from_git(paper):
    """队列里每一枚都带今天的状态，且状态与 `git log --all --grep` 的现查逐枚相符。"""
    rows = queue_rows(_read(paper))
    assert rows, "%s 里没有一张带「今天」列的队列表 ⇒ 队列根本没有今天状态" % paper.name
    problems = [r["arity"] for r in rows if r["arity"]]
    for row in rows:
        tickets = re.findall(r"R\d+", row["id_cell"])
        if not tickets:
            problems.append("第 %d 行的「号」格里没有 R 号：%s" % (row["line"], row["id_cell"][:40]))
            continue
        status = row["status_cell"]
        row_shas = SHA_TOKEN.findall(status)
        #: 今天栏里引别枚单的并树凭据是允许的，但那枚单必须是这一行自己点到过的。
        named = set(tickets) | set(re.findall(r"R\d+", row["line_text"]))
        for ticket in tickets:
            hits = merged_commits(ticket)
            if hits:
                shas = {s for s, _, _ in hits}
                if MERGED not in status:
                    problems.append("%s 已并树（%s @%s），第 %d 行的今天栏没写「%s」：%s" % (
                        ticket, sorted(shas)[0], hits[0][1], row["line"], MERGED, status[:60]))
                if not row_shas:
                    problems.append("%s 写了「%s」却没给 sha，第 %d 行：%s" % (
                        ticket, MERGED, row["line"], status[:60]))
                for sha in row_shas:
                    if sha in shas:
                        continue
                    others = {s for t in named if t != ticket for s, _, _ in merged_commits(t)}
                    if sha in others:
                        continue
                    why = merge_lie(ticket, sha)
                    if why:
                        problems.append("第 %d 行 %s：%s" % (row["line"], ticket, why))
                if ZERO in status:
                    problems.append("%s 树上已有提交，第 %d 行的今天栏还写着「%s」" % (
                        ticket, row["line"], ZERO))
            else:
                if ZERO not in status:
                    problems.append("%s 现查零提交（git log --all --grep=%s 空读数），第 %d 行没写「%s」：%s" % (
                        ticket, ticket, row["line"], ZERO, status[:60]))
                if MERGED in status:
                    problems.append("%s 零提交，却被第 %d 行写成「%s」" % (ticket, row["line"], MERGED))
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("paper", (WAVE3, WAVE4), ids=lambda p: p.name)
def test_no_line_promises_a_slot_the_tree_already_used(paper):
    """任何一行既写「还没人做」（无主/待派/施工中/候选…）又点着 R 号 ⇒ 那一行每一枚单都要有凭据。

    这是会随时间自己变红的那一枚：新添一行「R999 待派」，R999 并树当天本件红。
    """
    problems = []
    for number, line in enumerate(_read(paper).splitlines(), start=1):
        #: 表格按格子取，散文按整行取 —— 承诺写在哪个格子里，那个格子的单号才要凭据。
        units = _cells(line) if line.strip().startswith("|") else [line]
        tickets = []
        for unit in units:
            if has_dispatch_promise(unit):
                tickets.extend(re.findall(r"R\d+", unit))
        for ticket in sorted(set(tickets)):
            hits = merged_commits(ticket)
            if not hits:
                if ZERO not in line:
                    problems.append("第 %d 行 %s 零提交却写着派工词，且没标「%s」：%s" % (
                        number, ticket, ZERO, line.strip()[:80]))
                continue
            if not any(sha in line for sha, _, _ in hits):
                promise = [p for p in DISPATCH_PATTERNS if re.search(p, line)][0]
                problems.append("第 %d 行还在说「%s」，而 %s 早已并树（%s @%s），整行没有它的 sha：%s" % (
                    number, promise, ticket, sorted(s for s, _, _ in hits)[0],
                    hits[0][1], line.strip()[:90]))
    assert not problems, "\n".join(problems)


# ------------------------------------------------------------------ 钉三：量具那半句


def self_carried_widths(path: Path) -> list[str]:
    """AST 扫：这枚脚本有没有把一枚候选宽度数字绑到 ef_search 这个名字上。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, int) and "ef_search" in (node.arg or ""):
                found.append("%s=%s @L%d" % (node.arg, node.value.value, node.lineno))
        if isinstance(node, ast.FunctionDef):
            names = [a.arg for a in node.args.args]
            offset = len(names) - len(node.args.defaults)
            for k, default in enumerate(node.args.defaults):
                arg = names[offset + k]
                if isinstance(default, ast.Constant) and isinstance(default.value, int):
                    if "ef_search" in arg or node.name.endswith("ef_search"):
                        found.append("%s() 的 %s 默认 %s @L%d" % (node.name, arg, default.value, node.lineno))
    return found


def load_gauge(path: Path):
    name = "_r408_" + path.stem
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, str(path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def gauge_follows_the_true_source(path: Path) -> tuple[bool, str]:
    """量具今天踩在哪一档：现场调用它自己的 resolver，与真源比，再看它自不自带数字。"""
    module = load_gauge(path)
    resolver = (getattr(module, "resolve_probe_ef_search", None)
                or getattr(module, "resolve_ef_search", None))
    assert resolver is not None, "%s 里找不到现场取档的那枚函数" % path.name
    got = resolver()
    width = got[0] if isinstance(got, tuple) else got
    source = pg_store.configured_hnsw_ef_search()
    carried = self_carried_widths(path)
    return (width == source and not carried), (
        "%s() => %s｜真源 configured_hnsw_ef_search() => %s｜自带宽度 => %s" % (
            resolver.__name__, width, source, carried or "无"))


def test_the_two_registered_gauges_stand_on_the_true_source_today():
    """`scripts/r59c_sandbox_corpus.py` 与 `scripts/r59_recall_compare.py` 现读与读腿同宽。"""
    assert pg_store.configured_hnsw_ef_search() == pg_store.HNSW_EF_SEARCH_DEFAULT
    for path in GAUGES:
        ok, reading = gauge_follows_the_true_source(path)
        assert ok, "%s 没有站在真源上：%s" % (path.name, reading)


def segments(text: str) -> list[str]:
    """把账面切成「一句一口气」的段：换行、句号、分号都算断点。

    为什么按段而不是 ±200 字的窗口：本仓的账面一行能有三千字，窗口会把隔壁那一格的
    「量具/窄档」拽进来，于是任何一句未派都能被判成在说这两枚量具 —— 那不是判据，是噪声。
    """
    parts = []
    for line in text.splitlines():
        parts.extend(re.split(r"[。；]", line))
    return [p for p in parts if p.strip()]


def unassigned_gauge_claims(text: str) -> list[str]:
    """每一处「未派/待派/无主」，看它**所在那一段**讲的是不是这两枚量具。"""
    claims = []
    for seg in segments(text):
        if not any(word in seg for word in UNASSIGNED_WORDS):
            continue
        if any(word in seg for word in GAUGE_WORDS):
            claims.append("「%s」← %s" % (
                "/".join(w for w in UNASSIGNED_WORDS if w in seg), seg.strip()[:160]))
    return claims


def gauge_fix_claims(text: str) -> list:
    """账面里「R<n> 并树 <sha> 治了这两枚量具」那一类凭据，按段取，跨段不算。"""
    found = []
    for seg in segments(text):
        if not any(g.name in seg for g in GAUGES):
            continue
        for match in re.finditer(r"(R\d+)[^，,。；)]{0,40}?并树[^0-9a-f]{0,3}([0-9a-f]{7,40})", seg):
            found.append((match.group(1), match.group(2)))
    return found


def test_agents_md_does_not_owe_a_gauge_the_tree_already_fixed():
    """AGENTS.md 那半句不许回潮：量具已跟真源同宽，账面就不许再把它们记成欠账。"""
    claims = unassigned_gauge_claims(_read(AGENTS))
    assert not claims, "AGENTS.md 把已经治好的量具写成未派：\n" + "\n".join(claims)


def test_plan_section_13_does_not_owe_a_gauge_the_tree_already_fixed():
    """计划书 §13 同一条：改口后 `rg -n 未派` 不许再把 R393 治过的脚本算作未派。"""
    text = _read(PLAN)
    marker = "## 13."
    assert marker in text, "计划书里没有 §13"
    claims = unassigned_gauge_claims(text[text.index(marker):])
    assert not claims, "计划书 §13 把已经治好的量具写成未派：\n" + "\n".join(claims)


def test_the_fix_the_paper_names_is_a_real_commit_that_touched_both_gauges():
    """纸说「已由 R<n> 并树 <sha> 治过」时，那枚 sha 必须真在树上、且真改过这两枚脚本。"""
    claims = gauge_fix_claims(_read(AGENTS))
    assert claims, (
        "AGENTS.md 说这两枚量具治好了，却没在同一句里给出「R<n> 并树 <sha>」的凭据（须与 %s 同段）"
        % GAUGE_A.name)
    for ticket, sha in claims:
        lie = merge_lie(ticket, sha)
        assert lie is None, lie
    files = _git("show", "--name-only", "--format=", sha).stdout.splitlines()
    for gauge in GAUGES:
        rel = gauge.relative_to(REPO).as_posix()
        assert rel in files, "%s 没有改过 %s，它治不了这一格" % (sha, rel)
