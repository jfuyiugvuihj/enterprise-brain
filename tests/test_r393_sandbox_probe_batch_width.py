# -*- coding: utf-8 -*-
"""R393 判据①②③：沙盒只读探针这一批踩在哪一档候选宽度上，必须当场可查、且只有一个来历。

钉的是什么
----------
``scripts/r59c_sandbox_corpus.py`` 过去自带一枚候选宽度：函数签名默认值、生成的 SQL 里那句
会话级设定、CLI ``--ef-search`` 的缺省 —— 同一个数在 R386 已经"钉死只能活在一处"之后又被
抄了三份。生产读腿问的是 ``app/rag/pg_store.py`` 里那枚 ``configured_hnsw_ef_search``，
量具却站在自己那一档上量，还用**会话级** SET 把同一条连接后面每一次读数都染了色。

本件再钉一条跟着批头一起进来的回归：探针批头多了 ``BEGIN`` / 库探测 / 事务内设定三句之后，
``read_probe_csv_run`` 若还按「第一行就是表头」读 psql ``--csv`` 的产物，每一条真读数都会被
读没 —— 而"零读数"在 verify 里长得和"没跑"一模一样，这一格照样没人发现。

全程离线：不连库、不起容器、不打模型。psql 的输出形状取自 2026-09-27 在真容器上跑同一批头
的只读实测（``BEGIN`` / ``?column?`` / ``t`` / ``set_config`` / ``<那一档的值>`` / 表头 /
数据行 / 再来一遍表头 / ... / ``ROLLBACK``）。
"""
import ast
import csv
import importlib.util
import inspect
import io
import pathlib
import re
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = "scripts/r59c_sandbox_corpus.py"
#: 会话级设定：它会一直留在这条连接上，把后面每一次读数都染成同一档（判据③封死）。
SESSION_SET = re.compile(r"^\s*SET\s+(LOCAL\s+)?hnsw", re.I)
#: 2026-09-27 在容器里实测过的两档就是这两个数（pgvector 出厂档与生产真源那一档）。
BANNED_WIDTH_NUMBER = re.compile(r"(?<![\dA-Za-z_.\-])(40|100)(?![\dA-Za-z_.\-])")
#: 一行源码/SQL 在"谈候选宽度"的判据。
WIDTH_CONTEXT = re.compile(r"ef_search|ef-search|hnsw|set_config|SHOW ", re.I)
#: GUC 名本身也只许来自真源：脚本里出现它的字面量，就意味着哪天改名没人听得到。
GUC_LITERAL = re.compile(r"hnsw\.ef_search")
#: psql --csv 里那条排名 SELECT 的表头，每回一条都会再打一遍。
DUMP_HEADER = ["cell", "qid", "vector_id", "classification", "department"]


