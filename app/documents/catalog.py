import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException

from app.common.logger import logger
from app.documents.index_policy import (
    INDEX_STATUSES,
    INDEX_STATUS_EXCLUDED,
    INDEX_STATUS_UNKNOWN,
)

_tz = timezone(timedelta(hours=8))
_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")
DOCUMENTS_DIR = os.getenv("DOCUMENTS_DIR", "./documents")
_initialized = False
_db_available: bool | None = None
_PRODUCTION_ENVIRONMENTS = {"production", "prod"}

# The catalog has two persistence paths and both of them must carry ownership: the
# PostgreSQL document_versions table (mirrored by the documents table) and, for any
# deployment where PostgreSQL is offline, a JSON sidecar kept next to the stored
# files. The sidecar is addressed through the directory of the file it describes
# rather than through DOCUMENTS_DIR, so a caller that stores a version outside the
# documents root can never write into that root by accident.
LOCAL_CATALOG_FILENAME = ".document-versions.json"
PARSE_STATUSES = ("pending", "parsing", "ready", "failed")
#: 解析状态只有上面四个值：那是 migrations/0006_document_ownership.sql 上的数据库 CHECK
#: 约束，不是应用约定。"解析成功但按策略不入索引"没有第五个值可写，由 INDEX_STATUSES
#: （app/documents/index_policy.py，本模块直接透出）表达，两者正交。
OWNERSHIP_OWNED = "owned"
OWNERSHIP_LEGACY = "legacy"
_SELECT_COLUMNS = (
    "filename, version, classification, department, storage_path, created_at, "
    "owner_id, size_bytes, parse_status"
)


def next_document_version(rows: list[dict], filename: str) -> int:
    versions = [int(row.get("version", 0)) for row in rows if row.get("filename") == filename]
    return max(versions, default=0) + 1


def build_storage_name(filename: str, version: int) -> str:
    stem, ext = os.path.splitext(filename)
    return f"{stem}__v{version}{ext}"


def _public_storage_path(value) -> str:
    """Express a stored file for API responses without echoing a server path.

    Catalog rows are also consumed inside the process (preview, download and
    delete resolve the physical file), so the value must stay resolvable: an
    absolute path is rewritten relative to the working directory the service
    runs from, and only the bare file name is kept when no relative form can be
    expressed at all (for example across Windows drives). The absolute path
    remains in the catalog table and in the server log, never in a response.
    """
    if value is None or value == "":
        return ""
    raw = str(value)
    if not os.path.isabs(raw):
        return raw.replace(os.sep, "/")
    try:
        relative = os.path.relpath(raw, os.getcwd())
    except ValueError:
        logger.warning(f"[Docs] storage path leaves the working directory tree: {raw}")
        return os.path.basename(raw).replace(os.sep, "/")
    return relative.replace(os.sep, "/")


def _is_unowned(value) -> bool:
    """A row without a usable owner is legacy, never public."""
    return value is None or str(value).strip() == ""


def _resolve_owner_id(principal=None, owner_id=None) -> str | None:
    """Read an owner identity from a Principal, a user mapping or an explicit value.

    Callers that have no authenticated subject record an unowned row on purpose: the
    policy treats an unowned document as legacy and keeps it away from ordinary
    staff until somebody resolves its ownership.
    """
    if owner_id not in (None, ""):
        return str(owner_id).strip() or None
    if principal is None:
        return None
    if isinstance(principal, dict):
        value = principal.get("id") or principal.get("user_id") or principal.get("username")
    else:
        value = getattr(principal, "user_id", None)
    if value is None:
        return None
    return str(value).strip() or None


def _normalise_parse_status(value) -> str:
    status = str(value or "pending").strip().lower()
    if status in PARSE_STATUSES:
        return status
    logger.warning(f"[Docs] unknown parse status {value!r} recorded as pending")
    return "pending"


def _normalise_index_status(value) -> str:
    """索引状态归一：没有记录就是"未知"，只有认不出的取值才告警。

    与 ``_normalise_parse_status`` 不同，这里空值是一等公民：本列落地之前，库里每一行都
    没有索引状态，把"没有记录"当成异常会淹掉日志。
    """
    status = str(value or "").strip().lower()
    if not status:
        return INDEX_STATUS_UNKNOWN
    if status in INDEX_STATUSES:
        return status
    logger.warning(f"[Docs] unknown index status {value!r} recorded as unknown")
    return INDEX_STATUS_UNKNOWN


