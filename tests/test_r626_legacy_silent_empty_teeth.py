# -*- coding: utf-8 -*-
"""R626 判据①~⑥ —— 遗留引擎的静默空召回必须被读成静默空召回，而且必须摘不掉。

这单买的不是"多一枚脚本"，是**这句话以后每班都能现跑现证**：1008 枚存量之上问 5 名，
遗留引擎对 21 枚题交回空列表，PGVector 对同 21 枚交回满 5 名。零报错、零异常，所以引擎
不会自己开口——只有判据会红它才开口。于是本文件只管三形，一形都不许含糊：

1. **空列表＝红**：库容 >= k 而某腿交回空表 ⇒ 判 EMPTY、退出码 1，并把题号点名（① ②）。
2. **两腿全等＝绿**：名次逐位相等 ⇒ mean overlap 1.0、重合率任意高都不红（③）。
3. **反证刀＝当场红**：把判空那一格的任一半摘掉，钉必须立刻失守（④⑤）。摘的是
   `is_silent_empty()` 里那两枚承重条件——摘掉 `returned == 0` 就什么都算空，
   摘掉 `leg_size >= k` 就把"库里没东西"洗成"引擎坏了"；两种都是这单最怕的假话，
   所以两半各下一把刀。刀一律做在 tmp 的源码副本上，真树一个字节都不写。

另外三格是这枚量具自己的安全带，不是装饰：腿抛异常按"没跑成"（码 2）出口而不是替 21 枚
真症状打掩护（⑥）；库容不足 k 的空返回单列一格、不许混进 EMPTY（②反向）；重合率阈值走
参数、今天的读数 0.7238 一枚都不许烤进码（⑦）。

零变异与不平行实现的静态账（⑧⑨）：本量具不许自己开 PersistentClient、不许自己裸 connect
（在册棘轮 test_r238 全仓 15 枚与 test_r134 开库收口名册都因新落点而红，这枚件先拦住自己），
不许有会落进工作树的缺省卷路径，`app/**` 也不许出现对它的引用——退役量具一旦被产品码
import，"遗留件"就又多了一枚活着的依赖。

全程离线：不连 PostgreSQL、不开任何真实卷（仓内 `chroma_db` 一个字节都不碰）、不打模型、
不起服务。假腿由用例注入，真腿（`ChromaLeg`／`PgLeg`）在本件里只按形状检查，不调用。
唯一一处真起进程是那枚命令行出口钉：子进程只做参数校验就在连库之前按前置码 2 退，
所以它同样零连库、零开卷、零模型——它钉的是"装配顺序"，不是引擎。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib
import subprocess
import sys
from types import SimpleNamespace

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO / "scripts" / "r626_legacy_engine_silent_empty_probe.py"
SIBLING_PATH = REPO / "scripts" / "compare_vector_recall.py"
PREFIX = "[前置不满足] "
K = 5
#: 与现场同量级的库容：判空格的分母。用 1008 不是把它当常数，而是让"库容 >= k"这一半
#: 在用例里就是真的（3 枚的库容只能测稀缺那一格，测不出静默空）。
CORPUS = 1008


def _load(path: pathlib.Path, name: str):
    """装载一枚 scripts/ 下的量具；顺手把它插进 sys.path 的落点收回原样。

    副本的 ROOT 指向 tmp，装载它就等于把 tmp 塞进全会话的导入路径——刀只许改判据，
    不许顺带改变后面每一枚用例的 import 搜索顺序。
    """
    before = list(sys.path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for extra in [item for item in sys.path if item not in before]:
        sys.path.remove(extra)
    return module


SCRIPT = _load(SCRIPT_PATH, "r626_legacy_engine_silent_empty_probe")


# ------------------------------------------------------------------ 假腿与装配台


class FakeLeg:
    """一枚只按标记交答案的腿：`answers` 以向量首元素为键，`raises` 让它抛。

    🔴 它不模拟"引擎坏了"，它**就是**坏掉的那条腿的读数：交回空列表，不抛任何东西。
    """

    def __init__(self, name: str, *, size: int, answers: dict, raises: Exception = None):
        self.name = name
        self._size = int(size)
        self.answers = dict(answers)
        self.raises = raises
        self.calls: list = []

    def size(self) -> int:
        return self._size

    def search(self, vector, k: int) -> list:
        marker = float(vector[0])
        self.calls.append((marker, int(k)))
        if self.raises is not None:
            raise self.raises
        return list(self.answers.get(marker, []))


def assemble(cases, *, chroma_size: int = CORPUS, pg_size: int = CORPUS,
             chroma_raises: Exception = None, pg_raises: Exception = None,
             module=SCRIPT):
    """把 (题号, 题面, chroma 名次, pg 名次) 装配成一次 run_probe 调用。

    题号写成现场那一族（doc-09 / metric-04 / scope-01 …），是为了让"打印的是哪几题"
    这一格能被读出来，而不是只能被数出来。
    """
    questions = [(source, qid, question) for source, qid, question, _c, _p in cases]
    chroma_answers = {}
    pg_answers = {}
    for index, (_source, _qid, question, chroma_ids, pg_ids) in enumerate(cases):
        chroma_answers[float(index + 1)] = list(chroma_ids)
        pg_answers[float(index + 1)] = list(pg_ids)

    def embed(question):
        for index, (_source, _qid, text, _c, _p) in enumerate(cases):
            if text == question:
                return [float(index + 1)]
        raise AssertionError("题面没在夹具里：" + question)

    chroma = FakeLeg("chroma", size=chroma_size, answers=chroma_answers, raises=chroma_raises)
    pg = FakeLeg("pg", size=pg_size, answers=pg_answers, raises=pg_raises)
    result = module.run_probe(questions, embed=embed, chroma=chroma, pg=pg, k=K)
    return result, chroma, pg


def full_ids(prefix_text: str, count: int = K) -> list:
    return ["%s_c%d" % (prefix_text, position) for position in range(count)]


# ------------------------------------------------------ ① 空列表＝红，且要报出题号
def test_empty_leg_with_corpus_present_is_flagged_and_exits_one():
    """库容 1008 之上问 5 名，chroma 腿对 doc-09 交回空表 ⇒ EMPTY、码 1、题号点名。"""
    cases = [("f.jsonl", "doc-09", "第一季度营收", [], full_ids("doc-09")),
             ("f.jsonl", "metric-04", "利润率口径", full_ids("metric-04"), full_ids("metric-04")),
             ("f.jsonl", "scope-01", "权限范围", full_ids("scope-01"), full_ids("scope-01"))]
    result, _chroma, _pg = assemble(cases)
    row = {item["id"]: item for item in result["questions"]}["doc-09"]

    assert row["empty_flag"] is True, row
    assert row["empty_legs"] == ["chroma"], row
    assert row["chroma_ids"] == [] and row["pg_ids"] == full_ids("doc-09"), row
    assert row["overlap_at_k"] == 0.0, row
    summary = result["summary"]
    assert summary["empty_chroma_count"] == 1, summary
    assert summary["empty_pg_count"] == 0, summary
    assert summary["empty_chroma_ids"] == ["doc-09"], summary
    assert summary["mean_overlap_at_k"] == round(2 / 3, 6), summary
    code, reasons = SCRIPT.classify(summary, min_mean_overlap=0.0)
    assert code == SCRIPT.EXIT_SILENT_EMPTY == 1, (code, reasons)
    assert "1 题" in "".join(reasons), reasons


def test_the_human_output_names_which_questions_came_back_empty():
    """判据只报枚数不点名，第二天就得有人再手算一遍——点名是交付的一部分。"""
    cases = [("f.jsonl", "report-12", "年度报告", [], full_ids("report-12")),
             ("f.jsonl", "tool-01", "工具清单", [], full_ids("tool-01"))]
    result, _chroma, _pg = assemble(cases)
    text = SCRIPT.render_human(result)

    counts = {line.split()[0]: line.split()[1] for line in text.splitlines()
              if line.startswith(("empty_", "thin_", "error_"))}
    assert counts["empty_chroma_count"] == "2", text
    assert counts["empty_pg_count"] == "0", text
    assert "report-12" in text and "tool-01" in text, text
    assert "静默空召回" in text, text


def test_both_legs_empty_is_still_one_red_not_two_halves():
    cases = [("f.jsonl", "insight-02", "洞察", [], [])]
    result, _chroma, _pg = assemble(cases)
    code, reasons = SCRIPT.classify(result["summary"], min_mean_overlap=0.0)

    assert code == SCRIPT.EXIT_SILENT_EMPTY, reasons
    assert result["summary"]["empty_chroma_count"] == 1 == result["summary"]["empty_pg_count"]
    assert result["questions"][0]["empty_legs"] == ["chroma", "pg"]


# ---------------------------------------------------------------- ② 稀缺不是坏了
def test_scarcity_is_not_read_as_silent_empty():
    """库容 3 < k=5 时空返回是"没东西可给"，单列 thin 一格，不许领 EMPTY 的码。"""
    cases = [("f.jsonl", "doc-99", "题面", [], full_ids("doc-99"))]
    result, _chroma, _pg = assemble(cases, chroma_size=3)
    summary = result["summary"]
    code, reasons = SCRIPT.classify(summary, min_mean_overlap=0.0)

    assert summary["empty_chroma_count"] == 0, summary
    assert summary["thin_corpus_empty_count"] == 1, summary
    assert result["questions"][0]["empty_flag"] is False, result["questions"][0]
    assert code == SCRIPT.EXIT_CLEAN, reasons


# -------------------------------------------------------------------- ③ 全等＝绿
def test_identical_legs_are_clean_at_any_threshold():
    cases = [("f.jsonl", "approval-06", "审批", full_ids("a"), full_ids("a")),
             ("f.jsonl", "chart-04", "图表", full_ids("b"), full_ids("b"))]
    result, _chroma, _pg = assemble(cases)
    summary = result["summary"]

    assert summary["mean_overlap_at_k"] == 1.0, summary
    assert summary["exact_leg_agreement"]["count"] == 2, summary
    assert summary["exact_leg_agreement"]["ratio"] == 1.0, summary
    assert summary["empty_chroma_count"] == 0 == summary["empty_pg_count"], summary
    for threshold in (0.0, 0.9, 1.0):
        assert SCRIPT.classify(summary, min_mean_overlap=threshold)[0] == SCRIPT.EXIT_CLEAN


def test_order_makes_difference_and_is_reported_separately_from_overlap():
    """同一组名次换序：overlap@k 仍是 1.0，但 exact_leg_agreement 必须掉——两把尺分账。"""
    ids = full_ids("x")
    cases = [("f.jsonl", "data-08", "数据源", ids, list(reversed(ids)))]
    result, _chroma, _pg = assemble(cases)
    summary = result["summary"]

    assert summary["mean_overlap_at_k"] == 1.0, summary
    assert summary["exact_leg_agreement"]["count"] == 0, summary
    assert result["questions"][0]["exact_order_match"] is False


def test_overlap_definition_is_intersection_over_k_not_union():
    """口径钉：交集 ÷ k。并集那把尺同时以 jaccard 列交回，两枚都不许被对方替换。"""
    chroma_ids = ["a", "b", "c", "d", "e"]
    pg_ids = ["a", "b", "c", "x", "y"]
    cases = [("f.jsonl", "metric-10", "指标", chroma_ids, pg_ids)]
    result, _chroma, _pg = assemble(cases)
    row = result["questions"][0]

    assert row["overlap_at_k"] == 0.6, row
    assert row["jaccard"] == round(3 / 7, 6), row
    assert SCRIPT.overlap_at_k(chroma_ids, pg_ids, K) == 0.6


# ------------------------------------------------------------------ ⑦ 阈值是参数
def test_threshold_is_a_parameter_and_todays_reading_is_not_baked_in():
    """低到 0.7 的阈值必须把 0.6 判红（码 3），而缺省 0.0 只判静默空——阈值不烤死。"""
    chroma_ids = ["a", "b", "c", "d", "e"]
    cases = [("f.jsonl", "metric-11", "指标", chroma_ids, ["a", "b", "c", "x", "y"]),
             ("f.jsonl", "metric-13", "指标", chroma_ids, ["a", "b", "c", "x", "y"])]
    result, _chroma, _pg = assemble(cases)
    summary = result["summary"]

    assert summary["mean_overlap_at_k"] == 0.6, summary
    assert SCRIPT.classify(summary, min_mean_overlap=0.7)[0] == SCRIPT.EXIT_LOW_OVERLAP
    assert SCRIPT.classify(summary, min_mean_overlap=0.0)[0] == SCRIPT.EXIT_CLEAN
    assert SCRIPT.classify(summary, min_mean_overlap=0.6)[0] == SCRIPT.EXIT_CLEAN
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for baked in ("0.7238", "0.72", "0.9378"):
        assert baked not in source.split('"""', 2)[2], baked


