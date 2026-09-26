# -*- coding: utf-8 -*-
"""R218 判据 ②-D（三格之一）+ 判据 ④ 反证钉：报告档翻开关与两族轮询停表。

对判据的哪一条：单号 R218 判据 ② 第一格（``REPORT_LANE_VIA_QUEUE`` 从默认 off 翻 on 之后，
入队/轮询/取回链路离线判得动的部分 + ``QUEUE_POLL_STOPPERS`` 那族停轮子收不收得住每个终态）。

形状：正例读「翻开关成立 + 两族停表收得住后端答得出的每一枚终态」—— 后一半自 R221
（前端名单补 ``dead``）与待并树 R222（适配器认全五枚终态）起才真的成立；反例把前端名单里
的一枚摘掉，红色必须落在本格的 ``frontend_unhandled_final`` 上，另两格一个字不动（上一班
那枚「摘判据① 没红、其实是被判据④ 顺手拦住」的假钉，本单不再犯）。

R245 改钉（09-25，总控预授权）—— 翻掉的钉逐行交代，一行都不含糊：
  - **哪两行**：原 ``:91``（``test_cell_is_red_because_a_final_status_is_never_stopped``
    里那句 ``assert cell["problems"] == ["frontend_deadline_appeared_rerun_the_cost_reading"]``）
    与原 ``:191``（``test_the_pin_has_teeth_in_the_other_direction_too`` 里同一句 ``problems ==``）。
  - **为什么**：那两枚钉钉的是量具自己那句「前端有了截止表 ⇒ "漏停=永不停"这条代价口径
    过期，宁可当场红，让窗前来人重算」（``scripts/r218_switch_rehearsal.py`` 原 :389-392）。
    R245 把"等人重算"换成"重算的公式在件里"：前端从此有 ``frontend_deadline_ms`` 与
    ``frontend_waste_per_stalled_watch_seconds`` 两枚有名读数，与适配器那枚
    ``adapter_waste_per_stalled_watch_seconds`` 对称，且数值**从 ChatPanel.vue 现读**。
    读数交得出来 ⇒ 那枚残红不再成立 ⇒ 两枚钉的原值从"恰等这一条 problem"变成"恰等空表"。
  - **强度只升不降**：两行都还是 ``==`` **恰等**比较（没改成 ``in``、没改成 ``len(...)``、
    没 skip/xfail）。原断言判"本格只许红在这一条"，新断言判"本格一条红都不许有"，
    并且另加：两枚有名读数的现读等式（钉里的值 == 从原件正则现读的值 ⇒ 件里写死数字就红）、
    ``frontend_deadline_gaps`` 恰等空表、出处三跳逐格对判。
  - **预授权之外还动了哪两行**（同属那枚钉，逐字列出，不暗改）：原 ``:88``
    ``assert cell["verdict"] == R.RED`` → ``== R.GREEN``，它是 :91 那枚钉的 verdict 半边，
    留着 RED 等于把本单刚退休的旧口径再钉一遍；原 ``:83-85`` 与 ``:168-170`` 两段注释叙述的
    就是那枚已经消失的残红，留假话在钉里比改注释更糟。**断言一枚没删。**
🔴 反证只加不减：既有断言一枚不删、不放宽。
"""
import re
import hashlib
import importlib.util
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _rehearsal():
    spec = importlib.util.spec_from_file_location(
        "r218_switch_rehearsal_mod", REPO / "scripts" / "r218_switch_rehearsal.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = _rehearsal()

PIN_FILES = R.rehearsal_inputs()  # 由 _CITATIONS 与三格读取点长出，不手抄


def _tree_sha(relatives=PIN_FILES) -> dict:
    return {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in relatives}


def _overlay(tmp_path: Path) -> Path:
    """把本格读到的那几枚文件复制进临时根：反证只作用在副本上，跟踪里的原件一枚不碰。"""
    root = tmp_path / "overlay"
    for rel in PIN_FILES:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target)
    return root


def test_cell_reads_the_flip_and_the_stop_sets():
    cell = R.cell_lane_flip(REPO)
    readings = cell["readings"]
    # 判据 ②-D 的前半：默认关，翻 on 才进队列道（读的是产品谓词本体）
    assert readings["lane_flip"]["default_off"] is True
    assert readings["lane_flip"]["flip_on"] is True
    assert readings["lane_flip"]["flip_off_literal"] is True
    assert readings["lane_flip"]["lane_predicate"] == {
        "report": "report", "REPORT": "", "qa": "", "analysis": "", "": ""}
    # 后半：状态字面与两族停表都从代码里抽出来，不是手抄清单
    assert "dead" in readings["backend_answers"]
    assert readings["final_statuses"] == list(R.FINAL_QUEUE_STATUSES)
    assert set(readings["frontend_http_stoppers"]) == {
        "401:authentication_required", "403:authorization_unavailable",
        "403:permission_denied", "404:resource_not_found"}
    assert readings["citation_drift"] == []


