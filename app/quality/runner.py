import json
import os
from pathlib import Path

from app.quality.eval import evaluate_evaluation_set, format_approval_line

#: R123 甲案：批准账本 = 采集适配器写的侧车。`EVAL_SIDECAR` 是采集期就有的那把旗子，
#: `EVAL_APPROVAL_LEDGER` 让收窗复盘时能另指一份（比如把 run6 的侧车改名存档）。
APPROVAL_LEDGER_ENV_KEYS = ("EVAL_APPROVAL_LEDGER", "EVAL_SIDECAR")


def resolve_approval_ledger(environ: dict | None = None) -> str | None:
    """按环境变量找批准账本；一个都没设就回 None（报告里就不加那两把尺，也不印空数）。"""
    env = os.environ if environ is None else environ
    for key in APPROVAL_LEDGER_ENV_KEYS:
        value = str(env.get(key) or "").strip()
        if value:
            return value
    return None


def _load_answers(path: str | Path) -> dict[str, dict]:
    answers = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            item = json.loads(line)
            answers[str(item["id"])] = item
    return answers


def run_recorded_evaluation(
    fixture_path: str | Path,
    answers_path: str | Path,
    output_path: str | Path,
    approval_ledger: str | Path | None = None,
) -> dict:
    """把一份 answers 跑成报告；给了批准账本就同时印出甲案与旧口径两把尺。

    不显式传账本时走 `resolve_approval_ledger()`：收窗那条命令（`scripts/run_quality_evaluation.py`
    在本单写域外，不许改）只带三个位置参数，所以甲案的那一行靠环境变量认账本。
    """
    answers = _load_answers(answers_path)

    def answer_fn(row):
        return answers.get(
            str(row["id"]),
            {"answer": "", "evidence": [], "latency_ms": None},
        )

    ledger = approval_ledger if approval_ledger is not None else resolve_approval_ledger()
    report = evaluate_evaluation_set(fixture_path, answer_fn, approval_ledger=ledger)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    line = format_approval_line(report)
    if line:
        # 判据 4：报告要多印的那一行。CLI 自己那行在写域外，所以这一行由 app/quality 印，
        # 顺带存进 report["approval_line"]，谁渲染报告都拿得到，不必再拼一遍字符串。
        print(line)
    return report
