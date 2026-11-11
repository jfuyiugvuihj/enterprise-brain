# -*- coding: utf-8 -*-
"""R676 交付第 1／4 条的钉：判据原文逐字进单，改一个字就点名哪一号哪一块。

形状照 ``tests/test_r132_contract_followup_sync.py`` 与 ``tests/test_r679_*``：
只用 ``pathlib``／``re``／``subprocess``，**不 import** ``app``，全离线。
本件只读 ``scripts/tickets_index.py`` 与 ``docs/tickets/**``，一枚字节都不写它们
（名册派生器归总控管，本单写域明令不许动）。
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TICKETS = REPO / "docs" / "tickets"
RULER = REPO / "scripts" / "tickets_index.py"
CARD = TICKETS / "R676-synonym-rewrite-no-roundtrip.md"

sys.path.insert(0, str(RULER.parent))
import tickets_index as ruler  # noqa: E402

#: 本单判据原文里那一枚「同义词」——反证只改盘上副本，仓内原件一格不动。
VICTIM_WORD = "同义词"
SWAP_WORD = "近义词"


def run_ruler(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RULER), *args],
                          capture_output=True, text=True, encoding="utf-8")


def card_for_r676():
    for path in ruler.ticket_files(TICKETS):
        ticket = ruler.Ticket(path)
        if ticket.number == "R676":
            return ticket
    raise AssertionError("docs/tickets 里没有 R676 这一枚工单文件")


def copy_tickets(tmp_path: Path) -> Path:
    target = tmp_path / "tickets"
    shutil.copytree(TICKETS, target)
    return target


# ---------------------------------------------------------------------------
# 交付第 1 条：尺子在真树绿
# ---------------------------------------------------------------------------

def test_verify_is_green_on_this_tree():
    result = run_ruler("--verify")
    assert result.returncode == ruler.EXIT_OK, result.stdout + result.stderr
    assert "全部判据过" in result.stdout


def test_r676_block_is_char_equal_to_its_source_cell():
    """判据原文逐字符对得上源文件那一格（出处谓词由尺现读，本件不抄坐标）。"""
    ticket = card_for_r676()
    assert ticket.specs, "R676 没带逐字块"
    for spec, block in zip(ticket.specs, ticket.blocks):
        assert ruler.extract_source(REPO, spec) == block, f"出处对不上：{spec}"
        assert VICTIM_WORD in block, block
        assert len(block) >= 20, block


# ---------------------------------------------------------------------------
# 交付第 4 条：反证牙（改盘上副本的一处判据原文 ⇒ 非零退出并点名）
# ---------------------------------------------------------------------------

def test_one_char_change_in_the_copy_names_the_ticket_and_the_block(tmp_path):
    tickets = copy_tickets(tmp_path)
    victim = tickets / CARD.name
    lines = victim.read_text(encoding="utf-8").split("\n")
    body = next(index for index, line in enumerate(lines)
                if index and lines[index - 1].startswith("```verbatim"))
    assert VICTIM_WORD in lines[body], lines[body]
    lines[body] = lines[body].replace(VICTIM_WORD, SWAP_WORD, 1)
    victim.write_bytes("\n".join(lines).encode("utf-8"))

    result = run_ruler("--verify", "--tickets-dir", str(tickets))
    assert result.returncode == ruler.EXIT_VERBATIM, result.stdout
    assert "R676" in result.stdout, result.stdout
    assert "第 1 块" in result.stdout, result.stdout
    assert "不合" in result.stdout, result.stdout


def test_a_dropped_predicate_is_shape_red_and_names_the_ticket(tmp_path):
    """出处谓词被改到源文件取不到 ⇒ 红在形状那一格，同样点名 R676。"""
    tickets = copy_tickets(tmp_path)
    victim = tickets / CARD.name
    text = victim.read_text(encoding="utf-8")
    tampered = text.replace("::R47::判据（机器可验）", "::R47::判据（机器可验） ", 1)
    assert tampered != text
    victim.write_bytes(tampered.encode("utf-8"))

    result = run_ruler("--verify", "--tickets-dir", str(tickets))
    assert result.returncode in (ruler.EXIT_SHAPE, ruler.EXIT_VERBATIM), result.stdout
    assert "R676" in result.stdout, result.stdout


def test_the_untouched_copy_still_passes(tmp_path):
    """正控：原样拷一份再跑，尺子必须照绿——否则上面两枚红没有对照。"""
    tickets = copy_tickets(tmp_path)
    result = run_ruler("--verify", "--tickets-dir", str(tickets))
    assert result.returncode == ruler.EXIT_OK, result.stdout + result.stderr


#: 本文件装载那一刻（＝任何反证跑之前）仓内那枚工单的字节指纹。
CARD_SHA_AT_IMPORT = hashlib.sha256(CARD.read_bytes()).hexdigest()


def fenced_block_of(text: str) -> str:
    """取出 ```verbatim 围栏里的那一段（判据原文），行尾一律按 LF 读。"""
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("```verbatim"):
            inside = True
            continue
        if inside and line.startswith("```"):
            break
        if inside:
            out.append(line)
    assert out, "围栏里没读到东西"
    return "\n".join(out)


def test_the_refutations_never_write_the_repo_original():
    """反证只许发生在盘上副本：本文件跑完之后，仓内这枚工单的字节必须一字未动。"""
    assert hashlib.sha256(CARD.read_bytes()).hexdigest() == CARD_SHA_AT_IMPORT


def test_the_verbatim_block_still_equals_the_base_blob():
    """判据原文那一格相对 HEAD 的 blob 逐字符相等（文末追加段不许碰到它）。"""
    rel = "docs/tickets/" + CARD.name
    shown = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:{rel}"], capture_output=True)
    assert shown.returncode == 0, shown.stderr.decode("utf-8", "replace")
    base_block = fenced_block_of(shown.stdout.decode("utf-8"))
    disk_block = fenced_block_of(CARD.read_text(encoding="utf-8"))
    assert disk_block == base_block, "盘上那份判据原文与基点 blob 不是同一串字节"