def test_cell_is_red_because_a_final_status_is_never_stopped():
    """本格今天读出的红只剩一枚，而且【不是】停表：两族停表都已收全六枚终态。

    ⚠️ 函数名是本单起点之前那一格红的名字，今天那枚红已经**不在了**（见下面的归因）。
    改钉只许动读数与字面量 ⇒ 名字留在原地，别按名索引的人以为少了一枚用例。

    R234 改钉（09-25）：这里原来钉的三枚读数都被**已并树/待并树的产品改动**收掉了，逐格归因：
      - ``frontend_unhandled_final`` ["dead"] → []  —— R221 并树 ``9850969``，
        ``frontend/src/components/ChatPanel.vue:852`` 把 ``dead`` 收进 ``QUEUE_SETTLED``；
      - ``adapter_unhandled_final`` ["cancelled","dead"] → []  —— 待并树 R222，
        ``scripts/eval_transport_ask_v2.py:888`` 让 ``_poll_queue`` 一次认全四枚非 done 终态；
      - ``frontend_watch_has_no_deadline`` True → False  —— 同一枚 R221，
        ``ChatPanel.vue:860``/``:863`` 的 ``QUEUE_WAIT_DEADLINE_MS``/``MAX_POLLS`` 落进
        ``watchQueueTurn`` 函数体（量具按 ``DEADLINE_TOKENS`` 读到 "Deadline" 两枚）。
    🔴 R245 起本格读 GREEN：原来那枚残红是量具自己那句「前端有了截止表 ⇒ "漏停=永不停"
    这条代价口径过期，宁可当场红，让窗前来人重算」（原 ``scripts/r218_switch_rehearsal.py:389-392``），
    本单已经把它换成有界判据 —— 截止在位且有名读数交得出来就绿，交不出来（缺失 / 为 0 /
    非数 / 无界）换名报红 ``frontend_deadline_cost_reading_unbounded=``，由下面 R245 的
    三枚反证钉各自咬住一侧。
    """
    cell = R.cell_lane_flip(REPO)
    assert cell["verdict"] == R.GREEN
    assert cell["readings"]["frontend_unhandled_final"] == []
    assert cell["readings"]["adapter_unhandled_final"] == []
    assert cell["problems"] == []
    # 适配器那族有截止 ⇒ 不算"永不停"，但每条未终结的轮询各白等一整段 deadline。
    # 🔴 R218 返工订正：上一班这里把 900 × 105 当成代价交出去（那枚乘法的前提是"105 题全部
    # 撞上未终结态"），本件从今天起只交两枚**各自有名**的量：单条白等时长 / 全体撞上的天花板。
    # 天花板是上界不是期望值，所以另钉一枚 flag 与现读题数，谁都别想再把它读成预计代价。
    assert cell["readings"]["adapter_waste_per_stalled_watch_seconds"] == 900.0
    assert cell["readings"]["adapter_deadline_seconds"] == 900.0
    assert cell["readings"]["adapter_deadline_env"] == "EVAL_QUEUE_POLL_SECONDS"
    assert cell["readings"]["question_count_read_from_fixture"] == 105
    assert cell["readings"]["adapter_worst_case_minutes_if_every_question_stalls"] == pytest.approx(1575.0)
    assert cell["readings"]["worst_case_is_upper_bound_not_expectation"] is True
    # 前端那一族今天有了第三枚停法（R221 到点收表）：这条读数翻 False 正是上面那枚残红的因，
    # 而 R245 起它同时是下面两枚有名读数的因 —— 代价口径不再过期，件里就有算式。
    # 🔴 不许拿"每枚未终结轮子白等 900 s"那句旧话替前端报数，也不许把毫秒数抄进件里。
    assert cell["readings"]["frontend_watch_has_no_deadline"] is False
    assert cell["readings"]["frontend_deadline_tokens_seen"]["Deadline"] == 2
    # R245 判据 ①：两枚有名读数进同一个 readings 字典，数值与**原件现读**逐格相等。
    # 这条等式就是"现读不手抄"的证据：件里把毫秒数写死，原件那枚常数一改就红。
    # （钉里出现的 300000 是现测凭证，与 :96 那枚 900.0 同一条规矩；它被上面那两行
    # ``== live_ms`` 拴着，漂了就红，不充当算式。）
    panel_text = (REPO / "frontend/src/components/ChatPanel.vue").read_text(encoding="utf-8")
    live_ms = int(re.search(r"(?m)^const QUEUE_WAIT_DEADLINE_MS = (\d+)$", panel_text).group(1))
    live_poll_ms = int(re.search(r"(?m)^const QUEUE_POLL_MS = (\d+)$", panel_text).group(1))
    assert (live_ms, live_poll_ms) == (300000, 3000), "原件的截止/时钟换了值：本钉跟着现读改"
    assert cell["readings"]["frontend_deadline_ms"] == live_ms
    assert cell["readings"]["frontend_waste_per_stalled_watch_seconds"] == live_ms / 1000.0
    assert cell["readings"]["frontend_deadline_gaps"] == []
    assert cell["readings"]["frontend_poll_ms"] == live_poll_ms
    # 出处三跳逐格对判：读数是从哪一枚比较式、哪一枚上限常数、哪一枚时钟算出来的，全交回来。
    assert cell["readings"]["frontend_deadline_source"] == {
        "counter": "entry.polls", "limit_const": "QUEUE_WAIT_MAX_POLLS",
        "deadline_const": "QUEUE_WAIT_DEADLINE_MS", "clock_const": "QUEUE_POLL_MS",
        "polls_before_stop": live_ms / live_poll_ms,
        "enforcement_line": "if (entry.polls > QUEUE_WAIT_MAX_POLLS) {"}
    # 这把尺只搜两枚停表动作的**原文**（行号用来证先后，不用来证内容）：命中名单停表 +
    # 到点再打一次的 setInterval。🔴 别把这读成"前端只有两枚停法"—— R221 起还有第三枚
    # 到点自停（``ChatPanel.vue:1052`` 的 ``stopAtDeadline``），它不落这两个字面，所以
    # 由上面那枚 ``frontend_watch_has_no_deadline is False`` 单独钉着。
    actions = cell["readings"]["frontend_stop_actions"]
    assert [x[1] for x in actions] == [
        "if (QUEUE_SETTLED.includes(read.status)) stop()",
        "entry.timer = setInterval(tick, QUEUE_POLL_MS)"]
    assert actions[0][0] < actions[1][0]
    # 上一班那枚假口径必须已经消失：仓里不许同时存在两份互相矛盾的代价说法
    assert "adapter_deadline_cost_105q_minutes" not in cell["readings"]


