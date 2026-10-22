# -*- coding: utf-8 -*-
"""R550 判据②③ · 六把刀全部跑在影子树上：翻绿只能由自洽腿逼出来，摘腿就要重新报过期。

在册那件（tests/test_r483_empty_table_triage_is_derived.py）的刀是「在内存里改 TRIAGE 就能咬」；
本单的判据② 要求的是另一回事：**摘掉事件发射点那一腿，量具必须重新报「应改判 no_seed_path」**。
那只能改产品码，所以每把刀都在 tmp 目录里的一棵影子树上下手（app/ + scripts/ + migrations/ 逐份
拷过去，被跟踪文件一个字都不改——事故 #71 的入规）：

* K1 只摘产品发射腿（`retrieval_pipeline.py` 那枚 `event_type="retrieval.completed"`）：调试面还
  在，产品叠必须归零，裁定必须重新报过期——这一把同时钉判据③ 前半「只被调试面发的仍读 no_seed_path」。
* K2 两枚发射腿全摘：产品面与调试面一起归零，`unused_exemptions` 必须点名那枚用不上的豁免。
* K3a 摘闸门（`if context is None: return None`）：`gate_token` 边消失，道消失。
* K3b 摘问答脸上的挂点（chat.py 两枚 `arm_retrieval_trace(`）：同上一条，且证明脸不是白捡的。
* K4 摘调试面的路由装饰器：产品道照在，但豁免声明用不上了——必须报「豁免成了后门」，不许静默通过。
* K5 把投影守卫里的事件名漂一格：新加的「声明↔现扫互证」牙必须报「不等」。

每把刀自带三格凭据：摘前正控（影子树本身 problems=0）、红了点名哪条、逐字节复原后**再扫一遍**
确认归零。🔴 本件只读盘上文档第五节那份读数，零库、零容器、零模型、零产品码改动。
"""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "r483_empty_tables_triage.py"
DOC_PATH = REPO_ROOT / "docs" / "testing" / "r483-empty-tables-2026-09-29.md"
SHADOW_FOLDERS = ("app", "scripts", "migrations")


