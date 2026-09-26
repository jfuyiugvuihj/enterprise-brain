"""R238 判据④：边界之外裸 ``psycopg.connect`` 的枚数棘轮。

一句话：本单只造边界，一枚调用点都不迁，所以"别人不能再随手加一枚"必须由机械钉住。
起点读数 = **15 枚**（``app/**`` 14 枚 + ``scripts/**`` 1 枚），逐枚 file:line 落在下面
``BASELINE`` 里；只准降不准升。

为什么是 15 而不是派工单里的 11：派工单那张表漏了 ``app/api/v1/`` 整棵
（chat.py:853 / alerts.py:45 / feedback.py:70），并且把三枚路径记错了目录
（真值是 app/memory/profile.py、app/semantics/registry.py、app/storage/pending_approvals.py）。
本单交回时按实测记账，同一个数字在主干上另有出处：app/common/auth.py:364 那句
"实测 app/** 里 auth.py 之外还有 14 处 psycopg.connect" 与这里的 app 侧 14 枚**互相
对上**（14 = 本表 app 侧 14 枚，auth.py 自己那枚另算，边界 connection.py:52 也另算）。

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
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = "app/db/connection.py"
SCANNED_ROOTS = ("app", "scripts")
DRIVER_ROOTS = frozenset({"psycopg", "psycopg2", "psycopg_binary"})
IMPORT_CONNECT = "import-connect"

#: 2026-09-25 @ecc9c54 的实测起点。迁移掉一枚就把对应那行删掉（判据④：只准降不准升）。
BASELINE = (
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
    "app/rag/retriever.py:567",
    "app/semantics/registry.py:514",
    "app/storage/pending_approvals.py:105",
    "app/storage/persistence.py:595",
    "scripts/audit_vector_mirror_sets.py:428",
)


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


def scan_source(rel: str, source: str):
    """扫一份源码，交回排序后的 ``[(reading, kind)]``，reading 形如 ``app/x/y.py:12``。

    kind 三枚：``call``（真在建连）、``reference``（把 ``psycopg.connect`` 当值递出去，
    绕过就长这样）、``from- psycopg import connect``（符号被搬出驱动本身）。
    """
    tree = ast.parse(source)
    module_alias, connect_alias = _bindings(tree)
    sites = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in DRIVER_ROOTS:
            for alias in node.names:
                if alias.name == "connect":
                    sites.add((f"{rel}:{node.lineno}", IMPORT_CONNECT))

    called_lines = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "connect" and _is_handle_to(func.value, module_alias):
            sites.add((f"{rel}:{node.lineno}", "call"))
            called_lines.add(node.lineno)
        elif isinstance(func, ast.Name) and func.id in connect_alias:
            sites.add((f"{rel}:{node.lineno}", "call"))
            called_lines.add(node.lineno)

    for node in ast.walk(tree):
        # 只引用不调用（functools.partial、赋值给变量、当参数递出去）也算站点。
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "connect"
            and node.lineno not in called_lines
            and _is_handle_to(node.value, module_alias)
        ):
            sites.add((f"{rel}:{node.lineno}", "reference"))

    return sorted(sites)


def repo_sources():
    sources = {}
    for root in SCANNED_ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            sources[rel] = path.read_text(encoding="utf-8")
    return sources


def scan_sources(sources):
    """交回 (边界之外, 边界之内) 两组站点。语法扫不动的文件一律当事故。"""
    sites, unparsed = [], []
    for rel, source in sources.items():
        try:
            sites.extend(scan_source(rel, source))
        except SyntaxError as exc:
            unparsed.append(f"{rel}: {exc}")
    assert unparsed == [], f"扫不动的文件不许被当成零命中：{unparsed}"
    prefix = BOUNDARY + ":"
    return (
        [site for site in sites if not site[0].startswith(prefix)],
        [site for site in sites if site[0].startswith(prefix)],
    )


def readings(sources):
    outside, _boundary = scan_sources(sources)
    return {reading for reading, _kind in outside}

# ------------------------------------------------------------------ 棘轮本体
def test_the_bare_connect_count_never_rises():
    """判据④主钉：边界之外的枚数只准降、不准升。"""
    actual = readings(repo_sources())

    assert len(actual) <= len(BASELINE), (
        f"边界之外裸 connect 从 {len(BASELINE)} 枚涨到 {len(actual)} 枚；"
        f"多出来的是 {sorted(actual - set(BASELINE))}"
    )


def test_no_unrecorded_site_is_allowed():
    """每一枚都必须能在起点清单里找到；新长出来的那一枚当场红，且被点名。"""
    actual = readings(repo_sources())

    assert actual <= set(BASELINE), (
        "新增裸 psycopg.connect：" + ", ".join(sorted(actual - set(BASELINE)))
        + " —— 请改走 app/db/connection.py 的边界，或向总控申请入册"
    )


def test_the_recorded_reading_is_current():
    """清单本身也不许过期：迁移掉一枚，就把那一行从 BASELINE 删掉。

    这一枚不是罚你迁移，是罚你迁移完不记账。删一行就绿。
    """
    actual = readings(repo_sources())

    assert actual == set(BASELINE), (
        f"已迁走（该从清单里删掉）：{sorted(set(BASELINE) - actual)}；"
        f"新长出来（不许）：{sorted(actual - set(BASELINE))}"
    )


def test_the_boundary_itself_opens_exactly_one_connection():
    """边界之内只许有一枚真建连，外加策略入口那一枚"引用"。

    为什么引用在边界里合法：``connect_with_policy`` 得把驱动函数接到注入缝上
    （``connect = psycopg.connect``），而"允许碰驱动"这件事本来就只属于这一棵文件。
    边界之外，引用和调用一样算越界。
    """
    _outside, boundary = scan_sources(repo_sources())
    calls = [site for site in boundary if site[1] == "call"]
    references = [site for site in boundary if site[1] == "reference"]
    lines = REPO_ROOT.joinpath(BOUNDARY).read_text(encoding="utf-8").splitlines()

    assert len(calls) == 1, boundary
    lineno = int(calls[0][0].split(":")[1])
    assert "settings.url" in lines[lineno - 1], lines[lineno - 1]
    assert len(references) <= 1, boundary


def test_a_migrated_site_is_a_decrease_not_a_failure():
    """反证（④的方向性）：把 15 枚里的 3 枚迁走，两枚硬钉必须照样绿。

    只有"清单未同步"那一枚会红，而它红的意思是"删三行"，不是"改回去"。
    """
    migrated = set(BASELINE) - {
        "app/api/v1/alerts.py:45",
        "app/memory/profile.py:36",
        "scripts/audit_vector_mirror_sets.py:428",
    }

    assert migrated <= set(BASELINE)
    assert len(migrated) <= len(BASELINE)
    assert migrated - set(BASELINE) == set()


# ------------------------------------------------- 挡绕过：三种以上写法逐个试
def _snippet(body):
    """拼一份"最后一步就是建连"的假模块，行号因此可预测。"""
    return "\n".join(["import psycopg", ""] + list(body)) + "\n"


def test_star_kwargs_bypass_is_counted():
    source = _snippet(["def open_conn(**kw):", "    return psycopg.connect(**kw)"])
    sites = scan_source("app/sneaky.py", source)

    assert ("app/sneaky.py:4", "call") in sites, sites


def test_aliased_module_bypass_is_counted():
    source = "\n".join(
        ["import psycopg as pg", "", "def open_conn(url):", "    return pg.connect(url)"]
    )
    sites = scan_source("app/sneaky.py", source)

    assert ("app/sneaky.py:4", "call") in sites, sites


def test_from_import_connect_bypass_is_counted():
    source = "\n".join(
        ["from psycopg import connect", "", "def open_conn(url):", "    return connect(url)"]
    )
    sites = scan_source("app/sneaky.py", source)

    assert ("app/sneaky.py:4", "call") in sites, sites
    assert ("app/sneaky.py:1", IMPORT_CONNECT) in sites, sites


def test_renamed_import_bypass_is_counted():
    source = "\n".join(
        ["from psycopg import connect as dial", "", "def open_conn(url):", "    return dial(url)"]
    )
    sites = scan_source("app/sneaky.py", source)

    assert ("app/sneaky.py:4", "call") in sites, sites


def test_connection_factory_lambda_bypass_is_counted():
    source = _snippet(
        ["class Store:", "    def __init__(self, connection_factory):", "        self.seam = connection_factory",
         "", "def build(url):", "    return Store(connection_factory=lambda: psycopg.connect(url))"]
    )
    sites = scan_source("app/sneaky.py", source)

    assert ("app/sneaky.py:8", "call") in sites, sites


def test_partial_reference_bypass_is_counted():
    source = _snippet(
        ["import functools", "", "def build(url):", "    return functools.partial(psycopg.connect, url)"]
    )
    sites = scan_source("app/sneaky.py", source)

    assert ("app/sneaky.py:6", "reference") in sites, sites


def test_psycopg2_spelling_is_counted():
    source = "\n".join(
        ["import psycopg2", "", "def open_conn(url):", "    return psycopg2.connect(url)"]
    )
    sites = scan_source("app/sneaky.py", source)

    assert ("app/sneaky.py:4", "call") in sites, sites


def test_importing_the_connect_symbol_is_alone_a_violation():
    """只 import 不调用也红：绕过往往是先在模块顶上把符号搬出来，回头再调。"""
    source = "\n".join(["from psycopg import connect", "", "HANDOFF = connect"])
    sites = scan_source("app/sneaky.py", source)

    assert (f"app/sneaky.py:1", IMPORT_CONNECT) in sites, sites


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
    actual = readings(repo_sources())

    assert "app/common/auth.py:364" not in actual, sorted(actual)
    assert "app/common/auth.py:301" in actual


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
    for reading, _kind in outside:
        root = reading.split("/")[0]
        per_root[root] = per_root.get(root, 0) + 1

    assert per_root == {"app": 14, "scripts": 1}, per_root
    assert [s for s in boundary if s[1] == "call"], boundary
    assert [s for s in boundary if s[1] == IMPORT_CONNECT] == [], boundary
    assert len(BASELINE) == len(outside) == 15


def test_tests_directory_is_out_of_scope_by_design():
    """``tests/**`` 里确实有真库直连，且它们按设计不进这枚棘轮。"""
    sites = []
    for path in sorted((REPO_ROOT / "tests").rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            sites.extend(scan_source(rel, path.read_text(encoding="utf-8")))
        except SyntaxError as exc:  # pragma: no cover
            pytest.fail(f"tests 里扫不动 {rel}: {exc}")
    integration = {reading for reading, kind in sites if kind == "call"}

    assert integration, "tests/** 里应当有真库直连（test_postgres_backup_recovery.py 等）"
    assert all(reading.startswith("tests/") for reading in integration)
    assert not (integration & set(BASELINE)), "测试件一旦算进生产读数，这枚钉就假了"