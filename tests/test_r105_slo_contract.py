"""R105 甲半 · the three-tier SLO contract: units, mapping, one algorithm, one floor.

Judgement 4 of the ticket is a *behaviour* requirement, so the decisive cases below call the
real ``GET /api/v1/slo`` readout against the real stage ledger. Source text is read only where
the fact under test is itself a source-text fact: that the repository holds one quantile rule,
and that the document renders the table that lives in code rather than a copy of it.

🔴 There is no measured number in this file. Every distribution below is a synthetic vector
whose only job is to move the sample gate, and every target slot in the contract must answer
``awaiting_real_samples`` -- the filling belongs to 乙半, from the D14甲 window.
"""

import inspect
import json
import re
from pathlib import Path

import pytest

from app.api.v1 import observability
from app.agents.contracts import ModelTier
from app.agents.nodes import LANE_ANALYSIS, LANE_QA, LANE_REPORT, LANE_TIERS
from app.common.performance import PerformanceStats
from app.common.stage_timing import (
    CANONICAL_STAGES,
    default_stage_ledger,
    record_stage_sample,
    reset_stage_ledger,
)

SLO_PATH = "/api/v1/slo"
CONTRACT_DOC = Path("docs/api/contract-v1.md")
ROUTER_SOURCE = Path("frontend/src/router/index.js")
SECTION_TITLE = "## Three-Tier SLO Contract (2026-09-20, R105 甲半)"
PROVENANCE_TITLE = "## Evaluation Report Provenance (2026-09-20, R105 甲案)"
PENDING_TEXT = "「待真机样本」"
REPORTS_PATH = "/api/v1/evaluations"
SHIPPED_REPORT_PATH = "docs/testing/evaluation-report.json"


@pytest.fixture(autouse=True)
def clean_ledger(monkeypatch):
    """One empty ledger per case, and no dependence on the operator's environment."""
    monkeypatch.delenv("STAGE_TIMING_ENABLED", raising=False)
    reset_stage_ledger()
    yield
    reset_stage_ledger()


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def _headers(username="admin"):
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _seed_lane(lane, requests, *, stage="generate", end_to_end=True):
    """Put a synthetic distribution under one lane -- to move the gate, never to be read.

    Values are distinct on purpose: a flat vector lets a percentile pass by coincidence of the
    constant, which would test nothing about the rank rule.
    """
    ledger = default_stage_ledger()
    for index in range(1, requests + 1):
        trace = f"{lane}-{index}"
        record_stage_sample(stage=stage, duration_ms=float(index), lane=lane, trace_id=trace)
        if end_to_end:
            ledger.add_request_window(trace, float(index) * 10.0)
    return ledger


def _tier(body, lane):
    matches = [item for item in body["tiers"] if item["lane"] == lane]
    assert len(matches) == 1, [item["lane"] for item in body["tiers"]]
    return matches[0]


def _values_named(payload, key):
    """Every value stored under ``key`` anywhere in the answer, however deep it sits."""
    found = []

    def visit(node):
        if isinstance(node, dict):
            for name, value in node.items():
                if name == key:
                    found.append(value)
                else:
                    visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload)
    return found


def _top_level_section(title: str) -> str:
    """Cut out one ``## `` section, stopping at the next one.

    The SLO parses below look for table rows by first cell, so a section appended to the
    contract after this ticket must not be able to join them by accident.
    """
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    start = text.index(title)
    following = re.compile(r"^## ", re.MULTILINE).search(text, start + len(title))
    return text[start : following.start() if following else len(text)]


def _contract_section():
    return _top_level_section(SECTION_TITLE)


def _provenance_section():
    return _top_level_section(PROVENANCE_TITLE)


def _table_rows(section, *, lanes, cells):
    rows = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        found = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(found) != cells:
            continue
        if any(found[0] == f"`{lane}`" or found[0].startswith(f"`{lane}` ") for lane in lanes):
            rows.append(found)
    return rows


