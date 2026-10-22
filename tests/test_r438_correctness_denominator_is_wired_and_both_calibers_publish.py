# -*- coding: utf-8 -*-
r"""R438 · correctness 的两把尺接线钉：丙案扣除进分母，历史那把尺一个字不动。

【本文件钉的三件事】
 1. 判据①：同一份报告里两把尺同时出。`answer_correctness` 的分母仍是全部题数（算法与语义
    一字未动 ⇒ run2..run9 的历史报告可比）；`answer_correctness_scorable_subset` 按可判子集出。
 2. 判据②③：进分母的枚数由题源里的 `r401.disposition` 现算，报告里三个数（全部题数 /
    点名扣除数 / 进分母数）齐备且算式自洽，逐枚被扣题带着 id、查无出处的词、为什么今天
    不可考、去向。本件与判分器都不许出现手抄的题数：期望值一律从题源现算，整型字面量由
    下面的 AST 钉逐枚对质。
 3. 判据④：可判子集那把尺的分子只来自同一批被点名的可判题。摘掉任一枚丙的扣除资格，
    分子与分母必须一起动；出现「分子按全部题数、分母按可判子集」（比值 > 1）那种越界读数
    必须当场红，不许变成一份能看的报告。
 4. 判据⑨：第二把尺要能被看见。`/evaluations` 的读数面
    （`app/api/v1/observability.py::_report_metrics`）一格都不许抄清单——它逐格读报告里
    `scorable_subset` 那一格自己的键名（`app.quality.eval.scorability_metrics`）。抄一份键名
    清单就是第二本账（R346/R351/R377/R396/R400 那一族病）；派生不到锚点当场红，分叉报告按
    既有词汇表落 `unreadable`，本单不造新状态词、不给响应面加新键。
 5. 判据⑩：CLI 那一行（`scripts/run_quality_evaluation.py`）在历史四格之后**追加**第二把尺，
    行数不变、历史 token 的写法与顺序不变；那一行的文本由 `format_correctness_rulers` 从同一个
    `scorability_metrics` 拼出来，出口与命令行共用一把尺，谁也不许拼第二遍。

🔴 接线之前欠的那句话：tests/test_r401_unscorable_rows_are_named_not_dropped.py:14-15 自己写明
   「判分器在 app/quality/eval.py（本单写域外），它算的 answer_correctness 仍按全部题数出」。
   本单把那根线接上：题面、锚词、处置标记一个字节都没动，`tests/fixtures/**` 不在本单写域内。

【十二把反证刀的形状与预期读数】（判据⑤⑨⑩；a / c / f 走影子副本道：把 app/quality/eval.py 复制进
 tmp_path 后只改刀口那一行，真树全程只读；i 走 CLI 影子副本道；b / d / e 只改 tmp_path 里的夹具副本；
 g 用 monkeypatch 摘掉出口的派生调用；h / j / k / l 只改内存里的报告副本，真树与入库件全程只读）
 刀a 摘掉派生读取（`row_disposition` 里那一格 marker 读成 None）⇒ 扣除数退成零、分母退成
    全部题数、两把尺塌成一把 ⇒ 期望：**红**（同一套守恒断言在 mutant 读数上必须失败）
 刀b 把夹具里所有 disposition 改成甲 ⇒ 没有任何一枚该扣 ⇒ 期望：**绿**，且两把尺逐位相等
    （若不等就是假绿：那时分子分母本来就是同一批题）
 刀c 点名腿偷偷少报一枚丙（`return named_rows[1:]`）⇒ 计数腿与点名腿对不上、三数算式破
    ⇒ 期望：**红**（mutant 必须当场报错，而不是出一份「扣了分母却点不出人」的报告）
 刀d 把某枚丙的 must_contain 清空（或把那个词换掉）⇒ R401 判据②明令禁的那条捷径
    ⇒ 期望：**红**
 刀e 把某枚丙的 reason / pool 抹掉 ⇒ 扣除题没被点名 ⇒ 期望：**红**
刀f 分子来自全部题数而分母是可判子集 ⇒ 比值越界 ⇒ 期望：**红**（两道同源闸各咬一把：
   摘掉子集过滤那把、把分子换成全集计数那把）
刀g 摘掉出口的派生调用 ⇒ 报告里那一格还在、出口悄悄少一把尺，而记录照旧报 ok ⇒ 期望：**红**
   （断言落在「该有几格」上而不是落在状态码上：少一格比报错更难被发现，这正是判据⑨禁的病）
刀h 尺与账只有一半（只有抬头那把尺 / 只有账那一格）⇒ 出口当场拒，`_report_summary` 落既有
   词汇表的 `unreadable` + 空 metrics，且不长出响应面新键 ⇒ 期望：**红**
刀i 把 CLI 那一行行尾的派生摘掉（影子副本）⇒ 仍只印一行、历史四格俱在，但行里没有第二把尺
   ⇒ 期望：**红**（一行里少一把尺，比两行里两把都齐更糟；「只印一行」本身不是判据）
刀j 拿一份没有第二把尺的旧形状报告去拼 CLI 那一行 ⇒ 期望：**红**（不许只印一把尺交活）
刀k 出口逐条拒分叉的账：清单少报一枚 / 扣除数多一枚 / 进分母数被改大 / 尺越出 [0,1] /
   尺读不成数 / 分母非零却没有读数 / 账里那把尺与抬头那把不是同一个数 ⇒ 期望：**红**（七条逐一红）
刀l 点名清单长过出口条数上限 ⇒ 当场红，不许截断之后照旧报 ok ⇒ 期望：**红**

跑法（窗后由总控亲跑；本件只读真树 + 往 tmp_path 写副本）：
    python -m pytest -q tests/test_r438_correctness_denominator_is_wired_and_both_calibers_publish.py
    python scripts/r438_correctness_denominator.py
"""
import ast
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_PY = REPO_ROOT / "app" / "quality" / "eval.py"
FIXTURE_105 = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"
R401_SCRIPT = REPO_ROOT / "scripts" / "r401_anchor_provenance.py"
R438_SCRIPT = REPO_ROOT / "scripts" / "r438_correctness_denominator.py"
#: 判据⑨的出口面与判据⑩的命令行面：两枚都是只读取证对象，本单写域内、但下面的钉子只读不写。
OBSERVABILITY_PY = REPO_ROOT / "app" / "api" / "v1" / "observability.py"
CLI_PY = REPO_ROOT / "scripts" / "run_quality_evaluation.py"

MARKER_FIELD = "r401"
UNSCORABLE = "丙"
RESOLVED = "甲"
#: 故意答错时给的文本：本件用它把两把尺拉开，逐枚锚词都不在它里面（下面的钉会自己验）。
WRONG_ANSWER = "r438-intentionally-wrong-answer"

