from pathlib import Path


def test_deployment_files_use_private_model_and_local_services_only():
    compose_files = [Path("docker-compose.yml"), Path("deploy/docker-compose.server.yml"), Path("deploy/.env.server.example"), Path(".env.example")]
    texts = "\n".join(path.read_text(encoding="utf-8") for path in compose_files if path.exists())

    assert "OPENAI_API_KEY" not in texts
    assert "ANTHROPIC_API_KEY" not in texts
    assert "http://ollama:11434" in texts or "http://host.docker.internal:11434" in texts
    assert "postgres" in texts.lower()
    assert "redis" in texts.lower()


def test_deployment_example_does_not_expose_public_model_provider_name():
    text = Path("deploy/.env.server.example").read_text(encoding="utf-8")
    assert "gpt-4" not in text.lower()
    assert "claude" not in text.lower()
