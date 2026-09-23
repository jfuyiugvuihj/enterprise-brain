"""R178 第 2 格 —— R163 交回的 B 类 row_scope_tools.all_datasets_hidden_says_no_data_file。

复现的原文（本树自证，不抄结论）：app/agents/tools.py:237-248 未选中文件时逐条算
authorization_decision，只把 allowed 的收进 permitted，全被裁掉就返回空表且不带任何因由；
拿到空表的两条腿 app/agents/tools.py:952-954 与 :1069-1071 原样吐
「暂无数据文件。请先在数据分析面板上传 Excel/CSV 文件。」——员工明明上传过，这句话把
「有，但你不能看」说成了「不存在」。同形两处，本件分别钉到。

判据③三张脸（两两不同句、不许并格）：
- 脸一：这一轮没有绑定任何数据文件（台账真的是空的）。
- 脸二：有数据文件，但按你的权限一份都读不到（权限事实，去申请权限，别重新上传）。
- 脸三：有可见文件，但没有你要的那一列/那一维（本单不动它的话术与判定，只钉它不许并被
  前两张脸共用）。

全进程内：不起服务、不打模型（_llm_pandas_code 一律换桩）、不连 PG，数据集台账落在 tmp_path。
"""

from __future__ import annotations

import pytest

from app.agents import evidence, tools

DEPT_OWN = "r178-own-dept"
DEPT_FOREIGN = "r178-fx-dept"
BODY_TOKEN = "R178T-OWN-ONLY 这一行只属于本部门"
FILE_A = "r178-own-sales.csv"
FILE_B = "r178-own-staff.csv"

#: 判据②的甩锅词族（口径照 R163 的 ABSENCE_BLAME，只留与本格相关的那几条）。
ABSENCE_BLAME = ("暂无数据文件", "暂无数据", "没有数据文件", "请先在数据分析面板上传", "no data")
#: 说得出权限因由就算诚实（同样照 R163 的 AUTHORITY_WORDS 口径）。
AUTHORITY_WORDS = ("权限", "无权", "授权", "可见范围", "permission_denied", "department_scope_required")
#: 闸上允许对外交出的公开码（封闭枚举的子集，多一枚就是发明词表）。
GATE_PUBLIC_CODES = {
    "authentication_required",
    "permission_denied",
    "authorization_unavailable",
    "account_unavailable",
    "department_scope_required",
}


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch):
    """每条用例都先把 LLM 那一条腿钉死：本件全程离线，一次模型调用都不许发出。"""
    monkeypatch.setattr(
        tools,
        "_llm_pandas_code",
        lambda df, query: "df['revenue'].max()" if "revenue" in df else "0",
    )


def _config(**overrides) -> dict:
    configurable = {
        "id": "u-r178-foreign",
        "username": "r178-foreign-manager",
        "role": "manager",
        "department": DEPT_FOREIGN,
        "evidence_bag": evidence.new_evidence_bag(),
    }
    configurable.update(overrides)
    return {"configurable": configurable}


def _registry(monkeypatch, tmp_path, slug: str = "main"):
    """一枚用例一座临时台账：文件名在台账里是唯一的，共用一份就会互相顶掉。"""
    from app.storage import datasets as dataset_storage
    from app.storage.datasets import DatasetRegistry

    root = tmp_path / slug
    registry = DatasetRegistry(root=root, metadata_path=tmp_path / (slug + "-meta.json"))
    monkeypatch.setattr(dataset_storage, "dataset_registry", registry)
    return registry


def _register(registry, tmp_path, filename: str, *, rows: int = 1, department: str = DEPT_OWN):
    from app.agents.contracts import Principal

    path = registry.root / filename
    body = "department,name,revenue\n"
    for index in range(rows):
        body += department + ",R178T-OWN-ONLY-" + str(index) + "," + str(7 + index) + "\n"
    path.write_text(body, encoding="utf-8")
    return registry.register(
        path,
        principal=Principal.from_user(
            {
                "id": "u-r178-owner",
                "username": "r178-owner",
                "role": "manager",
                "department": department,
            }
        ),
        classification="1",
    )


def _codes(config: dict, tool: str) -> list[str]:
    return [
        str(item["error_code"])
        for item in config["configurable"]["evidence_bag"]["tool_statuses"]
        if item.get("tool") == tool and item.get("error_code")
    ]


#: 两条同形的腿：app/agents/tools.py:952-954 与 :1069-1071。一处一枚用例，分开钉。
LEGS = ("analyze_data", "query_data")


def _run(leg: str, config: dict) -> str:
    if leg == "analyze_data":
        return tools._analyze_data("营收最高是多少", config)
    return tools._query_data("营收最高是多少", config)


# ==================== 脸二：有文件，但按你的权限一份都读不到 ====================


@pytest.mark.parametrize("leg", LEGS)
def test_hidden_datasets_are_reported_as_a_permission_fact(monkeypatch, tmp_path, leg) -> None:
    registry = _registry(monkeypatch, tmp_path)
    _register(registry, tmp_path, FILE_A)
    _register(registry, tmp_path, FILE_B)
    config = _config()

    out = _run(leg, config)

    assert isinstance(out, str), "工具交回去的必须是一句人话：" + repr(out)
    assert "DatasetsHiddenByScope" not in out, (
        "内部标记对象被原样吐给了调用方——这一条腿没有把「权限藏光」翻成人话"
    )
    blame = [word for word in ABSENCE_BLAME if word in out]
    assert not blame, "把「有，但你不能看」说成了「不存在」，命中甩锅词 " + str(blame) + "：" + out
    assert any(word in out for word in AUTHORITY_WORDS), "交回了空结果，却没交出权限因由：" + out
    assert "重新上传" in out, "得让人知道这不是一次重新上传能解决的事：" + out
    assert "管理员" in out, "得让人知道该去找谁办这件事：" + out


