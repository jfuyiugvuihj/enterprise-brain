"""R595 常驻钉（二）：停表帽那一格——帽值现读、命中单列、且**不进判据口径的 p95**。

对着的病：计划书 ``:384``（R440 同笔新增的硬要求）——「命中停表帽的题必须单列一格报数，
既不许从 p95 里悄悄摘掉，也不许混进『正常慢答』当成模型的问题；每轮跑分的抬头必须写停表帽命中 N 枚」。
判据⑤ 反证一把就在这一枚钉上：**把命中单列那一格从纸面上摘掉，本文件必红**。

三条命中路径各钉一枚：
* 帽值不是抄的：``--transport-source`` 换一份合成量具件（42 s / 7 s），生效值跟着走 ⇒ 写死 300 的件当场红。
* 量具自己宣告停表（``kind == "queued_stalled"``）即使 wall_ms 远小于帽值也算命中。
* wall_ms 落进帽带 ``[cap, cap+一枚轮询间隔]`` 也算命中——这条**必须存在**：R440 在册凭据
  ``run9 / chat-11 / wall_ms=300108.2`` 的 ``kind`` 是 ``ok``（``docs/testing/sidecar-run9.jsonl`` 原文），只认 kind 会漏掉它。
超帽带（越过帽值＋轮询间隔而 kind 不是停表）另立一格点名并**照旧进 p95**：不许摘。
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r595_latency_readout", REPO_ROOT / "scripts" / "r595_latency_readout.py")
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)

BANK = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"
RUN9_ANSWERS = REPO_ROOT / "docs" / "testing" / "answers-run9.jsonl"
RUN9_SIDECAR = REPO_ROOT / "docs" / "testing" / "sidecar-run9.jsonl"


def write_jsonl(path: Path, rows) -> None:
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def qa_case(tmp_path, walls, kinds=None, label="cap"):
    """问答类若干枚：wall_ms 与 kind 由调用方给，latency_ms 一律与 wall_ms 同数（本钉只管帽）。"""
    kinds = kinds or ["ok"] * len(walls)
    fixture = [{"id": "q-%02d" % (index + 1), "tier": "问答", "category": "文档问答", "question": "?"}
               for index in range(len(walls))]
    answers = [{"id": row["id"], "answer": "略", "evidence": [], "latency_ms": walls[index]}
               for index, row in enumerate(fixture)]
    sidecar = [{"id": row["id"], "kind": kinds[index], "attempt": 1, "wall_ms": walls[index]}
               for index, row in enumerate(fixture)]
    paths = {}
    for name, rows in (("fixture", fixture), ("answers", answers), ("sidecar", sidecar)):
        path = Path(tmp_path) / ("%s-%s.jsonl" % (name, label))
        write_jsonl(path, rows)
        paths[name] = path
    return paths, mod.collect(paths["answers"], paths["fixture"], paths["sidecar"],
                              transport_source=mod.DEFAULT_TRANSPORT_SOURCE, label=label)


def synthetic_transport(tmp_path, cap="42", poll="7.0") -> Path:
    path = Path(tmp_path) / ("transport-cap%s.py" % cap.replace(".", "_"))
    path.write_text(
        "import os\n"
        'QUEUE_STALL_SECONDS = float(os.getenv("EVAL_QUEUE_STALL_SECONDS", "%s"))\n'
        'QUEUE_POLL_INTERVAL = float(os.getenv("EVAL_QUEUE_POLL_INTERVAL_SECONDS", "%s"))\n' % (cap, poll),
        encoding="utf-8")
    return path


def test_cap_value_is_read_live_from_the_transport_source(tmp_path):
    real = mod.stall_cap(mod.DEFAULT_TRANSPORT_SOURCE)
    assert real["cap_ms"] == 300000.0 and real["poll_ms"] == 3000.0
    assert real["cap_line"] > 0 and "QUEUE_STALL_SECONDS" in real["cap_text"]
    assert real["cap_env"] == "EVAL_QUEUE_STALL_SECONDS"          # env 名也是现读，不是抄的
    fake = mod.stall_cap(synthetic_transport(tmp_path, "42", "7.0"))
    assert fake["cap_ms"] == 42000.0 and fake["poll_ms"] == 7000.0
    assert fake["cap_line"] == 2                                   # 行号来自那份件自己
    assert fake["cap_default"] == "42" and fake["poll_default"] == "7.0"   # 字面默认也从那份件读


def test_environment_override_moves_the_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_QUEUE_STALL_SECONDS", "77")
    monkeypatch.setenv("EVAL_QUEUE_POLL_INTERVAL_SECONDS", "5")
    cap = mod.stall_cap(synthetic_transport(tmp_path, "42", "7.0"))
    assert cap["cap_ms"] == 77000.0 and cap["poll_ms"] == 5000.0
    assert cap["cap_from_env"] is True


def test_cap_hit_is_listed_and_out_of_the_caliber_p95(tmp_path):
    """摘掉命中单列那一格 ⇒ 本钉必红（判据⑤ 反证一把）。"""
    walls = [1000.0, 2000.0, 3000.0, 300108.2]
    paths, data = qa_case(tmp_path, walls)
    assert [hit["id"] for hit in data["hits"]] == ["q-04"]
    cell = data["cells"][mod.GROUP_QA]
    assert (cell["n"], cell["n_measured"], cell["n_used"], cell["n_hits"]) == (4, 4, 3, 1)
    assert cell["p95_rank"] == 3000.0                  # 判据口径：命中那一枚不进 p95
    assert cell["p95_rank_inclusive"] == 300108.2      # 含帽那一格：一枚都不许悄悄摘掉
    assert cell["avg"] == round((1000.0 + 2000.0 + 3000.0) / 3, 1)
    text = "\n".join(mod.render(data))
    assert text.splitlines()[0].startswith("停表帽命中 1 枚")
    assert "### 停表帽命中" in text
    assert "q-04 ｜ wall_ms=300108.2 ms" in text
    assert "含停表帽命中那一格（一枚都不摘）：n=4 p95(最近秩)=300108.2 ms" in text
    assert "帽命中 0 枚" in text                        # 整表之外的群不许被误报成有命中


def test_a_group_without_hits_reports_zero_hits_not_the_global_count(tmp_path):
    """命中数只在**本群成员**里数：全局 1 枚不许把零命中的群印成「帽命中 1 枚」。"""
    fixture = [{"id": "q-01", "tier": "问答", "category": "文档问答", "question": "?"},
               {"id": "a-01", "tier": "分析", "category": "Excel计算", "question": "?"}]
    walls = {"q-01": 300108.2, "a-01": 5000.0}
    answers = [{"id": key, "answer": "略", "evidence": [], "latency_ms": value}
               for key, value in sorted(walls.items())]
    sidecar = [{"id": key, "kind": "ok", "attempt": 1, "wall_ms": value}
               for key, value in sorted(walls.items())]
    paths = {}
    for name, rows in (("fixture", fixture), ("answers", answers), ("sidecar", sidecar)):
        path = Path(tmp_path) / ("%s-mix.jsonl" % name)
        write_jsonl(path, rows)
        paths[name] = path
    data = mod.collect(paths["answers"], paths["fixture"], paths["sidecar"],
                       transport_source=mod.DEFAULT_TRANSPORT_SOURCE, label="mix")
    assert data["cells"][mod.GROUP_QA]["n_hits"] == 1
    assert data["cells"][mod.GROUP_ANALYSIS_REPORT]["n_hits"] == 0
    assert data["cells"][mod.GROUP_ANALYSIS_REPORT]["n_used"] == 1
    assert data["cells"][mod.GROUP_ALL]["n_hits"] == 1


def test_kind_stalled_counts_even_below_the_cap(tmp_path):
    paths, data = qa_case(tmp_path, [5000.0], kinds=[mod.STALL_KIND], label="stalled")
    assert [hit["id"] for hit in data["hits"]] == ["q-01"]
    assert "kind=queued_stalled" in data["hits"][0]["via"]
    assert data["cells"][mod.GROUP_QA]["n_used"] == 0
    assert data["cells"][mod.GROUP_QA]["p95_rank"] is None       # 一群只剩命中 ⇒ 明写无量，不补 0


def test_above_band_is_named_but_never_removed(tmp_path):
    """309 秒那一枚（run13 的 insight-07 形状）不是停表帽 ⇒ 点名，但照旧进 p95。"""
    paths, data = qa_case(tmp_path, [1000.0, 309301.6], kinds=["ok", "approval_failed"], label="above")
    assert data["hits"] == []
    assert [row["id"] for row in data["above"]] == ["q-02"]
    cell = data["cells"][mod.GROUP_QA]
    assert (cell["n_used"], cell["p95_rank"]) == (2, 309301.6)
    assert cell["p95_rank_inclusive"] == cell["p95_rank"]
    text = "\n".join(mod.render(data))
    assert "请总控判它慢在哪：1 枚" in text


def test_run9_book_credential_is_reproduced(tmp_path):
    """R440 的凭据本身就是判据：run9 的 chat-11 wall_ms=300108.2 恰等帽值，本件必须自己抓出来。"""
    data = mod.collect(RUN9_ANSWERS, BANK, RUN9_SIDECAR,
                       transport_source=mod.DEFAULT_TRANSPORT_SOURCE, label="run9")
    assert [hit["id"] for hit in data["hits"]] == ["chat-11"]
    assert data["hits"][0]["wall_ms"] == 300108.2
    assert data["hits"][0]["kind"] == "ok"           # 只认 kind 的判据会漏掉在册这一枚 ⇒ 帽带那一档不许摘
    assert data["cells"][mod.GROUP_ALL]["p95_rank_inclusive"] == 154509.1   # 板上「整表 p95 154.5 s」
    assert data["cells"][mod.GROUP_ALL]["p95_rank"] == 140878.8            # 剔帽后（信息位）
    assert data["tiers"]["问答"]["p95_rank_inclusive"] == 125225.2         # 板上「问答档 n=50 p95 125.2 s」
    assert data["tiers"]["问答"]["n"] == 50 and data["cells"][mod.GROUP_QA]["n"] == 64
    assert "\n".join(mod.render(data)).splitlines()[0] == "停表帽命中 1 枚（帽值 300000.0 ms (300.0 s)，现读自 eval_transport_ask_v2.py:201）"


def test_scale_check_survives_a_cap_hit(tmp_path):
    """剔帽之后的那把 p95 仍然必须与在册 build_latency_cell 同一枚数。"""
    paths, data = qa_case(tmp_path, [1000.0, 2000.0, 300108.2], label="scale")
    assert data["scale"][mod.GROUP_QA]["agree"] is True
    assert data["scale"][mod.GROUP_QA]["inbook_p95"] == 2000.0
    assert not data["ledger_error"]
