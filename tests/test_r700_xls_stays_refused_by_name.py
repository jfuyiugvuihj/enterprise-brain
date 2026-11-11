"""R700 判据④④ · 遗留二进制 .xls 明确拒绝、给出可读原因码，且这一格不许靠加依赖蒙过去。

工单原话：.xls 是故意不做——openpyxl 读不了遗留二进制，xlrd 不在本仓依赖里，这一句必须原样
保留在交付里，不许为过判据偷偷加依赖（依赖变动属业主侧）。本件把这句话落成四格可失败的钉：

① 名字这一格：.xls 既不在 app/documents/file_security.py 的知识库字典里，也不在
   app/tools/excel.py 现算出来的数据收口名单里。两本闸门口径不同（「这是不是知识库类型」与
   「这台机器开不开得动它」），本单只把第二本没管的前三件并进第一本，两本都不收 .xls。
② 理由这一格：白名单上方那段注释里，那句「为什么故意不做」必须逐字还在；同时它不许再留
   「upload-excel ... does not read this dict」那半句假话（判据②的治法就写在注释上）。
③ 答复这一格：真 OLE2 二进制走路由拿到的是 400 + 字典形状 {code, message}，message 要说清
   不支持的是哪一枚格式、下一步做什么（另存为 .xlsx 或 .csv）；一枚字节都不许落盘，知识库
   那条腿一枚块都不许被叫到——入库闸门是武装着的（_Brain 把模型发现的在册离线桩换成「服务
   答得出、且那枚 embedding 模型在」），所以「没写库」只能归因于这一格的拒绝。
④ 反证那一格：把 .xls 塞回允许名册，①那枚钉当场红（判据④④要求的形状就是这句），而路由
   仍然拒——拒它的是数据读腿那道独立闸门。两枚钉子各自咬人，谁也别想把 .xls 混进 V2。

零新依赖那一格也钉死：pyproject.toml 与 uv.lock 里都不许出现 xlrd（本单亦不许改这两枚文件，
交工纸另附 git diff --numstat 的空读数）。

全程离线：不连 PostgreSQL、不起服务、不开宿主模型端口、不打模型。夹具与盘面复用同族在册件
tests/test_r700_dataset_upload_reads_the_document_dict.py 的同一副 _Brain（先例：test_r625 从
test_r60 借装配台与替身），本件不另起一套平行实现。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.documents import file_security
from app.tools.excel import accepted_data_file_extensions

from test_r700_dataset_upload_reads_the_document_dict import (
    LEGACY_XLS_BYTES,
    OWNER,
    _Brain,
)

REPO = Path(__file__).resolve().parents[1]
SECURITY_PY = REPO / "app" / "documents" / "file_security.py"
PYPROJECT = REPO / "pyproject.toml"
UV_LOCK = REPO / "uv.lock"

XLS_NAME = "预算明细表.xls"
#: 注释里那枚后缀带着 markdown 反引号，用 chr(96) 拼出来，免得本件自己的字符串长得像判定。
BACKTICK = chr(96)
#: 工单点名要原样保留的那一句：.xls 是故意不做，不是漏做。
LEGACY_REASON_SENTENCE = (
    BACKTICK + ".xls" + BACKTICK
    + " is deliberately absent: openpyxl cannot read the legacy binary format "
    "and xlrd is not a direct dependency of this repository."
)
#: 判据②要治的那半句假话（改口之后不许再回来）。
RETIRED_CLAIM = "does not read this dict"
#: 注释里必须点名的三枚共用出口——判据②「并进同一本字典」的书面凭据。
SHARED_EXITS = (
    "sanitize_upload_filename",
    "inspect_dataset_upload",
    "guard_dataset_name_conflict",
)


def _comment_block_above_the_whitelist() -> str:
    """白名单上方那段注释，折行摊平成一段——换行落在哪一格不许影响判定。"""
    header = SECURITY_PY.read_text(encoding="utf-8").split("_ALLOWED_TYPES = {", 1)[0]
    lines = [
        line.lstrip("#").lstrip()
        for line in header.splitlines()
        if line.lstrip().startswith("#")
    ]
    return " ".join(" ".join(lines).split())


def _whitelist_names() -> set[str]:
    return set(file_security._ALLOWED_TYPES)


# ==================== ① 名字：两本闸门都不收 .xls ====================


def test_xls_is_absent_from_both_admission_lists() -> None:
    assert ".xls" not in _whitelist_names(), sorted(_whitelist_names())
    assert ".xls" not in accepted_data_file_extensions()
    assert {".xlsx", ".csv"} <= _whitelist_names(), "字典连电子表格都不收了：本件的尺子悬空"
    assert {".xlsx", ".csv"} <= set(accepted_data_file_extensions())


def test_both_upload_legs_answer_the_same_code_for_the_same_file() -> None:
    """判据②「同一份文件在两条上传路上答同一个码」的正身：两枚出口走的是同一处判定。"""
    with pytest.raises(file_security.UploadSecurityError) as knowledge_leg:
        file_security.inspect_upload_header(XLS_NAME, LEGACY_XLS_BYTES)
    with pytest.raises(file_security.UploadSecurityError) as dataset_leg:
        file_security.inspect_dataset_upload(XLS_NAME, LEGACY_XLS_BYTES)

    assert str(knowledge_leg.value) == str(dataset_leg.value)
    assert knowledge_leg.value.code == dataset_leg.value.code == "unsupported_file"


# ==================== ② 理由：那句「故意不做」逐字还在 ====================


def test_the_reason_the_legacy_format_is_out_stays_written_verbatim() -> None:
    block = _comment_block_above_the_whitelist()

    assert LEGACY_REASON_SENTENCE in block, (
        "工单点名要原样保留的那句改口了，.xls 的拒绝从此没有书面理由：" + block[-400:]
    )


def test_the_comment_no_longer_claims_the_dataset_route_reads_a_different_dict() -> None:
    """判据②的治法写在注释上：那半句「不读这本字典」撤掉了，且改口点名三枚共用出口。"""
    block = _comment_block_above_the_whitelist()

    assert RETIRED_CLAIM not in block, "那半句假话还挂在白名单上方：" + block[-400:]
    for exit_name in SHARED_EXITS:
        assert exit_name in block, "注释没点名共用出口：" + exit_name


def test_refutation_renaming_the_shared_exits_goes_red_on_the_comment_pin() -> None:
    """反证：注释里不再点名某一枚共用出口，②那一格就该红——它认的是名字，不是感受。"""
    block = _comment_block_above_the_whitelist()

    for exit_name in SHARED_EXITS:
        stripped = block.replace(exit_name, "另一枚什么函数")
        assert exit_name not in stripped, exit_name
        assert RETIRED_CLAIM not in stripped, "反证把假话又拼回来了：这不算红"


# ==================== ③ 答复：具名拒绝、零落盘、零入库 ====================


def test_the_route_refuses_xls_with_a_readable_code_and_indexes_nothing(monkeypatch, tmp_path) -> None:
    """真 OLE2 二进制：400 + 具名拒绝，落盘、登记表、知识库三条腿都没被动过。"""
    brain = _Brain(monkeypatch, tmp_path)

    response = brain.upload(XLS_NAME, LEGACY_XLS_BYTES)

    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, dict) and sorted(detail) == ["code", "message"], detail
    assert detail["code"] == "unsupported_file", "原因码换了形状：errcodes.js 会读不到"
    assert "另存为" in detail["message"] and ".xlsx" in detail["message"], detail["message"]
    assert list(brain.data_dir.iterdir()) == [], "读不动的遗留格式已经落进 DATA_DIR"
    assert brain.leg.add_document_calls == [], "被拒的 .xls 把知识库那条腿叫醒了"
    assert brain.bm25_calls == []
    assert brain.registry.get_active_by_filename(XLS_NAME) is None


def test_the_refusal_never_blames_the_customer_with_jargon(monkeypatch, tmp_path) -> None:
    """拒绝里不许出现把责任推回客户的黑话，也不许出现异常类名（那是 500 的形状）。"""
    brain = _Brain(monkeypatch, tmp_path)

    response = brain.upload(XLS_NAME, LEGACY_XLS_BYTES)
    detail = response.json()["detail"]

    for jargon in ("InvalidFileException", "ModuleNotFoundError", "ImportError",
                   "internal_error", "系统异常", "未知错误", "内部错误", "请重试"):
        assert jargon not in detail["message"], jargon
    assert response.status_code == 400, "这一格是拒绝，不是没登录（401）也不是没权限（403）"
    assert OWNER  # 盘面用有 upload 权限且有部门的账号跑的


# ==================== ④ 反证：把 .xls 塞回名册，①那枚钉必须红 ====================


def test_refutation_xls_back_in_the_dict_goes_red_on_the_name_pin(monkeypatch, tmp_path) -> None:
    """判据④④要求的形状：.xls 一进允许名册，名字那枚钉立刻不成立；路由仍被第二道闸挡住。"""
    monkeypatch.setitem(file_security._ALLOWED_TYPES, ".xls", ("application/vnd.ms-excel", ()))

    assert ".xls" in _whitelist_names()
    # ①那枚钉此刻必须红：把它的判据原话写成可执行的一句，红的就是这一句。
    with pytest.raises(AssertionError):
        assert ".xls" not in _whitelist_names()
    # 字典这一格放开之后，inspect 那一格也放开了——剩下那一手 400 只能来自数据读腿那道闸。
    assert file_security.inspect_dataset_upload(XLS_NAME, LEGACY_XLS_BYTES).extension == ".xls"
    brain = _Brain(monkeypatch, tmp_path)

    response = brain.upload(XLS_NAME, LEGACY_XLS_BYTES)

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "unsupported_file"
    assert brain.leg.add_document_calls == [], "两道闸全放开才算漏；放开一道不许算过"


# ==================== 零新依赖 ====================


def test_the_legacy_format_costs_no_new_dependency() -> None:
    """为过判据偷偷加 xlrd 是工单明令禁止的一格：两枚依赖文件里都不许出现它。"""
    declared = PYPROJECT.read_text(encoding="utf-8").split("dependencies = [", 1)[1]

    assert "xlrd" not in declared, "pyproject 的依赖里冒出了 xlrd"
    assert "xlrd" not in UV_LOCK.read_text(encoding="utf-8"), "uv.lock 里冒出了 xlrd"
    assert "openpyxl" in declared, "在册的读引擎自己不见了"
