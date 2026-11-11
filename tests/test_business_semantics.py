"""Metric definitions: the table is authoritative, the code rules are the fallback.

Everything here is offline. The connection factory of app/semantics/registry.py is
replaced by a stand-in that honours the UNIQUE constraint of metric_definitions
(migrations/0002_execution_data_lineage.sql:72), so read precedence, the idempotency of
the sync path, and the "adding a metric needs no code change" claim are all exercised
without PostgreSQL, Redis or Ollama.
"""
from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.common.auth import create_token
from app.main import app
from app.semantics import registry
from app.semantics.registry import DEFINITION_VERSION, match_metric_context

ROOT = Path(__file__).resolve().parents[1]
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)

_CODE_WARNING = "定义来自代码语义注册表，未与已上传制度文件核对"
_TABLE_WARNING = "定义来自指标定义表 metric_definitions，未与已上传制度文件核对"

client = TestClient(app)


def _headers(username: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(username)}"}


def _row(
    metric_id: str = "expense.training",
    *,
    definition_version: str = "finance-2026q3-v1",
    formula: str = "培训费合计",
    unit: str = "元",
    period_type: str = "month",
    currency: str | None = "CNY",
    status: str = "active",
    owner_id: str | None = None,
    definition_id: str | None = None,
    metric_name: str | None = "培训费",
    definition_text: str | None = "员工培训发生的费用",
    match_terms: tuple[str, ...] | None = ("培训费", "培训费用"),
    time_granularity: str | None = "月",
    origin: str | None = "operator",
    extra_filters: dict | None = None,
    source_scope: list | None = None,
    created_at: datetime | None = None,
) -> dict:
    """One metric_definitions row, spelled with the columns migration 0002 declares."""
    semantics: dict = {}
    for key, value in (
        ("metric_name", metric_name),
        ("definition_text", definition_text),
        ("time_granularity", time_granularity),
        ("origin", origin),
    ):
        if value is not None:
            semantics[key] = value
    if match_terms is not None:
        semantics["match_terms"] = list(match_terms)
    filters = dict(extra_filters or {})
    if semantics:
        filters[registry.SEMANTICS_KEY] = semantics
    return {
        "metric_definition_id": definition_id
        or f"md:{owner_id or registry.SYSTEM_OWNER_ID}:{metric_id}:{definition_version}",
        "owner_id": owner_id or registry.SYSTEM_OWNER_ID,
        "metric_id": metric_id,
        "definition_version": definition_version,
        "formula": formula,
        "unit": unit,
        "currency": currency,
        "period_type": period_type,
        "timezone": "Asia/Shanghai",
        "source_scope": source_scope if source_scope is not None else [],
        "filters": filters,
        "status": status,
        "created_at": created_at,
    }


