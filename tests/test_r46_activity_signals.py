"""R46 · 活动信号回填排序（采纳/驳回 → 相关度先验）后端的三条判据各自有钉子。

跟进单 §21 给 R46 的判据原文是三句：① 有信号后排序变化可测；② 无信号时与现状一致；
③ 隐私＝只存计数不存内容，禁止项＝不得把用户问题原文写进新表。本文件按这三句加派工单
另补的两条（④ 鉴权与越权、⑤ 迁移卫生）分组，每组都有一枚"摘掉实现就会红"的具名用例：

- ①⑥  ``test_the_search_call_itself_reorders_when_a_document_was_adopted``
        ——它跑的是 DocumentRetriever.search()，不是 rank_hits_by_activity。先验没接进
        那条腿它就红（反证一把）。
- ③    ``test_free_text_smuggled_into_the_payload_is_rejected_and_never_stored``
        ——把 _reject_extra_fields 那一步摘掉，它当场红（反证二把）。

库与模型都不在场：PG 走注入的假连接，向量库走假 collection，embedding 直接给常量向量。
"""
import json
import re
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.agents.contracts import ErrorEnvelope
from app.api.v1 import feedback
from app.common.auth import create_token
from app.main import app
from app.rag import retriever as rt

REPO = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO / "migrations"
MODEL = "nomic-embed-text"

#: 一篇文档一行计数的三元组，测试用它冒充 0011 那张表。
ROWS = [
    ("finance-q3.txt", 12, 0),
    ("hr-leave.txt", 0, 9),
    ("neutral.txt", 3, 3),
]


def _hits(*names):
    """命中字典：形状与 app/rag/retriever.py 的 _hit_dicts 一致（source 就是 filename）。"""
    return [
        {
            "content": f"body of {name}",
            "source": name,
            "chunk_index": 0,
            "classification": 1,
            "department": "finance",
            "retrieval_mode": rt.MODE_SEMANTIC if hasattr(rt, "MODE_SEMANTIC") else "semantic",
            "retrieval_reason": "",
        }
        for name in names
    ]


def _priors(rows=ROWS):
    return {name: {"accepted": int(a), "rejected": int(r)} for name, a, r in rows}


def _sources(hits):
    return [str(hit.get("source")) for hit in hits]


# ---------------------------------------------------- 判据① 有信号后排序变化可测
def test_an_adopted_document_moves_up_and_a_rejected_one_moves_down():
    hits = _hits("neutral.txt", "finance-q3.txt", "hr-leave.txt")
    ranked = rt.rank_hits_by_activity(hits, _priors())

    assert _sources(ranked) == ["finance-q3.txt", "neutral.txt", "hr-leave.txt"], (
        "R46 判据①：+12/-0 的那篇必须升到第一，-9 的那篇必须掉到末位；"
        "这里断言的是**名次**真的变了，不是「读到了计数」。"
    )
    # 分值同样真的动了：榜首的分值高于它原来那一档的名次分。
    first = ranked[0]["activity_prior"]
    assert first["previous_rank"] == 2 and first["new_rank"] == 1
    assert first["rank_score"] > 1.0 / (rt.ACTIVITY_PRIOR_RANK_BASE + 2)


def test_the_prior_reorders_the_candidate_set_without_widening_or_narrowing_it():
    hits = _hits("a.txt", "finance-q3.txt", "b.txt", "hr-leave.txt")
    ranked = rt.rank_hits_by_activity(hits, _priors())

    assert sorted(_sources(ranked)) == sorted(_sources(hits)), "先验一个候选都不许增删"
    assert len(ranked) == len(hits)


def test_a_single_adoption_is_weakened_by_the_smoothing_term():
    """一枚采纳不该替整篇文档定序：平滑项就是为了让小样本的先验弱。"""
    one = rt.activity_prior_value({"accepted": 1, "rejected": 0})
    many = rt.activity_prior_value({"accepted": 20, "rejected": 0})
    assert 0 < one < many
    assert many < rt.ACTIVITY_PRIOR_WEIGHT
    assert abs(one - rt.ACTIVITY_PRIOR_WEIGHT / (1 + rt.ACTIVITY_PRIOR_SMOOTHING)) < 1e-12


def test_equal_priors_keep_the_original_order_rather_than_coin_flipping():
    hits = _hits("x.txt", "y.txt")
    priors = {"x.txt": {"accepted": 5, "rejected": 0}, "y.txt": {"accepted": 5, "rejected": 0}}
    assert _sources(rt.rank_hits_by_activity(hits, priors)) == ["x.txt", "y.txt"]


def test_the_kill_switch_turns_the_prior_off_without_touching_the_order(monkeypatch):
    monkeypatch.setenv(rt.ACTIVITY_PRIOR_ENV, "off")
    hits = _hits("neutral.txt", "finance-q3.txt")
    assert rt.rank_hits_by_activity(hits, _priors(), enabled=rt.activity_prior_enabled()) is hits
    assert rt.activity_priors() == {}
    assert rt.activity_prior_diagnostics()["reason"] == "disabled_by_configuration"


def test_a_misconfigured_switch_value_does_not_silently_disable_the_prior(monkeypatch):
    """与 rbac.py 的 R17 灰度开关同口径：退回要写对，拼错不算退回。"""
    monkeypatch.setenv(rt.ACTIVITY_PRIOR_ENV, "of")
    assert rt.activity_prior_enabled() is True


# ---------------------------------------------------- 判据② 无信号时与现状一致
def test_no_signals_returns_the_very_same_list_object_not_an_equal_copy():
    hits = _hits("a.txt", "b.txt", "c.txt")
    assert rt.rank_hits_by_activity(hits, {}) is hits
    assert rt.rank_hits_by_activity(hits, {"a.txt": {"accepted": 0, "rejected": 0}}) is hits
    assert "activity_prior" not in hits[0], "无信号时连键都不许长出来"


