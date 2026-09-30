# -*- coding: utf-8 -*-
"""R483 · 演示库里八枚 0 行的表逐枚定性（取证单，零产品码、零写库）。

病：`docs/perf/raw/r470-2026-09-29/probe-before-stop-start.json` 里八枚表 rows=0 —— 「表在」正在
冒充「闭环在」。本单不新建业务闭环、不改产品码，只把八枚表逐枚交回：今日现读 / 昨日底 /
写入点「哪个文件哪个函数」（现扫）/ 一个词的裁定 / 它该走哪条写入道。

四条口径写死在这一枚文件里，不许在别处抄第二份：

* **今日现读**只经 `docker exec <pg 容器> psql ... -c "SET default_transaction_read_only = on"
  -c "<SELECT>"`。🔴 一条写语句、一条 DDL 都不发：`assert_select_only()` 是唯一的读数出口闸，
  命中禁词直接抛。宿主 127.0.0.1:5432 上另有野 PG（上一席实测两次），所以本件从不直连宿主端口。
* **昨日底**渲染时现读那枚在册探针原件，本件里一枚数字都没抄——抄来的数就是第二个真相。
* **写入点**现场扫 `app/**` 与 `scripts/**` 的源码，得到「哪枚文件哪一枚函数往里写」，再顺着
  调用链往上爬，看这条道今天到底挂在哪张产品脸上（HTTP 路由 / `add_job`）。🔴 不许推「应该由某个
  定时任务写」：定时任务要么被 `add_job(` 现扫到（连行号带触发参数一起交回），要么这条道不存在。
* **裁定只有三个词**：`no_seed_path`（该有数据，但产品侧没有任何走得通的写入道）/
  `legitimately_empty`（按设计就该空，等一次真实行为）/ `needs_owner`（要业主输入才能填）。
  裁定与扫出来的道互为牙齿：`validate()` 里谁漂了谁红，下一班不必信本席的嘴。

所以 `docs/testing/r483-empty-tables-2026-09-29.md` 整枚是生成物：每一枚数字、每一个行号都由
`render_document()` 出，改一个字符都得重跑 `--sync`；`--check` 逐字节核（含哨兵区两面）。
形状照 `scripts/r470_restart_diff.py`，并特意避开事故 #83：`--sync` 把 BEGIN 与 END **两枚**
哨兵都写回去，`--check` 先数两枚哨兵各恰好一枚，少一枚就红——绝不许「sync 报成功而 check
说没有哨兵区」。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_PATH = (REPO_ROOT / "docs" / "perf" / "raw" / "r470-2026-09-29"
              / "probe-before-stop-start.json")
DOC_PATH = REPO_ROOT / "docs" / "testing" / "r483-empty-tables-2026-09-29.md"
#: 扫源码时要把本件自己与自己的测试剔掉：这些行里写满了八枚表名，不剔就是自造的假写入点。
SELF_TOKENS = ("r483_empty_tables_triage", "r483_empty_table_triage")

BEGIN = "<!-- R483-TABLE-BEGIN -->"
END = "<!-- R483-TABLE-END -->"
READOUT_BEGIN = "<!-- R483-READOUT-BEGIN -->"
READOUT_END = "<!-- R483-READOUT-END -->"
NL = chr(10)

#: 本单点名的八枚 0 行表；顺序即文档里的呈现顺序，不许悄悄加宽或换序。
TARGET_TABLES = (
    "alerts",
    "alert_rules",
    "notification_states",
    "calculation_runs",
    "metric_definitions",
    "retrieval_traces",
    "user_profiles",
    "document_activity_signals",
)
#: 🔴 尺子不许空转：这两枚在册非空表跟着进同一张读数表，读出 0 就说明读数件在骗人。
CONTROL_TABLES = ("chunk_vectors", "sessions")
CONTROL_FLOOR = {"chunk_vectors": 1, "sessions": 1}
#: V2 那三句明话要引用的旁证格（同样只 SELECT 现读）。
CONTEXT_TABLES = ("pending_approvals", "trace_events", "agent_runs", "documents", "users")
READ_TABLES = TARGET_TABLES + CONTROL_TABLES + CONTEXT_TABLES

VERDICTS = ("no_seed_path", "legitimately_empty", "needs_owner")

CONTAINER = "enterprise-brain-postgres-1"
SCHEDULER_CONTAINER = "enterprise-brain-scheduler-1"
PG_USER = "enterprise_brain"
PG_DB = "enterprise_brain"
READ_ONLY_PREFIX = "SET default_transaction_read_only = on"
#: 告警巡检这一条道的运行证据只从这枚 job 名数起（在册名，见 scripts 扫出的 add_job）。
SWEEP_JOB = "evaluate_all"

IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")
#: SELECT 里一枚都不许出现的词：判据③「一条写语句/一条 DDL 都不许发」的代码化。
FORBIDDEN_IN_SELECT = (
    "insert", "update", "delete", "create", "alter", "drop", "truncate", "grant", "revoke",
    "copy", "vacuum", "analyze", "call", "merge", "refresh", "comment", "prepare",
    "deallocate", "set",
)


def assert_select_only(sql: str) -> str:
    """唯一的读数出口闸：不是 SELECT 就抛，命中禁词也抛。"""
    body = sql.strip().rstrip(";").strip()
    lowered = body.lower()
    if not lowered.startswith(("select", "with")):
        raise ValueError("R483 只许发 SELECT，收到的是：" + body[:120])
    for word in FORBIDDEN_IN_SELECT:
        if re.search(r"\b" + word + r"\b", lowered):
            raise ValueError("R483 的 SELECT 里出现禁词 " + word + "：" + body[:120])
    return body


def run_argv(argv, timeout: int = 120) -> tuple:
    """唯一的对外执行出口：原样发出 argv，返回 (rc, stdout, stderr)。"""
    proc = subprocess.run([str(item) for item in argv], capture_output=True, timeout=timeout)
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"))


def psql_select(sql: str, docker_bin: str = "docker") -> list:
    """进容器发一条只读 SELECT，返回数据行（psql 回显的 `SET` 不是数据，剔掉）。"""
    guarded = assert_select_only(sql)
    argv = [docker_bin, "exec", CONTAINER, "psql", "-U", PG_USER, "-d", PG_DB, "-At",
            "-v", "ON_ERROR_STOP=1", "-c", READ_ONLY_PREFIX, "-c", guarded]
    code, out, err = run_argv(argv)
    if code != 0:
        raise RuntimeError("psql 读数失败 rc=%d: %s" % (code, err.strip()[:300]))
    return [line for line in out.split(NL) if line.strip() and line.strip() != "SET"]


def pk_sql(table: str) -> str:
    if not IDENT_RE.match(table):
        raise ValueError("表名不合法：" + table)
    return ("SELECT coalesce(string_agg(column_name, ','), 'NONE') "
            "FROM information_schema.key_column_usage WHERE table_schema='public' "
            "AND table_name='" + table + "' AND constraint_name IN ("
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_schema='public' AND table_name='" + table + "' "
            "AND constraint_type='PRIMARY KEY')")


def census_sql(table: str, pk_col: str) -> str:
    """一枚表一行读数：行数 + 主键顶值。多列主键只报行数，顶值留 None（现读实况）。"""
    if not IDENT_RE.match(table):
        raise ValueError("表名不合法：" + table)
    column = (pk_col or "").strip().strip("'")
    if "," in column or not IDENT_RE.match(column or "x"):
        return ("SELECT json_build_object('rows', count(*)::int, 'pk_max', NULL)::text FROM "
                + table)
    return ("SELECT json_build_object('rows', count(*)::int, 'pk_max', max(" + column
            + ")::text)::text FROM " + table)


EVENT_SQL = ("SELECT coalesce(json_object_agg(event_type, n)::text, '{}') FROM "
             "(SELECT event_type AS event_type, count(*)::int AS n FROM trace_events "
             "GROUP BY event_type) t")


def server_identity(docker_bin: str = "docker") -> dict:
    """读数是从哪台库拿的，留名进文档：这是为了把「宿主那枚野 5432」钉死在证据外面。"""
    lines = psql_select("SELECT current_database() || '#' || current_user || '#' || "
                        "coalesce(inet_server_addr()::text, 'local') || '#' || version()",
                        docker_bin)
    parts = (lines[0] if lines else "").split("#")
    return {"container": CONTAINER,
            "database": parts[0] if parts else "",
            "db_user": parts[1] if len(parts) > 1 else "",
            "server_addr": parts[2] if len(parts) > 2 else "",
            "version": parts[3] if len(parts) > 3 else ""}


def scheduler_sweeps(docker_bin: str = "docker") -> dict:
    """告警巡检今天到底跑没跑：只读 scheduler 容器日志数成功行，零写入、零 DDL。"""
    code, out, err = run_argv([docker_bin, "logs", "--tail", "4000", SCHEDULER_CONTAINER])
    text = out + err
    interval = None
    #: 在册日志格式：Job "evaluate_all (trigger: interval[0:05:00], next run at: ...)" ...
    match = re.search(r'"' + SWEEP_JOB + r' \(trigger: interval\[([0-9:.]+)\]', text)
    if match:
        interval = match.group(1)
    done = re.compile(r'^(\d{4}-\d{2}-\d{2})[^\n]*"' + SWEEP_JOB
                      + r'[^\n]*executed successfully', re.M)
    days = [match.group(1) for match in done.finditer(text)]
    return {"rc": code, "container": SCHEDULER_CONTAINER,
            "successful_sweeps_in_tail": len(days),
            "trigger_interval": interval,
            "days_seen": sorted(set(days))}


def collect_live_readings(docker_bin: str = "docker") -> dict:
    """🔴 全篇唯一的取数口：逐枚现读，只发 SELECT，读出来的原始数落进文档那份读数块。"""
    readout = {}
    for table in READ_TABLES:
        pk_lines = psql_select(pk_sql(table), docker_bin)
        pk_col = pk_lines[0] if pk_lines else "NONE"
        rows_lines = psql_select(census_sql(table, pk_col), docker_bin)
        body = json.loads(rows_lines[0]) if rows_lines else {}
        readout[table] = {"rows": int(body.get("rows") or 0),
                          "pk_max": body.get("pk_max"),
                          "pk": None if pk_col == "NONE" else pk_col}
    events = {}
    event_lines = psql_select(EVENT_SQL, docker_bin)
    if event_lines:
        events = json.loads(event_lines[0])
    return {"taken_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "server": server_identity(docker_bin),
            "command": ("docker exec " + CONTAINER + " psql -U " + PG_USER + " -d " + PG_DB
                        + " -At -v ON_ERROR_STOP=1 -c \"" + READ_ONLY_PREFIX
                        + "\" -c \"<SELECT>\""),
            "readout": readout,
            "trace_event_types": events,
            "alert_sweep_log": scheduler_sweeps(docker_bin)}


def baseline_from_probe(probe_path: Path = PROBE_PATH) -> dict:
    """昨日底：渲染时现读在册探针原件，一枚数字都不在本件里过夜。"""
    census = json.loads(probe_path.read_text(encoding="utf-8"))["db"]
    return {name: {"rows": int((body or {}).get("rows") or 0),
                   "pk_max": (body or {}).get("pk_max")}
            for name, body in census.items()}


PRODUCT_ROOTS = ("app", "scripts")
MIGRATION_ROOT = "migrations"
TEST_ROOT = "tests"

DEF_RE = re.compile(r"^(?P<indent>[ \t]*)(?:async\s+)?def\s+(?P<name>[A-Za-z_]\w*)")
ROUTE_RE = re.compile(r"@(?:router|app|api)\.(?P<verb>get|post|put|delete|patch)\("
                      r"\s*[\"'](?P<path>[^\"']*)[\"']", re.I)
IMPORT_RE = re.compile(r"^\s*(from|import)\s")
WRITE_VERB = r"(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE)"
CREATE_RE = r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+"
#: 命中 kinds 的呈现顺序：真写语句 > 经表名常量拼出来的写句 > 注册型写点 > 声明这枚写入道的
#: 函数本身（多行调用扫不到同一行时，靠它把「哪个函数写它」现取回来）> 建表出处。
KIND_ORDER = ("sql_write", "write_via_table_constant", "write_by_registry", "declared_writer",
              "ddl")
BFS_NODE_CAP = 60
BFS_CALLERS_PER_NODE = 8


def _is_self_file(rel: str) -> bool:
    return any(token in rel for token in SELF_TOKENS)


def _fmt_location(file: str, line: int, symbol: str = "") -> str:
    label = file + ":" + str(line)
    return label + (" · " + symbol if symbol else "")


class Hit:
    """一枚现扫到的坐标：文件、行、种类、落在哪枚函数里。"""

    def __init__(self, file: str, line: int, kind: str, symbol: str, text: str):
        self.file = file
        self.line = line
        self.kind = kind
        self.symbol = symbol
        self.text = text

    def location(self) -> str:
        return _fmt_location(self.file, self.line, self.symbol)

    def __repr__(self) -> str:
        return "<Hit %s %s>" % (self.kind, self.location())


class SourceIndex:
    """把「这张表在代码里有没有写入点、那条道通向哪张脸」变成一次现场扫描。

    🔴 三件事由它现取，文档里一枚都不许抄：写语句的行号、包着它的函数名、以及这个函数
    往上爬能碰到的 HTTP 路由 / add_job。爬到脸 = 走得通的写入道；爬不到 = no_seed_path。
    """

    def __init__(self, root, product_roots=PRODUCT_ROOTS):
        self.root = Path(root)
        self.product = self._load(product_roots, ".py")
        self.migrations = self._load((MIGRATION_ROOT,), ".sql")
        self.tests = self._load((TEST_ROOT,), ".py")

    def _load(self, folders, suffix: str) -> dict:
        store = {}
        for folder in folders:
            base = self.root / folder
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*" + suffix)):
                rel = path.relative_to(self.root).as_posix()
                if _is_self_file(rel):
                    continue
                store[rel] = path.read_text(encoding="utf-8", errors="replace").split(NL)
        return store

    # -------------------------------------------------------------- 定位与装饰器
    def lines_of(self, rel: str) -> list:
        return self.product.get(rel) or self.migrations.get(rel) or []

    def symbol_at(self, rel: str, lineno: int) -> str:
        """这一行落在哪一枚函数里：往上找最近的一枚 def，并要求中间没有退回过它的缩进。

        不认缩进就会读出一张假脸：app/storage/persistence.py 的表注册是一张模块级字典，
        往上最近的一枚 def 与它毫无关系，认领错了就等于本单在说「有个函数写着这张表的注册」——
        那是第二句假话。缩进退回过，就答「模块级」（空串）。
        """
        lines = self.lines_of(rel)
        target = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
        target_indent = len(target) - len(target.lstrip())
        for i in range(min(lineno, len(lines)) - 1, -1, -1):
            match = DEF_RE.match(lines[i])
            if not match:
                continue
            def_indent = len(match.group("indent"))
            if def_indent >= target_indent:
                return ""
            #: 多行签名（app/rag/debug.py 那种 ) -> dict[str, Any]: 顶格收尾）不是「退出了函数体」，
            #: 所以要带括号深度判：深度没归零之前的行全部算签名的一部分。
            blocked = False
            depth = 0
            for j in range(i, lineno - 1):
                line = lines[j]
                stripped = line.strip()
                #: 深度还没归零 = 这一行仍是上一枚语句（多行签名 / 多行调用）的一部分，不作出缩进判。
                if (j > i and depth <= 0 and stripped and not stripped.startswith("#")
                        and len(line) - len(line.lstrip()) <= def_indent):
                    blocked = True
                    break
                depth += (line.count("(") + line.count("[") + line.count("{")
                          - line.count(")") - line.count("]") - line.count("}"))
            if blocked:
                return ""
            return match.group("name")
        return ""

    def route_above(self, rel: str, def_line: int) -> str:
        """def 头顶连着写的 @router.xxx("...") —— 有它才叫挂在产品脸上。"""
        lines = self.lines_of(rel)
        verbs = []
        for i in range(def_line - 2, -1, -1):
            line = lines[i]
            if not line.strip():
                continue
            match = ROUTE_RE.search(line)
            if line.lstrip().startswith("@") and match:
                verbs.append(match.group("verb").upper() + " " + match.group("path"))
                continue
            break
        return " / ".join(reversed(verbs))

    def definition(self, symbol: str):
        """def <symbol>( 在 app/ 与 scripts/ 里的坐标；找不到返回 None（不猜）。"""
        pattern = re.compile(r"^(?P<indent>[ \t]*)(?:async\s+)?def\s+" + re.escape(symbol)
                             + r"\s*\(")
        for rel, lines in sorted(self.product.items()):
            for i, line in enumerate(lines, 1):
                if pattern.match(line):
                    return Hit(rel, i, "declared_writer", symbol, line.strip())
        return None

    # -------------------------------------------------------------- 写入点扫描
    def write_hits(self, table: str) -> list:
        """一枚表的写入点：真写句、经 TABLE 常量拼出来的写句、注册型写点、建表出处。"""
        if not IDENT_RE.match(table):
            raise ValueError("表名不合法：" + table)
        literal = re.compile(r"\b" + WRITE_VERB + r"\s+(?:ONLY\s+)?" + re.escape(table) + r"\b",
                             re.I)
        ddl = re.compile(CREATE_RE + re.escape(table) + r"\b", re.I)
        constant = re.compile(r"[A-Z_]*TABLE[A-Z_]*\s*=\s*[\"']" + re.escape(table) + r"[\"']")
        interpolated = re.compile(r"\b" + WRITE_VERB + r"\s*\{")
        registry_head = re.compile(r"(?:_PostgresTable\(|\.upsert\(|Projection\()")
        hits = []
        for rel, lines in sorted(self.product.items()):
            constants = any(constant.search(line) for line in lines)
            for i, line in enumerate(lines, 1):
                if ddl.search(line):
                    hits.append(Hit(rel, i, "ddl", self.symbol_at(rel, i), line.strip()))
                elif literal.search(line) and not re.search(CREATE_RE, line, re.I):
                    hits.append(Hit(rel, i, "sql_write", self.symbol_at(rel, i), line.strip()))
                elif constants and interpolated.search(line):
                    hits.append(Hit(rel, i, "write_via_table_constant", self.symbol_at(rel, i),
                                    line.strip()))
                elif registry_head.search(line) and re.search(r"[\"']" + re.escape(table)
                                                              + r"[\"']", line):
                    hits.append(Hit(rel, i, "write_by_registry", self.symbol_at(rel, i),
                                    line.strip()))
        for rel, lines in sorted(self.migrations.items()):
            for i, line in enumerate(lines, 1):
                if ddl.search(line):
                    hits.append(Hit(rel, i, "ddl", "", line.strip()))
        hits.sort(key=lambda item: (KIND_ORDER.index(item.kind) if item.kind in KIND_ORDER
                                    else len(KIND_ORDER), item.file, item.line))
        return hits

    def ddl_home(self, table: str) -> str:
        """结构出处：migrations 里那枚 CREATE TABLE 优先，没有再看 app 里有没有自建表。"""
        for rel, lines in sorted(self.migrations.items()):
            for i, line in enumerate(lines, 1):
                if re.search(CREATE_RE + re.escape(table) + r"\b", line, re.I):
                    return rel + ":" + str(i)
        for hit in self.write_hits(table):
            if hit.kind == "ddl":
                return hit.location()
        return ""

    # -------------------------------------------------------------- 调用链上爬
    def callers(self, symbol: str) -> list:
        """谁在这个函数的名字后面写了左括号（import 行不算调用；定义行本身不算调用）。"""
        call = re.compile(r"(?<!\w)" + re.escape(symbol) + r"\s*\(")
        definition = re.compile(r"(?:async\s+)?def\s+" + re.escape(symbol) + r"\s*\(")
        #: 别的类里恰好同名的 self.方法（app/trace/store.py 也有一枚 _apply），不是这条道。
        receiver = re.compile(r"(?<!\w)(?:self|cls)\." + re.escape(symbol) + r"\s*\(")
        hits = []
        for rel, lines in sorted(self.product.items()):
            for i, line in enumerate(lines, 1):
                if IMPORT_RE.match(line) or definition.search(line) or receiver.search(line):
                    continue
                if call.search(line):
                    hits.append(Hit(rel, i, "caller", self.symbol_at(rel, i), line.strip()))
        return hits

    def job_hits(self, symbol: str) -> list:
        """add_job(<symbol> —— 定时任务这条道只有被现扫到才算存在。"""
        pattern = re.compile(r"add_job\(\s*" + re.escape(symbol) + r"\b")
        hits = []
        for rel, lines in sorted(self.product.items()):
            for i, line in enumerate(lines, 1):
                if pattern.search(line):
                    hits.append(Hit(rel, i, "job", self.symbol_at(rel, i), line.strip()))
        return hits

    def test_refs(self, symbol: str) -> list:
        """tests/ 里的引用：只用来把「测试夹具写过」与「产品有数据」分开说，不计入产品面。"""
        names = []
        pattern = re.compile(r"(?<!\w)" + re.escape(symbol) + r"\b")
        for rel, lines in sorted(self.tests.items()):
            if any(pattern.search(line) for line in lines):
                names.append(rel)
        return names

    def surface(self, entries, events=()) -> dict:
        """从写入函数往上爬到产品脸：HTTP 路由装饰器或 add_job；顺带留下爬过的脚印。"""
        routes, jobs, trail, problems = [], [], [], []
        queue = []
        for entry in entries:
            location = self.definition(entry)
            if location is not None:
                trail.append(location.location())
        for event in events:
            for emitter in self.event_emitters(event):
                trail.append(_fmt_location(emitter.file, emitter.line, emitter.symbol))
                if emitter.symbol:
                    queue.append((emitter.symbol, 0))
        if not events:
            queue += [(symbol, 0) for symbol in entries]
        seen = set()
        while queue:
            symbol, hop = queue.pop(0)
            if not symbol or symbol in seen or hop > 5:
                continue
            seen.add(symbol)
            if len(seen) > BFS_NODE_CAP:
                problems.append("调用链超过 " + str(BFS_NODE_CAP) + " 枚节点，本单不敢全收")
                break
            for job in self.job_hits(symbol):
                jobs.append({"file": job.file, "line": job.line, "text": job.text})
            location = self.definition(symbol)
            if location is not None:
                trail.append(location.location())
                route = self.route_above(location.file, location.line)
                if route:
                    routes.append({"file": location.file, "line": location.line,
                                   "symbol": symbol, "route": route})
                for caller in self.callers(symbol)[:BFS_CALLERS_PER_NODE]:
                    if caller.symbol:
                        queue.append((caller.symbol, hop + 1))
        return {"routes": _dedupe(routes, "route"),
                "jobs": _dedupe(jobs, "text"),
                "trail": sorted(set(trail)),
                "nodes": len(seen),
                "problems": problems}

    def event_emitters(self, event_type: str) -> list:
        """谁在发这枚事件：product 里 event_type="<event>" 的行（写路径的闸门就在这儿）。"""
        pattern = re.compile(r"event_type\s*=\s*[\"']" + re.escape(event_type) + r"[\"']")
        hits = []
        for rel, lines in sorted(self.product.items()):
            for i, line in enumerate(lines, 1):
                if pattern.search(line):
                    hits.append(Hit(rel, i, "emitter", self.symbol_at(rel, i), line.strip()))
        return hits

    def references(self, table: str) -> dict:
        """这枚表名在 app/ 与 scripts/ 里到底出现过几次（一次都没有 = 连读路径都没长）。"""
        pattern = re.compile(r"\b" + re.escape(table) + r"\b")
        files = []
        for rel, lines in sorted(self.product.items()):
            count = sum(1 for line in lines if pattern.search(line))
            if count:
                files.append((rel, count))
        return {"files": files, "total": sum(count for _, count in files)}


def _dedupe(items, key: str) -> list:
    out, seen = [], set()
    for item in items:
        marker = (item.get("file"), item.get("line"), str(item.get(key)))
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return sorted(out, key=lambda item: (item["file"], item["line"]))


#: 本席的裁定台账。「入口函数名 / 事件名」是坐标，行号一律由 SourceIndex 现扫，本表里一个行号
#: 都不写——这是判据⑦（同一棵树今天漂过 150 行）的落点。裁定与扫描结果谁漂了谁红：牙在
#: validate() 里，不在这段话里。
TRIAGE = {
    "alerts": {
        "verdict": "legitimately_empty",
        "entries": ("evaluate_all",),
        "events": (),
        "hit_kinds": ("sql_write",),
        "lane": "只有巡检命中才写：告警行唯一出处是 app/api/v1/alerts.py::evaluate_all 里那句 "
                "INSERT INTO alerts，规则集取自 alert_rules 里 enabled=TRUE 的行。上表另一枚 "
                "sql_write 是处置闭环的 UPDATE（确认 / 转派 / 关闭），它只改状态，不加行。",
        "why": "这条道今天真在跑（现扫到的 add_job 注册 + scheduler 日志里的成功行数，两格都进本表），"
               "空的是它的上游：一枚启用规则都没有，逐规则判定无从命中。补一条业主规则它自己会长行，"
               "缺的不是码。无库时的代码兜底规则走的是内存表，不构成本表数据。",
    },
    "alert_rules": {
        "verdict": "needs_owner",
        "entries": ("create_rule",),
        "events": (),
        "hit_kinds": ("sql_write",),
        "lane": "app/api/v1/alerts.py::create_rule（HTTP 建规则那一腿）→ INSERT INTO alert_rules。",
        "why": "规则的三要素（指标 / 运算符 / 阈值）就是一家企业的口径，代码替业主编一条就是假账。"
               "写入道在树且现扫得到路由，演示库从没建过规则 ⇒ 这 0 行是业主侧欠一次录入，不是欠码。",
    },
    "notification_states": {
        "verdict": "legitimately_empty",
        "entries": ("apply_state",),
        "events": (),
        "hit_kinds": ("write_via_table_constant",),
        "lane": "app/notifications/states.py::apply_state（表名走本文件的 TABLE 常量拼进写句）→ "
                "POST /notifications/read 与 /notifications/dismiss 两条腿共用它。",
        "why": "按设计只有真人点「已读 / 忽略」才写这一行，收件箱本身不开第四本账（三条源全从已有的账"
               "现读）。所以 0 行的准确说法是：铃铛挂上之后没人点过一次。要补的是端到端行为读数，"
               "不是接口。",
    },
    "calculation_runs": {
        "verdict": "no_seed_path",
        "entries": (),
        "events": (),
        "hit_kinds": (),
        "expect_no_write_hits": True,
        "expect_zero_references": True,
        "lane": "没找到：app/ 与 scripts/ 里现扫不到任何一条写这张表的语句。",
        "why": "结构在（现扫到的 CREATE TABLE 出处进本表），表名在 app/ 与 scripts/ 里一次都没出现，"
               "连读路径都没有。V2 第 3 句里「Artifact 绑 CalculationRun」那一格今天仍是后续目标，"
               "不是已有能力。",
    },
    "metric_definitions": {
        "verdict": "no_seed_path",
        "entries": ("register_metric_definition", "sync_code_definitions"),
        "events": (),
        "hit_kinds": ("write_via_table_constant",),
        "blocked_at": "promote_relation_to_definition",
        "owner_ruling": "裁定出处：总控 2026-09-29 裁定——本轮**不加 HTTP 面**（promotion 出口挂哪张脸"
                        "属 V2 语义层的决定），保持 no_seed_path；本格不再挂待裁。",
        "lane": "写句在树：app/semantics/registry.py::_insert_statement / ::_store_row（表名走 "
                "TABLE_NAME 常量）。入口是 register_metric_definition 与 sync_code_definitions。",
        "why": "两条入口从产品面都爬不到：register_metric_definition 唯一的调用者是 "
               "app/knowledge_graph/promotion.py::promote_relation_to_definition，而后者在 app/ 与 "
               "scripts/ 里现扫零调用者；sync_code_definitions 同样零调用者。tests/ 里能调到它——按"
               "判据④那不算产品数据。读侧此刻靠代码兜底口径作答，所以这是「写的那半没接上」，"
               "不是整条链不存在。",
    },
    "retrieval_traces": {
        "verdict": "no_seed_path",
        "entries": ("project_retrieval",),
        "events": ("retrieval.completed",),
        "hit_kinds": ("write_by_registry", "declared_writer"),
        #: 现扫确实能爬到一枚 HTTP 面，但那是 RAG 调试面；本单显式声明它不算「喂产品数据的道」，
        #: 并把它挂在读数里给所有人看。豁免没用上（那枚路由不在了）就是一枚问题，不许当后门留着。
        "debug_only_surface": ("/retrieval/debug",),
        "owner_ruling": "裁定出处：总控 2026-09-29 裁定——当时唯一发射点在 RAG 调试面"
                        "（" + "app/rag/debug.py" + " 发 retrieval.completed ← POST /retrieval/debug），"
                        "正常问答链一枚都不发 ⇒「有表、有写句、但没有喂它产品的道」。**那半句话已经过期**："
                        "R536（09-30 并树）把发射实现接到产品问答道，POST /ask 与 /approve 续跑轮现在都发"
                        "这枚事件，实现在全仓唯一一处（app/rag/retrieval_pipeline.py::"
                        "record_retrieval_completed）。裁定暂不翻：本量具认的「道」是从写语句往上爬到 HTTP"
                        " 路由或 add_job，而本表写句在事件投影里（app/trace/projections.py::"
                        "project_retrieval 由 trace store 派发），这一跳现扫爬不过去，所以它按自己的判据仍"
                        "读 no_seed_path。**这是量具的盲区，不是产品道没接通**，治它另立 R550；本格在 R550 "
                        "并树前不许被读成「问答不写这张表」，也不许被翻绿。",
        "lane": "app/trace/projections.py::project_retrieval（collection 走 _PostgresTable 注册）→ "
                "app/trace/store.py 的投影落库；闸门是有人发 retrieval.completed 事件。",
        "why": "本表现读只认两件事：写语句在不在、能不能从写句爬到产品脸。第一件在（"
               "project_retrieval 注册在册）；第二件爬到的是调试面 /retrieval/debug——事件投影那一跳"
               "不在现扫的爬法里，所以产品问答道今天虽然确实发这枚事件（R536 已并树），本表仍按判据读 "
               "no_seed_path。库里 retrieval.completed 的事件数由本表现读交回，读出 0 不区分「没跑过窗」"
               "与「道不通」，这一格要 R550 补上才量得准。",
    },
    "user_profiles": {
        "verdict": "needs_owner",
        "entries": ("upsert_profile",),
        "events": (),
        "hit_kinds": ("sql_write",),
        "lane": "app/memory/profile.py::upsert_profile ← app/api/v1/auth.py 的 PUT /api/v1/profile。",
        "why": "这格里该躺的是员工自报的职位与偏好，只能业主侧录。department 那一列已被 R296 钉成"
               "只读派生值，写入道今天明确不收它——所以「回填 department」不算这条道的填法。",
    },
    "document_activity_signals": {
        "verdict": "legitimately_empty",
        "entries": ("record_document_signal",),
        "events": (),
        "hit_kinds": ("sql_write",),
        "lane": "app/api/v1/feedback.py::record_document_signal ← POST /feedback/document"
                "（前端正脸在 frontend/src/lib/feedback.js 与 components/SourceCard.vue）。",
        "why": "只有采纳 / 驳回一次才加一次计数，演示库没有真人点过。读侧今天把「读成功而零行」当作"
               "一种独立状态记账（app/rag/retriever.py 的活动先验诊断格为此留了名目），所以零行不等于"
               "读不到。",
    },
}

#: V2 三条自述各挂一句明话：有数据就给表名与行数，没有就写没有。数字全部从读数件取。
V2_CHAINS = (
    {
        "goal": "#11 告警闭环",
        "tables": ("alert_rules", "alerts"),
        "kind": "alerts",
    },
    {
        "goal": "#17 通知基础能力",
        "tables": ("notification_states", "pending_approvals"),
        "kind": "notifications",
    },
    {
        "goal": "#3 CalculationRun（执行数据血缘）",
        "tables": ("calculation_runs",),
        "kind": "calculation",
    },
)


def inline(text: str) -> str:
    return chr(96) + text + chr(96)


def _fmt_cell(text: str, limit: int = 56) -> str:
    flat = str(text).replace("|", "\\|").replace(NL, " ")
    return flat if len(flat) <= limit else flat[:limit - 1] + "…"


def product_surface(analysis: dict) -> dict:
    """把「现扫爬到的脸」切成两叠：喂产品数据的道 / 被显式豁免的调试面。

    🔴 豁免必须是显式声明的（spec 里的 debug_only_surface），且必须真用得上：一旦那枚路由不再
    被扫到，"unused exemption" 就是一枚问题——不许留一条静默的后门把 no_seed_path 撑住。
    """
    routes = analysis["surface"]["routes"]
    excludes = analysis["spec"].get("debug_only_surface", ())
    debug = [route for route in routes if any(word in route["route"] for word in excludes)]
    product = [route for route in routes if route not in debug]
    return {"routes": product,
            "jobs": analysis["surface"]["jobs"],
            "debug_only": debug,
            "unused_exemptions": [word for word in excludes
                                  if not any(word in route["route"] for route in routes)]}


def analyze(index: SourceIndex, table: str) -> dict:
    """一枚表的现扫结果：写入点、结构出处、这条道今天挂在哪个产品面、表名出现处。"""
    spec = TRIAGE[table]
    hits = list(index.write_hits(table))
    for symbol in spec["entries"]:
        location = index.definition(symbol)
        if location is not None and not any(
                item.file == location.file and item.line == location.line for item in hits):
            hits.append(location)
    hits.sort(key=lambda item: (KIND_ORDER.index(item.kind) if item.kind in KIND_ORDER
                                else len(KIND_ORDER), item.file, item.line))
    return {
        "spec": spec,
        "hits": hits,
        "references": index.references(table),
        "ddl_home": index.ddl_home(table),
        "surface": index.surface(spec["entries"], spec["events"]),
    }


def _with_product(analysis: dict) -> dict:
    analysis["product"] = product_surface(analysis)
    return analysis


def build_readings(payload: dict, index: SourceIndex, probe: dict) -> dict:
    return {"payload": payload, "index": index, "probe": probe,
            "analysis": {table: _with_product(analyze(index, table)) for table in TARGET_TABLES}}


def rows_of(readings: dict, table: str) -> dict:
    body = (readings["payload"].get("readout") or {}).get(table) or {}
    return {"rows": int(body.get("rows") or 0), "pk_max": body.get("pk_max"),
            "pk": body.get("pk")}


def baseline_of(readings: dict, table: str) -> dict:
    body = (readings["probe"] or {}).get(table) or {}
    return {"rows": int(body.get("rows") or 0), "pk_max": body.get("pk_max")}


def render_readout_table(readings: dict) -> list:
    lines = [
        "| 表 | 今日现读 | 昨日底 | Δ | 主键顶值（今日现读） | 写入点（现扫 文件:行 · 函数） | 结构出处 | 裁定 |",
        "|---|---:|---:|---:|---|---|---|---|",
    ]
    for table in TARGET_TABLES:
        today = rows_of(readings, table)
        base = baseline_of(readings, table)
        hits = readings["analysis"][table]["hits"]
        writes = [hit for hit in hits if hit.kind != "ddl"]
        cell = ", ".join(inline(hit.location()) for hit in writes[:2]) or "没找到"
        if len(writes) > 2:
            cell += " ＋" + str(len(writes) - 2) + " 处"
        delta = today["rows"] - base["rows"]
        lines.append("| %s | %d | %d | %s | %s | %s | %s | %s |" % (
            inline(table), today["rows"], base["rows"], ("%+d" % delta) if delta else "0",
            _fmt_cell(str(today["pk_max"] if today["pk_max"] is not None else "None"), 40),
            cell, inline(readings["analysis"][table]["ddl_home"] or "没找到"),
            inline(TRIAGE[table]["verdict"])))
    return lines


def render_controls(readings: dict) -> list:
    lines = [
        "| 对照表 | 今日现读 | 昨日底 | 主键顶值（今日现读） | 尺子自证 |",
        "|---|---:|---:|---|---|",
    ]
    for table in CONTROL_TABLES:
        today = rows_of(readings, table)
        base = baseline_of(readings, table)
        verdict = "非空，读数件不是空转" if today["rows"] >= CONTROL_FLOOR[table] else "🔴 读出 0，尺子在空转"
        lines.append("| %s | %d | %d | %s | %s |" % (
            inline(table), today["rows"], base["rows"],
            _fmt_cell(str(today["pk_max"] if today["pk_max"] is not None else "None"), 40),
            verdict))
    return lines


def render_per_table(readings: dict) -> list:
    lines = []
    for table in TARGET_TABLES:
        analysis = readings["analysis"][table]
        spec = analysis["spec"]
        today = rows_of(readings, table)
        base = baseline_of(readings, table)
        writes = [hit for hit in analysis["hits"] if hit.kind != "ddl"]
        surface = analysis["surface"]
        lines += ["", "### " + inline(table) + " —— " + inline(spec["verdict"]), ""]
        lines.append("- 今日现读 " + str(today["rows"]) + " 行（昨日底 " + str(base["rows"])
                     + " 行，Δ " + str(today["rows"] - base["rows"]) + "），主键 "
                     + inline(str(today["pk"] or "没读到")) + " 顶值 "
                     + inline(str(today["pk_max"])) + "。")
        lines.append("- 结构出处：" + inline(analysis["ddl_home"] or "没找到")
                     + "；表名在 app/ 与 scripts/ 里现扫到 " + str(analysis["references"]["total"])
                     + " 行、" + str(len(analysis["references"]["files"])) + " 枚文件。")
        if writes:
            lines.append("- 写入点（现扫）：" + "、".join(
                inline(hit.location()) + "（" + hit.kind + "）" for hit in writes[:4])
                + ("，另有 " + str(len(writes) - 4) + " 处" if len(writes) > 4 else "") + "。")
        else:
            lines.append("- 写入点（现扫）：**没找到**（app/ 与 scripts/ 里没有任何写这张表的语句）。")
        product = analysis["product"]
        if product["routes"]:
            lines.append("- 这条道今天挂在产品面上：" + "、".join(
                inline(route["route"] + " ← " + _fmt_location(route["file"], route["line"],
                                                             route["symbol"]))
                for route in product["routes"]) + "。")
        else:
            lines.append("- 这条道今天没挂在任何产品面 HTTP 路由上（现扫零枚）。")
        if product["debug_only"]:
            lines.append("- 🔴 现扫确实爬到一枚脸，但它是**调试面**，按本单显式豁免不算产品道："
                         + "、".join(inline(route["route"] + " ← "
                                          + _fmt_location(route["file"], route["line"], route["symbol"]))
                                     for route in product["debug_only"]) + "。")
        if product["unused_exemptions"]:
            lines.append("- ⚠ 本件声明了调试面豁免却没用上（口径过期）：" + "、".join(
                inline(word) for word in product["unused_exemptions"]) + "。")
        if surface["jobs"]:
            lines.append("- 定时任务这条道现扫到：" + "、".join(
                inline(job["file"] + ":" + str(job["line"]) + " → " + job["text"])
                for job in surface["jobs"]) + "。")
        else:
            lines.append("- 定时任务这条道现扫为零（🔴 所以本单不写「应该由某个定时任务写」这种话）。")
        if surface["trail"]:
            lines.append("- 从写句往上爬过的坐标：" + "、".join(
                inline(item) for item in surface["trail"][:6])
                + ("，另有 " + str(len(surface["trail"]) - 6) + " 枚"
                   if len(surface["trail"]) > 6 else "") + "。")
        test_refs = []
        for symbol in spec["entries"]:
            test_refs += readings["index"].test_refs(symbol)
        if test_refs:
            named = sorted(set(test_refs))
            lines.append("- 入口只在测试里被引到：" + "、".join(inline(name) for name in named[:4])
                         + ("，另有 " + str(len(named) - 4) + " 枚" if len(named) > 4 else "")
                         + "（按判据④，那不算产品有一行真数据）。")
        lines.append("- 该走哪条写入道：" + spec["lane"])
        lines.append("- 裁定理由：" + spec["why"])
        blocked = spec.get("blocked_at")
        if blocked:
            location = readings["index"].definition(blocked)
            callers = readings["index"].callers(blocked)
            lines.append("- 道断在：" + inline(location.location() if location is not None
                                             else "现扫找不到它的 def") + "（现扫调用者 "
                         + str(len(callers)) + " 枚：调用者或产品面一出现，这一句与 "
                         + inline("validate()") + " 同时红）。")
        if spec.get("owner_ruling"):
            lines.append("- " + spec["owner_ruling"])
    return lines

FENCE = chr(96) * 3
JSON_FENCE = FENCE + "json"


def render_v2_sentences(readings: dict) -> list:
    """V2 三条各挂一句明话：有数据给表名与行数，没有就写没有（判据④）。"""
    payload = readings["payload"]
    sweep = payload.get("alert_sweep_log") or {}
    events = payload.get("trace_event_types") or {}
    alert_jobs = len(readings["analysis"]["alerts"]["surface"]["jobs"])
    rules = rows_of(readings, "alert_rules")["rows"]
    alerts = rows_of(readings, "alerts")["rows"]
    approvals = rows_of(readings, "pending_approvals")["rows"]
    documents = rows_of(readings, "documents")["rows"]
    users = rows_of(readings, "users")["rows"]
    states = rows_of(readings, "notification_states")["rows"]
    calc = rows_of(readings, "calculation_runs")["rows"]
    calc_refs = readings["analysis"]["calculation_runs"]["references"]["total"]
    retrieval = rows_of(readings, "retrieval_traces")["rows"]
    metrics = rows_of(readings, "metric_definitions")["rows"]
    completed = int(events.get("retrieval.completed") or 0)
    return [
        "- **#11 告警闭环**：今天**没有一行真数据** —— 现读 " + inline("alert_rules") + " "
        + str(rules) + " 行、" + inline("alerts") + " " + str(alerts) + " 行。代码侧不是空转："
        + inline("add_job") + " 现扫到 " + str(alert_jobs) + " 枚注册（连触发参数与行号进上面那张表），"
        + inline(SCHEDULER_CONTAINER) + " 日志尾部现数到 "
        + str(int(sweep.get("successful_sweeps_in_tail") or 0)) + " 次 " + inline(SWEEP_JOB)
        + " executed successfully（间隔现读 " + inline(str(sweep.get("trigger_interval"))) + "）。"
        + "⇒ 挡在这条链前面的是业主一条启用规则，不是缺码。",
        "- **#17 通知基础能力**：今天**没有一行行为数据** —— 现读 " + inline("notification_states")
        + " " + str(states) + " 行。收件箱本身有账可列（现读 " + inline("pending_approvals") + " "
        + str(approvals) + " 行、" + inline("documents") + " " + str(documents) + " 行、"
        + inline("users") + " " + str(users) + " 行），但没有任何一次已读/忽略落表；告警那一枚候选源"
        "今天恒交白卷（" + inline("alerts") + " " + str(alerts) + " 行）。⇒ 接口与前端正脸在树，"
        "端到端行为读数为零，这句只能报 (乙)。",
        "- **#3 CalculationRun（执行数据血缘）**：今天**没有一行真数据** —— 现读 "
        + inline("calculation_runs") + " " + str(calc) + " 行，且表名在 " + inline("app/") + " 与 "
        + inline("scripts/") + " 里现扫 " + str(calc_refs) + " 处引用（连读路径都没长）。"
        + "⇒ 「每个 Artifact 绑 DatasetVersion、CalculationRun、MetricDefinition」那句仍是后续目标；"
        + "同一句里的 " + inline("metric_definitions") + " 现读 " + str(metrics) + " 行、"
        + inline("retrieval_traces") + " 现读 " + str(retrieval) + " 行（库里 "
        + inline("retrieval.completed") + " 事件 " + str(completed) + " 条）。",
    ]


def render_event_appendix(readings: dict) -> list:
    """事件面现读：把「问答跑得再多也不给 retrieval_traces 加行」这句钉成一枚数。"""
    events = readings["payload"].get("trace_event_types") or {}
    lines = ["", "事件面现读（" + inline("trace_events") + " 按 event_type 分组，只 SELECT）："]
    for name, count in sorted(events.items(), key=lambda item: (-int(item[1]), item[0])):
        lines.append("- " + inline(name) + "：" + str(int(count)) + " 条")
    lines.append("- 其中 " + inline("retrieval.completed") + "（" + inline("retrieval_traces")
                 + " 今天唯一的闸门事件）：" + str(int(events.get("retrieval.completed") or 0))
                 + " 条")
    return lines


def render_region(readings: dict) -> str:
    """哨兵区里的全部内容：那张读数表与它的推论，每一枚数字都出自这里。"""
    payload = readings["payload"]
    server = payload.get("server") or {}
    lines = ["", "## 一、读数表（今日现读 / 昨日底 / 写入点现扫 / 裁定）"]
    lines += render_readout_table(readings)
    lines += ["", "## 二、逐枚：它该走哪条写入道"]
    lines += render_per_table(readings)
    lines += ["", "## 三、V2 三条自述：今天有没有一行真数据"]
    lines += render_v2_sentences(readings)
    lines += ["", "## 四、尺子自证（已知非空的表跟着进同一张读数表）"]
    lines += render_controls(readings)
    lines += render_event_appendix(readings)
    lines += ["", "## 五、原始读数（机器件，勿手改；" + inline("--check")
              + " 就用它复现上面每一格）", READOUT_BEGIN, JSON_FENCE,
              json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), FENCE,
              READOUT_END,
              "读数出处：" + inline(str(server.get("container"))) + " / 库 "
              + inline(str(server.get("database"))) + " / 账号 " + inline(str(server.get("db_user")))
              + " / 服务端地址 " + inline(str(server.get("server_addr"))) + " / "
              + _fmt_cell(str(server.get("version")), 120) + "；取数时刻 "
              + inline(str(payload.get("taken_at"))) + "。🔴 宿主 127.0.0.1:5432 上另有野 PG，"
              "本件从不直连它。"]
    return NL.join(line for line in lines if line is not None)


def render_document(readings: dict) -> str:
    """整枚文档的唯一出口。文档里没有任何一枚手写数字：要改就改生成器，或者重跑 --sync。"""
    payload = readings["payload"]
    head = [
        "<!-- 本文件整枚由 scripts/r483_empty_tables_triage.py 生成（--sync）。" + NL
        + "     改文案改生成器，改数重跑读数；手写任何一格，--check 逐字节红。 -->",
        "",
        "# R483 · 演示库八枚 0 行表的逐枚定性（2026-09-29）",
        "",
        "本单是取证单：不新建业务闭环、不改产品码，只把「结构在、一行没有」的八枚表逐枚定性，"
        "让下一班知道哪枚是真欠码、哪枚本来就该空、哪枚只能等业主。",
        "",
        "## 口径（四句写死在生成器里，不在别处抄第二份）",
        "",
        "- **今日现读**：" + inline(payload.get("command") or "") + "。" + inline("psql_select()")
        + " 里那道 " + inline("assert_select_only()") + " 是唯一读数出口：不是 SELECT 就抛，"
        "命中 insert / update / delete / create / alter / drop 一类禁词也抛。🔴 一条写语句、"
        "一条 DDL 都没发；除了在册库 " + inline(PG_DB) + "，没碰任何别的库。",
        "- **昨日底**：" + inline("PROBE_PATH") + " 里那枚 " + inline("rows") + "，渲染时现读原件，"
        "本件不隔夜存这份数。",
        "- **写入点**：现场扫 " + inline("app/**") + " 与 " + inline("scripts/**")
        + " 的源码得到「哪枚文件哪枚函数往里写」，再顺调用链往上爬，看这条道今天挂在哪个产品面"
        "（HTTP 路由 / " + inline("add_job") + "）。🔴 扫不到就写没找到，绝不写「应该由某个定时任务写」。",
        "- 路由串按装饰器原文交回（**不含** router 前缀），坐标一律现扫：🔴 本文件一枚行号都不是抄的。"
        + "　**裁定只有三词**：" + " / ".join(inline(word) for word in VERDICTS)
        + "；裁定与现扫互为牙齿，谁漂了 " + inline("validate()") + " 报哪一格。",
        "- 取数时刻 " + inline(str(payload.get("taken_at"))) + "；服务端 "
        + _fmt_cell(str((payload.get("server") or {}).get("version")), 120) + "。",
        "",
        "结论一句话：八枚里没有一枚是「码写完了等着跑」——" + str(sum(
            1 for table in TARGET_TABLES if TRIAGE[table]["verdict"] == "no_seed_path"))
        + " 枚今天压根没有走得通的写入道，" + str(sum(
            1 for table in TARGET_TABLES if TRIAGE[table]["verdict"] == "needs_owner"))
        + " 枚只能等业主录入，" + str(sum(
            1 for table in TARGET_TABLES if TRIAGE[table]["verdict"] == "legitimately_empty"))
        + " 枚按设计就该空着等一次真实行为。",
    ]
    tail = [
        "",
        "## 六、怎么重跑（同一把尺子，两面对）",
        "",
        "- 现读 PG + 现扫源码并回写本文件：" + inline("python scripts/r483_empty_tables_triage.py --sync"),
        "- 逐字节核盘上这张表（离线，用第五节那份原始读数复现每一格）："
        + inline("python scripts/r483_empty_tables_triage.py --check"),
        "- 核完再比一遍库里现值，漂了就说漂（要容器在跑）："
        + inline("python scripts/r483_empty_tables_triage.py --check --verify-live"),
        "- 只打读数不写文件：" + inline("python scripts/r483_empty_tables_triage.py --print")
        + "；机器可读：" + inline("python scripts/r483_empty_tables_triage.py --json"),
        "",
        "🔴 本件零产品码：除这枚生成器、本文件与 " + inline("tests/test_r483_empty_table_triage_is_derived.py")
        + " 三枚新件，全仓零写入。测试件：" + inline("tests/test_r483_empty_table_triage_is_derived.py") + "。",
        "",
    ]
    return (NL.join(head) + NL + BEGIN + NL + render_region(readings) + NL + END + NL
            + NL.join(tail))


def count_sentinels(text: str) -> dict:
    return {"begin": text.count(BEGIN), "end": text.count(END)}


def extract_payload(text: str) -> dict:
    """从文档第五节那份原始读数里取回取数现场，--check 因此全程离线可复现。"""
    if READOUT_BEGIN not in text or READOUT_END not in text:
        raise ValueError("文档里没有原始读数哨兵")
    segment = text.split(READOUT_BEGIN, 1)[1].split(READOUT_END, 1)[0]
    match = re.search(JSON_FENCE + NL + r"(.*?)" + NL + FENCE, segment, re.S)
    if not match:
        raise ValueError("原始读数哨兵里没有 json 代码块")
    return json.loads(match.group(1))


def splice_region(doc_text: str, region: str) -> str:
    """把生成表写回哨兵区。🔴 BEGIN 与 END 两枚都重新写回——事故 #83 的教训就在这两行。"""
    head, rest = doc_text.split(BEGIN, 1)
    _old, tail = rest.split(END, 1)
    return head + BEGIN + NL + region.rstrip(NL) + NL + END + tail


def validate(readings: dict) -> list:
    """五族牙：0 行还成立、裁定与现扫互证、写入点扫描不许空转、对照表不许 0、日志要撑得住那句话。"""
    problems = []
    payload = readings["payload"]
    readout = payload.get("readout") or {}
    for table in TARGET_TABLES:
        if table not in readout:
            problems.append(table + " 今日现读缺格（读数件里没有它）")
        if table not in readings["probe"]:
            problems.append(table + " 昨日底缺格（探针原件里没有它）")
    if sorted(TRIAGE) != sorted(TARGET_TABLES):
        problems.append("裁定台账的表名与点名的八枚不一致：" + repr(sorted(TRIAGE)))
    for table in TARGET_TABLES:
        spec = TRIAGE[table]
        analysis = readings["analysis"][table]
        surface = analysis["surface"]
        problems += [table + "：" + item for item in surface["problems"]]
        verdict = spec["verdict"]
        if verdict not in VERDICTS:
            problems.append(table + " 的裁定不在三词表里：" + verdict)
        rows = rows_of(readings, table)["rows"]
        if rows != 0:
            problems.append(table + " 今天已经有 " + str(rows) + " 行了，本单的 0 行定性过期，"
                            "重跑 --sync")
        kinds = {hit.kind for hit in analysis["hits"]}
        for kind in spec.get("hit_kinds", ()):
            if kind not in kinds:
                problems.append(table + " 的写入点扫描空了：现扫不到 " + kind
                                + " 这一类命中，裁 " + verdict + " 的依据没了")
        writes = {kind for kind in kinds if kind != "ddl"}
        if spec.get("expect_no_write_hits") and writes:
            problems.append(table + " 裁为 no_seed_path，但现扫到了写入点："
                            + ", ".join(sorted(writes)))
        if spec.get("expect_zero_references") and analysis["references"]["total"]:
            problems.append(table + " 裁为「连读点都没有」，但表名在 app/ 与 scripts/ 里现扫到 "
                            + str(analysis["references"]["total"]) + " 处")
        product = analysis["product"]
        has_product = bool(product["routes"] or product["jobs"])
        if verdict == "no_seed_path" and has_product:
            problems.append(table + " 裁为 no_seed_path，但现扫已能从产品面走到它，裁定过期："
                            + repr(product["routes"] + product["jobs"]))
        if verdict in ("legitimately_empty", "needs_owner") and not has_product:
            problems.append(table + " 裁为 " + verdict + "，但现扫爬不到任何产品面 HTTP 路由或 "
                            "add_job：按判据这条道不存在，应改判 no_seed_path")
        for word in product["unused_exemptions"]:
            problems.append(table + " 声明了调试面豁免 " + word + "，但现扫爬不到那枚路由："
                            "豁免成了后门，要么删声明要么重裁")
        blocked = spec.get("blocked_at")
        if blocked:
            location = readings["index"].definition(blocked)
            if location is None:
                problems.append(table + " 的 blocked_at 找不到 def：" + blocked + "，那句「道断在它」过期")
            else:
                callers = readings["index"].callers(blocked)
                if callers:
                    problems.append(table + " 的「道断在 " + blocked + "」已被推翻：现扫到调用者 "
                                    + ", ".join(item.location() for item in callers[:3]))
    for table in CONTROL_TABLES:
        rows = rows_of(readings, table)["rows"]
        if rows < CONTROL_FLOOR[table]:
            problems.append("尺子空转：对照表 " + table + " 读出 " + str(rows)
                            + " 行，读数件不可信，本单所有 0 行都不作数")
    sweep = payload.get("alert_sweep_log") or {}
    if int(sweep.get("successful_sweeps_in_tail") or 0) <= 0:
        problems.append("#11 那句「巡检真在跑」没有日志支撑：" + inline(SCHEDULER_CONTAINER)
                        + " 现数到 " + str(int(sweep.get("successful_sweeps_in_tail") or 0))
                        + " 次成功")
    if not (payload.get("trace_event_types") or {}):
        problems.append("事件面读数为空：#3 与 retrieval_traces 那两句引用的分组条数没有出处")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R483 · 八枚 0 行表的逐枚定性（只读取证件）")
    ap.add_argument("--doc", default=str(DOC_PATH), help="生成物落点")
    ap.add_argument("--probe", default=str(PROBE_PATH), help="昨日底探针原件")
    ap.add_argument("--scan-root", default=str(REPO_ROOT), help="扫写入点的仓根")
    ap.add_argument("--docker-bin", default="docker")
    ap.add_argument("--sync", action="store_true", help="现读 PG + 现扫源码，回写整枚文档")
    ap.add_argument("--check", action="store_true", help="逐字节核盘上那张表（离线）")
    ap.add_argument("--verify-live", action="store_true", help="再读一次库，与文档里那份逐格比")
    ap.add_argument("--live-from-doc", action="store_true",
                    help="不重读 PG，用文档第五节那份读数（离线复现与测试用）")
    ap.add_argument("--print", dest="print_doc", action="store_true", help="把整枚文档打到 stdout")
    ap.add_argument("--json", dest="as_json", action="store_true",
                    help="把读数件、现扫写入点与裁定打成 JSON")
    args = ap.parse_args(argv)

    doc_path = Path(args.doc)
    probe = baseline_from_probe(Path(args.probe))
    index = SourceIndex(Path(args.scan_root))
    payload = None
    if args.live_from_doc or args.check or args.print_doc or args.as_json:
        if not doc_path.exists():
            print("ABORT: 盘上没有 " + str(doc_path) + "，先 --sync", file=sys.stderr)
            return 2
        try:
            payload = extract_payload(doc_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print("ABORT: 取不回原始读数：" + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
            return 6
    if payload is None:
        payload = collect_live_readings(args.docker_bin)
    readings = build_readings(payload, index, probe)
    problems = validate(readings)
    document = render_document(readings)
    region = render_region(readings)

    if args.as_json:
        print(json.dumps({
            "payload": payload,
            "problems": problems,
            "triage": {table: {
                "verdict": TRIAGE[table]["verdict"],
                "lane": TRIAGE[table]["lane"],
                "routes": readings["analysis"][table]["surface"]["routes"],
                "jobs": readings["analysis"][table]["surface"]["jobs"],
                "write_hits": [hit.location() + " (" + hit.kind + ")"
                               for hit in readings["analysis"][table]["hits"]],
                "ddl_home": readings["analysis"][table]["ddl_home"],
            } for table in TARGET_TABLES}},
            ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not problems else 1

    if args.sync:
        if doc_path.exists():
            marks = count_sentinels(doc_path.read_text(encoding="utf-8"))
            if marks["begin"] != 1 or marks["end"] != 1:
                print("ABORT: %s 的哨兵区不成对（begin=%d end=%d），不许把手写件当成生成物覆盖"
                      % (doc_path, marks["begin"], marks["end"]), file=sys.stderr)
                return 5
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(document, encoding="utf-8", newline=NL)
        print("synced %s bytes=%d problems=%d" % (doc_path, len(document.encode("utf-8")),
                                                  len(problems)))
        return 0 if not problems else 1

    if args.print_doc:
        sys.stdout.write(document)
        return 0 if not problems else 1

    if args.check:
        text = doc_path.read_text(encoding="utf-8")
        marks = count_sentinels(text)
        if marks["begin"] != 1 or marks["end"] != 1:
            print("FAIL: 文档里哨兵区不成对（BEGIN=%d END=%d）——就是事故 #83 那一格"
                  % (marks["begin"], marks["end"]), file=sys.stderr)
            return 3
        on_disk = text.split(BEGIN, 1)[1].split(END, 1)[0].strip()
        if on_disk != region.strip():
            print("FAIL: 盘上那张表与再生件逐字节不符（手写或抄了旧班）", file=sys.stderr)
            return 4
        if text != document:
            print("FAIL: 本件整枚是生成物，哨兵区外的文案也被改过了——改文案请改生成器",
                  file=sys.stderr)
            return 4
        if args.verify_live:
            fresh = collect_live_readings(args.docker_bin)
            drift = []
            for table in READ_TABLES:
                before = (payload.get("readout") or {}).get(table) or {}
                after = (fresh.get("readout") or {}).get(table) or {}
                if (before.get("rows") != after.get("rows")
                        or before.get("pk_max") != after.get("pk_max")):
                    drift.append(table + ": " + repr(before) + " -> " + repr(after))
            if drift:
                print("FAIL: 库里现值与文档里那份读数已经漂了：" + NL + NL.join(drift),
                      file=sys.stderr)
                return 7
            print("PASS verify-live：库里现值与文档读数逐格一致（文档取数时刻 "
                  + str(payload.get("taken_at")) + "）")
        if problems:
            print("FAIL check：盘上那张表确实是再生件，但读数本身没过判据", file=sys.stderr)
            for item in problems:
                print("  - " + item, file=sys.stderr)
            return 1
        print("PASS check：八枚表 + 两枚对照 + 现扫写入点全部逐字节复现，problems=0")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
