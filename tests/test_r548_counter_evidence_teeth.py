# -*- coding: utf-8 -*-
"""R548 反证刀 —— 十把，victim 全部是**在册钉本身**，仓里一字节不动。

机械口径照 R524 那笔的先例（``tests/test_r524_counter_evidence_teeth.py`` §6）：

- 摘刀一律在**内存影子**里做。被跟踪文件的源文在 import 那一刻抄进 ``TEXT_AT_IMPORT``，按锚点改
  一格，写进 ``tmp_path`` 的影子副本；``exec`` 的目标是模块**活的那本 ``__dict__``**（不是
  ``dict(vars(module))`` 的副本）——victim 钉在跑的过程里还要 ``monkeypatch`` 别的模块属性
  （``orchestrator._cancellable_stream``、``queue_worker._queue``），副本 globals 会让影子看不见
  那些补丁 ⇒ 正控与摘刀量的就不是同一条链。
- 源文侧的摘刀（K8/K1b）不 exec，只把改过的文本喂给**在册钉自己用的那枚读数函数**
  （``nail.worker_source`` / ``queue_lane.WORKER_PATH``），所以红的是钉本身，不是钉旁边的注释。
- 每把刀进刀前后各核一次被跟踪文件的 sha256，逐条记进 ``SHA_LEDGER``；最后两枚用例总清点：
  十把都真摘过、点名的在册钉都真咬出红、四枚以上文件仍是进门那一刻的字节。

判据④ 要的下限是五把；本单交十把，其中 K1/K3/K5 三把是派工词点名形状的正面等价物（摘注册 ⇒
判据① 那枚红、收端钝化成"一整篇" ⇒ 可区分性那枚红、片漏进发布面 ⇒ 零外溢那枚红）。

🔴 与 R524 同一格偏差，写在纸上而不是藏起来：派工词那句「摘掉队列道注册 ⇒ 端到端一枚红」里的
"端到端"在这里仍旧取不到——投递面没裁，队列道没有一条活着的流可收片（凭据见 R548 交工纸 §5，
真读数挂在 run11）。本单交的是**进程内端到端**：真 ``run_with_stream`` 把出口塞进 config、真
``nodes.publish_stream_pieces`` 盖章交片、真 ``process_one`` 把这一轮跑完并发布。摘注册之后红的
就是这条链上的钉。
"""

import ast
import hashlib
import inspect
from pathlib import Path

import test_r524_queue_lane_sends_no_second_character as queue_lane
import test_r548_queue_lane_registers_the_piece_sink as nail
from deploy import queue_worker

REPO = Path(__file__).resolve().parents[1]
WORKER_PATH = REPO / "deploy" / "queue_worker.py"
NAIL_PATH = REPO / "tests" / "test_r548_queue_lane_registers_the_piece_sink.py"
R524_PATH = REPO / "tests" / "test_r524_queue_lane_sends_no_second_character.py"
PAPER_PATH = REPO / "docs" / "testing" / "r548-queue-lane-piece-sink-registration.md"
NODES_PATH = REPO / "app" / "agents" / "nodes.py"
ORCHESTRATOR_PATH = REPO / "app" / "agents" / "orchestrator.py"
TRACKED = (WORKER_PATH, NAIL_PATH, R524_PATH, PAPER_PATH, NODES_PATH, ORCHESTRATOR_PATH)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


#: 进门就抄死的六枚指纹：每把刀进刀前后各核一次，最后两枚用例总清点读这里。
FINGERPRINT_AT_IMPORT = {path: _sha(path) for path in TRACKED}
#: 摘刀只作用在内存副本上，所以"原件长什么样"必须在 import 那一刻抄下来，不许回头再读盘。
TEXT_AT_IMPORT = {WORKER_PATH: WORKER_PATH.read_text(encoding="utf-8")}

