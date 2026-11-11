"""R187 · 挂起那一轮声明的档位，今天真的写得进也读得回（持久化那半条腿）。

坐标（改前在同一台机器、同一个解释器上实取；本机文件账与 PG 分支的语句形状）：

    写侧    record_awaiting(..., declared_lane="report") ⇒ record.declared_lane == "report"
    INSERT  (session_id, owner_user_id, parked_steps, status, request_id, trace_id,
             task_id, created_at, expires_at) VALUES (%s ×9) —— 九列九参，没有这一格
    SELECT  ×3：session_id, ... , created_at, expires_at, decided_at —— 十列，止于 decided_at
    PG 读回 get_row() / open_items() / mark_status() 的 declared_lane 全部 == ""
    文件账  同一枚调用读回 "report"

⇒ 挂起时声明的档位过不了重启那道门：这一格写得进内存，读不回持久层。

本单四枚语句一起补：INSERT 多绑一列一参（第十枚就是 ``record.declared_lane`` 本身），三枚
显式列表 SELECT 各多读一格。绑值只准走同源 —— 入口是 app.agents.nodes 的
``declared_lane_from_config`` → ``normalize_declared_lane``（未知拼写当场硬失败）；storage 层
不猜、不校验、不另起第二份归一化、不做 ``or "qa"`` 兜底。列由 0012 送进台账（TEXT NOT NULL
DEFAULT ''），存量行零回填，'' 就是 normalize_declared_lane("") 的那个值。

假台账 ``_FakeLedger`` 是这文件的断路探测器，不是把 SQL 桩掉：INSERT 按列名存行，SELECT
只回它自己点名那些列，``%s::jsonb`` 回 list，NOT NULL 列喂 None 就炸，库里没这一列就炸
42703 形状。于是
- 只改 INSERT 不改 SELECT ⇒ 读回空串 ⇒ 具名红（反证 a：那半条腿）；
- 在 storage 层再写一份归一化 ⇒ 交进来的拼写被改写、或档位字面量出现在本层代码里 ⇒ 具名红（反证 b）。

全程离线：不开真端口、不连库、不跑 scripts/migrate.py。
"""
from __future__ import annotations

import ast
import dataclasses
import io
import json
import re
import tokenize
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.agents.nodes import (
    DECLARED_LANE_KEY,
    LANE_ANALYSIS,
    LANE_QA,
    LANE_REPORT,
    LANE_SOURCE_RESUMED,
    LANE_TIERS,
    declared_lane_from_config,
    normalize_declared_lane,
)
from app.api.v1 import chat
from app.storage import pending_approvals as store

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "app" / "storage" / "pending_approvals.py"

SESSION = "r187-the-lane-crosses-the-restart"
OWNER = "u-r187"
STEPS = ("export",)
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)

#: 0008 建表给出的列 + 0012 送出的那一格。这就是本文件所谓"已过 0012 的台账"。
LANDED_COLUMNS = (
    "id",
    "session_id",
    "owner_user_id",
    "parked_steps",
    "request_id",
    "trace_id",
    "task_id",
    "status",
    "created_at",
    "expires_at",
    "decided_at",
    "declared_lane",
)
#: 只到 0008 的那台库：本单之后写侧必须拒绝在它身上静默写空。
PRE_0012_COLUMNS = tuple(name for name in LANDED_COLUMNS if name != "declared_lane")
#: 0008/0012 里带 NOT NULL 的列（id 走序列、decided_at/request_id/trace_id/task_id 可空）。
NOT_NULL_COLUMNS = {
    "session_id",
    "owner_user_id",
    "parked_steps",
    "status",
    "created_at",
    "expires_at",
    "declared_lane",
}


class _Clock:
    """可控的账本时钟：INSERT 绑的时间戳与假库的 NOW() 都从这一枚取。"""

    def __init__(self, start: datetime):
        self.value = start

    def __call__(self) -> datetime:
        return self.value


class _UndefinedColumn(RuntimeError):
    """库里没有这一列（42703）。真库会炸在这里，假台账也必须炸在这里。"""


class _NotNullViolation(RuntimeError):
    """NOT NULL 列喂了 None（23502）。"""


class _Cursor:
    def __init__(self, one=None, many=None):
        self._one = one
        self._many = many if many is not None else ([one] if one else [])

    def fetchone(self):
        return self._many[0] if self._many else None

    def fetchall(self):
        return list(self._many)


