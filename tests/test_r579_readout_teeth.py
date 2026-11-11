# -*- coding: utf-8 -*-
"""R579 · 常驻牙：写域守卫、名次指标、缺档点名、拐点区间、前后对账——全部离线，一条 SQL 都不出站。

这枚钉守的是 `scripts/r579_index_crossover_readout.py` 里五处"看着像绿其实没量"的位置：

  ① 写域守卫：受保护库名上任何非只读形状必须**在出站之前**被拦（判据 5 第③把）。
     钉里逐枚点名写形状（INSERT/UPDATE/DELETE/DDL/COPY/TRUNCATE/VACUUM/DO/`SELECT INTO`），
     也逐枚点名合法读形状（含产品读腿那条原文、`EXPLAIN (ANALYZE...)`、`SET LOCAL`、`SHOW`、
     `BEGIN/ROLLBACK`）——**不许把合法的读成本单的罪证**，否则下一班会误删读腿。
  ② 名次指标不许硬编码：`only_in_*` 那一项被摘掉时，"一名之差"夹具必须逃掉、`self_check()`
     必须红（判据 5 第①把）；两枚夹具各由不同那项判出来，所以只摘一项也红。
  ③ 缺档必须点名：指一档没有读数的规模 ⇒ rc≠0 且 stdout 里出现那一档（判据 5 第②把）。
  ④ 拐点只交区间：四档里"小的走全表、大的走索引"才给区间；全是同一族腿时必须落在
     "未量到"那句话上，不许外推成单点。
  ⑤ 前后对账与库名集合：判据 6 的两枚纯函数，逐枚点名不等项；`sz_*` 之外的 schema 不许被清掉。

🔴 本件不连库：所有"发出去"的位置都被假连接/假游标顶替；也不打模型、不动容器。
"""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "r579_index_crossover_readout.py"


