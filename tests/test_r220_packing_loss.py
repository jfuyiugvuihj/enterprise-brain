"""R220 量具的钉子：三桶互斥、并起来正好等于损失行，而且这条由测试自己复算一遍。

🔴 这批钉子不许改成"恒真"。桶标签是 analyze() 自己写进 detail 的，只读标签的断言摘掉
任一桶都不会红（它会把摘掉那几行静默挪进别处）。所以
test_the_three_buckets_survive_an_independent_recomputation 三样都不用量具的结论：名次集合
直读 r59b 那份 json 的 chroma_ids，进场集合直读 run6 证据袋的 source_id（量具走的是
source + chunk_index 那条拼接路，两条路必须同解），装箱调**产品函数** pack_prefix_by_rank
而不是量具里那份本地副本。摘掉一桶的判据 ⇒ 这一枚必红。

零模型、零容器：本件 import app.rag.retrieval_pipeline 只为取装箱函数与它的常数，
tests/conftest.py 的端口闸门与 Chroma 沙箱负责让这次 import 不发连接、不写跟踪件。
"""
import ast
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "r220_packing_loss.py"
SEED_MANIFEST = ROOT / "deploy" / "workspace-seed.json"

_spec = importlib.util.spec_from_file_location("r220_packing_loss", SCRIPT_PATH)
r220 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r220)

#: 交回单与 docs/testing/r220-packing-loss-2026-09-25.md 同一批读数。三份输入或 documents/
#: 任一字节动了，这几枚就该红着要求重新出数，而不是悄悄跟着变。
SHIPPED = {
    "questions": 105,
    "topk_rows": 420,
    "lost_rows": 375,
    "lost_by_room": 6,
    "lost_before_packing": 93,
    "lost_unattributed": 276,
    "room": 1198,
    "empty_vector_leg": 21,
    "clean_questions": ["metric-06"],
}

#: 三份只读原件的 sha256，现场取的。
INPUT_FINGERPRINTS = {
    "r59b-recall-comparison-2026-09-24.json":
        "4214eaff36fcc84e1f651a7bfc3bb63b30d153448774ee731c71785b11f62d5d",
    "answers-run6.jsonl":
        "d50c2f9805ffa2dfed7154115ebfc9f173c954f07d26ff0776b6fb1637b5bb5a",
    "business_evaluation_100.jsonl":
        "686c564ff2985744e6f050e5ea7639500c99bd80b3e32fc3a85e585f5ecdd79b",
}

#: 逐题可追的三枚抽查：一题两桶混装、一题全名次侧、一题被第一枚缺料的块整段拖进判不了。
SPOT = {
    "approval-04": {"lost_n": 5, "lost_by_room_n": 1, "lost_before_packing_n": 4, "lost_unattributed_n": 0},
    "metric-07": {"lost_n": 5, "lost_by_room_n": 0, "lost_before_packing_n": 5, "lost_unattributed_n": 0},
    "data-01": {"lost_n": 5, "lost_by_room_n": 0, "lost_before_packing_n": 0, "lost_unattributed_n": 5},
}

LOST_BUCKETS = ("lost_by_room", "lost_before_packing", "lost_unattributed")
ALL_BUCKETS = ("in_prompt",) + LOST_BUCKETS


@pytest.fixture(scope="module")
def reading():
    return r220.analyze()


@pytest.fixture(scope="module")
def raw_ranked():
    """名次集合：直读 r59b 那份 json，不经 load_recall()。"""
    doc = json.loads(r220.RECALL.read_text(encoding="utf-8"))
    return {
        q["id"]: list(q.get("chroma_ids") or [])
        for q in doc["questions"]
        if q.get("source") == r220.FIXTURE_SOURCE
    }


