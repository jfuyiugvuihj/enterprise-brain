"""R679 · 判据 3／5 的钉：待派池工单里的判据原文必须与源文件逐字符对得上。

形状照 tests/test_r132_contract_followup_sync.py：pathlib／re／subprocess，不 import app，全离线。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TICKETS = REPO / "docs" / "tickets"
RULER = REPO / "scripts" / "tickets_index.py"

sys.path.insert(0, str(RULER.parent))
import tickets_index as ruler  # noqa: E402

# 本单开工时向总控在册的待派池取来的号列（来源见 docs/testing/r679-2026-10-05.md）
POOL = ["R665", "R667", "R668", "R669", "R670", "R673", "R674", "R675",
        "R676", "R677", "R678", "R681", "R683", "R684"]
HAND_SIGNED = ["R679", "R680", "R682", "R686"]


def cards() -> list[ruler.Ticket]:
    return [ruler.Ticket(path) for path in ruler.ticket_files(TICKETS)]


def machine_cards() -> list[ruler.Ticket]:
    return [card for card in cards() if card.specs]


def run_ruler(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RULER), *args], capture_output=True, text=True, encoding="utf-8")


def copy_tickets(tmp_path: Path) -> Path:
    target = tmp_path / "tickets"
    shutil.copytree(TICKETS, target)
    return target


def test_pool_has_one_file_per_number():
    """判据 3：待派池每一号各一枚 docs/tickets/RNNN.md，一枚不多一枚不少。"""
    numbers = sorted({card.number for card in machine_cards()})
    assert numbers == sorted(set(POOL))
    assert len(numbers) == 14


def test_verbatim_blocks_are_char_equal_to_source():
    """判据 3：逐字块与源文件逐字符相等，且是源文件里的一段连续原文。"""
    checked = 0
    for card in machine_cards():
        for spec, block in zip(card.specs, card.blocks):
            source_text = ruler.read_source(REPO, spec.split("::")[1])
            assert ruler.extract_source(REPO, spec) == block, f"{card.number} 对不上源文件：{spec}"
            assert block in source_text, f"{card.number} 的逐字块不是源文件里的连续原文：{spec}"
            assert len(block) >= 20, f"{card.number} 的逐字块太短，不像判据原文"
            checked += 1
    assert checked == 14


def test_generated_tickets_carry_the_three_named_sections():
    """判据 3：每枚工单都要带写域／禁区／交付清单三段。"""
    for card in machine_cards():
        text = card.path.read_text(encoding="utf-8")
        assert "## 判据原文（逐字·一个字不许改）" in text, card.path.name
        assert "## 禁区（踩线即退回）" in text, card.path.name
        assert "## 交付清单" in text, card.path.name
        assert len(card.domain) >= 3, f"{card.path.name}: 写域少于三格"
        assert card.hand_signed is False


def test_hand_signed_tickets_stay_untouched():
    """总控亲签的四枚不许被本单改写：它们仍不该带机器字段。"""
    by_number = {card.number: card for card in cards()}
    for number in HAND_SIGNED:
        assert by_number[number].hand_signed is True, f"{number} 被塞进了机器字段"
        assert by_number[number].specs == []


def test_on_disk_char_change_names_which_ticket_and_block(tmp_path):
    """判据 5 的反证牙：改掉盘上那份工单的判据原文一格 ⇒ 非零退出并点名哪一号哪一块。"""
    tickets = copy_tickets(tmp_path)
    victim = tickets / "R673-gpu-honest-declaration.md"
    lines = victim.read_text(encoding="utf-8").split("\n")
    body = next(i for i, line in enumerate(lines) if i and lines[i - 1].startswith("```verbatim"))
    assert "容器内" in lines[body], lines[body]
    lines[body] = lines[body].replace("容器内", "容器里", 1)
    victim.write_bytes("\n".join(lines).encode("utf-8"))
    result = run_ruler("--verify", "--tickets-dir", str(tickets))
    assert result.returncode == ruler.EXIT_VERBATIM, result.stdout
    assert "R673 第 1 块" in result.stdout, result.stdout


def test_tampered_provenance_predicate_is_shape_red(tmp_path):
    """出处谓词被改到源文件里取不到 ⇒ 形状红，同样点名那一号。"""
    tickets = copy_tickets(tmp_path)
    victim = tickets / "R681-generated-doc-section-diff.md"
    text = victim.read_text(encoding="utf-8").replace("::- **R681**：", "::- **R681** ;", 1)
    assert text != victim.read_text(encoding="utf-8")
    victim.write_bytes(text.encode("utf-8"))
    result = run_ruler("--verify", "--tickets-dir", str(tickets))
    assert result.returncode == ruler.EXIT_SHAPE, result.stdout
    assert "R681" in result.stdout