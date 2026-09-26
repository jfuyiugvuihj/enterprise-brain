"""
Unified document loader for PDF / DOCX / DOC / TXT / Markdown.

R130: every loader below ends in :func:`sanitize_text`, because pypdf really does hand
back a NUL character (measured in documents/AI-Agent学习路线图.pdf) and a PostgreSQL
text column cannot hold one.

R298: PDF 不再只有文本层这一条腿。逐页判定"这页是扫描页"（判据①），扫描页交给
本地 OCR 通道（app/rag/ocr.py，判据②），有文本层的页一个字都不再 OCR（判据④）。OCR
出来的文字与 pypdf 交回的文字过的是**同一个** :func:`sanitize_text`（判据⑤）—— PG 那一腿
对 NUL 的拒绝与它从哪条通道来无关。

R304: 表格接进来了。带表的 PDF / DOCX 在交给分块器之前先经过 app/rag/tables.py：
正文里多出的是「每枚表一段、段首一行来源锚」的 markdown，每一表行恰好一次；0 表的
文档逐字退回上面两条腿今天的输出，已索引语料不因为本单重算 hash。表格上限触顶、
表格通道自己塌了，都从 DocumentExtraction.tables 这一枚账里看得见（判据⑤：不许静默）。
"""
import contextlib
import os
import threading
from dataclasses import dataclass, replace
from pathlib import Path

from pypdf import PdfReader

from app.common.logger import logger
from app.rag import ocr as ocr_channel
from app.rag import tables as table_channel

#: U+0000 -- the one character a PostgreSQL ``text`` column refuses, and therefore the
#: one character this module drops. psycopg only complains about it from inside
#: ``executemany``, by which point the batch has no document name left to report, so
#: the drop belongs here, at the edge where a third-party parser stops being our problem.
#: The mirror in app/rag/pg_store.py keeps its own gate for anything arriving by another
#: route: two layers, each doing its own job.
NUL_CHARACTER = "\x00"


def sanitize_text(text: str) -> str:
    """Drop NUL characters and nothing else.

    Deliberately surgical (R130 判据①): whitespace, blank lines, emoji, letter case and
    every other control character belong to the document, so they leave unchanged. A text
    without NUL comes back byte-identical, which is what keeps the already-indexed corpus
    (R130 判据④: 985 chunks, none of them dirty) untouched by this ticket.
    """
    if NUL_CHARACTER not in text:
        return text
    return text.replace(NUL_CHARACTER, "")


# ==================== 扫描页判定（判据①） ====================

#: 一页"文本层实质字符"（去掉全部空白后计数）少于这么多，**且**该页存在图像对象，才判为
#: 扫描页。两个条件缺一不可：只看字符数会把空白页/纯矢量图页猜成扫描页，只看图像会把
#: "正文 + 一张插图"的数字页整个重跑一遍 OCR（判据④）。
#:
#: 这个数是量出来的，不是拍的。2026-09-26 在本树 documents/ 现取（pypdf 逐页抽文本、去空白
#: 计数，脚本在仓库外，未改任何生产数据）：
#:   - ``documents/AI-Agent学习路线图.pdf`` 8 页 = 754/957/939/829/937/973/832/942；
#:   - ``documents/refactor_guide.pdf`` 28 页，最小 79、中位 641、最大 1,342；
#:   - 两本合计 36 页，**空文本层 0 页** ⇒ 真·数字 PDF 的实测下沿是 79 个字符。
#: 扫描页一侧：纯图件实测 0 字符（``tests/fixtures/r298_scanned_pages.pdf``），带垃圾隐形
#: 文本层的扫描件通常只剩页码或水印一行（1-20 字符）。48 卡在"一行中文正文"以下、实测下沿
#: 79 以上，两侧都留了余量；客户机要收紧/放宽走 PDF_SCANNED_PAGE_TEXT_CHARS。
SCANNED_PAGE_TEXT_CHARS = 48

#: 运维覆盖入口（与 app/documents/index_policy.py 的 DOCUMENT_INDEX_MIN_CHARS 同风格：
#: **调用期**读环境变量，不在 import 期固化，避开 conftest R70 那一段坑）。
SCANNED_PAGE_TEXT_CHARS_ENV = "PDF_SCANNED_PAGE_TEXT_CHARS"

