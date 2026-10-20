# -*- coding: utf-8 -*-
"""R303 · 通知中心收口（二）：PG 那条 UPSERT 真被执行，推进规则只有 contracts 那一处。

R299 交工时自己写着：apply_state 的 PG 分支「从未被执行过」，同一枚新键上的并发抢写只有推理与
注释。本文件把那一句从推理变成读数 —— 用一枚会记账的假连接（记 SQL 文本与绑定参数，并按语句真的
改一份行），把语句形状、执行事实、幂等与并发单调性逐条钉住。零真连：全程只换 states 那一层的
_database_available 与 _conn 两枚既有缝，本文件不出现任何 psycopg.connect。

形状（判据②前半）：钉的是语句本身 —— ON CONFLICT (notification_id, recipient) DO UPDATE、列名、
列序、SET state = EXCLUDED.state，而且冲突目标要从 0016 那枚 reader_key 现读出来对判，不是本文
件手抄一遍列名：迁移改了列，这里就得跟着红。

规则唯一（判据②后半）：终态单调这句话必须由 contracts.advance_state 那一处保证。这里用两枚互补的
钉：一枚把 advance_state 换成会记录入参/返回的代理，断言落库的那个值就是它返回的那个值、且每条
写口都由它决策；另一枚走 AST，断言 states.py 里 final 只有一个赋值点、右值就是 advance_state 这
一枚调用，并且文件里不存在第二份状态序。复制一份推进规则进 states.py 是「第二本账」的病根形状，
两枚钉都不同意。

并发（判据②末段）：两线程对同一枚 (notification_id, recipient) 抢写，钉的是「dismissed 不被 read
复活」—— 这一枚从一行已提交的 dismissed 起跳，那是真 PG 的行锁覆盖得下的形状。另一枚件不假装新
键上的抢写窗口已被修好：它把「两枚线程都读了、都写了，表里恰好留下一行合法词，留下的是最后一次
写的值」原样记进账 —— 代码注释明写着不处理那种情形，测试就照这个口径判，多一句都不说。

反证 (b) 与 (d) 在文件末尾：变异只落影子副本并 exec 进内存，盘上那枚 states.py 全程只读，进出各量
一次 sha256；AST 那枚钉读的是 overlay.authoritative_text，所以窗内看的是变异版。
"""
from __future__ import annotations

import ast
import re
import threading

import pytest

from app.notifications import contracts
from app.notifications import states as state_store
from tests import _temp_edit_overlay as overlay
from tests.test_r303_notification_pins import STATES_PY, _mutate, _tracked_sha

REPO = overlay.REPO
MIGRATION = REPO / "migrations" / "0016_notification_states.sql"

TABLE = "notification_states"
RECIPIENT = "r303-pg-reader"
IDENTIFIER = "alert:3030"
OTHER = "alert:3031"

#: 反证窗里那两枚变异：(b) 把 UPSERT 换成先 DELETE 再 INSERT；(d) 把推进规则复制进 states.py。
_UPSERT_ANCHOR = (
    "            f'INSERT INTO {TABLE} '",
    "                '(notification_id, recipient, state, recorded_at, updated_at) '",
    "                'VALUES (%s, %s, %s, %s, %s) '",
    "                'ON CONFLICT (notification_id, recipient) DO UPDATE SET '",
    "                'state = EXCLUDED.state, updated_at = EXCLUDED.updated_at',",
)
_UPSERT_MUTANT = (
    "            f'DELETE FROM {TABLE} WHERE notification_id = %s AND recipient = %s',",
    "            (identifier, person),",
    "        )",
    "        conn.execute(",
    "            f'INSERT INTO {TABLE} '",
    "                '(notification_id, recipient, state, recorded_at, updated_at) '",
    "                'VALUES (%s, %s, %s, %s, %s)',",
)
_COPIED_RULE_ANCHOR = ("    final = advance_state(current, requested)",)
_COPIED_RULE_MUTANT = (
    "    _copied_order = {'read': 1, 'dismissed': 2}",
    "    final = requested if requested in _copied_order else current",
)


