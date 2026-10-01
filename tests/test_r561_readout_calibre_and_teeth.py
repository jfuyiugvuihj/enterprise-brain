# -*- coding: utf-8 -*-
r"""R561 判据④：把「容器里那一遍」的**判读口径**离线钉住（本件一枚容器都不碰）。

来历（账在本件不靠摘要）：R558（甲案投递面，并树 `5477645`）的判据① 只交到「同进程真路由真载荷」
那一半，凭据纸 `docs/testing/r558-queue-lane-piece-delivery.md:41-43` 与 `:174` 明写着「容器＋真 Redis
的那一遍**仍欠**」。R561 交的是能去跑那一遍的量具 `scripts/r561_queue_lane_piece_readout.py`，
而**真窗由总控在开窗条件满足时执行**（跟进单 §143 三 判据 5）。所以本件只做一件事：
把量具的判读口径钉成「读不到就红、不许折成 0」，并且把抄自上游的每一枚字面**现取推导**比回去。

编号映射（🔴 派工词与跟进单的编号不同，本件按派工词落，纸里两处都点名）：

| 派工词 | 跟进单 §143 三 | 本体 |
|---|---|---|
| ① | 1 与 2 的后半 | ≥3 发 processing 且 state==ok 且 chars 递增过／`discarded`＝`truncated`＝0／终态那发不许出现片段键 |
| ② | 3 | provenance 逐字符相等才开窗，不等交「落后几枚＋清单」 |
| ③ | 2 的前半 | 零 bypass／零 unreadable／零重试逐枚点名，`reason` 只许三枚词表内的字 |
| ④ | 4 | 本件：离线夹具喂判读函数，「递增／终态无键／上限为零」三格各有牙，反证 ≥2 把 |
| ⑤ | 5 | 容器那一遍归总控；本件不 import 任何 app 码，也不起任何子进程 |

三条姿势（都是本仓已有的规矩，不是本件新造的）：

1. 🔴 **抄来的字面一律现取推导比对**（同族先例：`tests/test_r400_backfill_ladder_pins.py`、
   `tests/test_r455_gapdoc_coordinates_are_derived.py`）。钉里**没有一处**写死上游的键名、状态词、
   阈值数字或 `file:line` 坐标——全部从 `git show HEAD:` 的那一份字节里当场抠出来再比。
   读不到就抛，绝不折成「没有／为零／通过」。
2. 🔴 **量不到不等于干净**（P-20 那句）。每一格只认三态，`UNMEASURED` 走 rc=2；
   反证刀里有一把专门把「量不到」折成 0，它必须红。
3. 🔴 **本件不碰容器、不碰网络、不起子进程**：所有判读都吃 `tmp_path` 里的夹具存档，
   并且由 `test_the_offline_readout_opens_no_subprocess_and_no_socket` 当场证明它没这个能力。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
TOOL_REL = "scripts/r561_queue_lane_piece_readout.py"
TOOL_PATH = REPO / TOOL_REL
R558_REL = "tests/test_r558_queue_lane_pieces_reach_the_polling_surface.py"

PASS, FAIL, UNMEASURED = "PASS", "FAIL", "UNMEASURED"


# ---------------------------------------------------------------- 量具本体（只读盘上那一份）
def _load_tool():
    spec = importlib.util.spec_from_file_location("r561_readout_tool", str(TOOL_PATH))
    assert spec is not None and spec.loader is not None, "量具件读不到：" + str(TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TOOL = _load_tool()


def _tool_source() -> str:
    """量具在盘上的**那一份字节**（判据④ 的刀就落在这份的副本上，原件全程只读）。"""
    return TOOL_PATH.read_bytes().decode("utf-8")


# ---------------------------------------------------------------- 上游字面：现取推导，不许手抄
def blob(rel: str) -> str:
    """`git show HEAD:<rel>` 的那一份字节：工作树脏不脏都不影响它（R496 那枚钉的病根）。"""
    done = subprocess.run(["git", "show", "HEAD:" + rel], cwd=str(REPO), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    assert done.returncode == 0, "上游那份字节读不到（这不能读成「没有」）：" + rel + "\n" + done.stderr
    return done.stdout


def _tree(rel: str) -> ast.Module:
    return ast.parse(blob(rel).replace("\r\n", "\n"))


def _assigned_dict_keys(func: ast.AST, target: str) -> list:
    """函数体里 `target = {…}` 那一份字面键表（按书写顺序交回）。"""
    hits = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if target in names and isinstance(node.value, ast.Dict):
            hits.append([k.value for k in node.value.keys if isinstance(k, ast.Constant)])
    assert len(hits) == 1, "字面键表 %s 命中 %d 枚（要求恰好 1）" % (target, len(hits))
    return hits[0]


def _module_constants(rel: str, names) -> dict:
    tree = _tree(rel)
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = node.targets[0]
            if isinstance(name, ast.Name) and name.id in tuple(names):
                out[name.id] = ast.literal_eval(node.value)
    missing = [name for name in names if name not in out]
    assert not missing, "%s 里取不到这些顶层常数（读不到就是红，不许当默认值）：%r" % (rel, missing)
    return out


def _string_comparisons(func: ast.AST, subject: str) -> set:
    """函数体里与 `subject` 比过的字符串字面（`==`／`in (...)`／`not in` 全收）。"""
    found = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Compare):
            continue
        if not (isinstance(node.left, ast.Name) and node.left.id == subject):
            continue
        for operand in [node.comparators[0]]:
            if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                found.add(operand.value)
            elif isinstance(operand, (ast.Tuple, ast.List, ast.Set)):
                for item in operand.elts:
                    if isinstance(item, ast.Constant) and isinstance(item.value, str):
                        found.add(item.value)
    assert found, "%s 里没有与 %s 作过比较的字面：上游改形状了，本钉拒绝猜" % (
        getattr(func, "name", "?"), subject)
    return found


def _string_keyword_values(func: ast.AST, keyword: str) -> set:
    found = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == keyword and isinstance(kw.value, ast.Constant) \
                    and isinstance(kw.value.value, str):
                found.add(kw.value.value)
    assert found, "函数体里没有一枚 %s= 字面" % keyword
    return found


def _string_literals(tree_or_func) -> list:
    nodes = ast.walk(tree_or_func)
    return [n.value for n in nodes if isinstance(n, ast.Constant) and isinstance(n.value, str)]


# ============================================================ 上游件名（只有路径，没有坐标）
QUEUE_REL = "app/common/reliable_queue.py"
CHAT_REL = "app/api/v1/chat.py"
WORKER_REL = "deploy/queue_worker.py"
PROBE_REL = "scripts/eval_transport_ask_v2.py"
CONTRACT_REL = "docs/api/contract-v1.md"
COMPOSE_REL = "docker-compose.yml"
R255_REL = "tests/test_r255_env_documents_the_conversion.py"


def _tool_tree() -> ast.Module:
    return ast.parse(_tool_source().replace("\r\n", "\n"))


def _function_in(tree_or_text, name: str):
    tree = tree_or_text if isinstance(tree_or_text, ast.Module) else _tree(tree_or_text)
    found = [node for node in ast.walk(tree)
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    assert len(found) == 1, "名为 %s 的函数应当恰好一枚，实取 %d 枚" % (name, len(found))
    return found[0]


def upstream_piece_keys() -> list:
    """片段读数的键表：从 `piece_readout()` 里那份 `empty = {…}` 字面当场抠。"""
    return _assigned_dict_keys(_function_in(QUEUE_REL, "piece_readout"), "empty")


def upstream_reasons() -> list:
    """产品那枚 `reason` 闭集：从 `piece_readout()` 的关键字实参当场抠，不许手抄。"""
    return sorted(_string_keyword_values(_function_in(QUEUE_REL, "piece_readout"), "reason"))


def upstream_failure_keys() -> list:
    """`failure()` 交回的那一格有哪几枚键：轮询夹具照这份长，绝不自造形状。"""
    func = _function_in(QUEUE_REL, "failure")
    returns = [node for node in ast.walk(func)
               if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)]
    assert len(returns) == 1, "failure() 的返回不止一份字面字典：%d 枚" % len(returns)
    keys = [key.value for key in returns[0].value.keys if isinstance(key, ast.Constant)]
    assert keys, "failure() 的返回里没有字面键表：本钉拒绝猜"
    return keys


def upstream_field_and_its_guard():
    """`stream_pieces` 这个键名，与产品里唯一允许下发它的那枚状态守卫。

    🔴 守卫不是「任何与 status 比过的字面」——轮询面那扇门一共比过三枚状态。本件要的是
    **写了这一格的那一扇 if** 所比的状态：只有它才叫「下发片段的门」。
    """
    func = _function_in(CHAT_REL, "queue_status")
    names = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
                    if isinstance(target.slice.value, str):
                        names.add(target.slice.value)
    assert names, "queue_status 里没有往载荷上写任何字面键：上游改形状了"
    assert TOOL.PIECE_FIELD in names, ("%s 不再由轮询面写下：%r" % (TOOL.PIECE_FIELD, sorted(names)))
    guarded = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.If):
            continue
        writes_field = any(
            isinstance(sub, ast.Assign) and any(
                isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                and t.slice.value == TOOL.PIECE_FIELD for t in sub.targets)
            for sub in ast.walk(node))
        if not writes_field:
            continue
        test = node.test
        assert isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) \
            and test.left.id == "status", "下发片段的门不再与 status 作比：本钉拒绝猜"
        for comp in ast.walk(test.comparators[0]):
            if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                guarded.add(comp.value)
    assert guarded, "找不到写 %s 的那扇状态门：上游改形状了" % TOOL.PIECE_FIELD
    assert len(guarded) == 1, "下发 %s 的门不止一枚状态：%r" % (TOOL.PIECE_FIELD, sorted(guarded))
    return names, guarded


def upstream_stop_words() -> set:
    return _string_comparisons(_function_in(PROBE_REL, "_poll_queue"), "status")


def upstream_kind_words() -> set:
    """上游那把停表量具的 kind 词表：`queued_*` 全族，外加 `approval_failed`。"""
    words = {item for item in _string_literals(_tree(PROBE_REL))
             if re.fullmatch(r"queued_[a-z_]+", item)}
    assert "approval_failed" in blob(PROBE_REL), "上游的 approval_failed 不见了：词表读不到"
    words.add("approval_failed")
    assert words, "kind 词表一枚都读不到：上游那一族改口了，本钉拒绝猜"
    return words


def upstream_route_literals() -> set:
    return {item for item in _string_literals(_tree(PROBE_REL)) if item.startswith("/api/")}


def upstream_caps() -> dict:
    """两枚上限：**名字**从产品里现取，**数值**也从产品里现取（本件一个数字都不抄）。"""
    store = _module_constants(QUEUE_REL, [TOOL.STORE_LIMIT_NAME, TOOL.FLUSH_PIECES_NAME,
                                          TOOL.FLUSH_SECONDS_NAME])
    ledger = _module_constants(WORKER_REL, [TOOL.LEDGER_LIMIT_NAME])
    return {"ledger_value": ledger[TOOL.LEDGER_LIMIT_NAME], "store_value": store[TOOL.STORE_LIMIT_NAME],
            "flush_pieces": store[TOOL.FLUSH_PIECES_NAME], "flush_seconds": store[TOOL.FLUSH_SECONDS_NAME]}


def upstream_env_default(name: str) -> float:
    """`X = float(os.getenv("ENV", "3.0"))` 里那枚默认值：从上游量具当场解出来。"""
    for node in _tree(PROBE_REL).body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name):
            continue
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.Call) and len(sub.args) == 2 \
                    and isinstance(sub.args[1], ast.Constant):
                return float(sub.args[1].value)
        raise AssertionError("%s 的写法不是 os.getenv(名字, 默认值)：本钉拒绝猜" % name)
    raise AssertionError("上游量具里没有 %s 这枚常数" % name)


def contract_section() -> str:
    text = blob(CONTRACT_REL)
    parts = text.split("## Queue lane streaming pieces", 1)
    assert len(parts) == 2, "契约里那一节不见了（R558 的键表就靠它）"
    return parts[1].split("\n## ", 1)[0]


# ================================================= 派生比对：抄上去的字面必须还相等
def test_the_piece_key_table_is_derived_from_the_live_readout():
    """九枚键的名字与**顺序**都必须等于 `piece_readout()` 那份字面键表。"""
    live = upstream_piece_keys()
    assert list(TOOL.PIECE_KEYS) == live, (
        "量具的键表与产品读数不一致：量具 %r ／产品 %r" % (list(TOOL.PIECE_KEYS), live))
    assert len(live) >= 9, "读回来的键表短于一族读数应有的枚数：%r" % (live,)


def test_the_three_states_are_the_stores_three_states_and_nothing_else():
    live = _module_constants(QUEUE_REL, ["PIECE_ABSENT", "PIECE_OK", "PIECE_UNREADABLE"])
    expected = (live["PIECE_ABSENT"], live["PIECE_OK"], live["PIECE_UNREADABLE"])
    assert tuple(TOOL.PIECE_STATES) == expected, (list(TOOL.PIECE_STATES), list(expected))


def test_the_closed_reason_vocab_is_exactly_the_stores_reasons():
    """`reason` 只许那三枚字：多出第四枚就是本件自创口径，钉当场红。"""
    live = set(upstream_reasons())
    assert set(TOOL.PIECE_REASON_VOCAB) == live, (set(TOOL.PIECE_REASON_VOCAB), live)
    assert len(TOOL.PIECE_REASON_VOCAB) == len(live), "词表里有重复字"


def test_the_field_name_and_its_only_guarding_status_are_the_products():
    names, guarded = upstream_field_and_its_guard()
    assert TOOL.PIECE_FIELD in names, (TOOL.PIECE_FIELD, sorted(names))
    assert TOOL.PIECE_FIELD in contract_section(), "契约没给这一格命名：量具就无权读它"
    assert len(guarded) == 1, "轮询面里与 status 比较的字面守卫不止一枚，下发这一格的门不再唯一：%r" % (guarded,)
    guard = next(iter(guarded))
    assert guard == TOOL.LIVE_STATUS, (
        "产品下发片段的状态是 %r，量具认的「正在长」那一态是 %r：只能同一枚" % (guard, TOOL.LIVE_STATUS))
    assert guard not in set(TOOL.TERMINAL_STATUSES), (
        "下发片段的那枚状态 %r 落在终态词表里：那与「终态不许出现片段键」直接矛盾" % guard)


def test_the_stop_words_are_the_pollers_stop_words():
    """五枚终态＋一枚挂起，一枚不多一枚不少（与上游 `_poll_queue` 同一张嘴）。"""
    live = upstream_stop_words()
    mine = set(TOOL.TERMINAL_STATUSES) | {TOOL.PARK_STATUS}
    assert mine == live, ("停表词表与上游不一致：量具多出 %r ／少了 %r" % (mine - live, live - mine))
    assert TOOL.PARK_STATUS not in TOOL.TERMINAL_STATUSES, "挂起不是终态，混进去就把等人读成跑完"


def test_the_three_route_doors_are_the_ones_the_frozen_transport_tool_uses():
    live = upstream_route_literals()
    for name in ("LOGIN_PATH", "ASK_PATH", "APPROVE_PATH", "STATUS_PATH"):
        value = getattr(TOOL, name)
        assert value in live, "%s=%r 不在上游量具走过的门里（%r）" % (name, value, sorted(live))


def test_the_two_cap_names_are_the_live_names_and_the_quoted_numbers_are_the_live_numbers():
    """两枚上限的名字与量具纸上引的数字，都必须等于产品里那两枚常数（一个数字都不许手抄）。"""
    caps = upstream_caps()
    quoted = {int(item) for item in re.findall(
        r"\d+", ast.get_docstring(_function_in(_tool_tree(), "judge_caps")) or "") if int(item) > 10}
    assert quoted == {int(caps["ledger_value"]), int(caps["store_value"])}, (
        "量具 docstring 里的数字 %r 不再是产品里那两枚（账本 %s／存储 %s）："
        "上游改了上限而纸上还写旧数，这就是过期账" % (
            sorted(quoted), caps["ledger_value"], caps["store_value"]))


def _upstream_env_defaults() -> dict:
    """上游那把量具里每一枚 `float(os.getenv(名字, 缺省))`：名与数都现取，不许手抄。"""
    out = {}
    for node in _tree(PROBE_REL).body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            continue
        for sub in ast.walk(node.value):
            if (isinstance(sub, ast.Call) and getattr(sub.func, "attr", getattr(sub.func, "id", "")) == "getenv"
                    and len(sub.args) == 2 and isinstance(sub.args[1], ast.Constant)):
                if not (isinstance(node.value, ast.Call)
                        and getattr(node.value.func, "id", "") == "float"):
                    continue
                try:
                    out[node.targets[0].id] = float(sub.args[1].value)
                except (TypeError, ValueError):
                    #: 只收「个数」那一族 env 缺省（BASE_URL 那种字符串缺省不参与节奏比对）；
                    #: 具体哪一枚必须存在，由用它的钉逐枚点名，不在这里默默放行。
                    continue
    assert out, "上游量具里一枚 env 缺省都读不到：这一格量不到，不许当成「没有这回事」"
    return out


def _cli_float_defaults() -> dict:
    """量具 CLI 上每一枚浮点缺省（--poll-interval／--deadline／--stall／--timeout）。"""
    out = {}
    for node in ast.walk(_function_in(_tool_tree(), "parse_args")):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_argument"):
            continue
        if not (node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            continue
        for kw in node.keywords:
            if (kw.arg == "default" and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, float)):
                out[node.args[0].value] = kw.value.value
    assert out, "parse_args 里没有一枚浮点缺省：节奏这一格读不到就不许交"
    return out


def test_the_cadence_numbers_on_the_cli_are_the_upstream_tools_own_readings():
    """🔴 判据① 的节奏面：3 s 一发／到点／卡死三枚数必须是上游那把量具的读数，不是本件拍的。

    本件只证「这个数在上游确有其事」，不靠行号，也不在本件里写死任何一枚数字。
    """
    live = _upstream_env_defaults()
    defaults = _cli_float_defaults()
    for flag, word in (("--poll-interval", "INTERVAL"), ("--stall", "STALL")):
        carriers = [name for name in live if word in name]
        assert len(carriers) == 1, "%s 该在上游有唯一一枚同名读数，实取 %r" % (flag, carriers)
        assert defaults[flag] == upstream_env_default(carriers[0]), (
            "%s=%r 不再是上游 %s 那枚 env 缺省 %r：客户端节奏改了而量具还按旧数问" % (
                flag, defaults[flag], carriers[0], upstream_env_default(carriers[0])))
    deadline = defaults["--deadline"]
    assert [name for name, value in live.items() if value == deadline], (
        "--deadline 那枚数在上游任何一枚 env 读数里都不存在：那是本件自造的时限")
    assert deadline > defaults["--poll-interval"], "到点比一发还短：那一窗根本来不及问第二发"
    assert defaults["--timeout"] < deadline, (
        "单发 HTTP 超时比整轮到点还长：一发卡死就能把到点那一格顶穿，退不回 rc=2")


def test_the_kind_names_are_all_upstream_names_beyond_the_one_declared_new():
    live = upstream_kind_words()
    mine = {getattr(TOOL, name) for name in ("KIND_POLLED", "KIND_APPROVED", "KIND_NO_BYTES",
                                             "KIND_PARKED")}
    assert mine <= live, "量具用了上游词表之外的 kind：%r" % sorted(mine - live)
    assert TOOL.BYPASS_KIND not in live, "bypass 那枚名是本件新立的，若哪天上游也有了，这条要改口而不是被抹掉"
    assert TOOL.BYPASS_KIND not in {TOOL.KIND_POLLED, TOOL.KIND_NO_BYTES}, "根本没入队不许顶替任何一枚既有 kind"


def test_the_minimum_three_poll_floor_is_the_registered_pin_floor():
    """「至少三发」这枚数是 R558 在册钉里那枚 `len(seen) >= 3`，不是本件拍的。"""
    body = _function_in(R558_REL, "test_the_polling_body_grows_while_the_turn_is_still_running")
    floors = [node.comparators[0].value for node in ast.walk(body)
              if isinstance(node, ast.Compare) and isinstance(node.left, ast.Call)
              and isinstance(node.left.func, ast.Name) and node.left.func.id == "len"
              and isinstance(node.ops[0], ast.GtE)
              and isinstance(node.comparators[0], ast.Constant)
              and isinstance(node.comparators[0].value, int)]
    assert floors, "R558 那枚钉里没读到 len(...) >= N 这一格：本钉拒绝猜下限"
    assert TOOL.MIN_PROCESSING_OK_POLLS in floors, (TOOL.MIN_PROCESSING_OK_POLLS, floors)


def test_the_contract_section_names_every_key_the_readout_answers():
    section = contract_section()
    for key in TOOL.PIECE_KEYS:
        assert "`stream_pieces.%s`" % key in section or "| `%s`" % key % () in section, (
            "契约里没给 stream_pieces.%s 命名：量具无权读这一格" % key)
    for reason in TOOL.PIECE_REASON_VOCAB:
        assert reason in section, "契约里没有这枚 reason：%s 是自创口径" % reason
    assert "processing" in section, "契约没说清这一格只在正在跑的那一态出现"


def _compose_services_with_build() -> set:
    """compose 里带 `build:` 的服务：只在 services 那一段里逐块读，别把 volumes 也算成服务。"""
    text = blob(COMPOSE_REL).replace("\r\n", "\n")
    body = text.split("services:", 1)[1]
    stop = re.search(r"^\S", body, re.M)
    body = body[:stop.start()] if stop else body
    built, current = set(), None
    for line in body.split("\n"):
        named = re.match(r"^  ([A-Za-z0-9_\-]+):\s*$", line)
        if named:
            current = named.group(1)
        elif current and re.match(r"^    build:", line):
            built.add(current)
    assert built, "从 compose 里读不出任何带 build 的服务：本钉拒绝猜"
    return built
def test_the_two_remediation_exits_are_the_composes_and_the_r255_calibre():
    """provenance 不等时只能指这两条出口，且措辞与在册口径同源（判据② 点名的两枚坑）。"""
    compose = blob(COMPOSE_REL)
    built = sorted(_compose_services_with_build())
    assert built, "从 compose 里读不出带 build 的服务：本钉拒绝猜"
    assert "backend" not in built, (
        "compose 现在给 backend 也配上 build 了：那句「不要 docker compose build backend」得改口，"
        "读不到就不许继续交旧出口（实取：%r）" % (built,))
    assert TOOL.REMEDIATION_RECREATE in compose or (
        "--env-file" in TOOL.REMEDIATION_RECREATE and "up -d" in TOOL.REMEDIATION_RECREATE
        and "--force-recreate" in TOOL.REMEDIATION_RECREATE), TOOL.REMEDIATION_RECREATE
    assert "--force-recreate" in blob(R255_REL), "在册 R255 那枚钉已不再钉这条口径，本件的引据过期"
    assert "No services to build" in TOOL.REMEDIATION_NOT_BUILD or "build" in TOOL.REMEDIATION_NOT_BUILD
    assert TOOL.IMAGE in compose, "镜像名不在 compose 里：出口指错了对象"
    assert "migrate" in built, ("带 build 的服务里读不到 migrate：那句「backend 与 migrate 共用同一枚镜像」要改口：%r" % (built,))


# ==================================================================== 离线夹具（存档面）


def _piece(state: str, **over) -> dict:
    """造一份片段读数：键与顺序**逐枚取自上游派生出来的那张键表**，夹具不自造形状。"""
    defaults = {"absent": "absent", "ok": "ok", "unreadable": "unreadable"}
    face = dict(zip(TOOL.PIECE_KEYS,
                    [defaults[state], "", 0, 0, 0, 0, 0, [], ""]))
    assert set(face) == set(TOOL.PIECE_KEYS), "夹具的键表与量具不一致：本件的夹具在自造形状"
    face.update(over)
    return face


def _failure(attempts: int = 1, last_error=None) -> dict:
    """轮询载荷里那一枚 `failure`：键表逐枚取自产品的 `failure()`，本件不自造形状。

    🔴 判读只碰它自己从这份键表里读走的那几枚（见 test_the_readout_reads_only_the_failure_keys_it_claims）；
    剩下那枚填什么都不参与判词，填 0 只为把形状对齐产品，不是从上游抄来的读数。
    """
    keys = upstream_failure_keys()
    values = {"attempts": attempts, "last_error": last_error}
    for key in keys:
        values.setdefault(key, 0)
    return {key: values[key] for key in keys}


def _body(status: str, piece=None, **extra) -> dict:
    body = {"status": status, "request_id": "req-r561-offline", "failure": _failure()}
    if piece is not None:
        body[TOOL.PIECE_FIELD] = piece
    body.update(extra)
    return body


def _archive(tmp_path, faces, head_over=None, sub: str = "window"):
    """按 `Capture` 的正经写路数落一份存档，再**从盘上读回来**交回 (rows, head, dir)。

    🔴 判读吃的是读回来的那一份，不是内存里的那一份：凭据面（逐发原文＋索引）必须被走到，
    否则这一族钉只证了判读函数，证不了「存档能重放出同一份判读」。
    """
    out = Path(tmp_path) / sub
    cap = TOOL.Capture(out)
    cursor = 0
    for status, piece, extra in faces:
        body = _body(status, piece, **(extra or {}))
        cap.write_poll(sent_at="2026-10-01 18:00:00", since=cursor, http_status=200,
                       raw=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                       body=body, status=status)
        if isinstance(piece, dict):
            cursor = int(piece.get("cursor") or 0)
    head = {"asked_at": "2026-10-01 18:00:00", "request_id": "req-r561-offline",
            "ask_events": ["queued", "done"], "final_kind": TOOL.KIND_POLLED,
            "blips": 0, "relogins": 0, "approval_rounds": 0, "wait_ms": 1234.5,
            "interval_ms": 3000.0,
            "provenance": {"verdict": PASS, "value": {"host_resolved": "f" * 40},
                           "note": "钉住用夹具读数"}}
    head.update(head_over or {})
    cap.write_head(head)
    return TOOL.load_capture(out), head, out


_GROWING = [("processing", _piece("ok", text="一二三", cursor=1, pieces=3, chars=3), {}),
            ("processing", _piece("ok", text="四五六", cursor=2, pieces=6, chars=6), {}),
            ("processing", _piece("ok", text="七八九", cursor=3, pieces=9, chars=9), {}),
            ("done", None, {"result": "整篇报告正文"})]

#: 🔴 下面每一枚都是「判读钉与反证刀共用」的那一份坏夹具：刀不许自己另造一形，
#: 否则它咬的就不是在册钉当场看着的那个东西（同族先例：R558 那把 backfill 刀）。
_FLAT = [("processing", _piece("ok", cursor=n, chars=7, pieces=7), {})
         for n in (1, 2, 3)] + [("done", None, {"result": "x"})]
_NOPIECES = [("processing", None, {}), ("processing", None, {}),
             ("done", None, {"result": "x"})]
_TERMINAL_LEAK = _GROWING[:3] + [
    ("done", _piece("ok", text="整篇", cursor=3, pieces=9, chars=9), {"result": "整篇报告正文"})]
_INVENTED_FACE = _piece("unreadable", reason="batch_froze_over_nicely")
_INVENTED = [("processing", _INVENTED_FACE, {})] + _GROWING[1:]
_BYPASS_HEAD = {"ask_events": ["done"], "request_id": ""}
_PARKED_HEAD = {"final_kind": TOOL.KIND_PARKED}
_NO_PROV_HEAD = {"provenance": None}


# ============================== 判据① 那一格：递增（跟进单 §143 三 把它归 1）
def test_a_growing_lane_passes_and_names_every_poll(tmp_path):
    rows, head, _ = _archive(tmp_path, _GROWING)
    cell = TOOL.judge_growing(rows)
    assert cell["verdict"] == PASS, cell
    assert cell["value"]["processing_ok_polls"] >= TOOL.MIN_PROCESSING_OK_POLLS, cell
    for item in cell["evidence"]:
        assert {"index", "chars", "cursor"} <= set(item), item
    assert TOOL.judge_terminal(rows)["verdict"] == PASS, TOOL.judge_terminal(rows)


def test_a_backfill_at_terminal_is_red_not_growing(tmp_path):
    """R558 反证刀 backfill 的那一形：过程中每一发都读不到字，终态一次给全 ⇒ 必须红。"""
    rows, head, _ = _archive(
        tmp_path,
        [("processing", _piece("absent"), {}), ("processing", _piece("absent"), {}),
         ("processing", _piece("absent"), {}),
         ("done", _piece("ok", text="整篇", cursor=1, pieces=24, chars=880),
          {"result": "整篇报告正文"})], sub="backfill")
    cell = TOOL.judge_growing(rows)
    assert cell["verdict"] == FAIL, cell
    assert cell["value"]["processing_ok_polls"] < TOOL.MIN_PROCESSING_OK_POLLS, cell


def test_three_polls_that_never_move_are_red(tmp_path):
    rows, _, _ = _archive(tmp_path, _FLAT, sub="flat")
    cell = TOOL.judge_growing(rows)
    assert cell["verdict"] == FAIL, cell
    assert "递增" in cell["note"], cell["note"]


def test_characters_that_grow_while_the_cursor_freezes_are_red(tmp_path):
    """游标不动而字数在动：客户端下一发会重拿同一截字——那一形不是递增。"""
    rows, _, _ = _archive(tmp_path,
                          [("processing", _piece("ok", cursor=1, chars=n, pieces=n), {})
                           for n in (3, 6, 9)] + [("done", None, {"result": "x"})],
                          sub="mixed")
    cell = TOOL.judge_growing(rows)
    assert cell["verdict"] == FAIL, cell
    assert "同涨同停" in cell["note"], cell["note"]


def test_fewer_ok_polls_than_the_registered_floor_is_red(tmp_path):
    rows, _, _ = _archive(tmp_path,
                          [("processing", _piece("ok", cursor=1, chars=4, pieces=4), {}),
                           ("processing", _piece("ok", cursor=2, chars=8, pieces=8), {}),
                           ("done", None, {"result": "x"})], sub="floor")
    assert TOOL.judge_growing(rows)["verdict"] == FAIL


def test_an_ok_face_with_an_empty_delta_is_still_a_real_reading(tmp_path):
    """🔴 本件与 R558 在册钉的唯一一处有意不同：容器每 3 s 一发，`text` 为空是契约允许的。

    契约 R558 节原话：``text`` 是 "legitimately empty when `ok` and nothing new arrived since
    the cursor"。把「末发 text 非空」那格从同进程钉照搬过来，就会把节奏差读成假红。
    """
    rows, _, _ = _archive(tmp_path,
                          [("processing", _piece("ok", text="", cursor=1, chars=4, pieces=4), {}),
                           ("processing", _piece("ok", text="", cursor=2, chars=8, pieces=8), {}),
                           ("processing", _piece("ok", text="尾巴", cursor=3, chars=12, pieces=12), {}),
                           ("done", None, {"result": "x"})], sub="emptydelta")
    assert TOOL.judge_growing(rows)["verdict"] == PASS


# ============================== 判据①/② 那两枚上限（派工词归 ①，跟进单归 2）
def test_both_caps_at_zero_passes_and_reports_what_was_measured(tmp_path):
    rows, _, _ = _archive(tmp_path, _GROWING, sub="caps-pass")
    cell = TOOL.judge_caps(rows)
    assert cell["verdict"] == PASS, cell
    assert cell["value"]["max_discarded"] == 0 and cell["value"]["max_truncated"] == 0, cell
    assert cell["value"]["polls_with_pieces"] >= TOOL.MIN_PROCESSING_OK_POLLS, cell["value"]


def test_a_nonzero_ledger_cap_is_red_and_is_read_as_truncation_not_silence(tmp_path):
    caps = upstream_caps()
    rows, _, _ = _archive(tmp_path,
                          [("processing", _piece("ok", cursor=n, chars=n * 3, discarded=caps["ledger_value"]), {})
                           for n in (1, 2, 3)] + [("done", None, {"result": "x"})],
                          sub="cap-discard")
    cell = TOOL.judge_caps(rows)
    assert cell["verdict"] == FAIL, cell
    assert "截断" in cell["note"] or "按截断读" in cell["note"], cell["note"]
    assert cell["value"]["max_discarded"] == int(caps["ledger_value"]), cell["value"]
    assert cell["value"]["nonzero_polls"], cell["value"]


def test_the_store_cap_is_a_separate_number_from_the_ledger_cap(tmp_path):
    """两枚上限不许混成一枚：一枚说内存丢了片，一枚说增量表停止存正文。"""
    rows, _, _ = _archive(tmp_path,
                          [("processing", _piece("ok", cursor=n, chars=n * 3, truncated=1), {})
                           for n in (1, 2, 3)] + [("done", None, {"result": "x"})],
                          sub="cap-store")
    cell = TOOL.judge_caps(rows)
    assert cell["verdict"] == FAIL, cell
    assert cell["value"]["max_truncated"] == 1 and cell["value"]["max_discarded"] == 0, cell["value"]


def test_a_lane_that_answered_nothing_about_pieces_is_unmeasured_not_zero(tmp_path):
    """🔴 一发片段读数都没取到＝量不到，绝不能读成「discarded 与 truncated 都是 0」。"""
    rows, head, _ = _archive(tmp_path, _NOPIECES, sub="nopieces")
    caps = TOOL.judge_caps(rows)
    assert caps["verdict"] == UNMEASURED, caps
    assert "不是" in caps["note"] and "0" in caps["note"], caps["note"]
    assert TOOL.overall([caps]) == 2, "量不到被折进退出码 0/1 了"


# ====================== 判据① 那一格：终态不许出现片段键（跟进单把它归 2 的后半）
def test_a_terminal_face_without_the_piece_field_passes(tmp_path):
    rows, _, _ = _archive(tmp_path, _GROWING, sub="terminal-pass")
    cell = TOOL.judge_terminal(rows)
    assert cell["verdict"] == PASS, cell
    assert cell["value"]["terminal_status"] == TOOL.TERMINAL_STATUSES[0], cell["value"]


def test_a_terminal_face_carrying_the_piece_field_is_red(tmp_path):
    """这一形就是把增量面当成终态正文的第二份副本——判据① 明写终态那发不许出现这一格。"""
    rows, _, _ = _archive(tmp_path, _TERMINAL_LEAK, sub="terminal-leak")
    cell = TOOL.judge_terminal(rows)
    assert cell["verdict"] == FAIL, cell
    assert cell["value"]["wrong_carriers"], cell["value"]


def test_a_queued_face_carrying_the_piece_field_is_red_too(tmp_path):
    """不是 processing 的每一发都不许多这一格：契约原话是 absent for queued/awaiting/done。"""
    rows, _, _ = _archive(
        tmp_path,
        [("queued", _piece("ok", text="不该有", cursor=1, pieces=1, chars=3), {})] + _GROWING[1:],
        sub="queued-leak")
    assert TOOL.judge_terminal(rows)["verdict"] == FAIL


def test_a_window_that_never_read_a_terminal_face_is_unmeasured(tmp_path):
    rows, head, _ = _archive(tmp_path, _GROWING[:3], {"final_kind": "queued_stalled"},
                             sub="no-terminal")
    cell = TOOL.judge_terminal(rows)
    assert cell["verdict"] == UNMEASURED, cell
    assert "不许折成通过" in cell["note"] or "无从判定" in cell["note"], cell["note"]
    assert TOOL.judge(rows, head)["rc"] == 2, TOOL.judge(rows, head)["rc"]


# ============ 判据③：bypass／unreadable／重试 三枚计数逐枚点名（跟进单把它归 2 的前半）
def test_a_clean_run_passes_the_three_counts_and_says_it_measured_them(tmp_path):
    rows, head, _ = _archive(tmp_path, _GROWING, sub="counts-clean")
    cell = TOOL.judge_counts(rows, head)
    assert cell["verdict"] == PASS, cell
    value = cell["value"]
    assert value["bypass"] is False and value["unreadable_polls"] == [] \
        and value["invented_reasons"] == [] and value["retried_polls"] == [], value
    assert value["retry_measurable"] is True, value


def test_a_turn_that_never_entered_the_queue_is_named_bypass_not_zero_polls(tmp_path):
    rows, head, _ = _archive(tmp_path, _GROWING, _BYPASS_HEAD, sub="bypass")
    cell = TOOL.judge_counts(rows, head)
    assert cell["verdict"] == FAIL, cell
    assert cell["value"]["bypass"] is True, cell["value"]
    assert TOOL.BYPASS_KIND in cell["evidence"][0]["bypass"]["named"], cell["evidence"]
    assert "bypass" in cell["note"], cell["note"]


def test_an_unreadable_batch_is_a_bad_reading_not_a_missing_reading(tmp_path):
    reason = upstream_reasons()[0]
    rows, head, _ = _archive(
        tmp_path,
        [("processing", _piece("unreadable", reason=reason), {})] + _GROWING[1:],
        sub="unreadable")
    cell = TOOL.judge_counts(rows, head)
    assert cell["verdict"] == FAIL, cell
    assert cell["value"]["unreadable_polls"] == [1], cell["value"]
    assert cell["value"]["invented_reasons"] == [], cell["value"]


def test_a_reason_outside_the_closed_vocab_is_named_a_new_calibre(tmp_path):
    """第四枚 reason 出现＝本件自创口径：判 FAIL 并点名，绝不判「没读到读数」。"""
    assert len(TOOL.PIECE_REASON_VOCAB) == len(upstream_reasons()), "词表与上游不等，上一格已红"
    rows, head, _ = _archive(tmp_path, _INVENTED, sub="invented")
    cell = TOOL.judge_counts(rows, head)
    assert cell["verdict"] == FAIL, cell
    invented = cell["value"]["invented_reasons"]
    assert len(invented) == 1 and invented[0]["reason"] == "batch_froze_over_nicely", invented
    assert "自创口径" in cell["note"], cell["note"]


def test_a_second_attempt_is_a_retry_and_a_non_empty_error_is_a_retry(tmp_path):
    rows, head, _ = _archive(
        tmp_path,
        [("processing", _piece("ok", cursor=1, chars=3), {"failure": _failure(attempts=2)}),
         ("processing", _piece("ok", cursor=2, chars=6), {}),
         ("processing", _piece("ok", cursor=3, chars=9), {}),
         ("done", None, {"result": "x"})], sub="retry")
    cell = TOOL.judge_counts(rows, head)
    assert cell["verdict"] == FAIL, cell
    assert cell["value"]["retried_polls"] == [1], cell["value"]
    assert "重试" in cell["note"], cell["note"]


def test_no_failure_reading_at_all_is_unmeasured_not_zero_retries(tmp_path):
    rows, head, _ = _archive(tmp_path, _GROWING, {"retry_face": "absent"}, sub="no-retry-face")
    stripped = []
    for row in rows:
        body = dict(row["body"])
        body.pop("failure", None)
        copy = dict(row)
        copy["body"] = body
        copy["raw"] = json.dumps(body, ensure_ascii=False).encode("utf-8")
        stripped.append(copy)
    cell = TOOL.judge_counts(stripped, head)
    assert cell["verdict"] == UNMEASURED, cell
    assert cell["value"]["retry_measurable"] is False, cell["value"]
    assert "量不到" in cell["note"], cell["note"]


def test_a_genuine_bad_reading_outranks_a_missing_reading(tmp_path):
    """优先级写死：坏读数与量不到同时在场时判 FAIL（量到了坏东西不能躲进 2）。"""
    rows, head, _ = _archive(tmp_path, _GROWING, _BYPASS_HEAD, sub="both")
    stripped = []
    for row in rows:
        body = dict(row["body"])
        body.pop("failure", None)
        copy = dict(row)
        copy["body"] = body
        stripped.append(copy)
    cell = TOOL.judge_counts(stripped, head)
    assert cell["verdict"] == FAIL, cell


# ============================ 账格：停在「没有正文」那一族的窗，形状读数不可采信
def test_a_window_that_stopped_at_the_park_fails_its_own_bookkeeping(tmp_path):
    rows, head, _ = _archive(tmp_path, _GROWING, {"final_kind": TOOL.KIND_PARKED}, sub="parked")
    cell = TOOL.judge_bookkeeping(rows, head)
    assert cell["verdict"] == FAIL, cell
    assert cell["value"]["final_kind"] == TOOL.KIND_PARKED, cell["value"]


def test_a_window_that_never_took_a_final_account_is_unmeasured(tmp_path):
    rows, head, _ = _archive(tmp_path, _GROWING, {"final_kind": ""}, sub="no-final")
    assert TOOL.judge_bookkeeping(rows, head)["verdict"] == UNMEASURED


def test_a_window_that_ran_with_no_approval_is_polled_and_one_that_waited_is_approved(tmp_path):
    """R447 那枚口径：「一次读回正文」与「等了人批准才读回正文」两形分开有名，不许混。"""
    rows, head, _ = _archive(tmp_path, _GROWING, sub="kind-split")
    assert TOOL.judge_bookkeeping(rows, head)["verdict"] == PASS
    waited = dict(head)
    waited["approval_rounds"] = 1
    waited["final_kind"] = TOOL.KIND_APPROVED
    assert TOOL.judge_bookkeeping(rows, waited)["verdict"] == PASS
    for kind in (TOOL.KIND_NO_BYTES, "queued_deadline", "queued_no_status", "queued_stalled",
                 "approval_failed", "queued_cancelled", "queued_dead", "queued_expired",
                 "queued_failed"):
        bad = dict(head)
        bad["final_kind"] = kind
        assert TOOL.judge_bookkeeping(rows, bad)["verdict"] == FAIL, kind


# ==================================== 退出码那一格（三态不许互相顶替）
def test_the_rc_ladder_never_folds_a_missing_reading_into_zero(tmp_path):
    rows, head, _ = _archive(tmp_path, _GROWING, sub="rc")
    report = TOOL.judge(rows, head)
    assert report["rc"] == 0, report["cells"]
    assert list(report["cells"]) == list(TOOL.CELLS), "六格的名字与顺序是本单唯一的叫法表"
    assert TOOL.overall([{"verdict": PASS}] * 6) == 0
    assert TOOL.overall([{"verdict": PASS}, {"verdict": FAIL}]) == 1
    assert TOOL.overall([{"verdict": PASS}, {"verdict": UNMEASURED}]) == 2
    assert TOOL.overall([{"verdict": FAIL}, {"verdict": UNMEASURED}]) == 2, \
        "量不到被一次 FAIL 顶掉了：交回里读不出「这一格压根没量」"


# ============================ 判据②：provenance（全用桩，本件一次容器都不碰）
HOST_FULL = "c" * 40
OTHER_FULL = "d" * 40
GIT_ROUTE = "git rev-parse HEAD"
BUILD_ROUTE = "/app/BUILD_INFO"


def _stub(monkeypatch, replies):
    """把量具唯一那条外部命令出口换成查表桩；查不到就抛（不许折成「没有输出＝干净」）。"""
    calls = []

    def _run(cmd, **kw):
        argv = [str(part) for part in cmd]
        calls.append(argv)
        for want, reply in replies:
            if argv[: len(want)] == want:
                return reply if isinstance(reply, tuple) else (0, reply)
        raise AssertionError("量具问了一条本钉没准备的命令（这一格不许折成空读数）：" + repr(argv))

    monkeypatch.setattr(TOOL, "run", _run)
    return calls


def _replies(container, *, git=None, build=None, label=None, host=HOST_FULL):
    """查表桩的默认账：三条读数路都要有回话，没准备的那条交「这条路量不到」，不交空读数。"""
    table = [(["git", "rev-parse", "HEAD"], host),
             (["git", "rev-parse", host + "^{commit}"], host)]
    table.append((["docker", "exec", container, "git"],
                  git if git else (128, "fatal: not a git repository")))
    table.append((["docker", "exec", container, "cat", BUILD_ROUTE],
                  build if build is not None else (1, "No such file or directory")))
    if isinstance(build, str):
        stamp = build.split("=", 1)[1].strip()
        table.append((["git", "rev-parse", stamp + "^{commit}"], stamp))
    table.append((["docker", "image", "inspect"], label if label else (0, "<no value>")))
    if isinstance(label, str):
        table.append((["git", "rev-parse", label.strip() + "^{commit}"], label.strip()))
    return table


def _all_silent(container):
    return _replies(container, git=(128, "fatal: not a git repository"),
                    build=(128, "No such file or directory"), label=(0, "<no value>"))


def test_the_two_containers_the_image_is_made_of_are_named_from_the_compose():
    """两枚容器名不许是手抄的：项目名与服务名都从 compose 现取（片段是 worker 产的、增量面在 backend）。"""
    compose = blob(COMPOSE_REL)
    project = re.search(r"^name:\s*(\S+)\s*$", compose, re.M)
    assert project, "compose 里读不到项目名：本钉拒绝猜容器名"
    prefix = project.group(1)
    services = set(re.findall(r"^  ([a-z_][\w-]*):\s*$", compose.split("services:", 1)[1]
                              .split("\nvolumes:")[0], re.M))
    assert {"backend", "worker"} <= services, sorted(services)
    for container in TOOL.CONTAINERS:
        assert container.startswith(prefix + "-") and container.endswith("-1"), container
        assert container.split("-")[len(prefix.split("-"))] in services, container
    assert len(set(TOOL.CONTAINERS)) == 2, TOOL.CONTAINERS


def test_the_image_label_and_the_build_stamp_are_the_dockerfiles_own_words():
    docker = blob("Dockerfile")
    assert "LABEL " + TOOL.LABEL in docker, (TOOL.LABEL, "Dockerfile 里那枚 label 改口了")
    assert "revision=" in docker and "BUILD_INFO" in docker, "BUILD_INFO 的 revision= 前缀改口了"
    compose = blob(COMPOSE_REL)
    assert TOOL.IMAGE in compose, "镜像名不在 compose 里：provenance 问的是另一枚镜像"


def test_three_silent_routes_answer_unmeasured_and_refuse_to_open(monkeypatch):
    """容器里那三条路全哑 ⇒ UNMEASURED 并拒绝开窗：既不是「落后」，也不是「干净」。"""
    table = []
    for container in TOOL.CONTAINERS:
        table.extend(_all_silent(container))
    _stub(monkeypatch, table)
    gate = TOOL.provenance_gate()
    assert gate["verdict"] == UNMEASURED, gate
    assert "量不到" in gate["note"], gate["note"]
    for container in TOOL.CONTAINERS:
        entry = gate["value"]["containers"][container]
        assert entry["state"] == UNMEASURED, entry
        assert len(entry["routes_tried"]) == 3, "三条路没逐枚试完就下结论：%r" % (entry,)
        assert [item["route"] for item in entry["routes_tried"]] == [GIT_ROUTE, BUILD_ROUTE,
                                                                      TOOL.LABEL], entry
    cell = TOOL.judge_provenance({"provenance": gate})
    assert cell["verdict"] == UNMEASURED and TOOL.overall([cell]) == 2, cell


def test_an_abbreviated_container_rev_is_resolved_before_the_character_test(monkeypatch):
    """缩写号必须先解成全 40 位再逐字符比；拿 7 位短号直接相等就是假绿。"""
    table = [(["git", "rev-parse", "HEAD"], HOST_FULL),
             (["git", "rev-parse", HOST_FULL + "^{commit}"], HOST_FULL)]
    for container in TOOL.CONTAINERS:
        table.append((["docker", "exec", container, "git"], HOST_FULL[:7]))
        table.append((["git", "rev-parse", HOST_FULL[:7] + "^{commit}"], HOST_FULL))
    _stub(monkeypatch, table)
    gate = TOOL.provenance_gate()
    assert gate["verdict"] == PASS, gate
    for container in TOOL.CONTAINERS:
        entry = gate["value"]["containers"][container]
        assert entry["raw_rev"] == HOST_FULL[:7] and entry["resolved_rev"] == HOST_FULL, entry
        assert entry["equal_chars"] == len(HOST_FULL), entry


def test_a_stale_image_is_refused_and_reports_how_far_behind(monkeypatch):
    table = [(["git", "rev-parse", "HEAD"], HOST_FULL),
             (["git", "rev-parse", HOST_FULL + "^{commit}"], HOST_FULL),
             (["git", "rev-parse", OTHER_FULL + "^{commit}"], OTHER_FULL),
             (["git", "merge-base", "--is-ancestor", OTHER_FULL, "HEAD"], (0, "")),
             (["git", "rev-list", "--count", OTHER_FULL + "..HEAD"], "7\n"),
             (["git", "log", "--oneline", OTHER_FULL + "..HEAD"], "aaaa one\nbbbb two\n"),
             (["git", "diff", "--name-only", OTHER_FULL + "..HEAD", "--", "app", "scripts",
               "deploy", "migrations"], "app/api/v1/chat.py\n")]
    for container in TOOL.CONTAINERS:
        table.append((["docker", "exec", container, "git"], OTHER_FULL))
    calls = _stub(monkeypatch, table)
    gate = TOOL.provenance_gate()
    assert gate["verdict"] == FAIL, gate
    for container in TOOL.CONTAINERS:
        entry = gate["value"]["containers"][container]
        assert entry["state"] == FAIL, entry
        assert TOOL.REMEDIATION_RECREATE in entry["note"], entry["note"]
        assert "No services to build" in entry["note"], entry["note"]
        divergence = entry["divergence"]
        assert divergence["commits_behind"] == "7", divergence
        assert divergence["is_ancestor"] is True, divergence
        assert len(divergence["commits"]) == 2, divergence
        assert divergence["image_inputs_touched"] == ["app/api/v1/chat.py"], divergence
    assert any("rev-list" in " ".join(argv) for argv in calls), "落后几枚没现取，是抄的"


def test_the_build_info_stamp_is_the_second_route_and_the_label_the_third(monkeypatch):
    table = [(["git", "rev-parse", "HEAD"], HOST_FULL),
             (["git", "rev-parse", HOST_FULL + "^{commit}"], HOST_FULL)]
    for container in TOOL.CONTAINERS:
        table.append((["docker", "exec", container, "git"], (128, "fatal: not a git repository")))
        table.append((["docker", "exec", container, "cat", BUILD_ROUTE],
                      "revision=%s\nbuilt_at=2026-10-01T00:00:00Z\n" % HOST_FULL))
    _stub(monkeypatch, table)
    read = TOOL.container_head(TOOL.CONTAINERS[0])
    assert read["route"] == TOOL.ROUTE_BUILD_INFO and read["rev"] == HOST_FULL, read
    assert TOOL.provenance_gate()["verdict"] == PASS
    table = [(["git", "rev-parse", "HEAD"], HOST_FULL),
             (["git", "rev-parse", HOST_FULL + "^{commit}"], HOST_FULL)]
    for container in TOOL.CONTAINERS:
        table.append((["docker", "exec", container, "git"], (128, "fatal: not a git repository")))
        table.append((["docker", "exec", container, "cat", BUILD_ROUTE], (1, "no such file")))
        table.append((["docker", "image", "inspect"], HOST_FULL))
    _stub(monkeypatch, table)
    read = TOOL.container_head(TOOL.CONTAINERS[0])
    assert read["route"] == TOOL.ROUTE_LABEL, read
    assert TOOL.provenance_gate()["verdict"] == PASS


def test_an_unknown_stamp_is_never_read_as_a_head(monkeypatch):
    """BUILD_INFO 里那枚 `revision=unknown`（没传 GIT_SHA 的旧做法）是「量不到」，不是「新镜像」。"""
    table = []
    for container in TOOL.CONTAINERS:
        table.extend(_replies(container, build=(0, "revision=unknown\nbuilt_at=x\n")))
    _stub(monkeypatch, table)
    gate = TOOL.provenance_gate()
    assert gate["verdict"] == UNMEASURED, gate
    for container in TOOL.CONTAINERS:
        entry = gate["value"]["containers"][container]
        assert entry["raw_rev"] == "" and entry["route"] == "", entry
    for stamp in ("latest", "v1.2", "main"):
        table = []
        for container in TOOL.CONTAINERS:
            table.extend(_replies(container, build="revision=%s\nbuilt_at=x\n" % stamp))
        _stub(monkeypatch, table)
        gate = TOOL.provenance_gate()
        assert gate["verdict"] == UNMEASURED, (stamp, gate["verdict"])
        for container in TOOL.CONTAINERS:
            assert gate["value"]["containers"][container]["raw_rev"] == "", (stamp, container)


def test_a_host_head_that_cannot_be_read_never_knocks_on_the_containers(monkeypatch):
    calls = _stub(monkeypatch, [(["git", "rev-parse", "HEAD"], (128, "fatal: not a valid object"))])
    gate = TOOL.provenance_gate()
    assert gate["verdict"] == UNMEASURED, gate
    assert not [argv for argv in calls if argv[0] == "docker"], \
        "主树 HEAD 都没读到就去敲容器：%r" % (calls,)
    assert TOOL.judge_provenance({"provenance": gate})["verdict"] == UNMEASURED


def test_the_head_without_a_provenance_reading_at_all_is_unmeasured(tmp_path):
    rows, head, _ = _archive(tmp_path, _GROWING, {"provenance": None}, sub="no-prov")
    assert TOOL.judge_provenance(head)["verdict"] == UNMEASURED
    assert TOOL.judge_provenance({})["verdict"] == UNMEASURED
    assert TOOL.judge(rows, head)["rc"] == 2, "没 provenance 也能出 0：那道闸是空的"


def test_the_tool_knocks_on_no_external_door_but_the_three_read_routes(monkeypatch):
    table = []
    for container in TOOL.CONTAINERS:
        table.extend(_replies(container, git=HOST_FULL))
    calls = _stub(monkeypatch, table)
    TOOL.provenance_gate()
    for argv in calls:
        assert argv[0] in ("git", "docker"), argv
        if argv[0] == "docker":
            assert argv[1] in ("exec", "image"), argv
            assert argv[1] != "exec" or argv[3] in ("git", "cat"), argv
        assert not any(word in argv for word in ("stop", "restart", "rm", "kill", "build", "up",
                                                 "create", "push", "commit", "cp")), argv


# ============================= 存档面与离线入口（判据①「原文落盘」与判据④「离线可自测」）








def test_the_archive_stores_the_whole_face_verbatim_and_the_index_points_at_it(tmp_path):
    rows, head, out = _archive(tmp_path, _GROWING, sub="verbatim")
    names = sorted(p.name for p in out.iterdir() if p.name.endswith(".json") and p.name != "head.json")
    assert len(names) == len(rows) == len(_GROWING), (names, len(rows))
    for row in rows:
        stored = (out / row["raw_file"]).read_bytes()
        assert stored == json.dumps(_rebuild(row), ensure_ascii=False).encode("utf-8"), row
        assert hashlib.sha256(stored).hexdigest()[:16] == row["raw_sha256"], row
        assert row["has_piece_field"] == (TOOL.PIECE_FIELD in row["body"]), row
    assert (out / "head.json").is_file() and (out / "polls.jsonl").is_file()
    assert head["final_kind"] == TOOL.KIND_POLLED, head


def _rebuild(row) -> dict:
    """按索引那一行还原「应当发出去的那份载荷」，与落盘的原文逐字节对拍。"""
    return row["body"]


def test_the_archive_directory_the_cli_chooses_is_the_one_the_pin_names():
    """判据① 点名落 docs/perf/raw/r561-<今天>/：这一格只从码体现取，钉里不复制路径字面。"""
    words = _string_literals(_function_in(_tool_tree(), "main"))
    assert {item for item in words if item in ("docs", "perf", "raw")} == {"docs", "perf", "raw"},         "存档落点那三节目录名在码里读不齐：%r" % sorted(item for item in words if item in ("docs", "perf", "raw"))
    assert [item for item in words if item.startswith("r561-")],         "main 里读不到 r561-<日期> 那枚前缀：那一格是谁定的落点？"

def test_an_empty_or_missing_archive_raises_instead_of_answering_zero_polls(tmp_path):
    missing = Path(tmp_path) / "not-there"
    with pytest.raises(FileNotFoundError):
        TOOL.load_capture(missing)
    empty = Path(tmp_path) / "empty"
    empty.mkdir()
    (empty / "polls.jsonl").write_bytes(b"")
    with pytest.raises(ValueError):
        TOOL.load_capture(empty)


def test_the_offline_entry_replays_a_saved_window_and_answers_the_same_code(tmp_path, capsys):
    rows, head, out = _archive(tmp_path, _GROWING, sub="replay")
    expected = TOOL.judge(rows, head)["rc"]
    got = TOOL.main(["--offline", str(out)])
    assert got == expected == 0, (got, expected)
    printed = capsys.readouterr().out.splitlines()
    banner = [line for line in printed if "离线重放" in line]
    assert banner and "不是此刻" in banner[0], ("离线重放没声明它不是容器读数：那一形就是把纸面当容器", printed)
    cells = [line for line in printed if line.startswith("[R561] cell=")]
    assert len(cells) == len(TOOL.CELLS), printed
    assert cells[0].startswith("[R561] cell=%s " % TOOL.CELLS[0]), cells[0]
    assert printed[-1].startswith("[R561] rc=0"), printed[-1]
    for name in TOOL.CELLS:
        assert ("cell=%s verdict=PASS" % name) in "\n".join(printed), (name, printed)


def test_the_offline_entry_of_a_missing_archive_answers_two_and_prints_no_cell(tmp_path, capsys):
    rc = TOOL.main(["--offline", str(Path(tmp_path) / "ghost")])
    printed = capsys.readouterr().out
    assert rc == 2, rc
    assert "cell=" not in printed, printed
    assert "存档读不出" in printed, printed


def test_a_second_window_into_a_saved_directory_is_refused(tmp_path, capsys):
    """一扇窗一份账：同目录已存在存档时必须拒绝开窗，不许把两遍叠成一份凭据。"""
    _, _, out = _archive(tmp_path, _GROWING, sub="stacked")
    rc = TOOL.main(["--username", "evalbot", "--password", "hunter2",
                    "--skip-provenance", "--out-dir", str(out)])
    printed = capsys.readouterr().out
    assert rc == 2, (rc, printed)
    assert "拒绝开窗" in printed, printed
    assert "cell=" not in printed, printed


def test_missing_credentials_answer_two_and_produce_no_numbers(monkeypatch, capsys):
    monkeypatch.delenv("EVAL_USERNAME", raising=False)
    monkeypatch.delenv("EVAL_PASSWORD", raising=False)
    rc = TOOL.main(["--id", TOOL.DEFAULT_QUESTION_ID])
    printed = capsys.readouterr().out
    assert rc == 2, (rc, printed)
    assert "凭证" in printed, printed
    for name in TOOL.CELLS:
        assert "cell=%s" % name not in printed, printed


def test_the_offline_replay_opens_no_subprocess_and_no_socket(tmp_path, monkeypatch):
    """🔴 判据④ 那句「离线可自测」的硬证：重放一份存档不需要一条外部命令、一个套接字。"""
    def _no_subprocess(cmd, **kw):
        raise AssertionError("离线重放里起了子进程：" + repr(cmd))

    def _no_opener():
        raise AssertionError("离线重放里打开了 HTTP 门")

    monkeypatch.setattr(TOOL, "run", _no_subprocess)
    monkeypatch.setattr(TOOL, "_no_proxy_opener", _no_opener)
    rows, head, out = _archive(tmp_path, _GROWING, sub="no-io")
    assert TOOL.main(["--offline", str(out)]) == 0
    report = TOOL.judge(TOOL.load_capture(out), head)
    assert report["rc"] == 0 and set(report["cells"]) == set(TOOL.CELLS), report


def _open_mode(node) -> str:
    """`Path.open("a", …)` 与 `open(path, "w")` 两种写法都要认得：模式位是位置相关的。"""
    words = {kw.arg: kw.value for kw in node.keywords}
    if "mode" in words and isinstance(words["mode"], ast.Constant):
        return str(words["mode"].value or "")
    for arg in node.args[:2]:
        if (isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value
                and set(arg.value) <= set("rwbxt+a")):
            return arg.value
    return ""


def test_the_tool_writes_only_inside_its_archive_and_touches_no_tracked_path():
    """量具的写口只有存档那三处；仓内任何一枚在册件都不许被它盖一下。"""
    tree = ast.parse(_tool_source().replace("\r\n", "\n"))
    targets = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in (
                    "write_bytes", "write_text", "mkdir", "touch", "remove", "unlink",
                    "replace", "rename"):
                targets.append(func.attr)
            elif isinstance(func, ast.Attribute) and func.attr == "open":
                mode = _open_mode(node)
                if isinstance(mode, str) and set(mode) & set("wax"):
                    targets.append("open:" + mode)
    assert sorted(targets) == sorted(["mkdir", "open:a", "write_bytes", "write_text",
                                      "write_text"]), targets
    text = _tool_source()
    for tracked in ("app/", "deploy/", "frontend/", "migrations/", "docs/api/"):
        assert ('"%s"' % tracked) not in text, "量具里出现了往 %s 写的路径形状" % tracked


# ==================================================== 真树写口记账（沿 r558 驱动器那一族口径）
_REPOS_NORM = os.path.normcase(str(REPO)) + os.sep
#: 解释器与 pytest 自己的缓存目录不是本件的写口，也不属被跟踪文件；除此之外都记。
_LEDGER_SKIP = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_TREE_WRITES: list = []
_HOOKED = False


def _install_tree_write_ledger() -> None:
    global _HOOKED
    if _HOOKED:
        return
    sys.addaudithook(_tree_write_hook)
    _HOOKED = True


def _tree_write_hook(event, args):
    if event != "open" or len(args) < 2:
        return
    target = args[0]
    if isinstance(target, int):
        return
    try:
        text = os.path.abspath(os.fspath(target))
    except TypeError:
        return
    if not os.path.normcase(text).startswith(_REPOS_NORM):
        return
    parts = Path(os.path.relpath(text, str(REPO))).parts
    if set(parts) & _LEDGER_SKIP:
        return
    mode = args[1] if isinstance(args[1], str) else ""
    flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
    if any(char in mode for char in "wax+") or bool(flags & _WRITE_FLAGS):
        _TREE_WRITES.append(Path(os.path.relpath(text, str(REPO))).as_posix())


_install_tree_write_ledger()
_PRISTINE_TOOL = TOOL
LEDGER_LINES: list = []


# ============================================================ 反证刀（判据④：≥2 把）
def _mutant(pairs):
    """把量具的码体摘掉一格守卫，落进**一次性隔离命名空间**：原件与活模块都不碰。"""
    source = _tool_source().replace("\r\n", "\n")
    for old, new in pairs:
        hits = source.count(old)
        assert hits == 1, "刀口在量具里命中 %d 次（要求恰好 1）：%r" % (hits, old[:72])
        source = source.replace(old, new, 1)
    ast.parse(source)
    ns = {"__name__": "r561_mutant_namespace", "__file__": str(TOOL_PATH)}
    exec(compile(source, str(TOOL_PATH), "exec"), ns)
    return SimpleNamespace(**ns)


def _cell_of(cell) -> dict:
    assert isinstance(cell, dict) and "verdict" in cell and "cell" in cell, cell
    return cell


def _read_growing(tool, rows, head):
    return tool.judge_growing(rows)


def _read_caps(tool, rows, head):
    return tool.judge_caps(rows)


def _read_terminal(tool, rows, head):
    return tool.judge_terminal(rows)


def _read_counts(tool, rows, head):
    return tool.judge_counts(rows, head)


def _read_bookkeeping(tool, rows, head):
    return tool.judge_bookkeeping(rows, head)


def _read_provenance(tool, rows, head):
    return tool.judge_provenance(head)


def _probe(name, faces, head_over, reader):
    """一枚探针＝「拿这一份坏夹具去问那一格」：刀与钉共用同一份夹具，不许各造一形。"""

    def _read(tool, workdir):
        rows, head, _ = _archive(Path(workdir), faces, head_over, sub=name)
        cell = _cell_of(reader(tool, rows, head))
        assert cell["cell"] == name, (name, cell["cell"])
        return cell

    return _read


def _bite_became_pass(before, after):
    return after["verdict"] == PASS


def _bite_emptied_the_invented_list(before, after):
    """词表那一格摘掉：自创口径那枚名从「点出来了」变成「没点出来」。

    🔴 这一格的 verdict 摘前摘后都还是 FAIL——unreadable 本身在场，那是量到了的坏读数，
    一把摘词表的刀没有权利把它一起抹掉。所以这一把的牙看 evidence，不看三态。
    """
    return bool(before["value"]["invented_reasons"]) and not after["value"]["invented_reasons"]


def _bite(tmp_path, key, knife, victim_name, pairs, probe, witness=_bite_became_pass):
    """摘掉守卫 ⇒ 那一格必须真的变样（刀咬到了），且点名 victim 当场红。

    三件事逐件证：① 原件下这一格非 PASS（否则刀没有可咬的东西）；② 摘掉守卫后 witness
    认出变化（默认＝变成 PASS）；③ victim 那枚在册钉在变异体下必须抛 AssertionError。
    🔴 全程只动一次性隔离命名空间：原件字节与活模块都不碰，出窗逐字节复验＋真树写口记账。
    """
    victim = globals()[victim_name]
    self_module = sys.modules[__name__]
    digest_before = hashlib.sha256(TOOL_PATH.read_bytes()).hexdigest()
    writes_before = len(_TREE_WRITES)
    before = probe(_PRISTINE_TOOL, Path(tmp_path) / ("pristine-" + key))
    assert before["verdict"] != PASS, "%s：开窗前这一格就是绿的，刀没有可咬的东西：%r" % (
        knife, before["verdict"])
    mutant = _mutant(pairs)
    after = probe(mutant, Path(tmp_path) / ("mutant-" + key))
    assert witness(before, after), "%s：摘掉守卫后这一格没变样（%s -> %s），这一把是空牙" % (
        knife, before["verdict"], after["verdict"])
    outcome = "GREEN"
    try:
        self_module.TOOL = mutant
        victim(Path(tmp_path) / ("victim-" + key))
    except AssertionError:
        outcome = "RED"
    finally:
        self_module.TOOL = _PRISTINE_TOOL
    digest_after = hashlib.sha256(TOOL_PATH.read_bytes()).hexdigest()
    writes = _TREE_WRITES[writes_before:]
    restored = (digest_after == digest_before and _PRISTINE_TOOL is TOOL and outcome == "RED")
    LEDGER_LINES.append(
        "[R561-KNIFE] %s %s victim=%s 摘前=%s 摘后=%s outcome=%s RESTORED=%s 真树写口=%d "
        "sha256=%s..%s" % (key, knife, victim_name, before["verdict"], after["verdict"], outcome,
                           restored, len(writes), digest_before[:16], digest_after[:16]))
    assert outcome == "RED", "%s 摘掉守卫后那枚钉还绿：牙是空的（victim=%s）" % (knife, victim_name)
    assert restored, "%s 收尾没恢复到逐字节同一：sha 前=%s 后=%s" % (knife, digest_before, digest_after)
    assert not writes, "%s 在真树里开过写口：%r" % (knife, writes)

def test_knife_g1_removing_the_monotonic_guard_reddens_the_growing_pin(tmp_path):
    """刀 G1「摘掉递增判读」：把 growing 那格的判词钉死成 PASS。"""
    _bite(tmp_path, "G1", "摘掉递增判读", "test_three_polls_that_never_move_are_red",
          [("    verdict = PASS if not problems else FAIL", "    verdict = PASS")],
          _probe("growing", _FLAT, None, _read_growing))


def test_knife_g2_the_terminal_face_carrying_pieces_must_redden_the_pin(tmp_path):
    """刀 G2「终态那一发也带片段键」：非 processing 那一格与终态那一格一起摘掉。"""
    _bite(tmp_path, "G2", "摘掉终态不许带键这一格",
          "test_a_terminal_face_carrying_the_piece_field_is_red",
          [('             if row.get("status") != LIVE_STATUS and row.get("has_piece_field")]',
            "              if False]"),
           ('    if last.get("has_piece_field"):', "    if False:")],
          _probe("terminal_no_pieces", _TERMINAL_LEAK, None, _read_terminal))


def test_knife_g3_folding_unmeasured_into_zero_reddens_the_cap_pin(tmp_path):
    """刀 G3「把量不到折成 0」：一发片段读数都没取到也报 PASS。"""
    _bite(tmp_path, "G3", "把量不到折成 0",
          "test_a_lane_that_answered_nothing_about_pieces_is_unmeasured_not_zero",
          [('        return _cell("caps_zero", UNMEASURED, {"polls_with_pieces": 0},',
            '        return _cell("caps_zero", PASS, {"polls_with_pieces": 0},')],
          _probe("caps_zero", _NOPIECES, None, _read_caps))


def test_knife_g4_folding_a_bypassed_lane_reddens_the_counts_pin(tmp_path):
    """刀 G4「把根本没入队折成零片」：bypass 不再判读 ⇒ 那枚钉红。"""
    _bite(tmp_path, "G4", "把没入队折成零片",
          "test_a_turn_that_never_entered_the_queue_is_named_bypass_not_zero_polls",
          [('    bypass = not request_id or "queued" not in events', "    bypass = False")],
          _probe("zero_bypass_unreadable_retry", _GROWING, _BYPASS_HEAD, _read_counts))


def test_knife_g5_opening_the_reason_vocab_reddens_the_vocab_pin(tmp_path):
    """刀 G5「放开 reason 词表」：第四枚字不再被点名成自创口径 ⇒ 那枚钉红。"""
    _bite(tmp_path, "G5", "放开 reason 词表",
          "test_a_reason_outside_the_closed_vocab_is_named_a_new_calibre",
          [("            if reason not in PIECE_REASON_VOCAB:", "            if False:")],
          _probe("zero_bypass_unreadable_retry", _INVENTED, None, _read_counts),
          witness=_bite_emptied_the_invented_list)


def test_knife_g6_passing_a_missing_provenance_reddens_the_gate_pin(tmp_path):
    """刀 G6「没有 provenance 读数也放行」：那道开窗闸就白了 ⇒ 那枚钉红。"""
    _bite(tmp_path, "G6", "没读数也开窗",
          "test_the_head_without_a_provenance_reading_at_all_is_unmeasured",
          [('        return _cell("provenance", UNMEASURED, {}, "没有 provenance 读数（未跑或被跳过）", [])',
            '        return _cell("provenance", PASS, {}, "没有 provenance 读数（未跑或被跳过）", [])')],
          _probe("provenance", _GROWING, _NO_PROV_HEAD, _read_provenance))


def test_knife_g7_trusting_a_parked_window_reddens_the_bookkeeping_pin(tmp_path):
    """刀 G7「停在挂起也算账齐」：那种窗里的形状读数本来不可采信。"""
    _bite(tmp_path, "G7", "停在挂起也算账齐",
          "test_a_window_that_stopped_at_the_park_fails_its_own_bookkeeping",
          [("    bad_final = final not in KINDS_WITH_BYTES", "    bad_final = False")],
          _probe("poll_bookkeeping", _GROWING, _PARKED_HEAD, _read_bookkeeping))


def test_the_knife_ledger_is_printed_and_every_knife_is_restored(capsys):
    """七把刀逐枚交末行：摘前摘后逐字节同一、victim 点名、真树零写口。"""
    keys = [line.split()[1] for line in LEDGER_LINES]
    assert len(LEDGER_LINES) >= 2, LEDGER_LINES
    for line in LEDGER_LINES:
        print(line)
    assert "G1" in keys and "G2" in keys, keys
    assert all("RESTORED=True" in line for line in LEDGER_LINES), LEDGER_LINES
    assert all("真树写口=0" in line for line in LEDGER_LINES), LEDGER_LINES
    assert TOOL is _PRISTINE_TOOL, "刀跑完活模块不是原件那一枚：变异漏在命名空间上了"


# ================================================== 姿势钉（本件自己不许长成病的样子）
def test_the_readout_reads_only_the_failure_keys_it_claims(tmp_path):
    """轮询载荷那一枚 `failure`：判读碰的键必须是产品那格的一部分，其余那枚填什么都不作数。

    这枚钉是 `_failure()` 那句注释的正身——给没人读的那枚键填个天文数字，判词不许跟着动。
    """
    func = _function_in(_tool_tree(), "judge_counts")
    read = {node.args[0].value for node in ast.walk(func)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get" and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "failure" and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)}
    live = set(upstream_failure_keys())
    assert read and read <= live, ("判读碰的键不在产品那格里：%r / %r" % (sorted(read), sorted(live)))
    others = sorted(live - read)
    assert others, "产品那一格里每一枚键都被判读碰着：夹具无处填占位值，这条口径要改口"
    rows, head, _ = _archive(tmp_path, _GROWING, sub="failure-keys")
    baseline = TOOL.judge_counts(rows, head)["verdict"]
    for key in others:
        poked = []
        for row in rows:
            copy = dict(row)
            body = dict(row["body"])
            failure = dict(body["failure"])
            failure[key] = 987654321
            body["failure"] = failure
            copy["body"] = body
            poked.append(copy)
        assert TOOL.judge_counts(poked, head)["verdict"] == baseline, \
            "把没人读的那枚键改成天文数字，判词居然跟着变了：%s" % key


def test_the_tool_is_stdlib_only_and_imports_no_product_code():
    tree = ast.parse(_tool_source().replace("\r\n", "\n"))
    allowed = {"__future__", "argparse", "hashlib", "json", "os", "re", "subprocess", "sys",
               "time", "urllib.error", "urllib.request", "uuid", "pathlib"}
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            seen.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            seen.add(node.module)
    assert seen <= allowed, "量具引了名单外的模块：%r" % sorted(seen - allowed)
    assert not [name for name in seen if name.split(".")[0] in ("app", "deploy", "frontend")], \
        "量具把产品码 import 进来了：容器那一遍就不是独立第三方读数"


def test_the_tool_has_exactly_one_external_command_seam():
    tree = ast.parse(_tool_source().replace("\r\n", "\n"))
    hits = [node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "run"
            and isinstance(node.value, ast.Name) and node.value.id == "subprocess"]
    assert len(hits) == 1, "subprocess 出口从一枚变成 %d 枚：provenance 那条闸就不止敲一扇门了" % len(hits)


def test_this_file_adds_no_skip_and_no_xfail():
    """🔴 判据④ 末句：钉里不许 skip／xfail，也不许把「此刻盘面脏不脏」当判据（事故 #96）。"""
    source = Path(__file__).read_text(encoding="utf-8")
    for banned in ("pytest." + "skip", "pytest." + "xfail", "@" + "pytest.mark.skip",
                   "@" + "pytest.mark.xfail", "skip" + "if", "por" + "celain", "is" + "_dirty"):
        assert banned not in source, banned