# ---------------------------------------------------------------- ④⑤ 反证刀
#: `is_silent_empty()` 的函数体那一行，两把刀各自摘掉一半承重条件。
EMPTY_CLAUSE = "    return int(returned) == 0 and int(leg_size) >= int(k)"


def _mutated_module(tmp_path: pathlib.Path, *, replacement: str, marker: str):
    """把源码副本做进 tmp 的 scripts/ 之下再装载；真树一个字节都不写。

    落点保持 `<tmp>/scripts/x.py` 这层形状，副本里的 ROOT 才仍然指向"仓根上一层"，
    不会误指到真仓——刀只许碰判据，不许顺手把路径判断也改了。
    """
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert source.count(EMPTY_CLAUSE) == 1, "判空格形状变了，刀要先重新磨"
    mutated = source.replace(EMPTY_CLAUSE, replacement, 1)
    assert mutated != source, marker
    target = tmp_path / "scripts" / ("mutated_" + marker + ".py")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(mutated, encoding="utf-8", newline="\n")
    return _load(target, "r626_mutated_" + marker), source


def _assert_empty_leg_is_red(module, cases) -> None:
    """把 ① 那枚钉的断言本体抽出来，好在"真源"与"摘了格的副本"上各跑一遍同一句话。"""
    result, _chroma, _pg = assemble(cases, module=module)
    summary = result["summary"]
    assert summary["empty_chroma_count"] == 1, summary
    assert module.classify(summary, min_mean_overlap=0.0)[0] == module.EXIT_SILENT_EMPTY