def _mod():
    spec = importlib.util.spec_from_file_location("r483_r550_teeth", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _mod()
DOC = DOC_PATH.read_text(encoding="utf-8")
PAYLOAD = M.extract_payload(DOC)
BASELINE = M.baseline_from_probe(M.PROBE_PATH)

#: 六把刀的受害者（全部是产品码，只在影子里被改）：键名 → 相对路径。
VICTIMS = {
    "pipeline": "app/rag/retrieval_pipeline.py",
    "debug": "app/rag/debug.py",
    "chat": "app/api/v1/chat.py",
    "observability": "app/api/v1/observability.py",
    "projections": "app/trace/projections.py",
}
#: 每枚受害者的「摘前」字节指纹，交回纸要逐枚点名（sha256 前 12 位）。
DIGESTS = {}


@pytest.fixture(scope="module")
def shadow(tmp_path_factory):
    root = Path(tmp_path_factory.mktemp("r550_shadow")) / "tree"
    root.mkdir()
    for folder in SHADOW_FOLDERS:
        shutil.copytree(REPO_ROOT / folder, root / folder,
                        ignore=shutil.ignore_patterns("__pycache__"))
    for key, rel in VICTIMS.items():
        DIGESTS[key] = hashlib.sha256((root / rel).read_bytes()).hexdigest()[:12]
    return root


def _snapshot(root) -> dict:
    return {key: (root / rel).read_bytes() for key, rel in VICTIMS.items()}


def _cut(root, key: str, old: str, new: str, count: int = 1):
    path = root / VICTIMS[key]
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == count, (key, old, text.count(old))
    path.write_text(text.replace(old, new, count), encoding="utf-8", newline=M.NL)


def _restore(root, key: str, snap: dict):
    path = root / VICTIMS[key]
    path.write_bytes(snap[key])
    assert path.read_bytes() == snap[key], "逐字节复原失败：" + key
    assert hashlib.sha256(path.read_bytes()).hexdigest()[:12] == DIGESTS[key], key


def _scan(root):
    return M.build_readings(PAYLOAD, M.SourceIndex(root), BASELINE)


def _leg(readings) -> dict:
    return readings["analysis"]["retrieval_traces"]


def _traces_problems(readings) -> list:
    return [item for item in M.validate(readings) if "retrieval_traces" in item]


def _faces(readings) -> tuple:
    product = _leg(readings)["product"]
    return ([route["route"] for route in product["routes"]],
            [route["route"] for route in product["debug_only"]],
            list(product["unused_exemptions"]))


def test_knife_zero_the_shadow_tree_is_green_before_any_cut(shadow):
    """正控：影子树本身必须与盘上同一份判定——不然六把刀全是在量一棵别的树。"""
    readings = _scan(shadow)
    assert M.validate(readings) == [], M.validate(readings)
    product, debug, unused = _faces(readings)
    assert set(product) == {"POST /ask", "POST /approve"}, product
    assert debug == ["POST /retrieval/debug"], debug
    assert unused == [], unused
    assert set(DIGESTS) == set(VICTIMS), DIGESTS


def test_k1_stripping_the_product_emitter_makes_the_ruling_expired_again(shadow):
    snap = _snapshot(shadow)
    _cut(shadow, "pipeline", '            event_type="retrieval.completed",',
         '            event_type="retrieval.completed.stripped",')
    try:
        readings = _scan(shadow)
        product, debug, unused = _faces(readings)
        assert product == [], product
        assert debug == ["POST /retrieval/debug"], debug
        assert unused == [], unused
        problems = _traces_problems(readings)
        assert any("应改判 no_seed_path" in item for item in problems), problems
        assert not any("无主的跨跳边" in item for item in problems), problems
    finally:
        _restore(shadow, "pipeline", snap)
    assert _traces_problems(_scan(shadow)) == []


def test_k2_stripping_every_emitter_also_loses_the_debug_face(shadow):
    snap = _snapshot(shadow)
    _cut(shadow, "pipeline", '            event_type="retrieval.completed",',
         '            event_type="retrieval.completed.stripped",')
    _cut(shadow, "debug", '            event_type="retrieval.completed",',
         '            event_type="retrieval.completed.stripped",')
    try:
        readings = _scan(shadow)
        product, debug, unused = _faces(readings)
        assert product == [], product
        assert debug == [], debug
        assert unused == ["/retrieval/debug"], unused
        problems = _traces_problems(readings)
        assert any("应改判 no_seed_path" in item for item in problems), problems
        assert any("豁免成了后门" in item for item in problems), problems
    finally:
        _restore(shadow, "pipeline", snap)
        _restore(shadow, "debug", snap)
    assert _traces_problems(_scan(shadow)) == []


def test_k3a_a_gate_that_no_longer_closes_the_function_is_not_a_path(shadow):
    snap = _snapshot(shadow)
    _cut(shadow, "pipeline", "    if context is None:\n        return None\n",
         "    if context == 0:\n        return None\n")
    try:
        readings = _scan(shadow)
        surface = _leg(readings)["surface"]
        assert [route["route"] for route in readings["analysis"]["retrieval_traces"]
                ["product"]["routes"]] == [], surface["routes"]
        assert not [item for item in surface["bridges"] if item["kind"] == "gate_token"], (
            surface["bridges"])
        assert any("record_retrieval_completed" in item for item in surface["trail"]), (
            surface["trail"])
        assert any("应改判 no_seed_path" in item for item in _traces_problems(readings))
    finally:
        _restore(shadow, "pipeline", snap)
    assert _traces_problems(_scan(shadow)) == []


def test_k3b_removing_the_arm_sites_on_the_chat_face_removes_the_path(shadow):
    snap = _snapshot(shadow)
    _cut(shadow, "chat", "            trace_token = arm_retrieval_trace(",
         "            trace_token = stripped_arm_call(", count=2)
    try:
        readings = _scan(shadow)
        product, debug, _unused = _faces(readings)
        assert product == [], product
        assert debug == ["POST /retrieval/debug"], debug
        surface = _leg(readings)["surface"]
        #: 🔴 这一格与 K3a 的区别必须看得见：闸门那条边还在（armer 与 `.set(` 都在树里），
        #: 消失的只是「谁把身份挂上来」那一跳的调用者。所以「脸没了就不算道」这条判据是
        #: 挂在挂点上的，不是我删掉一条边才凑出来的红。
        assert [item for item in surface["bridges"] if item["kind"] == "gate_token"], (
            surface["bridges"])
        assert not [item for item in surface["routes"] if "chat.py" in item["file"]], (
            surface["routes"])
        assert any("应改判 no_seed_path" in item for item in _traces_problems(readings))
    finally:
        _restore(shadow, "chat", snap)
    assert _traces_problems(_scan(shadow)) == []


def test_k4_a_debug_route_that_is_no_longer_there_must_scream(shadow):
    snap = _snapshot(shadow)
    _cut(shadow, "observability",
         '@router.post("/retrieval/debug", responses=_ERROR_RESPONSES)',
         "# (R550 knife K4: the debug face lost its route)")
    try:
        readings = _scan(shadow)
        product, debug, unused = _faces(readings)
        assert set(product) == {"POST /ask", "POST /approve"}, product
        assert debug == [], debug
        assert unused == ["/retrieval/debug"], unused
        problems = _traces_problems(readings)
        assert any("豁免成了后门" in item for item in problems), problems
        assert not any("应改判 no_seed_path" in item for item in problems), problems
    finally:
        _restore(shadow, "observability", snap)
    assert _traces_problems(_scan(shadow)) == []


def test_k5_a_drifted_guard_label_breaks_the_declaration_agreement(shadow):
    snap = _snapshot(shadow)
    _cut(shadow, "projections", '    if event_type == "retrieval.completed":',
         '    if event_type == "retrieval.drifted":')
    try:
        readings = _scan(shadow)
        problems = _traces_problems(readings)
        assert any("声明的事件与现扫守卫到的不等" in item for item in problems), problems
    finally:
        _restore(shadow, "projections", snap)
    assert _traces_problems(_scan(shadow)) == []


def test_the_whole_shadow_tree_is_byte_for_byte_untouched_after_every_knife(shadow):
    for key, rel in VICTIMS.items():
        current = (shadow / rel).read_bytes()
        assert hashlib.sha256(current).hexdigest()[:12] == DIGESTS[key], key
        assert current == (REPO_ROOT / rel).read_bytes(), key
    assert M.validate(_scan(shadow)) == []