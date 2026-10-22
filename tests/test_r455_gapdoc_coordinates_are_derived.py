# -*- coding: utf-8 -*-
"""R455 · 常驻钉：缺口单那三枚后端坐标只许是**符号派生**的读数 —— 抄一枚与漂一枚同样当场红。

病灶（工单 R455，本单基点 `c2e6546`）：`docs/handoff/2026-09-26-v1-frontend-gap-list.md`
的五枚行内引用（T2／G04／G06／G08／§遗留 2）抄的是 `app/api/v1/chat.py:NNNN`。为这一族返工
已经两笔（R387/R400 那本血缘账先漂，R404 并树给 import 块净 +1、版本史那条腿净 +17，又漂一次）。
本单不再抄第三遍：量具 `scripts/r455_gapdoc_coordinates.py` 按符号现读，本件把「文档那一格 ==
现读」逐枚钉死，多出来的手抄、被追改的历史表、写错层的引用各配一把牙（后两把在
`tests/test_r455_hand_fudged_numbers_and_wrong_layers_both_redden.py`）。

本件钉什么：
  ① 三枚锚在那棵干净的树上逐枚唯一命中，落点各在自己那一层（Form 缺省落在签名区间里，
     两枚路由落在 `@router.` 装饰器上、且下一行读得出端点定义）；
  ② 缺口单那五枚行内引用与派生读数**逐字节等值**（判据①那句等值要求就钉在这里）；
  ③ 历史区之外不许再长出一枚手抄坐标；文末那两张对账表逐行与并树那一版相同（判据③）；
  ④ 那枚 `chat.py:3933` 继续替「这枚已经漂了」说话：枚数对得上，且不等于今天的任何一枚现读；
  ⑤ 量具自己不许夹带抄来的行号，也不许另起第二把匹配器 —— 派生道只有 r387 那一族，
     而 r387 的本体在这单里一个字都没动。

🔴 效力边界：本件只读源码文本与文档字节，不写生产码、不起服务、不连库、不打模型；变异一律
   落在 tmp 影子树或进程内字典上（`tests/test_r253_no_test_rewrites_a_tracked_file.py` 盯着这一形）。
   它证的是「文档说的那三个坐标与现场同序、手抄进不了这本账」，不证问答本身好用。
🔴 摘守卫的门：环境变量 `R455_GAPDOC_TOOL` 指到一枚改过的量具副本，本件与两枚牙件都从那里加载。
   这不是豁免名单 —— 它是「摘掉哪一把牙、红几枚」能被复跑的那条路。
"""
from __future__ import annotations

