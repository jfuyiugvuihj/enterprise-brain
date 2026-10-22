# -*- coding: utf-8 -*-
"""R625 判据①~⑦ —— 停写之后，Chroma 的每一枚写点必须各自有名字、各自的闸门、各自的 id 来源。

被本单顶回来的在册形状是 tests/test_r60_write_path_unique_under_pgvector.py 里那枚
test_stopping_the_write_is_a_switch_and_not_a_deletion：它在 AST 里数 _write_batch 内
collection.add 的枚数，判据写的是 len(handed) >= 2。这句话钉不住任何一枚具体写点的身份——
明天谁在主写路径上再抄一枚 collection.add，枚数只会更满足 >= 2，钉不会红。所以本文件把
"数枚数"换成"逐枚点名"，名册从 AST 现取，判据里一枚行号都不抄（行号会漂，本仓记过多次；
位置只在内部用来判断"谁在谁之前"，从不当成断言值）。

* 身份 = 文件 + 函数限定名 + 动词 + 关键字形状。谁新增、改名或摘掉一枚写点，名册当场对不上，
  报的是那一枚写点的名字，不是一句"数量不对"。
* 闸门 = 到达这一枚调用必须成立／必须不成立的条件名字。条件由语法位置派生：包住它的 if
  （and/or/not 的极性逐枚传播）＋ 它之前任何一枚"进去就 return/raise"的判定。
* id 来源 = 这一枚调用实际读得到的名字。补偿那一枚只许读删除前的 snapshot，读不到本次新写的 id。

判据⑥是本文件对自己的约束：名册不许退化成 "== 3 / == 4" 这种新的数量幻觉。
test_the_roster_is_not_a_count 把这条钉在自己身上——写点原地换身份而枚数不变，名册必须照样红。

判据⑦是禁区：本文件只读 app/** 的源码文本，产品码一字不改；三把反证刀在临时副本上做完就还原，
还原后的 sha256 与刀前逐字节等（读数见交工纸）。

全程离线：不连 PostgreSQL、不起服务、不开 chromadb、不打模型。假腿与装配台复用同族在册件
test_r60_write_path_unique_under_pgvector，不另起一套平行实现。
"""

from __future__ import annotations

import ast
import builtins
import pathlib
from dataclasses import dataclass

import pytest

from app.rag import indexing
from app.rag.retriever import DocumentRetriever