def _resolved_size(storage_path, size_bytes) -> int | None:
    """Prefer the recorded size and fall back to the file actually on disk."""
    if size_bytes is not None:
        try:
            return max(int(size_bytes), 0)
        except (TypeError, ValueError):
            pass
    if storage_path in (None, ""):
        return None
    try:
        return int(os.path.getsize(str(storage_path)))
    except (OSError, TypeError, ValueError):
        return None


def _sidecar_key(filename: str, version: int) -> str:
    return f"{filename}|v{int(version)}"


def _sidecar_path(storage_path) -> Path | None:
    raw = str(storage_path or "").strip()
    if not raw:
        return None
    return Path(raw).parent / LOCAL_CATALOG_FILENAME


def _read_sidecar(path: Path) -> dict:
    """Load locally recorded version metadata; an absent file is not an error."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning(f"[Docs] catalog sidecar is unreadable: {exc}")
        return {}
    records = payload.get("documents") if isinstance(payload, dict) else None
    if not isinstance(records, dict):
        return {}
    return {str(key): dict(value) for key, value in records.items() if isinstance(value, dict)}


def _write_sidecar(path: Path, records: dict) -> None:
    temp = path.with_name(f".{path.name}.tmp")
    payload = json.dumps({"documents": records}, ensure_ascii=False, indent=2, sort_keys=True)
    temp.write_text(payload, encoding="utf-8")
    os.replace(temp, path)


_SIDECAR_FIELDS = (
    "filename",
    "version",
    "classification",
    "department",
    "owner_id",
    "size_bytes",
    "parse_status",
    "created_at",
)
#: 索引状态与排除原因也走 sidecar。``document_versions`` 没有这两列（加列需要新迁移，
#: 不在本单写域内），而 sidecar 在两条持久化路径上都会被 ``_record_local_version`` 写一次，
#: 所以它是当前唯一不需要迁移就能落地的持久处；读侧用 ``_apply_index_policy`` 补回。
_SIDECAR_FIELDS = _SIDECAR_FIELDS + ("index_status", "index_reason")


def _record_local_version(metadata: dict) -> None:
    """Mirror one version row into the JSON sidecar that sits beside the file."""
    path = _sidecar_path(metadata.get("storage_path"))
    if path is None:
        return
    try:
        records = _read_sidecar(path)
        records[_sidecar_key(str(metadata["filename"]), int(metadata["version"]))] = {
            key: metadata.get(key) for key in _SIDECAR_FIELDS
        } | {"recorded_path": str(metadata.get("storage_path") or "")}
        _write_sidecar(path, records)
    except OSError as exc:
        logger.warning(f"[Docs] catalog sidecar write failed: {exc}")
    except Exception as exc:
        logger.warning(f"[Docs] catalog sidecar write skipped: {exc}")


def _drop_local_versions(filename: str, storage_paths=()) -> None:
    """Remove every local record of a logical document after a delete."""
    paths = {Path(DOCUMENTS_DIR) / LOCAL_CATALOG_FILENAME}
    for storage_path in storage_paths:
        sidecar = _sidecar_path(storage_path)
        if sidecar is not None:
            paths.add(sidecar)
    for path in sorted(paths):
        records = _read_sidecar(path)
        kept = {key: value for key, value in records.items() if value.get("filename") != filename}
        if len(kept) == len(records):
            # Nothing here belongs to the document: leave the file untouched.
            continue
        try:
            if kept:
                _write_sidecar(path, kept)
            else:
                path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(f"[Docs] catalog sidecar prune failed: {exc}")


def public_document_row(row: dict) -> dict:
    """Shape one stored row for an API response.

    R4 asks the catalog to carry the stored size, the parse state and the owner, and
    the ownership marker tells a client whether a row predates document ownership and
    is therefore only visible to the management level.
    """
    public = dict(row)
    if "storage_path" in public:
        public["storage_path"] = _public_storage_path(public["storage_path"])
    storage_path = row.get("storage_path")
    public["owner_id"] = None if _is_unowned(row.get("owner_id")) else str(row.get("owner_id"))
    public["size_bytes"] = _resolved_size(storage_path, row.get("size_bytes"))
    public["parse_status"] = _normalise_parse_status(row.get("parse_status"))
    # R49: index_status / index_reason answer "will the assistant find this document", and a
    # row that was excluded has to say so out loud -- that is the whole point of the slice.
    # A row that recorded no decision at all (everything stored before R49, and any row the
    # sidecar cannot describe) stays silent instead of being stamped "unknown": absence is
    # the only honest answer there, and it keeps a client from rendering a historical
    # document as "deliberately not indexed". Clients must read the three cases as:
    #   index_status == "excluded"  -> 未索引，index_reason says why
    #   index_status == "indexed"   -> 已入索引
    #   key absent                  -> 本单之前入库的历史行，按 parse_status 显示，不得显示未索引
    recorded_status = row.get("index_status")
    if recorded_status in (None, ""):
        public.pop("index_status", None)
        public.pop("index_reason", None)
    else:
        status = _normalise_index_status(recorded_status)
        public["index_status"] = status
        public["index_reason"] = (
            str(row.get("index_reason") or "") if status == INDEX_STATUS_EXCLUDED else ""
        )
    public["ownership"] = OWNERSHIP_LEGACY if public["owner_id"] is None else OWNERSHIP_OWNED
    return public


def _sidecar_records_for(rows: list[dict]) -> dict:
    """Collect the sidecar records that describe the given rows, keyed by catalog id."""
    paths = set()
    for row in rows:
        sidecar = _sidecar_path(row.get("storage_path"))
        if sidecar is not None:
            paths.add(sidecar)
    records = {}
    for path in sorted(paths):
        records.update(_read_sidecar(path))
    return records


def _apply_index_policy(rows: list[dict]) -> list[dict]:
    """Give every listed row a definite index state, whatever persistence path wrote it.

    A row's own ``index_status`` wins; the sidecar is the fallback for a deployment whose
    catalog table has no such column. A reason is only ever carried by an excluded row -- a
    row that is indexed cannot keep an old reason around, because the pair is what an
    operator reads to decide whether a document can be found by the assistant.

    A row that recorded nothing keeps nothing: ``public_document_row`` then omits the
    fields, which is how a client tells "no decision was ever made about this version"
    apart from "this version was indexed".
    """
    # Only pay for the sidecar read when a row cannot answer for itself. The offline path
    # builds its rows out of that very file, so it never needs a second read; the database
    # path always does, because document_versions has no column for this yet.
    needs_overlay = any(row.get("index_status") in (None, "") for row in rows)
    records = _sidecar_records_for(rows) if needs_overlay else {}
    shaped: list[dict] = []
    for row in rows:
        stored = records.get(_sidecar_key(str(row.get("filename") or ""), int(row.get("version") or 0)))
        stored = stored if isinstance(stored, dict) else {}
        merged = dict(row)
        recorded = row.get("index_status")
        if recorded in (None, ""):
            recorded = stored.get("index_status")
        if recorded in (None, ""):
            merged.pop("index_status", None)
            merged.pop("index_reason", None)
        else:
            status = _normalise_index_status(recorded)
            merged["index_status"] = status
            merged["index_reason"] = (
                str(row.get("index_reason") or stored.get("index_reason") or "")
                if status == INDEX_STATUS_EXCLUDED
                else ""
            )
        shaped.append(merged)
    return shaped


def _public_rows(rows: list[dict]) -> list[dict]:
    """Return catalog rows with every server-side storage path de-identified."""
    return [public_document_row(row) for row in rows]


def _database_available() -> bool:
    """Reuse the application's database health state to avoid repeated slow retries."""
    auth_module = sys.modules.get("app.common.auth")
    if auth_module is not None:
        return bool(getattr(auth_module, "_db_ready", False))
    return _db_available is not False


