# -*- coding: utf-8 -*-
"""R393 判据②③⑥：取证格必须真填上数，填不上就当众炸 —— 全部离线，靠一枚假会话。

为什么用假连接而不是真库
------------------------
这一格要钉的不是"库里有多少枚向量"，而是**四条环境事实**与"工具在事实面前怎么表现"。
四条事实是 2026-09-27 在容器 ``enterprise-brain-postgres-1``（PG 16.15 / pgvector 0.8.6）
里亲跑只读取证量出来的，本件把它们逐条建模（见 :class:`FakePgvectorSession`），于是不必
起容器、不必连库、更不必打模型，就能让"取证格悄悄空转"这一族缺陷当场红：

1. **GUC 在库被这条会话用过之前不存在**：未加载时 ``SHOW hnsw.ef_search`` 当场
   ``unrecognized configuration parameter``，``pg_settings`` 里连一行都没有。
   ⇒ 判据⑥点名要建模的就是这一条：它不许被写成"永远能读到数"。
2. **占位参数陷阱**：未加载时 ``set_config('hnsw.ef_search', v, TRUE)`` 照样返回 v，
   ``SHOW`` 也照样念回 v —— 但那只是 PostgreSQL 给两段式名字立的占位值，pgvector 根本不读；
   库真被带起来时它还会被出厂档顶掉。⇒ 只"念回来"不等于钉上了，探测必须在设定之前。
3. **``set_config(..., TRUE)`` 只活在这一笔事务**：COMMIT 之后回到会话档（无残留）。
4. **会话级 ``SET`` 会一直留在这条连接上**：跨事务，把后面每一次读数都染成同一档。
"""
import importlib.util
import pathlib
import re

import pytest

from app.rag import pg_store

ROOT = pathlib.Path(__file__).resolve().parents[1]
RULER = None

FACTORY_WIDTH = "40"      # 实测：pgvector 0.8.6 出厂档（source=default、boot_val 同值）
OTHER_WIDTH = "88"        # 实测：会话级 SET 之后跨事务仍在的那一档
BOUND_LOW, BOUND_HIGH = "1", "1000"    # 实测：服务端自己报的界

GUC = "hnsw.ef_search"


def _ruler():
    global RULER
    if RULER is None:
        spec = importlib.util.spec_from_file_location(
            "r393_ruler", ROOT / "scripts" / "r59_recall_compare.py")
        RULER = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(RULER)
    return RULER


class _Row(tuple):
    """元组行 + 可选 keys()：真库回来的行有时是元组、有时是字典，两形都得认。"""

    def keys(self):
        return self._names if hasattr(self, "_names") else []


def _row(values, names=None):
    row = _Row(values)
    if names is not None:
        row._names = names
    return row


