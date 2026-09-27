# -*- coding: utf-8 -*-
"""R390 · 退回处置的形状钉：xfail 必须是 strict 的那一种，边界必须是真走的那一条。

这枚钉管「形状」，不管数据。R387 的两笔退回落成主干之后，最容易被后人原地改回去，
而每一种改法今天都可能读不出来：

① read_postgres 换回一枚裸 psycopg.connect —— 棘轮
   （tests/test_r238_bare_connect_ratchet.py）当然会红，但那要等有人再跑一次它；
   本件把同一件事钉成「今天就看得到」，用的还是那枚尺子自己的扫描函数，不复制第二套口径。
② 那枚 xfail 被摘掉 strict —— 今天读不出任何差别（生产标签仍全空，它照样是 xfailed），
   等到标签回填、判据转好的那一天，非 strict 的 xfail 会静静变成一次无人报警的 XPASS，
   于是「验收 C 已验」这句没人生核过的话就自己长出来了。现读 pyproject 的
   [tool.pytest.ini_options] 里**没有** xfail_strict 这一项，全局默认 = strict=False，
   所以「必须有显式 strict=True 关键字」这一格是承重的，不是好看。
③ 整枚换成 skip —— skip 会被读成「这格过了」，正是上一班拒绝 skip 的理由。
④ 把登记阻塞的那枚 test_the_blocker_is_recorded_and_moves_with_the_data 一起 xfail 掉 ——
   整件测试就没有主张了。

与常驻红的分工：tests/test_r387_production_label_leg.py 今天交回 4 passed + 1 xfailed；
本件只钉它「为什么长这样」，不重复量它里面的数。判「裸连」的口径只此一家：直接 import
那枚尺子自己的 scan_source，本件不重写一遍第二本账。
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

TOOL_REL = "scripts/r387_label_lineage.py"
LEG_REL = "tests/test_r387_production_label_leg.py"
RULER_REL = "tests/test_r238_bare_connect_ratchet.py"

#: 唯一被允许带 xfail 的那一枚，以及必须保持真绿的那一枚。
XFAILED_TEST = "test_acceptance_c_department_leg_passes_on_production"
REGISTERING_TEST = "test_the_blocker_is_recorded_and_moves_with_the_data"

#: reason 要能当台账读：既要说「未验」，也要点得出阻塞因由与今天的读数。
REASON_KEYWORDS = ("未验", "department", "0/1008")

#: 会让一枚判据闭嘴的 mark 名（取点名的末段）。
SILENCERS = frozenset({"xfail", "skip", "skipif"})

BOUNDARY_MODULE = "app.db.connection"
BOUNDARY_NAMES = frozenset({"open_connection", "parse_database_settings"})

#: 自建正则之类是合法调用，所以这组只按「裸名字」匹配（re.compile 不算，compile 才算）。
BARE_DYNAMIC = frozenset({"exec", "eval", "compile", "__import__", "globals", "vars"})

#: 动态导入的两种写法按点名匹配。
DYNAMIC_IMPORTS = frozenset({"import_module", "reload"})

#: 驱动名一旦出现在非 docstring 的字符串里，就是「把 connect 拼出来」的形状。
DRIVER_ROOTS = frozenset({"psycopg", "psycopg2", "psycopg_binary"})

MISSING = object()


def _load_by_path(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    assert spec and spec.loader, "无法加载：" + rel
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: 借尺子自己的扫描函数，不复制第二套「什么算裸连」的判序。
RULER = _load_by_path("r238_bare_connect_ratchet_for_r390", RULER_REL)


def _source(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _tree(rel: str) -> ast.Module:
    return ast.parse(_source(rel), filename=rel)


def _functions(tree: ast.Module) -> dict:
    return {node.name: node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _name(node) -> str:
    return node.id if isinstance(node, ast.Name) else ""


def _dotted(node):
    """把 a.b.c（含调用形状）折成点名字符串；取不到名字就返回 None。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return head + "." + node.attr if head else node.attr
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return None


def _last(name) -> str:
    return (name or "").split(".")[-1]


def _root(dotted: str) -> str:
    """psycopg.connection / psycopg 一律折成根名 psycopg。"""
    return (dotted or "").split(".")[0]


