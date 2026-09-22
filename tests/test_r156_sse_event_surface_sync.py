"""R156：契约的 SSE Events 一节与 chat.py 的发射面必须同源（零手抄）。

来历：跟进单 §79 二/三。09-21 那次「sources 根本不在 canonical 名单里」是靠人眼补齐的，
而全仓没有一枚用例读过这一节 —— 人眼补的一定会第二次漂。R154 又往出处行里加了两格
（`excerpt` / `published_at`），正是最容易漂的时刻。

本件的纪律：
- **发射面**由 AST 现抠（`app/**` 里所有真会写进 `event:` 字段的名字，含 f-string 直拼与
  sink 调用两种机制），测试文件里没有第二份事件名清单。
- **契约面**由文本现解析（canonical 名单、`sources` 载荷键清单、行级字段与它的限定词、
  以及 deprecation 表里每行的 Status）。解析函数不硬编码任何事件名，抠不到就红并报"形状变了"。
- 两侧做双向比对；例外必须是**契约自己写明**的那一枚集合（表里 Status 含 "NOT emitted" 的行），
  由解析得到，不是我抄的。
"""
from __future__ import annotations

import ast
import hashlib
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO / "docs" / "api" / "contract-v1.md"
SSE_HEADING = "## SSE Events"
EMISSION_HEADING = "### What `POST /api/v1/ask` actually emits"
FRAME_FIELD = "event: "
#: 事件名的合法形状：小写单词，可带一段点分前缀。抠出不合这枚形状的东西＝解析器读错了行。
WIRE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?$")
PAYLINE_RE = re.compile(r"(?m)^`(?P<event>[a-z][a-z0-9_.]*)` payload \(.*?\):\s*$")
BULLET_KEY_RE = re.compile(r"(?m)^- `(?P<key>[a-z][a-z0-9_]*)`")
ROW_CLAIM_RE = re.compile(r"`(?P<field>[a-z][a-z0-9_]*)`[^`]*?\*\*(?P<qualifier>always present|may be absent)\*\*")
COUNT_CLAIM_RE = re.compile(r"the same (?P<numeral>one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve) payload keys")
NOT_EMITTED_RE = re.compile(r"not emitted", re.IGNORECASE)
NUMERALS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
#: 这枚差格**已关掉**（09-22 总控随本单并树补契约第五条 bullet，故集合清空、并逐字记账）。
#: 顶部这三把断言继续生效，别把它当死代码删：代码多交一枚没记名的载荷键 => 等式当场红；
#: 契约反过来点名一枚代码不交的键 => lost 当场红；有人重新往本集合塞例外 => 第三条红，
#: 逼下一个把契约补上再清空。例外不许活过它的修复，这条纪律比差格本身长。
UNDOCUMENTED_PAYLOAD_KEYS = frozenset()
SHAPE = "形状变了"


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _python_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        out += [Path(dirpath) / name for name in sorted(files) if name.endswith(".py")]
    return sorted(out)


def _functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _frame_literal(joined: ast.JoinedStr) -> str | None:
    """f-string 首段是 ``event: <字面量>`` 时返回那个名字；名字是变量时返回 None。"""
    head = joined.values[0] if joined.values else None
    if not (isinstance(head, ast.Constant) and isinstance(head.value, str) and head.value.startswith(FRAME_FIELD)):
        return None
    rest = head.value[len(FRAME_FIELD):].split("\n")[0].strip()
    return rest or None


def _name_slot(fn) -> int | None:
    """这个函数的第几号位置参数会被原样写进 ``event:`` 字段（＝一枚 sink）。"""
    params = [a.arg for a in fn.args.posonlyargs + fn.args.args]
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.JoinedStr):
            continue
        head = sub.values[0] if sub.values else None
        if not (isinstance(head, ast.Constant) and isinstance(head.value, str) and head.value.startswith(FRAME_FIELD)):
            continue
        if _frame_literal(sub) is not None:
            continue  # 名字已经写死在这枚 f-string 里，不走参数
        if len(sub.values) > 1 and isinstance(sub.values[1], ast.FormattedValue):
            inner = sub.values[1].value
            if isinstance(inner, ast.Name) and inner.id in params:
                return params.index(inner.id)
    return None


