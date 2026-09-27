# -*- coding: utf-8 -*-
r"""R409 · 文档 §2.3 那张批准材料表从此只有"渲染产物"这一种身份，而且带着牙。

病灶（这一单买的是"业主能不能批"）：``docs/perf/r387-label-lineage-2026-09-27.md`` 的 §2.3 是业主批
A3（按文件名规则回填部门）的输入，而它到今天是一张**纸账** —— 表里那批数是 R387 抄下来的一次数。
R400 只把「梯级」那一本账改成可复跑（``--unlock-ladder``），§2.3 没有牙；更要命的是它自己承认现读已经
漂走（同件 §9.5："§2.3 写的是研发 721，本班同一份量具现跑 = 713"，并按"读数不追溯改写"把原文留着）。
批准材料上的数与它自己的量具读数不是同一个数 ⇒ 业主批下去的是一个没人能复跑的东西。

本件钉的五格（姿势照 R346 / R351 / R377 / R396 / R398 / R400 那一族抄，不另起口径）：

① 文档里那一块与 ``--emit-plan-table`` 的 stdout **逐字节相等**；stdout 除了那一块一个字节都不出；
   同一份数据源跑两遍、换插入顺序，输出必须一字不差（排序稳定性）。
② §2.3 块外的散文一枚手抄的计数都不许有：不是「§号 / 字母编号 / 列表序号」形状的数字当场点名。
③ 反证刀（全部常驻成用例，变异只落 tmp 影子）：(a) 把某一格换回手抄常量 ⇒ 逐字节比对红；
   (a2) 把一枚数抄进散文 ⇒ 散文闸红；(b) 影子数据里挪走一批可回填 chunk ⇒ 数跟着动、那一块跟着动；
   (c) 数据源读不出 / 形状不对 / 文档里那一对标记不唯一 ⇒ 当场喊「取不到」，且 stdout 一个字节都不出
   （静默跳过 = 假绿：R396/R398 刚为这一格挨过退单）。
④ 与 §9.5 那本梯级账同源不打架：块里"可规则回填 / 合计 / 规则可达部门"三枚事实必须等于
   ``unlock_ladder()`` 里 S3、S3b 挪开的格数；把 §2.3 接到第二套口径上，两处读数自己就会打起来。
⑤ 渲染那几枚函数里不许长出手抄的数：数字常量 ≥ 十、或字符串常量里出现两枚连号数字，都算一处手抄。

零写入：本件对被跟踪文件只有读口，变异一律落 ``tmp_path`` 影子副本；每把刀进门取 sha、出门比 sha。
零连库：跑量具一律 ``--no-db``，并钉一条"带着 DATABASE_URL 也不许为了一张表去连库"。
数据源是那枚只读导出的快照（``docs/perf/raw/``），🔴 不是合成样本 —— 沙盒那批合成标签只证行为、不证客户隔离。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT_REL = "scripts/r387_backfill_estimate.py"
LINEAGE_REL = "scripts/r387_label_lineage.py"
DOC_REL = "docs/perf/r387-label-lineage-2026-09-27.md"
NAMES_REL = "docs/perf/raw/r387-backfill-names-2026-09-27.tsv"

#: 取证通道，不是豁免：三枚被检件都能被指到 tmp 影子副本，反证刀因此一格都不必碰盘上那三枚。
#: 口径照 tests/test_r387_label_ruler_teeth.py 的 R387_LABEL_TOOL —— 没有"今天可以不算"这一格。
SCRIPT = Path(os.getenv("R409_SCRIPT") or REPO / SCRIPT_REL)
DOC = Path(os.getenv("R409_DOC") or REPO / DOC_REL)
NAMES = Path(os.getenv("R409_NAMES") or REPO / NAMES_REL)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, "无法加载量具：" + str(path)
    module = importlib.util.module_from_spec(spec)
    #: frozen dataclass 要回查 sys.modules[cls.__module__]，手工 importlib 不注册就炸。
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_shadow(path: Path, name: str, root: Path):
    """加载影子量具，并把它 import 期插进 sys.path 的那一口收回来（R400 同一姿势）。"""
    before = list(sys.path)
    loaded = {}
    try:
        module = _load(path, name)
        for key, value in list(sys.modules.items()):
            filename = getattr(value, "__file__", "") or ""
            if key.split(".")[0] == "app" and str(root) in Path(filename).as_posix():
                loaded[key] = value
        return module
    finally:
        sys.path[:] = before
        for key in loaded:
            sys.modules.pop(key, None)


#: 先登记血缘件，量具那句 ``from r387_label_lineage import ...`` 才会命中同一枚 classify_arm；
#: 影子量具也共享这一本判序，不会在 tmp 里长出第二份判序。
TOOL = _load(REPO / LINEAGE_REL, "r387_label_lineage")
BF = _load(SCRIPT, "r409_backfill_estimate")


def sha16(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def doc_lines(path=None) -> list:
    return Path(path or DOC).read_bytes().decode("utf-8").split("\r\n")


def section_span(lines: list) -> tuple:
    """§2.3 那一节的边界：起于该节标题，止于下一个二级标题。"""
    head = [i for i, line in enumerate(lines) if line.startswith("### 2.3 ")]
    assert len(head) == 1, "文档里 §2.3 要么不在、要么出现了两节：" + str(head)
    following = [i for i in range(head[0] + 1, len(lines)) if lines[i].startswith("## ")]
    assert following, "§2.3 之后读不到下一节：没有尽头就量不出边界"
    return head[0], following[0]


def marker_bounds(lines: list) -> tuple:
    begins = [i for i, line in enumerate(lines) if line.strip() == BF.BLOCK_BEGIN]
    ends = [i for i, line in enumerate(lines) if line.strip() == BF.BLOCK_END]
    return begins, ends


def doc_block(path=None) -> list:
    """文档里那一整块（含两行标记本身）：唯一允许印数的地方就在这里面。"""
    lines = doc_lines(path)
    begins, ends = marker_bounds(lines)
    assert len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0], (
        "文档里那一对渲染标记不唯一（BEGIN=" + str(begins) + " END=" + str(ends)
        + "）：取不到就是红，不许拿旧表冒充现读")
    start, stop = section_span(lines)
    assert start < begins[0] and ends[0] < stop, "渲染块不在 §2.3 里：它被挪到别的口径旁边去了"
    return lines[begins[0]:ends[0] + 1]


def doc_prose(path=None) -> list:
    """§2.3 里**块外**的散文：那一格里一枚手抄的计数都不该出现。"""
    lines = doc_lines(path)
    start, stop = section_span(lines)
    begins, ends = marker_bounds(lines)
    assert len(begins) == 1 and len(ends) == 1, "先把那一对标记修好，再谈散文里有没有手抄的数"
    inside = set(range(begins[0], ends[0] + 1))
    return [lines[i] for i in range(start + 1, stop) if i not in inside]


def render_from(names_path) -> tuple:
    plan = BF.plan_from_names(BF.read_names_file(str(names_path)))
    return BF.plan_table_block(plan, str(names_path)), plan


def run_tool(*args: str):
    """真子进程跑量具：只有真 stdout 才谈得上"逐字节"，pytest 的捕获层不算。"""
    return subprocess.run([sys.executable, str(SCRIPT)] + list(args),
                          capture_output=True, cwd=str(REPO))


def emit_stdout() -> bytes:
    proc = run_tool("--no-db", "--names-file", str(NAMES), "--emit-plan-table")
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return proc.stdout


# ------------------------------------------------------------------ ① 逐字节同源

def test_the_data_source_is_in_the_tree_and_reads_as_data() -> None:
    """判据①⑥：喂数的那本数据必须在树里且读得出来 —— 落在 %TEMP% 上就等于只有一台机器能复跑。"""
    assert NAMES.is_file(), "数据源取不到（不许拿旧表冒充现读）：" + str(NAMES)
    try:
        NAMES.resolve().relative_to(REPO)
    except ValueError:
        raise AssertionError("数据源不在仓库里，批准材料就成了单机账：" + str(NAMES))
    raw = NAMES.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf", "数据源带 BOM：第一枚文件名会被读成另一枚名字"
    assert [c for i, c in enumerate(raw) if c == 0x0A and raw[i - 1] != 0x0D] == [], "数据源行尾不纯"
    rows = BF.read_names_file(str(NAMES))
    assert len(rows) >= 10, "数据源只有 " + str(len(rows)) + " 枚文档：这一格今天没在量东西"
    assert all(int(count) > 0 for count in rows.values()), "数据源里有零枚的文档：行数与枚数会打架"


def test_the_doc_block_equals_the_rendering_line_by_line() -> None:
    """🔴 文档里那一块 == 现读渲染：逐行比，红的时候直接端出差在第几行、两边各是什么。"""
    assert block_diff() == [], "文档那一块已经不是渲染产物：\n" + "\n".join(block_diff())


def test_the_cli_stdout_is_exactly_that_block_byte_for_byte() -> None:
    """🔴 stdout 除了那一块没有别的字节：交回的就是文档那一节的字节（含行尾、含末行换行）。"""
    expected = ("\r\n".join(doc_block()) + "\r\n").encode("utf-8")
    got = emit_stdout()
    assert got == expected, "stdout 与文档那一块不是同一批字节：%d vs %d 字节" % (len(got), len(expected))
    assert got.count(b"\n") == got.count(b"\r\n"), "交出去的字节里混着裸 LF"


def test_two_runs_and_three_input_orders_render_the_same_bytes() -> None:
    """判据①：同输入两次跑必须同输出；换键序（倒序 / 按枚数降序）也必须同输出 —— 序由渲染器定。"""
    assert emit_stdout() == emit_stdout(), "同一枚数据源两次渲染不等：排序不稳，批准材料读第二遍就变"
    rows = BF.read_names_file(str(NAMES))
    plain = BF.plan_table_block(BF.plan_from_names(dict(rows)), str(NAMES))
    reversed_order = BF.plan_table_block(
        BF.plan_from_names(dict(reversed(list(rows.items())))), str(NAMES))
    by_size = BF.plan_table_block(
        BF.plan_from_names(dict(sorted(rows.items(), key=lambda item: -int(item[1])))), str(NAMES))
    assert [reversed_order, by_size] == [plain, plain], "换插入顺序就换输出：那里有一处还在依赖字典序"
    departments = BF.plan_table_departments(BF.plan_from_names(rows))
    assert departments == sorted(departments, key=lambda row: (-row[2], -row[1], row[0])), (
        "部门那一段不是按「chunk 降序、同数按部门名升序」排的：并列一多，两次跑就会换序")


def test_the_block_names_its_path_row_count_and_rule() -> None:
    """判据①：路径 + 条数 + 判定依据三件都得在块里，读表的人才知道这数从哪来。"""
    text = "\r\n".join(doc_block())
    assert Path(NAMES_REL).as_posix() in text, "块里没印数据源路径：这数成了无源之水"
    assert "只读导出" in text and "不发一条 SQL" in text, "块里没声明这一格是只读导出的现读"
    assert "合计（= 数据源行数 / 枚数）" in text, "块里那枚合计没说明它就是数据源的行数与枚数"
    assert BF.HINT_RULE_LABEL in text, "块里没印判定依据的出处：读表的人无从复核口径"
# ------------------------------------------------------------------ ② 块外散文不许有手抄的数

SECTION_REF = re.compile(r"§\d+(?:\.\d+)*")
LIST_MARKER = re.compile(r"^\s*\d+\.\s")
STRAY_DIGIT = re.compile(r"(?<![A-Za-z0-9_])\d")


def stray_counts(lines: list) -> list:
    """块外散文里"手抄计数"的形状：剥掉 §号与列表序号后，任何不与字母粘连的数字都算一枚。

    放过 `A3` / `S3b` / `R409` / `app/api/v1/chat.py` 这一族（那是编号，不是读数），
    抓住「研发 721」与「实为 713」那一族 —— 后者正是这一节上一班留下的病形状。
    """
    found = []
    for line in lines:
        stripped = LIST_MARKER.sub("    ", SECTION_REF.sub("", line), count=1)
        for match in STRAY_DIGIT.finditer(stripped):
            found.append(stripped[max(0, match.start() - 8):match.start() + 8].strip())
    return found


def has_count(text: str, digits: str) -> bool:
    """一枚数是否作为独立计数出现（前后不粘别的数字），避免"1721"里混出个"721"。"""
    return re.search(r"(?<!\d)" + re.escape(digits) + r"(?!\d)", text) is not None


def block_diff(path=None) -> list:
    """① 那枚断言的本体：交出"文档那一块与现读渲染差在哪几行"，空列表就是相等。

    抽成一枚函数是为了让反证刀能拿同一把尺去量影子副本，而不是另抄一份比较逻辑（那是第二本账）。
    """
    block, _plan = render_from(NAMES)
    printed = doc_block(path)
    problems = []
    if len(printed) != len(block):
        problems.append("行数不等：文档 %d 行 / 渲染 %d 行" % (len(printed), len(block)))
    for index in range(min(len(printed), len(block))):
        if printed[index] != block[index]:
            problems.append("第 %d 行不等：渲染 [%s] / 文档 [%s]" % (index, block[index][:56], printed[index][:56]))
    return problems


def test_the_prose_outside_the_block_carries_no_hand_written_count() -> None:
    """🔴 判据②：这一节改口之后，块外的散文一枚手抄的计数都不许留（要数就去块里现读）。"""
    prose = [line for line in doc_prose() if line.strip()]
    assert len(prose) >= 6, "§2.3 块外只剩 " + str(len(prose)) + " 行正文：这一格今天没在看守东西"
    offenders = stray_counts(prose)
    assert offenders == [], "§2.3 块外的散文里出现手抄的数：" + " / ".join(offenders)


def test_the_audited_numbers_each_have_a_named_fate() -> None:
    """派工词点名的那四枚数的下落：74 / 923 由命令给，713 是命令给的现读，721 从这一节彻底消失。"""
    block = "\r\n".join(doc_block())
    prose = "\r\n".join(doc_prose())
    plan = BF.plan_from_names(BF.read_names_file(str(NAMES)))
    assert has_count(block, str(plan["automatic_files"])), "可回填的文档数不在块里：批准材料读不到它"
    assert has_count(block, str(plan["automatic_chunks"])), "可回填的 chunk 数不在块里：批准材料读不到它"
    heaviest = BF.plan_table_departments(plan)[0]
    assert has_count(block, str(heaviest[2])), "最重那一格的现读数不在块里：" + str(heaviest)
    for text, where in ((block, "块"), (prose, "散文")):
        assert not has_count(text, "721"), "旧的手抄读数还留在" + where + "里：那就是「保留原数」那一头堵"
    assert not has_count(prose, str(heaviest[2])), (
        "现读数被抄进了" + "散文" + "：它明天就会变成下一枚 721")


# ------------------------------------------------------------------ ④ 与梯级账同一本账

AUTO_ROW = r"^\| 文件名只指向\*\*唯一\*\*一枚部门（可规则回填） \| \*\*(\d+)\*\* \| \*\*(\d+)\*\* \|"
TOTAL_ROW = r"^\| 合计（= 数据源行数 / 枚数） \| (\d+) \| (\d+) \|"
DEPT_LINE = r"^规则可达部门 \*\*(\d+)\*\* 枚"


def block_number(block: list, pattern: str) -> tuple:
    hits = [match for line in block if (match := re.match(pattern, line))]
    assert len(hits) == 1, "块里这个形状读不出唯一一格（" + pattern + "）：命中 " + str(len(hits)) + " 枚"
    return tuple(int(value) for value in hits[0].groups())


def shared_facts(block: list, ladder: list) -> dict:
    """那一块与那本梯级共同声明的三枚事实：可回填 chunk、合计 chunk、规则可达部门枚数。

    🔴 两侧都从**渲染出来的字**里取，不回同一枚 dict 里自我确认 —— 那样两块代码抄同一个 dict
    也叫不打架，而这一格要防的正是"§2.3 被接到第二套口径上"。不等就当场红。
    """
    rows = {row["rung"]: row for row in ladder}
    auto = block_number(block, AUTO_ROW)
    total = block_number(block, TOTAL_ROW)
    departments = block_number(block, DEPT_LINE)[0]
    s3 = [int(value) for value in re.findall(r"\d+", rows["S3"]["moved"])]
    s3b = [int(value) for value in re.findall(r"\d+", rows["S3b"]["moved"])]
    assert s3[0] == 0, "S3 那一级的起点不是空集：" + str(rows["S3"]["moved"])
    assert s3[1:] == [auto[1], departments], (
        "梯级 S3 与那一块对不上：S3 挪开 " + str(s3[1:]) + "，块里印 " + str([auto[1], departments]))
    assert s3b == [auto[1], total[1]], (
        "两本账读数不一致（同一枚事实两处不等）：S3b = " + str(s3b)
        + " / 块里 合计 chunk = " + str(total[1]) + " / 块里 可回填 chunk = " + str(auto[1]))
    return {"auto_files": auto[0], "auto_chunks": auto[1], "total_files": total[0],
            "total_chunks": total[1], "departments": departments}


def test_the_block_and_the_ladder_report_the_same_three_facts() -> None:
    """判据④：块里的三枚事实必须与 ``unlock_ladder()`` 的 S3 / S3b 一格不差。"""
    block, plan = render_from(NAMES)
    ladder = BF.unlock_ladder(plan, 1)
    facts = shared_facts(block, ladder)
    rows = {row["rung"]: row for row in ladder}
    assert facts["auto_chunks"] == plan["automatic_chunks"]
    assert facts["total_chunks"] == plan["total_chunks"]
    assert facts["departments"] == len(plan["departments_reachable_by_rule"])
    #: 梯级吃的那枚 arm 也必须站在同一批数上（判序与读数不许分家）
    assert rows["S3"]["arm"]["corpus_labelled_chunks"] == facts["auto_chunks"]
    assert rows["S3b"]["arm"]["corpus_labelled_chunks"] == facts["total_chunks"]
    assert len(rows["S3"]["arm"]["corpus_departments"]) == facts["departments"]


# ------------------------------------------------------------------ ⑤ 渲染器里不许长出手抄的数

RENDERERS = ("plan_table_buckets", "plan_table_departments", "plan_table_manual", "percent",
             "source_label", "render_plan_table", "plan_table_block", "plan_table_guard",
             "replace_plan_block", "read_names_file", "plan_table_cli")
TWO_DIGITS = re.compile(r"\d\d")


def count_literals_in(source: str, names: tuple = RENDERERS) -> list:
    """渲染那几枚函数里的"手抄计数"形状：≥ 十的数字常量，或字符串常量里出现两枚连号数字。

    放行个位数（排序键、返回码、`or 0`）与"字母粘连"的编号不在这一格里 —— 这里量的是**计数**。
    """
    offenders = []
    for node in ast.parse(source).body:
        if not (isinstance(node, ast.FunctionDef) and node.name in names):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Constant) or isinstance(sub.value, bool):
                continue
            value = sub.value
            if isinstance(value, (int, float)) and abs(value) >= 10:
                offenders.append("%s:%s 数字常量 %s" % (node.name, sub.lineno, value))
            elif isinstance(value, str) and TWO_DIGITS.search(value):
                offenders.append("%s:%s 字符串里出现连号数字 %r" % (node.name, sub.lineno, value[:24]))
    return offenders


def test_the_renderers_carry_no_hand_copied_count() -> None:
    """判据⑤：数只能从数据来，渲染那几枚函数里一枚计数常量都不许有。"""
    offenders = count_literals_in(SCRIPT.read_bytes().decode("utf-8"))
    assert offenders == [], "渲染器里长出手抄的数：" + " / ".join(offenders)


def test_the_rendering_functions_are_all_still_there() -> None:
    """闸的闸：上面那枚扫描的作用域不许被改名掏空 —— 一枚都不在就是扫描量了个空。"""
    names = {node.name for node in ast.parse(SCRIPT.read_bytes().decode("utf-8")).body
             if isinstance(node, ast.FunctionDef)}
    missing = sorted(set(RENDERERS) - names)
    assert not missing, "渲染器少了几枚（扫描就退化成空集）：" + str(missing)
# ------------------------------------------------------------------ 刀（全部落在 tmp 影子里）

#: 开工时那三枚被跟踪文件的字节账：每把刀进门取一次、出门比一次，不等就是本件自己在改盘。
PRISTINE = {rel: sha16(REPO / rel) for rel in (SCRIPT_REL, DOC_REL, NAMES_REL)}


def _shadow_doc(tmp_path: Path, mutate=None) -> Path:
    """把文档按字节搬进 tmp 再叠变异：盘上那一枚一个字都不动（R253 口径）。"""
    shadow = tmp_path / "lineage.md"
    shadow.write_bytes(DOC.read_bytes())
    if mutate is not None:
        lines = shadow.read_bytes().decode("utf-8").split("\r\n")
        mutate(lines)
        shadow.write_bytes("\r\n".join(lines).encode("utf-8"))
    return shadow


def _shadow_names(tmp_path: Path, rows: dict) -> Path:
    path = tmp_path / "names-shifted.tsv"
    body = "\r\n".join("%s\t%s" % (name, rows[name]) for name in sorted(rows)) + "\r\n"
    path.write_bytes(body.encode("utf-8"))
    return path


def _shadow_script(tmp_path: Path, old: str, new: str, tag: str):
    """把量具按字节抄进 tmp，改一格源码，再按影子姿势加载（盘上那枚一个字都不动）。"""
    root = tmp_path / ("shadow-" + tag)
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    #: 兄弟件照字节带上，再摆一枚"影子树不连库"的桩（R400 同一姿势）：
    #: 整枚换掉 BF 时，子进程那几枚不许因 ImportError 陪红 —— 红要红在变异上。
    (scripts / Path(LINEAGE_REL).name).write_bytes((REPO / LINEAGE_REL).read_bytes())
    for pkg in ("app", "app/db"):
        (root / pkg).mkdir(parents=True, exist_ok=True)
        (root / pkg / "__init__.py").write_text("", encoding="utf-8")
    (root / "app/db/connection.py").write_text(
        "def open_connection(settings):\n    raise RuntimeError('影子树不连库')\n" 
        "def parse_database_settings(url):\n    return url\n", encoding="utf-8")
    source = SCRIPT.read_bytes().decode("utf-8")
    hits = source.count(old)
    assert hits == 1, "影子变异落点不对（命中 " + str(hits) + " 枚，应当一枚）：" + old[:56]
    target = scripts / ("mutant_" + tag + ".py")
    mutated = source.replace(old, new, 1)
    target.write_bytes(mutated.encode("utf-8"))
    module = _load_shadow(target, "r409_mutant_" + tag, root)
    module._source = mutated  # 静态那枚闸要拿同一份变异源码去量
    return module


def _stderr(proc) -> str:
    return proc.stderr.decode("utf-8", "replace")


def test_knife_a_a_hand_copied_count_put_back_into_the_block_is_caught(tmp_path: Path) -> None:
    """刀(a)：把块里某一格换回手抄常量（旧账那一枚）⇒ 逐字节比对红，工具自己也不肯签字。

    这就是「批准材料与量具读数不是同一个数」那一族的形状：今天的它绿着，明天谁再抄一次它就红。
    """
    before = {rel: sha16(REPO / rel) for rel in (SCRIPT_REL, DOC_REL, NAMES_REL)}
    plan = BF.plan_from_names(BF.read_names_file(str(NAMES)))
    heaviest = str(BF.plan_table_departments(plan)[0][2])
    stale = str(int(heaviest) + 8)  # 上一班那笔漂移的尺寸：抄回来的数与现读差几枚，形状要一样

    def taint(lines: list) -> None:
        hits = [i for i, line in enumerate(lines) if "| " + heaviest + " |" in line]
        assert hits, "块里找不到最重那一格：这把刀没有落点，先修量具再来谈牙"
        for index in hits:
            lines[index] = lines[index].replace("| " + heaviest + " |", "| " + stale + " |")

    shadow = _shadow_doc(tmp_path, taint)
    tainted = sha16(shadow)
    problems = block_diff(shadow)
    assert problems, "把数抄回块里，逐字节比对居然没意见：那枚闸是永真的"
    assert any(stale in item for item in problems), "红句没端出被抄的那枚数：" + str(problems[:2])
    proc = run_tool("--no-db", "--names-file", str(NAMES), "--verify-plan-table", "--doc", str(shadow))
    assert proc.returncode == 4 and "MISMATCH" in _stderr(proc), _stderr(proc)
    assert sha16(shadow) == tainted, "只做一次比对就把影子文档改了：那枚旗标还兼着写口"
    after = {rel: sha16(REPO / rel) for rel in (SCRIPT_REL, DOC_REL, NAMES_REL)}
    assert before == after == PRISTINE, "验一遍就动了盘：" + str([k for k in before if before[k] != after[k]])


def test_knife_a2_a_hand_copied_count_in_the_prose_is_named() -> None:
    """刀(a2)：散文里塞一枚手抄的数、或者留一句「实为 NNN」两头堵 ⇒ 散文闸都必须点名。"""
    prose = [line for line in doc_prose() if line.strip()]
    assert stray_counts(prose) == [], "今天的散文已经不干净，先把这一格修回来"
    stale = list(prose)
    stale[-1] = stale[-1] + "（研发 721）"
    assert any("721" in item for item in stray_counts(stale)), "散文闸量不到手抄的数：那是永真的闸"
    hedged = list(prose)
    hedged[-1] = hedged[-1] + "（实为 713）"
    assert any("713" in item for item in stray_counts(hedged)), (
        "「保留原数 + 加一句实为多少」这种两头堵的写法量不到：那正是这一节的旧病")
    assert sha16(REPO / DOC_REL) == PRISTINE[DOC_REL], "本件在取证时动了盘上那枚文档"


def test_knife_b_moving_chunks_moves_the_numbers_and_the_section(tmp_path: Path) -> None:
    """刀(b)：影子数据里挪走一批可回填 chunk ⇒ 数必须跟着动，那一块也必须跟着动。

    🔴 这一把才是"手抄常量"的正解：抄死的数对数据变化装聋，派生出来的数跟着走。
    """
    before = {rel: sha16(REPO / rel) for rel in (SCRIPT_REL, DOC_REL, NAMES_REL)}
    rows = BF.read_names_file(str(NAMES))
    plan = BF.plan_from_names(rows)
    heaviest = BF.plan_table_departments(plan)[0]
    victims = sorted(name for name, count in rows.items()
                     if BF.hint_departments(name) == [heaviest[0]] and int(count) >= 4)
    assert victims, "最重那一格连一枚可读的文档都没有：这把刀没有落点"
    give = 4
    shifted = dict(rows)
    shifted[victims[0]] = int(shifted[victims[0]]) - give
    shadow_names = _shadow_names(tmp_path, shifted)

    new_plan = BF.plan_from_names(shifted)
    assert new_plan["total_chunks"] == plan["total_chunks"] - give, "合计没跟着数据动"
    assert new_plan["automatic_chunks"] == plan["automatic_chunks"] - give, "可回填那格没跟着数据动"
    new_heaviest = BF.plan_table_departments(new_plan)[0]
    assert new_heaviest[0] == heaviest[0] and new_heaviest[2] == heaviest[2] - give, (
        "部门分布没跟着数据动：" + str(heaviest) + " -> " + str(new_heaviest))

    honest = BF.plan_table_block(new_plan, str(shadow_names))
    printed = doc_block()
    assert honest != printed, "影子数据都变了，那一块还一字不动：它是抄来的"
    shadow_doc = _shadow_doc(tmp_path)
    wrote = run_tool("--no-db", "--names-file", str(shadow_names), "--write-plan-table",
                     "--doc", str(shadow_doc))
    assert wrote.returncode == 0 and "WROTE" in wrote.stdout.decode("utf-8"), _stderr(wrote)
    assert doc_block(shadow_doc) == honest, "重落地之后那块仍不等于渲染：渲染与落地两本账"
    assert doc_block(shadow_doc) != printed, "影子文档白改了一趟"
    refuse = run_tool("--no-db", "--names-file", str(shadow_names), "--verify-plan-table")
    assert refuse.returncode == 4 and "MISMATCH" in _stderr(refuse), (
        "拿变了的数据去验真文档，工具居然签字：那一块根本没跟数据绑上")
    after = {rel: sha16(REPO / rel) for rel in (SCRIPT_REL, DOC_REL, NAMES_REL)}
    assert before == after == PRISTINE, "重落地影子文档时把盘上那三枚一起改了：" + str(after)


def test_knife_c1_an_unreadable_data_source_shouts_and_emits_nothing(tmp_path: Path) -> None:
    """刀(c)：数据源取不到 / 一行都没有 / 形状不对 / 同名打架 ⇒ 非零退出 + 报名字 + stdout 全空。

    🔴 静默跳过就是假绿：交一张空表或交上一班的旧表，业主读到的都是"量过了"。
    """
    empty = tmp_path / "empty.tsv"
    empty.write_bytes(b"")
    malformed = tmp_path / "malformed.tsv"
    malformed.write_bytes("这一行没有制表符\r\n".encode("utf-8"))
    clash = tmp_path / "clash.tsv"
    clash.write_bytes("扫描件.txt\t3\r\n扫描件.txt\t4\r\n".encode("utf-8"))
    cases = {"不存在": tmp_path / "nope.tsv", "空文件": empty, "形状不对": malformed,
             "同名打架": clash, "是目录": tmp_path}
    for label, path in cases.items():
        proc = run_tool("--no-db", "--names-file", str(path), "--emit-plan-table")
        assert proc.returncode == 3, label + " 这一格今天不出账却还签字：rc=" + str(proc.returncode)
        assert proc.stdout == b"", label + " 取不到还往 stdout 交表：" + repr(proc.stdout[:80])
        assert "取不到" in _stderr(proc), label + " 没有当场喊取不到：" + _stderr(proc)[:120]
    for rel in (DOC_REL, NAMES_REL, SCRIPT_REL):
        assert sha16(REPO / rel) == PRISTINE[rel], "取不到那一格还动了盘上的 " + rel


def test_knife_c2_a_doc_without_its_markers_shouts_instead_of_growing_a_second_block(tmp_path: Path) -> None:
    """刀(c2)：那一对标记丢了 / 重了 / 文档不在 ⇒ verify 与 write 都非零退出，且一个字都不写。

    🔴 不许"找不到就在文件尾追加一块"：那等于养出第二块，谁都不知道哪一块是真的。
    """
    def only(lines: list, marker: str, label: str) -> int:
        hits = [i for i, line in enumerate(lines) if line.strip() == marker]
        assert len(hits) == 1, "影子变异落点不对（" + label + " 命中 " + str(len(hits)) + " 枚）"
        return hits[0]

    def drop_begin(lines: list) -> None:
        del lines[only(lines, BF.BLOCK_BEGIN, "BEGIN")]

    def double_begin(lines: list) -> None:
        lines.insert(only(lines, BF.BLOCK_BEGIN, "BEGIN") + 1, BF.BLOCK_BEGIN)

    def no_end(lines: list) -> None:
        lines[only(lines, BF.BLOCK_END, "END")] = "这一行被人改成了散文"

    cases = {"丢了 BEGIN": drop_begin, "两枚 BEGIN": double_begin, "没有 END": no_end}
    for label, mutate in cases.items():
        shadow = _shadow_doc(tmp_path, mutate)
        was = sha16(shadow)
        for flag in ("--verify-plan-table", "--write-plan-table"):
            proc = run_tool("--no-db", "--names-file", str(NAMES), flag, "--doc", str(shadow))
            assert proc.returncode == 3, label + " + " + flag + " 没喊停：rc=" + str(proc.returncode)
            assert "取不到" in _stderr(proc), label + " + " + flag + " 的红句没报名字"
            assert b"R409:BEGIN" not in proc.stdout, label + " 还在往 stdout 交块"
        assert sha16(shadow) == was, label + "：写口在标记不唯一时还是动手了"
    absent = tmp_path / "absent.md"
    proc = run_tool("--no-db", "--names-file", str(NAMES), "--verify-plan-table", "--doc", str(absent))
    assert proc.returncode == 3 and not absent.exists(), "文档不在就该喊取不到，不该顺手造一枚"
    assert sha16(REPO / DOC_REL) == PRISTINE[DOC_REL], "验影子文档时动了盘上那一枚"


def test_knife_c3_a_zero_reading_is_not_the_same_as_no_reading(tmp_path: Path) -> None:
    """正对照：真的"一枚都回填不了"必须照常出账并写明 0 枚 —— 不许与"取不到"混成一格。"""
    rows = {"未命名扫描件_0001.pdf": 4, "invoice_0002.pdf": 2}
    plan = BF.plan_from_names(rows)
    assert plan["automatic_chunks"] == 0 and plan["departments_reachable_by_rule"] == [], plan
    assert BF.plan_table_guard(plan) == "", "全零的读数被当成了取不到：那是把测量结果藏起来"
    block = BF.plan_table_block(plan, str(NAMES))
    assert "规则可达部门 **0** 枚" in "\r\n".join(block), "零读数那一格没写在块里"
    assert block[0] == BF.BLOCK_BEGIN and block[-1] == BF.BLOCK_END


def test_knife_d_a_hardcoded_count_in_the_renderer_is_caught_twice(tmp_path: Path) -> None:
    """刀(d)：把渲染器里某一格换回写死的常量 ⇒ 静态那枚（⑤）与数据位移那枚（刀 b）一起红。

    两把都要：静态那枚抓"源码里出现计数"，位移那枚抓"数对不上数据"——只有一枚就留一角盲区。
    """
    anchor = '        ("文件名只指向**唯一**一枚部门（可规则回填）", plan["automatic_files"], plan["automatic_chunks"]),'
    forged = '        ("文件名只指向**唯一**一枚部门（可规则回填）", 74, 923),'
    mutant = _shadow_script(tmp_path, anchor, forged, "hardcoded")
    assert count_literals_in(mutant._source) != [], "静态那枚没抓到写死的计数"
    rows = BF.read_names_file(str(NAMES))
    shifted = dict(rows)
    victims = sorted(name for name, count in rows.items()
                     if len(BF.hint_departments(name)) == 1 and int(count) >= 6)
    assert victims, "找不到一枚可回填且枚数够减的文档：这把刀没有落点"
    shifted[victims[0]] = int(shifted[victims[0]]) - 5
    honest = BF.plan_table_block(BF.plan_from_names(shifted), str(NAMES))
    deaf = mutant.plan_table_block(mutant.plan_from_names(shifted), str(NAMES))
    assert honest != deaf, "位移那枚也抓不到：数据变了那块还一字不动"
    assert doc_block() != deaf, "写死的常量与盘上那一块竟然相等：今天的绿是巧合"


def test_knife_e_wiring_the_section_to_a_second_ledger_is_caught(tmp_path: Path) -> None:
    """刀(e)：把那一块的「合计」接到"可回填"那一枚事实上 ⇒ ④ 那枚必须红。

    这一格静态量不到（源码里没有任何计数），只有"同一枚事实两处读数"能抓 —— 所以 ④ 不许省。
    """
    anchor = '        ("合计（= 数据源行数 / 枚数）", plan["total_files"], plan["total_chunks"]),'
    forged = '        ("合计（= 数据源行数 / 枚数）", plan["total_files"], plan["automatic_chunks"]),'
    mutant = _shadow_script(tmp_path, anchor, forged, "secondledger")
    assert count_literals_in(mutant._source) == [], "这把刀的形状变了：那它就不该只给 ④ 抓"
    rows = BF.read_names_file(str(NAMES))
    plan = BF.plan_from_names(rows)
    forged_block = mutant.plan_table_block(plan, str(NAMES))
    with pytest.raises(AssertionError) as caught:
        shared_facts(forged_block, BF.unlock_ladder(plan, 1))
    assert "两本账读数不一致" in str(caught.value), "红句没说出是哪两处打架：" + str(caught.value)
    assert forged_block != doc_block(), "接错口径居然与盘上那块相等：今天的绿是巧合"


def test_the_ruler_shares_one_judgement_with_the_lineage_tool() -> None:
    """判据④的前半：两本账不许各养一份判序 —— 量具吃进去的就是血缘件那一枚 ``classify_arm``。"""
    assert BF.classify_arm is TOOL.classify_arm, "回填量具自己复制了第二份判序"
    assert BF.hint_departments is TOOL.hint_departments, "命中口径也被抄了第二份"


# ------------------------------------------------------------------ 零连库 / 零写口

def test_the_ruler_refuses_to_connect_just_to_render_a_table() -> None:
    """判据⑥：带着 DATABASE_URL 也不许为了一张表去连库 —— 渲染这一格只吃只读导出。"""
    bogus = "postgresql://nobody@invalid.invalid:1/nope"
    proc = run_tool("--emit-plan-table", "--database-url", bogus)
    assert proc.returncode == 2, "没带 --no-db 也肯出账：rc=" + str(proc.returncode)
    assert "拒绝" in _stderr(proc), _stderr(proc)
    assert proc.stdout == b"", "拒连还往 stdout 交表"


def test_the_rendering_code_adds_no_connection_or_sql_surface() -> None:
    """🔴 新增那一层不许有写口：连接面走裸调用名，SQL 关键词走字符串常量，两头都扫。"""
    source = SCRIPT.read_bytes().decode("utf-8")
    tree = ast.parse(source)
    forbidden_calls = {"connect", "execute", "executemany", "cursor", "commit"}
    sql_words = ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "TRUNCATE")
    offenders = []
    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef) and node.name in RENDERERS):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) \
                    and sub.func.id in forbidden_calls:
                offenders.append("%s:%s 调用 %s" % (node.name, sub.lineno, sub.func.id))
            elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                offenders.extend("%s:%s 字符串里出现 %s" % (node.name, sub.lineno, word)
                                 for word in sql_words if word in sub.value.upper())
    assert offenders == [], "渲染那一层长出写口：" + " / ".join(offenders[:6])


def test_no_tracked_file_moves_under_any_of_these_pins() -> None:
    """收口：本件从头到尾只有读口（变异全在 tmp），盘上那三枚的字节账一格都不许动。"""
    moved = [rel for rel, digest in PRISTINE.items() if sha16(REPO / rel) != digest]
    assert moved == [], "这些钉在取证时改了被跟踪文件：" + str(moved)
