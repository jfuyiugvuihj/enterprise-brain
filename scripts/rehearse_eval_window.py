#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R107 跑分窗口离线预演器（只读审计件，2026-09-20，基线见 --baseline 输出）。

它回答的唯一问题：D14甲 那个 3-4 小时窗口一开，105 题里每一题会被什么卡住。
产物 = 每题一行的预演表 + 四类失败模式的命中清单，全部从**本树源码**算出来。

四条硬规矩（照 scripts/check_eval_evidence_coverage.py 的形）：
  1. 只读：零模型调用、零网络、零连库、零起服务、零写盘（结果只走 stdout）。
     离线不是一句主张：本件在 import 任何业务代码之前把三条出站 socket 路径换成
     会抛的桩，任何一次真连接都会当场炸给看的人。``app/agents/orchestrator`` 不 import
     ——它模块级就 ``_make_model(...)``，会去发现本机模型。
  2. 不发明口径：must_contain 的「有没有出处」直接调 R94 常驻件
     scripts/check_eval_evidence_coverage.py 的函数；判分调 app/quality/eval.py 的
     ``_is_correct`` 本体；路由调 app/agents/planner.py 与 app/agents/nodes.py 的纯规则函数。
  3. 只报代码能担保的东西：模型说了算的部分一律标「静态不可确定」，不猜。
     表里的腿数/秒数是 [推算]，算式写在 --summary 里，参数取跟进单 §42 八变体的实测行。
  4. 🔴 R361：事实不许手抄。基点这份在这里躺着 42 枚 ``app/xxx.py:行号`` 形态的字面引用
   （散在 37 行；跟进单按 20 枚记，是低估），抄的是**值**本身，
     现场一改它就拿着旧事实继续算、还打出一份看起来正常的读数。现在每一格要么运行时
     现场派生（AST 抠字面量，或把现场源码的一小段 exec 成函数），要么留一份抄本并钉在
     现场上等值比对，不等当场红并点名差在哪一枚。开机先自量尺子（guard_facts），
     量不过就 exit 2 出红话，绝不带病出读数；尺子今天读了什么用 --facts 打印。

用法（仓库根，项目 venv 解释器）：
    python scripts/rehearse_eval_window.py --switches       # R218：窗口要翻的那几个开关（三格）
    python scripts/rehearse_eval_window.py --facts          # R361：尺子读了哪些现场事实（逐格锚点）
    python scripts/rehearse_eval_window.py                 # 每题一行 markdown 表
    python scripts/rehearse_eval_window.py --only doc      # 按题号前缀筛
    python scripts/rehearse_eval_window.py --csv           # 机器可读（仍只走 stdout）
    python scripts/rehearse_eval_window.py --floor 1536    # 复算 R100 落地后的那一半
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import socket
import subprocess
import sys
import textwrap
from functools import lru_cache
from pathlib import Path

#: 现场到底在哪棵树。🔴 不能只按 ``__file__`` 的祖先找：R218 那枚反证钉会把本件复制进
#: tmp 下的一棵 overlay 再 exec（它只拷脚本，不拷 app/），那种跑法里脚本自己所在的树不是现场。
#: 找不到就退回进程的工作目录——"你站在哪棵树里跑它，就读哪棵树"，与本件的读者身份一致。
REPO_MARKERS = ("pyproject.toml", "app/agents/orchestrator.py")


def _resolve_repo_root() -> Path:
    here = Path(__file__).resolve()
    cwd = Path.cwd().resolve()
    for base in (*here.parents, cwd, *cwd.parents):
        if all((base / marker).is_file() for marker in REPO_MARKERS):
            return base
    return here.parents[1]


REPO_ROOT = _resolve_repo_root()

FIXTURE_REL = Path("tests") / "fixtures" / "business_evaluation_100.jsonl"


# ==================== 现场事实层（R361）======================================
#
# 一句口径：**本件是读者**。基点那份里躺着 42 枚 ``app/xxx.py:行号`` 形态的手抄（本单一枚枚数过），
# 抄的不只是行号，**值本身也是抄的** —— 现场一改，预演器会拿着旧事实继续算，还打出一份
# 看起来正常的读数（它红不起来，因为它从没读过现场）。从今天起每一格只有两种下场：
#
#   derived  现场派生：AST 抠字面量，或把现场源码的一小段 exec 成函数（事实是**规则**时，
#            抄规则 = 重写一遍逻辑，那正是本单要根治的病）
#   copy     抄本 + 等值钉：本件仍自带一份字面量，但启动时逐格与现场比对，不等当场红
#
# 🔴 裸行号从本件里彻底退出（R346 同一条裁定：冻结的历史只准当素材读，不许当事实用）。
# 出处一律是 ``path::symbol``，写进 FACT_ANCHORS；打印进 --summary 的那两处锚点取现场
# 符号的行跨度，同样是算出来的，不是抄的。
#
# 判据丙（import 还是 AST）在本树 ``.venv`` 里逐枚实测（2026-09-27 主树、带 ``.env``，同一枚
# 只读拦网桩之下，桩会记下每一次真连接企图）：
#
#     import app.common.cache            0.02 s   出站 0    干净
#     import app.agents.planner          0.00 s   出站 0    干净
#     import app.quality.eval            0.00 s   出站 0    干净
#     import app.agents.nodes            4.45 s   出站 0    本件本来就 import 它
#     import app.api.v1.chat             4.42 s   出站 2    🔴 模块级造检索器与模型句柄，顺带连库
#     import app.agents.orchestrator     0.25 s   出站 1    🔴 模块级 create_react_agent(_make_model)
#
# 🔴 秒数和出站次数都随环境漂：把本件拷进一棵没有 ``.env`` 的 worktree 重跑，那两棵的出站数就
# 读成 0（本单一手实测）。环境变了不等于理由没了，真正不漂、也是这枚决定唯一依据的是**模块级
# 就动手造对象**——chat 那枚模块级 ``DocumentRetriever(...)`` 实测会把所在树的 chroma_db 写脏，
# 当场被 R134 闸门点名。所以常驻复跑的是判定不是秒数：见 tests/test_r361_import_or_ast_is_measured.py，
# 它 AST 读模块级，绝不 import 重件。
# ⇒ orchestrator / chat 两棵永远不 import，只 AST / exec 切片；其余按这张表挑。
# 判据乙：方向不许反。本件只**读** app/** 与 scripts/**，一个字节都不写它们，
# 也不为省事去动它们（写域见工单）。

REPO_RELS = {
    "orchestrator": "app/agents/orchestrator.py",
    "nodes": "app/agents/nodes.py",
    "planner": "app/agents/planner.py",
    "tools": "app/agents/tools.py",
    "evidence": "app/agents/evidence.py",
    "chat": "app/api/v1/chat.py",
    "cache": "app/common/cache.py",
    "model_handler": "app/common/model_handler.py",
    "model_budget": "app/common/model_budget.py",
    "eval": "app/quality/eval.py",
    "transport": "scripts/eval_transport_ask_v2.py",
}

#: 本件允许留在“等值比对”抄本一侧的格（判据丁）。其余事实没有抄本，只有现场读数。
#: CALIBRATED_FLOOR_TOKENS 是 R379 加的一枚：它抄的不是"现场的值"，是**一次跑分实测的标定条件**
#  ——那把尺子（每题 37.3 s）没有代码事实源，只能自带抄本，再钉回现场真身上等值比对。
COPY_CELLS = ("KW_CHART", "KW_DATA", "KW_EXPORT", "KW_DOC", "CACHE_KEY_PROSE",
              "CALIBRATED_FLOOR_TOKENS")


class FactError(RuntimeError):
    """现场读不出这一格：形状变了，不是数字变了。去看着现场，别改数（R346）。"""


def repo_root_of(root=None) -> Path:
    return REPO_ROOT if root is None else Path(root)


def source_text(rel: str, root=None) -> str:
    path = repo_root_of(root) / rel
    try:
        return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    except OSError as exc:
        raise FactError(f"读不到现场源码 {rel}：{exc}") from exc


@lru_cache(maxsize=None)
def _source_tree(rel: str, root: str) -> ast.Module:
    return ast.parse(source_text(rel, root))


def source_tree(rel: str, root=None) -> ast.Module:
    return _source_tree(rel, str(repo_root_of(root)))


def load_names(node) -> set:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def bound_names(node) -> set:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and not isinstance(n.ctx, ast.Load)}


BUILTINISH = frozenset(
    ("any all isinstance getattr len str bool int float tuple list dict set frozenset "
     "sorted reversed min max sum range enumerate zip print").split()
)


def module_binding(node):
    """模块级赋值的 ``(名字, 右端)``；``A = 1`` 与 ``A: tuple[str, ...] = (...)`` 同一种读法。

    🔴 R379：只认 ``ast.Assign`` 会把带类型注解的常量整格读不动（orchestrator 里那枚
    ``_SIDE_EFFECT_LEGS`` 就是注解写法），那是一枚假红——现场什么都没改，尺子先瞎了。
    """
    if isinstance(node, ast.Assign):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return None
        return node.targets[0].id, node.value
    if (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
            and node.value is not None):
        return node.target.id, node.value
    return None


def _binding_name(node) -> str:
    """模块级赋值语句左边那枚名字（``A = ...`` 与 ``A: T = ...`` 两种写法），取不到交回空串。"""
    binding = module_binding(node)
    return binding[0] if binding else ""


def module_assign_node(tree: ast.Module, name: str, rel: str) -> ast.expr:
    for node in tree.body:
        binding = module_binding(node)
        if binding and binding[0] == name:
            return binding[1]
    raise FactError(f"{rel} 里 {name} 不再是模块级赋值：这一格失去了事实源")


def literal_of(node, what: str, rel: str):
    try:
        return ast.literal_eval(node)
    except ValueError as exc:
        raise FactError(f"{rel} 里 {what} 不再是字面量，本件的读法失效：{exc}") from exc


def one_function(tree: ast.Module, name: str, rel: str):
    found = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(found) != 1:
        raise FactError(f"{rel} 里 {name} 应当恰有一处，实取 {len(found)} 处")
    return found[0]


def assignments_to(tree_or_fn, name: str) -> list:
    return [node for node in ast.walk(tree_or_fn)
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)]


def module_constants(tree: ast.Module, names, rel: str) -> dict:
    """把 names 解成模块级纯常量的值，顺着赋值链闭包到不动点。

    只吃字面量与字面量之间的运算（``A + B`` 这种拼表写法），不吃函数调用：现场要是把
    词表改成 ``build_words()``，这里读不动就红，比静默少读一格好。
    """
    ns: dict = {}
    pending = set(names)
    for _ in range(8):
        for node in tree.body:
            binding = module_binding(node)
            if binding and binding[0] in pending:
                pending |= (load_names(binding[1]) - BUILTINISH - set(ns))
        for node in tree.body:
            binding = module_binding(node)
            if not binding:
                continue
            name, value = binding
            if name not in pending or name in ns:
                continue
            if load_names(value) - set(ns) - BUILTINISH:
                continue
            try:
                ns[name] = eval(compile(ast.Expression(value),
                                        f"<literal:{rel}:{name}>", "eval"),
                                {"__builtins__": {}}, dict(ns))
            except Exception:
                continue
        pending -= set(ns)
        if not pending:
            break
    if pending:
        raise FactError(f"{rel} 里这些名字解不成纯常量（形状改了？去现场看）：{sorted(pending)}")
    return ns


def exec_module_functions(rel: str, names, root=None, extra=None) -> dict:
    """把现场那几枚函数的**源码本身**搬进一个干净命名空间跑，不 import 那枚模块。

    用于 chat.py：它模块级就造 DocumentRetriever / ModelHandler（顺手连库，实测还会把所在树
    的 chroma_db 写脏一次、被 R134 闸门点名），import 不动；而它的判定规则又不能手抄，
    于是只搬函数源码 + 它引用的模块级纯常量。读不动 = 红，不猜。

    ``extra`` 只给一种名字用：事实源在**别棵树**上的（R379：orchestrator 里那枚
    ``kb_leg_for_caliber`` 引用 nodes.py 的口径词表，在本树解不成常量）。传进来的必须
    自己也是现场读数，不许是手打字——两侧同名不同值当场红。
    """
    extra = dict(extra or {})
    tree = source_tree(rel, root)
    fns = [one_function(tree, name, rel) for name in names]
    params = {a.arg for fn in fns for a in fn.args.args}
    local = params | {fn.name for fn in fns} | BUILTINISH
    need = set()
    for fn in fns:
        need |= load_names(fn) - bound_names(fn) - local
    declared = {bound for node in tree.body if (bound := _binding_name(node))}
    overlap = sorted(declared & set(extra))
    if overlap:
        raise FactError(f"{rel} 里这些名字本树就有赋值，不该由 extra 带入第二份：{overlap}")
    seed = module_constants(tree, need - set(extra), rel)
    seed.update({key: value for key, value in extra.items() if key in need})
    src = "\n".join([f"{key} = {value!r}" for key, value in sorted(seed.items())]
                    + [ast.unparse(fn) for fn in fns])
    ns: dict = {}
    exec(compile(src, f"<rehearsal:{rel}>", "exec"), ns)
    return ns