def _load(alias):
    spec = importlib.util.spec_from_file_location(alias, ROOT / TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def _material(tool, queries=3):
    corpus = tool.build_corpus(48)
    return corpus, tool.build_matrix(corpus, top_k=3, queries=queries)


def _production_width(tool):
    """现场向被测件自己认的那枚真源取那一档：钉里不许出现第二个数。"""
    value = tool.probe_ef_source().configured_hnsw_ef_search()
    assert isinstance(value, int) and not isinstance(value, bool), repr(value)
    return int(value)


def _batch(tool, **kwargs):
    corpus, matrix = _material(tool)
    return corpus, matrix, tool.emit_probe_queries(corpus, matrix, table=tool.TABLE,
                                                   **kwargs)


def _setting_lines(text):
    return [line for line in text.splitlines() if "set_config(" in line]


def _psql_dump(matrix, width):
    """照真容器实测的形状拼一份 psql ``--csv`` 产物。

    命令标签与设定输出排在最前面（各占一行、单列），每回一条排名 SELECT 之前再打一遍
    表头 —— 这正是"按第一行当表头读"会把每一条真读数都读没的那一份形状。
    """
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    for tag in ("BEGIN", "?column?", "t", "set_config", str(width)):
        writer.writerow([tag])
    for cell in matrix["cells"]:
        for item in cell["expected"]:
            writer.writerow(DUMP_HEADER)
            for vector_id in item["exact_ids"]:
                writer.writerow([cell["principal"], item["qid"], vector_id, 1, ""])
    writer.writerow(["ROLLBACK"])
    return out.getvalue()


# -------------------------------------- 判据①：批里那一档只有一个来历

def test_the_batch_head_names_the_width_and_its_true_source():
    """批头必须自己说清"这一批踩在哪一档、这一档是谁定的"，读的人不用猜。"""
    tool = _load("r393_probe_head")
    width = _production_width(tool)
    _, _, text = _batch(tool)
    head = text.splitlines()
    assert head[1] == "-- HNSW 候选宽度 = {0}；来历 = {1}".format(
        width, tool.TRUE_SOURCE + "（现场取，与生产读腿同一次调用）"), head[1]
    assert tool.TRUE_SOURCE in text, "批里没有唯一真源的名字"
    assert "作用域 = 事务内" in head[2], head[2]


def test_no_second_width_number_appears_on_any_width_line_of_the_batch():
    """生成的 SQL 里，任何在谈候选宽度的行都不许出现第二个档位数字。"""
    tool = _load("r393_probe_numbers")
    width = _production_width(tool)
    _, _, text = _batch(tool)
    offenders = []
    for position, line in enumerate(text.splitlines(), start=1):
        if not WIDTH_CONTEXT.search(line):
            continue
        for hit in BANNED_WIDTH_NUMBER.finditer(line):
            if hit.group(0) != str(width):
                offenders.append("{0}: {1}".format(position, line.strip()[:80]))
    assert not offenders, "批里出现了不是生产那一档的宽度数字：" + " | ".join(offenders)


def test_the_value_written_in_the_head_is_the_value_the_batch_runs():
    """批头不许说谎：注释里那一档必须就是设定语句真正钉下去的那一档。"""
    tool = _load("r393_probe_head_lies")
    width = _production_width(tool)
    _, _, text = _batch(tool)
    settings = _setting_lines(text)
    assert len(settings) == 1, "批里的设定语句不止一条，读不出踩在哪一档：" + repr(settings)
    assert "'{0}'".format(width) in settings[0], (settings[0], width)
    assert tool.LOAD_VECTOR_PROBE_SQL + ";" in text


def test_an_explicitly_given_width_is_marked_as_not_production():
    """CLI 显式换档是允许的，但那一批必须自称"人为指定"，不许冒充生产口径。"""
    tool = _load("r393_probe_explicit")
    width = _production_width(tool)
    odd = width + 9
    _, _, text = _batch(tool, ef_search=odd)
    head = text.splitlines()[1]
    assert ("HNSW 候选宽度 = {0}；".format(odd)) in head, head
    assert "人为指定" in head, "越权换档没留名：" + head
    assert tool.TRUE_SOURCE not in head, head
    assert "'{0}'".format(odd) in _setting_lines(text)[0], _setting_lines(text)[0]


# -------------------------- 判据③：事务内、库探测在前、会话级 SET 封死

def test_the_width_lives_inside_one_transaction_only():
    """整批 BEGIN ... ROLLBACK；设定只活在笔内，跑完不残留在连接上。"""
    tool = _load("r393_probe_txn")
    _, _, text = _batch(tool)
    lines = text.splitlines()
    offset_begin = lines.index("BEGIN;")
    offset_probe = lines.index(tool.LOAD_VECTOR_PROBE_SQL + ";")
    offset_set = next(i for i, line in enumerate(lines) if "set_config(" in line)
    offset_rollback = max(i for i, line in enumerate(lines) if line == "ROLLBACK;")
    ranking = [i for i, line in enumerate(lines) if line.startswith("SELECT '")]
    assert offset_begin < offset_probe < offset_set < min(ranking) < max(ranking) \
        < offset_rollback, (offset_begin, offset_probe, offset_set, min(ranking),
                            max(ranking), offset_rollback)
    assert "TRUE" in lines[offset_set], "设定不是事务内那一版：" + lines[offset_set]


def test_the_library_probe_comes_first_because_a_placeholder_setting_is_void():
    """库探测排在设定之前：没加载时那条设定只会立一枚 pgvector 根本不读的占位参数（实测）。"""
    tool = _load("r393_probe_order")
    _, _, text = _batch(tool)
    lines = text.splitlines()
    assert lines.index(tool.LOAD_VECTOR_PROBE_SQL + ";") < next(
        i for i, line in enumerate(lines) if "set_config(" in line)
    doc = str(tool.emit_probe_queries.__doc__)
    assert ("占位" in doc) or ("探测" in doc), doc[:200]


def test_no_session_level_set_survives_in_the_generated_batch():
    """生成的 SQL 里不许再有会话级 SET hnsw：它会污染同一条连接后面的每一次读数。"""
    tool = _load("r393_probe_session_set")
    width = _production_width(tool)
    for extra in ({}, {"ef_search": width + 3}):
        _, _, text = _batch(tool, **extra)
        bad = [line for line in text.splitlines() if SESSION_SET.search(line)]
        assert not bad, repr(bad)
        assert "SET hnsw" not in text, text[:200]


def test_the_batch_is_read_only():
    """探针批零写入：它即使在生产库上跑也只读数 —— 批里不许混进任何 DDL/DML。"""
    tool = _load("r393_probe_readonly")
    _, _, text = _batch(tool)
    for token in ("INSERT", "UPDATE", "DELETE", "CREATE ", "DROP ", "ALTER ", "TRUNCATE",
                  "COPY ", "VACUUM", "REINDEX"):
        assert token not in text, "只读探针批里混进了 " + token


# ------------------------------ 形状与名字都来自真源：本件不许自己拼那一串

def test_the_setting_statement_is_derived_from_the_true_source(monkeypatch):
    """GUC 名与设定形状都取自真源模块：它哪天改口，批里跟着改，而不是继续拼旧的。"""
    tool = _load("r393_probe_derive")
    shifted = types.ModuleType("app.rag.pg_store")
    shifted.configured_hnsw_ef_search = lambda environ=None: 7
    shifted.HNSW_EF_SEARCH_GUC = "somebody.elses_guc"
    shifted._APPLY_HNSW_EF_SEARCH_SQL = "SELECT set_config(%s, %s, TRUE)"
    package = types.ModuleType("app.rag")
    package.pg_store = shifted
    monkeypatch.setitem(sys.modules, "app.rag", package)
    monkeypatch.setitem(sys.modules, "app.rag.pg_store", shifted)
    assert tool.render_apply_width_sql(7) == \
        "SELECT set_config('somebody.elses_guc', '7', TRUE)"


def test_the_script_itself_carries_no_guc_name_no_handwritten_statement_no_width():
    """脚本全文（含注释）里不许出现 GUC 名字、自己拼的设定语句、宽度语境行里的档位数字。"""
    text = (ROOT / TOOL).read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert not GUC_LITERAL.search(text), "GUC 名写死在脚本里，真源改口就没人听得到"
    assert "set_config('" not in text, "设定语句的形状不再来自真源，是本件自己拼的"
    for position, line in enumerate(text.splitlines(), start=1):
        if not WIDTH_CONTEXT.search(line) or "ef_construction" in line:
            continue
        for hit in BANNED_WIDTH_NUMBER.finditer(line):
            raise AssertionError("宽度语境行里出现了档位数字 {0} @ {1}: {2}".format(
                hit.group(0), position, line.strip()[:90]))


def test_the_probe_emitter_still_defaults_to_no_width_of_its_own():
    """签名缺省必须是"没给"：缺省带数字就等于又抄了一处。"""
    tool = _load("r393_probe_signature")
    parameters = inspect.signature(tool.emit_probe_queries).parameters
    assert parameters["ef_search"].default is None, repr(parameters["ef_search"].default)
    tree = ast.parse((ROOT / TOOL).read_bytes().decode("utf-8"))
    emitter = [node for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef) and node.name == "emit_probe_queries"]
    assert len(emitter) == 1
    assert [ast.unparse(item) for item in emitter[0].args.kw_defaults if item is not None] \
        == ["None"], "生成器的 ef_search 缺省不是 None"


