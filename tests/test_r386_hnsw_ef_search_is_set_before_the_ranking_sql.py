# -*- coding: utf-8 -*-
"""R386 · 切读那一刻的 HNSW 候选宽度，由代码钉住，不靠运气也不靠注释。

缺陷（R382 挖出、总控独立复现）：pgvector 出厂把 `hnsw.ef_search` 留在比遗留引擎更窄的一档
（运行时读数见 docs/perf/r382-readpath-2026-09-27.md:565 那张表的最后一列），而 `rg -n
ef_search app/ migrations/` 在并树前只交回两条**注释**——migrations/0010_pgvector_chunks.sql
头部那份实测字典，和 app/rag/loader.py 里那句"近重复把 Chroma 的候选吃光"。读路径从来没设过
这一档 ⇒ 单翻 `INDEX_BACKEND=pgvector` 就会把每次语义检索的候选宽度自己改窄。1008 枚上没咬人，
客户尺寸上是切读后的第一颗召回雷。

本文件钉的是四件事，每件都配一把可执行的刀（判据②）：

- 刀 (a) 接线：摘掉 `search_vectors` 里那行 `_apply_hnsw_ef_search(connection)` ⇒
  `test_the_width_is_set_before_the_ranking_statement_in_one_transaction` 红。
- 刀 (b) 缺省：把 `HNSW_EF_SEARCH_DEFAULT` 从"与遗留引擎同宽"改回出厂那一档 ⇒
  `test_the_default_is_the_width_the_retiring_engine_answers_with` 红（它比的不是本文件里的
  一枚数，而是从 0010 那句实测字典现读出来的数）。
- 刀 (c) 单点：在真源之外再抄一份字面量（SQL 文本里、注释里、别的模块里）⇒
  `test_the_number_lives_in_exactly_one_place` 与 `test_no_other_module_spells_the_width` 红。
  本文件的识别式自己配正反对照样本（`test_the_copy_detector_is_not_blind`），防止它退化成空响。
- 刀 (d) 作用域：把事务内的 local 设定换成会话级（裸 `SET` 或 `set_config(..., FALSE)`）⇒
  `test_the_setting_never_survives_the_read_it_belongs_to` 与
  `test_a_reused_connection_does_not_carry_the_previous_width` 红。假件按 PostgreSQL 的两层
  作用域建模，量的是"下一笔请求看见什么"，不是语句长什么样。

范围全离线：不 import psycopg、不连库、不起服务、不打模型、不碰 `chroma_db/**`。
判据③的三条边界（不翻 `INDEX_BACKEND_DEFAULT`、不动 0010 的索引 DDL、不写 `.env*`/`deploy/**`）
由 `test_the_switch_was_not_flipped_by_this_ticket` 自证一遍，写在这里是为了下一个人看得见。
"""
from __future__ import annotations

import ast
import inspect
import re
import textwrap
from pathlib import Path

import pytest

from app.rag import indexing
from app.rag import pg_store

REPO = Path(__file__).resolve().parents[1]
PRODUCTION = REPO / "app" / "rag" / "pg_store.py"
MIGRATION = REPO / "migrations" / "0010_pgvector_chunks.sql"
INDEXING = REPO / "app" / "rag" / "indexing.py"

DIM = 4
QUERY = [0.5] * DIM
VECTOR = "[0.5, 0.5, 0.5, 0.5]"

#: 一条排名 SQL 的形状指纹：本文件只用它**认出**排名语句，不复制它。
RANKING_MARK = "ORDER BY embedding"


# ------------------------------------------------------------------- 唯一可引用的旧口径
def retiring_engine_width() -> int:
    """0010 头部那份实测字典里的遗留引擎 ef_search——本文件不许另抄一枚这个数。

    读的是 migrations/0010_pgvector_chunks.sql 的注释，一字不动那枚文件（判据③：它的
    `ef_construction` 是**建索引**参数，与本单的**查询期**宽度不是一回事，混了就等于假修复）。
    命中数必须恰好一枚：多一枚说明字典被改花了，少一枚说明这条凭据没了，两种都该红。
    """
    hits = re.findall(r"'ef_search'\s*:\s*(\d+)", MIGRATION.read_text(encoding="utf-8"))
    assert len(hits) == 1, (
        f"0010 里 'ef_search' 的实测读数拿到 {len(hits)} 枚（{hits}），"
        "本单的缺省值没有可比的那一枚数了")
    return int(hits[0])


