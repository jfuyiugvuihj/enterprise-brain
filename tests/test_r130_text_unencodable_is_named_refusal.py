r"""R130：pypdf 抽出的一处 \x00 —— loader 出口净化 + pgvector 镜像具名早拒。

判据全文在 docs/handoff/2026-09-15-backend-followup-requests.md §65 二。本文件全程离线：
不连真实 PostgreSQL、不起容器、不打模型，所有 PG 语句都落在 FakeConnection 上。

四枚钉子
① 真件 documents/AI-Agent学习路线图.pdf 抽出确有 1 枚 NUL，且在字符串内部——那一句
   `.strip()` 结构上够不着它；load_pdf 之后没有，且净化结果 == 原抽出逐字 replace(NUL)，
   字符总数差 == NUL 枚数。同一把尺钉在每一个 load_* 出口上（含分派那一处）。
② VectorMirror 在开 cursor 之前按新立的具名码 vector_mirror_text_unencodable 拒写，消息
   带 filename 与 chunk_index，vector_mirror_diagnostics()["last_failure"] 读到同一枚。
③ 含 NUL 的分块走 VectorMirror.add 拿到的是②的具名拒绝，桩 driver 会像真 psycopg 那样对
   参数里的 NUL 抛 DataError——所以「早」是可证的；反向那条把「没有闸门时退化成
   vector_mirror_write_failed（只剩异常类名）」的形状也钉住了。真件走 loader → add 端到端
   一枚能落库，摘掉①的净化这条当场红。
④ 存量扫描走仓库自己这份语料（git ls-files documents，与 test_r49 同口径）：过完结子一枚
   NUL 都不剩，被摘掉的字符全仓合计 1 枚 ⇒ 对不含 NUL 的存量分块这把尺是恒等，本单一个字
   都不改写；将来非 0 时用例指名文档，不自动清洗。

反证三把（判据⑤，执行层已自己跑过，结果在交工回执里）：
(a) 摘掉 load_pdf 的净化 → ① 与③的端到端当场红；
(b) 摘掉 build_rows 的具名早拒 → ② 红，退回「原因被吞成异常类名」那种形状；
(c) 改成「镜像层 strip 后照写」→ ② 与「整批零写入」两条当场红。
"""
from __future__ import annotations

import contextlib
import inspect
import io
import logging
import subprocess
from pathlib import Path

import psycopg
import pytest

from app.rag import indexing, loader, pg_store, retriever


REPO_ROOT = Path(__file__).resolve().parents[1]
NUL_FILE = REPO_ROOT / "documents" / "AI-Agent学习路线图.pdf"

#: 本单唯一的主角，以及判据② 要的具名码——码写成字面量，实现里改名当场红。
NUL = "\x00"
REASON_TEXT_UNENCODABLE = "vector_mirror_text_unencodable"

#: 具名拒绝的消息里印的是「\x00」这四个字符，不是 NUL 本身；用 chr(92) 拼，免得源码里
#: 出现一枚真的控制字符。
NUL_TEXT = chr(92) + "x00"

#: 真机上 psycopg 抛回来的那一句话，逐字抄在这里当桩 driver 的台词。
DRIVER_MESSAGE = "PostgreSQL text fields cannot contain NUL (0x00) bytes"

#: 与真实 768 无关：镜像这条腿只认库口径（tests/test_r58_pgvector_dual_write.py 同一手法）。
DIM = 8
MODEL = "nomic-embed-r130"
VECTOR = [0.25] * DIM
DIRTY_CHUNK = "第一段" + NUL + "第二段"
CLEAN_CHUNK = "第一段\n\n第二段 🚀  MIXED case  "


def _meta(index: int, filename: str = "r130.txt") -> dict:
    return {
        "filename": filename,
        "chunk_index": index,
        "classification": 1,
        "department": "研发部",
        "hash": "0a1b2c3d4e5f",
    }


# ------------------------------------------------------------------ 只读工具


@contextlib.contextmanager
def _quiet_parser_warnings():
    """pypdf 解析这份真件会为上千条坏 CMap 行刷屏（§65 二：与本单无关，别去修它）。"""
    pypdf_logger = logging.getLogger("pypdf")
    previous = pypdf_logger.level
    pypdf_logger.setLevel(logging.ERROR)
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            yield
    finally:
        pypdf_logger.setLevel(previous)