def test_the_same_query_scores_identically_with_an_empty_table_and_with_the_prior_off():
    """判据②要的对照：同一把候选集，"表里零行"与"根本没开先验"两态逐字相同。

    两态都必须是**同一个对象**，不然就得靠浮点比较才算"一致"，那种一致随时会碎。
    """
    hits = _hits("a.txt", "b.txt", "c.txt")
    with_empty_table = rt.rank_hits_by_activity(hits, _priors(rows=[]))
    with_switch_off = rt.rank_hits_by_activity(hits, _priors(), enabled=False)

    assert with_empty_table is hits and with_switch_off is hits
    assert json.dumps(with_empty_table, ensure_ascii=False) == json.dumps(hits, ensure_ascii=False)


def test_an_unreadable_count_table_leaves_the_order_alone_and_says_why(monkeypatch, caplog):
    """fail-open 的两半：排序退回现状，但观测面要能把它与"没有信号"分开。

    选 fail-open 而不是 fail-closed 的理由写在 retriever.py 的 R46 段注释里：一次数据库
    故障不该决定问答能不能作答，而"读不到就换一种排法"才是真的把现状改掉。
    """
    rt.reset_activity_priors()
    monkeypatch.delenv(rt.ACTIVITY_PRIOR_ENV, raising=False)

    def broken_reader():
        raise RuntimeError("connection refused")

    assert rt.activity_priors(row_reader=broken_reader) == {}
    diagnostics = rt.activity_prior_diagnostics()
    assert diagnostics["source"] == "error" and diagnostics["reason"] == "RuntimeError"

    hits = _hits("a.txt", "b.txt")
    assert rt.rank_hits_by_activity(hits, rt.activity_priors(row_reader=broken_reader)) is hits

    rt.reset_activity_priors()
    assert rt.activity_priors(row_reader=lambda: []) == {}
    read_but_empty = rt.activity_prior_diagnostics()
    assert read_but_empty["source"] == "store" and read_but_empty["documents"] == 0
    rt.reset_activity_priors()

# ------------------------------------------ 判据①⑥ 真接线（摘掉先验读取就会红的靶子）
class _FakeCollection:
    """假向量库：只认 query()，按固定顺序交回命中，不碰 chromadb 也不碰模型。"""

    def __init__(self, names):
        self.names = list(names)
        self.query_calls = []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        picked = self.names[: int(kwargs.get("n_results", len(self.names)))]
        return {
            "documents": [["body of " + name for name in picked]],
            "metadatas": [
                [
                    {
                        "filename": name,
                        "chunk_index": 0,
                        "classification": 1,
                        "department": "finance",
                    }
                    for name in picked
                ]
            ],
            "distances": [[0.1 * (index + 1) for index in range(len(picked))]],
        }


class _StubEmbedder:
    """常量向量的假 embedding：本文件不验向量算术，只验名次算术。"""

    def embed_query(self, text):
        return [0.0] * rt.EMBEDDING_DIM


def _broken_reader():
    raise RuntimeError("no database in this test")


def _retriever(names, priors):
    """装一把只走语义腿的检索器：热集关着，向量库与 embedding 都是假的。

    chroma_dir 用 conftest 钉好的沙箱默认值而不是每次新开一个目录：本夹具根本不碰
    真向量库（collection 立刻被 _FakeCollection 顶掉），但 chromadb 每个新路径都要
    冷起一次客户端，实测三次自建目录就多花 33 秒——那是测试写法的时间，不是被测代码的。
    """
    from app.rag.retriever import DocumentRetriever

    instance = DocumentRetriever(activity_prior=lambda: dict(priors))
    instance.collection = _FakeCollection(names)
    instance.embedding = _StubEmbedder()
    return instance


def test_the_search_call_itself_reorders_when_a_document_was_adopted(monkeypatch):
    """🔴 反证一把的靶子：先验必须接在 search() 上，而不是只长在工具函数里。

    把 search() 里那几处 self._apply_activity_prior(...) 摘掉，这条用例当场红——红在
    "原本第三名的 finance-q3.txt 还在第三名"，而不是红在"读不到计数"。
    """
    from app.rag import hot_index

    monkeypatch.setattr(hot_index, "hot_index_enabled", lambda: False)
    instance = _retriever(["neutral.txt", "x.txt", "finance-q3.txt"], _priors())

    hits = instance.search("季度营收", k=3)

    assert [hit["source"] for hit in hits] == ["finance-q3.txt", "neutral.txt", "x.txt"], (
        "R46 判据①：search() 交回的次序没变，说明先验没接进这条腿（摘掉接线就红在这里）"
    )
    assert hits[0]["activity_prior"]["previous_rank"] == 3
    assert hits[0]["activity_prior"]["accepted"] == 12


def test_every_leg_of_search_routes_through_the_prior():
    """四条腿（语义/热集/降级词法/store 离线）都得过先验，漏一条就是"某些问答没先验"。

    这条读源码而不是跑四条腿：跑齐四条要造四套假后端，而"漏接线"本身看一眼源码就能钉住。
    断言写成"不许有裸返回命中列表"，以后再加长腿时也拦得住。
    """
    import inspect

    source = inspect.getsource(rt.DocumentRetriever.search)
    assert source.count("self._apply_activity_prior(") >= 4, (
        "search() 的每条命中出口都要过先验，实际接线次数不足 4"
    )
    for bare in ("return self._keyword_hits(", "return hot_hits", "return self._hit_dicts("):
        assert bare not in source, "search() 里出现了没过先验的裸返回：" + bare


def test_the_retriever_reads_the_default_loader_when_nothing_is_injected(monkeypatch):
    """不注入读取方时它也得得住：读不到 = 不动排序，而不是抛穿到问答里。"""
    from app.rag import hot_index
    from app.rag.retriever import DocumentRetriever

    monkeypatch.setattr(hot_index, "hot_index_enabled", lambda: False)
    monkeypatch.setattr(rt, "_read_activity_signal_rows", _broken_reader)
    rt.reset_activity_priors()
    instance = DocumentRetriever()
    instance.collection = _FakeCollection(["a.txt", "b.txt"])
    instance.embedding = _StubEmbedder()

    hits = instance.search("随便", k=2)

    assert [hit["source"] for hit in hits] == ["a.txt", "b.txt"], "读不到时名次必须一动不动"
    assert rt.activity_prior_diagnostics()["source"] == "error"
    rt.reset_activity_priors()


