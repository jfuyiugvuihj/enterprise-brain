"""R248 J-1 —— 产物登记落在 ``artifacts`` 表上，"进程重启"之后逐字段读得回来。

病：``ArtifactRegistry`` 的自述是「A JSON-backed local registry until the canonical
Artifact table is integrated」，登记写进 ``static/.artifact-metadata.json`` —— 进程重启靠
文件侥幸，多副本（``deploy/start_workers.ps1`` 起 ``-Workers 3``）直接不共享。

本文件把「表是唯一事实源」钉成读数，不钉成说法：

* 写：SQL 由 ``app.storage.persistence.PostgresPersistenceAdapter`` 真生成，假连接逐字记录；
* 读：新实例（＝重启后的那个进程）只能从假表里读回来，读不回来就是红；
* 一条真连接都不许开：``no_real_driver_connect`` 是哨兵，范式与禁库口径抄
  ``tests/test_r229_connect_retry.py:117-127`` 与 ``tests/conftest.py:41-53``。
"""
import dataclasses
import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.storage import artifacts as artifact_module
from app.storage.artifacts import (
    ARTIFACT_COLLECTION,
    ArtifactRegistry,
    InProcessArtifactStore,
    _as_datetime,
)
from app.storage.persistence import PersistenceWriteError, PostgresPersistenceAdapter

# 真实驱动在这里只用来取异常类的形状（psycopg.OperationalError 就是现网那枚），不拿它建连。
psycopg = pytest.importorskip("psycopg")

INSERT_RE = re.compile(
    r"^INSERT INTO (\w+) \(([^)]*)\) VALUES \(([^)]*)\) ON CONFLICT \((\w+)\) DO UPDATE SET (.+)$",
    re.IGNORECASE,
)
SELECT_RE = re.compile(
    r"^SELECT (.+) FROM (\w+)(?: WHERE (\w+) = %s)?(?: ORDER BY (\w+) DESC)?$",
    re.IGNORECASE,
)
TIMESTAMPTZ_COLUMNS = frozenset({"created_at", "expires_at", "deleted_at"})


class _Result:
    """``dict_row`` 口径的假结果集：行就是 dict，适配器的 ``_as_record`` 两条腿都走得通。"""

    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return dict(self._rows[0]) if self._rows else None

    def fetchall(self):
        return [dict(row) for row in self._rows]


class _FakePostgres:
    """一张假的 ``artifacts`` 表。

    刻意照真库的样子做四件事，少一件 J-1 就退化成自证：

    1. 只存被写到的列 —— 没写的列读回来就是没有，"表里有 owner 列、代码从来不写"骗不过去；
    2. ``TIMESTAMPTZ`` 写进去是 datetime、读回来也是 datetime，不是我们递进去的那枚字符串；
    3. ``jsonb`` 读回来是 dict（``json_as_text=True`` 那一枚假库反过来给文本，验另一条腿）；
    4. 主键冲突按 ``ON CONFLICT DO UPDATE`` 合并，语义与 upsert 相同。
    """

    def __init__(self, *, json_as_text=False, fail_reads=False):
        self.rows: dict[str, dict] = {}
        self.statements: list[tuple[str, tuple]] = []
        self.connections = 0
        self.json_as_text = json_as_text
        self.fail_reads = fail_reads

    def adapter(self):
        return PostgresPersistenceAdapter(self.connect)

    def connect(self):
        self.connections += 1
        return _FakeConnection(self)


