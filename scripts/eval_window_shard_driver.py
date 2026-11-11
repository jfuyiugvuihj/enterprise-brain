#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R570 —— 长跑评测窗的断点保护：把「一窗 105 题」切成逐题落盘的片。

为什么要有这一枚（10-02，run12 在 99/105 处整窗报废）
----------------------------------------------------
在册采集器 ``scripts/collect_evaluation_answers.py`` 的 ``write_answers``（:292-297）只在
覆盖闸 ``assert_coverage``（:279-289，必须全齐）通过之后一次性 ``write_text``，而
``scripts/eval_transport_ask_v2.py`` 头部第 4 条自己写明：「逐题在盘」只指 sidecar，
「采集器只在覆盖闸全过时写字节，中途没有断点」。⇒ 只要断 Docker／断网／休眠／杀进程，
**必然整窗重来**：99 题的模型调用全部白付，盘上只剩不含答案文本的 sidecar 与帧账。
这是在册设计，不是故障；本件不修它，只在它外面加一层「片成即落盘」的调度。

本件不做什么（一条都不越界）
--------------------------
* 不改采集器、不改 transport、不改 sidecar／帧账的键集（那两套键被
  ``tests/test_r123_hitl_approval.py:205``／``:243`` 钉着），不改评分尺
  （评分仍走 ``scripts/run_quality_evaluation.py``）。
* 不自己发 HTTP：每一片都原样调起在册采集器，题号取自切片后的迷你 fixture。
* 不去重、不粉饰：``--commit`` 如实报 sidecar 的重复行数（同一 id 第二行＝那片被整片重打过）。
* 一扇窗的产物一律落仓外（默认 ``%TEMP%\\evalrun``）；指到仓内直接拒。

复用为什么在这里是安全的（🔴 判据 5）
-----------------------------------
半窗混库拼成一条基线，比丢一窗更坏。所以盘上旧片只允许在**五项指纹全等**时被复用：
镜像 ``revision`` ∧ 容器 ``INDEX_BACKEND`` ∧ fixture ``sha256`` ∧ transport spec ∧ ``shard_size``。
指纹在开窗那一刻写进 ``<tag>.window.json``，此后每一枚读它的动作都先比对再干活；
任一不符 ⇒ REFUSE 并说明「这些片是在另一种条件下采的」，要混库就换新 tag 从头采。

七格判据 ↔ 代码落点（测试逐枚点名，见 tests/test_r570_window_shard_driver.py）
--------------------------------------------------------------------------
① 断点粒度到题 → ``DEFAULT_SHARD_SIZE``／``build_plan``／``write_shard_answers`` 路径命名／
   ``collector_env`` 里 EVAL_SIDECAR 全窗只一枚（分片不多写一行）
② 幂等 → ``shard_is_done`` + ``resume_plan_state`` 的 ``to run=0``
③ 局部失败局部补 → ``run_window`` 的 ``todo`` 差集
④ 合并仍走覆盖闸 → ``merge_shards``（缺枚／短片／空 answer／重复 id 一律 REFUSE，rc 非 0）
⑤ 指纹闸 → ``FINGERPRINT_KEYS``／``fingerprint_mismatch``／``provenance``
⑥ 失联早停 → ``DEAD_STREAK_DEFAULT``／``run_window`` 的 ``STOP``（rc=3，已完成片保留）
⑦ 读路径可钉死 → ``check_read_path``（pgvector 与 chroma 双向真拦；REFUSE 给正解
   ``docker compose up -d --force-recreate``，并写明 ``docker restart`` 不重读 env_file）

用法
---
    python scripts/eval_window_shard_driver.py --tag run13 --plan
    python scripts/eval_window_shard_driver.py --tag run13 --run
    python scripts/eval_window_shard_driver.py --tag run13 --commit
    python scripts/eval_window_shard_driver.py --tag rehearsal --fixture 迷你集 --run --dry-run

退出码：0 成功／2 REFUSE（参数、闸、指纹、覆盖、环境读不到）／3 连续失联停窗／
4 一轮跑完仍有片没成（保留进度，修好环境再 ``--run``）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

#: 每片默认一枚题：断在哪一题就只重打那一题（判据 ①）。
DEFAULT_SHARD_SIZE = 1
#: 在册采集器（相对 repo 工作目录调用，本件不复制它的任何逻辑）。
COLLECTOR = "scripts/collect_evaluation_answers.py"
DEFAULT_TRANSPORT = "eval_transport_ask_v2:transport"
DEFAULT_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_USERNAME = "evalbot"
DEFAULT_CONTAINER = "enterprise-brain-backend-1"
#: 连续这么多片零产出 ⇒ 判后端／容器已死，停窗保进度（判据 ⑥）。
DEAD_STREAK_DEFAULT = 4
#: 单实例闸：同 tag 不许两串并跑（端口占位，跨进程可见）。
LOCK_PORT_BASE = 38820
LOCK_PORT_SPAN = 40
#: 判据 ⑤ 的五枚指纹，一枚都不许多也不许少；比对只看这五枚。
FINGERPRINT_KEYS = ("revision", "index_backend", "fixture_sha256", "transport", "shard_size")
#: 读不到容器时的说法：不许把「读不到」当成「读到空」。
HOW_RECREATE = ("env_file 是在容器创建那一刻才解析的：正解 docker compose up -d --force-recreate，"
                "plain docker restart 不重读它")