#: 锚点全部现取唯一（命中 0 次或 >1 次 ⇒ ``_cut`` 当场红，死牙不算牙）。
REG_LINE = "        stream_piece_sink=stream_piece_sink,\n"
#: 摘形换成注释而不是整行删：整行删了 ``task_id=task_id,`` 之后紧跟 ``):`` 仍然合法，但注释留着
#: 更狠——它证明定罪格读的是 AST 里的关键字，不是源码里那行像不像注册点（R524 K2 同一条裁定）。
REG_LINE_CUT = "        # 反证 K1：注册腿摘掉，这一本 config 里不再长出那枚键\n"
PARAM_LINE = "    stream_piece_sink=None,\n"
RETURN_LINE = "    return final_answer, agent_results, stream_error"
RETURN_LEAK = (
    "    if stream_piece_sink is not None and callable("
    "getattr(stream_piece_sink, \"joined_text\", None)):\n"
    "        final_answer = str(stream_piece_sink.joined_text()) + final_answer\n"
    "    return final_answer, agent_results, stream_error"
)
APPEND_BLOCK = (
    "        if len(self.pieces) < self.limit:\n"
    "            self.pieces.append(piece)\n"
)
#: 把收端钝化成"一次投喂一整篇"那种写法：拼起来仍旧等值，分片数被抹平。
APPEND_LUMP = (
    "        if self.pieces:\n"
    "            self.pieces[0] = self.pieces[0]._replace("
    "text=self.pieces[0].text + piece.text)\n"
    "            return\n"
    + APPEND_BLOCK
)
OVERFLOW_LINE = "            self.overflow += 1\n"
OVERFLOW_CUT = "            pass  # 反证 K7：超限的片静默吞掉，不计数\n"
LOG_GATE = "    if not ledger.count:\n        return\n"
LOG_NEVER = "    if ledger.count >= 0:\n        return\n"
LOG_ALWAYS = "    if ledger.count < 0:\n        return\n"
TOKEN = "stream_piece_sink"
TOKEN_DETACHED = "piece_sink_detached_by_r548_teeth"

#: 走"影子回挂"机械的刀（exec 过才算真摘过）；另外三把走源文侧/判定侧，不该出现在这张表里。
CUT_KNIVES = ("k1", "k2", "k3", "k4", "k4b", "k5", "k7")
KNIFE_TAGS = ("k1", "k1b", "k2", "k3", "k4", "k4b", "k5", "k6", "k7", "k8")

#: 每把刀进刀前后各留一条：``{tag, file, before, after}``——总清点钉按这张表对账。
SHA_LEDGER: list = []
_CUT_TAGS: set = set()
_RED_VICTIMS: set = set()

#: 本件点名要咬红的在册钉（判据④ 的"victim 必须是在册钉本身"落在这里，逐枚点名）。
EXPECTED_RED_VICTIMS = {
    "test_the_registered_sink_reaches_the_graph_configuration",  # K1 / K2
    "test_a_direct_drain_that_hands_over_nothing_adds_not_a_single_key",  # K2
    "test_a_whole_dump_is_distinguishable_from_the_piece_run",  # K3
    "test_the_pieces_the_producer_stamps_and_publishes_arrive_in_order",  # K3
    "test_a_round_that_flowed_pieces_leaves_exactly_one_readout_line",  # K4
    "test_a_quiet_round_adds_not_a_single_readout_line",  # K4b
    "test_the_published_readings_do_not_move_when_pieces_flow",  # K5
    "test_the_paper_word_and_the_tree_agree",  # K6（R524 在册对判钉）
    "test_a_dead_registration_alone_does_not_read_as_connected_on_the_enqueue_lane",  # K6
    "test_the_ledger_counts_pieces_it_cannot_keep",  # K7
    "test_the_queue_lane_registers_exactly_one_sink_at_the_orchestrator_call",  # K8
    "test_the_only_other_handoff_carries_the_round_ledger_down",  # K8
    "test_the_real_hook_for_the_queue_lane_is_now_registered__r548",  # K1b（R524 改口钉）
    "test_the_enqueue_exit_still_registers_no_sink__r548_moved_the_hook_to_the_worker",  # K1b
}

lane = queue_lane.lane  # noqa: F841  R524 那枚入队道夹具，按同名同形借过来


# ==================== 机械：影子摘刀 + 源文侧摘刀 + 定罪格调用器 ====================


def _top_level_segment(text: str, name: str) -> str:
    """取源文里某枚**顶层**定义（函数或类）的整段源码（不含装饰器；嵌套定义算在这一段里）。"""
    found = [
        ast.get_source_segment(text, node)
        for node in ast.parse(text).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == name
    ]
    assert len(found) == 1, f"{name}：顶层定义 {len(found)} 枚，本件的取段前提变了"
    return found[0] or ""


def _record(tag: str, path: Path, before: str, after: str) -> None:
    SHA_LEDGER.append({"tag": tag, "file": path.name, "before": before, "after": after})
    assert before == after, f"{tag}：摘刀在被跟踪文件 {path.name} 上留下了写口"