class _Result:
    """psycopg 的 dict_row 结果把手：两条腿都按键取值，取不到就是 None 或空列表。"""

    def __init__(self, rows) -> None:
        self._rows = list(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeStateTable:
    """notification_states 的替身：记 SQL 文本与绑定参数，并按语句真的改一份行。

    它只被教过四条语句（表在不在、整份读、单枚 FOR UPDATE 读、写口），没被教过的形状当场抛 ——
    什么都答的桩会把「这条腿根本没被执行」糊成一枚绿钉。写口按 PostgreSQL 的语义落：带 ON
    CONFLICT 就撞在 reader_key 上做 UPDATE；不带冲突目标的 INSERT 撞上同一枚键就是唯一约束冲突，
    不是又一次静默覆盖。
    """

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, str]] = {}
        self.log: list[tuple[str, tuple]] = []
        self.commits = 0
        self.conflict_writes = 0
        self.reads = 0
        self._lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        raise AssertionError("生命周期这一层不回滚：写下的结论就是结论")

    @property
    def write_statements(self) -> list:
        return [
            entry
            for entry in self.log
            if entry[0].split(" ")[0].lower() in ("insert", "delete")
        ]

    def execute(self, sql, params=None):
        bound = tuple(params or ())
        statement = " ".join(str(sql).split())
        with self._lock:
            self.log.append((statement, bound))
            head = statement.lower()
            if head.startswith("select to_regclass"):
                return _Result([{"table_name": TABLE}])
            if head.startswith("select notification_id, state from"):
                self.reads += 1
                person = bound[0]
                return _Result(
                    [
                        {"notification_id": key[0], "state": row["state"]}
                        for key, row in self.rows.items()
                        if key[1] == person
                    ]
                )
            if head.startswith("select state from"):
                self.reads += 1
                person, identifier = bound
                row = self.rows.get((identifier, person))
                return _Result([{"state": row["state"]}] if row else [])
            if head.startswith("insert into"):
                self._apply_insert(statement, bound)
                return _Result([])
            if head.startswith("delete from"):
                identifier, person = bound
                self.rows.pop((identifier, person), None)
                return _Result([])
            raise AssertionError("替身没被教过这条语句，不替谁说谎：" + statement)

    def _apply_insert(self, statement: str, bound: tuple) -> None:
        identifier, person, state, recorded_at, updated_at = bound
        key = (identifier, person)
        upsert = " on conflict " in statement.lower()
        if key in self.rows and not upsert:
            raise AssertionError(
                'duplicate key violates notification_states_reader_key: ' + str(key)
            )
        if upsert:
            self.conflict_writes += 1
        existing = self.rows.get(key)
        self.rows[key] = {
            "state": state,
            "recorded_at": existing["recorded_at"] if existing else recorded_at,
            "updated_at": updated_at,
        }


def _pg_leg(monkeypatch) -> _FakeStateTable:
    """把 states 那一层接到替身上：只换 _database_available 与 _conn 两枚既有缝。"""
    table = _FakeStateTable()
    monkeypatch.setattr(state_store, "_ROWS", {})
    monkeypatch.setattr(state_store, "_database_available", lambda: True)
    monkeypatch.setattr(state_store, "_conn", lambda: table)
    return table


def _reader_key_columns() -> list:
    """冲突目标从 0016 现读：迁移改列，这里就得跟着红，而不是跟着一份手抄清单绿着。"""
    ddl = MIGRATION.read_bytes().decode("utf-8")
    match = re.search(
        r"CONSTRAINT\s+notification_states_reader_key\s+UNIQUE\s*\((?P<cols>[^)]*)\)",
        ddl,
        re.IGNORECASE,
    )
    if match is None:
        raise AssertionError("0016 里找不到那枚 reader_key：对判不能降级成看运气")
    return [piece.strip() for piece in match.group("cols").split(",") if piece.strip()]


