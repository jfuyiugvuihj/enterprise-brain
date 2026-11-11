# -*- coding: utf-8 -*-
"""R688 常驻牙：五段事件的**生产发点**真在产，段名只认在册字面。

对着的病（总控 10-06 现取，原文见 ``docs/tickets/R688-stage-event-production-leg.md``）：
``app/**`` 里 ``record_stage_event`` 与 ``stage_window`` 只有定义、没有调用点 ⇒ 五段事件从没
被发过，``r631 --window`` 的空输入不是导出器坏了。本件钉三格：

① 一次真生产问答（跑真图、真节点、真 trace 件；只有模型是脚本化的，``LOCAL_MODEL_NAME``
   哨兵口径一字不动）之后，``events.jsonl`` 里每一枚 stage 事件的段名都必须逐字等于
   ``CANONICAL_STAGES`` 的字面，且本单落地的三段各有 >= 1 枚；自造段名在写入口就被拒。
② 发点可指认：段名 -> ``文件::符号`` 由 AST 现读，不抄表、不写行号（AGENTS 行号禁令）。
③ 计时纪律：发点只许站在「没有自己的跨度」的那一段上（一段一枚件，区间互不重叠），
   一枚都不许落进逐片直发的流式腿 —— 那是 ``tests/test_r149_sse_text_pieces.py`` 与
   ``tests/test_r661_trace_journal_hot_path_teeth.py`` 两枚在册钉的地盘。

🔴 段名与发点枚数**一律由 ``stage_emit_points()`` 现读**，本文件不登记死清单：R688 建件那天
rewrite 段确实零枚发点，R695 把 rewrite 接上两条腿之后，那份手抄名单就成了假账。
现在「还没落地的段」= 在册五段减去现读有发点的段（``unlanded_stage_names()``）；
「落地的段各 >= 1 枚」那条仍按图道 ``LANDED_STAGES`` 走，因为它量的是**一次生产问答真发了
什么件**，不是码在不在树上 —— 两件事原先挤在同一格，是 R688 建件时的口径粗糙。
发点宿主拿身份认两种机制（形参 ``config``／同模块挂载后自读），凭据与反证牙在
``tests/test_r707_emit_point_host_account_shapes.py``。
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
from pathlib import Path
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from app.agents import orchestrator
from app.common.stage_timing import (
    CANONICAL_STAGES,
    default_stage_ledger,
    reset_stage_ledger,
)
from app.trace.store import default_trace_store, reset_default_trace_store

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPO_ROOT / "app"
STAGE_EVENT = "stage.finished"

#: 本单在写域内落地的三段（``app/agents/nodes.py`` 里各有可指认的发点）。
LANDED_STAGES = ("classify", "generate", "reflect")


def unlanded_stage_names(root: Path = APP_ROOT) -> tuple[str, ...]:
    """R707 订正：现读「在册但 ``app/**`` 里没有可指认发点」的段名。

    原先这格手抄成 ``("retrieve", "rewrite")``，R695 给 rewrite 上线两条腿之后就过期了；
    谁再补一段，这一格自己跟着变，不用回来改清单。
    """
    return tuple(stage for stage in CANONICAL_STAGES if stage not in stage_emit_points(root))

#: 流式腿的名字：这些宿主里出现 stage 发点 = 计时纪律破了（判据⑤）。
STREAMING_HOSTS = (
    "_ResilientModel",
    "publish_stream_pieces",
    "publish_formed_answer_pieces",
    "publish_formed_reply_for_call",
    "answer_leg_stream_target",
    "StreamPieceMerger",
    "_AnswerPieceTap",
)

#: 闲聊道的问题：``classify_intent`` 判到 chat，直接走 ``respond``。
SMALLTALK_QUESTION = "你好"
#: 问答道的问题：一枚关键字都不命中派工兜底，所以图停在 reflect → synthesize。
QA_QUESTION = "请把上周的销售情况简单说一下"


# ==================== 派生的发点表：段名 -> 文件::符号 ====================


def _defs(tree: ast.AST) -> list[tuple[int, int, str]]:
    """每枚函数/方法定义 ``(起始行, 结束行, 宿主符号名)``，符号名带类前缀。"""
    rows: list[tuple[int, int, str]] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + child.name
                rows.append((child.lineno, child.end_lineno or child.lineno, name))
                visit(child, name + ".")
            elif isinstance(child, ast.ClassDef):
                name = prefix + child.name + ""
                visit(child, name + ".")
            else:
                visit(child, prefix)

    visit(tree, "")
    return rows


def _def_map(tree: ast.AST) -> dict[str, ast.AST]:
    """与 ``_defs`` 同一趟遍历、同一套命名，交回 ``符号名 -> 定义节点``（只登记函数）。

    两把尺必须同名同形：发点表走 ``_defs``，形状表走 ``_def_map``，名字一分叉就各说各话。
    同名断言在 ``tests/test_r707_emit_point_host_account_shapes.py``。
    """
    out: dict[str, ast.AST] = {}

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + child.name
                out[name] = child
                visit(child, name + ".")
            elif isinstance(child, ast.ClassDef):
                name = prefix + child.name + ""
                visit(child, name + ".")
            else:
                visit(child, prefix)

    visit(tree, "")
    return out


def _called_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


#: 宿主拿到本轮身份的两种机制（R695 交出的两条腿）；两条都不通 = 静默失效。
IDENTITY_ARG = "config"
IDENTITY_READERS = ("current_turn_identity",)
IDENTITY_ARMS = ("arm_turn_identity",)


def host_account_shape(site: str, root: Path = APP_ROOT) -> dict:
    """现读一枚发点宿主 ``文件::符号`` 到底怎么拿到本轮身份。

    返回 ``{site, args, mechanism, mechanisms, self_reads, module_arms}``：``mechanism``
    是第一条走通的路（形参 ``config`` 优先），``mechanisms`` 登记全部走通的路。
    两条都不通就是 ``none`` —— 那种发点写的账恒为匿名、恒不落地，调用方必须红。
    """
    relative, _, symbol = site.partition("::")
    tail = relative.split("/", 1)[1] if "/" in relative else relative
    tree = ast.parse((root / tail).read_text(encoding="utf-8"))
    node = _def_map(tree).get(symbol)
    assert node is not None, "发点符号在 %s 里认不出定义：%s" % (relative, symbol)
    args = [a.arg for a in node.args.args + node.args.kwonlyargs]
    self_reads = any(isinstance(call, ast.Call) and _called_name(call.func) in IDENTITY_READERS
                     for call in ast.walk(node))
    module_arms = any(isinstance(call, ast.Call) and _called_name(call.func) in IDENTITY_ARMS
                      for call in ast.walk(tree))
    mechanisms = []
    if IDENTITY_ARG in args:
        mechanisms.append("config")
    if self_reads and module_arms:
        mechanisms.append("armed")
    return {"site": site, "args": args,
            "mechanism": mechanisms[0] if mechanisms else "none",
            "mechanisms": tuple(mechanisms), "self_reads": self_reads,
            "module_arms": module_arms}


def _host_of(rows: list[tuple[int, int, str]], lineno: int) -> str:
    """最深（起始行最大）的那一枚包含关系 = 宿主符号；模块级记为 ``<module>``。"""
    best = ""
    best_start = -1
    for start, end, name in rows:
        if start <= lineno <= end and start > best_start:
            best, best_start = name, start
    return best or "<module>"


#: 记账入口的名字：生产发点必须经由这三枚之一落到 stage 件。
ACCOUNT_WRITERS = ("record_stage_event", "stage_account", "_stage_account")


def stage_emit_points(root: Path = APP_ROOT) -> dict[str, list[str]]:
    """AST 现读 ``app/**`` 里每一枚带字面段名的记账调用点。

    返回 ``{段名: ["文件::符号", ...]}``，路径相对仓库根、坐标一律 ``文件::符号``。
    段名不是字符串字面量的调用（例如 ``stage_account(config, stage=stage)`` 那种转发）
    不算发点 —— 发点要能被指认，就得写得下一个字面段名。
    """
    out: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rows = _defs(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            called = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else "")
            if called not in ACCOUNT_WRITERS:
                continue
            keyword = next((k for k in node.keywords if k.arg == "stage"), None)
            if keyword is None or not isinstance(keyword.value, ast.Constant):
                continue
            if not isinstance(keyword.value.value, str) or not keyword.value.value.strip():
                continue
            rel = path.relative_to(root.parent).as_posix()
            out.setdefault(keyword.value.value, set()).add("%s::%s" % (rel, _host_of(rows, node.lineno)))
    return {stage: sorted(sites) for stage, sites in sorted(out.items())}


# ==================== stage 件的读数 ====================


def journal_lines(path: Path) -> list[dict]:
    """把 ``events.jsonl`` 逐行读成 dict —— 判据① 问的就是这本件里有什么。"""
    if not Path(path).exists():
        return []
    rows = []
    for line in io.open(str(path), encoding="utf-8").read().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def stage_accounts(events: list[dict], *, trace_id: str = "") -> dict[str, list[dict]]:
    """按段名归拢 stage 事件；``trace_id`` 非空时只算这一轮的。"""
    grouped: dict[str, list[dict]] = {}
    for event in events:
        if event.get("event_type") != STAGE_EVENT:
            continue
        if trace_id and event.get("trace_id") != trace_id:
            continue
        name = str((event.get("payload") or {}).get("stage") or "")
        grouped.setdefault(name, []).append(event)
    return grouped


def assert_stage_accounts(
    events: list[dict],
    *,
    trace_id: str = "",
    landed: tuple[str, ...] = LANDED_STAGES,
    unlanded: tuple[str, ...] | None = None,
) -> dict[str, int]:
    """判据① 的可执行版本：段名只认在册字面、落地的段各有 >=1 枚、没落地的段必须零枚。

    每一枚断言都在消息里点名它判的那一段 —— 反证牙（``test_r688_counter_evidence_teeth``）
    靠这一点把「摘掉一段发点」读成「那一段当场红」，而不是读成一句整体的失败。
    """
    if unlanded is None:
        unlanded = unlanded_stage_names()
    grouped = stage_accounts(events, trace_id=trace_id)
    invented = sorted(name for name in grouped if name not in CANONICAL_STAGES)
    assert not invented, (
            "自造段名混进了 stage 件（在册五段 = %s）：%s" % (list(CANONICAL_STAGES), invented))
    counts = {name: len(rows) for name, rows in grouped.items()}
    for stage in landed:
        assert counts.get(stage, 0) >= 1, (
                "判据① 未过：段 %s 在 events.jsonl 里一枚 stage 件都没有（现读各段枚数 %s）"
                % (stage, counts or "{}"))
    for stage in unlanded:
        assert counts.get(stage, 0) == 0, (
                "段 %s 现读枚数不为零（%d）：发点已经上线或本轮真发了件，"
                "R688/R707 的账面得跟着改口径，不许沿用旧账" % (stage, counts.get(stage, 0)))
    return counts


# ==================== 离线夹具：真图 + 脚本化模型 ====================


class Transport:
    """把 ``ChatOpenAI._generate`` 换成脚本答复器：零真模型，产品装配一字不动。

    形状照 ``tests/test_r167_answer_prefix_reuse.py::Transport``（在册正例）：挂普通函数
    而不是绑定方法，langchain 以 ``self._generate(input, ...)`` 调用。答复枚数不够时重复
    最后一枚，所以多轮图不会自己掐死。
    """

    def __init__(self, monkeypatch, replies=()):
        self.captured: list[list] = []
        self._replies = list(replies)
        monkeypatch.setattr(ChatOpenAI, "_generate", self._generate)

    def _generate(self, input=None, stop=None, run_manager=None, **kwargs):  # noqa: A002 - 形参名由 langchain 定
        messages = input if input is not None else kwargs.get("messages")
        self.captured.append(list(messages))
        index = min(len(self.captured) - 1, max(len(self._replies) - 1, 0))
        reply = self._replies[index] if self._replies else AIMessage(content="已作答。")
        return ChatResult(generations=[ChatGeneration(message=reply)])


def _identity() -> dict:
    return {"username": "r688", "role": "clerk", "department": "仓储部"}


def _principal():
    from app.common.identity import Principal

    return Principal.from_user(_identity(), auth_source="agent")


def _config(**extra) -> dict:
    """带认证主体的 config：``ExecutionSpan.active`` 要的是 owner + trace_id。"""
    configurable = dict(_identity())
    configurable["principal"] = _principal()
    configurable.update({
        "thread_id": extra.pop("thread_id", "thread-r688"),
        "request_id": "req-r688",
        "trace_id": "trace-r688",
        "task_id": "task-r688",
    })
    configurable.update(extra)
    return {"configurable": configurable}


@contextlib.contextmanager
def _redirected_journal(tmp_path, monkeypatch):
    """把 append-only 事件件改道到 tmp：一字节都不许落进工作树的 ``data/traces/``。

    形状照 ``tests/test_r649_first_screen_ms_is_measurable_on_the_wire.py::trace_book``。
    orchestrator 在 import 那一刻就把 ``default_trace_store()`` 存进了模块变量，所以那一格
    也必须一起改道，否则 request.* 落旧件、stage.* 落新件，读数会假。
    """
    journal = Path(tmp_path) / "events.jsonl"
    monkeypatch.setenv("TRACE_STORE_PATH", str(journal))
    reset_default_trace_store()
    monkeypatch.setattr(orchestrator, "_trace_store", default_trace_store())
    reset_stage_ledger()
    try:
        yield journal
    finally:
        reset_stage_ledger()
        reset_default_trace_store()


def run_production_round(
    tmp_path,
    monkeypatch,
    question: str,
    *,
    replies=(),
    thread_id: str = "",
) -> dict:
    """走一次生产问答：真编译图、真节点函数、真 trace 件，只有模型是脚本。

    入口用 ``run_orchestrator_result``（队列道，worker 进程用的就是它）：它自己发
    request.started/request.completed，并往 ``configurable`` 里放认证主体 —— 没有主体的
    老 ``run_orchestrator`` 落不进任何跨度，那是「无主不记」的既有规矩，不是本单的新行为。
    """
    transport = Transport(monkeypatch, replies=list(replies))
    with _redirected_journal(tmp_path, monkeypatch) as journal:
        record = orchestrator.run_orchestrator_result(
            question,
            thread_id=thread_id or "thread-r688-%s" % uuid4().hex[:8],
            user={"principal": _principal()},
        )
        events = journal_lines(journal)
    return {
        "record": record,
        "events": events,
        "transport": transport,
        "journal": journal,
        "trace_id": getattr(record, "trace_id", "") or "",
    }


# ==================== 判据①：一次生产问答之后 ====================


def test_the_task_lane_round_lands_stage_accounts_for_every_landed_segment(tmp_path, monkeypatch, offline_ollama_embeddings):
    round_ = run_production_round(
        tmp_path,
        monkeypatch,
        QA_QUESTION,
        replies=[AIMessage(content="上周销售环比上周持平，明细见知识库。")],
    )
    assert str(round_["record"].answer or "").strip(), "答案件没落地，这一轮不算生产问答"
    counts = assert_stage_accounts(round_["events"], trace_id=round_["trace_id"])
    assert counts["classify"] >= 2, counts  # classify_intent + plan（两段各一枚件）
    assert counts["generate"] >= 1, counts
    assert counts["reflect"] >= 1, counts


def test_the_chat_lane_round_lands_a_generate_account_from_respond(tmp_path, monkeypatch, offline_ollama_embeddings):
    round_ = run_production_round(
        tmp_path,
        monkeypatch,
        SMALLTALK_QUESTION,
        replies=[AIMessage(content="你好，我是企业智脑。")],
    )
    assert str(round_["record"].answer or "").strip()
    grouped = stage_accounts(round_["events"], trace_id=round_["trace_id"])
    assert len(grouped.get("generate", [])) >= 1, grouped.keys()
    hosts = {str((row.get("payload") or {}).get("summary") or "") for row in grouped["generate"]}
    assert any("respond" in row for row in hosts), hosts
    assert "classify" in grouped, grouped.keys()


def test_every_landed_stage_event_carries_only_the_canonical_literal(tmp_path, monkeypatch, offline_ollama_embeddings):
    round_ = run_production_round(tmp_path, monkeypatch, QA_QUESTION)
    grouped = stage_accounts(round_["events"], trace_id=round_["trace_id"])
    assert set(grouped) <= set(CANONICAL_STAGES), sorted(grouped)
    for name, rows in grouped.items():
        for event in rows:
            payload = event.get("payload") or {}
            assert payload["stage"] == name
            assert payload["record_kind"] == "stage_windows"
            assert isinstance(payload["duration_ms"], int)
            assert payload["status"] in {"completed", "failed"}
            assert payload["started_at"] and payload["completed_at"]
            assert payload.get("owner_id"), payload


# ==================== 判据① 的另一半：自造段名必须被拒 ====================


def test_a_self_invented_stage_name_is_refused_and_counted(tmp_path, monkeypatch):
    from app.trace.spans import record_stage_event

    with _redirected_journal(tmp_path, monkeypatch) as journal:
        before = default_stage_ledger().failures
        assert record_stage_event(_config(), stage="thinking", duration_ms=12) == {}
        assert journal_lines(journal) == [], "自造段名照样落了件：写入口没有闸"
        assert default_stage_ledger().failures == before + 1
        # 正控：在册字面照写，归一大小写与空格之后仍等于字面本体
        record_stage_event(_config(), stage=" Reflect ", duration_ms=9)
        rows = [event for event in journal_lines(journal) if event["event_type"] == STAGE_EVENT]
        assert len(rows) == 1, rows
        assert rows[0]["payload"]["stage"] == "reflect"


# ==================== 判据③/⑤ 的形状：一段一枚件、不上流式腿 ====================


def test_the_landed_segments_have_named_emit_points_and_no_invented_names():
    points = stage_emit_points()
    assert set(points) <= set(CANONICAL_STAGES), sorted(points)
    for stage in LANDED_STAGES:
        sites = points.get(stage) or []
        assert sites, "段 %s 在 app/** 里没有可指认的发点" % stage
        for site in sites:
            relative, _, symbol = site.partition("::")
            assert ":" not in relative and not symbol.isdigit(), site
            host = (REPO_ROOT / relative).read_text(encoding="utf-8")
            assert symbol.split(".")[0] in host, site


def test_every_emit_point_host_can_reach_the_turn_identity():
    """发点宿主拿不到本轮身份 = 账恒为匿名、恒不落地，那种静默失效必须钉住。

    R707 订正（10-06）：这枚钉原先只认「形参里有 ``config``」**一种**形状，还只解析
    ``app/agents/nodes.py`` 一枚文件的模块级函数；R695 给 chat 腿挂了端点身份
    （``app/trace/spans.py::arm_turn_identity`` ＋ 腿内自读 ``current_turn_identity``）
    并给检索腿加可选形参后，它把合法形状当唯一形状，当场红
    （红句 ``AssertionError: RetrievalPipeline.search``）。两种机制现在都算数，
    两条都不通才红；反证见 ``tests/test_r707_emit_point_host_account_shapes.py``
    （摘掉挂载那一行 ⇒ 那条腿的读数从 ``armed`` 掉回 ``none``）。
    """
    points = stage_emit_points()
    sites = sorted({site for stage_sites in points.values() for site in stage_sites})
    assert sites, "一枚发点都没有"
    shapes = [host_account_shape(site) for site in sites]
    silent = [shape for shape in shapes if shape["mechanism"] == "none"]
    assert not silent, "这些发点宿主既没有 %s 形参，也没有同模块挂载后自读：%s" % (
        IDENTITY_ARG, [shape["site"] for shape in silent])


def test_no_stage_account_sits_on_the_streaming_leg():
    """判据⑤ 的静态那半：发点一枚都不许落在逐片直发的腿上。"""
    points = stage_emit_points()
    hosts = [site.partition("::")[2] for sites in points.values() for site in sites]
    assert hosts
    for host in hosts:
        for forbidden in STREAMING_HOSTS:
            assert forbidden not in host, "%s 站在流式腿里（判据⑤）" % host


def test_one_account_writes_one_event_and_one_sample(tmp_path, monkeypatch):
    from app.trace.spans import stage_account

    with _redirected_journal(tmp_path, monkeypatch) as journal:
        with stage_account(_config(), stage="classify", tier="plan"):
            pass
        rows = [event for event in journal_lines(journal) if event["event_type"] == STAGE_EVENT]
        assert len(rows) == 1, rows
        samples = default_stage_ledger().samples()
        assert [sample.stage for sample in samples] == ["classify"]
        assert samples[0].source == "stage_windows"
        assert samples[0].duration_ms >= 0.0


def test_a_raising_block_still_lands_its_account(tmp_path, monkeypatch):
    from app.trace.spans import stage_account

    with _redirected_journal(tmp_path, monkeypatch) as journal:
        with pytest.raises(ValueError):
            with stage_account(_config(), stage="reflect"):
                raise ValueError("the segment itself failed")
        rows = [event for event in journal_lines(journal) if event["event_type"] == STAGE_EVENT]
        assert len(rows) == 1, rows
        assert rows[0]["payload"]["status"] == "failed"


def test_an_ownerless_block_lands_no_bytes(tmp_path, monkeypatch):
    """「无主不记」是本单继承的规矩，不是新行为：匿名 config ⇒ 件与样本双零。"""
    from app.trace.spans import stage_account

    anonymous = {"configurable": {"thread_id": "t-anon", "request_id": "req-anon", "trace_id": "trace-anon"}}
    with _redirected_journal(tmp_path, monkeypatch) as journal:
        with stage_account(anonymous, stage="classify"):
            pass
        assert journal_lines(journal) == []
        assert default_stage_ledger().samples() == []


def test_the_stage_accounts_do_not_change_the_answer_bytes(tmp_path, monkeypatch, offline_ollama_embeddings):
    """判据⑤ 的另一半：闸关掉只少读数，不许改正文 —— 记账是旁观者。"""
    reply = AIMessage(content="上周销售环比持平，明细见知识库。")
    with_accounts = run_production_round(tmp_path, monkeypatch, QA_QUESTION,
                                         replies=[reply], thread_id="thread-r688-on")
    monkeypatch.setenv("STAGE_TIMING_ENABLED", "0")
    without = run_production_round(tmp_path, monkeypatch, QA_QUESTION,
                                   replies=[reply], thread_id="thread-r688-off")
    assert str(with_accounts["record"].answer) == str(without["record"].answer)
    assert stage_accounts(without["events"], trace_id=without["trace_id"]) != {}