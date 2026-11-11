# -*- coding: utf-8 -*-
r"""R523 判据⑤ —— 反证刀：本单新加的每一枚守卫都必须先证明自己会咬。

上一班刚踩过一枚死牙（正则整枚永不匹配），所以这里的规矩是：**每把刀都配一枚正控**——
未变的源码先把探针跑绿，影子副本再把同一条链跑红，两件事按顺序写在册子里。刀全部落在
**内存里的源码影子副本**（``tests/test_r503_artifact_lineage_keys.py`` 的 ``load_shadow``：
compile + exec，锚点不唯一就当场报「这把刀会空转」），盘上的在册件一个字都不改。

* K1 摘掉 ``app/trace/projections.py`` 里那一格赋值 ⇒ 判据②那枚端到端链必须红；
* K2 把「没报」偷落成 0 ⇒ 判据③那枚 NULL 探针必须红；
* K3 把列从 ``app/trace/schema.py`` 的声明集里摘掉 ⇒ 契约封条必须拒绝这行（红在 ``extra=``）；
* K4 把列从 ``app/storage/persistence.py`` 的适配器列元组里摘掉 ⇒ 落库那枚探针必须红（第二道
  补令新加的那半段判据，正是「值在门口被静默丢掉」那一族的反证）。

写链仍复用 ``tests/test_r523_cached_count_lands.py`` 的真件夹具，本件不自建第二套。
全程离线：不连库、不起服务、不动容器、不打模型。
"""
from __future__ import annotations

import pytest
from tests._r250_fake_postgres import FakePostgres

#: 注意：load_shadow 用 exec 重跑一遍源码，影子件里的 TraceSchemaError 是**另一个类对象**，
#: 所以 K3 抓的是影子件自己那枚（抓真件那枚会漏，正是「看着在钉、实际永不红」的形状）。
from app.trace.schema import TRACE_TABLE_COLUMNS
from test_r503_artifact_lineage_keys import load_shadow
from test_r523_cached_count_lands import (
    COLUMN,
    PERSISTENCE,
    PROJECTIONS,
    SCHEMA,
    TABLE,
    compat_reply,
    drive_one_model_call,
    probe_absent_reading_is_null,
    probe_reported_count_is_handed_to_the_writer,
    probe_the_issued_insert_names_the_column,
    read_back_the_column,
)

#: K1 的靶：projections.py 里那一格赋值（连上面两行注释一起摘，模拟「这单忘了带上 cached」）。
ASSIGNMENT_BLOCK = (
    "                # 0018. A key the summary does not carry stays NULL, because spans.py drops\n"
    "                # it when the reply reported nothing; _first keeps a reported 0 as 0.\n"
    '                "cached_tokens": _first(summary.get("cached_tokens"), current.get("cached_tokens")),\n'
)
#: K2 的靶：同一格赋值，但把「没报」偷换成 0（判据③明令禁止的那种冒充）。
ZERO_FALLBACK = (
    "                "
    '"cached_tokens": _first(summary.get("cached_tokens"), current.get("cached_tokens")) or 0,\n'
)
#: K1 与 K2 共用同一枚单行锚点：K1 拿整块（含注释），K2 只拿赋值那一行。
ASSIGNMENT_LINE = ASSIGNMENT_BLOCK.splitlines(True)[-1]
#: K3 的靶：schema.py 里那一枚声明。
DECLARATION = f'        "{COLUMN}",\n'
#: K4 的靶：persistence.py 里 ``model_calls`` 列元组的末两格（摘掉 = 值在门口被丢掉）。
ADAPTER_TAIL = '            "metadata",\n            "cached_tokens",\n'
ADAPTER_TAIL_WITHOUT = '            "metadata",\n'


def _seed_agent_runs(chain, fresh):
    """把假库换成一台干净的，只搬外键要求的那几行 ``agent_runs``。

    不搬整库：K4 要判的是「这台库里只见过影子适配器那一笔写」，语句记录必须干净。
    """
    fresh.rows("agent_runs").update(
        {key: dict(row) for key, row in chain.rows("agent_runs").items()}
    )
    return fresh


