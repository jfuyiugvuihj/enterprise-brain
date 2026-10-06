"""lint_hand_copied_coordinates.py -- 机械层不许把行号当数据（CHASE-2026-10-06 段 B）

病形：一条断言里写着「某某文件 + 冒号 + 那枚数字」，代码一挪位这枚钉就红，红完就得开一枚纯重锚
工单（在册先例：重锚 46 枚那一单、换 15 枚那一单）。这一族一行产品功能都不产生。

口径（只此一条，别处不许扩）：
- 扫 tests/**.py 与 scripts/**.py 的 **AST 字符串常量**；文档字符串与注释不算（那是人话，
  人话里的出处引用不驱动判等）。
- 命中形状 = 路径样 token + 点 + 受管扩展名 + 冒号 + 数字。
- 棘轮：现取枚数不得高于 HAND_COPY_BUDGET；降了由牙逼着重取基线并逐枚点名（拿旧预算装新盘面＝假账）。

本件自身也在扫描范围内（自咬）：所以正文里一枚示例行号都不写，正则从常量拼出来。
"""
import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE_DIRS = ("tests", "scripts")
MANAGED_EXTS = ("py", "vue", "sql", "ts", "js", "jsonl", "md", "txt")
#: 冒号右边紧跟数字才算抄来的坐标；冒号右边是反斜杠（正则自身）不算。
COLON = ":"
LITERAL_CITE = re.compile(
    r"[A-Za-z0-9_./\\-]+\.(?:" + "|".join(MANAGED_EXTS) + r")" + COLON + r"\d")

#: 现取基线：本文件第一次落地时的枚数与文件数。改这个数必须在提交词里逐枚点名是谁降的。
HAND_COPY_BUDGET = 95
RC_CLEAN = 0
RC_OVER_BUDGET = 4
RC_NO_SCOPE = 5


def _docstring_constants(tree) -> set:
    """模块／类／函数的 docstring 常量 id 集合——那些是叙事，不是判据数据。"""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    out.add(id(value.value))
    return out


def hits_in_file(path: Path) -> list:
    """一枚文件里的越界字面坐标：(行号, 片段)。解析不动的文件直接点名，不静默跳过。"""
    source = path.read_text(encoding="utf-8", errors="replace")
    if COLON not in source:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise SyntaxError("%s 解析不动（%s），本尺拒绝猜" % (path, exc)) from exc
    doc_ids = _docstring_constants(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node.value) in doc_ids:
                continue
            match = LITERAL_CITE.search(node.value)
            if match:
                found.append((node.lineno, match.group(0)))
    return found


def scan(root: Path = ROOT) -> tuple:
    """扫受管范围，交回 (逐文件命中, 总枚数)。"""
    per_file = {}
    for name in SCOPE_DIRS:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            hits = hits_in_file(path)
            if hits:
                per_file[str(path.relative_to(root))] = hits
    total = sum(len(v) for v in per_file.values())
    return per_file, total


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="机械层手抄坐标棘轮（只读，不改任何文件）")
    parser.add_argument("--check", action="store_true",
                        help="现取枚数 <= 预算则 rc=0；超预算 rc=%d" % RC_OVER_BUDGET)
    parser.add_argument("--report", action="store_true", help="逐文件点名（默认只报总数）")
    parser.add_argument("--root", default="",
                        help="扫哪一棵树；缺省为本件所在仓库。测试要用临时树自证，cwd 不决定量什么")
    parser.add_argument("--budget", type=int, default=HAND_COPY_BUDGET,
                        help="棘轮线；缺省取在册常量。临时树要自证超线那一形时才由调用方给")
    parser.add_argument("--json", dest="out", default="", help="把全貌写成 JSON 文件")
    args = parser.parse_args(argv)

    base = Path(args.root).resolve() if args.root else ROOT
    per_file, total = scan(base)
    if not per_file and not any((base / name).is_dir() for name in SCOPE_DIRS):
        print("ABORT: 受管范围一枚目录都找不到，这一格今天没在量东西", file=sys.stderr)
        return RC_NO_SCOPE
    over = total > args.budget
    verdict = "OVER" if over else "WITHIN"
    print("手抄坐标现取=%d 预算=%d 越界文件=%d 判定=%s 在册基线=%d"
          % (total, args.budget, len(per_file), verdict, HAND_COPY_BUDGET))
    if args.report or over:
        for name in sorted(per_file, key=lambda k: (-len(per_file[k]), k)):
            print("  %3d  %s" % (len(per_file[name]), name))
            if args.report:
                for line, snippet in per_file[name][:3]:
                    print("         %s（第 %d 行）" % (snippet, line))
    if args.out:
        Path(args.out).write_text(json.dumps({"budget": args.budget, "in_book_baseline": HAND_COPY_BUDGET,
                                              "total": total,
                                              "per_file": per_file}, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
        print("全貌 -> " + args.out)
    if args.check:
        return RC_OVER_BUDGET if over else RC_CLEAN
    return RC_CLEAN


if __name__ == "__main__":
    sys.exit(main())
