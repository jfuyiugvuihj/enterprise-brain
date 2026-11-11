# -*- coding: utf-8 -*-
r"""R457 · 判据②③④⑤：那枚字段今天有人读，而预览／视图／记账面三格一个字没动。

甲 · **红话本身**（判据②）。跟进单 §131 五要的是「摘掉执行腿 ⇒ 反证钉当场红，且红话点名
   『这枚字段没人读』」。所以这一格写成一枚明文守卫，绿件与反证钉共读同一段判断，窗内窗外
   只换视图不换尺子（`production_sources()` 读 `overlay.view_root()`）。扫描面是 `app/**` 与
   `deploy/**` 里对 `purge_expired_audit_events` 的**调用**：AST 遍，`def` 那一行天然不算，
   docstring 里提名也不算。本单基点之前它交回空集——那空集就是这笔单的病灶，今天交回
   `app/scheduler/jobs.py` 一枚。

乙 · **不动三格**：
   ③ `purge_expired_audit_events(dry_run=True)` 的预览语义。它的主账在
      `tests/test_audit_persistence.py` 的
      `test_retention_window_is_stamped_and_expired_events_are_tombstoned`——本件不抄第二份，
      只拿一枚内存替身适配器（零盘、零库、零容器）把预览那格再量一次，证明本单的落点没把
      预览改成执行、也没把执行改成预览；再钉住那本主账仍然在册。
   ④ `MAX_VIEW_EVENTS` 那 20,000 与 `view_complete` 的语义。本件钉的是「执行腿够不到视图
      那一格」：`app/scheduler/jobs.py` 的语法里不许出现任何视图内部件的名字，交回的读数也
      只有 audit 给的那五个词（那枚 key-set 钉在
      tests/test_r457_audit_retention_execution_leg.py）。效力边界，明写不装：本件量的是
      「调度器这一路伸手没伸手」，`audit.py` 自己那一格由它的主账管。
   ⑤ `GET /documents/{filename}/versions` 的记账面（§126 结论② 刚裁的「合法读也留账」）。
      那本账的主人是 R404（`tests/test_r404_the_judgment_journals_and_the_stub_is_honest.py`
      的 `test_the_allowed_judgment_writes_one_row_too` 与
      `test_the_denied_judgment_writes_exactly_one_journal_row`），本件不抄第二份，只钉它们
      还活着；本单写域不含 `app/api/v1/chat.py`，交回的 diff 里也没有它。

反证钉一律走 `tests/_temp_edit_overlay.py` 的影子根或纯内存 dict：盘上的被跟踪文件全程只读，
进出各量一次 sha256（还原自证在 `_assert_disk_and_module_restored`）。
"""
from __future__ import annotations

import ast
import inspect
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.common import audit as audit_module
from app.common.identity import Principal
from app.scheduler import jobs as jobs_module

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_r457_audit_retention_execution_leg import (  # noqa: E402  复用同一枚扫描器与反证窗，不另起口径
    JOBS_PY,
    SWEEP_PURGE_CALL,
    _assert_disk_and_module_restored,
    _callers_of,
    _purge_witness,
    _window,
    assert_the_leg_actually_purges,
    production_sources,
)

REPO = Path(__file__).resolve().parents[1]
PERSISTENCE_PINS = REPO / "tests" / "test_audit_persistence.py"
R404_JOURNAL_PINS = REPO / "tests" / "test_r404_the_judgment_journals_and_the_stub_is_honest.py"
LEG_REL = "app/scheduler/jobs.py"
PURGE = "purge_expired_audit_events"
#: 视图那一格的内部件名字：执行腿一个都不许够到（判据④）。
VIEW_INTERNALS = frozenset({
    "MAX_VIEW_EVENTS", "_events", "view_complete", "_hydrate_view", "_hydrate_view_locked",
    "hydrate_audit_events", "get_audit_events", "clear_audit_events",
})
#: 台账交回的那五个词（同一份口径在注册钉那本件 tests/test_r457_audit_retention_execution_leg.py）。
PREVIEW_KEYS = ("status", "reason", "checked", "expired", "purged")


# ==================== 甲 · 那枚字段有没有人读（判据①②的红话在这里写死）====================


