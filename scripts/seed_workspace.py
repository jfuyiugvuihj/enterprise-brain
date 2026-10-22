"""Bring a fresh backend up to a measurable workspace, through its public API only.

A clean install hands you one administrator with no department, and
app/storage/datasets.py:136 refuses to let an owner without a department register a
dataset: POST /api/v1/upload-excel answers 403 department_scope_required. So the corpus
and the expense dataset behind the data questions used to be loaded by hand, one untracked
requests call at a time -- which is exactly how a run ended up scoring an empty knowledge
base. The whole bring-up lives in deploy/workspace-seed.json instead. This script is
idempotent, so it is safe after an image rebuild, a volume restore or a customer install,
and --check says out loud whether the workspace is ready for a measurement window.

Do not reach for docker cp to skip the permission layer: a dataset that exists only
because a shell wrote it into a volume is a pass that cannot be reproduced on a customer
machine.

Usage (on the host, against the published container port)::

    python scripts/seed_workspace.py --check

Three credential keys, three different accounts -- do not swap them:

* ``DEMO_ADMIN_PASSWORD`` is the password of the administrator that ``--username``
  names (default ``admin``), and it is the only key a default run reads. The process
  environment wins, then ``--env-file`` (default ``deploy/.env.server``), so the
  command above does not need a key name typed on the command line.
* ``EB_SEED_ADMIN_TOKEN`` is an already-issued administrator bearer token;
  ``--token-file`` reads that same token out of a file and skips the login.
* ``EB_SEED_OWNER_PASSWORD`` is the password of the *data owner* account
  ``dataowner``, which is who deploy/workspace-seed.json lists under ``owners``.
  That is a different person from the administrator: a seed run logs in as the
  administrator, creates ``dataowner``, then uploads the expense dataset as
  ``dataowner``. Setting this key alone cannot log you in as the administrator, and
  ``dataowner`` cannot run ``--check`` either, because that leg lists ``/users``
  and the staff role it holds does not carry ``users:manage``.

A credential that cannot be found is named out loud, never reported as a login failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

DEFAULT_MANIFEST = Path("deploy") / "workspace-seed.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8001"
#: Fallback source for the administrator password, the same file the parity check reads.
DEFAULT_ENV_FILE = "deploy/.env.server"
#: A knowledge-base document is embedded on the way in, so one upload is a model call.
UPLOAD_TIMEOUT_SECONDS = 600.0
API_PREFIX = "/api/v1"


class SeedError(RuntimeError):
    """The workspace cannot be brought up, and guessing is not an acceptable fallback."""


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_manifest(path: Path) -> dict:
    if not path.is_file():
        raise SeedError(f"seed manifest not found: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for section in ("owners", "documents", "datasets"):
        if section not in manifest:
            raise SeedError(f"seed manifest {path} is missing its {section!r} section")
    return manifest


def _session(base_url: str, token: str) -> requests.Session:
    session = requests.Session()
    session.trust_env = False  # a system proxy otherwise captures localhost
    session.headers["Authorization"] = f"Bearer {token}"
    return session


def _env_file_values(path: Path) -> dict[str, str]:
    """Read the KEY=VALUE lines of a dotenv file; a missing file is not an error."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def _login(base_url: str, username: str, password: str, credential_note: str = "") -> str:
    session = requests.Session()
    session.trust_env = False
    response = session.post(
        f"{base_url}{API_PREFIX}/login",
        json={"username": username, "password": password},
        timeout=30.0,
    )
    if response.status_code != 200:
        raise SeedError(
            f"login as {username!r} failed: HTTP {response.status_code} {response.text[:200]}"
            + (f"; the credential was read as {credential_note}" if credential_note else "")
        )
    token = str(response.json().get("token") or "")
    if not token:
        raise SeedError(f"the login response for {username!r} carried no token key")
    return token


