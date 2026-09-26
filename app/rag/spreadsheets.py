"""R305: Excel / CSV 上传 -> 带锚点的检索文本（渲染整套沿用 R300，不另起第二套）。

================================================================== 这一单不接线（接线 = R306）
两枚现取事实同时成立，所以"白名单先放开、分派还没落"确实比不接更坏：

  - `app/documents/file_security.py:28` 的 `_ALLOWED_TYPES` 只有 .pdf/.txt/.md/.docx 四格。
    `.xlsx`/`.csv` 在 `inspect_upload_header()`（同文件 :106-107）就被拒，上传路由在**写第一个
    字节之前**回 400 `unsupported_file`（`app/api/v1/chat.py:3795` -> :3798）。
  - `app/rag/loader.py:419` 的 `load_document()` 对认不出的后缀 `raise ValueError`。

白名单一放开而分派不落地，客户拿到的就不再是 400 而是 500 `document_parse_failed`
（`chat.py:3857`——那一条还会把文件和目录行留下、把版本记成 `parse_status="failed"`）。
R306 缺的只有 `loader.py:419` 那行 raise 之前的三行：

    if ext in spreadsheets.SPREADSHEET_SUFFIXES:
        return sanitize_text(spreadsheets.load_spreadsheet_text(file_path))

`load_spreadsheet_text()` 与 `load_txt()` 同形（进一枚路径，出一段已过 R130 闸门的文本），
所以这三行不需要 try/except，也不需要新错误码。判据①把 `loader.py` 划成禁域（R304 正在
改它），本单因此一字未动那枚文件：上面是**建议的落笔**，不是已完成。白名单/预览两格的
清单写在 R305 回执第 4 节，这里不复述。

================================================================== 产物是给检索用的文本，不是电子表格
每一枚块都是 `app/rag/tables.py` 的 `TableBlock`，layout 也整个走 `tables.render_tables()`：
锚点行 -> markdown 表头 + 分隔行 -> 每行一条 `| a | b |`，按 `SEGMENT_CHAR_BUDGET`
（=448，与上游唯一那把尺同值）装箱，**每段重贴一次锚**。锚的形状（`ANCHOR_JOIN` = " · "）：

    文件名.xlsx · Sheet「工作表名」 · 表N（i/j段） · 合并单元格K处
    文件名.csv · 表N（i/j段）

所以判据④禁的事这里都没做：没有"整表拼成一坨无锚点长串"，没有第二套分块器，
没有第二个字符预算常量。"每行带表头锚点"在这套渲染里的落法是**每一段的第一行既是锚也是
表头**（`TableBlock._assemble`/`to_markdown`），R300 已按真分块器逐行验过这条路，本模块复用。

一处**复用件自带的实测偏差**（缺陷在 `tables.py`，本单禁改，已回报总控）：`TableBlock.parts()`
算余量用的是不带段号的 `anchor()`，而 `_assemble` 印出来的是带段号的 `anchor(i,total)`，
于是段长上限比 `SEGMENT_CHAR_BUDGET` 多出 "（i/j段）" 那一截。实测一枚 144 行 / 37 段的真
CSV：最长段 450 字（> 448，仍 < 上游 500 与 R300 自己量出的 499 丢锚线）。同一枚问题在
`_header_only()` 里已经被"按最宽的 `anchor(99, 99)` 预留"修过，`parts()` 这一路漏了。

================================================================== 解析器交回来的东西（本机实测，不是推测）
`openpyxl` 3.1.5（`pyproject.toml:29` 直接依赖；本单零依赖变更）：

* **合并单元格**：左上角交回值，其余被覆盖的位置交回 `None` —— 与 pdfplumber 同一枚信号，
  所以 `tables.py` docstring 里"None = 被覆盖"的实测口径对得上。但 openpyxl 还额外给了真话：
  `ws.merged_cells.ranges` 逐项列出区域，于是"被覆盖"与"本来就是空格"分得开。
  本模块因此**不**走 `tables._rectangular()` 的"None 一律当被覆盖"（那一律会把一个真正的
  空格按左邻/上一行猜出一个值），而是按 ranges 生成覆盖位图、值取左上角——与
  `app/tools/excel.py:41` `_fill_merged_cells` 同一条"原地展开"口径。
* `read_only=True` **没有** `merged_cells`（实测 `AttributeError: 'ReadOnlyWorksheet' object
  has no attribute 'merged_cells'`）⇒ 流式读与"认得合并单元格"二选一，本单选后者，
  代价写在下面"上限"一节。
* xlsx 里没有"日期"这个类型：纯日期单元格交回来是**零点整的 `datetime`**（实测
  `datetime.date(2026,2,1)` 写进去、`datetime.datetime(2026,2,1,0,0)` 读出来）。
* 数字在**写入侧**就被 openpyxl 的 `safe_string` 按 `"%.16g"` 格式化（实测 `0.1+0.2` 落盘成
  `0.3`；`100.0` 落盘成 `100`，因而读回来是 `int`）。读侧本模块只做 `str()`，再加任何
  一次取整都是第二次漂移——所以一枚都没有加。

`csv`（stdlib）：空行交回 `[]`，短行交回短 list，引号里的分隔符与换行由 reader 处理。

================================================================== CSV 的三档编码 = 就是 load_txt 那三档
判据②要"沿用 `load_txt` 那三档"。最稳的沿用是**调用它**而不是抄它：整段文本取自
`loader.load_txt()`（`app/rag/loader.py:388`，utf-8 -> gbk -> gb2312，全败则
`ValueError: Unable to detect text encoding`）。本模块不复制那份清单，因此不存在
"txt 改了、csv 忘了跟"的漂移面；专件按**行为等值**钉：同一枚 utf-16 文件，两边必须同样地炸。

三处如实记录：
* `REPORT_ENCODINGS` 只为回执记账（日志要说清这枚 gbk 文件是按 gbk 读的）。它不参与任何
  判定，且每次记账都自证"重解一遍必须与 load_txt 交回的文本逐字相等"，所以清单漂了只会
  记成 `unknown`，记不出假账。
* 三档里的 `gb2312` 实测是**死档**：穷举 0x20..0xFE x 0x20..0xFE 全部 134,209 枚 2 字节
  序列，"gb2312 可解而 gbk 不可解"的有 **0 枚**，所以一枚真 gb2312 中文件在第二档就被
  gbk 收走了。这条对 `.txt` 今天就成立（同一个 `load_txt`），本单照旧沿用判据②点名的三档，
  只在回执里报给总控裁定。
* BOM 是本模块**主动**做的唯一一处偏离：`load_txt` 用 `encoding="utf-8"`，带 BOM 的 UTF-8
  交回时首字符是 U+FEFF，会污染表头那一格。裁掉它不引入第四档编码，也不改判定顺序。

分隔符（判据②要求 sniff，至少逗号/分号/Tab）：本模块自带一枚可解释的计数器，而不是
`csv.Sniffer`（它面对单列表与带引号的中文表会抛 `_csv.Error`，实测见专件）。打分口径与
并列时的优先级写在 `sniff_delimiter()` 的 docstring 里，逐条有专件钉。

================================================================== 上限：五道，每道都亲测真被触发
`rows:` / `cols:` 是**物化**顶（读的时候就收手），`budget:` 是**内容**顶（全文档预算，
逐块累计，先到先得，与 R300 的 `chars:` 同一条规则），`sheets:` / `time:` 是**成本**顶。
超限一律"截断 + 回执点名是哪一道、哪张表、留了多少"，绝不静默：

    sheets:2of3          第 3 张 sheet 起不读（顶 = MAX_SHEETS_PER_WORKBOOK）
    rows:一月:5000of90012   xlsx：维度知道总数（数的是网格行，**含表头那一枚**）
    rows:CSV:5000+       csv：流式读不数到底，所以用 + 号而不是假报一个总数
    cols:一月:128of300   砍掉的是列（宽表按列序保留前 128 列）
    budget:2:412of900    第 2 枚块按行装到 412 行就撞上全文档字符顶
    time:3of7            撞上时间预算，后 4 张没读

超内容顶时**先保表头再按行往里装**（`_fit_budget`）。连表头都装不下的那张表整枚不入库，
回执记 `budget:`。为什么不是"整表丢弃"：一张表的列名本身就是可检索的事实，客户问
"这份表有哪些字段"该答得出来；而"这张表没进库"必须是回执说出来的，不是渲染悄悄做的。

xlsx 的行顶省不了内存，只省时间与后面的渲染：`read_only=True` 才流式，而那一档没有
`merged_cells`（实测）。真正挡在门口的是上传体积顶
（`app/api/v1/chat.py:94` `MAX_DOCUMENT_UPLOAD_BYTES`，默认 25 MiB）。
"""
from __future__ import annotations

