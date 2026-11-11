# -*- coding: utf-8 -*-
r"""R46 差格 a · 写口与越权——点击／浏览那半张单的后端判据①与③。

判据原文（派工词要求先把全文摘出来再动手，这里连同交工纸一起留一份）：

- 计划书 §5.2 的 R46 那一行（跟进单 2026-09-15 L1033 逐字抄录在册）：
  | **R46** | 活动信号回填排序（采纳/驳回/点击 → 相关度先验；对齐 contracts.py:157
  score_type 已备枚举） | ① 有信号后排序变化可测；② 无信号时与现状一致；
  ③ 隐私：只存计数不存内容 | 不得把用户问题原文写进新表 |
- 跟进单 §21 给 R46 的判据即上面那一行，禁止项只有那一句：不得把用户问题原文写进新表。
- 差格 a 的欠账形状（计划书复核单 §3 代号 C 那行，跟进单 §141 R527 那节全文）：
  「新列（要 migration）＋新端点或同端点新枚举＋前端埋点＋先验源」，且
  「点击半张零实现且无具号认领单」。R521 的裁定把这一格记成「部分落地……点击半张零实现」，
  本单补的就是那半张。

业主已给的口径（10-03 派工词转述原话「那些信息本来就是假的在网上找的」）：演示数据与信号
本来就是合成数据，总控可自主裁定。⇒ 本单裁定：采纳／驳回＝在册 feedback 那两枚动作，
点击／浏览＝本件这半张；按人限额那一格属 D 组另一格，本单不做，欠业主的读数见交工纸。

分工：判据②（读侧派生）在 tests/test_r46c_engagement_prior.py，反证刀在
tests/test_r46c_counter_evidence_teeth.py，前端接线在
frontend/src/components/__tests__/r46c-source-engagement.test.js。

库与模型都不在场：PG 走注入的假连接（语义照 0019 的 CHECK 与 UNIQUE 演，不是照本件的期望演），
向量库与 embedding 一枚都不碰，身份走在册那枚 create_token。
"""
import json
import logging
from hashlib import sha256
import re
from contextlib import contextmanager
from pathlib import Path
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from app.agents.contracts import ErrorEnvelope
from app.api.v1 import feedback
from app.common.auth import create_token
from app.common.permissions import ACTION_VIEW
from app.main import app
from tests import _temp_edit_overlay as overlay
from test_r349_catalog_tail_ledger import CATALOG_TAIL_NAME, CATALOG_TAIL_VERSION

REPO = Path(__file__).resolve().parents[1]
MIGRATION_REL = "migrations/0019_" + CATALOG_TAIL_NAME + ".sql"
POST_URL = "/api/v1/feedback/engagement"
GET_URL = "/api/v1/feedback/engagement"

#: 载荷里唯一允许的四格（与 feedback.ENGAGEMENT_ALLOWED_FIELDS 判等，两处必须同值）。
ALLOWED_ENGAGEMENT_KEYS = {"filename", "event", "thread_id", "rank"}

#: 判据①的禁词：正文一段（真会出现在问答里的长句子，含中日韩与逗号）、部门值、密级值。
BODY_TEXT = "第三季度营收环比增长百分之十二，主因是华东渠道并表后的口径调整"
FORBIDDEN_TOKENS = (BODY_TEXT, "finance", "department", "classification", "answer", "excerpt")

USERS = {
    "alice": {"username": "alice", "role": "staff", "department": "finance"},
    "mallory": {"username": "mallory", "role": "staff", "department": "hr"},
    "boss": {"username": "boss", "role": "admin", "department": ""},
    "orphan": {"username": "orphan", "role": "staff", "department": ""},
}
DOC_ROW = {
    "filename": "finance-q3.txt",
    "version": 3,
    "classification": 1,
    "department": "finance",
    "owner_id": "alice",
}
GOOD_BODY = {"filename": "finance-q3.txt", "event": "click", "thread_id": "m1", "rank": 2}