def test_control_overlay_reproduces_the_real_verdict(tmp_path):
    """对照：原样复制的临时根必须复现同一判定，否则下面的红色是复制造出来的假红。

    两族名单今天都已收全六枚终态（R260 给前端名单补 `awaiting_approval`，R259 同日给量具补同一枚）⇒ 缺口读两枚空表（前端一枚归 R221 ``9850969``，
    适配器一枚归待并树 R222 ``scripts/eval_transport_ask_v2.py:888``）。
    """
    overlay = _overlay(tmp_path)
    assert R.frontend_stop_vocabulary(overlay) == R.frontend_stop_vocabulary(REPO)
    assert R.stop_set_gap(R.frontend_stop_vocabulary(overlay)["settled"],
                          R.adapter_stop_vocabulary(overlay)["stops"]) == ([], [])


def test_counter_proof_dropping_one_settled_status_goes_red_here(tmp_path):
    """反证钉（判据 ④）：把前端名单里的一枚终态摘掉 ⇒ 本格必须变红，且红在摘掉的那一枚上。"""
    overlay = _overlay(tmp_path)
    panel = overlay / "frontend/src/components/ChatPanel.vue"
    original = panel.read_text(encoding="utf-8")
    # 🔴 抄本会过期，这里按现值同步：产品那一行自 R260 起是六枚（多 `awaiting_approval`），
    # 拿五枚的旧抄本去 replace 是一枚 no-op —— 那正是本件自己禁的假钉。摘的仍是 expired 这一枚。
    mutated = original.replace(
        "const QUEUE_SETTLED = ['done', 'cancelled', 'failed', 'expired', 'dead', 'awaiting_approval']",
        "const QUEUE_SETTLED = ['done', 'cancelled', 'failed', 'dead', 'awaiting_approval']")
    assert mutated != original, "反证没作用到东西上，这枚钉是空的"
    panel.write_text(mutated, encoding="utf-8")

    before = _tree_sha()
    cell = R.cell_lane_flip(overlay)
    assert cell["verdict"] == R.RED
    assert "expired" in cell["readings"]["frontend_unhandled_final"]
    assert any(p.startswith("frontend_never_stops_on=") for p in cell["problems"])

    # 红色只能落在本格：另两格对着同一枚临时根判，必须维持原判
    other = R.cell_cache_hit(overlay)
    assert other["verdict"] == R.GREEN, f"别格顺手拦住了本钉：{other['problems']}"
    assert R.cell_ruler(overlay)["readings"]["unparsed_shapes"] == []

    # 还原核对：临时根删掉，跟踪里的原件 sha256 逐字不变
    shutil.rmtree(tmp_path)
    assert _tree_sha() == before
    assert (REPO / "frontend/src/components/ChatPanel.vue").read_text(
        encoding="utf-8") == original


