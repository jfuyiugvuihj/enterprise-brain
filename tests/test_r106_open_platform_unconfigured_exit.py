"""R106 判据（跟进单 §45.2）：开放平台「生产压根没配 store」不许冒名存储故障。

六枚钉子全部走真 TestClient 打真路由，一枚源码字符串都不 grep：

* ``APP_ENV=production`` 且 ``OPEN_PLATFORM_APP_STORE_PATH`` 从未设过 ⇒
  ``POST /api/v1/apps`` 得 **409**，detail 精确等于 ``open_platform_unconfigured``；
* store 配好了、``upsert`` 真失败 ⇒ **仍须 503** ``storage_read_only``。本单要的是语义与
  事实相符，不是把 503 清零；把真故障改判成 4xx 与原来的谎报同等严重；
* 开发态注册照旧 200 落进程内字典，耐久态照旧 200，两者都不许带 ``reason``——没在拒
  写就没有理由可解释；
* ``/api/v1/health/details`` 的 ``open_platform_apps`` 节与路由同一个词，两枚拒绝各验一次。
  这个词只存在于 ``app_registry_storage_state()`` 的 ``reason`` 字段里，拆掉那一行，本文件
  的路由断言与 health 断言必须一起红；
* 没配 / 真写失败 / 请求本身不合格 ⇒ 审计末位理由三个不同值；
* 最后一条是反「第二份真源」的鉴别用例：异常文本写着「is required in production」而事实
  是「配了却打不开」，出口必须跟状态字段走，不跟措辞走。

全程离线：健康快照三枚探针换成桩（同 tests/test_r103_graph_unconfigured_exit.py 的规矩），
注册表落在 tmp_path，模型端口另有 tests/conftest.py 的 R56 闸门拦着。每枚用例自己收尾
``configure_app_store("")``：注册表状态是模块级的，留在盘上的 error 会串到下一个用例身上。
"""
import pytest
from fastapi.testclient import TestClient

APPS_PATH = "/api/v1/apps"
HEALTH_PATH = "/api/v1/health/details"

#: The two words as a client sees them. Spelled out here rather than imported from the
#: service, so renaming one side alone cannot leave this file agreeing with itself.
UNCONFIGURED = "open_platform_unconfigured"
WRITE_FAILED = "storage_read_only"

BODY = {"app_name": "r106-oa", "allowed_actions": ["query"]}


def _headers(username: str) -> dict:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


@pytest.fixture()
def client(monkeypatch):
    """A TestClient over the real app, plus one account allowed to register apps."""
    from app.common import auth
    from app.main import app

    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "id": f"u-{username}",
            "username": username,
            "role": "admin",
            "department": "",
        },
    )
    return TestClient(app)


@pytest.fixture()
def audit_calls(monkeypatch):
    """Every audit line the registration route writes, in call order, unedited."""
    from app.api.v1 import open_platform as routes

    calls: list[tuple] = []
    monkeypatch.setattr(routes, "record_audit", lambda *args, **kwargs: calls.append(args))
    return calls


@pytest.fixture()
def registry():
    """Hand each case the module-level registry, then put it back where it was found.

    ``_STORE`` is process state: an ``error`` left behind by one case would be read as the
    next case's refusal reason, and an application registered here stays signed against
    every later test in the run. The empty value falls back to memory and clears both.
    """
    from app.common import open_platform

    yield open_platform
    open_platform.configure_app_store("")


def _offline_probes(monkeypatch) -> None:
    """A health read must not open a socket, so the three probes are simulated."""
    from app.common import monitoring

    monkeypatch.setattr(monitoring, "_probe_ollama", lambda: {"status": "ok"})
    monkeypatch.setattr(monitoring, "_probe_postgres", lambda: {"status": "not_configured"})
    monkeypatch.setattr(monitoring, "_probe_redis", lambda: {"status": "not_configured"})


def _production_without_a_store(registry, monkeypatch):
    """The fact R106 is about: production, and no store path was ever named."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("OPEN_PLATFORM_APP_STORE_PATH", raising=False)
    registry.configure_app_store("")
    assert registry._STORE["path"] is None and registry._STORE["store"] is None
    return registry


def _production_with_a_store_that_refuses_the_write(registry, monkeypatch, tmp_path):
    """The opposite fact: the store exists and was opened, then would not take the row."""
    monkeypatch.setenv("APP_ENV", "production")
    path = tmp_path / "apps.json"
    monkeypatch.setenv("OPEN_PLATFORM_APP_STORE_PATH", str(path))
    registry.configure_app_store(str(path))
    store = registry._STORE["store"]
    assert store is not None, "this case is about a store which exists and then fails"

    def fail_upsert(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(store, "upsert", fail_upsert)
    return registry


def _production_with_a_store_that_cannot_be_opened(registry, monkeypatch, tmp_path):
    """A named store which this process cannot even open: configured, and broken.

    The path sits under a plain file, so creating its parent directory fails on the first
    touch. ``register_application`` then reaches the same raise as an unconfigured
    deployment does -- there is no store object to write through -- and its message says
    so. The state is the one which tells the truth here: the operator did name a store.
    """
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("not a directory", encoding="utf-8")
    path = str(blocker / "apps.json")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPEN_PLATFORM_APP_STORE_PATH", path)
    registry.configure_app_store(path)
    assert registry._STORE["store"] is None and registry._STORE["error"]
    return registry


def _production_with_a_working_store(registry, monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    path = tmp_path / "apps.json"
    monkeypatch.setenv("OPEN_PLATFORM_APP_STORE_PATH", str(path))
    registry.configure_app_store(str(path))
    assert registry._STORE["store"] is not None
    return registry


def _development_without_a_store(registry, monkeypatch):
    """The same missing store in a process which is allowed to keep a dictionary."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("OPEN_PLATFORM_APP_STORE_PATH", raising=False)
    registry.configure_app_store("")
    assert registry._STORE["path"] is None
    return registry