def drive_with_shadow(tmp_path, monkeypatch, reply, *, trace_id, patches):
    """把写链里的投影换成影子副本，再跑真那条链。"""
    import app.trace.store as store_module

    shadow = load_shadow(PROJECTIONS, "r523_shadow_projections", patches)
    monkeypatch.setattr(store_module, "project_event", shadow.project_event)
    return drive_one_model_call(tmp_path, monkeypatch, reply, trace_id=trace_id)


def _reported():
    from test_r523_cached_count_lands import _compat_triplet

    return _compat_triplet()[2]


# ---------------------------------------------------------------------- K1：摘掉那一格赋值


def test_k1_control_the_pristine_chain_hands_the_count_over(tmp_path, monkeypatch):
    """正控：一字未改的源码先把判据②那枚探针跑绿，K1 的红才有对照组。"""
    _engine, _record_id, handed, _stored = drive_one_model_call(
        tmp_path, monkeypatch, compat_reply(cached="reported"), trace_id="r523-k1-control"
    )

    probe_reported_count_is_handed_to_the_writer(handed, _reported())


def test_k1_removing_the_assignment_blinds_the_end_to_end_chain(tmp_path, monkeypatch):
    """K1：摘掉 ``cached_tokens`` 那格赋值 ⇒ 端到端那条链必须红，且红得点名这一列。"""
    expected = _reported()

    with pytest.raises(AssertionError) as caught:  # 行上是 None：赋值被摘掉，声明还在 ⇒ 假绿的原形状
        _engine, _record_id, handed, _stored = drive_with_shadow(
            tmp_path,
            monkeypatch,
            compat_reply(cached="reported"),
            trace_id="r523-k1",
            patches=[(ASSIGNMENT_BLOCK, "")],
        )
        probe_reported_count_is_handed_to_the_writer(handed, expected)

    assert COLUMN in str(caught.value), (
        f"K1 是红了，但红话里没点名这一列（归因就不可查）：{type(caught.value).__name__} {caught.value}"
    )


# ---------------------------------------------------------------------- K2：把「没报」偷成 0


def test_k2_control_an_absent_reading_stays_null(tmp_path, monkeypatch):
    """正控：没报数那一发在未改源码上是 NULL，K2 的红才有对照组。"""
    _engine, _record_id, handed, _stored = drive_one_model_call(
        tmp_path, monkeypatch, compat_reply(cached="absent"), trace_id="r523-k2-control"
    )

    probe_absent_reading_is_null(handed)


def test_k2_defaulting_absent_to_zero_blinds_the_null_probe(tmp_path, monkeypatch):
    """K2：把「没报」偷落成 0 ⇒ NULL 那枚探针必须红（两脸合成一脸正是判据③拦的事）。"""
    _engine, _record_id, handed, _stored = drive_with_shadow(
        tmp_path,
        monkeypatch,
        compat_reply(cached="absent"),
        trace_id="r523-k2",
        patches=[(ASSIGNMENT_LINE, ZERO_FALLBACK)],
    )

    with pytest.raises(AssertionError) as caught:
        probe_absent_reading_is_null(handed)

    assert "0" in str(caught.value), f"红话里读不出被偷换成 0：{caught.value}"


# ---------------------------------------------------------------------- K3：声明与写入脱节


def test_k3_control_the_seal_accepts_the_declared_column_set():
    """正控：未改的声明集与投影交回的那一行对得上，封条今天不拦本单。"""
    from app.trace.projections import project_span

    event = {
        "trace_id": "r523-k3",
        "request_id": "req-r523-k3",
        "timestamp": "2026-09-30T00:00:00+00:00",
        "status": "completed",
        "event_type": "model.finished",
        "payload": {"record_id": "r523-k3:model:1", "summary": {"cached_tokens": 292}},
    }

    projection = project_span(event, "owner:r523-k3", {}, "model_calls").seal()

    assert projection.values[COLUMN] == 292


