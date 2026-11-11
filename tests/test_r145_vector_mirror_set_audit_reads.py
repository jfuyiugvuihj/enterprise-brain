"""R145 判据①②③④：四个问题各自可证伪 —— 全程离线假件，一个真库都不连、一个模型都不打。

这枚文件要钉的不是"脚本会输出字"，而是**四个问题各自的读数形状**，尤其是三类会让人误判的形状：

* 只在两侧总数相等时才报"一致"：那正是本单要防的假绿灯，所以集合差、重复 id、0/0 空集都必须
  有自己的读数（判据①）。
* 把 `index_version_id IS NULL` 一律当故障：R76 之后这一列的 NULL 有"刚写进镜像、还没发布过"
  这一层正常含义（`docs/handoff/2026-09-17-pgvector-adoption-plan.md` 的 R76 三段），所以分桶
  本身进判据（判据②）。
* 把"问不出来"塌缩成"零行"：表没迁移、psql 退出码非零、镜像是空表，三件事都必须停在
  `cannot_ask` 并且退出码 2，绝不许读成"没有差异"（判据②③④同一条底线）。

PG 侧的假件坐在**文本协议**上（`R` + 0x1f 的行），不是直接喂元组：psql 的 `-tA` 输出格式本身就是
本单最容易出错的那一层，所以 `parse_rows` 也在被同一枚文件现跑。Chroma 侧的假句柄只允许
`.get()`，`query/add/upsert/delete/peek/count` 一被调用就报红 —— "只比集合与形状、不比距离"
这句话靠它保证，不靠注释。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "audit_vector_mirror_sets.py"


def _load_audit():
    spec = importlib.util.spec_from_file_location("r145_audit_vector_mirror_sets", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    #: @dataclass 在求值时要回查 sys.modules[__name__].__dict__，脚本这种加载方式必须先登记，
    #: 否则收集期就死在 "'NoneType' object has no attribute '__dict__'"。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


AUDIT = _load_audit()

MODEL = "nomic-embed-text"
DIM = "768"
#: 镜像行写进库的时刻（chunk_vectors.created_at/updated_at）与发布的时刻。两个都用带时区的
#: 文本，形状照 psql -tA 回 TIMESTAMPTZ 的样子写，不给假件开后门。
WRITE_OLD = "2026-09-20 01:00:00+00"
WRITE_NEW = "2026-09-20 02:00:00+00"
PUBLISHED = "2026-09-21 00:00:00+00"
CLEAN_IDS = ("a.pdf_0", "a.pdf_1", "b.docx_0")


# ============================================================ 假件：psql 文本协议
def row_line(*values) -> str:
    cells = [AUDIT.NULL_SENTINEL if value is None else str(value) for value in values]
    return AUDIT.ROW_PREFIX + AUDIT.FIELD_SEP.join(cells)


def precondition_rows(*, drop_tables=()) -> list:
    """按脚本自己声明的 REQUIRED/OPTIONAL 清单生成 information_schema 的行。

    假件不抄第二份列清单：将来 0010 加列、脚本改 REQUIRED_COLUMNS，这里会跟着动，
    不会出现"假件比生产宽"的假绿。
    """
    tables = {
        AUDIT.DEFAULT_VECTOR_TABLE: AUDIT.REQUIRED_COLUMNS["chunk_vectors"],
        AUDIT.DEFAULT_CHUNKS_TABLE: AUDIT.REQUIRED_COLUMNS["chunks"],
        "index_versions": AUDIT.REQUIRED_COLUMNS["index_versions"],
        "index_registry": AUDIT.REQUIRED_COLUMNS["index_registry"],
        AUDIT.DEFAULT_SCOPE_TABLE: AUDIT.OPTIONAL_COLUMNS["vector_scope"],
    }
    return [
        (table, column)
        for table, columns in tables.items()
        if table not in drop_tables
        for column in columns
    ]


def world_rows(**overrides) -> dict:
    """一枚自洽的库：3 枚镜像行、3 枚都在 Chroma、全部已回填、单代向量、零孤儿。

    默认干净是故意的 —— 任何一条读数在"世界没坏"时也必须报 clean，否则判据就是靠报警刷出来的。
    """
    rows = {
        "preconditions": precondition_rows(),
        "q1_pg_vector_ids": [(item,) for item in CLEAN_IDS],
        "q2_null_rows": [],
        "q2_mirror_totals": [(3, 3)],
        "q2_dangling_bindings": [],
        "q3_pg_generations": [(MODEL, DIM, 3, WRITE_OLD, WRITE_NEW)],
        "q3_declared_scope": [("1", MODEL, DIM, "cosine")],
        "q3_shape_lies": [],
        "q4_vectors_without_chunks": [],
        "q4_chunks_without_vectors": [],
        "q4_chunk_id_shapes": [],
        "q4_vector_id_shapes": [],
        "self_check_counts": [(AUDIT.DEFAULT_VECTOR_TABLE, 3), (AUDIT.DEFAULT_CHUNKS_TABLE, 3)],
    }
    rows.update(overrides)
    return rows


class FakeReader:
    """按查询名分支的假 PG 通道。三件事一起办：走真 parse_rows、记账、认输（抛异常）。"""

    label = "fake-read-only"

    def __init__(self, rows_by_query: dict):
        self.rows_by_query = dict(rows_by_query)
        self.calls: list = []
        self.transcript: list = []
        self.malformed: list = []
        self.closed = 0

    def rows(self, query):
        self.calls.append(query.name)
        self.transcript.append({"query": query.name, "script": query.sql})
        if query.name not in self.rows_by_query:
            raise AssertionError("脚本新问了一条假件不认识的问题，先补假件再改脚本：" + query.name)
        spec = self.rows_by_query[query.name]
        if isinstance(spec, BaseException):
            raise spec
        if callable(spec):
            spec = spec(self.calls.count(query.name))
        rows, malformed = AUDIT.parse_rows(query, "\n".join(row_line(*row) for row in spec))
        self.malformed.extend(malformed)
        return rows

    def close(self) -> None:
        self.closed += 1


class FakeCollection:
    """只有 `.get()` 的 Chroma 句柄。其余方法一碰就报红。"""

    def __init__(self, ids, width=768):
        self._ids = sorted(str(item) for item in ids)
        #: 给一个宽度，或者给"每枚 id 一个宽度" —— 后者用来测"Chroma 侧宽度不止一种"那一格。
        self._widths = [int(width)] * len(self._ids) if not isinstance(width, (list, tuple)) \
            else [int(item) for item in width]
        self.get_calls = 0
        self.include_seen: list = []

    def get(self, include=None, limit=None, offset=0):
        self.get_calls += 1
        self.include_seen.append(list(include or []))
        window = self._ids[offset:offset + limit] if limit else self._ids[offset:]
        payload = {"ids": list(window), "metadatas": [
            {"filename": item.rpartition("_")[0]} for item in window]}
        if "embeddings" in (include or []):
            payload["embeddings"] = [
                [0.0] * self._widths[offset + position] for position in range(len(window))]
        return payload

    def _forbidden(self, name):
        raise AssertionError("R145 只许 collection.get()，这里调到了 " + name)

    def query(self, *args, **kwargs):  # pragma: no cover - 断言用
        self._forbidden("query")

    def add(self, *args, **kwargs):  # pragma: no cover
        self._forbidden("add")

    def upsert(self, *args, **kwargs):  # pragma: no cover
        self._forbidden("upsert")

    def update(self, *args, **kwargs):  # pragma: no cover
        self._forbidden("update")

    def delete(self, *args, **kwargs):  # pragma: no cover
        self._forbidden("delete")

    def peek(self, *args, **kwargs):  # pragma: no cover
        self._forbidden("peek")

    def count(self, *args, **kwargs):  # pragma: no cover
        self._forbidden("count")


class FakeClient:
    def __init__(self, collection, sink: list):
        self._collection = collection
        self.sink = sink
        sink.append(self)

    def get_collection(self, name=None, **kwargs):
        self.requested = name
        return self._collection

    def get_or_create_collection(self, *args, **kwargs):  # pragma: no cover - 会建表
        raise AssertionError("R145 只读已存在的 collection，不许 get_or_create")


def options(**kwargs):
    args = AUDIT.parse_args([])
    args.r76_deployed_at = None
    for key, value in kwargs.items():
        setattr(args, key, value)
    return args


def run(**kwargs):
    """跑一场完整审计，返回 (报告, 假 reader, 假 collection)。"""
    overrides = kwargs.pop("rows", None) or {}
    chroma_ids = kwargs.pop("chroma_ids", CLEAN_IDS)
    width = kwargs.pop("width", 768)
    reader = FakeReader(world_rows(**overrides))
    collection = FakeCollection(chroma_ids, width=width)
    view = AUDIT.read_chroma(collection, page=2)  # page=2：三枚 id 必须逼它翻两次
    view.update({"ok": True, "collection": AUDIT.DEFAULT_COLLECTION, "opened_path": "/tmp/x"})
    report = AUDIT.audit(reader, AUDIT.build_queries(
        AUDIT.DEFAULT_VECTOR_TABLE, AUDIT.DEFAULT_CHUNKS_TABLE, AUDIT.DEFAULT_SCOPE_TABLE),
        view, options(**kwargs))
    return report, reader, collection


def test_chroma_side_rolls_up_per_document_so_a_list_points_at_a_document():
    """Q1 的名单是 id，可读数得是文档：只看 985/1007 这种总数正是本单要避免的读法。"""
    report, _, _ = run()
    assert report["chroma"]["documents"] == {"a.pdf": 2, "b.docx": 1}
    assert report["questions"]["q1"]["chroma_documents"] == 2
    assert "3 枚 id / 2 个文档" in AUDIT.render(report, 20)


# ================================================================== 判据①：集合面
def test_clean_world_reports_three_numbers_and_no_difference():
    report, reader, _ = run()
    q1 = report["questions"]["q1"]
    assert (q1["status"], report["verdict"]["q1"]) == (AUDIT.CLEAN, AUDIT.CLEAN)
    assert (q1["only_in_chroma"], q1["only_in_pg"], q1["both"]) == (0, 0, 3)
    assert q1["pg_total_rows"] == q1["chroma_total_rows"] == 3
    assert report["self_check"]["row_counts_stable"] is True
    assert reader.closed == 0  # audit() 不管生命周期，main() 才关 —— 别在这儿骗自己


def test_dropping_one_pg_row_names_the_missing_id_instead_of_totals():
    """反证第一把：从 PG 侧删掉一枚 id ⇒ Q1 必须报红并点名它。"""
    report, _, _ = run(rows={"q1_pg_vector_ids": [(item,) for item in CLEAN_IDS[:-1]]})
    q1 = report["questions"]["q1"]
    assert q1["status"] == AUDIT.ATTENTION
    assert (q1["only_in_chroma"], q1["only_in_pg"], q1["both"]) == (1, 0, 2)
    assert q1["lists"]["only_in_chroma"]["list"] == ["b.docx_0"]
    assert "只在 Chroma" in q1["reasons"][0]


def test_equal_counts_with_different_sets_is_still_attention():
    """总数相等而集合不同 —— 只报总数的那类脚本会在这里放绿灯，本单不许。"""
    report, _, _ = run(
        rows={"q1_pg_vector_ids": [("a.pdf_0",), ("a.pdf_1",), ("ghost.pdf_9",)]},
        chroma_ids=CLEAN_IDS,
    )
    q1 = report["questions"]["q1"]
    assert q1["status"] == AUDIT.ATTENTION
    assert (q1["only_in_chroma"], q1["only_in_pg"], q1["both"]) == (1, 1, 2)
    assert q1["pg_total_rows"] == q1["chroma_total_rows"] == 3
    assert any("count_equal_but_sets_differ" in reason for reason in q1["reasons"])


def test_duplicate_ids_on_one_side_are_named_not_flattened():
    """两侧集合相同、Chroma 里同一 id 出现两次 ⇒ 报红。真 chromadb 会不会去重本单没证，
    但至少这里不会把它读成"一致"。"""
    report, _, _ = run(
        rows={"q1_pg_vector_ids": [("a.pdf_0",), ("a.pdf_0",), ("b.docx_0",)]},
        chroma_ids=["a.pdf_0", "a.pdf_0", "b.docx_0"],
    )
    q1 = report["questions"]["q1"]
    assert q1["status"] == AUDIT.ATTENTION
    assert q1["chroma_total_rows"] == 3 and q1["chroma_distinct_ids"] == 2
    assert any("出现多次" in reason for reason in q1["reasons"])
    assert (q1["only_in_chroma"], q1["only_in_pg"]) == (0, 0)


def test_empty_on_both_sides_is_cannot_ask_and_exit_two():
    """0/0 不是"一致"。工单那条"不许把空集合当成一致"就落在这里。"""
    report, _, _ = run(rows={"q1_pg_vector_ids": []}, chroma_ids=[])
    q1 = report["questions"]["q1"]
    assert q1["status"] == AUDIT.CANNOT_ASK
    assert "不许读成" in q1["reasons"][0] or "没有对象" in q1["reasons"][0]
    assert AUDIT.exit_code_for(report) == 2


def test_missing_table_cannot_collaps_into_zero_rows():
    """服务端直接拒（relation does not exist）⇒ asked=False ⇒ cannot_ask + 原文带回，
    绝不塌成"零行 ⇒ 一致"。"""
    error = RuntimeError('relation "chunk_vectors" does not exist')
    report, _, _ = run(rows={"q1_pg_vector_ids": error})
    q1 = report["questions"]["q1"]
    assert q1["status"] == AUDIT.CANNOT_ASK
    assert "does not exist" in q1["blocked_reason"]
    assert AUDIT.exit_code_for(report) == 2


def test_empty_mirror_only_on_pg_side_is_one_sided_and_reported():
    report, _, _ = run(rows={"q1_pg_vector_ids": [], "q2_mirror_totals": [(0, 0)],
                             "q3_pg_generations": []})
    q1 = report["questions"]["q1"]
    assert q1["status"] == AUDIT.ATTENTION  # Chroma 有 3 枚而镜像 0 枚：这是能问的，且是坏消息
    assert (q1["only_in_chroma"], q1["only_in_pg"], q1["both"]) == (3, 0, 0)
    assert any("一张行都没有" in reason for reason in q1["reasons"])
    assert report["questions"]["q2"]["status"] == AUDIT.CANNOT_ASK
    assert report["questions"]["q3"]["status"] == AUDIT.CANNOT_ASK


# ================================================================== 判据②：NULL 的分桶
def test_never_published_null_rows_read_as_pending_not_fault():
    """R76 新语义：文档从没发布过 ⇒ NULL 是正常待回填。这条必须是 clean，不许当故障。"""
    report, _, _ = run(
        rows={"q2_null_rows": [("b.docx", 1, WRITE_NEW, 0, None)], "q2_mirror_totals": [(3, 2)]},
    )
    q2 = report["questions"]["q2"]
    assert q2["status"] == AUDIT.CLEAN
    assert q2["null_rows_total"] == 1 and q2["documents_with_null_rows"] == 1
    assert q2["by_bucket"] == {"never_published": 1}
    reading = q2["rows"][0]["reading"]
    assert "正常待回填" in reading and "不是故障" in reading


def test_rows_written_after_the_last_publication_are_pending_too():
    report, _, _ = run(
        rows={"q2_null_rows": [("a.pdf", 2, "2026-09-22 09:00:00+00", 1, PUBLISHED)],
              "q2_mirror_totals": [(3, 1)]},
    )
    q2 = report["questions"]["q2"]
    assert q2["status"] == AUDIT.CLEAN
    assert list(q2["by_bucket"]) == ["written_after_last_publication"]
    assert "下一次发布会把它收编" in q2["rows"][0]["reading"]


def test_publication_newer_than_write_needs_a_human_and_the_flag_splits_off_legacy():
    """同一份读数：不给 --r76-deployed-at 只能停在"要人看"；给了才拆得出"R76 上线前的存量"。"""
    rows = {"q2_null_rows": [("a.pdf", 2, WRITE_OLD, 1, PUBLISHED)], "q2_mirror_totals": [(3, 1)]}
    import datetime as dt

    plain, _, _ = run(rows=rows)
    assert plain["questions"]["q2"]["status"] == AUDIT.ATTENTION
    assert list(plain["questions"]["q2"]["by_bucket"]) == ["publication_newer_than_write"]

    stamped, _, _ = run(
        rows=rows, r76_deployed_at=dt.datetime(2026, 9, 22, tzinfo=dt.timezone.utc))
    q2 = stamped["questions"]["q2"]
    assert list(q2["by_bucket"]) == ["legacy_before_r76"]
    # 拆成"历史存量"不等于判它没问题：镜像里还挂着没回填的行，语义上仍要人再发布一次。
    assert q2["status"] == AUDIT.ATTENTION
    assert "再发布一次" in q2["rows"][0]["reading"]
    assert stamped["r76_deployed_at"].startswith("2026-09-22")


def test_mixed_timestamp_offsets_stop_at_the_unclassified_bucket_instead_of_500():
    """TIMESTAMPTZ 正常都带时区；万一一个带一个不带，比较本身没有定义 —— 停在未分类并报红，
    而不是让审计在判读到一半时抛 TypeError，也不是挑一个桶把人支走。"""
    report, _, _ = run(
        rows={"q2_null_rows": [("a.pdf", 1, "2026-09-20 01:00:00", 1, PUBLISHED)],
              "q2_mirror_totals": [(3, 2)]},
    )
    q2 = report["questions"]["q2"]
    assert q2["status"] == AUDIT.ATTENTION
    assert list(q2["by_bucket"]) == ["unparsable_timestamp"]
    assert "时区" in q2["rows"][0]["reading"]


def test_the_two_independent_null_counts_must_agree():
    """按文档聚合的 NULL 与按总量反推的 NULL 是两条独立算法，对不上就报红。"""
    report, _, _ = run(
        rows={"q2_null_rows": [("a.pdf", 1, WRITE_NEW, 0, None)], "q2_mirror_totals": [(9, 9)]},
    )
    q2 = report["questions"]["q2"]
    assert q2["status"] == AUDIT.ATTENTION
    assert any("两条独立算法对不上" in line for line in q2["cross_checks"])
    assert q2["by_bucket"] == {"never_published": 1}  # 分桶本身仍是正常态，红的是对账


def test_empty_mirror_table_is_cannot_ask_not_fully_backfilled():
    report, _, _ = run(rows={"q2_mirror_totals": [(0, 0)]})
    q2 = report["questions"]["q2"]
    assert q2["status"] == AUDIT.CANNOT_ASK
    assert "不许读成全部已回填" in q2["blocked_reason"]
    assert q2["null_rows_total"] == 0 and q2["mirror_rows"] == 0


def test_binding_without_a_matching_index_version_is_named():
    report, _, _ = run(rows={"q2_dangling_bindings": [
        ("a.pdf_0", "iv-gone", "no_such_index_version")]})
    q2 = report["questions"]["q2"]
    assert q2["status"] == AUDIT.ATTENTION
    assert q2["binding_anomalies"]["list"] == ["a.pdf_0 -> iv-gone (no_such_index_version)"]
    assert q2["binding_anomalies"]["count"] == 1


def test_a_failing_binding_probe_is_attention_not_silence():
    report, _, _ = run(rows={
        "q2_dangling_bindings": RuntimeError("permission denied for index_registry")})
    q2 = report["questions"]["q2"]
    assert q2["status"] == AUDIT.ATTENTION
    assert "permission denied" in q2["binding_anomalies"]["blocked"]


def test_document_lists_are_capped_but_totals_are_not():
    rows = [("d%d.pdf" % i, 1, WRITE_NEW, 0, None) for i in range(5)]
    report, _, _ = run(rows={"q2_null_rows": rows, "q2_mirror_totals": [(8, 3)]})
    q2 = report["questions"]["q2"]
    assert q2["null_rows_total"] == 5
    assert q2["documents_total"] == 5 and len(q2["rows"]) == 5  # 默认 list_limit=20
    capped = run(rows={"q2_null_rows": rows, "q2_mirror_totals": [(8, 3)]}, list_limit=2)
    assert len(capped[0]["questions"]["q2"]["rows"]) == 2
    assert capped[0]["questions"]["q2"]["documents_total"] == 5


# ================================================================== 判据③：代际
def test_single_generation_matching_scope_is_clean():
    report, _, _ = run()
    q3 = report["questions"]["q3"]
    assert q3["status"] == AUDIT.CLEAN
    assert q3["generation_count"] == 1
    assert q3["generations"][0]["embedding_model"] == MODEL
    assert q3["generations"][0]["matches_declared_scope"] is True


def test_second_generation_is_named_as_the_shape_r76_refuses():
    """换模型留下半张脸的形状 = 两代并存。这一格必须具名报出来，不许只报"分组 2 条"。"""
    report, _, _ = run(rows={"q3_pg_generations": [
        (MODEL, DIM, 3, WRITE_OLD, WRITE_NEW), ("bge-m3", "1024", 7, WRITE_OLD, WRITE_NEW)]})
    q3 = report["questions"]["q3"]
    assert q3["status"] == AUDIT.ATTENTION
    assert q3["generation_count"] == 2
    joined = " ".join(q3["reasons"])
    assert "bge-m3/1024×7" in joined and "nomic-embed-text/768×3" in joined
    assert "R76" in joined


def test_counter_evidence_a_changed_dimension_turns_q3_red():
    """反证第二把：把镜像里那一代的 dimension 改成 1024（声明仍是 768）⇒ Q3 必须报红。"""
    report, _, _ = run(rows={"q3_pg_generations": [(MODEL, "1024", 3, WRITE_OLD, WRITE_NEW)]})
    q3 = report["questions"]["q3"]
    assert q3["status"] == AUDIT.ATTENTION
    assert q3["generations"][0]["matches_declared_scope"] is False
    assert any("与 vector_scope 声明的" in reason for reason in q3["reasons"])


def test_declared_column_that_disagrees_with_the_real_vector_is_named():
    report, _, _ = run(rows={"q3_shape_lies": [("a.pdf_0", "768", "1024")]})
    q3 = report["questions"]["q3"]
    assert q3["status"] == AUDIT.ATTENTION
    assert q3["shape_lies"]["list"] == ["a.pdf_0 声明 768 实宽 1024"]
    assert any("vector_dims(embedding)" in reason for reason in q3["reasons"])


def test_unreadable_scope_still_reports_the_grouping_but_asks_a_question():
    missing = RuntimeError('relation "vector_scope" does not exist')
    report, _, _ = run(rows={"q3_declared_scope": missing})
    q3 = report["questions"]["q3"]
    assert q3["declared_scope"] is None
    assert q3["status"] == AUDIT.ATTENTION
    assert q3["generation_count"] == 1
    assert any("没有声明口径" in reason for reason in q3["reasons"])


def test_chroma_side_with_two_widths_is_reported():
    report, _, _ = run(chroma_ids=CLEAN_IDS, width=[768, 768, 1024])
    q3 = report["questions"]["q3"]
    assert q3["chroma_widths"] == {"768": 2, "1024": 1}
    assert q3["status"] == AUDIT.ATTENTION
    assert any("Chroma 侧宽度也不止一种" in reason for reason in q3["reasons"])


def test_empty_mirror_grouping_is_cannot_ask_not_single_generation():
    report, _, _ = run(rows={"q3_pg_generations": []})
    q3 = report["questions"]["q3"]
    assert q3["status"] == AUDIT.CANNOT_ASK
    assert q3["generation_count"] == 0
    assert "别读成" in q3["reasons"][0]


def test_blank_embedding_model_is_a_written_bad_row():
    report, _, _ = run(rows={"q3_pg_generations": [("", DIM, 3, WRITE_OLD, WRITE_NEW)],
                             "q3_declared_scope": []})
    q3 = report["questions"]["q3"]
    assert any("embedding_model 是空串" in reason for reason in q3["reasons"])


# ================================================================== 判据④：孤儿
def test_no_orphans_and_no_shape_violations_is_clean():
    report, _, _ = run()
    q4 = report["questions"]["q4"]
    assert q4["status"] == AUDIT.CLEAN
    assert q4["vectors_without_chunks"]["count"] == 0
    assert q4["chunks_without_vectors_total"] == 0


def test_a_vector_row_without_a_chunk_is_named():
    report, _, _ = run(rows={"q4_vectors_without_chunks": [
        ("ghost.pdf_9", "ghost.pdf", 9, "iv-1", WRITE_NEW)]})
    q4 = report["questions"]["q4"]
    assert q4["status"] == AUDIT.ATTENTION
    assert q4["vectors_without_chunks"]["list"] == [
        "ghost.pdf_9 (filename=ghost.pdf chunk_index=9 index_version_id=iv-1)"]
    assert any("镜像有、账上没有" in reason for reason in q4["reasons"])


def test_only_chunks_on_a_currently_published_version_are_a_fault():
    """老版本留下的 chunk 行没有向量行是历史正常态（retire 删过向量），列出来但不算故障；
    当前发布版本还挂着的才是。两个数分开报，不混成一个"孤儿数"。"""
    report, _, _ = run(rows={"q4_chunks_without_vectors": [
        ("old.pdf_0", 1, 0, 0), ("live.pdf_0", 2, 1, 2)]})
    q4 = report["questions"]["q4"]
    assert q4["chunks_without_vectors_total"] == 2
    assert q4["chunks_without_vectors_on_current_version"] == 1
    assert q4["status"] == AUDIT.ATTENTION
    assert any("当前发布版本" in reason for reason in q4["reasons"])
    listed = q4["chunks_without_vectors"]["list"]
    assert any(item.startswith("old.pdf_0") for item in listed)


def test_chunk_ids_the_derivation_does_not_fit_are_called_out_loudly():
    """派生尺不适用的行必须先点名，否则上面两条孤儿判定就是在胡说。"""
    report, _, _ = run(rows={"q4_chunk_id_shapes": [("no-ordinal-chunk", "a.pdf", "iv-1")]})
    q4 = report["questions"]["q4"]
    assert q4["status"] == AUDIT.ATTENTION
    assert q4["chunk_id_shapes_not_derivable"]["list"] == ["no-ordinal-chunk (resource_id=a.pdf)"]
    assert any("派生尺对它们不成立" in reason and "不可信" in reason for reason in q4["reasons"])


def test_vector_id_that_disagrees_with_its_own_columns_is_named():
    report, _, _ = run(rows={"q4_vector_id_shapes": [("a.pdf__0", "a.pdf", 0)]})
    q4 = report["questions"]["q4"]
    assert q4["status"] == AUDIT.ATTENTION
    assert q4["vector_id_shape_violations"]["list"] == ["a.pdf__0"]


def test_either_orphan_query_failing_asks_nothing():
    report, _, _ = run(rows={"q4_chunks_without_vectors": RuntimeError("query cancelled")})
    q4 = report["questions"]["q4"]
    assert q4["status"] == AUDIT.CANNOT_ASK
    assert "query cancelled" in q4["blocked_reason"]


# ================================================================== 前置：缺表不许读成零差异
def test_missing_chunk_vectors_blocks_every_question_by_name():
    report, _, _ = run(rows={"preconditions": precondition_rows(
        drop_tables=(AUDIT.DEFAULT_VECTOR_TABLE,))})
    pre = report["preconditions"]
    assert pre["ok"] is False
    assert set(pre["askable"]) == {"q1", "q2", "q3", "q4"}
    assert all(value is False for value in pre["askable"].values())
    assert any("表 chunk_vectors 不存在" in line for line in pre["blocking"])
    assert all(value["status"] == AUDIT.CANNOT_ASK for value in report["questions"].values())
    assert AUDIT.exit_code_for(report) == 2


def test_missing_column_is_reported_as_a_missing_column_not_a_missing_table():
    columns = [row for row in precondition_rows()
               if row != (AUDIT.DEFAULT_CHUNKS_TABLE, "metadata")]
    report, _, _ = run(rows={"preconditions": columns})
    pre = report["preconditions"]
    assert pre["askable"]["q4"] is False and pre["askable"]["q1"] is True
    assert any("表 chunks 缺列 metadata" in line for line in pre["blocking"])
    assert report["questions"]["q1"]["status"] == AUDIT.CLEAN
    assert report["questions"]["q4"]["status"] == AUDIT.CANNOT_ASK


def test_information_schema_unreachable_leaves_nothing_askable():
    report, _, _ = run(rows={"preconditions": RuntimeError("connection timeout")})
    assert report["preconditions"]["ok"] is False
    assert any("information_schema" in line for line in report["preconditions"]["blocking"])
    assert all(value["status"] == AUDIT.CANNOT_ASK for value in report["questions"].values())


def test_row_counts_drifting_during_the_audit_is_visible_in_self_check():
    """审计前后各数一次行数。假件第二次给出不同的数 ⇒ row_counts_stable 必须翻成 False。
    这一条是"我没写库"的可证伪面：稳定的反证长这样。"""
    reader = FakeReader(world_rows(**{
        "self_check_counts": lambda call_no: (
            [(AUDIT.DEFAULT_VECTOR_TABLE, 3), (AUDIT.DEFAULT_CHUNKS_TABLE, 3)]
            if call_no == 1 else [(AUDIT.DEFAULT_VECTOR_TABLE, 4),
                                   (AUDIT.DEFAULT_CHUNKS_TABLE, 3)])}))
    collection = FakeCollection(CLEAN_IDS)
    view = AUDIT.read_chroma(collection)
    view.update({"ok": True})
    report = AUDIT.audit(reader, AUDIT.build_queries(
        AUDIT.DEFAULT_VECTOR_TABLE, AUDIT.DEFAULT_CHUNKS_TABLE, AUDIT.DEFAULT_SCOPE_TABLE),
        view, options())
    assert report["self_check"]["row_counts_stable"] is False
    assert report["self_check"]["row_counts_before"]["tables"] == {"chunk_vectors": 3, "chunks": 3}
    assert report["self_check"]["row_counts_after"]["tables"] == {"chunk_vectors": 4, "chunks": 3}


def test_counts_that_cannot_be_taken_are_reported_as_not_measured():
    """表读不到时前后两次数行都会失败 —— 这一格必须是 None（没测到），不是 False（测到变化）。

    本机真库实测就长这样：五张镜像表一张都没有，把 None 打成 False 会把读者支去查"谁在并发写"。
    """
    poison = RuntimeError(chr(39) + "chunk_vectors" + chr(39) + " 不存在")
    report, _, _ = run(rows={"self_check_counts": poison})
    assert report["self_check"]["row_counts_stable"] is None
    assert report["self_check"]["row_counts_before"]["asked"] is False
    text = AUDIT.render(report, 20)
    assert "审计前后行数稳定=问不出来" in text
    assert "模型调用=0" in text


# ================================================================== 出口：渲染与退出码
def test_render_names_all_four_questions_and_their_numbers():
    text = AUDIT.render(run()[0], 20)
    for marker in ("Q1 只在 Chroma=0 只在 PG=0 两边都有=3", "Q2 NULL 行=0", "Q3 代际=1",
                   "Q4 向量无 chunk=0", "模型调用=0，距离比较=0"):
        assert marker in text, marker


def test_render_says_which_question_could_not_be_asked():
    report, _, _ = run(rows={"q3_pg_generations": RuntimeError("boom")})
    text = AUDIT.render(report, 20)
    assert "Q3 问不出来：RuntimeError: boom" in text
    assert AUDIT.exit_code_for(report) == 2


def test_exit_code_is_zero_only_when_chroma_read_and_all_four_are_clean():
    clean, _, _ = run()
    assert AUDIT.exit_code_for(clean) == 0
    attention, _, _ = run(rows={"q4_vectors_without_chunks": [
        ("ghost.pdf_9", "ghost.pdf", 9, None, WRITE_NEW)]})
    assert AUDIT.exit_code_for(attention) == 1
    broken_chroma = dict(clean)
    broken_chroma["chroma"] = dict(clean["chroma"], ok=False)
    assert AUDIT.exit_code_for(broken_chroma) == 2


def test_exit_code_two_when_a_question_is_missing_entirely():
    """四问少一问也算问不出来，不许因为"没报错"就返回 0。"""
    report, _, _ = run()
    report["questions"].pop("q4")
    report["verdict"].pop("q4")
    assert AUDIT.exit_code_for(report) == 2
# ================================================================== 整场：main() 走一遍假通道
def _clean_main(tmp_path):
    """把 main() 的两条注入口都换成假件，跑一整场，返回 (退出码, JSON 报告, 记账)。"""
    source = tmp_path / "chroma_db"
    (source / "collection").mkdir(parents=True)
    (source / "chroma.sqlite3").write_bytes(b"not-a-real-sqlite-file")
    (source / "collection" / "data_level0.bin").write_bytes(b"bin-bytes")
    work = tmp_path / "work"
    work.mkdir()
    out = tmp_path / "r145.json"
    clients: list = []
    collection = FakeCollection(CLEAN_IDS)

    def client_factory(path):
        client = FakeClient(collection, clients)
        client.path = path
        return client

    reader = FakeReader(world_rows())
    code = AUDIT.main(
        ["--chroma-dir", str(source), "--work-dir", str(work), "--out", str(out),
         "--chroma-page", "2"],
        reader_factory=lambda args: reader,
        client_factory=client_factory,
    )
    report = json.loads(out.read_text(encoding="utf-8"))
    return code, report, source, work, clients, reader


def test_main_audits_through_fakes_without_touching_the_source_directory(tmp_path):
    code, report, source, work, clients, reader = _clean_main(tmp_path)
    assert code == 0
    assert report["verdict"] == {key: AUDIT.CLEAN for key in ("q1", "q2", "q3", "q4")}
    assert report["chroma"]["source_untouched"] is True
    assert report["chroma"]["source_manifest_before"] == report["chroma"]["source_manifest_after"]
    assert report["chroma"]["total"] == 3 and report["chroma"]["get_calls"] == 2
    assert report["self_check"]["model_calls"] == 0
    assert report["self_check"]["distance_comparisons"] == 0
    assert report["self_check"]["chroma_source_files"] == 2
    assert report["pg_transport"] == "fake-read-only"
    assert reader.closed == 1  # main() 负责关通道

    opened = Path(report["chroma"]["opened_path"])
    assert opened != source.resolve()
    assert opened.parent.parent == work.resolve()
    assert opened.name == "chroma_db"
    assert not opened.exists()  # 没给 --keep-copy ⇒ 副本用完即删
    assert clients and clients[0].requested == AUDIT.DEFAULT_COLLECTION
    assert str(opened) == clients[0].path
    # 仓库目录里一个字节都没多：没有 -wal / -shm，也没有新文件
    assert sorted(path.name for path in source.rglob("*")) == [
        "chroma.sqlite3", "collection", "data_level0.bin"]


def test_main_keeps_the_copy_when_asked_and_still_leaves_the_source_alone(tmp_path):
    source = tmp_path / "chroma_db"
    source.mkdir()
    (source / "chroma.sqlite3").write_bytes(b"abc")
    work = tmp_path / "work"
    work.mkdir()
    collection = FakeCollection(CLEAN_IDS)
    kept: list = []

    def client_factory(path):
        kept.append(path)
        return FakeClient(collection, [])

    code = AUDIT.main(
        ["--chroma-dir", str(source), "--work-dir", str(work), "--keep-copy"],
        reader_factory=lambda args: FakeReader(world_rows()), client_factory=client_factory,
    )
    assert code == 0
    assert len(kept) == 1 and Path(kept[0]).exists()
    assert kept[0].startswith(str(work))
    assert Path(source / "chroma.sqlite3").read_bytes() == b"abc"


def test_main_reports_the_source_is_untouched_even_when_chroma_cannot_be_opened(tmp_path):
    """打不开 collection 也要把"仓库目录没被动过"这句说出来，而不是直接崩在打开那一步。"""
    source = tmp_path / "chroma_db"
    source.mkdir()
    (source / "chroma.sqlite3").write_bytes(b"abc")

    def client_factory(path):
        raise AUDIT.MirrorUnavailable("chromadb exploded")

    code = AUDIT.main(
        ["--chroma-dir", str(source), "--work-dir", str(tmp_path)],
        reader_factory=lambda args: FakeReader(world_rows()), client_factory=client_factory,
    )
    assert code == 2  # Chroma 侧读不到 ⇒ 整场没有可信结论，不许返回 0
    # 就算死在打开那一步，仓库那个目录也还是原样：没多文件、没被改写字节
    assert sorted(path.name for path in source.iterdir()) == ["chroma.sqlite3"]
    assert (source / "chroma.sqlite3").read_bytes() == b"abc"
def _small_source(tmp_path):
    """造一枚最小的"仓库 Chroma 目录"，只够 copytree 用。"""
    source = tmp_path / "chroma_db"
    source.mkdir()
    (source / "chroma.sqlite3").write_bytes(b"abc")
    work = tmp_path / "work"
    work.mkdir()
    return source, work


def test_a_copy_that_cannot_be_removed_is_named_instead_of_swallowed(tmp_path, monkeypatch):
    """以前这里是 shutil.rmtree(..., ignore_errors=True)：真机上 chromadb 还握着句柄时它
    会静静失败，等于把 200MB 临时副本留在客户机器上 —— 本机实测就一次都没删掉过。
    """
    source, work = _small_source(tmp_path)
    out = tmp_path / "r145.json"

    def refusing_rmtree(path, *args, **kwargs):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(AUDIT.shutil, "rmtree", refusing_rmtree)
    code = AUDIT.main(
        ["--chroma-dir", str(source), "--work-dir", str(work), "--out", str(out)],
        reader_factory=lambda args: FakeReader(world_rows()),
        client_factory=lambda path: FakeClient(FakeCollection(CLEAN_IDS), []),
    )
    assert code == 0  # 清理失败不是审计失败，别拿退出码去遮它
    report = json.loads(out.read_text(encoding="utf-8"))
    cleanup = report["chroma_copy_cleanup"]
    assert cleanup["attempted"] is True and cleanup["removed"] is False
    assert "Permission denied" in cleanup["error"]
    assert cleanup["path"].startswith(str(work))
    assert report["chroma"]["source_untouched"] is True  # 仓库目录依旧一个字没动


def test_keep_copy_records_that_no_cleanup_was_attempted(tmp_path):
    source, work = _small_source(tmp_path)
    out = tmp_path / "r145.json"
    code = AUDIT.main(
        ["--chroma-dir", str(source), "--work-dir", str(work), "--keep-copy",
         "--out", str(out)],
        reader_factory=lambda args: FakeReader(world_rows()),
        client_factory=lambda path: FakeClient(FakeCollection(CLEAN_IDS), []),
    )
    assert code == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["chroma_copy_cleanup"] == {"attempted": False}
    assert (source / "chroma.sqlite3").read_bytes() == b"abc"