def production_source() -> str:
    return PRODUCTION.read_text(encoding="utf-8")


# ------------------------------------------------------------- 假连接：按两层作用域记账
class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._scalar


def row_for(position):
    return ("r%d.txt_0" % position, "正文 %d" % position, "r%d.txt" % position, 0, 2,
            "研发中心", 0.5)


_SET_CONFIG = re.compile(
    r"^SELECT\s+set_config\(\s*(?:%s|'[^']*')\s*,\s*(?:%s|'[^']*')\s*,\s*"
    r"(TRUE|FALSE|'TRUE'|'FALSE'|'t'|'f'|t|f)\s*\)", re.IGNORECASE)
_BARE_SET = re.compile(
    r"^SET\s+(LOCAL|SESSION)?\s*([A-Za-z_.]+)\s*(?:=|TO)\s*(\S.*)$", re.IGNORECASE)


def interpret_setting(statement, bound=()):
    """把一条"设定参数"的语句读成 PostgreSQL 会读的样子：哪个作用域、哪枚参数、什么值。

    返回 `(scope, name, value)`，不是设定语句就交回 None。认两形：`set_config(name, value,
    is_local)`——第三枚实参决定 local 还是 session——和裸 `SET [LOCAL] name = value`——缺
    LOCAL 就是会话级。这样本件量的是**设定落在哪一层**，而不是某句 SQL 的拼写：刀 (d) 换成
    会话级 `SET`，或把 `TRUE` 改成 `FALSE`，都会在这里被读成 session，不必让本文件再抄一份
    语句文本。
    """
    text = str(statement).strip()
    match = _SET_CONFIG.match(text)
    if match:
        spelling = match.group(1).strip("'").upper()
        assert spelling in {"TRUE", "FALSE", "T", "F"}, spelling
        local = spelling in {"TRUE", "T"}
        pair = [str(item) for item in tuple(bound or ())][:2]
        if len(pair) < 2:
            pair = re.findall(r"'([^']*)'", text)[:2]
        name, value = (pair + [None, None])[:2]
        return ("local" if local else "session"), name, value
    match = _BARE_SET.match(text)
    if match:
        scope = (match.group(1) or "session").lower()
        return ("local" if scope == "local" else "session"), match.group(2), match.group(3)
    return None


class _PgSession:
    """一枚分两层记参数的假连接，外加 vector_mirror 那两条探测。

    为什么可以这么记：读腿的连接由 `open_connection` 交出且不设 autocommit，第一句 SQL 起事务
    就已经开着（`read_topk` 的 finally 只关不提交，正是这件事的另一半），所以本件以
    `in_transaction=True` 开场。`end_transaction()` 就是 PostgreSQL 在事务结束时对 local
    设定做的那次回滚——它只清 local，session 层留下的东西会一路跟着这条连接跑到下一笔。
    """

    def __init__(self, rows=None, *, distance_function="l2", in_transaction=True):
        configured = pg_store.configured_embedding_scope()
        dimension = int(configured.dimension)
        self.scope_row = (configured.embedding_model, dimension, distance_function)
        self.column_type = ("vector(%d)" % dimension,)
        self.rows = [_row for _row in (list(rows) if rows is not None else [row_for(0)])]
        self.session = {}
        self.local = {}
        self.in_transaction = bool(in_transaction)
        self.log = []
        self.width_at_scan = {}
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    # -- the DB-API surface the read leg uses --------------------------------
    def execute(self, sql, params=None):
        statement = str(sql)
        bound = tuple(params or ())
        self.log.append((statement, bound, self.in_transaction))
        setting = interpret_setting(statement, bound)
        if setting is not None:
            scope, name, value = setting
            if scope == "local":
                assert self.in_transaction, (
                    "local 设定落在事务外：PostgreSQL 只把它维持到本语句，紧接着那句排名 SQL "
                    "看见的仍是服务器默认——这正是本件要防的形状，不是本件的 bug")
                self.local[name] = value
            else:
                self.session[name] = value
            return _Result(scalar=value)
        if "vector_scope" in statement:
            return _Result(scalar=self.scope_row)
        if "pg_attribute" in statement:
            return _Result(scalar=self.column_type)
        if RANKING_MARK in statement:
            effective = dict(self.session)
            effective.update(self.local)
            self.width_at_scan = effective
            return _Result(rows=self.rows)
        raise AssertionError("假连接收到没准备好的语句：" + statement)

    def end_transaction(self):
        self.local.clear()

    def commit(self):
        self.commits += 1
        self.end_transaction()

    def rollback(self):
        self.rollbacks += 1
        self.end_transaction()

    def close(self):
        self.closes += 1
        self.end_transaction()

    # -- readers for the assertions ------------------------------------------
    def width_statements(self):
        return [item for item in self.log if interpret_setting(item[0], item[1]) is not None]

    def ranking_statements(self):
        return [item for item in self.log if RANKING_MARK in item[0]]