from test_r60_write_path_unique_under_pgvector import (
    DIM,
    LegacyHandle,
    PgTable,
    _assemble,
    legacy_row,
    pg_row,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
APP_DIR = REPO / "app"
R60_FILE = REPO / "tests" / "test_r60_write_path_unique_under_pgvector.py"
RETRIEVER_REL = "app/rag/retriever.py"

#: 遗留目录（chromadb Collection 或离线 _JsonCollection）里会改动作物的动词。
#: 读动词（get/query/count/peek）不在名册里：本单判的是"行落到哪一库"，不是"行从哪一库读"。
WRITE_VERBS = frozenset({"add", "upsert", "update", "put", "insert", "modify", "delete"})
#: 会把新行交给遗留目录的动词——判据③管的就是这一族。
NEW_ROW_VERBS = WRITE_VERBS - {"delete"}
#: R60 的停写判定。任何一枚"新行交给遗留腿"的调用都必须被它挡在False那一侧。
PREDICATE = "_writes_go_to_pgvector"

_IGNORED = {"self", "cls"} | set(dir(builtins))


@dataclass(frozen=True)
class SiteSpec:
    """一枚 Chroma 写点的在册语义：它凭什么存在、什么条件下才写、允许喂哪些名字。"""

    role: str
    why: str
    ids_names: tuple
    allowed_argument_names: tuple
    requires_true: tuple = ()
    requires_false: tuple = ()
    forbids: tuple = ()
    feeds_embeddings: bool = True


def _key(rel, scope, verb, kwargs, positionals=0):
    tail = ", +%dpos" % positionals if positionals else ""
    return "%s::%s::%s(%s%s)" % (rel, scope, verb, ", ".join(kwargs), tail)


_WRITE_BATCH = "DocumentRetriever._write_batch"
_UNDO = "DocumentRetriever._undo_vector_write"

CHROMA_WRITE_ROSTER = {
    _key(RETRIEVER_REL, _WRITE_BATCH, "add", ("documents", "ids", "metadatas")): SiteSpec(
        role="offline",
        why="离线 _JsonCollection 腿：后端不存向量时那枚 JSON 文件就是唯一的库，"
            "文本与元数据照写，向量一枚都不喂（喂了就是 R22 要挡的零向量）。",
        requires_false=("stores_vectors",),
        ids_names=("ids",),
        allowed_argument_names=("documents", "ids", "metadatas"),
        feeds_embeddings=False,
    ),
    _key(RETRIEVER_REL, _WRITE_BATCH, "add",
         ("documents", "embeddings", "ids", "metadatas")): SiteSpec(
        role="primary",
        why="遗留腿正常那支：只有当 PostgreSQL 不是新行的住所（判定为 False）时才接行。"
            "R60 的停写就落在这枚闸门上，代码留着不删＝回滚通路还在。",
        requires_true=("stores_vectors",),
        requires_false=(PREDICATE,),
        ids_names=("ids",),
        allowed_argument_names=("documents", "embeddings", "ids", "metadatas"),
    ),
    _key(RETRIEVER_REL, _UNDO, "delete", ("ids",)): SiteSpec(
        role="compensation",
        why="补偿撤销：只撤本次真写进遗留腿的那批 id。停写态里遗留腿从没写过，"
            "撤它们等于把上一版还留在 Chroma 里的行删掉。",
        requires_true=("written_ids",),
        requires_false=(PREDICATE,),
        ids_names=("written_ids",),
        allowed_argument_names=("written_ids",),
        forbids=("snapshot", "legacy_ids", "stale_ids"),
    ),
    _key(RETRIEVER_REL, _UNDO, "add",
         ("documents", "embeddings", "ids", "metadatas")): SiteSpec(
        role="compensation",
        why="补偿放回：'停写不是删码'唯一的例外通道。只许把删除前 snapshot 里那批旧行原样放回，"
            "不许喂本次新写的 id——喂了它，回滚就成了第二次写入，停写的例外通道就成了后门。",
        requires_true=("stale_deleted", "snapshot"),
        ids_names=("snapshot",),
        allowed_argument_names=("snapshot",),
        forbids=("written_ids", "ids", "documents", "metadatas", "embeddings"),
    ),
    _key(RETRIEVER_REL, "DocumentRetriever.add_document", "delete", ("ids",)): SiteSpec(
        role="primary",
        why="同名重传撤旧行：遗留腿只删它自己持有的那批（legacy_ids）。把并集喂进来就是"
            "判据③点名的孤儿形状——PG 删干净了，Chroma 里的旧行还在被检索。",
        requires_true=("legacy_ids", "stale_ids"),
        ids_names=("legacy_ids",),
        allowed_argument_names=("legacy_ids",),
        forbids=("stale_ids", "pg_ids", "stored_ids"),
    ),
    _key(RETRIEVER_REL, "DocumentRetriever.delete_document", "delete", ("ids",)): SiteSpec(
        role="primary",
        why="删文档撤旧行：与 add_document 同一口径，只删遗留腿持有的那批。",
        requires_true=("legacy_ids",),
        ids_names=("legacy_ids",),
        allowed_argument_names=("legacy_ids",),
        forbids=("stored_ids", "pg_ids", "stale_ids"),
    ),
}

# ------------------------------------------------------------------ AST 派生：身份、闸门、id 来源


def _sense_key(pair):
    """给 (名字, 极性) 一个稳定次序——极性可能是 None（比较式），不能让 sorted() 去比 None。"""
    return (str(pair[1]), pair[0])


def _pairs(test, sense):
    """把一枚条件拆成 (名字, 该名字此刻必须成立吗)。

    sense=True 表示"这枚 if 进去了"，sense=False 表示"这枚 if 没进去才走到下面"。
    and/or/not 的极性逐枚传播；比较式（a == b、x is None）拆不出单枚名字的极性，
    只登记成"问过了这个名字"（polarity=None），宁可少断言，不可假断言。
    """
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return _pairs(test.operand, not sense)
    if isinstance(test, ast.BoolOp):
        same = isinstance(test.op, ast.And) == sense
        out = set()
        for value in test.values:
            if same:
                out |= _pairs(value, sense)
            else:
                out |= {(name, None) for name in _names(value)}
        return out
    if isinstance(test, ast.Compare):
        return {(name, None) for name in _names(test)}
    return {(name, sense) for name in _names(test)}


def _names(node):
    """一棵表达式树里读得到的名字：局部变量名与属性名，去掉 self/cls 与内建。"""
    out = set()
    for item in ast.walk(node):
        if isinstance(item, ast.Name):
            out.add(item.id)
        elif isinstance(item, ast.Attribute):
            out.add(item.attr)
    return {name for name in out if name not in _IGNORED}


def _always_exits(stmts):
    """这一段进去之后出不来（末尾必然 return/raise，或两分支都必然 return/raise）。"""
    if not stmts:
        return False
    last = stmts[-1]
    if isinstance(last, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
        return True
    if isinstance(last, ast.If):
        return bool(last.orelse) and _always_exits(last.body) and _always_exits(last.orelse)
    if isinstance(last, ast.Try):
        return (_always_exits(last.body)
                and all(_always_exits(handler.body) for handler in last.handlers)
                and _always_exits(last.orelse) and _always_exits(last.finalbody))
    return False


def _scope_nodes(container):
    """本作用域里的节点，遇到嵌套函数就停：别名与闸门都不许跨函数借用。"""
    stack = list(ast.iter_child_nodes(container))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _terminal_guards(container):
    """本作用域里所有"进去就出不来"的 if：过得去的人必须先让它为假（或它没进去）。"""
    guards = []
    for node in _scope_nodes(container):
        if isinstance(node, ast.If):
            if _always_exits(node.body):
                guards.append((node, False))     # 进去了就出不来：走到下面 = 这枚条件为假
            if node.orelse and _always_exits(node.orelse):
                guards.append((node, True))      # 没进去才出不来：走到下面 = 这枚条件为真
    return guards


def _starts(node):
    return (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))


def _ends(node):
    return (getattr(node, "end_lineno", 0), getattr(node, "end_col_offset", 0))


def _collection_aliases(container):
    """把 self.collection 起了别名的局部名收走：换名不许躲过名册。"""
    aliases = set()
    for node in _scope_nodes(container):
        value = node.value if isinstance(node, ast.Assign) else None
        if value is None and isinstance(node, ast.AnnAssign):
            value = node.value
        if value is None:
            continue
        source = ast.unparse(value)
        if source == "self.collection" or source.endswith(".collection"):
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                if isinstance(target, ast.Name):
                    aliases.add(target.id)
    return aliases


def _write_verb(call, aliases):
    """这一枚调用是不是打在遗留目录上的写动作；是则返回动词。"""
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return None
    if call.func.attr not in WRITE_VERBS:
        return None
    receiver = ast.unparse(call.func.value)
    if receiver in aliases or receiver.endswith(".collection"):
        return call.func.attr
    if receiver == "collection":          # 别名之后又裸用的那一种
        return call.func.attr
    return None


@dataclass(frozen=True)
class WriteSite:
    """一枚 Chroma 写点的现取读数：名字、闸门、id 来源。行号只用于排序，不进任何判据。"""

    identity: str
    path: str
    scope: str
    verb: str
    kwargs: tuple
    positionals: int
    ids_source: str
    ids_names: frozenset
    argument_names: frozenset
    gate_true: frozenset
    gate_false: frozenset
    guard_true: frozenset
    guard_false: frozenset
    asked: frozenset
    call_source: str

    @property
    def may_feed_ids(self):
        """到达这一枚调用时，判据认为必须成立／必须不成立的条件名字（两支并起来）。"""
        return (self.gate_true | self.guard_true, self.gate_false | self.guard_false)


def _scopes(tree):
    """每个函数节点的限定名（Class.method），供名册当身份用。"""
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parts = []
            current = node
            while current is not None:
                if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    parts.append(current.name)
                current = parent.get(id(current))
            parts.reverse()
            out[id(node)] = ".".join(parts)
    return out


def _visit_body(stmts, gates, out, aliases, scope, rel):
    for stmt in stmts:
        if isinstance(stmt, ast.If):
            _visit_body(stmt.body, gates + sorted(_pairs(stmt.test, True), key=_sense_key),
                        out, aliases, scope, rel)
            _visit_body(stmt.orelse, gates + sorted(_pairs(stmt.test, False), key=_sense_key),
                        out, aliases, scope, rel)
            continue
        if isinstance(stmt, ast.Try):
            for block in ([stmt.body, stmt.orelse, stmt.finalbody]
                          + [handler.body for handler in stmt.handlers]):
                _visit_body(block, gates, out, aliases, scope, rel)
            continue
        if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            _visit_body(stmt.body, gates, out, aliases, scope, rel)
            _visit_body(stmt.orelse, gates, out, aliases, scope, rel)
            continue
        if isinstance(stmt, (ast.With, ast.AsyncWith)):
            _visit_body(stmt.body, gates, out, aliases, scope, rel)
            continue
        if isinstance(stmt, ast.ClassDef):
            _visit_body(stmt.body, gates, out, aliases, scope, rel)
            continue
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue                      # 嵌套定义由 _scopes 那一轮各自点名
        for call in ast.walk(stmt):
            verb = _write_verb(call, aliases)
            if verb is None:
                continue
            out.append((scope, rel, gates, call, verb))


def chroma_write_sites(source, rel):
    """从源码现取本文件里每一枚 Chroma 写点：身份 + 闸门 + 允许读到的名字。"""
    tree = ast.parse(source)
    scopes = _scopes(tree)
    found = []
    containers = [tree] + [item for item in ast.walk(tree)
                           if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for node in containers:
        scope = "<module>" if node is tree else scopes[id(node)]
        aliases = _collection_aliases(node)
        guards = _terminal_guards(node)
        sites = []
        _visit_body(node.body, [], sites, aliases, scope, rel)
        for site_scope, site_rel, gates, call, verb in sites:
            kwargs = tuple(sorted(keyword.arg or "*" for keyword in call.keywords))
            ids_node = next((keyword.value for keyword in call.keywords if keyword.arg == "ids"),
                            call.args[0] if call.args else None)
            argument_names = set()
            for argument in list(call.args) + [keyword.value for keyword in call.keywords]:
                argument_names |= _names(argument)
            gate_true = {name for name, sense in gates if sense is True}
            gate_false = {name for name, sense in gates if sense is False}
            asked = {name for name, sense in gates if sense is None}
            guard_true, guard_false = set(), set()
            start = _starts(call)
            for guard, sense in guards:
                if _ends(guard) >= start:
                    continue              # 在它之后，或者把它整个包住——都不算"先过这道门"
                for name, pol in _pairs(guard.test, sense):
                    if pol is True:
                        guard_true.add(name)
                    elif pol is False:
                        guard_false.add(name)
                    else:
                        asked.add(name)
            found.append(WriteSite(
                identity=_key(site_rel, site_scope, verb, kwargs, len(call.args)),
                path=site_rel, scope=site_scope, verb=verb, kwargs=kwargs,
                positionals=len(call.args),
                ids_source=ast.unparse(ids_node) if ids_node is not None else "<无 ids 参数>",
                ids_names=frozenset(_names(ids_node)) if ids_node is not None else frozenset(),
                argument_names=frozenset(argument_names),
                gate_true=frozenset(gate_true), gate_false=frozenset(gate_false),
                guard_true=frozenset(guard_true), guard_false=frozenset(guard_false),
                asked=frozenset(asked),
                call_source=ast.unparse(call),
            ))
    return tuple(found)


def app_write_sites():
    """整棵 app/ 的 Chroma 写点：新代码在别的文件里加写点，一样要点名。"""
    sites = []
    for path in sorted(APP_DIR.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "collection" not in source:
            continue
        sites.extend(chroma_write_sites(source, path.resolve().relative_to(REPO).as_posix()))
    return tuple(sites)

# ------------------------------------------------------------------- 逐枚点名的四格判据


def _retriever_source():
    """现读产品码。本文件只读不写：判据⑦——app/** 是禁区。"""
    return (REPO / RETRIEVER_REL).read_text(encoding="utf-8")


def _render(site):
    truthy, falsy = site.may_feed_ids
    return ("%s\n        现取调用 = %s\n        现取闸门：必须真 %s / 必须假 %s / 只问到名字 %s\n"
            "        现取 id：%s（这一枚调用读得到的名字：%s）"
            % (site.identity, " ".join(site.call_source.split()),
               sorted(truthy), sorted(falsy), sorted(site.asked),
               site.ids_source, sorted(site.argument_names)))


def _identity_findings(sites):
    """名册对账：多出来的、被摘掉的、同一身份撞成两枚的。全是名字，不是数字。"""
    identities = [site.identity for site in sites]
    by_identity = {}
    for site in sites:
        by_identity.setdefault(site.identity, site)
    findings = []
    for item in sorted(set(identities) - set(CHROMA_WRITE_ROSTER)):
        findings.append("名册之外多出一枚 Chroma 写点：" + _render(by_identity[item])
                        + "\n        它凭什么存在？先说清「什么条件下允许写、允许喂哪些 id」，再进名册。")
    for item in sorted(set(identities) & set(CHROMA_WRITE_ROSTER)):
        if identities.count(item) > 1:
            findings.append("同一身份出现了两枚以上的写点：%s —— 名册按身份逐枚点名，撞名之后再也点不出"
                            "是谁在写、写的是哪一批 id。" % item)
    for item in sorted(set(CHROMA_WRITE_ROSTER) - set(identities)):
        findings.append("名册在册的写点在码上找不到了：%s\n        在册理由：%s\n"
                        "        停写靠的是判定，不是把这枚写点摘掉——摘掉就把回滚通路拆了（判据②）。"
                        % (item, CHROMA_WRITE_ROSTER[item].why))
    return findings


def _gate_findings(sites):
    """每一枚写点各自的闸门：在册要求与现取读数逐枚对，不许用一句总数糊过去。"""
    findings = []
    for site in sites:
        spec = CHROMA_WRITE_ROSTER.get(site.identity)
        if spec is None:
            continue
        truthy, falsy = site.may_feed_ids
        lack_true = [name for name in spec.requires_true if name not in truthy]
        lack_false = [name for name in spec.requires_false if name not in falsy]
        if lack_true or lack_false:
            findings.append("%s\n        在册闸门：必须真 %s / 必须假 %s%s\n        %s"
                            % (site.identity, sorted(spec.requires_true), sorted(spec.requires_false),
                               "（在册角色：%s）" % spec.role if spec.role else "",
                               _render(site)))
    return findings


def _id_source_findings(sites):
    """每一枚写点允许喂哪些 id：白名单、必取之处、禁地，逐枚点名。"""
    findings = []
    for site in sites:
        spec = CHROMA_WRITE_ROSTER.get(site.identity)
        if spec is None:
            continue
        problems = []
        smuggled = sorted(site.argument_names - set(spec.allowed_argument_names))
        if smuggled:
            problems.append("这一枚只许读 %s，却读到了 %s"
                            % (sorted(spec.allowed_argument_names), smuggled))
        absent = sorted(name for name in spec.ids_names if name not in site.ids_names)
        if absent:
            problems.append("ids 没取自 %s（现取 ids=%s）" % (absent, site.ids_source))
        forbidden = sorted(name for name in spec.forbids if name in site.argument_names or name in site.ids_names)
        if forbidden:
            problems.append("喂进了名册点名的禁地 %s" % forbidden)
        if site.verb not in NEW_ROW_VERBS:
            has_embeddings = spec.feeds_embeddings      # delete 那一族本来就没有向量可喂
        else:
            has_embeddings = "embeddings" in site.kwargs or "embeddings" in site.argument_names
        if has_embeddings != spec.feeds_embeddings:
            problems.append("向量这一格与在册语义相反：现取%s" % ("带 embeddings" if has_embeddings
                                                               else "不带 embeddings"))
        if problems:
            findings.append("%s\n        %s\n        %s"
                            % (site.identity, "\n        ".join(problems), _render(site)))
    return findings


def _primary_leg_findings(sites):
    """判据③的形状：任何一枚"把新行交给遗留腿"的写点，都必须先过停写判定那一道门。

    例外只有两支，各自另有专钉：离线 _JsonCollection（后端根本不存向量，那枚 JSON 文件就是
    唯一的库）与补偿放回（"停写不是删码"唯一允许的例外通道，只许喂 snapshot 里那批旧 id）。
    """
    findings = []
    for site in sites:
        if site.verb not in NEW_ROW_VERBS:
            continue
        spec = CHROMA_WRITE_ROSTER.get(site.identity)
        _truthy, falsy = site.may_feed_ids
        if spec is not None and spec.role == "compensation":
            continue
        if PREDICATE in falsy or "stores_vectors" in falsy:
            continue
        findings.append("%s\n        这一枚把新行交给遗留腿，却没有任何判定挡着它：INDEX_BACKEND=pgvector "
                        "时它照样接行，停写就破了。%s" % (site.identity, _render(site)))
    return findings


def write_site_findings(sites=None):
    """三格语义判据一次算完，返回逐枚点名的红句清单；空清单＝全绿。

    公开给 tests/test_r60_write_path_unique_under_pgvector.py 那枚在册钉复用：同一份名册，
    不在两枚件里各写一套判据。
    """
    sites = tuple(app_write_sites() if sites is None else sites)
    return (_identity_findings(sites) + _gate_findings(sites) + _id_source_findings(sites)
            + _primary_leg_findings(sites))


def _red(findings):
    return "\n".join(["", ""] + ["  [%d/%d] %s" % (index + 1, len(findings), item)
                                for index, item in enumerate(findings)])

# --------------------------------------------------------------- 判据①：名册、闸门、id 来源、主写腿


def test_chroma_write_sites_are_a_named_roster():
    """判据①：遗留腿的写点是一张点名册，不是一句"不少于几枚"。

    在册那枚钉写的是 len(collection.add 调用) >= 2：明天谁在主写路径上再抄一枚 add，枚数只会
    更满足这句话。这里换成身份对账——多出来的、被摘掉的、撞名的，逐枚点名。
    """
    findings = _identity_findings(app_write_sites())
    assert findings == [], "Chroma 写点名册对不上：" + _red(findings)


def test_each_write_site_declares_its_own_gate():
    """判据①后半：每一枚写点要指名"它在什么条件下允许写"，条件从语法位置派生。"""
    findings = _gate_findings(app_write_sites())
    assert findings == [], "有写点的闸门与在册语义对不上：" + _red(findings)


def test_each_write_site_declares_which_ids_it_may_feed():
    """判据①后半＋②：每一枚写点要指名"允许喂哪些 id"，白名单之外就是假账。"""
    findings = _id_source_findings(app_write_sites())
    assert findings == [], "有写点喂了不该喂的 id：" + _red(findings)


def test_no_new_row_write_is_reachable_while_pgvector_is_primary():
    """判据③：pgvector 主写时，任何一枚"新行交给遗留腿"的写点都必须先被停写判定挡住。

    例外只有两支，各自另有专钉：离线 _JsonCollection（后端不存向量）与补偿放回（只喂 snapshot）。
    """
    findings = _primary_leg_findings(app_write_sites())
    assert findings == [], "主写路径上出现了没有闸门的 Chroma 写点：" + _red(findings)


# ------------------------------------------------------------------- 判据②：补偿放回不是后门

_COMPENSATION_ADD = _key(RETRIEVER_REL, _UNDO, "add",
                         ("documents", "embeddings", "ids", "metadatas"))
_COMPENSATION_DELETE = _key(RETRIEVER_REL, _UNDO, "delete", ("ids",))


def test_the_compensation_channel_reads_the_snapshot_and_nothing_else():
    """判据②静态面：那枚例外通道只许喂删除前 snapshot 里的旧 id，一枚本次新写的都不许碰。"""
    sites = {site.identity: site for site in app_write_sites()}
    site = sites.get(_COMPENSATION_ADD)
    assert site is not None, (
        "补偿放回那枚写点不在码上了（在册身份 %s）—— 停写的例外通道没了，回滚就成了第二次丢数据"
        % _COMPENSATION_ADD)
    truthy, _falsy = site.may_feed_ids
    assert "stale_deleted" in truthy, (
        "补偿放回不再问「这次到底删过没有」了：%s —— 没删过就 add，回滚自己就成了一次写入"
        % _render(site))
    assert "written_ids" not in site.argument_names | site.ids_names, (
        "补偿通道读得到本次新写的 id —— 例外通道成了后门：" + _render(site))
    assert site.ids_names == frozenset({"snapshot"}), (
        "补偿放回的 ids 不再只来自删除前的快照：" + _render(site))
    assert site.argument_names == frozenset({"snapshot"}), (
        "补偿放回喂的正文/元数据/向量已不是快照里那一套（重算或换成新写的都是假还原）：" + _render(site))


def test_the_compensation_delete_only_undoes_a_write_that_happened():
    """判据②静态面：撤销那一枚只许撤本次真写过的 id，且必须被停写判定挡着。"""
    sites = {site.identity: site for site in app_write_sites()}
    site = sites.get(_COMPENSATION_DELETE)
    assert site is not None, "补偿撤销那枚写点不在码上了（在册身份 %s）" % _COMPENSATION_DELETE
    _truthy, falsy = site.may_feed_ids
    assert "written_ids" in site.ids_names, (
        "补偿撤销撤的不是本次写入的那批 id：" + _render(site))
    assert PREDICATE in falsy, (
        "补偿撤销不再问停写判定：停写态里遗留腿从没写过这批行，撤它就是删掉上一版还活着的索引"
        + _render(site))


def test_the_compensation_puts_back_the_old_rows_and_not_the_new_ones(monkeypatch):
    """判据②现跑面：回滚交给遗留腿的，只能是 snapshot 里那批旧行、那一版向量。"""
    legacy = LegacyHandle([legacy_row("b.txt_0", document="上一版的正文", embedding=[0.5] * DIM)])
    instance, _connection, _table = _assemble(
        monkeypatch, backend=indexing.PGVECTOR_BACKEND, legacy=legacy)
    snapshot = instance._vector_snapshot(["b.txt_0"])
    mirror = instance._open_vector_mirror()
    new_ids = ["b.txt_0_v2", "b.txt_1_v2"]

    instance._undo_vector_write(mirror, new_ids, snapshot, stale_deleted=True)

    assert legacy.adds == [["b.txt_0"]], (
        "补偿放回喂的不是删除前那批旧 id：现取 %s，而本次新写的是 %s" % (legacy.adds, new_ids))
    assert legacy.rows["b.txt_0"]["document"] == "上一版的正文", "放回去的正文不是快照里那一版"
    assert legacy.rows["b.txt_0"]["embedding"] == [0.5] * DIM, "放回的是快照里那一枚向量，不是重算的"
    assert not set(new_ids) & set(legacy.rows), "本次新写的 id 借补偿通道进了遗留腿 = 后门"
    assert legacy.deletes == [], "停写态里遗留腿从没写过这批行，撤一次没发生过的写入＝自己制造删除"


def test_the_compensation_stays_shut_when_nothing_was_deleted(monkeypatch):
    """判据②现跑面：没删过就不许 add——回滚不许自己变成一次写入。"""
    legacy = LegacyHandle([legacy_row("b.txt_0", document="上一版的正文", embedding=[0.5] * DIM)])
    instance, _connection, _table = _assemble(
        monkeypatch, backend=indexing.PGVECTOR_BACKEND, legacy=legacy)
    snapshot = instance._vector_snapshot(["b.txt_0"])

    instance._undo_vector_write(instance._open_vector_mirror(), [], snapshot, stale_deleted=False)

    assert legacy.adds == [], "一次都没删过，补偿却放回了行：%s" % legacy.adds
    assert legacy.deletes == []


# --------------------------------------------- 判据①点名到 delete：遗留腿只删它自己持有的那批


def test_the_legacy_delete_leg_never_receives_pg_only_ids(monkeypatch):
    """删文档那一腿：只住在 PG 的 id 不许喂给遗留目录（名册里的 forbids 现跑一遍）。"""
    legacy = LegacyHandle([legacy_row("a.txt_0"), legacy_row("a.txt_1")])
    table = PgTable([pg_row("a.txt_9", "a.txt", 9, "九", "sha9")])
    instance, _connection, table = _assemble(
        monkeypatch, backend=indexing.PGVECTOR_BACKEND, legacy=legacy, table=table)

    instance.delete_document("a.txt")

    assert legacy.deletes == [["a.txt_0", "a.txt_1"]], (
        "遗留腿收到的删除名单不是它自己持有的那批：现取 %s" % legacy.deletes)
    assert "a.txt_9" not in [item for batch in legacy.deletes for item in batch]
    assert table.rows == {}, "PG 那一腿删的必须是两腿并集，它持有的行一枚都不许留下"


def test_the_reupload_legacy_delete_also_feeds_only_its_own_rows(monkeypatch):
    """同名重传那一腿与删文档同一口径：喂并集就是把孤儿留在 Chroma 里。"""
    legacy = LegacyHandle([legacy_row("a.txt_0")])
    table = PgTable([pg_row("a.txt_9", "a.txt", 9, "九", "sha9")])
    instance, _connection, _table = _assemble(
        monkeypatch, backend=indexing.PGVECTOR_BACKEND, legacy=legacy, table=table)

    ok, _message = instance.add_document("a.txt", "一\n二")

    assert ok is True
    assert legacy.deletes == [["a.txt_0"]], (
        "同名重传时遗留腿被喂了不属于它的名单：现取 %s" % legacy.deletes)

# --------------------------------- 判据⑤：停写判定那三枚相与条件，摘掉任意一枚都必须红

PREDICATE_TERMS = ("stores_vectors", "dual_write_enabled", "pgvector_writes_are_primary")

#: 每一枚条件单独摆成"只有它为假、其余两枚为真"的那一档。
_TERM_SETUPS = {
    "stores_vectors": dict(backend=indexing.PGVECTOR_BACKEND, dual="on", stores=False),
    "dual_write_enabled": dict(backend=indexing.PGVECTOR_BACKEND, dual="off", stores=True),
    "pgvector_writes_are_primary": dict(backend=indexing.INDEX_BACKEND_DEFAULT, dual="on", stores=True),
}


def _predicate_controlling_names(source):
    """判定函数里真正挡着答复的名字：早退 if 的条件 + 返回值那一段的布尔操作数。

    只写在 docstring 里、或者写了却不在答复链上的名字不算——摘掉那一枚条件正是这两种形状。
    """
    tree = ast.parse(source)
    func = next((node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef) and node.name == PREDICATE), None)
    assert func is not None, "%s 整枚函数都不在了 —— 停写已经不是靠判定这句话" % PREDICATE
    names = set()
    for node in ast.walk(func):
        if isinstance(node, ast.If) and _always_exits(node.body):
            names |= {name for name, _sense in _pairs(node.test, True)}
        elif isinstance(node, ast.Return) and node.value is not None:
            names |= {name for name, _sense in _pairs(node.value, True)}
    return names


@pytest.mark.parametrize("term", PREDICATE_TERMS)
def test_dropping_one_term_of_the_write_predicate_is_a_lie(term, monkeypatch):
    """判据⑤：本单立项的起因。三枚条件与成的判定，摘掉任意一枚它就当着人说不存在的事实。

    在册那枚件（17 条）对这一形全绿——它数的是 collection.add 的枚数。这里现取两格：判定必须
    答 False；判定答 False 必须真的让「这份文档的行住在哪一库」那一句不去问 PostgreSQL。
    """
    setup = _TERM_SETUPS[term]
    instance, connection, _table = _assemble(
        monkeypatch, backend=setup["backend"], dual=setup["dual"])
    monkeypatch.setattr(DocumentRetriever, "stores_vectors", property(lambda self: setup["stores"]))

    assert instance._writes_go_to_pgvector() is False, (
        "%s 这一枚条件已经不挡住判定了：它答 True 的时候 PostgreSQL 根本不是新行的住所，"
        "「停写靠判定」就退化成「停写靠猜」" % term)
    instance._document_rows_by_leg("a.txt")
    assert "doc_rows" not in connection.log, (
        "%s 为假而判定仍答 True，于是删除要先问 PostgreSQL 有哪些行 —— 那一腿这本账是空的，"
        "报出去的是一次没 locating 成功的删除" % term)
    metadata = {"filename": "a.txt", "chunk_index": 0, "hash": "r625",
                "classification": 1, "department": ""}
    instance._write_batch(["a.txt_0"], ["一"], [metadata], [[0.25] * DIM],
                          mirror=instance._open_vector_mirror())
    assert instance.collection.adds == [["a.txt_0"]], (
        "%s 这一枚条件被摘掉之后，本批行既没落 PG 也没落遗留腿 = 零写："
        "客户上传的文档在两个库里都不存在（现取 adds=%s）" % (term, instance.collection.adds))


def test_the_three_terms_together_really_do_flip_the_leg(monkeypatch):
    """正控：三枚条件全成立时判定答 True、那句问句确实发得出去——不然上面的反证全是空转。"""
    instance, connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND)
    assert instance._writes_go_to_pgvector() is True
    instance._document_rows_by_leg("a.txt")
    assert "doc_rows" in connection.log, "问句没发出去：这一格压根量不到，反证刀也就量不到"


@pytest.mark.parametrize("term", PREDICATE_TERMS)
def test_each_term_still_holds_a_controlling_position(term):
    """判据⑤静态面：三枚条件都还在答复链上，不是只当注释活着。"""
    names = _predicate_controlling_names(_retriever_source())
    assert term in names, (
        "判定 %s 的答复链上不见了 %s（现取控制位名字：%s）—— 三枚与条件少一枚，"
        "「停写靠判定」就没有载体了" % (PREDICATE, term, sorted(names)))


# ------------------------------------------------- 判据⑥自证：这枚钉不许是又一枚数量幻觉


def _function(tree, name):
    found = next((node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == name), None)
    assert found is not None, "找不到函数 %s —— 这枚反证刀的前提没了，先改刀再改钉" % name
    return found


def _mutate_source(source, mutate):
    tree = ast.parse(source)
    assert mutate(tree) is tree, "变体必须原地改 AST 并交回同一枚树"
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def _variant_rename_write_batch(tree):
    """形一：把整枚宿主函数改名（代码搬家）。枚数一枚不少，身份全变。"""
    _function(tree, "_write_batch").name = "_write_batch_moved_elsewhere"
    return tree


def _variant_neutralise_guard(tree):
    """形二：把停写判定中和成 if False。身份不变、枚数不变，只有闸门变了。"""
    func = _function(tree, "_write_batch")
    for node in ast.walk(func):
        if isinstance(node, ast.If) and PREDICATE in ast.unparse(node.test):
            node.test = ast.Constant(value=False)
            return tree
    raise AssertionError("找不到 if self._writes_go_to_pgvector(): 那道闸门 —— 本单判的那格已经变了")


def _variant_extra_write(tree):
    """形三：在 pgvector 主写路径上多插一枚 Chroma 写点（＝反证刀 A 的静态形）。"""
    func = _function(tree, "_write_batch")
    for node in ast.walk(func):
        if isinstance(node, ast.If) and "mirror" in ast.unparse(node.test):
            extra = ast.parse("self.collection.add(ids=ids)").body[0]
            ast.copy_location(extra, node.body[0])
            node.body.insert(0, extra)
            return tree
    raise AssertionError("找不到 if mirror is not None 那一道分支 —— 刀先磨不利，别拿去砍钉")


def _legacy_numeric_verdict(source):
    """在册那枚旧钉的判据本身：_write_batch 里 collection.add 的枚数，>= 2 就算绿。"""
    tree = ast.parse(source)
    func = next((node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef) and node.name == "_write_batch"), None)
    if func is None:
        return None
    return sum(1 for item in ast.walk(func)
               if isinstance(item, ast.Call) and ast.unparse(item.func).endswith("collection.add"))