def _conn():
    global _db_available
    import psycopg
    from psycopg.rows import dict_row

    try:
        conn = psycopg.connect(_PG_URL, row_factory=dict_row, connect_timeout=1)
    except Exception:
        _db_available = False
        raise
    _db_available = True
    return conn


def _is_production_environment() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in _PRODUCTION_ENVIRONMENTS


#: 「该由 migrations 建的那枚表不在」在本模块只有一句话术：``_ensure`` 生产分支那一句。判定
#: 只认它的前缀，不认「任何异常」——把宽捕获整体翻成 503 等于替真正的 bug 打掩护（同
#: ``app/api/v1/alerts.py:137`` 的 ``_migrations_first_at_http_exit``，R371 的裁定）。
MIGRATION_REQUIRED_PREFIX = "document_versions table is required in production"
#: 这一格的排查路径：响应侧共用仓里已有的那一枚 503 ``storage_unavailable``（零新增错误码），
#: 能把「表还没迁移」与「库没起」两张脸分辨开的只有下面那两行日志。
MIGRATION_REQUIRED_HINT = "migrations/0003_legacy_runtime_tables.sql"


def _schema_needs_migrations(exc: BaseException) -> bool:
    """这枚异常是不是「目录表还没建」：只认 ``_ensure`` 抛出的那一句前缀，其余一概不认。"""
    return str(exc).startswith(MIGRATION_REQUIRED_PREFIX)