import ast
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, "读不到量具：" + str(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


TOOL = _load(Path(os.getenv("R455_GAPDOC_TOOL") or (REPO / "scripts" / "r455_gapdoc_coordinates.py")),
             "r455_gapdoc_coordinates")

TOOL_REL = "scripts/r455_gapdoc_coordinates.py"
R387_REL = "scripts/r387_label_lineage.py"
CHAT = TOOL.CHAT
GAPDOC_REL = TOOL.GAPDOC
#: 影子树里插的那一行：它只活在 tmp_path 里，盘上那一棵一个字没动。
PAD_LINE = ""


def gapdoc_text() -> str:
    return (REPO / GAPDOC_REL).read_bytes().decode("utf-8")


def tool_text() -> str:
    return (REPO / TOOL_REL).read_bytes().decode("utf-8")


def derived(root: Path = REPO, sites: dict | None = None) -> dict:
    cells, failures = TOOL.derived_cells(root, sites)
    assert not failures, "锚读不出来，先修锚再谈落地：" + "；".join(failures)
    return cells


def shadow_root(tmp_path: Path, pad_lines: int = 0, doc_text: str | None = None) -> Path:
    """把被引的两枚文件按字节搬进 tmp 再叠变异：这是 R253 之后唯一允许的变异形状。"""
    root = tmp_path / "shadow"
    chat = root / CHAT
    chat.parent.mkdir(parents=True, exist_ok=True)
    body = (REPO / CHAT).read_bytes().decode("utf-8")
    if pad_lines:
        body = (PAD_LINE + "\r\n") * pad_lines + body
    chat.write_bytes(body.encode("utf-8"))
    doc = root / GAPDOC_REL
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_bytes((gapdoc_text() if doc_text is None else doc_text).encode("utf-8"))
    return root


# ------------------------------------------------------------------ ① 锚与层


def test_the_three_anchors_hit_exactly_once_on_the_pristine_tree() -> None:
    """三枚锚逐枚唯一命中：命中 0 枚＝锚已腐，≥2 枚＝不再是唯一锚（取第一次就是猜）。"""
    cells, failures = TOOL.derived_cells(REPO)
    assert not failures, str(failures)
    assert set(cells) == {"upload_form", "queue_cancel", "sessions_route"}, str(cells)
    for key, cell in cells.items():
        assert cell.startswith(TOOL.CELL_HEAD), key + " 那一格的形状不对：" + cell
        assert int(cell[len(TOOL.CELL_HEAD):]) > 0, key + " 那一格读不出行号：" + cell


def test_the_upload_coordinate_is_the_form_default_inside_its_signature() -> None:
    """判据①第一枚锚：`classification: int = Form(1)` 所在**签名的行区间**，引的是区间里那一格。"""
    read = TOOL.resolve_site("upload_form", REPO)
    first, last = read["signature"]
    assert first < read["line"] < last, "那一格没落在签名区间之内：" + str(read)
    assert "Form(" in read["face"], read["face"]
    assert read["face"].startswith("classification: int = Form(1"), read["face"]


@pytest.mark.parametrize("key", ["queue_cancel", "sessions_route"])
def test_the_route_coordinates_land_on_route_decorators_not_on_a_helper(key: str) -> None:
    """判据①另两枚锚：路由那一行必须是 `@router.` 装饰器本身，下一行读得出端点定义。

    这正是 §126 那句「写下时就查错了层」的解药 —— 当年 `GET /sessions` 被抄成了
    `_ensure_session` 那一层，数没错在偏移上，错在引的根本不是路由本体。
    """
    read = TOOL.resolve_site(key, REPO)
    assert read["face"].startswith("@router."), key + " 落在非路由的一层：" + read["face"]
    rows = TOOL._rows(CHAT, REPO)
    assert rows[read["line"]].startswith("async def "), "装饰器下面那行不是端点：" + rows[read["line"]]


# ------------------------------------------------------------------ ② 逐字节等值


def test_the_marker_registry_locates_every_live_cite_uniquely() -> None:
    """五枚行内引用的锚（行锚 + 坐标左锚）各须恰一枚命中：锚腐了要先知道，不许读成旧数。"""
    text = gapdoc_text()
    assert len(TOOL.LIVE_CITES) == 5, "行内引用比病灶点名的少：只登记了 " + str(len(TOOL.LIVE_CITES)) + " 枚"
    for cite in TOOL.LIVE_CITES:
        assert text.count(cite["row"]) == 1, cite["label"] + " 的行锚命中 " + str(text.count(cite["row"])) + " 枚"
        assert text.count(cite["before"]) == 1, cite["label"] + " 的坐标左锚命中 " + str(text.count(cite["before"])) + " 枚"


@pytest.mark.parametrize("cite", TOOL.LIVE_CITES, ids=lambda cite: cite["label"])
def test_every_live_coordinate_cell_in_the_gap_doc_equals_the_derived_reading(cite: dict) -> None:
    """🔴 判据①那句「逐字节等值」：文档那一格印的 == 按符号现读的，一枚都不许多一枚都不许少。"""
    printed = TOOL.read_cite_cell(gapdoc_text(), cite)
    want = derived()[cite["key"]]
    assert printed == want, (
        cite["label"] + "（锚 " + cite["key"] + "）：那一格印 " + printed + "、按符号现读 " + want
        + " ⇒ 这一格只有一条路：跑 `" + TOOL.EMIT_COMMAND + "` 重落地，不许手改数字，也不许拿旧数加减行号")


# ------------------------------------------------------------------ ③④ 历史与反证钉


def test_no_hand_copied_coordinate_lives_outside_the_history() -> None:
    """🔴 结构性关掉这一族的落点：历史区之外，本文每一枚后端坐标都得是派生读数。"""
    text = gapdoc_text()
    assert TOOL.stray_coordinates(text, derived()) == [], "历史区之外躺着抄来的坐标"
    assert TOOL.compare(root=REPO, text=text)["stray"] == []


def test_the_tool_catches_a_brand_new_copied_coordinate() -> None:
    """反证：往正文里再抄一枚「看着对得上」的坐标，尺子必须当场认出那是第六枚手抄。"""
    text = gapdoc_text()
    row, _ = TOOL._row_of(text, "| T3 | 查自己报的数据", "T3")
    lines = text.splitlines()
    lines[row] = lines[row] + "（手抄一枚新坐标 `app/api/v1/chat.py:4100`）"
    assert TOOL.stray_coordinates("\r\n".join(lines), derived()) == [TOOL.CELL_HEAD + "4100"]


def test_the_two_historical_tables_are_unchanged_since_the_merge() -> None:
    """判据③：`ac84f1a`／`4037868`／`4cd0a1c` 那几张是当年现读，改口历史＝造假 —— 逐行钉死。"""
    base = TOOL.head_gapdoc(REPO)
    assert TOOL.history_frozen_diff(gapdoc_text(), base) == []


def test_the_stale_coordinate_still_proves_the_drift() -> None:
    """`chat.py:3933` 继续留着：枚数对得上，且不等于今天的任何一枚现读（它说的是「已经漂了」）。"""
    text = gapdoc_text()
    assert text.count(TOOL.STALE_PROOF_SHORT) == TOOL.STALE_PROOF_OCCURRENCES, "那枚反证钉被人动了"
    assert TOOL.STALE_PROOF_TOKEN not in set(derived().values()), "它要是等于今天的现读，那句反证就白写了"
    red = TOOL.compare(root=REPO, text=text)["red"]
    assert not [item for item in red if TOOL.STALE_PROOF_SHORT in item], str(red)


# ------------------------------------------------------------------ ⑤ 量具自己的形状


def _string_constants(tree: ast.AST, exclude_docstrings: bool = True) -> list:
    doc_nodes = set()
    if exclude_docstrings:
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
                head = body[0]
                if isinstance(head, ast.Expr) and isinstance(head.value, ast.Constant) \
                        and isinstance(head.value.value, str):
                    doc_nodes.add(id(head.value))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_nodes]