def _assert_upsert_shape(table: _FakeStateTable, expected_state: str) -> dict:
    """判据②前半句的不变量本身：一次写 = 一枚 INSERT，形状就是那条 UPSERT。

    反证 (b) 也在这一枚 helper 上跑红字。另搓一份「只看有没有落行」的弱判等于把牙齿留在窗外。
    """
    writes = table.write_statements
    assert len(writes) == 1, (
        "一次 apply_state 应当只发一枚写口，实发 " + str(len(writes)) + " 枚："
        + " | ".join(entry[0][:70] for entry in writes)
    )
    statement, bound = writes[0]
    assert statement.lower().startswith("insert into"), statement
    assert "delete" not in statement.lower(), (
        "生命周期这一层不发 DELETE：划掉是一格状态，不是一行消失"
    )
    assert "ON CONFLICT (notification_id, recipient) DO UPDATE" in statement, (
        "写口不是那条 ON CONFLICT ... DO UPDATE 形状的 UPSERT，全部证据就在下一行：" + statement
    )
    assert (
        "(notification_id, recipient, state, recorded_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s)" in statement
    ), "列名与列序不对，或绑定不是五枚占位符：" + statement
    assert (
        "DO UPDATE SET state = EXCLUDED.state, updated_at = EXCLUDED.updated_at" in statement
    ), "DO UPDATE 没有只推进 state 与 updated_at 这两格：" + statement
    target = re.search(r"ON CONFLICT \(([^)]*)\)", statement)
    assert target is not None, statement
    assert [piece.strip() for piece in target.group(1).split(",")] == _reader_key_columns(), (
        "冲突目标与 0016 上那枚 reader_key 的列不同源"
    )
    assert bound[0] == IDENTIFIER and bound[1] == RECIPIENT, bound
    assert bound[2] == expected_state, bound
    assert bound[3] == bound[4] and bound[3], (
        "recorded_at 与 updated_at 同源同一枚时钟：" + str(bound)
    )
    assert table.commits == 1, table.commits
    assert table.rows[(IDENTIFIER, RECIPIENT)]["state"] == expected_state
    return table.rows[(IDENTIFIER, RECIPIENT)]


# ------------------------------------------------------- 形状：那条 ON CONFLICT 真被执行过


def test_the_pg_leg_sends_the_upsert_it_only_claimed_in_comments(monkeypatch):
    table = _pg_leg(monkeypatch)

    outcome = state_store.apply_state(RECIPIENT, IDENTIFIER, contracts.STATE_DISMISSED)

    assert outcome == {"state": "dismissed", "changed": True, "notification_id": IDENTIFIER}
    _assert_upsert_shape(table, "dismissed")
    assert table.conflict_writes == 1
    assert state_store._ROWS == {}, "PG 就绪时不许同时往内存腿再写一份：那是第二本账"


def test_the_write_leg_reads_through_the_table_not_through_the_memory_copy(monkeypatch):
    """回执说有这一行不算数：同一枚假连接上再读一次，两条读语句都得真发出去过。"""
    table = _pg_leg(monkeypatch)
    state_store.apply_state(RECIPIENT, IDENTIFIER, contracts.STATE_READ)

    assert state_store.read_state(RECIPIENT, IDENTIFIER) == "read"
    assert state_store.recipient_states(RECIPIENT) == {IDENTIFIER: "read"}

    single = [entry[0] for entry in table.log if entry[0].lower().startswith("select state from")]
    listing = [
        entry[0]
        for entry in table.log
        if entry[0].lower().startswith("select notification_id, state")
    ]
    # apply_state 自己那次 FOR UPDATE 读，加上这一枚显式读：两条都真到过表，不是内存腿答的。
    assert len(single) == 2 and all(item.endswith("FOR UPDATE") for item in single), table.log
    assert len(listing) == 1 and "WHERE recipient = %s" in listing[0], table.log
    assert "state =" not in listing[0], (
        "整份读不许在 SQL 里按状态裁：未读没有行，裁了就数不出来"
    )