def _require_ready_store(operation: str, *, migrations_missing: bool = False, write_failed: bool = False) -> None:
    """生产环境 + 目录存储未就绪 = 这一条腿拒答，不许回落本地台账（R383）。

    判的两件事都是本模块既有的读数，一枚都不新造、也不另算一遍：库在不在取
    ``_database_available()``（全模块唯一那枚 ``_db_ready`` 读者；读者总数由
    ``tests/test_r246_honest_readiness_claims.py`` 按 AST 管着，这里多引一处它当场红），是不是
    生产取 ``_is_production_environment()``（与 ``app/api/v1/alerts.py:61`` 同一把尺）。两支同时
    成立才拒。

    ``migrations_missing`` 与 ``write_failed`` 是同一道门上的另外两种「没就绪」（R394）：库连着、
    旗标也翻到了 True，可 ``_ensure()`` 现查到 ``document_versions`` 不在，或者那一发 INSERT 自己被打回。
    两者说的是同一件事——这一发的权威台账没落行。判定一枚都不新造，那道 503 也仍只在本闸抛出。

    为什么不许退成「200 + 本地台账」：客户机上那一屏照字面把 ``{"documents": []}`` 画成「这家
    公司没有知识文档」，而现场事实是「这一格问不出」。把问不出说成没有，与 ``/users``（R356）、
    ``/dashboard``（R332）、告警（R359）、通知（R299）是同一条裁定，文档目录是这条链上最后还在
    沉默回空的那一环。

    为什么开发/裸机/离线三条腿一个字都不改：本地台账回落是设计而不是 bug——``_ensure()`` 在非生产
    分支就地补 DDL，离线部署由 JSON sidecar 供数，那一支的回包形状、行数、排序逐字保持。本单分开
    的是三张脸，不是一律 503：把开发态一起打死同样是在说假话，只不过反着说。

    两扇门不是一扇门：``peek_next_document_version`` / ``record_document_version`` /
    ``delete_document_versions`` 三枚写口排在授权之后、在任何一次读写之前先过这道闸——权威库不在位
    时写不成却说成了，才是本单要治的病。两枚读口（``current_documents`` /
    ``list_document_versions``）**不设入口闸**：PostgreSQL 不在位时 JSON sidecar 是本模块设计内的
    第二本真账（见文件头那两行注释），那一支交出去的是盘上真实的行，不是
    ``app/api/v1/alerts.py`` 里客户机上恒为空的 ``_MEM_ALERTS``。读侧要改的只有「库连着、表却不在」
    那一格：它由五枚 catch-all 现查之后带 ``migrations_missing`` 走进这道闸——拒答的仍是这一句，
    只是排在那次现查之后。
    """
    refused = migrations_missing or write_failed
    if (_database_available() and not refused) or not _is_production_environment():
        return
    if migrations_missing:
        lead, hint = "生产库缺该由迁移建的目录表", f"code=storage_unavailable migration={MIGRATION_REQUIRED_HINT}"
    elif write_failed:
        lead = "生产环境这一发的权威台账写失败（sidecar 镜像排在前面已写、document_versions 这一发零行）"
        hint = "code=storage_unavailable write_failed=true"
    else:
        lead, hint = "生产环境目录存储没起", "code=storage_unavailable（PG 未起）"
    # 三张脸共用这一句出口，一字不改的是状态码与 detail；把三格分开的只有 lead / hint 两段文字。
    logger.warning(f"[Docs] {lead}，这一条腿拒答而不是回落本地台账: operation={operation} {hint}")
    raise HTTPException(status_code=503, detail="storage_unavailable")


def _path_is_readable(value) -> bool:
    """Report whether a recorded storage path still points at a real file."""
    raw = str(value or "").strip()
    if not raw:
        return False
    try:
        return Path(raw).is_file()
    except OSError:
        return False