def _raw_pdf_extraction(path: Path) -> str:
    """把改动之前的 load_pdf 逐字重做一遍（pypdf + 同样的 strip / join）。

    判据① 要拿「原抽出」作对照，所以这里刻意不借 loader 的任何 helper：两份实现只差一把
    尺子，差值才只可能来自 NUL，不可能来自第二个实现。
    """
    from pypdf import PdfReader

    with _quiet_parser_warnings():
        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                parts.append(page_text.strip())
        return "\n\n".join(parts).strip()


def _corpus_files() -> list[Path]:
    """版本化语料清单，不是 documents/ 的目录列表——理由见 test_r49 的同名函数。"""
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--", "documents"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        check=False,
    )
    assert listing.returncode == 0, f"git ls-files 未能列出语料：{listing.stderr!r}"
    names = sorted(item.decode("utf-8") for item in listing.stdout.split(b"\0") if item)
    files = [REPO_ROOT / name for name in names]
    assert files, "版本化语料清单为空，这个扫描没有意义"
    return files


def _load_one(path: Path, *, sanitized: bool) -> str:
    """同一份 load_document，只把尺子临时换成恒等，就得到「净化前」那份正文。"""
    original = loader.sanitize_text
    if not sanitized:
        loader.sanitize_text = lambda text: text
    try:
        return loader.load_document(str(path))
    finally:
        loader.sanitize_text = original


def _load_corpus():
    raw: dict[str, str] = {}
    clean: dict[str, str] = {}
    with _quiet_parser_warnings():
        for path in _corpus_files():
            try:
                unsanitized = _load_one(path, sanitized=False)
            except ValueError:
                # documents/ 兼作上传落地区，非文档扩展名会顶回 ValueError；test_r49 取
                # 同一份 git 清单也是这个口径。跳过不是放宽断言，下面的条数钉子会接住。
                continue
            raw[path.name] = unsanitized
            clean[path.name] = _load_one(path, sanitized=True)
    assert len(raw) >= 90, f"语料只读到 {len(raw)} 篇，这个扫描没有意义"
    return raw, clean


@pytest.fixture(scope="module")
def corpus():
    return _load_corpus()


# ------------------------------------------------------ 判据①：只删该删的那一枚


def test_sanitizer_drops_nul_and_only_nul():
    original = (
        "  第一段\t带 emoji 🚀 与 MIXED case\r\n\n\n"
        "第三行\x00带两枚 NUL\x00\n"
        "\u3000全角空格 stays\u0007 bell stays\n"
    )
    cleaned = loader.sanitize_text(original)

    assert cleaned == original.replace(NUL, "")
    assert NUL not in cleaned
    # 差值只可能是 NUL 的枚数，别的一概不动
    assert len(original) - len(cleaned) == original.count(NUL) == 2
    assert cleaned.startswith("  第一段\t")  # 首尾空白、制表符原样
    assert cleaned.endswith("bell stays\n")
    assert "\r\n\n\n" in cleaned  # 换行没被折叠
    assert "🚀" in cleaned and "MIXED case" in cleaned  # emoji 与大小写没被顺手处理
    assert "\u0007" in cleaned and "\u3000" in cleaned  # 别的控制字符不归本单管
    # 干净的文本过这把尺是恒等：判据④「存量无从被改写」说的就是这个
    assert loader.sanitize_text(CLEAN_CHUNK) == CLEAN_CHUNK
    assert loader.sanitize_text("") == ""


def test_real_pdf_really_carries_one_internal_nul():
    """先钉「这个用例不是空跑」：净化之前，真件抽出确有 1 枚 NUL，而且在字符串内部。"""
    assert NUL_FILE.is_file(), f"缺少 git 已跟踪的真件：{NUL_FILE}"
    raw = _raw_pdf_extraction(NUL_FILE)

    assert raw.count(NUL) == 1, "§65 二实测半径：全仓只有这一枚文档、恰好 1 个 NUL"
    position = raw.index(NUL)
    # 位置在中间，:17 那个 .strip() 结构上就够不着它——这正是缺陷的成因
    assert 0 < position < len(raw) - 1
    assert raw.strip() == raw


