# -*- coding: utf-8 -*-
"""R310 · 补 owner 这一格到底花了什么：行数、查询次数、权限链次数改前改后逐枚对账 ＋ 四把反证。

判据 3 明令「不许因为补字段而多开一次查询、第二条权限链」，并把这句话钉成「同一批 fixture，
改前改后每档 `len(files)` 逐枚相等」。这里的「改前」不是回忆：影子根
（`tests/_temp_edit_overlay.py`）把 `app/api/v1/data.py` 复刻到 %TEMP%，在副本上摘掉 owner_id
那一行赋值——那正是基点 9344028 的形态——再 exec 进内存里那一枚模块字典，同一副夹具跑两遍，
逐枚对账。盘上的被跟踪文件全程只读，进出各取一次 sha256。

对账（`_run_catalog` / `_assert_the_owner_field_costed_nothing`）五笔：
  · 每档账号（外加 request is None 那一档）的 `len(files)` 与文件名清单逐枚相等；
  · `restricted` 计数相等；
  · `dataset_registry.get_active_by_filename` 的调用次数相等 —— 没多开一次查询；
  · `app.api.v1.data.authorization_decision` 的调用次数相等 —— 没长第二条权限链；
  · 变异体那一侧确实一行 owner_id 都没有 —— 否则这扇窗是空转，对账就成了自己跟自己对。

四把反证（判据 6），每把都在窗内把一条真断言打到红、出门复跑为绿，打印里写清「摘了哪把刀、
红了哪一条」：
  (a) 摘掉 owner_id 赋值 → 判据 1 的「每一行都带 owner」红；
  (b) 无主的 None 换成空串 → 判据 2 的「无主答 None」红；
  (c) 放宽既有的可见性过滤（越权行也送出来，于是也带上 owner）→ 判据 3 的行集钉与判据 4 的
      泄漏钉同时红，且行数对账当场红；
  (d) 只给入了账的行补 owner（把字段挪进 `if record is not None:` 那一支）→ 判据 1 里
      `record is None` 那一格红。(a) 是全红、(d) 只红这一格：两枚钉判的不是同一句话。

路由一律以「直接 await 协程」的方式跑：FastAPI 在 import 时把当时那枚函数对象钉进了路由表，
exec 换不掉它，而本件的每一件都必须让变异体真的被执行。HTTP 通路（中间件 → request.state →
principal_from_request）由 tests/test_r310_dataset_row_owner.py 那枚件的 wire 用例走真路由表验。
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import _temp_edit_overlay as overlay
from tests import test_r466_mutation_does_not_leak_into_live_module as r466

ROOT = Path(__file__).resolve().parents[1]
DATA_PY = ROOT / "app" / "api" / "v1" / "data.py"

DEPT_FINANCE = "r310-finance"
DEPT_HR = "r310-hr"
DEPT_OPS = "r310-ops"
LEGACY = "legacy.csv"
UNREGISTERED = "unregistered.csv"
REGISTERED = ("mine.csv", "team.csv", "hr.csv")
OWNER_OF = {"mine.csv": "alice", "team.csv": "bob", "hr.csv": "carol", LEGACY: ""}
DEPT_OF = {"mine.csv": DEPT_FINANCE, "team.csv": DEPT_FINANCE, "hr.csv": DEPT_HR}
ACCOUNTS = {
    "alice": {"id": "alice", "username": "alice", "role": "manager", "department": DEPT_FINANCE},
    "bob": {"id": "bob", "username": "bob", "role": "manager", "department": DEPT_FINANCE},
    "carol": {"id": "carol", "username": "carol", "role": "manager", "department": DEPT_HR},
    "root": {"id": "root", "username": "root", "role": "admin", "department": "r310-hq"},
    "dave": {"id": "dave", "username": "dave", "role": "staff", "department": DEPT_OPS},
}

#: 锚一律按「行列表」给，换行由被改文件自己决定：本仓文件体是纯 CRLF，把换行写进字面量迟早对不上。
OWNER_LINE = ['            "owner_id": _dataset_row_owner_id(record),']
OWNER_LINE_REMOVED: list[str] = []
UNOWNED_BRANCH = ['    if value is None or str(value).strip() == "":', "        return None"]
UNOWNED_BRANCH_AS_BLANK = ['    if value is None or str(value).strip() == "":', '        return ""']
FILTER_GUARD = ["            if not decision.allowed:"]
FILTER_OFF = ["            if False:"]
CLASSIFICATION_LINE = ['                    "classification": record.classification,']
CLASSIFICATION_CARRYING_OWNER = [
    '                    "classification": record.classification,',
    '                    "owner_id": record.owner_id,',
]


# --------------------------------------------------------------------------- 夹具（与第一枚件各自一份）


def _principal(username):
    from app.agents.contracts import Principal

    return Principal.from_user(ACCOUNTS[username])


def _request(username):
    return SimpleNamespace(state=SimpleNamespace(principal=_principal(username)))


def _wire(monkeypatch, tmp_path):
    from app.api.v1 import data
    from app.storage.datasets import DatasetRegistry, InMemoryDatasetTableStore

    root = tmp_path / "data"
    root.mkdir()
    registry = DatasetRegistry(
        root=root,
        metadata_path=root / ".dataset-metadata.json",
        store=InMemoryDatasetTableStore(),
    )
    (root / LEGACY).write_text("department,note\n%s,LEGACY-BODY\n" % DEPT_FINANCE, encoding="utf-8")
    (root / ".dataset-metadata.json").write_text(
        json.dumps({"datasets": [{
            "dataset_id": "r310-legacy",
            "filename": LEGACY,
            "owner_id": "",
            "department_ids": [DEPT_FINANCE],
            "classification": "internal",
            "visibility": "private",
            "storage_path": str(root / LEGACY),
            "status": "active",
            "created_at": "2026-09-20T00:00:00+00:00",
            "version_id": "r310-legacy:v1",
        }]}, ensure_ascii=False),
        encoding="utf-8",
    )
    for filename in REGISTERED:
        path = root / filename
        path.write_text("department,note\n%s,body-%s\n" % (DEPT_OF[filename], filename), encoding="utf-8")
        registry.register(path, principal=_principal(OWNER_OF[filename]))
    (root / UNREGISTERED).write_text("department,note\n%s,STRAY-BODY\n" % DEPT_OPS, encoding="utf-8")

    data.DATA_DIR = str(root)
    data.dataset_registry = registry
    monkeypatch.setattr(data, "DATA_DIR", str(root))
    monkeypatch.setattr(data, "dataset_registry", registry)
    return data, registry, root


def _visible_and_refused(registry, username):
    from app.common.permissions import ACTION_VIEW
    from app.common.policy import authorization_decision

    principal = _principal(username)
    visible, refused = [], []
    for record in registry.active_records():
        decision = authorization_decision(
            principal, record.resource_scope, action=ACTION_VIEW, require_resource_scope=True
        )
        (visible if decision.allowed else refused).append(record.filename)
    return sorted(visible), sorted(refused)


# ---------------------------------------------------------------------------- 反证窗：变异只落影子根


class _R310Edit(overlay.ShadowEdit):
    """一扇 R310 的反证窗：锚点命中不是恰好一处，整片变异就不落盘；变异文本先过 compile()。"""

    tag = "r310"
    #: 🔴 R466：变异只落影子副本，不 exec 进活模块——见 _window 的说明。
    execs_module = False

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
                "%s 里锚点命中 %d 处（要求恰好 1 处）：%r —— 变异整体不落盘" % (
                    self.path.name, hits, old[0]
                )
            )
            mutated = mutated.replace(needle, newline.join(new), 1)
        compile(mutated, str(self.path), "exec")
        return mutated


@contextmanager
def _window(edits):
    """开一扇窗：变异只落影子副本，窗内只把变了的那几枚顶层绑定装进 app.api.v1.data，出门逐枚装回。

    🔴 R466：旧姿势 execs_module=True 会把变异后的整份码体 exec 进 sys.modules 里那枚模块——
    本席现取 19 枚顶层把手逐枚换新身体；而那次 exec 在 __enter__ 里、_WINDOWS.append 之后，
    变异体在顶层就跑炸时 __exit__ 根本不会执行，活模块留下半份变异码。姿势件与
    test_r457_audit_retention_execution_leg.py:169-242 同一族：模块体不重跑，没点名的名字连身份都不动。
    """
    module = overlay.module_of(overlay.rel_of(DATA_PY))
    assert module is not None, "app.api.v1.data 还没被导入，改绑无处可落"
    with _R310Edit(DATA_PY, edits) as info, \
            r466.install_mutation(module, DATA_PY, info.read_text()):
        yield info


def _is_function(node, name: str) -> bool:
    """路由是 async def，helper 是普通 def：两种结型都算一枚函数。"""
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name


def _tracked_sha(path: Path = DATA_PY) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rebind(data, registry, root):
    """exec 会把模块顶层重新跑一遍（DATA_DIR / dataset_registry 都回到出厂值），窗内必须重装夹具。"""
    data.DATA_DIR = str(root)
    data.dataset_registry = registry


class _Counters:
    __slots__ = ("lookup", "decision")

    def __init__(self):
        self.lookup = 0
        self.decision = 0


def _instrument(data, registry, counters):
    """在既有的两处调用上装计数器（包一层，不改语义）：改动前后的读数都从同一副夹具现取。"""
    lookup_original = registry.get_active_by_filename
    decision_original = data.authorization_decision

    def counting_lookup(filename):
        counters.lookup += 1
        return lookup_original(filename)

    def counting_decision(*args, **kwargs):
        counters.decision += 1
        return decision_original(*args, **kwargs)

    registry.get_active_by_filename = counting_lookup
    data.authorization_decision = counting_decision
    return lookup_original, decision_original


def _deinstrument(data, registry, originals):
    """把两处调用装回原函数：registry 是这枚用例自己造的，实例属性随它一起退役。"""
    lookup_original, decision_original = originals
    registry.get_active_by_filename = lookup_original
    data.authorization_decision = decision_original


# --------------------------------------------------------------------- 一次完整读数：每档账号 ＋ 无 request


def _run_catalog(data, registry, root, counters=None):
    if counters is None:
        counters = _Counters()
    counters.lookup = 0
    counters.decision = 0
    readings = {}
    for username in ACCOUNTS:
        payload = asyncio.run(data.list_data_files(request=_request(username)))
        readings[username] = {
            "names": [row["filename"] for row in payload["files"]],
            "count": len(payload["files"]),
            "restricted": payload.get("restricted", {}).get("count", 0),
            "owners": {row["filename"]: row.get("owner_id", "<缺格>") for row in payload["files"]},
        }
    anonymous = asyncio.run(data.list_data_files())
    readings["<no-request>"] = {
        "names": sorted(row["filename"] for row in anonymous["files"]),
        "count": len(anonymous["files"]),
        "restricted": anonymous.get("restricted", {}).get("count", 0),
        "owners": {row["filename"]: row.get("owner_id", "<缺格>") for row in anonymous["files"]},
    }
    return readings, {"lookup": counters.lookup, "decision": counters.decision}


def _assert_the_owner_field_costed_nothing(before, after, cost_before, cost_after):
    """改前（没有 owner_id 那一行赋值的形态）与改后的账：行数、集合、受限计数、两处调用次数逐枚相等。"""
    for key in sorted(after):
        assert before[key]["count"] == after[key]["count"], (
            "%s 这一档行数漂了：改前 %d 行，改后 %d 行" % (key, before[key]["count"], after[key]["count"])
        )
        assert before[key]["names"] == after[key]["names"], (
            "%s 这一档可见的文件名清单不是同一串：%s vs %s" % (
                key, before[key]["names"], after[key]["names"]
            )
        )
        assert before[key]["restricted"] == after[key]["restricted"], key
    assert cost_before == cost_after, (
        "补一枚 owner_id 花掉了东西：改前 %s，改后 %s" % (cost_before, cost_after)
    )


# ------------------------------------------------------------------------------- 判据 3：零成本的钉


def test_the_owner_field_costs_no_row_and_no_lookup(monkeypatch, tmp_path):
    data, registry, root = _wire(monkeypatch, tmp_path)
    counters = _Counters()
    before_sha = _tracked_sha()

    originals = _instrument(data, registry, counters)
    after, cost_after = _run_catalog(data, registry, root, counters)
    rows_after = _all_rows(data, registry, root)
    _deinstrument(data, registry, originals)
    assert any(row["owner_id"] is not None for row in rows_after), (
        "夹具空转：改后这一侧一枚 owner 都没读到，下面的对账就是恒真"
    )

    with _window([(OWNER_LINE, OWNER_LINE_REMOVED)]) as info:
        _rebind(data, registry, root)
        instrumented_again = _instrument(data, registry, counters)
        try:
            before, cost_before = _run_catalog(data, registry, root, counters)
            assert all(
                "owner_id" not in row for row in _all_rows(data, registry, root)
            ), "摘刀没生效：这一窗里的形态还带着 owner_id，对账就成了自己跟自己对"
            _assert_the_owner_field_costed_nothing(before, after, cost_before, cost_after)
        finally:
            _deinstrument(data, registry, instrumented_again)

    _rebind(data, registry, root)
    assert info["restored"] is True
    assert _tracked_sha() == before_sha, "反证窗碰过盘上的文件：字节凭据不对"
    print("[R310 判据3] 改前/改后逐枚相等：%s；调用计数 %s == %s" % (
        sorted(after[key]["count"] for key in ACCOUNTS), cost_before, cost_after
    ))


def _all_rows(data, registry, root):
    rows = []
    for username in ACCOUNTS:
        rows.extend(asyncio.run(data.list_data_files(request=_request(username)))["files"])
    rows.extend(asyncio.run(data.list_data_files())["files"])
    return rows


# --------------------------------------------------------------------------------- 判据 6：四把反证


def _assert_every_row_has_an_owner(rows, label):
    missing = [row["filename"] for row in rows if "owner_id" not in row]
    assert not missing, "%s：这些行没有 owner_id 这一格 —— %s" % (label, sorted(missing))


def _assert_unowned_rows_answer_none(rows, label):
    blanks = [row["filename"] for row in rows if row.get("owner_id") == ""]
    assert not blanks, "%s：无主行答了空串而不是 None —— %s" % (label, sorted(blanks))
    for row in rows:
        if row["filename"] == LEGACY:
            assert row["owner_id"] is None, "%s：无主的数据行答了 %r" % (label, row["owner_id"])
            return
    raise AssertionError("%s：夹具里那枚无主行没出现在界面上" % label)


def _assert_the_stray_row_answers_none(rows, label):
    stray = [row for row in rows if row["filename"] == UNREGISTERED]
    assert stray, "%s：request is None 那一档没把未入账的文件送出来，夹具空转" % label
    assert "owner_id" in stray[0], (
        "%s：record is None 那一格整个不存在 —— 无主与「这一类产品不谈主人」是两句话" % label
    )
    assert stray[0]["owner_id"] is None, "%s：未入账的行答了 %r" % (label, stray[0]["owner_id"])


def _assert_the_row_set_is_the_policy_set(data, registry, username, label):
    payload = asyncio.run(data.list_data_files(request=_request(username)))
    visible, _refused = _visible_and_refused(registry, username)
    got = sorted(row["filename"] for row in payload["files"])
    assert got == visible, "%s：账号 %s 界面上是 %s，既有权限尺子量出来是 %s" % (
        label, username, got, visible
    )


def _assert_no_foreign_owner_travels(data, username, forbidden):
    payload = asyncio.run(data.list_data_files(request=_request(username)))
    blob = json.dumps(payload, ensure_ascii=False, default=str)
    for name in forbidden:
        assert name not in blob, "%s 的行替别人带了主人：%s 泄漏进 %s 的响应" % (username, name, username)


def test_counter_evidence_a_dropping_the_assignment_reddens_the_owner_pin(monkeypatch, tmp_path):
    """反证 (a)：摘掉 owner_id 那一行赋值 → 判据 1 的「每一行都带 owner」必须红。"""
    data, registry, root = _wire(monkeypatch, tmp_path)
    before_sha = _tracked_sha()
    _assert_every_row_has_an_owner(_all_rows(data, registry, root), "现网码")

    with _window([(OWNER_LINE, OWNER_LINE_REMOVED)]) as info:
        _rebind(data, registry, root)
        with pytest.raises(AssertionError) as caught:
            _assert_every_row_has_an_owner(_all_rows(data, registry, root), "摘掉赋值")
        print("[R310 反证a] 摘了 owner_id 赋值 → 红了判据1的行钉：%s" % caught.value)

    assert info["restored"] is True and _tracked_sha() == before_sha
    _rebind(data, registry, root)
    _assert_every_row_has_an_owner(_all_rows(data, registry, root), "出窗复跑")


def test_counter_evidence_b_an_empty_string_owner_reddens_the_none_pin(monkeypatch, tmp_path):
    """反证 (b)：无主那一支的 None 换成空串 → 判据 2 的「无主答 None」必须红。"""
    data, registry, root = _wire(monkeypatch, tmp_path)
    before_sha = _tracked_sha()
    _assert_unowned_rows_answer_none(_all_rows(data, registry, root), "现网码")

    with _window([(UNOWNED_BRANCH, UNOWNED_BRANCH_AS_BLANK)]) as info:
        _rebind(data, registry, root)
        with pytest.raises(AssertionError) as caught:
            _assert_unowned_rows_answer_none(_all_rows(data, registry, root), "无主改成空串")
        print("[R310 反证b] 无主的 None 换成空串 → 红了判据2的口径钉：%s" % caught.value)

    assert info["restored"] is True and _tracked_sha() == before_sha
    _rebind(data, registry, root)
    _assert_unowned_rows_answer_none(_all_rows(data, registry, root), "出窗复跑")


def test_counter_evidence_c_widening_the_filter_reddens_the_row_count_pin(monkeypatch, tmp_path):
    """反证 (c)：放宽既有的可见性过滤，越权行也送出来并带上 owner → 行集钉与泄漏钉同时红。"""
    data, registry, root = _wire(monkeypatch, tmp_path)
    before_sha = _tracked_sha()
    counters = _Counters()
    originals = _instrument(data, registry, counters)
    _after, cost_now = _run_catalog(data, registry, root, counters)
    _deinstrument(data, registry, originals)

    with _window([(FILTER_GUARD, FILTER_OFF)]) as info:
        _rebind(data, registry, root)
        instrumented_again = _instrument(data, registry, counters)
        with pytest.raises(AssertionError) as caught:
            _assert_the_row_set_is_the_policy_set(data, registry, "carol", "放宽过滤")
        print("[R310 反证c] 越权行也带 owner → 红了判据3的行集钉：%s" % caught.value)
        with pytest.raises(AssertionError) as leaked:
            _assert_no_foreign_owner_travels(data, "carol", ("alice", "bob"))
        print("[R310 反证c] 同一把刀 → 也红了判据4的泄漏钉：%s" % leaked.value)
        _widened, cost_widened = _run_catalog(data, registry, root, counters)
        with pytest.raises(AssertionError) as costed:
            _assert_the_owner_field_costed_nothing(_after, _widened, cost_now, cost_widened)
        print("[R310 反证c] 同一把刀 → 行数对账也红：%s" % costed.value)
        _deinstrument(data, registry, instrumented_again)

    assert info["restored"] is True and _tracked_sha() == before_sha
    _rebind(data, registry, root)
    _assert_the_row_set_is_the_policy_set(data, registry, "carol", "出窗复跑")


def test_counter_evidence_d_owner_only_for_registered_rows_reddens_the_stray_pin(monkeypatch, tmp_path):
    """反证 (d)：把 owner 挪进入账那一支 → record is None 那一格红（(a) 红全部，这枚只红这一格）。"""
    data, registry, root = _wire(monkeypatch, tmp_path)
    before_sha = _tracked_sha()
    stray_rows = asyncio.run(data.list_data_files())["files"]
    _assert_the_stray_row_answers_none(stray_rows, "现网码")

    with _window([(OWNER_LINE, OWNER_LINE_REMOVED), (CLASSIFICATION_LINE, CLASSIFICATION_CARRYING_OWNER)]) as info:
        _rebind(data, registry, root)
        with pytest.raises(AssertionError) as caught:
            _assert_the_stray_row_answers_none(asyncio.run(data.list_data_files())["files"], "只给入账行补 owner")
        print("[R310 反证d] 字段只跟着 record 走 → 红了 record is None 那一格：%s" % caught.value)
        with pytest.raises(AssertionError) as owned:
            _assert_unowned_rows_answer_none(
                asyncio.run(data.list_data_files(request=_request("alice")))["files"], "只给入账行补 owner"
            )
        print("[R310 反证d] 同一把刀 → 台账里那枚空串 owner 直接上了界面：%s" % owned.value)

    assert info["restored"] is True and _tracked_sha() == before_sha
    _rebind(data, registry, root)
    _assert_the_stray_row_answers_none(asyncio.run(data.list_data_files())["files"], "出窗复跑")


def test_the_counter_evidence_window_touches_no_tracked_file(monkeypatch, tmp_path):
    """反证窗自己的纪律：data.py 与契约的 sha256 全程恒定，窗里只许有 data.py 一枚。"""
    _wire(monkeypatch, tmp_path)
    targets = {DATA_PY: _tracked_sha(DATA_PY)}
    contract = ROOT / "docs" / "api" / "contract-v1.md"
    targets[contract] = _tracked_sha(contract)

    with _window([(OWNER_LINE, OWNER_LINE_REMOVED)]):
        assert overlay.open_windows() == ("app/api/v1/data.py",), overlay.open_windows()

    for path, digest in targets.items():
        assert _tracked_sha(path) == digest, "%s 被反证窗碰过" % path.name


def test_the_helper_stays_a_pure_read_of_the_record_in_hand():
    """判据 3 的形状半边：owner 只是读手上那枚 record，不许在组装处起第二条链或一次查询。"""

    tree = ast.parse(DATA_PY.read_bytes().decode("utf-8"), filename=str(DATA_PY))
    route = next(
        node for node in ast.walk(tree)
        if _is_function(node, "list_data_files")
    )
    helper = next(
        node for node in ast.walk(tree)
        if _is_function(node, "_dataset_row_owner_id")
    )

    targets = sorted({ast.unparse(node.func) for node in ast.walk(helper) if isinstance(node, ast.Call)})
    assert targets == ["str", "str(value).strip"], (
        "helper 只许读手上那枚 record：多出来的每一次调用都可能是一次查询或第二条权限链 —— %s" % targets
    )
    assert not [node for node in ast.walk(helper) if isinstance(node, (ast.Assert, ast.Raise))], (
        "helper 不许自己判权限、不许自己拒人：那会变成第二条权限链"
    )

    item_lines = [
        node for node in ast.walk(route)
        if isinstance(node, ast.Dict) and any(
            isinstance(key, ast.Constant) and key.value == "owner_id" for key in node.keys
        )
    ]
    assert len(item_lines) == 1, "文件行组装处只许有一枚 owner_id：%d 枚" % len(item_lines)
    item = item_lines[0]
    keys = [key.value for key in item.keys]
    assert ast.unparse(item.values[keys.index("owner_id")]) == "_dataset_row_owner_id(record)", (
        "owner 的来源不再是手上那枚 record：%s" % ast.unparse(item.values[keys.index("owner_id")])
    )