def one_search(session, **kwargs):
    """问一次排名 SQL：k / where 的默认形状收在这一处，免得每枚用例各抄一份。"""
    kwargs.setdefault("k", 3)
    kwargs.setdefault("where", None)
    return pg_store.search_vectors(connection=session,
                                   vector_table=pg_store.DEFAULT_VECTOR_TABLE,
                                   distance_function="l2", query_vector=list(QUERY), **kwargs)


# --------------------------------------------------------------------- ①／②：接线与作用域
def test_the_default_is_the_width_the_retiring_engine_answers_with():
    """刀 (b)：把缺省改回出厂那一档，这一枚当场红——它比的是 0010 里那枚实测数。

    为什么钉等式而不是钉一枚数：本文件再抄一枚这个数就是全仓第二份真源（判据①），而等式两边
    各自只有一个来源——代码侧 `HNSW_EF_SEARCH_DEFAULT`，凭据侧 0010 那句实测字典。改口要改的
    是 0010 那条注释所记录的事实，不是本文件的某一行断言。
    """
    assert pg_store.HNSW_EF_SEARCH_DEFAULT == retiring_engine_width()
    assert pg_store.configured_hnsw_ef_search({}) == pg_store.HNSW_EF_SEARCH_DEFAULT


def test_the_number_is_the_one_the_read_leg_actually_asks_for(monkeypatch):
    """缺省不配也等于两侧同宽：走真入口 read_topk，量的是排名语句那一刻生效的值。

    这一枚把接线与消费点连起来：`configured_hnsw_ef_search()` 返回得再对，只要排名 SQL 发出
    时那层作用域里没有它，切读仍然是窄的。假件按 PostgreSQL 的层次记账，所以这里断言的是
    "扫描看见什么"，不是"代码写了什么"。
    """
    monkeypatch.delenv(pg_store.ENV_HNSW_EF_SEARCH, raising=False)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    session = _PgSession()
    pg_store.read_topk(query_vector=list(QUERY), k=3, where=None,
                       connection_factory=lambda: session)

    assert session.ranking_statements(), "排名 SQL 根本没发出去，本件无从判定"
    width = pg_store.HNSW_EF_SEARCH_GUC
    assert session.width_at_scan.get(width) == str(pg_store.HNSW_EF_SEARCH_DEFAULT), (
        "排名语句看见的候选宽度不是真源那一档：%r" % (session.width_at_scan,))
    assert session.commits == 0, "读腿不许提交，local 设定也就不会泄漏到事务外"
    assert session.closes == 1