import csv
import datetime
import io
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Sequence

from app.common.logger import logger
from app.rag.tables import (
    ANCHOR_JOIN,
    MAX_CONTEXT_CHARS,
    MAX_TABLE_CHARS,
    MAX_TABLES_PER_DOCUMENT,
    SEGMENT_CHAR_BUDGET,
    TABLE_TIME_BUDGET_SECONDS,
    TableBlock,
    _cell_text,
    _shape_from,
    render_tables,
)

#: 本模块认的后缀。**接线时白名单放开哪一格，这里就得有一格**——两边不一致就是"400 变
#: 500"，所以这两枚元组是契约的一部分：tests/test_r305_spreadsheets.py 拿
#: file_security._ALLOWED_TYPES 现取对照（今天两边都不含 .xlsx/.csv，同样不红）。
CSV_SUFFIXES = (".csv",)
XLSX_SUFFIXES = (".xlsx",)
SPREADSHEET_SUFFIXES = CSV_SUFFIXES + XLSX_SUFFIXES

#: 旧二进制格式明确不做：openpyxl 读不了它，而仓库直接依赖里没有 xlrd
#: （`app/tools/excel.py:88` 那条 `.xls` 分支因此今天就是坏的，与本单无关，已报总控）。
UNSUPPORTED_SUFFIXES = (".xls",)

