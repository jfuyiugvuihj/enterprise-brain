"""R238 判据④：边界之外裸 ``psycopg.connect`` 的枚数棘轮。

一句话：本单只造边界，一枚调用点都不迁，所以"别人不能再随手加一枚"必须由机械钉住。
起点读数 = **15 枚**（``app/**`` 14 枚 + ``scripts/**`` 1 枚），逐枚的**身份**落在下面
``BASELINE`` 里；只准降不准升。

为什么是 15 而不是派工单里的 11：派工单那张表漏了 ``app/api/v1/`` 整棵
（chat.py:853 / alerts.py:45 / feedback.py:70），并且把三枚路径记错了目录
（真值是 app/memory/profile.py、app/semantics/registry.py、app/storage/pending_approvals.py）。
本单交回时按实测记账，同一个数字在主干上另有出处：app/common/auth.py:364 那句
"实测 app/** 里 auth.py 之外还有 14 处 psycopg.connect" 与这里的 app 侧 14 枚**互相
对上**（14 = 本表 app 侧 14 枚，auth.py 自己那枚另算，边界 connection.py:52 也另算）。

R261（2026-09-26）：账记的是"谁"，不是"第几行"。R254 往 ``app/api/v1/chat.py`` 上方落了
481 行，同一处裸 connect 从 ``chat.py:853`` 漂到 ``chat.py:854``，旧口径把它读成"已迁走
一枚 + 新长一枚"——没有任何东西被迁走，也没有任何新调用点诞生，总控只能改账（c70548a）
把它按下去。只要有人在被记账的文件上方加一行，全量门就红一次；本仓 5218 枚用例、一天
9 枚起并树，这枚钉每次误伤都是真金白银的墙钟与判断力。所以身份换成
``路径::所属作用域#该作用域内第几枚``（非 ``call`` 那两种形状再加 ``:kind``），行号退出
账本、只留在报错里给人带路。三条不变量各有钉子：往上插行不算迁走（判据①，
``test_inserting_lines_above_every_recorded_site_keeps_the_ledger_green`` 与
``test_the_r254_incident_replays_green_under_the_new_ledger_and_red_under_the_old``），
凭空多写那一枚照样红且被点到 ``path:line``（判据②），真迁走而不删账照样红（判据③）。
代价写清楚，别指望它偷偷过关：函数**改名**会挪身份（那是明账，改一行就绿）；同一作用域
内多枚靠 ``#N`` 区分，删掉前一枚会让后一枚补位——那本来就该重记一次账。

扫过哪些形状（AST，不是文本匹配）：
1. ``psycopg.connect(...)`` / ``psycopg2.connect(...)`` —— 属性调用，含 ``**kwargs`` 写法；
2. ``import psycopg as pg`` 之后的 ``pg.connect(...)`` —— 起别名一样抓；
3. ``from psycopg import connect`` + ``connect(...)``、以及 ``import connect as dial``
   + ``dial(...)`` —— 从驱动里把符号搬出来再裸调，抓；
4. ``from psycopg import connect`` 这枚**绑定本身** —— 只要出现在边界之外就单独红，
   哪怕还没调用（见 ``test_importing_the_connect_symbol_is_alone_a_violation``）；
5. ``connection_factory=lambda: psycopg.connect(url)`` —— 注入缝里塞裸连，抓第 5 条里的
   connect 调用（``connection_factory=`` 本身是合法既有缝，app/** 已有 pg_store /
   indexing 用它，不许一刀禁）；
6. ``functools.partial(psycopg.connect, url)`` 这类**只引用不调用**的写法 —— 抓，
   因为绕过正是靠"先递出去、回头再调"；
7. 异步驱动 ``AsyncConnection.connect`` / ``ClientConnection`` 与 ``psycopg2`` 之外
   的其它入口 —— 2026-09-25 @ecc9c54 实测 app/** 与 scripts/** **零命中**，所以本表
   没有它们；哪天冒出来，第 1/2/3 条的形状照样能抓住属性调用形态。

为什么必须用 AST 而不是 grep（实测读数）：
- ``app/common/auth.py:364`` 的 docstring 里就写着 "``psycopg.connect``" 四个字符，
  grep 会把它当成第 16 枚，本表不会（AST 里那是一枚字符串常量）；
- 本文件自己就写着二十来处 ``psycopg.connect`` 的字面量，grep 会立刻把自己算进去；
  ``test_this_file_is_invisible_to_itself`` 钉的就是这条。

不在范围内，且是有意的：
- ``tests/**`` 8 枚（``test_postgres_backup_recovery.py`` /  ``test_postgres_execution_
  persistence.py``）：那是真库集成件，按 R20 的口径只能直连，算进来就等于逼测试撒谎；
- ``app/db/connection.py:52`` 自己：它就是被供出来的那一枚边界；
- ``psycopg_pool.ConnectionPool`` （app/agents/orchestrator.py:174）：加不加池归总控定，
  本钉只管裸 connect。
"""
import ast
import re
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = "app/db/connection.py"
SCANNED_ROOTS = ("app", "scripts")
DRIVER_ROOTS = frozenset({"psycopg", "psycopg2", "psycopg_binary"})
IMPORT_CONNECT = "import-connect"
KIND_CALL = "call"
KIND_REFERENCE = "reference"
MODULE_SCOPE = "<module>"

