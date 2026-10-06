"""R707 的牙：发点宿主「怎么拿到本轮身份」认两种机制，两种都不占必须红。

对着的病（总控 10-06 现取）：``tests/test_r688_stage_accounts_are_landed.py`` 原先只把
``config`` 形参当唯一合法路，且只解析 ``app/agents/nodes.py`` 一枚文件的模块级函数——
R695 交出检索腿（可选形参 ``config``）与 chat 改写腿（``arm_turn_identity`` 挂载＋腿内自读）
两条腿之后，那枚钉把合法形状当成了唯一形状，当场红（红句：``AssertionError:
RetrievalPipeline.search``）。口径已按 R695 判据② 那句「红了就说明账要跟着改口径」订正。

🔴 本件存在的意义是证明**订正不是把牙磨平**：摘掉挂载、或摘掉传参，读数必须回到 ``none``。
全程离线：零容器、零模型、零库连接，写盘只写 tmp_path。
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PIN = REPO / "tests" / "test_r688_stage_accounts_are_landed.py"


def _load_pin():
    name = "r688_pin_under_r707"
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, PIN)
    assert spec and spec.loader, "加载不到 R688 那枚常驻牙：" + str(PIN)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


pin = _load_pin()


def test_def_map_names_match_the_defs_ranges_exactly():
    """两把尺必须同名同形：发点表用 ``_defs``，形状表用 ``_def_map``，名字分叉就各说各话。"""
    for path in sorted((REPO / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        from_ranges = {name for _s, _e, name in pin._defs(tree)}
        from_map = set(pin._def_map(tree))
        assert from_map == from_ranges, path.name


def test_both_registered_mechanisms_are_accepted(tmp_path):
    """``config`` 形参与「同模块挂载＋自读」两条路都算拿到身份。"""
    app = tmp_path / "app"
    app.mkdir()
    (app / "both.py").write_text(
        "from app.trace.spans import arm_turn_identity, current_turn_identity\n"
        "\n"
        "def handle_config(config=None):\n"
        "    pass\n"
        "\n"
        "def handle_armed(thread_id):\n"
        "    return current_turn_identity()\n"
        "\n"
        "def mount():\n"
        "    return arm_turn_identity({})\n",
        encoding="utf-8")
    shape_config = pin.host_account_shape("app/both.py::handle_config", root=app)
    shape_armed = pin.host_account_shape("app/both.py::handle_armed", root=app)
    assert shape_config["mechanism"] == "config", shape_config
    assert shape_armed["mechanism"] == "armed", shape_armed


def test_silent_failure_still_reads_none(tmp_path):
    """判据 3 的牙：既不接 config、也没挂载自读 ⇒ none，调用方必须红。"""
    app = tmp_path / "app"
    app.mkdir()
    (app / "anon.py").write_text(
        "def anonymous_host(session_id):\n"
        "    return 1\n",
        encoding="utf-8")
    shape = pin.host_account_shape("app/anon.py::anonymous_host", root=app)
    assert shape["mechanism"] == "none", shape
    assert "config" not in shape["args"]


def test_removing_the_arm_call_turns_the_armed_leg_red(tmp_path):
    """摘掉挂载那一行（真改盘上副本，跑完不复用）⇒ 同一条腿从 armed 掉回 none。

    这一枚排除「armed 其实是被模块里的 import 语句蒙出来的」：只有调用点在才算挂载。
    """
    app = tmp_path / "app"
    app.mkdir()
    source = (
        "from app.trace.spans import arm_turn_identity, current_turn_identity\n"
        "\n"
        "def handle_armed(thread_id):\n"
        "    return current_turn_identity()\n"
        "\n"
        "def mount():\n"
        "    return arm_turn_identity({})\n")
    path = app / "armed.py"
    path.write_text(source, encoding="utf-8")
    assert pin.host_account_shape("app/armed.py::handle_armed", root=app)["mechanism"] == "armed"
    path.write_text(source.replace("    return arm_turn_identity({})\n", "    return None\n"),
                    encoding="utf-8")
    shape = pin.host_account_shape("app/armed.py::handle_armed", root=app)
    assert shape["mechanism"] == "none", shape
    assert shape["module_arms"] is False


def test_the_real_tree_hosts_are_all_identifiable():
    """真树读数：每一枚发点宿主都认得出机制，且两条腿（config 与 armed）今天都在位。

    现取（10-06）：``app/agents/nodes.py`` 五枚宿主与 ``retrieval_pipeline.py`` 那枚走
    ``config``；``app/api/v1/chat.py::_rewrite_followup`` 一枚同时走两条（形参缺省 None、
    为空时自读挂载的本轮身份），所以 ``mechanisms`` 才是真相，单值 ``mechanism`` 只报第一条。
    """
    points = pin.stage_emit_points()
    sites = sorted({site for stage_sites in points.values() for site in stage_sites})
    assert sites, "一枚发点都没有"
    shapes = [pin.host_account_shape(site) for site in sites]
    for shape in shapes:
        assert shape["mechanism"] != "none", shape
        assert set(shape["mechanisms"]) <= {"config", "armed"}, shape
    mechanisms = {name for shape in shapes for name in shape["mechanisms"]}
    assert mechanisms == {"config", "armed"}, mechanisms
    armed = [shape["site"] for shape in shapes if "armed" in shape["mechanisms"]]
    assert armed, "没有一形走挂载自读（R695 的 chat 腿换了路或没了）"
    assert any(site.startswith("app/api/v1/chat.py::") for site in armed), armed
    retrieval = [shape for shape in shapes
                 if shape["site"].startswith("app/rag/retrieval_pipeline.py::")]
    assert retrieval and all("config" in shape["mechanisms"] for shape in retrieval), retrieval


@pytest.mark.parametrize("stage", ["rewrite"])
def test_rewrite_stage_has_a_pointed_emit_site(stage):
    """判据② 的读数口：rewrite 段现在必须交回 >= 1 枚 ``文件::符号``（曾经交回 0 枚）。"""
    points = pin.stage_emit_points()
    assert points.get(stage), "rewrite 段没有可指认发点"
    assert len(points[stage]) >= 1