#: 只为回执记账，见 docstring：判定唯一入口是 loader.load_txt。
REPORT_ENCODINGS = ("utf-8", "gbk", "gb2312")

#: 分隔符候选（判据②）。**元组顺序就是并列时的优先级**：逗号优先，因为它是 CSV 的 D。
DELIMITERS = (",", ";", "\t")
DELIMITER_DEFAULT = ","

#: sniffer 只看前这么多行；一行都读不到就退回默认值，不猜。
SNIFF_SAMPLE_LINES = 32

#: 与 `tables.MAX_TABLES_PER_DOCUMENT` 同一个数、同一把尺（一张 sheet 最多产出一枚块，
#: 所以"表枚数顶"就是"sheet 数顶"）；专件钉这份同源，不许本模块自填第二个数。
MAX_SHEETS_PER_WORKBOOK = MAX_TABLES_PER_DOCUMENT  # 200
MAX_SPREADSHEET_CHARS = MAX_TABLE_CHARS  # 40_000
SPREADSHEET_TIME_BUDGET_SECONDS = TABLE_TIME_BUDGET_SECONDS  # 12.0 s

#: 存量实测（2026-09-26 本机现取；`git ls-files "*.xlsx" "*.csv"` 在业务目录里只有这两枚
#: 真件）：data/2026年6月门店经营数据.xlsx = 1 sheet / 11 行 / 7 列 / 0 处合并；
#: data/报销明细表.csv = 146 行 / 9 列 / UTF-8 / 逗号 / CRLF。
#: 列顶 128 = 存量最坏 9 的 14 倍，行顶 5_000 = 存量最坏 145 的 34 倍。两道各自能挡住一种
#: 病态件：一行几十字符的宽表先撞 `budget:`，一列三个字符的窄表先撞 `rows:`——两种形状
#: 都有专件，所以两道顶都不是摆设。
MAX_ROWS_PER_SHEET = 5_000
MAX_COLUMNS_PER_SHEET = 128

#: 纯日期单元格在 xlsx 里交回来长这样（实测见 docstring）。
_MIDNIGHT = datetime.time(0, 0)


@dataclass(frozen=True)
class SheetReport:
    """一张 sheet / 一枚 CSV 在读入阶段做了什么，全部可核对（判据⑥要的就是这份账）。

    三行数字不是同一把尺，别读混：`rows_total` 是**这个格式自己声称**有的行数
    （xlsx = `ws.max_row`，CSV = 解析出来的原始行数，含表头）；`rows_read` 是清掉空行之后
    真的进了网格的行数（仍含表头）；`rows_kept` 是**交出去的 data 行**，不含表头
    ——所以一张 11 行的 xlsx 是 total=11 / read=11 / kept=10。`columns_total` 同理，
    比 `columns_kept` 多出来的就是被砍的超宽列与被去掉的全空列。
    """

    label: str
    index: int = 1
    source: str = ""
    rows_total: int = 0
    rows_read: int = 0
    rows_kept: int = 0
    columns_total: int = 0
    columns_kept: int = 0
    blank_rows_dropped: int = 0
    empty_columns_dropped: int = 0
    spans: int = 0
    state: str = "visible"
    emitted: bool = False
    truncated: str = ""