def _cut(module, name: str, edits, monkeypatch, tmp_path, tag: str):
    """按锚点摘一格：影子副本写进 ``tmp_path``，再 exec 回挂到模块活的 globals 上。

    ``edits=()`` 就是**正控**：同一套机械不摘任何一刀，victim 必须先绿一遍，否则"红"是它本来就
    红，量不出任何东西。被跟踪文件的指纹在进刀前后各核一次、逐条记进台账。
    """
    tracked = Path(inspect.getsourcefile(module)).resolve()
    assert tracked in FINGERPRINT_AT_IMPORT, f"{tracked.name}：不在本件的指纹台账里"
    before = _sha(tracked)
    assert tracked in TEXT_AT_IMPORT, f"{tracked.name}：本件没抄它的进门源文"
    source = _top_level_segment(TEXT_AT_IMPORT[tracked], name)
    shadow_source = source
    for needle, replacement in edits:
        hits = shadow_source.count(needle)
        assert hits == 1, f"{tag}：锚点在 {name} 里命中 {hits} 次（要恰好 1 次）⇒ 这枚反证是空的"
        shadow_source = shadow_source.replace(needle, replacement, 1)
    if edits:
        assert shadow_source != source, f"{tag}：改了个寂寞"

    target = tmp_path / f"r548_shadow_{tag}.py"
    assert REPO not in target.resolve().parents, f"{tag}：影子副本落进仓里了，这一刀不许开"
    target.write_text(shadow_source, encoding="utf-8", newline="\n")

    original = getattr(module, name)
    monkeypatch.setattr(module, name, original)  # 先把原件记进 teardown，再 exec 覆盖同一个名字
    exec(compile(shadow_source, str(target), "exec"), module.__dict__)
    shadow = getattr(module, name)
    assert shadow is not original, f"{tag}：影子与原件是同一枚对象"
    after = _sha(tracked)
    _record(tag, tracked, before, after)
    if edits:
        _CUT_TAGS.add(tag)
    return shadow


def _mutate_worker(edits, tag: str) -> str:
    """源文侧摘刀：只在内存副本上动，交回整本文件的改后文本（仓里一字节不动）。

    改完先 ``ast.parse`` 一遍——SyntaxError 是机械坏了，不是牙咬到；再按同一枚 tag 把被跟踪文件的
    进刀前后 sha256 记进台账（这一把不动盘，所以两枚必然相等；不等就是别的东西在写）。
    """
    before = _sha(WORKER_PATH)
    text = TEXT_AT_IMPORT[WORKER_PATH]
    mutated = text
    for needle, replacement in edits:
        hits = mutated.count(needle)
        assert hits == 1, f"锚点命中 {hits} 次 => 这枚反证是空的：{needle!r}"
        mutated = mutated.replace(needle, replacement, 1)
    assert mutated != text, "摘刀没作用到东西上"
    ast.parse(mutated)
    _record(tag, WORKER_PATH, before, _sha(WORKER_PATH))
    return mutated


def _bite(fn, *args) -> str:
    """跑在册那枚钉：红了交回 ``"类型: 红话"``，没红交回空串。"""
    try:
        fn(*args)
    except Exception as error:  # noqa: BLE001  要的就是"任何形状的红"：KeyError/TypeError/AssertionError 都算
        _RED_VICTIMS.add(fn.__name__)
        return f"{type(error).__name__}: {error}"
    return ""


# ==================== K1：摘掉交给编排的那一枚注册关键字 ====================


def test_k1_positive_control_the_unmutated_shadow_still_hands_the_sink_down(monkeypatch, tmp_path):
    """正控：同一套机械不摘刀 ⇒ 交收端那枚在册钉必须先是绿的。"""
    _cut(queue_worker, "_drain_report_stream", (), monkeypatch, tmp_path, "k1_control")
    nail.test_the_registered_sink_reaches_the_graph_configuration(monkeypatch, tmp_path)