# ------------------------ 批头变了，读数解析器必须还认得出一条条真读数

def test_the_parser_reads_a_real_psql_dump_with_command_tags_in_front(tmp_path):
    """回归钉：批头那三句会打脏 CSV 的第一行，按表头读会把每一条真读数都读没。"""
    tool = _load("r393_probe_csv")
    _, matrix = _material(tool, queries=3)
    width = _production_width(tool)
    dump = _psql_dump(matrix, width)
    assert dump.splitlines()[0] == "BEGIN", dump.splitlines()[:2]
    path = tmp_path / "probe.csv"
    path.write_text(dump, encoding="utf-8", newline="")
    buckets = tool.read_probe_csv_run(path, matrix)
    assert set(buckets) == {cell["principal"] for cell in matrix["cells"]}, sorted(buckets)
    for cell in matrix["cells"]:
        rows = buckets[cell["principal"]]
        assert set(rows) == {item["qid"] for item in cell["expected"]}, sorted(rows)
        for item in cell["expected"]:
            assert rows[item["qid"]] == item["exact_ids"], (
                item["qid"], rows[item["qid"]], item["exact_ids"])


def test_the_parser_admits_no_bucket_the_matrix_did_not_declare(tmp_path):
    """认行的唯一凭据是矩阵：别的 principal / qid 一律不许立桶（防幽灵读数）。"""
    tool = _load("r393_probe_csv_ghost")
    _, matrix = _material(tool, queries=2)
    width = _production_width(tool)
    declared = {cell["principal"]: {item["qid"] for item in cell["expected"]}
                for cell in matrix["cells"]}
    junk = io.StringIO()
    writer = csv.writer(junk, lineterminator="\n")
    writer.writerows([["who-is-this", "sbx-01", "fake-id", 9, ""],
                      [matrix["cells"][0]["principal"], "sbx-99", "fake-id-2", 9, ""],
                      DUMP_HEADER])
    path = tmp_path / "probe2.csv"
    path.write_text(junk.getvalue() + _psql_dump(matrix, width), encoding="utf-8",
                    newline="")
    buckets = tool.read_probe_csv_run(path, matrix)
    assert "who-is-this" not in buckets, repr(sorted(buckets))
    for principal, rows in buckets.items():
        assert set(rows) <= declared[principal], (principal, sorted(rows))


