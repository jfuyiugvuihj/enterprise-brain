#!/usr/bin/env python3
"""R461 · P-18 开窗前置的唯一仓内量具：先看 PING，再看 answer:* 的枚数。

病灶（总控 09-28 现取）：runbook 的 P-18「开窗前清掉 Redis 的 `answer:*`」在纸面上是对的，
但仓里没有一件东西**执行**它 —— 每班手写一次开窗驱动，每班重踩一次。本班实测那枚手写驱动把
Redis 口令取成了 `EB_EVAL_PASSWORD`（那是跑分账号 `evalbot` 的口令，看板 §3108 定档），
`redis-cli -a <错口令>` 把错误写进 stderr，下游 `... | wc -l` 把空 stdout 数成 **0** ⇒
打印出来的「开窗前该数必须为 0」当场成立，库里实际还有 10 枚缓存键。本班是第二次踩同一根
（第一次见本文「订正三」第 1 条自述）。它是制度性假绿：缓存命中会让报告档跳过队列道，
也会往 P95 里灌约 50 ms 的假时延。

四格硬牙，逐格可摘下来验证（`tests/test_r461_answer_cache_gate.py` 三把反证钉）：
  1 口令**只**从 `deploy/.env.server` 的 `REDIS_PASSWORD` 取，进程环境一律不读；取不到 = rc=2。
  2 第一道牙是 `PING`：回话不等于 `PONG` = rc=2，且**一个枚数都不报**。认证失败时 redis-cli
    的错误走 stderr、stdout 是空的，任何计数挂在这条腿上都是假零。
  3 `--check` 只判不清：`answer:*` 非 0 = rc=1（带着缓存就是不许开窗）；默认模式只
    `DEL answer:*` —— 逐枚点名删，禁 `FLUSHALL`／`FLUSHDB`，键名不合形状当场拒。
  4 清完复扫，仍非 0 = rc=1；清前清后各报一次**其它键族**的枚数自证没碰它们，
    任何非 `answer` 族的数量变少 = rc=1。

用法：
    python scripts/eval_window_answer_cache_gate.py --check   # 开窗前置：只判，不动数据
    python scripts/eval_window_answer_cache_gate.py           # 两相之间：把 answer:* 清掉

退出码：0＝判据成立；1＝缓存没归零／复扫仍有键／别的键族被删少；2＝量具自己没跑成
（口令取不到／PING 不回 PONG／redis-cli 回错误／docker 起不来）。2 永远不是「已通过」。

真连走容器里的 redis-cli：`docker exec -e RG=<口令> <container> sh -lc '...'`，内层用单引号包
整条命令，让**容器里的 shell** 展开 `"$RG"`（这就是「订正三」第 1 条要的那个形态）。件里的
`transport` 是一枚可注入函数，测试全部用替身，不许真去动生产 Redis 的键。
"""
from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
#: 口令的唯一来源 = 这一枚件的这一行。进程环境一律不读，读了就把「取错名字」那条道又放开了。
ENV_FILE_RELATIVE = Path("deploy") / ".env.server"
REDIS_PASSWORD_ENV = "REDIS_PASSWORD"
#: 名字相近的另一枚：跑分账号 evalbot 的登录口令，走 EVAL_PASSWORD 那条道，不是 redis 的。
EVALBOT_ACCOUNT_KEY = "EB_EVAL_PASSWORD"
MISSING_KEY_HINT = "（同文件里的 EB_EVAL_PASSWORD 是跑分账号 evalbot 的口令，不是 redis 的）"
ANSWER_PREFIX = "answer:"
ANSWER_PATTERN = ANSWER_PREFIX + "*"
ANSWER_FAMILY = "answer"
#: redis 在 compose 里的默认服务名是 enterprise-brain-redis-1（docker-compose.yml:13 定了 project）。
DEFAULT_CONTAINER = "enterprise-brain-redis-1"
#: 删除逐枚点名传参，一批 200 枚，不靠 xargs、不靠模式删除。
DELETE_BATCH = 200
#: 只删这个形状的键：扫描里冒出别的东西（空白、引号、控制字符）一律当场拒。
SAFE_ANSWER_KEY_RE = re.compile(r"^answer:[A-Za-z0-9_.:@/-]+$")
#: 「整库清空」那两条：P-18 只许删 answer:*，别的键一枚都不许碰。
BANNED_COMMANDS = ("flushall", "flushdb")

