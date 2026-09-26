"""
Day 7-8: Excel 数据处理
优化 #4 CSV编码, #5 大文件, #6 合并单元格, #1 Excel画像, #2 pandas纠错, #22 沙箱
"""
import ast
import os
import io
import importlib.util
import pandas as pd
import openpyxl
from typing import Any
from app.agents.contracts import ErrorEnvelope
from app.common.logger import logger

# ==================== 收口名单 <-> 读引擎 (R336) ====================
#: 单一事实源: 一枚扩展名 -> 本机读它所用的引擎模块名; None = pandas 内置通道, 不需要额外的包。
#: 「平台收哪个后缀」与「用什么读它」必须写在同一行。下一位往这张表里塞 .ods / .numbers 而忘了带
#: 引擎, `unavailable_read_engines()` 现读 `importlib.util.find_spec` 就会当场咬人
#: (尺子与两把反证见 tests/test_r336_read_engine_backs_the_whitelist.py)。结论不许写成常量。
DATA_READ_ENGINES: dict[str, str | None] = {
    ".csv": None,
    ".xlsx": "openpyxl",
}

#: 客户仍然会递上来、但本系统明确不读的后缀: 具名拒绝 + 员工照着做得下去的下一步。
#: `.xls` (Excel 97-2003) 要 xlrd 才读得动, 而 xlrd 不在依赖里 (`pyproject.toml` 只有 openpyxl):
#: 旧实现那句 `engine = "openpyxl" if ext == ".xlsx" else "xlrd"` 是一条必然失败的 import,
#: 而更早一步的 `_fill_merged_cells` 会让 openpyxl 先抛 InvalidFileException, 一路穿到路由变成 500。
#: R336 裁定走「诚实拒绝」这一支, 不新增依赖; 「要不要真支持 2003 老格式」已进业主待裁清单。
#: 将来要翻案, 只需把 .xls 从这张表搬进 `DATA_READ_ENGINES` (值写 xlrd) 并装上依赖, 别处一个字不用改。
REFUSED_DATA_FILE_READS: dict[str, str] = {
    ".xls": (
        "请在 Excel 或 WPS 里打开它，选「另存为」，把保存类型改成「Excel 工作表 (*.xlsx)」"
        "或「CSV (逗号分隔) (*.csv)」，再上传另存出来的那一份。文件名和表格里的内容都不用改。"
    ),
}


class UnsupportedDataFile(ValueError):
    """这一枚后缀在本机没有可用的读引擎: 一句具名拒绝, 不是一条运行时崩溃。

    `code` 复用 app/agents/contracts.py::ErrorEnvelope.code 里已有的 `unsupported_file`
    (app/api/v1/chat.py 的文档上传闸今天吐的就是这一枚), R336 零新增错误码。
    `str(exc)` 是给员工看的那句话: 先告诉他下一步做什么, 再说不支持的是哪个格式。
    """

    code = "unsupported_file"

    def __init__(self, filename: str, extension: str, message: str) -> None:
        super().__init__(message)
        self.filename = filename
        self.extension = extension


def extension_of(name_or_path: str) -> str:
    """小写后缀; 没有后缀回空串。收口名单与读引擎问的都是这一个值。"""
    return os.path.splitext(str(name_or_path))[-1].lower()


def engine_for(extension: str) -> str | None:
    """这张后缀声明用哪个引擎读; 不在名单里回 None (不是「换个默认引擎试试」)。"""
    return DATA_READ_ENGINES.get(extension)


def engine_is_importable(engine: str | None) -> bool:
    """None = pandas 内置通道 (CSV), 恒可用; 其余一律现读 find_spec, 不缓存、不写死。"""
    if engine is None:
        return True
    try:
        return importlib.util.find_spec(engine) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def unavailable_read_engines(table: dict[str, str | None] | None = None) -> dict[str, str]:
    """通用尺子: 名单里每一枚扩展名, 它的引擎在本机 import 得到吗。回量坏的那些。

    空 dict = 白名单每一格脚下都有引擎。非空 = 有人在名单里挂了一枚读不动的格式:
    要么补依赖, 要么把这一格搬去 `REFUSED_DATA_FILE_READS`, 不许留在收口名单里。
    """
    declared = DATA_READ_ENGINES if table is None else table
    return {
        ext: engine
        for ext, engine in declared.items()
        if engine is not None and not engine_is_importable(engine)
    }