def test_the_width_is_set_before_the_ranking_statement_in_one_transaction():
    """刀 (a)：摘掉 search_vectors 里那一行 `_apply_hnsw_ef_search(connection)`，这枚红。

    钉三件事，缺一件都不算守住：(1) 每次排名查询恰好配一次设定，不是一句里夹带也不是零次；
    (2) 设定在排名语句**之前**；(3) 两条语句都在**同一笔开着的**事务里——psycopg 的隐式
    BEGIN 让 SET LOCAL 有得以生效的那一层，这一格不是想当然，本件把它读成 log 里的第三个字段。
    """
    session = _PgSession()
    one_search(session)

    widths, rankings = session.width_statements(), session.ranking_statements()
    assert len(rankings) == 1, "一次检索只该发一条排名 SQL，拿到 %d 条" % len(rankings)
    assert len(widths) == 1, (
        "一次检索应当配恰好一次候选宽度设定，拿到 %d 次：零次＝读腿在比窄的一档问，"
        "两次＝同一笔事务里改了两回口径" % len(widths))
    assert widths[0][2] is True, "设定发出时事务没开着，local 只活到本句就没了"
    assert rankings[0][2] is True, "排名 SQL 落在了事务外"
    order = [item[0] for item in session.log]
    assert order.index(widths[0][0]) < order.index(rankings[0][0]), (
        "先排名后设定：那条排名 SQL 用的仍是服务器默认，本单的接线等于没接")
    assert all(scope == "local" for scope, _name, _value in
               (interpret_setting(item[0], item[1]) for item in widths)), (
        "设定不在 local 层，切读之后它会跟着连接活到下一笔")


def test_the_width_is_applied_in_exactly_one_place():
    """单点读取：整棵 app/ 里把宽度发到 SQL 的调用点只许有一枚。

    与上一枚配对使用：上一枚验"这一条路走对了"，这一枚验"没有第二条路各走各的"。今天这一枚
    只有一个合法落点——`search_vectors` 自己的函数体。
    """
    callers = []
    for path in sorted((REPO / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == pg_store._apply_hnsw_ef_search.__name__):
                callers.append("%s:%d" % (path.relative_to(REPO).as_posix(), node.lineno))
    assert callers == ["app/rag/pg_store.py:%d" % _ranking_call_site()], (
        "候选宽度的发函点应当只有一枚，实际：" + str(callers))


def _ranking_call_site() -> int:
    """`search_vectors` 里那一枚 `_apply_hnsw_ef_search(...)` 的行号，现读，不手写。"""
    tree = ast.parse(production_source())
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == pg_store.search_vectors.__name__)
    sites = [node.lineno for node in ast.walk(function)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == pg_store._apply_hnsw_ef_search.__name__]
    assert len(sites) == 1, "search_vectors 里的设定调用应当恰好一枚，实际 %r" % (sites,)
    return sites[0]


# ------------------------------------------------------------------ ②(d)：作用域不许外泄
def three_reads(session, monkeypatch, widths):
    """在同一枚假连接上连开三笔 read_topk，每笔按 widths 给那一笔配一次 knob。

    widths 里的元素是 None（不配）或字符串（配）。走真入口而不是只喂 search_vectors：本件要
    断言的是"下一笔请求实际看见的口径"，而连接的一整轮生命周期（探测→设定→排名→只关不提交）
    只有 read_topk 会走完。
    """
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    for value in widths:
        if value is None:
            monkeypatch.delenv(pg_store.ENV_HNSW_EF_SEARCH, raising=False)
        else:
            monkeypatch.setenv(pg_store.ENV_HNSW_EF_SEARCH, value)
        pg_store.read_topk(query_vector=list(QUERY), k=3, where=None,
                           connection_factory=lambda: session)
    return session.width_at_scan.get(pg_store.HNSW_EF_SEARCH_GUC)


def test_the_setting_never_survives_the_read_it_belongs_to():
    """刀 (d)：把 local 换成会话级 `SET hnsw.ef_search = ...`，或把 set_config 第三枚改成 FALSE。

    为什么这一枚要紧：读腿今天是一条连接一笔读，会话级设定看着无害；`_connect` 一旦换成池
    （app/db/connection.py 那节 R238 正是朝这个方向铺的路），下一笔请求——另一个用户、另一个 k、
    另一个语料——就会在一个没人设过的宽度上被答一次。留了名字、没留痕迹，最难查的就是这种。
    """
    session = _PgSession()
    one_search(session)

    assert session.session == {}, (
        "排名查询往会话层写了参数 %r：连接一被复用，这就污染下一笔" % (session.session,))
    assert local_only(session), "候选宽度的设定不止落在 local 层"
    assert session.local, (
        "local 层是空的：接线不在这里了，本件的判定对象已经换掉，必须重新写这一枚")

    session.close()                       # 一笔读结束：只关不提交，事务连带 local 一起回滚
    assert session.local == {}, "事务都结束了，local 还留着宽度"