def exec_statement_block(rel: str, fn_name: str, pick, params, root=None):
    """从现场函数里切一段语句，包成一枚可调用对象 —— 规则本身不抄第二份。

    ``pick`` 负责在语句里定位那一段；定位不到就红，红话说清是哪一段读不动了。
    """
    tree = source_tree(rel, root)
    host = one_function(tree, fn_name, rel)
    stmts = pick(host)
    if not stmts:
        raise FactError(f"{rel}::{fn_name} 里切不出那一段语句：现场分支结构改了，去看着")
    src = "def _slice(" + ", ".join(params) + "):\n" \
        + "".join(textwrap.indent(ast.unparse(st), "    ") + "\n" for st in stmts) \
        + "    return workers\n"
    ns: dict = {}
    exec(compile(src, f"<rehearsal:{rel}::{fn_name}>", "exec"), ns)
    return ns["_slice"]


def symbol_span(rel: str, name: str, root=None) -> str:
    """符号现在的行跨度：--summary 打印的出处用，永远现算，不抄。"""
    tree = source_tree(rel, root)
    node = one_function(tree, name, rel) if not name.isupper() \
        else module_assign_node(tree, name, rel)
    start, end = node.lineno, getattr(node, "end_lineno", None) or node.lineno
    return f"{rel}:{start}" if start == end else f"{rel}:{start}-{end}"


# -------------------- 逐枚读数（每枚一个现场锚点）-----------------------------

def read_hitl_parked(root=None) -> tuple:
    rel = REPO_RELS["orchestrator"]
    value = literal_of(module_assign_node(source_tree(rel, root), "_HITL_PARKED", rel),
                       "_HITL_PARKED", rel)
    if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
        raise FactError(f"{rel}::_HITL_PARKED 不再是字符串元组：挂起集合的读法失效")
    return tuple(value)


def read_hitl_labels(root=None) -> dict:
    rel = REPO_RELS["orchestrator"]
    return dict(literal_of(module_assign_node(source_tree(rel, root), "_HITL_LABELS", rel),
                           "_HITL_LABELS", rel))


def read_route_valid(root=None) -> tuple:
    rel = REPO_RELS["orchestrator"]
    fn = one_function(source_tree(rel, root), "route_main", rel)
    for node in assignments_to(fn, "valid"):
        return tuple(sorted(literal_of(node.value, "route_main#valid", rel)))
    raise FactError(f"{rel}::route_main 里找不到 valid 这张合法腿表")


def read_registered_nodes(root=None) -> list:
    """``_builder.add_node("<腿>", <处理者>)`` 的现场清单，按注册顺序。"""
    rel = REPO_RELS["orchestrator"]
    found = [node for node in ast.walk(source_tree(rel, root))
             if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_node"
             and len(node.args) >= 2 and isinstance(node.args[0], ast.Constant)]
    # ast.walk 给的是广度序，不是源码序；腿的注册顺序只有按行号排才是那句读数
    found.sort(key=lambda node: node.lineno)
    return [(node.args[0].value, ast.unparse(node.args[1])) for node in found]


def read_worker_graphs(root=None) -> tuple:
    valid = set(read_route_valid(root))
    return tuple(name for name, _handler in read_registered_nodes(root) if name in valid)


def read_zero_model_workers(root=None) -> tuple:
    """注册时不走 ``_make_worker_wrapper``（没有 react 子图、不发生成调用）的那些腿。"""
    valid = set(read_route_valid(root))
    return tuple(name for name, handler in read_registered_nodes(root)
                 if name in valid and not handler.startswith("_make_worker_wrapper"))


def read_graph_tools(root=None) -> dict:
    """``x_graph = create_react_agent(model, [tool, ...], ...)`` -> {图变量名: [工具名]}。"""
    rel = REPO_RELS["orchestrator"]
    out = {}
    for node in source_tree(rel, root).body:
        if not (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id.endswith("_graph") and isinstance(node.value, ast.Call)
                and len(node.value.args) > 1
                and isinstance(node.value.args[1], (ast.List, ast.Tuple))):
            continue
        out[node.targets[0].id] = [ast.unparse(item) for item in node.value.args[1].elts]
    return out


def calls_name(node, name: str) -> bool:
    return any(isinstance(call, ast.Call) and getattr(call.func, "id", "") == name
               for call in ast.walk(node))


def read_doc_bearing(root=None) -> tuple:
    """会往证据袋里写 document 证据的腿 = 真能产出 sources 的腿。

    react 腿看它的工具里有没有人调 ``record_document_hits``，直挂腿看它自己的函数体。
    出处不再是两行手抄，而是这条链本身。
    """
    rel_orch = REPO_RELS["orchestrator"]
    writers = {fn.name for fn in ast.walk(source_tree(REPO_RELS["tools"], root))
               if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
               and calls_name(fn, "record_document_hits")}
    graph_tools = read_graph_tools(root)
    tree_orch = source_tree(rel_orch, root)
    valid = set(read_route_valid(root))
    out = []
    for name, handler in read_registered_nodes(root):
        if name not in valid:
            continue
        match = re.match(r"_make_worker_wrapper\((\w+),", handler)
        if match:
            if writers & set(graph_tools.get(match.group(1), [])):
                out.append(name)
            continue
        plain = [fn for fn in ast.walk(tree_orch) if isinstance(fn, ast.FunctionDef)
                 and fn.name == handler]
        if any(calls_name(fn, "record_document_hits") for fn in plain):
            out.append(name)
    if not out:
        raise FactError("现场没有任何腿写 document 证据：sources 那一列失去了意义，去看为什么")
    return tuple(out)


def read_written_source_types(root=None) -> tuple:
    rel = REPO_RELS["evidence"]
    values = {keyword.value.value
              for call in ast.walk(source_tree(rel, root)) if isinstance(call, ast.Call)
              for keyword in call.keywords
              if keyword.arg == "source_type" and isinstance(keyword.value, ast.Constant)}
    return tuple(sorted(values))


def read_document_source_type(root=None) -> str:
    """sources 出口只放行哪一类证据（现场那句 ``!= "document"``）。"""
    rel = REPO_RELS["chat"]
    fn = one_function(source_tree(rel, root), "_document_source_row", rel)
    kept = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Compare) and "source_type" in ast.unparse(node.left):
            for op, comparator in zip(node.ops, node.comparators):
                if isinstance(op, ast.NotEq) and isinstance(comparator, ast.Constant):
                    kept.add(comparator.value)
    if len(kept) != 1:
        raise FactError(f"{rel}::_document_source_row 的放行判据不唯一：{sorted(kept)}")
    return kept.pop()


def read_getenv_default(rel: str, env_name: str, cast, root=None):
    """现场 ``os.getenv("<env>", "<默认>")`` 的默认值 —— 开关的默认态也是源码事实。"""
    values = [literal_of(call.args[1], f'getenv("{env_name}") 默认值', rel)
              for call in ast.walk(source_tree(rel, root))
              if isinstance(call, ast.Call) and ast.unparse(call.func).endswith("getenv")
              and call.args and getattr(call.args[0], "value", "") == env_name
              and len(call.args) >= 2 and isinstance(call.args[1], ast.Constant)]
    if not values:
        raise FactError(f'{rel} 里读不到 getenv("{env_name}") 的默认值')
    if len({str(item) for item in values}) != 1:
        raise FactError(f"{rel} 里 {env_name} 的默认值不止一枚：{sorted(map(str, values))}")
    return cast(values[0])


def read_rate_limit(root=None) -> int:
    """限流口径：调用点的实参与被调者的默认值必须报同一个数。"""
    rel = REPO_RELS["chat"]
    calls = {keyword.value.value
             for call in ast.walk(source_tree(rel, root))
             if isinstance(call, ast.Call) and getattr(call.func, "id", "") == "check_rate_limit"
             for keyword in call.keywords
             if keyword.arg == "max_per_minute" and isinstance(keyword.value, ast.Constant)}
    cache_rel = REPO_RELS["cache"]
    fn = one_function(source_tree(cache_rel, root), "check_rate_limit", cache_rel)
    args = list(fn.args.args) + list(getattr(fn.args, "kwonlyargs", []))
    defaults = list(fn.args.defaults) + list(getattr(fn.args, "kw_defaults", []))
    default = None
    for arg, node in zip(args[len(args) - len(defaults):], defaults):
        if arg.arg == "max_per_minute":
            default = literal_of(node, "check_rate_limit 默认", cache_rel)
    found = calls | ({default} if default is not None else set())
    if len(found) != 1:
        raise FactError(f"限流口径不唯一：调用点 {sorted(map(str, calls))} 与默认值 {default!r}")
    return int(found.pop())


def read_cache_key_shape(root=None) -> dict:
    """答案缓存键的形状（摘要里那句“键=md5(scope)[:12]+…”的现场侧）。"""
    rel = REPO_RELS["cache"]
    tree = source_tree(rel, root)
    widths, digests, stripped = {}, set(), {}
    for fn_name in ("_hash", "_scope_part"):
        fn = one_function(tree, fn_name, rel)
        widths[fn_name] = [node.upper.value for node in ast.walk(fn)
                           if isinstance(node, ast.Slice) and isinstance(node.upper, ast.Constant)]
        digests |= {node.value.func.attr for node in ast.walk(fn)
                    if isinstance(node, ast.Attribute) and node.attr == "hexdigest"
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and isinstance(node.value.func.value, ast.Name)
                    and node.value.func.value.id == "hashlib"}
        stripped[fn_name] = any(isinstance(node, ast.Call)
                                and getattr(node.func, "attr", "") == "strip"
                                for node in ast.walk(fn))
    key_fn = one_function(tree, "_answer_key", rel)
    prefix = ""
    for node in ast.walk(key_fn):
        if isinstance(node, ast.JoinedStr) and node.values \
                and isinstance(node.values[0], ast.Constant):
            prefix = node.values[0].value
    return {"digest": tuple(sorted(digests)),
            "width_scope": widths["_scope_part"][0] if widths["_scope_part"] else None,
            "width_hash": widths["_hash"][0] if widths["_hash"] else None,
            "question_stripped": bool(stripped["_hash"]),
            "prefix": prefix,
            "span": f"{rel}:{key_fn.lineno}-{key_fn.end_lineno}"}


def read_kw_tables(root=None) -> dict:
    """route_main 里那四张关键词兜底表 —— 判据丁要等值比对的现场侧。"""
    rel = REPO_RELS["orchestrator"]
    fn = one_function(source_tree(rel, root), "route_main", rel)
    wanted = {"chart_kw", "data_kw", "export_kw", "doc_kw"}
    out = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in wanted:
            out[node.targets[0].id] = list(literal_of(node.value, node.targets[0].id, rel))
    if wanted - set(out):
        raise FactError(f"{rel}::route_main 里少了关键词兜底表：{sorted(wanted - set(out))}")
    return out


def _route_outer_if(host):
    """route_main 里"计划优先 / 关键词兜底"那一分岔：定位不到就交回 None，由调用方红。"""
    for node in host.body:
        if isinstance(node, ast.If) and "planned_workers" in ast.unparse(node.test):
            return node
    return None


def _route_tail(host, rel):
    """route_main 分岔**之后**的收尾两支（R206a 补 doc、R42 弃权轮补 doc）。

    🔴 R379 格三：基点的等值门只切到分派两支为止，这两支不在门里——现场在后面还会改派
    腿，镜像却停在前面，那 105 题 diffs=0 属巧合。两段各按一枚锚点定位（一条调用名、一个
    判据名），现场把这两段搬走、删掉或换了先后，这里红，而不是悄悄少切一段。
    """
    outer = _route_outer_if(host)
    if outer is None:
        raise FactError(f"{rel}::route_main 找不到『计划优先/关键词兜底』那一分岔")
    index = host.body.index(outer)

    def first(predicate, what):
        for position in range(index + 1, len(host.body)):
            if predicate(host.body[position]):
                return position
        raise FactError(f"{rel}::route_main 分岔之后找不到『{what}』那一段：收尾两支的形状改了")

    caliber = first(lambda node: "kb_leg_for_caliber" in ast.unparse(node),
                    "R206a 口径题补读腿")
    # R42 那一支的锚点是 abstained——这条规则的定义就是"只接管弃权轮"（现场那句
    # if not workers and abstained and ...）。锚点不许吃 classify_route：反证刀摘掉的正是它。
    r42 = first(lambda node: isinstance(node, ast.If)
                and "abstained" in ast.unparse(node.test), "R42 弃权轮补派 doc")
    if r42 <= caliber:
        raise FactError(f"{rel}::route_main 收尾两支的先后换了（R206a 必须在 R42 之前）")
    return host.body[caliber:r42 + 1]