def accepted_data_file_extensions() -> frozenset[str]:
    """对外收口名单 = 引擎声明表的键, 现算。第二份手抄的扩展名清单正是本单的病灶。"""
    return frozenset(DATA_READ_ENGINES)


def refuse_data_file(name_or_path: str) -> UnsupportedDataFile | None:
    """这一份能不能读: 能读回 None, 不能读回一枚话已经说好的拒绝 (调用方决定 raise 还是转 400)。

    三种「不能读」各有各的实话, 不许糊成一句 unsupported file type:
      1) 明确不做的格式 (.xls) -> 另存为什么、在哪一步点;
      2) 名单里根本没有的后缀 -> 把名单现算给他看;
      3) 名单里有、引擎却装不上 -> 这是服务器的锅, 说清楚, 并给一条今天就走得通的退路。
    """
    filename = os.path.basename(str(name_or_path))
    ext = extension_of(name_or_path)

    if ext in REFUSED_DATA_FILE_READS:
        return UnsupportedDataFile(
            filename,
            ext,
            "「{0}」是 {1} 老格式，本系统不读它。{2}".format(filename, ext, REFUSED_DATA_FILE_READS[ext]),
        )

    if ext not in DATA_READ_ENGINES:
        return UnsupportedDataFile(
            filename,
            ext,
            "「{0}」不是本系统能读的数据文件{1}。数据分析只收 {2}，请在 Excel 或 WPS 里把表格"
            "「另存为 *.xlsx」或 CSV 之后再上传。".format(
                filename,
                "" if ext else " (没有文件后缀)",
                " / ".join(
                    "「{0}」".format(item) for item in sorted(accepted_data_file_extensions())
                ),
            ),
        )

    engine = DATA_READ_ENGINES[ext]
    if not engine_is_importable(engine):
        return UnsupportedDataFile(
            filename,
            ext,
            "「{0}」这一份文件本身没问题，但这台服务器上缺读 {1} 所需的组件 ({2})，所以本系统读不了它。"
            "请先在 Excel 或 WPS 里把它「另存为 *.csv」再上传，并把这一句转给管理员补组件。".format(
                filename, ext, engine
            ),
        )

    return None


def ensure_data_file_readable(name_or_path: str) -> None:
    """收口名单之外的文件在这里点名拒绝, 早于任何一次磁盘读。"""
    refusal = refuse_data_file(name_or_path)
    if refusal is not None:
        raise refusal

# ==================== 编码检测 (#4) ====================

ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]


def _detect_encoding(file_path: str) -> str:
    """依次尝试编码，返回第一个成功的"""
    for enc in ENCODINGS:
        try:
            with open(file_path, "r", encoding=enc) as f:
                f.read(4096)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return "latin-1"  # 兜底


def read_csv(file_path: str) -> pd.DataFrame:
    """读 CSV，自动检测编码"""
    enc = _detect_encoding(file_path)
    logger.info(f"CSV 编码检测: {enc} ({file_path})")
    return pd.read_csv(file_path, encoding=enc)

# ==================== 合并单元格填充 (#6) ====================

