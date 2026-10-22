"""R120 任务 2: 把 VECTOR_DUAL_WRITE 透传打通，而且默认仍然是"没人碰过它"。

立单事实（总控 09-20 亲核，看板 R120 行第 ① 条）：这个开关既不在 deploy/.env.server 里，
docker-compose.yml 也从不透传它 —— 也就是说真机上根本没有一条受支持的路径能把双写打开，
R58 的 P3 影子读对比因此一次都没跑过。app/rag/pg_store.py 那侧早就写好了（默认 OFF、
不认识的值只告警并当 OFF），缺的只是交付面。

三条不许退让的线，逐条钉住：
* 不设它的安装行为一字不变 —— 见 test_an_install_that_sets_nothing_...;
* compose 不许自己发明"开"，只能透传操作者写下的值，默认写 off;
* 拼错的值走 pg_store.dual_write_enabled() 那条既有告警，不新造第二套判定。

这里同样一条真库都不连：判据只需要 compose 的插值语义与 pg_store 的取值判定。
"""
from __future__ import annotations

import logging
from pathlib import Path
import re

import pytest
import yaml

from app.rag import pg_store


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = (
    ROOT / "docker-compose.yml",
    ROOT / "deploy" / "docker-compose.server.yml",
    ROOT / "deploy" / "docker-compose.tls.yml",
)
ENV_SAMPLES = (ROOT / ".env.example", ROOT / "deploy" / ".env.server.example")

#: The processes that can write a vector: backend answers uploads, worker drains the queue,
#: scheduler runs alert jobs that embed. migrate is deliberately NOT one of them -- it runs
#: scripts/migrate.py, which is DDL only and never calls an embedder, so handing it the switch
#: would advertise a knob where it does nothing.
WRITERS = ("backend", "worker", "scheduler")
OTHER_SERVICES = ("migrate", "postgres", "redis", "ollama", "frontend")

SWITCH = pg_store.DUAL_WRITE_ENV
PLAN_DOC = "docs/handoff/2026-09-17-pgvector-adoption-plan.md"


def _interpolate(value: str, environment: dict[str, str]) -> str:
    """Compose substitution for ``${VAR}`` and ``${VAR:-fallback}`` -- the only two forms used."""
    def one(match: re.Match) -> str:
        name, fallback = match.group(1), match.group(2)
        if environment.get(name):
            return environment[name]
        return fallback if fallback is not None else ""

    return re.sub(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}", one, value)


