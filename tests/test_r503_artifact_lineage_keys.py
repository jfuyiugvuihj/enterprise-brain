# -*- coding: utf-8 -*-
"""R503 · 成果回读链缺两把键：取证钉 + 三把反证刀（判据①②⑦）。

现读 @092fb34，三张账：

  表账   migrations/0001_core_resource_versions.sql:36-49  artifacts 的列全集里**没有**
         session_id，也没有 request_id；能装额外事实的只有 metadata JSONB 一格。
  写点账 app/storage/artifacts.py::register() 只往 metadata 写 SCOPE_METADATA_KEYS 那五枚，
         且两枚生产写点（app/api/v1/data.py:514、app/agents/tools.py:260）连 source_version_id
         都不喂 —— 那一列今天恒 null。
  读点账 app/api/v1/artifacts.py::_artifact_row 交回 12 枚字段，一枚生成键都不在里面；
         模块里唯一的 request_id 在删除审计那一发（:109），它记的是**删这一发的请求号**，
         不是「哪一次问答生成了这张图」。

⇒ 判据②要的「来源必须是已有落盘事实」今天不成立，本单按工单自己的口径停手只取证。
  但「不许假接入」这条不能空着，所以本件把三道门先钉上，并跑三把刀证明门有牙：

  K1 把行上今天真在的那枚来源形字段摘掉       -> 探针必须红且点名；
  K2 把一枚没有落盘来源的 request_id 接到行上  -> 探针必须红且点名（删除审计那条路）；
  K3 摘掉 metadata 白名单那一道过滤            -> 探针必须红（jsonb 后门从此无人看守）。

刀全落在**内存里的源码影子副本**（compile + exec），盘上那三件一个字都不改；
每把刀先把锚点数一遍，锚点不唯一或找不到就判定这把刀空转。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
API_MODULE = REPO_ROOT / "app" / "api" / "v1" / "artifacts.py"
STORAGE_MODULE = REPO_ROOT / "app" / "storage" / "artifacts.py"

LIST_PATH = "/api/v1/artifacts"

#: 列表行今天的字段全集（现取 app/api/v1/artifacts.py:151-165：public_payload 五枚 + update 七枚）。
ROW_KEYS = frozenset({
    "artifact_id",
    "artifact_type",
    "content_url",
    "download_url",
    "expires_at",
    "filename",
    "owner_id",
    "department_ids",
    "classification",
    "visibility",
    "created_at",
    "source_version_id",
})

#: 「哪一次问答 / 哪一次计算」这几枚键的真名，逐枚现取自 migrations 的列名。
LINEAGE_KEYS = (
    "session_id",          # agent_runs 有这一列（0002:95），artifacts 没有
    "request_id",          # agent_runs / calculation_runs / audit_events 有，artifacts 没有
    "task_id",
    "agent_run_id",
    "agent_step_id",
    "calculation_run_id",
    "trace_id",
)

# --------------------------------------------------------------------------- 探针（刀与真件共用）


def probe_row_field_set(row):
    """行上只许出现今天这 12 枚字段：多一枚要先回答「落盘在哪一列」，少一枚就是屏上又说不出来源了。"""
    missing = sorted(set(ROW_KEYS) - set(row))
    extra = sorted(set(row) - ROW_KEYS)
    assert not missing, f"列表行丢了字段，屏上再也说不出这一条的来源：{missing}"
    assert not extra, f"列表行多出没有落盘来源的字段：{extra}（先加列再来改本钉）"


def probe_no_generating_key_on_the_row(row):
    """artifacts 表里没有这几枚列，register() 也没写过它们，所以任何一枚上路都是假接入。"""
    riding = [key for key in LINEAGE_KEYS if key in row]
    assert not riding, (
        f"列表行回显了表里不存在的生成键：{riding}；"
        "artifacts 无此列、register() 无此写点，这就是拿访问者那一发冒充「哪一次问答」"
    )


def probe_metadata_stays_inside_the_allow_list(record):
    """metadata 里白名单外的键必须被读路径丢掉，否则 jsonb 就成了无人看守的第二套字段。"""
    from app.storage.artifacts import SCOPE_METADATA_KEYS

    leaked = sorted(set(record.metadata) - set(SCOPE_METADATA_KEYS))
    assert not leaked, f"白名单外的 metadata 键读回来了：{leaked}"


# --------------------------------------------------------------------------- 影子装载（盘上零改动）


def load_shadow(path, name, patches=()):
    """把盘上源码读进来、按 patches 逐枚替换、再 compile+exec 成一个独立命名空间。"""
    source = path.read_text(encoding="utf-8")
    for anchor, replacement in patches:
        hits = source.count(anchor)
        assert hits == 1, f"锚点不唯一或找不到（这把刀会空转）：{anchor!r} 命中 {hits} 次"
        source = source.replace(anchor, replacement)
    import sys
    from types import ModuleType

    #: ``@dataclass`` 会按 ``cls.__module__`` 反查 ``sys.modules[name].__dict__``，
    #: 所以必须真造一个模块对象入册，裸 dict 会在 dataclass 那一行撕。
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


SOURCE_VERSION_LINE = '            "source_version_id": record.source_version_id,'
METADATA_LOOP = "        for key in SCOPE_METADATA_KEYS:"


def sample_record(module):
    return module.ArtifactRecord(
        artifact_id="a-503",
        owner_id="keeper",
        resource_type=module.ARTIFACT_RESOURCE_TYPE,
        resource_id="a-503",
        storage_key="a-503.png",
        content_sha256="0" * 64,
        status="active",
        created_at="2026-09-29T10:00:00+00:00",
        metadata={
            "artifact_type": "chart",
            "filename": "销售额趋势.png",
            "department_ids": ["finance"],
            "classification": "internal",
            "visibility": "private",
        },
    )


def raw_stored_row(root, metadata):
    """一枚直接落到 artifacts 表形状的行（绕过 register()），用来测读路径的白名单。"""
    return {
        "artifact_id": "a-raw",
        "owner_id": "keeper",
        "resource_type": "artifact",
        "resource_id": "a-raw",
        "source_version_id": None,
        "storage_key": str(Path(root) / "a-raw.png"),
        "content_sha256": "0" * 64,
        "status": "active",
        "expires_at": None,
        "deleted_at": None,
        "created_at": "2026-09-29T10:00:00+00:00",
        "metadata": metadata,
    }


FAKE_LINEAGE_METADATA = {
    "artifact_type": "chart",
    "filename": "a-raw.png",
    "department_ids": ["finance"],
    "classification": "internal",
    "visibility": "private",
    "session_id": "sess-fake",
    "request_id": "req-fake",
}


def registry_from(module, tmp_path, persistence=None):
    from app.storage.artifacts import InProcessArtifactStore

    return module.ArtifactRegistry(
        tmp_path,
        metadata_path=tmp_path / "unused-metadata.json",
        persistence=persistence if persistence is not None else InProcessArtifactStore(),
        import_legacy_metadata=False,
    )


# --------------------------------------------------------------------------- 路由夹具（沿用同族件的搭法）


def _headers(username):
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _account(username, department="finance", role="manager"):
    return {"id": username, "username": username, "role": role, "department": department}


@pytest.fixture()
def registry(monkeypatch, tmp_path):
    from app.storage import artifacts

    instance = registry_from(artifacts, tmp_path)
    monkeypatch.setattr(artifacts, "artifact_registry", instance)
    return instance


@pytest.fixture()
def account(monkeypatch):
    from app.common import auth

    users = {}
    monkeypatch.setattr(auth, "get_user", lambda username: users.get(username))

    def add(username, department="finance", role="manager"):
        users[username] = _account(username, department, role)
        return username

    return add


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


def store(registry, username, filename, **fields):
    from app.agents.contracts import Principal

    department = fields.pop("department", "finance")
    role = fields.pop("role", "manager")
    path = registry.root / filename
    path.write_bytes(b"payload-" + filename.encode("utf-8"))
    principal = Principal.from_user(_account(username, department, role))
    return registry.register(path, artifact_type=fields.pop("artifact_type", "chart"), principal=principal, **fields)


# --------------------------------------------------------------------------- 判据① 三张账的现读读数


def test_the_row_publishes_exactly_the_fields_that_have_a_column(client, registry, account):
    account("keeper", "finance")
    store(registry, "keeper", "chart.png", source_version_id="dv-1")

    row = client.get(LIST_PATH, headers=_headers("keeper")).json()["artifacts"][0]

    assert set(row) == set(ROW_KEYS), sorted(set(row) ^ set(ROW_KEYS))
    probe_row_field_set(row)
    assert row["source_version_id"] == "dv-1", "那一枚来源形字段本来就在行上，喂了就会交回"


def test_no_key_on_the_row_names_the_generating_question_or_calculation(client, registry, account):
    """行上没有、也造不出「哪一次问答 / 哪一次计算」——这是本单停手的直接证据。"""
    account("keeper", "finance")
    account("peer", "finance")
    mine = store(registry, "keeper", "chart.png")

    own = client.get(LIST_PATH, headers=_headers("keeper")).json()["artifacts"][0]
    peer = client.get(LIST_PATH, headers=_headers("peer")).json()["artifacts"][0]

    probe_no_generating_key_on_the_row(own)
    assert not [key for key in LINEAGE_KEYS if key in own]
    assert own == peer, "同一行在两个账号眼里必须一字不差：访问者的身份不许渗进列表行"
    assert own["source_version_id"] is None, "两枚生产写点都不喂它，今天恒 null"


def test_the_two_production_writers_never_feed_the_one_lineage_shaped_column():
    """列已有、码已读、写点没喂 —— 这一格要写清，不许说成「列也没有」。"""
    writers = {
        "app/api/v1/data.py": "artifact_storage.register_artifact(",
        "app/agents/tools.py": "artifact_storage.register_artifact(",
    }
    for relative, anchor in writers.items():
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        calls = re.findall(re.escape(anchor) + r"[^)]*\)", text)
        assert len(calls) == 1, f"{relative} 的写点数变了：{len(calls)}"
        assert "source_version_id" not in calls[0], f"{relative} 今天把来源版本喂进来了，本钉要重读"


def test_a_lineage_key_pushed_into_the_metadata_jsonb_never_reaches_the_row(tmp_path):
    """不走白名单的 jsonb 后门今天被读路径丢掉：想靠它绕开加列，绕不过去。"""
    from app.storage.artifacts import ARTIFACT_COLLECTION

    instance = registry_from(__import__("app.storage.artifacts", fromlist=["x"]), tmp_path)
    instance.persistence.upsert(ARTIFACT_COLLECTION, "a-raw", raw_stored_row(tmp_path, dict(FAKE_LINEAGE_METADATA)))

    record = instance._read("a-raw")

    assert record is not None
    probe_metadata_stays_inside_the_allow_list(record)
    assert "session_id" not in record.metadata and "request_id" not in record.metadata


def test_the_only_request_id_in_the_module_names_the_deleting_call():
    """删除审计那一发确实带着 request_id，但它记的是「谁删的」，不是「哪一次问答生成的」。"""
    text = API_MODULE.read_text(encoding="utf-8")

    assert text.count("request_id=") == 1, "artifacts.py 里的 request_id 用法变了，要重读它接的是哪条腿"
    audit_leg = re.search(r"def delete_artifact[\s\S]*$", text)
    assert audit_leg and "request_id=principal.request_id" in audit_leg.group(0), "那一枚 request_id 不在删除审计里，判据要重下"
    assert "def _artifact_row(record)" in text, "_artifact_row 的签名变了，行上可能出现访问者身份"


# --------------------------------------------------------------------------- 判据⑦ 三把反证刀


def test_control_the_real_modules_pass_every_probe(tmp_path):
    """对照：盘上源码一枚都不许红，否则下面的红没有意义。"""
    from app.api.v1.artifacts import _artifact_row
    from app.storage.artifacts import ARTIFACT_COLLECTION
    import app.storage.artifacts as storage_module

    record = sample_record(storage_module)
    probe_row_field_set(_artifact_row(record))
    probe_no_generating_key_on_the_row(_artifact_row(record))

    instance = registry_from(storage_module, tmp_path)
    instance.persistence.upsert(ARTIFACT_COLLECTION, "a-raw", raw_stored_row(tmp_path, dict(FAKE_LINEAGE_METADATA)))
    probe_metadata_stays_inside_the_allow_list(instance._read("a-raw"))


def test_blade_k1_dropping_the_source_column_key_goes_red():
    """刀①：把行上今天真在的来源形字段摘掉 —— 屏上再也说不出来源，必须红且点名。"""
    shadow = load_shadow(API_MODULE, "r503_k1", ((SOURCE_VERSION_LINE, ""),))
    row = shadow._artifact_row(sample_record(__import__("app.storage.artifacts", fromlist=["x"])))

    with pytest.raises(AssertionError) as caught:
        probe_row_field_set(row)
    assert "source_version_id" in str(caught.value), str(caught.value)


def test_blade_k2_faking_a_request_id_onto_the_row_goes_red():
    """刀②：落盘里没有这一键却硬回显（拿删除审计那条路径的请求号冒充生成号）。"""
    injected = SOURCE_VERSION_LINE + '\n            "request_id": "req-" + record.artifact_id[:8],'
    shadow = load_shadow(API_MODULE, "r503_k2", ((SOURCE_VERSION_LINE, injected),))
    row = shadow._artifact_row(sample_record(__import__("app.storage.artifacts", fromlist=["x"])))

    assert row["request_id"].startswith("req-"), "刀没切进去"
    with pytest.raises(AssertionError) as caught:
        probe_no_generating_key_on_the_row(row)
    assert "request_id" in str(caught.value), str(caught.value)


def test_blade_k3_removing_the_metadata_allow_list_goes_red(tmp_path):
    """刀③：摘掉读路径那一道白名单过滤 —— 假血缘键从此顺着记录上路，必须红。"""
    import app.storage.artifacts as storage_module

    patched = registry_from(storage_module, tmp_path)
    patched.persistence.upsert(
        storage_module.ARTIFACT_COLLECTION, "a-raw", raw_stored_row(tmp_path, dict(FAKE_LINEAGE_METADATA))
    )
    assert "session_id" not in patched._read("a-raw").metadata, "对照已经先红，刀不必跑"

    crippled_root = tmp_path / "crippled"
    crippled_root.mkdir()
    shadow = load_shadow(
        STORAGE_MODULE,
        "r503_k3",
        ((METADATA_LOOP, "        for key in metadata:"),),
    )
    shadow_registry = registry_from(shadow, crippled_root)
    shadow_registry.persistence.upsert(
        storage_module.ARTIFACT_COLLECTION, "a-raw", raw_stored_row(crippled_root, dict(FAKE_LINEAGE_METADATA))
    )

    with pytest.raises(AssertionError) as caught:
        probe_metadata_stays_inside_the_allow_list(shadow_registry._read("a-raw"))
    assert "session_id" in str(caught.value), str(caught.value)