# ------------------------------------------------- 判据③ 隐私：只存计数不存内容
def _create_table_columns(sql, table):  # noqa: ANN001 - 测试内的极简解析器
    """从 CREATE TABLE 块里抠出 列名 -> 类型，只认这张新表自己的定义。"""
    block = re.search(
        r"CREATE TABLE IF NOT EXISTS " + re.escape(table) + r"\s*\((.*?)\n\);",
        sql,
        re.S,
    )
    assert block, "0011 里没有 " + table + " 的 CREATE TABLE 块"
    columns = {}
    for raw in block.group(1).split("\n"):
        line = raw.strip()
        if not line or line.startswith(("--", "CONSTRAINT")):
            continue
        name, _, rest = line.partition(" ")
        if name.upper() in ("PRIMARY", "UNIQUE", "CHECK", "FOREIGN"):
            continue
        columns[name] = rest.split("CONSTRAINT")[0].strip()
    return columns


def test_migration_0011_has_no_column_that_could_hold_a_question():
    """禁止项＝「不得把用户问题原文写进新表」——钉在列清单上，不钉在清洗逻辑上。"""
    sql = (MIGRATIONS / "0011_document_activity_signals.sql").read_text(encoding="utf-8")
    columns = _create_table_columns(sql, "document_activity_signals")

    assert set(columns) == {
        "filename",
        "accepted_count",
        "rejected_count",
        "first_signal_at",
        "last_signal_at",
    }, columns
    joined = " ".join(columns)
    for banned in ("query", "question", "prompt", "text", "content", "answer", "excerpt", "note"):
        assert banned not in joined, "新表里出现了能装内容的列：" + banned
    text_columns = [name for name, kind in columns.items() if "TEXT" in kind.upper()]
    assert text_columns == ["filename"], "唯一的文本列必须是文件名"
    assert "length(filename) <= 512" in sql, (
        "key 列要有硬上界，否则原文可以整段塞进文件名位置"
    )


class _RecordingConnection:
    """假 PG 连接：把每一次 execute 的 SQL 与参数原样记下来，供隐私断言检查。"""

    def __init__(self, counts=(0, 0)):
        self.calls = []
        self.counts = counts
        self.committed = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.calls.append((str(sql), params))
        return self

    def fetchone(self):
        return self.counts

    def commit(self):
        self.committed += 1


USERS = {
    "alice": {"username": "alice", "role": "staff", "department": "finance"},
    "mallory": {"username": "mallory", "role": "staff", "department": "hr"},
    "boss": {"username": "boss", "role": "admin", "department": ""},
    "ghost": {"username": "ghost", "role": "staff", "department": "finance", "status": "disabled"},
}
DOC_ROW = {
    "filename": "finance-q3.txt",
    "version": 3,
    "classification": 1,
    "department": "finance",
    "owner_id": "alice",
}


def _staff_client(monkeypatch, users, rows, store):  # noqa: ANN001 - 测试夹具
    """把身份、目录、PG 三件事都换成假的；一切改动走 monkeypatch，用例结束自动还原。"""
    from app.common import auth as auth_module

    monkeypatch.setattr(auth_module, "get_user", lambda username: users.get(username))
    monkeypatch.setattr(
        feedback,
        "list_document_versions",
        lambda name: [rows[name]] if name in rows else [],
    )
    monkeypatch.setattr(feedback, "_CONNECTION_FACTORY", lambda: store)
    return TestClient(app)


def _post(client, payload, username="alice"):
    return client.post(
        "/api/v1/feedback/document",
        headers={"Authorization": "Bearer " + create_token(username)},
        json=payload,
    )


def test_the_only_values_that_reach_the_store_are_a_filename_and_two_counters(monkeypatch):
    """写路径的形状钉死：一次 INSERT，参数只有文件名 + 两枚 0/1。"""
    store = _RecordingConnection((7, 2))
    client = _staff_client(monkeypatch, USERS, {"finance-q3.txt": DOC_ROW}, store)

    response = _post(client, {"filename": "finance-q3.txt", "signal": "accepted"})

    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "ok",
        "filename": "finance-q3.txt",
        "signal": "accepted",
        "accepted_count": 7,
        "rejected_count": 2,
    }
    written = [call for call in store.calls if call[0].strip().upper().startswith("INSERT")]
    assert len(written) == 1, "一次请求只许写一条 INSERT"
    assert written[0][1] == ("finance-q3.txt", 1, 0), "写库参数只能是文件名 + 两枚 0/1 增量"
    # 整条路径上出现过的**全部**参数：字符串只能是文件名，整数只能是 0/1，谁都不许超长。
    for _sql, params in store.calls:
        for value in params or ():
            if isinstance(value, str):
                assert value == "finance-q3.txt", "触达数据库的字符串只有文件名这一枚"
            else:
                assert int(value) in (0, 1), "触达数据库的数字只能是 0/1 增量"
            assert len(str(value)) <= feedback.MAX_FILENAME_CHARS, "任何参数都不许长成一段正文"

# ------------------------------------- 判据③ 内容进不来：拒收并且一个字都不落库
def _smuggled_text():
    """一段足以塞满 answer 正文的中文长文本，用来试走私。"""
    return "第一季度营收同比上涨，请解释原因" * 40