def _assert_scarcity_is_not_red(module, cases) -> None:
    """② 那枚钉的断言本体：库容不足 k 的空返回不许领 EMPTY 的码。"""
    result, _chroma, _pg = assemble(cases, chroma_size=3, module=module)
    assert result["summary"]["empty_chroma_count"] == 0, result["summary"]
    assert module.classify(result["summary"], min_mean_overlap=0.0)[0] == module.EXIT_CLEAN


CASES_WITH_ONE_EMPTY = [("f.jsonl", "doc-13", "员工年假", [], full_ids("doc-13")),
                        ("f.jsonl", "doc-18", "调休规定", full_ids("doc-18"), full_ids("doc-18"))]


def test_the_pin_holds_on_the_real_source():
    """正向对照先站住：同一份夹具在真源上是红的（码 1）。"""
    _assert_empty_leg_is_red(SCRIPT, CASES_WITH_ONE_EMPTY)


def test_knife_removing_the_empty_check_launders_the_symptom(tmp_path):
    """刀一：把判空那一格整个摘掉 ⇒ 21 枚空列表被折成"零差异"，① 那枚钉当场失守。"""
    mutated, _source = _mutated_module(tmp_path, replacement="    return False",
                                       marker="drop_empty_check")

    result, _chroma, _pg = assemble(CASES_WITH_ONE_EMPTY, module=mutated)
    assert result["summary"]["empty_chroma_count"] == 0, result["summary"]
    assert mutated.classify(result["summary"], min_mean_overlap=0.0)[0] == mutated.EXIT_CLEAN
    with pytest.raises(AssertionError):
        _assert_empty_leg_is_red(mutated, CASES_WITH_ONE_EMPTY)


