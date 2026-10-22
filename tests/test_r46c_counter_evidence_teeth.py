# -*- coding: utf-8 -*-
r"""R46 差格 a 的反证刀——八把，victim 同时覆盖本单新钉与在册钉本身。

派工词点名的三把是 K1（摘写口）／K2（把派生改成写死）／K3（摘权限门）；跟进单 §141 R527 判据 7
另要求反证不少于五把、且 victim 必须点名在册钉本身，所以这里做到八把，其中两把的 victim 就长在
tests/test_r46_activity_signals.py 那两枚在册钉上（K2 与 K3 各一枚）。

机械口径抄 R578 那笔（跟进单 §141 的同一套）：

- 摘刀一律在**内存影子**里做：mutant_text 从不写盘，install_mutation 只把变了的那几枚顶层绑定
  临时装进活模块，出门逐枚装回并核对每一枚把手没被换过。
- 每把刀进刀前后各核一次被摘件的 sha256（前 12 位），记进 SHA_LEDGER；最后一枚总清点钉再数一遍，
  并且与进门那一刻的指纹逐枚比对——被跟踪文件全程只读。
- 每把刀都配一枚正控：同一套机械不摘任何一刀，点名的 victim 必须先绿——否则红是它本来就红。
- 锚点必须现取唯一（命中 0 或大于 1 ⇒ 这把刀无法被执行，反证就是空的，当场红）。

八把的落点：

- K1 摘写口：feedback 里那一步"载荷四格以外的字段一律拒收"变成 no-op。
- K2 把派生改成写死：retriever 里点击那一路不再读表里的两枚计数，改吃两枚常量。
- K3 摘权限门：_visibility_decision 永远放行——这一枚是两路共用的，摘它新旧两本账一起红。
- K4 摘跨用户闸：点击账读腿里那道"别人的行回来了就当场关账"的结构闸摘掉。
- K5 摘样本数下限：confidence 恒为 1，第一枚点击就能替整篇定序。
- K6 放宽合并界：两路相加之后不夹回那一根 ±1 名，界变两名。
- K7 摘 0019 的名次 CHECK：库里那道非负有界的形状闸没了（走 R253 的影子根，盘上一字节不动）。
- K8 摘写后作废：点击落库之后不再作废排序侧快照，回执与排序两本账分家。
"""
import hashlib
import inspect
from pathlib import Path
import pytest
from tests import _temp_edit_overlay as overlay
from tests.test_r466_mutation_does_not_leak_into_live_module import install_mutation
from app.api.v1 import feedback
from app.rag import retriever as rt
import test_r46_activity_signals as r46
import test_r46c_engagement_prior as w2
import test_r46c_engagement_signals as w1

REPO = Path(__file__).resolve().parents[1]
FEEDBACK_PATH = REPO / "app" / "api" / "v1" / "feedback.py"
RETRIEVER_PATH = REPO / "app" / "rag" / "retriever.py"
MIGRATION_PATH = REPO / "migrations" / "0019_document_engagement_events.sql"
#: 全程只读的三枚被跟踪／交付件：每把刀进出门各取一次指纹，最后一枚钉数总账。
TRACKED = (FEEDBACK_PATH, RETRIEVER_PATH, MIGRATION_PATH)

#: 在册钉那两枚的名字：判据 7 要 victim 落在别人写的件上，不是只落在自写件上。
IN_REGISTER_VICTIMS = {
    "r46::no_signals_returns_the_same_object",
    "r46::cross_department_batch_is_denied",
}


