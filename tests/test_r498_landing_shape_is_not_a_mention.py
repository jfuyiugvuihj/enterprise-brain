# -*- coding: utf-8 -*-
"""R498 · 判据②③：号账把「提及」与「并树」分家；正解不是「首行含『并树』两个字」。

病根（本席 09-29 16:5x 现读，HEAD 7126614）：C 档给 R493/R495/R496 报 HAS_COMMIT，
而这三枚此刻全在途——那三枚 sha 只是**本席自己的**并树信息在正文里「另立 RNNN」的提及。
上一任「20 枚零提交」是同一个病的反面。

这枚钉吃两种料：
  ① 纯函数料：首行形状判据 `subject_shape`／写域交集 `declares_path`／按号命名 `names_the_ticket`，
     用真仓首行的**字节样本**喂，并把「并树首行」与「正文提及」两种字节互换后必须翻判据；
  ② 影子账料：把 `Ruler.records` 换成撒出来的提交记录（sha/父/首行/正文/文件名），
     端到端读档位——空提交、货已不在册、写域对不上、躺在别的 ref 上、模板漂移，五格各有专钉。
  ③ 活账料：真仓历史里的 R491/R484/R471（确已并树）、R493/R495（确在途）、R900（被并树正文
     自己烧掉的探针）、R26 那一族（父号零并树、货在子号名下）、R26 的号界污染（57 vs 9）。

🔴 全程只读：影子记录是撒进内存的，不落任何盘；档位读数一律与仓库位置无关（不写死树名）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "dispatch_preflight.py"

#: 真仓首行的字节样本（形状取自在册的九枚并树提交与三枚提及提交，号与 sha 都换成可核的写法）。
LAND_R495 = "并树 R495（施工 Example/01a0e000，树 be-r495@abc1234）：新钉 tests/test_r495_owner.py 一枚。"
MENTION_R495 = ("并树 R484（施工 Example/01a0e000，树 be-r484@abc1234）：会话读腿对账；"
                "另立 R495 把这层承重变显式契约。")
BOARD_R495 = ("跟进单 §136（09-29 第二十八格）：R484/R471/R491 三枚并树落账 · "
              "新立四单 R495/R496/R497 已投出、R498 立案但投递被拒。")
QUALIFIED = "并树 R471 丙案（施工 Example/01a0e000，树 be-r471@abc1234）：口径改字。"
BUILD_FEAT = "feat(R26a): ollama 容器显式声明 GPU + 算力三分诚实探测（默认零行为变更）"
BUILD_BARE = "R260b（总控补口·并树后全量门抓到）：r218 反证钉的锚点抄本同步到 R260 之后。"
MERGE_BRANCH = "Merge codex/be-leg2: R26a GPU 诚实声明（compose 设备声明 + 算力三分探测 + 文档）"
DRIFT_NO_PAREN = "并树 R495 今天没写模板括号了 新钉一枚"
NO_HEAD_MARK = "并树 R495（Example/01a0e000）：新钉 tests/test_r495_owner.py 一枚。"

#: 真仓里确已并树的号（首行都是并树模板，货在 HEAD 祖先链上）。
LANDED_IN_HISTORY = ("R478", "R481", "R482", "R484", "R490", "R491", "R492")
#: 在途那一族：本席跑动期间别的席还在往树上并（R493/R495/R496/R497 依次脱链），
#: 所以档位本身是活的、不许写死；下面那枚钉吃的是不变量，两棵树都必须成立。
IN_FLIGHT = ("R493", "R494", "R495", "R496", "R497", "R498")
IN_FLIGHT = ("R493", "R494", "R495", "R496", "R497", "R498")
#: 派工词点名的三枚提交：首行是别人的落地、正文才提了本号 ⇒ 对本号永远只是提及。
MENTION_SHAS = (("R493", "314888b"), ("R495", "5270c40"), ("R496", "438d67d"))

R491_FILES = ["scripts/dispatch_preflight.py", "docs/testing/dispatch-preflight-2026-09-29.md",
              "tests/test_r491_ticket_ledger_keeps_three_tiers.py"]


@pytest.fixture(scope="module")
def r498():
    spec = importlib.util.spec_from_file_location("dispatch_preflight_r498_landing", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def live(r498):
    return r498.Ruler(REPO_ROOT)


def rec(sha, subject, files=(), parents=("dad",), message=""):
    """一枚撒出来的提交记录：字段形状与 `parse_records` 交回的完全一致。"""
    return {"sha": sha, "parents": list(parents), "subject": subject,
            "message": subject + chr(10) + message, "files": list(files)}


def fake(r498, records_by_token, tracked, on_trunk=True, paper=None):
    """把 git 层换成影子账的尺子：档位判据（形状 + 实改 + 在册 + 写域 + 祖先链）全部照跑。"""
    ruler = r498.Ruler(REPO_ROOT)
    ruler._tracked = set(tracked)
    ruler._head = "f" * 40
    ruler.records = lambda token: list(records_by_token.get(token, []))
    ruler.paper_index = lambda: dict(paper or {})
    ruler.on_trunk = lambda sha: on_trunk
    return ruler


def tier(ruler, token):
    return ruler.ticket_status(token)[0]


def row_of(ruler, token):
    return ruler.check("核 {0} 一枚。".format(token))["numbers"][0]


# ---------------------------------------------------------------------------
# ① 首行形状：读位置，不读「含不含那两个字」
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("subject,token,expected", [
    (LAND_R495, "R495", "并树模板"),
    (LAND_R495, "R484", None),                 # 别的号的首行，与本号无关
    (MENTION_R495, "R484", "并树模板"),         # 同一枚提交对 R484 是并树……
    (MENTION_R495, "R495", None),              # ……对 R495 只是提及
    (BOARD_R495, "R495", None),                # 看板/跟进单正文点了名，首行不是模板
    (BOARD_R495, "R484", None),
    (QUALIFIED, "R471", "并树模板"),           # 「R471 丙案」这类限定语要吃下
    (BUILD_FEAT, "R26a", "施工首行"),
    (BUILD_BARE, "R260b", "施工首行"),
    (BUILD_BARE, "R260", None),                # 拆单子号不许并回父号
    (MERGE_BRANCH, "R26a", "分支并树"),
    (DRIFT_NO_PAREN, "R495", None),            # 模板漂了就是漂了，认不下来要红着说
    (NO_HEAD_MARK, "R495", "并树模板"),        # 标记缺（无「施工」字样）仍认首行位置
])
def test_the_first_line_is_read_from_position_not_presence(r498, subject, token, expected):
    assert r498.subject_shape(subject, token) == expected


def test_swapping_the_landing_and_mention_bytes_flips_every_verdict(r498, live):
    """把两种字节互换，判据必须跟着翻——否则就是恰好命中，不是判据。"""
    land, mention = LAND_R495, MENTION_R495
    assert r498.subject_shape(land, "R495") == "并树模板"
    assert r498.subject_shape(mention, "R495") is None
    own = [r498.subject_shape(one, "R495") for one in (land, mention)]
    swapped = [r498.subject_shape(one, "R495") for one in (mention, land)]
    assert swapped == [None, "并树模板"], swapped
    assert own != swapped, "互换后读数一模一样 ⇒ 判据没在读字节"
    # 另一枚号（R484）从同一批字节里读到的必须恰好相反：并树 vs 提及
    assert r498.subject_shape(mention, "R484") == "并树模板"
    assert r498.subject_shape(land, "R484") is None


def test_the_number_boundary_is_enforced_on_the_first_line(r498):
    """R26 的首行不许被读成 R260–R269 任何一枚的并树，反之亦然。"""
    for digit in "0123456789":
        assert r498.subject_shape("并树 R26{0}（施工 X/1，树 be-r26x@abc1234）：货".format(digit),
                                  "R26") is None
    assert r498.subject_shape("并树 R26（施工 X/1，树 be-r26@abc1234）：货", "R26") == "并树模板"
    assert r498.subject_shape("并树 R2678（施工 X/1，树 be-r267@abc1234）：货", "R267") is None


@pytest.mark.parametrize("rel,token,expected", [
    ("tests/test_r483_empty_table_triage_is_derived.py", "R483", True),
    ("scripts/r483_empty_tables_triage.py", "R483", True),
    ("docs/testing/r496-forbidden-pin-scope-2026-09-29.md", "R496", True),
    ("tests/test_r260b_anchor.py", "R26", False),        # 号后必须收在边界上
    ("tests/test_r260b_anchor.py", "R260b", True),
    ("app/common/model_capabilities.py", "R26a", False),  # 不按号命名的货走另一条腿
])
def test_a_product_named_after_the_ticket_is_recognised_and_not_prefix_matched(r498, rel, token,
                                                                               expected):
    assert r498.names_the_ticket(rel, token) is expected


@pytest.mark.parametrize("message,rel,expected", [
    ("新增取证件 scripts/r484_ledger.py(493 行) + 新钉 tests/test_r484_owner.py(708 行)",
     "scripts/r484_ledger.py", True),                     # 尾巴挂字也算点名
    ("五枚 tests/test_r491_* 与 docs/testing/x.md", "tests/test_r491_blades.py", True),
    ("把假形状从 app/** 与两枚对外串里清掉", "app/common/rbac.py", True),
    ("改口 docs/* 一节", "docs/handoff/note.md", True),
    ("五枚 tests/test_r491_* 与 docs/testing/x.md", "scripts/other.py", False),
    ("正文只说中文，一件名都没有", "scripts/whatever.py", False),
])
def test_the_write_domain_intersection_reads_three_ways_of_naming(r498, message, rel, expected):
    assert r498.declares_path(message, rel) is expected


# ---------------------------------------------------------------------------
# ② 影子账：五格各有专钉（每一格都是「首行声称落地」，差别只在腿）
# ---------------------------------------------------------------------------

def test_a_real_landing_with_named_products_reads_landed(r498):
    ruler = fake(r498, {"R495": [rec("a" * 40, LAND_R495, ["tests/test_r495_owner.py"])]},
                 ["tests/test_r495_owner.py"])
    assert tier(ruler, "R495") == r498.HAS_COMMIT
    assert ruler.check("核 R495。")["numbers"][0]["commits"] == 1


def test_a_prose_mention_of_the_same_bytes_never_reads_landed(r498):
    ruler = fake(r498, {"R495": [rec("b" * 40, MENTION_R495, ["scripts/r484_ledger.py"])],
                        "R484": [rec("b" * 40, MENTION_R495, ["scripts/r484_ledger.py"])]},
                 ["scripts/r484_ledger.py"])
    assert tier(ruler, "R484") == r498.HAS_COMMIT
    assert tier(ruler, "R495") == r498.MENTION_ONLY
    row = row_of(ruler, "R495")
    assert row["commits"] == 0 and row["mentions"] == 1 and "并树 0 枚" in row["note"]


def test_a_board_commit_that_lists_the_number_is_a_mention_not_a_landing(r498):
    ruler = fake(r498, {"R495": [rec("c" * 40, BOARD_R495,
                                     ["docs/handoff/2026-09-15-backend-followup-requests.md"])]},
                 ["docs/handoff/2026-09-15-backend-followup-requests.md"])
    assert tier(ruler, "R495") == r498.MENTION_ONLY


def test_an_empty_landing_claim_is_refused(r498):
    """首行写着并树、diff 是空的：并树不能靠一句话。"""
    ruler = fake(r498, {"R495": [rec("d" * 40, LAND_R495, [])]}, ["tests/test_r495_owner.py"])
    assert tier(ruler, "R495") == r498.MENTION_ONLY
    assert "实改清单为空" in row_of(ruler, "R495")["note"]


def test_a_landing_whose_products_are_no_longer_in_the_ledger_is_refused(r498):
    ruler = fake(r498, {"R495": [rec("e" * 40, LAND_R495, ["tests/test_r495_owner.py"])]}, [])
    assert tier(ruler, "R495") == r498.MENTION_ONLY
    assert "不在 git ls-files 在册" in row_of(ruler, "R495")["note"]


def test_a_landing_that_moves_another_tickets_products_is_a_named_conflict(r498):
    """首行声称本号并树、货也在册，但实改与正文点名的写域零交集 ⇒ 冲突档，既不许绿也不许判死。"""
    ruler = fake(r498, {"R495": [rec("a1" * 20, LAND_R495, ["scripts/r484_ledger.py"])]},
                 ["scripts/r484_ledger.py"])
    status = tier(ruler, "R495")
    assert status == r498.LANDING_CONFLICT, status
    assert status not in r498.RED_STATUSES
    row = row_of(ruler, "R495")
    assert row["commits"] == 0 and "对不上" in row["note"] and "a1a1a1a" in row["note"]


def test_a_landing_claim_sitting_on_another_ref_is_not_this_trees_landing(r498):
    ruler = fake(r498, {"R495": [rec("b2" * 20, LAND_R495, ["tests/test_r495_owner.py"])]},
                 ["tests/test_r495_owner.py"], on_trunk=False)
    assert tier(ruler, "R495") == r498.LANDING_OFF_TRUNK
    row = row_of(ruler, "R495")
    assert row["commits"] == 0 and "祖先链" in row["note"] and "b2b2b2b" in row["note"]


def test_a_merge_landing_is_read_against_its_first_parent(r498):
    """merge 的 --name-only 天生是空的：不补第一父这一腿，真并树会被读成没并。"""
    sha = "c3" * 20
    ruler = fake(r498, {"R26a": [rec(sha, MERGE_BRANCH, [], ("dad", "mom"))]},
                 ["app/common/model_capabilities.py"])
    ruler._files[sha] = []                        # 影子账：相对第一父也没带货
    assert tier(ruler, "R26a") == r498.MENTION_ONLY          # 没补第一父这一腿之前：货读不到
    ruler._files[sha] = ["app/common/model_capabilities.py"]
    assert tier(ruler, "R26a") == r498.HAS_COMMIT


def test_a_drifted_first_line_is_refused_and_says_which_layer_failed(r498):
    ruler = fake(r498, {"R495": [rec("d4" * 20, DRIFT_NO_PAREN, ["tests/test_r495_owner.py"])]},
                 ["tests/test_r495_owner.py"])
    row = row_of(ruler, "R495")
    assert row["status"] == r498.MENTION_ONLY
    assert "首行无一条是本号的落地形状" in row["note"], row["note"]


def test_missing_template_markers_are_reported_but_do_not_alone_decide(r498):
    ruler = fake(r498, {"R495": [rec("e5" * 20, NO_HEAD_MARK, ["tests/test_r495_owner.py"])]},
                 ["tests/test_r495_owner.py"])
    row = row_of(ruler, "R495")
    assert row["status"] == r498.HAS_COMMIT
    assert "模板标记缺" in row["note"], row["note"]


def test_a_subnumber_landing_is_never_merged_into_its_parent_number(r498):
    """父号名下零并树、子号名下有 ⇒ 只能读 SUBNUMBER_LANDED 并点名子号，两档不许互混。"""
    records = {"R26": [rec("f6" * 20, BUILD_FEAT, ["app/common/model_capabilities.py"])],
               "R26a": [rec("f6" * 20, BUILD_FEAT, ["app/common/model_capabilities.py"])]}
    tracked = ["app/common/model_capabilities.py"]
    ruler = fake(r498, records, tracked)
    assert tier(ruler, "R26a") == r498.HAS_COMMIT
    parent = row_of(ruler, "R26")
    assert parent["status"] == r498.SUBNUMBER_LANDED
    assert parent["commits"] == 0, "子号的货被记到父号名下就是并号"
    assert "R26a=f6f6f6f" in parent["note"] and "不自动并号" in parent["note"]
    assert ruler.landing_hits("R26")[0] == []


# ---------------------------------------------------------------------------
# ③ 活账：真仓历史必须按这套判据读出来
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token", LANDED_IN_HISTORY)
def test_tickets_whose_landing_commits_are_on_trunk_read_landed(live, r498, token):
    assert tier(live, token) == r498.HAS_COMMIT, token + " 的货明明在树上"


@pytest.mark.parametrize("token", IN_FLIGHT)
def test_a_number_without_this_trees_landing_never_reads_as_landed(live, r498, token):
    """判据②：在途号不许冒充已并树——但「今天读哪一档」是活账，会被别的席推走，
    所以这枚钉不吃档位名，吃的是与树无关的不变量：

      · 读 HAS_COMMIT ⇒ 必须交得出一枚在本树 HEAD 祖先链上的凭据，且 commits ≥ 1；
      · 交不出凭据 ⇒ commits 必须为 0，且档位只能落在那四枚「未并树」的说法里；
      · 无论哪态，读数都要把「哪一层、哪个名字」说出口（凭据 sha 或提及 sha）。
    把正文提及当并树、或把别的 ref 上的落地冒充本树的货，这一枚立刻红。
    """
    row = row_of(live, token)
    landed, offtrunk, mentioned, refused = live.landing_hits(token)
    if row["status"] == r498.HAS_COMMIT:
        assert row["commits"] >= 1 and landed, row["note"]
        assert live.on_trunk(landed[0]["sha"]), "读成已并树却拿不出祖先链凭据：" + token
        assert row["first"] == landed[0]["sha"], row
    else:
        assert row["commits"] == 0, "{0} 未并树却记了凭据枚数".format(token)
        assert row["status"] in (r498.MENTION_ONLY, r498.LANDING_OFF_TRUNK,
                                  r498.LANDING_CONFLICT, r498.SUBNUMBER_LANDED), row["status"]
        assert row["first"], "{0} 的读数没点名任何一枚 sha".format(token)
        assert row["mentions"] or row["docs"], "{0} 两路证据都没有，档位不该是这一档".format(token)


def test_the_landing_commit_of_one_ticket_is_only_a_mention_for_the_numbers_it_names(live, r498):
    """R491 的并树提交正文点了 R475 的名：对 R491 是凭据，对 R475 只是提及。"""
    assert row_of(live, "R491")["first"] == "7126614"
    assert row_of(live, "R491")["status"] == r498.HAS_COMMIT
    row = row_of(live, "R475")
    assert row["status"] == r498.MENTION_ONLY, row["status"]
    assert row["commits"] == 0 and "7126614" in row["note"]


def test_a_probe_burned_by_a_landing_message_reads_a_mention(live, r498):
    """R491 的并树信息把探针号 R900 写进了正文：从此 R900 只能是提及，绝不能是并树。"""
    row = row_of(live, "R900")
    assert row["status"] == r498.MENTION_ONLY and row["commits"] == 0
    assert "7126614" in row["note"]


@pytest.mark.parametrize("token,sha", MENTION_SHAS)
def test_a_commit_that_landed_another_ticket_is_never_this_numbers_credential(
        live, r498, token, sha):
    """判据②的活例：`5270c40` 首行是「并树 R484」，正文才写「另立 R495」；
    `438d67d` 首行是「并树 R471 丙案」，正文才写「另立案 R496」；`314888b` 是看板。

    与树无关：本号在这棵树读 MENTION_ONLY 还是 HAS_COMMIT 都行，但那枚 sha
    绝不许出现在本号的凭据/脱链/被拒任何一堆里——否则就是把提及当并树。
    """
    landed, offtrunk, mentioned, refused = live.landing_hits(token)
    assert any(one["sha"] == sha for one in mentioned), (
        "{0} 名下读不到 {1} 这枚提及：取账层变了".format(token, sha))
    for name, rows in (("landed", landed), ("off-trunk", offtrunk), ("refused", refused)):
        assert all(one["sha"] != sha for one in rows), (
            "{0} 被当成 {1} 的{2}凭据＝把提及当并树".format(sha, token, name))


def test_a_landing_claim_is_either_on_trunk_or_named_by_sha(live, r498):
    """脱链这一腿的读数不许含糊：不是 HAS_COMMIT 就得把 sha 说出口（R496 是活例）。"""
    for token in ("R496", "R491", "R484"):
        landed, offtrunk, mentioned, refused = live.landing_hits(token)
        if landed:
            continue
        claims = offtrunk + [one for one in refused if one["kind"] == r498.UNMATCHED]
        if not claims:
            continue
        row = row_of(live, token)
        assert row["status"] in (r498.LANDING_OFF_TRUNK, r498.LANDING_CONFLICT, r498.HAS_COMMIT)
        assert any(one["sha"] in row["note"] for one in claims), token + " 的声称没点名 sha"


def test_the_bare_parent_number_is_not_polluted_by_its_hundred_family(live, r498):
    """`git log --all -F --grep=R26` 是**子串**命中，一把捞回 R260–R269 那一族；
    号边界复核（`message_names_token` + `R[0-9]{2,3}[a-z]?(?![0-9A-Za-z])`）必须收窄它。
    🔴 零命中不是判据：这枚要交出「用的是哪一层的哪个名字」——raw 枚数、mention 枚数、
    被剔掉的兄弟号、以及这些 sha 一枚都不许记进本号名下。
    """
    raw = live.records("R26")
    landed, offtrunk, mentioned, refused = live.landing_hits("R26")
    assert len(raw) > len(mentioned) > 0, (
        "raw={0} mentions={1}：号边界这一层没起作用，或者 R26 那一族的账变了".format(
            len(raw), len(mentioned)))
    family = [one for one in raw
              if "R26" in r498.text_of(one)
              and not r498.message_names_token(r498.text_of(one), "R26")]
    assert family, "活证：raw 里确实有只命中「R26」子串的兄弟号提交"
    sibling = set()
    for one in family:
        sibling.update(tok for tok in r498.NUMBER_RE.findall(r498.text_of(one))
                       if tok.startswith("R26") and tok != "R26")
    assert sibling, "污染源必须报出名字：哪些兄弟号混进了这次 grep"
    attributed = {one["sha"] for one in landed + offtrunk + mentioned + refused}
    assert not ({one["sha"][:7] for one in family} & attributed), (
        "兄弟号的货被记到父号名下了")


def test_the_r26_family_reads_a_named_subnumber_landing_not_a_dead_end(live, r498):
    row = row_of(live, "R26")
    assert row["status"] == r498.SUBNUMBER_LANDED, row["status"]
    assert "R26a" in row["note"] and "R26b" in row["note"], row["note"]
    assert row["commits"] == 0 and row["docs"] > 0, "账面提到 + 父号零并树 ⇒ 这就是那条冲突"
    for token in ("R26a", "R26b"):
        assert tier(live, token) == r498.HAS_COMMIT, token + " 名下确有并树凭据"


def test_the_six_tier_words_are_all_distinct_and_only_never_filed_is_dead(r498):
    words = (r498.HAS_COMMIT, r498.LANDING_OFF_TRUNK, r498.LANDING_CONFLICT, r498.SUBNUMBER_LANDED,
             r498.MENTION_ONLY, r498.PAPER_ONLY, r498.NEVER_FILED)
    assert len(set(words)) == len(words)
    assert [one for one in words if one in r498.RED_STATUSES] == [r498.NEVER_FILED]


def test_records_parser_reads_the_shipped_record_shape_back_into_fields(r498):
    """`--name-only` 拼在 `%x01..%x03` 里的那格形状：解析必须还原 sha/父/首行/文件名。"""
    sample = (chr(1) + "f" * 40 + chr(2) + "e" * 40 + " " + "a" * 40 + chr(2)
              + "并树 R495（施工 X/1，树 be-r495@abc1234）：货" + chr(2)
              + "正文" + chr(3) + chr(10) + "tests/test_r495_owner.py" + chr(10))
    records = r498.parse_records(sample.encode("utf-8"))
    assert len(records) == 1
    one = records[0]
    assert one["sha"] == "f" * 40 and len(one["parents"]) == 2
    assert one["subject"].startswith("并树 R495")
    assert one["files"] == ["tests/test_r495_owner.py"], one