class _Result(object):
    def __init__(self, rows, names=None):
        self._rows = list(rows)
        self.description = [(name, ) for name in (names or [])]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakePgvectorSession(object):
    """按上面四条事实建模的一条连接。零真库、零容器、零网络。"""

    def __init__(self, *, vector_present=True, settings_lies=False,
                 setting_is_ignored=False, refuses_settings_query=False):
        self.log = []
        self.loaded = False
        self.session_value = None
        self.txn_value = None
        self.placeholder = None
        self.vector_present = vector_present
        self.settings_lies = settings_lies
        self.setting_is_ignored = setting_is_ignored
        self.refuses_settings_query = refuses_settings_query
        self.closed = False
        self.commit_count = 0

    # -- 会话档：只有库加载之后这个参数才存在 -----------------------------------
    def _effective(self):
        if not self.loaded:
            return None
        if self.txn_value is not None:
            return self.txn_value
        return self.session_value or FACTORY_WIDTH

    @property
    def _source(self):
        if self.txn_value is not None or self.session_value:
            return "session"
        return "default"

    def execute(self, sql, params=None):
        statement = str(sql)
        bound = tuple(params or ())
        self.log.append((statement, bound))
        lowered = statement.lower()
        if "::vector" in lowered or "null::vector" in lowered:
            if not self.vector_present:
                raise RuntimeError('type "vector" does not exist')
            self.loaded = True
        if statement == RULER_ENSURES:
            return _Result([_row((True, ))])
        if statement.startswith("SELECT setting, source, boot_val"):
            if self.refuses_settings_query:
                raise RuntimeError("permission denied for view pg_settings")
            if not self.loaded:
                return _Result([])                      # 事实 1：目录里没有行
            value = self._effective()
            if self.settings_lies:
                value = OTHER_WIDTH                     # 目录与后端各说一个数
            return _Result([_row((value, self._source, FACTORY_WIDTH, FACTORY_WIDTH,
                                  "user", BOUND_LOW, BOUND_HIGH))],
                           names=["setting", "source", "boot_val", "reset_val",
                                  "context", "min_val", "max_val"])
        if statement.startswith("SELECT current_setting"):
            if self.setting_is_ignored:
                return _Result([_row((FACTORY_WIDTH, ))])   # 钉了，但库里不认
            if self.loaded:
                return _Result([_row((self._effective(), ))])
            return _Result([_row((self.placeholder, ))])    # 事实 2：占位值，库不读
        if statement.startswith("SHOW "):
            if not self.loaded:
                raise RuntimeError('unrecognized configuration parameter "' + GUC + '"')
            return _Result([_row((self._effective(), ))])
        if re.match(r"^\s*SET\s+hnsw\.ef_search", statement, re.I):
            value = str(bound[1] if len(bound) > 1 else bound[0])
            if self.loaded:
                self.session_value = value              # 事实 4：跨事务留着
            else:
                self.placeholder = value                # 事实 2：只是占位
            return _Result([_row(("SET", ))])
        if statement == pg_store._APPLY_HNSW_EF_SEARCH_SQL:
            guc, value = str(bound[0]), str(bound[1])
            assert guc == GUC, "钉的不是候选宽度那一枚参数：" + guc
            if self.loaded:
                self.txn_value = value                  # 事实 3：只活在这笔事务
            else:
                self.placeholder = value
            return _Result([_row((value, ))])
        if "from vector_scope" in lowered:
            return _Result([_row((1, "nomic-embed-text", 768, "l2", 16, 100))])
        if "from pg_indexes" in lowered:
            return _Result([_row(("chunk_vectors_pkey", "CREATE UNIQUE INDEX ..."))])
        if "order by embedding" in lowered:
            return _Result([_row(("v-1", 0.25)), _row(("v-2", 0.5))])
        if "count(*)" in lowered:
            return _Result([_row((2, ))])
        return _Result([])

    def commit(self):
        self.commit_count += 1
        self.txn_value = None                           # 事实 3

    def rollback(self):
        self.txn_value = None

    def close(self):
        self.closed = True

    # -- 便于断言的小工具 --------------------------------------------------------
    def indexes_of(self, pattern):
        finder = re.compile(pattern, re.I)
        return [position for position, (statement, _bound) in enumerate(self.log)
                if finder.search(statement)]


RULER_ENSURES = _ruler().ENSURE_VECTOR_LIB_SQL


class _FakeTool(object):
    """真库那一侧的取值小工具：字典行/元组行都认（照抄 compare_vector_recall 的口径）。"""

    pg_store = pg_store

    @staticmethod
    def _row(row, key, index):
        return row[key] if isinstance(row, dict) else row[index]

    @staticmethod
    def _scalar(row):
        return _row(row, "", 0)


@pytest.fixture()
def ruler():
    return _ruler()


@pytest.fixture()
def tool():
    return _FakeTool()


# ------------------------------------------------- 事实建模本身也要钉（判据⑥）

def test_the_fake_models_the_guc_only_existing_after_a_vector_statement(tool):
    fake = FakePgvectorSession()
    assert fake.loaded is False
    with pytest.raises(RuntimeError) as caught:
        fake.execute("SHOW " + GUC)
    assert "unrecognized configuration parameter" in str(caught.value)
    assert fake.execute(_ruler().ENSURE_VECTOR_LIB_SQL).fetchone() == (True,)
    assert fake.loaded is True
    assert fake.execute("SHOW " + GUC).fetchone()[0] == FACTORY_WIDTH


def test_the_fake_models_the_placeholder_trap(tool):
    """未加载时钉一档：念回来像成功，但 pg_settings 没行、库真加载后又被顶回出厂档。"""
    fake = FakePgvectorSession()
    assert fake.execute(pg_store._APPLY_HNSW_EF_SEARCH_SQL, (GUC, "77")).fetchone() == ("77", )
    #: 未加载时 current_setting 照样念回占位值：看着像钉上了，pgvector 根本不读。
    assert fake.execute(_ruler().READ_SETTING_SQL, (GUC,)).fetchone() == ("77", )
    assert fake.execute(_ruler().PG_SETTING_SQL, (GUC,)).fetchone() is None
    fake.execute(_ruler().ENSURE_VECTOR_LIB_SQL)
    assert fake.execute(_ruler().PG_SETTING_SQL, (GUC,)).fetchone()[0] == FACTORY_WIDTH


# ----------------------------------------------------------- 判据②：格必须填上数