def _admin_token(base_url: str, args: argparse.Namespace, root: Path) -> str:
    if args.token_file:
        path = Path(args.token_file)
        if not path.is_file():
            raise SeedError(f"--token-file points at nothing: {path}")
        return path.read_text(encoding="utf-8").strip()
    token = os.getenv(args.token_env or "", "").strip()
    if token:
        return token
    username = str(args.username or "").strip()
    if not username:
        raise SeedError(
            "no administrator to log in as: --username is empty, so pass --username, or "
            f"an already-issued token via --token-file or {args.token_env}"
        )
    password, source = _admin_password(args, root)
    return _login(base_url, username, password, credential_note=source)


def _admin_password(args: argparse.Namespace, root: Path) -> tuple[str, str]:
    """The administrator password, plus a note on where it came from.

    The precedence is the one scripts/check_corpus_parity.py uses: a process environment
    value wins, --env-file is the fallback, and a key found in neither is named out loud
    together with the file that was tried. The account this resolves for is the
    administrator, not the data owner whose password the seed manifest names under
    owners[].password_env -- conflating the two is what made a working deployment look
    like it owed someone a password.
    """
    key = str(args.password_env or "").strip()
    if not key:
        raise SeedError(
            "--password-env is empty, so there is no key an administrator password could "
            f"be read from: pass --password-env, --token-file or {args.token_env}"
        )
    password = os.getenv(key, "")
    if password:
        return password, f"{key} from the process environment"
    env_file = Path(str(args.env_file or "").strip() or DEFAULT_ENV_FILE)
    if not env_file.is_absolute():
        env_file = root / env_file
    password = _env_file_values(env_file).get(key, "")
    if password:
        return password, f"{key} from {env_file}"
    raise SeedError(
        f"no administrator password: {key} is set neither in the process environment nor "
        f"in {env_file}, the file named by --env-file. Set {key} for the account "
        f"--username {args.username!r} names, or pass --token-file/--token-env. This is a "
        "missing credential, not a wrong password: nothing was sent to the server. The "
        "owners[].password_env key in the seed manifest belongs to the data owner account, "
        "which is not the account being logged in here."
    )


def _remote_document_names(session: requests.Session, base_url: str) -> set[str]:
    response = session.get(f"{base_url}{API_PREFIX}/documents", timeout=120.0)
    if response.status_code != 200:
        raise SeedError(f"GET /documents: HTTP {response.status_code} {response.text[:200]}")
    return {str(name) for name in (response.json().get("documents") or [])}


def _remote_dataset_names(session: requests.Session, base_url: str) -> set[str]:
    response = session.get(f"{base_url}{API_PREFIX}/data-files", timeout=120.0)
    if response.status_code != 200:
        raise SeedError(f"GET /data-files: HTTP {response.status_code} {response.text[:200]}")
    return {str(row.get("filename") or "") for row in (response.json().get("files") or [])}


def plan_documents(manifest: dict, corpus_dir: Path, remote: set[str]):
    """Sort the manifest into (uploadable, unmeetable, already in, server-only).

    A name that is neither on disk nor on the server is an error, never quietly
    dropped: the last time a document was missing, a reconcile-by-deletion read that
    as licence to remove real corpus rows. A name that is on the server but not on disk
    is counted towards the target and warned about, because that row cannot be brought
    back by this script if the volume ever goes away.
    """
    wanted: list[Path] = []
    absent: list[str] = []
    already: list[str] = []
    server_only: list[str] = []
    for name in manifest["documents"]["files"]:
        path = corpus_dir / str(name)
        on_disk = path.is_file()
        indexed = str(name) in remote
        if not on_disk and not indexed:
            absent.append(str(name))
        elif not on_disk:
            server_only.append(str(name))
        elif indexed:
            already.append(str(name))
        else:
            wanted.append(path)
    return wanted, absent, already, server_only


