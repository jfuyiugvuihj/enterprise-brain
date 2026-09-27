# -*- coding: utf-8 -*-
"""R337 · 两处出口补 owner 到底花了什么：正文逐格对账、查询计数对账 ＋ 五把反证（影子根）。

判据②「不为补字段多开一次查询」与判据③「逐档行数不变」不能靠自述。手法沿 R310 的账：
`tests/_temp_edit_overlay.py` 把那枚 `app/api/v1/data.py` 复刻进 %TEMP%，在副本上把两处 owner
赋值整片摘掉 —— 那正是基点 957c7d2 的形态，「改前」不是回忆 —— 再 exec 进内存里那一枚模块字典，
两副内容相同、彼此独立的世界各跑一趟，逐格对账。分副而不是一副跑两趟，是因为「改后」那一趟跑完
之后盘上会多出它上传的新档：候选文件数一变，查询与权限判定的次数就跟着变，对账量的就不再是
「补这一格花了什么」。两副世界的随机 id 与文件 mtime 打掩码后再比。
盘上的被跟踪文件全程只读，进出各取一次 sha256。

对账三笔（`_assert_the_owner_field_costed_nothing` / `_owner_problems`）：
  · 每一格出口（每档账号的目录行集、每一次预览、每一次上传回执）摘掉 owner 键之后的正文
    **逐字节相等** —— 列没多没少、行没多没少、`profile` 与 `row_scope` 一字未动；
  · `dataset_registry.get_active_by_filename` 与 `app.api.v1.data.authorization_decision` 的
    调用次数两趟相等 —— 没多开一次查询，也没长第二条权限链；
  · 变异体那一侧确实一行 owner 都没有 —— 否则这扇窗是空转，对账就成了自己跟自己对。

五把反证（每把都在窗内把一条真断言打到红、出门复跑为绿，打印写清「摘了哪把刀、红了哪一格」）：
  (1) 无主的 None 换成空串 → 预览与目录的「无主答 None」红；同源形状尺**不红**（它量的是取法）。
  (2) 绕过同源 helper 直接摸属性 → 形状尺红，且遗留台账那枚空串当场爬上界面 → 行为钉也红。
  (3) 为 owner 现算一次查询 → 计数对账红（正文那一趟逐格仍相等：这把刀只有账目咬得住）。
  (4) 摘掉预览那一处的 owner → 只有预览面红，上传与目录照旧绿：本单治的正是「一处有一处没有」。
  (5) 摘掉上传回执那一处的 owner → 只有上传面红。

尺子只有一把：形状取证从 `tests/test_r337_owner_receipt_on_both_exits.py` 的
`owner_shape_violations()` 现取，本文件不另抄一份判据①。
"""
from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from pathlib import Path