RC_PASS = 0
RC_GATE_FAILED = 1
RC_TOOL_BROKEN = 2

Transport = Callable[[str, str, List[str]], Tuple[int, str, str]]


class GateError(RuntimeError):
    """量具自己跑不成的那一类失败。它必须是非零退出，绝不许被读成「缓存已清」。"""


def env_file_values(path: Path) -> Dict[str, str]:
    """把 env 件读成一张键值表（与 seed_workspace / check_corpus_parity 同一口径）。"""
    values: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def read_redis_password(env_file: Path) -> str:
    """口令只从 env_file 的 REDIS_PASSWORD 取；取不到就当场停，不回落到进程环境。"""
    if not env_file.is_file():
        raise GateError(f"{REDIS_PASSWORD_ENV} 取不到：{env_file} 不存在（口令只认这一枚件）")
    values = env_file_values(env_file)
    secret = values.get(REDIS_PASSWORD_ENV, "")
    if not secret:
        raise GateError(
            f"{REDIS_PASSWORD_ENV} 取不到：{env_file} 里没有非空的这一行{MISSING_KEY_HINT}"
        )
    return secret


def docker_exec_transport(container: str, secret: str, argv: List[str]) -> Tuple[int, str, str]:
    """在容器里跑一条 redis-cli，口令由**容器内的 shell** 展开。

    形态就是「订正三」第 1 条要的那个：`docker exec -e RG=<口令原文> <container> sh -lc
    'redis-cli --no-auth-warning -a "$RG" ...'`。旧写法把 `$REDIS_PASSWORD` 关在内层双引号里，
    外层先剥引号、容器里不回展开 ⇒ redis-cli 拿空口令连 ⇒ 错误进 stderr、stdout 空，
    下游 `wc -l` 数出 0，看着像「缓存已清」。这里口令走 `-e`，命令走单引号，两者不同轨。
    """
    inner = " ".join(
        ["redis-cli", "--no-auth-warning", "-a", '"$RG"'] + [shlex.quote(part) for part in argv]
    )
    cmd = ["docker", "exec", "-e", "RG=" + secret, container, "sh", "-lc", inner]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120)
    except FileNotFoundError as error:
        raise GateError("docker 不可用：本量具靠容器里的 redis-cli 读数，起不起来就不是「已清」") from error
    except subprocess.TimeoutExpired:
        raise GateError("docker exec 超时（120 s）：redis-cli 这一条没有跑成")
    return proc.returncode, proc.stdout, proc.stderr


def _shown(argv: List[str]) -> str:
    return " ".join(argv[:3]) + (" ..." if len(argv) > 3 else "")


class RedisCli:
    """一条 redis-cli 的薄封装：任何「命令没跑成」的形状都抛 GateError，不返回一个数让你猜。"""

    def __init__(self, secret: str, container: str = DEFAULT_CONTAINER,
                 transport: Optional[Transport] = None) -> None:
        self._secret = secret
        self._container = container
        self._transport: Transport = transport or docker_exec_transport

    def _run(self, argv: List[str]) -> str:
        banned = [name for name in BANNED_COMMANDS if name in {part.lower() for part in argv}]
        if banned:
            raise GateError(
                f"本量具禁发 {'/'.join(name.upper() for name in banned)}："
                "P-18 只许点名 DEL answer:*，别的键一枚都不许碰"
            )
        rc, out, err = self._transport(self._container, self._secret, list(argv))
        if rc != 0:
            raise GateError(
                f"redis-cli 没跑成（rc={rc}，argv={_shown(argv)}）："
                f"{(err or out).strip() or '无输出'}"
            )
        if err.strip():
            raise GateError(
                f"redis-cli 回话里有 stderr（argv={_shown(argv)}）：{err.strip()}"
                " ⇒ 这条命令本身没跑成，它的 stdout 一个字符都不算数"
            )
        return out

    def ping(self) -> str:
        return self._run(["ping"]).strip()

    def scan(self, pattern: Optional[str] = None) -> List[str]:
        argv = ["--scan"] + (["--pattern", pattern] if pattern else [])
        out = self._run(argv)
        return [line.strip() for line in out.splitlines() if line.strip()]

    def dbsize(self) -> int:
        raw = self._run(["dbsize"]).strip()
        try:
            return int(raw)
        except ValueError:
            raise GateError(f"dbsize 回的不是个数：{raw!r} ⇒ 读数不可信，不判")

    def delete(self, keys: List[str]) -> int:
        removed = 0
        for start in range(0, len(keys), DELETE_BATCH):
            batch = keys[start:start + DELETE_BATCH]
            for key in batch:
                if not SAFE_ANSWER_KEY_RE.match(key):
                    raise GateError(f"拒绝删除形状不对的键：{key!r}（只许 answer:<...>）")
            out = self._run(["DEL"] + batch)
            tail = out.strip().splitlines()[-1].strip() if out.strip() else ""
            try:
                removed += int(tail)
            except ValueError:
                raise GateError(f"DEL 回的不是个数：{tail!r} ⇒ 删除结果读不出来，不判")
        return removed


