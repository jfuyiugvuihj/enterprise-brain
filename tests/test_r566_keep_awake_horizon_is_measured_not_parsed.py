r"""R566 的常驻钉：keep-awake 那一格的覆盖时长必须**量出来**，不许从命令行里**抠一个数**。

判据出处＝跟进单 §148 第一节 R566 五格。来历（本席 10-02 现读代码坐实）：
`scripts/r530_run10_window_preflight.py` 旧写法用 `KEEP_AWAKE_MINUTES` 从命令行抠一个数当「剩余分钟」，
而真实命令行是 `python scripts\window_keep_awake.py --interval 240 --loop`——数字落在 `--interval` 之后，
那条正则要求 `keep_awake.py` 后紧跟 `\S+` 再紧跟数字，因此**永不命中**，每一枚调用都走 `minutes=240.0`
兜底。后果是两种假读数同时存在：

  · 假绿：开窗后四小时内恒 PASS，哪怕锁其实没在续——那一格从没读过 `stamp`，也没读
    `window_keep_awake.check_stamp()`（`MAX_STAMP_AGE_SECONDS = 300` 正是为这件事存在）。
  · 假红：同一枚活着且每 240 s 真在续锁的常驻进程，起 4 小时之后被判「已过期」并 FAIL；
    `--need-minutes > 240` 对新挂的锁**永远不可能过**。本席 10-02 那次 7/7 PASS 是把需求降到
    180 才拿到的——没吹锁，但过的理由不对，而这枚假红今晚就会正好卡在 21:13 之后把 run13 拦死。

口径：`--loop` 的覆盖时长是「进程活着就无限」，有界的只有 `--once`；`--interval` 的单位是**秒**，
不是分钟；本格能证的只有「上一次真续锁距今多久」。四枚形状各自独立可红。
"""
from __future__ import annotations

import os
import importlib.util
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GAUGE_PATH = REPO / "scripts" / "r530_run10_window_preflight.py"
LOOP_CMD = r'"C:\py\python.exe" -X utf8 scripts\window_keep_awake.py --interval 240 --loop --stamp '
FOREVER = 10_000_000.0


def _load_gauge():
    spec = importlib.util.spec_from_file_location("eb_r530_gauge", GAUGE_PATH)
    module = importlib.util.module_from_spec(spec)
    #: 必须先登记再 exec：那枚 Snapshot 用 @dataclass，dataclasses 处理会回到
    #: sys.modules[cls.__module__] 取命名空间，没登记就当场 AttributeError（本钉 10-02 亲自撞过）。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_stamp(tmp_path, now: float, age_seconds: float):
    """造一枚真 stamp 并**把 mtime 拨到 age_seconds 前**。

    🔴 `check_stamp` 判新鲜度用的是 `os.path.getmtime(path)`，不是文件里那串 AT——本钉第一版
    只改了文本、mtime 停在「刚落盘」，于是过期那格照样判 PASS（10-02 现跑撞到的，记下来免得
    再交一枚假牙）。AT 照样写，因为缺 PREV 字段会被判「不像本件写的锁文件」。
    """
    stamp = tmp_path / "ka.txt"
    when = time.localtime(now - age_seconds)
    stamp.write_text("PREV=0x80000003 REQUESTED=0x80000003 PID=4242 AT=%s\n"
                     % time.strftime("%Y-%m-%dT%H:%M:%S+0800", when), encoding="utf-8")
    os.utime(stamp, (now - age_seconds, now - age_seconds))
    return stamp


def _cell(gauge, processes, now):
    snap = gauge.Snapshot(provenance_rc=0, provenance_text="", cache_rc=0,
                          processes=processes, create_times={}, gpu_apps=[], gpu_seen=True,
                          now=now)
    rows = dict((name, (status, note)) for name, status, note in gauge.evaluate(snap, 180))
    assert "keep_awake" in rows, "evaluate() 不再交回 keep_awake 那一格：本钉与开窗前置一起失效"
    return rows["keep_awake"]


