"""R345 · 告警巡检认哪些后缀，必须现读 R336 那把单一事实源，而不是第三份手抄。

症状（总控在基点实测，不是推测）：`app/api/v1/alerts.py::_data_file_extensions` 写的是
`getattr(data_api, "DATA_FILE_EXTENSIONS", None) or {".csv", ".xlsx", ".xls"}`。回退那一支今天走不到
（data.py 一定回值），所以它是**死的可见的**：字面量里带着 `.xls` —— 一枚 R336 已经点名拒绝的格式。
下一位改了 data.py 的导入路径、或 `_data_api_module()` 递不出那一格，巡检就悄悄恢复扫 `.xls`，
而读它的那条腿（`load_excel` 现在先吐 `UnsupportedDataFile`）已经被关掉：名单与读腿各漂各的。

本件照 R336 的口径钉两格，缺一格都拦不住下一位：
  · 写法：AST 要求 `_data_file_extensions` 的返回值来自一枚调用（`accepted_data_file_extensions`），
    并且全文件不再出现任何一枚长得就是后缀的字符串字面量 —— 只抓今天的值抓不住明天那份手抄；
  · 现读：往声明表塞一枚新扩展名 / 从声明表摘掉 `.csv`，巡检集合与 `_directory_data_files`
    必须跟着动。导入期抄下来的快照（哪怕它自己也是派生的）在这一把下会红，正是要它红。

全部离线：不起服务、不连库、不打模型；夹具坐在 `tmp_path` 上。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALERTS_PY = ROOT / "app" / "api" / "v1" / "alerts.py"

#: 产生巡检名单的那枚调用（真源：app/tools/excel.py::DATA_READ_ENGINES 的键）。
SOURCE_OF_TRUTH_CALL = "accepted_data_file_extensions"
#: 回退字面量的主角：这枚后缀一旦以任何形式回到 alerts.py，就说明第三份手抄又长回来了。
LEGACY_EXTENSION = ".xls"
#: 一整枚常量就是一个后缀的形状（".csv" / ".xls"）：散文里提到 .xls 不算，字面量才算。
#: 首字符必须是字母 —— alerts.py 里 `f"{value:.1f}"` 那种格式说明符的片段也是字符串常量，
#: 把它们算进「手抄名单」就是把牙磨平了。
EXTENSION_SHAPE = re.compile(r"^\.[A-Za-z][A-Za-z0-9]{0,4}$")
#: 反证夹具：只在 monkeypatch 期内存在，绝不落盘、绝不进声明表。
BOGUS_EXTENSION = ".r345fake"
BOGUS_ENGINE = "r345_bogus_engine"

CSV_BODY = "store,profit\nwest,42.0\n"


# ==================== 现读工具 ====================


def _tree() -> ast.Module:
    return ast.parse(ALERTS_PY.read_text(encoding="utf-8"))


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1, f"{name} 应当恰好有一处定义，实取 {len(matches)} 处"
    return matches[0]


def _extension_literals(tree: ast.Module) -> list[str]:
    """整棵 AST 里所有「一整枚常量就是一个后缀」的字符串（含 f-string 的片段）。"""
    return sorted(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and EXTENSION_SHAPE.match(node.value)
    )


def _sweep_extensions() -> set[str]:
    from app.api.v1 import alerts

    return {str(ext).lower() for ext in alerts._data_file_extensions()}


def _declared_extensions() -> set[str]:
    from app.tools import excel

    return {str(ext).lower() for ext in excel.accepted_data_file_extensions()}


def _gate_extensions() -> set[str]:
    from app.api.v1 import data

    return {str(ext).lower() for ext in data.DATA_FILE_EXTENSIONS}


# ==================== 判据 ①：第三份手抄必须消失 ====================


def test_no_extension_is_hand_copied_anywhere_in_the_alert_module():
    """全文件扫一遍：alerts.py 里不许再躺着任何一枚后缀字面量。

    这一枚钉抓的不是今天的值，是「下一位又手抄一份」这个动作本身：无论他抄成
    `{".csv", ".xlsx"}` 还是把 `.xls` 请回来，无论写在模块级常量还是函数里的兜底，都当场红。
    """
    literals = _extension_literals(_tree())

    assert literals == [], (
        "app/api/v1/alerts.py 里又出现了后缀字面量 %s：巡检名单只准现读 "
        "app/tools/excel.py::DATA_READ_ENGINES，第二份手抄迟早与读腿各漂各的" % literals
    )


def test_the_sweep_list_is_a_call_on_the_single_source_not_a_literal():
    """写法钉（照 R336 那枚 AST 钉的口径）：名单要从一枚调用现算，不许是字面量。"""
    definition = _function(_tree(), "_data_file_extensions")
    calls = [
        node
        for node in ast.walk(definition)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", getattr(node.func, "attr", "")) == SOURCE_OF_TRUTH_CALL
    ]
    assert calls, (
        "_data_file_extensions 不再调用 %s()：单一事实源在 app/tools/excel.py，这里既不许"
        "手抄，也不许兜一份「反正今天走不到」的字面量" % SOURCE_OF_TRUTH_CALL
    )

    returns = [node for node in ast.walk(definition) if isinstance(node, ast.Return)]
    assert returns, "_data_file_extensions 竟然不回值"
    for container in (ast.Set, ast.List, ast.Tuple, ast.Dict):
        offenders = [
            inner
            for node in returns
            for inner in ast.walk(node)
            if isinstance(inner, container)
        ]
        assert not offenders, (
            "返回值里又出现了 %s 字面量：巡检名单要从真源现算，不许就地写死"
            % container.__name__
        )


def test_the_sweep_and_the_read_leg_and_the_upload_gate_are_one_fact_today():
    """今天的三枚读数：巡检名单、引擎声明表、上传收口闸必须是同一份事实。"""
    assert _sweep_extensions() == _declared_extensions() == _gate_extensions()
    assert LEGACY_EXTENSION not in _sweep_extensions(), (
        ".xls 又回到巡检名单：R336 已经关掉读它的那条腿，扫到它只会被跳过"
    )


# ==================== 判据 ②：能抓「下一位又手抄一份」的牙 ====================


def test_the_sweep_follows_the_declaration_table_when_a_row_is_added(monkeypatch, tmp_path):
    """往声明表加一枚扩展名 ⇒ 巡检名单与 `_directory_data_files` 必须当场跟着动。

    手抄名单在这一把下会红；导入期抄的快照也会红。真源动了它不动，就是两本账。
    """
    from app.api.v1 import alerts
    from app.tools import excel

    (tmp_path / ("ledger" + BOGUS_EXTENSION)).write_text(CSV_BODY, encoding="utf-8")
    (tmp_path / "ledger.csv").write_text(CSV_BODY, encoding="utf-8")
    assert BOGUS_EXTENSION not in _sweep_extensions()

    monkeypatch.setitem(excel.DATA_READ_ENGINES, BOGUS_EXTENSION, BOGUS_ENGINE)

    assert BOGUS_EXTENSION in _sweep_extensions(), (
        "声明表多了一枚扩展名而巡检名单没跟着动：名单是从别处抄来的，不是现读真源"
    )
    swept = sorted(path.name for path in alerts._directory_data_files(tmp_path))
    assert swept == sorted(["ledger" + BOGUS_EXTENSION, "ledger.csv"]), (
        "巡检扫盘那道过滤没跟着真源走：%s" % swept
    )


def test_the_sweep_follows_the_declaration_table_when_a_row_is_removed(monkeypatch, tmp_path):
    """从声明表摘掉 `.csv` ⇒ 巡检当场不再扫 .csv。

    反向那一把才分得清「现读」与「起手抄一份、之后各自漂」：只测增，兜底字面量能蒙过去；
    只测删，导入期快照能蒙过去。两把都要。
    """
    from app.api.v1 import alerts
    from app.tools import excel

    (tmp_path / "ledger.csv").write_text(CSV_BODY, encoding="utf-8")
    (tmp_path / "ledger.xlsx").write_bytes(b"not a workbook")
    assert alerts._directory_data_files(tmp_path), "夹具自己先空了"

    monkeypatch.delitem(excel.DATA_READ_ENGINES, ".csv")

    swept = sorted({path.suffix.lower() for path in alerts._directory_data_files(tmp_path)})
    assert ".csv" not in swept, "真源已经不收 .csv 了，巡检还在按旧名单扫它"
    assert swept == [".xlsx"], swept


def test_every_extension_the_sweep_scans_is_one_the_read_leg_opens():
    """通用尺子（借 R336 那把）：巡检扫到的每一枚后缀，`load_excel` 都得真打得开。

    「白名单指着一条死路」正是 `.xls` 那次的病根。这一枚量的是机制不是今天的值：下一位
    往声明表塞一枚装不上引擎的格式，收口闸那头红（R336），这条巡检腿上同样红。
    """
    from app.tools import excel

    for ext in sorted(_sweep_extensions()):
        assert excel.refuse_data_file("ledger" + ext) is None, (
            "巡检要扫 %s，可读腿却拒它：两本账又分家了" % ext
        )


# ==================== 反证（判据写得对不对的镜像） ====================


def test_refutation_the_old_hand_copied_fallback_would_go_red():
    """旧实现那一份兜底字面量喂给同一把尺子，字面量扫描与写法扫描两枚都必须响。

    真·反证由总控在盘上改文件实跑（测试自己不许改写被跟踪的源文件，见
    tests/test_r253_no_test_rewrites_a_tracked_file.py）；这一枚钉的是牙本身：
    它证明上面两枚判据不是只对着今天的值念一遍，而是能认出那个形状。
    """
    old_leg = ast.parse(
        "def _data_file_extensions() -> set[str]:\n"
        '    extensions = getattr(_data_api_module(), "DATA_FILE_EXTENSIONS", None)\n'
        '    return {str(ext).lower() for ext in (extensions or {".csv", ".xlsx", ".xls"})}\n'
    )
    copied = _extension_literals(old_leg)
    assert copied == [".csv", ".xls", ".xlsx"], "反证夹具自己坏了：%s" % copied
    assert LEGACY_EXTENSION in copied, "兜底字面量里竟然没有 .xls：这一把抓不到本单的病"

    # 写法那一枚钉也对得上：旧那一支的返回值里躺着 ast.Set。
    returns = [
        node
        for node in ast.walk(_function(old_leg, "_data_file_extensions"))
        if isinstance(node, ast.Return)
    ]
    assert any(
        isinstance(inner, ast.Set) for node in returns for inner in ast.walk(node)
    ), "ast.Set 认不出花括号字面量：写法那一枚钉是空牙"

    # 正证：今天的 alerts.py 里这两样都没有。
    assert _extension_literals(_tree()) == []
    assert LEGACY_EXTENSION not in _sweep_extensions()
