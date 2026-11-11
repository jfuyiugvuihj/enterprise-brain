# -*- coding: utf-8 -*-
"""R524 差格 b：队列道今天结构上发不出第二枚字——判据② 交回带凭据的 ``not_applicable``。

派工词判据② 原文：「测试里真走 ``queued_response`` 那一支，断言一轮里 ``text`` 事件数 >1、片段时间戳
不重叠、逐字拼回与全量正文无缺字……**若这一支今天结构性发不出第二枚字，不许伪造**——把「发不出」写成
带凭据的 ``not_applicable`` 并交回总控裁。本件就是那份凭据，四条事实全部现取、可复跑：

1. **这一支一轮只交两枚帧**：``event: queued`` + 一枚 ``done``（``terminal_state=queued``、
   ``answer_present=false``、``usage=null``）。``text`` 帧恒 **0 枚** ⇒ 判据② 那三条在这一支没有主语。
2. **本轮零枚模型调用**：入队那一发不碰图、不碰模型（``run_with_stream`` 零次、``_make_model`` 零次），
   所以出口连一枚字节都没有可发的来源——不是"没接上"，是**没有字可发**。
3. **这一支上没有可注册的地方**：入队出口的源文里 ``stream_piece_sink`` 零命中；真接点在
   ``deploy/queue_worker.py::_drain_report_stream`` 那一发 ``run_with_stream``（本树现取该文件
   ``stream_piece_sink`` **0** 命中），而 ``deploy/**`` 不在本单写域白名单里。
4. **投递面已经关了**：入队那条 SSE 在两枚帧之后就地结束，此后的读数只从轮询面
   ``GET /api/v1/queue/status/{request_id}`` 回来（``docs/handoff/2026-09-30-plan-eight-tickets-recheck.md``
   §2 R31 差格 b、以及 R519 交工纸同一条事实）。就算 worker 进程注册了出口，也没有一条活着的流收它。

**R548 改口（2026-09-30）**：上面第 3 条「这一支上没有可注册的地方」已经翻面——
``deploy/queue_worker.py`` 现在有了一枚注册点（``_drain_report_stream`` 把本轮的
``ReportLanePieceLedger`` 交给编排入口那枚同名形参；恰一枚，坐标与牙见
``tests/test_r548_queue_lane_registers_the_piece_sink.py``）。第 1／2／4 条一字未动：入队
那一条流仍旧只交两枚帧、仍旧零枚模型调用、仍旧在第二枚字符之前就关掉。所以本件的名字与
结论都还成立，只改两格：③「有没有可注册点」，以及 ``verdict_for`` 里「存在注册点就算
connected」——后者改成**只算投递面**（注册而不交付正是 R545 明令禁止的那一种洗绿）。
逐字对账、当场红的原文与 sha256 台账在
``docs/testing/r548-queue-lane-piece-sink-registration.md`` §6。

🔴 与「把 not_applicable 偷写成已过」同源的那枚牙：本件把纸上的判定词与盘面事实**对判**（
``docs/testing/r524-stream-piece-sink-two-runways.md`` 的 ``r524-verdict`` 段）。纸改成"已过"、
或盘面真接上了而纸还写着 ``not_applicable``，两向都当场红——上一班刚造出一枚永不匹配的死牙，这枚不是。
"""

import ast
import asyncio
import inspect
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents import nodes, orchestrator
from app.api.v1 import chat
from app.common.identity import Principal
from app.common import reliable_queue
from app.storage.sessions import SessionRegistry

REPO = Path(__file__).resolve().parents[1]
CHAT_PATH = REPO / "app" / "api" / "v1" / "chat.py"
WORKER_PATH = REPO / "deploy" / "queue_worker.py"
PAPER = REPO / "docs" / "testing" / "r524-stream-piece-sink-two-runways.md"

SESSION = "r524-queue-lane"
USERNAME = "r524-queue"
USER_ID = "u-r524-queue"
MESSAGE = "把上季度的经营情况整理成一页纸报告"
IDEM = "r524-idempotency-key"
QUEUE_REQUEST_ID = "r524-reliable-request"

