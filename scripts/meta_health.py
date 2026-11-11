"""R682 · 元健康 KPI 量具：四数一红线，一条命令一张机器账。

来历：规矩已改成「判进度只看四个数」（`docs/engineering/multi-agent-project-rules-2026-10-05.md` §D），
但那四个数今天全靠每班手抄现取——手抄就是下一本假账。本件把它变成一条命令。

四数一红线（逐枚可失败，缺一枚判负）：
  ① 产品面 ``product_face``        —— ``app/**`` py 枚数与近 N 笔新增行数、``tests/**`` py 枚数、路由枚数；
  ② 验证墙钟 ``validation_wallclock`` —— 从 ``docs/testing/**`` 与看板里取**同 HEAD** 的复跑数，取不到打 ``NOT_MEASURED``；
  ③ 台账字节 ``ledger_bytes``       —— 跟进单与看板逐枚字节数；
  ④ 并树/日 ``merges_per_day``      —— ``git log --since`` 现算近 7 天逐日并树枚数；
  🔴 红线   ``markdown_share``      —— 读 markdown 的用例枚数 ÷ 全集枚数，分子分母都打印。

自守的规矩：
  ① 零 import ``app``、零起服务、零动容器、零打模型，全离线；整把尺自跑墙钟 ≤ 60 s。
  ② 造数即红：每一枚 MEASURED 读数都带出处，出处必须能当场复算＋原文可寻；复算不等就点名并判红。
  ③ 取不到只许写 ``NOT_MEASURED``，且该读数里一行数字都不许夹带。
  ④ 坐标一律 ``文件::符号`` 或 ``git:<谓词>``／``fs:<谓词>``，本文件不写 ``文件:数字``。

已知边界（不是缺陷，是口径）：红线分子按「函数体内直接读」与「经由本模块 helper 传递读」两档同时给出，
第三档 ``upper_bound`` 是「函数体里出现过 docs 字面量」的宽口径上限；模块级常量派生后再被间接使用的
那一族不在闭包里——本尺只报现算的三档读数，不外推。
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import time
import warnings
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Mapping, Sequence

REPO = Path(__file__).resolve().parents[1]

SCHEMA_VERSION = 1
EXIT_GREEN = 0
EXIT_RED = 1
MEASURED = "MEASURED"
NOT_MEASURED = "NOT_MEASURED"
SELF_RUNTIME_LIMIT_S = 60.0
RECENT_COMMITS_DEFAULT = 200
SINCE_DAYS_DEFAULT = 7

FOLLOWUP_LEDGER = "docs/handoff/2026-09-15-backend-followup-requests.md"
BOARD_LEDGER = "docs/handoff/2026-09-15-orchestration-board.md"
GATE_DOC_DIR = "docs/testing"

MEGA = "\x01"

#: 并树的现取判据：提交标题里带「并树」二字，或它本身就是一枚 merge 提交
MERGE_SUBJECT = re.compile(r"并树")
MERGE_COMMIT_SUBJECT = re.compile(r"^(?:Merge|merge)\b")

#: 手抄坐标（``文件:数字``）——本尺的出处里一枚都不许有
LINE_COORDINATE = re.compile(r"[A-Za-z0-9_./\\-]+\.(?:py|md|rst|tsv|json|jsonl|toml|sh|ya?ml)[:：]([0-9]+)")

#: 提交号形状（用于「账面引用的 sha 到底存不存在」这一道反造数闸）
SHA_TOKEN = re.compile(r"(?<![0-9a-f])([0-9a-f]{7,40})(?![0-9a-f])")

ROUTE_METHODS = frozenset(
    {
        "get",
        "post",
        "put",
        "delete",
        "patch",
        "head",
        "options",
        "trace",
        "websocket",
        "api_route",
        "add_api_route",
    }
)
DOC_READ_METHODS = frozenset({"read_text", "read_bytes", "open", "glob", "rglob", "iterdir"})
DOC_READ_FUNCTIONS = frozenset({"open", "Path"})

REQUIRED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("product_face", "① 产品面", "app/tests/路由枚数"),
    ("validation_wallclock", "② 验证墙钟", "同 HEAD 复跑秒数"),
    ("ledger_bytes", "③ 每轮必读台账字节数", "跟进单＋看板"),
    ("merges_per_day", "④ 并树/日", "近 7 天逐日"),
    ("markdown_share", "🔴 红线·读 markdown 的用例占比", "分子/分母都印"),
)


@dataclass(frozen=True)
class Provenance:
    """一枚读数的出处：kind 决定怎么复算，coordinates 决定是谁在供数，recheck 是当场重算。"""

    kind: str
    coordinates: tuple[str, ...]
    excerpts: tuple[str, ...]
    recheck: Callable[[], Mapping[str, str]]


@dataclass(frozen=True)
class Reading:
    """一列读数。MEASURED 必须可复算；NOT_MEASURED 一行数字都不许夹带。"""

    key: str
    label: str
    values: Mapping[str, str]
    provenance: Provenance | None = None
    status: str = MEASURED
    reason: str = ""


NET_DIFF_MISSING = "NOT_MEASURED"


def _run_git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} rc={proc.returncode}: {proc.stderr.strip()[:160]}")
    return proc.stdout


def _py_files(repo: Path, subdir: str) -> list[Path]:
    root = repo / subdir
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _parse(path: Path) -> ast.Module | None:
    try:
        with warnings.catch_warnings():
            # 扫别人的源码不是本尺的活：历史件里的 invalid escape sequence 不许冒进账面
            warnings.simplefilter("ignore", SyntaxWarning)
            warnings.simplefilter("ignore", DeprecationWarning)
            return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return None


def _string_constants(node: ast.AST) -> set[str]:
    return {sub.value for sub in ast.walk(node) if isinstance(sub, ast.Constant) and isinstance(sub.value, str)}


def _is_docs_literal(text: str) -> bool:
    normalized = text.replace("\\", "/")
    return (
        normalized.endswith(".md")
        or normalized == "docs"
        or normalized.startswith("docs/")
        or "/docs/" in normalized
        or normalized.startswith("./docs")
    )


def _doc_literals(literals: set[str]) -> list[str]:
    return sorted(item for item in literals if _is_docs_literal(item))


# ==================== ① 产品面 ====================

def _route_decorator_count(files: Sequence[Path]) -> tuple[int, list[str]]:
    total = 0
    unparsable: list[str] = []
    for path in files:
        tree = _parse(path)
        if tree is None:
            unparsable.append(path.name)
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                if isinstance(target, ast.Attribute) and target.attr in ROUTE_METHODS:
                    total += 1
    return total, unparsable


def _git_added_lines(repo: Path, subdir: str, limit: int) -> int:
    """逐笔累加的近 N 笔新增行数（含同一行被反复重写，是 churn 口径）。"""
    out = _run_git(
        repo,
        "log",
        f"-n{limit}",
        "--no-renames",
        "--numstat",
        f"--format={MEGA}%H",
        "--",
        subdir,
    )
    return _sum_numstat_added(out, subdir)


def _git_added_lines_net(repo: Path, subdir: str, limit: int) -> str:
    """近 N 笔的净新增行数：``HEAD~N`` 到 ``HEAD`` 一次性 diff（同一行改三次只算一次）。"""
    probe = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"HEAD~{limit}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        return NET_DIFF_MISSING
    base = probe.stdout.strip()
    out = _run_git(repo, "diff", "--no-renames", "--numstat", base, "HEAD", "--", subdir)
    return str(_sum_numstat_added(out, subdir))


def _sum_numstat_added(numstat: str, subdir: str) -> int:
    added = 0
    for line in numstat.splitlines():
        if line.startswith(MEGA):
            continue
        columns = line.split("\t")
        if len(columns) < 3 or not columns[0].isdigit():
            continue
        if columns[2].startswith(f"{subdir}/"):
            added += int(columns[0])
    return added


def measure_product_face(repo: Path, recent_commits: int = RECENT_COMMITS_DEFAULT) -> Reading:
    def snapshot() -> Mapping[str, str]:
        app_files = _py_files(repo, "app")
        tests_files = _py_files(repo, "tests")
        routes, unparsable = _route_decorator_count(app_files)
        if unparsable:
            raise RuntimeError("unparsable app sources: " + ",".join(unparsable))
        return {
            "app_py_files": str(len(app_files)),
            "app_added_lines_churn_last_n_commits": str(_git_added_lines(repo, "app", recent_commits)),
            "app_added_lines_net_last_n_commits": _git_added_lines_net(repo, "app", recent_commits),
            "tests_py_files": str(len(tests_files)),
            "api_route_decorators": str(routes),
            "recent_commits_window": str(recent_commits),
        }

    values = snapshot()
    return Reading(
        key="product_face",
        label="① 产品面",
        values=values,
        provenance=Provenance(
            kind="fs",
            coordinates=(
                "git::log_numstat_no_renames",
                "git::diff_numstat_base_to_head",
                "ast::app_route_decorators",
                "fs::app_tests_py_glob",
            ),
            excerpts=(
                f"git log -n{recent_commits} --no-renames --numstat -- app",
                f"git diff --no-renames --numstat HEAD~{recent_commits} HEAD -- app",
            ),
            recheck=snapshot,
        ),
    )


# ==================== ② 验证墙钟 ====================

PASSED_COUNT = re.compile(r"\b(\d+) passed\b")
SKIPPED_COUNT = re.compile(r"\b(\d+) skipped\b")
EXIT_ZERO = re.compile(r"exit\s*==?\s*0\b")
WALLCLOCK = re.compile(r"(\d+(?:\.\d+)?)\s*s\b")


def _gate_doc_files(repo: Path) -> list[Path]:
    files = sorted((repo / GATE_DOC_DIR).rglob("*.md"))
    board = repo / BOARD_LEDGER
    if board.is_file():
        files.append(board)
    return files


def _pick_wallclock(line: str) -> tuple[str, str]:
    """门秒数只认 ``run_gate`` 自己报的那一枚；账面没写 ``run_gate`` 就取行内最后一枚秒数。

    形状凭据：「（pytest 125.63 s，run_gate 133.6 s，exit=0）」取 133.6 不取 125.63——
    内层 pytest 的秒数不含起子进程与折叠的钱，不是门的墙钟。
    """
    durations = list(WALLCLOCK.finditer(line))
    if not durations:
        return "", ""
    anchor = line.rfind("run_gate")
    if anchor >= 0:
        after = [match for match in durations if match.start() > anchor]
        if after:
            return after[0].group(1), "run_gate_duration"
    return durations[-1].group(1), "last_duration_in_line"


def _gate_records(files: Sequence[Path], repo: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            relative = path.relative_to(repo).as_posix()
        except ValueError:
            relative = path.name
        for line in text.splitlines():
            if not EXIT_ZERO.search(line):
                continue
            passed = PASSED_COUNT.search(line)
            wallclock_s, wallclock_basis = _pick_wallclock(line)
            if not passed or not wallclock_s:
                continue
            shas = SHA_TOKEN.findall(line)
            if not shas:
                continue
            skipped = SKIPPED_COUNT.search(line)
            records.append(
                {
                    "shas": ";".join(dict.fromkeys(shas)),
                    "passed": passed.group(1),
                    "skipped": skipped.group(1) if skipped else "0",
                    "wallclock_s": wallclock_s,
                    "wallclock_basis": wallclock_basis,
                    "source": relative,
                    "excerpt": line.strip()[:300],
                }
            )
    return records


def _known_commits(repo: Path, shas: Sequence[str]) -> set[str]:
    """账面引的那些 sha 到底有几枚真在仓里——一次 ``cat-file --batch-check`` 全量验。

    取不到就是造数：既把它从候选里剔掉，也把它计入 ``gate_records_phantom_sha`` 那一格。
    """
    candidates = list(dict.fromkeys(sha for sha in shas if sha))
    if not candidates:
        return set()
    payload = "".join(f"{sha}^{{commit}}\n" for sha in candidates)
    proc = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch-check"],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    lines = proc.stdout.splitlines()
    if len(lines) != len(candidates):
        raise RuntimeError(f"git cat-file --batch-check 回了 {len(lines)} 行，投了 {len(candidates)} 枚")
    return {sha for sha, line in zip(candidates, lines) if line.strip() and "missing" not in line and "error" not in line}


def _head_sha(repo: Path) -> str:
    return _run_git(repo, "rev-parse", "HEAD").strip()


def _sha_matches_head(candidate: str, head: str) -> bool:
    return bool(candidate) and (head.startswith(candidate) or candidate.startswith(head[:7]))


def _record_shas(record: Mapping[str, str]) -> list[str]:
    return [sha for sha in record["shas"].split(";") if sha]


def _record_matches_head(record: Mapping[str, str], head: str) -> bool:
    return any(_sha_matches_head(sha, head) for sha in _record_shas(record))


def _record_is_real(record: Mapping[str, str], known: set[str]) -> bool:
    return any(sha in known for sha in _record_shas(record))


HEADLINE_FIELDS = ("wallclock_s", "passed", "skipped", "rerun_sha", "wallclock_basis")


def _collect_gate_readings(repo: Path) -> dict[str, list[dict[str, str]]]:
    files = _gate_doc_files(repo)
    records = _gate_records(files, repo)
    head = _head_sha(repo)
    known = _known_commits(repo, [sha for record in records for sha in _record_shas(record)])
    live = [record for record in records if _record_is_real(record, known)]
    same_head = [record for record in live if _record_matches_head(record, head)]
    return {
        "files": files,
        "records": records,
        "live": live,
        "same_head": same_head,
        "head": [head],
    }


def _scan_stats(collected: Mapping[str, list]) -> Mapping[str, str]:
    return {
        "gate_source_files": str(len(collected["files"])),
        "gate_records_found": str(len(collected["records"])),
        "gate_records_verified_sha": str(len(collected["live"])),
        "gate_records_phantom_sha": str(len(collected["records"]) - len(collected["live"])),
    }


def wallclock_values(collected: Mapping[str, list]) -> Mapping[str, str]:
    """有同 HEAD 的复跑就照抄那枚秒数；没有就整行 ``NOT_MEASURED``，一枚数字都不夹带。"""
    matched = collected["same_head"]
    if not matched:
        return {name: NOT_MEASURED for name in HEADLINE_FIELDS}
    record = matched[-1]
    head = collected["head"][0]
    matched_sha = next((sha for sha in _record_shas(record) if _sha_matches_head(sha, head)), NOT_MEASURED)
    return {
        "wallclock_s": record["wallclock_s"],
        "passed": record["passed"],
        "skipped": record["skipped"],
        "rerun_sha": matched_sha,
        "wallclock_basis": record["wallclock_basis"],
        **_scan_stats(collected),
    }


def assemble_wallclock_reading(
    collected: Mapping[str, list], *, recheck: Callable[[], Mapping[str, str]]
) -> Reading:
    """把候选读数拼成一枚 Reading：出处逐字取账面原文，秒数取同 HEAD 那一枚。"""
    matched = collected["same_head"]
    cited = matched or collected["live"][-1:]
    coordinates = tuple(dict.fromkeys(f"{record['source']}::gate_readings" for record in cited)) or (
        f"{GATE_DOC_DIR}::gate_readings",
    )
    excerpts = tuple(record["excerpt"] for record in cited) or ("(no gate record lines found)",)
    reason = ""
    status = MEASURED
    if not matched:
        newest = collected["live"][-1] if collected["live"] else None
        reason = "NO_SAME_HEAD_RERUN"
        if newest:
            reason += f"::nearest_not_same_head={newest['shas']}@{newest['wallclock_s']}s::{newest['source']}"
        reason += f"::scanned={_scan_stats(collected)['gate_source_files']}_files"
        status = NOT_MEASURED
    return Reading(
        key="validation_wallclock",
        label="② 验证墙钟",
        values=wallclock_values(collected),
        provenance=Provenance(
            kind="doc",
            coordinates=coordinates,
            excerpts=excerpts,
            recheck=recheck,
        ),
        status=status,
        reason=reason,
    )


def measure_validation_wallclock(repo: Path) -> Reading:
    """只认「账面里写明了 HEAD、而那枚 HEAD 就是当前 HEAD」的复跑秒数；对不上就 NOT_MEASURED。

    反造数三道闸：① 出处必须逐字落在被点名的账面里；② 账面引的 sha 必须真在仓里
    （``git cat-file --batch-check``）；③ 当场复算一遍，数字漂移就点名。
    """
    return assemble_wallclock_reading(
        _collect_gate_readings(repo),
        recheck=lambda: wallclock_values(_collect_gate_readings(repo)),
    )


# ==================== ③ 每轮必读台账字节数 ====================

def measure_ledger_bytes(repo: Path) -> Reading:
    def snapshot() -> Mapping[str, str]:
        values = {}
        total = 0
        for label, relative in (("followup", FOLLOWUP_LEDGER), ("board", BOARD_LEDGER)):
            size = (repo / relative).stat().st_size
            values[f"{label}_bytes"] = str(size)
            total += size
        values["total_bytes"] = str(total)
        return values

    return Reading(
        key="ledger_bytes",
        label="③ 每轮必读台账字节数",
        values=snapshot(),
        provenance=Provenance(
            kind="fs",
            coordinates=(f"{FOLLOWUP_LEDGER}::whole_file", f"{BOARD_LEDGER}::whole_file"),
            excerpts=("pathlib.Path.stat().st_size",),
            recheck=snapshot,
        ),
    )


# ==================== ④ 并树/日 ====================

def measure_merges_per_day(repo: Path, since_days: int = SINCE_DAYS_DEFAULT) -> Reading:
    def snapshot() -> Mapping[str, str]:
        rows = _run_git(
            repo,
            "log",
            f"--since={since_days}.days.00:00",
            "--date=short",
            f"--format=%ad{MEGA}%s",
        )
        per_day: dict[str, int] = {}
        for line in rows.splitlines():
            if MEGA not in line:
                continue
            day, _, subject = line.partition(MEGA)
            if MERGE_SUBJECT.search(subject) or MERGE_COMMIT_SUBJECT.match(subject):
                per_day[day] = per_day.get(day, 0) + 1
        today = date.today()
        window = [(today - timedelta(days=back)).isoformat() for back in range(since_days)][::-1]
        series = {day: per_day.get(day, 0) for day in window}
        total = sum(series.values())
        return {
            "window_days": str(since_days),
            "window_start": window[0],
            "window_end": window[-1],
            "merges_total": str(total),
            "merges_per_day_mean": f"{total / since_days:.2f}",
            "per_day_series": ";".join(f"{day}:{count}" for day, count in series.items()),
        }

    return Reading(
        key="merges_per_day",
        label="④ 并树/日",
        values=snapshot(),
        provenance=Provenance(
            kind="git",
            coordinates=("git::log_since_subjects_and_merge_subject_ruler",),
            excerpts=(f"git log --since={since_days}.days.00:00 --date=short --format=%ad<US>%s",),
            recheck=snapshot,
        ),
    )


# ==================== 🔴 红线：读 markdown 的用例占比 ====================

@dataclass(frozen=True)
class ShareCounts:
    denominator: int
    direct_numerator: int
    helper_numerator: int
    upper_bound_numerator: int


def _module_constant_literals(tree: ast.Module) -> dict[str, set[str]]:
    table: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if value is None:
                continue
            literals = _string_constants(value)
            for target in targets:
                if isinstance(target, ast.Name):
                    table.setdefault(target.id, set()).update(literals)
    return table



def _call_is_doc_read(call: ast.Call, constants: Mapping[str, set[str]]) -> bool:
    func = call.func
    direct = isinstance(func, ast.Name) and func.id in DOC_READ_FUNCTIONS
    attr = isinstance(func, ast.Attribute) and func.attr in DOC_READ_METHODS
    if not (direct or attr):
        return False
    literals = set(_string_constants(call))
    for sub in ast.walk(call):
        if isinstance(sub, ast.Name) and sub.id in constants:
            literals |= constants[sub.id]
    return bool(_doc_literals(literals))


def _body_has_doc_literal(node: ast.AST, constants: Mapping[str, set[str]]) -> bool:
    literals = set(_string_constants(node))
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in constants:
            literals |= constants[sub.id]
    return bool(_doc_literals(literals))


def _functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    found: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append(node)
    return found


def _direct_doc_readers(functions: Sequence[ast.AST], constants: Mapping[str, set[str]]) -> set[str]:
    return {
        node.name
        for node in functions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_call_is_doc_read(call, constants) for call in ast.walk(node) if isinstance(call, ast.Call))
    }


def _closure_of_doc_readers(
    functions: Sequence[ast.AST], constants: Mapping[str, set[str]], seeds: set[str]
) -> set[str]:
    """把「调了读盘 helper」的函数也收进来：不动点迭代，谁经过 helper 读到 md 就算谁。"""
    callers = {
        node.name: {
            sub.func.id for sub in ast.walk(node) if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
        }
        for node in functions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    readers = set(seeds)
    changed = True
    while changed:
        changed = False
        for name, called in callers.items():
            if name not in readers and called & readers:
                readers.add(name)
                changed = True
    return readers


def count_markdown_readers(repo: Path) -> ShareCounts:
    denominator = 0
    direct = 0
    helper = 0
    upper = 0
    for path in _py_files(repo, "tests"):
        tree = _parse(path)
        if tree is None:
            continue
        constants = _module_constant_literals(tree)
        functions = _functions(tree)
        seeds = _direct_doc_readers(functions, constants)
        closure = _closure_of_doc_readers(functions, constants, seeds)
        for node in functions:
            if not node.name.startswith("test_"):
                continue
            denominator += 1
            body_direct = node.name in seeds
            in_closure = node.name in closure
            if body_direct:
                direct += 1
            if in_closure:
                helper += 1
            if in_closure or _body_has_doc_literal(node, constants):
                upper += 1
    return ShareCounts(denominator, direct, helper, upper)


def _percent(numerator: int, denominator: int) -> str:
    return f"{100.0 * numerator / denominator:.2f}%"


def build_share_reading(counts: ShareCounts, *, coordinates: Sequence[str], excerpts: Sequence[str], recheck: Callable[[], Mapping[str, str]]) -> Reading:
    if counts.denominator <= 0:
        return Reading(
            key="markdown_share",
            label="🔴 红线·读 markdown 的用例占比",
            values={
                name: NOT_MEASURED
                for name in (
                    "direct_numerator",
                    "helper_numerator",
                    "upper_bound_numerator",
                    "denominator",
                    "direct_percent",
                    "helper_percent",
                    "upper_bound_percent",
                )
            },
            provenance=Provenance(
                kind="fs",
                coordinates=tuple(coordinates),
                excerpts=tuple(excerpts) or ("(no test modules found)",),
                recheck=recheck,
            ),
            status=NOT_MEASURED,
            reason="ZERO_DENOMINATOR::tests/** 里没有一枚 test_ 函数",
        )
    return Reading(
        key="markdown_share",
        label="🔴 红线·读 markdown 的用例占比",
        values={
            "direct_numerator": str(counts.direct_numerator),
            "helper_numerator": str(counts.helper_numerator),
            "upper_bound_numerator": str(counts.upper_bound_numerator),
            "denominator": str(counts.denominator),
            "direct_percent": _percent(counts.direct_numerator, counts.denominator),
            "helper_percent": _percent(counts.helper_numerator, counts.denominator),
            "upper_bound_percent": _percent(counts.upper_bound_numerator, counts.denominator),
        },
        provenance=Provenance(
            kind="fs",
            coordinates=tuple(coordinates),
            excerpts=tuple(excerpts) or ("ast::tests_markdown_reader_scan",),
            recheck=recheck,
        ),
    )


def measure_markdown_share(repo: Path) -> Reading:
    def snapshot() -> Mapping[str, str]:
        counts = count_markdown_readers(repo)
        reading = build_share_reading(
            counts,
            coordinates=("ast::tests_markdown_reader_scan", "fs::tests_py_glob"),
            excerpts=("Path(...)/open(...)/read_text(...) with a docs/** or *.md literal",),
            recheck=snapshot,
        )
        return reading.values

    counts = count_markdown_readers(repo)
    return build_share_reading(
        counts,
        coordinates=("ast::tests_markdown_reader_scan", "fs::tests_py_glob"),
        excerpts=("Path(...)/open(...)/read_text(...) with a docs/** or *.md literal",),
        recheck=snapshot,
    )


# ==================== 出处复算闸（造数即红的落点） ====================

def _excerpts_are_present(repo: Path, reading: Reading) -> str | None:
    if reading.provenance is None or reading.provenance.kind != "doc":
        return None
    haystacks: list[str] = []
    for coordinate in reading.provenance.coordinates:
        relative, _, _symbol = coordinate.partition("::")
        path = repo / relative
        if not path.is_file():
            return f"CITED_FILE_ABSENT::{coordinate}"
        haystacks.append(path.read_text(encoding="utf-8", errors="replace"))
    joined = "\n".join(haystacks)
    excerpts = [excerpt for excerpt in reading.provenance.excerpts if not excerpt.startswith("(")]
    known = _known_commits(repo, [sha for excerpt in excerpts for sha in SHA_TOKEN.findall(excerpt)])
    for excerpt in excerpts:
        if excerpt not in joined:
            return f"EXCERPT_NOT_IN_CITED_FILE::{excerpt[:60]}"
        phantom = [sha for sha in SHA_TOKEN.findall(excerpt) if sha not in known]
        if phantom:
            return f"PHANTOM_SHA::{phantom[0]}"
    return None


def verify_reading(repo: Path, reading: Reading) -> list[str]:
    """MEASURED 必须当场复算得出同一个数；NOT_MEASURED 不许夹带数字。违约就点名。"""
    faults: list[str] = []
    if reading.status == NOT_MEASURED:
        smuggled = {name: value for name, value in reading.values.items() if value != NOT_MEASURED}
        if smuggled:
            faults.append(f"NUMBERS_UNDER_NOT_MEASURED::{reading.key}::{sorted(smuggled)}")
        if not reading.reason:
            faults.append(f"UNREASONED_NOT_MEASURED::{reading.key}")
        return faults
    if reading.status != MEASURED:
        return [f"UNKNOWN_STATUS::{reading.key}::{reading.status}"]
    provenance = reading.provenance
    if provenance is None or not provenance.coordinates:
        return [f"UNPROVEN_READING::{reading.key}::{dict(reading.values)}"]
    for coordinate in provenance.coordinates:
        if LINE_COORDINATE.search(coordinate):
            faults.append(f"LINE_NUMBER_COORDINATE::{reading.key}::{coordinate}")
    if not callable(provenance.recheck):
        faults.append(f"NOT_RECOMPUTABLE::{reading.key}")
        return faults
    try:
        fresh = dict(provenance.recheck())
    except Exception as error:  # noqa: BLE001 - 复算炸了就是一次红，必须点名
        faults.append(f"RECHECK_RAISED::{reading.key}::{type(error).__name__}::{error}")
        return faults
    for name, value in reading.values.items():
        if name not in fresh:
            faults.append(f"FIELD_VANISHED::{reading.key}::{name}")
        elif fresh[name] != value:
            faults.append(f"DRIFT::{reading.key}.{name}::{value}!={fresh[name]}")
    excerpt_fault = _excerpts_are_present(repo, reading)
    if excerpt_fault:
        faults.append(f"{excerpt_fault}::via::{reading.key}")
    return faults


# ==================== 渲染 ====================

def _row(index: int, total: int, reading: Reading, faults: Sequence[str]) -> str:
    if faults:
        joined = " | ".join(faults)
        return f"[{index}/{total}] {reading.label} | {reading.key} = RED :: {joined}"
    body = " ".join(f"{name}={value}" for name, value in reading.values.items())
    tail = "" if reading.status == MEASURED else f" reason={reading.reason}"
    source = " ,".join(reading.provenance.coordinates) if reading.provenance else "none"
    return f"[{index}/{total}] {reading.label} | {reading.key} = {reading.status}{tail} | {body} | 出处 {source}"


def render_report(
    readings: Mapping[str, Reading],
    *,
    repo: Path,
    head: str,
    generated_at: str,
    elapsed: Callable[[], float],
) -> tuple[list[str], int]:
    """一行一枚量具，读数与出处同栏；末尾再交一段 ``key=value`` 对账行。

    秒数在复算跑完之后才取，所以 ``meta.self_runtime_s`` 是「整把尺」的钱，含验伪。
    """
    total = len(REQUIRED_COLUMNS)
    rows: list[str] = []
    exit_code = EXIT_GREEN
    for index, (key, label, _hint) in enumerate(REQUIRED_COLUMNS, start=1):
        reading = readings.get(key)
        if reading is None:
            exit_code = EXIT_RED
            rows.append(f"[{index}/{total}] {label} | {key} = RED :: MISSING_COLUMN::{key}")
            continue
        if reading.key != key:
            exit_code = EXIT_RED
            rows.append(f"[{index}/{total}] {label} | {key} = RED :: MISKEYED_COLUMN::{reading.key}")
            continue
        faults = verify_reading(repo, reading)
        if faults:
            exit_code = EXIT_RED
        rows.append(_row(index, total, reading, faults))
    present = {reading.key for reading in readings.values()}
    for key in sorted(present - {item[0] for item in REQUIRED_COLUMNS}):
        exit_code = EXIT_RED
        rows.append(f"UNDECLARED_COLUMN::{key}")
    self_runtime_s = elapsed()
    if self_runtime_s > SELF_RUNTIME_LIMIT_S:
        exit_code = EXIT_RED
        rows.append(f"SELF_RUNTIME_EXCEEDED::{self_runtime_s:.2f}s > {SELF_RUNTIME_LIMIT_S:.0f}s")

    lines: list[str] = [
        "R682 · 元健康 KPI 量具（四数一红线·全离线·零 import app）",
        f"repo={repo} head={head} generated_at={generated_at} self_runtime_s={self_runtime_s:.2f}",
    ]
    lines.extend(rows)

    kv: list[str] = [
        f"meta.schema={SCHEMA_VERSION}",
        f"meta.head={head}",
        f"meta.generated_at={generated_at}",
        f"meta.self_runtime_s={self_runtime_s:.2f}",
        f"meta.exit={exit_code}",
    ]
    for key, label, _hint in REQUIRED_COLUMNS:
        reading = readings.get(key)
        if reading is None:
            kv.append(f"{key}.status=MISSING_COLUMN")
            continue
        kv.append(f"{key}.status={reading.status}")
        if reading.reason:
            kv.append(f"{key}.reason={reading.reason}")
        for name, value in reading.values.items():
            kv.append(f"{key}.{name}={value}")
    lines.append("")
    lines.append("# machine-readable 对账行（与上一班直接 diff，不再手抄进散文）")
    lines.extend(kv)
    lines.append("")
    lines.append("GREEN" if exit_code == EXIT_GREEN else "RED")
    return lines, exit_code


def build_readings(repo: Path, *, recent_commits: int = RECENT_COMMITS_DEFAULT, since_days: int = SINCE_DAYS_DEFAULT) -> dict[str, Reading]:
    readings = {
        "product_face": measure_product_face(repo, recent_commits),
        "merges_per_day": measure_merges_per_day(repo, since_days),
        "ledger_bytes": measure_ledger_bytes(repo),
        "validation_wallclock": measure_validation_wallclock(repo),
        "markdown_share": measure_markdown_share(repo),
    }
    return {key: readings[key] for key, _label, _hint in REQUIRED_COLUMNS}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R682 · 元健康 KPI 量具：四数一红线")
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--recent-commits", type=int, default=RECENT_COMMITS_DEFAULT)
    parser.add_argument("--since-days", type=int, default=SINCE_DAYS_DEFAULT)
    arguments = parser.parse_args(argv)

    started = time.perf_counter()
    head = _head_sha(arguments.repo)
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    readings = build_readings(
        arguments.repo,
        recent_commits=arguments.recent_commits,
        since_days=arguments.since_days,
    )
    lines, exit_code = render_report(
        readings,
        repo=arguments.repo,
        head=head,
        generated_at=generated_at,
        elapsed=lambda: time.perf_counter() - started,
    )
    for line in lines:
        print(line)
    sys.stdout.flush()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