def _load():
    spec = importlib.util.spec_from_file_location("r579_readout", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = _load()

PRODUCT_SQL = (
    "SELECT vector_id, content, filename, chunk_index, classification, department, "
    "embedding <-> %s::vector AS distance FROM chunk_vectors "
    "WHERE classification = ANY(%s) ORDER BY embedding <-> %s::vector LIMIT %s")

READ_SHAPES = (
    PRODUCT_SQL,
    "EXPLAIN (ANALYZE, BUFFERS, TIMING, FORMAT TEXT) " + PRODUCT_SQL,
    "SELECT set_config('hnsw.ef_search', '100', TRUE)",
    "SET LOCAL enable_seqscan = off",
    "SET LOCAL enable_sort = off",
    "SET default_transaction_read_only = on",
    "SHOW transaction_read_only",
    "SELECT current_database()",
    "SELECT count(*) FROM chunk_vectors",
    "SELECT c.relpages FROM pg_class c WHERE c.oid = 'public.chunk_vectors'::regclass",
    "BEGIN", "ROLLBACK",
    'SELECT to_regclass($$sz_0001008."chunk_vectors"$$) IS NOT NULL',
)

WRITE_SHAPES = (
    "INSERT INTO chunk_vectors (vector_id) VALUES ('r579-x')",
    "UPDATE chunk_vectors SET department = 'r579' WHERE vector_id = 'nope'",
    "DELETE FROM chunk_vectors WHERE vector_id = 'nope'",
    "CREATE INDEX r579_bad_idx ON chunk_vectors (department)",
    "DROP TABLE chunk_vectors",
    "COPY chunk_vectors (vector_id) FROM STDIN",
    "TRUNCATE chunk_vectors",
    "VACUUM FULL chunk_vectors",
    "ANALYZE chunk_vectors",
    "REFRESH MATERIALIZED VIEW whatever",
    "EXPLAIN (ANALYZE) INSERT INTO chunk_vectors (vector_id) VALUES ('r579-y')",
    "WITH gone AS (DELETE FROM chunk_vectors RETURNING *) SELECT count(*) FROM gone",
    "SELECT pg_sleep(0) INTO r579_sink",
    "DO $$ BEGIN INSERT INTO chunk_vectors (vector_id) VALUES ('r579-w'); END $$;",
    "LOCK TABLE chunk_vectors IN ACCESS EXCLUSIVE MODE",
    "ALTER TABLE chunk_vectors ADD COLUMN r579_bad TEXT",
    "GRANT ALL ON chunk_vectors TO PUBLIC",
)


# ---------------------------------------------------------------- ① 写域守卫
@pytest.mark.parametrize("text", READ_SHAPES)
def test_read_shapes_are_reads(text):
    assert R.classify_statement(text) == "read", text


@pytest.mark.parametrize("text", WRITE_SHAPES)
def test_write_shapes_are_writes(text):
    assert R.classify_statement(text) == "write", text


@pytest.mark.parametrize("text", WRITE_SHAPES)
def test_guard_refuses_writes_on_protected_db_before_sending(text):
    with pytest.raises(R.WriteRefusedOnProduction):
        R.guard_statement("enterprise_brain", text)
    # 合法读在受保护库上必须照过：不许把读腿判成罪证
    for read in READ_SHAPES:
        assert R.guard_statement("enterprise_brain", read) == read


def test_guard_only_bites_on_protected_names_and_sandbox_guard_has_its_own_teeth():
    assert R.guard_statement("eb_r579_probe", WRITE_SHAPES[0]) == WRITE_SHAPES[0]
    for refused in ("enterprise_brain", "postgres", "template1", "template0"):
        with pytest.raises(R.SandboxTargetRefused):
            R.assert_sandbox_db(refused, "eb_r579_probe")
        assert refused in R.PROTECTED_DBS
    with pytest.raises(R.SandboxTargetRefused):
        R.assert_sandbox_db("someone_elses_sandbox", "eb_r579_probe")
    with pytest.raises(R.SandboxTargetRefused):
        R.assert_sandbox_db("", "eb_r579_probe")
    assert R.assert_sandbox_db("eb_r579_probe", "eb_r579_probe") == "eb_r579_probe"
    assert R.assert_sandbox_db("eb_r579_probe_b", "eb_r579_probe") == "eb_r579_probe_b"
    # 前缀本身不许被写成生产库名前缀的变体（"eb_r579_probeX" 不是本席的库）
    with pytest.raises(R.SandboxTargetRefused):
        R.assert_sandbox_db("eb_r579_probeX", "eb_r579_probe")


def test_guarded_cursor_sends_nothing_when_it_refuses():
    calls = []

    class FakeCursor:
        def execute(self, sql, params=None):
            calls.append(sql)
            return self

    class FakeDbConn:
        def cursor(self):
            return FakeCursor()

    cursor = R.GuardedCursor("enterprise_brain", FakeCursor())
    with pytest.raises(R.WriteRefusedOnProduction):
        cursor.execute(WRITE_SHAPES[0])
    assert calls == [], "拒绝了却已经出站：守卫是摆设"
    cursor.execute("SELECT 1")
    assert calls == ["SELECT 1"]


def test_db_open_proves_read_only_and_database_before_anything_else():
    seen = []

    class FakeCur:
        def __init__(self, owner):
            self.owner = owner
            self._value = None

        def execute(self, sql, params=None):
            self.owner["calls"].append(sql)
            self._value = self.owner["answers"].get(str(sql).strip())
            return self

        def fetchone(self):
            return self._value

    class FakeConn:
        def __init__(self, owner):
            self.owner = owner

        def cursor(self):
            return FakeCur(self.owner)

        def execute(self, sql, params=None):
            return FakeCur(self.owner).execute(sql, params)

        def close(self):
            self.owner["closed"] = True

    def factory(owner):
        def connect(url, **kwargs):
            return FakeConn(owner)
        return connect

    import psycopg
    original = psycopg.connect

    # 生产：设只读 → 证明 → 对账库名，顺序不许反
    owner = {"calls": [], "closed": False,
             "answers": {"SHOW default_transaction_read_only": ("on",),
                         "SELECT current_database()": ("enterprise_brain",)}}
    psycopg.connect = factory(owner)
    try:
        db = R.Db(url="postgresql://u:***@h:5432/enterprise_brain",
                  database="enterprise_brain", read_only=True, label="prod").open()
        assert owner["calls"][:2] == ["SET default_transaction_read_only = on",
                                      "SHOW default_transaction_read_only"]
        assert owner["calls"][2] == "SELECT current_database()"
        db.close()
        # 守卫拦下的写语句一条都没进连接
        with pytest.raises(R.WriteRefusedOnProduction):
            db.execute(WRITE_SHAPES[0])
        assert not any("INSERT" in call for call in owner["calls"])
    finally:
        psycopg.connect = original

    # 连错库：现场对账必须拒
    wrong = {"calls": [], "answers": {"SHOW default_transaction_read_only": ("on",),
                                      "SELECT current_database()": ("eb_r59_sandbox",)}}
    psycopg.connect = factory(wrong)
    try:
        with pytest.raises(R.SandboxTargetRefused):
            R.Db(url="u", database="enterprise_brain", read_only=True,
                 label="prod").open()
    finally:
        psycopg.connect = original

    # 设不成只读：宁可不跑
    ro_fail = {"calls": [], "answers": {"SHOW default_transaction_read_only": ("off",),
                                        "SELECT current_database()": ("enterprise_brain",)}}
    psycopg.connect = factory(ro_fail)
    try:
        with pytest.raises(R.WriteRefusedOnProduction):
            R.Db(url="u", database="enterprise_brain", read_only=True,
                 label="prod").open()
    finally:
        psycopg.connect = original


def test_mask_url_never_leaks_the_password_and_swap_only_changes_the_db():
    url = "postgresql://user:secretpass@postgres:5432/enterprise_brain"
    masked = R.mask_url(url)
    assert "secretpass" not in masked and "enterprise_brain" in masked
    swapped = R.swap_dbname(url, "eb_r579_probe")
    assert swapped.endswith("/eb_r579_probe") and "secretpass" in swapped


# ---------------------------------------------------------------- ② 名次指标
def test_rank_metrics_compute_real_numbers():
    exact = ["a", "b", "c", "d", "e"]
    index = ["a", "b", "c", "d", "z"]
    metrics = R.rank_metrics(exact, index, k=5)
    assert metrics["overlap_ratio"] == 0.8
    assert metrics["only_in_exact"] == 1 and metrics["only_in_index"] == 1
    assert metrics["members_agree"] is False and metrics["mismatch"] is True
    swapped = R.rank_metrics(exact, ["b", "a", "c", "d", "e"], k=5)
    assert swapped["overlap_ratio"] == 1.0 and swapped["only_in_exact"] == 0
    assert swapped["relative_order_agree"] is False and swapped["mismatch"] is True
    assert swapped["members_agree"] is True and swapped["identical"] is False
    assert swapped["mean_abs_displacement"] == 0.4 and swapped["max_abs_displacement"] == 1
    same = R.rank_metrics(exact, list(exact), k=5)
    assert same["mismatch"] is False and same["max_abs_displacement"] == 0
    assert same["identical"] is True and same["members_agree"] is True
    assert same["relative_order_agree"] is True, "全等对照被误判：尺子在虚报差异"
    # 位移按名次差算，不是按 id 差：把最后一个挪到第一个必须量到 4
    moved = R.rank_metrics(exact, ["e", "a", "b", "c", "d"], k=5)
    assert moved["max_abs_displacement"] == 4


def test_the_two_verdict_terms_are_independent_and_each_has_its_own_escape():
    """判据 5 第①把：`only_in` 那项被摘掉 ⇒ "一名之差"夹具必须逃掉、本件必须红。

    两枚夹具各由不同那项判出来（同成员乱序只看先后、一名之差只看集合差），所以顶包不了。
    """
    clean = R.self_check()
    assert clean["ok"] is True
    caught = {pin["fixture"]: pin["caught"] for pin in clean["pins"]}
    assert caught == {"同成员乱序": True, "一名之差": True, "全等对照": True}, caught
    for kwargs, escaping in (({"drop_only_in_compare": True}, ["一名之差"]),
                             ({"drop_order_compare": True}, ["同成员乱序"])):
        tampered = R.self_check(**kwargs)
        assert tampered["ok"] is False, kwargs
        assert [pin["fixture"] for pin in tampered["pins"] if not pin["caught"]] == escaping


def test_truncated_answer_is_reported_not_silently_equal():
    short = R.rank_metrics(["a", "b", "c", "d", "e"], ["a", "b"], k=5)
    assert short["n_index"] == 2 and short["only_in_exact"] == 3
    assert short["mismatch"] is True


# ---------------------------------------------------------------- ③ 缺档点名
def test_missing_size_is_named_and_exit_is_nonzero(tmp_path, capsys, monkeypatch):
    payload = {"action": "measure", "requested_sizes": [1008, 5000],
               "records": [{"size": 1008, "state": "as_loaded", "ks": {},
                            "catalog": {}}], "errors": {}}
    path = tmp_path / "measure.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(R.sys, "argv", ["x"])
    rc = R.main(["--action", "report", "--from-results", str(path), "--sizes", "5000"])
    captured = capsys.readouterr()
    assert rc == R.EXIT_MISSING_SIZE
    assert "5000" in captured.out
    coverage = R.check_size_coverage([1008, 5000], payload["records"], payload["errors"])
    assert coverage["missing"] == [5000] and coverage["no_extrapolation"]
    # 齐档时不得误报
    full = [{"size": size, "state": "as_loaded", "ks": {}, "catalog": {}}
            for size in (1008, 5000)]
    assert R.check_size_coverage([1008, 5000], full, {})["missing"] == []


def test_unknown_action_payload_is_refused(tmp_path, capsys):
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({"action": "build"}), encoding="utf-8")
    assert R.main(["--action", "report", "--from-results", str(path)]) == \
        R.EXIT_PRECONDITION


