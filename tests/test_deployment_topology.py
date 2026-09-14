"""Offline deployment-topology consistency gates.

Docker, Compose, Nginx, the queue worker and the scheduler must describe one stack.
These checks run without a container engine; the runtime proof is the separate
``docker compose config`` / build / health verification.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

COMPOSE = ROOT / "docker-compose.yml"
OVERLAY = ROOT / "deploy" / "docker-compose.server.yml"
NGINX = ROOT / "deploy" / "nginx.conf"
DOCKERFILE = ROOT / "Dockerfile"
DOCKER_IGNORE = ROOT / ".dockerignore"
ENV_EXAMPLES = (ROOT / ".env.example", ROOT / "deploy" / ".env.server.example")

_RUNTIME_PATHS = ("documents", "data", "chroma_db", "logs", "static/charts", "static/exports")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


@pytest.fixture(scope="module")
def base() -> dict:
    return _load(COMPOSE)


@pytest.fixture(scope="module")
def overlay() -> dict:
    return _load(OVERLAY)


def test_dockerfile_interpreter_satisfies_requires_python() -> None:
    image = re.search(r"^FROM python:([0-9.]+)-slim", DOCKERFILE.read_text(encoding="utf-8"), re.MULTILINE)
    spec = re.search(r'requires-python = ">=\s*(\d+\.\d+)\s*,\s*<\s*(\d+\.\d+)', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert image and spec, "the image and the dependency contract must both declare a version"
    major, minor = (int(part) for part in image.group(1).split("."))
    low_major, low_minor = (int(part) for part in spec.group(1).split("."))
    high_major, high_minor = (int(part) for part in spec.group(2).split("."))
    assert (major, minor) >= (low_major, low_minor)
    assert (major, minor) < (high_major, high_minor)


def test_dockerfile_resolves_dependencies_inside_the_venv_on_path() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "uv sync --frozen" in text
    assert "/app/.venv/bin" in text, "uv installs into a project venv; PATH must expose it"
    assert re.search(r"^CMD \[\"uvicorn\"", text, re.MULTILINE), "the API must start from that PATH"


def test_dockerfile_ships_migration_and_recovery_tools_but_no_customer_data() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY migrations ./migrations" in text, "scripts/migrate.py needs the SQL catalog in the image"
    assert "COPY scripts ./scripts" in text, "backup and restore scripts must be runnable in the image"
    for runtime_path in ("documents", "data", "chroma_db"):
        assert f"COPY {runtime_path}" not in text, runtime_path + " is customer data, not image content"
    assert re.search(r"^USER \d+:\d+", text, re.MULTILINE), "the container must not run as root"
    assert "HEALTHCHECK" in text


def test_dockerignore_keeps_secrets_and_runtime_data_out_of_the_context() -> None:
    entries = {line.strip() for line in DOCKER_IGNORE.read_text(encoding="utf-8").splitlines() if line.strip()}
    for required in (".env", "data", "documents", "chroma_db", "static/charts", "static/exports", "logs"):
        assert required in entries
    # Anything the Dockerfile copies must survive the ignore list.
    for copied in re.findall(r"^COPY (\S+) ", DOCKERFILE.read_text(encoding="utf-8"), re.MULTILINE):
        assert copied not in entries and copied.rstrip("./") not in entries, copied + " would never reach the build"


def test_the_stack_declares_every_process_the_code_exposes(base) -> None:
    services = base["services"]
    assert {"postgres", "redis", "migrate", "backend", "worker", "scheduler", "frontend"} <= set(services)
    assert services["worker"]["command"] == ["python", "deploy/queue_worker.py"]
    assert services["scheduler"]["command"] == ["python", "deploy/scheduler.py"]
    assert (ROOT / "deploy" / "scheduler.py").is_file()
    assert services["migrate"]["command"] == ["python", "scripts/migrate.py"]
    assert not base["services"]["postgres"]["image"].startswith("postgres:"), (
        "upstream PostgreSQL has no pgvector; migration 0001 would fail"
    )
    assert "pgvector" in base["services"]["postgres"]["image"]


def test_long_running_services_wait_for_a_successful_migration(base) -> None:
    for name in ("backend", "worker", "scheduler"):
        depends = base["services"][name]["depends_on"]
        assert depends["migrate"]["condition"] == "service_completed_successfully", name
        assert depends["postgres"]["condition"] == "service_healthy", name


def test_production_services_persist_the_ledger_and_every_runtime_directory(base) -> None:
    for name in ("backend", "worker", "scheduler"):
        service = base["services"][name]
        assert service["environment"]["PERSISTENCE_BACKEND"] == "postgres", name
        mounted = {entry.split(":")[1] for entry in service["volumes"]}
        assert {"/app/documents", "/app/data", "/app/static", "/app/logs"} <= mounted, name

    # API and worker replicas must not each own a scheduler with external side effects.
    for name in ("backend", "worker"):
        assert base["services"][name]["environment"]["SCHEDULER_ENABLED"] == "false", name
    assert "SCHEDULER_ENABLED" not in base["services"]["scheduler"]["environment"]


def test_only_the_edge_and_a_loopback_operators_port_reach_the_host(base) -> None:
    for name, service in base["services"].items():
        for published in service.get("ports", []):
            binding = str(published)
            if name == "frontend":
                continue
            assert binding.startswith("127.0.0.1:"), name + " must not publish " + binding
    for name in ("postgres", "redis", "ollama"):
        assert not base["services"][name].get("ports"), name + " must stay on the internal network"


def test_no_compose_file_invents_a_model_name_or_a_default_secret() -> None:
    text = COMPOSE.read_text(encoding="utf-8") + "\n" + OVERLAY.read_text(encoding="utf-8")
    assert not re.search(r"LOCAL_MODEL_NAME:\s*[a-z0-9._-]+:?\w*$", text, re.MULTILINE), (
        "the model name must come from the operator environment or local discovery"
    )
    for forbidden in ("password=123", ":changeme", "POSTGRES_PASSWORD: postgres"):
        assert forbidden not in text


def test_required_compose_variables_are_documented_in_both_env_templates(base, overlay) -> None:
    required = set()
    for path in (COMPOSE, OVERLAY):
        required |= set(re.findall(r"\$\{([A-Z0-9_]+):\?", path.read_text(encoding="utf-8")))
    assert required, "the stack must fail closed on missing secrets"
    for path in ENV_EXAMPLES:
        declared = {
            line.split("=", 1)[0].strip()
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if "=" in line and not line.startswith("#")
        }
        missing = required - declared
        assert not missing, path.name + " must declare " + ", ".join(sorted(missing))


def test_the_overlay_only_adjusts_services_the_base_defines(base, overlay) -> None:
    unknown = set(overlay["services"]) - set(base["services"])
    assert not unknown, "the overlay introduces orphan services: " + ", ".join(unknown)
    for name, service in overlay["services"].items():
        assert "build" not in service, name + " must not redefine the image build"
        assert service.get("restart") == "always"
        assert service["logging"]["options"]["max-size"], "a private server needs bounded logs"


def _nginx_directives() -> str:
    """Strip comments so documentation cannot satisfy or break a directive assertion."""
    return "\n".join(
        line.split("#", 1)[0].rstrip() for line in NGINX.read_text(encoding="utf-8-sig").splitlines()
    )


def test_nginx_is_a_conf_d_fragment_without_a_public_runtime_path() -> None:
    text = _nginx_directives()
    for forbidden in ("worker_processes", "events {", "http {"):
        assert forbidden not in text, forbidden + " belongs to the image nginx.conf, not conf.d"
    assert "server backend:8001" in text, "the upstream must name the compose service, not a loopback port"
    assert "proxy_pass http://enterprise_brain_api" in text
    assert "proxy_buffering off" in text, "SSE must not be buffered"
    assert "return 200" not in text, "health must be answered by the backend, not the proxy"
    assert "/path/to/" not in text
    assert re.search(
        r"location\s+~\*\s+\^/\(documents\|data\|logs\|chroma_db\|static[^)]*\)/?\s*\{"
        r"[\s\S]*?deny all;[\s\S]*?return 404;",
        text,
    ), "runtime directories must be refused at the edge"


def test_nginx_does_not_publish_generated_artifacts() -> None:
    text = _nginx_directives()
    assert not re.search(r"location\s+/static/\s*\{", text), "charts and reports are Artifact-route only"
    assert "alias" not in text, "an alias to a host directory would bypass authorization"


def test_scheduled_jobs_are_declared_once(base) -> None:
    text = (ROOT / "app" / "scheduler" / "jobs.py").read_text(encoding="utf-8-sig")
    assert "def register_jobs(" in text
    assert text.count("add_job(evaluate_all") == 1, "duplicate job definitions drift per host"
    assert "def run_forever(" in text


DEPLOYMENT_ENV = "deploy/.env.server"


def _env_file_entries(document: dict) -> dict[str, list[str]]:
    return {
        name: [str(entry) for entry in service["env_file"]]
        for name, service in document["services"].items()
        if isinstance(service, dict) and service.get("env_file")
    }


def test_containers_read_the_deployment_env_file_not_the_developer_one(base) -> None:
    entries = _env_file_entries(base)
    assert entries, "the stack must inject its configuration somewhere"
    for name, files in entries.items():
        assert files == [DEPLOYMENT_ENV], name + " must read only the deployment env file"
    assert "- .env\n" not in COMPOSE.read_text(encoding="utf-8-sig")
    assert "--env-file " + DEPLOYMENT_ENV in COMPOSE.read_text(encoding="utf-8-sig")


def test_the_overlay_uses_the_same_env_file_as_the_base_stack(base, overlay) -> None:
    assert _env_file_entries(overlay) == {}, "the overlay must not redefine the env source"
    assert DEPLOYMENT_ENV in OVERLAY.read_text(encoding="utf-8-sig")


def test_the_deployment_env_file_is_never_committed() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8-sig").split()
    assert DEPLOYMENT_ENV in ignored, "operator secrets must not be able to reach git"
    tracked = subprocess.run(
        ["git", "ls-files", "--", DEPLOYMENT_ENV],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked.returncode == 0 and not tracked.stdout.strip(), "the real env file must stay untracked"


def test_the_env_examples_explain_the_two_escaping_regimes() -> None:
    server = (ROOT / "deploy" / ".env.server.example").read_text(encoding="utf-8-sig")
    assert "$$" in server and "literal $" in server
    assert "check_deployment_env" in server, "the example must point at the pre-flight"
    developer = (ROOT / ".env.example").read_text(encoding="utf-8-sig")
    assert "python-dotenv" in developer and DEPLOYMENT_ENV in developer


def test_the_deployment_documents_give_the_pre_flight_command() -> None:
    for document in (ROOT / "README.md", ROOT / "deploy" / "README.server.md"):
        text = document.read_text(encoding="utf-8-sig")
        assert "--env-file " + DEPLOYMENT_ENV in text, str(document)
        assert "check_deployment_env" in text, str(document)
    assert (ROOT / "scripts" / "check_deployment_env.py").is_file()