def purge_readers(sources: dict[str, str]) -> list[str]:
    """谁真的调用那枚清账函数；`def` 那一行是 FunctionDef，天然不算。"""
    return sorted({rel for rel, _scope in _callers_of(sources, PURGE)})


def assert_expires_at_has_a_reader(sources: dict[str, str] | None = None) -> list[str]:
    readers = purge_readers(production_sources() if sources is None else sources)
    assert readers, (
        "expires_at 是一枚没人读的字段：app/** 与 deploy/** 里没有任何生产调用点读它 ⇒ "
        "审计留存只有定义、没有执行腿，台账行数只增不减（R457 判据①②）。要还这笔债，"
        "要么把清扫挂上调度器，要么写明替代触发者是谁并真的装上——写在注释里不算执行腿。"
    )
    return readers


def test_production_code_still_reads_the_expires_at_window():
    readers = assert_expires_at_has_a_reader()

    assert readers == [LEG_REL], (
        f"生产读者不是那枚排好的留存清扫，现读 {readers}：字段有人读没错，但读它的不是本单装上的腿"
    )


def test_the_leg_that_reads_it_is_the_registered_one(monkeypatch):
    """读到那枚字段的那一路，就是日历上那一格：两枚钉之间不许有缝。"""
    seen = _purge_witness(monkeypatch)

    assert_the_leg_actually_purges(seen["args"], seen["kwargs"])
    documented = jobs_module.audit_retention_sweep.__doc__ or ""
    assert "内容" in documented and "行" in documented, (
        "执行腿没在 docstring 里写清「清的是内容，不是行」：那笔读数就又被抄成「台账不再变长」"
    )
    assert "runbook" in documented, (
        "「真正的 DELETE 属部署 runbook」那一格得留在明面上，本单不冒充它已经做了"
    )


# ==================== 乙 · 判据③：预览还是预览，执行还是执行 ====================


class _MemoryAdapter:
    """共享适配器的最小替身：一枚 dict。盘上零写入、库里零连接、容器零接触。"""

    def __init__(self) -> None:
        self.records: dict[str, dict] = {}

    def upsert(self, collection, record_id, record):
        self.records[record_id] = dict(record)
        return dict(record)

    def get(self, collection, record_id):
        value = self.records.get(record_id)
        return dict(value) if value else None

    def list(self, collection):
        return [dict(record) for record in self.records.values()]


def _principal() -> Principal:
    principal = Principal.from_user(
        {"id": 1, "username": "r457", "role": "staff", "department": "finance"}
    )
    principal.request_id = "req-r457"
    return principal


@pytest.fixture
def journal(monkeypatch: pytest.MonkeyPatch):
    """把审计台账接到一枚内存替身上：三枚预览钉同生同灭，收尾清干净。"""
    monkeypatch.delenv("AUDIT_PERSISTENCE", raising=False)
    monkeypatch.delenv("AUDIT_RETENTION_DAYS", raising=False)
    adapter = _MemoryAdapter()
    audit_module.configure_audit_storage(persistence=adapter)
    yield adapter
    audit_module.reset_audit_storage()


def _expired_event(adapter, days: int = 7) -> dict:
    event = audit_module.record_audit(
        _principal(), "resource:view", "allowed", "doc-r457", "owner_match", retention_days=days
    )
    assert event["expires_at"], "台账没再 stamp 留存窗口：执行腿读的就是空气"
    return event


def test_the_preview_still_only_previews(journal):
    """判据③：`dry_run=True` 交回的仍然是「看多少、清零枚」，盘上一枚也不动。"""
    event = _expired_event(journal)
    future = datetime.now(timezone.utc) + timedelta(days=30)

    preview = audit_module.purge_expired_audit_events(future, dry_run=True)

    assert (preview["status"], preview["reason"]) == ("ok", "dry_run"), preview
    assert (preview["checked"], preview["expired"], preview["purged"]) == (1, 1, 0), preview
    assert tuple(preview) == PREVIEW_KEYS, f"预览交回的面换了词表：{tuple(preview)}"
    assert journal.records[event["event_id"]]["resource"] == "doc-r457", (
        "预览落笔了：那它就不再是预览，判据③ 要保住的那一格就没了"
    )


