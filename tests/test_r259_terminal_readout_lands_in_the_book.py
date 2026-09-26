# -*- coding: utf-8 -*-
"""R259 判据②③：`/queue/status` 多交的那批终态读数必须进账，而 D-2 / D-3 两格要变得可判。

判据原文（派工词 R259 ②）：把 ``terminal_state`` / ``answer_present`` / ``sources_present`` /
``len(sources)`` / ``sources_error`` / ``usage``（``prompt_tokens``、``completion_tokens``、
``total_tokens``、``model_calls``、``authoritative``、``ledger``）折进 ``book`` —— 那枚「取回账」，
由 ``transport`` 塞进帧账 ``queue`` 那一格。诚实口径三条，缺一枚就是假话：

  ① 键根本不在位（``terminal_schema: "legacy"`` / ``terminal_state: "legacy_row"``）⇒ 记成
     「这一行说不出」，不许拿 0 或空表冒充「查过，是零」；
  ② 载荷在位但读不出（``unreadable_terminal``）⇒ 另记一枚形状，与 legacy 分开；
  ③ ``usage`` 里 ``authoritative: false`` ⇒ 必须带着这个标志进账，不许把它洗掉。

判据③：run8 相 2 里 D-2 红在「可读面没有 usage」、D-3 红在「``sources`` 0/20」
（``docs/testing/run8-phase2-readout-2026-09-25.md`` §1）。达标线不是分数变好，是这两格从
「无从判定」变成**有字段可算**：D-2 读 ``queue.terminal.usage_present`` + ``queue.terminal.usage``
的 ``authoritative`` / ``total_tokens`` / ``model_calls``；D-3 读 ``queue.terminal.sources_n`` /
``sources_present`` / ``sources_error`` / ``shape``。两枚读法都写在 ``_r259_queue_ruler`` 里，
逐枚有名，且 ``row_cannot_say`` 与 ``read_zero`` 永远是两件事。

反证两把（判据④）：``launder_usage`` 摘掉 usage 采集 ⇒ 点名的 ``assert_usage_landed`` 红；
``launder_legacy_sources`` 把 legacy 行照抄成「零枚出处」⇒ 点名的 ``assert_legacy_cannot_say``
红。变异只落影子副本（R253 纪律），原件 sha 逐枚复验。全程离线，产物落 tmp_path。
"""
import json

import pytest

from tests import _r259_queue_ruler as Q

SCRIPT_PATH = Q.SCRIPT_PATH
#: 反证乙：摘掉 usage 采集（那一格从此进不了账）。
DROP_USAGE = ('    usage = body.get("usage")',
              '    usage = None  # 反证乙：把 usage 采集摘掉')
#: 反证丙：把「这一行说不出」照抄成「查过了，零枚」。
LAUNDER_LEGACY = ("    return shape in SOURCES_READABLE_SHAPES",
                  "    return True  # 反证丙：旧行的占位空表也照抄成读数")


@pytest.fixture
def adapter(tmp_path):
    return Q.configure(Q.load("r259_readout"), tmp_path, name="r259-b")


def book_of(module, body):
    """把一枚终态载荷读到停表，回它的取回账。"""
    (kind, _answer, book), fake = Q.poll(module, [json.loads(json.dumps(body))] * 5)
    assert len(fake.queue_reads) == 1, kind
    return book


def assert_usage_landed(book):
    """判据② / ③ 的点名断言（D-2）：token 读数逐槽进账，且带着 ``authoritative`` 那枚名分。"""
    terminal = book.get("terminal") or {}
    assert terminal.get("usage_present") is True, (
        "usage_present=" + repr(terminal.get("usage_present"))
        + " ⇒ 客户端读到的 token 读数没进取回账（判据② / D-2）")
    usage = terminal.get("usage") or {}
    assert usage.get("prompt_tokens") == 91271, usage
    assert usage.get("completion_tokens") == 18859, usage
    assert usage.get("total_tokens") == 110130, usage
    assert usage.get("model_calls") == 70, usage
    assert usage.get("authoritative") is True, usage
    assert usage.get("ledger") == "postgres_model_calls", usage
    return terminal


def assert_legacy_cannot_say(book):
    """判据② 第一条口径的点名断言（D-3）：旧行只能说「我说不出」，不许被读成「零枚出处」。"""
    terminal = book.get("terminal") or {}
    assert terminal.get("shape") == "legacy", terminal.get("shape")
    assert terminal.get("sources_n") is None, (
        "sources_n=" + repr(terminal.get("sources_n"))
        + " ⇒ 把「这一行说不出」洗成了「查过了，零枚」（判据② 第一条口径）")
    assert terminal.get("sources_present") is None
    assert terminal.get("sources_error") is None
    assert Q.sources_cell({"terminal": terminal}) == "row_cannot_say"
    return terminal