def _local_row(filename: str, version: int, storage_path, stored: dict) -> dict:
    """Build one offline catalog row, preferring what the sidecar recorded."""
    return {
        "filename": filename,
        "version": int(version),
        # R57 §1 判定：此处**到达**权限判定，但本单不改，理由如下（三点都有实测支撑）。
        # (1) 缺陷是真的：缺 classification 键的 sidecar 行会沿 current_documents()/
        # list_document_versions() → app/api/v1/chat.py 的 _visible_document_rows →
        # _document_resource_scope → app/common/policy.py 的 authorization_decision 走进去，
        # 而判定在 policy.py:180 之后把这里的值当真实密级读。补 1 让缺键行以"1 级"身份通过
        # classification > clearance 的比较，正好违背 policy.py:178-179 已成文的口径
        # "密级缺失不视为公开、管理员也不得猜测"——它因此永远等不到 None。
        # (2) "改了会造成库可用/库不可用下不一致"这个理由不成立，已实测否证：两侧同向补 1
        # （_local_row(stored={}) 给 1；DB 侧本文件 :359 与 chat.py:620 同为
        # classification INT NOT NULL DEFAULT 1，NOT NULL 连显式 NULL 都拒），故不作为理由。
        # (3) 不改的真实理由是这个键一词两用：它既是判定输入，又逐字出现在
        # /documents/catalog 的响应体里（_visible_document_rows 用 public_document_row 原样
        # 透出整行，dashboard 概览就调这个端点）。把兜底直接换成 None 会让缺 sidecar 密级的
        # 行既不可见、目录列同时变空，一次改动跨两个关注点，还顺带替业主裁掉 H13（未标密级
        # 的上传算公开还是算不可见）。正解是把"参与判定的值"与"用于展示的值"拆开，需要单独
        # 设计：已按 R57 订正令另立新单（拟号 R58）交总控，本单不实现。论证见 R57 报告站点④。
        "classification": stored.get("classification", 1),
        "department": stored.get("department") or "",
        "owner_id": stored.get("owner_id"),
        "size_bytes": stored.get("size_bytes"),
        "parse_status": stored.get("parse_status"),
        "index_status": stored.get("index_status"),
        "index_reason": stored.get("index_reason"),
        "storage_path": _public_storage_path(storage_path),
        "created_at": stored.get("created_at")
        or _file_mtime(storage_path),
    }


def _file_mtime(storage_path) -> str:
    try:
        return datetime.fromtimestamp(os.path.getmtime(str(storage_path)), _tz).isoformat()
    except OSError:
        return datetime.now(_tz).isoformat()


def _version_number(row: dict) -> int:
    """Read a catalog row's version as the number it actually is.

    ``document_versions.version`` is ``INT NOT NULL`` (see ``_ensure`` in this file, and the
    ``version DESC`` in the index created by migrations/0006_document_ownership.sql),
    ``next_document_version`` returns an ``int``, and an offline row already passed through
    ``int()`` inside ``_local_version_rows``. So "which version is current" is a comparison over
    a **monotonic integer**, never a string comparison. An unreadable value is compared as 0 and
    logged; it never falls back to lexicographic order, which is exactly how ``10`` would end up
    in front of ``2``.
    """
    raw = row.get("version")
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning(
            f"[Docs] catalog row {row.get('filename')!r} has unreadable version {raw!r}; compared as 0"
        )
        return 0


def _ordered_by_current_version(rows: list[dict]) -> list[dict]:
    """Order rows the way ``ORDER BY filename, version DESC`` orders them.

    The shared half of the R292 contract: an ordering the database leg used to express only in
    SQL now exists once, in Python, and both legs pass through it.
    """
    return sorted(rows, key=lambda row: (str(row.get("filename") or ""), -_version_number(row)))


def _current_version_rows(rows: list[dict]) -> list[dict]:
    """Collapse stored versions into one "current" row per filename - the single arbiter.

    A logical document can have N stored versions but appears in the catalog once, and which row
    it appears as is the answer to "what is the current version". Before R292 that question had
    two different answers. The database leg asked SQL: ``ORDER BY filename, version DESC`` pushed
    the newest version into the first slot of each filename, so ``setdefault``'s first-write-wins
    happened to collect the newest. The offline leg (``_local_version_rows``) carried no version
    ordering at all, so first-write-wins collected **whatever the enumeration handed over first** -
    on NTFS the lexicographic order of ``name__vN.ext``, and for sidecar-only rows the
    ``sort_keys`` order of the JSON file. Both put ``v1`` before ``v2``, so an offline deployment
    reported its *oldest* stored version as current while the same rows in PostgreSQL reported the
    newest.

    Both legs now reach this one function and input order no longer participates in the decision.
    Two rows sharing a filename and a version cannot get here (``UNIQUE(filename, version)`` on the
    database side, the ``listed`` set on the offline side); if one ever does the first is kept,
    which is what SQL does with an unordered tie, so this rule strictly extends the old one.
    """
    current: dict[str, dict] = {}
    for row in _ordered_by_current_version(rows):
        current.setdefault(str(row.get("filename") or ""), row)
    return list(current.values())


