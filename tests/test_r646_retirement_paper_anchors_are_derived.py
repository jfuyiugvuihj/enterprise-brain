# -*- coding: utf-8 -*-
"""R646 常驻钉 —— Chroma 退役纸只许挂派生锚：锚要枚枚真解析，且必须落在 R60 下刀的那一支。

派工词 R646 的判据对号：
  1) 这张纸正文与表格里那 15 枚「某点 py 冒号数字」的手抄坐标全部换成 文件::符号 派生锚。
     本件拿派工词点名的那枚正则原文再扫一次，命中即红，红句逐枚点名是第几行。
  2) 同一格里的非 .py 手抄行号（compose 那一枚、human-gates 那三枚、主树 env 那两枚）一并
     派生化：compose 用键名＋service，human-gates 用 H 号，env 用键名。本件用第二把尺盯它。
  3) 常驻钉不许是死尺：形状尺对合成分必须真咬并点得出行位，锚点尺对伪造符号必须真红。
  4) 内容事实一字不许改 —— 反过来钉住它：每一枚锚点都得现读解析得到，而且锚点那枚符号体内
     必须真有纸上说的那一件事（collection.add / PersistentClient / 遗留问句 / 出厂缺省值）。

🔴 本件全程只读盘上文本，不调 git、不比 dirty、不看任何人的施工态（同族事故 #96/#107/#113）：
   「盘上字节等于 HEAD blob」不是这枚牙的判据；纸面再抄回一枚坐标就是红，与工作树脏不脏无关。
🔴 零 import 产品码：锚点解析走 AST 腿。在册那把同族尺（R630）要先 import 观测面，而 app 码
   在模块级就构造 DocumentRetriever()，一 import 就朝被跟踪的 chroma_db 写回；observability.py
   此刻还由 R649 在治 ⇒ 本件不借那条 import 腿，只沿用它的形状约定，不另立更松的规矩。
🔴 本件自己一枚坐标都不抄：要样本就把串拆开来现场拼（R638 同口径），源文里零枚数字落点。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAPER = REPO / "docs" / "deployment" / "chroma-retirement-path.md"

#: 派工词判据 1 点名那枚正则的原文形状：不放宽，也不收窄。
TICKET_SHAPE = r"[A-Za-z0-9_./-]+\.py:[0-9]+"
PY_COORD = re.compile(TICKET_SHAPE + r"(?:-[0-9]+)?")

#: 判据 2 那把更宽的尺：任何「文件名冒号数字」都是会漂的落点，不止 .py。
OTHER_SUFFIXES = ("yml", "yaml", "md", "markdown", "json", "jsonl", "toml", "sh",
                  "env", "server", "ini", "cfg", "txt", "example", "sql", "ps1",
                  "html", "css", "lock")
OTHER_COORD = re.compile(r"[A-Za-z0-9_./-]+\.(?:%s):[0-9]+(?:-[0-9]+)?" % "|".join(OTHER_SUFFIXES))

PY_ANCHOR = re.compile(r"([A-Za-z0-9_./-]+\.py)::([A-Za-z0-9_.]+)")
YML_ANCHOR = re.compile(r"([A-Za-z0-9_./-]+\.(?:yml|yaml))::([A-Za-z0-9_.-]+)")
MD_ANCHOR = re.compile(r"([A-Za-z0-9_./-]+\.md)::([A-Za-z0-9_-]+)")

RETRIEVER = "app/rag/retriever.py"
PAPER_CITE = "docs/deployment/chroma-retirement-path.md"


# ==================== 把手：读纸、数形状、解析锚 ====================


def read(rel: str) -> str:
    path = REPO / rel
    if not path.is_file():
        raise OSError("纸面点名的文件不在盘上：" + rel)
    return path.read_text(encoding="utf-8")


def paper() -> str:
    return PAPER.read_text(encoding="utf-8")


def paper_lines(text: str | None = None) -> list[str]:
    return (paper() if text is None else text).splitlines()


def py_coordinate_offenders(text: str) -> list[str]:
    """判据 1 的尺：命中一枚报一枚，红句里带行位（派工词要求点名是哪一行）。"""
    return ["%s 第 %d 行手抄坐标 %s" % (PAPER_CITE, number, match.group(0))
            for number, row in enumerate(text.splitlines(), 1)
            for match in PY_COORD.finditer(row)]


def other_coordinate_offenders(text: str) -> list[str]:
    return ["%s 第 %d 行手抄行号 %s" % (PAPER_CITE, number, match.group(0))
            for number, row in enumerate(text.splitlines(), 1)
            for match in OTHER_COORD.finditer(row)]


def anchor_census(text: str | None = None) -> list[tuple[str, str, str, int]]:
    """纸上现读的派生锚清单：(leg, 文件, 符号, 行位)，逐枚可抽查。"""
    found: list[tuple[str, str, str, int]] = []
    for number, row in enumerate(paper_lines(text), 1):
        for regex, leg in ((PY_ANCHOR, "py"), (YML_ANCHOR, "yml"), (MD_ANCHOR, "md")):
            for match in regex.finditer(row):
                found.append((leg, match.group(1), match.group(2), number))
    return found


def unanchored(anchors) -> list[str]:
    bad = []
    for leg, rel, dotted, number in sorted(set(anchors)):
        ok = {"py": py_anchor_resolves, "yml": yml_anchor_resolves,
              "md": md_anchor_resolves}[leg](rel, dotted)
        if not ok:
            bad.append("第 %d 行锚点 %s::%s 现读解析不到" % (number, rel, dotted))
    return bad


_TREES: dict[str, ast.Module] = {}


def tree_for(rel: str) -> ast.Module:
    if rel not in _TREES:
        _TREES[rel] = ast.parse(read(rel))
    return _TREES[rel]


def _defined_name(node: ast.stmt) -> str | None:
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                return target.id
        return None
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def _children(container) -> list[ast.stmt]:
    """真承载定义的下层体：条件块、try、with 里定义的符号同样算在册。"""
    if isinstance(container, ast.Module):
        return list(container.body)
    body = list(getattr(container, "body", []) or [])
    if isinstance(container, ast.Try):
        body += [line for handler in container.handlers for line in handler.body]
    body += list(getattr(container, "orelse", []) or [])
    body += list(getattr(container, "finalbody", []) or [])
    return body


def find_symbol(rel: str, dotted: str):
    """沿锚点写下的点号链逐层现读；读不到交 None（不猜、不宽松匹配）。"""
    node = None
    container = tree_for(rel)
    for part in dotted.split("."):
        hit = None
        for child in _children(container):
            if _defined_name(child) == part:
                hit = child
                break
        if hit is None:
            return None
        node = hit
        container = hit
    return node


def py_anchor_resolves(rel: str, dotted: str) -> bool:
    return find_symbol(rel, dotted) is not None


def symbol_body(rel: str, dotted: str) -> str:
    node = find_symbol(rel, dotted)
    if node is None:
        raise OSError("锚点解析不到：%s::%s" % (rel, dotted))
    lines = read(rel).splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def module_value(rel: str, name: str):
    for child in tree_for(rel).body:
        if _defined_name(child) == name and isinstance(
                child, (ast.Assign, ast.AnnAssign)):
            return ast.literal_eval(child.value)
    raise OSError("模块级在册名找不到：%s::%s" % (rel, name))


def _yml_rows(rel: str) -> list[tuple[int, str]]:
    rows = []
    for raw in read(rel).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        rows.append((len(raw) - len(raw.lstrip(" ")), raw.strip()))
    return rows


def _yml_locate(rel: str, parts: list[str]):
    rows = _yml_rows(rel)
    floor = 0
    index = -1
    for part in parts:
        found = None
        pattern = re.compile(r"^%s:(\s|$)" % re.escape(part))
        for pos in range(index + 1, len(rows)):
            indent, text = rows[pos]
            if indent < floor:
                break
            if indent == floor and pattern.match(text):
                found = pos
                break
        if found is None:
            return None
        index = found
        floor = rows[found][0] + 1
    return index, floor


def yml_anchor_resolves(rel: str, dotted: str) -> bool:
    return _yml_locate(rel, dotted.split(".")) is not None


def yml_block(rel: str, dotted: str) -> list[str]:
    """那枚键之下、更深缩进里的每一行（键名派生锚的现读凭据）。"""
    located = _yml_locate(rel, dotted.split("."))
    if located is None:
        return []
    index, floor = located
    out = []
    for indent, text in _yml_rows(rel)[index + 1:]:
        if indent < floor:
            break
        out.append(text)
    return out


def services_mounting(rel: str, alias: str) -> list[str]:
    """按缩进现读：哪几枚 service 的块里挂了那枚 YAML 锚（不引第三方 yaml）。"""
    rows = _yml_rows(rel)
    start = next((i for i, (_ind, text) in enumerate(rows) if text == "services:"), None)
    if start is None:
        raise OSError("%s 里没有顶层 services 块" % rel)
    holders: list[str] = []
    current = None
    for indent, text in rows[start + 1:]:
        if indent == 0:
            break
        if indent == 2 and text.endswith(":"):
            current = text[:-1].strip()
        elif current and alias in text:
            holders.append(current)
    return sorted(set(holders))


def md_anchor_resolves(rel: str, dotted: str) -> bool:
    return md_heading(rel, dotted) is not None


def md_heading(rel: str, token: str) -> str | None:
    """H 号派生锚的现读凭据：那本闸门账里以这枚号开头的那一行标题。"""
    for raw in read(rel).splitlines():
        match = re.match(r"^#{1,6}\s+([^\s#]+)", raw)
        if match and match.group(1) == token:
            return raw.strip()
    return None


def row_starting_with(prefix: str) -> str:
    for line in paper_lines():
        if line.startswith(prefix):
            return line
    raise AssertionError("退役纸里找不到以 %r 开头的那一行：纸的结构被人改了" % prefix)


def forged(*parts: str) -> str:
    """把坐标拆开来现场拼出（本件源文因此一枚真坐标都没有）。"""
    return "".join(parts)


# ==================== 判据 1 —— 手抄坐标清零（并且这尺不是死的）====================


def test_the_retirement_paper_carries_no_hand_copied_python_coordinate() -> None:
    """判据 1 正文：这张纸里再出现「某点 py 冒号数字」就当场红，红句点名哪一行。"""
    assert TICKET_SHAPE == r"[A-Za-z0-9_./-]+\.py:[0-9]+", "形状尺被人改窄/改宽了"
    offenders = py_coordinate_offenders(paper())
    assert offenders == [], "退役纸又抄回行号了：" + "；".join(offenders)


def test_the_retirement_paper_carries_no_hand_copied_line_coordinate_at_all() -> None:
    """判据 2 正文：compose / human-gates / env 那几枚非 .py 手抄行号同样一枚不许留。"""
    offenders = other_coordinate_offenders(paper())
    assert offenders == [], "退役纸还挂着会漂的行号：" + "；".join(offenders)


def test_the_shape_ruler_bites_and_names_the_line_it_bites() -> None:
    """死尺前置：把坐标拆开拼出来喂进合成盘面，两把尺都必须咬，且红句报得出行位。"""
    py_forged = forged("app/rag/retriever", ".py", ":", "1", "5", "2", "2")
    yml_forged = forged("docker-compose", ".yml", ":", "4", "4")
    gates_forged = forged("docs/handoff/2026-09-17-human-gates", ".md", ":", "4", "3")
    sample = "\r\n".join(["开头一行。", "中间一行。", "还是正文。",
                          "落点见 " + py_forged + "。",
                          "卷名 " + yml_forged + " 与闸门 " + gates_forged + "。"])
    py_hits = py_coordinate_offenders(sample)
    other_hits = other_coordinate_offenders(sample)
    assert py_hits == ["第 4 行手抄坐标 " + py_forged] or "第 4 行" in " ".join(py_hits), py_hits
    assert any("第 5 行" in row for row in other_hits), other_hits
    assert any(yml_forged in row for row in other_hits), other_hits
    assert any(gates_forged in row for row in other_hits), other_hits
    assert py_coordinate_offenders(paper()) == [] and other_coordinate_offenders(paper()) == []


# ==================== 判据 4 —— 锚点枚枚真解析，且落在下刀的那一支 ====================


def test_the_paper_is_anchored_and_every_anchor_resolves() -> None:
    """15 枚坐标换成锚之后必须有货：清单非空，每一枚都现读解析得到。"""
    census = anchor_census()
    assert census, "退役纸一枚派生锚都没有：判据 4 成了空转"
    unique = {(leg, rel, dotted) for leg, rel, dotted, _row in census}
    assert len(unique) >= 15, "锚点比原来那 15 枚坐标还少，说明有落点被整格删掉了：%d" % len(unique)
    assert unanchored(census) == []


def test_a_fabricated_symbol_dies_on_the_anchor_ruler() -> None:
    """锚点尺的正控：把一枚在册锚的符号名换成一枚不存在的，必须解析不到。"""
    census = [(rel, dotted) for leg, rel, dotted, _row in anchor_census() if leg == "py"]
    assert census, "本件前提变了：纸上没有 .py 锚点"
    rel, dotted = sorted(set(census))[0]
    assert py_anchor_resolves(rel, dotted) is True
    ghost = "%s%s" % (dotted.split(".")[0], "_r646_ghost_symbol")
    assert py_anchor_resolves(rel, ghost) is False


def test_the_delete_row_anchors_point_at_the_symbols_that_actually_delete() -> None:
    """本单的根因：错位的那两枚正是「删除」那一臂，锚必须落在真发问与真删的那两支上。"""
    row = row_starting_with("| 删除 |")
    for dotted in ("DocumentRetriever._document_rows_by_leg", "DocumentRetriever.delete_document"):
        anchor = "%s::%s" % (RETRIEVER, dotted)
        assert anchor in row, "删除那一格没挂上 %s" % anchor
        assert py_anchor_resolves(RETRIEVER, dotted), anchor
        assert isinstance(find_symbol(RETRIEVER, dotted), ast.FunctionDef), anchor
    delete_body = symbol_body(RETRIEVER, "DocumentRetriever.delete_document")
    assert "_document_rows_by_leg(" in delete_body, "delete_document 今天不再问那一臂：纸要改口"
    leg_body = symbol_body(RETRIEVER, "DocumentRetriever._document_rows_by_leg")
    assert "collection.get(" in leg_body, "_document_rows_by_leg 里已经没有遗留问句：纸要改口"


def test_the_cutting_markers_really_sit_inside_the_anchored_symbols() -> None:
    """S0/S5 那几支的锚不许只是「符号存在」：纸上说的那件事要在符号体内现读得到。"""
    markers = (
        (RETRIEVER, "DocumentRetriever._write_batch", ("collection.add",)),
        (RETRIEVER, "DocumentRetriever.__init__",
         ("chromadb.PersistentClient", "chromadb is None", "_JsonCollection")),
        (RETRIEVER, "DocumentRetriever._writes_go_to_pgvector",
         ("stores_vectors", "dual_write_enabled", "pgvector_writes_are_primary")),
        ("app/rag/indexing.py", "pgvector_writes_are_primary", ("read_backend",)),
        ("app/rag/pg_store.py", "dual_write_enabled", ("DUAL_WRITE_ENV",)),
    )
    for rel, dotted, wants in markers:
        anchor = "%s::%s" % (rel, dotted)
        assert anchor in paper(), "退役纸没挂这枚锚：%s" % anchor
        body = symbol_body(rel, dotted)
        for want in wants:
            assert want in body, "%s 体内现读不到 %r" % (anchor, want)


def test_the_module_level_anchors_still_hold_the_values_the_paper_cites() -> None:
    """出厂缺省与备份名册这两格是纸面判语的地基：值一翻，本钉当场红，不许静悄悄。"""
    assert module_value("app/rag/indexing.py", "INDEX_BACKEND_DEFAULT") == "chroma"
    assert module_value("app/rag/indexing.py", "INDEX_BACKEND_ENV") == "INDEX_BACKEND"
    assert module_value("app/rag/pg_store.py", "DUAL_WRITE_ENV") == "VECTOR_DUAL_WRITE"
    assert "chroma_db" in module_value("app/common/backup.py", "DEFAULT_BACKUP_DIRS")


def test_the_compose_anchor_still_mounts_the_legacy_directory() -> None:
    """S4 那格把命名卷交给键名派生锚：卷必须在，引用它的必须正是那三 service。"""
    assert yml_anchor_resolves("docker-compose.yml", "x-persistent-paths")
    assert yml_anchor_resolves("docker-compose.yml", "volumes")
    mounted = [re.sub(r"^-\s+", "", line) for line in
               yml_block("docker-compose.yml", "x-persistent-paths")]
    assert "vectordb:/app/chroma_db" in mounted, mounted
    assert "vectordb:" in yml_block("docker-compose.yml", "volumes")
    assert services_mounting("docker-compose.yml", "persistent-paths") == \
        ["backend", "scheduler", "worker"]


def test_the_owner_only_gates_behind_S4_are_named_by_gate_number() -> None:
    """human-gates 的三枚行号换成 H 号之后：H 号得真是「仅用户本人」那三格。"""
    row = row_starting_with("| S4 ")
    assert "业主本人" in row, "S4 那一格不再说这是业主本人的闸门：纸要改口"
    for token in ("H4", "H5", "H8"):
        assert "2026-09-17-human-gates.md::" + token in row, "S4 没挂 H%s" % token
        head = md_heading("docs/handoff/2026-09-17-human-gates.md", token)
        assert head is not None, "闸门账里找不到 H%s 这一枚标题" % token
        assert "仅用户本人" in head, "H%s 现在不是业主专属闸门了：纸要改口" % token


# ==================== 钉自己的卫生 ====================


def test_the_env_knob_the_paper_cites_is_named_by_key_not_by_line() -> None:
    """主树那枚 env 文件未跟踪、行位只在主树本机成立：纸面必须改口成键名。"""
    body = paper()
    for knob in ("INDEX_BACKEND", "VECTOR_DUAL_WRITE"):
        assert "`%s`" % knob in body, "退役纸没再点名 %s 这枚键" % knob
    assert forged("deploy/.env", ".server", ":", "7", "7") not in body
    assert forged("deploy/.env", ".server", ":", "5", "6") not in body


def test_this_nail_never_asks_the_working_tree_whether_it_is_dirty() -> None:
    """牙不许拿施工态当判据（事故 #96/#107/#113 同族病）：静态自证本件不走 git、不比 dirty。"""
    source = Path(__file__).resolve().read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "ast", "re", "pathlib"}, sorted(imported)
    strings = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
               and isinstance(node.value, str)]
    joined = " ".join(strings)
    # 把手名也拼出来：否则这枚自证会被自己那串字面量绊倒（本单实测撞过一次）。
    banned = ("por" + "celain", "status " + "--", "rev-" + "parse",
              "diff " + "--", "sub" + "process")
    for handle in banned:
        assert handle not in joined, "本件里出现了盘面态把手：" + handle
    assert PY_COORD.findall(source) == [] and OTHER_COORD.findall(source) == [], \
        "钉自己抄了坐标"


def test_the_r646_evidence_paper_copies_no_coordinate() -> None:
    """本单取证纸同样一枚坐标不许抄（R638 同口径）：它若开始抄行号，就是本钉漏放。"""
    papers = sorted((REPO / "docs" / "testing").glob("r646-*.md"))
    assert papers, "本单取证纸没落盘：docs/testing/r646-*.md 一枚都没有"
    for path in papers:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO).as_posix()
        assert py_coordinate_offenders(text) == [], rel
        assert other_coordinate_offenders(text) == [], rel
