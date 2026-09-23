"""R163 —— 给 R159 那枚「矩阵不许被改松」的钉接上牙，并把判据④的对照表钉成机器可校验的事实。

## 判据①：反向钉（证明那枚钉还有牙）

R159 版把八枚放宽标记写成模块级常量，再拿全文源码去扫这些常量 ⇒ 字面量永远在自己肚子里，
那枚钉永不可能绿。R163 的改法是按 ast 行区间只剥标记表本身，表外一行都不放过。本件回答
「改完之后它是不是还咬得动」，三条口径：

- 不许降级：八枚标记（skip / skipif / xfail / mark / filterwarnings / raises / strict）逐条
  真塞进矩阵那枚参数化用例里，每一条都得被抓到——只查 skip 不查别的，本件当场红。
- 真塞进用例：注入的是可执行语句或真装饰器（ast 复核它确实落在用例函数体内 / 装饰器列表里），
  不是注释和 docstring 里的字样；塞进去之后那枚格子会静默变绿，正是它最该红的形状。
- 真跑一次：另有一枚子进程取证——把 pytest.skip( 写进 tmp_path 里的矩阵副本，由真 pytest 跑
  那枚钉，必须非零退出；仓库里的原件全程一个字没动，跑完再读它仍然是绿的（＝撤桩之后的样子）。

## 判据②的防洗白条：归因快照

每格的 A/B/C 与「产品漏 / 矩阵搭错」都写进格子；本件再钉两条：归了产品因的格子今天必须真的红
（且报出的必须是它那一列的判据），判成「矩阵桩搭错」的格子修完必须真的绿。哪天产品把 A 类补了，
这里会红一声——那是提醒去更新归因与 §6 C 行读数，不是让你删格子。

## 判据④：覆盖对照表

「既存权限件各盖了矩阵哪几格 vs 本件新补哪几格」由矩阵自己的 covered_by 字段生成（单一真相源）。
本件把它打印成表，并钉住四条：每格都得交代、引到的既存件必须真在盘上、判「缺口」的格子也必须点名
既存件漏在哪、未被本矩阵引用的权限件必须逐条说清为什么不算本件补的。下一班不必再数一遍。
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

import test_r159_cross_scope_matrix as matrix
from test_r159_cross_scope_matrix import (  # noqa: F401  -- ctx 复用矩阵那枚夹具，不另起一套现场
    SOFTENING_MARKERS,
    audit_matrix_source,
    cells_covering,
    cited_test_files,
    ctx,
    find_softening_markers,
    gap_cells,
    is_gap_cell,
)

MATRIX_PATH = Path(__file__).with_name("test_r159_cross_scope_matrix.py")
MATRIX_SOURCE = MATRIX_PATH.read_text(encoding="utf-8")
TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
#: 矩阵唯一那枚参数化用例的头；反向桩全部塞在它身上。
CASE_DEF = "def test_r159_cross_scope_cell(ctx, cell: Cell) -> None:"
NAIL_SELECTOR = "test_r159_matrix_is_not_softened"


def _case_def_line(lines: list[str]) -> int:
    hits = [i for i, line in enumerate(lines, start=1) if line.startswith(CASE_DEF)]
    assert len(hits) == 1, "矩阵里必须恰有一枚参数化用例可当反向桩落点，实取 " + str(hits)
    return hits[0]


def _inject(statement: str, kind: str, source: str = MATRIX_SOURCE) -> tuple[str, int]:
    """把一行真代码塞进那枚用例：body 进函数体第一行，decorator 贴到 def 上方。"""
    lines = source.splitlines()
    at = _case_def_line(lines)
    if kind == "decorator":
        injected = lines[: at - 1] + [statement] + lines[at - 1 :]
        number = at
    else:
        injected = lines[:at] + [statement] + lines[at:]
        number = at + 1
    return "\n".join(injected), number


def _case_node(source: str) -> ast.FunctionDef:
    nodes = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "test_r159_cross_scope_cell"
    ]
    assert len(nodes) == 1, "注入之后的矩阵必须还能解析，且那枚用例还得是那枚用例"
    return nodes[0]


#: (标记, 注入位置, 真代码)：八枚逐条取自矩阵自己的标记表，少一枚本件就红。
TEETH_PAYLOADS = [
    ("pytest.skip(", "body", '    pytest.skip("R163 反向桩：证明这枚钉还有牙")'),
    ("@pytest.mark.skip", "decorator", "@pytest.mark.skip"),
    ("pytest.mark.skipif", "decorator", '@pytest.mark.skipif(True, reason="R163 反向桩")'),
    ("pytest.mark.xfail", "decorator", "@pytest.mark.xfail"),
    ("pytest.xfail(", "body", '    pytest.xfail("R163 反向桩")'),
    ('filterwarnings("ignore"', "body", '    warnings.filterwarnings("ignore")'),
    ("raises=False", "body", "    pytest.raises(RuntimeError, _probe, raises=False)"),
    ("strict=False", "body", '    warnings.filterwarnings("error", append=True, strict=False)'),
]


def test_r163_marker_table_is_still_whole() -> None:
    """反向钉的前提：表里就是那八枚，且牙齿样本与扫描器读的是同一张表。"""
    assert len(SOFTENING_MARKERS) == 8, "标记表被改动过，先对齐本件的牙齿样本再说"
    for marker, _kind, statement in TEETH_PAYLOADS:
        assert marker in SOFTENING_MARKERS, "牙齿样本 " + marker + " 已不在表里：表与样本脱钩"
        assert marker in statement, "注入样本没带上自己的标记：" + statement


def test_r163_clean_matrix_has_no_marker_outside_the_table() -> None:
    """撤桩之后的基线：真源码在标记表之外一行都不该被抓到——这条红＝桩没撤干净。"""
    assert find_softening_markers(MATRIX_SOURCE) == []
    assert not [f for f in audit_matrix_source(MATRIX_SOURCE) if "放宽标记" in f]


@pytest.mark.parametrize(
    "marker,kind,statement",
    TEETH_PAYLOADS,
    ids=[item[0] for item in TEETH_PAYLOADS],
)
def test_r163_nail_bites_every_softening_marker(marker, kind, statement) -> None:
    """把八枚放宽手段逐条真塞进那枚用例：钉必须逐条红，且报出的是注入的那一行。"""
    injected, number = _inject(statement, kind)
    before = len(_case_node(MATRIX_SOURCE).decorator_list)
    node = _case_node(injected)
    if kind == "decorator":
        assert len(node.decorator_list) == before + 1, "装饰器没真挂到用例上，这次注入不算"
        assert node.lineno == number + 1, "装饰器没贴在用例 def 上方，这次注入不算"
    else:
        assert node.lineno <= number <= node.end_lineno, "语句没落进用例函数体，这次注入不算"

    hits = [f for f in audit_matrix_source(injected) if "放宽标记" in f]
    tag = "第 " + str(number) + " 行"
    assert hits, "注入 " + marker + " 之后一条放宽标记都没报"
    # 标记之间互为子串（skip ⊂ skipif），所以只要求「全部报在注入那一行」＋「目标标记在内」。
    assert all(tag in f for f in hits), "放宽标记没全报在注入的那一行：" + str(hits)
    assert any(marker in f for f in hits), "没报出注入的那枚标记：" + str(hits)


def test_r163_nail_bites_when_a_marker_moves_out_of_the_table() -> None:
    """「把标记从表里摘走、另存一处」同样得红：扫描器剥的是行区间，不是字面量本身。"""
    lines = MATRIX_SOURCE.splitlines()
    relocated = "\n".join(lines + ["", "", 'R163_EXTRA = ("pytest.skip(", "pytest.mark.xfail")'])
    findings = find_softening_markers(relocated)
    assert findings, "标记搬到表外一处就没牙：那枚钉仍可被绕开"
    assert len(findings) == 2, "表外那一行该报两枚，实报：" + str(findings)
    assert all(("R163_EXTRA" in f and "第 " + str(len(lines) + 3) + " 行" in f) for f in findings), (
        "表外那一处没被按行号报出来：" + str(findings)
    )


def test_r163_nail_bites_when_the_table_is_renamed_or_duplicated() -> None:
    """表被改名 / 拆成两处：连「该剥哪一段」都定不下来，必须报错而不是退回全文扫描。"""
    renamed = MATRIX_SOURCE.replace("def " + matrix.MARKER_TABLE_FUNCTION + "(", "def _moved(", 1)
    with pytest.raises(AssertionError):
        audit_matrix_source(renamed)
    duplicated = MATRIX_SOURCE + (
        "\n\n\ndef " + matrix.MARKER_TABLE_FUNCTION + "() -> tuple[str, ...]:\n    return ()\n"
    )
    assert duplicated.count("def " + matrix.MARKER_TABLE_FUNCTION + "(") == 2, (
        "这一份里标记表只出现一处，测不出「被拆成两处」"
    )
    with pytest.raises(AssertionError):
        audit_matrix_source(duplicated)


# ==================== 判据①：真 pytest 跑一次的磁盘取证 ====================


def _run_nail(cwd: Path, target: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    return subprocess.run(
        [
            sys.executable, "-m", "pytest", target, "-k", NAIL_SELECTOR,
            "-q", "--no-header", "-p", "no:randomly", "-p", "no:cacheprovider",
        ],
        cwd=str(cwd), capture_output=True, text=True, env=env, timeout=900,
    )


def test_r163_teeth_proven_by_a_real_pytest_run(tmp_path) -> None:
    """塞进用例的 skip 让钉由真 pytest 报红；仓库原件全程没被写过，所以它仍然是绿的。"""
    green = _run_nail(REPO_ROOT, str(MATRIX_PATH))
    assert green.returncode == 0 and "1 passed" in green.stdout, (
        "仓库里那枚钉今天必须绿：" + (green.stdout + green.stderr)[-2500:]
    )

    marker, kind, statement = TEETH_PAYLOADS[0]
    softened, number = _inject(statement, kind)
    softened_path = tmp_path / MATRIX_PATH.name
    softened_path.write_text(softened, encoding="utf-8")
    red = _run_nail(tmp_path, softened_path.name)
    out = red.stdout + red.stderr
    assert red.returncode != 0, "把 " + marker + " 塞进用例之后那枚钉居然还绿：" + out[-2500:]
    assert "1 failed" in out and "no tests ran" not in out, out[-2500:]
    assert marker in out, "红是红了，却没报注入的这枚标记：" + out[-2500:]
    assert ("第 " + str(number) + " 行") in out, "红没报到行号：" + out[-2500:]
    assert MATRIX_PATH.read_text(encoding="utf-8") == MATRIX_SOURCE, "本件不许写矩阵原件"
# ==================== 判据②：归因快照（红格不许被悄悄洗成绿） ====================

#: 起点 21 红 = 7 枚矩阵自己的桩搭错（本班修绿）+ 13 枚产品侧。13 枚逐格归因如下，
#: 少一格、多一格、换一类，本件都红——那是提醒你去更新归因与 §6 C 行读数，不是让你删格子。
EXPECTED_ATTRIBUTION = {
    "retrieval.nodept_account_is_refused": "C",
    "legacy_chat.hidden_document_says_no_relevant_document": "B",
    "legacy_chat.nodept_account_is_refused": "C",
    "document_route.nodept_catalog_answers_empty_list": "B",
    "dataset_route.preview_must_not_leak_foreign_rows": "A",
    "dataset_route.nodept_catalog_answers_empty_list": "B",
    "session_route.peer_probe_of_anothers_session": "C",
    "session_route.admin_cannot_read_anothers_session": "C",
    "alert_route.foreign_manager_reads_scoped_alert": "A",
    "alert_route.staff_read_denial_is_audited": "C",
    "alert_route.staff_rule_write_is_denied": "C",
    "intelligence_route.peer_cannot_see_anothers_triples": "A",
    "row_scope_tools.all_datasets_hidden_says_no_data_file": "B",
}
#: 判成「矩阵桩搭错」的格子：修完必须真的绿，否则就是拿产品红冒充桩错。
EXPECTED_STUB_CELLS = {
    "answer_cache.keeper_reads_own_answer",
    "answer_cache_wire.keeper_hits_own_answer",
    "dataset_route.xclear_cannot_preview_higher_classification",
    "alert_route.manager_rule_write_is_allowed",
    "row_scope_tools.xclear_row_level_clearance",
    "observability.audit_events_require_audit_read",
    "observability.auditor_reads_the_journal",
}
#: A＝内容真越权（判据①）/ B＝挡住了但话说错了（判据②）/ C＝审计缺席（判据③）。
COLUMN_OF = {"A": "判据①", "B": "判据②", "C": "判据③"}
P1_CELLS = tuple(sorted(k for k, v in EXPECTED_ATTRIBUTION.items() if v == "A"))

PRODUCT_RED_CELLS = [cell for cell in matrix.CELLS if cell.root_cause == "product"]
STUB_CELLS = [cell for cell in matrix.CELLS if cell.root_cause == "matrix"]


def test_r163_attribution_snapshot_has_not_drifted() -> None:
    """归因表和实测必须一字不差地对上：谁偷偷改判、谁悄悄摘牌，这里都跑不掉。"""
    now = {cell.cell_id: cell.finding for cell in matrix.CELLS if cell.finding}
    assert now == EXPECTED_ATTRIBUTION, (
        "归因漂移：新增 " + str(sorted(set(now) - set(EXPECTED_ATTRIBUTION)))
        + " / 消失 " + str(sorted(set(EXPECTED_ATTRIBUTION) - set(now)))
        + " / 改类 " + str(sorted(k for k in now if k in EXPECTED_ATTRIBUTION and now[k] != EXPECTED_ATTRIBUTION[k]))
    )
    stubs = {cell.cell_id for cell in matrix.CELLS if cell.root_cause == "matrix"}
    assert stubs == EXPECTED_STUB_CELLS, "桩错名单变了：" + str(sorted(stubs ^ EXPECTED_STUB_CELLS))
    classes = {cell.finding for cell in matrix.CELLS if cell.finding}
    assert classes == {"A", "B", "C"}, "三类根因缺了：" + str(sorted(classes))
    assert P1_CELLS == tuple(
        sorted(cell.cell_id for cell in matrix.CELLS if cell.finding == "A")
    ), "A 类清单与格子对不上"


def test_r163_attribution_populations_are_not_emptied() -> None:
    """两拨名单都不许空：参数化空集会安静地少跑，而不是报错。"""
    assert len(PRODUCT_RED_CELLS) == 13, "产品侧红格数变了：" + str(len(PRODUCT_RED_CELLS))
    assert len(STUB_CELLS) == 7, "桩错格数变了：" + str(len(STUB_CELLS))


@pytest.mark.parametrize(
    "cell", PRODUCT_RED_CELLS, ids=[cell.cell_id for cell in PRODUCT_RED_CELLS]
)
def test_r163_attributed_product_gaps_are_still_red_today(ctx, cell) -> None:
    """归了产品因的格子今天必须真的红，而且报的必须是它那一列的判据——红错列也算归因错。"""
    with pytest.raises(AssertionError) as excinfo:
        matrix.test_r159_cross_scope_cell(ctx, cell)
    message = str(excinfo.value)
    assert cell.cell_id in message
    assert COLUMN_OF[cell.finding] in message, (
        cell.finding + " 类该由 " + COLUMN_OF[cell.finding] + " 报出来，实际报错：" + message[:400]
    )


@pytest.mark.parametrize("cell", STUB_CELLS, ids=[cell.cell_id for cell in STUB_CELLS])
def test_r163_matrix_stub_cells_are_green_today(ctx, cell) -> None:
    """判成「矩阵搭错」的格子必须已经绿：还红着就说明那句归因是假的。"""
    matrix.test_r159_cross_scope_cell(ctx, cell)


def test_r163_p1_list_is_reconstructible_from_the_matrix() -> None:
    """交回的 P1 清单三行（身份 / 请求 / 实拿）必须都能从格子里复原，不许只活在报告里。"""
    for cell in matrix.CELLS:
        if cell.finding != "A":
            continue
        assert cell.identity and cell.actor_over is not None, cell.cell_id + " 缺身份行"
        assert callable(cell.drive), cell.cell_id + " 缺请求行（drive）"
        assert cell.forbidden, cell.cell_id + " 缺「实拿」行（forbidden 令牌）"
        assert matrix._PRODUCT_PATH_PATTERN.search(cell.evidence), cell.cell_id + " 缺产品证据行"


# ==================== 判据④：既存权限件 × 本矩阵格子 ====================

#: 这 20+ 枚是「权限件」里本矩阵没有取格子的部分——逐条写明它管哪一面、为什么不算本件补的。
#: 与格子里引用的那些（cited_test_files）合起来就是对照表的全集。
UNCITED_PERMISSION_FILES = {
    "test_r65_two_path_error_codes.py": "管工具腿「码 + 人话」两路文案的码表，本矩阵判据②只在出口数一次措辞。",
    "test_phase2_rbac.py": "阶段 2 冒烟件（角色/密级模型），按模块组织，不构成本矩阵的格子来源。",
    "test_phase4_alerts.py": "阶段 4 冒烟件（告警/日报），同上。",
    "test_auth.py": "Day X JWT 冒烟件（签发/校验），鉴权入口层，不是资源面。",
    "test_auth_stable_codes.py": "鉴权面的稳定码词汇（401 家族）；本矩阵的格子全在「已过鉴权、判授权」之后。",
    "test_auth_database.py": "账号读写走数据库还是内存兜底，属存储契约。",
    "test_authorization_api.py": "401/403 语义与用户管理端点，鉴权入口层；本矩阵取的是资源出口内容。",
    "test_rbac_abac.py": "policy / 权限表的单元层（角色有哪些动作），本矩阵一律走端到端格子。",
    "test_document_ownership.py": "owner 列的写入与 catalog 行形状（数据契约层）；本矩阵 owner 轴只取路由那一格。",
    "test_agent_tool_authorization.py": "Agent 工具上下文里带不带 principal 权限集（工具注册层），本矩阵取工具执行后的内容与审计。",
    "test_knowledge_graph_verification.py": "图谱「谁能核对」的 review 动作面；本矩阵 intelligence 面取的是三元组读侧。",
    "test_prefiltering.py": "权限谓词必须早于向量打分/重排（检索管线内部顺序），本矩阵 retrieval 面只判「能不能被绕过」。",
    "test_sse_sources.py": "/ask 的 sources 事件形状与跨部门裁行；本矩阵 legacy /chat 那格恰恰因为这条腿没有 sources 出口才红。",
    "test_chat_cache_safety.py": "缓存键不带敏感料、跨会话不串答（会话轴）；本矩阵 answer_cache 面取的是授权作用域轴。",
    "test_stream_owner_resolution.py": "流恢复时按会话解析归属（归属解析层），本矩阵会话面取读/探测出口。",
    "test_hitl_pending.py": "待办列表只看自己的（挂起队列面），本矩阵 13 个资源面里没有这一面。",
    "test_response_hygiene.py": "响应不回显受保护正文（卫生层），本矩阵判的是可达性不是回显。",
    "test_resource_delete_cascade.py": "删除级联的授权与索引回滚，本矩阵不测写删路径。",
    "test_security_operations.py": "安全运维面（bootstrap admin、口令策略等），与本矩阵的资源可见性不同轴。",
    "test_data_tool_output_leak.py": "工具输出把路径/异常内部细节带出去（泄漏面），本矩阵 content 列只搜内容令牌。",
    "test_mcp_identity_scope.py": "MCP 面的身份继承（第 14 个资源面），本矩阵没开 MCP 面。",
    "test_open_platform.py": "开放平台契约与配额（面本身的行为），越权那几格由本矩阵 open_platform 承担。",
    "test_error_code_vocabulary.py": "错误码由谁定义、码表只许一份（词汇表治理），不是任何一格的判据。",
}

def test_r163_permission_coverage_census() -> None:
    """判据④的对照表：既存件各盖哪格、本件新补哪几格，全部由矩阵现场生成。"""
    cells = matrix.CELLS
    blank = [cell.cell_id for cell in cells if not cell.covered_by.strip()]
    assert not blank, "有格子没交代既存覆盖：" + str(blank)
    cited = sorted({name for cell in cells for name in cited_test_files(cell)})
    ghost = [name for name in cited if not (TESTS_DIR / name).exists()]
    assert not ghost, "对照表引了盘上不存在的既存件：" + str(ghost)

    covers = {name: [c for c in cells_covering(name) if not is_gap_cell(c)] for name in cited}
    covering_files = sorted(name for name in cited if covers[name])
    named_files = sorted(name for name in cited if not covers[name])
    for name, why in UNCITED_PERMISSION_FILES.items():
        assert (TESTS_DIR / name).exists(), "对照表里的既存权限件不在盘上：" + name
        assert why.strip(), name + " 没写为什么不算本件补的"
        assert not cells_covering(name), name + " 已被矩阵引用，这条得并入引用侧（否则表在说谎）"
    for cell in gap_cells():
        assert cited_test_files(cell), "缺口格 " + cell.cell_id + " 没点名既存件漏在哪"
    total = len(cited) + len(UNCITED_PERMISSION_FILES)
    assert total >= 20, "权限件全集不足 20 枚：对照表口径缩水"

    print("\n===== R163 判据④ 对照表 =====")
    print("-- A 面：盖了本矩阵格子的既存权限件（" + str(len(covering_files)) + " 枚）")
    for name in covering_files:
        print("  tests/" + name + "  盖 " + str(len(covers[name])) + " 格："
              + "、".join(c.cell_id for c in covers[name]))
    print("-- B 面：只在「缺口格」里被点名的既存件（" + str(len(named_files)) + " 枚）")
    for name in named_files:
        print("  tests/" + name + "  被这些新补格点名没盖到："
              + "、".join(c.cell_id for c in cells_covering(name)))
    print("-- C 面：与本矩阵零引用的既存权限件（" + str(len(UNCITED_PERMISSION_FILES)) + " 枚，逐条给理由）")
    for name in sorted(UNCITED_PERMISSION_FILES):
        print("  tests/" + name + "  " + UNCITED_PERMISSION_FILES[name])
    gaps = gap_cells()
    print("-- D 面：本件新补的格子（covered_by 以「" + matrix.GAP_PREFIX + "」开头，共 " + str(len(gaps)) + " 格）")
    for cell in gaps:
        state = "红格 " + cell.finding if cell.finding else "绿格 -"
        print("  " + cell.cell_id + "  [" + state + "]  " + cell.covered_by)
    line = (
        "对照表合计：既存权限件 " + str(total) + " 枚（盖格 " + str(len(covering_files))
        + " ＋ 只被点名 " + str(len(named_files)) + " ＋ 零引用 " + str(len(UNCITED_PERMISSION_FILES))
        + "）；矩阵 " + str(len(cells)) + " 格里本件新补 " + str(len(gaps)) + " 格，其中红格 "
        + str(len([c for c in gaps if c.finding])) + " 格")
    print(line)
    assert line



def test_r163_readout_for_plan_section_6_row_c() -> None:
    """能直接写进计划书 §6 C 行的那句读数，由本件算出来，不靠人复述。"""
    counts = {kind: len([c for c in matrix.CELLS if c.finding == kind]) for kind in ("A", "B", "C")}
    assert counts["A"] == 3, "A 类数量变了，读数得重发：" + str(counts)
    line = (
        "阶段 C 越权命中 " + str(counts["A"]) + " 条（R159/R163 矩阵 " + str(len(matrix.CELLS)) + " 格："
        + "A 内容越权 " + str(counts["A"]) + " / B 说法不诚实 " + str(counts["B"]) + " / C 审计缺席 "
        + str(counts["C"]) + "；另 " + str(len(STUB_CELLS)) + " 格系矩阵桩自错，R163 修后转绿）"
        + " ⇒ §6 C 行「越权命中 0 条」不成立，按 §8.5 继续锁 E 线越权判据。"
    )
    print(line)
    assert line