@dataclass(frozen=True)
class Spreadsheet:
    """一枚表格文件的解析总账：块、每格的账、是哪道顶收的口、花了多少时间。"""

    filename: str
    source: str
    blocks: tuple[TableBlock, ...] = ()
    sheets: tuple[SheetReport, ...] = ()
    encoding: str = ""
    delimiter: str = ""
    truncated: str = ""
    skipped_sheets: int = 0
    elapsed_s: float = 0.0

    @property
    def block_count(self) -> int:
        return len(self.blocks)

    @property
    def row_count(self) -> int:
        return sum(block.row_count for block in self.blocks)

    @property
    def char_count(self) -> int:
        return sum(block.char_count for block in self.blocks)

    @property
    def text(self) -> str:
        """交给既有分块器的那一段文本：锚 + 表头 + 每行一条，出口已过 R130 闸门。

        预算**显式**传 `SEGMENT_CHAR_BUDGET`（借来的那把尺），而不是吃 render_tables 的
        默认值：本层的账（判据⑥那道字符顶）与 tests 里的段长断言都按这把尺记，
        上游哪天改了默认值，这里要当场对上而不是悄悄变宽。
        """
        return render_tables(self.blocks, SEGMENT_CHAR_BUDGET)

    def summary(self) -> dict:
        return {
            "filename": self.filename,
            "source": self.source,
            "sheets": len(self.sheets),
            "skipped_sheets": self.skipped_sheets,
            "blocks": self.block_count,
            "rows": self.row_count,
            "encoding": self.encoding,
            "delimiter": delimiter_name(self.delimiter),
            "truncated": self.truncated,
            "elapsed_s": round(self.elapsed_s, 3),
        }

    def stats(self) -> dict:
        merged = dict(self.summary())
        merged.update(
            {
                "table_chars": self.char_count,
                "rendered_chars": len(self.text),
                "segments": sum(len(block.parts()) for block in self.blocks),
                "sheets_detail": [sheet.__dict__ for sheet in self.sheets],
            }
        )
        return merged


def delimiter_name(delimiter: str) -> str:
    """日志与回执里的可读名：Tab 打出来是一整页空白，不能进日志。

    空串原样交回——xlsx 没有分隔符，那一格该是空的，而不是 `repr("")` 那种三个字符的假话。
    """
    if not delimiter:
        return ""
    return {"\t": "tab", ",": "comma", ";": "semicolon"}.get(delimiter, repr(delimiter))


def _anchor_base(display_name: str | None, path: Path) -> str:
    """锚点第一段。落盘名是 uuid（`chat.py:3802-3803` `build_storage_path`），所以这一格
    **必须**能被调用方改名。

    `load_document()` 只有一枚路径可传，接线时若不把 `inspection.display_filename` 递进来，
    客户看到的出处就是 `2f3a9c1e....xlsx · Sheet「一月」`。这是 R306 要裁的一格，本模块
    把口子先留好：`display_name` 传什么，锚点第一段就是什么。
    """
    raw = (display_name if display_name is not None else path.name) or path.name
    cleaned = _cell_text(raw)
    return cleaned or (path.name or "工作簿")


def _sheet_label(name: str) -> str:
    """能塞进锚点的工作表名：清洗一次，再按 `MAX_CONTEXT_CHARS` 收口（判据④的口径）。

    Excel 允许表名叫 `一月 · 销售`，而 " · " 正是锚点的字段分隔符——不替换掉它，解析锚点的
    人会多出一枚不存在的字段。截断与 tables.py 同法：硬切，不加省略号
    （`extract_docx_tables` 对前文就是这么办的）。
    """
    cleaned = _cell_text((name or "").replace(ANCHOR_JOIN, " "))
    return (cleaned or "工作表")[:MAX_CONTEXT_CHARS]


