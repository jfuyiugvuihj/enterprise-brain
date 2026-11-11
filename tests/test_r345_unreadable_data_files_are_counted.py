"""R345 · 读不开的那一份数据，不许再被伪装成「没有异常」。

症状（总控在基点实测，不是推测）：`app/api/v1/alerts.py::evaluate_all` 里那句

    except Exception:
        continue

把任何一次读盘失败咽了下去：不告警、不记因、`scan_summary` 也不提。异常被吞掉之后，
「这个月没有异常」与「这个月的数据一个都读不出来」在屏上是同一张脸 —— 读不到被伪装成零，
正是本仓最忌的那类病。R336 并完之后的那条尾巴就落在这里：租户 DATA_DIR 里留下的 `.xls`
（读腿已被 R336 关掉，`load_excel` 现在先吐 `UnsupportedDataFile`）会一声不响地消失。

本件钉三件事（判据 ③ 的三格），一件都不许只是注释：
  (a) 不吞栈：`logger.warning(..., exc_info=True)`，说清是哪一份文件、什么异常类；
  (b) `scan_summary` 长出「评估了几份 / 跳了几份 / 为什么」：`evaluated_files` 收窄成
      「真读进来并真拿去判定了的那些」，另加 `unreadable_files`（每格只有文件名 + 异常类名）；
  (c) 一份都没读成功时，结果面不许长得像「一切正常」：`reason` 换成 `all_data_files_unreadable`，
      与 `no_data_files`（目录里真的没有文件）分家。

判据 ④/⑤/⑥ 一并钉住：判定语义（规则、阈值、落章部门、行级 scope）一字未动；新词只是内部
摘要，不是对外错误码；摘要里只许出现文件名，不许出现服务端路径。

全部离线：不起服务、不连库、不打模型；夹具坐在 `tmp_path` + 文件形态的登记表上。
"""
from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path
from typing import get_args

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
ALERTS_PY = ROOT / "app" / "api" / "v1" / "alerts.py"

DEPT = "r345-finance"
OWNER = "r345-manager"
GOOD_CSV = "east.csv"
BROKEN_XLSX = "broken.xlsx"
EMPTY_CSV = "empty.csv"
LEGACY_XLS = "legacy-book.xls"

#: 一份真 .xls 的开头：Excel 97-2003 是 OLE2 复合文档（照 R336 那份夹具）。
LEGACY_XLS_BYTES = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512

#: 摘要里那一格的名字，以及只准出现在摘要里的内部词。
ALL_UNREADABLE = "all_data_files_unreadable"
SUMMARY_COUNT_KEYS = ("evaluated_files", "unreadable_files")


def _rule(rule_id=7, name="profit-floor", metric="profit", op="gt", threshold=1.0):
    return {
        "id": rule_id,
        "name": name,
        "metric": metric,
        "op": op,
        "threshold": threshold,
        "enabled": True,
    }


def _account(username: str, department: str = DEPT) -> dict[str, str]:
    return {"id": username, "username": username, "role": "manager", "department": department}


def _principal(username: str = OWNER, department: str = DEPT):
    from app.agents.contracts import Principal

    return Principal.from_user(_account(username, department))


def _headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": "Bearer %s" % create_token(username)}


def _csv(directory: Path, name: str, profit: float) -> Path:
    path = directory / name
    path.write_text("store,profit\nwest,%.2f\n" % profit, encoding="utf-8")
    return path


def _broken_xlsx(directory: Path, name: str = BROKEN_XLSX) -> Path:
    """后缀是 .xlsx、内容不是 zip：openpyxl 会 BadZipFile（伪装后缀那一族的今天形态）。"""
    path = directory / name
    path.write_text("this is not a workbook", encoding="utf-8")
    return path


def _empty_csv(directory: Path, name: str = EMPTY_CSV) -> Path:
    """零字节 CSV：pandas 报 EmptyDataError。真实客户目录里就有这一份（传了一半的导出）。"""
    path = directory / name
    path.write_bytes(b"")
    return path


@pytest.fixture()
def sweep(monkeypatch, tmp_path):
    """租户 DATA_DIR + 登记表 + 内存规则：整条巡检在离线态跑完，一条真库连接都不发。"""
    from app.api.v1 import alerts, data
    from app.storage import datasets as dataset_storage
    from app.storage.datasets import DatasetRegistry

    root = tmp_path / "tenant-data"
    root.mkdir()
    registry = DatasetRegistry(root=root, metadata_path=root / ".dataset-metadata.json")
    monkeypatch.setattr(dataset_storage, "dataset_registry", registry)
    monkeypatch.setattr(data, "DATA_DIR", str(root))
    monkeypatch.setattr(alerts, "_database_available", lambda: False)
    monkeypatch.setattr(alerts, "_MEM_RULES", [dict(_rule())])
    monkeypatch.setattr(alerts, "_MEM_ALERTS", [])
    monkeypatch.setattr(alerts, "_ai_analysis", lambda rule, value: "r345 analysis")
    monkeypatch.setattr(alerts, "send_im_notification", lambda *a, **k: True)
    return alerts, root, registry