def test_live_loop_with_fresh_stamp_passes_even_after_four_hours(tmp_path):
    """判据①② 的正例：起于 5 小时前的常驻 --loop + 新鲜 stamp 必须 PASS（旧写法在这里判「已过期」）。"""
    gauge = _load_gauge()
    now = time.time()
    stamp = _write_stamp(tmp_path, now, 60.0)
    status, note = _cell(gauge, [{"ProcessId": 4242, "CommandLine": LOOP_CMD + str(stamp)}], now)
    assert status == gauge.PASS, "活着的常驻锁被判 FAIL（读数：%s）——那正是拦死今晚 run13 的假红" % note
    assert "240 s" in note, "续锁间隔没按秒进读数：%s" % note
    assert "自复核" in note, "窗长超过可证到此刻那一段，却不交「窗内自复核」那句：%s" % note


def test_stale_stamp_with_live_process_is_red(tmp_path):
    """判据① 的牙（b 格）：进程还活着但 stamp 过期 ⇒ 必须 FAIL，且话术要点明「锁没在续」。"""
    gauge = _load_gauge()
    now = time.time()
    stamp = _write_stamp(tmp_path, now, 3_000.0)
    status, note = _cell(gauge, [{"ProcessId": 4242, "CommandLine": LOOP_CMD + str(stamp)}], now)
    assert status == gauge.FAIL, "stamp 三千米没人续却判过：那一格就又把「没量到」冒充成「通过」了（%s）" % note


def test_once_mode_is_not_treated_as_a_horizon_in_minutes(tmp_path):
    """判据② ：`--once` 才是有界那一支，且必须因为「不是常驻」而红，不许换算成一个到期分钟数。"""
    gauge = _load_gauge()
    now = time.time()
    stamp = _write_stamp(tmp_path, now, 30.0)
    cmd = '"C:\\py\\python.exe" -X utf8 scripts\\window_keep_awake.py --once --stamp %s' % stamp
    status, note = _cell(gauge, [{"ProcessId": 7, "CommandLine": cmd}], now)
    assert status == gauge.FAIL, "--once 那一发被判成常驻锁：%s" % note
    assert "min" not in note, "读数里冒出「剩余/已过期 X min」那种旧形状（本单明令不许）：%s" % note


def test_missing_process_is_red_and_names_the_remedy():
    """判据④ ：进程不在位 ⇒ FAIL，且必须交回可执行补法，而不是一个过期分钟数。"""
    gauge = _load_gauge()
    status, note = _cell(gauge, [{"ProcessId": 9, "CommandLine": "python -m pytest -q"}], time.time())
    assert status == gauge.FAIL
    assert "window_keep_awake.py --loop" in note, "没交补法的 FAIL 等于让操作员自己猜：%s" % note


def test_the_parsed_minutes_regex_is_gone_and_cannot_come_back():
    """判据③ 的反弹牙：那条把命令行当覆盖时长的正则一旦复活，本单立刻红。"""
    gauge = _load_gauge()
    assert not hasattr(gauge, "KEEP_AWAKE_MINUTES"), (
        "KEEP_AWAKE_MINUTES 复活了：它对着真实命令行永不命中，两枚假读数会一起回来")
    assert hasattr(gauge, "keep_awake_interval") and hasattr(gauge, "keep_awake_freshness"), (
        "两枚把手少一枚：覆盖时长就又是抠出来的而不是量出来的")
    assert gauge.keep_awake_interval("--interval 90 --loop") == 90, "续锁间隔没按秒读"


def test_the_real_stamp_on_this_machine_is_readable_not_assumed(tmp_path, monkeypatch):
    """判据① 的现场一格：`--stamp` 缺省路径必须真问得到东西——量不到就 FAIL，绝不默认「挂上了」。"""
    gauge = _load_gauge()
    missing = tmp_path / "definitely-not-here.txt"
    fresh, phrase = gauge.keep_awake_freshness(str(missing), time.time())
    assert fresh is False, "问不到 stamp 却交回 True：那是本单治的第一枚假绿（%s）" % phrase
    assert phrase, "FAIL 却不说话＝操作员拿不到原因：%s" % (phrase,)