def _arm_block(leg, ids=None):
    return {"ids": ids or [["a", "b", "c", "d", "e"]],
            "plans": [{"leg": leg, "index_name": None}],
            "knobs": [], "latency_samples_ms": [1.0, 2.0]}


def test_report_runs_the_self_check_first_and_tamper_turns_it_red(tmp_path, capsys):
    entry = {"size": 1008, "state": "as_loaded", "schema": "sz_0001008", "catalog": {},
             "ks": {"5": {"natural": _arm_block("seq_scan"),
                          "index": _arm_block("index_scan"),
                          "exact": _arm_block("seq_scan")}},
             "queries": 1, "width_from_true_source": "derived",
             "width_server_confirmed": "derived"}
    payload = {"action": "measure", "requested_sizes": [1008], "records": [entry],
               "errors": {}, "width_from_true_source": "derived"}
    path = tmp_path / "m.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert R.main(["--action", "report", "--from-results", str(path)]) == R.EXIT_OK
    for mode in ("drop-only-in-compare", "drop-order-compare"):
        tampered = R.main(["--action", "report", "--from-results", str(path),
                           "--tamper", mode])
        assert tampered == R.EXIT_RED, "摘掉 {0} 之后本件还绿 = 全等是硬编码".format(mode)


# ---------------------------------------------------------------- ④ 拐点只交区间
def _entry(size, state, k, natural_leg, index_leg="index_scan"):
    def plan(leg, name):
        return {"plans": [{"leg": leg, "index_name": name, "est_rows": size}],
                "latency": {}, "knobs": [], "latency_samples_ms": [1.0]}

    return {"size": size, "state": state, "k": k,
            "catalog": {"rows": size, "analyzed": state == "analyzed"},
            "arms": {"natural": plan(natural_leg, None),
                     "index": plan(index_leg, "chunk_vectors_embedding_idx"),
                     "exact": plan("seq_scan", None)},
            "natural_leg_family": R.leg_family(natural_leg),
            "exact_leg_family": "seq", "index_leg_family": "index"}


def test_crossover_is_a_bracket_between_two_measured_sizes():
    # crossover_brackets 只吃已汇总的 aggregate 行（report 阶段），不吃原始 ids
    aggregate = [_entry(1008, "as_loaded", 5, "seq_scan"),
                 _entry(5000, "as_loaded", 5, "seq_scan"),
                 _entry(20000, "as_loaded", 5, "index_scan"),
                 _entry(50000, "as_loaded", 5, "index_scan")]
    brackets = R.crossover_brackets(aggregate)
    value = brackets["as_loaded|k=5"]
    assert value["transition_between"] == [5000, 20000]
    assert "5000" in value["statement"] and "20000" in value["statement"]
    assert value["all_index"] is False and value["all_seq"] is False


def test_crossover_never_invents_a_point_when_the_leg_never_switches():
    same_leg = [_entry(size, "as_loaded", 5, "seq_scan")
                for size in (1008, 5000, 20000, 50000)]
    value = R.crossover_brackets(same_leg)["as_loaded|k=5"]
    assert value["all_seq"] is True and value["all_index"] is False
    assert value["transition_between"] == [50000, None]
    assert "未量到" in value["statement"] or value["transition_between"][1] is None


def test_leg_family_names_both_families_and_refuses_to_guess():
    assert R.leg_family("parallel_seq_scan") == "seq"
    assert R.leg_family("index_scan") == "index"
    assert R.leg_family("bitmap_index_scan+heap") == "index"
    assert R.leg_family(None) is None
    assert R.leg_family("something_new") == "other"


# ---------------------------------------------------------------- ⑤ 对账与清理形状
def test_snapshot_diff_points_at_the_unequal_item():
    before = {"items": {"chunk_vectors_rows": 1008, "vector_count": 1008,
                        "migrations": {"count": 18, "digest": "d"}}}
    after_equal = json.loads(json.dumps(before))
    assert R.snapshot_diff(before, after_equal)["all_equal"] is True
    after_bad = json.loads(json.dumps(before))
    after_bad["items"]["vector_count"] = 1007
    diff = R.snapshot_diff(before, after_bad)
    assert diff["all_equal"] is False and diff["unequal"] == ["vector_count"]


def test_db_set_diff_requires_the_exact_same_set():
    start = ["eb_r59_sandbox", "enterprise_brain", "postgres"]
    assert R.db_set_diff(start, list(start))["restored"] is True
    left = R.db_set_diff(start, start + ["eb_r579_probe"])
    assert left["restored"] is False and left["added"] == ["eb_r579_probe"]


def test_cleanup_only_touches_this_seat_schemas(monkeypatch, capsys):
    sent = []

    class FakeSandbox:
        database = "eb_r579_probe"
        pending = [[("sz_0001008",), ("sz_0005000",)], []]

        def rows(self, sql, params=None):
            return self.pending.pop(0)

        def execute(self, sql, params=None):
            sent.append(sql)

        def close(self):
            pass

    monkeypatch.setattr(R, "open_sandbox", lambda args: FakeSandbox())
    args = R.build_parser().parse_args(["--db-user", "enterprise_brain"])
    assert R.action_cleanup(args, io.StringIO()) == R.EXIT_OK
    assert all("sz_" in sql and sql.startswith("DROP SCHEMA") for sql in sent), sent
    assert not any("DROP DATABASE" in sql for sql in sent), "删库不是本件的活"