def test_real_pdf_exit_equals_the_raw_extraction_minus_the_nul():
    """判据①：净化结果与原抽出「逐字 replace(NUL)」相等，字符总数差 == NUL 枚数。"""
    raw = _raw_pdf_extraction(NUL_FILE)
    with _quiet_parser_warnings():
        cleaned = loader.load_pdf(str(NUL_FILE))

    assert cleaned == raw.replace(NUL, "")
    assert NUL not in cleaned
    assert len(raw) - len(cleaned) == raw.count(NUL) == 1
    # 只少了一枚字符，别的东西一处没动：换行数、空格数、NUL 后面那行原文
    assert cleaned.count("\n") == raw.count("\n")
    assert cleaned.count(" ") == raw.count(" ")
    assert "核心概念速查" in cleaned


# ------------------------------------------- 判据①「同一把尺」：每个 load_* 出口


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self):
        return self._text


class _FakePdfReader:
    """只替掉 pypdf 的抽出这一层，strip / join / 净化仍走 load_pdf 的真实实现。"""

    def __init__(self, pages):
        self._pages = list(pages)

    @property
    def pages(self):
        return self._pages


class _FakeParagraph:
    def __init__(self, text: str):
        self.text = text


class _FakeDocxDocument:
    def __init__(self, paragraphs):
        self.paragraphs = list(paragraphs)


class _FakeOleStream:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload


class _FakeOleFile:
    def __init__(self, payload: bytes):
        self._payload = payload
        self.closed = 0

    def exists(self, name):
        return name == "WordDocument"

    def openstream(self, name):
        return _FakeOleStream(self._payload)

    def close(self):
        self.closed += 1


def test_pdf_exit_drops_only_the_nul(monkeypatch):
    monkeypatch.setattr(
        loader,
        "PdfReader",
        lambda path: _FakePdfReader(
            [_FakePage("第一段\x00继续"), _FakePage("   "), _FakePage("第二段 🚀\n")]
        ),
    )

    assert loader.load_pdf("demo.pdf") == "第一段继续\n\n第二段 🚀"


def test_docx_exit_uses_the_same_ruler(monkeypatch):
    import docx as docx_module

    paragraphs = [_FakeParagraph("第一段\x00继续"), _FakeParagraph("  \n "), _FakeParagraph("第二段")]
    monkeypatch.setattr(docx_module, "Document", lambda path: _FakeDocxDocument(paragraphs))

    assert loader.load_docx("demo.docx") == "第一段继续\n第二段"


def test_doc_exit_uses_the_same_ruler(monkeypatch):
    import olefile

    # .doc 的字节筛子（31 < b < 127）本来就漏掉 NUL，出口这把尺是第二层：两层的口径
    # 必须一致，否则今天这条路径「碰巧干净」而明天换个筛子就漏。
    payload = b"line one\x00still one\nline two\n"
    monkeypatch.setattr(olefile, "OleFileIO", lambda path: _FakeOleFile(payload))

    text = loader.load_doc("demo.doc")
    assert text == "line onestill one\nline two"
    assert NUL not in text


def test_txt_md_and_dispatch_exits_use_the_same_ruler(tmp_path):
    body = "第一行\x00尾巴\n\n  缩进与 emoji 🚀 保持\n"
    expected = body.replace(NUL, "")
    for name in ("note.txt", "note.md"):
        document = tmp_path / name
        document.write_bytes(body.encode("utf-8"))
        assert body.encode("utf-8") == document.read_bytes()

        direct = loader.load_txt if name.endswith(".txt") else loader.load_md
        assert direct(str(document)) == expected
        assert loader.load_document(str(document)) == expected


