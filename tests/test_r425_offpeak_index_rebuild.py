# -*- coding: utf-8 -*-
"""R425 · 计划书 R50「低峰」那半句：把窗口挂上排程，缺省不排，且证据只断形状。

本件零执行：不起子进程、不打模型、不动容器、不连真库。判据⑤ 要的是**断形状**，所以桩是一枚
只有 `add_job` 一个方法的假 scheduler——它没有 `start()`，`register_jobs` 一旦伸手去碰别的属性
就当场 AttributeError，"注册"与"跑成"在这枚桩里不可能混淆；另有一枚绊线钉在 `subprocess.run`
上，注册和到点各测一次，两遍都不许被碰。

🔴 关于判据① 的执行腿，本件不假装：R22 判据 3 把"应用侧能不能自己起重建"钉成硬钉
（tests/test_r22_rebuild_cli.py，R242 之后连 argv 列表形状都读解析出的语法），所以排程落得、
命令落不得。test_the_r22_pin_still_clears_the_whole_tree 就是这条边界的交叉钉：本单一枚
自动路径都没偷偷塞进去。

判据 ↔ 落点
  ① 第三枚 job 带增量窗口与时间预算 → test_a_switched_on_box_registers_a_third_job 等四枚
  ② 缺省必须不排（开关关时不许 add_job）→ test_the_shipped_default_registers_two_jobs_only
  ③ 三枚旋钮一份常数 / 示例配置写成注释掉的出厂默认 → test_the_three_knobs_are_named_in_one_file_only /
     test_the_env_sample_writes_each_knob_as_a_commented_factory_default
  ④ 反证钉（TOOTH 1..4）逐把在 %TEMP%\r425_op 改码复跑取读数，见各枚 docstring
  ⑤ 断注册不跑成 → test_registering_a_job_runs_no_command / test_firing_the_window_starts_no_process
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.common.model_config import (
    DEFAULT_KEEP_ALIVE_SECONDS,
    KEEP_ALIVE_ENV,
    parse_keep_alive_seconds,
    resolve_keep_alive,
)
from app.scheduler import jobs as jobs_module
from app.scheduler.index_rebuild_config import (
    AT_ENV,
    DEFAULT_AT,
    DEFAULT_SCHEDULE_ENABLED,
    DEFAULT_TIME_BUDGET_SECONDS,
    REBUILD_JOB_ID,
    SCHEDULE_ENV,
    TIME_BUDGET_ENV,
    IndexRebuildWindow,
    resolve_index_rebuild_window,
)
from app.scheduler.jobs import offpeak_rebuild_window

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_r22_rebuild_cli import automatic_path_hits  # noqa: E402  复用同一枚检测器，不另起口径

REPO = Path(__file__).resolve().parents[1]
ENV_SAMPLE = REPO / ".env.example"
SCHEDULER_DIR = REPO / "app" / "scheduler"
#: 本单写进示例配置的四枚键：三枚窗口旋钮，加跟进单 §3.2 第 7 条欠的那枚 R34 文档面。
DOCUMENTED_KNOBS = (SCHEDULE_ENV, TIME_BUDGET_ENV, AT_ENV, KEEP_ALIVE_ENV)
#: 一枚会动笔的排程件不该有的形状：起进程、开 socket、发 HTTP。
FORBIDDEN_CALLS = frozenset(
    {"system", "popen", "Popen", "run", "check_output", "exec", "execv", "execve",
     "startfile", "connect", "send"}
)
ALLOWED_IMPORT_ROOTS = {"__future__", "os", "re", "dataclasses", "apscheduler", "app"}


# ==================== 判据⑤ 的桩 ====================


@dataclass(frozen=True)
class Registered:
    """add_job 被塞了什么。只读，从不执行。"""

    func: object
    trigger: str | None
    options: dict


class RecordingScheduler:
    """Duck-typed scheduler：只有 add_job 一枚方法，而那枚方法只做记录。"""

    def __init__(self) -> None:
        self.registered: list[Registered] = []

    def add_job(self, func, trigger=None, **options) -> None:
        self.registered.append(Registered(func=func, trigger=trigger, options=options))


def ids(fake: RecordingScheduler) -> list[str]:
    return [r.options.get("id", "") for r in fake.registered]


def job(fake: RecordingScheduler, job_id: str) -> Registered:
    matches = [r for r in fake.registered if r.options.get("id") == job_id]
    assert len(matches) == 1, f"{job_id} 被注册了 {len(matches)} 次"
    return matches[0]


@pytest.fixture
def knobs(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """清空本单三枚旋钮，即一台新装机器什么也没说的状态。"""
    for name in (SCHEDULE_ENV, TIME_BUDGET_ENV, AT_ENV):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def subprocess_must_not_run(monkeypatch: pytest.MonkeyPatch) -> list:
    """绊线：任何真 subprocess 调用都记成一枚失败，而不是记成一个读数。"""
    seen: list[list[str]] = []

    def trip(argv, *args, **kwargs):
        seen.append(list(argv))
        raise AssertionError(f"排程起了子进程: {argv}")

    monkeypatch.setattr(subprocess, "run", trip)
    return seen


# ==================== 判据②：缺省不排（TOOTH 1 / TOOTH 2 咬在这里）====================


def test_the_shipped_default_registers_two_jobs_only(knobs):
    """TOOTH 1：摘掉 register_jobs 里那枚 `if window.schedulable` ⇒ 本枚当场红（多出第三枚 add_job）。

    TOOTH 2：把开关检查挪进回调、`add_job` 无条件 ⇒ 本枚同样红。判据② 那句"不是先 add_job、
    再在回调里 return"就钉在这一行：一台没人让它自己重嵌的机器，日历上不该多那一格。
    """
    fake = RecordingScheduler()
    jobs_module.register_jobs(fake)

    assert ids(fake) == ["alert_check", "daily_report"]
    assert REBUILD_JOB_ID not in ids(fake)


@pytest.mark.parametrize("spelling", ["", "0", "false", "no", "off", "OFF", "   ", "maybe"])
def test_an_unset_or_unreadable_switch_still_registers_nothing(knobs, spelling):
    knobs.setenv(SCHEDULE_ENV, spelling)

    fake = RecordingScheduler()
    jobs_module.register_jobs(fake)

    assert ids(fake) == ["alert_check", "daily_report"]


def test_the_off_state_names_the_switch_it_needs(knobs):
    window = resolve_index_rebuild_window()

    assert window.enabled is DEFAULT_SCHEDULE_ENABLED is False
    assert window.schedulable is False
    assert SCHEDULE_ENV in window.unschedulable_reason()


def test_the_two_pre_existing_jobs_are_untouched(knobs):
    """本单只许多一枚 job，不许顺手改另外两枚的形状。"""
    fake = RecordingScheduler()
    jobs_module.register_jobs(fake)

    alert = job(fake, "alert_check")
    assert alert.trigger == "interval" and alert.options["minutes"] == 5
    report = job(fake, "daily_report")
    assert report.trigger == "cron" and report.options["hour"] == 8 and report.options["minute"] == 0


def test_registration_never_asks_the_scheduler_to_run(knobs):
    """桩只有 add_job：register_jobs 若去碰 start / shutdown，AttributeError 当场炸。"""
    fake = RecordingScheduler()
    assert not hasattr(fake, "start") and not hasattr(fake, "shutdown")

    jobs_module.register_jobs(fake)

    assert all(isinstance(r, Registered) for r in fake.registered)


# ==================== 判据①③：多出来的第三枚长什么样 ====================


@pytest.mark.parametrize("spelling", ["1", "true", "yes", "on", "ON"])
def test_a_switched_on_box_registers_a_third_job(knobs, spelling):
    knobs.setenv(SCHEDULE_ENV, spelling)

    fake = RecordingScheduler()
    jobs_module.register_jobs(fake)

    assert ids(fake) == ["alert_check", "daily_report", REBUILD_JOB_ID]
    assert job(fake, REBUILD_JOB_ID).func is offpeak_rebuild_window
    assert job(fake, REBUILD_JOB_ID).trigger == "cron"


def test_the_third_job_carries_a_positive_time_budget(knobs):
    """TOOTH 3：把 `kwargs={"time_budget_seconds": ...}` 传成 None 或 0 ⇒ 本枚当场红。"""
    knobs.setenv(SCHEDULE_ENV, "on")

    fake = RecordingScheduler()
    jobs_module.register_jobs(fake)

    budget = job(fake, REBUILD_JOB_ID).options["kwargs"]["time_budget_seconds"]
    assert budget == DEFAULT_TIME_BUDGET_SECONDS
    assert isinstance(budget, int) and budget > 0, "预算为空或为零＝无界的整库重嵌"


def test_the_budget_and_the_moment_come_from_the_same_reader(knobs):
    """判据③ 的行为面：改一处配置，注册形状跟着改 ⇒ jobs.py 里没有第二份常数可落。"""
    knobs.setenv(SCHEDULE_ENV, "on")
    knobs.setenv(TIME_BUDGET_ENV, "900")
    knobs.setenv(AT_ENV, "04:15")

    fake = RecordingScheduler()
    jobs_module.register_jobs(fake)

    window = job(fake, REBUILD_JOB_ID)
    assert (window.options["hour"], window.options["minute"]) == (4, 15)
    assert window.options["kwargs"]["time_budget_seconds"] == 900


def test_the_window_and_its_budget_finish_before_the_morning_report(knobs):
    """低峰之所以是低峰：窗口 + 最坏预算必须仍在 8:00 日报之前，且 8:00 是从树上现读的。"""
    fake = RecordingScheduler()
    knobs.setenv(SCHEDULE_ENV, "on")
    jobs_module.register_jobs(fake)

    report = job(fake, "daily_report")
    window = job(fake, REBUILD_JOB_ID)
    start = window.options["hour"] * 60 + window.options["minute"]
    ends = start + window.options["kwargs"]["time_budget_seconds"] // 60
    morning = report.options["hour"] * 60 + report.options["minute"]

    assert ends < morning, f"窗口 {start}+预算落在营业时段 {morning} 之后"


def test_the_third_job_cannot_stack_on_itself(knobs):
    """同一时刻不许叠两遍：两枚窗口同时报同一笔欠账是噪声，同时动库更是事故。"""
    knobs.setenv(SCHEDULE_ENV, "on")

    fake = RecordingScheduler()
    jobs_module.register_jobs(fake)

    window = job(fake, REBUILD_JOB_ID)
    assert window.options["max_instances"] == 1
    assert window.options["coalesce"] is True
    assert window.options["replace_existing"] is True


# ==================== 判据⑤：注册与到点都不许跑成任何事 ====================


def test_registering_a_job_runs_no_command(knobs, subprocess_must_not_run):
    """把 job 排上日历＝零执行。绊线在 subprocess.run 上，一次都不该被碰。"""
    knobs.setenv(SCHEDULE_ENV, "on")

    fake = RecordingScheduler()
    jobs_module.register_jobs(fake)

    assert len(fake.registered) == 3
    assert subprocess_must_not_run == []


def test_firing_the_window_starts_no_process_and_writes_nothing(knobs, subprocess_must_not_run):
    """到点那一发同样零执行：回调只报一句话，绊线仍然没人碰。"""
    knobs.setenv(SCHEDULE_ENV, "on")
    knobs.setenv(TIME_BUDGET_ENV, "900")

    result = offpeak_rebuild_window(time_budget_seconds=900)

    assert subprocess_must_not_run == []
    assert result["status"] == "refused"
    assert result["budget_seconds"] == 900


def test_the_refusal_names_the_budget_and_the_flags_an_operator_needs(knobs):
    knobs.setenv(SCHEDULE_ENV, "on")
    knobs.setenv(TIME_BUDGET_ENV, "900")
    knobs.setenv(AT_ENV, "04:15")

    result = offpeak_rebuild_window(time_budget_seconds=900)

    reason = result["reason"]
    assert "应用侧不许触发索引重建" in reason
    assert result["window"] == "04:15"
    assert "--incremental" in reason
    assert "--time-budget-seconds 900" in reason


def test_the_refusal_does_not_smuggle_the_pinned_command_name(knobs):
    """那条日志自己也得留在钉里：把被钉死的命令名写进字符串常量，R22 的 AST 遍当场算命中。"""
    knobs.setenv(SCHEDULE_ENV, "on")

    reason = offpeak_rebuild_window()["reason"]

    assert "rebuild_index" not in reason
    assert automatic_path_hits(REPO) == []


def test_the_scheduler_files_hold_no_spawn_or_socket_shape_at_all():
    """AST 正面钉：app/scheduler/ 里既没有 subprocess，也没有任何起进程/连网络的调用。"""
    roots: set[str] = set()
    called: set[str] = set()
    for path in sorted(SCHEDULER_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    called.add(node.func.attr)
                elif isinstance(node.func, ast.Name):
                    called.add(node.func.id)

    assert roots <= ALLOWED_IMPORT_ROOTS, roots
    assert "subprocess" not in roots and "socket" not in roots
    assert not (called & FORBIDDEN_CALLS), called & FORBIDDEN_CALLS


def test_the_r22_pin_still_clears_the_whole_tree():
    """🔴 本单对 R22 判据 3 零放宽、零绕行：那枚钉自己的检测器在真树上必须仍然交回空。"""
    assert automatic_path_hits(REPO) == []


# ==================== 判据③：三枚旋钮只有一份 ====================


@pytest.mark.parametrize("knob", [SCHEDULE_ENV, TIME_BUDGET_ENV, AT_ENV])
def test_the_three_knobs_are_named_in_one_file_only(knob):
    readers = [p for p in sorted((REPO / "app").rglob("*.py")) if knob in p.read_text(encoding="utf-8")]

    assert readers == [SCHEDULER_DIR / "index_rebuild_config.py"], readers


def test_jobs_py_carries_no_second_copy_of_a_knob():
    """开关／预算／时刻都不许在 jobs.py 落成一枚字面量，也不许它自己伸手读 env。"""
    source = (SCHEDULER_DIR / "jobs.py").read_text(encoding="utf-8")

    for token in (str(DEFAULT_TIME_BUDGET_SECONDS), DEFAULT_AT, "os.environ", "os.getenv", "getenv"):
        assert token not in source, f"jobs.py 里出现了第二份常数或第二个读者: {token!r}"


def test_the_shipped_defaults_are_the_factory_state():
    window = resolve_index_rebuild_window({})

    assert window == IndexRebuildWindow(
        enabled=False,
        budget_seconds=DEFAULT_TIME_BUDGET_SECONDS,
        hour=3,
        minute=30,
    )
    assert (window.clock,) == ((3, 30),) and DEFAULT_AT == "03:30"


@pytest.mark.parametrize(
    "raw, expected",
    [("", DEFAULT_TIME_BUDGET_SECONDS), ("0", DEFAULT_TIME_BUDGET_SECONDS),
     ("-5", DEFAULT_TIME_BUDGET_SECONDS), ("abc", DEFAULT_TIME_BUDGET_SECONDS),
     ("900", 900), ("90.7", 90)],
)
def test_an_unusable_budget_never_becomes_an_unbounded_window(raw, expected):
    window = resolve_index_rebuild_window({SCHEDULE_ENV: "on", TIME_BUDGET_ENV: raw})

    assert window.budget_seconds == expected > 0


def test_an_unusable_moment_warns_instead_of_inventing_a_time():
    window = resolve_index_rebuild_window({AT_ENV: "25:99", TIME_BUDGET_ENV: "900"})

    assert window.clock == (3, 30)
    assert any(AT_ENV in note for note in window.notes)


# ==================== 判据③ 与跟进单 §3.2 第 7 条：纸面 ====================


def _commented_values(sample: str, name: str) -> list[str]:
    pattern = re.compile(rf"^[ \t]*#[ \t]*(?:-[ \t]+)?{name}[ \t]*=[ \t]*(.*)$", re.MULTILINE)
    return [m.group(1).strip() for m in pattern.finditer(sample)]


def _effective_values(sample: str, name: str) -> list[str]:
    #: 行首只允许空白或 YAML 短横，键名后紧跟 = 或 :，注释行不算——与
    #: tests/test_r382_untouched_defaults_pins.py 里 09-28 随 R408 收窄后的 EFFECTIVE_SET 同形。
    pattern = re.compile(rf"^[ \t]*(?:-[ \t]+)?{name}[ \t]*[=:][ \t]*(.*)$", re.MULTILINE)
    return [m.group(1).strip() for m in pattern.finditer(sample)]


@pytest.mark.parametrize(
    "name, factory_default",
    [
        (SCHEDULE_ENV, "false"),
        (TIME_BUDGET_ENV, str(DEFAULT_TIME_BUDGET_SECONDS)),
        (AT_ENV, DEFAULT_AT),
    ],
)
def test_the_env_sample_writes_each_knob_as_a_commented_factory_default(name, factory_default):
    """纸上一个数，码里一个数：注释值不等于出厂值 ⇒ 本枚当场红（又是一台机器一个行为）。"""
    sample = ENV_SAMPLE.read_text(encoding="utf-8")

    values = _commented_values(sample, name)
    assert len(values) == 1, f"{name} 在示例配置里写了 {len(values)} 行"
    assert values[0] == factory_default


def test_the_documented_defaults_are_derivable_not_copied():
    """注释里那三行必须能交回同一枚解析器同一个数：一份手抄的默认值就是下一枚漂移。"""
    sample = ENV_SAMPLE.read_text(encoding="utf-8")
    budget = int(_commented_values(sample, TIME_BUDGET_ENV)[0])
    hour, minute = _commented_values(sample, AT_ENV)[0].split(":")
    switch = _commented_values(sample, SCHEDULE_ENV)[0]

    assert budget == resolve_index_rebuild_window({TIME_BUDGET_ENV: str(budget)}).budget_seconds
    assert resolve_index_rebuild_window({AT_ENV: f"{hour}:{minute}"}).clock == (int(hour), int(minute))
    assert switch == str(DEFAULT_SCHEDULE_ENABLED).lower()
    assert resolve_index_rebuild_window({SCHEDULE_ENV: switch}).enabled is False


def test_the_sample_leaves_every_knob_unassigned():
    """🔴 R408 的口径：注释可以写、生效位赋值不可以写。

    TOOTH 4：把本单四枚键里任何一行取消注释 ⇒ 本枚当场红——示例配置不该替业主做决定，
    一枚"装上就自己排窗口"的缺省尤其不该由一张纸悄悄发出去。
    """
    sample = ENV_SAMPLE.read_text(encoding="utf-8")

    offenders = {
        name: _effective_values(sample, name) for name in DOCUMENTED_KNOBS if _effective_values(sample, name)
    }
    assert not offenders, f"示例配置里出现了生效位赋值: {offenders}"


def test_local_model_keep_alive_is_on_the_sample_at_its_own_default():
    """跟进单 §3.2 第 7 条：机制早就在码（app/common/model_config.py:30-31），纸上一直缺这一行。

    值不手抄：由 resolve_keep_alive() 现算，再用它自己的解析器读回来，两半必须同一个数。
    """
    sample = ENV_SAMPLE.read_text(encoding="utf-8")

    values = _commented_values(sample, KEEP_ALIVE_ENV)
    assert len(values) == 1, f"{KEEP_ALIVE_ENV} 写了 {len(values)} 行"
    assert values[0] == resolve_keep_alive("").wire
    assert parse_keep_alive_seconds(values[0]) == float(DEFAULT_KEEP_ALIVE_SECONDS)


def test_the_window_block_says_what_the_tree_actually_does():
    """R408 那一族的规矩：纸要说这棵树今天做的事。窗口不等于重嵌，这句必须写在纸上。"""
    sample = ENV_SAMPLE.read_text(encoding="utf-8")

    assert "three knobs that put a WINDOW on the calendar" in sample
    assert "it never buys a rebuild" in sample
    assert "no scheduler job may import, call or spawn the rebuild" in sample
    assert "R22 判据 3" in sample


def test_the_window_block_points_at_the_reader_and_the_recreate_rule():
    """运维读这块纸时必须知道的三件事：值在哪解析、容器读哪一份、改了怎么生效。"""
    sample = ENV_SAMPLE.read_text(encoding="utf-8")

    assert "app/scheduler/index_rebuild_config.py" in sample
    assert "deploy/.env.server" in sample, "容器读的是那一份，不是这一份"
    assert "--force-recreate" in sample, "env_file 在容器创建那一刻才解析"
