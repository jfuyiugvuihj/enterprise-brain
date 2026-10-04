# -*- coding: utf-8 -*-
r"""R632 缺陷二 —— 契约点名的那枚读数件落仓之后，它自己必须有牙。

## 为什么判「件从来没落」而不是「改名漂了」（定性全文见 docs/testing/r632-instrument-lane-readout.md）

契约家族 A 那一格点名 `scripts/eval_slo_lane_readout.py`；本席 10-04 现取
`git log --all -- scripts/eval_slo_lane_readout.py` 交**空输出** —— 任何 ref 都没碰过这个路径；
在册 docs/testing/r526-slo-caliber-closure.md 也早把这三枚件名记成 MISS；
app/api/v1/observability.py 的 `_A_READER` 同样指着这枚不存在的件（写域外，只交证据）。
⇒ 不是改名漂了，是**件从来没落**，所以照契约那一格的口径把件补出来，本件钉住它的三条纪律：

① 档位名只认**服务端说了什么**：响应头腿（量具的第三份件）优先，`[R42]` 日志腿只补空缺；
   题面前缀不唯一／同一题读出两枚档位名／闭集外的名字 —— 三种一律判**取不到**，不挑一枚，
   也不许拿评测夹具那一列 `tier`（声明档）冒充生效档。
② 分位只出自产品那把尺（app/common/performance.py::PerformanceStats）：本件不写第二套排名，
   空表不叫尺 —— 那把尺对空表回 0，而一枚 0 是最会骗人的假 p95。
③ 档位名与样本下限**现场派生**（nodes.py 的 LANE_* ＋ observability 的 MIN_SLO_SAMPLES，AST 现读）：
   派生不到就是取不到，当场 rc=2，绝不退落成手抄的 qa/analysis/report 或 100。

反证三把（只在临时根副本上动刀，真树件前后各核一次 sha256）：
甲 空表那一格摘掉 ⇒ 件对空表当场炸（现取炸在 min(空表)；那行改成安全写法就直接交 0 那枚假 p95），
   两种死法都不许变成「读数」；
乙 派生闭集那一格摘掉 ⇒ 服务端说 `turbo` 也照收；
丙 `return names` 换成手抄三枚字面 ⇒ 影子根改名立刻失效（证明「派生」不是句空话）。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import itertools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
READER = REPO_ROOT / "scripts" / "eval_slo_lane_readout.py"
GATE = REPO_ROOT / "scripts" / "eval_cloud_window_readout.py"
NODES = REPO_ROOT / "app" / "agents" / "nodes.py"
OBSERVABILITY = REPO_ROOT / "app" / "api" / "v1" / "observability.py"
CONTRACT = REPO_ROOT / "docs" / "api" / "contract-v1.md"
#: 契约里点名的那枚件名（相对路径写法）—— 本件的长期钉只认件名不认行号。
CONTRACT_READER = "scripts/eval_slo_lane_readout.py"

_COUNTER = itertools.count(1)


# ==================== 产品那两枚真源：测试自己现读，一个字节都不抄 ====================

def module_literals(path, names):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    table = {}
    for node in tree.body:
        target = value = None
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            target, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        if target in names and value is not None:
            table[target] = ast.literal_eval(value)
    missing = sorted(set(names) - set(table))
    assert not missing, "真源 %s 里读不到 %s ⇒ 源件漂了，先复验再谈判据" % (path, missing)
    return table


def product_lane_names():
    table = module_literals(NODES, ("LANE_QA", "LANE_ANALYSIS", "LANE_REPORT"))
    return (table["LANE_QA"], table["LANE_ANALYSIS"], table["LANE_REPORT"])


def product_min_samples():
    return module_literals(OBSERVABILITY, ("MIN_SLO_SAMPLES",))["MIN_SLO_SAMPLES"]


# ==================== 影子根：让「派生」这件事可以被反证 ====================

def shadow_root(tmp_path, nodes_src=None, obs_src=None, reader_src=None):
    """造一枚假仓根：app/agents/nodes.py 与 app/api/v1/observability.py 用**给定**的字面。

    🔴 缺省给的是**从产品真源现读**的那三枚名字与那枚下限（不是测试里手抄的字面）；
    于是「影子根改名、读数件跟着改」这一格只能由派生实现，抄不出来。
    """
    names = product_lane_names()
    root = tmp_path / ("root%d" % next(_COUNTER))
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "app" / "agents").mkdir(parents=True, exist_ok=True)
    (root / "app" / "api" / "v1").mkdir(parents=True, exist_ok=True)
    nodes_text = nodes_src if nodes_src is not None else "".join(
        "LANE_%s = %r\n" % (suffix, name)
        for suffix, name in zip(("QA", "ANALYSIS", "REPORT"), names))
    (root / "app" / "agents" / "nodes.py").write_text(nodes_text, encoding="utf-8", newline="\n")
    obs_text = obs_src if obs_src is not None else "MIN_SLO_SAMPLES = %r\n" % product_min_samples()
    (root / "app" / "api" / "v1" / "observability.py").write_text(obs_text, encoding="utf-8", newline="\n")
    script = root / "scripts" / "eval_slo_lane_readout.py"
    script.write_text(reader_src if reader_src is not None else READER.read_text(encoding="utf-8"),
                      encoding="utf-8", newline="\n")
    return root, script


def load(path):
    name = "r632_slo_%d" % next(_COUNTER)
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def reader():
    return load(READER)

# ==================== 件：一扇窗的三份产物 ====================

def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def window_files(root, window, naming):
    """两种在册命名都走：驱动写 `{window}-sidecar.jsonl`，同僚件写 `sidecar-{window}.jsonl`。"""
    if naming == "suffixed":
        return (root / ("%s-sidecar.jsonl" % window), root / ("%s-sidecar-frames.jsonl" % window),
                root / ("%s-sidecar-lane.jsonl" % window))
    return (root / ("sidecar-%s.jsonl" % window), root / ("sidecar-%s-frames.jsonl" % window),
            root / ("sidecar-%s-lane.jsonl" % window))


def make_window(tmp_path, window="run10", naming="suffixed", spec=None, write_lane=True, tag=None):
    """落三份件。缺省一题一档，档位名一律用**派生出来的**那三枚（不在测试里手抄）。

    spec 每项 = (题号, wall_ms, 生效档 or None, 发出去的 lane or None, headers_readable)
    """
    names = product_lane_names()
    if spec is None:
        spec = [(("q%d" % (slot + 1)), 1000.0 + 100 * slot, names[slot], names[slot], True)
                for slot in range(3)]
    root = tmp_path / ("artifacts-%s-%s" % (window, tag or next(_COUNTER)))
    sidecar, frames, lane = window_files(root, window, naming)
    write_jsonl(sidecar, [{"id": row_id, "kind": "answered", "attempt": 1,
                           "wall_ms": wall_ms, "sentinel": False}
                          for row_id, wall_ms, _effective, _sent, _readable in spec])
    write_jsonl(frames, [{"id": row_id, "session_id": "sess-%s" % row_id}
                         for row_id, _wall, _effective, _sent, _readable in spec])
    if write_lane:
        write_jsonl(lane, [{"id": row_id, "session_id": "sess-%s" % row_id, "attempt": 1,
                            "sent_lane": sent, "server_declared_lane": sent,
                            "effective_lane": effective,
                            "lane_source": "explicit" if effective else "unknown",
                            "headers_readable": readable}
                           for row_id, _wall, effective, sent, readable in spec])
    return root, {"sidecar": sidecar, "frames": frames, "lane": lane}


def run(script, extra):
    """真跑子进程：读数件是量具，判据得按调用者会用的那条路走一遍。"""
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    for key in ("EVAL_DECLARE_LANE_TIER", "EVAL_DECLARE_LANE_PER_TIER",
                "EVAL_RECORD_LANE_READOUT", "EVAL_LANE_LEDGER"):
        env.pop(key, None)
    proc = subprocess.run([str(PYTHON), str(script)] + [str(item) for item in extra],
                          cwd=str(REPO_ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    return proc.returncode, proc.stdout + proc.stderr


# ==================== 缺陷二那一格：件名与契约同源（长期钉） ====================

def test_every_lane_readout_named_in_the_contract_exists_on_disk():
    """契约点名的每一枚读数件必须真在盘上——本单之前那句「一枚在册读数件」是假话。

    🔴 只认件名不认行号：行号会漂（本单给 transport 加了 105 行就是现例），路径不会。
    """
    text = CONTRACT.read_text(encoding="utf-8")
    named = set(re.findall(r"scripts/eval_[a-z0-9_]*lane_readout\.py", text))
    assert named, "契约里一枚读数件名都没点名：这枚钉的前提变了，先复验契约"
    assert CONTRACT_READER in named, "契约换名了？现在点名的是：%s" % sorted(named)
    absent = sorted(name for name in named if not (REPO_ROOT / name).exists())
    assert absent == [], "契约点名而盘上没有：%s ⇒「跑不起来就是取不到」又成了空话" % absent


def test_the_contract_env_vocabulary_matches_the_reader_header():
    """契约那一格要求抬头报四枚开关：件名的清单与件里报的必须逐枚相同（同源，不手抄）。"""
    text = CONTRACT.read_text(encoding="utf-8")
    anchor = text.index("抬头开关态")
    listed = set(re.findall(r"`([A-Z][A-Z0-9_]{3,})`", text[anchor:anchor + 260]))
    module = load(READER)
    assert listed, "契约里那串开关名读不出来：先复验契约那一格"
    assert set(module.HEAD_ENV_KEYS) == listed, (
        "读数件抬头报的开关与契约点名的不齐：件多=%s 契约多=%s"
        % (sorted(set(module.HEAD_ENV_KEYS) - listed), sorted(listed - set(module.HEAD_ENV_KEYS))))


def test_the_reader_refuses_to_invent_numbers_when_the_window_is_empty(tmp_path):
    """件落仓不等于件能用：读不到件那一格必须明写取不到（与缺陷一同一族病）。"""
    root, script = shadow_root(tmp_path)
    empty = tmp_path / "evalrun-empty"
    empty.mkdir()
    rc, out = run(script, ["--window", "run10", "--dir", str(empty)])
    assert rc == 2, "缺件还交 0：\n" + out[-800:]
    assert "取不到" in out and "不编数" in out, out[-800:]
    assert "kind=lane" in out, "档位名读数件那一格必须点名：\n" + out[-800:]
    assert "EVAL_RECORD_LANE_READOUT" in out, "没交代这格为什么今天注定是空的：\n" + out[-800:]
    assert "sidecar" in out and "sha256" not in out, "缺件那一趟不许长出凭据：\n" + out[-800:]


# ==================== ③ 派生：改名必须跟着改，抄不来 ====================

def test_lane_names_and_floor_come_from_the_product_files(reader):
    """正控：真树缺省路径下，三枚档位名与样本下限逐枚等于产品真源现读的数。"""
    assert reader.derive_lane_names() == product_lane_names()
    assert reader.derive_min_samples() == product_min_samples()


def test_shadow_root_rename_is_honoured(tmp_path):
    """影子根把三枚档位名换成市面上没见过的字面 ⇒ 读数件必须跟着换（丙的正控面）。"""
    root, script = shadow_root(
        tmp_path, nodes_src='LANE_QA = "甲档"\nLANE_ANALYSIS = "乙档"\nLANE_REPORT = "丙档"\n')
    module = load(script)
    assert module.derive_lane_names() == ("甲档", "乙档", "丙档"), "改名没跟 ⇒ 本件是手抄不是派生"
    for name in product_lane_names():
        assert name not in module.derive_lane_names(), "产品那三枚拼写还留在读数里 = 手抄"


def test_shadow_root_drives_everything_the_ledger_prints(tmp_path):
    """影子根那一窗：抬头报影子的档名与影子的下限，逐档表与「声明≠生效」都跟着影子走。"""
    root, script = shadow_root(
        tmp_path,
        nodes_src='LANE_QA = "甲档"\nLANE_ANALYSIS = "乙档"\nLANE_REPORT = "丙档"\n',
        obs_src="MIN_SLO_SAMPLES = 3\n")
    art = tmp_path / "win-shadow"
    write_jsonl(art / "run99-sidecar.jsonl",
                [{"id": "a", "kind": "answered", "attempt": 1, "wall_ms": 1500.0, "sentinel": False},
                 {"id": "b", "kind": "answered", "attempt": 1, "wall_ms": 900.0, "sentinel": False},
                 {"id": "c", "kind": "answered", "attempt": 1, "wall_ms": 1200.0, "sentinel": False}])
    write_jsonl(art / "run99-sidecar-frames.jsonl",
                [{"id": "a", "session_id": "s1"}, {"id": "b", "session_id": "s2"},
                 {"id": "c", "session_id": "s3"}])
    write_jsonl(art / "run99-sidecar-lane.jsonl",
                [{"id": "a", "session_id": "s1", "effective_lane": "丙档", "sent_lane": "丙档",
                  "headers_readable": True},
                 {"id": "b", "session_id": "s2", "effective_lane": "丙档", "sent_lane": "乙档",
                  "headers_readable": True},
                 {"id": "c", "session_id": "s3", "effective_lane": "丙档", "sent_lane": "甲档",
                  "headers_readable": True}])
    rc, out = run(script, ["--window", "run99", "--dir", str(art)])
    assert rc == 0, out[-1200:]
    assert "甲档/乙档/丙档" in out, "抬头没报影子档名：\n" + out
    assert "样本下限=3" in out, "下限没跟影子根：\n" + out
    assert "| 丙档 | 3 | 3 | 够 |" in out, "三题同档 n=3 且下限=3 必须判够：\n" + out
    assert "| 甲档 | 0 | 3 |" in out, "零样本那一格不许消失：\n" + out
    assert "sent=乙档 effective=丙档" in out, "声明档≠生效档要逐题点名：\n" + out


@pytest.mark.parametrize("nodes_src,why", [
    ('LANE_QA = "qa"\nLANE_ANALYSIS = "analysis"\n', "少一枚档位名"),
    ('LANE_QA = lane_of("qa")\nLANE_ANALYSIS = "analysis"\nLANE_REPORT = "report"\n', "档位名不是字面量"),
    ('LANE_QA = "same"\nLANE_ANALYSIS = "same"\nLANE_REPORT = "other"\n', "三枚不成闭集"),
])
def test_derivation_failure_is_take_not_a_quiet_default(tmp_path, nodes_src, why):
    root, script = shadow_root(tmp_path, nodes_src=nodes_src)
    art, _ = make_window(tmp_path, window="run10")
    rc, out = run(script, ["--window", "run10", "--dir", str(art)])
    assert rc == 2, "%s 还交了 0：\n" % why + out[-800:]
    assert "派生失败" in out and "不退回手抄数" in out, "%s 没明写取不到：\n" % why + out[-800:]


@pytest.mark.parametrize("obs_src", ["MIN_SLO_SAMPLES = 0\n", "MIN_SLO_SAMPLES = -5\n",
                                     "MIN_SLO_SAMPLES = True\n", "MIN_SLO_SAMPLES = 100.5\n"])
def test_a_bogus_sample_floor_is_take_too(tmp_path, obs_src):
    root, script = shadow_root(tmp_path, obs_src=obs_src)
    rc, out = run(script, ["--window", "run10", "--dir", str(tmp_path / "nowhere")])
    assert rc == 2, "下限 %r 居然被认下：\n" % obs_src + out[-600:]
    assert "派生失败" in out, out[-600:]

# ==================== ② 分位只出自产品那把尺 ====================

def test_percentiles_equal_the_product_ruler_on_the_same_multiset(reader):
    from app.common.performance import PerformanceStats

    values = [1200.0, 1500.0, 900.0, 1100.0, 1300.0, 950.0, 1000.0, 1400.0, 800.0, 1600.0]
    stats = PerformanceStats()
    for value in values:
        stats.observe(value)
    report = stats.report()
    pair = reader.percentile_pair(values)
    assert pair["n"] == int(report["count"]) == len(values)
    assert pair["p50_ms"] == pytest.approx(float(report["p50_ms"])), "本件自己排了名"
    assert pair["p95_ms"] == pytest.approx(float(report["p95_ms"])), "本件自己排了名"
    assert pair["max_ms"] == pytest.approx(float(report["max_ms"]))
    assert pair["min_ms"] == pytest.approx(min(values))


def test_empty_table_is_none_and_the_ruler_would_have_lied(reader):
    """② 的后半：空表**不许**叫尺。正控先证明那把尺对空表回 0 —— 那枚 0 就是假 p95。"""
    from app.common.performance import PerformanceStats

    empty = PerformanceStats().report()
    assert empty["count"] == 0
    assert empty["p95_ms"] == 0, "正控不成立：尺对空表不再回 0，这一格的病根变了"
    assert reader.percentile_pair([]) is None, "本件把空表交给了那把尺 ⇒ 会读出 0 那枚假 p95"


def test_reader_carries_no_second_ranking_implementation():
    """结构钉：本件不许自己排名（ceil／quantile／percentile／另引一套库），只许用产品那把尺。"""
    tree = ast.parse(READER.read_text(encoding="utf-8"), filename=str(READER))
    banned = {"ceil", "floor", "quantile", "percentile", "median", "mean"}
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in banned:
            hits.append("%s@L%d" % (name, node.lineno))
    assert hits == [], "读数件里长出了第二套排名：%s" % hits
    libs = [node.module for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            and any(alias.name.split(".")[0] in ("numpy", "statistics", "pandas") for alias in node.names)]
    assert libs == [], "不许另引一套分位库：%s" % libs
    sources = [node for node in ast.walk(tree)
               if isinstance(node, ast.ImportFrom) and node.module == "app.common.performance"
               and any(alias.name == "PerformanceStats" for alias in node.names)]
    assert len(sources) == 1, "分位出处必须只有一处，实取 %d 处" % len(sources)


def test_wall_ms_that_is_not_a_number_is_dropped_and_named(reader):
    """非数的 wall_ms 不许折成 0 进分位：它得掉出去，并且点名题号。"""
    names = product_lane_names()
    readings = {"q1": {"wall_ms": 1000.0, "kind": "answered", "sentinel": False, "lane": names[0]},
                "q2": {"wall_ms": None, "kind": "answered", "sentinel": False, "lane": names[0]}}
    cells = reader.per_lane_cells(readings, names, 1)
    assert cells[names[0]]["dropped_wall_ms"] == ["q2"], cells[names[0]]
    assert cells[names[0]]["pair"]["n"] == 1, "掉出去的题被算进了分位"
    assert cells[names[1]]["pair"] is None, "零样本那一档必须交 None，不是 0"
    assert cells[names[1]]["enough"] is False, "零样本还敢判够"


# ==================== ① join：三跳精确键 ＋ 三态 ====================

def test_both_artifact_namings_are_tried(reader):
    """两种在册命名都要认；认不到就点名试过哪几条路径，不静默造第三条。"""
    expected = {"sidecar": ("sidecar-run7.jsonl", "run7-sidecar.jsonl"),
                "frames": ("sidecar-run7-frames.jsonl", "run7-sidecar-frames.jsonl"),
                "lane": ("sidecar-run7-lane.jsonl", "run7-sidecar-lane.jsonl")}
    for kind, names in expected.items():
        found = tuple(Path(path).name for path in reader.artifact_candidates("run7", "D", kind))
        assert found == names, "%s 的命名表漂了：实取 %s" % (kind, found)
    with pytest.raises(reader.CaliberError):
        reader.artifact_candidates("run7", "D", "whatever")


def test_latest_attempt_wins_and_row_collisions_are_counted(reader):
    rows = [{"id": "q1", "attempt": 1, "wall_ms": 100.0},
            {"id": "q1", "attempt": 3, "wall_ms": 300.0},
            {"id": "q1", "attempt": 2, "wall_ms": 200.0},
            {"id": "q2", "attempt": 1, "wall_ms": 50.0},
            {"id": "q2", "attempt": 1, "wall_ms": 55.0}]
    table, counts = reader.latest_by(rows, "id")
    assert table["q1"]["wall_ms"] == 300.0, "attempt 最大那一枚才算终答"
    assert counts["q1"] == 3 and counts["q2"] == 2, "撞行枚数没交回 ⇒ 会话键撞行没人点得出名"
    reversed_table, _ = reader.latest_by(list(reversed(rows)), "id")
    assert reversed_table["q1"]["wall_ms"] == 300.0, "行序反了就不认 ⇒ 靠的是顺序不是键"
    empty_table, empty_counts = reader.latest_by([{"attempt": 1, "wall_ms": 5.0}], "id")
    assert empty_table == {} and empty_counts == {}, "没有 id 的那一行被安到了空键上"


def test_three_hops_join_by_exact_keys_in_any_order(reader):
    """侧车 id → 帧账 session_id → 档位件 session_id：三跳全是精确键，与行序无关。"""
    names = product_lane_names()
    sidecar = [{"id": "q1", "kind": "answered", "attempt": 1, "wall_ms": 1100.0, "sentinel": False},
               {"id": "q2", "kind": "answered", "attempt": 1, "wall_ms": 2200.0, "sentinel": False}]
    frames = [{"id": "q2", "session_id": "sB"}, {"id": "q1", "session_id": "sA"}]
    lane = [{"id": "q2", "session_id": "sB", "effective_lane": names[1], "sent_lane": names[1],
             "server_declared_lane": names[1], "lane_source": "explicit", "headers_readable": True},
            {"id": "q1", "session_id": "sA", "effective_lane": names[2], "sent_lane": names[0],
             "server_declared_lane": names[0], "lane_source": "override", "headers_readable": True}]
    readings = reader.build_lane_table(sidecar, frames, lane, None, names)
    assert readings["q1"]["lane"] == names[2] and readings["q1"]["session_id"] == "sA"
    assert readings["q2"]["lane"] == names[1] and readings["q2"]["wall_ms"] == 2200.0
    cells = reader.per_lane_cells(readings, names, 1)
    assert cells[names[0]]["pair"] is None, "声明档被当成生效档用了（q1 发的是 %s）" % names[0]
    assert cells[names[2]]["pair"]["n"] == 1 and cells[names[1]]["pair"]["n"] == 1


def test_header_leg_wins_and_the_log_leg_only_fills_the_gap(reader):
    sidecar = [{"id": "q1", "kind": "answered", "attempt": 1, "wall_ms": 100.0, "sentinel": False},
               {"id": "q2", "kind": "answered", "attempt": 1, "wall_ms": 200.0, "sentinel": False}]
    frames = [{"id": "q2", "session_id": "s2"}, {"id": "q1", "session_id": "s1"}]
    lane = [{"id": "q1", "session_id": "s1", "effective_lane": "report", "sent_lane": "analysis",
             "server_declared_lane": "analysis", "lane_source": "override", "headers_readable": True},
            {"id": "q2", "session_id": "s2", "effective_lane": None, "sent_lane": None,
             "server_declared_lane": None, "lane_source": None, "headers_readable": False}]
    log_readout = {"lanes": {"q1": "qa", "q2": "analysis"}, "conflicts": [],
                   "ambiguous_prefixes": [], "r42_lines": 2, "log_lines": 2}
    readings = reader.build_lane_table(sidecar, frames, lane, log_readout,
                                       ("qa", "analysis", "report"))
    assert (readings["q1"]["lane"], readings["q1"]["origin"]) == ("report", reader.ORIGIN_HEADER), \
        "响应头读到了还被日志覆盖 ⇒ 两条腿的优先级反了"
    assert (readings["q2"]["lane"], readings["q2"]["origin"]) == ("analysis", reader.ORIGIN_LOG), \
        "响应头那条读不到时，日志这条腿必须补上空缺"


def test_session_key_collision_is_not_picked(reader, tmp_path):
    """同一枚 session_id 撞两行 ⇒ 判取不到并点名；挑一枚就是替服务端编档。"""
    _, paths = make_window(tmp_path, window="run5", spec=[("q1", 1000.0, "qa", "qa", True)])
    lane_rows = reader.load_jsonl(paths["lane"])
    lane_rows.append(dict(lane_rows[0], effective_lane="report"))
    write_jsonl(paths["lane"], lane_rows)
    readings = reader.build_lane_table(reader.load_jsonl(paths["sidecar"]),
                                       reader.load_jsonl(paths["frames"]),
                                       lane_rows, None, ("qa", "analysis", "report"))
    assert readings["q1"]["lane"] is None, "撞键还挑了一枚"
    assert readings["q1"]["origin"] == reader.ORIGIN_NONE
    assert "撞了 2 行" in readings["q1"]["note"], readings["q1"]["note"]


def test_frames_without_session_say_so(reader, tmp_path):
    """帧账里读不到 session_id ⇒ 档位件 join 不上：这条要说得出是哪一跳断的。"""
    art, paths = make_window(tmp_path, window="run4", spec=[("q1", 1000.0, "qa", "qa", True)])
    write_jsonl(paths["frames"], [{"id": "q1"}])
    readings = reader.build_lane_table(reader.load_jsonl(paths["sidecar"]),
                                       [{"id": "q1"}], reader.load_jsonl(paths["lane"]), None,
                                       ("qa", "analysis", "report"))
    assert readings["q1"]["lane"] is None
    assert "帧账里读不到 session_id" in readings["q1"]["note"], readings["q1"]["note"]


def test_lane_outside_the_derived_closed_set_is_refused(reader):
    """服务端说了句本件不认识的话 ⇒ 不认它，也不折进任何一档。"""
    sidecar = [{"id": "q1", "kind": "answered", "attempt": 1, "wall_ms": 100.0, "sentinel": False}]
    frames = [{"id": "q1", "session_id": "s1"}]
    lane = [{"id": "q1", "session_id": "s1", "effective_lane": "turbo", "sent_lane": "qa",
             "server_declared_lane": "qa", "lane_source": "explicit", "headers_readable": True}]
    readings = reader.build_lane_table(sidecar, frames, lane, None, ("qa", "analysis", "report"))
    assert readings["q1"]["lane"] is None and readings["q1"]["origin"] == reader.ORIGIN_NONE
    assert "不在派生闭集里" in readings["q1"]["note"], readings["q1"]["note"]


def test_declared_tier_column_is_never_used_as_the_effective_lane():
    """夹具那一列是**声明档**：本件全文不许拿它当生效档（契约原话「多轮改写会把两者分开」）。"""
    text = READER.read_text(encoding="utf-8")
    lines = text.split("\n")
    offenders = [line.strip() for line in lines
                 if 'get("tier")' in line and "def " not in line and not line.strip().startswith("#")]
    assert offenders == [], "档位名从声明档那一列抄了近道：%s" % offenders
    assert 'row.get("question")' in text, "题面只许当 [R42] 日志那条腿的 join 键用"
    assert "绝不当档位用" in text, "这条纪律得写在件里，不能只留在测试里"


def test_two_artifact_namings_both_run_end_to_end(tmp_path):
    root, script = shadow_root(tmp_path)
    names = product_lane_names()
    for naming in ("suffixed", "prefixed"):
        art, paths = make_window(tmp_path, window="run8", naming=naming, tag=naming)
        rc, out = run(script, ["--window", "run8", "--dir", str(art)])
        assert rc == 0, "%s 命名读不出来：\n" % naming + out[-900:]
        assert str(paths["sidecar"]) in out and str(paths["lane"]) in out, \
            "%s 命名没在抬头点名真用了哪一条：\n" % naming + out[-600:]
        assert "sha256=" in out, "缺 sha256 ⇒ 契约要的凭据格交不出"
        assert "| %s | 1 |" % names[0] in out, out[-600:]
        assert "caliber=local-full" in out, "分位属时延类，本机口径必须挂在行上"

# ==================== ① 的第二条腿：后端 [R42] 日志 ====================

def r42_line(question, lane, tier="chat"):
    """照 app/common/stage_timing.py::R42_LOG_PATTERN 认得的那一句写（不是随便编的格式）。"""
    return "[R42] '%s' → lane=%s tier=%s rule=keyword hit=0" % (question, lane, tier)


SHADOW_NODES = 'LANE_QA = "甲档"\nLANE_ANALYSIS = "乙档"\nLANE_REPORT = "丙档"\n'


def test_utf16le_log_with_bom_is_read_and_the_naive_read_is_the_trap(tmp_path, reader):
    """跟进单 §62 的教训在这条腿上复发过一次：PowerShell `>` 交的是 UTF-16 LE。

    正控先证明按 utf-8 硬读同一枚件会得到**零枚** [R42]（全零假阴性），再看本件读得回来。
    """
    names = product_lane_names()
    question = "请比较 2025 年三个季度的毛利率与费用率"
    payload = "\n".join([r42_line(question, names[2]), "别的日志行"]) + "\n"
    log = tmp_path / "backend.log"
    log.write_bytes(payload.encode("utf-16"))
    raw = log.read_bytes()
    assert raw[:2] == b"\xff\xfe", "正控不成立：这枚件不是 UTF-16 LE 带 BOM"
    assert raw.decode("utf-8", "replace").count("[R42]") == 0, \
        "按 utf-8 硬读居然读到了 ⇒ 这条反证是空的"
    assert "[R42]" in reader.read_log_text(log), "本件读不回 UTF-16 ⇒ 那条腿会静默全零"
    readout = reader.r42_log_lanes(log, {"q1": question})
    assert readout["lanes"] == {"q1": names[2]}, readout
    assert readout["r42_lines"] == 1 and readout["log_lines"] == 2, readout


def test_ambiguous_question_prefix_is_take_not_a_pick(tmp_path, reader):
    """题面前 30 字撞车 ⇒ 谁都不认，并把撞车的前缀点名（挑一枚就是替服务端编档）。"""
    names = product_lane_names()
    base = "请对比 2024 与 2025 年华东区三个季度的回款率与费用率并给出结论"
    assert len(base) >= 30, "正控不成立：这枚题面不足 30 字，撞不了前缀"
    first, second = base, base + "（换半句后缀）"
    assert first[:30] == second[:30], "正控不成立：这两枚题面前 30 字不相同"
    log = tmp_path / "backend.log"
    log.write_text(r42_line(first, names[0]) + "\n", encoding="utf-8")
    readout = reader.r42_log_lanes(log, {"q1": first, "q2": second})
    assert readout["lanes"] == {}, readout
    assert readout["ambiguous_prefixes"] == [base[:30]], readout
    assert readout["r42_lines"] == 1, "行还是该计数，掉档只掉在读数那一格"


def test_conflicting_r42_lines_for_one_question_are_dropped(tmp_path, reader):
    names = product_lane_names()
    question = "把去年的库存周转率算一下"
    log = tmp_path / "backend.log"
    log.write_text("\n".join([r42_line(question, names[0]),
                              r42_line(question, names[2])]) + "\n", encoding="utf-8")
    readout = reader.r42_log_lanes(log, {"q1": question})
    assert readout["lanes"] == {}, readout
    assert readout["conflicts"] == ["q1"], readout
    assert readout["r42_lines"] == 2, "两行都该计数，掉档只掉在读数那一格"


def test_a_log_with_zero_r42_lines_is_a_hard_failure_and_is_not_reported_as_absent(tmp_path):
    """日志里一枚 [R42] 都没有 ⇒ 判硬失败，而且不许被写成「--r42-log 没给」。

    响应头那条腿还在，所以本窗整体仍可交数（rc=0），但日志那条腿必须单独报废。
    """
    root, script = shadow_root(tmp_path)
    art, _ = make_window(tmp_path, window="run6")
    log = tmp_path / "quiet.log"
    log.write_text("nothing interesting here\n", encoding="utf-8")
    rc, out = run(script, ["--window", "run6", "--dir", str(art), "--r42-log", str(log)])
    assert "零枚 [R42]" in out, out[-900:]
    assert "不写成「没给」" in out, "三态没分开：给了但零枚被读成了没给：\n" + out[-900:]
    assert "未指定（--r42-log 没给）" not in out, out[-900:]
    assert rc == 0, "响应头那条腿还在，本窗不该因为日志空就整体作废：\n" + out[-900:]


def test_all_effective_lanes_unreadable_yields_rc_two_not_a_zero_table(tmp_path):
    """每行都说不出档位 ⇒ 三档全无读数 ⇒ rc=2；n 照实报 0，题号点名。"""
    root, script = shadow_root(tmp_path)
    names = product_lane_names()
    art = tmp_path / "win-blind"
    write_jsonl(art / "run7-sidecar.jsonl", [{"id": "q1", "kind": "answered", "attempt": 1,
                                              "wall_ms": 700.0, "sentinel": False}])
    write_jsonl(art / "run7-sidecar-frames.jsonl", [{"id": "q1", "session_id": "s1"}])
    write_jsonl(art / "run7-sidecar-lane.jsonl", [{"id": "q1", "session_id": "s1",
                                                   "effective_lane": None, "headers_readable": False}])
    rc, out = run(script, ["--window", "run7", "--dir", str(art)])
    assert rc == 2, "全部取不到还交 0：\n" + out[-900:]
    assert "三档一枚分位都没算出来" in out, out[-900:]
    assert "| %s | 0 |" % names[0] in out, "n 没照实报 0：\n" + out
    assert "q1" in out, "取不到的题号没点名：\n" + out
    assert "响应头读不到档位名" in out, "没交代为什么读不到：\n" + out
    assert out.count("| - | - | - |") == 3, "取不到那一趟不许出分位数，三档都得是 -：\n" + out


def test_surface_stage_refuses_to_pass_e2e_off_as_stage(tmp_path):
    """家族 E 那一格今天交不出数：明写取不到，不许拿端到端三格冒充分段格。"""
    root, script = shadow_root(tmp_path)
    rc, out = run(script, ["--window", "run10", "--surface", "stage"])
    assert rc == 2, out[-600:]
    assert "家族 E" in out and "取不到" in out, out[-600:]
    assert "p95" not in out, "分段格那一趟居然顺手出了分位数：\n" + out[-600:]


def test_missing_r42_log_path_is_announced_in_the_ledger(tmp_path):
    root, script = shadow_root(tmp_path)
    art, _ = make_window(tmp_path, window="run14")
    rc, out = run(script, ["--window", "run14", "--dir", str(art),
                           "--r42-log", str(tmp_path / "no-such.log")])
    assert rc == 0, out[-900:]
    assert "件不在（--r42-log=" in out, "日志腿的第三种状态没在抬头交代：\n" + out[-900:]


# ==================== 与云形闸的接口：契约凭据那一格 ====================

def test_emitted_readouts_are_accepted_by_the_cloud_shape_gate(tmp_path):
    """契约要的凭据：`eval_cloud_window_readout.py --readouts <件>` 退出码 0。

    顺带钉三件事：口径标签只能是 local-full、格名与闸表同源、下限派生自产品；
    最后拿同一批读数换一枚云端口径做反证 —— 闸要是连这个都不拦，上面那枚 rc=0 就是永真钉。
    """
    root, script = shadow_root(tmp_path)
    art, _ = make_window(tmp_path, window="run12")
    out_file = tmp_path / "readouts.jsonl"
    rc, out = run(script, ["--window", "run12", "--dir", str(art),
                           "--emit-readouts", str(out_file)])
    assert rc == 0, out[-1200:]
    rows = [json.loads(line) for line in
            out_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    names = product_lane_names()
    assert sorted(row["segment"] for row in rows) == sorted(names), rows
    assert all(row["caliber"] == "local-full" for row in rows), "分位属时延类，只许本机口径"
    assert all(set(row["cells"]) == {"p50_wall_ms", "p95_wall_ms"} for row in rows), rows
    assert all(row["sample_floor"] == product_min_samples() for row in rows), "样本下限没派生"
    assert all(row["n"] == 1 and "样本不足" in row["note"] for row in rows), \
        "一题一档还判够 ⇒ 闸要的诚实计数在骗人"
    gate_rc, gate_out = run(GATE, ["--readouts", str(out_file)])
    assert gate_rc == 0, "云形闸拒了本件的读数：\n" + gate_out[-1200:]

    smuggled = [dict(row, caliber="cloud-shape") for row in rows]
    bad_file = write_jsonl(tmp_path / "readouts-smuggled.jsonl", smuggled)
    bad_rc, bad_out = run(GATE, ["--readouts", str(bad_file)])
    assert bad_rc == 2, "换上云端口径居然没人拦 ⇒ 上面那枚 rc=0 是永真钉：\n" + bad_out[-800:]
    assert "caliber=cloud-shape" in bad_out, bad_out[-800:]


def test_gate_cell_names_and_the_reader_agree_byte_for_byte():
    """本件交回的格名必须就是闸表里那两枚；闸表改字，本件当场对不上（不靠行号、不靠注释）。"""
    gate = GATE.read_text(encoding="utf-8")
    for cell in ("p50_wall_ms", "p95_wall_ms"):
        assert '_cell("%s"' % cell in gate, "闸表里那枚格改名了：%s" % cell
    module = load(READER)
    assert {module.CELL_P50, module.CELL_P95} == {"p50_wall_ms", "p95_wall_ms"}
    assert module.CALIBER_LOCAL == "local-full"

# ==================== 反证三把（只在临时根副本上动刀） ====================

def mutate(tmp_path, tag, needle, replacement, path=None):
    """把真件的一格改成「那格不存在」，交回副本路径；落点不唯一就直接判刀是空的。"""
    source = (path or READER).read_text(encoding="utf-8")
    assert source.count(needle) == 1, "反证落点命中 %d 次（要 1 次）：%r" % (
        source.count(needle), needle[:70])
    mutant = source.replace(needle, replacement, 1)
    assert mutant != source, "改了个寂寞"
    target = tmp_path / ("r632_mutant_%s.py" % tag)
    target.write_text(mutant, encoding="utf-8", newline="\n")
    return target


def test_knife_a_dropping_the_empty_guard_revives_the_fake_p95(tmp_path):
    """甲：摘掉「空表不叫尺」那一句 ⇒ 件对空表当场炸（10-04 实取：min() 收到空序列）。那行一旦改成安全写法，交回的就是 0 那枚假 p95；两种都不许被读成「数」。"""
    target = mutate(tmp_path, "a", "    if not values:\n        return None",
                    "    if False:\n        return None")
    original = load(READER)
    mutant = load(target)
    assert original.percentile_pair([]) is None, "真件这一格先站不住 ⇒ 反证没有对照"
    with pytest.raises(ValueError) as exc:
        mutant.percentile_pair([])
    assert "empty sequence" in str(exc.value), "摘掉那一格之后炸的不是空表那处：%s" % exc.value
    assert mutant.percentile_pair([1000.0])["n"] == 1, "刀下别的路径也坏了 ⇒ 这枚反证切多了"


def test_knife_b_dropping_the_closed_set_accepts_a_made_up_lane(tmp_path):
    """乙：摘掉派生闭集那一格 ⇒ 服务端说 `turbo` 也照收，档位计数当场多出东西。"""
    sidecar = [{"id": "q1", "kind": "answered", "attempt": 1, "wall_ms": 100.0, "sentinel": False}]
    frames = [{"id": "q1", "session_id": "s1"}]
    lane = [{"id": "q1", "session_id": "s1", "effective_lane": "turbo", "sent_lane": "qa",
             "server_declared_lane": "qa", "lane_source": "explicit", "headers_readable": True}]
    names = ("qa", "analysis", "report")
    original = load(READER).build_lane_table(sidecar, frames, lane, None, names)
    assert original["q1"]["lane"] is None, "真件这一格先站不住 ⇒ 反证没有对照"
    target = mutate(tmp_path, "b",
                    '        if record["lane"] is not None and record["lane"] not in lane_names:',
                    "        if False:")
    mutant = load(target)
    accepted = mutant.build_lane_table(sidecar, frames, lane, None, names)
    assert accepted["q1"]["lane"] == "turbo", "摘掉闭集检查还判取不到 ⇒ 那格本来就没起作用"
    assert accepted["q1"]["origin"] == mutant.ORIGIN_HEADER


def test_knife_c_hardcoded_lane_names_break_a_renamed_window(tmp_path):
    """丙：把派生换成手抄三枚字面 ⇒ 影子根那扇窗当场读不出数（正控＝真件同一扇窗是绿的）。"""
    target = mutate(tmp_path, "c", "    return names",
                    '    return ("qa", "analysis", "report")')
    art = tmp_path / "win-knife-c"
    write_jsonl(art / "run21-sidecar.jsonl",
                [{"id": "a", "kind": "answered", "attempt": 1, "wall_ms": 1000.0, "sentinel": False},
                 {"id": "b", "kind": "answered", "attempt": 1, "wall_ms": 2000.0, "sentinel": False}])
    write_jsonl(art / "run21-sidecar-frames.jsonl", [{"id": "a", "session_id": "s1"},
                                                     {"id": "b", "session_id": "s2"}])
    write_jsonl(art / "run21-sidecar-lane.jsonl",
                [{"id": "a", "session_id": "s1", "effective_lane": "丙档", "sent_lane": "丙档",
                  "headers_readable": True},
                 {"id": "b", "session_id": "s2", "effective_lane": "甲档", "sent_lane": "甲档",
                  "headers_readable": True}])
    argv = ["--window", "run21", "--dir", str(art)]

    real_root, real_script = shadow_root(tmp_path, nodes_src=SHADOW_NODES)
    rc, out = run(real_script, argv)
    assert rc == 0, "正控不成立：真件在同一扇影子窗就读不出数：\n" + out[-900:]
    assert "| 丙档 | 1 |" in out and "| 甲档 | 1 |" in out, out[-900:]

    fake_root, fake_script = shadow_root(tmp_path, nodes_src=SHADOW_NODES,
                                         reader_src=target.read_text(encoding="utf-8"))
    fake_rc, fake_out = run(fake_script, argv)
    assert fake_rc == 2, "改成手抄之后影子窗还是绿的 ⇒「派生」那枚钉是永真钉"
    assert "不在派生闭集里" in fake_out and "三档一枚分位都没算出来" in fake_out, fake_out[-900:]


def test_all_three_knives_left_the_real_reader_byte_for_byte_untouched(tmp_path):
    """四把刀只动副本：真树那枚件的字节一个都不能变（本单对它的写点只有 :134 那一格）。"""
    before = hashlib.sha256(READER.read_bytes()).hexdigest()
    for needle, replacement in (("    if not values:", "    if False:"),
                                ('        if record["lane"] is not None and record["lane"] not in lane_names:',
                                 "        if False:"),
                                ("    return names", '    return ("qa", "analysis", "report")')):
        mutate(tmp_path, str(abs(hash(needle)) % 9999), needle, replacement)
        assert hashlib.sha256(READER.read_bytes()).hexdigest() == before, "反证动到了真树件"
