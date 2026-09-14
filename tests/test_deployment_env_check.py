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