def scrape_emission_surface(app_root: Path) -> dict:
    """AST 现抠发射面：sink 表 + 每枚名字的出处站点 + 看不见的事件（盲点）。"""
    trees = {}
    for path in _python_files(app_root):
        trees[path.relative_to(app_root.parent).as_posix()] = ast.parse(path.read_text(encoding="utf-8"))
    sinks: dict[str, int] = {}
    for tree in trees.values():
        for fn in _functions(tree):
            slot = _name_slot(fn)
            if slot is not None:
                sinks[fn.name] = slot
    for _ in range(6):  # 转发关系求不动点：canonical_sse_event 把参数原样交给 sse_event
        grew = False
        for tree in trees.values():
            for fn in _functions(tree):
                if fn.name in sinks:
                    continue
                params = [a.arg for a in fn.args.posonlyargs + fn.args.args]
                for sub in ast.walk(fn):
                    if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id in sinks):
                        continue
                    slot = sinks[sub.func.id]
                    if len(sub.args) > slot and isinstance(sub.args[slot], ast.Name) and sub.args[slot].id in params:
                        sinks[fn.name] = params.index(sub.args[slot].id)
                        grew = True
        if not grew:
            break
    sites: dict[str, list] = {}
    blind: list[str] = []
    for rel, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                literal = _frame_literal(node)
                if literal is not None:
                    _site(sites, literal, rel, node.lineno, "frame-literal")
            if not isinstance(node, ast.Call):
                continue
            callee = node.func.id if isinstance(node.func, ast.Name) else (node.func.attr if isinstance(node.func, ast.Attribute) else None)
            if callee not in sinks:
                continue
            slot = sinks[callee]
            value = None
            if len(node.args) > slot and isinstance(node.args[slot], ast.Constant):
                value = node.args[slot].value
            for kw in node.keywords:
                if kw.arg in ("event_name", "event") and isinstance(kw.value, ast.Constant):
                    value = kw.value.value
            if isinstance(value, str):
                _site(sites, value, rel, node.lineno, "sink-call:%s" % callee)
                continue
            owner = _enclosing_function(tree, node)
            if owner not in sinks:  # 名字来自变量、又不属于任何已登记的转发腿 -> 这枚读数我看不见
                blind.append("%s:%d sse frame name from a non-sink scope (%s)" % (rel, node.lineno, owner or "<module>"))
    return {"sinks": sinks, "sites": sites, "blind_spots": blind}


def _site(sites: dict, name: str, rel: str, lineno: int, mechanism: str) -> None:
    if not WIRE_NAME_RE.match(name):
        raise AssertionError("%s：从 %s:%d 抠出来的 %r 不合事件名形状，读错了行" % (SHAPE, rel, lineno, name))
    sites.setdefault(name, []).append((rel, lineno, mechanism))


def _enclosing_function(tree: ast.AST, target: ast.AST) -> str | None:
    for fn in _functions(tree):
        for sub in ast.walk(fn):
            if sub is target:
                return fn.name
    return None


def _section(text: str, heading: str) -> str:
    if heading not in text:
        raise AssertionError("%s：契约里找不到锚 `%s`" % (SHAPE, heading))
    rest = text[text.index(heading) + len(heading):]
    for stop in ("\n## ", "\n### "):
        pass
    cut = len(rest)
    idx = rest.find("\n## ")
    if idx != -1:
        cut = idx
    return rest[:cut]