def test_k1_dropping_the_registration_keyword_starves_the_queue_lane(monkeypatch, tmp_path):
    """**刀 K1**（派工词点名的那一把的进程内等价形）：摘注册 ⇒ 交收端那枚在册钉红在 KeyError。

    源文侧同时验一遍：把那一行换成一条**留着当纪念的注释**，``nail.registration_points`` 立刻数到
    零枚——定罪格读 AST，不读注释；而注册点之外的形参、docstring 原样留着也不影响它红。
    """
    mutated = _mutate_worker([(REG_LINE, REG_LINE_CUT)], "k1")
    assert nail.registration_points(mutated) == [], nail.registration_points(mutated)
    assert [h["callee"] for h in nail.sink_handoffs(mutated)] == ["_drain_report_stream"]

    _cut(queue_worker, "_drain_report_stream", [(REG_LINE, REG_LINE_CUT)], monkeypatch, tmp_path, "k1")
    red = _bite(nail.test_the_registered_sink_reaches_the_graph_configuration, monkeypatch, tmp_path)
    assert "stream_piece_sink" in red, red


# ==================== K2：只摘形参（半接线） ====================


def test_k2_dropping_the_parameter_half_wires_the_runway(monkeypatch, tmp_path):
    """**刀 K2**：形参摘掉、调用点留着 ⇒ 只剩半根线，真跑与直调两枚在册钉一起红。

    根因单独点名（第一手实取教出来的一格）：摘掉形参后那枚注册关键字 `stream_piece_sink` 是
    未定义名，`_drain_report_stream` 当场 `NameError`；而 `_process_report_lane_turn` 把后台
    异常收成 error 日志（在册行为，本单一字节没改它），所以**发布面看得到的症状是"这一轮连
    config 都没到"**（`KeyError: 'config'`）。两半都要有据：NameError 里必须出现那枚符号，
    红掉的必须是「收端没进 config」与「直调不该加键」这两枚在册钉。
    """
    mutated = _mutate_worker([(PARAM_LINE, "")], "k2")
    assert "    stream_piece_sink=None," not in mutated
    assert nail.registration_points(mutated) and nail.registration_points(mutated)[0]["line"]

    _cut(queue_worker, "_drain_report_stream", [(PARAM_LINE, "")], monkeypatch, tmp_path, "k2")

    try:
        queue_worker._drain_report_stream(
            "r548-k2",
            thread_id="t",
            principal=None,
            provenance=None,
            request_id="r",
            trace_id="c",
            task_id="k",
        )
        raise AssertionError("K2：形参摘掉之后 `_drain_report_stream` 居然跑通了——这半根线是虚的")
    except NameError as error:
        assert "stream_piece_sink" in str(error), error

    red = _bite(nail.test_a_direct_drain_that_hands_over_nothing_adds_not_a_single_key,
                monkeypatch, tmp_path)
    assert "config" in red, red
    red = _bite(nail.test_the_registered_sink_reaches_the_graph_configuration, monkeypatch, tmp_path)
    assert red, red


# ==================== K3：把收端钝化成"一次投喂一整篇" ====================


def test_k3_positive_control_the_ledger_keeps_the_pieces_apart(monkeypatch, tmp_path):
    """正控：原样 exec 一遍收端类 ⇒ 可区分性那枚在册钉是绿的（机械本身不改行为）。"""
    _cut(queue_worker, "ReportLanePieceLedger", (), monkeypatch, tmp_path, "k3_control")
    nail.test_a_whole_dump_is_distinguishable_from_the_piece_run()


def test_k3_blunting_the_ledger_into_one_lump_goes_red(monkeypatch, tmp_path):
    """**刀 K3**：收端把片并成一枚 ⇒ 判据① 那两枚一起红（拼起来等值这一半还成立，分片数先塌）。"""
    _cut(queue_worker, "ReportLanePieceLedger", [(APPEND_BLOCK, APPEND_LUMP)],
         monkeypatch, tmp_path, "k3")
    red = _bite(nail.test_a_whole_dump_is_distinguishable_from_the_piece_run)
    assert "assert 1 > 1" in red or "count > 1" in red, red
    red = _bite(nail.test_the_pieces_the_producer_stamps_and_publishes_arrive_in_order,
                monkeypatch, tmp_path)
    assert red, red


# ==================== K4 / K4b：读数那一行的两向钝化 ====================


def test_k4_blunting_the_readout_into_never_logging_goes_red(monkeypatch, tmp_path):
    """**刀 K4**：读数永不留行 ⇒ "流到字就恰有一行"那枚红（真机窗会读同一行，摘了就没得读）。"""
    _cut(queue_worker, "_log_report_lane_pieces", (), monkeypatch, tmp_path, "k4_control")
    nail.test_a_round_that_flowed_pieces_leaves_exactly_one_readout_line(monkeypatch, tmp_path)

    _cut(queue_worker, "_log_report_lane_pieces", [(LOG_GATE, LOG_NEVER)], monkeypatch, tmp_path, "k4")
    red = _bite(nail.test_a_round_that_flowed_pieces_leaves_exactly_one_readout_line,
                monkeypatch, tmp_path)
    assert red, red


