# -*- coding: utf-8 -*-
"""R361 判据丙：走 import 还是走 AST 是量出来的，而且这个理由今天还得站得住。

预演件头部那张表（六枚模块 × 秒数 × 出站次数）记的是当轮在 ``.venv`` 里的实测。秒数和出站
次数都随环境漂——把本件拷进一棵没有 ``.env`` 的 worktree 再 import，出站计数就变 0——所以
它们不能当常驻判据。真正不随环境漂、由这枚钉常驻复核的是：

    现场那两棵重件在**模块级**就动手造对象（造 supervisor agent、造检索器、造模型句柄），
    所以 import 它们等于让一枚只读审计件替全仓拉起模型与向量库；其余几棵模块级零动作。

🔴 本件全程只做 AST，绝不在测试里 import 那两棵重件。上一轮实测时 ``import app.api.v1.chat``
的模块级 ``DocumentRetriever(...)`` 把 ``chroma_db/chroma.sqlite3`` 写脏了一次，被 R134 闸门
当场点名——那正是"不许碰数据"该抓的形状，所以量理由改用静态读法，不改用跑一下试试。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/rehearse_eval_window.py"
TABLE_ROW = re.compile(r"import\s+(\S+)\s+[\d.]+\s+s\s+出站\s*(\d+)")

#: 模块级出现这些构造 = import 期就伸手（模型 / 向量库 / 数据库 / 落盘）。
REACH_OUT = ("_make_model", "create_react_agent", "_make_checkpointer", "DocumentRetriever",
             "ModelHandler", "makedirs", "PersistentClient", "ConnectionPool", "ChatOpenAI")
#: 模块级这些动作无害（读 .env、造路由对象），单列以免把"干净"误判成"伸手"。
HARMLESS = {"APIRouter", "getLogger", "compile", "Path", "ThreadPoolExecutor", "load_dotenv", "Lock"}

NEVER_IMPORT = ("app.agents.orchestrator", "app.api.v1.chat")
MAY_IMPORT = ("app.common.cache", "app.agents.planner", "app.quality.eval", "app.agents.nodes")
MAY_IMPORT_RELS = ("app/common/cache.py", "app/agents/planner.py", "app/quality/eval.py", "app/agents/nodes.py")


def reaches_out_at_import_time(rel: str) -> dict:
    """只看模块级语句（不进任何函数体/类体），抠出"import 那一刻就会执行"的构造调用。"""
    tree = ast.parse((REPO / rel).read_text(encoding="utf-8-sig"))
    found = {}
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else None)
            if name and name in REACH_OUT and name not in HARMLESS:
                found.setdefault(name, node.lineno)
    return found


# ==================== ① 那张表要还完整 ====================


def test_the_header_table_still_covers_every_decided_module():
    """表里少一枚模块 = 那枚的 import/AST 选择没了实测记录，判据丙 不成立。"""
    text = SCRIPT.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    listed = {name for name, _seconds in TABLE_ROW.findall(text)}
    missing = sorted((set(NEVER_IMPORT) | set(MAY_IMPORT)) - listed)
    assert not missing, f"预演件头部表少了这些模块的实测行：{missing}"


# ==================== ② 不 import 的理由今天仍然成立 ====================


@pytest.mark.parametrize("rel", ["app/agents/orchestrator.py", "app/api/v1/chat.py"])
def test_the_heavy_modules_still_build_things_at_import_time(rel):
    """这两棵一旦不在模块级造对象，"永不 import"就得重新论证——不许让理由烂成信仰。"""
    found = reaches_out_at_import_time(rel)
    assert found, (f"{rel} 模块级已经没有 " + repr(REACH_OUT) + " 里的任何构造："
                   "当轮实测的『import 会拉起模型/向量库』这条理由过期，去重新决定 import 还是 AST")


def test_the_modules_we_do_import_have_no_import_time_construction():
    """反方向也要钉：预演件真 import 的那几棵必须没有模块级伸手动作。

    只钉"重件确实重"是半套——轻件哪天在模块级加一枚 PersistentClient，本件就悄悄替全仓开了
    向量库，而那张表还在说它"干净"。
    """
    offenders = {rel: reaches_out_at_import_time(rel) for rel in MAY_IMPORT_RELS}
    offenders = {rel: hits for rel, hits in offenders.items() if hits}
    assert not offenders, "模块级会伸手、却正被预演件 import 的件：" + repr(offenders)


# ==================== ③ 判定要落进代码形状 ====================


def test_the_script_imports_neither_heavy_module():
    """AST 扫本件：那两棵一枚 import 都不许有，动态 import_module 也算。"""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8-sig"))
    pulled = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in NEVER_IMPORT:
            pulled.add(node.module)
        elif isinstance(node, ast.Import):
            pulled |= {alias.name for alias in node.names if alias.name in NEVER_IMPORT}
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in {"import_module", "__import__"}:
                pulled |= {arg.value for arg in node.args
                           if isinstance(arg, ast.Constant) and arg.value in NEVER_IMPORT}
    assert not pulled, "预演件把重件 import 进了进程：" + repr(sorted(pulled))


def test_the_script_states_the_stay_out_reason_in_its_header():
    """理由要写在读得到的地方：文件头点名这两棵不 import，而不是只剩一张裸表。"""
    head = SCRIPT.read_text(encoding="utf-8-sig").replace("\r\n", "\n")[:4500]
    assert "orchestrator" in head and "AST" in head, "文件头不再交代为什么不 import 重件"
    for rel in NEVER_IMPORT:
        assert rel.split(".")[-2] + "/" + rel.split(".")[-1] in head or rel in head, rel