def _ticks(text):
    return re.findall(r"`([^`]+)`", text)


# ==================== ① the three units are three different enumerations ====================


def test_the_slo_unit_is_the_product_lane_and_not_the_budget_tier() -> None:
    units = observability.slo_units()

    assert units["product_lane"]["members"] == [LANE_QA, LANE_ANALYSIS, LANE_REPORT]
    assert units["product_lane"]["this_is_the_unit_of_the_slo"] is True
    assert [tier.lane for tier in observability.slo_tiers()] == [
        LANE_QA,
        LANE_ANALYSIS,
        LANE_REPORT,
    ]
    # A lane is not a budget tier: two of the three names do not exist in ``ModelTier`` at all,
    # which is the whole reason the ticket forbids renaming one for the other. The third is a
    # spelling collision (`analysis` means two different things in the two tables).
    budget_values = {tier.value for tier in ModelTier}
    assert {LANE_QA, LANE_REPORT} - budget_values == {LANE_QA, LANE_REPORT}
    assert LANE_ANALYSIS in budget_values
    assert units["ledger_stage"]["members"] == list(CANONICAL_STAGES)


def test_the_document_keeps_the_three_units_apart_and_names_the_collision() -> None:
    section = _contract_section()
    lanes = {tier.lane for tier in observability.slo_tiers()}

    lane_row = next(line for line in section.splitlines() if "**product lane**" in line)
    tier_row = next(line for line in section.splitlines() if "**model budget tier**" in line)
    stage_row = next(line for line in section.splitlines() if "**ledger stage**" in line)
    assert set(lanes) <= set(_ticks(lane_row)), _ticks(lane_row)
    assert {tier.value for tier in ModelTier} <= set(_ticks(tier_row)), _ticks(tier_row)
    assert set(CANONICAL_STAGES) <= set(_ticks(stage_row)), _ticks(stage_row)
    # Only one of the three rows may call itself the unit of the SLO.
    assert "**yes**" in lane_row and "**yes**" not in tier_row and "**yes**" not in stage_row
    assert "collision" in section


def test_the_lane_to_budget_tier_bridge_is_read_from_lane_tiers() -> None:
    bridge = observability.slo_units()["model_budget_tier"]["bridge_from_product_lane"]

    assert bridge == {
        lane: LANE_TIERS[lane].value for lane in (LANE_QA, LANE_ANALYSIS, LANE_REPORT)
    }
    # Not a bijection in either direction: two lanes share one tier, and five tiers belong to
    # no lane. A contract row may not pretend the two tables have the same shape.
    assert bridge[LANE_ANALYSIS] == bridge[LANE_REPORT]
    unlaned = {tier.value for tier in ModelTier} - set(bridge.values())
    assert unlaned == {"plan", "compress", "rewrite", "code", "alert"}


# ==================== ② 档 -> 屏/端点 -> stage 组, written down exactly once ====================


def test_every_slo_screen_is_a_real_route_in_the_frontend_router() -> None:
    """The router is 总控's file; a contract row may name a route but never invent one."""
    source = ROUTER_SOURCE.read_text(encoding="utf-8")
    routes = dict(
        (match.group(2), match.group(1))
        for match in re.finditer(
            r"path:\s*'([^']+)',\s*\n\s*name:\s*'([^']+)'", source
        )
    )
    assert "chat" in routes, sorted(routes)

    for tier in observability.slo_tiers():
        assert tier.screen in routes, f"{tier.lane} names a screen that does not exist: {tier.screen}"
        assert routes[tier.screen] == tier.screen_path
    # The one screen the router keeps out of first-level navigation is not an SLO host either.
    assert "graph" not in {tier.screen for tier in observability.slo_tiers()}
    assert "primary: false" in source


