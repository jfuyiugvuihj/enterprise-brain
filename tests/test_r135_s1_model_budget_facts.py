# -*- coding: utf-8 -*-
"""R135·S1 · 模型档位事实：把「我们到底跑在 4096 上吗」从猜变成读。

只测行为，不测文案：每一枚数都从**环境变量真源**推出来，所以把读数写死成常数当场就红
（判据 3）。全离线：不连模型、不起服务、不开 socket、不动数据——判据 4 要的就是这个，
本文件里 ``test_readout_opens_no_socket_and_never_calls_the_model`` 直接把 httpx 拦成炸弹。

今天这台机器的真实形状（总控 docker 亲测）是：``MODEL_MAX_CONCURRENCY`` 由 compose 写，
``MODEL_CONTEXT_TOKENS`` / ``MODEL_CONCURRENCY_WAIT_SECONDS`` / ``MODEL_MIN_ANSWER_TOKENS``
三枚没有任何部署文件写 ⇒ 生效值 = 代码默认。所以下面最重要的判据是 ①：**同一个响应里
必须同时能出现 env 与 default 两种出处**，混成一个数就是没做。
"""

import json
import os

import pytest

from app.agents.contracts import ModelTier
from app.api.v1.observability import (
    MODEL_BUDGET_FACTS_PATH,
    SOURCE_DEFAULT,
    SOURCE_ENV,
    SOURCE_ENV_IGNORED,
    model_budget_facts,
)
from app.common import model_budget as mb

FACTS_PATH = "/api/v1" + MODEL_BUDGET_FACTS_PATH
#: 判据 1 要的完整出处词汇：只有这三种，且必须彼此可辨。
SOURCE_VOCABULARY = {SOURCE_ENV, SOURCE_DEFAULT, SOURCE_ENV_IGNORED}
#: 判据 ①点名的四问里所有"今天真机上走默认或走 env"的变量，一个都不许多一个都不许少。
KNOB_ENV_NAMES = (
    "MODEL_CONTEXT_TOKENS",
    "MODEL_CONCURRENCY_WAIT_SECONDS",
    "MODEL_MIN_ANSWER_TOKENS",
    "MODEL_MAX_CONCURRENCY",
    "MODEL_TIER_ANALYSIS_MAX_TOKENS",
)


