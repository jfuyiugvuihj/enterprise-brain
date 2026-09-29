# -*- coding: utf-8 -*-
"""R509 · 成果血缘落地：两枚可空列 + 一处写点真源 + 两脸读点（判据①②③④⑤）。

上一枚单 R503 交回的是「不加列就接不住『哪一次问答』」，本单把那一半落地：

  列   migrations/0017_artifact_generation_lineage.sql 给 artifacts 追加两枚**可空** TEXT 列
       session_id / request_id。存量行全 NULL：无 DEFAULT、无回填、本文件一条 UPDATE 都没有。
  写   ArtifactRegistry.register()/register_artifact() 收这两枚关键字实参；两枚生产写点各自把
       自己那一发的轮身份递进来——app/api/v1/data.py 用路由 Principal 的 request_id（直连没有
       会话，那一格就留 NULL），app/agents/tools.py 用 configurable 的 thread_id 加上
       span_identity() 的 request_id。键名的拼装全仓只有一处，本件用 AST 闸钉住，不靠 review 记忆。
  读   ArtifactRecord.lineage_payload() 只交回「登记过的那几枚」，列表行 row.update(...) 它
       ⇒ 没登记的行整格缺席，永远不是空串、不是 null、不是「—」。

在册夹具一律复用同族件（tests/test_r503_artifact_lineage_keys.py、tests/_r250_fake_postgres.py），
本件不自建第二套。反证刀 K1..K6 全落在**内存里的源码影子副本**（compile + exec），
盘上的在册件一个字都不改。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from _r250_fake_postgres import FakePostgres
from test_r503_artifact_lineage_keys import (
    API_MODULE,
    LIST_PATH,
    _headers,
    account,
    client,
    load_shadow,
    registry,
    registry_from,
    sample_record,
    store,
)

from app.storage.artifacts import ARTIFACT_LINEAGE_COLUMNS as LINEAGE_KEYS
from app.storage.artifacts import SCOPE_METADATA_KEYS, ArtifactRegistry
from app.storage.persistence import PostgresPersistenceAdapter

REPO_ROOT = Path(__file__).resolve().parents[1]
STORAGE_MODULE = REPO_ROOT / "app" / "storage" / "artifacts.py"
PERSISTENCE_MODULE = REPO_ROOT / "app" / "storage" / "persistence.py"
MIGRATION = REPO_ROOT / "migrations" / "0017_artifact_generation_lineage.sql"
WRITERS = ("app/api/v1/data.py", "app/agents/tools.py")

#: 列表行今天合法的字段全集 = 12 枚既有键 + 0017 那两枚（只许这一对，多一枚就红）。
BASE_ROW_KEYS = frozenset({
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

OWNER = {"id": "keeper", "username": "keeper", "role": "manager", "department": "finance"}

# --------------------------------------------------------------------------- 探针（刀与真件共用）


def probe_lineage_row(row, record, *, session=None, request=None):
    """行上的血缘键必须逐字等于那一行存储的列值；没登记的必须整格缺席。

    三个方向都判：少了（有血缘却不报）、多了（没血缘却补了一格）、改了（值不是列值）全红。
    """
    from app.storage.artifacts import normalize_lineage

    expected = {k: v for k, v in normalize_lineage(vars(record)).items() if v is not None}
    published = {k: row[k] for k in LINEAGE_KEYS if k in row}
    assert published == expected, f"血缘行不对：屏上={published} 列里={expected}"
    if session is not None:
        assert published.get("session_id") == session, "会话号没回到行上：『哪一次问答』又说不出了"
    if request is not None:
        assert published.get("request_id") == request, "请求号没回到行上：『哪一笔请求』又说不出了"


def probe_row_field_set(row):
    """十二枚下限一枚不少；多出来的只许是这两枚有列的血缘键。"""
    missing = sorted(BASE_ROW_KEYS - set(row))
    extra = sorted(set(row) - BASE_ROW_KEYS - set(LINEAGE_KEYS))
    assert not missing, f"列表行丢了既有字段：{missing}"
    assert not extra, f"列表行多出没有落盘来源的字段：{extra}"


def probe_no_placeholder_lineage(row):
    """"缺席"只能靠缺席表达：不许出现空串、"null"、"—"、0 这类顶替品。"""
    for key in LINEAGE_KEYS:
        if key not in row:
            continue
        value = row[key]
        assert isinstance(value, str) and value.strip(), (
            f"血缘键 {key} 带着一个顶替品回到行上：{value!r}"
        )


# --------------------------------------------------------------------------- 落库腿的夹具（复用既有 double）


def postgres_registry(tmp_path):
    """一台假库 + 一枚登记表：与 tests/test_r256_artifact_deleted_at_lands.py 同一搭法。"""
    engine = FakePostgres()
    root = tmp_path / "static"
    root.mkdir(parents=True, exist_ok=True)
    instance = ArtifactRegistry(
        root,
        metadata_path=tmp_path / "sidecar.json",
        persistence=PostgresPersistenceAdapter(engine.connection_factory),
        import_legacy_metadata=False,
    )
    return engine, instance


def chart_file(instance, name="revenue.png"):
    path = instance.root / name
    path.write_bytes(b"\x89PNG chart bytes")
    return path


def register(instance, name="revenue.png", **fields):
    from app.agents.contracts import Principal

    principal = fields.pop("principal", None) or Principal.from_user(OWNER)
    return instance.register(chart_file(instance, name), artifact_type="chart", principal=principal, **fields)


# --------------------------------------------------------------------------- AST 助手（写点唯一真源）


def dict_literal_key_sets(text):
    """源码里每一枚「字典字面量」的键名集合，连行号一起交回。"""
    found = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Dict):
            found.append((node.lineno, {k.value for k in node.keys if isinstance(k, ast.Constant)}))
    return found


def register_artifact_calls(text):
    """点名所有 ``register_artifact(...)`` 调用与其关键字实参。"""
    calls = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name == "register_artifact":
                calls.append(
                    ({kw.arg: ast.unparse(kw.value) for kw in node.keywords},
                     [ast.unparse(a) for a in node.args])
                )
    return calls


def namespaced_calls(name):
    """全仓（app/**）里某枚函数被调用的文件清单，用来证明「拼装只有一处」。"""
    hits = []
    for path in sorted((REPO_ROOT / "app").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                func = node.func
                if (isinstance(func, ast.Name) and func.id == name) or (
                    isinstance(func, ast.Attribute) and func.attr == name
                ):
                    hits.append((path.relative_to(REPO_ROOT).as_posix(), node.lineno))
    return hits


# --------------------------------------------------------------------------- 判据① 两形：有血缘 / 没血缘


def test_a_registered_turn_comes_back_on_the_row(client, registry, account):
    """有血缘：列表行报得出是哪一次问答、哪一笔请求，值逐字等于存储的列值。"""
    account("keeper", "finance")
    record = store(registry, "keeper", "chart.png", session_id="sess-42", request_id="req-42")

    row = client.get(LIST_PATH, headers=_headers("keeper")).json()["artifacts"][0]

    probe_row_field_set(row)
    probe_no_placeholder_lineage(row)
    probe_lineage_row(row, record, session="sess-42", request="req-42")


def test_an_unrecorded_row_omits_both_keys_instead_of_filling_a_slot(client, registry, account):
    """没血缘（今天所有存量行的形状）：整格缺席，屏上才画得出与上一格不同的那张脸。"""
    account("keeper", "finance")
    record = store(registry, "keeper", "chart.png")

    row = client.get(LIST_PATH, headers=_headers("keeper")).json()["artifacts"][0]

    assert set(row) == set(BASE_ROW_KEYS), sorted(set(row) ^ set(BASE_ROW_KEYS))
    probe_lineage_row(row, record)
    assert not [key for key in LINEAGE_KEYS if key in row], "没登记的键不许占一格"


def test_blank_lineage_collapses_to_absent_and_never_to_an_empty_string(client, registry, account):
    """空串/空白不是「登记过」：写点折成 NULL，读点整格缺席，两脸不许长成一格。"""
    account("keeper", "finance")
    record = store(registry, "keeper", "chart.png", session_id="   ", request_id="")

    row = client.get(LIST_PATH, headers=_headers("keeper")).json()["artifacts"][0]

    assert not [key for key in LINEAGE_KEYS if key in row], f"空值冒充了血缘：{row}"
    assert record.session_id is None and record.request_id is None
    probe_lineage_row(row, record)


def test_lineage_is_recorded_at_generation_not_borrowed_from_the_reader(client, registry, account):
    """同一行在所有能看它的账号眼里长出同一个来源：访问者的身份渗不进来。"""
    account("keeper", "finance")
    account("peer", "finance")
    store(registry, "keeper", "chart.png", session_id="sess-42", request_id="req-42")

    own = client.get(LIST_PATH, headers=_headers("keeper")).json()["artifacts"][0]
    peer = client.get(LIST_PATH, headers=_headers("peer")).json()["artifacts"][0]

    assert own == peer, "行上的来源一格若随读者变，画出来的就是访问者而不是生成者"
    assert own["request_id"] == "req-42" and own["session_id"] == "sess-42"


# --------------------------------------------------------------------------- 判据② 存量行为 NULL 且不丢


def test_the_two_columns_actually_land_and_survive_a_new_process(tmp_path):
    """真发给库的 INSERT 点名这两枚列，换一枚登记表（＝换进程）还读得回来。"""
    engine, instance = postgres_registry(tmp_path)
    record = register(instance, session_id="sess-77", request_id="req-77")

    stored = engine.rows("artifacts")[record.artifact_id]
    assert stored["session_id"] == "sess-77" and stored["request_id"] == "req-77", stored

    again = ArtifactRegistry(
        instance.root,
        metadata_path=tmp_path / "sidecar.json",
        persistence=PostgresPersistenceAdapter(engine.connection_factory),
        import_legacy_metadata=False,
    ).get(record.artifact_id)

    assert again is not None and again.session_id == "sess-77" and again.request_id == "req-77"


def test_an_old_row_reads_back_as_the_same_old_row(tmp_path):
    """存量行（0017 之前那十二枚列的形状）读回来还是那一行，血缘两格是 NULL 而不是猜出来的。"""
    from app.storage.artifacts import ARTIFACT_COLLECTION

    root = tmp_path / "static"
    instance = registry_from(__import__("app.storage.artifacts", fromlist=["x"]), tmp_path)
    legacy = {
        "artifact_id": "a-legacy",
        "owner_id": "keeper",
        "resource_type": "artifact",
        "resource_id": "a-legacy",
        "source_version_id": "dv-old",
        "storage_key": str(root / "a-legacy.png"),
        "content_sha256": "0" * 64,
        "status": "active",
        "expires_at": None,
        "deleted_at": None,
        "created_at": "2026-09-20T10:00:00+00:00",
        "metadata": {
            "artifact_type": "chart",
            "filename": "旧图.png",
            "department_ids": ["finance"],
            "classification": "internal",
            "visibility": "private",
        },
    }
    instance.persistence.upsert(ARTIFACT_COLLECTION, "a-legacy", dict(legacy))

    back = instance.get("a-legacy")
    row = _artifact_row_of(back)

    assert back is not None, "存量行读不回来了"
    assert back.source_version_id == "dv-old" and back.owner_id == "keeper"
    assert back.created_at == legacy["created_at"] and dict(back.metadata) == legacy["metadata"]
    assert back.session_id is None and back.request_id is None, "不许替旧行猜一轮问答"
    assert row["filename"] == "旧图.png" and row["classification"] == "internal"
    probe_lineage_row(row, back)
    # 旧行再写一次也不长出血缘：NULL 不会因为有人读了它就变成有来源
    instance._write(back)
    assert _artifact_row_of(instance.get("a-legacy")).get("session_id") is None


def _artifact_row_of(record):
    from app.api.v1.artifacts import _artifact_row

    return _artifact_row(record)


# --------------------------------------------------------------------------- 判据④ metadata 白名单


def test_the_metadata_allow_list_still_carries_exactly_the_five_scope_keys():
    """SCOPE_METADATA_KEYS 五枚一字不改；血缘走真列，不走 jsonb 偷渡。"""
    assert SCOPE_METADATA_KEYS == (
        "artifact_type",
        "filename",
        "department_ids",
        "classification",
        "visibility",
    )
    assert not set(SCOPE_METADATA_KEYS) & set(LINEAGE_KEYS), "血缘不许挤进 scope 白名单"


def test_lineage_pushed_through_the_metadata_jsonb_is_still_dropped(tmp_path):
    """后门那一格仍然只认五枚：jsonb 里的 session_id 造不出血缘列。"""
    from app.storage.artifacts import ARTIFACT_COLLECTION

    instance = registry_from(__import__("app.storage.artifacts", fromlist=["x"]), tmp_path)
    smuggled = {
        "artifact_id": "a-smuggled",
        "owner_id": "keeper",
        "resource_type": "artifact",
        "resource_id": "a-smuggled",
        "source_version_id": None,
        "storage_key": str(instance.root / "a-smuggled.png"),
        "content_sha256": "0" * 64,
        "status": "active",
        "expires_at": None,
        "deleted_at": None,
        "created_at": "2026-09-29T10:00:00+00:00",
        "metadata": {
            "artifact_type": "chart",
            "filename": "a.png",
            "department_ids": ["finance"],
            "classification": "internal",
            "visibility": "private",
            "session_id": "sess-fake",
            "request_id": "req-fake",
        },
    }
    instance.persistence.upsert(ARTIFACT_COLLECTION, "a-smuggled", smuggled)

    record = instance.get("a-smuggled")

    assert record.session_id is None and record.request_id is None
    assert set(record.metadata) == set(SCOPE_METADATA_KEYS)
    assert _artifact_row_of(record).get("session_id") is None, "metadata 里塞的键上了行就是假血缘"

# --------------------------------------------------------------------------- 判据③ 写点只有一处真源（AST）


def test_both_production_writers_call_the_one_registry_entry_point_once():
    """两枚生产写点各自只有一发 register，且血缘只作为关键字实参递进同一枚函数。"""
    for relative in WRITERS:
        calls = register_artifact_calls((REPO_ROOT / relative).read_text(encoding="utf-8"))
        assert len(calls) == 1, f"{relative} 的 register_artifact 写点变成 {len(calls)} 处了"
        keywords, positional = calls[0]
        assert {"artifact_type", "principal"} <= set(keywords), keywords
        assert positional == ["path"], f"{relative} 的字节参数不再是第一枚：{positional}"
        assert "source_version_id" not in keywords, f"{relative} 开始喂来源版本了，本钉要重读"


def test_the_agent_writer_names_its_own_turn_and_the_direct_writer_its_own_request():
    """图内那一发把会话与请求都递进来；直连 POST /chart 只认得到请求，会话就留 NULL。"""
    tools = register_artifact_calls((REPO_ROOT / "app/agents/tools.py").read_text(encoding="utf-8"))[0][0]
    assert set(LINEAGE_KEYS) <= set(tools), f"图内写点没递轮身份：{sorted(tools)}"
    assert tools["session_id"] == "turn_session" and tools["request_id"] == "turn_request", tools

    data = register_artifact_calls((REPO_ROOT / "app/api/v1/data.py").read_text(encoding="utf-8"))[0][0]
    assert data.get("request_id") == "principal.request_id", data
    assert "session_id" not in data, "直连路由没有会话可报，不许替它补一枚假的"


def test_the_tool_turn_reader_is_defined_once_and_used_once():
    """configurable -> 轮身份 的读取在 tools.py 里只有一处，且只喂产物写点。"""
    tree = ast.parse((REPO_ROOT / "app/agents/tools.py").read_text(encoding="utf-8"))
    definitions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_tool_turn"]
    assert definitions == ["_tool_turn"], f"_tool_turn 定义了 {definitions} 次"
    used = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_tool_turn"]
    assert len(used) == 1, f"_tool_turn 被用了 {len(used)} 次：产物写点出现了第二份来源"


def test_the_pair_is_assembled_in_the_storage_module_only():
    """除 app/storage/artifacts.py 外，成果链上没有任何一处把这两枚名字拼成字典键或再调一次拼装。"""
    where = {rel for rel, _ in namespaced_calls("normalize_lineage")}
    assert where == {"app/storage/artifacts.py"}, where
    readers = (API_MODULE.relative_to(REPO_ROOT).as_posix(), *WRITERS)
    for relative in readers:
        surface = set()
        for _lineno, keys in dict_literal_key_sets((REPO_ROOT / relative).read_text(encoding="utf-8")):
            surface |= keys & set(LINEAGE_KEYS)
        assert not surface, f"{relative} 自己拼了一份血缘键名：{sorted(surface)}"
    api_text = API_MODULE.read_text(encoding="utf-8")
    for name in LINEAGE_KEYS:
        assert f'"{name}"' not in api_text, f"读点在 app/api/v1/artifacts.py 里第二次拼了 {name}"


def test_the_reader_publishes_lineage_only_through_the_record():
    """列表行只许转述记录自己的 lineage_payload()，不自己算、更不许拿访问者充数。"""
    tree = ast.parse(API_MODULE.read_text(encoding="utf-8"))
    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_artifact_row"]
    assert len(functions) == 1
    calls = [ast.unparse(n) for n in ast.walk(functions[0]) if isinstance(n, ast.Call)]
    assert any("lineage_payload" in call for call in calls), calls
    assert not [call for call in calls if "principal" in call.lower()], "读点不许把访问者画成来源"


def test_the_adapter_names_the_two_columns_or_the_lineage_never_leaves_the_process():
    """PostgreSQL 那条腿的列元组必须点名这两枚列，否则它们只活在内存里（R256 同族的坑）。"""
    from app.storage import persistence as persistence_module

    columns = persistence_module._TABLES["artifacts"].columns
    for name in LINEAGE_KEYS:
        assert name in columns, f"{name} 没进适配器列元组：生产库永远收不到这一格"


# --------------------------------------------------------------------------- 迁移与卫生


def _statements(sql):
    """注释剥掉之后的 DDL 正文：判「不许默认值 / 不许回填」只判真语句，不判说明文。"""
    return re.sub(r"^\s*--.*$", "", sql, flags=re.MULTILINE).split("COMMENT ON")[0].lower()


def test_the_migration_adds_two_nullable_columns_and_nothing_else():
    sql = MIGRATION.read_text(encoding="utf-8")
    ddl = _statements(sql)
    for name in LINEAGE_KEYS:
        assert re.search(rf"add column if not exists {name} text;", sql, re.IGNORECASE), name
        assert re.search(rf"create index if not exists \w+ on artifacts \({name}\)", sql, re.IGNORECASE), name
    assert "not null" not in ddl, "两枚都可空：NULL 才是『没登记』的真拼写"
    assert "default" not in ddl, "不许给默认值——默认值会替存量行编一个来源"
    assert not re.search(r"\bupdate\b", ddl), "不许回填"
    assert "drop" not in ddl, "不许删东西"
    assert "metadata" not in ddl, "不许把血缘塞进 jsonb"


def test_the_migration_is_registered_and_loads():
    from app.db.migrations import MIGRATIONS

    entry = next((item for item in MIGRATIONS if item.name == "artifact_generation_lineage"), None)
    assert entry is not None, "0017 没进迁移册：loader fail closed，客户机上这两枚列根本不存在"
    assert entry.version == "0017", entry.version
    assert MIGRATIONS[-1] is entry, "0017 必须是当前最新一版，否则并树顺序错了"


def test_no_new_chroma_writepoint_and_no_classification_blocked():
    """本单不碰向量库，也不长第二套密级判定。"""
    touched = [
        "app/storage/artifacts.py",
        "app/storage/persistence.py",
        "app/api/v1/artifacts.py",
        "app/api/v1/data.py",
        "app/agents/tools.py",
    ]
    for relative in touched:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "import chromadb" not in text and "PersistentClient" not in text, relative
    hits = [
        str(path.relative_to(REPO_ROOT))
        for path in (REPO_ROOT / "app").rglob("*.py")
        if "classification_blocked" in path.read_text(encoding="utf-8")
    ]
    assert hits == [], hits

# --------------------------------------------------------------------------- 判据①「退回原状必红」五把刀
# 刀身全在内存源码影子上（load_shadow：锚点不唯一就判定这把刀空转），盘上的在册件一字不改。


LINEAGE_UPDATE = "    row.update(record.lineage_payload())"
TO_ROW_PAIR = '        "session_id": record.session_id,\n        "request_id": record.request_id,\n'
COERCE_LINEAGE = "                **normalize_lineage(raw),\n"
PAYLOAD_FILTER = "            if value is not None\n"
BLANK_FOLD = "    return text or None"
TOOLS_CALL = "        session_id=turn_session,\n        request_id=turn_request,\n"


def test_blade_k1_dropping_the_reader_leg_goes_red():
    """刀①：读点不再把血缘搬进行 —— 有血缘的那一条又说不清是哪一次问答了。"""
    shadow = load_shadow(API_MODULE, "r509_k1", ((LINEAGE_UPDATE, ""),))
    record = sample_record(
        __import__("app.storage.artifacts", fromlist=["x"]), session_id="sess-1", request_id="req-1"
    )

    row = shadow._artifact_row(record)
    with pytest.raises(AssertionError) as caught:
        probe_lineage_row(row, record, session="sess-1", request="req-1")
    assert "血缘行不对" in str(caught.value), str(caught.value)


def test_blade_k2_publishing_unrecorded_keys_goes_red(tmp_path):
    """刀②：lineage_payload 不再筛掉未登记的键 —— 存量行凭空多出一格（假血缘的入口）。"""
    shadow = load_shadow(STORAGE_MODULE, "r509_k2", ((PAYLOAD_FILTER, "            if True\n"),))
    instance = registry_from(shadow, tmp_path)
    path = instance.root / "old.png"
    path.write_bytes(b"old bytes")
    from app.agents.contracts import Principal

    record = instance.register(
        path, artifact_type="chart", principal=Principal.from_user(OWNER), session_id="", request_id=""
    )

    row = _artifact_row_of(record)
    assert set(LINEAGE_KEYS) <= set(row), "刀没切进去"
    with pytest.raises(AssertionError) as caught:
        probe_no_placeholder_lineage(row)
    assert "顶替品" in str(caught.value), str(caught.value)


def test_blade_k3_a_column_the_writer_stops_filling_goes_red(tmp_path):
    """刀③：_to_row 少写这两枚列 —— 写点还在、值却再也不落库，重启之后血缘整段蒸发。"""
    shadow = load_shadow(STORAGE_MODULE, "r509_k3", ((TO_ROW_PAIR, ""),))
    engine = FakePostgres()
    root = tmp_path / "static"
    root.mkdir(parents=True, exist_ok=True)
    instance = shadow.ArtifactRegistry(
        root,
        metadata_path=tmp_path / "sidecar.json",
        persistence=PostgresPersistenceAdapter(engine.connection_factory),
        import_legacy_metadata=False,
    )
    path = root / "chart.png"
    path.write_bytes(b"\x89PNG chart bytes")
    from app.agents.contracts import Principal

    instance.register(
        path,
        artifact_type="chart",
        principal=Principal.from_user(OWNER),
        session_id="sess-1",
        request_id="req-1",
    )

    re_read = instance.get(next(iter(engine.rows("artifacts"))))
    with pytest.raises(AssertionError) as caught:
        probe_lineage_row(_artifact_row_of(re_read), re_read, session="sess-1", request="req-1")
    assert "哪一次问答" in str(caught.value), str(caught.value)


def test_blade_k4_a_column_the_reader_stops_reading_goes_red(tmp_path):
    """刀④：_coerce_record 不认这两枚列 —— 库里明明有，读出来却是没来源。"""
    shadow = load_shadow(STORAGE_MODULE, "r509_k4", ((COERCE_LINEAGE, ""),))
    instance = registry_from(shadow, tmp_path)
    path = instance.root / "chart.png"
    path.write_bytes(b"chart bytes")
    from app.agents.contracts import Principal

    record = instance.register(
        path, artifact_type="chart", principal=Principal.from_user(OWNER), session_id="sess-9", request_id="req-9"
    )

    assert record.session_id is None, "刀没切进去：读腿明明还认这一列"
    with pytest.raises(AssertionError) as caught:
        probe_lineage_row(_artifact_row_of(record), record, session="sess-9", request="req-9")
    assert "哪一次问答" in str(caught.value), str(caught.value)


def test_blade_k5_a_writer_that_stops_naming_its_turn_goes_red():
    """刀⑤：图内写点不再递轮身份 —— 屏上那张「有血缘」的脸从此永远是假的。"""
    text = (REPO_ROOT / "app/agents/tools.py").read_text(encoding="utf-8")
    crippled = text.replace(TOOLS_CALL, "")
    assert crippled != text, "锚点漂了，这把刀会空转"
    keywords = register_artifact_calls(crippled)[0][0]
    assert not set(LINEAGE_KEYS) & set(keywords), keywords
    with pytest.raises(AssertionError):
        assert set(LINEAGE_KEYS) <= set(keywords), f"图内写点没递轮身份：{sorted(keywords)}"


def test_blade_k6_an_empty_string_let_through_as_lineage_goes_red(tmp_path):
    """刀⑥：空值不折成 NULL —— 于是「空白」和「登记过」在库里长成同一个样子。"""
    shadow = load_shadow(STORAGE_MODULE, "r509_k6", ((BLANK_FOLD, '    return text or ""'),))
    from app.agents.contracts import Principal

    instance = registry_from(shadow, tmp_path)
    path = instance.root / "blank.png"
    path.write_bytes(b"blank")
    record = instance.register(
        path, artifact_type="chart", principal=Principal.from_user(OWNER), session_id="  ", request_id="req-1"
    )

    row = _artifact_row_of(record)
    with pytest.raises(AssertionError) as caught:
        probe_no_placeholder_lineage(row)
    assert "顶替品" in str(caught.value), str(caught.value)
