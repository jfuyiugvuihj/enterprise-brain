# -*- coding: utf-8 -*-
"""R60 判据⑤＋⑦第三把 —— 一键回滚演练的账必须**少一步就红**，不许"跑了就行"。

判据⑤要的是"回到上一 ``index_version`` 全量恢复**真跑一次**并留证"。真跑一次的读数落在
``docs/testing/r60-chroma-writeoff-ledger-2026-10-03.json``，本文件是它那本账的判器：

* **步序是判据，不是目录**：十步逐枚点名，缺任一枚当场红 —— 那正是⑦第三把「回滚演练少一步
  必须红」的可复跑形式。步名在而读数为空同样红：R587 已经抓过一次"备份日志全绿、恢复库里两枚
  库级 setting 却是 MISSING"，因为"上报"不等于"判红"。
* **备份必须连库级 GUC 成对**：``backup`` 那一步没有 ``globals`` 这一对产物（.json + .sql）
  就红。R587 立的规矩，本单不许把它降回"照实上报"。
* **恢复的目标只能是独立演练库**：写侧库名必须逐字等于 ``eb_r575_drill``；出现演示库
  ``enterprise_brain`` 当写侧目标，本判器直接判红。第④格同样只写在沙盒库里。
* **删账也逐腿点名**：``delete_proof`` 少一枚（只住 PG 的 / 两腿都持有的），或"两腿都持有"那枚的
  遗留腿增量不为负，判器直接红 —— 那正是「删了 PG、Chroma 还留着孤儿行」的形状（判据③）。
* **两臂必须读出不同的结果**：停写态（``pgvector``）遗留腿增量必须为 0，回滚档（``chroma``）
  遗留腿增量必须为正、且 PG 那一腿也得为正 —— 两臂同形就是停写没生效，或者把双写关成了零写。

盲区（诚实写明）：本文件判的是**账的形状与自洽**，它证不了 PostgreSQL 的恢复行为，也证不了那
1008 枚向量真恢复回来了 —— 后者由在册件 ``scripts/r575_vector_restore_drill.py`` 在真机上那一轮
回答（它的离线钉在 ``tests/test_r575_vector_restore_drill.py``；本单只读复用，一枚都不改）。
"""

from __future__ import annotations

import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
LEDGER = REPO / "docs" / "testing" / "r60-chroma-writeoff-ledger-2026-10-03.json"

#: 唯一允许被写的那枚库名（R575 的演练库；本单第④格也写在它里面）。
SANDBOX_DB = "eb_r575_drill"
PRODUCTION_DB = "enterprise_brain"

#: 十步，逐枚点名。顺序即工序：备份在恢复之前，恢复在对账之前，清理在最后。
DRILL_STEPS = (
    "preflight",
    "backup",
    "restore",
    "reconcile",
    "recall",
    "writeoff-probe",
    "rollback-knob",
    "index-rollback",
    "postflight",
    "cleanup",
)

#: 每一步必须交回的读数键。本文件判"有没有交回读数"，判不了读数对不对 —— 对不对由
#: scripts/r575_vector_restore_drill.py 自己的七项对账与 tests/test_r575_* 那族管。
REQUIRED_READINGS = {
    "preflight": ("container", "image", "pgvector_version", "databases_before",
                  "production_vector_count"),
    "backup": ("archive", "archive_sha256", "bytes", "globals"),
    "restore": ("drill_db", "archive_sha256", "globals_applied", "globals_verified"),
    "reconcile": ("compared_items", "vector_fingerprint_source",
                  "vector_fingerprint_drill", "differences"),
    "recall": ("queries", "top_k", "only_in_source", "only_in_drill",
               "max_rank_shift", "ef_search_seen_in_session"),
    "writeoff-probe": ("index_backend", "pg_count_before", "pg_count_after",
                       "legacy_count_before", "legacy_count_after", "written_chunks"),
    "rollback-knob": ("index_backend", "pg_count_before", "pg_count_after",
                      "legacy_count_before", "legacy_count_after", "written_chunks"),
    "index-rollback": ("ledger_source", "index_id", "version_before", "version_after",
                       "previous_index_version_id", "restored_status"),
    "postflight": ("production_vector_count_before", "production_vector_count_after",
                   "chunk_vectors_equal", "documents_equal", "chunks_equal"),
    "cleanup": ("drill_dropped", "databases_after_cleanup", "residue_extra",
                "residue_missing"),
}

#: "必须为空"的读数：这些键非空就是这一步没过，而不是"有读数就行"。
MUST_BE_EMPTY = ("differences", "only_in_source", "only_in_drill",
                 "residue_extra", "residue_missing")