class _EngagementStore:
    """假 PG：照 0019 的语句面与约束面演，不按本件的期望演。

    三条语句各认各的形状（INSERT／按 filename 的聚合／按 username 的账目读腿），
    表上那五条 CHECK 在这里逐条有对应的一次抛出：把库的语义抄成"永远接受"，
    本件的隐私钉就退化成自我认证。leak_foreign 那一格是给越权读腿用的——
    它模拟"读腿被改坏了、别人的行回来了"，用来验服务端那道结构闸，不验库。
    """

    def __init__(self):
        self.rows = []            # 每行一枚字典，与表里那六列同名
        self.calls = []           # (语句压平后的文本, 参数)
        self.committed = 0
        self.leak_foreign = False
        self._pending = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        self.calls.append((text, params))
        if text.startswith("INSERT INTO document_engagement_events"):
            self._pending = ("one", self._insert(params))
        elif "AS clicks" in text:
            name = params[0]
            self._pending = ("one", (
                self._count(name, "click"),
                self._count(name, "view"),
            ))
        elif text.startswith("SELECT username, thread_id"):
            self._pending = ("all", self._ledger(text, params))
        else:
            raise AssertionError("假 PG 只认 0019 那三条语句，收到：" + text[:80])
        return self

    def fetchone(self):
        kind, value = self._pending
        assert kind == "one", "这条语句不是取一行的那一条"
        return value

    def fetchall(self):
        kind, value = self._pending
        assert kind == "all", "这条语句不是取多行的那一条"
        return value

    def commit(self):
        self.committed += 1

    # ---------------------------------------------------------------- 表语义（照 0019）
    def _insert(self, params):
        username, thread_id, filename, rank, event = params
        self._assert_check(self._username_ok(username), "document_engagement_events_username_check")
        self._assert_check(
            self._thread_ok(thread_id), "document_engagement_events_thread_id_check")
        self._assert_check(self._filename_ok(filename), "document_engagement_events_filename_check")
        self._assert_check(
            isinstance(rank, int) and 1 <= rank <= 100,
            "document_engagement_events_rank_check")
        self._assert_check(event in ("click", "view"), "document_engagement_events_event_type_check")
        key = (username, thread_id, filename, event)
        if any(self._key_of(row) == key for row in self.rows):
            return None                      # ON CONFLICT DO NOTHING：那枚 UNIQUE 的落点
        row = {
            "username": username,
            "thread_id": thread_id,
            "filename": filename,
            "result_rank": rank,
            "event_type": event,
            "occurred_at": "2026-10-03T12:00:00+08:00",
        }
        self.rows.append(row)
        return len(self.rows)

    @staticmethod
    def _key_of(row):
        return (row["username"], row["thread_id"], row["filename"], row["event_type"])

    def _count(self, filename, event):
        return sum(1 for row in self.rows if row["filename"] == filename and row["event_type"] == event)

    def _ledger(self, text, params):
        username, limit = params
        if "WHERE username = %s" not in text:
            pool = list(self.rows)            # 读腿丢了那格过滤：流水全回来（反证 K4 的形状）
        else:
            pool = [row for row in self.rows if row["username"] == username]
        if self.leak_foreign:
            pool = pool + [{"username": "someone-else", "thread_id": "m9",
                               "filename": "other.txt", "result_rank": 1,
                               "event_type": "click", "occurred_at": "2026-10-03T12:00:00+08:00"}]
        return [tuple(row[column] for column in
                    ("username", "thread_id", "filename", "result_rank", "event_type", "occurred_at"))
                for row in pool[-int(limit):]]

    # ---------------------------------------------------------------- CHECK 逐条
    @staticmethod
    def _assert_check(ok, name):
        if ok:
            return
        import psycopg.errors
        raise psycopg.errors.CheckViolation("约束 " + name + " 被违反")

    @staticmethod
    def _username_ok(value):
        return isinstance(value, str) and 1 <= len(value) <= 64 and value == value.strip() \
            and not re.search(r"[\x00-\x1f\x7f]", value)

    @staticmethod
    def _thread_ok(value):
        return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_.:#-]{1,128}", value))

    @staticmethod
    def _filename_ok(value):
        return isinstance(value, str) and 1 <= len(value) <= 512 and value == value.strip() \
            and not re.search(r"[\x00-\x1f\x7f]", value)

    def aggregate(self):
        """排序侧那条聚合语句的读数：(filename, clicks, views) 元组列表，没有身份。"""
        names = sorted({row["filename"] for row in self.rows})
        return [(name, self._count(name, "click"), self._count(name, "view")) for name in names]


