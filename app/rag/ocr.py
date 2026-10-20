"""R298 · 本地 OCR 通道：pypdfium2 栅格化 + rapidocr_onnxruntime 识别。

私有化部署 = 一台机器一个企业、数据不出客户服务器（AGENTS.md），所以这一格没有第二种
选择：判据② 把引擎钉死成本地 `rapidocr_onnxruntime`（模型随 wheel 分发，尺寸见
``_MODEL_FILE_NAMES`` 的实测值）。本模块**没有任何网络调用**，也不许将来加 —— 一份扫描
件的像素一旦出门上云 OCR，"数据不出客户机器"这条承诺就作废了。

引擎不可用（未安装 / 模型缺失 / 初始化失败）时，这里交出的是**一句写明原因的降级结论**
（``OcrRunOutcome.degradation_note``），不是一个空字符串。判据② 点名禁止的正是"静默返回
空文本冒充成功"：0 字与"识别不出来"在检索面同色，客户看不出少了什么。
"""
from __future__ import annotations

import importlib.util
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium

from app.common.logger import logger

#: 判据②：唯一允许的引擎。换引擎 = 换一句"数据不出客户机器"的口径，不在本单射程内。
OCR_ENGINE_MODULE = "rapidocr_onnxruntime"
OCR_ENGINE_CLASS = "RapidOCR"

#: rapidocr_onnxruntime 1.4.4 随 wheel 分发的三枚 onnx 模型（相对包目录，config.yaml 里
#: 的 Det/Rec/Cls.model_path）。实测尺寸 2026-09-26 本树现取：det 4,745,517 B /
#: rec 10,857,958 B / cls 585,532 B。缺任何一枚 ⇒ 引擎初始化会连不上推理会话，
#: 与其等 onnxruntime 抛一句没有文件名的错，不如在这里点名。
_MODEL_FILE_NAMES = (
    os.path.join("models", "ch_PP-OCRv4_det_infer.onnx"),
    os.path.join("models", "ch_PP-OCRv4_rec_infer.onnx"),
    os.path.join("models", "ch_ppocr_mobile_v2.0_cls_infer.onnx"),
)

# ==================== 逐页状态码 ====================

#: ``OcrPageOutcome.status`` 的取值。``empty`` 与 ``unavailable`` 是两件事：前者是"这页确实
#: 没有字"，后者是"这页根本没跑成识别"。判据② 不许把后者说成前者，loader 的
#: PAGE_SOURCE_OCR_EMPTY / PAGE_SOURCE_OCR_DEGRADED 两态就按这条分界走。
STATUS_RECOGNIZED = "ocr"
STATUS_EMPTY = "empty"
STATUS_UNAVAILABLE = "unavailable"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"

# ==================== 栅格化参数 ====================

#: 判据③：DPI 参数化。200 是 2026-09-26 本机（CPU / onnxruntime，无 GPU）实测出来的，
#: 不是习惯值。fixture = ``tests/fixtures/r298_scanned_pages.pdf``（3 页 A4，位图原生
#: 150 DPI，正文 44 px），逐档现取：
#:   dpi=72  raster=(595,842)   单页 3086/1657/1457 ms
#:   dpi=200 raster=(1653,2339) 单页 3090/2285/2247 ms（同一档第二遍现取 2916/2326/1958）
#:   dpi=300 raster=(2480,3509) 单页 2295/2186/1268 ms
#:   dpi=400 raster=(3306,4678) 单页 1825/1519/1545 ms
#: 引擎自身初始化 0.771-1.112 s（两遍现取），一次性成本，由 get_engine 缓存承担。
#: 四档识别出的文字逐字相同（150 那一档把句号读成逗号，是唯一差异），耗时也不随 DPI 上升
#: —— 因为 rapidocr 的 ``Global.max_side_len=2000`` 会先把长边压回 2000 px：200 DPI 的
#: A4 长边 2339 px 已经越过那条线，再抬 DPI 只是多栅格化一遍然后丢掉。
#: ⇒ 200 = "把引擎要用的像素一次给够"的最低整档；客户机没有 GPU 也照样跑得完。
#: 逐页耗时由 tests/test_r298_real_engine.py 现取打印（门内不钉绝对毫秒，理由见该件 docstring
#: 与 R269 收口那一笔：会浮动的量当了门，就是把假红买进门里）。
DEFAULT_OCR_DPI = 200