# ==================== ② 结构化终态：读数逐槽进账 ====================

def test_a_structured_done_row_folds_the_whole_terminal_readout(adapter):
    """一枚真答完的队列行：契约那十一格逐枚有名，取值口径与契约样例逐字相同。"""
    terminal = book_of(adapter, Q.answered_body())["terminal"]
    assert terminal == {"shape": "structured", "usage_present": True,
                        "approval_present": False, "schema": "queue-terminal-v1",
                        "state": "answered", "answer_present": True,
                        "answer_is_park_notice": False, "worker_status": "success",
                        "sources_present": True, "sources_n": 3, "sources_error": "",
                        "scope_reason_code": "department_and_classification",
                        "usage": Q.usage_readout(), "approval_steps": None,
                        "approval_ledger_status": None, "approval_notice_chars": None,
                        "terminal_note": ""}, json.dumps(terminal, ensure_ascii=False)
    assert_usage_landed(book_of(adapter, Q.answered_body()))


def test_zero_sources_and_no_sources_are_two_different_readings(adapter):
    """判据② 的正反两枚：结构化行的「零枚」是真读数，旧行的空表不是。"""
    zero = book_of(adapter, Q.answered_body(sources=[], sources_present=False))["terminal"]
    assert (zero["sources_n"], zero["sources_present"], zero["sources_error"]) == (0, False, "")
    assert Q.sources_cell({"terminal": zero}) == "read_zero"
    legacy = book_of(adapter, Q.legacy_row_body())["terminal"]
    assert (legacy["sources_n"], legacy["sources_present"]) == (None, None)
    assert Q.sources_cell({"terminal": legacy}) == "row_cannot_say"


def test_a_sources_error_says_could_not_compute_not_zero(adapter):
    """``sources_error`` 非空 = 压根没算成（第三件事），不许与「零枚」「说不出」混读。"""
    book = book_of(adapter, Q.answered_body(sources=[], sources_present=False,
                                            sources_error="answer_cache_without_manifest"))
    terminal = book["terminal"]
    assert terminal["sources_n"] == 0 and terminal["sources_error"]
    assert Q.sources_cell(book) == "not_computable"


def test_a_non_authoritative_ledger_arrives_with_the_flag_intact(adapter):
    """判据② 第三条口径：``authoritative: false`` 原样进账（那本账只有一台机器看得见）。"""
    body = Q.answered_body(usage=Q.usage_readout(authoritative=False,
                                                 ledger="persistence_model_calls"))
    terminal = book_of(adapter, body)["terminal"]
    assert terminal["usage"]["authoritative"] is False
    assert terminal["usage"]["ledger"] == "persistence_model_calls"
    assert terminal["usage"]["total_tokens"] == 110130, "数照抄，只把名分改口"
    assert Q.usage_cell({"terminal": terminal}) == "read_local_ledger"


def test_a_silent_ledger_stays_silent(adapter):
    """台账读不到时后端交四枚 null：量具照 null 记，一枚都不许折算成零。"""
    body = Q.answered_body(usage=Q.usage_readout(
        prompt_tokens=None, completion_tokens=None, total_tokens=None, model_calls=None,
        calls_with_token_readout=None, calls_missing_token_readout=None,
        token_readout_complete=False, authoritative=False, ledger="ledger_unavailable"))
    terminal = book_of(adapter, body)["terminal"]
    assert terminal["usage_present"] is True
    assert terminal["usage"]["total_tokens"] is None
    assert terminal["usage"]["model_calls"] is None
    assert terminal["usage"]["authoritative"] is False
    assert Q.usage_cell({"terminal": terminal}) == "read_ledger_silent"


def test_the_parked_row_carries_the_approval_handle_but_not_the_notice(adapter):
    """挂起那一轮：可批准的东西进账，那句 37 字文案只留字数（不许换个格子回正文面）。"""
    terminal = book_of(adapter, Q.parked_body())["terminal"]
    assert (terminal["shape"], terminal["state"]) == ("structured", "awaiting_approval")
    assert terminal["approval_present"] is True
    assert terminal["approval_steps"] == ["export"]
    assert terminal["approval_ledger_status"] == "awaiting"
    assert terminal["approval_notice_chars"] == len(Q.PARK_NOTICE)
    assert terminal["answer_present"] is False
    assert Q.PARK_NOTICE not in json.dumps(terminal, ensure_ascii=False)
    assert_usage_landed_and_parked(adapter, terminal)


def assert_usage_landed_and_parked(adapter, terminal):
    """挂起那一轮的 token 读数也在账上（412 / 0 / 412 / 1，权威台账），只是格数与正文两空。"""
    usage = terminal["usage"]
    assert (usage["prompt_tokens"], usage["completion_tokens"]) == (412, 0)
    assert (usage["total_tokens"], usage["model_calls"]) == (412, 1)
    assert usage["authoritative"] is True
    assert terminal["sources_n"] == 0 and Q.sources_cell({"terminal": terminal}) == "read_zero"
    return True