def _columns_of_select(text: str) -> list[str]:
    match = re.match(r"SELECT (.*?) FROM \w+", text, re.I)
    assert match, text
    return [name.strip() for name in match.group(1).split(",")]


class _FakeLedger:
    """一台只认这张表口径的假 PG：按列名存行，也按列名回行。

    与真库对齐的四处就是取证的前提：SELECT 只回它点名的列（漏一格就回 None，不是回真值）、
    jsonb 回 list、NOT NULL 喂 None 就炸、catalog 里没有的列一律 42703。它不实现的东西
    直接 AssertionError，免得某条判据靠"假库太宽松"蒙过去。
    """

    def __init__(self, catalog, clock: _Clock):
        self.catalog = set(catalog)
        self.clock = clock
        self.rows: list[dict] = []
        self.statements: list[tuple[str, tuple]] = []

    # ------------------------------------------------------------ 入口
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        bound = tuple(params or ())
        self.statements.append((text, bound))
        head = text.upper()
        if "TO_REGCLASS" in head:
            return _Cursor({"table_name": "pending_approvals"})
        if head.startswith("INSERT INTO PENDING_APPROVALS"):
            return self._insert(text, bound)
        if head.startswith("UPDATE PENDING_APPROVALS"):
            return self._update(text, bound)
        if head.startswith("SELECT"):
            return self._select(text, bound)
        raise AssertionError("假台账没实现这一句：" + text)

    def statements_matching(self, needle: str) -> list[tuple[str, tuple]]:
        return [item for item in self.statements if needle in item[0]]

    # ------------------------------------------------------------ 写
    def _insert(self, text: str, bound: tuple):
        header, values = text.split("VALUES", 1)
        match = re.match(r"INSERT INTO (\w+) \((.*)\)$", header.strip(), re.I)
        assert match, header
        names = [name.strip() for name in match.group(2).split(",")]
        casts = [cast for _placeholder, cast in re.findall(r"(%s)(::\w+)?", values)]
        assert len(names) == len(casts) == len(bound) == text.count("%s"), (names, bound)
        self._require_columns(names)

        row: dict = {"id": len(self.rows) + 1, "decided_at": None}
        for name, cast, value in zip(names, casts, bound):
            if cast == "::jsonb":
                value = json.loads(value)
            if value is None and name in NOT_NULL_COLUMNS:
                raise _NotNullViolation(f'null value in column "{name}" violates not-null')
            row[name] = value
        self.rows.append(row)
        return _Cursor({"id": row["id"]})

    def _update(self, text: str, bound: tuple):
        head, _, where = text.partition("WHERE")
        assert re.match(r"UPDATE pending_approvals SET status = %s, decided_at = NOW\(\)$",
                        head.strip(), re.I), head
        set_count = head.count("%s")
        self._require_columns(["status", "decided_at"])
        wanted = self._wanted(where, bound[set_count:])
        for row in self.rows:
            if self._matches(row, wanted, where):
                row["status"] = bound[0]
                row["decided_at"] = self.clock().isoformat()
        return _Cursor()

    # ------------------------------------------------------------ 读
    def _select(self, text: str, bound: tuple):
        names = _columns_of_select(text)
        assert "pending_approvals" in text, text
        self._require_columns(names)
        where = text.split("WHERE", 1)[1] if "WHERE" in text else ""
        wanted = self._wanted(where, bound)
        rest = list(bound[len(wanted):])

        hits = [row for row in self.rows if self._matches(row, wanted, where)]
        if "ORDER BY created_at DESC" in text:
            hits = sorted(hits, key=lambda row: str(row.get("created_at")), reverse=True)
        page = re.search(r"LIMIT (%s|\d+)", text)
        if page:
            bounded = rest[0] if page.group(1) == "%s" else int(page.group(1))
            if page.group(1) == "%s":
                rest = rest[1:]
            hits = hits[: int(bounded)]
        if "OFFSET %s" in text and rest:
            hits = hits[int(rest[0]):]
        return _Cursor(many=[{name: row.get(name) for name in names} for row in hits])

    # ------------------------------------------------------------ 共用
    def _require_columns(self, names) -> None:
        for name in names:
            if name not in self.catalog:
                raise _UndefinedColumn(
                    f'column "{name}" of relation "pending_approvals" does not exist'
                )

    @staticmethod
    def _wanted(where: str, bound: tuple) -> dict:
        terms = [m.group(1) for m in re.finditer(
            r"\b(session_id|status|owner_user_id)\b\s*=\s*%s", where)]
        assert len(terms) <= len(bound), (terms, bound)
        return dict(zip(terms, bound))

    def _matches(self, row: dict, wanted: dict, where: str) -> bool:
        for name, value in wanted.items():
            if row.get(name) != value:
                return False
        if "expires_at > NOW()" in where:
            expires = row.get("expires_at")
            if expires is not None and datetime.fromisoformat(str(expires)) <= self.clock():
                return False
        return True