#: 口令来源问不到时的两条补法（R571：deploy/.env.server 是未跟踪件，只在工作副本里）。
ENV_FILE_REMEDIES = ("① 显式传 --env-file <主树工作副本>/deploy/.env.server（该件未跟踪，"
                     "只存在于主树工作副本，工作树／跑分树里根本没有）；"
                     "② 或把它放进 --repo 那棵树的 deploy/.env.server")

RC_OK = 0
RC_REFUSE = 2
RC_DEAD_BACKEND = 3
RC_SHARDS_OPEN = 4


class Refuse(RuntimeError):
    """一切「不肯干」都从这里出去，且一律带非零退出码（🔴 不沿用参照件的 exit 0）。"""

    def __init__(self, why: str, hint: str = "", code: int = RC_REFUSE) -> None:
        super().__init__(why)
        self.why = why
        self.hint = hint
        self.code = code


def log(message: str) -> None:
    print(message, flush=True)


def refuse(why: str, hint: str = "", code: int = RC_REFUSE) -> None:
    """REFUSE 一律写 stdout（便于总控按行取数）并以非零码收。"""
    log("REFUSE: " + why)
    if hint:
        log("  fix: " + hint)
    raise Refuse(why, hint, code)

def default_tmp_dir() -> Path:
    """产物目录：``EB_EVAL_TMP_DIR`` 优先，否则 ``%TEMP%\\evalrun``（与在册 runbook 同口径）。"""
    raw = os.environ.get("EB_EVAL_TMP_DIR")
    if raw:
        return Path(raw)
    return Path(os.environ.get("TEMP") or tempfile.gettempdir()) / "evalrun"


def default_python() -> str:
    """调起采集器用的解释器：``EB_EVAL_PYTHON`` 优先，否则**当前解释器**。

    绝不在代码里落一枚绝对路径：那会造出第二份会过期的环境事实。
    """
    return os.environ.get("EB_EVAL_PYTHON") or sys.executable


def paths(tag: str, tmp_dir: Path) -> dict:
    """一扇窗的全部落点。文件名与在册 runbook / 既有量具保持一致。"""
    root = tmp_dir / (tag + ".shards")
    return {
        "tmp": tmp_dir,
        "root": root,
        "window": tmp_dir / (tag + ".window.json"),
        "shards": tmp_dir / (tag + ".shards.json"),
        "sidecar": tmp_dir / (tag + "-sidecar.jsonl"),
        "frames": tmp_dir / (tag + "-sidecar-frames.jsonl"),
        "answers": tmp_dir / (tag + "-answers.jsonl"),
        "log": tmp_dir / (tag + ".driver.log"),
    }


def shard_name(tag: str, index: int, suffix: str) -> str:
    return "%s-s%03d-%s.jsonl" % (tag, index, suffix)


def refuse_inside_repo(path: Path, what: str, root: Path = None) -> None:
    """🔴 产物只许落仓外：指进仓内当场拒（在册纪律，别让脏件流进别的树）。

    R601 判据②：``root`` 可指到**别的**一棵树。``--repo`` 指哪棵树，采集器就在哪棵树里写字节，
    只拿本件自己的 ``REPO_ROOT`` 过闸等于放行「往 --repo 那棵树漏产物」这一形（在册 runbook
    里的跑分树就是另一棵）。与 ``scripts/collect_evaluation_answers.py`` 同名同语义同一枚把手。
    """
    base = REPO_ROOT if root is None else Path(root)
    try:
        resolved = Path(path).resolve()
        inside = base.resolve()
    except OSError:
        return
    try:
        resolved.relative_to(inside)
    except ValueError:
        return
    refuse(what + " 落在仓内：" + str(resolved) + "（对 " + str(inside) + " 这棵树）",
           "产物必须落仓外（默认 %TEMP%\\evalrun），仓内答案件会脏每一棵 worktree 并招来误加 git add")


#: 一扇窗会写的每一枚落点（R601 判据②：逐枚点名过闸，不许只挑两枚看）。
#: 分片自己的 fixture/answers 都在 ``root`` 之下，由「分片目录」这一枚代闸。
LANDING_SPOTS = (("tmp", "产物目录"), ("root", "分片目录"), ("window", "指纹件"),
                 ("shards", "分片计划件"), ("sidecar", "侧车"), ("frames", "帧账"),
                 ("answers", "合并件"), ("log", "驱动日志"))


def is_git_tree(path) -> bool:
    """``.git`` 在位就算一棵树（主树是目录，worktree 是文件，两形都算）。"""
    try:
        return (Path(path) / ".git").exists()
    except OSError:
        return False