def key_families(keys: List[str]) -> Dict[str, int]:
    """按第一枚冒号前的族名归堆：answer / ratelimit / queue ... 用来自证没碰别的键。"""
    families: Dict[str, int] = {}
    for key in keys:
        family = key.split(":", 1)[0]
        families[family] = families.get(family, 0) + 1
    return families


def format_families(families: Dict[str, int]) -> str:
    if not families:
        return "（无）"
    return " ".join(f"{name}={count}" for name, count in sorted(families.items()))


class Snapshot:
    def __init__(self, answer_keys: List[str], families: Dict[str, int], dbsize: int) -> None:
        self.answer_keys = answer_keys
        self.families = families
        self.dbsize = dbsize

    @property
    def answer_count(self) -> int:
        return len(self.answer_keys)

    def other_families(self) -> Dict[str, int]:
        return {name: count for name, count in self.families.items() if name != ANSWER_FAMILY}


def take_snapshot(client: RedisCli) -> Snapshot:
    """两枚独立读数对账：--scan --pattern 与全库扫描必须数出同一个 answer 族，否则不判。"""
    answer_keys = client.scan(ANSWER_PATTERN)
    for key in answer_keys:
        if not SAFE_ANSWER_KEY_RE.match(key):
            raise GateError(f"扫描里冒出形状不对的答案键：{key!r} ⇒ 不许按这个名字删")
    all_keys = client.scan()
    families = key_families(all_keys)
    if families.get(ANSWER_FAMILY, 0) != len(answer_keys):
        raise GateError(
            f"两枚读数不一致：--scan --pattern {ANSWER_PATTERN} 数到 {len(answer_keys)} 枚，"
            f"全库扫描把 answer 族数到 {families.get(ANSWER_FAMILY, 0)} 枚 ⇒ 扫描本身不可信，不判"
        )
    return Snapshot(answer_keys=answer_keys, families=families, dbsize=client.dbsize())