@pytest.fixture(scope="module")
def raw_bag():
    """进场集合：直读证据袋的 source_id 字面（file.txt#chunk=N）。"""
    bag = {}
    for line in r220.ANSWERS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            bag[row["id"]] = [
                str(item["source_id"]).replace("#chunk=", "_")
                for item in row.get("evidence") or []
                if item.get("source_id")
            ]
    return bag


@pytest.fixture(scope="module")
def server_only_rows():
    """清单在册、本机 documents/ 没有的那几枚 —— 与 test_corpus_parity 同一真源。"""
    manifest = json.loads(SEED_MANIFEST.read_text(encoding="utf-8"))
    directory = str(manifest["corpus_directory"])
    disk = {path.name for path in (ROOT / directory).iterdir() if path.is_file()}
    return {str(name) for name in manifest["documents"]["files"] if str(name) not in disk}


def _oracle(corpus, room, limit, ranked, bag):
    """按跟进单 §94 四的口径独立复算三桶；装箱调产品函数，不用量具那份副本。

    "就地停"这一条与量具同义：块长取不到、或房顶穿，从那一枚起整段判不了/装不进，
    谁先发生谁说了算 —— 所以房顶穿发生在缺料块之前时，那几枚缺料块会被并进"房不够"。
    这是口径自带的偏向，报告里写死了，不在钉子这儿偷偷改。
    """
    from app.rag.retrieval_pipeline import text_pack_tokens

    bodies = [corpus.text(vector_id) for vector_id in ranked]
    cut = next((index for index, body in enumerate(bodies) if body is None), len(ranked))
    kept_units, dropped_units, _used = _product_pack(bodies[:cut], room, text_pack_tokens)
    kept_ids = set(ranked[: len(kept_units)])
    if dropped_units:
        room_ids, unknown_ids = set(ranked[len(kept_units) :]), set()
    else:
        room_ids, unknown_ids = set(), set(ranked[cut:])
    present = set(bag)
    lost = [vector_id for vector_id in ranked if vector_id not in present]
    return {
        "lost": lost,
        "lost_by_room": [v for v in lost if v in room_ids],
        "lost_before_packing": [v for v in lost if v in kept_ids],
        "lost_unattributed": [v for v in lost if v in unknown_ids],
    }


def _product_pack(unit_bodies, room, token_of):
    from app.rag.retrieval_pipeline import pack_prefix_by_rank

    return pack_prefix_by_rank(list(unit_bodies), room, token_of=token_of)


def test_the_three_input_artifacts_are_the_batch_these_numbers_came_from():
    for path in r220.READONLY_INPUTS:
        assert INPUT_FINGERPRINTS[path.name] == r220.sha256(path), (
            f"{path.name} 换了字节：这一轮三桶读数不再成立，重跑并在报告里改口"
        )


def test_capacity_reserves_and_room_are_the_products_own_numbers(reading):
    from app.rag.retrieval_pipeline import DOC_HIT_CONTENT_CHARS, context_pack_room

    numbers = reading["numbers"]
    assert numbers["room"] == context_pack_room(), "room 与产品那一枚算式分了叉"
    assert numbers["content_chars"] == DOC_HIT_CONTENT_CHARS
    assert numbers["room"] == numbers["capacity"] - numbers["reserve_total"]
    assert numbers["capacity"] == numbers["context_limit_tokens"] - numbers["tier_max_tokens"]
    assert numbers["recall_depth"] >= numbers["top_k"], "召回深度小于最终 top-k ⇒ 那一格本来就是空的"
    assert numbers["top_k"] > 0 and numbers["recall_depth"] > 0


def test_the_two_numbers_read_by_call_site_came_from_a_call_site(reading):
    """真源换了形状时宁可就地红，也不许退化成手抄字面量 —— 所以命中形状本身就是读数。"""
    assert reading["numbers"]["top_k_shape"] in {"call_keyword", "dict_splat"}
    assert reading["numbers"]["recall_depth_shape"] in {"direct_call", "submitted_callee"}


