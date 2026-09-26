"""R256 判据③ —— 裸机路径那句 ``PERSISTENCE_BACKEND`` 缺省，从今天起是一句有钉的决定。

判据③给了两条出路：要么给 JSON 版表存储，要么「把操作者前置写进 `setup.sh`/`.env.example`
并让缺省翻转有钉」。本单走第二条，理由逐条落在盘上：

* 仓库里**没有** ``setup.sh``（``git ls-files`` 零命中，``git log --all -- setup.sh`` 也零命中），
  裸机那条路是 README 第 71 行 ``cp .env.example .env`` —— 所以前置只能写进 ``.env.example``。
* JSON 版表存储不在本单写域（``app/storage/datasets.py`` 只许动「把新列接上读写」那几行），
  而且它与 R249 自己钉下的「本模块不再导入 JSON 持久化台账」正面冲突。
* 代码侧的缺省**今天不动**，因为 ``app/common/audit.py`` 独立地也读同一枚变量、也缺省 ``json``，
  而它不在本单写域：只翻两枚就是 R30 那笔账的翻版（一页一码两个数）。于是本件把「翻转」本身
  钉成一件必须同时改三处、还要改示例与本件的**动作**。

四枚断言因此各守一段：三处读同一枚缺省（不许半翻）、缺省与示例的关系写清楚（不许暗翻）、
缺省落地时的那条 warning 仍然诚实（不许把丢失写成正常），以及——这条最要紧——**示例文件确实是
裸机操作者会打开的那一份**（R90a 就是把指引写进了一份容器永不打开的文件）。
"""
from __future__ import annotations

import ast
import logging
import os
from pathlib import Path

import pytest

from app.storage import datasets as dataset_storage
from app.storage import persistence as persistence_module
from app.storage.datasets import InMemoryDatasetTableStore, build_dataset_table_store
from app.storage.persistence import JsonPersistenceAdapter, build_persistence_adapter

REPO = Path(__file__).resolve().parents[1]
ENV = "PERSISTENCE_BACKEND"
SAMPLE = REPO / ".env.example"

#: 今天读这枚环境变量的三处。第三处在 R256 写域之外，所以它出现在这里正是本件要看住它的原因。
READER_FILES = (
    Path("app/storage/persistence.py"),
    Path("app/storage/datasets.py"),
    Path("app/common/audit.py"),
)
#: 两处工厂接受的值（``datasets`` 还多认一枚 postgresql 别名，见 build_dataset_table_store）。
ACCEPTED_DEFAULTS = {"json", "local", "postgres", "postgresql"}


def _getenv_defaults(relative: Path) -> list[str]:
    """一个文件里 ``os.getenv("PERSISTENCE_BACKEND", <default>)`` 写出的所有缺省字面量。

    走 AST 而不是文本搜：本件的靶子是「代码实际会用哪个值」，注释里那句话不是。
    """
    tree = ast.parse((REPO / relative).read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        spelling = getattr(function, "attr", None) or getattr(function, "id", "")
        if spelling != "getenv" or not node.args:
            continue
        key = node.args[0]
        if not (isinstance(key, ast.Constant) and key.value == ENV):
            continue
        default = node.args[1] if len(node.args) > 1 else None
        assert isinstance(default, ast.Constant) and isinstance(default.value, str), (
            f"{relative}: {ENV} 的缺省必须是字面量，藏进变量里的缺省本件读不到，也不许有"
        )
        found.append(default.value)
    assert found, f"{relative} 不再读 {ENV}：本件与它的分工变了，请连本文件一起改口"
    return found


def _documented(path: Path) -> dict[str, str]:
    """按读它的那两位的办法解析：最后一枚赋值赢，``#`` 起头的行是散文。"""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        values[name.strip()] = value.strip()
    return values


# ------------------------------------------------------- 半翻：三处不许写出两个答案


def test_the_three_readers_still_share_one_default():
    """三处缺省必须是同一个值。只翻其中一处 = 一台机器两种持久化，正是 R30 的口径。"""
    defaults = {str(relative): _getenv_defaults(relative) for relative in READER_FILES}
    every = {value for values in defaults.values() for value in values}

    assert len(every) == 1, defaults
    assert every <= ACCEPTED_DEFAULTS, every
    assert all(len(set(values)) == 1 for values in defaults.values()), defaults


def test_the_code_default_and_the_sample_are_one_decision_spelled_out_loudly():
    """示例写 ``postgres``；代码缺省与它**不同**是允许的，但必须在同一份文件里被写明并指名三处。

    这就是「让缺省翻转有钉」的那枚钉：翻到 ``postgres`` 的人会发现示例已经在那一值上，只剩本件
    与那条 warning；把示例改回 ``json`` 的人必须同时改掉下面那三枚路径的点名。
    """
    documented = _documented(SAMPLE)
    code_default = _getenv_defaults(READER_FILES[0])[0]
    prose = SAMPLE.read_text(encoding="utf-8")

    assert documented.get(ENV), f"{ENV} 必须出现在 {ENV}.example 里，裸机操作者只能读到这里"
    assert documented[ENV] in ACCEPTED_DEFAULTS, documented[ENV]
    assert documented[ENV] == "postgres", "示例是发给真部署的：它不许把过渡态写成建议值"
    if code_default != documented[ENV]:
        assert "default in the code" in prose.lower(), "缺省与示例不一致，就必须有一句话解释它"
        for relative in READER_FILES:
            assert relative.as_posix() in prose, f"{prose!r} 没点名 {relative}"


def test_the_sample_is_the_file_a_bare_metal_operator_actually_opens():
    """R90a 的教训：把前置写进一份没人打开的文件，等于没写。

    仓库没有 ``setup.sh``（第一格当场钉住），裸机那条路只有 README 第 71 行那句 ``cp .env.example
    .env``——所以本单把前置写进 ``.env.example`` 是有落点的：它落在那条复制命令的另一头。
    """
    tracked = os.popen("git ls-files").read().splitlines()

    assert not [name for name in tracked if Path(name).name == "setup.sh"], tracked
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "cp .env.example .env" in readme, "README 不再指向这份示例，本单的前置就得换地方写"


# ------------------------------------------------------- 缺省落地时那条话不许变软


def test_an_absent_backend_line_lands_on_the_in_process_table(monkeypatch, tmp_path):
    """今天的真实行为，钉成一根线：不设这枚变量，登记就落在会随进程消失的那张表上。

    谁把三处缺省一起翻成 ``postgres``，这一格当场红——那是**要求**它红：那一翻同时改变了
    「没配库的机器现在怎么启动」，必须有人在这里签一次，而不是让一次默认值改动悄悄走过全量门。
    """
    monkeypatch.delenv(ENV, raising=False)

    store = build_dataset_table_store()
    adapter = build_persistence_adapter()

    assert isinstance(store, InMemoryDatasetTableStore), type(store)
    assert isinstance(adapter, JsonPersistenceAdapter), type(adapter)


def test_the_transition_warning_names_the_loss_and_the_remedy(monkeypatch, caplog):
    """那句 warning 是本单唯一替「重启即失」作证的运行时声音：它必须还说得清丢了什么、怎么修。"""
    monkeypatch.delenv(ENV, raising=False)
    monkeypatch.setattr(dataset_storage, "_TRANSITION_WARNING_LOGGED", False)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        build_dataset_table_store()

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "PERSISTENCE_BACKEND=postgres" in message and "重启即失" in message for message in messages
    ), messages


