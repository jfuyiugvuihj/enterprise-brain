"""R180 · data.py 越权矩阵两格的常驻反证（跟进单 §86 二 / §87 六认领表）。

钉 R163 只读矩阵在 data.py 族打出来的两格：

  A 类 ``dataset_route.preview_must_not_leak_foreign_rows`` —— 预览只过文件级授权、
      没有行级过滤，别的部门 manager 能读到别人的数据正文行；
  B 类 ``dataset_route.nodept_catalog_answers_empty_list`` —— 目录用静默 ``continue``
      把「有文件但你不能看」说成「这里没有文件」。

判据⑤至少三把常驻反证，每把写清钉红哪一格：
  · 摘掉行级过滤 -> test_preview_hides_foreign_and_blank_rows... 红（A 类格）；
  · 摘掉拒绝审计 -> test_preview_row_denial_is_audited... / test_catalog_denial_is_audited... 红；
  · 把「有但不能看」退回空列表 / 空表 -> test_preview_that_hides_every_row... /
    test_catalog_names_files_you_cannot_open... 红。
另附两把同族的刀：把部门维度之外的清空说成权限拒绝 ->
test_row_scope_never_blames_the_department_dimension... 红；另立一份 reason→码 映射、
与翻译层的字面量脱钩 -> test_the_two_public_codes_stay_bolted_to... 红。
另附正向对照（keeper / admin / 未登记 / 空目录 / 跨部门 403），证明绿不是空转刷出来的。

全部离线：进程内 TestClient，零起服务、零模型、零库。
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

DEPT_OWN = "r180-finance"
DEPT_FOREIGN = "r180-hr"
OWN_TOKEN = "R180-OWN-SECRET"
FOREIGN_TOKEN = "R180-FOREIGN-SECRET"
BLANK_TOKEN = "R180-BLANK-SECRET"

MIXED_CSV = """部门,note
r180-finance,R180-OWN-SECRET
r180-hr,R180-FOREIGN-SECRET
"",R180-BLANK-SECRET
"""

ALL_FOREIGN_CSV = """部门,note
r180-hr,R180-FOREIGN-SECRET
r180-hr,R180-FOREIGN-SECRET-2
"""


def _principal(username, department, role="manager"):
    from app.agents.contracts import Principal

    return Principal.from_user(
        {"id": username, "username": username, "role": role, "department": department}
    )


def _wire(monkeypatch, tmp_path, csv_text):
    from app.api.v1 import data
    from app.common import auth
    from app.storage import datasets
    from app.storage.datasets import DatasetRegistry

    registry = DatasetRegistry(root=tmp_path, metadata_path=tmp_path / "meta.json")
    monkeypatch.setattr(data, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(data, "dataset_registry", registry)
    monkeypatch.setattr(datasets, "dataset_registry", registry)

    path = tmp_path / "consolidated.csv"
    path.write_text(csv_text, encoding="utf-8")
    registry.register(path, principal=_principal("owner-finance", DEPT_OWN))

    accounts = {
        "keeper": {"id": "keeper", "username": "keeper", "role": "manager", "department": DEPT_OWN},
        "xdept": {"id": "xdept", "username": "xdept", "role": "manager", "department": DEPT_FOREIGN},
        "admin": {"id": "admin", "username": "admin", "role": "admin", "department": "r180-hq"},
    }
    monkeypatch.setattr(auth, "get_user", lambda username: accounts.get(username))

    from app.common.auth import create_token
    from app.main import app

    client = TestClient(app)
    client.headers.update({"Authorization": "Bearer " + create_token("keeper")})
    return registry, client


def _as(client, username):
    from app.common.auth import create_token

    client.headers.update({"Authorization": "Bearer " + create_token(username)})


def _audit_rows(dataset_id):
    from app.common.audit import get_audit_events

    rows = [
        event
        for event in get_audit_events(action="resource:view", outcome="denied")
        if str(event.get("resource")) == dataset_id
    ]
    return rows, json.dumps(rows, ensure_ascii=False, default=str)


def test_preview_hides_foreign_and_blank_rows_for_an_authorized_viewer(monkeypatch, tmp_path):
    # 正向对照 + 反证①：keeper 只该看到自己部门的行；摘掉行级过滤，下面两枚令牌
    # 会重现在 200 正文里 -> 这一枚与 A 类格同时转红。
    _registry, client = _wire(monkeypatch, tmp_path, MIXED_CSV)
    _as(client, "keeper")
    response = client.get("/api/v1/data-files/consolidated.csv/preview")
    assert response.status_code == 200
    body = response.json()
    payload = json.dumps(body, ensure_ascii=False, default=str)
    assert OWN_TOKEN in payload, "本人部门的行被误删：绿就成了空转"
    assert FOREIGN_TOKEN not in payload, "反证①：别部门的行仍从预览泄漏"
    assert BLANK_TOKEN not in payload, "反证①：空部门的行没按 fail-closed 藏起来"
    assert body["row_scope"]["rows_in"] == 3
    assert body["row_scope"]["rows_visible"] == 1
    assert body["row_scope"]["code"] == "", "有部分可见行时不该报成整体拒绝"


def test_preview_that_hides_every_row_says_rows_exist_but_denied(monkeypatch, tmp_path):
    # 反证③（预览侧）：文件能开、一行都不给时，返回体必须明说「存在但无权」。退回
    # 空列表 / 只当 R170 空表标记，row_scope.code 就不是 row_scope_denied -> 这一枚红。
    _registry, client = _wire(monkeypatch, tmp_path, ALL_FOREIGN_CSV)
    _as(client, "keeper")
    body = client.get("/api/v1/data-files/consolidated.csv/preview").json()
    assert body["rows"] == []
    assert body["row_scope"]["code"] == "row_scope_denied", "有但不能看被退回了空列表"
    assert body["row_scope"]["rows_in"] > 0
    assert body["row_scope"]["rows_visible"] == 0
    assert "可见范围" in body["row_scope"]["message"]
    assert FOREIGN_TOKEN not in json.dumps(body, ensure_ascii=False, default=str)


def test_preview_row_denial_is_audited_without_leaking_body(monkeypatch, tmp_path):
    # 反证②（预览侧）：摘掉拒绝审计 -> 查不到 -> 红；往审计塞正文 -> 命中令牌 -> 红。
    from app.common.audit import clear_audit_events

    registry, client = _wire(monkeypatch, tmp_path, ALL_FOREIGN_CSV)
    dataset_id = registry.get_active_by_filename("consolidated.csv").dataset_id
    clear_audit_events()
    _as(client, "keeper")
    client.get("/api/v1/data-files/consolidated.csv/preview")
    rows, blob = _audit_rows(dataset_id)
    assert rows, "反证②：行级拒绝没落既有审计通路"
    assert rows[0]["reason"] == "row_scope_denied"
    assert rows[0]["resource"] == dataset_id, "审计资源标识该用 dataset_id"
    for secret in (FOREIGN_TOKEN, OWN_TOKEN, BLANK_TOKEN):
        assert secret not in blob, "反证②：审计里混进了数据正文"


def test_catalog_names_files_you_cannot_open_instead_of_an_empty_lie(monkeypatch, tmp_path):
    # 正向对照 + 反证③（目录侧）：退回静默 continue -> restricted 键消失
    # （B 类 nodept 格）当场转红；同时不许点名（文件名主干本身是泄漏）。
    _registry, client = _wire(monkeypatch, tmp_path, MIXED_CSV)
    _as(client, "keeper")
    keeper = client.get("/api/v1/data-files").json()
    assert [item["filename"] for item in keeper["files"]] == ["consolidated.csv"]
    assert "restricted" not in keeper, "看得到全部时不该凭空造拒绝"

    _as(client, "xdept")
    xdept = client.get("/api/v1/data-files").json()
    assert xdept["files"] == [], "被拒文件不许混进可访问列表"
    restricted = xdept.get("restricted")
    assert restricted, "反证③：目录把『有但你不能看』退回了空列表假话"
    assert restricted["count"] == 1
    assert "department_scope_denied" in restricted["reason_codes"]
    assert "可见范围" in restricted["message"]
    assert "consolidated" not in json.dumps(restricted, ensure_ascii=False, default=str)


def test_catalog_denial_is_audited_without_leaking_body(monkeypatch, tmp_path):
    # 反证②（目录侧）：文件级被拒也要落审计，只放主体 / dataset_id / 判定结果。
    from app.common.audit import clear_audit_events

    registry, client = _wire(monkeypatch, tmp_path, MIXED_CSV)
    dataset_id = registry.get_active_by_filename("consolidated.csv").dataset_id
    clear_audit_events()
    _as(client, "xdept")
    client.get("/api/v1/data-files")
    rows, blob = _audit_rows(dataset_id)
    assert rows, "反证②：目录的文件级拒绝没落审计"
    assert rows[0]["reason"] == "department_scope_denied"
    assert rows[0]["resource"] == dataset_id
    for secret in (FOREIGN_TOKEN, OWN_TOKEN, BLANK_TOKEN):
        assert secret not in blob, "反证②：审计里混进了数据正文"
    assert "consolidated.csv" not in blob, "审计资源标识该用 dataset_id，不该是文件名"


def test_cross_department_file_is_still_a_403_not_a_row_scope_field(monkeypatch, tmp_path):
    # 判据①分层：文件级拒绝走 403 + policy 原因码，不许被塞进行级 row_scope 那一层。
    _registry, client = _wire(monkeypatch, tmp_path, MIXED_CSV)
    _as(client, "xdept")
    response = client.get("/api/v1/data-files/consolidated.csv/preview")
    assert response.status_code == 403
    assert response.json()["detail"] == "department_scope_denied"


def test_administrator_still_sees_every_row_and_is_not_a_bypass_channel(monkeypatch, tmp_path):
    # 判据①：admin 豁免不许改坏（仍看全部行），也不许放大成绕过行级却谎报拒绝的通道。
    _registry, client = _wire(monkeypatch, tmp_path, MIXED_CSV)
    _as(client, "admin")
    body = client.get("/api/v1/data-files/consolidated.csv/preview").json()
    payload = json.dumps(body, ensure_ascii=False, default=str)
    assert body["row_scope"]["rows_visible"] == body["row_scope"]["rows_in"] == 3
    assert body["row_scope"]["code"] == "", "admin 全可见却被说成拒绝"
    for token in (OWN_TOKEN, FOREIGN_TOKEN, BLANK_TOKEN):
        assert token in payload, "admin 豁免被改坏：某一部门行不在了"


def test_empty_and_unregistered_stay_honest_without_fake_refusals(monkeypatch, tmp_path):
    # 判据③分类守卫：真没有 / 未登记 不能被冒充成「有但无权」。
    _registry, client = _wire(monkeypatch, tmp_path, MIXED_CSV)
    (tmp_path / "legacy.csv").write_text(MIXED_CSV, encoding="utf-8")
    _as(client, "keeper")
    body = client.get("/api/v1/data-files").json()
    assert [item["filename"] for item in body["files"]] == ["consolidated.csv"]
    assert "restricted" not in body, "未登记文件不该被冒充成权限拒绝"
    assert client.get("/api/v1/data-files/legacy.csv/preview").status_code == 404


def test_row_scope_status_classifies_denial_empty_and_partial():
    # 分类器本体四张脸钉死：denial / 空表 / 非部门维度整体清空 / 部分可见各归各码，
    # 且「码」与「人话」必须同源——说不出因由的那一支，两句都不许有。
    from app.api.v1 import data

    denial = data._row_scope_status(
        {
            "rows_in": 5,
            "rows_visible": 0,
            "reason_code": "department_scope",
            "rows_hidden_by_department": 5,
            "rows_hidden_blank_department": 2,
            "rows_hidden_account_department": 0,
            "account_department": DEPT_OWN,
        }
    )
    assert denial["code"] == data.ROW_SCOPE_DENIED
    assert "可见范围" in denial["message"], "反证③：拒绝没有说话"
    empty = data._row_scope_status(
        {"rows_in": 0, "rows_visible": 0, "reason_code": "department_scope"}
    )
    assert empty["code"] == "", "空表要交给 R170 的 empty 标记，不许冒充权限"
    assert "message" not in empty, "本来就没有行，却写了一句权限话"
    hidden = data._row_scope_status(
        {
            "rows_in": 5,
            "rows_visible": 0,
            "reason_code": "department_column_missing",
            "rows_hidden_by_department": 0,
        }
    )
    assert hidden["code"] == data.NO_VISIBLE_ROWS, "非部门维度的整体清空不替它下结论"
    assert "message" not in hidden, "判据源空手回去，这里就不许有文案"
    partial = data._row_scope_status(
        {
            "rows_in": 5,
            "rows_visible": 2,
            "reason_code": "department_scope",
            "rows_hidden_by_department": 3,
        }
    )
    assert partial["code"] == ""


def test_row_scope_never_blames_the_department_dimension_for_another_ones_clearing():
    """R62 打回过的缺陷在预览这一路的镜像。

    reason 名字听着像「部门口径拒绝」，但部门维度一行都没藏过（整帧是被未裁的密级维度
    清空的）⇒ 只许说「没有可见行」。本树第一版在这里自己抄了一张 reason→码 表、只看
    rows_in/rows_visible 就下结论，这一枚当场砍红；现在码由 tools.py 唯一的判据源给出。
    """
    from app.api.v1 import data

    for reason_code in ("department_scope", "legacy_open_department_scope"):
        status = data._row_scope_status(
            {
                "rows_in": 2,
                "rows_visible": 0,
                "reason_code": reason_code,
                "rows_after_clearance": 0,
                "rows_hidden_by_department": 0,
                "rows_hidden_blank_department": 0,
                "rows_hidden_account_department": 0,
                "account_department": DEPT_OWN,
            }
        )
        assert status["code"] == data.NO_VISIBLE_ROWS, (reason_code, status)
        assert "message" not in status, (reason_code, status)


def test_the_two_public_codes_stay_bolted_to_the_translation_layer():
    """本层只借用码，不另立判据：两枚字符串必须与 tools.py 的唯一出处同值。

    这里改字面量、或 tools.py 改名而这里没跟上，「拒绝才落审计」那次比较就会静默失效，
    这一枚先红。
    """
    from app.agents import tools
    from app.api.v1 import data

    assert data.ROW_SCOPE_DENIED == tools._ROW_SCOPE_DENIED_CODE
    assert data.NO_VISIBLE_ROWS == tools._NO_VISIBLE_ROWS_CODE


def test_preview_without_any_principal_fails_closed(monkeypatch, tmp_path):
    """没有主体不是超级通道：一行都不给，且照样说「有但不能看」（判据①）。

    生产里 `_authorized_dataset` 会先回 401，这条钉的是直接调用那一层。把取值改回
    `principal.role` 当场 AttributeError；改成放行整帧则 rows_visible 变成 2 并且
    FOREIGN_TOKEN 回到正文里 —— 两种偷懒都砍得红。
    """
    import asyncio
    from types import SimpleNamespace

    import pandas
    from fastapi import Response

    from app.api.v1 import data

    stored = tmp_path / "noprincipal.csv"
    stored.write_text(
        f"部门,note\n{DEPT_FOREIGN},{FOREIGN_TOKEN}\n{DEPT_FOREIGN},second-row\n",
        encoding="utf-8",
    )
    record = SimpleNamespace(
        dataset_id="ds-noprincipal",
        version_id="dv-noprincipal",
        filename="noprincipal.csv",
        storage_path=str(stored),
        classification=1,
    )
    monkeypatch.setattr(data, "_authorized_dataset", lambda request, filename, action: record)
    monkeypatch.setattr(data, "load_excel", lambda path: pandas.read_csv(path))

    body = asyncio.run(data.preview_data_file("noprincipal.csv", request=None, response=Response()))

    assert body["row_scope"]["code"] == data.ROW_SCOPE_DENIED, body["row_scope"]
    assert body["row_scope"]["rows_in"] == 2
    assert body["row_scope"]["rows_visible"] == 0
    assert FOREIGN_TOKEN not in json.dumps(body, ensure_ascii=False, default=str)


def test_a_header_only_file_keeps_the_r170_empty_profile_through_the_row_filter(monkeypatch, tmp_path):
    """§3 护栏：只有一行表头的表，R170 交回的是完整空表画像 + empty 标记。

    行级过滤插进预览之后，这一支一个字节都不许变：把它改回「数据为空」的 error 形状，
    或者因为「零行可见」就冒充成 row_scope_denied，都当场砍红（rows_in == 0 那一支
    本来就不该由权限层说话）。
    """
    _registry, client = _wire(monkeypatch, tmp_path, "部门,note\n")
    _as(client, "keeper")
    response = client.get("/api/v1/data-files/consolidated.csv/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["empty"] is True, "R170 的空表标记被改回去了"
    assert "error" not in body["profile"], f"空表被说成了错误：{body['profile']}"
    assert body["profile"]["rows"] == 0
    assert body["row_scope"]["code"] == "", "表本来就是空的，不许冒充权限拒绝"
    assert "message" not in body["row_scope"]