def parse_contract(text: str) -> dict:
    """契约现解析：canonical 名单、载荷键清单、行级字段限定词、deprecation 表的逐行 Status。"""
    # "契约是纯 CRLF"：\r\n 不折掉就切不出空行，canonical 名单会把整节的反引号词全吞进来
    text = text.replace("\r\n", "\n")
    sse = _section(text, SSE_HEADING)
    deprecation = _section(text, EMISSION_HEADING)

    anchor = "canonical event names are:"
    if anchor not in sse:
        raise AssertionError("%s：SSE Events 一节里找不到 canonical 名单的引导句" % SHAPE)
    anchor_line = sse[sse.index(anchor):].split("\n", 1)[0]
    continuation = sse[sse.index(anchor):].split("\n", 1)[1].split("\n\n", 1)[0]
    paragraph = anchor_line + "\n" + continuation
    tokens = re.findall(r"`([^`]+)`", paragraph)
    canonical = {t for t in tokens if WIRE_NAME_RE.match(t)}
    if len(canonical) < 5:
        raise AssertionError("%s：canonical 名单解析出 %d 枚，名单形状变了" % (SHAPE, len(canonical)))

    payload_line = PAYLINE_RE.search(sse)
    if not payload_line:
        raise AssertionError("%s：找不到 ``<event>` payload (...)`` 那一行" % SHAPE)
    payload_event = payload_line.group("event")
    block = sse[payload_line.end():].split("\n\n", 1)[0]
    payload_keys = set(BULLET_KEY_RE.findall(block))
    if not payload_keys:
        raise AssertionError("%s：%s 的载荷键清单抠不到" % (SHAPE, payload_event))
    row_claims = [(m.group("field"), m.group("qualifier")) for m in ROW_CLAIM_RE.finditer(block)]
    if not row_claims:
        raise AssertionError("%s：载荷清单里没有带限定词的行级字段" % SHAPE)
    numerals = COUNT_CLAIM_RE.findall(sse)
    if len(set(numerals)) != 1:
        raise AssertionError("%s：契约对载荷键数的自述不唯一或读不到（%r）" % (SHAPE, numerals))
    claimed_keys = NUMERALS[numerals[0]]

    lines: list[str] = []
    for line in deprecation.split("\n"):  # only the contiguous table: rows of any
        if line.startswith("|"):          # later table in the section are field names
            lines.append(line)
        elif lines:
            break
    if len(lines) < 2:
        raise AssertionError("%s：发射表现只剩表头，形状变了" % SHAPE)
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    try:
        name_col = next(i for i, cell in enumerate(header) if "event name" in cell.lower())
        status_col = next(i for i, cell in enumerate(header) if cell.lower() == "status")
    except StopIteration:
        raise AssertionError("%s：发射表列名不是 Event names / Status 了" % SHAPE) from None
    rows = []
    for line in lines[1:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < max(name_col, status_col) + 1:
            raise AssertionError("%s：发射表有一行列数不对：%r" % (SHAPE, line[:60]))
        if set(cells[0]) <= {"-", " "}:
            continue
        names = {c for c in re.findall(r"`([^`]+)`", cells[name_col]) if WIRE_NAME_RE.match(c)}
        rows.append({"emitter": cells[0], "names": names, "status": cells[status_col],
                     "declared_not_emitted": bool(NOT_EMITTED_RE.search(cells[status_col]))})
    if not rows:
        raise AssertionError("%s：发射表没有数据行" % SHAPE)
    table_names = set().union(*[r["names"] for r in rows])
    declared = set().union(*[r["names"] for r in rows if r["declared_not_emitted"]])
    claimed_emitted = set().union(*[r["names"] for r in rows if not r["declared_not_emitted"]])
    return {
        "canonical": canonical,
        "payload_event": payload_event,
        "payload_keys": payload_keys,
        "row_claims": dict(row_claims),
        "claimed_key_count": claimed_keys,
        "rows": rows,
        "recorded": canonical | table_names,
        "declared_not_emitted": declared,
        "declared_emitted": claimed_emitted,
    }


def row_shape_from_code(module_text: str, always_field: str) -> dict:
    """按契约的限定词找出行构造器：返回枚该字段的那个 dict 字面量的键，以及条件赋值。"""
    tree = ast.parse(module_text)
    candidates = []
    for fn in _functions(tree):
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
                keys = [k.value for k in sub.value.keys if isinstance(k, ast.Constant)]
                if always_field in keys:
                    candidates.append((fn.name, fn.lineno, keys))
    if not candidates:
        raise AssertionError("%s：契约说 %r 是行里 always present 的一格，但本模块没有任何构造器无条件交出它"
                             % (SHAPE, always_field))
    if len({name for name, _, _ in candidates}) > 1:
        raise AssertionError("%s：无条件交出 %r 的构造器不唯一（%s），指针该由人重看"
                             % (SHAPE, always_field, sorted({c[0] for c in candidates})))
    name, lineno, keys = candidates[0]
    conditional: set[str] = set()
    for fn in _functions(tree):
        guarded = {id(node) for node in ast.walk(fn) if isinstance(node, ast.If)}
        parents = {}
        for node in ast.walk(fn):
            for child in ast.iter_child_nodes(node):
                parents[id(child)] = node
        for node in ast.walk(fn):
            if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Subscript):
                continue
            target = node.targets[0]
            if not (isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str)):
                continue
            walk, inside = node, False
            while walk is not None:
                if id(walk) in guarded:
                    inside = True
                    break
                walk = parents.get(id(walk))
            if inside:
                conditional.add(target.slice.value)
    return {"builder": name, "builder_lineno": lineno, "keys": keys, "conditional": conditional}


