"""R590 A② 逐腿归因量具（run13／run14／run17 三窗 × 具名题）。只读、离线、零网络、零模型、零容器、零写盘。

为什么要这件：跟进单 §157 三问的是「``tool-02``／``scope-05`` 各红在 ``_frame_verdict`` 那把尺的第几枚腿上」。
在册那三把尺都不做**逐题逐腿的合取分解**：

  * ``scripts/eval_frame_caliber_readout.py`` 出全窗逐腿普查（哪枚腿红了几题、题号），不落到「这一题红在第几腿」；
  * ``scripts/r239_stream_gap_offline_audit.py`` 出 ②-a／②-b 两格 + 独立复算 + ``extra_red_conditions``，
    而 ``extra_red_conditions`` 只点名**两枚**腿（``max_stream_frames>1``／``uncorrected_breaks==0``）；
  * ``scripts/r573_caliber_reconciliation.py`` 出甲／乙／丙三口径的分母分子。

于是「红在哪一枚腿」今天只能靠人读帧账，而**人读就会自造腿名**。本件把这件事变成机器读数，且一枚腿名都不自造。

🔴 本件不复制任何判则。腿名、腿值、腿判全部取自在册尺自己的字节：

  1. **腿清单**＝对 ``scripts/eval_transport_ask_v2.py::_frame_verdict`` 的源码现场 ``inspect`` + ``ast`` 拆：
     把返回值那枚布尔合取的每一枚操作数原样取出（含它在文件里的绝对行号）；短名按在册判器
     ``extra_red_conditions`` 已有的写法生成（``<键><运算符><右值>``，裸真值测试只给键名）；拆出来的**键序**
     必须逐枚等于在册名单 ``r239_stream_gap_offline_audit.LEDGER_CONJUNCTS`` 去掉 ``criterion_two_holds``
     的前七枚 —— 对不上当场 REFUSE（行号会漂，键序与名单不会；真尺加腿时本件逼着人来对账）。
  2. **腿值**＝在册判器的现场调用：``_uncorrected_breaks``（老账退回 ``prefix_breaks`` 那条纪律）、
     ``cross_stream_repeat_frames``（第七枚证词从行内那一列 R223 逐帧指纹现场派生，派生不出＝``None``＝未量）。
  3. **腿判**＝把拆出来的那一枚操作数原样 ``compile`` 后执行，命名空间里只有 ``readings`` 与真尺自己的缺省
     ``REPEAT_DELIVERY_UNMEASURED`` —— 本件不重写任何一次比较。
  4. **四面同代对判**（每一行都要过）：逐枚操作数的合取 ∧ 真尺 ``_frame_verdict(readings)`` ∧
     判器 ``recomputed_ledger(row)`` ∧ 账上存档 ``criterion_two_holds`` —— 四面任何一面不同值 ⇒ REFUSE，
     本件不替哪一面改写，也不许拿半套读数出归因。
  5. **在册腿名对判**：每一行 ``extra_red_conditions(row)`` 交回的腿名必须是本件该枚红腿短名的**子集**
     （判器只点名两枚腿，所以是子集不是等集）；不成立＝本件的短名写法与在册漂了，REFUSE。

「唯一挡路腿」用反事实探针交：把**那一枚**腿的读数换成「能满足该枚操作数自己的比较」的值（探针值由运算符与
右值机械推出，不是本件另定的合格线），其余腿照原样，再叫真尺判一次 —— 翻绿＝这一枚腿单独挡路；不翻＝还有别的腿。
🔴 探针只改内存里那一行影子，盘上一字节不动。

帧正文与终答的关系用真尺自己的 ``_sha12`` 现算（逐帧那一列只有 sha + chars，本件不另起指纹尺）：
「断流到底是真改写还是切批不同」只能靠内容判 —— 前缀＝切批，不在终答里＝屏上那份字被换掉了。

A④ 那一维顺带走在册评分尺：``app/quality/eval.py::_is_correct`` 现场调用，逐窗逐枚点名 correct／incorrect。
🔴 本件只出数：翻不翻绿、哪枚腿算产品形状、量具口径要不要改，全部由总控裁（改判据要单独报批，本件一枚腿都不放宽）。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))  # 在册评分尺 app/quality/eval.py 要按仓根导入（只读，不改它一个字）

import eval_frame_caliber_readout as readout  # noqa: E402  在册主口径取行法（同题多轮取 attempt 最大那一行）
import eval_transport_ask_v2 as ruler  # noqa: E402  在册真尺（_frame_verdict / _sha12 / 缺省证词）
import r239_stream_gap_offline_audit as audit  # noqa: E402  在册判器（复算 + 派生读数 + 在册腿名写法）

DEFAULT_EVALRUN = Path(os.environ.get("TEMP", ".")) / "evalrun"
DEFAULT_TAGS = ("run13", "run14", "run17")
DEFAULT_IDS = ("tool-02", "scope-05")
DEFAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"
EXPECTED_DENOMINATOR = 105

RC_OK = 0
RC_REFUSE = 2

#: 第七枚证词的键名：它**不是**帧账的一格（丙案，总控 09-29 裁定一），只能从行内那一列逐帧指纹派生。
REPEAT_KEY = "cross_stream_repeat_frames"
#: 存档读数那一列不是合取的腿，它是四面同代对判里的第四面。
ARCHIVE_KEY = "criterion_two_holds"
UNMEASURED = "未量"

_OP_TEXT = {ast.Gt: ">", ast.GtE: ">=", ast.Lt: "<", ast.LtE: "<=", ast.Eq: "==", ast.NotEq: "!="}


class RefuseError(Exception):
    """问不到就是问不到：拒绝出归因，不许退化成半套读数，也不许把「没量过」读成「量过且干净」。"""


def sha256_of(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

# ===== 1. 腿清单：从在册尺自己的源码字节里拆，一枚都不自造 =====

def _readings_key(node):
    """这一枚操作数读的是 ``readings`` 里哪一枚键：``readings["k"]`` 或 ``readings.get("k", ...)``。"""
    if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
            and node.value.id == "readings" and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)):
        return node.slice.value
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get" and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "readings" and node.args
            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
        return node.args[0].value
    return None


def _operand_key(node) -> str:
    for sub in ast.walk(node):
        key = _readings_key(sub)
        if key:
            return key
    raise RefuseError("那一枚合取操作数里拆不出 readings 键，本件拒绝给它腿名：" + ast.dump(node)[:160])


def _operand_label(node) -> str:
    """短名写法跟在册判器 ``extra_red_conditions`` 一致：``max_stream_frames>1``／``uncorrected_breaks==0``。"""
    key = _operand_key(node)
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        right = node.comparators[0]
        if isinstance(right, ast.Constant) and isinstance(right.value, int):
            return key + _OP_TEXT.get(type(node.ops[0]), "?") + str(right.value)
    return key


def _pass_value(node):
    """探针值：能满足这一枚比较的值 —— 由运算符与右值机械推出，不是本件另定的合格线。"""
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        right = node.comparators[0]
        if isinstance(right, ast.Constant) and isinstance(right.value, int):
            op = type(node.ops[0])
            if op is ast.Eq:
                return right.value
            if op in (ast.Gt, ast.GtE):
                return right.value + 1
            if op in (ast.Lt, ast.LtE):
                return right.value - 1
            if op is ast.NotEq:
                return right.value + 1
    return True


def registered_labels() -> list:
    """在册判器自己写出来的那两枚腿名（本件的短名必须能罩住它们，见 ``attribute`` 的第五道闸）。"""
    sample = {"text_frames": 3, "max_stream_frames": 1, "uncorrected_breaks": 2, "prefix_breaks": 2,
              "missing_chars": 0, "extra_chars": 0, "last_frame_covers_answer": True}
    return sorted(set(audit.extra_red_conditions(sample)))


def _assert_key_order(keys) -> None:
    expected = [key for key in audit.LEDGER_CONJUNCTS if key != ARCHIVE_KEY]
    if list(keys) != expected:
        raise RefuseError("拆出来的腿序与在册名单不同代：本件拆到 " + json.dumps(list(keys))
                          + " 而 LEDGER_CONJUNCTS 交回 " + json.dumps(expected)
                          + " ⇒ 真尺加／减／换了腿，先改本件与纸，不许按自己一套出数")


def derive_legs() -> list:
    """现场拆 ``_frame_verdict`` 的合取：序号／键／短名／操作数原文／绝对行号／可执行码／探针值。"""
    source = inspect.getsource(ruler._frame_verdict)
    first_line = inspect.getsourcelines(ruler._frame_verdict)[1]
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    returned = next(node for node in ast.walk(function) if isinstance(node, ast.Return))
    expression = returned.value
    if (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name)
            and expression.func.id == "bool" and len(expression.args) == 1):
        expression = expression.args[0]
    if not isinstance(expression, ast.BoolOp) or not isinstance(expression.op, ast.And):
        raise RefuseError("_frame_verdict 的返回值不是一枚布尔合取，本件不会拆腿")
    legs = []
    for operand in expression.values:
        segment = ast.get_source_segment(source, operand) or ""
        normalized = " ".join(segment.split())
        code = compile(ast.parse(normalized, mode="eval"), "<_frame_verdict 的一枚操作数>", "eval")
        legs.append({"index": len(legs) + 1, "key": _operand_key(operand), "label": _operand_label(operand),
                     "operand": normalized, "line": first_line + operand.lineno - 1,
                     "code": code, "pass_value": _pass_value(operand)})
    _assert_key_order([leg["key"] for leg in legs])
    return legs


def legs_table(legs) -> list:
    """纸里那张腿名表的原文：第几腿／短名／操作数／源文件行号。"""
    return [{"index": leg["index"], "label": leg["label"], "operand": leg["operand"], "line": leg["line"]}
            for leg in legs]


def repeat_label(legs) -> str:
    return next(leg["label"] for leg in legs if leg["key"] == REPEAT_KEY)


# ===== 2. 读数与判：全部走在册尺自己的字节 =====

def leg_value(row, key):
    if key == "uncorrected_breaks":
        return audit._uncorrected_breaks(row)
    if key == REPEAT_KEY:
        return audit.cross_stream_repeat_frames(row)
    if key == "last_frame_covers_answer":
        return bool(row[key])
    return int(row.get(key) or 0)


def build_readings(row, legs) -> dict:
    return {leg["key"]: leg_value(row, leg["key"]) for leg in legs}


def _eval_operand(code, readings) -> bool:
    return bool(eval(code, {"__builtins__": {"int": int, "bool": bool}},
                     {"readings": readings, "REPEAT_DELIVERY_UNMEASURED": ruler.REPEAT_DELIVERY_UNMEASURED}))


def attribute(row, legs) -> dict:
    """一题一条归因：逐枚腿读数／判／状态 + 四面同代对判 + 在册腿名子集对判 + 唯一挡路腿探针。"""
    readings = build_readings(row, legs)
    per_leg = []
    for leg in legs:
        value = readings[leg["key"]]
        passed = _eval_operand(leg["code"], readings)
        state = "量过" if not (leg["key"] == REPEAT_KEY and value is None) else UNMEASURED
        probe = dict(readings)
        probe[leg["key"]] = leg["pass_value"]
        per_leg.append({"index": leg["index"], "key": leg["key"], "label": leg["label"],
                        "value": UNMEASURED if value is None else value, "passed": passed, "state": state,
                        "sole_blocker": None if passed else bool(ruler._frame_verdict(probe))})
    blockers = [item for item in per_leg if not item["passed"]]
    faces = {"逐枚操作数合取": all(item["passed"] for item in per_leg),
             "_frame_verdict": ruler._frame_verdict(readings),
             "recomputed_ledger": audit.recomputed_ledger(row),
             "存档 " + ARCHIVE_KEY: bool(row[ARCHIVE_KEY])}
    if len({bool(value) for value in faces.values()}) != 1:
        raise RefuseError("四面不同代（题=" + str(row.get("id")) + "）："
                          + json.dumps({key: bool(value) for key, value in faces.items()}, ensure_ascii=False)
                          + " ⇒ 账与尺不同代，本件拒绝出归因（先取证谁改了哪一面）")
    registered = set(audit.extra_red_conditions(row))
    own = {item["label"] for item in blockers}
    if not registered.issubset(own):
        raise RefuseError("在册判器点名的腿不在本件红腿短名里（题=" + str(row.get("id")) + "）：在册="
                          + json.dumps(sorted(registered), ensure_ascii=False) + " 本件="
                          + json.dumps(sorted(own), ensure_ascii=False)
                          + " ⇒ 本件的短名写法与在册漂了，拒绝出数")
    return {"id": str(row.get("id", "")), "kind": str(row.get("kind", "")),
            "streams": int(row.get("streams") or 0), "text_frames": int(row["text_frames"]),
            "max_stream_frames": int(row.get("max_stream_frames") or 0),
            "per_stream": row.get("per_stream") or [],
            "answer_chars": int(row.get("answer_chars") or 0), "answer_sha": row.get("answer_sha"),
            "first_visible_event": row.get("first_visible_event"),
            "first_visible_ms": row.get("first_visible_ms"),
            "queue_cell_keys": len(row.get("queue") or {}),
            "verdict": bool(faces["_frame_verdict"]),
            "faces": {key: bool(value) for key, value in faces.items()},
            "legs": per_leg,
            "blockers": [{"index": item["index"], "label": item["label"], "value": item["value"],
                          "sole_blocker": item["sole_blocker"]} for item in blockers],
            "unmeasured": [item["label"] for item in per_leg if item["state"] == UNMEASURED]}


def census(rows, legs) -> dict:
    """全窗逐腿普查：每一枚腿红了几题（题号逐枚点名）+ 未量枚数 + 绿题号。"""
    red = {leg["label"]: [] for leg in legs}
    unmeasured = {leg["label"]: [] for leg in legs}
    green = []
    for row in rows:
        item = attribute(row, legs)
        if item["verdict"]:
            green.append(item["id"])
        for blocker in item["blockers"]:
            red[blocker["label"]].append(item["id"])
        for label in item["unmeasured"]:
            unmeasured[label].append(item["id"])
    return {"rows": len(rows), "green_n": len(green), "red_n": len(rows) - len(green),
            "legs": {label: {"红枚数": len(sorted(ids)), "题号": sorted(ids)} for label, ids in red.items()},
            "unmeasured": {label: len(ids) for label, ids in unmeasured.items()}}


# ===== 3. 帧正文与终答的关系（切批 vs 真改写，只能靠内容判） =====

def frame_relation(answer, record) -> str:
    chars = int(record.get("chars") or 0)
    sha = str(record.get("sha") or "")
    if not sha:
        return "无逐帧指纹"
    if chars > len(answer):
        return "比终答长"
    if chars == len(answer) and sha == ruler._sha12(answer):
        return "终答逐字"
    if sha == ruler._sha12(answer[:chars]):
        return "终答前缀"
    for offset in range(0, len(answer) - chars + 1):
        if ruler._sha12(answer[offset:offset + chars]) == sha:
            return "终答内截@" + str(offset)
    return "不在终答里"


def frames_shape(row, answer):
    if answer is None:
        return []
    return [{"stream": record.get("stream"), "at": record.get("at"), "chars": int(record.get("chars") or 0),
             "sha": record.get("sha"), "prefix_break": bool(record.get("prefix_break")),
             "elapsed_ms": record.get("elapsed_ms"), "relation": frame_relation(answer, record)}
            for record in row.get("frames") or []]

# ===== 4. 装载与来源指纹（三本账 + 窗指纹 + fixture 现算对判） =====

def ledger_paths(evalrun: Path, tag: str) -> dict:
    paths = {"frames": evalrun / (tag + "-sidecar-frames.jsonl"),
             "sidecar": evalrun / (tag + "-sidecar.jsonl"),
             "answers": evalrun / (tag + "-answers.jsonl"),
             "window": evalrun / (tag + ".window.json")}
    for name, path in paths.items():
        if not path.is_file():
            raise RefuseError("输入件读不到：" + name + "=" + str(path) + " ⇒ 这一窗不出数（本件不补造账）")
        if name != "window" and path.stat().st_size == 0:
            raise RefuseError("输入件零字节：" + name + "=" + str(path) + " ⇒ 不可判，拒绝出数")
    return paths


def load_window(evalrun: Path, tag: str, expect: int, fixture: Path, legs) -> dict:
    paths = ledger_paths(evalrun, tag)
    try:
        fingerprint = json.loads(Path(paths["window"]).read_text(encoding="utf-8"))
    except ValueError as error:
        raise RefuseError("窗指纹读不动：" + str(paths["window"]) + " " + str(error)) from error
    fixture_sha = sha256_of(fixture)
    recorded = str(fingerprint.get("fixture_sha256") or "")
    if recorded and recorded != fixture_sha:
        raise RefuseError("fixture 与窗指纹不同代：" + str(fixture) + " 现算 sha256=" + fixture_sha
                          + " 而 " + tag + ".window.json 记的是 " + recorded
                          + " ⇒ 归因必须落在同一份题面上（换 --fixture 或重开窗）")
    try:
        deduped = readout.load_rows(str(paths["frames"]))
    except (ValueError, OSError) as error:
        raise RefuseError("主口径取行失败：" + str(error)) from error
    if len(deduped) != expect:
        raise RefuseError(tag + " 分母对不上：去重后=" + str(len(deduped)) + " 要求=" + str(expect)
                          + "（要出小窗就显式改 --expect-denominator）")
    answers = {}
    for line in Path(paths["answers"]).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            answers[str(row.get("id"))] = row
    return {"tag": tag, "fingerprint": fingerprint, "fixture_sha12": fixture_sha[:12], "paths": paths,
            "rows": deduped, "by_id": {str(row.get("id")): row for row in deduped},
            "answers": answers, "census": census(deduped, legs)}


def require_ids(window: dict, want) -> None:
    missing = [row_id for row_id in want if row_id not in window["by_id"]]
    if missing:
        raise RefuseError(window["tag"] + " 帧账里读不到题号 " + ",".join(missing)
                          + " ⇒ 拒绝按半套窗出归因（先确认这一窗收没收全）")


def fixture_rows(fixture: Path) -> dict:
    rows = {}
    for line in fixture.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[str(row.get("id"))] = row
    return rows


def score_of(fixture_row, answer):
    """A④ 那一维走在册评分尺上：``app/quality/eval.py::_is_correct``（按 must_contain 锚词），零复制。"""
    from app.quality.eval import _is_correct

    return bool(_is_correct(fixture_row, {"answer": answer}))


# ===== 5. 影子正控（盘上一字节不动；反证刀全砍在这些格上） =====

def shadow(row, **patch):
    """内存影子：json 深拷贝 + 打补丁。落盘的那三本账一字节不许动。"""
    copy = json.loads(json.dumps(row, ensure_ascii=False))
    copy.update(patch)
    return copy


def self_test(windows: dict, legs) -> list:
    """每一格都必须点名题号与腿名；摘刀之后漏的就是这些格。"""
    cases = []

    def check(name, ok, detail):
        cases.append({"case": name, "ok": bool(ok), "detail": detail})

    def row_of(tag, row_id):
        window = windows.get(tag) or {}
        return (window.get("by_id") or {}).get(row_id)

    # 🔴 影子必须连存档列一起改：recomputed_ledger 不读那一列，只改读数就等于拿「当年的存档值」反对「影子」，
    #    四面同代对判会（正确地）拒判 —— 这一格今天就是这样撞出来的，写在这里是给下一班省一次误诊。
    row = row_of("run14", "scope-05")
    if row is not None:
        red = attribute(row, legs)
        labels = [item["label"] for item in red["blockers"]]
        check("T1 run14 scope-05 只红在第3枚腿 uncorrected_breaks==0，影子把它摘成 0 就该翻绿",
              labels == ["uncorrected_breaks==0"] and red["blockers"][0]["sole_blocker"] is True
              and attribute(shadow(row, uncorrected_breaks=0, criterion_two_holds=True), legs)["verdict"],
              "红腿=" + json.dumps(red["blockers"], ensure_ascii=False))
    row = row_of("run13", "tool-02")
    if row is not None:
        red = attribute(row, legs)
        labels = [item["label"] for item in red["blockers"]]
        check("T2 run13 tool-02 与 run14 同形（同一枚腿、同一枚唯一挡路腿）=> 与读后端无关的第一凭据",
              labels == ["uncorrected_breaks==0"] and red["blockers"][0]["sole_blocker"] is True,
              "红腿=" + json.dumps(red["blockers"], ensure_ascii=False))
    row17 = row_of("run17", "tool-02")
    if row17 is not None:
        red = attribute(row17, legs)
        labels = sorted(item["label"] for item in red["blockers"])
        check("T3 run17 tool-02 同时红在第1枚腿 text_frames>1 与第2枚腿 max_stream_frames>1，单摘一枚不翻绿",
              len(labels) == 2 and "text_frames>1" in labels and "max_stream_frames>1" in labels
              and all(item["sole_blocker"] is False for item in red["blockers"]),
              "红腿=" + json.dumps(red["blockers"], ensure_ascii=False))
    row = row_of("run13", "scope-05")
    if row is not None:
        blinded = attribute(shadow(row, frames=[]), legs)
        check("T4 摘掉逐帧那一列=>第7枚腿必须报" + UNMEASURED + "（不许拿 0 冒充量过，R507 同族）",
              repeat_label(legs) in blinded["unmeasured"],
              "unmeasured=" + json.dumps(blinded["unmeasured"], ensure_ascii=False))
        flipped = shadow(row, criterion_two_holds=not bool(row[ARCHIVE_KEY]))
        try:
            attribute(flipped, legs)
            caught, detail = False, "没拦：翻过的存档读数被当成同代放过了"
        except RefuseError as error:
            caught, detail = True, str(error)[:150]
        check("T5 翻一枚 run13 scope-05 的存档 criterion_two_holds=>四面同代对判必须 REFUSE", caught, detail)
    try:
        _assert_key_order([leg["key"] for leg in legs][::-1])
        caught, detail = False, "没拦：键序倒过来仍然放行"
    except RefuseError as error:
        caught, detail = True, str(error)[:150]
    check("T6 腿序与 LEDGER_CONJUNCTS 换一枚=>腿名对判必须 REFUSE（真尺加腿时不许按自己一套出数）", caught, detail)
    tampered = [dict(leg, label=leg["label"].replace("==", "<>")) for leg in legs]
    try:
        attribute(shadow(row_of("run14", "scope-05")), tampered)
        caught, detail = False, "没拦：短名漂了一枚仍然出数"
    except RefuseError as error:
        caught, detail = True, str(error)[:150]
    check("T7 本件短名与 extra_red_conditions 的写法漂一枚=>在册腿名子集对判必须 REFUSE", caught, detail)
    return cases

# ===== 6. 出数 =====

def render(legs, windows, ids, scored, cases, include_census: bool) -> str:
    lines = ["# R590 A② 逐腿归因（真尺=_frame_verdict 的合取；腿名全部现拆，零自造）", ""]
    lines.append("## 0. 腿清单原文（第几腿 -> ``_frame_verdict`` 里的那一枚操作数）")
    lines.append("")
    lines.append("| 第几腿 | 短名（在册写法） | 操作数原文 | 源文件行号 |")
    lines.append("| --- | --- | --- | --- |")
    for leg in legs_table(legs):
        lines.append("| %d | `%s` | `%s` | :%d |" % (leg["index"], leg["label"], leg["operand"], leg["line"]))
    lines.append("")
    lines.append("- 在册名单真源：`scripts/r239_stream_gap_offline_audit.py::LEDGER_CONJUNCTS`（去掉 `criterion_two_holds`）")
    lines.append("- 在册判器自己点名的腿名（本件短名必须罩住它们）："
                 + ", ".join("`" + label + "`" for label in registered_labels()))
    lines.append("")
    lines.append("## 1. 三窗指纹（现读 `*.window.json`，不抄纸面）")
    lines.append("")
    for tag, window in windows.items():
        fingerprint = window["fingerprint"]
        lines.append("- %s revision=%s index_backend=%r fixture_sha12=%s ｜ 输入件 sha12=%s" % (
            tag, str(fingerprint.get("revision"))[:7], fingerprint.get("index_backend"),
            window["fixture_sha12"],
            json.dumps({name: sha256_of(path)[:12] for name, path in window["paths"].items()
                        if name != "window"}, ensure_ascii=False)))
    lines.append("")
    lines.append("## 2. 逐题逐腿归因（判据①）")
    lines.append("")
    lines.append("| 题号 | 窗 | kind | 红在第几腿=短名（读数） | 唯一挡路腿 | verdict | 四面同代 | tf/msf/streams | 队列格 | 首屏 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row_id in ids:
        for tag, window in windows.items():
            row = window["by_id"].get(row_id)
            if row is None:
                continue
            item = attribute(row, legs)
            blockers = "; ".join("第%d枚 %s（值=%s）" % (block["index"], block["label"], block["value"])
                                 for block in item["blockers"]) or "无（这一格绿）"
            sole = "; ".join("%s=%s" % (block["label"], block["sole_blocker"])
                             for block in item["blockers"]) or "-"
            lines.append("| `%s` | %s | %s | %s | %s | %s | %s | %d/%d/%d | %d | %s @ %s ms |" % (
                row_id, tag, item["kind"], blockers, sole, item["verdict"],
                json.dumps(item["faces"], ensure_ascii=False), item["text_frames"],
                item["max_stream_frames"], item["streams"], item["queue_cell_keys"],
                item["first_visible_event"], item["first_visible_ms"]))
    lines.append("")
    if not include_census:
        lines.append("（--no-census：全窗普查与 A④ 读数未交）")
        lines.append("")
    if include_census:
        lines.append("## 3. 逐腿全窗普查（哪一枚腿红了几题，题号逐枚点名）")
        lines.append("")
        for tag, window in windows.items():
            data = window["census"]
            lines.append("- **%s**（n=%d）绿=%d 红=%d" % (tag, data["rows"], data["green_n"], data["red_n"]))
            for leg in legs:
                block = data["legs"][leg["label"]]
                lines.append("    第%d枚 `%s` 红=%d 题号=%s ｜ %s枚数=%d" % (
                    leg["index"], leg["label"], block["红枚数"], ",".join(block["题号"]) or "无",
                    UNMEASURED, data["unmeasured"].get(leg["label"], 0)))
        lines.append("")
        lines.append("## 4. 帧正文与终答的关系（切批 vs 真改写）")
        lines.append("")
        for row_id in ids:
            for tag, window in windows.items():
                row = window["by_id"].get(row_id)
                if row is None:
                    continue
                answer = (window["answers"].get(row_id) or {}).get("answer")
                shape = frames_shape(row, answer)
                relations = {}
                for frame in shape:
                    relations[frame["relation"]] = relations.get(frame["relation"], 0) + 1
                breaks = [{"at": frame["at"], "stream": frame["stream"], "chars": frame["chars"],
                           "sha": frame["sha"], "relation": frame["relation"]}
                          for frame in shape if frame["prefix_break"]]
                lines.append("- %s `%s` 帧数=%d 关系计数=%s ｜ 断流帧=%s" % (
                    tag, row_id, len(shape), json.dumps(relations, ensure_ascii=False),
                    json.dumps(breaks, ensure_ascii=False)))
        lines.append("")
        lines.append("## 5. A④ 那一维：在册评分尺逐窗读数（与 R580 那句对账）")
        lines.append("")
        lines.append("| 题号 | " + " | ".join(windows) + " | 三窗同分？ |")
        lines.append("| --- | " + " | ".join(["---"] * (len(windows) + 1)) + " |")
        for row_id in ids:
            values = [str(scored.get(row_id, {}).get(tag)) for tag in windows]
            lines.append("| `%s` | %s | %s |" % (row_id, " | ".join(values), len(set(values)) == 1))
        lines.append("")
    lines.append("## 6. 影子正控（盘上零写入）")
    lines.append("")
    for case in cases:
        lines.append("- [%s] %s ｜ %s" % ("x" if case["ok"] else " ", case["case"], case["detail"]))
    lines.append("")
    lines.append("🔴 本件只出数：翻不翻绿、哪枚腿算产品形状、量具口径要不要改，由总控裁。")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="R590 A② 逐腿归因量具（只读，零写盘）")
    parser.add_argument("--evalrun", default=str(DEFAULT_EVALRUN), help="三本账与窗指纹所在目录")
    parser.add_argument("--tag", nargs="+", default=list(DEFAULT_TAGS), help="窗名，默认三窗齐")
    parser.add_argument("--ids", nargs="+", default=list(DEFAULT_IDS), help="逐腿点名的题号")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="题面（与窗指纹现算对判）")
    parser.add_argument("--expect-denominator", type=int, default=EXPECTED_DENOMINATOR,
                        help="在册分母，对不上即 REFUSE")
    parser.add_argument("--no-census", action="store_true", help="只交逐题归因，不交全窗普查")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        legs = derive_legs()
        evalrun = Path(args.evalrun)
        fixture = Path(args.fixture)
        windows = {}
        for tag in args.tag:
            windows[tag] = load_window(evalrun, tag, args.expect_denominator, fixture, legs)
            require_ids(windows[tag], args.ids)
        ordered = {tag: windows[tag] for tag in args.tag}
        rows = fixture_rows(fixture)
        scored = {}
        for row_id in args.ids:
            scored[row_id] = {}
            for tag, window in ordered.items():
                answer = (window["answers"].get(row_id) or {}).get("answer")
                scored[row_id][tag] = score_of(rows[row_id], answer) if answer is not None else None
        cases = self_test(ordered, legs)
        if args.format == "json":
            payload = {"legs": legs_table(legs), "registered_labels": registered_labels(),
                       "windows": {tag: {"fingerprint": window["fingerprint"],
                                         "inputs_sha12": {name: sha256_of(path)[:12]
                                                          for name, path in window["paths"].items()
                                                          if name != "window"},
                                         "census": window["census"]} for tag, window in ordered.items()},
                       "attribution": [attribute(ordered[tag]["by_id"][row_id], legs)
                                       for row_id in args.ids for tag in ordered],
                       "score": scored, "self_test": cases}
            print(json.dumps(payload, ensure_ascii=False, indent=1))
        else:
            print(render(legs, ordered, args.ids, scored, cases, include_census=not args.no_census))
        failed = [case["case"] for case in cases if not case["ok"]]
        if failed:
            print("REFUSE: 影子正控有格没过：" + "; ".join(failed), file=sys.stderr)
            return RC_REFUSE
        return RC_OK
    except RefuseError as error:
        print("REFUSE: " + str(error), file=sys.stderr)
        return RC_REFUSE


if __name__ == "__main__":
    raise SystemExit(main())