# ==================== ② 三枚「说不出」的形状彼此不同名 ====================

def test_a_legacy_row_is_recorded_as_unable_to_say(adapter):
    """旧行（run8 那 11 枚的家）：出处/token/批准把手三格当年没落账 ⇒ 记 None，不记零。"""
    book = book_of(adapter, Q.legacy_row_body())
    assert_legacy_cannot_say(book)
    terminal = book["terminal"]
    assert terminal["schema"] == "legacy" and terminal["state"] == "legacy_row"
    assert terminal["usage"] is None and terminal["usage_present"] is False
    assert Q.usage_cell(book) == "row_cannot_say"
    assert terminal["terminal_note"], "旧行那句「我说不出」得留在账上"


def test_a_legacy_row_handing_back_the_notice_is_named_as_one(adapter):
    """run8 相 2 那 11 枚的形状：正文位置上是挂起文案 —— 量具认得它，不再当正文交回。"""
    terminal = book_of(adapter, Q.legacy_row_body(park_notice=True))["terminal"]
    assert terminal["answer_present"] is True, "旧行只读得出「有没有一句字」"
    assert terminal["answer_is_park_notice"] is True
    assert Q.usage_cell({"terminal": terminal}) == "row_cannot_say"


def test_corruption_and_legacy_are_two_different_diagnoses(adapter):
    """判据② 第二条口径：``unreadable_terminal`` 另记一枚形状，与 legacy 不许混。"""
    legacy = book_of(adapter, Q.legacy_row_body())["terminal"]
    broken = book_of(adapter, Q.unreadable_row_body())["terminal"]
    assert (legacy["shape"], broken["shape"]) == ("legacy", "unreadable")
    assert broken["schema"] == "unreadable" and broken["state"] == "unreadable_terminal"
    for terminal in (legacy, broken):
        assert terminal["sources_n"] is None and terminal["usage"] is None
    assert legacy["terminal_note"] != broken["terminal_note"]
    assert broken["answer_present"] is True, "损坏行仍读得出「有没有正文」"


def test_a_row_from_a_server_without_these_keys_says_nothing(adapter):
    """更老的读路（R222 那扇窗看见的形状）：一个字都不许现填，而 kind 与正文照旧。"""
    body = Q.bare_done_body()
    (kind, answer, book), _fake = Q.poll(adapter, [body])
    terminal = book["terminal"]
    assert kind == "queued_polled" and answer == Q.ANSWER, "判据⑤：取回正文那一枚不许被本单带回退化"
    assert terminal["shape"] == "no_keys"
    for slot in ("sources_n", "sources_present", "sources_error", "usage", "schema", "state"):
        assert terminal[slot] is None, slot
    assert terminal["usage_present"] is False and terminal["approval_present"] is False
    assert Q.usage_cell(book) == "row_cannot_say"
    assert Q.sources_cell(book) == "row_cannot_say"


@pytest.mark.parametrize("status", ["cancelled", "dead", "expired", "failed"])
def test_an_undocumented_terminal_says_nothing_but_still_stops(adapter, status):
    """契约没给这五枚状态交读数键 ⇒ 形状 no_keys，而停表与 kind 一字不改（判据⑤）。"""
    (kind, _answer, book), fake = Q.poll(adapter, [Q.bare_done_body(status=status)] * 5)
    assert kind == "queued_" + status and book["final"] == status
    assert len(fake.queue_reads) == 1 and adapter.time.slept == []
    assert book["terminal"]["shape"] == "no_keys"


@pytest.mark.parametrize("statuses,label", [
    ([{"status": "processing"}] * 500, "queued_stalled"),
    ([Q.url_error()] * 400, "queued_no_status")])
def test_a_watch_that_never_read_a_terminal_says_so(adapter, statuses, label):
    """没读到终局那一族：``terminal.shape = not_terminal``，两格都读「没读到」，不读成零。"""
    (kind, _answer, book), _fake = Q.poll(adapter, list(statuses))
    assert kind == label, kind
    assert book["terminal"]["shape"] == "not_terminal"
    assert Q.usage_cell(book) == "no_terminal_read"
    assert Q.sources_cell(book) == "no_terminal_read"


# ==================== ③ D-2 / D-3 两格从「无从判定」变成「有字段可算」 ====================

MATRIX = (
    ("answered", Q.answered_body()),
    ("answered_zero_sources", Q.answered_body(sources=[], sources_present=False)),
    ("answered_no_manifest", Q.answered_body(sources=[], sources_present=False,
                                             sources_error="answer_cache_without_manifest")),
    ("parked", Q.parked_body()),
    ("legacy", Q.legacy_row_body()),
    ("legacy_park_notice", Q.legacy_row_body(park_notice=True)),
    ("corrupt", Q.unreadable_row_body()),
    ("no_keys", Q.bare_done_body()),
    ("dead", Q.bare_done_body(status="dead")),
)


