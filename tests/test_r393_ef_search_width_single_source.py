# -*- coding: utf-8 -*-
"""R393 判据①③④：两枚在册向量量具的候选宽度只允许有一个真源。

钉的是什么
----------
``scripts/r59_recall_compare.py`` 与 ``scripts/r59c_sandbox_corpus.py`` 过去各自带着一枚
HNSW 候选宽度：前者把 ``--pg-ef-search`` 的缺省写成"用库里的默认"（库里那一档是 pgvector 的
出厂档），后者把同一个数抄了三份（签名默认值、生成的 SQL、CLI 默认值）。生产读腿在 R386 已经
把"这个数只能活在一处"钉死（``app/rag/pg_store.py`` 里那枚 ``configured_hnsw_ef_search``），
量具却站在另一档上量 —— 凡是没显式给值时取过的召回读数，量的都不是生产那一档。

本件全程离线：不连库、不起容器、不打模型。它只读那两枚脚本的文本与 AST，外加在假模块缝上验
一次"取不到真源时必须炸"。

为什么这么钉
------------
* 只禁"宽度语境行"里的档位数字，不全文件禁数字：``ef_construction`` 是**建索引**参数，与查询期
  候选宽度无关（R386 已把这条区别写进看板），一刀切会把量具指错方向。
* 真源必须在函数体内被调用：import 期取一次再赋给模块常量，等于又立一枚会漂的数，而且旋钮改口
  之后没人听得到 —— 那正是 R386 立"被问到才定档"的理由，量具必须跟着。
* 解析函数不许**返回**数字：``except ...: return <一档>`` 是"悄悄退回自定档"的那一种形状，而
  ``str(exc)[:160]`` 这类截断长度不是宽度，把它一起禁掉只会把钉磨钝。
"""
import ast
import contextlib
import importlib.util
import io
import pathlib
import re
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS = ("scripts/r59_recall_compare.py", "scripts/r59c_sandbox_corpus.py")
DOC = ROOT / "docs" / "perf" / "r393-tool-width-drift-2026-09-27.md"

#: 一行源码在"谈候选宽度"的判据：命中任一记号即算宽度语境。
WIDTH_CONTEXT = re.compile(
    r"ef_search|ef-search|hnsw|set_config|current_setting|pg_settings|SHOW ", re.I)
#: 建索引参数不是查询期候选宽度：那一行的 100 是 m / ef_construction。
INDEX_BUILD_PARAM = re.compile(r"ef_construction", re.I)
#: 2026-09-27 在容器里实测过的两档就是这两个数（出厂档与生产真源那一档）。
BANNED_WIDTH_NUMBER = re.compile(r"(?<![\dA-Za-z_.\-])(40|100)(?![\dA-Za-z_.\-])")
#: 名字里带这些词的绑定，右边不许出现写死的数字。
WIDTH_NAME = re.compile(r"(?i)(ef_search|width)")
TRUE_SOURCE_SYMBOL = "configured_hnsw_ef_search"
LIBRARY_DEFAULT_PHRASE = "用库里的默认"
#: 会话级设定与裸 SHOW 这两种写法：前者污染同一条连接后面的每一次读数，后者在库没加载的会话里
#: 直接报错 —— 而它过去正是取证格长期空着的那条路。
SESSION_SET = re.compile(r"^\s*SET\s+(LOCAL\s+)?hnsw", re.I)
BARE_SHOW = re.compile(r"^\s*SHOW\s+hnsw", re.I)
RESOLVERS = {
    "scripts/r59_recall_compare.py": ("resolve_ef_search", "pg_store_true_source"),
    "scripts/r59c_sandbox_corpus.py": ("resolve_probe_ef_search", "probe_ef_source"),
}


def _text(rel):
    return (ROOT / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")


def _tree(rel):
    return ast.parse(_text(rel))


def _parents(tree):
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _int_literals(node):
    """表达式里自己写死的数字。切片里的不算：``rows[0]``、``str(exc)[:160]`` 都不是档位。"""
    skip = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Subscript):
            skip.update(id(item) for item in ast.walk(sub.slice))
    return [item.value for item in ast.walk(node)
            if isinstance(item, ast.Constant) and isinstance(item.value, int)
            and not isinstance(item.value, bool) and id(item) not in skip]


def _string_constants(tree):
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def _target_names(target):
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for item in target.elts for name in _target_names(item)]
    return []


def _function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("这棵树里找不到函数 " + name)