#: 身份 = ``路径::所属作用域#该作用域内第几枚``（``call`` 之外的形状再加 ``:kind``）。
#: 行号不参与记账（R261）；行号只出现在报错里，由 ``_located()`` 现场翻译，保证人还能
#: 一跳跳过去。迁移掉一枚就把对应那行删掉（判据③：只准降不准升）。行尾的 ``#`` 注记是
#: "这枚长什么样"，它不是判据的一部分：改参数不必修订它，真迁走一枚时连同这一行一起删。
#: ``test_every_ledger_entry_carries_a_human_readable_note`` 钉的就是"十五行账不许退化
#: 成十五枚不透明身份"。
BASELINE = (
    "app/agents/orchestrator.py::_make_checkpointer#0",  # psycopg.connect(_PG_URL, connect_timeout=2).close()
    "app/api/v1/alerts.py::_conn#0",  # return psycopg.connect(_PG_URL, row_factory=dict_row)
    "app/api/v1/chat.py::_sess_conn#0",  # return psycopg.connect(_PG_URL, row_factory=dict_row)
    "app/api/v1/feedback.py::_connect#0",  # return psycopg.connect(pg_store.resolve_database_url(), connect_timeout=2)
    "app/common/auth.py::_raw_conn#0",  # return psycopg.connect(_PG_URL, row_factory=dict_row, **_connect_kwargs())
    "app/common/monitoring.py::_probe_postgres#0",  # with psycopg.connect(database_url, connect_timeout=1) as conn: ...
    "app/documents/catalog.py::_conn#0",  # conn = psycopg.connect(_PG_URL, row_factory=dict_row, connect_timeout=1)
    "app/memory/long_term.py::_conn#0",  # return psycopg.connect(_PG_URL, row_factory=dict_row)
    "app/memory/profile.py::_conn#0",  # return psycopg.connect(_PG_URL, row_factory=dict_row)
    "app/rag/indexing.py::PostgresIndexStore._connect#0",  # return psycopg.connect(url, row_factory=dict_row, connect_timeout=2)
    "app/rag/retriever.py::_read_activity_signal_rows#0",  # with psycopg.connect(url) as connection: ...
    "app/semantics/registry.py::_conn#0",  # connection = psycopg.connect(_PG_URL, row_factory=dict_row, ...)
    "app/storage/pending_approvals.py::_conn#0",  # return psycopg.connect(_PG_URL, row_factory=dict_row)
    "app/storage/persistence.py::build_persistence_adapter#0",  # PostgresPersistenceAdapter(lambda: psycopg.connect(url, connect_timeout=2))
    "scripts/audit_vector_mirror_sets.py::PsycopgReader._ensure#0",  # self._connection = psycopg.connect(self._dsn, autocommit=False, ...)
)

#: 2026-09-26 @c70548a 的实测读数。这是 R238…R254b 那段历史的**账，不是判据**：没有任何
#: 钉拿它比生产代码，它只被 R254 事故重放那一枚用例引用，用来说明旧口径为什么必然把
#: "往上加行"读成"迁走一枚 + 新长一枚"。
LEGACY_LINE_LEDGER = (
    "app/agents/orchestrator.py:167",
    "app/api/v1/alerts.py:45",
    "app/api/v1/chat.py:854",
    "app/api/v1/feedback.py:70",
    "app/common/auth.py:301",
    "app/common/monitoring.py:381",
    "app/documents/catalog.py:334",
    "app/memory/long_term.py:55",
    "app/memory/profile.py:36",
    "app/rag/indexing.py:1503",
    # 575 而不是 567：R59 块1（Anscombe，随本笔并树）在这一行上方加了 8 行；
    # 尺子按物理行号记账，随之改口——与 persistence.py 那笔（662，见 dde3c1f）同源
    "app/rag/retriever.py:575",
    "app/semantics/registry.py:514",
    "app/storage/pending_approvals.py:105",
    # 662 而不是 596：R272（951909b）在这一行上方加了 66 行；尺子按物理行号记账，随之改口
    "app/storage/persistence.py:662",
    "scripts/audit_vector_mirror_sets.py:428",
)

class Hit(NamedTuple):
    """一枚落点。记账用 ``identity``，报位置用 ``line``，两件事从此分开。"""

    rel: str
    scope: str
    ordinal: int
    kind: str
    line: int
    snippet: str

    @property
    def location(self) -> str:
        return f"{self.rel}:{self.line}"

    @property
    def identity(self) -> str:
        return ledger_identity(self.rel, self.scope, self.ordinal, self.kind, self.line)


def ledger_identity(rel, scope, ordinal, kind, line):
    """记账口径的唯一入口。反证刀 A 摘的就是下面这一行公式。"""
    tag = "" if kind == KIND_CALL else f":{kind}"
    return f"{rel}::{scope}{tag}#{ordinal}"


def path_only_identity(rel, scope, ordinal, kind, line):
    """退化口径一（判据⑥演的就是它）：只认路径，同一文件的两枚落点并成一枚。"""
    return rel


def unnumbered_identity(rel, scope, ordinal, kind, line):
    """退化口径二：认到作用域但丢掉 ``#N``。反证刀 B 摘的就是下面这一行。"""
    tag = "" if kind == KIND_CALL else f":{kind}"
    return f"{rel}::{scope}{tag}"


def line_number_identity(rel, scope, ordinal, kind, line):
    """R238…R254b 的旧口径：把行号写进身份。开头那段事故就是它造的。"""
    return f"{rel}:{line}"


