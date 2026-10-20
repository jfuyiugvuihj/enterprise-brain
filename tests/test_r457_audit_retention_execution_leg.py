# -*- coding: utf-8 -*-
r"""R457 · 判据① 的执行腿：审计留存真的排上日程，每一枚调度器 host 都挂得上。

病灶（跟进单 §131 五；本单基点现读，行号一律按符号派生或 rg 现取）：`app/common/audit.py` 里
`DEFAULT_RETENTION_DAYS` 早就在、每一笔事件 stamped 的 `expires_at` 也早就在写、
`purge_expired_audit_events()` 也早就编好，而全仓对它的生产调用点是零 ⇒ 那枚字段没人读，
留存只是纸上的，台账行数只增不减。本件钉的是「腿真长上了」，不是「纸上说了要长」：
注册面、两枚 host、到点那一发，各占一格。

两枚口径沿用在册件，不另起一份：
  · 只记账的假 scheduler 沿用 R425 那族的样子（`add_job` 记账、从不执行，`start()` 也只数一次），
    所以「注册」与「跑成」在这枚桩里不可能混淆。R425 自己那本名册钉
    （`tests/test_r425_offpeak_index_rebuild.py`）逐字钉着「缺省恰两枚」的名册**全等**——
    正因为那本账不在 R457 写域里，这枚 sweep 落在两枚 host 的公共把手上、不落在
    `register_jobs()` 的名册里。搬进去就红在册钉上，本件 TOOTH 4 量的就是这一格：
    它不是本单的口味问题，是写域边界。
  · 反证窗只落 `tests/_temp_edit_overlay.py` 的影子根：变异写进临时目录里那份副本，读出来装进
    一枚一次性模块对象（绝不 exec 进 `app.scheduler.jobs`，理由写在那枚窗的 docstring 里）；
    盘上的 `app/scheduler/jobs.py` 全程只读，进出各量一次 sha256，窗尾自证 `restored` 为真
    且活模块把手逐枚没换过身体。本件一次都不写被跟踪文件（事故 #71 那一族，别撞）。

判据 ↔ 落点
  ① 留存装上执行腿（挂上 scheduler）→ test_the_sweep_is_declared_once_per_host /
     test_the_sweep_clock_is_a_real_moment_and_not_a_second_copy /
     test_the_api_process_host_mounts_the_sweep /
     test_the_standalone_scheduler_process_mounts_the_sweep /
     test_no_host_can_register_jobs_without_the_sweep
  ② 摘掉执行腿 ⇒ 反证钉当场红 → test_teeth_1_the_standalone_host_goes_red /
     test_teeth_2_the_in_process_host_goes_red / test_teeth_3_a_preview_leg_goes_red /
     test_teeth_4_a_fourth_job_on_the_named_surface_goes_red；
     红话点名「这枚字段没人读」那一把在 tests/test_r457_expires_at_has_a_reader.py
  ③④⑤（预览语义／视图那格／记账面）→ 同一本文件，它们守的是 audit 侧的语义，落点也在那边
"""
from __future__ import annotations

import ast
import logging
import subprocess
import types
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.common import audit as audit_module
from app.scheduler import jobs as jobs_module
from app.scheduler.index_rebuild_config import (
    AT_ENV,
    SCHEDULE_ENV,
    TIME_BUDGET_ENV,
    resolve_index_rebuild_window,
)
from tests import _temp_edit_overlay as overlay

REPO = Path(__file__).resolve().parents[1]
JOBS_PY = REPO / "app" / "scheduler" / "jobs.py"
#: 反证钉要摘／改的锚点行：文本按 jobs.py 现读的形状给，命中数不是恰好一枚就整窗不开。
SWEEP_ON_API_HOST = "    register_audit_sweep(scheduler)"
SWEEP_ON_STANDALONE_HOST = "    register_audit_sweep(standalone)"
SWEEP_PURGE_CALL = "    result = purge_expired_audit_events()"
DAILY_REPORT_ANCHOR = '                      id="daily_report", replace_existing=True)'
#: R425 判据② 那本名册钉的缺省读数：本单不搬动它，只借来当落点边界的尺。
NAMED_SURFACE_IDS = ["alert_check", "daily_report"]
#: 清扫到点该交回的那五个词：唯一事实源在 audit 那边，这里只认它给的面。
PURGE_REPORT_KEYS = {"status", "reason", "checked", "expired", "purged"}


