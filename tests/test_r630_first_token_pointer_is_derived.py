# -*- coding: utf-8 -*-
"""R630 判据①② —— 观测面那句「first_token_at 落在哪」必须现读代码，一枚行号都不许抄。

对判据的哪一条（派工词 R630）：
  ① 旧坐标那一格的在册假话（把落点抄成 ``app/trace/store.py`` 的第 259 行，而那枚文件里这一格
     零命中）改成指真源：文件 + 符号名、零行号。本件把「文案点名的每一格断言」都配上一枚现读
     谓词，派生源一动（落盘点搬家／名册改列／账本开始吃这一格），钉咬的就是文案与真源不一致那一形。
  ② 原 R537 那一格（桥话里拿两个英文词手写名册枚数）**已由 R533 并树派生化**，本件不重抄 R533
     那几枚钉，只把它那把尺从 bridge_note 一格放宽到整本对外回执：任何一枚 published 散文手写
     名册枚数，当场红。学的正是 ``tests/test_r520_counter_evidence_teeth.py`` 记的那一笔——
     纸面判据为真、常量层为假，因为别处那几格压根没有尺。
  ③ 派生源改了而句子没改＝红；单纯把一枚数字换成另一枚数字＝还是红（按形状失败，不按枚数失败）。

🔴 形状约定（钉与反证刀共用同一把尺，见 ``tests/test_r630_counter_evidence_teeth.py``）：
  · 带 ``::符号`` 的锚点＝这句话声称该文件确实经手这一格，所以那枚文件必须现读带着它，
    那个符号也必须现读解析得到；
  · 只写文件名不写符号＝声称它**不**经手，所以那枚文件必须现读没有它，且所在分句要带否定词；
  · ``.py:数字`` 这种形状＝手抄坐标，本件那一格里一枚都不许有。

零 IO：只读盘上源码文本与内存对象，不起服务、不连库、不打模型、不动容器。
枚数一律现取：名册读数复用 ``tests/test_r533_bridge_note_is_derived.py`` 的同一批把手，不抄第二份。
"""
from __future__ import annotations

import ast
import importlib
import inspect
import re
from dataclasses import fields
from pathlib import Path

import test_r526_slot_caliber_closure as r526
import test_r533_bridge_note_is_derived as r533
from app.api.v1 import observability
from app.common import stage_timing
from app.storage import persistence
from app.trace import projections, schema, spans

REPO = Path(__file__).resolve().parents[1]
OBSERVABILITY = REPO / "app" / "api" / "v1" / "observability.py"
OBSERVABILITY_REL = OBSERVABILITY.relative_to(REPO).as_posix()

FIELD = "first_token_at"
CELL = "first_token_not_a_stage_sample"

#: 一枚 finished model span 交回的载荷长什么样：戳是真的，值固定下来只为把链路量到同一点。
STAMP = "2026-10-04T00:00:07+00:00"

#: 锚点形状：``app/…py::符号``（符号可点号分段）。
ANCHOR = re.compile(r"(app/[A-Za-z0-9_./-]+\.py)::([A-Za-z0-9_.]+)")
#: 只点名文件、不点符号：本件只允许它出现在「这一枚确实不经手」那一支。
BARE_MODULE = re.compile(r"(?<![\w./-])(app/[A-Za-z0-9_./-]+\.py)(?!::)")
#: 手抄坐标的形状。
LINE_ANCHOR = re.compile(r"\.py:\d+")
#: 「不经手」那一支必须自带的否定词。
NEGATIONS = ("never", "no ", "not ", "none")
#: 分句边界：钉与刀共用，句子改写要落在这几枚分隔符上。
CLAUSE = re.compile(r"[;,]|\s--\s")


# ==================== 派生源现读（不抄第二份名册，也不另抄一把尺） ====================


def rel_path(obj) -> str:
    """把一个活对象换成仓内相对路径：派生源搬家，红就红在这一枚读数上。"""
    return Path(inspect.getfile(obj)).resolve().relative_to(REPO).as_posix()