def test_knife_dropping_the_size_floor_blends_scarcity_into_red(tmp_path):
    """刀二：只摘 `leg_size >= k` ⇒ 库容不足 k 的正常空也判坏了，② 那枚钉当场失守。"""
    mutated, _source = _mutated_module(
        tmp_path, replacement="    return int(returned) == 0", marker="drop_size_floor")
    scarcity = [("f.jsonl", "doc-99", "题面", [], full_ids("doc-99"))]

    result, _chroma, _pg = assemble(scarcity, chroma_size=3, module=mutated)
    assert result["summary"]["empty_chroma_count"] == 1, result["summary"]
    assert mutated.classify(result["summary"], min_mean_overlap=0.0)[0] \
        == mutated.EXIT_SILENT_EMPTY
    with pytest.raises(AssertionError):
        _assert_scarcity_is_not_red(mutated, scarcity)
    _assert_scarcity_is_not_red(SCRIPT, scarcity)


# -------------------------------------------------------------------- ⑥ 崩溃分账
def test_a_raising_leg_is_a_precondition_not_a_silent_empty(tmp_path, capsys):
    """腿抛异常时不许领 1 号：那会把"引擎坏了"与"量具坏了"读成同一件事。"""
    cases = [("f.jsonl", "scope-03", "范围", [], full_ids("scope-03"))]
    result, _chroma, _pg = assemble(cases, chroma_raises=RuntimeError("index boom"))

    assert result["summary"]["error_count"] == 1, result["summary"]
    assert result["questions"][0]["error"], result["questions"][0]
    assert result["questions"][0]["empty_flag"] is False, "崩溃被读成了空召回"
    tool = SCRIPT.load_recall_tool()
    with pytest.raises(SystemExit) as caught:
        SCRIPT.require_no_leg_errors(tool, result)
    assert caught.value.code == SCRIPT.EXIT_PRECONDITION == 2, caught.value.code
    assert PREFIX in capsys.readouterr().err, "没跑成必须进 stderr 首行"