@pytest.mark.parametrize(
    "keyword, expected",
    [("CONTEXT_SHELL_RESERVE_TOKENS", 456), ("CONTEXT_HISTORY_RESERVE_TOKENS", 906)],
)
def test_both_reserve_constants_are_still_module_literals(keyword, expected):
    assert r220.module_literal(r220.PIPELINE_SRC, keyword) == expected


@pytest.mark.parametrize(
    "units, room, cost_of, expect",
    [
        pytest.param(["a", "b", "c"], 0, len, ([], ["a", "b", "c"], 0), id="room-0-drops-everything"),
        pytest.param(["ab", "c"], 1, len, ([], ["ab", "c"], 0), id="first-unit-too-big-drops-the-batch"),
        pytest.param(["a", "b", "c"], 3, len, (["a", "b", "c"], [], 3), id="exact-fit-is-kept"),
        pytest.param(["xx", "x", "xxx"], 3, len, (["xx", "x"], ["xxx"], 3), id="overflow-drops-the-suffix"),
        pytest.param(["", "", "a"], 2, len, (["", "", "a"], [], 1), id="zero-cost-units-are-free"),
        pytest.param([], 5, len, ([], [], 0), id="empty-input"),
        pytest.param(["x"] * 8, 8, len, (["x"] * 8, [], 8), id="eight-units-exactly-fill"),
    ],
)
def test_local_packing_copy_matches_the_product_function(units, room, cost_of, expect):
    from app.rag.retrieval_pipeline import pack_prefix_by_rank

    assert r220.pack_prefix(units, room, cost_of) == expect
    assert pack_prefix_by_rank(units, room, token_of=cost_of) == expect, "产品函数与钉住的形状分了叉"


def test_the_three_buckets_survive_an_independent_recomputation(reading, raw_ranked, raw_bag):
    from app.rag.retrieval_pipeline import DOC_HIT_CONTENT_CHARS, context_pack_room

    corpus = reading["corpus"]
    room = context_pack_room()
    bad = []
    for row in reading["rows"]:
        ranked = raw_ranked.get(row["id"]) or []
        bag = raw_bag.get(row["id"]) or []
        want = _oracle(corpus, room, DOC_HIT_CONTENT_CHARS, ranked, bag)
        got = {label: [d["vector_id"] for d in row["detail"] if d["bucket"] == label] for label in ALL_BUCKETS}
        for bucket in LOST_BUCKETS:
            if sorted(got[bucket]) != sorted(want[bucket]):
                bad.append((row["id"], bucket, sorted(got[bucket]), sorted(want[bucket])))
        if sorted(got["in_prompt"]) != sorted(v for v in ranked if v in set(bag)):
            bad.append((row["id"], "in_prompt", sorted(got["in_prompt"]), sorted(want["lost"])))
    assert not bad, "量具的桶与自己复算的桶对不上（前 3 条）：" + str(bad[:3])


def test_the_three_lost_buckets_are_mutually_exclusive_per_question(reading):
    for row in reading["rows"]:
        buckets = [
            {d["vector_id"] for d in row["detail"] if d["bucket"] == label} for label in LOST_BUCKETS
        ]
        for i in range(len(buckets)):
            for j in range(i + 1, len(buckets)):
                overlap = buckets[i] & buckets[j]
                assert not overlap, f'{row["id"]} 的两桶共享了 {sorted(overlap)}'
        in_prompt = {d["vector_id"] for d in row["detail"] if d["bucket"] == "in_prompt"}
        assert sum(len(b) for b in buckets) + len(in_prompt) == row["top_k"], (
            f'{row["id"]} 四桶没覆盖满这一发名次'
        )


