


# -*- coding: utf-8 -*-
r"""R535 反证刀 —— 十三把，每一把先在影子端跑正控确认它真的会咬。

口径沿用 R459 / R464 / R520 / R524 那一套，不另立规矩：

- 🔴 **仓里一字节都不改**。摘刀一律在**内存影子**里做：把被跟踪那枚文件的源文在 import 那一刻
  抄进内存，按锚点改一格，写进 ``tmp_path`` 的影子副本，再 ``exec`` 回挂到模块上（``monkeypatch``
  负责 teardown 复原）。每把刀进刀前后各核一次被跟踪文件的 sha256，最后一枚用例总清点：十三把刀
  跑完，被跟踪件的指纹必须还是进门那一组。影子副本落进仓里 = 当场红。
- **victim 全部是在册那枚钉本身**：本单的邻件（``tests/test_r535_context_pairing_gate.py``）里的
  函数，加总控点名的三枚在册钉 —— ``test_r30_context_limit_guard.py:144``（撞顶不许报成
  ``model_unavailable``）、``:158``（码不许被降级）、``test_r255_refusal_says_the_parameters_are_small.py:162``
  （一发一行）。🔴 本件**不修改任何在册钉**：它们与被跟踪件同表列在 ``TRACKED`` 里逐枚 sha256，
  总清那一格负责证明「摘前摘后一字节没动」。
- **按值绑定的坑**（本班新踩，机械里已经治了）：``from app.agents.contracts import
  evaluate_context_pairing`` 在消费件里绑的是**函数对象**，影子 exec 回挂到源模块只改得到
  ``contracts.evaluate_context_pairing``，改不到 ``gate.evaluate_context_pairing``。所以凡是 victim
  走按值导入的那几把，``_cut`` 都多带一枚 ``consumers=``，把影子同时挂回消费件。不带这一格，
  那几把刀会咬不动——而咬不动的反证是空的，不是绿的。

## 刀的清单

| 刀 | 摘掉的那一格 | victim（在册钉） | 侧 |
|----|--------------|------------------|----|
| K1  | 闸里读运行时那一格（``runtime_window_tokens=None``） | 判据② 的闸本体格 | 运行侧 |
| K1b | 闸里读声明那一格（写死 4096，不再跟环境） | 「跟着 env 变」那一格 | 运行侧 |
| K2  | ``evaluate_context_pairing`` 的方向判据 ``runtime < declared`` 钝化成永真 | 反方向格 + 配套格 | 运行侧 |
| K3  | 预发拒发那一支的 ``raise`` 换成离线兜底（本单明令不许的形状） | r30:144 + r255:199 | 运行侧 |
| K4  | 归因行不再取配对话（``pairing = None``） | 归因带配对话那一格 | 运行侧 |
| K5  | ``invoke`` 服务端拒发处不再摘服务端的数 | 台账拒发→闸读数那一格 | 运行侧 |
| K6  | ``_make_model`` 里的启动把手整行摘掉 | 启动一行那一格 | 运行侧 |
| K7  | 启动把手的 ``except`` 从「只留一行告警」改成往上抛 | 自检炸了不许塌建图那一格 | 运行侧 |
| K8  | ``PAIRING_SLACK_RATIO`` 从 2 钝化成 1（「白留着」不再需要证据） | 不足两倍那一格 | 常数 |
| K9  | ``PAIRING_ACTIONABLE`` 把 ``runtime_unread`` 也算成可行动 | 缺席不许当绿灯那一格 | 常数 |
| K10 | 证据边界的码表里摘掉 ``context_limit_exceeded`` | r30:158 码不许被降级 | 常数 |
| K11 | ``authorize`` 的拒发行打成两行 | r255:162 一发一行 | 运行侧 |
| K12 | 归因行改用 ``[ModelBudget]`` 标记（把在册标记稀释掉） | r30:231 一发一行 | 运行侧 |

K10 / K11 动的是**本单写域外**的文件（``app/agents/evidence.py``、``app/common/model_budget.py``），
只在内存里动、盘上零写入（sha 台账当场自证）。之所以要动它们：总控点名的那两枚在册钉只读得到这两
条腿，在写域内没有能让它们变红的摘法。若总控认为写域外连内存摘刀都不许开，撤 K10 / K11 两把即可，
其余十把不受影响。
"""

import ast
import hashlib
import inspect
import sys
import textwrap
from pathlib import Path

import pytest