def test_k4b_blunting_the_readout_into_always_logging_goes_red(monkeypatch, tmp_path):
    """**刀 K4b**：反向同一格——每轮都留行 ⇒ "没流到字就一行都不留"那枚红（既有日志面被污染）。"""
    _cut(queue_worker, "_log_report_lane_pieces", [(LOG_GATE, LOG_ALWAYS)], monkeypatch, tmp_path, "k4b")
    red = _bite(nail.test_a_quiet_round_adds_not_a_single_readout_line, monkeypatch, tmp_path)
    assert red, red


# ==================== K5：片漏进发布面（零外溢那枚钉的真牙） ====================


def test_k5_positive_control_the_published_readings_are_still_quiet(monkeypatch, tmp_path):
    """正控：原样 exec 一遍 drain ⇒ 零外溢那枚在册钉是绿的（不是它本来就红）。"""
    _cut(queue_worker, "_drain_report_stream", (), monkeypatch, tmp_path, "k5_control")
    nail.test_the_published_readings_do_not_move_when_pieces_flow(monkeypatch, tmp_path)


def test_k5_leaking_pieces_into_the_answer_goes_red(monkeypatch, tmp_path):
    """**刀 K5**：让片参与正文 ⇒ 零外溢那枚当场红（本单的绿不是靠"没人读这格"换来的）。"""
    _cut(queue_worker, "_drain_report_stream", [(RETURN_LINE, RETURN_LEAK)],
         monkeypatch, tmp_path, "k5")
    red = _bite(nail.test_the_published_readings_do_not_move_when_pieces_flow, monkeypatch, tmp_path)
    assert red, red


# ==================== K6：把队列道那格洗成 connected ====================


def test_k6_washing_the_verdict_with_a_dead_registration_goes_red(lane, monkeypatch):
    """**刀 K6**：恢复 R524 改前那条"存在注册点就算 connected" ⇒ R524 对判钉与本单那枚一起红。

    这一把证明判据② 的改口**只严不松**：注册点存在而投递面为空，今天必须读成
    ``not_applicable``；谁把这条规则放宽回去，纸上的 ``not_applicable`` 就对不上盘。
    """
    def _old_rule(facts):
        if facts["sink_points"] or facts["graph_runs"]:
            return "connected"
        if facts["text_frames"] > 1:
            return "connected"
        return "not_applicable"

    before = _sha(R524_PATH)
    _record("k6", R524_PATH, before, before)
    assert queue_lane.verdict_for(queue_lane.queue_lane_facts(lane)) == "not_applicable"
    monkeypatch.setattr(queue_lane, "verdict_for", _old_rule)
    red = _bite(queue_lane.test_the_paper_word_and_the_tree_agree, lane)
    assert "connected" in red and "not_applicable" in red, red
    red = _bite(nail.test_a_dead_registration_alone_does_not_read_as_connected_on_the_enqueue_lane, lane)
    assert red, red


# ==================== K7：超限静默吞片 ====================


def test_k7_positive_control_the_ledger_counts_its_overflow(monkeypatch, tmp_path):
    """正控：原样 exec 一遍收端类 ⇒ 截断计数那枚在册钉是绿的。"""
    _cut(queue_worker, "ReportLanePieceLedger", (), monkeypatch, tmp_path, "k7_control")
    nail.test_the_ledger_counts_pieces_it_cannot_keep()


def test_k7_dropping_the_overflow_count_goes_red(monkeypatch, tmp_path):
    """**刀 K7**：超上限的片不计数码上 ⇒ 那枚在册钉红（"收端到底收到几枚"又变成看不见的东西）。"""
    _cut(queue_worker, "ReportLanePieceLedger", [(OVERFLOW_LINE, OVERFLOW_CUT)],
         monkeypatch, tmp_path, "k7")
    red = _bite(nail.test_the_ledger_counts_pieces_it_cannot_keep)
    assert red, red


# ==================== K8 / K1b：源文侧与在册负向钉 ====================


