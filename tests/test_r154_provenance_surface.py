"""R154：出处面三格补齐（跟进单 §79 第三条）。

判据对应关系（三格各自一枚具名反证，不许一条大用例盖三格）：

- ① ``_document_source_row`` 把证据袋里已有的 ``excerpt`` 抄进 sources 行：
  ``test_excerpt_is_carried_from_the_evidence_bag_onto_the_sources_row``（搬运真值）/
  ``test_the_excerpt_on_the_wire_belongs_to_a_row_this_principal_may_see``（泄漏面）/
  ``test_evidence_without_an_excerpt_reports_an_empty_string_and_nothing_invented``（不造）
- ② 把 ``published_at`` 抄进 sources 行，并同时进 ``GET /documents/{f}/versions`` 的行：
  ``test_sources_row_carries_the_index_publication_moment`` /
  ``test_a_document_with_no_index_record_gets_no_published_at`` /
  ``test_a_retired_index_is_never_reported_as_an_effective_date`` /
  ``test_the_versions_endpoint_exposes_index_versions_published_at`` /
  ``test_a_version_that_was_never_indexed_carries_no_invented_date``
- ③ 缓存命中腿也交来源清单，让 ``cached-stale`` 在结构上可能成立：
  ``test_a_cached_hit_turn_hands_over_the_same_source_rows`` 等七枚

取证全程离线：假编排 + ``app/common/cache.py`` 自己的内存回退实现 + 临时目录里的真
``IndexRegistry``。不打模型、不连库、不动 ``frontend/**``（读取位由 R150 接好，本单只把
后端那三格补上，前端一个字节都不改；键名同源由
``test_the_two_new_keys_are_named_exactly_as_the_frontend_reads_them`` 钉住）。
"""
import asyncio
import json
import re
from pathlib import Path

import pytest

from tests.test_sse_sources import (
    FINANCE_DOC,
    HR_DOC,
    SECRET_DOC,
    doc_agent_result,
    doc_state,
    event_names,
    events,
    fake_retriever_hits,
    finance_principal,
    sources_event,
)

QUESTION = "差旅报销上限是多少？"
ANSWER = "财务部差旅上限 2000 元。"
HR_EXCERPT = "HR 薪酬带宽表。"
SECRET_EXCERPT = "董事会纪要（机密）。"


def _request(principal):
    return type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": principal.username})()},
    )()


def _memory_cache(monkeypatch):
    """换成进程内那套 Redis 回退实现：REDIS_URL 没配时生产上跑的就是它。"""
    from app.common import cache

    backend = cache._MemoryRedis()
    monkeypatch.setattr(cache, "_redis", backend)
    return backend


def _harness(monkeypatch, tmp_path, turns):
    """把 /ask 摘成离线件，但**不桩缓存**——判据③ 要的就是答案与它的证据快照真过一遍往返。

    ``turns`` 每被取走一枚就等于打了一次模型：命中腿不许动它，动了就说明那一轮根本没走缓存。
    与 ``tests/test_sse_sources.patch_offline`` 的区别只在这一处（那枚把缓存桩成了永不命中）。
    """
    from app.api.v1 import chat
    from app.storage.sessions import SessionRegistry

    backend = _memory_cache(monkeypatch)
    remaining = list(turns)

    def fake_stream(*_args, **_kwargs):
        assert remaining, "这一轮不该再打模型：缓存命中必须就地短路"
        return iter(remaining.pop(0))

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_a, **_k: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_a, **_k: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _sid, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}))
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.agents.orchestrator.check_interrupt", lambda _tid: None)
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))

    async def consume(response):
        parts = []
        async for chunk in response.body_iterator:
            parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        return "".join(parts)

    def ask(principal, message=QUESTION, session_id="r154"):
        response = asyncio.run(
            chat.ask(
                chat.AskRequest(message=message, session_id=session_id),
                http_request=_request(principal),
            )
        )
        return asyncio.run(consume(response))

    return chat, backend, remaining, ask


def _publish_index_version(tmp_path, monkeypatch, chat, *, filename=FINANCE_DOC, version=3, retirement=False):
    """真发一版索引给注册表（走 ``IndexRegistry`` 自己的发布路径），并把读数口指到这份文件。

    ``published_at`` 不是测试造出来的字符串：它是 ``IndexRegistry.publish`` 写进记录的那一笔，
    与 PG 镜像 ``mark_published`` 写进 ``index_versions`` 的是同一次发布的两个读数。
    """
    from app.rag.indexing import IndexRegistry, document_index_id, document_resource_version_id

    path = tmp_path / "index-versions.json"
    registry = IndexRegistry(path)
    created = registry.create_version(
        index_id=document_index_id(filename),
        source_version_id=document_resource_version_id(filename, version),
        backend="chroma",
        chunk_count=0 if retirement else 1,
        checksum="a" * 64,
        retirement=retirement,
    )
    published = registry.publish(created.index_version_id)
    monkeypatch.setattr(chat, "default_metadata_path", lambda: str(path))
    return registry, published


