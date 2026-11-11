"""跟进单 R70 的守卫测试：宿主的 .env 在 pytest 期间一个字都不许进测试进程。

生产侧有 5 个模块在 import 期调 dotenv.load_dotenv()（app/agents/nodes.py:10、
app/agents/orchestrator.py:21、app/common/auth.py:13、app/common/model_handler.py:28、
app/rag/retriever.py:19），而 app/common/monitoring.py 的 build_health_snapshot() 要到调用期
才懒加载 auth 与 retriever。两者叠加的后果：一个先把模型环境变量擦干净、再打健康快照的用例，
会在打快照那一刻被宿主 .env 重新灌回真机模型名 —— 主树 .env 里有 OLLAMA_MODEL 时，
"未配置模型"的断言稳定为红；而 .env 不入版本库，没有它的子树里全绿。
tests/conftest.py 为此把 load_dotenv 换成只记账不读文件的桩，本文件钉住这个事实。

反证：删掉 conftest 里那次赋值，第一个用例立刻红；在有 .env 的主树上，第三个用例也会红。
"""
import os

import pytest

#: 与 app/common/model_config.py:161-167 一一对应的四个变量，少钉一个都算漏。
MODEL_ENV_NAMES = ("LOCAL_MODEL_NAME", "OLLAMA_MODEL", "LOCAL_MODEL_BASE_URL", "OLLAMA_BASE_URL")


def test_the_dotenv_stub_is_installed_before_app_can_import_it(dotenv_guard):
    if dotenv_guard.live:
        pytest.skip(f"{dotenv_guard.flag} 为真时按设计不装桩（真机验收态自己负责环境）")
    import dotenv

    assert dotenv.load_dotenv is dotenv_guard.stub, (
        "dotenv.load_dotenv 不再是 conftest 的桩：宿主的 .env 又能往测试进程里写东西了。"
        "这条红不等于被测代码有错，但它会让所有\"干净环境\"用例随机器配置漂移。"
    )


def test_the_stub_records_the_attempt_and_writes_nothing(dotenv_guard, monkeypatch):
    import dotenv

    for name in MODEL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    before = dict(os.environ)
    assert dotenv.load_dotenv() is False, "桩必须报告\"什么都没加载\""
    assert dotenv_guard.blocked, "桩被调用却没留下任何记账，账本形同虚设"
    assert dict(os.environ) == before, (
        f"桩往 os.environ 里写了 {sorted(set(os.environ) ^ set(before))}，隔离失效"
    )


def test_a_health_snapshot_cannot_reinject_the_host_model_name(monkeypatch) -> None:
    from app.common import model_config, monitoring

    # 按 test_deployment_guards.py 的既有惯例把 Ollama 探针换成离线值，测试期不开 socket。
    monkeypatch.setattr(monitoring, "_probe_ollama", lambda: {"status": "ok"})
    for name in MODEL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    model_config.reset_model_discovery_cache()
    monkeypatch.setattr(model_config, "_cached_discovery", lambda _base_url: "")

    snapshot = monitoring.build_health_snapshot()["model"]

    assert snapshot["name"] is None, (
        f"健康快照报出了模型名 {snapshot['name']!r}：宿主 .env 在打快照那一刻被灌进了测试进程"
    )
    assert snapshot["source"] == "none", f"模型来源应为 none，实际 {snapshot['source']!r}"
    assert not os.environ.get("OLLAMA_MODEL"), (
        "打完快照 os.environ 里又出现了 OLLAMA_MODEL："
        f"{os.environ['OLLAMA_MODEL']!r} —— .env 泄漏未被拦下"
    )