def _bindings(tree):
    """把"哪个本地名字其实指向 psycopg 的 connect"算出来。"""
    module_alias = {}
    connect_alias = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in DRIVER_ROOTS:
                    module_alias[alias.asname or root] = root
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in DRIVER_ROOTS:
                for alias in node.names:
                    if alias.name == "connect":
                        connect_alias.add(alias.asname or alias.name)
    return module_alias, connect_alias


def _is_handle_to(node, module_alias):
    """这枚表达式是不是"驱动模块本身"（``psycopg`` / ``import psycopg as pg`` 的 pg）。"""
    return isinstance(node, ast.Name) and (node.id in module_alias or node.id in DRIVER_ROOTS)


def _parent_map(tree):
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def _scope_of(node, parents):
    """这枚落点落在哪个作用域里：从它往上数 def/class 的名字，拼成限定名。

    lambda 不进链（它没有名字，进链只会让账更难读）；同作用域内多枚靠 ``#N`` 分开。
    """
    chain = []
    current = parents.get(id(node))
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            chain.append(current.name)
        current = parents.get(id(current))
    return ".".join(reversed(chain)) or MODULE_SCOPE


def _enclosing_stmt(node, parents):
    current = node
    while current is not None and not isinstance(current, ast.stmt):
        current = parents.get(id(current))
    return current


def scan_source(rel: str, source: str):
    """扫一份源码，交回按行号排好的 ``[Hit]``。

    kind 三枚：``call``（真在建连）、``reference``（把 ``psycopg.connect`` 当值递出去，
    绕过就长这样）、``from- psycopg import connect``（符号被搬出驱动本身）。
    ``ordinal`` 是"同一作用域内同类形状的第几枚"，从 0 起，按行号先后编号。
    """
    return list(_cached_scan(rel, source))


@lru_cache(maxsize=None)
def _cached_scan(rel: str, source: str):
    """同一份 (路径, 源码) 只解析一次：这枚棘轮一轮要扫全树十几遍。

    缓存的是一枚纯函数的结果——同一份源码必然扫出同一批落点，判据一条没松。前提是本仓
    纪律：测试会话里没人改写 ``app/**`` 与 ``scripts/**``（R253 起变异只落影子副本；
    2026-09-26 @c70548a 实测 git grep 零命中），所以没有"读到陈旧账"这条路。
    """
    tree = ast.parse(source)
    module_alias, connect_alias = _bindings(tree)
    parents = _parent_map(tree)

    found = []

    def note(node, kind):
        stmt = _enclosing_stmt(node, parents)
        snippet = " ".join(ast.get_source_segment(source, stmt).split()) if stmt is not None else "?"
        found.append((node.lineno, node.col_offset, kind, _scope_of(node, parents), snippet))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in DRIVER_ROOTS:
            for alias in node.names:
                if alias.name == "connect":
                    note(node, IMPORT_CONNECT)

    called_lines = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "connect" and _is_handle_to(func.value, module_alias):
            note(node, KIND_CALL)
            called_lines.add(node.lineno)
        elif isinstance(func, ast.Name) and func.id in connect_alias:
            note(node, KIND_CALL)
            called_lines.add(node.lineno)

    for node in ast.walk(tree):
        # 只引用不调用（functools.partial、赋值给变量、当参数递出去）也算站点。
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "connect"
            and node.lineno not in called_lines
            and _is_handle_to(node.value, module_alias)
        ):
            note(node, KIND_REFERENCE)

    counters = {}
    hits = []
    for line, _column, kind, scope, snippet in sorted(found):
        key = (scope, kind)
        ordinal = counters.get(key, 0)
        counters[key] = ordinal + 1
        hits.append(Hit(rel, scope, ordinal, kind, line, snippet))
    return tuple(sorted(hits, key=lambda hit: (hit.line, hit.kind, hit.ordinal)))


def repo_sources():
    sources = {}
    for root in SCANNED_ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            sources[rel] = path.read_text(encoding="utf-8")
    return sources


def scan_sources(sources):
    """交回 (边界之外, 边界之内) 两组落点。语法扫不动的文件一律当事故。"""
    sites, unparsed = [], []
    for rel, source in sources.items():
        try:
            sites.extend(scan_source(rel, source))
        except SyntaxError as exc:
            unparsed.append(f"{rel}: {exc}")
    assert unparsed == [], f"扫不动的文件不许被当成零命中：{unparsed}"
    return (
        [hit for hit in sites if hit.rel != BOUNDARY],
        [hit for hit in sites if hit.rel == BOUNDARY],
    )


def booked(sources, identity=ledger_identity):
    """边界之外的落点按给定口径归堆：身份 -> 当前那一枚 Hit。"""
    outside, _boundary = scan_sources(sources)
    result = {}
    for hit in outside:
        result.setdefault(identity(hit.rel, hit.scope, hit.ordinal, hit.kind, hit.line), hit)
    return result


def readings(sources, identity=ledger_identity):
    """这轮扫描在账上的读数（身份集合），行号不在里面。"""
    return set(booked(sources, identity))


def _located(identities, sites):
    """把身份翻译回"现在在第几行"——判据②要求报错原文里人能一跳跳过去。"""
    if not identities:
        return "（无）"
    parts = []
    for identity in identities:
        site = sites.get(identity)
        parts.append(identity if site is None else f"{identity} → {site.location}")
    return ", ".join(parts)