@pytest.mark.parametrize("leg", LEGS)
def test_hidden_dataset_denial_carries_a_public_code_on_both_paths(monkeypatch, tmp_path, leg) -> None:
    registry = _registry(monkeypatch, tmp_path)
    _register(registry, tmp_path, FILE_A)
    config = _config()

    out = _run(leg, config)

    codes = _codes(config, tools._DATASET_GATE)
    assert len(codes) == 1, "一次权限藏光落了 " + str(len(codes)) + " 条码：" + str(codes)
    assert codes[0] in GATE_PUBLIC_CODES, codes
    assert "error_code=" + codes[0] in out, "两条路必须报同一个码：" + out


@pytest.mark.parametrize("leg", LEGS)
def test_hidden_dataset_denial_names_no_resource_it_just_refused(monkeypatch, tmp_path, leg) -> None:
    registry = _registry(monkeypatch, tmp_path)
    _register(registry, tmp_path, FILE_A)
    _register(registry, tmp_path, FILE_B, department="r178-third-dept")
    config = _config()

    out = _run(leg, config)

    for secret in (FILE_A, FILE_B, DEPT_OWN, BODY_TOKEN):
        assert secret not in out, "拒绝的话里出现了被挡资源的具体名字/归属：" + secret


# ==================== 脸一：这一轮没有绑定任何数据文件 ====================


@pytest.mark.parametrize("leg", LEGS)
def test_empty_registry_says_nothing_is_bound(monkeypatch, tmp_path, leg) -> None:
    _registry(monkeypatch, tmp_path)
    config = _config()

    out = _run(leg, config)

    assert isinstance(out, str)
    assert "本轮没有绑定任何数据文件" in out, out
    assert "数据分析面板" in out, "这时候才是真的该去上传：" + out


@pytest.mark.parametrize("leg", LEGS)
def test_empty_registry_does_not_claim_a_permission_fact(monkeypatch, tmp_path, leg) -> None:
    """反向并格闸：台账真空的时候，也不许假称「有文件但你读不到」。"""
    _registry(monkeypatch, tmp_path)
    config = _config()

    out = _run(leg, config)

    assert not _codes(config, tools._DATASET_GATE), "一次都不存在的资源，凭什么落一条权限拒绝"
    assert "权限" not in out and "一份都读不到" not in out, out


# ==================== 脸三：有可见文件，但没有你要的那一列/那一维 ====================


@pytest.mark.parametrize("leg", LEGS)
def test_visible_file_without_analyzable_rows_is_its_own_third_face(monkeypatch, tmp_path, leg) -> None:
    registry = _registry(monkeypatch, tmp_path)
    _register(registry, tmp_path, FILE_A, rows=0, department=DEPT_FOREIGN)
    config = _config(department=DEPT_FOREIGN)

    out = _run(leg, config)

    assert isinstance(out, str)
    assert "权限" not in out and "一份都读不到" not in out, (
        "文件本来就看得见，却把它说成权限挡掉的：" + out
    )
    assert "本轮没有绑定任何数据文件" not in out, "有可见文件，就不能说没绑定文件：" + out


# ==================== 判据③：三张脸两两不同句，不许并格 ====================


@pytest.mark.parametrize("leg", LEGS)
def test_the_three_faces_are_pairwise_different_sentences(monkeypatch, tmp_path, leg) -> None:
    def build(scenario: str) -> str:
        registry = _registry(monkeypatch, tmp_path, slug=scenario)
        if scenario == "bound":
            return _run(leg, _config())
        if scenario == "hidden":
            _register(registry, tmp_path, FILE_A)
            return _run(leg, _config())
        _register(registry, tmp_path, FILE_B, rows=0, department=DEPT_FOREIGN)
        return _run(leg, _config(department=DEPT_FOREIGN))

    bound = build("bound")
    hidden = build("hidden")
    visible = build("visible")

    assert bound != hidden, "「没有绑定文件」与「按权限读不到」并成了同一句：" + bound
    assert hidden != visible, "「按权限读不到」与「有文件但没有你要的那一维」并成了同一句"
    assert bound != visible, "「没有绑定文件」与「有文件但没有你要的那一维」并成了同一句"
    # 第四句：选中了别人的那份文件，那条腿早就说得出因由，不许被前三种复用。
    _register(_registry(monkeypatch, tmp_path), tmp_path, FILE_A)
    selected = _run(leg, _config(data_filename=FILE_A))
    for face in (bound, hidden, visible):
        assert selected != face, "选中文件那条既有说法被并进了新话术"


# ==================== 正向对照：绿不是空转刷出来的 ====================


@pytest.mark.parametrize("leg", LEGS)
def test_a_permitted_dataset_still_reaches_the_tool(monkeypatch, tmp_path, leg) -> None:
    """三张脸都只在「读不到」时说话；该看得见的时候必须真的看得见，否则全套断言是空转。"""
    registry = _registry(monkeypatch, tmp_path)
    _register(registry, tmp_path, FILE_A, department=DEPT_FOREIGN)
    config = _config(department=DEPT_FOREIGN)

    out = _run(leg, config)

    assert FILE_A in out, out
    for face in ("本轮没有绑定任何数据文件", "一份都读不到"):
        assert face not in out