#: 纸上那一格的取值域：只认这三枚词，别的写法一律算改口没改干净。
PAPER_WORDS = {"connected", "not_applicable", "not_reached"}


def _function_source(module, name: str) -> str:
    """按名字取模块里某枚函数的源码，**嵌套定义也算**（``queued_response`` 藏在入队出口里面）。"""
    text = Path(inspect.getsourcefile(module)).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    raise AssertionError(f"{module.__name__} 里找不到 {name}，这条钉的前提变了")


# ============ 夹具：把入队这一支摘成离线件（零模型、零端口、零容器、零真队列） ============


class _FakeQueue:
    """只记录入队调用：本件要的是"这一支到底跑没跑图"，不需要真 Redis。"""

    def __init__(self):
        self.calls = []

    def enqueue(self, payload, idempotency_key):
        self.calls.append({"payload": payload, "idempotency_key": idempotency_key})
        return SimpleNamespace(request_id=QUEUE_REQUEST_ID)


class _StreamSpy:
    """顶替 ``run_with_stream``：它被调用就说明这一轮其实进了在场执行，那就不是队列道。"""

    def __init__(self):
        self.calls = []

    def __call__(self, *_args, **kwargs):
        self.calls.append(kwargs)
        yield {"messages": [], "worker_results": {}, "final_answer": "不该出现在这一支"}


class _ModelFactorySpy:
    """入队这一发只要造模型，这里就当场炸。"""

    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("入队这一发不许造模型：它一个 token 都没付")


@pytest.fixture
def lane(monkeypatch, tmp_path):
    """报告档 + ``REPORT_LANE_VIA_QUEUE=on``：让 ``chat.ask`` 真走到 ``queued_response``。"""
    monkeypatch.setenv(str(chat.REPORT_LANE_QUEUE_ENV), "on")
    ctx = SimpleNamespace(
        queue=_FakeQueue(), stream=_StreamSpy(), models=_ModelFactorySpy(),
        monkeypatch=monkeypatch, saved=[],
    )
    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_a: {})
    monkeypatch.setattr(chat, "_save_message", lambda *a, **k: ctx.saved.append((a, k)))
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _sid, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(
        chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)})
    )
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr(reliable_queue, "connect_reliable_queue", lambda: ctx.queue)
    monkeypatch.setattr(orchestrator, "run_with_stream", ctx.stream)
    monkeypatch.setattr(nodes, "_make_model", ctx.models)
    monkeypatch.setattr(orchestrator, "_make_model", ctx.models, raising=False)
    return ctx


def _http_request():
    principal = Principal.from_user(
        {"id": USER_ID, "username": USERNAME, "role": "staff", "department": "R&D"}
    )
    return SimpleNamespace(state=SimpleNamespace(username=USERNAME, principal=principal), headers={})


def _ask(lane_value="report", *, idempotency=IDEM):
    fields = {"message": MESSAGE, "session_id": SESSION}
    if lane_value is not None:
        fields["lane"] = lane_value
    if idempotency is not None:
        fields["idempotency_key"] = idempotency
    return asyncio.run(chat.ask(chat.AskRequest(**fields), http_request=_http_request()))


def _body(response) -> str:
    async def collect():
        parts = []
        async for chunk in response.body_iterator:
            parts.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        return "".join(parts)

    return asyncio.run(collect())


def _frames(body: str) -> list:
    """按到达顺序交回 ``(事件名, data 载荷)``，与 ``tests/test_r210...`` 的 ``_wire`` 同一读法。"""
    out = []
    for frame in body.split("\n\n"):
        if not frame.strip():
            continue
        name, data = None, None
        for line in frame.split("\n"):
            if line.startswith("event: "):
                name = line[len("event: "):].strip()
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if name or data:
            out.append((name or str((data or {}).get("type") or ""), data or {}))
    return out