def _services(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    assert isinstance(document, dict), f"{path.name} must stay a mapping"
    return document["services"]


def _documented(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        values[name.strip()] = value.strip()
    return values


def _comments(path: Path) -> str:
    return "\n".join(
        line.lstrip("# ").strip()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip().startswith("#")
    )


@pytest.fixture
def clean_switch(monkeypatch):
    """Start every test from "nobody has ever mentioned this switch on the machine"."""
    monkeypatch.delenv(SWITCH, raising=False)
    return monkeypatch


# ------------------------------------------------------------------ 交付面：透传确实存在了


def test_compose_passes_the_switch_to_every_process_that_writes_vectors():
    services = _services(COMPOSE_FILES[0])

    for name in WRITERS:
        assert SWITCH in services[name]["environment"], name


def test_compose_does_not_leak_the_switch_where_it_does_nothing():
    services = _services(COMPOSE_FILES[0])

    for name in OTHER_SERVICES:
        assert SWITCH not in (services[name].get("environment") or {}), name


def test_the_pass_through_is_one_spelling_three_times_and_invents_no_value():
    """三处写法必须一模一样，而且是透传：compose 自己不许发明"开"。"""
    text = COMPOSE_FILES[0].read_text(encoding="utf-8")
    expected = f"{SWITCH}: ${{{SWITCH}:-off}}"

    assert text.count(expected) == len(WRITERS), text.count(expected)
    assert text.count(f"{SWITCH}: ${{{SWITCH}}}") == 0, (
        "without a fallback the container receives an empty value and Compose warns on every"
        " command; off says what the code already treats as off"
    )


def test_the_resolved_default_is_the_state_every_release_shipped_before_this_one():
    """操作者一个字不写 ⇒ 三个进程各自拿到 off，而 off 是代码认识的假值，不是"不认识"。"""
    services = _services(COMPOSE_FILES[0])

    for name in WRITERS:
        resolved = _interpolate(services[name]["environment"][SWITCH], {})
        assert resolved == "off", (name, resolved)
        assert resolved in pg_store.FALSY_VALUES


def test_an_operator_who_says_on_reaches_all_three_processes_unchanged():
    services = _services(COMPOSE_FILES[0])

    for name in WRITERS:
        resolved = _interpolate(services[name]["environment"][SWITCH], {SWITCH: "on"})
        assert resolved == "on", (name, resolved)
        assert resolved in pg_store.TRUTHY_VALUES


def test_no_compose_file_turns_the_mirror_on_by_default():
    """任何一枚 compose 文件都不许把开关写成"开"：那是一次没人签字的迁移。"""
    for path in COMPOSE_FILES:
        for name, service in _services(path).items():
            value = (service.get("environment") or {}).get(SWITCH)
            if value is None:
                continue
            resolved = _interpolate(str(value), {})
            assert resolved in pg_store.FALSY_VALUES, (path.name, name, resolved)


# ------------------------------------------------------------------ 运行面：默认态一字不变


def test_an_install_that_sets_nothing_issues_no_postgres_statement(clean_switch, caplog):
    """开关关着：本模块不开连接、一条 SQL 都不发，也不吵。"""
    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        assert pg_store.dual_write_enabled() is False

        def must_not_be_called():
            raise AssertionError("the off state must not open a connection")

        assert pg_store.vector_mirror(connection_factory=must_not_be_called) is None

    assert not [record for record in caplog.records if record.levelno >= logging.WARNING], (
        caplog.messages
    )


def test_an_unrecognised_value_warns_and_stays_off(clean_switch, caplog):
    """拼错的值走 pg_store.dual_write_enabled() 那条既有告警 —— 不新造第二套判定，也不误开。"""
    clean_switch.setenv(SWITCH, "ture")

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        assert pg_store.dual_write_enabled() is False

    assert any(
        SWITCH in message and "is not recognised" in message for message in caplog.messages
    ), caplog.messages


def test_an_empty_value_is_off_without_a_warning(clean_switch, caplog):
    """``VECTOR_DUAL_WRITE=``（占一行没值）是操作者"我关掉了"的写法，不是拼错。"""
    clean_switch.setenv(SWITCH, "")

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        assert pg_store.dual_write_enabled() is False

    assert not [record for record in caplog.records if record.levelno >= logging.WARNING], (
        caplog.messages
    )


def test_the_switch_is_read_at_call_time_so_the_pipethrough_is_useful(clean_switch):
    """透传要真的有用，判定就不能在 import 期被固化：一次 setenv 立刻改变答案。"""
    assert pg_store.dual_write_enabled() is False

    clean_switch.setenv(SWITCH, "on")

    assert pg_store.dual_write_enabled() is True


def test_only_the_spelling_the_code_reads_is_promised_anywhere():
    """交付面写下的名字必须与 pg_store.DUAL_WRITE_ENV 同一个字符串。

    跟进单里出现过 EB_PG_VECTOR_DUAL_WRITE 这种旧写法，真源只有 app/rag/pg_store.py 那一枚
    常量；把这件事写成用例，是为了下次有人照旧文档加开关时立刻红。
    """
    assert SWITCH == "VECTOR_DUAL_WRITE"
    for path in COMPOSE_FILES + ENV_SAMPLES:
        text = path.read_text(encoding="utf-8-sig")
        assert "EB_PG_VECTOR_DUAL_WRITE" not in text, path.name
        for other in re.findall(r"\b[A-Z0-9_]*DUAL_WRITE[A-Z0-9_]*\b", text):
            assert other == SWITCH, (path.name, other)


# --------------------------------------------------------- 示例文件：开关有出处，也有默认值


def test_both_env_samples_ship_the_switch_as_off():
    documented = {path: _documented(path) for path in ENV_SAMPLES}

    for path in ENV_SAMPLES:
        assert documented[path][SWITCH] == "off", path.name
    assert {path.name: documented[path][SWITCH] for path in ENV_SAMPLES} == {
        ENV_SAMPLES[0].name: "off",
        ENV_SAMPLES[1].name: "off",
    }, "two samples that disagree is the same defect with a second copy"


def test_the_samples_say_what_turning_it_on_means():
    """说明必须说清三件事：这是迁移步不是提速阀、读腿仍然在 Chroma、开了要先全量重建。"""
    for path in ENV_SAMPLES:
        comments = _comments(path)
        #: Prose wraps; compare on single-spaced text, not on one physical line.
        lowered = " ".join(comments.lower().split())
        assert SWITCH.lower() in lowered, path.name
        assert "rebuild" in lowered, path.name
        assert "read path" in lowered, path.name
        assert PLAN_DOC in comments, path.name


def test_the_runbook_the_samples_point_at_exists():
    assert (ROOT / PLAN_DOC).is_file(), "the samples name a document this ticket must keep valid"
    assert "P3" in (ROOT / PLAN_DOC).read_text(encoding="utf-8")
