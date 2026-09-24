# -*- coding: utf-8 -*-
r"""R48 路线甲 · 首屏线索卡的**发射面**：什么时候发、发什么、什么时候**宁可不发**。

判据全文在跟进单 §93「R48 定案（路线甲）」与本单派工 §5。本件钉的是：

  ① 三处同源 —— 发射点、契约 canonical 名单、``frontend/src/lib/sessions.js`` 的 ``EVENT_CLAIMS``。
     前两处另有 ``tests/test_r156_sse_event_surface_sync.py`` 做双向门；本件补第三处（那枚门读不到
     前端），并把「卡片每一格」逐格指回契约：契约没记名的一格不许上流线。
  ③ 卡片内容全部可指回事实 —— 每一格要么来自一行**已过** ``scope.allows`` 的来源行，要么来自发卡
     这一刻真读到的计数/耗时。🔴 没有一格是手填示例值，也没有一格来自模型正文。
  ④ 三态里后两态在**后端**这一侧的形状：本轮该有卡（有可见行）就发；无可见行、或全部被检索范围
     扣下，就**一枚都不发**（宁缺毋造）；缓存命中腿同样不发。
  ⑤ 反证里的两把（从契约摘掉名字、卡片取一枚不存在的字段）；第三把（把卡片改发成 ``event: text``）
     在 ``tests/test_r48_headline_never_enters_the_text_ledger.py``。

纪律：不打模型、不连库、不起服务。真跑着的是 ``/ask`` 路由本体、真证据边界
（``app/agents/evidence.py::record_document_hits``）与真 ``app/rag/filters.py`` 的 ``scope.allows``；
假的只有 ``run_with_stream`` 那一层 —— 直接借 ``tests/test_sse_sources.py`` 的夹具，不造第二份。
"""
import asyncio
import hashlib
import importlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

from app.api.v1 import chat

from tests.test_sse_sources import (  # noqa: F401  -- 同一条链，不造第二份夹具
    FINANCE_DOC,
    HR_DOC,
    SECRET_DOC,
    _http_request,
    consume,
    doc_state,
    drive,
    fake_retriever_hits,
    finance_principal,
    patch_offline,
)

REPO = Path(__file__).resolve().parents[1]
CHAT_PY = REPO / "app" / "api" / "v1" / "chat.py"
CONTRACT = REPO / "docs" / "api" / "contract-v1.md"
CLAIMS_JS = REPO / "frontend" / "src" / "lib" / "sessions.js"
R150_JS = REPO / "frontend" / "src" / "lib" / "r150-event-claims.test.js"
R156_PY = REPO / "tests" / "test_r156_sse_event_surface_sync.py"
EVENT = "answer.headline"
#: 事件名在前端源码里由单引号包着；这里用码位取字符，免得本件抄出一份事件名字面量集合。
SQ = chr(39)
DQ = chr(34)
BT = chr(96)


# ==================== 取帧 ====================


def wire(body):
    frames = []
    for block in body.split("\n\n"):
        if not block.startswith("event: "):
            continue
        name = block.split("\n", 1)[0][len("event: "):].strip()
        try:
            payload = json.loads(block.split("data: ", 1)[1])
        except (IndexError, ValueError):
            payload = {}
        frames.append((name, payload))
    return frames


def cards(body):
    return [payload for name, payload in wire(body) if name == EVENT]


def names(body):
    return [name for name, _payload in wire(body)]


def text_contents(body):
    return [str(payload.get("content") or "")
            for name, payload in wire(body) if name == "text"]


def _one_card(body):
    found = cards(body)
    assert len(found) == 1, "一轮应当恰好一枚首屏卡，实得 %d：%s" % (len(found), names(body))
    return found[0]


def _one_sources(body):
    found = [payload for name, payload in wire(body) if name == "sources"]
    assert len(found) == 1, found
    return found[0]["data"]


# ==================== 取样：可见行 / 全扣行，都走同一枚 scope.allows ====================


