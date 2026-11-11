# -*- coding: utf-8 -*-
r"""R673 · GPU 姿势声明：两种语义各自可失败，且互不混（全离线，零真机）。

写域只有一枚产品文件：`app/common/model_capabilities.py`（新符号 `declare_gpu_posture
`gpu_posture` `posture_basis` `reset_gpu_posture_declaration`，加 `annotate_inference_compute`
里那三行）。`app/common/model_handler.py` 与 `app/rag/**` 一格没碰——派工词把它们划成禁区，
R690 正在那里独占。

判据怎么落地：

① 未设那一格必须有名字。缺省形态（`OLLAMA_REQUIRE_GPU` 非真值）下第一次探测就在日志上打出
   `POSTURE_DECLARATION_FAIL_OPEN`，句子里同时写着「这一形态不拦 CPU 腿」与「R26② 类判据在
   这种形态下不可判」；确证 CPU 腿时另打一行 `CPU_LEG_DECLARATION`，句子里写着「此刻走的是
   CPU 腿」与「本形态下测出的延迟数不得用于 R26②」。发射点唯一（`annotate_inference_compute`
   里那一句），谁打的由日志记录自己的 funcName 报名，不靠本件手抄。
② 设成 on 时必须真硬：`require_gpu` 形态 + 确证 CPU 腿 ⇒ 发现结果就地 available=false、
   带在册稳定码 model_unavailable，并打一行 `HARD_REFUSAL_DECLARATION`。在册牙
   `tests/test_compute_wiring.py::test_require_gpu_makes_a_confirmed_cpu_fallback_unavailable`
   与 `tests/test_gpu_compute_honesty.py::test_require_gpu_hard_fails_a_confirmed_cpu_fallback`
   照样咬得住：把硬门改成静默降级，两枚一起红，本件的反证窗同时点名 `annotate_inference_compute`。
③ 生产缺省一格没翻：本件不读也不写任何 `.env*` 与 `deploy/**`，只按 `os.getenv` 的现值判姿势。
④ 判定口径那一句话同时写在日志里（fail_open 形态的延迟数不得用于 R26②），凭据纸同句复读。

五把反证刀全部走 `tests/test_r466_mutation_does_not_leak_into_live_module.py::install_mutation`
的内存影子：盘上那枚文件全程只读，进刀出门各复对一次 sha256。

  · K1 摘掉声明那一行 ⇒ 声明那一族全红，硬门那一族照绿（证明声明与门是两条腿）。
  · K2 把硬门改成静默降级（只告警不拒绝）⇒ 本件的门牙加两枚在册牙红，声明那一族照绿。
  · K3 把真值名册掏空（on 塌成 fail_open）⇒ 依赖 armed 的每一枚红，fail_open 语义照绿。
  · K4 把声明降到 DEBUG（本件的取数阈值是 INFO）⇒ 声明一族红，门照绿。
  · K5 把两条声明文本互换 ⇒ armed 那一格红（两形态不许互混）。

transport 全部注入，域名不可解析：这套用例不存在打真机 Ollama 的路径，也不动容器。
"""
from __future__ import annotations

import contextlib
import hashlib
import inspect
import logging
import os
from pathlib import Path

import pytest

from app.common import model_config
from app.common import model_capabilities as mc
from tests import test_compute_wiring as wiring
from tests import test_gpu_compute_honesty as honesty
from tests.test_r466_mutation_does_not_leak_into_live_module import install_mutation

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "app" / "common" / "model_capabilities.py"
APP_LOGGER = "enterprise_brain"
REQUIRE_GPU_ENV = mc.REQUIRE_GPU_ENV
BASE_URL = "http://ollama.invalid"
STABLE_CODE = "model_unavailable"
GATE_SYMBOL = "annotate_inference_compute"
DECLARE_SYMBOL = "declare_gpu_posture"

TAGS = {"models": [{"name": "board-chat:latest"}]}
PS_GPU = {"models": [{"name": "board-chat:latest", "size": 4_700_000_000, "size_vram": 4_700_000_000}]}
PS_CPU = {"models": [{"name": "board-chat:latest", "size": 4_700_000_000, "size_vram": 0}]}
VERSION_GPU = {"version": "0.12.0", "num_gpus": 1, "inference_compute": [{"id": "gpu0", "library": "cuda"}]}
VERSION_CPU = {"version": "0.12.0", "inference_compute": [{"id": "cpu", "library": "cpu"}]}
GPU_ROUTES = {"/api/ps": PS_GPU, "/api/version": VERSION_GPU}
CPU_ROUTES = {"/api/ps": PS_CPU, "/api/version": VERSION_CPU}


