# -*- coding: utf-8 -*-
"""R592 · 常驻牙：判读件里 `evidence_n` 只许有一枚取数把手。

缺陷本体（总控 10-03 现取，本钉按在册样本复现）：``scripts/eval_lane_readout.py`` 里
「侧车 evidence_n ↔ answers.evidence 枚数不等」那一行直接去**帧账行**上取这一格，而它住在
**sidecar 行**里 —— 在册 run9 样本实测：sidecar 105/105 带 `evidence_n`，帧账 0/105 带。
于是那一枚取数恒为 None，`int(None or 0) != 枚数` 就恒真：run16 把 12 枚齐全的账打印成
11 枚「两本账不齐」，在册 run9 三件套把 105 枚里 72 枚打印成不齐，同一件程序的逐枚表那一列
（取 sidecar，取对了）又明明打着 14/6/9。下一班照那行打印就会去立案「两本账口径不齐」——
而账是齐的。同族第二次的转抄假话，所以钉死，不靠人记得。

五格（全部离线：只读 docs/testing 的在册样本，变异一律落 tmp_path 或件内自造样本；
零模型、零容器、零库、被跟踪文件一个字都不改）：
  ① 在册样本正面：sidecar 逐枚带着 `evidence_n` 时，读数件不许打印成缺失/None，
     「不等」必须为空，「=0 的题号」必须正好等于逐枚真零那几枚（不许全列点名）。
  ② 同源：逐枚表 `evidence_n` 那一列必须逐枚等于 sidecar 原文的读数（表格列与「不等」行同源）。
  ③ 真缺那一格必须如实报缺：件内自造最小 sidecar 行里删掉这一格 ⇒ 点名「取不到」，
     且不许出现在「不等」清单里，也不许出现在「=0」名册里（既不冒充不齐，也不冒充零枚）。
  ④ 判据不许被放宽成「None 也算齐」：值在而数目不等 ⇒ 「不等」必须逐枚点名 (题号, 侧车, 交回)。
  ⑤ 结构钉：全件除那一枚把手之外不许有第二处取 `evidence_n`，且把手只许喂 sidecar 那本账。
"""
from __future__ import annotations

import ast
import importlib.util
import io
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "eval_lane_readout.py"
RUN9_DIR = REPO_ROOT / "docs" / "testing"
RUN9 = "run9"
HANDLER = "sidecar_evidence_n"
KEY = "evidence_n"

MISMATCH_NEEDLE = "侧车 evidence_n ↔ answers.evidence 枚数不等="
MISMATCH_TAIL = "（两本账"
ZERO_NEEDLE = "- sidecar.evidence_n=0 的题号="
ZERO_TAIL = "（真读到"
UNKNOWN_NEEDLE = "- sidecar.evidence_n 取不到的题号="
UNKNOWN_TAIL = "（取不到"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, str(SCRIPT))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows(path):
    return [json.loads(line) for line in io.open(str(path), encoding="utf-8") if line.strip()]


def _line(out, needle):
    hits = [ln for ln in out.splitlines() if needle in ln]
    assert len(hits) == 1, ("读数行必须恰好一行，取不到就多枚都算红", needle, hits)
    return hits[0]


def _payload(out, needle, tail):
    line = _line(out, needle)
    start = line.index(needle) + len(needle)
    return line[start:line.index(tail, start)]


def _list(out, needle, tail):
    payload = _payload(out, needle, tail)
    return [] if payload == "无" else list(ast.literal_eval(payload))


def _table(out):
    """收逐枚表：表头 + 分隔行 + 之后的每一枚数据行（本件把表打在最后）。"""
    lines = out.splitlines()
    head_at = next(n for n, ln in enumerate(lines) if ln.startswith("| id |"))
    header = [c.strip() for c in lines[head_at].strip("|").split("|")]
    rows = {}
    for ln in lines[head_at + 2:]:
        if not ln.startswith("| "):
            break
        cells = [c.strip() for c in ln.strip("|").split("|")]
        assert len(cells) == len(header), (header, cells)
        rows[cells[header.index("id")]] = cells
    return header, rows