def test_stage_groups_are_canonical_ledger_stages_and_no_invented_name() -> None:
    tiers = observability.slo_tiers()

    for tier in tiers:
        assert tier.stages, tier.lane
        assert set(tier.stages) <= set(CANONICAL_STAGES), sorted(set(tier.stages) - set(CANONICAL_STAGES))
    assert {stage for tier in tiers for stage in tier.stages} == set(CANONICAL_STAGES)


def test_the_contract_table_and_the_document_cannot_drift() -> None:
    section = _contract_section()
    mapping_rows = _table_rows(section, lanes=[tier.lane for tier in observability.slo_tiers()], cells=4)

    assert len(mapping_rows) == 3, mapping_rows
    for tier in observability.slo_tiers():
        row = next(cells for cells in mapping_rows if cells[0].startswith(f"`{tier.lane}`"))
        screen_cells = _ticks(row[1])
        assert tier.screen in screen_cells and tier.screen_path in screen_cells, row
        assert set(_ticks(row[2])) == set(tier.endpoints), row
        assert set(_ticks(row[3])) == set(tier.stages), row


def test_the_document_registers_every_slot_with_a_target_instead_of_a_number() -> None:
    section = _contract_section()
    slot_rows = _table_rows(section, lanes=[tier.lane for tier in observability.slo_tiers()], cells=5)
    expected = {tier.lane: {metric.name for metric in tier.metrics} for tier in observability.slo_tiers()}

    documented: dict[str, set[str]] = {}
    for row in slot_rows:
        documented.setdefault(row[0].strip("`"), set()).add(_ticks(row[1])[0])
        assert row[-1] == PENDING_TEXT, row
    assert documented == expected, (documented, expected)


# ==================== ③ one percentile algorithm, and its one registered duplicate =========


def test_no_unregistered_module_computes_a_quantile() -> None:
    """Judgement 3: the rank rule lives in ``app/common/performance.py`` or nowhere new.

    ``app/quality/eval.py`` is a registered exception the coordinator has to rule on; the
    assertion is that nothing *else* joins it. The tripwire watches the two spellings a rank
    rule takes in this repository -- a ``ceil`` whose argument mentions a quantile, or the
    ``0.9`` literal -- so ``model_budget.py``'s token estimator, which also ceilings a
    product of a different kind, stays out of it.
    """
    pattern = re.compile(r"ceil\(.*(?:quantile|0\.9)")
    registered = {Path("app/common/performance.py"), Path("app/quality/eval.py")}
    found = {}
    for path in sorted(Path("app").rglob("*.py")):
        hits = [
            (number, line.strip())
            for number, line in enumerate(
                path.read_text(encoding="utf-8-sig").splitlines(), start=1
            )
            if pattern.search(line)
        ]
        if hits:
            found[path] = hits

    assert set(found) <= registered, {str(key): value for key, value in found.items()}
    assert Path("app/common/performance.py") in found


def test_the_registered_second_quantile_cannot_diverge_from_the_source(tmp_path) -> None:
    """The duplicate in ``evaluate_evaluation_set`` is run, not re-read, and must agree.

    ``app/quality/eval.py`` is outside this ticket's write scope, so the pin is behavioural:
    the same distributions go through both implementations, from JSONL written into
    ``tmp_path`` -- never into ``tests/fixtures``, which belongs to the evaluation sets.
    """
    from app.quality.eval import evaluate_evaluation_set

    for size in (1, 2, 3, 7, 20, 40, 99, 100, 101, 200):
        values = [float(index) for index in range(1, size + 1)]
        path = tmp_path / f"vector-{size}.jsonl"
        path.write_text(
            "".join(
                json.dumps(
                    {"question": f"q{index}", "answer": f"a{index}", "latency": value},
                    ensure_ascii=False,
                )
                + "\n"
                for index, value in enumerate(values, start=1)
            ),
            encoding="utf-8",
        )

        report = evaluate_evaluation_set(
            path,
            lambda row: {
                "answer": row["answer"],
                "latency_ms": row["latency"],
                "evidence": [{"source": "pin"}],
            },
        )
        stats = PerformanceStats()
        for value in values:
            stats.observe(float(value))

        assert report["latency_ms"]["count"] == size
        assert report["latency_ms"]["p95"] == stats.report()["p95_ms"], size
        assert report["latency_ms"]["average"] == stats.report()["average_ms"], size