#: 反证刀的刀口：每一串都必须在盘上恰好命中一次，命中数不为 1 就中止（不猜行号）。
KNIFE_A_LAND = "    marker = row.get(SCORABILITY_MARKER_FIELD)"
KNIFE_A_BLOW = "    marker = None"
KNIFE_C_LAND = "    return named_rows"
KNIFE_C_BLOW = "    return named_rows[1:]"
KNIFE_F_NUMERATOR_LAND = '    correct_n = sum(bool(item["correct"]) for item in scorable)'
KNIFE_F_NUMERATOR_BLOW = '    correct_n = sum(bool(item["correct"]) for item in results)'
KNIFE_F_FILTER_LAND = '    scorable = [item for item in results if _plain_id(item["row"]) not in deducted_ids]'
KNIFE_F_FILTER_BLOW = "    scorable = list(results)"
#: 刀i 的刀口：CLI 那一行行尾追加的那一段（源码文本对质，命中数必须恰好一次，不猜行号）。
KNIFE_I_LAND = "        f\"p95_ms={report['latency_ms']['p95']} {format_correctness_rulers(report)}\""
KNIFE_I_BLOW = "        f\"p95_ms={report['latency_ms']['p95']}\""

#: 分母账的全部派生函数：AST 钉只扫这些函数体里的整型字面量。
DERIVATION_FUNCTIONS = (
    "_plain_id", "row_disposition", "_named_id", "unscorable_row_ids",
    "unscorable_records", "derive_scorability", "correctness_subset_ruler",
    # 判据⑨：出口那两枚读数面同样不许手抄题数，一起扫。
    "scorability_metrics", "format_correctness_rulers",
)

# --------------------------------------------------------------------------- 取数与写副本


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_fixture_rows(path: Path = FIXTURE_105) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


@pytest.fixture(scope="module")
def r401():
    """R401 的派生件（本单只读引用）：那本账是分母的唯一上游，字段名与处置集合都从它对齐。"""
    return _load_module("r401_anchor_provenance_r438", R401_SCRIPT)


@pytest.fixture(scope="module")
def rows():
    """题源＝真树里那份评测集：本件只读不写，改动一律只落在 tmp_path 的内存副本上。"""
    return read_fixture_rows()


def row_id(row: dict) -> str:
    return str(row.get("id", "") or "").strip()


def unscorable_ids(rows: list[dict]) -> list[str]:
    """独立于判分器的第二只眼：直接从题源读丙案题号，一行都不经过 app/quality/eval.py。"""
    return sorted(
        row_id(row)
        for row in rows
        if isinstance(row.get(MARKER_FIELD), dict)
        and row[MARKER_FIELD].get("disposition") == UNSCORABLE
    )


def marked_ids(rows: list[dict]) -> list[str]:
    return sorted(row_id(row) for row in rows if isinstance(row.get(MARKER_FIELD), dict))


def patched_rows(rows: list[dict], targets, *, disposition=None, blank_marker_key=None,
                 anchors=None) -> list[dict]:
    """只在内存副本上改题，随后写进 tmp_path：真树与 `tests/fixtures/**` 一个字都不动。"""
    wanted = set(targets)
    out = []
    for row in rows:
        if row_id(row) not in wanted:
            out.append(row)
            continue
        new = dict(row)
        if isinstance(new.get(MARKER_FIELD), dict):
            marker = dict(new[MARKER_FIELD])
            if disposition is not None:
                marker["disposition"] = disposition
            if blank_marker_key is not None:
                marker[blank_marker_key] = ""
            new[MARKER_FIELD] = marker
        if anchors is not None:
            new["must_contain"] = list(anchors)
        out.append(new)
    return out


def stripped_rows(rows: list[dict]) -> list[dict]:
    """把处置标记整格摘掉：模拟 R401 之前的题源，用来钉「历史那把尺没被接线动过」。"""
    return [{key: value for key, value in row.items() if key != MARKER_FIELD} for row in rows]


def write_fixture(tmp_path: Path, rows: list[dict], name: str) -> Path:
    path = tmp_path / name
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return path


def gold_text(row: dict) -> str:
    return " ".join([str(row.get("answer", ""))] + [str(t) for t in (row.get("must_contain") or [])])


def make_answer_fn(rows: list[dict], chosen):
    """偶数位的题给金标文本，其余给一句答非所问 ⇒ 两把尺的分子都是现数出来的。"""

    def answer_fn(row: dict) -> dict:
        text = gold_text(row) if row_id(row) in chosen else WRONG_ANSWER
        return {
            "answer": text,
            "evidence": [{"source_name": "制度与口径登记表", "locator": "第1行"}],
            "confidence_label": "high",
            "latency_ms": 100,
        }

    return answer_fn


def half_plan(rows: list[dict]):
    ids = [row_id(row) for row in rows]
    chosen = {ids[index] for index in range(0, len(ids), 2)}
    return chosen, make_answer_fn(rows, chosen)


def expected_ledger(rows: list[dict], chosen) -> dict:
    """期望值全部从题源现算：本件没有一枚手抄的题数。"""
    ids = [row_id(row) for row in rows]
    deducted = set(unscorable_ids(rows))
    scorable = [item for item in ids if item not in deducted]
    assert any(row_id(row) not in chosen for row in rows), "这套题全答对了，两把尺的差量不出来"
    for row in rows:
        terms = [str(term) for term in (row.get("must_contain") or [])]
        assert terms, "{0} 没有锚词，判分口径不唯一".format(row_id(row))
        assert all(term not in WRONG_ANSWER for term in terms), (
            "{0} 的锚词落进了「故意答错」文本里，本件的分子不可信".format(row_id(row)))
    return {
        "total_rows": len(ids),
        "deducted_n": len(deducted),
        "denominator_rows": len(scorable),
        "correct_all_rows": len([item for item in ids if item in chosen]),
        "correct_scorable": len([item for item in scorable if item in chosen]),
    }


# --------------------------------------------------------------------------- 公共断言


