"""R575 离线钉：真库恢复演练的判据必须**有牙**，而且必须在没有库的机器上也跑得动。

为什么这一枚文件必须存在（业主口径：PGVector 是生产向量库，Chroma 是退役中的遗留件）：
R575 的读数只在真机那一枚 ``enterprise-brain-postgres-1`` 上量得到，而全量回归门里没有库
——真机件在门里永远是 skip，不是 pass。于是「把 ``DROP`` 递到生产库上会怎样」「把向量列校验
摘掉会怎样」「归档被截断会怎样」这三件事，在门里只能由**本文件**长期拦住：真机演练今天绿，
不代表明天那枚件还有牙。

它钉什么（全部离线，一枚 ``_run`` 桩住所有 docker/psql/pg_dump/pg_restore）：

1. **只读闸门两侧**：写语句一律拒；``updated_at`` 这种带子串的列名不许被误伤（误伤一次，读腿
   就拼不出来，那道闸迟早被人整枚拆掉）。生产库上连"非只读批次"都发不出去，且拒之前一次
   docker 调用都没有。
2. **对账不是硬编码**：喂 7/6/0 这类假数它照样逐枚比、照样变红并点名；把向量校验一族摘掉，
   剩下的读数全等也必须红（判据④②的常驻版）；缺项即红，沉默不是通过。
3. **归档坏了要拒**：sha 不符、``pg_restore --list`` 读不动、落点表缺数据——都在建库之前拒。
4. **检索对账真的在比名次**：只在恢复/只在生产非 0 必红；名次挪动必须报数；候选宽度没钉住
   （会话现读回出厂档）当场作废整轮读数。
5. **幂等与残留**：同名恢复库已存在时拒，不建第二枚；``DROP``/``CREATE`` 只认那一枚名字。
   收尾那本库名账只算别人家的库——恢复库自己的去留按 ``--keep`` 判（这一支是真机反证⑤抓出来的
   假阳性：``--replace-drill-db`` 且不 ``--keep`` 的一轮，删掉自己那枚却被判「少了」，rc=5）。
6. **静态预算**：件里以写动词开头的语句字面量逐枚点名，全部只指向 ``eb_r575_drill``，
   ``TRUNCATE``/``UPDATE``/``DELETE``/``INSERT``/``COPY``/``VACUUM``/``ALTER``/``GRANT`` 零枚。

盲区（诚实写明）：假句柄只回答演练**真的发出去**的那些语句，它证的是判据的形状，不证
PostgreSQL 的恢复行为，也不证那 1008 枚向量真恢复回来了——后者只有
``scripts/r575_vector_restore_drill.py full`` 在真机上那一轮能答，读数在
``docs/testing/r575-vector-restore-drill-2026-10-03.md``。本文件绿不代表演练已过。
"""
from __future__ import annotations

import ast
import csv
import hashlib
import io
from pathlib import Path
import re
import subprocess

import pytest

import scripts.r575_vector_restore_drill as drill

CONTAINER = "enterprise-brain-postgres-1"
PROD_ROWS = "7"
VECTOR_IDS = ["a_0", "a_1", "a_2", "a_3"]
ARCHIVE = b"r575 fake pg_dump payload" * 64
ARCHIVE_SHA = hashlib.sha256(ARCHIVE).hexdigest()


def _record(fields) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerow(list(fields))
    return buffer.getvalue()


def _answer(sets) -> str:
    """Render per-statement row lists the way one psql ``--csv -t`` session would."""
    return "".join("".join(_record(row) for row in rows) + _record([drill.BOUNDARY])
                   for rows in sets)


