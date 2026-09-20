"""R120 (= D9 放行件): 干净环境首装必须能自己走完 migrate，补救指引必须指向真存在的库与文件。

判据出处：docs/handoff/2026-09-15-backend-followup-requests.md SS33.2 / SS34.3（R90 / R90b）、
SS22（R58）、docs/handoff/2026-09-17-human-gates.md 的 D9 与 D4。

本文件一条真库都不连，也不建库：宿主 5432 被 tests/conftest.py:41 那颗钉子钉死，Docker 那台
pgvector/pgvector:pg16 又没发布宿主端口（同一处注释已实测写明），所以"首装停在哪一句"只能靠
静态推演 + 假连接坐实。SS33.2 判据 ① 要的是"零人工前置"，本文件把它写成可执行的形状：
把交付时真正给操作者的那份示例 env 喂进 apply_migrations，看它能不能一路走到 0010 记账。

任务 0 的两条测量也在本文件里（A1/A2/A3）：原地改一枚已应用过的迁移会撞 schema_migrations 的
checksum 账本，撞在哪一层、报错原文是什么，都由用例说，不靠嘴。R90b 因此走"禁止改 0010"这条，
0010 在本单之后仍与基线 6a70f73 逐字节相同（A3 钉住）。
"""
from __future__ import annotations

from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
import re

import pytest
import yaml

from app.db import migrations as mig
from app.rag import indexing


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
DEPLOY_SAMPLE = ROOT / "deploy" / ".env.server.example"
MIGRATIONS_DIR = ROOT / "migrations"

#: 0010 as shipped at baseline 6a70f73. Editing the file means editing this line too, and the
#: point of writing the number down is that a text-only "harmless" edit is exactly what A1
#: measures: every database that already recorded this digest then refuses to migrate.
BASELINE_0010_SHA256 = "abc4f16d25fec72e174305c95589c1cb9475245856be0ab0035082279176d6d3"

#: The database name the Compose stack creates by default: services.postgres.environment
#: .POSTGRES_DB in docker-compose.yml. A14 checks it is still that, instead of trusting this.
COMPOSE_DEFAULT_DATABASE = "enterprise_brain"