def _use_pg(monkeypatch, catalog=LANDED_COLUMNS, clock=None) -> _FakeLedger:
    """把 store 的 PG 分支接到假台账上：本文件的 PG 腿全部从这里走。"""
    ledger = _FakeLedger(catalog, clock or _Clock(NOW))
    monkeypatch.setattr(store, "_database_available", lambda: True)
    monkeypatch.setattr(store, "_conn", lambda: ledger)
    return ledger


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    clock = _Clock(NOW)
    monkeypatch.setattr(store, "_NOW", clock)
    monkeypatch.setattr(store, "_MEM_ROWS", {})
    monkeypatch.delenv("PENDING_APPROVAL_TTL_HOURS", raising=False)
    return clock


def _shape(record) -> str:
    """把一条记录折成可比较的字节形状（字段名 + 值，按 key 排序）。"""
    return json.dumps(dataclasses.asdict(record), ensure_ascii=False, sort_keys=True)


def _park(*, declared: str = LANE_REPORT, catalog=LANDED_COLUMNS,
          monkeypatch=None, clock=None) -> _FakeLedger:
    ledger = _use_pg(monkeypatch, catalog=catalog, clock=clock)
    store.record_awaiting(
        SESSION, OWNER, STEPS, request_id="req-1", trace_id="tr-1", task_id="tk-1",
        declared_lane=declared,
    )
    return ledger


def _insert_statement(ledger: _FakeLedger) -> tuple[str, tuple]:
    found = ledger.statements_matching("INSERT INTO pending_approvals")
    assert len(found) == 1, found
    return found[0]


def _select_statements(ledger: _FakeLedger) -> list[tuple[str, tuple]]:
    return ledger.statements_matching("SELECT session_id")


# ==================================================== 判据 1：写得进，也读得回
def test_a_lane_declared_at_park_time_reads_back_through_every_pg_reader(monkeypatch, frozen_clock):
    """这一格的四条读腿全部要能答话：面板、复核、闭合后的回读、失败行。

    改前这四枚读数全是空串（模块 docstring 里那句"PG 分支一字未动"说的就是它）。
    """
    _park(monkeypatch=monkeypatch, clock=frozen_clock, declared=LANE_REPORT)

    assert store.get_row(SESSION).declared_lane == LANE_REPORT
    assert [row.declared_lane for row in store.open_items()] == [LANE_REPORT]
    assert [row.declared_lane for row in store.open_items(owner_user_id=OWNER)] == [LANE_REPORT]
    assert store.mark_status(SESSION, store.RESUMED).declared_lane == LANE_REPORT
    # 闭合之后仍读得回：那一格的寿命跟这行账一样长，不跟状态机走。
    assert store.get_row(SESSION).declared_lane == LANE_REPORT


def test_the_pg_leg_and_the_local_ledger_leg_park_the_same_bytes(monkeypatch, frozen_clock):
    """同源同值：同一枚调用打到两条腿上，读回的记录逐字节相同。

    这条比"绑了没绑"更硬：写侧少绑任意一列（不止新格），两条腿的产物立刻分叉。
    """
    common = dict(request_id="req-1", trace_id="tr-1", task_id="tk-1", declared_lane=LANE_ANALYSIS)

    monkeypatch.setattr(store, "_database_available", lambda: False)
    store.record_awaiting(SESSION, OWNER, STEPS, **common)
    memory = store.get_row(SESSION)

    _use_pg(monkeypatch, clock=frozen_clock)
    store.record_awaiting(SESSION, OWNER, STEPS, **common)
    pg = store.get_row(SESSION)

    assert _shape(pg) == _shape(memory), (dataclasses.asdict(pg), dataclasses.asdict(memory))
    assert pg.declared_lane == LANE_ANALYSIS == memory.declared_lane