def _sink_registration_points() -> list:
    """这一支上有没有可注册出口的地方：入队出口的源文 + worker 进程各扫一遍（只读，不 import）。"""
    hits = []
    if "stream_piece_sink" in _function_source(chat, "_enqueue_ask_turn"):
        hits.append("app/api/v1/chat.py::_enqueue_ask_turn")
    hits += [
        f"deploy/queue_worker.py:{number}"
        for number, line in enumerate(WORKER_PATH.read_text(encoding="utf-8").splitlines(), 1)
        if "stream_piece_sink" in line
    ]
    return hits


def queue_lane_facts(lane) -> dict:
    """现取这一支的事实（本件所有判据与纸面对账都读这里，不另抄一份数）。"""
    body = _body(_ask())
    frames = _frames(body)
    return {
        "event_names": [name for name, _payload in frames],
        "text_frames": sum(1 for name, _payload in frames if name == "text"),
        "model_calls": len(lane.models.calls),
        "graph_runs": len(lane.stream.calls),
        "sink_points": _sink_registration_points(),
        "done_payload": dict(next((p for n, p in frames if n == "done"), {})),
    }


def verdict_for(facts: dict) -> str:
    """纸上那一格该写哪个词，由盘面事实决定——不由任何人手填。

    R548 改口（凭据与逐字对账见 ``docs/testing/r548-queue-lane-piece-sink-registration.md`` §6）。
    改前三格里任一枚成立就判 ``connected``，其中第一格把「worker 里存在注册点」直接当成「这一支
    接上了」。R548 之后那一格不再单独算数：注册点今天真的在了，而客户端那条 SSE 已经关掉、一个字
    都收不到——把这种状态写成 ``connected`` 就是洗绿。判定只严不松：
      · 这一支真在场跑了图（``graph_runs``）⇒ connected（与改前同一半）
      · 这一支真发出第二枚字（``text_frames`` > 1）⇒ connected（与改前同一半）
      · 只有注册点、没有收端 ⇒ not_applicable（**唯一**的收紧处，改前记 connected）

    注册点那格的读数没被删：它仍旧留在 facts["sink_points"] 里，由
    ``tests/test_r548_queue_lane_registers_the_piece_sink.py`` 反向钉着（把注册退回就红）。
    """
    if facts["graph_runs"] or facts["text_frames"] > 1:
        return "connected"
    return "not_applicable"


def paper_verdict(path: Path = PAPER) -> str:
    """从交工纸的 ``r524-verdict`` 段取队列道那一格；取不到就是红，不许靠记忆读纸。"""
    text = path.read_text(encoding="utf-8")
    block = re.search(r"```r524-verdict\n(.*?)```", text, re.S)
    assert block, "交工纸里没有 r524-verdict 段：这一格没有机器可读的落点"
    match = re.search(r"^queue_lane=(\S+)$", block.group(1), re.M)
    assert match, block.group(1)
    word = match.group(1)
    assert word in PAPER_WORDS, f"纸上的判定词不在认的词汇表里：{word}"
    return word


# ==================== 事实① ②：这一支只有两枚帧、零枚模型调用 ====================


def test_the_queued_lane_yields_a_receipt_and_a_terminal_frame_and_nothing_else(lane, monkeypatch):
    """真走 ``queued_response``：帧名序列就是那两枚，``text`` 恒 0（判据② 的第一条没有主语）。"""
    body = _body(_ask())
    frames = _frames(body)

    assert [name for name, _p in frames] == ["queued", "done"], body
    assert frames[0][1]["lane"] == "report", frames[0][1]
    assert sum(1 for name, _p in frames if name == "text") == 0
    assert lane.queue.calls, lane.queue.calls
    assert lane.stream.calls == [] and lane.models.calls == []


def test_the_over_limit_lane_is_the_same_two_frames(lane, monkeypatch):
    """超限那一支共用同一个入队出口（``lane=""``）：形状逐字同，只是不带档位。"""
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (False, 0))
    frames = _frames(_body(_ask(lane_value=None)))

    assert [name for name, _p in frames] == ["queued", "done"]
    assert "lane" not in frames[0][1], frames[0][1]
    assert sum(1 for name, _p in frames if name == "text") == 0


