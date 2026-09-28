# -*- coding: utf-8 -*-
r"""R404 判据 a · 判定之前只许读一行：catalog 的单行读，与路由里那两次读数的先后。

现场（本件全部现读，行号一枚不抄）：

  * `app/documents/catalog.py` 的 `latest_document_version()` = 单行读，SQL 是
    ``ORDER BY version DESC`` 同一句带上 ``LIMIT 1``。它借 `list_document_versions`
    同一枚 scope 落地，所以本模块的 `_ensure()` 调用点一枚没多（R377／R383 那两本账按
    AST 穷尽数着，多一枚当场红）。
  * `app/api/v1/chat.py` 的 `document_version_history`：判定输入 = 那一行；全量读排在判定
    之后，只喂响应正文。⇒ 一次跨部门的探测付的是「一行」的代价，而不是整本版本历史。

判据 a：把单行读换回全量读 ⇒ 本件红。两把独立的尺：catalog 侧量「这次读数物化了几行」，
路由侧量「判定那一刻已经发生过哪几次读数」。`test_teeth_a_the_ruler_fires_on_the_legacy_shape`
是量具自证：同一把尺去量落码前的旧序形状，必须判出「不合规」——否则这些绿是假绿。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _catalog():
    from app.documents import catalog

    return catalog


def _rows(name: str, versions) -> list[dict]:
    return [
        {
            "filename": name,
            "version": version,
            "classification": 2,
            "department": "finance",
            "storage_path": _catalog().build_storage_name(name, version),
            "created_at": f"2026-09-{20 + version:02d}T09:00:00+08:00",
            "owner_id": "finance-owner",
            "size_bytes": 11,
            "parse_status": "ready",
        }
        for version in versions
    ]


class _Engine:
    """只替身引擎：真 SQL / 真参数 / 真 fetchall 都跑，连 LIMIT 也照吃。

    「单行读」这句判据必须能被数出来，所以 `fetchall()` 只交回引擎真读物化的行数；
    把 SQL 里的 LIMIT 摘掉，这里就多交一行，本件当场红。
    """

    def __init__(self, rows):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE document_versions (
                filename TEXT NOT NULL,
                version INTEGER NOT NULL,
                classification INTEGER NOT NULL DEFAULT 1,
                department TEXT,
                storage_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                owner_id TEXT,
                size_bytes INTEGER,
                parse_status TEXT NOT NULL DEFAULT 'pending',
                UNIQUE (filename, version)
            )
            """
        )
        for row in rows:
            self.connection.execute(
                "INSERT INTO document_versions (filename, version, classification, department,"
                " storage_path, created_at, owner_id, size_bytes, parse_status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["filename"], row["version"], row["classification"], row["department"],
                    row["storage_path"], row["created_at"], row["owner_id"], row["size_bytes"],
                    row["parse_status"],
                ),
            )
        self.statements: list[tuple[str, tuple]] = []
        self.materialized = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        text = " ".join(str(sql).split())
        self.statements.append((text, tuple(params)))
        rows = self.connection.execute(text.replace("%s", "?"), tuple(params)).fetchall()
        self.materialized += len(rows)
        self._rows = [dict(row) for row in rows]
        return self

    def fetchall(self):
        return list(self._rows)


def _database_leg(monkeypatch, rows):
    catalog = _catalog()
    engine = _Engine(rows)
    monkeypatch.setattr(catalog, "_database_available", lambda: True)
    monkeypatch.setattr(catalog, "_ensure", lambda: None)
    monkeypatch.setattr(catalog, "_conn", lambda: engine)
    return engine
# ==================== catalog 侧：单行读真的只读一行 ====================


def test_the_single_row_read_asks_for_one_row_and_gets_one_row(monkeypatch, tmp_path):
    catalog = _catalog()
    engine = _database_leg(monkeypatch, _rows("policy.txt", (2, 5, 7)))
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))

    row = catalog.latest_document_version("policy.txt")

    assert isinstance(row, dict), "单行读交回的不是「一行」：%r" % (row,)
    assert row["version"] == 7, row
    assert len(engine.statements) == 1, "判定那发读不该走第二趟：%s" % engine.statements
    sql, params = engine.statements[0]
    assert "ORDER BY version DESC" in sql, sql
    assert sql.rstrip().endswith("LIMIT %s"), "单行读没有把 LIMIT 落到 SQL 尾巴上：%s" % sql
    assert params == ("policy.txt", 1), "绑到 LIMIT 上的不是 1：%s" % (params,)


def test_the_full_listing_still_asks_for_the_whole_history_without_a_limit(monkeypatch, tmp_path):
    """默认那一支逐字不变：不带 limit 的 SQL 里一枚 LIMIT 都不许出现（响应正文靠它）。"""
    catalog = _catalog()
    engine = _database_leg(monkeypatch, _rows("policy.txt", (2, 5, 7)))
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))

    rows = catalog.list_document_versions("policy.txt")

    assert [row["version"] for row in rows] == [7, 5, 2], rows
    assert "LIMIT" not in engine.statements[0][0], engine.statements[0][0]
    assert engine.statements[0][1] == ("policy.txt",), engine.statements[0][1]