def _staff_client(monkeypatch, store, rows=None, audit=None):
    """身份、目录、PG、审计四件事全换假的；改动走 monkeypatch，用例结束自动还原。"""
    from app.common import auth as auth_module

    catalog = rows if rows is not None else {"finance-q3.txt": DOC_ROW}
    monkeypatch.setattr(auth_module, "get_user", lambda username: USERS.get(username))
    monkeypatch.setattr(
        feedback, "list_document_versions", lambda name: [catalog[name]] if name in catalog else []
    )
    monkeypatch.setattr(feedback, "_CONNECTION_FACTORY", lambda: store)
    if audit is not None:
        monkeypatch.setattr(feedback, "record_audit", audit)
    return TestClient(app)


def _post(client, payload, username="alice"):
    return client.post(POST_URL, headers={"Authorization": "Bearer " + create_token(username)}, json=payload)


def _get(client, username="alice", query=""):
    return client.get(
        GET_URL + query, headers={"Authorization": "Bearer " + create_token(username)}
    )


class _AuditRecorder:
    """替 record_audit 记账：只留调用形状，不给真审计落盘。"""

    def __init__(self):
        self.calls = []

    def __call__(self, principal, action, outcome, *, resource="", reason="", **kwargs):
        self.calls.append({
            "username": getattr(principal, "username", ""),
            "action": action,
            "outcome": outcome,
            "resource": resource,
            "reason": reason,
            "extra": kwargs,
        })


@contextmanager
def _feedback_logs():
    """抓 feedback 那一族日志：本件的日志钉不靠 caplog，反证窗里也能直接调那枚用例。"""
    logger = feedback.logger
    holder = []

    class _Handler(logging.Handler):
        def emit(self, record):
            holder.append(record.getMessage())

    handler = _Handler()
    previous = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield holder
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)

# ======================================= 判据① 写口：点击／浏览各落一行到新表，载荷只有形状
def test_the_table_has_no_column_that_could_hold_a_question():
    """禁止项＝「不得把用户问题原文写进新表」——钉在列清单上，不钉在清洗逻辑上。"""
    sql = overlay.authoritative_text(MIGRATION_REL)
    block = re.search(
        r"CREATE TABLE IF NOT EXISTS document_engagement_events\s*\((.*?)\n\);",
        sql,
        re.S,
    )
    assert block, "0019 里没有 document_engagement_events 的 CREATE TABLE 块"
    columns = {}
    for raw in block.group(1).split(chr(10)):
        line = raw.strip()
        if not line or line.startswith(("--", "CONSTRAINT")):
            continue
        name, _, rest = line.partition(" ")
        # 只认「列名 + 已知列类型」那一行：约束折行的续行（AND ... / CHECK ...）不算列。
        if rest.split(" ")[0] not in ("BIGINT", "TEXT", "SMALLINT", "TIMESTAMPTZ"):
            continue
        columns[name] = rest.split("CONSTRAINT")[0].strip()

    assert set(columns) == {
        "event_id", "username", "thread_id", "filename", "result_rank", "event_type", "occurred_at"
    }, columns
    for banned in ("query", "question", "prompt", "answer", "content", "text", "excerpt", "note",
                    "snippet", "department", "classification", "payload", "detail"):
        assert banned not in " ".join(columns), "新表里出现了装得下内容的列：" + banned
    # 文本列可以有，但每一枚都必须被形状钉死：event_type 是封闭枚举，thread_id 只认 id 字符集，
    # username 有长度与空白与控制字符三道闸，filename 有 512 上界。没有一格是"自由文本槽"。
    text_columns = sorted(name for name, kind in columns.items() if "TEXT" in kind.upper())
    assert text_columns == ["event_type", "filename", "thread_id", "username"], text_columns
    assert "length(filename) BETWEEN 1 AND 512" in sql, "key 列要有硬上界，否则原文整段塞得进文件名"
    assert "length(username) BETWEEN 1 AND 64" in sql
    assert "thread_id ~ '^[A-Za-z0-9_.:#-]{1,128}$'" in sql, (
        "题号那一格必须靠字符集把关：没有空格、没有换行、没有中日韩，问题原文结构上塞不进"
    )


