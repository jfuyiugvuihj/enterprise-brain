#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R160 只读普查：无部门列的表到底有多少、翻成 fail-closed（乙）会打死谁。

只读契约（本脚本自身可验证，逐条打印实际发出的语句/命令）：
  * SQLite   sqlite3.connect("file:...?mode=ro", uri=True) + PRAGMA query_only=ON，只发 SELECT。
  * Postgres 只经 docker exec psql，每条语句前置 SET default_transaction_read_only = on，只发 SELECT。
  * 容器内文件 只经 docker exec 的 ls / cat（读语义），不落盘、不改权限、不创建。
  * 主机文件   只以 rb 方式读，全程不写、不改、不删、不建临时文件。
  * 不联网、不起服务、不跑模型、不跑 pytest、不碰 chroma_db/。

判定口径来源：app/common/rbac.py 里的 ROW_DEPARTMENT_COLUMNS / ROW_CLASSIFICATION_COLUMNS，
本脚本在运行时从那枚文件里解析，绝不自带一份副本，避免普查口径和产品口径漂移。

退出码：0 = 所有登记到的数据源都读到了；3 = 有读不到的（已逐枚指名，不当成“没有”）。
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

DEPT_SOURCE_NAME = "ROW_DEPARTMENT_COLUMNS"
CLASS_SOURCE_NAME = "ROW_CLASSIFICATION_COLUMNS"
TABULAR_SUFFIXES = (".csv", ".xlsx", ".xls")
OOMAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
OOREL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKGREL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

# 敏感字段词典：命中即进 P1 候选。分类名给人看，正则给机器用。
SENSITIVE_PATTERNS = (
    ("薪酬", r"薪资|工资|薪|报酬|提成|奖金|绩效|salary|payroll|wage|bonus|compensation", True),
    ("个人身份", r"身份证|证件号|护照|社保|公积金|id_?card|identity|ssn|tax_?id", True),
    ("联系方式", r"手机号|电话|联系方式|传真|邮箱|email|mail|phone|mobile|tel\b", True),
    ("账户与银行", r"银行卡|开户行|账号|账户|iban|bank_?account|routing", True),
    ("家庭住址", r"住址|地址|户籍|address", False),
    ("合同与金额", r"合同|协议金额|价款|金额|总价|付款|invoice|amount|contract|price", True),
    ("客户与供应商名单", r"客户|供应商|甲方|乙方|经销商|customer|client|vendor|supplier", True),
    ("人员名册", r"姓名|员工|花名册|入职|离职|工号|employee|staff_?name", True),
    ("报销", r"报销|费用明细|reimburse|expense", True),
    ("经营指标", r"营收|营业额|利润|毛利|流水|客单价|客流量|revenue|profit|turnover|gmv", True),
    ("健康", r"体检|病历|健康|diagnosis|medical", True),
)

READ_ONLY_SQL_PREFIX = "SET default_transaction_read_only = on"


@dataclass
class Item:
    """一格被普查到的表/文件。"""

    source: str
    ident: str
    provenance: str
    row_rbac: bool
    columns: list = field(default_factory=list)
    rows: object = None
    detail: str = ""
    error: str = ""
    consumers: list = field(default_factory=list)
    def add_error(self, message: str) -> None:
        self.error = message if not self.error else f"{self.error} / {message}"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_rbac_candidates(repo_root: Path) -> tuple:
    """从产品源码里现取部门列/密级列候选名，并带回行号（散文里的行号也是数字）。"""
    path = repo_root / "app" / "common" / "rbac.py"
    if not path.is_file():
        raise SystemExit(f"中止：找不到判定源文件 {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    found = {}
    for name in (DEPT_SOURCE_NAME, CLASS_SOURCE_NAME):
        hit = None
        for number, line in enumerate(lines, start=1):
            if re.match(rf"^{name}\s*=", line):
                hit = (number, line)
                break
        if hit is None:
            raise SystemExit(f"中止：{path}:{1} 里找不到 {name}，普查不能凭记忆跑")
        values = [v for v in re.findall(r'"([^"]+)"', hit[1])]
        if not values:
            raise SystemExit(f"中止：{path}:{hit[0]} 的 {name} 解析不出候选名，原文：{hit[1].strip()}")
        found[name] = (tuple(values), hit[0])
    marker = [n for n, line in enumerate(lines, start=1) if "department_column_missing" in line]
    return (
        found[DEPT_SOURCE_NAME][0],
        found[CLASS_SOURCE_NAME][0],
        {"dept_line": found[DEPT_SOURCE_NAME][1], "class_line": found[CLASS_SOURCE_NAME][1],
         "missing_branch_lines": marker, "file": str(path)},
    )


def match_columns(columns: list, candidates: tuple) -> str | None:
    """口径与 rbac.py 一致：只看列名里是否出现候选名（:146/:152 用的是 `col in df.columns`）。"""
    names = [str(c) for c in columns]
    for candidate in candidates:
        if candidate in names:
            return candidate
    return None


def sensitive_hits(columns: list) -> list:
    hits = []
    for column in columns:
        text = str(column).lower()
        for label, pattern, p1 in SENSITIVE_PATTERNS:
            if re.search(pattern, text):
                hits.append((label, str(column), p1))
    return hits


def is_testy(text: str) -> bool:
    return bool(re.search(r"e2e|test|fixture|sample|demo|示例|测试|样例|样本|r58|acceptance|mock", str(text), re.I))


def build_tracked_set(repo_root: Path) -> set:
    """用 git ls-files 划“仓内跟踪”边界（跟踪 = 样本/测试带上去的，不是客户上传的）。"""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=str(repo_root), capture_output=True, timeout=60
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[警告] git ls-files 失败，样本/客户分界退化为按名字判断：{type(exc).__name__}: {exc}")
        return set()
    if out.returncode != 0:
        print(f"[警告] git ls-files 返回码 {out.returncode}，分界退化为按名字判断")
        return set()
    return {p.decode("utf-8", "replace") for p in out.stdout.split(b"\x00") if p}

def decode_text(raw: bytes) -> tuple:
    """按 load_excel -> read_csv 的语义近似：先试常用中文编码，全失败才报错，绝不静默。"""
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030", "cp936", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV 编码无法识别（试过 utf-8-sig/utf-8/gbk/gb18030/cp936/latin-1）")