def test_dispatch_exit_has_its_own_ruler(monkeypatch):
    """load_document 自己也要过尺：判据① 说「别只补一处」，包括分派这一处。"""
    monkeypatch.setattr(loader, "load_pdf", lambda path: DIRTY_CHUNK)
    monkeypatch.setattr(loader, "load_docx", lambda path: DIRTY_CHUNK)
    monkeypatch.setattr(loader, "load_doc", lambda path: DIRTY_CHUNK)
    monkeypatch.setattr(loader, "load_txt", lambda path: DIRTY_CHUNK)
    monkeypatch.setattr(loader, "load_md", lambda path: DIRTY_CHUNK)

    for extension in (".pdf", ".docx", ".doc", ".txt", ".md"):
        assert loader.load_document("demo" + extension) == "第一段第二段"


def test_every_loader_exit_calls_the_same_ruler():
    missing = [
        name
        for name in ("load_pdf", "load_docx", "load_doc", "load_txt", "load_md", "load_document")
        if "sanitize_text(" not in inspect.getsource(getattr(loader, name))
    ]

    assert missing == [], f"这些出口没过同一把尺：{missing}"


def test_loader_and_mirror_agree_on_the_one_character():
    assert loader.NUL_CHARACTER == pg_store.NUL_CHARACTER == NUL


# --------------------------------- 判据②/③：镜像在开 cursor 之前的具名早拒（离线）


class FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [] if self._row is None else [self._row]


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def executemany(self, sql, rows):
        for row in rows:
            self.connection.record(sql, tuple(row))


class FakeConnection:
    """假 psycopg 连接：像真 driver 一样，参数里出现 NUL 就抛 DataError。

    桩子只替数据库，不替闸门：cursors_opened / statements 让「早拒到底早不早」变成可读数。
    """

    def __init__(self, *, scope_row, column_type):
        self.scope_row = scope_row
        self.column_type = column_type
        self.statements: list = []
        self.cursors_opened = 0
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def record(self, sql, params=None):
        for value in self._values(params):
            if isinstance(value, str) and NUL in value:
                raise psycopg.DataError(DRIVER_MESSAGE)
        self.statements.append((sql, params))

    @staticmethod
    def _values(params):
        if params is None:
            return ()
        if isinstance(params, (str, bytes)):
            return (params,)
        try:
            return tuple(params)
        except TypeError:
            return (params,)

    def execute(self, sql, params=None):
        self.record(sql, params)
        if "FROM vector_scope" in sql:
            return FakeResult(self.scope_row)
        if "pg_attribute" in sql:
            return FakeResult({"format_type": self.column_type})
        if "count(*)" in sql:
            return FakeResult({"count": len(self.statements)})
        return FakeResult(None)

    def cursor(self):
        self.cursors_opened += 1
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1


def _connection() -> FakeConnection:
    return FakeConnection(scope_row=(MODEL, DIM, "cosine"), column_type=f"vector({DIM})")


def _mirror_env(monkeypatch, connection):
    """口径三件套 + 双写开关 + 把建连接换成假连接，其余逻辑一律走真实实现。"""
    monkeypatch.setenv(indexing.EMBEDDING_DIMENSION_ENV, str(DIM))
    monkeypatch.setenv(indexing.EMBEDDING_MODEL_ENV, MODEL)
    monkeypatch.setattr(retriever, "EMBEDDING_DIM", DIM)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    monkeypatch.setattr(pg_store, "_connect", lambda url, connection_factory: connection)
    pg_store.reset_vector_mirror_diagnostics()


def test_the_new_reason_code_is_named_and_distinct():
    assert pg_store.REASON_VECTOR_MIRROR_TEXT_UNENCODABLE == REASON_TEXT_UNENCODABLE

    existing = {
        value for name, value in vars(retriever).items() if name.startswith("REASON_")
    }
    # 不复用 vector_mirror_write_failed：那道门一开就整单失败，运维要的正是「哪一篇、哪一块」
    assert REASON_TEXT_UNENCODABLE not in existing


def test_the_column_names_the_gate_reports_match_the_upsert_statement():
    statement = pg_store._UPSERT_VECTOR_SQL
    columns = statement.split("(", 1)[1].split(")", 1)[0]
    names = tuple(part.strip() for part in columns.split(","))

    assert names == tuple(pg_store._UPSERT_COLUMNS)
    assert statement.count("%s") == len(names)