def test_the_new_migration_is_the_ledger_tail_and_manifest_gained_exactly_one_line():
    """00 号只许用 0019，manifest 里只许加自己那一行（派工词的两枚同号死规矩）。"""
    assert CATALOG_TAIL_VERSION == "0019", CATALOG_TAIL_VERSION
    assert CATALOG_TAIL_NAME == "document_engagement_events", CATALOG_TAIL_NAME
    assert MIGRATION_REL.endswith("0019_document_engagement_events.sql"), MIGRATION_REL
    manifest = json.loads((REPO / "migrations" / "manifest.json").read_text(encoding="utf-8"))
    sql_files = sorted(p.name for p in (REPO / "migrations").glob("0*.sql"))
    assert sorted(manifest) == sql_files, (
        "manifest 的键清单必须与目录里的迁移一枚不差地对上：" + str(set(manifest) ^ set(sql_files))
    )
    # 与 app/db/migrations.py 同一口径：digest 取的是文本（通用换行）编成 UTF-8 的那笔字节，
    # 不是盘上带 CRLF 的原始字节——两把尺子必须能互相量到，否则这条钉永远是假红或假绿。
    normalised = (REPO / "migrations" / "0019_document_engagement_events.sql").read_text(encoding="utf-8")
    assert manifest["0019_document_engagement_events.sql"] == sha256(normalised.encode("utf-8")).hexdigest(), (
        "0019 的 digest 与盘上的字节不是同一笔——要么改过文件没改账，要么相反"
    )


def test_the_check_family_of_0019_pairs_up_with_the_one_of_0011():
    """R527 判据 3：0011 那族 CHECK 在 0019 逐条对等（非负／有界、去空、≤512、封闭枚举）。"""
    eleven = (REPO / "migrations" / "0011_document_activity_signals.sql").read_text(encoding="utf-8")
    nineteen = overlay.authoritative_text(MIGRATION_REL)
    assert "CHECK (accepted_count >= 0" in eleven and "CHECK (rejected_count >= 0" in eleven
    assert "CHECK (result_rank >= 1 AND result_rank <= 100)" in nineteen, (
        "名次那一格要有下界与上界：0011 的非负计数在这里换成有界的位次，一条都不许少"
    )
    assert "CHECK (event_type IN ('click', 'view'))" in nineteen, "事件类型是封闭枚举"
    assert "event_type = 'click'" in eleven or "accepted_count" in eleven
    for column in ("username", "filename"):
        assert column + " = btrim(" + column + ")" in nineteen, column + " 不许带首尾空白"
        assert column + " !~ '[[:cntrl:]]'" in nineteen, column + " 不许带控制字符"
    assert "UNIQUE (username, thread_id, filename, event_type)" in nineteen, (
        "一次动作＝一枚事件：这四格合起来才是那枚去重键，缺一格就能刷分"
    )


def test_the_write_statement_carries_five_shape_values_and_no_content(monkeypatch):
    """递给库的参数恰五枚：身份、题号、文档名、名次、动作码。没有一格放得下正文。"""
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    response = _post(client, GOOD_BODY)
    assert response.status_code == 200, response.text
    inserts = [call for call in store.calls if call[0].startswith("INSERT")]
    assert len(inserts) == 1, [call[0][:60] for call in store.calls]
    sql, params = inserts[0]
    assert params == ("alice", "m1", "finance-q3.txt", 2, "click"), params
    assert len(params) == 5, "五枚以外就是第六个能装东西的位置"
    assert sql.count("%s") == 5, sql
    assert "NOW()" in sql, "时刻由库生成，客户端不许递"
    assert sql.count("NOW()") == 1, "五枚占位符以外只剩库自己生成的那一格时刻"
    for value in params:
        assert isinstance(value, (str, int)), type(value)
        assert BODY_TEXT not in str(value)
        assert not any(character in str(value) for character in ("\r", "\n", "\x00"))
        assert value not in (DOC_ROW["department"], str(DOC_ROW["classification"])), (
            "部门值与密级值一个字都不许进载荷（判据①与告警处置账同一口径）"
        )