def _denied_reasons(calls) -> list[str]:
    """The reason column of refusals only; an allowed registration proves nothing."""
    return [call[4] for call in calls if call[2] == "denied"]


def _health_section(client, monkeypatch) -> dict:
    """The registry's own line in the health snapshot, as an operator reads it."""
    _offline_probes(monkeypatch)
    health = client.get(HEALTH_PATH, headers=_headers("r106-admin"))
    assert health.status_code == 200, health.text
    return health.json()["storage"]["subsystems"]["open_platform_apps"]


def test_an_unconfigured_production_deployment_answers_409_with_its_own_word(client, monkeypatch, registry):
    """判据 2: a deployment which never enabled this feature is not an outage."""
    _production_without_a_store(registry, monkeypatch)

    response = client.post(APPS_PATH, json=BODY, headers=_headers("r106-admin"))

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == UNCONFIGURED
    # The word this ticket exists to retire must not come back through the detail: a
    # client keyed on it would retry, and nothing retried configures a store.
    assert response.json()["detail"] != WRITE_FAILED


def test_a_store_which_was_configured_and_failed_keeps_the_503(client, monkeypatch, registry, tmp_path):
    """判据 2 the other way: a real write failure stays 503. Softening it is a reject."""
    _production_with_a_store_that_refuses_the_write(registry, monkeypatch, tmp_path)

    response = client.post(APPS_PATH, json=BODY, headers=_headers("r106-admin"))

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == WRITE_FAILED


def test_development_registration_is_not_collateral_damage(client, monkeypatch, registry):
    """判据 3: correcting one exit must not install a second refusal next to it."""
    _development_without_a_store(registry, monkeypatch)

    response = client.post(APPS_PATH, json=BODY, headers=_headers("r106-admin"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["app_id"] and body["secret"]
    assert body["storage_mode"] == "memory"
    # Nothing is refused in this state, so there is no reason to name.
    assert "reason" not in registry.app_registry_storage_state()


def test_a_durable_store_registers_and_explains_nothing(client, monkeypatch, registry, tmp_path):
    _production_with_a_working_store(registry, monkeypatch, tmp_path)

    response = client.post(APPS_PATH, json=BODY, headers=_headers("r106-admin"))

    assert response.status_code == 200, response.text
    assert response.json()["storage_mode"] == "json"
    state = registry.app_registry_storage_state()
    assert state["durable"] is True and "reason" not in state


def test_health_details_and_the_route_quote_the_same_word(client, monkeypatch, registry, tmp_path):
    """判据 3: one fact, one word, read out of one field by both surfaces."""
    _production_without_a_store(registry, monkeypatch)
    posted = client.post(APPS_PATH, json=BODY, headers=_headers("r106-admin"))
    section = _health_section(client, monkeypatch)
    assert posted.status_code == 409, posted.text
    assert section["reason"] == posted.json()["detail"] == UNCONFIGURED
    assert section["protection"] == "read_only" and section["durable"] is False

    _production_with_a_store_that_refuses_the_write(registry, monkeypatch, tmp_path)
    posted = client.post(APPS_PATH, json=BODY, headers=_headers("r106-admin"))
    section = _health_section(client, monkeypatch)
    assert posted.status_code == 503, posted.text
    assert section["reason"] == posted.json()["detail"] == WRITE_FAILED


def test_the_three_refusals_leave_three_different_audit_reasons(client, monkeypatch, registry, tmp_path, audit_calls):
    """判据 2 audit half: whoever reads the trail tells these three apart."""
    _production_without_a_store(registry, monkeypatch)
    assert client.post(APPS_PATH, json=BODY, headers=_headers("r106-admin")).status_code == 409

    _production_with_a_store_that_refuses_the_write(registry, monkeypatch, tmp_path)
    assert client.post(APPS_PATH, json=BODY, headers=_headers("r106-admin")).status_code == 503

    _production_without_a_store(registry, monkeypatch)
    refused = client.post(
        APPS_PATH, json={"app_name": "r106-oa", "allowed_actions": []}, headers=_headers("r106-admin")
    )
    assert refused.status_code == 400, refused.text

    reasons = _denied_reasons(audit_calls)
    assert reasons == [UNCONFIGURED, WRITE_FAILED, "allowed_actions_required"]
    assert len(set(reasons)) == 3


def test_the_exit_follows_the_state_field_and_not_the_words_of_the_exception(client, monkeypatch, registry, tmp_path):
    """判据 1: no second source. The route believes the state, not its own reading.

    Here the two disagree on purpose. With no store object to write through, the service
    raises the message it reserves for an unconfigured deployment, so a route which
    sniffed ``str(exc)`` or re-read the environment would answer 409 -- and would then
    contradict the health page, which reads ``reason`` off the same state and says the
    named store could not be opened. The state wins: this is a storage failure.
    """
    from app.common.monitoring import ProductionReadOnlyProtection

    registry = _production_with_a_store_that_cannot_be_opened(registry, monkeypatch, tmp_path)
    with pytest.raises(ProductionReadOnlyProtection) as raised:
        registry.register_application("r106-oa", allowed_actions=["query"])
    assert "is required in production" in str(raised.value), "the trap this case exists for"

    response = client.post(APPS_PATH, json=BODY, headers=_headers("r106-admin"))

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == WRITE_FAILED
    assert _health_section(client, monkeypatch)["reason"] == WRITE_FAILED
