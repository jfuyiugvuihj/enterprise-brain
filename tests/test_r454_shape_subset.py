"""R454 判据①的常驻钉：形状子集必须逐字节等于题源本体里那几行（现值 33 行，规模由 planner 定）。

为什么钉得这么死（跟进单 §128 二节原文：「只准按 id 从在册 105 题里选，一个字都不许改」）：

返工令（09-28 第 5 条）把 report 族配额从 3 抬到 12，族配额之和变成 33，子集规模随之从 30 抬到 33；本件里所有规模与配额数字都现读 planner，不写第二份。
子集一旦允许顺手改题面，它就不再是同一把尺，形状与分数读数都失去可比性；
而评测集本体被 `tests/test_evaluation_report.py` 钉住，改本体要业主单独批。
本单的子集**不改题**，所以不触发那条审批——前提是这条钉真的咬得住。

本机抓到的反面先例（数字为 09-28 现取，写在这里是为了说明这条判据不是凭空收紧）：
仓里上一代子集 `docs/testing/bank-run8p2-subset20.jsonl` 是把题源行重新 json.dumps
烤出来的——id 冒号后面多了一个空格、行尾从 CRLF 变成 LF，20 行里与本体字节等值的是 **0 行**。
按判据①的口径，那件今天就是一枚假子集；本文件把它变成可跑的数，不留在散文里。

反证两把（本文件后四枚用例）：
- 塞一枚不在 105 里的 id ⇒ 红；把"在册 105"这层成员检查摘掉 ⇒ 同一枚变异溜过去
  ⇒ 红来自成员检查这一被测行为，不是 JSON 形状的巧合。
- 改动任一字 ⇒ 红；而只看 id 的检查对它是**瞎的** ⇒ 红来自逐字节比对这一步。

全程离线：只读仓内文本文件，零模型、零网络、零容器。
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval_window_planner.py"
BANK_PATH = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"
SUBSET_PATH = REPO_ROOT / "docs" / "testing" / "bank-shape-subset-30.jsonl"
PRECEDENT_PATH = REPO_ROOT / "docs" / "testing" / "bank-run8p2-subset20.jsonl"


def _load_planner():
    "按路径加载量具件。dataclass 要靠 sys.modules 里的登记认出本模块，顺序不能反。"
    name = "eval_window_planner"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


planner = _load_planner()

BANK_SIZE = 105
#: 子集规模、族清单、最低配额一律现读 planner：本件落第二份数字，配额一抬就漂。
SUBSET_SIZE = planner.SUBSET_SIZE
FAMILY_FLOOR = planner.FAMILY_FLOOR
OVERRIDES = dict(planner.FAMILY_FLOOR_OVERRIDES)
FAMILIES = tuple(planner.FAMILIES)


def _bank_lines():
    return [line for line in BANK_PATH.read_bytes().splitlines(keepends=True) if line.strip()]


def _subset_lines():
    return [line for line in SUBSET_PATH.read_bytes().splitlines(keepends=True) if line.strip()]


def _ids(lines):
    return [json.loads(line.decode("utf-8"))["id"] for line in lines]


def _family(qid):
    return qid.split("-", 1)[0]


# ==================== 判据①本体 ====================


def test_the_bank_is_still_the_in_register_one_hundred_and_five():
    "子集的唯一来源就是这 105 枚；本体漂了，本文件所有结论同时作废，所以先钉本体。"
    lines = _bank_lines()
    assert len(lines) == BANK_SIZE, len(lines)
    assert len(set(_ids(lines))) == BANK_SIZE


def test_subset_is_exactly_thirty_rows_and_every_row_is_verbatim():
    "判据①主断言：30 行，逐行字节等值于本体同一枚 id 那一行（含行尾 CRLF）。"
    subset = SUBSET_PATH.read_bytes()
    lines = _subset_lines()
    assert len(lines) == SUBSET_SIZE, len(lines)
    report = planner.compare_subset(_bank_lines(), subset)
    assert report["equal"] == SUBSET_SIZE, report["rows"]
    assert report["foreign"] == []
    assert report["mutated"] == []
    # 独立复算一遍，不套 planner 的实现：本体的行集合必须原样包含子集每一行。
    bank_set = set(_bank_lines())
    assert all(line in bank_set for line in lines)


def test_subset_keeps_the_compact_serialisation_and_the_crlf_endings():
    """反面先例的形状检查：重序列化会把紧凑分隔符烤成带空格的写法，把 CRLF 烤成 LF。

    这一枚不靠"看起来一样"，直接数分隔符与行尾——上一代子集就是在这儿漏掉的。
    """
    raw = SUBSET_PATH.read_bytes()
    assert raw.count(b"\r\n") == SUBSET_SIZE, raw.count(b"\r\n")
    assert raw.count(b"\n") == SUBSET_SIZE, "混进裸 LF ⇒ 行尾被重新烤过"
    assert raw.count(b'"id": ') == 0, "出现带空格的 id 分隔符 ⇒ 行被重序列化过"
    assert raw.endswith(b"\r\n")


def test_subset_ids_are_unique_and_stay_in_bank_order():
    lines = _subset_lines()
    ids = _ids(lines)
    assert len(set(ids)) == SUBSET_SIZE
    bank_ids = _ids(_bank_lines())
    positions = [bank_ids.index(qid) for qid in ids]
    assert positions == sorted(positions), "子集把题序打乱了：窗内题序必须可追到本体顺序"


def test_every_family_meets_its_floor_and_the_two_priced_ones_clear_three():
    counts = {}
    for qid in _ids(_subset_lines()):
        counts[_family(qid)] = counts.get(_family(qid), 0) + 1
    assert sorted(counts) == list(FAMILIES), sorted(counts)
    assert sum(counts.values()) == SUBSET_SIZE
    for fam in FAMILIES:
        floor = OVERRIDES.get(fam, FAMILY_FLOOR)
        assert counts[fam] >= floor, (fam, counts[fam], floor)


def test_the_selection_rule_reproduces_the_subset_bytes_exactly():
    """子集不是手抄的：按登记规则重算一遍，字节必须与盘上那件相同。

    这条同时钉住两件事——谁进子集由规则决定（可复算，不是人工挑一组好过的题），
    以及落盘走的是逐字节搬运而不是字符串往返。
    """
    lines = _bank_lines()
    ids = _ids(lines)
    alloc = planner.allocate_families(ids)
    picked = planner.select_ids(ids, alloc)
    assert planner.emit_subset(lines, picked) == SUBSET_PATH.read_bytes()
    assert picked == _ids(_subset_lines())


def test_the_allocation_rule_lands_on_the_subset_size_and_respects_floors():
    alloc = planner.allocate_families(_ids(_bank_lines()))
    assert sum(alloc.values()) == SUBSET_SIZE
    for fam in FAMILIES:
        assert alloc[fam] >= OVERRIDES.get(fam, FAMILY_FLOOR)


def test_validate_subset_accepts_the_file_in_tree():
    report = planner.validate_subset(_bank_lines(), SUBSET_PATH.read_bytes())
    assert report["count"] == SUBSET_SIZE
    assert report["equal"] == SUBSET_SIZE


def test_the_subset_size_is_exactly_the_sum_of_family_floors():
    """返工令第 5 条的算式：子集规模＝Σ 族配额；report 抬到 12 之后是 12+3+9×2＝33。

    把 12 这一枚数写死在这儿是有意的：它是总控裁下来的配额（D 三格要吃满报告档那 12 枚），
    不是本件自己拍的。谁把它改回 3，这条当场红——配额落空比枚数少更坏，因为它会让
    队列相拿到一张只覆盖四分之一报告档的子集，还自称跑过 D 三格。
    """
    floors = [max(FAMILY_FLOOR, OVERRIDES.get(fam, 0)) for fam in FAMILIES]
    assert OVERRIDES["report"] == planner.FAMILY_FLOOR_OVERRIDES["report"] == 12, OVERRIDES
    assert OVERRIDES["approval"] == planner.FAMILY_FLOOR_OVERRIDES["approval"] == 3
    assert SUBSET_SIZE == planner.SUBSET_SIZE == sum(floors) == 33, (SUBSET_SIZE, floors)
    assert len(_subset_lines()) == SUBSET_SIZE
    counts = {}
    for qid in _ids(_subset_lines()):
        counts[_family(qid)] = counts.get(_family(qid), 0) + 1
    assert counts["report"] == 12 and counts["approval"] == 3, counts


def test_counter_evidence_the_previous_generation_subset_would_not_pass_this_ruler():
    """把「上一代子集是假子集」这句话变成可跑的数（只读那一件，不碰它）。"""
    if not PRECEDENT_PATH.exists():
        pytest.skip("上一代子集不在了：这条反面先例随件一起退役")
    report = planner.compare_subset(_bank_lines(), PRECEDENT_PATH.read_bytes())
    assert report["equal"] == 0, report["rows"]
    # 题号仍可点名（id 没被改），所以它们落进"改动"这一桶而不是"外来"那一桶。
    assert report["foreign"] == [], report["foreign"]
    assert len(report["mutated"]) == report["count"] == 20, (report["mutated"], report["count"])


# ==================== 反证钉 1：塞一枚不在 105 里的 id ⇒ 红 ====================


def _ghost_line():
    payload = {
        "id": "doc-99",
        "tier": "问答",
        "category": "文档问答",
        "question": "这枚题从来不在册。",
        "answer": "编的",
        "must_contain": ["编的"],
        "requires_evidence": False,
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\r\n"


def _subset_with_a_foreign_swap():
    """把 doc 族那一枚换成 **同族** 的外来题（doc-99）：行数不变、每一族配额都不变。

    为什么要挑同族的外来 id：本单返工后每一族都正好压在最低配额上（report 12、
    approval 3、其余各 2），随便抽掉任何一枚真题都会先撞族配额那条线——
    红是红了，但红错了地方，成员检查这一被测行为就白钉。id 用 doc-99：
    族名照旧是 doc，配额位不动，只有"这枚 id 不在册"这一条能拦它。
    """
    lines = _subset_lines()
    ghost = _ghost_line()
    target = next(index for index, line in enumerate(lines)
                  if _family(planner.line_id(line)) == "doc")
    mutated = b"".join(ghost if index == target else line for index, line in enumerate(lines))
    return lines, mutated, ghost


def test_counter_evidence_a_foreign_id_turns_the_subset_red():
    _, mutated, _ = _subset_with_a_foreign_swap()
    with pytest.raises(planner.SubsetError) as caught:
        planner.validate_subset(_bank_lines(), mutated)
    message = str(caught.value)
    assert "doc-99" in message, message
    assert "不在本体" in message, message


def test_counter_evidence_the_foreign_id_pin_bites_on_membership_not_on_shape():
    """摘掉"必须来自在册 105"这一层：同一枚外来行就溜过去了。

    上一枚用例的红**只来自成员检查**，不来自 JSON 形状、行数、族配额或编码——
    这正是判据①那句"只准按 id 从在册 105 题里选"的被测行为，摘掉它钉子就没牙。
    """
    lines, mutated, ghost = _subset_with_a_foreign_swap()
    assert len(lines) == SUBSET_SIZE
    # 先把 ghost 冒充成"在册"（摘掉在册集合这一约束）：连 validate 都一路放行。
    tolerant = planner.compare_subset(_bank_lines() + [ghost], mutated)
    assert tolerant["foreign"] == []
    assert tolerant["equal"] == SUBSET_SIZE
    assert planner.validate_subset(_bank_lines() + [ghost], mutated)["equal"] == SUBSET_SIZE
    # 真·在册集合里没有它：比对器当场把它报成外来行，等值数掉到 29。
    strict = planner.compare_subset(_bank_lines(), mutated)
    assert strict["foreign"] == ["doc-99"], strict["foreign"]
    assert strict["equal"] == SUBSET_SIZE - 1
    with pytest.raises(planner.SubsetError):
        planner.validate_subset(_bank_lines(), mutated)


# ==================== 反证钉 2：改动任一字 ⇒ 红 ====================


def _one_character_mutation():
    lines = _subset_lines()
    target = next(index for index, line in enumerate(lines) if b"500" in line)
    mutated_line = lines[target].replace("500元/晚".encode("utf-8"), "600元/晚".encode("utf-8"))
    assert mutated_line != lines[target], "没找到可改的那一字，用例本身要重开"
    rebuilt = b"".join(
        mutated_line if index == target else line for index, line in enumerate(lines)
    )
    return lines, target, mutated_line, rebuilt


def test_counter_evidence_one_changed_character_turns_the_subset_red():
    _, _, _, rebuilt = _one_character_mutation()
    with pytest.raises(planner.SubsetError) as caught:
        planner.validate_subset(_bank_lines(), rebuilt)
    assert "改了一个字也算改" in str(caught.value), str(caught.value)


def test_counter_evidence_an_id_only_check_is_blind_to_the_changed_character():
    """摘掉逐字节比对、只留 id 检查：同一枚改字溜过去。

    这枚用例标出第二把牙的实位：红来自"整行含行尾一起比"这一步，
    不来自 id 唯一性，也不来自 JSON 可解析性。
    """
    lines, target, mutated_line, rebuilt = _one_character_mutation()
    assert planner.line_id(mutated_line) == planner.line_id(lines[target])
    report = planner.compare_subset(_bank_lines(), rebuilt)
    assert report["foreign"] == []
    assert report["duplicates"] == []
    assert report["mutated"] == [_ids([lines[target]])[0]]
    assert report["equal"] == SUBSET_SIZE - 1
    with pytest.raises(planner.SubsetError):
        planner.validate_subset(_bank_lines(), rebuilt)