@dataclass(frozen=True)
class Registered:
    """add_job 被塞了什么。只读，从不执行。"""

    func: object
    trigger: str | None
    options: dict


class RecordingScheduler:
    """Duck-typed scheduler：`add_job` 与 `start()` 都只记账，真线程一枚也不起。"""

    def __init__(self) -> None:
        self.registered: list[Registered] = []
        self.starts = 0
        self.running = False

    def add_job(self, func, trigger=None, **options) -> None:
        self.registered.append(Registered(func=func, trigger=trigger, options=options))

    def start(self) -> None:
        self.starts += 1
        self.running = True


def ids(fake: RecordingScheduler) -> list[str]:
    return [str(job.options.get("id", "")) for job in fake.registered]


def assert_sweep_mounted(fake: RecordingScheduler, host: str) -> None:
    """名册上有没有那一格。绿件与反证钉共读这一段判断，不另起第二份口径。"""
    assert ids(fake).count(jobs_module.AUDIT_SWEEP_JOB_ID) == 1, (
        f"{host} 没把审计留存清扫挂上日程 ⇒ expires_at 仍是一枚没人读的字段："
        f"留存只有定义、没有执行腿，台账行数只增不减。名册现读={ids(fake)}"
    )


def assert_named_surface_is_r425_two(fake: RecordingScheduler) -> None:
    """`register_jobs()` 的名册仍是 R425 那两枚：本单的腿长在 host 层，不是这里。"""
    assert ids(fake) == NAMED_SURFACE_IDS, (
        "register_jobs() 的名册漂了：R425 判据② 那族在册钉按这一格逐字钉死，现读="
        f"{ids(fake)}。第四枚 job 要走 host 层的 register_audit_sweep()；要搬进名册，"
        "得先改那本账，而那不在 R457 写域里。"
    )


def assert_the_leg_actually_purges(args: tuple, kwargs: dict) -> None:
    """到点那一发打的是清账，不是预览：预览只报数，一枚也不清。"""
    assert args == () and kwargs.get("dry_run") is not True, (
        "审计留存清扫开的是预览（dry_run=True）⇒ 它一枚都不清，expires_at 仍然是"
        f"一枚没人读的字段。位置参数={args} 关键字参数={kwargs}"
    )


def _callee_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _callers_of(sources: dict[str, str], name: str) -> set[tuple[str, str]]:
    """哪些 (文件, 函数) 的体里出现了 `name(...)` 这枚调用；def 那一行不算，模块级也算 `<module>`。"""
    hits: set[tuple[str, str]] = set()

    def visit(node, scope):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, (rel, child.name))
                continue
            if isinstance(child, ast.Call) and _callee_name(child) == name:
                hits.add(scope)
            visit(child, scope)

    for rel, text in sources.items():
        visit(ast.parse(text), (rel, "<module>"))
    return hits


def production_sources(root=None) -> dict[str, str]:
    """生产码的全部 .py 文本（`app/**` 与 `deploy/**`）。

    读的是当前视图：窗外＝盘上的被跟踪文件，反证窗内＝影子副本。同一份解析代码两种视图，
    反证钉才不是「另一枚只咬副本的尺」。影子根今天只复刻 `app/`，`deploy/` 不在就跳过——
    少一面只会少看见一个读者，不会凭空多出一个读者（假红不假绿）。
    """
    base = Path(root) if root is not None else overlay.view_root()
    sources: dict[str, str] = {}
    for folder_name in ("app", "deploy"):
        folder = base / folder_name
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            sources[path.relative_to(base).as_posix()] = path.read_text(encoding="utf-8")
    return sources