def test_the_three_buckets_sum_exactly_to_the_loss_rows(reading):
    rows = reading["rows"]
    for row in rows:
        assert (
            row["lost_by_room_n"] + row["lost_before_packing_n"] + row["lost_unattributed_n"]
            == row["lost_n"]
        ), f'{row["id"]} 三桶并起来不等于损失行'
    assert (
        sum(row["lost_by_room_n"] for row in rows)
        + sum(row["lost_before_packing_n"] for row in rows)
        + sum(row["lost_unattributed_n"] for row in rows)
        == sum(row["lost_n"] for row in rows)
        == SHIPPED["lost_rows"]
    )


def test_the_shipped_reading_is_this_batch_end_to_end(reading):
    rows = reading["rows"]
    assert len(rows) == SHIPPED["questions"]
    assert sum(row["top_k"] for row in rows) == SHIPPED["topk_rows"]
    assert sum(row["lost_n"] for row in rows) == SHIPPED["lost_rows"]
    assert sum(row["lost_by_room_n"] for row in rows) == SHIPPED["lost_by_room"]
    assert sum(row["lost_before_packing_n"] for row in rows) == SHIPPED["lost_before_packing"]
    assert sum(row["lost_unattributed_n"] for row in rows) == SHIPPED["lost_unattributed"]
    assert reading["numbers"]["room"] == SHIPPED["room"]
    assert sum(1 for row in rows if not row["top_k"]) == SHIPPED["empty_vector_leg"]
    assert sorted(row["id"] for row in rows if row["top_k"] and not row["lost_n"]) == SHIPPED[
        "clean_questions"
    ], "「装箱零损失」这一格今天只有 metric-06 一枚；多出来的都是向量腿空返回，别当成绩"


@pytest.mark.parametrize("qid", sorted(SPOT))
def test_a_spot_question_carries_exactly_the_hand_recomputed_buckets(reading, qid):
    row = next(item for item in reading["rows"] if item["id"] == qid)
    for field, value in SPOT[qid].items():
        assert row[field] == value, f"{qid}.{field} 与报告里的复算结论不符"
    for item in row["detail"]:
        assert item["bucket"] in ALL_BUCKETS
        assert item["vector_id"] in row["lost_ids"] or item["bucket"] == "in_prompt"


def test_every_loss_row_is_traceable_to_a_question_a_block_and_a_bucket(reading):
    for row in reading["rows"]:
        lost = {d["vector_id"] for d in row["detail"] if d["bucket"] != "in_prompt"}
        assert lost == set(row["lost_ids"]), f'{row["id"]} 的损失行与逐格明细对不上'
        assert len(lost) == row["lost_n"], f'{row["id"]} 损失行里有重复块号'
        assert row["lost_n"] + row["evidence_n"] - row["foreign_n"] == row["top_k"], (
            f'{row["id"]} 进场/损失/外来三格算不拢这一发名次'
        )


def test_the_unattributed_bucket_is_only_the_known_server_only_gap(reading, server_only_rows):
    """判不了那一桶必须全落在"清单在册、本机无料"那几枚文件上。

    这一枚是 276 这个数字的诚实性来源：哪天 documents/ 里文件还在、块号却取不到
    （splitter 换了参数、向量库与磁盘不同源），这里会红，而不是把那几枚静默算进"房不够"。
    """
    corpus = reading["corpus"]
    unresolvable_files = set()
    for row in reading["rows"]:
        for item in row["detail"]:
            if item["chars"] is None:
                unresolvable_files.add(r220.split_vector_id(item["vector_id"])[0])
    assert unresolvable_files
    assert unresolvable_files <= server_only_rows, (
        f"这些块取不到正文但文件本机是在的，属切分/索引不同源：{sorted(unresolvable_files - server_only_rows)}"
    )
    assert sorted(corpus.missing_files) == sorted(unresolvable_files)


def test_the_instrument_never_imports_the_module_that_opens_a_model_socket():
    """本件立论就是离线：量具自己不许 import 那枚 import 期就构造 ModelHandler 的模块。"""
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "app.rag.retrieval_pipeline" not in imported, "量具一 import 它就在收集期对宿主模型端口发连接"