def render_value(value: object) -> str:
    """一个单元格的**存储值** -> 文本（判据⑤：日期只有一种写法，数字不做第二次取整）。

    规则一共四条，全部与 locale 无关（没有任何一处走 `strftime`/`%x`/locale 格式化，
    专件按源码钉死）：

    * `None` -> ""；
    * `datetime` -> `YYYY-MM-DD HH:MM:SS`；零点整则退成 `YYYY-MM-DD`——xlsx 里存的就是同一枚
      序列号，日期与"零点的时刻"本来就分不开（实测见 module docstring），一种值只给一种写法；
    * `date`/`time`/`timedelta` -> 各自 `isoformat()`；
    * 其余（`int`/`float`/`bool`/`str`）-> `str()`，也就是 Python 的最短往返表示：
      `0.3333333333333333` 就是 `0.3333333333333333`，`1e+20` 就是 `1e+20`。这里若改成
      `%.2f` 或千分位，就是拿一个印出来的数替换客户存的数。

    已知**未做**（如实记录，不静默）：不看 number format。百分比单元格在 xlsx 里存 0.15、
    屏上显示 15%，本模块交回 `0.15`。判据⑤禁的是"四舍五入伪装"，没有要求还原格式；按
    `cell.number_format` 再实现一套格式化引擎就是本文件判据③禁的第②套渲染。
    """
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        if value.time() == _MIDNIGHT:
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        # timedelta **没有** isoformat()（实测 AttributeError）。openpyxl 会把带时长格式的
        # 单元格读回成 timedelta（实测：写 timedelta(days=1,hours=2) 读回来还是它），
        # 所以这一支不是防御性代码，是一枚真会走到的路：走 str()，仍是确定写法、仍与 locale 无关。
        return str(value)
    return _cell_text(value)


@dataclass
class _Grid:
    """一张表在读入阶段的形状：值、覆盖位、以及"读的时候各自丢掉了什么"。"""

    values: list[list[str]] = field(default_factory=list)
    flags: list[list[bool]] = field(default_factory=list)
    rows_total: int = 0
    columns_total: int = 0
    blank_rows: int = 0
    empty_columns: int = 0
    truncated: str = ""


def _normalize_grid(grid: _Grid, *, label: str, max_columns: int) -> _Grid:
    """补齐成方格 -> 砍超宽列 -> 去空行 -> 去全空列（判据②"不得产出空白块"的前半）。

    顺序是有讲究的：列顶必须在补齐**之前**生效，否则一枚 300 列的病态件会先被补齐成
    5_000 x 300 再处理；空行必须在全空列**之前**去掉，否则一列只剩一行残留就会被当成
    "这列有值"而留下。空行必须在这里去掉：`_shape_from` 之后没有第二处会做，而
    `tables._rectangular()` 那一族"None 就当被覆盖"的补法会把一枚空行抄成上一行的副本。
    """
    rows = [list(row) for row in grid.values]
    marks = [list(row) for row in grid.flags]
    seen = max(max((len(row) for row in rows), default=0), grid.columns_total)
    if seen > max_columns:
        grid.truncated = grid.truncated or f"cols:{label}:{max_columns}of{seen}"
        rows = [row[:max_columns] for row in rows]
        marks = [row[:max_columns] for row in marks]
    width = max((len(row) for row in rows), default=0)

    kept_rows: list[list[str]] = []
    kept_marks: list[list[bool]] = []
    for row, mark in zip(rows, marks):
        line = list(row[:width]) + [""] * (width - len(row[:width]))
        flags = list(mark[:width]) + [False] * (width - len(mark[:width]))
        if not any(line):
            grid.blank_rows += 1
            continue
        kept_rows.append(line)
        kept_marks.append(flags)

    live = [position for position in range(width) if any(row[position] for row in kept_rows)]
    grid.empty_columns = width - len(live)
    grid.values = [[row[position] for position in live] for row in kept_rows]
    grid.flags = [[mark[position] for position in live] for mark in kept_marks]
    grid.columns_total = seen
    return grid


def _fit_budget(block: TableBlock, remaining: int) -> tuple[TableBlock | None, int]:
    """把一枚块裁进全文档预算：先保表头，再按行装（判据⑥的超顶行为，可解释）。

    记的是 `TableBlock.char_count` 那本账（表头 + 说明行 + 每行，不含锚点行），与 R300
    `chars:` 顶同一口径；锚点行按 R300 同样不计入，因为它有 `SEGMENT_CHAR_BUDGET` 那把尺
    自己管着。返回 (块或 None, 被顶掉的行数)。
    """
    frame = len(block.header_line) + len(block.separator_line) + 2
    if block.caption_line:
        frame += len(block.caption_line) + 1
    if remaining < frame:
        return None, block.row_count
    used = frame
    kept = 0
    for line in block.row_lines:
        used += len(line) + 1
        if used > remaining:
            break
        kept += 1
    if kept >= block.row_count:
        return block, 0
    return replace(block, rows=block.rows[:kept]), block.row_count - kept


