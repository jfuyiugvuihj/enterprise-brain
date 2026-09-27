"""R392 · 声称 postgres / durable 的每一枚读数，都得自己把那张表现查出来。

症状（判据①，读数本件现取）：`app/common/monitoring.py` 那张五枚表把「这一腿存在哪」交给五枚读数
函数，健康报逐枚问。修前五枚里有两枚只看「库就绪」不看「表在位」——`profile_storage_state` 读的是
`auth._db_ready`（那枚旗标的凭据是 users 的现查，一步都没查过 user_profiles），`memory_storage_state`
更空，只读 `psycopg is not None`（一枚驱动导入成功与否的事实，既没连库也没查表）。于是在「生产 +
迁移没跑全」这一格上一台机器两张嘴：健康报把 memories / user_profiles 记进 durable 名单，同一时刻
`PUT /api/v1/profile` 答 503 `storage_unavailable`、`remember()` 交回 False。另三枚不在这张嘴的靶上：
`user_storage_state` 的凭据正是那枚对 `users` 现查过的旗标（本件把这条也量出来，防下一班改错），
`knowledge_graph` 与 `open_platform_apps` 从头到尾没声称过 postgres。

本件钉的是形状，逐枚抄文案一格都没有：

- 甲 覆盖面（T1/T2/T3）：名单逐行取自 `_STORAGE_SUBSYSTEMS` 的 AST，表里加一行就必须配一份能过关的
  读数；交回的键只能是 `monitoring._unavailable_state` 那五枚再加 `reason`，`protection` 只能取
  monitoring 自己分档时用过的字面值。
- 乙 凭据（T4）：一枚读数只要可能答 `storage_mode == "postgres"`，它的取证路径（含同模块内被它调到的
  函数）上就必须出现过一次针对该腿同名那张表的 `to_regclass` 现查——自己向共用探针问，或它读的那枚
  就绪旗标本身就是靠那张表的现查翻真的。
- 丙 借来的证据不算证据（同一枚钉）：`user_profiles` 这一腿拿 `users` 的旗标背书就是本班的病灶，所以
  「旗标覆盖的表」不许冒充「本腿的表」。
- 丁 三张脸各归各位（T6/T7/T8）：表在 ⇒ 必须敢说 durable（永远悲观同样是把健康报读废）；表不在 ⇒ 不许
  敢说；问不到 ⇒ 不许敢说，且不许写成迁移问题。
- 戊 与写路径同一副世界（T9/T10）：同一枚替身台账同时喂读路与写路，缺表那一格上两张嘴从此说同一句话。
- 己 边界（T11/T12/T13）：探针只问那一句、零 DDL 零 commit；非生产一支一发连接都不许多开；读路问的
  那张表必须与写路闸问的那张同名（两本账不许分叉）。
- 庚 说人话（T14）：那两句 detail 必须点名那张表并给出排查路，后端状态名与驱动原话不许占这个位置。
- 辛 判器自己要有牙（T15）：喂它一副「声称 postgres 而什么都没查」的假形状，它必须当场判不合格。

效力边界：全部跑在替身台账上。桩位是各条腿自己那枚既有的 `_conn`（探针不开新连接，见
`app/common/table_presence.py` 那段"什么不是它"），台账也只对 `to_regclass('public.x')` 这一句作答——
不求值任何真 SQL、不连真库、不起服务、不打模型、不写 chroma_db。
"""
from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

from app.common import auth, monitoring
from app.memory import long_term, profile

REPO = Path(__file__).resolve().parents[1]
MONITORING_REL = "app/common/monitoring.py"

#: 全仓唯一那枚「库连得上吗」的旗标，与共用的「表在位吗」探针。钉的是接口名，不是文案。
READINESS_FLAG = "_db_ready"
SHARED_PROBE = "probe_table"
REGCLASS_TABLE = re.compile(r"to_regclass\('public\.(\w+)'\)")

#: 本班改到那两枚读数所在的腿（丁戊己庚那几张脸的靶面）。逐枚点名，不给「新增一枚而没人管」留缝。
PG_LEGS = ("memories", "user_profiles")


# --------------------------------------------------------------- 取形状：一律 AST 现算，不抄源文本
def _source(relative: str) -> str:
    path = REPO / relative
    assert path.is_file(), f"判器不许降级成恒真：{relative} 读不到"
    return path.read_text(encoding="utf-8")


