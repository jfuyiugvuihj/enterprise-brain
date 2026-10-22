import json
from pathlib import Path


def test_evaluation_report_tracks_categories_and_latency(tmp_path):
    from app.quality.eval import evaluate_evaluation_set

    fixture = tmp_path / "evaluation.jsonl"
    fixture.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "doc-1",
                        "category": "文档问答",
                        "question": "住宿费标准是多少？",
                        "answer": "500元/晚",
                        "must_contain": ["500元/晚"],
                        "requires_evidence": True,
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "id": "scope-1",
                        "category": "无证据问题",
                        "question": "公司有没有火星基地？",
                        "answer": "无法确认",
                        "must_contain": ["无法确认"],
                        "requires_evidence": False,
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )

    def answer_fn(row):
        return {
            "answer": "住宿费标准是500元/晚。",
            "evidence": [{"source_name": "差旅制度.pdf", "locator": "第3页"}],
            "confidence_label": "high",
            "latency_ms": 120,
        } if row["id"] == "doc-1" else {
            "answer": "无法确认，公司知识库没有相关证据。",
            "evidence": [],
            "confidence_label": "low",
            "latency_ms": 240,
        }

    report = evaluate_evaluation_set(fixture, answer_fn)

    assert report["total"] == 2
    assert report["answer_correctness"] == 1.0
    assert report["evidence_coverage"] == 1.0
    assert report["category_metrics"]["文档问答"]["correctness"] == 1.0
    assert report["category_metrics"]["无证据问题"]["correctness"] == 1.0
    assert report["latency_ms"]["p95"] == 240


def test_evaluate_provenance_flags_unsupported_claims():
    from app.quality.eval import evaluate_provenance

    report = evaluate_provenance(
        {
            "answer": "公司规定住宿费为500元/晚，财务总监审批。",
            "evidence": [{"source_name": "差旅制度.pdf", "locator": "第3页"}],
            "claims": [
                {"text": "住宿费为500元/晚", "supported": True},
                {"text": "财务总监审批", "supported": False},
            ],
            "confidence": 0.42,
        }
    )

    assert report["has_evidence"] is True
    assert report["evidence_coverage"] == 0.5
    assert report["confidence_label"] == "low"
    assert report["unsupported_claims"] == ["财务总监审批"]



# --- R36：分层业务评测集（30 → 105）结构与可跑性校验 -------------------------------
#
# 判据来源：docs/handoff/2026-09-15-backend-followup-requests.md §21 R36 行
#   ① 每档有可跑的分层评测集（含同指标两部门口径冲突成对题）
#   ② P95 计算样本 ≥100（依据 docs/handoff/2026-09-17-perf-architecture-plan.md:110）
#   ③ 基线分数落盘供 R29/R33/R35 对比 —— 本轮**不产出**。真机跑分要打 Ollama，而 Ollama 计时是全腿
#      共享红线（n_ctx=4096 单点，并发即作废），必须另开独立对话单跑一轮，命令见
#      scripts/run_quality_evaluation.py：--fixture 指向本文件，--answers 为真机录制的 105 条应答。
#
# 题面全部人工构造，未取 Dashboard/洞察的演示语料（§21 R36 禁改边界）。

EVALUATION_100_PATH = Path(__file__).parent / "fixtures" / "business_evaluation_100.jsonl"
EVALUATION_30_PATH = Path(__file__).parent / "fixtures" / "business_evaluation_30.jsonl"
EVALUATION_TIERS = ("问答", "分析", "报告")
REQUIRED_ROW_FIELDS = ("id", "tier", "category", "question", "answer", "must_contain", "requires_evidence")
CONFLICT_ROW_FIELDS = ("conflict_pair", "metric", "department")
MIN_ROWS = 100
MIN_TIER_ROWS = 20
MIN_CONFLICT_PAIRS = 6

