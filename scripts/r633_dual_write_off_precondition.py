#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R633 —— 回答「把 VECTOR_DUAL_WRITE 关掉会掉什么」的**只读**前置量具。

它存在的理由（本单开工第一步现读到的形状，不是转述）：计划书 §15 与退役路径表 §4 把
`VECTOR_DUAL_WRITE` 当「双写开关」，而 app/rag/pg_store.py:175 `dual_write_enabled()` 自己的
第一行写的是 **"Is the PostgreSQL leg on?"** —— 这一枚旋钮管的是**整条 PG 腿在不在**，
不是「要不要顺手多写一份」。它一关：

* 写侧：`_writes_go_to_pgvector()` 少一枚合取项即为假 ⇒ 停写判定打开，遗留目录**重新接新行**；
* 读侧：`read_topk()` / `read_corpus()` 与目录问句 `_document_leg_connection()` 都拿同一枚
  `vector_mirror()` 当唯一开口，拿不到腿就按 `REASON_VECTOR_READ_WITHOUT_DUAL_WRITE` **拒答**；
* 消费侧：那两句拒答被上一层 `except` 吞成 `None`，答复改由 `self.collection.query()` 给出。

所以「停双写」不是一格可以照着退役表往下做的动作，它一次同时**退回写**与**退回读**。
本量具把这件事变成一枚会红、可复跑的读数，而不每班手写一遍。

三面各量什么（全部派生自 AST 与库，纸上一个行号、一个枚数都不抄）：
  1. switch —— 两把旋钮的现读答复（`dual_write_enabled()` / `read_backend()` /
     `pgvector_writes_are_primary()`），以及 `--env-file` 给出的部署声明原文（不在位就报未取数）；
  2. sites  —— 逐枚点名 Chroma 变异写点：名册、闸门、id 来源**一律复用在册件**
     tests/test_r625_chroma_write_sites_are_named_one_by_one.py（它把「数枚数」换成了「逐枚点名」，
     同族病：`collection.add` 字面 4 处里有 1 枚在 docstring）。本文件一枚写点清单都没有；
  3. corpus —— PG 侧 `chunk_vectors` 与遗留引擎侧 collection 的语料面差集（vector_id 集合、
     枚数、宽度、`index_version_id` 空值、以及「关掉双写会整篇消失的文档」）。

🔴 连库那一层的规矩（本单不许总控之外的任何人碰生产）：
* `--database-url` / `--chroma-dir` / `--snapshot-from` 全部可注入，**没有默认卷**——
  绝不学 compare_vector_recall 留一枚会按 cwd 落进工作树的 `./chroma_db`（R134 那枚病灶）；
* PG 侧只走 scripts/compare_vector_recall.py 的 `connect_read_only()`，并且连上之后**自己再验一次**
  `SHOW transaction_read_only`，不是 on 就按前置不满足收，不产出任何语料结论；
* 库名不在沙盒名册（`eb_r59_sandbox` 及 `eb_r*_sandbox` / `eb_r*_drill` 那一族）之内时，
  必须同时给 `--window-owner <谁开的窗>`，否则当场拒。生产那一遍**由总控开窗跑**，本席没跑；
* 遗留引擎那一侧一律按 r626 的快照口径读副本（复制源可以是现役卷，打开的目标绝不可以），
  开库前后各做一次源目录字节清单，不等就按前置不满足收。

退出码（写死在 epilog，与 R269「1 号只由差异发出」同口径）：
  0 = 三面全量到 且 没有任何一条发现 ⇒ 「停双写」现在可翻
  1 = 跑成了，且**检出发现**（关掉双写会掉功能/会留下删不掉的行）⇒ 不可翻。这个码只允许由这一族发出
  2 = 前置不满足 **或本量具的读数不可信**（名册与在册件对不上、只读事务设不上、目录是现役卷、
      库名不在沙盒又没给开窗责任人，以及量具自身任何异常）；stderr 首行带「[前置不满足] 」
  3 = 静态两面量到且无发现，但语料面未取数（未给 --database-url / --chroma-dir| --snapshot-from）
      ⇒ 不足以说「可翻」，只能说「这一遍没量全」
优先级：2 > 1 > 3 > 0。

只读纪律：本文件不发一条 INSERT/UPDATE/DELETE/CREATE/DROP，不动容器、不打模型、不改任何在册文件；
产物一律落仓外（`--out-dir` 缺省落在系统临时目录，指进仓内当场拒）。
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rag import indexing, pg_store  # noqa: E402  -- 上面刚插好 sys.path

ROSTER_REL = Path("tests") / "test_r625_chroma_write_sites_are_named_one_by_one.py"
PROBE_REL = Path("scripts") / "r626_legacy_engine_silent_empty_probe.py"
RETRIEVER_REL = "app/rag/retriever.py"
PG_STORE_REL = "app/rag/pg_store.py"

#: 停写判定那一句的名字。名字在册（app/rag/retriever.py 与 R625 名册件同用这一个），行号不抄。
PREDICATE = "_writes_go_to_pgvector"
#: 判定必须由这几枚条件与成，一枚都不许少：少一枚，"关掉这枚旋钮会掉什么"就换了问题。
SWITCH_TERM = "dual_write_enabled"
BACKEND_TERM = "pgvector_writes_are_primary"
STORES_TERM = "stores_vectors"
PREDICATE_TERMS = (SWITCH_TERM, BACKEND_TERM)
#: 「这份文档的行住在哪一库」那一句问句的名字，同样只按名字找。
DOC_ROWS_QUESTION = "_document_rows_by_leg"
#: 关掉双写后读腿与目录问句拒答时打出的稳定码（写在 pg_store 里的那一枚常量名）。
SWITCH_REASON_CONSTANT = "REASON_VECTOR_READ_WITHOUT_DUAL_WRITE"
#: 两条腿唯一的开口：拿不到它就没有 PG 腿。
MIRROR_FACTORY = "vector_mirror"
#: 交回那条腿的两个名字（写侧自己包了一层，两处都算）。除此之外的变量名一律从赋值现取。
LEG_PRODUCERS = (MIRROR_FACTORY, "_open_vector_mirror")
#: 遗留目录的**读**动词。本量具这一面判的是「答复从哪一库给」，与 R625 管变异写点不是同一问句。
LEGACY_RECEIPT_VERBS = frozenset({"get", "query", "count"})