def assert_both_calibers(report: dict, fixture_rows: list[dict], chosen) -> dict:
    """两把尺的公共断言：绿件用它，反证刀也用它（刀必须让这里失败）。"""
    want = expected_ledger(fixture_rows, chosen)
    assert report["total"] == want["total_rows"], (
        "total 被改动了 ⇒ 判据①要的历史那把尺，分母就是全部题数")
    assert report["answer_correctness"] == round(
        want["correct_all_rows"] / want["total_rows"], 4), (
        "answer_correctness 不再是「全部答对 / 全部题数」⇒ 历史口径被接线改掉了")
    block = report.get("scorable_subset")
    assert isinstance(block, dict), "报告里没有可判子集那一格 ⇒ 第二把尺根本没接线"
    assert block["total_rows"] == want["total_rows"], "格子里的全部题数与 total 不是同一个数"
    assert block["deducted_n"] == want["deducted_n"], (
        "点名扣除数与题源里的丙案枚数不符 ⇒ 派生读取被摘掉了，两把尺塌成一把")
    assert block["denominator_rows"] == want["denominator_rows"], (
        "进分母数不等于「全部题数 − 点名扣除数」")
    assert block["denominator_rows"] == block["total_rows"] - block["deducted_n"], "三数算式破了"
    assert block["correct_n"] == want["correct_scorable"], (
        "分子不是从同一批被点名的可判题里数出来的 ⇒ 分子分母不同源")
    ruler = report.get("answer_correctness_scorable_subset")
    assert ruler is not None, "可判子集那把尺没出现在报告里"
    assert ruler == round(want["correct_scorable"] / want["denominator_rows"], 4), (
        "可判子集那把尺的读数不等于「可判答对 / 可判枚数」")
    assert ruler <= 1.0, "可判子集的比值大于 1 ⇒ 分子踩在了全部题数上"
    assert block["deducted_n"] == len(block["deducted_rows"]), (
        "扣除数与点名清单的枚数不等 ⇒ 有题被扣了分母却没被点名")
    return block


# --------------------------------------------------------------------------- 判据①..④


def test_both_calibers_publish_at_once_and_the_historical_denominator_is_all_rows(rows, tmp_path):
    """判据①：一份报告里两把尺同时出，历史那把的分母仍是全部题数，一把都不许藏。"""
    from app.quality.eval import evaluate_evaluation_set

    chosen, answer_fn = half_plan(rows)
    report = evaluate_evaluation_set(write_fixture(tmp_path, rows, "r438_full.jsonl"), answer_fn)
    block = assert_both_calibers(report, rows, chosen)
    assert report["answer_correctness"] != report["answer_correctness_scorable_subset"], (
        "两把尺读数一样：要么没题被扣，要么第二把尺根本没派生")
    assert block["deducted_n"] and block["denominator_rows"] < block["total_rows"]
    assert str(block["deducted_n"]) in block["rule"] and str(block["denominator_rows"]) in block["rule"]
    assert str(block["total_rows"]) in block["rule"], "分母规则没把三个数写明白"
    assert "evidence_coverage" in block["rule"], "要说清 total 与 evidence_coverage 仍按全部题数"
    assert block["basis"]


def test_the_historical_ruler_does_not_move_when_the_markers_are_stripped(rows, tmp_path):
    """判据①：把处置标记整格摘掉（＝R401 之前的题源），历史那把尺逐位不变。"""
    from app.quality.eval import evaluate_evaluation_set

    chosen, answer_fn = half_plan(rows)
    kept = evaluate_evaluation_set(write_fixture(tmp_path, rows, "kept.jsonl"), answer_fn)
    stripped = evaluate_evaluation_set(
        write_fixture(tmp_path, stripped_rows(rows), "stripped.jsonl"), answer_fn)
    for key in ("total", "answer_correctness", "evidence_coverage", "unsupported_claim_rate",
                "category_metrics", "latency_ms"):
        assert kept[key] == stripped[key], "{0} 被接线改动影响到了".format(key)
    assert stripped["scorable_subset"]["deducted_n"] == 0
    assert stripped["answer_correctness_scorable_subset"] == stripped["answer_correctness"]
    assert kept["answer_correctness_scorable_subset"] != stripped["answer_correctness_scorable_subset"], (
        "摘掉处置标记前后第二把尺纹丝不动 ⇒ 它的分母不是从标记派生的")


def test_the_denominator_carries_no_copied_row_counts(rows):
    """判据②：进分母的枚数只能派生——把派生函数体里的整型字面量拿现算的那三枚数对质。"""
    total = len(rows)
    deducted = len(unscorable_ids(rows))
    numbers = {total, deducted, total - deducted}
    source = EVAL_PY.read_text(encoding="utf-8")
    scanned = 0
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in DERIVATION_FUNCTIONS:
            scanned += 1
            ints = {
                item.value for item in ast.walk(node)
                if isinstance(item, ast.Constant) and isinstance(item.value, int)
                and not isinstance(item.value, bool)
            }
            stolen = sorted(ints & numbers)
            assert not stolen, "{0} 里出现了手抄的题数 {1}".format(node.name, stolen)
    assert scanned == len(DERIVATION_FUNCTIONS), "AST 扫到的派生函数少了几枚"
    assert source.count("row.get(SCORABILITY_MARKER_FIELD)") == 1, (
        "处置标记在判分器里被读了不止一处 ⇒ 两处读点迟早长成两套口径")


def test_the_app_ledger_and_the_r401_ledger_are_the_same_ledger(rows, r401):
    """判据②⑥：判分器那本账必须与 R401 派生件那本账逐格相等，字段名与处置集合同源于 R401。"""
    import app.quality.eval as ev

    block = ev.derive_scorability(rows)
    ledger = r401.denominator(rows)
    assert block["total_rows"] == ledger["total_rows"]
    assert block["deducted_n"] == ledger["unscorable_n"]
    assert block["denominator_rows"] == ledger["correctness_denominator"]
    assert sorted(block["deducted_ids"]) == sorted(ledger["unscorable_ids"])
    assert ev.SCORABILITY_MARKER_FIELD == r401.MARKER_FIELD
    assert set(ev.KNOWN_DISPOSITIONS) == set(r401.DISPOSITIONS)
    assert ev.UNSCORABLE_DISPOSITION == UNSCORABLE


def test_every_deducted_row_is_named_verbatim_with_reason_and_destination(rows, tmp_path):
    """判据③：逐枚点名（id + 为什么今天不可考 + 去向），文本原样取自 R401 的记录。"""
    from app.quality.eval import evaluate_evaluation_set

    chosen, answer_fn = half_plan(rows)
    block = assert_both_calibers(
        evaluate_evaluation_set(write_fixture(tmp_path, rows, "naming.jsonl"), answer_fn),
        rows, chosen)
    by_id = {row_id(row): row for row in rows}
    assert sorted(record["id"] for record in block["deducted_rows"]) == unscorable_ids(rows)
    reasons, destinations = set(), set()
    for record in block["deducted_rows"]:
        marker = by_id[record["id"]][MARKER_FIELD]
        assert record["reason"] == str(marker["reason"]).strip(), record["id"]
        assert record["destination"] == str(marker["pool"]).strip(), record["id"]
        assert record["missing_term"] == str(marker["missing_term"]).strip(), record["id"]
        assert record["disposition"] == UNSCORABLE
        assert record["question"] == str(by_id[record["id"]].get("question") or "")
        assert record["missing_term"] in [str(term) for term in by_id[record["id"]]["must_contain"]], (
            "{0} 被扣的理由挂在别的词上：题源里那个词才是查无出处的枚证".format(record["id"]))
        reasons.add(record["reason"])
        destinations.add(record["destination"])
    assert len(reasons) == len(block["deducted_rows"]), (
        "逐枚理由是同一句话复制的，不是每枚各自的「为什么今天不可考」")
    assert len(destinations) > 1, "去向只有一句套话，点不出这批题各自等谁"


