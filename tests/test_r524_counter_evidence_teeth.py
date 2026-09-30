# -*- coding: utf-8 -*-
"""R524 判据⑦ —— 反证刀：九把，每一把先在影子端跑正控确认它真的会咬。

## 口径（沿用 R459 / R464 / R520 那一套，不另立规矩）

- 🔴 **仓里一字节都不改**。摘刀一律在**内存影子**里做：把被跟踪那枚文件的源文在 import 那一刻
  抄进内存，按锚点改一格，写进 ``tmp_path`` 的影子副本，再 ``exec`` 回挂到模块上（``monkeypatch``
  负责 teardown 复原）。每把刀进刀前后各核一次被跟踪文件的 sha256，最后一枚用例总清点：九把刀
  跑完，四份文件的指纹必须还是进门那四枚。影子副本落进仓里 = 当场红（``_cut`` 自己断言）。
- 影子的 ``__globals__`` 用的是模块**活的那本 dict**，不是 ``dict(vars(module))`` 的副本：
  victim 钉在跑的过程里还要 ``monkeypatch`` 模块属性（``orchestrator._cancellable_stream``、
  ``nodes.logger``），副本 globals 会让影子看不见那些补丁 ⇒ 正控与摘刀量的就不是同一条链。
- **每把刀都带正控**：同一套机械不摘刀（``edits=()``）先跑一遍，在册那枚钉必须是绿的。
  没有正控的反证不算牙——派工词判据 7 点的就是"上一班那枚永不匹配的死牙"这一格。
- **victim 全部是在册那枚钉本身**（``tests/test_r524_sink_reaches_both_runways.py`` 与
  ``tests/test_r524_queue_lane_sends_no_second_character.py`` 里的函数），本件不重抄一份相似物。
  红话由那枚钉自己报，本件只点名它红在哪一格。

## 刀的清单

| 刀 | 摘掉的那一格 | victim（在册钉） | 侧 |
|----|--------------|------------------|----|
| K1  | ``orchestrator.run_interrupt_stream`` 写 ``configurable`` 的注册语句 | 判据① 运行侧 + 文本谓词 | 派工词点名的"摘掉审批道注册 ⇒ 判据 1 那枚红" |
| K1b | 同一跑道的 ``stream_piece_sink=None,`` 形参（半接线） | 同上，红在 TypeError | 运行侧 |
| K2  | ``chat.approve`` 调用点的 ``stream_piece_sink=_piece_sink,`` | 端到端逐片定罪（注释留着也红 ⇒ 钉不看注释） | 运行侧 |
| K3  | 收端 ``if kind == "piece":`` 那一支的入口 | 端到端逐片定罪 + 判据⑥ 的窗内读数行 | 运行侧 |
| K4  | 「屏上已含其字 ⇒ 只记账」守卫的 ``startswith`` 方向 | R464 侧重放定罪（告警账被灌满） | 运行侧 |
| K5  | 同一格写钝成「一概不发」 | 端到端逐片定罪（证明绿不是靠不发帧换来的） | 运行侧 |
| K6  | 纸上 ``queue_lane=not_applicable`` 偷写成 ``connected`` | 纸盘对判钉 | 纸面 |
| K6b | 反方向：盘面真接上字而纸不改口 | 同一枚纸盘对判钉 | 盘面 |
| K7  | 判据③ 尺寸闸 ``20`` 改成 ``2`` | 三把尺字面钉 + 运行侧常数钉 | 源文/运行侧 |
| K8  | ``publish_stream_pieces`` 里「无人注册直接 return」那一格 | 判据⑤ 的未注册钉 | 运行侧 |

🔴 派工词点名三把里的「摘掉**队列道**注册 ⇒ 端到端枚红」**照字面构造不出来**：那一支今天没有
注册可摘——``deploy/queue_worker.py`` 里 ``stream_piece_sink`` 零命中，唯一真接点在 ``deploy/**``
（本单写域外）。凭据与未达归因在 ``tests/test_r524_queue_lane_sends_no_second_character.py`` 与
交工纸 ``docs/testing/r524-stream-piece-sink-two-runways.md``。本件按判据② 的裁定交**等价的两把**：
K6（纸偷写成已过 ⇒ 红）与 K6b（盘面真接上而纸不改口 ⇒ 红），两把都是双向牙，不是一句"反正没接"。
"""

