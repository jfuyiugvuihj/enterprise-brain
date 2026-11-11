"""R418 · 常驻派生钉：严格假库所答的问，必须罩得住 ``insert_if_absent`` 真问的问。

来路（主树 2026-09-27 全量门里唯一那枚红）：
``tests/test_r38_native_input_tokens.py::test_both_counts_reach_the_postgres_insert_parameters``
拿到 ``[]``——一枚 ``INSERT INTO model_calls`` 都没观察到。根因不在生产：那枚用例就地手搓的
假连接只答了这条写链两问里的一问，于是空表上一枚自由的 key 也被判成「已被占用」
（``app/trace/store.py:518`` 的 ``insert_if_absent`` 拿到 ``rowcount`` 的缺省 0），
``_apply_event_row`` 抛 ``EventIdTakenError``，该事件的其余投影一枚都不写，两枚事件一起
掉进兜底账。修的是桩，判据 ``:328`` 一字未动。

本钉管下一次。写链今天问两问，明天可能问三问——真要问的那天假库答不上来，得有枚件当场喊，
而不是又留一红给下一班去重新猜「这是桩过期还是生产有格子」。所以两头都不许手抄清单：

- 「真问的问」从 ``app/storage/persistence.py`` 的 **AST 现场派生**（连接对象、驱动返回
  对象、以及执行期真的发出去的语句），源码多读一个属性或多发一条语句，这里跟着长；
- 「所答的问」从 ``tests/_r250_fake_postgres.py`` **现场派生**（实例可答的名字 + 模块里
  编译好的语句识别式），R250 家哪天删掉一条识别式，这里也跟着长；
- 判据就是这两集合之间的 ⊇，外加一枚「把任一问噤掉，自由 key 就不再报本次写入」的牙。

🔴 锚点取不到＝红，绝不是跳过：R346/R377/R396/R398/R400 全是「账没跟着现实加长」这一族。
全程离线：只在内存字典上执行，一次数据库连接都不建立，也不改 ``app/**``。
"""
from __future__ import annotations

import ast
import re

from app.storage import persistence as persistence_module
from app.storage.persistence import PostgresPersistenceAdapter
from app.trace import run_reader as run_reader_module
from app.trace.run_reader import TraceDatabase
from tests import _r250_fake_postgres as fake_module
from tests._r250_fake_postgres import FakeConnection, FakePostgres, FakeResult

#: The one write in this codebase whose answer is a verdict about a key (R272).
PRIMITIVE = "insert_if_absent"
#: The number-line question the same connection answers for the same event write (R263).
SEQUENCE_READER = "max_sequence"
#: A protected row needs an owner before ``_prepare`` will even build a statement.
OWNER = "owner-r418"


# ------------------------------------------------------------------ the derivation
def _source(module, label: str) -> tuple[str, str]:
    """Read a module's bytes off disk, so line numbers match ``git grep -n``."""
    path = getattr(module, "__file__", "") or ""
    if not path:
        raise AssertionError(f"锚点取不到：{label} 没有 __file__，无法现场派生")
    return open(path, encoding="utf-8").read(), path


def _class_node(source: str, class_name: str, path: str) -> ast.ClassDef:
    for node in ast.parse(source).body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise AssertionError(
        f"锚点取不到：{path} 里没有 class {class_name}——本钉盯的东西改名了，范围跟着漂了"
    )


def _bound_from(fn: ast.AST, attribute: str) -> set[str]:
    """Names this function binds from ``self.<attribute>(...)``."""
    found: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == attribute
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "self"
        ):
            found.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return found


def _driver_methods(methods: dict[str, ast.FunctionDef]) -> set[str]:
    """Which methods actually reach a driver connection.

    Derived rather than named: a method counts when its body calls ``<handle>.execute(...)`` on
    a name bound from ``self.connection_factory()``. A rename cannot quietly narrow this pin.
    """
    reached: set[str] = set()
    for name, fn in methods.items():
        handles = _bound_from(fn, "connection_factory")
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "execute"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in handles
            ):
                reached.add(name)
                break
    if not reached:
        raise AssertionError("锚点取不到：没有任何方法朝 connection_factory 拿来的对象 execute")
    return reached


def _handles_returned_by(fn: ast.AST, driver_methods: set[str]) -> set[str]:
    """Names bound in *fn* from a call to one of the methods that reach the driver."""
    found: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if (
            isinstance(call.func, ast.Attribute)
            and call.func.attr in driver_methods
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "self"
        ):
            found.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return found