# ------------------------------------------------------------ ⑧ 两份产物都要在
def test_machine_and_human_artifacts_carry_every_named_column(tmp_path):
    """机读列名与汇总字段名就是交回口径：少一枚等于这单没交。"""
    cases = [("f.jsonl", "doc-09", "第一季度营收", [], full_ids("doc-09")),
             ("f.jsonl", "metric-04", "利润率", full_ids("metric-04"), ["metric-04_c0"])]
    result, _chroma, _pg = assemble(cases)
    code, reasons = SCRIPT.classify(result["summary"], min_mean_overlap=0.0)
    json_path = tmp_path / "r626.json"
    md_path = tmp_path / "r626.md"
    SCRIPT.write_outputs(result, json_path=json_path, md_path=md_path, code=code,
                         reasons=reasons)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    required_row = {"id", "question", "chroma_ids", "pg_ids", "empty_flag", "overlap_at_k"}
    for row in payload["questions"]:
        assert required_row <= set(row), sorted(required_row - set(row))
    for key in ("empty_chroma_count", "empty_pg_count", "mean_overlap_at_k",
                "exact_leg_agreement"):
        assert key in payload["summary"], key
    assert payload["verdict"]["exit_code"] == 1, payload["verdict"]

    table = md_path.read_text(encoding="utf-8")
    assert "| id | question | chroma_ids | pg_ids | empty_flag | overlap_at_k |" in table
    assert "doc-09" in table and "（空）" in table, table
    assert "empty_chroma_count | 1" in table, table


# ---------------------------------------------------------- ⑨ 零变异：只读副本
def test_snapshot_copies_and_the_source_stays_the_same_bytes(tmp_path):
    """快照出来的是另一枚目录，且源目录内容与副本内容逐字节同一份。"""
    source = tmp_path / "volume"
    source.mkdir()
    (source / "chroma.sqlite3").write_text("记录平面", encoding="utf-8")
    nested = source / "d" / "index"
    nested.mkdir(parents=True)
    (nested / "data_level0.bin").write_bytes(b"\x00\x01\x02")

    stage = tmp_path / "stage"
    copy = SCRIPT.snapshot_volume(source, stage)
    before = SCRIPT.volume_inventory(source)
    after_copy = SCRIPT.volume_inventory(copy)

    assert copy != source.resolve(), "读的就是原件，零变异这句话不成立"
    assert str(copy).startswith(str(stage.resolve())), copy
    assert before == SCRIPT.volume_inventory(source), "做完快照源目录自己变了"
    assert after_copy["digest"] == before["digest"], (before, after_copy)
    assert after_copy["files"] == 2, after_copy

    (copy / "chroma.sqlite3").write_text("副本被写过", encoding="utf-8")
    assert SCRIPT.inventories_match(before, SCRIPT.volume_inventory(source)), \
        "源目录的清单被副本的写动到了，这枚量具有鬼"


