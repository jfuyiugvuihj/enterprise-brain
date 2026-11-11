# -*- coding: utf-8 -*-
"""R550 判据① · 「事件发射点 → 订阅 / 投影 → 写句」这一跳的爬法必须通用，不许有表名特例。

三格自证，缺一格都不算通用：

* **静态**：参与沿边爬法的那些方法，参数名里不许出现 `table` / `collection`，非文档串的字面量、
  名字、属性里也不许出现八枚表名、`retrieval.completed`、`/retrieval/debug`、`project_retrieval`
  这一族真名——引用真名当分支，就是给这张表写特例（文档串是散文，允许写真名，故逐条剥掉再查）。
* **合成正控**：一棵全 invented 名字的小树（`synth.completed` / `project_synth` / `emit_synth` /
  `arm_synth_token`…）跑同一套爬法必须爬到 `POST /synth/ask`。这一格是「通用」的正证，不是靠
  真树读数蒙对：树里一个真表名都没有，脸、闸门、守卫、投影全是我造的。
* **合成反控**：同一套形状里，闸门摘掉、一处调用被两枚事件守卫、发射点只躺在脚本 `main()` 里
  ——三种都必须读成零枚产品面。放宽爬法换来的绿，本件不收。

最后四枚拿真树的现扫对拍：桥必须带事件标签、声明的事件与现扫守卫到的必须互证、`validate()`
在盘上这份必须零 problem，而我新加的两枚牙（裁定↔现扫自洽、无主跨跳）各配一把在内存里就
能咬的刀——不许留永不匹配的死牙。
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "r483_empty_tables_triage.py"
DOC_PATH = REPO_ROOT / "docs" / "testing" / "r483-empty-tables-2026-09-29.md"


def _mod():
    spec = importlib.util.spec_from_file_location("r483_r550_generic", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _mod()
SOURCE = SCRIPT.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
DOC = DOC_PATH.read_text(encoding="utf-8")
PAYLOAD = M.extract_payload(DOC)
INDEX = M.SourceIndex(REPO_ROOT)
READINGS = M.build_readings(PAYLOAD, INDEX, M.baseline_from_probe(M.PROBE_PATH))

#: 参与沿边爬法的全部方法：判据① 的审计面就是这一叠（改名即红，本件先钉「它们还在树上」）。
CLIMB_METHODS = ("surface", "event_emitters", "dispatch_labels", "dispatch_events",
                 "gate_armers", "context_set_sites", "route_on_chain", "enclosing_defs",
                 "event_constants", "statement", "function_body", "shadowed", "callers")
#: 真树里这张表专用的名字：爬法一旦引用它们，判据① 就退化成「为 retrieval_traces 写特例」。
FORBIDDEN_NAMES = tuple(M.TARGET_TABLES) + (
    "retrieval.completed", "/retrieval/debug", "project_retrieval", "project_event",
    "record_retrieval_completed", "arm_retrieval_trace",
)

PIPE = '''
_SYNTH_CONTEXT = ContextVar("synth_ctx", default=None)


def current_synth_context():
    return _SYNTH_CONTEXT.get()


def arm_synth_token(payload):
    return _SYNTH_CONTEXT.set(payload.trace_id)


def reset_synth_token(token):
    return _SYNTH_CONTEXT.reset(token)


def emit_synth(payload):
    context = payload.context or current_synth_context()
    if context is None:
        return None
    return synth_sink.record_event(
        trace_id=context,
        event_type="synth.completed",
        status="completed",
    )


def search_synth(query, principal):
    payload = build_payload(query, principal)
    emit_synth(payload)
    return payload.rows
'''

FACE = '''
from app.rag.synthpipe import arm_synth_token, reset_synth_token


@router.post("/synth/ask")
def ask(payload):
    """路由挂在外层，真正挂身份的是体内那枚 _run —— 与真树问答面同一形状。"""
    def _run():
        token = arm_synth_token(payload)
        return run_pipeline(payload)
    try:
        return _run()
    finally:
        reset_synth_token(token)
'''

PROJ = '''
def project_synth(event):
    return {"trace_id": event["trace_id"]}


def synth_dispatch(event_type, event):
    rows = []
    if event_type == "synth.completed":
        rows.append(project_synth(event))
    return rows
'''

TOOL = '''
def search_docs(query, principal):
    rows = search_synth(query, principal)
    return rows
'''

#: 合成小树的文件表：键是相对路径，值是整份源码。改任何一枚名字前先看 FORBIDDEN_NAMES。
SYNTH_FILES = {
    "app/rag/synthpipe.py": PIPE,
    "app/api/v1/synthface.py": FACE,
    "app/trace/synthproj.py": PROJ,
    "app/tools/synthtool.py": TOOL,
}
#: 这一格只钉「形状是通用的」：小树里一枚真表名、真事件名都不许出现。
SYNTH_BLOB = "".join(SYNTH_FILES.values())


def _write_tree(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text.lstrip("\n"), encoding="utf-8", newline="\n")
    return root


def _cut(text: str, old: str, new: str, count: int = 1) -> str:
    assert text.count(old) == count, (old, text.count(old))
    return text.replace(old, new, count)


def _scan(root: Path, entries, events):
    return M.SourceIndex(root).surface(entries, events)


# ------------------------------------------------------------------ 静态：爬法里没有真名
def _funcs_by_name():
    out = {}
    for node in ast.walk(TREE):
        if isinstance(node, ast.FunctionDef):
            out.setdefault(node.name, node)
    return out


FUNCS = _funcs_by_name()


def _code_tokens(func):
    """函数体里所有字符串字面量 / 名字 / 属性 / 形参名；🔴 先剥掉文档串（散文允许写真名）。
    """
    body = list(func.body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    found = []
    for item in body:
        for sub in ast.walk(item):
            if isinstance(sub, ast.Constant):
                if isinstance(sub.value, str):
                    found.append(sub.value)
            elif isinstance(sub, ast.Name):
                found.append(sub.id)
            elif isinstance(sub, ast.Attribute):
                found.append(sub.attr)
            elif isinstance(sub, ast.arg):
                found.append(sub.arg)
    return found


def test_the_climb_methods_are_still_on_the_tree():
    missing = [name for name in CLIMB_METHODS if name not in FUNCS]
    assert not missing, "爬法里的方法不在树上了（改名或删掉都要先改本件）：" + repr(missing)


def test_the_climb_code_carries_no_table_name_and_no_real_event_name():
    offenders = []
    for name in CLIMB_METHODS:
        for token in _code_tokens(FUNCS[name]):
            for banned in FORBIDDEN_NAMES:
                if banned in token:
                    offenders.append(name + " 的代码里引用真名 " + banned
                                     + "（字面：" + token[:60] + "）")
    assert not offenders, offenders


def test_no_climb_method_takes_a_table_or_collection_argument():
    for name in CLIMB_METHODS:
        arguments = FUNCS[name].args
        args = [item.arg for item in list(arguments.posonlyargs) + list(arguments.args)
                + list(arguments.kwonlyargs)]
        for arg in args:
            assert arg not in ("table", "collection", "table_name"), (name, args)
        if name == "surface":
            assert args == ["self", "entries", "events"], args


def test_the_synthetic_tree_contains_no_real_name_at_all():
    for banned in FORBIDDEN_NAMES:
        assert banned not in SYNTH_BLOB, banned
    assert "retrieval" not in SYNTH_BLOB, "小树里混进了真树的族名，这棵就不算独立正证"


# ------------------------------------------------------------------ 合成正控：跳过去了
def test_the_same_climb_crosses_the_event_hop_on_an_invented_tree(tmp_path):
    surface = _scan(_write_tree(tmp_path, SYNTH_FILES), ("project_synth",), ("synth.completed",))
    assert surface["problems"] == [], surface["problems"]
    assert [route["route"] for route in surface["routes"]] == ["POST /synth/ask"], surface
    assert all(route["event"] == "synth.completed" for route in surface["routes"]), surface
    kinds = {bridge["kind"] for bridge in surface["bridges"]}
    assert {"declared_event", "gate_token", "event_guard", "publish"} <= kinds, kinds
    assert all(bridge["event"] for bridge in surface["bridges"]), surface["bridges"]


def test_the_route_on_an_invented_tree_is_paid_for_by_the_gate(tmp_path):
    """把闸门那一腿（`if context is None: return`）摘掉，同一棵树必须立刻读成零枚产品面。

    🔴 这一格证明爬法不是「模块里恰好有一枚同名 .get」：发射点、守卫、投影、路由全在原地，
    只有「缺身份就走开」那条语句没了——边与脸同时消失，才算闸门真的承重。
    """
    files = dict(SYNTH_FILES)
    files["app/rag/synthpipe.py"] = _cut(PIPE, "    if context is None:\n        return None\n",
                                         "    if context == 0:\n        return None\n")
    surface = _scan(_write_tree(tmp_path, files), ("project_synth",), ("synth.completed",))
    assert surface["routes"] == [], surface["routes"]
    assert not [bridge for bridge in surface["bridges"] if bridge["kind"] == "gate_token"], (
        surface["bridges"])
    visited = " ".join(surface["trail"])
    assert "emit_synth" in visited and "synth_dispatch" in visited, surface["trail"]


# ------------------------------------------------------------------ 合成反控：不许过收
def test_a_call_guarded_by_two_events_is_not_clothed_with_one_label(tmp_path):
    """一处调用被两枚事件守卫时不许随手挑一枚标签上爬：挑错就是给别的表借道。"""
    files = dict(SYNTH_FILES)
    files["app/trace/synthproj.py"] = (
        "def project_synth4(event):\n"
        "    return {\"trace_id\": event[\"trace_id\"]}\n"
        "\n"
        "def synth_dispatch(event_type, kind, event):\n"
        "    rows = []\n"
        "    if event_type == \"pack.done\":\n"
        "        if event_type == \"synth4.completed\":\n"
        "            rows.append(project_synth4(event))\n"
        "    return rows\n")
    files["app/rag/synthpipe.py"] = _cut(PIPE, '"synth.completed"', '"synth4.completed"')
    surface = _scan(_write_tree(tmp_path, files), ("project_synth4",), ())
    assert surface["routes"] == [], surface["routes"]
    assert any("多枚事件守卫" in note for note in surface["notes"]), surface["notes"]


def test_an_emitter_only_reachable_from_a_script_main_is_not_a_product_face(tmp_path):
    """发射点只躺在 scripts/ 的 main() 里、又没有闸门时，不许把「全仓有人跑过脚本」算成道。"""
    files = {
        "app/trace/synthproj.py": (
            "def project_synth5(event):\n"
            "    return {\"trace_id\": event[\"trace_id\"]}\n"
            "\n"
            "def synth_dispatch(event_type, event):\n"
            "    rows = []\n"
            "    if event_type == \"synth5.completed\":\n"
            "        rows.append(project_synth5(event))\n"
            "    return rows\n"),
        "scripts/synth5tool.py": (
            "def emit_synth5(payload):\n"
            "    return synth_sink.record_event(\n"
            "        trace_id=payload.trace_id,\n"
            "        event_type=\"synth5.completed\",\n"
            "    )\n"
            "\n"
            "def main():\n"
            "    emit_synth5(build_payload())\n"),
    }
    surface = _scan(_write_tree(tmp_path, files), ("project_synth5",), ("synth5.completed",))
    assert surface["routes"] == [], surface["routes"]
    assert surface["jobs"] == [], surface["jobs"]


# ------------------------------------------------------------------ 真树：沿边形状与四枚牙
def test_the_real_tree_records_the_hop_and_every_bridge_carries_a_label():
    surface = READINGS["analysis"]["retrieval_traces"]["surface"]
    assert surface["bridges"], "真树这一跳没留下任何边，翻绿就没有凭据"
    assert all(bridge["event"] for bridge in surface["bridges"]), surface["bridges"]
    assert {"declared_event", "gate_token", "event_guard"} <= {
        bridge["kind"] for bridge in surface["bridges"]}
    product = READINGS["analysis"]["retrieval_traces"]["product"]
    assert all(route["event"] for route in product["routes"]), product["routes"]
    assert not any("retrieval/debug" in route["route"] for route in product["routes"]), (
        "调试面混进了产品叠：豁免失效")


def test_declared_events_and_derived_guards_agree_on_every_table():
    for table in M.TARGET_TABLES:
        spec = M.TRIAGE[table]
        derived = set()
        for entry in spec["entries"]:
            derived |= INDEX.dispatch_events(entry)
        assert set(spec["events"]) == derived, (table, sorted(spec["events"]), sorted(derived))


def test_the_pristine_readings_report_no_problems():
    assert M.validate(READINGS) == [], M.validate(READINGS)


def test_the_old_ruling_word_is_now_the_one_that_goes_red():
    """自洽腿双向咬：把裁定按回 no_seed_path，validate() 必须当场报「裁定过期」。

    这就是「翻绿只能由自洽腿逼出来」的可复跑形态——不是谁宣布它该翻。
    """
    original = M.TRIAGE["retrieval_traces"]["verdict"]
    M.TRIAGE["retrieval_traces"]["verdict"] = "no_seed_path"
    try:
        problems = [item for item in M.validate(READINGS) if "retrieval_traces" in item]
        assert any("裁定过期" in item for item in problems), problems
    finally:
        M.TRIAGE["retrieval_traces"]["verdict"] = original


def test_an_unlabelled_cross_edge_is_refused():
    """无主的跨跳边＝后门：往现扫结果里塞一枚 via=publish 而不带事件标签，必须报 problem。"""
    surface = READINGS["analysis"]["retrieval_traces"]["surface"]
    fake = {"file": "app/x.py", "line": 1, "symbol": "ghost", "route": "POST /ghost",
            "via": "publish", "event": ""}
    surface["routes"].append(fake)
    try:
        problems = [item for item in M.validate(READINGS)
                    if "retrieval_traces" in item and "无主的跨跳边" in item]
        assert problems, M.validate(READINGS)
    finally:
        surface["routes"].remove(fake)
    assert M.validate(READINGS) == []


def test_a_drifted_event_declaration_is_reported():
    """声明多于现扫（或现扫多于声明）都必须报「不等」——不许凭散文给爬法加宽事件。"""
    original = M.TRIAGE["retrieval_traces"]["events"]
    M.TRIAGE["retrieval_traces"]["events"] = ("retrieval.completed", "ghost.completed")
    try:
        problems = [item for item in M.validate(READINGS)
                    if "retrieval_traces" in item and "声明的事件与现扫守卫到的不等" in item]
        assert problems, M.validate(READINGS)
    finally:
        M.TRIAGE["retrieval_traces"]["events"] = original
    assert M.validate(READINGS) == []