def test_dropping_one_deduction_moves_numerator_and_denominator_together(rows, tmp_path):
    """判据④：摘掉任一枚丙的扣除资格，分子与分母必须一起动。"""
    from app.quality.eval import evaluate_evaluation_set

    chosen, answer_fn = half_plan(rows)
    before = evaluate_evaluation_set(
        write_fixture(tmp_path, rows, "before.jsonl"), answer_fn)["scorable_subset"]
    target = unscorable_ids(rows)[0]
    flipped = patched_rows(rows, [target], disposition=RESOLVED)
    after_report = evaluate_evaluation_set(
        write_fixture(tmp_path, flipped, "after.jsonl"), answer_fn)
    after = after_report["scorable_subset"]
    assert after["deducted_n"] == before["deducted_n"] - 1
    assert after["denominator_rows"] == before["denominator_rows"] + 1
    assert after["correct_n"] - before["correct_n"] == (1 if target in chosen else 0), (
        "分母动了一枚，分子却没跟着这枚题自己的对错动 ⇒ 两把尺不同源")
    assert target not in [record["id"] for record in after["deducted_rows"]]
    assert_both_calibers(after_report, flipped, chosen)


def synthetic_bing_rows(count: int) -> list[dict]:
    """全判丙的合成题：逐枚自带可点名的处置记录，用来量「分母为零」那个形状。"""
    return [
        {
            "id": "r438-syn-{0}".format(index),
            "tier": "问答",
            "category": "文档问答",
            "question": "合成题{0}的答案是什么？".format(index),
            "answer": "合成答案{0}".format(index),
            "must_contain": ["合成锚词{0}".format(index)],
            "requires_evidence": False,
            MARKER_FIELD: {
                "disposition": UNSCORABLE,
                "missing_term": "合成锚词{0}".format(index),
                "reason": "合成语料里没有「合成锚词{0}」这个词，今天不可考，等补语料".format(index),
                "pool": "待派池：合成题{0}".format(index),
            },
        }
        for index in range(count)
    ]


def test_an_empty_scorable_subset_reports_none_rather_than_a_fake_zero(tmp_path):
    """判据②的诚实出口：全部题都判丙 ⇒ 分母为零 ⇒ 那把尺报 None，不许报 0.0。"""
    from app.quality.eval import evaluate_evaluation_set

    subset_rows = synthetic_bing_rows(3)
    all_ids = {row_id(row) for row in subset_rows}
    report = evaluate_evaluation_set(
        write_fixture(tmp_path, subset_rows, "all_bing.jsonl"),
        make_answer_fn(subset_rows, all_ids))
    assert report["total"] == len(subset_rows)
    assert report["answer_correctness"] == 1.0, "历史那把尺仍按全部题数出，且这套全答对了"
    assert report["scorable_subset"]["denominator_rows"] == 0
    assert report["answer_correctness_scorable_subset"] is None, (
        "分母为零时把尺报成数字 ⇒ 0.0 会被读成「一道题都没答对」，那是假话")
    assert "note" in report["scorable_subset"], "分母为零要说清为什么这一把尺没有读数"


def test_a_fixture_without_markers_publishes_identical_rulers(tmp_path):
    """判据⑥：R123 / R205a 那几族的合成夹具没有处置标记 ⇒ 两把尺逐位相等。"""
    from app.quality.eval import evaluate_evaluation_set

    plain_rows = [
        {
            "id": "r438-plain-{0}".format(index),
            "category": "文档问答",
            "question": "合成 plain 题{0}？".format(index),
            "answer": "合成 plain 答案{0}".format(index),
            "must_contain": ["合成 plain 锚词{0}".format(index)],
            "requires_evidence": False,
        }
        for index in range(3)
    ]
    report = evaluate_evaluation_set(
        write_fixture(tmp_path, plain_rows, "plain.jsonl"),
        make_answer_fn(plain_rows, {row_id(plain_rows[0])}))
    assert report["scorable_subset"]["deducted_n"] == 0
    assert report["scorable_subset"]["deducted_rows"] == []
    assert report["answer_correctness_scorable_subset"] == report["answer_correctness"]


def test_the_read_side_ledger_script_agrees_with_the_report(tmp_path):
    """判据②：读侧取数口不许另算一套——它印的数必须与判分器那格逐位相等，且同样零手抄。"""
    script = _load_module("r438_ledger_script", R438_SCRIPT)
    fixture_rows = read_fixture_rows()
    result = script.cross_check(fixture_rows)
    assert result["mismatches"] == [], "两本账分叉了：" + " / ".join(result["mismatches"])
    out = tmp_path / "ledger.json"
    assert script.main(["--fixture", str(FIXTURE_105), "--json", str(out)]) == 0
    published = json.loads(out.read_text(encoding="utf-8"))
    block = result["block"]
    ints = {
        item.value for item in ast.walk(ast.parse(R438_SCRIPT.read_text(encoding="utf-8")))
        if isinstance(item, ast.Constant) and isinstance(item.value, int)
        and not isinstance(item.value, bool)
    }
    for key in ("total_rows", "deducted_n", "denominator_rows"):
        assert published[key] == block[key]
        assert not (ints & {block[key]}), "读侧件里抄了 {0}＝{1}".format(key, block[key])


# --------------------------------------------------------------------------- 反证刀


def mutant_eval(tmp_path: Path, tag: str, land: str, blow: str):
    """影子副本道：把 eval.py 复制进 tmp_path，只改刀口那一行；真树全程只读。"""
    source = EVAL_PY.read_text(encoding="utf-8")
    hits = source.count(land)
    assert hits == 1, "刀口 {0!r} 在盘上命中 {1} 次（必须恰好一次，否则本刀证明不了任何事）".format(
        land, hits)
    path = tmp_path / "eval_mutant_{0}.py".format(tag)
    path.write_text(source.replace(land, blow), encoding="utf-8")
    return _load_module("r438_mutant_{0}".format(tag), path)


def test_knife_a_collapsing_the_derived_read_collapses_the_two_rulers(rows, tmp_path):
    """刀a（判据⑤a，期望红）：摘掉派生读取 ⇒ 第二把尺退成全部题数那把 ⇒ 公共断言必须失败。"""
    mutant = mutant_eval(tmp_path, "a", KNIFE_A_LAND, KNIFE_A_BLOW)
    chosen, answer_fn = half_plan(rows)
    report = mutant.evaluate_evaluation_set(
        write_fixture(tmp_path, rows, "knife_a.jsonl"), answer_fn)
    assert report["scorable_subset"]["deducted_n"] == 0, "刀口没咬到：摘掉读取后仍报得出扣除数"
    assert report["answer_correctness_scorable_subset"] == report["answer_correctness"], (
        "刀a 要让两把尺塌成一把，这里却量出了差值 ⇒ 本刀没落地")
    with pytest.raises(AssertionError):
        assert_both_calibers(report, rows, chosen)