import ast
import hashlib
import inspect
import re
from pathlib import Path

import test_r524_queue_lane_sends_no_second_character as queue_lane
import test_r524_sink_reaches_both_runways as both
from app.agents import nodes, orchestrator
from app.api.v1 import chat
from tests.test_r203_sse_progressive_frames import CHUNK_SIZE  # noqa: F401  在册假 provider 的 chunk 宽度

# 两枚在册件里的 fixture 直接搬进本模块：pytest 按本模块的名字找 fixture，同一实例不造第二套。
lane = queue_lane.lane  # noqa: F841
offline = both.offline  # noqa: F841

REPO = Path(__file__).resolve().parents[1]
CHAT_PATH = REPO / "app" / "api" / "v1" / "chat.py"
ORCHESTRATOR_PATH = REPO / "app" / "agents" / "orchestrator.py"
NODES_PATH = REPO / "app" / "agents" / "nodes.py"
PAPER_PATH = REPO / "docs" / "testing" / "r524-stream-piece-sink-two-runways.md"
TRACKED = (CHAT_PATH, ORCHESTRATOR_PATH, NODES_PATH, PAPER_PATH)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


#: 进门就抄死的四枚指纹：每把刀进刀前后各核一次，最后一枚用例总清点读这里。
FINGERPRINT_AT_IMPORT = {path: _sha(path) for path in TRACKED}
#: 摘刀只作用在内存副本上，所以"原件长什么样"必须在 import 那一刻抄下来，不许回头再读盘。
TEXT_AT_IMPORT = {path: path.read_text(encoding="utf-8")
                  for path in (CHAT_PATH, ORCHESTRATOR_PATH, NODES_PATH)}

#: 锚点全部现取唯一（命中 0 次或 >1 次 ⇒ ``_cut`` 当场红，死牙不算牙）。
REGISTER_LINE = '        config["configurable"][STREAM_PIECE_SINK_KEY] = stream_piece_sink\n'
#: 摘刀后的形状：只把那一枚赋值换成 ``pass``。整行删掉会让 ``if stream_piece_sink is not None:``
#: 底下只剩注释 ⇒ SyntaxError，影子的 exec 与源文侧的 ast.parse 都跑不起来——那是机械坏了，不是牙。
REGISTER_LINE_CUT = "        pass  # 反证 K1：注册腿摘掉，这一本 config 里不再出现那枚键\n"
PARAM_LINE = "    stream_piece_sink=None,\n"
CALL_SITE = "                    stream_piece_sink=_piece_sink,\n"
RECEIVER_GATE = '            if kind == "piece":'
RECEIVER_GATE_CUT = '            if kind == "__piece_branch_cut_by_r524_k3":'
REPLAY_GUARD = "answer_stream.on_screen.startswith(frame_text)"
UNREGISTERED_RETURN = "    if sink is None:\n        return\n"
RULER_TEXT = "STREAM_PIECE_MIN_CHARS = 20"



# ==================== 机械：影子摘刀 + 定罪格调用器 + 台账 ====================

_CUT_TAGS: set = set()
_RED_VICTIMS: set = set()

#: 本件声明的全部刀号；最后一枚用例按这张表清点"每把都真摘过、每把都真咬出红"。
KNIFE_TAGS = ("k1", "k1b", "k2", "k3", "k4", "k5", "k6", "k6b", "k7", "k8")
#: 走"影子回挂"那套机械的七把：K6/K6b/K7 动的是纸面读数与模块常数，不经 exec，不该出现在 _CUT_TAGS 里。
CUT_KNIVES = ("k1", "k1b", "k2", "k3", "k4", "k5", "k8")


