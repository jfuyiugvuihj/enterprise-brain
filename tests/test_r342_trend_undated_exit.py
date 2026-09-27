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

世界与夹具直接取自 ``tests/test_r332_dashboard_trend.py``（含三枚 autouse 桩），因为这一件量的
正是「同一枚行、同一位调用者、同一次读」——换一套夹具，守恒就对不到那一本账上。
"""
from __future__ import annotations

from datetime import timezone
from types import SimpleNamespace

from app.agents.contracts import Principal

import pytest

from tests.test_r332_dashboard_trend import (  # noqa: F401  (夹具是导入进来的，不是复制的)
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
                                                                monkeypatch):
    """判据甲要求的实测：混一世界（有期间的 + 无期间的 + 已处置的）三本账逐条对平。

    ``sum(buckets) + undated == /summary 对同一位调用者同一范围报的数``。告警那一本没有
    ``/summary`` 的对偶列（``alerts_open`` 是当前状态投影，R332 裁定 ②），所以它跟「本次可见
    的行数」对，用的仍是 ``GET /alerts`` 那把谓词，不是这一件自己另算的账。
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
    assert sum(point["alerts_open"] for point in body["series"]) + undated["alerts_open"] == (
        len(open_rows)
    )
    assert undated == {"documents": 2, "documents_ready": 1, "datasets": 1,
                       "alerts": 2, "alerts_open": 1}


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