def route_tail_statements(root=None):
    rel = REPO_RELS["orchestrator"]
    return _route_tail(one_function(source_tree(rel, root), "route_main", rel), rel)


def read_route_branch_slices(root=None):
    """切 route_main 的分派两段（计划优先支 / 关键词兜底支）成可调用对象。"""
    rel = REPO_RELS["orchestrator"]

    def outer_if(host):
        return _route_outer_if(host)

    tables = ("chart_kw", "data_kw", "export_kw", "doc_kw")
    kw = exec_statement_block(
        rel, "route_main", lambda host: (outer_if(host).orelse if outer_if(host) else []),
        ["workers", "intent_text", "planned_workers", *tables], root)
    plan = exec_statement_block(
        rel, "route_main", lambda host: (outer_if(host).body if outer_if(host) else []),
        ["planned_workers", "intent_text", *tables], root)
    return kw, plan


#: 收尾两支要多带三枚现场名字：规则本体、日志出口、档位判别器。
TAIL_PARAMS = ("abstained", "kb_leg_for_caliber", "logger", "classify_route", "LANE_QA")


class _RouteLogSink:
    """切片里的 ``logger.info`` 落地处：本件不 import orchestrator，日志一律收进这只桶。

    它不是事实源，只是让现场那两句日志语句能在本进程里跑一遍——桶里攒了什么不做判据
    （攒多少随环境漂，格五那一条）。
    """

    def __init__(self) -> None:
        self.lines: list = []

    def info(self, message) -> None:
        self.lines.append(str(message))

    def warning(self, message) -> None:
        self.lines.append(str(message))


ROUTE_LOG_SINK = _RouteLogSink()


def read_route_tail_slices(root=None):
    """切"分派那一支 + 收尾两支"整段：等值门由此覆盖 route_main 定派腿的全部四段。"""
    rel = REPO_RELS["orchestrator"]
    tables = ("chart_kw", "data_kw", "export_kw", "doc_kw")
    kw = exec_statement_block(
        rel, "route_main",
        lambda host: ((_route_outer_if(host).orelse if _route_outer_if(host) else [])
                      + _route_tail(host, rel)),
        ["workers", "intent_text", "planned_workers", *tables, *TAIL_PARAMS], root)
    plan = exec_statement_block(
        rel, "route_main",
        lambda host: ((_route_outer_if(host).body if _route_outer_if(host) else [])
                      + _route_tail(host, rel)),
        ["planned_workers", "intent_text", *tables, *TAIL_PARAMS], root)
    return kw, plan


def read_side_effect_legs(root=None) -> tuple:
    """R206a 那条"副作用腿不改派"的腿表（现场 ``_SIDE_EFFECT_LEGS``，带注解的模块级常量）。"""
    rel = REPO_RELS["orchestrator"]
    value = literal_of(module_assign_node(source_tree(rel, root), "_SIDE_EFFECT_LEGS", rel),
                       "_SIDE_EFFECT_LEGS", rel)
    if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
        raise FactError(f"{rel}::_SIDE_EFFECT_LEGS 不再是字符串元组：副作用腿那一格读不动")
    return tuple(value)


def read_caliber_markers(root=None) -> tuple:
    """口径词表 = 现场 ``KB_CALIBER_MARKERS`` 那枚赋值表达式本身，不抄第三张表。

    它由 nodes.py 里两张已裁定闭集求并而来，``module_constants`` 解不动那种 ``tuple(
    dict.fromkeys(...))`` 写法（只吃字面量之间的运算），所以这里搬**表达式本身**进干净 ns
    跑，再与进程里 import 到的同名对象交叉核对——只看 import 那一侧对影子副本的漂移是瞎的
    （``read_offline_texts`` 同一形状，同一理由）。
    """
    rel = REPO_RELS["nodes"]
    tree = source_tree(rel, root)
    value = module_assign_node(tree, "KB_CALIBER_MARKERS", rel)
    ns: dict = module_constants(tree, load_names(value) - BUILTINISH, rel)
    exec(compile("KB_CALIBER_MARKERS = " + ast.unparse(value),
                 f"<rehearsal:{rel}::KB_CALIBER_MARKERS>", "exec"), ns)
    out = tuple(ns["KB_CALIBER_MARKERS"])
    if not out:
        raise FactError(f"{rel}::KB_CALIBER_MARKERS 解出来是空表：口径补派那一支失去了词表")
    if root is None and out != tuple(KB_CALIBER_MARKERS):
        raise FactError(
            f"{rel}::KB_CALIBER_MARKERS 源码侧与 import 侧不等："
            f"源码={as_text(out)} 进程={as_text(tuple(KB_CALIBER_MARKERS))}"
            "（字节码过期或 sys.path 指到别棵树，去看现场再跑）")
    return out


def read_caliber_rule(root=None):
    """"口径题的读腿没出门就补一条"这条规则的本体 = 现场 ``kb_leg_for_caliber`` 源码。"""
    rel = REPO_RELS["orchestrator"]
    return exec_module_functions(rel, ("kb_leg_for_caliber",), root,
                                 extra={"KB_CALIBER_MARKERS": read_caliber_markers(root)}
                                 )["kb_leg_for_caliber"]


def read_min_answer_default(root=None) -> int:
    """``MODEL_MIN_ANSWER_TOKENS`` 的默认值真身（现场那枚模块级整数字面量）。

    🔴 R379 格一：从前 --summary 那一行的两侧都是同一个运行期读数，"DEFAULT" 半句永远
    读不出漂移。真身住在本件本来就 import 的轻件里，从这里现读才算读到默认值。
    """
    rel = REPO_RELS["model_budget"]
    value = literal_of(module_assign_node(source_tree(rel, root),
                                          "DEFAULT_MIN_ANSWER_TOKENS", rel),
                       "DEFAULT_MIN_ANSWER_TOKENS", rel)
    if isinstance(value, bool) or not isinstance(value, int):
        raise FactError(f"{rel}::DEFAULT_MIN_ANSWER_TOKENS 不再是整数字面量：{value!r}")
    return int(value)


def read_rewrite_rule(root=None):
    """“这一句算不算追问” = chat.py 那两枚判定函数的现场源码本身（本件不抄第二套词表）。"""
    rel = REPO_RELS["chat"]
    return exec_module_functions(rel, ("_starts_with_deictic", "_is_followup"), root)["_is_followup"]


def read_rewrite_prefixes(root=None) -> tuple:
    rel = REPO_RELS["chat"]
    return tuple(literal_of(module_assign_node(source_tree(rel, root), "_FOLLOWUP_PREFIXES", rel),
                            "_FOLLOWUP_PREFIXES", rel))


def read_rewrite_guard_codes(root=None) -> tuple:
    """改写腿拒收的罐头回复码（现场那张 canned_reply_reasons 的键）。"""
    rel = REPO_RELS["chat"]
    fn = one_function(source_tree(rel, root), "_rewrite_followup", rel)
    for node in assignments_to(fn, "canned_reply_reasons"):
        if not isinstance(node.value, ast.Dict) or any(
                not isinstance(key, ast.Name) for key in node.value.keys):
            raise FactError(f"{rel}::_rewrite_followup 的 canned_reply_reasons 形状改了")
        # 键是 app/common/model_handler.py 里那两枚码的符号名：取名字，不取字面量，
        # 改名片刻读不出来就红，不会静默少一档。
        return tuple(sorted(key.id for key in node.value.keys))
    raise FactError(f"{rel}::_rewrite_followup 不再区分罐头改写：回填那一格的读法要改")


def read_park_texts(root=None) -> dict:
    """挂起文案 = 现场 hitl_park_text 的拼法 + 现场 _HITL_LABELS，逐字来自两棵源码树。"""
    rel = REPO_RELS["chat"]
    builder = exec_module_functions(rel, ("hitl_park_text",), root)["hitl_park_text"]
    labels, parked = read_hitl_labels(root), read_hitl_parked(root)
    for leg in parked:
        if leg not in labels:
            raise FactError(f"_HITL_PARKED 里的 {leg} 在 _HITL_LABELS 里没有名字：文案算不出来")
    texts = {"park_" + leg: builder({"labels": [labels[leg]]}) for leg in parked}
    if len(parked) > 1:
        texts["park_both"] = builder({"labels": [labels[leg] for leg in parked]})
    return texts


def read_chat_assignment_literal(name: str, root=None) -> str:
    rel = REPO_RELS["chat"]
    found = {node.value.value for node in assignments_to(source_tree(rel, root), name)
             if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)}
    if len(found) != 1:
        raise FactError(f"{rel} 里 {name} 的字面量不唯一（实取 {len(found)} 枚）")
    return found.pop()


def read_error_event_text(root=None) -> str:
    """``sse_event("error", {"content": "<一句 literal>"})`` 里那句超时文案。"""
    rel = REPO_RELS["chat"]
    texts = set()
    for call in ast.walk(source_tree(rel, root)):
        if not (isinstance(call, ast.Call) and getattr(call.func, "id", "") == "sse_event"
                and call.args and getattr(call.args[0], "value", "") == "error"
                and len(call.args) > 1 and isinstance(call.args[1], ast.Dict)):
            continue
        texts |= {value.value for key, value in zip(call.args[1].keys, call.args[1].values)
                  if getattr(key, "value", "") == "content"
                  and isinstance(value, ast.Constant) and isinstance(value.value, str)}
    if len(texts) != 1:
        raise FactError(f"{rel} 里 error 事件的固定文案不唯一：{sorted(texts)}")
    return texts.pop()


def read_approval_texts(root=None) -> dict:
    """审批缺料那几句：前缀/分隔/后缀取自现场 f-string，缺项名取自现场 append 顺序。"""
    rel = REPO_RELS["orchestrator"]
    fn = one_function(source_tree(rel, root), "_approval_worker_node", rel)
    pairs = []
    for node in fn.body:
        if not (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and "is None" in ast.unparse(node.test)):
            continue
        variable = ast.unparse(node.test.left)
        for call in node.body:
            if isinstance(call, ast.Expr) and getattr(call.value.func, "attr", "") == "append" \
                    and call.value.args and isinstance(call.value.args[0], ast.Constant):
                pairs.append((variable, call.value.args[0].value))
    guard = next((node for node in fn.body
                  if isinstance(node, ast.If) and ast.unparse(node.test) == "missing"), None)
    if guard is None or not pairs:
        raise FactError(f"{rel}::_approval_worker_node 的缺料分支读不动（pairs={pairs}）")
    answer = next((node for node in assignments_to(guard, "answer")
                   if isinstance(node.value, ast.JoinedStr)), None)
    if answer is None:
        raise FactError(f"{rel}::_approval_worker_node 的缺料文案不再是 f-string")
    prefix, suffix, sep = "", "", "、"
    for piece in answer.value.values:
        if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
            if not prefix:
                prefix = piece.value
            else:
                suffix += piece.value
        elif isinstance(piece, ast.Call) and getattr(piece.func, "attr", "") == "join" \
                and isinstance(piece.func.value, ast.Constant):
            sep = piece.func.value.value
    variants = {}
    for mask in range(1, 1 << len(pairs)):
        chosen = [label for index, (_var, label) in enumerate(pairs) if mask >> index & 1]
        keys = tuple(sorted(var for index, (var, _label) in enumerate(pairs) if mask >> index & 1))
        variants[keys] = prefix + sep.join(chosen) + suffix
    return variants


#: 离线罐头那四句：本件 import 侧的名字 -> nodes.py 模块级常量的名字。
OFFLINE_NAMES = {
    "offline_reimburse": "OFFLINE_REIMBURSEMENT_ANSWER",
    "offline_analysis": "OFFLINE_ANALYSIS_ANSWER",
    "offline_generic": "OFFLINE_GENERIC_ANSWER",
    "offline_stream": "OFFLINE_STREAM_CHUNK",
}


def read_offline_texts(root=None) -> dict:
    """离线那四句罐头：从 nodes.py 源码读，再与进程里 import 到的同名符号交叉核对。

    🔴 为什么不学别处"只走 import"就算派生：判据 戊 的尺子自证改的是磁盘上的影子副本，
    而 import 拿到的是进程一开始就吃进的那棵——只认 import 的那一格对影子漂移天生是瞎的。
    两侧都读还有个好处：源码与 import 不等（字节码过期、sys.path 指到别棵树）当场红。
    取值的形状仍由现场把关：那四枚必须是模块级纯字面量，改成函数调用就解不动、就红。
    """
    rel = REPO_RELS["nodes"]
    read = module_constants(source_tree(rel, root), set(OFFLINE_NAMES.values()), rel)
    out = {key: read[name] for key, name in OFFLINE_NAMES.items()}
    if root is not None:
        return out
    from_process = {key: globals()[name] for key, name in OFFLINE_NAMES.items()}
    if out != from_process:
        moved = [key for key in sorted(out) if out[key] != from_process[key]]
        raise FactError(
            f"{rel}::{'/'.join(sorted(OFFLINE_NAMES.values()))} 源码侧与本件 import 侧不等："
            f"{moved}（源码={as_text([out[key] for key in moved])} "
            f"进程={as_text([from_process[key] for key in moved])}）")
    return out