def test_the_verdict_tracks_identity_and_gate_not_quantity():
    """判据⑥：不许把一个 >= 2 换成另一个 == 3。枚数不变而身份或闸门变了，钉必须照样红。"""
    source = _retriever_source()
    baseline = chroma_write_sites(source, RETRIEVER_REL)
    findings = write_site_findings(baseline)
    assert findings == [], "真码上名册先要绿，反证才量得准：" + _red(findings)

    renamed = chroma_write_sites(_mutate_source(source, _variant_rename_write_batch), RETRIEVER_REL)
    assert {item.identity for item in renamed} != {item.identity for item in baseline}
    assert _identity_findings(renamed), "整枚宿主函数搬家改名，名册没红——那它还是在数枚数"

    neutralised_source = _mutate_source(source, _variant_neutralise_guard)
    neutralised = chroma_write_sites(neutralised_source, RETRIEVER_REL)
    assert {item.identity for item in neutralised} == {item.identity for item in baseline}, (
        "这形本该只改闸门不改身份")
    assert _primary_leg_findings(neutralised), "停写判定被中和成 if False，主写路径上没闸门的 add 没红"
    assert _gate_findings(neutralised), "停写判定被中和成 if False，在册闸门要求没红"

    extra_source = _mutate_source(source, _variant_extra_write)
    extra = chroma_write_sites(extra_source, RETRIEVER_REL)
    assert _identity_findings(extra), "主写路径上新增一枚 Chroma 写点，名册没点名"
    assert _primary_leg_findings(extra), "主写路径上新增一枚 Chroma 写点，判据③没红"

    # 反向凭据（本单立项的形状）：后两形在旧那句 >= 2 上照样绿——数量钉量不到，名册量得到。
    assert _legacy_numeric_verdict(neutralised_source) >= 2
    assert _legacy_numeric_verdict(extra_source) >= 2