def refuse_landing_spots(P: dict, repo: Path = None) -> None:
    """逐枚过闸，并对两棵树过闸：本件自己的树 + ``--repo`` 那棵**树**。

    🔴 第二道只在那枚 ``--repo`` 确实是一棵 git worktree 时才走：量具自测里 ``--repo`` 常被
    指成一枚临时目录（``tests/test_r570_window_shard_driver.py`` 两枚在册钉就这么用），临时目录
    不是仓库，往它里面写产物脏不了任何一棵树；把它当仓库拒＝拿假罪证拦真窗。对真跑分树
    （``be-eval95`` 那形）这一道是实打实的：从前只闸本件自己的 REPO_ROOT。
    """
    roots = [REPO_ROOT]
    if repo is not None and is_git_tree(repo):
        roots.append(Path(repo))
    for key, label in LANDING_SPOTS:
        for base in roots:
            refuse_inside_repo(P[key], label, root=base)


def read_jsonl_rows(path: Path) -> list:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def run_in_container(shell: str, container: str, timeout: float = 25.0):
    """向在跑的容器要一枚读数，返回 ``(ok, value)``。

    🔴 单点：判据 ⑤／⑦ 的容器读数全走这一枚，测试里 monkeypatch 它即可，一枚都不许真调 docker。
    ``ok=False`` 是「问不着」（docker 不在／容器没起／超时），与「问到了但变量为空」严格分开。
    """
    try:
        proc = subprocess.run(["docker", "exec", container, "sh", "-c", shell],
                              capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                              errors="replace")
    except Exception as exc:  # docker 缺席／超时／权限：一律算「问不着」，不猜
        return False, type(exc).__name__
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "").strip()[:160]
    return True, (proc.stdout or "").strip()


def _revision_from_build_info(info: str) -> str:
    for line in info.splitlines():
        if line.startswith("revision="):
            return line.split("=", 1)[1].strip()
    return ""


def probe_container(container: str):
    """取镜像 revision 与容器 INDEX_BACKEND；返回 (读到了几枚, 值, 失败原因)。"""
    ok_rev, rev = run_in_container("cat /app/BUILD_INFO", container)
    # 🔴 别用 printenv：变量未设时它 rc=1，会把「读到空」（＝chroma 读路径）误判成「问不着」，
    # 于是判据 ⑦ 的 chroma 那一半在现场必假拒。用一枚恒等前缀把两件事分开。
    ok_backend, backend = run_in_container(
        'printf SET=%s "$INDEX_BACKEND"', container)
    reasons = []
    revision = ""
    index_backend = ""
    if ok_rev:
        revision = _revision_from_build_info(rev)
    else:
        reasons.append("BUILD_INFO 读不到：" + str(rev))
    if ok_backend:
        index_backend = backend[4:].strip() if backend.startswith("SET=") else backend.strip()
    else:
        reasons.append("INDEX_BACKEND 读不到：" + str(backend))
    return {"probe_ok": bool(ok_rev and ok_backend), "revision": revision,
            "index_backend": index_backend, "container": container,
            "probe_errors": reasons}


def fixture_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def provenance(transport: str, fixture: Path, shard_size: int, container: str,
               dry_run: bool, require_probe=None) -> dict:
    """把「这一窗是在什么条件下采的」记成一枚指纹（判据 ⑤ 的五项 ＋ 取证辅助项）。

    ``require_probe``＝问不着容器时要不要当场拒。缺省跟随「是不是真窗」：真窗拒、演练放行。
    ``--commit`` 显式传 False：Docker 停了也得把已采完的一窗收口（run12 正是死在收不了口），
    此时只比不问容器也算得出的那三枚（见 OFFLINE_FINGERPRINT_KEYS）。
    """
    live = probe_container(container)
    if require_probe is None:
        require_probe = not dry_run
    if require_probe and not live["probe_ok"]:
        refuse("容器读数取不全，指纹无法成立（" + "；".join(live["probe_errors"]) + "）",
               "真窗必须能问到容器读数：先 docker ps 确认 " + container + " 在跑；"
               "演练请用 --dry-run（零模型调用，不要求容器在场）",
               code=RC_REFUSE)
    return {
        "revision": live["revision"],
        "index_backend": live["index_backend"],
        "fixture_sha256": fixture_sha256(fixture),
        "transport": transport,
        "shard_size": int(shard_size),
        "container": container,
        "probe_ok": live["probe_ok"],
        "probe_errors": live["probe_errors"],
        "dry_run": bool(dry_run),
        "probed_at": time.strftime("%F %T"),
    }


def fingerprint_mismatch(recorded: dict, live: dict, keys=FINGERPRINT_KEYS) -> list:
    """比指纹：默认那五枚全比；返回不符的键名列表（全等 ⇒ 空表 ⇒ 才准复用盘上旧片）。"""
    return [key for key in keys if recorded.get(key) != live.get(key)]


#: 问不着容器时仍然比得动的三枚（都不依赖 docker）：收口处用它们兜底。
OFFLINE_FINGERPRINT_KEYS = ("fixture_sha256", "transport", "shard_size")