EXIT_CAN_FLIP = 0
EXIT_CANNOT_FLIP = 1
EXIT_PRECONDITION = 2
EXIT_STATIC_ONLY = 3
#: 与 scripts/compare_vector_recall.py:59 同一串值，由 tests/test_r633_* 钉死，谁改一边就红。
PRECONDITION_PREFIX = "[前置不满足] "

#: 允许随手连的库名：沙盒与演练库那一族。生产库名一律要开窗责任人。
SANDBOX_DATABASES = ("eb_r59_sandbox",)
_SANDBOX_DATABASE_SHAPE = re.compile(r"^eb_r\w*_(sandbox|drill)\Z")
READ_ONLY_PROBE_SQL = "SHOW transaction_read_only"

#: 逐枚点名的发现（红句）的代码名。牙按这些名字判「哪一格红」，不按句子措辞。
CODES = (
    "predicate_missing",
    "predicate_term_missing",
    "chroma_write_gate_reopens",
    "compensation_needs_a_leg_it_wont_have",
    "delete_set_blind_to_pg_only_rows",
    "question_rehomes_to_legacy_store",
    "read_leg_waits_for_chroma_receipt",
    "corpus_gap",
    "roster_cross_check_failed",
)


def fail_precondition(reason: str):
    """前置不满足 / 读数不可信的唯一出口：原因进 stderr，退出码 2，绝不借用 1。"""
    print(PRECONDITION_PREFIX + str(reason), file=sys.stderr, flush=True)
    raise SystemExit(EXIT_PRECONDITION)


# ------------------------------------------------------------------ 在册件装载（不抄第二份）

_MODULES: dict = {}


def _load(path: Path, module_name: str, extra_sys_path=None):
    if not path.is_file():
        fail_precondition("在册件不在位：" + str(path) + "（本量具不复制第二份实现）")
    for extra in extra_sys_path or []:
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    cached = _MODULES.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    # 先进 sys.modules 再 exec：dataclasses 解析注解时按 __module__ 回查模块字典，
    # 装载一枚带 @dataclass 的在册件（R625 的 SiteSpec / WriteSite）少了这一步就当场
    # AttributeError: 'NoneType' object has no attribute '__dict__'。
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    _MODULES[module_name] = module
    return module


def load_roster():
    """装载 R625 的写点名册件：名册、闸门、id 来源、三格判据全部从它那儿读回来。

    它自己 `from test_r60_write_path_unique_under_pgvector import ...`，所以 tests/ 必须先进
    sys.path——这一层是它的装载前提，不是本量具的实现。
    """
    return _load(ROOT / ROSTER_REL, "r633_write_site_roster", extra_sys_path=[ROOT / "tests"])


def load_probe():
    """装载 r626 的快照口径件：`--chroma-dir` 的现役卷判据与前后字节清单都从它那儿借。"""
    return _load(ROOT / PROBE_REL, "r633_legacy_snapshot_probe")


# ------------------------------------------------------------------------ AST 小工具