class _FakeConnection:
    def __init__(self, db):
        self.db = db
        self.commits = 0
        self.closed = False

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        values = tuple(params or ())
        self.db.statements.append((text, values))
        match = INSERT_RE.match(text)
        if match:
            return self._insert(match, values)
        match = SELECT_RE.match(text)
        if match:
            return self._select(match, values)
        raise AssertionError(f"R248 假库收到意料之外的语句：{text}")

    def _insert(self, match, values):
        table, columns, placeholders, key_column, assignments = match.groups()
        names = [item.strip() for item in columns.split(",")]
        assert table == ARTIFACT_COLLECTION, table
        assert len(names) == len(placeholders.split(",")) == len(values), (names, values)
        assert key_column == "artifact_id", key_column
        written = {
            item.split("=")[0].strip().upper()
            for item in re.split(r",(?![^{]*\})", assignments)
        }
        assert written == {name.upper() for name in names if name != key_column}, assignments
        row = {}
        for name, value in zip(names, values):
            if name in TIMESTAMPTZ_COLUMNS and value is not None:
                moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                assert moment.tzinfo is not None, f"{name} 写进了不带时区的时间：{value!r}"
                row[name] = moment
            elif name == "metadata" and isinstance(value, str):
                # jsonb 列存的是文档，不是我们递进去的那段文本；不照这一笔，
                # json_as_text 那枚用例就是在比两段文本，而不是比一个 loader。
                row[name] = json.loads(value)
            else:
                row[name] = value
        key = str(row[key_column])
        stored = dict(self.db.rows.get(key) or {})
        stored.update(row)
        self.db.rows[key] = stored
        return _Result([])

    def _select(self, match, values):
        if self.db.fail_reads:
            raise psycopg.OperationalError("fake outage: the table is not reachable")
        names = [item.strip() for item in match.group(1).split(",")]
        assert match.group(2) == ARTIFACT_COLLECTION, match.group(2)
        where_column, order_column = match.group(3), match.group(4)
        if where_column:
            row = self.db.rows.get(str(values[0]))
            rows = [row] if row is not None else []
        else:
            rows = list(self.db.rows.values())
            if order_column:
                rows = sorted(
                    rows,
                    key=lambda item: item.get(order_column) or datetime.min.replace(tzinfo=timezone.utc),
                    reverse=True,
                )
        projected = []
        for row in rows:
            item = {}
            for name in names:
                value = row.get(name)
                if name == "metadata" and self.db.json_as_text and value is not None:
                    value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                item[name] = value
            projected.append(item)
        return _Result(projected)

    def commit(self):
        self.commits += 1

    def rollback(self):
        return None

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def no_real_driver_connect(monkeypatch):
    """哨兵：本文件任何用例都不许经真驱动建连（假连接一律走 ``_FakePostgres.connect``）。"""

    def refuse(*args, **kwargs):
        raise AssertionError(
            "tests/test_r248_artifact_table_source.py 试图开一条真 PostgreSQL 连接；"
            "J-1 全程只用假库，按 R20 的口径判失败"
        )

    monkeypatch.setattr(psycopg, "connect", refuse, raising=False)


def _principal(username="finance-manager", department="finance", role="manager"):
    from app.agents.contracts import Principal

    return Principal.from_user(
        {"id": username, "username": username, "role": role, "department": department}
    )


def _registry(db, tmp_path, **kwargs):
    """一枚"进程"里的 registry：root 固定，所以两张假进程看见的是同一个 root 与同一张表。"""
    root = tmp_path / "static"
    root.mkdir(parents=True, exist_ok=True)
    return ArtifactRegistry(root, metadata_path=tmp_path / "sidecar.json", persistence=db.adapter(), **kwargs)


def _store_file(registry, name, payload=b"\x89PNG\r\n\x1a\n chart bytes"):
    path = registry.root / name
    path.write_bytes(payload)
    return path


def _wire(record):
    """一枚记录能被读到的每一个字：列字段 + 派生属性 + 交付串 + 授权入口。"""
    observed = {field.name: getattr(record, field.name) for field in dataclasses.fields(record)}
    observed.update(
        {
            "artifact_type": record.artifact_type,
            "filename": record.filename,
            "storage_path": record.storage_path,
            "department_ids": record.department_ids,
            "classification": record.classification,
            "visibility": record.visibility,
            "media_type": record.media_type,
            "content_url": record.content_url,
            "download_url": record.download_url,
            "is_active": record.is_active(),
            "public_payload": record.public_payload(),
            "resource_scope": record.resource_scope.model_dump(),
        }
    )
    return observed


def test_the_sentinel_itself_would_catch_a_real_connect():
    """本文件的禁库哨兵不是装饰：谁绕过假库直接 ``psycopg.connect``，当场炸。"""
    with pytest.raises(AssertionError, match="真 PostgreSQL 连接"):
        psycopg.connect("postgresql://nobody@postgres:5432/nothing")