def read_csv_blob(raw: bytes) -> tuple:
    text, enc = decode_text(raw)
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return [], 0, f"encoding={enc} 空文件"
    header = [h.strip() for h in rows[0]]
    body = [r for r in rows[1:] if any(str(cell).strip() for cell in r)]
    return header, len(body), f"encoding={enc} 原始行={len(rows)}"


def col_letter_to_index(letters: str) -> int:
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - 64)
    return value - 1


def shared_strings(zf: zipfile.ZipFile) -> list:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    out = []
    with zf.open("xl/sharedStrings.xml") as handle:
        for _event, elem in ET.iterparse(handle, events=("end",)):
            if elem.tag == f"{OOMAIN}si":
                out.append("".join(t.text or "" for t in elem.iter(f"{OOMAIN}t")))
                elem.clear()
    return out


_DEPT_CANDIDATES: tuple = ()


def configure_terms(dept_cols: tuple, class_cols: tuple) -> None:
    """把从 rbac.py 现取到的候选名注进模块，供 xlsx 逐表判定用（不自带副本）。"""
    global _DEPT_CANDIDATES
    _DEPT_CANDIDATES = dept_cols


def parse_sheet(zf: zipfile.ZipFile, sheet_path: str, name: str, strings: list) -> dict:
    header: list = []
    body_rows = 0
    merged = False
    with zf.open(sheet_path) as handle:
        for _event, elem in ET.iterparse(handle, events=("end",)):
            if elem.tag == f"{OOMAIN}mergeCells":
                merged = True
                elem.clear()
                continue
            if elem.tag != f"{OOMAIN}row":
                continue
            cells = {}
            for cell in elem.iter(f"{OOMAIN}c"):
                ref = cell.get("r") or ""
                letters = re.match(r"([A-Z]+)", ref)
                idx = col_letter_to_index(letters.group(1)) if letters else len(cells)
                kind = cell.get("t")
                value = ""
                if kind == "inlineStr":
                    value = "".join(t.text or "" for t in cell.iter(f"{OOMAIN}t"))
                else:
                    node = cell.find(f"{OOMAIN}v")
                    if node is not None and node.text is not None:
                        value = strings[int(node.text)] if kind == "s" else node.text
                cells[idx] = str(value).strip()
            elem.clear()
            if not header:
                if not any(cells.values()):
                    continue
                width = max(cells) + 1 if cells else 0
                header = [cells.get(i, "") for i in range(width)]
                continue
            if any(cells.values()):
                body_rows += 1
    return {
        "name": name,
        "header": header,
        "rows": body_rows,
        "merged": merged,
        "dept": match_columns(header, _DEPT_CANDIDATES),
    }