class MetricDefinitionStore:
    """Stand-in for PostgreSQL: it knows the two statements the registry uses."""

    def __init__(self, rows: list[dict] | None = None):
        self.rows = [dict(row) for row in rows or []]
        self.statements: list[tuple[str, tuple]] = []
        self.commits = 0
        self.rollbacks = 0
        self.rowcount = 0
        self._fetched: list[dict] = []
        self._insert_seq = 0

    def execute(self, sql, params=None):
        values = tuple(params or ())
        self.statements.append((sql, values))
        statement = " ".join(sql.split()).lower()
        if statement.startswith("select"):
            owners = set(values)
            self._fetched = sorted(
                (row for row in self.rows if row["owner_id"] in owners),
                key=lambda row: (
                    row.get("created_at") or _EPOCH,
                    str(row.get("metric_definition_id") or ""),
                ),
            )
            self.rowcount = len(self._fetched)
        elif statement.startswith("insert"):
            self._insert(statement, dict(zip(registry._INSERT_COLUMNS, values)))
        else:
            raise AssertionError(f"unexpected statement: {sql}")
        return self

    def _insert(self, statement: str, values: dict) -> None:
        clash = next(
            (
                row
                for row in self.rows
                if all(str(row.get(column)) == str(values.get(column)) for column in registry._UNIQUE_COLUMNS)
            ),
            None,
        )
        if clash is None:
            # NOW() DEFAULT, plus the column this stand-in is asked to keep.
            self._insert_seq += 1
            values["created_at"] = _BASE_TIME + timedelta(minutes=self._insert_seq)
            self.rows.append(values)
            written, is_new = values, True
        elif "do update" in statement:
            for column in registry._INSERT_COLUMNS:
                if column not in registry._IMMUTABLE_COLUMNS:
                    clash[column] = values[column]
            written, is_new = clash, False
        else:
            # ON CONFLICT DO NOTHING affects no row, so RETURNING comes back empty.
            self.rowcount = 0
            self._fetched = []
            return
        self.rowcount = 1
        returned = {"metric_definition_id": written["metric_definition_id"]}
        if "as is_new" in statement:
            returned["is_new"] = is_new
        self._fetched = [returned]

    def fetchone(self):
        return copy.deepcopy(self._fetched[0]) if self._fetched else None

    def fetchall(self):
        return copy.deepcopy(self._fetched)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        return None

    def row_ids(self, metric_id: str) -> list[str]:
        return [row["metric_definition_id"] for row in self.rows if row["metric_id"] == metric_id]


def _never_connect():
    raise AssertionError("the registry must not open a connection on this path")


@pytest.fixture
def store(monkeypatch):
    """A readable and writable metric_definitions table with no PostgreSQL behind it."""
    fake = MetricDefinitionStore()
    monkeypatch.setattr(registry, "_database_available", lambda: True)
    monkeypatch.setattr(registry, "_conn", lambda: fake)
    return fake


@pytest.fixture
def offline(monkeypatch):
    """The no-database deployment: fallback rules only, and no connection attempts."""
    monkeypatch.setattr(registry, "_database_available", lambda: False)
    monkeypatch.setattr(registry, "_conn", _never_connect)


def test_metric_matching_handles_different_business_phrases(offline):
    context = match_metric_context("分析差旅费用并判断是否超标")
    assert context is not None
    assert context.metric_name in {"住宿费标准", "差旅费"}


def test_metric_matching_returns_none_for_unrelated_questions(offline):
    assert match_metric_context("今天天气怎么样？") is None


def test_table_rows_and_code_fallback_report_different_versions(store):
    store.rows = [_row()]

    from_table = registry.match_definition("今年培训费用是多少")
    assert from_table is not None
    assert from_table.source == registry.SOURCE_TABLE
    assert from_table.definition_version == "finance-2026q3-v1"
    assert from_table.to_context().warnings == [_TABLE_WARNING]

    from_code = registry.match_definition("本月住宿费标准是多少？")
    assert from_code is not None
    assert from_code.source == registry.SOURCE_CODE
    assert from_code.definition_version == DEFINITION_VERSION
    assert from_code.to_context().warnings == [_CODE_WARNING]


def test_a_row_added_without_touching_code_is_matched(store):
    assert match_metric_context("今年培训费用是多少") is None

    store.rows = [_row()]

    context = match_metric_context("今年培训费用是多少")
    assert context is not None
    assert context.metric_id == "expense.training"
    assert context.metric_name == "培训费"
    assert context.definition_version == "finance-2026q3-v1"
    assert context.unit == "元"
    assert context.period_type == "month"


def test_a_bare_row_is_matched_from_the_wording_it_carries(store):
    """No match_terms, no metadata: metric_id and formula are still enough."""
    store.rows = [
        _row(
            "收入.销售额",
            metric_name=None,
            definition_text=None,
            match_terms=None,
            time_granularity=None,
            origin=None,
            formula="销售额合计",
        )
    ]

    definition = registry.match_definition("上月销售额是多少")

    assert definition is not None
    assert definition.metric_id == "收入.销售额"
    assert definition.metric_name == "销售额"
    assert definition.origin == registry.SOURCE_TABLE