class FakePg:
    """A docker-shaped stand-in that answers only the statements this drill really sends.

    ``damage`` 是往里注入谎的地方：``drop-row`` 让恢复库少一行；``zero-vectors`` 让向量列
    在行数不变的情况下整列归零；``topk-drops`` 让恢复库少一枚命中；``topk-swaps`` 命中相同
    次序不同；``width-ignored`` 让候选宽度停在出厂档；``toc-drops-mirror`` 让归档目录里没有
    ``chunk_vectors`` 的数据项；``drop-fails`` 让那句 DROP DATABASE 不生效。
    """

    def __init__(self, *, databases=None, damage=None):
        self.databases = list(databases if databases is not None
                              else [drill.MAINT_DB, drill.SOURCE_DB, drill.DRILL_DB])
        self.damage = set(damage or ())
        self.calls: list = []

    def __call__(self, argv, *, input_text=None, timeout=900):
        argv = list(argv)
        self.calls.append({"argv": argv, "stdin": input_text})
        if argv[:2] == ["docker", "cp"]:
            return self._cp(argv)
        tool = self._tool(argv)
        if tool == "psql":
            return self._psql(argv, input_text or "")
        if tool == "pg_dump":
            return self._ok("")
        if tool == "pg_restore":
            if "--list" in argv:
                if "archive-unreadable" in self.damage or "toc-drops-mirror" in self.damage:
                    if "archive-unreadable" in self.damage:
                        return self._fail("pg_restore: error: could not read from input file: "
                                          "end of file")
                    return self._ok(self._toc())
                return self._ok(self._toc())
            return self._ok("")
        if tool == "sha256sum":
            return self._ok(ARCHIVE_SHA + "  " + argv[-1] + "\n")
        if tool == "stat":
            return self._ok(f"{len(ARCHIVE)}\n")
        if tool in ("mkdir", "rm", "true"):
            return self._ok("")
        if tool == "inspect":
            return self._ok("true\n" if "Running" in argv[-1] else "pgvector/pgvector:pg16\n")
        return self._ok("")

    def _cp(self, argv):
        source, target = argv[2], argv[3]
        if source.startswith(CONTAINER + ":"):
            Path(target).write_bytes(ARCHIVE)
        return self._ok("")

    @staticmethod
    def _tool(argv):
        if argv[:2] != ["docker", "exec"]:
            return "unknown"
        tail = argv[4:] if argv[2] == "-i" else argv[3:]
        if tail and tail[0] == "sh":
            return "rm" if "rm -rf" in tail[-1] else "unknown"
        return tail[0] if tail else "unknown"

    @staticmethod
    def _ok(stdout):
        return subprocess.CompletedProcess(["fake"], 0, stdout, "")

    @staticmethod
    def _fail(stderr):
        return subprocess.CompletedProcess(["fake"], 1, "", stderr)

    def _database(self, argv):
        return argv[argv.index("-d") + 1]

    def _psql(self, argv, stdin):
        database = self._database(argv)
        if database not in self.databases:
            return self._fail('psql: error: FATAL:  database "' + database
                              + '" does not exist')
        restored = database == drill.DRILL_DB
        width = "100"
        sets = []
        for statement in self._statements(stdin):
            pinned = re.search(r"set_config\('hnsw\.ef_search', '(\d+)'", statement)
            if pinned:
                width = "40" if "width-ignored" in self.damage else pinned.group(1)
            sets.append(self._one(restored, statement, width))
        return self._ok(_answer(sets))

    @staticmethod
    def _statements(stdin) -> list:
        keep = []
        for line in stdin.splitlines():
            text = line.strip().rstrip(";").strip()
            if (not text or text in ("BEGIN", "COMMIT")
                    or text == f"SELECT '{drill.BOUNDARY}'"
                    or text.startswith(drill.READ_ONLY_PIN)):
                continue
            keep.append(text)
        return keep

    def _one(self, restored, sql, width):
        if sql.startswith("DROP DATABASE"):
            name = sql.split('"')[1]
            if "drop-fails" not in self.damage and name in self.databases:
                self.databases.remove(name)
            return []
        if sql.startswith("CREATE DATABASE"):
            name = sql.split('"')[1]
            if name not in self.databases:
                self.databases.append(name)
            return []
        if sql.startswith("ANALYZE") or sql.startswith("SELECT pg_sleep"):
            return []
        for pattern, builder in self._patterns(restored, width):
            if re.search(pattern, sql):
                return builder()
        raise AssertionError("FakePg 没被教会回答这条语句：" + sql[:140])

    def _patterns(self, restored, width):
        rows = str(max(int(PROD_ROWS) - 1, 0) if restored and "drop-row" in self.damage
                   else PROD_ROWS)
        vectors = "0" if restored and "zero-vectors" in self.damage else PROD_ROWS
        zeros = PROD_ROWS if restored and "zero-vectors" in self.damage else "0"
        return [
            (r"^SELECT datname FROM pg_database", lambda: [(name,) for name in self.databases]),
            (r"extversion", lambda: [("0.8.6",)]),
            (r"pg_control_system", lambda: [("16.15/7685285828163473446",)]),
            (r"pg_settings", lambda: [("1/1000/40",)]),
            (r"^SELECT NULL::vector", lambda: [("t",)]),
            (r"count\(embedding\) FROM chunk_vectors", lambda: [(vectors,)]),
            (r"array_fill", lambda: [(zeros,)]),
            (r"count\(\*\) FROM chunk_vectors$", lambda: [(rows,)]),
            (r"format_type\(atttypid", lambda: [("vector(768)",)]),
            (r"vector_dims\(embedding\)", lambda: [("768..768",)]),
            (r"count\(\*\) FROM vector_scope", lambda: [("1",)]),
            (r"^SELECT coalesce\(string_agg\(format",
             lambda: [("1|nomic-embed-text|768|l2|16|100|x|y",)]),
            (r"count\(\*\) FROM documents", lambda: [("2",)]),
            (r"count\(\*\) FROM chunks", lambda: [(PROD_ROWS,)]),
            (r"FROM schema_migrations", lambda: [("0001,0002,0018",)]),
            (r"md5\(string_agg", lambda: [("deadbeef",)]),
            (r"FROM pg_indexes", lambda: [("chunk_vectors_pkey :: CREATE ...",)]),
            (r"FROM pg_db_role_setting",
             lambda: [("NONE" if restored else "db=enterprise_brain conf={x}",)]),
            (r"current_setting\('app\.embedding",
             lambda: [("MISSING/MISSING" if restored else "768/nomic-embed-text",)]),
            (r"FROM pg_roles", lambda: [("enterprise_brain:super",)]),
            (r"ORDER BY md5\(vector_id\)", lambda: [(vid, "[0.5,0.5]") for vid in VECTOR_IDS]),
            (r"^SELECT set_config", lambda: [(width,)]),
            (r"current_setting\('hnsw\.ef_search'\)", lambda: [(width,)]),
            (r"^SELECT embedding_model", lambda: [("nomic-embed-text", "768", "l2")]),
            (r"ORDER BY embedding", lambda: self._topk(restored)),
        ]

    def _topk(self, restored):
        ids = list(VECTOR_IDS)
        if restored and "topk-drops" in self.damage:
            ids = ids[:-1]
        if restored and "topk-swaps" in self.damage:
            ids[1], ids[2] = ids[2], ids[1]
        return [(vid, "content", "f.txt", "1", "1", "", str(0.5 + index / 10))
                for index, vid in enumerate(ids)]

    def _toc(self):
        # 逐字照 09-26 那枚真 dump 的 ``pg_restore --list`` 目录行格式（无分号开头）：
        # ``missing_landing_tables`` 的正言就钉在这个形状上，抄错一枚分号它就是假绿。
        lines = ["3200; 0 16388 TABLE public chunks enterprise_brain",
                 "3400; 0 16388 TABLE DATA public chunks enterprise_brain"]
        if "toc-drops-mirror" not in self.damage:
            lines += ["3210; 0 16420 TABLE public chunk_vectors enterprise_brain",
                      "3410; 0 16420 TABLE DATA public chunk_vectors enterprise_brain"]
        else:
            lines += ["3210; 0 16420 TABLE public chunk_vectors enterprise_brain"]
        return "\n".join(lines)


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """Point every docker-shaped hole in the drill at a fake; artifacts 留在 tmp_path（仓外）。"""
    fake = FakePg()
    monkeypatch.setattr(drill, "_run", fake)
    drill.LEDGER.clear()
    return fake, tmp_path