def _fill_merged_cells(file_path: str) -> pd.DataFrame:
    """
    检测并填充合并单元格。
    openpyxl 读取 → 原地展开合并区域的值 → 转为 DataFrame
    """
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active

    merged_ranges = list(ws.merged_cells.ranges)
    if not merged_ranges:
        wb.close()
        return None  # 无合并单元格，走正常 pandas 读取

    logger.info(f"检测到 {len(merged_ranges)} 个合并单元格区域，自动填充")

    # 转为二维列表
    data = [[ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
            for r in range(1, ws.max_row + 1)]

    # 填充合并单元格：左上角值覆盖整个区域
    for mr in merged_ranges:
        val = ws.cell(row=mr.min_row, column=mr.min_col).value
        for r in range(mr.min_row, mr.max_row + 1):
            for c in range(mr.min_col, mr.max_col + 1):
                data[r - 1][c - 1] = val

    wb.close()

    if not data or not data[0]:
        return pd.DataFrame()

    columns = data[0]
    df = pd.DataFrame(data[1:], columns=columns)
    df.dropna(how="all", inplace=True)
    return df

# ==================== 文件加载 ====================

def load_excel(file_path: str) -> pd.DataFrame:
    """统一入口：自动识别收口名单里的格式，处理合并单元格。

    R336：进门先问「这一枚后缀在本机真有读引擎吗」，拒绝发生在任何一次磁盘读之前。
    旧实现把答案押在 `engine = "openpyxl" if ext == ".xlsx" else "xlrd"` 上，而 xlrd 从来
    不在依赖里：客户传一份真 .xls 上来，收到的是一条运行时 import 失败（更早一步还会先在
    openpyxl 的 InvalidFileException 上炸开），不是一句「请另存为 .xlsx」。
    """
    ensure_data_file_readable(file_path)
    ext = extension_of(file_path)

    # 走哪条腿由那张声明表决定，不由读腿里再抄一份后缀判断决定：
    # 引擎写着 None = pandas 内置通道（今天只有 .csv），其余一律 engine_for(ext) 交给 pandas。
    # 上一版这里写的是 `if ext == ".csv"` 加一句 `else "xlrd"`，两处手抄各错一半。
    if engine_for(ext) is None:
        return read_csv(file_path)

    # 收口名单里剩下的表格格式（今天只有 .xlsx），引擎名从 DATA_READ_ENGINES 现取
    df = _fill_merged_cells(file_path)
    if df is None:
        df = pd.read_excel(file_path, engine=engine_for(ext))

    # 清理：删全空行/列
    df.dropna(how="all", inplace=True)
    df.dropna(axis=1, how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)

    return df

# ==================== Excel 数据画像 (#1) ====================

def _is_text_series(series: pd.Series) -> bool:
    """文本列的语义判定：只问 pandas.api.types 这一族谓词，不和字面 dtype 串比较。

    R182：pandas 3 起字符串列的 dtype 是 `str`，旧实现那一支比的是字面「object」，
    真机数据上基本进不去 —— text_columns 常年为空、每列「多少个不同取值」永远不发，
    数据面板等于对客户说「这台机器上没有文本列」。判类别要判语义，不判 dtype 的写法：
    - is_string_dtype 收 str / string，也收装着字符串的 object 列与 category 列；
    - is_object_dtype 再兜住混装列（字符串与数字同列）与全空的 object 列 —— 旧实现
      把它们算作文本列，不收进来就等于让这批列从两份名单里一起消失（假干净）；
    - 数值（含 bool）先出局：一列同时进 numeric 与 text 两份名单，等于对同一列说两次谎。
    日期与时间差不归这两份名单里的任何一份，维持原样。
    """
    if pd.api.types.is_numeric_dtype(series):
        return False
    return bool(pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series))


