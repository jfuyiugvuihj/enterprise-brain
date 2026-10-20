# -*- coding: utf-8 -*-
r"""R394 · 版本腿的「非迁移族」写失败不许静默答已登记（`app/documents/catalog.py:768-772`）。

## 判据①取证表（每一枚 path:line 都在本树 `64b3f3c` 上 `rg -F` 命中过；状态码一律
`TestClient(app, raise_server_exceptions=False)` 现场；全部离线：替身台账，零真库、零容器、零模型端口）

链路：`app/api/v1/chat.py:4070` `upload_document` → `app/api/v1/chat.py:3644` `_record_uploaded_version`
→ `app/api/v1/chat.py:3692` 调版本腿 → `app/documents/catalog.py:692` `record_document_version`
→ `app/documents/catalog.py:733` 入口闸（R383）→ `app/documents/catalog.py:734` 先写 sidecar
→ `app/documents/catalog.py:736-737`「库没起 = 设计内降级，一次连接都不发」→ `app/documents/catalog.py:738-767`
`_ensure()`（`app/documents/catalog.py:570`）+ `INSERT INTO document_versions ... ON CONFLICT`
（`app/documents/catalog.py:747`）+ `commit()` → 🔴 修前 `app/documents/catalog.py:768-772`：只有
`_schema_needs_migrations`（`app/documents/catalog.py:357`）那一支带 `migrations_missing` 进闸，其余**任何**
写失败只 `logger.warning("[Docs] version record fallback: ...")` 再 `return metadata`
（`app/documents/catalog.py:772`）。文件已落盘、正文已进索引、版本号已写进 sidecar，权威表
`document_versions` 零行，而出口照旧 200。R391 把 `app/api/v1/chat.py:3705` 修成
`except HTTPException: raise` 之后那一支**接不到这一格**——因为这里根本没抛。

| 态 | 构造 | 修前出口 | 修后出口 | 谁钉 |
| --- | --- | --- | --- | --- |
| W1 生产·表在·那一发 INSERT 被打回 | `versions_present=True` + 只拒 INSERT 的台账 | 🔴 200 `status:"ok"` | **503 `storage_unavailable`** | `test_a_*` 三枚 |
| W2 生产·迁移族（= R391 的 D 态） | `versions_present=False` + peek 撞一次连接失败 | 503 + `migration=` | 同（一字未动，且不混进 `write_failed=true`） | `test_b_*` |
| W3 生产·旗标在入口闸之后翻转 | `_database_available()` 第一次 True、其后 False | 200 + 零语句 | 同（设计内降级，不许被①带成 503） | `test_c2_*` |
| W4 开发·库没起 | 非生产 + `_database_available()=False` | 200 + 本地台账 | 同 | `test_c1_*` |
| W5 开发·表在·那一发 INSERT 被打回 | 非生产 + 只拒 INSERT | 200 `status:"ok"` | 同（回落本地台账是设计） | `test_d_*` |
| W6 生产·归属腿挂了 | `chat._upsert_document` 抛 `RuntimeError("db down")` | 200 `status:"ok"` | 同（宽捕获一字未动：`tests/test_document_upload_resilience.py:103` 那条裁定） | `test_d2_*` |
| W0 生产·一切正常（反空白对照） | 表在 + INSERT 不拒 | 200 `status:"ok"` | 同 | `test_the_healthy_*` |

改脸的只有 W1；W0/W2-W6 逐字保持 ⇒ 判据②「不许误伤既有裁定」由这六格现场量出来，不由自述证。

## 判据③ 两本账的形状必须可见
拒答之后现场是：sidecar 有那一行（写在 `app/documents/catalog.py:734`，排在落库之前）、权威表零行
（`commit()` 从没发生）。本单把这件事钉成两处可读事实：闸交出去那一句日志**同时点名两本账**
（`test_e_*` 读盘上 sidecar 的行数 + `store.commits == 0` + 那一句话里两枚账名都在），以及因由那一行
`test_a_the_underlying_cause_*`（超时/约束/断连只有它带着——摘掉它，运维就只能看见「写失败」三个字）。
🔴 不回滚 sidecar：回滚点是 `app/documents/catalog.py:734`，而那一枚镜像是当前唯一不需要迁移就能落地的
持久处（`app/documents/catalog.py:182-184`），删它等于把「文件收了、账没落」改成「文件收了、两本账都没」，
三份不一致变四份，且替客户机做了一次删除决定。论证在 R394 回执③。

## 判据④ 撞号覆盖那一格（只复核，不改行为）
`app/documents/catalog.py:603-620` 的 peek 在 SELECT 撞上连接失败时按既有设计回落本地台账推 `max+1`
（`app/documents/catalog.py:620`）⇒ 号从 1 重来 ⇒ 版本腿发的仍是 `INSERT ... ON CONFLICT (filename,
version) DO UPDATE`（`app/documents/catalog.py:747`）⇒ 真库旧行的 `storage_path/created_at/parse_status`
被覆盖。本件复核它今天仍然成立（`test_the_collision_cell_still_holds_*`）。它与①的分界：那条语句**成功
执行并 commit**，`except` 根本不进 ⇒ ①不拒它；反过来①也治不了它（写成功正是①放行的那一支）。治它要
动 peek 的回落口径（号必须从真库现取）或给 `document_versions` 加「拒绝回退号」的约束，两样都超出本单
写域 ⇒ 只报不改。

## 刀法
**行为面**由 `%TEMP%\r394\r394_refutation_driver.py` 在影子副本上下盘真刀（五把：摘①、放宽①、删③那句
可读者证、只喊日志不改脸、把写失败吞进迁移族），逐把记进/出 sha256 前缀，读数在 R394 回执里；本件对
被跟踪文件零写口。**形状面**（下面四枚 `test_ruler_*` + 一枚对照）常驻在本件里，全部在内存里变异源码
（R253 口径），要证的是这几把尺子真能看见那四种改法，不是「应该会红」。
"""
import ast
import json
from pathlib import Path
from typing import get_args