#: 判据④：来源要逐页记，不许整件二选一。五个态各自可核对。
PAGE_SOURCE_TEXT_LAYER = "text-layer"
PAGE_SOURCE_OCR = "ocr"
PAGE_SOURCE_OCR_EMPTY = "ocr-empty"
PAGE_SOURCE_OCR_DEGRADED = "ocr-degraded"
PAGE_SOURCE_BLANK = "blank"

#: 跟进 ``page_has_image_object``：位图常包在 Form XObject 里，往下一层查，再多不查。
FORM_XOBJECT_DEPTH_LIMIT = 1

#: 判据⑥"降级句"的前缀。测试按它钉"出降级句而非空文本"。
DEGRADATION_NOTE_PREFIX = "扫描页 OCR 降级"


def scanned_page_text_char_threshold() -> int:
    """扫描页判定的字符阈值（环境变量优先，非法值退回常量并 WARNING）。"""
    raw = (os.getenv(SCANNED_PAGE_TEXT_CHARS_ENV) or "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            logger.warning(f"[PDF] 忽略 {SCANNED_PAGE_TEXT_CHARS_ENV}={raw!r}（不是整数）")
    return SCANNED_PAGE_TEXT_CHARS


def _resolve_pdf_object(value):
    """IndirectObject -> 真身；已经是真身就原样返回。"""
    getter = getattr(value, "get_object", None)
    return getter() if callable(getter) else value


def _lookup_pdf_key(node, key: str):
    """读一个字典键，读不到返回 ``None``。

    这一层同时挡住"页对象根本是个鸭子"的情况：``tests/test_document_upload_resilience.py``
    的 FakePage 只有 ``extract_text``，没有 ``get``，走的就是这条返回 ``None`` 的分支。
    """
    getter = getattr(node, "get", None)
    if not callable(getter) or node is None:
        return None
    try:
        return _resolve_pdf_object(getter(key))
    except Exception as exc:  # noqa: BLE001 - 探测失败不是解析失败
        logger.debug(f"[PDF] 读 {key} 失败，按未判定处理：{type(exc).__name__}: {exc}")
        return None


def _mapping_items(node) -> list:
    getter = getattr(node, "items", None)
    if not callable(getter):
        return []
    try:
        return list(getter())
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[PDF] 展开 XObject 失败：{type(exc).__name__}: {exc}")
        return []


def page_has_image_object(page) -> bool:
    """这页的资源树里有没有位图对象（``/Subtype /Image``）。

    只认位图，不认"Form 里画了什么"：判据① 要的是"这一页是一张图"。位图常被扫描驱动包在
    Form XObject 里，所以往下一层查（``FORM_XOBJECT_DEPTH_LIMIT``），再多不查——深度无上限
    的递归会给一张构造怪异的 PDF 把上传线程拖住。

    探测不出结果时返回 ``False``，方向是刻意选的：漏一页 OCR 只是回到今天的结局，而猜一页
    "有图"再把它的文本层重跑一遍 OCR，就是判据④ 点名的双份正文。
    """
    stack: list[tuple[object, int]] = [(page, 0)]
    while stack:
        node, depth = stack.pop()
        resources = _lookup_pdf_key(node, "/Resources")
        xobjects = _lookup_pdf_key(resources, "/XObject")
        for _name, raw_entry in _mapping_items(xobjects):
            entry = _resolve_pdf_object(raw_entry)
            subtype = str(_lookup_pdf_key(entry, "/Subtype") or "")
            if subtype == "/Image":
                return True
            if subtype == "/Form" and depth < FORM_XOBJECT_DEPTH_LIMIT:
                stack.append((entry, depth + 1))
    return False


def _text_layer_char_count(text: str) -> int:
    """文本层"实质字符"数：全部空白不计，其余一个字算一个（与阈值同一口径）。"""
    return len("".join(text.split()))


@dataclass(frozen=True)
class PdfPageExtraction:
    """一页的提取账（判据①④）：判了什么、用了哪条通道、为什么。"""

    page_number: int  # 1-based，人读的页码
    source: str  # PAGE_SOURCE_* 之一
    text: str  # 进入正文的文本（可能为空）
    text_layer_chars: int  # 判据① 左半边：该页文本层实质字符数
    has_image_object: bool  # 判据① 右半边：该页有没有位图对象
    is_scanned: bool
    note: str = ""  # 降级原因 / "图里没字"，正常页为空
    ocr_elapsed_ms: float = 0.0
    raster_size: tuple[int, int] = (0, 0)


@dataclass(frozen=True)
class PdfExtractionReport:
    """一份 PDF 的提取总账。``load_document`` 只要 ``text``，这一份是给排查用的。"""

    file_path: str
    page_count: int
    pages: tuple[PdfPageExtraction, ...]
    text: str
    ocr_dpi: int
    ocr_engine: str
    ocr_attempted: bool
    #: 本轮 OCR 通道是否可用。``False`` 时降级句走"引擎不可用"那一档措辞，
    #: 与"引擎在、只是这一页没跑成（超上限 / 栅格化炸）"区分开。
    ocr_available: bool = True

    @property
    def scanned_page_numbers(self) -> tuple[int, ...]:
        return tuple(page.page_number for page in self.pages if page.is_scanned)

    @property
    def scanned_pages(self) -> int:
        return len(self.scanned_page_numbers)

    @property
    def source_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for page in self.pages:
            counts[page.source] = counts.get(page.source, 0) + 1
        return counts

    @property
    def degradation_notes(self) -> tuple[str, ...]:
        return tuple(
            f"第{page.page_number}页：{page.note}" for page in self.pages if page.source == PAGE_SOURCE_OCR_DEGRADED
        )

    @property
    def degradation_sentence(self) -> str:
        """一句能直接给客户看的降级说明；没有降级时空串（判据②⑥）。"""
        notes = self.degradation_notes
        if not notes:
            return ""
        head = DEGRADATION_NOTE_PREFIX if self.ocr_available else ocr_channel.ENGINE_UNAVAILABLE_NOTE
        return f"{head}：{'；'.join(notes)}"

    def summary(self) -> str:
        """判据① 要求的口径：扫描页数 / 总页数，外加每页来源。"""
        sources = " ".join(f"{name}={count}" for name, count in sorted(self.source_counts.items()))
        return (
            f"pages={self.page_count} scanned={self.scanned_pages}/{self.page_count} "
            f"scanned_pages={list(self.scanned_page_numbers)} dpi={self.ocr_dpi} [{sources}]"
        )


def extract_pdf(
    file_path: str,
    *,
    dpi: int | None = None,
    enable_ocr: bool = True,
    engine=None,
    include_degradation_note: bool = False,
) -> PdfExtractionReport:
    """逐页抽取一份 PDF：文本层照旧，扫描页走本地 OCR 通道（R298）。

    两条通道的分工按页定，不按件定（判据④）：有文本层的页**一个字都不再 OCR**，双份正文
    等于双份墓碑 + 双份近重复命中 —— R269 刚实测过近重复把 Chroma ``ef_search=100`` 的候选
    预算吃光（240 探针 miss 23），检索面不为这种重复买单。

    ``include_degradation_note`` 默认 ``False``：降级说明进 ``report.degradation_sentence``
    与 WARNING 日志，**不默认进正文**，因为那句"本页未能识别文字"会被切块、被 embedding、
    被检索命中，正是要避免的那类墓碑。要它进正文的调用方自己承担后果（测试钉住了两态）。
    """
    reader = PdfReader(file_path)
    pages = list(reader.pages)
    threshold = scanned_page_text_char_threshold()

    probed: list[tuple[int, str, int, bool, bool]] = []
    for index, page in enumerate(pages, start=1):
        layer_text = (page.extract_text() or "").strip()
        chars = _text_layer_char_count(layer_text)
        has_image = page_has_image_object(page)
        probed.append((index, layer_text, chars, has_image, chars < threshold and has_image))

    scanned_numbers = [number for number, _t, _c, _h, is_scanned in probed if is_scanned]
    ocr_by_page: dict[int, ocr_channel.OcrPageOutcome] = {}
    ocr_dpi = ocr_channel.resolve_dpi(dpi)
    ocr_available = True
    if scanned_numbers and enable_ocr:
        run = ocr_channel.ocr_pages(file_path, scanned_numbers, dpi=ocr_dpi, engine=engine)
        ocr_dpi = run.dpi
        ocr_available = run.available
        ocr_by_page = {outcome.page_number: outcome for outcome in run.outcomes}

    records: list[PdfPageExtraction] = []
    parts: list[str] = []
    for number, layer_text, chars, has_image, is_scanned in probed:
        note = ""
        elapsed = 0.0
        raster: tuple[int, int] = (0, 0)
        if not is_scanned:
            source = PAGE_SOURCE_TEXT_LAYER if layer_text else PAGE_SOURCE_BLANK
            body = layer_text
            if not layer_text and not has_image:
                note = "该页既无文本层也无图像对象"
        else:
            outcome = ocr_by_page.get(number)
            if outcome is None:
                source = PAGE_SOURCE_OCR_DEGRADED
                body = layer_text
                note = "扫描页未送 OCR（本次调用关闭了 OCR 通道）"
            elif outcome.ok and outcome.status == ocr_channel.STATUS_RECOGNIZED:
                # 判据⑤：OCR 通道出来的文字过同一个 sanitize_text（R130 那一刀）。
                # 整件在收尾还会再过一次，这里是"谁产出谁负责"，不是重复劳动。
                body = sanitize_text(outcome.text).strip()
                elapsed = outcome.elapsed_ms
                raster = outcome.raster_size
                # 净化后一个字都不剩（整页只有一枚 NUL 这种形状）不能算"OCR 出来了"：
                # 不变量是 source=ocr ⇒ 这一页真的往正文里放了字。
                source = PAGE_SOURCE_OCR if body else PAGE_SOURCE_OCR_EMPTY
                if not body:
                    note = "OCR 文字经 sanitize_text 后为空"
                else:
                    note = ""
            elif outcome.ok:
                source = PAGE_SOURCE_OCR_EMPTY
                body = layer_text
                note = "图像页 OCR 未检出文字"
                elapsed = outcome.elapsed_ms
                raster = outcome.raster_size
            else:
                source = PAGE_SOURCE_OCR_DEGRADED
                body = layer_text
                note = outcome.reason or outcome.status
                elapsed = outcome.elapsed_ms
                raster = outcome.raster_size
        if body:
            parts.append(body)
        records.append(
            PdfPageExtraction(
                page_number=number,
                source=source,
                text=body,
                text_layer_chars=chars,
                has_image_object=has_image,
                is_scanned=is_scanned,
                note=note,
                ocr_elapsed_ms=elapsed,
                raster_size=raster,
            )
        )

    text = sanitize_text("\n\n".join(parts).strip())
    report = PdfExtractionReport(
        file_path=file_path,
        page_count=len(pages),
        pages=tuple(records),
        text=text,
        ocr_dpi=ocr_dpi,
        ocr_engine=ocr_channel.OCR_ENGINE_MODULE,
        ocr_attempted=bool(scanned_numbers) and enable_ocr,
        ocr_available=ocr_available,
    )
    if include_degradation_note:
        sentence = report.degradation_sentence
        if sentence:
            report = replace(report, text=sanitize_text("\n\n".join(item for item in (text, sentence) if item)))
    logger.info(f"Extracted PDF: {file_path} | {report.summary()}")
    for line in report.degradation_notes:
        logger.warning(f"[PDF] OCR 降级: {file_path} {line}")
    return report


# ==================== R304：把 R300 的表格模块接进上传路径 ====================

#: 上限触顶时的 WARNING 前缀（判据⑤：截断不许静默）。口径与 R298 的降级句一致 —— 事实进
#: 账、进日志，**不**进正文：那句「表格没抽完」会被切块、被 embedding、被检索命中，正是
#: R298 判据⑥ 点名的墓碑。要看截断，出口是 DocumentExtraction.tables。
TABLE_TRUNCATION_LOG_PREFIX = "[R304] 表格预算触顶"

#: 表格通道自己塌了（文件读不了、解析器抛错）时的那一句：退回纯正文，不冒充「这份文档没表」。
TABLE_CHANNEL_LOG_PREFIX = "[R304] 表格通道"

#: 逐页散文回补只认这两种触顶：它们是「页根本没走到」，不是「表太多放不下」。前者会把
#: 未走到的页的正文一起丢掉（prose 与 tables 共用同一趟 pdfplumber 页走），接线不许制造这种
#: 丢字；后者的页已经走完，散文完整，回补只会把同一页的字吐两次。
TAIL_RECOVERABLE_TRUNCATION = ("pages:", "time:")


@dataclass(frozen=True)
class TableExtractionReport:
    """一份文档的表格账（判据⑤）：接了几枚表、有没有被上限切断、表格通道自己塌没塌。

    ``load_*`` 只能交回一串正文，所以这一份是接线之后**新增的那半个出口**：
    :func:`extract_pdf_with_tables` 与 :func:`extract_docx_with_tables` 都带着它，
    上传链路要报「表格被截断了」不必回头 grep 日志。
    """

    source: str = ""
    tables: int = 0
    rows: int = 0
    segments: int = 0
    table_chars: int = 0
    page_count: int = 0
    pages_scanned: int = 0
    prose_chars: int = 0
    truncated: str = ""
    degraded: str = ""

    @property
    def has_prose(self) -> bool:
        """判据②：表不算「有正文」——这一枚只数散文通道，一枚表格字符都不算进来。"""
        return self.prose_chars > 0

    @property
    def attached(self) -> bool:
        """表格通道这轮真的接上了（没塌、且抽到了表）：判据① 在 loader 侧的可核对形式。"""
        return bool(self.source) and not self.degraded and self.tables > 0

    @property
    def truncated_notice(self) -> str:
        """一句能直接给客户看的话：哪一道上限收的口、还差哪几页。空串表示没触顶。"""
        if not self.truncated:
            return ""
        kind = self.truncated.split(":", 1)[0]
        labels = {
            "pages": "页数上限",
            "time": "时间预算",
            "chars": "表格字数上限",
            "tables": "表格枚数上限",
        }
        label = labels.get(kind, "未知上限")
        missing = ""
        if self.page_count and self.pages_scanned < self.page_count:
            missing = f"，未走到的页为第 {self.pages_scanned + 1}-{self.page_count} 页"
        return (
            f"表格抽取被{label}切断（{self.truncated}）：已入正文 "
            f"{self.tables} 枚表 / {self.rows} 行 / {self.segments} 段{missing}。"
            "未抽到的表格不补，未走到的页的正文按逐页账回补。"
        )

    def summary(self) -> str:
        return (
            f"source={self.source or '-'} tables={self.tables} rows={self.rows} "
            f"segments={self.segments} table_chars={self.table_chars} "
            f"prose_chars={self.prose_chars} pages={self.pages_scanned}/{self.page_count} "
            f"truncated={self.truncated or '-'} degraded={self.degraded or '-'}"
        )


@dataclass(frozen=True)
class DocumentExtraction:
    """接线后的统一出口：正文（含表格段）+ 表格账 +（PDF 才有的）R298 逐页来源账。

    ``pdf`` 这一枚是判据④ 的凭据：接了表格，逐页「这页走了文本层还是 OCR」的账**逐页照旧**，
    表格那一腿不改写它，也不与它抢口径 —— 表格段是往正文后面**追加**的，不是替换某一页。
    """

    file_path: str
    text: str
    tables: TableExtractionReport
    pdf: PdfExtractionReport | None = None

    @property
    def has_prose(self) -> bool:
        return self.tables.has_prose

    def summary(self) -> str:
        head = f"{self.tables.source or 'document'}: {self.file_path} chars={len(self.text)}"
        return f"{head} | {self.tables.summary()}"


# ---------- 重入闸：tables.pdf_prose_via_loader() 调回来的那一层 ----------
#
# 0 表的 PDF 必须逐字交回「今天的正文」，而 tables.py 拿到这句话的方式是回头调
# load_pdf 自己（它不复制实现，为的是永不与 loader 漂移）。接线之后 load_pdf 又要调表格
# 模块 —— 中间不加这一道闸就是无限递归。闸同时还是个省字的地方：回调那一层不再解析一次
# PDF，也不再跑一遍 OCR（R298 那两条口径由调用方自己带进来的那份账保证，逐字不变）。
# 用 thread-local：上传走 asyncio.to_thread，多枚线程可以同时在不同 PDF 上接线。

_PDF_PROSE_PASS = threading.local()


def _pdf_pass_key(file_path) -> str:
    return os.path.abspath(os.fspath(file_path))


@contextlib.contextmanager
def _pdf_prose_pass(key: str, prose: str):
    stack = getattr(_PDF_PROSE_PASS, "stack", None)
    if stack is None:
        stack = []
        _PDF_PROSE_PASS.stack = stack
    stack.append((key, prose))
    try:
        yield
    finally:
        stack.pop()


def _pdf_prose_holdover(file_path) -> str | None:
    """本轮表格接线里这份 PDF 的「今天的正文」。不在本轮里就返回 None（照平常一样解析）。"""
    stack = getattr(_PDF_PROSE_PASS, "stack", None)
    if not stack:
        return None
    key = _pdf_pass_key(file_path)
    for held_key, prose in reversed(stack):
        if held_key == key:
            return prose
    return None


def _table_report(
    document,
    *,
    prose: str,
    page_count: int = 0,
) -> TableExtractionReport:
    """tables.DocumentTables -> loader 的账（只搬运，不重新发明第二个口径）。"""
    return TableExtractionReport(
        source=document.source,
        tables=document.table_count,
        rows=document.tables.row_count,
        # 一枚表至少渲染一段（无数据行的表走 header-only 那一支，parts() 是空的），
        # 所以这里的段数是「读者会看见几段带锚的表」，不是 parts() 的长度之和。
        segments=sum(max(1, len(block.parts())) for block in document.tables.blocks),
        table_chars=document.tables.char_count,
        page_count=page_count or document.tables.pages,
        pages_scanned=document.tables.pages_scanned,
        prose_chars=len(prose.strip()),
        truncated=document.tables.truncated,
    )


def _report_table_facts(file_path: str, report: TableExtractionReport) -> None:
    """判据⑤：触顶要在 loader 的出口上留下一句能看见的话，而不是悄悄少几枚表。"""
    if report.truncated:
        logger.warning(f"{TABLE_TRUNCATION_LOG_PREFIX}: {file_path} | {report.truncated_notice}")


def _pdf_scanned_prose(report: PdfExtractionReport) -> str:
    """扫描页的 OCR 文字（逐页账里 source=ocr 那些页）。

    为什么要把它们单独再交一次：带表 PDF 的散文那一半改用 pdfplumber 扣掉表框的文字，
    而扫描页根本没有文本层，pdfplumber 从那些页上什么字也拿不到 —— 不补这一笔，接线就会
    把 R298 好不容易 OCR 回来的正文整个丢掉，逐页来源账当场变成假账。
    """
    parts = [page.text for page in report.pages if page.source == PAGE_SOURCE_OCR and page.text.strip()]
    return table_channel.BLOCK_SEPARATOR.join(parts)


def _pdf_prose_beyond(report: PdfExtractionReport, pages_walked: int) -> str:
    """表格上限切断页走时，把没走到的那些页的正文按逐页账回补（判据⑤ 的另一半）。"""
    parts = [
        page.text for page in report.pages if page.page_number > pages_walked and page.text.strip()
    ]
    return table_channel.BLOCK_SEPARATOR.join(parts)


def extract_pdf_with_tables(
    file_path: str,
    *,
    dpi: int | None = None,
    enable_ocr: bool = True,
    engine=None,
    include_degradation_note: bool = False,
) -> DocumentExtraction:
    """PDF 的接线出口（R304）：R298 的逐页正文 + R300 的锚定表格段。

    两半按「这枚文档有没有表」分岔，这条岔路是 R300 的模块自己定的（判据①⑤）：

    - 0 表：正文逐字退回「今天的 load_pdf」。已索引语料不因此重算 hash，接线对存量是空操作。
    - 有表：散文改用 pdfplumber 扣掉表框的那一份，表格段追加在后面。pypdf 那份里本来就
      带着表框里的字，两半不能并存 —— 判据① 要的是「同一枚表不许吐两次」。

    扫描页与表格的**已知边界**（判据④，不许假装支持）：扫描页的正文是 OCR 出来的**文字**，
    而 pdfplumber 找表靠的是页里的矢量框线；一张整页扫描件里没有框线，也根本没有文本层，
    所以「扫描件里的表格」今天不支持，本模块不猜、不声称支持。这类页在这份账里只有一个
    来源（PAGE_SOURCE_OCR），表数为 0，正文不会因为接线而多出一段假的表。

    表格通道塌了（文件读不了 / 解析器抛错）时**只朝一个方向退化**：交回 R298 那份纯正文，
    并在账里写明 degraded —— 那与「这份文档没有表」是两句不同的话，不许混。

    判据②：表不算「有正文」。散文通道为空时 ``tables.has_prose is False``，而 ``text`` 非空、
    首行是来源锚 —— R49 的入索引闸门看的是 loader 交回的正文长度，不是这一枚 has_prose，
    所以「只有表的文档」照常入索引，不会被判成 no_text_content。
    """
    report = extract_pdf(
        file_path,
        dpi=dpi,
        enable_ocr=enable_ocr,
        engine=engine,
        include_degradation_note=include_degradation_note,
    )
    prose = sanitize_text(report.text)
    path = str(file_path)

    try:
        with _pdf_prose_pass(_pdf_pass_key(file_path), prose):
            document = table_channel.extract_document(path, extra_prose="")
    except Exception as exc:  # noqa: BLE001 - 表格通道不许把一次成功的解析顶掉
        logger.warning(f"{TABLE_CHANNEL_LOG_PREFIX} 退回纯正文: {path} | {type(exc).__name__}: {exc}")
        return DocumentExtraction(
            file_path=path,
            text=prose,
            tables=TableExtractionReport(
                source="pdf",
                page_count=report.page_count,
                prose_chars=len(prose.strip()),
                degraded=f"{type(exc).__name__}: {exc}",
            ),
            pdf=report,
        )

    if document.table_count == 0:
        fallback = _table_report(document, prose=prose, page_count=report.page_count)
        _report_table_facts(path, fallback)
        return DocumentExtraction(file_path=path, text=prose, tables=fallback, pdf=report)

    extra_parts: list[str] = [_pdf_scanned_prose(report)]
    if document.tables.truncated.startswith(TAIL_RECOVERABLE_TRUNCATION):
        extra_parts.append(_pdf_prose_beyond(report, document.tables.pages_scanned))
    if include_degradation_note:
        extra_parts.append(report.degradation_sentence)
    extra = table_channel.BLOCK_SEPARATOR.join(part for part in extra_parts if part.strip())
    composed = replace(document, extra_prose=extra) if extra else document

    tables_report = _table_report(
        composed,
        prose=table_channel.BLOCK_SEPARATOR.join([composed.prose, extra]),
        page_count=report.page_count,
    )
    text = sanitize_text(composed.text)
    _report_table_facts(path, tables_report)
    logger.info(f"[PDF] 表格接线: {path} | {tables_report.summary()}")
    return DocumentExtraction(file_path=path, text=text, tables=tables_report, pdf=report)


def _docx_paragraph_prose(file_path: str) -> str:
    """今天 load_docx 的那一串段落，逐字保留（判据③：接线不换正文通道，只追加表格段）。"""
    from docx import Document

    doc = Document(file_path)
    return sanitize_text("\n".join(p.text for p in doc.paragraphs if p.text.strip()))


def extract_docx_with_tables(file_path: str) -> DocumentExtraction:
    """.docx 的接线出口（R304）：段落 join + Word 表格段（含嵌在单元格里的表）。

    与 PDF 那一侧不同，这里**不存在重复的余地**：``doc.paragraphs`` 从来不含单元格里的字
    （R300 实测：只有表的 .docx 交回空列表），所以段落 join 与表格段拼接后每行恰好一次。

    0 表时正文逐字退回今天的样子；表格通道塌了则退回段落 join 并在账里写明。
    """
    prose = _docx_paragraph_prose(file_path)
    try:
        document = table_channel.extract_document(file_path, prose=prose)
    except Exception as exc:  # noqa: BLE001 - 表格通道不许把一次成功的解析顶掉
        logger.warning(f"{TABLE_CHANNEL_LOG_PREFIX} 退回纯正文: {file_path} | {type(exc).__name__}: {exc}")
        return DocumentExtraction(
            file_path=file_path,
            text=prose,
            tables=TableExtractionReport(
                source="docx", prose_chars=len(prose.strip()), degraded=f"{type(exc).__name__}: {exc}"
            ),
        )

    if document.table_count == 0:
        return DocumentExtraction(
            file_path=file_path,
            text=prose,
            tables=_table_report(document, prose=prose),
        )

    tables_report = _table_report(document, prose=document.prose)
    text = sanitize_text(document.text)
    _report_table_facts(file_path, tables_report)
    logger.info(f"[DOCX] 表格接线: {file_path} | {tables_report.summary()}")
    return DocumentExtraction(file_path=file_path, text=text, tables=tables_report)


def load_pdf(
    file_path: str,
    *,
    dpi: int | None = None,
    enable_ocr: bool = True,
    engine=None,
    include_degradation_note: bool = False,
) -> str:
    """抽取 PDF 正文：本地 pypdf 文本层 + 本地 OCR 扫描页（R298）+ 锚定表格段（R304）。

    接线的那一腿在 :func:`extract_pdf_with_tables`（含「扫描件里的表格今天不支持」那条边界）；
    这一枚只负责交回正文串，要表格账与逐页来源账的调用方用前者。

    出口再过一次 :func:`sanitize_text` —— R130 的不变量是"每一个 load_* 出口都过同一把
    尺"（``tests/test_r130_text_unencodable_is_named_refusal.py`` 按源码钉这条），尺在这一条
    路上已经落过几次（OCR 通道一次、整件收尾一次、表格模块的 _finish 一次），这里是最后一个
    出口口径，对不含 NUL 的文本是恒等，不多改一个字符。

    被 :func:`app.rag.tables.pdf_prose_via_loader` 回调进来的那一层直接从闸里交回正文，
    不再走第二遍表格模块 —— 那既是递归的止点，也是"0 表的 PDF 逐字不变"的凭据。
    """
    holdover = _pdf_prose_holdover(file_path)
    if holdover is not None:
        return sanitize_text(holdover)
    extraction = extract_pdf_with_tables(
        file_path,
        dpi=dpi,
        enable_ocr=enable_ocr,
        engine=engine,
        include_degradation_note=include_degradation_note,
    )
    return sanitize_text(extraction.text)


def load_docx(file_path: str) -> str:
    """Plain text from .docx: 段落 join（逐字不变）+ Word 表格段（R304 接线）。

    账在 :func:`extract_docx_with_tables`；这一枚只交回正文串，出口照旧过同一把尺。
    """
    return sanitize_text(extract_docx_with_tables(file_path).text)


def load_doc(file_path: str) -> str:
    """Best-effort extraction for old .doc files."""
    import olefile

    ole = olefile.OleFileIO(file_path)
    if ole.exists("WordDocument"):
        stream = ole.openstream("WordDocument")
        raw = stream.read()
        text = "".join(chr(b) for b in raw if 31 < b < 127 or b in (10, 13))
        lines = [line.strip() for line in text.split("\n") if len(line.strip()) > 2]
        ole.close()
        return sanitize_text("\n".join(lines))
    ole.close()
    return ""


def load_txt(file_path: str) -> str:
    """Read TXT with automatic encoding detection."""
    for encoding in ["utf-8", "gbk", "gb2312"]:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return sanitize_text(f.read())
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Unable to detect text encoding: {file_path}")


def load_md(file_path: str) -> str:
    """Read Markdown as plain source text, reusing TXT encoding detection."""
    return sanitize_text(load_txt(file_path))


def load_document(file_path: str) -> str:
    """Auto-detect file type and return plain text."""
    ext = Path(file_path).suffix.lower()
    logger.info(f"Loading document: {file_path} ({ext})")

    if ext == ".pdf":
        return sanitize_text(load_pdf(file_path))
    if ext == ".docx":
        return sanitize_text(load_docx(file_path))
    if ext == ".doc":
        return sanitize_text(load_doc(file_path))
    if ext == ".txt":
        return sanitize_text(load_txt(file_path))
    if ext == ".md":
        return sanitize_text(load_md(file_path))
    raise ValueError(f"Unsupported file format: {ext}")