def payload_key_sets_from_code(app_root: Path, payload_event: str) -> list:
    """每一处真发这枚事件的地方，交出的载荷顶层键集合。"""
    found = []
    for path in _python_files(app_root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            args = [a.value for a in node.args if isinstance(a, ast.Constant)]
            if payload_event not in args:
                continue
            data = next((kw.value for kw in node.keywords if kw.arg == "data"), None)
            if not isinstance(data, ast.Dict):
                continue
            found.append((path.relative_to(app_root.parent).as_posix(), node.lineno,
                          [k.value for k in data.keys if isinstance(k, ast.Constant)]))
    if not found:
        raise AssertionError("%s：契约记为 `%s` payload 的那枚事件，代码里一处都没发" % (SHAPE, payload_event))
    return found


def check_scrape_is_healthy(scrape: dict) -> None:
    assert scrape["sinks"], "%s：没认出任何构造 event: 帧的函数" % SHAPE
    assert scrape["sites"], "%s：发射面抠出来是空的" % SHAPE
    mechanisms = {m for sites in scrape["sites"].values() for _, _, m in sites}
    assert any(m == "frame-literal" for m in mechanisms), "%s：f-string 直拼那条腿没读到东西" % SHAPE
    assert any(m.startswith("sink-call:") for m in mechanisms), "%s：sink 调用那条腿没读到东西" % SHAPE
    assert not scrape["blind_spots"], "有一处 event 帧的名字来自我看不见的scope，比对不作数：%s" % scrape["blind_spots"]


def check_emitted_are_recorded(scrape: dict, contract: dict) -> None:
    emitted = set(scrape["sites"])
    missing = sorted(emitted - contract["recorded"])
    assert not missing, ("代码在发而契约没记的事件名：%s" % missing)


def check_recorded_are_emitted_or_declared(scrape: dict, contract: dict) -> None:
    emitted = set(scrape["sites"])
    silent = sorted((contract["recorded"] - emitted) - contract["declared_not_emitted"])
    assert not silent, ("契约记了而全仓发射不到、且那一行又没写明尚未发射：%s" % silent)
    stale = sorted(contract["declared_not_emitted"] - contract["recorded"])
    assert not stale, "发射表里说尚未发射的名字，已不在 SSE Events 名单里：%s" % stale
    overtaken = sorted(contract["declared_not_emitted"] & emitted)
    assert not overtaken, "发射表还写着尚未发射、代码其实已经在发：%s" % overtaken
    both = sorted(contract["declared_not_emitted"] & contract["declared_emitted"])
    assert not both, "同一枚名字在表里既被说成已发又被说成未发：%s" % both


def check_payload_keys_are_documented(scrape: dict, contract: dict, code_sites: list) -> None:
    names = {name for name in scrape["sites"] if name == contract["payload_event"]}
    assert names, "契约把 payload 形状记在 `%s` 名下，代码却没发这枚事件" % contract["payload_event"]
    shapes = {frozenset(keys) for _, _, keys in code_sites}
    assert len(shapes) == 1, "同一个事件的各处发射点载荷键不一致：%s" % sorted(sorted(s) for s in shapes)
    code_keys = set(next(iter(shapes)))
    undocumented = sorted(code_keys - contract["payload_keys"])
    assert set(undocumented) == set(UNDOCUMENTED_PAYLOAD_KEYS), (
        "代码在交而契约没点名的载荷键集合变了（期望只差已挂号的那一枚，实际 %s）" % undocumented)
    assert not (UNDOCUMENTED_PAYLOAD_KEYS & contract["payload_keys"]), (
        "契约已经补记了 %s，请把本件顶部那枚差格集合清空——例外不许活过它的修复"
        % sorted(UNDOCUMENTED_PAYLOAD_KEYS & contract["payload_keys"]))
    lost = sorted(contract["payload_keys"] - code_keys)
    assert not lost, "契约点名的载荷键，代码已经不交了：%s" % lost
    assert contract["claimed_key_count"] == len(code_keys), (
        "契约自述载荷有 %d 枚键，代码真交 %d 枚" % (contract["claimed_key_count"], len(code_keys)))


def check_row_fields_match_their_qualifiers(module_text: str, contract: dict) -> None:
    always = sorted(f for f, q in contract["row_claims"].items() if q == "always present")
    optional = sorted(f for f, q in contract["row_claims"].items() if q == "may be absent")
    assert always or optional, "%s：契约行级散文里没有任何带限定词的字段" % SHAPE
    shape = row_shape_from_code(module_text, always[0] if always else optional[0])
    for field in always:
        assert field in shape["keys"], "契约说 %r 在每一行里 always present，构造器却没无条件给这一格" % field
    for field in optional:
        assert field not in shape["keys"], "契约说 %r may be absent，构造器却把它写成了必然存在" % field
        assert field in shape["conditional"], "契约说 %r may be absent，代码里找不到任何条件给它的地方" % field


# ==================== 用例 ====================


def _state() -> tuple:
    contract = parse_contract(_read_text(CONTRACT_PATH))
    scrape = scrape_emission_surface(REPO / "app")
    sites = payload_key_sets_from_code(REPO / "app", contract["payload_event"])
    module_text = (REPO / sites[0][0]).read_text(encoding="utf-8")
    return contract, scrape, sites, module_text


def test_the_emission_surface_is_actually_scraped_from_source():
    """非空转：两种机制各读到东西，每一枚名字都有具名出处，且不留下看不见的事件。"""
    contract, scrape, _, _ = _state()
    check_scrape_is_healthy(scrape)
    assert len(scrape["sites"]) >= 10, "发射面只抠到 %d 枚名字，怀疑读错了行" % len(scrape["sites"])
    assert sum(len(v) for v in scrape["sites"].values()) >= 25, "出处站点太少，比对不成立"
    for name, entries in scrape["sites"].items():
        assert entries and all(rel and line for rel, line, _ in entries), name
    assert contract["payload_event"] in scrape["sites"], "契约记载荷的那枚事件，发射面里没有"


def test_no_real_event_name_is_written_by_hand_in_this_file():
    """判据①的零手抄：两侧任何一枚带点的真名，都不许出现在本件里。

    带点的那批（canonical 名单）正是最容易被人"顺手抄一份"进测试的地方，单字词
    （step / text / done）在散文里躲不开，也就不构成第二份名单。
    """
    contract, scrape, _, _ = _state()
    text = Path(__file__).read_text(encoding="utf-8")
    dotted = {n for n in (contract["recorded"] | set(scrape["sites"])) if "." in n}
    assert dotted, "两侧都没有带点事件名，这枚断言就空了——先确认解析没瞎"
    strays = sorted(n for n in dotted if n in text)
    assert not strays, "本件里抄了真事件名（%s）：名单只许从代码与契约现解析" % strays
    # 散文里提一笔名字不算抄，抄成数据才算：本件不许出现一枚含两枚以上真事件名的字面量集合。
    wire = contract["recorded"] | set(scrape["sites"])
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Set, ast.Tuple)):
            continue
        copied = [e.value for e in node.elts
                  if isinstance(e, ast.Constant) and isinstance(e.value, str) and e.value in wire]
        assert len(copied) <= 1, ("本件把事件名抄成了字面量集合 %s：名单只许从代码与契约现解析" % copied)