def test_k3_undeclaring_the_column_makes_the_seal_refuse_the_row():
    """K3：把列从声明集里摘掉 ⇒ 封条必须拒掉带着这一格的行（红在 ``extra=`` 那一半）。"""
    shadow = load_shadow(SCHEMA, "r523_shadow_schema", [(DECLARATION, "")])

    assert COLUMN not in shadow.TRACE_TABLE_COLUMNS["model_calls"], "锚点没摘掉，这把刀在空转"
    with pytest.raises(shadow.TraceSchemaError) as refused:
        shadow.require_columns("model_calls", set(TRACE_TABLE_COLUMNS["model_calls"]))

    assert f"extra=['{COLUMN}']" in str(refused.value), str(refused.value)



# ---------------------------------------------------------------------- K4：适配器列元组退回去

def test_k4_control_the_real_adapter_names_the_column_it_lands(tmp_path, monkeypatch):
    """正控：同一枚行、同一台干净假库，交给未改的适配器 —— 落库探针必须绿。"""
    from app.storage.persistence import PostgresPersistenceAdapter

    expected = _reported()
    chain, record_id, handed, _stored = drive_one_model_call(
        tmp_path, monkeypatch, compat_reply(cached="reported"), trace_id="r523-k4-control"
    )
    engine = _seed_agent_runs(chain, FakePostgres())

    PostgresPersistenceAdapter(engine.connection_factory).upsert(TABLE, record_id, handed)

    probe_the_issued_insert_names_the_column(engine, expected)
    assert read_back_the_column(engine, record_id) == expected


def test_k4_dropping_the_column_from_the_adapter_blinds_the_landing_probe(tmp_path, monkeypatch):
    """K4：把列从适配器列元组摘回去 ⇒ 真发出去的 INSERT 不再点它，落库探针必须红。

    这正是总控不许结案成「半笔」的那一族：投影算得对、schema 也声明了，值却在写库那一步
    被静默丢掉。这把刀证明判据②那枚新探针盯的是**发出去的语句**，不是纸面上的列。
    """
    expected = _reported()
    chain, record_id, handed, _stored = drive_one_model_call(
        tmp_path, monkeypatch, compat_reply(cached="reported"), trace_id="r523-k4"
    )

    shadow = load_shadow(
        PERSISTENCE, "r523_shadow_persistence", [(ADAPTER_TAIL, ADAPTER_TAIL_WITHOUT)]
    )
    assert COLUMN not in shadow._TABLES[TABLE].columns, "锚点没摘掉，这把刀在空转"

    engine = _seed_agent_runs(chain, FakePostgres())
    shadow.PostgresPersistenceAdapter(engine.connection_factory).upsert(TABLE, record_id, handed)

    with pytest.raises(AssertionError) as caught:
        probe_the_issued_insert_names_the_column(engine, expected)
    assert COLUMN in str(caught.value), f"红话里没点名这一列，归因不可查：{caught.value}"
    assert COLUMN not in engine.rows(TABLE)[record_id], "库里那一行竟然还带着这一格"


# ---------------------------------------------------------------------- 死牙闸门


def test_the_knife_anchors_are_unique_or_the_blade_is_dead():
    """四枚锚点在盘上必须各命中一枚。锚点漂了就是「正则永不匹配」那一族的老病。"""
    projections_text = PROJECTIONS.read_text(encoding="utf-8")
    schema_text = SCHEMA.read_text(encoding="utf-8")
    persistence_text = PERSISTENCE.read_text(encoding="utf-8")

    assert projections_text.count(ASSIGNMENT_BLOCK) == 1, "K1 的靶漂了"
    assert projections_text.count(ASSIGNMENT_LINE) == 1, "K2 的靶漂了"
    assert schema_text.count(DECLARATION) == 1, "K3 的靶漂了"
    assert persistence_text.count(ADAPTER_TAIL) == 1, "K4 的靶漂了"