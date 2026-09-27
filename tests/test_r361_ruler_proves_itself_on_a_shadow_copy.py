# -*- coding: utf-8 -*-
r"""R361 · 尺子自证：在**影子副本**里改掉一枚被读的事实，预演器必须报出"哪一格、从几变到几"。

判据 戊。姿势照 tests/test_r346_line_ledger_is_derived_not_copied.py：变异全部落在
``tmp_path`` 下那棵影子里，🔴 盘上的被跟踪文件一字节都不动（每件用例都亲自比 sha256）。
本仓另有两件常驻抓"测试就地改写被跟踪源文件"——``tests/test_r253_no_test_rewrites_a_tracked_file.py``
与 ``tests/test_r253_shadow_root_holds_the_mutation.py``——它们必须一直绿，本件也不给它们送人头。

四组读数，每组都要红得**指名道姓**：

  ① 派生格被改：值跟着变，报告里那一句必须同时带出旧值与新值（"从几变到几"）。
  ② 抄本格被改（route_main 那两张词表 + 缓存键那一句）：等值钉当场点名差在哪一枚。
  ③ 只插行、不改值：🔴 值账必须一字不动（红的不许是值），只有"行跨度"这一格会跟上——
     这正是 R346 那枚门红的病根反过来当判据用：量行号的东西必须自己跟着动。
  ④ 影子与盘上同字：drift 必须是空表（尺子不许"总是红"，那是另一种假绿）。
"""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "rehearse_eval_window.py"

#: 影子树要装下的现场：预演器读的全部源码。
READ_SOURCES = (
    "app/agents/orchestrator.py",
    "app/agents/nodes.py",
    "app/agents/planner.py",
    "app/agents/tools.py",
    "app/agents/evidence.py",
    "app/api/v1/chat.py",
    "app/common/cache.py",
    "app/common/model_handler.py",
    "app/common/model_budget.py",     # R379 格一：地板默认值的真身住在这里
    "app/quality/eval.py",
    "scripts/eval_transport_ask_v2.py",
)


def load_script(module_name: str, path: Path):
    """按源码文本现编译加载本件。🔴 不许换回 ``spec.loader.exec_module``（理由见 R361 那枚同名钉）。"""
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    exec(compile(path.read_text(encoding="utf-8-sig"), str(path), "exec"), module.__dict__)
    return module


@pytest.fixture(scope="module")
def mod():
    return load_script("r361_ruler_target", SCRIPT)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_shadow_tree_covers_every_source_the_ruler_reads(mod):
    """影子树少了哪一枚现场，尺子在那一枚上就天生是瞎的（R379 加格子时踩过一次）。

    只钉集合相等：``REPO_RELS`` 是预演件读现场的全部路径，这张名单是它的影子副本——两边
    必须一枚不差地长在一起，否则新加一枚读数就会让下面每一格报"读不到现场源码"。
    """
    assert set(READ_SOURCES) == set(mod.REPO_RELS.values()), (
        "影子树与预演件的现场清单不等："
        + str(sorted(set(READ_SOURCES) ^ set(mod.REPO_RELS.values()))))


def build_shadow(tmp_path: Path, edits=()) -> Path:
    """把被读的十枚源码原样复制进影子根，再按 (相对路径, 原文, 新文) 逐条改影子。

    每改一条都当场核对盘上那枚的 sha256 没动——"改的是影子不是被跟踪文件"这句得可复核。
    """
    root = tmp_path / "shadow"
    tracked_before = {rel: sha256(REPO / rel) for rel in READ_SOURCES}
    for rel in READ_SOURCES:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target)
    for rel, old, new, times in shadow_edits(edits):
        path = root / rel
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        found = text.count(old)
        assert found == times, f"影子里锚点数不对：{rel} / {old[:44]} 要 {times} 处，实有 {found} 处"
        path.write_text(text.replace(old, new), encoding="utf-8", newline="")
        assert sha256(REPO / rel) == tracked_before[rel], f"{rel} 被就地改写了（判据 戊 的红线）"
    return root


def shadow_edits(cases):
    """把 (rel, old, new) 补成 (rel, old, new, 处数)：锚点允许多处，但必须当面说好几处。"""
    return [edit + (1,) if len(edit) == 3 else edit for edit in cases]


def names(report) -> list:
    return [line.split(" ", 1)[0] for line in report]


# ==================== ④ 影子与盘上同字 => 不许红 ====================


def test_an_untouched_shadow_reports_zero_drift(tmp_path, mod):
    root = build_shadow(tmp_path)
    assert mod.drift_between(REPO, root) == [], "影子原样复制也报漂移：这把尺子总是红"
    assert mod.copy_drift(root) == []


# ==================== ① 派生格 ====================

