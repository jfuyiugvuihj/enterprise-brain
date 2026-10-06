# -*- coding: utf-8 -*-
r"""R638 —— 文档手抄代码坐标的尺：现取枚数、现判漂移、现出「能不能换成 ::符号」。

这单的病（派工词 R638）：``docs/**/*.md`` 里抄着 ``某文件.py:行号`` 的坐标，而产品码天天在动。
今天并树的跑分量具一笔 +566 行，在册引用里那一类坐标逐枚被打断；本席按宽形状（任意
``.py:行号``，含行区间）在 docs 现取 **4,102 枚／123 枚 .md**。今天最贵的不是「有一堆漂了的行号」，
是**没有一把尺挡得住新的一枚继续长进纸里**，而且没人知道哪些是真漂、哪些只是引用形式。

所以本件只交尺与清单，**不改任何正文**（正文批量转换按写集切给后面几枚单，切法见 ``--batches``）。

三件判定（逐枚）：
  ① 被引文件在不在：全路径 → 仓内后缀 → 基名三级解析；基名撞车记歧义并交回候选，不猜。
     ``.venv`` 依赖里的同名文件单列 ``external`` 档——那是引用第三方，不是本仓漂移。
  ② 该行当前内容与句子声称对不对得上：走 **AST**（不 import：``app/api/v1/chat.py`` 一 import
     就发 Postgres 探针并把被跟踪的 ``chroma_db/chroma.sqlite3`` 写脏，今天两枚执行层都踩过）。
     同一枚 md 行里点名、且在被引文件源码里真有其名的符号，必须落进该行的所属符号区间；
     落不进＝对不上。句子里挑不出可核对的符号时**不判漂移**，如实记 ``unverified``。
  ③ 该枚能否安全换成 ``文件::符号``：解析唯一 ＋ 该行（区间则逐行）有具名所属。判红的枚
     另给「按句子声称的符号」那一枚锚点建议，但机械锚与语义锚分两栏，不许混着吹。

身份口径（R638-R①）：棘轮记的是 ``doc::整行文本哈希::被引坐标串``，**与行位无关**——本仓的账面
纪律就是「看板名册行 splice＋跟进单文末追加」，任何一次正常记账都会移动行位；拿行位当身份，
每写一次账面就全仓变红（实测 ``473235f``→``7fd8d4a`` 看板只净增 25 行，431 枚坐标被报成新增）。
带行号的身份串只留给抽查清单（``--stale`` 那一格），绝不当棘轮的账。

行号口径：枚数与行号一律按 ``\n`` 切行、行尾 ``\r`` 剥掉。这是被现网逼出来的——跟进单那枚 .md
盘上有 1,534 枚孤立 ``\r``，用 Python 通用换行读会把行号整体错位，与总控 ``rg -n`` 的号对不上，
抽查时就成了假凭据。``sha`` 那一格只归一 ``\r\n``→``\n``（孤立 ``\r`` 属内容，不归一），
所以基线不随 ``core.autocrlf`` 的检出姿势漂。

零 IO：只读盘上文本，不 import 产品码、不起服务、不连库、不打模型、不动容器。
唯一写口是 ``--out``／``--write-baseline``（都只写给定路径），本件不碰任何 .md 正文。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import itertools
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable

REPO = Path(__file__).resolve().parents[1]
DOCS_DEFAULT = "docs"

#: 派工词判据① 那把宽尺的形状原文（总控命令：rg -o -N --glob "docs/**/*.md" 这一枚）。
TICKET_SHAPE = r"[A-Za-z0-9_./-]+\.py:[0-9]+(-[0-9]+)?"
#: 本件的实现：同一形状，区间段收进非捕获组，逐枚语义不变。
COORD = re.compile(r"[A-Za-z0-9_./-]+\.py:[0-9]+(?:-[0-9]+)?")
_COORD_PIECES = re.compile(r"^(?P<file>[A-Za-z0-9_./-]+\.py):(?P<start>[0-9]+)(?:-(?P<end>[0-9]+))?$")

#: 不进 .py 名册的目录（依赖／产物／被跟踪数据）。
PRUNED_DIRS = {
    ".git", ".venv", ".idea", ".vite", ".firecrawl", "venv", "node_modules",
    "__pycache__", "dist", "build", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "chroma_db",
}

#: 声称形状的把手：反引号里的符号／def X／class X／X( ／X ＝。
_BACKTICK = re.compile(r"`([^`\n]+)`")
_DEF_OR_CLASS = re.compile(r"\b(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
_CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
#: 从这些串里挑符号没意义（文件名、语言、HTTP 词、markdown 表格把手）。
_STOPWORDS = {
    "py", "md", "json", "sql", "txt", "yaml", "yml", "http", "https", "api", "v1",
    "git", "sha", "def", "class", "self", "true", "false", "none", "get", "post",
    "id", "ok", "todo", "rfc", "utf", "cli", "run", "test", "src", "app",
}

#: 「句子在讲引用形式本身」的形状：这一行的坐标是反例展示，不当漂移裁。
_SHAPE_TALK = re.compile(r"(形状|反例|示例|不许|禁止|口径|尺|regex|正则|rg |-o -n)")


# ==================== 一、盘上文本：与总控那把 rg 同形地读 ====================


def decode_text(raw: bytes) -> tuple[str, dict]:
    """字节 → 文本，并如实记下读取姿势（BOM／有损解码），读数要能被别人复现。"""
    meta = {"bom": raw.startswith(b"\xef\xbb\xbf"), "lossy": False}
    body = raw[3:] if meta["bom"] else raw
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("utf-8", errors="replace")
        meta["lossy"] = True
    return text, meta


def doc_lines(text: str) -> list[str]:
    """按 ``\n`` 切行、剥行尾 ``\r``：枚数与行号以此为准。"""
    return [line[:-1] if line.endswith("\r") else line for line in text.split("\n")]


def content_digest(text: str) -> str:
    """归一 ``\r\n``→``\n`` 之后的 sha256 前 16 位：CRLF/LF 两种检出下同值，孤立 ``\r`` 保留为内容。"""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()[:16]

def line_digest(line_text: str) -> str:
    """整行文本的 sha256 前 16 位：折叠行内空白、剥两端——身份的地基，与这行排在第几行无关。

    折叠空白是刻意的：账面 splice 常常只动表格行前后的空格数（补一格竖线、多一个缩进），
    那不算多长出一枚坐标。真删掉或添上一枚坐标，行文本必然变，这一格照样抓得到。
    """
    return hashlib.sha256(" ".join(line_text.split()).encode("utf-8")).hexdigest()[:16]


#: 身份口径写进基线件：换了口径的旧基线当场被 validate_baseline 拒收，不留第二条真源。
IDENTITY_SCHEME = "doc::line-sha256/16::cited(#occurrence)"


@dataclass(frozen=True)
class Occurrence:
    """纸上的一枚坐标：它在哪枚 md 的第几行第几列、原文是什么、点名了哪枚文件的哪一段。"""

    doc: str            # 相对 docs 父目录的 posix 路径，形如 docs/handoff/x.md
    doc_line: int       # 1-based，按 \n 数
    column: int         # 0-based，行内偏移（同一行多枚坐标靠它区分）
    raw: str            # 原文，纸上原文：文件串＋冒号＋行号（可带行区间）
    file_part: str      # 被引文件串（照纸上的写法，可能是裸基名）
    start: int
    end: int | None     # None ＝ 单行；否则区间右端
    doc_line_text: str  # 所在 md 行全文：判「句子声称了什么」的唯一依据

    @property
    def cited_span(self) -> tuple[int, int]:
        return (self.start, self.start if self.end is None else self.end)

    @property
    def is_range(self) -> bool:
        return self.end is not None

    @property
    def where(self) -> str:
        """派工词判据②要的「所在md:行」。"""
        return "%s:%d" % (self.doc, self.doc_line)

    @property
    def key(self) -> str:
        """带行位的在册账号（``doc:行:列:原文``）：只给抽查清单用，绝不当身份。"""
        return "%s:%d:%d:%s" % (self.doc, self.doc_line, self.column, self.raw)

    @property
    def identity(self) -> str:
        """一枚坐标的身份（R638-R①）：``doc 相对路径::整行文本哈希::被引坐标串``。

        本仓的账面纪律本身就是「看板名册行 splice ＋跟进单文末追加」，任何一次正常记账都会
        移动行位——所以棘轮认这一串：上方插一行、整行搬到相邻行，它逐枚不变；而多长一枚坐标、
        删掉一枚坐标，它必然变。行位漂移曾把 670<671 报成 grew，那是假案，不是止血。
        """
        return "%s::%s::%s" % (self.doc, line_digest(self.doc_line_text), self.raw)


def scan_doc(doc_rel: str, path: Path) -> tuple[list[Occurrence], dict]:
    """扫一枚 .md：交回全部坐标与这枚文件的读数元数据。"""
    text, meta = decode_text(path.read_bytes())
    found: list[Occurrence] = []
    unparsed: list[str] = []
    for index, line in enumerate(doc_lines(text), start=1):
        for match in COORD.finditer(line):
            pieces = _COORD_PIECES.match(match.group(0))
            if pieces is None:      # 形状尺抓到却拆不开：绝不静默丢，单独记一笔
                unparsed.append("%s:%d:%s" % (doc_rel, index, match.group(0)))
                continue
            found.append(Occurrence(
                doc_rel, index, match.start(), match.group(0), pieces.group("file"),
                int(pieces.group("start")),
                int(pieces.group("end")) if pieces.group("end") else None, line,
            ))
    meta.update({
        "pointers": len(found),
        "ranges": sum(1 for occ in found if occ.is_range),
        "unparsed": unparsed,
        "crlf": text.count("\r\n"),
        "lone_cr": len(re.findall(r"\r(?!\n)", text)),
        "digest": content_digest(text),
        "lines": len(doc_lines(text)),
    })
    return found, meta


def scan_docs(docs_root: Path) -> tuple[list[Occurrence], dict[str, dict]]:
    """扫 ``docs_root`` 下全部 .md（跳过点目录）：与 ``rg --glob "docs/**/*.md"`` 同一集合。"""
    occurrences: list[Occurrence] = []
    per_doc: dict[str, dict] = {}
    for path in sorted(docs_root.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(docs_root).parts[:-1]):
            continue
        doc_rel = path.relative_to(docs_root.parent).as_posix()
        found, meta = scan_doc(doc_rel, path)
        occurrences.extend(found)
        per_doc[doc_rel] = meta
    return occurrences, per_doc

# ==================== 二、被引文件的解析（只认盘，零 import） ====================


def python_files(repo_root: Path) -> list[str]:
    """本仓的 .py 名册（仓根相对 posix 路径）。"""
    found = []
    for path in repo_root.rglob("*.py"):
        rel = path.relative_to(repo_root)
        if any(part in PRUNED_DIRS for part in rel.parts[:-1]):
            continue
        found.append(rel.as_posix())
    return sorted(found)


class PyIndex:
    """坐标串 → 盘上那枚 .py 的解析器，外加按 AST 派生的符号表（逐枚缓存，读盘一次）。"""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = Path(repo_root) if repo_root else REPO
        self.files = python_files(self.repo_root)
        self._by_file = set(self.files)
        self.by_base: dict[str, list[str]] = {}
        for rel in self.files:
            self.by_base.setdefault(PurePosixPath(rel).name, []).append(rel)
        self._site = self._site_packages()
        self._lines: dict[str, list[str]] = {}
        self._tables: dict[str, SymbolTable] = {}

    def _site_packages(self) -> list[Path]:
        """依赖的落点：先认**现跑这枚解释器**的 site-packages，再认仓里那枚 ``.venv``。

        为什么不能只认 ``repo/.venv``：干净检出的树里根本没有 ``.venv``（它不被跟踪）。第一版把
        依赖档绑在那枚目录上，于是同一份 docs 在脏树读成 8 枚 ``external_dependency``、在干净检出
        读成 8 枚 ``file_missing``——**两态差 8 枚**，正是「把此刻盘面当判据」的同族病（事故 #96／#107）。
        改绑解释器之后，同一枚 venv 跑两态，读数逐枚相等。
        """
        import sysconfig

        bases = [Path(sysconfig.get_paths()["purelib"])]
        for prefix in dict.fromkeys([sys.prefix, getattr(sys, "base_prefix", sys.prefix)]):
            bases += [Path(prefix) / "Lib" / "site-packages",
                      *sorted((Path(prefix) / "lib").glob("python*/site-packages"))]
        venv = self.repo_root / ".venv"
        if venv.is_dir():
            bases += [venv / "Lib" / "site-packages",
                      *sorted((venv / "lib").glob("python*/site-packages"))]
        return [base for base in dict.fromkeys(bases) if base.is_dir()]

    def is_third_party(self, file_part: str) -> bool:
        """坐标点名的是依赖里的文件（``chromadb/api/types.py`` 那一族）：引用第三方，不是本仓漂移。"""
        return any((base / file_part).is_file() for base in self._site)

    def resolve(self, file_part: str) -> tuple[str, list[str]]:
        """三级解析（全路径 → 仓内后缀 → 基名），交回 ``(档位, 候选)``。

        档位 ∈ exact／suffix／unique／ambiguous／external／moved／missing。基名撞车就如实报歧义并交回候选：
        猜一枚出来判漂移，裁的就是假话。抄的整路径已不在盘上而同名文件还在别处，记 ``moved``——
        那是漂移的硬凭据，不是"找不到"。
        """
        part = file_part.replace("\\", "/").removeprefix("./")
        if part in self._by_file:
            return "exact", [part]
        if "/" in part:
            suffix = [rel for rel in self.files if rel.endswith("/" + part)]
            if len(suffix) == 1:
                return "suffix", suffix
            if suffix:
                return "ambiguous", suffix
            if self.is_third_party(part):
                return "external", [part]
            same_base = [rel for rel in self.files
                         if PurePosixPath(rel).name == PurePosixPath(part).name]
            if len(same_base) == 1:
                return "moved", same_base
            if same_base:
                return "moved_ambiguous", same_base
            return "missing", []
        base = self.by_base.get(part, [])
        if len(base) == 1:
            return "unique", base
        if len(base) > 1:
            return "ambiguous", base
        return "missing", []

    def lines(self, rel: str) -> list[str]:
        if rel not in self._lines:
            text, _meta = decode_text((self.repo_root / rel).read_bytes())
            self._lines[rel] = text.split("\n")
        return self._lines[rel]

    def table(self, rel: str) -> SymbolTable:
        """被引文件的 AST 符号表：解析失败的文件也如实进表（``parsed=False``）。"""
        if rel not in self._tables:
            text, _meta = decode_text((self.repo_root / rel).read_bytes())
            self._tables[rel] = SymbolTable.of(rel, text)
        return self._tables[rel]

# ==================== 三、AST 符号表：某一行现在属于谁 ====================

#: 一行现在挂着什么：``(点号链, 种类)``；种类 ∈ def／async def／class／variable／None（无名语句）。
_ANCHORABLE_KINDS = ("def", "async def", "class", "variable")


def _target_names(node: ast.stmt) -> list[str]:
    """赋值语句左边那几个名字（``X = ...``／``X: T = ...``）；解包与属性赋值不算具名符号。"""
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


class SymbolTable:
    """一枚 .py 的现读符号表（AST 派生，零 import）：行→所属符号、名→区间、锚点链→区间。"""

    def __init__(self, rel: str, entries: list[dict], parsed: bool, error: str = "") -> None:
        self.rel = rel
        self.entries = entries                      # 每枚具名定义／命名赋值：lo／hi／chain／kind
        self.parsed = parsed
        self.error = error
        self.spans_by_chain: dict[str, list[tuple[int, int]]] = {}
        self.spans_by_name: dict[str, list[tuple[int, int]]] = {}
        for entry in entries:
            self.spans_by_chain.setdefault(entry["chain"], []).append((entry["lo"], entry["hi"]))
            self.spans_by_name.setdefault(entry["chain"].split(".")[-1], []).append(
                (entry["lo"], entry["hi"])
            )

    @classmethod
    def of(cls, rel: str, text: str) -> "SymbolTable":
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            return cls(rel, [], parsed=False, error="SyntaxError@line %s" % exc.lineno)
        entries: list[dict] = []

        def span(node: ast.AST) -> tuple[int, int]:
            lo = node.lineno
            for deco in getattr(node, "decorator_list", []) or []:
                lo = min(lo, deco.lineno)
            return lo, (getattr(node, "end_lineno", None) or node.lineno)

        def walk(node: ast.AST, chain: tuple[str, ...], in_class: bool) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    kind = ("async def" if isinstance(child, ast.AsyncFunctionDef)
                            else "class" if isinstance(child, ast.ClassDef) else "def")
                    lo, hi = span(child)
                    full = chain + (child.name,)
                    entries.append({"lo": lo, "hi": hi, "chain": ".".join(full), "kind": kind})
                    walk(child, full, isinstance(child, ast.ClassDef))
                elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                    if in_class or not chain:       # 局部变量不可锚，只记模块级与类级命名
                        lo, hi = span(child)
                        for name in _target_names(child):
                            entries.append({
                                "lo": lo, "hi": hi,
                                "chain": ".".join(chain + (name,)), "kind": "variable",
                            })
                    walk(child, chain, in_class)
                else:
                    walk(child, chain, in_class)

        walk(tree, (), False)
        return cls(rel, entries, parsed=True)

    # ---------- 查询 ----------

    @property
    def names(self) -> set[str]:
        """这枚文件里真有其名的末段符号（句子里的声称只有撞上它，才谈得上「对不对得上」）。"""
        return set(self.spans_by_name)

    def spans_of(self, name: str) -> list[tuple[int, int]]:
        return self.spans_by_name.get(name.split(".")[-1], [])

    def owner_at(self, line: int) -> tuple[str, str | None]:
        """该行的所属：取包住它的最小具名定义；没有定义包住时退到该行所在的命名赋值，再退到空串。"""
        best = None
        for entry in self.entries:
            if entry["kind"] == "variable" or not entry["chain"]:
                continue
            if entry["lo"] <= line <= entry["hi"]:
                if best is None or (entry["hi"] - entry["lo"]) < (best["hi"] - best["lo"]):
                    best = entry
        if best is not None:
            return best["chain"], best["kind"]
        for entry in self.entries:
            if entry["kind"] == "variable" and entry["lo"] <= line <= entry["hi"]:
                return entry["chain"], "variable"
        return "", None
# ==================== 四、逐枚判定：在不在／对不对得上／能不能换成锚点 ====================

#: 硬判据（今天已对不上）：这五档逐枚进清单，每枚带现读凭据。
#: ``empty_target_line`` 也在其内——那一行现在一个字都没有，坐标指着的是空气，没有裁量余地。
HARD_VERDICTS = ("file_missing", "file_moved", "line_out_of_range", "symbol_mismatch",
                 "empty_target_line")
#: 不判漂移的几档：信息不足就是不足，既不拿它冒充凭据，也不拿它凑红。
SOFT_VERDICTS = ("ambiguous_path", "external_dependency", "unparsed_target",
                 "unverified_no_claim", "unverified_multi_pointer", "comment_target_line")


def claims_in(doc_line_text: str, known_names: set[str]) -> set[str]:
    """从所在 md 行里挑出「句子点名的符号」，只留被引文件现读真有其名的那些。

    先把纸上每一枚坐标整段抹成空格——不然 ``chat.py`` 会被读成一枚声称，尺子自己骗自己。
    """
    masked = COORD.sub(lambda m: " " * len(m.group(0)), doc_line_text)
    cands: set[str] = set()
    for inner in _BACKTICK.findall(masked):
        token = inner.strip()
        headed = _DEF_OR_CLASS.search(token)
        if headed:
            cands.add(headed.group(1))
            continue
        token = token.split("(")[0].split("=")[0].split(":")[0].strip().strip("`")
        if _IDENT.match(token):
            cands.add(token)
    for match in _DEF_OR_CLASS.finditer(masked):
        cands.add(match.group(1))
    for match in _CALL.finditer(masked):
        cands.add(match.group(1))
    kept = set()
    for cand in cands:
        last = cand.split(".")[-1]
        if last in known_names and last.lower() not in _STOPWORDS:
            kept.add(cand)
    return kept


def anchor_for(index: PyIndex, target: str, chain: str) -> tuple[str | None, str]:
    """把「该行现读所属」拼成一枚 ``文件::符号`` 锚点，并用同一棵 AST 走通它自己。

    走不通就不交锚点：交出一枚解析不到的锚点，等于把漂了的行号洗成看着体面的假锚点。
    解析腿与在册那把尺（``tests/test_r630_first_token_pointer_is_derived.py`` 的
    ``anchor_resolves``）同形——按点号链逐层下钻，符号必须真在源码里定义，零 import。
    """
    if not chain:
        return None, "该行现读属模块级无名语句，没有可锚的具名符号"
    table = index.table(target)
    if chain not in table.spans_by_chain:
        return None, "锚点 %s::%s 在源码里逐层走不通" % (target, chain)
    return "%s::%s" % (target, chain), ""


def classify(occ: Occurrence, index: PyIndex, siblings: int = 1, shared=()) -> dict:
    """一枚坐标的三件判定，交回可核对的读数（判据②要的现读凭据全在这一格）。

    ``siblings`` ＝同一枚 md 行里指向同一枚被引文件的坐标枚数；``shared`` ＝同一枚行里**别枚**
    坐标的目标文件也带着的那些符号名。两者都是归因闸：一行里数枚坐标各说各话时，
    「这句声称属于哪一枚」纸上说不清，宁可记 unverified，也不裁出一枚假漂移。
    """
    kind, candidates = index.resolve(occ.file_part)
    row = {
        "where": occ.where, "column": occ.column, "cited": occ.raw,
        "resolution": kind, "target": None, "is_range": occ.is_range,
        "owner_now": None, "owner_kind": None, "claims": [], "claim_spans": [],
        "verdict": None, "hard": False, "anchor": None, "anchor_note": "",
        "line_now": None, "shape_talk": bool(_SHAPE_TALK.search(occ.doc_line_text)),
        "doc_excerpt": occ.doc_line_text.strip()[:240],
    }

    if kind == "external":
        row["verdict"] = "external_dependency"
        row["anchor_note"] = "点名的是依赖里的文件，不属本仓行号账"
        return row
    if kind == "missing":
        row["verdict"], row["hard"] = "file_missing", True
        row["anchor_note"] = "被引文件不在盘上"
        return row
    if kind in ("moved", "moved_ambiguous"):
        row["verdict"], row["hard"], row["target"] = "file_moved", True, candidates
        row["anchor_note"] = "抄的那条路径不在盘上，同名文件现读在别处"
        return row
    if kind == "ambiguous":
        row["verdict"], row["target"] = "ambiguous_path", candidates
        row["anchor_note"] = "基名撞车，候选见 target"
        return row

    target = candidates[0]
    row["target"] = target
    lines = index.lines(target)
    lo, hi = occ.cited_span
    if hi > len(lines):
        row["verdict"], row["hard"] = "line_out_of_range", True
        row["line_now"] = "该文件现读共 %d 行" % len(lines)
        row["anchor_note"] = "抄的行号已在文件长度之外"
        return row

    table = index.table(target)
    if not table.parsed:
        row["verdict"] = "unparsed_target"
        row["anchor_note"] = "被引文件 AST 解析失败：%s" % table.error
        return row

    owner, owner_kind = table.owner_at(lo)
    row["owner_now"] = owner or "<module>"
    row["owner_kind"] = owner_kind
    row["line_now"] = lines[lo - 1].strip()[:160]

    claims = sorted(claims_in(occ.doc_line_text, table.names) - {str(name) for name in shared})
    row["claims"] = claims
    if siblings > 1 and claims:
        row["verdict"] = "unverified_multi_pointer"
        row["anchor_note"] = "同一枚 md 行里有数枚指向同一文件的坐标，声称归谁说不清，本件不裁"
    elif claims:
        row["claim_spans"] = [
            {"symbol": name, "spans": [list(span) for span in table.spans_of(name)]}
            for name in claims
        ]
        hit = any(span_lo <= hi and lo <= span_hi for name in claims
                  for span_lo, span_hi in table.spans_of(name))
        row["verdict"] = "claim_matches" if hit else "symbol_mismatch"
        if not hit:
            row["hard"] = True
            row["anchor_note"] = "句子点名的符号现读不在抄的那一段里"
    elif not lines[lo - 1].strip() and not any(
        str(lines[at - 1].strip()) for at in range(lo, hi + 1)
    ):
        # 单行引用空即空；区间引用只要整段全是空行才算空指，免得误伤「这段现在塌成空白了」那一形。
        row["verdict"], row["hard"] = "empty_target_line", True
        row["anchor_note"] = "该行现读是空行：坐标指着的地方一个字都没有"
    elif lines[lo - 1].strip().startswith("#"):
        row["verdict"] = "comment_target_line"
        row["anchor_note"] = "该行现读是注释：可能在指注释里写着的那件事，本件不裁"
    else:
        row["verdict"] = "unverified_no_claim"
        row["anchor_note"] = "句子里挑不出可在该文件核对的符号名，本件只量到行在界内"

    if not row["hard"]:
        chain = owner if owner_kind in _ANCHORABLE_KINDS else ""
        anchor, note = anchor_for(index, target, chain)
        row["anchor"] = anchor
        if anchor and row["verdict"] == "claim_matches":
            row["anchor_note"] = "该行现读所属 %s 与句子声称同枚，可直接换" % chain
        elif anchor:
            row["anchor_note"] = (row["anchor_note"] + "；可按行机械换成锚点").lstrip("；")
        elif note:
            row["anchor_note"] = note
    return row

# ==================== 五、派生读数、棘轮基线、批量转换的切法 ====================

#: 事故取证原文的形状：这一枚引用本身就是当时那句读数/那句假话的凭据，改它＝销毁证据。
_FORENSIC = re.compile(r"(事故\s*#|取证|当时的?假话|原文|逐字|作废|复现|现场读|现取|实测读数|症状)")

#: 只许文末追加的账本（跟进单与看板）：中间改字会破在册的 pure_append 钉。
LEDGER_PREFIX = "docs/handoff/"
#: 同一枚追加纪律下的契约（tests/test_r523_cached_count_lands.py::contract_is_pure_append 挡着）。
CONTRACT_DOC = "docs/api/contract-v1.md"
#: 整篇就是取证纸的命名形状（readout／verdict／caliber／debt／事故…）：批里带上旗标，交总控定夺。
_FORENSIC_PAPER = re.compile(
    r"(readout|reading|verdict|caliber|forensic|debt|incident|事故|取证|实测|窗口|recheck|closure)"
)


def is_ledger(doc: str) -> bool:
    return doc.startswith(LEDGER_PREFIX)


def batch_of(doc: str) -> str:
    """非账本文件按所在目录归批：同一枚 .md 只落一枚批，写集才不重叠。"""
    parent = PurePosixPath(doc).parent
    return doc if str(parent) == "." else parent.as_posix()


#: 同一棵树的名册与 AST 只读一次：影子刀连着跑数遍，不必每次重扫 906 枚 .py。
_INDEX_CACHE: dict[str, PyIndex] = {}


def index_for(repo_root: Path | None = None) -> PyIndex:
    key = str(Path(repo_root or REPO).resolve())
    if key not in _INDEX_CACHE:
        _INDEX_CACHE[key] = PyIndex(repo_root or REPO)
    return _INDEX_CACHE[key]


def analyze(docs_root: Path | None = None, repo_root: Path | None = None) -> dict:
    """跑完整把尺：逐枚判定 ＋ 派生读数（总枚数、分组枚数、对不上清单、锚点可换性）。"""
    docs_root = Path(docs_root) if docs_root else REPO / DOCS_DEFAULT
    index = index_for(repo_root)
    occurrences, meta = scan_docs(docs_root)

    siblings: dict[tuple[str, int, str], int] = {}
    for occ in occurrences:
        siblings[(occ.doc, occ.doc_line, occ.file_part)] = (
            siblings.get((occ.doc, occ.doc_line, occ.file_part), 0) + 1
        )

    # 归因第二道闸：同一枚 md 行里，别枚坐标的目标文件也带着的符号名，说不属于哪一枚，先摘出去。
    line_names: dict[tuple[str, int], dict[str, set[str]]] = {}
    for occ in occurrences:
        kind, candidates = index.resolve(occ.file_part)
        if not candidates or not isinstance(candidates[0], str):
            continue
        target = candidates[0]
        if kind in ("external", "ambiguous", "moved", "moved_ambiguous", "missing"):
            continue
        line_names.setdefault((occ.doc, occ.doc_line), {})[occ.key] = index.table(target).names

    rows: list[dict] = []
    for occ in occurrences:
        others = set()
        for key, names in line_names.get((occ.doc, occ.doc_line), {}).items():
            if key != occ.key:
                others |= names
        row = classify(occ, index, siblings[(occ.doc, occ.doc_line, occ.file_part)],
                       shared=others & claims_in(occ.doc_line_text, others))
        row["key"] = occ.key
        row["identity"] = occ.identity
        row["doc"] = occ.doc
        row["forensic"] = bool(_FORENSIC.search(occ.doc_line_text))
        rows.append(row)

    by_doc: dict[str, list[dict]] = {}
    by_target: dict[str, int] = {}
    verdicts: dict[str, int] = {}
    for row in rows:
        by_doc.setdefault(row["doc"], []).append(row)
        target = row["target"]
        key = target if isinstance(target, str) else (
            "|".join(target) if isinstance(target, list) else "unresolved:" + row["cited"]
        )
        by_target[key] = by_target.get(key, 0) + 1
        verdicts[row["verdict"]] = verdicts.get(row["verdict"], 0) + 1

    hard = [row for row in rows if row["hard"]]
    readings = {
        "shape": TICKET_SHAPE,
        "docs_root": docs_root.as_posix(),
        "repo_root": index.repo_root.as_posix(),
        "md_files_scanned": len(meta),
        "md_files_with_pointers": len(by_doc),
        "total_pointers": len(rows),
        "range_pointers": sum(1 for row in rows if row["is_range"]),
        "verdict_counts": dict(sorted(verdicts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "hard_total": len(hard),
        "hard_by_verdict": {
            name: sum(1 for row in hard if row["verdict"] == name)
            for name in sorted({row["verdict"] for row in hard})
        },
        "hard_on_forensic_lines": sum(1 for row in hard if row["forensic"]),
        "hard_shape_talk": sum(1 for row in hard if row["shape_talk"]),
        "anchor_safe": sum(1 for row in rows if row["anchor"]),
        "anchor_unverifiable": sum(1 for row in rows if not row["hard"] and not row["anchor"]),
        "per_doc": [
            {"doc": doc, "pointers": len(items),
             "hard": sum(1 for item in items if item["hard"]),
             "anchor_safe": sum(1 for item in items if item["anchor"]),
             "forensic": sum(1 for item in items if item["forensic"])}
            for doc, items in sorted(by_doc.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        ],
        "per_target": [
            {"target": target, "pointers": count}
            for target, count in sorted(by_target.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }
    return {"readings": readings, "rows": rows, "doc_meta": meta, "by_doc": by_doc}


def identity_ledger(rows: list[dict]) -> list[str]:
    """一枚 .md 的身份清单：同一身份重复出现时按出现序号后缀（``#2``／``#3``……），逐枚点得出名。"""
    seen: dict[str, int] = {}
    ledger: list[str] = []
    for row in rows:
        base = row["identity"]
        seen[base] = seen.get(base, 0) + 1
        ledger.append(base if seen[base] == 1 else "%s#%d" % (base, seen[base]))
    return sorted(ledger)