#: 写侧读数里出现这几枚库名就是越界（第④格与演练都只准碰沙盒库）。
FORBIDDEN_WRITE_TARGETS = (PRODUCTION_DB,)


def _no_reading(value) -> bool:
    """None / 空串 / 空容器 ＝ "这一步没交回读数"。0 与 False 是读数，不是空。"""
    return value is None or value == "" or value == [] or value == {}


def _as_count(value):
    """行数是 int 读数；空值/坏值一律当作"这一步没交回行数"，判器不许为此抛异常。"""
    if _no_reading(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _delta(payload, prefix):
    """前后之差；任一端不是行数读数就回 None —— 空读数由上面的逐键检查判红，不在这里重复报。"""
    before = _as_count(payload.get(prefix + "_count_before"))
    after = _as_count(payload.get(prefix + "_count_after"))
    if before is None or after is None:
        return None
    return after - before


def check_ledger(ledger: dict) -> list:
    """Return every problem with the drill's evidence ledger. Empty list == 达标。"""
    problems: list = []
    if str(ledger.get("ticket") or "") != "R60":
        problems.append("这本账不是 R60 的回滚演练账（ticket 应逐字等于 R60）")
    steps = ledger.get("steps")
    if not isinstance(steps, dict):
        return problems + ["steps 不是一本账（应为逐步骤的字典）"]
    missing = [name for name in DRILL_STEPS if name not in steps]
    if missing:
        problems.append("少了这些步：" + ", ".join(missing))
    extra = sorted(name for name in steps if name not in DRILL_STEPS)
    if extra:
        problems.append("账里有没登记的步：" + ", ".join(extra))
    for name in DRILL_STEPS:
        payload = steps.get(name)
        if not isinstance(payload, dict):
            continue
        if payload.get("ok") is not True:
            problems.append(f"{name}: ok 不为 true（{payload.get('ok')!r}）")
        for key in REQUIRED_READINGS[name]:
            if key not in payload:
                problems.append(f"{name}: 缺读数 {key}")
            elif key not in MUST_BE_EMPTY and _no_reading(payload[key]):
                problems.append(f"{name}: 读数 {key} 是空值")
        for key in MUST_BE_EMPTY:
            if key in payload and payload[key]:
                problems.append(f"{name}: {key} 非空 —— {payload[key]!r}")
    pre, post = steps.get("preflight") or {}, steps.get("postflight") or {}
    if pre and post:
        before = pre.get("production_vector_count")
        after = post.get("production_vector_count_after")
        if isinstance(before, int) and isinstance(after, int) and before != after:
            problems.append("生产库在演练期间被改动过（前后行数不等）")
        for key in ("chunk_vectors_equal", "documents_equal", "chunks_equal"):
            if key in post and post[key] is not True:
                problems.append(f"postflight: {key} 不为 true")
    restore = steps.get("restore") or {}
    if str(restore.get("drill_db") or "") != SANDBOX_DB:
        problems.append(f"恢复目标必须是独立演练库 {SANDBOX_DB}，实为 "
                        f"{restore.get('drill_db')!r}")
    for name in ("writeoff-probe", "rollback-knob", "restore"):
        payload = steps.get(name) or {}
        target = str(payload.get("database") or payload.get("drill_db") or "")
        if target in FORBIDDEN_WRITE_TARGETS:
            problems.append(f"{name}: 写侧指到了 {target}（演示库一行都不许动）")
    write = steps.get("writeoff-probe") or {}
    rollback = steps.get("rollback-knob") or {}
    if write and rollback:
        write_pg = _delta(write, "pg")
        write_legacy = _delta(write, "legacy")
        rollback_pg = _delta(rollback, "pg")
        rollback_legacy = _delta(rollback, "legacy")
        if write.get("index_backend") != "pgvector":
            problems.append("writeoff-probe 的 index_backend 不是 pgvector")
        if rollback.get("index_backend") != "chroma":
            problems.append("rollback-knob 的 index_backend 不是 chroma（回滚通路那一档）")
        if write_legacy is not None and write_legacy != 0:
            problems.append(f"停写态里遗留腿还涨了 {write_legacy} 行（判据①第一半不达标）")
        if write_pg is not None and write_pg <= 0:
            problems.append(f"停写态里 PG 那一腿没涨行（+{write_pg}），第④格没量到")
        if rollback_legacy is not None and rollback_legacy <= 0:
            problems.append("开关退回 chroma 之后遗留腿仍不涨行：退路被拆了（判据②不达标）")
        if rollback_pg is not None and rollback_pg <= 0:
            problems.append("开关退回 chroma 之后 PG 那一腿也不涨行：双写被关成了零写")
    if write:
        proofs = write.get("delete_proof") or {}
        for label, key, shape in (
            ("只住在 PG 的那枚文档", "pg_only_document", "删不掉（判据③的第④格形状）"),
            ("两腿都持有的那枚文档", "held_by_both_legs",
             "遗留腿没删干净：PG 删了、Chroma 留着孤儿行（判据③）"),
        ):
            proof = proofs.get(key) or {}
            if not proof:
                problems.append(f"writeoff-probe 缺 delete_proof.{key} 的删账：{label}未证")
                continue
            pg_gone = _delta(proof, "pg")
            legacy_gone = _delta(proof, "legacy")
            if pg_gone is None or legacy_gone is None:
                problems.append(f"delete_proof.{key} 的前后行数是空值，判不了删没删")
            elif pg_gone >= 0:
                problems.append(f"{label}{shape}")
            elif key == "held_by_both_legs" and legacy_gone >= 0:
                problems.append(f"{label}{shape}")
    cleanup = steps.get("cleanup") or {}
    if cleanup and cleanup.get("drill_dropped") is not True:
        problems.append("cleanup: 演练库没删干净（drill_dropped 不为 true）")
    return problems


@pytest.fixture(scope="module")
def signed_ledger() -> dict:
    if not LEDGER.exists():
        raise AssertionError(
            f"{LEDGER.relative_to(REPO)} 不在盘上：判据⑤要求真跑一次的读数进纸，"
            "本文件的绿必须由那本账撑着，不由这段代码自己撑着")
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def test_the_signed_ledger_passes_the_gate(signed_ledger):
    """真跑那一次的账必须逐格达标；任何一格红，本用例就红。"""
    assert check_ledger(signed_ledger) == []


@pytest.mark.parametrize("step", DRILL_STEPS)
def test_dropping_any_step_reddens_the_ledger(signed_ledger, step):
    """判据⑦第三把：回滚演练少一步必须红。"""
    damaged = json.loads(json.dumps(signed_ledger))
    del damaged["steps"][step]
    problems = check_ledger(damaged)
    assert any(step in item for item in problems), f"摘掉 {step} 这一步，判器没响"


@pytest.mark.parametrize("step", DRILL_STEPS)
def test_a_step_with_blank_readings_reddens_the_ledger(signed_ledger, step):
    """少一步的另一种形状：步名还在、读数是空的 —— R587 已经抓过一次这种假绿。"""
    damaged = json.loads(json.dumps(signed_ledger))
    payload = damaged["steps"][step]
    for key in REQUIRED_READINGS[step]:
        if key in payload:
            payload[key] = ""
    assert check_ledger(damaged), f"{step} 的读数清空之后判器仍然全绿"


def test_the_guc_pair_is_a_gate_not_a_note(signed_ledger):
    """R587 的规矩进本单的账：备份少了成对的库级 setting 产物就红。"""
    damaged = json.loads(json.dumps(signed_ledger))
    damaged["steps"]["backup"]["globals"] = {}
    assert any(item.startswith("backup") for item in check_ledger(damaged))


def test_the_write_side_never_names_the_production_db(signed_ledger):
    damaged = json.loads(json.dumps(signed_ledger))
    damaged["steps"]["writeoff-probe"]["database"] = PRODUCTION_DB
    assert any("写侧" in item for item in check_ledger(damaged))


def test_the_two_arms_must_disagree(signed_ledger):
    """停写态与回滚档读出同一对增量，就等于没停写：这一枚钉不许两臂同形。"""
    damaged = json.loads(json.dumps(signed_ledger))
    write = damaged["steps"]["writeoff-probe"]
    write["legacy_count_after"] = write["legacy_count_before"] + (
        write["pg_count_after"] - write["pg_count_before"])
    assert any("遗留腿还涨" in item for item in check_ledger(damaged))


def test_a_delete_that_misses_pg_rows_reddens_the_ledger(signed_ledger):
    """判据③：演练账里"只住在 PG 的文档删不掉"这一形状必须红。"""
    damaged = json.loads(json.dumps(signed_ledger))
    proof = damaged["steps"]["writeoff-probe"]["delete_proof"]["pg_only_document"]
    proof["pg_count_after"] = proof["pg_count_before"]
    assert any("删不掉" in item for item in check_ledger(damaged))
