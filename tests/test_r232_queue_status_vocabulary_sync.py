"""R232 : the contract `## Long Task Status` status enum must come from the code (zero hand-copy).

来历：契约把客户端读得到的 status 说成 "one of 六枚"，而 `app/common/reliable_queue.py` 现场往
`_status_key` 写的是七枚，`app/api/v1/chat.py` 那支 `/queue/status/{request_id}` 路由在状态键读不到时
还另造一枚 —— 少记的两枚（failed / cancel_requested）客户照文档写客户端就当未知值处理。R227 交回时写的
"状态词表一个新字未加"是真话：它没造新字，文档本来就少两个字，既存漂移，两回事。

本件不修代码（本单是文档追代码），钉的是"补齐之后不许再漂"，纪律四条：
* 代码面由 AST 现抠：每一处 `redis.set(self._status_key(...), "<字面量>")` 算一枚；写成变量或任何不合
  字面量形状的站点记进 blind_spots，非空即红 —— 看不见比看得见更危险。本文件没有第二份词表。
* 出处分层同样由 AST 推导：路由自己写死的 status 字面量减去队列真写过的，才是"路由现造的"那一格。契约给
  每枚值标注的出处必须与这个推导逐枚相等，把两层的来源混在一起写本件红。
* 契约面由文本现解析（枚举行 + 逐值那一行的终态与出处标注），解析函数不硬编码任何值名。
* 反证在内存里做：往契约枚举多记一枚、从契约枚举摘掉代码真写的一枚、往队列源码的内存副本多插一处 status
  写入，三样各自当场红。产品代码零字节落盘（最后一枚反证自己复核 sha256）。

全程离线：输入只有两枚 `.py` 与一枚 `.md` 的文本，不连 redis、不起容器、不打模型、不发 `/api/v1/ask`。
"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
QUEUE_SOURCE_PATH = REPO / "app" / "common" / "reliable_queue.py"
CHAT_SOURCE_PATH = REPO / "app" / "api" / "v1" / "chat.py"
CONTRACT_DOC = REPO / "docs" / "api" / "contract-v1.md"
QUEUE_ORIGIN = "app/common/reliable_queue.py"
CHAT_ORIGIN = "app/api/v1/chat.py"

#: 本节在契约里的位置（按 `## ` 标题定位，别按行号 —— 行号会为别人的一次编辑而漂）。
STATUS_SECTION_HEADING = "## Long Task Status"
STATUS_KEY_METHOD = "_status_key"
STATUS_DICT_KEY = "status"
ROUTE_PATH_FRAGMENT = "/queue/status/"
QUEUE_LAYER = "written by the queue"
ROUTE_LAYER = "answered by the route"
TERMINAL = "terminal"
NON_TERMINAL = "non-terminal"
#: 反证用的假值：两侧都不该有它，它出现在哪一栏就说明哪一栏真的被读到了。
PROBE = "probe_value_that_nobody_writes"

SHAPE = "shape changed"
WORD_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ENUM_RE = re.compile(r"^`status` is one of (?P<values>.+)\.$", re.MULTILINE)
BACKTICK_RE = re.compile(r"`([a-z][a-z0-9_]*)`")
BULLET_RE = re.compile(
    r"^\* `(?P<value>[a-z][a-z0-9_]*)` "
    r"\((?P<phase>non-terminal|terminal), "
    r"(?P<layer>written by the queue|answered by the route)\): "
    r"(?P<prose>.+)$"
)
WRITE_CALL_RE = re.compile(r"\.set\([^)]*_status_key\(")


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _site(value: str, sites: dict) -> str:
    """一枚值的全部出处，形如 `app/common/reliable_queue.py:216`，逐枚可对。"""
    return " ".join("%s:%d" % (origin, lineno) for origin, lineno in sites.get(value, []))


def _status_writes_in(source: str, origin: str) -> dict:
    """AST 现抠队列往 status 键写过的每一个字面量，不猜、不抄。"""
    written: dict = {}
    blind: list = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "set"):
            continue
        target = node.args[0] if node.args else None
        if not (
            isinstance(target, ast.Call)
            and isinstance(target.func, ast.Attribute)
            and target.func.attr == STATUS_KEY_METHOD
        ):
            continue
        value = node.args[1] if len(node.args) > 1 else None
        for keyword in node.keywords:
            if keyword.arg == "value":
                value = keyword.value
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            blind.append("%s:%d 写进 status 键的不是字符串字面量，本件读不到它的取值" % (origin, node.lineno))
            continue
        if not WORD_RE.match(value.value):
            raise AssertionError(
                "%s：%s:%d 抠出来的 %r 不合状态词形状，解析器读错了行" % (SHAPE, origin, node.lineno, value.value)
            )
        written.setdefault(value.value, []).append((origin, node.lineno))
    if not written:
        raise AssertionError("%s：%s 里一处 status 写入都没抠到，比对失去对象" % (SHAPE, origin))
    return {"sites": written, "blind_spots": blind, "textual": len(WRITE_CALL_RE.findall(source))}


def _route_readings_in(source: str, origin: str) -> dict:
    """AST 现抠那支轮询路由：它自己写死了哪些 status 值，又把哪些值原样转发。"""
    route = None
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            path = decorator.args[0]
            if isinstance(path, ast.Constant) and isinstance(path.value, str) and ROUTE_PATH_FRAGMENT in path.value:
                if route is not None:
                    raise AssertionError("%s：%s 里有多于一支 %s 路由" % (SHAPE, origin, ROUTE_PATH_FRAGMENT))
                route = node
    if route is None:
        raise AssertionError("%s：%s 里找不到 %s 那支路由" % (SHAPE, origin, ROUTE_PATH_FRAGMENT))

    literals: dict = {}
    forwarded: list = []
    blind: list = []
    for node in ast.walk(route):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and key.value == STATUS_DICT_KEY):
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                literals[value.value] = node.lineno
            elif isinstance(value, ast.Name):
                forwarded.append("%s:%d 原样转发 %s" % (origin, node.lineno, value.id))
            else:
                blind.append("%s:%d status 键的取值既不是字面量也不是转发，本件读不到它" % (origin, node.lineno))
    return {"function": route.name, "literals": literals, "forwarded": forwarded, "blind_spots": blind}


def _code_side(queue_source: str | None = None, chat_source: str | None = None) -> dict:
    queue = _status_writes_in(
        _read_text(QUEUE_SOURCE_PATH) if queue_source is None else queue_source, QUEUE_ORIGIN
    )
    route = _route_readings_in(
        _read_text(CHAT_SOURCE_PATH) if chat_source is None else chat_source, CHAT_ORIGIN
    )
    queue_values = set(queue["sites"])
    #: 路由写死而队列从不写的值，才是"路由现造的"那一格 —— 出处不同，不许混进队列词表。
    route_only = {value: line for value, line in sorted(route["literals"].items()) if value not in queue_values}
    return {
        "queue_sites": queue["sites"],
        "queue_values": queue_values,
        "queue_sites_total": sum(len(rows) for rows in queue["sites"].values()),
        "queue_sites_textual": queue["textual"],
        "route": route,
        "route_only": route_only,
        "answers": queue_values | set(route_only),
        "blind_spots": queue["blind_spots"] + route["blind_spots"],
    }


def _section(text: str) -> str:
    if STATUS_SECTION_HEADING not in text:
        raise AssertionError("%s：契约里找不到锚 `%s`（改名即改钉，别指望它替你沉默）" % (SHAPE, STATUS_SECTION_HEADING))
    rest = text[text.index(STATUS_SECTION_HEADING) + len(STATUS_SECTION_HEADING):]
    cut = rest.find("\n## ")
    return rest[: cut if cut != -1 else len(rest)]


def parse_contract(text: str) -> dict:
    """契约现解析：枚举句的取值清单 + 逐值那一行的终态与出处标注。不硬编码任何值名。"""
    #: "契约是纯 CRLF"：\r\n 不折掉就切不出行，枚举行与逐值清单都会解析失败
    section = _section(text.replace("\r\n", "\n"))

    match = ENUM_RE.search(section)
    if match is None:
        raise AssertionError("%s：本节没有以 `status` is one of 开头、以句号结尾的那枚枚举句" % SHAPE)
    enum = BACKTICK_RE.findall(match.group("values"))
    if len(set(enum)) != len(enum):
        raise AssertionError("%s：枚举句里同一枚值被记了两遍：%s" % (SHAPE, enum))

    rows: dict = {}
    unparsed: list = []
    lines = section.split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith("* "):
            index += 1
            continue
        bullet = BULLET_RE.match(line.rstrip())
        if bullet is None:
            unparsed.append("%s" % line.strip()[:60])
            index += 1
            continue
        prose = [bullet.group("prose")]
        while (
            index + 1 < len(lines)
            and lines[index + 1].strip()
            and not lines[index + 1].startswith(("* ", "| ", "# ", "> "))
        ):
            prose.append(lines[index + 1].strip())
            index += 1
        value = bullet.group("value")
        if value in rows:
            raise AssertionError("%s：契约把 %r 记了两遍" % (SHAPE, value))
        rows[value] = {"phase": bullet.group("phase"), "layer": bullet.group("layer"), "prose": " ".join(prose)}
        index += 1
    return {"enum": enum, "rows": rows, "unparsed_bullets": unparsed, "sentence": match.group(0)}


def _contract_side() -> dict:
    return parse_contract(_read_text(CONTRACT_DOC))


# ==================== 双向比对（反证钉复用这两枚，只换内存输入） ====================


def check_the_enum_matches_what_the_code_answers(code: dict, contract: dict) -> None:
    """判据①：契约枚举 == 队列写过的 并 路由现造的，逐枚相等，多一枚少一枚都红。"""
    documented = set(contract["enum"])
    missing = sorted(code["answers"] - documented)
    invented = sorted(documented - code["answers"])
    assert not missing, "契约的枚举行漏了代码真会答的值：%s" % "; ".join(
        "`%s` 由 %s 答，文档没记" % (value, _site(value, code["queue_sites"]) or "the route") for value in missing
    )
    assert not invented, "契约记了代码从不答的值：%s" % "; ".join(
        "`%s` 无处可证（队列站点：%s）" % (value, _site(value, code["queue_sites"]) or "none") for value in invented
    )


def check_the_documented_layers_keep_their_provenance(code: dict, contract: dict) -> None:
    """判据⑦：每枚值的出处标注必须与 AST 推导逐枚相等 —— 路由现造的那枚不许写成队列写的。"""
    claimed_queue = {value for value, row in contract["rows"].items() if row["layer"] == QUEUE_LAYER}
    claimed_route = {value for value, row in contract["rows"].items() if row["layer"] == ROUTE_LAYER}
    assert claimed_queue == code["queue_values"], "标注为 `%s` 的集合与队列真写过的不等：多记 %s，漏记 %s" % (
        QUEUE_LAYER,
        sorted(claimed_queue - code["queue_values"]),
        sorted(code["queue_values"] - claimed_queue),
    )
    assert claimed_route == set(code["route_only"]), "标注为 `%s` 的集合与路由现造的不等：多记 %s，漏记 %s" % (
        ROUTE_LAYER,
        sorted(claimed_route - set(code["route_only"])),
        sorted(set(code["route_only"]) - claimed_route),
    )


# ==================== 正钉 ====================


def test_the_queue_source_really_is_scraped_and_not_copied():
    """非空转：站点数、取值数、文本计数三样对得上，且不留下读不见的写入。"""
    code = _code_side()
    assert len(code["queue_values"]) >= 5, "队列侧只抠到 %d 枚值，怀疑读错了行" % len(code["queue_values"])
    assert code["queue_sites_total"] >= 10, "写入站点太少，比对不成立"
    for value, rows in code["queue_sites"].items():
        assert rows and all(origin and lineno for origin, lineno in rows), value
    assert not code["blind_spots"], "有 status 写入本件读不到：%s" % code["blind_spots"]
    assert code["queue_sites_total"] + len(code["blind_spots"]) == code["queue_sites_textual"], (
        "AST 抠到的站点数与文本里 `set(self._status_key(` 的枚数对不上，解析器漏了腿"
    )


def test_the_route_forwards_the_status_it_reads_verbatim():
    """漏记之所以是客户真会撞上的假话，凭据是路由确实把状态键原样转发出去。"""
    code = _code_side()
    assert code["route"]["forwarded"], "路由没有原样转发的腿，未记名的值未必到得了客户端"
    assert code["route_only"], "路由没现造任何值，分层出处这枚钉无从谈起"
    for value, lineno in code["route_only"].items():
        assert value not in code["queue_sites"], "%s 其实由队列写过（%s），出处不是路由" % (value, lineno)


def test_the_contract_side_anchors_all_exist():
    contract = _contract_side()
    assert contract["enum"], "枚举句里一枚值都没解析到"
    assert not contract["unparsed_bullets"], "%s：本节出现了不合逐值语法的 bullet 行，解析器不敢猜：%s" % (
        SHAPE,
        " / ".join(contract["unparsed_bullets"]),
    )


def test_the_documented_enum_is_the_vocabulary_the_code_answers():
    """判据①主钉：修前必红，且红的就是缺 failed 与 cancel_requested 那两枚。"""
    check_the_enum_matches_what_the_code_answers(_code_side(), _contract_side())


def test_every_documented_value_explains_when_a_client_reads_it():
    """判据②：枚举行点名的每一枚都要有逐值那一行，且真的写了一句话。"""
    contract = _contract_side()
    documented = set(contract["enum"])
    assert set(contract["rows"]) == documented, "枚举行与逐值清单不等：只在枚举行 %s，只在逐值清单 %s" % (
        sorted(documented - set(contract["rows"])),
        sorted(set(contract["rows"]) - documented),
    )
    for value, row in sorted(contract["rows"].items()):
        prose = row["prose"]
        assert len(prose) >= 40, "`%s` 那一行没成句：%r" % (value, prose)
        assert prose.endswith("."), "`%s` 那一行没收尾：%r" % (value, prose[-20:])


def test_the_terminal_partition_covers_every_value_exactly_once():
    """判据②：终态/非终态这条线（R221/R222/R227 三代人的口径）不许漏标，也不许两标。"""
    contract = _contract_side()
    phases = {value: row["phase"] for value, row in contract["rows"].items()}
    assert set(phases.values()) <= {TERMINAL, NON_TERMINAL}, sorted(phases.values())
    terminal = {value for value, phase in phases.items() if phase == TERMINAL}
    non_terminal = {value for value, phase in phases.items() if phase == NON_TERMINAL}
    assert terminal and non_terminal, "某一栏空了，逐值清单没在分终态"
    assert terminal | non_terminal == set(contract["enum"]), sorted(set(contract["enum"]) - set(phases))
    assert not (terminal & non_terminal), sorted(terminal & non_terminal)
    ordered = [row["phase"] for row in contract["rows"].values()]
    assert ordered == sorted(ordered, key=lambda phase: phase != NON_TERMINAL), (
        "逐值清单要按「非终态在前、终态在后」排，读的人一眼看得见轮询什么时候该停"
    )


def test_the_documented_layers_name_the_layer_that_actually_writes_them():
    """判据⑦主钉：出处按层分列，路由现造的那枚（今天只有 expired）不许算成队列写的。"""
    check_the_documented_layers_keep_their_provenance(_code_side(), _contract_side())


def test_this_file_adds_no_skip_and_no_xfail():
    tree = ast.parse(Path(__file__).read_bytes().decode("utf-8"))
    banned = {"skip", "xfail", "skipif"}
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in banned:
            hits.append(node.lineno)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            for decorator in node.decorator_list:
                text = ast.unparse(decorator)
                if "mark.skip" in text or "mark.xfail" in text or "mark.parametrize" in text:
                    hits.append(node.lineno)
    assert not hits, "本件里出现了 skip/xfail/parametrize：%s" % hits


def test_no_hand_copied_status_vocabulary_lives_in_this_file():
    """零手抄：本件里不许出现"两枚以上真值装进一枚字面量集合"的第二份词表。"""
    answers = _code_side()["answers"]
    tree = ast.parse(Path(__file__).read_bytes().decode("utf-8"))
    copied = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Set, ast.List, ast.Tuple)):
            continue
        words = [item.value for item in node.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)]
        if len(words) >= 2 and set(words) & answers:
            copied.append("第 %d 行 %s" % (node.lineno, words))
    assert not copied, "本件里出现了手抄的词表：%s" % copied


# ==================== 反证（全部走内存输入，产品代码零落盘） ====================


def _enum_line(text: str) -> str:
    lines = text.split("\n")
    return next(row for row in lines if row.startswith("`status` is one of"))


def _drop_from_the_enum(text: str, value: str) -> str:
    line = _enum_line(text)
    for needle in ("`%s`, " % value, "`%s` or " % value, ", or `%s`." % value, " `%s`." % value):
        if needle in line:
            patched = line.replace(needle, "" if needle.endswith(" ") else ".")
            assert value not in patched.replace("`%s`" % value, ""), "%s：没能把 %r 摘干净" % (SHAPE, value)
            return text.replace(line, patched)
    raise AssertionError("%s：枚举行里找不到 %r，反证没法做" % (SHAPE, value))


def _add_to_the_enum(text: str, value: str) -> str:
    line = _enum_line(text)
    assert line.endswith("."), "%s：枚举行不以句号结尾，反证没法做" % SHAPE
    return text.replace(line, line[:-1] + ", or `%s`." % value)


def _extra_queue_write(source: str, value: str) -> str:
    """往队列源码的**内存**副本多插一处 status 写入。落盘改 `app/**` 不在本单写域内，故只喂字符串。"""
    newline = "\r\n" if "\r\n" in source else "\n"
    lines = source.split(newline)
    anchor = "self.redis.set(self._status_key(request_id), "
    for index, line in enumerate(lines):
        if anchor in line:
            indent = line[: len(line) - len(line.lstrip())]
            injected = indent + anchor + '"%s")' % value
            return newline.join(lines[: index + 1] + [injected] + lines[index + 1:])
    raise AssertionError("%s：队列源码里没有 %r 这枚锚" % (SHAPE, anchor))


def test_counter_evidence_dropping_a_written_value_from_the_contract_turns_the_pin_red():
    """判据⑤(a) 的常驻版本：契约少记一枚代码真写的值，主钉当场红并点名它。"""
    code = _code_side()
    text = _read_text(CONTRACT_DOC).replace("\r\n", "\n")
    picked = sorted(code["queue_values"])[0]
    mutated = parse_contract(_drop_from_the_enum(text, picked))
    assert picked not in mutated["enum"], "摘掉 %r 之后它仍在册，解析没吃到这一处" % picked
    with pytest.raises(AssertionError) as caught:
        check_the_enum_matches_what_the_code_answers(code, mutated)
    assert picked in str(caught.value), str(caught.value)


def test_counter_evidence_an_invented_documented_value_turns_the_pin_red():
    """判据⑤(a) 的反向：契约凭空多记一枚代码从不答的值，同样当场红。"""
    code = _code_side()
    text = _read_text(CONTRACT_DOC).replace("\r\n", "\n")
    mutated = parse_contract(_add_to_the_enum(text, PROBE))
    assert PROBE in mutated["enum"]
    with pytest.raises(AssertionError) as caught:
        check_the_enum_matches_what_the_code_answers(code, mutated)
    assert PROBE in str(caught.value), str(caught.value)


def test_counter_evidence_an_extra_status_write_in_the_source_turns_the_pin_red():
    """判据⑤(b)：多一枚字面量=词表又漂了。只改内存里的 AST 输入，`app/**` 零字节落盘。"""
    digest_before = _digest(QUEUE_SOURCE_PATH)
    original = _read_text(QUEUE_SOURCE_PATH)
    assert PROBE not in _code_side()["answers"]
    mutated_code = _code_side(queue_source=_extra_queue_write(original, PROBE))
    assert PROBE in mutated_code["answers"], "插进去的写入没被 AST 读到，正钉是空转"
    with pytest.raises(AssertionError) as caught:
        check_the_enum_matches_what_the_code_answers(mutated_code, _contract_side())
    assert PROBE in str(caught.value), str(caught.value)
    assert _digest(QUEUE_SOURCE_PATH) == digest_before, "反证写过产品代码，本单铁规已破"


def test_counter_evidence_a_layer_swap_in_the_contract_turns_the_provenance_pin_red():
    """判据⑤/⑦：把路由现造的那枚改口成"队列写的"，出处钉当场红。"""
    code = _code_side()
    route_only = sorted(code["route_only"])
    assert route_only, "路由没有现造的值，分层反证无从谈起"
    value = route_only[0]
    text = _read_text(CONTRACT_DOC)
    line = next(row for row in text.split("\n") if row.rstrip().startswith("* `%s` (" % value))
    swapped = line.replace(ROUTE_LAYER, QUEUE_LAYER)
    assert swapped != line, "%r 那一行没写出 %s，反证没法做" % (value, ROUTE_LAYER)
    mutated = parse_contract(text.replace(line, swapped))
    assert mutated["rows"][value]["layer"] == QUEUE_LAYER
    with pytest.raises(AssertionError) as caught:
        check_the_documented_layers_keep_their_provenance(code, mutated)
    assert value in str(caught.value), str(caught.value)