def test_the_same_door_still_closes_when_it_is_not_a_preview(journal):
    """另一面：本单没把执行改完预览。清完留 tombstone、正文抹掉、第二遍不再命中（幂等）。"""
    event = _expired_event(journal)
    future = datetime.now(timezone.utc) + timedelta(days=30)

    result = audit_module.purge_expired_audit_events(future)

    assert (result["status"], result["reason"], result["purged"]) == ("ok", "purged", 1), result
    tombstone = journal.records[event["event_id"]]
    assert tombstone["purged_at"] and tombstone["resource"] == "", tombstone
    assert tombstone["payload"]["purge_reason"] == "retention_window_elapsed", tombstone
    assert tombstone["expires_at"] is None, (
        "tombstone 没把窗口清空：下一次扫到它会再清一遍，两枚 host 同时挂着就重复清账"
    )
    assert audit_module.purge_expired_audit_events(future)["expired"] == 0, (
        "清过的又命中一次：台账被同一笔欠账清了两遍"
    )


def test_the_preview_door_is_still_keyword_only_and_off_by_default():
    """门的形状也不许动：`dry_run` 仍是 keyword-only、缺省 False，`now` 仍由 audit 自己取表。"""
    params = inspect.signature(audit_module.purge_expired_audit_events).parameters

    dry = params["dry_run"]
    assert dry.kind is inspect.Parameter.KEYWORD_ONLY, f"dry_run 变成了可位置传入：{dry}"
    assert dry.default is False, f"dry_run 的缺省不再是 False：{dry}"
    assert params["now"].default is None, "调度器不该替 audit 决定到点是哪一刻"


def test_the_booked_owner_of_the_preview_semantics_is_still_on_the_books():
    """③ 的主账仍在册（本件不抄第二份，只钉它没被摘牙）。"""
    text = PERSISTENCE_PINS.read_text(encoding="utf-8")

    assert "def test_retention_window_is_stamped_and_expired_events_are_tombstoned(" in text, (
        "在册那本预览主账被摘掉了：判据③ 从此没有主人，本单不接这本账"
    )
    assert re.search(r"purge_expired_audit_events\(\s*[^)]*dry_run=True", text), (
        "主账里那发预览调用不见了：预览语义的钉到了哪儿去了"
    )


# ==================== 乙 · 判据④：那 20,000 与 view_complete 不归执行腿说 ====================


def _names_used(text: str) -> set[str]:
    """一枚模块的语法里出现过的名字（Name 与 Attribute）：注释与 docstring 不算数。"""
    found: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
    return found


def assert_the_leg_leaves_the_view_alone(sources: dict[str, str]) -> None:
    reached = sorted(_names_used(sources[LEG_REL]) & VIEW_INTERNALS)
    assert not reached, (
        f"执行腿伸手够到了视图那一格：{reached}。判据④ 说 MAX_VIEW_EVENTS 那 20,000 与 "
        "view_complete 的语义不动——清扫只管把过期的正文改成 tombstone，视图完不完整是"
        "audit 那一侧按落笔与读失败自己算的账，不归调度器说"
    )


def test_the_view_cap_still_reads_twenty_thousand():
    assert audit_module.MAX_VIEW_EVENTS == 20_000, (
        f"视图上限被挪动了：现读 {audit_module.MAX_VIEW_EVENTS}，判据④ 说它不动"
    )


def test_the_sweep_never_reaches_the_view_that_view_complete_describes():
    assert_the_leg_leaves_the_view_alone(production_sources())


# ==================== 乙 · 判据⑤：/versions 的记账面不归本单动 ====================


def assert_the_versions_ledger_face_is_still_booked(text: str) -> None:
    for symbol in (
        "test_the_allowed_judgment_writes_one_row_too",
        "test_the_denied_judgment_writes_exactly_one_journal_row",
    ):
        assert f"def {symbol}(" in text, (
            f"§126 结论② 的那本主账里 {symbol} 不见了。合法读也留账是刚裁的，要翻它得另起一笔；"
            "R457 既不动 /versions 的记账面，也不许这本账悄悄没牙"
        )