# ---------------------------------------------------------------- 棘轮本体（三枚钉的判断逻辑）
def _check_count_never_rises(sources, baseline=BASELINE, identity=ledger_identity):
    sites = booked(sources, identity)
    assert len(sites) <= len(baseline), (
        f"边界之外裸 connect 从 {len(baseline)} 枚涨到 {len(sites)} 枚；"
        f"多出来的是 {_located(sorted(set(sites) - set(baseline)), sites)}"
    )
    return sites


def _check_no_unrecorded_site(sources, baseline=BASELINE, identity=ledger_identity):
    sites = booked(sources, identity)
    unrecorded = sorted(set(sites) - set(baseline))
    assert not unrecorded, (
        "新增裸 psycopg.connect：" + _located(unrecorded, sites)
        + " —— 请改走 app/db/connection.py 的边界，或向总控申请入册"
    )
    return sites


def _check_ledger_is_current(sources, baseline=BASELINE, identity=ledger_identity):
    sites = booked(sources, identity)
    unrecorded = sorted(set(sites) - set(baseline))
    stale = sorted(set(baseline) - set(sites))
    assert not (unrecorded or stale), (
        f"已迁走（该从清单里删掉）：{_located(stale, sites)}；"
        f"新长出来（不许）：{_located(unrecorded, sites)}"
    )
    return sites


def test_the_bare_connect_count_never_rises():
    """判据④主钉：边界之外的枚数只准降、不准升。"""
    _check_count_never_rises(repo_sources())


def test_no_unrecorded_site_is_allowed():
    """每一枚都必须能在起点清单里找到；新长出来的那一枚当场红，且被点名。"""
    _check_no_unrecorded_site(repo_sources())


def test_the_recorded_reading_is_current():
    """清单本身也不许过期：迁移掉一枚，就把那一行从 BASELINE 删掉。

    这一枚不是罚你迁移，是罚你迁移完不记账。删一行就绿。
    """
    _check_ledger_is_current(repo_sources())


def test_the_boundary_itself_opens_exactly_one_connection():
    """边界之内只许有一枚真建连，外加策略入口那一枚"引用"。

    为什么引用在边界里合法：``connect_with_policy`` 得把驱动函数接到注入缝上
    （``connect = psycopg.connect``），而"允许碰驱动"这件事本来就只属于这一棵文件。
    边界之外，引用和调用一样算越界。
    """
    _outside, boundary = scan_sources(repo_sources())
    calls = [hit for hit in boundary if hit.kind == KIND_CALL]
    references = [hit for hit in boundary if hit.kind == KIND_REFERENCE]
    lines = REPO_ROOT.joinpath(BOUNDARY).read_text(encoding="utf-8").splitlines()

    assert len(calls) == 1, boundary
    assert "settings.url" in lines[calls[0].line - 1], lines[calls[0].line - 1]
    assert len(references) <= 1, boundary


def test_a_migrated_site_is_a_decrease_not_a_failure():
    """反证（④的方向性）：把 15 枚里的 3 枚迁走，两枚硬钉必须照样绿。

    只有"清单未同步"那一枚会红，而它红的意思是"删三行"，不是"改回去"。
    """
    victims = ("app/api/v1/alerts.py", "app/memory/profile.py", "scripts/audit_vector_mirror_sets.py")
    migrated = {entry for entry in BASELINE if entry.partition("::")[0] not in victims}

    assert len(migrated) == len(BASELINE) - 3, sorted(migrated)
    assert migrated <= set(BASELINE)
    assert len(migrated) <= len(BASELINE)
    assert migrated - set(BASELINE) == set()


# ------------------------------------------- 判据①：往上加行不是迁移，也不许长得像迁移
NOISE_SHAPE = "# r261 噪声 {marker} 第 {index} 行：注释里写 psycopg.connect(url) 也不算落点"


def _insert_before(source: str, at_line: int, text: str) -> str:
    """在 ``at_line`` 这一行之前塞进 ``text``（返回新串，不碰磁盘）。"""
    lines = source.splitlines(keepends=True)
    assert 1 <= at_line <= len(lines) + 1, at_line
    return "".join(lines[: at_line - 1]) + text + "".join(lines[at_line - 1:])


def _pad_above(source: str, at_line: int, count: int, marker: str) -> str:
    """在第 ``at_line`` 行之前塞 ``count`` 行注释噪声（只在内存里，不落盘）。

    被记账那枚有可能正卡在多行调用的括号中间（``app/storage/persistence.py`` 就是），
    插语句会当场把语法弄坏；纯注释行哪儿都能插，而行号照样被顶下去——旧口径正是死在
    "行号变了"这一件事上，跟插的是不是代码无关。噪声里故意写着 ``psycopg.connect(url)``：
    哪天扫描器退化成正则匹配，这里立刻红。
    """
    text = "".join(NOISE_SHAPE.format(marker=marker, index=index) + "\n" for index in range(count))
    return _insert_before(source, at_line, text)


def _function_above(source: str, at_line: int, count: int, marker: str) -> str:
    """在第 ``at_line`` 行之前插一枚真函数（顶层语句），其余行数用注释凑够。"""
    body = ["def r261_noise():", "    return None", ""]
    head = [NOISE_SHAPE.format(marker=marker, index=index) for index in range(count - len(body))]
    text = "".join(line + "\n" for line in head + body)
    return _insert_before(source, at_line, text)


