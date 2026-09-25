"""R236 T1：观测件不许把业务请求打死 —— `app/trace/store.py` 的 `logger` 补 import。

R233 扫出的那枚活雷：`_observe_request_window` 的 `except Exception as exc:` 里写着
`logger.warning(...)`，而这枚文件从来没 import 过 `logger`。后果不是"少一行日志"，是
兜底自己抛 `NameError` 顶掉原异常，再顺着 `record_event`（同一把 RLock 内、无外层兜底）
抛回调用方 —— 而调用方是 `app/api/v1/chat.py` 与 `app/agents/orchestrator.py`。函数注释
里那句 "a counter is never a request failure" 当场不成立。

修法只有一句 import（判据②：零语义夹带 —— 捕获范围、日志级别、返回形状一字未动）。
本件钉的是修后的三件事：
1. try 块里真抛异常时，调用方拿到的还是"没有异常"这个语义，且日志落了一行、里面是**原**异常；
2. `NameError` 这枚二次替换从链路上消失（第 1 条就是它的反证）；
3. 什么都不坏时计数器照旧加窗 —— 别把"不炸"修成"什么都不干"。

全程不连库、不打模型：TraceStore 写 tmp_path，persistence 留 None。
"""
import logging

import pytest

import app.common.logger as logger_module
import app.common.stage_timing as stage_timing
import app.trace.store as trace_store
from app.trace.store import TraceStore


@pytest.fixture
def store(tmp_path):
    return TraceStore(tmp_path / "trace.jsonl")


def test_the_module_binds_the_logger_it_uses():
    """修前必红的最短形状：这枚文件的名字空间里今天必须有 `logger`，而且是仓里那枚。"""
    assert getattr(trace_store, "logger", None) is logger_module.logger


def test_a_failing_observer_returns_the_event_and_logs_the_original_error(store, monkeypatch, caplog):
    """判据③的行为钉本体：try 块抛 RuntimeError ⇒ 调用方不接异常，日志里是那枚 RuntimeError。

    修前这一枚红在别处：兜底 `logger.warning` 自己 NameError，调用方拿到的是
    `NameError: name 'logger' is not defined`，原异常只活在 `__context__` 里。
    """
    def boom():
        raise RuntimeError("PROBE: the observation layer exploded")

    monkeypatch.setattr(stage_timing, "stage_timing_enabled", boom)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        event = store.record_event(
            trace_id="t-1", request_id="r-1", event_type="request.started", status="ok")

    assert event["event_type"] == "request.started"
    lines = [rec.getMessage() for rec in caplog.records]
    assert any("[Trace] request window was not recorded" in line for line in lines), lines
    assert any("PROBE: the observation layer exploded" in line for line in lines), \
        "日志要记的是原异常，不是 NameError"
    assert not any("is not defined" in line for line in lines), lines


def test_the_in_try_import_failing_is_also_swallowed(store, monkeypatch, caplog):
    """不碰产品码的第二个入口：try 块里那句函数内 import 失败，同样不许冒到调用方。"""
    import sys

    monkeypatch.setitem(sys.modules, "app.common.stage_timing", None)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        event = store.record_event(
            trace_id="t-2", request_id="r-2", event_type="request.started", status="ok")

    assert event["trace_id"] == "t-2"
    assert "request window was not recorded" in caplog.text


def test_the_event_is_still_on_disk_after_the_observer_fails(store, tmp_path, monkeypatch):
    """账不能跟着观测件一起丢：异常发生在 append 之后，那一行必须还在盘上。"""
    def boom():
        raise RuntimeError("PROBE: after the write")

    monkeypatch.setattr(stage_timing, "stage_timing_enabled", boom)
    path = tmp_path / "trace.jsonl"

    store.record_event(trace_id="t-3", request_id="r-3", event_type="request.started", status="ok")

    assert path.read_text(encoding="utf-8").count('"t-3"') == 1


def test_the_window_is_still_recorded_when_nothing_fails(store, monkeypatch):
    """正向形状：把异常摘掉，热路径上的 request window 照样进台账 —— 修后不是"只是不炸"。"""
    monkeypatch.delenv("STAGE_TIMING_ENABLED", raising=False)
    stage_timing.reset_stage_ledger()
    try:
        store.record_event(trace_id="t-ok", request_id="r-ok",
                           event_type="request.started", status="ok")
        store.record_event(trace_id="t-ok", request_id="r-ok",
                           event_type="request.completed", status="ok")

        windows = stage_timing.default_stage_ledger().request_windows()
    finally:
        stage_timing.reset_stage_ledger()

    assert "t-ok" in windows, windows
    assert windows["t-ok"] >= 0.0