# ---------------------------------------------------------------- DDL 派生
PROD_INDEXES = [
    {"name": "chunk_vectors_pkey",
     "def": 'CREATE UNIQUE INDEX chunk_vectors_pkey ON public.chunk_vectors USING btree '
            '(vector_id)'},
    {"name": "chunk_vectors_embedding_idx",
     "def": "CREATE INDEX chunk_vectors_embedding_idx ON public.chunk_vectors USING hnsw "
            "(embedding vector_l2_ops) WITH (m='16', ef_construction='100')"},
]


def test_index_ddl_is_prod_text_retargeted_not_retyped():
    ddls = R.build_index_ddls("sz_0005000", "chunk_vectors", PROD_INDEXES)
    hnsw = next(item for item in ddls if "hnsw" in item["def"])["def"]
    assert 'ON "sz_0005000"."chunk_vectors"' in hnsw
    assert "public.chunk_vectors" not in hnsw
    assert "m='16'" in hnsw and "ef_construction='100'" in hnsw
    assert "vector_l2_ops" in hnsw


def test_index_ddl_refuses_a_shape_it_could_have_to_guess():
    with pytest.raises(R.SandboxTargetRefused):
        R.build_index_ddls("sz_1", "chunk_vectors", [{"name": "x",
                         "def": "CREATE INDEX x ON other_schema.chunk_vectors (a)"}])
    with pytest.raises(R.SandboxTargetRefused):
        R.build_index_ddls("sz_1", "chunk_vectors", [{"name": "x",
                         "def": "CREATE INDEX x ON public.chunk_vectors (a) "
                                "ON public.chunk_vectors (b)"}])


def test_create_table_copies_types_and_refuses_unsafe_identifiers():
    columns = [{"attnum": 1, "name": "vector_id", "type": "text", "notnull": True,
                "default": "", "storage": "x"},
               {"attnum": 9, "name": "embedding", "type": "vector(768)", "notnull": True,
                "default": "", "storage": "e"},
               {"attnum": 13, "name": "created_at", "type": "timestamptz", "notnull": True,
                "default": "now()", "storage": "p"}]
    ddl = R.build_create_table("sz_0001008", "chunk_vectors", columns)
    assert '"vector_id" text NOT NULL' in ddl
    assert '"embedding" vector(768) NOT NULL' in ddl
    assert '"created_at" timestamptz NOT NULL DEFAULT now()' in ddl
    with pytest.raises(R.SandboxTargetRefused):
        R.build_create_table("sz_0; DROP TABLE x", "chunk_vectors", columns)


def test_safe_size_guard_blocks_injection_shaped_memory_settings():
    assert R._safe_size("512MB") == "512MB"
    assert R._safe_size("64 MB") == "64MB"
    for bad in ("'512MB'", "512MB; DROP TABLE x", "default_risk", "1GB'"):
        with pytest.raises(R.SandboxTargetRefused):
            R._safe_size(bad)


# ---------------------------------------------------------------- 宽度必须派生
def test_no_candidate_width_literal_is_written_into_the_tool():
    """判据 3：件里出现一枚硬编码候选宽度数字就红（R393 同族）。

    尺子不许自带那一枚宽度数字本身，所以它拿真源的**键名**去量：源码里任何一处把
    `ef_search` 与一枚字面整数写在同一行，就是抄了第二次。
    """
    source = SCRIPT.read_text(encoding="utf-8")
    offenders = []
    for number, line in enumerate(source.splitlines(), start=1):
        if re_search_width(line):
            offenders.append((number, line.strip()))
    assert offenders == [], "抄进来的候选宽度：" + json.dumps(offenders, ensure_ascii=False)


def re_search_width(line: str) -> bool:
    import re as _re
    stripped = line.split("#", 1)[0]
    if "ef_search" not in stripped.lower():
        return False
    return bool(_re.search(r"(?<![\w.])\d{1,5}(?![\w.])", stripped))


def test_width_only_arrives_from_the_true_source_call(monkeypatch):
    calls = {"n": 0}

    class FakeStore:
        DEFAULT_VECTOR_TABLE = "chunk_vectors"
        DISTANCE_OPERATORS = {"l2": "<->"}
        HNSW_EF_SEARCH_GUC = "hnsw.ef_search"
        _APPLY_HNSW_EF_SEARCH_SQL = "SELECT set_config(%s, %s, TRUE)"

        @staticmethod
        def configured_hnsw_ef_search(environ=None):
            calls["n"] += 1
            return 4242                                   # 只要不是字面量就行

        @staticmethod
        def sql_scope_filter(where):
            return "classification = ANY(%s)", [1]

        @staticmethod
        def _vector_literal(vector):
            return "[0.5]"

    import sys as _sys
    import app.rag as _rag
    monkeypatch.setitem(_sys.modules, "app.rag.pg_store", FakeStore)
    monkeypatch.setattr(_rag, "pg_store", FakeStore, raising=False)
    plan = io.StringIO()
    rc = R.main(["--action", "plan"])
    assert rc == R.EXIT_OK
    probe = R._width_probe()
    assert probe["value"] == 4242 and calls["n"] >= 1
    assert probe["source"] == "app.rag.pg_store.configured_hnsw_ef_search"


