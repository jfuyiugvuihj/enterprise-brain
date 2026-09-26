"""R256 判据① —— ``artifacts.deleted_at`` 落进控制面适配器的列元组，而且真的落得进库。

跟进单 §100.4 判据①的原话是「今天 11 枚不含它，所以 R248 那枚退役只活在内存里，进程一重启
就复活」。列数与「不含它」都成立（现取：``_TABLES["artifacts"].columns`` 今天 12 枚，改之前
11 枚）；**「重启就复活」这半句不成立**，本件最后一枚用例把两种说法分开钉住：``status`` 从来
在列元组里，所以退役本身是能重启的，真正丢的只有 ``deleted_at`` 那一枚时间戳——一行说得出
"它退了"、说不出"它什么时候退的"，而这两格在审计里不是同一句话。

靶子仍然取迁移原文：0001 建 ``artifacts`` 时就带着 ``deleted_at TIMESTAMPTZ``，所以判据①不需要
新迁移，欠的只有适配器那一个名字。三处名单（表 / 记录 / 适配器）必须逐字同一份，就是本件第一格。
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from _r250_fake_postgres import FakePostgres
from app.agents.contracts import Principal
from app.storage import persistence as persistence_module
from app.storage.artifacts import ARTIFACT_COLUMNS, ArtifactRegistry
from app.storage.persistence import PostgresPersistenceAdapter
from test_r248_artifact_column_alignment import _artifact_columns

_OWNER = {"id": "keeper", "username": "keeper", "role": "manager", "department": "finance"}


def _registry(engine: FakePostgres, root: Path) -> ArtifactRegistry:
    """同一枚库，另一枚登记表——"重启"在这里就是换一个进程里的新对象。

    ``import_legacy_metadata=False`` 关掉侧车导入那条路：本件判的是列元组与表之间的那一段，
    不是 R248 之前那本 JSON 账能不能被重新读进来。
    """
    return ArtifactRegistry(
        root / "static",
        metadata_path=root / "sidecar.json",
        persistence=PostgresPersistenceAdapter(engine.connection_factory),
        import_legacy_metadata=False,
    )


def _chart(root_parent: Path) -> Path:
    """登记表只收自己根目录里的字节（``_contained_path``），所以图就落在那儿。"""
    root = root_parent / "static"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "revenue.png"
    path.write_bytes(b"\x89PNG chart bytes")
    return path


def _registered(tmp_path: Path):
    engine = FakePostgres()
    registry = _registry(engine, tmp_path)
    path = _chart(tmp_path)
    record = registry.register(
        path, artifact_type="chart", principal=Principal.from_user(_OWNER)
    )
    return engine, registry, record


# ------------------------------------------------------ 三处名单必须是同一份十二枚


def test_the_adapter_names_every_column_the_artifacts_table_declares():
    """表（0001 的建表体）↔ 记录（``ARTIFACT_COLUMNS``）↔ 写库那行（``_TABLES``）。

    R248 已经钉住了前两处相等；判据①缺的是第三处，所以这里只补第三处，并把"缺的那一枚叫什么"
    钉死在名字上，而不是钉成一个枚数——枚数对了而名字不对的改法（删掉别的列补一个数）也红。
    """
    declared = set(_artifact_columns())
    columns = persistence_module._TABLES["artifacts"].columns

    assert "deleted_at" in columns
    assert tuple(columns) == ARTIFACT_COLUMNS, (
        "适配器点名的列必须逐字就是记录携带的那一份，顺序也算："
        "INSERT 的列序就是这个元组的序"
    )
    assert set(columns) == declared, {
        "adapter_only": sorted(set(columns) - declared),
        "table_only": sorted(declared - set(columns)),
    }
    assert len(columns) == len(declared) == 12


# ------------------------------------------------------------------ 落库与重启那格


def test_a_retired_artifact_comes_back_retired_and_stamped(tmp_path):
    """退役写进表；换一枚登记表读回来，状态与退役时刻都还在。"""
    engine, registry, record = _registered(tmp_path)

    assert registry.soft_delete(record.artifact_id) is True
    before = registry.get(record.artifact_id)

    assert before is not None
    assert before.status == "deleted"
    assert before.deleted_at, "soft_delete 盖的那枚时间戳必须写出去，不许只活在内存里"

    after = _registry(engine, tmp_path).get(record.artifact_id)

    assert after is not None, "同一枚库，重启之后连行都读不到"
    assert after.status == "deleted"
    assert after.deleted_at == before.deleted_at, "退役的时刻是审计要读的那一格，重写一次不许换值"


def test_an_active_artifact_gains_no_timestamp_from_the_new_column(tmp_path):
    """反向：列进了元组不等于值凭空长了出来——没退过的行，重启后仍然没有退役时刻。"""
    engine, registry, record = _registered(tmp_path)

    after = _registry(engine, tmp_path).get(record.artifact_id)

    assert after is not None
    assert after.status == "active"
    assert not after.deleted_at, repr(after.deleted_at)


# ------------------------------------------------- 反证：把那一枚名字摘掉，债就回来了


def test_dropping_the_name_from_the_tuple_reproduces_the_debt(tmp_path, monkeypatch):
    """摘掉判据①那一行会红成什么样，这里当场演一遍——并且顺手把派工词订正了。

    把 ``deleted_at`` 从列元组里摘掉就是 R248 落地的形状。重放同一个场景：``status`` 仍然活着
    （它一直在那 11 枚里），所以"进程一重启就复活"是假话；丢的只有时间戳。这一格同时是那句话的
    反证与判据①的牙齿：谁把名字改回去，``test_a_retired_artifact_comes_back_retired_and_stamped``
    立刻红，而不是安静地少写一列。
    """
    definition = persistence_module._TABLES["artifacts"]
    monkeypatch.setitem(
        persistence_module._TABLES,
        "artifacts",
        replace(
            definition,
            columns=tuple(name for name in definition.columns if name != "deleted_at"),
        ),
    )
    engine = FakePostgres()
    registry = _registry(engine, tmp_path)
    record = registry.register(
        _chart(tmp_path), artifact_type="chart", principal=Principal.from_user(_OWNER)
    )

    assert registry.soft_delete(record.artifact_id) is True
    stored = _registry(engine, tmp_path).get(record.artifact_id)

    assert stored is not None
    assert stored.status == "deleted", "派工词那句「重启就复活」不成立：status 从来在列元组里"
    assert not stored.deleted_at, "这一枚才是 R248 真正丢掉的格子"