def _skipped_names(summary: dict) -> dict[str, str]:
    return {row["filename"]: row["error"] for row in summary.get("unreadable_files", [])}


# ==================== 判据 ③(b)：跳了几份、为什么，要长在摘要里 ====================


def test_a_file_that_cannot_be_read_is_named_instead_of_vanishing(sweep):
    """一份读不开的文件必须在摘要里点名，并带着异常类名。"""
    alerts, root, _ = sweep
    _csv(root, GOOD_CSV, 42.0)
    _broken_xlsx(root)

    summary: dict = {}
    triggered = alerts.evaluate_all(scan_summary=summary)

    assert [item["message"] for item in triggered] == ["profit-floor: profit=42.0 (gt 1.0)"]
    assert summary["evaluated_files"] == [GOOD_CSV]
    assert _skipped_names(summary) == {BROKEN_XLSX: "BadZipFile"}
    # 还读得起来一份：这一格就不是「一份都没读成功」，不许抢答那个词。
    assert summary["reason"] == ""


def test_the_summary_counts_read_and_skipped(sweep):
    """「评估了几份 / 跳了几份」两格相加必须等于扫到的份数，不许漏记也不许重记。"""
    alerts, root, _ = sweep
    _csv(root, GOOD_CSV, 42.0)
    _csv(root, "west.csv", 30.0)
    _broken_xlsx(root)
    _empty_csv(root)

    summary: dict = {}
    alerts.evaluate_all(scan_summary=summary)

    assert sorted(summary["evaluated_files"]) == ["east.csv", "west.csv"]
    assert sorted(_skipped_names(summary)) == [BROKEN_XLSX, EMPTY_CSV]
    assert _skipped_names(summary) == {BROKEN_XLSX: "BadZipFile", EMPTY_CSV: "EmptyDataError"}
    assert len(summary["evaluated_files"]) + len(summary["unreadable_files"]) == 4


# ==================== 判据 ③(c)：一份都没读成功 ≠ 一切正常 ====================


def test_every_file_unreadable_is_not_reported_as_an_all_clear(sweep):
    """本单最硬的一格：有文件、但一份都没读成功时，结果面不许像「没有异常」。

    旧实现下这一把必红：`reason` 是空串、`evaluated_files` 还留着两份根本没读进来的文件名，
    前端拿到的就是「本轮按 2 个数据文件判定，没有任何一条规则被触发」——一句假话。
    """
    alerts, root, _ = sweep
    _broken_xlsx(root)
    _empty_csv(root)

    summary: dict = {}
    triggered = alerts.evaluate_all(scan_summary=summary)

    assert triggered == []
    assert alerts._MEM_ALERTS == [], "读不出来的数据不许凭空落一条告警"
    assert summary["data_dir_configured"] is True, "目录是在的：这一格不是「没配置」"
    assert summary["evaluated_files"] == []
    assert summary["reason"] == ALL_UNREADABLE
    assert sorted(_skipped_names(summary)) == [BROKEN_XLSX, EMPTY_CSV]
    # 「读不到」与「没有数据」必须是两句话：不许复用 no_data_files 那一格糊过去。
    assert summary["reason"] != "no_data_files"


def test_the_check_route_does_not_render_an_all_clear_when_nothing_was_read(sweep, monkeypatch):
    """端到端同一格：POST /alerts/check 的 scan_scope 必须把这一次说成一次没做成的巡检。

    这一把走真路由（客户在屏上看见的就是这一格）：登记一份 `.xls` —— 字节在、权限在、
    读腿被 R336 关掉 —— 旧口径下它无声消失，回执读起来就是「没有异常」。
    """
    from app.common import auth
    from app.main import app

    _alerts, root, registry = sweep
    legacy = root / LEGACY_XLS
    legacy.write_bytes(LEGACY_XLS_BYTES)
    registry.register(legacy, principal=_principal(), filename=LEGACY_XLS)
    monkeypatch.setattr(auth, "get_user", lambda username: _account(username))

    response = TestClient(app).post("/api/v1/alerts/check", headers=_headers(OWNER))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["triggered"] == []
    scope = body["scan_scope"]
    assert scope["reason"] == ALL_UNREADABLE
    assert scope["evaluated_files"] == []
    assert _skipped_names(scope) == {LEGACY_XLS: "UnsupportedDataFile"}