def test_the_payload_has_exactly_four_slots_and_the_identity_is_not_one_of_them():
    """载荷四格，一格不多：username 与 occurred_at 都不在请求体里。"""
    assert feedback.ENGAGEMENT_ALLOWED_FIELDS == ALLOWED_ENGAGEMENT_KEYS, feedback.ENGAGEMENT_ALLOWED_FIELDS
    assert set(feedback.DocumentEngagement.model_fields) == ALLOWED_ENGAGEMENT_KEYS
    for banned in ("username", "user", "occurred_at", "timestamp", "query", "question", "answer",
                    "note", "text", "content", "excerpt", "department", "classification", "signal"):
        assert banned not in feedback.DocumentEngagement.model_fields, banned
    assert feedback.ENGAGEMENT_EVENTS == ("click", "view")


def test_a_hundred_thousand_characters_of_body_is_refused_and_lands_no_row(monkeypatch):
    """往端点塞十万字自由文本 ⇒ 4xx 且库里零行（R527 判据 3 的那一句）。"""
    smuggled = (BODY_TEXT * 4000)[:100_000]
    assert len(smuggled) == 100_000, len(smuggled)
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    for key in ("query", "answer", "note", "excerpt", "username"):
        response = _post(client, dict(GOOD_BODY, **{key: smuggled}))
        assert response.status_code == 422, (key, response.status_code)
        assert response.json()["detail"] == "validation_error"
    assert store.rows == [], "拒了的请求一条都不该落库"
    assert store.calls == [], "拒了的请求一次库都不该碰"


def test_the_rejection_log_names_the_field_and_never_the_value(monkeypatch):
    """🔴 反证 K1 的靶子：摘掉 _reject_extra_engagement_fields 那一步，本件当场红。"""
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    with _feedback_logs() as messages:
        response = _post(client, dict(GOOD_BODY, **{"excerpt": BODY_TEXT}))
    assert response.status_code == 422
    assert any("点击账出口拒收未登记字段" in message for message in messages), messages
    assert any("excerpt" in message for message in messages), messages
    assert not any(BODY_TEXT in message for message in messages), (
        "日志里只许出现字段名，绝不允许出现值——那等于把正文另抄一份进日志"
    )

def test_a_question_pasted_into_the_thread_id_slot_is_refused_by_shape(monkeypatch):
    """题号那一格靠字符集把关：带空格、带换行、带中日韩的"题号"根本不该存在，整条拒绝。"""
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    for bad in (BODY_TEXT, "m1 " + BODY_TEXT, "m1\nm2", "m1\tm2", "", " " * 5,
                  "x" * (feedback.MAX_THREAD_ID_CHARS + 1)):
        response = _post(client, dict(GOOD_BODY, thread_id=bad))
        assert response.status_code == 422, (bad[:20], response.status_code)
    assert store.rows == []
    assert store.calls == []
    ok = _post(client, dict(GOOD_BODY, thread_id="s-2026#turn-3"))
    assert ok.status_code == 200, ok.text


def test_the_rank_slot_refuses_anything_that_is_not_a_position(monkeypatch):
    """名次越界或被静默折算都拒：0 与 101 是越界，True 与 "3" 与 3.0 是"修好"，那种修好比拒更坏。"""
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    for bad in (0, -1, 101, 10_000, True, False, "3", 3.0, None, [3]):
        response = _post(client, dict(GOOD_BODY, rank=bad))
        assert response.status_code == 422, (bad, response.status_code)
    assert store.rows == []
    assert [feedback.MIN_RESULT_RANK, feedback.MAX_RESULT_RANK] == [1, 100]