def _functions(tree):
    return [node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _function_by_name(tree, name):
    for node in _functions(tree):
        if node.name == name:
            return node
    return None


def _unparenthesised(value):
    """`bool(a and b)` 与 `a and b` 是同一句话；脱掉外层 bool() 再数合取项。"""
    if (isinstance(value, ast.Call) and not value.keywords
            and ast.unparse(value.func) == "bool" and len(value.args) == 1):
        return value.args[0]
    return value


def _calls_inside(node):
    """这一段落里发出去的调用名，两种写法都收：模块内裸名（`vector_mirror(...)`）与带点的（`pg_store.read_topk(...)`）。

    只认带点那一种会漏掉 pg_store 自己文件里的 helper 调用：`_document_leg_connection()` 的两位
    经手人会被派生成「不存在」，问句面从此少两条腿。
    """
    out = set()
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        if isinstance(item.func, ast.Attribute):
            out.add(ast.unparse(item.func))
        elif isinstance(item.func, ast.Name):
            out.add(item.func.id)
    return out


def _handler_swallows(handler):
    """except 支里没有任何 raise ⇒ 这次失败被吞掉了（答复得由别人给）。"""
    return not any(isinstance(node, ast.Raise) for node in ast.walk(handler))


def _legacy_receipt_calls(func):
    """这一枚函数里打在遗留目录上的**读**调用：`self.collection.query(...)` / `collection.get(...)`。"""
    out = []
    for node in ast.walk(func):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in LEGACY_RECEIPT_VERBS:
            continue
        receiver = ast.unparse(node.func.value)
        if receiver.endswith(".collection") or receiver == "collection":
            out.append({"call": ast.unparse(node), "line": int(node.lineno)})
    return out


# --------------------------------------------------------------------- 面一：旋钮现读


def switch_face(deployment=None):
    """两把旋钮在本进程现读到的答复 + 部署声明原文。一不发 SQL，二不开连接。"""
    raw_backend = str(os.getenv(indexing.INDEX_BACKEND_ENV, "") or "")
    raw_dual = str(os.getenv(pg_store.DUAL_WRITE_ENV, "") or "")
    return {
        "knobs": {
            indexing.INDEX_BACKEND_ENV: {
                "raw": raw_backend,
                "constant": indexing.INDEX_BACKEND,
                "factory_default": indexing.INDEX_BACKEND_DEFAULT,
                "resolved_by_read_backend": indexing.read_backend(),
                "reads_enabled": indexing.pgvector_reads_enabled(),
                "writes_primary": indexing.pgvector_writes_are_primary(),
            },
            pg_store.DUAL_WRITE_ENV: {
                "raw": raw_dual,
                "truthy_values": sorted(pg_store.TRUTHY_VALUES),
                "falsy_values": sorted(pg_store.FALSY_VALUES),
                "resolved_by_dual_write_enabled": pg_store.dual_write_enabled(),
            },
        },
        "deployment_declaration": deployment or {"source": None, "declared": {},
                                                 "note": "未给 --env-file：这一格未取数"},
    }


def deployment_declaration(path):
    """只读解析部署 env 文件里那两把旋钮的声明原文。文件不在位就报未取数，不猜。"""
    if not path:
        return {"source": None, "declared": {}, "note": "未给 --env-file：这一格未取数"}
    file = Path(str(path)).expanduser()
    if not file.is_file():
        return {"source": str(file), "declared": {}, "note": "声明文件不在位：这一格未取数"}
    wanted = {pg_store.DUAL_WRITE_ENV, indexing.INDEX_BACKEND_ENV}
    declared = {}
    for number, line in enumerate(file.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() in wanted:
            declared[key.strip()] = {"value": value.strip().strip("'\""), "line": number}
    return {"source": str(file), "declared": declared, "note": ""}


# ------------------------------------------------------- 面二：判定与逐枚写点的 off 态形状


def predicate_terms(roster_module, source):
    """现取停写判定由哪几枚条件与成、被哪几句早退挡过。合取项里少了 `dual_write_enabled` ⇒ 旋钮不再决定停写。"""
    tree = ast.parse(source)
    func = _function_by_name(tree, PREDICATE)
    if func is None:
        return {"present": False, "conjunction": False, "terms": [], "early_returns": []}
    terms = []
    conjunction = False
    for node in ast.walk(func):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        value = _unparenthesised(node.value)
        if isinstance(value, ast.BoolOp) and isinstance(value.op, ast.And):
            terms = [ast.unparse(item) for item in value.values]
            conjunction = True
            break
        if not terms:
            terms = [ast.unparse(value)]
            conjunction = False
    early = []
    for node in func.body:
        if not (isinstance(node, ast.If) and roster_module._always_exits(node.body)):
            continue
        returned = next((item for item in ast.walk(node) if isinstance(item, ast.Return)), None)
        early.append({"test": ast.unparse(node.test),
                      "returns": ast.unparse(returned.value) if returned is not None
                      and returned.value is not None else ""})
    return {
        "present": True,
        "conjunction": conjunction,
        "terms": terms,
        "switch_terms": [item for item in terms if pg_store.DUAL_WRITE_ENV in item
                         or "dual_write_enabled" in item],
        "backend_terms": [item for item in terms if "pgvector_writes_are_primary" in item],
        "early_returns": early,
    }


def _leg_variable_names(host_node):
    """宿主函数里"这条腿"叫什么：只认 `X = ...vector_mirror()` / `X = ..._open_vector_mirror()` 这一族赋值。

    写侧那层包装的变量名会漂（本仓为行号与名字漂记过一整族事故），所以补偿那一族的闸门判的是
    "有没有一枚由这两个生产者交回来的东西被 ``is not None`` 问过"，不是某一枚固定的 ``mirror``。
    """
    if host_node is None:
        return set()
    out = set()
    for node in ast.walk(host_node):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        called = ast.unparse(node.value.func)
        if not any(called.endswith("." + name) or called == name for name in LEG_PRODUCERS):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                out.add(target.id)
    return out


def _guard_needs_a_leg(guard, leg_names):
    return any(re.search(r"\b%s\b is not None" % name, guard) for name in leg_names)


def compensation_leg_guards(roster_module, sites, source):
    """补偿那一族今天靠谁被调用：调用点必须先过的那道门，从 AST 往上走现取。

    宿主函数名不抄——名册里 role == "compensation" 的那几枚写点住在谁名下，就从谁的限定名尾段
    取。找到调用点后，一路走到宿主函数，路上每一枚 ``if`` 的原文都记下来；只要其中一道门写的
    是"这条腿拿得到"（现取：那一枚由 ``vector_mirror()`` / ``_open_vector_mirror()`` 交回来的名字
    被 ``is not None`` 问过一遍），那这族补偿在 off 态就是**整支不可达**，
    而不是"闸门打开、重新动手"。那一形比措辞重要：写闸门同时是开的，接了新行却没人撤。
    """
    hosts = sorted({item.scope.split(".")[-1] for item in sites
                    if roster_module.CHROMA_WRITE_ROSTER.get(item.identity) is not None
                    and roster_module.CHROMA_WRITE_ROSTER[item.identity].role == "compensation"})
    tree = ast.parse(source)
    scopes = roster_module._scopes(tree)
    host_scopes = {node.name: scopes[id(node)] for node in _functions(tree)
                   if node.name in hosts}
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in hosts:
            continue
        guards = []
        host = ""
        host_node = None
        current = parents.get(id(node))
        while current is not None:
            if isinstance(current, ast.If):
                guards.append(" ".join(ast.unparse(current.test).split()))
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                host = scopes[id(current)]
                host_node = current
                break
            current = parents.get(id(current))
        leg_names = _leg_variable_names(host_node)
        out.append({"compensation_host": node.func.attr,
                    "host_scope": host_scopes.get(node.func.attr, ""),
                    "call_site": host, "guards": sorted(set(guards)),
                    "leg_names": sorted(leg_names),
                    "requires_a_leg": any(_guard_needs_a_leg(guard, leg_names)
                                          for guard in guards)})
    return out


def write_site_face(roster_module, sites, retriever_source):
    """逐枚写点在「关掉双写」前后的形状。名册、闸门、id 来源全部来自在册件，本函数只做一步派生：

    把闸门的正负两支与停写判定对齐 ⇒ 这一枚今天是挡着的还是放行的，旋钮一关会不会翻过来。
    判据只认名字（`_writes_go_to_pgvector` 出现在 gate_false 那一支 ⇒ 它只在判定为假时到达），
    不认枚数、不认行号。
    """
    tree = ast.parse(retriever_source)
    scopes = roster_module._scopes(tree)
    leg_guarded = compensation_leg_guards(roster_module, sites, retriever_source)
    blocked_scopes = {item["host_scope"] for item in leg_guarded if item["requires_a_leg"]}
    doc_rows_scopes = set()
    for func in _functions(tree):
        if any(item.endswith(DOC_ROWS_QUESTION) for item in _calls_inside(func)):
            doc_rows_scopes.add(scopes[id(func)])
    rows = []
    for site in sites:
        truthy, falsy = site.may_feed_ids
        spec = roster_module.CHROMA_WRITE_ROSTER.get(site.identity)
        if PREDICATE in falsy:
            verdict = "reopens_when_off"        # 今天被判定挡着，关掉双写就放行
        elif PREDICATE in truthy:
            verdict = "blocked_when_off"        # 今天到达，关掉双写就到不了
        else:
            verdict = "switch_independent"
        rows.append({
            "identity": site.identity,
            "role": getattr(spec, "role", "") if spec else "",
            "verb": site.verb,
            "ids_source": site.ids_source,
            "gate_true": sorted(truthy),
            "gate_false": sorted(falsy),
            "asked": sorted(site.asked),
            "verdict": verdict,
            "blocked_by_missing_leg": site.scope in blocked_scopes,
            "leg_guards": sorted({guard for guard_row in leg_guarded
                                  if guard_row["host_scope"] == site.scope
                                  for guard in guard_row["guards"]}),
            "reads_the_doc_rows_question": site.scope in doc_rows_scopes,
            "call_source": " ".join(site.call_source.split()),
        })
    return {"sites": rows, "leg_guards": leg_guarded,
            "roster_findings": list(roster_module.write_site_findings(sites))}


def roster_cross_check(roster_module, site_face):
    """本量具点名的写点身份与在册名册件点名的身份必须一一对得上。

    对不上时量具写什么都不算数——名册件说「这枚写点不见了」而我还在给它派生 off 态形状，
    那句派生就是假账。所以这一格进 `void`，按退出码 2 收，而不是当成一条普通发现。
    """
    void = []
    identities = [item["identity"] for item in site_face["sites"]]
    for item in sorted({name for name in identities if identities.count(name) > 1}):
        void.append("roster_cross_check_failed: 同一身份 %s 在码上长成两枚写点 —— 本量具按身份派生"
                    "off 态形状，撞名之后哪一枚接行、哪一枚撤行无从分开" % item)
    mine_missing = sorted(set(roster_module.CHROMA_WRITE_ROSTER) - set(identities))
    mine_surplus = sorted(set(identities) - set(roster_module.CHROMA_WRITE_ROSTER))
    theirs = "\n".join(site_face["roster_findings"])
    for item in mine_surplus:
        if item not in theirs:
            void.append("roster_cross_check_failed: 码上多出的写点 %s 在册件没点名" % item)
    for item in mine_missing:
        if item not in theirs:
            void.append("roster_cross_check_failed: 在册名册里的写点 %s 在码上找不到，"
                        "本量具仍按在册那一套闸门给它派生形状——读数不可信" % item)
    if site_face["roster_findings"] and not void:
        void.append("roster_cross_check_failed: 在册件自己就报了名册对不上（%d 条红句），"
                    "本量具的写点面读数不可信" % len(site_face["roster_findings"]))
    return void


def switch_gated_legs(roster_module, pg_store_source):
    """pg_store 里「双写关着就拒答」的腿：直接从 AST 现取，一枚都不抄。

    拒答有两种写法，都算：① 这一枚函数自己 raise 出 `REASON_VECTOR_READ_WITHOUT_DUAL_WRITE`；
    ② 它经过一枚拿不到腿就 raise 的 helper（`_document_leg_connection()` 那一枚）。
    """
    tree = ast.parse(pg_store_source)
    functions = _functions(tree)
    direct = {}
    for func in functions:
        for node in ast.walk(func):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            keywords = {keyword.arg for keyword in node.exc.keywords} if isinstance(node.exc, ast.Call) else set()
            if SWITCH_REASON_CONSTANT in keywords or SWITCH_REASON_CONSTANT in ast.unparse(node):
                direct[func.name] = {"raises_switch_reason": True,
                                     "opens_mirror": any(item.endswith("." + MIRROR_FACTORY)
                                                         or item == MIRROR_FACTORY
                                                         for item in _calls_inside(func))}
                break
    legs = []
    for func in functions:
        name = func.name
        if name in direct:
            legs.append({"leg": name, "how": "直接按 %s 拒答" % SWITCH_REASON_CONSTANT,
                         **direct[name]})
            continue
        for helper in sorted(direct):
            if helper == name or not helper.startswith("_"):
                continue
            if any(item.endswith("." + helper) or item == helper for item in _calls_inside(func)):
                legs.append({"leg": name, "how": "经 %s() 拿不到腿即拒答" % helper,
                             "raises_switch_reason": False,
                             "opens_mirror": any(item.endswith("." + MIRROR_FACTORY)
                                                 for item in _calls_inside(func))})
                break
    return {"refusers": sorted(direct), "legs": sorted(legs, key=lambda row: row["leg"])}


def predicate_dependent_questions(roster_module, source, leg_names):
    """停写判定还管着哪几句**问句**：关掉双写之后，这些问句的答复改由谁给。

    两种写法各是一格，都从 AST 现取：
      * `if not self._writes_go_to_pgvector(): return ..., []` ⇒ 这一枚问句在 off 态**恒交回空的
        PG 那一格**（`_document_rows_by_leg` 正身：删除集合里从此没有只住 PG 的行）；
      * `if self._writes_go_to_pgvector(): ...` 后面跟着遗留目录的读调用 ⇒ off 态**整句改问遗留
        目录**（`list_documents()` / `document_chunks()` 正身：已删文档与在库文档从此同一种读法）。
    """
    tree = ast.parse(source)
    scopes = roster_module._scopes(tree)
    rows = []
    for func in _functions(tree):
        calls = _calls_inside(func)
        if not any(item.endswith("." + PREDICATE) or item == PREDICATE for item in calls):
            continue
        negated_empty = []
        positive_branch = []
        for node in ast.walk(func):
            if not isinstance(node, ast.If):
                continue
            test = ast.unparse(node.test)
            if PREDICATE not in test:
                continue
            if test.lstrip().startswith("not "):
                returns = [item for item in ast.walk(node) if isinstance(item, ast.Return)]
                if returns and "[]" in ast.unparse(returns[0].value or ast.Constant(value=None)):
                    negated_empty.append(test)
            else:
                positive_branch.append(test)
        rows.append({
            "question": scopes[id(func)],
            "negated_early_return": sorted(set(negated_empty)),
            "positive_branch": sorted(set(positive_branch)),
            "legacy_receipts": _legacy_receipt_calls(func),
            "switch_gated_leg_calls": sorted(item for item in calls
                                             if any(item.endswith("." + name) or item == name
                                                    for name in leg_names)),
        })
    return {"questions": rows}


def legacy_receipt_waiters(app_sources, legs):
    """拒答被吞掉之后，答复由谁给出：两跳派生（腿 → 吞掉它的那句 except → 该调用方的遗留读）。

    只算「吞」不算「退」：`_document_rows_by_leg` 那种把拒答原样上抛的调用方**不是**回执等 Chroma，
    它是拒答，两者必须分开记，否则这一格会把 fail-closed 读成静默降级。
    """
    trees = {}
    for rel, source in app_sources.items():
        try:
            trees[rel] = ast.parse(source)
        except SyntaxError:
            continue
    targets = {row["leg"] for row in legs}
    swallows = []
    for rel, tree in trees.items():
        for func in _functions(tree):
            for node in ast.walk(func):
                if not isinstance(node, ast.Call):
                    continue
                called = ast.unparse(node.func)
                leg = next((name for name in targets
                            if called.endswith("." + name) or called == name), None)
                if leg is None:
                    continue
                for try_node in ast.walk(func):
                    if not isinstance(try_node, ast.Try):
                        continue
                    if not any(node is item for item in ast.walk(try_node)):
                        continue
                    for handler in try_node.handlers:
                        if _handler_swallows(handler):
                            swallows.append({"file": rel, "function": func.name, "leg": leg,
                                             "handler": ast.unparse(handler.type)
                                             if handler.type is not None else "bare"})
                            break
                    break
    waiters = []
    for swallow in swallows:
        for rel, tree in trees.items():
            for func in _functions(tree):
                calls = _calls_inside(func)
                if not any(item.endswith("." + swallow["function"]) or item == swallow["function"]
                           for item in calls):
                    continue
                legacy = _legacy_receipt_calls(func)
                if not legacy:
                    continue
                waiters.append({
                    "leg": swallow["leg"],
                    "refusal_swallowed_by": "%s::%s" % (swallow["file"], swallow["function"]),
                    "answered_by": "%s::%s" % (rel, func.name),
                    "legacy_receipts": [item["call"] for item in legacy],
                })
    return {"swallows": swallows, "waiters": waiters}


# --------------------------------------------------------------------- 发现（红句）清单


def _finding(code, subject, text):
    return {"code": code, "subject": subject, "text": text}


def off_state_findings(predicate, site_face, questions, waiters, corpus):
    """把三面拼成一句句可判读的话：关掉双写会掉什么，逐枚点名。"""
    findings = []
    if not predicate["present"]:
        findings.append(_finding("predicate_missing", PREDICATE,
                                 "码上找不到停写判定 " + PREDICATE + "() —— 本量具判的就是这枚旋钮"
                                 "与写闸门的关系，判定没了就一律按「测不到」记账，不许报绿"))
    else:
        if not predicate["conjunction"]:
            findings.append(_finding("predicate_missing", "conjunction",
                                     "停写判定不再是合取（现取：%s）—— 「三枚条件与成」那句话已经不成立，"
                                     "下面每一条写点读数都要重新对" % (predicate["terms"],)))
        for name in PREDICATE_TERMS:
            if not any(name in item for item in predicate["terms"]):
                why = ("%s 不再决定停写：关掉它不会把遗留腿的写闸门打开，但照样会杀掉两条读腿"
                       % pg_store.DUAL_WRITE_ENV) if name == SWITCH_TERM else (
                      "新行落点不再跟着读路径那一把开关走：这就是「两把开关」的形状，读在 PG、"
                      "写在另一台，谁都不知道今天哪一库是本体")
                findings.append(_finding("predicate_term_missing", name,
                                         "停写判定的合取项里已经没有 %s()（现取合取：%s）—— %s"
                                         % (name, " and ".join(predicate["terms"]), why)))
        if not predicate["early_returns"]:
            findings.append(_finding("predicate_term_missing", STORES_TERM,
                                     "判定顶部那枚\"不存向量就早退\"不在了 —— 离线 _JsonCollection "
                                     "会把「该走 PostgreSQL」误读成关键词降级（计划书 §15 S5 那一格）"))
    for site in site_face["sites"]:
        if site["role"] == "compensation":
            if site["blocked_by_missing_leg"]:
                findings.append(_finding(
                    "compensation_needs_a_leg_it_wont_have", site["identity"],
                    "这一枚补偿的调用点必须先过 %s；关掉 %s 就没有那条腿，整支逆序补偿不再被调用——"
                    "而同一时刻遗留目录的写闸门是开的，Chroma 接的新行没有任何东西撤它（回滚面"
                    "静默失效，不是换成另一套补偿）"
                    % (" / ".join(site["leg_guards"]) or "<取不到门>", pg_store.DUAL_WRITE_ENV)))
            continue
        if site["verdict"] == "reopens_when_off":
            findings.append(_finding(
                "chroma_write_gate_reopens", site["identity"],
                "这一枚今天被停写判定挡着（现取闸门：必须假 %s）；关掉 %s 判定即为假，遗留目录重新接新行"
                "——所以「停双写」是把 S0 停写翻回去，不是停掉最后一份写。（现取 id：%s）"
                % (", ".join(site["gate_false"]) or "<无>", pg_store.DUAL_WRITE_ENV,
                   site["ids_source"])))
        if site["reads_the_doc_rows_question"]:
            findings.append(_finding("delete_set_blind_to_pg_only_rows", site["identity"],
                                     "这一枚所在的那一笔先问 %s() 拿行；那一句在 off 态走早退，"
                                     "PG 那一格恒交回空列表 ⇒ 同名重传时只住在 PostgreSQL 的旧行"
                                     "不在删除集合里，重开双写后上一版会自己活回来。"
                                     % DOC_ROWS_QUESTION))
    for row in questions["questions"]:
        if row["negated_early_return"]:
            findings.append(_finding("question_rehomes_to_legacy_store", row["question"],
                                     "off 态早退（现取判定 %s）：这一句只问遗留目录，PG 那一格恒空"
                                     % (row["negated_early_return"],)))
        elif row["positive_branch"] and row["legacy_receipts"]:
            findings.append(_finding("question_rehomes_to_legacy_store", row["question"],
                                     "off 态整句改问遗留目录（现取遗留读调用：%s）—— 名单与按文档读回"
                                     "都退回那台要退役的引擎"
                                     % ", ".join(item["call"] for item in row["legacy_receipts"])))
    for waiter in waiters["waiters"]:
        findings.append(_finding("read_leg_waits_for_chroma_receipt", waiter["leg"],
                                 "%s() 在 off 态按 %s 拒答，拒答被 %s 吞成\"这一腿没答\"，"
                                 "答复改由 %s 的遗留读给出（现取：%s）—— 这一形就叫「隐式等 Chroma 回执」。"
                                 % (waiter["leg"], SWITCH_REASON_CONSTANT,
                                    waiter["refusal_swallowed_by"], waiter["answered_by"],
                                    ", ".join(waiter["legacy_receipts"]))))
    for row in (corpus or {}).get("findings", []):
        findings.append(row)
    return findings

# ------------------------------------------------------------------ 面三：语料面（可注入）

_ID_TAIL = re.compile(r"^(.*)_([0-9]+)\Z")


def document_of_vector_id(vector_id):
    """vector_id 的形状是 `f"{filename}_{i}"`（写在 retriever 的 add_document 里）；尾巴不是数字就整串当文档名。"""
    match = _ID_TAIL.match(str(vector_id))
    return match.group(1) if match else str(vector_id)


def database_name(url):
    return Path(str(urlsplit(str(url)).path or "")).name


def is_sandbox_database(name):
    return str(name) in SANDBOX_DATABASES or bool(_SANDBOX_DATABASE_SHAPE.match(str(name or "")))


def assert_session_read_only(connection):
    """`connect_read_only()` 设不上 READ ONLY 时只 print 一句 warn 就继续；本量具不接受 warn。"""
    row = connection.execute(READ_ONLY_PROBE_SQL).fetchone()
    value = row[0] if isinstance(row, (tuple, list)) else (
        next(iter(row.values())) if isinstance(row, dict) else row)
    if str(value).strip().lower() not in ("on", "true", "1", "yes"):
        fail_precondition("会话不读只读（%s 现取 %r）：本量具只允许在 READ ONLY 事务里问库"
                          % (READ_ONLY_PROBE_SQL, value))
    return str(value)


def corpus_face(args, probe, tool, staging):
    """PG 侧与遗留引擎侧的语料面差集。任何一枚前置不齐都按 2 号收，不产出半张结论。"""
    chroma_dir, made_snapshot = probe.chroma_dir_for_run(args, staging)
    source = Path(str(args.snapshot_from)).expanduser().resolve() if args.snapshot_from else None
    before = probe.volume_inventory(source) if source is not None else None
    collection = tool.open_chroma(str(chroma_dir), args.collection)
    legacy_count = int(collection.count())
    url = str(args.database_url or "")
    if not url:
        fail_precondition("语料面要连库，而本量具没有默认连接串：给 --database-url（生产那一遍由总控开窗跑）")
    name = database_name(url)
    if not is_sandbox_database(name) and not str(args.window_owner or "").strip():
        fail_precondition("库名 %r 不在沙盒名册 %r 那一族之内：本单不许自行开生产窗。"
                          "要读生产必须同时给 --window-owner <谁开的窗>（并先与总控对过测量窗）。"
                          % (name, tuple(SANDBOX_DATABASES)))
    connection = tool.connect_read_only(url)
    read_only = assert_session_read_only(connection)
    scope = tool.read_scope(connection, args.vector_table)
    drift = tool.corpus_drift(connection, collection, vector_table=args.vector_table, scope=scope)
    after = probe.volume_inventory(source) if source is not None else None
    mutated = (None if before is None else not probe.inventories_match(before, after))
    if mutated:
        fail_precondition("源卷在读取前后不再是同一份字节（before=%s after=%s）：本次不产出语料面结论"
                          % (str(before["digest"])[:16], str(after["digest"])[:16]))
    try:
        chroma_ids = tool.chroma_all_ids(collection)
    finally:
        connection.close()
        if made_snapshot:
            probe.remove_snapshot(chroma_dir)
    pg_only = [str(item) for item in drift["only_in_pg"]]
    legacy_only = [str(item) for item in drift["only_in_chroma"]]
    pg_only_docs = {document_of_vector_id(item) for item in pg_only}
    legacy_docs = {document_of_vector_id(item) for item in chroma_ids}
    vanish = sorted(pg_only_docs - legacy_docs)
    findings = []
    if pg_only:
        findings.append(_finding("corpus_gap", "only_in_pg",
                                 "%d 枚行只住在 PostgreSQL（切换之后写的，遗留腿一枚都没有）；关掉双写后"
                                 "它们同时从读答复与删除问句里消失，其中 %d 篇文档会整篇不见：%s"
                                 % (len(pg_only), len(vanish), ", ".join(vanish[:20]) or "（无）")))
    if legacy_only:
        findings.append(_finding("corpus_gap", "only_in_chroma",
                                 "%d 枚行只有遗留腿持有（PG 没有）：重开双写不会把它们补回来，"
                                 "这一格属于回滚姿势里要单独处理的那一批" % len(legacy_only)))
    if drift["wrong_width"]:
        findings.append(_finding("corpus_gap", "wrong_width",
                                 "%d 枚行的向量宽度与 vector_scope 声明的 %d 维不符（R22 口径）"
                                 % (len(drift["wrong_width"]), scope["dimension"])))
    return {
        "gathered": True,
        "database": {"name": name, "sandbox": is_sandbox_database(name),
                     "window_owner": str(args.window_owner or ""),
                     "read_only_verified": read_only},
        "chroma": {"opened": str(chroma_dir), "snapshot_of": str(source) if source else None,
                   "made_by_this_run": bool(made_snapshot), "collection": args.collection,
                   "count": legacy_count,
                   "source_inventory_before": before, "source_inventory_after": after},
        "scope": scope,
        "vector_table": args.vector_table,
        "drift": {"pg_vectors": drift["pg_vectors"], "chroma_vectors": drift["chroma_vectors"],
                  "only_in_pg": len(pg_only), "only_in_chroma": len(legacy_only),
                  "wrong_width": len(drift["wrong_width"]),
                  "all_zero_rows": drift["all_zero_rows"],
                  "index_version_id_null": drift["index_version_id_null"],
                  "chunks_rows": drift["chunks_rows"],
                  "chunks_with_backfilled_embedding": drift["chunks_with_backfilled_embedding"]},
        "documents": {"pg_only": len(pg_only_docs), "legacy_held": len(legacy_docs),
                      "vanish_if_off": vanish},
        "findings": findings,
    }


# ---------------------------------------------------------------------------- 拼装与出口


def app_sources():
    out = {}
    for path in sorted((ROOT / "app").rglob("*.py")):
        out[path.resolve().relative_to(ROOT).as_posix()] = path.read_text(encoding="utf-8")
    return out


def revision():
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001 - 取不到版本号不影响量具
        return "unknown"


def measure(args):
    roster = load_roster()
    probe = load_probe() if (args.database_url or args.chroma_dir or args.snapshot_from) else None
    retriever_source = (ROOT / RETRIEVER_REL).read_text(encoding="utf-8")
    pg_store_source = (ROOT / PG_STORE_REL).read_text(encoding="utf-8")

    predicate = predicate_terms(roster, retriever_source)
    site_face = write_site_face(roster, roster.app_write_sites(), retriever_source)
    void = roster_cross_check(roster, site_face)
    gated = switch_gated_legs(roster, pg_store_source)
    leg_names = [row["leg"] for row in gated["legs"]]
    questions = predicate_dependent_questions(roster, retriever_source, leg_names)
    waiters = legacy_receipt_waiters(app_sources(), gated["legs"])
    corpus = None
    if probe is not None:
        staging = Path(args.out_dir) / "snapshots"
        corpus = corpus_face(args, probe, load_recall(probe), staging)
    findings = off_state_findings(predicate, site_face, questions, waiters, corpus)
    code = EXIT_PRECONDITION if void else classify_exit(findings, corpus_gathered=bool(corpus))
    return {
        "ticket": "R633",
        "question": "把 %s 关掉会掉什么（S1 停双写的前置）" % pg_store.DUAL_WRITE_ENV,
        "run_stamp": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "revision": revision(),
        "readonly": True,
        "exit_code": code,
        "exit_meaning": EXIT_MEANINGS[code],
        "switch": switch_face(deployment_declaration(args.env_file)),
        "predicate": predicate,
        "write_sites": site_face,
        "switch_gated_legs": gated,
        "predicate_dependent_questions": questions,
        "chroma_receipt_waiters": waiters,
        "corpus": corpus or {"gathered": False,
                             "note": "未给 --database-url 与 --chroma-dir/--snapshot-from："
                                     "语料面这一格未取数，本席没有跑生产库，那一遍由总控开窗"},
        "void": void,
        "findings": findings,
    }


def load_recall(probe):
    return probe.load_recall_tool()


def classify_exit(findings, corpus_gathered: bool) -> int:
    """退出码的唯一派生处。1 号只允许由「检出发现」发出（与 R269 同口径）。"""
    if findings:
        return EXIT_CANNOT_FLIP
    if not corpus_gathered:
        return EXIT_STATIC_ONLY
    return EXIT_CAN_FLIP

EXIT_MEANINGS = {
    EXIT_CAN_FLIP: "三面全量到且没有任何发现：S1 停双写现在可翻",
    EXIT_CANNOT_FLIP: "跑成了，且检出发现：关掉 %s 会掉功能或留下删不掉的行 ⇒ 现在不可翻"
                      % pg_store.DUAL_WRITE_ENV,
    EXIT_PRECONDITION: "前置不满足或本量具的读数不可信（名册对不上／只读事务设不上／目录是现役卷／"
                       "库名不在沙盒又没给开窗责任人／量具自身异常），stderr 首行带「%s」" % PRECONDITION_PREFIX.strip(),
    EXIT_STATIC_ONLY: "静态两面量到且无发现，但语料面未取数 ⇒ 只能说这一遍没量全，不能说可翻",
}

EPILOG = """退出码（优先级 2 > 1 > 3 > 0）：
  0  %(0)s
  1  %(1)s
  2  %(2)s
  3  %(3)s

发现的代码名（牙按名字判哪一格红，不按句子措辞）：
  predicate_missing                  停写判定不在码上、或不再是合取 ⇒ 三面读数全部换问题
  predicate_term_missing             合取项里少了一枚在册条件（dual_write_enabled /
                                     pgvector_writes_are_primary / stores_vectors 早退）
  chroma_write_gate_reopens          这一枚变异写点在 off 态重新接行
  compensation_needs_a_leg_it_wont_have  补偿那一支唯一的调用点要一条拿不到的腿（mirror 非 None）
  delete_set_blind_to_pg_only_rows   删除集合的来源问句在 off 态恒交回空的 PG 那一格
  question_rehomes_to_legacy_store   名单/按文档读回这类问句整句退回遗留目录
  read_leg_waits_for_chroma_receipt  拒答被吞成「这一腿没答」，答复改由 Chroma 给
  corpus_gap                         语料面差集非空（只在给了库与卷时才有这一格）
  roster_cross_check_failed          名册与在册件对不上 ⇒ 走 2 号，不当成绿

连库姿势（生产那一遍由总控开窗跑，本席一枚字节都没连）：
  python scripts/r633_dual_write_off_precondition.py ^
      --database-url postgresql://<user>@<host>:5432/eb_r59_sandbox ^
      --snapshot-from /app/chroma_db --collection enterprise_docs ^
      --env-file deploy/.env.server
  # 读生产库必须再加 --window-owner <谁开的窗>，否则按 2 号收；
  # --chroma-dir 只接已经快照好的副本，指到仓内/容器内的现役卷同样按 2 号收。
""" % {str(key): EXIT_MEANINGS[key] for key in (0, 1, 2, 3)}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="r633_dual_write_off_precondition.py",
        description="R633：把 VECTOR_DUAL_WRITE 关掉会掉什么（只读前置量具，一不写库二不动容器）",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--database-url", default=None,
                        help="PG 侧连接串；没有默认值（缺省即不连库，语料面报未取数）")
    parser.add_argument("--window-owner", default=None,
                        help="开窗责任人；库名不在沙盒名册时必填，否则按前置不满足收")
    parser.add_argument("--chroma-dir", default=None,
                        help="已经快照好的遗留目录副本（绝不指现役卷）")
    parser.add_argument("--snapshot-from", default=None,
                        help="复制源可以是现役卷：本量具按字节复制一份到 --out-dir/snapshots 再读副本")
    parser.add_argument("--collection", default="enterprise_docs",
                        help="遗留集合名，与写入侧同名（tests/test_r120_p3_collection_default.py 钉着）")
    parser.add_argument("--vector-table", default=pg_store.DEFAULT_VECTOR_TABLE)
    parser.add_argument("--env-file", default=None,
                        help="部署声明文件（deploy/.env.server 那一类），只读它里面两把旋钮的原文")
    parser.add_argument("--out-dir", default=os.path.join(tempfile.gettempdir(), "r633"),
                        help="产物落点，必须在仓外")
    parser.add_argument("--all", action="store_true", help="打印每一枚写点与每一条发现")
    return parser.parse_args(argv)


def render_human(report, *, show_all: bool = False) -> str:
    lines = ["R633 —— 把 %s 关掉会掉什么（只读，退出码 %d）" % (pg_store.DUAL_WRITE_ENV,
                                                                report["exit_code"]),
             "  revision      : " + report["revision"],
             "  判定的合取项  : " + " and ".join(report["predicate"]["terms"] or ["<取不到>"]),
             "  旋钮是否决定停写: %s" % bool(report["predicate"]["switch_terms"]),
             "  变异写点      : %d 枚（名册来自 %s）" % (len(report["write_sites"]["sites"]),
                                                        ROSTER_REL.as_posix()),
             "  开关一关就拒答的腿: %s" % (", ".join(row["leg"] for row in
                                                     report["switch_gated_legs"]["legs"]) or "<无>"),
             "  隐式等 Chroma 回执: %d 条路径" % len(report["chroma_receipt_waiters"]["waiters"]),
             "  语料面        : " + ("已取数" if report["corpus"]["gathered"]
                                    else report["corpus"]["note"])]
    if report["void"]:
        lines.append("  🔴 读数不可信：%s" % "; ".join(report["void"]))
    lines.append("发现 %d 条：" % len(report["findings"]))
    shown = report["findings"] if show_all else report["findings"][:8]
    for index, item in enumerate(shown, 1):
        lines.append("  [%d/%d] <%s> %s —— %s" % (index, len(report["findings"]),
                                                  item["code"], item["subject"], item["text"]))
    if len(shown) < len(report["findings"]):
        lines.append("  （余 %d 条见 --all 与产物）" % (len(report["findings"]) - len(shown)))
    if report["corpus"]["gathered"]:
        lines.append("语料面读数：" + json.dumps(report["corpus"]["drift"], ensure_ascii=False))
    if show_all:
        for site in report["write_sites"]["sites"]:
            lines.append("  写点 %s ｜角色 %s｜off 态 %s｜现取 id %s"
                         % (site["identity"], site["role"] or "?", site["verdict"], site["ids_source"]))
    return "\n".join(lines)


def render_markdown(report) -> str:
    parts = ["# R633 停双写前置读数（机器生成，只读）",
             "",
             "- revision：`%s`" % report["revision"],
             "- 退出码：`%d` — %s" % (report["exit_code"], report["exit_meaning"]),
             "- 停写判定合取项：%s" % "、".join("`%s`" % item for item in report["predicate"]["terms"]),
             "",
             "## 逐枚写点的 off 态形状",
             "",
             "| 身份 | 角色 | 现取闸门（必须假） | off 态 |",
             "| --- | --- | --- | --- |"]
    for site in report["write_sites"]["sites"]:
        parts.append("| `%s` | %s | %s | %s |" % (site["identity"], site["role"] or "?",
                                                  ", ".join("`%s`" % item for item in site["gate_false"]) or "-",
                                                  site["verdict"]))
    parts += ["", "## 发现", ""]
    for item in report["findings"]:
        parts.append("- `%s` ｜ `%s` ｜ %s" % (item["code"], item["subject"], item["text"]))
    if not report["findings"]:
        parts.append("- （无）")
    parts += ["", "## 语料面", "", "```json",
              json.dumps(report["corpus"], ensure_ascii=False, indent=1, default=str), "```"]
    return "\n".join(parts) + "\n"


def write_outputs(report, out_dir: Path) -> dict:
    stamp = report["run_stamp"]
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / ("r633-precondition-%s.json" % stamp)
    md_path = out_dir / ("r633-precondition-%s.md" % stamp)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str),
                         encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def guard_out_dir(out_dir: str) -> Path:
    """产物落仓外：指进工作树当场按前置不满足收（本单不许在仓里留下任何东西）。"""
    path = Path(str(out_dir)).expanduser().resolve()
    if path == ROOT or str(path).startswith(str(ROOT) + os.sep):
        fail_precondition("--out-dir 落在仓内：" + str(path) + "；本量具的产物一律落仓外")
    return path


def main(argv=None) -> int:
    args = parse_args(argv)
    args.out_dir = str(guard_out_dir(args.out_dir))
    try:
        report = measure(args)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - "没跑成"不许冒领 1 号
        fail_precondition("量具自身异常终止：" + type(exc).__name__ + ": " + str(exc)
                          + "（本次没有产出任何前置结论）")
    print(render_human(report, show_all=args.all))
    if not report["corpus"]["gathered"]:
        print("（语料面未取数：本量具默认一枚库都不连。生产那一遍由总控开窗跑，"
              "命令见 --help 的「连库姿势」。）")
    outputs = write_outputs(report, Path(args.out_dir))
    print("产物：" + json.dumps(outputs, ensure_ascii=False))
    if report["void"]:
        fail_precondition("名册与在册件对不上，本量具的写点面读数不可信："
                          + "; ".join(report["void"]))
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
