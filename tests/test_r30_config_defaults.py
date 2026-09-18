"""R30 judgement (3): the default in the code and the default on the page are one number.

``app/common/model_handler.py`` used to read ``MODEL_REQUEST_TIMEOUT`` with a default of 60
while both shipped env samples documented 120. Nobody was wrong exactly: the operator who
followed the documentation got one machine, the operator who left the line out got another,
and the difference only appeared as a timeout in production. These tests make that pair of
statements impossible.
"""

from pathlib import Path

import pytest

from app.common import model_budget
from app.common.model_budget import budget_env_defaults, request_timeout_ceiling_seconds
from app.common.model_handler import ModelHandler
from app.common.rbac import (
    ROW_DEPARTMENT_SCOPE_ENV,
    ROW_DEPARTMENT_SCOPE_FAIL_CLOSED,
    resolve_row_department_scope,
)

_REPOSITORY = Path(__file__).resolve().parents[1]
ENV_FILES = (".env.example", "deploy/.env.server.example")

#: Every budget variable, checked against both samples.
CASES = sorted(budget_env_defaults())


def _documented(path: str) -> dict[str, str]:
    """Parse an env sample the way the two readers do: last assignment wins, ``$`` is literal."""
    values: dict[str, str] = {}
    for line in (_REPOSITORY / path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        values[name.strip()] = value.strip()
    return values


@pytest.mark.parametrize("relative", ENV_FILES)
@pytest.mark.parametrize("name", CASES)
def test_the_code_default_is_written_down_in_both_env_samples(relative, name):
    """One half of judgement (3): the knob is documented where an operator can find it."""
    documented = _documented(relative)

    assert name in documented, f"{name} is read by the code but missing from {relative}"
    assert documented[name] != "", f"{name} is documented as empty in {relative}"


@pytest.mark.parametrize("relative", ENV_FILES)
@pytest.mark.parametrize("name", CASES)
def test_the_documented_number_equals_the_number_the_code_uses(relative, name):
    """The other half: they are equal, and equal as numbers, not as strings that happen to match."""
    documented = _documented(relative)[name]
    default = budget_env_defaults()[name]

    if isinstance(default, bool):  # pragma: no cover - no budget flag is a bool
        assert documented.lower() == str(default).lower(), (relative, name)
    elif isinstance(default, int) and not isinstance(default, float):
        assert int(documented) == default, (relative, name, documented, default)
    else:
        assert float(documented) == pytest.approx(float(default)), (relative, name)


def test_the_two_samples_do_not_disagree_with_each_other():
    """Two documents that drift is the same defect with a second copy."""
    parsed = {relative: _documented(relative) for relative in ENV_FILES}
    drift = [
        name
        for name in CASES
        if parsed[ENV_FILES[0]].get(name) != parsed[ENV_FILES[1]].get(name)
    ]

    assert drift == [], drift


def test_the_handler_no_longer_keeps_its_own_copy_of_the_timeout():
    """The exact 60-vs-120 defect, closed at the place it lived."""
    handler = ModelHandler()

    assert handler.request_timeout == request_timeout_ceiling_seconds()


def test_model_request_timeout_is_read_in_exactly_one_place():
    """A second reader is how the two numbers came apart in the first place."""
    readers = [
        path.relative_to(_REPOSITORY).as_posix()
        for path in (_REPOSITORY / "app").rglob("*.py")
        if "MODEL_REQUEST_TIMEOUT" in path.read_text(encoding="utf-8")
    ]

    assert readers == ["app/common/model_budget.py"], readers


def test_an_unset_budget_variable_and_a_documented_one_agree(monkeypatch):
    """Deleting the line must not change the machine, which is what the samples promise."""
    for name, default in budget_env_defaults().items():
        monkeypatch.delenv(name, raising=False)

    profile = model_budget.tier_profile("analysis")

    assert profile["max_tokens"] == budget_env_defaults()["MODEL_TIER_ANALYSIS_MAX_TOKENS"]
    assert profile["timeout_ceiling_seconds"] == budget_env_defaults()["MODEL_REQUEST_TIMEOUT"]
    assert profile["context_limit_tokens"] == budget_env_defaults()["MODEL_CONTEXT_TOKENS"]


def test_the_row_department_scope_switch_is_documented_with_its_real_default(monkeypatch):
    """R17 closed with the switch undocumented; the debt is paid against the real value.

    Read in both directions on purpose. The page must show what the code resolves with the
    variable absent, and writing the page's own value must resolve back to itself: a
    documented value the code silently overrode with a stricter one would look correct in
    a diff and fail in production.
    """
    monkeypatch.delenv(ROW_DEPARTMENT_SCOPE_ENV, raising=False)
    resolved_when_unset = resolve_row_department_scope()

    assert resolved_when_unset == ROW_DEPARTMENT_SCOPE_FAIL_CLOSED
    for relative in ENV_FILES:
        documented = _documented(relative)
        assert ROW_DEPARTMENT_SCOPE_ENV in documented, relative
        value = documented[ROW_DEPARTMENT_SCOPE_ENV]
        assert value == resolved_when_unset, (relative, value)
        monkeypatch.setenv(ROW_DEPARTMENT_SCOPE_ENV, value)
        assert resolve_row_department_scope() == value, (relative, value)


def test_the_code_falls_back_to_what_the_page_promises(monkeypatch):
    """Unset must mean fail_closed, the same answer the samples tell an operator to expect."""
    monkeypatch.delenv(ROW_DEPARTMENT_SCOPE_ENV, raising=False)

    assert resolve_row_department_scope() == ROW_DEPARTMENT_SCOPE_FAIL_CLOSED