def read_intent_text_rule(root=None):
    """把现场 ``_intent_text`` 连它自己那枚 ``_DOC_REFERENCE`` 一起搬进干净 ns 跑。

    从前本件抄的是"它那次 sub"的写法（模式串派生了，替换动作没派生）。规则不许有第二份：
    现场怎么剥，本件就怎么剥，搬源码本身。
    """
    rel = REPO_RELS["orchestrator"]
    tree = source_tree(rel, root)
    # module_assign_node 给的是赋值**右端**，所以这里自己把名字绑回去（形状仍来自现场）
    value = module_assign_node(tree, "_DOC_REFERENCE", rel)
    fn = one_function(tree, "_intent_text", rel)
    ns: dict = {"re": re}
    exec(compile("_DOC_REFERENCE = " + ast.unparse(value) + "\n" + ast.unparse(fn),
                 f"<rehearsal:{rel}::_intent_text>", "exec"), ns)
    return ns["_intent_text"]


def read_doc_reference_pattern(root=None) -> str:
    rel = REPO_RELS["orchestrator"]
    call = module_assign_node(source_tree(rel, root), "_DOC_REFERENCE", rel)
    if not (isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "compile" and call.args):
        raise FactError(f"{rel}::_DOC_REFERENCE 不再是 re.compile(字面量) 的形状")
    return literal_of(call.args[0], "_DOC_REFERENCE", rel)


def read_judge_is_substring(root=None) -> bool:
    """``_is_correct`` 判分的仍是“子串在正文里”——假绿通道那一列靠这条才算得出。"""
    rel = REPO_RELS["eval"]
    fn = one_function(source_tree(rel, root), "_is_correct", rel)
    return any(isinstance(node, ast.Compare) and any(isinstance(op, ast.In) for op in node.ops)
               and "text" in ast.unparse(node) for node in ast.walk(fn))


def read_reflect_redo_branches(root=None) -> int:
    rel = REPO_RELS["nodes"]
    fn = one_function(source_tree(rel, root), "reflect_node", rel)
    return sum(1 for node in assignments_to(fn, "redo")
               if isinstance(node.value, ast.Constant) and node.value.value is True)


def read_empty_route_target(root=None) -> str:
    """route_main 收尾那句“本轮没人出门 → 去哪儿”。"""
    rel = REPO_RELS["orchestrator"]
    fn = one_function(source_tree(rel, root), "route_main", rel)
    for node in fn.body:
        if isinstance(node, ast.If) and ast.unparse(node.test) == "not workers" \
                and isinstance(node.body[-1], ast.Return):
            return literal_of(node.body[-1].value, "route_main 空派发的去向", rel)
    raise FactError(f"{rel}::route_main 收尾不再按“空派发 → 去向”收尾：①那格失败模式的读法要改")


def read_interrupt_before(root=None) -> tuple:
    rel = REPO_RELS["orchestrator"]
    for call in ast.walk(source_tree(rel, root)):
        if not isinstance(call, ast.Call):
            continue
        for keyword in call.keywords:
            if keyword.arg == "interrupt_before":
                text = ast.unparse(keyword.value)
                if text.startswith("list("):
                    return read_hitl_parked(root), text[5:-1].strip()
                raise FactError(f"{rel} 编译期 interrupt_before 不再引用模块级元组：{text}")
    raise FactError(f"{rel} 里找不到编译期 interrupt_before")


def read_worker_empty_answer_fallback(root=None) -> bool:
    """react 腿找不到 final 就先交空串：下界腿数那一格靠它。"""
    rel = REPO_RELS["orchestrator"]
    fn = one_function(source_tree(rel, root), "_make_worker_wrapper", rel)
    return any(isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "final"
               and isinstance(node.value, ast.Constant) and node.value.value == ""
               for node in ast.walk(fn))


def read_planner_workers(root=None) -> tuple:
    rel = REPO_RELS["planner"]
    fn = one_function(source_tree(rel, root), "build_task_plan", rel)
    calls = [call for call in ast.walk(fn)
             if isinstance(call, ast.Call) and getattr(call.func, "id", "") == "_task"
             and call.args and isinstance(call.args[0], ast.Constant)]
    calls.sort(key=lambda call: call.lineno)      # 同上：排腿顺序就是 planner 的写法顺序
    out = []
    for call in calls:
        if call.args[0].value not in out:
            out.append(call.args[0].value)
    if not out:
        raise FactError(f"{rel}::build_task_plan 里排不出腿了：planner 的读法要改")
    return tuple(out)


#: 假绿通道那三句审批文案 -> 现场 ``if <变量> is None`` 的那两枚变量名。变量一改名，
#: 这里就取不到值（红），而不是安静地少算一句罐头。
APPROVAL_SCENARIOS = {
    "approval_missing_both": ("amount", "standard"),
    "approval_missing_standard": ("standard",),
    "approval_missing_amount": ("amount",),
}

FACT_READERS = {
    "HITL_PARKED": read_hitl_parked,
    "HITL_LABELS": read_hitl_labels,
    "ROUTE_VALID_WORKERS": read_route_valid,
    "WORKER_GRAPHS": read_worker_graphs,
    "ZERO_MODEL_WORKERS": read_zero_model_workers,
    "DOC_BEARING": read_doc_bearing,
    "WRITTEN_SOURCE_TYPES": read_written_source_types,
    "DOCUMENT_SOURCE_TYPE": read_document_source_type,
    "REQUEST_BUDGET_SECONDS": lambda root=None: read_getenv_default(
        REPO_RELS["chat"], "CHAT_REQUEST_TIMEOUT", float, root),
    "RATE_LIMIT_PER_MINUTE": read_rate_limit,
    "ADAPTER_MIN_GAP_SECONDS": lambda root=None: read_getenv_default(
        REPO_RELS["transport"], "EVAL_MIN_GAP_SECONDS", float, root),
    "CACHE_TTL_SECONDS": lambda root=None: int(literal_of(
        module_assign_node(source_tree(REPO_RELS["cache"], root),
                           "DEFAULT_ANSWER_CACHE_TTL_SECONDS", REPO_RELS["cache"]),
        "DEFAULT_ANSWER_CACHE_TTL_SECONDS", REPO_RELS["cache"])),
    "CACHE_KEY_SHAPE": read_cache_key_shape,
    "KW_TABLES": read_kw_tables,
    "REWRITE_PREFIXES": read_rewrite_prefixes,
    "REWRITE_GUARD_CODES": read_rewrite_guard_codes,
    "PARK_TEXTS": read_park_texts,
    "NO_ANSWER_TEXT": lambda root=None: read_chat_assignment_literal("failure_text", root),
    "TIMEOUT_TEXT": read_error_event_text,
    "APPROVAL_TEXTS": read_approval_texts,
    "MODEL_UNAVAILABLE_REPLY": lambda root=None: str(literal_of(
        module_assign_node(source_tree(REPO_RELS["model_handler"], root),
                           "MODEL_UNAVAILABLE_REPLY", REPO_RELS["model_handler"]),
        "MODEL_UNAVAILABLE_REPLY", REPO_RELS["model_handler"])),
    "BLANK_SENTINEL": lambda root=None: read_getenv_default(
        REPO_RELS["transport"], "EVAL_BLANK_SENTINEL", str, root),
    "OFFLINE_TEXTS": read_offline_texts,
    "DOC_REFERENCE_PATTERN": read_doc_reference_pattern,
    "PLANNER_WORKERS": read_planner_workers,
    "JUDGE_IS_SUBSTRING": read_judge_is_substring,
    "REFLECT_REDO_BRANCHES": read_reflect_redo_branches,
    "EMPTY_ROUTE_TARGET": read_empty_route_target,
    "INTERRUPT_BEFORE": read_interrupt_before,
    "WORKER_EMPTY_ANSWER_FALLBACK": read_worker_empty_answer_fallback,
    "ANSWER_CACHE_SPAN": lambda root=None: symbol_span(REPO_RELS["cache"], "_answer_key", root),
    "APPROVAL_WORKER_SPAN": lambda root=None: symbol_span(
        REPO_RELS["orchestrator"], "_approval_worker_node", root),
    # R379 格一：地板的默认值真身。它以前只以"运行期读数"的身份出现一次，抄本那一侧是空气。
    "MIN_ANSWER_TOKENS_DEFAULT": read_min_answer_default,
    # R379 格三：route_main 收尾两支（R206a 口径补 doc / R42 弃权补 doc）的两枚输入。
    "SIDE_EFFECT_LEGS": read_side_effect_legs,
    "CALIBER_MARKERS": read_caliber_markers,
}

FACT_ANCHORS = {
    "HITL_PARKED": "app/agents/orchestrator.py::_HITL_PARKED",
    "HITL_LABELS": "app/agents/orchestrator.py::_HITL_LABELS",
    "ROUTE_VALID_WORKERS": "app/agents/orchestrator.py::route_main#valid",
    "WORKER_GRAPHS": "app/agents/orchestrator.py::add_node(腿) ∩ route_main#valid",
    "ZERO_MODEL_WORKERS": "app/agents/orchestrator.py::add_node(腿, 非 react 处理者)",
    "DOC_BEARING": "app/agents/orchestrator.py + app/agents/tools.py 的 record_document_hits 调用点",
    "WRITTEN_SOURCE_TYPES": "app/agents/evidence.py::source_type= 各写入点",
    "DOCUMENT_SOURCE_TYPE": "app/api/v1/chat.py::_document_source_row",
    "REQUEST_BUDGET_SECONDS": "app/api/v1/chat.py::getenv(CHAT_REQUEST_TIMEOUT) 默认",
    "RATE_LIMIT_PER_MINUTE": "app/api/v1/chat.py::check_rate_limit(max_per_minute=) 与 app/common/cache.py 默认",
    "ADAPTER_MIN_GAP_SECONDS": "scripts/eval_transport_ask_v2.py::getenv(EVAL_MIN_GAP_SECONDS) 默认",
    "CACHE_TTL_SECONDS": "app/common/cache.py::DEFAULT_ANSWER_CACHE_TTL_SECONDS",
    "CACHE_KEY_SHAPE": "app/common/cache.py::_answer_key/_hash/_scope_part",
    "KW_TABLES": "app/agents/orchestrator.py::route_main#chart_kw/data_kw/export_kw/doc_kw",
    "REWRITE_PREFIXES": "app/api/v1/chat.py::_FOLLOWUP_PREFIXES",
    "REWRITE_GUARD_CODES": "app/api/v1/chat.py::_rewrite_followup#canned_reply_reasons",
    "PARK_TEXTS": "app/api/v1/chat.py::hitl_park_text + orchestrator.py::_HITL_LABELS",
    "NO_ANSWER_TEXT": "app/api/v1/chat.py::failure_text 赋值",
    "TIMEOUT_TEXT": "app/api/v1/chat.py::sse_event(error) 固定文案",
    "APPROVAL_TEXTS": "app/agents/orchestrator.py::_approval_worker_node#missing",
    "MODEL_UNAVAILABLE_REPLY": "app/common/model_handler.py::MODEL_UNAVAILABLE_REPLY",
    "BLANK_SENTINEL": "scripts/eval_transport_ask_v2.py::getenv(EVAL_BLANK_SENTINEL) 默认",
    "OFFLINE_TEXTS": "app/agents/nodes.py::OFFLINE_* 四枚常量（源码现读，并与 import 侧交叉核对）",
    "DOC_REFERENCE_PATTERN": "app/agents/orchestrator.py::_DOC_REFERENCE",
    "PLANNER_WORKERS": "app/agents/planner.py::build_task_plan#_task(腿)",
    "JUDGE_IS_SUBSTRING": "app/quality/eval.py::_is_correct",
    "REFLECT_REDO_BRANCHES": "app/agents/nodes.py::reflect_node#redo",
    "EMPTY_ROUTE_TARGET": "app/agents/orchestrator.py::route_main 收尾",
    "INTERRUPT_BEFORE": "app/agents/orchestrator.py::compile(interrupt_before=)",
    "WORKER_EMPTY_ANSWER_FALLBACK": "app/agents/orchestrator.py::_make_worker_wrapper#final",
    "ANSWER_CACHE_SPAN": "app/common/cache.py::_answer_key 行跨度",
    "APPROVAL_WORKER_SPAN": "app/agents/orchestrator.py::_approval_worker_node 行跨度",
    "REWRITE_RULE": "app/api/v1/chat.py::_starts_with_deictic/_is_followup 源码切片",
    "ROUTE_BRANCHES": "app/agents/orchestrator.py::route_main 分派两段的源码切片",
    "INTENT_TEXT_RULE": "app/agents/orchestrator.py::_intent_text +::_DOC_REFERENCE",
    "CACHE_KEY_PROSE": "app/common/cache.py::_answer_key/_hash/_scope_part",
    "MIN_ANSWER_TOKENS_DEFAULT": "app/common/model_budget.py::DEFAULT_MIN_ANSWER_TOKENS",
    "SIDE_EFFECT_LEGS": "app/agents/orchestrator.py::_SIDE_EFFECT_LEGS",
    "CALIBER_MARKERS": "app/agents/nodes.py::KB_CALIBER_MARKERS",
    "CALIBER_RULE": "app/agents/orchestrator.py::kb_leg_for_caliber 源码切片",
    "ROUTE_TAIL_SLICES": "app/agents/orchestrator.py::route_main 分岔之后到 R42 那一段的源码切片",
    "CALIBRATED_FLOOR_TOKENS": "app/common/model_budget.py::DEFAULT_MIN_ANSWER_TOKENS",
}


