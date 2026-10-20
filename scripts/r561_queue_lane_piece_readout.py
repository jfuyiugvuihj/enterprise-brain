"""R561：队列道「逐字片段」在**容器里**的那一遍读数（脚本本体，零产品码改动）。

来历（这条格子的账，不靠摘要）：R558（甲案投递面，并树 `5477645`）把 worker 内存账本接到
客户端每 3 s 就在读的 `GET /api/v1/queue/status/{request_id}` 上，`stream_pieces` 只在
`status == "processing"` 下发。它的判据① 只交到「**同进程**真路由真载荷」那一半（真
`ReliableQueue` ＋真 `deploy/queue_worker.py` 码体 ＋真 HTTP 门，底下是 `FakeRedis`）；
容器那一遍（真 Redis ＋ `REPORT_LANE_VIA_QUEUE=on` ＋独立 worker 进程）**至今没跑过**。
上一班把「纸面形状」当成「容器里也这么走」，烧掉一整扇窗（run10 作废，看板 §0 名册有账），
所以这一格不留给纸：本件是一枚**问出去并把每一发的原文存下来**的量具，不是一段散文。

三条纪律写在这里，不在注释里躲：

1. 🔴 **只读**。对 Redis／PostgreSQL／容器一个字都不写；不改 `.env`、不起服务、不重建容器。
   要跑它只需要栈已经起来、`REPORT_LANE_VIA_QUEUE=on`、`deploy/.env.server` 里那枚开关真在位。
   起容器与打模型都不是本件的动作（`--help` 也不会）。执行层不得自己起容器：那一遍由总控在
   开窗条件满足时（`scripts/r530_run10_window_preflight.py` 全绿）执行并回填凭据纸。
2. 🔴 **量不到不等于干净**（P-20 那句）。每一格只有三态：`PASS` / `FAIL` / `UNMEASURED`。
   任何一格落到 `UNMEASURED`，总退出码就是 2，而 2 **永远不是**「已通过」。把「取不到读数」
   折成 0 或折成绿，就是本件要消灭的那枚假绿。
3. 🔴 **零新口径**。`stream_pieces` 那九枚键、三枚 state、三枚 reason、五枚终态停表词、
   kind 名，一律抄自上游（`app/common/reliable_queue.py` 与 `app/api/v1/chat.py` 的字面，
   以及契约 `## Queue lane streaming pieces (R558)` 那一节），本件**不新增任何一枚**名字，
   也不许读出一个上游词表之外的 reason。字面抄在这里是为了让量具能被单独 import（与
   `scripts/eval_transport_ask_v2.py:398` 那句 `CORRECTION_STEP_TOOL` 同一族做法），
   两份字面是否还相等由 `tests/test_r561_readout_calibre_and_teeth.py` 现取推导来钉，
   不靠本件的注释自证。

读数落点：`docs/perf/raw/r561-<date>/`。逐发存**整份回执原文**（含那一发的
`stream_pieces` 原样 JSON），另存一份 `polls.jsonl` 索引与 `summary.json` 收尾账。
🔴 这一处与 runbook §8「跑分产物落仓外」是**两件事**：sidecar／帧账是评分输入，必须落仓外；
本件存的是「容器当时真吐了哪些字节」的凭据，判据① 明写落 `docs/perf/raw/`，
与 `run11c-2026-10-01/` 那一批同格。凭据纸里把这条界线原样写出来。

用法（总控窗内，一行一次，串行）：

    python scripts/r561_queue_lane_piece_readout.py --id report-01
    python scripts/r561_queue_lane_piece_readout.py --offline docs/perf/raw/r561-2026-10-01
    python scripts/r561_queue_lane_piece_readout.py --id report-01 --skip-provenance   # 只演形状，不出数

退出码：0 六格全 PASS / 1 至少一格 FAIL / 2 有格子量不到或量具自己没跑成（含 provenance 读不出）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ------------------------------------------------------------------ 上游字面（被钉，不被自证）
#: 轮询面与入队面：三扇门都是既有的，本件不开第二套。
LOGIN_PATH = "/api/v1/login"
ASK_PATH = "/api/v1/ask"
APPROVE_PATH = "/api/v1/approve"
STATUS_PATH = "/api/v1/queue/status/"
#: 增量面那枚键（契约 R558 节：只在 processing 下发）。
PIECE_FIELD = "stream_pieces"
#: 那一格的九枚键，逐枚（键名与枚数都由钉现取比对上游）。
PIECE_KEYS = ("state", "text", "cursor", "pieces", "chars",
              "discarded", "truncated", "legs", "reason")
PIECE_OK = "ok"
PIECE_ABSENT = "absent"
PIECE_UNREADABLE = "unreadable"
PIECE_STATES = (PIECE_ABSENT, PIECE_OK, PIECE_UNREADABLE)
#: reason 的封闭词表：出现第四枚字就是本件自创口径，判 FAIL 而不是判「没读数」。
PIECE_REASON_VOCAB = ("batch_payload_unparsable", "batch_schema_mismatch", "batch_seq_invalid")
#: 停表词表：五枚终态 ＋ 一枚「一步没走、在等人批准」。与
#: `scripts/eval_transport_ask_v2.py` 的 `_poll_queue` 同一族口径，一枚都不许多、一枚都不许少。
TERMINAL_STATUSES = ("done", "cancelled", "dead", "expired", "failed")
PARK_STATUS = "awaiting_approval"
#: 这一轮**根本没入队**（同步道答完了）——本件单独立名，绝不折进「零片」或「零发」。
BYPASS_KIND = "lane_bypassed_not_queued"
#: kind 名沿用上游量具那一张表（同名同义，本件不改口径）。
KIND_POLLED = "queued_polled"
KIND_APPROVED = "queued_approved"
KIND_NO_BYTES = "queued_done_no_bytes"
KIND_PARKED = "queued_awaiting_approval"
#: 只有这两枚 kind 的窗里，「一发正文都没取到」才可能是真话，其余 kind 一律 FAIL。
#: 停在到点／没有状态回复／挂起等批准／批准失败的那几形，正文压根没往增量面上走；
#: 空正文／取消／死信／过期／失败同理——那种窗里的形状读数不可采信。
#: 这一格判的是账齐不齐，不是投递对不对；名单只此两枚，不在这里手写第三枚。
KINDS_WITH_BYTES = (KIND_POLLED, KIND_APPROVED)
#: 上游两枚上限的名字与数值（只用于把读数说清，不用于放宽任何判定）。
LEDGER_LIMIT_NAME = "QUEUE_PIECE_LEDGER_LIMIT"
STORE_LIMIT_NAME = "PIECE_BATCH_LIMIT"
FLUSH_PIECES_NAME = "PIECE_FLUSH_PIECES"
FLUSH_SECONDS_NAME = "PIECE_FLUSH_SECONDS"
#: 判据① 那「至少三发」的下界——与 R558 同进程那枚钉同一枚数（它在 `len(seen) >= 3` 那一格）。
MIN_PROCESSING_OK_POLLS = 3
#: 六格的名字：交回、判读、凭据纸用同一张表，不许一处一个叫法。
CELLS = ("provenance", "growing", "caps_zero", "terminal_no_pieces",
         "zero_bypass_unreadable_retry", "poll_bookkeeping")
PASS, FAIL, UNMEASURED = "PASS", "FAIL", "UNMEASURED"
#: 默认问哪一题：报告档第一题。评测集只读，一个字节都不写回去。
DEFAULT_FIXTURE_REL = "tests/fixtures/business_evaluation_100.jsonl"
DEFAULT_QUESTION_ID = "report-01"
#: 容器名：backend 与 worker 各自一枚，provenance 两枚都要问（片段是 worker 产的，
#: 增量的读出面在 backend——只验其中一枚就等于没验这一路）。
CONTAINERS = ("enterprise-brain-backend-1", "enterprise-brain-worker-1")
IMAGE = "enterprise-brain:local"
LABEL = "org.opencontainers.image.revision"
#: 只有这一枚状态下发片段：产品那扇门与量具认的是同一个词，钉里引用这一枚、不抄字面。
LIVE_STATUS = "processing"
#: 三条读数路的叫法是本件自己的（routes 那本账才记命令原文）。
ROUTE_GIT = "git"
ROUTE_BUILD_INFO = "BUILD_INFO"
ROUTE_LABEL = "label"
#: 一枚看得像提交号的读数：7 到 40 位十六进制。缩写先解成 40 位，才谈得上逐字符。
REV_SHAPE = r"[0-9a-f]{7,40}"
#: provenance 不等时**唯一**正确的两条出口（判据② 明写的两枚坑，写成可读出的字面，
#: 由钉现取比对 `docker-compose.yml` 与 `tests/test_r255_env_documents_the_conversion.py`）。
REMEDIATION_RECREATE = ("docker compose --env-file deploy/.env.server up -d --force-recreate")
REMEDIATION_NOT_BUILD = ("不要 docker compose build backend：build: 只在 migrate 与 frontend 两格，"
                         "backend/worker/scheduler 共用 migrate 产出的 " + IMAGE + "，"
                         "对 backend 直接报 No services to build")


# ------------------------------------------------------------------------ 极小的工具面
def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _sha16(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def run(cmd, *, cwd=None, timeout=120):
    """跑一条外部命令，回 (rc, stdout+stderr)。跑不成就是 rc=2，不冒充「没有输出＝干净」。"""
    try:
        done = subprocess.run(list(cmd), cwd=str(cwd or ROOT), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 2, type(exc).__name__ + ": " + str(exc)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def git(*args, **kw):
    return run(["git", *args], **kw)


def docker(*args, **kw):
    return run(["docker", *args], **kw)


def load_question(fixture_rel: str, question_id: str) -> dict:
    """从评测集里按 id 现取那一行（整行原样，一个字不改），并记下它的 sha256。

    🔴 只读：本件从不向评测集写任何字节。取不到题号就是量不到，不许退化成「随便问一句」。
    """
    path = ROOT / fixture_rel
    if not path.is_file():
        raise FileNotFoundError("评测集不在盘上：" + fixture_rel)
    for line in path.read_bytes().decode("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if str(row.get("id", "")) == question_id:
            row["_line_sha256"] = hashlib.sha256(line.encode("utf-8")).hexdigest()
            row["_fixture_rel"] = fixture_rel
            return row
    raise KeyError("评测集里没有这枚题号：" + question_id)


# ---------------------------------------------------------------------------- HTTP 门（只读三扇）
def _no_proxy_opener():
    """空 dict = 无视 http_proxy/HTTPS_PROXY（runbook §6：本机 Clash 会劫 127.0.0.1）。"""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Session:
    """一枚最小的 Bearer 会话：与 `scripts/eval_transport_ask_v2.py` 同一扇门、同一个 token 口径。

    本件不绕过鉴权、不伪造 session、不直接调 `app.agents.orchestrator`——「跑分账号有权读
    自己的队列轮、并批自己挂起的那一轮」这句话必须靠真 HTTP 实测，抄近路就不是这句话了。
    """

    def __init__(self, base_url: str, opener=None) -> None:
        self.base = base_url.rstrip("/")
        self.opener = opener or _no_proxy_opener()
        self.token = ""
        self.relogins = 0

    def login(self, username: str, password: str) -> str:
        body = self._post_json(LOGIN_PATH, {"username": username, "password": password})
        self.token = str(body.get("token") or "")
        if not self.token:
            raise RuntimeError("login 响应里没有 token 键")
        return self.token

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        return headers

    def _post_json(self, path, payload):
        request = urllib.request.Request(self.base + path,
                                         data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                         headers=self._headers(), method="POST")
        with self.opener.open(request, timeout=float(os.getenv("R561_HTTP_TIMEOUT", "60"))) as resp:
            return json.loads(resp.read().decode("utf-8", "replace") or "{}")

    def poll_status(self, request_id: str, since: int, timeout: float):
        """读一发轮询面：回 (http_status, 原文 bytes, 解析后的 dict 或 None)。

        非 2xx／连不通／解不开**一律不是停表条件**（与 `_poll_queue` 口径②同一条）：
        瞬记一次抖动接着轮，绝不把一次网络抖动读成「这一轮结束了」。
        """
        path = STATUS_PATH + request_id + "?since=" + str(int(since))
        request = urllib.request.Request(self.base + path, headers=self._headers(), method="GET")
        try:
            with self.opener.open(request, timeout=timeout) as resp:
                raw = resp.read()
                status = resp.getcode()
        except urllib.error.HTTPError as exc:
            return exc.code, (exc.read() or b""), None
        except (urllib.error.URLError, OSError) as exc:
            return 0, ("transport: " + type(exc).__name__ + ": " + str(exc)).encode("utf-8"), None
        try:
            body = json.loads(raw.decode("utf-8", "replace") or "null")
        except json.JSONDecodeError:
            return status, raw, None
        if not isinstance(body, dict):
            return status, raw, None
        return status, raw, body

    def ask(self, question: str, session_id: str, idempotency_key: str, lane: str, timeout: float):
        """POST /api/v1/ask 并把那条 SSE 流读到关流，回 (events, queued 那一份 data 或 None)。

        队列道的形状是「流在入队口就关」：`queued` + 一帧 done（契约 R558 节抬头那段）。
        所以这一趟**没有** text 帧是它的形状，不是缺字——这句话判据③ 要用来分 bypass。
        """
        payload = {"message": question, "session_id": session_id,
                   "idempotency_key": idempotency_key}
        if lane:
            payload["lane"] = lane
        request = urllib.request.Request(self.base + ASK_PATH,
                                         data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                         headers=self._headers(), method="POST")
        events = []
        queued = None
        with self.opener.open(request, timeout=timeout) as resp:
            name = None
            data = None
            for line in resp:
                text = line.decode("utf-8", "replace").rstrip("\r\n")
                if text.startswith("event: "):
                    name = text[7:].strip()
                elif text.startswith("data: "):
                    try:
                        data = json.loads(text[6:])
                    except json.JSONDecodeError:
                        data = {}
                elif not text and name:
                    events.append(name)
                    if name == "queued":
                        queued = data or {}
                    name, data = None, None
        return events, queued

    def approve(self, session_id: str, timeout: float) -> int:
        """批准自己挂起的那一轮：同一个 session_id、同一个 token，回 HTTP 状态码。"""
        request = urllib.request.Request(self.base + APPROVE_PATH,
                                         data=json.dumps({"session_id": session_id,
                                                          "approved": True},
                                                         ensure_ascii=False).encode("utf-8"),
                                         headers=self._headers(), method="POST")
        try:
            with self.opener.open(request, timeout=timeout) as resp:
                resp.read()
                return int(resp.getcode())
        except urllib.error.HTTPError as exc:
            return int(exc.code)
        except (urllib.error.URLError, OSError):
            return 0


# --------------------------------------------------------------------------- 原文落盘（凭据面）
class Capture:
    """把每一发的**整份回执原文**存下来，另写一份可重放的索引。

    🔴 逐发存原文，不存「我解析后的样子」：判读以后要能对着一字节重算，凭据纸要能被人逐字核。
    `stream_pieces` 的原文 JSON 就在这一份里（本件不摘出来单独改写，也不按判读需要补键）。
    """

    def __init__(self, out_dir: Path) -> None:
        self.dir = Path(out_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index = self.dir / "polls.jsonl"
        #: rows 是**发数**，polls 是**清单本体**——判读吃后者，纸上的「共 N 发」吃前者。
        self.rows = 0
        self.polls: list = []

    def write_poll(self, *, sent_at: str, since: int, http_status: int,
                   raw: bytes, body, status: str) -> dict:
        self.rows += 1
        name = "%04d-%s.json" % (self.rows, status or "unreadable")
        (self.dir / name).write_bytes(raw)
        row = {"index": self.rows, "sent_at": sent_at, "since": int(since),
               "http_status": int(http_status), "raw_file": name, "raw_sha256": _sha16(raw),
               "status": status, "body": body,
               "has_piece_field": isinstance(body, dict) and PIECE_FIELD in body}
        with self.index.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.polls.append(row)
        return row

    def write_head(self, meta: dict) -> None:
        (self.dir / "head.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def write_summary(self, summary: dict) -> None:
        (self.dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_capture(out_dir) -> list:
    """读回一份存档：按发序返回行。目录不在／索引不在 ⇒ 抛，不返回空表冒充「零发」。"""
    path = Path(out_dir) / "polls.jsonl"
    if not path.is_file():
        raise FileNotFoundError("存档里没有 polls.jsonl：" + str(path))
    rows = []
    for line in path.read_bytes().decode("utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    if not rows:
        raise ValueError("存档是空的（polls.jsonl 零行）：" + str(path))
    return rows


# ---------------------------------------------------------------------------- 判读（纯函数，可离线喂）
def _cell(name, verdict, value, note, evidence=None):
    return {"cell": name, "verdict": verdict, "value": value, "note": note,
            "evidence": list(evidence or [])}


def _piece_of(row):
    body = row.get("body")
    if not isinstance(body, dict):
        return None
    piece = body.get(PIECE_FIELD)
    return piece if isinstance(piece, dict) else None


def judge_growing(rows):
    """判据① 那一格：≥3 发处于 processing 且 state==ok，且 chars 严格递增过。

    这一格只准读「正在跑的那一程」。只有一发读到字、到终态一次给全，是 R558 反证刀
    backfill 的形状——那一形在这里必须红（`len(set(chars)) >= 3` 就是它的落点）。
    """
    series = []
    for row in rows:
        if row.get("status") != LIVE_STATUS:
            continue
        piece = _piece_of(row)
        if piece is None or piece.get("state") != PIECE_OK:
            continue
        series.append({"index": row["index"], "chars": int(piece.get("chars") or 0),
                       "cursor": int(piece.get("cursor") or 0),
                       "text_chars": len(str(piece.get("text") or ""))})
    if len(series) < MIN_PROCESSING_OK_POLLS:
        return _cell("growing", FAIL if series or rows else UNMEASURED,
                     {"processing_ok_polls": len(series),
                      "required": MIN_PROCESSING_OK_POLLS},
                     "处于 processing 且 state==ok 的发数不够：递增这一格没有发生过", series)
    chars = [item["chars"] for item in series]
    cursors = [item["cursor"] for item in series]
    problems = []
    if chars != sorted(chars):
        problems.append("chars 倒退：" + repr(chars))
    if len(set(chars)) < MIN_PROCESSING_OK_POLLS:
        problems.append("整轮只读出一两个 chars 值，递增没有发生：" + repr(chars))
    if cursors != sorted(cursors):
        problems.append("cursor 倒退：" + repr(cursors))
    if len(set(cursors)) < MIN_PROCESSING_OK_POLLS:
        problems.append("cursor 只有不到三个值：" + repr(cursors))
    grew_chars = [b > a for a, b in zip(chars, chars[1:])]
    grew_cursor = [b > a for a, b in zip(cursors, cursors[1:])]
    if grew_chars != grew_cursor:
        problems.append("字数与游标不同涨同停（客户端会重拿同一截字或永远拿不到新字）："
                        + repr((chars, cursors)))
    verdict = PASS if not problems else FAIL
    return _cell("growing", verdict, {"processing_ok_polls": len(series), "chars": chars,
                                      "cursors": cursors,
                                      "distinct_chars": len(set(chars))},
                 "; ".join(problems) or ("递增成立：chars " + repr(chars) + " / cursor " + repr(cursors)),
                 series)


def judge_caps(rows):
    """判据①/② 那两枚上限：一题报告档远不到 512 与 1024，非 0 就是账错。

    🔴 非 0 不许读成「没有片段」：`discarded` 说的是 worker 内存账本丢的片，
    `truncated` 说的是增量表自己停止存正文之后又过了几批——两枚分开报，分开判。
    """
    seen = [(row["index"], int((_piece_of(row) or {}).get("discarded", 0) or 0),
             int((_piece_of(row) or {}).get("truncated", 0) or 0))
            for row in rows if _piece_of(row) is not None]
    if not seen:
        return _cell("caps_zero", UNMEASURED, {"polls_with_pieces": 0},
                     "一发片段读数都没取到：这两格是「量不到」，不是「都是 0」", [])
    bad = [item for item in seen if item[1] or item[2]]
    verdict = PASS if not bad else FAIL
    return _cell("caps_zero", verdict,
                 {"polls_with_pieces": len(seen),
                  "max_discarded": max(item[1] for item in seen),
                  "max_truncated": max(item[2] for item in seen),
                  "nonzero_polls": [item[0] for item in bad]},
                 "两枚上限逐发都为 0" if not bad else
                 "这两枚里至少一枚非 0，按截断读、不按「没有片段」读：" + repr(bad), seen)


def judge_terminal(rows):
    """判据①/②：终态那一发**不许出现** `stream_pieces`；非 processing 的每一发也不许出现。

    增量面是「正在长」那一截的表演，不是终态正文的第二份副本（契约 R558 节原文那两句）。
    """
    wrong = [row["index"] for row in rows
             if row.get("status") != LIVE_STATUS and row.get("has_piece_field")]
    terminal = [row for row in rows if row.get("status") in TERMINAL_STATUSES]
    if not terminal:
        return _cell("terminal_no_pieces", UNMEASURED,
                     {"terminal_polls": 0, "wrong_carriers": wrong},
                     "这一遍根本没读到终态那一发（停在挂起／到点／没读到状态）："
                     "「终态无键」这一格无从判定，不许折成通过", [])
    last = terminal[-1]
    if last.get("has_piece_field"):
        wrong.append(last["index"])
    verdict = PASS if not wrong else FAIL
    return _cell("terminal_no_pieces", verdict,
                 {"terminal_poll": last["index"], "terminal_status": last.get("status"),
                  "keys_in_terminal_body": sorted((last.get("body") or {}).keys()),
                  "wrong_carriers": wrong},
                 "终态那一发没有片段键，非 processing 的每一发也没有" if verdict == PASS else
                 "这些发带着 stream_pieces，而它们不是 processing：" + repr(wrong), [])


def judge_counts(rows, head):
    """判据③ 的三枚计数，逐枚点名：bypass／unreadable／重试。

    🔴 每一枚都分「量到了 0」与「压根没量到」：`failure` 键一发都不在，重试这一格就是
    UNMEASURED，绝不是零重试。词表外的一枚 reason 出现 ⇒ 那是自创口径，当场 FAIL。
    """
    problems, notes = [], {}
    events = list((head or {}).get("ask_events") or [])
    request_id = str((head or {}).get("request_id") or "")
    bypass = not request_id or "queued" not in events
    notes["bypass"] = {"named": BYPASS_KIND if bypass else "", "ask_events": events,
                       "request_id_present": bool(request_id)}
    if bypass:
        problems.append("bypass：这一题根本没入队（队列道被绕过），增量面没被问到位")

    unreadable_polls = []
    invented = []
    for row in rows:
        piece = _piece_of(row)
        if piece is not None and piece.get("state") == PIECE_UNREADABLE:
            unreadable_polls.append(row["index"])
            reason = str(piece.get("reason") or "")
            if reason not in PIECE_REASON_VOCAB:
                invented.append({"index": row["index"], "reason": reason})
    notes["unreadable"] = {"polls": unreadable_polls, "invented_reasons": invented,
                           "vocab": list(PIECE_REASON_VOCAB)}
    if unreadable_polls:
        problems.append("unreadable：这些发的片段表解不开（表在位而读不懂，不是「还没长出来」）："
                        + repr(unreadable_polls))
    if invented:
        problems.append("词表外 reason＝自创口径：" + repr(invented))

    attempts_series = []
    missing_failure = 0
    for row in rows:
        body = row.get("body") if isinstance(row.get("body"), dict) else {}
        failure = body.get("failure")
        if not isinstance(failure, dict):
            missing_failure += 1
            continue
        attempts_series.append({"index": row["index"],
                                "attempts": int(failure.get("attempts") or 0),
                                "last_error": failure.get("last_error")})
    retried = [item for item in attempts_series if item["attempts"] > 1
               or item["last_error"] not in (None, "")]
    notes["retry"] = {"series": attempts_series, "polls_without_failure_key": missing_failure,
                      "polls": len(rows)}
    if attempts_series and retried:
        problems.append("重试：这些发的 attempts/last_error 说这一轮被重跑过：" + repr(retried))
    unverifiable = not attempts_series
    #: 优先级写死：bypass／unreadable／词表外 reason／真重试 任何一枚在场都是 FAIL（那是量到了
    #: 的坏读数）；只有「其余都干净、而重试这一格压根没带回来」才落 UNMEASURED——量不到不是零。
    if bypass or unreadable_polls or invented or retried:
        verdict = FAIL
    elif unverifiable:
        verdict = UNMEASURED
        problems.append("重试这一格量不到：没有一发带回 failure 读数，"
                        "这不能读成零重试")
    else:
        verdict = PASS
    return _cell("zero_bypass_unreadable_retry", verdict,
                 {"bypass": bool(bypass), "unreadable_polls": unreadable_polls,
                  "invented_reasons": invented, "retried_polls": [item["index"] for item in retried],
                  "retry_measurable": bool(attempts_series)},
                 "; ".join(problems) or "三枚计数逐枚为 0，且三枚都是量到了的 0",
                 [notes])


def judge_bookkeeping(rows, head):
    """账那一格：这一遍有没有把「带正文的那种窗」跑完。

    🔴 只有落在 `KINDS_WITH_BYTES` 里的那两枚终账，「一发片段都没取到」才可能是真话；
    停在挂起／到点／批准失败／没有状态回复那一族的窗，增量面本来就不会有字，拿它的形状
    读数说「递增没发生」是误判，说「递增发生了」更是假话——那种窗一律 FAIL，不许混进 PASS。
    head.json 里没有 final_kind 就是量不到（UNMEASURED），绝不折成「零枚所以干净」。
    """
    final = str((head or {}).get("final_kind") or "")
    if not final:
        return _cell("poll_bookkeeping", UNMEASURED, {}, "head.json 里没有终账：量不到", [])
    bad_final = final not in KINDS_WITH_BYTES
    value = {"polls": len(rows), "blips": int((head or {}).get("blips", 0) or 0),
             "relogins": int((head or {}).get("relogins", 0) or 0),
             "approval_rounds": int((head or {}).get("approval_rounds", 0) or 0),
             "final_kind": final, "wait_ms": (head or {}).get("wait_ms"),
             "interval_ms": (head or {}).get("interval_ms")}
    return _cell("poll_bookkeeping", FAIL if bad_final else PASS, value,
                 "终账是 " + final + "：这一型根本没把字往增量面上送，形状读数不可采信"
                 if bad_final else "终账 " + final + "：这一窗是有正文的那一型", [])


def judge_provenance(head):
    """判据②：容器里的 rev 与主树 HEAD **逐字符**相等才许开窗；量不到就是量不到。"""
    block = (head or {}).get("provenance")
    if not isinstance(block, dict):
        return _cell("provenance", UNMEASURED, {}, "没有 provenance 读数（未跑或被跳过）", [])
    verdict = block.get("verdict")
    if verdict == PASS:
        return _cell("provenance", PASS, block.get("value"), "两枚容器的 rev 与主树 HEAD 逐字符相等", [])
    if verdict == FAIL:
        return _cell("provenance", FAIL, block.get("value"), block.get("note", ""), [])
    return _cell("provenance", UNMEASURED, block.get("value") or {},
                 block.get("note", "rev 取不到：这不能读成「镜像是新的」"), [])


def judge(rows, head=None) -> dict:
    """六格一起判，返回可原样落进 summary.json 的那一份账。"""
    cells = [judge_provenance(head), judge_growing(rows), judge_caps(rows),
             judge_terminal(rows), judge_counts(rows, head), judge_bookkeeping(rows, head)]
    return {"cells": {cell["cell"]: cell for cell in cells},
            "order": list(CELLS), "rc": overall(cells)}


def overall(cells) -> int:
    """退出码：0 全 PASS／1 至少一格 FAIL／2 至少一格量不到（2 永远不是通过）。"""
    verdicts = [cell["verdict"] for cell in cells]
    if UNMEASURED in verdicts:
        return 2
    return 1 if FAIL in verdicts else 0


# ----------------------------------------------------------------- provenance（开窗前的那道闸）
def host_head() -> dict:
    rc, out = git("rev-parse", "HEAD")
    rev = out.strip() if rc == 0 else ""
    return {"rc": rc, "rev": rev, "raw": out.strip(),
            "note": "" if rc == 0 and re.fullmatch(r"[0-9a-f]{40}", rev) else
                    "主树 HEAD 取不到（rc=%d）：%s" % (rc, out.strip()[:120])}


def rev_shape(rev) -> bool:
    """这一枚读数像不像提交号：不像就是量不到，绝不让它冒充「镜像是新的」。"""
    return bool(re.fullmatch(REV_SHAPE, str(rev or "")))


def container_head(container: str) -> dict:
    """容器里那一枚 rev，按三条路依次试，每条都把失败原因原样留下。

    🔴 不许只试一条就下结论：镜像里带不带 `.git` 是构建上下文决定的（`Dockerfile` 只 COPY
    `app/migrations/scripts/deploy` 并写 `/app/BUILD_INFO`），所以 `git rev-parse HEAD`
    在容器里**很可能**报 not a git repository。那一形不是「镜像落后」，也不是「镜像干净」，
    是这一条路量不到——本件接着试 BUILD_INFO 与 OCI label，三条路全哑就交 UNMEASURED。
    🔴 缩写（7 位起）先收下，由 provenance_gate 用 `resolve()` 解成 40 位再逐字符比；
    解不开就是解不开，绝不拿半截字面冒充「相等」。
    """
    routes = []
    rc, out = docker("exec", container, "git", "-C", "/app", "rev-parse", "HEAD")
    text = out.strip()
    if rc == 0 and rev_shape(text):
        routes.append({"route": "git rev-parse HEAD", "ok": True, "rev": text})
        return {"container": container, "rev": text, "route": ROUTE_GIT,
                "routes": routes, "note": ""}
    routes.append({"route": "git rev-parse HEAD", "ok": False, "rc": rc, "text": text[:160]})
    rc, out = docker("exec", container, "cat", "/app/BUILD_INFO")
    stamp = ""
    if rc == 0:
        for line in out.splitlines():
            if line.strip().startswith("revision="):
                stamp = line.split("=", 1)[1].strip()
        if rev_shape(stamp):
            routes.append({"route": "/app/BUILD_INFO", "ok": True, "rev": stamp})
            return {"container": container, "rev": stamp, "route": ROUTE_BUILD_INFO,
                    "routes": routes, "note": ""}
        routes.append({"route": "/app/BUILD_INFO", "ok": False, "rc": rc,
                       "text": (stamp or out.strip())[:160]})
    else:
        routes.append({"route": "/app/BUILD_INFO", "ok": False, "rc": rc,
                       "text": out.strip()[:160]})
    rc, out = docker("image", "inspect", IMAGE, "--format",
                     "{{index .Config.Labels \"" + LABEL + "\"}}")
    stamp = out.strip()
    if rc == 0 and rev_shape(stamp):
        routes.append({"route": LABEL, "ok": True, "rev": stamp})
        return {"container": container, "rev": stamp, "route": ROUTE_LABEL,
                "routes": routes, "note": ""}
    routes.append({"route": LABEL, "ok": False, "rc": rc, "text": stamp[:160]})
    return {"container": container, "rev": "", "route": "", "routes": routes,
            "note": "三条路都取不到容器里的 rev（这既不是「镜像落后」也不是「镜像在位」）"}
def resolve(rev: str) -> str:
    """把任意一枚可缩写的 rev 解成全 40 位提交号——解得开才谈得上逐字符。"""
    rc, out = git("rev-parse", rev + "^{commit}")
    text = out.strip()
    return text if rc == 0 and re.fullmatch(r"[0-9a-f]{40}", text) else ""


def behind_report(container_rev: str) -> dict:
    """镜像不是 HEAD 时那份「落后几枚＋清单」（判据② 点名要的输出）。"""
    base = resolve(container_rev) or container_rev
    rc, out = git("merge-base", "--is-ancestor", base, "HEAD")
    ancestor = rc == 0
    _, count = git("rev-list", "--count", base + "..HEAD") if ancestor else (0, "")
    _, oneline = git("log", "--oneline", base + "..HEAD") if ancestor else (0, "")
    _, files = git("diff", "--name-only", base + "..HEAD", "--", "app", "scripts",
                   "deploy", "migrations") if ancestor else (0, "")
    return {"is_ancestor": ancestor,
            "commits_behind": (count.strip() if ancestor else "读不出（不是 HEAD 的祖先）"),
            "commits": [line for line in oneline.splitlines() if line.strip()][:20],
            "image_inputs_touched": [line for line in files.splitlines() if line.strip()][:20]}


def provenance_gate(containers=CONTAINERS) -> dict:
    """开窗前的闸：两枚容器逐字符对上主树 HEAD 才算 PASS；任何一条路哑掉＝UNMEASURED。"""
    host = host_head()
    if not host["rev"]:
        return {"verdict": UNMEASURED, "value": {"host": host},
               "note": host["note"] + "；provenance 量不到，本件不开窗"}
    full_host = resolve(host["rev"]) or host["rev"]
    per_container, problems, unreadable = {}, [], []
    for container in containers:
        read = container_head(container)
        entry = {"container": container, "route": read["route"], "raw_rev": read["rev"],
                 "routes_tried": read["routes"]}
        if not read["rev"]:
            entry["state"] = UNMEASURED
            entry["note"] = read["note"]
            unreadable.append(container)
        else:
            full = resolve(read["rev"])
            entry["resolved_rev"] = full or ""
            if full and full == full_host:
                entry["state"] = PASS
                entry["equal_chars"] = len(full)
            else:
                entry["state"] = FAIL
                entry["divergence"] = behind_report(read["rev"])
                entry["note"] = REMEDIATION_RECREATE + "｜" + REMEDIATION_NOT_BUILD
                problems.append(container)
        per_container[container] = entry
    value = {"host_head": host["rev"], "host_resolved": full_host,
             "containers": per_container}
    if problems:
        return {"verdict": FAIL, "value": value,
                "note": "镜像里至少一枚容器与主树 HEAD 不逐字符相等：" + repr(problems)}
    if unreadable:
        return {"verdict": UNMEASURED, "value": value,
                "note": "这些容器的 rev 三条路都取不到：" + repr(unreadable) +
                        "（量不到不等于干净，本件拒绝开窗）"}
    return {"verdict": PASS, "value": value,
            "note": "两枚容器的 rev 与主树 HEAD 逐字符相等（全 " + str(len(full_host)) + " 位）"}


# --------------------------------------------------------------------- 问出去＋逐发存原文
def run_window(args) -> tuple:
    """一题报告档问出去、按游标轮询到终态、逐发落原文。返回 (rows, head)。"""
    out_dir = Path(args.out_dir)
    capture = Capture(out_dir)
    session = Session(args.base_url)
    started = time.time()
    head = {"asked_at": _now(), "base_url": session.base, "id": args.id,
            "tier": "", "lane": args.lane, "fixture_rel": args.fixture,
            "question_sha256": "", "poll_interval_seconds": args.poll_interval,
            "deadline_seconds": args.deadline, "stall_seconds": args.stall,
            "http_timeout_seconds": args.timeout, "provenance": args.provenance_block,
            "blips": 0, "relogins": 0, "approval_rounds": 0, "approval_http": [],
            "final_kind": "", "request_id": "", "ask_events": [], "username": args.username}
    question = load_question(args.fixture, args.id)
    head["tier"] = str(question.get("tier", ""))
    head["question_sha256"] = str(question.get("_line_sha256", ""))
    head["question_chars"] = len(str(question.get("question", "")))
    capture.write_head(head)
    session.login(args.username, args.password)
    session_id = uuid.uuid4().hex
    events, queued = session.ask(str(question["question"]), session_id,
                                 uuid.uuid4().hex, args.lane, args.timeout)
    head["ask_events"] = events
    head["request_id"] = str((queued or {}).get("request_id") or "")
    head["queue_reason"] = str((queued or {}).get("reason") or "")
    head["queue_lane_echo"] = str((queued or {}).get("lane") or "")
    if not head["request_id"]:
        head["final_kind"] = BYPASS_KIND
        capture.write_head(head)
        return capture.polls, head
    since = 0
    stalled_at = None
    signature = None
    deadline = started + args.deadline
    while True:
        now = time.time()
        if now >= deadline:
            head["final_kind"] = "queued_deadline" if capture.rows else "queued_no_status"
            break
        if stalled_at is not None and now >= stalled_at:
            head["final_kind"] = "queued_stalled"
            break
        http_status, raw, body = session.poll_status(head["request_id"], since, args.timeout)
        status = str((body or {}).get("status") or "")
        sent_at = _now()
        row = capture.write_poll(sent_at=sent_at, since=since, http_status=http_status,
                                 raw=raw, body=body, status=status)
        mark = (status, (body or {}).get("position"),
                ((body or {}).get("failure") or {}).get("attempts")
                if isinstance((body or {}).get("failure"), dict) else None)
        if http_status != 200 or body is None:
            head["blips"] += 1
            if http_status == 401:
                head["relogins"] += 1
                session.login(args.username, args.password)
            time.sleep(args.poll_interval)
            continue
        if status in ("queued", LIVE_STATUS, "cancel_requested"):
            piece = _piece_of(row)
            if piece is not None:
                cursor = int(piece.get("cursor") or 0)
                if cursor > since:
                    since = cursor
        if mark != signature:
            signature = mark
            stalled_at = now + args.stall
        if status in TERMINAL_STATUSES:
            #: 上游分两枚名：一次读回正文 = queued_polled，挂起被批准后才拿到正文 = queued_approved。
            #: 混成一枚就把「这一轮等了人批准」这件事读没了（R447 判据② 那条口径）。
            got_bytes = bool(str((body or {}).get("result") or "").strip())
            if status != "done":
                head["final_kind"] = "queued_" + status
            elif not got_bytes:
                head["final_kind"] = KIND_NO_BYTES
            else:
                head["final_kind"] = KIND_APPROVED if head["approval_rounds"] else KIND_POLLED
            head["wait_ms"] = round((time.time() - started) * 1000.0, 1)
            break
        if status == PARK_STATUS:
            if args.max_approval_rounds and head["approval_rounds"] < args.max_approval_rounds:
                head["approval_rounds"] += 1
                code = session.approve(session_id, args.timeout)
                head["approval_http"].append(code)
                if not 200 <= code < 300:
                    head["final_kind"] = "approval_failed"
                    break
                time.sleep(args.poll_interval)
                continue
            head["final_kind"] = KIND_PARKED
            break
        time.sleep(args.poll_interval)
    if not head["final_kind"]:
        head["final_kind"] = "queued_no_status"
    head["polls"] = capture.rows
    capture.write_head(head)
    return capture.polls, head


# ------------------------------------------------------------------------- 输出与 CLI
def render(report: dict) -> list:
    """六格逐枚点名，一行一枚：值与判词都从判读函数现出，纸不许另抄一份。"""
    lines = []
    for name in report["order"]:
        cell = report["cells"][name]
        lines.append("[R561] cell=%s verdict=%s value=%s note=%s" % (
            name, cell["verdict"], json.dumps(cell["value"], ensure_ascii=False, sort_keys=True),
            cell["note"]))
    verdicts = [report["cells"][name]["verdict"] for name in report["order"]]
    headline = PASS if verdicts.count(PASS) == len(verdicts) else (
        "有格子量不到" if UNMEASURED in verdicts else "有格子 FAIL")
    lines.append("[R561] rc=%d headline=%s" % (report["rc"], headline))
    return lines


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="R561 队列道片段读数（容器内那一遍，只读）")
    parser.add_argument("--id", default=DEFAULT_QUESTION_ID, help="问哪一题（评测集里的 id）")
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE_REL,
                        help="题源：默认在册评测集那一份，只读，取不到就红")
    parser.add_argument("--base-url", default=os.getenv("EVAL_BASE_URL", "http://127.0.0.1:8001"))
    parser.add_argument("--username", default=os.getenv("EVAL_USERNAME", ""))
    parser.add_argument("--password", default=os.getenv("EVAL_PASSWORD", ""))
    parser.add_argument("--lane", default="report",
                        help="载荷里声明的档位；报告档不入队就是 bypass。空串＝故意不入队（演 bypass 用）")
    parser.add_argument("--out-dir", default="", help="默认 docs/perf/raw/r561-<今天>")
    parser.add_argument("--poll-interval", type=float, default=3.0,
                        help="与前端每 3 s 一发同宽（客户端就是这么读的）")
    parser.add_argument("--deadline", type=float, default=900.0)
    parser.add_argument("--stall", type=float, default=300.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-approval-rounds", type=int, default=3)
    parser.add_argument("--skip-provenance", action="store_true",
                        help="只为演量具形状；provenance 那一格会被判「量不到」，总退出码不可能是 0")
    parser.add_argument("--offline", default="",
                        help="不问出去，只把已存的那一发发原文重新判一遍（离线自测与回填凭据纸走这条）")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.offline:
        try:
            rows = load_capture(args.offline)
        except (OSError, ValueError) as exc:
            print("[R561] rc=2 存档读不出：" + type(exc).__name__ + ": " + str(exc) +
                  "（读不到就是读不到，绝不折成「零发」或「都干净」）", flush=True)
            return 2
        head_path = Path(args.offline) / "head.json"
        head = None
        if head_path.is_file():
            try:
                head = json.loads(head_path.read_bytes().decode("utf-8"))
            except ValueError as exc:
                print("[R561] rc=2 终账读不出：" + type(exc).__name__ + ": " + str(exc) +
                      "（head.json 解不开就不交任何一格的数）", flush=True)
                return 2
        report = judge(rows, head)
        print("[R561] 离线重放：下面六格读的是存档里那一遍记下的东西（provenance 也是当时存的），"
              "不是此刻容器里的读数——拿它当容器凭据就是把纸面形状当成容器形状", flush=True)
        for line in render(report):
            print(line)
        return report["rc"]
    if not args.username or not args.password:
        print("[R561] rc=2 量具没跑成：EVAL_USERNAME/EVAL_PASSWORD 没给（缺凭证不是缺读数，"
              "这一遍一枚都没问，绝不交任何一格的数）", flush=True)
        return 2
    if args.skip_provenance:
        args.provenance_block = {"verdict": UNMEASURED, "value": {"skipped": True},
                                 "note": "--skip-provenance：这一格压根没量，不许当成通过"}
        print("[R561] provenance 被显式跳过（只演形状，不开真窗）", flush=True)
    else:
        args.provenance_block = provenance_gate()
        print("[R561] provenance=%s %s" % (args.provenance_block["verdict"],
                                           json.dumps(args.provenance_block["value"],
                                                      ensure_ascii=False)[:900]), flush=True)
        if args.provenance_block["verdict"] != PASS:
            print("[R561] rc=2 拒绝开窗：" + args.provenance_block["note"], flush=True)
            print("[R561] 出口只有两条：" + REMEDIATION_RECREATE + "；" + REMEDIATION_NOT_BUILD,
                  flush=True)
            return 2
    today = time.strftime("%Y-%m-%d")
    out_dir = Path(args.out_dir) if args.out_dir else (ROOT / "docs" / "perf" / "raw" /
                                                       ("r561-" + today))
    if (out_dir / "polls.jsonl").exists():
        print("[R561] rc=2 拒绝开窗：" + str(out_dir) + " 里已经有一份 polls.jsonl——"
              "一扇窗一份账，不许把两遍叠在同一份凭据上（换 --out-dir）", flush=True)
        return 2
    try:
        rows, head = run_window(args)
    except Exception as exc:  # 量具自己没跑成 = 2，不是「干净」
        print("[R561] rc=2 量具没跑成：" + type(exc).__name__ + ": " + str(exc), flush=True)
        return 2
    report = judge(rows, head)
    #: summary.json 只留去 evidence 的那一份账：逐发原文在 polls.jsonl 与 raw 存档里，
    #: 不在这里再抄一遍（同一份数双写迟早对不上，见本单凭据纸自曝第二笔）。
    summary = {"asked_at": head.get("asked_at"), "out_dir": str(out_dir), "head": head,
               "order": report["order"],
               "cells": {name: {k: v for k, v in cell.items() if k != "evidence"}
                         for name, cell in report["cells"].items()},
               "rc": report["rc"]}
    Capture(out_dir).write_summary(summary)
    print("[R561] 存档：" + str(out_dir) + " 共 " + str(len(rows)) + " 发", flush=True)
    for line in render(report):
        print(line, flush=True)
    return report["rc"]


if __name__ == "__main__":
    sys.exit(main())