def test_knife_b_relabeling_every_row_resolved_makes_the_two_rulers_equal(rows, tmp_path):
    """刀b（判据⑤b，守恒钉，期望绿）：所有处置都改成甲 ⇒ 没有一枚该扣 ⇒ 两把尺逐位相等。"""
    from app.quality.eval import evaluate_evaluation_set

    all_resolved = patched_rows(rows, marked_ids(rows), disposition=RESOLVED)
    assert len(marked_ids(all_resolved)) == len(marked_ids(rows))
    assert unscorable_ids(all_resolved) == []
    chosen, answer_fn = half_plan(rows)
    report = evaluate_evaluation_set(
        write_fixture(tmp_path, all_resolved, "knife_b.jsonl"), answer_fn)
    assert_both_calibers(report, all_resolved, chosen)
    assert report["scorable_subset"]["denominator_rows"] == report["total"]
    assert report["scorable_subset"]["deducted_rows"] == []
    assert report["answer_correctness"] != 1.0, "这套题全答对了，相等是白得的，钉不住越界形状"
    assert report["answer_correctness_scorable_subset"] == report["answer_correctness"], (
        "该扣的枚数为零时两把尺居然不等 ⇒ 第二把尺的分母不是从处置标记派生的")


def test_knife_c_a_shortened_roster_breaks_the_three_number_equation(rows, tmp_path):
    """刀c（判据⑤c，期望红）：点名腿偷偷少报一枚 ⇒ 计数腿与点名腿对不上 ⇒ 报告不出。"""
    mutant = mutant_eval(tmp_path, "c", KNIFE_C_LAND, KNIFE_C_BLOW)
    chosen, answer_fn = half_plan(rows)
    with pytest.raises(mutant.ScorabilityDerivationError) as caught:
        mutant.evaluate_evaluation_set(write_fixture(tmp_path, rows, "knife_c.jsonl"), answer_fn)
    assert "没被点名" in str(caught.value), (
        "报错形状不对：这把刀应当咬在「扣了分母却点不出人」上")


def test_knife_d_emptying_or_swapping_a_bing_anchor_is_refused(rows, tmp_path):
    """刀d（判据⑤d，期望红）：把某枚丙的锚词清空或换掉 ⇒ R401 判据②明令禁的那条捷径。"""
    from app.quality.eval import ScorabilityDerivationError, evaluate_evaluation_set

    chosen, answer_fn = half_plan(rows)
    target = unscorable_ids(rows)[0]
    for label, anchors in (("emptied", []), ("swapped", ["r438-刀口-换进去的词"])):
        mutated = patched_rows(rows, [target], anchors=anchors)
        with pytest.raises(ScorabilityDerivationError) as caught:
            evaluate_evaluation_set(
                write_fixture(tmp_path, mutated, "knife_d_{0}.jsonl".format(label)), answer_fn)
        assert "锚词" in str(caught.value), label


def test_knife_e_an_unnamed_deduction_is_refused(rows, tmp_path):
    """刀e（判据⑤e，期望红）：抹掉某枚丙的理由 / 去向 / 缺的词 ⇒ 扣除题没被点名 ⇒ 红。"""
    from app.quality.eval import ScorabilityDerivationError, evaluate_evaluation_set

    chosen, answer_fn = half_plan(rows)
    target = unscorable_ids(rows)[0]
    for key, needle in (("reason", "没被点名"), ("pool", "没被点名"), ("missing_term", "锚词")):
        with pytest.raises(ScorabilityDerivationError) as caught:
            evaluate_evaluation_set(
                write_fixture(tmp_path, patched_rows(rows, [target], blank_marker_key=key),
                              "knife_e_{0}.jsonl".format(key)), answer_fn)
        assert needle in str(caught.value), key


def test_knife_f_a_numerator_from_all_rows_is_refused_as_out_of_range(rows, tmp_path):
    """刀f（判据④⑤，期望红）：分子踩在全部题数上、分母是可判子集 ⇒ 比值越界 ⇒ 当场报错。"""
    from app.quality.eval import evaluate_evaluation_set

    all_ids = {row_id(row) for row in rows}
    gold_fn = make_answer_fn(rows, all_ids)
    clean = evaluate_evaluation_set(write_fixture(tmp_path, rows, "knife_f_clean.jsonl"), gold_fn)
    assert clean["answer_correctness_scorable_subset"] == 1.0, (
        "全题答对时可判子集那把尺就该是满的；它一旦被读成别的数，下面的越界刀就量不到东西")
    assert clean["scorable_subset"]["correct_n"] == clean["scorable_subset"]["denominator_rows"]

    for tag, land, blow in (
        ("numerator", KNIFE_F_NUMERATOR_LAND, KNIFE_F_NUMERATOR_BLOW),
        ("filter", KNIFE_F_FILTER_LAND, KNIFE_F_FILTER_BLOW),
    ):
        mutant = mutant_eval(tmp_path, tag, land, blow)
        with pytest.raises(mutant.ScorabilityDerivationError) as caught:
            mutant.evaluate_evaluation_set(
                write_fixture(tmp_path, rows, "knife_f_{0}.jsonl".format(tag)), gold_fn)
        assert "不同源" in str(caught.value), tag


# --------------------------------------------------------------------------- 判据⑨⑩：出口与 CLI


def subset_report(tmp_path: Path, fixture_rows: list[dict], name: str):
    """用判分器真跑一份报告（窗内不打模型：answer_fn 是本地金标），供出口与 CLI 两格读。"""
    from app.quality.eval import evaluate_evaluation_set

    chosen, answer_fn = half_plan(fixture_rows)
    report = evaluate_evaluation_set(write_fixture(tmp_path, fixture_rows, name), answer_fn)
    return chosen, report


def face_names() -> tuple:
    """出口该认哪两把尺的名字：从判分器的常量读，本件同样不抄第二份清单。"""
    from app.quality.eval import SCORABLE_SUBSET_REPORT_KEY, SUBSET_RULER_KEY

    return SCORABLE_SUBSET_REPORT_KEY, SUBSET_RULER_KEY


def outlet_face(report: dict) -> dict:
    """独立于出口的第二只眼：出口该出现哪些格，从报告那一格自己的键名推出来，不抄清单。"""
    report_key, ruler_key = face_names()
    prefix = f"{report_key}_"
    face: dict = {}
    for key, value in report[report_key].items():
        if key == ruler_key or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            face[f"{prefix}{key}"] = value
        elif isinstance(value, list) and value and all(isinstance(item, str) for item in value):
            face[f"{prefix}{key}"] = list(value)
    if report.get(ruler_key) is not None:
        face[ruler_key] = report[ruler_key]
    return face