def _env_documented(path: Path) -> dict[str, str]:
    """Parse an env file the way the app's readers do: last assignment wins, ``#`` is a comment."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        values[name.strip()] = value.strip()
    return values


def _compose() -> dict:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8-sig"))
    assert isinstance(document, dict), "docker-compose.yml must stay a mapping"
    return document


def _interpolate(value: str, environment: dict[str, str]) -> str:
    """Compose's own substitution for the only two spellings this stack uses.

    ``${VAR}`` becomes empty when VAR is unset and ``${VAR:-default}`` becomes the default;
    nothing else in the three files this ticket touches needs more, and inventing a richer
    simulator here would let a wrong default hide.
    """
    def one(match: re.Match) -> str:
        name, fallback = match.group(1), match.group(2)
        present = environment.get(name)
        if present:
            return present
        return fallback if fallback is not None else ""

    return re.sub(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}", one, value)


# ------------------------------------------------------------------ a PostgreSQL that behaves
#
# The shape is the one tests/test_r90a_embedding_guc_provisioning.py established: two layers of
# settings (database-level defaults apply to a *later* session, set_config(..., TRUE) applies to
# this transaction), format() quoting done by the server, and a ledger. What this file adds is a
# catalog that is not a stub: an empty migration is recorded as "applied", so asserting that 0010
# was applied means the runner got all the way to it.


class FreshSession:
    """A live-enough PostgreSQL session for one migration run, including the ledger."""

    def __init__(
        self,
        *,
        database: str,
        ledger: dict[str, str],
        database_settings=None,
        catalog=None,
    ) -> None:
        self.database = database
        self.database_settings = dict(database_settings or {})
        self.transaction_settings: dict[str, str] = {}
        self.ledger = dict(ledger)
        #: Which SQL bodies count as "a migration was applied". A test that hands the runner an
        #: edited catalog has to say so, or its own file text would match nothing here.
        self.catalog = tuple(mig.MIGRATIONS if catalog is None else catalog)
        self.statements: list[tuple[str, object]] = []
        self.applied: list[str] = []

    def transaction(self):
        return nullcontext()

    def _setting(self, name: str) -> str:
        return self.transaction_settings.get(name) or self.database_settings.get(name) or ""

    def execute(self, sql: str, params=None):
        self.statements.append((sql, params))
        if "AS database_name" in sql:
            return _Result([(
                self.database,
                self._setting(mig.EMBEDDING_DIMENSION_GUC),
                self._setting(mig.EMBEDDING_MODEL_GUC),
            )])
        if "AS statement" in sql:
            template, value = params  # type: ignore[misc]
            quoted = '"' + self.database.replace('"', '""') + '"'
            rendered = template.replace("%I", quoted).replace("%L", "'" + value + "'")
            return _Result([(rendered,)])
        if sql.startswith("ALTER DATABASE "):
            match = re.match(r'ALTER DATABASE "(.+)" SET (\S+) = \'(.*)\'', sql)
            assert match, f"not a well-formed declaration: {sql!r}"
            assert match.group(1) == self.database, sql
            self.database_settings[match.group(2)] = match.group(3)
            return _Result([])
        if "set_config" in sql:
            dimension_setting, dimension_value, model_setting, model_value = params  # type: ignore[misc]
            self.transaction_settings[dimension_setting] = dimension_value
            self.transaction_settings[model_setting] = model_value
            return _Result([(dimension_value, model_value)])
        if "FROM schema_migrations" in sql:
            return _Result(sorted(self.ledger.items()))
        if "INSERT INTO schema_migrations" in sql:
            version, name, checksum = params  # type: ignore[misc]
            self.ledger[version] = checksum
            return _Result([])
        migration = next((item for item in self.catalog if sql == item.sql), None)
        if migration is not None:
            self.applied.append(migration.version)
        return _Result([])

    @property
    def executed_sql(self) -> list[str]:
        return [sql for sql, _ in self.statements]


class _Result:
    def __init__(self, rows) -> None:
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)


def _clean_database(catalog=None) -> FreshSession:
    """A fresh install that has reached pgvector: 0001..0009 recorded, 0010 pending."""
    return FreshSession(
        database=COMPOSE_DEFAULT_DATABASE,
        ledger={item.version: item.checksum for item in mig.MIGRATIONS if item.version != "0010"},
        catalog=catalog,
    )


def _migrated_database() -> FreshSession:
    """A database that already applied 0010 and recorded its digest: the installed customer."""
    return FreshSession(
        database=COMPOSE_DEFAULT_DATABASE,
        ledger={item.version: item.checksum for item in mig.MIGRATIONS},
    )


@pytest.fixture(autouse=True)
def _declared_pair(monkeypatch):
    """默认站在"操作者照示例文件把成对的两个变量写上了"的那一侧。

    故意不用出厂的 768/bge 之外的数：值取自 deploy/.env.server.example 本身，所以这条夹具同时
    是判据 ① 的一部分 —— 示例文件写错数，这里立刻红。要测"没声明"的那几条用例自己 delenv。
    """
    # Tolerant on purpose: a sample that does not carry the pair has to make the tests that
    # depend on it fail on their own merits, not error this whole file at fixture setup.
    documented = _env_documented(DEPLOY_SAMPLE)
    for name in (indexing.EMBEDDING_MODEL_ENV, indexing.EMBEDDING_DIMENSION_ENV):
        if documented.get(name):
            monkeypatch.setenv(name, documented[name])


def _declared_from_the_sample() -> dict[str, str]:
    """The two variables exactly as the shipped deployment sample writes them."""
    documented = _env_documented(DEPLOY_SAMPLE)
    return {
        indexing.EMBEDDING_MODEL_ENV: documented[indexing.EMBEDDING_MODEL_ENV],
        indexing.EMBEDDING_DIMENSION_ENV: documented[indexing.EMBEDDING_DIMENSION_ENV],
    }


def _copy_catalog(destination: Path) -> Path:
    target = destination / "migrations"
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(MIGRATIONS_DIR.glob("*")):
        (target / path.name).write_bytes(path.read_bytes())
    return target


def _re_register(catalog: Path, filename: str) -> str:
    """Do the part an honest editor always does: put the new digest into the manifest."""
    manifest_path = catalog / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sql = (catalog / filename).read_text(encoding="utf-8")
    digest = sha256(sql.encode("utf-8")).hexdigest()
    manifest[filename] = digest
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return digest


# ------------------------------------------------------------- 任务 0：账本到底拦不拦


def test_task0_editing_an_applied_migration_collides_with_the_ledger(tmp_path, monkeypatch):
    """红用例：原地改 0010，哪怕只改文案、哪怕 manifest 已同步，账本仍把这套路挡在门外。

    这就是 R120 不敢改 0010 的全部理由，也是"已应用则前滚"这条判据的证据。改的是注释行，
    语义一字未动 —— 越是没有语义的改动，越容易被当成"顺手改改"，所以拿它来测。

    这条是测量，不是缺陷：它在修之前和修之后都必须绿，所以它自己声明 profile，不依赖示例文件。
    """
    monkeypatch.setenv(indexing.EMBEDDING_MODEL_ENV, "measure-only-model")
    monkeypatch.setenv(indexing.EMBEDDING_DIMENSION_ENV, "512")
    catalog = _copy_catalog(tmp_path)
    before = mig.MIGRATIONS
    original_0010 = next(item for item in before if item.version == "0010")
    edited = original_0010.sql + "\n-- a comment-only edit, no semantics at all\n"
    (catalog / "0010_pgvector_chunks.sql").write_text(edited, encoding="utf-8")
    new_digest = _re_register(catalog, "0010_pgvector_chunks.sql")

    edited_migrations = mig.discover_migrations(catalog)  # the manifest gate is satisfied...
    changed = next(item for item in edited_migrations if item.version == "0010")
    assert changed.checksum == new_digest != original_0010.checksum

    installed = _migrated_database()  # ...and this database recorded the OLD digest.
    with pytest.raises(ValueError) as caught:
        mig.apply_migrations(installed, COMPOSE_DEFAULT_DATABASE, migrations=edited_migrations)

    assert str(caught.value) == "migration checksum mismatch: 0010"
    assert installed.applied == [], "a refused run may not have applied anything"
    assert not [sql for sql in installed.executed_sql if sql.startswith("ALTER DATABASE ")], (
        "it stops before declaring anything either: scripts/migrate.py returns 1, and because"
        " backend / worker / scheduler all wait for migrate, an install that already has 0010"
        " stops booting at all -- which is a worse delivery defect than the one an in-place"
        " edit of 0010 would have fixed"
    )

    # The asymmetry that makes an in-place edit sneaky: a machine that has not reached 0010
    # yet applies the edited text without a murmur, so the change looks fine on the next
    # clean build and only bites the databases that were already migrated.
    fresh = _clean_database(edited_migrations)
    applied = mig.apply_migrations(fresh, COMPOSE_DEFAULT_DATABASE, migrations=edited_migrations)
    assert [item.version for item in applied] == ["0010"]
    assert fresh.applied == ["0010"]


def test_task0_editing_without_the_manifest_dies_at_the_loader(tmp_path):
    """另一半：改了内容不登记 SHA-256，连目录都打不开 —— README 那句"漏登记 = loader 直接拒"。"""
    catalog = _copy_catalog(tmp_path)
    path = catalog / "0010_pgvector_chunks.sql"
    path.write_text(path.read_text(encoding="utf-8") + "\n-- %\n", encoding="utf-8")

    with pytest.raises(ValueError) as caught:
        mig.discover_migrations(catalog)

    assert str(caught.value) == "migration manifest checksum mismatch: 0010_pgvector_chunks.sql"


def test_task0_left_the_migrations_directory_alone():
    """本单走的是"禁止改 0010"那条判据，这条用例就是那句"我没改"的可查证据。"""
    on_disk = (MIGRATIONS_DIR / "0010_pgvector_chunks.sql").read_text(encoding="utf-8")
    manifest = json.loads((MIGRATIONS_DIR / "manifest.json").read_text(encoding="utf-8"))
    registered = next(item for item in mig.MIGRATIONS if item.version == "0010")

    assert sha256(on_disk.encode("utf-8")).hexdigest() == BASELINE_0010_SHA256
    assert manifest["0010_pgvector_chunks.sql"] == BASELINE_0010_SHA256
    assert registered.checksum == BASELINE_0010_SHA256
    assert not any(item.version > "0010" for item in mig.MIGRATIONS), (
        "no forward migration was needed either: nothing in migrations/** had to change"
    )


# ---------------------------------------- 判据 ①：干净首装（照示例文件配）必须走到 0010


def test_criterion_1_the_deployed_sample_declares_the_pair_the_migrate_step_needs():
    """判据 ① 的根：操作者唯一被交给的那份 env 文件里，过去根本没有这两个变量。

    R90a 让 runner 自己下发 GUC（那是修好的一半），但 deploy/.env.server.example —— 也就是
    deploy/README.server.md 让操作者复制的那一份 —— 一个字都没提 EMBEDDING_*，而 compose 又
    只在 deploy/.env.server 里取值。于是"照文档装一台干净机器"必然停在 migrate，且因为
    backend/worker/scheduler 都 depends_on migrate service_completed_successfully，整套栈
    起不来。这条用例修之前是红的。
    """
    declared = _env_documented(DEPLOY_SAMPLE)

    assert declared[indexing.EMBEDDING_DIMENSION_ENV] == str(indexing.DEFAULT_EMBEDDING_DIMENSION)
    assert declared[indexing.EMBEDDING_MODEL_ENV] == indexing.DEFAULT_EMBEDDING_MODEL


def test_criterion_1_the_two_samples_do_not_disagree_about_the_profile():
    """两份文档各写一套数 = 一台机器两种行为（R30 的口径，这里换到 embedding 这一族）。"""
    host = _env_documented(ROOT / ".env.example")
    deploy = _env_documented(DEPLOY_SAMPLE)
    names = (indexing.EMBEDDING_MODEL_ENV, indexing.EMBEDDING_DIMENSION_ENV)

    assert {name: host.get(name) for name in names} == {name: deploy.get(name) for name in names}


def test_criterion_1_the_sample_says_a_new_model_moves_the_width_and_rebuilds():
    """换 embedding 模型必须同时改宽度、并且重建索引 —— 这条写在部署侧那份上才算数。"""
    comments = "\n".join(
        line.lstrip("# ").strip()
        for line in DEPLOY_SAMPLE.read_text(encoding="utf-8-sig").splitlines()
        if line.strip().startswith("#")
    ).lower()

    assert "same edit" in comments, "must say the pair changes together"
    assert "rebuild" in comments, "a different profile means a rebuilt index, not a relabel"
    assert "scripts/rebuild_index.py" in comments


def test_criterion_1_a_clean_first_boot_reaches_0010_with_no_hand_written_guc(monkeypatch):
    """端到端（离线）：一次全新库，零手工 ALTER DATABASE，靠示例文件里的值走通。

    这是 R90 判据 ①"零人工前置"在离线层的形状：库级设置一开始是空的，runner 必须自己把成对
    的两个值下发成事务可见，0010 才可能落账。
    """
    for name, value in _declared_from_the_sample().items():
        monkeypatch.setenv(name, value)
    session = _clean_database()

    applied = mig.apply_migrations(session, COMPOSE_DEFAULT_DATABASE)

    assert [item.version for item in applied] == ["0010"]
    assert session.applied == ["0010"]
    alters = [sql for sql in session.executed_sql if sql.startswith("ALTER DATABASE ")]
    assert len(alters) == 2, alters
    assert session.database_settings[mig.EMBEDDING_DIMENSION_GUC] == (
        _declared_from_the_sample()[indexing.EMBEDDING_DIMENSION_ENV]
    )


def test_criterion_1_the_stop_is_a_python_gate_that_runs_before_any_migration_sql(monkeypatch):
    """任务 0/① 要的"停在哪一句"：停的位置在 app/db/migrations.py，0010 的 SQL 一个字都没发出去。

    把这条写成用例而不是写在交工里，是因为它同时是 R90b 判据 ④ 的一半前提：0010:216 那句
    RAISE（含 ``%I`` 的那句）在受支持的通路上已经不可达 —— 见 A11 的另一半。
    """
    monkeypatch.delenv(indexing.EMBEDDING_MODEL_ENV, raising=False)
    monkeypatch.delenv(indexing.EMBEDDING_DIMENSION_ENV, raising=False)
    session = _clean_database()

    with pytest.raises(mig.EmbeddingProfileError):
        mig.apply_migrations(session, COMPOSE_DEFAULT_DATABASE)

    assert session.applied == []
    assert not any("ALTER DATABASE" in sql for sql in session.executed_sql)
    assert not any("$r58" in sql for sql in session.executed_sql), (
        "0010's own body must never have been handed to the server"
    )


# --------------------------------- 判据 ②：补救指引里的库名、文件、命令必须与真源一致


def test_criterion_2_the_refusal_names_the_real_database_the_real_file_and_the_real_command(
    monkeypatch,
):
    """R90b 的第二件事：文案不许再把人指向一个不存在的库，也不许再指向容器根本不读的文件。

    R90a 原来那句写的是 "see .env.example"：.env.example 是宿主开发用的示例，compose 容器只读
    deploy/.env.server（docker-compose.yml 顶部那八行注释、SS34.2 判据 ⑤ 与
    tests/test_deployment_topology.py::test_containers_read_the_deployment_env_file 都这么说），
    所以照着改一次，等于什么都没改。这一条修之前是红的。
    """
    monkeypatch.delenv(indexing.EMBEDDING_MODEL_ENV, raising=False)
    monkeypatch.setenv(indexing.EMBEDDING_DIMENSION_ENV, "1024")
    session = _clean_database()

    with pytest.raises(mig.EmbeddingProfileError) as caught:
        mig.apply_migrations(session, COMPOSE_DEFAULT_DATABASE)

    message = str(caught.value)
    assert indexing.EMBEDDING_MODEL_ENV in message
    assert mig.MIGRATE_ENV_FILE in message, "name the file the containers actually read"
    assert ".env.example" not in message, "that file is not one the stack reads"
    assert f"'{COMPOSE_DEFAULT_DATABASE}'" in message, message
    assert f"{COMPOSE_DEFAULT_DATABASE}I" not in message and f"{COMPOSE_DEFAULT_DATABASE}s" not in (
        message
    ), "R90b: no %I / %s tail may follow the database name"
    assert mig.MIGRATE_COMPOSE_COMMAND in message, "give the command to re-run, not a shrug"


def test_criterion_2_the_named_database_is_what_the_server_said_not_a_string_join(monkeypatch):
    """库名只能抄 current_database() 的回答：换一枚带引号带分号的名字，文案里仍是整枚原样。"""
    awkward = 'ops"; DROP DATABASE brain; --'
    monkeypatch.delenv(indexing.EMBEDDING_MODEL_ENV, raising=False)
    monkeypatch.delenv(indexing.EMBEDDING_DIMENSION_ENV, raising=False)
    session = FreshSession(
        database=awkward,
        ledger={item.version: item.checksum for item in mig.MIGRATIONS if item.version != "0010"},
    )

    with pytest.raises(mig.EmbeddingProfileError) as caught:
        mig.apply_migrations(session, awkward)

    message = str(caught.value)
    assert repr(awkward) in message, "the prose must quote exactly what the server answered"
    assembled = [sql for sql in session.executed_sql if awkward in sql]
    assert all(sql.startswith("ALTER DATABASE ") for sql in assembled), (
        "only the statement the server composed itself may carry the name: " + repr(assembled)
    )
    assert session.applied == []


def test_criterion_2_every_path_and_command_in_the_guidance_matches_its_truth_source():
    """守卫用例：文案里出现的每一个文件名 / 服务名 / 命令，都要对得上真源，防再漂。

    SS33.2 判据 ④ 要的是"渲染出的库名 == current_database()"；那是 PL/pgSQL 那一侧的钉。
    Python 这一侧的同一族缺陷（指错文件、指错服务）由这条钉住：改 compose 的 env_file、改
    migrate 服务的 command、删掉示例文件里的成对变量，任何一处都会让这条变红。
    """
    compose = _compose()
    migrate = compose["services"]["migrate"]

    assert list(migrate["env_file"]) == [mig.MIGRATE_ENV_FILE], (
        "the guidance names a file the migrate service must actually read"
    )
    assert list(migrate["command"]) == ["python", "scripts/migrate.py"]
    assert f"-f {COMPOSE.name}" in mig.MIGRATE_COMPOSE_COMMAND
    assert f"--env-file {mig.MIGRATE_ENV_FILE}" in mig.MIGRATE_COMPOSE_COMMAND
    assert " run --rm migrate" in mig.MIGRATE_COMPOSE_COMMAND
    assert Path(mig.MIGRATE_ENV_SAMPLE_FILE).is_file()
    declared = _env_documented(Path(mig.MIGRATE_ENV_SAMPLE_FILE))
    for name in (indexing.EMBEDDING_MODEL_ENV, indexing.EMBEDDING_DIMENSION_ENV):
        assert declared.get(name), f"{name} must be documented in {mig.MIGRATE_ENV_SAMPLE_FILE}"
    # The host half of the sentence: scripts/migrate.py really does load HOST_ENV_FILE.
    runner = (ROOT / "scripts" / "migrate.py").read_text(encoding="utf-8")
    assert re.search(rf'load_dotenv\(.*"{re.escape(mig.HOST_ENV_FILE)}"\)', runner), runner
    assert mig.HOST_ENV_FILE not in list(migrate["env_file"]), (
        "the two files must stay two different claims, not one duplicated name"
    )


def test_criterion_2_the_default_database_the_stack_creates_is_the_one_named():
    """compose 里那台 pgvector/pgvector:pg16 的库名默认值，就是文案里的默认库名。"""
    compose = _compose()
    postgres = compose["services"]["postgres"]

    assert postgres["image"] == "pgvector/pgvector:pg16"
    declared = postgres["environment"]["POSTGRES_DB"]
    default = re.fullmatch(r"\$\{POSTGRES_DB:-([^}]+)\}", declared)
    assert default and default.group(1) == COMPOSE_DEFAULT_DATABASE, declared


# ---------------------------------- 0010 那句 %I：本单不改，但必须钉住它不再扩散


def _raise_literals(sql: str) -> list[str]:
    return re.findall(r"RAISE\s+EXCEPTION\s+'((?:[^']|'')*)'", sql, re.IGNORECASE)


def test_0010_raise_prefix_defect_is_grandfathered_and_may_not_spread():
    """``RAISE`` 只认 ``%``，``%I`` / ``%s`` 是 ``format()`` 的语法 —— SS33.2 判据 ④ 已真机实测三次。

    本单没有改 0010（任务 0 的判据），所以这一族缺陷还剩一处存量。存量必须写死成"只有 0010
    这一枚文件、只有这一句"，任何新迁移再写一次 `%I` 进 RAISE，这条立刻红。SS33.2 判据 ④
    要的那枚"库名 == current_database()"的钉，在受支持的通路上由 A7/A9/A11 负责。
    """
    offenders = set()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        for literal in _raise_literals(path.read_text(encoding="utf-8")):
            if re.search(r"%(?=[IiLlSsOo])", literal):
                offenders.add(path.name)

    assert offenders == {"0010_pgvector_chunks.sql"}, sorted(offenders)


def test_0010_is_still_right_about_the_refusal_it_only_renders_the_name_wrong():
    """存量那一句仍然在做它该做的事：没声明宽度就停，不猜。它错的只是渲染。"""
    sql = (MIGRATIONS_DIR / "0010_pgvector_chunks.sql").read_text(encoding="utf-8")
    refusal = next(
        literal for literal in _raise_literals(sql) if "will not guess one" in literal
    )

    assert "ALTER DATABASE %I SET app.embedding_dimension" in refusal
    end = sql.index(refusal) + len(refusal)
    following = sql[end:end + 120]
    assert "current_database()" in following, (
        "the name it renders wrong is the server's own name: " + repr(following)
    )