def _questions_asked_of(handles: set[str], nodes: list[ast.AST]) -> set[str]:
    """Every attribute name read off one of *handles*, in all three spellings."""
    asked: set[str] = set()
    for root in nodes:
        for node in ast.walk(root):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in handles
            ):
                asked.add(node.attr)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"getattr", "hasattr", "delattr"}
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in handles
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                asked.add(node.args[1].value)
    return asked - {"__class__"}


def derive_questions() -> tuple[set[str], set[str]]:
    """(attributes read off the driver result, attributes read off the connection), now."""
    source, path = _source(persistence_module, "app.storage.persistence")
    cls = _class_node(source, PostgresPersistenceAdapter.__name__, path)
    methods = {
        node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)
    }
    primitive = methods.get(PRIMITIVE)
    if primitive is None:
        raise AssertionError(f"锚点取不到：{path} 的 {cls.name} 里没有 {PRIMITIVE}")
    drivers = _driver_methods(methods)

    result_handles = _handles_returned_by(primitive, drivers)
    if not result_handles:
        raise AssertionError(
            f"锚点取不到：{PRIMITIVE} 没有把任何名字绑定到驱动返回的对象上"
        )
    result_questions = _questions_asked_of(result_handles, [primitive])
    if not result_questions:
        raise AssertionError(
            f"锚点取不到：{PRIMITIVE} 没有朝驱动对象读任何属性——那一问换写法了，本钉得跟着改读法"
        )

    connection_handles: set[str] = set()
    helper_nodes = [methods[name] for name in sorted(drivers)]
    for fn in helper_nodes:
        connection_handles |= _bound_from(fn, "connection_factory")
    connection_questions = _questions_asked_of(connection_handles, helper_nodes)
    if not connection_questions:
        raise AssertionError("锚点取不到：连接对象上读不出任何属性")
    return result_questions, connection_questions


def derive_answers() -> tuple[set[str], set[str], list[re.Pattern]]:
    """(names a result answers, names a connection answers, statement shapes it recognises)."""
    result_answers = {n for n in dir(FakeResult([], [])) if not n.startswith("_")}
    connection_answers = {n for n in dir(FakeConnection(FakePostgres())) if not n.startswith("_")}
    _source_used, path = _source(fake_module, "tests._r250_fake_postgres")
    patterns = [value for value in vars(fake_module).values() if isinstance(value, re.Pattern)]
    if not patterns:
        raise AssertionError(f"锚点取不到：{path} 里没有编译好的语句识别式")
    return result_answers, connection_answers, patterns


class _Recorder(FakeConnection):
    """A connection that answers evenly and writes down every statement it was sent.

    It inherits the double so the shape of an answer stays identical; what it collects is
    whatever production code actually sends, so a third question shows up by itself instead of
    waiting for somebody to remember to add it to a list.
    """

    def __init__(self, engine: FakePostgres, log: list[str]) -> None:
        super().__init__(engine)
        self.log = log

    def execute(self, sql, params=None):  # noqa: ANN001 - the point is to accept anything
        self.log.append(" ".join(str(sql or "").split()))
        return FakeResult(["n"], [(7,)], rowcount=1)


class _Mute:
    """A driver result that cannot hear exactly one of the questions the source asks for."""

    def __init__(self, inner, hidden: str) -> None:  # noqa: ANN001
        self._inner = inner
        self._hidden = hidden

    def __getattr__(self, name: str):  # noqa: ANN204
        if name == self._hidden:
            raise AttributeError(name)
        return getattr(self._inner, name)


class _MutingConnection(FakeConnection):
    """The strict double with one derived question taken away from the result it hands back."""

    def __init__(self, engine: FakePostgres, hidden: str) -> None:
        super().__init__(engine)
        self.hidden = hidden

    def execute(self, sql, params=None):  # noqa: ANN001
        return _Mute(super().execute(sql, params), self.hidden)


def _event_row(trace: str, sequence: int, event_type: str, status: str) -> dict[str, object]:
    return {
        "trace_id": trace,
        "request_id": f"{trace}:req",
        "task_id": f"{trace}:task",
        "sequence": sequence,
        "event_type": event_type,
        "status": status,
        "owner_id": f"owner:{trace}",
        "payload": {"owner_id": f"owner:{trace}"},
        "created_at": None,
    }


def _verdict(adapter: PostgresPersistenceAdapter, record_id: str, row: dict) -> str:
    """What ``insert_if_absent`` says about a free key: written / held / raised:<Type>."""
    try:
        return "written" if adapter.insert_if_absent("trace_events", record_id, row) else "held"
    except Exception as exc:  # noqa: BLE001 - a missing answer may surface as an error
        return f"raised:{type(exc).__name__}"