def _module_relative(module_path: str) -> str:
    relative = module_path.replace(".", "/") + ".py"
    assert (REPO / relative).is_file(), f"读数表指向一个不存在的模块：{relative}"
    return relative


def _tree(relative: str) -> ast.Module:
    return ast.parse(_source(relative))


def _module_functions(tree) -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


def _callee_name(call: ast.Call) -> str:
    node: ast.AST = call.func
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else ""


def _evidence_functions(tree: ast.Module, root: str) -> set[str]:
    """一枚读数的取证路径 = 它自己，加上它（递归）会走到的同模块函数。"""
    functions = _module_functions(tree)
    if root not in functions:
        return set()
    walked = {root}
    queue = [root]
    while queue:
        for call in ast.walk(functions[queue.pop()]):
            if isinstance(call, ast.Call):
                callee = _callee_name(call)
                if callee in functions and callee not in walked:
                    walked.add(callee)
                    queue.append(callee)
    return walked


def _string_constants_in(bodies) -> set[str]:
    found: set[str] = set()
    for body in bodies:
        for node in ast.walk(body):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.add(node.value)
            elif isinstance(node, ast.JoinedStr):
                found.add(ast.unparse(node))
    return found


def _tables_asked(tree: ast.Module, root: str) -> set[str]:
    """取证路径上向那枚共用探针点过名的表。"""
    functions = _module_functions(tree)
    asked: set[str] = set()
    for name in _evidence_functions(tree, root):
        for call in ast.walk(functions[name]):
            if isinstance(call, ast.Call) and _callee_name(call) == SHARED_PROBE:
                asked |= {
                    arg.value
                    for arg in call.args
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                }
    return asked


def _tables_probed(bodies) -> set[str]:
    found: set[str] = set()
    for text in _string_constants_in(bodies):
        found |= set(REGCLASS_TABLE.findall(text))
    return found


def _reads_readiness_flag(tree: ast.Module, root: str) -> bool:
    functions = _module_functions(tree)
    for name in _evidence_functions(tree, root):
        for node in ast.walk(functions[name]):
            if isinstance(node, ast.Name) and node.id == READINESS_FLAG:
                return True
            if isinstance(node, ast.Attribute) and node.attr == READINESS_FLAG:
                return True
            if (
                isinstance(node, ast.Call)
                and _callee_name(node) in {"getattr", "hasattr"}
                and any(
                    isinstance(arg, ast.Constant) and arg.value == READINESS_FLAG
                    for arg in node.args[1:2]
                )
            ):
                return True
    return False