def select_text_columns(frame: pd.DataFrame) -> list:
    """一帧里文本列的名单 —— 判定复用 `_is_text_series`，本函数不另立第二份谓词。

    R185 把这格口径公开成出口：`app/agents/tools.py` 的 analyze_data 那条腿原先自己写了一份
    `select_dtypes`，只按字面 dtype 串「object」判定；它今天全凭 pandas 3 那条声明要移除的兼容通道
    才勉强捞到 `str` 列（每调一次发一枚 Pandas4Warning），而 `string` / `category` 两族当场漏掉。
    兼容通道一撤，这份名单就从「勉强对」滑成「恒空」，「哪个/谁最XX」那一支随之饿死。

    返回原始列标签而不是 `str(col)`：画像里的 `text_columns` 是给人看的显示名，这一份是要拿去
    `frame[col]` 取数的键，两者同源于同一个谓词，但不能互相顶替。
    """
    return [column for column in frame.columns if _is_text_series(frame[column])]


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """
    生成数据画像：
    - 行列数、列名、类型
    - 数值列统计（均值/最大/最小/缺失）
    - 文本列唯一值数量

    「有列无行」是一张合法的空表画像，不是一条错误。只交了表头的 CSV/Excel 在 pandas 里
    恰好 df.empty 为真，旧实现把它和「真的什么都没解析出来」一起塞进 `{"error": ...}`，
    前端 `v-if="profile"` 判真之后去读 profile.columns.length，上传空表就当场抛。
    现在：空表交回形状完整的画像并带 empty 标记；只有零列才走错误形状，
    错误走既有信封 ErrorEnvelope 与既有稳定码（app/agents/contracts.py）。
    契约与空列口径钉在 tests/test_r170_header_only_dataframe_profile.py。
    """
    row_count = int(len(df))
    column_names = list(df.columns)
    if not column_names:
        return _profile_failure(
            "parse_failed",
            "这份文件没有解析出任何列，无法生成数据画像；请确认文件里有表头行。",
        )

    profile = {
        "rows": row_count,
        "columns": len(column_names),
        "column_count": len(column_names),
        # 0 行不等于统计失败：这是一张开张空表，标记让读的人和界面分得清这两种「空」。
        "empty": row_count == 0,
    }

    cols_info = []
    numeric_names: list[str] = []
    text_names: list[str] = []
    for col in column_names:
        series = df[col]
        dtype = str(series.dtype)
        missing = int(series.isna().sum())
        missing_pct = round(missing / max(row_count, 1) * 100, 1)
        is_numeric = bool(pd.api.types.is_numeric_dtype(series))
        # 一次判定两处共用：汇总名单与逐列统计键必须由同一个布尔派生，否则两份名单各说各话。
        is_text = _is_text_series(series)

        # 分类按语义谓词走，不按「统计键在不在」走：空表不发统计量，后者会把 float 列说成文本列。
        if is_numeric:
            numeric_names.append(str(col))
        elif is_text:
            text_names.append(str(col))

        info = {
            "name": str(col),
            "dtype": dtype,
            "missing": missing,
            "missing_pct": missing_pct,
        }

        if row_count == 0:
            # 空列的口径，定死不许留白：一个单元格都没有 => missing 0 / missing_pct 0.0；
            # 一个取值都没有 => 唯一值 0 个。数值列不发 min/max/mean/sum —— 0 行的均值不是
            # 一个数，写 0 会把「没有数据」说成「数据是 0」，写 None 会让界面印出「最小 null」。
            info["unique_values"] = 0

        # 数值列
        elif is_numeric:
            info["min"] = _safe_float(series.min())
            info["max"] = _safe_float(series.max())
            info["mean"] = _safe_float(series.mean())
            info["sum"] = _safe_float(series.sum())

        # 文本列
        elif is_text:
            info["unique_values"] = int(series.nunique())

        cols_info.append(info)

    profile["columns"] = cols_info

    # 摘要
    profile["numeric_columns"] = numeric_names
    profile["text_columns"] = text_names
    profile["total_missing"] = int(df.isna().sum().sum())

    # 行数抽样提示 (#5)
    if row_count > 10000:
        profile["warning"] = f"文件较大 ({row_count} 行)，建议抽样分析。统计信息基于全量数据。"

    return profile


def _profile_failure(code: str, message: str) -> dict[str, Any]:
    """画像层的错误形状：只有既有信封，不新造字段与裸码。

    键名 error 是这里本来就在用的那一个，换掉的只是它的值：从「人读得懂、机器读不懂」的裸中文
    换成 app/agents/contracts.py::ErrorEnvelope，码名走封闭枚举，前端 lib/errcodes.js 才有归一的地方。
    除它以外一个键都不给，免得错误形状长得像画像。
    """
    envelope = ErrorEnvelope(code=code, message=message, retryable=False)
    return {"error": envelope.model_dump()}


def _safe_float(val) -> float | None:
    """安全转 float，处理 NaN"""
    try:
        if pd.isna(val):
            return None
        return round(float(val), 2)
    except (ValueError, TypeError):
        return None

# ==================== pandas 纠错 (#2) ====================

# 禁止的危险模块
FORBIDDEN_IMPORTS = {"os", "sys", "subprocess", "shutil", "importlib",
                      "__import__", "eval", "exec", "open", "compile"}


_ALLOWED_QUERY_NAMES = {
    "df",
    "pd",
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "enumerate",
    "filter",
    "float",
    "int",
    "len",
    "list",
    "map",
    "max",
    "min",
    "range",
    "round",
    "set",
    "sorted",
    "str",
    "sum",
    "tuple",
    "type",
    "zip",
    "True",
    "False",
    "None",
}
_ALLOWED_METHODS = {
    "abs", "all", "any", "astype", "between", "count", "describe", "dropna",
    "fillna", "head", "idxmax", "idxmin", "isna", "max", "mean", "median",
    "min", "nunique", "notna", "reset_index", "round", "sort_values", "std",
    "sum", "tail", "to_dict", "var", "groupby", "agg", "items", "value_counts",
}
_ALLOWED_PD_ATTRS = {"isna", "notna", "to_datetime", "to_numeric", "Series", "DataFrame"}


