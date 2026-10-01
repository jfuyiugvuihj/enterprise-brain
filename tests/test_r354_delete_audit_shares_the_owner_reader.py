# -*- coding: utf-8 -*-
r"""R354 判据⑤⑥⑦ · delete 那一腿与两处出口同读一枚 helper：审计里无主从此是 null，不是空串。

病灶（基点 `a7ac040` 现取，`app/api/v1/data.py` 的 `delete_data_file`）：R337（`aefa3ce`）给数据集
两处出口（上传回执 / `/preview`）接了同源读法 `_dataset_row_owner_id`，并把 `.owner_id` 直读禁掉；
但 delete 那一腿为了审计载荷仍然直读 `record.owner_id`，把注册表里那枚原始 `""` 原样带走 ——
同一枚遗留无主行，回执答 `null`、审计答 `""`，两本账。

三条判据逐枚对位：

  · 判据⑤：delete 那一腿改走**同一枚** helper，不许新增第二套 owner 读法；R337 那枚 AST 尺子从
    「点名的两枚出口只许一处 helper」升级成「任何读 owner 的路径都必须经它」（升级在
    `tests/test_r337_owner_receipt_on_both_exits.py` 里，只加判不减判）。本件另钉「旧点名表在基点上
    对 delete 那一腿是瞎的」—— 否则这单到底补了什么无从证明。
  · 判据⑥：审计事件的 schema、稳定码词表、delete 的响应形状一律不动。唯一动的是那一格的**值形态**
    （`""` → `null`），本件拿两副世界逐格对账证明别的一格一个字没变。
  · 判据⑦：契约只能文末追加 —— 现取 `git show a7ac040:docs/api/contract-v1.md`，逐字节证明当前文件
    的前 N 字节与它 prefix-identical，再证明 `--numstat` 删除列为 0、`## ` 节标题恰 +1、lone LF 0、
    U+FFFD 0。

四把反证（只落 `tests/_temp_edit_overlay.py` 的影子根，盘上 `data.py` 全程只读，进出各取一次 sha256）：
刀1 退回基点那一形（直读属性）；刀2 就地手搓一套「答案碰巧也对」的第二读法；刀3 为审计那一格现查
一次注册表；刀4 把审计里的字段挪走名。每把逐枚报红名，不报总数。

另登记一条**只报不改**的邻格：`app/common/audit.py::_project_scope`（`:362-365`）投影 resource_scope
时把空串键直接丢掉，所以无主行的审计里 `resource_scope` 至今**没有** `owner_id` 这一格 —— 那是第三本
账，不在本单写域，本件把它的今天钉住，免得下一班有人宣称「审计里无主已全部统一成 null」。
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path

from app.common import audit
from tests import _temp_edit_overlay as overlay
from tests import test_r466_mutation_does_not_leak_into_live_module as r466
from tests.test_r337_owner_receipt_on_both_exits import (
    EXIT_SHAPE,
    LEGACY,
    MINE,
    OWNER_OF,
    _document_rule,
    _preview,
    _request,
    _wire,
    module_owner_read_violations,
    owner_read_shape,
    owner_shape_violations,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_PY = ROOT / "app" / "api" / "v1" / "data.py"
DATA_REL = "app/api/v1/data.py"
CONTRACT = ROOT / "docs" / "api" / "contract-v1.md"
LOADER_PY = ROOT / "app" / "rag" / "loader.py"

#: 本单的基点：那一腿上还写着 `record.owner_id` 的那一份。读 git 对象而不是工作树副本，
#: 否则各 worktree 停在自己的基点上会稳定假绿。
BASE = "a7ac040"

#: 审计载荷里本来该有哪几格（顺序即代码里的顺序）—— 判据⑥：schema 一字不动。
AUDIT_BEFORE_KEYS = ["filename", "owner_id", "department_ids", "classification", "size_bytes"]
#: delete 的响应形状 —— 判据⑥：一个键都不许多、不许多。
DELETE_RESPONSE_KEYS = {"status", "filename", "dataset_id", "file_removed", "record_status"}
#: delete 这一腿能发出去的稳定码 —— 判据⑥：不新增。
DELETE_STABLE_CODES = {"internal_error"}

_ID_RE = re.compile(r"[0-9a-f]{32}")


# ------------------------------------------------------------------ 现取基点那一份


def _base_text(rel: str) -> str:
    raw = subprocess.run(
        ["git", "-C", str(ROOT), "show", "%s:%s" % (BASE, rel)],
        capture_output=True,
        check=True,
    ).stdout
    return raw.decode("utf-8")


def _delivered_source() -> str:
    """当前该算数的那份 `data.py`：窗外是盘上的字，窗内是影子根里的变异体。"""
    return overlay.authoritative_text(DATA_REL)


# ------------------------------------------------------------------ 真叫那一腿


def _delete(data, username: str, filename: str) -> dict:
    return asyncio.run(data.delete_data_file(filename, request=_request(username)))


def _capture_audits(monkeypatch, module) -> list:
    """收下这一腿写的每一条审计（授权判定与收尾各一条），按 reason 取样。"""

    calls: list[dict] = []

    def record(principal, action, outcome, resource="", reason="", **kwargs):
        calls.append(
            {
                "principal": principal.username,
                "action": action,
                "outcome": outcome,
                "resource": resource,
                "reason": reason,
                **kwargs,
            }
        )
        return dict(calls[-1])

    monkeypatch.setattr(module, "record_audit", record)
    return calls


def _completion(calls: list) -> dict:
    picked = [event for event in calls if event["reason"] == "dataset_deleted"]
    assert len(picked) == 1, "收尾审计应当恰有一条，实取 %d：%s" % (len(picked), [e["reason"] for e in calls])
    return picked[0]


# ------------------------------------------------------------------ 反证窗


class _R354Edit(overlay.ShadowEdit):
    """一扇 R354 的反证窗：锚点命中不是恰好一处，变异整片不落影子；文本先过 compile()。"""

    tag = "r354"
    #: 🔴 R466：变异只落影子副本，不 exec 进活模块——见 _window 的说明。
    execs_module = False

    def __init__(self, path: Path, edits) -> None:
        super().__init__(path)
        self.edits = [(old, new) for old, new in edits]

    def mutate(self, text: str) -> str:
        newline = chr(13) + chr(10) if chr(13) + chr(10) in text else chr(10)
        mutated = text
        for old, new in self.edits:
            needle = old.replace(chr(10), newline)
            hits = mutated.count(needle)
            assert hits == 1, "%s 里锚点命中 %d 处（要求恰好 1 处）：%r —— 变异整体不落盘" % (
                self.path.name, hits, old[:70])
            mutated = mutated.replace(needle, new.replace(chr(10), newline), 1)
        compile(mutated, str(self.path), "exec")
        return mutated


#: 交付体里 delete 那一腿的两行（赋值式 + 填格），与两处出口同一形状。
DELIVERED_READ = "\n".join([
    '    owner_id = _dataset_row_owner_id(record)',
    '    before = {',
    '        "filename": record.filename,',
    '        "owner_id": owner_id,',
])
#: 基点那一形：直读属性，无主带着注册表里那枚原始空串（R354 要修的病灶，也是刀1 的靶）。
BASE_READ = "\n".join([
    '    before = {',
    '        "filename": record.filename,',
    '        "owner_id": record.owner_id,',
])
#: 刀2：就地手搓一套「答案碰巧也对」的第二读法 —— 行为绿、尺子必须红。
SECOND_READER = "\n".join([
    '    owner_id = None if not str(record.owner_id or "").strip() else str(record.owner_id)',
    '    before = {',
    '        "filename": record.filename,',
    '        "owner_id": owner_id,',
])
#: 刀3：为审计那一格现查一次注册表（多开一次查询，且来源不再是手上那枚 record）。
FRESH_LOOKUP = "\n".join([
    '    owner_id = _dataset_row_owner_id(dataset_registry.get_active_by_filename(record.filename))',
    '    before = {',
    '        "filename": record.filename,',
    '        "owner_id": owner_id,',
])
#: 刀4：把审计里的字段挪走名（schema 被动 —— 判据⑥点名禁止）。
RENAMED_FIELD = "\n".join([
    '    owner_id = _dataset_row_owner_id(record)',
    '    before = {',
    '        "filename": record.filename,',
    '        "owner": owner_id,',
])


@contextmanager
def _window(edits):
    """开一扇窗：变异只落影子副本，窗内只把变了的那几枚顶层绑定装进 app.api.v1.data，出门逐枚装回。

    🔴 R466：旧姿势 execs_module=True 会把变异后的整份码体 exec 进活模块（本席现取 19 枚顶层把手
    全部换新身体），且那次 exec 在 __enter__ 里、_WINDOWS.append 之后，它一炸就没有 __exit__ 还原。
    姿势件与 test_r457_audit_retention_execution_leg.py:169-242 同一族。
    """
    module = overlay.module_of(DATA_REL)
    assert module is not None, "app.api.v1.data 还没被导入，改绑无处可落"
    with _R354Edit(DATA_PY, edits) as info, \
            r466.install_mutation(module, DATA_PY, info.read_text()):
        yield info


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ 判据⑤：两本账合一


def test_the_audit_and_the_receipt_answer_the_same_thing_for_the_unowned_row(monkeypatch, tmp_path):
    """判据⑤⑥：同一枚无主行，回执答 null、审计也答 null —— 基点那一份在这里是两本账。"""
    from app.api.v1 import data

    _data, registry, root = _wire(monkeypatch, tmp_path)
    calls = _capture_audits(monkeypatch, data)

    receipt = _preview(data, "alice", LEGACY)
    raw_at_rest = registry.get_active_by_filename(LEGACY).owner_id  # 删之前现取：不留人抄的空串
    result = _delete(data, "root", LEGACY)

    assert receipt["owner_id"] is None, "回执那一侧的口径不是本单定的，先把它钉住"
    assert result["record_status"] == "deleted"
    before = _completion(calls)["before_summary"]
    assert before["owner_id"] is None, "审计里无主仍是空串：两本账没合一（实取 %r）" % (before["owner_id"],)
    assert before["owner_id"] == _document_rule(raw_at_rest)


def test_an_owned_row_still_names_its_owner_in_the_audit(monkeypatch, tmp_path):
    """判据⑥ 的下半句：有主那一格一个字不动（`test_resource_delete_cascade.py:231` 同源）。"""
    from app.api.v1 import data

    _data, registry, root = _wire(monkeypatch, tmp_path)
    calls = _capture_audits(monkeypatch, data)

    _delete(data, "alice", MINE)

    before = _completion(calls)["before_summary"]
    assert before["owner_id"] == OWNER_OF[MINE] == "alice", before["owner_id"]


def test_the_journal_projects_the_unowned_owner_as_null_and_keeps_the_key(monkeypatch, tmp_path):
    """判据⑥：无主上账本是 `null` 且**那一格还在** —— 不是键没了，也不是空串。"""
    from app.api.v1 import data

    _data, registry, root = _wire(monkeypatch, tmp_path)
    calls = _capture_audits(monkeypatch, data)

    _delete(data, "root", LEGACY)

    projected = audit._summarize(_completion(calls)["before_summary"])
    assert "owner_id" in projected, "无主那一格整个掉下账本 = 「这一行没被看过」，不是「没人认领」"
    assert projected["owner_id"] is None
    assert '"owner_id": null' in json.dumps(projected)
    assert '"owner_id": ""' not in json.dumps(projected)


def test_the_scope_projection_still_drops_a_blank_owner(monkeypatch, tmp_path):
    """只报不改的邻格钉住现状：`audit._project_scope` 把空串键丢掉，`resource_scope` 里没有 owner。

    那是第三本账（授权判定用的 scope），本单不碰它；这枚钉不许下一班把「审计里无主已统一成 null」
    说成覆盖 resource_scope。要统一它请另立单，先改本钉并带上裁据。
    """
    from app.api.v1 import data

    _data, registry, root = _wire(monkeypatch, tmp_path)
    projection, _source = audit._project_scope(registry.get_active_by_filename(LEGACY).resource_scope, "x")

    assert "owner_id" not in projection, "邻格改了口（空串不再被丢）：本钉要连同 §判据⑦ 那节一起改口"
    assert _delete(data, "root", LEGACY)["record_status"] == "deleted"


def _rebind(data, registry, root, monkeypatch) -> None:
    """exec 会把模块顶层重跑一遍（DATA_DIR / dataset_registry 回到出厂值），窗内必须重装夹具。

    🔴 R563：这里过去是裸赋值，用例结束没人还原 ⇒ 同一枚 worker 上的下一模块会拿到一枚
    指向已删临时目录的 registry。改走 monkeypatch：它按 setattr 顺序逐枚 undo。
    """
    monkeypatch.setattr(data, "DATA_DIR", str(root), raising=False)
    monkeypatch.setattr(data, "dataset_registry", registry, raising=False)


def _recapture(data, calls: list, monkeypatch) -> None:
    """同一扇窗里再装一次审计收集器：exec 把 ``record_audit`` 也换回了真身，不重装就收不到账。"""

    def record(principal, action, outcome, resource="", reason="", **kwargs):
        calls.append(
            {
                "principal": principal.username,
                "action": action,
                "outcome": outcome,
                "resource": resource,
                "reason": reason,
                **kwargs,
            }
        )
        return dict(calls[-1])

    monkeypatch.setattr(data, "record_audit", record, raising=False)


# ------------------------------------------------------------------ 判据⑥：schema / 码表 / 响应形状


def _route_emission(name: str, source: str) -> tuple:
    """现取一枚路由能发出去的 (稳定码, HTTP 状态) —— 两个集合都按 AST 取，不抄散文。"""
    route = next(
        node for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )
    codes, statuses = set(), set()
    for node in ast.walk(route):
        if not (isinstance(node, ast.Call) and ast.unparse(node.func).endswith("HTTPException")):
            continue
        for keyword in node.keywords:
            if keyword.arg == "detail" and isinstance(keyword.value, ast.Constant):
                codes.add(keyword.value.value)
        if node.args and isinstance(node.args[0], ast.Constant):
            statuses.add(node.args[0].value)
    return codes, statuses


def test_the_delete_leg_adds_no_stable_code_and_no_new_status(monkeypatch, tmp_path):
    """判据⑥：delete 这一腿能发出的稳定码与状态集合与基点逐字相等。"""
    base_codes, base_statuses = _route_emission("delete_data_file", _base_text(DATA_REL))
    shipped_codes, shipped_statuses = _route_emission("delete_data_file", DATA_PY.read_text(encoding="utf-8"))

    assert shipped_codes == base_codes == DELETE_STABLE_CODES, (base_codes, shipped_codes)
    assert shipped_statuses == base_statuses, (base_statuses, shipped_statuses)


def test_the_response_shape_is_word_for_word_the_one_at_base(monkeypatch, tmp_path):
    """判据⑥：响应形状一个键都不许多、不少、不改名；那一腿该做的事也没顺手变。"""
    from app.api.v1 import data

    _data, registry, root = _wire(monkeypatch, tmp_path)

    result = _delete(data, "root", LEGACY)

    assert set(result) == DELETE_RESPONSE_KEYS, sorted(result)
    assert result["filename"] == LEGACY
    assert result["file_removed"] is True and result["record_status"] == "deleted"
    assert re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", str(result["dataset_id"])), result["dataset_id"]
    assert registry.get_active_by_filename(LEGACY) is None, "行没被退役：这一腿的行为变了，本单不许动行为"
    assert not (root / LEGACY).exists(), "字节没删：这一腿的行为变了，本单不许动行为"


def test_nothing_else_in_the_audit_moved_between_base_and_delivered(monkeypatch, tmp_path):
    """判据⑥ 的正证：两副世界逐格对账 —— 事件键集、`before_summary` 键集、其余每一格都相等，
    唯一动的是 owner 那一格的**值形态**（基点 `""` / 交付 `null`）。那正是本单要的效果，不是副作用。
    """
    from app.api.v1 import data

    dir_a = tmp_path / "world-a"
    dir_a.mkdir()
    _data, registry_a, root_a = _wire(monkeypatch, dir_a)
    calls_delivered = _capture_audits(monkeypatch, data)
    _delete(data, "root", LEGACY)

    dir_b = tmp_path / "world-b"
    dir_b.mkdir()
    _d2, registry_b, root_b = _wire(monkeypatch, dir_b)
    calls_base = _capture_audits(monkeypatch, data)
    with _window([(DELIVERED_READ, BASE_READ)]) as info:
        _rebind(data, registry_b, root_b, monkeypatch)
        _recapture(data, calls_base, monkeypatch)
        _delete(data, "root", LEGACY)
    assert info["restored"], "对账窗没还原"

    shipped, base = _completion(calls_delivered), _completion(calls_base)
    assert set(shipped) == set(base), "审计事件的键集变了：判据⑥ 不许动 schema"
    assert set(shipped["before_summary"]) == set(base["before_summary"]) == set(AUDIT_BEFORE_KEYS)
    assert list(shipped["before_summary"]) == AUDIT_BEFORE_KEYS, "字段顺序也是形状的一部分"
    assert shipped["after_summary"] == base["after_summary"]
    for key in ("principal", "action", "outcome", "reason", "request_id", "resource_scope"):
        assert shipped[key] == base[key], "%s 不该跟着动" % key
    for key in ("filename", "department_ids", "classification", "size_bytes"):
        assert shipped["before_summary"][key] == base["before_summary"][key], "%s 不该跟着动" % key
    assert base["before_summary"]["owner_id"] == "" and shipped["before_summary"]["owner_id"] is None, (
        "这一格必须是从空串变成 null：两边相等说明变异没落地，两样都不是说明改错了地方")
    assert _ID_RE.sub("<id>", json.dumps(shipped, sort_keys=True, default=str)) != _ID_RE.sub(
        "<id>", json.dumps(base, sort_keys=True, default=str)), "两本账逐字相等 = 交付体没改任何东西"


# ------------------------------------------------------------------ 判据⑤ 的另一半：尺子升级确实变严


def test_the_old_roster_was_blind_to_the_delete_leg_at_base():
    """旧尺子在基点上对 delete 那一腿是瞎的：那枚病灶不是「已经有钉在看着」。"""
    import tests.test_r337_owner_receipt_on_both_exits as r337

    base_text = _base_text(DATA_REL)
    old_roster = {name: EXIT_SHAPE[name] for name in ("upload_excel", "preview_data_file")}
    original = dict(r337.EXIT_SHAPE)
    try:
        r337.EXIT_SHAPE.clear()
        r337.EXIT_SHAPE.update(old_roster)
        assert owner_shape_violations(base_text) == [], (
            "旧点名表在基点上就红了：说明本单治的那一格早就有钉在看，判据⑤ 的动机不成立")
    finally:
        r337.EXIT_SHAPE.clear()
        r337.EXIT_SHAPE.update(original)

    assert "delete_data_file" in original and sorted(original) == [
        "delete_data_file", "preview_data_file", "upload_excel"]


def test_the_upgraded_ruler_catches_the_base_shape_and_passes_the_delivered_one():
    """新尺子（任何读 owner 的路径都必须经 helper）：在基点上抓到 delete 那一腿，在交付体上归零。"""
    base_violations = module_owner_read_violations(_base_text(DATA_REL))
    shipped = module_owner_read_violations(DATA_PY.read_text(encoding="utf-8"))

    assert base_violations, "升级后的尺子在基点上没红：那这单只是换了个说法，没长新牙"
    assert any("delete_data_file" in line for line in base_violations), base_violations
    assert any("record.owner_id" in line for line in base_violations), base_violations
    assert shipped == [], "交付体不合规：" + "；".join(shipped)


def test_the_delivered_audit_leg_passes_both_layers_of_the_ruler():
    """两把尺子说的是同一句话：按出口点名判与全模块扫，在交付体上都是零违规。"""
    source = DATA_PY.read_text(encoding="utf-8")

    assert owner_shape_violations(source) == [], owner_shape_violations(source)
    assert module_owner_read_violations(source) == [], module_owner_read_violations(source)


# ------------------------------------------------------------------ 判据⑦：契约只能文末追加


def _git(args: list) -> str:
    return subprocess.run(["git", "-C", str(ROOT)] + args, capture_output=True, check=True).stdout.decode("utf-8")


def _normalize_eol(data: bytes) -> bytes:
    """按签出语义归一（index 存 LF、工作树是 CRLF）：等式要在内容层成立，不在传输层成立。"""
    return data.replace(b"\r\n", b"\n")


def _first_difference(base: bytes, current: bytes) -> int:
    return next(
        (index for index in range(min(len(base), len(current))) if base[index] != current[index]),
        min(len(base), len(current)),
    )


def test_the_current_contract_is_the_base_plus_an_appendage():
    """判据⑦：前 N 字节与 `git show a7ac040` 那一份 prefix-identical —— 历史行一字节都不许动。"""
    base = _normalize_eol(subprocess.run(
        ["git", "-C", str(ROOT), "show", "%s:%s" % (BASE, "docs/api/contract-v1.md")],
        capture_output=True, check=True).stdout)
    current = _normalize_eol(CONTRACT.read_bytes())

    assert current.startswith(base), "契约的历史被动过：第 %d 字节起与基点不同" % _first_difference(base, current)
    assert len(current) > len(base), "本单没往契约里追加任何东西"


def test_the_appendage_deletes_nothing_and_adds_exactly_one_section():
    """判据⑦ 的三笔账：历史行一字节不动 / 本单那一节恰一枚 / 严格 UTF-8、零 lone LF、零 U+FFFD。

    🔴 总控并树时改口一次（同类病这两天已裁三回：R346 行号账、R351 手抄 sha、R340 节数账，口径照抄）：
    原写法两半都在并树之后必红——「`git diff --numstat` 删除列 == 0」比的是**工作树与 HEAD**，总控一提交
    就成空 diff（added=0，"契约没长东西"当场假红）；「全仓 `## ` 节数 == 基点 + 1」把**冻结基点**的节数放在
    与现场读数的等号一侧，而本单从开工到并树之间 R356 / R340 正当各追加过一节（现场 35 -> 38）。
    现在这三条都与提交先后无关且各自咬得住：① 前缀等式咬"回改历史行"，一字节都不许动；② 长度必须变长，
    咬"什么都没写"；③ 本单那枚节标题在追加段里恰一枚，咬"同一单写两节"，也咬"没写节"。编码两条原样留着。
    """
    base_text = _normalize_eol(_git(
        ["show", "%s:%s" % (BASE, "docs/api/contract-v1.md")]).encode("utf-8")).decode("utf-8")
    current_bytes = CONTRACT.read_bytes()
    current_text = _normalize_eol(current_bytes).decode("utf-8")  # 严格解码：坏一个字节就红

    assert current_text.startswith(base_text), "契约的历史被动过：本单只许文末追加"
    assert len(current_text) > len(base_text), "契约没长东西：本单一格都没写"
    own_headings = [
        line
        for line in current_text[len(base_text):].splitlines()
        if line.startswith("## ") and "R353 / R354" in line
    ]
    assert len(own_headings) == 1, "本单那一节在追加段里应有 1 枚，实得 %d" % len(own_headings)
    assert current_text.count("\ufffd") == 0, "契约里出现 U+FFFD：编码被写坏过"
    assert current_bytes.count(b"\n") - current_bytes.count(b"\r\n") == 0, "追加引入了 lone LF"

def test_the_contract_records_that_the_audit_says_null_now():
    """判据⑦ 的正文字半边：契约得写清「审计里无主从此是 null 不是空串」，也不许吹成全覆盖。"""
    text = CONTRACT.read_text(encoding="utf-8")

    assert "delete_data_file" in text and "before_summary" in text
    assert "PDF_DEGRADATION_REASON_GROUP_CAP" in text and "_dataset_row_owner_id" in text
    assert "resource_scope" in text and "_project_scope" in text, (
        "没登记 resource_scope 那本账仍然不对称：审计里无主统一成 null 这话不能整句说")


# ------------------------------------------------------------------ 反证刀


def _delete_and_count(data, filename: str, bucket: list) -> list:
    """在计数窗里跑一趟 delete，只回本趟新增的那几笔注册表查询。"""
    before = len(bucket)
    _delete(data, "root", filename)
    return bucket[before:]


def test_counter_evidence_1_reverting_the_delete_leg_goes_red(monkeypatch, tmp_path):
    """刀1：退回基点那一形（直读属性）⇒ 两把尺子都红、两本账分家；响应形状照旧绿。"""
    from app.api.v1 import data

    tracked = _sha(DATA_PY)
    world = tmp_path / "w1"
    world.mkdir()
    _data, registry, root = _wire(monkeypatch, world)
    calls: list = []
    receipt_owner = _preview(data, "alice", LEGACY)["owner_id"]

    with _window([(DELIVERED_READ, BASE_READ)]) as info:
        _rebind(data, registry, root, monkeypatch)
        _recapture(data, calls, monkeypatch)
        assert receipt_owner is None, "回执那一侧先不是 null 了：夹具或既有码变了，本刀无从对照"
        _delete(data, "root", LEGACY)
        audit_owner = _completion(calls)["before_summary"]["owner_id"]
        violations = module_owner_read_violations(_delivered_source())
        shape = owner_shape_violations(_delivered_source())
        assert audit_owner == "" and audit_owner != receipt_owner, "两本账没分家：刀1 没落地"
        assert violations and any("delete_data_file" in line for line in violations), violations
        assert shape and any("delete_data_file" in line for line in shape), shape
        assert _sha(DATA_PY) == tracked, "被跟踪的 data.py 在反证窗里被改过"
        print("[r354] 刀1 全模块扫红 %d 枚 / 按出口点名红 %d 枚：%s" % (len(violations), len(shape), violations))
    assert info["restored"], "刀1 没还原"
    print("[r354] 刀1 RESTORED=%s sha=%s" % (info["restored"], info["after"]))


def test_counter_evidence_2_a_second_reader_that_is_right_anyway_goes_red(monkeypatch, tmp_path):
    """刀2：就地手搓一套「答案碰巧也对」的第二读法 ⇒ 行为绿、尺子必须红（口径不能靠运气）。"""
    from app.api.v1 import data

    tracked = _sha(DATA_PY)
    world = tmp_path / "w2"
    world.mkdir()
    _data, registry, root = _wire(monkeypatch, world)
    calls: list = []

    with _window([(DELIVERED_READ, SECOND_READER)]) as info:
        _rebind(data, registry, root, monkeypatch)
        _recapture(data, calls, monkeypatch)
        _delete(data, "root", LEGACY)
        audit_owner = _completion(calls)["before_summary"]["owner_id"]
        violations = module_owner_read_violations(_delivered_source())

        assert audit_owner is None, "这一把要证的是「答案看着对」：它先答错了就不是那一形"
        assert violations, "第二套读法没被抓到：判据⑤ 只在字面上成立"
        assert any("在 helper 之外读了 owner" in line for line in violations), violations
        assert any("不是同源 helper 的读数" in line for line in violations), violations
        assert _sha(DATA_PY) == tracked
        print("[r354] 刀2 第二读法（行为对、尺子红）红 %d 枚：%s" % (len(violations), violations))
    assert info["restored"], "刀2 没还原"
    print("[r354] 刀2 RESTORED=%s sha=%s" % (info["restored"], info["after"]))


def test_counter_evidence_3_a_fresh_lookup_for_the_audit_cell_goes_red(monkeypatch, tmp_path):
    """刀3：为审计那一格现查一次注册表 ⇒ 按出口点名那把尺子红（来源不再是手上那枚 record），账上多一笔；
    全模块扫那一层不红（它取的确实是同源读数）—— 两层的分工如实记下，不把功劳记错账。"""
    from app.api.v1 import data

    tracked = _sha(DATA_PY)
    world = tmp_path / "w3"
    world.mkdir()
    _data, registry, root = _wire(monkeypatch, world)
    lookups: list = []
    original = registry.get_active_by_filename

    def counting(filename):
        lookups.append(filename)
        return original(filename)

    registry.get_active_by_filename = counting
    delivered = _delete_and_count(data, MINE, lookups)

    with _window([(DELIVERED_READ, FRESH_LOOKUP)]) as info:
        _rebind(data, registry, root, monkeypatch)
        _recapture(data, [], monkeypatch)
        widened = _delete_and_count(data, LEGACY, lookups)
        shape = owner_shape_violations(_delivered_source())
        violations = module_owner_read_violations(_delivered_source())
        assert len(widened) == len(delivered) + 1, (delivered, widened)
        assert shape and any(
            "delete_data_file" in line and "来源不是手上那枚 record" in line for line in shape), shape
        assert violations == [], "这一把不该让全模块扫那层红：它取的就是同源读数，红在别处是记错账"
        print("[r354] 刀3 现查一次：本趟查询 %d -> %d；按出口点名红 %d 枚" % (
            len(delivered), len(widened), len(shape)))
    assert info["restored"], "刀3 没还原"
    registry.get_active_by_filename = original
    print("[r354] 刀3 RESTORED=%s sha=%s" % (info["restored"], info["after"]))


def test_counter_evidence_4_renaming_the_audit_field_goes_red(monkeypatch, tmp_path):
    """刀4：把审计里的字段挪走名 ⇒ schema 两格当场红（键集与顺序），响应形状照旧绿。"""
    from app.api.v1 import data

    tracked = _sha(DATA_PY)
    world = tmp_path / "w4"
    world.mkdir()
    _data, registry, root = _wire(monkeypatch, world)
    calls: list = []

    with _window([(DELIVERED_READ, RENAMED_FIELD)]) as info:
        _rebind(data, registry, root, monkeypatch)
        _recapture(data, calls, monkeypatch)
        result = _delete(data, "root", LEGACY)
        before = _completion(calls)["before_summary"]
        shape = owner_shape_violations(_delivered_source())

        assert list(before) != AUDIT_BEFORE_KEYS and "owner_id" not in before, "字段没被动：刀4 没落地"
        assert set(result) == DELETE_RESPONSE_KEYS, "响应形状跟着红：本刀只动审计载荷，夹具串了"
        assert shape and any("delete_data_file" in line for line in shape), shape
        print("[r354] 刀4 挪字段名：按出口点名红 %d 枚；审计键集=%s" % (len(shape), list(before)))
    assert info["restored"], "刀4 没还原"
    print("[r354] 刀4 RESTORED=%s sha=%s" % (info["restored"], info["after"]))


def test_the_counter_evidence_window_touches_no_tracked_file():
    """反证窗自己的纪律：`data.py` / `loader.py` / 契约的 sha256 全程恒定，窗里只许有 data.py 一枚。"""
    targets = (DATA_PY, LOADER_PY, CONTRACT)
    digests = {path: _sha(path) for path in targets}

    assert overlay.open_windows() == (), "窗外还有开着的反证窗：上一把没关"
    with _window([(DELIVERED_READ, BASE_READ)]) as info:
        assert overlay.open_windows() == (DATA_REL,), overlay.open_windows()
        assert _sha(DATA_PY) == digests[DATA_PY], "窗里盘上那枚被改过：影子根没接住"
    assert info["restored"] and info["shadow_clean"]
    assert overlay.open_windows() == ()
    for path, digest in digests.items():
        assert _sha(path) == digest, "%s 被反证窗碰过" % path.name
    print("[r354] 窗纪律 RESTORED=%s sha=%s" % (info["restored"], info["after"]))