def as_text(value) -> str:
    """读数进比对与红话时的统一文本形态（元组/字典/标量都要能一眼看出差在哪枚）。"""
    if isinstance(value, (tuple, list)):
        return "(" + ", ".join(as_text(item) for item in value) + ")"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{as_text(key)}: {as_text(item)}" for key, item in sorted(
            value.items(), key=lambda kv: str(kv[0]))) + "}"
    return repr(value)


def diff_terms(copy, live) -> str:
    """“差在哪一枚”而不是只报“集合不等”。"""
    gone = [item for item in copy if item not in live]
    added = [item for item in live if item not in copy]
    bits = []
    if gone:
        bits.append("抄本多出 " + "、".join(as_text(item) for item in gone))
    if added:
        bits.append("现场多出 " + "、".join(as_text(item) for item in added))
    if not bits and as_text(copy) != as_text(live):
        bits.append("同枚不同形（顺序或值）")
    return ("；".join(bits) if bits else "逐枚相同") + f"：从 {as_text(copy)} 变到 {as_text(live)}"


def live_facts(root=None) -> dict:
    return {name: reader(root) for name, reader in FACT_READERS.items()}


def fact_snapshot(root=None) -> dict:
    """每格读数的文本形态。影子副本自证（判据戊）就吃这一枚 + drift_between()。"""
    out = {}
    for name, reader in FACT_READERS.items():
        try:
            out[name] = as_text(reader(root))
        except FactError as exc:
            out[name] = "读不动：" + str(exc)
    for name, value in COPIES.items():
        out[name] = as_text(value)
    return out


def copy_drift(root=None) -> list:
    """抄本 vs 现场（判据丁）。返回红话清单，空表 = 这一扇门量得准。

    🔴 这里不印警告继续算：调用方（main／常驻件）拿到非空清单必须停下来。
    """
    facts = live_facts(root)
    tables = facts["KW_TABLES"]
    cells = {"KW_CHART": "chart_kw", "KW_DATA": "data_kw",
             "KW_EXPORT": "export_kw", "KW_DOC": "doc_kw"}
    lines = []
    for cell, live_name in cells.items():
        copy, live = list(COPIES[cell]), tables[live_name]
        if copy != live:
            lines.append(f"{cell} 抄本与现场 {FACT_ANCHORS['KW_TABLES']} 不等"
                         f"（{live_name}）{diff_terms(copy, live)}")
    floor_live = facts["MIN_ANSWER_TOKENS_DEFAULT"]
    calib = COPIES["CALIBRATED_FLOOR_TOKENS"]
    if calib != floor_live:
        lines.append(
            f"CALIBRATED_FLOOR_TOKENS 抄本与现场 "
            f"{FACT_ANCHORS['MIN_ANSWER_TOKENS_DEFAULT']} 不等："
            f"从 {calib} 变到 {floor_live}（每题 {MEASURED_SECONDS_PER_CALL} s 那把尺子是在"
            f"{calib} tok 地板上量到的；地板改了要么重测再登记，要么把这一格改成派生——"
            "不许只把抄本改成今天的数）")
    shape = facts["CACHE_KEY_SHAPE"]
    claim = f"md5(scope)[:{shape['width_scope']}]+md5(问题.strip())[:{shape['width_hash']}]"
    copy = COPIES["CACHE_KEY_PROSE"]
    if shape["digest"] != ("md5",) or not shape["question_stripped"] or copy != claim:
        lines.append(
            f"CACHE_KEY_PROSE 抄本与现场 {FACT_ANCHORS['CACHE_KEY_SHAPE']} 不等："
            f"从 {copy!r} 变到 {claim!r}"
            f"（现场 digest={as_text(shape['digest'])} 去空白={shape['question_stripped']}）")
    return lines


def branch_equivalence(rows, root=None) -> list:
    """本件的镜像分支与现场切片必须逐题同形（规则和词表都不抄第二份）。

    四段一起量：分派那两支（计划优先 / 关键词兜底）与 R379 补进来的收尾那两支
    （R206a 口径补 doc / R42 弃权补 doc）。收尾那一圈吃的是"分派结果 + 收尾"整段切片，
    所以动分派段会两格一起红、只动收尾段则只有收尾那一格红——红话各自点名出处。
    """
    kw_live, plan_live = read_route_branch_slices(root)
    kw_final, plan_final = read_route_tail_slices(root)
    tables = read_kw_tables(root)
    order = ("chart_kw", "data_kw", "export_kw", "doc_kw")
    caliber = (read_caliber_rule(root), ROUTE_LOG_SINK, classify_route, LANE_QA)
    lines = []
    for row in rows:
        question, planned = str(row["question"]), plan_workers(str(row["question"]))
        intent = _intent(question)
        cells = [tables[name] for name in order]
        kw_mine = kw_path_workers(question, planned)
        plan_mine = plan_path_workers(planned, question)
        for label, mine, live in (
                ("关键词兜底路", kw_mine, kw_live([], intent, planned, *cells)),
                ("计划优先路", plan_mine, plan_live(planned, intent, *cells))):
            if mine != live:
                lines.append(f"{row['id']} {label} 本件={as_text(mine)} 现场={as_text(live)}"
                             f"（{FACT_ANCHORS['ROUTE_BRANCHES']}）")
        # 收尾两支（R379 格三）：本件 = 镜像分派 + 镜像收尾；现场 = 分岔到 R42 的整段切片
        tail = [True, *caliber]        # intent_text 已在分派那五个入参里，收尾只多带五枚
        for label, mine, live in (
                ("收尾·关键词路", route_final_workers(intent, list(kw_mine), True),
                 kw_final([], intent, planned, *cells, *tail)),
                ("收尾·计划优先路", route_final_workers(intent, list(plan_mine), True),
                 plan_final(planned, intent, *cells, *tail))):
            if mine != live:
                lines.append(f"{row['id']} {label} 本件={as_text(mine)} 现场={as_text(live)}"
                             f"（{FACT_ANCHORS['ROUTE_TAIL_SLICES']}）")
    return lines


def drift_between(base=None, other=None) -> list:
    """两棵树之间的逐格读数差：“哪一格变了、从几变到几”。影子副本自证吃这一枚。"""
    before, after = fact_snapshot(base), fact_snapshot(other)
    lines = []
    for name in sorted(set(before) | set(after)):
        left = before.get(name, "（这一侧缺席）")
        right = after.get(name, "（那一侧缺席）")
        if left != right:
            kind = "copy" if name in COPIES else "derived"
            lines.append(f"{name} [{kind}] {FACT_ANCHORS.get(name, name)}: {left} -> {right}")
    return lines


def guard_facts(rows=None, root=None) -> list:
    """开机先量尺子。空表 = 本件的事实与现场同源，可以继续算；非空 = 一律红，不许带病出读数。

    ``root`` 只给常驻件用：把现场换成影子副本，就能证明这扇门真的会红（判据戊）。
    脚本自己调用时永远不传，量的是盘上这一棵。
    """
    try:
        lines = copy_drift(root)
    except FactError as exc:
        lines = [f"现场事实读不动：{exc}"]
    try:
        read_rewrite_rule(root)
    except FactError as exc:
        lines.append(f"追问判定读不动：{exc}")
    try:
        probe = read_intent_text_rule(root)
        if probe("住宿证.pdf 标准") == "住宿证.pdf 标准":
            lines.append(f"剥离文档引用那一步搬进来后不干活了：{FACT_ANCHORS['INTENT_TEXT_RULE']}")
    except FactError as exc:
        lines.append(f"文档引用剥离规则读不动：{exc}")
    if rows is not None:
        try:
            lines.extend(branch_equivalence(rows, root))
        except FactError as exc:
            lines.append(f"分派分支切不动：{exc}")
    return lines


def fact_report(root=None) -> str:
    """逐格读数（含现场锚点）：``--facts`` 用，出问题时先自证尺子读了什么。"""
    facts = live_facts(root)
    lines = []
    for name in sorted(FACT_READERS):
        kind = "derived"
        lines.append(f"FACT {name} [{kind}] {FACT_ANCHORS[name]} = {facts[name]}")
    for name in sorted(COPIES):
        lines.append(f"COPY {name} [copy] 等值比对现场 -> {COPIES[name]!r}")
    return "\n".join(lines)




def _block_network() -> None:
    """三条出站路径换成会抛的桩，然后才 import 业务代码。

    只换 connect 类入口、不换 socket.socket 本身：R94 的测试用整类替换会打断导入期
    的 zipimport（本件亲测），那是一条假绿的反面——炸在 import 上而不是炸在连接上。
    """

    def _boom(*_args, **_kwargs):
        raise AssertionError("R107 预演件禁止任何网络动作")

    socket.create_connection = _boom
    socket.getaddrinfo = _boom
    socket.socket.connect = _boom


#: --- R218 修：拦网装在哪一刻（门内地雷）----------------------------------------------
#: 原来这里是无条件一句 ``_block_network()``（HEAD 第 90 行）。它把「import 任何业务代码之前
#: 先拦住三条出站路径」这条安全主张实现成了 **import 副作用** —— 于是任何在 pytest 里
#: import 本件的人，会把这三条桩留给**同进程的别的事**：
#:   tests/test_r217_strict_unaffordable_form.py 里那句 ``from scripts.rehearse_eval_window
#:   import budget_table`` ⇒ 同 worker 的 tests/test_r37_report_lane_enqueue.py 当场
#:   ``AssertionError: R107 预演件禁止任何网络动作``（09-24 实测：r37 单跑 14 passed；
#:   r37 + r217 无论谁在前都是 11 failed / 8 passed；对照 r37 + r155 是 41 passed）。
#:   全量门 ``-n 8 --dist loadfile`` 只要把这俩文件派进同一枚 worker，就会为**与判据无关的
#:   原因**变红。
#: 现在的形状：**主张一个字不删，只改装载条件** —— 进程里没有更严的闸门时才拦（脚本直跑、
#: ``python -c``、被非 pytest 的调用方 import 全在这一类）；conftest 的 R56 端口闸门已在时
#: 让位，因为它按目标端口识别、逐用例记 attempt、收尾再判一次红，比这枚桩严格。
#: 「在 import 业务代码之前」仍然成立：本段就在下面那几行 ``from app...`` 之上。
#: 反证形状见 tests/test_r218_egress_gate_placement.py（摘掉这枚条件 ⇒ 红必须落在
#: 「脚本模式下没拦网」这一格）。
EGRESS_GUARDED = False


def _conftest_gate_loaded() -> bool:
    """pytest 的 R56 闸门在不在本进程里：在就让位，不在就必须自己拦。

    判据用「conftest 模块带着 BLOCKED_MODEL_PORT_ATTEMPTS 进没进 sys.modules」，不用
    PYTEST_CURRENT_TEST 之类环境变量 —— 那只覆盖用例执行期，收集期 import app 同样危险。
    """
    for name in ("tests.conftest", "conftest"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "BLOCKED_MODEL_PORT_ATTEMPTS"):
            return True
    return False


def egress_guard_state() -> dict:
    """本件此刻拦没拦、为什么这么选：给反证钉读的出口，不改变任何行为。"""
    return {"guarded": EGRESS_GUARDED,
            "conftest_gate_loaded": _conftest_gate_loaded(),
            "stubbed": getattr(socket.create_connection, "__name__", "") == "_boom"}


if not _conftest_gate_loaded():
    _block_network()
    EGRESS_GUARDED = True

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.agents.contracts import ModelTier  # noqa: E402
from app.agents.nodes import (  # noqa: E402
    KB_CALIBER_MARKERS,
    LANE_QA,
    OFFLINE_ANALYSIS_ANSWER,
    OFFLINE_GENERIC_ANSWER,
    OFFLINE_REIMBURSEMENT_ANSWER,
    OFFLINE_STREAM_CHUNK,
    _OfflineModel,
    build_task_plan,
    classify_route,
)
from app.common.model_budget import (  # noqa: E402
    clock_affordable_tokens,
    min_answer_tokens,
    model_tier_budget,
)
from app.quality.eval import _is_correct  # noqa: E402