def _visible_hits(count):
    """``count`` 条 finance / 密级 2 命中：对 ``finance_principal`` 全部**可见**。"""
    base = fake_retriever_hits()[0]
    return [dict(base, source="policy-%d.pdf" % index, source_id="policy-%d.pdf" % index,
                 chunk_index=index, content="财务部可见命中 %d 的正文。" % index)
            for index in range(count)]


def _hidden_hits(count):
    """``count`` 条 hr / 密级 2 命中：对 ``finance_principal`` 全部**不可见**（跨部门）。"""
    base = fake_retriever_hits()[1]
    return [dict(base, source="hr-only-%d.pdf" % index, source_id="hr-only-%d.pdf" % index,
                 chunk_index=index, content="人事专用命中 %d 的正文。" % index)
            for index in range(count)]


# ==================== 出处核对：两枚名单都从契约现解析，不抄第二份 ====================


def _contract_text():
    return CONTRACT.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _table_first_cells(markdown, anchor):
    """``anchor`` 之后第一枚 markdown 表格的**首格**里点名的全部字段。"""
    if anchor not in markdown:
        raise AssertionError("契约里找不到锚 %r：那一节的形状变了" % anchor)
    rows = []
    for line in markdown.split(anchor, 1)[1].split("\n"):
        if line.startswith("|"):
            rows.append(line)
        elif rows:
            break
    if len(rows) < 3:
        raise AssertionError("锚 %r 之后的表格不足三行（实到 %d），解析不成立" % (anchor, len(rows)))
    found = set()
    for line in rows[2:]:                                   # 跳过表头与分隔行
        cells = [c.strip() for c in line.strip("|").split("|")]
        found |= set(re.findall(r"`([a-z_][a-z0-9_]*)`", cells[0]))
    if not found:
        raise AssertionError("锚 %r 之后的首格抠不出任何名字" % anchor)
    return found


def _contract_card_keys():
    return _table_first_cells(_contract_text(), "Keys inside " + BT + "data" + BT + ":")


def _contract_row_keys():
    """卡片行形状 = ``sources`` 事件那张行表：两枚事件共用一份字段账。"""
    return _table_first_cells(_contract_text(), "Per-row keys, all of them")


def _check_payload_keys(data):
    """载荷只许装契约点过名的键，一枚不多、一枚不少。"""
    documented = _contract_card_keys()
    extra = sorted(set(data) - documented)
    assert not extra, "卡片载荷里有契约没记名的键：%s" % extra
    lost = sorted(documented - set(data))
    assert not lost, "契约点名而卡片不交的键：%s" % lost


def _check_row_keys(rows):
    documented = _contract_row_keys()
    for row in rows:
        undeclared = sorted(set(row) - documented)
        assert not undeclared, "卡片行里有契约没记名的键：%s" % undeclared

# ==================== 判据 ①：该发的时候发，而且只发一枚 ====================


def test_a_turn_with_a_visible_source_sends_exactly_one_card(monkeypatch, tmp_path):
    body = drive(monkeypatch, tmp_path, [doc_state(fake_retriever_hits())], finance_principal())
    assert cards(body), "有可见行却没发卡：首屏那一格空着"
    assert _one_card(body)["data"]["carries_answer"] is False, "卡片自称承载答案 = 谎话"


def test_the_card_is_canonical_and_arrives_before_the_answer(monkeypatch, tmp_path):
    """信封七键齐全 + 位置在正文之前：这条道要给的是首屏，不是收尾的复盘。"""
    body = drive(monkeypatch, tmp_path, [doc_state(fake_retriever_hits())], finance_principal())
    payload = _one_card(body)
    for field in ("request_id", "trace_id", "task_id", "sequence", "timestamp", "status", "data"):
        assert field in payload, "卡片不是 canonical 信封，缺 %s" % field
    assert payload["status"] == "running", "卡片不是终态信号，不许写成 completed"
    order = names(body)
    assert order.index(EVENT) < order.index("text"), "卡片排在正文之后就不是首屏了"
    assert order.index(EVENT) > order.index("request.started"), "卡片不许抢在轮号之前"