import pytest
from psycopg import errors

import test_r383_catalog_refuses_a_store_that_is_not_there as r383
import test_r391_upload_refusal_reaches_the_exit as r391
from app.agents.contracts import ErrorEnvelope
from app.api.v1 import chat
from app.documents import catalog

CATALOG_REL = r383.CATALOG_REL
GATE_CODE = r391.store_gate_detail()          # 从闸里现取，不抄字面量（R366 的口径）
MIGRATION_NEEDLE = r383.GATE_MISSING_TABLE    # 迁移族那张脸的句子：借 R383 的尺，不另造
WRITE_NEEDLE = "write_failed=true"            # 本单新造的只是**日志 token**：零新增错误码/reason/档位
CAUSE_NEEDLE = "version record not written"   # 因由先记，脸由闸决定（生产拒 / 非生产回落）
LEDGER_EVIDENCE = ("sidecar", "document_versions")  # ③：拒答那一句必须同时点名两本账

LOCK_TIMEOUT = errors.LockNotAvailable("canceling statement due to lock timeout")
FOREIGN_KEY = errors.ForeignKeyViolation('insert or update violates foreign key constraint "fk_owner"')


# ------------------------------------------------------------------ 替身台账与现场
class RefusingStore(r391.Store):
    """表在、旗标在，只有那一发 INSERT 被打回：W1/W5 的病格（超时、约束、断连同族不同因）。

    与 R391 那具台账的分工：它演「表根本不在」（迁移族，走 `migrations_missing`），本具演「表在而这一发
    写不成」（非迁移族，正是修前静默那一支）。两者共用同一具 `to_regclass` 现查，差别只落在 INSERT 上。
    """

    error = None

    def __init__(self, tables=(), fail_next_connect=False):
        super().__init__(tables, fail_next_connect)
        self.refused: list[str] = []
        self.commits = 0

    def execute(self, sql, params=()):
        text = " ".join(str(sql).split())
        if self.error is not None and text.upper().startswith("INSERT INTO DOCUMENT_VERSIONS"):
            self.statements.append(text)
            self.refused.append(text)
            raise self.error
        return super().execute(sql, params)

    def commit(self):
        self.commits += 1
        return super().commit()


@pytest.fixture
def refusing(monkeypatch):
    """把 R391 那具现场换成「只拒 INSERT」的台账：借它的 harness，不另造一套平行的。"""
    monkeypatch.setattr(r391, "Store", RefusingStore)
    return RefusingStore


def upload_with_write_refusal(monkeypatch, tmp_path, refusing, *, env="production", error=LOCK_TIMEOUT):
    root, store, log = r391.world(monkeypatch, tmp_path, env=env, db_ready=True,
                                  versions_present=True, blip=False, site=r391.SITE_OK)
    if error is None:
        monkeypatch.setattr(RefusingStore, "error", None)
    else:
        monkeypatch.setattr(refusing, "error", error)
    response, body = r391.upload(r391.SITE_OK)
    return root, store, log, response, body