def _sha12(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


FINGERPRINT_AT_IMPORT = {path: _sha12(path) for path in TRACKED}
SHA_LEDGER = []
_CUT_TAGS = set()
_RED_VICTIMS = set()


def _call(victim):
    """直接调那枚用例：需要 monkeypatch 的自己带一枚，用完立刻 undo。"""
    holder = pytest.MonkeyPatch()
    try:
        if "monkeypatch" in inspect.signature(victim).parameters:
            victim(holder)
        else:
            victim()
    finally:
        holder.undo()


def _outcome(victim):
    """交回 (红不红, 读数)：红 = 这枚 victim 不绿，无论它抛的是断言还是别的什么。"""
    try:
        _call(victim)
    except AssertionError as exc:
        first = str(exc).splitlines()
        return True, "AssertionError: " + (first[0] if first else "")
    except Exception as exc:  # noqa: BLE001 - 摘刀之后任何失守都算红
        return True, exc.__class__.__name__
    return False, ""


def _read_text(path):
    """按盘上的字读（保住 CRLF）：影子文本与锚点计数都必须对着真字节来。"""
    return open(path, "r", encoding="utf-8", newline="").read()


def _cut_python(tag, module, path, anchor, mutant, victims):
    """内存影子摘刀：mutant 只进 install_mutation，盘上那枚文件全程只读。"""
    text = _read_text(path)
    before = _sha12(path)
    hits = text.count(anchor)
    assert hits == 1, (tag, "锚点命中 " + str(hits) + " 处，这把刀无法被执行")
    entry = {"tag": tag, "file": path.name, "before": before, "after": None, "victims": []}
    SHA_LEDGER.append(entry)
    with install_mutation(module, path, text.replace(anchor, mutant)):
        for name, victim in victims:
            red, reading = _outcome(victim)
            assert red, (
                tag + " 摘刀之后 " + name + " 竟然还是绿的：这把刀等于没动任何东西"
            )
            entry["victims"].append({"victim": name, "reading": reading})
            _RED_VICTIMS.add(name)
    after = _sha12(path)
    entry["after"] = after
    assert after == before, tag + " 出窗之后盘上的字节变了：被跟踪件必须全程只读"
    _CUT_TAGS.add(tag)
    print(
        "[r46c] " + tag + " " + path.name + " " + before + " -> " + after
        + " victims=" + ",".join(name for name, _ in victims)
    )

class _MigrationCut(overlay.ShadowEdit):
    """0019 那枚形状 CHECK 走影子根：变异只落 %TEMP% 那份副本，盘上的字全程只读。"""

    tag = "r46c"

    def __init__(self, path, anchor, replacement):
        super().__init__(path)
        self.anchor = anchor
        self.replacement = replacement

    def mutate(self, text):
        hits = text.count(self.anchor)
        assert hits == 1, "0019 的锚点命中 " + str(hits) + " 处"
        return text.replace(self.anchor, self.replacement)


def _cut_migration(tag, path, anchor, replacement, victims):
    text = _read_text(path)
    before = _sha12(path)
    assert text.count(anchor) == 1, (tag, "锚点不唯一")
    entry = {"tag": tag, "file": path.name, "before": before, "after": None, "victims": []}
    SHA_LEDGER.append(entry)
    with _MigrationCut(path, anchor, replacement):
        for name, victim in victims:
            red, reading = _outcome(victim)
            assert red, tag + " 摘刀之后 " + name + " 竟然还是绿的：这把刀等于没动任何东西"
            entry["victims"].append({"victim": name, "reading": reading})
            _RED_VICTIMS.add(name)
    after = _sha12(path)
    entry["after"] = after
    assert after == before, tag + " 出窗之后盘上的字节变了"
    _CUT_TAGS.add(tag)
    print("[r46c] " + tag + " " + path.name + " " + before + " -> " + after
          + " victims=" + ",".join(name for name, _ in victims))

def _lines(*parts):
    """把多行锚点拼成盘上那一笔：本仓的 .py 与 .sql 都是 CRLF，锚点必须同形。"""
    return (chr(13) + chr(10)).join(parts)


#: 八把刀的落点。锚点一律现取唯一（命中数不等于 1 当场红），victim 逐枚点名。
KNIVES = [
    {
        "tag": "K1",
        "kind": "python",
        "module": feedback,
        "path": FEEDBACK_PATH,
        "anchor": _lines(
            '    unexpected = sorted(str(key) for key in set(payload) - ENGAGEMENT_ALLOWED_FIELDS)',
            '    if not unexpected:',
            '        return',
        ),
        "mutant": _lines(
            '    unexpected = sorted(str(key) for key in set(payload) - ENGAGEMENT_ALLOWED_FIELDS)',
            '    if True:  # 反证 K1：写口那一手摘掉，四格以外的字段不再被拦',
            '        return',
        ),
        "victims": [
            ("w1.rejection_log_names_fields",
             w1.test_the_rejection_log_names_the_field_and_never_the_value),
        ],
    },
    {
        "tag": "K2",
        "kind": "python",
        "module": rt,
        "path": RETRIEVER_PATH,
        "anchor": _lines(
            '        clicks = int(counts.get("clicks") or 0)',
            '        views = int(counts.get("views") or 0)',
        ),
        "mutant": _lines(
            '        clicks = 7  # 反证 K2：写死，不再从 0019 那两枚计数派生',
            '        views = 3',
        ),
        "victims": [
            ("w2.neutral_when_nobody_clicked",
             w2.test_a_source_nobody_clicked_holds_the_neutral_value),
            ("r46::no_signals_returns_the_same_object",
             r46.test_no_signals_returns_the_very_same_list_object_not_an_equal_copy),
        ],
    },
    {
        "tag": "K3",
        "kind": "python",
        "module": feedback,
        "path": FEEDBACK_PATH,
        "anchor": _lines(
            '    if not scope.allows(row):',
            '        return False, "permission_denied"',
        ),
        "mutant": _lines(
            '    if False:  # 反证 K3：权限门摘掉——采纳/驳回与点击/浏览共用这一枚',
            '        return False, "permission_denied"',
        ),
        "victims": [
            ("w1.denial_is_refused_and_audited",
             w1.test_clicking_a_source_the_caller_cannot_read_is_refused_and_audited),
            # 没带部门那一格不吃这道闸：authorization_unavailable 长在 scope 解析那一步，
            # 本刀摘的是 scope.allows 那一道，所以它不进 K3 的 victim 名册。
            ("r46::cross_department_batch_is_denied",
             r46.test_no_caller_out_of_a_cross_department_batch_gets_through),
        ],
    },
    {
        "tag": "K4",
        "kind": "python",
        "module": feedback,
        "path": FEEDBACK_PATH,
        "anchor": _lines(
            '    if any(item["username"] != username for item in ledger):',
            '        raise HTTPException(status_code=403, detail="permission_denied")',
        ),
        "mutant": _lines(
            '    if False:  # 反证 K4：别人的行回来了也不关账',
            '        raise HTTPException(status_code=403, detail="permission_denied")',
        ),
        "victims": [
            ("w1.foreign_ledger_row_closes_the_read",
             w1.test_a_ledger_row_belonging_to_someone_else_closes_the_read),
        ],
    },
    {
        "tag": "K5",
        "kind": "python",
        "module": rt,
        "path": RETRIEVER_PATH,
        "anchor": '    confidence = min(1.0, support / float(ENGAGEMENT_MIN_SAMPLES))',
        "mutant": '    confidence = 1.0  # 反证 K5：样本数下限摘掉，第一枚点击就替整篇定序',
        "victims": [
            ("w2.first_click_weaker_than_fifth",
             w2.test_the_first_click_is_weaker_than_the_fifth),
        ],
    },
    {
        "tag": "K6",
        "kind": "python",
        "module": rt,
        "path": RETRIEVER_PATH,
        "anchor": _lines(
            '    cap = float(ACTIVITY_PRIOR_MAX_SHIFT_RANKS)',
            '    total = activity_prior_value(counts) + engagement_prior_value(counts)',
        ),
        "mutant": _lines(
            '    cap = float(ACTIVITY_PRIOR_MAX_SHIFT_RANKS) * 2  # 反证 K6：合并后界放宽成两名',
            '    total = activity_prior_value(counts) + engagement_prior_value(counts)',
        ),
        "victims": [
            ("w2.merge_keeps_one_place_cap",
             w2.test_the_merge_never_widens_the_shift_cap),
        ],
    },
    {
        "tag": "K7",
        "kind": "migration",
        "path": MIGRATION_PATH,
        "anchor": "CHECK (result_rank >= 1 AND result_rank <= 100)",
        "mutant": "CHECK (1 = 1)",
        "victims": [
            ("w1.check_family_pairs_with_0011",
             w1.test_the_check_family_of_0019_pairs_up_with_the_one_of_0011),
        ],
    },
    {
        "tag": "K8",
        "kind": "python",
        "module": feedback,
        "path": FEEDBACK_PATH,
        "anchor": '    reset_signal_priors()',
        "mutant": '    pass  # 反证 K8：写完不作废，回执与排序两本账分家',
        "victims": [
            ("w2.fresh_click_invalidates_snapshot",
             w2.test_a_fresh_click_invalidates_the_sort_side_snapshot),
        ],
    },
]


# ============================================================= 正控：摘刀之前每一枚都得绿
def test_the_positive_control_named_victims_are_green_before_any_knife():
    """否则"红"是它本来就红，这把刀量不到任何东西。锚点也在这里先数一遍。"""
    for knife in KNIVES:
        text = _read_text(knife["path"])
        assert text.count(knife["anchor"]) == 1, (
            knife["tag"] + " 的锚点在盘上不是唯一一处：这把刀无法被执行"
        )
        assert knife["victims"], knife["tag"]
        for name, victim in knife["victims"]:
            red, reading = _outcome(victim)
            assert not red, name + " 在没摘刀的时候就已经不绿了：" + reading


# ================================================================== 八把刀，逐枚执行
def test_the_eight_knives_are_all_cut_and_every_named_victim_bled():
    for knife in KNIVES:
        if knife["kind"] == "python":
            _cut_python(
                knife["tag"], knife["module"], knife["path"],
                knife["anchor"], knife["mutant"], knife["victims"],
            )
        else:
            _cut_migration(
                knife["tag"], knife["path"], knife["anchor"], knife["mutant"], knife["victims"]
            )
    assert len(KNIVES) == 8 and _CUT_TAGS == {
        "K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8"
    }, sorted(_CUT_TAGS)


# ============================================================= 总账：两态读数与只读纪律
def test_every_knife_recorded_a_pair_of_twelve_hex_digests():
    """派工词判据⑥：每把刀交摘前摘后各一枚 sha256 前 12，并且逐字节还原。"""
    import re
    assert len(SHA_LEDGER) == 8, SHA_LEDGER
    for entry in SHA_LEDGER:
        assert re.fullmatch(r"[0-9a-f]{12}", str(entry["before"])), entry
        assert entry["after"] == entry["before"], entry
        assert entry["victims"], entry
        for hit in entry["victims"]:
            assert hit["reading"], hit


def test_two_of_the_victims_are_in_register_nails_not_self_written_ones():
    """R527 判据 7：victim 里必须点名在册钉本身——这里两枚，长在 R46 那件里。"""
    assert IN_REGISTER_VICTIMS <= _RED_VICTIMS, sorted(IN_REGISTER_VICTIMS - _RED_VICTIMS)


def test_the_tracked_files_are_still_the_bytes_we_came_in_on():
    """摘刀全程不写盘：三枚件出到最后一格时仍与进门那一刻逐字节同值。"""
    for path, fingerprint in FINGERPRINT_AT_IMPORT.items():
        assert _sha12(path) == fingerprint, path.name
    assert overlay.open_windows() == (), "反证窗没收干净：影子根还挂着"


def test_the_live_module_is_back_to_the_disk_behaviour_after_every_window():
    """窗尾复跑正控：变异一枚都不许留在活模块上（install_mutation 的还原面在这里现量）。"""
    assert rt.engagement_prior_value({"clicks": 0, "views": 0}) == 0.0
    expected = float(rt.ENGAGEMENT_PRIOR_MAX_SHIFT_RANKS) * 1.0 / (1.0 + rt.ENGAGEMENT_PRIOR_SMOOTHING) * (1.0 / float(rt.ENGAGEMENT_MIN_SAMPLES))
    assert rt.engagement_prior_value({"clicks": 1, "views": 0}) == pytest.approx(expected)
    assert rt.signal_prior_value(
        {"accepted": 99, "rejected": 0, "clicks": 99, "views": 99}) == float(
        rt.ACTIVITY_PRIOR_MAX_SHIFT_RANKS)
    for name, victim in [(k["tag"], v) for k in KNIVES for _, v in k["victims"]]:
        red, reading = _outcome(victim)
        assert not red, name + " 出窗之后还是不绿：" + reading
