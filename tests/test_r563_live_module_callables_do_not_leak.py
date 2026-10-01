"""R563 · 活模块的顶层函数绑定不得跨模块漏：守卫有牙、且不咬还原窗。

病（10-01 实测，同一条 traceback 连撞三遍门，每遍换个受害者，前两遍被当成 xdist 共置假红放过去）：
`tests/test_r354_delete_audit_shares_the_owner_reader.py` 的 `_recapture`/`_rebind` 用裸赋值
`data.record_audit = record` 把一枚假定 `principal` 非 None 的假收集器装进活模块，用例结束没人还原；
同一枚 worker 上的下一模块撞上它——
`test_r180_...::test_preview_without_any_principal_fails_closed` 抛
`AttributeError: 'NoneType' object has no attribute 'username'`，顺着 `except Exception`
滑成 500 `dataset_preview_failed`，正是那枚用例注释里禁止的"把拒绝伪装成故障"。
现场取证：`%TEMP%\\eb-r563-order-<pid>.log` 记到 r180 与 r354 同进程；现场合跑两枚文件 100% 复现（rc=1），
r354 改走 monkeypatch 之后同跑 31 passed。

甲 守卫在册：conftest 里那枚 autouse／module scope 的钉子在册，被盯清单逐枚点名，比的是码体不是身份。
乙 当场咬（牙1）：把被盯模块的一枚顶层函数换成就地定义的假身，模块收工必须红在本模块自己身上，
   而且红过之后活模块已还回真身（受害者不再挨第二下）。
丙 不空转（正证）：什么都没换 ⇒ 收工不红。
丁 不咬还原窗：把盘上那份源码重新 exec 出来的同名函数装回去（新对象、旧身体，r48 那一扇窗的做法）
   ⇒ 收工不红。这条是"守卫不许把既有窗当成凶手"的形状证明。
戊 病本案不许复发：AST 扫 r354，凡对被盯模块绑定的裸赋值一枚都不许剩。
"""
import ast
import io
import os
import sys
import types

import pytest

CONFTEST = os.path.join(os.path.dirname(__file__), "conftest.py")
WATCHED = ("app.api.v1.data", "app.api.v1.chat", "app.common.audit",
           "app.agents.orchestrator", "app.rag.retrieval_pipeline")
R354_REL = "test_r354_delete_audit_shares_the_owner_reader.py"


def _conftest_text():
    return io.open(CONFTEST, encoding="utf-8").read().replace("\r\n", "\n")


def _drive(guard, node):
    """手工跑一遍 module-scoped fixture：返回 (setup 产物, teardown 调用)。"""
    gen = guard.body(node)
    next(gen)
    return gen


class _Node:
    nodeid = "tests/test_r563_live_module_callables_do_not_leak.py"


def test_jia_the_guard_is_registered_and_watches_the_named_modules(eb_r563_guard):
    text = _conftest_text()
    assert "@pytest.fixture(autouse=True, scope=\"module\")" in text
    assert "def eb_r563_live_module_callables_do_not_leak(request):" in text
    assert tuple(eb_r563_guard.watched) == WATCHED, eb_r563_guard.watched
    same = eb_r563_guard.snapshot  # noqa: F841  (拿钉子当在场证明即可)
    # 比码体而不是比身份：这条写在源里，改回 `is` 就等于把 r48 那扇还原窗判成凶手
    assert "ca.co_code == cb.co_code" in text, "守卫的比较口径被改窄成身份比较了：还原窗会集体冤枉"


def test_yi_a_leaked_fake_body_reddens_on_its_own_module(eb_r563_guard):
    from app.api.v1 import data

    original = data.record_audit
    gen = _drive(eb_r563_guard, _Node())

    def fake_body(principal, action, outcome, resource="", reason="", **kwargs):
        return {"poisoned": True}

    data.record_audit = fake_body
    # pytest.fail 抛的是 Failed（BaseException 支系），用 Exception 去接会漏接 ⇒ 反证自己先失真
    with pytest.raises(BaseException) as caught:
        next(gen)
    message = str(caught.value)
    assert "R563" in message, message[:200]
    assert "app.api.v1.data.record_audit" in message, message[:400]
    assert data.record_audit is original, "红完了还没还账：下一模块仍当受害者"


def test_bing_a_clean_module_does_not_redden(eb_r563_guard):
    gen = _drive(eb_r563_guard, _Node())
    done = False
    try:
        next(gen)
    except StopIteration:
        done = True
    assert done, "什么都没换也红：守卫在空转咬人"


def test_ding_a_reexec_of_the_disk_source_is_restoration_not_a_leak(eb_r563_guard):
    from app.api.v1 import data

    path = os.path.join(os.path.dirname(__file__), os.pardir, "app", "api", "v1", "data.py")
    source = io.open(path, encoding="utf-8").read()
    scratch = {}
    keep = {}
    try:
        exec(compile(source, path, "exec"), scratch)  # noqa: S102 - 只落进临时字典，不碰活模块
    except Exception as exc:  # 顶层有依赖时编译不出函数：至少把同名同体的那几枚拿到
        print("[r563] 整份 exec 未竟（%s）：改用可比的子集" % type(exc).__name__)
    for name in ("record_audit", "preview_data_file", "list_data_files"):
        value = scratch.get(name)
        if isinstance(value, types.FunctionType) and name in vars(data):
            keep[name] = getattr(data, name)
            data.__dict__[name] = value
    assert keep, "没拿到任何一枚同名同体的函数：这把刀无从落下"
    gen = _drive(eb_r563_guard, _Node())
    # 上面那次换装发生在 setup 之前，所以 setup 的基线已是"新对象、旧身体"——换一枚真正的假身再验丁
    name, original = next(iter(keep.items()))
    fresh = scratch[name]
    data.__dict__[name] = fresh
    done = False
    try:
        next(gen)
    except StopIteration:
        done = True
    finally:
        for key, value in keep.items():
            data.__dict__[key] = value
    assert done, "重新 exec 出来的同体函数被当成漏：还原窗会被集体冤枉（守卫比的是码体）"


def test_wu_the_case_file_keeps_no_raw_store_on_watched_bindings():
    path = os.path.join(os.path.dirname(__file__), R354_REL)
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    owners = {"data": "app.api.v1.data", "audit": "app.common.audit", "chat": "app.api.v1.chat"}
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Attribute):
            target = node.targets[0]
            if isinstance(target.value, ast.Name) and target.value.id in owners:
                bad.append("%s.%s:%s" % (owners[target.value.id], target.attr, node.lineno))
    assert bad == [], "r354 里又出现裸赋值，守卫之外还得再治一遍：%s" % bad