def test_k8_detaching_the_registration_token_goes_red_on_the_ast_pins(monkeypatch):
    """**刀 K8**：把整本源文里的出口名摘掉（等于 R548 从未落地）⇒ 两枚 AST 钉本身一起红。

    摘刀走 ``nail.worker_source`` 的读数——那正是两枚钉自己叫的那一手，所以红的是钉，不是注释。
    """
    before = _sha(WORKER_PATH)
    detached = TEXT_AT_IMPORT[WORKER_PATH].replace(TOKEN, TOKEN_DETACHED)
    assert TOKEN not in detached and TOKEN_DETACHED in detached
    monkeypatch.setattr(nail, "worker_source", lambda: detached)
    red = _bite(nail.test_the_queue_lane_registers_exactly_one_sink_at_the_orchestrator_call)
    assert red, red
    red = _bite(nail.test_the_only_other_handoff_carries_the_round_ledger_down)
    assert red, red
    _record("k8", WORKER_PATH, before, _sha(WORKER_PATH))


def test_k1b_the_r524_teeth_read_the_tree_not_memory(monkeypatch, tmp_path):
    """**刀 K1b**：把 R524 那枚在册钉的 ``WORKER_PATH`` 换成"没有注册点"的影子 ⇒ 两枚改口钉一起红。

    这一把是 R524 K6b 的同族：它证明本单对 R524 负向钉的改口不是把断言写死成"永远绿"——盘面退回
    没有注册点的那一刻，那两枚钉立刻跟着退回红。影子文件写在 ``tmp_path``，仓里一字节不动。
    """
    detached = TEXT_AT_IMPORT[WORKER_PATH].replace(TOKEN, TOKEN_DETACHED)
    target = tmp_path / "queue_worker_r548_k1b.py"
    assert REPO not in target.resolve().parents
    target.write_text(detached, encoding="utf-8", newline="\n")
    before = _sha(WORKER_PATH)
    monkeypatch.setattr(queue_lane, "WORKER_PATH", target)
    red = _bite(queue_lane.test_the_real_hook_for_the_queue_lane_is_now_registered__r548)
    assert red, red
    red = _bite(queue_lane.test_the_enqueue_exit_still_registers_no_sink__r548_moved_the_hook_to_the_worker)
    assert red, red
    _record("k1b", WORKER_PATH, before, _sha(WORKER_PATH))


# ==================== 总清点（判据④ 的最后一条） ====================


def test_z9_the_ledger_names_every_knife_and_every_tooth_bit():
    """台账查账：十把刀各有记录、影子刀全真摘过、点名的在册钉全真咬出红。"""
    assert all(entry["tag"] for entry in SHA_LEDGER), SHA_LEDGER
    assert _CUT_TAGS >= set(CUT_KNIVES), sorted(set(CUT_KNIVES) - _CUT_TAGS)
    tagged = {entry["tag"].replace("(control)", "") for entry in SHA_LEDGER}
    assert tagged >= set(KNIFE_TAGS), sorted(set(KNIFE_TAGS) - tagged)
    missing = EXPECTED_RED_VICTIMS - _RED_VICTIMS
    assert not missing, f"这些在册钉一次都没被摘红：{sorted(missing)}"
    assert len(_RED_VICTIMS) >= 5, sorted(_RED_VICTIMS)
    assert len(SHA_LEDGER) >= len(KNIFE_TAGS), SHA_LEDGER
    for entry in SHA_LEDGER:
        assert entry["before"] == entry["after"], entry


def test_z9b_the_tracked_files_are_the_ones_we_opened_the_door_with():
    """十把刀跑完，六枚被跟踪件（含交工纸与本件的两枚钉）必须还是进门那一刻的字节。"""
    for path, digest in FINGERPRINT_AT_IMPORT.items():
        assert _sha(path) == digest, path
    strays = list((REPO / "tests").glob("r548_shadow_*.py")) + list(REPO.glob("r548_shadow_*.py"))
    strays += list(REPO.glob("*r548_k1b*"))
    assert not strays, strays


def test_z9c_the_worker_bytes_match_the_number_written_on_paper():
    """纸上的进门指纹与本件现读同一枚：交工纸与盘面漂开就红（不许纸一个数、盘另一个数）。"""
    digest = _sha(WORKER_PATH)
    paper = PAPER_PATH.read_text(encoding="utf-8")
    assert digest in paper, (digest, "交工纸里没有出现这枚 sha256")
    assert f"`{digest}`" in paper, digest