def _marks(func) -> list:
    """返回 [(点名, 装饰器节点)]，连不带括号的裸 mark 一起算（裸 xfail = strict=False）。"""
    out = []
    for dec in func.decorator_list:
        dotted = _dotted(dec)
        if dotted:
            out.append((dotted, dec))
    return out


def _module_literal(tree: ast.Module, name: str):
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and any(_name(t) == name for t in stmt.targets):
            try:
                return ast.literal_eval(stmt.value)
            except ValueError:
                return MISSING
    return MISSING


def _marker_keyword(tree: ast.Module, func_name: str, keyword: str):
    """读那一枚 xfail 标记的关键字：reason 给的是 Name 就顺到模块级赋值去取值。"""
    marks = [dec for dec_name, dec in _marks(_functions(tree)[func_name])
             if _last(dec_name) == "xfail" and isinstance(dec, ast.Call)]
    assert marks, func_name + " 上没有带括号的 xfail 标记，读不出 " + keyword

    for kw in marks[0].keywords:
        if kw.arg != keyword:
            continue
        node = kw.value
        if isinstance(node, ast.Name):
            return _module_literal(tree, node.id)
        try:
            return ast.literal_eval(node)
        except ValueError:
            return MISSING
    return MISSING


def _docstring_nodes(tree: ast.Module) -> set:
    """模块/类/函数的 docstring 节点：那是散文，允许写着 psycopg.connect 这四个字符。"""
    docs = set()
    holders = [tree]
    holders += [node for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    for holder in holders:
        body = getattr(holder, "body", None) or []
        first = body[0] if body else None
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            docs.add(id(first.value))
    return docs


# ===================================================== 判据①：read_postgres 走边界，不许假修复

def test_read_postgres_is_invisible_to_the_rulers_own_ast_scan() -> None:
    """那枚尺子自己扫本文件必须零命中 —— 不是「少一枚」，是一枚都不许有。"""
    sites = RULER.scan_source(TOOL_REL, _source(TOOL_REL))

    assert sites == [], (
        TOOL_REL + " 又长出边界之外的裸连：" + str([hit.identity for hit in sites])
        + " —— 全仓只供 app/db/connection.py 这一枚边界（政策见 app/notifications/states.py 上方注释）")


def test_read_postgres_opens_its_connection_through_the_boundary() -> None:
    """边界调用必须真在：模块顶上取符号 + read_postgres 里真调 + 真压 read_only = True。"""
    tree = _tree(TOOL_REL)
    imported = {alias.name for node in tree.body
                if isinstance(node, ast.ImportFrom) and node.module == BOUNDARY_MODULE
                for alias in node.names}

    assert BOUNDARY_NAMES <= imported, (
        "没在模块顶上从 " + BOUNDARY_MODULE + " 取 " + str(sorted(BOUNDARY_NAMES))
        + "，现读：" + str(sorted(imported)) + "（函数里 lazy import 不算——原版就是这么漏的）")

    func = _functions(tree)["read_postgres"]
    called = {_dotted(node) for node in ast.walk(func) if isinstance(node, ast.Call)}

    assert "parse_database_settings" in called, "read_postgres 不再经 parse_database_settings 校验连接串"
    assert "open_connection" in called, "read_postgres 不再经 open_connection 取连接：边界只被 import 了没用"

    guards = [node for node in ast.walk(func) if isinstance(node, ast.Assign)
              and any(isinstance(t, ast.Attribute) and t.attr == "read_only" for t in node.targets)]
    assert guards, "read_postgres 不再压 conn.read_only = True（psycopg3 会话事务只读，误写当场报错）"
    value = guards[0].value

    assert isinstance(value, ast.Constant) and value.value is True, (
        "conn.read_only 被改成不真只读了：" + ast.dump(value))


def test_the_boundary_call_is_not_concealed_behind_dynamic_eval_or_strings() -> None:
    """🔴 挡「假修复」：把裸 connect 藏进动态求值 / 动态导入 / 字符串 / getattr 里，一律红。

    这格存在的理由是棘轮自己的形状表并不覆盖全部绕法：`import psycopg` 再
    `getattr(psycopg, "connect")(url)` 今天就能骗过它（它记的是 connect 符号与调用点）。
    所以本件替它补上扫不到的四条路。
    """
    tree = _tree(TOOL_REL)

    dynamic = sorted({
        _dotted(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id in BARE_DYNAMIC)
            or _last(_dotted(node)) in DYNAMIC_IMPORTS
        )
    })
    assert not dynamic, ("取证件里出现动态求值/动态导入 " + str(dynamic) + "：那是绕过 AST 扫描的现成路子")

    drivers = sorted({
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if _root(alias.name) in DRIVER_ROOTS
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and _root(node.module or "") in DRIVER_ROOTS
    })
    assert not drivers, ("取证件自己 import 了驱动 " + str(drivers) + "：握着模块就随时能裸连，边界之外不许再要一条路")

    docs = _docstring_nodes(tree)
    smuggled = sorted({
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docs
        and any(root in node.value.lower() for root in DRIVER_ROOTS)
    })
    assert not smuggled, ("非 docstring 的字符串常量里出现了驱动名 " + str(smuggled) + "：靠字符串拼出 connect 的写法棘轮扫不到，本件扫得到")

    dialled = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _last(_dotted(node)) in {"getattr", "setattr"}
        and any(
            isinstance(arg, ast.Constant)
            and isinstance(arg.value, str)
            and "connect" in arg.value.lower()
            for arg in node.args
        )
    ]
    assert not dialled, "用 getattr/setattr 按名字取 connect 符号的写法出现在行 " + str(dialled)