def _local_version_rows(filename: str | None = None) -> list[dict]:
    rows = []
    pattern = re.compile(r"^(?P<stem>.+)__v(?P<version>\d+)(?P<ext>\.[^.]+)$")
    directory = Path(DOCUMENTS_DIR)
    if not directory.is_dir():
        return rows
    recorded = _read_sidecar(directory / LOCAL_CATALOG_FILENAME)

    for path in directory.iterdir():
        if not path.is_file() or path.name == LOCAL_CATALOG_FILENAME:
            continue
        match = pattern.match(path.name)
        if not match:
            continue
        original_name = f"{match.group('stem')}{match.group('ext')}"
        if filename and original_name != filename:
            continue
        version = int(match.group("version"))
        stored = recorded.get(_sidecar_key(original_name, version)) or {}
        rows.append(
            _local_row(
                filename=original_name,
                version=version,
                storage_path=path,
                stored=stored,
            )
        )

    # A stored version is addressed by resource id, so the legacy ``name__vN`` scan
    # never sees it. The sidecar rows are the only way an offline catalog can list
    # them, and dropping them would also drop their ownership.
    listed = {(row["filename"], row["version"]) for row in rows}
    for stored in recorded.values():
        name = str(stored.get("filename") or "")
        try:
            version = int(stored.get("version"))
        except (TypeError, ValueError):
            continue
        if not name or (name, version) in listed:
            continue
        if filename and name != filename:
            continue
        recorded_path = stored.get("recorded_path")
        if not _path_is_readable(recorded_path):
            continue
        path = Path(str(recorded_path))
        rows.append(_local_row(filename=name, version=version, storage_path=path, stored=stored))
        listed.add((name, version))
    # Neither of the two sources above can say which version is current: the directory scan
    # comes back in filesystem enumeration order and the sidecar in JSON key order. Hand the
    # rows over in the catalog order instead so no reader, this module's dedup included, can
    # pick up a "current version" from the filesystem. R292.
    return _ordered_by_current_version(rows)