def _statement_start(node) -> int:
    """语句真正的起始行：带装饰器的，从第一枚装饰器算起。"""
    line = node.lineno
    for decorator in getattr(node, "decorator_list", []):
        line = min(line, decorator.lineno)
    return line


def _scope_anchor(source: str, scope: str):
    """这枚作用域所属的**顶层** ``def``/``class`` 在第几行；``<module>`` 就是第 1 行。

    取最外那一枚而不是最近那一枚：噪声函数只能插在顶层语句之前，插进 class body 或
    函数体里会把被记账那枚变成它的嵌套作用域——那才是真的动了身份。
    """
    if scope == MODULE_SCOPE:
        return 1
    node = ast.parse(source)
    anchor = None
    for name in scope.split("."):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and child.name == name:
                if anchor is None:
                    anchor = _statement_start(child)
                node = child
                break
        else:
            return None
    return anchor


def _all_three_green(sources, baseline=BASELINE):
    _check_count_never_rises(sources, baseline=baseline)
    _check_no_unrecorded_site(sources, baseline=baseline)
    _check_ledger_is_current(sources, baseline=baseline)


def test_inserting_lines_above_every_recorded_site_keeps_the_ledger_green():
    """判据①主钉：15 枚落点各自正上方插 40 行，三枚钉全绿，身份一字未动。

    插完之后行号确实全变了——这既是"钉还在跟踪位置"的证据，也是"没干脆不比了"的反证：
    要是这枚棘轮改成不比了，它既不会绿得这么干净，也不会知道自己搬去了哪一行。
    """
    sources = repo_sources()
    sites = booked(sources)
    crowded = dict(sources)
    # 从最底下那枚开始插，先前插进去的都排在它下面，行号不会互相踩。
    for hit in sorted(sites.values(), key=lambda item: item.line, reverse=True):
        crowded[hit.rel] = _pad_above(crowded[hit.rel], hit.line, 40, hit.rel)

    moved = booked(crowded)
    assert set(moved) == set(sites) == set(BASELINE), (
        f"插行不该动身份：凭空迁走 {sorted(set(sites) - set(moved))}；"
        f"凭空长出 {sorted(set(moved) - set(sites))}"
    )
    for identity, hit in moved.items():
        above = sum(1 for other in sites.values() if other.rel == hit.rel and other.line <= hit.line)
        assert hit.line == sites[identity].line + 40 * above, (identity, hit, sites[identity])
    _all_three_green(crowded)


def test_inserting_a_whole_function_before_a_recorded_function_is_not_a_migration():
    """判据①的第二种形状：在它所属函数**之前**整段插一枚新函数（顶层语句）。"""
    sources = repo_sources()
    sites = booked(sources)
    anchors = set()
    for hit in sites.values():
        start = _scope_anchor(sources[hit.rel], hit.scope)
        assert start is not None and start <= hit.line, hit.identity
        anchors.add((hit.rel, start))

    crowded = dict(sources)
    for rel, start in sorted(anchors, key=lambda pair: pair[1], reverse=True):
        crowded[rel] = _function_above(crowded[rel], start, 12, f"{rel}@{start}")

    moved = booked(crowded)
    assert set(moved) == set(BASELINE), (
        f"整段函数插进文件，一处身份都不该动："
        f"凭空迁走 {sorted(set(sites) - set(moved))}；凭空长出 {sorted(set(moved) - set(sites))}"
    )
    _all_three_green(crowded)


def test_the_r254_incident_replays_green_under_the_new_ledger_and_red_under_the_old():
    """把 09-26 那次假红原地重放：chat.py 那枚落点上方进 481 行。

    新账：三枚钉全绿，而且知道自己从第几行搬到了第几行。
    旧账（行号进身份）：同一枚落点被读成"已迁走一枚 + 新长一枚"。
    """
    sources = repo_sources()
    rel = "app/api/v1/chat.py"
    sites = booked(sources)
    victims = [hit for hit in sites.values() if hit.rel == rel]
    assert len(victims) == 1, victims
    victim = victims[0]

    crowded = dict(sources, **{rel: _pad_above(sources[rel], victim.line, 481, rel)})
    _all_three_green(crowded)
    after = booked(crowded)[victim.identity]
    assert after.line == victim.line + 481, (victim, after)

    assert readings(sources, identity=line_number_identity) == set(LEGACY_LINE_LEDGER)
    old_after = readings(crowded, identity=line_number_identity)
    assert old_after != set(LEGACY_LINE_LEDGER)
    assert sorted(set(LEGACY_LINE_LEDGER) - old_after) == [f"{rel}:{victim.line}"]
    assert sorted(old_after - set(LEGACY_LINE_LEDGER)) == [f"{rel}:{victim.line + 481}"]

# ------------------------------------------------- 判据②：凭空多写一枚，红，且点名到行
EXTRA_SITE = "import psycopg\n\n\ndef r261_extra_site(url):\n    return psycopg.connect(url)\n"


def _with_extra_site(sources, rel, text=EXTRA_SITE):
    """在一份源码末尾凭空多写一枚边界之外的裸 connect（只在内存里）。

    交回 (改过的源码表, 那枚新落点应当在第几行)——报错必须点名到这个行号。
    """
    original = sources[rel]
    joined = original if original.endswith("\n") else original + "\n"
    base = len(joined.splitlines())
    body = text.splitlines()
    marked = [index for index, line in enumerate(body, start=1) if "psycopg.connect(" in line]
    assert len(marked) == 1, text
    return dict(sources, **{rel: joined + text}), base + marked[0]


