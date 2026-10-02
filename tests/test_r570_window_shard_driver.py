# -*- coding: utf-8 -*-
"""R570 常驻钉 —— 钉住长跑窗断点保护驱动的形状，七格判据一枚都不许是摆设。

七格 ↔ 用例（按派工词编号逐枚点名；这张表由 ``test_the_header_mapping_names_only_real_cases``
   自证——表里点了不存在的用例、或用例没进表，当场红，别手抄过期）：
① 断点粒度到题／分片不多写 sidecar 行 → ``test_shard_size_default_is_one_question_per_shard`` ＋
   ``test_sharding_writes_exactly_one_sidecar_row_per_question`` ＋
   ``test_the_real_collector_is_driven_one_shard_per_question``（真采集器 --dry-run，零模型调用）
② 幂等 ``to run=0`` → ``test_rerun_reports_to_run_zero_and_reasks_nothing``
③ 局部失败局部补 → ``test_only_the_missing_shards_get_repaired`` ＋
   ``test_a_shard_that_answered_empty_is_not_counted_as_done`` ＋
   ``test_a_failed_shard_is_repaired_in_the_next_round``（补跑轮取的是差集，不是整窗重打）
④ 合并仍走覆盖闸／拒合并非零 → ``test_merge_follows_fixture_order`` ＋
   ``test_a_short_shard_refuses_merge_non_zero`` ＋ ``test_an_empty_answer_row_refuses_merge`` ＋
   ``test_a_duplicate_answer_row_across_shards_refuses_merge`` ＋
   ``test_dry_run_samples_are_refused_as_a_baseline`` ＋ ``test_counter_evidence_c_no_refusal_ever_exits_zero``
⑤ 五项指纹闸 → ``test_each_of_the_five_fingerprint_keys_gates_reuse``（逐枚点名不符的那一枚）＋
   ``test_the_fingerprint_gate_covers_the_merge_door_too`` ＋
   ``test_a_closed_docker_still_lets_a_finished_window_be_committed`` ＋
   ``test_counter_evidence_a_blinding_the_fingerprint_gate_reigns_a_mixed_baseline``
⑥ 连续失联早停 → ``test_dead_streak_stops_the_window_and_keeps_progress`` ＋
   ``test_a_collector_that_cannot_spawn_stops_the_window_not_the_driver`` ＋
   ``test_counter_evidence_b_the_dead_streak_threshold_is_load_bearing``
⑦ 读路径双向真拦 ＋ 补法文案 → ``test_expect_backend_pgvector_refuses_when_container_is_empty`` ＋
   ``test_expect_backend_chroma_refuses_when_container_is_pgvector`` ＋
   ``test_the_read_path_pin_passes_when_it_is_true`` ＋
   ``test_an_unreachable_container_is_not_read_as_chroma`` ＋
   ``test_a_real_run_refuses_before_touching_the_collector``
④⑥ 的口径本身（退出码与默认值不许漂）→ ``test_the_exit_code_and_default_tables_are_pinned``
七格之外的两道机械闸 → ``test_the_same_tag_cannot_be_claimed_twice``（同 tag 单实例）＋
   ``test_the_header_mapping_names_only_real_cases``（本表自证）

反证牙（在册 ``counter_evidence`` 命名，一枚都不分层出门）：
  a ``test_counter_evidence_a_blinding_the_fingerprint_gate_reigns_a_mixed_baseline`` 摘指纹闸⇒敢混库
  b ``test_counter_evidence_b_the_dead_streak_threshold_is_load_bearing`` 摘阈值⇒死后端上空转整窗
  c ``test_counter_evidence_c_no_refusal_ever_exits_zero`` 任何 REFUSE 退成 0 即红
  d ``test_counter_evidence_d_the_driver_never_writes_inside_the_repo`` 驱动往仓内写一个字节即红
  e ``test_counter_evidence_e_this_file_carries_no_downgrade_marker`` 本件零降级记号
  f ``test_counter_evidence_f_no_test_here_shells_out_to_docker`` 全轮零 docker（subprocess 换会炸的桩）

纪律：全程零模型调用（真采集器只以 ``--dry-run`` 出场）、零 docker（容器读数走注入的假读数单点）、
产物只落 ``tmp_path``，仓内一字节不写。
"""

import importlib.util
import io
import json
import os
import re
import socket
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r570_eval_window_shard_driver", REPO_ROOT / "scripts" / "eval_window_shard_driver.py")
drv = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(drv)

TRANSPORT = "eval_transport_ask_v2:transport"


def mini_fixture(tmp_path: Path, count: int = 6, prefix: str = "r570"):
    """自造迷你评测集（派工词指定 6–12 枚）：题号一律带 r570- 前缀，绝不与在册 105 题同名。"""
    rows = []
    for index in range(1, count + 1):
        rows.append({
            "id": "%s-%02d" % (prefix, index),
            "tier": "冒烟",
            "category": "断点演练",
            "question": "第 %d 题：这一片的终答是什么？" % index,
            "answer": "演练答案-%02d" % index,
            "must_contain": ["演练答案"],
            "requires_evidence": False,
        })
    path = tmp_path / ("mini-%s-%d.jsonl" % (prefix, count))
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                    encoding="utf-8")
    return path, [row["id"] for row in rows]