def test_the_contract_side_anchors_all_exist():
    """判据②：解析不出东西就是红，而且要说清是形状变了。"""
    contract, _, _, _ = _state()
    assert contract["canonical"], "canonical 名单为空"
    assert len(contract["rows"]) >= 3, "发射表行数异常：%d" % len(contract["rows"])
    assert contract["row_claims"], "行级字段限定词读不到"
    assert contract["claimed_key_count"] > 0


def test_every_emitted_event_name_is_recorded_in_the_contract():
    contract, scrape, _, _ = _state()
    check_emitted_are_recorded(scrape, contract)


def test_every_recorded_event_name_is_emitted_or_declared_unemitted():
    """判据③的双向半边：例外只能是契约自己写明的那一枚集合。"""
    contract, scrape, _, _ = _state()
    check_recorded_are_emitted_or_declared(scrape, contract)
    declared = contract["declared_not_emitted"]
    assert declared == {n for r in contract["rows"] if r["declared_not_emitted"] for n in r["names"]}
    assert declared, "契约里那行「尚未发射」的例外整行没了——名单与发射面此刻是否还差十枚，得由人重看"
    unexplained = sorted((contract["recorded"] - set(scrape["sites"])) - declared)
    assert not unexplained, unexplained


def test_the_sources_payload_keys_are_the_documented_set():
    contract, scrape, sites, _ = _state()
    check_payload_keys_are_documented(scrape, contract, sites)
    assert len(sites) >= 3, "载荷比对只看到 %d 处发射点，缓存腿/续跑腿是否还在？" % len(sites)


