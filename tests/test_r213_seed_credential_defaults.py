"""R213: the credential defaults of scripts/seed_workspace.py must be real, paired and taught.

What this pays for: --password-env defaulted to a key that exists in no env file, no example
file and no document -- it appeared exactly once in the repository, inside that default. The
module docstring meanwhile taught the data owner key, which unlocks a different account than
the one the script logs in as. Two entry points, two accounts, and a 401 that got attributed
to a password nobody owed.

Every request here goes through the recorder in `server`. A credential pin that talks to the
live backend cannot tell "the default is wrong" apart from "the server is busy", and it must
never be the thing that uploads a corpus.
"""
import ast
import importlib.util
import json
import re
import types
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "scripts" / "seed_workspace.py"
PARITY_PATH = ROOT / "scripts" / "check_corpus_parity.py"
MANIFEST_PATH = ROOT / "deploy" / "workspace-seed.json"

_spec = importlib.util.spec_from_file_location("seed_workspace", SEED_PATH)
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)

#: Written by these tests into a tmp file. It is not, and must never become, a live password.
SENTINEL = "sentinel-not-a-real-password"

#: The one owner the deployment manifest names. Read, never copied, so the account pairing is
#: checked against the paper rather than against a second list typed in here.
OWNER_SPEC = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["owners"][0]

BASE_URL = "http://testserver"


def _defaults():
    parser = seed._build_parser()
    return {dest: parser.get_default(dest)
            for dest in ("username", "password_env", "token_env", "env_file")}


def _args(argv):
    return seed._build_parser().parse_args(argv)


def _source_default(script: Path, option: str):
    """Read an argparse default out of a sibling script that builds its parser inside main()."""
    for node in ast.walk(ast.parse(script.read_text(encoding="utf-8"))):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
                and node.args and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == option):
            for keyword in node.keywords:
                if keyword.arg == "default":
                    return ast.literal_eval(keyword.value)
    raise AssertionError(f"{script.name} declares no {option} default to compare against")


def _declared_credential_keys():
    """Credential keys the repository declares somewhere other than the default under test.

    deploy/.env.server is deliberately absent: it is gitignored and carries live passwords,
    so a test that read it could leak one into a failure message. The sibling script, the
    seed manifest, the example env file and the deploy README are the honest census.
    """
    keys = {str(OWNER_SPEC["password_env"])}
    for option in ("--password-env", "--token-env", "--username"):
        keys.add(str(_source_default(PARITY_PATH, option)))
    example = ROOT / "deploy" / ".env.server.example"
    if example.is_file():
        keys.update(seed._env_file_values(example))
    readme = ROOT / "deploy" / "README.server.md"
    if readme.is_file():
        keys.update(re.findall(r"\b[A-Z][A-Z0-9_]*\b", readme.read_text(encoding="utf-8")))
    return keys


def _docstring_bullets():
    """The credential bullets of the module docstring, keyed by the name they teach."""
    bullets = {}
    for chunk in re.split(r"\n(?=\* ``)", seed.__doc__ or ""):
        match = re.match(r"\* ``([A-Z][A-Z0-9_]*)``(.*)", chunk, re.S)
        if match:
            bullets[match.group(1)] = match.group(2)
    return bullets


class _Response:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class _Server:
    def __init__(self):
        self.routes = {}
        self.calls = []

    def answer(self, method, url):
        path = urlsplit(url).path
        self.calls.append((method, path))
        return self.routes.get((method, path)) or _Response(
            404, text=f"unrouted {method} {path}")

    @property
    def methods(self):
        return [method for method, _ in self.calls]

    @property
    def posts(self):
        return [path for method, path in self.calls if method != "GET"]

    @property
    def writes(self):
        """Everything that could change the deployment: a POST that is not the login."""
        return [path for path in self.posts if path != "/api/v1/login"]


class _Session:
    def __init__(self, server):
        self.headers = {}
        self._server = server

    def get(self, url, **kwargs):
        return self._server.answer("GET", url)

    def post(self, url, **kwargs):
        return self._server.answer("POST", url)