import test_r255_refusal_says_the_parameters_are_small as r255
import test_r30_context_limit_guard as r30
import test_r535_context_pairing_gate as gate
from app.agents import contracts, nodes
from app.agents import evidence
from app.common import model_budget, model_config

# 邻件的 autouse 夹具直接搬进来：本模块的用例跑的就是它那一套「两枚缓存都归零 + 环境干净」。
_one_pair_at_a_time = gate._one_pair_at_a_time

REPO = Path(__file__).resolve().parents[1]
MODEL_CONFIG_PATH = REPO / "app" / "common" / "model_config.py"
CONTRACTS_PATH = REPO / "app" / "agents" / "contracts.py"
NODES_PATH = REPO / "app" / "agents" / "nodes.py"
BUDGET_PATH = REPO / "app" / "common" / "model_budget.py"
EVIDENCE_PATH = REPO / "app" / "agents" / "evidence.py"
ENV_PATH = REPO / ".env.example"
GATE_PATH = REPO / "tests" / "test_r535_context_pairing_gate.py"
R30_PATH = REPO / "tests" / "test_r30_context_limit_guard.py"
R255_PATH = REPO / "tests" / "test_r255_refusal_says_the_parameters_are_small.py"
#: 进门先登指纹：三枚产品件 + 两枚不动的在册钉 + 邻件 + 台账件，一字节都不许被摘刀蹭到。
TRACKED = (
    MODEL_CONFIG_PATH,
    CONTRACTS_PATH,
    NODES_PATH,
    BUDGET_PATH,
    EVIDENCE_PATH,
    ENV_PATH,
    GATE_PATH,
    R30_PATH,
    R255_PATH,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


FINGERPRINT_AT_IMPORT = {path: _sha(path) for path in TRACKED}
#: 源文在 import 那一刻抄进内存；摘刀只作用在副本上，回头再读盘就拿不到「原样」了。
TEXT_AT_IMPORT = {path: path.read_text(encoding="utf-8").replace("\r\n", "\n") for path in TRACKED}

CUT_KNIVES = ("k1", "k1b", "k2", "k3", "k4", "k5", "k6", "k7", "k11", "k12")
ATTR_KNIVES = ("k8", "k9", "k10")

# ==================== 机械：影子摘刀 + 在册钉调用器 + 台账 ====================

_CUT_TAGS: set = set()
_ATTR_CUTS: set = set()
_RED_VICTIMS: set = set()


def _top_level_segment(text: str, name: str) -> str:
    """取源文里某枚**顶层**函数的整段源码（不含装饰器）。"""
    found = [
        ast.get_source_segment(text, node)
        for node in ast.parse(text).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(found) == 1, f"{name}: 顶层定义 {len(found)} 枚,本件的取段前提变了"
    return found[0] or ""


def _method_segment(text: str, class_name: str, name: str) -> str:
    """取某枚类方法的整段源码并 ``dedent``：R535 的 K3/K5 要摘的是 ``_ResilientModel.invoke``。"""
    classes = [n for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == class_name]
    assert len(classes) == 1, f"{class_name}: 类定义 {len(classes)} 枚"
    methods = [
        n for n in classes[0].body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    ]
    assert len(methods) == 1, f"{class_name}.{name}: 方法定义 {len(methods)} 枚"
    return textwrap.dedent(ast.get_source_segment(text, methods[0]) or "")


def _apply_edits(shadow: str, edits, original: str, tag: str, where: str) -> str:
    for needle, replacement in edits:
        hits = shadow.count(needle)
        assert hits == 1, f"{tag}: 锚点在 {where} 里命中 {hits} 次(要恰好 1 次)⇒ 这枚反证是空的"
        shadow = shadow.replace(needle, replacement, 1)
    if edits:
        assert shadow != original, f"{tag}: 改了个寂寞"
    assert "\r" not in shadow, f"{tag}: 影子里混进裸 CR"
    return shadow


def _shadow_file(tmp_path, tag: str, source: str) -> Path:
    target = tmp_path / f"r535_shadow_{tag}.py"
    assert REPO not in target.resolve().parents, f"{tag}: 影子副本落进仓里了,这一刀不许开"
    target.write_text(source, encoding="utf-8", newline="\n")
    return target


def _cut(module, name: str, edits, monkeypatch, tmp_path, tag: str, consumers=()):
    """按锚点摘一格，改出的源码写进 ``tmp_path`` 影子副本，再 exec 回挂到模块上。

    ``edits=()`` 就是**正控**：同一套机械不摘任何一刀，victim 必须先绿一遍。
    ``consumers`` 是被摘那枚名字的**按值导入方**（见头部那一节），影子同时挂回它们。
    """
    tracked = Path(inspect.getsourcefile(module)).resolve()
    assert tracked in FINGERPRINT_AT_IMPORT, f"{tracked.name}: 不在本件的指纹台账里"
    assert _sha(tracked) == FINGERPRINT_AT_IMPORT[tracked], f"{tag}: 进刀之前 {tracked.name} 就不是原样了"
    original_source = _top_level_segment(TEXT_AT_IMPORT[tracked], name)
    shadow_source = _apply_edits(original_source, edits, original_source, tag, f"{module.__name__}.{name}")
    _shadow_file(tmp_path, tag, shadow_source)

    original = getattr(module, name)
    monkeypatch.setattr(module, name, original)  # 先把原件记进 teardown,再 exec 覆盖同一个名字
    exec(compile(shadow_source, str(tracked), "exec"), module.__dict__)
    shadow = getattr(module, name)
    assert shadow is not original, f"{tag}: 影子与原件是同一枚对象"
    for consumer in consumers:
        assert hasattr(consumer, name), f"{tag}: 消费件 {consumer.__name__} 里没有 {name} 这枚绑定"
        monkeypatch.setattr(consumer, name, shadow)
    assert _sha(tracked) == FINGERPRINT_AT_IMPORT[tracked], f"{tag}: 摘刀在被跟踪文件上留下了写口"
    _CUT_TAGS.add(tag)
    return shadow


def _cut_method(cls, name: str, edits, monkeypatch, tmp_path, tag: str):
    """摘类方法：exec 出来的影子从模块命名空间里 ``pop`` 掉，只挂在类上，不留同名的顶层杂物。"""
    tracked = Path(inspect.getsourcefile(cls)).resolve()
    assert tracked in FINGERPRINT_AT_IMPORT, f"{tracked.name}: 不在本件的指纹台账里"
    assert _sha(tracked) == FINGERPRINT_AT_IMPORT[tracked], f"{tag}: 进刀之前 {tracked.name} 就不是原样了"
    original_source = _method_segment(TEXT_AT_IMPORT[tracked], cls.__name__, name)
    shadow_source = _apply_edits(original_source, edits, original_source, tag, f"{cls.__name__}.{name}")
    _shadow_file(tmp_path, tag, shadow_source)

    original = getattr(cls, name)
    monkeypatch.setattr(cls, name, original)
    host = sys.modules[cls.__module__].__dict__
    exec(compile(shadow_source, str(tracked), "exec"), host)
    shadow = host.pop(name, None)
    assert shadow is not None and shadow is not original, f"{tag}: 影子没挂上或摘下来还是原件"
    monkeypatch.setattr(cls, name, shadow)
    assert name not in host, f"{tag}: 影子在模块命名空间里留了个同名顶层函数"
    assert _sha(tracked) == FINGERPRINT_AT_IMPORT[tracked], f"{tag}: 摘刀在被跟踪文件上留下了写口"
    _CUT_TAGS.add(tag)
    return shadow


def _cut_attr(module, name: str, value, monkeypatch, tag: str):
    """常数刀：摘的是模块属性，正控与摘刀同一套机械（``edits`` 只有这一种形状时用它）。"""
    assert hasattr(module, name), f"{tag}: {module.__name__} 没有 {name}"
    monkeypatch.setattr(module, name, value)
    _ATTR_CUTS.add(tag)


def _bite(fn, *args) -> str:
    """跑在册那枚钉：红了交回 ``"类型: 红话"``，没红交回空串。

    🔴 接的是 ``BaseException`` 而不是 ``Exception``：K3 那种「摘掉 raise」的摘法，红在
    ``pytest.raises`` 那一格，抛的是 ``Failed: DID NOT RAISE``——``Failed``/``Skipped`` 继承的是
    ``BaseException``（``OutcomeException``），用 ``except Exception`` 接就会让一把真咬中的刀
    表现得像没咬中（本班实测：K3 摘刀后 r30 那枚钉确实红了，却被机械漏记成「一次都没被摘红」）。
    """
    try:
        fn(*args)
    except BaseException as error:  # noqa: BLE001  这里要的就是"任何形状的红"，含 pytest 的判决异常
        _RED_VICTIMS.add(fn.__name__)
        return f"{type(error).__name__}: {error}"
    return ""


@pytest.fixture(autouse=True)
def _clean_r255_window(monkeypatch):
    """在册钉被本件直接调用时，它们自己的 autouse 夹具不会跑——这里补上同一组环境变量清理。"""
    for name in (
        "MODEL_TIER_ANALYSIS_MAX_TOKENS",
        "MODEL_CONCURRENCY_WAIT_SECONDS",
        "MODEL_MAX_CONCURRENCY",
    ):
        monkeypatch.delenv(name, raising=False)


# ==================== 源文侧机械：只在内存副本上动，交给在册表达式去判 ====================


def _mutate_text(path: Path, edits, name: str | None = None) -> str:
    """返回改过的**内存副本**源文（盘上一字节不动）；``name`` 给定时锚点限定在那枚函数整段里数。"""
    text = TEXT_AT_IMPORT[path]
    scope = _top_level_segment(text, name) if name else text
    mutated = _apply_edits(scope, edits, scope, "mutate", name or path.name)
    return text.replace(scope, mutated, 1) if name else mutated


def _pairing_call_sites(text: str) -> int:
    """`_make_model` 里那句启动把手的命中数——与邻件那枚 AST 格用的是同一枚表达式。"""
    tree = ast.parse(text)
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_log_context_pairing"
    )


# ==================== K1 / K1b：摘闸的两枚读数格，victim 必须是判据② 本身 ====================


def test_k1_positive_control_the_gate_reads_both_halves(monkeypatch, tmp_path):
    """正控：同一套机械不摘刀（``edits=()``），判据② 那枚闸格必须先绿——否则"红"是它本来就在红。"""
    _cut(model_config, "check_context_pairing", (), monkeypatch, tmp_path, "k1_control")
    gate.test_the_gate_reads_both_halves_and_judges_the_direction(monkeypatch)


def test_k1_dropping_the_runtime_reading_goes_red_on_the_gate_itself(monkeypatch, tmp_path):
    """**刀 K1**：闸里读运行时那一格换成 ``None`` ⇒ 判据② 那枚格当场红，不许静默通过。

    这一把就是「两条读数链只在纸上并列、代码里其实只读了一枚」那种交付的形状：摘掉之后
    判决会退回 ``runtime_unread``，红话由邻件那枚格自己报。
    """
    _cut(
        model_config,
        "check_context_pairing",
        [('        runtime_window_tokens=state.get("tokens"),\n', "        runtime_window_tokens=None,\n")],
        monkeypatch,
        tmp_path,
        "k1",
    )
    red = _bite(gate.test_the_gate_reads_both_halves_and_judges_the_direction, monkeypatch)
    assert "runtime_unread" in red, red


def test_k1b_positive_control_the_claimed_half_follows_the_environment(monkeypatch, tmp_path):
    """正控：不摘刀时，「声明那一半跟着 env 走」那枚格是绿的。"""
    _cut(model_config, "check_context_pairing", (), monkeypatch, tmp_path, "k1b_control")
    gate.test_the_claimed_half_follows_the_environment_and_the_one_reading_home(monkeypatch)


def test_k1b_hardcoding_the_declared_half_goes_red(monkeypatch, tmp_path):
    """**刀 K1b**：把 ``plan.context_limit_tokens`` 写死成 4096 ⇒ 同一枚格红在「跟着 env 变」那一格。

    这一格是缺省值边界的另一面：本单一枚缺省都不改，但闸必须**引用**当下那枚读数，
    引用被剪断时它得当场响，而不是永远交出 4096 这种看着最舒服的假绿。
    """
    _cut(
        model_config,
        "check_context_pairing",
        [("        declared_window_tokens=plan.context_limit_tokens,\n", "        declared_window_tokens=4096,\n")],
        monkeypatch,
        tmp_path,
        "k1b",
    )
    red = _bite(gate.test_the_claimed_half_follows_the_environment_and_the_one_reading_home, monkeypatch)
    assert "16384" in red, red


# ==================== K2：方向判据钝化——两个方向都得有牙 ====================


def test_k2_positive_control_both_directions_judge_apart(monkeypatch, tmp_path):
    """正控：反方向与同宽两枚格在影子机械下都还是绿的。"""
    _cut(contracts, "evaluate_context_pairing", (), monkeypatch, tmp_path, "k2_control", consumers=(gate,))
    gate.test_the_reverse_direction_names_idle_capacity()
    gate.test_equal_windows_are_paired_and_say_nothing_further()


def test_k2_blunting_the_direction_test_prints_a_false_mismatch(monkeypatch, tmp_path):
    """**刀 K2**：``runtime < declared`` 写成永真 ⇒ 反方向那格与「配套」那格一起红。

    摘的是方向判据本身：运行时比声明宽也被判成「不配套」，「白留着容量」那一格就此消失，
    同宽那一格也被谎报成不配套。两枚 victim 都是邻件里在册的格，本件不重抄相似物。
    """
    _cut(
        contracts,
        "evaluate_context_pairing",
        [("    if runtime < declared:\n", "    if True:  # 反证 K2:方向判据钝化\n")],
        monkeypatch,
        tmp_path,
        "k2",
        consumers=(gate,),
    )
    reversed_red = _bite(gate.test_the_reverse_direction_names_idle_capacity)
    equal_red = _bite(gate.test_equal_windows_are_paired_and_say_nothing_further)
    assert "env_above_runtime" in reversed_red, reversed_red
    assert "env_above_runtime" in equal_red, equal_red


# ==================== K3：把预发拒发接进兜底文案——本单明令不许的那一枚形状 ====================


def test_k3_positive_control_the_two_registered_pins_stay_green(monkeypatch, tmp_path):
    """正控：原样 exec 一遍 ``invoke``，r30:144 与 r255:199 两枚在册钉都还是绿的。"""
    _cut_method(nodes._ResilientModel, "invoke", (), monkeypatch, tmp_path, "k3_control")
    r30.test_the_collision_is_not_reported_as_model_unavailable()
    r255.test_the_real_size_is_still_refused_before_it_is_sent_and_offline_is_still_not_used()


def test_k3_laundering_the_refusal_through_the_offline_reply_goes_red(monkeypatch, tmp_path):
    """**刀 K3**：撞顶那一支的 ``raise`` 换成离线兜底 ⇒ 两枚在册钉本身当场红。

    这一把对着的是本单的形界：``context_limit_exceeded`` 不许接进兜底文案。摘完之后
    ``pytest.raises`` 收不到异常、证据袋里多出 ``model_unavailable``，红话由那两枚钉自己报——
    本件一个字都没改它们（末了总清点按 sha256 自证）。
    """
    _cut_method(
        nodes._ResilientModel,
        "invoke",
        [
            (
                '            slot.release()\n            span.finish("failed", error_code=exc.code)\n            raise\n',
                '            slot.release()\n            span.finish("failed", error_code=exc.code)\n'
                "            return self._offline_fallback(messages, config=config, **kwargs)\n",
            )
        ],
        monkeypatch,
        tmp_path,
        "k3",
    )
    r30_red = _bite(r30.test_the_collision_is_not_reported_as_model_unavailable)
    r255_red = _bite(r255.test_the_real_size_is_still_refused_before_it_is_sent_and_offline_is_still_not_used)
    assert "DID NOT RAISE" in r30_red, r30_red
    assert "DID NOT RAISE" in r255_red, r255_red


# ==================== K4 / K5：归因行不再取配对话、服务端那枚数不再被摘 ====================


def test_k4_positive_control_the_pairing_rides_the_refusal_line(monkeypatch, caplog, tmp_path):
    """正控：不摘刀时，撞顶那一行的配对话确实跟得上来。"""
    _cut(nodes, "_log_context_refusal", (), monkeypatch, tmp_path, "k4_control")
    gate.test_the_refusal_line_carries_the_pairing_once_the_gate_has_a_reading(caplog, monkeypatch)


def test_k4_losing_the_pairing_on_the_refusal_line_goes_red(monkeypatch, caplog, tmp_path):
    """**刀 K4**：归因行不再问闸（``pairing = None``）⇒ 邻件那枚「带配对话」的格红。

    两枚读数在手却不说出来，等于本单判据③ 那一格没交：拒发句重新变成三枚孤立数字。
    """
    _cut(
        nodes,
        "_log_context_refusal",
        [("        pairing = check_context_pairing(budget=budget)\n", "        pairing = None  # 反证 K4\n")],
        monkeypatch,
        tmp_path,
        "k4",
    )
    red = _bite(gate.test_the_refusal_line_carries_the_pairing_once_the_gate_has_a_reading, caplog, monkeypatch)
    assert "配套自检" in red, red


def test_k5_positive_control_the_servers_number_is_harvested(monkeypatch, tmp_path):
    """正控：原样 exec ``invoke``，服务端拒发→台账读数那一枚格是绿的。"""
    _cut_method(nodes._ResilientModel, "invoke", (), monkeypatch, tmp_path, "k5_control")
    gate.test_a_provider_refusal_teaches_the_gate_the_servers_window()


def test_k5_dropping_the_harvest_blinds_the_second_channel(monkeypatch, tmp_path):
    """**刀 K5**：摘掉 ``_harvest_runtime_window(exc)`` ⇒ 第二条通道就此失联，邻件那枚格红。

    这一把证明「运行时那一半」不是只有一条路：撞顶那一发本来就带回了服务端的数，
    不摘它等于把免费到手的一半读数白白丢掉。
    """
    _cut_method(
        nodes._ResilientModel,
        "invoke",
        [("                    _harvest_runtime_window(exc)\n", "")],
        monkeypatch,
        tmp_path,
        "k5",
    )
    red = _bite(gate.test_a_provider_refusal_teaches_the_gate_the_servers_window)
    assert "None" in red, red


# ==================== K6 / K7：启动把手整行摘掉、自检异常放回建图 ====================


def test_k6_positive_control_the_announcement_is_wired_and_said_once(monkeypatch, caplog, tmp_path):
    """正控：源文侧谓词与运行时格同判——把手此刻真接在 ``_make_model`` 上，且只说一句。"""
    text = TEXT_AT_IMPORT[NODES_PATH]
    assert _pairing_call_sites(text) == 1, _pairing_call_sites(text)
    _cut(nodes, "_make_model", (), monkeypatch, tmp_path, "k6_control")
    gate.test_the_startup_handle_announces_the_pairing_once_per_verdict(monkeypatch, caplog)


def test_k6_unhooking_the_startup_announcement_goes_red_both_ways(monkeypatch, caplog, tmp_path):
    """**刀 K6**：摘掉 ``_make_model`` 里那一行把手 ⇒ 源文侧谓词归零，运行时那一格也红。

    两面都摘：只看源文会把「接了但从不说话」算成过，只看运行时会漏掉「说话的地方接错了」。
    """
    mutated = _mutate_text(NODES_PATH, [("        _log_context_pairing(settings.base_url, budget)\n", "")], name="_make_model")
    assert _pairing_call_sites(mutated) == 0, "把手摘掉了源文侧却还说接得上:这枚谓词是死牙"
    assert _pairing_call_sites(TEXT_AT_IMPORT[NODES_PATH]) == 1, "原样必须是 1 枚,不然 K6 摘错了格子"

    _cut(nodes, "_make_model", [("        _log_context_pairing(settings.base_url, budget)\n", "")], monkeypatch, tmp_path, "k6")
    red = _bite(gate.test_the_startup_handle_announces_the_pairing_once_per_verdict, monkeypatch, caplog)
    assert "[]" in red, red


def test_k7_positive_control_a_broken_probe_leaves_the_graph_up(monkeypatch, caplog, tmp_path):
    """正控：不摘刀时，探针炸了也只剩一行告警、图照旧建出来。"""
    _cut(nodes, "_log_context_pairing", (), monkeypatch, tmp_path, "k7_control")
    gate.test_a_broken_probe_never_takes_the_graph_down(monkeypatch, caplog)


def test_k7_letting_the_self_check_escape_goes_red_on_the_graph_itself(monkeypatch, caplog, tmp_path):
    """**刀 K7**：自检的 ``except`` 从「只留一行告警」改成往上抛 ⇒ 那一枚格红在建图结果上。

    摘完之后 `_make_model` 的外层 except 会把整台服务接进离线件：一次读不到模型服务端
    就起不来，正是本单反复强调的「自检不该成为第二个 bug」。
    """
    _cut(
        nodes,
        "_log_context_pairing",
        [
            (
                '        logger.warning(f"{CONTEXT_PAIRING_MARKER} 配套自检未运行: {type(exc).__name__}")\n        return\n',
                '        raise RuntimeError("反证 K7：自检炸了就让它炸到建图外面") from exc\n',
            )
        ],
        monkeypatch,
        tmp_path,
        "k7",
    )
    red = _bite(gate.test_a_broken_probe_never_takes_the_graph_down, monkeypatch, caplog)
    assert "_OfflineModel" in red or "AssertionError" in red, red


# ==================== K8 / K9：两枚判读常数钝化——「白留着」与「缺席」都得有证据 ====================


def test_k8_positive_control_the_slack_ruler_is_evidence_based():
    """正控：2 倍那一格现在是绿的——「白留着」只在服务端宽出一倍以上时才说出口。"""
    gate.test_a_narrower_gap_is_the_same_direction_without_the_idle_claim()


def test_k8_dulling_the_slack_ratio_invents_idle_capacity(monkeypatch):
    """**刀 K8**：``PAIRING_SLACK_RATIO`` 从 2 钝化成 1 ⇒ 不足两倍那一格红。

    这一把对着的是「不许把没证明过的目标当结论」：钝化之后 6144 对 4096 也会被叫成白留着。
    """
    _cut_attr(contracts, "PAIRING_SLACK_RATIO", 1, monkeypatch, "k8")
    red = _bite(gate.test_a_narrower_gap_is_the_same_direction_without_the_idle_claim)
    assert "白留着容量" in red, red


def test_k9_positive_control_absence_is_not_actionable():
    """正控：读不到运行时那一侧时，`actionable` 现在是假的（缺席不判可行动）。"""
    gate.test_an_unobserved_server_is_never_printed_as_paired(None)


def test_k9_making_absence_actionable_goes_red_on_the_unread_nail(monkeypatch):
    """**刀 K9**：把 ``runtime_unread`` 也算进「可行动」集合 ⇒ 缺席不许当绿灯那一枚格红。

    反向那半由邻件自己钉（``actionable is False`` 与「配套：」不出现），这一把只证一头有牙；
    它同时说明四枚判读词与 ``PAIRING_ACTIONABLE`` 之间的关系是真在代码里生效的，不是纸面分类。
    """
    _cut_attr(
        contracts,
        "PAIRING_ACTIONABLE",
        frozenset({
            contracts.PAIRING_ENV_ABOVE_RUNTIME,
            contracts.PAIRING_RUNTIME_ABOVE_ENV,
            contracts.PAIRING_RUNTIME_UNREAD,
        }),
        monkeypatch,
        "k9",
    )
    red = _bite(gate.test_an_unobserved_server_is_never_printed_as_paired, None)
    assert "actionable" in red, red


# ==================== K10 / K11 / K12：三枚在册钉本身（码不许降级·一发一行） ====================


def test_k10_positive_control_the_code_reaches_the_client_undegraded():
    """正控：在册钉 r30:158 此刻是绿的——本件的归因没给它添堵。"""
    r30.test_the_code_reaches_the_client_without_being_downgraded()


def test_k10_losing_the_code_at_the_evidence_boundary_goes_red(monkeypatch):
    """**刀 K10**：证据边界的码表里摘掉 ``context_limit_exceeded`` ⇒ r30:158 当场红。

    这一把证明「码不许被降级」不是形容词：那枚钉读的是 ``evidence`` 的降级腿。摘的格子在
    本单写域外（``app/agents/evidence.py``），只在内存里动，盘上一字节没改（sha 台账自证）。
    """
    _cut_attr(
        evidence,
        "_ERROR_CODES",
        frozenset(set(evidence._ERROR_CODES) - {contracts.CONTEXT_LIMIT_CODE}),
        monkeypatch,
        "k10",
    )
    red = _bite(r30.test_the_code_reaches_the_client_without_being_downgraded)
    assert "internal_error" in red, red


def test_k11_positive_control_the_refusal_line_is_still_one_line(monkeypatch, caplog, tmp_path):
    """正控：原样 exec 一遍 ``authorize``，r255:162 那枚「一发一行」的在册钉是绿的。"""
    _cut(model_budget, "authorize", (), monkeypatch, tmp_path, "k11_control", consumers=(r255,))
    r255.test_the_refusal_line_stays_one_line_and_gains_the_distance(caplog)


def test_k11_multiplying_the_marker_line_goes_red(monkeypatch, caplog, tmp_path):
    """**刀 K11**：``authorize`` 的拒发行打成两行 ⇒ r255:162 当场红。

    这一把是给本单的归因行配的牙的另一半：``[ModelBudget]`` 一旦多发，那枚在册钉就响。
    摘的格子同样在写域外（``app/common/model_budget.py``），内存动、盘上不动。
    """
    _cut(
        model_budget,
        "authorize",
        [
            (
                "        report_budget(budget, prompt_tokens, stream=stream)\n",
                "        report_budget(budget, prompt_tokens, stream=stream)\n"
                "        report_budget(budget, prompt_tokens, stream=stream)\n",
            )
        ],
        monkeypatch,
        tmp_path,
        "k11",
        consumers=(r255,),
    )
    red = _bite(r255.test_the_refusal_line_stays_one_line_and_gains_the_distance, caplog)
    assert "len(lines)" in red or "2" in red, red


def test_k12_positive_control_the_attribution_uses_its_own_marker(monkeypatch, caplog, tmp_path):
    """正控：不摘刀时，归因行走的是 ``[ContextPairing]``，r30:231 那一枚「一发一行」仍旧绿。"""
    _cut(nodes, "_log_context_refusal", (), monkeypatch, tmp_path, "k12_control")
    r30.test_the_budget_verdict_is_findable_by_one_grep(caplog)


def test_k12_diluting_the_registered_marker_with_a_second_line_goes_red(monkeypatch, caplog, tmp_path):
    """**刀 K12**：把归因行的标记换成 ``[ModelBudget]`` ⇒ r30:231 当场红。

    这一把落在本单写域内，对着的是派工词点名的形界：归因行**不许**并进在册那枚标记。
    摘完之后一发拒发出现两行 ``[ModelBudget]``，「一次 grep 一个结论」的性质就此作废。
    """
    _cut(
        nodes,
        "_log_context_refusal",
        [('        logger.warning(f"{CONTEXT_PAIRING_MARKER} {attribution}")', '        logger.warning(f"[ModelBudget] {attribution}")')],
        monkeypatch,
        tmp_path,
        "k12",
    )
    red = _bite(r30.test_the_budget_verdict_is_findable_by_one_grep, caplog)
    assert "2" in red, red


# ==================== 总清点：刀都真摘过、牙都真咬过、仓里一字节没动 ====================


#: 每把刀必须咬红的那枚在册钉（按钉名点名,不数总数——数总数会把死牙算成活的）。
EXPECTED_RED_VICTIMS = {
    "test_the_gate_reads_both_halves_and_judges_the_direction",  # K1
    "test_the_claimed_half_follows_the_environment_and_the_one_reading_home",  # K1b
    "test_the_reverse_direction_names_idle_capacity",  # K2
    "test_equal_windows_are_paired_and_say_nothing_further",  # K2
    "test_the_collision_is_not_reported_as_model_unavailable",  # K3  🔴 在册钉本身
    "test_the_real_size_is_still_refused_before_it_is_sent_and_offline_is_still_not_used",  # K3  🔴 在册钉本身
    "test_the_refusal_line_carries_the_pairing_once_the_gate_has_a_reading",  # K4
    "test_a_provider_refusal_teaches_the_gate_the_servers_window",  # K5
    "test_the_startup_handle_announces_the_pairing_once_per_verdict",  # K6
    "test_a_broken_probe_never_takes_the_graph_down",  # K7
    "test_a_narrower_gap_is_the_same_direction_without_the_idle_claim",  # K8
    "test_an_unobserved_server_is_never_printed_as_paired",  # K9
    "test_the_code_reaches_the_client_without_being_downgraded",  # K10  🔴 在册钉本身
    "test_the_refusal_line_stays_one_line_and_gains_the_distance",  # K11  🔴 在册钉本身
    "test_the_budget_verdict_is_findable_by_one_grep",  # K12
}


def test_z13_the_ledger_names_every_knife_and_every_tooth_bit():
    """台账查账：十把影子刀全真摘过、三把常数刀全真钝过，点名的钉全被咬红,且不止三枚。"""
    assert _CUT_TAGS >= set(CUT_KNIVES), sorted(set(CUT_KNIVES) - _CUT_TAGS)
    assert _ATTR_CUTS >= set(ATTR_KNIVES), sorted(set(ATTR_KNIVES) - _ATTR_CUTS)
    missing = EXPECTED_RED_VICTIMS - _RED_VICTIMS
    assert not missing, f"这些在册钉一次都没被摘红:{sorted(missing)}"
    assert len(_RED_VICTIMS) >= 3, sorted(_RED_VICTIMS)
    assert EXPECTED_RED_VICTIMS <= _RED_VICTIMS, sorted(EXPECTED_RED_VICTIMS - _RED_VICTIMS)


def test_z13b_the_tracked_files_are_the_ones_we_opened_the_door_with():
    """十三把刀跑完，被跟踪件的指纹必须还是进门那一刻那一组；仓里也不许留影子件。"""
    for path, digest in FINGERPRINT_AT_IMPORT.items():
        assert _sha(path) == digest, path
    strays = list(REPO.glob("r535_shadow_*.py")) + list((REPO / "tests").glob("r535_shadow_*.py"))
    strays += list((REPO / "app").rglob("r535_shadow_*.py"))
    assert not strays, strays
