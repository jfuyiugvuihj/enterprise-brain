# -*- coding: utf-8 -*-
r"""R379 格五：「import 期出站几次」随环境漂，它一次都不许当判据、更不许进对外读数。

事由（总控 2026-09-27 派工）：worktree 里没有 ``.env`` ⇒ 同一段 import 在本树量到"出站 0"、
在主树量到"出站 1/2"。凡以这种计数当判据的钉子都会随环境漂，一漂就是假红/假绿各半。
预演件头部那张表记的正是这类读数，它只能当**带日期的历史素材**留在注释里。

本件钉四格，全在本写域内：
  ① 出站计数一次都不许进 ``print``（进了就是把它升格成对外读数，run6 要拿去并排看的）；
  ② 那张实测表只准待在模块 docstring 里（离开注释即红）；
  ③ 拦网状态的对外出口只给布尔形状（``guarded`` / ``stubbed`` / ``conftest_gate_loaded``），
     计数一枚都不出口——这一格把"能吃的是什么"钉死，而不是钉住今天吃到的数；
  ④ 本家族（预演件 + r361 + r217 + r379）零枚绝对出站计数断言；写域外那些**只列不判**，
     名单当场扫、当场印，交回单里那份出处就是这一枚钉的输出。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/rehearse_eval_window.py"
TABLE_ROW = re.compile(r"import\s+\S+\s+[\d.]+\s+s\s+出站\s*\d+")
#: 只认"出站 N 次"这种带数的记录；裸"出站 socket 路径"那种主张句不在射程里。
COUNT_TEXT = re.compile(r"出站\s*\d+")
#: 只认"出站/连库次数"这几枚计数器名字。裸 attempt 不算：那是重试次数，与宿主环境无关。
COUNT_WORDS = ("出站", "blocked_count", "BLOCKED_MODEL_PORT_ATTEMPTS", "OFFLINE_DISCOVERY",
               "DISCOVERY_PIN_REINSTALLED", "blocked_socket_attempts", "egress_attempts")

#: 本写域：只有这几棵许被本件判。写域外一律进"只列不判"的名单。
OWNED = ("scripts/rehearse_eval_window.py", "tests/test_r217_strict_unaffordable_form.py")
OWNED_PREFIX = ("tests/test_r361_", "tests/test_r379_")

def _rel(path: Path) -> str:
    return str(path.relative_to(REPO)).replace("\\", "/")


def _owned(rel: str) -> bool:
    return rel in OWNED or any(rel.startswith(prefix) for prefix in OWNED_PREFIX)


def _scanned() -> list:
    files = [REPO / "conftest.py", SCRIPT]
    for sub in ("tests", "scripts"):
        files += sorted((REPO / sub).glob("*.py"))
    return [path for path in files if path.is_file()]


# ==================== ① 对外读数里不许有出站计数 ====================


def test_no_printed_reading_carries_an_egress_count():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8-sig"))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print":
            text = ast.unparse(node)
            if COUNT_TEXT.search(text) or "blocked_socket" in text:
                hits.append(node.lineno)
    assert not hits, f"出站计数被印进对外读数了（行 {hits}）：它随环境漂，不配当读数"


def test_the_fact_cells_carry_no_environment_reading():
    """``--facts`` 每一格都得是"现场源码里的事实"，不许混进宿主环境量到的东西。"""
    text = SCRIPT.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    start = text.index("FACT_READERS = {")
    end = text.index("\n}\n", start)
    block = text[start:end]
    assert "getenv(" not in block or "read_getenv_default" in block, block[:200]
    for word in ("出站", "attempts", "time()"):
        assert word not in block, f"读数格里出现了 {word}：那一格读的是环境不是现场"


# ==================== ② 那张实测表只准待在注释里 ====================


def test_the_measured_import_table_lives_only_in_comments():
    """那张表是**带日期的历史素材**：它只准待在注释里，一旦被写进字符串常量就离印出去不远了。"""
    source = SCRIPT.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    lines = source.splitlines()
    rows = [(index, line.strip()) for index, line in enumerate(lines, 1)
            if TABLE_ROW.search(line)]
    assert rows, "头部那张判据丙实测表整个没了：判据的取证记录不许删（删表 ≠ 改判据）"
    not_comment = [row for row in rows if not row[1].startswith("#")]
    assert not not_comment, f"出站记录离开了注释（会被人当成现场读数）：{not_comment}"
    import ast as _ast
    strings = [node.value for node in _ast.walk(_ast.parse(source))
               if isinstance(node, _ast.Constant) and isinstance(node.value, str)]
    leaked = [item for item in strings if COUNT_TEXT.search(item)]
    assert not leaked, f"出站计数进了字符串常量，下一步就是 stdout：{leaked}"
    assert "随环境漂" in source, "表旁边那句『秒数和出站次数都随环境漂』的交代被擦了"


# ==================== ③ 出口只给布尔形状 ====================


def test_the_egress_guard_readout_is_boolean_shaped():
    """拦没拦 = 三枚布尔。计数不出口 ⇒ 谁拿它当判据都只会吃到形状，不会吃到环境的数。"""
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("r379_egress_shape", str(SCRIPT))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(SCRIPT.read_text(encoding="utf-8-sig"), str(SCRIPT), "exec"), module.__dict__)
    state = module.egress_guard_state()
    assert set(state) == {"guarded", "conftest_gate_loaded", "stubbed"}, state
    assert all(isinstance(value, bool) for value in state.values()), state


# ==================== ④ 绝对计数：写域内零枚，写域外只列不判 ====================


def _count_comparisons(path: Path) -> list:
    """抠出"拿绝对出站次数当判据"的两种形状：与字面量比、以及直接 ``assert not 计数``。"""
    import warnings
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError):
        return []
    found = []
    asserts = [node for node in ast.walk(tree) if isinstance(node, ast.Assert)]
    for host in asserts:
        for node in ast.walk(host):
            if isinstance(node, ast.Compare):
                text = ast.unparse(node)
                if not any(word in text for word in COUNT_WORDS):
                    continue
                literals = [item for item in [node.left] + list(node.comparators)
                            if isinstance(item, ast.Constant) and isinstance(item.value, int)]
                if literals:
                    found.append((host.lineno, text[:120]))
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                text = ast.unparse(node.operand)
                if any(word in text for word in COUNT_WORDS):
                    found.append((host.lineno, "断言计数为零：" + text[:110]))
    return found


def test_the_family_eats_shapes_never_absolute_egress_counts(capsys):
    mine, elsewhere = [], []
    for path in _scanned():
        rel = _rel(path)
        rows = _count_comparisons(path)
        if not rows:
            continue
        (mine if _owned(rel) else elsewhere).append((rel, rows))
    print("\nR379 格五名单（现场扫出，只报不改）：")
    for rel, rows in elsewhere:
        for lineno, text in rows:
            print(f"  {rel}:{lineno}  {text}")
    assert not mine, "本写域里又长出拿绝对出站计数当判据的钉子：" + repr(mine)
    listed = {rel for rel, _rows in elsewhere}
    assert listed, "一枚写域外的计数钉都没扫到：这枚扫描件今天瞎了，去改它的形状"