def test_free_text_smuggled_into_the_payload_is_rejected_and_never_stored(monkeypatch):
    """🔴 反证二把的靶子：把 _reject_extra_fields 那一步摘掉（改成直接 return），这条当场红。

    红法有两处可看：状态码不再是 422，或者 store.calls 多出一次 INSERT——两者都说明
    「只存计数」退成了「记得清洗」，而那是会在下一个调用点忘掉的守法。
    """
    store = _RecordingConnection((1, 0))
    client = _staff_client(monkeypatch, USERS, {"finance-q3.txt": DOC_ROW}, store)
    smuggled = _smuggled_text()

    response = _post(
        client,
        {"filename": "finance-q3.txt", "signal": "accepted", "note": smuggled},
    )

    assert response.status_code == 422, "带计数以外字段的请求必须被拒，实际 " + str(response.status_code)
    assert response.json()["detail"] == "validation_error"
    assert store.calls == [], "被拒的请求不许留下任何一次数据库往返"
    assert smuggled not in response.text, "拒绝响应也不许把原文回显出去"


def test_the_rejection_log_records_field_names_and_never_field_values(monkeypatch, caplog):
    """拒收时的日志只许出现字段名：那个值很可能就是问题原文，打日志等于换个地方存。"""
    import logging

    store = _RecordingConnection((1, 0))
    client = _staff_client(monkeypatch, USERS, {"finance-q3.txt": DOC_ROW}, store)
    smuggled = _smuggled_text()

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        response = _post(client, {"filename": "finance-q3.txt", "question": smuggled})

    assert response.status_code == 422
    assert store.calls == []
    joined = " | ".join(record.getMessage() for record in caplog.records)
    assert "question" in joined, "字段名要记下来，否则拒收无从取证"
    assert smuggled not in joined, "日志里出现了被拒的原文"


def test_a_filename_longer_than_the_column_check_is_rejected_before_it_reaches_sql(monkeypatch):
    """上界两侧都是硬护栏：出口 512，0011 的 CHECK 也 512，中间没有可伸展位。"""
    store = _RecordingConnection((1, 0))
    client = _staff_client(monkeypatch, USERS, {"finance-q3.txt": DOC_ROW}, store)
    sql = (MIGRATIONS / "0011_document_activity_signals.sql").read_text(encoding="utf-8")
    column_bound = int(re.search(r"length\(filename\) <= (\d+)", sql).group(1))
    assert column_bound == feedback.MAX_FILENAME_CHARS, "出口上界必须与表上 CHECK 同一个数"

    too_long = "x" * (column_bound + 1) + ".txt"
    assert _post(client, {"filename": too_long, "signal": "accepted"}).status_code == 422
    assert _post(client, {"filename": "a\r\nb.txt", "signal": "accepted"}).status_code == 422
    assert store.calls == [], "越界的 key 不许触达 SQL"


def test_an_unknown_signal_value_is_rejected_rather_than_counted(monkeypatch):
    """signal 只认两枚枚举值：第三种（点击/浏览）要等前端半张单，不预先收。"""
    store = _RecordingConnection((1, 0))
    client = _staff_client(monkeypatch, USERS, {"finance-q3.txt": DOC_ROW}, store)

    assert _post(client, {"filename": "finance-q3.txt", "signal": "clicked"}).status_code == 422
    assert set(feedback.SIGNALS) == {"accepted", "rejected"}
    assert store.calls == []


# ------------------------------------------------------- 判据④ 鉴权与越权：0 条通过
def test_no_caller_out_of_a_cross_department_batch_gets_through(monkeypatch):
    """越权必须是 0 条通过，而不是「返回码好看但账已记上」：整批一次库都不许碰。"""
    store = _RecordingConnection((9, 9))
    client = _staff_client(monkeypatch, USERS, {"finance-q3.txt": DOC_ROW}, store)
    bodies = [
        {"filename": "finance-q3.txt", "signal": "accepted"},
        {"filename": "finance-q3.txt", "signal": "rejected"},
    ]

    denied = [_post(client, body, username="mallory") for body in bodies]

    assert [response.status_code for response in denied] == [403, 403], (
        "跨部门打分必须整批拒；实际 " + str([response.status_code for response in denied])
    )
    assert {response.json()["detail"] for response in denied} == {"permission_denied"}
    assert store.calls == [], "越权请求一条计数都不许写进去"


def test_the_document_owner_is_not_special_cased_a_department_is_the_scope(monkeypatch):
    """能不能打分＝能不能看见，同一个判定：owner 不加分，同部门不因"不是自己的"而减分。"""
    store = _RecordingConnection((2, 0))
    client = _staff_client(monkeypatch, USERS, {"finance-q3.txt": DOC_ROW}, store)

    colleague = _post(client, {"filename": "finance-q3.txt", "signal": "accepted"}, username="alice")
    assert colleague.status_code == 200, "同部门可见即可打分，本模块不长第二套规则"

    stranger = _post(client, {"filename": "finance-q3.txt", "signal": "accepted"}, username="mallory")
    assert stranger.status_code == 403 and stranger.json()["detail"] == "permission_denied"

    admin = _post(client, {"filename": "finance-q3.txt", "signal": "accepted"}, username="boss")
    assert admin.status_code == 200, "管理员按 administrator_scope 可见即可打分"
    assert len([call for call in store.calls if call[0].strip().upper().startswith("INSERT")]) == 2


def test_an_anonymous_caller_and_an_unlisted_document_are_refused_with_their_own_codes(monkeypatch):
    """401/403/404/422/503 各归各位：把"没登录"与"没权限"混成一码，审计就没法用。"""
    store = _RecordingConnection((0, 1))
    client = _staff_client(monkeypatch, USERS, {"finance-q3.txt": DOC_ROW}, store)

    anonymous = client.post("/api/v1/feedback/document", json={"filename": "finance-q3.txt", "signal": "accepted"})
    assert anonymous.status_code == 401 and anonymous.json()["detail"] == "authentication_required"

    missing = _post(client, {"filename": "not-uploaded.txt", "signal": "accepted"})
    assert missing.status_code == 404 and missing.json()["detail"] == "resource_not_found"
    assert store.calls == [], "查无此文与未登录都不该触达计数表"


