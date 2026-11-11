# -*- coding: utf-8 -*-
r"""R404 判据 c + d · 判定过程必须落审计台账，且在册那枚桩必须是真台账行的形状。

d（审计）：这条腿今天原本一条 `record_audit` 都不写——拒答只在屏上留了一句 403，机器上查不到
「谁探过这份文档的版本」。落码之后与 `_authorize_document_request` 共用同一条唯一通路：动词按门分
（这一扇门记它自己判定用的 `resource:view`），allowed / denied 各一笔，带 `resource_scope` 与
`policy_version`，文档正文一个字都不进台账，也不许另立第二枚日志器。
`tests/test_r404_version_history_judges_before_it_lists.py` 的 K2／K3／K4／K5／K6 是那五把结构刀；
本件量的是行为：把通路摘掉，账上必须一行都不长（长了就是第二套形状）。

c（桩）：`tests/test_document_route_authorization.py` 那条跨部门 403 用例的桩，换符号以后必须同时
补上 `storage_path`——真台账每行都有这一列（`_SELECT_COLUMNS` 里写着），桩不给就是假形状；
而这条用例在缺列时**照样会绿**（判定读的是 owner_id／department／classification），所以必须有一枚
单独的钉盯着它。`test_teeth_c_a_stub_without_a_storage_path_goes_red` 是这枚钉的自证：把那一行从
内存副本里删掉，量具必须立刻判红。被跟踪文件进门取 sha、出门比 sha，本件一个字都不写。
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
from pathlib import Path

import pytest
from fastapi import HTTPException

REPO = Path(__file__).resolve().parents[1]
AUTH_TEST_REL = "tests/test_document_route_authorization.py"
VERSIONS_TEST = "test_document_version_history_denies_cross_department_principal"
NAME = "finance.txt"
VERBATIM_403 = "response.status_code == 403"


def _sha16(relative: str) -> str:
    return hashlib.sha256((REPO / relative).read_bytes()).hexdigest()[:16]


def _chat():
    from app.api.v1 import chat

    return chat


def _principal(department: str, username: str, role: str = "manager"):
    from app.agents.contracts import Principal

    return Principal.from_user(
        {"id": username, "username": username, "role": role, "department": department}
    )


def _request(principal):
    return type(
        "Request",
        (),
        {
            "state": type(
                "State", (), {"principal": principal, "username": principal.username}
            )()
        },
    )()


def _ledger_row() -> dict:
    """一枚真台账行的形状：列齐，且那份文件压根不在盘上（403 那张脸不许由文件在不在决定）。"""
    return {
        "filename": NAME,
        "version": 7,
        "classification": 2,
        "department": "finance",
        "storage_path": "finance__v7.txt",
        "owner_id": "finance-owner",
        "size_bytes": 4,
        "parse_status": "ready",
    }


@pytest.fixture()
def journal(monkeypatch):
    """包一层 chat 模块的 record_audit：原实现照调，顺手取位置参数与事件（沿 R179 的取证件形状）。"""
    import app.common.audit as audit_module

    chat = _chat()
    original = audit_module.record_audit
    rows: list[dict] = []

    def _record(principal, action, outcome, resource="", reason="", **kwargs):
        event = original(principal, action, outcome, resource, reason, **kwargs)
        rows.append(
            {
                "action": str(action),
                "outcome": str(outcome),
                "resource": str(resource),
                "reason": str(reason),
                "event": event,
            }
        )
        return event

    def _stub_reads(_name):
        return dict(_ledger_row())

    monkeypatch.setattr(chat, "latest_document_version", _stub_reads)
    monkeypatch.setattr(chat, "list_document_versions", lambda _name: [dict(_ledger_row())])
    monkeypatch.setattr(chat, "record_audit", _record)
    return rows


def _drive(principal) -> tuple:
    chat = _chat()
    try:
        return 200, asyncio.run(chat.document_version_history(NAME, _request(principal)))
    except HTTPException as raised:
        return raised.status_code, raised.detail


def _rows_for(journal: list[dict], outcome: str, resource: str = NAME) -> list[dict]:
    return [row for row in journal if row["resource"] == resource and row["outcome"] == outcome]


# ==================== 判据 d：判定过程落的这笔记在哪 ====================


def test_the_denied_judgment_writes_exactly_one_journal_row(journal):
    code, detail = _drive(_principal("hr", "hr-manager"))

    assert code == 403, (code, detail)
    rows = _rows_for(journal, "denied")
    assert len(rows) == 1, "这条腿的拒答在台账里不是恰好一笔：%s" % journal
    row = rows[0]
    assert row["action"] == "resource:view", row
    assert row["reason"] == detail, (row["reason"], detail)


def test_the_denied_row_carries_the_scope_and_policy_version_of_the_decided_row(journal):
    _drive(_principal("hr", "hr-manager"))
    row = _rows_for(journal, "denied")[0]
    event = row["event"]

    assert event["resource_scope_source"] == "explicit", event["resource_scope_source"]
    assert event["resource_scope"]["department"] == "finance", event["resource_scope"]
    assert event["resource_scope"]["owner_id"] == "finance-owner", event["resource_scope"]
    assert event["policy_version"], "留账没带 policy_version：这一笔日后无法复算"


def test_the_allowed_judgment_writes_one_row_too(journal):
    code, payload = _drive(_principal("finance", "fin-manager"))

    assert code == 200, payload
    rows = _rows_for(journal, "allowed")
    assert len(rows) == 1, "放行那一支在台账里不是恰好一笔：%s" % journal
    assert rows[0]["action"] == "resource:view", rows[0]


def test_teeth_d_the_journal_is_the_only_channel(journal, monkeypatch):
    """摘掉通路：账必须一行都不长，而码还是那个码——长了就是存在第二套留账形状。"""
    chat = _chat()
    _drive(_principal("hr", "hr-manager"))
    assert len(_rows_for(journal, "denied")) == 1, journal

    monkeypatch.setattr(chat, "record_audit", lambda *args, **kwargs: {})
    before = len(journal)
    code, detail = _drive(_principal("hr", "hr-manager"))
    assert code == 403, (code, detail)
    assert len(journal) == before, "摘掉通路还在长账：本文件里有第二枚日志器"


# ==================== 判据 c：在册那枚桩的诚实性 ====================


def _versions_stub_shape(source: str) -> tuple:
    """从在册授权件里现读那条 403 用例：patch 的符号名 + 桩交回的行有哪些键 + 那枚 verbatim 断言。"""
    tree = ast.parse(source, filename=AUTH_TEST_REL)
    fn = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == VERSIONS_TEST
        ),
        None,
    )
    assert fn is not None, "%s 不在 %s 里了" % (VERSIONS_TEST, AUTH_TEST_REL)

    patches = []
    for call in ast.walk(fn):
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "setattr"
            and len(call.args) == 3
            and isinstance(call.args[1], ast.Constant)
            and isinstance(call.args[2], ast.Lambda)
            and isinstance(call.args[2].body, ast.Dict)
        ):
            keys = {
                str(ast.unparse(key)).strip("\"'")
                for key in call.args[2].body.keys
                if key is not None
            }
            patches.append((call.args[1].value, keys))
    assert len(patches) == 1, "这条腿的桩不再是恰好一枚 setattr：%s" % patches

    asserted = [
        ast.unparse(node.test)
        for node in ast.walk(fn)
        if isinstance(node, ast.Assert)
    ]
    return patches[0], VERBATIM_403 in asserted


def _assert_stub_is_a_real_ledger_row(source: str) -> None:
    (symbol, keys), verbatim = _versions_stub_shape(source)
    assert symbol == "latest_document_version", (
        "那枚 403 用例还打在 %s 上：判定腿换了单行读，旧 patch 拦不到 ⇒ 404 假红" % symbol
    )
    assert "storage_path" in keys, (
        "桩没有 storage_path 而用例仍会绿（判定读的是 owner_id/department/classification）："
        "那是假台账行形状，本单判据 c 不容 %s" % sorted(keys)
    )
    assert verbatim, "那枚 `assert response.status_code == 403` 被人改过了"


def test_the_booked_authorization_stub_is_a_real_ledger_row():
    relative = AUTH_TEST_REL
    before = _sha16(relative)
    _assert_stub_is_a_real_ledger_row((REPO / relative).read_text(encoding="utf-8"))
    assert _sha16(relative) == before


def test_teeth_c_a_stub_without_a_storage_path_goes_red():
    """量具自证：把桩里那一行删掉（用例本身不会因此变红），这枚钉必须立刻判红。"""
    source = (REPO / AUTH_TEST_REL).read_text(encoding="utf-8")
    # 刀口必须锚到行首：只写 12 个空格会被更深缩进（16 空格）的那五行含住，
    # 切偏了就是一把看不见的假刀——本单实测踩过一次，所以把它写成钉。
    fragment = '\n            "storage_path": stored_file,'
    assert source.count(fragment) == 1, source.count(fragment)
    mutated = source.replace(fragment, "", 1)
    assert mutated != source, "锚点切偏：这一刀没落到桩上"
    with pytest.raises(AssertionError) as raised:
        _assert_stub_is_a_real_ledger_row(mutated)
    assert "storage_path" in str(raised.value), raised.value

    # 反向自证：把符号换回旧名（拦不到判定腿），同一枚钉也必须判红
    renamed = source.replace('"latest_document_version",', '"list_document_versions",', 1)
    assert renamed != source, "锚点切偏：符号名那一刀没落到桩上"
    with pytest.raises(AssertionError) as renamed_raised:
        _assert_stub_is_a_real_ledger_row(renamed)
    assert "list_document_versions" in str(renamed_raised.value), renamed_raised.value