def test_a_new_site_in_an_otherwise_quiet_file_is_named_with_its_line():
    """判据②：边界之外多写一枚 ⇒ 红，报错原文里带着能一跳跳过去的 ``path:line``。"""
    sources = repo_sources()
    rel = "app/semantics/registry.py"
    crowded, extra_line = _with_extra_site(sources, rel)

    with pytest.raises(AssertionError) as excinfo:
        _check_no_unrecorded_site(crowded)
    message = str(excinfo.value)
    assert "新增裸 psycopg.connect：" in message, message
    assert f"{rel}:{extra_line}" in message, message
    assert f"{rel}::r261_extra_site#0" in message, message
    with pytest.raises(AssertionError):
        _check_count_never_rises(crowded)
    with pytest.raises(AssertionError):
        _check_ledger_is_current(crowded)


def test_a_new_site_in_an_already_recorded_file_is_still_caught():
    """已记账那棵文件里再长一枚：路径没变，也必须红，并把新行号一起报出来。"""
    sources = repo_sources()
    rel = "app/storage/pending_approvals.py"
    assert rel in {hit.rel for hit in booked(sources).values()}
    crowded, extra_line = _with_extra_site(sources, rel)

    with pytest.raises(AssertionError) as excinfo:
        _check_no_unrecorded_site(crowded)
    assert f"{rel}:{extra_line}" in str(excinfo.value), str(excinfo.value)
    assert len(readings(crowded)) == len(BASELINE) + 1


# -------------------------------------------------- 判据③：真迁走而不删账，红不许松
def _migrate(source: str, line: int) -> str:
    """把第 ``line`` 行那枚裸 connect 换成边界内的取连接函数（只动那一行）。"""
    lines = source.splitlines(keepends=True)
    text = lines[line - 1]
    for token in ("psycopg.connect(", "psycopg2.connect(", "connect("):
        if token in text:
            lines[line - 1] = text.replace(token, "get_connection(", 1)
            return "".join(lines)
    raise AssertionError(f"第 {line} 行没有可迁走的裸 connect：{text!r}")


@pytest.mark.parametrize(
    "victim_rel",
    ["app/api/v1/feedback.py", "app/memory/profile.py", "scripts/audit_vector_mirror_sets.py"],
)
def test_migrating_a_site_without_unbooking_it_is_still_red(victim_rel):
    """判据③：真把某一枚迁进边界内而不删账 ⇒ 仍红（换了身份口径这条不许松）。"""
    sources = repo_sources()
    sites = booked(sources)
    victims = [hit for hit in sites.values() if hit.rel == victim_rel and hit.kind == KIND_CALL]
    assert len(victims) == 1, victims
    victim = victims[0]
    crowded = dict(sources, **{victim_rel: _migrate(sources[victim_rel], victim.line)})

    assert readings(crowded) == set(BASELINE) - {victim.identity}
    _check_count_never_rises(crowded)
    _check_no_unrecorded_site(crowded)
    with pytest.raises(AssertionError) as excinfo:
        _check_ledger_is_current(crowded)
    message = str(excinfo.value)
    assert "已迁走（该从清单里删掉）：" in message, message
    assert victim.identity in message, message
    assert "新长出来（不许）：（无）" in message, message


def test_unbooking_migrated_sites_turns_everything_green():
    """迁走 + 删账 = 绿：这是"删一行就绿"那条承诺没被换皮削弱的证据。"""
    sources = repo_sources()
    sites = booked(sources)
    victims = sorted(sites.values(), key=lambda hit: hit.identity)[:3]
    crowded = dict(sources)
    for hit in victims:
        crowded[hit.rel] = _migrate(crowded[hit.rel], hit.line)
    unbooked = tuple(entry for entry in BASELINE if entry not in {hit.identity for hit in victims})

    assert len(unbooked) == len(BASELINE) - 3
    _all_three_green(crowded, baseline=unbooked)


# ---------------------------------------------------------- 判据⑤：账要一眼看得见是谁
def test_the_ledger_identities_are_well_formed_and_point_at_real_scopes():
    """十五枚身份齐整，且账上的函数名在源码里真找得着（改名要重记账，这是明账）。"""
    sources = repo_sources()
    assert len(set(BASELINE)) == len(BASELINE) == 15, BASELINE

    for entry in BASELINE:
        assert "#" in entry, entry
        left, _, ordinal = entry.rpartition("#")
        assert ordinal.isdigit(), entry
        rel, _, scope = left.partition("::")
        assert rel.endswith(".py") and "::" not in rel, entry
        assert re.search(r":\d+$", entry) is None, f"身份里不许再有行号：{entry}"
        if scope != MODULE_SCOPE and ":" not in scope:
            assert _scope_anchor(sources[rel], scope) is not None, f"账上的作用域在源码里找不到：{entry}"


def test_every_ledger_entry_carries_a_human_readable_note():
    """判据⑤：每行账后面都跟着"这枚长什么样"，不许退化成十五枚不透明身份。"""
    pattern = re.compile(r'^\s+"(?P<identity>[^":]+::[^"]+)",\s+#\s*(?P<who>[^#\n]*connect\([^#\n]*)$')
    notes = {}
    for line in Path(__file__).resolve().read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            notes[match.group("identity")] = match.group("who").strip()

    assert set(notes) == set(BASELINE), (
        f"账上有注记缺席：{sorted(set(BASELINE) - set(notes))}；"
        f"注记不属于账：{sorted(set(notes) - set(BASELINE))}"
    )
    for identity, who in notes.items():
        assert len(who) > len("connect()"), identity