def test_a_principal_without_any_department_cannot_score_anything(monkeypatch):
    """filters 的 authorization_unavailable 要原样传出来，不能被压成一句权限不足。"""
    no_department = {"orphan": {"username": "orphan", "role": "staff", "department": ""}}
    store = _RecordingConnection((0, 0))
    client = _staff_client(monkeypatch, no_department, {"finance-q3.txt": DOC_ROW}, store)

    response = _post(client, {"filename": "finance-q3.txt", "signal": "accepted"}, username="orphan")

    assert response.status_code == 403
    assert response.json()["detail"] == "authorization_unavailable"
    assert store.calls == []


def test_every_code_this_routes_can_emit_is_already_in_the_approved_vocabulary():
    """没有新造码：全部落在 ErrorEnvelope 的封闭枚举里，故不必动已批的拒绝码清单。"""
    from typing import get_args

    approved = set(get_args(ErrorEnvelope.model_fields["code"].annotation))
    emitted = {
        "authentication_required",
        "permission_denied",
        "authorization_unavailable",
        "resource_not_found",
        "validation_error",
        "storage_unavailable",
    }
    assert emitted <= approved, "需要先挂号的码：" + str(sorted(emitted - approved))


def test_a_store_failure_is_reported_as_storage_unavailable_not_as_a_receipt(monkeypatch):
    """记账失败不许冒充"信号已收下"：业主跑没跑 0011，答案侧要分得清。"""
    class _ExplodingConnection(_RecordingConnection):
        def execute(self, sql, params=None):
            raise RuntimeError("relation document_activity_signals does not exist")

    client = _staff_client(monkeypatch, USERS, {"finance-q3.txt": DOC_ROW}, _ExplodingConnection())

    response = _post(client, {"filename": "finance-q3.txt", "signal": "accepted"})

    assert response.status_code == 503 and response.json()["detail"] == "storage_unavailable"


# --------------------------------- 判据⑥ 反空表闭环：出口写的列＝排序读的列＝0011 的列
class _InMemorySignals:
    """一张只认 0011 那三条语句的假表：写侧与读侧共用同一份列名，谁改了都当场红。"""

    def __init__(self):
        self.rows = {}
        self.statements = []

    def connection(self):
        return _InMemoryConnection(self)

    def snapshot(self):
        return [(name, counts[0], counts[1]) for name, counts in sorted(self.rows.items())]

    def apply(self, sql, params):
        text = " ".join(str(sql).split())
        self.statements.append((text, params))
        if text.upper().startswith("INSERT"):
            name, accepted, rejected = params
            current = self.rows.get(name, (0, 0))
            totals = (current[0] + int(accepted), current[1] + int(rejected))
            assert sum(totals) > 0 and len(name) <= feedback.MAX_FILENAME_CHARS, "0011 的 CHECK"
            self.rows[name] = totals
        return self


class _InMemoryConnection:
    def __init__(self, table):
        self.table = table
        self._pending = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        if text.upper().startswith("INSERT"):
            self.table.apply(sql, params)
            self._pending = None
        elif text.startswith("SELECT accepted_count, rejected_count"):
            row = self.table.rows.get(params[0])
            self._pending = row
        else:
            raise AssertionError("反馈出口发出了预期以外的语句：" + text[:72])
        return self

    def fetchone(self):
        return self._pending

    def commit(self):
        return None


def _table_contract():
    """从 0011 现抠三样东西：key 列名、两枚计数列名、长度上界——测试不抄常数。"""
    sql = (MIGRATIONS / "0011_document_activity_signals.sql").read_text(encoding="utf-8")
    columns = _create_table_columns(sql, "document_activity_signals")
    key = re.search(r"(\w+)\s+TEXT\s+PRIMARY KEY", sql).group(1)
    counters = sorted(name for name in columns if name.endswith("_count"))
    return key, counters, columns


def test_the_writing_columns_and_the_reading_columns_are_the_same_0011_columns():
    """写侧 INSERT 的列、读侧 SELECT 的列、表里真实存在的列，三者必须同源同名。

    这条是"不许假完成"的结构性钉子：只要有一侧悄悄改了列名，读回来就是空，
    那张表立刻退化成没人读的空表——而这里会先红。
    """
    import inspect

    key, counters, columns = _table_contract()
    assert len(counters) == 2, counters
    assert key in columns

    write_columns = re.search(
        r"INSERT INTO document_activity_signals AS s\s*\(([^)]*)\)",
        feedback._UPSERT_SQL,
    ).group(1)
    written = [item.strip() for item in write_columns.split(",")]
    assert set(written) <= set(columns), "写侧用了表里没有的列：" + str(sorted(set(written) - set(columns)))
    assert key in written and set(counters) <= set(written)

    reader_source = inspect.getsource(rt._read_activity_signal_rows)
    # 只抠那条字面量 SQL：docstring 里也有一句白话的 SELECT，不能拿 index 找开头。
    statement = re.search(r'"(SELECT [^"]+ FROM document_activity_signals)"', reader_source)
    assert statement, "读取方里找不到那条 SELECT 语句字面量"
    read_statement = " ".join(statement.group(1).split())
    expected = "SELECT " + ", ".join([key, *counters]) + " FROM document_activity_signals"
    assert read_statement == expected, "读侧语句与 0011 的列名不再同源：" + read_statement


def test_a_signal_recorded_through_the_endpoint_is_read_back_and_moves_the_ranking(monkeypatch):
    """判据⑥的正证：HTTP 出口写的账，排序侧真的读回来并真的改了名次。"""
    table = _InMemorySignals()
    client = _staff_client(monkeypatch, USERS, {"finance-q3.txt": DOC_ROW}, table.connection())

    for _ in range(4):  # 四枚采纳、一枚驳回
        assert _post(client, {"filename": "finance-q3.txt", "signal": "accepted"}).status_code == 200
    assert _post(client, {"filename": "finance-q3.txt", "signal": "rejected"}).status_code == 200
    assert table.rows == {"finance-q3.txt": (4, 1)}, table.rows

    hits = _hits("neutral.txt", "x.txt", "finance-q3.txt")
    ranked = rt.rank_hits_by_activity(hits, rt.activity_priors(row_reader=table.snapshot))

    assert _sources(ranked)[0] == "finance-q3.txt", "4 采纳 1 驳回的那篇必须被顶到首位"
    assert ranked[0]["activity_prior"]["accepted"] == 4 and ranked[0]["activity_prior"]["rejected"] == 1