def test_the_insert_binds_one_value_for_every_column_it_names(monkeypatch, frozen_clock):
    """列集与占位符数与实参数三者一致：这条不变量从九枚那时代就是这个样子，十枚照旧。

    它替代"必须是九"那种快照断言：真正会杀人的是"多绑一格参数"（位置错位的
    UndefinedColumn），不是那个数字本身。
    """
    ledger = _park(monkeypatch=monkeypatch, clock=frozen_clock, declared=LANE_REPORT)
    sql, bound = _insert_statement(ledger)
    names = re.match(r"INSERT INTO \w+ \((.*)\) VALUES", sql, re.I).group(1).split(", ")

    assert len(names) == len(bound) == sql.count("%s") == 10
    assert names[-1] == "declared_lane" and bound[-1] == LANE_REPORT
    assert len(names) == len(set(names)), names


# ==================================================== 判据 4 的持久层半边：三枚 SELECT 都要带
@pytest.mark.parametrize("reader", ["get_row", "open_items", "mark_status"])
def test_every_pg_read_side_names_the_column_it_was_written_into(monkeypatch, frozen_clock, reader):
    """只改 INSERT 不改 SELECT 就是半条腿：这一枚按读腿点名，一条漏了都红。

    它不钉源码文本，它真让假库按 SELECT 的列名回行：漏一格 ⇒ ``_record_from_row`` 读到
    None ⇒ 落空串 ⇒ 断言当场红。这就是反证 (a) 的机制本体。
    """
    ledger = _park(monkeypatch=monkeypatch, clock=frozen_clock, declared=LANE_QA)
    read = {
        "get_row": lambda: store.get_row(SESSION),
        "open_items": lambda: store.open_items(owner_user_id=OWNER)[0],
        "mark_status": lambda: store.mark_status(SESSION, store.RESUMED),
    }[reader]()

    assert read is not None, reader
    assert read.declared_lane == LANE_QA, reader
    selects = _select_statements(ledger)
    assert selects, reader
    for sql, _bound in selects:
        assert "declared_lane" in _columns_of_select(sql), sql


def test_the_landed_catalog_takes_the_write_and_the_pre_0012_catalog_refuses_it(monkeypatch, frozen_clock):
    """前置条件写实：0012 那台库写得进；没跑 0012 的那台当场炸，而不是静默写空。

    本单不引入兜底重试，所以这条耦合必须留痕：模块 docstring 里"过 0012"是写侧的前提。
    """
    landed = _park(monkeypatch=monkeypatch, clock=frozen_clock, declared=LANE_REPORT)
    assert store.get_row(SESSION).declared_lane == LANE_REPORT

    monkeypatch.setattr(store, "_database_available", lambda: True)
    monkeypatch.setattr(store, "_conn", lambda: _FakeLedger(PRE_0012_COLUMNS, frozen_clock))
    with pytest.raises(_UndefinedColumn):
        store.record_awaiting(SESSION, OWNER, STEPS, declared_lane=LANE_REPORT)


# ==================================================== 判据 3 的读法侧：空串与"无此键"同形
def test_a_row_that_cannot_answer_the_column_reads_byte_identical_to_an_empty_one(monkeypatch, frozen_clock):
    """三种读法（无此键／值为 None／值就是空串）折成同一枚产物。

    R183 判据 6 钉的是形状，这一枚把它从"源码里读一遍"升级成真过 ``_record_from_row``
    与真打 ``open_items``：存量 83 行今天就是这个形状，一条都不许多读出个档位来。
    """
    blank = dict(session_id=SESSION, owner_user_id=OWNER, parked_steps=["export"],
                 status=store.AWAITING, request_id=None, trace_id=None, task_id=None,
                 created_at=NOW.isoformat(), expires_at=(NOW + timedelta(hours=1)).isoformat(),
                 decided_at=None)

    without_key = store._record_from_row(dict(blank))
    with_null = store._record_from_row(dict(blank, declared_lane=None))
    with_empty = store._record_from_row(dict(blank, declared_lane=""))

    assert _shape(without_key) == _shape(with_null) == _shape(with_empty)
    assert without_key.declared_lane == "" == normalize_declared_lane("")

    # 同一枚形状也要能从 PG 腿读回来：库里那一格答不上话（NULL）不等于有人声明过。
    ledger = _FakeLedger(LANDED_COLUMNS, frozen_clock)
    legacy = dict(blank, id=1)
    ledger.rows.append(legacy)
    monkeypatch.setattr(store, "_database_available", lambda: True)
    monkeypatch.setattr(store, "_conn", lambda: ledger)

    assert store.open_items()[0].declared_lane == ""
    assert store.get_row(SESSION).declared_lane == ""
    assert _shape(store.get_row(SESSION)) == _shape(without_key)