from tests import _temp_edit_overlay as overlay
from tests.test_r337_owner_receipt_on_both_exits import (
    FRESH_BODY,
    VIEWERS,
    _catalogue,
    _document_rule,
    _preview,
    _upload,
    _wire,
    owner_shape_violations,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_PY = ROOT / "app" / "api" / "v1" / "data.py"
DATA_REL = "app/api/v1/data.py"

#: 上传每趟都要新文件名（同名会被路由以 409 拒掉），对账时把它归一化成 <fresh>。
FRESH_PREFIX = "r337-fresh"
#: 本单补的两枚面。目录那一格是 R310 的地盘：它两趟都必须带着 owner，一格都不许多也不许少。
NEW_OWNER_FACES = ("preview", "upload")
_ID_RE = re.compile(r"[0-9a-f]{32}")
_MTIME_RE = re.compile(r'"modified_at": "[^"]*"')
_ABSENT = "<缺格>"

# ---------------------------------------------------- 行锚点：按「行列表」给，换行由被改文件自己决定

PREVIEW_OWNER_BLOCK = [
    "        owner_id = _dataset_row_owner_id(record)",
    "        preview.update(",
    "            {",
    '                "dataset_id": record.dataset_id,',
    '                "version_id": record.version_id,',
    '                "owner_id": owner_id,',
    "            }",
    "        )",
]
PREVIEW_OWNER_BLOCK_AS_BASELINE = [
    '        preview.update({"dataset_id": record.dataset_id, "version_id": record.version_id})',
]
PREVIEW_READ_LINE = ["        owner_id = _dataset_row_owner_id(record)"]
PREVIEW_READ_VIA_ATTRIBUTE = ["        owner_id = record.owner_id"]
PREVIEW_READ_VIA_SECOND_LOOKUP = [
    "        owner_id = _dataset_row_owner_id("
    "dataset_registry.get_active_by_filename(record.filename))",
]
UPLOAD_READ_LINE = ["    owner_id = _dataset_row_owner_id(dataset)"]
UPLOAD_KEY_LINES = [
    '            "classification": dataset.classification,',
    '            "owner_id": owner_id,',
]
UPLOAD_KEY_LINES_WITHOUT_OWNER = ['            "classification": dataset.classification,']
UNOWNED_BRANCH = ['    if value is None or str(value).strip() == "":', "        return None"]
UNOWNED_BRANCH_AS_BLANK = ['    if value is None or str(value).strip() == "":', '        return ""']

#: 两处 owner 一起摘掉 = 基点 957c7d2 的形态，对账里「改前」那一侧。
NO_OWNER_ON_EITHER_EXIT = [
    (PREVIEW_OWNER_BLOCK, PREVIEW_OWNER_BLOCK_AS_BASELINE),
    (UPLOAD_READ_LINE, []),
    (UPLOAD_KEY_LINES, UPLOAD_KEY_LINES_WITHOUT_OWNER),
]
PREVIEW_OWNER_ONLY = [(PREVIEW_OWNER_BLOCK, PREVIEW_OWNER_BLOCK_AS_BASELINE)]
UPLOAD_OWNER_ONLY = [(UPLOAD_READ_LINE, []), (UPLOAD_KEY_LINES, UPLOAD_KEY_LINES_WITHOUT_OWNER)]

# -------------------------------------------------------------------------- 反证窗：变异只落影子根


class _R337Edit(overlay.ShadowEdit):
    """一扇 R337 的反证窗：锚点命中不是恰好一处，整片变异就不落影子；变异文本先过 compile()。"""

    tag = "r337"
    execs_module = True

    def __init__(self, path: Path, edits) -> None:
        super().__init__(path)
        self.edits = [(tuple(old), tuple(new)) for old, new in edits]

    def mutate(self, text: str) -> str:
        newline = chr(13) + chr(10) if chr(13) + chr(10) in text else chr(10)
        mutated = text
        for old, new in self.edits:
            needle = newline.join(old)
            hits = mutated.count(needle)
            assert hits == 1, (
                "%s 里锚点命中 %d 处（要求恰好 1 处）：%r —— 变异整体不落盘"
                % (self.path.name, hits, old[0])
            )
            mutated = mutated.replace(needle, newline.join(new), 1)
        compile(mutated, str(self.path), "exec")
        return mutated


@contextmanager
def _window(edits):
    """开一扇窗，把变异 exec 进 app.api.v1.data，出门由基类逐字节还原视图。"""
    module = overlay.module_of(DATA_REL)
    assert module is not None, "app.api.v1.data 还没被导入，exec 无处可落"
    with _R337Edit(DATA_PY, edits) as info:
        yield info


def _rebind(data, registry, root):
    """exec 会把模块顶层重跑一遍（DATA_DIR / dataset_registry 回到出厂值），窗内必须重装夹具。"""
    data.DATA_DIR = str(root)
    data.dataset_registry = registry


def _tracked_sha() -> str:
    return hashlib.sha256(DATA_PY.read_bytes()).hexdigest()


# ------------------------------------------------------------- 一趟读数：正文 + owner 证词 + 两处计数


def _dump_without_owner(payload, fresh_name: str) -> str:
    """摘掉所有 owner_id 键之后的正文，归一化成可比对的字符串。

    掩码只有三处，每一处都与 owner 无关：随机 dataset_id / version_id、两副世界各写各的文件
    mtime、每趟新上传的那个文件名。正文的列、行、`profile`、`row_scope` 一个字节都不掩。
    """

    def strip(node):
        if isinstance(node, dict):
            return {key: strip(value) for key, value in node.items() if key != "owner_id"}
        if isinstance(node, list):
            return [strip(item) for item in node]
        return node

    text = json.dumps(strip(payload), ensure_ascii=False, sort_keys=True, default=str)
    text = _MTIME_RE.sub('"modified_at": "<mtime>"', text.replace(fresh_name, "<fresh>"))
    return _ID_RE.sub("<id>", text)


def _short_name(filename: str) -> str:
    return "<fresh>" if FRESH_PREFIX in filename else filename


def _owner_of(payload):
    """owner 证词：目录逐行给 {文件名: 值}，预览与上传给标量；缺格记 <缺格>。"""
    if isinstance(payload, list):
        return {_short_name(row["filename"]): row.get("owner_id", _ABSENT) for row in payload}
    return payload.get("owner_id", _ABSENT)


def _expected_owner(registry, filename):
    """台账上这一行本来该答的主人（无主 = None）：谓词走文档层，与两枚出口同一把尺子。"""
    record = registry.get_active_by_filename(filename)
    assert record is not None, "台账查无 %s，期望值无从算起" % filename
    return _document_rule(record.owner_id)


def _sort_key(item):
    return tuple(str(part) for part in item)


def _run_exits(data, registry, fresh_name: str):
    """跑一遍两处出口 + 目录。两趟之间唯一多出来的那一枚新档由 FRESH_PREFIX 滤掉，保证同集。"""
    counters = {"lookup": 0, "decision": 0}
    lookup_original = registry.get_active_by_filename
    decision_original = data.authorization_decision

    def counting_lookup(filename):
        counters["lookup"] += 1
        return lookup_original(filename)

    def counting_decision(*args, **kwargs):
        counters["decision"] += 1
        return decision_original(*args, **kwargs)

    registry.get_active_by_filename = counting_lookup
    data.authorization_decision = counting_decision
    readings: dict = {}
    owners: dict = {}
    payloads: dict = {}
    try:
        for username in VIEWERS:
            # 两副世界各写各的 mtime，「谁新谁在前」不属本单对账（那是 test_data_file_catalog 的格子）；
            # 这里按文件名定序，行集、行数与每一行的内容仍然逐字节对判。
            rows = sorted(
                (row for row in _catalogue(data, username) if FRESH_PREFIX not in row["filename"]),
                key=lambda row: row["filename"],
            )
            payloads[("catalogue", username)] = rows
            readings[("catalogue", username)] = _dump_without_owner(rows, fresh_name)
            owners[("catalogue", username)] = _owner_of(rows)
            for filename in sorted(row["filename"] for row in rows):
                key = ("preview", username, filename)
                body = _preview(data, username, filename)
                payloads[key] = body
                readings[key] = _dump_without_owner(body, fresh_name)
                owners[key] = _owner_of(body)
        receipt = _upload(data, "bob", fresh_name, FRESH_BODY.encode("utf-8"))
        payloads[("upload", "<fresh>")] = receipt
        readings[("upload", "<fresh>")] = _dump_without_owner(receipt, fresh_name)
        owners[("upload", "<fresh>")] = _owner_of(receipt)
    finally:
        registry.get_active_by_filename = lookup_original
        data.authorization_decision = decision_original

    expected: dict = {}
    for key, payload in payloads.items():
        if key[0] == "catalogue":
            expected[key] = {
                _short_name(row["filename"]): _expected_owner(registry, row["filename"])
                for row in payload
            }
        elif key[0] == "preview":
            expected[key] = _expected_owner(registry, key[2])
        else:
            expected[key] = "bob"
    return readings, owners, expected, dict(counters)


def _owner_problems(owners, expected, tag: str) -> list[str]:
    """每一格出口都得带 owner，且值就是台账上那一枚。违规逐条列出，不抛 —— 反证要说清红了哪一面。"""
    problems = []
    for key in sorted(owners, key=_sort_key):
        actual, want = owners[key], expected[key]
        face = key[0]
        where = "/".join(map(str, key[1:]))
        if isinstance(want, dict):
            assert set(actual) == set(want), "%s/%s 两趟的行集不是一批：%s vs %s" % (
                tag, where, sorted(actual), sorted(want))
            for filename in sorted(want):
                if actual[filename] is _ABSENT:
                    problems.append("%s %s：%s 整格没有 owner_id" % (tag, face, filename))
                elif actual[filename] != want[filename]:
                    problems.append(
                        "%s %s：%s 的主人答成 %r，台账是 %r"
                        % (tag, face, filename, actual[filename], want[filename])
                    )
        elif actual is _ABSENT:
            problems.append("%s %s：%s 整格没有 owner_id" % (tag, face, where))
        elif actual != want:
            problems.append(
                "%s %s：%s 的主人答成 %r，台账是 %r" % (tag, face, where, actual, want)
            )
    return problems


def _cells(owners, faces=None) -> list:
    return [value for key, value in owners.items() if faces is None or key[0] in faces]


def _absent_cells(owners, faces=None) -> int:
    return sum(
        1
        for value in _cells(owners, faces)
        if value is _ABSENT or (isinstance(value, dict) and _ABSENT in value.values())
    )


def _assert_the_owner_field_costed_nothing(before, after, cost_before, cost_after):
    """改前（两处 owner 被整片摘掉的形态）与改后的账：正文逐格逐字节相等，两处调用次数相等。"""
    readings_before, owners_before = before[0], before[1]
    readings_after, owners_after = after[0], after[1]

    assert set(readings_before) == set(readings_after), (
        "两趟读的格不是同一批：只在前一趟 %s，只在后一趟 %s"
        % (
            sorted(set(readings_before) - set(readings_after)),
            sorted(set(readings_after) - set(readings_before)),
        )
    )
    assert readings_before, "空转：一格都没读到，下面的相等断言恒真"
    for key in sorted(readings_after, key=_sort_key):
        assert readings_before[key] == readings_after[key], (
            "补 owner 改动了 %s 的正文（列 / 行 / profile / row_scope 逐字节对判）：判据③破了" % (key,)
        )
    assert cost_before == cost_after, (
        "补 owner 多花了账：改前 %s，改后 %s —— 判据②（不为这一格多开一次查询）破了"
        % (cost_before, cost_after)
    )
    return {
        "cells": len(readings_after),
        "cost": cost_after,
        "absent_before": _absent_cells(owners_before),
        "absent_after": _absent_cells(owners_after),
        "new_faces_cells": len(_cells(owners_after, NEW_OWNER_FACES)),
        "new_faces_absent_before": _absent_cells(owners_before, NEW_OWNER_FACES),
        "new_faces_absent_after": _absent_cells(owners_after, NEW_OWNER_FACES),
        "catalogue_absent_before": _absent_cells(owners_before, ("catalogue",)),
        "catalogue_absent_after": _absent_cells(owners_after, ("catalogue",)),
    }

def _faces(problems) -> list[str]:
    """从违规句里取「红了哪一面」：句式是「<tag> <face>：<where> …」，face 是冒号前最后一个词。"""
    return sorted({line.split("：")[0].split()[-1] for line in problems})


def _wire_world(monkeypatch, base: Path, name: str):
    """一副独立但内容相同的世界：两趟读数各占一副，盘上互不污染。"""
    world = base / name
    world.mkdir(parents=True, exist_ok=True)
    return _wire(monkeypatch, world)


def _preview_faces(violations) -> list[str]:
    """形状尺的违规句里取路由名：句式是「<route>：<说明>」。"""
    return sorted({line.split("：")[0] for line in violations})


# ================================================================ 对账：两处出口只加一格，账目分文未动


def test_the_owner_key_costed_nothing_on_either_exit(monkeypatch, tmp_path):
    from app.api.v1 import data

    _data, registry, root = _wire_world(monkeypatch, tmp_path, "delivered")
    before_sha = _tracked_sha()

    now = _run_exits(data, registry, "%s-1.csv" % FRESH_PREFIX)
    assert _owner_problems(now[1], now[2], "交付体") == []

    _d2, registry_b, root_b = _wire_world(monkeypatch, tmp_path, "mutant")
    with _window(NO_OWNER_ON_EITHER_EXIT) as info:
        _rebind(data, registry_b, root_b)
        then = _run_exits(data, registry_b, "%s-2.csv" % FRESH_PREFIX)
        problems = _owner_problems(then[1], then[2], "摘掉 owner")
        assert problems, "反证窗空转：变异体照样带着 owner，下面的对账就成了自己跟自己对"
        print("[R337 对账] 变异体缺 owner 的出口格：%d / %d；违规首条：%s"
              % (_absent_cells(then[1]), len(then[1]), problems[0]))
        summary = _assert_the_owner_field_costed_nothing(then, now, then[3], now[3])

    assert info["restored"] is True and _tracked_sha() == before_sha
    _rebind(data, registry, root)
    print("[R337 对账] 逐格 %d 处正文逐字节相同；查询 %s 次 / 权限判定 %s 次两趟相等；"
          "本单两面 %d 格：改前全缺 %d、改后全在 %d；目录那一格两趟缺格 %d/%d"
          % (summary["cells"], summary["cost"]["lookup"], summary["cost"]["decision"],
             summary["new_faces_cells"], summary["new_faces_absent_before"],
             summary["new_faces_absent_after"],
             summary["catalogue_absent_before"], summary["catalogue_absent_after"]))
    assert summary["new_faces_absent_before"] == summary["new_faces_cells"], summary
    assert summary["new_faces_absent_after"] == 0, summary
    # 目录那一格不归本单：它两趟都得带着 owner，缺一格就是碰坏了 R310。
    assert summary["catalogue_absent_before"] == 0, summary
    assert summary["catalogue_absent_after"] == 0, summary


# ================================================================== 五把反证：窗内红、出门绿，逐把报数


def test_counter_evidence_1_unowned_answers_a_blank_string(monkeypatch, tmp_path):
    """反证 (1)：「无主 = None」改成「无主 = 空串」→ 预览与目录两格当场红。"""
    from app.api.v1 import data

    _data, registry, root = _wire(monkeypatch, tmp_path)
    before_sha = _tracked_sha()
    _readings, owners, expected, _cost = _run_exits(data, registry, "%s-a.csv" % FRESH_PREFIX)
    assert _owner_problems(owners, expected, "现网码") == []

    with _window([(UNOWNED_BRANCH, UNOWNED_BRANCH_AS_BLANK)]) as info:
        _rebind(data, registry, root)
        _r2, blanked, expected2, _c2 = _run_exits(data, registry, "%s-b.csv" % FRESH_PREFIX)
        problems = _owner_problems(blanked, expected2, "无主答空串")
        assert problems, "这把刀没砍到东西：空串没被任何一格钉抓住"
        for line in problems:
            print("[R337 反证1] %s" % line)
        assert _faces(problems) == ["catalogue", "preview"], _faces(problems)
        assert all("答成 ''" in line for line in problems), problems
        # 形状尺量的是「怎么取」，取值口径换了它不红 —— 如实记下来，别把功劳记错账。
        assert owner_shape_violations(overlay.authoritative_text(DATA_REL)) == [], (
            "取值口径的变异不该让形状尺红：红了说明两把尺子搅在一起了"
        )

    assert info["restored"] is True and _tracked_sha() == before_sha
    _rebind(data, registry, root)
    _r3, restored, expected3, _c3 = _run_exits(data, registry, "%s-c.csv" % FRESH_PREFIX)
    assert _owner_problems(restored, expected3, "出窗复跑") == []

def test_counter_evidence_2_bypassing_the_shared_helper(monkeypatch, tmp_path):
    """反证 (2)：预览那一处绕过同源 helper 直接摸属性 → 形状尺红，台账那枚空串也爬上界面。"""
    from app.api.v1 import data

    _data, registry, root = _wire(monkeypatch, tmp_path)
    before_sha = _tracked_sha()
    assert owner_shape_violations(DATA_PY.read_text(encoding="utf-8")) == []

    with _window([(PREVIEW_READ_LINE, PREVIEW_READ_VIA_ATTRIBUTE)]) as info:
        _rebind(data, registry, root)
        violations = owner_shape_violations(overlay.authoritative_text(DATA_REL))
        assert violations, "形状尺没红：判据①那几格判据读不到这一形"
        for line in violations:
            print("[R337 反证2] 形状尺：%s" % line)
        assert _preview_faces(violations) == ["preview_data_file"], violations
        _r2, owners, expected, _c = _run_exits(data, registry, "%s-d.csv" % FRESH_PREFIX)
        problems = _owner_problems(owners, expected, "直读属性")
        assert _faces(problems) == ["preview"], _faces(problems)
        for line in problems:
            print("[R337 反证2] 行为钉：%s" % line)
        assert all("答成 ''" in line for line in problems), problems

    assert info["restored"] is True and _tracked_sha() == before_sha
    _rebind(data, registry, root)
    assert owner_shape_violations(overlay.authoritative_text(DATA_REL)) == []


def test_counter_evidence_3_one_more_lookup_is_caught_by_the_tally(monkeypatch, tmp_path):
    """反证 (3)：为 owner 现算一次查询 → 正文逐格仍相等（这把刀只有账目咬得住），计数对账当场红。"""
    from app.api.v1 import data

    _data, registry, root = _wire_world(monkeypatch, tmp_path, "delivered")
    before_sha = _tracked_sha()
    now = _run_exits(data, registry, "%s-a.csv" % FRESH_PREFIX)
    previews = len([key for key in now[0] if key[0] == "preview"])

    _d2, registry_b, root_b = _wire_world(monkeypatch, tmp_path, "mutant")
    with _window([(PREVIEW_READ_LINE, PREVIEW_READ_VIA_SECOND_LOOKUP)]) as info:
        _rebind(data, registry_b, root_b)
        widened = _run_exits(data, registry_b, "%s-b.csv" % FRESH_PREFIX)
        assert _owner_problems(widened[1], widened[2], "多开一次查询") == [], (
            "这一把刀要证的是「答案没变、账变了」：答案先变了就说明夹具不成立"
        )
        assert widened[3]["lookup"] - now[3]["lookup"] == previews, (widened[3], now[3], previews)
        assert widened[3]["decision"] == now[3]["decision"], (
            "这一把刀只该多开查询：权限判定次数也变了，说明变异顺手动了别的腿 %s vs %s"
            % (now[3], widened[3])
        )
        print("[R337 反证3] 每次预览多一次现查：%d 格预览 -> 查询 %d 涨到 %d（权限判定 %d 不变）"
              % (previews, now[3]["lookup"], widened[3]["lookup"], widened[3]["decision"]))
        try:
            _assert_the_owner_field_costed_nothing(widened, now, widened[3], now[3])
        except AssertionError as caught:
            print("[R337 反证3] 多开一次查询 → 计数对账红：%s" % str(caught).splitlines()[0])
        else:
            raise AssertionError("反证 (3) 空转：多出来的那次查询没被账目抓到")
        assert _preview_faces(owner_shape_violations(overlay.authoritative_text(DATA_REL))) == [
            "preview_data_file"
        ]

    assert info["restored"] is True and _tracked_sha() == before_sha
    _rebind(data, registry, root)
    _d3, registry_c, root_c = _wire_world(monkeypatch, tmp_path, "restored")
    _rebind(data, registry_c, root_c)
    again = _run_exits(data, registry_c, "%s-c.csv" % FRESH_PREFIX)
    _rebind(data, registry, root)
    _assert_the_owner_field_costed_nothing(again, now, again[3], now[3])

def test_counter_evidence_4_dropping_the_preview_owner_leaves_the_other_two_alone(monkeypatch, tmp_path):
    """反证 (4)：只摘预览那一处 → 只有预览面红；目录与上传照旧绿（本单治的就是这一族病）。"""
    from app.api.v1 import data

    _data, registry, root = _wire(monkeypatch, tmp_path)
    before_sha = _tracked_sha()
    _readings, owners, expected, _cost = _run_exits(data, registry, "%s-a.csv" % FRESH_PREFIX)
    assert _owner_problems(owners, expected, "现网码") == []

    with _window(PREVIEW_OWNER_ONLY) as info:
        _rebind(data, registry, root)
        _r2, dropped, expected2, _c2 = _run_exits(data, registry, "%s-b.csv" % FRESH_PREFIX)
        problems = _owner_problems(dropped, expected2, "摘掉预览的 owner")
        assert problems, "这把刀谁都没砍到：预览面根本没有钉在看 owner"
        for line in problems:
            print("[R337 反证4] %s" % line)
        assert _faces(problems) == ["preview"], _faces(problems)
        assert _absent_cells(dropped) < len(dropped), "上传与目录也一起缺格了：两枚变异不是一枚的账"

    assert info["restored"] is True and _tracked_sha() == before_sha
    _rebind(data, registry, root)
    _r3, restored, expected3, _c3 = _run_exits(data, registry, "%s-c.csv" % FRESH_PREFIX)
    assert _owner_problems(restored, expected3, "出窗复跑") == []


def test_counter_evidence_5_dropping_the_upload_receipt_owner(monkeypatch, tmp_path):
    """反证 (5)：只摘上传回执那一处 → 只有上传面红；预览与目录照旧绿。"""
    from app.api.v1 import data

    _data, registry, root = _wire(monkeypatch, tmp_path)
    before_sha = _tracked_sha()
    _readings, owners, expected, _cost = _run_exits(data, registry, "%s-a.csv" % FRESH_PREFIX)
    assert _owner_problems(owners, expected, "现网码") == []

    with _window(UPLOAD_OWNER_ONLY) as info:
        _rebind(data, registry, root)
        _r2, dropped, expected2, _c2 = _run_exits(data, registry, "%s-b.csv" % FRESH_PREFIX)
        problems = _owner_problems(dropped, expected2, "摘掉上传回执的 owner")
        assert problems, "这把刀谁都没砍到：上传回执那一格没有钉在看 owner"
        for line in problems:
            print("[R337 反证5] %s" % line)
        assert _faces(problems) == ["upload"], _faces(problems)
        assert _absent_cells(dropped) == 1, _absent_cells(dropped)

    assert info["restored"] is True and _tracked_sha() == before_sha
    _rebind(data, registry, root)
    _r3, restored, expected3, _c3 = _run_exits(data, registry, "%s-c.csv" % FRESH_PREFIX)
    assert _owner_problems(restored, expected3, "出窗复跑") == []


def test_the_counter_evidence_window_touches_no_tracked_file(monkeypatch, tmp_path):
    """反证窗自己的纪律：data.py 与契约的 sha256 全程恒定，窗里只许有 data.py 一枚。"""
    _wire(monkeypatch, tmp_path)
    contract = ROOT / "docs" / "api" / "contract-v1.md"
    targets = {
        DATA_PY: _tracked_sha(),
        contract: hashlib.sha256(contract.read_bytes()).hexdigest(),
    }

    with _window(PREVIEW_OWNER_ONLY):
        assert overlay.open_windows() == (DATA_REL,), overlay.open_windows()

    for path, digest in targets.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, "%s 被反证窗碰过" % path.name
