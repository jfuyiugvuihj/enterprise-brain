"""R15-b 的判据链：候选关系 → 人工核对来源 → 落成正式口径 → 未核对 warning 消失。

用例离线跑在一个 metric_definitions 替身上（与 tests/test_business_semantics.py 同一手法：
替身按 registry 自己声明的 _INSERT_COLUMNS/_UNIQUE_COLUMNS 行事），所以断言能落在**真列**上，
而不是 JSONB 里。真机 PostgreSQL 上的 0009 回放属待总控复验项。
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.agents.contracts import Principal
from app.knowledge_graph.promotion import promote_relation_to_definition
from app.knowledge_graph.service import KnowledgeGraph
from app.semantics import registry

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)

DOC = "\u5dee\u65c5\u8d39\u62a5\u9500\u5236\u5ea6.pdf"
SECTION = "\u7b2c3\u9875 \u4f4f\u5bbf\u8d39\u6807\u51c6"
CODE_WARNING = "\u5b9a\u4e49\u6765\u81ea\u4ee3\u7801\u8bed\u4e49\u6ce8\u518c\u8868\uff0c\u672a\u4e0e\u5df2\u4e0a\u4f20\u5236\u5ea6\u6587\u4ef6\u6838\u5bf9"
TABLE_WARNING = "\u5b9a\u4e49\u6765\u81ea\u6307\u6807\u5b9a\u4e49\u8868 metric_definitions\uff0c\u672a\u4e0e\u5df2\u4e0a\u4f20\u5236\u5ea6\u6587\u4ef6\u6838\u5bf9"


def _principal(user_id: str, *, department: str = "\u7814\u53d1\u90e8", approve: bool = False) -> Principal:
    permissions = ["resource:view", "resource:upload"]
    if approve:
        permissions.append("resource:approve")
    return Principal(
        user_id=user_id,
        username=user_id,
        roles=["manager" if approve else "staff"],
        permissions=permissions,
        department=department,
        department_ids=[department],
        clearance=2 if approve else 1,
    )


class CatalogStore:
    """The two statements the registry issues, against an in-memory metric_definitions."""

    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = [dict(row) for row in rows or []]
        self.statements: list[str] = []
        self._result: list[dict] = []
        self._sequence = 0

    def execute(self, sql, params=None):
        statement = " ".join(sql.split()).lower()
        self.statements.append(statement)
        values = tuple(params or ())
        if statement.startswith("select"):
            owners = set(values)
            self._result = sorted(
                (row for row in self.rows if row["owner_id"] in owners),
                key=lambda row: (row.get("created_at") or _EPOCH, str(row.get("metric_definition_id") or "")),
            )
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
            self._sequence += 1
            values["created_at"] = _BASE_TIME + timedelta(minutes=self._sequence)
            self.rows.append(values)
            written, is_new = values, True
        elif "do update" in statement:
            for column in registry._INSERT_COLUMNS:
                if column not in registry._IMMUTABLE_COLUMNS:
                    clash[column] = values[column]
            written, is_new = clash, False
        else:
            self._result = []
            return
        returned = {"metric_definition_id": written["metric_definition_id"]}
        if "as is_new" in statement:
            returned["is_new"] = is_new
        self._result = [returned]

    def fetchone(self):
        return copy.deepcopy(self._result[0]) if self._result else None

    def fetchall(self):
        return copy.deepcopy(self._result)

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


def _bare_row(**overrides) -> dict:
    """One 0009-shaped row, as PostgreSQL would hand it back."""
    row = {
        "metric_definition_id": "md:system:expense.training:v1",
        "owner_id": registry.SYSTEM_OWNER_ID,
        "metric_id": "expense.training",
        "definition_version": "v1",
        "formula": "\u57f9\u8bad\u8d39\u5408\u8ba1",
        "unit": "\u5143",
        "currency": "CNY",
        "period_type": "month",
        "timezone": "Asia/Shanghai",
        "source_scope": [],
        "filters": {},
        "status": "active",
        "metric_name": "\u57f9\u8bad\u8d39",
        "definition_text": "\u5458\u5de5\u57f9\u8bad\u53d1\u751f\u7684\u8d39\u7528",
        "time_granularity": "\u6708",
        "origin": "operator",
        "match_terms": ["\u57f9\u8bad\u8d39"],
        "verification_state": registry.UNVERIFIED_STATE,
        "verified_document": None,
        "verified_section": None,
        "verified_by": None,
        "verified_at": None,
        "source_relation_id": None,
        "created_at": _BASE_TIME,
    }
    row.update(overrides)
    return row


@pytest.fixture
def catalog(monkeypatch):
    store = CatalogStore()
    monkeypatch.setattr(registry, "_database_available", lambda: True)
    monkeypatch.setattr(registry, "_conn", lambda: store)
    return store


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(registry, "_database_available", lambda: False)
    monkeypatch.setattr(registry, "_conn", _never)


def _never():
    raise AssertionError("no connection may be opened on this path")


@pytest.fixture
def graph(tmp_path):
    return KnowledgeGraph(store_path=tmp_path / "relations.json")


def _candidate(graph: KnowledgeGraph) -> str:
    """A relation as it arrives from the录入端: candidate, source located, nobody has checked."""
    return graph.add_relation(
        "\u5dee\u65c5\u5236\u5ea6",
        "\u89c4\u5b9a",
        "\u4f4f\u5bbf\u4e0a\u9650",
        f"{DOC} {SECTION}",
        principal=_principal("u-1"),
    ).relation_id


def _verify(graph: KnowledgeGraph, relation_id: str) -> None:
    graph.record_verification(
        relation_id, principal=_principal("u-9", approve=True), document=DOC, section=SECTION
    )


def _promote(graph: KnowledgeGraph, relation_id: str, **overrides) -> dict:
    arguments = dict(
        metric_id="expense.accommodation.standard",
        definition_version="policy-2026-v1",
        formula="\u5355\u665a\u4f4f\u5bbf\u8d39\u7528 <= \u5236\u5ea6\u6807\u51c6",
        unit="\u5143/\u665a",
        period_type="single",
        metric_name="\u4f4f\u5bbf\u8d39\u6807\u51c6",
        definition_text="2026 \u7248\u5dee\u65c5\u5236\u5ea6\u89c4\u5b9a\u7684\u5355\u665a\u4f4f\u5bbf\u4e0a\u9650",
        match_terms=("\u4f4f\u5bbf\u8d39\u6807\u51c6", "\u4f4f\u5bbf\u4e0a\u9650"),
        time_granularity="\u5355\u7b14",
    )
    arguments.update(overrides)
    return promote_relation_to_definition(
        graph, relation_id, principal=_principal("u-9", approve=True), **arguments
    )


# ------------------------------------------------------------------- 全链路


def test_a_verified_relation_becomes_a_definition_the_warning_disappears_from(graph, catalog):
    relation_id = _candidate(graph)
    _verify(graph, relation_id)

    result = _promote(graph, relation_id)

    assert result["promoted"] is True
    assert result["result"] == "inserted"
    assert catalog.rows and catalog.rows[0]["metric_definition_id"] == result["definition_id"]

    row = catalog.rows[0]
    # 判据：证据落在真列上。JSONB 里那个保留键读不到核对状态，也永远不算证据。
    for column, expected in (
        ("verification_state", registry.VERIFIED_STATE),
        ("verified_document", DOC),
        ("verified_section", SECTION),
        ("verified_by", "u-9"),
        ("source_relation_id", relation_id),
        ("metric_name", "\u4f4f\u5bbf\u8d39\u6807\u51c6"),
        ("definition_text", "2026 \u7248\u5dee\u65c5\u5236\u5ea6\u89c4\u5b9a\u7684\u5355\u665a\u4f4f\u5bbf\u4e0a\u9650"),
        ("origin", "operator"),
    ):
        assert row[column] == expected, column
    assert isinstance(row["verified_at"], datetime)
    assert json.loads(row["match_terms"]) == ["\u4f4f\u5bbf\u8d39\u6807\u51c6", "\u4f4f\u5bbf\u4e0a\u9650"]
    mirror = json.loads(row["filters"])[registry.SEMANTICS_KEY]
    assert mirror["metric_name"] == "\u4f4f\u5bbf\u8d39\u6807\u51c6"
    for leaked in registry.VERIFICATION_EVIDENCE:
        assert leaked not in mirror, leaked

    definition = registry.match_definition("\u4eca\u5e74\u4f4f\u5bbf\u8d39\u6807\u51c6\u662f\u591a\u5c11")
    assert definition is not None
    assert definition.source == registry.SOURCE_TABLE
    assert definition.definition_version == "policy-2026-v1"
    assert definition.verified_against_documents is True
    assert definition.warnings == ()
    assert definition.to_context().warnings == []
    assert definition.filters == {}
    provenance = definition.provenance()
    assert provenance["verification_state"] == registry.VERIFIED_STATE
    assert provenance["verified_document"] == DOC and provenance["verified_section"] == SECTION
    assert provenance["verified_by"] == "u-9" and provenance["source_relation_id"] == relation_id

    record = graph.get(relation_id, principal=_principal("u-1"))
    assert record.status == "promoted"
    assert record.promoted_definition_id == result["definition_id"]


def test_the_catalog_reports_the_unverified_half_instead_of_claiming_victory(graph, catalog):
    relation_id = _candidate(graph)
    _verify(graph, relation_id)
    _promote(graph, relation_id)

    payload = registry.metric_catalog()

    assert payload["definition_sources"] == {registry.SOURCE_TABLE: 1, registry.SOURCE_CODE: 1}
    # 只剩差旅费那条没人核对，所以整本目录仍然不许自称全部核对过。
    assert payload["verified_against_documents"] is False
    assert payload["definition_verification"] == {
        registry.VERIFIED_STATE: 1,
        registry.UNVERIFIED_STATE: 1,
    }
    assert payload["warnings"] == [CODE_WARNING]
    by_metric = {item["metric_id"]: item for item in payload["metrics"]}
    assert by_metric["expense.accommodation.standard"]["provenance"]["warnings"] == []
    assert by_metric["expense.travel.total"]["provenance"]["warnings"] == [CODE_WARNING]


def test_a_re_promotion_under_a_new_version_revises_without_losing_the_lineage(graph, catalog):
    relation_id = _candidate(graph)
    _verify(graph, relation_id)

    first = _promote(graph, relation_id)
    second = _promote(graph, relation_id, definition_version="policy-2027-v1")

    assert first["promoted"] and second["promoted"]
    assert len(catalog.rows) == 2
    assert {row["source_relation_id"] for row in catalog.rows} == {relation_id}
    assert all(row["verification_state"] == registry.VERIFIED_STATE for row in catalog.rows)
    assert graph.get(relation_id, principal=_principal("u-1")).promoted_definition_id == second["definition_id"]


# --------------------------------------------------------- 只有真列才算证据


def test_a_verification_flag_smuggled_into_the_mirror_does_not_count(catalog):
    catalog.rows = [
        _bare_row(
            filters={
                registry.SEMANTICS_KEY: {
                    "metric_name": "\u57f9\u8bad\u8d39",
                    "origin": "operator",
                    "verification_state": "verified",
                    "verified_document": DOC,
                    "verified_section": SECTION,
                    "verified_by": "u-1",
                }
            },
            metric_name=None,
            definition_text=None,
            origin=None,
            match_terms=None,
        )
    ]

    definition = registry.match_definition("\u4eca\u5e74\u57f9\u8bad\u8d39\u662f\u591a\u5c11")

    assert definition is not None
    assert definition.metric_name == "\u57f9\u8bad\u8d39", "\u955c\u50cf\u4ecd\u662f\u56de\u9000\u8bfb\u53d6\u7684\u6765\u6e90"
    assert definition.verified_against_documents is False
    assert definition.warnings == (TABLE_WARNING,)


def test_a_row_claiming_verified_without_evidence_is_read_as_unverified(catalog):
    catalog.rows = [
        _bare_row(
            verification_state=registry.VERIFIED_STATE,
            verified_document=DOC,
            verified_section="",
            verified_by="u-9",
            verified_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        )
    ]

    definition = registry.match_definition("\u4eca\u5e74\u57f9\u8bad\u8d39\u662f\u591a\u5c11")

    assert definition.verification_state == registry.UNVERIFIED_STATE
    assert definition.verified_against_documents is False
    assert definition.warnings == (TABLE_WARNING,)
    assert definition.provenance()["verified_document"] == ""
    assert registry.metric_catalog()["verified_against_documents"] is False


def test_a_real_column_beats_the_mirror_it_used_to_live_in(catalog):
    catalog.rows = [
        _bare_row(
            metric_name="\u771f\u5217\u6807\u7b7e",
            definition_text="\u771f\u5217\u5b9a\u4e49",
            match_terms='["\u771f\u5217\u6807\u7b7e"]',
            filters={
                registry.SEMANTICS_KEY: {
                    "metric_name": "\u955c\u50cf\u6807\u7b7e",
                    "definition_text": "\u955c\u50cf\u5b9a\u4e49",
                    "match_terms": ["\u955c\u50cf\u6807\u7b7e"],
                }
            },
        )
    ]

    definition = registry.match_definition("\u771f\u5217\u6807\u7b7e\u600e\u4e48\u7b97")

    assert definition is not None
    assert definition.metric_name == "\u771f\u5217\u6807\u7b7e"
    assert definition.definition == "\u771f\u5217\u5b9a\u4e49"
    assert definition.match_terms == ("\u771f\u5217\u6807\u7b7e",)


# ---------------------------------------------------------------- 门禁与失败面


def test_an_unverified_relation_cannot_be_promoted(graph, catalog):
    relation_id = _candidate(graph)

    with pytest.raises(ValueError, match="relation_not_verified"):
        _promote(graph, relation_id)

    assert catalog.rows == []


def test_a_rejected_relation_cannot_be_promoted(graph, catalog):
    relation_id = _candidate(graph)
    graph.record_verification(
        relation_id,
        principal=_principal("u-9", approve=True),
        outcome="rejected",
        note="\u5f15\u7528\u7684\u662f\u5e9f\u6b62\u7248",
    )

    with pytest.raises(ValueError, match="relation_not_verified"):
        _promote(graph, relation_id)

    assert catalog.rows == []
    assert graph.get(relation_id, principal=_principal("u-1")).status == "rejected"


def test_a_promotion_needs_approval_and_a_database(graph, offline):
    relation_id = _candidate(graph)
    _verify(graph, relation_id)

    with pytest.raises(PermissionError, match="approval_permission_required"):
        promote_relation_to_definition(
            graph,
            relation_id,
            principal=_principal("u-8"),
            metric_id="expense.accommodation.standard",
            definition_version="policy-2026-v1",
            formula="\u5355\u665a <= \u6807\u51c6",
            unit="\u5143/\u665a",
            period_type="single",
        )

    result = _promote(graph, relation_id)
    assert result["promoted"] is False
    assert result["result"] == "skipped"
    assert result["definition_id"] is None
    record = graph.get(relation_id, principal=_principal("u-1"))
    assert record.status == "confirmed", "\u6ca1\u5199\u8fdb\u8868\u7684\u53e3\u5f84\u4e0d\u8bb8\u79f0\u5df2\u664b\u5347"
    assert record.promoted_definition_id == ""


def test_default_wording_comes_from_the_relation_and_the_review_still_counts(graph, catalog):
    relation_id = _candidate(graph)
    _verify(graph, relation_id)

    result = _promote(graph, relation_id, metric_name="", definition_text="", match_terms=())

    assert result["promoted"] is True
    row = catalog.rows[0]
    assert row["metric_name"] == "\u4f4f\u5bbf\u4e0a\u9650"
    assert "\u5dee\u65c5\u5236\u5ea6" in row["definition_text"] and DOC in row["definition_text"]
    # 没人给词表时仍然按派生词可检索，而且派生结果落在了真列上，不再是 JSONB 里的私钥。
    assert set(json.loads(row["match_terms"])) >= {
        "\u4f4f\u5bbf\u4e0a\u9650",
        "\u5dee\u65c5\u5236\u5ea6",
        "expense.accommodation.standard",
    }
    definition = registry.match_definition("\u4f4f\u5bbf\u4e0a\u9650\u662f\u591a\u5c11")
    assert definition is not None and definition.metric_id == "expense.accommodation.standard"
    assert definition.verified_against_documents is True


def test_revising_a_definition_without_the_evidence_reopens_the_warning(catalog):
    arguments = dict(
        metric_id="expense.meeting",
        definition_version="ops-2026-v1",
        formula="\u4f1a\u8bae\u8d39\u5408\u8ba1",
        unit="\u5143",
        period_type="month",
        match_terms=("\u4f1a\u8bae\u8d39",),
    )
    certified = registry.register_metric_definition(
        metric_name="\u4f1a\u8bae\u8d39",
        definition_text="\u4f1a\u8bae\u5ba4\u4e0e\u8bbe\u5907\u8d39\u7528",
        verified_document=DOC,
        verified_section=SECTION,
        verified_by="u-9",
        **arguments,
    )
    assert certified["definition"]["provenance"]["warnings"] == []
    assert certified["definition"]["provenance"]["verified_against_documents"] is True

    revised = registry.register_metric_definition(metric_name="\u4f1a\u8bae\u8d39", **arguments)

    assert revised["result"] == "updated"
    assert revised["definition_id"] == certified["definition_id"]
    assert revised["definition"]["provenance"]["verification_state"] == registry.UNVERIFIED_STATE
    assert revised["definition"]["provenance"]["warnings"] == [TABLE_WARNING]
    row = catalog.rows[0]
    assert row["verification_state"] == registry.UNVERIFIED_STATE
    assert row["verified_document"] is None and row["verified_at"] is None


def test_half_an_evidence_trail_is_refused(catalog):
    with pytest.raises(ValueError, match="verification evidence incomplete"):
        registry.register_metric_definition(
            metric_id="expense.meeting",
            definition_version="ops-2026-v1",
            formula="\u4f1a\u8bae\u8d39\u5408\u8ba1",
            unit="\u5143",
            period_type="month",
            verified_document=DOC,
        )
    assert catalog.rows == []


def test_synced_code_rows_stay_unverified_and_the_mirror_still_writes(catalog):
    result = registry.sync_code_definitions()

    assert result["inserted"] == 2
    for row in catalog.rows:
        assert row["verification_state"] == registry.UNVERIFIED_STATE
        assert row["verified_document"] is None
        assert row["origin"] == registry.SOURCE_CODE
        assert json.loads(row["filters"])[registry.SEMANTICS_KEY]["origin"] == registry.SOURCE_CODE
    assert registry.metric_catalog()["definition_verification"] == {
        registry.VERIFIED_STATE: 0,
        registry.UNVERIFIED_STATE: 2,
    }
    assert registry.metric_catalog()["verified_against_documents"] is False