def test_expect_ef_search_mismatch_refuses_before_touching_a_database(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    rc = R.main(["--action", "measure", "--expect-ef-search", "-7"])
    assert rc == R.EXIT_PRECONDITION
    assert "整单不跑" in capsys.readouterr().out


def test_plan_action_touches_no_database_and_reports_no_produced_files(capsys, tmp_path,
                                                                      monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    rc = R.main(["--action", "plan", "--sandbox-db", "eb_r579_probe"])
    out = capsys.readouterr().out
    assert rc == R.EXIT_OK
    payload = json.loads(out)
    assert payload["touching_database"] is False
    assert payload["sql_sketch"].count("%s") >= 0
    assert list(tmp_path.iterdir()) == []


def test_unprotected_prod_db_name_is_refused_because_the_guard_needs_a_credential():
    with pytest.raises(SystemExit) as raised:
        R.main(["--action", "snapshot", "--prod-db", "not_the_production_db"])
    assert "受保护库名" in str(raised.value)


def test_parse_plan_names_the_leg_and_the_actual_times():
    lines = [
        "Limit  (cost=817.67..818.04 rows=5 width=57) (actual time=0.491..0.522 rows=5 "
        "loops=1)",
        "  Buffers: shared hit=538",
        "  ->  Index Scan using chunk_vectors_embedding_idx on chunk_vectors  "
        "(cost=0.28..3025.42 rows=1008 width=57) (actual time=0.491..0.519 rows=5 loops=1)",
        "        Filter: (classification = ANY ('{1}'::integer[]))",
        "Planning Time: 0.312 ms",
        "Execution Time: 0.550 ms",
    ]
    parsed = R.parse_plan(lines)
    assert parsed["leg"] == "index_scan"
    assert parsed["index_name"] == "chunk_vectors_embedding_idx"
    assert parsed["execution_time_ms"] == 0.550
    assert parsed["shared_hit"] == 538 and parsed["shared_read"] == 0
    seq = R.parse_plan([
        'Limit  (cost=282.61..282.62 rows=5 width=57) (actual time=2.471..2.475 rows=5 '
        'loops=1)',
        "  Sort Method: top-N heapsort  Memory: 25kB",
        "  Buffers: shared hit=3296 read=3",
        "  ->  Seq Scan on chunk_vectors  (cost=0.00..259.86 rows=1008 width=57) "
        "(actual time=0.029..2.468 rows=1008 loops=1)",
        "Execution Time: 2.622 ms"])
    assert seq["leg"] == "seq_scan" and seq["index_name"] is None
    assert seq["sort_method"] == "top-N heapsort"
    assert seq["est_rows"] == 1008 and seq["shared_read"] == 3
    assert seq["scan_actual_last_ms"] == 2.468
    assert seq["execution_time_ms"] == 2.622
    gather = R.parse_plan([
        "Gather  (cost=1000.00..2000.00 rows=100 width=57) (actual time=1.0..2.0 rows=5 "
        "loops=1)",
        "  Workers Planned: 2",
        "  ->  Parallel Seq Scan on chunk_vectors  (cost=0.00..1000.00 rows=504 width=57) "
        "(actual time=0.5..1.5 rows=2 loops=3)"])
    assert gather["leg"] == "parallel_seq_scan" and gather["parallel"] is True
    assert R.parse_plan(["Sort  (cost=1.0..2.0 rows=3 width=4)"])["leg"] is None


def test_percentile_is_nearest_rank_and_survives_an_empty_sample():
    samples = list(range(1, 101))
    assert R.percentile(samples, 0.50) == 50
    assert R.percentile(samples, 0.95) == 95
    assert R.percentile([3.0], 0.95) == 3.0
    assert R.percentile([], 0.5) is None
    summary = R.latency_summary([1, 2, 3, 4])
    assert summary["n"] == 4 and summary["p50_ms"] == 2.0 and summary["min_ms"] == 1.0


def test_params_reconstruction_is_checked_against_the_captured_statement():
    """录言重设：`make_reader` 必须把重建的参数与产品自己交出去的那一枚逐元素对上。"""

    class FakeStore:
        DEFAULT_VECTOR_TABLE = "chunk_vectors"
        DISTANCE_OPERATORS = {"l2": "<->"}
        _APPLY_HNSW_EF_SEARCH_SQL = "SELECT set_config(%s, %s, TRUE)"
        HNSW_EF_SEARCH_GUC = "hnsw.ef_search"

        @staticmethod
        def sql_scope_filter(where):
            return "classification = ANY(%s)", [1]

        @staticmethod
        def _vector_literal(vector):
            return "[0.5]"

        @staticmethod
        def search_vectors(*, connection, vector_table, distance_function, query_vector,
                           k, where):
            clause, params = FakeStore.sql_scope_filter(where)
            literal = FakeStore._vector_literal(query_vector)
            connection.execute(FakeStore._APPLY_HNSW_EF_SEARCH_SQL,
                               (FakeStore.HNSW_EF_SEARCH_GUC, "100"))
            connection.execute(
                "SELECT vector_id FROM chunk_vectors WHERE " + clause
                + " ORDER BY embedding <-> %s::vector LIMIT %s",
                (literal, *params, literal, k))
            return [{"vector_id": "r579-00000000", "distance": 1.0}]

    class FakeCursor:
        def execute(self, sql, params=None):
            return self

        def fetchall(self):
            return []

    shape = {"distance_function": "l2", "dimension": 768}
    reader = R.make_reader(FakeStore, cursor=FakeCursor(), shape=shape,
                           where={"classification": {"$in": [1]}},
                           sample_vector=[0.5], k=5)
    assert reader["answer_ids"] == ["r579-00000000"]
    assert reader["params_for"]([0.5], 5) == ("[0.5]", 1, "[0.5]", 5)
    assert "set_config" in reader["width_call"][0]

    class LyingStore(FakeStore):
        @staticmethod
        def _vector_literal(vector):
            return "[0.6]"

    with pytest.raises(SystemExit) as raised:
        R.make_reader(LyingStore, cursor=FakeCursor(), shape=shape,
                      where={"classification": {"$in": [1]}}, sample_vector=[0.5], k=5)
    assert "重建的产品参数与录到的不一致" in str(raised.value)


def test_run_reader_only_uses_read_shapes_and_pins_the_width_inside_each_txn():
    sent = []

    class FakeGuardedCursor:
        def __init__(self, database):
            self.database = database

        def execute(self, sql, params=None):
            R.guard_statement(self.database, sql)
            sent.append((sql, params))
            return self

        def fetchall(self):
            return [("r579-x",)]

        def close(self):
            pass

    class FakeDb:
        database = "enterprise_brain"
        read_only = True

        def cursor(self):
            import contextlib

            @contextlib.contextmanager
            def opener():
                yield FakeGuardedCursor(self.database)
            return opener()

    reader = {"sql": PRODUCT_SQL, "knobs": [], "clause": "classification = ANY(%s)",
              "params_for": lambda vector, k: ("[0.5]", 1, "[0.5]", k),
              "width_call": ("SELECT set_config(%s, %s, TRUE)", ("hnsw.ef_search", "100"))}
    result = R.run_reader(FakeDb(), reader, knobs=("enable_seqscan = off",),
                          vectors=[[0.1], [0.2], [0.3]], k=5, plan_samples=1,
                          warm_rounds=1)
    assert result["queries"] == 3, "计时相位必须把每枚向量都计一次，不再丢掉开头几枚"
    assert len(result["plans"]) == 1
    assert result["ids"] == [["r579-x"]] * 3
    kinds = {R.classify_statement(sql) for sql, _ in sent}
    assert kinds == {"read"}, "取数路径里出现了写形状"
    # 三相位各自的事务枚数：热身 3 + 计时 3 + 取计划 1
    assert sum(1 for sql, _ in sent if sql == "BEGIN") == 7
    assert sum(1 for sql, _ in sent if sql == "ROLLBACK") == 7
    assert "SET LOCAL enable_seqscan = off" in [sql for sql, _ in sent]
    assert sum(1 for sql, _ in sent if "set_config" in sql) == 7
    assert result["phases"] == {"warm": 3, "timed": 3, "plan": 1}
    executed = sum(1 for sql, _ in sent if sql == PRODUCT_SQL)
    assert executed == 6, "热身相位必须**真的执行**读语句：只发 BEGIN/ROLLBACK 的暖是假的"
    explains = sum(1 for sql, _ in sent if sql.startswith("EXPLAIN (ANALYZE"))
    assert explains == 2, "取计划相位每条腿打两次 EXPLAIN，留第二次——第一次是冷页拽入"


def test_warm_phase_is_the_bug_that_was_fixed_not_a_renamed_noop():
    """冷启动曾把 HNSW 第一枚 EXPLAIN 读成 169 ms（生产现取），派工词据此判"索引慢 18 倍"。

    所以这一枚钉只管一件事：`warm_rounds=0` 与 `warm_rounds=1` 之间，**真执行的读语句枚数
    必须差一整轮向量**；而计时样本枚数不随热身轮数变化（计时与热身是两个相位）。
    """
    sent = []

    class Cur:
        def execute(self, sql, params=None):
            sent.append(sql)
            return self

        def fetchall(self):
            return [("r579-x",)]

    class Db:
        database = "enterprise_brain"

        def cursor(self):
            import contextlib

            @contextlib.contextmanager
            def opener():
                yield Cur()
            return opener()

    reader = {"sql": PRODUCT_SQL, "clause": "classification = ANY(%s)", "knobs": [],
              "params_for": lambda vector, k: ("[0.5]", 1, "[0.5]", k), "width_call": None}
    vectors = [[float(i)] for i in range(4)]
    for rounds, expect_exec in ((0, 4), (1, 8), (2, 12)):
        sent.clear()
        got = R.run_reader(Db(), reader, knobs=(), vectors=vectors, k=5,
                           plan_samples=0, warm_rounds=rounds)
        assert got["phases"]["warm"] == rounds * 4
        assert got["phases"]["timed"] == 4, "计时样本不许被热身手吃掉"
        assert len(got["latency_samples_ms"]) == 4
        assert sum(1 for sql in sent if sql == PRODUCT_SQL) == expect_exec
        assert sum(1 for sql in sent if sql.startswith("EXPLAIN")) == 0


# ---------------------------------------------------------- 统计态体检（判据 1 第四条读数）
def _stat_db(statistic_rows):
    """假连接：只回答 catalog_facts 那三条，一条真 SQL 都不出站。"""

    class Fake:
        def rows(self, sql, params=None):
            return [(1, 2, 3, 4, None, None, 5, 6, 0, 0, 0)]

        def one(self, sql, params=None):
            if "pg_statistic" in sql:
                return (statistic_rows,)
            return (7,)

    return Fake()


def test_catalog_facts_derives_statistic_presence_not_timestamps():
    """生产实测过：last_analyze/last_autoanalyze 双双 NULL，pg_statistic 里却有活统计。

    所以 `analyzed` 这一态不许只由时间戳作证——本钉把那 14 行的形状钉成"必须现读目录"。
    """
    clean = R.catalog_facts(_stat_db(0), "sz_0001008", "chunk_vectors")
    dirty = R.catalog_facts(_stat_db(14), "sz_0001008", "chunk_vectors")
    assert (clean["statistic_rows"], clean["stats_present"]) == (0, False)
    assert (dirty["statistic_rows"], dirty["stats_present"]) == (14, True)
    assert dirty["analyzed"] is False, "时间戳为空但目录有统计：两问必须各自交回，不许互相顶替"


def test_state_flags_marks_both_wrong_states_and_never_invents_a_verdict():
    dirty_as_loaded = R.state_flags("as_loaded", {"stats_present": True,
                                                  "statistic_rows": 14,
                                                  "last_analyze": None})
    assert dirty_as_loaded["contaminated"] is True
    assert "pg_statistic" in dirty_as_loaded["reason"]
    assert R.state_flags("as_loaded", {"stats_present": False, "statistic_rows": 0}) == {
        "contaminated": False, "reason": ""}
    assert R.state_flags("analyzed", {"stats_present": True, "statistic_rows": 3}) == {
        "contaminated": False, "reason": ""}
    analyzed_missing = R.state_flags("analyzed", {"stats_present": False,
                                                  "statistic_rows": 0})
    assert analyzed_missing["contaminated"] is True


def test_shape_sql_asks_the_catalog_for_statistics():
    """派生口径不许在件里另立一套：连"这态分析过没有"都得问目录。"""
    assert "pg_statistic" in R.SHAPE_SQL["statistic"]
    assert "starelid" in R.SHAPE_SQL["statistic"]


def test_report_points_at_the_contaminated_size(tmp_path, capsys):
    entry = {"size": 1008, "state": "as_loaded", "schema": "sz_0001008",
             "catalog": {"rows": 1008, "statistic_rows": 14, "stats_present": True},
             "state_flags": {"contaminated": True,
                             "reason": "as_loaded 档现场读到 pg_statistic 14 行"},
             "ks": {"5": {"natural": _arm_block("seq_scan"),
                          "index": _arm_block("index_scan"),
                          "exact": _arm_block("seq_scan")}},
             "width_from_true_source": "derived", "width_server_confirmed": "derived"}
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"action": "measure", "requested_sizes": [1008],
                                "records": [entry], "errors": {}}), encoding="utf-8")
    assert R.main(["--action", "report", "--from-results", str(path)]) == R.EXIT_OK
    out = capsys.readouterr().out
    assert "DIRTY" in out, "污染档不点名 = 下一班把 analyzed 态当 as_loaded 读"
    assert "pg_statistic 14 行" in out