DERIVED_CASES = (
    ("parked leg removed", "app/agents/orchestrator.py",
     '_HITL_PARKED = ("chart", "export")', '_HITL_PARKED = ("chart",)', 1,
     ("HITL_PARKED", "PARK_TEXTS", "INTERRUPT_BEFORE")),
    ("cache ttl halved", "app/common/cache.py",
     "DEFAULT_ANSWER_CACHE_TTL_SECONDS = 1800", "DEFAULT_ANSWER_CACHE_TTL_SECONDS = 900", 1,
     ("CACHE_TTL_SECONDS",)),
    ("adapter gap widened", "scripts/eval_transport_ask_v2.py",
     'os.getenv("EVAL_MIN_GAP_SECONDS", "7")', 'os.getenv("EVAL_MIN_GAP_SECONDS", "8")', 1,
     ("ADAPTER_MIN_GAP_SECONDS",)),
    # 现场把同一枚默认值算了两次（两条链路各一枚 RequestBudget）：影子两处一起改，
    # 只改一处会被读数的“口径不唯一”闸截住——那是另一枚牙，不冲突。
    ("request budget tightened", "app/api/v1/chat.py",
     'os.getenv("CHAT_REQUEST_TIMEOUT", "300")', 'os.getenv("CHAT_REQUEST_TIMEOUT", "301")', 2,
     ("REQUEST_BUDGET_SECONDS",)),
    ("blank sentinel reworded", "scripts/eval_transport_ask_v2.py",
     'os.getenv("EVAL_BLANK_SENTINEL", "<no-bytes-emitted>")',
     'os.getenv("EVAL_BLANK_SENTINEL", "<nothing-emitted>")', 1, ("BLANK_SENTINEL",)),
    ("planner drops the approval step", "app/agents/planner.py",
     '        tasks.append(_task("approval", f"根据数据和制度生成审批预审建议：{q}", deps))\n',
     '        pass  # 影子：现场不再排 approval 这条腿\n', 1,
     ("PLANNER_WORKERS",)),
    ("approval label renamed", "app/agents/orchestrator.py",
     'missing.append("可核对的制度标准")', 'missing.append("可核对的报销上限")', 1,
     ("APPROVAL_TEXTS",)),
    # 这四枚本件也 import（判据 丙量过：nodes 零出站），但派生走的是源码——
    # 只认 import 的那一格对影子天生是瞎的，这一枚就是专门钉那件事。
    ("offline sentence reworded", "app/agents/nodes.py",
     "OFFLINE_STREAM_CHUNK = '离线模式已启用'", "OFFLINE_STREAM_CHUNK = '离线模式已就绪'", 1,
     ("OFFLINE_TEXTS",)),
)


@pytest.mark.parametrize("label, rel, old, new, times, expected", DERIVED_CASES,
                         ids=[case[0] for case in DERIVED_CASES])
def test_a_mutated_derived_cell_is_reported_with_before_and_after(
        tmp_path, mod, label, rel, old, new, times, expected):
    root = build_shadow(tmp_path, [(rel, old, new, times)])
    report = mod.drift_between(REPO, root)
    reported = names(report)
    for cell in expected:
        assert cell in reported, f"{label}：报告没点到 {cell}。整份报告：{report}"
    for line in report:
        cell = line.split(" ", 1)[0]
        assert " -> " in line, f"{cell} 那一句没带『从几变到几』：{line}"
        left, right = line.split(": ", 1)[1].split(" -> ")
        assert left != right, f"{cell} 两句同值：{line}"
    # 🔴 派生格的红不需要抄本参与：值本身就跟着现场走
    assert all("[copy]" not in line for line in report), report


# ==================== ② 抄本格：等值钉当场点名 ====================

COPY_CASES = (
    ("chart table grew a word", "app/agents/orchestrator.py",
     'chart_kw = ["画", "图", "图表", "柱状图", "折线图", "饼图", "可视化", "图形"]',
     'chart_kw = ["画", "图", "图表", "柱状图", "折线图", "饼图", "可视化", "图形", "曲线"]',
     "KW_CHART", "曲线"),
    ("export table lost a word", "app/agents/orchestrator.py",
     'export_kw = ["导出", "PDF", "pdf", "报告", "下载"]',
     'export_kw = ["导出", "PDF", "pdf", "报告"]', "KW_EXPORT", "下载"),
    ("doc table reordered", "app/agents/orchestrator.py",
     '    doc_kw = [\n        "制度", "流程",', '    doc_kw = [\n        "流程", "制度",',
     "KW_DOC", "同枚不同形"),
    ("data table lost a word", "app/agents/orchestrator.py",
     'data_kw = ["排名", "最高", "最低", "统计", "分析数据", "对比", "比较", "哪个"]',
     'data_kw = ["排名", "最高", "统计", "分析数据", "对比", "比较", "哪个"]', "KW_DATA", "最低"),
)