def run_gate(client: RedisCli, check_only: bool, emit: Callable[[str], None]) -> int:
    # 第 2 格：PING 先行。这道牙没过，后面一枚数都不许报 —— 报出来的零就是那枚假零。
    ping = client.ping()
    if ping != "PONG":
        emit(f"[P-18] PING 回的是 {ping!r}，不是 'PONG' ⇒ redis 没鉴权通过（或连的不是那台）")
        emit("[P-18] 这一刻**不报任何枚数**：认证失败时 redis-cli 的错误走 stderr、stdout 是空的，")
        emit("[P-18] 把那个空数当成「缓存已清」就是本件的病灶（runbook 订正三第 1 条＝本班第二次踩）。")
        emit(f"[P-18] 口令只认 {REDIS_PASSWORD_ENV}，不是 {EVALBOT_ACCOUNT_KEY}"
             "（后者是跑分账号 evalbot 的登录口令，两枚名字相近、用途不同）")
        emit(f"[P-18] verdict: FAIL rc={RC_TOOL_BROKEN}（量具没跑成，不是「已清」）")
        return RC_TOOL_BROKEN
    emit("[P-18] PING = PONG ⇒ 这条命令本身跑成了，接下来的计数才算数")

    before = take_snapshot(client)
    emit(f"[P-18] answer:* = {before.answer_count} 枚（dbsize={before.dbsize}）")
    emit(f"[P-18] 旁证·其它键族 清前 = {format_families(before.other_families())}")

    if check_only:
        if before.answer_count:
            emit(f"[P-18] --check：库里带着 {before.answer_count} 枚答案缓存 ⇒ 不许开窗（本模式只判不清）")
            emit(f"[P-18] verdict: FAIL rc={RC_GATE_FAILED}")
            return RC_GATE_FAILED
        emit("[P-18] --check：0 枚，而且是 PING 过之后读到的 0 ⇒ 可以开窗")
        emit("[P-18] verdict: PASS")
        return RC_PASS

    if before.answer_count == 0:
        emit("[P-18] 已经是 0 枚，不发 DEL")
        emit("[P-18] verdict: PASS")
        return RC_PASS

    removed = client.delete(before.answer_keys)
    emit(f"[P-18] 已发 DEL：点名 {len(before.answer_keys)} 枚 answer:* 键，redis 回 removed={removed}"
         "（未发 FLUSHALL/FLUSHDB，别的键族不进参数表）")

    after = take_snapshot(client)
    emit(f"[P-18] 旁证·其它键族 清后 = {format_families(after.other_families())}")
    if after.answer_count:
        sample = ", ".join(repr(key) for key in after.answer_keys[:5])
        emit(f"[P-18] 复扫仍有 {after.answer_count} 枚（例：{sample}）⇒ 没清干净，不许开窗")
        emit(f"[P-18] verdict: FAIL rc={RC_GATE_FAILED}")
        return RC_GATE_FAILED

    shrunk = {
        name: (count, after.families.get(name, 0))
        for name, count in before.families.items()
        if name != ANSWER_FAMILY and after.families.get(name, 0) < count
    }
    if shrunk:
        detail = ", ".join(f"{name} {was}->{now}" for name, (was, now) in sorted(shrunk.items()))
        emit(f"[P-18] 别的键族在这一趟里变少了：{detail} ⇒ 「只删了 answer:*」这句不成立，不许开窗")
        emit(f"[P-18] verdict: FAIL rc={RC_GATE_FAILED}")
        return RC_GATE_FAILED

    emit("[P-18] 复扫 0 枚，其它键族一枚没少 ⇒ 答案缓存已清")
    emit("[P-18] verdict: PASS")
    return RC_PASS


def main(argv: Optional[List[str]] = None, *, transport: Optional[Transport] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eval_window_answer_cache_gate.py",
        description="P-18 开窗前置：先看 PING 再看 answer:* 枚数，只点名删 answer:*，禁 FLUSHALL。",
    )
    parser.add_argument("--check", action="store_true", help="只判不清：answer:* 非 0 就非零退出")
    parser.add_argument(
        "--repo-root", type=Path, default=REPO_ROOT,
        help="deploy/.env.server 所在的那棵树（在跑分树里跑就指主树，那文件是 gitignored 的）",
    )
    parser.add_argument("--container", default=DEFAULT_CONTAINER, help="redis 容器名")
    args = parser.parse_args(argv)

    env_file = (args.repo_root.resolve() / ENV_FILE_RELATIVE)

    def emit(text: str) -> None:
        print(text)

    try:
        secret = read_redis_password(env_file)
    except GateError as error:
        print(f"[P-18] {error}", file=sys.stderr)
        print(f"[P-18] verdict: FAIL rc={RC_TOOL_BROKEN}（口令取不到，量具没跑成）", file=sys.stderr)
        return RC_TOOL_BROKEN

    emit(f"[P-18] 模式={'check（只判不清）' if args.check else 'clear（可点名删 answer:*）'} · "
         f"口令={REDIS_PASSWORD_ENV} len={len(secret)} 取自 {env_file} · 容器={args.container}")

    client = RedisCli(secret=secret, container=args.container, transport=transport)
    try:
        return run_gate(client, args.check, emit)
    except GateError as error:
        print(f"[P-18] {error}", file=sys.stderr)
        print(f"[P-18] verdict: FAIL rc={RC_TOOL_BROKEN}（量具没跑成，不是「缓存已清」）", file=sys.stderr)
        return RC_TOOL_BROKEN


if __name__ == "__main__":
    sys.exit(main())