def test_the_empty_string_parks_as_the_empty_string_and_is_never_repaired_into_a_tier(monkeypatch, frozen_clock):
    """没声明就是没声明：绑进库的是空串本身，不是 None，也不是任何一档。

    两件事一起钉：NOT NULL 列喂 None 会炸（所以兜底值不许是 None），``or "qa"`` 之类的
    兜底会把"没人定过"改写成"有人定了最便宜那一档"。
    """
    ledger = _park(monkeypatch=monkeypatch, clock=frozen_clock, declared="")
    _sql, bound = _insert_statement(ledger)

    assert bound[-1] == ""
    assert store.get_row(SESSION).declared_lane == ""
    assert store.open_items()[0].declared_lane == ""

    not_null = _FakeLedger(LANDED_COLUMNS, frozen_clock)
    monkeypatch.setattr(store, "_conn", lambda: not_null)
    with pytest.raises(_NotNullViolation):
        not_null.execute(
            "INSERT INTO pending_approvals (session_id, owner_user_id, parked_steps, status, "
            "request_id, trace_id, task_id, created_at, expires_at, declared_lane) "
            "VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)",
            (SESSION, OWNER, '["export"]', store.AWAITING, None, None, None,
             NOW.isoformat(), (NOW + timedelta(hours=1)).isoformat(), None),
        )


# ==================================================== 判据 2：绑值只准走同源
def test_the_value_that_lands_is_the_one_the_only_normalizer_produced(monkeypatch, frozen_clock):
    """入口链算出什么，库里就是什么：""／qa／analysis／report 四值逐个真打一遍。

    通路：``declared_lane_from_config(config)`` → ``normalize_declared_lane(declared)``
    → 这一枚实参 → 这一格列。中间不许有人再动它一次。
    """
    for tier in ("", LANE_QA, LANE_ANALYSIS, LANE_REPORT):
        config = {"configurable": {DECLARED_LANE_KEY: tier}} if tier else {}
        declared = normalize_declared_lane(declared_lane_from_config(config))
        assert declared in ("", *tuple(LANE_TIERS)), declared

        _use_pg(monkeypatch, clock=frozen_clock)
        store.record_awaiting(SESSION, OWNER, STEPS, declared_lane=declared)

        assert store.get_row(SESSION).declared_lane == declared
        assert store.open_items()[0].declared_lane == declared


def test_the_storage_layer_repairs_nothing_it_is_handed(monkeypatch, frozen_clock):
    """未知拼写不归本层管：交进来长什么样，绑出去就长什么样（不洗、不补、不拒）。

    这一枚是反证 (b) 的行为半边：storage 层一旦长出第二份归一化（把 REPORT 洗成
    report、或把不认识的退成 ""／"qa"），这里立刻红。硬失败属于入口：
    ``normalize_declared_lane("REPORT")`` 当场 raise。
    """
    assert normalize_declared_lane("") == ""
    with pytest.raises(ValueError):
        normalize_declared_lane("REPORT")
    with pytest.raises(ValueError):
        normalize_declared_lane("repot")

    ledger = _park(monkeypatch=monkeypatch, clock=frozen_clock, declared="REPORT")
    _sql, bound = _insert_statement(ledger)

    assert bound[-1] == "REPORT"
    assert store.get_row(SESSION).declared_lane == "REPORT"
    # 脏行也不许被读成一档：闭集校验在读侧（chat._parked_declaration），退向是"没有记录"。
    assert chat._parked_declaration(SESSION) == ""


def test_the_resume_readout_reads_the_lane_back_over_the_pg_leg(monkeypatch, frozen_clock):
    """这单真正的产物：批准后续跑那一轮，从 PG 台账读回挂起轮的声明。

    改前这一句是 resumed + declared_lane=""（档位随那一轮流掉了）；本单之后走的是
    ``get_row`` 那条 PG 腿，读数落 resumed 而不是 explicit/r42 —— 沿用不等于现声明。
    """
    _park(monkeypatch=monkeypatch, clock=frozen_clock, declared=LANE_REPORT)

    readout = chat._resumed_lane_readout(SESSION)

    assert readout["declared_lane"] == LANE_REPORT
    assert readout["lane_source"] == LANE_SOURCE_RESUMED
    assert readout["lane"] == ""


