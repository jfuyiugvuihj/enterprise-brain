"""R153 · 检索活动先验的强度校准：一根具名的、与腿宽解耦的名次界（全离线）。

跟进单 §78 三 判据①②③。R152 那版把 0.01×净值**加进** 1/(60+rank)，于是"值多少分"说话、
"能挪几名"取决于那一带有多挤：本文件跑真函数现量的读数是——一枚「采纳」在 5 名的腿里从第 5
名顶到第 1 名（走 4 名），在 40 名的腿里从第 40 名顶到第 21 名（走 19 名）；总控在 §78 二按另
一把量法量到 11 名。三种量法说的是同一件事：一个同事点一次就能决定这一条腿的第一名。

现在界写成 ACTIVITY_PRIOR_MAX_SHIFT_RANKS = 1 枚名次（正负两侧同一个数），位移由
rank_hits_by_activity 里"一条命中每轮至多参与一次相邻交换、交换轮数＝这根界"这个结构给出。
本文件每枚钉子都指名它挡哪种错法：

- 界的字面值与满格（反证一把：把 value 上界撑到 1.5 就红在这里）；
- 腿 5 / 12 / 40 各自的"最远从第几名顶到第几名"实测读数（反证一把：把界放宽一档就红在这里）；
- 界与出厂腿宽解耦：同一个信号在宽腿上不许比窄腿上走得更远；
- 判据②（R152 一字未松）：无信号／开关关着／输入非列表 ⇒ 交回**同一个对象**，不是等价的拷贝；
- 判据③：注记仍说得出"这篇凭什么排上来"，而且注记里一个内容字段都没有。

库与模型都不在场：计数是灌进去的假表，向量库与 embedding 根本不参与（本文件只调纯函数）。
"""
import ast
import json
import random
from pathlib import Path

import pytest

from app.rag import retriever as rt

ROOT = Path(__file__).resolve().parents[1]
CHAT_PY = ROOT / "app" / "api" / "v1" / "chat.py"

#: 判据①点名的三种腿宽：出厂那条（chat.py 里 k=5）、总控 §78 二端到端复用的 12、以及一把明显更宽的。
LEG_WIDTHS = (5, 12, 40)

#: 注记的全部键：多长一枚就是替答案侧开一个没人审计的口子（判据③：只有计数与名次）。
NOTE_KEYS = {
    "accepted",
    "rejected",
    "shift_ranks",
    "rank_score",
    "previous_rank",
    "new_rank",
    "places_moved",
}


def _hit(name):
    """形状与 retriever._hit_dicts 一致的命中：内容字段故意留着，好验先验一个字节都不碰它。"""
    return {
        "content": "body of " + name,
        "source": name,
        "chunk_index": 0,
        "classification": 1,
        "department": "finance",
        "retrieval_mode": rt.RETRIEVAL_MODE_SEMANTIC,
        "retrieval_reason": "",
    }


def _names(width):
    return ["doc%02d.txt" % index for index in range(width)]


def _rank(width, signals):
    """把 signals（下标 -> (采纳, 驳回)）灌进假计数表，走真函数，交回逐条可断言的读数。

    每行是 (source, previous_rank, new_rank, places_moved, note)。new_rank 既从返回次序里
    数出来、也从注记里读出来，两值必须相等——不然"位移"就只是注记自己写的故事。
    """
    names = _names(width)
    priors = {
        names[index]: {"accepted": accepted, "rejected": rejected}
        for index, (accepted, rejected) in signals.items()
    }
    assert any(rt.activity_prior_value(counts) for counts in priors.values()), (
        "本夹具只量「真有信号」的形状；全零形状交回同一个对象，由判据②那几枚钉看着"
    )
    ranked = rt.rank_hits_by_activity([_hit(name) for name in names], priors)
    rows = []
    for position, carrier in enumerate(ranked, start=1):
        note = carrier["activity_prior"]
        assert note["new_rank"] == position, "注记里的新名次与实际次序不符：" + str(note)
        assert note["places_moved"] == note["previous_rank"] - position
        rows.append((carrier["source"], note["previous_rank"], position, note["places_moved"], note))
    assert sorted(row[0] for row in rows) == sorted(names), "先验一个候选都不许多、都不许少"
    return names, rows