def test_the_fact_cell_fills_value_and_provenance_on_a_fresh_session(ruler, tool):
    fake = FakePgvectorSession()
    facts = ruler.pg_engine_facts(fake, tool=tool, vector_table="chunk_vectors",
                                  width=999, width_source=ruler.WIDTH_FROM_TRUE_SOURCE)
    assert facts["errors"] == {}, "背景格也不该红：" + repr(facts["errors"])
    cell = facts["width"]
    assert cell["readable"] is True
    assert cell["session_baseline"]["value"] == FACTORY_WIDTH
    assert cell["session_baseline"]["origin"] == ruler.ORIGIN_FACTORY
    assert cell["session_baseline"]["source"] == "default"
    assert cell["session_baseline"]["boot_val"] == FACTORY_WIDTH
    assert (cell["session_baseline"]["min_val"], cell["session_baseline"]["max_val"]) \
        == (BOUND_LOW, BOUND_HIGH)
    assert cell["true_source"] == pg_store.configured_hnsw_ef_search()
    assert cell["requested"] == 999
    #: 归档产物里那枚字段名沿用，但它过去长期是空串：现在为空的话上面就已经炸了。
    assert facts["hnsw_ef_search"] == FACTORY_WIDTH
    ensure = fake.indexes_of("NULL::vector")
    read_back = fake.indexes_of("current_setting")
    assert ensure and read_back and min(ensure) < min(read_back), (
        "探测必须排在读数之前：库没加载时读回来的只是一枚占位参数")


def test_a_failing_background_leg_no_longer_empties_the_width_cell(ruler, tool):
    """过去正是这条路让取证格空转：pg_indexes 那一腿失败 ⇒ 没人加载库 ⇒ SHOW 炸 ⇒ 吞掉。

    现在背景格失败照样记账，宽度那一格自己先把库带起来，照样填得出数。
    """
    fake = FakePgvectorSession(refuses_settings_query=False)
    broken = ruler.pg_engine_facts(_RefusingIndexes(fake), tool=tool,
                                   vector_table="chunk_vectors", width=999,
                                   width_source=ruler.WIDTH_FROM_CLI)
    assert "indexes" in broken["errors"], "背景格失败要看得见（这一格允许记错，不许冒充读数）"
    assert broken["width"]["readable"] is True
    assert broken["hnsw_ef_search"] == FACTORY_WIDTH


def test_the_cell_shouts_instead_of_swallowing_when_the_guc_is_unreachable(ruler, tool):
    for kwargs, hint in (({"vector_present": False}, "不可知"),
                         ({"refuses_settings_query": True}, "不可知"),
                         ({"settings_lies": True}, "对不上")):
        fake = FakePgvectorSession(**kwargs)
        with pytest.raises(ruler.EngineWidthUnreadable) as caught:
            ruler.pg_engine_facts(fake, tool=tool, vector_table="chunk_vectors",
                                  width=999, width_source=ruler.WIDTH_FROM_TRUE_SOURCE)
        message = str(caught.value)
        assert GUC in message and hint in message, (kwargs, message)
        assert "作废" in message, "读不到数必须把这份读数丢掉，而不是印出来"


def test_the_failure_never_lands_in_an_errors_string(ruler, tool):
    """判据②的正面形状：宽度失败不写进 errors，也不返回半张脸的产物。"""
    fake = FakePgvectorSession(vector_present=False)
    with pytest.raises(ruler.EngineWidthUnreadable):
        ruler.pg_engine_facts(fake, tool=tool, vector_table="chunk_vectors",
                              width=999, width_source=ruler.WIDTH_FROM_TRUE_SOURCE)
    assert ruler.EngineWidthUnreadable is not Exception  # 一枚具名异常，不是一句字符串


# --------------------------------------------------- 判据③：钉法与读腿同口径

def test_the_width_is_pinned_in_the_read_txn_before_the_ranking_sql(ruler, tool):
    fake = FakePgvectorSession()
    fake.execute(_ruler().ENSURE_VECTOR_LIB_SQL)
    ledger = {"applied_reads": 0, "observed": None, "origin": "not-applied-yet"}
    hits = ruler.pg_live_topk(fake, vector_table="chunk_vectors", operator="<->",
                              literal="[1,2]", k=2, width=999, ledger=ledger)
    set_positions = fake.indexes_of("set_config")
    rank_positions = fake.indexes_of("order by embedding")
    assert set_positions and rank_positions and max(set_positions) < min(rank_positions), \
        "排名语句之前没钉宽度：这一腿量的还是进来时那一档"
    applied = [bound for statement, bound in fake.log
               if statement == pg_store._APPLY_HNSW_EF_SEARCH_SQL]
    assert applied and applied[-1] == (GUC, "999"), "钉的不是真源那条 SQL 或参数不对"
    assert ledger["observed"] == "999" and ledger["origin"] == ruler.ORIGIN_TRANSACTION
    assert ledger["applied_reads"] == 1
    assert [vector_id for vector_id, _distance in hits] == ["v-1", "v-2"]