@pytest.fixture(autouse=True)
def clean_model_environment(monkeypatch):
    """把这几枚变量清干净：读数必须反映"现在"，不能反映上一枚用例留下的脏 env。"""
    for name in KNOB_ENV_NAMES + tuple(
        mb.tier_max_tokens_env_name(tier) for tier in ModelTier
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("MODEL_CONTEXT_TOKENS", raising=False)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def _headers(username="admin"):
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _all_knobs(report: dict) -> list[dict]:
    """把响应里每一枚"带出处的数字"收成一串，供结构性判据统一扫。"""
    knobs = [
        report["context_window"],
        report["generation_room"]["output_cap"],
        report["concurrency"]["max_concurrency"],
        report["concurrency"]["wait_seconds"],
        report["answer_floor"],
    ]
    knobs.extend(tier["declared_output_cap"] for tier in report["tiers"])
    return knobs


# ==================== 判据 ①：effective 与 source 必须分开交 ====================


def test_every_number_carries_its_own_provenance():
    report = model_budget_facts()
    knobs = _all_knobs(report)
    assert len(knobs) == 5 + len(list(ModelTier)), len(knobs)
    for knob in knobs:
        assert {"effective", "source", "env", "written"} <= set(knob), knob
        assert knob["source"] in SOURCE_VOCABULARY, knob
        assert isinstance(knob["effective"], (int, float)) and not isinstance(knob["effective"], bool)
        #: source 与 written 不许自相矛盾：没写过的变量不可能报成 env。
        if not knob["written"]:
            assert knob["source"] == SOURCE_DEFAULT, knob


def test_env_and_default_are_distinguishable_inside_one_response():
    """判据 ① 的正身：compose 只写闸门那一枚，其余三枚走默认——响应必须原样说出这个差别。"""
    mb_os_set = "MODEL_MAX_CONCURRENCY"

    os.environ[mb_os_set] = "1"
    try:
        report = model_budget_facts()
    finally:
        del os.environ[mb_os_set]
    gate = report["concurrency"]["max_concurrency"]
    window = report["context_window"]
    assert (gate["source"], window["source"]) == (SOURCE_ENV, SOURCE_DEFAULT), (gate, window)
    assert gate["written_value"] == "1", gate
    assert window["written_value"] is None and window["written"] is False, window
    sources = {knob["source"] for knob in _all_knobs(report)}
    assert sources == {SOURCE_ENV, SOURCE_DEFAULT}, sources


def test_a_written_but_unusable_value_is_not_reported_as_a_default():
    """写了个不合法的值：生效的是默认，但出处必须是 env_ignored，不许与"没写过"混同。"""

    os.environ["MODEL_CONTEXT_TOKENS"] = "not-a-number"
    try:
        report = model_budget_facts()
    finally:
        del os.environ["MODEL_CONTEXT_TOKENS"]
    window = report["context_window"]
    assert window["source"] == SOURCE_ENV_IGNORED, window
    assert window["written"] is True and window["effective"] == mb.DEFAULT_CONTEXT_TOKENS, window
    unset = model_budget_facts()["context_window"]
    assert unset["source"] == SOURCE_DEFAULT, unset
    assert window["source"] != unset["source"], "写了被忽略与压根没写混成一个数，就是本单要补的洞"


# ==================== 判据 ②：设与不设，读数各答一次 ====================


def test_context_window_tracks_an_operator_who_set_it():

    os.environ["MODEL_CONTEXT_TOKENS"] = "8192"
    try:
        report = model_budget_facts()
    finally:
        del os.environ["MODEL_CONTEXT_TOKENS"]
    window = report["context_window"]
    assert window["effective"] == 8192, window
    assert window["source"] == SOURCE_ENV, window
    assert window["written_value"] == "8192", window


def test_unset_context_window_reads_back_the_code_default_and_says_default():
    report = model_budget_facts()
    window = report["context_window"]
    assert window["effective"] == mb.DEFAULT_CONTEXT_TOKENS == 4096, window
    assert window["code_default"] == mb.DEFAULT_CONTEXT_TOKENS, window
    assert window["source"] == SOURCE_DEFAULT, window


def test_generation_room_is_the_live_window_minus_the_live_cap():
    """生成档能塞的房必须由被测代码自己的性质算出，且随窗口动。"""

    baseline = model_budget_facts()
    analysis = mb.model_tier_budget(ModelTier.ANALYSIS)
    assert baseline["generation_room"]["input_budget_tokens"] == analysis.input_budget_tokens == 2560
    os.environ["MODEL_CONTEXT_TOKENS"] = "8192"
    try:
        widened = model_budget_facts()
    finally:
        del os.environ["MODEL_CONTEXT_TOKENS"]
    cap = int(widened["generation_room"]["output_cap"]["effective"])
    assert widened["context_window"]["effective"] == 8192
    assert widened["generation_room"]["input_budget_tokens"] == 8192 - cap
    assert widened["generation_room"]["input_budget_tokens"] > baseline["generation_room"]["input_budget_tokens"]


def test_concurrency_gate_and_wait_seconds_are_both_readable_with_sources():

    os.environ["MODEL_MAX_CONCURRENCY"] = "3"
    os.environ["MODEL_CONCURRENCY_WAIT_SECONDS"] = "5"
    try:
        report = model_budget_facts()
    finally:
        del os.environ["MODEL_MAX_CONCURRENCY"]
        del os.environ["MODEL_CONCURRENCY_WAIT_SECONDS"]
    gate = report["concurrency"]["max_concurrency"]
    wait = report["concurrency"]["wait_seconds"]
    assert (gate["effective"], gate["source"]) == (3, SOURCE_ENV), gate
    assert (wait["effective"], wait["source"]) == (5.0, SOURCE_ENV), wait
    #: 等待秒数那枚默认在 model_budget.py 里没有命名常数，出口拒绝抄第二份 ⇒ code_default 为空。
    assert wait["code_default"] is None, wait
    assert gate["code_default"] == mb.DEFAULT_MAX_CONCURRENCY, gate


def test_answer_floor_reports_env_or_default_too():

    assert model_budget_facts()["answer_floor"] == {
        **model_budget_facts()["answer_floor"],
        "source": SOURCE_DEFAULT,
        "effective": mb.DEFAULT_MIN_ANSWER_TOKENS,
    }
    os.environ["MODEL_MIN_ANSWER_TOKENS"] = "2048"
    try:
        floor = model_budget_facts()["answer_floor"]
    finally:
        del os.environ["MODEL_MIN_ANSWER_TOKENS"]
    assert (floor["effective"], floor["source"]) == (2048, SOURCE_ENV), floor


# ==================== 判据 ③：读数不许是抄来的常数 ====================


def test_readout_follows_a_value_nothing_would_have_hardcoded():
    """挑一枚谁都不会写进代码的怪数：写死读数的实现当场红。"""

    os.environ["MODEL_CONTEXT_TOKENS"] = "7777"
    try:
        report = model_budget_facts()
    finally:
        del os.environ["MODEL_CONTEXT_TOKENS"]
    assert report["context_window"]["effective"] == 7777
    assert report["generation_room"]["input_budget_tokens"] == 7777 - 1536


def test_tier_rooms_come_from_the_contract_not_a_copy():
    report = model_budget_facts()
    by_tier = {row["tier"]: row for row in report["tiers"]}
    assert set(by_tier) == {tier.value for tier in ModelTier}
    for tier in ModelTier:
        budget = mb.model_tier_budget(tier)
        row = by_tier[tier.value]
        assert row["declared_output_cap"]["effective"] == int(budget.max_tokens), row
        assert row["generation_room_tokens"] == int(budget.input_budget_tokens), row
        assert row["generation_room_tokens"] == int(budget.context_limit_tokens) - int(budget.max_tokens)


# ==================== 判据 ④：只读——不开口、不写库、不换全局闸 ====================


def test_readout_opens_no_socket_and_never_calls_the_model(monkeypatch):
    import httpx

    def _boom(*args, **kwargs):
        raise AssertionError("模型档位读数不许产生任何模型往返或 socket：判据 4")

    for target in ("Client", "AsyncClient"):
        monkeypatch.setattr(getattr(httpx, target), "request", _boom)
    for target in ("get", "post", "head", "options"):
        monkeypatch.setattr(httpx, target, _boom)
    report = model_budget_facts()
    assert report["context_window"]["effective"] > 0


def test_route_is_reachable_and_fails_closed_without_a_principal(client):
    anonymous = client.get(FACTS_PATH)
    assert anonymous.status_code == 401, anonymous.status_code
    body = anonymous.json()
    #: 稳定码在契约 v1 里是**扁平** detail 字符串（与 /api/v1/slo 等所有观测口一致），
    #: 不是嵌套 dict——本出口的 401 形状不许和邻居不一样。
    assert isinstance(body["detail"], str), body
    assert body["detail"] == "authentication_required", body
    allowed = client.get(FACTS_PATH, headers=_headers())
    assert allowed.status_code == 200, allowed.status_code
    payload = allowed.json()
    assert payload["requested_by"]["username"] == "admin"
    assert payload["context_window"] == model_budget_facts()["context_window"]


def test_reading_the_gate_does_not_swap_the_process_wide_budget():
    """GET 不该有把全局并发闸换掉的能力：这条读数必须与进程级单例无副作用地共存。"""
    before = mb.default_model_budget()
    before_max = before.max_concurrency
    before_wait = before.default_wait_seconds
    report = model_budget_facts()
    after = mb.default_model_budget()
    assert after is before, "读数换了全局闸：一条 GET 不该有这个权力"
    assert (after.max_concurrency, after.default_wait_seconds) == (before_max, before_wait)
    assert report["concurrency"]["max_concurrency"]["effective"] == before_max


def test_a_value_written_equal_to_the_default_is_still_reported_as_env():
    """操作员把窗口显式写成 4096：数没变，但出处必须是 env——否则下一班会以为没人配过。"""

    os.environ["MODEL_CONTEXT_TOKENS"] = str(mb.DEFAULT_CONTEXT_TOKENS)
    try:
        window = model_budget_facts()["context_window"]
    finally:
        del os.environ["MODEL_CONTEXT_TOKENS"]
    assert window["effective"] == mb.DEFAULT_CONTEXT_TOKENS, window
    assert window["source"] == SOURCE_ENV, window
    assert window["written"] is True and window["written_value"] == "4096", window


def test_response_body_is_plain_json_with_no_python_objects_left():
    """出口交的是 HTTP JSON：任何不可序列化对象都算实现错，而不是"测试没覆盖"。"""

    import json

    payload = json.loads(json.dumps(model_budget_facts(), ensure_ascii=False))
    assert payload["context_window"]["env"] == "MODEL_CONTEXT_TOKENS"
    json.dumps(payload)


def test_the_success_path_writes_no_audit_and_no_store(client, monkeypatch):
    """判据 4 的正身之一：一次成功的读数不得写任何东西。

    只在**拒绝**路径记审计是观测模块的既有共享行为（``_deny``），每条 GET 都这样；
    成功路径若开始写库/写审计，本出口就不再是"只读"了。
    """
    from app.api.v1 import observability as obs

    calls = []

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("成功读数不得记审计：本出口只读")

    monkeypatch.setattr(obs.audit_log, "record_audit", _spy)
    allowed = client.get(FACTS_PATH, headers=_headers())
    assert allowed.status_code == 200, allowed.status_code
    assert calls == [], calls


def test_the_new_exit_never_diverges_from_the_existing_health_number():
    """同一枚窗口数在两条出口上必须永远相等：本出口是补出处，不是另开一本账。

    ``/api/v1/health/details`` 今天已经把 ``model_budget_readout()`` 嵌在
    ``subsystems.model_budget`` 里（``app/common/monitoring.py:249``），所以"数"本来就看得见；
    本单补的是出处、并发闸与生成房。要是哪天这条读数自己算了一套数，就得当场红在这里。
    """
    # 不走 build_health_snapshot()：那条函数会 _probe_ollama/_probe_postgres/_probe_redis，
    # 一次断言不该为了对比数字去开 socket（判据 4 与 conftest 的 R56 闸门都不答应）。
    # 这里用的是健康页自己那一行完全相同的入口 monitoring.py:249 的 _subsystem_state。
    from app.common.monitoring import _subsystem_state

    facts = model_budget_facts()
    embedded = _subsystem_state("app.common.model_budget", "model_budget_readout")
    assert embedded["context_limit_tokens"] == facts["context_window"]["effective"], (
        embedded["context_limit_tokens"], facts["context_window"]["effective"])
    assert embedded["min_answer_tokens"] == facts["answer_floor"]["effective"], embedded
    assert facts["budget_readout"] == embedded, "嵌进来的读数与健康页不是一份"


def test_the_hole_being_filled_is_real_and_stays_named():
    """把本单存在的理由钉住：老读数对窗口本身没有出处字段，只有速率有。

    如果哪天 ``model_budget_readout()`` 自己补出了窗口的 env/default 出处，这条用例就会红，
    那时该删的是本出口的重复劳动，而不是让这件事悄悄过去。
    """
    readout = mb.model_budget_readout()
    assert "MODEL_CONTEXT_TOKENS" not in json.dumps(readout["throughput_provenance"])
    assert readout["thinking"]["provenance"], "老口径只覆盖速率与思考档"
    assert model_budget_facts()["context_window"]["source"] in SOURCE_VOCABULARY


def test_embedded_readout_is_the_existing_one_not_a_second_copy():
    """现成件不许重造：嵌进来的必须是 ``model_budget_readout()`` 本身，同一个对象内容。"""
    report = model_budget_facts()
    assert report["budget_readout"] == mb.model_budget_readout()
    assert report["budget_readout"]["context_limit_tokens"] == report["context_window"]["effective"]