def test_a_table_row_replaces_the_code_rule_for_the_same_metric(store):
    store.rows = [
        _row(
            "expense.accommodation.standard",
            definition_version="policy-2025-v3",
            metric_name="住宿费标准",
            definition_text="2025 版制度规定的单晚上限",
            formula="单晚住宿 <= 500",
            unit="元/晚",
            period_type="single",
            match_terms=("住宿费",),
            time_granularity="单笔",
        )
    ]

    context = match_metric_context("本月住宿费标准是多少？")

    assert context is not None
    assert context.definition_version == "policy-2025-v3"
    assert context.definition == "2025 版制度规定的单晚上限"
    assert "代码语义注册表" not in "".join(context.warnings)

    catalog = registry.metric_catalog()
    by_metric = {item["metric_id"]: item for item in catalog["metrics"]}
    assert by_metric["expense.accommodation.standard"]["definition_version"] == "policy-2025-v3"
    # An untouched metric keeps answering from the code rules, side by side.
    assert by_metric["expense.travel.total"]["provenance"]["source"] == registry.SOURCE_CODE
    assert catalog["definition_sources"] == {registry.SOURCE_TABLE: 1, registry.SOURCE_CODE: 1}


def test_a_deprecated_row_retires_the_metric_instead_of_falling_back(store):
    store.rows = [_row("expense.travel.total", match_terms=("差旅费",), status="deprecated")]

    catalog = registry.metric_catalog()

    assert "expense.travel.total" not in {item["metric_id"] for item in catalog["metrics"]}
    matched = registry.match_definition("分析差旅费用并判断是否超标")
    assert matched is None or matched.metric_id != "expense.travel.total"


def test_a_newer_definition_version_wins_within_one_metric(store):
    store.rows = [
        _row(definition_version="finance-2025q1-v1", definition_text="旧口径", created_at=_BASE_TIME),
        _row(definition_version="finance-2026q3-v1", definition_text="新口径", created_at=_BASE_TIME + timedelta(days=200)),
    ]

    definition = registry.match_definition("今年培训费用是多少")

    assert definition.definition_version == "finance-2026q3-v1"
    assert definition.definition == "新口径"


def test_the_owners_own_row_beats_the_shared_one(store):
    store.rows = [
        _row(definition_version="shared-v1", definition_text="全员口径"),
        _row(
            owner_id="7",
            definition_version="own-v1",
            definition_text="本部门口径",
            created_at=_BASE_TIME - timedelta(days=1),
        ),
    ]

    assert registry.match_definition("今年培训费用是多少", owner_id="7").definition_version == "own-v1"
    assert registry.match_definition("今年培训费用是多少").definition_version == "shared-v1"


def test_an_empty_table_falls_back_to_the_code_rules(store):
    assert store.rows == []

    context = match_metric_context("本月住宿费标准是多少？")

    assert context is not None
    assert context.definition_version == DEFINITION_VERSION
    assert context.warnings == [_CODE_WARNING]


def test_a_missing_database_keeps_the_same_fallback_and_warning(offline):
    context = match_metric_context("本月住宿费标准是多少？")

    assert context is not None
    assert context.definition_version == DEFINITION_VERSION
    assert context.warnings == [_CODE_WARNING]

    catalog = registry.metric_catalog()
    assert catalog["database_available"] is False
    assert catalog["definition_sources"] == {registry.SOURCE_TABLE: 0, registry.SOURCE_CODE: 2}
    assert catalog["verified_against_documents"] is False
    assert catalog["warnings"] == [_CODE_WARNING]


def test_rows_are_read_whether_the_driver_returns_json_or_text(store):
    row = _row(source_scope=["dataset:expenses"])
    row["filters"] = json.dumps(row["filters"], ensure_ascii=False)
    row["source_scope"] = json.dumps(row["source_scope"], ensure_ascii=False)
    store.rows = [row]

    definition = registry.match_definition("今年培训费用是多少")

    assert definition.source_scope == ("dataset:expenses",)
    assert list(definition.match_terms) == ["培训费", "培训费用"]