def _stores_flag(node: ast.AST) -> bool:
    for inner in ast.walk(node):
        if isinstance(inner, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = inner.targets if isinstance(inner, ast.Assign) else [inner.target]
            if any(isinstance(t, ast.Name) and t.id == READINESS_FLAG for t in targets):
                return True
    return False


def _flag_owner() -> str:
    """全仓唯一在模块层写这枚旗标的文件——多一枚东家就是第二本账。"""
    owners = []
    for path in sorted((REPO / "app").rglob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        if any(_stores_flag(node) for node in _tree(relative).body):
            owners.append(relative)
    assert len(owners) == 1, f"「库就绪」旗标有 {len(owners)} 个东家：{owners}"
    return owners[0]


def _flag_warranted_tables() -> set[str]:
    """那枚旗标凭什么被翻真：写它的那些模块层语句（含它们调用的同模块函数）现查过哪些表。"""
    owner = _flag_owner()
    tree = _tree(owner)
    functions = _module_functions(tree)
    scopes = [node for node in tree.body if _stores_flag(node)]
    assert scopes, f"{owner} 里没人写 {READINESS_FLAG}"
    bodies = list(scopes)
    for scope in scopes:
        for call in ast.walk(scope):
            if isinstance(call, ast.Call) and _callee_name(call) in functions:
                bodies.append(functions[_callee_name(call)])
    return _tables_probed(bodies)


def _storage_modes(tree, root=None) -> set[str]:
    """`storage_mode` 那格能取到的字面值。给了 root 只算那枚读数的取证路径，不给就算全模块。"""
    if root is None:
        scopes = [tree]
    else:
        functions = _module_functions(tree)
        scopes = [functions[name] for name in _evidence_functions(tree, root)]
    modes: set[str] = set()
    for scope in scopes:
        for node in ast.walk(scope):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "storage_mode"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    modes.add(value.value)
    return modes


def _subsystem_rows() -> list[tuple[str, str, str]]:
    """`monitoring._STORAGE_SUBSYSTEMS` 逐行取自 AST：表里加一行，本件就自动多一行活。"""
    for node in _tree(MONITORING_REL).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_STORAGE_SUBSYSTEMS" for t in node.targets
        ):
            rows: list[tuple[str, str, str]] = []
            for element in node.value.elts:
                assert isinstance(element, ast.Tuple) and len(element.elts) == 3, (
                    "读数表的一行不再是 (子系统, 模块, 函数)：本件的覆盖面判法要一起重取"
                )
                values = tuple(literal.value for literal in element.elts)
                assert all(isinstance(value, str) for value in values), values
                rows.append(values)
            assert rows, "读数表是空的，判器没有可判的东西"
            return rows
    raise AssertionError("_STORAGE_SUBSYSTEMS 不在了：健康报拿什么逐腿问？")


def _protection_vocabulary() -> set[str]:
    """分档只认 monitoring 自己用过的字面值：它比对的、它交回的，两处一起算。"""
    tree = _tree(MONITORING_REL)
    words: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and "protection" in ast.unparse(node.left):
            words |= {
                operand.value
                for operand in node.comparators
                if isinstance(operand, ast.Constant) and isinstance(operand.value, str)
            }
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "protection":
                    # 值整棵子树都算：queue_storage_state 那一格是个三元式（"none" / "disabled"），
                    # 只认直裸的 Constant 会漏掉它，档位表就会假红成「长出了新档」。
                    for inner in ast.walk(value):
                        if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                            words.add(inner.value)
    assert words, "读不到 monitoring 的 protection 档位，判器不许降级成恒真"
    return words


ROWS = _subsystem_rows()

# ----------------------------------------------------------------------------- 一副世界（替身台账）
class _Ledger:
    """只对 `to_regclass('public.x')` 作答的替身台账，并把每一条语句记在账上。"""

    def __init__(self, tables=()):
        self.tables = set(tables)
        self.statements: list[str] = []
        self.connects = 0
        self.commits = 0
        self._row = None

    def factory(self):
        """顶替本腿那枚既有的 `_conn`：每一次开账都记一笔，好让「多问了没有」量得出来。"""
        self.connects += 1
        return self

    def refuse(self):
        """问不到那一格：这条腿连不上，谁也没回答「在」或「不在」。"""
        self.connects += 1
        raise RuntimeError("connection timeout expired")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        text = " ".join(str(statement).split())
        self.statements.append(text)
        found = REGCLASS_TABLE.search(text)
        table = found.group(1) if found else None
        self._row = {"table_name": table if table in self.tables else None}
        return self

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [self._row] if self._row is not None else []

    def commit(self):
        self.commits += 1

    def close(self):
        return None

    @property
    def ddl(self) -> list[str]:
        return [
            text
            for text in self.statements
            if text.upper().startswith(("CREATE", "ALTER", "DROP", "TRUNCATE"))
        ]

    @property
    def probes(self) -> list[str]:
        return [text for text in self.statements if "to_regclass" in text]


def _arm(monkeypatch, tables, *, environment="production", db_ready=True):
    """摆一副世界：环境、那枚就绪旗标。台账由被问的那条腿自己接。"""
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setattr(auth, "_db_ready", db_ready, raising=False)
    return _Ledger(tables)


def _arm_profile(monkeypatch, tables, *, broken=False, **kwargs):
    """顶替画像腿既有那枚 `_conn`。探针不许另开连接，桩位因此只能落在它自己那条上。"""
    ledger = _arm(monkeypatch, tables, **kwargs)
    monkeypatch.setattr(profile, "_conn", ledger.refuse if broken else ledger.factory)
    monkeypatch.setattr(profile, "_initialized", False)
    return ledger


def _arm_memory(monkeypatch, tables, *, broken=False, **kwargs):
    """同一件事的记忆腿。换掉 `psycopg` 是为了让「驱动在、表不在」这一格真的可达。"""
    ledger = _arm(monkeypatch, tables, **kwargs)
    monkeypatch.setattr(long_term, "psycopg", object(), raising=False)
    monkeypatch.setattr(long_term, "_conn", ledger.refuse if broken else ledger.factory)
    monkeypatch.setattr(long_term, "_initialized", False)
    return ledger


def _reader(name: str):
    for row in ROWS:
        if row[0] == name:
            return importlib.import_module(row[1]), row[2]
    raise AssertionError(f"读数表里没有 {name} 这一行：本件的靶面要一起重取")


def _readout(name: str) -> dict:
    module, function_name = _reader(name)
    return getattr(module, function_name)()


def _leg_arm(name: str):
    return _arm_profile if name == "user_profiles" else _arm_memory


# ------------------------------------------------------------------------------ 甲：覆盖面与形状
def test_the_health_table_and_the_runtime_agreement_are_the_same_rows():
    """AST 取的名单与健康报运行时真正逐腿问的名单必须一字不差——两路各取一次，谁漂了都红。"""
    runtime = [row[0] for row in monitoring._STORAGE_SUBSYSTEMS]
    ast_rows = [row[0] for row in ROWS]

    assert ast_rows == runtime, f"AST 读到 {ast_rows}，运行时读到 {runtime}：两本账对不上"
    assert len(set(runtime)) == len(runtime), f"读数表里有重名的一腿：{runtime}"


@pytest.mark.parametrize(("name", "module_path", "function_name"), ROWS)
def test_every_row_of_the_health_table_carries_a_real_readout(name, module_path, function_name):
    """表里每一行都得指着一枚真存在的读数——新增一行而没人配读数，当场红。"""
    reader = getattr(importlib.import_module(module_path), function_name, None)

    assert callable(reader), f"{name} 这一行指的读数不可调用：{module_path}.{function_name}"


@pytest.mark.parametrize(("name", "module_path", "function_name"), ROWS)
def test_no_readout_grows_a_key_or_a_slot_the_health_page_does_not_know(name, module_path, function_name):
    """键与档位一枚都不许多长：健康报那张 JSON 形状对客户是契约。"""
    ratified = set(monitoring._unavailable_state("simulated").keys())
    state = getattr(importlib.import_module(module_path), function_name)()

    assert isinstance(state, dict) and state, name
    assert ratified <= set(state), f"{name} 少了一格：{sorted(ratified - set(state))}"
    extra = set(state) - ratified
    assert extra <= {"reason"}, f"{name} 长出了新键：{sorted(extra)}"
    for cell in ("durable", "shared_across_processes"):
        assert isinstance(state[cell], bool), f"{name}.{cell}"
    assert state["protection"] in _protection_vocabulary(), (
        f"{name} 交回一枚 monitoring 不认的 protection 档位：{state['protection']}"
    )
    assert state["detail"], f"{name} 的 detail 空了"
    assert not (state["durable"] and state["storage_mode"] == "unavailable"), (
        f"{name} 一边说存不了、一边说 durable"
    )

# ------------------------------------------------------------ 乙 + 丙：postgres 声称要拿谁的背书
@pytest.mark.parametrize(("name", "module_path", "function_name"), ROWS)
def test_a_postgres_claim_is_warranted_by_a_probe_on_its_own_named_table(name, module_path, function_name):
    """只要一枚读数可能答 postgres，它就得拿与这一腿同名的那张表的现查背书；光靠旗标不算。

    「同名」不是本件起的规矩，是 `_STORAGE_SUBSYSTEMS` 那行自己写的：健康报逐腿问的那枚名字，就是这一腿
    声称要服务的表。全模块一句 postgres 都没声称的腿（json 那两张脸）判不着这条，直接放行——它没这张嘴。
    """
    tree = _tree(_module_relative(module_path))
    if "postgres" not in _storage_modes(tree):
        assert not _tables_asked(tree, function_name), (
            f"{name} 全模块一句 postgres 都没声称，读数却去现查了"
            f"{sorted(_tables_asked(tree, function_name))}：账对不上一次就得写清理由"
        )
        return

    asked = _tables_asked(tree, function_name)
    covered = _flag_warranted_tables() if _reads_readiness_flag(tree, function_name) else set()

    assert name in asked | covered, (
        f"{name} 声称 postgres/durable，取证路径上却没有任何一次针对 {name} 的现查："
        f"自己问了 {sorted(asked)}，那枚就绪旗标问过 {sorted(covered)}"
    )


def test_the_readiness_flag_is_itself_warranted_by_a_table_probe():
    """`user_storage_state` 为什么是对的：那枚旗标翻真之前，本身就现查过 `users`。

    这条不是给历史记功，是把「旗标凭什么算证据」钉住——下一班若把 `_create_schema` 里那次现查换成一句
    「连上了就行」，全仓靠它背书的 durable 声称会一起变假，这枚钉先红。
    """
    warrant = _flag_warranted_tables()

    assert warrant == {"users"}, f"那枚旗标的凭据不再是「users 这张表在位」：{sorted(warrant)}"


def test_a_flag_that_never_saw_the_table_still_refuses_the_durable_claim(monkeypatch):
    """行为侧的同一件事：库里没有 `users` 时那枚旗标翻不了真，读数也就没法声称 durable。"""
    ledger = _arm(monkeypatch, (), db_ready=False)
    monkeypatch.setattr(auth, "_last_ready_probe_at", None, raising=False)
    monkeypatch.setattr(auth, "_connect_for_request", lambda operation: ledger)

    assert auth._retry_readiness_probe() is False
    state = auth.user_storage_state()

    assert state["durable"] is False, "库都没问到表，用户腿却还报 durable"
    assert state["storage_mode"] == "unavailable"
    assert ledger.probes, "重探没去现查那张表：旗标的凭据换人了，本件要一起重取"


# ------------------------------------------------- 丁：表在 / 表不在 / 问不到，三张脸各就各位
@pytest.mark.parametrize("name", PG_LEGS)
def test_a_missing_table_is_never_reported_durable(name, monkeypatch):
    _leg_arm(name)(monkeypatch, ())

    state = _readout(name)

    assert state["durable"] is False, f"{name}：表不在位，健康报却把它记进 durable 名单"
    assert state["storage_mode"] == "unavailable", name
    assert state["protection"] == "read_only", f"{name}：这一格写入真落不下去，档位得说对"


@pytest.mark.parametrize("name", PG_LEGS)
def test_a_table_that_is_really_there_is_still_reported_durable(name, monkeypatch):
    """不许拿「永远悲观」冒充诚实：问得出那张表，就得敢说 durable——不然健康报在客户机上读废了。"""
    _leg_arm(name)(monkeypatch, (name,))

    state = _readout(name)
    cells = sorted(set(monitoring._unavailable_state("simulated")) - {"detail"})
    assert cells == [
        "durable", "protection", "shared_across_processes", "storage_mode",
    ], f"健康报那四格档位脸的形状变了：{cells}"
    claimed = {cell: state[cell] for cell in cells}
    assert claimed == {
        "durable": True,
        "protection": "none",
        "shared_across_processes": True,
        "storage_mode": "postgres",
    }, f"{name}：表真在位这一格，读数不敢说 durable 了？{state}"


@pytest.mark.parametrize("name", PG_LEGS)
def test_a_question_nobody_answered_is_not_reported_as_absence(name, monkeypatch):
    """连不上 ≠ 表不在：两格都不配声称 durable，但两句排查路必须分得开。"""
    _leg_arm(name)(monkeypatch, (), broken=True)

    state = _readout(name)

    assert state["durable"] is False, name
    assert name in state["detail"], f"{name}：detail 没点名那张表：{state['detail']}"
    assert "migration" not in state["detail"].lower(), (
        f"{name}：问不到不等于缺迁移，两条排查路不许并成一句：{state['detail']}"
    )


# ------------------------------------------------------------------- 戊：与写路径同一副世界
def test_the_health_page_and_the_profile_write_now_tell_one_story(monkeypatch):
    """一副台账同时喂读路与写路：缺 `user_profiles` 这一格上，两张嘴从今天起说同一句话。"""
    ledger = _arm_profile(monkeypatch, ())

    assert profile.profile_storage_state()["durable"] is False
    with pytest.raises(profile.ProfileStoreUnavailable):
        profile.upsert_profile("r392-user", position="boss")
    assert profile._MEM_PROFILES == {}, "生产缺表那一格不许把画像折进进程内字典（R383 同一条裁定）"
    assert ledger.probes, "两张嘴都该问到那一次现查"


def test_the_health_page_and_a_memory_write_now_tell_one_story(monkeypatch, offline_ollama_embeddings):
    """同一件事的 memory 腿：健康报不 durable，`remember()` 也确实一条都没存下。"""
    ledger = _arm_memory(monkeypatch, ())

    assert long_term.memory_storage_state()["durable"] is False
    assert long_term.remember("r392-user", "prefers bar charts") is False
    assert long_term._MEMORY == {}, "生产缺表那一格不许把长期记忆折进进程内字典"
    assert ledger.probes


# --------------------------------------------------------------------------- 己：探针的边界
@pytest.mark.parametrize("name", PG_LEGS)
def test_the_warrant_asks_one_read_only_question(name, monkeypatch):
    ledger = _leg_arm(name)(monkeypatch, (name,))

    assert _readout(name)["durable"] is True

    probes = ledger.probes
    assert len(probes) == 1, f"{name}：一次读数问了 {len(probes)} 句，本该只问一句"
    assert probes[0].startswith("SELECT to_regclass"), probes[0]
    assert ledger.ddl == [], f"{name}：健康报动了 DDL：{ledger.ddl}"
    assert ledger.commits == 0, f"{name}：一次只读读数不该 commit"


@pytest.mark.parametrize("name", PG_LEGS)
def test_non_production_never_borrows_a_connection_to_answer(name, monkeypatch):
    """本单一枚都没改开发/裸机/离线那三张脸：判法是「那一支一发连接都不许多开」。"""
    ledger = _leg_arm(name)(monkeypatch, (name,), environment="development")

    _readout(name)

    assert ledger.connects == 0, f"{name}：非生产这一支去问库了，本单没那个授权"


def test_the_readout_and_the_write_gate_ask_about_the_same_table():
    """两本账不许分叉：读路问的表，必须就是写路那道闸问的同一张。"""
    for name in PG_LEGS:
        module_tree = _tree(_module_relative(_reader(name)[0].__name__))
        module_functions = _module_functions(module_tree)
        readout_name = _reader(name)[1]
        assert "_ensure" in module_functions, f"{name}：写路那道闸不在了，本钉要一起重取"
        gate_tables = _tables_probed(
            [module_functions[gate] for gate in _evidence_functions(module_tree, "_ensure")]
        )
        asked = _tables_asked(module_tree, readout_name)

        assert gate_tables == {name}, f"{name}：写路闸问的是 {sorted(gate_tables)}"
        assert asked == gate_tables, f"{name}：读路问 {sorted(asked)}，写路问 {sorted(gate_tables)}"

# --------------------------------------------------------------------- 庚：detail 说人话
@pytest.mark.parametrize("verdict", ("absent", "unknown"))
@pytest.mark.parametrize("name", PG_LEGS)
def test_the_unwarranted_detail_is_an_operators_sentence(name, verdict, monkeypatch):
    """那两句是给运维读的：点名那张表、给出排查路；后端状态名与驱动原话不许占这个位置。"""
    _leg_arm(name)(monkeypatch, (), broken=(verdict == "unknown"))

    detail = _readout(name)["detail"]

    assert name in detail, f"{name}：detail 没点名那张表：{detail}"
    assert detail not in {
        "postgres", "memory", "unavailable", "json", "redis",
        "none", "read_only", "refuse_start", "disabled", "storage_unavailable",
    }, f"{name}：detail 交出来的是一枚档位名：{detail}"
    assert not re.search(r"\b[A-Za-z][A-Za-z]*Error\b", detail), (
        f"{name}：detail 里混进了后端异常名：{detail}"
    )
    assert "psycopg" not in detail.lower(), f"{name}：detail 把驱动名当人话交出去了：{detail}"
    if verdict == "absent":
        assert "migration" in detail.lower(), f"{name}：缺表这句得指到迁移：{detail}"


# ----------------------------------------------------------------- 辛：判器自己要有牙
def test_the_warrant_ruler_is_not_a_no_op():
    """喂一副「声称 postgres 而什么都没查」的假形状给判器，它必须当场判不合格。

    这一枚是本件自己的反证：哪天 `test_a_postgres_claim_is_warranted_by_a_probe_on_its_own_named_table`
    变成谁都过得了的宽判，这里先红。
    """
    source = (
        "def _database_available():\n"
        "    return getattr(auth_module, '_db_ready', False)\n"
        "\n"
        "\n"
        "def lying_storage_state():\n"
        "    if _database_available():\n"
        "        return {\"storage_mode\": \"postgres\", \"durable\": True}\n"
        "    return {\"storage_mode\": \"memory\", \"durable\": False}\n"
    )
    tree = ast.parse(source)

    assert "postgres" in _storage_modes(tree, "lying_storage_state")
    assert _reads_readiness_flag(tree, "lying_storage_state"), "判器连旗标都读不到，那就是枚空钉"
    assert _tables_asked(tree, "lying_storage_state") == set()
    assert "user_profiles" not in (
        _tables_asked(tree, "lying_storage_state") | _flag_warranted_tables()
    ), "拿 users 的现查给 user_profiles 背书——本班的病灶，判器量不到就是空钉"