def fake_docker(monkeypatch, revision="abc1234", index_backend="pgvector", reachable=True):
    """容器读数的注入点：测试里一枚 docker 都不许真调（派工词硬要求）。"""
    asked = []

    def _read(shell, container, timeout=25.0):
        asked.append((shell, container))
        if not reachable:
            return False, "docker: Error: No such container: " + container
        if shell.startswith("cat /app/BUILD_INFO"):
            return True, "revision=" + revision
        return True, "SET=" + (index_backend or "")

    monkeypatch.setattr(drv, "run_in_container", _read)
    return asked


class FakeCollector:
    """假采集器：一题一行写答案件 ＋ 一题一行追加进 env 里那枚 EVAL_SIDECAR。

    它复刻的只是在册 transport 的落账契约（``scripts/eval_transport_ask_v2.py:1281`` 每题
    ``SIDECAR.open("a")`` 一行），零 HTTP、零模型调用；分片会不会多写一行，就从这里量得出来。
    """

    def __init__(self, produce=True, answer_source=None):
        self.produce = produce
        self.answer_source = answer_source or TRANSPORT
        self.calls = []

    def __call__(self, cmd, repo, env):
        index = cmd.index("--fixture") + 1
        out = cmd.index("--output") + 1
        rows = [json.loads(line) for line in
                Path(cmd[index]).read_text(encoding="utf-8").splitlines() if line.strip()]
        self.calls.append({
            "ids": [str(row["id"]) for row in rows],
            "cmd": list(cmd),
            "sidecar": env.get("EVAL_SIDECAR"),
            "dry_run": "--dry-run" in cmd,
        })
        if not self.produce:
            return 1, "GATE FAILED: missing %d fixture id(s)" % len(rows)
        payload = []
        for row in rows:
            payload.append({
                "id": str(row["id"]),
                "answer": "演练答案 " + str(row["id"]),
                "evidence": [{"source_type": "fake", "source_name": "fake", "locator": None,
                              "excerpt": "x"}],
                "latency_ms": 12.5,
                "first_token_at": None,
                "thinking_chars": None,
                "tool_calls": None,
                "answer_source": self.answer_source,
            })
        target = Path(cmd[out])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in payload),
                          encoding="utf-8")
        sidecar = Path(env["EVAL_SIDECAR"])
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        with sidecar.open("a", encoding="utf-8") as handle:
            for item in payload:
                handle.write(json.dumps({"id": item["id"], "kind": "ok", "answer_chars": 9},
                                        ensure_ascii=False) + "\n")
        return 0, "collected=%d of %d" % (len(payload), len(rows))


def run_driver(tmp_path, fixture, *args, **over):
    argv = ["--tag", over.pop("tag", "r570win"), "--fixture", str(fixture),
            "--tmp-dir", str(tmp_path)] + list(args)
    if "--python" not in " ".join(argv):
        argv += ["--python", over.pop("python", "FAKE-PYTHON")]
    for key, value in over.items():
        argv += [str(key), str(value)] if not isinstance(value, bool) else [str(key)]
    return drv.main(argv)


def asked_sidecar(tmp_path, tag="r570win"):
    return drv.read_jsonl_rows(tmp_path / (tag + "-sidecar.jsonl"))


def base_argv(tmp_path, fixture, tag="r570win", python="FAKE-PYTHON"):
    return ["--tag", tag, "--fixture", str(fixture), "--tmp-dir", str(tmp_path),
            "--python", python]


def shard_answers(tmp_path, tag, index):
    return Path(tmp_path) / (tag + ".shards") / ("%s-s%03d-answers.jsonl" % (tag, index))


# ============================ 判据 ①：断点粒度到题，且分片不多写证据行 ============================

def test_shard_size_default_is_one_question_per_shard(tmp_path):
    fixture, ids = mini_fixture(tmp_path, count=6)
    plan = drv.build_plan(ids, drv.DEFAULT_SHARD_SIZE)
    assert drv.DEFAULT_SHARD_SIZE == 1
    assert plan == [[rid] for rid in ids], "默认粒度不是逐题：断一次就要重打一串"
    cmd = drv.collector_command("PY", REPO_ROOT, tmp_path / "s.jsonl", tmp_path / "a.jsonl",
                                TRANSPORT, dry_run=False)
    assert cmd[3] == drv.COLLECTOR, "本件不许自己判读，只能调在册采集器"
    assert "--transport" in cmd and "--dry-run" not in cmd
    dry = drv.collector_command("PY", REPO_ROOT, tmp_path / "s.jsonl", tmp_path / "a.jsonl",
                                TRANSPORT, dry_run=True)
    assert "--dry-run" in dry and "--allow-sample" in dry
    assert "--transport" not in dry, "演练把真 transport 带上了：那是要打模型的形状"
    with pytest.raises(drv.Refuse):
        drv.build_plan(ids, 0)


