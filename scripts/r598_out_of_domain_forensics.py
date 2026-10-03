"""R598 · 域外硬编码取证：把 doc-17 落成甲，写域外那两枚 R401 件的**哪几格**会红——实调，不读源码猜。

【为什么要这件】
判据⑤只许我动两枚守卫（`tests/test_evaluation_report.py`、
`tests/test_r94_eval_evidence_coverage.py`）。而 `tests/test_r401_unscorable_rows_are_named_not_dropped.py`
把「丙案 19 枚 / 分母 86」写死在断言里：任何一枚丙→甲都要重录它，那是总控的授权面，不是执行层的。
「会挡路」这句结论必须给成**凭据**，所以要实调：
  · 对照组 = 盘面行（今天全绿，证明红的唯一来源是那枚甲，不是那两枚件本身坏了）；
  · 实验组 = 影子行（同一套函数、同一把尺，只把 doc-17 按待授权账换成甲）。
🔴 本件零写入：只 import 那两枚件的测试函数并直接调用，不碰它们的字节，不碰题源，不碰语料。

【怎么读输出】
每条一行：`件::函数  对照=绿/红  实验=绿/红  → 实验组那句红话术（原样，不转述）`。
实验组红而对照组绿的那些格，就是「要落甲必须先重录」的清单；总控若裁「不落甲」，本件继续当
「为什么一枚都没救」的凭据。
"""
from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import sys
import tempfile
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_REL = Path("scripts") / "r598_disposition_ledger.py"
PENDING_REL = Path("scripts") / "r598_pending_jia.py"
DOMAIN_OUTSIDE_TESTS = (
    Path("tests") / "test_r401_unscorable_rows_are_named_not_dropped.py",
    Path("tests") / "test_r401_anchor_provenance_is_derived.py",
)


def _load(name: str, path: Path, unique: bool = False):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _call(func, r401_module, rows):
    """按签名喂参数：r401 → 件模块，rows → 行表，tmp_path → 临时目录；其余参数（capsys 等）跳过。"""
    kwargs = {}
    wanted = inspect.signature(func).parameters
    for name in wanted:
        if name in ("r401", "r401_module"):
            kwargs[name] = r401_module
        elif name == "rows":
            kwargs[name] = rows
        elif name == "tmp_path":
            kwargs[name] = Path(tempfile.mkdtemp(prefix="r598_forensics_"))
        else:
            return None, "skipped:参数 {0} 无法在取证脚本里注入".format(name)
    try:
        func(**kwargs)
    except AssertionError as exc:
        frames = traceback.extract_tb(sys.exc_info()[2])
        hit = [frame for frame in frames if frame.name == func.__name__]
        line = hit[-1].lineno if hit else (frames[-1].lineno if frames else "?")
        first = str(exc).splitlines()[0] if str(exc).strip() else "(无消息的 assert)"
        return "red", "{0}:{1} {2}".format(func.__name__, line, first[:220])
    except Exception as exc:  # noqa: BLE001 - 取证要把任何异常如实记下来
        return "error", "{0}: {1}".format(type(exc).__name__, str(exc)[:220])
    return "green", ""


def run(root: Path = REPO_ROOT) -> dict:
    ledger = _load("r598_ledger_for_forensics", root / LEDGER_REL)
    pending = _load("r598_pending_for_forensics", root / PENDING_REL)
    dd = pending.deps(root)
    shipped = ledger.read_rows(root)
    shadow_rows, _proofs = pending.planned_rows(root, shipped, dd["cov"], dd["r401"])
    report = {"control": [], "experiment": [], "files": []}
    for rel in DOMAIN_OUTSIDE_TESTS:
        module = _load("forensics_{0}".format(rel.stem), root / rel)
        #: 测试件里的 r401 是 pytest fixture（函数对象），取不到实例；这里把**同一份脚本**再 Exec
        #: 一次当成参数递进去，被测函数拿到的是同一把尺（同一份 DETAILS/UNSCORABLE 账）。
        real_r401 = _load("r401_script_for_forensics", root / "scripts" / "r401_anchor_provenance.py")
        names = [n for n in dir(module) if n.startswith("test_")]
        report["files"].append({"file": rel.as_posix(), "tests": len(names)})
        for name in sorted(names):
            func = getattr(module, name)
            if not callable(func):
                continue
            control, control_note = _call(func, real_r401, shipped)
            experiment, experiment_note = _call(func, real_r401, shadow_rows)
            entry = {
                "case": "{0}::{1}".format(rel.stem, name),
                "control": control,
                "experiment": experiment,
                "experiment_note": experiment_note,
                "control_note": control_note,
            }
            report["control"].append(entry)
            if experiment != control:
                report["experiment"].append(entry)
    return report


def render(report: dict) -> str:
    out = ["R598 域外硬编码取证（实调，零写入；对照=盘面行 / 实验=影子行把 doc-17 换成甲）"]
    for item in report["files"]:
        out.append("  被调件 {0}：{1} 枚测试函数".format(item["file"], item["tests"]))
    out.append("")
    out.append("  实验组与对照组**结果不同**的格（＝要落甲必须先重录的清单）：")
    if not report["experiment"]:
        out.append("    （空——说明甲的落地不会碰这两枚件，本单的「域外卡死」结论作废）")
    for item in report["experiment"]:
        out.append("    {0}  对照={1} → 实验={2}".format(
            item["case"], item["control"], item["experiment"]))
        out.append("        红话术：{0}".format(item["experiment_note"] or item["control_note"]))
    skipped = [item["case"] for item in report["control"] if item["control"] is None]
    out.append("")
    out.append("  无法在取证脚本里注入参数的格（跳过，如实点名不装绿）：{0}".format(
        "、".join(skipped) if skipped else "无"))
    broken = [item["case"] for item in report["control"] if item["control"] == "red"]
    out.append("  对照组就红的格（与本单无关，属盘面既有病，逐枚点名）：{0}".format(
        "、".join(broken) if broken else "无"))
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="R598 域外硬编码取证（零写入）")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--json", dest="json_path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    report = run(root)
    print(render(report))
    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    #: 本件是取证不是判卷：无论清单长短都出数（落甲之前它是「为什么一枚没救」，落甲之后它是
    #: 「当时点的就是这几格」的留痕。要不要把它升成钉，由总控裁。
    return 0


if __name__ == "__main__":
    sys.exit(main())