def test_the_envelope_is_the_same_seven_keys_as_request_started(monkeypatch, tmp_path):
    """信封逐键对钉：卡片与 ``request.started`` 共用唯一构造器，键序漂一格收端就认不出。"""
    body = drive(monkeypatch, tmp_path, [doc_state(fake_retriever_hits())], finance_principal())
    by_name = {name: payload for name, payload in wire(body)}
    assert list(by_name[EVENT]) == list(by_name["request.started"]), (
        "卡片信封的键序与 request.started 不同：信封被复制成了第二份")
    assert by_name[EVENT]["status"] == "running"


def test_the_card_is_sent_once_even_when_evidence_arrives_in_several_updates(monkeypatch, tmp_path):
    """多枚 update 反复交证据，卡也只发一枚：首屏不是一块会自己刷新的板。"""
    hits = fake_retriever_hits()
    body = drive(monkeypatch, tmp_path,
                 [doc_state(hits[:1]), doc_state(hits), doc_state(hits)], finance_principal())
    assert len(cards(body)) == 1, names(body)
    data = _one_card(body)["data"]
    # 第一枚 update 只有一条可见行就把卡发了：卡说的是「发卡那一刻」的读数，不是整轮的总数。
    assert data["hit_count"] == 1, data


def test_the_sequence_counter_stays_continuous_across_the_card(monkeypatch, tmp_path):
    """插入一枚事件不许让后面的号撞车或跳号：``sources`` 仍然紧跟 ``request.completed``。"""
    body = drive(monkeypatch, tmp_path, [doc_state(fake_retriever_hits())], finance_principal())
    frames = wire(body)
    sequences = [payload["sequence"] for _name, payload in frames if "sequence" in payload]
    assert sequences == list(range(min(sequences), min(sequences) + len(sequences))), sequences
    by_name = {name: payload for name, payload in frames}
    assert by_name["sources"]["sequence"] == by_name["request.completed"]["sequence"] + 1


# ==================== 判据 ③：每一格都指得回一次读数 ====================


def test_every_card_row_is_a_row_this_principal_is_entitled_to(monkeypatch, tmp_path):
    """可见性只有一枚判据（``scope.allows``）：卡片不新增分支，也不许多带一行被拒的。"""
    body = drive(monkeypatch, tmp_path, [doc_state(fake_retriever_hits())], finance_principal())
    data = _one_card(body)["data"]
    assert [row["source"] for row in data["sources"]] == [FINANCE_DOC], data["sources"]
    assert data["hit_count"] == 1 and data["unauthorized_count"] == 2, data
    for withheld in (HR_DOC, SECRET_DOC):
        assert withheld not in body, "被拒来源出现在流里（%s）：卡片是本单新开的泄露面" % withheld


def test_card_fields_trace_back_to_the_evidence_boundary(monkeypatch, tmp_path):
    """逐格对出处：文件名/密级/部门/命中句都等于工具边界那行记下的值。"""
    body = drive(monkeypatch, tmp_path, [doc_state(fake_retriever_hits())], finance_principal())
    data = _one_card(body)["data"]
    _check_payload_keys(data)
    _check_row_keys(data["sources"])
    row = data["sources"][0]
    assert row["classification"] == 2 and row["department"] == "finance", row
    assert row["permission_checked"] is True, row
    assert row["source_id"] == FINANCE_DOC + "#chunk=0", row
    # 命中句是搬运：卡片上那一格必须等于证据边界记下的正文，不是任何人重新写的一句话。
    assert row["excerpt"] == "财务部差旅报销上限 2000 元。", row