def test_sharding_writes_exactly_one_sidecar_row_per_question(tmp_path, monkeypatch, capsys):
    fixture, ids = mini_fixture(tmp_path, count=6)
    fake_docker(monkeypatch)
    collector = FakeCollector()
    monkeypatch.setattr(drv, "invoke_collector", collector)
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    assert [call["ids"] for call in collector.calls] == [[rid] for rid in ids]
    assert len({call["sidecar"] for call in collector.calls}) == 1, "分片各写一本 sidecar：全账被切碎了"
    rows = asked_sidecar(tmp_path)
    assert [row["id"] for row in rows] == ids
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    rows_after_resume = asked_sidecar(tmp_path)
    assert len(rows_after_resume) == len(ids), "一次幂等复跑就多写行：分片在污染证据账"
    assert len({row["id"] for row in rows_after_resume}) == len(ids)
    capsys.readouterr()
    assert drv.main(base_argv(tmp_path, fixture) + ["--commit"]) == drv.RC_OK
    assert "duplicate=0" in capsys.readouterr().out


def test_the_real_collector_is_driven_one_shard_per_question(tmp_path, monkeypatch, capsys):
    """🔴 拿在册采集器自己跑一遍（``--dry-run`` 假 transport，零模型调用）：契约不许只对着替身演。"""
    fixture, ids = mini_fixture(tmp_path, count=3, prefix="r570real")
    fake_docker(monkeypatch)
    rc = drv.main(base_argv(tmp_path, fixture, tag="r570real", python=__import__("sys").executable)
                  + ["--run", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == drv.RC_OK, out
    for index, rid in enumerate(ids):
        rows = drv.read_jsonl_rows(shard_answers(tmp_path, "r570real", index))
        assert [str(row["id"]) for row in rows] == [rid], "这一片不是逐题一片"
        assert str(row := rows[0]) and rows[0]["answer"]
        assert rows[0]["answer_source"] == "dry-run"
    assert not (tmp_path / "r570real-sidecar.jsonl").exists(), "假 transport 不该产 sidecar；产了就是多写"
    capsys.readouterr()
    refused = drv.main(base_argv(tmp_path, fixture, tag="r570real",
                                 python=__import__("sys").executable) + ["--commit"])
    assert refused == drv.RC_REFUSE and "dry-run" in capsys.readouterr().out


# ============================ 判据 ②：幂等，一题都不许多打 ============================

def test_rerun_reports_to_run_zero_and_reasks_nothing(tmp_path, monkeypatch, capsys):
    fixture, ids = mini_fixture(tmp_path, count=5)
    fake_docker(monkeypatch)
    collector = FakeCollector()
    monkeypatch.setattr(drv, "invoke_collector", collector)
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    first = len(collector.calls)
    capsys.readouterr()
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    out = capsys.readouterr().out
    assert "to run=0" in out, out
    assert len(collector.calls) == first, "复跑重打了题：重打＝重付费＝假时延进 P95"


# ============================ 判据 ③：局部失败只补局部 ============================

def test_only_the_missing_shards_get_repaired(tmp_path, monkeypatch, capsys):
    fixture, ids = mini_fixture(tmp_path, count=6)
    fake_docker(monkeypatch)
    collector = FakeCollector()
    monkeypatch.setattr(drv, "invoke_collector", collector)
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    for index in (1, 4):
        shard_answers(tmp_path, "r570win", index).unlink()
    before = len(collector.calls)
    capsys.readouterr()
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    out = capsys.readouterr().out
    assert "already complete=4 to run=2" in out, out
    assert [call["ids"] for call in collector.calls[before:]] == [[ids[1]], [ids[4]]]


def test_a_shard_that_answered_empty_is_not_counted_as_done(tmp_path, monkeypatch, capsys):
    """「片成没成」只看行数会骗人：answer 为空的片必须仍算欠着（否则半窗会被当成全窗）。"""
    fixture, ids = mini_fixture(tmp_path, count=4)
    fake_docker(monkeypatch)
    collector = FakeCollector()
    monkeypatch.setattr(drv, "invoke_collector", collector)
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    path = shard_answers(tmp_path, "r570win", 2)
    rows = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    rows["answer"] = "   "
    path.write_text(json.dumps(rows, ensure_ascii=False) + "\n", encoding="utf-8")
    capsys.readouterr()
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    assert "already complete=3 to run=1" in capsys.readouterr().out


# ============================ 判据 ④：合并仍走覆盖闸，且一律非零退出 ============================

def test_merge_follows_fixture_order(tmp_path, monkeypatch, capsys):
    fixture, ids = mini_fixture(tmp_path, count=6)
    fake_docker(monkeypatch)
    monkeypatch.setattr(drv, "invoke_collector", FakeCollector())
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    assert drv.main(base_argv(tmp_path, fixture) + ["--commit"]) == drv.RC_OK
    merged = drv.read_jsonl_rows(tmp_path / "r570win-answers.jsonl")
    assert [row["id"] for row in merged] == ids, "合并顺序不是 fixture 原序"
    assert all(str(row["answer"]).strip() for row in merged)
    assert len({row["id"] for row in merged}) == len(ids)


def test_a_short_shard_refuses_merge_non_zero(tmp_path, monkeypatch, capsys):
    fixture, _ids = mini_fixture(tmp_path, count=5)
    fake_docker(monkeypatch)
    monkeypatch.setattr(drv, "invoke_collector", FakeCollector())
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    shard_answers(tmp_path, "r570win", 3).unlink()
    capsys.readouterr()
    rc = drv.main(base_argv(tmp_path, fixture) + ["--commit"])
    out = capsys.readouterr().out
    assert rc == drv.RC_REFUSE and rc != 0, "半窗被拼成了基线，且退出码还是 0"
    assert "拒合并半窗" in out
    assert not (tmp_path / "r570win-answers.jsonl").exists(), "拒合并却不该落件"


def test_an_empty_answer_row_refuses_merge(tmp_path, monkeypatch, capsys):
    fixture, ids = mini_fixture(tmp_path, count=3)
    fake_docker(monkeypatch)
    monkeypatch.setattr(drv, "invoke_collector", FakeCollector())
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    path = shard_answers(tmp_path, "r570win", 1)
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    row["answer"] = ""
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    capsys.readouterr()
    rc = drv.main(base_argv(tmp_path, fixture) + ["--commit"])
    assert rc == drv.RC_REFUSE, rc
    assert "空串" in capsys.readouterr().out


def test_a_duplicate_answer_row_across_shards_refuses_merge(tmp_path, monkeypatch, capsys):
    fixture, ids = mini_fixture(tmp_path, count=3)
    fake_docker(monkeypatch)
    monkeypatch.setattr(drv, "invoke_collector", FakeCollector())
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    path = shard_answers(tmp_path, "r570win", 2)
    stolen = json.loads(shard_answers(tmp_path, "r570win", 0).read_text(encoding="utf-8")
                        .splitlines()[0])
    path.write_text(json.dumps(stolen, ensure_ascii=False) + "\n", encoding="utf-8")
    capsys.readouterr()
    rc = drv.main(base_argv(tmp_path, fixture) + ["--commit"])
    assert rc == drv.RC_REFUSE, rc
    assert "跨片重复" in capsys.readouterr().out


def test_dry_run_samples_are_refused_as_a_baseline(tmp_path, monkeypatch, capsys):
    """样本≈满分：演练件拼成基线就是假话，这一格比「能不能合并」更要紧。"""
    fixture, _ids = mini_fixture(tmp_path, count=4)
    fake_docker(monkeypatch)
    monkeypatch.setattr(drv, "invoke_collector", FakeCollector(answer_source="dry-run"))
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    capsys.readouterr()
    assert drv.main(base_argv(tmp_path, fixture) + ["--commit"]) == drv.RC_REFUSE
    out = capsys.readouterr().out
    assert "answer_source=dry-run" in out and "基线" in out
    assert drv.main(base_argv(tmp_path, fixture) + ["--commit", "--allow-sample-merge"]) == drv.RC_OK
    assert "NOT 质量基线" in capsys.readouterr().out

# ============================ 判据 ⑤：五项指纹全等才准复用盘上旧片 ============================

def test_each_of_the_five_fingerprint_keys_gates_reuse(tmp_path, monkeypatch, capsys):
    fixture, _ids = mini_fixture(tmp_path, count=3)
    fake_docker(monkeypatch, revision="rev-A", index_backend="pgvector")
    monkeypatch.setattr(drv, "invoke_collector", FakeCollector())
    argv = base_argv(tmp_path, fixture) + ["--run", "--dry-run"]
    assert drv.main(argv) == drv.RC_OK
    capsys.readouterr()
    assert drv.main(argv) == drv.RC_OK
    assert "全等" in capsys.readouterr().out, "同条件续跑本该放行（不许把幂等也一起拒掉）"

    other = tmp_path / "other.jsonl"
    other.write_text(fixture.read_text(encoding="utf-8") + json.dumps(
        {"id": "r570-99", "question": "多一枚题", "answer": "另一枚"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    cases = [
        ("revision", ["--run", "--dry-run"], dict(revision="rev-B")),
        ("index_backend", ["--run", "--dry-run"], dict(index_backend="")),
        ("fixture_sha256", ["--run", "--dry-run"], None),
        ("transport", ["--run", "--dry-run", "--transport", "someone_else:transport"], None),
        ("shard_size", ["--run", "--dry-run", "--shard-size", "3"], None),
    ]
    for key, tail, readings in cases:
        if readings is not None:
            fake_docker(monkeypatch, **readings)
        target = other if key == "fixture_sha256" else fixture
        capsys.readouterr()
        rc = drv.main(base_argv(tmp_path, target) + tail)
        out = capsys.readouterr().out
        assert rc == drv.RC_REFUSE, (key, rc, out)
        assert key in out, (key, "REFUSE 没点名是哪一枚指纹不符：" + out)
        assert "另一种条件下采的" in out and "**" not in out, (key, out)
        fake_docker(monkeypatch, revision="rev-A", index_backend="pgvector")


def test_the_fingerprint_gate_covers_the_merge_door_too(tmp_path, monkeypatch, capsys):
    """采完之后换了镜像再收口：同一枚闸必须在 --commit 处也拦一次。"""
    fixture, _ids = mini_fixture(tmp_path, count=3)
    fake_docker(monkeypatch, revision="rev-A", index_backend="pgvector")
    monkeypatch.setattr(drv, "invoke_collector", FakeCollector())
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    fake_docker(monkeypatch, revision="rev-B", index_backend="pgvector")
    capsys.readouterr()
    assert drv.main(base_argv(tmp_path, fixture) + ["--commit"]) == drv.RC_REFUSE
    assert "合并前指纹复核不过" in capsys.readouterr().out


def test_a_closed_docker_still_lets_a_finished_window_be_committed(tmp_path, monkeypatch, capsys):
    """run12 的死法：Docker 停了，但活干完了。收口只比三枚离线指纹，不许拿「问不着」当不符。"""
    fixture, ids = mini_fixture(tmp_path, count=3)
    fake_docker(monkeypatch, revision="rev-A", index_backend="pgvector")
    monkeypatch.setattr(drv, "invoke_collector", FakeCollector())
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    fake_docker(monkeypatch, reachable=False)
    capsys.readouterr()
    assert drv.main(base_argv(tmp_path, fixture) + ["--commit"]) == drv.RC_OK
    out = capsys.readouterr().out
    assert "只比三枚离线指纹" in out and "committed 3 answers" in out
    assert [row["id"] for row in drv.read_jsonl_rows(tmp_path / "r570win-answers.jsonl")] == ids


# ============================ 判据 ⑥：连续失联早停，且保住已完成片 ============================

def test_dead_streak_stops_the_window_and_keeps_progress(tmp_path, monkeypatch, capsys):
    fixture, _ids = mini_fixture(tmp_path, count=6)
    fake_docker(monkeypatch)
    good = FakeCollector()
    monkeypatch.setattr(drv, "invoke_collector", good)
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    for index in (2, 3, 4, 5):
        shard_answers(tmp_path, "r570win", index).unlink()
    dead = FakeCollector(produce=False)
    monkeypatch.setattr(drv, "invoke_collector", dead)
    capsys.readouterr()
    rc = drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run", "--retries", "0"])
    out = capsys.readouterr().out
    assert rc == drv.RC_DEAD_BACKEND and rc == 3, (rc, out)
    assert len(dead.calls) == drv.DEAD_STREAK_DEFAULT == 4, "早停没在阈值上收，或在阈值前就收"
    assert "STOP" in out
    assert shard_answers(tmp_path, "r570win", 0).exists()
    assert shard_answers(tmp_path, "r570win", 1).exists()


def test_a_collector_that_cannot_spawn_stops_the_window_not_the_driver(tmp_path, monkeypatch, capsys):
    """``EB_EVAL_PYTHON`` 打错＝每片零产出，必须走判据 ⑥ 停窗（rc=3），不许把整窗炸成 traceback。

    这一枚**故意不打桩** ``invoke_collector``：让它真去 ``subprocess.run`` 一枚不存在的解释器，
    量的正是 ``except OSError`` 那一格——去掉它，本件当场以 FileNotFoundError 红。
    """
    fixture, _ids = mini_fixture(tmp_path, count=6)
    fake_docker(monkeypatch)
    rc = drv.main(base_argv(tmp_path, fixture, python="EB-EVAL-PYTHON-DOES-NOT-EXIST")
                  + ["--run", "--dry-run", "--retries", "0"])
    out = capsys.readouterr().out
    assert rc == drv.RC_DEAD_BACKEND, (rc, out)
    assert "STOP" in out and "解释器" in out, out
    assert "起不来" in out, "零产出那一行要写清是起不来，不是采集器报了 0 题"
    straight = drv.invoke_collector(["EB-EVAL-PYTHON-DOES-NOT-EXIST", "-c", "x"],
                                     Path.cwd(), dict(os.environ))
    assert straight[0] == 127 and "起不来" in straight[1], ("摘掉 except OSError 这枚即红", straight)
    assert not shard_answers(tmp_path, "r570win", 0).exists()
    assert drv.main(base_argv(tmp_path, fixture) + ["--plan"]) == drv.RC_OK, "停窗后盘上账要还能念"


# ============================ 判据 ⑦：读路径双向真拦 ＋ 补法文案 ============================

def test_expect_backend_pgvector_refuses_when_container_is_empty(tmp_path, monkeypatch, capsys):
    fixture, _ids = mini_fixture(tmp_path, count=3)
    asked = fake_docker(monkeypatch, index_backend="")
    rc = drv.main(base_argv(tmp_path, fixture) + ["--plan", "--expect-backend", "pgvector"])
    out = capsys.readouterr().out
    assert rc == drv.RC_REFUSE, out
    assert "docker compose up -d --force-recreate" in out, "REFUSE 必须给正解，不是只喊不通"
    assert "restart" in out and "不重读" in out
    assert any("printenv" not in shell for shell, _ in asked)
    assert 'printf SET=%s' in asked[0][0] or len(asked) > 1


def test_expect_backend_chroma_refuses_when_container_is_pgvector(tmp_path, monkeypatch, capsys):
    fixture, _ids = mini_fixture(tmp_path, count=3)
    fake_docker(monkeypatch, index_backend="pgvector")
    rc = drv.main(base_argv(tmp_path, fixture) + ["--plan", "--expect-backend", "chroma"])
    assert rc == drv.RC_REFUSE, rc
    out = capsys.readouterr().out
    assert "要钉的是 chroma" in out and "该变量为空" in out, out


@pytest.mark.parametrize("backend,expect", [("pgvector", "pgvector"), ("", "chroma")])
def test_the_read_path_pin_passes_when_it_is_true(tmp_path, monkeypatch, capsys, backend, expect):
    """正控：钉对了必须放行。只拦不放的闸等于把 --expect-backend 变成摆设的反面——拦死一切。"""
    fixture, _ids = mini_fixture(tmp_path, count=2)
    fake_docker(monkeypatch, index_backend=backend)
    assert drv.main(base_argv(tmp_path, fixture) + ["--plan", "--expect-backend", expect]) == drv.RC_OK
    assert "backend=%r" % backend in capsys.readouterr().out


def test_an_unreachable_container_is_not_read_as_chroma(tmp_path, monkeypatch, capsys):
    """「问不着」≠「读到空」：把这两件事混成一谈，chroma 那一半就是假绿。"""
    fixture, _ids = mini_fixture(tmp_path, count=2)
    fake_docker(monkeypatch, reachable=False)
    rc = drv.main(base_argv(tmp_path, fixture) + ["--plan", "--expect-backend", "chroma"])
    out = capsys.readouterr().out
    assert rc == drv.RC_REFUSE and "问不着" in out, out
    rc2 = drv.main(base_argv(tmp_path, fixture) + ["--plan", "--expect-backend", "sqlite"])
    assert rc2 == drv.RC_REFUSE and "只认 pgvector 或 chroma" in capsys.readouterr().out


def test_a_real_run_refuses_before_touching_the_collector(tmp_path, monkeypatch, capsys):
    fixture, _ids = mini_fixture(tmp_path, count=2)
    fake_docker(monkeypatch, reachable=False)
    collector = FakeCollector()
    monkeypatch.setattr(drv, "invoke_collector", collector)
    rc = drv.main(base_argv(tmp_path, fixture) + ["--run"])
    assert rc == drv.RC_REFUSE and collector.calls == [], capsys.readouterr().out


class FlakyCollector(FakeCollector):
    """第一发故意交白卷、第二发才成：判据 ③ 的「补跑轮」这条路只有它能量到。"""

    def __init__(self, flaky_id):
        FakeCollector.__init__(self)
        self.flaky_id = flaky_id
        self.seen = set()

    def __call__(self, cmd, repo, env):
        index = cmd.index("--fixture") + 1
        rows = [json.loads(line) for line in
                Path(cmd[index]).read_text(encoding="utf-8").splitlines() if line.strip()]
        rid = str(rows[0]["id"])
        if rid == self.flaky_id and rid not in self.seen:
            self.seen.add(rid)
            self.calls.append({"ids": [rid], "cmd": list(cmd), "sidecar": env.get("EVAL_SIDECAR"),
                               "dry_run": "--dry-run" in cmd})
            return 1, "GATE FAILED: missing 1 fixture id(s): " + rid
        self.seen.add(rid)
        return FakeCollector.__call__(self, cmd, repo, env)


def test_a_failed_shard_is_repaired_in_the_next_round(tmp_path, monkeypatch, capsys):
    """``--retries`` 不是装饰：第一发白卷的那一片，第二发要补回来。"""
    fixture, ids = mini_fixture(tmp_path, count=4)
    fake_docker(monkeypatch)
    flaky = FlakyCollector(ids[2])
    monkeypatch.setattr(drv, "invoke_collector", flaky)
    rc = drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run", "--retries", "1",
                                                  "--retry-sleep", "0"])
    out = capsys.readouterr().out
    assert rc == drv.RC_OK, out
    assert "第 2 轮补片" in out, out
    asked = [call["ids"][0] for call in flaky.calls]
    assert asked == ids + [ids[2]], ("补跑是整轮制，不是原地重试", asked)
    assert asked.count(ids[2]) == 2
    assert all(asked.count(i) == 1 for i in ids if i != ids[2]), "补跑轮把别的题重打了"
    assert shard_answers(tmp_path, "r570win", 2).exists()
    assert len(asked_sidecar(tmp_path)) == len(ids), "补跑轮把别的题重打了"
    # 负控：``--retries 0`` 时同一枚白卷片绝不许被补回来 —— 补回来的确实是补跑轮，不是运气
    again = FlakyCollector(ids[1])
    monkeypatch.setattr(drv, "invoke_collector", again)
    rc0 = drv.main(base_argv(tmp_path, fixture, tag="r570retry0") + ["--run", "--dry-run",
                                                           "--retries", "0", "--retry-sleep", "0"])
    capsys.readouterr()
    assert rc0 == drv.RC_SHARDS_OPEN and rc0 == 4, rc0
    assert [call["ids"][0] for call in again.calls] == ids, "retries=0 还去补跑：这一格没在尺上"


def test_the_same_tag_cannot_be_claimed_twice(tmp_path):
    """单实例闸：同 tag 第二次占位必须拒；换 tag 不互相挡；端口映射跨进程稳定。"""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    base = probe.getsockname()[1]
    probe.close()
    assert drv.lock_port("run13", 38820, 40) == drv.lock_port("run13", 38820, 40)
    held = drv.acquire_tag_lock("run13", base, 1)
    try:
        with pytest.raises(drv.Refuse) as refused:
            drv.acquire_tag_lock("run13", base, 1)
        assert refused.value.code == drv.RC_REFUSE
        assert "--force-recreate" not in str(refused.value)  # 这一格的补法与读路径无关
    finally:
        held.close()
    second = drv.acquire_tag_lock("run14", base, 1)
    second.close()


def test_the_exit_code_and_default_tables_are_pinned():
    """判据 ④⑥ 交给总控的是**数字**，不是形容词：退出码表与两枚默认值漂了，本件先红。

    本班现场真撞过一次「加载到的模块常量与盘上源码不符」（一次跑测报出 rc=5 这种表里
    根本不存在的数）⇒ 光靠 ``rc != 0`` 这种相对断言抓不到，必须把绝对值钉死。
    """
    assert (drv.RC_OK, drv.RC_REFUSE, drv.RC_DEAD_BACKEND, drv.RC_SHARDS_OPEN) == (0, 2, 3, 4)
    assert drv.DEFAULT_SHARD_SIZE == 1, "判据 ① 的「每题一片」就是这枚默认值"
    assert drv.DEAD_STREAK_DEFAULT == 4, "判据 ⑥ 派工词写死连续 4 片"
    assert drv.FINGERPRINT_KEYS == ("revision", "index_backend", "fixture_sha256", "transport",
                                   "shard_size"), "判据 ⑤ 五枚指纹，一枚不许多一枚不许少"
    assert drv.OFFLINE_FINGERPRINT_KEYS == ("fixture_sha256", "transport", "shard_size")
    assert len(drv.FINGERPRINT_KEYS) == 5 and len(drv.OFFLINE_FINGERPRINT_KEYS) == 3


# ============================ 反证牙（在册 counter_evidence 命名法） ============================

def test_counter_evidence_a_blinding_the_fingerprint_gate_reigns_a_mixed_baseline(tmp_path,
                                                                                  monkeypatch,
                                                                                  capsys):
    """牙 a：把指纹闸摘掉 ⇒ 换一份 fixture 也敢把旧片当本窗进度复用。"""
    fixture, _ids = mini_fixture(tmp_path, count=3)
    other = tmp_path / "other.jsonl"
    other.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    fake_docker(monkeypatch)
    collector = FakeCollector()
    monkeypatch.setattr(drv, "invoke_collector", collector)
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    grown = tmp_path / "grown.jsonl"
    grown.write_text(fixture.read_text(encoding="utf-8") + json.dumps(
        {"id": "r570-77", "question": "换集", "answer": "换集"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    capsys.readouterr()
    assert drv.main(base_argv(tmp_path, grown) + ["--run", "--dry-run"]) == drv.RC_REFUSE
    monkeypatch.setattr(drv, "fingerprint_mismatch", lambda *a, **k: [])
    capsys.readouterr()
    blinded = drv.main(base_argv(tmp_path, grown) + ["--run", "--dry-run"])
    out = capsys.readouterr().out
    assert blinded == drv.RC_OK, "摘了闸还拦得住：这一格不是真在尺上"
    assert "被复用" in out or "to run=1" in out, out


def test_counter_evidence_b_the_dead_streak_threshold_is_load_bearing(tmp_path, monkeypatch,
                                                                      capsys):
    """牙 b：阈值放宽到片数 ⇒ 死后端上把整窗空转跑完（正是判据 ⑥ 要拦的烧钱形状）。"""
    fixture, _ids = mini_fixture(tmp_path, count=6)
    fake_docker(monkeypatch)
    dead = FakeCollector(produce=False)
    monkeypatch.setattr(drv, "invoke_collector", dead)
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run", "--retries", "0",
                                                    "--dead-streak", "2"]) == drv.RC_DEAD_BACKEND
    assert len(dead.calls) == 2, "阈值 2 没在 2 片上收"
    loose = FakeCollector(produce=False)
    monkeypatch.setattr(drv, "invoke_collector", loose)
    capsys.readouterr()
    rc = drv.main(base_argv(tmp_path, fixture) + ["--plan"])
    assert rc == drv.RC_OK
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run", "--retries", "0",
                                                    "--dead-streak", "7"]) == drv.RC_SHARDS_OPEN
    assert len(loose.calls) == 6, "阈值 7（大于片数）却提前停了：那早停不是阈值说了算"
    assert "STOP" not in capsys.readouterr().out


def test_counter_evidence_c_no_refusal_ever_exits_zero(tmp_path, monkeypatch, capsys):
    """牙 c：REFUSE 一律非零（总控要能程序化判）——把每一条拒都跑一遍数一遍。"""
    fixture, _ids = mini_fixture(tmp_path, count=3)
    fake_docker(monkeypatch)
    monkeypatch.setattr(drv, "invoke_collector", FakeCollector())
    argv = base_argv(tmp_path, fixture)
    cases = [
        argv + [],
        argv + ["--plan", "--run"],
        base_argv(tmp_path, tmp_path / "now-here.jsonl") + ["--plan"],
        ["--tag", "r570win", "--fixture", str(fixture), "--tmp-dir", str(REPO_ROOT / "evalout"),
         "--plan"],
        argv + ["--plan", "--expect-backend", "weird"],
        argv + ["--shard-size", "0", "--plan"],
    ]
    for extra in cases:
        capsys.readouterr()
        rc = drv.main(extra)
        assert rc != 0, "这条拒退成了 0：" + " ".join(extra)
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    shard_answers(tmp_path, "r570win", 1).unlink()
    assert drv.main(base_argv(tmp_path, fixture) + ["--commit"]) == drv.RC_REFUSE
    assert drv.main(base_argv(tmp_path, fixture, python="X") + ["--run", "--dry-run",
                                                                "--retries", "0"]) == drv.RC_OK


def test_counter_evidence_d_the_driver_never_writes_inside_the_repo(tmp_path, monkeypatch, capsys):
    """牙 d：产物只许落仓外。①指进仓内当场拒；②整轮跑完仓内文件清单逐枚全等。"""
    capsys.readouterr()
    rc = drv.main(["--tag", "r570win", "--fixture", str(tmp_path / "x.jsonl"),
                   "--tmp-dir", str(REPO_ROOT / "scripts"), "--plan"])
    assert rc == drv.RC_REFUSE and "仓内" in capsys.readouterr().out
    fixture, _ids = mini_fixture(tmp_path, count=4)
    fake_docker(monkeypatch)
    monkeypatch.setattr(drv, "invoke_collector", FakeCollector())
    before = {name: (REPO_ROOT / "scripts" / name).stat().st_mtime_ns
              for name in sorted(p.name for p in (REPO_ROOT / "scripts").iterdir())}
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    assert drv.main(base_argv(tmp_path, fixture) + ["--commit"]) == drv.RC_OK
    after = {name: (REPO_ROOT / "scripts" / name).stat().st_mtime_ns
             for name in sorted(p.name for p in (REPO_ROOT / "scripts").iterdir())}
    assert after == before, "驱动往仓内写了东西"


def test_counter_evidence_e_this_file_carries_no_downgrade_marker():
    """牙 e：本件一枚降级记号都不许有（跳过／放宽／独占）。"""
    text = Path(__file__).read_text(encoding="utf-8")
    for marker in ("pytest.mark." + "skip", "pytest.mark." + "xfail", "pytest.mark." + "skipif",
                   "pytest." + "skip(", "pytest." + "xfail(", ".only" + "("):
        assert marker not in text, "本件里出现了降级记号：" + marker


def test_counter_evidence_f_no_test_here_shells_out_to_docker(tmp_path, monkeypatch, capsys):
    """牙 f：把 subprocess 换成一枚会炸的桩 ⇒ 全轮跑完一次没炸，才证明确实没调 docker。"""
    calls = []

    def bang(*a, **k):
        calls.append((a, k))
        raise AssertionError("测试里不许真起子进程：" + repr(a)[:120])

    fixture, _ids = mini_fixture(tmp_path, count=3)
    asked = fake_docker(monkeypatch)
    monkeypatch.setattr(drv, "invoke_collector", FakeCollector())
    monkeypatch.setattr(drv.subprocess, "run", bang)
    assert drv.main(base_argv(tmp_path, fixture) + ["--run", "--dry-run"]) == drv.RC_OK
    assert drv.main(base_argv(tmp_path, fixture) + ["--commit"]) == drv.RC_OK
    assert calls == []
    assert asked, "假读数单点没被用上：那指纹是从哪来的？"
    assert any("BUILD_INFO" in shell for shell, _ in asked)
    assert not any("printenv" in shell for shell, _ in asked), "printenv 会把「读到空」误判成「问不着」"

# ==================== 件头映射自证（R560/R562 同族病：手抄的引用会过期） ====================

def header_mapping_faults(doc, real_names):
    """把件头那张表与盘面用例名对账，返回（表里点了却不存在的, 存在却没进表的）。"""
    listed = set(re.findall(r"\btest_[a-z0-9_]+\b", doc or ""))
    real = set(real_names)
    return sorted(listed - real), sorted(real - listed)


def test_the_header_mapping_names_only_real_cases():
    """件头那张「七格 ↔ 用例」表必须与盘面同源：表里点名的用例都得存在，存在的用例都得进表。

    这一单治的就是「纸上抄的引用会漂」，本件的纸不能例外。摘掉一枚用例、或改名忘了改表 ⇒ 当场红。
    """
    doc = globals()["__doc__"]
    names = [name for name, value in globals().items()
             if name.startswith("test_") and callable(value)]
    assert header_mapping_faults(doc, names) == ([], []), header_mapping_faults(doc, names)
    for cell in "①②③④⑤⑥⑦":
        assert cell in doc, "件头丢了判据 " + cell + " 那一格的映射"
    assert len(names) >= 28, "用例枚数掉了：" + str(len(names))
    # 负控：少写一枚 / 多写一枚不存在的，对账函数必须报出来（不许恒空）
    assert header_mapping_faults(doc.replace("test_rerun_reports_to_run_zero_and_reasks_nothing", ""),
                                 names) == ([], ["test_rerun_reports_to_run_zero_and_reasks_nothing"])
    assert header_mapping_faults(doc + " ``test_a_name_that_does_not_exist``", names) == (
        ["test_a_name_that_does_not_exist"], [])