def test_the_readout_points_at_the_one_rank_rule() -> None:
    report = observability.slo_readout()
    assert report["percentile_source"].startswith("app/common/performance.py::PerformanceStats")
    assert set(_values_named(report, "percentile_source")) == {observability.SLO_PERCENTILE_SOURCE}


# ==================== ④ the floor: below it the readout must confess, not answer ===========


def test_readout_below_the_floor_says_so_and_returns_no_number(client) -> None:
    _seed_lane(LANE_QA, 99)

    body = client.get(SLO_PATH, headers=_headers()).json()
    tier = _tier(body, LANE_QA)

    assert tier["observed_requests"] == 99
    gate = tier["numbers"]["end_to_end_p95_ms"]
    assert gate["n"] == 99
    assert gate["required_samples"] == observability.MIN_SLO_SAMPLES == 100
    assert gate["shortfall"] == 1
    assert gate["status"] == observability.SLO_INSUFFICIENT
    assert "insufficient samples" in gate["reason"]
    assert gate["p95_ms"] is None and gate["p50_ms"] is None
    # Nothing anywhere in the answer may look like an SLO while the floor is unmet.
    assert set(_values_named(body, "p95_ms")) == {None}
    assert set(_values_named(body, "p50_ms")) == {None}
    assert set(_values_named(body, "target_status")) == {observability.SLO_TARGET_PENDING}
    assert set(_values_named(body, "target")) == {None}


def test_the_floor_is_a_knife_edge_and_gates_each_number_on_its_own_n(client) -> None:
    _seed_lane(LANE_QA, 100)

    tier = _tier(client.get(SLO_PATH, headers=_headers()).json(), LANE_QA)
    gate = tier["numbers"]["end_to_end_p95_ms"]

    ledger = default_stage_ledger()
    expected = PerformanceStats()
    for window in ledger.request_windows().values():
        expected.observe(float(window))
    assert gate["status"] == observability.SLO_MEASURED
    assert gate["n"] == 100 and gate["shortfall"] == 0
    assert gate["p95_ms"] == expected.report()["p95_ms"]
    # The stage distribution inside the same tier only has 100 samples of one stage, so the
    # other four are still short: one number crossing the floor does not promote its neighbours.
    short = tier["stage_numbers"]["classify"]
    assert short["n"] == 0 and short["status"] == observability.SLO_INSUFFICIENT
    assert short["p95_ms"] is None


def test_an_empty_ledger_says_insufficient_instead_of_publishing_zero() -> None:
    """The failure mode the gate exists for, shown side by side."""
    raw = default_stage_ledger().report()["stages"]["generate"]
    assert raw["count"] == 0 and raw["p95_ms"] == 0

    gated = _tier(observability.slo_readout(), LANE_QA)["stage_numbers"]["generate"]
    assert gated["n"] == 0
    assert gated["status"] == observability.SLO_INSUFFICIENT
    assert gated["p95_ms"] is None


def test_unlabelled_live_samples_are_not_split_across_tiers(client) -> None:
    """What a real process records today: no lane on any sample, so no tier may answer.

    ``app/trace/spans.py`` never passes a lane, so a window with a hundred requests is still
    one pooled distribution. The honest readout says "insufficient" per tier and shows the
    pool, rather than inventing a per-tier split out of an ``unknown`` bucket.
    """
    ledger = default_stage_ledger()
    for index in range(1, 101):
        record_stage_sample(
            stage="generate", duration_ms=float(index), trace_id=f"untraced-{index}"
        )
        ledger.add_request_window(f"untraced-{index}", float(index) * 10.0)

    body = client.get(SLO_PATH, headers=_headers()).json()

    for tier in body["tiers"]:
        assert tier["observed_requests"] == 0, tier["lane"]
        assert tier["numbers"]["end_to_end_p95_ms"]["p95_ms"] is None
    pool = body["unattributed_pool"]["end_to_end"]
    assert pool["n"] == 100 and pool["status"] == observability.SLO_MEASURED
    assert "lane_attribution_absent" in json.dumps(body["tiers"], ensure_ascii=False)