def test_a_repeated_action_writes_nothing_and_answers_the_same_conclusion(monkeypatch):
    """幂等在 PG 腿上的形状：第二次同一枚动作一枚写口都不发，结论仍是 dismissed。"""
    table = _pg_leg(monkeypatch)
    state_store.apply_state(RECIPIENT, IDENTIFIER, contracts.STATE_DISMISSED)
    writes_after_first = len(table.write_statements)

    again = state_store.apply_state(RECIPIENT, IDENTIFIER, contracts.STATE_DISMISSED)

    assert again == {"state": "dismissed", "changed": False, "notification_id": IDENTIFIER}
    assert len(table.write_statements) == writes_after_first, "重复动作不该再发一次写口"
    assert table.commits == 1, table.commits


# ------------------------------------------------- 规则唯一：落库的值只由 advance_state 决定


def _spy_advance_state(monkeypatch) -> list:
    """把 contracts.advance_state 换成记录器，并同时换掉 states.py 里那一格同名绑定。

    两处都换才叫「只此一处」：只换 contracts 那一头，谁在 states.py 里复制一份规则照样能溜过去。
    """
    calls: list = []
    original = contracts.advance_state

    def spy(current, requested):
        final = original(current, requested)
        calls.append((current, requested, final))
        return final

    monkeypatch.setattr(contracts, "advance_state", spy)
    monkeypatch.setattr(state_store, "advance_state", spy)
    return calls


def test_every_stored_value_is_what_advance_state_returned(monkeypatch):
    calls = _spy_advance_state(monkeypatch)
    table = _pg_leg(monkeypatch)

    first = state_store.apply_state(RECIPIENT, IDENTIFIER, contracts.STATE_DISMISSED)
    second = state_store.apply_state(RECIPIENT, IDENTIFIER, contracts.STATE_READ)
    third = state_store.apply_state(RECIPIENT, OTHER, contracts.STATE_READ)
    fourth = state_store.apply_state(RECIPIENT, OTHER, contracts.STATE_DISMISSED)

    assert [one["changed"] for one in (first, second, third, fourth)] == [True, False, True, True]
    assert calls == [
        (None, "dismissed", "dismissed"),
        ("dismissed", "read", "dismissed"),
        (None, "read", "read"),
        ("read", "dismissed", "dismissed"),
    ], calls
    assert table.rows[(IDENTIFIER, RECIPIENT)]["state"] == "dismissed"
    assert table.rows[(OTHER, RECIPIENT)]["state"] == "dismissed"
    assert len(table.write_statements) == 3, (
        "四枚动作里只有三次真的改变那本账，第四次不许发写口：" + str(len(table.write_statements))
    )


def _states_source() -> str:
    """窗内读影子副本的变异版、窗外读盘上的被跟踪文件：同一份判法，两种视图。"""
    return overlay.authoritative_text(overlay.rel_of(STATES_PY))


def _final_assignments(source: str) -> list:
    """apply_state 里对 final 的所有赋值右值。"""
    tree = ast.parse(source)
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "apply_state"
    ]
    assert len(functions) == 1, "states.py 里 apply_state 应当只有一枚定义"
    found = []
    for node in ast.walk(functions[0]):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "final":
                    found.append(node.value)
    return found