def _load(rel, alias):
    spec = importlib.util.spec_from_file_location(alias, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------- 判据①：不许有第二处数字

def test_no_candidate_width_number_on_any_width_line():
    """两枚脚本里，任何一行在谈候选宽度的源码都不许带那两枚实测档位。"""
    offenders = []
    for rel in TOOLS:
        for position, line in enumerate(_text(rel).split("\n"), start=1):
            if not WIDTH_CONTEXT.search(line) or INDEX_BUILD_PARAM.search(line):
                continue
            if BANNED_WIDTH_NUMBER.search(line):
                offenders.append("%s:%d %s" % (rel, position, line.strip()[:90]))
    assert not offenders, ("宽度语境行里又出现了档位数字（单一真源被抄破）："
                           + " | ".join(offenders))


def test_the_index_build_exemption_covers_only_build_parameters():
    """豁免不能变成后门：借 ef_construction 免掉的行，必须确实在建索引。"""
    for rel in TOOLS:
        for position, line in enumerate(_text(rel).split("\n"), start=1):
            if not (WIDTH_CONTEXT.search(line) and INDEX_BUILD_PARAM.search(line)
                    and BANNED_WIDTH_NUMBER.search(line)):
                continue
            assert "USING hnsw" in line or "ef_construction=" in line, (
                rel + ":" + str(position) + " 借建索引那一行藏了查询期宽度："
                + line.strip()[:90])


def test_no_number_is_bound_to_a_width_name():
    """AST 层面：宽度名字的右边不许有写死的数字。签名默认值、赋值、CLI default 都算。"""
    for rel in TOOLS:
        tree = _tree(rel)
        parents = _parents(tree)
        bad = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    for name in _target_names(target):
                        if WIDTH_NAME.search(name):
                            bad += [(name + " 被绑成数字", node.lineno)
                                    for _ in _int_literals(node.value)]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                positional = [arg.arg for arg in node.args.args]
                defaults = list(node.args.defaults)
                pairs = list(zip(positional[len(positional) - len(defaults):], defaults))
                pairs += [(arg.arg, default) for arg, default
                          in zip(node.args.kwonlyargs, node.args.kw_defaults)
                          if default is not None]
                for name, default in pairs:
                    if WIDTH_NAME.search(name):
                        bad += [("%s(...) 的 %s 带数字默认值" % (node.name, name),
                                 default.lineno) for _ in _int_literals(default)]
            if isinstance(node, ast.keyword) and node.arg in ("default", "ef_search"):
                call = node
                while call is not None and not isinstance(call, ast.Call):
                    call = parents.get(call)
                spelled = " ".join(item.value for item in ast.walk(call or ast.Pass())
                                   if isinstance(item, ast.Constant)
                                   and isinstance(item.value, str))
                if re.search(r"ef.?search", spelled, re.I):
                    bad += [(node.arg + "= 数字（CLI 自己带了档）", node.lineno)
                            for _ in _int_literals(node.value)]
        assert not bad, rel + " 里宽度被绑上了数字：" + "; ".join(
            "%s @line %d" % item for item in bad)


def test_true_source_is_the_only_reader_and_is_asked_at_run_time():
    """两枚脚本都必须现场问真源；在 import 期问一次冻成常量，等于又抄了一处。"""
    for rel in TOOLS:
        tree = _tree(rel)
        parents = _parents(tree)
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and node.func.attr == TRUE_SOURCE_SYMBOL]
        assert calls, rel + " 不再向唯一真源 " + TRUE_SOURCE_SYMBOL + " 取候选宽度了"
        for call in calls:
            walker = parents.get(call)
            while walker is not None and not isinstance(
                    walker, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walker = parents.get(walker)
            assert walker is not None, (
                rel + ":" + str(call.lineno) + " 在模块导入期就取宽度：旋钮改口听不到，"
                "这个数就此冻成第二枚常量")


def test_resolvers_raise_and_never_return_a_fallback_number():
    """取不到真源必须炸；解析函数任何一条 return 都不许交出一个写死的数。"""
    for rel, names in RESOLVERS.items():
        tree = _tree(rel)
        for name in names:
            function = _function(tree, name)
            assert any(isinstance(node, ast.Raise) for node in ast.walk(function)), (
                rel + " 的 " + name + " 不报了：取不到真源时它会安静地交出某个数")
            returned = []
            for node in ast.walk(function):
                if isinstance(node, ast.Return) and node.value is not None:
                    returned += [(node.lineno, value) for value in _int_literals(node.value)]
            assert not returned, (rel + " 的 " + name + " 会返回写死的数字 "
                                  + repr(returned) + "：那就是第二处候选宽度")


# ---------------------------------------------- 行为面：真源取不到时明确报错退出

def _poison(monkeypatch, replacement):
    """把 app.rag / app.rag.pg_store 换成假件：None 表示"这棵树上没有这枚模块"。"""
    package = types.ModuleType("app.rag")
    if replacement is not None:
        setattr(package, "pg_store", replacement)
    monkeypatch.setitem(sys.modules, "app.rag", package)
    monkeypatch.setitem(sys.modules, "app.rag.pg_store", replacement)


def test_compare_tool_gives_a_named_exit_when_the_source_is_gone(monkeypatch):
    tool = _load(TOOLS[0], "r393_rc_no_source")
    _poison(monkeypatch, None)
    with pytest.raises(SystemExit) as caught:
        tool.resolve_ef_search()
    message = str(caught.value)
    assert "前置不满足" in message and TRUE_SOURCE_SYMBOL in message, message
    #: 报错里不许顺手给出一个可退回去的数：那等于把第二处宽度藏进错误消息。
    assert not BANNED_WIDTH_NUMBER.search(message), message


def test_sandbox_tool_refuses_to_emit_when_the_source_is_gone(monkeypatch):
    tool = _load(TOOLS[1], "r393_sc_no_source")
    _poison(monkeypatch, None)
    with pytest.raises(SystemExit) as caught:
        tool.resolve_probe_ef_search()
    assert "拒出料" in str(caught.value), str(caught.value)


def test_sandbox_tool_refuses_when_the_source_module_lost_the_symbol(monkeypatch):
    """真源改口（改名、搬走）也算取不到：本件不许猜，必须停。"""
    tool = _load(TOOLS[1], "r393_sc_no_symbol")
    _poison(monkeypatch, types.ModuleType("app.rag.pg_store"))
    with pytest.raises(SystemExit) as caught:
        tool.probe_ef_source()
    assert TRUE_SOURCE_SYMBOL in str(caught.value), str(caught.value)


def test_sandbox_refuses_to_guess_a_changed_setting_statement(monkeypatch):
    """设定语句的形状来自真源：它哪天不再是两枚参数，本件停，而不是拼出一条没见过的 SQL。"""
    tool = _load(TOOLS[1], "r393_sc_shape")
    shifted = types.ModuleType("app.rag.pg_store")
    shifted.configured_hnsw_ef_search = lambda environ=None: 7
    shifted.HNSW_EF_SEARCH_GUC = "hnsw.ef_search"
    shifted._APPLY_HNSW_EF_SEARCH_SQL = "SELECT set_config(%s, %s, %s, TRUE)"
    _poison(monkeypatch, shifted)
    with pytest.raises(SystemExit) as caught:
        tool.render_apply_width_sql(7)
    assert "拒出料" in str(caught.value), str(caught.value)


# ------------------------------------------------- 判据③：会话级 SET 与裸 SHOW 封死

def test_no_session_level_set_and_no_bare_show_in_any_string_constant():
    """两枚脚本的字符串常量里不许再出现会话级设定，也不许再发裸 SHOW（库没加载时它必炸）。"""
    for rel in TOOLS:
        hits = [value[:70] for value in _string_constants(_tree(rel))
                if SESSION_SET.search(value) or BARE_SHOW.search(value)]
        assert not hits, rel + " 里还留着会话级 SET 或裸 SHOW：" + repr(hits)


def test_the_cli_defaults_no_longer_promise_a_library_default():
    """两枚脚本的 CLI 缺省都不再指向库里那一档：默认 None，help 里点名唯一真源。"""
    compare = _load(TOOLS[0], "r393_rc_defaults")
    sandbox = _load(TOOLS[1], "r393_sc_defaults")
    assert compare.parse_args([]).pg_ef_search is None
    assert sandbox.build_parser().parse_args(["plan", "--out", "x"]).ef_search is None
    buffer = io.StringIO()
    for call in (lambda: compare.parse_args(["--help"]),
                 lambda: sandbox.build_parser().parse_args(["plan", "--help"])):
        with pytest.raises(SystemExit):
            with contextlib.redirect_stdout(buffer):
                call()
    help_text = buffer.getvalue()
    assert LIBRARY_DEFAULT_PHRASE not in help_text, "help 还在承诺库里那一档"
    assert TRUE_SOURCE_SYMBOL in help_text, "help 没说出缺省跟随哪一枚真源"


def test_the_default_tracks_the_knob_at_call_time(monkeypatch):
    """缺省跟随真源，而且是被问到才定档：旋钮改口之后再生成一次，档必须跟着变。"""
    from app.rag import pg_store

    compare = _load(TOOLS[0], "r393_rc_knob")
    sandbox = _load(TOOLS[1], "r393_sc_knob")
    monkeypatch.delenv(pg_store.ENV_HNSW_EF_SEARCH, raising=False)
    baseline = pg_store.configured_hnsw_ef_search()
    assert compare.resolve_ef_search() == baseline
    assert sandbox.resolve_probe_ef_search()[0] == baseline
    moved = baseline + 11
    monkeypatch.setenv(pg_store.ENV_HNSW_EF_SEARCH, str(moved))
    assert pg_store.configured_hnsw_ef_search() == moved
    assert compare.resolve_ef_search() == moved, "旋钮改口听不到：宽度被冻在 import 期那一档"
    corpus = sandbox.build_corpus(48)
    matrix = sandbox.build_matrix(corpus, top_k=3, queries=2)
    text = sandbox.emit_probe_queries(corpus, matrix, table="chunk_vectors")
    assert ("HNSW 候选宽度 = %d；" % moved) in text, "生成的批还站在旧档上"


# ---------------------------------------------------------- 判据④：历史读数标记

def test_the_drift_doc_names_both_tools_and_the_qualifier():
    assert DOC.exists(), "缺 docs/perf/r393-tool-width-drift-2026-09-27.md（判据④）"
    text = DOC.read_bytes().decode("utf-8")
    for rel in TOOLS:
        assert rel in text, "漂移单没点名这枚量具：" + rel
    for phrase in ("不可知", "不许外推", "客户尺寸", "未证", LIBRARY_DEFAULT_PHRASE):
        assert phrase in text, "必须落字的那句话不见了：" + phrase