def _stored_file(tmp_path, name="policy.txt", payload=b"policy bytes") -> Path:
    path = Path(tmp_path) / name
    path.write_bytes(payload)
    return path


def _sidecar_records(directory: Path) -> dict:
    """盘上那本本地台账，按它自己写下的形状读出来（`_write_sidecar` 外面包了一枚 `documents` 键）。

    本件要的是「运维打开那个文件能看见什么」，所以读盘上字节，不走 `_read_sidecar` 的兜底。
    """
    payload = json.loads((directory / catalog.LOCAL_CATALOG_FILENAME).read_text(encoding="utf-8"))
    return payload["documents"]


# ================================================== 判据①：W1 生产 + 真写失败 ⇒ 出口具名拒答
def test_a_real_write_failure_at_the_version_leg_reaches_the_exit_as_a_named_refusal(monkeypatch, tmp_path, refusing):
    root, store, log, response, body = upload_with_write_refusal(monkeypatch, tmp_path, refusing)

    assert store.refused, "现场没造出来：那一发 INSERT 根本没被拒，下面的断言全是空的"
    assert response.status_code == 503, response.text
    assert body == {"detail": GATE_CODE}, body
    assert log.mentions("operation=version record"), log.lines
    assert log.mentions(WRITE_NEEDLE), log.lines


def test_a_refused_write_carries_no_registration_receipt(monkeypatch, tmp_path, refusing):
    root, store, log, response, body = upload_with_write_refusal(monkeypatch, tmp_path, refusing, error=FOREIGN_KEY)

    assert response.status_code == 503, response.text
    for claimed in ("version", "status", "stored_name", "index_status"):
        assert claimed not in body, (claimed, body)
    assert store.inserts("document_versions") == 1, store.statements
    assert store.commits == 0, "语句被拒之后仍然 commit = 现场在说谎"


def test_a_the_underlying_cause_is_still_logged_and_it_is_not_the_migration_face(monkeypatch, tmp_path, refusing):
    """三张脸分得开：非迁移族**不许**借 `migration=` 那一句出去（R377 的窄判定继续生效）。"""
    root, store, log, response, body = upload_with_write_refusal(monkeypatch, tmp_path, refusing)

    cause = log.mentions(CAUSE_NEEDLE)
    assert len(cause) == 1, log.lines
    assert "canceling statement due to lock timeout" in cause[0], cause
    assert not log.mentions(MIGRATION_NEEDLE), "写失败被翻成缺迁移 = 替下一个班埋雷"


# ============================================ 判据②：既有裁定与既有脸，一格都不许漂
def test_b_the_migration_family_keeps_its_own_face_and_is_not_swallowed(monkeypatch, tmp_path):
    """R391 的 D 态一字不许漂：缺表那一格仍走 `migrations_missing`，不借①这张新脸。"""
    root, store, log = r391.world(monkeypatch, tmp_path, env="production", db_ready=True,
                                  versions_present=False, blip=True, site=r391.SITE_OK)
    response, body = r391.upload(r391.SITE_OK)

    assert response.status_code == 503, response.text
    assert body == {"detail": GATE_CODE}, body
    assert log.mentions(MIGRATION_NEEDLE), log.lines
    assert not log.mentions(WRITE_NEEDLE), "迁移族被①吞成另一张脸：两格又并回一张"
    assert store.inserts("document_versions") == 0, store.statements


def test_c1_the_designed_offline_leg_is_not_turned_into_a_refusal(monkeypatch, tmp_path):
    """非生产 + 库没起：`:736-737` 那一支照设计交本地台账，一次连接都不发。"""
    stored = _stored_file(tmp_path)
    connects: list[int] = []

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(catalog, "_database_available", lambda: False)
    monkeypatch.setattr(catalog, "_conn", lambda: connects.append(1) or RefusingStore({"document_versions"}))
    log = r391.Recorder()
    monkeypatch.setattr(catalog, "logger", log)

    metadata = catalog.record_document_version("policy.txt", 2, "finance", str(stored), version=4)

    assert metadata["version"] == 4
    assert connects == [], connects
    assert not log.mentions(WRITE_NEEDLE) and GATE_CODE not in str(log.lines), log.lines
    records = _sidecar_records(stored.parent)
    assert [row["filename"] for row in records.values()] == ["policy.txt"], records
    assert [row["version"] for row in records.values()] == [4], records