def _fingerprint(database=drill.SOURCE_DB):
    return drill.collect_fingerprint(CONTAINER, database)


def test_the_read_only_gate_refuses_writing_statements():
    for statement in ("DELETE FROM chunk_vectors WHERE vector_id = 'x'",
                      "UPDATE chunk_vectors SET department = 'd'",
                      "TRUNCATE chunk_vectors",
                      "DROP TABLE chunk_vectors",
                      "INSERT INTO vector_scope VALUES (1)",
                      "COPY chunk_vectors FROM stdin",
                      "VACUUM ANALYZE chunk_vectors",
                      "ALTER TABLE chunk_vectors ADD COLUMN oops text",
                      "CREATE INDEX bad ON chunk_vectors (filename)",
                      "GRANT ALL ON chunk_vectors TO public",
                      "/* 藏在注释里也躲不过 */ DELETE FROM chunk_vectors",
                      "DROP DATABASE eb_r575_drill",
                      "WITH gone AS (DELETE FROM chunk_vectors RETURNING *) SELECT 1"):
        with pytest.raises(drill.Refuse):
            drill.guard_statement(statement)


def test_the_read_only_gate_does_not_bite_its_own_column_names():
    # 上一枚钉反着来一次：误伤一次，读腿就拼不出来，这道闸迟早被人整枚拆掉。
    for statement in ("SELECT updated_at FROM chunk_vectors",
                      "SELECT created_at, embedding FROM chunk_vectors",
                      "SELECT set_config('hnsw.ef_search', '100', TRUE)",
                      "SELECT count(*) FROM vector_scope",
                      "SELECT datname FROM pg_database ORDER BY datname",
                      "SELECT current_setting('hnsw.ef_search')",
                      "SELECT coalesce(extversion, 'MISSING') FROM pg_extension"):
        drill.guard_statement(statement)