def test_a_reused_connection_does_not_carry_the_previous_width(monkeypatch):
    """同一枚连接连开三笔（缺省 → 运维档 → 缺省）：第三笔必须回到真源，不继承第二笔。

    与上一枚同一族病、两个断面。会话级写法在这一枚同样红，而且红得更准：它扛不住第三笔，
    因为上一笔的数跟着连接活到了这一笔——那正是"翻完开关第一夜口径悄悄变了"的形状。
    """
    width = retiring_engine_width()
    session = _PgSession()
    asked = three_reads(session, monkeypatch, [None, str(width + 1)])
    assert asked == str(width + 1), "第二笔没问到运维配的那一档：knob 没被读"

    asked = three_reads(session, monkeypatch, [None])       # 第三笔，环境已经干净
    assert asked == str(width), (
        "第三笔继承了第二笔的宽度（%r）：那是会话级设定的形状，不是本单要的 local" % (asked,))


def test_a_later_reader_on_the_same_connection_is_not_pre_set():
    """刀 (d) 的第二断面：本笔读结束以后，同一条连接上**没设过宽度**的那一问不该继承任何东西。

    上一枚看的是"下一笔设定者算不算得对"，这一枚看的是更硬的一格——连接后面接的是别人：一个
    直接发 SQL 的脚本、一个共用这条连接的池。会话级设定在这一枚红，因为 `search_vectors` 之外
    的人从没 ask 过 100，却已经站在 100 上答题了；local 那一档在事务结束时就跟着事务回滚了。
    """
    session = _PgSession()
    one_search(session)
    session.close()                            # 一笔读的生命周期到此为止（只关不提交）

    session.execute("SELECT vector_id FROM chunk_vectors ORDER BY embedding <-> %s::vector"
                    " LIMIT %s", (VECTOR, 1))
    assert pg_store.HNSW_EF_SEARCH_GUC not in session.width_at_scan, (
        "下一位提问者接手了一个它没要过的候选宽度：%r" % (session.width_at_scan,))
    assert session.session == {} and session.local == {}


def local_only(session) -> bool:
    return all(interpret_setting(statement, bound)[0] == "local"
               for statement, bound, _open in session.width_statements())


# ------------------------------------------------------------------- ①：单点派生的静态面
def _standalone(number: int):
    """只认作为独立数字出现的这一枚数，别把 0010 / 247 / 1.5 也算成抄。"""
    return re.compile(r"(?<![\d.])%d(?![\d.])" % int(number))


def true_source_line() -> int:
    """`HNSW_EF_SEARCH_DEFAULT = <那枚数>` 的行号，现读自生产码。"""
    tree = ast.parse(production_source())
    nodes = [node for node in tree.body
             if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name)
                     and target.id == "HNSW_EF_SEARCH_DEFAULT" for target in node.targets)]
    assert len(nodes) == 1, "真源的定义行应当恰好一枚，实际 %d 枚" % len(nodes)
    value = nodes[0].value
    assert isinstance(value, ast.Constant) and int(value.value) == retiring_engine_width(), (
        "真源那行应当直接把宽度写成一枚整数：本单的判定全靠这一格")
    return nodes[0].lineno


def _string_constants(tree):
    """非叙述的字符串常量，连行号一起交回（docstring 是说明，不是第二份真源）。"""
    narrative = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            narrative.add(id(node.value))
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in narrative]