def test_c2_a_flag_that_flips_after_the_entry_gate_still_takes_the_designed_leg(monkeypatch, tmp_path):
    """入口闸那一次读到 True、`:736` 读到 False：那一支照旧 return metadata，一次连接都不许发。

    生产现场拿不到这个翻转（R230 之后 `_db_ready` 只许 False→True，见 R391 文件头那段），所以这一枚是
    **形状钉**：钉的是「库没起」那一格今天仍然是设计内降级，而不是被①的写失败带进闸。盘上刀 K2 冲它下。
    """
    stored = _stored_file(tmp_path)
    connects: list[int] = []
    gate_reads: list[int] = []

    def available() -> bool:
        gate_reads.append(1)
        return len(gate_reads) == 1

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(catalog, "_database_available", available)
    monkeypatch.setattr(catalog, "_conn", lambda: connects.append(1) or RefusingStore({"document_versions"}))
    log = r391.Recorder()
    monkeypatch.setattr(catalog, "logger", log)

    metadata = catalog.record_document_version("policy.txt", 2, "finance", str(stored), version=4)

    assert metadata["version"] == 4
    assert len(gate_reads) == 2, gate_reads
    assert connects == [], connects
    assert not log.mentions(WRITE_NEEDLE) and GATE_CODE not in str(log.lines), log.lines


def test_d_a_non_production_write_failure_still_falls_back_to_the_local_ledger(monkeypatch, tmp_path, refusing):
    """开发/裸机那两条腿不许被①打成拒答：写失败照旧回落本地台账、照旧 200。"""
    root, store, log, response, body = upload_with_write_refusal(monkeypatch, tmp_path, refusing,
                                                                 env="development")

    assert response.status_code == 200, response.text
    assert body["status"] == "ok" and body["version"] == 1, body
    assert len(store.refused) == 1 and store.commits == 1
    assert log.mentions(CAUSE_NEEDLE), log.lines
    assert not log.mentions(WRITE_NEEDLE), "非生产被①带成拒答：三张脸并回一张"
    assert GATE_CODE not in str(log.lines), log.lines


