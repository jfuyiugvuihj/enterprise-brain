"""R601 · 常驻钉不许把「此刻盘面有没有某枚产物」当判据（前后差分那一刀的牙）。

一手病灶（本班 10-03 在本树现取，不是转述）：
  ``tests/test_r181_text_frame_ruler.py::test_the_replay_produces_no_bytes_inside_the_repo``
  扫 ``scripts/*frames*.jsonl`` 断言空集。双写窗 10-03 08:52:05 把采集器产物
  ``collect-sidecar-frames.jsonl``（26,095 B，sha256 EA1CC7247804AEB7…）漏进仓库 ``scripts/``，
  这枚钉从那一刻起恒红、与任何改动无关；10-03 总控并 R590 时就被它挡了一次
  （全过程记在主树 commit ``b78ecd8`` 的 subject）。本树复证：把那枚产物按字节摆回
  ``scripts/`` ⇒ 旧判法 rc=1；搬回仓外 ⇒ rc=0，两态之间那枚钉一个字未改。

真根因在落点，不在这枚钉：``scripts/eval_transport_ask_v2.py:228`` 的 ``SIDECAR`` 缺省是
``Path(__file__).with_name("collect-sidecar.jsonl")`` —— 派工词那句「相对 cwd」要订正：它相对
**脚本自己**，比相对 cwd 更硬，无论从哪里起窗，不设 ``EVAL_SIDECAR`` 就一律往 ``scripts/`` 写；
帧账（:236）跟着它走。``refuse_inside_repo`` 从前只有 driver 那条腿有，采集器那条腿一枚闸都没有
（判据② 本单补齐），driver 那条腿自己也只闸了八枚落点里的两枚。

本件全部离线，判决全部走影子根（``tmp_path`` 造的假树），真仓一字节都不许多：
 ① 两把反证（判据③）：a 真写点新落一枚 ``*frames*.jsonl`` 进 ``scripts/`` ⇒ 尺读「不绿」；
    b 原有产物在场 ⇒ 本钉必须绿，且同一份盘面下**旧判法**必须红（不摆这一刀，「绿」可能只是空响）；
 ② 结构钉：常驻钉里不许再出现「盘面清单 == 空集」这一形，也不许出现任何降级记号；
 ③ 把手钉：采集器与 driver 两条腿对同一份盘面给同一个判决（含 ``..`` 绕行与跨树 ``--repo``）；
 ④ ``test_z_`` 收尾：真仓产物清单 + 四枚被治件的字节指纹，与 import 那一刻逐字节全等。

尺一份都不新造：``frames_inventory`` / ``new_frames_since`` / ``repo_write_judgment`` /
``build_adapter`` 全部取自被治的那枚件（``importlib`` 按路径载），影子根与真仓共用同一把尺。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
R181_SOURCE = REPO_ROOT / "tests" / "test_r181_text_frame_ruler.py"
TRANSPORT_SOURCE = REPO_ROOT / "scripts" / "eval_transport_ask_v2.py"
COLLECTOR_SOURCE = REPO_ROOT / "scripts" / "collect_evaluation_answers.py"
DRIVER_SOURCE = REPO_ROOT / "scripts" / "eval_window_shard_driver.py"
RESIDENT_TEST = "test_the_replay_produces_no_bytes_inside_the_repo"
#: 今天漏进仓里的那枚名字（transport 的在册缺省命名：与 SIDECAR 同目录、同名加 -frames）。
STRAY_NAME = "collect-sidecar-frames.jsonl"
DEFAULT_SIDECAR_NAME = "collect-sidecar.jsonl"
#: 影子根用的产物面与真仓同一枚 glob（不许给影子道另造一把更窄的尺）。
SCAN = "scripts/*frames*.jsonl"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec is not None and spec.loader is not None, "载不到被治的那枚件：" + str(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


r181 = _load("r601_r181_under_test", R181_SOURCE)
transport = _load("r601_transport_under_test", TRANSPORT_SOURCE)
collector = _load("r601_collector_under_test", COLLECTOR_SOURCE)
driver = _load("r601_driver_under_test", DRIVER_SOURCE)


def _repo_state() -> dict:
    """真仓这一格进出必须逐字节全等：产物清单（差分用）+ 四枚被治件的字节指纹。"""
    state = dict(r181.frames_inventory(REPO_ROOT))
    for path in (R181_SOURCE, TRANSPORT_SOURCE, COLLECTOR_SOURCE, DRIVER_SOURCE):
        blob = path.read_bytes()
        state[path.name] = (len(blob), hashlib.sha256(blob).hexdigest())
    return state


AT_IMPORT = _repo_state()


def _shadow_repo(tmp_path: Path) -> Path:
    """一棵只有 ``scripts/`` 的影子树：被驱动的尺看的就是这个形状。"""
    root = tmp_path / "shadow-repo"
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    return root


def _replay_into(sidecar: Path, tmp_path: Path) -> None:
    """跑**真的** 105 题重放（真 transport + 真采集器 + 记账假 opener），落点指到 ``sidecar``。

    帧账不许我手摆：它由 ``transport.frame_ledger_path()`` 按在册缺省命名从 sidecar 派生，
    所以「新落一枚 ``*frames*.jsonl``」这条罪是写点自己犯的，不是道具做的。
    """
    module = r181.build_adapter(tmp_path)
    module.SIDECAR = Path(sidecar)
    r181._replay(module, tmp_path)


# ===== 一、判据③ 的两把反证 =====

def test_counter_evidence_a_a_new_frames_artifact_written_by_a_real_replay_turns_the_pin_red(tmp_path):
    """牙 a：真写点新落一枚 *frames*.jsonl 进 scripts/ ⇒ 差分必点名它 ⇒ 本钉红。"""
    root = _shadow_repo(tmp_path)
    before, new, green = r181.repo_write_judgment(
        root, lambda: _replay_into(root / "scripts" / DEFAULT_SIDECAR_NAME, tmp_path))
    assert before == {}, "影子根进门时不该带原有产物：" + str(sorted(before))
    assert new == [STRAY_NAME], "新落一枚而差分没点名：" + str(new)
    assert green is False, "新落一枚产物而尺读成绿 ⇒ 这枚牙是纸牙"
    landed = root / "scripts" / STRAY_NAME
    assert landed.is_file(), "落点应由真写点产生：" + str(landed)
    assert r181.frames_inventory(root)[STRAY_NAME] == (
        landed.stat().st_size, hashlib.sha256(landed.read_bytes()).hexdigest())


def test_counter_evidence_b_a_pre_existing_artifact_keeps_the_pin_green(tmp_path):
    """牙 b（今天缺的那半边）：原有产物在场 ⇒ 本钉必须绿；同一份盘面上旧判法必须红。"""
    root = _shadow_repo(tmp_path)
    stray = root / "scripts" / STRAY_NAME
    seed = json.dumps({"id": "pre-existing-window", "text_frames": 3}, ensure_ascii=False) + "\n"
    blob = seed.encode("utf-8")
    stray.write_bytes(blob)  # 按字节写：write_text 会把换行翻成 CRLF，字节数就不是我算的那一枚
    stamp = (len(blob), hashlib.sha256(blob).hexdigest())

    before, new, green = r181.repo_write_judgment(
        root, lambda: _replay_into(tmp_path / "elsewhere" / "run13-sidecar.jsonl", tmp_path))
    assert sorted(before) == [STRAY_NAME], "跑前清单没拍到那枚原有产物：" + str(sorted(before))
    assert new == [], "原有产物被算成了本单罪证（差分退化回盘面判据）：" + str(new)
    assert green is True, "原有产物在场时本钉必须绿——10-03 挡掉 R590 的正是这一格"
    assert r181.frames_inventory(root)[STRAY_NAME] == stamp, "跑完把盘上原有产物的字节改了"
    # 旧判法（此刻清单 == 空集）在同一份盘面上必须红：不摆这一刀，上面的「绿」可能只是空响。
    old_verdict = sorted(p.name for p in root.glob(SCAN))
    assert old_verdict == [STRAY_NAME], "影子盘面没造出来，牙 b 空响：" + str(old_verdict)


def test_the_delta_is_not_an_exemption_list(tmp_path):
    """原有 1 枚 + 新落 2 枚 ⇒ 新增清单逐枚点名两枚。扫描面没缩，也没有豁免名单。"""
    root = _shadow_repo(tmp_path)
    (root / "scripts" / STRAY_NAME).write_text("pre-existing\n", encoding="utf-8")

    def leak_two():
        (root / "scripts" / "run14-frames.jsonl").write_text("one\n", encoding="utf-8")
        (root / "scripts" / "second-frames.jsonl").write_text("two\n", encoding="utf-8")
        # 顺带一形：覆写那枚原有件。差分按「枚数」只认新落的名字，覆写不在返回里——
        # 这一格由被治件里那条「落点必须在仓外」补刀与下面的把手钉兜住，写在纸上当已知边界。
        (root / "scripts" / STRAY_NAME).write_bytes(b"")

    before, new, green = r181.repo_write_judgment(root, leak_two)
    assert sorted(before) == [STRAY_NAME]
    assert new == ["run14-frames.jsonl", "second-frames.jsonl"], new
    assert green is False


# ===== 二、结构钉：常驻钉不许再读「此刻盘面」 =====

def test_the_resident_pin_reads_a_delta_and_no_longer_the_live_disk_state():
    tree = ast.parse(R181_SOURCE.read_text(encoding="utf-8"))
    target = next((node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == RESIDENT_TEST), None)
    assert target is not None, "常驻钉 " + RESIDENT_TEST + " 不在了"
    called = {node.func.id for node in ast.walk(target)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "repo_write_judgment" in called, "常驻钉没走那把差分尺：" + str(sorted(called))
    attrs = {node.func.attr for node in ast.walk(target)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert "glob" not in attrs and "rglob" not in attrs, \
        "常驻钉里再出现 glob 就是把盘面当判据回来了：" + str(sorted(attrs))
    empty_comparisons = [node for node in ast.walk(target)
                         if isinstance(node, ast.Compare)
                         and any(isinstance(op, ast.Eq) for op in node.ops)
                         and isinstance(node.comparators[0], ast.List)
                         and not node.comparators[0].elts]
    assert empty_comparisons == [], \
        "常驻钉本体里不许再出现「清单 == 空集」这一形，判定只由 repo_write_judgment 交回：" + \
        str(len(empty_comparisons))


def test_the_treated_files_carry_no_downgrade_marker():
    """不许 skip／xfail／只跑某一枚——判据① 把这条路写死了不走。"""
    for path in (R181_SOURCE, Path(__file__)):
        text = path.read_text(encoding="utf-8")
        for marker in ("pytest.mark." + "skip", "pytest.mark." + "xfail", "pytest.mark." + "skipif",
                       "pytest." + "skip(", "pytest." + "xfail("):
            assert marker not in text, path.name + " 里出现了降级记号：" + marker


# ===== 三、把手钉：两条腿同一份盘面 ⇒ 同一个判决 =====

#: (相对影子根的路径, 该不该拒)。「拒」=落点在仓内。含一枚 ``..`` 绕行与两枚仓外件。
HANDLE_CASES = (
    ("scripts/" + DEFAULT_SIDECAR_NAME, True),
    ("scripts/" + STRAY_NAME, True),
    ("", True),                                          # 落点 = 仓根自己
    ("a/b/c/frames.jsonl", True),
    ("outside/../scripts/collect-sidecar.jsonl", True),  # .. 绕行不许骗过闸
    ("scripts/nope-not-there.jsonl", True),              # 件不在也要拒：闸看落点不看在场
    ("../elsewhere/sidecar.jsonl", False),
    ("../scripts-twin/collect-sidecar.jsonl", False),    # 与 scripts 同名但仓外
)


def _verdict(leg, error, path: Path, root: Path) -> tuple:
    try:
        leg(path, "落点", root=root)
    except error as exc:
        return ("refuse", str(exc) or getattr(exc, "why", ""))
    return ("pass", "")


@pytest.mark.parametrize("rel, refuses", HANDLE_CASES)
def test_both_legs_give_the_same_verdict_on_the_same_disk_state(tmp_path, rel, refuses):
    root = _shadow_repo(tmp_path)
    path = root / rel if rel else root
    want = "refuse" if refuses else "pass"
    got_collector = _verdict(collector.refuse_inside_repo, collector.LandingSpotError, path, root)
    got_driver = _verdict(driver.refuse_inside_repo, driver.Refuse, path, root)
    assert (got_collector[0], got_driver[0]) == (want, want), (rel, got_collector, got_driver)


def test_both_legs_say_the_same_word_when_they_refuse(tmp_path):
    """同名同语义＝连文案都能被 runbook 按行取数：同一个词「落在仓内」。"""
    root = _shadow_repo(tmp_path)
    path = root / "scripts" / STRAY_NAME
    with pytest.raises(collector.LandingSpotError) as got:
        collector.refuse_inside_repo(path, "帧账", root=root)
    assert "落在仓内：" in str(got.value) and "帧账" in str(got.value), str(got.value)
    with pytest.raises(driver.Refuse) as got2:
        driver.refuse_inside_repo(path, "帧账", root=root)
    assert "落在仓内：" in got2.value.why and "帧账" in got2.value.why, got2.value.why


# ===== 四、采集器那条腿：写第一个字节之前就拒 ======

class _LedgerLeg:
    """一枚假的「transport 所属模块」，只用来喂 ``window_landing_spots`` 的两枚落点。"""

    def __init__(self, sidecar, frames, name="eval_transport_ask_v2"):
        self.__name__ = name
        if sidecar is not None:
            self.SIDECAR = sidecar
        self._frames = frames

    def frame_ledger_path(self):
        return Path(self._frames)


class _Installed:
    def __init__(self, name, module):
        self.name = name
        self.module = module

    def __enter__(self):
        self.prev = sys.modules.get(self.name)
        sys.modules[self.name] = self.module
        return self.module

    def __exit__(self, *exc):
        if self.prev is None:
            sys.modules.pop(self.name, None)
        else:
            sys.modules[self.name] = self.prev
        return False


def _fake_module(name, module):
    """把假模块挂进 ``sys.modules`` 再摘下来（不动真仓、不动真 import 链）。"""
    return _Installed(name, module)


def _fake_transport_callable(module_name: str):
    def transport(row):  # 永不调用：只让采集器问得出所属模块
        raise AssertionError("反证里不许真打 transport")
    transport.__module__ = module_name
    return transport


#: 采集器里那两枚落点的名字（问不着那一格也靠它们点名）。
SIDECAR_SPOT = "侧车"
LEDGER_SPOT = "帧账"


def test_the_collector_asks_its_two_evidence_spots_from_the_module_itself(tmp_path):
    root = _shadow_repo(tmp_path)
    sidecar = tmp_path / "elsewhere" / "run13-sidecar.jsonl"
    frames = tmp_path / "elsewhere" / "run13-sidecar-frames.jsonl"
    leg = _LedgerLeg(sidecar, frames)
    with _fake_module("eval_transport_ask_v2", leg):
        spots = collector.window_landing_spots(tmp_path / "answers.jsonl",
                                               _fake_transport_callable("eval_transport_ask_v2"))
    assert [what for what, _ in spots] == ["答案件", SIDECAR_SPOT, LEDGER_SPOT], spots
    assert [str(p) for _, p in spots] == [str(tmp_path / "answers.jsonl"), str(sidecar), str(frames)]
    assert not (root / "scripts" / STRAY_NAME).exists(), "影子根不该被这一枚用例写过"


def test_the_collector_refuses_a_repo_internal_ledger_before_writing(tmp_path):
    """今天那形：EVAL_SIDECAR 没设 ⇒ 侧车与帧账都指进仓内 ⇒ 开窗前就拒。"""
    root = _shadow_repo(tmp_path)
    leg = _LedgerLeg(root / "scripts" / DEFAULT_SIDECAR_NAME, root / "scripts" / STRAY_NAME)
    with _fake_module("eval_transport_ask_v2", leg):
        with pytest.raises(collector.LandingSpotError) as got:
            collector.refuse_landing_spots(tmp_path / "answers.jsonl",
                                           _fake_transport_callable("eval_transport_ask_v2"),
                                           root=root)
    assert "落在仓内" in str(got.value), str(got.value)


def test_cannot_ask_the_ledger_is_a_refusal_not_a_pass(tmp_path):
    """transport 名字对得上而落点问不着 ⇒ 按「问不到」拒（与 driver 的 --env-file 同一口径）。"""
    leg = _LedgerLeg(None, tmp_path / "elsewhere" / "f.jsonl")
    with _fake_module("eval_transport_ask_v2", leg):
        with pytest.raises(collector.LandingSpotError) as got:
            collector.refuse_landing_spots(tmp_path / "answers.jsonl",
                                           _fake_transport_callable("eval_transport_ask_v2"))
    assert "问不到" in str(got.value), str(got.value)


def test_the_main_gate_refuses_the_factory_default_before_any_bytes(tmp_path, monkeypatch, capsys):
    """``main()`` 那一层的真形：两枚环境变量都不设 + 真 transport ⇒ rc=2，且采集一次都没开打。"""
    monkeypatch.delenv("EVAL_SIDECAR", raising=False)
    monkeypatch.delenv("EVAL_FRAME_LEDGER", raising=False)
    monkeypatch.setenv("EVAL_BASE_URL", "http://127.0.0.1:9")   # discard 端口：谁也打不到
    monkeypatch.syspath_prepend(str(REPO_ROOT / "scripts"))

    def never_collect(*args, **kwargs):
        raise AssertionError("闸必须在采集之前：collect_answers 被调到了")
    monkeypatch.setattr(collector, "collect_answers", never_collect)

    sidecar = REPO_ROOT / "scripts" / DEFAULT_SIDECAR_NAME
    sidecar_before = sidecar.exists()  # 读**差分**：盘上原来在不在都不是本单罪证
    before, new, green = r181.repo_write_judgment(
        REPO_ROOT,
        lambda: collector.main(["--transport", "eval_transport_ask_v2:transport",
                                "--output", str(tmp_path / "answers.jsonl")]))
    out = capsys.readouterr()
    assert sidecar.exists() == sidecar_before, "拒在写之前：这一枚闸不该多落侧车的一个字节"
    assert green and new == [], "拒在写之前，仓内一枚帧账都不许多：" + str(new)
    # before（跑前真仓清单）只作凭据点名，不进判据：一枚常驻钉不许因为它人在场就红。


def test_the_main_gate_refuses_a_repo_internal_answers_file_even_for_a_dry_run(tmp_path, capsys):
    """dry-run 也过同一枚闸：样本答案件指进仓内 ⇒ 拒（从前它会照写）。"""
    target = REPO_ROOT / "scripts" / "r601-sample-answers.jsonl"
    before = target.exists()
    rc = collector.main(["--dry-run", "--allow-sample", "--output", str(target)])
    out = capsys.readouterr()
    assert rc == 2, (rc, out.out, out.err)
    assert "落在仓内" in out.err, out.err
    assert target.exists() == before, "拒在写之前：样本答案件一枚字节都不许多落"


def test_the_main_gate_still_lets_a_repo_external_dry_run_through(tmp_path, capsys):
    """正控：仓外落点不许被闸误拦（焊死才是假安全）。"""
    rc = collector.main(["--dry-run", "--allow-sample", "--output", str(tmp_path / "a.jsonl")])
    assert rc == 0, (rc, capsys.readouterr().err)
    assert (tmp_path / "a.jsonl").is_file()


# ===== 五、driver 那条腿：逐枚落点，且对「另一棵树」也过闸 =====

def test_the_driver_gates_every_landing_spot_not_only_two(tmp_path):
    """从前只闸 产物目录／合并件；侧车、帧账、指纹件、分片目录、日志逐枚都得点名。"""
    P = driver.paths("r601", Path(tmp_path) / "evalrun")
    for key, label in driver.LANDING_SPOTS:
        hijacked = dict(P)
        hijacked[key] = REPO_ROOT / "scripts" / ("r601-" + key + ".jsonl")
        with pytest.raises(driver.Refuse) as got:
            driver.refuse_landing_spots(hijacked)
        assert label in got.value.why and "落在仓内" in got.value.why, (key, got.value.why)


def test_the_driver_refuses_products_that_would_dirty_the_tree_being_measured(tmp_path):
    """``--repo`` 指另一棵真树（``.git`` 在位）时，往那棵树漏产物同样当场拒——从前只比自己这棵。"""
    other = tmp_path / "run-tree"
    (other / ".git").mkdir(parents=True)
    P = driver.paths("r601", other / "scripts")
    with pytest.raises(driver.Refuse) as got:
        driver.refuse_landing_spots(P, repo=other)
    assert "落在仓内" in got.value.why, got.value.why


def test_a_plain_directory_as_repo_is_not_mistaken_for_a_tree(tmp_path):
    """``--repo`` 指一枚临时目录（在册量具自测就这么用）不算仓库：脏不了任何一棵树，不许误拒。"""
    scratch = tmp_path / "scratch"
    (scratch / "scripts").mkdir(parents=True)
    driver.refuse_landing_spots(driver.paths("r601", scratch / "scripts"), repo=scratch)


def test_the_collector_env_pins_both_evidence_files_outside_the_repo(tmp_path):
    """判据②：driver 现在自己把帧账也钉给采集器，不再靠 transport 的跟随缺省。"""
    env_file = tmp_path / "deploy.env.server"
    env_file.write_text("EB_EVAL_PASSWORD=x\n", encoding="utf-8")
    tmp_dir = tmp_path / "evalrun"
    sidecar = tmp_dir / "run13-sidecar.jsonl"
    frames = tmp_dir / "run13-sidecar-frames.jsonl"
    env = driver.collector_env(tmp_dir, sidecar, dict(os.environ), env_file, tmp_path,
                               "http://127.0.0.1:8001", "evalbot", False, frames=frames)
    assert Path(env["EVAL_SIDECAR"]) == sidecar
    assert Path(env["EVAL_FRAME_LEDGER"]) == frames
    derived = driver.collector_env(tmp_dir, sidecar, dict(os.environ), env_file, tmp_path,
                                   "http://127.0.0.1:8001", "evalbot", False)
    assert Path(derived["EVAL_FRAME_LEDGER"]) == frames, "缺 frames 时按 transport 同一把命名派生"
    for key in ("EVAL_SIDECAR", "EVAL_FRAME_LEDGER"):
        assert REPO_ROOT not in Path(env[key]).resolve().parents, key


# ===== 六、收尾：以上各把都不许碰真仓 =====

def test_z_the_knives_left_the_real_repo_byte_identical():
    """每把刀跑完，真仓产物清单 + 四枚被治件必须还是进门那一刻那几枚指纹（R496 同规）。"""
    now = _repo_state()
    drift = {key: (AT_IMPORT.get(key), now.get(key))
             for key in set(AT_IMPORT) | set(now) if AT_IMPORT.get(key) != now.get(key)}
    assert drift == {}, "影子刀动到了真仓：" + json.dumps(sorted(drift.items()), ensure_ascii=False, default=str)