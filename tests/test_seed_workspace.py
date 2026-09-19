"""Pins for the one-shot bring-up of a deployment's workspace.

A run that scores an empty knowledge base is not a measurement. The corpus used to be
loaded by hand, from an untracked shell history, which is how that happened twice. These
pins keep scripts/seed_workspace.py honest about the two failure modes that matter: a
manifest name that quietly stops being reproducible, and a second run that uploads again.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "seed_workspace.py"

_spec = importlib.util.spec_from_file_location("seed_workspace", SCRIPT_PATH)
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)

MANIFEST_PATH = ROOT / "deploy" / "workspace-seed.json"

#: Corpus rows the server holds but the repository does not, so no seed run can rebuild
#: them. Widening this list is an admission of data loss, not a fix: the fix is a file
#: that goes back on disk.
SERVER_ONLY_ROWS = {
    "browser_acceptance_policy.txt",
    "\u516d\u7ea7\u4f5c\u6587\u6a21\u677f.docx",
    "\u6df1\u5ea6\u5b66\u4e60\u5165\u95e8\uff1a\u57fa\u4e8ePython\u7684\u7406\u8bba\u4e0e\u5b9e\u73b0.pdf",
    "\u6df1\u5ea6\u5b66\u4e60\u6280\u672f\u6808\u5b66\u4e60\u8def\u7ebf.pdf",
}


def _manifest(files):
    return {"documents": {"files": files}, "owners": [], "datasets": []}


def _workspace_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_plan_documents_separates_uploadable_from_unmeetable(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")

    wanted, absent, already, server_only = seed.plan_documents(
        _manifest(["a.txt", "b.txt", "c.txt", "d.txt"]), tmp_path, {"a.txt", "c.txt"})

    assert [path.name for path in wanted] == ["b.txt"], "only an on-disk name can be uploaded"
    assert already == ["a.txt"], "already on the server: a second run must be a no-op"
    assert server_only == ["c.txt"], "on the server but not on disk: counted, and warned about"
    assert absent == ["d.txt"], "nowhere at all: the seed has to fail closed on this"


def test_second_run_of_the_same_manifest_uploads_nothing(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    manifest = _manifest(["a.txt"])

    first, *_ = seed.plan_documents(manifest, tmp_path, set())
    second, _, already, _ = seed.plan_documents(manifest, tmp_path, {"a.txt"})

    assert [path.name for path in first] == ["a.txt"]
    assert second == [] and already == ["a.txt"]


def test_every_manifest_document_is_reproducible_from_disk():
    manifest = _workspace_manifest()
    corpus = ROOT / str(manifest["corpus_directory"])
    names = [str(name) for name in manifest["documents"]["files"]]

    assert names, "the seed manifest carries no corpus"
    assert len(names) == len(set(names)), "duplicate document name in the manifest"
    missing = sorted(name for name in names if not (corpus / name).is_file())

    assert missing == sorted(SERVER_ONLY_ROWS), (
        "a manifest name is neither on disk nor an accepted server-only row: put the file "
        "back, or account for the row in SERVER_ONLY_ROWS and say why"
    )


def test_every_seed_owner_has_a_department():
    """The whole reason this script exists: an owner without one cannot own a dataset."""
    manifest = _workspace_manifest()

    assert manifest["owners"], "a workspace with no data owner cannot register a dataset"
    for owner in manifest["owners"]:
        assert owner.get("department"), (
            f"owner {owner.get('username')!r} has no department, so upload-excel would "
            "answer 403 department_scope_required"
        )
        assert owner.get("password_env"), f"owner {owner.get('username')!r} names no password_env"
        assert not owner.get("password"), "a seed manifest must never carry a password value"


def test_every_manifest_dataset_sits_on_disk():
    manifest = _workspace_manifest()

    assert manifest["datasets"], "no dataset means the data questions have nothing to read"
    for spec in manifest["datasets"]:
        path = ROOT / str(spec["path"])
        assert path.is_file(), f"dataset {spec['path']!r} is named by the manifest but absent"
        assert spec.get("owner"), f"dataset {spec['path']!r} names no owner"