def test_mirror_refuses_a_nul_document_by_name_before_the_cursor(monkeypatch):
    connection = _connection()
    _mirror_env(monkeypatch, connection)
    mirror = pg_store.vector_mirror()
    documents = [DIRTY_CHUNK]

    with pytest.raises(retriever.VectorWriteRejectedError) as refused:
        mirror.add(
            ids=["r130.txt_3"],
            documents=documents,
            metadatas=[_meta(3)],
            embeddings=[VECTOR],
        )

    assert refused.value.reason == REASON_TEXT_UNENCODABLE
    message = str(refused.value)
    # 可定位信息：哪一篇、第几块、哪一列、几枚、首个偏移
    assert "filename=r130.txt" in message
    assert "chunk_index=3" in message
    assert "content" in message and NUL_TEXT in message

    assert connection.cursors_opened == 0, "早拒必须在开 cursor 之前"
    assert not any("INSERT INTO chunk_vectors" in sql for sql, _ in connection.statements)
    assert connection.commits == 0
    assert mirror.written == 0
    # 镜像不代清洗：调用方手里那份脏文本一个字都不许被改掉
    assert documents == [DIRTY_CHUNK]

    diagnostics = pg_store.vector_mirror_diagnostics()
    assert diagnostics["last_failure"]["reason"] == REASON_TEXT_UNENCODABLE
    assert "filename=r130.txt" in diagnostics["last_failure"]["detail"]
    assert diagnostics["rejected_writes"] == 1
    assert diagnostics["mirrored_writes"] == 0


def test_one_dirty_chunk_refuses_the_whole_batch(monkeypatch):
    """R58 刻意选了 all-or-nothing：一块脏就整批不写，但必须写下「是哪一块」。"""
    connection = _connection()
    _mirror_env(monkeypatch, connection)
    mirror = pg_store.vector_mirror()

    with pytest.raises(retriever.VectorWriteRejectedError) as refused:
        mirror.add(
            ids=["r130.txt_0", "r130.txt_1", "r130.txt_2"],
            documents=[CLEAN_CHUNK, DIRTY_CHUNK, CLEAN_CHUNK],
            metadatas=[_meta(0), _meta(1), _meta(2)],
            embeddings=[VECTOR, VECTOR, VECTOR],
        )

    assert refused.value.reason == REASON_TEXT_UNENCODABLE
    assert "chunk_index=1" in str(refused.value)
    assert connection.cursors_opened == 0
    assert mirror.written == 0
    assert pg_store.vector_mirror_diagnostics()["mirrored_writes"] == 0


def test_a_nul_free_batch_still_writes_byte_identical_content(monkeypatch):
    """尺子不在镜像里：干净的一批照常落库，正文字节不变——防止「顺手 strip」。"""
    connection = _connection()
    _mirror_env(monkeypatch, connection)
    mirror = pg_store.vector_mirror()

    assert mirror.add(
        ids=["r130.txt_0"],
        documents=[CLEAN_CHUNK],
        metadatas=[_meta(0)],
        embeddings=[VECTOR],
    ) == 1

    upserts = [
        params for sql, params in connection.statements if "INSERT INTO chunk_vectors" in sql
    ]
    assert len(upserts) == 1
    assert upserts[0][pg_store._UPSERT_COLUMNS.index("content")] == CLEAN_CHUNK
    assert mirror.written == 1
    assert pg_store.vector_mirror_diagnostics()["mirrored_writes"] == 1
    assert pg_store.vector_mirror_diagnostics()["last_failure"] is None


def test_without_the_gate_the_failure_degrades_to_the_swallowed_reason(monkeypatch):
    """反证 (b) 的靶形：闸门若摘掉，脏料一路走到 driver，报回来的只剩异常类名。

    这里把 build_rows 换成「直接给出带 NUL 的 row」，等于本单之前的世界，用来钉住
    「具名早拒」不是装饰：同一个入口，reason 会从具名码退化成 vector_mirror_write_failed。
    """
    connection = _connection()
    _mirror_env(monkeypatch, connection)
    mirror = pg_store.vector_mirror()
    dirty_row = (
        "r130.txt_0",
        "r130.txt",
        0,
        DIRTY_CHUNK,
        1,
        "研发部",
        "0a1b2c3d4e5f",
        None,
        "[0.25]",
        MODEL,
        DIM,
        "cosine",
    )
    monkeypatch.setattr(mirror, "build_rows", lambda *args, **kwargs: [dirty_row])

    with pytest.raises(retriever.VectorWriteRejectedError) as refused:
        mirror.add(
            ids=["r130.txt_0"],
            documents=[DIRTY_CHUNK],
            metadatas=[_meta(0)],
            embeddings=[VECTOR],
        )

    assert refused.value.reason == retriever.REASON_VECTOR_MIRROR_WRITE_FAILED
    assert refused.value.reason != REASON_TEXT_UNENCODABLE
    assert "DataError" in str(refused.value)
    assert connection.cursors_opened == 1