def carriers() -> set[str]:
    """``app/**`` 里现读确实写着这一格的那几枚文件（观测面自己不算，它是被量的人）。"""
    found = set()
    for path in sorted((REPO / "app").rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel == OBSERVABILITY_REL:
            continue
        if FIELD in path.read_text(encoding="utf-8"):
            found.add(rel)
    return found


def resolve_symbol(rel: str, dotted: str):
    """按锚点写下的样子现场解析符号：``path.py::A.b`` → ``getattr(模块, A).b``。"""
    module = importlib.import_module(rel[: -len(".py")].replace("/", "."))
    found = module
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def cell_from_source(text: str) -> str:
    """从观测面源文里现取那一格：反证刀改的就是这段，牙读的也是这段。"""
    for node in ast.parse(text).body:
        targets = (
            [node.target]
            if isinstance(node, ast.AnnAssign)
            else list(node.targets)
            if isinstance(node, ast.Assign)
            else []
        )
        if not any(isinstance(target, ast.Name) and target.id == "SLO_BLOCKERS" for target in targets):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            if isinstance(key, ast.Constant) and key.value == CELL:
                return str(ast.literal_eval(value))
    raise AssertionError("SLO_BLOCKERS 里取不到那一格，本件的取段前提变了")


def cell_prose() -> str:
    return observability.SLO_BLOCKERS[CELL]


# ==================== 真链路：全程离线，走的是产品自己的那几枚函数 ====================


def finished_span_payload() -> dict:
    """``ExecutionSpan.finish`` 真交回的载荷。

    身份为空 ⇒ ``record()`` 与 ``_observe_stage()`` 都在 ``active`` 那枚闸前直接返回：
    不写盘、不发事件、不进账本，只把载荷算出来给本件量。
    """
    span = spans.ExecutionSpan(
        record_kind="model_calls",
        record_id="r630:model:1",
        identity={},
        started_event="model.started",
        finished_event="model.finished",
    )
    span.mark_first_token()
    return span.finish("completed")


def projected_model_row() -> dict:
    """把上面那枚载荷折进 ``model_calls`` 行：走 ``project_event`` 真代码，零 IO。"""
    payload = dict(finished_span_payload())
    payload[FIELD] = STAMP
    event = {
        "event_type": "model.finished",
        "trace_id": "r630-trace",
        "request_id": "r630-req",
        "task_id": "r630-task",
        "sequence": 1,
        "timestamp": STAMP,
        "status": "completed",
        "payload": payload,
    }
    rows = {
        projection.collection: projection.values
        for projection in projections.project_event(
            event, owner_id="r630-owner", fetch=lambda collection, record_id: None
        )
    }
    return rows["model_calls"]


def insert_statement() -> str:
    """``PostgresPersistenceAdapter`` 真要发出去的那条 INSERT 的文本：组语句，不连库。"""
    row = dict(projected_model_row(), owner_id="r630-owner")
    adapter = persistence.PostgresPersistenceAdapter(lambda: None)
    definition, values = adapter._prepare("model_calls", str(row["model_call_id"]), row)
    sql, _params = adapter._statement(definition, values, overwrite=True)
    return sql


# ==================== 文案点名的每一格断言 ↔ 一枚现读谓词 ====================


def column_roster_has(table: str):
    return lambda: FIELD in schema.TRACE_TABLE_COLUMNS[table]


def write_whitelist_has(table: str):
    return lambda: FIELD in persistence._TABLES[table].columns


def source_holds(source_obj):
    body = inspect.getsource(source_obj)
    return lambda: FIELD in body


#: ``(锚点, 这句话声称的事, 期望真值, 现读谓词)``：期望为 False 的那几行守的是「不经手」。
CLAIMS: tuple[tuple[str, str, bool, object], ...] = (
    ("TRACE_TABLE_COLUMNS", "列名册里带着这一格", True, column_roster_has("model_calls")),
    ("_TABLES", "落盘白名单里带着这一格", True, write_whitelist_has("model_calls")),
    ("PostgresPersistenceAdapter", "写出去那条 INSERT 点得到这一格", True, lambda: FIELD in insert_statement()),
    ("project_span", "投影把这一格折进了 model_calls 行", True, lambda: projected_model_row().get(FIELD) == STAMP),
    ("mark_first_token", "span 确实落这一枚戳", True, lambda: finished_span_payload().get(FIELD) is not None),
    ("ExecutionSpan.finish", "finished 载荷确实带着这一格", True, source_holds(spans.ExecutionSpan.finish)),
    ("samples_from_span_payload", "账本把这一格折进了样本", False, source_holds(stage_timing.samples_from_span_payload)),
    ("_observe_stage", "span 收尾时把这一格交给了账本", False, source_holds(spans.ExecutionSpan._observe_stage)),
)


def sample_holds_the_field() -> bool:
    """``StageSample`` 里有没有一枚装得下 first token 的字段：名字由派生算出，不抄字面。"""
    return any(
        FIELD in entry.name or entry.name.startswith("first_token")
        for entry in fields(stage_timing.StageSample)
    )


def prose_shape_violations(prose: str) -> list[str]:
    """唯一一把形状尺：文案与真源不一致的每一形，逐枚点名。"""
    bad: list[str] = []
    copied = sorted(set(LINE_ANCHOR.findall(prose)))
    if copied:
        bad.append("抄了行号坐标：%s" % copied)
    for rel, dotted in ANCHOR.findall(prose):
        try:
            resolve_symbol(rel, dotted)
        except (ImportError, AttributeError, ValueError) as exc:
            bad.append("锚点 %s::%s 现读解析不到：%r" % (rel, dotted, exc))
        if rel not in carriers():
            bad.append("锚点声称 %s 经手这一格，现读那枚文件里没有它" % rel)
    for rel in BARE_MODULE.findall(prose):
        if rel in carriers():
            bad.append("%s 只点名不点符号，可它其实带着这一格：句子把经手说成了不经手" % rel)
        segment = next((part for part in CLAUSE.split(prose) if rel in part), "")
        if not any(word in segment for word in NEGATIONS):
            bad.append("%s 那一支不带否定词，读起来像在声称它落这一格" % rel)
    for needle, claim, expected, reading in CLAIMS:
        if needle not in prose:
            continue
        if bool(reading()) is not expected:
            bad.append("文案声称「%s」，现读不是那样（锚点 %s）" % (claim, needle))
    if "StageSample" in prose and sample_holds_the_field():
        bad.append("文案说 StageSample 装不下这一格，现读它已经有了字段")
    return bad


def chain_violations(prose: str) -> list[str]:
    """真链路的每一枚落点都必须被文案点名：落点搬家而句子不改 ⇒ 红。"""
    chain = (
        ("落戳那枚文件", spans.ExecutionSpan.mark_first_token),
        ("折进行那枚文件", projections.project_span),
        ("列名册那枚文件", schema),
        ("写 INSERT 那枚文件", persistence.PostgresPersistenceAdapter.upsert),
    )
    named = {rel for rel, _ in ANCHOR.findall(prose)}
    return [
        "真链路上 %s 是 %s，文案没点名它" % (label, rel_path(obj))
        for label, obj in chain
        if rel_path(obj) not in named
    ]


def published_blockers(payload) -> list[str]:
    """回执里所有 ``code == CELL`` 的 detail，一枚不遗漏（形状与名册同一枚才算对得上）。"""
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if node.get("code") == CELL and "detail" in node:
                found.append(str(node["detail"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)

    walk(payload)
    return found


# ==================== 判据① 的正例 ====================


def test_the_cell_carries_no_hand_copied_coordinate() -> None:
    """那一格里一枚 ``.py:数字`` 都没有；旧那句把落点抄给 store 的那一形也彻底死了。"""
    prose = cell_prose()
    assert LINE_ANCHOR.findall(prose) == []
    source = OBSERVABILITY.read_text(encoding="utf-8")
    assert "(app/trace/store.py" not in source, "旧那句括号包坐标的写法被退回去了"
    assert cell_from_source(source) == prose, "源文那一格与活模块那一格不是同一句话"


def test_the_prose_agrees_with_the_live_chain_shape() -> None:
    """形状尺正例：锚点都解析得到、都真带这一格；只点名的都不带、且都配着否定词。"""
    assert prose_shape_violations(cell_prose()) == []


def test_the_prose_credits_every_leg_of_the_live_chain() -> None:
    """落点搬家那一形：真链路每一枚文件都必须被文案点名。"""
    assert chain_violations(cell_prose()) == []


def test_the_recorded_value_reaches_the_written_row_offline() -> None:
    """链路实物面：span 落的戳 → 折进行 → 组进 INSERT，全程零 IO、零库。"""
    assert finished_span_payload()[FIELD] is not None
    assert projected_model_row()[FIELD] == STAMP
    assert FIELD in insert_statement()
    assert FIELD in schema.TRACE_TABLE_COLUMNS["model_calls"]
    assert FIELD in persistence._TABLES["model_calls"].columns


def test_the_blamed_store_and_the_ledger_really_do_not_carry_it() -> None:
    """被冤枉的那两枚：``store.py`` 现读零命中，账本那几枚把手也零命中。"""
    assert FIELD not in (REPO / "app" / "trace" / "store.py").read_text(encoding="utf-8")
    assert FIELD not in (REPO / "app" / "common" / "stage_timing.py").read_text(encoding="utf-8")
    assert not source_holds(stage_timing.samples_from_span_payload)()
    assert not source_holds(spans.ExecutionSpan._observe_stage)()
    assert not sample_holds_the_field()


def test_the_surface_publishes_the_same_string_as_the_registry() -> None:
    """对外那一格就是名册那一枚，不是第二份抄本。"""
    published = published_blockers(observability.slo_readout())
    assert published, "回执里找不到这一格的 detail，本件的取段前提变了"
    assert set(published) == {cell_prose()}, "对外那格与名册那一格对不上"


# ==================== 判据② 的形状尺（把 R533 那把放宽到整本回执） ====================


def string_leaves(node, path: str = ""):
    """``[(路径, 字符串)]``：对外散文的全部落点。"""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from string_leaves(value, "%s/%s" % (path, key))
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            yield from string_leaves(value, "%s/%d" % (path, index))


def derived_tally() -> set[str]:
    """允许出现在对外散文里的每一枚名册枚数：全部现取，一枚不抄。"""
    return {
        str(len(r533.budget_roster())),
        str(len(r533.lane_bridge())),
        str(len(r533.unlaned_tiers())),
        str(len(r533.shared_tiers())),
        str(len(stage_timing.CANONICAL_STAGES)),
        str(len(observability.slo_tiers())),
    }


def roster_count_offenders(payload) -> list[str]:
    """整本回执里「枚数紧贴名册名词」的每一形：英文词＝手写，数字对不上派生＝手写。"""
    allowed = derived_tally()
    bad: list[str] = []
    for path, text in string_leaves(payload):
        for match in r533.COUNT_IN_PROSE.finditer(text):
            if any(re.search(r"\b%s\b" % word, match.group(0), re.IGNORECASE) for word in r533.SPELL_NUMBERS):
                bad.append("%s 拿英文词写了名册枚数：%r" % (path, match.group(0)))
            digits = set(re.findall(r"\d+", match.group(0)))
            if digits - allowed:
                bad.append(
                    "%s 的名册枚数 %r 不在派生读数里（现取派生＝%s）"
                    % (path, match.group(0), sorted(allowed, key=int))
                )
    return bad


def test_no_published_prose_types_a_roster_count_by_hand() -> None:
    """R533 只钉了 bridge_note 一格；这一枚把同一把尺铺到整本对外回执。"""
    assert roster_count_offenders(observability.slo_readout()) == []


def test_a_shadow_roster_growth_leaves_the_surface_clean(monkeypatch) -> None:
    """派生源动了句子必须跟着动：影子注一档之后，整本回执仍只对得上新的派生读数。"""
    note_before = cell_prose()
    bridge_before = observability.slo_units()[r533.BUDGET_UNIT]["bridge_note"]
    assert roster_count_offenders(observability.slo_readout()) == []
    with monkeypatch.context() as box:
        box.setattr(r533.contracts, "ModelTier", r533.grown_model_tier(r533.SHADOW_TIER))
        grown = observability.slo_readout()
        assert roster_count_offenders(grown) == [], "往名册注一档之后句子对不上新名册了"
        note = grown["units"][r533.BUDGET_UNIT]["bridge_note"]
        assert "`%s`" % r533.SHADOW_TIER in note, note
        assert str(len(r533.unlaned_tiers())) in note, note
        assert str(len(r533.budget_roster())) in note, note
    assert observability.SLO_BLOCKERS[CELL] == note_before, "影子漏在活模块上了"
    assert observability.slo_units()[r533.BUDGET_UNIT]["bridge_note"] == bridge_before, "影子漏在活模块上了"


# ==================== 本件自己先过一遍尺 ====================


def test_this_file_itself_copies_no_coordinate() -> None:
    """钉自己不许抄坐标，也不许往口径里塞量级（R526 那把尺复用，不另抄一份）。"""
    source = Path(__file__).resolve().read_text(encoding="utf-8")
    assert LINE_ANCHOR.findall(source) == []
    assert r526.find_magnitudes(source) == []
    assert re.search(r"\b\w+\s+of\s+the\s+\w+\s+budget\s+tiers\b", source, re.IGNORECASE) is None