@pytest.fixture(autouse=True)
def server(monkeypatch):
    """Autouse so that no test in this file can reach a socket by forgetting a fixture."""
    fake = _Server()
    monkeypatch.setattr(seed, "requests", types.SimpleNamespace(Session=lambda: _Session(fake)))
    return fake


@pytest.fixture(autouse=True)
def _no_ambient_credentials(monkeypatch):
    """A developer shell that already exports these keys must not decide what passes."""
    defaults = _defaults()
    for key in (defaults["password_env"], defaults["token_env"], OWNER_SPEC["password_env"]):
        monkeypatch.delenv(str(key), raising=False)


@pytest.fixture
def workspace(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "kept.txt").write_text("kept", encoding="utf-8")
    (corpus / "fresh.txt").write_text("fresh", encoding="utf-8")
    dataset = tmp_path / "expense.csv"
    dataset.write_text("a,b\n1,2\n", encoding="utf-8")
    manifest = tmp_path / "seed.json"
    manifest.write_text(json.dumps({
        "corpus_directory": str(corpus),
        "documents": {"classification": 1, "files": ["kept.txt", "fresh.txt"]},
        "owners": [dict(OWNER_SPEC)],
        "datasets": [{"path": str(dataset), "owner": OWNER_SPEC["username"]}],
    }), encoding="utf-8")
    return manifest


def _ready_routes():
    return {
        ("POST", "/api/v1/login"): _Response(200, {"token": "a-token"}),
        ("GET", "/api/v1/documents"): _Response(200, {"documents": ["kept.txt", "fresh.txt"]}),
        ("GET", "/api/v1/data-files"): _Response(200, {"files": [{"filename": "expense.csv"}]}),
        ("GET", "/api/v1/users"): _Response(200, {"users": [{
            "username": OWNER_SPEC["username"], "department": OWNER_SPEC["department"]}]}),
    }


def _empty_routes():
    return {
        ("POST", "/api/v1/login"): _Response(200, {"token": "a-token"}),
        ("GET", "/api/v1/documents"): _Response(200, {"documents": []}),
        ("GET", "/api/v1/data-files"): _Response(200, {"files": []}),
        ("GET", "/api/v1/users"): _Response(200, {"users": []}),
    }


# --- judgement 1: a default call is enough, and the default is not a hole ------------------

def test_the_admin_password_default_is_a_key_the_repository_declares():
    default = str(_defaults()["password_env"])
    assert default in _declared_credential_keys(), (
        f"--password-env defaults to {default!r}, which nothing outside its own default "
        "names: nobody can set it, so every default run dies on the credential"
    )


@pytest.mark.parametrize("dest", ["password_env", "token_env"])
def test_no_credential_default_is_written_only_once_in_the_repository(dest):
    value = str(_defaults()[dest])
    assert value in _declared_credential_keys(), f"--{dest.replace('_', '-')} defaults to {value!r} alone"


def test_the_two_seed_scripts_agree_on_the_administrator_credential():
    defaults = _defaults()
    assert defaults["password_env"] == _source_default(PARITY_PATH, "--password-env")
    assert defaults["token_env"] == _source_default(PARITY_PATH, "--token-env")
    assert defaults["env_file"] == _source_default(PARITY_PATH, "--env-file")


def test_the_default_username_and_the_default_key_name_one_account():
    defaults = _defaults()
    assert str(defaults["username"]).strip(), "a default run has to have an account to log in as"
    assert defaults["username"] == _source_default(PARITY_PATH, "--username")
    assert defaults["username"] != OWNER_SPEC["username"], (
        "the administrator default and the data owner account have been merged into one "
        "name again, which is precisely how a working deployment read as a broken password"
    )
    assert defaults["password_env"] != str(OWNER_SPEC["password_env"]), (
        "one key cannot be the password of two different accounts")


# --- judgement 3: the docstring and the code read from one source --------------------------