# ------------------------------------------------------------------ 判据①：命中句
def test_excerpt_is_carried_from_the_evidence_bag_onto_the_sources_row():
    """证据袋里那一格是什么，sources 行里就是什么——搬运，不加工、不反推。"""
    from app.api.v1 import chat

    hit = {
        "content": "单笔限额 5000 元以内据实报销，超过部分须事前书面审批。",
        "source": FINANCE_DOC,
        "chunk_index": 0,
        "classification": 2,
        "department": "finance",
    }
    evidence = doc_agent_result("doc", [hit], ANSWER)["evidence"][0]
    assert evidence["excerpt"] == hit["content"], "证据袋本身没收下这一段，本用例就没有可搬的东西"

    row = chat._document_source_row("doc", evidence)

    assert row["excerpt"] == hit["content"]


def test_an_excerpt_longer_than_the_evidence_bag_cap_arrives_capped_not_extended():
    """400 字这一刀是工具边界上落的（``evidence._EXCERPT_LIMIT``），出口不许把它接长。

    出口要是自己再拼一段正文，"命中句"就成了半截实测半截编造，比整格缺失更难查。
    """
    from app.agents import evidence as evidence_module
    from app.api.v1 import chat

    long_content = "限" * 900
    hits = [
        {
            "content": long_content,
            "source": FINANCE_DOC,
            "chunk_index": 0,
            "classification": 2,
            "department": "finance",
        }
    ]
    evidence = doc_agent_result("doc", hits, ANSWER)["evidence"][0]
    assert evidence["excerpt"] == long_content[: evidence_module._EXCERPT_LIMIT]

    row = chat._document_source_row("doc", evidence)

    assert len(row["excerpt"]) == evidence_module._EXCERPT_LIMIT
    assert row["excerpt"] == evidence["excerpt"]


def test_evidence_without_an_excerpt_reports_an_empty_string_and_nothing_invented():
    """证据袋没记摘录 ⇒ 空串。不许拿 ``content_sha256``、文件名或正文反推一句凑上。"""
    from app.api.v1 import chat

    evidence = {
        "source_type": "document",
        "source_name": FINANCE_DOC,
        "source_id": f"{FINANCE_DOC}#chunk=0",
        "locator": {"chunk_index": 0},
        "metadata": {"classification": 2, "department": "finance", "content_sha256": "0" * 64},
        "permission_checked": True,
        "provenance_status": "verified",
    }

    row = chat._document_source_row("doc", evidence)

    assert row["excerpt"] == ""
    assert row["content_sha256"] == "0" * 64, "摘录缺席时，别的格也不许顺手挪位置"


def test_the_excerpt_on_the_wire_belongs_to_a_row_this_principal_may_see(monkeypatch, tmp_path):
    """上屏证据：命中句真的随 sources 事件发出去了；被拒那两条的摘录连 raw body 都不许有。"""
    _chat, _backend, _remaining, ask = _harness(monkeypatch, tmp_path, [[doc_state(fake_retriever_hits())]])

    body = ask(finance_principal())

    rows = sources_event(body)["data"]["sources"]
    assert [row["source"] for row in rows] == [FINANCE_DOC]
    assert rows[0]["excerpt"] == "财务部差旅报销上限 2000 元。"
    assert HR_DOC not in body and SECRET_DOC not in body
    assert HR_EXCERPT not in body, "被拒来源的命中句泄漏进了流"
    assert SECRET_EXCERPT not in body, "被拒来源的命中句泄漏进了流"


# ------------------------------------------------------------------ 判据②：生效日期
def _source_row(chat, filename=FINANCE_DOC):
    """一枚从证据袋走过来的正常出处行（不含 published_at）。"""
    hits = [
        {
            "content": "财务部差旅报销上限 2000 元。",
            "source": filename,
            "chunk_index": 0,
            "classification": 2,
            "department": "finance",
        }
    ]
    evidence = doc_agent_result("doc", hits, ANSWER)["evidence"][0]
    row = chat._document_source_row("doc", evidence)
    assert "published_at" not in row, "出生时不该带这一格：它是出口侧补上去的"
    return row