def assert_outlet_face(metrics: dict, report: dict) -> None:
    """出口面与判分器那本账逐格对质：少一格就是静默降级，多一格就是另长了第二本账。"""
    report_key, ruler_key = face_names()
    want = outlet_face(report)
    missing = sorted(key for key, value in want.items() if metrics.get(key) != value)
    assert not missing, "出口少了/错了这些格：" + repr(missing) + "（该有 " + repr(sorted(want)) + "）"
    family = (f"{report_key}_", ruler_key)
    extras = sorted(key for key in metrics if key.startswith(family) and key not in want)
    assert not extras, "出口长出了账上没有的格：" + repr(extras)


def historical_metrics_only(payload: dict) -> dict:
    """既有那七格（total / 三把比值 / latency 三格）：判据⑨只许追加，不许改它们一个字。"""
    return {
        "total": payload["total"],
        "answer_correctness": payload["answer_correctness"],
        "evidence_coverage": payload["evidence_coverage"],
        "unsupported_claim_rate": payload["unsupported_claim_rate"],
        "latency_count": float(payload["latency_ms"]["count"]),
        "latency_average": float(payload["latency_ms"]["average"]),
        "latency_p95": float(payload["latency_ms"]["p95"]),
    }


def shipped_shape_report() -> dict:
    """本单接线之前入库的那批件的形状：根本没有第二把尺那两格。"""
    return {
        "total": 30,
        "answer_correctness": 0.87,
        "evidence_coverage": 1.0,
        "unsupported_claim_rate": 0.03,
        "category_metrics": {"文档问答": {"correctness": 0.9, "total": 10}},
        "latency_ms": {"count": 30, "average": 812.5, "p95": 1400},
    }


def test_the_observability_outlet_publishes_both_rulers_and_the_named_roster(rows, tmp_path):
    """判据⑨①③：`/evaluations` 的读数面两把尺同报、三数齐备、点名清单逐枚上出口。"""
    from app.api.v1 import observability
    from app.quality.eval import SCORABLE_SUBSET_REPORT_KEY, SUBSET_RULER_KEY

    chosen, report = subset_report(tmp_path, rows, "outlet.jsonl")
    block = assert_both_calibers(report, rows, chosen)
    metrics = observability._report_metrics(report)
    assert_outlet_face(metrics, report)
    assert metrics[SUBSET_RULER_KEY] == report[SUBSET_RULER_KEY], "第二把尺上了出口却不是同一个数"
    for key in ("total_rows", "deducted_n", "denominator_rows", "correct_n"):
        assert metrics[f"{SCORABLE_SUBSET_REPORT_KEY}_{key}"] == block[key], key
    assert block["denominator_rows"] == block["total_rows"] - block["deducted_n"], "三数算式破了"
    assert metrics[f"{SCORABLE_SUBSET_REPORT_KEY}_deducted_ids"] == block["deducted_ids"], (
        "点名清单没进出口 ⇒ 出口只报了扣了多少，没报扣了谁")
    assert sorted(metrics[f"{SCORABLE_SUBSET_REPORT_KEY}_deducted_ids"]) == unscorable_ids(rows), (
        "出口上点名的那些题号与题源里的丙案不是同一批")
    assert len(block["deducted_ids"]) <= observability.MAX_LIST_ITEMS, (
        "今天的点名清单已经长出出口的条数上限了：先报总控，别让出口少一格")
    for key, value in metrics.items():
        assert isinstance(value, (int, float, list)), f"{key} 上了出口却不是读数"
    for historical, expected in historical_metrics_only(report).items():
        assert metrics[historical] == expected, f"{historical} 被接线改动影响到了"


def test_the_route_lists_both_rulers_for_a_scorable_report(rows, tmp_path, monkeypatch):
    """判据⑨的 HTTP 面：`GET /api/v1/evaluations` 里那条记录必须带第二把尺与点名清单。"""
    from fastapi.testclient import TestClient

    from app.common import auth
    from app.common.auth import create_token
    from app.main import app

    registry = {}
    monkeypatch.setattr(auth, "get_user", lambda username: registry.get(username))
    registry["r438-admin-outlet"] = {
        "id": "u-r438-admin-outlet",
        "username": "r438-admin-outlet",
        "role": "admin",
        "department": "研发部",
    }

    chosen, report = subset_report(tmp_path, rows, "route.jsonl")
    directory = tmp_path / "reports"
    directory.mkdir()
    (directory / "r438-run.json").write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("EVALUATION_REPORT_DIRS", str(directory))

    body = TestClient(app).get(
        "/api/v1/evaluations",
        headers={"Authorization": f"Bearer {create_token('r438-admin-outlet')}"}).json()
    records = [item for item in body["reports"] if item["id"] == "r438-run"]
    assert len(records) == 1, body["reports"]
    assert records[0]["status"] == "ok", records[0]
    assert_outlet_face(records[0]["metrics"], report)


def test_a_report_without_the_second_ruler_keeps_its_historical_face_word_for_word(tmp_path):
    """判据⑥⑨：接线前入库那种没有第二把尺的件，出口一格都不许多、一格都不许少。"""
    from app.api.v1 import observability

    shipped = shipped_shape_report()
    assert observability._report_metrics(shipped) == historical_metrics_only(shipped), (
        "旧件的读数面被接线改动动了 ⇒ 历史报告不能再按老样子读")
    path = tmp_path / "shipped-like.json"
    path.write_text(json.dumps(shipped, ensure_ascii=False), encoding="utf-8")
    record = observability._report_summary(path, source=observability.REPORT_SOURCE_CONFIGURED)
    assert record["status"] == "ok", "旧件被接线判成读不出来 ⇒ 历史报告失明了"


def test_the_outlet_and_the_cli_take_no_scorability_names_from_a_hand_written_ledger():
    """判据⑨⑩的反抄钉：两枚读数面里都不许出现第二把尺的键名字面，也不许有第二个读点。"""
    report_key, ruler_key = face_names()
    outlets = {
        OBSERVABILITY_PY: "scorability_metrics(",
        CLI_PY: "format_correctness_rulers(",
    }
    for path, read_point in outlets.items():
        source = path.read_text(encoding="utf-8")
        for needle in (ruler_key, report_key):
            assert needle not in source, f"{path.name} 抄了键名清单：{needle}"
        assert source.count(read_point) == 1, (
            f"{path.name} 对分母账的读点不止一处 ⇒ 两处读迟早长成两套口径")