# ------------------------------------------------------------------------ the ⊇ test
def test_the_double_answers_every_attribute_the_primitive_reads():
    """「``insert_if_absent`` 真问的问」⊆「严格假库所答的问」，两头都从现场派生。"""
    result_questions, connection_questions = derive_questions()
    result_answers, connection_answers, _patterns = derive_answers()

    missing_result = sorted(result_questions - result_answers)
    assert not missing_result, (
        f"写链朝驱动对象读了 {missing_result}，而 tests/_r250_fake_postgres.py 答不出这些名字。"
        "手搓的桩就是这样过期的：少答一问 ⇒ 空表上的自由 key 也被判成已被占用 ⇒ 整条投影链"
        "一枚都不写（R418）。要么让假库答上，要么让生产别再问，不许留着不答。"
    )
    missing_connection = sorted(connection_questions - connection_answers)
    assert not missing_connection, (
        f"写链朝连接对象读了 {missing_connection}，而假库答不出这些名字"
    )


def test_every_statement_the_write_chain_sends_is_one_the_double_recognises():
    """执行期派生：真发出去的每一条语句都得在假库认得的形状里。"""
    _result_questions, _connection_questions = derive_questions()
    _ra, _ca, patterns = derive_answers()

    engine = FakePostgres()
    sent: list[str] = []
    adapter = PostgresPersistenceAdapter(lambda: _Recorder(engine, sent))
    collections = sorted(persistence_module._TABLES)
    assert collections, "锚点取不到：_TABLES 是空的，本钉的语句通道就成了摆设"
    for collection in collections:
        assert adapter.insert_if_absent(
            collection, f"r418:{collection}", {"owner_id": OWNER}
        ) is True, f"{collection} 的 {PRIMITIVE} 没有报「本次写入」"

    if not hasattr(TraceDatabase, SEQUENCE_READER):
        raise AssertionError(f"锚点取不到：TraceDatabase 里没有 {SEQUENCE_READER} 这一问了")
    TraceDatabase(lambda: _Recorder(engine, sent)).max_sequence("trace-r418")

    assert len(sent) == len(collections) + 1, (
        f"以为会问 {len(collections) + 1} 条，实际发了 {len(sent)} 条：{sent}"
    )
    unanswered = [sql for sql in sent if not any(p.match(sql) for p in patterns)]
    assert not unanswered, (
        f"生产真发了假库不认得的语句：{unanswered[:2]}——认不出就回空行的假库会把这条写链"
        "测成假绿，所以严格件是直接喊（R250 立的规矩）"
    )


def test_silencing_any_one_derived_question_stops_a_free_key_reading_as_written():
    """🔴 牙：派生出的每一问都是承重的，噤掉任一枚，自由 key 就不再报「本次写入」。

    反过来说，如果哪一天噤掉某一问它仍然报「本次写入」，那一问就不是判据——本钉会红，
    提醒下一班「范围里躺着一枚不再承重的问」，而不是让 ⊇ 检查悄悄罩住一长串空问。
    """
    result_questions, _connection_questions = derive_questions()
    trace = "r418-mute"
    outcomes: dict[str, str] = {}

    for question in sorted(result_questions):
        honest = FakePostgres()
        honest_adapter = PostgresPersistenceAdapter(honest.connection_factory)
        assert honest_adapter.insert_if_absent(
            "trace_events", f"{trace}:1", _event_row(trace, 1, "request.started", "started")
        ) is True, "前提：严格假库对一枚自由的 key 报「本次写入」"
        assert honest_adapter.insert_if_absent(
            "trace_events", f"{trace}:1", _event_row(trace, 1, "tool_call.started", "running")
        ) is False, "前提：同一枚 key 第二次报「已被占用」"
        assert honest.rows("trace_events")[f"{trace}:1"]["event_type"] == "request.started", (
            "前提：被拒的那一次不许换掉已经在位的身"
        )

        muted = FakePostgres()
        muted_adapter = PostgresPersistenceAdapter(
            lambda muted=muted, question=question: _MutingConnection(muted, question)
        )
        outcomes[question] = _verdict(muted_adapter, f"{trace}:9", _event_row(trace, 9, "x", "y"))

    still_written = sorted(q for q, verdict in outcomes.items() if verdict == "written")
    assert not still_written, (
        f"噤掉 {still_written} 之后自由 key 仍然报「本次写入」：那一问不承重，"
        f"派生集合与假库的能力对不上号了。实测读数 {outcomes}"
    )