def _test_function_in(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == name)


def _numeric_comparisons(func):
    """这枚判据里"和数字比"的形状——正是 >= 2 那一族的化石。"""
    out = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Compare):
            continue
        for operand in [node.left] + list(node.comparators):
            value = operand.value if isinstance(operand, ast.Constant) else None
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out.append(ast.unparse(node))
                break
    return out


_ROSTER_JUDGMENTS = (
    "test_chroma_write_sites_are_a_named_roster",
    "test_each_write_site_declares_its_own_gate",
    "test_each_write_site_declares_which_ids_it_may_feed",
    "test_no_new_row_write_is_reachable_while_pgvector_is_primary",
)


@pytest.mark.parametrize("name", _ROSTER_JUDGMENTS)
def test_a_roster_judgment_holds_no_number(name):
    """判据⑥：本单换成的这四格判据里，不许再长出"拿数量当判据"的形状。"""
    verdicts = _numeric_comparisons(_test_function_in(pathlib.Path(__file__), name))
    assert verdicts == [], (
        "%s 里又长出了数量判据 %s —— 那正是本单要拆掉的东西" % (name, verdicts))


def test_the_registered_count_pin_is_replaced_by_the_roster():
    """判据①落地凭据：在册那格已经改成逐枚点名，而且不再和数字比。"""
    func = _test_function_in(R60_FILE, "test_stopping_the_write_is_a_switch_and_not_a_deletion")
    assert "write_site_findings" in ast.unparse(func), (
        "那一格还在自己数 collection.add 的枚数，本单判据①没落地：" + ast.unparse(func))
    verdicts = _numeric_comparisons(func)
    assert verdicts == [], "那一格还留着拿数量当判据的形状：%s" % verdicts