def test_the_frame_ledger_rows_answer_both_cells(adapter, tmp_path):
    """逐题落盘之后，D-2 与 D-3 两格**只从账件里**算得出来，一枚都不必翻日志。"""
    for index, (label, body) in enumerate(MATRIX):
        Q.drive_queue(adapter, [body] * 5, row_id="doc-%02d" % index)
    rows = Q.read_jsonl(adapter.frame_ledger_path())
    assert len(rows) == len(MATRIX)
    usage = {}
    sources = {}
    for (label, _body), row in zip(MATRIX, rows):
        assert row["queue"], label
        usage[label] = Q.usage_cell(row["queue"])
        sources[label] = Q.sources_cell(row["queue"])
    assert usage["answered"] == "read_authoritative"
    assert usage["legacy"] == usage["corrupt"] == usage["no_keys"] == "row_cannot_say"
    assert sources["answered"] == "read_some" and sources["answered_zero_sources"] == "read_zero"
    assert sources["answered_no_manifest"] == "not_computable"
    assert sources["legacy"] == sources["corrupt"] == sources["no_keys"] == "row_cannot_say"
    assert sources["legacy_park_notice"] == "row_cannot_say", "旧行那 11 枚不许读成「零枚出处」"
    assert sources["dead"] == "row_cannot_say" and usage["dead"] == "row_cannot_say"
    assert set(usage.values()) <= set(Q.USAGE_CELLS) and set(sources.values()) <= set(Q.SOURCES_CELLS)


def test_the_readouts_never_enter_the_sidecar_row(adapter):
    """判据⑥：读数只长在一格里，sidecar 那一行的键集（甲案七键子集钉）一个字没多。"""
    Q.drive_queue(adapter, [Q.answered_body()] * 5)
    record = Q.read_jsonl(adapter.SIDECAR)[0]
    assert tuple(list(record)[:9]) == Q.SIDECAR_BASE_KEYS
    assert set(record) - set(Q.SIDECAR_BASE_KEYS) <= (Q.R123_EXTRA_KEYS | {"pre_answer"})
    assert not {"usage", "terminal", "sources_n"} & set(record), set(record)


# ==================== ④ 反证乙 / 丙（红必须落在本格） ====================

def test_counter_evidence_dropping_usage_collection_goes_red_here(tmp_path):
    """反证乙：摘掉 usage 采集 ⇒ D-2 那格又回到「无从判定」，红落在 ``usage_present`` 上。"""
    module, _ = Q.mutant(tmp_path, "launder_usage", *DROP_USAGE)
    book = book_of(module, Q.answered_body())
    terminal = book["terminal"]
    assert terminal["shape"] == "structured", "别的第一格先红了：这枚刀没切到 usage"
    assert (terminal["sources_n"], terminal["state"]) == (3, "answered"), "牵连了别格"
    with pytest.raises(AssertionError) as exc:
        assert_usage_landed(book)
    assert "token 读数没进取回账（判据② / D-2）" in str(exc.value), str(exc.value)
    assert Q.usage_cell(book) == "row_cannot_say"


def test_counter_evidence_a_legacy_row_reading_as_zero_sources_goes_red_here(tmp_path):
    """反证丙：把旧行的占位空表照抄成读数 ⇒ 「查过了，零枚」的谎换格复发，红落在 ``sources_n``。"""
    module, _ = Q.mutant(tmp_path, "launder_legacy", *LAUNDER_LEGACY)
    book = book_of(module, Q.legacy_row_body(park_notice=True))
    terminal = book["terminal"]
    assert terminal["shape"] == "legacy", "形状先变了：这枚刀没切到出处那一格"
    assert (terminal["usage"], terminal["answer_is_park_notice"]) == (None, True), "牵连了别格"
    with pytest.raises(AssertionError) as exc:
        assert_legacy_cannot_say(book)
    assert "洗成了「查过了，零枚」" in str(exc.value), str(exc.value)
    assert terminal["sources_n"] == 0, "摘掉之后确实长出了那枚假零（钉不是空的）"


def test_the_tracked_ruler_keeps_every_literal_the_two_knives_touched():
    """临时根反证不许漏进真树：两处锚点的字面逐枚还在，且原件仍是 CRLF 一色。"""
    raw = SCRIPT_PATH.read_bytes()
    text = raw.decode("utf-8")
    assert '    usage = body.get("usage")' in text
    assert "    return shape in SOURCES_READABLE_SHAPES" in text
    assert '        if status == "awaiting_approval":' in text
    assert raw.count(b"\r\n") == raw.count(b"\n") > 0