def build_baseline(analysis: dict) -> dict:
    """把现取读数写成棘轮基线：每枚 .md 记 digest／枚数／逐枚身份，枚数由清单长度派生。

    🔴 基线里没有一处手抄数字：``count`` 永远是 ``len(pointers)``，``pointers`` 永远是尺自己数的。
    🔴 身份与行位无关（R638-R①）：所以同一份基线在任何一枚 HEAD 上都能重生成而不破牙。
    """
    files = {}
    for doc, meta in sorted(analysis["doc_meta"].items()):
        if not meta["pointers"]:
            continue
        pointers = identity_ledger(analysis["by_doc"].get(doc, []))
        files[doc] = {"digest": meta["digest"], "count": len(pointers), "pointers": pointers}
    return {
        "shape": TICKET_SHAPE,
        "identity_scheme": IDENTITY_SCHEME,
        "generated_by": "scripts/r638_doc_pointer_ruler.py",
        "total_pointers": sum(entry["count"] for entry in files.values()),
        "files": files,
    }


def validate_baseline(baseline: dict) -> list[str]:
    """基线自己得先经得起一枚尺：枚数＝清单长度、digest 在场、形状与总枚数对得上。

    任何一条不满足都是「数被抄下来了」的形状——手改一列数字、少抄一枚身份、换个形状，当场红。
    """
    bad: list[str] = []
    if baseline.get("shape") != TICKET_SHAPE:
        bad.append("基线记的形状与尺现在这枚不等：%r" % baseline.get("shape"))
    if baseline.get("identity_scheme") != IDENTITY_SCHEME:
        bad.append("基线记的身份口径与尺现在这枚不等（行位口径的旧基线不收）：%r"
                   % baseline.get("identity_scheme"))
    files = baseline.get("files")
    if not isinstance(files, dict) or not files:
        return bad + ["基线里没有一枚 .md：这枚尺没量过任何东西"]
    for doc, entry in sorted(files.items()):
        pointers = entry.get("pointers")
        if not isinstance(pointers, list):
            bad.append("%s：没有逐枚身份清单，枚数无从派生" % doc)
            continue
        if entry.get("count") != len(pointers):
            bad.append("%s：count=%s 而清单实数 %s 枚（数被抄下来了）" % (doc, entry.get("count"), len(pointers)))
        digest = str(entry.get("digest") or "")
        if len(digest) != 16 or any(ch not in "0123456789abcdef" for ch in digest):
            bad.append("%s：正文 digest 不是一枚 sha256 前 16 位：%r" % (doc, digest))
        if not all(key.startswith(doc + "::") for key in pointers):
            bad.append("%s：清单里混进了别枚文件的身份串" % doc)
        position_bearing = [key for key in pointers
                            if not re.fullmatch(r"[0-9a-f]{16}", key.split("::")[1]
                                                if key.count("::") >= 2 else "")]
        if position_bearing:
            bad.append("%s：%d 枚身份串的第二段不是行文本哈希（行位口径复活了）：%s"
                       % (doc, len(position_bearing), position_bearing[:3]))
    total = sum(int(entry.get("count") or 0) for entry in files.values())
    if baseline.get("total_pointers") != total:
        bad.append("total_pointers=%s 而各枚文件实数之和 %d" % (baseline.get("total_pointers"), total))
    return bad