def test_an_unrecognisable_dump_is_a_loud_failure_not_an_empty_answer(tmp_path):
    """一条真读数都没认出来 = 前置不满足，当场报错；不许交回空桶被当成零命中。"""
    tool = _load("r393_probe_csv_empty")
    _, matrix = _material(tool, queries=2)
    path = tmp_path / "junk.csv"
    path.write_text("BEGIN\n?column?\nt\nset_config\n1\nROLLBACK\n", encoding="utf-8",
                    newline="")
    with pytest.raises(SystemExit) as caught:
        tool.read_probe_csv_run(path, matrix)
    assert "没认出来" in str(caught.value), str(caught.value)


def test_the_verify_command_refuses_a_blackout_dump(tmp_path, capsys):
    """整条 verify 路径：认不出行的读数文件 -> 前置不满足 + 点名，绝不判绿。"""
    tool = _load("r393_probe_verify")
    out = tmp_path / "plan"
    assert tool.main(["plan", "--out", str(out), "--chunks", "48", "--queries", "2"]) \
        == tool.EXIT_OK
    junk = tmp_path / "probe.csv"
    junk.write_text("BEGIN\n?column?\nt\nROLLBACK\n", encoding="utf-8", newline="")
    code = tool.main(["verify", "--matrix", str(out / "matrix.json"),
                      "--run", "pgvector=" + str(junk)])
    printed = capsys.readouterr().out
    assert code == tool.EXIT_PRECONDITION, (code, printed[-300:])
    assert "没认出来" in printed, printed[-300:]
    assert '"GREEN"' not in printed, printed[-300:]