def copied_width_lines(source: str, width: int, exempt_line: int = 0):
    """这一份源码里把宽度抄成第二处的地方：字面量、SQL 文本、独立成行的注释。"""
    pattern = _standalone(width)
    tree = ast.parse(source)
    offenders = [(lineno, "字符串里出现宽度：" + text[:60])
                 for lineno, text in _string_constants(tree) if pattern.search(text)]
    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if lineno == exempt_line or not pattern.search(line):
            continue
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            offenders.append((lineno, "非真源行写到了宽度：" + stripped[:60]))
    for node in ast.walk(tree):
        if (isinstance(node, (ast.Assign, ast.AnnAssign)) and node.lineno != exempt_line
                and isinstance(getattr(node, "value", None), ast.Constant)
                and isinstance(node.value.value, int) and node.value.value == width):
            offenders.append((node.lineno, "第二枚整数字面量"))
    return sorted(offenders)


def test_the_number_lives_in_exactly_one_place():
    """刀 (c)：在 pg_store.py 里再抄一份那枚数——写进 SQL、写进新常量、写进注释——当场红。

    这条正是 R380 立的"防线只有一处"那一族：R22 不许这枚文件出现第二份 768，本单不许出现第二
    份宽度。判据不是"看起来重复"，是三样可机械检出的形状：非叙述字符串、独立成行的数字、第二枚
    整数字面量赋值。真源那一行按行号豁免，而豁免本身来自 `true_source_line()` 的现读。
    """
    width = retiring_engine_width()
    source = production_source()
    definition = true_source_line()
    assert not copied_width_lines(source, width, exempt_line=definition), (
        "宽度被抄成了第二处：%r" % (copied_width_lines(source, width,
                                                        exempt_line=definition),))
    assert [node.lineno for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, int)
            and node.value == width] == [definition], "整数字面量不止真源那一枚：改一处漏一处"


def test_the_statement_carries_no_pasted_number():
    """宽度必须作为绑定参数到达 SQL；语句文本里出现数字即假接线。"""
    statement = pg_store._APPLY_HNSW_EF_SEARCH_SQL
    assert statement.count("%s") == 2, "设定语句该有两个占位符（参数名、参数值）：" + statement
    assert not re.search(r"\d", statement), (
        "设定语句里出现数字，说明宽度被手抄进了 SQL 文本：" + statement)
    assert not _standalone(retiring_engine_width()).search(pg_store.HNSW_EF_SEARCH_GUC)

    session = _PgSession()
    one_search(session)
    _statement, bound, _open = session.width_statements()[0]
    assert bound == (pg_store.HNSW_EF_SEARCH_GUC, str(pg_store.HNSW_EF_SEARCH_DEFAULT)), (
        "设定参数不是（GUC 名, 真源的数）这一对：%r" % (bound,))


# -------------------------------------------------------------------- ①：knob 与拒答的形状
def test_the_knob_moves_the_width_and_an_unusable_value_costs_only_the_setting(monkeypatch):
    """运维可配、缺省同宽、写坏了也只是"这次没配成"：三种形状都要在缺省真源之外自洽。

    不接的形状一律回落到真源并留一条 WARNING，这是 indexing._configured_dimension 对维度已经
    采用的那一条：回落值不是猜的，它就是遗留引擎那一档，所以 knob 写错付的是"设置没生效"，
    永远不会付"答得比被替换的那台还窄"。上限不在这里写死——那是 PostgreSQL 的 GUC 边界，本单
    不许再抄一枚数，越界的正整数交给服务器拒答，由 retriever 记成一枚有名绕行。
    """
    width = retiring_engine_width()
    knob = pg_store.ENV_HNSW_EF_SEARCH
    monkeypatch.setenv(knob, str(width + 7))
    assert pg_store.configured_hnsw_ef_search() == width + 7
    session = _PgSession()
    one_search(session)
    assert session.width_at_scan[pg_store.HNSW_EF_SEARCH_GUC] == str(width + 7), (
        "knob 在函数里算对了却没到达排名语句：接线是假的")

    for unusable in ("", "   ", "abc", "0", "-1", "1.5", "1e3"):
        monkeypatch.setenv(knob, unusable)
        assert pg_store.configured_hnsw_ef_search() == width, unusable
    monkeypatch.setenv(knob, str(2 ** 40))
    assert pg_store.configured_hnsw_ef_search() == 2 ** 40, (
        "本件不再替 PostgreSQL 判上限，越界那一档必须由服务器自己拒")