def test_the_read_only_guards_and_the_wrong_database_gate_survive() -> None:
    """三格里的两格逐格对：只读语义（两道守卫）与 expect_database 闸门，都不许顺手带走。"""
    func = _functions(_tree(TOOL_REL))["read_postgres"]
    executed = sorted({node.args[0].value for node in ast.walk(func)
                       if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                       and node.func.attr == "execute" and node.args
                       and isinstance(node.args[0], ast.Constant)
                       and isinstance(node.args[0].value, str)})

    assert "SET default_transaction_read_only = on" in executed, (
        "会话级只读那道 SQL 被摘了；现读执行的语句：" + str(executed))
    assert any("current_database()" in sql for sql in executed), (
        "不再现读连上的是哪个库：expect_database 闸门失去输入")

    gate = [node for node in ast.walk(func) if isinstance(node, ast.Compare)
            and _name(node.left) == "attached"
            and any(_name(comparator) == "expect_database" for comparator in node.comparators)
            and any(isinstance(op, ast.NotEq) for op in node.ops)]
    assert gate, "attached != expect_database 那格比对不见了：把别人的库读成生产的老事故形状就回来了"

    aborts = [node for node in ast.walk(func) if isinstance(node, ast.Raise)
              and _last(_dotted(node.exc)) == "SystemExit"]
    assert aborts, "闸门不放行时不再 raise SystemExit(ABORT)"


# ================================================= 判据②：xfail-strict 只加在该加的那一枚上

def test_the_xfail_lands_on_exactly_the_acceptance_c_leg() -> None:
    """带 xfail 的枚数与身份都是唯一的一格：多一枚、少一枚都红。"""
    marked = sorted(name for name, func in _functions(_tree(LEG_REL)).items()
                    if any(_last(dec_name) == "xfail" for dec_name, _ in _marks(func)))

    assert marked == [XFAILED_TEST], (
        "带 xfail 的是 " + str(marked) + "，定案只允许 " + XFAILED_TEST
        + " 那一枚：把 " + REGISTERING_TEST + " 一起 xfail 掉 = 整件没有主张")


def test_that_xfail_is_strict_true_not_bare_not_false() -> None:
    """🔴 摘掉 strict 就得红：非 strict 的 XPASS 不报警，那格会悄悄变成假绿。"""
    tree = _tree(LEG_REL)
    marks = [dec for dec_name, dec in _marks(_functions(tree)[XFAILED_TEST])
             if _last(dec_name) == "xfail"]

    assert marks, XFAILED_TEST + " 上的 xfail 标记不见了"
    for dec in marks:
        assert isinstance(dec, ast.Call), (
            "xfail 写成了不带括号的裸 mark：pyproject 没有全局 xfail_strict，"
            "裸 mark 等于 strict=False，判据转好那天不会红出来")

    strict = _marker_keyword(tree, XFAILED_TEST, "strict")

    assert strict is True, (
        "xfail 的 strict 关键字读数是 " + str(strict) + "，定案要 True（缺省、False、非字面量都算摘掉）")