def _worst(rows):
    return max(abs(row[3]) for row in rows)


# ============================== 判据① 那根界：字面值、单位、满格 ==============================
def test_the_named_bound_is_one_place_and_a_whole_number_of_places():
    """界的字面值就是判据①的内容：一名。写成分数或写成 1.5 都是自相矛盾（位移按整档交换）。"""
    bound = rt.ACTIVITY_PRIOR_MAX_SHIFT_RANKS
    assert bound == 1, "先验对单条命中的最大位移必须是一枚名次；要改这句就连 §78 三 判据① 一起改"
    assert bound == int(bound), "这根界的单位是名次，只能取整枚：交换是按档发生的"
    assert bound > 0, "0 或负数意味着先验整个关掉，那要走开关，不是把界拧成 0"


def test_the_value_saturates_at_the_bound_and_a_single_signal_is_only_half_of_it():
    """强度与位移脱钩：到顶之后再点也不许多要一名，一枚采纳只买到半格。"""
    bound = float(rt.ACTIVITY_PRIOR_MAX_SHIFT_RANKS)
    assert rt.activity_prior_value({"accepted": 999, "rejected": 0}) == bound
    assert rt.activity_prior_value({"accepted": 0, "rejected": 999}) == -bound
    one = rt.activity_prior_value({"accepted": 1, "rejected": 0})
    assert one == pytest.approx(rt.ACTIVITY_PRIOR_SIGNAL_GAIN / (1 + rt.ACTIVITY_PRIOR_SMOOTHING))
    assert 0 < one < bound, "一枚采纳必须是半格而非满格：它只够挤过一位无信号的邻居，不该压过更强的证据"
    assert rt.activity_prior_value({"accepted": 3, "rejected": 0}) == bound, "三枚净采纳到顶，此后不再涨"


# ============================== 判据① 实测读数：腿宽 5 / 12 / 40 ==============================
@pytest.mark.parametrize("width", LEG_WIDTHS)
def test_a_saturated_adoption_at_the_tail_travels_exactly_one_place(width):
    """腿尾那篇满格采纳：最远只能从第 width 名顶到第 width-1 名，与腿有多宽无关。"""
    names, rows = _rank(width, {width - 1: (20, 0)})
    tail = next(row for row in rows if row[0] == names[-1])
    assert _worst(rows) == 1, "实测越界：" + str([row[3] for row in rows])
    assert (tail[1], tail[2], tail[3]) == (width, width - 1, 1), (
        "读数应当是「第 %d 名 → 第 %d 名」，一条 %d 名的腿里一枚信号最多买一名" % (width, width - 1, width)
    )


@pytest.mark.parametrize("width", LEG_WIDTHS)
def test_a_single_acceptance_at_the_tail_travels_the_same_one_place(width):
    """一枚采纳与二十枚采纳走的是同一名：强度不再兑换位移枚数，这就是"校准"本身。"""
    names, rows = _rank(width, {width - 1: (1, 0)})
    tail = next(row for row in rows if row[0] == names[-1])
    assert _worst(rows) == 1
    assert (tail[1], tail[2], tail[3]) == (width, width - 1, 1)
    assert tail[4]["shift_ranks"] < 1.0, "它只买到半格强度，但位移与满格同为一名——差别只在抢名额时"


@pytest.mark.parametrize("width", LEG_WIDTHS)
def test_a_rejected_head_sinks_one_place_and_no_further(width):
    """负侧对称：榜首被驳回只掉到第 2 名，不会因为下面全是采纳者就一路沉到底。"""
    names, rows = _rank(width, {0: (0, 20)})
    head = next(row for row in rows if row[0] == names[0])
    assert _worst(rows) == 1, "负侧越界：" + str([row[3] for row in rows])
    assert (head[1], head[2], head[3]) == (1, 2, -1)