def test_a_readable_sibling_still_carries_the_legacy_xls_by_name(sweep):
    """混合现场：能读的那一份照旧判定，读不出来的那一份被点名，两格各归各。"""
    from app.api.v1 import alerts

    _alerts, root, registry = sweep
    _csv(root, GOOD_CSV, 42.0)
    legacy = root / LEGACY_XLS
    legacy.write_bytes(LEGACY_XLS_BYTES)
    keeper = _principal()
    registry.register(legacy, principal=keeper, filename=LEGACY_XLS)
    registry.register(root / GOOD_CSV, principal=keeper, filename=GOOD_CSV)

    summary: dict = {}
    triggered = alerts.evaluate_all(principal=keeper, scan_summary=summary)

    assert [item["message"] for item in triggered] == ["profit-floor: profit=42.0 (gt 1.0)"]
    assert summary["evaluated_files"] == [GOOD_CSV]
    assert _skipped_names(summary) == {LEGACY_XLS: "UnsupportedDataFile"}


# ==================== 判据 ③(a)：不吞栈 ====================


def test_the_read_failure_is_logged_with_the_file_and_the_exception_class(sweep, caplog):
    """日志必须说清是哪一份文件、什么异常类，并且带着栈。"""
    alerts, root, _ = sweep
    _broken_xlsx(root)
    caplog.set_level(logging.WARNING, logger="enterprise_brain")

    alerts.evaluate_all()

    hits = [row for row in caplog.records if BROKEN_XLSX in row.getMessage()]
    assert hits, "读不开的那一份文件没有在本轮日志里点名：%s" % [
        row.getMessage() for row in caplog.records
    ]
    assert any("BadZipFile" in row.getMessage() for row in hits), hits
    assert any(row.exc_info for row in hits), "只记了一句话就把栈吞了"


def test_the_daily_report_leg_no_longer_swallows_the_stack(tmp_path, monkeypatch, caplog):
    """`daily_report` 里同一形状的 `except Exception: continue` 也不再一声不响。

    日报的文案一个字没改（那是另一枚单的口径），改的只是「少了一份数据」这件事要留在日志里。
    """
    from app.api.v1 import alerts, data

    root = tmp_path / "tenant-data"
    root.mkdir()
    _csv(root, GOOD_CSV, 42.0)
    _broken_xlsx(root)
    monkeypatch.setattr(data, "DATA_DIR", str(root))
    monkeypatch.setattr(alerts, "send_im_notification", lambda *a, **k: True)
    caplog.set_level(logging.WARNING, logger="enterprise_brain")

    text = alerts.daily_report()

    assert "日报" in text
    assert GOOD_CSV in text, "能读的那一份照旧进日报"
    hits = [row for row in caplog.records if BROKEN_XLSX in row.getMessage()]
    assert hits and any(row.exc_info for row in hits), "日报那条腿还在咽栈"


# ==================== 判据 ⑥：摘要里不许有服务端路径 ====================


def test_no_server_side_path_leaks_into_the_summary(sweep, monkeypatch):
    """异常文本里带着绝对路径时，摘要仍然只许有文件名与异常类名。

    `str(exc)` 是服务端的东西（`FileNotFoundError` 就把整条路径写进 message），而 `scan_scope`
    要出网：客户看得见的是文件名，同 `_scan_data_files` 只放 `path.name` 那一条理由。
    """
    alerts, root, _ = sweep
    _csv(root, GOOD_CSV, 42.0)

    def exploding_load(path: str):
        raise FileNotFoundError(2, "No such file or directory", path)

    monkeypatch.setattr("app.tools.excel.load_excel", exploding_load)

    summary: dict = {}
    alerts.evaluate_all(scan_summary=summary)

    blob = json.dumps(summary, ensure_ascii=False)
    forbidden = {
        str(root),
        str(root).replace("\\", "/"),
        root.name,
        root.parent.name,
    }
    for spelling in sorted(forbidden):
        assert spelling and spelling not in blob, "服务端路径漏进了摘要：%s" % spelling
    assert _skipped_names(summary) == {GOOD_CSV: "FileNotFoundError"}
    for row in summary["unreadable_files"]:
        assert not re.search(r"[\\/]", row["filename"]), row
        assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", row["error"]), row


# ==================== 判据 ④/⑤：判定语义不动、不新增错误码 ====================