def test_the_queued_turn_pays_for_no_model_at_all(lane):
    """判据② 的"没有字"那一半：本轮一个模型都没打，``usage`` 交 null 而不是 0/0/0。"""
    body = _body(_ask())
    frames = _frames(body)
    done = dict(frames[-1][1])

    assert lane.models.calls == [] and lane.stream.calls == []
    assert done.get("terminal_state") == chat.TERMINAL_STATE_QUEUED, done
    assert done.get("answer_present") is False, done
    assert done.get("usage") is None, done


def test_the_stream_of_the_queued_lane_is_closed_before_any_piece_could_arrive(lane):
    """投递面在两枚帧之后就关了：再没有第二条帧的去处，所以逐片在这一支无处可收。"""
    response = _ask()

    async def collect():
        got = []
        async for chunk in response.body_iterator:
            got.append(chunk)
        with pytest.raises(StopAsyncIteration):
            await response.body_iterator.__aiter__().__anext__()
        return got

    chunks = asyncio.run(collect())
    assert len(chunks) == 2, chunks


# ========= 事实③ ④：R548 之后注册点在 worker 那一侧；入队出口这一侧仍旧一字未动 =========


def test_the_enqueue_exit_still_registers_no_sink__r548_moved_the_hook_to_the_worker():
    """改口件（R548）：入队出口那一侧一字未松；worker 那一侧由「零枚」翻成「有且只在 deploy 下」。

    改前整枚原文逐字留档（五条一字不删，只把最后那条的结论翻面）：

        def test_there_is_no_place_on_the_queued_lane_to_register_a_sink():
            # 派工词说「queued_response 不注册 sink，与 a 同族」；本钉把这句话钉成机器事实。
            enqueue = _function_source(chat, "_enqueue_ask_turn")
            assert "stream_piece_sink" not in enqueue
            assert _sink_registration_points() == [], _sink_registration_points()

    那条 ``== []`` 在 R548 落地之后必红：本机此刻在 run10 真机窗内，本单一律只写不跑，所以这里
    交回的是**预期红形**（等窗后代跑复现），不是实取读数——应当读成
    ``AssertionError: assert [] == ['deploy/queue_worker.py:<注册点行号>', ...]``。命令、预期读数
    与 sha256 台账见 ``docs/testing/r548-queue-lane-piece-sink-registration.md`` §6。
    改法只动「哪一侧有」这一格，强度不降反升：入队出口那一半的断言原样留着，新加的是「worker
    侧必须有一枚」——R548 的注册被人退回，这枚同样红。
    """
    enqueue = _function_source(chat, "_enqueue_ask_turn")
    assert "stream_piece_sink" not in enqueue
    hits = _sink_registration_points()
    assert not [hit for hit in hits if hit.startswith("app/")], hits
    assert [hit for hit in hits if hit.startswith("deploy/queue_worker.py")], hits


def test_the_real_hook_for_the_queue_lane_is_now_registered__r548():
    """差格 b 的真接点：``deploy/queue_worker.py`` 里那一发 ``run_with_stream``（本单白名单外）。

    本件**不 import 也不改**那枚文件（它会打真队列），只把坐标钉死：它是队列道唯一真打模型、
    也是唯一能注册出口的地方。要接上差格 b，得由总控改派一枚含 ``deploy/**`` 写域的单，
    并另定投递面（今天只有轮询面）。

    R548（2026-09-30）把这一手接上了：注册点恰一枚，就在本函数点的那一发调用上；投递面仍旧
    没裁，所以本件的名字与结论都留着，只把「白名单外」那一格改成「已在册」，并把最后那条断言
    反了个方向——改前那条逐字留档在下面。
    """
    worker = WORKER_PATH.read_text(encoding="utf-8")
    hits = [n for n, line in enumerate(worker.splitlines(), 1) if "run_with_stream(" in line]
    assert len(hits) == 1, hits
    # 改前那一条（逐字留档；R548 之前它成立，之后它当场红）：
    #     assert "stream_piece_sink" not in worker
    assert "stream_piece_sink" in worker
    # 一枚调用点配一枚注册关键字：多一枚就是第二套口径，由 R548 的 AST 钉按调用名点名。
    assert worker.count("stream_piece_sink=stream_piece_sink,") == 1


