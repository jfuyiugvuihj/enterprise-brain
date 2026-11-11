"""R96: the provenance classifier behind P-8 must never bless a stale image.

``scripts/check_image_provenance.py`` is the replacement for comparing an image's UTC
``Created`` timestamp with a local committer date. The whole value of that swap is one
function, so the function is tested against the cases that used to be got wrong --
including the tempting one, where a documentation-only commit makes an old image look
stale and somebody "fixes" the check by loosening it.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_image_provenance.py"
DOCKERFILE = ROOT / "Dockerfile"


def _load():
    spec = importlib.util.spec_from_file_location("check_image_provenance", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prov = _load()


@pytest.mark.parametrize(
    ("stamped", "expected", "ancestor", "touched", "dirty", "state"),
    [
        ("1a2b3c4", "1a2b3c4", True, [], False, prov.MATCH),
        ("unknown", "1a2b3c4", True, [], False, prov.UNSTAMPED),
        ("", "1a2b3c4", True, [], False, prov.UNSTAMPED),
        ("<label absent>", "1a2b3c4", True, [], False, prov.UNSTAMPED),
        # An image built from an uncommitted tree cannot be described by a commit id.
        ("1a2b3c4+dirty", "1a2b3c4", True, [], False, prov.UNSTAMPED),
        # A clean stamp says nothing about edits made after the build: prove it per file.
        ("1a2b3c4", "1a2b3c4", True, [], True, prov.UNSTAMPED),
        # Rebased or built from another branch: never a pass, whatever the diff says.
        ("9z8y7x6", "1a2b3c4", False, [], False, prov.MISMATCH),
        # The load-bearing pair: only commits that touch nothing the image carries may pass.
        ("1a2b3c4", "5d6e7f8", True, ["app/rag/retriever.py"], False, prov.MISMATCH),
        ("1a2b3c4", "5d6e7f8", True, [], False, prov.DOCS_ONLY),
    ],
)
def test_decide_states(stamped, expected, ancestor, touched, dirty, state) -> None:
    assert prov.decide(stamped, expected, ancestor, touched, dirty)[0] == state


def test_a_dirty_tree_is_never_reported_as_a_match() -> None:
    """The hole this ticket nearly shipped with: HEAD unchanged, files edited afterwards.

    The stamp still equals HEAD, so a string comparison alone would say MATCH while the
    image is missing the edits. Every dirty tree must be pushed down to per-file proof.
    """
    state, message = prov.decide("1a2b3c4", "1a2b3c4", True, [], True)
    assert state == prov.UNSTAMPED
    assert "per file" in message


def test_source_dirs_stay_in_step_with_what_the_dockerfile_copies() -> None:
    """A new COPY that the checker ignores would make it certify images missing code."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    copied = set(re.findall(r"^COPY (?:--\S+\s+)(\S+) ", text, re.MULTILINE))
    directories = {name for name in copied if Path(name).is_dir() or "." not in name}
    assert set(prov.SOURCE_DIRS) == directories, (
        "SOURCE_DIRS and the Dockerfile source COPYs drifted apart: "
        + str(sorted(directories ^ set(prov.SOURCE_DIRS)))
    )


def test_file_inputs_cover_everything_copied_outside_the_source_dirs() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    loose = {name for name in re.findall(r"^COPY (?:--\S+\s+)*([^ ]+) ", text, re.MULTILINE)
             if "." in name or "/" in name and not name.startswith(("app", "scripts", "deploy", "migrations"))}
    listed = set(prov.FILE_INPUTS) | set(prov.SOURCE_DIRS)
    assert loose <= listed, "COPY list names " + str(sorted(loose - listed)) + " which the checker never compares"
