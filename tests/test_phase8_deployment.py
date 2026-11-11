from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app as main_app
from app.api.v1.auth import router as auth_router


ROOT = Path(__file__).resolve().parents[1]


class TestPhase8Deployment:
    def test_deployment_artifacts_exist(self):
        assert (ROOT / "Dockerfile").exists()
        assert (ROOT / "docker-compose.yml").exists()
        assert (ROOT / ".dockerignore").exists()
        assert (ROOT / ".env.example").exists()

    def test_readme_mentions_one_command_startup(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        assert "docker compose" in text.lower()
        assert "一条命令" in text or "one command" in text.lower()

    def test_compose_defines_the_api_worker_and_scheduler_processes(self):
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        # One name for the API across the stack, the edge proxy and the overlay.
        for service in ("backend:", "worker:", "scheduler:", "migrate:"):
            assert service in text
        assert "deploy/queue_worker.py" in text
        assert "deploy/scheduler.py" in text
        assert "scripts/migrate.py" in text
        # The API itself starts from the image command, which is the same uvicorn used
        # by every non-container start path.
        assert "uvicorn" in (ROOT / "Dockerfile").read_text(encoding="utf-8")

    def test_the_stack_gates_on_readiness_and_forbids_default_secrets(self):
        base = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        overlay = (ROOT / "deploy/docker-compose.server.yml").read_text(encoding="utf-8")

        assert "healthcheck:" in base
        assert "condition: service_healthy" in base
        assert "condition: service_completed_successfully" in base
        assert "${POSTGRES_PASSWORD:?" in base
        assert "${REDIS_PASSWORD:?" in base
        for literal in ("POSTGRES_PASSWORD: postgres", "enterprise_brain_pwd", "REDIS_PASSWORD: \"\""):
            assert literal not in base
            assert literal not in overlay

    def test_server_env_example_declares_database_password_without_real_secret(self):
        text = (ROOT / "deploy/.env.server.example").read_text(encoding="utf-8")

        assert "POSTGRES_PASSWORD=" in text
        assert "enterprise_brain_pwd" not in text

    def test_backup_restore_runbook_covers_postgres_dump_restore_order(self):
        text = (ROOT / "docs/deployment/backup-restore.md").read_text(encoding="utf-8")

        assert "pg_dump" in text
        assert "pg_restore" in text
        assert "## 数据库恢复" in text

    def test_health_endpoint_is_public(self):
        app = FastAPI()
        app.include_router(auth_router, prefix="/api/v1")
        client = TestClient(app)

        response = client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_main_middleware_whitelists_health_endpoint(self):
        client = TestClient(main_app)

        response = client.get("/api/v1/health")

        assert response.status_code == 200