def test_the_reason_is_a_ledger_entry_naming_the_blocker_and_its_source() -> None:
    """reason 要能当台账读：说「未验」、点得出阻塞关键字，并指向一枚真存在的文档。"""
    tree = _tree(LEG_REL)
    reason = _marker_keyword(tree, XFAILED_TEST, "reason")

    assert isinstance(reason, str) and reason.strip(), (
        "reason 必须解析得出一个非空字符串，现读：" + str(reason))
    missing = [word for word in REASON_KEYWORDS if word not in reason]
    assert not missing, (
        "reason 里少了阻塞关键字 " + str(missing) + "（防止被换成一句空话蒙过去）。原文：" + reason)

    cited = re.findall("docs/[^ ]*[.]md", reason)

    assert cited, "reason 没点名出处文档的相对路径：" + reason
    for rel in cited:
        assert (REPO / rel).is_file(), "reason 点名的出处文档不在树里：" + rel


def test_the_blocker_registration_test_stays_unmarked() -> None:
    """登记「阻塞在案」的那枚必须保持真绿：它一被挂上任何静音 mark，本件红。"""
    func = _functions(_tree(LEG_REL))[REGISTERING_TEST]
    silenced = sorted(dec_name for dec_name, _ in _marks(func) if _last(dec_name) in SILENCERS)

    assert not silenced, REGISTERING_TEST + " 被挂了 " + str(silenced) + "：它是账，不是待办"


def test_the_xfailed_leg_is_not_also_silenced_by_a_skip_mark() -> None:
    """刀②的钉子：xfail 整枚换成 skip 之后，这里读到的不是空集而是「多了 skip」。"""
    func = _functions(_tree(LEG_REL))[XFAILED_TEST]
    silenced = sorted(dec_name for dec_name, _ in _marks(func)
                      if _last(dec_name) in (SILENCERS - {"xfail"}))

    assert not silenced, XFAILED_TEST + " 上另挂了 " + str(silenced) + "：skip 会被读成「这格过了」"


def test_no_runtime_xfail_call_masquerades_as_the_marker() -> None:
    """刀④的钉子：装饰器之外出现运行时 pytest.xfail()/xfail() 调用就红。

    运行时 xfail 同样能让门绿，但它把「这一枚判据今天不成立」降级成执行到那一行才说的话——
    前面的代码一跑飞，xfail 就永远轮不到，摘要里照样一枚 xfailed 都不剩。
    """
    tree = _tree(LEG_REL)
    decorated = {id(dec) for func in _functions(tree).values() for dec in func.decorator_list}
    runtime = [node.lineno for node in ast.walk(tree)
               if isinstance(node, ast.Call) and id(node) not in decorated
               and _last(_dotted(node)) == "xfail"]

    assert not runtime, (
        "本件出现运行时 xfail 调用（行 " + str(runtime)
        + "）：定案要的是标记形状 @pytest.mark.xfail(strict=True)")


def test_container_absence_still_skips_with_the_original_words() -> None:
    """环境缺失那两枚 skip 的原语义一字不许动：那是「本机读不到库」，不是「判据未成立」。"""
    tree = _tree(LEG_REL)
    for fixture in ("census", "production_arm"):
        skips = [node for node in ast.walk(_functions(tree)[fixture])
                 if isinstance(node, ast.Call) and _last(_dotted(node)) == "skip"]

        assert len(skips) == 1, fixture + " 里的 skip 调用现在是 " + str(len(skips)) + " 枚，定案是一枚"
        args = skips[0].args
        assert len(args) == 1 and _name(args[0]) == "UNAVAILABLE", (
            fixture + " 的 skip 不再引用 UNAVAILABLE 那句话：容器不在位那格的原语义被动了")

    unavailable = _module_literal(tree, "UNAVAILABLE")

    assert isinstance(unavailable, str) and "未验" in unavailable, (
        "UNAVAILABLE 不再写明「未验」：" + str(unavailable))
    live = [node for node in tree.body if isinstance(node, ast.Assign)
            and any(_name(t) == "LIVE" for t in node.targets)]
    assert live and _dotted(live[0].value) == "production_available", (
        "LIVE 不再由 production_available() 现算：那两枚 skip 就会开始凭空地放行")
