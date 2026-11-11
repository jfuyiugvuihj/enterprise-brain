"""Pins for the corpus parity check.

These run offline on purpose: a pre-flight gate that needs a live server cannot tell
"the corpus drifted" apart from "the server is down". The interesting failure is the one
nobody notices -- a file that sits in documents/, is tracked by git, and is in neither the
manifest nor an exemption, so it never reaches the knowledge base and never shows up in a
count either. That is exactly how refactor_guide.pdf hid.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check_corpus_parity.py"
MANIFEST_PATH = ROOT / "deploy" / "workspace-seed.json"

_spec = importlib.util.spec_from_file_location("check_corpus_parity", SCRIPT_PATH)
parity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(parity)

#: Rows the live volume holds and the repository does not, so no seed run can rebuild them.
#: Narrowing this list means a file came back; widening it is an admission of data loss.
SERVER_ONLY_ROWS = [
    "browser_acceptance_policy.txt",
    "六级作文模板.docx",
    "深度学习入门：基于Python的理论与实现.pdf",
    "深度学习技术栈学习路线.pdf",
]


def _manifest(files, non_corpus=None):
    manifest = {"corpus_directory": "documents", "documents": {"files": files}}
    if non_corpus:
        manifest["non_corpus"] = non_corpus
    return manifest


def _workspace():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    directory = str(manifest["corpus_directory"])
    tracked = parity.tracked_names(ROOT, directory)
    disk = {path.name for path in (ROOT / directory).iterdir() if path.is_file()}
    return manifest, tracked, disk


def test_a_row_only_the_volume_holds_is_warned_and_not_blocked():
    manifest = _manifest(["kept.txt", "gone.txt"])
    result = parity.compare(manifest, {"kept.txt"}, {"kept.txt"}, {"kept.txt", "gone.txt"})

    assert result["server_only"] == ["gone.txt"]
    assert result["absent_everywhere"] == [], "the index has it, so a seed run is not blocked"
    assert not parity.failed(result, [])


def test_a_manifest_row_missing_from_disk_and_index_blocks_the_window():
    manifest = _manifest(["kept.txt", "nowhere.txt"])
    result = parity.compare(manifest, {"kept.txt"}, {"kept.txt"}, {"kept.txt"})

    assert result["absent_everywhere"] == ["nowhere.txt"]
    assert parity.failed(result, [])


def test_a_tracked_file_outside_the_manifest_needs_a_declared_reason():
    undeclared = parity.compare(
        _manifest(["a.txt"]), {"a.txt", "junk.pdf"}, {"a.txt", "junk.pdf"}, {"a.txt"}
    )

    assert undeclared["never_seedable"] == ["junk.pdf"]
    assert parity.failed(undeclared, []), "an unseedable file must be argued about, not ignored"

    declared = parity.compare(
        _manifest(["a.txt"], {"junk.pdf": "not enterprise corpus"}),
        {"a.txt", "junk.pdf"},
        {"a.txt", "junk.pdf"},
        {"a.txt"},
    )
    assert declared["never_seedable"] == []
    assert not parity.failed(declared, [])


def test_an_exempted_row_must_not_be_retrievable():
    manifest = _manifest(["a.txt"], {"junk.pdf": "not enterprise corpus"})
    result = parity.compare(
        manifest,
        {"a.txt", "junk.pdf"},
        {"a.txt", "junk.pdf"},
        {"a.txt", "junk.pdf"},
    )

    assert result["non_corpus_still_live"] == ["junk.pdf"]
    assert parity.failed(result, [])


def test_an_unaccounted_live_row_is_a_failure_not_a_surprise():
    result = parity.compare(_manifest(["a.txt"]), {"a.txt"}, {"a.txt"}, {"a.txt", "ghost.txt"})

    assert result["unexplained_live"] == ["ghost.txt"]
    assert parity.failed(result, [])


def test_offline_mode_reports_nothing_it_could_not_see():
    result = parity.compare(_manifest(["kept.txt", "gone.txt"]), {"kept.txt"}, {"kept.txt"}, None)

    assert result["have_live"] is False
    assert result["server_only"] == [], "without the index there is no evidence for this bucket"
    assert result["counts"]["live"] == "n/a"
    assert not parity.failed(result, None)


def test_catalog_rows_that_are_not_indexed_block():
    result = parity.compare(_manifest(["a.txt"]), {"a.txt"}, {"a.txt"}, {"a.txt"})

    assert not parity.failed(result, [])
    assert parity.failed(result, ["a.txt"])


def test_nothing_tracked_under_documents_escapes_the_manifest():
    manifest, tracked, disk = _workspace()

    assert tracked, "git tracked nothing under the corpus directory"
    assert tracked == disk, (
        "documents/ differs from what git tracks, and the repo side of this check reads git"
    )

    result = parity.compare(manifest, disk, tracked, None)
    never_seedable = result["never_seedable"]

    assert never_seedable == [], "tracked but unseedable: seed it, delete it, or declare it " + str(never_seedable) + " in the non_corpus section of deploy/workspace-seed.json with a reason"


def test_every_non_corpus_declaration_names_a_real_tracked_file():
    manifest, tracked, _disk = _workspace()

    for name, reason in manifest.get("non_corpus", {}).items():
        assert name in tracked, f"{name!r} is declared non-corpus but is not even in the repository"
        assert name not in manifest["documents"]["files"], f"{name!r} is both seeded and exempt"
        assert len(str(reason).strip()) > 20, f"{name!r} is exempted without a reason worth reading"


def test_the_manifest_still_names_its_server_only_rows():
    manifest, _tracked, disk = _workspace()

    missing = sorted(str(name) for name in manifest["documents"]["files"] if name not in disk)

    assert missing == SERVER_ONLY_ROWS, (
        "the server-only set changed: putting a lost file back narrows it, and that is the fix"
    )


def test_every_bucket_has_a_readable_label():
    for key in parity.BUCKETS:
        assert parity.label(key)
    assert set(parity.BLOCKING) <= set(parity.BUCKETS)