def test_the_reserved_semantics_key_never_leaks_into_filters(store):
    store.rows = [_row(extra_filters={"department": "销售部"})]

    definition = registry.match_definition("今年培训费用是多少")

    assert definition.filters == {"department": "销售部"}
    assert registry.SEMANTICS_KEY not in definition.to_public()["filters"]


def test_sync_seeds_the_catalog_once_and_never_clobbers_curation(store):
    first = registry.sync_code_definitions()

    assert first["database_available"] is True
    assert first["total"] == len(registry.code_metric_ids()) == 2
    assert first["inserted"] == 2 and first["failed"] == 0 and first["unchanged"] == 0
    assert {row["metric_id"] for row in store.rows} == set(registry.code_metric_ids())
    # The JSONB columns are sent as JSON text, the way every other writer in this
    # project does it, so the stored parameter is checked as text.
    seeded = json.loads(store.rows[0]["filters"])[registry.SEMANTICS_KEY]
    assert seeded["origin"] == registry.SOURCE_CODE
    assert seeded["metric_name"] == "住宿费标准"
    assert "住宿费" in seeded["match_terms"]

    # A seeded row is table-backed but still says where it came from: three distinct
    # provenance messages, never a claim that somebody checked a policy document.
    after_sync = registry.match_definition("本月住宿费标准是多少？")
    assert after_sync.source == registry.SOURCE_TABLE
    assert after_sync.warnings == ("定义由代码语义注册表同步进 metric_definitions，未与已上传制度文件核对",)
    assert after_sync.to_public()["provenance"]["origin"] == registry.SOURCE_CODE

    second = registry.sync_code_definitions()

    assert second["inserted"] == 0 and second["unchanged"] == 2
    assert len(store.rows) == 2, "a re-sync must not duplicate the catalog"

    curated = _row(
        "expense.travel.total",
        definition_version="policy-2026-v9",
        formula="差旅费含税费",
        match_terms=("差旅费",),
        created_at=_BASE_TIME + timedelta(days=400),
    )
    store.rows.append(curated)
    registry.sync_code_definitions()

    assert curated["formula"] == "差旅费含税费", "the re-sync rewrote a curated row"
    travel = registry.match_definition("分析差旅费用并判断是否超标")
    assert travel is not None and travel.metric_id == "expense.accommodation.standard"
    assert [row["definition_version"] for row in store.rows if row["metric_id"] == "expense.travel.total"] == [
        DEFINITION_VERSION,
        "policy-2026-v9",
    ]


def test_register_metric_definition_writes_a_row_the_matcher_then_uses(store):
    result = registry.register_metric_definition(
        metric_id="expense.meeting",
        definition_version="ops-2026-v1",
        formula="会议费合计",
        unit="元",
        period_type="month",
        metric_name="会议费",
        definition_text="会议室与设备费用",
        match_terms=("会议费",),
    )

    assert result["result"] == "inserted"
    assert result["definition"]["provenance"]["source"] == registry.SOURCE_TABLE

    context = match_metric_context("上个月会议费是多少")

    assert context is not None
    assert context.definition_version == "ops-2026-v1"
    assert context.definition == "会议室与设备费用"
    assert context.warnings == [_TABLE_WARNING]


def test_revising_a_definition_updates_the_row_it_already_owns(store):
    arguments = dict(
        metric_id="expense.meeting",
        definition_version="ops-2026-v1",
        unit="元",
        period_type="month",
        match_terms=("会议费",),
    )
    created = registry.register_metric_definition(formula="会议费合计", **arguments)
    revised = registry.register_metric_definition(formula="会议费不含税", **arguments)

    assert created["result"] == "inserted"
    assert revised["result"] == "updated"
    assert revised["definition_id"] == created["definition_id"], "a revision minted a second key"
    assert len(store.row_ids("expense.meeting")) == 1
    assert match_metric_context("上个月会议费是多少").formula == "会议费不含税"