@pytest.mark.parametrize("label, rel, old, new, cell, token", COPY_CASES,
                         ids=[case[0] for case in COPY_CASES])
def test_a_mutated_copy_cell_goes_red_and_names_the_difference(
        tmp_path, mod, label, rel, old, new, cell, token):
    root = build_shadow(tmp_path, [(rel, old, new)])
    assert isinstance(root, Path)
    lines = mod.copy_drift(root)
    assert lines, f"{label}：抄本与现场已经不等，等值钉却没红"
    assert any(cell in line for line in lines), f"{label}：红的不是那一格 {cell}：{lines}"
    assert any(token in line for line in lines), f"{label}：没点名差在哪一枚 {token}：{lines}"
    assert any("变到" in line for line in lines), f"{label}：没给出从几变到几：{lines}"
    # 整扇门必须红：预演器不许带着这一格继续算（guard_facts 是 main 开机走的那道闸）
    gate = mod.guard_facts(mod.load_rows(), root)
    assert any(cell in line for line in gate), f"{label}：开机闸门没拦下这格：{gate}"


def test_the_cache_key_prose_is_pinned_to_the_live_shape(tmp_path, mod):
    """摘要里那句"键=md5(scope)[:12]+…"是抄本：现场把摘要位宽改成 11，它必须当场点名。"""
    root = build_shadow(tmp_path, [("app/common/cache.py",
                                   "hashlib.md5(question.strip().encode()).hexdigest()[:12]",
                                   "hashlib.md5(question.strip().encode()).hexdigest()[:11]")])
    lines = mod.copy_drift(root)
    assert any("CACHE_KEY_PROSE" in line for line in lines), lines
    assert any("md5(问题.strip())[:12]" in line and "md5(问题.strip())[:11]" in line
               for line in lines), lines


# ==================== ③ 只插行不改值 ====================


#: ③ 的插行锚点。影子改的这枚字节串与派生基准行扫的必须是同一枚，所以全文只写这一次。
ANCHOR_DEF = "def _approval_worker_node(state: AgentState, config) -> dict:"


def live_anchor_line(rel: str, anchor: str) -> int:
    """在**盘上现读**锚点行号 —— 本件不许把行号抄成常数。

    这是独立于尺子的第二把量具：报告里的旧值必须等于它，否则 ③ 退化成自证。
    抄死过一次的下场记在这里：R395 并树 ``0ab5f1f`` 给 orchestrator.py 加了 11 行，
    把 _approval_worker_node 从 808 推到 819，于是 09-28 全量门里一枚**尺子行为完全正确**
    的用例被判成红 —— 病不在被量的东西，在抄下来的那个数。
    """
    rows = (REPO / rel).read_text(encoding="utf-8-sig").replace("\r\n", "\n").splitlines()
    hits = [index for index, row in enumerate(rows, start=1) if row == anchor]
    assert len(hits) == 1, f"锚点在盘上不是唯一命中，插行判据失去基准：{hits}"
    return hits[0]


def test_inserting_lines_moves_only_the_span_ledger(tmp_path, mod):
    """在被读函数上方插 300 行噪声：值账一字不动，行跨度那一格自己跟上。

    R346 那枚门红就是这么埋出来的：账按行号钉、又不肯跟着现场动。这一格反过来当判据——
    插行之后预演器**不许**报任何值漂移，而打印进 --summary 的那两处出处必须跟着走。
    """
    rel = "app/agents/orchestrator.py"
    pad = "\n".join(f"# R361 影子噪声 第 {index} 行" for index in range(300))
    root = build_shadow(tmp_path, [(rel, ANCHOR_DEF, pad + "\n" + ANCHOR_DEF)])
    base = live_anchor_line(rel, ANCHOR_DEF)
    report = mod.drift_between(REPO, root)
    assert names(report) == ["APPROVAL_WORKER_SPAN"], report
    line = report[0]
    cells = [cell.strip("'") for cell in line.split(": ", 1)[1].split(" -> ")]
    assert len(cells) == 2 and all(rel in cell for cell in cells), line
    spans = [[int(part) for part in cell.rsplit(":", 1)[1].split("-")] for cell in cells]
    assert [start for start, end in spans] == [base, base + 300], (
        f"插 300 行后行跨度没跟着基准 {base} 走：尺子仍然是抄的：{line}")
    assert spans[0][1] - spans[0][0] == spans[1][1] - spans[1][0], (
        "插行把函数自身的长度也改了：那是尺子算错跨度，不是行号跟上：" + line)
    assert mod.copy_drift(root) == [], "插行把等值钉插红了：那是假红，本单要根治的就是它"
