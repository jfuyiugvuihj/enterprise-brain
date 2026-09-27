# -*- coding: utf-8 -*-
"""R342 · GET /dashboard/trend 的「没有期间」出口：判据甲 / 乙 / 丙。

病灶（业主体已授权的修法）：``_trend_unreadable`` 把「这一枚行读不出期间」判成
「整条响应拒答」，于是一枚 legacy 登记行（``app/storage/datasets.py:763`` 走
``_timestamp_text(None)`` -> ``""``）就能把 R332+R341 刚接上的总览「数据趋势」卡打死成
永久 503。迁移默认值与 legacy 导入是我们自己留下的形状，界面不该拿它惩罚每一个用户。

这一件钉的是改完之后仍然成立的账，四条：

- **甲 · 显式出口，且不是 0。**「这一枚行没有期间」从拒答整个响应改成响应里新的一格
  ``undated``（名字沿用看板 §4CV 对 R332 裁定 ③ 的判词）。它装的是份数，所以既没有少画一根
  柱子，也没有把 N 画成 0。守恒必须是量出来的：``各桶之和 + undated == /summary 对同一个人
  同一范围报的数``（见 ``test_the_three_books_all_reconcile_...``）。
- **乙 · 两张脸不合并。** 登记行根本没记时间（可预期）与「列表说这档可见、台账说没有 active
  行」（两次读互相矛盾）是两件事：前者进 ``undated``，后者继续 503。记了但解析不出来的第三种
  形状也继续 503 —— 把一致性故障洗成一条脚注，就是这一单要防的复发。
- **丙 · 真不可用还是 503。** 被拒的响应里没有 ``series``，也没有 ``undated``：一张画不出来的
  卡不许降级成「0 条 + 无期间 N」。读依赖抛的错原样往外传。
- **丁 · 零新增错误码、零迁移。** 只有 200 / 422 / 503 三张既有脸，``detail`` 逐字不变。
- **戊 · 「各档之和 + 无期间 == 当下未处置的行数」不是律。** R340 把 ``alerts_open`` 换成按
  各档自己那一刻回放之后，这句只在「所有有期间的行都住在最新那一档」的种子里恰好成立（最新
  那一档还没收口，它的地平线就是请求瞬间，新旧读法在那几枚行上同数）。R365 把世界补真 ——
  一枚上月创建、本月才知悉，一枚知悉时刻落在自己那一档收口之前 —— 再把这句升成一条由同枚
  种子现算派生的等式（见 ``_assert_alerts_open_conserves`` 与那几枚 R365 具名钉）。

世界与夹具直接取自 ``tests/test_r332_dashboard_trend.py``（含三枚 autouse 桩），因为这一件量的
正是「同一枚行、同一位调用者、同一次读」——换一套夹具，守恒就对不到那一本账上。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.agents.contracts import Principal

import pytest

from tests.test_r332_dashboard_trend import (  # noqa: F401  (夹具是导入进来的，不是复制的)
    SHANGHAI,
    SUMMARY_PATH,
    _headers,
    _month_label,
    _now,
    _series,
    _shanghai_instants,
    _trend,
    accounts,
    client,
    dataset_store,
    document_store,
    memory_alerts,
    offline_catalog,
    seed_alerts,
)

#: PG 腿的替身与「带处置三列的行」都取自 R340 那一件，不在这里复制第二台。
from tests.test_r340_replayable_alerts_open import (  # noqa: F401  (同上：导入，不是复制的)
    _body,
    _created,
    _memory_leg,
    _prev_month_anchor,
    _sql_leg,
    _stamp,
    alarm,
)

#: 三本账在响应里各自的那几格。``alerts`` / ``alerts_open`` 只在有告警读权时出现。
CORE_KEYS = {"documents", "documents_ready", "datasets"}
ALERT_KEYS = {"alerts", "alerts_open"}


def _undated(body):
    """``undated`` 必须一直在：缺席就是「服务端没说这一格」，客户端无从判断有没有漏。"""
    assert "undated" in body, "无期间那一格从响应里消失了"
    return body["undated"]


def _summary(client, username: str = "finance-manager") -> dict:
    return client.get(SUMMARY_PATH, headers=_headers(username)).json()


@pytest.fixture()
def catalog_rows(monkeypatch):
    """Drive the document book with a row the *offline* catalog cannot produce.

    ``catalog._local_row`` substitutes ``_file_mtime`` into any row whose ``created_at`` is
    falsy (``app/documents/catalog.py:386-387``), so offline there is no such thing as a
    document with no period. The PostgreSQL leg has no such rescue: ``created_at`` is
    ``TEXT NOT NULL`` with no ``DEFAULT`` (``migrations/0003_legacy_runtime_tables.sql:46``),
    so an empty cell is a storable shape. Stubbing the one read ``/summary`` and ``/trend``
    share keeps both answers over the same rows, which is what the conservation pin needs.
    """
    from app.api.v1 import chat

    holder = {"rows": []}

    async def listing(request):
        return {"documents": [dict(row) for row in holder["rows"]]}

    monkeypatch.setattr(chat, "list_document_catalog", listing)
    return holder


# ----------------------------------------------------------- 判据甲 · 显式出口，而且不是 0


def test_the_response_always_answers_how_many_rows_have_no_period(client):
    """一枚 legacy 行都没有时，这一格也在位，并且答 0 —— 缺席与零不是一回事。"""
    body = _trend(client).json()

    assert _undated(body) == {"documents": 0, "documents_ready": 0, "datasets": 0,
                              "alerts": 0, "alerts_open": 0}
    assert len(body["series"]) == 12, "窗口一格都不许因为这一格而变短"


def test_a_legacy_dataset_row_with_no_period_no_longer_refuses_the_series(client, dataset_store):
    """R332 那枚「整条 503」的判词在这里改口：这一枚行只是没有期间，不是读不到账。"""
    dataset_store("legacy.csv", owner="finance-manager", department="finance", created_at="")

    response = _trend(client)

    assert response.status_code == 200, response.json()
    body = response.json()
    assert _undated(body)["datasets"] == 1
    assert sum(point["datasets"] for point in body["series"]) == 0


def test_the_undated_count_is_never_written_as_the_zero_it_replaced(client, dataset_store):
    """判据甲的后半：不许悄悄少画一根柱子，更不许把这枚行画成某一期的一根 0 柱。"""
    dataset_store("legacy.csv", owner="finance-manager", department="finance", created_at="")

    body = _trend(client).json()

    assert _undated(body)["datasets"] != 0, "把死刑换成 0 是第二种假话"
    assert all(point["datasets"] == 0 for point in body["series"])


def test_a_blank_and_a_whitespace_period_are_the_same_face(client, dataset_store):
    """``''`` 与 ``'   '`` 都是「没记」；这一档与服务端的 strip 口径同源。"""
    dataset_store("blank.csv", owner="finance-manager", department="finance", created_at="")
    dataset_store("spaces.csv", owner="finance-manager", department="finance", created_at="   ")

    body = _trend(client).json()

    assert _undated(body)["datasets"] == 2


def test_an_undated_row_does_not_move_a_dated_one(client, dataset_store):
    """两枚行各归各：有期间的那枚照样落在自己的那一期。"""
    inside, _ = _shanghai_instants()
    dataset_store("legacy.csv", owner="finance-manager", department="finance", created_at="")
    dataset_store("fresh.csv", owner="finance-manager", department="finance",
                  created_at=inside.astimezone(timezone.utc).isoformat())

    body = _trend(client, buckets=12).json()

    assert _series(body)[_month_label(inside.date())]["datasets"] == 1
    assert _undated(body)["datasets"] == 1
    assert sum(point["datasets"] for point in body["series"]) + _undated(body)["datasets"] == 2


def test_several_rows_for_one_file_let_the_newest_recorded_one_win(client, dataset_store,
                                                                    monkeypatch):
    """``get_active_by_filename`` 同一把尺：``''`` 排在任何 ISO 串之后，无期间那枚赢不了桶。

    单位是「可见的一档」，不是「台账里的一行」，所以一档有两行时 ``undated`` 只该数没期间的
    *档*——这里一档有期间，就该一格都不进 ``undated``。
    """
    from app.api.v1 import data

    inside, _ = _shanghai_instants()
    dataset_store("finance.csv", owner="finance-manager", department="finance",
                  created_at=inside.astimezone(timezone.utc).isoformat())
    monkeypatch.setattr(
        data.dataset_registry, "active_records",
        lambda: [
            SimpleNamespace(filename="finance.csv", created_at=""),
            SimpleNamespace(filename="finance.csv",
                            created_at=inside.astimezone(timezone.utc).isoformat()),
        ],
    )

    body = _trend(client, buckets=12).json()

    assert _series(body)[_month_label(inside.date())]["datasets"] == 1
    assert _undated(body)["datasets"] == 0


def test_an_alert_row_that_recorded_no_time_is_counted_not_refused(client, seed_alerts):
    from app.api.v1 import alerts

    seed_alerts("undated alarm", created_at=_now().isoformat(timespec="seconds"))
    alerts._MEM_ALERTS[0].pop("created_at")

    response = _trend(client)

    assert response.status_code == 200, response.json()
    body = response.json()
    assert _undated(body) == {"documents": 0, "documents_ready": 0, "datasets": 0,
                              "alerts": 1, "alerts_open": 1}
    assert sum(point["alerts"] for point in body["series"]) == 0


def test_an_alert_without_a_period_that_is_already_disposed_still_has_no_open_count(client,
                                                                                   seed_alerts):
    """两列各数各的：无期间的已处置告警进 ``alerts``，不进 ``alerts_open``。"""
    seed_alerts("acked alarm", created_at="", status="acknowledged")
    seed_alerts("open alarm", created_at="", status="open")

    body = _trend(client).json()

    assert (_undated(body)["alerts"], _undated(body)["alerts_open"]) == (2, 1)


def test_a_document_row_with_no_period_is_counted_in_both_document_columns(catalog_rows, client):
    """``documents_ready`` 不许比 ``documents`` 少算一枚无期间的行：两列同一本账。"""
    inside, _ = _shanghai_instants()
    catalog_rows["rows"] = [
        {"filename": "old-a.pdf", "created_at": "", "parse_status": "ready"},
        {"filename": "old-b.pdf", "created_at": None, "parse_status": "pending"},
        {"filename": "new.pdf", "created_at": inside.isoformat(), "parse_status": "ready"},
    ]

    body = _trend(client, buckets=12).json()
    summary = _summary(client)

    assert _undated(body)["documents"] == 2
    assert _undated(body)["documents_ready"] == 1
    assert _series(body)[_month_label(inside.date())]["documents"] == 1
    assert sum(point["documents"] for point in body["series"]) == summary["documents"] - 2
    assert sum(point["documents_ready"] for point in body["series"]) == (
        summary["documents_ready"] - 1
    )


def test_undated_is_a_sibling_of_the_series_and_never_a_bucket(client, dataset_store):
    """「有多少条没有期间」与「这一期新增了几条」是两个问题，不许画进同一格。"""
    dataset_store("legacy.csv", owner="finance-manager", department="finance", created_at="")

    body = _trend(client, buckets=6).json()

    assert set(body) == {"generated_for", "period", "buckets", "time_zone", "series", "undated"}
    for point in body["series"]:
        assert "undated" not in point
        assert set(point) == {"bucket", "start", "documents", "documents_ready", "datasets",
                              "alerts", "alerts_open"}


# ------------------------------------------------- 判据乙 · 三种形状三张脸，一枚 except 兜不住


def test_a_recorded_value_that_is_not_a_period_still_refuses_the_whole_series(client,
                                                                             dataset_store):
    """解析不出来 != 没记：这一枚仍然不许被摊成「无期间」。"""
    dataset_store("odd.csv", owner="finance-manager", department="finance",
                  created_at="2026-13-45T99:99:99")

    response = _trend(client)

    assert response.status_code == 503
    assert response.json()["detail"] == "storage_unavailable"
    assert "undated" not in response.json()


def test_a_non_text_non_datetime_period_still_refuses(client, seed_alerts):
    """形状根本不是时间的行（驱动给了个整数）也算解析不出，不算没记。"""
    from app.api.v1 import alerts

    seed_alerts("weird alarm", created_at=_now().isoformat(timespec="seconds"))
    alerts._MEM_ALERTS[0]["created_at"] = 1789000000

    response = _trend(client)

    assert response.status_code == 503
    assert response.json()["detail"] == "storage_unavailable"


def test_a_document_row_with_an_unparseable_time_still_refuses(catalog_rows, client):
    """三条腿同一判据：文档腿记了但读不成期间，也是 503，不是 ``undated``。"""
    catalog_rows["rows"] = [{"filename": "odd.pdf", "created_at": "昨天上午",
                             "parse_status": "ready"}]

    response = _trend(client)

    assert response.status_code == 503
    assert response.json()["detail"] == "storage_unavailable"
    assert "undated" not in response.json()


def test_a_visible_file_with_no_active_registry_row_still_refuses(client, monkeypatch,
                                                                  dataset_store):
    """R342 不许顺手放走的第二张脸：两次读互相矛盾，是真异常。"""
    from app.api.v1 import data

    inside, _ = _shanghai_instants()
    dataset_store("finance.csv", owner="finance-manager", department="finance",
                  created_at=inside.astimezone(timezone.utc).isoformat())

    async def listing_with_a_ghost(request=None):
        return {"files": [{"filename": "vanished.csv", "modified_at": inside.isoformat()}]}

    monkeypatch.setattr(data, "list_data_files", listing_with_a_ghost)

    response = _trend(client)

    assert response.status_code == 503
    assert response.json()["detail"] == "storage_unavailable"
    assert "series" not in response.json()
    assert "undated" not in response.json(), "矛盾不许被洗成一条脚注"


def test_a_book_that_raises_is_still_not_folded_into_a_count(client, monkeypatch):
    """判据丙：没有任何一处 ``try/except`` 把读依赖的失败摊平。"""
    from app.api.v1 import chat

    async def boom(request):
        raise RuntimeError("catalog is down")

    monkeypatch.setattr(chat, "list_document_catalog", boom)

    with pytest.raises(RuntimeError, match="catalog is down"):
        _trend(client)


# ----------------------------------------------------------- 守恒 · 各桶之和 + 无期间 = 总览


# ------------------------------------- R365 · 把「各档之和 + 无期间」那句巧合升成真律


#: 本件种进趋势卡的两枚行，名字即判据：一枚跨档处置，一枚的处置时刻落在自己那一档收口之前。
CROSS_MONTH_MESSAGE = "上月创建_本月才知悉"
LATEST_BUCKET_MESSAGE = "本月创建_知悉时刻落在本档收口之前"

#: 守恒式两边共用这一枚账号，与 ``_summary`` 的默认调用者同一个。
FINANCE_MANAGER = Principal.from_user({
    "id": "finance-manager", "username": "finance-manager",
    "role": "manager", "department": "finance",
})


def _visible_alert_rows(alerts_api) -> list[dict]:
    """本次可见的那些行：可见性仍用 ``GET /alerts`` 那把尺，本件不另立归属口径。"""
    return [row for row in alerts_api._MEM_ALERTS
            if alerts_api.alert_row_visible(FINANCE_MANAGER, row)]


def _present_open_rows(alerts_api) -> list[dict]:
    """当下这一秒按告警面板那把 status 尺算「未处置」的那些行 —— 旧那句守恒的整条右端。"""
    return [row for row in _visible_alert_rows(alerts_api)
            if alerts_api.alert_row_status(row) == alerts_api.ALERT_STATUS_OPEN]


def _month_edge(start: date) -> datetime:
    """``start`` 那一档收口的瞬间：下个月 1 号 00:00（上海墙上时间）。

    测试自己按日历推一遍（承 R340 的「日历测试自己算一遍」），不把实现里的 ``_bucket_end``
    搬过来再与它自己对一次：那样等式两侧就成了同一个表达式。``start`` 恒为某月 1 号，所以
    「加 31 天再回到 1 号」在 28/29/30/31 天的月里都恰好走到下一档。这一枚尺由
    ``test_the_test_side_month_edge_walks_one_period`` 自己量：本件施工时它错过一次（写成
    「加 4 天」会退回本档 1 号），而它错了不只是红，是红得像实现的问题。
    """
    following = (start + timedelta(days=31)).replace(day=1)
    return datetime(following.year, following.month, 1, tzinfo=SHANGHAI)


class _BucketClockRow:
    """一枚本件种下的告警：它归哪一档、那一档的地平线在哪、什么时候被人处置，全部现算。"""

    def __init__(self, message: str, created: datetime, disposed: datetime) -> None:
        self.message = message
        self.created = created
        self.disposed = disposed

    @property
    def bucket_start(self) -> date:
        """``period=month`` 下这一枚行所属那一档的起点，由它自己的 ``created`` 决定。"""
        return self.created.date().replace(day=1)

    @property
    def horizon(self) -> datetime:
        """档边与当下取更早的一枚：最新那一档还没收口，它的地平线就是「现在」。"""
        return min(_month_edge(self.bucket_start), _now())

    @property
    def disposed_after_horizon(self) -> bool:
        return self.disposed >= self.horizon


def _bucket_clock_rows() -> tuple[_BucketClockRow, ...]:
    """种子表：同一份 datetime 既用来播种，也用来现算等式右端，两处都不许手填常数。

    - ``CROSS_MONTH_MESSAGE`` 上月创建、本月才有人知悉：旧口径（按请求时刻的 status 数）
      一枚都不数它，新口径把它留在上月那一档 —— 两种读法因此在测试世界里真的分得开。
    - ``LATEST_BUCKET_MESSAGE`` 本月创建，知悉时刻落在「当下」与「本档收口」正中：最新那一
      档的档边还没到，它的地平线必须是当下。取中点而不是「今天再加一天」，是为了月末最后
      一天跑也不跨档。
    """
    now = _now()
    inside, _ = _shanghai_instants()
    edge = _month_edge(inside.date().replace(day=1))
    return (
        _BucketClockRow(CROSS_MONTH_MESSAGE, _prev_month_anchor(), now),
        _BucketClockRow(LATEST_BUCKET_MESSAGE, inside, now + (edge - now) / 2),
    )


def _bucket_clock_world(alarm, alerts_api) -> tuple[_BucketClockRow, ...]:
    """把上面那张表落到台账上，并把同一份表交回：摘掉种子里任何一枚，等式两边一起动。"""
    rows = _bucket_clock_rows()
    for row in rows:
        alarm(row.message, created_at=_created(row.created),
              status=alerts_api.ALERT_STATUS_ACKNOWLEDGED,
              acknowledged_at=_stamp(row.disposed))
    return rows


def _rows_the_bucket_clock_adds(rows, body, alerts_api) -> int:
    """等式右端那枚修正量：只有按「自己那一刻」回放才数得到的行数，由种子现算派生。

    一枚行要同时满足三条才算：① 它有期间，而且所在那一档在本次响应的窗口里；② 按告警面板
    那把 status 尺它今天不算未处置（旧口径正因为如此才数不到它）；③ 它的处置时刻落在自己
    那一档的地平线之后。三条都在这里量，不留给任何一枚测试写死。
    """
    window = {point["start"] for point in body["series"]}
    status_of = {str(row.get("message")): alerts_api.alert_row_status(row)
                 for row in _visible_alert_rows(alerts_api)}
    counted = 0
    for row in rows:
        assert row.message in status_of, f"{row.message} 不在可见的行里：本件的种子没落到台账上"
        if row.bucket_start.isoformat() not in window:
            continue
        if status_of[row.message] == alerts_api.ALERT_STATUS_OPEN:
            continue
        assert row.disposed_after_horizon, f"{row.message} 的处置时刻不再晚于自己那档的地平线"
        counted += 1
    return counted


def _assert_alerts_open_conserves(alerts_api, rows, body, open_now: int, label: str):
    """本件的等式本体（写一次，几枚钉共用）：

    ``sum(各档 alerts_open) + undated.alerts_open == 当下未处置的行数 + 只有回放才数得到的行数``

    左端是一次 HTTP 读数，右端是把台账逐行数出来的两笔账，两侧不是同一个表达式。第一笔右端
    项正是 R342 原来那句守恒的整条右端，所以旧那句在这里没被摘掉，只是降成一条特例：修正量
    为 0 时两边同解。
    """
    replayed = _rows_the_bucket_clock_adds(rows, body, alerts_api)
    bucketed = sum(point["alerts_open"] for point in body["series"])
    undated_open = _undated(body)["alerts_open"]

    assert bucketed + undated_open == open_now + replayed, (
        f"{label}：各档回放 {bucketed} + 无期间 {undated_open} ≠ "
        f"当下未处置 {open_now} + 处置晚于自己档边 {replayed}")
    return bucketed, undated_open, open_now, replayed


def test_a_day_with_no_legacy_rows_still_reconciles_with_the_summary(client, dataset_store,
                                                                    document_store):
    inside, _ = _shanghai_instants()
    document_store("plan.pdf", department="finance", owner="finance-manager",
                   created_at=inside.isoformat())
    dataset_store("finance.csv", owner="finance-manager", department="finance",
                  created_at=inside.astimezone(timezone.utc).isoformat())

    body = _trend(client, buckets=60).json()
    summary = _summary(client)

    for key in ("documents", "documents_ready", "datasets"):
        assert sum(point[key] for point in body["series"]) + _undated(body)[key] == summary[key]


def test_the_three_books_all_reconcile_with_what_summary_reports(client, dataset_store,
                                                                seed_alerts, catalog_rows,
                                                                alarm, monkeypatch):
    """判据甲要求的实测：混一世界（有期间的 + 无期间的 + 已处置的）三本账逐条对平。

    ``sum(buckets) + undated == /summary 对同一位调用者同一范围报的数``。告警那一本没有
    ``/summary`` 的对偶列（``alerts_open`` 是当前状态投影，R332 裁定 ②），所以它跟「本次可见
    的行数」对，用的仍是 ``GET /alerts`` 那把谓词，不是这一件自己另算的账。

    R365：``alerts_open`` 那一行原来跟「本次可见且当下未处置的行数」直接对等，那只在这枚种子
    里成立 —— 所有有期间的行都住在最新那一档。现在世界里有了跨档处置的行，这句换成一条现算
    派生的等式（``_assert_alerts_open_conserves``），旧那句是它修正量为 0 时的特例。
    """
    from app.api.v1 import alerts as alerts_api

    inside, before = _shanghai_instants()
    catalog_rows["rows"] = [
        {"filename": "dated.pdf", "created_at": inside.isoformat(), "parse_status": "ready"},
        {"filename": "aged.pdf", "created_at": before.isoformat(), "parse_status": "pending"},
        {"filename": "legacy-a.pdf", "created_at": "", "parse_status": "pending"},
        {"filename": "legacy-b.pdf", "created_at": None, "parse_status": "ready"},
    ]
    dataset_store("dated.csv", owner="finance-manager", department="finance",
                  created_at=inside.astimezone(timezone.utc).isoformat())
    dataset_store("legacy.csv", owner="finance-manager", department="finance", created_at="")
    seed_alerts("dated alarm", created_at=inside.isoformat(), department="finance")
    seed_alerts("legacy open alarm", created_at="", department="finance")
    seed_alerts("legacy acked alarm", created_at="   ", department="finance",
                status="acknowledged")
    bucket_clock = _bucket_clock_world(alarm, alerts_api)

    body = _trend(client, buckets=60).json()
    summary = _summary(client)

    undated = _undated(body)
    for key in ("documents", "documents_ready", "datasets", "alerts"):
        total = summary[key] if key != "alerts" else summary["alerts"]["total"]
        assert sum(point[key] for point in body["series"]) + undated[key] == total, key

    principal = Principal.from_user({
        "id": "finance-manager", "username": "finance-manager",
        "role": "manager", "department": "finance",
    })
    visible = [row for row in alerts_api._MEM_ALERTS if alerts_api.alert_row_visible(principal,
                                                                                     row)]
    open_rows = [row for row in visible if alerts_api.alert_row_status(row)
                 == alerts_api.ALERT_STATUS_OPEN]
    _assert_alerts_open_conserves(alerts_api, bucket_clock, body, len(open_rows), "三本账对平")
    assert undated == {"documents": 2, "documents_ready": 1, "datasets": 1,
                       "alerts": 2, "alerts_open": 1}


def test_the_test_side_month_edge_walks_one_period():
    """钉⓪：先量本件自己那把日历尺，再量等式。

    等式右端用的是测试这一侧的日历：本件的 ``_month_edge`` 与从 R340 那件导入来的
    ``_prev_month_anchor``，不是实现里的 ``_bucket_end``。这一枚尺错一格，等式就跟着错，
    而且错得像实现的问题 —— 上面的 ``_month_edge`` 施工时写过「加 4 天回到 1 号」，
    那一版退回本档 1 号，量的就是这种错。
    """
    cursor = date(2026, 1, 1)
    for _ in range(36):  # 含 28/29/30/31 天四种月长（2028 是闰年）
        following = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        edge = _month_edge(cursor)
        assert edge.date() == following, f"{cursor} 那一档的档边算成了 {edge}"
        assert (edge.hour, edge.minute, edge.second) == (0, 0, 0), edge
        cursor = following
    assert cursor == date(2029, 1, 1), cursor


def test_a_disposal_after_its_own_bucket_edge_really_landed_in_the_world(client, alarm):
    """钉①：跨档处置确实进过世界 —— 摘掉 ``_bucket_clock_rows`` 里那枚 seed，这一枚先红。

    上月那一档里只住着「上月创建、本月才知悉」这一枚行，而它今天已经不是 ``open``：按请求
    时刻的 status 数，这一档该报 0 枚未处置；R340 的回放报 1 枚。这一枚钉要量的就是「新旧
    两种读法在测试世界里真的分开了」这件事本身，不是等式。
    """
    from app.api.v1 import alerts as alerts_api

    _bucket_clock_world(alarm, alerts_api)
    previous = _prev_month_anchor()
    body = _body(client, buckets=60)

    assert _month_label(previous.date()) != _month_label(_now().date()), "两档得真的是两档"
    late = [row for row in _visible_alert_rows(alerts_api)
            if row.get("message") == CROSS_MONTH_MESSAGE]
    assert len(late) == 1, f"{CROSS_MONTH_MESSAGE} 没进世界：本件的种子被摘掉了"
    assert alerts_api.alert_row_status(late[0]) == alerts_api.ALERT_STATUS_ACKNOWLEDGED, (
        "这枚行今天仍是 open：新旧读法就没分开，这一枚钉量的不是跨档处置")
    # 这一档总共只住一枚行，而那枚行今天已经不是 open：按请求时刻的 status 数，这里该是
    # (1, 0)；响应报 (1, 1)，量的就是「按自己那一刻回放」真的发生了。
    previous_bucket = _series(body)[_month_label(previous.date())]
    assert (previous_bucket["alerts"], previous_bucket["alerts_open"]) == (1, 1), (
        f"上月那一档读成 {previous_bucket['alerts']} 行 / "
    f"{previous_bucket['alerts_open']} 枚未处置：跨档处置没有进世界")


def test_the_present_status_equation_is_not_a_law(client, alarm):
    """钉②：跨档处置一进世界，「各档之和 + 无期间 == 当下未处置的行数」这句必然不成立。

    下一位要是再把旧那句当律抄回守恒式，这一枚先红，并且报出方向：左端比右端多出的正是那些
    「处置时刻晚于自己档边」的行 —— 新口径把它们留在自己那一档，旧口径一枚都不数。旧那句在
    本件补真之前恰好成立，是因为那时的种子里有期间的行全住在最新那一档，而最新一档的地平线
    就是当下。
    """
    from app.api.v1 import alerts as alerts_api

    rows = _bucket_clock_world(alarm, alerts_api)
    body = _body(client, buckets=60)
    open_now = len(_present_open_rows(alerts_api))

    bucketed, undated_open, _same, replayed = _assert_alerts_open_conserves(
        alerts_api, rows, body, open_now, "钉②")

    assert replayed >= 1, "修正量为 0：新旧读法没分开，本件要还的那笔债根本没被种进世界"
    assert bucketed + undated_open != open_now, (
        f"旧那句等式又成立了（左右都是 {open_now}）：跨档处置的行不在世界里，"
        "而它不是律，不许被抄回守恒式")


def test_no_bucket_replays_more_open_rows_than_it_has(client, alarm):
    """钉③：R340 的界在补真的世界里仍然成立 —— 每档 ``0 ≤ alerts_open ≤ alerts``。"""
    from app.api.v1 import alerts as alerts_api

    _bucket_clock_world(alarm, alerts_api)
    previous = _prev_month_anchor()
    body = _body(client, buckets=60)
    filled = [point for point in body["series"] if point["alerts"]]

    assert filled, "一档都没有行，这条界就成了恒真"
    for point in filled:
        assert 0 <= point["alerts_open"] <= point["alerts"], f"该档未处置数越界：{point}"
    cross = _series(body)[_month_label(previous.date())]
    assert cross["alerts_open"] == cross["alerts"], "上界不许只是画在纸上的界"
    assert sum(point["alerts_open"] for point in body["series"]) + (
        _undated(body)["alerts_open"]) <= len(_visible_alert_rows(alerts_api)), (
        "回放不许凭空造行：各档之和加无期间仍被同一个可见行数封顶")


def test_both_legs_replay_the_same_seed_and_obey_the_same_law(client, alarm, monkeypatch):
    """R365 判据：补真的世界与新的等式都得两腿同种子同读数，不许哪一腿自己算一套。

    PG 腿的替身沿用 ``tests/test_r340_replayable_alerts_open.py`` 那一台：只认
    ``alert_row_scope_sql`` 生成的那三种析取支，并按 ``SELECT`` 清单逐列投影 —— 这一腿少读
    一枚处置列，交回的行就少一个键，下面的等号当场红，不靠 docstring 说。
    """
    from app.api.v1 import alerts as alerts_api

    rows = _bucket_clock_world(alarm, alerts_api)

    _memory_leg(alerts_api, monkeypatch)
    offline = _body(client, buckets=60)
    open_now = len(_present_open_rows(alerts_api))
    _assert_alerts_open_conserves(alerts_api, rows, offline, open_now, "离线腿")

    _sql_leg(alerts_api, list(alerts_api._MEM_ALERTS), monkeypatch)
    postgres = _body(client, buckets=60)
    _assert_alerts_open_conserves(alerts_api, rows, postgres, open_now, "PG 腿")

    assert offline["series"], "空序列会让下面那条等号变成恒真"
    assert postgres["series"] == offline["series"], "同一份种子在两条腿上长出了两个数"
    assert postgres["undated"] == offline["undated"]


def test_no_row_is_counted_twice(client, dataset_store, catalog_rows):
    """守恒的另一半：``undated`` 加回去之后不许超过总览，一枚行只属于一格。"""
    inside, _ = _shanghai_instants()
    catalog_rows["rows"] = [{"filename": "legacy.pdf", "created_at": "",
                             "parse_status": "pending"}]
    dataset_store("legacy.csv", owner="finance-manager", department="finance", created_at="")

    body = _trend(client, buckets=60).json()
    summary = _summary(client)

    for key in ("documents", "documents_ready", "datasets"):
        buckets = sum(point[key] for point in body["series"])
        assert buckets + _undated(body)[key] == summary[key]
        assert buckets <= summary[key]


# --------------------------------------------------------- 权限 · 没告警权就没有那两格


def test_a_caller_without_alert_rights_gets_no_undated_alert_keys(client, seed_alerts):
    """R1 不许从这一格绕回来：无权限是键整个缺席，不是 0，也不是「无期间 0 条」。"""
    from app.api.v1 import alerts

    seed_alerts("hidden alarm", created_at=_now().isoformat(timespec="seconds"))
    alerts._MEM_ALERTS[0].pop("created_at")

    staff = _trend(client, "finance-staff").json()

    assert set(_undated(staff)) == CORE_KEYS
    assert all("alerts" not in point and "alerts_open" not in point for point in staff["series"])
    assert client.get(SUMMARY_PATH, headers=_headers("finance-staff")).json().get("alerts") is None


def test_the_gate_still_runs_before_any_period_is_read(client):
    """无 ``resource:analyze`` 的账号连「有没有无期间的行」都问不出来。"""
    assert _trend(client, "outside-auditor").status_code == 403
