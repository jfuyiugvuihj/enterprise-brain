"""R461 · runbook 改口钉：P-18 的处方只许指向那枚件，不许再抄命令（判据④）。

这枚钉防的是**下一班**：R461 之前，本文 §2 那一行、§清单第 8 步、以及「两相之间复跑」那一条
抄的都是手写命令，于是每班照抄一次、每班重踩一次（09-25 踩的是引号，09-28 踩的是取错口令）。
「订正三」第 1 条那段是**病历**，不是处方：它必须留着那句错误形态（`WRONGPASS` 与 `| wc -l`
的假零形状就是它记下来的），但它给的处方也已经改成指向那枚件。所以这条钉分三格：

  1 处方三处（§2 的 P-18 行、§清单第 8 步、两相 bullet）必须出现 `scripts/eval_window_answer_cache_gate.py`，
    且**一个字的 redis-cli / wc -l 都不许再出现** —— 出现即红，那就是下一班漂移的开始；
  2 病历那一处（订正三第 1 条）必须同时留着错误形态与指向那枚件的处方；
  3 这份账本的行尾形状是恒量：全 CRLF、零裸 LF、零孤独 CR、零 U+FFFD、文件尾以 CRLF 收尾。
    🔴 钉的是形状恒量，不钉字节数与行数 —— 那两枚每追加一次就会变，钉死就是造一枚永久红的假门。

离线：只读本文一个文件，不改它一个字节。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNBOOK = REPO / "docs" / "handoff" / "2026-09-17-eval-real-run-runbook.md"
GATE = "scripts/eval_window_answer_cache_gate.py"

#: 四处锚点：每处都必须唯一存在，锚点丢了这枚钉就该红（不是静默放行）。
PRESCRIPTIONS = {
    "§2 前置表 P-18 行": "| **P-18** | **开窗前清掉答案缓存**",
    "§清单第 8 步": "8. **P-18 缓存清零**",
    "两相之间复跑那一格": "**两相之间必须复跑 P-18**",
}
POSTMORTEM = "1. **P-18 的旧命令跑不通，而且失败方式是假零**"
#: 处方里再出现这些形状，就是有人把命令重新抄回了正文。
RECOPIED_SHAPES = ("redis-cli", "wc -l", "xargs", "--no-auth-warning", "$RG")


def lines() -> list[str]:
    return RUNBOOK.read_bytes().decode("utf-8").splitlines(keepends=True)


def lone(key: str) -> str:
    matches = [line for line in lines() if key in line]
    assert len(matches) == 1, f"锚点在 runbook 里出现 {len(matches)} 次，本该唯一：{key}"
    return matches[0]


def prescription_findings(step8_line: str | None = None, phase_line: str | None = None,
                          table_row: str | None = None) -> list[str]:
    """处方三格：没指向件＝一条问题；把命令抄回来＝一条问题。可喂改写行做反证。"""
    body = {
        "§2 前置表 P-18 行": table_row if table_row is not None else lone(PRESCRIPTIONS["§2 前置表 P-18 行"]),
        "§清单第 8 步": step8_line if step8_line is not None else lone(PRESCRIPTIONS["§清单第 8 步"]),
        "两相之间复跑那一格": phase_line if phase_line is not None else lone(PRESCRIPTIONS["两相之间复跑那一格"]),
    }
    problems: list[str] = []
    for name, text in body.items():
        if GATE not in text:
            problems.append(f"{name} 没有指向 {GATE}")
        for shape in RECOPIED_SHAPES:
            if shape in text:
                problems.append(f"{name} 又把命令抄回了正文：{shape!r}")
    return problems


def test_the_four_anchors_are_still_unique() -> None:
    for key in list(PRESCRIPTIONS.values()) + [POSTMORTEM]:
        assert len([line for line in lines() if key in line]) == 1, key


def test_prescriptions_point_at_the_gate_and_copy_no_command() -> None:
    problems = prescription_findings()
    assert problems == [], "; ".join(problems)


def test_the_step8_prescription_reads_as_an_exit_code() -> None:
    """第 8 步的判据必须是退出码，不再是「该数必须为 0」—— 那枚零正是两班假绿的形状。"""
    step8 = lone(PRESCRIPTIONS["§清单第 8 步"])
    assert "退出码 **0**" in step8, step8
    assert "该数必须为 **0**" not in step8 and "→ 必须 **0**" not in step8, step8


def test_the_postmortem_keeps_the_specimen_and_names_the_tool() -> None:
    """病历那一格：错误形态（WRONGPASS / wc -l 假零）与「处方是那枚件」必须同时在。"""
    text = lone(POSTMORTEM)
    assert GATE in text, text
    for specimen in ("WRONGPASS", "wc -l", "PONG", "EB_EVAL_PASSWORD", "REDIS_PASSWORD"):
        assert specimen in text, f"病历丢了形态 {specimen!r}：下一班就没法知道自己踩的是哪一根"
    assert "一个枚数都不报" in text, text


def shape_findings(raw: bytes) -> list[str]:
    """这份账本的行尾形状恒量：全 CRLF、零裸 LF、零孤独 CR、零 U+FFFD、文件尾以 CRLF 收尾。"""
    problems: list[str] = []
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n")
    cr = raw.count(b"\r")
    if crlf != lf:
        problems.append(f"混进裸 LF：CRLF {crlf} / LF {lf}")
    if crlf != cr:
        problems.append(f"混进孤独 CR：CRLF {crlf} / CR {cr}")
    if "\ufffd" in raw.decode("utf-8", "replace"):
        problems.append("读出 U+FFFD：编码被写坏了")
    if not raw.endswith(b"\r\n"):
        problems.append("文件尾不再以 CRLF 收尾")
    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append("写进了 BOM")
    return problems


def test_the_line_ending_shape_stays_a_constant() -> None:
    assert shape_findings(RUNBOOK.read_bytes()) == []


def test_counter_evidence_copying_a_hand_command_back_reddens_the_pin(tmp_path: Path) -> None:
    """反证：把第 8 步换回原来那条手写命令 ⇒ 钉必须点名两处（没指向件 + 抄回命令）。"""
    old_step8 = (
        "8. **P-18 缓存清零**：`docker exec -e RG='<口令原文>' enterprise-brain-redis-1 sh -lc "
        "'redis-cli -a \"$RG\" --no-auth-warning --scan --pattern \"answer:*\" | wc -l'` → 必须 **0**。\r\n"
    )
    problems = prescription_findings(step8_line=old_step8)
    assert any("没有指向" in item for item in problems), problems
    assert any("又把命令抄回了正文" in item for item in problems), problems
    assert re.search(r"wc -l", old_step8), old_step8


def test_counter_evidence_dropping_the_pointer_reddens_every_prescription(tmp_path: Path) -> None:
    """反证：三格处方同时不指向那枚件 ⇒ 三格各红一条，钉不是只看一眼第 8 步。"""
    problems = prescription_findings(step8_line="8. 见第 12 步。\r\n",
                                     phase_line="    - 两相之间复跑缓存清零。\r\n",
                                     table_row="| **P-18** | 见 §清单 | 见 §清单 | 见 §清单 |")
    assert len(problems) == 3, problems
    assert all("没有指向" in item for item in problems), problems


def test_counter_evidence_a_lone_cr_in_the_ledger_reddens_the_shape_pin() -> None:
    """反证：账本里冒出一枚孤独 CR ⇒ 形状那格必须点名（逐行写回的红线，不是修辞）。"""
    damaged = RUNBOOK.read_bytes().replace(b"\r\n", b"\r", 1)
    problems = shape_findings(damaged)
    assert any("孤独 CR" in item for item in problems), problems


def test_counter_evidence_a_bare_lf_and_a_lost_tail_newline_redden_the_shape_pin() -> None:
    """反证：整文件 split+join 那种写法会把 CRLF 打成裸 LF、把文件尾的换行吃掉 ⇒ 两格都红。"""
    raw = RUNBOOK.read_bytes()
    problems = shape_findings(raw.replace(b"\r\n", b"\n"))
    assert any("裸 LF" in item for item in problems), problems
    assert any("文件尾" in item for item in problems), problems
    truncated = shape_findings(raw[:-2])
    assert any("文件尾" in item for item in truncated), truncated
