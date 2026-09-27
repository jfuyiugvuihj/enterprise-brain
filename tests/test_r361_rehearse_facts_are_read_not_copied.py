# -*- coding: utf-8 -*-
r"""R361 · 预演器的事实必须"从现场读"，而且本件要能证明它真读了现场。

``scripts/rehearse_eval_window.py`` 是真机跑分窗口（run6）的开窗判据来源。它过去把这棵树
里的 30 处 ``app/**:行号`` 连同**值本身**一起抄进了常数：orchestrator 或 nodes 一改，它会
拿着旧事实继续算，并打出一份看起来正常的读数——它红不起来，因为它从没读过现场。
本件是那台预演器的常驻看守（判据 甲/丙/丁/己 里能钉成静态事实的那几格）：

  ① 裸行号归零：全文件（含注释与 docstring）不许再出现 ``xxx.py:123`` 这种形状。
     写注释行号不算处置，把数字改成"今天的值"也不算处置（R346 明令禁止的交差法）。
  ② 登记表自洽：每一格读数都有出处锚点；锚点自己不许带行号；抄本侧只有登记过的那五格。
  ③ 🔴 判定与分支必须**来自现场源码**：那三枚可调用对象的 ``co_filename`` 就是证据——
     它们来自 <rehearsal:app/...>，不来自本件。谁把它们换回本文件里手写的 if/elif，
     这一格当场红。（这一枚是"派生"的反面取证：不看它算得对不对，看它是不是从现场搬来的。）
  ④ 抄本与现场今天等值（copy_drift 空表）；镜像分支在 105 题上与现场切片逐题同形。
  ⑤ 只读方向不许反：本件不许把 orchestrator / chat 拉进 sys.modules（那两棵 import 期
     就连模型与数据库），也不许在脚本里 import 它们。
  ⑥ 判据己（对外读数格式）另由 tests/test_r361_output_format_is_frozen.py 钉。

反证（"这把尺子有没有牙"）落在 tests/test_r361_ruler_proves_itself_on_a_shadow_copy.py。
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT_REL = "scripts/rehearse_eval_window.py"
SCRIPT = REPO / SCRIPT_REL

#: 出处锚点允许的形状：path::symbol 或一句人话。带行号就不算锚点，算抄。
BARE_LINE_REF = re.compile(r"[\w./\-]+\.py:\d+")
ANCHOR_WITH_LINE = re.compile(r":\d+")

def load_script(module_name: str, path: Path):
    """按源码文本现编译加载本件。🔴 不许换回 ``spec.loader.exec_module``。

    实测理由（本仓踩过）：反证刀会就地改写 ``scripts/rehearse_eval_window.py`` 再按字节还原，
    Windows 的 mtime 只到秒、刀版本与原文件大小常常同尺寸，``scripts/__pycache__`` 里那枚过期
    ``.pyc`` 就能通过校验——于是钉读到的是刀版本的代码，现场文件却是干净的（跑过一次"文件干净却红"
    的假红；反向也能把刀吃成假绿）。``compile()`` 只吃当下这份文本，既不写也不读 .pyc。
    """
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    exec(compile(path.read_text(encoding="utf-8-sig"), str(path), "exec"), module.__dict__)
    return module


@pytest.fixture(scope="module")
def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8-sig")


@pytest.fixture(scope="module")
def mod():
    return load_script("r361_target", SCRIPT)


SIBLING_PINS = (
    "tests/test_r361_rehearse_facts_are_read_not_copied.py",
    "tests/test_r361_ruler_proves_itself_on_a_shadow_copy.py",
    "tests/test_r361_output_format_is_frozen.py",
)

# ==================== ⓪ 加载方式本身也要钉 ====================


@pytest.mark.parametrize("rel", SIBLING_PINS)
def test_the_pins_load_the_script_from_source_text_not_bytecode_cache(rel):
    """钉不许读 ``__pycache__``：反证刀就地改写再还原本件时，秒级 mtime + 同尺寸能让过期
    pyc 通过校验，钉就吃到刀版本（实测过一次"文件干净却红"的假红，反向则是假绿）。

    所以三份钉件只准 ``compile(text)`` 现编译，谁换回 ``exec_module`` 谁当场红。
    """
    tree = ast.parse((REPO / rel).read_text(encoding="utf-8-sig"))
    cached = [node.lineno for node in ast.walk(tree)
              if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute)
              and node.func.attr == "exec_module"]
    assert not cached, f"{rel} 又用回 importlib 的字节码缓存加载本件（行 {cached}）"
    compiled = [node.lineno for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id == "compile"]
    assert compiled, f"{rel} 没有现编译源码文本，靠什么保证读到的是现场？"


# ==================== ① 裸行号归零 ====================


def test_no_bare_line_number_reference_survives_in_the_script(script_text):
    """全文件零枚 ``xxx.py:行号``。留一枚就是给下一个人留一张会过期的谎话。"""
    offenders = []
    for number, line in enumerate(script_text.replace("\r\n", "\n").split("\n"), start=1):
        for hit in BARE_LINE_REF.finditer(line):
            offenders.append(f"{SCRIPT_REL}:{number}: {hit.group(0)}")
    assert not offenders, "预演器里又长出裸行号：\n" + "\n".join(offenders)


def test_fact_anchors_carry_no_line_numbers(mod):
    offenders = {name: anchor for name, anchor in mod.FACT_ANCHORS.items()
                 if BARE_LINE_REF.search(anchor) or ANCHOR_WITH_LINE.search(anchor)}
    assert not offenders, f"出处锚点里混进行号（那等于把抄本换了个地方放）：{offenders}"


# ==================== ② 登记表自洽 ====================


def test_every_read_cell_has_an_anchor_and_every_anchor_is_a_real_symbol(mod):
    assert set(mod.FACT_READERS) <= set(mod.FACT_ANCHORS), (
        "读数有格没有出处：" + str(sorted(set(mod.FACT_READERS) - set(mod.FACT_ANCHORS))))
    for name, anchor in mod.FACT_ANCHORS.items():
        assert "::" in anchor or "：" not in anchor, f"{name} 的锚点读不出符号：{anchor}"


def test_copy_side_is_exactly_the_registered_copies(mod):
    """抄本只准有登记过的那几格；多一枚就是又开了一口手抄的井。"""
    assert set(mod.COPIES) == set(mod.COPY_CELLS), (
        f"抄本侧不等：{sorted(set(mod.COPIES) ^ set(mod.COPY_CELLS))}")


def test_assembled_constants_are_the_live_readings_not_a_second_copy(mod):
    """装配段的每一枚公开常数都必须等于现场读数（等值来自比对，不来自重新打字）。"""
    for name, value in mod.FACTS.items():
        if hasattr(mod, name) and name in mod.FACT_READERS:
            assert getattr(mod, name) == value, f"{name} 被重新打了一遍字，没走读数"
    assert mod.DOC_REFERENCE.pattern == mod.FACTS["DOC_REFERENCE_PATTERN"]
    assert mod.REWRITE_TRIGGERS == mod.FACTS["REWRITE_PREFIXES"]


# ==================== ③ 判定/分支必须来自现场源码 ====================


def test_the_follow_up_predicate_was_carried_in_from_chat_source(mod):
    """"这句算不算追问"必须是 chat.py 那两枚函数本身，不是本件里重新写的一套。"""
    filename = mod.LIVE_REWRITE_RULE.__code__.co_filename
    assert filename == "<rehearsal:app/api/v1/chat.py>", (
        f"追问判定不再从现场搬来：{filename}")
    assert "_is_followup" in mod.LIVE_REWRITE_RULE.__qualname__


def test_the_document_reference_strip_is_carried_in_from_orchestrator(mod):
    """"先把文档引用剥掉再匹配关键词"这一步也必须是现场那枚 ``_intent_text`` 本身。"""
    filename = mod.LIVE_INTENT_TEXT.__code__.co_filename
    assert filename == "<rehearsal:app/agents/orchestrator.py::_intent_text>", (
        f"剥离文档引用的规则不再从现场搬来：{filename}")
    assert mod.LIVE_INTENT_TEXT("住宿证.pdf 标准").strip() == "标准"
    assert mod.LIVE_INTENT_TEXT.__code__.co_names, "现场那枚函数不再引用任何名字"


def test_the_strip_step_only_delegates_to_the_live_function(mod):
    """形状钉：本件那一步只准"转交现场函数"，不许在旁边再写一遍同样的 sub。

    反证 K9：把 ``_intent`` 换回 ``DOC_REFERENCE.sub(" ", question or "")`` —— 模式串仍是派生的，
    今天算出来一模一样，所以值账抓不到它；抓它的是这枚形状钉：转交只允许引用 ``LIVE_INTENT_TEXT``
    这一个名字，多写一份规则就当场红。
    """
    names = mod._intent.__code__.co_names
    assert names == ("LIVE_INTENT_TEXT",), f"剥离文档引用这一步不再只是转交：{names}"
    assert "DOC_REFERENCE.sub" not in SCRIPT.read_text(encoding="utf-8-sig"), "本件里又长出一份 sub() 抄本"


def test_the_route_branch_mirrors_are_carried_in_from_orchestrator(mod):
    kw_live, plan_live = mod.read_route_branch_slices()
    for fn in (kw_live, plan_live):
        assert fn.__code__.co_filename == "<rehearsal:app/agents/orchestrator.py::route_main>", (
            f"route_main 的分支不是从现场切的：{fn.__code__.co_filename}")


def test_the_script_does_not_reimplement_the_follow_up_scan(mod):
    """本件里不许再留"逐枚前缀 startswith"那一手——它是被现场换掉的旧口径。"""
    text = SCRIPT.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    assert "startswith(t) for t in REWRITE_TRIGGERS" not in text
    assert "startswith(prefix)" not in text


# ==================== ④ 今天等值、今天同形 ====================


def test_copies_equal_the_source_today(mod):
    assert mod.copy_drift() == [], "抄本已经和现场不等（判据丁）：\n" + "\n".join(mod.copy_drift())


def test_mirror_branches_agree_with_the_live_slice_on_every_row(mod):
    rows = mod.load_rows()
    assert len(rows) == 105, len(rows)
    assert mod.branch_equivalence(rows) == [], (
        "本件的镜像分支与 route_main 现场切片在题面上不同形：\n"
        + "\n".join(mod.branch_equivalence(rows)))


def test_guard_gate_is_green_today(mod):
    assert mod.guard_facts(mod.load_rows()) == []


def test_readers_survive_a_second_root(mod):
    """读现场这件事只对读有副作用：换一枚 root 再读一遍，必须读出同一批数。"""
    assert mod.live_facts(REPO) == mod.live_facts()


def test_a_drifted_ruler_refuses_to_print_readings(monkeypatch, capsys):
    """判据 丁 的下半场：量不过尺子就**不出读数**，不许"警告一句继续算"。

    这里不改任何被跟踪文件：只把本件进程里那枚 ``copy_drift`` 换成"报一格漂移"，
    看 ``main()`` 是不是真的停在那儿。红了就说明这扇门接在开机路径上，不是装饰。
    """
    gate = load_script("r361_gate_target", SCRIPT)
    monkeypatch.setattr(gate, "copy_drift",
                        lambda root=None: ["CACHE_KEY_PROSE 抄本与现场不等：从 x 变到 y"])
    code = gate.main(["--summary"])
    printed = capsys.readouterr()
    assert code == 2, f"带病出了读数（退出码 {code}）：判据 丁 要的是停下来"
    assert "预演汇总" not in printed.out, "报了漂移还照样打印摘要"
    assert "CACHE_KEY_PROSE" in printed.err and "变到" in printed.err, printed.err


# ==================== ⑤ 只读方向 ====================


def _imported_modules(script_text):
    """把脚本里真会执行的 import 语句数出来（AST，不是子串）。"""
    names = set()
    for node in ast.walk(ast.parse(script_text)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_the_script_never_imports_the_two_heavy_modules(script_text):
    """方向钉（判据 乙/丙）：那两棵 import 期就连模型与数据库，本件只准 AST/exec 读它们。

    🔴 只数 AST 里的真 import 语句，不做子串匹配：判据 丙 要求把"为什么走 AST"的实测表写进
    件里，那张表本来就得把这几种写法念出来——按子串查会把证词当罪证，红得没有意义。
    """
    loaded = _imported_modules(script_text)
    heavy = ("app.agents.orchestrator", "app.api.v1.chat", "app.agents.tools", "app.main")
    offenders = sorted(name for name in loaded
                       if name in heavy or any(name.startswith(h + ".") for h in heavy))
    assert not offenders, f"本件又去 import 现场重件了：{offenders}"
    # 现场源码是"切片搬进干净 ns 跑"，不是动态 import：出现按名字加载就查不到方向了
    assert "import_module" not in script_text, "动态 import 能绕过上面那枚 AST 钉，本件不许用"


def test_loading_the_script_pulls_neither_heavy_module_into_the_process():
    """同一件事的运行期那一半：现场搬进进程就红，不看措辞只看 sys.modules 增量。"""
    before = set(sys.modules)
    module = load_script("r361_fresh_target", SCRIPT)
    pulled = {"app.agents.orchestrator", "app.api.v1.chat"} & (set(sys.modules) - before)
    assert not pulled, f"加载预演件把重件拉进了进程：{sorted(pulled)}"


def test_importing_the_script_leaves_egress_stubs_alone(mod):
    """R218 那条装载条件不许被本单改掉：pytest 里 import 预演件不留桩。"""
    import socket

    state = mod.egress_guard_state()
    assert state["conftest_gate_loaded"] is True, state
    assert state["guarded"] is False and state["stubbed"] is False, state
    for name in ("create_connection", "getaddrinfo"):
        assert getattr(socket, name).__name__ != "_boom", name