# ------------------------------------------------------------- 判据④ 越权要留痕
def test_a_refused_signal_is_written_into_the_audit_trail(monkeypatch):
    """拒绝不能只好看：判据④要能事后回答"谁在什么时候试图给别人的文档打分"。"""
    events = []
    monkeypatch.setattr(
        feedback,
        "record_audit",
        lambda principal, action, outcome, resource="", reason="": events.append(
            {
                "username": principal.username,
                "action": action,
                "outcome": outcome,
                "resource": resource,
                "reason": reason,
            }
        ),
    )
    store = _RecordingConnection((0, 0))
    client = _staff_client(monkeypatch, USERS, {"finance-q3.txt": DOC_ROW}, store)

    assert _post(client, {"filename": "finance-q3.txt", "signal": "accepted"}, username="mallory").status_code == 403

    assert len(events) == 1, events
    assert events[0] == {
        "username": "mallory",
        "action": feedback.ACTION_VIEW,
        "outcome": "failure",
        "resource": "finance-q3.txt",
        "reason": "permission_denied",
    }
    assert store.calls == []


# --------------------------------------------------------- 出口真的接在应用上
def test_the_signal_exit_is_registered_as_a_real_route():
    """判据⑥的另一半：HTTP 出口得在应用上活着，不是只写在一个没人 import 的文件里。

    走 openapi()["paths"] 而不是 app.routes：这版 FastAPI 把 include_router 挂成
    懒解析的 _IncludedRouter，路由表里没有可读的 path（同一口径见 tests/test_deployment_guards.py）。"""
    paths = app.openapi()["paths"]

    document = paths.get("/api/v1/feedback/document", {})
    assert "post" in document, "信号出口没注册成 POST：" + str(sorted(document))
    assert "get" in document, "读回计数的那半张脸没挂上：" + str(sorted(document))


def test_reading_back_counts_names_where_the_prior_came_from(monkeypatch):
    """GET 那半张脸：0 分得清是"没人打过点"还是"没读到账"，靠的是 prior_source。"""
    store = _RecordingConnection((0, 0))
    table = _InMemorySignals()
    table.rows = {"finance-q3.txt": (5, 2)}
    client = _staff_client(monkeypatch, USERS, {"finance-q3.txt": DOC_ROW}, store)
    rt.reset_activity_priors()
    monkeypatch.setattr(rt, "_read_activity_signal_rows", table.snapshot)

    response = client.get(
        "/api/v1/feedback/document",
        params={"filename": "finance-q3.txt"},
        headers={"Authorization": "Bearer " + create_token("alice")},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "filename": "finance-q3.txt",
        "accepted_count": 5,
        "rejected_count": 2,
        "prior_source": "store",
        "prior_reason": "",
        "prior_enabled": True,
    }
    rt.reset_activity_priors()


# --------------------------- 判据② 的同一条查询对照：开/关两态的分值快照逐字相同
def test_the_same_query_returns_the_same_snapshot_with_the_prior_off_and_with_no_signals(monkeypatch):
    """工单判据②要的那把对照：同一条查询、同一批候选，两态的分值快照逐字相同。

    顺手把"没多要行"也钉住：发给向量库的 kwargs 在两态下一模一样——先验不改 n_results，
    所以它只在召回窗口内挪名次（窗口外的先验等 next-result 那一单，已写进回执）。
    """
    from app.rag import hot_index

    names = ["neutral.txt", "x.txt", "finance-q3.txt"]
    snapshots = []
    sent_kwargs = []
    for label, priors in (("prior_off", _priors()), ("no_signals", {})):  # noqa: B007 - label 只作标识
        monkeypatch.setattr(hot_index, "hot_index_enabled", lambda: False)
        if label == "prior_off":
            monkeypatch.setenv(rt.ACTIVITY_PRIOR_ENV, "off")
        else:
            monkeypatch.delenv(rt.ACTIVITY_PRIOR_ENV, raising=False)
        instance = _retriever(names, priors)

        hits = instance.search("季度营收", k=3)

        snapshots.append(json.dumps(hits, ensure_ascii=False, sort_keys=True))
        sent_kwargs.append(json.dumps(instance.collection.query_calls[-1]["n_results"]))

    assert snapshots[0] == snapshots[1], "开关两态的返回快照必须逐字相同"
    assert sent_kwargs[0] == sent_kwargs[1] == "3", "先验一个候选都不许多 fetch"
    assert "activity_prior" not in json.dumps(snapshots[0]), "无信号态不许长出先验键"


# ------------------------------------------------------------ 判据⑤ 迁移卫生
def test_the_migrations_stay_one_to_one_with_the_manifest_after_0011():
    """新增一版之后仍然一一对应；README 那条 fail-closed 规矩不许被本单弄破。"""
    manifest = json.loads((MIGRATIONS / "manifest.json").read_text(encoding="utf-8"))
    on_disk = sorted(path.name for path in MIGRATIONS.glob("*.sql"))

    assert sorted(manifest) == on_disk, "SQL 文件与 manifest.json 必须一一对应"
    assert "0011_document_activity_signals.sql" in on_disk
    assert not [name for name in on_disk if name.split("_")[0] > "0011"], "本单没排 0012 的号"
    assert len({name.split("_")[0] for name in on_disk}) == len(on_disk), "版本号不许重复"