def test_no_card_field_is_a_model_conclusion(monkeypatch, tmp_path):
    """🔴 卡片一个字都不从正文来：同一份证据跑两轮、只改腿交回的那句答案，卡片必须不动。

    ``elapsed_ms`` 是时间读数，两轮天然不同，比对时摘掉——其余每一格都必须逐位相同。
    """
    hits = fake_retriever_hits()
    first = drive(monkeypatch, tmp_path, [doc_state(hits, answer="一线 500 元")],
                  finance_principal())
    second = drive(monkeypatch, tmp_path, [doc_state(hits, answer="完全不同的另一句话")],
                   finance_principal())

    def comparable(body):
        data = dict(_one_card(body)["data"])
        data.pop("elapsed_ms")
        return data

    assert comparable(first) == comparable(second), "卡片跟着正文变了：它在转述模型，不是在报读数"
    # 反手再钉一格：那句答案确实上了流线，否则「两轮相同」只是因为压根什么都没发。
    assert any("一线 500 元" in c for c in text_contents(first)), names(first)
    assert any("完全不同的另一句话" in c for c in text_contents(second)), names(second)


def test_the_card_reports_the_truncation_instead_of_hiding_it(monkeypatch, tmp_path):
    """命中多于显示上限时：``shown_count < hit_count``，屏上那句「另有 N 条」才有读数。"""
    hits = _visible_hits(5)
    body = drive(monkeypatch, tmp_path, [doc_state(hits)], finance_principal())
    data = _one_card(body)["data"]
    assert len(data["sources"]) == chat.HEADLINE_SOURCE_LIMIT, data
    assert data["shown_count"] == chat.HEADLINE_SOURCE_LIMIT, data
    assert data["hit_count"] == 5, data
    assert data["unauthorized_count"] == 0, data
    assert data["shown_count"] < data["hit_count"], data
    # 「画了几条」与「命中几条」两枚计数各说各的事：合并成一格就把截断说成了全部。
    assert _one_sources(body)["hit_count"] == 5, "收尾那枚来源事件的读数与卡片对不上账"


def test_elapsed_ms_is_a_real_reading_not_a_placeholder(monkeypatch, tmp_path):
    """``elapsed_ms`` 必须是「本轮真的过了这么久」：为负、非整数都不合口径。"""
    body = drive(monkeypatch, tmp_path, [doc_state(fake_retriever_hits())], finance_principal())
    elapsed = _one_card(body)["data"]["elapsed_ms"]
    assert isinstance(elapsed, int) and not isinstance(elapsed, bool), type(elapsed)
    assert elapsed >= 0, elapsed


# ==================== 判据 ④：不该有卡的那两支，一枚都不发 ====================


def test_a_turn_that_retrieved_nothing_sends_no_card(monkeypatch, tmp_path):
    """「库里没检索到」：不发卡。空卡就是拿一张假卡填首屏，比少一张卡更糟。"""
    body = drive(monkeypatch, tmp_path,
                 [{"messages": [], "worker_results": {"doc": "没有依据的一句话"},
                   "final_answer": "没有依据的一句话"}], finance_principal())
    assert EVENT not in names(body)
    assert "sources" in names(body), "收尾的来源事件照旧要交，那张脸归它"
    assert _one_sources(body)["hit_count"] == 0
    assert _one_sources(body)["unauthorized_count"] == 0, _one_sources(body)


def test_a_turn_whose_rows_are_all_withheld_sends_no_card(monkeypatch, tmp_path):
    """「检索到了但不给你看」：同样不发卡，而两分支的**读数**必须可分辨。

    区别不在卡片这一侧（都不发），而在收尾那枚 ``sources`` 的两枚计数：这里
    ``hit_count=0 / unauthorized_count=3``，上一枚是 ``0/0``。前端字典
    （``lib/provenance.js::sourcesFace``）就是拿这两格画出 all-hidden 与 none 两张脸的，
    所以本枚钉的是读数可分辨，不是「看起来不一样」。
    """
    body = drive(monkeypatch, tmp_path, [doc_state(_hidden_hits(3))], finance_principal())
    assert EVENT not in names(body), "全被扣下还发卡，卡上能写的只有假话"
    sources = _one_sources(body)
    assert sources["hit_count"] == 0 and sources["unauthorized_count"] == 3, sources
    for row in _hidden_hits(3):
        assert row["source"] not in body, "被拒文件名进了流：这一支才是本单真正的泄露面"


