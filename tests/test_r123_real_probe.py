"""R123 判据 6：真机单题探针 —— 挂起 → 按契约批准 → 拿终答，全程只跑 approval-05 一题。

默认 **跳过**：这条要打真模型、真容器，跑分窗口纪律不允许顺手跑。总控特批一次时这样开：

    $env:EB_PROBE = "1"
    $env:EB_ENV_FILE = "<deploy/.env.server 的绝对路径>"   # 只读 EB_EVAL_PASSWORD 这一行
    & "<venv 绝对路径>" -m pytest -q -s tests/test_r123_real_probe.py

口径（写死，免得被当成跑分）：
  * 这是**功能探针**不是计时样本：一题、不占 P95、不进任何分数。
  * 凭据只从 `EB_ENV_FILE` 指向的文件里读进环境变量，🔴 口令值不落任何文件、回执与日志
    （`test_receipt_never_carries_the_password` 当场自证）。
  * 产物全部写到 `EB_PROBE_DIR`（默认系统临时目录）——仓外，零残留。
  * 探针跑的是交付里那份采集适配器本体（`scripts/eval_transport_ask_v2.py`），不是另写一套。
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import time
import urllib.request
from urllib.parse import urlparse
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval_transport_ask_v2.py"
FIXTURE_105 = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"
PROBE_ID = "approval-05"
#: 真路径：chat.router 挂在 /api/v1 上（app/main.py:80）。工单原文写的 /api/v1/chat/approve
#: 在实机上打成 404（08-21 第一投实测），这里按容器的 openapi 钉回 /api/v1/approve。
APPROVAL_PATH = "/api/v1/approve"

pytestmark = pytest.mark.skipif(
    os.getenv("EB_PROBE") != "1",
    reason="真机探针要总控特批：设 EB_PROBE=1 才跑（一题、真模型、真容器）",
)


def _out_dir() -> Path:
    target = Path(os.getenv("EB_PROBE_DIR") or (Path(os.environ.get("TEMP", ".")) / "r123-probe"))
    target.mkdir(parents=True, exist_ok=True)
    return target


def _env_value(name: str) -> str:
    """只读地取部署环境文件里的一个键；取不到就整条判据报失败，不许猜口令。"""
    path = Path(os.getenv("EB_ENV_FILE", ""))
    if not path.is_file():
        pytest.fail("EB_ENV_FILE 没指向一个真文件 ⇒ 判据 6 无法执行（不许拿假凭据交差）")
    for raw in path.read_bytes().decode("utf-8", "replace").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip().strip('"').strip("'")
    pytest.fail(f"{path.name} 里没有 {name} 这一行")
    return ""


def _fixture_row(row_id: str) -> dict:
    for line in FIXTURE_105.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            row = json.loads(line)
            if str(row.get("id")) == row_id:
                return row
    raise AssertionError(f"{row_id} 不在 105 题夹具里")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Witness:
    """独立于适配器自己的记账：把每一次 HTTP 的方法/路径/状态码与原始 SSE 帧抄一份。

    只记路径与状态码，🔴 不记请求体 —— 登录体里带着口令。
    """

    def __init__(self, opener):
        self.opener = opener
        self.calls: list[dict] = []
        self.frames: dict[str, list[str]] = {}
        self._current = None

    def open(self, request, timeout=None):
        """先记账再打网络：批准被打成 4xx 时也要留下状态码（第一投就是这么丢的）。"""
        path = urlparse(request.full_url).path
        sink: list[str] = []
        call = {"path": path, "method": request.get_method(), "status": None, "frames": sink}
        self.calls.append(call)
        self.frames[path + "#" + str(len(self.calls))] = sink
        try:
            response = self.opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            call["status"] = exc.code
            raise
        except OSError as exc:
            call["error"] = type(exc).__name__
            raise
        call["status"] = getattr(response, "status", None)
        return _Tee(response, sink)

    def statuses(self, path):
        return [call["status"] for call in self.calls if call["path"] == path]


class _Tee:
    def __init__(self, inner, sink):
        self._inner = inner
        self._sink = sink

    def __iter__(self):
        for raw in self._inner:
            self._sink.append(raw.decode("utf-8", "replace"))
            yield raw

    def read(self):
        return self._inner.read()

    def close(self):
        return self._inner.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _redact(text: str, secret: str) -> str:
    """脱敏：口令、Bearer、绝对盘路径、连号数字一律打掉；只留人话与结构。"""
    out = text.replace(secret, "***") if secret else text
    out = re.sub(r"(Bearer\s+)\S+", r"\1***", out)
    out = re.sub(r"[A-Za-z]:\\\\[^\s\"”]+", "<path>", out)
    out = re.sub(r"\b\d{4,}\b", "<n>", out)
    return out


def _park_frames(frames: list[str]) -> list[str]:
    """把原始 SSE 帧压成"事件名 + data"两行式；超长帧（带正文/证据全文）只留前 400 字。"""
    kept = []
    for line in frames:
        stripped = line.strip()
        if stripped.startswith("event: "):
            kept.append(stripped)
        elif stripped.startswith("data: ") and len(stripped) <= 400:
            kept.append(stripped)
        elif stripped.startswith("data: "):
            kept.append(stripped[:400] + " …（长帧已截）")
    return kept


@pytest.fixture(scope="module")
def probe():
    password = _env_value("EB_EVAL_PASSWORD")
    out = _out_dir()
    os.environ["EVAL_USERNAME"] = "evalbot"
    os.environ["EVAL_PASSWORD"] = password
    os.environ["EVAL_BASE_URL"] = os.getenv("EVAL_BASE_URL", "http://127.0.0.1:8001")
    os.environ["EVAL_SIDECAR"] = str(out / "sidecar-probe.jsonl")
    module = _load("r123_probe_transport", SCRIPT_PATH)
    module.SIDECAR = Path(os.environ["EVAL_SIDECAR"])
    witness = _Witness(module._OPENER)
    module._OPENER = witness
    row = _fixture_row(PROBE_ID)
    started = time.time()
    payload = module.transport(row)
    records = [json.loads(line) for line in
               module.SIDECAR.read_text(encoding="utf-8").splitlines() if line.strip()]
    ask_frames = []
    approve_frames = []
    for call in witness.calls:
        if call["path"] == "/api/v1/ask":
            ask_frames = call["frames"]
        elif call["path"] == APPROVAL_PATH:
            approve_frames = call["frames"]
    result = {"transport": module, "row": row, "payload": payload, "record": records[-1],
              "witness": witness, "out": out, "secret": password, "sidecar": module.SIDECAR,
              "ask_frames": ask_frames, "approve_frames": approve_frames,
              "wall_seconds": round(time.time() - started, 1)}
    try:
        yield result
    finally:
        os.environ.pop("EVAL_PASSWORD", None)  # 口令只活在这一个进程的环境里


def test_probe_reached_a_terminal_answer_through_the_real_approve_route(probe):
    record, witness = probe["record"], probe["witness"]
    assert record["id"] == PROBE_ID
    assert record["pre_kind"] == "hitl", f"这一题没挂起（pre_kind={record['pre_kind']}）⇒ 探针选错题"
    assert witness.statuses(APPROVAL_PATH), "探针根本没打 /approve ⇒ 判据 1 没被实测"
    assert record["kind"] == "approved_ok", f"批准结果={record['kind']}：{record['approval_error']}"
    assert record["approved"] is True and record["approval_http_status"] == 200
    assert probe["payload"]["answer"].strip() and \
        probe["payload"]["answer"] != record.get("pre_answer")


def test_probe_receipt_written_outside_the_repo(probe):
    probe["out"].mkdir(parents=True, exist_ok=True)
    record, payload = probe["record"], probe["payload"]
    # 真机上 sources 行的键是 worker/source/... （app/api/v1/chat.py 的 canonical sources 事件），
    # 第一版按 source_name/locator 取 ⇒ 全 null。按键交集投影，认不得的键不硬编。
    keep = ("worker", "source", "source_name", "locator", "page", "sheet", "chart_type")
    evidence = [{key: item.get(key) for key in keep if key in item}
                for item in payload["evidence"][:5]]
    receipt = {
        "probe_id": PROBE_ID,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": probe["transport"].BASE_URL,
        "wall_seconds": probe["wall_seconds"],
        "pre_kind": record["pre_kind"],
        "pre_answer_frame": _redact(str(record.get("pre_answer")), probe["secret"]),
        "pre_answer_chars": record["pre_answer_chars"],
        "ask_events": _redact(" ".join(_park_frames(probe["ask_frames"])), probe["secret"]),
        "approve_http_status": record["approval_http_status"],
        "approve_rounds": record["approval_rounds"],
        "approved": record["approved"],
        "kind": record["kind"],
        "terminal_answer_head": _redact(payload["answer"][:80], probe["secret"]),
        "terminal_answer_chars": record["answer_chars"],
        "evidence_n": record["evidence_n"],
        "evidence_head": _redact(json.dumps(evidence, ensure_ascii=False), probe["secret"]),
        "answer_events_in_recovery_stream": sum(
            1 for line in probe["approve_frames"] if line.startswith("event: text")),
        "sidecar_row": {key: value for key, value in record.items()
                        if key != "pre_answer"},
    }
    target = probe["out"] / "receipt.json"
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    probe["receipt"] = receipt
    assert target.is_file() and REPO_ROOT not in target.parents
    print("\n[R123 PROBE] " + json.dumps(receipt, ensure_ascii=False))


def test_receipt_never_carries_the_password(probe):
    secret = probe["secret"]
    blob = "\n".join(path.read_text(encoding="utf-8", errors="replace")
                     for path in sorted(probe["out"].glob("*")))
    assert secret and secret not in blob, "回执或侧车里出现了口令明文 ⇒ 立刻停手上报"
    assert "Authorization" not in blob


def test_probe_kept_the_run_window_discipline_for_one_question_only(probe):
    witness = probe["witness"]
    asks = [call for call in witness.calls if call["path"] == "/api/v1/ask"]
    approves = [call for call in witness.calls if call["path"] == APPROVAL_PATH]
    assert len(asks) == 1 and len(approves) >= 1, "探针只许一题；打了第二轮就说明收不住"
    assert all("payload" not in call for call in witness.calls)  # 请求体（含口令）一个字节都没记
    assert witness.calls[0]["path"] == "/api/v1/login"
    assert probe["sidecar"].is_file() and REPO_ROOT not in probe["sidecar"].parents