def test_the_versions_ledger_face_is_still_owned_by_its_booked_pin():
    assert_the_versions_ledger_face_is_still_booked(R404_JOURNAL_PINS.read_text(encoding="utf-8"))


# ==================== 反证钉：三把，变异只在影子根或内存 dict 里 ====================


def test_teeth_5_the_field_goes_back_to_unread_when_the_leg_is_dropped():
    """TOOTH 5（判据② 的正身）：摘掉那一枚生产调用点 ⇒ 红话点名「这枚字段没人读」。

    这一把与注册钉那本件的四把分工：那四把量「腿在不在日历上」，本把量「就算日历上还有别的
    格子，只要没人读那枚字段，本件照样红」——这才是跟进单要的那句红话。
    """
    stub = ('    result: dict = {"status": "ok", "reason": "nothing_to_purge", '
            '"checked": 0, "expired": 0, "purged": 0}')
    with _window([SWEEP_PURGE_CALL], [stub]) as ref:
        with pytest.raises(AssertionError) as red:
            assert_expires_at_has_a_reader()
        message = str(red.value)
        assert "没人读" in message, "红话没点名那枚字段：" + message
        assert "写在注释里不算执行腿" in message, "红话没把『注释不算腿』那条口径写进去：" + message

    _assert_disk_and_module_restored(ref)


def test_teeth_6_the_reader_ruler_bites_a_synthetic_tree_too():
    """同一把尺在纯内存的合成树上也得咬：反证不必改盘，也不该只能改盘才红。"""
    sources = production_sources()
    assert_expires_at_has_a_reader(sources)

    mutated = dict(sources)
    mutated[LEG_REL] = sources[LEG_REL].replace(SWEEP_PURGE_CALL, "    result = {}")
    assert SWEEP_PURGE_CALL not in mutated[LEG_REL], "变异没把那枚调用摘干净：本把刀不作数"

    with pytest.raises(AssertionError, match="没人读"):
        assert_expires_at_has_a_reader(mutated)

    assert SWEEP_PURGE_CALL in JOBS_PY.read_text(encoding="utf-8"), (
        "盘上的 jobs.py 被动过：本把刀只许改内存里那份 dict"
    )


def test_teeth_7_a_preview_leg_still_reads_the_field():
    """两把尺不互相顶班：`dry_run=True` 那一把（注册钉那本件的 TOOTH 3）只该红在预览钉上。

    调用点还在 ⇒ 字段仍有人读，本件必须绿；「从此一枚也不清」由预览那枚钉管。少了这一格，
    两本账就并成一枚「只要不是真清账就都红」的钝尺，红话反而说不清病灶在哪。
    """
    sources = production_sources()
    previewed = dict(sources)
    previewed[LEG_REL] = sources[LEG_REL].replace(
        PURGE + "()", PURGE + "(dry_run=True)"
    )

    assert purge_readers(previewed) == [LEG_REL], "预览版被读成零枚读者：尺子钝了"
    assert_expires_at_has_a_reader(previewed)

    with pytest.raises(AssertionError, match="预览"):
        assert_the_leg_actually_purges((), {"dry_run": True})


def test_teeth_8_a_leg_that_reaches_the_view_goes_red():
    sources = production_sources()
    mutated = dict(sources)
    mutated[LEG_REL] = sources[LEG_REL] + "\n_budget = MAX_VIEW_EVENTS\n"

    with pytest.raises(AssertionError, match="视图那一格"):
        assert_the_leg_leaves_the_view_alone(mutated)

    assert_the_leg_leaves_the_view_alone(production_sources())


def test_teeth_9_a_stripped_versions_ledger_book_goes_red():
    text = R404_JOURNAL_PINS.read_text(encoding="utf-8")
    stripped = text.replace(
        "def test_the_allowed_judgment_writes_one_row_too(",
        "def _removed_the_allowed_face(", 1
    )

    with pytest.raises(AssertionError, match="§126 结论") as red:
        assert_the_versions_ledger_face_is_still_booked(stripped)
    assert "test_the_allowed_judgment_writes_one_row_too" in str(red.value)