def test_the_two_absent_card_faces_differ_in_the_readings_they_carry(monkeypatch, tmp_path):
    """两张「没有卡」的脸不许长成同一张：差别就在 ``unauthorized_count`` 那一格。"""
    nothing = drive(monkeypatch, tmp_path,
                    [{"messages": [], "worker_results": {"doc": "没有依据的一句话"},
                      "final_answer": "没有依据的一句话"}], finance_principal())
    withheld = drive(monkeypatch, tmp_path, [doc_state(_hidden_hits(2))], finance_principal())
    assert EVENT not in names(nothing) and EVENT not in names(withheld)

    def counts(body):
        payload = _one_sources(body)
        return payload["hit_count"], payload["unauthorized_count"]

    assert counts(nothing) == (0, 0), counts(nothing)
    assert counts(withheld) == (0, 2), counts(withheld)


def test_the_cache_hit_leg_sends_no_card(monkeypatch, tmp_path):
    """命中腿：答案当场就在，卡片没有存在的理由（它要说的是「正文还在路上」）。

    🔴 这里不能用 ``drive``：它内部会再跑一次 ``patch_offline``，把下面这枚缓存桩覆成 None，
    于是「命中腿不发卡」会被跑成「未命中腿不发卡」——同一句断言，证的却是别的东西。
    """
    patched = patch_offline(monkeypatch, tmp_path, [])
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: "缓存里的答案。")
    body = asyncio.run(_ask(patched, finance_principal()))
    assert any("缓存里的答案。" in c for c in text_contents(body)), names(body)
    assert EVENT not in names(body)


async def _ask(module, principal, message="差旅报销上限是多少？", session_id="r48-card"):
    response = await module.ask(
        module.AskRequest(message=message, session_id=session_id),
        http_request=_http_request(principal))
    return await consume(response)


def test_the_emission_point_is_unique_in_the_route():
    """全仓只有 ``/ask`` 这一处发卡：``/chat`` 与 ``/approve`` 续跑腿都不在射程内。"""
    source = CHAT_PY.read_bytes().decode("utf-8").replace("\r\n", "\n")
    emission_lines = [line for line in source.split("\n")
                      if line.strip() == DQ + EVENT + DQ + ","]
    assert len(emission_lines) == 1, (
        "发卡那枚实参出现在 %d 行，而不是唯一一处：发射点被复制了" % len(emission_lines))
    assert source.count(DQ + EVENT + DQ) == 2, (
        "事件名在本文件里除了发射实参只许再出现在 docstring 一处")
    assert source.count("_answer_headline_frame(") == 2, "构造器一处定义、一处调用，多一处就是多一条腿"
    assert source.count("HEADLINE_SOURCE_LIMIT = ") == 1


# ==================== 判据 ①：三处同源（第三处归本件，r156 读不到前端）====================


