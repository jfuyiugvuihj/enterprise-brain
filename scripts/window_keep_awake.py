# -*- coding: utf-8 -*-
"""P-19 执行状态锁的在册工具（R511·09-29 总控自修；「总控自修」先例 #77->72bdf96）。

为什么有这一枚：开窗前置第 10 格（P-19）要求「机器不会中途睡过去」。09-24 那一班是靠
一枚手写常驻进程往 `%TEMP%\ka.txt` 刷数自证的，进程一死、文件一删，这格就变成「没人量过」；
`powercfg /change standby-timeout-ac 0` 单独用是假绿（09-21、09-23 两次 AC=0x0 仍掉进 S0）。

🔴 两条现取口径（第二条推翻了 runbook §17「订正二」的原话，本件按真语义写）：
1. **`SetThreadExecutionState` 交回的是「上一次」的执行需求位，不是刚设进去的那一位**
   （MSDN：returns the previous execution request flags；0 = 失败）。⇒ 判「有没有挂上」
   只能用「返回值非 0」，**不能**要求返回值含本次请求的位。09-24 观察到稳态回
   `0x80000003` 是因为那是 `--loop` 第二次以后的调用：上一次设的就是 `0x80000003`。
   照原话去等 `0x80000000`（订正二原文否掉的那个值）**恰好是第一次调用的正常成功值**。
2. 这把锁是**进程存活期内的临时锁**：本件一行电源设置都不改（业主 09-29 明令「别设为永眠」），
   进程退出即回到该机原有配置。

用法：
    python scripts/window_keep_awake.py --loop --interval 240    # 开窗期常驻
    python scripts/window_keep_awake.py --once                   # 挂一发并落 stamp 就退
    python scripts/window_keep_awake.py --check                  # 判器：stamp 在且新且位非 0
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import os
import sys
import time
from datetime import datetime, timezone

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
REQUESTED = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED

#: stamp 超过这个秒数就算「锁没人续」。09-24 那班 240 s 一续、前置那格写「5 分钟内」，
#: 两值取严：300 s 是上限，不是目标。
MAX_STAMP_AGE_SECONDS = 300

DEFAULT_STAMP = os.path.join(
    os.environ.get("TEMP") or os.getcwd(), "enterprise-brain-window-keep-awake.txt"
)


def _kernel32():
    if not sys.platform.startswith("win"):
        raise RuntimeError("P-19 这把锁只在 Windows 上有意义（SetThreadExecutionState 是 Win32 API）")
    kernel32 = ctypes.windll.kernel32
    #: 🔴 不声明签名时 ctypes 把这枚超 0x7FFFFFFF 的常量当有符号 int 传，符号扩展后
    #: API 收到非法位组合、交回 None（本席 09-29 一手撞上）。声明是必需的，不是讲究。
    kernel32.SetThreadExecutionState.restype = ctypes.wintypes.DWORD
    kernel32.SetThreadExecutionState.argtypes = [ctypes.wintypes.DWORD]
    return kernel32


def set_lock(flags: int = REQUESTED) -> int:
    """挂锁。返回值是 API 语义下的「上一次」执行需求位；**0 才是失败**。"""
    return int(_kernel32().SetThreadExecutionState(flags))


def lock_succeeded(returned: int) -> bool:
    """成功判据只有「非 0」这一条。要求返回值含本次请求位是错的（见模块 docstring 第 1 条）。"""
    return returned != 0


def release_lock() -> int:
    """只留 ES_CONTINUOUS＝把本进程挂的两把需求位清掉（临时锁的正解收法）。"""
    return int(_kernel32().SetThreadExecutionState(ES_CONTINUOUS))


def write_stamp(path: str, returned: int, flags: int = REQUESTED) -> str:
    moment = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    body = "PREV=0x%08X REQUESTED=0x%08X PID=%d AT=%s\n" % (returned, flags, os.getpid(), moment)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return body.strip()


def _fields(text: str) -> dict:
    out = {}
    for token in text.split():
        if "=" in token:
            key, _, value = token.partition("=")
            out[key] = value
    return out


def check_stamp(path: str, now: float | None = None) -> tuple[bool, str]:
    """判器读 stamp 本身：不在／太旧／位为 0，三种红各给名字，不许并成一句「没挂上」。"""
    if not os.path.isfile(path):
        return False, "stamp 文件不存在：" + path + "（没人挂锁，这格根本没量）"
    with open(path, "r", encoding="utf-8") as handle:
        fields = _fields(handle.read())
    if "PREV" not in fields:
        return False, "stamp 里没有 PREV 字段，不像本件写的锁文件：" + text_head(path)
    returned = int(fields["PREV"], 16)
    if not lock_succeeded(returned):
        return False, "PREV=0x00000000 ⇒ 那一发 SetThreadExecutionState 当场失败"
    age = (time.time() if now is None else now) - os.path.getmtime(path)
    if age > MAX_STAMP_AGE_SECONDS:
        return False, "锁超过 %d 秒没续（上次 %.0f s 前）：常驻进程大概已经死了" % (MAX_STAMP_AGE_SECONDS, age)
    return True, "上一次调用交回 PREV=0x%08X（非 0＝成功），%.0f s 前续过，PID=%s" % (
        returned, age, fields.get("PID", "?"))


def text_head(path: str, limit: int = 80) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read(limit).strip()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="P-19 执行状态锁（临时锁，不改任何电源设置）")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="挂一发并写 stamp 就退出")
    mode.add_argument("--loop", action="store_true", help="开窗期常驻，每 --interval 秒续一次")
    mode.add_argument("--check", action="store_true", help="只判 stamp 文件，退出码 0/1")
    parser.add_argument("--stamp", default=DEFAULT_STAMP, help="stamp 文件路径（默认落 %%TEMP%%）")
    parser.add_argument("--interval", type=int, default=240, help="--loop 的续锁间隔秒数")
    args = parser.parse_args(argv)

    if args.check:
        ok, why = check_stamp(args.stamp)
        print("[P-19] stamp=" + args.stamp)
        print("[P-19] " + why)
        print("[P-19] verdict: " + ("PASS" if ok else "FAIL"))
        return 0 if ok else 1

    if not 0 < args.interval <= MAX_STAMP_AGE_SECONDS:
        print("[P-19] --interval 必须落在 (0, %d] 秒里，否则 stamp 自己就先过期" % MAX_STAMP_AGE_SECONDS)
        return 2

    returned = set_lock()
    if not lock_succeeded(returned):
        print("[P-19] SetThreadExecutionState 交回 0 ⇒ 当场失败，不装作挂上了")
        return 1
    print("[P-19] " + write_stamp(args.stamp, returned))
    if args.once:
        print("[P-19] verdict: PASS（单发；正式开窗要的是常驻，请用 --loop）")
        return 0
    print("[P-19] 常驻续锁中（PID=%d，每 %d s 一发）；退出即释放临时锁" % (os.getpid(), args.interval))
    try:
        while True:
            time.sleep(args.interval)
            returned = set_lock()
            if not lock_succeeded(returned):
                print("[P-19] 续锁交回 0 ⇒ 锁掉了，这一窗别再往下读数")
                return 1
            write_stamp(args.stamp, returned)
    except KeyboardInterrupt:
        release_lock()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())