class Boom(Exception):
    """探测端点挂了：结论必须是 unknown，两形态的声明都不许替它编一个罪名。"""


DEAD_ROUTES = {"/api/ps": Boom("socket closed"), "/api/version": Boom("socket closed")}


def _make_fetch(routes):
    calls = []

    def fetch(url):
        calls.append(url)
        for suffix, payload in routes.items():
            if url.endswith(suffix):
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError("unrouted url: " + url)

    fetch.calls = calls
    return fetch


def _discover(routes):
    """走生产那条腿：discover_ollama_models 带 compute_fetch， annotate 才会被叫到。"""
    tags = _make_fetch({"/api/tags": TAGS})
    probe = _make_fetch(routes)
    return mc.discover_ollama_models(tags, BASE_URL, compute_fetch=probe)


@contextlib.contextmanager
def _logs():
    """自己取数：不靠 basicConfig 有没有跑过，阈值钉在 INFO。

    阈值是刀口的一部分——K4 把声明降到 DEBUG，取数阈值不动，声明就取不到，牙当场红。
    """
    logger = logging.getLogger(APP_LOGGER)
    previous_level, previous_propagate = logger.level, logger.propagate
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Collect(level=logging.INFO)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


@contextlib.contextmanager
def _posture(value=None):
    """一枚用例从干净姿势起跑：env、声明台账、两枚缓存全部归零，出门一样归位。"""
    previous = os.environ.pop(REQUIRE_GPU_ENV, None)
    if value is not None:
        os.environ[REQUIRE_GPU_ENV] = value
    mc.reset_gpu_posture_declaration()
    model_config.reset_model_discovery_cache()
    model_config.reset_inference_compute_cache()
    try:
        with _logs() as records:
            yield records
    finally:
        os.environ.pop(REQUIRE_GPU_ENV, None)
        if previous is not None:
            os.environ[REQUIRE_GPU_ENV] = previous
        mc.reset_gpu_posture_declaration()
        model_config.reset_model_discovery_cache()
        model_config.reset_inference_compute_cache()


def _hits(records, needle):
    return [record for record in records if needle in record.getMessage()]


def _named(record):
    return "%s::%s" % (getattr(record, "funcName", "?"), getattr(record, "levelname", "?"))


# ---------------------------------------------------------------- 判据 ①：未设那一格有名字


def test_the_fail_open_posture_is_announced_once():
    """缺省形态第一次探测就打出具名声明，且点名是谁打的、级别看得见。"""
    with _posture(None) as records:
        result = _discover(GPU_ROUTES)
        assert result.available is True, result.error_message
        hits = _hits(records, mc.POSTURE_DECLARATION_FAIL_OPEN)
        assert len(hits) == 1, [_named(r) for r in records]
        record = hits[0]
        assert record.funcName == DECLARE_SYMBOL, _named(record)
        assert record.name == APP_LOGGER, record.name
        assert record.levelno >= logging.WARNING, _named(record)
        assert REQUIRE_GPU_ENV in record.getMessage(), record.getMessage()


def test_the_fail_open_declaration_says_what_cannot_be_judged():
    """声明必须自己把「不可判」说出来，否则下一班又会拿 CPU 腿的数当 GPU 数用。"""
    body = mc.POSTURE_DECLARATION_FAIL_OPEN
    for needle in ("fail_open", "CPU 腿", "R26②", "不可判"):
        assert needle in body, needle
    with _posture(None) as records:
        _discover(CPU_ROUTES)
        lines = [record.getMessage() for record in _hits(records, mc.CPU_LEG_DECLARATION)]
        assert len(lines) == 1, [_named(r) for r in records]
        assert "此刻走的是 CPU 腿" in lines[0], lines[0]
        assert "不得用于 R26②" in lines[0], lines[0]