def test_only_two_actions_exist_and_a_third_is_refused_rather_than_counted(monkeypatch):
    """想加第三种动作得再排一枚 migration 改那条 CHECK，而不是往这列里塞自由文本。"""
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    for bad in ("hover", "CLICKED", "", BODY_TEXT, None, 0):
        response = _post(client, dict(GOOD_BODY, event=bad))
        assert response.status_code == 422, (bad, response.status_code)
    assert store.rows == []
    accepted = _post(client, dict(GOOD_BODY, event="view"))
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["event"] == "view"


def test_the_client_cannot_book_a_click_for_someone_else_or_choose_the_clock(monkeypatch):
    """身份只从鉴权主体取，时刻只在库里生成：这两格都不在请求体里，也就都不可能被冒充。"""
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    response = _post(client, dict(GOOD_BODY, username="mallory", occurred_at="1999-01-01T00:00:00Z"))
    assert response.status_code == 422, response.text
    assert store.rows == []
    honest = _post(client, GOOD_BODY)
    assert honest.status_code == 200
    assert honest.json()["username"] == "alice", "记账的那枚人是 token 的主体，不是请求体里的名字"
    assert store.rows[0]["username"] == "alice"
    assert store.rows[0]["occurred_at"] == "2026-10-03T12:00:00+08:00", "时刻这一格由库给"


def test_twenty_clicks_on_the_same_source_land_one_row_and_one_point_of_credit(monkeypatch):
    """那枚 UNIQUE 的行为钉：同人同题同出处同动作只算一次，重复打点刷不出分数。"""
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    readings = []
    for _ in range(20):
        response = _post(client, GOOD_BODY)
        assert response.status_code == 200, response.text
        readings.append(response.json())
    assert len(store.rows) == 1, store.rows
    assert readings[0]["deduplicated"] is False, "第一枚是真入账"
    assert all(item["deduplicated"] is True for item in readings[1:]), (
        "从第二枚起都必须报去重，否则排序读到的 clicks 会被同一个人刷上去"
    )
    assert {item["clicks"] for item in readings} == {1}
    view = _post(client, dict(GOOD_BODY, event="view"))
    assert view.status_code == 200 and view.json()["deduplicated"] is False
    assert len(store.rows) == 2, "点开与展开是两枚动作，各记一次"


def test_the_dedup_key_is_per_person_not_global(monkeypatch):
    """去重按人分组：两个人各点一次是两行事实，一个人点二十次是一行事实。"""
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    assert _post(client, GOOD_BODY, username="alice").status_code == 200
    assert _post(client, GOOD_BODY, username="boss").status_code == 200, "管理员按 scope 可见即可打点"
    assert len(store.rows) == 2
    assert {row["username"] for row in store.rows} == {"alice", "boss"}
    assert store.aggregate() == [("finance-q3.txt", 2, 0)], store.aggregate()


def test_a_missing_table_is_a_refusal_not_a_silent_success(monkeypatch):
    """0019 还没跑的库：写腿必须响。静默吞掉它，排序侧就永远读不到这半张先验还没人知道。"""
    import psycopg.errors
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    def missing(sql, params=None):
        store.calls.append((" ".join(str(sql).split()), params))
        raise psycopg.errors.UndefinedTable('关系 "document_engagement_events" 不存在')
    monkeypatch.setattr(store, "execute", missing)
    response = _post(client, GOOD_BODY)
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "storage_unavailable"
    assert store.rows == [] and store.committed == 0, "写失败的那一笔不许留下半个提交"


# ========================================== 判据③ 权限与越权：拒要拒得下账
def test_clicking_a_source_the_caller_cannot_read_is_refused_and_audited(monkeypatch):
    """点的是读不到的出处 ⇒ 403，且留一行拒绝账（本格的第一枚反证靶子）。"""
    store = _EngagementStore()
    audit = _AuditRecorder()
    client = _staff_client(monkeypatch, store, audit=audit)
    response = _post(client, GOOD_BODY, username="mallory")
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "permission_denied"
    assert store.rows == [], "越权的一条都不许进账"
    assert store.calls == [], "越权的请求一次库都不该碰"
    assert [item["outcome"] for item in audit.calls] == ["failure"], audit.calls
    assert audit.calls[0]["action"] == ACTION_VIEW
    assert audit.calls[0]["resource"] == "finance-q3.txt"
    assert audit.calls[0]["reason"] == "permission_denied"
    assert audit.calls[0]["username"] == "mallory"