def test_the_row_fields_mean_what_the_contract_prose_says():
    contract, _, _, module_text = _state()
    check_row_fields_match_their_qualifiers(module_text, contract)


def test_this_file_adds_no_skip_and_no_xfail():
    """判据⑥：本件不许用 skip/xfail 过关。"""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    banned = {"skip", "xfail", "skipif"}
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in banned:
            hits.append(node.col_lineno if hasattr(node, "col_lineno") else node.lineno)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in banned:
            hits.append(node.lineno)
        if isinstance(node, ast.ClassDef) or isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                text = ast.unparse(dec)
                if "mark.skip" in text or "mark.xfail" in text:
                    hits.append(node.lineno)
    assert not hits, "本件里出现了 skip/xfail：%s" % hits


# ==================== 判据⑤：反证（临时改文件 -> 具名用例红 -> finally 逐字节还原） ====================


class _TempEdit:
    """按字节进出的一枚临时变异；退出时不论断言成败都还原，并留 sha 证据。"""

    def __init__(self, path: Path, old: str, new: str, every: bool = False):
        self.path = path
        self.old = old
        self.new = new
        self.every = every
        self.info: dict = {}

    def __enter__(self):
        raw = self.path.read_bytes().decode("utf-8")
        self.info = {"before": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16], "raw": raw}
        n = raw.count(self.old)
        assert n >= 1, "%s 里找不到待改的锚：%r" % (self.path.name, self.old[:60])
        edited = raw.replace(self.old, self.new) if self.every else raw.replace(self.old, self.new, 1)
        assert edited != raw
        self.path.write_bytes(edited.encode("utf-8"))
        return self.info

    def __exit__(self, *exc):
        self.path.write_bytes(self.info["raw"].encode("utf-8"))
        after = sha256_of(self.path)
        self.info["after"] = after
        self.info["restored"] = after == self.info["before"]
        print("[r156] %s %s -> %s restored=%s" % (self.path.name, self.info["before"], after, self.info["restored"]))
        return False