#: 运维修调入口（与 app/documents/index_policy.py 的 DOCUMENT_INDEX_MIN_CHARS 同风格）。
#: 不在测试期读取：见 _resolve_dpi 的说明。
OCR_DPI_ENV = "DOCUMENT_OCR_DPI"

#: 实测下限：72 DPI 是本机验证过的最低一档（A4 -> 595x842 px，正文仍可整页读出）。
#: 再往下没有实测凭据，而栅格化是本地唯一能控制输入清晰度的旋钮，所以不给未验证区开门。
MIN_OCR_DPI = 72
#: 上限：600 DPI 时 A4 单页 RGB 栅格约 105 MB（4958x7016x3 B），而 det 之前长边就被压回
#: 2000 px —— 上面那段实测已经说明 300/400 DPI 的像素就有一部分是白栅格的。600 是"再高
#: 只会先把内存花掉再丢掉"的位置，不是识别能力的位置。
MAX_OCR_DPI = 600

#: 单份文件一次最多 OCR 多少页。上传路径是同步的（app/api/v1/chat.py 的
#: ``await asyncio.to_thread(load_document, ...)``），而实测 CPU 单页 200 DPI 均值
#: 2,541 ms（上面那三页的均值，本机现取）：80 页 ≈ 3.4 分钟，再长就是把一次上传变成
#: 一次后台作业 —— 而本单没有作业层可用（禁域里的队列/服务不在射程内）。
#: 超出的页一律记 ``status=STATUS_SKIPPED`` 并写明原因 + WARNING 日志，不静默截断
#: （判据②同源的要求：少了几页要能说出来是哪几页）。
DEFAULT_OCR_MAX_PAGES = 80
OCR_MAX_PAGES_ENV = "DOCUMENT_OCR_MAX_PAGES"

#: 引擎不可用时给下游的一句话。判据⑥的"降级句"就是它，测试按字面钉。
ENGINE_UNAVAILABLE_NOTE = "本地 OCR 引擎不可用，扫描页未识别文字"

_engine_lock = threading.Lock()
_engine_instance: object | None = None
_engine_unavailable_reason: str | None = None


class OcrEngineUnavailable(RuntimeError):
    """引擎起不来，且``str(exc)`` 必须说明是"没装"还是"模型缺失"还是"初始化失败"。"""


@dataclass(frozen=True)
class OcrPageOutcome:
    """一页的 OCR 结论。``ok`` 与 ``text`` 是两件事：认不出字是 ok 且空文本，引擎起不来
    是不 ok 且带原因。"""

    page_number: int  # 1-based，与 PdfExtractionReport 对齐
    ok: bool
    text: str = ""
    status: str = STATUS_RECOGNIZED  # STATUS_* 之一
    reason: str = ""
    raster_size: tuple[int, int] = (0, 0)
    elapsed_ms: float = 0.0


@dataclass(frozen=True)
class OcrRunOutcome:
    """一次"这些页交给 OCR"的总账。``degradation_note`` 非空 = 这一轮有页没拿到文字，
    且每一页为什么没拿到都写在那里。"""

    dpi: int
    engine: str
    outcomes: tuple[OcrPageOutcome, ...]
    available: bool

    @property
    def degraded_pages(self) -> tuple[OcrPageOutcome, ...]:
        return tuple(item for item in self.outcomes if not item.ok)

    @property
    def degradation_note(self) -> str:
        """降级句：没有降级时是空串，有降级时逐页写明原因（判据②⑥）。"""
        if not self.degraded_pages:
            return ""
        pages = "、".join(f"第{item.page_number}页({item.reason})" for item in self.degraded_pages)
        return f"{ENGINE_UNAVAILABLE_NOTE if not self.available else '部分扫描页未能识别文字'}：{pages}"

# ==================== 引擎 ====================


def model_files() -> tuple[Path, ...]:
    """rapidocr 包目录里那三枚模型的绝对路径（解析不出来时返回空元组）。

    只查"在不在"，不查哈希：模型被换过一次版本是配置问题，被删掉才是本单关心的降级。
    """
    try:
        package_dir = Path(importlib.util.find_spec(OCR_ENGINE_MODULE).origin).parent
    except Exception:  # noqa: BLE001 - 找不到包本身就是降级原因，交给调用方说明
        return ()
    return tuple(package_dir / name for name in _MODEL_FILE_NAMES)


