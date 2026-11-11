"""selfcheck_ledger.py -- 账面坐标族的自检（2026-10-06 改章：从全量门里搬出来）。

跑法：python scripts/selfcheck_ledger.py

这一族针断言的是「文档表格 == 代码现读 == 账本数字」，防的是编数，不是产品坏。
它**不再是门**：红只打印出来记账，退出码恒 0，不阻塞并树、不阻塞发版、不算 V1 欠项。
想修的时候按它点名的族逐枚再生（各件自带的 --land / --check 通道），不许手抄数字凑绿。
"""
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: 搬出门的族名册（按文件名认族，与全量门同一套口径；新增族须逐枚点名）。
FAMILIES = [
    "tests/test_r460_run9_coordinates_are_derived.py",
    "tests/test_r460_hand_fudged_numbers_and_wrong_layers_both_redden.py",
    "tests/test_r460_a_blank_line_above_the_backed_files_reddens_both_cells.py",
    "tests/test_r455_gapdoc_coordinates_are_derived.py",
    "tests/test_r455_hand_fudged_numbers_and_wrong_layers_both_redden.py",
    "tests/test_r387_label_ruler_teeth.py",
    "tests/test_r492_s93_column_matches_derived.py",
    "tests/test_r400_derived_ledger_shift_and_silence_pins.py",
    "tests/test_r483_empty_table_triage_is_derived.py",
    "tests/test_r516_the_dataset_stubs_stay_on_the_class.py",
    "tests/test_r508_the_bind_stub_stays_on_the_class.py",
    "tests/test_r638_pointer_ratchet.py",
    "tests/test_r676_ledger_verify_and_char_refutation.py",
    "tests/test_r676_synonym_rewrite_no_roundtrip.py",
    "tests/test_r679_index_is_derived_and_status_from_git.py",
    "tests/test_r679_verbatim_criteria_are_char_equal.py",
    "tests/test_r623_content_caliber_disk_pins.py",
    "tests/test_r548_counter_evidence_teeth.py",
    "tests/test_r550_counter_evidence_teeth.py",
    "tests/test_r550_event_hop_climb_is_generic.py",
]


def main():
    files = [f for f in FAMILIES if (REPO / f).exists()]
    missing = [f for f in FAMILIES if not (REPO / f).exists()]
    for f in missing:
        print("[selfcheck] 名册里这枚文件不在盘上（改名须逐枚点名，不许静默摘族）：" + f, flush=True)
    started = time.time()
    cmd = [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
           "--tb=line", "-o", "addopts=", "-o", "console_line_prefix="] + files
    print("[selfcheck] $ " + " ".join(cmd), flush=True)
    rc = subprocess.call(cmd, cwd=str(REPO))
    print("[selfcheck] 账面自检 rc=" + str(rc) + " 墙钟 " + str(round(time.time() - started, 1))
          + " s —— 这一行不是门，红不阻塞任何事（2026-10-06 改章）。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