def read_path_state(expect: str) -> str:
    """把 ``--expect-backend`` 的取值钉成两枚：pgvector / chroma（chroma＝该变量为空）。"""
    if expect in ("", None):
        return ""
    if expect in ("pgvector", "chroma"):
        return expect
    refuse("--expect-backend 只认 pgvector 或 chroma，收到 " + repr(expect),
           "chroma 这一档的含义是容器里 INDEX_BACKEND 为空；别的取值本件不代猜")
    return expect  # pragma: no cover  -- refuse() 已抛


def check_read_path(live: dict, expect: str) -> None:
    """判据 ⑦：双向真拦。钉 pgvector 而容器为空 ⇒ 拦；钉 chroma 而容器是 pgvector ⇒ 也拦。"""
    want = read_path_state(expect)
    if not want:
        return
    if not live["probe_ok"]:
        refuse("钉不死读路径：容器的 INDEX_BACKEND 问不着（" + "；".join(live["probe_errors"]) + "）",
               "先让容器可问再 --expect-backend；" + HOW_RECREATE)
    actual = live["index_backend"]
    holds = (actual == "pgvector") if want == "pgvector" else (actual == "")
    if not holds:
        refuse("容器 INDEX_BACKEND=" + repr(actual) + "，而这一窗要钉的是 " + want
               + "（chroma 这一档要求该变量为空）", HOW_RECREATE)

def load_ids(fixture: Path) -> list:
    """按 fixture 原序取题号（合并时也是这个序，判据 ④）。"""
    ids = []
    for line in Path(fixture).read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rid = str(row.get("id", "")).strip()
        if not rid:
            refuse("fixture 里有一行没有 id：" + str(fixture))
        ids.append(rid)
    if len(ids) != len(set(ids)):
        refuse("fixture 自带重复题号，分片会含混：" + str(fixture))
    return ids


def build_plan(ids: list, shard_size: int) -> list:
    if shard_size < 1:
        refuse("--shard-size 必须 >=1，收到 " + str(shard_size),
               "默认 1：每题一片、片成即落盘；>1 时一片里任一题失败会整片重打（sidecar 会多行）")
    return [ids[i:i + shard_size] for i in range(0, len(ids), shard_size)]


def shard_is_done(shard_answers: Path, want: list) -> bool:
    """一片算「已成」的唯一口径：行数相等 ∧ 题号集合相等 ∧ 每行 answer 非空。"""
    rows = read_jsonl_rows(shard_answers)
    if len(rows) != len(want):
        return False
    got = [str(row.get("id")) for row in rows]
    if sorted(got) != sorted(str(item) for item in want):
        return False
    return all(str(row.get("answer") or "").strip() for row in rows)


def resume_plan_state(plan: list, tag: str, shard_root: Path) -> dict:
    """把片分成「已在盘上」与「还欠着」两堆（判据 ②③ 的读数就从这里出）。"""
    done = [index for index, want in enumerate(plan)
            if shard_is_done(shard_root / shard_name(tag, index, "answers"), want)]
    todo = [index for index in range(len(plan)) if index not in done]
    return {"shards": len(plan), "done": done, "todo": todo}


def make_shard_fixture(fixture: Path, want: list, target: Path) -> None:
    """切一片的迷你 fixture：只挑这些题号，一题不多一题不少（采集器的覆盖闸按片成立）。"""
    wanted = set(str(item) for item in want)
    lines = []
    for line in Path(fixture).read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        if str(json.loads(line).get("id")) in wanted:
            lines.append(line.rstrip("\r\n"))
    if len(lines) != len(want):
        refuse("切片题数对不上：" + ",".join(sorted(wanted)) + " 期望 " + str(len(want))
               + " 实得 " + str(len(lines)), "fixture 与分片计划不同代：重跑 --plan")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def password_from_env_file(env_file: Path, explicit: bool = False) -> str:
    """口令的唯一取用点：文件问不到 ⇒ 走 REFUSE（非零）。

    🔴 裸 FileNotFoundError 一律不许出现在这条路上——deploy/.env.server 是未跟踪件，缺省值
    ``<repo>/deploy/.env.server`` 在 --repo 指向跑分树时必然落空（R571 真窗 22:36:22 就这么裸崩）。
    量具自己崩＝问不到，既不是「被测环境干净」，也不许当成通过。
    """
    src = "显式给的 --env-file" if explicit else "由 --repo 推出的缺省 env-file（可用 --env-file 覆盖）"
    path = Path(env_file)
    try:
        if not path.is_file():
            raise FileNotFoundError("文件不在或不是一枚普通件")
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        refuse(src + " 读不到：" + str(path) + "（" + type(exc).__name__ + "：" + str(exc) + "）"
               + " ⇒ 这一窗不开：按「问不到」处理，不许当缺省能用、也不许当通过",
               ENV_FILE_REMEDIES)
    for line in lines:
        if line.startswith("EB_EVAL_PASSWORD"):
            return line.split("=", 1)[1].strip()
    return ""