def test_sources_row_carries_the_index_publication_moment(monkeypatch, tmp_path):
    """②sources：行的 ``published_at`` 逐字等于注册表里那一版的发布时间。"""
    from app.api.v1 import chat

    _version_record, published = _publish_index_version(tmp_path, monkeypatch, chat)
    row = _source_row(chat)

    chat._stamp_source_publications({row["source_id"]: row})

    assert row["published_at"] == published.published_at
    assert published.published_at, "注册表自己都没记时间，这条取证就没有内容"


def test_a_document_with_no_index_record_gets_no_published_at(monkeypatch, tmp_path):
    """没有索引发布记录 ⇒ 这一格缺席。宁可不带，不许拿 ``created_at`` 或今天凑一个数。"""
    from app.api.v1 import chat

    monkeypatch.setattr(chat, "default_metadata_path", lambda: str(tmp_path / "absent.json"))
    row = _source_row(chat)
    keys_before = sorted(row)

    chat._stamp_source_publications({row["source_id"]: row})

    assert "published_at" not in row
    assert sorted(row) == keys_before, "查不到就得一个字节都不动"
    assert "created_at" not in row, "拿别的列顶替生效日期，是本单最贵的一种造假"


def test_a_retired_index_is_never_reported_as_an_effective_date(monkeypatch, tmp_path):
    """墓碑记录的是"什么时候被撤下"，把它当生效日期报出去就是一句假话。"""
    from app.api.v1 import chat

    _version_record, tombstone = _publish_index_version(tmp_path, monkeypatch, chat, retirement=True)
    assert tombstone.retirement and tombstone.published_at
    row = _source_row(chat)

    chat._stamp_source_publications({row["source_id"]: row})

    assert "published_at" not in row, "撤下时间被卖成了上线时间"


def test_the_index_search_is_bounded_to_document_index_ids(monkeypatch, tmp_path):
    """配对用 ``document_index_id(filename)``：另一族资源（数据集）的同名记录不算数。"""
    from app.api.v1 import chat
    from app.rag.indexing import IndexRegistry

    path = tmp_path / "index-versions.json"
    registry = IndexRegistry(path)
    foreign = registry.create_version(
        index_id="dataset:" + FINANCE_DOC,
        source_version_id="whatever",
        backend="chroma",
        chunk_count=1,
        checksum="b" * 64,
    )
    registry.publish(foreign.index_version_id)
    monkeypatch.setattr(chat, "default_metadata_path", lambda: str(path))
    row = _source_row(chat)

    chat._stamp_source_publications({row["source_id"]: row})

    assert "published_at" not in row, "把数据集索引的发布时间安到一份文档头上，是两个不同的事实"


def test_an_unreadable_registry_costs_a_field_not_the_endpoint(monkeypatch, tmp_path):
    """注册表读不出来（写到一半 / JSON 坏掉）时，出口照常工作，只是这一格不说。"""
    from app.api.v1 import chat

    broken = tmp_path / "index-versions.json"
    broken.write_text("{not json at all", encoding="utf-8")
    monkeypatch.setattr(chat, "default_metadata_path", lambda: str(broken))
    _version_rows(chat, monkeypatch, [_stored_version()])
    row = _source_row(chat)

    chat._stamp_source_publications({row["source_id"]: row})
    payload = asyncio.run(chat.document_version_history("policy.txt", _request(finance_principal())))

    assert "published_at" not in row
    assert payload["versions"], "读不出一本索引账，不该把版本历史一起没收"


def _version_rows(chat, monkeypatch, rows):
    monkeypatch.setattr(chat, "list_document_versions", lambda _filename, *_a, **_k: list(rows))


def _stored_version(filename="policy.txt", version=3):
    return {
        "filename": filename,
        "version": version,
        "department": "finance",
        "classification": 2,
        "owner_id": "alice",
        "storage_path": f"{filename}__v{version}.txt",
        "size_bytes": 12,
        "created_at": "2026-09-14T09:00:00+08:00",
    }


def test_the_versions_endpoint_exposes_index_versions_published_at(monkeypatch, tmp_path):
    """②versions：``index_versions.published_at`` 从这张出口开始才有 API 可读。"""
    from app.api.v1 import chat

    _version_record, published = _publish_index_version(tmp_path, monkeypatch, chat, filename="policy.txt", version=3)
    _version_rows(chat, monkeypatch, [_stored_version()])

    payload = asyncio.run(chat.document_version_history("policy.txt", _request(finance_principal())))

    row = payload["versions"][0]
    assert row["version"] == 3
    assert row["published_at"] == published.published_at
    assert row["created_at"] == "2026-09-14T09:00:00+08:00", "两列各说各的事，一枚都不许覆盖另一枚"