def test_states_py_carries_no_second_advancement_rule():
    """AST 那一枚钉：final 只有一个赋值点，右值就是 advance_state 那一枚调用。

    再加两格防抄近路：文件里不许出现第二份状态序（把两枚词映射成序号的字典），也不许去引用
    contracts 私有那枚 _STATE_ORDER。规则写两遍迟早会各漂一次，那正是本期判据⑥要防的形状。
    """
    source = _states_source()
    assigns = _final_assignments(source)

    assert len(assigns) == 1, "final 被赋值 " + str(len(assigns)) + " 次：推进规则不止一处"
    only = assigns[0]
    assert isinstance(only, ast.Call), (
        "final 的右值不再是一枚调用，推进规则被就地重写了：" + ast.dump(only)
    )
    assert getattr(only.func, "id", None) == "advance_state", (
        "final 由另一枚函数决定，不是 advance_state：" + ast.dump(only)
    )

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [
                item.value
                for item in node.keys
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            ]
            values = [item.value for item in node.values if isinstance(item, ast.Constant)]
            ranked = bool(values) and all(isinstance(item, int) for item in values)
            assert not ({"read", "dismissed"} <= set(keys) and ranked), (
                "states.py 里出现了一份状态序字典：推进规则被抄了第二遍"
            )
    assert "_STATE_ORDER" not in source, (
        "states.py 去引用 contracts 的私有词序，也是第二本账的形状"
    )


# ------------------------------------------------------------------- 并发：同一枚键上抢写


def test_two_threads_racing_the_same_pair_never_revive_a_dismissed_row(monkeypatch):
    """一行已提交的 dismissed 之上，两线程各按 read 与 dismissed 猛写：终态恒为 dismissed。

    这一枚从「行已经存在」起跳 —— 那是真 PG 的行锁覆盖得下的形状，也是契约里那句「划掉的不许被
    标为已读悄悄放回收件箱」。落在这个形状上的单调性由 advance_state 独担：两条腿每次都先读再判，
    读到 dismissed 就一处都不写。
    """
    table = _pg_leg(monkeypatch)
    _spy_advance_state(monkeypatch)
    state_store.apply_state(RECIPIENT, IDENTIFIER, contracts.STATE_DISMISSED)
    writes_before = len(table.write_statements)
    failures: list = []
    gate = threading.Barrier(2)

    def hammer(action: str) -> None:
        try:
            gate.wait()
            for _ in range(30):
                outcome = state_store.apply_state(RECIPIENT, IDENTIFIER, action)
                if outcome["state"] != "dismissed":
                    raise AssertionError("dismissed 被 read 复活了：回执 " + str(outcome))
                if outcome["changed"]:
                    raise AssertionError(
                        "一次没有推进的动作被报成 changed=True：" + str(outcome)
                    )
        except BaseException as exc:  # noqa: BLE001 - 线程里的红字必须能带回主线程
            failures.append(exc)

    threads = [
        threading.Thread(target=hammer, args=(contracts.STATE_READ,)),
        threading.Thread(target=hammer, args=(contracts.STATE_DISMISSED,)),
    ]
    for one in threads:
        one.start()
    for one in threads:
        one.join(timeout=60)

    assert failures == [], failures
    assert list(table.rows) == [(IDENTIFIER, RECIPIENT)], table.rows
    assert table.rows[(IDENTIFIER, RECIPIENT)]["state"] == "dismissed"
    assert len(table.write_statements) == writes_before, (
        "抢写期间一枚写口都不该发出去：两条腿都读到 dismissed，都不该落笔"
    )


def test_a_first_write_race_on_an_unseen_pair_leaves_exactly_one_legal_row(monkeypatch):
    """新键上的抢写：这一枚件钉的是代码实际承诺的那一格，不替它吹另一格。

    states.py 的注释明写着「一枚从没出现过的键上若真有两件不同的动作并发抢写，锁不到不存在的行
    —— 这里不假装处理过那种情形」。所以本件只判它能判的：两枚线程都真的读了也真的写了，表里恰好
    留下一行（reader_key 与 ON CONFLICT 保证的那一格）、留下的词在封闭词表里、就是最后一次写的
    值。谁赢不判 —— 把那一格写成「单调性成立」就是假话，它记在交工回执的诚实账里。
    """
    table = _pg_leg(monkeypatch)
    calls = _spy_advance_state(monkeypatch)
    gate = threading.Barrier(2)
    failures: list = []

    def race(action: str) -> None:
        try:
            gate.wait()
            state_store.apply_state(RECIPIENT, IDENTIFIER, action)
        except BaseException as exc:  # noqa: BLE001
            failures.append(exc)

    threads = [
        threading.Thread(target=race, args=(contracts.STATE_DISMISSED,)),
        threading.Thread(target=race, args=(contracts.STATE_READ,)),
    ]
    for one in threads:
        one.start()
    for one in threads:
        one.join(timeout=60)

    assert failures == [], failures
    assert list(table.rows) == [(IDENTIFIER, RECIPIENT)], table.rows
    survivors = [row["state"] for row in table.rows.values()]
    assert all(word in contracts.NOTIFICATION_STATES for word in survivors), survivors
    assert len(calls) == 2, calls
    assert table.reads >= 2, table.reads
    assert len(table.write_statements) >= 1
    assert table.conflict_writes == len(table.write_statements), (
        "写口一旦不带冲突目标，reader_key 那一格就不再是它说的那句话"
    )