def test_the_docstring_teaches_exactly_the_credential_keys_the_code_reads():
    defaults = _defaults()
    taught = _docstring_bullets()
    live = {defaults["password_env"], defaults["token_env"], str(OWNER_SPEC["password_env"])}
    assert set(taught) == live, (
        "the credential keys taught in the module docstring and the keys this script actually "
        f"reads have drifted apart: docstring={sorted(taught)} code={sorted(live)}"
    )


def test_the_docstring_ties_each_credential_key_to_its_account():
    defaults = _defaults()
    bullets = _docstring_bullets()
    admin = bullets[str(defaults["password_env"])]
    assert str(defaults["username"]) in admin, (
        "the administrator key has to name the account it unlocks")
    assert "--env-file" in admin and str(defaults["env_file"]) in admin, (
        "the fallback file must be taught beside the key it can supply")
    owner = bullets[str(OWNER_SPEC["password_env"])]
    assert str(OWNER_SPEC["username"]) in owner, (
        "the owner key must be taught as belonging to the owner account, by name")
    assert "administrator" in owner, (
        "the owner key bullet has to say it is not the administrator's credential")
    assert "users:manage" in owner, (
        "the docstring must say why a data owner cannot run --check, or the next reader "
        "will read a 403 as a wrong password")


# --- judgement 2: explicit argument first, env file as fallback, named failure -------------

def test_the_password_is_read_from_the_env_file_when_the_environment_is_silent(tmp_path):
    key = str(_defaults()["password_env"])
    env_file = tmp_path / "custom.env"
    env_file.write_text(f"# a comment\n{key}={SENTINEL}\nOTHER=1\n", encoding="utf-8")
    password, source = seed._admin_password(_args(["--env-file", str(env_file)]), tmp_path)
    assert password == SENTINEL
    assert key in source and str(env_file) in source


def test_the_default_env_file_is_resolved_against_the_repository_root(tmp_path):
    key = str(_defaults()["password_env"])
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / ".env.server").write_text(f"{key}={SENTINEL}\n", encoding="utf-8")
    password, source = seed._admin_password(_args([]), tmp_path)
    assert password == SENTINEL, "a bare default call finds deploy/.env.server unaided"
    assert str(tmp_path / "deploy" / ".env.server") in source


def test_the_process_environment_beats_the_env_file(tmp_path, monkeypatch):
    key = str(_defaults()["password_env"])
    env_file = tmp_path / ".env.server"
    env_file.write_text(f"{key}=from-the-file\n", encoding="utf-8")
    monkeypatch.setenv(key, "from-the-process")
    password, source = seed._admin_password(_args(["--env-file", str(env_file)]), tmp_path)
    assert password == "from-the-process"
    assert "process environment" in source


def test_an_explicit_password_env_is_honoured_in_the_fallback_file_too(tmp_path):
    env_file = tmp_path / ".env.server"
    env_file.write_text("MY_NAMED_KEY=from-the-named-key\n", encoding="utf-8")
    password, source = seed._admin_password(
        _args(["--password-env", "MY_NAMED_KEY", "--env-file", str(env_file)]), tmp_path)
    assert password == "from-the-named-key"
    assert "MY_NAMED_KEY" in source


def test_a_missing_credential_names_the_key_and_file_instead_of_blaming_the_password(tmp_path):
    defaults = _defaults()
    with pytest.raises(seed.SeedError) as raised:
        seed._admin_password(_args([]), tmp_path)
    message = str(raised.value)
    assert str(defaults["password_env"]) in message, "the error must name the key to set"
    assert str(tmp_path / "deploy" / ".env.server") in message, "and the file it tried"
    assert "--env-file" in message
    assert str(defaults["username"]) in message, "and the account the credential is for"
    assert "missing credential" in message
    assert "login" not in message.lower(), "a missing key must never read as a failed login"


def test_an_emptied_password_env_is_reported_by_name(tmp_path):
    with pytest.raises(seed.SeedError) as raised:
        seed._admin_password(_args(["--password-env", ""]), tmp_path)
    assert "--password-env" in str(raised.value)