def test_the_drill_cannot_issue_a_writing_batch_to_the_production_database(wired):
    fake, _ = wired
    with pytest.raises(drill.Refuse):
        drill.run_psql(CONTAINER, drill.SOURCE_DB, ["SELECT 1"], readonly=False)
    assert fake.calls == [], "拒收必须发生在任何 docker 调用之前"


def test_only_the_drill_database_may_be_created_or_dropped():
    drill.assert_droppable(drill.DRILL_DB)
    for forbidden in (drill.SOURCE_DB, "postgres", "template1", "eb_r59_sandbox", ""):
        with pytest.raises(drill.Refuse):
            drill.assert_droppable(forbidden)
    drill.assert_creatable(drill.DRILL_DB, [drill.SOURCE_DB])
    with pytest.raises(drill.Refuse):
        drill.assert_creatable("some_other_db", [drill.SOURCE_DB])
    with pytest.raises(drill.Refuse, match=drill.DRILL_DB):
        drill.assert_creatable(drill.DRILL_DB, [drill.SOURCE_DB, drill.DRILL_DB])


def test_the_fingerprint_reads_live_numbers_not_constants(wired):
    wired
    found = _fingerprint()
    assert found["chunk_vectors_rows"] == PROD_ROWS
    assert found["embedding_dims"] == "768..768"
    assert found["zero_vector_rows"] == "0"
    assert found["schema_migrations"] == "0001,0002,0018"
    assert set(found) >= set(drill.RECON_ITEMS) | set(drill.EXTRA_ITEMS)


def test_the_reconcile_is_data_driven_and_names_the_offending_item(wired):
    wired
    prod, restored = _fingerprint(drill.SOURCE_DB), _fingerprint(drill.DRILL_DB)
    assert drill.compare_fingerprints(prod, restored)["differences"] == []
    lost = drill.compare_fingerprints(prod, dict(restored, chunk_vectors_rows="6"))
    assert lost["differences"][0].startswith("chunk_vectors_rows")
    # 行数照样相等、只有向量坏了：这一族必须由向量列校验自己抓到，而不是靠行数列出来。
    zeroed = drill.compare_fingerprints(prod, dict(restored, zero_vector_rows="7",
                                                   embedding_count="0"))
    named = " ".join(item.split(":")[0] for item in zeroed["differences"])
    assert "zero_vector_rows" in named and "embedding_count" in named
    shifted = drill.compare_fingerprints(prod, dict(restored, vector_content_md5="other"))
    assert shifted["differences"][0].startswith("vector_content_md5")


def test_taking_the_vector_check_out_turns_the_reconcile_red(wired):
    """判据④②的常驻版：摘掉向量列校验，剩下的读数全等也不许报绿。"""
    wired
    prod, restored = _fingerprint(drill.SOURCE_DB), _fingerprint(drill.DRILL_DB)
    assert drill.compare_fingerprints(prod, restored)["differences"] == []
    with pytest.raises(drill.Mismatch, match="对账缺项"):
        drill.compare_fingerprints(prod, restored, skip_vector_check=True)


def test_a_missing_item_is_a_red_not_a_silence(wired):
    wired
    prod = _fingerprint(drill.SOURCE_DB)
    partial = {key: value for key, value in prod.items() if key != "vector_content_md5"}
    with pytest.raises(drill.Mismatch, match="vector_content_md5"):
        drill.compare_fingerprints(prod, partial)