class _R457Edit(overlay.ShadowEdit):
    """一扇 R457 反证窗：变异只落临时目录里那份影子副本，活模块与盘上的字都不动。

    锚点按行列表给（本仓纯 CRLF，换行由被改文件自己定），命中数不是恰好一枚就整窗不开；
    变异文本先过 `compile()`，语法不过连窗都不开——「红」必须红在守卫上，不能红在笔误上。
    """

    tag = "r457"
    #: 🔴 不许 exec 进 app.scheduler.jobs——见 _window 的说明：那会换掉活模块里每一枚函数的身体。
    execs_module = False

    def __init__(self, path, old_lines, new_lines):
        super().__init__(path)
        self.old_lines = tuple(old_lines)
        self.new_lines = tuple(new_lines)

    def mutate(self, text: str) -> str:
        newline = chr(13) + chr(10) if chr(13) + chr(10) in text else chr(10)
        old = newline.join(self.old_lines)
        hits = text.count(old)
        assert hits == 1, (
            f"{self.path.name} 里锚点命中 {hits} 处（要求恰好 1 处）：变异整体不落盘"
        )
        mutated = text.replace(old, newline.join(self.new_lines), 1)
        compile(mutated, str(self.path), "exec")
        return mutated


#: 窗门前后都要对照的那几枚活模块把手。
LIVE_HANDLES = (
    "register_jobs", "register_audit_sweep", "audit_retention_sweep",
    "offpeak_rebuild_window", "start_scheduler", "run_forever", "scheduler",
)


@dataclass
class Refutation:
    """一扇反证窗的读数：影子副本的 sha 凭据 + 一枚隔离的变异模块 + 窗门前的活把手。"""

    info: dict
    mutant: object
    live: dict


def _mutant_jobs(text: str):
    """把影子副本里那份变异字节装进一枚一次性模块对象：不进 sys.modules，不换活模块。"""
    module = types.ModuleType("r457_mutant_jobs")
    module.__file__ = str(JOBS_PY)
    exec(compile(text, str(JOBS_PY), "exec"), module.__dict__)
    return module


@contextmanager
def _window(old_lines, new_lines):
    """开一扇反证窗：变异只落临时目录里那份影子副本，盘上与被 exec 的活模块都不动。

    🔴 为什么不走 `execs_module`：`install_source` 与 `importlib.reload` 同形，它把码体重跑进
    活模块的 `__dict__`，于是 `app.scheduler.jobs` 里**每一枚**函数都换成新身体。R425 那本在册钉
    在模块顶层 `from app.scheduler.jobs import offpeak_rebuild_window` 拿的是旧身体，同一枚
    worker 里它跑在本件之后就会红 5 枚（本单实测复现过：`test_a_switched_on_box_registers_a_third_job`
    的五枚拼写全红）。那是假红，是「同树两本账互相顶」那一族，所以变异只进隔离模块，窗尾再逐枚
    对照活把手没被换过。
    """
    live = {name: getattr(jobs_module, name) for name in LIVE_HANDLES}
    with _R457Edit(JOBS_PY, old_lines, new_lines) as info:
        ref = Refutation(info=info, mutant=_mutant_jobs(info.read_text()), live=live)
        try:
            yield ref
        finally:
            for name, handle in live.items():
                assert getattr(jobs_module, name) is handle, (
                    f"窗尾活模块的 {name} 被换过身体：反证窗污染了生产模块，本件的变异体"
                    "绝不能 exec 进 app.scheduler.jobs"
                )