def test_slots_without_a_measurement_piece_still_answer_no_number(client) -> None:
    tier = _tier(client.get(SLO_PATH, headers=_headers()).json(), LANE_QA)

    for name in ("first_text_p95_ms", "cache_hit_p95_ms"):
        block = tier["numbers"][name]
        assert block["status"] == observability.SLO_NOT_MEASURABLE, name
        assert block["p95_ms"] is None and block["target"] is None, name
        codes = [item["code"] for item in block["blockers"]]
        assert codes and set(codes) <= set(observability.SLO_BLOCKERS), name
    assert "cache_hits_are_not_traced" in json.dumps(tier["numbers"]["cache_hit_p95_ms"])


def test_the_floor_is_not_a_query_parameter(client) -> None:
    """A threshold a caller can lower is not a threshold."""
    parameters = inspect.signature(observability.read_slo).parameters
    assert list(parameters) == ["request"], list(parameters)

    operation = client.get("/openapi.json").json()["paths"][SLO_PATH]["get"]
    assert operation.get("parameters", []) == []
    assert operation["tags"] == ["observability"]


def test_the_slo_route_needs_the_audit_permission() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    bare = FastAPI()
    bare.include_router(observability.router, prefix="/api/v1")

    response = TestClient(bare).get(SLO_PATH)

    assert response.status_code == 401
    envelope = response.json()["detail"]
    assert set(envelope) == {"code", "message", "retryable", "details"}
    assert envelope["code"] == "authentication_required"
    assert envelope["retryable"] is False