def collector_command(python: str, repo: Path, shard_fixture: Path, shard_answers: Path,
                      transport: str, dry_run: bool) -> list:
    """拼一针采集器命令行。🔴 本件不 import 采集器、不复制它的任何判读，只是调它。"""
    cmd = [python, "-X", "utf8", COLLECTOR, "--fixture", str(shard_fixture)]
    if dry_run:
        cmd += ["--dry-run", "--allow-sample"]
    else:
        cmd += ["--transport", transport]
    cmd += ["--output", str(shard_answers)]
    return cmd


def collector_env(tmp_dir: Path, sidecar: Path, base_env: dict, env_file: Path, repo: Path,
                  base_url: str, username: str, dry_run: bool,
                  env_file_explicit: bool = False, frames: Path = None) -> dict:
    """给采集器的一瓶环境。

    🔴 ``EVAL_SIDECAR`` 全窗只有**一枚**：sidecar／帧账仍是一题一行的全账，
    分片本身不许让它多写一行（判据 ①）。``TEMP``/``TMP`` 指向本窗目录，
    免得采集器自己的临时件漏在别处。

    R601 判据②：``EVAL_FRAME_LEDGER`` 从前**不设**，帧账全靠 transport 跟着 SIDECAR 走
    （``scripts/eval_transport_ask_v2.py:236`` 的缺省名）。跟着走不是把手：那一腿的缺省值是
    ``scripts/collect-sidecar-frames.jsonl``，SIDECAR 一旦没设就落在仓内——今天漏进仓里的正是这一枚。
    现在两枚落点都由本件逐枚钉死，缺 ``frames`` 时按 transport 的同一把命名派生。
    """
    ledger = Path(frames) if frames is not None else \
        Path(sidecar).with_name(Path(sidecar).stem + "-frames.jsonl")
    env = dict(base_env)
    env.update({
        "EVAL_SIDECAR": str(sidecar),
        "EVAL_FRAME_LEDGER": str(ledger),
        "PYTHONIOENCODING": "utf-8",
        "TEMP": str(tmp_dir),
        "TMP": str(tmp_dir),
    })
    if dry_run:
        return env
    password = env.get("EVAL_PASSWORD") or password_from_env_file(env_file, env_file_explicit)
    if not password:
        refuse("拿不到 EVAL_PASSWORD，也没有 " + str(env_file) + " 里的 EB_EVAL_PASSWORD",
               "演练请用 --dry-run（零模型调用、不要求凭据）；真窗先备好 deploy/.env.server")
    env.update({"EVAL_BASE_URL": base_url, "EVAL_USERNAME": username, "EVAL_PASSWORD": password})
    return env


