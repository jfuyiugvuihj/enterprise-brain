# -*- coding: utf-8 -*-
r"""R714 · 属主那一枚拒绝按**类型**认，不按原句认（判据 1／2／3／4）。

一手事实：本席位开工现读，`app/api/v1/data.py::upload_excel` 拿 ``str(exc) ==`` 比登记表那句
拒绝原句，比的正是 `app/storage/datasets.py::DatasetRegistry.register` 抛出来的话。同一族形状
在盘上曾经有两处：`app/storage/artifacts.py::ArtifactOwnerScopeMissing`（R710 配的名，认类型）
与这一处（认原句）。本件把第二处也改成认类型。

罪不在「今天能不能过」——今天这两句话当然相等，所以这条腿今天是通的。罪在**原句一改就静默改口**
（改标点都算）：登记表哪天把话说顺一点，路由那一格就不再认得这枚拒绝，于是一枚本该 403 的越权
请求换来的是别的答复，而盘上没有任何一枚钉会说「部门这一格今天没人判了」。

本件钉三件事，逐条可失败：

① 判据 1（形状）：`app/**` 全树现读，``str(exc)`` 参与的任何判等一枚都不剩；路由那一段源码只按
   ``isinstance(..., DatasetOwnerScopeMissing)`` 认；登记表那句话在 ``app/**`` 里只剩一枚出处。
② 判据 2（两枚反证牙）：同类型、换了原句的拒绝 ⇒ 路由仍然答 403（退役那写法在这里必红）；
   同原句、换了类型的冒牌 ⇒ 路由**不认**，原样抛出去答 500（退役那写法会把它当拒绝）。两枚牙
   共用一具替身，唯一的变量是异常类型；另附一枚把退役写法原地重放的逻辑钉，读数逐行可查。
③ 判据 3（语义不许放宽）：真登记表＋无部门主体走真路由，答复还是 403
   ``department_scope_required``，盘上与台账照旧归零；``DatasetOwnerScopeMissing`` 仍是
   ``ValueError`` 的子类，登记表那句话一个字没改——本单只换认法，不改判定。

全程离线：不连 PostgreSQL、不起服务、不开宿主模型端口、不打模型。登记表坐的是
``InMemoryDatasetTableStore``，知识库那条腿只记账。坐标一律 ``文件::符号``，本件不写行号。
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
APP_DIR = REPO / "app"

OWNER = "r714-manager"
DEPT = "r714-finance"
CSV_NAME = "r714-台账.csv"
CSV_BYTES = "部门,预算额度\n研发,3100\n".encode("utf-8")
#: 登记表真正在说的那句话：本件不许改它（判据 3）。
REGISTRY_SENTENCE = "dataset owner must have a department scope"
#: 判据 1 的机器形态：派工词里那枚 rg 谓词的等价实现。
REFUSAL_STRING_MATCH = re.compile(r"str\(\s*exc\s*\)\s*(?:==|!=)")
#: 退役那写法在路由侧留下的句子副本；本件之后必须归零。
RETIRED_CONSTANT = "_OWNER_SCOPE_ERROR"
SCOPE_CODE = "department_scope_required"
#: 判据 2 的第一枚牙：同类型、不同原句。
REWORDED_SENTENCE = "owner scope is missing for this dataset row"


def _account(department: str) -> dict:
    return {
        "id": OWNER,
        "username": OWNER,
        "role": "manager",
        "department": department,
    }


def _registry_offline(tmp_path: Path):
    from app.storage.datasets import DatasetRegistry, InMemoryDatasetTableStore

    return DatasetRegistry(
        root=tmp_path,
        metadata_path=tmp_path / ".dataset-metadata.json",
        store=InMemoryDatasetTableStore(),
    )


class _Harness:
    """真路由＋真登记表，外加一枚「登记表抛什么」的旋钮与知识库腿的记账。

    ``register_raises`` 一给，``DatasetRegistry.register`` 就换成一枚只会拒绝的替身：路由脚下的
    写盘、解析、清理三步全是真的。本件要量的只有一格——拒绝抵达路由时**怎么被认出来**。
    """

    def __init__(self, monkeypatch, tmp_path, *, department: str = DEPT, register_raises=None):
        from app.api.v1 import data
        from app.common import auth
        from app.storage import datasets as datasets_module
        from app.storage.datasets import DatasetRegistry

        self.data_dir = tmp_path / "data"
        self.data_dir.mkdir()
        self.index_calls: list[str] = []
        self.registry = _registry_offline(self.data_dir)
        self.account = _account(department)
        monkeypatch.setattr(data, "DATA_DIR", str(self.data_dir))
        monkeypatch.setattr(data, "dataset_registry", self.registry)
        monkeypatch.setattr(datasets_module, "dataset_registry", self.registry)
        monkeypatch.setattr(auth, "get_user", lambda username: dict(self.account))

        async def record_index(**kwargs):
            self.index_calls.append(str(kwargs.get("display_filename")))
            return {}

        monkeypatch.setattr(data, "index_dataset_copy", record_index)

        if register_raises is not None:
            def refuse(registry_self, storage_path, **values):
                raise register_raises

            monkeypatch.setattr(DatasetRegistry, "register", refuse)

    def upload(self, name: str = CSV_NAME, payload: bytes = CSV_BYTES):
        from app.common.auth import create_token
        from app.main import app

        return TestClient(app, raise_server_exceptions=False).post(
            "/api/v1/upload-excel",
            headers={"Authorization": "Bearer {0}".format(create_token(OWNER))},
            files={"file": (name, payload, "application/octet-stream")},
        )


def _str_equality_comparisons(source: str) -> list[str]:
    """源码里「把 ``str(...)`` 与一枚字符串字面量判等」的比较式，逐枚交回原文（不报行号）。"""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        left_is_str_call = (
            isinstance(left, ast.Call)
            and isinstance(left.func, ast.Name)
            and left.func.id == "str"
        )
        if not left_is_str_call:
            continue
        for operator, comparator in zip(node.ops, node.comparators):
            if isinstance(operator, ast.Eq) and isinstance(comparator, ast.Constant):
                if isinstance(comparator.value, str):
                    found.append(ast.unparse(node))
    return found


# ==================== ① 形状：盘上不再留任何一处比原句的写法（判据 1）====================


def test_the_app_holds_no_str_comparison_of_an_exception() -> None:
    """派工词那枚 rg 谓词的等价实现：``app/**`` 全树现读，``str(exc)`` 参与的判等＝零枚。"""
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if REFUSAL_STRING_MATCH.search(line):
                offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], "拒绝又回到比原句那一族：" + " | ".join(sorted(set(offenders)))


def test_the_route_recognises_the_refusal_by_type_only() -> None:
    """``app/api/v1/data.py::upload_excel`` 现读：认的是类型，不留一处比句子的比较式。"""
    from app.api.v1 import data
    from app.storage.datasets import DatasetOwnerScopeMissing

    source = inspect.getsource(data.upload_excel)

    assert "isinstance(exc, DatasetOwnerScopeMissing)" in source, source
    assert "str(exc)" not in source, "路由又回去读原句了"
    assert _str_equality_comparisons(source) == [], "这一格还留着一处 str(...) 与字面量判等"
    assert data.DatasetOwnerScopeMissing is DatasetOwnerScopeMissing, (
        "认的不是登记表抛的那枚类型：两枚同名的类就是一句换了写法的话"
    )


def test_the_retired_copy_of_the_sentence_is_gone_from_the_app() -> None:
    """那句话在 ``app/**`` 里只剩一枚出处：登记表自己说的。路由侧的副本必须已经归零。"""
    from app.api.v1 import data

    homes = sorted(
        str(path.relative_to(REPO)).replace("\\", "/")
        for path in APP_DIR.rglob("*.py")
        if REGISTRY_SENTENCE in path.read_text(encoding="utf-8", errors="replace")
    )
    assert homes == ["app/storage/datasets.py"], homes
    assert not hasattr(data, RETIRED_CONSTANT), (
        "路由又留了一份句子副本：下一枚改标点就是静默失效"
    )


# ==================== ② 两枚反证牙（判据 2）====================


def test_a_reworded_refusal_of_the_same_type_still_answers_403(monkeypatch, tmp_path) -> None:
    """牙 1：同类型、不同原句。登记表哪天把话说顺一点，403 那一格不许漂。

    退役那写法在这里必红：``str(exc) ==`` 比不上一句它从没见过的话，拒绝会被原样抛出去答 500。
    """
    from app.storage.datasets import DatasetOwnerScopeMissing

    harness = _Harness(
        monkeypatch, tmp_path, register_raises=DatasetOwnerScopeMissing(REWORDED_SENTENCE)
    )

    response = harness.upload()

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == SCOPE_CODE, response.text
    assert REWORDED_SENTENCE not in response.text, "内部原句又外泄了"
    assert not (harness.data_dir / CSV_NAME).exists(), "拒收之后盘上留了货"
    assert harness.index_calls == [], "被拒的上传已经把知识库那条腿叫醒了"


def test_the_old_sentence_on_an_unnamed_type_is_not_recognised(monkeypatch, tmp_path) -> None:
    """牙 2：同原句、不同类型。冒牌不许被当成属主拒绝——退役那写法会认下它。

    「认类型」的另一半是**只**认类型：一枚裸 ``ValueError`` 带着当年那句话，路由不能给它配上属主
    码，否则任何一处手写的同名句子都能冒充这一格，把真故障说成权限问题。
    """
    harness = _Harness(monkeypatch, tmp_path, register_raises=ValueError(REGISTRY_SENTENCE))

    response = harness.upload()

    assert response.status_code == 500, response.text
    assert SCOPE_CODE not in response.text, "冒牌被认成了属主拒绝"
    assert not (harness.data_dir / CSV_NAME).exists(), "清理那一格不该因认法而漂"
    assert harness.index_calls == [], "失败之后知识库那条腿还是被叫醒了"


def test_the_retired_shape_would_have_broken_on_both_teeth() -> None:
    """把退役那写法原地重放一次：两枚牙各打它一次——「今天能过」不等于「今天已证」。

    这一枚不碰产品码，只证一件事：同一条腿，``str(exc) == 句子`` 与本单的 ``isinstance`` 在两枚
    牙上给出**相反**的答复。谁要收回本件的认法，得先解释这两行读数。
    """
    from app.storage.datasets import DatasetOwnerScopeMissing

    def retired(exc):
        return str(exc) == REGISTRY_SENTENCE

    def renamed(exc):
        return isinstance(exc, DatasetOwnerScopeMissing)

    reworded = DatasetOwnerScopeMissing(REWORDED_SENTENCE)
    impostor = ValueError(REGISTRY_SENTENCE)

    assert retired(reworded) is False and renamed(reworded) is True
    assert retired(impostor) is True and renamed(impostor) is False


# ==================== ③ 语义不许放宽（判据 3）====================


def test_the_refusal_is_named_and_still_a_value_error() -> None:
    """具名不等于换契约：它仍是 ``ValueError`` 的子类，老的 ``except ValueError`` 调用方不改坏。"""
    from app.storage.datasets import DatasetOwnerScopeMissing

    assert issubclass(DatasetOwnerScopeMissing, ValueError), "老调用方会被这枚改名打坏"


def test_the_registry_refuses_a_departmentless_owner_with_the_named_type(tmp_path) -> None:
    """真登记表那一格：抛的是具名类型，而那句话一个字没改。"""
    from app.agents.contracts import Principal
    from app.storage.datasets import DatasetOwnerScopeMissing

    registry = _registry_offline(tmp_path)
    data_file = tmp_path / CSV_NAME
    data_file.write_bytes(CSV_BYTES)

    with pytest.raises(DatasetOwnerScopeMissing) as refused:
        registry.register(data_file, principal=Principal.from_user(_account("")))

    assert str(refused.value) == REGISTRY_SENTENCE, "本单只换认法：句子一改，判据 3 就破了"
    assert isinstance(refused.value, ValueError)


def test_a_principal_with_a_department_still_registers(tmp_path) -> None:
    """反证：补上部门，同一枚登记表就把行落下来——上面那枚拒绝只能来自部门那一格。"""
    from app.agents.contracts import Principal

    registry = _registry_offline(tmp_path)
    data_file = tmp_path / CSV_NAME
    data_file.write_bytes(CSV_BYTES)

    record = registry.register(data_file, principal=Principal.from_user(_account(DEPT)))

    assert registry.get_active_by_filename(CSV_NAME) is not None
    assert record.dataset_id


def test_the_route_still_answers_the_registered_shape_end_to_end(monkeypatch, tmp_path) -> None:
    """真路由＋真登记表（无部门主体）：403 与在册码照旧，盘上与台账归零——既有语义一字未动。"""
    harness = _Harness(monkeypatch, tmp_path, department="")

    response = harness.upload()

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == SCOPE_CODE, response.text
    assert not (harness.data_dir / CSV_NAME).exists()
    assert harness.registry.get_active_by_filename(CSV_NAME) is None
    assert harness.index_calls == []