def test_the_single_row_read_costs_one_row_even_when_the_history_is_long(monkeypatch, tmp_path):
    """判据 a 的反面形状：判定读一行 vs 读全量，在物化行数上必须数得出来。"""
    catalog = _catalog()
    engine = _database_leg(monkeypatch, _rows("policy.txt", tuple(range(1, 11))))
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))

    assert catalog.latest_document_version("policy.txt")["version"] == 10
    assert engine.materialized == 1, "判定这一发物化了 %d 行：单行读被换回了全量读" % engine.materialized

    engine2 = _database_leg(monkeypatch, _rows("policy.txt", tuple(range(1, 11))))
    catalog.list_document_versions("policy.txt")
    assert engine2.materialized == 10, engine2.materialized


def test_the_offline_leg_answers_the_newest_row_or_nothing(monkeypatch, tmp_path):
    """库不在位的那一支同样只交回最新一行；台账没这份文档就交回 None（404 那张脸的输入）。"""
    catalog = _catalog()
    for version in (2, 7):
        # 离线台账的取名口径由 build_storage_name 说：policy.txt 的 v2 叫 policy__v2.txt
        (tmp_path / catalog.build_storage_name("policy.txt", version)).write_text("body", encoding="utf-8")
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "_database_available", lambda: False)

    row = catalog.latest_document_version("policy.txt")
    assert isinstance(row, dict) and row["version"] == 7, row
    assert catalog.latest_document_version("absent.txt") is None


# ==================== 路由侧：判定那一刻，只发生过一次读数 ====================


def _chat():
    from app.api.v1 import chat

    return chat


def _judged_after_one_row(log_at_judgment, single_calls, full_calls):
    """把「判定之前只读一行」写成一把可复用的尺（量现场，也拿来量旧序自证）。"""
    return bool(
        single_calls == 1
        and full_calls == 0
        and log_at_judgment == ["single"]
    )


def test_the_route_judges_before_it_reads_the_full_history(monkeypatch):
    chat = _chat()
    log: list[str] = []
    snapshot: dict[str, object] = {}
    row = {
        "filename": "policy.txt",
        "version": 7,
        "classification": 2,
        "department": "finance",
        "storage_path": "policy.txt__v7.txt",
        "owner_id": "finance-owner",
    }

    def _single(_name):
        log.append("single")
        return dict(row)

    def _full(_name):
        log.append("list")
        return [dict(row)]

    original_decision = chat._document_authorization_decision

    def _spy_decision(principal, filename, version, action):
        # 只取第一次判定那一刻：响应侧的 _classify_document_rows 会再判一次，不许把它覆写进取证
        snapshot.setdefault("log", list(log))
        snapshot.setdefault("row", version)
        return original_decision(principal, filename, version, action)

    monkeypatch.setattr(chat, "latest_document_version", _single)
    monkeypatch.setattr(chat, "list_document_versions", _full)
    monkeypatch.setattr(chat, "_document_authorization_decision", _spy_decision)
    monkeypatch.setattr(chat, "record_audit", lambda *args, **kwargs: {})

    import asyncio

    from app.agents.contracts import Principal

    principal = Principal.from_user(
        {"id": "fin", "username": "fin", "role": "manager", "department": "finance"}
    )
    request = _fake_request(principal)
    payload = asyncio.run(chat.document_version_history("policy.txt", request))

    assert snapshot["row"] is not None and snapshot["row"] != {}, "判定没有输入行"
    assert _judged_after_one_row(
        snapshot["log"], snapshot["log"].count("single"), snapshot["log"].count("list")
    ), (
        "判定那一刻的读数记录不合规：%s（判据 a：单行读被换回全量读就是这个形状）" % (snapshot["log"],)
    )
    assert payload["versions"], "响应正文的全量读没接上"


def _fake_request(principal):
    """只给路由真读的那一格：`principal_from_request` 只问 `request.state.principal`。"""
    return type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": principal.username})()},
    )()


def test_teeth_a_the_ruler_fires_on_the_legacy_shape():
    """量具自证：落码前的旧序（先取全量、`versions[0]` 当判定输入）必须被同一把尺判红。"""
    log: list[str] = []
    snapshot: dict[str, list] = {}

    def legacy_route(_name):
        log.append("list")  # 先取全量
        versions = [{"version": 7}]
        snapshot["log"] = list(log)
        _ = versions[0]  # 判定输入来自那次全量读
        log.append("response")
        return versions

    legacy_route("policy.txt")
    single_calls = log.count("single")
    full_before = snapshot["log"].count("list")
    assert not _judged_after_one_row(snapshot["log"], single_calls, full_before), (
        "旧序形状居然过了判据 a：这把尺是空的，本单的绿不算数"
    )