def _top_level_segment(text: str, name: str) -> str:
    """取源文里某枚**顶层**函数的整段源码（不含装饰器；嵌套定义算在这一段里）。"""
    found = [
        ast.get_source_segment(text, node)
        for node in ast.parse(text).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(found) == 1, f"{name}：顶层定义 {len(found)} 枚，本件的取段前提变了"
    return found[0] or ""


def _cut(module, name: str, edits, monkeypatch, tmp_path, tag: str):
    """按锚点摘一格，改出的源码写进 ``tmp_path`` 影子副本，再 exec 回挂到模块上。

    ``edits=()`` 就是**正控**：同一套机械不摘任何一刀，victim 必须先绿一遍，否则"红"是它本来
    就红，量不出任何东西。被跟踪文件的指纹在进刀前后各核一次。
    """
    tracked = Path(inspect.getsourcefile(module)).resolve()
    assert tracked in FINGERPRINT_AT_IMPORT, f"{tracked.name}：不在本件的指纹台账里"
    assert _sha(tracked) == FINGERPRINT_AT_IMPORT[tracked], \
        f"{tag}：进刀之前 {tracked.name} 就不是原样了"
    source = _top_level_segment(TEXT_AT_IMPORT[tracked], name)
    shadow_source = source
    for needle, replacement in edits:
        hits = shadow_source.count(needle)
        assert hits == 1, f"{tag}：锚点在 {name} 里命中 {hits} 次（要恰好 1 次）⇒ 这枚反证是空的"
        shadow_source = shadow_source.replace(needle, replacement, 1)
    if edits:
        assert shadow_source != source, f"{tag}：改了个寂寞"

    target = tmp_path / f"r524_shadow_{tag}.py"
    assert REPO not in target.resolve().parents, f"{tag}：影子副本落进仓里了，这一刀不许开"
    target.write_text(shadow_source, encoding="utf-8", newline="\n")

    original = getattr(module, name)
    monkeypatch.setattr(module, name, original)  # 先把原件记进 teardown，再 exec 覆盖同一个名字
    exec(compile(shadow_source, str(target), "exec"), module.__dict__)
    shadow = getattr(module, name)
    assert shadow is not original, f"{tag}：影子与原件是同一枚对象"
    assert _sha(tracked) == FINGERPRINT_AT_IMPORT[tracked], \
        f"{tag}：摘刀在被跟踪文件上留下了写口"
    _CUT_TAGS.add(tag)
    return shadow


def _mutate_text(path: Path, edits, name: str | None = None):
    """源文侧的摘刀：只在内存副本上动，交给**在册那枚字面钉用的同一表达式**去判。

    🔴 ``name`` 给定时锚点限定在那枚顶层函数的整段里数：同名锚点在**另一枚跑道**里还有一枚，
    整本文件计数会把两枚一起抓出来，那-not-本刀要摘的格子（K1 摘审批道，不该把 ``run_with_stream``
    一起带倒——上一班那枚"永不匹配的死牙"就是从这种抓错格子上长出来的）。
    """
    text = TEXT_AT_IMPORT[path]
    scope = _top_level_segment(text, name) if name else text
    mutated = scope
    for needle, replacement in edits:
        hits = mutated.count(needle)
        assert hits == 1, f"锚点在 {name or path.name} 里命中 {hits} 次 ⇒ 这枚反证是空的"
        mutated = mutated.replace(needle, replacement, 1)
    assert mutated != scope, "摘刀没作用到东西上"
    return text.replace(scope, mutated, 1) if name else mutated


def _bite(fn, *args) -> str:
    """跑在册那枚钉：红了交回 ``"类型: 红话"``，没红交回空串。"""
    try:
        fn(*args)
    except Exception as error:  # noqa: BLE001  # 这里要的就是"任何形状的红"，KeyError/TypeError 都算
        _RED_VICTIMS.add(fn.__name__)
        return f"{type(error).__name__}: {error}"
    return ""


# ==================== K1：摘审批道写 configurable 的那枚注册语句 ====================


def test_k1_positive_control_the_text_predicate_and_the_named_pin_both_read_wired():
    """正控：源文侧谓词（在册钉用的那一段表达式）与在册钉本身此刻同判——两跑道都接上了。"""
    text = TEXT_AT_IMPORT[ORCHESTRATOR_PATH]
    for runway in ("run_with_stream", "run_interrupt_stream"):
        assert both._runway_is_wired(both._runway_body(text, runway)), runway
    assert text.count(both.REGISTER_STATEMENT) == 2, text.count(both.REGISTER_STATEMENT)
    both.test_criterion_one_names_both_runways_not_just_a_hit_count()


def test_k1_positive_control_the_unmutated_shadow_registers_the_sink(monkeypatch, tmp_path):
    """正控：同一套机械不摘刀（``edits=()``），真跑 ``run_interrupt_stream`` 那枚钉必须绿。"""
    _cut(orchestrator, "run_interrupt_stream", (), monkeypatch, tmp_path, "k1_control")
    both.test_the_resume_runway_registers_the_very_sink_the_caller_handed_in(monkeypatch)


def test_k1_dropping_the_registration_line_goes_red_on_both_sides(monkeypatch, tmp_path):
    """**刀 K1**（派工词点名的那一把）：摘掉注册语句 ⇒ 判据① 那枚钉红，且源文侧谓词同时不成立。

    摘形：那一枚赋值换成 ``pass`` 而不是整行删掉——整行删了 ``if stream_piece_sink is not None:``
    底下只剩注释，影子的 exec 与源文侧的 ``ast.parse`` 都会 SyntaxError，那是机械坏了而不是牙咬到。
    源文侧摘的是内存副本（被跟踪文件一字节不动），喂给 ``both._runway_is_wired``——那正是
    ``test_criterion_one_...`` 里逐字用的表达式；运行侧摘刀之后叫的是**在册钉本身**。
    """
    mutated = _mutate_text(ORCHESTRATOR_PATH, [(REGISTER_LINE, REGISTER_LINE_CUT)], name="run_interrupt_stream")
    assert not both._runway_is_wired(both._runway_body(mutated, "run_interrupt_stream")), \
        "摘掉审批道的注册语句，按函数点名的谓词居然还说接上了：这枚牙是死牙"
    assert both._runway_is_wired(both._runway_body(mutated, "run_with_stream")), \
        "K1 只许咬审批道：把 run_with_stream 也带倒了，说明锚点抓错格子"
    assert mutated.count(both.REGISTER_STATEMENT) == 1

    _cut(orchestrator, "run_interrupt_stream", [(REGISTER_LINE, REGISTER_LINE_CUT)], monkeypatch, tmp_path, "k1")
    red = _bite(both.test_the_resume_runway_registers_the_very_sink_the_caller_handed_in, monkeypatch)
    assert "stream_piece_sink" in red, red


def test_k1b_dropping_the_parameter_half_wires_the_runway(monkeypatch, tmp_path):
    """**刀 K1b**：只摘形参留下注册语句 ⇒ 半接线。文本谓词红，真跑红在 TypeError。"""
    mutated = _mutate_text(ORCHESTRATOR_PATH, [(PARAM_LINE, "")], name="run_interrupt_stream")
    assert not both._runway_is_wired(both._runway_body(mutated, "run_interrupt_stream"))
    assert mutated.count(both.REGISTER_STATEMENT) == 2, "K1b 没动注册语句，注册计数那格仍旧该是两枚"

    _cut(orchestrator, "run_interrupt_stream", [(PARAM_LINE, "")], monkeypatch, tmp_path, "k1b")
    red = _bite(both.test_the_resume_runway_registers_the_very_sink_the_caller_handed_in, monkeypatch)
    assert red.startswith("TypeError") and "stream_piece_sink" in red, red


# ==================== K2/K3/K4/K5：摘 chat.approve 上的四格 ====================


def test_k2_positive_control_the_shadow_approve_still_streams_progressive_frames(
        offline, monkeypatch, tmp_path):
    """正控：把 ``approve`` 原样 exec 一遍再跑端到端——摘刀机械本身不改任何行为。"""
    _cut(chat, "approve", (), monkeypatch, tmp_path, "k2_control")
    both.test_the_resume_runway_streams_progressive_frames_when_the_screen_holds_nothing(offline)


def test_k2_dropping_the_call_site_starves_the_resume_runway(offline, monkeypatch, tmp_path):
    """**刀 K2**：摘掉调用点那一行 ⇒ 续跑道收不到出口，端到端逐片定罪当场红。

    注释里"注册点"那几行原样留着也没救：定罪格读的是屏上真到过什么，不是源码里的自述。
    """
    _cut(chat, "approve", [(CALL_SITE, "")], monkeypatch, tmp_path, "k2")
    red = _bite(both.test_the_resume_runway_streams_progressive_frames_when_the_screen_holds_nothing,
                offline)
    assert "text 事件 >1 不成立" in red, red


def test_k3_positive_control_the_receiver_branch_is_live(offline, caplog, monkeypatch, tmp_path):
    """正控：不摘刀时端到端与窗内读数两枚钉同绿（后者证明日志行真打得出来）。"""
    _cut(chat, "approve", (), monkeypatch, tmp_path, "k3_control")
    both.test_the_resume_runway_streams_progressive_frames_when_the_screen_holds_nothing(offline)
    caplog.clear()
    both.test_the_resume_runway_reports_the_round_in_the_registered_log_keys(offline, caplog)


def test_k3_dropping_the_receiving_branch_kills_frames_and_the_window_reading(
        offline, caplog, monkeypatch, tmp_path):
    """**刀 K3**：收端那一支进不去 ⇒ 帧与判据⑥ 的读数行一起消失（两处都得有牙）。"""
    _cut(chat, "approve", [(RECEIVER_GATE, RECEIVER_GATE_CUT)], monkeypatch, tmp_path, "k3")
    red = _bite(both.test_the_resume_runway_streams_progressive_frames_when_the_screen_holds_nothing,
                offline)
    assert "text 事件 >1 不成立" in red, red
    caplog.clear()
    red_line = _bite(both.test_the_resume_runway_reports_the_round_in_the_registered_log_keys,
                     offline, caplog)
    assert "AssertionError" in red_line and "[]" in red_line, red_line


def test_k4_positive_control_a_replay_never_reaches_the_alarm_ledger(
        offline, caplog, monkeypatch, tmp_path):
    """正控：屏上已站着同一份正文时，R464 那一侧的账本该是干净的（零枚帧、零条告警）。"""
    _cut(chat, "approve", (), monkeypatch, tmp_path, "k4_control")
    both.test_the_resume_runway_does_not_re_deliver_text_already_on_screen(offline, caplog)


def test_k4_turning_the_replay_guard_into_an_equality_of_the_wrong_direction_goes_red(
        offline, caplog, monkeypatch, tmp_path):
    """**刀 K4**：``startswith`` 写歪成 ``endswith`` ⇒ 逐片帧不再被认成"屏上已有其字"。

    红不在"多发了一枚帧"（R464 闸门还是把非延续整段拦在门外），红在**那门账被灌满**：
    ``批准腿拦下 N 枚非延续整段`` 这条 error 一旦响起来，屏上是干净的而账已经不是了——
    正是本单不许留下的那种"看起来没改形状"的退化。
    """
    _cut(chat, "approve", [(REPLAY_GUARD, "answer_stream.on_screen.endswith(frame_text)")],
         monkeypatch, tmp_path, "k4")
    red = _bite(both.test_the_resume_runway_does_not_re_deliver_text_already_on_screen,
                offline, caplog)
    assert "批准腿拦下" in red, red


def test_k5_positive_control_the_progressive_shape_is_not_bought_by_silence(
        offline, monkeypatch, tmp_path):
    """正控：同一枚守卫未动时，屏上无正文那一族必须真发得出逐片帧（不是"不发所以没病历"）。"""
    _cut(chat, "approve", (), monkeypatch, tmp_path, "k5_control")
    both.test_the_resume_runway_streams_progressive_frames_when_the_screen_holds_nothing(offline)


def test_k5_blunting_the_guard_into_never_emitting_goes_red(offline, monkeypatch, tmp_path):
    """**刀 K5**：把守卫写钝成"一概不发" ⇒ 端到端逐片定罪当场红。

    这一把挡的是最省事的那种假绿：续跑道把片全吞进 ``piece_suppressed``，屏上形状与改前逐字
    相同，R464 一条告警都不响，看着也像"接上了而没惹事"。判据② 要的是**真到屏**。
    """
    _cut(chat, "approve", [(REPLAY_GUARD, "True")], monkeypatch, tmp_path, "k5")
    red = _bite(both.test_the_resume_runway_streams_progressive_frames_when_the_screen_holds_nothing,
                offline)
    assert "text 事件 >1 不成立" in red, red


# ==================== K6 / K6b：纸与盘面的对判（队列道那格的等价牙） ====================


def test_k6_positive_control_the_paper_word_matches_the_tree_today(lane):
    """正控：纸写 ``not_applicable``、盘面确实发不出第二枚字 ⇒ 在册对判钉是绿的。"""
    assert queue_lane.paper_verdict() == "not_applicable"
    assert queue_lane.verdict_for(queue_lane.queue_lane_facts(lane)) == "not_applicable"
    queue_lane.test_the_paper_word_and_the_tree_agree(lane)


def test_k6_forging_the_paper_word_goes_red(lane, monkeypatch):
    """**刀 K6**（派工词点名的第三把）：把 ``not_applicable`` 偷写成 ``connected`` ⇒ 那枚对判红。

    伪造落在"纸交回来的那一格读到的词"上（``paper_verdict`` 的读数），在册那枚
    ``test_the_paper_word_and_the_tree_agree`` 叫的是同一个落点，所以红的是**在册钉本身**；
    交工纸一字节未改（末尾指纹总清点读这里）。
    """
    monkeypatch.setattr(queue_lane, "paper_verdict", lambda *_a, **_k: "connected")
    red = _bite(queue_lane.test_the_paper_word_and_the_tree_agree, lane)
    assert "connected" in red and "not_applicable" in red, red


def test_k6b_connecting_the_tree_under_the_old_paper_goes_red(lane, monkeypatch, tmp_path):
    """**刀 K6b**：反方向同一枚——盘面真接上字（影子入队出口发两枚 text 帧）而纸不改口 ⇒ 同样红。

    这一把是派工词「摘掉队列道注册 ⇒ 端到端枚红」在本单写域内唯一能构造的等价形：那一支今天
    没有注册可摘（凭据见 ``test_r524_queue_lane_sends_no_second_character``），所以改成证明
    "对判不是单向的死牙：纸说没接而盘面接上了，一样当场红"。
    """
    monkeypatch.setattr(chat, "_enqueue_ask_turn", queue_lane._shadow_enqueue_with_pieces(tmp_path))
    facts = queue_lane.queue_lane_facts(lane)
    assert facts["text_frames"] > 1 and facts["model_calls"] == 0, facts
    assert queue_lane.verdict_for(facts) == "connected", facts
    red = _bite(queue_lane.test_the_paper_word_and_the_tree_agree, lane)
    assert "AssertionError" in red, red


# ==================== K7：判据③ 那三把尺（"为了过门把 20 改成 2" = 退回） ====================


def _merger_pieces(min_chars: int) -> list:
    """按在册口径把本轮正文喂进 merger：``min_chars`` 只在这里显式传，不看模块常数的默认绑定。"""
    merger = nodes.StreamPieceMerger(min_chars=min_chars)
    pieces = []
    for start in range(0, len(both.ANSWER), CHUNK_SIZE):
        pieces.extend(merger.feed(both.ANSWER[start:start + CHUNK_SIZE]))
    pieces.extend(merger.finish())
    return pieces


def test_k7_positive_control_the_three_rulers_read_the_caliber():
    """正控：三把尺现读 20 字 / 0.1 s / 4 字地板，在册那枚字面钉此刻是绿的。"""
    both.test_the_three_rulers_of_criterion_three_are_untouched()
    for name, literal in both.RULERS.items():
        assert re.search(rf"^{name} = {re.escape(literal)}$",
                         TEXT_AT_IMPORT[NODES_PATH], re.M), name
    assert _merger_pieces(nodes.STREAM_PIECE_MIN_CHARS) and all(
        len(piece.text) >= 20 for piece in _merger_pieces(20)[:-1]
    ), "在册尺寸闸下不该出现短于 20 字的中间片"


def test_k7_dulling_the_size_gate_to_two_chars_goes_red_every_side(monkeypatch):
    """**刀 K7**：把 20 改成 2 ⇒ 源文侧谓词与运行侧常数钉两半都红（判据③ 不许为了过门改数）。"""
    mutated = _mutate_text(NODES_PATH, [(RULER_TEXT, "STREAM_PIECE_MIN_CHARS = 2")])
    assert not re.search(rf"^STREAM_PIECE_MIN_CHARS = {re.escape(both.RULERS['STREAM_PIECE_MIN_CHARS'])}$",
                         mutated, re.M), "把 20 改成 2 之后字面钉的谓词居然还成立：这枚牙是死牙"
    monkeypatch.setattr(nodes, "STREAM_PIECE_MIN_CHARS", 2)
    red = _bite(both.test_the_three_rulers_of_criterion_three_are_untouched)
    assert "AssertionError" in red and "20" in red, red


def test_k7b_the_end_to_end_shape_is_blind_to_a_dulled_ruler():
    """K7 的补充事实：端到端那一格**量不到**钝尺，所以判据③ 必须靠字面钉——这不是装饰。

    ``min_chars=2`` 的 merger 把 157 字正文（现取 len(ANSWER)=157）切成一堆短于 20 字的碎片，而在"2 字"这把钝尺下每一片
    都不违例：任何"拼回去无损、时间戳不重叠"的形状断言都放行它。🔴 顺带记一笔机械事实：
    ``StreamPieceMerger.__init__`` 的默认值在类定义期绑定（``min_chars=STREAM_PIECE_MIN_CHARS``），
    运行时改模块常数改不动默认值，只有真改了源文才改得动——所以字面钉读源文，不读属性。
    """
    dulled = _merger_pieces(2)
    assert len(dulled) > len(_merger_pieces(20)), (len(dulled), len(_merger_pieces(20)))
    assert any(len(piece.text) < 20 for piece in dulled), [len(p.text) for p in dulled]
    assert all(len(piece.text) >= 2 for piece in dulled), "钝尺连 2 字都保不住：本例前提变了"
    assert "".join(piece.text for piece in dulled) == both.ANSWER


# ==================== K8：摘「无人注册直接 return」那一格（判据④/⑤ 不许倒退） ====================


def test_k8_positive_control_the_unregistered_round_is_still_silent(monkeypatch, tmp_path):
    """正控：不摘刀时 ``publish_stream_pieces`` 在无人注册那一支仍旧一个字节都不做。"""
    _cut(nodes, "publish_stream_pieces", (), monkeypatch, tmp_path, "k8_control")
    both.test_an_unregistered_round_publishes_nothing()


def test_k8_dropping_the_unregistered_early_return_goes_red(monkeypatch, tmp_path):
    """**刀 K8**：摘掉 ``sink is None ⇒ return`` 那一格 ⇒ 判据⑤ 那枚未注册钉当场红。

    摘完这一格，无人注册的轮次会一路走到 ``sink(piece)`` 并抛 TypeError，被 except 兜住记进
    ``logger.warning``：判据④ 要的"默认这一枚函数是整个特性关掉的样子"就没了——不建列表不发事件
    那一格正是靠这个早退撑着。红话里能看到那行 R31 告警。
    """
    _cut(nodes, "publish_stream_pieces", [(UNREGISTERED_RETURN, "")], monkeypatch, tmp_path, "k8")
    red = _bite(both.test_an_unregistered_round_publishes_nothing)
    assert "AssertionError" in red and "R31" in red, red


# ==================== 总清点：刀都真摘过、牙都真咬过、仓里一字节没动 ====================

#: 每把刀必须咬出红的那枚在册钉（按钉名点名，不数总数——数总数会把死牙算成活的）。
EXPECTED_RED_VICTIMS = {
    "test_the_resume_runway_registers_the_very_sink_the_caller_handed_in",  # K1 / K1b
    "test_the_resume_runway_streams_progressive_frames_when_the_screen_holds_nothing",  # K2 / K3 / K5
    "test_the_resume_runway_reports_the_round_in_the_registered_log_keys",  # K3
    "test_the_resume_runway_does_not_re_deliver_text_already_on_screen",  # K4
    "test_the_paper_word_and_the_tree_agree",  # K6 / K6b
    "test_the_three_rulers_of_criterion_three_are_untouched",  # K7
    "test_an_unregistered_round_publishes_nothing",  # K8
}


def test_z9_the_ledger_names_every_knife_and_every_tooth_bit():
    """台账查账：七把影子刀全真摘过，点名在册钉全真咬出红，而且不止三把（判据⑦ 的 >=3 是下限）。"""
    assert _CUT_TAGS >= set(CUT_KNIVES), sorted(set(CUT_KNIVES) - _CUT_TAGS)
    missing = EXPECTED_RED_VICTIMS - _RED_VICTIMS
    assert not missing, f"这些在册钉一次都没被摘红：{sorted(missing)}"
    assert len(_RED_VICTIMS) >= 3, sorted(_RED_VICTIMS)


def test_z9b_the_tracked_files_are_the_ones_we_opened_the_door_with():
    """九把刀跑完，四份被跟踪件（含交工纸）的指纹必须还是进门那一刻那四枚。"""
    for path, digest in FINGERPRINT_AT_IMPORT.items():
        assert _sha(path) == digest, path
    strays = list((REPO / "tests").glob("r524_shadow_*.py")) + list(REPO.glob("r524_shadow_*.py"))
    assert not strays, strays