def missing_model_files() -> tuple[str, ...]:
    """缺失的模型文件名。空元组 = 三枚都在位。"""
    return tuple(str(path.name) for path in model_files() if not path.is_file())


def unavailable_reason() -> str | None:
    """引擎起不来的原因；``None`` 表示可用。判据②：这句话必须能回答"为什么没识别"。"""
    try:
        spec = importlib.util.find_spec(OCR_ENGINE_MODULE)
    except Exception as exc:  # noqa: BLE001
        return f"{OCR_ENGINE_MODULE} 无法定位：{type(exc).__name__}: {exc}"
    if spec is None:
        return f"{OCR_ENGINE_MODULE} 未安装（import 找不到模块）"
    missing = missing_model_files()
    if missing:
        return f"{OCR_ENGINE_MODULE} 模型文件缺失：{'、'.join(missing)}"
    return None


def get_engine(*, force_new: bool = False):
    """取（并缓存）本地引擎实例。

    缓存不是优化，是必需：onnxruntime 每次建会话都要把那 ~16 MB 模型重读一遍（实测
    初始化 0.4 s+），而上传一份 200 页扫描件会调几百次。

    ``threading.Lock`` 同理：backend / queue_worker / scheduler 三个进程各有一份实例，
    进程内却是多线程共享（上传走 ``asyncio.to_thread``），onnxruntime 的推理会话按
    RapidOCR 自己的用法不算并发安全 —— 一次调用串一页，代价换来的是不会互相踩。
    """
    global _engine_instance, _engine_unavailable_reason
    if _engine_instance is not None and not force_new:
        return _engine_instance
    with _engine_lock:
        if _engine_instance is not None and not force_new:
            return _engine_instance
        reason = unavailable_reason()
        if reason is not None:
            _engine_unavailable_reason = reason
            raise OcrEngineUnavailable(reason)
        try:
            module = importlib.import_module(OCR_ENGINE_MODULE)
            engine = getattr(module, OCR_ENGINE_CLASS)()
        except Exception as exc:  # noqa: BLE001 - 初始化失败一律当降级处理，见模块文档
            _engine_unavailable_reason = (
                f"{OCR_ENGINE_MODULE}.{OCR_ENGINE_CLASS} 初始化失败：{type(exc).__name__}: {exc}"
            )
            raise OcrEngineUnavailable(_engine_unavailable_reason) from exc
        _engine_unavailable_reason = None
        _engine_instance = engine
        return engine


def reset_engine_cache() -> None:
    """丢掉缓存的实例。测试用它切换"引擎可用/被禁用"两态，运行期没人该调它。"""
    global _engine_instance, _engine_unavailable_reason
    with _engine_lock:
        _engine_instance = None
        _engine_unavailable_reason = None


# ==================== 栅格化（判据③：pypdfium2 + 参数化 DPI） ====================


def _resolve_dpi(dpi: int | None) -> int:
    if dpi is None:
        return DEFAULT_OCR_DPI
    dpi = int(dpi)
    if not MIN_OCR_DPI <= dpi <= MAX_OCR_DPI:
        raise ValueError(
            f"OCR DPI 必须落在 {MIN_OCR_DPI}..{MAX_OCR_DPI} 之间，收到 {dpi}"
            f"（下限以下是糊图，上限以上的像素在识别前就被缩放掉了）"
        )
    return dpi


def resolve_dpi(dpi: int | None = None) -> int:
    """调用方显式给的 DPI > 环境变量 > 常量默认。

    环境变量在**调用期**读，不在 import 期读：app 侧多个模块 import 期就固化了配置，
    那正是 conftest 里 R70 那一整段要处理的坑，本模块不再制造第二枚。
    """
    if dpi is not None:
        return _resolve_dpi(dpi)
    raw = (os.getenv(OCR_DPI_ENV) or "").strip()
    if raw:
        try:
            return _resolve_dpi(int(raw))
        except ValueError as exc:
            logger.warning(f"[OCR] 忽略 {OCR_DPI_ENV}={raw!r}：{exc}")
    return DEFAULT_OCR_DPI