def read_xlsx_blob(raw: bytes) -> tuple:
    """复现 load_excel 到底读哪张表：app/tools/excel.py:44 先看 wb.active 有无合并单元格，
    有合并走活动表，无合并回落到 :87 pd.read_excel ⇒ 第一张表。每张表都算，被读的那张写清楚。
    """
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        sheets = []
        for node in wb.iter(f"{OOMAIN}sheet"):
            sheets.append(
                {
                    "name": node.get("name"),
                    "rid": node.get(f"{OOREL}id"),
                    "state": node.get("state") or "visible",
                }
            )
        active = 0
        view = wb.find(f"{OOMAIN}bookViews/{OOMAIN}workbookView")
        if view is not None and view.get("activeTab") is not None:
            active = int(view.get("activeTab"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        path_map = {r.get("Id"): r.get("Target") for r in rels.iter(f"{PKGREL}Relationship")}
        visible = [s for s in sheets if s["state"] == "visible"] or sheets
        strings = shared_strings(zf)
        fallback = sorted(n for n in zf.namelist() if n.startswith("xl/worksheets/sheet"))
        parsed = []
        for position, sheet in enumerate(visible):
            rel_target = path_map.get(sheet["rid"], "").lstrip("/")
            rel_target = rel_target[3:] if rel_target.startswith("xl/") else rel_target
            sheet_path = ("xl/" + rel_target.removeprefix("./")) if rel_target else ""
            if sheet_path not in zf.namelist():
                if not fallback:
                    raise ValueError("xlsx 里找不到工作表 XML")
                sheet_path = fallback[min(position, len(fallback) - 1)]
            parsed.append(parse_sheet(zf, sheet_path, sheet["name"], strings))
    act = parsed[min(active, len(parsed) - 1)]
    if act["merged"]:
        chosen, why = act, "活动表：有合并单元格，走 _fill_merged_cells"
    else:
        chosen, why = parsed[0], "第一张表：活动表无合并单元格，回落 pd.read_excel"
    summary = " ".join(
        f"{p['name']}[行={p['rows']} 列={len(p['header'])} 部门列={p['dept'] or '无'}]" for p in parsed
    )
    return chosen["header"], chosen["rows"], f"app实读={chosen['name']}（{why}）｜各表：{summary}"


def read_tabular_blob(raw: bytes, suffix: str) -> tuple:
    if suffix == ".csv":
        return read_csv_blob(raw)
    if suffix == ".xlsx":
        return read_xlsx_blob(raw)
    raise ValueError(".xls 是二进制老格式，本脚本只用 stdlib，需 openpyxl/xlrd 之外的人工通道复核")


def run_command(argv: list, binary_stdout: bool = False, timeout: int = 120) -> tuple:
    """唯一的对外执行出口：打印原命令，返回 (returncode, stdout, stderr)。"""
    printable = " ".join(str(a) for a in argv)
    _CMD_LOG.append(printable)
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return 127, b"", f"{type(exc).__name__}: {exc}".encode("utf-8")
    if binary_stdout:
        return proc.returncode, proc.stdout, proc.stderr
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", "replace"),
        proc.stderr.decode("utf-8", "replace"),
    )


_CMD_LOG: list = []


def psql_readonly(docker_bin: str, container: str, user: str, db: str, sql: str) -> tuple:
    """只读 psql：会话先 default_transaction_read_only = on，再发 SELECT。"""
    argv = [
        docker_bin, "exec", container, "psql", "-U", user, "-d", db, "-At",
        "-v", "ON_ERROR_STOP=1", "-c", READ_ONLY_SQL_PREFIX, "-c", sql,
    ]
    code, out, err = run_command(argv)
    return code, out, err


PG_COLUMNS_SQL = (
    "SELECT table_schema||'.'||table_name||'|'||column_name||'|'||data_type "
    "FROM information_schema.columns "
    "WHERE table_schema NOT IN ('pg_catalog','information_schema') AND table_schema NOT LIKE 'pg!_%' "
    "ORDER BY 1"
)
PG_TABLES_SQL = (
    "SELECT table_schema||'.'||table_name||'|'||table_type "
    "FROM information_schema.tables "
    "WHERE table_schema NOT IN ('pg_catalog','information_schema') AND table_schema NOT LIKE 'pg!_%' "
    "ORDER BY 1"
)


def pg_count_sql(tables: list) -> str:
    parts = [
        "SELECT '" + t.replace("'", "''") + "' AS tbl, count(*) AS n FROM " + ".".join(
            '"' + p + '"' for p in t.split(".")
        )
        for t in tables
    ]
    return " UNION ALL ".join(parts)


def audit_postgres(args, tables: list) -> tuple:
    """返回 (每表列名字典, 行数字典, 错误列表)。"""
    errors: list = []
    columns: dict = {}
    counts: dict = {}
    code, out, err = psql_readonly(args.docker_bin, args.pg_container, args.pg_user, args.pg_db, PG_COLUMNS_SQL)
    if code != 0:
        errors.append(f"PostgreSQL 列目录读取失败：{err.strip() or out.strip() or f'返回码 {code}'}")
        return columns, counts, errors
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 2:
            if line.strip() == "SET":  # psql 回显 -c SET 的结果行，不是数据行
                continue
            errors.append(f"PostgreSQL 列目录行格式异常，已指名跳过：{line!r}")
            continue
        columns.setdefault(parts[0], []).append(parts[1])
    names = sorted(columns)
    if names:
        code, out, err = psql_readonly(args.docker_bin, args.pg_container, args.pg_user, args.pg_db, pg_count_sql(names))
        if code != 0:
            errors.append(f"PostgreSQL 行数统计失败（列目录仍可用）：{err.strip() or f'返回码 {code}'}")
        else:
            for line in out.splitlines():
                if "|" not in line:
                    continue
                tbl, _, n = line.rpartition("|")
                counts[tbl.strip()] = n.strip()
    return columns, counts, errors

def uri_ro(path: Path) -> str:
    return "file:" + path.as_posix() + "?mode=ro"


def audit_sqlite(path: Path) -> tuple:
    """只读打开一枚 SQLite 库，返回 (表->列名, 表->行数, 备注, 错误)。"""
    columns: dict = {}
    counts: dict = {}
    notes: list = []
    errors: list = []
    sidecars = [p.name for p in path.parent.glob(path.name + "-*") if p.is_file()]
    if sidecars:
        notes.append(f"存在附属文件 {sidecars}：只读模式下 WAL 帧可能未合并，行数可能偏小")
    try:
        con = sqlite3.connect(uri_ro(path), uri=True)
    except Exception as exc:  # noqa: BLE001
        return columns, counts, notes, [f"只读打开失败 {type(exc).__name__}: {exc}"]
    try:
        con.execute("PRAGMA query_only=ON")
        mode = con.execute("PRAGMA query_only").fetchone()
        if not mode or str(mode[0]) not in ("1", "on"):
            errors.append("PRAGMA query_only 未能置位，拒绝继续（只读保证不成立）")
            return columns, counts, notes, errors
        objects = con.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        for kind, name in objects:
            key = f"{name}" if kind == "table" else f"{name}({kind})"
            try:
                cols = [r[1] for r in con.execute(f'PRAGMA table_info("{name}")').fetchall()]
                columns[key] = cols
                if kind == "table":
                    counts[key] = str(con.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0])
                else:
                    counts[key] = "视图未计行数"
            except Exception as exc:  # noqa: BLE001
                columns.setdefault(key, [])
                counts[key] = "读不到"
                errors.append(f"表 {key} 读取失败 {type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"SQLite 目录查询失败 {type(exc).__name__}: {exc}")
    finally:
        con.close()
    return columns, counts, notes, errors


def host_file_bytes(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read()


def container_file_bytes(docker_bin: str, container: str, remote: str) -> bytes:
    code, out, err = run_command(
        [docker_bin, "exec", container, "cat", remote], binary_stdout=True
    )
    if code != 0:
        raise RuntimeError(f"docker exec cat 失败({code}): {err.decode('utf-8', 'replace').strip()}")
    return out


def container_listing(docker_bin: str, container: str, remote_dir: str) -> tuple:
    code, out, err = run_command(
        [docker_bin, "exec", container, "sh", "-c", f"ls -1 {remote_dir} 2>/dev/null || true"]
    )
    if code != 0:
        raise RuntimeError(f"docker exec ls 失败({code}): {err.strip()}")
    return [l for l in out.splitlines() if l.strip()]


def build_code_index(repo_root: Path, tracked: set) -> list:
    """把仓内代码/SQL/迁移按行拆开，用于回答“谁在查这张表”。普查脚本自己不进索引。"""
    index = []
    exts = (".py", ".sql", ".sh", ".vue", ".ts", ".js", ".json")
    for rel in sorted(tracked):
        if rel.startswith("scripts/audit_r160"):
            continue
        if not rel.endswith(exts):
            continue
        if rel.startswith("frontend/") or "/node_modules/" in rel:
            continue
        try:
            text = (repo_root / rel).read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if len(line) > 400:
                continue
            index.append((rel, number, line))
    return index


def find_consumers(index: list, token: str, limit: int = 6) -> list:
    if not token:
        return []
    pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(token) + r"(?![A-Za-z0-9_])")
    hits = []
    for rel, number, line in index:
        if pattern.search(line):
            hits.append(f"{rel}:{number}")
            if len(hits) >= limit:
                break
    return hits

PG_USERS_SQL = (
    "SELECT username||'|'||role||'|'||COALESCE(NULLIF(department,''),'<无部门>') "
    "FROM public.users ORDER BY 1"
)
PG_DATASETS_SQL = (
    "SELECT dataset_id||'|'||owner_id||'|'||filename||'|'||status||'|'||classification||'|'||storage_key "
    "FROM public.datasets ORDER BY created_at"
)
PG_DOC_TABULAR_SQL = (
    "SELECT filename||'|'||version::text||'|'||COALESCE(classification::text,'')||'|'||COALESCE(department,'<无部门>') "
    "FROM public.document_versions WHERE lower(filename) ~ '\\.(csv|xlsx|xls)$' ORDER BY filename"
)
SQLITE_APP_TABLES = (
    "sessions", "session_messages", "users", "checkpoints", "writes",
)


def provenance_of(path_text: str, rel: str | None, tracked: set, in_container: bool, testy: bool) -> str:
    """归类：客户真数据 = 走上传口进现网 DATA_DIR 的落地产物；仓内跟踪算样本；主机未跟踪单列。"""
    if rel is not None and rel in tracked:
        return "仓内样本/测试（git 跟踪）"
    if testy:
        return "样本(容器)" if in_container else "样本(主机)"
    return "客户真数据(现网容器)" if in_container else "主机现场未跟踪文件"


def is_customer(item) -> bool:
    return item.provenance.startswith("客户真数据")


def is_host_untracked(item) -> bool:
    return item.provenance.startswith("主机现场未跟踪文件")
def load_json_registry(label: str, loader) -> tuple:
    try:
        raw = loader()
        payload = json.loads(raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw)
    except Exception as exc:  # noqa: BLE001
        return None, f"{label} 读取失败 {type(exc).__name__}: {exc}"
    records = payload.get("datasets") or payload.get("documents") or []
    return records, ""


def collect_items(args, repo_root: Path, tracked: set, dept_cols: tuple, class_cols: tuple, extras: dict) -> tuple:
    items: list = []
    notes: list = []
    failures: list = []
    code_index = build_code_index(repo_root, tracked)
    dataset_names: dict = {}
    extras["load_calls"] = [(rel, num) for rel, num, line in code_index if "load_excel(" in line]
    extras["rbac_files"] = sorted({rel for rel, _n, line in code_index if "filter_dataframe_rows" in line})

    # --- 1) 登记面：数据集清单（主机 JSON + 容器 JSON + PG datasets） -----------------
    registry_files = []
    for root in args.scan_dir:
        for name in (".dataset-metadata.json", ".document-versions.json"):
            candidate = Path(root) / name
            if candidate.is_file():
                registry_files.append(("主机", str(candidate), candidate))
    if not args.skip_container:
        registry_files.append(
            ("容器", f"{args.be_container}:{args.be_data_dir}/.dataset-metadata.json", None)
        )
    for origin, display, candidate in registry_files:
        if candidate is not None:
            records, err = load_json_registry(display, lambda c=candidate: host_file_bytes(c))
        else:
            records, err = load_json_registry(
                display,
                lambda: container_file_bytes(
                    args.docker_bin, args.be_container, f"{args.be_data_dir}/.dataset-metadata.json"
                ),
            )
        if err:
            failures.append(f"登记面 {display}：{err}")
            continue
        for record in records:
            filename = record.get("filename") or ""
            if not filename:
                continue
            dataset_names[Path(str(record.get("storage_path") or filename)).name] = record
        notes.append(f"登记面 {display} 读到 {len(records)} 条记录（origin={origin}）")

    if not args.skip_postgres:
        code, out, err = psql_readonly(args.docker_bin, args.pg_container, args.pg_user, args.pg_db, PG_DATASETS_SQL)
        if code != 0:
            failures.append(f"登记面 PG public.datasets：{err.strip() or f'返回码 {code}'}")
        else:
            for line in out.splitlines():
                parts = line.split("|")
                if len(parts) < 6:
                    continue
                dataset_id, owner, filename, status, classification, storage_key = parts[:6]
                dataset_names[Path(filename).name] = {
                    "dataset_id": dataset_id,
                    "owner_id": owner,
                    "filename": filename,
                    "status": status,
                    "classification": classification,
                    "storage_path": storage_key,
                }
            notes.append("登记面 PG public.datasets 已并入")

    # --- 1b) 文档清单登记面：app/documents/catalog.py:28 .document-versions.json -------
    catalogs = [(str(Path(root) / ".document-versions.json"), "主机") for root in args.scan_dir]
    if not args.skip_container:
        catalogs.append((f"{args.be_documents_dir}/.document-versions.json", "容器"))
    for display, kind in catalogs:
        try:
            if kind == "容器":
                raw = container_file_bytes(args.docker_bin, args.be_container, display)
            else:
                candidate = Path(display)
                if not candidate.is_file():
                    notes.append(f"文档清单 {display} 不存在（该目录没有本地清单，不等于没有登记）")
                    continue
                raw = host_file_bytes(candidate)
            payload = json.loads(raw.decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001
            failures.append(f"文档清单 {display} 读取失败：{type(exc).__name__}: {exc}")
            continue
        docs = payload.get("documents") or {}
        for key, meta in docs.items():
            extras.setdefault("doc_catalog", []).append(
                {
                    "catalog": display,
                    "origin": kind,
                    "key": key,
                    "filename": str(meta.get("filename") or ""),
                    "department": str(meta.get("department") or ""),
                    "classification": meta.get("classification"),
                }
            )
        notes.append(f"文档清单 {display}（{kind}）读到 {len(docs)} 条登记")
    # --- 2) 表类文件：主机目录 + 容器目录 -------------------------------------------
    file_targets: list = []
    for root in args.scan_dir:
        base = Path(root)
        if not base.is_dir():
            failures.append(f"目录不存在，无法普查：{base}")
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix.lower() in TABULAR_SUFFIXES:
                file_targets.append(("主机", str(path), path, base))
    for shallow in args.shallow_dir:
        base = Path(shallow)
        if not base.is_dir():
            failures.append(f"浅层目录不存在，无法普查：{base}")
            continue
        for path in sorted(base.iterdir()):
            if path.is_file() and path.suffix.lower() in TABULAR_SUFFIXES:
                file_targets.append(("主机", str(path), path, base))
    for loose in args.file:
        target = Path(loose)
        if target.is_file():
            file_targets.append(("主机", str(target), target, target.parent))
        else:
            failures.append(f"指名文件不存在，无法普查：{target}")
    if not args.skip_container:
        for remote in (args.be_data_dir, args.be_documents_dir):
            try:
                listing = container_listing(args.docker_bin, args.be_container, remote)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"容器目录 {remote} 列举失败：{exc}")
                continue
            for name in listing:
                if Path(name).suffix.lower() in TABULAR_SUFFIXES:
                    file_targets.append(("容器", f"{remote}/{name}", None, remote))
        notes.append("容器目录已按 ls -1 枚举（只读）")

    seen_files: set = set()
    for origin, display, path, base in file_targets:
        if display in seen_files:
            continue
        seen_files.add(display)
        suffix = Path(display).suffix.lower()
        name = Path(display).name
        try:
            raw = host_file_bytes(path) if origin == "主机" else container_file_bytes(
                args.docker_bin, args.be_container, display
            )
            header, nrows, detail = read_tabular_blob(raw, suffix)
        except Exception as exc:  # noqa: BLE001
            items.append(Item("table-file", display, "", True, error=f"{type(exc).__name__}: {exc}"))
            failures.append(f"表文件读不出来：{display}（{type(exc).__name__}: {exc}）")
            continue
        rel = None
        if origin == "主机":
            try:
                rel = str(Path(display).resolve().relative_to(repo_root)).replace("\\", "/")
            except Exception:  # noqa: BLE001
                rel = None
        record = dataset_names.get(name)
        stored = str((record or {}).get("storage_path") or "").replace("\\", "/")
        same_path = bool(record) and stored == display.replace("\\", "/")
        in_documents = "documents" in Path(display).parent.name.lower() or "documents" in display.lower()
        prov = provenance_of(display, rel, tracked, origin == "容器", is_testy(name) or is_testy(display))
        reachable = bool(record) and same_path and str(record.get("status", "")) == "active"
        plane = "数据集面（app/agents/tools.py:_authorized_dataset_files -> filter_dataframe_rows）"
        reg_kind = "否" if record is None else ("按路径命中" if same_path else "仅同名(路径不同)")
        if in_documents:
            plane = "知识库文档面（app/documents/catalog.py，不落 filter_dataframe_rows）"
        mtime = "-"
        if origin == "主机":
            mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        item = Item(
            source="table-file",
            ident=display,
            provenance=prov if record is None or not in_documents else f"{prov}｜文档登记",
            row_rbac=not in_documents,
            columns=header,
            rows=nrows,
            detail=(
                f"{detail}｜origin={origin}｜mtime={mtime}｜登记={reg_kind}"
                f"｜状态={(record or {}).get('status', '-') if record else '-'}"
                f"｜密级={(record or {}).get('classification', '-') if record else '-'}"
                f"｜owner={(record or {}).get('owner_id', '-') if record else '-'}"
                f"｜今日可查={('是' if reachable else '否')}"
                f"｜判定路径={plane}"
            ),
            consumers=find_consumers(code_index, Path(name).stem),
        )
        items.append(item)
    return items, notes, failures, code_index

def collect_db_items(args, repo_root: Path, tracked: set, code_index: list) -> tuple:
    """SQLite 与 PostgreSQL 两侧：应用元数据库的表，不是客户业务表，必须标清楚。"""
    items: list = []
    notes: list = []
    failures: list = []
    extras: dict = {}

    db_files = list(args.sqlite_file)
    if not args.skip_sqlite:
        for root in args.scan_dir:
            base = Path(root)
            if base.is_dir():
                db_files += [str(p) for p in sorted(base.rglob("*.db"))]
    seen = set()
    for raw_path in db_files:
        path = Path(raw_path)
        if str(path) in seen:
            continue
        seen.add(str(path))
        if not path.is_file():
            failures.append(f"SQLite 库不存在：{path}")
            continue
        columns, counts, db_notes, errors = audit_sqlite(path)
        for note in db_notes:
            notes.append(f"{path.name}: {note}")
        for err in errors:
            failures.append(f"{path}: {err}")
        if not columns:
            failures.append(f"{path}: 一枚表都没读到，不能当成“没有表”")
        for table in sorted(columns):
            bare = table.split("(")[0]
            app_metadata = bare in SQLITE_APP_TABLES or bare in {
                "schema_migrations", "documents", "document_versions", "datasets",
                "alerts", "alert_rules", "artifacts", "audit_events", "sessions",
            }
            items.append(
                Item(
                    source="sqlite",
                    ident=f"{path}::{table}",
                    provenance="应用元数据(遗留 SQLite)" if app_metadata else "待归类(SQLite 对象)",
                    row_rbac=False,
                    columns=columns[table],
                    rows=counts.get(table, "读不到"),
                    detail="SQLite 不经 filter_dataframe_rows；仓内无引用则应用读不到它",
                    consumers=find_consumers(code_index, bare),
                )
            )
        notes.append(f"SQLite {path} 读到 {len(columns)} 个对象（只读 URI + query_only）")

    if args.skip_postgres:
        return items, notes, failures, extras

    pg_columns, pg_counts, pg_errors = audit_postgres(args, [])
    for err in pg_errors:
        failures.append(err)
    if not pg_columns:
        failures.append("PostgreSQL: 一枚表都没读到，不能当成“没有表”")
    business = re.compile(r"业务|biz|sales|finance|hr|salary|order|invoice|employee|门店|交易")
    for table in sorted(pg_columns):
        bare = table.split(".")[-1]
        extras.setdefault(table, None)
        is_dataset_meta = bare in ("datasets", "dataset_versions")
        items.append(
            Item(
                source="postgres",
                ident=table,
                provenance="应用元数据(PostgreSQL)"
                + ("｜数据集登记表" if is_dataset_meta else "")
                + ("｜疑似业务表需人工归类" if business.search(bare) else ""),
                row_rbac=False,
                columns=pg_columns[table],
                rows=pg_counts.get(table, "读不到"),
                detail="PG 表由 app 侧 SQL/策略闸门服务，不经 pandas 行级过滤器；"
                       "仓内无 read_sql/to_sql（已 rg 验证），故不会进 filter_dataframe_rows",
                consumers=find_consumers(code_index, bare),
            )
        )
    notes.append(f"PostgreSQL 读到 {len(pg_columns)} 张用户表（information_schema + count(*)，只读事务）")

    code, out, err = psql_readonly(args.docker_bin, args.pg_container, args.pg_user, args.pg_db, PG_USERS_SQL)
    if code != 0:
        failures.append(f"PG public.users 部门分布读取失败：{err.strip() or f'返回码 {code}'}")
    else:
        extras["users"] = [l.split("|") for l in out.splitlines() if "|" in l]
    code, out, err = psql_readonly(args.docker_bin, args.pg_container, args.pg_user, args.pg_db, PG_DOC_TABULAR_SQL)
    if code != 0:
        failures.append(f"PG public.document_versions 表类登记读取失败：{err.strip() or f'返回码 {code}'}")
    else:
        extras["doc_tabular"] = [l.split("|") for l in out.splitlines() if "|" in l]
    return items, notes, failures, extras


def evaluate(item: Item, dept_cols: tuple, class_cols: tuple) -> dict:
    dept = match_columns(item.columns, dept_cols)
    cls = match_columns(item.columns, class_cols)
    sensitive = sensitive_hits(item.columns)
    try:
        nrows = int(item.rows)
    except (TypeError, ValueError):
        nrows = None
    if item.error:
        verdict = "读不到（见“未读到”一节）"
    elif not item.row_rbac:
        verdict = "不经行级判定：乙 不改其可见性"
    elif dept:
        verdict = f"不受影响（有部门列 {dept}）"
    elif nrows == 0:
        verdict = "本就 0 行，甲乙无差别"
    else:
        reachable = "今日可查=是" in item.detail
        verdict = "乙→非管理员整表查不到" + ("" if reachable else "（但今日应用侧已查不到：未登记或已退役）")
    return {
        "dept": dept,
        "cls": cls,
        "sensitive": sensitive,
        "nrows": nrows,
        "verdict": verdict,
        "no_dept": not dept,
        "bit": bool(verdict.startswith("乙→")),
    }


def report(args, items: list, dept_cols: tuple, class_cols: tuple, rbac_loc: dict,
           notes: list, failures: list, extras: dict) -> int:
    print("=" * 100)
    print("R160 只读普查 · 无部门列表面（口径来源：app/common/rbac.py，现取现写）")
    print(f"运行时间：{now_iso()}　仓库：{args.repo_root}")
    print(f"部门列候选 {DEPT_SOURCE_NAME} = {dept_cols}　（定义于 app/common/rbac.py:{rbac_loc['dept_line']}）")
    print(f"密级列候选 {CLASS_SOURCE_NAME} = {class_cols}　（定义于 app/common/rbac.py:{rbac_loc['class_line']}）")
    print(f"现状放行支路 reason_code=\"department_column_missing\" 出现在 app/common/rbac.py:"
          f"{','.join(str(n) for n in rbac_loc['missing_branch_lines'])}")
    print("=" * 100)

    rows = []
    for item in items:
        ev = evaluate(item, dept_cols, class_cols)
        rows.append((item, ev))

    print("\n【清单表】每格两行：对象名 / 指标 + 乙口径判定")
    for item, ev in sorted(rows, key=lambda r: (r[0].source, r[0].ident)):
        print(f"[{item.source}] {item.ident}")
        line = (
            f"行数={item.rows if item.rows is not None else '-'} 列数={len(item.columns)} "
            f"部门列={ev['dept'] or '无'} 密级列={ev['cls'] or '无'} "
            f"归类={item.provenance or '-'} 乙判定={ev['verdict']}"
        )
        print(f"      {line}")
        if item.source == "table-file" and item.columns:
            print(f"      列名={item.columns}")
        if item.error:
            print(f"      读取失败={item.error}")
        elif item.detail and item.source == "table-file":
            print(f"      {item.detail}")

    total = len(rows)
    no_dept = [r for r in rows if r[1]["no_dept"] and not r[0].error]
    bit = [r for r in rows if r[1]["bit"]]
    bit_customer = [r for r in bit if is_customer(r[0])]
    bit_host = [r for r in bit if is_host_untracked(r[0])]
    bit_sample = [r for r in bit if not is_customer(r[0]) and not is_host_untracked(r[0])]

    print("\n【三个汇总数】")
    print(f"  1. 普查到的表/文件总数：{total}（SQLite {sum(1 for r in rows if r[0].source=='sqlite')}　"
          f"PostgreSQL {sum(1 for r in rows if r[0].source=='postgres')}　"
          f"表类文件 {sum(1 for r in rows if r[0].source=='table-file')}）")
    print(f"  2. 无部门列的表/文件数：{len(no_dept)}"
          f"（其中走 filter_dataframe_rows 行的 {sum(1 for r in no_dept if r[0].row_rbac)}，"
          f"不走的 {sum(1 for r in no_dept if not r[0].row_rbac)}）")
    print(f"  3. 若按乙将完全查不到的表/文件数：{len(bit)}"
          f"（客户真数据(现网) {len(bit_customer)}／样本或仓内或应用元数据 {len(bit_sample)}／主机现场未跟踪 {len(bit_host)}）")
    live = [r for r in bit if "今日可查=是" in r[0].detail]
    print(f"     3b. 其中“应用今天真能查出去”的：{len(live)}（其余是未登记/已退役文件，今天也查不到）")

    print("\n【P1：无部门列 + 含敏感字段】")
    p1 = [(i, e) for i, e in rows if e["no_dept"] and any(h[2] for h in e["sensitive"])]
    p1_real = [(i, e) for i, e in p1 if i.row_rbac and not i.error]
    if not p1:
        print("  未发现：所有无部门列对象的列名里都没有敏感词典命中。")
    for item, ev in sorted(p1, key=lambda r: (not r[1]["bit"], r[0].ident)):
        labels = "、".join(sorted({f"{lbl}:{col}" for lbl, col, _p1 in ev["sensitive"] if _p1}))
        tag = "P1-甲（真越权面：走行级判定 + 今天可查）" if item.row_rbac and "今日可查=是" in item.detail \
            else ("P1-乙（走行级判定但今天查不到：未登记/已退役）" if item.row_rbac
                  else "P1-丙（敏感列在此不经行级判定，另有闸门，仍建议复核）")
        print(f"  [{tag}] {item.source} {item.ident}")
        print(f"      行数={item.rows} 归类={item.provenance} 命中={labels}")
        print(f"      甲口径下的暴露={ev['verdict']}")
    print(f"  P1 合计 {len(p1)} 枚，其中走行级判定面的 {len(p1_real)} 枚。")

    print("\n【谁在查它（行级判定路径的调用点，现取现行号）】")
    print("  app/agents/tools.py:950 / app/agents/tools.py:1067 → _authorized_dataset_files")
    print("  app/agents/tools.py:964（_analyze_data）、app/agents/tools.py:1081（_query_data）→ filter_dataframe_rows_with_scope")
    print("  登记表面：app/storage/datasets.py:229 dataset_registry（DATA_DIR + PERSISTENCE_BACKEND）")
    print("  app/api/v1/data.py:35 DATA_DIR、app/documents/catalog.py:17 DOCUMENTS_DIR")
    print("  说明：全仓 rg 未发现 read_sql / to_sql / sqlalchemy ⇒ 任何数据库表都不会被读成 DataFrame ⇒ 乙 打不到 DB 表。")
    for item, ev in sorted(rows, key=lambda r: r[0].ident):
        if item.source == "table-file" and item.consumers:
            print(f"  · {item.ident} 在仓内被引用：{', '.join(item.consumers)}")

    if extras.get("users"):
        print("\n【非管理员账号的部门归属（决定乙 对谁生效；不取 password_hash）】")
        for parts in extras["users"]:
            if len(parts) >= 3:
                print(f"  · {parts[0]}　role={parts[1]}　department={parts[2]}")

    doc_records = extras.get("doc_catalog") or []
    tab_docs = [d for d in doc_records if Path(d["filename"]).suffix.lower() in TABULAR_SUFFIXES]
    blank_dept = [d for d in doc_records if not d["department"]]
    print(f"\n【文档清单登记面（.document-versions.json）：共 {len(doc_records)} 条，"
          f"表类 csv/xlsx/xls {len(tab_docs)} 条、department 为空 {len(blank_dept)} 条】")
    for doc in tab_docs:
        print(f"  · {doc['filename']}｜清单={doc['catalog']}｜department={doc['department'] or '<空>'}")
    if extras.get("doc_tabular") is not None:
        print(f"\n【文档清单里登记的表类对象：{len(extras['doc_tabular'])} 枚（知识库面，不经行级判定）】")
        for parts in extras["doc_tabular"]:
            print("  · " + " | ".join(parts))

    print("\n【装机种子清单：全新装机第一天的“存量”（deploy/workspace-seed.json datasets 段）】")
    seed_path = Path(args.repo_root) / "deploy" / "workspace-seed.json"
    if seed_path.is_file():
        try:
            seed = json.loads(seed_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            failures.append(f"装机种子清单解析失败 {seed_path}：{type(exc).__name__}: {exc}")
        else:
            entries = seed.get("datasets") or []
            print(f"  清单登记数据集 {len(entries)} 枚（这是客户装机当天唯一的存量数据集面）")
            for entry in entries:
                name = Path(str(entry.get("path") or "")).name
                hits = [ev for it, ev in rows if it.source == "table-file" and Path(it.ident).name == name]
                state = hits[0]["verdict"] if hits else "本次没扫到这枚文件（见未读到）"
                print(f"  · {entry.get('path')}｜owner={entry.get('owner')}｜乙判定={state}")
    else:
        print(f"  未读到：{seed_path} 不存在（不当成“没有种子”）")

    if notes:
        print("\n【普查过程备注】")
        for note in notes:
            print(f"  · {note}")

    print("\n【未读到（绝不按“没有”处理）】")
    if not failures:
        print("  无：登记到的数据源全部读到。")
    for failure in failures:
        print(f"  × {failure}")

    print("\n【本次实际发出的外部命令（原样，可复核只读性）】")
    for line in _CMD_LOG:
        shown = line if len(line) <= 400 else line[:400] + " …(截断显示，未改语义)"
        print(f"  $ {shown}")

    print("\n【可写进计划书的结论口径】")
    print(f"  按乙：全量普查 {total} 格里 {len(no_dept)} 格没有部门列，但真正会被打死的是 "
          f"{len(bit)} 格，其中客户真数据 {len(bit_customer)} 格、今天应用真能查出去的 {len(live)} 格。")
    reachable_items = [r for r in rows if r[0].source == "table-file" and "今日可查=是" in r[0].detail]
    reach_no_dept = [r for r in reachable_items if r[1]["no_dept"]]
    print(f"  口径二（现网活跃数据集）：今天应用真能查出去的表 {len(reachable_items)} 枚，其中无部门列 {len(reach_no_dept)} 枚 ⇒ 乙 对现网的净影响 = {len(reach_no_dept)} 枚。")
    return 0 if not failures else 3

def default_docker_bin() -> str:
    env = os.getenv("DOCKER_BIN", "").strip()
    if env and Path(env).is_file():
        return env
    found = shutil.which("docker")
    if found:
        return found
    for candidate in (r"E:\Docker\Docker\resources\bin\docker.exe",
                      r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"):
        if Path(candidate).is_file():
            return candidate
    return "docker"


def parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="R160 只读普查：无部门列表面（不写任何文件）")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--scan-dir", action="append", default=None,
                        help="要普查的目录，可重复；默认 <repo>/data 与 <repo>/documents")
    parser.add_argument("--shallow-dir", action="append", default=None,
                        help="只普查这一层的表类文件（不递归），可重复；默认 <repo> 顶层")
    parser.add_argument("--file", action="append", default=[],
                        help="指名普查某一枚表文件（用于散落在别处的落地件），可重复")
    parser.add_argument("--sqlite-file", action="append", default=[])
    parser.add_argument("--docker-bin", default=default_docker_bin())
    parser.add_argument("--be-container", default="enterprise-brain-backend-1")
    parser.add_argument("--be-data-dir", default="/app/data")
    parser.add_argument("--be-documents-dir", default="/app/documents")
    parser.add_argument("--pg-container", default="enterprise-brain-postgres-1")
    parser.add_argument("--pg-user", default="enterprise_brain")
    parser.add_argument("--pg-db", default="enterprise_brain")
    parser.add_argument("--skip-postgres", action="store_true")
    parser.add_argument("--skip-sqlite", action="store_true")
    parser.add_argument("--skip-container", action="store_true")
    args = parser.parse_args(argv)
    if not args.scan_dir:
        root = Path(args.repo_root)
        args.scan_dir = [str(root / "data"), str(root / "documents")]
        if (root / "tmp").is_dir():  # 现场散落的 e2e/探针落地件也在这下面
            args.scan_dir.append(str(root / "tmp"))
        for name in ("DATA_DIR", "DOCUMENTS_DIR"):
            extra = os.getenv(name, "").strip()
            if extra and Path(extra).is_dir() and extra not in args.scan_dir:
                args.scan_dir.append(extra)
    args.repo_root = Path(args.repo_root).resolve()
    if not args.shallow_dir:
        args.shallow_dir = [str(args.repo_root)]
    return args


def main(argv: list | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    dept_cols, class_cols, rbac_loc = parse_rbac_candidates(args.repo_root)
    configure_terms(dept_cols, class_cols)
    tracked = build_tracked_set(args.repo_root)
    print(f"[准备] 判定源 app/common/rbac.py:{rbac_loc['dept_line']} / :{rbac_loc['class_line']}；"
          f"git 跟踪文件 {len(tracked)} 条")
    if not args.skip_postgres and not Path(args.docker_bin).is_file() and not shutil.which(args.docker_bin):
        print(f"[警告] 找不到 docker CLI（{args.docker_bin}），PostgreSQL 一侧将记为“未读到”，不会当成没有表")
        failures_note = [f"PostgreSQL 未普查：docker CLI 不可用（{args.docker_bin}）"]
    else:
        failures_note = []
    extras: dict = {}
    items, notes, failures, code_index = collect_items(
        args, args.repo_root, tracked, dept_cols, class_cols, extras
    )
    db_items, db_notes, db_failures, pg_extras = collect_db_items(
        args, args.repo_root, tracked, code_index
    )
    extras.update(pg_extras)
    items += db_items
    notes += db_notes
    failures += db_failures + failures_note
    return report(args, items, dept_cols, class_cols, rbac_loc, notes, failures, extras)


if __name__ == "__main__":
    sys.exit(main())