def test_d2_the_attribution_leg_broad_catch_is_untouched(monkeypatch, tmp_path, refusing):
    """`RuntimeError("db down")` 那条既有裁定：归属腿挂了、版本腿健康 ⇒ 仍然 200（宽捕获一字没动）。"""
    def down(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(chat, "_upsert_document", down)
    root, store, log, response, body = upload_with_write_refusal(monkeypatch, tmp_path, refusing, error=None)

    assert response.status_code == 200, response.text
    assert body["status"] == "ok", body
    assert log.mentions("metadata sync failed"), log.lines
    assert not log.mentions(WRITE_NEEDLE), "①接管了归属腿：越界"
    assert store.commits == 1, store.statements


def test_the_healthy_production_write_still_lands_and_still_answers_ok(monkeypatch, tmp_path, refusing):
    """反空白对照：同一具现场只把「拒 INSERT」这一枚开关摘掉，出口就必须照旧 200 且落行。"""
    root, store, log, response, body = upload_with_write_refusal(monkeypatch, tmp_path, refusing, error=None)

    assert response.status_code == 200, response.text
    assert body["status"] == "ok" and body["version"] == 1, body
    assert store.inserts("document_versions") == 1 and store.commits == 1
    assert not log.mentions(CAUSE_NEEDLE) and not log.mentions(WRITE_NEEDLE), log.lines


# =============================================== 判据③：两本账的裂缝是可读的现场
def test_e_the_split_between_the_two_ledgers_is_readable_after_the_refusal(monkeypatch, tmp_path, refusing):
    root, store, log, response, body = upload_with_write_refusal(monkeypatch, tmp_path, refusing)

    records = _sidecar_records(root)
    assert len(records) == 1, records
    row = next(iter(records.values()))
    assert row["version"] == 1 and Path(row["recorded_path"]).is_file(), row
    assert store.commits == 0 and len(store.refused) == 1, (store.commits, store.refused)

    refusal = log.mentions(WRITE_NEEDLE)
    assert len(refusal) == 1, log.lines
    for ledger in LEDGER_EVIDENCE:
        assert ledger in refusal[0], (ledger, refusal[0])

    stored = [path for path in root.iterdir() if path.suffix == ".txt"]
    assert len(stored) == 1 and stored[0].is_file(), ("拒答不删文件：那一发留在盘上等台账补齐", stored)


# =============================================== 判据④：撞号覆盖只复核（不改行为）
def test_the_collision_cell_still_holds_and_is_not_a_write_failure(monkeypatch, tmp_path, refusing):
    """peek 回落本地台账 ⇒ 号从 1 重来 ⇒ 那一发仍走 ON CONFLICT DO UPDATE 覆盖旧行并 commit。"""
    root, store, log = r391.world(monkeypatch, tmp_path, env="production", db_ready=True,
                                  versions_present=True, blip=True, site=r391.SITE_OK)

    assert catalog.peek_next_document_version("policy.txt") == 1, log.lines
    assert log.mentions("version lookup fallback"), log.lines

    metadata = catalog.record_document_version("policy.txt", classification=2, department="finance",
                                               storage_path=str(root / "policy__v1.txt"), version=1)

    assert metadata["version"] == 1
    assert [t for t in store.statements if "ON CONFLICT (filename, version) DO UPDATE" in t], store.statements
    assert store.refused == [] and store.commits == 1, (store.refused, store.commits)
    assert not log.mentions(WRITE_NEEDLE), "覆盖写被①当成拒答：判据④明令不改行为"


# ================================================== 形状钉：闸只一扇、新脸只一枚、探针不加二
def _write_face_calls(tree: ast.Module) -> list[tuple[int, str]]:
    """全模块里带 `write_failed` kwarg 的 `_require_ready_store` 调用：位置 + 那一枚值的原文。"""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_require_ready_store":
            for keyword in node.keywords:
                if keyword.arg == "write_failed":
                    found.append((node.lineno, ast.unparse(keyword.value)))
    return found


def _write_face_words(text: str) -> str:
    """闸里 `elif write_failed:` 那一支写下的所有字面量，抠成一整段文本（③的取证面）。"""
    tree = ast.parse(text)
    gate = r383._function(tree, "_require_ready_store")
    branch = next(
        (node for node in ast.walk(gate)
         if isinstance(node, ast.If) and ast.unparse(node.test) == "write_failed"),
        None,
    )
    assert branch is not None, "闸里再没有 `elif write_failed` 这一支：①的新脸被搬走或改判了"
    return "".join(
        node.value for node in ast.walk(branch)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def _ruler_facts(text: str) -> dict:
    tree = ast.parse(text)
    approved = set(get_args(ErrorEnvelope.model_fields["code"].annotation))
    details = r383._raise_details_with_status(tree, 503)
    return {
        "write_faces": len(_write_face_calls(tree)),
        "ledgers": sum(1 for ledger in LEDGER_EVIDENCE if ledger in _write_face_words(text)),
        "exits": len(r383._raise_sites_with_status(tree, 503)),
        "codes": tuple(details),
        "ratified": bool(details) and all(detail in approved for detail in details),
        "probes": len(r383._db_ready_reads(text)),
    }


def test_the_version_leg_routes_a_write_failure_through_the_existing_gate():
    tree = r383._tree(CATALOG_REL)
    calls = _write_face_calls(tree)

    assert calls and all(value == "True" for _line, value in calls), calls
    record = r383._function(tree, "record_document_version")
    inside = [line for line, _value in calls if record.lineno <= line <= record.end_lineno]
    assert len(inside) == 1, (inside, record.lineno)


def test_only_the_version_leg_asks_the_gate_for_the_write_face():
    """①的捕获面没有漏进别的腿：全模块那一枚新脸只许长在版本腿里。"""
    assert len(_write_face_calls(r383._tree(CATALOG_REL))) == 1, _write_face_calls(r383._tree(CATALOG_REL))


def test_the_gate_still_owns_the_only_storage_exit_and_the_module_gained_no_second_probe():
    tree = r383._tree(CATALOG_REL)
    exits = r383._raise_sites_with_status(tree, 503)
    gate = r383._function(tree, "_require_ready_store")

    assert len(exits) == 1, exits
    assert gate.lineno <= exits[0] <= gate.end_lineno, "第二枚 503 长在闸外：档位被私造了"
    assert r383._raise_sites_with_status(tree, 500) == [], "目录模块不许自己写 500"
    assert len(r383._db_ready_reads(r383._source(CATALOG_REL))) == 1, "长出了第二枚 `_db_ready` 读者"


def test_the_write_face_names_both_ledgers_and_reuses_the_ratified_code():
    facts = _ruler_facts(r391.working_text(CATALOG_REL))
    assert facts["ledgers"] == len(LEDGER_EVIDENCE), facts
    assert facts["codes"] == (GATE_CODE,), facts
    assert facts["ratified"], "为了写失败新造错误码：四连先例（R380/R381/R383/R384）否掉的那件事"


# ============================================== 常驻反证牙：形状尺必须真能咬（内存变异，零写盘）
CLAUSE = (
    '        _require_ready_store("version record", migrations_missing=_schema_needs_migrations(exc),\r\n'
    "                             write_failed=True)\r\n"
)
PEEK_GATE = '    _require_ready_store("version peek")\r\n'
RAISE_LINE = '    raise HTTPException(status_code=503, detail="storage_unavailable")\r\n'


def _knife_removed(text: str) -> str:
    """刀M1：摘掉①的新脸（其余一字不动）= 退回修前的静默。"""
    return text.replace(CLAUSE, '        _require_ready_store("version record", '
                                'migrations_missing=_schema_needs_migrations(exc))\r\n', 1)


def _knife_leaked(text: str) -> str:
    """刀M2：把新脸漏给别的腿（peek 也带 `write_failed=True`）。"""
    return text.replace(PEEK_GATE, '    _require_ready_store("version peek", write_failed=True)\r\n', 1)


def _knife_blind_evidence(text: str) -> str:
    """刀M3：删掉③那句可读者证里的一枚账名（拒答照旧，运维看不出是哪本账没落）。"""
    return text.replace("（sidecar 镜像排在前面已写、document_versions 这一发零行）", "（这一发没落）", 1)


def _knife_invented_code(text: str) -> str:
    """假修复：脸改对了却顺手新造一枚码（词表钉会当场红的那件事）。"""
    return text.replace(RAISE_LINE,
                        '    raise HTTPException(status_code=503, detail="catalog_write_failed")\r\n', 1)


def _knife_log_only(text: str) -> str:
    """假修复其二：照旧静默，只是把日志喊成 error（判据⑥点名的那一种）。"""
    return text.replace(CLAUSE, '        _require_ready_store("version record", '
                                'migrations_missing=_schema_needs_migrations(exc))\r\n'
                                '        logger.error(f"[Docs] version record write failed: {exc}")\r\n', 1)


KNIVES = {
    "M1_write_face_removed": (_knife_removed, ("write_faces",)),
    "M2_write_face_leaked": (_knife_leaked, ("write_faces",)),
    "M3_evidence_sentence_blinded": (_knife_blind_evidence, ("ledgers",)),
    "M4_invented_code": (_knife_invented_code, ("codes", "ratified")),
    "M5_log_only_fake_fix": (_knife_log_only, ("write_faces",)),
}


@pytest.mark.parametrize("label", sorted(KNIVES))
def test_ruler_sees_every_way_this_fix_could_be_faked_or_widened(label, monkeypatch, tmp_path):
    """每把刀各自把尺子判红，且**只有**它该碰的那几格红：哑刀与连带红一起算不合格。"""
    honest = _ruler_facts(_honest_source())

    mutate, expected = KNIVES[label]
    facts = _ruler_facts(mutate(_honest_source()))
    drifted = tuple(key for key in honest if honest[key] != facts[key])

    assert drifted, "%s 没有被尺子看见：这一格没钉住" % label
    assert set(drifted) == set(expected), (label, drifted, expected)


def test_the_ruler_is_not_vacuous_on_the_honest_tree():
    """尺子在真源码上必须给出那五格读数；少一格就是尺子自己瞎了（刀全都不红的唯一合法解释）。"""
    facts = _ruler_facts(_honest_source())

    assert facts == {
        "write_faces": 1,
        "ledgers": 2,
        "exits": 1,
        "codes": (GATE_CODE,),
        "ratified": True,
        "probes": 1,
    }, facts


def _honest_source() -> str:
    text = r391.working_text(CATALOG_REL)
    assert CLAUSE in text, "①的新分支不在原位：先重读树，再改这把刀"
    assert PEEK_GATE in text and RAISE_LINE in text, "对照面缺件：刀会切在空气上"
    return text