def test_the_declaration_is_once_per_posture_and_returns_when_the_posture_flips():
    """一次进程一次声明；姿势翻了必须重新报名——沉默的缺省正是本单治的病。"""
    with _posture(None) as records:
        _discover(GPU_ROUTES)
        _discover(GPU_ROUTES)
        assert len(_hits(records, mc.POSTURE_DECLARATION_FAIL_OPEN)) == 1
        assert _hits(records, mc.POSTURE_DECLARATION_REQUIRE_GPU) == []
        os.environ[REQUIRE_GPU_ENV] = "1"
        _discover(GPU_ROUTES)
        assert len(_hits(records, mc.POSTURE_DECLARATION_REQUIRE_GPU)) == 1
        assert len(_hits(records, mc.POSTURE_DECLARATION_FAIL_OPEN)) == 1


def test_the_declaration_has_exactly_one_emission_point_and_it_is_the_probe():
    """发射点唯一，且量的是**装进活模块的那枚码体**：反证窗里摘掉那一行，本牙当场红。

    盘上文本那把尺子留给静态那一半——`dis` 走的是活函数对象的字节码，所以内存影子改了什么
    它看得见；只看 `MODULE_PATH` 的文本，K1 那种不下盘的刀就永远量不到（钝牙）。
    """
    import dis
    import types

    live = vars(mc)
    callers = sorted(
        {
            name
            for name, value in live.items()
            if isinstance(value, types.FunctionType) and getattr(value, "__globals__", None) is live
            for instruction in dis.get_instructions(value)
            if instruction.opname.startswith("LOAD")
            and DECLARE_SYMBOL in str(instruction.argrepr)
        }
    )
    assert callers == [GATE_SYMBOL], callers
    disk = MODULE_PATH.read_text(encoding="utf-8")
    assert disk.count(DECLARE_SYMBOL + "(require_gpu)") == 1, "声明的落点不止一处"


# ---------------------------------------------------------------- 判据 ②：设成 on 就真硬


def test_a_confirmed_cpu_leg_under_the_hard_gate_fails_by_name():
    """on 形态 + 确证 CPU 腿 ⇒ 就地不可用、带稳定码、并打出具名失败那一行。"""
    with _posture("1") as records:
        result = _discover(CPU_ROUTES)
        assert result.available is False, (
            "硬门静默了：%s 在 require_gpu 形态下仍然放行确证的 CPU 腿（R673②）" % GATE_SYMBOL
        )
        assert result.error_code == STABLE_CODE, result.error_code
        assert result.error_message == mc.CPU_FALLBACK_MESSAGE
        hits = _hits(records, mc.HARD_REFUSAL_DECLARATION)
        assert len(hits) == 1, [_named(r) for r in records]
        assert hits[0].funcName == GATE_SYMBOL, _named(hits[0])
        assert _hits(records, mc.CPU_LEG_DECLARATION) == []


def test_a_confirmed_cpu_leg_under_fail_open_keeps_serving_and_names_the_leg():
    """未设 ⇒ 照样服务，但那一行必须把「此刻走的是 CPU 腿」写出来，不许静默。"""
    with _posture(None) as records:
        result = _discover(CPU_ROUTES)
        assert result.available is True, result.error_message
        assert result.error_code is None
        assert result.compute.error_code == STABLE_CODE
        assert len(_hits(records, mc.CPU_LEG_DECLARATION)) == 1
        assert _hits(records, mc.HARD_REFUSAL_DECLARATION) == []


def test_an_undetermined_probe_borrows_neither_postures_conclusion():
    """看不见卡 ≠ 拿不到卡：on 形态下 unknown 既不定罪也不发通行证。"""
    with _posture("1") as records:
        result = _discover(DEAD_ROUTES)
        assert result.available is True, result.error_message
        assert result.error_code is None
        assert result.compute.undetermined is True
        assert _hits(records, mc.HARD_REFUSAL_DECLARATION) == []
        assert _hits(records, mc.CPU_LEG_DECLARATION) == []
        assert len(_hits(records, mc.POSTURE_DECLARATION_REQUIRE_GPU)) == 1