def test_a_version_that_was_never_indexed_carries_no_invented_date(monkeypatch, tmp_path):
    """注册表里只有 v2 的发布记录时，v3 那一行不许借用 v2 的时间。"""
    from app.api.v1 import chat

    _version_record, published_v2 = _publish_index_version(tmp_path, monkeypatch, chat, filename="policy.txt", version=2)
    _version_rows(chat, monkeypatch, [_stored_version(version=3)])

    payload = asyncio.run(chat.document_version_history("policy.txt", _request(finance_principal())))

    row = payload["versions"][0]
    assert "published_at" not in row, "相邻版本的日期借过来，界面上就是一条读不出真值的假账"
    assert published_v2.published_at


def test_the_catalog_list_endpoint_keeps_its_own_shape(monkeypatch, tmp_path):
    """本单只往 ``/documents/{f}/versions`` 里加字段：``/documents/catalog`` 那枚出口不许顺手改。

    两处都走同一个 ``public_document_row`` 投影，判据点名的只有 versions 那一枚；另一枚出口
    今天不发布"生效日期"，改了就是把一次订正变成一次全目录的载荷变更。
    """
    from app.api.v1 import chat

    _publish_index_version(tmp_path, monkeypatch, chat, filename="policy.txt", version=3)
    monkeypatch.setattr(chat, "current_documents", lambda *_a, **_k: [_stored_version()])

    listed = asyncio.run(chat.list_document_catalog(_request(finance_principal())))

    assert [row["filename"] for row in listed["documents"]] == ["policy.txt"]
    assert all("published_at" not in row for row in listed["documents"])


# ------------------------------------------------------------------ 判据③：缓存腿交清单
def _scope_for(principal):
    from app.common.cache import answer_cache_scope

    return answer_cache_scope(principal, username=principal.username)


def _seed_answer(principal, answer=ANSWER):
    """按 R35 之前的形状写一条答案缓存：只有 ``{answer, created_at}``，没有清单。

    必须在 ``_harness`` **之后**调用：那枚夹具会换上一块新的内存缓存后端，先写就被冲掉。
    """
    from app.common import cache

    cache.cache_answer(QUESTION, answer, scope=_scope_for(principal))
    return _scope_for(principal)


def _seed_manifest(chat, question, scope, text):
    """绕过 ``_cache_source_manifest`` 直接写一条清单条目：形状由用例说了算。"""
    from app.common import cache

    cache.cache_answer(chat._evidence_manifest_key(question), text, scope=scope)


def test_a_cached_hit_turn_hands_over_the_same_source_rows(monkeypatch, tmp_path):
    """③：命中的那一轮也发 canonical ``sources``，legacy 三枚帧的次序与字面原样不动。"""
    _chat, _backend, remaining, ask = _harness(monkeypatch, tmp_path, [[doc_state(fake_retriever_hits())]])
    caller = finance_principal()

    live = ask(caller)
    hit = ask(caller)

    assert remaining == [], "第二轮必须命中缓存，一枪都不许打"
    assert event_names(live).count("sources") == 1
    assert event_names(hit) == ["status", "text", "sources", "done"]
    assert [row["source"] for row in sources_event(hit)["data"]["sources"]] == [FINANCE_DOC]
    assert sources_event(hit)["data"] == sources_event(live)["data"], (
        "同一份证据的两次下发必须逐键相等：命中腿偷偷少发一格，前端就少读一格"
    )
    payload = next(data for name, data in events(hit) if name == "text")
    assert payload["cached"] is True and payload["cache_generated_at"] and payload["cache_note"], (
        "R35 那三枚字段是缓存那张脸的读数，新加一枚事件不许把它们挤掉"
    )


