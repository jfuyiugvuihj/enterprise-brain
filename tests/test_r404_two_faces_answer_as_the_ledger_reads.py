# -*- coding: utf-8 -*-
r"""R404 判据 b · 两张脸按现读认下来：无台账行先 404，台账有行而文件已没仍走判定。

落码前那条腿只有一张脸的形状是：判定输入取自全量历史的第一行，于是「文件还在不在」这件事
悄悄进了权限判定——`app/api/v1/chat.py` 里那枚 `_latest_document_version()` 会逐行
`os.path.exists`，台账有行而盘上文件已没时它会掉进 glob／直读兜底分支，交回的行只剩
`filename` 与 `storage_path`，`owner_id`／`department`／`classification` 全 None ⇒
`resource_scope_missing` ⇒ 403（或压根兜不到 ⇒ 404）。跟进单 §126 第二节把这两张脸写死：

  * 台账有行而文件已没 ⇒ **判定仍读那一行**（403 那张脸不许被翻成 404，也不许由文件在不在决定）；
  * 无台账行 ⇒ **判定之前先 404**（`resource_not_found`，一次判定都不许发生）。

在册那枚 `tests/test_document_route_authorization.py::test_document_version_history_denies_cross_department_principal`
的 `assert response.status_code == 403` 一字未动，由本目录的
`tests/test_r404_the_judgment_journals_and_the_stub_is_honest.py` 连桩一起钉着。
`test_teeth_b_the_ruler_fires_on_flipped_faces` 是量具自证：把任一张脸翻掉，同一把尺必须判红。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

REPO = Path(__file__).resolve().parents[1]
NAME = "policy.txt"


def _chat():
    from app.api.v1 import chat

    return chat


def _principal(department: str, username: str = "u", role: str = "manager"):
    from app.agents.contracts import Principal

    return Principal.from_user(
        {"id": username, "username": username, "role": role, "department": department}
    )


def _request(principal):
    """只给路由真读的那一格：`principal_from_request` 只问 `request.state.principal`。"""
    return type(
        "Request",
        (),
        {
            "state": type(
                "State", (), {"principal": principal, "username": getattr(principal, "username", "")}
            )()
        },
    )()


def _ledger_row(tmp_path, *, exists: bool):
    from app.documents.catalog import build_storage_name

    stored = tmp_path / build_storage_name(NAME, 7)
    if exists:
        stored.write_text("body", encoding="utf-8")
    return {
        "filename": NAME,
        "version": 7,
        "classification": 2,
        "department": "finance",
        "storage_path": str(stored),
        "owner_id": "finance-owner",
        "size_bytes": 4,
        "parse_status": "ready",
    }


def _drive(monkeypatch, row, principal, log=None):
    """跑真路由：读数、判定、留账各留下形状，返回 (状态码, detail, 判定次数)。"""
    chat = _chat()
    log = [] if log is None else log
    decisions: list = []

    def _single(_name):
        log.append("single")
        return None if row is None else dict(row)

    def _full(_name):
        log.append("list")
        return [] if row is None else [dict(row)]

    original = chat._document_authorization_decision

    def _spy(principal_arg, filename, version, action):
        decisions.append(version)
        return original(principal_arg, filename, version, action)

    def _no_file_asking_reader(_name):
        raise AssertionError("版本历史这条腿去问「文件还在不在」了：那张 403 的脸交给磁盘说话")

    monkeypatch.setattr(chat, "latest_document_version", _single)
    monkeypatch.setattr(chat, "list_document_versions", _full)
    monkeypatch.setattr(chat, "_document_authorization_decision", _spy)
    monkeypatch.setattr(chat, "_latest_document_version", _no_file_asking_reader)
    monkeypatch.setattr(chat, "record_audit", lambda *args, **kwargs: {})

    try:
        payload = asyncio.run(chat.document_version_history(NAME, _request(principal)))
    except HTTPException as raised:
        return raised.status_code, raised.detail, len(decisions), log
    return 200, payload, len(decisions), log


def _faces_are_the_booked_ones(file_missing: int, no_row: int, judged_without_row: bool) -> bool:
    return bool(file_missing == 403 and no_row == 404 and judged_without_row is False)


def test_a_ledger_row_whose_file_is_gone_is_still_the_row_the_judgment_reads(monkeypatch, tmp_path):
    """脸一：台账有行、盘上那份文件已经没了 ⇒ 判定照旧读那一行，跨部门答 403。"""
    row = _ledger_row(tmp_path, exists=False)
    code, detail, judged, log = _drive(monkeypatch, row, _principal("hr", "hr-manager"))

    assert code == 403, "文件不见了就把人当成「没这份文档」答 404：那张脸翻了（实测 %s/%s）" % (code, detail)
    assert detail != "resource_not_found", detail
    assert judged == 1, judged
    assert log == ["single"], "判定之前除了一行还读过别的：%s" % log


def test_the_same_row_still_answers_the_in_scope_principal_with_its_history(monkeypatch, tmp_path):
    """同一枚缺文件的行，本人那一侧仍然读得出版本历史：判定与响应都不问文件在不在。"""
    row = _ledger_row(tmp_path, exists=False)
    code, payload, judged, log = _drive(monkeypatch, row, _principal("finance", "fin-manager"))

    assert code == 200, payload
    assert [row_["version"] for row_ in payload["versions"]] == [7], payload
    assert log == ["single", "list"], log
    # 判定次数 = 这条腿自己那一次 + 响应侧逐行分类那 N 次（_classify_document_rows 复用同一枚谓词，
    # 本单没动它）；关键形状由上面那行 log 说：判定之前只发生过一次读数。
    assert judged == 1 + len(payload["versions"]), (judged, payload)


def test_no_ledger_row_is_answered_404_before_any_judgment(monkeypatch, tmp_path):
    """脸二：台账没行 ⇒ 判定之前先 404，一次判定都不许发生。"""
    code, detail, judged, log = _drive(monkeypatch, None, _principal("finance", "fin-manager"))

    assert code == 404, "无台账行不再先答 404：%s / %s" % (code, detail)
    assert detail == "resource_not_found", detail
    assert judged == 0, "没有台账行却还是进了判定：%d 次" % judged
    assert log == ["single"], log


def test_anonymous_still_answers_401_before_touching_the_store(monkeypatch):
    """401 那张脸不归本单改：principal 不在场时连台账都不该读。"""
    log: list[str] = []
    code, detail, judged, seen = _drive(monkeypatch, {"filename": NAME}, None, log)

    assert code == 401, (code, detail)
    assert detail == "authentication_required", detail
    assert seen == [], "匿名请求读到了台账：%s" % seen


def test_teeth_b_the_ruler_fires_on_flipped_faces():
    """量具自证：任一张脸翻掉，同一把尺必须判红（否则上面三枚绿是假的）。"""
    # 翻第一张脸：把「文件在不在」搬进判定腿（甲方案的形状）⇒ 尺必须判红
    assert not _faces_are_the_booked_ones(404, 404, False), "文件一没就答 404，这张脸翻了而尺没认"
    # 翻第二张脸：判定跑到「有没有这一行」之前 ⇒ 尺必须判红
    assert not _faces_are_the_booked_ones(403, 403, True), "无台账行还先判定，这张脸翻了而尺没认"