def test_the_pin_has_teeth_in_the_other_direction_too(tmp_path):
    """反证钉要能钉回绿：名单收全六枚终态 ⇒ 本格不许再因停表变红（不许靠放宽判据变绿）。

    R234 改钉：``dead`` 自 R221（``9850969``，``ChatPanel.vue:852``）起就在名单里，原来那句
    「把四枚的旧抄本换成五枚」落在今天的原件上是**no-op** ⇒ 一枚不咬人的假钉（本件自己禁）。
    改成**先摘再补**：摘掉必须红在 ``dead`` 上，补回来必须一枚停表红都不剩。
    🔴 R245 起「补回名单」这一格直接全绿：原来那两句"全绿还要另外撤掉截止表"讲的是量具
    一读到前端有截止就拒沿用旧代价口径的那枚残红（原 ``scripts/r218_switch_rehearsal.py:389-392``），
    本单已把它换成有界判据，残红随之消失。撤截止那一半仍然要有牙 —— 现在由
    ``test_counter_evidence_removing_the_deadline_moves_the_cell_to_the_other_side`` 单独钉，
    强度不在这行降（本函数下面那几行原文一条不改，只把 :191 的期望值换成空表）。
    """
    overlay = _overlay(tmp_path)
    panel = overlay / "frontend/src/components/ChatPanel.vue"
    original = panel.read_text(encoding="utf-8")
    lit_full = "const QUEUE_SETTLED = ['done', 'cancelled', 'failed', 'expired', 'dead', 'awaiting_approval']"
    lit_no_dead = "const QUEUE_SETTLED = ['done', 'cancelled', 'failed', 'expired', 'awaiting_approval']"
    stripped = original.replace(lit_full, lit_no_dead)
    assert stripped != original, "反证没作用到东西上，这枚钉是空的"
    panel.write_text(stripped, encoding="utf-8")
    red = R.cell_lane_flip(overlay)
    assert red["readings"]["frontend_unhandled_final"] == ["dead"]
    assert "frontend_never_stops_on=dead" in red["problems"]
    assert red["verdict"] == R.RED

    restored = stripped.replace(lit_no_dead, lit_full)
    assert restored == original, "摘得下补不回：两枚抄本不是同一行，本钉的对照失效"
    panel.write_text(restored, encoding="utf-8")
    cell = R.cell_lane_flip(overlay)
    assert cell["readings"]["frontend_unhandled_final"] == []
    assert "frontend_never_stops_on=dead" not in cell["problems"]
    assert cell["problems"] == []

    deadline_def = ("  const stopAtDeadline = () => {\n"
                    "    queueWaits.value = storeBag(queueWaits, key, true)\n"
                    "    stop()\n"
                    "  }\n")
    deadline_use = ("    if (entry.polls > QUEUE_WAIT_MAX_POLLS) {\n"
                    "      stopAtDeadline()\n"
                    "      return\n"
                    "    }\n")
    no_deadline = original.replace(deadline_def, "").replace(deadline_use, "")
    assert no_deadline != original, "反证没作用到东西上：R221 的截止半条换了形状"
    panel.write_text(no_deadline, encoding="utf-8")
    green = R.cell_lane_flip(overlay)
    assert green["readings"]["frontend_watch_has_no_deadline"] is True
    assert green["problems"] == []
    assert green["verdict"] == R.GREEN
    # R245 顺手把这半条也钉满：撤掉截止 ⇒ 有名读数一起消失，不许留下一个"孤儿秒数"。
    assert green["readings"]["frontend_deadline_ms"] is None
    assert green["readings"]["frontend_waste_per_stalled_watch_seconds"] is None
    assert green["readings"]["frontend_deadline_gaps"] == ["enforcement_not_wired"]
    shutil.rmtree(tmp_path)