def test_writes_are_skipped_rather_than_simulated_without_a_database(offline):
    assert registry.sync_code_definitions()["skipped"] == 2
    assert registry.sync_code_definitions()["inserted"] == 0

    result = registry.register_metric_definition(
        metric_id="expense.meeting",
        definition_version="ops-2026-v1",
        formula="会议费合计",
        unit="元",
        period_type="month",
        match_terms=("会议费",),
    )

    assert result["result"] == "skipped"
    assert result["definition_id"] is None
    assert match_metric_context("上个月会议费是多少") is None


def test_a_failed_read_keeps_answering_from_the_code_rules(monkeypatch):
    def _broken():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(registry, "_database_available", lambda: True)
    monkeypatch.setattr(registry, "_conn", _broken)

    context = match_metric_context("本月住宿费标准是多少？")

    assert context is not None
    assert context.definition_version == DEFINITION_VERSION
    assert context.warnings == [_CODE_WARNING]


def test_importing_and_answering_never_opens_a_connection():
    code = (
        "import sys\n"
        "sys.modules['psycopg'] = None\n"
        "import app.semantics.registry as registry\n"
        "context = registry.match_metric_context('本月住宿费标准是多少？')\n"
        "print(registry._database_available(), context.definition_version)\n"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT)}

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == f"False {DEFINITION_VERSION}"


def test_match_endpoint_reports_the_table_source(store):
    store.rows = [_row()]

    response = client.post(
        "/api/v1/semantics/match", json={"question": "今年培训费用是多少"}, headers=_headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["context"]["definition_version"] == "finance-2026q3-v1"
    assert body["definition_source"] == registry.SOURCE_TABLE
    assert body["provenance"]["verified_against_documents"] is False
    assert body["provenance"]["warnings"] == [_TABLE_WARNING]


def test_match_endpoint_marks_the_code_fallback(offline):
    response = client.post(
        "/api/v1/semantics/match", json={"question": "本月住宿费标准是多少？"}, headers=_headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["definition_source"] == registry.SOURCE_CODE
    assert body["context"]["definition_version"] == DEFINITION_VERSION
    assert body["context"]["metric_name"] == "住宿费标准"
    assert body["provenance"]["warnings"] == [_CODE_WARNING]


def test_match_endpoint_reports_no_definition(offline):
    response = client.post(
        "/api/v1/semantics/match", json={"question": "今天天气怎么样？"}, headers=_headers()
    )

    assert response.status_code == 200
    assert response.json() == {"context": None, "definition_source": None, "provenance": None}


def test_metrics_endpoint_lists_definitions_with_version_and_provenance(store):
    store.rows = [_row()]

    response = client.get("/api/v1/semantics/metrics", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["database_available"] is True
    assert {item["metric_id"] for item in body["metrics"]} == {
        "expense.training",
        "expense.accommodation.standard",
        "expense.travel.total",
    }
    by_metric = {item["metric_id"]: item for item in body["metrics"]}
    assert by_metric["expense.training"]["provenance"]["source"] == registry.SOURCE_TABLE
    assert by_metric["expense.travel.total"]["provenance"]["source"] == registry.SOURCE_CODE
    assert by_metric["expense.training"]["definition_version"] == "finance-2026q3-v1"
    assert by_metric["expense.travel.total"]["definition_version"] == DEFINITION_VERSION
    assert body["definition_sources"] == {registry.SOURCE_TABLE: 1, registry.SOURCE_CODE: 2}
    assert body["definition_versions"] == sorted(["finance-2026q3-v1", DEFINITION_VERSION])
    for item in body["metrics"]:
        assert item["definition_version"], "a definition without a version is not reportable"
        assert item["provenance"]["verified_against_documents"] is False
        assert "未与已上传制度文件核对" in item["provenance"]["warnings"][0]


def test_metrics_endpoint_requires_authentication():
    assert client.get("/api/v1/semantics/metrics").status_code == 401