def test_a_restarted_process_reads_the_same_rows_back_field_for_field(tmp_path):
    db = _FakePostgres()
    first = _registry(db, tmp_path)
    chart = _store_file(first, "revenue.png")
    report = _store_file(first, "board-report.pdf", b"%PDF-1.4 board")
    horizon = datetime.now(timezone.utc) + timedelta(days=7)

    registered = [
        first.register(chart, artifact_type="chart", principal=_principal()),
        first.register(
            report,
            artifact_type="report",
            principal=_principal("keeper"),
            classification="confidential",
            visibility="department",
            source_version_id="ds-1:v3",
            expires_at=horizon,
        ),
    ]
    before = [_wire(record) for record in registered]
    listed_before = [record.artifact_id for record in first.list_active()]
    stored_moments = {
        record.artifact_id: (
            db.rows[record.artifact_id]["created_at"],
            db.rows[record.artifact_id]["expires_at"],
        )
        for record in registered
    }

    # 「重启」＝新进程、新 registry、同一张表：它没有任何办法继承上一进程的内存。
    second = _registry(db, tmp_path)
    mark = len(db.statements)

    after = [_wire(second.get(record.artifact_id)) for record in registered]
    assert after == before, "重启后读数变了"
    assert [record.artifact_id for record in second.list_active()] == listed_before
    assert [_wire(record) for record in second.list_active()] == [
        _wire(second.get(artifact_id)) for artifact_id in listed_before
    ]
    # 恢复全靠读：重启后的这一程一句 INSERT 都没发，问的又确实是指名这枚列的 SELECT。
    restarted_statements = [sql for sql, _ in db.statements[mark:]]
    assert restarted_statements, "重启后的读数没有问过表"
    assert all(sql.upper().startswith("SELECT") for sql in restarted_statements), restarted_statements
    assert any("WHERE artifact_id = %s" in sql for sql in restarted_statements)
    assert any("ORDER BY created_at DESC" in sql for sql in restarted_statements)
    # 归一化必须仍指向同一瞬：不是"字符串自己跟自己对齐"。
    for record in registered:
        created, expires = stored_moments[record.artifact_id]
        wire = _wire(second.get(record.artifact_id))
        assert _as_datetime(wire["created_at"]) == created
        assert (_as_datetime(wire["expires_at"]) if wire["expires_at"] else None) == expires


def test_the_write_names_the_owner_and_the_lifecycle_columns(tmp_path):
    db = _FakePostgres()
    registry = _registry(db, tmp_path)
    path = _store_file(registry, "revenue.png")

    record = registry.register(path, artifact_type="chart", principal=_principal("keeper"))

    insert_sql, insert_params = next(
        (sql, params) for sql, params in db.statements if sql.upper().startswith("INSERT")
    )
    columns = [
        item.strip()
        for item in insert_sql.split("(", 1)[1].split(")")[0].split(",")
    ]
    # 稳定 ID / owner / 生命周期三件必须落在列上（roadmap V2 硬要求）。
    for column in (
        "artifact_id",
        "owner_id",
        "status",
        "created_at",
        "expires_at",
        "storage_key",
        "content_sha256",
        "metadata",
    ):
        assert column in columns, f"{column} 不在 INSERT 的列里：{columns}"
    bound = dict(zip(columns, insert_params))
    assert bound["owner_id"] == "keeper"
    assert bound["status"] == "active"
    assert bound["artifact_id"] == record.artifact_id
    assert json.loads(bound["metadata"])["department_ids"] == ["finance"]


def test_reads_ask_the_table_on_every_call(tmp_path):
    db = _FakePostgres()
    registry = _registry(db, tmp_path)
    path = _store_file(registry, "revenue.png")
    record = registry.register(path, artifact_type="chart", principal=_principal())

    registry.get(record.artifact_id)
    mark = len(db.statements)
    registry.get(record.artifact_id)
    registry.get(record.artifact_id)
    selects = [sql for sql, _ in db.statements[mark:] if sql.upper().startswith("SELECT")]

    assert len(selects) == 2, f"每次 get 都要问一次表，这里问到 {len(selects)} 次"
    assert all("WHERE artifact_id = %s" in sql for sql in selects), selects


def test_a_second_worker_sees_a_retirement_without_restarting(tmp_path):
    db = _FakePostgres()
    writer = _registry(db, tmp_path)
    path = _store_file(writer, "revenue.png")
    record = writer.register(path, artifact_type="chart", principal=_principal())
    reader = _registry(db, tmp_path)  # 另一枚进程：它先起来，再看着对面把这条撤掉

    assert reader.get_active(record.artifact_id) is not None
    assert writer.soft_delete(record.artifact_id) is True

    assert reader.get(record.artifact_id).status == "deleted"
    assert reader.get_active(record.artifact_id) is None
    assert reader.list_active() == []


def test_a_row_the_table_cannot_describe_is_not_delivered(tmp_path):
    db = _FakePostgres()
    registry = _registry(db, tmp_path)
    db.rows["orphan"] = {
        "artifact_id": "orphan",
        "owner_id": "",  # 表里 owner 为空：这不是"权限弱一点的产物"，这是不可寻址的行
        "resource_type": "artifact",
        "resource_id": "orphan",
        "storage_key": str(registry.root / "revenue.png"),
        "content_sha256": "b" * 64,
        "status": "active",
    }

    assert registry.get("orphan") is None
    assert registry.list_active() == []