def test_a_truncated_archive_refuses_before_it_can_build_a_database(tmp_path, monkeypatch):
    fake = FakePg()
    monkeypatch.setattr(drill, "_run", fake)
    archive = tmp_path / "eb_r575_drill-half.dump"
    archive.write_bytes(ARCHIVE[: len(ARCHIVE) // 2])
    whole = tmp_path / "eb_r575_drill.dump"
    whole.write_bytes(ARCHIVE)
    with pytest.raises(drill.Refuse, match="sha"):
        drill.restore(CONTAINER, archive=archive, drill=drill.DRILL_DB,
                      expect_sha256=ARCHIVE_SHA)
    assert fake.calls == [], "sha 这道闸必须在下 docker 之前"
    broken = FakePg(damage={"archive-unreadable"})
    monkeypatch.setattr(drill, "_run", broken)
    with pytest.raises(drill.Refuse):
        drill.restore(CONTAINER, archive=archive, drill=drill.DRILL_DB)
    assert not [call for call in broken.calls
                if call["stdin"] and "CREATE DATABASE" in call["stdin"]]
    assert drill.DRILL_DB in broken.databases  # 生产库与既有清单都没被碰


def test_an_archive_that_lost_the_mirror_is_not_a_pass(tmp_path, monkeypatch):
    # 正控先跑一遍：同一枚假目录补齐镜像那一行，落点判据必须放行。
    good = FakePg()
    monkeypatch.setattr(drill, "_run", good)
    assert drill.landing_gaps(good._toc().splitlines(), drill.VECTOR_LANDING_TABLES) == set()
    good_backup = tmp_path / "good"
    report = drill.backup(CONTAINER, source=drill.SOURCE_DB, artifact_dir=good_backup)
    assert report["bytes"] == len(ARCHIVE) and report["sha256"] == ARCHIVE_SHA
    assert (good_backup / Path(report["path"]).name).read_bytes() == ARCHIVE
    fake = FakePg(damage={"toc-drops-mirror"})
    monkeypatch.setattr(drill, "_run", fake)
    with pytest.raises(drill.Refuse, match="chunk_vectors"):
        drill.backup(CONTAINER, source=drill.SOURCE_DB, artifact_dir=tmp_path / "out")
    archive = tmp_path / "eb_r575_drill.dump"
    archive.write_bytes(ARCHIVE)
    with pytest.raises(drill.Refuse, match="chunk_vectors"):
        drill.restore(CONTAINER, archive=archive, drill=drill.DRILL_DB)
    assert drill.VECTOR_LANDING_TABLES == ("chunks", "chunk_vectors")


def test_a_nonexistent_source_database_is_named_in_the_refusal(monkeypatch):
    fake = FakePg(databases=[drill.MAINT_DB, drill.SOURCE_DB])
    monkeypatch.setattr(drill, "_run", fake)
    with pytest.raises(drill.Refuse, match="eb_no_such_db"):
        drill.container_preflight(CONTAINER, "eb_no_such_db")


def test_the_recall_reports_only_in_sets_and_rank_displacement(wired):
    fake, _ = wired
    reading = drill.recall(CONTAINER, source=drill.SOURCE_DB, drill=drill.DRILL_DB,
                           queries=len(VECTOR_IDS), top_k=4, exact_cross_check=False)
    one = reading["passes"][0]
    assert one["only_in_source"] == one["only_in_drill"] == one["max_rank_shift"] == 0
    assert one["ef_search_seen_in_session"] == [str(one["requested_ef_search"])]
    fake.damage = {"topk-drops"}
    with pytest.raises(drill.RecallRed):
        drill.recall(CONTAINER, source=drill.SOURCE_DB, drill=drill.DRILL_DB,
                     queries=len(VECTOR_IDS), top_k=4, exact_cross_check=False)
    fake.damage = {"topk-swaps"}
    swapped = drill.recall(CONTAINER, source=drill.SOURCE_DB, drill=drill.DRILL_DB,
                           queries=len(VECTOR_IDS), top_k=4, exact_cross_check=False)
    assert swapped["passes"][0]["only_in_source"] == swapped["passes"][0]["only_in_drill"] == 0
    assert swapped["passes"][0]["max_rank_shift"] == 1


def test_the_recall_refuses_when_the_pinned_width_did_not_take(wired):
    """R393 那一族：同一个 SQL 换了候选宽度就是换了问题，钉没钉上必须现读现证。"""
    fake, _ = wired
    fake.damage = {"width-ignored"}
    with pytest.raises(drill.Refuse, match="候选宽度"):
        drill.recall(CONTAINER, source=drill.SOURCE_DB, drill=drill.DRILL_DB,
                     queries=len(VECTOR_IDS), top_k=4, exact_cross_check=False)


def test_the_leg_sql_is_the_production_read_leg_not_a_copy(wired):
    from app.rag import pg_store

    statements = drill.leg_statements("l2", [0.5, 0.5], 3)
    assert "set_config" in statements[0]
    assert str(pg_store.configured_hnsw_ef_search()) in statements[0]
    assert ", ".join(pg_store._READ_COLUMNS) in statements[1]
    assert "ORDER BY embedding " + pg_store.DISTANCE_OPERATORS["l2"] in statements[1]
    assert "LIMIT 3" in statements[1]
    with pytest.raises(pg_store.VectorReadRejectedError):
        drill.leg_statements("not-an-operator", [0.5, 0.5], 3)
    with pytest.raises(drill.Refuse):
        drill.render_sql("SELECT %s", ())


def test_the_width_bounds_come_from_the_server(wired):
    wired
    assert drill.hnsw_width_bounds(CONTAINER, drill.SOURCE_DB) == {
        "min": 1, "max": 1000, "factory": 40}
    assert drill.max_dimension("768..768") == 768
    assert drill.max_dimension("EMPTY") is None
    with pytest.raises(drill.Refuse):
        drill.max_dimension("wide")


def test_artifacts_cannot_land_inside_a_git_worktree(tmp_path):
    nested = tmp_path / "repo" / "out"
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    nested.mkdir(parents=True)
    with pytest.raises(drill.Refuse, match="git 工作树"):
        drill.assert_outside_worktree(nested)
    assert drill.assert_outside_worktree(tmp_path / "plain") == tmp_path / "plain"


def test_restore_refuses_to_create_a_second_database_with_the_same_name(tmp_path, monkeypatch):
    fake = FakePg(databases=[drill.MAINT_DB, drill.SOURCE_DB])
    monkeypatch.setattr(drill, "_run", fake)
    archive = tmp_path / "eb_r575_drill.dump"
    archive.write_bytes(ARCHIVE)
    drill.restore(CONTAINER, archive=archive, drill=drill.DRILL_DB)
    assert fake.databases.count(drill.DRILL_DB) == 1
    with pytest.raises(drill.Refuse, match=drill.DRILL_DB):
        drill.restore(CONTAINER, archive=archive, drill=drill.DRILL_DB)
    assert fake.databases.count(drill.DRILL_DB) == 1
    drill.restore(CONTAINER, archive=archive, drill=drill.DRILL_DB, replace=True)
    assert fake.databases.count(drill.DRILL_DB) == 1
    assert drill.SOURCE_DB in fake.databases


def test_the_cleanup_reports_the_drop_it_actually_made(wired):
    fake, _ = wired
    report = drill.cleanup(CONTAINER, drill=drill.DRILL_DB)
    assert report["drill_dropped"] is True
    assert drill.DRILL_DB not in report["databases_after_cleanup"]
    fake.damage = {"drop-fails"}
    fake.databases.append(drill.DRILL_DB)
    lying = drill.cleanup(CONTAINER, drill=drill.DRILL_DB)
    assert lying["drill_dropped"] is False, "删不掉却说删掉了，就是这枚钉要拦的谎"


OTHERS = [drill.MAINT_DB, drill.SOURCE_DB, "eb_r59_sandbox"]


def test_the_residue_gate_does_not_charge_its_own_drill_database_to_others():
    """真机反证⑤抓到的假阳性：收尾删掉自己那枚同名库，不许算成「少了别人的库」。"""
    report = drill.check_residue(OTHERS + [drill.DRILL_DB], OTHERS,
                                 drill_db=drill.DRILL_DB, keep=False)
    assert report["missing"] == [] and report["unexpected_extra"] == []
    assert report["drill_present_before"] is True
    assert report["drill_present_after"] is False
    assert report["kept_by_request"] == []


def test_the_residue_gate_still_names_everyones_elses_database():
    """把恢复库摘出去之后，别人家的库少一枚、多一枚都要红，而且要具名。"""
    with pytest.raises(drill.Residue, match="eb_r59_sandbox"):
        drill.check_residue(OTHERS, [item for item in OTHERS if item != "eb_r59_sandbox"],
                            drill_db=drill.DRILL_DB, keep=False)
    with pytest.raises(drill.Residue, match="someone_elses_db"):
        drill.check_residue(OTHERS, OTHERS + ["someone_elses_db"],
                            drill_db=drill.DRILL_DB, keep=False)


def test_the_residue_gate_keeps_only_what_it_promised():
    """``--keep`` 说了留就得留着，说了不就得删干净；两头的谎都要红，账要随异常交出来。"""
    left = drill.check_residue(OTHERS, OTHERS + [drill.DRILL_DB],
                               drill_db=drill.DRILL_DB, keep=True)
    assert left["kept_by_request"] == [drill.DRILL_DB]
    replaced = drill.check_residue(OTHERS + [drill.DRILL_DB], OTHERS + [drill.DRILL_DB],
                                   drill_db=drill.DRILL_DB, keep=True)
    assert replaced["kept_by_request"] == [drill.DRILL_DB], "上一轮留下的那枚也是它留的"
    with pytest.raises(drill.Residue, match="--keep"):
        drill.check_residue(OTHERS, OTHERS, drill_db=drill.DRILL_DB, keep=True)
    with pytest.raises(drill.Residue, match=drill.DRILL_DB) as caught:
        drill.check_residue(OTHERS, OTHERS + [drill.DRILL_DB],
                            drill_db=drill.DRILL_DB, keep=False)
    assert caught.value.residue["kept_by_request"] == []
    assert caught.value.residue["drill_present_after"] is True


def test_the_ledger_keeps_production_apart_from_everything_else(wired):
    wired
    _fingerprint(drill.SOURCE_DB)
    _fingerprint(drill.DRILL_DB)
    drill.list_databases(CONTAINER)
    production = drill.ledger_for(drill.SOURCE_DB)
    assert production and all(text.startswith("SELECT") for text in production)
    assert not [item for item in drill.LEDGER if item["database"] == drill.SOURCE_DB
                and re.search(r"\b(DROP|TRUNCATE|UPDATE|DELETE|INSERT|ALTER|CREATE|COPY)\b",
                              item["statement"], re.I)]
    maintenance = [item["statement"] for item in drill.LEDGER
                   if item["database"] == drill.MAINT_DB]
    assert maintenance, "建库/删库/搬运也要留痕"


_WRITE_VERB = re.compile(r"^(DROP|CREATE|ALTER|TRUNCATE|UPDATE|DELETE|INSERT|COPY|VACUUM|"
                         r"GRANT|ANALYZE|REPLACE|REFRESH)\s")
_BANNED_VERBS = ("TRUNCATE", "UPDATE", "DELETE", "INSERT", "COPY", "VACUUM", "ALTER", "GRANT",
                 "REPLACE", "REFRESH")


def _issued_statements(path: Path) -> list:
    """String literals that start like a writing statement, f-strings whole, fragments dropped.

    ``ast`` hands an f-string as pieces, so ``f'DROP DATABASE "{drill}"'`` arrives both as the
    whole unparsed node and as its constant prefix; the prefix of a longer collected statement
    is a fragment of that same statement, not a second one, so it is dropped rather than
    pretending each fragment names a database.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and not isinstance(node.value, str):
            continue
        if not isinstance(node, (ast.Constant, ast.JoinedStr)):
            continue
        text = ast.unparse(node)
        text = text[text.index(text.lstrip("rbuf'\"")[0]):] if text[:1] in "rfbuf" else text
        text = text.strip().strip("'\"").strip()
        if _WRITE_VERB.match(text):
            found.add(text)
    return sorted(item for item in found
                  if not any(item != other and other.startswith(item) for other in found))


def test_the_script_issues_no_writing_statement_that_names_the_production_database():
    """判据⑥的静态预算：以写动词开头的语句字面量逐枚点名，只准指向恢复库。"""
    issued = _issued_statements(Path(drill.__file__))
    assert issued, "这件本来就发 CREATE/DROP DATABASE，清单不该是空的"
    for text in issued:
        assert drill.SOURCE_DB not in text, text
        assert "{drill}" in text or drill.DRILL_DB in text or text.upper().startswith("ANALYZE"), text
        assert not text.upper().startswith(_BANNED_VERBS), text
    drops = [text for text in issued if text.upper().startswith("DROP")]
    assert drops and all(drill.DRILL_DB in text or "{drill}" in text for text in drops)
    creates = [text for text in issued if text.upper().startswith("CREATE")]
    assert creates and all(drill.DRILL_DB in text or "{drill}" in text for text in creates)