def test_a_cache_entry_from_before_the_manifest_says_nothing_at_all(monkeypatch, tmp_path):
    """R154 之前写下的条目读不出清单 ⇒ 那一轮**不发** sources。

    这是判据点名要的那一格的具名钉：界面落到 ``provenance.js::cacheFace`` 的第四态
    ``cached-unknown``（"这一轮的回答没有再交出来源清单，是否改版无从核对"），而不是第三态
    ``cached``（"已核对过，确实没改版"）。发一枚空清单冒充核对过，就是把"没查到"说成
    "查过了，没有"。
    """
    from app.api.v1 import chat

    _chat, _backend, remaining, ask = _harness(monkeypatch, tmp_path, [])
    scope = _seed_answer(finance_principal())

    body = ask(finance_principal())

    assert remaining == [], "这一轮是缓存命中，不许打模型"
    assert event_names(body) == ["status", "text", "done"]
    assert "sources" not in body
    assert chat._cached_source_manifest(QUESTION, scope) is None


@pytest.mark.parametrize("shape", ["{not json at all", '{"rows": []}', "[]", '"一段话"'])
def test_a_manifest_that_cannot_be_read_is_not_served_as_an_empty_one(monkeypatch, tmp_path, shape):
    """清单坏了 / 形状不认 / 空表：一律当"没有清单"，命中腿安静，正文与缓存标注照发。"""
    from app.api.v1 import chat

    _chat, _backend, _remaining, ask = _harness(monkeypatch, tmp_path, [])
    scope = _seed_answer(finance_principal())
    _seed_manifest(chat, QUESTION, scope, shape)

    body = ask(finance_principal())

    assert "sources" not in event_names(body)
    assert event_names(body) == ["status", "text", "done"]
    assert json.loads(next(f.split("data: ", 1)[1] for f in body.split("\n\n") if f.startswith("event: text")))["cached"] is True
    assert chat._cached_source_manifest(QUESTION, scope) is None


def test_a_turn_with_no_documents_stores_no_manifest(monkeypatch):
    """没有文档来源的一轮不存空表：界面上两种下发画的是同一张脸，多存一格只是多占一格。"""
    from app.api.v1 import chat

    backend = _memory_cache(monkeypatch)
    scope = _scope_for(finance_principal())

    assert chat._cache_source_manifest(QUESTION, scope, {}) is False
    assert backend._kv == {}, "本轮没有可交的证据，就不该留下任何条目"


def test_the_hit_leg_reauthorizes_the_manifest_it_read(monkeypatch, tmp_path):
    """清单里存的是**过滤前**的证据行；命中这一轮必须重新过一遍 ``scope.allows``。"""
    from app.api.v1 import chat

    hits = [
        {
            "content": "财务部差旅报销上限 2000 元。",
            "source": FINANCE_DOC,
            "chunk_index": 0,
            "classification": 2,
            "department": "finance",
        },
        {
            "content": HR_EXCERPT,
            "source": HR_DOC,
            "chunk_index": 1,
            "classification": 1,
            "department": "hr",
        },
    ]
    caller = finance_principal()
    rows = {}
    for evidence in doc_agent_result("doc", hits, ANSWER)["evidence"]:
        row = chat._document_source_row("doc", evidence)
        rows[row["source_id"]] = row
    assert len(rows) == 2, "两条命中都要进清单，否则本用例没有可越权的东西"

    _chat, _backend, _remaining, ask = _harness(monkeypatch, tmp_path, [])
    scope = _seed_answer(caller)
    assert chat._cache_source_manifest(QUESTION, scope, rows) is True

    body = ask(caller)

    data = sources_event(body)["data"]
    assert [row["source"] for row in data["sources"]] == [FINANCE_DOC]
    assert data["hit_count"] == 1
    assert data["unauthorized_count"] == 1, "当年检到两条、这一轮一条不给看，这个数要重算而不是照抄"
    assert HR_DOC not in body and HR_EXCERPT not in body


def test_the_manifest_is_bound_to_the_answers_own_scope(monkeypatch):
    """清单继承答案那把作用域尺子：换一个授权输入，连证据快照都读不出来。"""
    from app.api.v1 import chat
    from app.common.identity import Principal

    _memory_cache(monkeypatch)
    owner = finance_principal()
    other = Principal.from_user({"id": "carol", "username": "carol", "role": "manager", "department": "hr"})
    assert _scope_for(owner) != _scope_for(other)
    row = _source_row(chat)
    rows = {row["source_id"]: row}
    assert chat._cache_source_manifest(QUESTION, _scope_for(owner), rows) is True

    assert chat._cached_source_manifest(QUESTION, _scope_for(other)) is None, "跨作用域读到了别人的证据"
    assert chat._cached_source_manifest(QUESTION, _scope_for(owner)) == rows, (
        "反向对照：本人作用域必须读得回来，否则上面那条 0 命中是靠谁都查不到刷出来的假绿"
    )