def _first_sink_site(scrape: dict) -> tuple:
    """取一处"sink 调用+字面名"的站点，函数名从机制标签里导出，不写死。"""
    for name in sorted(scrape["sites"]):
        for rel, lineno, mechanism in scrape["sites"][name]:
            if mechanism.startswith("sink-call:"):
                return name, rel, lineno, mechanism.split(":", 1)[1]
    raise AssertionError("发射面里没有 sink-call 站点，反证没法做")


def test_counter_evidence_a_renamed_emission_turns_the_forward_pin_red():
    contract, scrape, _, _ = _state()
    check_emitted_are_recorded(scrape, contract)
    name, rel, _, callee = _first_sink_site(scrape)
    probe = "%s.probe" % name
    path = REPO / rel
    with _TempEdit(path, '%s("%s"' % (callee, name), '%s("%s"' % (callee, probe)) as info:
        contract2, scrape2, _, _ = _state()
        with pytest.raises(AssertionError) as exc:
            check_emitted_are_recorded(scrape2, contract2)
        assert probe in str(exc.value), str(exc.value)
    assert info["restored"], "临时变异没还原：%s" % info
    assert info["before"] == info["after"]


def test_counter_evidence_a_dropped_contract_name_turns_the_forward_pin_red():
    contract, scrape, _, _ = _state()
    picked = sorted(set(scrape["sites"]) & contract["recorded"])[0]
    with _TempEdit(CONTRACT_PATH, "`%s`" % picked, "", every=True) as info:
        contract2, scrape2, _, _ = _state()
        assert picked not in contract2["recorded"], "摘掉 %r 之后它仍被记着，解析没吃到这一处" % picked
        with pytest.raises(AssertionError) as exc:
            check_emitted_are_recorded(scrape2, contract2)
        assert picked in str(exc.value), str(exc.value)
    assert info["restored"] and info["before"] == info["after"], info


def test_counter_evidence_losing_the_always_present_row_field_turns_red():
    contract, _, sites, _ = _state()
    always = sorted(f for f, q in contract["row_claims"].items() if q == "always present")
    assert always, "契约没有 always present 的行级字段，反证没法做"
    field = always[0]
    module_path = REPO / sites[0][0]
    raw = module_path.read_bytes().decode("utf-8")
    line = next(l for l in raw.split("\n") if l.rstrip("\r").strip().startswith('"%s":' % field)).rstrip("\r")
    with _TempEdit(module_path, line + "\r\n", "") as info:
        contract2, _, _, module_text2 = _state()
        with pytest.raises(AssertionError) as exc:
            check_row_fields_match_their_qualifiers(module_text2, contract2)
        assert field in str(exc.value), str(exc.value)
    assert info["restored"] and info["before"] == info["after"], info


def test_counter_evidence_a_name_only_the_contract_invents_turns_the_backward_pin_red():
    fake = "zephyr.handoff"
    with _TempEdit(CONTRACT_PATH, "canonical event names are:", "canonical event names are: `%s`," % fake) as info:
        contract2, scrape2, _, _ = _state()
        assert fake in contract2["recorded"]
        with pytest.raises(AssertionError) as exc:
            check_recorded_are_emitted_or_declared(scrape2, contract2)
        assert fake in str(exc.value), str(exc.value)
    assert info["restored"] and info["before"] == info["after"], info


def test_counter_evidence_a_dropped_payload_bullet_turns_the_key_pin_red():
    contract, _, _, _ = _state()
    key = sorted(contract["payload_keys"])[0]
    with _TempEdit(CONTRACT_PATH, "- `%s`" % key, "- `%s`" % key.upper(), every=True) as info:
        contract2, scrape2, sites2, _ = _state()
        assert key not in contract2["payload_keys"], "解析没吃到这一处"
        with pytest.raises(AssertionError) as exc:
            check_payload_keys_are_documented(scrape2, contract2, sites2)
        assert key in str(exc.value), str(exc.value)
    assert info["restored"] and info["before"] == info["after"], info