def test_a_refused_read_sends_no_statement_at_all():
    """拒答的三条路（不认的表、不认的算符、翻译不出来的 where）一个字都不许落到连接上。

    这一枚管的是本单唯一一次改动语句次序的理由：宽度设定必须排在**全部校验之后**。校验没过后
    还去 SET，等于在一笔被拒的事务里留下一个人设过的口径——R59 那条"谓词翻译不出来就不该发
    向量 SQL"的钉子管的是同一件事，本单不许从旁边绕过去。
    """
    session = _PgSession()
    with pytest.raises(pg_store.VectorReadRejectedError):
        pg_store.search_vectors(connection=session, vector_table="some_other_table",
                                distance_function="l2", query_vector=list(QUERY), k=3)
    with pytest.raises(pg_store.VectorReadRejectedError):
        pg_store.search_vectors(connection=session,
                                vector_table=pg_store.DEFAULT_VECTOR_TABLE,
                                distance_function="cosinus", query_vector=list(QUERY), k=3)
    with pytest.raises(pg_store.ScopeFilterUntranslatable):
        one_search(session, where={"$or": [{"classification": {"$in": [1]}}]})

    assert session.log == [], "拒答的分支往连接上发了语句：%r" % (session.log,)
    assert session.width_statements() == [] and session.width_at_scan == {}


def test_the_new_knob_is_not_a_read_backend_switch():
    """本单只加"多宽"，不加"问谁"：宽度函数不许读 INDEX_BACKEND，也不许新增任何后端默认值。"""
    assert pg_store.ENV_HNSW_EF_SEARCH != indexing.INDEX_BACKEND_ENV
    tree = ast.parse(textwrap.dedent(inspect.getsource(pg_store.configured_hnsw_ef_search)))
    words = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    words |= {text for _lineno, text in _string_constants(tree)}
    assert indexing.INDEX_BACKEND_ENV not in words, (
        "宽度函数开始读切读开关：两枚闸门就此缠成一枚，出事时没人分得清是谁翻的页")
    assert "ENV_HNSW_EF_SEARCH" in words, (
        "宽度函数没有按名字问那枚唯一的开关名，它读的是哪一枚？")
    spelled = [text for _lineno, text in _string_constants(tree)
               if re.fullmatch(r"[A-Z][A-Z0-9_]{4,}", text)]
    assert not spelled, "函数把开关名写成了字面量，那是开关名的第二份抄本：%r" % (spelled,)
    names = {target.id for node in ast.parse(production_source()).body
             if isinstance(node, ast.Assign) for target in node.targets
             if isinstance(target, ast.Name)}
    assert not (names & {"INDEX_BACKEND", "INDEX_BACKEND_DEFAULT",
                         indexing.INDEX_BACKEND_ENV}), "pg_store 自己立了一枚读后端默认值"


# ---------------------------------------------------------------- 反证钉的自证（不许空响）
def copies_in_source(label, source, width, exempt_lines=()):
    """一份源码里"把宽度写成第二处"的可执行形状：字面量赋值，或带着 GUC 名又带数的语句文本。"""
    pattern, tree = _standalone(width), ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.lineno in exempt_lines:
            continue
        value = node.value
        if not (isinstance(value, ast.Constant) and isinstance(value.value, int)):
            continue
        targets = getattr(node, "targets", None) or [node.target]
        names = " ".join(getattr(target, "id", "") for target in targets
                             if isinstance(target, (ast.Name, ast.Attribute)))
        if value.value == width and _ef_like(names):
            found.append((label, node.lineno, "第二枚宽度字面量：" + names))
    for lineno, text in _string_constants(tree):
        if lineno in exempt_lines:
            continue
        if "ef_search" in text.lower() and pattern.search(text):
            found.append((label, lineno, "语句文本里带着宽度：" + text[:60]))
    return found


def _ef_like(name: str) -> bool:
    return re.search(r"ef.{0,12}search|hnsw", name or "", re.IGNORECASE) is not None


