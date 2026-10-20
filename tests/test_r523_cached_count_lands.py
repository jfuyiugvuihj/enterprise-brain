# -*- coding: utf-8 -*-
r"""R523 判据②③⑥ —— cached 计数从应答走到 ``model_calls`` 那一列，NULL 与 0 分得开，谁都不许造数。

写链一律用真件，量具只借在册同族件，本件不自建第二套：
``app.trace.spans.start_model_call`` / ``model_token_counts`` → ``app.trace.store.TraceStore`` →
``app.storage.persistence.PostgresPersistenceAdapter`` → ``tests/_r250_fake_postgres.py``（在册
替身，与 ``tests/test_r250_*`` 同一台机器）。夹具数字全部现读真机落盘或 R29 逐字帧，一个都不
手抄：``tests/test_r146_cached_token_ledger.py`` 的 ``_compat_usage_from_think_off`` /
``_measured_zero_from_prodpath`` / ``_native_done_frames``。

第二道补令（总控裁决：不另开一单）之后，落库那半段在本件里跑通了：
``app/storage/persistence.py`` 的 ``_TABLES["model_calls"].columns`` 尾追了 ``cached_tokens``，
判据②不再只交承载面。三枚探针各管一段，缺一枚就是半笔：

* ``test_a_reported_count_*_reaches_the_writer`` 判「应答 → 递交给写库那一行」；
* ``test_a_reported_count_lands_in_the_column_and_reads_back`` 判「真发出去的 INSERT 点名这一列
  → 行落进库 → 再从库里读回来」，走的是在册替身 ``FakePostgres`` 记下的语句与它自己的表；
* ``test_the_adapter_column_tuple_and_the_declared_set_are_flush`` 把三副本（0018 的加列、
  ``TRACE_TABLE_COLUMNS``、适配器列元组）的对齐写成明账（``EXPECTED_ADAPTER_GAP`` 今天置空，
  与 ``tests/test_r248_artifact_column_alignment.py`` 的 ``DOCUMENTED_GAP`` 同形）：谁把列元组
  退回去，缺口重新张开就红。

🔴 仍然没有的那一格：真机读数。假库里的每个数都来自服务端报数或 R29 逐字帧，
E3 档 ``cached_tokens > 0`` 只能开窗量，见 ``docs/testing/r523-prompt-cache-tokens-2026-09-30.md`` §3。

全程离线：不连库、不起服务、不动容器、不打模型（conftest 的 R56 宿主模型端口闸门会记账）。
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

from app.common import model_budget
from app.common.model_handler import TRANSPORT_NATIVE, ModelHandler, ModelSource
from app.storage.persistence import PostgresPersistenceAdapter
from app.trace import spans
from app.trace.schema import TRACE_TABLE_COLUMNS, TraceSchemaError, require_columns
from app.trace.store import TraceStore
from tests._r250_fake_postgres import FakePostgres

REPO = Path(__file__).resolve().parents[1]
PAPER = REPO / "docs" / "testing" / "r523-prompt-cache-tokens-2026-09-30.md"
PROJECTIONS = REPO / "app" / "trace" / "projections.py"
SCHEMA = REPO / "app" / "trace" / "schema.py"
PERSISTENCE = REPO / "app" / "storage" / "persistence.py"
CONTRACT = REPO / "docs" / "api" / "contract-v1.md"
#: 契约里本单那一节的标题：裁定要求它落在**文末**（纯追加），不落中间。
CONTRACT_SECTION_HEADING = "## Cached-count carrier for `model_calls`"
#: 作废声明的固定说法：旧句留在原地，靠点名作废，不靠删掉来表态。
VOID_DECLARATION = "**that phrase is void from this section onward**"
#: 谁都不许在这些纸里写出的口径（半笔不算结案，实测读数也不算）。
FORBIDDEN_CALIBER = (
    "实测 cached_tokens > 0 已达成",
    "生产库已读到 cached",
    "落库已通",
)
STALE_CONTRACT_CLAIM = "`model_calls` has no cached column"

TABLE = "model_calls"
COLUMN = "cached_tokens"
#: R29 逐字帧里原生腿用来报 cached 的那一格名字。
NATIVE_CACHED_FIELD = "prompt_eval_cached_count"
#: 一个不存在的机器名：万一有缝没堵住，它也只能 DNS 失败，碰不到宿主模型端口。
SAFE_BASE_URL = "http://model.internal:11434/v1"

#: 适配器列元组相对声明集欠下的格。第二道补令后为**空集**：谁把它退回去，明账钉当场红。
EXPECTED_ADAPTER_GAP: frozenset = frozenset()


@pytest.fixture(autouse=True)
def _clean_durability_ledger():
    from app.trace import durability

    durability.reset_durability_ledger()
    yield
    durability.reset_durability_ledger()


# ------------------------------------------------------------------ 写链夹具（真件，无第二套）


class _RecordingAdapter(PostgresPersistenceAdapter):
    """记下递交给真适配器写 ``model_calls`` 那一步的整行，再原样交给父类去拼 SQL。

    记的是**递交**给写库那一步的东西。少了这一层，判据②就只剩自述：投影自己算得对，
    不等于库里那一行有这一列。
    """

    def __init__(self, connection_factory):
        super().__init__(connection_factory)
        self.handed: list[tuple[str, dict]] = []

    def upsert(self, collection, record_id, record):
        if collection == TABLE:
            self.handed.append((str(record_id), dict(record)))
        return super().upsert(collection, record_id, record)


def drive_one_model_call(tmp_path, monkeypatch, reply, *, trace_id: str):
    """把一枚应答喂进真那条写链，交回 ``(假库, 主键, 递交给适配器的行, 库里那一行)``。"""
    engine = FakePostgres()
    adapter = _RecordingAdapter(engine.connection_factory)
    store = TraceStore(tmp_path / f"{trace_id}.jsonl", persistence=adapter)
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    config = {
        "configurable": {
            "principal": _principal(trace_id),
            "request_id": f"req-{trace_id}",
            "trace_id": trace_id,
            "task_id": f"task-{trace_id}",
            "worker": "doc",
            "step_id": f"{trace_id}:worker:doc",
        }
    }

    span = spans.start_model_call(config, provider="ollama", model_name="qwen3.5:9b")
    span.finish("completed", summary=spans.model_token_counts(reply))

    #: 一发调用写两笔同一主键的行：model.started 建行，model.finished 带着计数改行。
    #: 判据看的是最后那一笔（计数只在 finished 上），两笔必须是同一个 model_call_id。
    ids = [record_id for record_id, _row in adapter.handed]
    assert len(adapter.handed) == 2, adapter.handed
    assert len(set(ids)) == 1, ids
    record_id, handed = adapter.handed[-1]
    return engine, record_id, handed, engine.rows(TABLE).get(record_id)


def _principal(trace_id: str):
    from app.agents.contracts import Principal

    return Principal(user_id=f"u-{trace_id}", username=f"staff-{trace_id}", roles=["staff"])


def native_reply_from_frame(monkeypatch, frame):
    """只经过真 ``ModelHandler.chat`` 这一道出口，三枚计数全部来自那一枚逐字 done 帧。"""
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", SAFE_BASE_URL)
    monkeypatch.setenv("LOCAL_MODEL_NAME", str(frame.get("model") or "qwen3.5:9b"))
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    handler = ModelHandler()
    monkeypatch.setattr(
        handler, "_native_chat_request", lambda url, payload, *, timeout: dict(frame)
    )
    reply = handler.chat(
        messages=[{"role": "user", "content": "改写这个问题"}],
        source=ModelSource.LOCAL,
        stream=False,
    )
    assert reply.transport == TRANSPORT_NATIVE
    return reply


def _native_frame_that_reports_a_cached_count() -> dict:
    from test_r146_cached_token_ledger import _native_done_frames

    for frame in _native_done_frames():
        counts = [frame.get(name) for name in (NATIVE_CACHED_FIELD, "prompt_eval_count", "eval_count")]
        if all(isinstance(value, int) for value in counts) and frame[NATIVE_CACHED_FIELD] > 0:
            return frame
    raise AssertionError(
        "R29 的逐字 done 帧里没有「三枚计数都报了且 cached > 0」的那一枚：前提变了，本件要重读"
    )


def _compat_triplet() -> tuple[int, int, int]:
    from test_r146_cached_token_ledger import _compat_usage_from_think_off

    return _compat_usage_from_think_off()


def _langchain_reply(prompt, completion, cached):
    from test_r146_cached_token_ledger import _langchain_reply as build

    return build(prompt, completion, cached)


def compat_reply(*, cached):
    """兼容腿（非流式）的三种脸：报了数 / 报了 0 / 什么都没报。数字取自真机落盘。"""
    if cached == "reported":
        prompt, completion, reported = _compat_triplet()
        return _langchain_reply(prompt, completion, reported)
    if cached == "zero":
        from test_r146_cached_token_ledger import _measured_zero_from_prodpath

        prompt, completion = _measured_zero_from_prodpath()
        return _langchain_reply(prompt, completion, 0)
    prompt, completion, _reported = _compat_triplet()
    return _langchain_reply(prompt, completion, None)


# ------------------------------------------------------------------ 判据探针（刀与真件共用）


def probe_reported_count_is_handed_to_the_writer(handed, expected):
    """递交给写库那一步的行必须带着那枚读数，带的还是原值。"""
    assert handed.get(COLUMN) == expected, (
        f"{COLUMN} 没走到写库那一步：行上是 {handed.get(COLUMN)!r}"
        f"（行上的键：{sorted(handed)}），应答报的是 {expected!r}"
    )


def probe_count_lands_in_the_database_row(stored, expected):
    """库里那一行读回来还是这枚数 —— 判据②要的「真写进去再读回来」。"""
    assert stored is not None, "行没写进假库"
    assert stored.get(COLUMN) == expected, (
        f"库里那行没有 {COLUMN}：真发出去的 INSERT 只点了 {sorted(stored)}"
    )


def probe_absent_reading_is_null(handed):
    """没报的那一发必须是 NULL：既不是 0，也不是整格缺席（缺席＝这一列没被声明）。"""
    assert COLUMN in handed, f"行上根本没有这一列：{sorted(handed)}"
    assert handed[COLUMN] is None, f"没报数却被读成了 {handed[COLUMN]!r}"


def probe_reported_zero_is_zero(handed):
    """报了 0 的那一发必须是 0，且与上一枚探针不同脸。"""
    assert handed[COLUMN] == 0, f"服务端报了 0，行上却是 {handed[COLUMN]!r}"
    assert handed[COLUMN] is not None, "0 不是 None：两枚探针判的是两种不同的读数"


def issued_model_call_inserts(engine):
    """假库记下的、**真发出去**的 ``model_calls`` INSERT：列名与参数逐位对齐后交回。

    判据②不许靠「这列在 schema 里」推断：要的是适配器拼给驱动的那条语句点名了它。
    """
    prefix = f"INSERT INTO {TABLE} ("
    found = []
    for sql, params in engine.statements:
        if not sql.startswith(prefix):
            continue
        names = [name.strip() for name in sql[len(prefix):sql.index(")")].split(",")]
        assert len(names) == len(params), (names, params)
        found.append((dict(zip(names, params)), sql))
    assert found, "假库里一条发给 model_calls 的 INSERT 都没有：写链没走到库"
    return found


def probe_the_issued_insert_names_the_column(engine, expected):
    """两笔写库（started 建行 / finished 带计数改行）都必须点上这一列，最后一笔是那枚读数。"""
    inserts = issued_model_call_inserts(engine)
    for row, sql in inserts:
        assert COLUMN in row, f"发出去的 INSERT 没点这一列：{sql[:200]}"
    assert inserts[-1][0][COLUMN] == expected, inserts[-1][0]


def read_back_the_column(engine, record_id):
    """从库里读回来：走在册替身自己的 SELECT 通道，不碰任何内存变量。"""
    connection = engine.connection()
    try:
        result = connection.execute(
            f"SELECT {COLUMN} FROM {TABLE} WHERE model_call_id = %s", (record_id,)
        )
        row = result.fetchone()
    finally:
        connection.close()
    assert row is not None, f"{TABLE} 里没有主键 {record_id} 这一行"
    return row[0]


#: 本单的工单号：判「本节之后躺着的节是不是更晚立案的」要用它。
TICKET_NUMBER = 523


def _heading_ticket(heading: str) -> int | None:
    """从一枚 `## ` 标题里取工单号；没有就回 None（尾追加必须自报号，见下面那一格）。"""
    found = re.search(r"R(\d{2,4})", heading)
    return int(found.group(1)) if found else None


def contract_cached_note(text: str) -> str:
    """取出契约里本单那一节（标题到下一枚 `## ` 之前），供守卫与刀共用。

    顺手钉三件事：这一节在整份文件里恰一枚；本节之后**只许长更晚立案的单的节**；
    而本节自己的正文里不许有读数（由调用方那枚 `find_unowed_numbers` 管）。

    改口（2026-10-01 · 总控动手，执行层写域外）：原句是 `text.rindex("\n## ") == start`，
    钉的是「我是契约上最后一节」。可 `docs/api/contract-v1.md` 是 append-only 的跨栈公共面，
    而 `contract_is_pure_append` 又要求 HEAD 那版必须是新版的前缀（⇒ 本节的位子动不得）——
    两枚钉合起来等于宣布「本契约从此不许再有任何 `## ` 级尾追加」，与总控 §142 裁定①
    「契约只许尾追加」直接冲突，R558 那节（队列道逐字片段）就是长在本单之后的第一枚合法尾追加。
    同族先例与口径照抄 ``tests/test_r397_read_legs_refuse_a_missing_table.py:571``
    （09-28 总控对同一枚病的改法：把「我是最后一节」换成「我的前身是谁」）。
    🔴 改成「本节之后不许有更早立案的节、也不许有不报号的节」之后，本格仍然挡得住原句想挡的那件事
    （把口径写回中间＝前面那些 `R<523` 的节会有一枚跑到本节后面），而且比原句多挡一件：
    尾追加不报工单号。旧句那条「本节必须永远在最后」从今天起不再成立，写在这里当账，不偷偷放宽。
    """
    assert text.count(CONTRACT_SECTION_HEADING) == 1, "本单那一节要么没写，要么写了两处"
    start = text.index("\n" + CONTRACT_SECTION_HEADING)
    body_from = start + 1 + len(CONTRACT_SECTION_HEADING)
    nxt = re.search(r"(?m)^## ", text[body_from:])
    if nxt is None:
        return text[start + 1:]
    end = body_from + nxt.start()
    following = re.findall(r"(?m)^## .*$", text[end:])
    stale = [h for h in following if (n := _heading_ticket(h)) is not None and n < TICKET_NUMBER]
    assert not stale, (
        "本单那一节之后躺着更早立案的节（口径被搬回中间了）：" + str([h[:48] for h in stale[:3]])
    )
    unnumbered = [h for h in following if _heading_ticket(h) is None]
    assert not unnumbered, (
        "契约文末长出没有工单号的节：尾追加必须自报号，本格才认得出它比本单晚 "
        + str([h[:48] for h in unnumbered[:3]])
    )
    return text[start + 1:end]


def contract_is_pure_append(text: str) -> bool:
    """拿 ``git show HEAD:`` 的原文比：文末之前每一个字都不许动（照 r367 那枚钉的口径）。"""
    result = subprocess.run(
        ["git", "-C", str(REPO), "show", "HEAD:docs/api/contract-v1.md"],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return text.startswith(result.stdout.decode("utf-8").replace("\r\n", "\n"))


def find_unowed_numbers(note: str) -> list[str]:
    """那段口径里除 ``run10`` 这个名次以外的一切数字。

    派工词对契约那一格的话是「只准写承载面已就位／实测读数待 run10，禁止出现任何数字」——
    所以这里数的不是钱，是「有没有人把某枚读数写进契约冒充事实」。
    """
    return re.findall(r"\d+", note.replace("run10", ""))


def find_subtracted_cached_readings(source: str, *, name: str = "<source>") -> list[str]:
    """在**可执行代码**里找「用别的计数减出 cached」的形状（走 AST，不读散文）。"""
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub):
            rendered = ast.unparse(node)
            if "cached" in rendered.lower():
                hits.append(f"{name}:{node.lineno}: {rendered}")
    return hits


# ------------------------------------------------------------------ 判据②：一行真数据端到端


def test_a_reported_count_from_the_native_frame_reaches_the_writer(tmp_path, monkeypatch):
    """原生腿：逐字 done 帧报了 cached，行就带着它走到写库那一步。"""
    frame = _native_frame_that_reports_a_cached_count()

    _engine, _record_id, handed, _stored = drive_one_model_call(
        tmp_path,
        monkeypatch,
        native_reply_from_frame(monkeypatch, frame),
        trace_id="r523-native",
    )

    probe_reported_count_is_handed_to_the_writer(handed, frame[NATIVE_CACHED_FIELD])
    assert handed["input_tokens"] == frame["prompt_eval_count"], handed
    assert handed["output_tokens"] == frame["eval_count"], handed


def test_a_reported_count_from_the_compatible_leg_reaches_the_writer(tmp_path, monkeypatch):
    """兼容腿非流式那一发：``usage.prompt_tokens_details.cached_tokens`` 同样走到写库那一步。"""
    _prompt, _completion, expected = _compat_triplet()

    _engine, _record_id, handed, _stored = drive_one_model_call(
        tmp_path, monkeypatch, compat_reply(cached="reported"), trace_id="r523-compat"
    )

    probe_reported_count_is_handed_to_the_writer(handed, expected)


def test_a_reported_count_lands_in_the_column_and_reads_back(tmp_path, monkeypatch):
    """判据②的落库半段（第二道补令后转真跑）：INSERT 点名 → 行落库 → 从库里读回来。

    全程走真件：``spans`` → ``TraceStore`` → ``PostgresPersistenceAdapter._statement`` 拼出的那条
    SQL → 在册替身 ``FakePostgres`` 的表。没有任何一格是内存变量冒充的：读回来用的是替身的
    ``SELECT``，值来自 ``docs/perf/raw/think_off.jsonl`` 现读的报数。
    """
    _prompt, _completion, expected = _compat_triplet()

    engine, record_id, handed, stored = drive_one_model_call(
        tmp_path, monkeypatch, compat_reply(cached="reported"), trace_id="r523-land"
    )

    probe_reported_count_is_handed_to_the_writer(handed, expected)
    probe_the_issued_insert_names_the_column(engine, expected)
    probe_count_lands_in_the_database_row(stored, expected)
    assert read_back_the_column(engine, record_id) == expected, "库里读回来的不是那枚数"


def test_the_projection_is_sealed_against_the_declared_column_set():
    """这一列在契约里：声明集点名它，投影少带它就被拒。第三份副本（适配器列元组）另判。"""
    assert COLUMN in TRACE_TABLE_COLUMNS[TABLE]
    complete = set(TRACE_TABLE_COLUMNS[TABLE])

    require_columns(TABLE, complete)
    with pytest.raises(TraceSchemaError) as refused:
        require_columns(TABLE, complete - {COLUMN})
    assert COLUMN in str(refused.value)


def test_the_adapter_column_tuple_and_the_declared_set_are_flush():
    """三份副本今天必须对齐：0018 加的列 == ``TRACE_TABLE_COLUMNS`` == 适配器列元组。

    这枚是明账，不是装饰：``EXPECTED_ADAPTER_GAP`` 今天置空，谁把 ``persistence.py`` 那格
    退回去，缺口重新张开就红（第二道补令前它写的正是 ``frozenset({COLUMN})``）。
    """
    from app.storage.persistence import _TABLES

    declared = set(TRACE_TABLE_COLUMNS[TABLE])
    adapter_columns = set(_TABLES[TABLE].columns)

    assert declared - adapter_columns == set(EXPECTED_ADAPTER_GAP), (
        f"{TABLE} 的声明集与适配器列元组差 {sorted(declared - adapter_columns)}，"
        f"明账写的是 {sorted(EXPECTED_ADAPTER_GAP)}"
    )
    assert adapter_columns - declared == set(), (
        f"适配器多写了一枚契约里没声明的列：{sorted(adapter_columns - declared)}"
    )


# ------------------------------------------------------------------ 判据③：NULL 与 0 是两种读数


def test_an_unreported_round_is_null_and_a_reported_zero_is_zero(tmp_path, monkeypatch):
    """两枚分别断言：没报 = NULL，报了 0 = 0。合成一列就等于把「流说不出来」写成「没命中」。"""
    null_engine, null_id, unreported, _null_stored = drive_one_model_call(
        tmp_path, monkeypatch, compat_reply(cached="absent"), trace_id="r523-null"
    )
    zero_engine, zero_id, reported_zero, _zero_stored = drive_one_model_call(
        tmp_path, monkeypatch, compat_reply(cached="zero"), trace_id="r523-zero"
    )

    probe_absent_reading_is_null(unreported)
    probe_reported_zero_is_zero(reported_zero)
    assert unreported[COLUMN] is not reported_zero[COLUMN] or unreported[COLUMN] is None

    #: 两种脸必须一路带到库里：0018 没给默认值、投影没做减法，库读回来才还是两种脸。
    assert read_back_the_column(null_engine, null_id) is None
    assert read_back_the_column(zero_engine, zero_id) == 0


def test_a_streamed_answer_round_cannot_report_one_and_stays_null(tmp_path, monkeypatch):
    """流式答案腿根本没有 usage 可取 ⇒ 这一列只能是 NULL，不是 0，也不是估算值。"""
    from langchain_core.messages import AIMessageChunk
    from test_r146_cached_token_ledger import _compat_stream_frames

    frames = _compat_stream_frames()
    assert frames, "R29 的流式逐字帧读不到：前提变了"
    for frame in frames:
        assert "usage" not in frame, f"流里长出 usage 了，本件前提要重读：{frame}"

    _engine, _record_id, handed, _stored = drive_one_model_call(
        tmp_path, monkeypatch, AIMessageChunk(content="嗯"), trace_id="r523-stream"
    )

    probe_absent_reading_is_null(handed)


def test_no_product_source_subtracts_a_cached_reading():
    """五枚相关文件里，没有任何一处用别的计数减出 cached（AST 判，散文不算）。"""
    relative = (
        "app/trace/spans.py",
        "app/trace/projections.py",
        "app/trace/schema.py",
        "app/common/model_handler.py",
        "app/agents/nodes.py",
    )

    hits = [
        hit
        for name in relative
        for hit in find_subtracted_cached_readings(
            (REPO / name).read_text(encoding="utf-8"), name=name
        )
    ]

    assert hits == [], "有人把减法当成读数写进账了：" + " | ".join(hits)


def test_the_ticket_paper_declares_the_cell_it_did_not_measure():
    """判据⑥：纸必须写明「承载面已就位、真机读数仍欠」，两处不许被读成实测。

    这条钉的是纸，不是代码：``run10`` 之前谁都不许把「列有了、写进去了」写成「cached > 0 量到了」；
    第二道补令把落库那半段做完之后，口径只许往「欠读数」这一格收，不许往外扩。
    """
    text = PAPER.read_text(encoding="utf-8")

    for clause in (
        "承载面已就位",
        "写进库再读回来",
        "cached_tokens > 0",
        "run10",
        "流式答案腿无 usage 可取",
        "跟进单 §74 四、§81",
    ):
        assert clause in text, f"纸上少了这句：{clause}"
    assert "未达" in text, "纸里必须有一格写着未达，不许交出一张全绿的表"
    for forbidden in FORBIDDEN_CALIBER:
        assert forbidden not in text, f"纸里出现了越界的口径：{forbidden}"


def test_the_contract_note_keeps_the_declared_caliber():
    """裁定 1(c)：旧句**仍在**契约文内，由文末那一节点名宣布作废；那一节本身零读数。"""
    text = CONTRACT.read_text(encoding="utf-8")
    note = contract_cached_note(text)

    #: 两格同咬的第一格：不靠删除来表态。
    assert STALE_CONTRACT_CLAIM in text, (
        " blockers[] 表里那句旧话不见了：作废必须是点名作废，不是把假话抹掉装作没写过"
    )
    #: 第二格：文末那一节确实作废了它，并说清真源在哪。
    assert VOID_DECLARATION in note, "文末那一节没写下作废声明"
    assert STALE_CONTRACT_CLAIM in note, "作废声明没点名被作废的那句原话"
    assert "native_leg_reports_no_cached_tokens" in note, "没写清作废的是 blockers[] 里哪一行"
    assert contract_is_pure_append(text), "契约不是纯追加：文末之前动过字（r367 同形判据）"

    for clause in ("NULL", "run10", "cache-hit rate"):
        assert clause in note, f"契约那段少了这句口径：{clause}"
    assert find_unowed_numbers(note) == [], (
        "契约里本单那段出现了数字：那一格只许写承载面与待 run10，读数不许进契约 —— "
        + str(find_unowed_numbers(note))
    )
    for forbidden in FORBIDDEN_CALIBER:
        assert forbidden not in text, f"契约里出现了越界的口径：{forbidden}"


def test_the_append_teeth_bite_on_synthetic_poisons():
    """合成刀三把：中间插一句 ⇒ 纯追加那格红；更晚立案的尾追加 ⇒ 不许红且不被并进本段；
    更早立案的节被挪到本节之后 ⇒ 「我的前身是谁」那格红；尾追加不报工单号 ⇒ 同样红。

    上一班的教训就写在这枚件里：正则永不匹配的牙不如不装。这里不动盘上文件，只拿内存副本判。
    10-01 改口理由见 `contract_cached_note` 的 docstring（同族先例 r397:571）。
    """
    text = CONTRACT.read_text(encoding="utf-8")
    cut = len(text) // 2
    mid_edit = text[:cut] + "有人在中途加了一句\n" + text[cut:]
    assert not contract_is_pure_append(mid_edit), "中间改写没被抓住：这枚牙是死牙"

    #: 合法那一形（今天盘上就长着）：更晚立案的尾追加不许红——原句把这形判红才是自毁。
    later = text + "\n## R999 · somebody appended after us\n\ntext\n"
    note = contract_cached_note(later)
    assert "## R999" not in note, "尾追加被并进了本节正文：取节那一手没在下一枚 `## ` 前收口"

    moved = text + "\n## R509 · a predecessor moved behind us\n\ntext\n"
    try:
        contract_cached_note(moved)
    except AssertionError as caught:
        assert "搬回中间" in str(caught), str(caught)
    else:
        raise AssertionError("更早立案的节躺在本节之后而那一格没红：死牙")

    unnamed = text + "\n## Somebody appended without a ticket number\n\ntext\n"
    try:
        contract_cached_note(unnamed)
    except AssertionError as caught:
        assert "没有工单号" in str(caught), str(caught)
    else:
        raise AssertionError("尾追加不报工单号而那一格没红：死牙")


def test_the_contract_caliber_guard_bites_on_a_poisoned_note():
    """正控：把一枚读数塞进那段口径，数字守卫必须点名它（不然这枚牙就是死牙）。"""
    note = contract_cached_note(CONTRACT.read_text(encoding="utf-8"))
    poisoned = note + " measured 292 cached of 543 prompt on product traffic"

    assert find_unowed_numbers(note) == []
    assert find_unowed_numbers(poisoned) == ["292", "543"], find_unowed_numbers(poisoned)


def test_the_subtraction_guard_bites_on_a_poisoned_copy_of_the_real_source():
    """正控（上一班刚踩过死牙）：把真 projections.py 里那一枚赋值换成减法，守卫必须点名它。"""
    source = PROJECTIONS.read_text(encoding="utf-8")
    anchor = '"cached_tokens": _first(summary.get("cached_tokens"), current.get("cached_tokens")),'
    poisoned = '"cached_tokens": summary.get("input_tokens") - summary.get("cached_tokens"),'

    assert source.count(anchor) == 1, "锚点漂了，这把正控刀会空转"
    assert find_subtracted_cached_readings(source, name="pristine") == []

    hits = find_subtracted_cached_readings(source.replace(anchor, poisoned), name="poisoned")

    assert len(hits) == 1, hits
    assert "cached" in hits[0]