def test_the_file_has_one_line_ending_not_a_mix():
    """纪律：同一文件不许混行尾，也不许有 BOM。

    为什么不钉"必须 CR=0"：`core.autocrlf=true` 下，一枚纯 LF 的文件重新 checkout 就变成
    全 CRLF —— be-r261 开工时实测，HEAD 里那枚 blob 是 16 183 B / CR=0，同一棵工作树里
    落地的它却是 372 枚 CR。把"CR=0"写成判据，等于照 R254 的样子再铸一枚"checkout 一次
    红一次"的假红钉，而那正是本单要拆的东西。所以钉的是一致性：纯 LF 或全 CRLF 都算合格，
    混着就红。本班交付形态本身是纯 LF，实测记在 `_r261_verify.txt`。
    """
    raw = Path(__file__).resolve().read_bytes()
    cr, lf = raw.count(13), raw.count(10)

    assert not raw.startswith(b"\xef\xbb\xbf"), "不许有 BOM"
    assert cr in (0, lf), f"行尾混了：CR={cr} LF={lf}"


# ------------------------------------------------------------------ 判据⑥：反证自证
def _duplicate_the_booked_line(sources, hit):
    """把那枚已记账的落点行原地复制一份塞在它上面——同函数、同缩进、语法必然成立。"""
    original = sources[hit.rel].splitlines()[hit.line - 1]
    return _insert_before(sources[hit.rel], hit.line, original + "\n")


def test_the_ordinal_is_load_bearing_a_second_site_in_one_scope_stays_two():
    """判据⑥：身份里那枚 ``#N`` 是承重的——退化成"同一函数只算一枚"就漏。

    反证刀 B 摘 ``unnumbered_identity()`` 那行公式，本枚用例必红；真身份下它必须绿。
    """
    sources = repo_sources()
    sites = booked(sources)
    chat = next(hit for hit in sites.values() if hit.rel == "app/api/v1/chat.py")
    crowded = dict(sources, **{chat.rel: _duplicate_the_booked_line(sources, chat)})

    caught = readings(crowded)
    assert len(caught) == len(BASELINE) + 1, sorted(caught)
    assert f"{chat.rel}::{chat.scope}#1" in caught, caught
    with pytest.raises(AssertionError):
        _check_no_unrecorded_site(crowded)

    collapsed = readings(crowded, identity=unnumbered_identity)
    assert len(collapsed) == len(BASELINE), collapsed
    assert f"{chat.rel}::{chat.scope}" in collapsed, collapsed


def test_a_path_only_ledger_would_swallow_whole_files():
    """判据⑥：退化成"只认路径"，同一棵文件里第二枚连报错都不会有。

    反证刀 A 摘 ``ledger_identity()`` 那行公式（改成 ``return rel``）：账本立刻对不上号，
    本枚与上面那枚连同三枚硬钉一起红——红得有道理，因为身份真的不比了。
    """
    sources = repo_sources()
    quiet_paths = readings(sources, identity=path_only_identity)
    assert len(quiet_paths) == 15, sorted(quiet_paths)

    crowded, _line = _with_extra_site(sources, "app/api/v1/chat.py")
    assert len(readings(crowded)) == len(BASELINE) + 1
    assert len(readings(crowded, identity=path_only_identity)) == 15
    with pytest.raises(AssertionError):
        _check_no_unrecorded_site(crowded)
    _check_no_unrecorded_site(crowded, baseline=quiet_paths, identity=path_only_identity)

# ------------------------------------------------- 挡绕过：三种以上写法逐个试（判据④）
def _snippet(body):
    """拼一份"最后一步就是建连"的假模块，行号因此可预测。"""
    return "\n".join(["import psycopg", ""] + list(body)) + "\n"


def _site(sites, kind, line, rel="app/sneaky.py"):
    """按"第几行 + 哪种形状"取回那一枚落点：形状用例只验识别力，不验身份怎么拼。"""
    found = [hit for hit in sites if hit.kind == kind and hit.line == line and hit.rel == rel]
    assert len(found) == 1, sites
    return found[0]


def test_star_kwargs_bypass_is_counted():
    source = _snippet(["def open_conn(**kw):", "    return psycopg.connect(**kw)"])
    sites = scan_source("app/sneaky.py", source)

    assert _site(sites, KIND_CALL, 4).snippet == "return psycopg.connect(**kw)"


def test_aliased_module_bypass_is_counted():
    source = "\n".join(
        ["import psycopg as pg", "", "def open_conn(url):", "    return pg.connect(url)"]
    )
    sites = scan_source("app/sneaky.py", source)

    assert _site(sites, KIND_CALL, 4).scope == "open_conn"


def test_from_import_connect_bypass_is_counted():
    source = "\n".join(
        ["from psycopg import connect", "", "def open_conn(url):", "    return connect(url)"]
    )
    sites = scan_source("app/sneaky.py", source)

    assert _site(sites, KIND_CALL, 4).identity == "app/sneaky.py::open_conn#0"
    assert _site(sites, IMPORT_CONNECT, 1).identity == "app/sneaky.py::<module>:import-connect#0"