@pytest.mark.parametrize("width", LEG_WIDTHS)
def test_a_wall_of_saturated_adoptions_cannot_crush_the_same_neighbour_twice(width):
    """其余全体满格、只头一名没打点：名额只有一个，头名至多掉一名，而不是被顶下去 width-1 名。"""
    names, rows = _rank(width, {index: (20, 0) for index in range(1, width)})
    assert _worst(rows) == 1, "一群满格采纳把同一名邻居挤下去多档：" + str([row[3] for row in rows])
    assert sum(1 for row in rows if row[3] == 1) == 1, "一轮里只许一次上位"
    assert sum(1 for row in rows if row[3] == -1) == 1
    assert [row[0] for row in rows] == [names[1], names[0]] + names[2:]


def test_equal_evidence_never_moves_and_the_same_batch_is_deterministic():
    """证据并列 ⇒ 一律保持原序（不靠排序算法的运气）；同一批输入两次跑必须逐字同序。"""
    signals = {index: (5, 0) for index in range(12)}
    first_names, first_rows = _rank(12, signals)
    assert [row[3] for row in first_rows] == [0] * 12, "并列证据一个名次都不许动"
    second_names, second_rows = _rank(12, signals)
    assert [row[0] for row in first_rows] == [row[0] for row in second_rows]
    mixed = {index: (index % 4, (index + 2) % 3) for index in range(12)}
    once = [row[0] for row in _rank(12, mixed)[1]]
    twice = [row[0] for row in _rank(12, mixed)[1]]
    assert once == twice


def test_the_promotion_slot_goes_to_the_stronger_evidence():
    """两个候选抢同一个空位时按证据强弱分配：一枚采纳不许顶掉三枚采纳的位置。"""
    names, rows = _rank(3, {1: (1, 0), 2: (3, 0)})
    assert [row[0] for row in rows] == [names[0], names[2], names[1]], (
        "第 3 名（三枚采纳，满格）拿走那一次交换；第 2 名（一枚采纳，半格）没抢到，反而让位"
    )
    moves = {row[0]: row[3] for row in rows}
    assert (moves[names[2]], moves[names[1]], moves[names[0]]) == (1, -1, 0)


@pytest.mark.parametrize("width", LEG_WIDTHS)
def test_a_seeded_battery_of_signal_patterns_keeps_every_travel_inside_the_bound(width):
    """把界钉在结构上而不是钉在某几个例子上：随机信号形状下位移一律 ≤1，且候选集合不变。"""
    rng = random.Random(20260921)
    examined = 0
    while examined < 120:  # 每一枚都真的过一遍函数，随机只用来生成形状，不用来决定断言
        signals = {
            index: (rng.randint(0, 25), rng.randint(0, 25))
            for index in range(width)
            if rng.random() < 0.45
        }
        if not any(
            rt.activity_prior_value({"accepted": a, "rejected": r}) for a, r in signals.values()
        ):
            continue  # 全零形状命中的是判据②那支（同一个对象），另有一枚钉看着它
        examined += 1
        names, rows = _rank(width, signals)
        assert sorted(row[0] for row in rows) == sorted(names)
        assert _worst(rows) <= int(rt.ACTIVITY_PRIOR_MAX_SHIFT_RANKS), (
            "越界形状：" + str(signals) + " -> " + str([row[3] for row in rows])
        )


# ============================== 判据① 后半：与腿宽解耦（现抠出厂 k，不手抄） ==============================
def _shipped_leg_widths():
    """AST 现抠 chat.py 里 retriever.search(...) 的 k 实参：本单一个字都不改它（那是 Laplace 写域）。"""
    widths = set()
    for node in ast.walk(ast.parse(CHAT_PY.read_text(encoding="utf-8-sig"))):
        if not isinstance(node, ast.Call) or getattr(node.func, "attr", "") != "search":
            continue
        for keyword in node.keywords:
            if keyword.arg == "k" and isinstance(keyword.value, ast.Constant):
                if isinstance(keyword.value.value, int):
                    widths.add(keyword.value.value)
    assert widths, "chat.py 里的 search(...) 不再带 k= 实参：腿宽得换个地方量（连本钉一起改）"
    return sorted(widths)


