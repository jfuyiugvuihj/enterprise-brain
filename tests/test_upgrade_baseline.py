from pathlib import Path


def test_core_upgrade_modules_are_importable():
    from app.agents import contracts, critic, planner
    from app.common import auth, model_config
    from app.rag import retrieval_pipeline

    assert contracts.AgentResult
    assert callable(critic.review_agent_results)
    assert callable(planner.build_task_plan)
    assert callable(auth.verify_token)
    assert callable(model_config.get_local_model_settings)
    assert callable(retrieval_pipeline.rrf_fusion)


def test_local_model_settings_always_name_an_endpoint_and_key(monkeypatch):
    from app.common import model_config

    for name in (
        "LOCAL_MODEL_BASE_URL",
        "LOCAL_MODEL_NAME",
        "LOCAL_MODEL_API_KEY",
        "OLLAMA_MODEL",
        "OLLAMA_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = model_config.get_local_model_settings(discover=lambda _base_url: "local-chat")

    assert settings.base_url.endswith("/v1")
    assert settings.model_name == "local-chat"
    assert settings.api_key


def test_deployment_templates_do_not_require_cloud_model_credentials():
    compose_files = list(Path("deploy").glob("*.yml")) + list(Path("deploy").glob("*.yaml"))

    assert compose_files
    text = "\n".join(path.read_text(encoding="utf-8") for path in compose_files)
    assert "OPENAI_API_KEY" not in text
    assert "ANTHROPIC_API_KEY" not in text