def test_renamed_import_bypass_is_counted():
    source = "\n".join(
        ["from psycopg import connect as dial", "", "def open_conn(url):", "    return dial(url)"]
    )
    sites = scan_source("app/sneaky.py", source)

    assert _site(sites, KIND_CALL, 4).identity == "app/sneaky.py::open_conn#0"


def test_connection_factory_lambda_bypass_is_counted():
    source = _snippet(
        ["class Store:", "    def __init__(self, connection_factory):", "        self.seam = connection_factory",
         "", "def build(url):", "    return Store(connection_factory=lambda: psycopg.connect(url))"]
    )
    sites = scan_source("app/sneaky.py", source)

    assert _site(sites, KIND_CALL, 8).scope == "build"


def test_partial_reference_bypass_is_counted():
    source = _snippet(
        ["import functools", "", "def build(url):", "    return functools.partial(psycopg.connect, url)"]
    )
    sites = scan_source("app/sneaky.py", source)

    assert _site(sites, KIND_REFERENCE, 6).scope == "build"


def test_psycopg2_spelling_is_counted():
    source = "\n".join(
        ["import psycopg2", "", "def open_conn(url):", "    return psycopg2.connect(url)"]
    )
    sites = scan_source("app/sneaky.py", source)

    assert _site(sites, KIND_CALL, 4).identity == "app/sneaky.py::open_conn#0"


def test_importing_the_connect_symbol_is_alone_a_violation():
    """只 import 不调用也红：绕过往往是先在模块顶上把符号搬出来，回头再调。"""
    source = "\n".join(["from psycopg import connect", "", "HANDOFF = connect"])
    sites = scan_source("app/sneaky.py", source)

    assert _site(sites, IMPORT_CONNECT, 1).scope == MODULE_SCOPE


def test_two_sites_in_one_scope_are_two_identities():
    """同一函数里两枚裸连必须分开记账（``#N`` 承重的正面证据）。"""
    source = _snippet(["def open_conn(url):", "    a = psycopg.connect(url)", "    b = psycopg.connect(url)"])
    sites = scan_source("app/sneaky.py", source)

    assert [hit.identity for hit in sites] == [
        "app/sneaky.py::open_conn#0",
        "app/sneaky.py::open_conn#1",
    ]


# ------------------------------------------- 假阳性防护：散文与注释不算站点
def test_prose_mentions_are_not_sites():
    """注释里、docstring 里写 "psycopg.connect" 不许被数成站点。

    这不是假想的：app/common/auth.py:364 的 docstring 里就写着这四个字符，R230 的钉
    （tests/test_r230_db_ready_selfheal.py:421）也在拿这个字符串做断言。文本匹配会
    把它们当成越界站点，AST 不会。
    """
    comment_only = _snippet(["def plan(url):", "    # 这里将来要换成 psycopg.connect(url)", "    return None"])
    docstring_only = _snippet(["def plan(url):", "    '''换用 psycopg.connect 之前先读判据'''", "    return None"])

    assert scan_source("app/quiet.py", comment_only) == []
    assert scan_source("app/quiet.py", docstring_only) == []


def test_the_real_prose_site_is_not_double_counted():
    """实测：auth.py 第 364 行那句散文没有进清单，进的只有它 301 行那次真调用。"""
    locations = {hit.location for hit in booked(repo_sources()).values()}

    assert "app/common/auth.py:364" not in locations, sorted(locations)
    assert "app/common/auth.py:301" in locations


def test_this_file_is_invisible_to_itself():
    """本文件写着几十处 psycopg.connect 字面量，扫自己必须是零命中。

    拿 grep 做这枚棘轮的话，这一条当场就死。
    """
    source = Path(__file__).resolve().read_text(encoding="utf-8")
    rel = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()

    assert scan_source(rel, source) == []


def test_scope_roots_are_the_ones_the_reading_claims():
    """读数说话要有范围：app/** 14 枚 + scripts/** 1 枚，边界自己 1 枚。"""
    outside, boundary = scan_sources(repo_sources())
    per_root = {}
    for hit in outside:
        root = hit.rel.split("/")[0]
        per_root[root] = per_root.get(root, 0) + 1

    assert per_root == {"app": 14, "scripts": 1}, per_root
    assert [hit for hit in boundary if hit.kind == KIND_CALL], boundary
    assert [hit for hit in boundary if hit.kind == IMPORT_CONNECT] == [], boundary
    assert len(BASELINE) == len(outside) == 15
    assert len({hit.identity for hit in outside}) == len(outside), "身份撞车说明记账口径不够细"


def test_tests_directory_is_out_of_scope_by_design():
    """``tests/**`` 里确实有真库直连，且它们按设计不进这枚棘轮。"""
    sites = []
    for path in sorted((REPO_ROOT / "tests").rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            sites.extend(scan_source(rel, path.read_text(encoding="utf-8")))
        except SyntaxError as exc:  # pragma: no cover
            pytest.fail(f"tests 里扫不动 {rel}: {exc}")
    integration = {hit.identity for hit in sites if hit.kind == KIND_CALL}

    assert integration, "tests/** 里应当有真库直连（test_postgres_backup_recovery.py 等）"
    assert all(identity.startswith("tests/") for identity in integration)
    assert not (integration & set(BASELINE)), "测试件一旦算进生产读数，这枚钉就假了"