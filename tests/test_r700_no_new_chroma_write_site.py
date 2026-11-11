"""R700 判据④③ · 本单碰过的三枚模块里一枚新增的 Chroma 写点都不许多出来（棘轮钉）。

形状沿用在册的 tests/test_r238_bare_connect_ratchet.py：判定走 AST，不走 grep。理由在这里
同样成立——本文件自己就写着十几处 chromadb / PersistentClient 的字面量，文本匹配会立刻把
自己算成罪证；而 app/documents/knowledge_ingest.py 的 docstring 里也写着「本模块不开 store、
不开 client」这种话，AST 不会把它数成一枚调用。

判据写的是 AGENTS.md 的技术栈定案（生产向量库＝PostgreSQL + PGVector，Chroma＝退役中的遗留件，
新代码一律不得新增 Chroma 依赖或新的 Chroma 写点），落成四格可失败的话：
① 三枚文件里不许 import chromadb（含起别名 import chromadb as store、含 from chromadb import 某一枚符号）；
② 不许出现 PersistentClient／EphemeralClient／Client／HttpClient 这类开库动作；
③ 不许出现 get_or_create_collection／create_collection／get_collection 这类开集合动作；
④ 不许对「看起来就是遗留集合／客户端」的把手（collection、client、legacy_store…）调用会改
   动物的动词（add／upsert／update／put／insert／modify／delete）。

被批准的那一枚出口法外开恩，并且反过来点名要求它必须在：app/rag/retriever.py 的
DocumentRetriever.add_document —— 那是 R625 逐枚点名过的在册写点，本单唯一的入库写动作。
它由「同一枚扫描器不许把它算成违规」与「新模块里它恰好出现一枚、接收者是 retriever」两半
一起钉住：换成第二枚写点，前一枚红；偷偷新加第二枚，后一枚红。

扫描范围按本单写域收口（判据原话「扫本单新文件」）：全仓 Chroma 写点的名册另有在册件
tests/test_r625_chroma_write_sites_are_named_one_by_one.py，本件不复制它，也不与它抢真源。

全程离线：不 import app，只读源码文本；不起服务、不连库、不开宿主模型端口、不打模型。
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 本单写域里被改过／新建的三枚产品码，逐枚点名（新增一枚文件就要在这里多点名一枚）。
TICKET_FILES = (
    "app/api/v1/data.py",
    "app/documents/file_security.py",
    "app/documents/knowledge_ingest.py",
)

#: 遗留向量库的包名。import 它 = 新增 Chroma 依赖，本单判据①直接拒。
LEGACY_PACKAGE_NAMES = frozenset({"chromadb", "chroma"})
#: 开库动作：拿到一枚客户端就等于自己开了一个 store，本单一条都不许多。
CLIENT_CONSTRUCTORS = frozenset({"PersistentClient", "EphemeralClient", "HttpClient", "Client"})
#: 开集合动作。
COLLECTION_OPENERS = frozenset({"get_or_create_collection", "create_collection", "get_collection"})
#: 会改动物的动词（与在册 R625 的 WRITE_VERBS 同一口径，本件不另造一套词）。
WRITE_VERBS = frozenset({"add", "upsert", "update", "put", "insert", "modify", "delete"})
#: 「看起来就是遗留集合／客户端」的把手名。写点只认这些把手，避免把 dict.update 之类算成罪证。
STORE_HANDLE_NAMES = frozenset({
    "collection", "collections", "client", "chroma_client", "chroma",
    "legacy", "legacy_client", "legacy_collection", "legacy_store",
    "store", "vector_store", "kb_store",
})
#: 唯一被批准把行交给索引的那枚出口（app/rag/retriever.py::DocumentRetriever.add_document）。
SANCTIONED_EXIT = "add_document"

KIND_IMPORT = "import-legacy-package"
KIND_CLIENT = "open-legacy-client"
KIND_COLLECTION = "open-legacy-collection"
KIND_WRITE = "write-to-legacy-handle"


@dataclass(frozen=True)
class Site:
    """一枚被点名的写点：它在哪一枚文件、哪一枚作用域、是哪一格形状。"""

    rel: str
    kind: str
    scope: str
    line: int
    source: str

    @property
    def identity(self) -> str:
        return "{0}::{1}::{2}".format(self.rel, self.kind, self.scope)


def _root_name(node: ast.expr) -> str:
    """属性链最底下那个名字（a.b.c → a），取不到就交回空串。"""
    current = node
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else ""


def _attr_name(node: ast.expr) -> str:
    return node.attr if isinstance(node, ast.Attribute) else ""


def scan_source(rel: str, source: str) -> list[Site]:
    """现取一枚源文件里所有「新增 Chroma 依赖／写点」的形状；散文与注释天然不算（交回逐枚点名的清单）。"""
    tree = ast.parse(source)
    found: list[Site] = []

    def note(kind: str, node: ast.Call | ast.stmt) -> None:
        found.append(
            Site(
                rel=rel,
                kind=kind,
                scope=_scope_name(tree, node),
                line=getattr(node, "lineno", 0),
                source=" ".join(ast.unparse(node).split()),
            )
        )

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if _imports_legacy(node):
                note(KIND_IMPORT, node)
            continue
        if not isinstance(node, ast.Call):
            continue
        kind = _legacy_write_call(node)
        if kind:
            note(kind, node)
    return found


def _legacy_write_call(node: ast.Call) -> str:
    """这一枚调用是不是「对遗留库或对遗留把手动手」；是就交回形状名，不是就交回空串。

    PersistentClient／EphemeralClient 这两枚名字本身就是遗留库的入口，不管挂在哪个把手上
    （chromadb.PersistentClient／store.EphemeralClient）都算开库；写动词则只认遗留把手
    （collection／client／legacy_store…），否则一句 preview.update(...) 就会被当成罪证。
    """
    called = _called_name(node.func)
    if called in CLIENT_CONSTRUCTORS:
        return KIND_CLIENT
    if called in COLLECTION_OPENERS:
        return KIND_COLLECTION
    if called in WRITE_VERBS and called != SANCTIONED_EXIT:
        handle = _handle_name(node.func.value) if isinstance(node.func, ast.Attribute) else ""
        if handle in STORE_HANDLE_NAMES or _root_name(node.func) in STORE_HANDLE_NAMES:
            return KIND_WRITE
    return ""


def _called_name(func: ast.expr) -> str:
    """被调用的名字：x.y.z(...) 取 y，bare(...) 取 bare。"""
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _imports_legacy(node: ast.stmt) -> bool:
    if isinstance(node, ast.Import):
        return any(alias.name.split(".")[0] in LEGACY_PACKAGE_NAMES for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        return (node.module or "").split(".")[0] in LEGACY_PACKAGE_NAMES
    return False


def _handle_name(node: ast.expr) -> str:
    """把手名：collection.add(...) 取 collection，self.collection.add(...) 也取 collection。"""
    if isinstance(node, ast.Attribute):
        return node.attr or _root_name(node)
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _scope_name(tree: ast.Module, node: ast.AST) -> str:
    """节点所属的作用域名（函数／类限定名），拿不到就记 <module>。"""
    best = "<module>"
    best_span = None
    for child in ast.walk(tree):
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        span = _span(child)
        if span is None:
            continue
        start, end = span
        line = getattr(node, "lineno", 0)
        if start <= line <= end and (best_span is None or (end - start) < best_span):
            best = child.name
            best_span = end - start
    return best


def _span(node: ast.AST) -> tuple[int, int] | None:
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if start is None or end is None:
        return None
    return int(start), int(end)


def ticket_sources() -> dict[str, str]:
    readings = {}
    for rel in TICKET_FILES:
        path = REPO_ROOT / rel
        assert path.is_file(), "本单写域里的文件不见了：" + rel
        readings[rel] = path.read_text(encoding="utf-8")
    return readings


def _snippet(lines: list[str]) -> str:
    return "\n".join(lines)


# ==================== 判据④③：本单三枚文件零命中 ====================


def test_the_files_this_ticket_touched_open_no_legacy_store() -> None:
    """三枚文件逐枚点名：import／开库／开集合／写遗留把手，一格都不许多出来。"""
    violations = []
    for rel, source in ticket_sources().items():
        violations.extend(scan_source(rel, source))

    assert violations == [], "\n".join(
        "新增 Chroma 依赖或写点：{0}（{1} 第 {2} 枚：{3}）".format(
            hit.identity, hit.kind, hit.line, hit.source
        )
        for hit in violations
    )


def test_the_ingest_module_writes_through_the_sanctioned_exit_only() -> None:
    """入库动作只许有一枚，且就是 retriever.add_document；接收者必须是路由借来的那枚 handle。

    那一枚出口是被递给 asyncio.to_thread 的（写库是阻塞调用，路由不许为它占住事件循环），
    所以这里认的是「名字为 add_document 的属性引用」而不是 Call：直接调用与作为函数交出去
    两种形状都算同一枚出口，多出来第二枚就红。
    """
    source = (REPO_ROOT / "app/documents/knowledge_ingest.py").read_text(encoding="utf-8")
    refs = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute) and node.attr == SANCTIONED_EXIT
    ]

    assert [ast.unparse(node) for node in refs] == ["retriever.add_document"], refs
    assert scan_source("app/documents/knowledge_ingest.py", source) == [], (
        "既点名了在册出口，又冒出了第二枚写点"
    )


def test_the_route_hands_the_table_to_the_shared_leg_exactly_once() -> None:
    """路由自己不许再叫第二枚写点：upload_excel 里只有一枚 index_dataset_copy。"""
    source = (REPO_ROOT / "app/api/v1/data.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    route = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "upload_excel"
    )
    write_calls = [
        node
        for node in ast.walk(route)
        if isinstance(node, ast.Call)
        and (_legacy_write_call(node) or _called_name(node.func) == SANCTIONED_EXIT)
    ]
    copy_calls = [
        node
        for node in ast.walk(route)
        if isinstance(node, ast.Call) and _called_name(node.func) == "index_dataset_copy"
    ]

    assert write_calls == [], [ast.unparse(node) for node in write_calls]
    assert len(copy_calls) == 1, [ast.unparse(node) for node in copy_calls]


def test_the_new_module_opens_no_database_connection() -> None:
    """第二套入库腿最省事的写法是绕过 handle 自己连库写 SQL：本件把它一并钉掉。"""
    source = (REPO_ROOT / "app/documents/knowledge_ingest.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_attrs = {"connect", "execute", "executemany", "execute_sql", "cursor"}

    hits = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _attr_name(node.func) in forbidden_attrs
    ]
    assert hits == [], hits
    assert "psycopg" not in source, "新模块不许直接摸数据库驱动"


def test_this_file_is_invisible_to_itself() -> None:
    """本件写着十几处 chromadb / PersistentClient 的字面量，扫自己必须零命中。"""
    rel = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()
    source = Path(__file__).resolve().read_text(encoding="utf-8")

    assert scan_source(rel, source) == []


# ==================== 反证：形状必须抓得到 ====================


@pytest.mark.parametrize(
    "lines, expected_kind",
    [
        (["import chromadb"], KIND_IMPORT),
        (["import chromadb as store"], KIND_IMPORT),
        (["from chromadb import PersistentClient"], KIND_IMPORT),
        (["from chromadb.config import Settings"], KIND_IMPORT),
        (["client = chromadb.PersistentClient(path='./chroma_db')"], KIND_CLIENT),
        (["client = store.EphemeralClient()"], KIND_CLIENT),
        (["client = PersistentClient(name='x')"], KIND_CLIENT),
        (["col = client.get_or_create_collection('enterprise_docs')"], KIND_COLLECTION),
        (["collection.add(ids=ids, documents=docs)"], KIND_WRITE),
        (["collection.upsert(ids=ids, documents=docs)"], KIND_WRITE),
        (["self.client.delete(ids=ids)"], KIND_WRITE),
        (["legacy_store.insert(rows)"], KIND_WRITE),
    ],
)
def test_refutation_each_bypass_shape_is_caught(lines, expected_kind) -> None:
    """十二种绕行写法逐枚点名：哪一格松了，本件就在那一格红。"""
    sites = scan_source("app/sneaky.py", _snippet(lines))

    assert [hit.kind for hit in sites] == [expected_kind], sites


def test_refutation_the_sanctioned_exit_is_not_a_violation() -> None:
    """正面对照：retriever.add_document(...) 是唯一的合法出口，扫描器不许把它算成写点。"""
    source = _snippet(["def go(retriever, name, body, level, department):",
                       "    return retriever.add_document(name, body, level, department)"])

    assert scan_source("app/quiet.py", source) == []


def test_refutation_a_second_exit_under_another_name_is_still_caught() -> None:
    """把手改名不改形状：把遗留集合塞进一个叫 kb_store 的字段，写点照样点名。"""
    source = _snippet([
        "class _Mirror:",
        "    def keep(self, rows):",
        "        self.kb_store.add(documents=rows)",
    ])

    assert [hit.kind for hit in scan_source("app/sneaky.py", source)] == [KIND_WRITE]


def test_prose_and_docstrings_are_not_sites() -> None:
    """注释里、docstring 里写着 chromadb 或 collection.add 不算站点——这正是必须用 AST 的理由。"""
    comment_only = _snippet([
        "def plan(retriever):",
        "    # 这里不许换成 chromadb.PersistentClient，也不许 collection.add(...)",
        "    return retriever.add_document('a', 'b', 1, 'd')",
    ])
    docstring_only = _snippet([
        "def plan():",
        "    '''本模块不开 store、不开 client：PersistentClient 一律不许出现。'''",
        "    return None",
    ])

    assert scan_source("app/quiet.py", comment_only) == []
    assert scan_source("app/quiet.py", docstring_only) == []


def test_the_scope_roots_are_the_named_ones() -> None:
    """把手词表与动词词表各是一枚明账：谁往里加一枚，本件就要求它被点名一次。"""
    assert SANCTIONED_EXIT not in WRITE_VERBS, "add_document 不许被当成遗留动词"
    assert "collection" in STORE_HANDLE_NAMES and "client" in STORE_HANDLE_NAMES
    assert {"add", "upsert", "delete"} <= WRITE_VERBS
    assert {"get", "query", "count"}.isdisjoint(WRITE_VERBS), "读动词不算写点"