def test_the_denial_ledger_carries_no_body_and_no_scope_values(monkeypatch):
    """拒绝账与告警处置账同一口径：只带资源标识与稳定码，正文／部门值／密级值一个字不进。"""
    store = _EngagementStore()
    audit = _AuditRecorder()
    client = _staff_client(monkeypatch, store, audit=audit)
    _post(client, dict(GOOD_BODY, thread_id="m7"), username="mallory")
    dumped = json.dumps(audit.calls, ensure_ascii=False, default=str)
    assert audit.calls, "拒了却不留账，等于没拒"
    for forbidden in (BODY_TEXT, DOC_ROW["department"], str(DOC_ROW["classification"])):
        assert forbidden not in dumped.replace("finance-q3.txt", ""), (
            "拒绝账里出现了不该出现的一格：" + forbidden[:16]
        )
    assert audit.calls[0]["extra"] == {}, "别给审计再开一个能装东西的自由槽"


def test_the_owner_gets_no_extra_credit_and_a_colleague_is_not_locked_out(monkeypatch):
    """能不能点＝能不能看见，同一个判定：owner 不加分，同部门不因"不是自己的"而减分。"""
    store = _EngagementStore()
    audit = _AuditRecorder()
    client = _staff_client(monkeypatch, store, audit=audit)
    owner = _post(client, GOOD_BODY, username="alice")
    assert owner.status_code == 200, owner.text
    admin = _post(client, GOOD_BODY, username="boss")
    assert admin.status_code == 200
    stranger = _post(client, GOOD_BODY, username="mallory")
    assert stranger.status_code == 403 and stranger.json()["detail"] == "permission_denied"
    assert [item["outcome"] for item in audit.calls] == ["success", "success", "failure"], audit.calls
    assert audit.calls[-1]["outcome"] == "failure"


def test_anonymous_and_unlisted_are_refused_with_their_own_codes(monkeypatch):
    """401／403／404／422／503 各归各位：把没登录与没权限混成一码，审计就没法用。"""
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    anonymous = client.post(POST_URL, json=GOOD_BODY)
    assert anonymous.status_code == 401 and anonymous.json()["detail"] == "authentication_required"
    missing = _post(client, dict(GOOD_BODY, filename="not-uploaded.txt"))
    assert missing.status_code == 404 and missing.json()["detail"] == "resource_not_found"
    anonymous_get = client.get(GET_URL)
    assert anonymous_get.status_code == 401
    assert store.calls == [], "未登录与查无此文都不该触达事件表"


def test_a_principal_without_any_department_refuses_with_authorization_unavailable(monkeypatch):
    """filters 的 authorization_unavailable 要原样传出来，不能被压成一句权限不足。"""
    store = _EngagementStore()
    audit = _AuditRecorder()
    client = _staff_client(monkeypatch, store, audit=audit)
    response = _post(client, GOOD_BODY, username="orphan")
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "authorization_unavailable"
    assert store.rows == []
    assert audit.calls and audit.calls[0]["outcome"] == "failure"
    assert audit.calls[0]["reason"] == "authorization_unavailable"


def test_the_read_leg_has_no_slot_for_another_identity(monkeypatch):
    """GET 那条腿压根没有 username 这一格，也没有按别人身份读的那一支：管理员也不例外。"""
    import inspect
    parameters = list(inspect.signature(feedback.read_document_engagement).parameters)
    assert parameters == ["request", "limit"], parameters
    assert "username" not in parameters
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    assert _post(client, GOOD_BODY, username="alice").status_code == 200
    assert _post(client, GOOD_BODY, username="boss").status_code == 200
    tried = _get(client, username="alice", query="?username=boss")
    assert tried.status_code == 200, tried.text
    body = tried.json()
    assert body["username"] == "alice", "别人的身份串不进这条读腿"
    assert all(row["username"] == "alice" for row in body["rows"]), body
    assert len(body["rows"]) == 1, body