def resolve_max_pages(max_pages: int | None = None) -> int:
    if max_pages is not None:
        return max(0, int(max_pages))
    raw = (os.getenv(OCR_MAX_PAGES_ENV) or "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            logger.warning(f"[OCR] 忽略 {OCR_MAX_PAGES_ENV}={raw!r}（不是整数）")
    return DEFAULT_OCR_MAX_PAGES


def rasterize_page(pdf_path: str, page_number: int, *, dpi: int) -> "object":
    """把一页栅格化成 RGB uint8 数组，形状 ``(高, 宽, 3)``。

    一次只开一页的文档句柄由调用方管（见 ``ocr_pages``），这里只负责"页码 -> 像素"。
    用 RGB 而不是灰度：rapidocr 的预处理按三通道走，喂单通道是赌它的兼容分支。

    DPI 在这一层再校一次：`ocr_pages` 已经校过，但直接调本函数的人（脚本、后来的
    运维入口）才是会把 2000 DPI 传进来、当场申请一枚 ~1 GB 栅格的人。
    """
    dpi = _resolve_dpi(dpi)
    with pdfium.PdfDocument(pdf_path) as document:
        if not 1 <= page_number <= len(document):
            raise IndexError(f"页码越界：{page_number}/{len(document)}")
        page = document[page_number - 1]
        bitmap = page.render(scale=dpi / 72.0)
        pil_image = bitmap.to_pil()
    array = _as_rgb_array(pil_image)
    del bitmap, pil_image, page
    return array


def _as_rgb_array(image) -> "object":
    import numpy as np

    array = np.asarray(image)
    if array.ndim == 2:  # 灰度底页（扫描件常见）：补成三通道，别赌引擎兼容分支
        array = np.repeat(array[:, :, None], 3, axis=2)
    elif array.ndim == 3 and array.shape[2] == 4:  # pypdfium2 默认给 BGRA
        array = array[:, :, :3][:, :, ::-1]
    elif array.ndim == 3 and array.shape[2] == 3:  # 已是 RGB
        pass
    else:
        raise ValueError(f"栅格化拿到意外形状 {array.shape}")
    return np.ascontiguousarray(array, dtype="uint8")


def recognize(engine, array) -> tuple[str, float]:
    """一页像素 -> 文字。返回 (文本, 本次识别墙钟耗时 ms)；未检出文字时文本为空串。

    计时用的是本函数自己的墙钟，**不是** rapidocr 返回的 `elapse`：那个只含推理段，
    不含检测/识别前后的预处理，拿它当"客户机单页要等多久"会读小（判据③要的是总账）。

    阅读顺序按检测框左上角 (行, 列) 排：rapidocr 的返回顺序跟检测框生成顺序走，
    不排序会把同一行的两个字块拼颠倒，而正文顺序就是检索命中的顺序。
    """
    started = time.perf_counter()
    result, _elapse = engine(array)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if not result:
        return "", elapsed_ms
    boxes = []
    for entry in result:
        quad, text = entry[0], entry[1]
        if not str(text).strip():
            continue
        top = min(point[1] for point in quad)
        left = min(point[0] for point in quad)
        boxes.append((top, left, str(text).strip()))
    # 同一行的判定用**相对**容差：栅格高度 / 200（A4@200dpi = 2339 px -> 11 px，
    # A4@72dpi = 842 px -> 4 px）。裸写一个像素数会随 DPI 漂，等于把行序判给一个
    # 没人解释过的常数。
    tolerance = max(2.0, float(array.shape[0]) / 200.0)
    boxes.sort(key=lambda item: (round(item[0] / tolerance), item[1]))
    return "\n".join(text for _top, _left, text in boxes), elapsed_ms

# ==================== 一次 OCR 跑批 ====================


def ocr_pages(
    pdf_path: str,
    page_numbers: list[int] | tuple[int, ...],
    *,
    dpi: int | None = None,
    max_pages: int | None = None,
    engine=None,
) -> OcrRunOutcome:
    """识别指定页（1-based 页码）。**永不抛"引擎不可用"**，而是交回一份写明原因的降级账。

    ``engine`` 是测试注入口（假引擎 / 计数用引擎），生产调用一律不传，走缓存的真引擎。
    """
    resolved_dpi = resolve_dpi(dpi)
    pages = sorted({int(page) for page in page_numbers})
    if not pages:
        return OcrRunOutcome(dpi=resolved_dpi, engine=OCR_ENGINE_MODULE, outcomes=(), available=True)

    limit = resolve_max_pages(max_pages)
    if engine is None:
        reason = unavailable_reason()
        if reason is None:
            try:
                engine = get_engine()
            except OcrEngineUnavailable as exc:
                reason = str(exc)
        if reason is not None:
            logger.warning(f"[OCR] 引擎降级：{reason}")
            return OcrRunOutcome(
                dpi=resolved_dpi,
                engine=OCR_ENGINE_MODULE,
                available=False,
                outcomes=tuple(
                    OcrPageOutcome(
                        page_number=page,
                        ok=False,
                        status=STATUS_UNAVAILABLE,
                        reason=reason,
                    )
                    for page in pages
                ),
            )

    outcomes: list[OcrPageOutcome] = []
    for position, page in enumerate(pages):
        if position >= limit:
            # 截断必须留名：这一页不是"没字"，是"这轮没跑"。
            logger.warning(
                f"[OCR] {pdf_path} 第{page}页未识别：超出单次 {OCR_MAX_PAGES_ENV}={limit} 页上限"
            )
            outcomes.append(
                OcrPageOutcome(
                    page_number=page,
                    ok=False,
                    status=STATUS_SKIPPED,
                    reason=f"超出单次 OCR 页数上限 {limit}",
                )
            )
            continue
        started = time.perf_counter()
        try:
            array = rasterize_page(pdf_path, page, dpi=resolved_dpi)
        except Exception as exc:  # noqa: BLE001 - 单页栅格化失败不能带走整份文档
            logger.warning(f"[OCR] 第{page}页栅格化失败：{type(exc).__name__}: {exc}")
            outcomes.append(
                OcrPageOutcome(
                    page_number=page,
                    ok=False,
                    status=STATUS_FAILED,
                    reason=f"栅格化失败 {type(exc).__name__}",
                    elapsed_ms=(time.perf_counter() - started) * 1000.0,
                )
            )
            continue
        height, width = int(array.shape[0]), int(array.shape[1])
        try:
            text, engine_ms = recognize(engine, array)
        except Exception as exc:  # noqa: BLE001 - 引擎中途炸了同样逐页记账
            logger.warning(f"[OCR] 第{page}页识别失败：{type(exc).__name__}: {exc}")
            outcomes.append(
                OcrPageOutcome(
                    page_number=page,
                    ok=False,
                    status=STATUS_FAILED,
                    reason=f"识别失败 {type(exc).__name__}",
                    raster_size=(width, height),
                    elapsed_ms=(time.perf_counter() - started) * 1000.0,
                )
            )
            continue
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if not text:
            # 认得出图、图里确实没字：这是合法的 OCR 结果，不是降级，不写原因句。
            outcomes.append(
                OcrPageOutcome(
                    page_number=page,
                    ok=True,
                    status=STATUS_EMPTY,
                    text="",
                    raster_size=(width, height),
                    elapsed_ms=elapsed_ms,
                )
            )
            continue
        outcomes.append(
            OcrPageOutcome(
                page_number=page,
                ok=True,
                status=STATUS_RECOGNIZED,
                text=text,
                raster_size=(width, height),
                elapsed_ms=elapsed_ms,
            )
        )
    return OcrRunOutcome(
        dpi=resolved_dpi,
        engine=OCR_ENGINE_MODULE,
        outcomes=tuple(outcomes),
        available=True,
    )


__all__ = [
    "DEFAULT_OCR_DPI",
    "DEFAULT_OCR_MAX_PAGES",
    "ENGINE_UNAVAILABLE_NOTE",
    "MAX_OCR_DPI",
    "MIN_OCR_DPI",
    "OCR_DPI_ENV",
    "OCR_ENGINE_CLASS",
    "OCR_ENGINE_MODULE",
    "OCR_MAX_PAGES_ENV",
    "OcrEngineUnavailable",
    "STATUS_EMPTY",
    "STATUS_FAILED",
    "STATUS_RECOGNIZED",
    "STATUS_SKIPPED",
    "STATUS_UNAVAILABLE",
    "OcrPageOutcome",
    "OcrRunOutcome",
    "get_engine",
    "missing_model_files",
    "model_files",
    "ocr_pages",
    "rasterize_page",
    "recognize",
    "reset_engine_cache",
    "resolve_dpi",
    "resolve_max_pages",
    "unavailable_reason",
]