# --- R245 反证钉（判据 ④）：新读数的每一侧都要有人咬 ------------------------------------

#: 到点自停那半条在 ``watchQueueTurn`` 里的两处原文（定义 + 那一跳），与上面那枚
#: ``test_the_pin_has_teeth_in_the_other_direction_too`` 用的是同一份抄本 —— 摘的是同一半条。
DEADLINE_DEF = ("  const stopAtDeadline = () => {\n"
                "    queueWaits.value = storeBag(queueWaits, key, true)\n"
                "    stop()\n"
                "  }\n")
DEADLINE_USE = ("    if (entry.polls > QUEUE_WAIT_MAX_POLLS) {\n"
                "      stopAtDeadline()\n"
                "      return\n"
                "    }\n")


def _panel_cell(tmp_path, mutate):
    """反证钉公共骨架：只在临时根上改 ChatPanel.vue，跑 D 格，回来逐枚核 sha256 一字未变。

    🔴 跑前跑后各取一次 ``_tree_sha()`` —— 写法照抄 ``tests/test_r233_undefined_root_names.py``
    里 R236 那枚「反证钉不许动工作树」的自证，另加原件文本逐字对照：本单的数值靠**读**
    前端，不靠改前端。红色还只能落在本格：C 格与 A② 格对着同一枚临时根判，必须维持原判。
    """
    before = _tree_sha()
    overlay = _overlay(tmp_path)
    panel = overlay / "frontend/src/components/ChatPanel.vue"
    original = panel.read_text(encoding="utf-8")
    mutated = mutate(original)
    assert mutated != original, "反证没作用到东西上，这枚钉是空的"
    panel.write_text(mutated, encoding="utf-8")

    cell = R.cell_lane_flip(overlay)
    assert _tree_sha() == before, "反证钉不许写脏工作树"
    assert R.cell_cache_hit(overlay)["verdict"] == R.GREEN, "别格顺手拦住了本钉"
    assert R.cell_ruler(overlay)["readings"]["unparsed_shapes"] == []

    shutil.rmtree(tmp_path)
    assert _tree_sha() == before, "反证钉不许写脏工作树"
    assert (REPO / "frontend/src/components/ChatPanel.vue").read_text(
        encoding="utf-8") == original
    return cell


def test_counter_evidence_removing_the_deadline_moves_the_cell_to_the_other_side(tmp_path):
    """反证钉 (a)（R245 判据 ④）：把前端截止整条摘掉 ⇒ 新读数必须消失，本格回到另一侧。

    摘的是 ``watchQueueTurn`` 里到点自停那半条，模块级常数留在原位 —— 本件读的是"截止有没有
    真装进这族轮询"，写在文件里却没装进去的截止等于没有截止。期望：两枚有名读数一起读 None、
    缺口点名 ``enforcement_not_wired``、``frontend_watch_has_no_deadline`` 改回 True
    （回到"漏停 = 永不停"那一侧），本格一条红都不许有。
    """
    cell = _panel_cell(tmp_path, lambda text: text.replace(DEADLINE_DEF, "")
                       .replace(DEADLINE_USE, ""))
    readings = cell["readings"]
    assert readings["frontend_watch_has_no_deadline"] is True
    assert readings["frontend_deadline_ms"] is None
    assert readings["frontend_waste_per_stalled_watch_seconds"] is None
    assert readings["frontend_deadline_gaps"] == ["enforcement_not_wired"]
    assert readings["frontend_unhandled_final"] == []
    assert cell["problems"] == []
    assert cell["verdict"] == R.GREEN


def test_counter_evidence_unparseable_deadline_goes_red_here(tmp_path):
    """反证钉 (b)（R245 判据 ④）：把 ``frontend_deadline_ms`` 的来源换成不可解析的形状 ⇒ D 格必须红。

    ``const QUEUE_WAIT_DEADLINE_MS = <数字>`` 改成 ``Number.NaN``：函数体里那一跳还在
    （``no_deadline`` 照旧 False），但第三跳读不出一枚十进制数 ⇒ 读数不许交付，本格换名报红，
    红因逐字钉住（``==`` 恰等，不 ``in``、不 ``len``）。
    """
    cell = _panel_cell(tmp_path, lambda text: re.sub(
        r"(?m)^const QUEUE_WAIT_DEADLINE_MS = \d+$",
        "const QUEUE_WAIT_DEADLINE_MS = Number.NaN", text))
    assert cell["readings"]["frontend_watch_has_no_deadline"] is False
    assert cell["readings"]["frontend_deadline_ms"] is None
    assert cell["readings"]["frontend_waste_per_stalled_watch_seconds"] is None
    assert cell["readings"]["frontend_deadline_gaps"] == ["deadline_ms_unreadable"]
    assert cell["verdict"] == R.RED
    assert cell["problems"] == [
        "frontend_deadline_cost_reading_unbounded=deadline_ms_unreadable"]