# --------------------------------------------------------------- 判据⑤：反证 (b) 与 (d)


def test_counter_evidence_b_delete_then_insert_breaks_the_upsert_pin(monkeypatch):
    """反证 (b)：把 UPSERT 换成先 DELETE 再 INSERT ⇒ 判据②的形状钉必须红。"""
    before = _tracked_sha(STATES_PY)

    with _mutate(STATES_PY, _UPSERT_ANCHOR, _UPSERT_MUTANT):
        # 腿要在窗内接：exec 变异版会把模块顶层每一格重造一遍，先接上的腿会被它抹掉。
        table = _pg_leg(monkeypatch)
        state_store.apply_state(RECIPIENT, IDENTIFIER, contracts.STATE_DISMISSED)
        with pytest.raises(AssertionError) as caught:
            _assert_upsert_shape(table, "dismissed")
        message = str(caught.value)
        assert "一枚写口" in message or "ON CONFLICT" in message, message
        assert any(entry[0].lower().startswith("delete") for entry in table.write_statements), (
            "变异版根本没发出 DELETE：这枚反证没被执行，红字不算数"
        )

    assert before == _tracked_sha(STATES_PY), "反证窗碰过盘上的文件：字节凭据不对"
    fresh = _pg_leg(monkeypatch)
    state_store.apply_state(RECIPIENT, IDENTIFIER, contracts.STATE_DISMISSED)
    _assert_upsert_shape(fresh, "dismissed")


def test_counter_evidence_d_a_copied_rule_reddens_monotonicity_and_provenance(monkeypatch):
    """反证 (d)：在 states.py 里复制一份推进规则 ⇒ 单调性、同源、AST 三枚钉一起红。

    这一枚要防的不是「算错了一个分支」，而是第二本账的形状本身：规则一旦在存储层复写，契约里那句
    「单向、重复不改变结论」就有两处可以各自漂移。
    """
    before = _tracked_sha(STATES_PY)
    with _mutate(STATES_PY, _COPIED_RULE_ANCHOR, _COPIED_RULE_MUTANT):
        calls = _spy_advance_state(monkeypatch)
        table = _pg_leg(monkeypatch)

        with pytest.raises(AssertionError) as ast_red:
            test_states_py_carries_no_second_advancement_rule()
        assert "推进规则" in str(ast_red.value), str(ast_red.value)

        state_store.apply_state(RECIPIENT, IDENTIFIER, contracts.STATE_DISMISSED)
        revived = state_store.apply_state(RECIPIENT, IDENTIFIER, contracts.STATE_READ)

        assert revived["changed"] is True and revived["state"] == "read", (
            "变异版居然还守着单调：这枚反证没牙 -> " + str(revived)
        )
        assert table.rows[(IDENTIFIER, RECIPIENT)]["state"] == "read", table.rows
        assert calls == [], "复制的规则仍在调 advance_state：变异没落到那一格"
        assert state_store.recipient_states(RECIPIENT) == {IDENTIFIER: "read"}

    assert before == _tracked_sha(STATES_PY), "反证窗碰过盘上的文件：字节凭据不对"
    test_states_py_carries_no_second_advancement_rule()