# ==================== 纸面与盘面对判：不许把 not_applicable 偷写成已过 ====================


def test_the_paper_word_and_the_tree_agree(lane):
    """纸写 ``not_applicable`` ⇔ 盘面确实发不出第二枚字。改口与接通都必须同时动两边，缺一即红。"""
    facts = queue_lane_facts(lane)
    assert facts["text_frames"] == 0 and facts["model_calls"] == 0, facts
    assert verdict_for(facts) == paper_verdict(), (facts, paper_verdict())


def test_a_forged_paper_word_goes_red(lane, tmp_path):
    """正控＋摘刀同一枚：把纸上的 ``not_applicable`` 偷写成 ``connected`` ⇒ 这枚对判当场红。"""
    facts = queue_lane_facts(lane)
    forged = tmp_path / "forged.md"
    forged.write_text(
        PAPER.read_text(encoding="utf-8").replace(
            "queue_lane=not_applicable", "queue_lane=connected"
        ),
        encoding="utf-8", newline="\n",
    )
    assert verdict_for(facts) == "not_applicable"
    with pytest.raises(AssertionError):
        assert verdict_for(facts) == paper_verdict(forged), "偷写没被抓到：这枚牙是死牙"


def test_a_connected_tree_would_not_fit_under_the_old_paper(lane, monkeypatch, tmp_path):
    """另一向：盘面真接上了（造一枚影子 ``queued_response`` 发出两枚 text 帧）而纸还写着
    ``not_applicable`` ⇒ 同样当场红。这一枚证明对判不是单向的"纸说没接就永远绿"。
    """
    monkeypatch.setattr(chat, "_enqueue_ask_turn", _shadow_enqueue_with_pieces(tmp_path))
    facts = queue_lane_facts(lane)
    assert facts["text_frames"] > 1, facts
    assert facts["graph_runs"] == 0 and facts["model_calls"] == 0, facts
    assert verdict_for(facts) == "connected", verdict_for(facts)
    with pytest.raises(AssertionError):
        assert verdict_for(facts) == paper_verdict(), "旧纸盖得住新盘面：这枚对判是单向的死牙"


def _shadow_enqueue_with_pieces(tmp_path: Path):
    """影子入队出口：把 queued_response 真改成发两枚 text 帧（只在内存里，仓内一字节不动）。"""
    source = _function_source(chat, "_enqueue_ask_turn")
    anchor = '        yield f"event: queued\\ndata: {json.dumps(queued, ensure_ascii=False)}\\n\\n"'
    assert source.count(anchor) == 1, source.count(anchor)
    # 影子那份源码 exec 进的是 chat 模块 globals 的副本，所以这里直接叫得出 text_sse_frame
    # （不写 chat.xxx：模块 globals 里另有一枚同名对象，前缀会指错东西）。
    mutated = source.replace(
        anchor,
        anchor + '\n        yield text_sse_frame("第一段逐片正文示例，足够长以过尺寸闸的部分内容")\n'
                   '        yield text_sse_frame("第一段逐片正文示例，足够长以过尺寸闸的部分内容再加一段")',
        1,
    )
    namespace = dict(vars(chat))
    target = tmp_path / "r524_shadow_enqueue.py"
    target.write_text(mutated, encoding="utf-8", newline="\n")
    exec(compile(mutated, str(target), "exec"), namespace)
    assert namespace["_enqueue_ask_turn"] is not chat._enqueue_ask_turn
    return namespace["_enqueue_ask_turn"]