def test_the_bound_measures_the_same_on_the_shipped_leg_and_on_a_much_wider_one():
    """出厂腿宽与 40 名宽腿上的位移读数必须相同：这正是"界不随候选宽度漂"的可读数。"""
    readings = {}
    for width in sorted(set(_shipped_leg_widths()) | {max(LEG_WIDTHS)}):
        for signals in ({width - 1: (20, 0)}, {0: (0, 20)}, {width // 2: (1, 0)}):
            names, rows = _rank(width, signals)
            readings[(width, tuple(sorted(signals)))] = _worst(rows)
    assert set(readings.values()) == {1}, "界随腿宽漂了：" + repr(readings)


def test_rank_base_and_leg_length_appear_nowhere_in_the_transposition_bound():
    """界只由"交换轮数"给出：把 rank_base 换成任意值、把腿换成任意宽度，位移读数一个都不动。"""
    for width in LEG_WIDTHS:
        orders = set()
        for rank_base in (1, 60, 999):
            names = _names(width)
            priors = {names[-1]: {"accepted": 20, "rejected": 0}}
            hits = [_hit(name) for name in names]
            ranked = rt.rank_hits_by_activity(hits, priors, rank_base=rank_base)
            travels = [carrier["activity_prior"]["places_moved"] for carrier in ranked]
            assert max(abs(move) for move in travels) == 1, (rank_base, width, travels)
            assert all(
                carrier["activity_prior"]["rank_score"]
                == 1.0 / (rank_base + carrier["activity_prior"]["previous_rank"])
                for carrier in ranked
            ), "rank_base 只该活在这枚注记分里"
            orders.add(tuple(carrier["source"] for carrier in ranked))
        assert len(orders) == 1, "换了 rank_base 连次序都换了 ⇒ 界其实还藏在分值里：" + str(width)


# ============================== 判据② R152 那三支一字未松 ==============================
def test_no_signal_still_comes_back_as_the_very_same_list_object():
    """无信号（含净值 0 与全是争议样本）⇒ 同一个对象：不复制、不加键、不改序。"""
    hits = [_hit("a.txt"), _hit("b.txt")]
    assert rt.rank_hits_by_activity(hits, {}) is hits
    assert rt.rank_hits_by_activity(hits, {"a.txt": {"accepted": 0, "rejected": 0}}) is hits
    assert rt.rank_hits_by_activity(hits, {"a.txt": {"accepted": 5, "rejected": 5}}) is hits
    assert "activity_prior" not in hits[0], "无信号时连键都不许长出来"


def test_the_off_switch_and_non_list_inputs_come_back_untouched(monkeypatch):
    """开关关着走的是真开关（不是 enabled= 形参一把假把式）；非列表输入原样交回。"""
    monkeypatch.setenv(rt.ACTIVITY_PRIOR_ENV, "off")
    hits = [_hit("a.txt"), _hit("b.txt")]
    priors = {"a.txt": {"accepted": 20, "rejected": 0}}
    assert rt.rank_hits_by_activity(hits, priors, enabled=rt.activity_prior_enabled()) is hits
    monkeypatch.delenv(rt.ACTIVITY_PRIOR_ENV, raising=False)
    empty = []
    assert rt.rank_hits_by_activity(empty, priors) is empty, "空表也走判据②那支：同一个对象"
    for not_a_list in (None, 42, "a.txt", ({"source": "a.txt"},), {"source": "a.txt"}):
        assert rt.rank_hits_by_activity(not_a_list, priors) is not_a_list


def test_the_copied_hits_keep_their_own_fields_byte_for_byte():
    """真有信号时才复制：除注记之外，每条命中的其余键必须与原命中逐字相同。"""
    names = _names(6)
    original = [_hit(name) for name in names]
    originals = {
        hit["source"]: json.dumps(hit, ensure_ascii=False, sort_keys=True) for hit in original
    }
    ranked = rt.rank_hits_by_activity(original, {names[-1]: {"accepted": 12, "rejected": 0}})
    assert len(ranked) == len(original)
    assert all(carrier is not source for carrier, source in zip(ranked, original)), "有信号才复制"
    for carrier in ranked:  # 次序变了也要逐字对得上：先验只许添注记，不许改内容
        stripped = dict(carrier)
        stripped.pop("activity_prior")
        assert json.dumps(stripped, ensure_ascii=False, sort_keys=True) == (
            originals[carrier["source"]]
        ), "先验改动了命中自身的内容字段"


# ============================== 判据③ 注记：说得出为什么，也不越隐私 ==============================
def test_the_annotation_says_why_this_document_came_up():
    names, rows = _rank(5, {0: (0, 3), 4: (12, 0)})
    by_source = {row[0]: row for row in rows}
    assert [row[0] for row in rows] == [names[1], names[0], names[2], names[4], names[3]]
    adopted = by_source[names[4]]
    assert adopted[3] == 1, "满格采纳的那篇上位一名——界内的最大位移"
    note = adopted[4]
    assert set(note) == NOTE_KEYS, "注记的键清单就是答案侧的契约，多一枚少一枚都要先改判据"
    assert (note["accepted"], note["rejected"]) == (12, 0)
    assert note["shift_ranks"] == float(rt.ACTIVITY_PRIOR_MAX_SHIFT_RANKS)
    assert note["rank_score"] == 1.0 / (rt.ACTIVITY_PRIOR_RANK_BASE + note["previous_rank"]), (
        "名次分是注记，不是先验的容器：它必须等于本档名次分本身"
    )
    rejected = by_source[names[0]]
    assert (rejected[3], rejected[4]["accepted"], rejected[4]["rejected"]) == (-1, 0, 3), (
        "榜首被驳回就沉一名，注记说得出它为什么沉、沉了几名"
    )
    neighbour = by_source[names[1]]
    assert neighbour[3] == 1 and neighbour[4]["accepted"] == 0, (
        "没打点的邻居因驳回者下沉而浮上一名：它也在界内，计数为 0 就是它的理由"
    )
    assert by_source[names[2]][4]["places_moved"] == 0
    assert by_source[names[3]][4]["places_moved"] == -1, "被满格采纳者越过一位，正好一名"


def test_the_annotation_carries_no_content_and_no_query_anywhere():
    """注记里只有计数与名次：整枚字典序列化之后不许出现内容字段的值或字段名。"""
    names, rows = _rank(4, {3: (7, 0)})
    for row in rows:
        note = row[4]
        assert set(note) <= NOTE_KEYS
        dumped = json.dumps(note, ensure_ascii=False)
        assert "body of" not in dumped, "注记里出现了正文内容"
        for banned in ("content", "query", "question", "answer", "text", "excerpt"):
            assert banned not in dumped


def test_the_diagnostics_read_the_bound_in_places_rather_than_a_score_weight():
    """观测面：界以名次交回，分值时代那枚 weight 键不许悄悄回来。"""
    rt.reset_activity_priors()
    diagnostics = rt.activity_prior_diagnostics()
    assert diagnostics["max_shift_ranks"] == rt.ACTIVITY_PRIOR_MAX_SHIFT_RANKS == 1
    assert diagnostics["gain_per_signal"] == rt.ACTIVITY_PRIOR_SIGNAL_GAIN
    assert diagnostics["smoothing"] == rt.ACTIVITY_PRIOR_SMOOTHING
    assert "weight" not in diagnostics, (
        "weight 的单位是分值，加进 1/(60+rank) 之后一枚采纳能值 11 名（跟进单 §78 二）；"
        "要恢复它就连同本文件的界用例一起改，别只改判据"
    )


def test_malformed_hits_travel_through_without_breaking_the_ranking():
    """非字典命中拿不到先验、也不被注记，但照样参与名次：一条脏数据不许打断整条检索。"""
    hits = [_hit("a.txt"), "not-a-dict", _hit("b.txt")]
    ranked = rt.rank_hits_by_activity(hits, {"b.txt": {"accepted": 9, "rejected": 0}})
    assert [hit if not isinstance(hit, dict) else hit["source"] for hit in ranked] == [
        "a.txt",
        "b.txt",
        "not-a-dict",
    ]
    assert all("activity_prior" in hit for hit in ranked if isinstance(hit, dict))
    assert "not-a-dict" not in json.dumps(
        [hit.get("activity_prior") for hit in ranked if isinstance(hit, dict)], ensure_ascii=False
    )