def _ensure():
    global _initialized
    if _initialized:
        return
    with _conn() as conn:
        if _is_production_environment():
            row = conn.execute("SELECT to_regclass('public.document_versions') AS table_name").fetchone()
            if not row or row["table_name"] is None:
                raise RuntimeError("document_versions table is required in production; run migrations first")
            _initialized = True
            return
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_versions (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL,
                version INT NOT NULL,
                classification INT NOT NULL DEFAULT 1,
                department TEXT,
                storage_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                owner_id TEXT,
                size_bytes BIGINT,
                parse_status TEXT NOT NULL DEFAULT 'pending',
                UNIQUE(filename, version)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_versions_name ON document_versions(filename)")
        conn.commit()
    _initialized = True


def peek_next_document_version(filename: str) -> int:
    # 上传路径在落盘之前先问这一格要版本号：闸排在这里，生产缺库就整发拒，一字节都不落。
    _require_ready_store("version peek")
    if not _database_available():
        return next_document_version(_local_version_rows(filename), filename)
    try:
        _ensure()
        with _conn() as conn:
            rows = conn.execute(
                "SELECT filename, version FROM document_versions WHERE filename = %s ORDER BY version",
                (filename,),
            ).fetchall()
        return next_document_version([dict(row) for row in rows], filename)
    except Exception as exc:
        if _schema_needs_migrations(exc):
            _require_ready_store("version peek", migrations_missing=True)
        logger.warning(f"[Docs] version lookup fallback: {exc}")
        return next_document_version(_local_version_rows(filename), filename)


def _version_metadata(
    filename: str,
    classification: int,
    department: str,
    storage_path: str,
    version: int | None,
    principal,
    owner_id: str | None,
    size_bytes: int | None,
    parse_status: str,
    index_status: str = INDEX_STATUS_UNKNOWN,
    index_reason: str = "",
) -> dict:
    """Build the one shape both persistence paths share."""
    version = version or peek_next_document_version(filename)
    owner = _resolve_owner_id(principal, owner_id)
    status = _normalise_index_status(index_status)
    return {
        "filename": filename,
        "version": version,
        "classification": int(classification),
        "department": department or "",
        "storage_path": storage_path,
        "created_at": datetime.now(_tz).isoformat(),
        "owner_id": owner,
        "size_bytes": _resolved_size(storage_path, size_bytes),
        "parse_status": _normalise_parse_status(parse_status),
        "index_status": status,
        "index_reason": index_reason if status == INDEX_STATUS_EXCLUDED else "",
    }


def record_local_document_version(
    filename: str,
    classification: int,
    department: str,
    storage_path: str,
    version: int | None = None,
    *,
    principal=None,
    owner_id: str | None = None,
    size_bytes: int | None = None,
    parse_status: str = "pending",
    index_status: str = INDEX_STATUS_UNKNOWN,
    index_reason: str = "",
) -> dict:
    """Record one version through the local JSON path only.

    This is the write an offline deployment still gets: a stored file with no owner in
    either path would become a legacy row that ordinary staff can never list, which is
    exactly how a document ends up undeletable.
    """
    metadata = _version_metadata(
        filename,
        classification,
        department,
        storage_path,
        version,
        principal,
        owner_id,
        size_bytes,
        parse_status,
        index_status=index_status,
        index_reason=index_reason,
    )
    _record_local_version(metadata)
    return metadata


def record_document_version(
    filename: str,
    classification: int,
    department: str,
    storage_path: str,
    version: int | None = None,
    *,
    principal=None,
    owner_id: str | None = None,
    size_bytes: int | None = None,
    parse_status: str = "pending",
    index_status: str = INDEX_STATUS_UNKNOWN,
    index_reason: str = "",
) -> dict:
    """Register one stored version on both persistence paths, owner included.

    ``owner_id`` wins over ``principal``, which may be a Principal or a user mapping.
    The sidecar is written before the table: it is the only durable owner record when
    PostgreSQL is offline, and a version that exists on disk without ownership
    metadata would otherwise stay unattributable forever.

    ``index_status`` / ``index_reason`` only ever reach the sidecar: ``document_versions``
    has no such column, and inventing one is a migration this slice does not own. The read
    paths put them back with ``_apply_index_policy``, so a listing answers the same way on
    both persistence paths.
    """
    metadata = _version_metadata(
        filename,
        classification,
        department,
        storage_path,
        version,
        principal,
        owner_id,
        size_bytes,
        parse_status,
        index_status=index_status,
        index_reason=index_reason,
    )

    # 生产而库没起：整发拒，连本地镜像都不写——只落在 sidecar 上的「已登记」缺一本真账。
    _require_ready_store("version record")
    _record_local_version(metadata)

    if not _database_available():
        return metadata
    try:
        _ensure()
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO document_versions
                (filename, version, classification, department, storage_path, created_at,
                 owner_id, size_bytes, parse_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (filename, version) DO UPDATE SET
                    classification = EXCLUDED.classification,
                    department = EXCLUDED.department,
                    storage_path = EXCLUDED.storage_path,
                    owner_id = COALESCE(document_versions.owner_id, EXCLUDED.owner_id),
                    size_bytes = COALESCE(EXCLUDED.size_bytes, document_versions.size_bytes),
                    parse_status = EXCLUDED.parse_status
                """,
                (
                    metadata["filename"],
                    metadata["version"],
                    metadata["classification"],
                    metadata["department"] or None,
                    metadata["storage_path"],
                    metadata["created_at"],
                    metadata["owner_id"],
                    metadata["size_bytes"],
                    metadata["parse_status"],
                ),
            )
            conn.commit()
    except Exception as exc:
        logger.warning(f"[Docs] version record not written: {exc}")
        _require_ready_store("version record", migrations_missing=_schema_needs_migrations(exc),
                             write_failed=True)
    return metadata


def current_documents() -> list[dict]:
    # 读侧入口不闸：库没起时这一条腿交的是设计内的 sidecar（上面那段判据），一字未改。
    # 「库连着、表却不在」那一格由下面的 catch-all 现查之后带 migrations_missing 进闸。
    if not _database_available():
        rows = _local_version_rows()
    else:
        try:
            _ensure()
            with _conn() as conn:
                rows = [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT {_SELECT_COLUMNS}
                        FROM document_versions
                        ORDER BY filename, version DESC
                        """
                    ).fetchall()
                ]
        except Exception as exc:
            if _schema_needs_migrations(exc):
                _require_ready_store("current listing", migrations_missing=True)
            logger.warning(f"[Docs] current listing fallback: {exc}")
            rows = _local_version_rows()

    # One arbiter for "current version", the same on both legs (R292). The ORDER BY above is
    # still worth sending - it makes the read deterministic - but correctness no longer depends
    # on it, which is the whole point: the offline leg has no ORDER BY to depend on.
    latest = _current_version_rows(rows)
    ordered = sorted(latest, key=lambda item: item["created_at"], reverse=True)
    return _public_rows(_apply_index_policy(ordered))