def test_the_ledger_only_shows_the_callers_own_reading_history(monkeypatch):
    """🔴 反证 K4 的靶子：读腿里那格 username 一旦丢了，本件当场红（别人的阅读史不许递出去）。"""
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    assert _post(client, GOOD_BODY, username="alice").status_code == 200
    assert _post(client, dict(GOOD_BODY, thread_id="m2"), username="boss").status_code == 200
    mine = _get(client, username="alice").json()
    theirs = _get(client, username="boss").json()
    assert [row["username"] for row in mine["rows"]] == ["alice"], mine
    assert [row["username"] for row in theirs["rows"]] == ["boss"], theirs
    assert mine["returned"] == 1 and theirs["returned"] == 1
    assert {row["thread_id"] for row in theirs["rows"]} == {"m2"}


def test_a_ledger_row_belonging_to_someone_else_closes_the_read(monkeypatch):
    """结构闸：别人的行真回来了（读腿被改坏的形状），宁可当场 403 关账，也不递出去。"""
    store = _EngagementStore()
    store.leak_foreign = True
    client = _staff_client(monkeypatch, store)
    assert _post(client, GOOD_BODY, username="alice").status_code == 200
    response = _get(client, username="alice")
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "permission_denied"
    assert "other.txt" not in response.text, "拒绝的答复里不许把别人的出处再念一遍"


def test_the_ledger_row_shape_is_six_slots_and_carries_no_content(monkeypatch):
    """账目那一页的列清单固定六枚：谁／哪道题／哪一枚出处／第几名次／什么动作／什么时候。"""
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    _post(client, dict(GOOD_BODY, event="view", rank=3))
    page = _get(client).json()
    assert set(page) == {
        "username", "rows", "returned", "limit", "prior_source", "prior_reason", "prior_enabled"
    }, sorted(page)
    assert set(page["rows"][0]) == {"username", "thread_id", "filename", "rank", "event", "occurred_at"}
    assert page["rows"][0]["rank"] == 3 and page["rows"][0]["event"] == "view"
    assert BODY_TEXT not in json.dumps(page, ensure_ascii=False)
    assert page["prior_source"] in {"never", "store", "error"}


def test_the_page_size_is_bounded_and_out_of_range_is_refused(monkeypatch):
    """上界给死是为了这条读腿永远不必全表扫；越界不走默认值，直接拒。"""
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    for index in range(1, 6):
        assert _post(client, dict(GOOD_BODY, thread_id="m" + str(index))).status_code == 200
    assert [feedback.DEFAULT_LEDGER_ROWS, feedback.MAX_LEDGER_ROWS] == [20, 100]
    small = _get(client, query="?limit=3")
    assert small.status_code == 200 and small.json()["returned"] == 3, small.text
    assert small.json()["limit"] == 3
    for bad in ("0", "101", "-5"):
        refused = _get(client, query="?limit=" + bad)
        assert refused.status_code == 422, (bad, refused.status_code)
        assert refused.json()["detail"] == "validation_error"


def test_no_stable_code_in_this_half_is_a_new_invention():
    """本半张单不新增错误码：全部落在已批的 ErrorEnvelope 封闭枚举里（在册口径守住）。"""
    from typing import get_args
    approved = set(get_args(ErrorEnvelope.model_fields["code"].annotation))
    emitted = {
        "authentication_required", "permission_denied", "authorization_unavailable",
        "resource_not_found", "validation_error", "storage_unavailable",
    }
    assert emitted <= approved, sorted(emitted - approved)


def test_the_migration_number_is_reserved_for_this_ticket_and_no_other_was_opened():
    """派工词的两枚死规矩：只许 0019，不许抢 0018，也不许另开 0020。"""
    numbers = sorted(path.name.split("_")[0] for path in (REPO / "migrations").glob("0*.sql"))
    assert numbers[-1] == "0019", numbers[-3:]
    assert "0020" not in numbers and "0018" in numbers
    ledger = (REPO / "tests" / "test_r349_catalog_tail_ledger.py").read_text(encoding="utf-8")
    assert ledger.count('CATALOG_TAIL_VERSION = "0019"') == 1, "尾号字面量全仓只许出现在账本里一次"
