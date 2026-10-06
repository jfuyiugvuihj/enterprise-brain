# -*- coding: utf-8 -*-
"""R709 · 带表提问不许被 document_terms 否决：data_filename 必须进路由，可见集不许退化

病形一手现读（凭据纸 docs/testing/r709-2026-10-06.md 第一节）：问句「按月份统计报销金额，
并画一张柱状图」里 data_terms 命中「统计」、document_terms 命中「报销」，而
app/api/v1/chat.py::_should_use_data_context 交回 False；app/api/v1/chat.py::ask 曾拿这同一枚
返回值同时管两件事 —— 既管「要不要把问句改写成只走数据工具」（＝要不要额外检索文档），
又管「点名的数据集进不进 configurable」。后者被否决之后连带两处退化：
app/agents/orchestrator.py::route_main 的 has_data 读成假（分析档地板不补 Data 腿），
app/agents/tools.py::_authorized_dataset_files 走不到选中支（退化成逐条放行后的全量可见集）。

本件钉五格，每条都可失败：
  1) 判据 1 —— 取证：命中哪枚词由本件 ast 现读函数体里的 document_terms 字面量算出；否决的
     落点由 ask 的源码现读（守卫换名之后那枚谓词在 ask 里只剩一处调用）；
  2) 判据 2 —— 路由改口：离线驱动一次 /api/v1/ask（/chat 压根没有工作腿，见凭据纸 §五），
     终态 done 件里 Data 腿读数在位（钉 data_filename 那一格，不钉「答复里好像有数字」）；
  3) 判据 2 的另一半 —— document_terms 只影响「要不要额外检索文档」：含制度词时问句不被改写
     成「请仅使用数据分析工具」，纯数据问句照旧改写；分析档地板那一格由**真** route_main 判；
  4) 判据 3 —— 可见集不退化：台账里两枚都看得见时，只算点名的那一枚；
  5) 🔴 判据 3 的反证牙 —— 点名一枚无权访问的文件：必须走在册错误码那一支并点名那枚码，
     不许静默放宽回可见集（改前那一形恰好就是静默放宽：名字被否决 ⇒ 整张可见表都算了）。

全程离线：假会话、假缓存、假编排线程，Data 腿用本仓在册的 app/agents/nodes.py::_OfflineModel
（conftest 把 LOCAL_MODEL_NAME 关死），一发真模型都不打、不起服务、不动容器、不碰真库；
数据集台账落 tmp_path（口径照 tests/test_r178_dataset_visibility_faces.py 与
tests/test_r703_analysis_lane_sees_the_dataset.py 的在册写法）。
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import re
from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from app.agents import evidence, nodes, orchestrator, tools
from app.agents.contracts import Principal
from app.agents.planner import build_task_plan
from app.storage.sessions import SessionRegistry

DEPT = "r709-报销测试部"
SIBLING_DEPT = "r709-销售部"
FOREIGN_DEPT = "r709-人力资源部"

NAMED_TABLE = "报销明细表.csv"
SIBLING_TABLE = "销售明细表.csv"
FOREIGN_TABLE = "薪酬明细表.csv"

#: 走查原题（R703 凭据纸 §一）：document_terms 命中「报销」，data_terms 命中「统计」。
QUESTION = "按月份统计报销金额，并画一张柱状图"
#: 只含制度词的那枚问法：判据 2 要的正是「带着表问制度」这一形。
POLICY_QUESTION = "住宿费用通常按什么标准报销？超过标准需要准备哪些材料？"
#: 纯数据问法（不含任何制度词）：document_terms 唯一还管着的那一格——要不要改写问句。
DATA_ONLY_QUESTION = "各部门金额最高、最低各是多少，差距多大"

MONTHS = ("2026-01", "2026-02", "2026-03")
#: 只在点名表里出现的标记词；另一枚只在未点名的可见表里。可见集一旦退化，后者就会漏进终态。
NAMED_TOKEN = "R709-NAMED-ONLY"
SIBLING_TOKEN = "R709-SIBLING-ONLY"


# -------------------------------------------------------------------- 夹具


def _table_text(token: str) -> str:
    """三列 × 三个月的小表；行数与列数是钉得住的读数（📁 那一行的形状）。"""
    lines = ["备注,金额,发生月份"]
    for index, month in enumerate(MONTHS, start=1):
        lines.append(f"{token}-{index},{index}00,{month}")
    return "\n".join(lines) + "\n"


def _registry(monkeypatch, tmp_path, slug: str):
    """一枚用例一座临时台账（台账里文件名唯一，共用会互相顶掉）。"""
    from app.storage import datasets as dataset_storage
    from app.storage.datasets import DatasetRegistry

    registry = DatasetRegistry(root=tmp_path / slug, metadata_path=tmp_path / (slug + "-meta.json"))
    monkeypatch.setattr(dataset_storage, "dataset_registry", registry)
    return registry


def _register(registry, filename: str, *, department: str) -> None:
    token = NAMED_TOKEN if filename == NAMED_TABLE else SIBLING_TOKEN
    path = registry.root / filename
    path.write_text(_table_text(token), encoding="utf-8-sig")
    registry.register(
        path,
        principal=Principal.from_user(
            {
                "id": f"u-owner-{department}",
                "username": f"owner-{department}",
                "role": "manager",
                "department": department,
            }
        ),
        classification="1",
    )


def _principal(*, department: str = DEPT, role: str = "manager") -> Principal:
    return Principal.from_user(
        {
            "id": f"u-{role}-{department}",
            "username": f"{role}-{department}",
            "role": role,
            "department": department,
        }
    )


def _http_request(principal: Principal):
    return type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": principal.username})()},
    )()


# -------------------------------------------------------------------- 真 Data 腿


def _run_data_leg(config: dict, message: str) -> str:
    """生产 Data 腿那一格（同一枚 DATA_PROMPT、同两枚工具），模型换成本仓在册的假腿。"""
    graph = create_react_agent(
        nodes._OfflineModel(),
        [tools.analyze_data, tools.query_data],
        prompt=orchestrator.DATA_PROMPT,
    )
    result = graph.invoke({"messages": [HumanMessage(content=message)]}, config=config)
    for row in reversed(result.get("messages", [])):
        if getattr(row, "content", "") and not getattr(row, "tool_calls", None):
            return str(row.content)
    return ""


def _dispatch_workers(config: dict, message: str) -> list[str]:
    """真跑 app/agents/orchestrator.py::route_main，读它这一轮到底派了哪几条腿。"""
    state = {
        "messages": [HumanMessage(content=message)],
        "plan": build_task_plan(message),
        "worker_results": {},
    }
    routed = orchestrator.route_main(state, config)
    if not isinstance(routed, list):
        return []
    return [str(getattr(item, "node", item)) for item in routed]


def _fake_stream(captured: dict[str, Any], *, probe_dispatch: bool = False):
    """替掉 run_with_stream：configurable 按真件同一口径拼，然后**真跑** Data 腿。

    拼法逐格照 app/agents/orchestrator.py::run_with_stream（thread_id + **user + 三枚 id，
    声明档位走 DECLARED_LANE_KEY），证据袋那一格照
    app/agents/orchestrator.py::_make_worker_wrapper 的 child_conf —— 本件不发明第三份形状，
    否则钉的只是本件的夹具而不是生产道。
    """

    def stream(user_message, *, thread_id, user=None, request_id=None, trace_id=None, task_id=None, **kwargs):
        configurable: dict[str, Any] = {
            "thread_id": thread_id,
            **(user or {}),
            "request_id": request_id,
            "trace_id": trace_id,
            "task_id": task_id,
        }
        declared = str(kwargs.get("declared_lane") or "")
        if declared:
            configurable[nodes.DECLARED_LANE_KEY] = declared
        bag = evidence.new_evidence_bag()
        configurable["evidence_bag"] = bag
        configurable["worker"] = "data"
        config = {"configurable": configurable}

        captured["user_message"] = user_message
        captured["user"] = dict(user or {})
        captured["configurable"] = dict(configurable)
        captured["bag"] = bag
        captured["has_data_filename"] = "data_filename" in configurable
        if probe_dispatch:
            captured["dispatch"] = _dispatch_workers(config, user_message)

        answer = _run_data_leg(config, user_message)
        agent_results = {
            "data": {
                "worker": "data",
                "status": "success",
                "answer": answer,
                "evidence": [item.model_dump() for item in evidence.evidence_from_bag(bag)],
            }
        }
        state = {
            "messages": [],
            "worker_results": {"data": answer},
            "agent_results": agent_results,
            "final_answer": answer,
        }
        return iter([state])

    return stream


def _patch_offline(monkeypatch, tmp_path, fake_stream):
    """把 /ask 摘成离线件：假会话、假缓存、假编排；模型那一腿由 _OfflineModel 顶。"""
    from app.api.v1 import chat

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_a, **_k: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_a, **_k: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _sid, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}))
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.agents.orchestrator.check_interrupt", lambda _tid: None)
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))
    return chat


async def _consume(response) -> str:
    parts = []
    async for chunk in response.body_iterator:
        parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
    return "".join(parts)


def _drive_ask(
    monkeypatch,
    tmp_path,
    *,
    question: str,
    data_filename: str,
    principal: Principal,
    slug: str,
    lane: str = "",
    probe_dispatch: bool = False,
):
    """进程内打一次 /api/v1/ask，交回 (SSE 正文, 假编排收到的那一格)。"""
    captured: dict[str, Any] = {}
    chat = _patch_offline(monkeypatch, tmp_path, _fake_stream(captured, probe_dispatch=probe_dispatch))
    request = chat.AskRequest(
        message=question,
        session_id=f"r709-{slug}",
        data_filename=data_filename,
        lane=lane,
    )
    response = asyncio.run(chat.ask(request, http_request=_http_request(principal)))
    return asyncio.run(_consume(response)), captured


def _events(body: str) -> list[tuple[str, dict]]:
    pairs: list[tuple[str, dict]] = []
    name = None
    for line in body.splitlines():
        if line.startswith("event: "):
            name = line.removeprefix("event: ").strip()
        elif line.startswith("data: ") and name:
            pairs.append((name, json.loads(line.removeprefix("data: "))))
            name = None
    return pairs


def _done_frame(body: str) -> dict:
    matches = [data for name, data in _events(body) if name == "done"]
    assert len(matches) == 1, f"一轮应恰好一枚 done 帧，实际 {len(matches)} 枚"
    return matches[0]


def _denial_codes(captured: dict[str, Any]) -> list[str]:
    """本轮证据袋里数据集闸落下的码（口径照 tests/test_r178_dataset_visibility_faces.py）。"""
    return [
        str(item["error_code"])
        for item in captured["bag"].get("tool_statuses", [])
        if item.get("tool") == tools._DATASET_GATE and item.get("error_code")
    ]


# ==================== 判据 1 · 先取证：命中哪枚词、否决落在哪两行之间 ====================


def test_the_document_term_that_vetoes_the_walkthrough_question() -> None:
    """现读 _should_use_data_context 函数体里的 document_terms 字面量，算出命中的是哪枚词。

    词表不手抄：从源码 ast 取。走查那道原题只命中一枚制度词（报销），data_terms 那边命中
    「统计」——两枚同时命中时旧形状是**制度词一票否决**，点名文件因此进不了路由。
    """
    from app.api.v1 import chat

    tree = ast.parse(inspect.getsource(chat._should_use_data_context))
    tuples: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Tuple):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            values = [element.value for element in node.value.elts if isinstance(element, ast.Constant)]
            for name in names:
                tuples[name] = tuple(values)
    assert {"document_terms", "data_terms"} <= set(tuples), tuples

    document_hits = [term for term in tuples["document_terms"] if term in QUESTION.lower()]
    data_hits = [term for term in tuples["data_terms"] if term in QUESTION.lower()]
    assert document_hits == ["报销"], document_hits
    assert "统计" in data_hits, data_hits
    # 收窄之后的职责：这枚谓词照旧否决「只走数据工具」那一格改写（判据 2 后半段要的就是它
    # 还管着文档腿），但它不再持有对点名文件的否决权（下一枚件钉那一格）。
    assert not chat._should_use_data_context(QUESTION, NAMED_TABLE)


def test_the_veto_no_longer_holds_the_named_dataset() -> None:
    """否决的落点：app/api/v1/chat.py::ask 里 user_ctx["data_filename"] 那一格的守卫。

    结构证据，可失败：改前那一格与「要不要改写问句」共用同一枚谓词（ask 源码里
    _should_use_data_context 出现两枚），改后只剩一处调用，data_filename 的守卫换成
    app/api/v1/chat.py::_named_dataset_must_travel —— 它只看点没点名。
    """
    from app.api.v1 import chat

    source = inspect.getsource(chat.ask)
    assert source.count("_should_use_data_context(") == 1, source.count("_should_use_data_context(")
    guard = re.search(
        r"if [^\n]*_named_dataset_must_travel\(request\.data_filename\):\r?\n"
        r"\s+user_ctx = user_ctx or \{[^\n]*\}\r?\n"
        r'\s+user_ctx\["data_filename"\] = request\.data_filename',
        source,
    )
    assert guard is not None, "点名文件的守卫不是那枚只看点名的谓词：本单的路由改口没落地"
    # 🔴 反证：谓词交回 False 也必须放行点名文件 —— 两格判据不同源，把守卫换回旧谓词即红。
    assert not chat._should_use_data_context(QUESTION, NAMED_TABLE)
    assert chat._named_dataset_must_travel(NAMED_TABLE)
    assert not chat._named_dataset_must_travel("")
    assert not chat._named_dataset_must_travel("   ")


# ==================== 判据 2 · 路由改口：终态件里 Data 腿读数在位 ====================


def test_named_dataset_reaches_the_terminal_frame_despite_document_terms(monkeypatch, tmp_path) -> None:
    """带表 + 问句含制度词 ⇒ 终态 done 件必须读得出「这一轮真算了点名的那一份」。

    改前：data_filename 被否决 ⇒ _authorized_dataset_files 退化成全量可见 ⇒ 台账里两枚都算了
    ⇒ terminal_data_filename 对多枚交空串 ⇒ done 件里那一格整格缺席。判据钉的是那一枚读数，
    不是「答复里好像有数字」。
    """
    registry = _registry(monkeypatch, tmp_path, "terminal")
    _register(registry, NAMED_TABLE, department=DEPT)
    _register(registry, SIBLING_TABLE, department=SIBLING_DEPT)

    body, captured = _drive_ask(
        monkeypatch,
        tmp_path,
        question=QUESTION,
        data_filename=NAMED_TABLE,
        principal=_principal(role="admin"),
        slug="terminal",
    )

    assert captured["has_data_filename"], "点名的文件没进 configurable：路由那一半又把它否决了"
    assert captured["configurable"].get("data_filename") == NAMED_TABLE, captured["configurable"]
    done = _done_frame(body)
    assert done.get("data_filename") == NAMED_TABLE, done
    assert NAMED_TOKEN in body, "Data 腿没把这张表算进答复"


def test_analysis_lane_floor_adds_the_data_leg_when_a_policy_question_names_a_table(monkeypatch, tmp_path) -> None:
    """has_data 必须读得出真：分析档地板那条 (data, has_data) 靠的就是这一格。

    问句只含制度词、调用方却点了名 —— 判据 2 要的形。腿的有无由**真**
    app/agents/orchestrator.py::route_main 判出，本件不复述它的规则。
    """
    registry = _registry(monkeypatch, tmp_path, "floor")
    _register(registry, NAMED_TABLE, department=DEPT)

    _body, captured = _drive_ask(
        monkeypatch,
        tmp_path,
        question=POLICY_QUESTION,
        data_filename=NAMED_TABLE,
        principal=_principal(),
        slug="floor",
        lane="analysis",
        probe_dispatch=True,
    )

    assert captured["has_data_filename"], captured["user"]
    assert "data" in captured["dispatch"], captured["dispatch"]
    # 正控：没点名文件时那一格不许凭空补出分析腿（地板条件仍然只有 has_data）。
    control = {"configurable": {"thread_id": "r709-control", nodes.DECLARED_LANE_KEY: "analysis"}}
    assert "data" not in _dispatch_workers(control, POLICY_QUESTION), "地板被无条件补了"


@pytest.mark.parametrize(
    ("question", "forced_data_only"),
    [
        # 含制度词 ⇒ 不改写：文档腿留在场，「要不要额外检索文档」由那枚谓词说了算。
        (POLICY_QUESTION, False),
        (QUESTION, False),
        # 纯数据问法 ⇒ 照旧改写成「请仅使用数据分析工具」。
        (DATA_ONLY_QUESTION, True),
    ],
)
def test_document_terms_only_decide_whether_docs_get_retrieved(
    monkeypatch, tmp_path, question: str, forced_data_only: bool
) -> None:
    registry = _registry(monkeypatch, tmp_path, "docs-leg")
    _register(registry, NAMED_TABLE, department=DEPT)

    _body, captured = _drive_ask(
        monkeypatch,
        tmp_path,
        question=question,
        data_filename=NAMED_TABLE,
        principal=_principal(),
        slug="docs-leg",
    )

    assert captured["user_message"].startswith("请仅使用数据分析工具") is forced_data_only, captured["user_message"]
    # 无论改写与否，点名的文件都必须跟着这一轮走（判据 2 前半段不许被这枚参数化放宽）。
    assert captured["has_data_filename"], question


# ==================== 判据 3 · 可见集不许退化 ====================


def test_the_visible_set_stays_narrowed_to_the_named_file(monkeypatch, tmp_path) -> None:
    """两枚台账都看得见时，带表的那一轮只许算点名的那一枚。"""
    registry = _registry(monkeypatch, tmp_path, "narrow")
    _register(registry, NAMED_TABLE, department=DEPT)
    _register(registry, SIBLING_TABLE, department=SIBLING_DEPT)

    body, captured = _drive_ask(
        monkeypatch,
        tmp_path,
        question=QUESTION,
        data_filename=NAMED_TABLE,
        principal=_principal(role="admin"),
        slug="narrow",
    )

    filenames = [
        str((item.get("locator") or {}).get("filename") or "")
        for item in captured["bag"].get("datasets", [])
    ]
    assert filenames == [NAMED_TABLE], f"可见集退化：本轮实际算了 {filenames}"
    assert SIBLING_TOKEN not in body, "没点名的表也被算了：可见集退化成全量"
    assert _done_frame(body).get("data_filename") == NAMED_TABLE


# ==================== 🔴 判据 3 的反证牙 · 无权文件不许静默放宽 ====================


def test_a_named_file_the_caller_may_not_read_hits_the_ratified_error_code(monkeypatch, tmp_path) -> None:
    """点名一枚读不到的文件 ⇒ 必须走在册错误码那一支并点名那枚码，不许退回全量可见集。

    这枚牙是 C 门「越权 0 条」那一格的牙。把守卫放宽成「读不到就当没点名」立刻红——那正是
    改前的形状：名字被否决 ⇒ 整张可见表都算了。
    """
    registry = _registry(monkeypatch, tmp_path, "tooth")
    _register(registry, NAMED_TABLE, department=DEPT)
    _register(registry, FOREIGN_TABLE, department=FOREIGN_DEPT)

    body, captured = _drive_ask(
        monkeypatch,
        tmp_path,
        question=QUESTION,
        data_filename=FOREIGN_TABLE,
        principal=_principal(),
        slug="tooth",
    )

    codes = _denial_codes(captured)
    assert len(codes) == 1, f"一次权限拒绝应恰好落一枚码，实际 {codes}"
    assert codes[0] in tools._PUBLIC_ERROR_CODES, f"闸上交回的不是在册错误码：{codes}"
    assert "暂无可访问的数据文件" in body and "error_code=" in body, body[:800]
    # 静默放宽的反证：这一轮一枚数据集都没算成，done 件里那一格必须整格缺席。
    assert captured["bag"].get("datasets") == [], captured["bag"].get("datasets")
    assert "data_filename" not in _done_frame(body), _done_frame(body)
    assert NAMED_TOKEN not in body, "拒了一枚无权文件，却把别的可见表算了进去"


def test_a_named_file_that_does_not_exist_says_so_and_still_does_not_widen(monkeypatch, tmp_path) -> None:
    """点名一枚台账里没有的文件 ⇒ 走「未找到选中的数据文件」那一支，同样不许退化成全量。"""
    registry = _registry(monkeypatch, tmp_path, "missing")
    _register(registry, NAMED_TABLE, department=DEPT)
    ghost = "r709-根本不存在的表.csv"

    body, captured = _drive_ask(
        monkeypatch,
        tmp_path,
        question=QUESTION,
        data_filename=ghost,
        principal=_principal(),
        slug="missing",
    )

    assert ghost in body, body[:800]
    codes = _denial_codes(captured)
    assert codes and codes[0] in tools._PUBLIC_ERROR_CODES, codes
    assert captured["bag"].get("datasets") == [], captured["bag"].get("datasets")
    assert "data_filename" not in _done_frame(body), _done_frame(body)