def test_every_recorded_migration_checksum_still_matches_the_file_on_disk():
    """0001–0010 一枚都不许动：逐枚重算校验和，与本单之前登记的数字判等。"""
    import hashlib

    manifest = json.loads((MIGRATIONS / "manifest.json").read_text(encoding="utf-8"))
    for filename, digest in manifest.items():
        text = (MIGRATIONS / filename).read_text(encoding="utf-8")
        assert digest == hashlib.sha256(text.encode("utf-8")).hexdigest(), filename
    from app.db.migrations import MIGRATIONS as discovered_versions

    versions = [migration.version for migration in discovered_versions]
    assert versions == [f"{number:04d}" for number in range(1, len(versions) + 1)], versions


def test_the_new_table_is_discovered_by_the_runner_without_touching_its_source():
    """0011 靠既有发现规则就能被认出来：没改 app/db/migrations.py 一个字节。"""
    from app.db.migrations import MIGRATIONS as discovered, _DEFAULT_MIGRATIONS_DIR

    migration = next(item for item in discovered if item.version == "0011")

    assert migration.name == "document_activity_signals"
    assert str(_DEFAULT_MIGRATIONS_DIR).replace("\\", "/").endswith("migrations")
    assert "document_activity_signals" in migration.sql
    assert migration.sql.count("CREATE TABLE") == 1, "一版只建这张表，不顺手改别的表"


def test_the_0011_file_carries_the_five_columns_and_nothing_else():
    """列清单一枚不多、一枚不少：多一列就可能多一个隐私面。"""
    key, counters, columns = _table_contract()

    assert key == "filename"
    assert counters == ["accepted_count", "rejected_count"]
    assert set(columns) == {key, *counters, "first_signal_at", "last_signal_at"}

# --------------------------------------------- 退避与超时：fail-open 必须是便宜的 open
def test_a_failed_read_is_backed_off_instead_of_retried_on_every_question(monkeypatch):
    """库连不上时，一个窗口内只探一次。

    这条不是装饰：不缓存失败态的话，每一次问答都要重付一趟连接超时（本机实测 2.03s），
    一枚排序信号就把整站拖慢——那比先验失效严重得多。断言的是**读取方被调用几次**。
    """
    calls = []

    def counting_broken_reader():
        calls.append(1)
        raise RuntimeError("connection refused")

    monkeypatch.delenv(rt.ACTIVITY_PRIOR_ENV, raising=False)
    rt.reset_activity_priors()

    assert rt.activity_priors(row_reader=counting_broken_reader, now=100.0) == {}
    assert len(calls) == 1, "注入 reader 的调用恒真跑，不享退避"

    assert rt.activity_priors(now=100.5) == {}
    assert len(calls) == 1, "注入的 reader 每次都跑，这一条与生产路径无关"

    # 生产路径（不注入 reader）：默认读取方被换成会计数的坏读取方。
    monkeypatch.setattr(rt, "_read_activity_signal_rows", counting_broken_reader)
    rt.reset_activity_priors()
    before = len(calls)
    assert rt.activity_priors(now=200.0) == {}
    assert len(calls) == before + 1, "第一次问答要真去探一次"
    assert rt.activity_priors(now=200.5) == {}
    assert rt.activity_priors(now=204.0) == {}
    assert len(calls) == before + 1, "退避窗口内不许再探：" + str(len(calls) - before) + " 次"
    diagnostics = rt.activity_prior_diagnostics()
    assert diagnostics["source"] == "error" and diagnostics["reason"] == "RuntimeError", (
        "退避不能把失败抹平成" + chr(34) + "没有信号" + chr(34) + "：观测面仍要说是 error"
    )

    assert rt.activity_priors(now=200.0 + rt.ACTIVITY_PRIOR_RETRY_SECONDS + 1) == {}
    assert len(calls) == before + 2, "窗口过去之后必须恢复重试，否则一次故障就永久静音"
    rt.reset_activity_priors()


def test_the_configured_connect_timeout_beats_our_default(monkeypatch):
    """业主在 DATABASE_URL 里写了 connect_timeout 就用他的，没写才补上界。

    钉的是"补不补"，不是"补成几"：把调用方的数字覆盖掉，等于让排序这一路自己去决定
    一次故障要挂多久。
    """
    import sys
    from types import ModuleType

    seen = []

    fake = ModuleType("psycopg")

    class _Cursor:
        def execute(self, *args, **kwargs):
            return self

        def fetchall(self):
            return []

    class _Connection:
        def __enter__(self):
            return _Cursor()

        def __exit__(self, *exc):
            return False

    def connect(conninfo, **kwargs):
        seen.append((conninfo, kwargs))
        return _Connection()

    fake.connect = connect
    monkeypatch.setitem(sys.modules, "psycopg", fake)

    pinned = "postgresql://u@127.0.0.1:1/db?connect_timeout=1"
    monkeypatch.setenv("DATABASE_URL", pinned)
    assert rt._read_activity_signal_rows() == []
    assert seen[-1] == (pinned, {}), "业主写了超时，本模块一个字都不许加"

    monkeypatch.setenv("DATABASE_URL", "postgresql://u@127.0.0.1:1/db")
    assert rt._read_activity_signal_rows() == []
    conninfo, kwargs = seen[-1]
    assert kwargs == {}, "超时随 conninfo 走，不走 kwarg"
    assert conninfo.endswith("connect_timeout=" + str(rt.ACTIVITY_PRIOR_CONNECT_TIMEOUT_SECONDS)), conninfo

# ------------------------------- 第二层护栏的独立钉子：extra=forbid 自己也要站得住
def test_the_request_model_itself_has_no_place_for_content_fields():
    """两道护栏各自有钉子：这道不依赖 _reject_extra_fields，单独摘掉它也会红。

    上一版的反证说明了一件事——只摘未登记字段的拒绝那一步，走私用例仍绿，因为 pydantic
    的 extra="forbid" 独立兜着。既然它是**第二道**而不是装饰，就得有自己的用例，
    否则谁把它改成 extra="ignore" 都没人拦。
    """
    from pydantic import ValidationError

    smuggled = _smuggled_text()

    assert feedback.DocumentFeedback.model_config["extra"] == "forbid", (
        "请求模型必须拒收未登记字段，不是忽略它"
    )
    with pytest.raises(ValidationError):
        feedback.DocumentFeedback.model_validate(
            {"filename": "finance-q3.txt", "signal": "accepted", "note": smuggled}
        )
    # 唯一能过校验的形状，就是"文件名 + 信号"两枚；模型里根本没有装正文的字段。
    assert set(feedback.DocumentFeedback.model_fields) == set(feedback.ALLOWED_FIELDS)
    for field_name in feedback.DocumentFeedback.model_fields:
        assert field_name not in ("query", "question", "note", "content", "answer", "text")