def test_the_new_files_are_crlf_and_unbommed():
    """新件必须 CRLF 且无 BOM：在**原始字节**上判，先归一再问「原来是 CRLF 吗」是恒假条件。"""
    paper = REPO / "docs" / "perf" / "r561-queue-lane-piece-readout.md"
    targets = [TOOL_PATH, Path(__file__), paper]
    for path in targets:
        assert path.is_file(), "该交的件不在盘上：" + str(path)
        data = path.read_bytes()
        assert data[:3] != b"\xef\xbb\xbf", path.name + " 带了 BOM"
        assert data.count(b"\r") == data.count(b"\r\n"), path.name + " 里有裸 CR"
        assert data.count(b"\n") == data.count(b"\r\n"), path.name + " 里有裸 LF（混行尾）"
        assert data.endswith(b"\r\n"), path.name + " 结尾没换行"


def test_the_pin_does_not_read_the_working_tree_as_its_own_source(tmp_path):
    """在册字面一律从 `git show HEAD:` 取：盘上那份可能是别人的在途改动，不是可复现的那一份。"""
    assert "git show" in Path(__file__).read_text(encoding="utf-8")
    for rel in (QUEUE_REL, CHAT_REL, WORKER_REL, PROBE_REL, CONTRACT_REL, COMPOSE_REL, R255_REL):
        assert blob(rel), "这份在册字节读不到：" + rel