def invoke_collector(cmd: list, repo: Path, env: dict):
    """调起一针采集器，返回 (rc, 末段输出)。测试里 monkeypatch 这一枚即可，零子进程。

    解释器或 cwd 起不来（``EB_EVAL_PYTHON`` 打错、树被搬走）不许把整窗炸成 traceback：
    那属于「这一片零产出」，交给判据 ⑥ 的死串计数去判停窗，已完成片一律留在盘上。
    """
    try:
        proc = subprocess.run(cmd, cwd=str(repo), env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError as exc:
        return 127, "采集器起不来（判为零产出，不按成功计）：%s: %s" % (type(exc).__name__, exc)
    tail = " | ".join((proc.stdout or "").splitlines()[-2:] + (proc.stderr or "").splitlines()[-3:])
    return proc.returncode, tail


def lock_port(tag: str, base_port: int, span: int) -> int:
    """tag → 端口：用 sha256 而不是 ``hash()``（后者受 PYTHONHASHSEED 支配，跨进程不稳定）。"""
    return base_port + int(hashlib.sha256(tag.encode("utf-8")).hexdigest()[:8], 16) % span


def acquire_tag_lock(tag: str, base_port: int, span: int) -> socket.socket:
    """同 tag 单实例：端口占位是最硬的闸（进程名数不出串与串）。"""
    port = lock_port(tag, base_port, span)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.listen(1)
    except OSError:
        refuse("另一串 " + tag + " 驱动仍占着 127.0.0.1:" + str(port),
               "按端口判，别按进程名数：.venv 的 python 是 shim 会 re-exec，一串显示两枚是正常")
    return sock


def write_window_json(path: Path, live: dict) -> None:
    payload = dict(live)
    payload["started_at"] = time.strftime("%F %T")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def open_window_or_resume(P: dict, live: dict, tag: str, dry_run: bool) -> str:
    """开窗前必做的一格：要么按同一枚指纹续旧窗，要么干净开窗，🔴 绝不混库。"""
    recorded = None
    if P["window"].exists():
        recorded = json.loads(P["window"].read_text(encoding="utf-8"))
    if recorded is not None:
        bad = fingerprint_mismatch(recorded, live)
        if bad:
            refuse("、".join(bad) + " 与盘上记录不符：" +
                   "、".join("%s 记为 %r／现取 %r" % (key, recorded.get(key), live.get(key))
                            for key in bad) +
                   " ⇒ 这些片是在另一种条件下采的，不许复用到 " + tag,
                   "换一个新 tag，或删掉 " + str(P["window"]) + " 与 " + str(P["root"]) +
                   " 把这扇窗从头重采（半窗混库拼成一条基线比丢一窗更坏）")
        log("resume: 五项指纹与 " + str(P["window"]) + " 全等，盘上已完成片将被复用")
        return "resumed"
    sidecar_rows = read_jsonl_rows(P["sidecar"])
    if sidecar_rows and not dry_run:
        refuse(str(P["sidecar"]) + " 已有 " + str(len(sidecar_rows)) +
               " 行，但 window.json 不在 ⇒ 那是另一扇窗（条件未知）的账，不许并进 " + tag,
               "用属于那本 sidecar 的 tag，或把它挪走再开窗")
    write_window_json(P["window"], live)
    log("window.json 已落：" + str(P["window"]))
    return "opened"

def run_window(args, P: dict, live: dict, fixture: Path, repo: Path) -> int:
    """按片跑：已完成的一题都不重打，欠着的补差集，连续 N 片零产出就停窗（判据 ②③⑥）。"""
    ids = load_ids(fixture)
    plan = build_plan(ids, args.shard_size)
    P["root"].mkdir(parents=True, exist_ok=True)
    P["shards"].write_text(json.dumps(plan, ensure_ascii=False) + "\n", encoding="utf-8")
    env = collector_env(P["tmp"], P["sidecar"], dict(os.environ), Path(args.env_file), repo,
                       args.base_url, args.username, args.dry_run, args.env_file_explicit,
                       frames=P["frames"])
    if args.dry_run:
        log("DRY RUN：假 transport（采集器自带），零模型调用；不占单实例闸")
    else:
        _LOCKS.append(acquire_tag_lock(args.tag, args.lock_port_base, LOCK_PORT_SPAN))

    state = resume_plan_state(plan, args.tag, P["root"])
    log("shards=%d already complete=%d to run=%d"
        % (state["shards"], len(state["done"]), len(state["todo"])))
    if not state["todo"]:
        log("to run=0 ⇒ 一题都不重打（判据 ②）；要收口直接 --commit")
        return RC_OK

    todo = list(state["todo"])
    failed = []
    dead_streak = 0
    for round_no in range(args.retries + 1):
        queue = [index for index in todo if index in failed] if round_no else list(todo)
        queue = [index for index in queue
                 if not shard_is_done(P["root"] / shard_name(args.tag, index, "answers"), plan[index])]
        if not queue:
            break
        if round_no:
            log("-- 第 %d 轮补片：%d 片仍欠（退避 %.1fs）--"
                % (round_no + 1, len(queue), args.retry_sleep))
            if args.retry_sleep > 0:
                time.sleep(args.retry_sleep)
        for index in queue:
            want = plan[index]
            shard_fixture = P["root"] / shard_name(args.tag, index, "fixture")
            shard_answers = P["root"] / shard_name(args.tag, index, "answers")
            make_shard_fixture(fixture, want, shard_fixture)
            cmd = collector_command(args.python, repo, shard_fixture, shard_answers,
                                    args.transport, args.dry_run)
            started = time.time()
            rc, tail = invoke_collector(cmd, repo, env)
            took = time.time() - started
            log("  [shard %03d %-12s] rc=%s %5.1fs %s" % (index, ",".join(want), rc, took, tail))
            if shard_is_done(shard_answers, want):
                dead_streak = 0
                continue
            failed.append(index)
            dead_streak += 1
            if dead_streak >= args.dead_streak:
                log("STOP: 连续 " + str(dead_streak) + " 片零产出 ⇒ 判后端／容器／解释器已死，停窗保进度。"
                    "已完成片全部留在 " + str(P["root"]) + "，环境修好后再 --run，最后 --commit。")
                return RC_DEAD_BACKEND
            log("  ↳ 这一片没成（零产出或短行）；死串计数 " + str(dead_streak) + "/"
                + str(args.dead_streak))

    remaining = resume_plan_state(plan, args.tag, P["root"])["todo"]
    log("run finished: %d/%d shards complete, %d open%s"
        % (len(plan) - len(remaining), len(plan), len(remaining),
           "" if not remaining else " (ids: " + ",".join(plan[i][0] for i in remaining[:20]) + ")"))
    return RC_OK if not remaining else RC_SHARDS_OPEN


def merge_shards(args, P: dict, fixture: Path) -> int:
    """合并仍走覆盖闸（判据 ④）：短片／缺枚／空 answer／跨片重复 ⇒ 一律 REFUSE 且非零退出。"""
    ids = load_ids(fixture)
    if not P["window"].exists():
        refuse("window.json 不在（" + str(P["window"]) + "）：没有指纹记录的一堆片不许拼成基线",
               "先 --plan 确认 tag，或整窗重采")
    live = provenance(args.transport, fixture, args.shard_size, args.container, args.dry_run,
                      require_probe=False)
    recorded = json.loads(P["window"].read_text(encoding="utf-8"))
    keys = FINGERPRINT_KEYS if live["probe_ok"] else OFFLINE_FINGERPRINT_KEYS
    bad = fingerprint_mismatch(recorded, live, keys)
    if bad:
        refuse("合并前指纹复核不过：" + "、".join(
            "%s 记为 %r／现取 %r" % (key, recorded.get(key), live.get(key)) for key in bad),
               "这些片不是同一条件下采的；换 tag 或重采（" + HOW_RECREATE + "）")
    if not live["probe_ok"]:
        log("合并前的容器两枚（revision／INDEX_BACKEND）问不着，这轮只比三枚离线指纹："
            + "、".join(OFFLINE_FINGERPRINT_KEYS))
    plan = (json.loads(P["shards"].read_text(encoding="utf-8")) if P["shards"].exists()
            else build_plan(ids, args.shard_size))
    flat = [str(item) for shard in plan for item in shard]
    if flat != ids:
        refuse("分片计划与 fixture 不同代：拼出来的题集与 fixture 原序不等（缺/多/序漂）",
               "重跑 --plan 让 " + str(P["shards"]) + " 与当前 fixture 同代")

    merged = {}
    for index, want in enumerate(plan):
        path = P["root"] / shard_name(args.tag, index, "answers")
        rows = read_jsonl_rows(path)
        if len(rows) != len(want):
            refuse("片 %03d 只拿着 %d/%d 行（%s）⇒ 拒合并半窗"
                   % (index, len(rows), len(want), ",".join(want)), "先 --run 把这一片补齐")
        for row in rows:
            rid = str(row.get("id"))
            if not str(row.get("answer") or "").strip():
                refuse("片 %03d 里 %s 的 answer 是空串：空串会被评分端当成「没问过」" % (index, rid))
            if rid in merged:
                refuse("跨片重复答案行：" + rid + "（分片不许让同一题被写进两片）")
            merged[rid] = row
        if sorted(str(row.get("id")) for row in rows) != sorted(str(item) for item in want):
            refuse("片 %03d 的行数对，但题号与本片不符 ⇒ 拒合并：%s" % (index, path),
                   "先 --run 重打这一片")

    missing = [rid for rid in ids if rid not in merged]
    extra = sorted(set(merged) - set(ids))
    if missing or extra:
        refuse("合并处的覆盖闸：missing=" + str(missing) + " extra=" + str(extra))

    samples = sorted({str(row.get("answer_source")) for row in merged.values()
                      if str(row.get("answer_source")) == "dry-run"})
    if samples and not args.allow_sample_merge:
        refuse("盘上的片是 dry-run 样本（answer_source=" + ",".join(samples) +
               "）：样本≈满分，绝不许拼成质量基线",
               "确要落一份演练件就加 --allow-sample-merge（并把它当结构演练，不当读数）")

    refuse_inside_repo(P["answers"], "合并件")
    body = "".join(json.dumps(merged[rid], ensure_ascii=False) + "\n" for rid in ids)
    P["answers"].parent.mkdir(parents=True, exist_ok=True)
    P["answers"].write_text(body, encoding="utf-8")
    log("committed %d answers -> %s（顺序 == fixture 原序）" % (len(ids), str(P["answers"])))
    if samples:
        log("DRY RUN 合并件：结构演练，NOT 质量基线")

    side_rows = read_jsonl_rows(P["sidecar"])
    side_ids = [str(row.get("id")) for row in side_rows]
    duplicates = len(side_ids) - len(set(side_ids))
    frame_rows = read_jsonl_rows(P["frames"])
    log("sidecar rows=%d unique=%d duplicate=%d（duplicate>0 即某片被整片重打过，如实报、不去重）"
        % (len(side_rows), len(set(side_ids)), duplicates))
    log("frames 账 rows=%d -> %s" % (len(frame_rows), str(P["frames"])))
    log("评分仍走在册尺：python scripts/run_quality_evaluation.py --fixture %s --answers %s --output ..."
        % (str(fixture), str(P["answers"])))
    return RC_OK

def report_plan(args, P: dict, live: dict, fixture: Path, ids: list) -> int:
    """只读地把这一窗的当前状态念一遍（开窗前先看这一格，别拿猜的去开窗）。"""
    plan = build_plan(ids, args.shard_size)
    state = resume_plan_state(plan, args.tag, P["root"])
    log("tag=%s fixture=%s ids=%d shard_size=%d shards=%d done=%d todo=%d"
        % (args.tag, str(fixture), len(ids), args.shard_size, state["shards"], len(state["done"]),
           len(state["todo"])))
    log("指纹现取：revision=%s backend=%r fixture=%s transport=%s probe_ok=%s"
        % ((live["revision"][:7] or "unknown"), live["index_backend"], live["fixture_sha256"][:12],
           live["transport"], live["probe_ok"]))
    if live["probe_errors"]:
        log("  容器读数缺口：" + "；".join(live["probe_errors"]))
    if P["window"].exists():
        recorded = json.loads(P["window"].read_text(encoding="utf-8"))
        bad = fingerprint_mismatch(recorded, live)
        log("window.json=%s（五项指纹 matches live: %s%s）"
            % (str(P["window"]), "yes" if not bad else "NO", "" if not bad else " -> " + "、".join(bad)))
    else:
        log("window.json 不在：这一窗还没开过（--run 会先落指纹再动手）")
    return RC_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="R570：长跑评测窗的断点保护驱动（分片落盘＋指纹闸；不碰采集器与评分尺）")
    parser.add_argument("--tag", required=True, help="窗名，如 run13（产物全按它命名）")
    parser.add_argument("--shard-size", type=int, default=DEFAULT_SHARD_SIZE,
                        help="每片题数（默认 1＝逐题断点；>1 时一片里任一题失败会整片重打，"
                             "sidecar 会留下第二行）")
    parser.add_argument("--fixture", default=str(REPO_ROOT / "tests" / "fixtures"
                                                 / "business_evaluation_100.jsonl"))
    parser.add_argument("--transport", default=DEFAULT_TRANSPORT)
    parser.add_argument("--expect-backend", default="",
                        help="钉死读路径：pgvector 或 chroma（chroma＝容器该变量为空）")
    parser.add_argument("--plan", action="store_true", help="只念分片计划与续跑状态")
    parser.add_argument("--run", action="store_true", help="把所有未完成的片跑完")
    parser.add_argument("--commit", action="store_true", help="按 fixture 原序拼 <tag>-answers.jsonl")
    parser.add_argument("--retries", type=int, default=2, help="失败片的额外补跑轮数")
    parser.add_argument("--dead-streak", type=int, default=DEAD_STREAK_DEFAULT,
                        help="连续这么多片零产出即判后端已死，停窗保进度")
    parser.add_argument("--retry-sleep", type=float, default=45.0)
    parser.add_argument("--dry-run", action="store_true",
                        help="用采集器自带的假 transport 演练整条机械：零模型调用")
    parser.add_argument("--tmp-dir", default=str(default_tmp_dir()),
                        help="产物目录（默认 EB_EVAL_TMP_DIR 或 %%TEMP%%\\evalrun，必须仓外）")
    parser.add_argument("--repo", default=str(REPO_ROOT), help="采集器的工作目录（在册树）")
    parser.add_argument("--python", default=None,
                        help="调采集器用的解释器（默认 EB_EVAL_PYTHON 或当前解释器）")
    parser.add_argument("--env-file", default=None,
                        help="EVAL_PASSWORD 来源（缺省 <repo>/deploy/.env.server；该件未跟踪，"
                             "跑分树里通常没有 ⇒ 要显式指主树工作副本那一枚）")
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--base-url", default=os.environ.get("EVAL_BASE_URL") or DEFAULT_BASE_URL)
    parser.add_argument("--username", default=os.environ.get("EVAL_USERNAME") or DEFAULT_USERNAME)
    parser.add_argument("--lock-port-base", type=int,
                        default=int(os.environ.get("EB_EVAL_LOCK_PORT_BASE") or LOCK_PORT_BASE))
    parser.add_argument("--allow-sample-merge", action="store_true",
                        help="允许把 dry-run 样本片拼成一件（仅结构演练，日志会明写不是基线）")
    return parser