def _r156():
    spec = importlib.util.spec_from_file_location("r156_sync", R156_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_event_name_lives_in_the_contract_and_in_the_claim_table():
    """前两处**复用 r156 的解析器**（不抄第二份名单），第三处由本件钉。"""
    contract = _r156().parse_contract(_contract_text())
    assert EVENT in contract["canonical"], "契约的 canonical 名单里没有卡片：R156 那枚门会红"
    assert EVENT in contract["declared_emitted"], "发射表没把这枚卡片记成 emitted"

    claims = CLAIMS_JS.read_text(encoding="utf-8")
    assert SQ + EVENT + SQ + ": " + SQ + "render" + SQ in claims, (
        "前端认领表没把卡片认成 render：它会掉进 unknownEvents，就是 sources 当年的死法")
    assert "case " + SQ + EVENT + SQ + ":" in claims, "认领了却没接线，等于没认领"


def test_the_wire_name_is_visible_to_the_frontend_claim_gate():
    """并树那一刻的隐形红：直接跑 r150 那三条正则，量本工作树的 chat.py。

    ``r150-event-claims.test.js`` 的真源取自 ``git show <ref>:chat.py``，而执行层不许提交，
    所以它在并树前必然红（僵尸名）。那一枚红是设计使然的在途红，本枚把它**提前**到工作树：
    写法若让 r150 抠不到这枚名字，并树之后那枚僵尸名用例会永久红，而不是并树即绿。
    """
    js = R150_JS.read_text(encoding="utf-8")
    collected = _run_r150_patterns(js, CHAT_PY.read_bytes().decode("utf-8"))
    assert EVENT in collected, (
        "发射点写法在 r150 的枚举下不可见（实抠到 %d 枚）：并树后它会把 EVENT_CLAIMS 里这枚名字"
        "判成「后端已不再发出」，那一枚红不随并树消失" % len(collected))


def _run_r150_patterns(js_source, chat_source):
    """把 r150 里那三条正则现抠出来跑：正则仍归那枚文件所有，本件不抄第二份。"""
    block = js_source.split("function collectWireNames(src)", 1)[1].split("return names", 1)[0]
    literals = re.findall(r"^\s{4}/(.+)/g,$", block, re.MULTILINE)
    assert len(literals) == 3, "r150 的枚举形制不再是三条正则（%d 条），本枚要重写" % len(literals)
    found = set()
    for literal in literals:
        # 不做任何改写：JS 与 Python 的这枚字面同形（源里的 ``\\n`` 两边都读成「字面反斜杠
        # 加 n」，正是 f-string 字面上那两枚字符），改了就不是在跑 r150 的那三条了。
        found |= {m.group(1) for m in re.finditer(literal, chat_source)}
    return found


# ==================== 判据 ⑤：反证（临时改文件 -> 具名用例红 -> 逐字节还原）====================


class _TempEdit:
    """按字节进出的一枚临时变异；退出时不论断言成败都还原，并留 sha 证据。"""

    def __init__(self, path, edits):
        self.path = path
        self.edits = edits                      # [(old, new), ...] 每一枚锚点都必须唯一
        self.info = {}

    def __enter__(self):
        raw = self.path.read_bytes().decode("utf-8")
        self.info = {"before": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16], "raw": raw}
        edited = raw
        for old, new in self.edits:
            hits = edited.count(old)
            assert hits == 1, "%s 里锚点不唯一（%d 处）：%r" % (self.path.name, hits, old[:70])
            edited = edited.replace(old, new)
        assert edited != raw
        self.path.write_bytes(edited.encode("utf-8"))
        return self.info

    def __exit__(self, *_exc):
        self.path.write_bytes(self.info["raw"].encode("utf-8"))
        after = hashlib.sha256(self.path.read_bytes()).hexdigest()[:16]
        self.info["after"] = after
        self.info["restored"] = after == self.info["before"]
        print("[r48] %s %s -> %s restored=%s" % (self.path.name, self.info["before"],
                                                 after, self.info["restored"]))
        return False


def _reload():
    """把 chat 模块按盘上的字重新装一遍：临时变异要能被跑到。"""
    import tests.test_sse_sources as sources

    importlib.reload(chat)
    importlib.reload(sources)
    return sources