def _emit(
    grid: _Grid,
    *,
    label: str,
    anchor_name: str,
    ordinal: str,
    source: str,
    index: int,
    remaining: int,
    max_columns: int,
    state: str = "visible",
) -> tuple[TableBlock | None, SheetReport]:
    """清洗 -> 交给 tables.py 的那套渲染 -> 裁预算。一张 sheet 只出一枚块。"""
    grid = _normalize_grid(grid, label=label, max_columns=max_columns)
    shaped = _shape_from(grid.values, grid.flags)
    report = SheetReport(
        label=label,
        index=index,
        source=source,
        rows_total=grid.rows_total,
        rows_read=len(grid.values),
        columns_total=grid.columns_total,
        columns_kept=len(grid.values[0]) if grid.values else 0,
        blank_rows_dropped=grid.blank_rows,
        empty_columns_dropped=grid.empty_columns,
        spans=sum(1 for marks in grid.flags for mark in marks if mark),
        state=state,
        truncated=grid.truncated,
    )
    if shaped is None:
        return None, report
    shaped.source = source
    block = shaped.to_block(anchor_name, ordinal)
    fitted, dropped = _fit_budget(block, remaining)
    if dropped:
        report = replace(
            report,
            truncated=report.truncated
            or f"budget:{ordinal}:{block.row_count - dropped}of{block.row_count}",
        )
    if fitted is None:
        return None, report
    return fitted, replace(report, rows_kept=fitted.row_count, emitted=True)


def sniff_delimiter(
    lines: Sequence[str],
    candidates: Sequence[str] = DELIMITERS,
    *,
    sample: int = SNIFF_SAMPLE_LINES,
) -> str:
    """在**已经解码好的**前若干行里挑分隔符（判据②）。打分口径，三级，逐条有专件：

    1. 每一行都被切成**同样多**且 >= 2 枚字段 —— 先比这一条；
    2. 再比谁切得窄（取 `min` 而不是 `max`：最保守的那一行说了算，宽窄不一的样本判低分）；
    3. 还平就按 `candidates` 的顺序，逗号优先——它是 CSV 的 D。

    只看样例行、不追跨行引号：真正的解析仍然由 `csv.reader` 对整个文件做，所以引号里的
    分隔符不会切错字段，唯一的失败模式是"选错候选"，而它被第 2 条按最窄行压住。
    三档全不成立（单列表、只有一行、全是空行）就退回 `DELIMITER_DEFAULT`，不猜。
    """
    sample_lines = [line for line in lines if line.strip()][:sample]
    if not sample_lines:
        return DELIMITER_DEFAULT
    best = DELIMITER_DEFAULT
    best_key: tuple[int, int, int] | None = None
    for order, candidate in enumerate(candidates):
        widths: list[int] = []
        for line in sample_lines:
            try:
                widths.append(len(next(csv.reader([line], delimiter=candidate))))
            except (csv.Error, StopIteration):
                widths = []
                break
        if not widths:
            continue
        key = (1 if min(widths) == max(widths) and min(widths) >= 2 else 0, min(widths), -order)
        if best_key is None or key > best_key:
            best_key, best = key, candidate
    return best


def decode_text(file_path: str | Path) -> tuple[str, str]:
    """整段文本取自 `loader.load_txt()`（判据②：沿用那三档，而不是抄那三档）。

    返回 (text, encoding)。`encoding` 只是回执记账：拿 `REPORT_ENCODINGS` 逐档重解原始字节，
    **必须与 load_txt 交回的文本逐字相等**才敢记名，所以清单漂了只会记成 `unknown`。
    BOM 在这里裁掉（docstring 里写明它是唯一一处主动偏离）。
    """
    from app.rag.loader import load_txt

    path = Path(file_path)
    text = load_txt(str(path))
    encoding = "unknown"
    if text.startswith("\ufeff"):
        text = text[1:]
        encoding = "utf-8-sig"
    elif text:
        try:
            raw = path.read_bytes()
        except OSError:
            raw = b""
        # 比较前必须做与 open(..., "r") 同一档的换行翻译：`data/报销明细表.csv` 是 CRLF，
        # 不翻译就拿 \r\n 与 \n 比，实测会把一枚清清楚楚的 UTF-8 文件记成 unknown。
        for candidate in REPORT_ENCODINGS:
            try:
                decoded = raw.decode(candidate)
            except (UnicodeDecodeError, LookupError):
                continue
            if decoded.replace("\r\n", "\n").replace("\r", "\n") == text:
                encoding = candidate
                break
    return text, encoding