# ==================== 装配：常量 = 现场读数 ==================================
# 本节只有两种写法：从 FACTS 取（derived），或写死一份字面量并登记进 COPIES（copy，
# 启动时与现场等值比对）。老版本这里每行末尾那枚 ``app/xxx.py:NNN`` 全部作废 —— 它们
# 既不是读数也不是比对，只是一句会过期的谎话。

FACTS = live_facts()

HITL_PARKED = FACTS["HITL_PARKED"]                  # 编译期挂起的那两条腿
WORKER_GRAPHS = FACTS["WORKER_GRAPHS"]              # 主图注册的全部工作腿
PLANNER_WORKERS = FACTS["PLANNER_WORKERS"]          # planner 会排的腿（从不排 export）
ZERO_MODEL_WORKERS = FACTS["ZERO_MODEL_WORKERS"]    # 不发生成调用的腿
DOC_BEARING = FACTS["DOC_BEARING"]                  # 会写 document 证据的腿
DOCUMENT_SOURCE_TYPE = FACTS["DOCUMENT_SOURCE_TYPE"]
WRITTEN_SOURCE_TYPES = FACTS["WRITTEN_SOURCE_TYPES"]
REQUEST_BUDGET_SECONDS = FACTS["REQUEST_BUDGET_SECONDS"]
RATE_LIMIT_PER_MINUTE = FACTS["RATE_LIMIT_PER_MINUTE"]
ADAPTER_MIN_GAP_SECONDS = FACTS["ADAPTER_MIN_GAP_SECONDS"]
CACHE_TTL_SECONDS = FACTS["CACHE_TTL_SECONDS"]
REWRITE_TRIGGERS = FACTS["REWRITE_PREFIXES"]        # 现场词表，判定见 _is_followup()
#: 现场那枚模式串的编译结果（本件不再自己 sub 一次，见 ``_intent`` 直接调现场函数）。
DOC_REFERENCE = re.compile(FACTS["DOC_REFERENCE_PATTERN"], re.IGNORECASE)
LIVE_REWRITE_RULE = read_rewrite_rule()             # chat.py 那两枚判定函数本身
LIVE_INTENT_TEXT = read_intent_text_rule()          # orchestrator.py 那次剥离文档引用
#: R206a“口径题补读腿”那条规则本身（源码切片，见 CALIBER_RULE）：本件不抄它的词表与边界。
LIVE_KB_LEG_FOR_CALIBER = read_caliber_rule()
INTERRUPT_BEFORE = FACTS["INTERRUPT_BEFORE"]                # (腿列表, 它引用的符号名)
INTERRUPT_LEGS, INTERRUPT_BEFORE_SYMBOL = INTERRUPT_BEFORE
APPROVAL_ANCHOR = FACTS["APPROVAL_WORKER_SPAN"]
CACHE_KEY_ANCHOR = FACTS["CACHE_KEY_SHAPE"]["span"]

#: 追问改写腿拒收的罐头码（现场那张表的键，本件用它说“改写会换题面”这条模式还成立）。
REWRITE_GUARD_CODES = FACTS["REWRITE_GUARD_CODES"]

# --- 抄本 + 等值钉（判据丁）---------------------------------------------------
#: route_main 的四张关键词兜底表。本件仍自带一份（分派逻辑要跑它），但它现在被
#: copy_drift() 逐格钉在 route_main 现场那四张表上：不等就红并点名差在哪一枚，
#: 并且 branch_equivalence() 拿 105 题逐题比“本件的镜像分支”与“现场源码切片”。
KW_CHART = ["画", "图", "图表", "柱状图", "折线图", "饼图", "可视化", "图形"]
KW_DATA = ["排名", "最高", "最低", "统计", "分析数据", "对比", "比较", "哪个"]
KW_EXPORT = ["导出", "PDF", "pdf", "报告", "下载"]
KW_DOC = [
    "制度", "流程", "报销", "审批", "住宿费", "差旅", "员工手册",
    "入职", "安全", "规定", "标准", "谁审批", "审批人",
]
#: --summary 那句缓存口径摘要的抄本，钉在 cache.py 的 _answer_key/_hash/_scope_part 上。
CACHE_KEY_PROSE = "md5(scope)[:12]+md5(问题.strip())[:12]"
#: 🔴 下面那把每题秒数的尺子（MEASURED_SECONDS_PER_CALL）是在"地板 = 1536 tok"这一档上量出来的
#: （跟进单§42 表#6）。这一枚抄本没有代码事实源可抄，但它钉在真身上：现场把
#: DEFAULT_MIN_ANSWER_TOKENS 改到别处，本件当场红并停住读数——重测之后再登记，别改判据。
CALIBRATED_FLOOR_TOKENS = 1536

COPIES = {
    "KW_CHART": KW_CHART,
    "KW_DATA": KW_DATA,
    "KW_EXPORT": KW_EXPORT,
    "KW_DOC": KW_DOC,
    "CACHE_KEY_PROSE": CACHE_KEY_PROSE,
    "CALIBRATED_FLOOR_TOKENS": CALIBRATED_FLOOR_TOKENS,
}

# --- 实测输入：代码里没有事实源，不派生也不钉 ---------------------------------
#: 跟进单 §42 八变体里与现网链路同形的那一行（compat + thinking disabled + 1536）
#: = 37.3 s / 发（1328 计费 token，93 字正文）。那是**一次跑分实测**，不是本树的代码
#: 事实，所以它既不能 AST 派生也没有等值对象；表里所有秒数都按这一行线性外推。
#: 🔴 重测之后必须手动改这一格并同步 --summary 的算式说明，别指望它自己跟上。
MEASURED_SECONDS_PER_CALL = 37.3

# --- 产品在这一行可能吐出的“非模型正文”：逐条现算 ------------------------------
# 判分器只认子串（现场形状由 JUDGE_IS_SUBSTRING 这一格把关，出处 app/quality/eval.py::
# _is_correct），所以“这句罐头能不能让这一行变成对”是静态可算的。
_OFFLINE_TEXTS = FACTS["OFFLINE_TEXTS"]
_PARK_TEXTS = FACTS["PARK_TEXTS"]
_APPROVAL_TEXTS = FACTS["APPROVAL_TEXTS"]


def _canned_texts() -> dict:
    """每一条都带现场锚点；锚点是算出来的 path::symbol，不是手抄行号。"""
    texts = {name: (value, FACT_ANCHORS["PARK_TEXTS"]) for name, value in _PARK_TEXTS.items()}
    texts["no_answer"] = (FACTS["NO_ANSWER_TEXT"], FACT_ANCHORS["NO_ANSWER_TEXT"])
    texts["request_expired"] = (FACTS["TIMEOUT_TEXT"], FACT_ANCHORS["TIMEOUT_TEXT"])
    for name, value in _OFFLINE_TEXTS.items():
        texts[name] = (value, FACT_ANCHORS["OFFLINE_TEXTS"])
    texts["blank_sentinel"] = (FACTS["BLANK_SENTINEL"], FACT_ANCHORS["BLANK_SENTINEL"])
    texts["model_unavailable"] = (
        FACTS["MODEL_UNAVAILABLE_REPLY"],
        f'{FACT_ANCHORS["MODEL_UNAVAILABLE_REPLY"]}（改写腿会把它当问题文本回填，'
        f'见 {FACT_ANCHORS["REWRITE_GUARD_CODES"]}）')
    for name, variables in APPROVAL_SCENARIOS.items():
        try:
            value = _APPROVAL_TEXTS[tuple(variables)]
        except KeyError as exc:
            raise FactError(
                f"{FACT_ANCHORS['APPROVAL_TEXTS']} 里取不到缺料组合 {variables}："
                f"现场只剩 {sorted(map(str, _APPROVAL_TEXTS))}") from exc
        texts[name] = (value, FACT_ANCHORS["APPROVAL_TEXTS"])
    return texts


CANNED_TEXTS = _canned_texts()