# 沿用行里唯一一条「金标答案不含自身 must_contain」的历史遗留：insight-02 期望「上升」，
# 金标写的却是「返回趋势异常」。本轮为保住与历史 30 条跑分的可比性，不动沿用行的评分口径，
# 所以把它钉死成已知集合——沿用行再新增这种缺陷会直接失败，新题则强制自洽。
KNOWN_INCONSISTENT_INHERITED_IDS = {"insight-02"}


def _load_rows(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def _write_fixture(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _gold_answer_fn(rows):
    """Deterministic stand-in for the model: replays each row's own expected content.

    It proves the set is runnable and passable with zero model calls.
    """
    reference = {row["id"]: row for row in rows}
    counter = {"n": 0}

    def answer_fn(row):
        counter["n"] += 1
        target = reference[row["id"]]
        text = " ".join([str(target["answer"])] + [str(item) for item in target["must_contain"]])
        return {
            "answer": text,
            "evidence": [{"source_name": "制度与口径登记表", "locator": f"第{counter['n']}行"}],
            "confidence_label": "high",
            "latency_ms": 100 + 37 * counter["n"],
        }

    return answer_fn


def _recorded_answer_fn(answers):
    """Replay a fixed id -> answer map, so scoring is reproducible without a model."""

    def answer_fn(row):
        return {
            "answer": answers[str(row["id"])],
            "evidence": [{"source_name": "口径登记表", "locator": "第1行"}],
            "latency_ms": 100,
        }

    return answer_fn


def test_business_evaluation_100_expands_the_30_row_set_without_drift():
    rows = _load_rows(EVALUATION_100_PATH)
    inherited = _load_rows(EVALUATION_30_PATH)
    by_id = {row["id"]: row for row in rows}

    assert len(rows) >= MIN_ROWS
    assert len(rows) > len(inherited)
    for original in inherited:
        carried = by_id[original["id"]]
        for field, value in original.items():
            assert carried[field] == value, f"{original['id']}.{field} drifted from the 30-row set"


def test_business_evaluation_100_rows_are_structurally_valid():
    rows = _load_rows(EVALUATION_100_PATH)
    inherited_ids = {row["id"] for row in _load_rows(EVALUATION_30_PATH)}

    assert len({row["id"] for row in rows}) == len(rows)

    inconsistent = set()
    for row in rows:
        for field in REQUIRED_ROW_FIELDS:
            assert field in row, f"{row.get('id')} missing {field}"
        assert isinstance(row["id"], str) and row["id"].strip()
        assert row["tier"] in EVALUATION_TIERS, f"{row['id']} has illegal tier {row['tier']!r}"
        assert isinstance(row["category"], str) and row["category"].strip()
        assert isinstance(row["question"], str) and row["question"].strip()
        assert isinstance(row["answer"], str) and row["answer"].strip(), f"{row['id']} has empty expected answer"
        assert isinstance(row["must_contain"], list) and row["must_contain"], f"{row['id']} has empty must_contain"
        assert all(isinstance(item, str) and item.strip() for item in row["must_contain"])
        assert isinstance(row["requires_evidence"], bool)
        if any(field in row for field in CONFLICT_ROW_FIELDS):
            for field in CONFLICT_ROW_FIELDS:
                assert str(row.get(field, "")).strip(), f"{row['id']} conflict row is missing {field}"
        if not all(str(item) in row["answer"] for item in row["must_contain"]):
            inconsistent.add(row["id"])

    assert inconsistent == KNOWN_INCONSISTENT_INHERITED_IDS
    assert inconsistent <= inherited_ids, "new rows must satisfy their own must_contain"


def test_business_evaluation_100_covers_every_tier():
    rows = _load_rows(EVALUATION_100_PATH)
    counts = {tier: sum(1 for row in rows if row["tier"] == tier) for tier in EVALUATION_TIERS}

    assert sum(counts.values()) == len(rows)
    for tier, count in counts.items():
        assert count >= MIN_TIER_ROWS, f"tier {tier} has only {count} rows"


def test_business_evaluation_100_conflict_pairs_are_discriminating(tmp_path):
    from app.quality.eval import evaluate_evaluation_set

    rows = _load_rows(EVALUATION_100_PATH)
    pairs = {}
    for row in rows:
        if "conflict_pair" in row:
            pairs.setdefault(row["conflict_pair"], []).append(row)

    assert len(pairs) >= MIN_CONFLICT_PAIRS
    for pair_id, members in sorted(pairs.items()):
        assert len(members) == 2, f"{pair_id} must hold exactly two departments"
        left, right = members
        assert left["metric"] == right["metric"], f"{pair_id} is not the same metric"
        assert left["department"] != right["department"], f"{pair_id} needs two departments"

        left_expected = [str(item) for item in left["must_contain"]]
        right_expected = [str(item) for item in right["must_contain"]]
        assert set(left_expected) != set(right_expected), f"{pair_id} expected values are identical"
        assert not set(left_expected) & set(right_expected), f"{pair_id} expected values overlap"
        # 「含税」是「不含税」的子串，这种陷阱会让两边互相判对，必须排除。
        for first in left_expected:
            for second in right_expected:
                assert first not in second and second not in first, f"{pair_id} nests: {first!r}/{second!r}"

        fixture = tmp_path / f"{pair_id}.jsonl"
        _write_fixture(fixture, [left, right])

        own_caliber = {left["id"]: left["answer"], right["id"]: right["answer"]}
        report = evaluate_evaluation_set(fixture, _recorded_answer_fn(own_caliber))
        assert report["answer_correctness"] == 1.0, f"{pair_id} fails on its own caliber"

        crossed = {left["id"]: right["answer"], right["id"]: left["answer"]}
        report = evaluate_evaluation_set(fixture, _recorded_answer_fn(crossed))
        assert report["answer_correctness"] == 0.0, f"{pair_id} leaks: the other department still scores"


def test_business_evaluation_100_runs_per_tier_and_p95_sample_reaches_100(tmp_path):
    from app.quality.eval import evaluate_evaluation_set

    rows = _load_rows(EVALUATION_100_PATH)

    full = tmp_path / "business_evaluation_100.jsonl"
    _write_fixture(full, rows)
    report = evaluate_evaluation_set(full, _gold_answer_fn(rows))
    assert report["total"] == len(rows)
    assert report["answer_correctness"] == 1.0
    assert report["evidence_coverage"] == 1.0
    assert report["unsupported_claim_rate"] == 0.0
    assert report["latency_ms"]["count"] >= MIN_ROWS, "P95 needs at least 100 latency samples"
    assert report["latency_ms"]["p95"] > 0

    for tier in EVALUATION_TIERS:
        subset = [row for row in rows if row["tier"] == tier]
        path = tmp_path / f"{tier}.jsonl"
        _write_fixture(path, subset)
        tier_report = evaluate_evaluation_set(path, _gold_answer_fn(subset))
        assert tier_report["total"] == len(subset) >= MIN_TIER_ROWS
        assert tier_report["answer_correctness"] == 1.0
        assert tier_report["evidence_coverage"] == 1.0
        assert tier_report["latency_ms"]["count"] == len(subset)
        assert tier_report["category_metrics"], f"tier {tier} produced no category metrics"


def test_business_evaluation_100_questions_are_not_padded_with_duplicates():
    rows = _load_rows(EVALUATION_100_PATH)
    # 成对题只差部门名，属最小对照设计，本来就要求高度相似，故排除在重复率统计之外。
    solo = [row for row in rows if "conflict_pair" not in row]

    assert len({row["question"] for row in rows}) == len(rows)

    def bigrams(text):
        compact = "".join(str(text).split())
        return {compact[index:index + 2] for index in range(len(compact) - 1)} or {compact}

    grams = {row["id"]: bigrams(row["question"]) for row in solo}
    worst = 0.0
    keys = sorted(grams)
    for position, left_id in enumerate(keys):
        for right_id in keys[position + 1:]:
            left_grams = grams[left_id]
            right_grams = grams[right_id]
            union = left_grams | right_grams
            worst = max(worst, len(left_grams & right_grams) / len(union))

    assert worst < 0.7, f"near-duplicate non-conflict questions: {worst:.3f}"
