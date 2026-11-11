"""R679 · 判据 1／2 的钉：索引是生成物，状态只能由 git 现查。

形状照 tests/test_r132_contract_followup_sync.py：只用 pathlib／re／subprocess，
不 import app，全离线，不读工作区脏净。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TICKETS = REPO / "docs" / "tickets"
INDEX = TICKETS / "index.tsv"
RULER = REPO / "scripts" / "tickets_index.py"
COLUMNS = "号\t状态\t写域\t基点\t凭据出处"

sys.path.insert(0, str(RULER.parent))
import tickets_index as ruler  # noqa: E402


def run_ruler(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RULER), *args], capture_output=True, text=True, encoding="utf-8")


def copy_tickets(tmp_path: Path, name: str = "tickets") -> Path:
    target = tmp_path / name
    shutil.copytree(TICKETS, target)
    return target


def test_ruler_only_asks_git_for_log_and_cat_file():
    """状态只许由 git 现查——本尺只许问 `git log` 与 `git cat-file`，不许读此刻盘面。"""
    source = RULER.read_text(encoding="utf-8")
    wrapped = re.findall(r'git\(repo, "([a-z-]+)"', source)
    direct = re.findall(r'"git", "-C", str\(repo\), "([a-z-]+)"', source)
    assert wrapped and direct
    assert set(wrapped) <= {"log", "cat-file"}, wrapped
    assert set(direct) <= {"cat-file"}, direct
    for banned in ("status --porcelain", "diff --numstat", "dirty"):
        assert banned not in source, f"生成器里出现了把「此刻盘面」当判据的谓词：{banned}"

def test_index_header_is_the_five_named_columns():
    header = INDEX.read_text(encoding="utf-8").split("\n")[0]
    assert header == COLUMNS


def test_regenerated_index_is_byte_equal_to_disk():
    """判据 1：现场重跑生成器，产物与盘上那份逐字节相等。"""
    result = run_ruler("--check")
    assert result.returncode == ruler.EXIT_OK, result.stdout + result.stderr


def test_status_is_exactly_landed_or_queued():
    rows = ruler.parse_tsv(INDEX.read_text(encoding="utf-8"))
    assert rows
    assert {row[1] for row in rows} <= {ruler.LANDED, ruler.QUEUED}
    table = ruler.landing_commits(REPO)
    for row in rows:
        if row[1] == ruler.LANDED:
            assert row[0] in table and row[3] == table[row[0]][0][:12]
        else:
            assert row[0] not in table


def test_landed_sha_tooth_names_the_ticket(tmp_path):
    """判据 2 的牙：把一枚 LANDED 的 7..12 位 sha 换成不存在的 sha ⇒ 必须红并点名那一号。"""
    tickets = copy_tickets(tmp_path)
    rows = ruler.parse_tsv((tickets / "index.tsv").read_text(encoding="utf-8"))
    text = (tickets / "index.tsv").read_text(encoding="utf-8")
    landed = next(row for row in rows if row[1] == ruler.LANDED and text.count(row[3]) == 1)
    tampered = text.replace(landed[3], "deadbeefcafe", 1)
    assert tampered != text
    (tickets / "index.tsv").write_bytes(tampered.encode("utf-8"))
    result = run_ruler("--verify", "--tickets-dir", str(tickets))
    assert result.returncode == ruler.EXIT_STATUS, result.stdout
    assert landed[0] in result.stdout
    assert "现取不到任何提交" in result.stdout


def test_unmodified_copy_stays_green(tmp_path):
    """正控：同一把尺对没改过的盘上副本必须绿，否则上面那枚牙是假牙。"""
    tickets = copy_tickets(tmp_path)
    result = run_ruler("--verify", "--tickets-dir", str(tickets))
    assert result.returncode == ruler.EXIT_OK, result.stdout


def test_hand_edited_status_row_is_drift(tmp_path):
    """判据 1 的牙：手改索引一格状态 ⇒ --check 红，并点名差在哪一行。"""
    tickets = copy_tickets(tmp_path)
    index = tickets / "index.tsv"
    lines = index.read_text(encoding="utf-8").split("\n")
    position = next(i for i, line in enumerate(lines) if f"\t{ruler.QUEUED}\t" in line)
    number = lines[position].split("\t")[0]
    lines[position] = lines[position].replace(f"\t{ruler.QUEUED}\t", f"\t{ruler.LANDED}\t")
    index.write_bytes("\n".join(lines).encode("utf-8"))
    result = run_ruler("--check", "--tickets-dir", str(tickets))
    assert result.returncode == ruler.EXIT_DRIFT, result.stdout
    assert "索引第" in result.stdout and number in result.stdout


def test_dropped_row_is_named_as_missing(tmp_path):
    tickets = copy_tickets(tmp_path)
    index = tickets / "index.tsv"
    lines = index.read_text(encoding="utf-8").split("\n")
    dropped = lines[3].split("\t")[0]
    del lines[3]
    index.write_bytes("\n".join(lines).encode("utf-8"))
    result = run_ruler("--verify", "--tickets-dir", str(tickets))
    assert result.returncode != ruler.EXIT_OK
    assert dropped in result.stdout


def test_generated_ledger_carries_no_line_number_coordinates():
    """交付第 5 条：本单货（工单正文与索引本体）里不许出现 文件:数字 形态的行号。"""
    problems = ruler.check_pointers(REPO, TICKETS, [ruler.Ticket(p) for p in ruler.ticket_files(TICKETS)])
    assert problems == []