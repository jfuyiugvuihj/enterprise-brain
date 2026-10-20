# -*- coding: utf-8 -*-
"""R269 判据④：scripts/compare_vector_recall.py 的退出码归真。

现场实取（基点 af55756，git show HEAD:scripts/compare_vector_recall.py）：这个文件有九处
raise SystemExit("字符串") —— :100/:135/:148/:156/:166/:181/:185/:190/:376。Python 对字符串
参数一律给退出码 1，而 1 在本脚本里的既有语义是「跑成了，检出差异」（:445/:478）⇒ 九条
「根本没跑成」的路径，在照退出码分诊的自动化眼里全是「跑成了、有差异」。R264 交付时就被
这条撞车读反过一次（跟进单 §101.9 判据原文）。

本文件的钉子，按判据编号：
  ① 九处前置各自以整数 2 退出，且 stderr 首行带「[前置不满足]」——谁把某一格换回
    SystemExit(字符串)，那格的 code 立刻变成字符串，断言当场红。
  ② 反证钉：目录真实、集合名就是 enterprise_docs、count()=0 的空库 ⇒ rc 必须 ≠ 1，首行进
    stderr，不产出结论文件，且不许把真因（0 枚样本）说成「两边排序天然不同」。
  ③ 语义没被改宽：「检出差异」仍然且只仍然发 1；「无差异」仍然发 0。
  ④ 量具自己抛的异常按前置不满足记账，不再冒领 1；而前置码不许被兜底洗掉。
  ⑤ 静态钉（AST）：不许再有 SystemExit(字符串)，两个出口函数里不许再写退出码字面量。
  ⑥ 真子进程复跑：进程实际退出码是 2，不只是异常对象长这样。

所有 Chroma 访问都打在 pytest 的 tmp_path 上，一个字节都不碰工作树的 chroma_db/。
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "compare_vector_recall.py"
PREFIX = "[前置不满足] "


def _load_script():
    spec = importlib.util.spec_from_file_location("compare_vector_recall_r269", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()


def _first(text: str) -> str:
    lines = text.splitlines()
    return lines[0] if lines else ""


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return []


class FakeConnection:
    """只按位置回答两条 SELECT；行形状用裸 tuple，走 _row() 的 tuple 分支。"""

    def __init__(self, scope_row=None, type_row=None):
        self.scope_row = scope_row
        self.type_row = type_row
        self.closed = False

    def execute(self, sql, params=None):
        return FakeResult(self.scope_row if "vector_scope" in sql else self.type_row)

    def close(self):
        self.closed = True


# ------------------------------------------------------------------ ① 九处前置
def test_site1_bad_table_name_is_integer_two():
    with pytest.raises(SystemExit) as caught:
        SCRIPT._safe_table("chunks; DROP TABLE x")
    code = caught.value.code
    assert isinstance(code, int) and not isinstance(code, str), repr(code)
    assert code == SCRIPT.EXIT_PRECONDITION == 2, repr(code)


def test_site2_non_postgres_url_is_two_from_the_front_door(capsys):
    """这一格单独看是个死路：parse_database_settings 自己先 raise ValueError
    （app/db/connection.py:45，"only PostgreSQL URLs are supported"），走不到
    connect_read_only 里那条前置。所以判据只能从 main() 那一层量：ValueError 落进兜底，
    仍然 2、仍然进 stderr 首行。兜底要是不在，这条路径就是退出码 1。
    """
    with pytest.raises(SystemExit) as caught:
        SCRIPT.main(["--database-url", "sqlite:///whatever.db"])
    assert caught.value.code == 2, repr(caught.value.code)
    err = capsys.readouterr().err
    assert _first(err).startswith(PREFIX), err
    assert "ValueError" in err, "判读要能看出是哪一类失败：" + err


def test_site3_unmigrated_scope_is_two(capsys):
    with pytest.raises(SystemExit) as caught:
        SCRIPT.read_scope(FakeConnection(), "chunk_vectors")
    assert caught.value.code == 2, repr(caught.value.code)
    assert "0010_pgvector_chunks.sql" in capsys.readouterr().err


def test_site4_wrong_column_type_is_two(capsys):
    connection = FakeConnection(scope_row=("nomic-embed-text", 768, "l2"), type_row=("real",))
    with pytest.raises(SystemExit) as caught:
        SCRIPT.read_scope(connection, "chunk_vectors")
    assert caught.value.code == 2, repr(caught.value.code)
    assert "实际类型" in capsys.readouterr().err


def test_site5_scope_drift_is_two(capsys, monkeypatch):
    connection = FakeConnection(scope_row=("nomic-embed-text", 768, "l2"),
                                type_row=("vector(768)",))
    monkeypatch.setattr(SCRIPT.pg_store, "scope_disagreements",
                        lambda configured, stored: ("embedding_model_drift",))
    with pytest.raises(SystemExit) as caught:
        SCRIPT.read_scope(connection, "chunk_vectors")
    assert caught.value.code == 2, repr(caught.value.code)
    assert "R22" in capsys.readouterr().err


def test_site6_missing_directory_is_two_and_creates_nothing(tmp_path, capsys):
    absent = tmp_path / "never-created"
    with pytest.raises(SystemExit) as caught:
        SCRIPT.open_chroma(str(absent), "enterprise_docs")
    assert caught.value.code == 2, repr(caught.value.code)
    assert "不要新建" in capsys.readouterr().err
    assert not absent.exists(), "前置失败的一刻也不许替业主把目录建出来"


def test_site7_chromadb_unavailable_is_two(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "chromadb", None)   # import chromadb ⇒ ImportError
    with pytest.raises(SystemExit) as caught:
        SCRIPT.open_chroma(str(tmp_path), "enterprise_docs")
    assert caught.value.code == 2, repr(caught.value.code)
    assert "chromadb 不可用" in capsys.readouterr().err


def test_site8_real_dir_without_the_collection_is_two(tmp_path, capsys):
    import chromadb

    chromadb.PersistentClient(path=str(tmp_path)).get_or_create_collection(
        name="enterprise_docs")
    with pytest.raises(SystemExit) as caught:
        SCRIPT.open_chroma(str(tmp_path), "enterprise_brain")
    assert caught.value.code == 2, repr(caught.value.code)
    err = capsys.readouterr().err
    assert _first(err).startswith(PREFIX), err
    assert "目录真实也不等于集合在里面" in err, "空目录与集合不存在必须是两句话"


def test_site9_missing_question_set_is_two(capsys):
    with pytest.raises(SystemExit) as caught:
        SCRIPT.load_questions(["tests/fixtures/nope.jsonl"])
    assert caught.value.code == 2, repr(caught.value.code)
    assert _first(capsys.readouterr().err).startswith(PREFIX)


# --------------------------------------------------------- ② 反证钉：真·空库
SCOPE_COSINE = {"embedding_model": "nomic-embed-text", "dimension": 768,
                "distance_function": "cosine", "column_type": "vector(768)"}


def test_empty_library_is_precondition_not_difference(tmp_path, capsys, monkeypatch):
    """判据④点名的那一枚反证钉：目录真实、集合名对、count()=0。

    旧实现把这一格报成「两边排序天然不同」，真因却是「库里 0 枚样本可测」——码虽然碰巧
    是 2，文案却把业主支去改一个没写错的 0010。现在两件事都对：退出码 2、首行进 stderr、
    不产出结论文件、不再出现那句假话。
    """
    import chromadb

    client = chromadb.PersistentClient(path=str(tmp_path))
    collection = client.get_or_create_collection(name="enterprise_docs")
    assert collection.count() == 0, "反证钉的前提就是这枚空库"
    out = tmp_path / "verdict.json"
    monkeypatch.setattr(SCRIPT, "connect_read_only", lambda url: FakeConnection())
    monkeypatch.setattr(SCRIPT, "read_scope", lambda connection, table: dict(SCOPE_COSINE))
    code = SCRIPT.main(["--chroma-dir", str(tmp_path), "--collection", "enterprise_docs",
                       "--skip-questions", "--out", str(out)])
    captured = capsys.readouterr()
    assert code != 1, "空库冒领「检出差异」⇒ 判据④当场不达标（rc=%r）" % code
    assert code == 2, repr(code)
    assert _first(captured.err).startswith(PREFIX), captured.err
    assert "U1 判读" in captured.out, "人读那一份仍要留在 stdout（R157 契约）"
    assert "样本只有 0 枚" in captured.out, captured.out
    assert "先核对 0010" not in captured.out, "把 0 枚样本说成排序不同就是假话：" + captured.out
    assert not out.exists(), "前置不满足时不许产出结论文件"


# ------------------------------------------------- ③ 差异仍然 1、无差异仍然 0
DRIFT_CLEAN = {"pg_vectors": 12, "chroma_vectors": 12, "chunks_rows": 12,
               "chunks_with_backfilled_embedding": 0, "index_version_id_null": 0,
               "all_zero_rows": 0, "only_in_pg": [], "only_in_chroma": [], "wrong_width": []}
DRIFT_GAP = dict(DRIFT_CLEAN, only_in_chroma=["a_0"])
U1_RECORDED = {"source": "metadata", "recorded": "cosine", "sampled": 0, "probes": 0,
               "returned": 0, "matched": ["cosine"], "reason": ""}


def _run_corpus(tmp_path, monkeypatch, drift, distance="cosine"):
    out = tmp_path / "verdict.json"
    monkeypatch.setattr(SCRIPT, "connect_read_only", lambda url: FakeConnection())
    monkeypatch.setattr(SCRIPT, "read_scope", lambda connection, table: dict(
        SCOPE_COSINE, distance_function=distance))
    monkeypatch.setattr(SCRIPT, "open_chroma", lambda directory, name: object())
    monkeypatch.setattr(SCRIPT, "resolve_chroma_distance",
                        lambda collection: (distance, dict(U1_RECORDED)))
    monkeypatch.setattr(SCRIPT, "corpus_drift", lambda *a, **kw: dict(drift))
    code = SCRIPT.main(["--chroma-dir", str(tmp_path), "--skip-questions",
                       "--out", str(out)])
    return code, out


def test_detected_difference_still_exits_one(tmp_path, monkeypatch, capsys):
    code, out = _run_corpus(tmp_path, monkeypatch, DRIFT_GAP)
    captured = capsys.readouterr()
    assert code == SCRIPT.EXIT_DIFFERENCE == 1, repr(code)
    assert not _first(captured.err).startswith(PREFIX), "跑成了的结论不占 stderr 首行"
    assert out.exists()


def test_clean_run_still_exits_zero(tmp_path, monkeypatch, capsys):
    code, out = _run_corpus(tmp_path, monkeypatch, DRIFT_CLEAN)
    captured = capsys.readouterr()
    assert code == SCRIPT.EXIT_NO_DIFFERENCE == 0, repr(code)
    assert captured.err == "", captured.err
    assert out.exists()


# ---------------------------------------------------- ④ 量具自己的异常 ⇒ 2
def test_tool_own_exception_is_not_reported_as_difference(monkeypatch, capsys):
    """目录被别的进程写坏 / chromadb 内部错：过去以 1 混进「有差异」，现在按前置记账。"""

    def broken(argv=None):
        raise RuntimeError("段文件读不动（模拟）")

    monkeypatch.setattr(SCRIPT, "_compare", broken)
    with pytest.raises(SystemExit) as caught:   # 兜底不 return，它以前置码退出
        SCRIPT.main([])
    assert caught.value.code == 2, repr(caught.value.code)
    err = capsys.readouterr().err
    assert _first(err).startswith(PREFIX), err
    assert "RuntimeError" in err and "没有产出任何召回结论" in err, err


def test_precondition_code_is_not_washed_by_the_backstop(monkeypatch):
    """main() 的兜底是 except Exception，而 SystemExit 不是 Exception 的后代。"""
    monkeypatch.setattr(SCRIPT, "_compare",
                        lambda argv=None: SCRIPT.fail_precondition("兜底不许洗掉前置码"))
    with pytest.raises(SystemExit) as caught:
        SCRIPT.main([])
    assert caught.value.code == 2, repr(caught.value.code)


# ------------------------------------------------------------ ⑤ 静态钉（防回潮）
def test_no_string_systemexit_left_anywhere():
    """AST 走一遍：Raise 里带 SystemExit(字符串) 就红（字符串 ⇒ 退出码 1，与「有差异」撞车）。

    用 AST 而不是正则：本文件 docstring 里必须把那个历史形状写清楚，正则会把讲解文字一起
    抓进来，把钉子读成假红。
    """
    import ast

    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        if getattr(node.exc.func, "id", None) != "SystemExit":
            continue
        for argument in node.exc.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                offenders.append((node.lineno, argument.value[:24]))
    assert not offenders, (
        "又有人写 SystemExit(字符串)：Python 给退出码 1，与「检出差异」撞车；"
        "前置不满足一律走 fail_precondition()。命中 " + repr(offenders))


def test_exit_numbers_only_come_from_the_constants():
    """只管两个出口函数：main()/_compare() 里的 return 字面量都是退出码，必须走 EXIT_* 常量。

    全文件扫 return 0 会把 _scalar() 那种「读不到就是 0 枚」抓进来，那是计数不是退出码。
    """
    import ast

    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in {"main", "_compare"}:
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Return) or not isinstance(inner.value, ast.Constant):
                continue
            if isinstance(inner.value.value, int):
                offenders.append((inner.lineno, inner.value.value))
    assert not offenders, "退出码不许再写字面量，只许用 EXIT_* 常量：命中 " + repr(offenders)


# -------------------------------------------------------- ⑥ 真子进程的退出码
def test_real_process_exit_code_is_two_for_a_non_postgres_url():
    """进程实际退出码：raise SystemExit(main()) 那一层没把 2 洗成 1。"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--database-url", "sqlite:///x.db"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=180)
    assert proc.returncode == 2, (proc.returncode, proc.stdout[-300:], proc.stderr[-300:])
    assert _first(proc.stderr).startswith(PREFIX), proc.stderr[:300]


def test_the_r157_stdout_contract_survives_the_stderr_move(capsys, monkeypatch):
    """判读全文搬去 stderr 就会红：人读那一份钉在 stdout（R157），机读首行钉在 stderr。"""
    monkeypatch.setattr(SCRIPT, "connect_read_only", lambda url: FakeConnection())
    monkeypatch.setattr(SCRIPT, "read_scope", lambda connection, table: dict(SCOPE_COSINE))
    monkeypatch.setattr(SCRIPT, "open_chroma", lambda directory, name: object())
    monkeypatch.setattr(SCRIPT, "resolve_chroma_distance", lambda collection: ("", {
        "source": "measured", "recorded": "", "sampled": 0, "probes": 0, "returned": 0,
        "matched": [], "reason": "样本只有 0 枚，少于 12"}))
    assert SCRIPT.main(["--chroma-dir", ".", "--skip-questions"]) == 2
    captured = capsys.readouterr()
    assert "U1 判读" in captured.out, captured.out
    assert PREFIX.strip() in captured.out, captured.out
    assert _first(captured.err).startswith(PREFIX), captured.err