def test_counter_evidence_b_dropping_the_name_from_the_contract_turns_r156_red():
    """反证②：从契约里摘掉这枚事件名 ⇒ 同源门当场红。

    🔴 摘的是**两处**（canonical 名单与发射表），不是只摘一处：r156 的 ``recorded`` 是这两处的
    并集，只摘一处会被另一处兜住、门照样绿。那正是「反证跑了却没红」的假形状，所以这里先把
    「只摘一处仍然绿」实量出来，再摘两处看它红——两半都是读数，不是叙述。
    """
    r156 = _r156()
    text = CONTRACT.read_bytes().decode("utf-8")
    canonical_anchor = BT + EVENT + BT + " (R48, documented in the R48 compatibility note below)."
    table_anchor = BT + "request.cancelled" + BT + ", " + BT + EVENT + BT

    with _TempEdit(CONTRACT, [(canonical_anchor, "")]) as solo:
        contract = r156.parse_contract(CONTRACT.read_bytes().decode("utf-8"))
        scrape = r156.scrape_emission_surface(REPO / "app")
        assert EVENT not in contract["canonical"], "canonical 名单没被摘干净，反证无从谈起"
        assert EVENT in contract["recorded"], (
            "预期「只摘一处仍被发射表兜住」不成立了：发射表那一处也没记名，本枚反证要重看")
        r156.check_emitted_are_recorded(scrape, contract)      # 仍然绿——这就是只摘一处的代价
    assert solo["restored"], "第一处变异没还原"

    with _TempEdit(CONTRACT, [(canonical_anchor, ""),
                              (table_anchor, BT + "request.cancelled" + BT)]) as info:
        contract = r156.parse_contract(CONTRACT.read_bytes().decode("utf-8"))
        scrape = r156.scrape_emission_surface(REPO / "app")
        assert EVENT not in contract["recorded"], "两处都没摘干净，反证无从谈起"
        with pytest.raises(AssertionError) as exc:
            r156.check_emitted_are_recorded(scrape, contract)
        assert EVENT in str(exc.value), str(exc.value)
        print("[r48] 反证② 实际报错原文：", str(exc.value))
    assert text == CONTRACT.read_bytes().decode("utf-8"), "契约没还原"


def test_counter_evidence_c1_a_payload_key_nobody_named_turns_the_provenance_pin_red(monkeypatch,
                                                                                     tmp_path):
    """反证③ 的前半：卡片多交一枚谁都没记名的字段 ⇒ 「每格指得回出处」当场红。

    这一格要拦的形状很具体：往载荷里塞一句手填示例值，屏上就多出一格没有出处的读数，
    而它不需要改任何契约就能上屏——所以拦它的必须是对钉，不是契约门。
    """
    anchor = '        "unauthorized_count": max(0, int(withheld)),'
    patched = anchor + "\n" + DQ + "fabricated_note" + DQ + ": " + DQ + "一线 500 元（手填示例值）" + DQ + ","
    try:
        with _TempEdit(CHAT_PY, [(anchor, patched)]) as info:
            sources = _reload()
            body = sources.drive(monkeypatch, tmp_path,
                                 [sources.doc_state(sources.fake_retriever_hits())],
                                 sources.finance_principal())
            data = _one_card(body)["data"]
            assert "fabricated_note" in data, "变异没跑到盘上的码：这枚反证是空的"
            with pytest.raises(AssertionError) as exc:
                _check_payload_keys(data)
            assert "fabricated_note" in str(exc.value), str(exc.value)
            print("[r48] 反证③ 前半 实际报错原文：", str(exc.value))
    finally:
        _reload()


def test_counter_evidence_c2_a_row_field_that_does_not_exist_turns_the_round_red(monkeypatch,
                                                                                tmp_path):
    """反证③ 的后半：卡片去取一枚**不存在的行字段** ⇒ 当场炸，而不是安静地补一个默认值。

    ``excerpt`` 是行里真有的键，换成 ``excerpted_quote`` 就是没有的东西：这条道不兜底、
    不凑数，取不到就是异常，异常就是红。这比「读不到就写个空串」更难被洗成假绿。
    """
    anchor = '        "sources": [dict(row) for row in shown],'
    patched = '        "sources": [dict(row, quote=row["excerpted_quote"]) for row in shown],'
    try:
        with _TempEdit(CHAT_PY, [(anchor, patched)]) as info:
            sources = _reload()
            with pytest.raises(KeyError) as exc:
                sources.drive(monkeypatch, tmp_path,
                              [sources.doc_state(sources.fake_retriever_hits())],
                              sources.finance_principal())
            assert "excerpted_quote" in str(exc.value), str(exc.value)
            print("[r48] 反证③ 后半 实际报错原文：", type(exc.value).__name__, str(exc.value))
    finally:
        _reload()