def _validate_query_ast(code: str) -> str | None:
    try:
        tree = ast.parse(code, mode="eval")
    except SyntaxError as exc:
        return f"查询表达式语法错误: {exc.msg}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_QUERY_NAMES:
            return f"禁止使用名称: {node.id}"
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                return "禁止访问私有或内部属性"
            if isinstance(node.value, ast.Name) and node.value.id == "pd":
                if node.attr not in _ALLOWED_PD_ATTRS:
                    return f"禁止使用 pandas 属性: {node.attr}"
            elif node.attr not in _ALLOWED_METHODS and node.attr not in {"loc", "iloc", "columns", "index", "shape", "values", "dtypes"}:
                return f"禁止使用 DataFrame 属性或方法: {node.attr}"
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name) and function.id not in _ALLOWED_QUERY_NAMES:
                return f"禁止调用名称: {function.id}"
            if isinstance(function, ast.Attribute) and function.attr not in _ALLOWED_METHODS and function.attr not in _ALLOWED_PD_ATTRS:
                return f"禁止调用方法: {function.attr}"
        if isinstance(node, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef, ast.Import, ast.ImportFrom,
                             ast.Assign, ast.NamedExpr, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
                             ast.Await, ast.Yield, ast.YieldFrom)):
            return f"禁止使用表达式类型: {type(node).__name__}"
    return None


def safe_query(df: pd.DataFrame, code: str, max_retries: int = 3) -> dict[str, Any]:
    """Execute a single pandas expression after AST allow-list validation."""
    if not isinstance(code, str) or not code.strip():
        return {"error": "查询表达式不能为空", "result": None}

    for forbidden in FORBIDDEN_IMPORTS:
        if forbidden in code:
            return {"error": f"禁止使用 {forbidden}，仅允许 pandas 操作", "result": None}

    last_error = _validate_query_ast(code)
    if last_error:
        return {"error": last_error, "result": None}

    local_vars = {"df": df, "pd": pd}
    last_error = None
    for attempt in range(max_retries):
        try:
            result = eval(code, {"__builtins__": _safe_builtins()}, local_vars)
            if isinstance(result, pd.DataFrame):
                result = result.head(50).to_dict(orient="records")
            elif isinstance(result, pd.Series):
                result = result.to_dict()
            return {"result": result, "error": None}
        except Exception as exc:
            last_error = str(exc)
            logger.warning(f"pandas 查询失败 (第 {attempt + 1}/{max_retries} 次): {last_error}")
            if attempt < max_retries - 1:
                code = _add_hint(code, last_error)
                validation_error = _validate_query_ast(code)
                if validation_error:
                    return {"error": validation_error, "result": None}

    return {"error": f"执行失败 (重试 {max_retries} 次): {last_error}", "result": None}

def _safe_builtins() -> dict:
    """受限的 builtins"""
    allowed = {
        "abs": abs, "all": all, "any": any, "bool": bool,
        "dict": dict, "enumerate": enumerate, "filter": filter,
        "float": float, "int": int, "len": len, "list": list,
        "map": map, "max": max, "min": min, "print": print,
        "range": range, "round": round, "set": set, "slice": slice,
        "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
        "type": type, "zip": zip, "True": True, "False": False,
        "None": None, "Exception": Exception,
    }
    return allowed


def _add_hint(code: str, error: str) -> str:
    """根据错误信息给代码加提示"""
    hint = f"# 上次执行报错: {error}\n# 请修正后重试\n"
    return hint + code

# ==================== 数据合并 + 更新 (#5 多表, #4 数据更新) ====================

def merge_dataframes(dfs: list[pd.DataFrame]) -> pd.DataFrame:
    """多文件结构相同时，自动纵向合并"""
    if len(dfs) <= 1:
        return dfs[0] if dfs else pd.DataFrame()

    base_cols = set(dfs[0].columns)
    for i, df in enumerate(dfs[1:], 2):
        if set(df.columns) != base_cols:
            raise ValueError(f"第 {i} 个文件列名不一致，无法自动合并")

    merged = pd.concat(dfs, ignore_index=True)
    logger.info(f"合并 {len(dfs)} 个文件，共 {len(merged)} 行")
    return merged


def detect_duplicate_columns(new_df: pd.DataFrame, existing_df: pd.DataFrame) -> bool:
    """检测新数据与已有数据是否结构相同（用于判断替换/追加）"""
    return set(new_df.columns) == set(existing_df.columns)