def _multiset_diff(before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
    """同一枚 doc 的身份多重集之差：多出来的逐枚点名，少掉的逐枚点名（R638-R②）。"""
    delta_up, delta_down = Counter(after) - Counter(before), Counter(before) - Counter(after)
    return (sorted(delta_up.elements()), sorted(delta_down.elements()))


def ratchet_diff(baseline: dict, live: dict) -> dict:
    """基线对现取，方向只由**同一枚 doc 的身份多重集**定（R638-R②）。

    · ``grew``：枚数变多＝红，逐枚点名新身份——棘轮的正门。
    · ``shrank``：枚数变少＝不红，逐枚点名少了谁；更新基线是 ``--write-baseline`` 的活。
      🔴 枚数下降绝不进 ``grew``（旧版把 670<671 报成 grew，是假案）。
    · ``shifted``：枚数不变而身份变了＝不红，只点名——那是账面 splice 改了句子而没添坐标。
    · ``new_docs``：盘上新落的 .md 带着坐标＝不红，只点名——别的单的正文不由本单定罪（病因三）。
    · ``forged``：digest 未动而清单与现读不等，或基线自证不过＝红——守「基线必须由尺派生」。
    """
    grew, shrank, shifted, forged, fresh = [], [], [], [], []
    for row in validate_baseline(baseline):
        forged.append({"doc": "<baseline>", "why": row})
    for doc, entry in sorted(live["files"].items()):
        stored = baseline["files"].get(doc)
        if stored is None:
            if entry["count"]:
                fresh.append({"doc": doc, "count": entry["count"],
                              "added": sorted(set(entry["pointers"]))})
            continue
        added, removed = _multiset_diff(stored["pointers"], entry["pointers"])
        cell = {"doc": doc, "before": stored["count"], "after": entry["count"]}
        if entry["count"] > stored["count"]:
            grew.append({**cell, "added": added, "removed": removed})
        elif entry["count"] < stored["count"]:
            shrank.append({**cell, "added": added, "removed": removed})
        elif added or removed:
            shifted.append({**cell, "added": added, "removed": removed})
        if stored.get("digest") == entry.get("digest") and sorted(stored["pointers"]) != sorted(entry["pointers"]):
            forged.append({"doc": doc, "why": "正文 digest 未变而清单变了：基线那几枚不是尺取的",
                           "stored": stored["count"], "live": entry["count"]})
    for doc, stored in sorted(baseline["files"].items()):
        if doc not in live["files"] and stored["count"]:
            shrank.append({"doc": doc, "before": stored["count"], "after": 0, "added": [],
                           "removed": sorted(stored["pointers"])})
    # 自证：只有两边的 count 都等于各自清单长度时，方向算术才成立；不等的那一形归 forged 管。
    for cell in itertools.chain(grew, shrank, shifted):
        live_cell = live["files"].get(cell["doc"]) or {"count": 0, "pointers": []}
        stored_cell = baseline["files"].get(cell["doc"]) or {"count": 0, "pointers": []}
        if (len(live_cell["pointers"]) == live_cell["count"]
                and len(stored_cell["pointers"]) == stored_cell["count"]):
            assert cell["after"] - cell["before"] == \
                len(cell.get("added", [])) - len(cell.get("removed", [])), cell
    return {"grew": grew, "shrank": shrank, "shifted": shifted, "forged": forged,
            "new_docs": fresh, "offenders": grew + forged}


def batch_plan(analysis: dict, max_pointers: int = 250) -> dict:
    """把待转换的 .md 按写集切批，并把三类**必须排除**的单列出来（落不落由总控按先例办）。"""
    excluded = {
        "ledger_append_only": {"docs": [], "pointers": 0, "reason":
            "跟进单与看板只许文末追加：中间改字会破在册的 pure_append 钉，"
            "作废声明走文末追加、不抹原文（先例：契约文末追加 R523/R558/R635）"},
        "contract_append_only": {"docs": [], "pointers": 0, "reason":
            "docs/api/contract-v1.md 同文末追加纪律（tests/test_r523_cached_count_lands.py 的 "
            "contract_is_pure_append 挡中间改字）"},
    }
    pool: dict[str, list[dict]] = {}
    forensic_rows: list[dict] = []
    for row in analysis["rows"]:
        doc = row["doc"]
        if doc == CONTRACT_DOC:
            bucket = excluded["contract_append_only"]
        elif is_ledger(doc):
            bucket = excluded["ledger_append_only"]
        else:
            bucket = None
        if bucket is not None:
            # 账本与契约整枚文件排除：它们那几枚取证行同样落在排除格里，不另列（改不了的文件，逐枚清单没意义）
            bucket["docs"].append(doc)
            bucket["pointers"] += 1
            continue
        if row["forensic"]:
            forensic_rows.append(row)   # 取证原文：逐枚排除，不落任何批
            continue
        pool.setdefault(batch_of(doc), []).append(row)

    batches: list[dict] = []
    for group in sorted(pool):
        rows = pool[group]
        docs: dict[str, list[dict]] = {}
        for row in rows:
            docs.setdefault(row["doc"], []).append(row)
        current: list[str] = []
        load = 0
        for doc, items in sorted(docs.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            if current and load + len(items) > max_pointers:
                batches.append(_pack(group, current, docs, len(batches) + 1))
                current, load = [], 0
            current.append(doc)
            load += len(items)
        if current:
            batches.append(_pack(group, current, docs, len(batches) + 1))

    for entry in excluded.values():
        entry["docs"] = sorted(set(entry["docs"]))
    return {
        "batches": batches,
        "excluded": excluded,
        "forensic_lines": [
            {"where": row["where"], "cited": row["cited"], "verdict": row["verdict"],
             "hard": row["hard"]}
            for row in forensic_rows
        ],
        "totals": {
            "convertible_pool": sum(len(v) for v in pool.values()),
            "excluded": sum(v["pointers"] for v in excluded.values()),
            "forensic_lines": len(forensic_rows),
            "batches": len(batches),
        },
    }


def _pack(group: str, docs: list[str], rows_by_doc: dict[str, list[dict]], number: int) -> dict:
    """一枚批的账面：枚数、所在目录、风险旗标（全部现取派生，不抄第二份）。"""
    items = [row for doc in docs for row in rows_by_doc[doc]]
    return {
        "batch": "R638-%02d-%s" % (number, PurePosixPath(group).name or group),
        "group": group,
        "docs": sorted(docs),
        "pointers": len(items),
        "hard": sum(1 for row in items if row["hard"]),
        "anchor_ready": sum(1 for row in items if row["anchor"]),
        "needs_human": sum(1 for row in items if not row["anchor"] and not row["hard"]),
        "forensic_lines": sum(1 for row in items if row["forensic"]),
        "largest_doc": max(sorted(docs), key=lambda doc: len(rows_by_doc[doc])) if docs else None,
        "risk": {
            "forensic_paper_docs": sorted(doc for doc in docs if _FORENSIC_PAPER.search(doc)),
            "hard_majority": bool(items)
            and sum(1 for row in items if row["hard"]) * 2 > len(items),
            "ledger_named_docs": sorted(doc for doc in docs if doc.endswith(("runbook.md", "-plan.md"))),
        },
    }

# ==================== 六、CLI ====================


def render_stale(rows: list[dict], limit: int = 0) -> str:
    """判据②的逐枚清单：所在md:行 ＋ 被引坐标 ＋ 现读所属符号（外加句子声称与该行现读）。"""
    hard = [row for row in rows if row["hard"]]
    out = ["今天已对不上：%d 枚" % len(hard)]
    for row in (hard[:limit] if limit else hard):
        target = row["target"] if isinstance(row["target"], str) else ",".join(row["target"] or [])
        out.append(
            "  %s | 抄的=%s | 现读文件=%s | 现读所属=%s(%s) | 句子声称=%s | 判由=%s"
            % (row["where"], row["cited"], target or "-", row["owner_now"] or "-",
               row["owner_kind"] or "-", ",".join(row["claims"]) or "-", row["verdict"])
        )
        out.append("      纸上句子：%s" % row["doc_excerpt"])
        if row["line_now"]:
            out.append("      该行现读：%s" % row["line_now"])
        if row["claim_spans"]:
            out.append("      声称符号现读区间：%s" % row["claim_spans"])
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--docs-root", default=None, help="默认 <仓根>/docs；影子根可指到别处")
    parser.add_argument("--repo-root", default=None, help=".py 名册的仓根（默认本件所在树）")
    parser.add_argument("--max-per-batch", type=int, default=250, help="批量转换每批枚数上限")
    parser.add_argument("--out", default=None, metavar="PATH",
                        help="把整册派生读数落成机器件：readings ＋ batches ＋ 逐枚判定")
    parser.add_argument("--stale", action="store_true", help="打印今天已对不上的逐枚清单")
    parser.add_argument("--limit", type=int, default=0, help="配合 --stale 只印前 N 枚")
    parser.add_argument("--batches", action="store_true", help="打印批量转换的派工切法")
    parser.add_argument("--baseline", action="store_true", help="打印棘轮基线（JSON）")
    parser.add_argument("--check-baseline", default=None, metavar="PATH",  # 红只由 grew＋forged 决定
                        help="把现取读数与盘上基线对账；有变多或手抄即 exit=1")
    parser.add_argument("--write-baseline", default=None, metavar="PATH",
                        help="唯一写口：把现取读数落成基线件")
    args = parser.parse_args(argv)

    docs_root = Path(args.docs_root) if args.docs_root else REPO / DOCS_DEFAULT
    analysis = analyze(docs_root, Path(args.repo_root) if args.repo_root else REPO)

    if args.baseline or args.write_baseline or args.check_baseline:
        baseline = build_baseline(analysis)
    if args.write_baseline:
        target = Path(args.write_baseline)
        target.write_text(json.dumps(baseline, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                          encoding="utf-8", newline="\n")
        print("written:", target.as_posix(), "files=%d" % len(baseline["files"]),
              "total=%d" % baseline["total_pointers"])
        return 0
    if args.check_baseline:
        stored = json.loads(Path(args.check_baseline).read_text(encoding="utf-8"))
        diff = ratchet_diff(stored, baseline)
        print(json.dumps(diff, ensure_ascii=False, indent=1, sort_keys=True))
        return 1 if diff["offenders"] else 0
    if args.baseline:
        print(json.dumps(baseline, ensure_ascii=False, sort_keys=True))
        return 0
    if args.out:
        dump = {
            "readings": analysis["readings"],
            "batches": batch_plan(analysis, args.max_per_batch),
            "rows": analysis["rows"],
            "doc_meta": analysis["doc_meta"],
        }
        Path(args.out).write_text(json.dumps(dump, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                  encoding="utf-8", newline="\n")
        print("written:", Path(args.out).as_posix(), "pointers=%d" % analysis["readings"]["total_pointers"])
        return 0
    if args.batches:
        print(json.dumps(batch_plan(analysis, args.max_per_batch), ensure_ascii=False, indent=1,
                         sort_keys=True))
        return 0
    if args.stale:
        print(render_stale(analysis["rows"], args.limit))
        return 0
    print(json.dumps(analysis["readings"], ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
