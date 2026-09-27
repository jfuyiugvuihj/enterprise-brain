# -*- coding: utf-8 -*-
"""R379 格三：route_main 的**收尾两支**（R206a 补 doc / R42 弃权轮补 doc）今天进了等值门。

事由（总控 2026-09-27 派工，主树 ``285e265`` 现场复核属实）：等值门
``branch_equivalence()`` 从前只切 ``route_main`` 的分派那两支（计划优先 / 关键词兜底），
而现场在后面还接了两段改派腿的 if —— 那 105 题 diffs=0 属**巧合**：现场改收尾那两支之一，
本件的镜像照旧同形，读数照旧出，谁也不知道派腿口径已经换了。

本件吃两把对照刀，都真跑：

  🔪 **覆盖后抓得到**：把影子副本里那两支各改一刀（摘掉补派 / 换补的腿 / 摘掉档位判别），
     等值门必须逐题点名，红话里带出处与本件/现场两侧的值。
  🔪 **覆盖前抓不到**：同一批影子副本交给基点那份（``git show`` 取，只当素材跑），
     它的等值门回回是空表 ⇒ 这一格在修之前是瞎的。这条不是推理论证，是两枚模块各跑一遍。

外加一枚口径钉：收尾那两支今天对这批题**确实开口**（不是门对着空场），而把两支纳入覆盖
之后对外读数一格都没漂——``build_table`` 的每一格与基点逐字相等（改的是门的覆盖面，
不是表的口径；那一条若要走，得另派一单，见交回单"只报不改"）。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/rehearse_eval_window.py"
SCRIPT_REL = "scripts/rehearse_eval_window.py"
BASE = "HEAD"
ORCH = "app/agents/orchestrator.py"

#: 三把刀：两支持刀各一，外加"摘掉档位判别"这一把只有 R42 会红的。
MUTATIONS = (
    ("R206a 摘掉补派", "        workers = caliber_filled",
     "        workers = list(workers)", "收尾·计划优先路"),
    ("R42 换一条腿补派", '        workers = ["doc"]\n        logger.info("[R42]',
     '        workers = ["data"]\n        logger.info("[R42]', "收尾·关键词路"),
    ("R42 摘掉档位判别", "    if not workers and abstained and "
     "classify_route(intent_text).lane == LANE_QA:",
     "    if not workers and abstained:", "收尾·关键词路"),
)


def load_script(module_name: str, path: Path):
    """按源码文本现编译加载（格四那一族的自律：绝不碰 __pycache__）。"""
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    exec(compile(path.read_text(encoding="utf-8-sig"), str(path), "exec"), module.__dict__)
    return module


def load_base(module_name: str, tmp_root: Path):
    """把基点那份取出来当**素材**跑一遍（R346：冻结的历史只准当素材，不上等号）。"""
    text = subprocess.run(["git", "show", f"{BASE}:{SCRIPT_REL}"], cwd=str(REPO),
                          capture_output=True, check=True).stdout.decode("utf-8")
    path = tmp_root / "base_rehearse.py"
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="")
    module = load_script(module_name, path)
    module.__dict__["REPO_ROOT"] = REPO           # 量的还是这一棵树
    return module


@pytest.fixture(scope="module")
def mod():
    return load_script("r379_tail_target", SCRIPT)


@pytest.fixture(scope="module")
def base_mod(tmp_path_factory):
    return load_base("r379_tail_base", tmp_path_factory.mktemp("r379_base"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_shadow(tmp_path: Path, mod, rel, old, new) -> Path:
    """把预演件读的全部现场原样复制进影子，再就地改一枚（盘上那枚必须一字不动）。"""
    root = tmp_path / "shadow"
    before = {name: sha256(REPO / name) for name in sorted(set(mod.REPO_RELS.values()))}
    for name in sorted(set(mod.REPO_RELS.values())):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, target)
    path = root / rel
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    assert text.count(old) == 1, f"影子里锚点不唯一：{rel} / {old[:40]!r} 实有 {text.count(old)} 处"
    path.write_text(text.replace(old, new), encoding="utf-8", newline="")
    after = {name: sha256(REPO / name) for name in before}
    assert after == before, "盘上的被跟踪文件被就地改写了（判据戊的红线）"
    return root


# ==================== ① 门的覆盖面 ====================


def test_the_gate_now_cuts_the_route_tail_too(mod):
    """收尾切片必须真的存在，而且切到的是那两支（三枚语句：一条赋值 + 两枚 if）。"""
    stmts = mod.route_tail_statements()
    text = "\n".join(ast.unparse(node) for node in stmts)
    assert len(stmts) == 3, [type(node).__name__ for node in stmts]
    assert "kb_leg_for_caliber" in text and "classify_route" in text and "LANE_QA" in text
    kw, plan = mod.read_route_tail_slices()
    for fn in (kw, plan):
        assert fn.__code__.co_filename == "<rehearsal:app/agents/orchestrator.py::route_main>", \
            f"收尾切片不是从现场切的：{fn.__code__.co_filename}"


def test_the_branch_slices_still_cut_only_the_dispatch_pair(mod):
    """分派那两支的切片没被顺手加长：它引用的名字一枚都不许多（覆盖面扩到收尾是另一枚切片）。"""
    kw, plan = mod.read_route_branch_slices()
    for fn in (kw, plan):
        names = set(fn.__code__.co_names)
        assert "kb_leg_for_caliber" not in names and "classify_route" not in names, names


def test_the_tail_rules_are_carried_in_and_not_retyped(mod):
    """两支的规则一枚都不抄：补派哪条腿问现场，档位怎么判也问现场；本件只镜像 if 的形状。"""
    assert mod.LIVE_KB_LEG_FOR_CALIBER.__code__.co_filename == \
        "<rehearsal:app/agents/orchestrator.py>"
    names = mod.route_final_workers.__code__.co_names
    assert names == ("LIVE_KB_LEG_FOR_CALIBER", "classify_route", "lane", "LANE_QA"), names
    text = SCRIPT.read_text(encoding="utf-8-sig")
    assert "KB_CALIBER_MARKERS = (" not in text, "本件里又长出一份口径词表抄本"


def test_the_tail_cells_are_registered_without_line_numbers(mod):
    for cell in ("SIDE_EFFECT_LEGS", "CALIBER_MARKERS"):
        assert cell in mod.FACT_READERS, cell
    for cell in ("CALIBER_RULE", "ROUTE_TAIL_SLICES", "SIDE_EFFECT_LEGS", "CALIBER_MARKERS"):
        anchor = mod.FACT_ANCHORS[cell]
        assert "::" in anchor, anchor
        assert not re.search(r":\d", anchor), f"出处里混进行了号：{anchor}"
    assert mod.FACT_READERS["CALIBER_MARKERS"]() == tuple(
        mod.read_caliber_markers()), "口径词表两读不等早该红在闸门里"
    assert mod.FACT_READERS["SIDE_EFFECT_LEGS"]() == ("chart", "export")


# ==================== ② 不动则绿 ====================


def test_the_mirrors_agree_with_the_live_tail_on_every_row(mod):
    rows = mod.load_rows()
    assert len(rows) == 105, len(rows)
    assert mod.branch_equivalence(rows) == [], \
        "本件的镜像与 route_main 现场切片（含收尾两支）不同形：\n" + "\n".join(
            mod.branch_equivalence(rows))


def test_the_guard_gate_still_passes_with_the_wider_coverage(mod):
    assert mod.guard_facts(mod.load_rows()) == []


def test_the_tail_actually_opens_its_mouth_on_this_question_set(mod):
    """反空转：这两支对这批题确实会改派腿，否则上面那把刀是砍在空场上的。"""
    rows = mod.load_rows()
    tables = mod.read_kw_tables()
    order = ("chart_kw", "data_kw", "export_kw", "doc_kw")
    kw_live, _plan_live = mod.read_route_branch_slices()
    fired_r42 = fired_caliber = 0
    for row in rows:
        question = str(row["question"])
        planned = mod.plan_workers(question)
        intent = mod._intent(question)
        branch = kw_live([], intent, planned, *[tables[name] for name in order])
        final = mod.route_final_workers(intent, list(branch), True)
        if final != branch:
            if "doc" in final:
                fired_caliber += branch and 1 or 0
                fired_r42 += (not branch) and 1 or 0
    assert fired_r42 > 0, "R42 那一支在 105 题上一次都没开口：门对着空场"
    assert fired_caliber > 0, "R206a 那一支在 105 题上一次都没开口：门对着空场"


# ==================== ③ 反证刀：覆盖后抓得到 ====================


@pytest.mark.parametrize("label, old, new, expect", MUTATIONS,
                         ids=[case[0] for case in MUTATIONS])
def test_a_mutation_of_either_tail_branch_goes_red(tmp_path, mod, label, old, new, expect):
    root = build_shadow(tmp_path, mod, ORCH, old, new)
    rows = mod.load_rows()
    lines = mod.branch_equivalence(rows, root)
    tail = [line for line in lines if "收尾·" in line]
    assert tail, f"{label}：改了现场收尾那一支，等值门却没红。整份：{lines}"
    assert any(expect in line for line in tail), f"{label}：没红在该红的哪一路：{tail}"
    assert any("route_main" in line for line in tail), tail
    gate = mod.guard_facts(rows, root)
    assert any("收尾·" in line for line in gate), f"{label}：开机闸门没拦下：{gate}"
    # 只准红在收尾那一圈：分派那两支的字面形状没动，红它就是把刀使歪了
    assert not [line for line in lines
                if "收尾·" not in line and "路 本件=" in line], lines


def test_the_pre_fix_ruler_is_blind_to_exactly_those_mutations(tmp_path, mod, base_mod):
    """同一批刀口端给基点那份：它的等值门回回空表 ⇒ "覆盖前抓不到"这一句是真跑出来的。"""
    rows = base_mod.load_rows()
    blind = []
    for label, old, new, _expect in MUTATIONS:
        root = build_shadow(tmp_path / label.replace(" ", "_"), base_mod, ORCH, old, new)
        caught_new = [line for line in mod.branch_equivalence(rows, root) if "收尾·" in line]
        caught_old = base_mod.branch_equivalence(rows, root)
        blind.append((label, len(caught_new), len(caught_old)))
        assert caught_new, f"{label}：新门也没抓到，那这条对比不成立"
        assert caught_old == [], f"{label}：基点那份居然也抓到了：{caught_old}"
    assert all(old_count == 0 for _label, _new_count, old_count in blind), blind


# ==================== ④ 覆盖面变了，对外读数没变 ====================


def test_the_shipped_table_is_byte_for_byte_what_it_was(mod, base_mod):
    """纳入覆盖 = 门上多两格比对，不是表里多两列数：逐题表与基点逐字相等。"""
    rows = mod.load_rows()
    assert len(rows) == len(base_mod.load_rows())
    mine = mod.build_table(rows, {})
    theirs = base_mod.build_table(base_mod.load_rows(), {})
    assert [tuple(sorted(item.items())) for item in mine] == \
        [tuple(sorted(item.items())) for item in theirs], \
        "收尾两支进了表：那是改对外口径，得另派一单（见交回单）"


def test_the_summary_still_prints_the_same_readings(mod, base_mod):
    import contextlib
    import io
    rows = mod.load_rows()
    out = {}
    for name, module in (("base", base_mod), ("now", mod)):
        table = module.build_table(module.load_rows(), {})
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            module.summary(module.load_rows(), table, {}, 0, 95,
                           module.budget_table(None), module.min_answer_tokens(), False)
        out[name] = buf.getvalue()
    assert out["now"].splitlines() == out["base"].splitlines(), \
        "--summary 有读数因这一改而漂"