def test_counter_evidence_unbounded_deadline_limit_goes_red_here(tmp_path):
    """反证钉 (c)（R245 判据 ④）：截止上限换成**无界**形状 ⇒ D 格必须红，且红因是"数不出枚数"。

    把 ``const QUEUE_WAIT_MAX_POLLS = <A> / <B>`` 换成 ``Number.POSITIVE_INFINITY``：轮询时钟
    与到点那一跳的字面都还在，但那枚上限不再是"截止 ÷ 时钟"数出来的枚数 ⇒ 这条轮询的白等
    时长没有界，件里不许报一个秒数冒充它。
    """
    cell = _panel_cell(tmp_path, lambda text: re.sub(
        r"(?m)^const QUEUE_WAIT_MAX_POLLS = .*$",
        "const QUEUE_WAIT_MAX_POLLS = Number.POSITIVE_INFINITY", text))
    assert cell["readings"]["frontend_watch_has_no_deadline"] is False
    assert cell["readings"]["frontend_deadline_ms"] is None
    assert cell["readings"]["frontend_deadline_gaps"] == ["enforcement_not_wired"]
    assert cell["verdict"] == R.RED
    assert cell["problems"] == [
        "frontend_deadline_cost_reading_unbounded=enforcement_not_wired"]


def test_counter_evidence_retyping_the_deadline_moves_the_reading(tmp_path):
    """反证钉 (d)（R245 判据 ①「现读不手抄」）：把原件那枚截止改大 ⇒ 读数必须跟着走。

    🔴 这一枚专打"把毫秒数写成字面量"：件里只要有一处写死秒数，改原件常数就改不动读数，
    本格立刻红在"读数没跟着原件走"上。期望新值 = 原值 + 45 000 ms（等式两边都由原件现读，
    钉里没有第三个数）。
    """
    base_ms = int(re.search(r"(?m)^const QUEUE_WAIT_DEADLINE_MS = (\d+)$", (
        REPO / "frontend/src/components/ChatPanel.vue").read_text(
            encoding="utf-8")).group(1))
    cell = _panel_cell(tmp_path, lambda text: re.sub(
        r"(?m)^(const QUEUE_WAIT_DEADLINE_MS = )(\d+)$",
        lambda row: row.group(1) + str(int(row.group(2)) + 45000), text))
    moved = base_ms + 45000
    readings = cell["readings"]
    assert readings["frontend_deadline_ms"] == moved
    assert readings["frontend_waste_per_stalled_watch_seconds"] == moved / 1000.0
    assert readings["frontend_deadline_gaps"] == []
    assert readings["frontend_deadline_source"]["polls_before_stop"] == moved / readings[
        "frontend_poll_ms"]
    assert cell["problems"] == []
    assert cell["verdict"] == R.GREEN


def test_counter_evidence_deadline_token_drift_is_caught(tmp_path):
    """反证钉 (e)（R245 判据 ②「保留过期就红的纪律」）：改名到 ``DEADLINE_TOKENS`` 认不出 ⇒ 红。

    ``stopAtDeadline`` 换成 ``stopAtWaitLimit``：截止仍真装在轮询里（有名读数照样交得出 300 s），
    但 token 清单说"这一族没有截止" ⇒ 件里同时存着两份互相矛盾的代价口径，必须红在
    ``frontend_deadline_cost_reading_contradicts_no_deadline`` 上，不许叠着报数。
    """
    cell = _panel_cell(tmp_path, lambda text: text.replace("stopAtDeadline", "stopAtWaitLimit"))
    assert cell["readings"]["frontend_watch_has_no_deadline"] is True
    assert cell["readings"]["frontend_deadline_ms"] is not None
    assert cell["readings"]["frontend_deadline_gaps"] == []
    assert cell["verdict"] == R.RED
    assert cell["problems"] == ["frontend_deadline_cost_reading_contradicts_no_deadline"]