def assert_single_line_readout(line: str, report: dict) -> None:
    """CLI 那一行的公共断言：绿件用它，反证刀也用它（刀必须让这里失败）。"""
    report_key, ruler_key = face_names()

    assert "\n" not in line.strip(), "第二把尺被拆成了第二行：§7-C 认的是 stdout 的一行形状"
    for token, value in (("correctness=", report["answer_correctness"]),
                         (f"{ruler_key}=", report[ruler_key])):
        assert f"{token}{value:.4f}" in line, (
            "那一行里没有 {0}{1:.4f}：{2}".format(token, value, line))
    block = report[report_key]
    for key in ("total_rows", "deducted_n", "denominator_rows", "correct_n"):
        assert f"{key}={block[key]}" in line, f"那一行少报了分母账上的 {key}：{line}"


def drive_cli(tmp_path: Path, fixture_rows: list[dict], answer_fn, *, tag: str,
              land: str | None = None, blow: str | None = None):
    """跑 scripts/run_quality_evaluation.py 的 main()（或它的影子副本），把它印的那一行交回。

    影子副本道：真树全程只读，刀口只落在 tmp_path 里那份副本上。批准账本那两枚环境变量临时摘掉
    ——否则门里的侧车会替本件决定报告形状，还会让甲案那一行多印一行，「只印一行」就没法对质了。
    """
    import contextlib
    from io import StringIO

    fixture = write_fixture(tmp_path, fixture_rows, f"cli_{tag}.jsonl")
    answers = tmp_path / f"answers_{tag}.jsonl"
    collected = []
    for row in fixture_rows:
        payload = dict(answer_fn(row))
        payload["id"] = row_id(row)
        collected.append(payload)
    answers.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in collected),
        encoding="utf-8")
    out = tmp_path / f"report_{tag}.json"

    source = CLI_PY.read_text(encoding="utf-8")
    if land is None:
        # 🔴 真树那份直接传给加载器，不许经过任何局部名：R253 的名字表不分作用域，
        # 一旦染了就让全文同名局部全部连坐（本单踩过两次）。
        module = _load_module(f"r438_cli_{tag}", CLI_PY)
    else:
        hits = source.count(land)
        assert hits == 1, f"刀口 {land!r} 在 CLI 里命中 {hits} 次（必须恰好一次）"
        assert blow is not None, "给了刀口就得给刀"
        mutant_path = tmp_path / f"cli_mutant_{tag}.py"
        mutant_path.write_text(source.replace(land, blow), encoding="utf-8")
        module = _load_module(f"r438_cli_{tag}", mutant_path)

    held = {key: os.environ.pop(key, None) for key in ("EVAL_APPROVAL_LEDGER", "EVAL_SIDECAR")}
    old_argv = list(sys.argv)
    sys.argv = ["run_quality_evaluation.py", "--fixture", str(fixture),
                "--answers", str(answers), "--output", str(out)]
    buffer = StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            module.main()
    finally:
        sys.argv = old_argv
        for key, value in held.items():
            if value is not None:
                os.environ[key] = value
    printed = [item for item in buffer.getvalue().splitlines() if item.strip()]
    assert len(printed) == 1, f"CLI 那一行现在是 {len(printed)} 行：{printed}"
    return printed[0], json.loads(out.read_text(encoding="utf-8"))


def test_the_cli_reports_both_rulers_on_one_line_and_keeps_the_historical_tokens(rows, tmp_path):
    """判据⑩①：CLI 同一行行尾追加第二把尺；行数、历史四格的写法与顺序一个字不动。"""
    report_key, ruler_key = face_names()

    chosen, answer_fn = half_plan(rows)
    line, saved = drive_cli(tmp_path, rows, answer_fn, tag="clean")
    assert_single_line_readout(line, saved)
    # 历史那四格逐字不动，且必须排在前面：run2..run9 的跑分叙事认的就是这一段。
    historical = "evaluated={0} correctness={1:.4f} evidence={2:.4f} p95_ms={3}".format(
        saved["total"], saved["answer_correctness"], saved["evidence_coverage"],
        saved["latency_ms"]["p95"])
    assert line.startswith(historical + " "), (
        "历史那四格不再是老样子（写法/顺序/小数位都被改了）⇒ 判据①要的可比性没了：{0}".format(line))
    assert line.index(ruler_key) >= len(historical) + 1, (
        "第二把尺插进了历史四格中间 ⇒ 那一行的历史段不再与历史报告逐字可比")
    assert line.index(ruler_key) < line.index("{0}[".format(report_key)), (
        "分母账那一串没紧跟在尺后面")


# --------------------------------------------------------------------------- 判据⑨⑩的反证刀


def test_knife_g_blinding_the_outlet_derivation_loses_a_cell_in_silence(rows, tmp_path, monkeypatch):
    """刀g（判据⑨的反证，期望红）：摘掉出口的派生调用 ⇒ 出口悄悄少掉第二把尺，记录照旧报 ok。

    这一把量的正是判据⑨禁的那种病：报告里那一格明明在，出口上没有。少一格比报错更难被发现，
    所以断言必须落在「该有几格」上，不是落在状态码上。摘之前先验一遍全脸，证明本刀真摘掉了东西。
    """
    from app.api.v1 import observability
    from app.quality.eval import SUBSET_RULER_KEY

    chosen, report = subset_report(tmp_path, rows, "knife_g.jsonl")
    assert SUBSET_RULER_KEY in report, "判分器自己都没写第二把尺，本刀无从可摘"
    assert_outlet_face(observability._report_metrics(report), report)
    monkeypatch.setattr(observability, "scorability_metrics", lambda payload, **kwargs: {})
    metrics = observability._report_metrics(report)
    assert SUBSET_RULER_KEY not in metrics, "刀口没咬到：摘掉派生之后出口仍带着第二把尺"
    assert metrics == historical_metrics_only(report), (
        "摘掉派生之后出口还留着别的尺 ⇒ 本刀没落地")
    path = tmp_path / "knife_g_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    record = observability._report_summary(path, source=observability.REPORT_SOURCE_CONFIGURED)
    assert record["status"] == "ok", (
        "摘掉派生之后记录反而报错了：那说明本刀量的是报错，不是「静默少一格」")
    with pytest.raises(AssertionError):
        assert_outlet_face(metrics, report)


