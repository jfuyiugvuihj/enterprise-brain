# -*- coding: utf-8 -*-
"""R511·P-19 执行状态锁的牙（总控自修件，判据全在本文件里，零网络零容器零模型）。

为什么这组牙存在：P-19 从前靠一枚仓外手写进程自证，进程死了就没人量；本席 09-29 把工具
落进仓内，同时撞上两枚真坑，一人一手：
  坑一：ctypes 不声明 restype/argtypes 时，0x80000003 被当有符号 int 传，API 交回 None。
  坑二：SetThreadExecutionState 交回的是「上一次」的执行需求位。照 runbook §17「订正二」
        原话等 `0x80000003`、并把 `0x80000000` 判成「没挂上」，恰好会把**第一次调用的正常
        成功值**读成失败。⇒ 成功判据只能是「非 0」。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import window_keep_awake as lock  # noqa: E402


def _write(tmp_path, body, age_seconds=0):
    path = os.path.join(str(tmp_path), "ka.txt")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    if age_seconds:
        os.utime(path, (time.time() - age_seconds, time.time() - age_seconds))
    return path


def test_a1_success_is_nonzero_and_only_nonzero():
    assert lock.lock_succeeded(0x80000000) is True
    assert lock.lock_succeeded(0x80000003) is True
    assert lock.lock_succeeded(0) is False


def test_a2_the_first_call_value_is_not_a_failure(tmp_path):
    """坑二正向：第一次调用正常交回 0x80000000，判器必须当它是挂上了。"""
    path = _write(tmp_path, "PREV=0x80000000 REQUESTED=0x80000003 PID=1 AT=x\n")
    ok, why = lock.check_stamp(path)
    assert ok, why
    assert "非 0＝成功" in why


def test_b1_missing_stamp_is_red_with_its_own_name(tmp_path):
    ok, why = lock.check_stamp(os.path.join(str(tmp_path), "nope.txt"))
    assert ok is False
    assert "不存在" in why


def test_b2_zero_return_is_red_and_names_the_api(tmp_path):
    path = _write(tmp_path, "PREV=0x00000000 REQUESTED=0x80000003 PID=1 AT=x\n")
    ok, why = lock.check_stamp(path)
    assert ok is False
    assert "SetThreadExecutionState" in why


def test_b3_stale_lock_is_red_and_says_the_process_died(tmp_path):
    path = _write(tmp_path, "PREV=0x80000003 REQUESTED=0x80000003 PID=1 AT=x\n",
                  age_seconds=lock.MAX_STAMP_AGE_SECONDS + 1)
    ok, why = lock.check_stamp(path)
    assert ok is False
    assert "没续" in why


def test_b4_a_foreign_file_is_not_read_as_a_lock(tmp_path):
    path = _write(tmp_path, "hello world\n")
    ok, why = lock.check_stamp(path)
    assert ok is False
    assert "PREV" in why


def test_c1_write_stamp_roundtrips_into_a_checkable_file(tmp_path):
    path = os.path.join(str(tmp_path), "ka.txt")
    body = lock.write_stamp(path, 0x80000003)
    assert "PREV=0x80000003" in body
    ok, why = lock.check_stamp(path)
    assert ok, why


def test_d1_the_ctypes_signature_is_declared():
    """坑一的牙：签名没声明过一次，本件的锁当场交回 None 而被读成「失败」。"""
    if not sys.platform.startswith("win"):
        raise AssertionError("这组牙只在 Windows 上判得出签名这件事")
    kernel32 = lock._kernel32()
    assert kernel32.SetThreadExecutionState.restype is not None, "restype 必须声明，否则 DWORD 被截成有符号 int"
    assert kernel32.SetThreadExecutionState.argtypes == [lock.ctypes.wintypes.DWORD], "argtypes 必须声明"


def test_d2_interval_must_not_outlive_the_stamp_grace():
    assert lock.main(["--once", "--interval", str(lock.MAX_STAMP_AGE_SECONDS + 1)]) == 2
    assert lock.main(["--loop", "--interval", "0"]) == 2


def test_e1_counter_evidence_success_cannot_be_redefined_as_bitwise_containment():
    """反证钉：若把成功判据改成「返回值含本次请求位」，第一次调用就会被读成失败——
    那正是 09-24 那班「稳态才回 0x80000003」的原话会带来的误判。本件不许那样判。"""
    wrong_rule = (0x80000000 & lock.REQUESTED) == lock.REQUESTED
    assert wrong_rule is False
    assert lock.lock_succeeded(0x80000000) is True