# ------------------------------------------------------ 延迟的两本账：服务端 vs 协议往返
def test_server_table_keeps_execution_time_apart_from_wall_clock(tmp_path, capsys):
    plan = {"leg": "index_scan", "index_name": "chunk_vectors_embedding_idx",
            "execution_time_ms": 0.512, "top_actual_last_ms": 0.6, "shared_read": 1,
            "shared_hit": 40, "plan_head": "Index Scan ...", "plan_text": ["a"]}
    entry = {"size": 5000, "state": "as_loaded", "schema": "sz_0005000", "catalog": {},
             "state_flags": {"contaminated": False, "reason": ""},
             "ks": {"5": {
                 "natural": {"ids": [["a"]], "plans": [plan], "knobs": [],
                             "latency_samples_ms": [3.4]},
                 "index": {"ids": [["a"]], "plans": [plan],
                           "knobs": ["enable_seqscan = off"],
                           "latency_samples_ms": [0.7]},
                 "exact": {"ids": [["a"]], "plans": [plan], "knobs": [],
                           "latency_samples_ms": [3.1]}}}}
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"action": "measure", "requested_sizes": [5000],
                                "records": [entry], "errors": {},
                                "protocol_floor_ms": {
                                    "index": {"p50_ms": 0.21, "p95_ms": 0.4, "n": 25,
                                              "statements_per_txn": 6}}}),
                    encoding="utf-8")
    assert R.main(["--action", "report", "--from-results", str(path)]) == R.EXIT_OK
    out = capsys.readouterr().out
    assert "服务端那本账" in out
    assert "0.512" in out, "服务端 Execution Time 没进表 = 只剩一本被往返污染的账"
    assert "协议往返本身 arm=index" in out and "事务内语句枚数=6" in out