def ensure_owners(session: requests.Session, base_url: str, owners: list[dict], check: bool) -> dict[str, str]:
    """Create the data owners named by the manifest, and return their passwords.

    A department is not optional here: an owner without one is precisely the account
    that cannot own a dataset. An existing account whose department differs is reported
    and left alone, because moving someone's scope is not a seed job.
    """
    response = session.get(f"{base_url}{API_PREFIX}/users", timeout=30.0)
    if response.status_code == 403:
        raise SeedError(
            "GET /users answered 403, which is a permission problem and not a wrong "
            "password: listing users needs the users:manage permission, and the staff "
            "role does not have it. dataowner is staff, so run this script as the "
            "administrator (--username admin, the default), not as a data owner."
        )
    if response.status_code != 200:
        raise SeedError(f"GET /users: HTTP {response.status_code} {response.text[:200]}")
    existing = {str(row.get("username")): row for row in (response.json().get("users") or [])}

    credentials: dict[str, str] = {}
    for spec in owners:
        username = str(spec["username"])
        department = str(spec.get("department") or "")
        if not department:
            raise SeedError(f"owner {username!r} has no department in the manifest")
        password_env = str(spec.get("password_env") or "EB_SEED_OWNER_PASSWORD")
        password = os.getenv(password_env, "")
        current = existing.get(username)
        if current is not None:
            current_department = str(current.get("department") or "")
            if current_department and current_department != department:
                print(
                    f"WARN owner {username!r} is in department {current_department!r}, "
                    f"the manifest says {department!r}; left alone"
                )
            print(f"owner  {username:<14} present   department={current_department or department}")
            if password:
                credentials[username] = password
            continue
        if check:
            print(f"owner  {username:<14} to create  department={department}")
            continue
        if not password:
            raise SeedError(
                "owner " + repr(username) + " does not exist and " + password_env
                + " is unset, so no password can be chosen on your behalf"
            )
        response = session.post(
            f"{base_url}{API_PREFIX}/users",
            json={
                "username": username,
                "password": password,
                "role": str(spec.get("role") or "staff"),
                "department": department,
            },
            timeout=30.0,
        )
        if response.status_code != 200:
            raise SeedError(
                f"POST /users for {username!r}: HTTP {response.status_code} {response.text[:200]}"
            )
        print(f"owner  {username:<14} created    department={department}")
        credentials[username] = password
    return credentials


def _content_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return {
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
    }.get(suffix, "application/octet-stream")


def seed_datasets(base_url, manifest, remote, credentials, root, check) -> list[str]:
    """Register each dataset under the owner the manifest names for it."""
    for spec in manifest["datasets"]:
        relative = Path(str(spec["path"]))
        filename = relative.name
        owner = str(spec.get("owner") or "")
        path = root / relative
        if filename in remote:
            print(f"dataset {filename:<26} present   owner={owner}")
            continue
        if not path.is_file():
            raise SeedError(f"dataset {filename!r} is in the manifest but not on disk: {path}")
        if check:
            print(f"dataset {filename:<26} to upload  owner={owner}")
            continue
        password = credentials.get(owner) or os.getenv(
            str(spec.get("password_env") or "EB_SEED_OWNER_PASSWORD"), "")
        if not password:
            raise SeedError(
                f"dataset {filename!r} must be uploaded by {owner!r}, whose password is "
                "unknown: set the password_env named in the manifest"
            )
        owner_session = _session(base_url, _login(base_url, owner, password))
        response = owner_session.post(
            f"{base_url}{API_PREFIX}/upload-excel",
            files={"file": (filename, path.read_bytes(), _content_type(filename))},
            timeout=UPLOAD_TIMEOUT_SECONDS,
        )
        if response.status_code == 409:
            print(f"dataset {filename:<26} present   owner={owner}")
            continue
        if response.status_code != 200:
            raise SeedError(
                f"POST /upload-excel for {filename!r}: HTTP {response.status_code} {response.text[:300]}"
            )
        print(f"dataset {filename:<26} uploaded  owner={owner}")
    return []


