"""Offline gates for the Compose environment pre-flight script."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_deployment_env.py"

_spec = importlib.util.spec_from_file_location("check_deployment_env", SCRIPT)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)

BCRYPT_LIKE = "$2b$12$abcdefghijklmnopqrstuv$31abcdefghijklmnopqrstuvwxyz"


def test_a_bare_dollar_is_reported_at_every_offending_column() -> None:
    assert checker.single_dollar_offsets("a$b$$c$") == [1, 6]
    assert checker.single_dollar_offsets("no-dollars-here") == []


def test_an_unescaped_hash_is_a_hazard_and_the_doubled_form_is_not() -> None:
    entries = [("AUTH_PASSWORD_HASH", BCRYPT_LIKE), ("AUTH_USERNAME", "operator")]
    hazards = checker.find_interpolation_hazards(entries)
    assert [key for key, _ in hazards] == ["AUTH_PASSWORD_HASH"]
    escaped = BCRYPT_LIKE.replace("$", "$$")
    assert checker.find_interpolation_hazards([("AUTH_PASSWORD_HASH", escaped)]) == []


def test_required_keys_accept_either_jwt_variable_name() -> None:
    entries = [
        ("POSTGRES_USER", "brain"),
        ("POSTGRES_PASSWORD", "secret"),
        ("REDIS_PASSWORD", "secret"),
        ("CORS_ALLOW_ORIGINS", "http://localhost"),
        ("JWT_SECRET", "value"),
    ]
    assert checker.missing_required_keys(entries) == []
    assert checker.missing_required_keys(entries[:-1]) == ["JWT_SECRET"]


def test_a_missing_secret_is_still_missing_even_when_the_key_is_present() -> None:
    entries = [("POSTGRES_USER", "brain"), ("POSTGRES_PASSWORD", "   ")]
    assert "POSTGRES_PASSWORD" in checker.missing_required_keys(entries)


def test_the_report_names_keys_only_and_never_prints_a_value(tmp_path, capsys) -> None:
    path = tmp_path / "deploy.env"
    path.write_text("AUTH_PASSWORD_HASH=" + BCRYPT_LIKE + "\n", encoding="utf-8")
    assert checker.main([str(path), "--no-require-keys"]) == 1
    printed = capsys.readouterr().out
    assert "AUTH_PASSWORD_HASH" in printed
    assert "abcdefghijklmnopqrstuv" not in printed


def test_main_passes_a_clean_file_and_fails_when_a_required_key_is_absent(tmp_path, capsys) -> None:
    good = tmp_path / "good.env"
    good.write_text(
        "\n".join(
            [
                "POSTGRES_USER=brain",
                "POSTGRES_PASSWORD=str0ng",
                "REDIS_PASSWORD=str0ng",
                "CORS_ALLOW_ORIGINS=http://localhost",
                "JWT_SECRET_KEY=str0ng",
                "AUTH_PASSWORD_HASH=$$2b$$12$$salt$$rest",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert checker.main([str(good)]) == 0
    assert "no interpolation hazards" in capsys.readouterr().out

    partial = tmp_path / "partial.env"
    partial.write_text("POSTGRES_USER=brain\n", encoding="utf-8")
    assert checker.main([str(partial)]) == 1
    assert checker.main([str(tmp_path / "absent.env")]) == 2


@pytest.mark.parametrize("line", ["# comment", "", "not-an-assignment"])
def test_comments_and_malformed_lines_are_ignored(tmp_path, line) -> None:
    path = tmp_path / "odd.env"
    path.write_text(line + "\n", encoding="utf-8")
    assert checker.check_env_file(path, require_keys=False)["hazards"] == []


COMPOSE_KEYS = [
    ("POSTGRES_USER", "brain"),
    ("POSTGRES_PASSWORD", "secret"),
    ("REDIS_PASSWORD", "secret"),
    ("CORS_ALLOW_ORIGINS", "http://localhost"),
    ("JWT_SECRET", "value"),
]


def _env_file(tmp_path, name, entries):
    path = tmp_path / name
    path.write_text("\n".join(f"{key}={value}" for key, value in entries) + "\n", encoding="utf-8")
    return path


def test_a_production_file_needs_the_admin_bootstrap_pair(tmp_path) -> None:
    entries = [("APP_ENV", "production")] + COMPOSE_KEYS + [("AUTH_USERNAME", ""), ("AUTH_PASSWORD_HASH", "")]

    missing = checker.check_env_file(_env_file(tmp_path, "prod.env", entries))["missing"]

    assert "AUTH_USERNAME" in missing
    assert "AUTH_PASSWORD_HASH" in missing


def test_a_production_file_with_the_bootstrap_pair_is_complete(tmp_path) -> None:
    entries = [
        ("APP_ENV", "production"),
        ("AUTH_USERNAME", "operator"),
        ("AUTH_PASSWORD_HASH", BCRYPT_LIKE.replace("$", "$$")),
    ] + COMPOSE_KEYS

    assert checker.check_env_file(_env_file(tmp_path, "prod.env", entries))["missing"] == []


def test_an_administrator_without_a_department_is_warned_about(tmp_path) -> None:
    entries = [
        ("APP_ENV", "production"),
        ("AUTH_USERNAME", "operator"),
        ("AUTH_PASSWORD_HASH", BCRYPT_LIKE.replace("$", "$$")),
        ("AUTH_DEPARTMENT", ""),
    ] + COMPOSE_KEYS

    result = checker.check_env_file(_env_file(tmp_path, "prod.env", entries))

    assert result["missing"] == []
    assert any("AUTH_DEPARTMENT" in warning for warning in result["warnings"])
    assert "warn" in checker.format_report(result)


def test_a_department_scoped_administrator_produces_no_warning(tmp_path) -> None:
    entries = [
        ("APP_ENV", "production"),
        ("AUTH_USERNAME", "operator"),
        ("AUTH_PASSWORD_HASH", BCRYPT_LIKE.replace("$", "$$")),
        ("AUTH_DEPARTMENT", "head-office"),
    ] + COMPOSE_KEYS

    result = checker.check_env_file(_env_file(tmp_path, "prod.env", entries))

    assert result["warnings"] == []
    assert "ok      no interpolation hazards" in checker.format_report(result)


def test_development_is_not_warned_about_a_departmentless_administrator(tmp_path) -> None:
    entries = [
        ("APP_ENV", "development"),
        ("AUTH_USERNAME", ""),
        ("AUTH_PASSWORD_HASH", ""),
        ("AUTH_DEPARTMENT", ""),
    ] + COMPOSE_KEYS

    assert checker.check_env_file(_env_file(tmp_path, "dev.env", entries))["warnings"] == []


def test_a_development_file_may_leave_the_bootstrap_empty(tmp_path) -> None:
    entries = [
        ("APP_ENV", "development"),
        ("AUTH_USERNAME", ""),
        ("AUTH_PASSWORD_HASH", ""),
    ] + COMPOSE_KEYS

    assert checker.check_env_file(_env_file(tmp_path, "dev.env", entries))["missing"] == []


def test_the_shipped_example_is_incomplete_until_an_operator_fills_it_in() -> None:
    result = checker.check_env_file(ROOT / "deploy" / ".env.server.example")

    assert {"AUTH_USERNAME", "AUTH_PASSWORD_HASH"}.issubset(set(result["missing"]))


def test_the_bootstrap_hint_points_at_the_runbook_without_leaking_the_hash(tmp_path, capsys) -> None:
    entries = [("APP_ENV", "prod")] + COMPOSE_KEYS

    assert checker.main([str(_env_file(tmp_path, "prod.env", entries))]) == 1
    printed = capsys.readouterr().out
    assert "deploy/README.server.md" in printed
    assert "abcdefghijklmnopqrstuv" not in printed