def test_knife_h_a_half_wired_scorability_face_is_refused_and_lands_on_unreadable(rows, tmp_path):
    """刀h（判据⑨，期望红）：尺与账只有一半 ⇒ 出口当场红，并按既有词汇表落 unreadable。"""
    from app.api.v1 import observability
    from app.quality.eval import (SCORABLE_SUBSET_REPORT_KEY, SUBSET_RULER_KEY,
                                  ScorabilityDerivationError)

    chosen, report = subset_report(tmp_path, rows, "knife_h.jsonl")
    ruler_only = {key: value for key, value in report.items()
                  if key != SCORABLE_SUBSET_REPORT_KEY}
    ledger_only = {key: value for key, value in report.items() if key != SUBSET_RULER_KEY}
    assert SUBSET_RULER_KEY in ruler_only, "刀口没咬到：摘掉账那一格之后报告里真没尺了？"
    assert SCORABLE_SUBSET_REPORT_KEY not in ruler_only
    assert SUBSET_RULER_KEY not in ledger_only, "刀口没咬到：摘掉抬头那把尺之后报告里还留着尺"
    assert SCORABLE_SUBSET_REPORT_KEY in ledger_only

    broken = None
    for name, payload in (("ruler_only", ruler_only), ("ledger_only", ledger_only)):
        with pytest.raises(ScorabilityDerivationError):
            observability._report_metrics(payload)
        path = tmp_path / "knife_h_{0}.json".format(name)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        broken = observability._report_summary(path, source=observability.REPORT_SOURCE_CONFIGURED)
        assert broken["status"] == "unreadable", name
        assert broken["metrics"] == {}, name
        assert broken["size_bytes"] > 0 and broken["modified_at"], (
            name + "：fail closed 把记录自身的既有那几格也一起抹了")

    good_path = tmp_path / "knife_h_good.json"
    good_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    good = observability._report_summary(good_path, source=observability.REPORT_SOURCE_CONFIGURED)
    assert good["status"] == "ok"
    assert_outlet_face(good["metrics"], report)
    assert set(broken) - set(good) == set(), (
        "分叉记录长出了响应面新键 ⇒ 那是总控落笔的变更（docs/api/contract-v1.md 那张表），"
        "本单只许用既有词汇表 fail closed")
    assert "category_count" not in broken, (
        "非 ok 记录今天就不带 category_count（出口只在 ok 路径上写它），"
        "本刀必须与既有 unreadable 同形，不许另造一种形状")


def test_knife_k_the_outlet_refuses_every_face_it_cannot_anchor(rows, tmp_path):
    """刀k（判据⑨③④，期望红）：出口对七种分叉形状逐条红，一条都不许静默过关。"""
    from app.api.v1 import observability
    from app.quality.eval import (SCORABLE_SUBSET_REPORT_KEY, SUBSET_RULER_KEY,
                                  ScorabilityDerivationError, scorability_metrics)

    chosen, report = subset_report(tmp_path, rows, "knife_k.jsonl")
    base = report[SCORABLE_SUBSET_REPORT_KEY]
    roster = list(base["deducted_ids"])
    ruler_value = base[SUBSET_RULER_KEY]
    assert roster and ruler_value is not None, "这份报告没有可对质的账与尺，本刀空转"
    assert_outlet_face(observability._report_metrics(report), report)

    def tampered(**changes):
        block = dict(base)
        block.update(changes)
        return {**report, SCORABLE_SUBSET_REPORT_KEY: block}

    cases = {
        "点名清单少报一枚": tampered(deducted_ids=roster[:-1]),
        "扣除数比题源多一枚": tampered(deducted_n=base["deducted_n"] + 1),
        "进分母数被改大": tampered(denominator_rows=base["denominator_rows"] + 1),
        "尺踩在全部题数上（比值越界）": {**tampered(), SUBSET_RULER_KEY: ruler_value + 1},
        "尺读不成数": {**tampered(), SUBSET_RULER_KEY: "这不是数"},
        "分母非零却没有读数": {**tampered(), SUBSET_RULER_KEY: None},
        "账里那把尺与抬头那把不是同一个数": tampered(**{SUBSET_RULER_KEY: ruler_value + 0.25}),
    }
    limit = observability.MAX_LIST_ITEMS
    for label, payload in cases.items():
        with pytest.raises(ScorabilityDerivationError):
            scorability_metrics(payload, list_limit=limit)
        with pytest.raises(ScorabilityDerivationError):
            observability._report_metrics(payload)
    assert len(cases) == 7, "本刀的形状数掉了：一把都没少才算咬得住"


def test_knife_l_an_over_capped_roster_is_refused_instead_of_truncated(rows, tmp_path):
    """刀l（判据⑨，期望红）：清单长过出口条数上限 ⇒ 当场红，不许截断之后照旧报 ok。"""
    from app.api.v1 import observability
    from app.quality.eval import (SCORABLE_SUBSET_REPORT_KEY, ScorabilityDerivationError,
                                  scorability_metrics)

    chosen, report = subset_report(tmp_path, rows, "knife_l.jsonl")
    roster = report[SCORABLE_SUBSET_REPORT_KEY]["deducted_ids"]
    limit = observability.MAX_LIST_ITEMS
    assert len(roster) <= limit, "今天的点名清单已经长出出口上限 ⇒ 先报总控，别让出口少一格"
    face = scorability_metrics(report, list_limit=limit)
    assert len(face[f"{SCORABLE_SUBSET_REPORT_KEY}_deducted_ids"]) == len(roster), (
        "清单在出口里被截短了 ⇒ 少报几枚还照旧报 ok，正是判据⑨禁的静默少一格")
    with pytest.raises(ScorabilityDerivationError):
        scorability_metrics(report, list_limit=len(roster) - 1)


def test_knife_i_dropping_the_second_ruler_from_the_cli_line_goes_red(rows, tmp_path):
    """刀i（判据⑩的反证，期望红）：把行尾那段派生摘掉 ⇒ 仍只印一行、历史四格俱在，但少一把尺。

    这一把证明「只印一行」本身不是判据：一行里少一把尺，比两行里两把都齐更糟。
    """
    from app.quality.eval import SUBSET_RULER_KEY

    chosen, answer_fn = half_plan(rows)
    line, saved = drive_cli(tmp_path, rows, answer_fn, tag="knife_i",
                            land=KNIFE_I_LAND, blow=KNIFE_I_BLOW)
    assert SUBSET_RULER_KEY not in line, "刀口没咬到：摘掉行尾派生之后那一行仍带着第二把尺"
    assert "evaluated=" in line and "correctness=" in line and "p95_ms=" in line, (
        "刀i 只该摘掉第二把尺，历史那四格不许一起消失")
    with pytest.raises(AssertionError):
        assert_single_line_readout(line, saved)


def test_knife_j_a_report_without_the_second_ruler_cannot_feed_the_cli_line(tmp_path):
    """刀j（判据⑩，期望红）：拿旧形状报告去拼那一行 ⇒ 当场红，不许只印一把尺交活。"""
    from app.quality.eval import ScorabilityDerivationError, format_correctness_rulers

    report_key, ruler_key = face_names()
    shipped = historical_metrics_only(shipped_shape_report())
    assert ruler_key not in shipped and report_key not in shipped, (
        "旧形状件里居然带着第二把尺 ⇒ 本刀没有可对质的东西")
    with pytest.raises(ScorabilityDerivationError):
        format_correctness_rulers(shipped)