def _write_triple(tmp_path, label, sidecar_rows, frame_rows, answer_rows):
    """按件自己的缺省命名落三本账，免得路径口径又成为第二处把手。"""
    books = [("sidecar-%s.jsonl" % label, sidecar_rows),
             ("sidecar-%s-frames.jsonl" % label, frame_rows),
             ("answers-%s.jsonl" % label, answer_rows)]
    for name, rows in books:
        with io.open(str(tmp_path / name), "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read(tmp_path, capsys, label, sidecar_rows, frame_rows, answer_rows, name="r592_case"):
    _write_triple(tmp_path, label, sidecar_rows, frame_rows, answer_rows)
    rc = _load(name).main(["--label", label, "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0, out
    return out


# ---- 件内自造的最小三本账（与在册样本同形：帧账行一枚都不带 evidence_n）----
# 🔴 正面样本：sidecar 逐枚带着这一格。R592 的反证 K2 就是从这两行里真删掉 evidence_n，
# 删干净之后「不许打印成缺失」那一枚必须红，而 ③ 那枚自带缺格样本的钉不许跟着变红。
FRAME_ROWS = [
    {"id": "report-01", "kind": "queued_approved", "attempt": 1, "answer_chars": 40, "queue": {}},
    {"id": "report-02", "kind": "queued_polled", "attempt": 1, "answer_chars": 22, "queue": {}},
]
SIDECAR_ROWS = [
    {"id": "report-01", "kind": "queued_approved", "attempt": 1, KEY: 14},
    {"id": "report-02", "kind": "queued_polled", "attempt": 1, KEY: 6},
]
ANSWER_ROWS = [
    {"id": "report-01", "evidence": [{"locator": "第%d页" % i} for i in range(14)]},
    {"id": "report-02", "evidence": [{"locator": "第%d页" % i} for i in range(6)]},
]
# ③ 的样本自持一份，不借正面样本：report-02 那一行压根不写这一格（真缺，不是取来取错的把手）
MISSING_SIDECAR_ROWS = [
    {"id": "report-01", "kind": "queued_approved", "attempt": 1, KEY: 14},
    {"id": "report-02", "kind": "queued_polled", "attempt": 1},
]


def _copy(rows):
    return [dict(row) for row in rows]


# ==================== ① + ②：在册 run9 三件套（只读，一字节都不改） ====================

def test_in_book_run9_prints_no_evidence_n_as_missing(capsys):
    """判据①：sidecar 逐枚带着这一格时，「不等」必须为空，且一个 None 都不许打印出来。"""
    rc = _load("r592_run9").main(["--dir", str(RUN9_DIR), "--label", RUN9])
    out = capsys.readouterr().out
    assert rc == 0, out

    side = _rows(RUN9_DIR / ("sidecar-%s.jsonl" % RUN9))
    frames = _rows(RUN9_DIR / ("sidecar-%s-frames.jsonl" % RUN9))
    answers = {str(r["id"]): r for r in _rows(RUN9_DIR / ("answers-%s.jsonl" % RUN9))}
    # 本钉的前提，逐枚数过才敢钉：格在 sidecar 那本账上，不在帧账上
    assert all(KEY in r for r in side), "在册 sidecar 不再逐枚带 evidence_n，本钉前提变了"
    assert sum(1 for r in frames if KEY in r) == 0, "帧账开始带 evidence_n，本钉的对照前提变了"
    truth_zero = sorted(str(r["id"]) for r in side if r[KEY] == 0)
    assert truth_zero and len(truth_zero) < len(side), "样本成了全零或全非零，测不出「全列点名」那族假话"
    disagree = sorted(str(r["id"]) for r in side if str(r["id"]) in answers
                      and r[KEY] != len(answers[str(r["id"])].get("evidence") or []))
    assert disagree == [], "样本本身两本账就不齐，①的「必须为空」得改成点名口径"

    mismatch = _payload(out, MISMATCH_NEEDLE, MISMATCH_TAIL)
    assert "None" not in mismatch, "把取不到当成不等＝R592 缺陷本体：%s" % mismatch
    assert mismatch == "无", "两本账逐枚全等，读数件却又报不齐：%s" % mismatch
    assert _list(out, ZERO_NEEDLE, ZERO_TAIL) == truth_zero, "「=0 的题号」必须等于逐枚真零，不许全列点名"
    assert _payload(out, UNKNOWN_NEEDLE, UNKNOWN_TAIL) == "无", "样本齐全时报了取不到，也是假话"


def test_table_column_and_the_mismatch_line_share_one_reading(capsys):
    """判据②：逐枚表那一列与「不等」行同源——表格列逐枚等于 sidecar 原文的读数。"""
    rc = _load("r592_run9_table").main(["--dir", str(RUN9_DIR), "--label", RUN9])
    out = capsys.readouterr().out
    assert rc == 0, out
    side = {str(r["id"]): r for r in _rows(RUN9_DIR / ("sidecar-%s.jsonl" % RUN9))}
    header, rows = _table(out)
    assert KEY in header, header
    assert set(rows) == set(side), (sorted(set(rows) ^ set(side)))[:8]
    col = header.index(KEY)
    wrong = {rid: cells[col] for rid, cells in rows.items() if cells[col] != str(side[rid][KEY])}
    assert wrong == {}, "表格列与 sidecar 原文对不上（逐枚点名差在哪）：%s" % sorted(wrong.items())[:8]


# ==================== ①②的件内最小正面样本：值在就绝不许打印成缺失 ====================

def test_a_present_value_is_never_printed_as_missing(tmp_path, capsys):
    """判据③ 前半：在册同形的最小三本账，两枚都有值 ⇒ 不许出现取不到/不齐/零枚。"""
    out = _read(tmp_path, capsys, "r592present", _copy(SIDECAR_ROWS), _copy(FRAME_ROWS),
                _copy(ANSWER_ROWS), name="r592_present")
    header, rows = _table(out)
    col = header.index(KEY)
    assert rows["report-01"][col] == "14" and rows["report-02"][col] == "6", rows
    assert _payload(out, MISMATCH_NEEDLE, MISMATCH_TAIL) == "无"
    assert _payload(out, UNKNOWN_NEEDLE, UNKNOWN_TAIL) == "无"
    assert _list(out, ZERO_NEEDLE, ZERO_TAIL) == []


# ==================== ③：真缺那一格必须如实报缺 ====================

def test_a_dropped_cell_is_reported_as_missing_not_as_zero_or_unequal(tmp_path, capsys):
    """判据③ 后半（K2 那一格）：sidecar 真缺 `evidence_n` ⇒ 点名取不到，且不许冒充零枚/不齐。"""
    module = _load("r592_dropped")
    out = _read(tmp_path, capsys, "r592drop", _copy(MISSING_SIDECAR_ROWS), _copy(FRAME_ROWS),
                _copy(ANSWER_ROWS), name="r592_drop")
    unknown = _list(out, UNKNOWN_NEEDLE, UNKNOWN_TAIL)
    assert [rid for rid, _state in unknown] == ["report-02"], unknown
    assert unknown[0][1] == module.EV_NO_KEY, unknown
    assert _list(out, ZERO_NEEDLE, ZERO_TAIL) == [], "取不到被折成了零枚"
    assert _payload(out, MISMATCH_NEEDLE, MISMATCH_TAIL) == "无", "取不到被冒充成了两本账不齐"
    header, rows = _table(out)
    assert rows["report-02"][header.index(KEY)] == module.EV_NO_KEY, rows["report-02"]
    assert rows["report-01"][header.index(KEY)] == "14", "一枚缺不许带走另一枚的读数"


@pytest.mark.parametrize("row, expected", [
    ({KEY: 14}, "value"),
    ({KEY: 0}, "zero"),                      # 真零必须读成 0，不许与「取不到」混成一格
    ({}, "missing"),                         # 缺格
    ({KEY: None}, "null"),
    ({KEY: "14"}, "not_int"),
    ({KEY: True}, "not_int"),                # bool 是 int 的子类，这一枚也不许当成 1 枚
])
def test_the_handler_names_why_it_cannot_read(row, expected):
    """判据③/② 的把手本体：交回读数或点名缺在哪一格，一律不就近折成 0。"""
    module = _load("r592_handler")
    states = {"value": (14, module.EV_OK), "zero": (0, module.EV_OK),
              "missing": (None, module.EV_NO_KEY), "null": (None, module.EV_NULL),
              "not_int": (None, module.EV_NOT_INT)}
    assert getattr(module, HANDLER)({"qa-01": row}, "qa-01") == states[expected]
    assert getattr(module, HANDLER)({}, "qa-01") == (None, module.EV_NO_ROW)
    assert getattr(module, HANDLER)({"qa-01": {KEY: 3.0}}, "qa-01") == (None, module.EV_NOT_INT)


# ==================== ④：判据不许放宽成「None 也算齐」 ====================

def test_a_real_difference_is_still_named_per_id(tmp_path, capsys):
    """判据④：值在而数目不等 ⇒ 「不等」必须逐枚点名 (题号, 侧车枚数, 交回枚数)。"""
    answers = _copy(ANSWER_ROWS)
    answers[0]["evidence"] = answers[0]["evidence"][:13]      # 交回去的比侧车少一枚
    out = _read(tmp_path, capsys, "r592real", _copy(SIDECAR_ROWS), _copy(FRAME_ROWS), answers,
                name="r592_real")
    assert _list(out, MISMATCH_NEEDLE, MISMATCH_TAIL) == [("report-01", 14, 13)], out
    assert _payload(out, UNKNOWN_NEEDLE, UNKNOWN_TAIL) == "无"


# ==================== ⑤：结构钉——全件只许一枚把手，且只喂 sidecar 那本账 ====================

def _key_of(node):
    if isinstance(node, ast.Constant) and node.value == KEY:
        return KEY
    if isinstance(node, ast.Name) and node.id == "SIDECAR_EVIDENCE_KEY":
        return KEY
    return None


def test_only_one_handler_in_the_whole_script_reads_evidence_n():
    """判据②：第二处各自把手就是本单的缺陷本体，所以拿 AST 钉死它不许复活。"""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    handlers = [(n.lineno, n.end_lineno) for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == HANDLER]
    assert len(handlers) == 1, "取数把手必须恰好一枚：%s" % handlers
    low, high = handlers[0]
    offenders = []
    for node in ast.walk(tree):
        key = None
        if isinstance(node, ast.Subscript):
            key = _key_of(node.slice)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr in ("get", "pop") and node.args):
            key = _key_of(node.args[0])
        if key and not low <= node.lineno <= high:
            offenders.append((node.lineno, key))
    assert offenders == [], ("把手之外又开了一处取数（R592 缺陷本体复活）：%s" % offenders)


def test_the_handler_is_fed_the_sidecar_book_and_used_from_one_reading():
    """判据②：把手只许喂 sidecar 那本账；三处读数同取一份 ev_readings。"""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == HANDLER]
    assert len(calls) == 1, "调用点也只许一处：%s" % [c.lineno for c in calls]
    fed = calls[0].args[0]
    assert isinstance(fed, ast.Name) and fed.id == "sidecar", (
        "把帧账行喂给把手就是 R592 的那枚错：%s" % ast.dump(fed))
    loads = [n.lineno for n in ast.walk(tree)
             if isinstance(n, ast.Name) and n.id == "ev_readings" and isinstance(n.ctx, ast.Load)]
    assert len(loads) >= 4, ("=0 名册/取不到名册/两本账对判/表格列必须同用一份读数：%s" % sorted(loads))
