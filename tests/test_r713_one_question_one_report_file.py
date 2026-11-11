r"""R713 判据 1 —— 一枚问话从发问到取件走完全程：导出目录里恰有一枚 PDF，且与台账枚数同数。

病形（凭据纸 ``docs/testing/r710-2026-10-06.md`` 第二节第 2 条，R710 执行层 Ramanujan 现读）：
``app/agents/orchestrator.py::_fallback_export_result`` 只拿答复**文字**里有没有受控产物口
判断“这一轮是否已经落过盘”。文字不是证据——模型把链接改写成了别的形状（在册历史形状见
``tests/test_approval_stream.py``：它交回的是 ``/static/exports/`` 那一枚落盘路径），或者
只说一句“文件已导出”，字符串守卫就认不出来，兜底腿于是再调一次 ``export_report``：一枚问话
写**两枚** PDF。R710 已把两条腿都在写盘前叫停（孤儿字节归零），但这“再调一次”的语义本身
仍在它的禁区里，本单承接。

本件把它钉成可失败读数，全程离线：假模型（一发真推理都不打）、零容器、字节只落
``tmp_path``。走的是产品路径本身 —— ``app/agents/orchestrator.py::_make_worker_wrapper`` 的
export 腿 + 真 ``app/agents/tools.py::export_report`` + 真
``app/storage/artifacts.py::ArtifactRegistry`` + ``GET /api/v1/artifacts`` 取账。

判据对应（每格都可失败，红的时候点名是谁）：
  1) ``test_one_question_writes_exactly_one_report_file`` —— 枚数与台账同数，且取件打得开；
  2) 反证牙① ``test_the_pin_goes_red_when_the_second_call_actually_happens`` —— 让兜底腿对
     台账失明（＝改前形状），第二枚字节真落盘，钉当场红并报出第二枚的路径；
  3) 反证牙② ``test_the_pin_goes_red_when_the_registration_leg_is_cut`` —— 摘掉登记腿，
     盘上两枚而台账零枚，钉当场红；
  4) ``test_a_prose_link_that_names_the_controlled_route_needs_no_second_export`` —— 改前就
     成立的那一腿不许被本单改坏（零回归）；
  5) ``test_a_turn_that_registered_nothing_still_gets_one_report_file`` —— 本轮什么都没登记时
     兜底腿仍须交付恰一枚：本单砍的是第二次，不是第一次。

与 R710 那三枚针的分工（认领前先 ``rg`` 过在册名册）：
``tests/test_r710_export_leg_registers_the_report_row.py`` 钉“工具腿调一次＝台账一枚”，
``tests/test_r710_reply_never_fakes_an_exported_report.py`` 钉终答不许拿文字冒充查不回的件，
``tests/test_r710_export_leg_tells_a_refusal_honestly.py`` 钉拒绝要说人话。三枚都不管
**编排层会不会为同一轮调第二次导出**，本件只认领这一格。
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.prebuilt import create_react_agent
from pydantic import Field

from app.agents import orchestrator, tools

LIST_PATH = "/api/v1/artifacts"
USERNAME = "r713-owner"
DEPARTMENT = "r713-报告测试部"
REPORT_BYTES = b"%PDF-1.4 r713 offline report"
TITLE = "2026 年上半年经营情况分析报告"
QUESTION = "把上半年的经营分析整理成 PDF 报告文件"

#: 模型自己那一腿交回的正文。报告是真落过盘的（工具那一发就写了字节），但链接被它改写成了
#: 别的形状 —— 旧的字符串守卫认不出这一枚，兜底腿就会再导一次。这就是本单要杀的病形。
PARAPHRASED_ANSWER = f"{TITLE}已生成，含营收、利润与门店排名三节。\n\n📁 报告文件已导出：见附件"

#: 交付腿本来就写对的形状：正文里躺着受控产物口，改前改后都不该有第二次导出。
CONTROLLED_ANSWER = f"{TITLE}已生成。\n\n报告已生成: [📋 下载报告](/api/v1/artifacts/art-r713/download)"

# ==================== 离线盘与离线台账 ====================


def _registry(monkeypatch, tmp_path):
    """真 registry 类，根落在 tmp_path：本件一个字都不碰仓库里的 static 目录。"""
    from app.storage import artifacts
    from app.storage.artifacts import ArtifactRegistry

    instance = ArtifactRegistry(root=tmp_path, metadata_path=tmp_path / "artifact-metadata.json")
    monkeypatch.setattr(artifacts, "artifact_registry", instance)
    return instance


@pytest.fixture()
def account(monkeypatch):
    """一张内存里的用户表，替掉 ``app.common.auth.get_user``。"""
    from app.common import auth

    users: dict[str, dict] = {}

    def add(username: str = USERNAME, department: str = DEPARTMENT, role: str = "admin") -> str:
        users[username] = {
            "id": username,
            "username": username,
            "role": role,
            "department": department,
        }
        monkeypatch.setattr(auth, "get_user", lambda name: users.get(name))
        return username

    return add


@pytest.fixture()
def export_dir(tmp_path):
    """导出目录替身：真 ``app/tools/export.py::EXPORT_DIR`` 就躺在 registry 根之下，这里同构。"""
    directory = tmp_path / "exports"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@pytest.fixture()
def fake_pdf(monkeypatch, export_dir):
    """假 PDF：只把字节落盘并记下落点，真渲染那一腿本单不碰。"""
    written: list[str] = []

    def generate(title: str, sections, chart_paths=None) -> str:
        path = export_dir / f"report_{uuid4().hex[:10]}.pdf"
        path.write_bytes(REPORT_BYTES)
        written.append(str(path))
        return str(path)

    from app.tools import export as export_module

    monkeypatch.setattr(export_module, "generate_pdf_report", generate)
    return written


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


def _headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


# ==================== 假模型：第一发真调工具，第二发改写链接形状 ====================


class _ScriptedModel(BaseChatModel):
    """假模型：按脚本交回每一发，一次真推理都不打；``bind_tools`` 原样交回自己。"""

    script: list = Field(default_factory=list)
    fired: int = 0

    @property
    def _llm_type(self) -> str:
        return "r713-scripted-stub"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        reply = self.script[min(self.fired, len(self.script) - 1)]
        self.fired += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


def _export_tool_call() -> AIMessage:
    """模型自己那一发的形状：真调一次 ``export_report``，参数齐、真落盘。"""
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "export_report",
                "args": {
                    "report_title": TITLE,
                    "sections_json": json.dumps(
                        [
                            {"type": "heading", "content": TITLE},
                            {"type": "text", "content": "上半年营收完成年度预算目标的 48.7%。"},
                        ],
                        ensure_ascii=False,
                    ),
                },
                "id": "call-r713-export",
                "type": "tool_call",
            }
        ],
    )


def _react_graph(*script):
    """真 ``create_react_agent`` + 假模型：工具腿就是产品里那一枚 @tool，没有手搓替身。"""
    return create_react_agent(_ScriptedModel(script=list(script)), [tools.export_report])

# ==================== 驱动：一枚问话从发问到取件 ====================


def _parent_config() -> dict:
    return {
        "configurable": {
            "id": USERNAME,
            "username": USERNAME,
            "role": "admin",
            "department": DEPARTMENT,
            "thread_id": f"sess-r713-{uuid4().hex[:8]}",
            "request_id": f"req-r713-{uuid4().hex[:8]}",
            "trace_id": f"trace-r713-{uuid4().hex[:8]}",
            "task_id": f"task-r713-{uuid4().hex[:8]}",
        }
    }


def _ask_once(child_graph):
    """把一枚问话打进 export 腿：走真节点（含 ``_fallback_export_result``），交回终答与本轮账。"""
    node = orchestrator._make_worker_wrapper(child_graph, "export")
    update = node(
        {"messages": [HumanMessage(content=QUESTION)], "worker_results": {}, "agent_results": {}},
        _parent_config(),
    )
    return update["worker_results"]["export"], update


def _registered_paths(registry) -> list[str]:
    """台账行指的字节落点（``app/storage/artifacts.py::ArtifactRecord.storage_path``）。"""
    return sorted(str(row.storage_path) for row in registry.list_active())


def _files_on_disk(export_dir) -> list[str]:
    return sorted(str(path) for path in export_dir.glob("*.pdf"))


def _assert_one_report_file(export_dir, registry) -> None:
    """枚数读数：落盘枚数 == 台账枚数 == 1，且盘上不许有台账登记不上的孤儿字节。

    每一枚都是对盘的读数（逐枚路径互比），不是“字符串里好像有”。红的时候必须把孤儿字节的
    完整路径报出来 —— 判据 2① 要的就是“点名第二枚的字节路径”。
    """
    disk = _files_on_disk(export_dir)
    ledger = _registered_paths(registry)
    orphans = [path for path in disk if path not in ledger]
    listed = "; ".join(disk)
    #: 逐枚路径原样进消息（不套 repr）：反证牙要的"点名第二枚的字节路径"读的是原始路径。
    assert len(disk) == 1, (
        f"一枚问话只该留下恰一枚报告字节：盘上现读 {len(disk)} 枚 [{listed}]（台账 {len(ledger)} 枚）"
    )
    assert len(ledger) == 1, f"台账枚数与落盘枚数不同数：台账 [{'; '.join(ledger)}]／盘上 [{listed}]"
    assert not orphans, f"落盘却没人登记的孤儿字节：[{'; '.join(orphans)}]"


# ==================== 判据 1：走完全程恰一枚 ====================


def test_one_question_writes_exactly_one_report_file(
    monkeypatch, tmp_path, export_dir, account, fake_pdf, client
) -> None:
    registry = _registry(monkeypatch, tmp_path)
    account()

    answer, update = _ask_once(
        _react_graph(_export_tool_call(), AIMessage(content=PARAPHRASED_ANSWER))
    )

    _assert_one_report_file(export_dir, registry)
    assert len(fake_pdf) == 1, fake_pdf

    listed = client.get(
        LIST_PATH, params={"artifact_type": "report"}, headers=_headers(USERNAME)
    ).json()
    assert listed["total"] == 1, listed
    row = listed["artifacts"][0]
    turn_rows = update["agent_results"]["export"]["artifacts"]
    assert [item["artifact_id"] for item in turn_rows] == [row["artifact_id"]], (turn_rows, row)

    #: 客户拿到的那一句必须真能取件：交付口打得开，且打开的就是盘上唯一那一枚字节。
    assert row["download_url"] in answer, (row, answer)
    fetched = client.get(row["download_url"], headers=_headers(USERNAME))
    assert fetched.status_code == 200, fetched.text
    assert fetched.content == REPORT_BYTES, fetched.content[:64]
    assert row["filename"] == Path(fake_pdf[0]).name, (row, fake_pdf)


# ==================== 判据 2①：第二次调用真发生 ⇒ 钉红并点名第二枚 ====================


def test_the_pin_goes_red_when_the_second_call_actually_happens(
    monkeypatch, tmp_path, export_dir, account, fake_pdf
) -> None:
    """把兜底腿对台账的读数摘掉（＝改前形状：它只读答复文字），第二次导出就真会发生。

    这枚就是本钉的反证牙：谁把“读台账”那一腿弄瞎，枚数读数必须当场红，并把第二枚字节的
    路径原样报出来 —— 不许安静地长出一枚没人登记的 PDF。
    """
    registry = _registry(monkeypatch, tmp_path)
    account()
    monkeypatch.setattr(orchestrator, "_registered_report_rows", lambda config: [])

    _ask_once(_react_graph(_export_tool_call(), AIMessage(content=PARAPHRASED_ANSWER)))

    disk = _files_on_disk(export_dir)
    assert len(disk) == 2, f"反证前提没成立：第二次导出没发生，盘上只有 {disk}"
    with pytest.raises(AssertionError) as raised:
        _assert_one_report_file(export_dir, registry)
    assert disk[1] in str(raised.value), (disk, str(raised.value))


# ==================== 判据 2②：摘掉登记腿 ⇒ 钉红 ====================


def test_the_pin_goes_red_when_the_registration_leg_is_cut(
    monkeypatch, tmp_path, export_dir, account, fake_pdf
) -> None:
    """登记腿一摘，台账与兜底腿同时失明：一枚问话长两枚字节、零枚在册，钉必须红。

    这枚牙证明“不再调第二次”靠的是**登记**那一腿，不是答复文字。R710 那三枚针认领的是台账
    行的形状与终答的诚实，都不认领这一格。
    """
    registry = _registry(monkeypatch, tmp_path)
    account()
    monkeypatch.setattr(tools, "_register_artifact", lambda path, artifact_type, config: None)

    _ask_once(_react_graph(_export_tool_call(), AIMessage(content=PARAPHRASED_ANSWER)))

    assert _registered_paths(registry) == [], registry.list_active()
    with pytest.raises(AssertionError) as raised:
        _assert_one_report_file(export_dir, registry)
    message = str(raised.value)
    for path in _files_on_disk(export_dir):
        assert path in message, (path, message)


# ==================== 判据 4：改前成立的那一腿零回归 ====================


def test_a_prose_link_that_names_the_controlled_route_needs_no_second_export(
    monkeypatch, tmp_path, export_dir, account, fake_pdf
) -> None:
    """正文已经点着受控产物口：兜底腿一次都不许多调（改前改后同一格，本单不许碰坏）。"""
    registry = _registry(monkeypatch, tmp_path)
    account()
    calls: list = []

    class _MustNotBeCalled:
        def invoke(self, payload, config=None):
            calls.append(payload)
            raise AssertionError("答复已点着受控产物口，兜底腿不该再调第二次导出")

    monkeypatch.setattr(orchestrator, "export_report", _MustNotBeCalled())

    _ask_once(_react_graph(_export_tool_call(), AIMessage(content=CONTROLLED_ANSWER)))

    assert calls == [], calls
    _assert_one_report_file(export_dir, registry)


# ==================== 判据 5：什么都没登记时仍交付恰一枚 ====================


def test_a_turn_that_registered_nothing_still_gets_one_report_file(
    monkeypatch, tmp_path, export_dir, account, fake_pdf, client
) -> None:
    """模型压根没调工具（或工具那一腿拒了）：兜底腿的理由还在 —— 本轮恰落一枚、恰登记一枚。"""
    registry = _registry(monkeypatch, tmp_path)
    account()

    answer, update = _ask_once(_react_graph(AIMessage(content=PARAPHRASED_ANSWER)))

    _assert_one_report_file(export_dir, registry)
    turn_rows = update["agent_results"]["export"]["artifacts"]
    assert len(turn_rows) == 1, turn_rows
    assert "/api/v1/artifacts/" in answer, answer

    row = client.get(
        LIST_PATH, params={"artifact_type": "report"}, headers=_headers(USERNAME)
    ).json()["artifacts"][0]
    assert client.get(row["download_url"], headers=_headers(USERNAME)).content == REPORT_BYTES