def test_no_other_module_spells_the_width():
    """刀 (c) 的第二断面：全棵 app/ 加上本文件，除真源那一行之外不许再出现第二处。

    管的是可执行的抄本，不管叙述：0010 那句实测字典、loader 里那句"候选被吃光"都是凭据，按
    判据③一个字都不许动，也不该被这枚钉当成抄本（所以非 docstring 的字符串才算，行号豁免只给
    真源那一行）。这条同时把本文件自己算进去——抄一份数的冲动最先落在钉里。
    """
    width = retiring_engine_width()
    definition = true_source_line()
    production = PRODUCTION.relative_to(REPO).as_posix()
    sources = []
    for path in sorted((REPO / "app").rglob("*.py")) + [Path(__file__).resolve()]:
        label = path.relative_to(REPO).as_posix()
        sources.append((label, path.read_text(encoding="utf-8"),
                        {definition} if label == production else set()))
    found = [item for label, source, exempt in sources
             for item in copies_in_source(label, source, width, exempt_lines=exempt)]
    assert not found, "宽度出现了第二处：%r" % (found,)


def test_the_copy_detector_is_not_blind():
    """识别式自己配正反样本：把宽度抄进 SQL 文本、抄成新常量，两种都要被认出来。

    这一枚是判据②的"必须真咬"在刀 (c) 上的落地：没有它，`test_no_other_module_spells_the_width`
    可以因为正则写错而永远绿。合成样本一律现拼，本文件因此自己也不带第二份数字。
    """
    width = retiring_engine_width()
    guc = pg_store.HNSW_EF_SEARCH_GUC
    pasted_sql = "_SQL = \"SELECT set_config('%s', '%s', TRUE)\"\n" % (guc, width)
    second_constant = "HNSW_EF_SEARCH_OTHER = %d\n" % width
    clean = ("GUC = \"%s\"\n_WIDTH = pg_store.HNSW_EF_SEARCH_DEFAULT\n"
             "_SQL = \"SELECT set_config(%%s, %%s, TRUE)\"\n" % guc)

    assert copies_in_source("pasted.sql", pasted_sql, width), "抄进 SQL 文本没被认出来"
    assert copies_in_source("second.constant.py", second_constant, width), "第二枚常量没被认出来"
    assert copies_in_source("clean.py", clean, width) == [], "干净样本被误判，识别式在乱响"
    assert copied_width_lines(clean, width) == [], "干净样本在文件内规则下也被误判"


def test_the_setting_interpreter_is_not_blind():
    """假件分得清四种写法：local / 会话级 × 函数式 / 裸 SET。分不清就等于刀 (d) 没牙。"""
    width = str(retiring_engine_width())
    guc = pg_store.HNSW_EF_SEARCH_GUC
    forms = [interpret_setting("SELECT set_config(%s, %s, TRUE)", (guc, width)),
             interpret_setting("SELECT set_config(%s, %s, FALSE)", (guc, width)),
             interpret_setting("SET LOCAL " + guc + " = " + width),
             interpret_setting("SET " + guc + " = " + width)]
    assert [item[0] for item in forms] == ["local", "session", "local", "session"], forms
    assert all(item[1] == guc and item[2] == width for item in forms), forms
    assert interpret_setting("SELECT 1 FROM chunk_vectors", ()) is None, (
        "识别式把普通语句读成了设定，本件的作用域账就不可信了")


# -------------------------------------------------------------------- 判据③：本单的边界
def test_the_switch_was_not_flipped_by_this_ticket():
    """本单只把宽度接进读腿，出厂那行仍留在遗留引擎一侧（计划书 §P4/§9 的硬闸仍然生效）。

    这枚自证不替代 tests/test_r382_untouched_defaults_pins.py 对 `INDEX_BACKEND_DEFAULT` 的钉：
    那一枚是总控口径，本单不许把它搬过来重钉一遍；这里只记一件与本单直接有关的事实——我没有
    为这一档新增任何会翻页的开关。
    """
    source = INDEXING.read_text(encoding="utf-8")
    assert re.search(r'(?m)^INDEX_BACKEND_DEFAULT\s*=\s*"chroma"\s*$', source), (
        "出厂默认被翻了：本单的读数与 R382 的对照基线同时作废")
    assert pg_store.ENV_HNSW_EF_SEARCH not in source, (
        "宽度开关被接进了切读闸门：两件事必须各拧各的")