def test_jsonb_that_arrives_as_text_still_carries_the_scope(tmp_path):
    db = _FakePostgres(json_as_text=True)
    registry = _registry(db, tmp_path)
    path = _store_file(registry, "revenue.png")
    record = registry.register(
        path,
        artifact_type="chart",
        principal=_principal(),
        classification="confidential",
        visibility="department",
    )

    again = _registry(db, tmp_path).get(record.artifact_id)
    assert again is not None
    assert again.metadata["department_ids"] == ["finance"]
    assert _wire(again) == _wire(record)


def test_a_store_that_cannot_answer_is_not_answered_with_not_found(tmp_path):
    """源不可达时不许编造"没有这枚产物"：404 会替所有人宣布一次删除。"""
    db = _FakePostgres()
    registry = _registry(db, tmp_path)
    path = _store_file(registry, "revenue.png")
    record = registry.register(path, artifact_type="chart", principal=_principal())
    db.fail_reads = True

    with pytest.raises(PersistenceWriteError):
        registry.get(record.artifact_id)
    with pytest.raises(PersistenceWriteError):
        registry.list_active()


def _legacy_payload(registry, name="legacy-chart.png"):
    path = _store_file(registry, name, b"\x89PNG legacy")
    return {
        "artifacts": [
            {
                "artifact_id": "legacy-1",
                "artifact_type": "chart",
                "owner_id": "keeper",
                "department_ids": ["finance"],
                "classification": "internal",
                "visibility": "private",
                "storage_path": str(path),
                "filename": path.name,
                "content_sha256": "c" * 64,
                "status": "active",
                "created_at": "2026-09-01T00:00:00+00:00",
                "expires_at": None,
                "source_version_id": None,
            }
        ]
    }


def test_the_sidecar_is_imported_read_once_and_left_alone(tmp_path):
    db = _FakePostgres()
    seed = _registry(db, tmp_path)
    payload = _legacy_payload(seed)
    sidecar = tmp_path / "sidecar.json"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    before = sidecar.read_bytes()

    imported = _registry(db, tmp_path)
    record = imported.get("legacy-1")

    assert record is not None
    assert record.owner_id == "keeper"
    assert record.department_ids == ["finance"]
    assert record.storage_path == payload["artifacts"][0]["storage_path"]
    assert imported.legacy_imported == 1
    assert imported.legacy_skipped == 0
    assert sidecar.read_bytes() == before
    assert sorted(item.name for item in tmp_path.iterdir()) == ["sidecar.json", "static"]


def test_the_sidecar_cannot_resurrect_a_retired_row(tmp_path):
    """导入只补空缺：表已答的 id 一律跳过，否则 JSON 会把已撤的产物重新点活。"""
    db = _FakePostgres()
    writer = _registry(db, tmp_path)
    path = _store_file(writer, "legacy-chart.png", b"\x89PNG legacy")
    record = writer.register(path, artifact_type="chart", principal=_principal("keeper"))
    writer.soft_delete(record.artifact_id)

    entry = _legacy_payload(writer, "legacy-chart.png")["artifacts"][0]
    entry["artifact_id"] = record.artifact_id
    entry["storage_path"] = str(path)
    entry["content_sha256"] = record.content_sha256
    (tmp_path / "sidecar.json").write_text(json.dumps({"artifacts": [entry]}), encoding="utf-8")

    restarted = _registry(db, tmp_path)

    assert restarted.legacy_imported == 0
    assert restarted.legacy_skipped == 1
    assert restarted.get(record.artifact_id).status == "deleted"
    assert restarted.get_active(record.artifact_id) is None


def test_a_malformed_sidecar_does_not_stop_the_platform(tmp_path):
    (tmp_path / "sidecar.json").write_text("{ not json", encoding="utf-8")

    registry = _registry(_FakePostgres(), tmp_path)

    assert registry.legacy_imported == 0
    assert registry.list_active() == []


def test_the_shipped_singleton_never_falls_back_to_the_in_process_store():
    """生产那枚 registry 必须问控制面存储；in-process 只留给显式不要存储的调用方。"""
    assert artifact_module.artifact_registry.persistence is artifact_module._PERSISTENCE
    assert not isinstance(
        artifact_module.artifact_registry.persistence, InProcessArtifactStore
    )


def test_a_registry_that_declines_storage_says_so(tmp_path):
    registry = ArtifactRegistry(tmp_path / "static", metadata_path=tmp_path / "sidecar.json")
    path = _store_file(registry, "revenue.png")

    assert isinstance(registry.persistence, InProcessArtifactStore)
    assert registry.persistence.durable is False
    record = registry.register(path, artifact_type="chart", principal=_principal())
    assert registry.get(record.artifact_id).artifact_type == "chart"

    with pytest.raises(ValueError, match="owner_id"):
        registry.persistence.upsert(ARTIFACT_COLLECTION, "x", {"artifact_id": "x"})