def seed_documents(session, base_url, wanted, classification, check) -> None:
    for path in wanted:
        if check:
            print(f"doc     {path.name:<40} to upload")
            continue
        with path.open("rb") as handle:
            response = session.post(
                f"{base_url}{API_PREFIX}/upload",
                files={"file": (path.name, handle)},
                data={"classification": str(classification)},
                timeout=UPLOAD_TIMEOUT_SECONDS,
            )
        if response.status_code != 200:
            raise SeedError(
                f"POST /upload for {path.name!r}: HTTP {response.status_code} {response.text[:300]}"
            )
        print(f"doc     {path.name:<40} uploaded")


def _build_parser() -> argparse.ArgumentParser:
    """The whole credential surface of this script, in one place the tests can read.

    Every default here has to be a key that exists somewhere outside this file, and the
    module docstring has to teach it: a default nobody can set is how a run ended up
    blaming the owner for a typo.
    """
    parser = argparse.ArgumentParser(description="Seed the reference corpus and datasets of one deployment.")
    parser.add_argument("--base-url", default=os.getenv("EVAL_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--token-file", default=None, help="read the administrator bearer token from this file")
    parser.add_argument("--token-env", default="EB_SEED_ADMIN_TOKEN",
                        help="environment variable holding an administrator bearer token")
    parser.add_argument("--username", default="admin",
                        help="administrator account to log in as; a staff account such as dataowner "
                             "cannot list /users, so --check needs this one")
    parser.add_argument("--password-env", default="DEMO_ADMIN_PASSWORD",
                        help="environment variable holding the password of --username")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE,
                        help="fallback file to read the --password-env key from")
    parser.add_argument("--check", action="store_true",
                        help="report what is missing and upload nothing; it lists /users, so run it "
                             "as the administrator rather than as dataowner, whose staff role lacks "
                             "users:manage")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    root = _repository_root()
    base_url = args.base_url.rstrip("/")
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path

    try:
        manifest = load_manifest(manifest_path)
        corpus_dir = root / str(manifest.get("corpus_directory") or "documents")
        wanted_names = [str(name) for name in manifest["documents"]["files"]]
        dataset_names = [Path(str(spec["path"])).name for spec in manifest["datasets"]]

        session = _session(base_url, _admin_token(base_url, args, root))
        remote_documents = _remote_document_names(session, base_url)
        remote_datasets = _remote_dataset_names(session, base_url)
        wanted, absent, already, server_only = plan_documents(manifest, corpus_dir, remote_documents)
        print(f"manifest {manifest_path.name}: documents={len(wanted_names)} datasets={len(dataset_names)}")
        print(f"server   {base_url}: {len(remote_documents)} indexed documents, {len(remote_datasets)} datasets")
        print(f"plan     {len(already)} already in, {len(wanted)} to upload")
        if server_only:
            print("WARN    on the server but not on disk, this script cannot rebuild them: "
                  + ", ".join(server_only))
        if absent:
            raise SeedError("named by the manifest but found neither on disk nor on the server: "
                            + ", ".join(absent))

        credentials = ensure_owners(session, base_url, manifest["owners"], args.check)
        seed_datasets(base_url, manifest, remote_datasets, credentials, root, args.check)
        seed_documents(session, base_url, wanted, int(manifest["documents"].get("classification", 1)), args.check)

        if args.check:
            missing_documents = sorted(path.name for path in wanted)
            missing_datasets = sorted(set(dataset_names) - remote_datasets)
        else:
            missing_documents = sorted(set(wanted_names) - _remote_document_names(session, base_url))
            missing_datasets = sorted(set(dataset_names) - _remote_dataset_names(session, base_url))
        if missing_documents or missing_datasets:
            print("RESULT incomplete  documents=[" + ", ".join(missing_documents) + "]"
                  "  datasets=[" + ", ".join(missing_datasets) + "]")
            return 1
        print(f"RESULT ok  documents={len(wanted_names)} datasets={len(dataset_names)} "
              f"owners={len(manifest['owners'])}")
        return 0
    except SeedError as exc:
        print(f"SEED FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