def test_the_real_pdf_clears_the_mirror_once_the_loader_is_clean(monkeypatch):
    """判据③ 的端到端那一半：真件 -> load_pdf -> VectorMirror.add -> 桩 driver 收下正文。

    这条把两层接起来，因此反证 (a)（摘掉 load_pdf 的净化）也会打红它：脏正文根本走不到
    driver，会先撞上判据② 的具名拒绝。反过来，只补②不补① 也过不了这条。
    """
    connection = _connection()
    _mirror_env(monkeypatch, connection)
    mirror = pg_store.vector_mirror()
    with _quiet_parser_warnings():
        document = loader.load_pdf(str(NUL_FILE))

    assert mirror.add(
        ids=[f"{NUL_FILE.name}_0"],
        documents=[document],
        metadatas=[_meta(0, filename=NUL_FILE.name)],
        embeddings=[VECTOR],
    ) == 1

    upserts = [
        params for sql, params in connection.statements if "INSERT INTO chunk_vectors" in sql
    ]
    assert len(upserts) == 1
    content = upserts[0][pg_store._UPSERT_COLUMNS.index("content")]
    assert content == document and NUL not in content
    assert mirror.written == 1
    assert pg_store.vector_mirror_diagnostics()["last_failure"] is None


# ------------------------------- 判据④：只读扫存量，非 0 时指名文档、不自动清洗


def test_the_ruler_drops_exactly_the_nul_count_corpus_wide(corpus):
    """全仓逐字比对：净化 == 原文去掉 NUL，字符总数差 == NUL 枚数 == 1。"""
    raw, clean = corpus
    dirty = {name: text.count(NUL) for name, text in raw.items() if NUL in text}

    # §65 二半径实测：全仓 1 枚文档、恰好 1 个 NUL。上面那行也是「扫描不是空跑」的证据。
    assert dirty == {NUL_FILE.name: 1}, f"半径与 §65 二实测不符：{dirty}"
    for name, text in raw.items():
        assert clean[name] == text.replace(NUL, "")
        assert len(text) - len(clean[name]) == text.count(NUL)
    assert sum(len(text) - len(clean[name]) for name, text in raw.items()) == 1


def test_no_stock_chunk_carries_nul_into_the_index(corpus):
    """过完结子，存量一枚 NUL 都不带进索引：分块是正文的子串，出口干净即分块干净。

    真机上这对应现存 985 枚 Chroma 分块与 PG chunks 985 行；离线用例能扫的是仓库自己
    这份语料（与 test_r49 同口径）。将来这里变非 0，本用例指名文档，不许自动清洗。
    """
    raw, clean = corpus
    dirty = sorted((name, text.count(NUL)) for name, text in clean.items() if NUL in text)

    assert dirty == [], f"存量语料仍会把 NUL 带进索引，必须指名文档处理：{dirty}"
    assert len(clean) == len(raw)


def test_the_ruler_is_identity_on_every_stock_document_but_that_one(corpus):
    """「存量一条都不被本单改写」的可证形式：除那 1 枚脏文档，其余逐字不变。"""
    raw, clean = corpus
    dirty_names = sorted(name for name, text in raw.items() if NUL in text)
    rewritten = sorted(name for name in clean if clean[name] != raw[name])

    assert dirty_names == [NUL_FILE.name]
    assert rewritten == dirty_names
    untouched = [name for name in clean if name not in dirty_names]
    assert len(untouched) >= 89, "样本太少，这条恒等检查没有意义"
    assert all(clean[name] == raw[name] for name in untouched)