# ==================================================== 结构守卫：这一层不许知道词表
def _module_tree() -> ast.Module:
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def _string_literals() -> list[str]:
    """本模块里每一枚字符串常量（含拼接前的相邻字面量，parse 期已折成一枚）。"""
    return [
        node.value
        for node in ast.walk(_module_tree())
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _docstring_ids(tree: ast.AST) -> set[int]:
    """docstring 里点名那枚唯一通路是写给维护者看的路标，不是第二份实现。"""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def test_the_storage_layer_names_no_lane_vocabulary_of_its_own():
    """本层代码里既不出现档位字面量，也不引用 nodes 的词表/归一化 —— 反证 (b) 的结构半边。

    判据 2 说"不许在 storage 层再写一份归一化"，落到可执行上就是：这一层既没有词可查，
    也没有把空值兜成某一档的形状。它连 ``import app.agents`` 都没有，想抄也抄不动。
    """
    tree = _module_tree()
    docstrings = _docstring_ids(tree)
    vocabulary = set(LANE_TIERS) | {
        "LANE_TIERS", "LANE_QA", "LANE_ANALYSIS", "LANE_REPORT",
        "normalize_declared_lane", "declared_lane_from_config", "resolve_turn_lane",
        "turn_lane_from_decision", "resumed_lane", "not_routed_lane",
    }

    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    }
    names = {
        node.id if isinstance(node, ast.Name) else node.attr
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute))
    }
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert not literals & vocabulary, literals & vocabulary
    assert not names & vocabulary, names & vocabulary
    assert not {name for name in imports if name.startswith("app.agents")}, imports


def test_no_fallback_default_can_breathe_a_tier_into_an_empty_declaration():
    """不许有 ``x or "qa"`` / ``x if ... else "report"`` / ``get(k, "analysis")`` 这一类形状。

    三态里的第三态就是从这种兜底里长出来的：把"没人声明"读成"有人定了一档"，
    续跑轮的读数于是开始说谎。
    """
    tree = _module_tree()
    tiers = set(LANE_TIERS)
    hits: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            operands = node.values
        elif isinstance(node, ast.IfExp):
            operands = [node.body, node.orelse]
        elif isinstance(node, ast.Call):
            fname = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            operands = node.args if fname in {"get", "setdefault", "pop"} else []
        else:
            continue
        hits += [
            repr(operand.value)
            for operand in operands
            if isinstance(operand, ast.Constant) and operand.value in tiers
        ]

    assert hits == []


def test_this_ticket_lands_no_backfill_and_no_new_write_shape(monkeypatch, frozen_clock):
    """存量 83 行零回填：本层会写行的语句只有既有那两枚闭合，SET 里永远没有这一格。

    写侧一次挂起 = 一枚 INSERT；改状态 = 一枚 UPDATE status。多出任何一枚 UPDATE，
    或者哪条 UPDATE 开始碰 ``declared_lane``，就意味着有人开始给历史行编造档位。
    """
    mutations = [
        literal
        for literal in _string_literals()
        if re.match(r"\s*(UPDATE|DELETE|TRUNCATE|INSERT)", literal, re.I)
    ]
    updates = [item for item in mutations if "UPDATE pending_approvals" in item]

    assert len(updates) == 2, updates
    assert all("declared_lane" not in item for item in updates), updates
    assert len([item for item in mutations if "INSERT INTO pending_approvals" in item]) == 1

    # 真跑一遍：同一会话二次挂起，旧行按既有口径闭合为 stale，那一格仍原样躺在两行上。
    ledger = _park(monkeypatch=monkeypatch, clock=frozen_clock, declared=LANE_ANALYSIS)
    frozen_clock.value = NOW + timedelta(minutes=5)
    store.record_awaiting(SESSION, OWNER, STEPS, declared_lane="")

    rows = ledger.rows
    assert [row["status"] for row in rows] == [store.STALE, store.AWAITING]
    assert [row["declared_lane"] for row in rows] == [LANE_ANALYSIS, ""]
    assert [row.declared_lane for row in store.open_items()] == [""]