def load_csv(
    file_path: str | Path,
    *,
    display_name: str | None = None,
    delimiter: str | None = None,
    max_rows: int = MAX_ROWS_PER_SHEET,
    max_columns: int = MAX_COLUMNS_PER_SHEET,
    max_chars: int = MAX_SPREADSHEET_CHARS,
) -> Spreadsheet:
    """一枚 CSV -> 带锚点的检索文本。编码走 load_txt，分隔符走 sniff_delimiter。

    顶落在 `rows:`（流式读不数到底，记 `5000+`）、`cols:`、`budget:` 三道上。
    空行与全空列在 `_normalize_grid` 里去掉，所以一张只有空行的 CSV 交回**空文本**而不是
    空白块——空文本会由 `app/documents/index_policy.py` 按"实质字符 < 4"判成不入库，
    并把稳定码留在回执里，而不是悄悄进库。
    """
    path = Path(file_path)
    started = time.monotonic()
    text, encoding = decode_text(path)
    chosen = delimiter or sniff_delimiter(text.splitlines())

    grid = _Grid()
    truncated = ""
    for position, row in enumerate(csv.reader(io.StringIO(text, newline=""), delimiter=chosen), 1):
        if position > max_rows:
            truncated = f"rows:CSV:{max_rows}+"
            break
        grid.values.append([render_value(value) for value in row])
        grid.flags.append([False] * len(row))
    # 行数记账：撞顶那一档也照样记"读进来多少"，"还有多少"由 rows: 码里的 + 号说，
    # 不假报一个数不到的总数（CSV 是流式读的，csv.reader 不肯告诉我还剩多少行）。
    grid.rows_total = len(grid.values)
    grid.columns_total = max((len(row) for row in grid.values), default=0)

    base = _anchor_base(display_name, path)
    block, report = _emit(
        grid,
        label="CSV",
        anchor_name=base,
        ordinal="1",
        source="csv",
        index=1,
        remaining=max_chars,
        max_columns=max_columns,
    )
    report = replace(report, truncated=truncated or report.truncated)
    result = Spreadsheet(
        filename=base,
        source="csv",
        blocks=() if block is None else (block,),
        sheets=(report,),
        encoding=encoding,
        delimiter=chosen,
        truncated=report.truncated,
        elapsed_s=time.monotonic() - started,
    )
    logger.info(f"R305 表格入库 csv: {result.summary()}")
    return result


def _xlsx_grid(worksheet, *, label: str, max_rows: int, max_columns: int) -> _Grid:
    """一张 worksheet -> 值 + **真**覆盖位图（判据③：合并单元格按实测口径处理）。

    覆盖位由 `merged_cells.ranges` 生成，值取左上角，而不是把 `None` 一律当成被覆盖：
    后者是 pdfplumber 那个解析器**没有**别的信息时的猜法，openpyxl 有。
    左上角落在读取窗口之外的合并区域整块跳过（那部分内容本来就被行顶/列顶截掉了，
    在这里猜出来只会多一行假数据）。
    """
    raw: list[list[object]] = []
    truncated = ""
    for position, row in enumerate(worksheet.iter_rows(values_only=True), 1):
        if position > max_rows:
            truncated = f"rows:{label}:{max_rows}of{worksheet.max_row}"
            break
        raw.append(list(row[: max_columns + 1]))
    values = [[render_value(value) for value in row[:max_columns]] for row in raw]
    flags = [[False] * len(row[:max_columns]) for row in raw]
    for merge in worksheet.merged_cells.ranges:
        top_row, top_column = merge.min_row, merge.min_col
        if top_row > len(flags) or top_column > len(flags[top_row - 1]):
            continue
        top = values[top_row - 1][top_column - 1]
        for row_index in range(top_row, min(merge.max_row, len(flags)) + 1):
            marks = flags[row_index - 1]
            for column in range(top_column, min(merge.max_col, len(marks)) + 1):
                if row_index == top_row and column == top_column:
                    continue
                marks[column - 1] = True
                values[row_index - 1][column - 1] = top
    return _Grid(
        values=values,
        flags=flags,
        rows_total=int(worksheet.max_row or len(values)),
        columns_total=int(worksheet.max_column or max((len(row) for row in values), default=0)),
        truncated=truncated,
    )