def test_the_live_volume_may_be_copied_but_is_never_opened(tmp_path):
    """两件事必须分开：复制源**可以**是现役卷（复制只是读），打开目标绝不可以是它。

    第一版把这条写成"现役卷一律拒"，结果当场废掉派工词要求的那条配方
    （`--snapshot-from /app/chroma_db` 在容器里就是 ROOT/chroma_db，被自己拒了）。
    这枚钉把那一次误判钉在码上：复制与打开是两个动作，只禁后者。
    """
    live = REPO / "chroma_db"
    assert SCRIPT.is_live_volume(live) is True, "认不出仓根/容器那枚卷，零变异就是空话"
    assert SCRIPT.is_live_volume(live / "d" / "index") is True
    assert SCRIPT.is_live_volume(tmp_path / "chroma_db") is False
    assert SCRIPT.is_live_volume(tmp_path / "snapshot-of-chroma") is False

    seen = []

    def copier(src, dst):
        seen.append((pathlib.Path(str(src)), pathlib.Path(str(dst))))
        pathlib.Path(str(dst)).mkdir(parents=True)

    copy = SCRIPT.snapshot_volume(live, tmp_path, copier=copier)

    assert seen == [(live.resolve(), pathlib.Path(str(copy)))], seen
    assert pathlib.Path(str(copy)) != live.resolve(), "读的就是原件，零变异这句话不成立"
    assert str(copy).startswith(str(tmp_path.resolve())), copy
    assert SCRIPT.is_live_volume(pathlib.Path(str(copy))) is False, "副本仍指在现役卷上"


def test_the_opened_directory_is_refused_when_it_is_the_live_volume(tmp_path, capsys):
    """`--chroma-dir` 是"要打开的那一枚"：指到现役卷必须拒，且拒在动 staging 之前。"""
    live = REPO / "chroma_db"
    with pytest.raises(SystemExit) as caught:
        SCRIPT.chroma_dir_for_run(SimpleNamespace(snapshot_from=None, chroma_dir=str(live)),
                                  tmp_path)
    assert caught.value.code == SCRIPT.EXIT_PRECONDITION == 2, caught.value.code
    stderr = capsys.readouterr().err
    assert PREFIX in stderr, stderr
    assert "只许当 --snapshot-from 的复制源" in stderr, stderr
    assert list(tmp_path.iterdir()) == [], "拒开之前已经动了 staging，顺序不成立"


def test_a_snapshot_may_not_land_inside_its_own_source(tmp_path):
    """副本不许抄进源目录里：那会把自己卷进下一遍 rglob，也会把"零变异"变成自写。"""
    src = tmp_path / "volume"
    src.mkdir()
    with pytest.raises(SystemExit) as caught:
        SCRIPT.snapshot_volume(src, src / "inner")
    assert caught.value.code == SCRIPT.EXIT_PRECONDITION
    assert not (src / "inner").exists(), "拒之前已经 mkdir 了落点"


def test_the_command_line_refuses_a_default_volume_without_a_database():
    """真子进程：卷参数缺失时以 2 号收，前缀进 stderr，stdout 不出结论。

    证明装配顺序（卷参数排在连库之前）在命令行上成立——一台没起 PostgreSQL 的机器
    也必须问得出这一格，否则"拒开现役卷"只在有库的日子成立。
    """
    proc = subprocess.run([sys.executable, str(SCRIPT_PATH)], capture_output=True,
                          text=True, encoding="utf-8", cwd=str(REPO), timeout=300)
    assert proc.returncode == SCRIPT.EXIT_PRECONDITION, (proc.returncode, proc.stderr[-300:])
    assert proc.stderr.startswith(PREFIX), proc.stderr[:200]
    assert "打开默认卷" in proc.stderr, proc.stderr[:200]
    assert proc.stdout.strip() == "", proc.stdout[:200]