def test_the_manifest_rows_keep_excerpt_and_published_at(monkeypatch, tmp_path):
    """三格在缓存这一条腿上同时成立：快照里的行既带命中句，也带当年的生效日期。"""
    from app.api.v1 import chat

    _publish_index_version(tmp_path, monkeypatch, chat)
    _chat, _backend, _remaining, ask = _harness(monkeypatch, tmp_path, [
        [doc_state(fake_retriever_hits())],
    ])
    caller = finance_principal()

    live = ask(caller)
    hit = ask(caller)

    live_rows = sources_event(live)["data"]["sources"]
    hit_rows = sources_event(hit)["data"]["sources"]
    assert live_rows and hit_rows
    assert hit_rows == live_rows
    for row in hit_rows:
        assert row["excerpt"] == "财务部差旅报销上限 2000 元。"
        assert row["published_at"], "快照里的生效日期丢了，cached-stale 就没有可比的那一头"


# ---------------------------------------------------------------- 键名同源（不改前端）
def test_the_two_new_keys_are_named_exactly_as_the_frontend_reads_them(monkeypatch, tmp_path):
    """前端读取位是 R150 接好的（``frontend/src/lib/sessions.js::sourceRowFromWire``）。

    本单不许改前端来满足判据，那等于把判据绕过去；反过来，后端自己新造一枚键名
    （``hit_sentence`` / ``effective_date``）前端也读不到。所以这里从前端现读那两行读取位，
    把键名钉成同源：前端改读取位、或后端改发射键名，哪一边先动这枚钉都红。
    """
    from app.api.v1 import chat

    repo = Path(__file__).resolve().parents[1]
    source = (repo / "frontend" / "src" / "lib" / "sessions.js").read_text(encoding="utf-8")
    body = source[source.index("function sourceRowFromWire") :]
    body = body[: body.index("\n}")]
    lines = [line.strip() for line in body.splitlines()]
    excerpt_slot = next(line for line in lines if line.startswith("excerpt:"))
    date_slot = next(line for line in lines if line.startswith("effectiveDate:"))
    assert re.findall(r"raw\.(\w+)", excerpt_slot) == ["excerpt", "content"], excerpt_slot
    assert "published_at" in re.findall(r"raw\.(\w+)", date_slot), date_slot

    _publish_index_version(tmp_path, monkeypatch, chat)
    row = _source_row(chat)
    chat._stamp_source_publications({row["source_id"]: row})

    assert "excerpt" in row and "published_at" in row


# ------------------------------------------------------------------ 线上端点证据
def test_the_hit_leg_manifest_survives_a_real_asgi_round_trip(monkeypatch, tmp_path):
    """命中腿那枚新事件真过一遍 ASGI 栈（中间件、编码、流式），不是只在 in-process 字面上成立。

    与 ``tests/test_sse_sources.test_sources_event_reaches_a_real_http_client_over_asgi_transport``
    同一招式：``httpx.ASGITransport`` + ``app.main.app``，把整棵应用当成收端。第二问与第一问
    同一个账号、同一个问题文本 ⇒ 落在答案缓存上，读的就是判据③ 那条通道。
    """
    import httpx

    from app.api.v1 import chat
    from app.common.auth import create_token
    from app.storage.sessions import SessionRegistry

    backend = _memory_cache(monkeypatch)
    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_a, **_k: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_a, **_k: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _sid, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.agents.orchestrator.check_interrupt", lambda _tid: None)
    monkeypatch.setattr(
        "app.agents.orchestrator.run_with_stream",
        lambda *_a, **_k: iter([doc_state(fake_retriever_hits())]),
    )

    async def fetch(client):
        async with client.stream(
            "POST",
            "/api/v1/ask",
            json={"message": QUESTION, "session_id": "r154-asgi"},
            headers={"Authorization": f"Bearer {create_token('admin')}"},
        ) as response:
            assert response.status_code == 200, await response.aread()
            return "\n".join([line async for line in response.aiter_lines()])

    async def drive():
        transport = httpx.ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first = await fetch(client)
            second = await fetch(client)
        return first, second

    first, second = asyncio.run(drive())

    assert "event: sources" in first, "实时那一腿本来就该有来源事件"
    assert "event: sources" in second, "走真栈的命中腿没交出来源清单"
    data = sources_event(second)["data"]
    assert data["hit_count"] == len(data["sources"]) >= 1
    assert all(row["excerpt"] for row in data["sources"]), "命中句在真栈上被吃掉了一格"
    assert backend._kv, "内存缓存后端没落下任何东西，这一轮就不是缓存命中"