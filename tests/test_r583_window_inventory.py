# -*- coding: utf-8 -*-
r"""R583：「真实开窗者」这本账沿 AST 派生，名册与它逐枚对账（判据 ①②）。

病（跟进单 §155 R583）：`tests/test_r466_mutation_does_not_leak_into_live_module.py` 里那本在册
名册 `WINDOWS` 被在册钉 `test_the_roster_is_nine_windows_and_none_of_them_execs_the_live_module`
钉成「恰等于那 9 枚」，而 R572（并树 `6a2c09b`）已把第二扇窗——
`tests/test_r253_shadow_root_holds_the_mutation.py` 里那枚 `_chat_window`——接进 `install_mutation`
却**没进册**。名册与真实开窗者从此不一致，且那枚写死枚数的钉会**主动阻止**后来者进册：
谁进册谁就得同时改钉，于是没人改。

总控裁定走甲案（进册 + 同步枚数钉）。本件负责把「谁真的开了窗」做成**一枚可复跑的派生读数**，
让名册去对账它，而不是让钉去背一份手抄名单。🔴 派生口径（全部沿 AST，按 (文件, 名字) 建图，
import 别名解析，不按名字跨文件撞车——那是 `window_handles()` 为「谁调用过把手」设计的粗口径）：

  · **窗** = `overlay.ShadowEdit` 的传递子类（从别枚件 import 进来的那枚也算，认定义文件）。
  · **开窗点** = 一件里出现「构造一枚窗」，或出现「调用一枚会构造窗的把手」（沿调用图传递；
    🔴 用例本体不作把手：调用别人的 `test_...` 不算，与在册真源 `window_handles()` 那句
    「用例本体不是把手」同一口径）。
  · **装变异腿** = 开窗点所在函数（含它调用的把手）里对 `r466.install_mutation` 的调用。
  · **LIVE** = 那枚调用的第一参数解析到 `overlay.module_of(...)`（含先赋给局部名再用），
    或解析到本件顶层 import 进来的那枚**活模块对象**（r48 的 `_chat_window` 传 `chat`）。
  · **ISOLATED** = 第一参数是形参且调用点实参来自一枚本地现造副本的把手（r499 的 `_load_view`），
    或解析到 `overlay.isolated_module(...)`。
  · **一枚件进名册**当且仅当满足其一：
    甲式 同一枚函数里既开窗又有 LIVE 腿（含 r253／r48 台账／r303 pg 腿那三枚**消费者**：
        它们开窗走 import 进来的 `_chat_window`／`_mutate`，LIVE 腿就在那枚把手里）；
    乙式 本件有开窗点，且本件有一枚**非用例**把手带着 LIVE 腿（r495：窗由 `KNIFE_*` 造，
        装变异在 `_knife_window`，两处分家，靠把手接上）。
  · 只开窗、从不往活模块上装变异的那族（r156／r457／r467／r482／r508／r516／r553／r572 反证）
    **不进名册**，但本件逐枚点名交回，不许静默失踪；r482 与 r553 那两枚 exec 姿势窗由
    `tests/test_r556_window_posture_is_installed_not_executed.py` 单独看管。

两枚面都从**文本**派生（`sources` 与名册文本都可整体替换）：反证只摘输入面，被跟踪文件全程只读，
与 R572 那把「只摘输入面文本，盘上不动」同形。
"""
from __future__ import annotations

import ast
import hashlib

from tests import test_r253_no_test_rewrites_a_tracked_file as r253pin

OVERLAY_REL = "tests/_temp_edit_overlay.py"
R466_REL = "tests/test_r466_mutation_does_not_leak_into_live_module.py"
INSTALL_HANDLE = "install_mutation"
#: 甲案的判据下限：R466 那九枚在册件一枚不许从派生里掉出去（名单不许反弹）。
HISTORICAL_NINE = (
    "tests/test_r303_notification_pins.py",
    "tests/test_r310_owner_lookup_cost.py",
    "tests/test_r337_owner_receipt_cost_and_knives.py",
    "tests/test_r353_degradation_note_caps_reason_classes.py",
    "tests/test_r354_delete_audit_shares_the_owner_reader.py",
    "tests/test_r373_the_two_remaining_legs_answer_absence.py",
    "tests/test_r381_outlet_answers_the_absent_approval_ledger.py",
    "tests/test_r388_read_leg_answers_absence.py",
    "tests/test_r48_headline_card_lands_on_the_wire.py",
)
#: 只往隔离视图上装变异的那一枚：它不进名册是**派生出来的结论**，不是手抄的豁免名单。
ISOLATED_LEG_REL = "tests/test_r499_the_ownership_predicate_survives_any_file_order.py"