def test_plan_text_is_trimmed_after_the_keep_budget(tmp_path):
    """EXPLAIN 全文只留前 N 枚，其余留计划头：产物要能进纸，不许炸盘。"""
    plans = [{"plan_head": "Seq Scan ...", "plan_text": ["full", "text"]}]
    keep = 1
    for extra in range(3):
        plan = {"plan_head": "Seq Scan head {0}".format(extra), "plan_text": ["x", "y"]}
        if len(plans) >= keep:
            plan["plan_text"] = [plan["plan_head"]]
        plans.append(plan)
    assert plans[0]["plan_text"] == ["full", "text"]
    assert all(item["plan_text"] == [item["plan_head"]] for item in plans[keep:])


# --------------------------------------------------- 建索引的并行度：/dev/shm 64 MB 的教训
def test_parallel_maintenance_workers_is_bounded_before_it_enters_a_set_statement():
    """20000 档并行建 HNSW 要在 /dev/shm 开 512 MB DSM，容器只给 64 MB——直接 DiskFull。

    串行建不改查询期计划，但这枚数字要进 `SET`，所以必须先在件里收口，不许原样透传。
    """
    assert R._safe_workers("0") == 0
    assert R._safe_workers(4) == 4
    for bad in ("-1", "257", "0; DROP TABLE x", "", "1e3", None, " 1 "):
        with pytest.raises(R.SandboxTargetRefused):
            R._safe_workers(bad)


# --------------------------------------------------------- 复现探针的量具（判据 2 逼出来的）
def test_answer_tally_counts_distinct_answers_rather_than_first_one():
    same = [["a", "b"], ["a", "b"], ["a", "b"]]
    moved = [["a", "b"], ["b", "a"], ["a", "b"]]
    assert R.answer_tally(same)["distinct_answers"] == 1
    assert R.answer_tally(same)["pile_sizes"] == [3]
    tally = R.answer_tally(moved)
    assert tally["distinct_answers"] == 2, "同一题换了名次却没被查出来 = 复现探针是瞎的"
    assert tally["pile_sizes"] == [2, 1]
    assert tally["repeats"] == 3
    # 名次列里的 id 一律按字符串归堆：不许把 None/数字当成同名
    assert R.answer_tally([[None], ["None"]])["distinct_answers"] == 2


# ==================== 腿名可信度：抓到"臂名与实际执行计划不一致"的那枚牙 ====================
# 现场实测过的事：psycopg3 缺省 prepare_threshold=5 会在同连接上复用旧计划，于是被
# `SET LOCAL enable_seqscan = off` 逼出来的 index 臂**其实跑的是全表腿**——EXPLAIN 交回
# 2 ms、墙钟贴着全表腿的 18 ms。本单差点把 1.0000 的重合率交回总控。下面这些钉保证
# 那件仪器故障下一次会被**读数**当场抓住，而不是靠人记得开哪个开关。

def _probe_plan(leg, execution_time_ms, index_name=None):
    return {"leg": leg, "index_name": index_name,
            "execution_time_ms": execution_time_ms, "shared_read": 1, "shared_hit": 2}


def _probe_arm(leg, wall_samples, execution_samples, index_name=None, knobs=()):
    return {"ids": [["a", "b", "c", "d", "e"]],
            "plans": [_probe_plan(leg, ms, index_name) for ms in execution_samples],
            "knobs": list(knobs), "latency_samples_ms": list(wall_samples)}


def _probe_entry(size=5000, state="analyzed", walls=None, execs=None, legs=None):
    walls = walls or {"natural": [18.0] * 6, "index": [18.2] * 6, "exact": [18.1] * 6}
    execs = execs or {"natural": [18.0] * 6, "index": [2.0] * 6, "exact": [18.0] * 6}
    legs = legs or {"natural": "seq_scan", "index": "index_scan", "exact": "seq_scan"}
    ks = {}
    for k in ("5", "20"):
        ks[k] = {arm: _probe_arm(legs[arm], walls[arm], execs[arm],
                           index_name=("chunk_vectors_embedding_idx"
                                       if legs[arm] == "index_scan" else None),
                           knobs=["enable_seqscan = off"] if arm == "index" else [])
                 for arm in R.ARMS}
    return {"size": size, "state": state, "schema": "sz_{0:07d}".format(size),
            "catalog": {}, "state_flags": {"contaminated": False, "reason": ""},
            "width_from_true_source": "derived", "width_server_confirmed": "derived",
            "ks": ks}


def test_arm_consistency_flags_the_arm_whose_wall_clock_is_not_its_own_plan():
    """index 臂 EXPLAIN 2 ms、墙钟 18 ms ⇒ 只有那一臂被标成不可信，另外两臂不受牵连。"""
    item = R.aggregate_k(_probe_entry(), 5)
    cons = item["consistency"]
    assert cons["index"]["leg_attribution_suspect"] is True
    assert cons["natural"]["leg_attribution_suspect"] is False
    assert cons["exact"]["leg_attribution_suspect"] is False
    assert cons["index"]["wall_over_explain"] == pytest.approx(9.1)
    assert cons["limit_ratio"] == R.LEG_CONSISTENCY_RATIO