def test_the_counting_cells_are_not_invented_when_nothing_was_found(tmp_path, monkeypatch):
    """一份都没扫到时，不许替摘要编一个假的 `unreadable_files`。

    那三格（`tenant_data_dir_unavailable` / `no_data_files` / `no_permitted_datasets`）已经把
    「没有东西可读」说完了；计数格只属于真发生过读取尝试的那一支。
    """
    from app.api.v1 import alerts, data
    from app.storage import datasets as dataset_storage
    from app.storage.datasets import DatasetRegistry

    root = tmp_path / "tenant-data"
    root.mkdir()
    registry = DatasetRegistry(root=root, metadata_path=root / ".dataset-metadata.json")
    monkeypatch.setattr(dataset_storage, "dataset_registry", registry)
    monkeypatch.setattr(data, "DATA_DIR", str(root))
    monkeypatch.setattr(alerts, "_database_available", lambda: False)
    monkeypatch.setattr(alerts, "_MEM_RULES", [dict(_rule())])
    monkeypatch.setattr(alerts, "_MEM_ALERTS", [])

    summary: dict = {}
    assert alerts.evaluate_all(scan_summary=summary) == []

    assert summary["reason"] == "no_data_files"
    assert summary["evaluated_files"] == []
    assert not any(key in summary for key in SUMMARY_COUNT_KEYS if key != "evaluated_files"), (
        "没发生过任何读取尝试，却长出了计数格：%s" % sorted(summary)
    )


def test_the_rule_hit_and_the_department_stamp_are_untouched_by_the_new_cell(sweep):
    """判据 ④：新增的只是「读不到」那一格，判定与落章一个字没改。"""
    from app.api.v1 import alerts

    _alerts, root, registry = sweep
    _csv(root, GOOD_CSV, 42.0)
    _broken_xlsx(root)
    keeper = _principal()
    registry.register(root / GOOD_CSV, principal=keeper, filename=GOOD_CSV)

    alerts.evaluate_all(principal=keeper)

    recorded = alerts._MEM_ALERTS
    assert [row["message"] for row in recorded] == ["profit-floor: profit=42.0 (gt 1.0)"]
    assert [row["rule_id"] for row in recorded] == [7]
    assert [row["department"] for row in recorded] == [DEPT], "落章部门被这单碰动了"


def test_the_new_reason_word_is_an_internal_summary_word_not_an_error_code():
    """判据 ⑤：`all_data_files_unreadable` 只活在 scan_summary 里，不进错误码表。

    两把扫描器（test_r142_error_code_table_sync / test_error_code_vocabulary）钉的是
    `HTTPException(detail=...)`；这一枚钉把意图写在原地：它是一格内部摘要，不是一张对外新码。
    """
    from app.agents.contracts import ErrorEnvelope

    tree = ast.parse(ALERTS_PY.read_text(encoding="utf-8"))
    assigned = {
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == "ALL_DATA_FILES_UNREADABLE"
    }
    assert assigned == {ALL_UNREADABLE}, "那枚词不是在模块里写死的一处：%s" % assigned

    details = [
        keyword.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "HTTPException"
        for keyword in node.keywords
        if keyword.arg == "detail"
        and isinstance(keyword.value, ast.Constant)
        and isinstance(keyword.value.value, str)
    ]
    assert ALL_UNREADABLE not in details, "内部摘要词被接成了对外 detail"
    enum_codes = set(get_args(ErrorEnvelope.model_fields["code"].annotation))
    assert enum_codes, "封闭枚举读空了：这一枚钉会空响"
    assert ALL_UNREADABLE not in enum_codes, "本单不许新增错误码"


def test_evaluate_all_never_raises_when_a_file_explodes(sweep, monkeypatch):
    """把读腿换成必炸：巡检要照常返回，不许把异常顶穿路由（旧行为保留，只是不再无声）。"""
    from app.api.v1 import alerts

    _alerts, root, _ = sweep
    _csv(root, GOOD_CSV, 42.0)

    def exploding_load(path: str):
        raise ValueError("boom")

    monkeypatch.setattr("app.tools.excel.load_excel", exploding_load)

    summary: dict = {}
    assert alerts.evaluate_all(scan_summary=summary) == []
    assert summary["unreadable_files"] == [{"filename": GOOD_CSV, "error": "ValueError"}]
    assert summary["reason"] == ALL_UNREADABLE


def test_the_old_bare_continue_is_gone_from_the_sweep():
    """写法钉：`evaluate_all` 里那一句裸的 `except Exception: continue` 不许再回来。

    「异常体里只做 continue」就是这一格的形状本身：它不记名、不记因、不碰摘要。判据 ③
    的三格只要有人退回旧写法，`unreadable.append(...)` 那一行会先消失，这一枚当场红。
    """
    tree = ast.parse(ALERTS_PY.read_text(encoding="utf-8"))
    definition = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "evaluate_all"
    )
    swallowed = [
        node
        for node in ast.walk(definition)
        if isinstance(node, ast.ExceptHandler)
        and all(isinstance(stmt, ast.Continue) for stmt in node.body)
    ]
    assert swallowed == [], (
        "evaluate_all 里又出现了只写 continue 的 except 分支：读不到的那一份必须被点名"
    )
    assert any(
        isinstance(node, ast.Name) and node.id == "unreadable" for node in ast.walk(definition)
    ), "evaluate_all 不再统计读不开的份数"
