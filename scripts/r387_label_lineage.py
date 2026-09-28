"""R387 取证件：一份文档的「部门 / 密级」标签从表单走到 `chunk_vectors` 的那一格，逐跳可查。

本件**只读**，而且是按构造只读：
① PostgreSQL 侧每条语句都是 SELECT，并在会话上先压 `default_transaction_read_only = on`；
② 遗留向量库侧不走 `chromadb.PersistentClient`（它会推进 `chroma.sqlite3` 的 mtime；🔴 该库今天实测跑的是 legacy rollback journal（header byte18/19 = 1/1），根本不产生 WAL），
   走 `sqlite3` 的 `file:...?mode=ro` URI —— AGENTS.md 明令 Chroma 是退役中的遗留件，
   本单一枚新的 Chroma 写点都不许造。
③ 附 `--expect-database` 闸门：连上的库名与预期不符就停手，不把别人的库读成生产。

它把三个判据的答案写成可复跑的数，不写成散文：
* 判据①：血缘链逐跳（`LINEAGE_HOPS`，行号由锚块按内容现读，不是抄来的）；
* 判据②：标签为什么全空的定量分桶（源头就没有 / 源头有但没传下来 / 传下来了但写错列）；
* 判据④：把「越权 0 条」改写成一条**今天能失败**的判据（`classify_arm`）。

用法::

    python scripts/r387_label_lineage.py --json %TEMP%/r387-ledger.json
    python scripts/r387_label_lineage.py --no-db --chroma-sqlite <path> --documents-dir documents
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).parents[1].resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.connection import open_connection, parse_database_settings  # noqa: E402

# ---------------------------------------------------------------------------
# 判据①：血缘链。kind 三取一 —— truth（真值在走）/ default（默认值兜底）/ hardcoded（硬编覆盖）。
# 🔴 这一块的行号全是派生的：文件里不许出现任何「某文件:行号」字面量。每一格配一枚锚块
#    （若干行原文），运行时在被引文件里现读定位 —— 锚块语义就是 `rg -F`：逐行 strip 之后
#    连续固定串匹配，不是正则。每枚锚块必须在整个文件里恰枚一枚命中：
#      命中 0 枚 = 锚已腐（那一格被删或被改名）；
#      命中 ≥2 枚 = 锚不再是唯一锚 —— 并树往中间插一段长得像的代码是常事，这时候
#                   「取第一次命中」等于把整条血缘表指到别人身上去，比红更糟，
#                   所以两条路都不给：当场记进 LINEAGE_ANCHOR_FAILURES，取证主流程 ABORT。
#    ⇒ 被引文件被并树撑长时这张表一个字都不用改，行号自己跟着走；锚腐时它自己报。
#    下牙件：tests/test_r387_label_ruler_teeth.py（逐格比对文档 §1 那张表）。
# ---------------------------------------------------------------------------

#: 锚块是在这一枚基点的内容上挖出来的。这只是出处账，判据不依赖它。
ANCHOR_BASE_COMMIT = "64b3f3c"

#: 每一格的锚：key -> (被引文件, 起点锚, 终点锚或 None)。锚 = (目标行在锚块里的下标, 连续行原文)。
LINEAGE_SITES: dict = {
    "hop1": ("app/api/v1/chat.py",
             (0, ["async def upload_document(file: UploadFile = File(...),"]),
             (0, ["department: str = Form(\"\"),"])),
    "hop2": ("app/api/v1/chat.py",
             (0, ["department = str(getattr(principal, \"department\", \"\") or \"\")"]),
             None),
    "hop2n": ("app/api/v1/chat.py",
             (0, ["The document scope is decided here rather than accepted from the form: retrieval"]),
             (0, ["department is what the datasets and artifacts registries already use."])),
    "hop2v": ("frontend/src/components/DocPanel.vue",
             (0, ["// 🔴 这里永远不 append department：app/api/v1/chat.py 那段 docstring 写明了理由 —— 检索按"]),
             (0, ["// 【来问的人】的部门去匹配文档，客户端能挑部门就等于允许往别人的结果里投稿，服务端按 principal 自己定。"])),
    "hop3f": ("app/common/authorization.py",
             (0, ["def principal_from_request(request) -> Principal | None:"]),
             None),
    "hop3g": ("app/agents/contracts.py",
             (0, ["department=str(user.get(\"department\") or \"\"),"]),
             None),
    "hop3n": ("app/api/v1/auth.py",
             (0, ["@router.put(\"/profile\")"]),
             (0, ["\"message\": \"画像里的 department 是只读派生值，员工自助改不了；\""])),
    "hop4a": ("app/common/auth.py",
             (0, ["def _bootstrap_admin_department() -> str:"]),
             (0, ["return os.getenv(\"AUTH_DEPARTMENT\", \"\").strip()"])),
    "hop4b": ("app/common/auth.py",
             (0, ["def _seed_bootstrap_admin(conn) -> None:"]),
             (0, ["logger.info(\"[Security] Initial admin account created from configured bootstrap credentials\")"])),
    "hop4n": ("app/common/auth.py",
             (0, ["if conn.execute(\"SELECT COUNT(*) AS c FROM users\").fetchone()[\"c\"]:"]),
             (0, ["return", "username, password_hash = _bootstrap_admin_credentials()"])),
    "hop5f": ("app/api/v1/chat.py",
             (0, ["classification: int = Form(1),"]),
             None),
    "hop5g": ("app/api/v1/chat.py",
             (0, ["classification,", "department or None,"]),
             None),
    "hop5h": ("app/api/v1/chat.py",
             (5, ["if ok:", "version_meta = _record_uploaded_version(", "principal=principal,", "owner_id=owner_id,", "filename=inspection.display_filename,", "classification=classification,"]),
             None),
    "hop5i": ("app/api/v1/chat.py",
             (0, ["classification=classification,", "department=department,", "scope=_document_resource_scope(inspection.display_filename, version_meta),"]),
             None),
    "hop5j": ("app/api/v1/chat.py",
             (0, ["classification=classification,", "department=department,", "storage_path=file_path,", "version=next_version,", "size_bytes=written,", "parse_status=\"ready\",", "index_status=INDEX_STATUS_EXCLUDED,"]),
             None),
    "hop5v": ("frontend/src/components/DocPanel.vue",
             (0, ["item.classification = normalizeClassification(uploadClassification.value)"]),
             (0, ["form.append('classification', String(item.classification))"])),
    "hop6": ("app/api/v1/chat.py",
             (0, ["def _record_uploaded_version("]),
             (1, ["logger.warning(f\"[Docs] local version record failed: {exc}\")", "return metadata"])),
    "hop6b": ("app/api/v1/chat.py",
             (0, ["def _upsert_document("]),
             (2, ["),", ")", "conn.commit()"])),
    "hop6c": ("app/api/v1/chat.py",
             (0, ["\"INSERT INTO documents (filename, classification, department, owner_id, size_bytes, parse_status) \""]),
             None),
    "hop6n": ("app/api/v1/chat.py",
             (0, ["department or None,", "owner_id or None,"]),
             None),
    "hop7": ("app/documents/catalog.py",
             (0, ["def _version_metadata("]),
             (1, ["\"index_reason\": index_reason if status == INDEX_STATUS_EXCLUDED else \"\",", "}"])),
    "hop7b": ("app/documents/catalog.py",
             (0, ["def record_document_version("]),
             (1, ["),", ")"])),
    "hop7c": ("app/documents/catalog.py",
             (0, ["\"department\": department or \"\","]),
             None),
    "hop7d": ("app/documents/catalog.py",
             (0, ["metadata[\"department\"] or None,"]),
             None),
    "hop7e": ("app/documents/catalog.py",
             (0, ["INSERT INTO document_versions"]),
             (0, ["owner_id, size_bytes, parse_status)"])),
    "hop8": ("app/api/v1/chat.py",
             (0, ["def _document_publication("]),
             (2, ["content_hash=str((rows[0] if rows else {}).get(\"hash\") or \"\"),", "**shared,", ")"])),
    "hop8b": ("app/rag/indexing.py",
             (0, ["classification: int = 1"]),
             (0, ["department: str = \"\""])),
    "hop8c": ("app/rag/indexing.py",
             (0, ["def scope_metadata(self) -> dict:"]),
             (1, ["\"retirement\": self.retirement,", "}"])),
    "hop8d": ("app/rag/indexing.py",
             (0, ["\"\"\"The scope carried in every chunk row: classification and department live here.\"\"\""]),
             None),
    "hop8n": ("app/rag/indexing.py",
             (0, ["return {", "\"filename\": str(self.filename),"]),
             (1, ["\"retirement\": self.retirement,", "}"])),
    "hop9": ("app/rag/indexing.py",
             (0, ["def chunk_rows(self) -> tuple[IndexChunk, ...]:"]),
             (0, ["return tuple(rows)"])),
    "hop9c": ("app/rag/indexing.py",
             (0, ["def write_chunks(self, publication: DocumentIndexPublication, version: IndexVersion) -> int:"]),
             None),
    "hop10": ("app/api/v1/chat.py",
             (0, ["ok, msg = await asyncio.to_thread("]),
             (1, ["department or None,", ")"])),
    "hop10b": ("app/rag/retriever.py",
             (0, ["def add_document(self, filename: str, content: str,"]),
             (0, ["classification: int = 1, department: str | None = None) -> tuple[bool, str]:"])),
    "hop10c": ("app/rag/retriever.py",
             (0, ["metadatas = ["]),
             (0, ["]", "# R21：先验后删。向量不合格就在这里抛，一行业务数据都不动。"])),
    "hop10d": ("app/api/v1/chat.py",
             (0, ["department or None,", ")"]),
             None),
    "hop10e": ("app/rag/retriever.py",
             (0, ["\"classification\": int(classification), \"department\": department or \"\"}"]),
             None),
    "hop11": ("app/rag/pg_store.py",
             (0, ["def build_rows(self, ids, documents, metadatas, embeddings) -> list:"]),
             (0, ["return rows"])),
    "hop11c": ("app/rag/pg_store.py",
             (0, ["str(values.get(\"department\") or \"\"),"]),
             None),
    "hop11d": ("app/rag/pg_store.py",
             (0, ["_UPSERT_VECTOR_SQL = ("]),
             (0, [")", "_DELETE_VECTOR_SQL = \"DELETE FROM chunk_vectors WHERE vector_id = ANY(%s::text[])\""])),
    "hop11n": ("migrations/0010_pgvector_chunks.sql",
             (0, ["COMMENT ON COLUMN chunk_vectors.department IS"]),
             (0, ["'Duplicated from the vector metadata so a filtered search can pre-filter without a join. owner_id is deliberately NOT duplicated: it is a document-level fact owned by the catalog, and a second copy of it here could drift from the authority. department and classification are not separable from the chunk the retriever already holds.';"])),
    "hop12": ("app/rag/filters.py",
             (0, ["departments = frozenset("]),
             (1, ["departments=departments,", ")"])),
    "hop12b": ("app/rag/pg_store.py",
             (0, ["def _scope_clause(column: str, values, sql_type: str):"]),
             (0, ["return _scope_clause(key, value[\"$in\"], _SCOPE_COLUMNS[key])"])),
    "hop12c": ("app/rag/filters.py",
             (0, ["if not departments:"]),
             (0, [")", "return DocumentRetrievalScope("])),
    "hop12d": ("app/rag/filters.py",
             (0, ["if is_administrator(principal):"]),
             (1, ["departments=None,", ")"])),
    "hop12e": ("app/rag/pg_store.py",
             (0, ["raise ScopeFilterUntranslatable(", "f\"{column} 的 $in 里有空串：两侧对『没有部门』的表示法不同，\""]),
             (0, ["\"这一档不做猜测，宁可拒答\")"])),
}


class AnchorNotUnique(RuntimeError):
    """凭据锚不再是唯一锚：命中 0 枚或 ≥2 枚。这时候取哪一枚都是猜。"""


_LINE_CACHE: dict = {}


def _lines_of(path: Path) -> list:
    key = str(path)
    if key not in _LINE_CACHE:
        _LINE_CACHE[key] = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
    return _LINE_CACHE[key]


def anchor_lines(file: str, anchor: tuple, root: Path = ROOT) -> list:
    """这枚锚在这个文件里的全部命中（目标行的 1-based 行号）。固定串匹配，不是正则。"""
    offset, block = anchor
    want = [line.strip() for line in block]
    lines = _lines_of(root / file)
    return [i + 1 + offset for i in range(len(lines) - len(want) + 1) if lines[i:i + len(want)] == want]


def _one_hit(label: str, file: str, anchor: tuple, root: Path) -> int:
    hits = anchor_lines(file, anchor, root)
    if not hits:
        raise AnchorNotUnique("%s 的锚在 %s 里命中 0 枚（锚已腐，那一格不在原处）：锚首行 %r"
                              % (label, file, anchor[1][0]))
    if len(hits) > 1:
        raise AnchorNotUnique("%s 的锚在 %s 里命中 %d 枚 %s —— 不再是唯一锚，取第一次命中就是猜"
                              % (label, file, len(hits), hits))
    return hits[0]


def resolve_site(key: str, root: Path = ROOT) -> tuple:
    """把一格解成 (文件, 起始行, 结束行)。这里没有「取第一枚」这条路：不唯一就抛。"""
    file, start, end = LINEAGE_SITES[key]
    first = _one_hit(key + " 起点", file, start, root)
    last = first if end is None else _one_hit(key + " 终点", file, end, root)
    if last < first:
        raise AnchorNotUnique("%s：终点锚（%d）落到起点锚（%d）之前，区间不成立" % (key, last, first))
    return (file, first, last)


class _Cites(dict):
    """渲染表：{hop5g} -> "4216"，{hop6b} -> "1023-1058"。缺的格端出显式标记，绝不悄悄留旧数。"""

    def __missing__(self, key):
        return "<锚失效:" + key + ">"


def resolve_cites(root: Path = ROOT):
    """现读全部站点 -> (渲染表, 失败清单)。失败不抛：让判据红在具名那一格，而不是整件收不起来。"""
    cites, failures = _Cites(), []
    for key in LINEAGE_SITES:
        try:
            _file, first, last = resolve_site(key, root)
        except (AnchorNotUnique, OSError) as exc:
            failures.append("%s：%s" % (key, exc))
            continue
        cites[key] = str(first) if first == last else "%d-%d" % (first, last)
    return cites, failures


CITES, LINEAGE_ANCHOR_FAILURES = resolve_cites()

LINEAGE_TEMPLATES: tuple = (
    {
        "seq": 1,
        "stage": "接口收到什么",
        "site": "app/api/v1/chat.py:{hop1}",
        "carrier": "upload_document(file, classification=Form(1), department=Form(''))",
        "kind": "default",
        "note": "两枚 Form 默认值就是全库那两个签名的源头：department 默认空串、classification 默认 1。",
    },
    {
        "seq": 2,
        "stage": "服务端立刻丢弃客户端那一格",
        "site": "app/api/v1/chat.py:{hop2}",
        "carrier": "department = str(getattr(principal, 'department', '') or '')",
        "kind": "hardcoded",
        "note": (
            "全链第一处「真值被丢弃」：第 1 跳那枚形参 department 在这里被整体覆盖成 "
            "principal.department，客户端传什么都不看。理由写在 :{hop2n} 的 docstring 与 "
            "frontend/src/components/DocPanel.vue:{hop2v} —— 检索按【来问的人】的部门匹配文档，"
            "放客户端挑部门等于允许往别人的结果里投稿。这一跳是设计不是缺陷；它的后果是"
            "**文档部门没有第二个入口**，唯一入口 = 上传人自己的部门。"
        ),
    },
    {
        "seq": 3,
        "stage": "主体的部门从哪来",
        "site": "app/common/authorization.py:{hop3f} -> app/agents/contracts.py:{hop3g}",
        "carrier": "principal_from_request(request) -> Principal.department = str(user.get('department') or '')",
        "kind": "default",
        "note": "唯一事实源是 users.department；app/api/v1/auth.py:{hop3n} 明写员工自助写不了这一格（只读派生值）。",
    },
    {
        "seq": 4,
        "stage": "账号的部门又是谁写的",
        "site": "app/common/auth.py:{hop4a}, :{hop4b}",
        "carrier": "_bootstrap_admin_department() = os.getenv('AUTH_DEPARTMENT', '') -> INSERT INTO users(..., department)",
        "kind": "default",
        "note": (
            "全链真正的断点：建库时那枚管理员只在 AUTH_DEPARTMENT 有值时才有部门，否则落 NULL；"
            "且 :{hop4n} 那个 `if count(*) : return` 使 `_seed_bootstrap_admin` 只在 users 为空表时跑一次，"
            "之后补设环境变量也不会回填既有账号。生产实测 users 三行：admin / evalbot 的 department 是 "
            "SQL NULL，只有 dataowner 是「财务部」，而 dataowner 是 datasets 侧的上传账号，不走 POST /upload。"
        ),
    },
    {
        "seq": 5,
        "stage": "classification 走的是另一条路",
        "site": "app/api/v1/chat.py:{hop5f} -> :{hop5g} / :{hop5h} / :{hop5i} / :{hop5j}",
        "carrier": "form 的 classification 原样向下传",
        "kind": "truth",
        "note": (
            "密级没有被服务端覆盖（与 department 不同命）：R313 起前端真的把它发出去"
            "（frontend/src/components/DocPanel.vue:{hop5v}）。但现库 1008 枚全 = 1，说明这 1008 枚"
            "早于 R313，或出自不带这一格的通路（upload_all.py、scripts/seed_workspace.py）。"
            "**通路是通的，只是从没被真值喂过。**"
        ),
    },
    {
        "seq": 6,
        "stage": "目录行（逻辑文档）",
        "site": "app/api/v1/chat.py:{hop6} -> :{hop6b}",
        "carrier": "_upsert_document(...) -> INSERT INTO documents(filename, classification, department, ...)",
        "kind": "default",
        "note": ":{hop6n} 落 `department or None` —— 空串在这里变成 SQL NULL。",
    },
    {
        "seq": 7,
        "stage": "目录行（版本）",
        "site": "app/documents/catalog.py:{hop7} / :{hop7b}",
        "carrier": "record_document_version -> _version_metadata -> INSERT INTO document_versions(..., department, ...)",
        "kind": "default",
        "note": ":{hop7c} `department or ''`，:{hop7d} 又 `metadata['department'] or None`。同一个空值在同一趟里换了两种写法。",
    },
    {
        "seq": 8,
        "stage": "索引载体（chunk 行的 scope）",
        "site": "app/api/v1/chat.py:{hop8} -> app/rag/indexing.py:{hop8b}, :{hop8c}",
        "carrier": "DocumentIndexPublication(classification=..., department=...) -> scope_metadata()",
        "kind": "default",
        "note": (
            "indexing.py:{hop8b} 那两枚 dataclass 默认值（`classification: int = 1` / `department 默认为空串`）"
            "是兜底而不是这一跳的来源；来源是 chat.py 传进来的形参。:{hop8d} 那句 docstring「The scope carried "
            "in every chunk row」说的就是 :{hop8n} 这个 dict。"
        ),
    },
    {
        "seq": 9,
        "stage": "chunks 表（发布账）",
        "site": "app/rag/indexing.py:{hop9} chunk_rows / :{hop9c} write_chunks",
        "carrier": "IndexChunk.metadata = scope_metadata()",
        "kind": "default",
        "note": "实测 chunks 1008 行、metadata->>'department' 非空 0 枚 —— 与 chunk_vectors 同空，两本账一致地空。",
    },
    {
        "seq": 10,
        "stage": "遗留引擎元数据（今天仍在服务的读路径）",
        "site": "app/api/v1/chat.py:{hop10} -> app/rag/retriever.py:{hop10b}, :{hop10c}",
        "carrier": "add_document(filename, content, classification, department or None) -> {... 'department': department or ''}",
        "kind": "default",
        "note": "chat.py:{hop10d} 把空串折回 None，retriever.py:{hop10e} 再把 None 折回 ''。绕一圈还是空。",
    },
    {
        "seq": 11,
        "stage": "chunk_vectors.department 是谁写的那一格",
        "site": "app/rag/pg_store.py:{hop11}（:{hop11c}）-> :{hop11d}",
        "carrier": "build_rows: str(values.get('department') or '')  <- values = 遗留引擎那份 metadata",
        "kind": "default",
        "note": (
            "落库值**直接复制遗留引擎的元数据**，不查 catalog、不查 users。所以 PG 那一格永远不可能比上游更聪明："
            "上游空，它就空。migrations/0010_pgvector_chunks.sql:{hop11n} 那句 COMMENT「Duplicated from the vector "
            "metadata」说的就是这个动作，它同段还解释了为什么 `owner_id` 被刻意不复制。"
        ),
    },
    {
        "seq": 12,
        "stage": "读侧谓词（越权判定的出处）",
        "site": "app/rag/filters.py:{hop12} -> app/rag/pg_store.py:{hop12b}",
        "carrier": "{'$and': [classification $in levels, department $in departments]} -> sql_scope_filter",
        "kind": "truth",
        "note": (
            "filters.py:{hop12c}：非管理员且主体没有部门 -> 直接 raise（authorization_unavailable）。"
            "filters.py:{hop12d}：管理员那一档**根本不发部门谓词**（`departments=None`）。"
            "pg_store.py:{hop12e}：`$in` 里出现空串 -> 拒答，不猜。"
            "⇒ 生产上部门这条腿今天对管理员无约束、对无部门账号是拒答、对有部门账号是恒空集，三种都不是「隔离生效」。"
        ),
    },
)


def render_hop(hop: dict, cites) -> dict:
    """把一跳的模板渲染成读数：site 与 note 里的每个数字都来自 CITES，模板自己没有数字。"""
    out = dict(hop)
    out["site"] = str(hop["site"]).format_map(cites)
    out["note"] = str(hop["note"]).format_map(cites)
    return out


#: 文档 §1 那张血缘表第 3 格的模板：与 site 同源同数，只是分隔符换成人话（→、、括号里的内层引用）。
#: 🔴 表里印的行号由这里生成，跑 `--emit-doc-cells` 重落地，不许手改；两头等值由下牙件逐格钉。
HOP_DOC_CELLS: dict = {
    1: "`app/api/v1/chat.py:{hop1}`",
    2: "`app/api/v1/chat.py:{hop2}`",
    3: "`app/common/authorization.py:{hop3f}` → `app/agents/contracts.py:{hop3g}`",
    4: "`app/common/auth.py:{hop4a}`、`:{hop4b}`",
    5: "`app/api/v1/chat.py:{hop5f}` → `:{hop5g}` / `:{hop5h}` / `:{hop5i}` / `:{hop5j}`",
    6: "`app/api/v1/chat.py:{hop6}` → `:{hop6b}`（`:{hop6c}` / `:{hop6n}`）",
    7: "`app/documents/catalog.py:{hop7}`、`:{hop7b}`（`:{hop7c}` / `:{hop7e}` / `:{hop7d}`）",
    8: "`app/api/v1/chat.py:{hop8}` → `app/rag/indexing.py:{hop8b}`、`:{hop8c}`",
    9: "`app/rag/indexing.py:{hop9}`、`:{hop9c}`",
    10: "`app/api/v1/chat.py:{hop10}` → `app/rag/retriever.py:{hop10b}`、`:{hop10c}`",
    11: "`app/rag/pg_store.py:{hop11}`（`:{hop11c}`）→ `:{hop11d}`",
    12: "`app/rag/filters.py:{hop12}` → `app/rag/pg_store.py:{hop12b}`（`:{hop12e}`）",
}


def render_doc_cells(cites=None) -> dict:
    cites = CITES if cites is None else cites
    return {seq: cell.format_map(cites) for seq, cell in HOP_DOC_CELLS.items()}


LINEAGE_HOPS: tuple = tuple(render_hop(hop, CITES) for hop in LINEAGE_TEMPLATES)
LINEAGE_DOC_CELLS: dict = render_doc_cells()


FIRST_TRUTH_LOST_AT = 2
REAL_BREAK_POINT_AT = 4

# ---------------------------------------------------------------------------
# 判据④：可失败的验收 C 判据。
# ---------------------------------------------------------------------------

VERIFIED = "已验"
FAILED = "不通过（有越权）"
UNVERIFIED = "未验"

REASON_BREACH = "越权命中不为零"
REASON_NO_LABELLED_CHUNK = "语料的 department 全为空：部门谓词恒空集，「越权 0 条」只在空集上成立"
REASON_NO_DEPARTMENT_SELECTIVITY = "语料只有一枚非空部门：没有跨部门可选"
REASON_NO_CLASSIFICATION_SELECTIVITY = "语料只有一档密级：没有跨密级可选"
REASON_EMPTY_RETURN = "该臂交回 0 行：0 越权与 0 召回是同一个空集，不是隔离"
REASON_PRINCIPAL_UNSCOPED = "主体侧没有部门：这一臂测的不是部门隔离"


@dataclass(frozen=True)
class ArmReading:
    """验收 C 里一条臂的实测形状。故意不含正文，只含可核对的计数。"""

    name: str
    principal_departments: tuple = ()
    principal_clearance: int = 1
    corpus_labelled_chunks: int = 0
    corpus_departments: tuple = ()
    corpus_classifications: tuple = ()
    recalled: int = 0
    breaches: int = 0
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        payload = {
            "arm": self.name,
            "principal_departments": sorted(self.principal_departments),
            "principal_clearance": self.principal_clearance,
            "corpus_labelled_chunks": self.corpus_labelled_chunks,
            "corpus_departments": sorted(self.corpus_departments),
            "corpus_classifications": sorted(self.corpus_classifications),
            "recalled": self.recalled,
            "breaches": self.breaches,
        }
        payload.update(self.metadata)
        return payload


def classify_arm(arm: ArmReading) -> dict:
    """把一条臂的读数判成 已验 / 未验 / 不通过，并给出唯一原因码。

    判序是刻意的：越权优先（安全问题不能被「未验」盖掉），随后逐条问「这个 0 是不是空集」。
    一条臂要算**已验**，必须同时满足：主体侧真有部门、语料带非空标签、跨部门与跨密级都有
    选择性、并且它确实召回了东西 yet 零越权。少任何一条都是未验。
    """
    if arm.breaches > 0:
        return {"verdict": FAILED, "reason": REASON_BREACH, "arm": arm.name}
    if not arm.principal_departments:
        return {"verdict": UNVERIFIED, "reason": REASON_PRINCIPAL_UNSCOPED, "arm": arm.name}
    if arm.corpus_labelled_chunks == 0:
        return {"verdict": UNVERIFIED, "reason": REASON_NO_LABELLED_CHUNK, "arm": arm.name}
    if len(set(arm.corpus_departments)) < 2:
        return {"verdict": UNVERIFIED, "reason": REASON_NO_DEPARTMENT_SELECTIVITY, "arm": arm.name}
    if len(set(arm.corpus_classifications)) < 2:
        return {"verdict": UNVERIFIED, "reason": REASON_NO_CLASSIFICATION_SELECTIVITY, "arm": arm.name}
    if arm.recalled == 0:
        return {"verdict": UNVERIFIED, "reason": REASON_EMPTY_RETURN, "arm": arm.name}
    return {"verdict": VERIFIED, "reason": "标签非空、两轴都有选择性、召回非空且零越权", "arm": arm.name}


def naive_verdict(arm: ArmReading) -> dict:
    """那条会把假绿放过去的判法，写出来是为了让钉能咬：守卫一摘，红的就是这一格。"""
    return {"verdict": VERIFIED if arm.breaches == 0 else FAILED, "reason": "只看 breaches == 0"}


# ---------------------------------------------------------------------------
# 判据②：分桶。
# ---------------------------------------------------------------------------

#: 文件名词形 -> 部门提示。它**不是权威**，只是「这份文档在语义上像属于谁」的可核对量法：
#: 命中口径只有「文件名里出现该 token」。它用来回答「源头有、但没有结构化入口」那一段有多长。
DEPARTMENT_HINTS = {
    "财务": ("财务", "报销", "预算", "差旅", "增值税", "即征即退"),
    "人力资源": ("员工手册", "绩效", "入职", "离职", "考勤", "假期", "培训", "团建", "年会", "获奖"),
    "市场": ("市场", "品牌", "竞品", "投放", "SEM"),
    "销售": ("销售", "客户", "案例_", "话术", "会议纪要"),
    "研发": ("研发", "代码规范", "架构", "技术", "白皮书", "部署", "运维", "API", "CTO", "学习路线", "深度学习"),
    "法务": ("法务", "合同", "知识产权", "专利", "律师"),
    "信息安全": ("安全", "等保", "ISO27001", "数据保护", "灾备", "备份", "信息安全"),
    "行政": ("行政", "前台", "消防", "档案", "放假", "通知", "管理制度手册"),
    "采购供应链": ("采购", "供应商", "仓库", "供应链"),
    "审计": ("审计",),
    "经营层": ("经营分析", "年度经营", "预算方案"),
}


def hint_departments(filename: str) -> list:
    return sorted(dept for dept, tokens in DEPARTMENT_HINTS.items()
                  if any(token in filename for token in tokens))


def bucket_label_loss(catalog_rows: dict, vector_rows: dict) -> dict:
    """把「chunks 上丢了标签」分成四桶，全部按枚数计，不用文档数含糊过去。"""
    buckets = {
        "source_absent": {"files": 0, "chunks": 0},
        "source_present_not_propagated": {"files": 0, "chunks": 0},
        "propagated_but_wrong_column": {"files": 0, "chunks": 0},
        "propagated_and_consistent": {"files": 0, "chunks": 0},
    }
    for filename, vector in vector_rows.items():
        chunks = int(vector.get("chunks") or 0)
        catalog = catalog_rows.get(filename) or {}
        source_department = _norm(catalog.get("department"))
        stored_department = _norm(vector.get("department"))
        if not source_department:
            key = "source_absent"
        elif not stored_department:
            key = "source_present_not_propagated"
        elif source_department != stored_department:
            key = "propagated_but_wrong_column"
        else:
            key = "propagated_and_consistent"
        buckets[key]["files"] += 1
        buckets[key]["chunks"] += chunks
    return buckets


def _norm(value) -> str:
    return str(value or "").strip()


# ---------------------------------------------------------------------------
# 只读读数：PostgreSQL
# ---------------------------------------------------------------------------

PG_STATEMENTS = {
    "chunk_vectors": (
        "SELECT count(*) AS rows, "
        "count(*) FILTER (WHERE btrim(coalesce(department, '')) <> '') AS labelled, "
        "count(DISTINCT nullif(btrim(department), '')) AS distinct_departments, "
        "count(DISTINCT classification) AS distinct_classifications, "
        "count(*) FILTER (WHERE classification IS NULL) AS null_classifications, "
        "count(DISTINCT filename) AS files FROM chunk_vectors"
    ),
    "chunk_vectors_departments": (
        "SELECT coalesce(nullif(btrim(department), ''), '<EMPTY>') AS department, count(*) AS chunks "
        "FROM chunk_vectors GROUP BY 1 ORDER BY 2 DESC"
    ),
    "chunk_vectors_classifications": (
        "SELECT coalesce(classification::text, '<NULL>') AS classification, count(*) AS chunks "
        "FROM chunk_vectors GROUP BY 1 ORDER BY 2 DESC"
    ),
    "chunks_metadata": (
        "SELECT count(*) AS rows, "
        "count(*) FILTER (WHERE btrim(coalesce(metadata ->> 'department', '')) <> '') AS labelled, "
        "count(*) FILTER (WHERE coalesce(metadata ->> 'classification', '1') <> '1') AS nondefault "
        "FROM chunks"
    ),
    "documents": (
        "SELECT count(*) AS rows, "
        "count(*) FILTER (WHERE btrim(coalesce(department, '')) <> '') AS labelled, "
        "count(*) FILTER (WHERE coalesce(classification, 1) <> 1) AS nondefault FROM documents"
    ),
    "document_versions": (
        "SELECT count(*) AS rows, "
        "count(*) FILTER (WHERE btrim(coalesce(department, '')) <> '') AS labelled, "
        "count(*) FILTER (WHERE coalesce(classification, 1) <> 1) AS nondefault, "
        "count(*) FILTER (WHERE owner_id IS NULL) AS unowned FROM document_versions"
    ),
    "resource_versions": (
        "SELECT count(*) AS rows, "
        "count(*) FILTER (WHERE jsonb_array_length(coalesce(department_ids, '[]'::jsonb)) > 0) AS labelled "
        "FROM resource_versions WHERE resource_type = 'document'"
    ),
    "users": (
        "SELECT username, role, coalesce(nullif(btrim(department), ''), '<EMPTY>') AS department "
        "FROM users ORDER BY username"
    ),
    "catalog_departments": (
        "SELECT filename, coalesce(department, '') AS department, classification FROM documents"
    ),
    "vector_catalog": (
        "SELECT filename, max(coalesce(department, '')) AS department, "
        "max(classification) AS classification, count(*) AS chunks "
        "FROM chunk_vectors GROUP BY filename"
    ),
}


def read_postgres(url: str, expect_database: str) -> dict:
    """连上去、压只读、只发上面那些 SELECT，并且拒绝连错库。

    R390 只改「取连接」这一件事：本函数不再自带裸 ``psycopg.connect``，取连接改走
    ``app/db/connection.py`` 这枚唯一边界（政策写在 ``app/notifications/states.py`` 上方注释，
    尺子是 ``tests/test_r238_bare_connect_ratchet.py``，先例是 ``scripts/compare_vector_recall.py``）。
    三格未变：① 只读语义只强不弱 —— 先压 psycopg3 会话事务只读，再压
    ``default_transaction_read_only = on``，两道都在；② ``--expect-database`` 闸门原样；
    ③ stdout 字节形状原样 —— 取数语句、读数键名、打印语句一个字都没动。
    """
    settings = parse_database_settings(url)
    readings: dict = {}
    with open_connection(settings) as conn:
        conn.read_only = True  # psycopg3：会话事务只读，误写当场报错
        conn.execute("SET default_transaction_read_only = on")
        attached = conn.execute("SELECT current_database() AS database").fetchone()[0]
        readings["attached_database"] = attached
        if attached != expect_database:
            raise SystemExit(
                f"ABORT: 连上的是 {attached!r}，本件只按 {expect_database!r} 的口径读数。"
                "换库请显式带 --expect-database，不要把别人的库读成生产。"
            )
        for name, statement in PG_STATEMENTS.items():
            with conn.cursor() as cursor:
                cursor.execute(statement)
                columns = [column.name for column in cursor.description]
                readings[name] = [dict(zip(columns, row)) for row in cursor.fetchall()]
        readings["read_only_guard"] = conn.execute(
            "SHOW default_transaction_read_only"
        ).fetchone()[0]
    return readings


# ---------------------------------------------------------------------------
# 只读读数：遗留引擎（sqlite mode=ro，不走 chromadb 客户端）
# ---------------------------------------------------------------------------

CHROMA_STATEMENTS = {
    "embeddings": "SELECT count(*) AS rows FROM embeddings",
    "keys": "SELECT key, count(*) AS n FROM embedding_metadata GROUP BY key ORDER BY 2 DESC",
    "departments": (
        "SELECT coalesce(nullif(string_value, ''), '<EMPTY>') AS department, count(*) AS n "
        "FROM embedding_metadata WHERE key = 'department' GROUP BY 1 ORDER BY 2 DESC"
    ),
    "classifications": (
        "SELECT coalesce(string_value, CAST(int_value AS TEXT), '<NULL>') AS classification, count(*) AS n "
        "FROM embedding_metadata WHERE key = 'classification' GROUP BY 1 ORDER BY 2 DESC"
    ),
    "files": "SELECT count(DISTINCT string_value) AS files FROM embedding_metadata WHERE key = 'filename'",
    "labelled": (
        "SELECT count(*) AS labelled FROM embedding_metadata "
        "WHERE key = 'department' AND trim(coalesce(string_value, '')) <> ''"
    ),
}


def read_chroma_sqlite(path: str) -> dict:
    database = Path(path)
    readings: dict = {"chroma_sqlite": str(database), "present": database.exists()}
    if not database.exists():
        readings["skipped"] = "文件不在位"
        return readings
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        for name, statement in CHROMA_STATEMENTS.items():
            cursor = connection.execute(statement)
            columns = [column[0] for column in cursor.description]
            readings[name] = [dict(zip(columns, row)) for row in cursor.fetchall()]
        readings["query_only"] = connection.execute("PRAGMA query_only").fetchone()[0]
    finally:
        connection.close()
    return readings


#: 落盘名长什么样：上传那一格走 build_storage_path(DOCUMENTS_DIR, resource_id, extension)，
#: 所以 /app/documents 里是 32 位十六进制的 resource_id —— 显示文件名只活在目录账里。
#: 这一格不是修辞：它决定了「按文件名补部门」这条路只在 catalog 一侧可走，磁盘上不可走。
HEX_NAME = re.compile(r"^[0-9a-f]{32}\.[A-Za-z0-9]+$")


def scan_documents_dir(directory: str) -> dict:
    """磁盘侧的量：文件数、非文本数，以及有多少枚名字已被哈希掉（部门线索无从读起）。"""
    root = Path(directory)
    ledger = {"documents_dir": str(root), "present": root.is_dir(), "files": 0,
              "not_text": 0, "hashed_names": 0, "named_after_content": 0}
    if not root.is_dir():
        return ledger
    for entry in sorted(root.iterdir()):
        if not entry.is_file():
            continue
        ledger["files"] += 1
        if HEX_NAME.match(entry.name):
            ledger["hashed_names"] += 1
        else:
            ledger["named_after_content"] += 1
        if entry.suffix.lower() != ".txt":
            ledger["not_text"] += 1
    return ledger


def scan_name_hints(names, chunks_by_name=None) -> dict:
    """目录账侧的量：显示文件名里读得出部门提示的有多少枚（口径 = 文件名含该 token）。

    这是「语义上像属于某部门」的量法，不是权威：部门信息的权威只能是账号归属或人工标注。
    它存在的唯一理由，是把判据② 那句「源头就没有」说成一个数，而不是一句推断。
    """
    chunks_by_name = chunks_by_name or {}
    ledger = {"names": 0, "chunks": 0, "no_hint_files": 0, "no_hint_chunks": 0,
              "unique_hint_files": 0, "unique_hint_chunks": 0,
              "ambiguous_hint_files": 0, "ambiguous_hint_chunks": 0,
              "by_department": {}, "by_department_chunks": {}, "hint_files": {}}
    for name in sorted(set(names)):
        chunks = int(chunks_by_name.get(name) or 0)
        ledger["names"] += 1
        ledger["chunks"] += chunks
        hits = hint_departments(name)
        if not hits:
            ledger["no_hint_files"] += 1
            ledger["no_hint_chunks"] += chunks
            continue
        if len(hits) == 1:
            ledger["unique_hint_files"] += 1
            ledger["unique_hint_chunks"] += chunks
        else:
            ledger["ambiguous_hint_files"] += 1
            ledger["ambiguous_hint_chunks"] += chunks
        for dept in hits:
            ledger["by_department"][dept] = ledger["by_department"].get(dept, 0) + 1
            ledger["by_department_chunks"][dept] = (
                ledger["by_department_chunks"].get(dept, 0) + int(chunks_by_name.get(name) or 0))
            ledger["hint_files"].setdefault(dept, []).append(name)
    ledger["by_department"] = dict(sorted(ledger["by_department"].items()))
    ledger["by_department_chunks"] = dict(sorted(ledger["by_department_chunks"].items()))
    return ledger


def build_arm_readings(postgres: dict) -> dict:
    """把库里的实际标签分布折成一条臂，交给 classify_arm。

    这不是「模拟一条臂」，而是回答一个更硬的问题：今天这台机器上能不能凑出一条**能判**的臂。
    语料侧的数从 chunk_vectors 现取，主体侧取 users 里唯一那些带部门的账号。
    """
    vectors = (postgres.get("chunk_vectors") or [{}])[0]
    departments = tuple(row["department"] for row in (postgres.get("chunk_vectors_departments") or [])
                        if row["department"] != "<EMPTY>")
    classifications = tuple(row["classification"] for row in (postgres.get("chunk_vectors_classifications") or [])
                             if row["classification"] != "<NULL>")
    scoped = [row["username"] for row in (postgres.get("users") or []) if row["department"] != "<EMPTY>"]
    arm = ArmReading(
        name="production-department-leg",
        principal_departments=tuple(row["department"] for row in (postgres.get("users") or [])
                                    if row["department"] != "<EMPTY>"),
        principal_clearance=1,
        corpus_labelled_chunks=int(vectors.get("labelled") or 0),
        corpus_departments=departments,
        corpus_classifications=classifications,
        recalled=int(vectors.get("rows") or 0),
        breaches=0,
        metadata={
            "corpus_rows": vectors.get("rows"),
            "scoped_accounts": scoped,
            "measured_on": "chunk_vectors 现读",
        },
    )
    return {"arm": arm.as_dict(), "verdict": classify_arm(arm), "naive_verdict": naive_verdict(arm)}


def build_ledger(postgres: dict, chroma: dict, documents: dict) -> dict:
    catalog_rows = {row["filename"]: {"department": row["department"],
                                      "classification": row["classification"]}
                    for row in (postgres.get("catalog_departments") or [])}
    vector_rows = {row["filename"]: {"department": row["department"],
                                     "classification": row["classification"],
                                     "chunks": row["chunks"]}
                   for row in (postgres.get("vector_catalog") or [])}
    buckets = bucket_label_loss(catalog_rows, vector_rows)
    chunks_by_name = {name: int(row.get("chunks") or 0) for name, row in vector_rows.items()}
    display_names = sorted(set(list(catalog_rows) + list(chunks_by_name)))
    buckets["name_hint_ledger"] = scan_name_hints(display_names, chunks_by_name)
    buckets["disk_ledger"] = documents
    return {
        "lineage": LINEAGE_HOPS,
        "first_truth_lost_at": FIRST_TRUTH_LOST_AT,
        "real_break_point_at": REAL_BREAK_POINT_AT,
        "postgres": postgres,
        "legacy_engine": chroma,
        "buckets": buckets,
        "acceptance_c": build_arm_readings(postgres),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="R387 标签血缘取证（只读）")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--expect-database", default="enterprise_brain")
    parser.add_argument("--chroma-sqlite", default=os.getenv("R387_CHROMA_SQLITE", ""))
    parser.add_argument("--documents-dir", default=os.getenv("R387_DOCUMENTS_DIR", "documents"))
    parser.add_argument("--no-db", action="store_true", help="只出规则、血缘与目录量法，一条 SQL 都不发")
    parser.add_argument("--json", dest="out", default="")
    parser.add_argument("--emit-doc-cells", action="store_true",
                        help="把文档 §1 血缘表那一格的现读结果按「序号<TAB>格」打出来（行号是派生的，表不许手改）")
    args = parser.parse_args(argv)

    if args.emit_doc_cells:
        for seq in sorted(LINEAGE_DOC_CELLS):
            print("%d\t%s" % (seq, LINEAGE_DOC_CELLS[seq]))
        for item in LINEAGE_ANCHOR_FAILURES:
            print("ABORT: 锚不再是唯一锚 -> " + item, file=sys.stderr)
        return 3 if LINEAGE_ANCHOR_FAILURES else 0

    if LINEAGE_ANCHOR_FAILURES:
        print("ABORT: 血缘锚不再是唯一锚，行号派生不出来（带着腐锚出账＝把假行号交给下游）：", file=sys.stderr)
        for item in LINEAGE_ANCHOR_FAILURES:
            print("  - " + item, file=sys.stderr)
        return 3

    if args.no_db:
        postgres = {"skipped": "--no-db"}
    else:
        if not args.database_url:
            print("ABORT: 没有 DATABASE_URL，且没带 --no-db。不发一条猜测性的连接。", file=sys.stderr)
            return 2
        postgres = read_postgres(args.database_url, args.expect_database)

    chroma = read_chroma_sqlite(args.chroma_sqlite) if args.chroma_sqlite else {"skipped": "没带 --chroma-sqlite"}
    documents = scan_documents_dir(args.documents_dir)
    ledger = build_ledger(postgres, chroma, documents)

    payload = json.dumps(ledger, ensure_ascii=False, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    verdict = ledger["acceptance_c"]["verdict"]
    print(f"验收 C 部门腿判词：{verdict['verdict']} —— {verdict['reason']}")
    print(f"同一份读数在朴素判法下会得出：{ledger['acceptance_c']['naive_verdict']['verdict']}"
          f"（这正是那一格假绿的成因）")
    if args.out:
        print(f"ledger -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