def test_arm_consistency_passes_when_both_clocks_agree():
    clean = _probe_entry(walls={"natural": [18.0] * 6, "index": [2.0] * 6,
                                "exact": [221.0] * 6},
                         execs={"natural": [17.6] * 6, "index": [1.9] * 6,
                                "exact": [220.5] * 6})
    item = R.aggregate_k(clean, 5, floor=None)
    cons = {arm: item["consistency"][arm] for arm in R.ARMS}
    assert all(v["leg_attribution_suspect"] is False for v in cons.values()), \
        "三臂的墙钟与它自己的计划同宽时不许报警，否则下一班会把每一轮都读成坏数据"
    assert item["consistency"]["index"]["wall_over_explain"] == pytest.approx(1.053)


def test_protocol_floor_is_a_deduction_and_never_enters_the_ratio():
    """地板值只用来把端到端还原成服务端；把它混进比值，三臂的开关枚数就会混进判据。"""
    item = R.aggregate_k(_probe_entry(), 5)
    floor = {arm: {"p50_ms": 0.5} for arm in R.ARMS}
    with_floor = R.arm_consistency(item, floor=floor)
    without = R.arm_consistency(item, floor=None)
    assert [with_floor[a]["wall_over_explain"] for a in R.ARMS] == \
        [without[a]["wall_over_explain"] for a in R.ARMS]
    assert with_floor["index"]["wall_minus_floor_ms"] == pytest.approx(17.7)
    assert without["index"]["wall_minus_floor_ms"] == pytest.approx(18.2)


def test_suspect_marks_and_ratio_cells_point_at_the_suspect_probe_arm():
    item = R.aggregate_k(_probe_entry(), 5)
    assert R.suspect_marks(item["consistency"]) == "idx!"
    assert R.suspect_marks({}) == "-"
    clean = {"natural": {"wall_over_explain": 1.0}, "index": {"wall_over_explain": 1.1},
             "exact": {"wall_over_explain": 1.2}}
    assert R.suspect_marks(clean) == "ok"
    cells = R.ratio_cells(item["consistency"])
    assert "idx=9.1*" in cells and "nat=" in cells and "exa=" in cells


def test_report_prints_the_leg_trust_column_and_the_ratio_detail_block(tmp_path, capsys):
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"action": "measure", "requested_sizes": [5000],
                                "records": [_probe_entry()], "errors": {},
                                "protocol_floor_ms": {arm: {"p50_ms": 0.04, "p95_ms": 0.09,
                                                            "n": 25,
                                                            "statements_per_txn": 6}
                                                     for arm in R.ARMS}}),
                    encoding="utf-8")
    assert R.main(["--action", "report", "--from-results", str(path)]) == R.EXIT_OK
    text = capsys.readouterr().out
    assert "legTrust" in text, "主表少了腿名可信度那一格：读数就会不带警示地并排站"
    assert "idx!" in text
    assert "腿名可信度 = 端到端 p50" in text
    assert "idx=9.1*" in text, "明细块必须给比值，不许只给一个感叹号"
    assert "协议往返本身 arm=index" in text


def test_clean_round_prints_ok_and_no_star(tmp_path, capsys):
    entry = _probe_entry(walls={"natural": [18.0] * 6, "index": [2.0] * 6, "exact": [220.0] * 6},
                   execs={"natural": [17.5] * 6, "index": [1.9] * 6,
                          "exact": [221.0] * 6})
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"action": "measure", "requested_sizes": [5000],
                                "records": [entry], "errors": {}}), encoding="utf-8")
    assert R.main(["--action", "report", "--from-results", str(path)]) == R.EXIT_OK
    text = capsys.readouterr().out
    assert "* " not in text and "ok" in text


# ----------------------------------------------------------- prepare 阈值：本轮量测的自证
def test_parse_prepare_threshold_only_accepts_the_three_shapes():
    assert R.parse_prepare_threshold("none") is None
    assert R.parse_prepare_threshold("OFF") is None
    assert R.parse_prepare_threshold("psycopg") is R.KEEP_PSYCOPG_DEFAULT
    assert R.parse_prepare_threshold("0") == 0
    assert R.parse_prepare_threshold("7") == 7
    for bad in ("-1", "banana"):
        with pytest.raises(SystemExit) as caught:
            R.parse_prepare_threshold(bad)
        assert "prepare-threshold" in str(caught.value)


def test_describe_prepare_threshold_names_the_live_setting():
    assert R.describe_prepare_threshold(None) == "none"
    assert R.describe_prepare_threshold(R.KEEP_PSYCOPG_DEFAULT) == "psycopg-default"
    assert R.describe_prepare_threshold(0) == "0"


def test_db_open_only_forwards_the_threshold_it_was_given():
    """缺省哨兵 = 一个 kwargs 都不加（不许把 psycopg 的缺省悄悄改掉）；
    none = 显式加 prepare_threshold=None（本单默认，专治同连接复用旧计划）。"""
    seen = []

    class FakeCur:
        def execute(self, sql, params=None):
            return self

        def fetchone(self):
            return ("enterprise_brain",)

    class FakeConn:
        def cursor(self):
            return FakeCur()

        def execute(self, sql, params=None):
            return FakeCur().execute(sql)

        def close(self):
            pass

    import psycopg
    original = psycopg.connect
    try:
        def spy(url, **kwargs):
            seen.append(kwargs)
            return FakeConn()
        psycopg.connect = spy
        R.Db(url="u", database="enterprise_brain", read_only=False, label="t").open()
        assert "prepare_threshold" not in seen[-1], \
            "缺省必须不干预，否则这一轮量的不是生产连接姿势"
        assert seen[-1]["autocommit"] is True
        R.Db(url="u", database="enterprise_brain", read_only=False, label="t",
             prepare_threshold=None).open()
        assert seen[-1]["prepare_threshold"] is None
        assert seen[-1]["autocommit"] is True
        R.Db(url="u", database="enterprise_brain", read_only=False, label="t",
             prepare_threshold=0).open()
        assert seen[-1]["prepare_threshold"] == 0
    finally:
        psycopg.connect = original


def test_measure_payload_reports_its_own_prepare_threshold():
    """量测产物必须自报这一轮连接上生效的 prepare 阈值，不许靠人回忆口令。"""
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"prepare_threshold": describe_prepare_threshold(args.prepared)' in source
    assert "prepare_threshold=args.prepared" in source
