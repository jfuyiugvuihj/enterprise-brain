"""Current-principal rechecks inside analysis, query and retrieval tools."""
import threading
from types import SimpleNamespace

import pytest
from test_r462_query_data_tuple_keys import query_files
from test_alert_scan_scope import alert_pg

from app.agents import tools
from app.agents.orchestrator import RequestCancelled


def _run_for(config, operation):
    from app.storage.calculations import calculation_storage
    conf = config["configurable"]
    rows = calculation_storage.list_for(
        conf["principal"], request_id=conf["request_id"], limit=100
    )
    return next(row for row in rows
                if row["parameters"].get("operation") == operation)


def test_analyze_data_stops_before_completion_when_principal_changes(
    query_files, monkeypatch,
):
    config = query_files
    original = tools._tool_principal
    calls = 0

    def changing_principal(value):
        nonlocal calls
        calls += 1
        if calls >= 4:
            raise PermissionError("permission_denied: controlled change")
        return original(value)

    monkeypatch.setattr(tools, "_tool_principal", changing_principal)
    answer = tools._analyze_data("各区域销售额合计", config)
    assert answer == tools._CURRENT_ACCESS_DENIED_TEXT
    row = _run_for(config, "analyze_data")
    assert (row["status"], row["error_code"]) == ("failed", "permission_denied")


def test_query_data_cancelled_after_sandbox_propagates_and_fails_calculation(
    query_files, monkeypatch,
):
    from app.tools import excel

    config = query_files
    marker = threading.Event()
    config["configurable"]["cancel_event"] = marker
    real_safe_query = excel.safe_query

    def cancel_after_query(*args, **kwargs):
        result = real_safe_query(*args, **kwargs)
        marker.set()
        return result

    monkeypatch.setattr(excel, "safe_query", cancel_after_query)
    monkeypatch.setattr(
        tools, "_llm_pandas_code",
        lambda _df, _query: "df['销售额'].sum()",
    )
    with pytest.raises(RequestCancelled):
        tools._query_data("各区域销售额合计", config)
    row = _run_for(config, "query_data")
    assert (row["status"], row["error_code"]) == ("failed", "task_cancelled")


def test_search_docs_rechecks_before_using_returned_passages(
    query_files, monkeypatch,
):
    config = query_files
    original = tools._tool_principal
    calls = 0

    def changing_principal(value):
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise PermissionError("permission_denied: controlled change")
        return original(value)

    class Pipeline:
        def search_for_principal(self, *_args, **_kwargs):
            return ([{"source": "合成制度.md", "content": "不能交付的越权正文"}], [])

    monkeypatch.setattr(tools, "_tool_principal", changing_principal)
    monkeypatch.setattr(tools, "_get_pipeline", lambda: Pipeline())
    answer = tools.search_docs.invoke({"query": "制度"}, config=config)
    assert answer == tools._CURRENT_ACCESS_DENIED_TEXT
    statuses = tools.bag_from_config(config)["tool_statuses"]
    assert statuses[-1]["error_code"] == "permission_denied"