def list_document_versions(filename: str, limit: int | None = None) -> list[dict]:
    # 与 current_documents 同一口径：入口不闸，缺表那一格由下面的 catch-all 现查之后拒答。
    # R404：``limit`` 只改「读几行」，不改「读哪一本账」。带 limit 时 SQL 仍是同一句
    # ``ORDER BY version DESC``，只在尾部多挂一枚 ``LIMIT %s``；不带 limit 的那一支逐字不变。
    if not _database_available():
        return _public_rows(
            _apply_index_policy(
                _ordered_by_current_version(_local_version_rows(filename))[:limit]
            )
        )
    limit_clause = "LIMIT %s" if limit is not None else ""
    try:
        _ensure()
        with _conn() as conn:
            rows = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM document_versions
                WHERE filename = %s
                ORDER BY version DESC
                {limit_clause}""",
                (filename,) if limit is None else (filename, limit),
            ).fetchall()
        return _public_rows(_apply_index_policy([dict(row) for row in rows]))
    except Exception as exc:
        if _schema_needs_migrations(exc):
            _require_ready_store("history listing", migrations_missing=True)
        logger.warning(f"[Docs] history fallback: {exc}")
        return _public_rows(
            _apply_index_policy(
                _ordered_by_current_version(_local_version_rows(filename))[:limit]
            )
        )


def latest_document_version(filename: str) -> dict | None:
    """R404：台账里最新的那一行 = 单行读（``ORDER BY version DESC LIMIT 1``）。

    权限判定只需要这一行，所以这一枚一次都不取全量。它借 ``list_document_versions``
    同一枚 scope 里的同一句 SQL，只带上 ``limit=1``：本模块的存储读者、``_ensure()``
    调用点与 catch-all 的配对一枚都没多（那两本账由 R377／R383 按 AST 数着）。

    两张脸按现读分开，不许混着记：

      * 台账有行、盘上的文件已经没了：照样交回那一行。文件在不在是下载与预览那条腿的事
        （``app/api/v1/chat.py`` 的 ``_latest_document_version`` 才问 ``os.path.exists``），
        判定不替它说话——「有这份文档，但你没权看」与「盘上那份文件不见了」是两句话。
      * 台账没有行：交回 ``None``，由调用方在判定之前答 404，不进判定。
    """
    rows = list_document_versions(filename, limit=1)
    return rows[0] if rows else None


def _logical_documents_table_exists(conn) -> bool:
    """Ask whether the lazy logical table is there, without ever poisoning the transaction.

    ``to_regclass`` is the only safe probe: a ``DELETE`` against a missing table would abort
    the surrounding transaction and take the version rows down with it. Any surprise in the
    cursor answer (a shape this function does not recognise, a driver that refuses the
    statement) is reported as "absent", which costs a skipped row and not the whole delete.

    Known unknown: the shapes read here - a ``dict_row`` mapping, a NULL, and a probe that
    raises - are the three the tests reproduce against a fake connection. Real psycopg3
    returns a plain ``dict`` for ``row_factory=dict_row``, which is what the first branch
    expects, but no test in this repository has been run against a live database, so the
    probe has not been observed on one. Verification belongs to the next backend-image
    acceptance run.
    """
    try:
        row = conn.execute("SELECT to_regclass('public.documents') AS documents_table").fetchone()
        if row is None:
            return False
        if isinstance(row, dict):
            return bool(row.get("documents_table"))
        try:
            return bool(dict(row).get("documents_table"))
        except (TypeError, ValueError):
            return bool(row[0])
    except Exception as exc:
        logger.warning(f"[Docs] logical table probe failed: {exc}")
        return False


def delete_document_versions(filename: str, storage_paths=()) -> None:
    """Remove every catalog row of a logical document from both persistence paths.

    The ``documents`` row goes in the same transaction as its versions. The upload path
    UPSERTS it (``_upsert_document`` in app/api/v1/chat.py) and nothing else in the
    repository ever removed it, which is how a deployment ends up with logical rows that
    point at files no longer on disk while ``document_versions`` reads clean. Cleaning it
    here - rather than in one more caller - is why this function is the one the delete
    route already trusts.

    R383：拒答不许留下半件事。本地镜像的清理排在两次现查之后，生产库里表不在时这一格整发拒，
    ``document_versions`` 与本地 sidecar 都原样不动——今天删掉本地那一半却说「没删成」，等于把
    一条还能重试的记录先抹了。离线那一支的净效果没变（清完即返回），只是位置跟着两条持久化路径
    的同一条口径走。
    """
    _require_ready_store("version deletion")
    if not _database_available():
        _drop_local_versions(filename, storage_paths)
        return
    try:
        _ensure()
        with _conn() as conn:
            conn.execute(
                "DELETE FROM document_versions WHERE filename = %s",
                (filename,),
            )
            if _logical_documents_table_exists(conn):
                conn.execute(
                    "DELETE FROM documents WHERE filename = %s",
                    (filename,),
                )
            conn.commit()
    except Exception as exc:
        if _schema_needs_migrations(exc):
            _require_ready_store("version deletion", migrations_missing=True)
        logger.warning(f"[Docs] version deletion fallback: {exc}")
    _drop_local_versions(filename, storage_paths)