def test_a_setting_the_server_refuses_voids_the_reading(ruler, tool):
    """钉完必核：库里不认这个数（返回的还是进来时那一档），这一腿就不能算数。"""
    fake = FakePgvectorSession()
    fake.execute(_ruler().ENSURE_VECTOR_LIB_SQL)
    fake.setting_is_ignored = True
    with pytest.raises(ruler.EngineWidthUnreadable) as caught:
        ruler.pg_live_topk(fake, vector_table="chunk_vectors", operator="<->",
                           literal="[1,2]", k=2, width=999, ledger={})
    assert GUC in str(caught.value) and "不一致" in str(caught.value)


def test_the_exact_leg_does_not_claim_a_width_it_never_pinned(ruler, tool):
    """精确腿关掉了索引扫描：给它记一档只会多出一格来历不明的数。"""
    fake = FakePgvectorSession()
    fake.execute(_ruler().ENSURE_VECTOR_LIB_SQL)
    ledger = {"applied_reads": 0, "observed": None}
    ruler.pg_exact_topk(fake, vector_table="chunk_vectors", operator="<->",
                        literal="[1,2]", k=2)
    assert not [statement for statement, _bound in fake.log
                if statement == pg_store._APPLY_HNSW_EF_SEARCH_SQL]
    assert ledger["applied_reads"] == 0


# ------------------------------------ 会话级污染：本件不制造，制造了要看得见

def test_session_level_setting_would_have_persisted_across_transactions(tool):
    """事实 4 自己也要钉：会话级 SET 跨过 COMMIT 仍留在这条连接上。"""
    fake = FakePgvectorSession()
    fake.execute(_ruler().ENSURE_VECTOR_LIB_SQL)
    fake.execute("SET hnsw.ef_search = %s", ("77", ))
    fake.commit()
    assert fake.execute("SHOW " + GUC).fetchone()[0] == "77", "假件没建模住会话级残留"


def test_the_residue_check_passes_our_own_transaction_local_setting(ruler, tool):
    fake = FakePgvectorSession()
    cell = ruler.read_hnsw_width(fake, tool=tool, requested_width=999,
                                 width_source=ruler.WIDTH_FROM_TRUE_SOURCE)
    ruler.apply_hnsw_ef_search(fake, width=999, ledger=cell["read_txn"])
    assert fake.txn_value == "999"
    fake.commit()
    ruler.check_session_residue(fake, cell=cell)
    assert cell["after_read_txn"]["residue"] is False
    assert cell["after_read_txn"]["value"] == FACTORY_WIDTH
    assert "residue_warning" not in cell


def test_a_session_level_pinning_gets_caught_by_the_residue_check(ruler, tool, monkeypatch):
    """把钉法换回会话级 SET：这一腿结束后残留必须被量出来，并当众警告。"""
    lying = type("Fake", (), {"configured_hnsw_ef_search": staticmethod(
                   pg_store.configured_hnsw_ef_search),
               "HNSW_EF_SEARCH_GUC": GUC,
               "_APPLY_HNSW_EF_SEARCH_SQL": "SET hnsw.ef_search = %s"})
    monkeypatch.setattr(ruler, "pg_store_true_source", lambda: lying)
    fake = FakePgvectorSession()
    fake.execute(_ruler().ENSURE_VECTOR_LIB_SQL)
    cell = {"session_baseline": {"value": FACTORY_WIDTH}}
    ruler.apply_hnsw_ef_search(fake, width=999, ledger={})
    fake.commit()
    ruler.check_session_residue(fake, cell=cell)
    assert cell["after_read_txn"]["residue"] is True, "会话级污染没被这格逮住"
    assert "残留" in cell["residue_warning"] and GUC in cell["residue_warning"]


def test_build_result_drops_the_reading_when_the_cell_cannot_be_filled(ruler, tool):
    """判据②的最终形状：主流程拿不到档 = 前置不满足退出，不带着空口径继续印表。"""
    fake = FakePgvectorSession(vector_present=False)
    with pytest.raises(ruler.EngineWidthUnreadable):
        ruler.read_hnsw_width(fake, tool=tool, requested_width=1,
                              width_source=ruler.WIDTH_FROM_TRUE_SOURCE)
    source = (ROOT / "scripts" / "r59_recall_compare.py").read_bytes().decode("utf-8")
    assert "except EngineWidthUnreadable as exc:" in source.replace("\r\n", "\n"), \
        "主流程没有接住它：那这一格又会变成一句栈"


class _RefusingIndexes(object):
    """只把 pg_indexes 那一腿弄坏的连接：模拟"顺手加载库的那条语句失败了"。"""

    def __init__(self, inner):
        self.inner = inner
        self.log = inner.log

    def execute(self, sql, params=None):
        if "pg_indexes" in str(sql):
            raise RuntimeError("relation \"pg_indexes\" permission denied")
        return self.inner.execute(sql, params)

    def commit(self):
        self.inner.commit()

    def close(self):
        self.inner.close()