def load_xlsx(
    file_path: str | Path,
    *,
    display_name: str | None = None,
    max_sheets: int = MAX_SHEETS_PER_WORKBOOK,
    max_rows: int = MAX_ROWS_PER_SHEET,
    max_columns: int = MAX_COLUMNS_PER_SHEET,
    max_chars: int = MAX_SPREADSHEET_CHARS,
    time_budget_s: float = SPREADSHEET_TIME_BUDGET_SECONDS,
) -> Spreadsheet:
    """一枚 .xlsx -> 每张 sheet 一枚带锚点块（判据③：多 sheet 各自成段，表名进锚点）。

    打开方式实测过：`data_only=True` 要的是公式的**缓存值**而不是公式文本（与
    `app/tools/excel.py:44` 同一档），且**不能** `read_only=True`——那一档下
    `ws.merged_cells` 根本不存在，合并单元格就只能靠"None 猜"，正是判据③禁的第②套口径。
    隐藏的 sheet 一并入库（客户藏起来的通常是排版而不是废话），但 `SheetReport.state`
    记成 hidden，回执里看得见；chartsheet 之类没有单元格网格的页不参与，只计入
    `skipped_sheets`。
    """
    import openpyxl

    path = Path(file_path)
    started = time.monotonic()
    base = _anchor_base(display_name, path)
    book = openpyxl.load_workbook(str(path), data_only=True)
    worksheets = list(book.worksheets)
    sheets_in_book = len(getattr(book, "sheets", worksheets) or worksheets)
    reports: list[SheetReport] = []
    blocks: list[TableBlock] = []
    used = 0
    truncated = ""
    try:
        for index, worksheet in enumerate(worksheets, 1):
            if len(reports) >= max_sheets:
                truncated = truncated or f"sheets:{len(reports)}of{len(worksheets)}"
                break
            if time.monotonic() - started > time_budget_s:
                truncated = truncated or f"time:{len(reports)}of{len(worksheets)}"
                break
            label = _sheet_label(worksheet.title)
            grid = _xlsx_grid(worksheet, label=label, max_rows=max_rows, max_columns=max_columns)
            # 序号按**发出去的块**数，不按 sheet 位置（与 R300 的 pdf 那一路同法）：一张空
            # sheet 不占号，否则锚点会印出"表2"而库里根本没有"表1"。
            block, report = _emit(
                grid,
                label=label,
                anchor_name=f"{base}{ANCHOR_JOIN}Sheet「{label}」",
                ordinal=str(len(blocks) + 1),
                source="xlsx",
                index=index,
                remaining=max_chars - used,
                max_columns=max_columns,
                state=str(getattr(worksheet, "sheet_state", "visible") or "visible"),
            )
            truncated = truncated or report.truncated
            if block is not None:
                blocks.append(block)
                used += block.char_count
            reports.append(report)
    finally:
        book.close()
    result = Spreadsheet(
        filename=base,
        source="xlsx",
        blocks=tuple(blocks),
        sheets=tuple(reports),
        truncated=truncated,
        skipped_sheets=max(sheets_in_book - len(worksheets), 0),
        elapsed_s=time.monotonic() - started,
    )
    logger.info(f"R305 表格入库 xlsx: {result.summary()}")
    return result


def load_spreadsheet(file_path: str | Path, **limits: object) -> Spreadsheet:
    """按后缀分派，姿态与 `tables.extract_tables()` 一致：认不出的东西必须出声。"""
    suffix = Path(file_path).suffix.lower()
    if suffix in CSV_SUFFIXES:
        return load_csv(file_path, **limits)
    if suffix in XLSX_SUFFIXES:
        return load_xlsx(file_path, **limits)
    if suffix in UNSUPPORTED_SUFFIXES:
        raise ValueError(
            f"R305 表格入库不支持 {suffix}：openpyxl 读不了旧二进制格式，仓库直接依赖里没有 xlrd"
        )
    raise ValueError(f"R305 表格入库不支持该格式: {suffix or file_path}")


def load_spreadsheet_text(file_path: str | Path, **limits: object) -> str:
    """`load_document()` 缺的那一行该调这里：进路径，出一段已过 R130 闸门的文本。"""
    return load_spreadsheet(file_path, **limits).text