def load_rows() -> list:
    text = (REPO_ROOT / FIXTURE_REL).read_text(encoding="utf-8-sig")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def load_checker():
    import importlib.util

    path = REPO_ROOT / "scripts" / "check_eval_evidence_coverage.py"
    spec = importlib.util.spec_from_file_location("check_eval_evidence_coverage", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # 🔴 R379 格四同族：``spec.loader.exec_module`` 会先认 ``scripts/__pycache__`` 里那枚过期
    # .pyc（Windows mtime 只到秒、改版前后又常常同尺寸），无出处那 29 条就会是旧字节码算出来的。
    # 现读源文本 compile 出来跑，缓存这条路整个不存在。
    exec(compile(path.read_text(encoding="utf-8-sig"), str(path), "exec"), module.__dict__)
    return module


def provenance(pdf_caliber: bool = False):
    """主口径（documents/*.txt）的缺出处清单；备选口径（含 PDF）只在显式开关下才算。

    默认关：pypdf 一被 import 就往 stdout 刷几千行 "Skipping broken line"（本件 09-20
    在 --include-pdf 上实测），预演表要能直接贴进文档，不能被那种噪声埋掉。
    """
    checker = load_checker()
    rows = checker.load_rows(REPO_ROOT / checker.FIXTURE_REL)
    main = checker.find_missing_terms(rows, checker.load_corpus(REPO_ROOT))
    pdf_rows = 0
    if pdf_caliber:
        pdf_rows = len(checker.find_missing_terms(
            rows, checker.load_corpus(REPO_ROOT, include_pdf=True)))
    return ({str(key): [str(term) for term in value] for key, value in main.items()},
            pdf_rows, checker.EXPECTED_CORPUS_TXT_COUNT)


def offline_sentence_for(question: str) -> str:
    """模型缺席时产品会答哪一句：现问现场的 ``_OfflineModel`` 自己。

    旧版本这里抄了一遍它的分支顺序，还把出处写成一枚行号——现场把那段挪过一次家，那枚
    行号就成了对不上的谎话，而分支本身才是事实。抄分支=重写一遍逻辑，所以改成直接调现场那枚
    假模型（app/agents/nodes.py::_OfflineModel.invoke）——它零网络、零模型调用。
    """
    return _OfflineModel().invoke([{"role": "user", "content": question}]).content


def route_class(workers: list) -> str:
    """把计划折成判据 1 要的三分类：doc / data / mixed（外加两类副作用腿）。"""
    docish = "doc" in workers
    dataish = any(w in ("data", "chart") for w in workers)
    if docish and dataish:
        return "mixed"
    if docish:
        return "doc"
    if dataish:
        return "data"
    if "export" in workers:
        return "export-only"
    return "none"


def plan_workers(question: str) -> list:
    return [task["worker"] for task in build_task_plan(question)]


def _intent(question: str) -> str:
    # 剥离文档引用后的文本：现场 ``_intent_text`` 函数本体，源码搬进来的（判据 甲：
    # 连"用哪个替换串 sub"这种写法都不抄第二份）。出处见 INTENT_TEXT_RULE。
    return LIVE_INTENT_TEXT(question)


def kw_path_workers(question: str, planned: list) -> list:
    # route_main 分派段的"关键词兜底"那一支（现场 app/agents/orchestrator.py::route_main
    # 的 else 分支）：计划只有一步、且 supervisor 给出了正文时，关键词能整组取代它派发
    # 的腿。真窗口最终派腿由 supervisor 模型说了算（同一文件::main_agent_node 读它的
    # tool_calls），本函数算的是"派错了也会被关键词扳回来"的那一路，用来和确定性计划
    # 那一路做对照：两路一致 = 路由稳；不一致 = 这一题走哪条腿静态不可担保。
    # 🔴 R361：这段与现场那一支的**同形**由 branch_equivalence() 拿 105 题逐题比对，
    # 词表本身的等值由 copy_drift() 钉着（判据丁）。两处不等都红，不再靠"照抄"自觉。
    intent = _intent(question)
    workers = []
    if any(kw in intent for kw in KW_CHART):
        if workers != ["chart"]:
            workers = ["chart"]
    elif any(kw in intent for kw in KW_EXPORT) and not any(kw in intent for kw in KW_CHART):
        if workers != ["export"]:
            workers = ["export"]
    elif any(kw in intent for kw in KW_DOC) and not any(kw in intent for kw in KW_DATA):
        if workers != ["doc"]:
            workers = ["doc"]
    elif any(kw in intent for kw in KW_DATA) and "chart" not in workers:
        if "data" not in workers:
            workers = ["data"]
    if workers and all(worker in ("chart", "export") for worker in workers):
        for worker in planned:
            if worker not in workers and worker not in ("chart", "export"):
                workers.insert(0, worker)
    return workers


def plan_path_workers(planned: list, question: str) -> list:
    # route_main 的"计划优先"分支（现场同一函数里 planned>1 或 supervisor 弃权那支）。
    # 与现场的等值由 branch_equivalence() 把关，见 kw_path_workers 上面那段。
    intent = _intent(question)
    workers = list(planned)
    if "chart" not in workers and any(kw in intent for kw in KW_CHART):
        workers.append("chart")
    elif "export" not in workers and any(kw in intent for kw in KW_EXPORT):
        workers.append("export")
    return workers


def route_final_workers(intent: str, workers: list, abstained: bool) -> list:
    """route_main 分岔之后的收尾两支：R206a 口径补 doc、R42 弃权轮补 doc —— 本件的镜像。

    🔴 R379 格三：从前门里只有分派那两支，这两支没进等值比对。两支的**规则**这里一枚字都不抄：
    补哪条腿由现场 ``kb_leg_for_caliber`` 自己算（源码搬进来的 LIVE_KB_LEG_FOR_CALIBER），
    要不要补由现场 ``classify_route`` 判（import 侧那枚函数本身 + 它自己的档位表）。
    本函数只镜像 route_main 里那两段 if 的形状，形状与现场切片的等值由
    ``branch_equivalence()`` 拿 105 题逐题比对（动现场那两支之一 ⇒ 当场红）。

    ``abstained`` 是本件建模的那一局：supervisor 既没派发也没给正文。计划优先那一路
    进来时 workers 必非空，R42 那一支在它自己那句 ``not workers`` 上短路，不靠这个入参。
    """
    filled = LIVE_KB_LEG_FOR_CALIBER(intent, workers)
    if filled != workers:
        workers = filled
    if not workers and abstained and classify_route(intent).lane == LANE_QA:
        workers = ["doc"]
    return workers


def legs_range(workers: list, rewritten: bool) -> tuple:
    """每题模型发数的 [推算] 区间，算式在 --summary 里印出来。

    下界 = 链路坏（正文 0 字）时：supervisor 1 发 + 每个 worker 1 发（react agent
    拿不到正文也拿不到 tool_calls 就收摊：app/agents/orchestrator.py::_make_worker_wrapper
    找不到 final 就先交空串，那一格今天由 WORKER_EMPTY_ANSWER_FALLBACK 现读把关），
    加改写腿则 +1。
    上界 = 链路正常时：每个 worker 至少"要工具 1 发 + 出正文 1 发"，supervisor 若
    reflect 判 redo 再来 1 发（app/agents/nodes.py::reflect_node，本件现读它的 redo 分支数
    = REFLECT_REDO_BRANCHES），故 +1。
    """
    model_legs = [w for w in workers if w not in ZERO_MODEL_WORKERS]
    low = 1 + len(model_legs) + (1 if rewritten else 0)
    high = 1 + 2 * len(model_legs) + 1 + (1 if rewritten else 0)
    return low, high


def budget_table(floor_override: int | None) -> list:
    """每个档在当前代码值（或 R100 的地板现值替身）下的静态结论。"""
    out = []
    for tier in ModelTier:
        budget = model_tier_budget(tier)
        declared = int(budget.max_tokens)
        rate = max(0.1, float(budget.decode_tokens_per_second))
        prefill_rate = max(0.1, float(budget.prefill_tokens_per_second))
        ceiling = float(budget.timeout_ceiling_seconds)
        margin = max(1.0, float(budget.timeout_margin))
        floor = min_answer_tokens() if floor_override is None else floor_override
        affordable_max = clock_affordable_tokens(budget, 0, stream=False)
        # affordable(p) = (ceiling/margin - p/prefill_rate) * rate 在 p=0 处取最大
        # clamped 需要 floor <= affordable < declared；上限都够不到 floor 就不存在这样的 p
        # always_unaffordable 必须是「连本档自己的地板都付不起」，即 affordable < min(declared, floor)。
        # 旧式漏了地板这一侧，于是 declared > affordable >= floor 那一段会同时印出 clamp_possible=true
        # 与 always_unaffordable=true —— 一枚说「能夹」一枚说「永远付不起」，两旗自相矛盾。
        clamp_possible = floor <= affordable_max and affordable_max < declared
        always_unaffordable = affordable_max < min(declared, floor)
        break_even = (ceiling / margin - declared / rate) * prefill_rate
        out.append({
            "tier": tier.value,
            "declared": declared,
            "floor": floor,
            "ceiling": ceiling,
            "affordable_max": affordable_max,
            "self_decode_seconds": round(declared / rate, 1),
            "needed_worst_seconds": round(
                (budget.prefill_seconds(None) + declared / rate) * margin, 1),
            "read_timeout_worst_seconds": round(budget.read_timeout_seconds(None, stream=False), 1),
            "clamp_possible": clamp_possible,
            "always_unaffordable": always_unaffordable,
            "unaffordable_above_prompt_tokens": round(break_even, 1),
        })
    return out


def build_table(rows: list, missing: dict) -> list:
    table = []
    for row in rows:
        question = str(row["question"])
        row_id = str(row["id"])
        workers = plan_workers(question)
        decision = classify_route(question)
        terms = [str(term) for term in (row.get("must_contain") or [])]
        # 🔴 R361：这句从前是 any(question.startswith(t) for t in 手抄七枚前缀)，而现场
        # 早在 R126 就把判定换成了 _FOLLOWUP_PREFIXES + 指代排除 + _FOLLOWUP_MARKERS 三件
        # 一套。旧抄本今天只报 5 题，现场报 12 题（见 --facts 与工单回执）——拿旧事实继续
        # 算正是本单根治的那类病。现在直接跑现场那两枚判定函数的源码切片。
        rewrite = bool(LIVE_REWRITE_RULE(question))
        parked = [worker for worker in workers if worker in HITL_PARKED]
        upstream = [worker for worker in workers if worker not in HITL_PARKED]
        miss = missing.get(row_id) or []
        kw_path = kw_path_workers(question, workers)
        plan_path = plan_path_workers(workers, question)
        divergent = set(kw_path) != set(plan_path)
        canned_hits = sorted(name for name, (text, _) in CANNED_TEXTS.items()
                             if _is_correct(row, text))
        low, high = legs_range(workers, rewrite)

        modes = []
        if not kw_path:
            # supervisor 只要敢直接作答（不派发），route_main 收尾 workers=[] 就去
            # EMPTY_ROUTE_TARGET 现读的那一站（今天 = "reflect"），reflect 判 redo 再烧一发
            # supervisor（app/agents/nodes.py::reflect_node 的 redo 分支，见 legs_range）。
            modes.append("①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮")
        if parked and not upstream:
            modes.append("①挂起无上游→交付必为park文案")
        elif parked:
            modes.append("①chart/export腿挂起(前面有doc/data真结果)")
        if not [w for w in upstream if w in DOC_BEARING]:
            modes.append("①本轮无写document证据的腿→sources必为0条")
        if row.get("requires_evidence") and not [w for w in upstream if w in DOC_BEARING]:
            modes.append("①evidence闸必失(requires_evidence=true且0来源)")
        if rewrite:
            modes.append("①追问改写会换题面→金标可能对不上改写后的问题")
        if decision.tier is ModelTier.ANALYSIS:
            modes.append("②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped)")
        if high * MEASURED_SECONDS_PER_CALL > REQUEST_BUDGET_SECONDS:
            modes.append("③上界腿数会撞CHAT_REQUEST_TIMEOUT=300s")
        if miss:
            modes.append("②金标无出处:" + "|".join(miss))
        if canned_hits:
            modes.append("④假绿通道:" + "/".join(canned_hits))

        watch = bool(parked and not upstream) or bool(canned_hits) or rewrite \
            or (row.get("requires_evidence") and not [w for w in upstream if w in DOC_BEARING])
        table.append({
            "id": row_id,
            "tier": row.get("tier"),
            "category": row.get("category"),
            "question": question,
            "requires_evidence": bool(row.get("requires_evidence")),
            "must_contain": "、".join(terms),
            "tool_legs": ",".join(leg for leg in ("data", "chart", "export", "approval")
                                  if leg in workers) or "无",
            "plan": "+".join(workers),
            "route_class": route_class(workers),
            "plan_path": "+".join(plan_path) or "-",
            "kw_path": "+".join(kw_path) or "-",
            "route_stability": ("模型决定" if divergent else "两路一致"),
            "route": f'{decision.lane}/{decision.tier.value}',
            "route_rule": f'{decision.rule}:{"/".join(decision.matched) or "-"}',
            "provenance": ("缺:" + "|".join(miss)) if miss else "有",
            "failure_modes": "; ".join(modes) or "-",
            "false_green_via": ",".join(canned_hits) or "-",
            "legs": f"{low}-{high}",
            "advice": "人工盯" if watch else "照跑",
        })
    return table


def markdown(table: list, only: str, width: int) -> None:
    header = ("题 id", "档位/类别/题面", "工具腿", "预期路由", "计划", "车道/模型档",
              "must_contain 出处", "命中失败模式", "窗口建议")
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join(["---"] * len(header)) + "|")
    for item in table:
        if only and not item["id"].startswith(only):
            continue
        question = item["question"]
        if len(question) > width:
            question = question[:width] + "…"
        modes = item["failure_modes"].replace("|", "∣")
        plan_cell = item["plan"]
        if item["plan_path"] != item["plan"] and item["plan_path"]:
            plan_cell += f"<br>计划优先→{item['plan_path']}"
        if item["route_stability"] == "模型决定":
            plan_cell += "<br>⚠关键词路→" + ("空" if item["kw_path"] == "-" else item["kw_path"])
        print("| `{id}` | {tier}·{category}<br>{q} | {legs} | **{cls}** | {plan} | {route} "
              "| {prov} | {modes} | {advice} |".format(
                  id=item["id"], tier=item["tier"], category=item["category"], q=question,
                  legs=item["tool_legs"], cls=item["route_class"], plan=plan_cell,
                  route=item["route"], prov=item["provenance"], modes=modes,
                  advice=item["advice"]))