_SOURCES = {}
_INVENTORY = {}
_SITE_CACHE: dict = {}
_EXISTS_CACHE: dict = {}
#: 只有这些语句带 body，import 可能藏在里面（`def _reload()` 里那句就是）。
_COMPOUND = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.If, ast.For, ast.AsyncFor,
             ast.While, ast.With, ast.AsyncWith, ast.Try, ast.Match)


def _exists(path) -> bool:
    """路径存在与否只 stat 一次：500 枚件乘三档候选就是上万次 stat，实测 1.5 s。"""
    key = str(path)
    hit = _EXISTS_CACHE.get(key)
    if hit is None:
        hit = path.exists()
        _EXISTS_CACHE[key] = hit
    return hit


def _import_nodes(tree: ast.AST):
    """只下钻语句体找 import。

    🔴 不用 `ast.walk`：它连表达式节点一起走（本仓 500 枚件 = 240 万枚节点，实测 11.8 s），
    而 import 只会出现在语句层。
    """
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
        elif isinstance(node, _COMPOUND):
            stack.extend(getattr(node, "body", ()))
            stack.extend(getattr(node, "finalbody", ()))
            for handler in getattr(node, "handlers", ()):
                stack.extend(handler.body)


def sha12(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _tail(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def import_env(tree: ast.AST) -> dict:
    """别名 -> (定义文件 rel, 原名)；`原名 is None` 表示这枚名字是一枚**模块对象**。"""
    env: dict = {}
    root = r253pin.TESTS_DIR.parent
    tests_dir = r253pin.TESTS_DIR
    for node in _import_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module != "__future__":
            base = node.module.replace(".", "/")
            package = root / base / "__init__.py"
            for alias in node.names:
                submodule = root / base / (alias.name + ".py")
                in_tests = tests_dir / (alias.name + ".py")
                own_module = root / (base + ".py")
                if node.module == "tests" and _exists(in_tests):
                    env[alias.asname or alias.name] = ("tests/" + alias.name + ".py", None)
                elif _exists(own_module):
                    #: `from tests.test_r48_x import _chat_window` 那族：名字是**那枚模块文件**的顶层定义，
                    #: 不是子模块。少了这一支，消费者件（r253 / r48 台账 / r303 pg 腿）的开窗点认不出来。
                    env[alias.asname or alias.name] = (own_module.relative_to(root).as_posix(), alias.name)
                elif _exists(submodule):
                    env[alias.asname or alias.name] = (submodule.relative_to(root).as_posix(), None)
                elif _exists(package):
                    env[alias.asname or alias.name] = (package.relative_to(root).as_posix(), alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.replace(".", "/")
                module_path, package_path = root / (base + ".py"), root / base / "__init__.py"
                if _exists(module_path):
                    env[alias.asname or alias.name] = (module_path.relative_to(root).as_posix(), None)
                elif _exists(package_path):
                    env[alias.asname or alias.name] = (package_path.relative_to(root).as_posix(), None)
    return env


class Suite:
    """一次扫描的原料：顶层定义、import 别名、引用解析、行号归属。"""

    def __init__(self, sources: dict) -> None:
        self.sources = sources
        self.classes: dict = {}
        self.functions: dict = {}
        self.imports: dict = {}
        self.ranges: dict = {}
        for rel_path, (_text, tree) in sources.items():
            self.imports[rel_path] = import_env(tree)
            spans = []
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    self.classes[(rel_path, node.name)] = node
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.functions[(rel_path, node.name)] = node
                    spans.append((node.lineno, node.end_lineno, node))
            spans.sort()
            self.ranges[rel_path] = spans

    def resolve(self, rel_path, node):
        """`_TempEdit(...)`／`overlay.ShadowEdit`／`r466.install_mutation(...)` 共用的解析式。"""
        name = _tail(node)
        if name is None:
            return (None, None)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            alias = self.imports[rel_path].get(node.value.id)
            if alias and alias[1] is None:
                return (alias[0], name)                        # overlay.module_of -> overlay 那枚件
        if (rel_path, name) in self.functions or (rel_path, name) in self.classes:
            return (rel_path, name)                            # 本件顶层定义
        alias = self.imports[rel_path].get(name)
        if alias:
            return (alias[0], alias[1] or name)
        return (None, name)

    def module_object_names(self, rel_path) -> set:
        return {name for name, (target, orig) in self.imports[rel_path].items() if orig is None}

    def enclosing(self, rel_path, line):
        """行号落在哪枚顶层函数里（调用点归因用，不必再全树反查）。"""
        found = None
        for start, end, node in self.ranges.get(rel_path, ()):
            if start <= line:
                found = node if (end or start) >= line else found
            else:
                break
        return found


def window_classes(suite: Suite) -> set:
    """`overlay.ShadowEdit` 的传递子类，键是 (定义文件, 类名)。"""
    _text, overlay_tree = suite.sources[OVERLAY_REL]
    bases = {
        node.name for node in overlay_tree.body
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
        and {m.name for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}
        >= {"__enter__", "__exit__"}
    }
    found = {(OVERLAY_REL, name) for name in bases}
    grew = True
    while grew:
        grew = False
        for key, node in suite.classes.items():
            if key in found:
                continue
            for base in node.bases:
                target, name = suite.resolve(key[0], base)
                if target and (target, name) in found:
                    found.add(key)
                    grew = True
                    break
    return found


def _parameters(func_node) -> list:
    args = getattr(func_node, "args", None)
    if args is None:
        return []
    return [a.arg for a in list(args.posonlyargs) + list(args.args)]


def _local_assignment(func_node, name: str):
    if func_node is None:
        return None
    for statement in ast.walk(func_node):
        if isinstance(statement, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in statement.targets
        ):
            return statement.value
    return None


def classify_module_arg(suite: Suite, rel_path, expr, func_node, depth: int = 0):
    """装变异的第一参数落到哪枚模块上：活模块（LIVE）还是现造的隔离副本（ISOLATED）。"""
    if expr is None or depth > 6:
        return ("OTHER", "读不到第一参数")
    if isinstance(expr, ast.Call):
        _target, name = suite.resolve(rel_path, expr.func)
        if name == "module_of":
            return ("LIVE", "overlay.module_of(...) 交回的活模块")
        if name == "isolated_module":
            return ("ISOLATED", "overlay.isolated_module(...) 现造的副本")
        return ("ISOLATED", "本件把手 %s() 现造的副本" % (name or "?",))
    if isinstance(expr, ast.Name):
        if expr.id in suite.module_object_names(rel_path):
            return ("LIVE", "顶层 import 的活模块 " + expr.id)
        assigned = _local_assignment(func_node, expr.id)
        if assigned is not None:
            return classify_module_arg(suite, rel_path, assigned, func_node, depth + 1)
        if expr.id in _parameters(func_node):
            site = call_site_argument(suite, rel_path, func_node, expr.id)
            if site is not None:
                caller_rel, caller_node, argument = site
                return classify_module_arg(suite, caller_rel, argument, caller_node, depth + 1)
            return ("OTHER", "形参 %s 在读不到调用点" % (expr.id,))
        return ("OTHER", "局部名 " + expr.id)
    return ("OTHER", ast.unparse(expr)[:40])


def call_site_argument(suite: Suite, rel_path, func_node, parameter: str):
    """本件里对 `func_node(...)` 的调用点，按位置取那枚实参（连同它所在的函数）。

    同一枚 (件, 函数, 形参) 只扫一遍文件树：这枚派生要在在册钉里复跑，重复扫树是白付的耗时。
    """
    cache_key = (rel_path, getattr(func_node, "name", None), parameter, id(suite))
    if cache_key in _SITE_CACHE:
        return _SITE_CACHE[cache_key]
    name = getattr(func_node, "name", None)
    if name is None:
        _SITE_CACHE[cache_key] = None
        return None
    parameters = _parameters(func_node)
    if parameter not in parameters:
        _SITE_CACHE[cache_key] = None
        return None
    index = parameters.index(parameter)
    _text, tree = suite.sources[rel_path]
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call) or not call.args or len(call.args) <= index:
            continue
        target, callee = suite.resolve(rel_path, call.func)
        if callee != name or (target and target != rel_path):
            continue
        result = (rel_path, suite.enclosing(rel_path, call.lineno), call.args[index])
        _SITE_CACHE[cache_key] = result
        return result
    _SITE_CACHE[cache_key] = None
    return None


def scan_functions(suite: Suite, win: set):
    """一遍扫完每一枚顶层函数，同时交回三样：调用边、直接构造的窗、直接的装变异腿。

    🔴 合并成一枚把手是刻意的：分三遍走的话，开窗点与腿各拿一份判断，「同一体内既开窗又装变异」
    那一格量的就不是同一次扫描；也是三倍的耗时——本件是给在册钉复跑的。
    """
    graph, built_direct, legs_direct = {}, {}, {}
    for key, node in suite.functions.items():
        edges, built, rows = set(), set(), []
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            target, name = suite.resolve(key[0], call.func)
            if not name:
                continue
            if target and (target, name) in suite.functions and not name.startswith("test"):
                edges.add((target, name))          # 用例本体不是把手：边不指过去
            if target and (target, name) in win:
                built.add((target, name))
            if name == INSTALL_HANDLE and target == R466_REL:
                if not call.args:
                    rows.append(("OTHER", "install_mutation 少了第一参数", call.lineno, key[0]))
                    continue
                kind, why = classify_module_arg(suite, key[0], call.args[0], node)
                rows.append((kind, why, call.lineno, key[0]))
        graph[key], built_direct[key], legs_direct[key] = edges, built, rows
    return graph, built_direct, legs_direct


def _accumulate(direct: dict, graph: dict) -> dict:
    """沿调用图（只走非用例把手）把每一枚节点的自有读数并到「它 + 它能走到的」上。

    🔴 前驱工作队列：只有真的长出新东西才惊动上游。全量重扫在 500 枚件的输入面上要跑到分钟级，
    这枚派生是给在册钉用的，慢到这个形状没人敢复跑。
    """
    acc = {key: set(value) for key, value in direct.items()}
    predecessors: dict = {}
    for key, edges in graph.items():
        for step in edges:
            predecessors.setdefault(step, set()).add(key)
    pending = list(acc)
    in_pending = set(pending)
    while pending:
        key = pending.pop(0)
        in_pending.discard(key)
        grown = set()
        for step in graph.get(key, ()):
            extra = acc.get(step, set()) - acc[key]
            if extra:
                acc[key] |= extra
                grown.add(step)
        if grown:
            for upstream in predecessors.get(key, ()):
                if upstream not in in_pending:
                    in_pending.add(upstream)
                    pending.append(upstream)
    return acc


def exec_posture_classes(suite: Suite, win: set) -> set:
    """类体里写着 ``execs_module = True`` 的那几枚窗（旧姿势）：由 R556 那枚钉单独看管。"""
    found = set()
    for key, node in suite.classes.items():
        if key not in win:
            continue
        for statement in node.body:
            if isinstance(statement, ast.Assign) and any(
                isinstance(tg, ast.Name) and tg.id == "execs_module" for tg in statement.targets
            ) and ast.unparse(statement.value) == "True":
                found.add(key)
    return found


def inventory(sources: dict) -> dict:
    """派生读数：live／isolated／exec／no_install 四族，逐枚带开窗点与腿的理由。"""
    cache_key = id(sources)
    if cache_key in _INVENTORY:
        return _INVENTORY[cache_key]
    suite = Suite(sources)
    win = window_classes(suite)
    graph, built_direct, legs_direct = scan_functions(suite, win)
    opens = _accumulate(built_direct, graph)                    # 谁会开窗（含借把手）
    legs_via = _accumulate({key: set(rows) for key, rows in legs_direct.items()}, graph)

    live: dict = {}
    opened_files: dict = {}
    for key in sorted(suite.functions):
        rel_path, name = key
        windows = opens.get(key) or set()
        if not windows:
            continue
        file_entry = opened_files.setdefault(rel_path, {"windows": set(), "open_sites": []})
        file_entry["windows"].update("%s@%s" % (n, d.split("/")[-1]) for (d, n) in windows)
        file_entry["open_sites"].append("%s:L%d" % (name, suite.functions[key].lineno))
        entry = live.setdefault(rel_path, {"windows": set(), "open_sites": [], "live_hands": [],
                                           "isolated_hands": [], "clause": ""})
        entry["windows"].update(file_entry["windows"])
        entry["open_sites"].extend(file_entry["open_sites"])
        rows_all = sorted(legs_via.get(key, ()))
        kinds = {row[0] for row in rows_all}
        if "LIVE" in kinds:
            row = next(r for r in rows_all if r[0] == "LIVE")
            entry["live_hands"].append("%s -> %s @%s:L%d" % (name, row[1], row[3].split("/")[-1], row[2]))
            entry["clause"] = entry["clause"] or "甲式（开窗与活模块腿同体或经把手传递）"
        elif kinds and kinds <= {"ISOLATED", "OTHER"}:
            iso = [r for r in rows_all if r[0] == "ISOLATED"]
            if iso:
                entry["isolated_hands"].append("%s -> %s @%s:L%d" % (name, iso[0][1], iso[0][3].split("/")[-1], iso[0][2]))

    # 乙式：开窗点在本件、LIVE 腿在本件另一枚**非用例**把手里（r495 那族：窗由 KNIFE_* 造）
    for rel_path, entry in live.items():
        if entry["live_hands"]:
            continue
        for key, rows in legs_direct.items():
            if key[0] != rel_path or key[1].startswith("test"):
                continue
            live_rows = [r for r in rows if r[0] == "LIVE"]
            if live_rows:
                entry["clause"] = "乙式（窗与活模块腿分家，靠本件非用例把手接上）"
                entry["live_hands"].append("%s -> %s @%s:L%d" % (key[1], live_rows[0][1], key[0], live_rows[0][2]))

    isolated, no_install = {}, {}
    for rel_path, entry in list(live.items()):
        if entry["live_hands"]:
            continue
        if entry["isolated_hands"]:
            isolated[rel_path] = entry
        live.pop(rel_path)
    exec_homes = {}
    for (def_rel, cls_name) in sorted(exec_posture_classes(suite, win)):
        for rel_path, entry in opened_files.items():
            if any(token.split("@")[0] == cls_name for token in entry["windows"]):
                exec_homes.setdefault(rel_path, {"windows": set(), "classes": set()})
                exec_homes[rel_path]["windows"].update(entry["windows"])
                exec_homes[rel_path]["classes"].add("%s@%s" % (cls_name, def_rel.split("/")[-1]))
    for rel_path in sorted(exec_homes):
        entry = {"windows": sorted(exec_homes[rel_path]["windows"]),
                 "classes": sorted(exec_homes[rel_path]["classes"]),
                 "open_sites": sorted(opened_files[rel_path]["open_sites"])}
        exec_homes[rel_path] = entry
        isolated.pop(rel_path, None)
        live.pop(rel_path, None)
        no_install.pop(rel_path, None)
    for rel_path, entry in opened_files.items():
        if rel_path in live or rel_path in isolated or rel_path in exec_homes:
            continue
        no_install[rel_path] = {"windows": sorted(entry["windows"]), "open_sites": sorted(entry["open_sites"])}
    result = {"live": live, "isolated": isolated, "exec_posture": exec_homes, "no_install": no_install,
              "window_classes": win, "suite": suite, "sources": sources}
    _INVENTORY[cache_key] = result
    return result


def test_every_window_home_lands_in_exactly_one_family():
    """四族互斥且不漏：每一枚开窗的家只能落在一族里，名册只管 LIVE 那一族。

    这枚钉是判据 ② 的骨架——「缺哪枚点名哪枚」要成立，前提是分类不许把一枚家同时算进两族，
    也不许有一枚家四族都不在（那才是真的失踪）。
    """
    sources, _roster_text = default_surfaces()
    read = inventory(sources)
    families = {"live": set(read["live"]), "isolated": set(read["isolated"]),
                "exec_posture": set(read["exec_posture"]), "no_install": set(read["no_install"])}
    names = sorted(families)
    for index, first in enumerate(names):
        for second in names[index + 1:]:
            both = sorted(families[first] & families[second])
            assert not both, "%s 与 %s 两族重叠：%s：一枚家不许同时被算进两族" % (first, second, both)
    suite, win = read["suite"], read["window_classes"]
    direct = {key[0] for key, built in scan_functions(suite, win)[1].items() if built}
    lost = sorted(direct - set().union(*families.values()))
    assert not lost, "这些件直接构造了窗，却四族都不在（静默失踪）：%s" % (lost,)
    print("[r583] 四族枚数 live=%d isolated=%d exec=%d no_install=%d；直接构造窗的 %d 枚家全部落族"
          % (len(families["live"]), len(families["isolated"]), len(families["exec_posture"]),
             len(families["no_install"]), len(direct)))


def roster_rows_from_text(text: str) -> list:
    """从名册的**文本面**抠行：`WINDOWS` 那枚元组里逐枚 dict 的字面键（不 import，不执行）。"""
    tree = ast.parse(text)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "WINDOWS":
                rows = []
                for element in getattr(node.value, "elts", []):
                    if not isinstance(element, ast.Dict):
                        continue
                    row = {}
                    for key, value in zip(element.keys, element.values):
                        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                            continue
                        if isinstance(value, ast.Constant):
                            row[key.value] = value.value
                        elif isinstance(value, ast.Name):
                            row[key.value] = "<opener:" + value.id + ">"
                    rows.append(row)
                return rows
    raise AssertionError("文本面里读不到 `WINDOWS` 的赋值：名册换了形状，本件要跟着改写")


def reconcile(rows: list, homes: set) -> dict:
    """名册与派生清单逐枚对账：缺哪枚点名哪枚，多哪枚点名哪枚。"""
    registered = set()
    for row in rows:
        registered.add(str(row.get("test_file", "")).replace(".", "/") + ".py")
    return {"missing": sorted(homes - registered), "extra": sorted(registered - homes),
            "registered_count": len(registered), "derived_count": len(homes)}


def default_surfaces():
    """盘上的两份输入面：`tests/**` 文本 + 名册文本（都只读）。"""
    token = "suite"
    if token not in _SOURCES:
        _SOURCES[token] = (r253pin.suite_sources(), (r253pin.TESTS_DIR / "test_r466_mutation_does_not_leak_into_live_module.py").read_text(encoding="utf-8"))
    return _SOURCES[token]


def assert_roster_matches_the_inventory(rows: list, text_rows: list, homes: set) -> dict:
    """名册（活对象 + 文本面）与派生清单对账的**本体**。

    🔴 拆成普通函数是判据 ④ 的要求：反证要驱动同一枚判据，不许另造一套近似逻辑——那正是
    「摘掉守卫照样绿」的温床。这里一次核五格：清单不许空、名册不许同名行、文本面与活对象不许
    只改一面、R466 那 9 枚不许反弹、缺哪枚/多哪枚逐枚点名，最后才是枚数同数。
    """
    assert homes, "派生清单是空的：真实开窗者一枚都认不出，这格就成了空转的绿"
    keys = sorted(row["key"] for row in rows)
    assert len(set(keys)) == len(keys), "名册里有同名行：%s" % (keys,)
    assert sorted(row["key"] for row in text_rows) == keys, (
        "名册的文本面与活对象对不上（文本 %d 行 / 对象 %d 行）：有人只改了其中一面"
        % (len(text_rows), len(rows)))
    registered = {row["test_file"].replace(".", "/") + ".py" for row in rows}
    gone = sorted(set(HISTORICAL_NINE) - registered)
    assert not gone, "R466 那 9 枚里有 %s 离开了名册：名单不许反弹" % (gone,)
    gap = reconcile(text_rows, homes)
    assert not gap["missing"], (
        "这些窗真往被跟踪文件的活模块上装了变异却没进册（甲案：进册）：%s" % (gap["missing"],))
    assert not gap["extra"], (
        "名册里这些行在派生清单里找不到对应的活模块窗：%s" % (gap["extra"],))
    assert len(rows) == len(homes), (
        "枚数与真实开窗者不同名册：%d 行 vs 派生 %d 枚" % (len(rows), len(homes)))
    return {"rows": len(rows), "derived": len(homes), "keys": keys, "gap": gap}


def test_the_inventory_is_derived_and_keeps_the_historical_nine():
    """判据 ①：派生清单非空、逐枚带腿的出处，且 R466 那九枚一枚不少（名单不许反弹）。"""
    sources, _roster_text = default_surfaces()
    read = inventory(sources)
    homes = set(read["live"])
    assert homes, "派生不到任何一枚往活模块上装变异的窗：开窗点判据瞎了"
    gone = sorted(set(HISTORICAL_NINE) - homes)
    assert not gone, "R466 在册的那九枚里有 %s 从派生清单消失了：开窗点认不出它了" % (gone,)
    for rel_path in sorted(homes):
        entry = read["live"][rel_path]
        assert entry["live_hands"], "%s 进了 LIVE 却没交回活模块腿的出处：分类器在猜" % rel_path
        assert entry["windows"], rel_path + " 被列成开窗者却没点名是哪扇窗"
    print("[r583] 判据① 派生：LIVE %d 枚 · 隔离腿 %d 枚 · 只开窗不装变异 %d 枚 · 窗类 %d 枚"
          % (len(homes), len(read["isolated"]), len(read["no_install"]), len(read["window_classes"])))


def test_the_derived_openers_are_recognised_by_the_registered_truth():
    """判据 ① 的交叉核对：本件的细口径必须落在在册真源 `window_handles()` 的粗口径里。"""
    sources, _roster_text = default_surfaces()
    handles = r253pin.window_handles(sources)
    assert handles, "在册真源派生不到把手名：交叉核对无从做起"
    read = inventory(sources)
    homes = set(read["live"]) | set(read["isolated"]) | set(read["no_install"])
    blind = []
    for rel_path in sorted(homes):
        entry = sources.get(rel_path)
        if entry is None:
            blind.append(rel_path + "(不在输入面上)")
        elif not r253pin.called_handles(entry[1], handles):
            blind.append(rel_path)
    assert not blind, "这些件被本件判成开窗者，在册真源却认不出它调用过任何把手：%s" % (blind,)
    print("[r583] 在册真源派生把手 %d 枚；本件开窗者 %d 枚全部落在其射程内"
          % (len(handles), len(homes)))


def test_the_families_outside_the_roster_are_named_not_lost():
    """判据 ② 的另一半：不进册的三族逐枚点名，不许静默失踪。"""
    sources, _roster_text = default_surfaces()
    read = inventory(sources)
    assert ISOLATED_LEG_REL in read["isolated"], (
        "r499 那扇只往隔离视图上装的窗没被派生认成隔离腿：它要么该进册，要么该被点名，"
        "实取 isolated=%s" % (sorted(read["isolated"]),))
    assert read["isolated"][ISOLATED_LEG_REL]["isolated_hands"], "隔离腿那一族没交回理由"
    assert read["no_install"], "只开窗不装变异那一族整个空了：口径收窄到认不出 r156／r457／r553 了"
    assert read["exec_posture"], "exec 姿势那一族从派生里消失了：r482／r553 那两枚旧窗没人看了"
    for rel_path in sorted(read["isolated"]):
        print("[r583] 不进册·隔离腿 %s :: %s" % (rel_path, read["isolated"][rel_path]["isolated_hands"]))
    for rel_path in sorted(read["exec_posture"]):
        print("[r583] 不进册·exec 姿势 %s :: %s（由 test_r556_window_posture_is_installed_not_executed 看管）"
              % (rel_path, read["exec_posture"][rel_path]["classes"]))
    for rel_path in sorted(read["no_install"]):
        print("[r583] 不进册·不装变异 %s :: %s" % (rel_path, read["no_install"][rel_path]["windows"]))