def test_the_two_postures_differ_only_by_the_switch():
    """同一份探测读数，唯一变量是那枚开关；两行声明文本也必须互不相同。"""
    assert mc.POSTURE_DECLARATION_FAIL_OPEN != mc.POSTURE_DECLARATION_REQUIRE_GPU
    with _posture(None) as open_records:
        soft = _discover(CPU_ROUTES)
        assert soft.available is True
        assert len(_hits(open_records, mc.POSTURE_DECLARATION_FAIL_OPEN)) == 1
    with _posture("on") as hard_records:
        hard = _discover(CPU_ROUTES)
        assert hard.available is False, (
            "开关翻了门没翻：%s 仍然把确证的 CPU 腿当成可用" % GATE_SYMBOL
        )
        assert len(_hits(hard_records, mc.POSTURE_DECLARATION_REQUIRE_GPU)) == 1
        assert _hits(hard_records, mc.POSTURE_DECLARATION_FAIL_OPEN) == []


def test_the_new_lines_stay_out_of_the_registered_inference_warning_filter():
    """在册那把尺按 "inference" 子串筛告警；本单新长的四行一律不进那把尺，也不改它的读数。"""
    bodies = (
        mc.POSTURE_DECLARATION_FAIL_OPEN,
        mc.POSTURE_DECLARATION_REQUIRE_GPU,
        mc.CPU_LEG_DECLARATION,
        mc.HARD_REFUSAL_DECLARATION,
    )
    for body in bodies:
        assert "inference" not in body, body
        assert "R673" in body and "CPU" in body, body
    with _posture(None) as records:
        _discover(GPU_ROUTES)
        assert [r.getMessage() for r in records if "inference" in r.getMessage()] == []


# ---------------------------------------------------------------- 反证窗（五把刀）

_DISK_BASELINE = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
_LEDGER: list[dict] = []
_RED: set = set()

VICTIMS = {
    "r673::announced_once": test_the_fail_open_posture_is_announced_once,
    "r673::says_what_cannot_be_judged": test_the_fail_open_declaration_says_what_cannot_be_judged,
    "r673::once_per_posture": test_the_declaration_is_once_per_posture_and_returns_when_the_posture_flips,
    "r673::one_emission_point": test_the_declaration_has_exactly_one_emission_point_and_it_is_the_probe,
    "r673::gate_fails_by_name": test_a_confirmed_cpu_leg_under_the_hard_gate_fails_by_name,
    "r673::fail_open_names_the_leg": test_a_confirmed_cpu_leg_under_fail_open_keeps_serving_and_names_the_leg,
    "r673::unknown_borrows_neither": test_an_undetermined_probe_borrows_neither_postures_conclusion,
    "r673::only_the_switch_differs": test_the_two_postures_differ_only_by_the_switch,
    "r673::lines_outside_the_filter": test_the_new_lines_stay_out_of_the_registered_inference_warning_filter,
    "test_compute_wiring::require_gpu_makes_a_confirmed_cpu_fallback_unavailable": (
        wiring.test_require_gpu_makes_a_confirmed_cpu_fallback_unavailable
    ),
    "test_gpu_compute_honesty::require_gpu_hard_fails_a_confirmed_cpu_fallback": (
        honesty.test_require_gpu_hard_fails_a_confirmed_cpu_fallback
    ),
    "test_gpu_compute_honesty::the_switch_is_off_when_unset_and_an_argument_wins": (
        honesty.test_the_switch_is_off_when_unset_and_an_argument_wins
    ),
}


