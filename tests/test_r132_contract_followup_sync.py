"""R132 · 契约散文里那段「追问触发」必须与 chat.py 真源同色（工单判据①–⑥，全离线）。

来历：R127 在 `docs/api/contract-v1.md` 新增的 `Session and Cross-Turn Memory Semantics` 一段，
初稿把追问触发写成"七个 `startswith` 前缀的闭合清单"——那是 R126 **之前**的真相，R126 并树
之后就成了假话。原作者已按总控退回把它改对，但 `Wegener` 扫过并明告：**全仓没有一枚用例读
这段散文** ⇒ 下次谁再改词表，散文还会第二次漂。本钉就是那根焊条。

三条自守的规矩：
  ① 常量名与字面量集合一律从 `app/api/v1/chat.py` 的 AST 里现抠，本文件零手抄词表内容
     （手抄一份等于再埋一颗同形状的雷）；"代表词"取实测集合与散文的交集，不预设该出现哪几个词。
  ② 只读源码与 markdown 文本，**不 import app**：不碰模型、不碰库、不起服务、不建表。
  ③ 判据⑦ 的三把变异不在本文件里跑（变异要往盘上写字节），由临时脚本单进程串行做，
     每步比对 restore sha，日志头尾各插一次"未改一字节"对照组 —— 见交工回执。
"""
import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHAT_SOURCE = REPO / "app" / "api" / "v1" / "chat.py"
CONTRACT_DOC = REPO / "docs" / "api" / "contract-v1.md"
R126_TEST = REPO / "tests" / "test_r126_rewrite_prev_turn.py"

#: 契约里那段散文的标题前缀（标题括号内带日期与工单号，本钉只按前缀定位）
SECTION_HEADING = "## Session and Cross-Turn Memory Semantics"
#: 判据④ 的两半锚词
GUARANTEE_ANCHOR = "Guaranteed across turns"
NON_GUARANTEE_ANCHOR = "Explicitly **not** guaranteed"
#: 不保证侧必须点名的四条 worker 腿 —— 契约可见的枚举值，不是追问词表
WORKER_LEGS = ("doc", "data", "chart", "export")
#: 真源里那两枚触发函数（判据① 要求抠名，判据④⑤ 不看它们）
TRIGGER_FUNCTIONS = ("_starts_with_deictic", "_is_followup")
#: 汇总触发词的聚合常量：它是"别族的和"，本身不是族
AGGREGATE_CONSTANT = "_FOLLOWUP_MARKERS"
#: 消费触发判据的那条腿：接线必须还挂在它身上
CONSUMER_FUNCTION = "_rewrite_followup"
#: 判据⑥：R126 用例与散文必须对得上的三个数（12 枚多轮 / 93 枚其余 / 105 枚总题）
MEASURED_SPLIT = (12, 93, 105)
#: 判据⑤：旧口径句式，一次都不许出现
DEAD_ENGLISH_PHRASES = ("starts with one of",)
DEAD_CHINESE_PATTERN = re.compile(r"只认[^。\n]{0,24}前缀")
#: 判据⑤：这个短语只许在**否定**结构里出现（现稿正是 "**not** a closed prefix list"）
CLOSED_LIST_PHRASE = "closed prefix list"
NEGATION_PATTERN = re.compile(r"(\bnot\b|\bnever\b|\bno\b|不是|并非|绝不|不再)", re.IGNORECASE)
SENTENCE_ENDS = ".?!。？！"

CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
BACKTICK_PATTERN = re.compile(r"`([^`]+)`")
PAREN_GROUP_PATTERN = re.compile(r"\(([^()]*)\)")
CITED_FILE_PATTERN = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|md|jsonl))`")
INTEGER_PATTERN = re.compile(r"\b(\d{1,4})\b")


# ==================== 真源侧：AST 抠词表 ====================

def _text(path: Path) -> str:
    assert path.exists(), f"{path.relative_to(REPO)} 不在了"
    return path.read_text(encoding="utf-8")


def _module_tree() -> ast.Module:
    return ast.parse(_text(CHAT_SOURCE), filename=str(CHAT_SOURCE))


def _module_assignments(tree: ast.Module) -> dict:
    found = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            found[node.targets[0].id] = node
    return found


def _module_functions(tree: ast.Module) -> dict:
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


def _called_names(node: ast.AST) -> set:
    calls = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
            calls.add(sub.func.id)
    return calls


def _literal_tuple(value: ast.expr):
    """字符串字面量组成的元组 → 字面量集合；别的形状（含 `(A + B)`）返回 None。"""
    if not isinstance(value, ast.Tuple):
        return None
    literals = []
    for element in value.elts:
        if not (isinstance(element, ast.Constant) and isinstance(element.value, str)):
            return None
        literals.append(element.value)
    return tuple(literals)


def _family_names(tree: ast.Module, assignments: dict, functions: dict) -> list:
    """哪些常量真在供给触发词？只认两条接线，不认名字长什么样。

    (a) `AGGREGATE_CONSTANT` 的值里被连起来的那些常量名；
    (b) 两枚触发函数里被 `for` / 推导式**当词表遍历**的那些常量名。
    豁免判用的常量（`prefix in _DEICTIC_PREFIXES` 那类成员测试）不算供词，那是例外表。
    """
    names = []
    aggregate = assignments.get(AGGREGATE_CONSTANT)
    if aggregate is not None:
        for node in ast.walk(aggregate.value):
            if isinstance(node, ast.Name) and node.id in assignments and node.id not in names:
                names.append(node.id)
    for function_name in TRIGGER_FUNCTIONS:
        function = functions.get(function_name)
        if function is None:
            continue
        for node in ast.walk(function):
            if not isinstance(node, (ast.For, ast.comprehension)):
                continue
            target = getattr(node, "iter", None)
            if not isinstance(target, ast.Name):
                continue
            if target.id == AGGREGATE_CONSTANT or target.id in names:
                continue
            if target.id not in assignments:
                continue
            if _literal_tuple(assignments[target.id].value) is None:
                continue
            names.append(target.id)
    return sorted(names, key=lambda name: assignments[name].lineno)


def _families() -> dict:
    """`{常量名: 字面量元组}`，按源码行序 —— 顺序与散文里那五组的落笔顺序一致。"""
    tree = _module_tree()
    assignments = _module_assignments(tree)
    functions = _module_functions(tree)
    names = _family_names(tree, assignments, functions)
    assert names, (
        f"判据① 抠空了：从 {CHAT_SOURCE.name} 的 AST 里认不出一族触发词表。"
        f"要么是 `{AGGREGATE_CONSTANT}` 不再由常量相加组成，要么是 {TRIGGER_FUNCTIONS} 里"
        "不再有 `for ... in 某常量` 的遍历 —— 改形状可以，但请连契约那段与本钉一起改，"
        "不许只改一边。"
    )
    for name in names:
        value = assignments[name].value
        assert isinstance(value, ast.Tuple), f"{name} 不再是元组形状，本抠法认不出它的字面量"
    return {name: (_literal_tuple(assignments[name].value) or ()) for name in names}


def _asserted_integers(path: Path) -> set:
    """一枚测试文件里所有 `assert` 子树出现过的整数字面量（判据⑥：不执行，只按 AST 找）。"""
    numbers = set()
    for node in ast.walk(ast.parse(_text(path), filename=str(path))):
        if not isinstance(node, ast.Assert):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, int) and not isinstance(
                sub.value, bool
            ):
                numbers.add(sub.value)
    return numbers


# ==================== 散文侧：那段契约 ====================

def _section() -> str:
    text = _text(CONTRACT_DOC)
    start = text.find(SECTION_HEADING)
    assert start != -1, f"契约里找不到 {SECTION_HEADING!r} 这一段（改名或删段都得先动本钉）"
    tail = text[start + len(SECTION_HEADING):]
    end = tail.find("\n## ")
    section = text[start : start + len(SECTION_HEADING) + (len(tail) if end == -1 else end)]
    assert len(section) > 400, "这段散文短得不对劲 —— 后面每一枚钉都会变成空响"
    return section


def _bullets(block: str) -> list:
    bullets = []
    current = None
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            if current is not None:
                bullets.append(current)
            current = stripped[2:]
        elif stripped:
            if current is not None:
                current = f"{current} {stripped}"
        elif current is not None:
            bullets.append(current)
            current = None
    if current:
        bullets.append(current)
    return bullets


def _bullets_under(anchor: str) -> list:
    section = _section()
    start = section.find(anchor)
    assert start != -1, f"契约那段丢了锚句 {anchor!r} —— 两半结构少了一半"
    block = section[start + len(anchor):]
    for other in (GUARANTEE_ANCHOR, NON_GUARANTEE_ANCHOR):
        if other == anchor:
            continue
        position = block.find(other)
        if position != -1:
            block = block[:position]
    return _bullets(block)


def _prose_word_groups(section: str) -> list:
    """括号内、反引号包着、用 ` / ` 分隔的中文词 —— 那就是五族在散文里的落笔处。

    逗号分隔的括号组（豁免词表 `这份报告` / `这个月` 那一类）与纯 ASCII 组（`sessions` /
    `session_messages`、四条 worker 腿、五枚常量名）都不算族，天然被这两条筛掉。
    """
    groups = []
    for match in PAREN_GROUP_PATTERN.finditer(section):
        inner = match.group(1)
        if " / " not in inner:
            continue
        words = [token for token in BACKTICK_PATTERN.findall(inner) if CJK_PATTERN.search(token)]
        if words:
            groups.append(words)
    return groups


# ==================== 判据① 真源用 AST ====================

def test_the_followup_vocabulary_is_readable_straight_from_the_source():
    """判据①：五枚常量与它们的字面量集合必须能按 AST 现抠出来（本文件零手抄）。"""
    families = _families()

    assert len(families) >= 2, f"只抠出 {len(families)} 族，判据① 说的是五族"
    for name, literals in families.items():
        assert name.startswith("_") and name.upper() == name, f"{name} 不是模块级常量名"
        assert isinstance(literals, tuple), f"{name} 的字面量集合形状不对"
        assert all(isinstance(word, str) and word for word in literals), f"{name} 里混进了空值"
    total = {word for literals in families.values() for word in literals}
    assert len(total) >= 20, f"五族加起来只有 {len(total)} 枚词，不像还在供货"


def test_the_trigger_functions_exist_and_are_wired_end_to_end():
    """判据① 的外加半边：两枚函数名在，且接线没断（判据不是挂在死代码上的）。"""
    tree = _module_tree()
    functions = _module_functions(tree)
    for name in TRIGGER_FUNCTIONS + (CONSUMER_FUNCTION,):
        assert name in functions, f"{CHAT_SOURCE.name} 里不再有模块级函数 {name}"

    assert "_starts_with_deictic" in _called_names(functions["_is_followup"]), (
        "`_is_followup` 不再调用 `_starts_with_deictic` —— 句首指代那一族成了孤儿"
    )
    assert "_is_followup" in _called_names(functions[CONSUMER_FUNCTION]), (
        f"`{CONSUMER_FUNCTION}` 不再调用 `_is_followup` —— 词表与真路由脱钩了"
    )


# ==================== 判据② 散文点名每一枚常量 ====================

def test_the_contract_names_every_vocabulary_constant_by_its_real_name():
    """判据②：AST 抠出的每一枚常量名都要逐字出现在那段里 —— 改一枚红一枚。"""
    section = _section()
    families = _families()

    missing = [name for name in families if name not in section]
    assert missing == [], (
        "契约散文不再点名这些词表常量：" + "、".join(missing) + "（改名请两边一起改）"
    )


# ==================== 判据③ 每族至少一枚代表词在散文里 ====================

def test_every_family_keeps_a_representative_word_in_the_prose():
    """判据③：每一族至少有一枚实测字面量出现在散文里；整族清空或全换成散文没提的词 ⇒ 红。"""
    section = _section()
    families = _families()
    silenced = []
    emptied = []

    for name, literals in families.items():
        if not literals:
            emptied.append(name)
        elif not any(word in section for word in literals):
            silenced.append(name)

    assert emptied == [], f"这些族被清空了，散文还在按族描述它：" + "、".join(emptied)
    assert silenced == [], (
        "这些族在散文里一枚代表词都不剩：" + "、".join(silenced) + " —— 散文已经不知道词表长什么样了"
    )


def test_the_prose_cites_no_word_the_code_no_longer_has():
    """③ 的反向半边：散文列出的每一枚代表词必须真在某一族里，族数也要对得上。

    放行一种形态：`他们` / `她们` 是 `他` / `她` 的复数写法（代码按"单字前缀 + 必须跟`们`"
    实现，散文按读起来的样子写）——这是形态规则，不是手抄词表。
    """
    section = _section()
    families = _families()
    vocabulary = {word for literals in families.values() for word in literals}
    groups = _prose_word_groups(section)

    assert len(groups) == len(families), (
        f"散文里有 {len(groups)} 组词表，真源里是 {len(families)} 族：加族/删族必须两边同批"
    )
    ghosts = [
        word
        for group in groups
        for word in group
        if word not in vocabulary and not (word.endswith("们") and word[:-1] in vocabulary)
    ]
    assert ghosts == [], "散文引用了代码里已经没有的词：" + "、".join(ghosts)


# ==================== 判据④ 保证侧 / 不保证侧两半都在 ====================

def test_the_prose_holds_both_the_guarantee_and_the_non_guarantee_lists():
    """判据④：两半都在；不保证侧点名四条 worker 腿，并留下"改写≠已解析指代"那层意思。"""
    guaranteed = _bullets_under(GUARANTEE_ANCHOR)
    not_guaranteed = _bullets_under(NON_GUARANTEE_ANCHOR)

    assert guaranteed, "保证侧一条列表项都没有"
    assert not_guaranteed, "不保证侧一条列表项都没有"

    legs_text = " ".join(not_guaranteed)
    absent = [leg for leg in WORKER_LEGS if f"`{leg}`" not in legs_text]
    assert absent == [], "不保证侧不再点名这些 worker 腿：" + "、".join(absent)

    caveat = [
        bullet
        for bullet in not_guaranteed
        if "rewrit" in bullet.lower() and NEGATION_PATTERN.search(bullet)
    ]
    assert caveat, "不保证侧丢了「改写不等于把指代解析掉了」那条 —— 少这一句就是给调用方留错觉"


# ==================== 判据⑤ 旧口径不许复活 ====================

def _clause_before(text: str, index: int) -> str:
    window = text[max(0, index - 120) : index]
    cut = 0
    for position, char in enumerate(window):
        if char in SENTENCE_ENDS:
            cut = position + 1
    return window[cut:]


def test_the_closed_prefix_wording_never_comes_back():
    """判据⑤（否定式钉）：旧口径三种形状都不许出现；提它只许在否定结构里提。"""
    text = _text(CONTRACT_DOC)

    revived = [phrase for phrase in DEAD_ENGLISH_PHRASES if phrase in text]
    assert revived == [], "旧句式回来了：" + "、".join(revived)

    chinese = DEAD_CHINESE_PATTERN.search(text)
    assert chinese is None, f"「只认…前缀」这类闭合说法回来了：{chinese.group(0)}"

    unrefuted = [
        _clause_before(text, match.start()).strip()
        for match in re.finditer(re.escape(CLOSED_LIST_PHRASE), text)
        if not NEGATION_PATTERN.search(_clause_before(text, match.start()))
    ]
    assert unrefuted == [], (
        f"`{CLOSED_LIST_PHRASE}` 在没有否定词的句子结构里出现了 {len(unrefuted)} 次，"
        "等于把追问触发又写回闭合清单（现稿的合法写法是 **not** a closed prefix list）："
        + " // ".join(unrefuted)
    )


# ==================== 判据⑥ 引用的凭据必须真实 ====================

def test_every_file_the_prose_cites_as_evidence_actually_exists():
    """判据⑥ 前半：散文里当出处用的文件名必须真实存在，且至少一枚指向真源、一枚指向用例。"""
    cited = CITED_FILE_PATTERN.findall(_section())

    assert cited, "这段散文不再引用任何源文件当凭据了 —— 判据⑥ 得重新找凭据"
    missing = [relative for relative in cited if not (REPO / relative).exists()]
    assert missing == [], "散文引用的文件不存在：" + "、".join(missing)
    assert any(relative.endswith("chat.py") for relative in cited), "散文不再指向词表真源 chat.py"
    assert any(relative.startswith("tests/") for relative in cited), "散文不再指向算过命中数的用例"


def test_the_measured_numbers_in_the_prose_match_the_r126_case():
    """判据⑥ 后半：散文里的 12/93/105 必须与 R126 用例真断言的数对得上（按 AST 找，不执行它）。"""
    assert R126_TEST.exists(), f"散文引用的 {R126_TEST.name} 不在了"
    asserted = _asserted_integers(R126_TEST)
    gone = [number for number in MEASURED_SPLIT if number not in asserted]
    assert gone == [], (
        f"{R126_TEST.name} 不再以整数断言这些数：" + "、".join(map(str, gone)) + " —— 用例侧先漂了"
    )

    prose_numbers = {int(token) for token in INTEGER_PATTERN.findall(_section())}
    drift = [number for number in MEASURED_SPLIT if number not in prose_numbers]
    assert drift == [], (
        "用例断言了这些数而散文不再写：" + "、".join(map(str, drift)) + " —— 散文侧漂了，指名改散文"
    )