def test_an_empty_username_fails_before_a_password_is_sought(tmp_path):
    with pytest.raises(seed.SeedError) as raised:
        seed._admin_token(BASE_URL, _args(["--username", ""]), tmp_path)
    assert "--username" in str(raised.value)


def test_setting_only_the_owner_key_fails_closed_without_a_request(workspace, server, tmp_path,
                                                                   monkeypatch, capsys):
    """The R213 trap, replayed: the owner key is set, the administrator key is not."""
    monkeypatch.setenv(str(OWNER_SPEC["password_env"]), SENTINEL)
    server.routes.update(_ready_routes())
    exit_code = seed.main([
        "--check", "--base-url", BASE_URL, "--manifest", str(workspace),
        "--env-file", str(tmp_path / "nothing.env")])

    assert exit_code == 2
    assert server.calls == [], "an unresolved credential must not even reach the login"
    err = capsys.readouterr().err
    assert str(_defaults()["password_env"]) in err
    assert "owners[].password_env" in err, "and it has to say the owner key is not the one"


# --- judgement 4: --check stays read-only, and a permission 403 says permission ------------

def test_check_reads_the_workspace_back_without_a_single_post(workspace, server, tmp_path,
                                                             capsys):
    token_file = tmp_path / "token.txt"
    token_file.write_text("a-token\n", encoding="utf-8")
    server.routes.update(_ready_routes())
    exit_code = seed.main(["--check", "--base-url", BASE_URL, "--manifest", str(workspace),
                           "--token-file", str(token_file)])

    assert exit_code == 0
    assert set(server.methods) == {"GET"}, "a token-authenticated --check posts nothing at all"
    assert "RESULT ok  documents=2 datasets=1 owners=1" in capsys.readouterr().out


def test_check_touches_no_write_endpoint_even_on_an_empty_workspace(workspace, server,
                                                                   monkeypatch, capsys):
    monkeypatch.setenv(str(_defaults()["password_env"]), SENTINEL)
    server.routes.update(_empty_routes())
    exit_code = seed.main(["--check", "--base-url", BASE_URL, "--manifest", str(workspace)])

    assert exit_code == 1, "an empty workspace is reported, not quietly seeded"
    assert server.writes == [], "--check may upload nothing and may create no account"
    assert server.posts == ["/api/v1/login"], "the only POST a --check run makes is the login"
    out = capsys.readouterr().out
    assert "to create" in out and "to upload" in out, "the plan is still reported out loud"


def test_a_data_owner_is_told_it_is_a_permission_problem_not_a_password(workspace, server,
                                                                       tmp_path, capsys):
    token_file = tmp_path / "token.txt"
    token_file.write_text("a-token\n", encoding="utf-8")
    server.routes.update(_ready_routes())
    server.routes[("GET", "/api/v1/users")] = _Response(403, {"detail": "permission_denied"})
    exit_code = seed.main(["--check", "--base-url", BASE_URL, "--manifest", str(workspace),
                           "--token-file", str(token_file)])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "permission" in err and "users:manage" in err
    assert "not a wrong password" in err, "a 403 must not read as a bad password"
    assert str(OWNER_SPEC["username"]) in err and str(_defaults()["username"]) in err, (
        "the message has to name which account can do this")


def test_a_bad_password_still_reports_a_login_failure_naming_the_key_it_used(workspace, server,
                                                                            monkeypatch, capsys):
    key = str(_defaults()["password_env"])
    monkeypatch.setenv(key, SENTINEL)
    server.routes.update(_ready_routes())
    server.routes[("POST", "/api/v1/login")] = _Response(401, {"detail": "invalid_credentials"})
    exit_code = seed.main(["--check", "--base-url", BASE_URL, "--manifest", str(workspace)])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "login" in err.lower(), "401 stays a login failure, so the two codes stay apart"
    assert key in err and "process environment" in err, "and it says where the password came from"