# ------------------------ R152 收尾补的三枚钉子：这三格形状在接手时都没有用例挡着
def test_a_malformed_hit_travels_through_instead_of_breaking_the_whole_search():
    """两遍循环必须共用一把尺：非字典命中在第一遍被 isinstance 挡过，第二遍也得挡。

    rank_hits_by_activity 是在 _apply_activity_prior 那个 try **之外**调用的，所以第二遍漏挡
    时，一条畸形命中就会抛 AttributeError 把整条检索打断——这恰好逆着本文件判据②那半句
    fail-open：读不到计数排序不动，来了一条怪命中反倒让问答整个失败。
    """
    hits = _hits("a.txt") + ["not-a-dict"] + _hits("finance-q3.txt")
    ranked = rt.rank_hits_by_activity(hits, _priors())

    shape = [hit if not isinstance(hit, dict) else hit["source"] for hit in ranked]
    assert shape == ["finance-q3.txt", "a.txt", "not-a-dict"], shape
    assert len(ranked) == len(hits), "一个候选都不许多、都不许少"
    assert all("activity_prior" in hit for hit in ranked if isinstance(hit, dict)), (
        "注记只长在字典命中上，畸形那一条原样带着走"
    )

    # 同一个形状再经 _apply_activity_prior 走一遍：检索器交回的是排好序的表，不是异常。
    instance = _retriever(("a.txt", "finance-q3.txt"), _priors())
    again = _hits("a.txt") + ["not-a-dict"] + _hits("finance-q3.txt")
    applied = instance._apply_activity_prior(again)
    assert [h if not isinstance(h, dict) else h["source"] for h in applied] == shape


def test_a_disputed_document_scores_zero_and_stays_separable_only_in_the_counts():
    """分开记两列买到的是「可分辨」，不是「不同权重」。

    净值 0 有两种来历（没人打过点 / 一人一半），而先验对两者给的分值相同（都是 0.0），
    所以排序层面它们没有区别；区别只在计数本身——整批都是争议样本时交回的还是同一个对象
    （连键都不长），同批里另有信号时那一条的注记会带着 5/5 出来。上一版 0011 的注释把这件
    事说成了后者另有权重，那种话留在库里就会长出一段照它写的代码。
    """
    disputed = rt.activity_prior_value({"accepted": 5, "rejected": 5})
    assert disputed == 0.0, "净值 0 的先验必须是 0：不许偷偷给争议样本加或减"
    assert disputed == rt.activity_prior_value(None)
    assert disputed == rt.activity_prior_value({"accepted": 0, "rejected": 0})

    alone = _hits("disputed.txt", "quiet.txt")
    only_disputed = {"disputed.txt": {"accepted": 5, "rejected": 5}}
    assert rt.rank_hits_by_activity(alone, only_disputed) is alone, "全是净值 0 与无信号同形"

    mixed = _hits("disputed.txt", "adopted.txt")
    priors = dict(only_disputed)
    priors["adopted.txt"] = {"accepted": 4, "rejected": 0}
    ranked = rt.rank_hits_by_activity(mixed, priors)
    note = next(hit for hit in ranked if hit["source"] == "disputed.txt")["activity_prior"]
    assert (note["accepted"], note["rejected"], note["adjustment"]) == (5, 5, 0.0), (
        "计数读得回来，分值仍是 0：可分辨不等于被加权"
    )

    sql = (MIGRATIONS / "0011_document_activity_signals.sql").read_text(encoding="utf-8")
    assert "确有争议" not in sql, "注释不得声称争议样本另有一档分值"
    assert "activity_prior_value" in sql, "注释要指名这件事落在哪段代码上，不让人猜"


def test_a_signal_written_through_the_endpoint_is_visible_to_the_very_next_read(monkeypatch):
    """回执与下一问不许是两本账：POST 交回刚写的计数，快照就得在这一刻作废。

    写侧走库，读侧走 retriever 那份最长 30 秒的整表快照。不作废的话，同一个人刚看见
    "accepted_count: 1"，下一问却仍按打点之前那份账在排，GET 也照旧报 0——这不是"有点
    延迟"而是自相矛盾，判据②要的"与现状一致"也经不起这种对照。
    """
    table = _InMemorySignals()
    client = _staff_client(monkeypatch, USERS, {"finance-q3.txt": DOC_ROW}, table.connection())
    rt.reset_activity_priors()
    monkeypatch.setattr(rt, "_read_activity_signal_rows", table.snapshot)
    monkeypatch.delenv(rt.ACTIVITY_PRIOR_ENV, raising=False)

    # 先问一次，把空账快照填进缓存——这就是那 30 秒窗口的起点。
    assert rt.activity_priors() == {}
    posted = _post(client, {"filename": "finance-q3.txt", "signal": "accepted"})
    assert posted.status_code == 200, posted.text
    assert posted.json()["accepted_count"] == 1

    fresh = rt.activity_priors()
    assert fresh == {"finance-q3.txt": {"accepted": 1, "rejected": 0}}, (
        "写成功之后快照必须作废，否则下一问读到的还是打点之前那份账"
    )
    read_back = client.get(
        "/api/v1/feedback/document",
        params={"filename": "finance-q3.txt"},
        headers={"Authorization": "Bearer " + create_token("alice")},
    )
    assert read_back.status_code == 200, read_back.text
    assert read_back.json()["accepted_count"] == 1, "GET 与刚才那枚回执必须报同一个数"
    rt.reset_activity_priors()
