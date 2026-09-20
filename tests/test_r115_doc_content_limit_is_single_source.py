"""R115 · 一条命中最多进 prompt 的正文长度，全仓只许有一枚真源。

真源是 ``app/rag/retrieval_pipeline.py`` 的 ``DOC_HIT_CONTENT_CHARS``（R112 落的）。本单把最
后两枚手抄的 500 接回真源——``app/mcp_server.py`` 的检索串、``scripts/perf_probe_rounds.py``
的探针工具串——这个文件钉的是"别再抄第三枚"：

- 扫 ``app/**`` 与 ``scripts/**`` 的每个 ``.py``（只看非注释行）：凡是「把文档正文裁到一枚
  字面量长度」的式子——被切对象里带 content / body / chunk / passage / prose / text 字样、
  切片上界是字面量整数、且这枚整数等于真源的值——除真源自己的定义行之外一律违规，逐条印
  ``文件:行号:原文``，不许静默通过。识别式自己也配正反对照样本，防止它退化成空响。
- 为什么按"等于真源的值"来认：仓里还有别的正文截断，量的是别的尺——去重键 120 字、调试摘录
  240 字、历史行 200 字、会话标题 30 字。本单守的是 R112 那类分叉：**装箱按一份长度计量、
  发给模型按另一份长度**，所以钉的是同一枚长度的第二次出现，不是"所有带数字的切片"。
- 两处消费点必须按名字问真源要数，各照本文件既有风格：MCP 那条腿走函数内 import（它本来就
  从同一模块 import 了 ``format_relevance``）；探针走它自己那套 ``ast`` 只读产品源码——该文件
  顶部写死"不许手抄"，且它不 import 产品码，否则会把 sentence-transformers/torch 拉进一个
  专门测延时的进程。
- 零模型、零容器、零 ``app`` import：连真源那枚数都是用 ``ast`` 从源码里读出来的，所以这条
  守卫在真机评测窗口里也能跑。
"""

import ast
import io
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]
SOURCE_MODULE = pathlib.Path("app") / "rag" / "retrieval_pipeline.py"
SOURCE_NAME = "DOC_HIT_CONTENT_CHARS"
MCP_FILE = pathlib.Path("app") / "mcp_server.py"
PROBE_FILE = pathlib.Path("scripts") / "perf_probe_rounds.py"
SCAN_ROOTS = (pathlib.Path("app"), pathlib.Path("scripts"))
#: R112 之前这两处手抄的就是 500，真源也是 500 —— 接上真源后截断结果必须一字不差。
CAP_BEFORE_R115 = 500
#: 命中行的行头：装箱与发模型吃的都是这一行，所以它也是"这是正文截断"的现场证据。
HIT_HEADER_MARKS = ("来源:", "相关度:")

BODY_WORD = re.compile(
    r"(?:content|body|chunk|passage|prose)|(?<![a-z0-9])text(?![a-z0-9])", re.IGNORECASE
)
SLICE_TO_LITERAL = re.compile(r"\[\s*:\s*(\d+)\s*\]")
#: 只看切片左边紧贴的那一小段，认它切的是不是"正文"。
OPERAND_WINDOW = 40


def _read(relative):
    return io.open(REPO / relative, encoding="utf-8").read()


def _python_files():
    return sorted(p for root in SCAN_ROOTS for p in (REPO / root).rglob("*.py"))


def _source_definition():
    """真源定义那行的 ``(行号, 值)``；找不到或找到两枚都是本用例该订正的信号。"""
    tree = ast.parse(_read(SOURCE_MODULE))
    found = [
        (node.lineno, int(ast.literal_eval(node.value)))
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == SOURCE_NAME for t in node.targets)
    ]
    assert len(found) == 1, (
        f"{SOURCE_MODULE} 里 {SOURCE_NAME} 的定义有 {len(found)} 枚（{found}），真源必须只有一枚"
    )
    return found[0]