def test_there_is_no_default_volume_to_fall_into(tmp_path):
    """两把口子必须显式给一枚；缺省值一律是 None，不许有会按 cwd 落进工作树的默认卷。"""
    args = SCRIPT.parse_args([])
    assert args.chroma_dir is None and args.snapshot_from is None, vars(args)
    assert args.min_mean_overlap == 0.0, args.min_mean_overlap
    assert args.k == K, args.k
    with pytest.raises(SystemExit) as caught:
        SCRIPT.chroma_dir_for_run(SimpleNamespace(snapshot_from=None, chroma_dir=None),
                                  tmp_path)
    assert caught.value.code == SCRIPT.EXIT_PRECONDITION
    with pytest.raises(SystemExit) as both:
        SCRIPT.chroma_dir_for_run(SimpleNamespace(snapshot_from=str(tmp_path / "a"),
                                                  chroma_dir=str(tmp_path / "b")), tmp_path)
    assert both.value.code == SCRIPT.EXIT_PRECONDITION


# ------------------------------------------------------- ⑩ 不平行实现·不收口变长
def _call_names(source: str) -> set:
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                found.add(func.attr)
            elif isinstance(func, ast.Name):
                found.add(func.id)
    return found


def _imported_roots(source: str) -> set:
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(item.name.split(".")[0] for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_the_gauge_opens_no_store_and_connects_nothing_itself():
    """退役量具不新增收口：一枚 PersistentClient、一处裸 connect、一条 SQL 都不许多出来。

    在册两枚棘轮的账都是"枚数全等"：test_r238 钉 app 14 + scripts 1 的裸 connect，
    test_r134 钉开库收口名册。本量具靠复用 compare_vector_recall 才不动它们——
    这条钉是"别以后有人在这文件里图省事直接开库"的护栏，不是自我表扬。
    """
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    called = _call_names(source)
    roots = _imported_roots(source)

    for forbidden in ("PersistentClient", "open_connection", "connect", "HttpClient"):
        assert forbidden not in called, forbidden
    for forbidden in ("chromadb", "psycopg", "psycopg2"):
        assert forbidden not in roots, forbidden
    body = source.split('"""', 2)[2]
    for sql in ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "CREATE "):
        assert sql not in body.upper(), sql
    assert "connect_read_only" in source and "pg_recall" in source and "open_chroma" in source, \
        "复用点被摘掉了：那意味着有人在这里另起了一套平行实现"


def test_the_exit_codes_stay_homologous_with_the_registered_gauge():
    """2 号与"没跑成"前缀必须与在册量具同源；1 号语义不同，而且这件事写在码上。"""
    sibling = _load(SIBLING_PATH, "compare_vector_recall_for_r626")

    assert SCRIPT.EXIT_PRECONDITION == sibling.EXIT_PRECONDITION == 2
    assert SCRIPT.PRECONDITION_PREFIX == sibling.PRECONDITION_PREFIX == PREFIX
    assert SCRIPT.EXIT_CLEAN == sibling.EXIT_NO_DIFFERENCE == 0
    assert SCRIPT.EXIT_SILENT_EMPTY == sibling.EXIT_DIFFERENCE == 1
    assert SCRIPT.EXIT_LOW_OVERLAP == 3 and SCRIPT.EXIT_LOW_OVERLAP != sibling.EXIT_PRECONDITION
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "分诊表" in source, "两枚 1 号语义不同这件事必须留在码上"


def test_product_code_does_not_import_the_retirement_gauge():
    """文件头那句话要有牙：app/** 里出现本文件的引用＝遗留件多了一枚活依赖。"""
    needle = SCRIPT_PATH.name
    hits = [path.relative_to(REPO).as_posix()
            for path in (REPO / "app").rglob("*.py") if needle in path.read_text(encoding="utf-8")]
    assert hits == [], hits
    header = SCRIPT_PATH.read_text(encoding="utf-8").split('"""', 2)[1]
    assert "产品码不得 import 本文件" in header, header[:200]


def test_the_gauge_does_not_read_the_backend_switch():
    """两腿都显式问：读旋钮就等于把"没翻默认的装机"这格排除在测量之外。"""
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]

    assert 'getenv("INDEX_BACKEND' not in body, body[:200]
    assert "read_backend" not in body and "INDEX_BACKEND_DEFAULT" not in body
    assert "本量具不读 INDEX_BACKEND" in body or "不读 INDEX_BACKEND" in source