def test_the_tool_carries_no_copied_line_number_of_its_own() -> None:
    """🔴 量具里不许躺着一枚抄来的行号：整数字面量一枚都不许像行号，可执行字符串里也不许。"""
    tree = ast.parse(tool_text())
    ints = [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool)]
    assert [value for value in ints if value >= 1000] == [], "量具里躺着像行号的整数：" + str(ints)
    copies = [item for item in _string_constants(tree) if re.search(r"chat\.py:\d", item)]
    assert copies == [], "量具自己开始手抄坐标了：" + str(copies)


def test_the_derivation_path_is_shared_with_r387_and_no_second_matcher_is_written() -> None:
    """判据①那条「二选一」选的是复用：本件走 r387 的锚块匹配，自己一枚正则都没写。"""
    tree = ast.parse(tool_text())
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert any(module.endswith("r387_label_lineage") or module == "scripts" for module in imports), str(imports)
    aliases = [alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
               for alias in node.names if alias.asname or alias.name]
    assert "r387_label_lineage" in aliases, str(aliases)
    plain = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert "re" not in plain, "量具 import 了 re：那是第二把匹配器，判据①明令不许 —— 派生道只许 r387 那一把尺"
    used = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert {"_one_hit", "_lines_of"} <= used, "没走 r387 那把尺，走的什么：" + str(sorted(used))
    assert not any(name in used for name in ("compile", "match", "search", "findall")), "又长出一把正则"


def test_the_sibling_lineage_tool_is_untouched_by_this_ticket() -> None:
    """r387 的本体在这单里一个字都没动：与工作树对一份字节账。"""
    out = subprocess.run(["git", "show", "HEAD:" + R387_REL], cwd=str(REPO), capture_output=True)
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")
    assert (REPO / R387_REL).read_bytes().replace(b"\r\n", b"\n") == out.stdout, "r387 本体被人改了，本单写域不含它"


# ------------------------------------------------------------------ 出账那两条腿


def test_the_emit_command_and_the_library_answer_the_same_three_cells() -> None:
    """判据②凭据的一半：`--emit-doc-cells` 打出来的三格 == 库内现读的三格（逐字节）。"""
    out = subprocess.run([sys.executable, TOOL_REL, "--emit-doc-cells"], cwd=str(REPO),
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert out.returncode == 0, out.stderr
    printed = dict(line.split("\t", 1) for line in out.stdout.splitlines() if "\t" in line)
    assert printed == derived(), str(printed)


def test_the_check_command_answers_zero_on_a_clean_tree() -> None:
    """判据②凭据的另一半：`--check` 在今天这棵树上 rc=0，并报出五枚行内引用全等值。"""
    out = subprocess.run([sys.executable, TOOL_REL, "--check"], cwd=str(REPO),
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "RED" not in out.stdout, out.stdout
    assert "5／5 枚" in out.stdout, out.stdout