_LOCKS = []


def main(argv: list = None) -> int:
    args = build_parser().parse_args(argv)
    args.python = args.python or default_python()
    args.env_file_explicit = args.env_file is not None
    args.env_file = args.env_file or str(Path(args.repo) / "deploy" / ".env.server")
    try:
        modes = [args.plan, args.run, args.commit].count(True)
        if modes != 1:
            refuse("--plan / --run / --commit 三选一（现在 " + str(modes) + " 枚）")
        if args.shard_size < 1:
            build_plan([], args.shard_size)  # 同一枚闸，别在两处各写一遍文案
        P = paths(args.tag, Path(args.tmp_dir))
        refuse_landing_spots(P, Path(args.repo))
        fixture = Path(args.fixture)
        if not fixture.is_file():
            refuse("fixture 读不到：" + str(fixture))
        ids = load_ids(fixture)
        # 🔴 只有「真窗开跑」才必须问得到容器：--plan 是取证、--commit 是收口，
        # 都不能因为 Docker 停了就念不出状态（run12 就是先关 Docker 再谈收口的）。
        # 🔴 真窗要口令：来源问不到就在开窗前拒（R571 那枚裸崩）。--plan 是取证、--commit 是收口，
        # 两者都不碰凭据，不许被这一格误拦；--dry-run 走采集器自带假 transport，也不要凭据。
        if args.run and not args.dry_run and not os.environ.get("EVAL_PASSWORD"):
            password_from_env_file(Path(args.env_file), args.env_file_explicit)
        live = provenance(args.transport, fixture, args.shard_size, args.container,
                          args.dry_run, require_probe=bool(args.run and not args.dry_run))
        check_read_path(live, args.expect_backend)
        if args.plan:
            return report_plan(args, P, live, fixture, ids)
        if args.run:
            open_window_or_resume(P, live, args.tag, args.dry_run)
            return run_window(args, P, live, fixture, Path(args.repo))
        return merge_shards(args, P, fixture)
    except Refuse as error:
        return error.code


if __name__ == "__main__":
    sys.exit(main())