def _line_copies_cap(line, cap):
    """这一行是否在把文档正文裁到一枚手抄的 ``cap``（字面量整数，不是真源的名字）。"""
    if line.lstrip().startswith("#"):
        return False
    for match in SLICE_TO_LITERAL.finditer(line):
        if int(match.group(1)) != cap:
            continue
        window = line[max(0, match.start() - OPERAND_WINDOW) : match.start()]
        if BODY_WORD.search(window):
            return True
    return False


def _copied_cap_offenders(cap, exempt):
    """全仓扫一遍，返回 ``(违规行, 扫过的文件数)``。"""
    offenders, scanned = [], 0
    for path in _python_files():
        scanned += 1
        relative = path.relative_to(REPO)
        for number, line in enumerate(_read(relative).splitlines(), start=1):
            if (str(relative), number) in exempt:
                continue
            if _line_copies_cap(line, cap):
                offenders.append(f"{relative}:{number}: {line.strip()}")
    return offenders, scanned


def _hit_render_lines(text):
    return [
        line.strip()
        for line in text.splitlines()
        if all(mark in line for mark in HIT_HEADER_MARKS)
    ]


# ==================== 判据 2：全仓不许再抄一枚 ====================


def test_no_site_copies_the_document_content_cap():
    """守卫主用例：除真源那一行定义外，全仓不得再出现同一枚正文截断长度。"""
    lineno, cap = _source_definition()
    offenders, scanned = _copied_cap_offenders(cap, exempt={(str(SOURCE_MODULE), lineno)})
    assert scanned >= 100, (
        f"app/ 与 scripts/ 只扫到 {scanned} 个 .py：扫描根目录不对，这条守卫就是空响"
    )
    assert offenders == [], (
        f"{SOURCE_NAME} 的真源只有一枚（{SOURCE_MODULE}:{lineno} = {cap} 字），"
        f"这些地方又手抄了一枚 {cap} 去裁正文：" + " | ".join(offenders)
    )


def test_recognizer_has_teeth_on_the_shape_it_must_catch():
    """识别式的正反对照：真实样本必须红，别的尺必须不响——不然守卫就是在装样子。"""
    _, cap = _source_definition()
    assert cap == CAP_BEFORE_R115, (
        f"真源已从 {CAP_BEFORE_R115} 字变成 {cap} 字，下面的正反样本要跟着重抄"
    )
    must_fire = [
        # R115 开工前 app/mcp_server.py:55 的原文
        """        f"[{i}] 来源:{d.get('source')} 相关度:{format_relevance(d)}\\n{d['content'][:500]}\"""",
        # R115 开工前 scripts/perf_probe_rounds.py:166 的原文
        """        parts.append("[%d] 来源:%s 相关度:%s\\n%s" % (i, source, "未评分", content[:500]))""",
        "def render(hit): return hit.body[:500]",
        "excerpt = chunk[: 500 ]",
        "text = max_text[:500]",
    ]
    must_be_quiet = [
        "return d['content'][:DOC_HIT_CONTENT_CHARS]",
        "DOC_HIT_CONTENT_CHARS = 500",
        "key = doc['content'][:120]  # 去重键：另一把尺",
        "summary[key] = str(value)[:500]  # 台账里的非正文字段",
        "parts.append((path.name, text[:cap]))",
        "tool_text = header + cn_text(500)  # 合成料尺寸，不是截断动作",
        "raise HTTPException(status_code=500)",
        "tail = detail[-500:]  # 取尾巴，不是裁正文",
        "# 以前这里写的是 content[:500]",
        "session['title'] = content[:30]",
    ]
    for line in must_fire:
        assert _line_copies_cap(line, cap), f"识别式漏掉了这种手抄正文截断：{line}"
    for line in must_be_quiet:
        assert not _line_copies_cap(line, cap), f"识别式误伤了不该管的式子：{line}"


# ==================== 判据 1：两处消费点各按本文件风格接回真源 ====================