def summary(rows: list, table: list, missing: dict, pdf_rows: int, corpus_txt: int,
            budgets: list, floor_now: int, pdf_caliber_ran: bool = False) -> None:
    def count(predicate) -> int:
        return sum(1 for item in table if predicate(item))

    parked_only = [i["id"] for i in table if "①挂起无上游→交付必为park文案" in i["failure_modes"]]
    parked_any = [i["id"] for i in table if "①挂起无上游→交付必为park文案" in i["failure_modes"]
                  or "①chart/export腿挂起(前面有doc/data真结果)" in i["failure_modes"]]
    no_doc = [i["id"] for i in table if "①本轮无写document证据的腿→sources必为0条" in i["failure_modes"]]
    ev_fail = [i["id"] for i in table if "①evidence闸必失(requires_evidence=true且0来源)" in i["failure_modes"]]
    rewrite = [i["id"] for i in table if any(m.startswith("①追问改写") for m in i["failure_modes"].split("; "))]
    false_green = {i["id"]: i["false_green_via"] for i in table if i["false_green_via"] != "-"}
    analysis = [i["id"] for i in table if i["route"].endswith("/analysis")]
    timeout_risk = [i["id"] for i in table if "③上界腿数会撞CHAT_REQUEST_TIMEOUT=300s" in i["failure_modes"]]
    approval = [i["id"] for i in table if "+approval" in i["plan"] or i["plan"] == "approval"]
    plans = {}
    for item in table:
        plans[item["plan"]] = plans.get(item["plan"], 0) + 1

    print("=== R107 预演汇总（全部由本件当场从源码算出，出处见文件头）===")
    subprocess_out = ""
    try:
        subprocess_out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                        capture_output=True, cwd=str(REPO_ROOT), timeout=10
                                        ).stdout.decode().strip()
    except Exception:
        subprocess_out = "unknown"
    print(f"baseline={subprocess_out} rows={len(table)}")
    # R379 格一：两侧不同源。现值 = 这一次跑真正拿来算的地板（调用方给的读数）；
    # DEFAULT = 现场那枚默认值真身（app/common/model_budget.py 的模块级字面量，AST 现读）。
    print(f"MODEL_MIN_ANSWER_TOKENS 现值={floor_now}  DEFAULT={FACTS['MIN_ANSWER_TOKENS_DEFAULT']}")
    # 上一行的三元表达式会整条吞掉 no_provenance_rows（本件 09-20 实跑所见），拆成两行。
    print(f"no_provenance_rows={len(missing)}（主口径 corpus=documents/*.txt {corpus_txt} 篇）")
    print("no_provenance_rows_pdf_caliber="
          + (str(pdf_rows) if pdf_caliber_ran else "未算（加 --pdf-caliber 才算）")
          + "；口径差异见 provenance() docstring")
    print("no_provenance_ids=" + " ".join(sorted(missing)))
    print(f"tier_counts=" + json.dumps({t: count(lambda i, t=t: i['tier'] == t)
                                        for t in ('问答', '分析', '报告')}, ensure_ascii=False))
    advice_counts = {t: count(lambda i, t=t: i['advice'] == t) for t in ('照跑', '人工盯')}
    # R379 格二：跳过数从前是写死的 0（一句主张，不是读数）。现在从实际行集合算：
    # 落在两档之外的每一行都算跳过，行集合一动它跟着动。
    skipped = len(table) - sum(advice_counts.values())
    print("advice=" + json.dumps(advice_counts, ensure_ascii=False)
          + f" 跳过={skipped}（见 note:coverage）")
    print(f"parked_any={len(parked_any)} {parked_any}")
    print(f"parked_only={len(parked_only)} {parked_only}")
    print(f"no_doc_leg={len(no_doc)} {no_doc}")
    print(f"evidence_gate_expected_fail={len(ev_fail)} {ev_fail}")
    print(f"rewrite_triggered={len(rewrite)} {rewrite}")
    print(f"approval_leg_zero_model_call={len(approval)} {approval}")
    print(f"analysis_tier={len(analysis)}")
    print(f"request_budget_at_risk={len(timeout_risk)} {timeout_risk}")
    print(f"max_high_legs={max(int(i['legs'].split('-')[1]) for i in table)} "
          f"⇒ 高界秒数={max(int(i['legs'].split('-')[1]) for i in table) * MEASURED_SECONDS_PER_CALL:.1f}s "
          f"vs 请求预算 {REQUEST_BUDGET_SECONDS}s")
    print("legs_distribution=" + json.dumps(
        {i["legs"]: sum(1 for t in table if t["legs"] == i["legs"]) for i in table}, ensure_ascii=False))
    print(f"false_green_rows={len(false_green)}")
    for row_id in sorted(false_green):
        print(f"   FALSEGREEN {row_id}: {false_green[row_id]}")
    print(f"plan_shapes={json.dumps(dict(sorted(plans.items(), key=lambda kv: -kv[1])), ensure_ascii=False)}")
    route = {}
    lanes = {}
    for item in table:
        route[item["route_class"]] = route.get(item["route_class"], 0) + 1
        lanes[item["route"]] = lanes.get(item["route"], 0) + 1
    print("route_class=" + json.dumps(dict(sorted(route.items(), key=lambda kv: -kv[1])), ensure_ascii=False))
    print("lane_tier=" + json.dumps(dict(sorted(lanes.items(), key=lambda kv: -kv[1])), ensure_ascii=False))
    stable = [i["id"] for i in table if i["route_stability"] == "模型决定"]
    kw_empty = [i["id"] for i in table if i["kw_path"] == "-"]
    print(f"route_divergent={len(stable)} {stable}")
    print(f"route_kw_fallback_empty={len(kw_empty)} {kw_empty}")
    export_rows = [i["id"] for i in table if "export" in i["plan_path"] or "export" in i["kw_path"]]
    print(f"export_leg_any_path={len(export_rows)} {export_rows}")
    # 挂起风险要按"任一路"算：计划里没排 export，但 route_main 的关键词兜底两支会把
    # export 追加或整组改派进来（本件那两路 = 现场切片的镜像，见 branch_equivalence），
    # 而 export 和 chart 一样带 interrupt_before（现读 = INTERRUPT_LEGS）。
    park_path = [i["id"] for i in table
                 if set(i["plan_path"].split("+")) & set(HITL_PARKED)
                 or set(i["kw_path"].split("+")) & set(HITL_PARKED)]
    print(f"parked_any_path={len(park_path)} {park_path}")
    data_rows = [i["id"] for i in table
                 if "data" in i["plan_path"].split("+") or "data" in i["kw_path"].split("+")]
    print(f"data_leg_any_path={len(data_rows)} {data_rows}")
    print(f"requires_evidence_true={count(lambda i: i['requires_evidence'])}")
    print(f"evidence_coverage_ceiling={len(table) - len(ev_fail)}/{len(table)} "
          f"={round((len(table) - len(ev_fail)) / len(table), 4)}"
          f"（[算术] {len(ev_fail)} 行结构上不可能有 document 来源）")
    clean = [i["id"] for i in table if i["failure_modes"] == "-"]
    print(f"rows_with_no_failure_mode={len(clean)} {clean}")
    prov_free = [i["id"] for i in table if i["provenance"] != "有"]
    print(f"no_provenance_in_table={len(prov_free)}")
    print()
    print("=== 档位预算静态结论 ===")
    for row in budgets:
        print(json.dumps(row, ensure_ascii=False))
    print()
    print("=== [推算] 用的算式与参数 ===")
    print(f"legs_min = 1 + len(计划中会产生模型调用的腿) (+1 若追问改写)；"
          f"legs_max = 2 + 2*len(同类腿) (+1 改写)；approval 腿记 0 次模型调用"
          f"（{APPROVAL_ANCHOR} 是纯规则 worker）")
    print(f"每题秒数 ≈ legs × {MEASURED_SECONDS_PER_CALL}s（跟进单§42 表#6：compat+thinking off+1536 = 37.3s/发）")
    print(f"整窗 [秒] ≈ Σ(legs_min) × {MEASURED_SECONDS_PER_CALL} + {len(table)} × "
          f"{ADAPTER_MIN_GAP_SECONDS} 间隔"
          f"（上界同理换 Σ(legs_max)）")
    avg_low = sum(int(i["legs"].split("-")[0]) for i in table) / len(table)
    print(f"平均下界腿数={avg_low:.2f} ⇒ 整窗≈{len(table) * (avg_low * MEASURED_SECONDS_PER_CALL + ADAPTER_MIN_GAP_SECONDS) / 3600:.2f} h"
          f"；上界={len(table) * ((sum(int(i['legs'].split('-')[1]) for i in table) / len(table)) * MEASURED_SECONDS_PER_CALL + ADAPTER_MIN_GAP_SECONDS) / 3600:.2f} h")
    print(f"限流：{RATE_LIMIT_PER_MINUTE} 次/分钟/用户，适配器最小间隔 {ADAPTER_MIN_GAP_SECONDS}s ⇒ "
          f"任意 60s 窗内最多 {int(60 // ADAPTER_MIN_GAP_SECONDS) + 1} 发 < {RATE_LIMIT_PER_MINUTE} ⇒ 不入队道")
    print(f"答案缓存：键={CACHE_KEY_PROSE}（{CACHE_KEY_ANCHOR}），"
          f"TTL={CACHE_TTL_SECONDS}s；{len(table)} 题题面互不重复⇒单趟自相捂热=0")


def check_against_registered(missing: dict) -> int:
    # 判据 1 那句「核对是否正好那一批，多出来的要单独点名」的机器答复。
    # 登记抄本有两份：tests/test_r94_eval_evidence_coverage.py 的 MISSING_IDS_29（审计
    # 文档 §2.1 的抄本）与 TERM_BY_ID（附录 A 的抄本）。本函数只读 AST 取值，不 import
    # 测试件（那会拉起 pytest 依赖），也不下「谁对谁错」的结论。
    import ast

    test_path = REPO_ROOT / "tests" / "test_r94_eval_evidence_coverage.py"
    tree = ast.parse(test_path.read_text(encoding="utf-8"))
    def resolve(node):
        # 登记件把常量写成 ("a b c").split() 与 {"k": "a b".split()}，literal_eval 不认
        # Call；这里只还原这两种形状，不 eval 整个文件。
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "split":
            return str(resolve(node.func.value)).split()
        if isinstance(node, ast.Dict):
            return {resolve(k): resolve(v) for k, v in zip(node.keys, node.values)}
        return ast.literal_eval(node)

    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                name = getattr(target, "id", "")
                if name in ("MISSING_IDS_29", "TERM_BY_ID", "BUCKET_COUNTS"):
                    consts[name] = resolve(node.value)
    recorded_ids = [str(i) for i in consts["MISSING_IDS_29"]]
    term_by_id = {str(k): ([str(t) for t in v] if isinstance(v, (list, tuple))
                           else [str(v)]) for k, v in consts["TERM_BY_ID"].items()}
    got_ids = sorted(missing)
    terms = sum(len(v) for v in missing.values())
    extra = sorted(set(got_ids) - set(recorded_ids))
    gone = sorted(set(recorded_ids) - set(got_ids))
    mismatches = sorted(i for i in set(got_ids) & set(term_by_id)
                        if sorted(missing[i]) != sorted(term_by_id[i]))
    print(f"check29 rows_flagged={len(got_ids)} terms={terms}")
    print(f"check29 recorded_ids={len(recorded_ids)} extra={extra} missing={gone}")
    print(f"check29 term_mismatches={mismatches}")
    print(f"check29 row_level_equals_term_level={len(got_ids) == terms}（口径指纹，审计文档 §2.2）")
    buckets = consts.get("BUCKET_COUNTS")
    print(f"check29 bucket_counts={buckets} sum={sum(buckets.values()) if isinstance(buckets, dict) else 'n/a'}")
    return 0 if (not extra and not gone and not mismatches) else 1


def guard_failed(problems: list) -> int:
    """量不过尺子就不出读数（判据丁）。红话走 stderr，stdout 仍然只有读数那一样东西。"""
    print("R361 尺子自证失败：本件的抄本/镜像分支与现场源码不同形，拒绝出读数。", file=sys.stderr)
    for line in problems:
        print("  - " + line, file=sys.stderr)
    print(f"共 {len(problems)} 格。修法只有两种：把这一格改成现场派生，或把抄本改成与现场"
          "同源后再来；不许只把数字改成今天的数（那是 R346 明令禁止的交差法）。",
          file=sys.stderr)
    return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="R107 跑分窗口离线预演（只读）")
    parser.add_argument("--only", default="")
    parser.add_argument("--csv", action="store_true")
    parser.add_argument("--width", type=int, default=40)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--pdf-caliber", action="store_true",
                        help="另算含 PDF 的备选口径行数（R94 记 27；默认关，理由见 provenance docstring）")
    parser.add_argument("--check-29", action="store_true",
                        help="实取的无出处清单 vs 登记抄本，逐条点名（判据 1 最后一条）")
    parser.add_argument("--floor", type=int, default=None,
                        help="把 MODEL_MIN_ANSWER_TOKENS 当这个值复算（R100 会把它从 1537 改到 1536）")
    # R218：本件预演「窗口形状」，这一扇门预演「窗口要翻的那几个开关」（判据 ② 的三格）。
    # 只加一个分支，上面那几样既有用法的输出一个字都不变；两扇门的只读纪律同一条。
    parser.add_argument("--switches", action="store_true",
                        help="跑 R218 的开关离线预演三格（D 报告档翻开关 / C 缓存命中腿 / A② 帧账量具）")
    # R361：这台预演器过去把源码事实手抄进常数里。--facts 就是它现在读了哪些现场事实、
    # 每一格的锚点在哪；不给它加读数口径，只给尺子加一个自证出口。
    parser.add_argument("--facts", action="store_true",
                        help="打印本件运行时从源码现取的每一格事实（出处锚点 + 现值）")
    args = parser.parse_args(argv)

    if args.facts:
        print(fact_report())
        return 0

    # 🔴 判据丁：开机先量尺子，量不过就不出读数（不许"警告一句继续算"）。
    problems = guard_facts()
    if problems:
        return guard_failed(problems)

    if args.switches:
        import r218_switch_rehearsal

        return r218_switch_rehearsal.main([])

    from app.common.model_budget import min_answer_tokens

    os.environ.pop("MODEL_MIN_ANSWER_TOKENS", None)  # 只算代码现值，不吃宿主环境变量
    rows = load_rows()
    # 第二遍量的是"本件那两套镜像分支在 105 题上与现场切片是否逐题同形"。
    problems = guard_facts(rows)
    if problems:
        return guard_failed(problems)
    missing, pdf_rows, corpus_txt = provenance(args.pdf_caliber)
    table = build_table(rows, missing)
    budgets = budget_table(args.floor)
    # R379 格一：现值 = 这一次跑真正拿来算的那枚地板。给了 --floor 却不改这一格，摘要就会
    # 一边按 2048 算预算、一边宣称"现值=1536"——同一行里两枚数字讲的是两次跑。
    floor_now = args.floor if args.floor is not None else min_answer_tokens()

    if args.csv:
        keys = list(table[0].keys())
        print(",".join(keys))
        for item in table:
            print(",".join('"' + str(item[key]).replace('"', '""') + '"' for key in keys))
    elif args.check_29:
        return check_against_registered(missing)
    elif args.summary:
        summary(rows, table, missing, pdf_rows, corpus_txt, budgets, floor_now, args.pdf_caliber)
    else:
        markdown(table, args.only, args.width)
    return 0


if __name__ == "__main__":
    sys.exit(main())