@pytest.mark.parametrize("spelling", ["json", "local", "postgres", "postgresql", "banana"])
def test_one_switch_moves_both_surfaces(monkeypatch, spelling):
    """一枚变量决定两处（登记表 + 控制面台账），且不接受第三个答案。

    两处的取值集合本来就差一枚 ``postgresql`` 别名——这一格把这处**已知**的不一致钉在纸上：
    哪天有人补齐，这里红一次，改的人要么对齐、要么把这句话改掉，而不是留一份看不见的分歧。
    """
    monkeypatch.setenv(ENV, spelling)

    table_answers = {}
    adapter_answers = {}
    for name, collect in (("datasets", table_answers), ("persistence", adapter_answers)):
        try:
            if name == "datasets":
                collect["value"] = build_dataset_table_store()
            else:
                collect["value"] = build_persistence_adapter()
        except Exception as error:  # noqa: BLE001 - 本件判的就是"谁拒绝了"
            collect["error"] = type(error).__name__

    if spelling in {"postgres", "postgresql"}:
        assert "error" not in table_answers, table_answers
        assert "value" not in table_answers or not isinstance(table_answers["value"], InMemoryDatasetTableStore)
    elif spelling == "banana":
        assert "error" in table_answers and "error" in adapter_answers, (table_answers, adapter_answers)
    else:
        assert isinstance(table_answers["value"], InMemoryDatasetTableStore)
        assert isinstance(adapter_answers["value"], JsonPersistenceAdapter)


def test_the_container_path_still_pins_postgres_for_every_writer():
    """判据③只欠裸机那一条路：容器侧 ``PERSISTENCE_BACKEND: postgres`` 不许被本单弄丢。

    逐服务的钉在 ``tests/test_deployment_topology.py``，这一格只看「compose 里那几行还在」，
    与本件的样例文件形成对照：容器读 compose，裸机读 ``.env.example``，两条路都不许读缺省。
    """
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    lines = compose.splitlines()
    anchor = next(
        index for index, line in enumerate(lines) if line.startswith("x-storage-env:")
    )
    block = []
    for line in lines[anchor + 1 :]:
        if line.strip() and not line.startswith(" "):
            break
        block.append(line)

    assert any(line.strip() == f"{ENV}: postgres" for line in block), "\n".join(block)
    assert f"{ENV}: json" not in compose
    # 那一块是被 4 枚服务合并进去的（backend / worker / migrate / 还有一枚），枚数是一枚引信：
    # 多一个写状态的服务就必须回来看它是不是也合并了这一份 env。
    assert compose.count("<<: *storage-env") == 4, compose.count("<<: *storage-env")