def test_the_readout_opens_no_engine(monkeypatch) -> None:
    """A contract readout that needed the model stack could not be read on a quiet box."""
    import socket

    def refuse(*args, **kwargs):
        raise AssertionError("the SLO readout must not open a socket")

    monkeypatch.setattr(socket.socket, "__init__", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    report = observability.slo_readout()

    assert [tier["lane"] for tier in report["tiers"]] == [LANE_QA, LANE_ANALYSIS, LANE_REPORT]
    assert json.dumps(report, ensure_ascii=False, default=str)


# ==================== 甲案: /evaluations says where each report came from ====================


@pytest.fixture()
def users(monkeypatch):
    """Back the authentication middleware with an in-memory user table."""
    from app.common import auth

    registry = {}

    def add(username, role, **fields):
        registry[username] = {
            "id": f"u-{username}",
            "username": username,
            "role": role,
            "department": "研发部",
            **fields,
        }
        return username

    monkeypatch.setattr(auth, "get_user", lambda username: registry.get(username))
    return add


def _write_report(directory: Path, name: str, total: int) -> Path:
    path = directory / name
    path.write_text(
        json.dumps(
            {
                "total": total,
                "answer_correctness": 0.8,
                "latency_ms": {"count": total, "average": 900.0, "p95": 1400.0},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_configured_report_dirs_keep_the_shipped_score_visible_as_shipped_default(
    client, users, monkeypatch, tmp_path
) -> None:
    """Labelling the bundled score is allowed; hiding it is not, and neither changed the list."""
    admin = users("r105-admin-configured", "admin")
    _write_report(tmp_path, "run-window-3.json", 12)
    monkeypatch.delenv("EVALUATION_REPORT_DIRS", raising=False)
    monkeypatch.delenv("EVALUATION_REPORT_DIR", raising=False)
    monkeypatch.setenv("EVALUATION_REPORT_DIRS", str(tmp_path))

    body = client.get(REPORTS_PATH, headers=_headers(admin)).json()

    assert body["status"] == "reports_available"
    assert [item["path"] for item in body["reports"]] == [
        (tmp_path / "run-window-3.json").as_posix(),
        SHIPPED_REPORT_PATH,
    ], body["reports"]
    assert body["reports_total"] == len(body["reports"]) == 2
    assert body["truncated"] is False
    assert [item["source"] for item in body["reports"]] == [
        observability.REPORT_SOURCE_CONFIGURED,
        observability.REPORT_SOURCE_SHIPPED_DEFAULT,
    ]
    # The label is not a demotion: the shipped record is still the real, readable score.
    bundled = body["reports"][-1]
    assert bundled["status"] == "ok" and bundled["id"] == "evaluation-report"
    assert bundled["metrics"] and bundled["size_bytes"] > 0
    assert [item["status"] for item in body["reports"]] == ["ok", "ok"]
    assert set(_values_named(body, "source")) == {
        observability.REPORT_SOURCE_CONFIGURED,
        observability.REPORT_SOURCE_SHIPPED_DEFAULT,
    }


def test_a_configured_path_at_the_shipped_score_still_says_shipped_default(
    client, users, monkeypatch
) -> None:
    """Provenance belongs to the file, not to how the operator spelled it.

    Pointing a report dir straight at the bundled score used to make it look operator-owned;
    the identity test resolves the path, so the answer still says the box came with it. The
    dedup in the candidate list is checked in the same breath: one record, not two.
    """
    admin = users("r105-admin-spelled", "admin")
    monkeypatch.delenv("EVALUATION_REPORT_DIRS", raising=False)
    monkeypatch.delenv("EVALUATION_REPORT_DIR", raising=False)
    monkeypatch.setenv("EVALUATION_REPORT_DIR", SHIPPED_REPORT_PATH)

    body = client.get(REPORTS_PATH, headers=_headers(admin)).json()

    assert [item["path"] for item in body["reports"]] == [SHIPPED_REPORT_PATH]
    assert body["reports_total"] == 1 and body["truncated"] is False
    assert [item["source"] for item in body["reports"]] == [
        observability.REPORT_SOURCE_SHIPPED_DEFAULT
    ]


def test_an_unreadable_report_still_says_where_it_came_from(tmp_path) -> None:
    """The key is written before anything is read, so no early return can lose it."""
    missing = observability._report_summary(
        tmp_path / "gone.json", source=observability.REPORT_SOURCE_SHIPPED_DEFAULT
    )
    assert missing["status"] == "unreadable"
    assert missing["source"] == observability.REPORT_SOURCE_SHIPPED_DEFAULT
    assert list(missing)[:3] == ["id", "path", "source"]

    huge = tmp_path / "huge.json"
    huge.write_text("x" * (observability.MAX_EVALUATION_FILE_BYTES + 8), encoding="utf-8")
    fat = observability._report_summary(huge, source=observability.REPORT_SOURCE_CONFIGURED)
    assert fat["status"] == "too_large"
    assert fat["source"] == observability.REPORT_SOURCE_CONFIGURED


def test_the_provenance_field_has_two_values_and_the_contract_registers_both() -> None:
    """The doc fact: one registered key, exactly two spellings, and a promise about the list."""
    section = _provenance_section()
    assert section
    assert observability.REPORT_SOURCE_CONFIGURED == "configured"
    assert observability.REPORT_SOURCE_SHIPPED_DEFAULT == "shipped_default"
    for literal in (
        observability.REPORT_SOURCE_CONFIGURED,
        observability.REPORT_SOURCE_SHIPPED_DEFAULT,
    ):
        assert f"`{literal}`" in section, literal
    assert "`reports[].source`" in section
    assert "_shipped_report_paths" in section
    # 甲案 registers a label, so the section has to say the candidate set itself is untouched.
    assert "candidate set" in section
    assert "unconditional" in section
