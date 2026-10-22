# -*- coding: utf-8 -*-
"""R540 反证件：把三条通道各摘歪一次，看**在册的钉会不会红**，看完逐字节还回去。

三把刀（派工词⑥，至少两把；这里三把，每条通道各一枚）：

  K1 `app/rag/ocr.py`：`OCR_ENGINE_MODULE` 指到一枚不存在的模块
     ⇒ 期望 `tests/test_r540_scan_offline.py` 红（引擎身份那枚静态钉当场红），
        并且读数件的扫描件腿必须改口成 `ocr-degraded` + 「本地 OCR 引擎不可用」——
        降级腿要点名，不许把"没跑成"说成"这页没字"。
  K2 `app/rag/loader.py`：扫描页判定的 AND 摘成 OR（`chars < threshold or has_image`）
     ⇒ 期望 `test_pages_with_a_text_layer_never_reach_the_ocr_channel` 与混合件那枚当场红：
        判据④ 的"有文本层的页一个字都不许再走 OCR"必须是**可失败**的断言，不是一句口径。
  K3 `app/rag/spreadsheets.py`：`CSV_SUFFIXES` 摘成空元组
     ⇒ 期望 `tests/test_r540_table_sheet_offline.py` 的 csv 那几枚红（分派出口按后缀走，
        后缀一撤，`.csv` 就该在 `load_document` 那一句 `raise ValueError` 上出声）。

🔴 本件**会**就地改写 `app/rag/**` 三枚文件的其中一枚（这正是反证要的形状），改完立刻还原：
  摘前/摘后/还原后各交一枚 sha256 前 12，三者不闭合就 rc=4 出声。全程只在这枚工作树里动手，
  主树 `企业智脑/` 一字节不碰；跑法见 `--help`。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FAILED_LINE = re.compile(r"^(FAILED|ERROR)\s+(\S+)")

PYTEST_ARGS = ["-o", "addopts=", "-p", "no:cacheprovider", "--tb=no", "-q", "-rf"]

KNIVES: dict[str, dict] = {
    "K1": {
        "title": "OCR 引擎名指歪（不存在的模块）",
        "file": "app/rag/ocr.py",
        "old": 'OCR_ENGINE_MODULE = "rapidocr_onnxruntime"',
        "new": 'OCR_ENGINE_MODULE = "r540_engine_absent_here"',
        "pytest": ["tests/test_r540_scan_offline.py"],
        "readout_case": "scan",
        "expect": "至少一枚钉红，且降级腿点名引擎不可用",
    },
    "K2": {
        "title": "扫描页判定 AND 摘成 OR（有图就当扫描页）",
        "file": "app/rag/loader.py",
        "old": "chars < threshold and has_image",
        "new": "chars < threshold or has_image",
        "pytest": ["tests/test_r540_scan_offline.py"],
        "readout_case": "control",
        "expect": "对照件/混合件那两枚必须红（文本层页被送进 OCR）",
    },
    "K3": {
        "title": "`.csv` 从电子表格后缀里撤掉",
        "file": "app/rag/spreadsheets.py",
        "old": 'CSV_SUFFIXES = (".csv",)',
        "new": 'CSV_SUFFIXES = ()',
        "pytest": ["tests/test_r540_table_sheet_offline.py"],
        "readout_case": "csv",
        "expect": "csv 那几枚钉必须红（load_document 在分派出口出声拒绝）",
    },
}


def sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def run(command: list[str]) -> dict:
    proc = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    failures = [match.group(2) for match in (FAILED_LINE.search(line) for line in output.splitlines()) if match]
    counted = re.findall(r"(\d+ (?:passed|failed|error|deselected|skipped)[^\n=]*)", output)
    return {
        "command": " ".join(command),
        "rc": proc.returncode,
        "failed": failures,
        "summary": counted[-1].strip() if counted else "",
        "tail": [line for line in output.splitlines() if line.strip()][-8:],
    }


def readout_json(case: str, out: Path) -> dict:
    command = [sys.executable, "-X", "utf8", "scripts/r540_readout.py", "--out", str(out), "--case", case]
    proc = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        return {"command": " ".join(command), "rc": proc.returncode, "tail": (proc.stdout + proc.stderr).splitlines()[-6:]}
    payload = json.loads(proc.stdout)
    return {"command": " ".join(command), "rc": 0, "case": payload["cases"][case]}


def tamper(knife: dict, payload: str) -> None:
    path = REPO_ROOT / knife["file"]
    text = path.read_bytes().decode("utf-8")
    if text.count(knife["old"]) != 1:
        raise SystemExit(f"{knife['file']} 里锚点不唯一：{text.count(knife['old'])} 处")
    path.write_bytes(text.replace(knife["old"], knife["new"]).encode("utf-8"))


def apply_knife(name: str, out: Path, python: str) -> dict:
    knife = KNIVES[name]
    path = REPO_ROOT / knife["file"]
    original = path.read_bytes()
    before = hashlib.sha256(original).hexdigest()[:12]
    result: dict = {"knife": name, "title": knife["title"], "file": knife["file"], "sha_before_12": before, "expect": knife["expect"]}
    try:
        tamper(knife, "")
        result["sha_tampered_12"] = sha12(path)
        result["tampered_differs"] = result["sha_tampered_12"] != before
        pytest_commands = [[python, "-X", "utf8", "-m", "pytest", target, *PYTEST_ARGS, "--basetemp", str(out / f"pytest-{name}")] for target in knife["pytest"]]
        result["pytest"] = [run(command) for command in pytest_commands]
        if knife["readout_case"]:
            reading = readout_json(knife["readout_case"], out)
            case = reading.get("case") or {}
            result["readout"] = {
                "command": reading["command"],
                "rc": reading["rc"],
                "tail": reading.get("tail", []),
                "source_counts": case.get("source_counts"),
                "ocr_attempted": case.get("ocr_attempted"),
                "ocr_available": case.get("ocr_available"),
                "degradation_sentence": (case.get("degradation_sentence") or "")[:160],
                "degradation_notes": [line[:120] for line in (case.get("degradation_notes") or [])][:4],
                "loader_body_chars": case.get("loader_body_chars"),
                "warning_lines": [line for line in (case.get("logs") or []) if "WARNING" in line][:4],
                "pages": [
                    {key: value for key, value in page.items() if key in {"page", "source", "note", "ocr_elapsed_ms"}}
                    for page in (case.get("pages") or [])
                ],
            }
    finally:
        path.write_bytes(original)
        after = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        result["sha_restored_12"] = after
        result["restored_byte_identical"] = after == before
    # 还原之后同名件必须立刻复跑成绿：这是"摘的是别人、伤的不是盘面"的凭据
    result["post_restore_recheck"] = [
        run([python, "-X", "utf8", "-m", "pytest", target, *PYTEST_ARGS, "--basetemp", str(out / f"pytest-{name}-post")])
        for target in knife["pytest"]
    ]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R540 反证：摘歪 -> 看钉红不红 -> 逐字节还原")
    parser.add_argument("--out", required=True, help="样本目录（先跑 scripts/r540_samples.py --out 同一个）")
    parser.add_argument("--knife", default="all", help="K1 / K2 / K3 / all")
    parser.add_argument("--python", default=sys.executable, help="跑 pytest 与读数件的解释器")
    args = parser.parse_args(argv)
    out = Path(args.out).expanduser().resolve()
    chosen = list(KNIVES) if args.knife == "all" else [item.strip().upper() for item in args.knife.split(",")]
    unknown = [item for item in chosen if item not in KNIVES]
    if unknown:
        raise SystemExit(f"未知刀号：{unknown}")
    ledgers = [apply_knife(name, out, args.python) for name in chosen]
    print(json.dumps({"tool": "scripts/r540_refutation.py", "knives": ledgers}, ensure_ascii=False, indent=2))
    dirty = [item["knife"] for item in ledgers if not item.get("restored_byte_identical")]
    if dirty:
        print("R540 反证未闭合，这些刀没还回去：" + "、".join(dirty), file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())