def _disk_text() -> str:
    """按盘上的字读（保住 CRLF）：锚点与影子文本都必须对着真字节来。"""
    with open(MODULE_PATH, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _nl_join(*rows: str) -> str:
    text = _disk_text()
    nl = "\r\n" if "\r\n" in text else "\n"
    return nl.join(rows) + nl


def _sha256() -> str:
    return hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()


def _call(name: str) -> None:
    victim = VICTIMS[name]
    holder = pytest.MonkeyPatch()
    previous = os.environ.pop(REQUIRE_GPU_ENV, None)
    mc.reset_gpu_posture_declaration()
    try:
        if "monkeypatch" in inspect.signature(victim).parameters:
            victim(holder)
        else:
            victim()
    finally:
        holder.undo()
        os.environ.pop(REQUIRE_GPU_ENV, None)
        if previous is not None:
            os.environ[REQUIRE_GPU_ENV] = previous
        mc.reset_gpu_posture_declaration()


def _outcome(name: str) -> tuple:
    """交回 (红不红, 读数)：红 = 这枚 victim 不绿，抛断言还是抛别的都算。"""
    try:
        _call(name)
    except AssertionError as exc:
        head = str(exc).splitlines()
        return True, "AssertionError: " + (head[0] if head else "")
    except Exception as exc:  # noqa: BLE001 - 摘刀之后任何失守都算红
        return True, exc.__class__.__name__
    return False, ""


def _cut(tag, uniques, replacements, expect_red, expect_green, must_name=None):
    """内存影子摘刀：mutant 只进 install_mutation，盘上那枚文件全程只读。"""
    text = _disk_text()
    before = _sha256()
    for anchor in uniques:
        hits = text.count(anchor)
        assert hits == 1, (tag, "锚点命中 %d 处，这把刀无法被执行" % hits)
    mutant = text
    for anchor, replacement in replacements:
        mutant = mutant.replace(anchor, replacement)
    assert mutant != text, (tag, "影子文本与盘上一字不差，这把刀是空的")
    entry = {"tag": tag, "before": before, "after": None, "red": [], "green": []}
    _LEDGER.append(entry)
    with install_mutation(mc, MODULE_PATH, mutant):
        for name in expect_red:
            red, reading = _outcome(name)
            assert red, tag + " 摘刀之后 " + name + " 竟然还是绿的：这把刀等于没动任何东西"
            if must_name and name == must_name[0]:
                assert must_name[1] in reading, (tag, name, reading)
            entry["red"].append({"victim": name, "reading": reading})
            _RED.add(name)
        for name in expect_green:
            red, reading = _outcome(name)
            assert not red, tag + " 摘刀之后多红了 " + name + "：" + reading
            entry["green"].append(name)
    entry["after"] = _sha256()
    assert entry["after"] == before, tag + " 出窗之后盘上的字节变了：被跟踪件必须全程只读"
    print(
        "[r673] " + tag
        + " sha " + before[:12] + " -> " + entry["after"][:12]
        + " red=" + ",".join(item["victim"] for item in entry["red"])
        + " green=" + ",".join(entry["green"])
    )
    for item in entry["red"]:
        print("[r673]   " + item["victim"] + " :: " + item["reading"])


_DECLARE_CALL = _nl_join("    declare_gpu_posture(require_gpu)")
_GATE_BLOCK = _nl_join(
    "    if require_gpu_enabled(require_gpu):",
    '        logger.warning("%s 探测读数：%s", HARD_REFUSAL_DECLARATION, compute.detail or "")',
    "        result.available = False",
    "        result.error_code = compute.error_code",
    "        result.error_message = compute.error_message",
    "        return result",
)
_TRUE_VALUES_ROW = '_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})'
_WARNING_LINE = _nl_join('    logger.warning("%s 依据：%s", body, posture_basis(armed))')
_BODY_BLOCK = _nl_join(
    "    body = (",
    "        POSTURE_DECLARATION_REQUIRE_GPU",
    "        if posture == POSTURE_REQUIRE_GPU",
    "        else POSTURE_DECLARATION_FAIL_OPEN",
    "    )",
)
_BODY_SWAPPED = _nl_join(
    "    body = (",
    "        POSTURE_DECLARATION_FAIL_OPEN",
    "        if posture == POSTURE_REQUIRE_GPU",
    "        else POSTURE_DECLARATION_REQUIRE_GPU",
    "    )",
)

def test_the_victims_are_green_before_any_knife():
    """正控：不摘任何一刀，点名的 victim 必须先绿——否则后面的红证明不了任何事。"""
    for name in sorted(VICTIMS):
        red, reading = _outcome(name)
        assert not red, "进刀之前 " + name + " 就是红的：" + reading


def test_k1_removing_the_announcement_blinds_the_declaration_teeth_only():
    """K1 摘掉声明那一行：声明一族红，硬门一族照绿——两条腿分得很干净。"""
    _cut(
        "K1",
        [_DECLARE_CALL],
        [(_DECLARE_CALL, _nl_join("    gpu_posture(require_gpu)"))],
        [
            "r673::announced_once",
            "r673::once_per_posture",
            "r673::one_emission_point",
            "r673::unknown_borrows_neither",
            "r673::only_the_switch_differs",
        ],
        ["r673::gate_fails_by_name", "r673::fail_open_names_the_leg", "r673::lines_outside_the_filter"],
    )


def test_k2_a_silent_gate_blinds_the_registered_teeth_and_names_the_symbol():
    """K2 把硬门改成静默降级：本件的门牙加两枚在册牙一起红，且红话点名 annotate。"""
    _cut(
        "K2",
        [_GATE_BLOCK],
        [(
            _GATE_BLOCK,
            _nl_join(
                "    if require_gpu_enabled(require_gpu):",
                '        logger.warning("%s 探测读数：%s", CPU_LEG_DECLARATION, compute.detail or "")',
            ),
        )],
        [
            "r673::gate_fails_by_name",
            "r673::only_the_switch_differs",
            "test_compute_wiring::require_gpu_makes_a_confirmed_cpu_fallback_unavailable",
            "test_gpu_compute_honesty::require_gpu_hard_fails_a_confirmed_cpu_fallback",
        ],
        [
            "r673::announced_once",
            "r673::says_what_cannot_be_judged",
            "r673::fail_open_names_the_leg",
            "r673::unknown_borrows_neither",
        ],
        must_name=("r673::gate_fails_by_name", GATE_SYMBOL),
    )


def test_k3_an_empty_truth_table_collapses_the_hard_posture_only():
    """K3 真值名册掏空：on 塌成 fail_open，armed 一族全红，fail_open 语义照绿。"""
    _cut(
        "K3",
        [_TRUE_VALUES_ROW],
        [(_TRUE_VALUES_ROW, "_TRUE_VALUES = frozenset()")],
        [
            "r673::gate_fails_by_name",
            "r673::once_per_posture",
            "r673::unknown_borrows_neither",
            "r673::only_the_switch_differs",
            "test_gpu_compute_honesty::the_switch_is_off_when_unset_and_an_argument_wins",
        ],
        ["r673::announced_once", "r673::fail_open_names_the_leg", "r673::lines_outside_the_filter"],
    )


def test_k4_pushing_the_announcement_below_the_capture_level_blinds_it():
    """K4 声明降到 DEBUG：取数阈值仍是 INFO，声明一族红，门照绿——「看得见」也是判据。"""
    _cut(
        "K4",
        [_WARNING_LINE],
        [(_WARNING_LINE, _nl_join('    logger.debug("%s 依据：%s", body, posture_basis(armed))'))],
        [
            "r673::announced_once",
            "r673::once_per_posture",
            "r673::unknown_borrows_neither",
            "r673::only_the_switch_differs",
        ],
        ["r673::gate_fails_by_name", "r673::fail_open_names_the_leg"],
    )


def test_k5_swapping_the_two_bodies_makes_the_postures_indistinguishable():
    """K5 两条声明文本互换：armed 那一格读到 fail_open 的话 ⇒ 红。两形态不许互混。"""
    _cut(
        "K5",
        [_BODY_BLOCK],
        [(_BODY_BLOCK, _BODY_SWAPPED)],
        [
            "r673::announced_once",
            "r673::once_per_posture",
            "r673::only_the_switch_differs",
            "r673::unknown_borrows_neither",
        ],
        [
            "r673::gate_fails_by_name",
            "r673::fail_open_names_the_leg",
            "r673::lines_outside_the_filter",
        ],
    )


def test_a_knife_that_moves_nothing_is_refused():
    """刀必须能落空时被拦下：影子文本与盘上一样时 install_mutation 当场拒。"""
    with pytest.raises(AssertionError) as exc:
        with install_mutation(mc, MODULE_PATH, _disk_text()):
            pass
    assert "顶层绑定" in str(exc.value), str(exc.value)


def test_every_knife_bit_its_named_victims_and_the_module_never_moved():
    """总清点：五把刀各自咬到人，被跟踪那枚文件全程只读（sha 与进门那一刻一致）。"""
    tags = [entry["tag"] for entry in _LEDGER]
    assert tags == ["K1", "K2", "K3", "K4", "K5"], tags
    for entry in _LEDGER:
        assert entry["red"], entry["tag"] + " 一把都没咬红"
        assert entry["after"] == entry["before"], entry["tag"] + " 盘上字节变了"
    assert "test_compute_wiring::require_gpu_makes_a_confirmed_cpu_fallback_unavailable" in _RED
    assert "test_gpu_compute_honesty::require_gpu_hard_fails_a_confirmed_cpu_fallback" in _RED
    assert _sha256() == _DISK_BASELINE, "被跟踪文件在被反证窗摸过之后换了字节"