def test_mcp_search_string_asks_the_single_source_for_the_cap():
    """MCP 那条腿：函数内 import 真源，命中串里不留字面量长度。"""
    _, cap = _source_definition()
    text = _read(MCP_FILE)
    imported = {
        alias.name
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.ImportFrom) and node.module == "app.rag.retrieval_pipeline"
        for alias in node.names
    }
    assert SOURCE_NAME in imported, (
        f"{MCP_FILE} 没从真源模块 import {SOURCE_NAME}，现在只有：{sorted(imported)}"
    )
    render_lines = _hit_render_lines(text)
    assert len(render_lines) == 1, f"MCP 的命中渲染行应有 1 枚，实得 {len(render_lines)} 枚：{render_lines}"
    line = render_lines[0]
    assert f"[:{SOURCE_NAME}]" in line, f"MCP 的命中串没引用真源：{line}"
    assert not _line_copies_cap(line, cap), f"MCP 的命中串还在用手抄长度：{line}"


def test_perf_probe_reads_the_cap_out_of_the_product_source():
    """探针：照它自己的规矩（ast 只读产品源码，不 import 产品码）接回真源。"""
    text = _read(PROBE_FILE)
    assert SOURCE_NAME in text, f"{PROBE_FILE} 里已经没有 {SOURCE_NAME} 这个名字：正文上限没接回真源"
    assert '"app/rag/retrieval_pipeline.py"' in text, (
        "探针读真源用的那个路径字面量不见了，doc_content_cap() 就不可能读到它"
    )
    assert not re.search(r"^[ \t]*(?:from|import)[ \t]+app\.", text, re.MULTILINE), (
        "探针 import 了产品码：那会把 sentence-transformers/torch 拉进一个测延时的进程。"
        "正文上限请继续用 ast 只读源码，不要改成 import"
    )
    render_lines = [line for line in _hit_render_lines(text) if "[:cap]" in line]
    assert len(render_lines) == 1, (
        f"探针的命中渲染行应有 1 枚且用传入的 cap，实得 {len(render_lines)} 枚："
        f"{_hit_render_lines(text)}"
    )


def test_probe_cap_reader_measures_the_same_number_as_the_source(tmp_path):
    """把探针那枚读数函数单独抠出来跑（不 import 探针、不跑探针），证明它量到的就是真源。"""
    _, cap = _source_definition()
    func = next(
        (
            node
            for node in ast.parse(_read(PROBE_FILE)).body
            if isinstance(node, ast.FunctionDef) and node.name == "doc_content_cap"
        ),
        None,
    )
    assert func is not None, f"{PROBE_FILE} 里没有 doc_content_cap()：探针没按名字问真源要数"
    module = ast.Module(body=[func], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"ast": ast, "pathlib": pathlib, "APP_ROOT": REPO}
    exec(compile(module, str(REPO / PROBE_FILE), "exec"), namespace)
    assert namespace["doc_content_cap"](REPO) == cap, "探针从真源量到的长度和真源自己不一样"
    assert namespace["doc_content_cap"]() == cap, (
        "默认 root（APP_ROOT）量不到真源：探针换个目录就会拿别的数"
    )
    empty_rag = tmp_path / "app" / "rag"
    empty_rag.mkdir(parents=True)
    (empty_rag / "retrieval_pipeline.py").write_text(
        "DOC_HIT_CONTENT_CHARS_MOVED = 500\n", encoding="utf-8"
    )
    try:
        namespace["doc_content_cap"](tmp_path)
    except RuntimeError:
        pass
    else:
        raise AssertionError("真源里那枚数不见了，探针却没报错——它一定还兜着自己的一份")


def test_the_shared_number_is_still_the_one_both_sites_cut_at():
    """行为不变的钉子：真源仍是 500，两枚消费点都不再带手抄的字面量。"""
    _, cap = _source_definition()
    assert cap == CAP_BEFORE_R115, (
        f"真源从 {CAP_BEFORE_R115} 字变成了 {cap} 字：本单『截断结果一字不差』的前提失效，"
        "这两处的历史对账要重做，先回总控"
    )
    for relative in (MCP_FILE, PROBE_FILE):
        text = _read(relative)
        assert "[:500]" not in text, f"{relative} 还留着 [:500] 的字面量截断"
        assert "500)" not in text, f"{relative} 还在把 500 当实参递给某个函数"