@pytest.fixture
def knobs(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """清掉 R425 那三枚旋钮：即一台什么也没说的新装机器。"""
    for name in (SCHEDULE_ENV, TIME_BUDGET_ENV, AT_ENV):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def subprocess_must_not_run(monkeypatch: pytest.MonkeyPatch) -> list:
    """绊线：任何真 subprocess 调用都记成一枚失败，而不是记成一个读数。"""
    seen: list = []

    def trip(argv, *args, **kwargs):
        seen.append(list(argv))
        raise AssertionError(f"排程起了子进程: {argv}")

    monkeypatch.setattr(subprocess, "run", trip)
    return seen


def _host_reading(monkeypatch: pytest.MonkeyPatch, module=None) -> tuple[RecordingScheduler, int]:
    """跑一遍 run_forever 的注册道：BlockingScheduler 换成只记账的替身，一次都不阻塞。"""
    module = module if module is not None else jobs_module
    built: list[RecordingScheduler] = []

    class FakeBlocking(RecordingScheduler):
        def __init__(self, *args, **kwargs):
            super().__init__()
            built.append(self)

    monkeypatch.setattr("apscheduler.schedulers.blocking.BlockingScheduler", FakeBlocking)
    rc = module.run_forever()
    assert len(built) == 1, "run_forever 该恰好造一枚调度器，现读 " + str(len(built))
    return built[0], rc


def _api_host_reading(monkeypatch: pytest.MonkeyPatch, module=None) -> RecordingScheduler:
    """跑一遍 start_scheduler 的注册道：模块级那枚 scheduler 换成替身，真线程一枚不起。"""
    module = module if module is not None else jobs_module
    fake = RecordingScheduler()
    monkeypatch.setattr(module, "scheduler", fake)
    module.start_scheduler()
    return fake


def _purge_witness(monkeypatch: pytest.MonkeyPatch, module=None) -> dict:
    """到点跑一发，交回 (`args`, `kwargs`, `result`)：绿件与反证钉共读同一枚读数口。

    桩打在 `app.common.audit` 那枚函数名上——`audit_retention_sweep()` 是延迟 import，
    调用那一刻才从模块字典取名字，所以桩就是它到点真正要打的那一发；盘上、库里一个字节都不动。
    """
    module = module if module is not None else jobs_module
    seen: dict = {}

    def spy(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return {"status": "ok", "reason": "nothing_to_purge", "checked": 0, "expired": 0, "purged": 0}

    monkeypatch.setattr(audit_module, "purge_expired_audit_events", spy)
    seen["result"] = module.audit_retention_sweep()
    assert "args" in seen, (
        "到点那一发根本没打到 audit 那边：清扫是一枚空转的回调，"
        "expires_at 仍然没人读"
    )
    return seen


# ==================== 判据①：执行腿在名册上，且两枚 host 都挂得上 ====================


def test_the_sweep_is_declared_once_per_host():
    fake = RecordingScheduler()

    assert jobs_module.register_audit_sweep(fake) is None, "注册把手不该交回东西"
    assert ids(fake) == [jobs_module.AUDIT_SWEEP_JOB_ID], "一枚 host 只该挂一枚清扫"

    job = fake.registered[0]
    assert job.func is jobs_module.audit_retention_sweep, "日历上那一格挂的不是这枚回调"
    assert job.trigger == "cron"
    assert (job.options["hour"], job.options["minute"]) == (
        jobs_module.AUDIT_SWEEP_HOUR, jobs_module.AUDIT_SWEEP_MINUTE,
    ), "排程的时刻与常数不是同一份读数"
    assert job.options["replace_existing"] is True, "换身体时不许留下第二枚同名 job"
    assert job.options["max_instances"] == 1 and job.options["coalesce"] is True, (
        "同一时刻叠两遍清扫＝对同一笔欠账写两次 tombstone，纯噪声"
    )
    assert fake.starts == 0, "注册不是跑成"


def test_the_sweep_clock_is_a_real_moment_and_not_a_second_copy(knobs):
    """三枚 job 各占自己的时刻；低峰窗口那枚时钟从真源读，本件也不抄第二份数字。"""
    sweep = (jobs_module.AUDIT_SWEEP_HOUR, jobs_module.AUDIT_SWEEP_MINUTE)
    hour, minute = sweep
    assert 0 <= hour <= 23 and 0 <= minute <= 59, f"非法时刻: {sweep}"

    window = resolve_index_rebuild_window({})
    assert sweep != (window.hour, window.minute), "清扫与低峰窗口抢同一枚时刻"

    fake = RecordingScheduler()
    jobs_module.register_jobs(fake)
    others = [
        (job.options.get("hour"), job.options.get("minute"))
        for job in fake.registered if job.trigger == "cron"
    ]
    assert sweep not in others, f"清扫落在另一枚 job 的时刻上: {others}"


def test_the_api_process_host_mounts_the_sweep(knobs, monkeypatch):
    """开发形态：`app/main.py` 的 startup 走 `start_scheduler()`。"""
    fake = RecordingScheduler()
    monkeypatch.setattr(jobs_module, "scheduler", fake)

    jobs_module.start_scheduler()

    assert fake.starts == 1, "进程内调度没 start 就是没跑"
    assert ids(fake)[:2] == NAMED_SURFACE_IDS, "在册那两枚的顺序与名册不该被本单挪动"
    assert_sweep_mounted(fake, "进程内调度（start_scheduler）")


def test_the_standalone_scheduler_process_mounts_the_sweep(knobs, monkeypatch):
    """生产形态：`python deploy/scheduler.py` 走 `run_forever()`——今天真正在跑的那一枚。"""
    fake, rc = _host_reading(monkeypatch)

    assert rc == 0, "独立进程没交回 0：注册道被改成了别的东西"
    assert fake.starts == 1, "独立进程没 start 就是没跑"
    assert ids(fake)[:2] == NAMED_SURFACE_IDS, "在册那两枚的顺序与名册不该被本单挪动"
    assert_sweep_mounted(fake, "独立调度进程（run_forever / python deploy/scheduler.py）")


# ==================== 判据① 的两道边界 ====================


def assert_every_host_mounts_the_sweep() -> None:
    """AST 遍：凡在生产码里调用 `register_jobs()` 的函数，都必须同一笔挂上清扫。"""
    sources = production_sources()
    hosts = _callers_of(sources, "register_jobs")
    assert hosts, "app/** 与 deploy/** 里已经没有 host 调用 register_jobs()：这枚判据没被测到"
    sweeped = _callers_of(sources, "register_audit_sweep")

    missing = sorted(hosts - sweeped)
    assert not missing, (
        f"挂了名册却没挂执行腿的 host：{missing} ⇒ 对这一路进程而言，expires_at 仍然是一枚"
        "没人读的字段"
    )
    assert ("app/scheduler/jobs.py", "start_scheduler") in hosts, (
        "进程内那枚 host 不见了：本件的读数口径要跟生产形态一起改"
    )


def test_no_host_can_register_jobs_without_the_sweep():
    """这一格堵的是「落点为什么不在名册里」留下的那道缝：将来有人新起一枚 host，或者把本文件
    的注册道拆成两半，只挂名册不挂腿，`expires_at` 就又能在那一路进程里没人读。
    """
    assert_every_host_mounts_the_sweep()


# ==================== 判据① 的行为面：注册不跑成，到点真清账 ====================


def test_registering_the_sweep_fires_nothing(knobs, monkeypatch, subprocess_must_not_run):
    """排上日历＝零执行：清扫不许在 `add_job` 那一刻就把台账写一遍，也不许起任何子进程。"""
    fired: list = []

    monkeypatch.setattr(
        audit_module, "purge_expired_audit_events",
        lambda *args, **kwargs: fired.append((args, kwargs)) or {},
    )

    fake = RecordingScheduler()
    jobs_module.register_jobs(fake)
    jobs_module.register_audit_sweep(fake)

    assert fired == [], "注册即清扫＝把执行腿写成了 add_job 的副作用"
    assert fake.starts == 0, "注册把手不该伸手去 start"
    assert subprocess_must_not_run == []


def test_the_leg_fires_the_real_purge_not_a_preview(monkeypatch):
    seen = _purge_witness(monkeypatch)

    assert_the_leg_actually_purges(seen["args"], seen["kwargs"])


def test_the_sweep_hands_back_that_reading_and_nothing_else(monkeypatch):
    """交回的读数＝audit 那边给的那一份：视图那格（`view_complete`）不归清扫说。"""
    payload = {"status": "ok", "reason": "purged", "checked": 9, "expired": 4, "purged": 4}
    monkeypatch.setattr(audit_module, "purge_expired_audit_events", lambda **kwargs: dict(payload))

    result = jobs_module.audit_retention_sweep()

    assert result == payload, "清扫改写了到点的读数"
    assert set(result) == PURGE_REPORT_KEYS, (
        f"清扫自己加了词表：现读 {sorted(set(result) - PURGE_REPORT_KEYS)}"
    )


@pytest.mark.parametrize(
    "status, reason, level",
    [
        ("ok", "purged", logging.INFO),
        ("unavailable", "AUDIT_PERSISTENCE is disabled", logging.WARNING),
        ("error", "审计事件读取失败，无法执行保留期清理", logging.ERROR),
    ],
)
def test_the_sweep_answers_every_status_in_words(monkeypatch, caplog, status, reason, level):
    """三种状态各有各的音量：没有落点别报成成功，读不动台账别一声不响。"""
    payload = {
        "status": status, "reason": reason, "checked": 7, "expired": 2,
        "purged": 2 if status == "ok" else 0,
    }
    monkeypatch.setattr(audit_module, "purge_expired_audit_events", lambda **kwargs: dict(payload))
    caplog.set_level(logging.INFO, logger="enterprise_brain")

    assert jobs_module.audit_retention_sweep() == payload

    hits = [rec for rec in caplog.records if "留存清扫" in rec.getMessage()]
    assert len(hits) == 1, f"到点该说恰好一句话，现读 {len(hits)} 句"
    message = hits[0].getMessage()
    assert hits[0].levelno == level, f"{status} 记成了 {hits[0].levelname}：{message}"
    assert "checked=7" in message, "读数没进日志：" + message
    if status != "ok":
        assert reason in message, "失败的原因被吞了：" + message


# ==================== 判据②：四把反证钉，变异只落影子根，盘上全程只读 ====================


def _assert_disk_and_module_restored(ref: Refutation) -> None:
    """每把刀收尾都自证三格：盘上字节、活模块把手、注册道仍然挂得上腿。"""
    info = ref.info
    assert info["restored"] is True and info["after"] == info["before"], (
        f"盘上的 jobs.py 没回到原字节：{info['before']} -> {info['after']}"
    )
    assert overlay.sha16_of_bytes(JOBS_PY.read_bytes()) == info["before"], (
        "窗尾再读一次盘上那枚，sha 与进门时不同：反证窗漏了写口"
    )
    for name, handle in ref.live.items():
        assert getattr(jobs_module, name) is handle, f"活模块的 {name} 被换过身体"

    fake = RecordingScheduler()
    jobs_module.register_audit_sweep(fake)
    assert ids(fake) == [jobs_module.AUDIT_SWEEP_JOB_ID], "活模块的注册道不再挂腿：窗没关干净"


def test_teeth_1_the_standalone_host_goes_red_when_the_leg_is_dropped(knobs, monkeypatch):
    """TOOTH 1：摘掉独立进程那一行的腿 ⇒ 两枚钉当场红，红话点名「这枚字段没人读」。

    独立进程就是生产形态那一台（`python deploy/scheduler.py`），所以这一把是本单最贵的一把。
    """
    with _window([SWEEP_ON_STANDALONE_HOST], [""]) as ref:
        fake, rc = _host_reading(monkeypatch, ref.mutant)
        assert rc == 0 and fake.starts == 1, "变异把独立进程跑成了别的东西：本把刀不作数"
        assert ids(fake) == NAMED_SURFACE_IDS, "摘腿之后名册确实只剩那两枚，这才是本把要量的形状"

        with pytest.raises(AssertionError, match="没人读") as host_red:
            assert_sweep_mounted(fake, "独立调度进程（run_forever / python deploy/scheduler.py）")
        assert "run_forever" in str(host_red.value), "红话没点名是哪一路进程漏挂：" + str(host_red.value)

        with pytest.raises(AssertionError, match="没人读的字段") as ast_red:
            assert_every_host_mounts_the_sweep()
        assert "run_forever" in str(ast_red.value), "AST 遍没点名缺哪枚 host：" + str(ast_red.value)

    _assert_disk_and_module_restored(ref)


def test_teeth_2_the_in_process_host_goes_red_when_the_leg_is_dropped(knobs, monkeypatch):
    """TOOTH 2：摘掉进程内那一行的腿 ⇒ 同一对钉红在 `start_scheduler` 上，不红在别的 host 上。"""
    with _window([SWEEP_ON_API_HOST], [""]) as ref:
        fake = _api_host_reading(monkeypatch, ref.mutant)
        assert fake.starts == 1, "变异把进程内调度跑成了别的东西：本把刀不作数"
        assert ids(fake) == NAMED_SURFACE_IDS

        with pytest.raises(AssertionError, match="没人读") as host_red:
            assert_sweep_mounted(fake, "进程内调度（start_scheduler）")
        assert "start_scheduler" in str(host_red.value)

        with pytest.raises(AssertionError, match="没人读的字段") as ast_red:
            assert_every_host_mounts_the_sweep()
        assert "start_scheduler" in str(ast_red.value), "AST 遍没点名缺哪枚 host：" + str(ast_red.value)

    _assert_disk_and_module_restored(ref)


def test_teeth_3_a_preview_leg_goes_red(knobs, monkeypatch):
    """TOOTH 3：把执行腿改成预览 ⇒ 「预览不是执行腿」那一枚红，红话也点名那枚字段。

    这一格与「有没有人读」分开：调用点还在，只是它从此一枚也不清。那枚读没读的判断在
    tests/test_r457_expires_at_has_a_reader.py，它在这一把刀下必须仍是绿的（那儿另有一把钉）。
    """
    with _window([SWEEP_PURGE_CALL], ["    result = purge_expired_audit_events(dry_run=True)"]) as ref:
        seen = _purge_witness(monkeypatch, ref.mutant)
        assert seen["kwargs"] == {"dry_run": True}, "变异没打进预览那一格：本把刀不作数"

        with pytest.raises(AssertionError, match="预览") as red:
            assert_the_leg_actually_purges(seen["args"], seen["kwargs"])
        assert "没人读" in str(red.value), "红话没点名那枚字段：" + str(red.value)

    _assert_disk_and_module_restored(ref)


def test_teeth_4_a_fourth_job_on_the_named_surface_goes_red(knobs):
    """TOOTH 4：把腿搬进 `register_jobs()` ⇒ R425 判据② 那族名册钉按「缺省恰两枚」逐字钉死，红。

    本单写这份码之前先把这一格量出来了：落点在 host 层不是口味，是写域边界——那本账不在 R457
    里，一笔单不许改另一笔单的断言。搬进来照样挂着腿，但名册一漂就红在别人的账上：本单在临时
    影子里实量过那一版（%TEMP%\\r457_op，跑完按 sha 还原），R425 那本四枚名册钉共红 15 枚读数
    （缺省两枚那 1 枚 + 开关拼写那 8 枚 + 第三枚那 5 枚 + 注册不跑成那 1 枚），本件自己再红 5 枚。
    所以这枚 sweep 长在 host 层。
    """
    with _window([DAILY_REPORT_ANCHOR], [DAILY_REPORT_ANCHOR, SWEEP_ON_API_HOST]) as ref:
        fake = RecordingScheduler()
        ref.mutant.register_jobs(fake)
        assert jobs_module.AUDIT_SWEEP_JOB_ID in ids(fake), "变异没把腿搬进去：本把刀不作数"

        with pytest.raises(AssertionError, match="名册漂了") as red:
            assert_named_surface_is_r425_two(fake)
        assert "R425" in str(red.value), "红话没点名那本账：" + str(red.value)

    _assert_disk_and_module_restored(ref)
