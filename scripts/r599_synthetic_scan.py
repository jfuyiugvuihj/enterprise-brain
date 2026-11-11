# -*- coding: utf-8 -*-
"""R599 · 合成扫描件发生器：V2 #13「一份真扫描件跑通一次并留读数」按业主令（10-03）造的那份件。

形状要求（判据①）：A4、逐页**只有一张位图、零文本层**，位图里印中文假公文/说明书句子。

🔴 位图里**不许有任何统计数字或假指标** —— 这条是 R148 那笔换图事故订下来的铁规（旧图把
假统计烤死在像素里，客户一装机就当场被抓）。本件用三把独立的尺守这一格，逐枚可核对：
 ① **源句尺**（出件之前就拦）：``PAGE_SPECS`` 每一行都不许含 ASCII 数字、不许含中文数字
    字符、不许含 ``METRIC_TOKENS`` 点名的指标词；``assert_no_statistics_in_the_pixels()``
    命中任何一枚即 ``SystemExit``，压根不出件。常驻钉 ``tests/test_r599_synthetic_scan.py``
    逐枚复述这三把尺（不依赖 OCR、不依赖模型、不依赖字体）。
 ② **语法尺**（出件之后独立复量）：直接用 pypdf 读每页 ``/Contents`` 解压出来的绘制算子，
    断言 ``BT`` / ``Tj`` 零命中且 ``extract_text()`` 交回空串 ⇒ 位图之外根本没有第二套字
    可以藏数字。这一把不借 ``app/`` 的判断，两把尺各测各的。
 ③ **目视尺**：像素里到底有什么字，由真打一次在册 OCR 通道复述（读数见
    ``docs/perf/r599-synthetic-scan-2026-10-03.md``，跑法 ``scripts/r599_readout.py``）。

🔴 折行这一格是本班自己踩出来的（首版 15:52 那份件的句尾**根本没进像素**）：
A4 位图宽 1240 px、左边距 99 px，四十四号字一句三十四字就 ~1496 px，超出画布的部分被
**静默裁掉**，真打 OCR 读回来的是「超标部分」这种半句话——那既不是识别失败，也不是假指标，
而是样本自己缺字。``fit_lines()`` 因此成为出件的硬前置：句子按画布可用宽度折行
（拉丁词优先在空格处断，中文逐字断），**折完仍画不下的行直接 ``SystemExit``**，垂直方向越过
下边距同样拒绝。宁可不出件，也不出一枚"读数对不上正文"的件。

与 ``scripts/r540_samples.py`` 的分工（AGENTS.md「不复制一套平行实现」）：那枚发生器把样本
一律落**仓外 tmp**，本件要的恰恰是一份**进仓、有 sha256 账**的凭据件；渲染把手
（``render_text_image`` / ``blank_image``）与手写最小 PDF 把手（``build_pdf``）直接复用
那枚在册脚本，本文件不重写第二套。

落点铁规（判据③）：产物只许写 ``docs/testing/fixtures/r599-scan-demo.pdf``。
**绝不写 ``documents/**``** —— 语料零变化是铁规，这份件一旦进语料就打穿 P-17 哨兵与
全部历史窗口的可比性；``--out`` 指到 ``documents/`` / ``data/`` / ``chroma_db/`` 之下
会被 ``refuse_forbidden_targets`` 当场拒绝。本件也不落库、不建索引、不发向量。

可复算性的边界（如实写明）：位图由本机字体（``msyh.ttc`` 等）渲染，换一台机器、换一版
字体，像素字节就不同。所以常驻钉钉的是**这份已入库件的 sha256**，不是「重跑一遍必然
逐字节相同」——后者是一枚会随环境浮动的假绿（R269 收口那一笔点名的族）。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 判据① 点名的落点。写域之外一字节不碰。
FIXTURE_RELPATH = Path("docs") / "testing" / "fixtures" / "r599-scan-demo.pdf"

#: 判据③：这些目录之下不接受任何写入（语料/数据/向量库）。
FORBIDDEN_TARGET_ROOTS = ("documents", "data", "chroma_db")

#: 渲染口径（与 r540 把手一致）：左边距 8%、右边留 6% 余量、行距 2.1 倍字号、下边距 8%。
LEFT_MARGIN_RATIO = 0.08
RIGHT_MARGIN_RATIO = 0.06
TOP_MARGIN_RATIO = 0.12
BOTTOM_MARGIN_RATIO = 0.08
LINE_HEIGHT_RATIO = 2.1
DEFAULT_FONT_SIZE = 44

# ==================== ① 源句尺：三把禁尺 ====================

ASCII_DIGIT_RE = re.compile(r"[0-9]")

#: 中文数字字符：本件的正文刻意做到一枚都不出现，这样「位图里没有数字」是一句可以机械
#: 复核的话，而不是一句「我看过，像没有」的目测结论。
CJK_NUMERAL_CHARS = "〇一二三四五六七八九十百千万亿两零"

#: 假指标最常披的几件外衣。命中即拒，哪怕句子里没有阿拉伯数字。
METRIC_TOKENS = (
    "%",
    "％",
    "百分之",
    "元",
    "万元",
    "亿",
    "倍",
    "同比",
    "环比",
    "增长率",
    "占比",
    "达成率",
    "得分",
    "排名",
    "均值",
    "指标",
    "统计",
)

#: 折行时的词形：拉丁词/数字串连着其后的空白当一个 token，中文逐字，标点随字。
_TOKEN_RE = re.compile(r"[A-Za-z0-9@_.:/&%-]+\s*|\s+|.")

# ==================== 页面内容（假公文/说明书，零数字、零指标） ====================

PAGE_SPECS: tuple[dict, ...] = (
    {
        "role": "正文页：假会议纪要（大字标题 + 三行段落）",
        "style": {},
        "lines": [
            "内部管理制度宣贯会纪要",
            "会议明确，差旅住宿标准按照集团现行制度执行，超标部分须事前书面报批。",
            "会议指出，各所属单位应当如实记录资金使用情况，并按月报送综合办公室。",
            "会议强调，档案管理遵循谁形成、谁整理、谁负责的原则。",
        ],
    },
    {
        "role": "中英混排页：假机房管理办法",
        "style": {},
        "lines": [
            "机房出入管理办法",
            "进入机房须佩戴工牌并由值班人员陪同，严禁单独作业。",
            "Server room access requires a badge and a companion at all times.",
            "值班人员应当如实填写交接班记录并留存备查。",
        ],
    },
    {
        "role": "低质量页：小字 + 轻模糊 + 噪点，模拟二次复印出来的扫描件",
        "style": {"size": 34, "blur": 1.6, "gray": 0.8, "noise": 10, "seed": 20261003},
        "lines": [
            "库房巡检记录填写说明",
            "巡检人员应当当场填写巡检记录，不得事后补记或者代签。",
            "发现渗漏、异味或设备异响时，立即上报安全管理部门并留存现场。",
        ],
    },
    {
        "role": "有图无字页：空白表单区，判据② 的 ocr-empty 形状（真扫描件里常见）",
        "no_glyphs": True,
        "style": {},
        "lines": [],
    },
)


def page_lines() -> list[str]:
    """所有页要印进像素的**源句**（第 ① 把尺的测量对象；折行后的视觉行不算新句）。"""
    return [line for spec in PAGE_SPECS for line in spec["lines"]]


def statistics_offenders(lines: Sequence[str] | None = None) -> list[str]:
    """逐枚点名哪些句子踩了哪把尺；空列表 = 三把尺全过。"""
    offenders: list[str] = []
    for line in (page_lines() if lines is None else lines):
        if ASCII_DIGIT_RE.search(line):
            offenders.append(f"含 ASCII 数字：{line}")
        numeral = next((ch for ch in line if ch in CJK_NUMERAL_CHARS), None)
        if numeral is not None:
            offenders.append(f"含中文数字「{numeral}」：{line}")
        token = next((item for item in METRIC_TOKENS if item in line), None)
        if token is not None:
            offenders.append(f"含指标词「{token}」：{line}")
    return offenders


def assert_no_statistics_in_the_pixels(lines: Sequence[str] | None = None) -> None:
    """R148 铁规的执行点：踩尺的句子一个都不许进像素，出件之前先拦。"""
    offenders = statistics_offenders(lines)
    if offenders:
        raise SystemExit(
            "🔴 R148 铁规：位图里不许有统计数字或假指标 —— " + "；".join(offenders)
        )


# ==================== 在册把手：渲染 + 手写最小 PDF（复用 r540，不另造） ====================


def samples():
    """载入 ``scripts/r540_samples.py``（只读它，不改它一字节）。"""
    path = REPO_ROOT / "scripts" / "r540_samples.py"
    spec = importlib.util.spec_from_file_location("r540_samples", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"载入在册样本把手失败：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def refuse_forbidden_targets(path: Path) -> None:
    resolved = Path(path).resolve()
    for name in FORBIDDEN_TARGET_ROOTS:
        root = (REPO_ROOT / name).resolve()
        if root == resolved or root in resolved.parents:
            raise SystemExit(
                f"判据③ 铁规：本件不许写 {name}/**（语料零变化，且会打穿 P-17 哨兵），拒绝 {resolved}"
            )


# ==================== 折行：句尾不许被画布裁掉 ====================


def _token_widths(draw, text: str, font) -> float:
    return float(draw.textlength(text, font=font))


def fit_lines(lines: Sequence[str], *, size: int, hand) -> dict:
    """把源句折成画布放得下的视觉行，并交回几何账（宽度、行数、是否越过下边距）。

    画不下的句子**不是警告而是拒绝出件**：首版就是靠这句才被抓到的——超宽部分被 PIL 静默
    裁掉，OCR 读回半句话，样本自己缺字却装作"识别质量不行"。
    """
    from PIL import Image, ImageDraw

    canvas_width, canvas_height = hand.RASTER_SIZE
    left = int(canvas_width * LEFT_MARGIN_RATIO)
    limit = canvas_width - left - int(canvas_width * RIGHT_MARGIN_RATIO)
    font = hand._cjk_font(size)
    draw = ImageDraw.Draw(Image.new("L", (8, 8)))

    wrapped: list[str] = []
    widths: list[float] = []
    for line in lines:
        flat = line.strip()
        if not flat:
            continue
        if _token_widths(draw, flat, font) <= limit:
            wrapped.append(flat)
            widths.append(_token_widths(draw, flat, font))
            continue
        current = ""
        for token in _TOKEN_RE.findall(flat):
            candidate = current + token
            if current and _token_widths(draw, candidate.rstrip(), font) > limit:
                wrapped.append(current.rstrip())
                widths.append(_token_widths(draw, current.rstrip(), font))
                current = token.strip() if token.strip() else ""
            else:
                current = candidate
        if current.strip():
            wrapped.append(current.strip())
            widths.append(_token_widths(draw, current.strip(), font))

    overflow = [text for text, width in zip(wrapped, widths) if width > limit]
    if overflow:
        raise SystemExit(
            f"🔴 折行之后仍有 {len(overflow)} 枚视觉行宽 {max(widths):.0f}px 超出画布可用宽度 "
            f"{limit}px，句尾会被静默裁掉，拒绝出件：" + "；".join(overflow)
        )
    line_height = int(size * LINE_HEIGHT_RATIO)
    bottom_margin = int(canvas_height * (1.0 - BOTTOM_MARGIN_RATIO))
    if lines:
        last_line_bottom = int(canvas_height * TOP_MARGIN_RATIO) + line_height * len(wrapped)
    else:
        last_line_bottom = 0
    if last_line_bottom > bottom_margin:
        raise SystemExit(
            f"🔴 折行后共 {len(wrapped)} 行，底边到 {last_line_bottom}px，越过下边距 "
            f"{bottom_margin}px，会被静默裁掉，拒绝出件"
        )
    return {
        "size": size,
        "canvas": [canvas_width, canvas_height],
        "left_margin": left,
        "usable_width": limit,
        "source_lines": list(lines),
        "visual_lines": wrapped,
        "visual_line_widths": [round(value, 1) for value in widths],
        "widest_visual_line": round(max(widths), 1) if widths else 0,
        "line_count": len(wrapped),
        "lowest_painted_row": last_line_bottom,
    }


def page_geometry(hand) -> list[dict]:
    """逐页几何账（出件前算一遍、出件后同样口径复述一遍，供纸面核对）。"""
    rows: list[dict] = []
    for index, spec in enumerate(PAGE_SPECS, start=1):
        if spec.get("no_glyphs"):
            rows.append({"page": index, "no_glyphs": True, "line_count": 0})
            continue
        size = int(spec["style"].get("size", DEFAULT_FONT_SIZE))
        rows.append({"page": index, "no_glyphs": False, **fit_lines(spec["lines"], size=size, hand=hand)})
    return rows


# ==================== 出件 ====================


def build_fixture(path: Path) -> dict:
    """造件：每页一张 A4 位图塞进 PDF，不写任何文本层算子。"""
    target = Path(path)
    refuse_forbidden_targets(target)
    assert_no_statistics_in_the_pixels()

    hand = samples()
    geometry = page_geometry(hand)  # 折行不过关在这里就拒绝出件
    pages: list[dict] = []
    for spec in PAGE_SPECS:
        if spec.get("no_glyphs"):
            pages.append({"image": hand.blank_image()})
        else:
            size = int(spec["style"].get("size", DEFAULT_FONT_SIZE))
            visual = fit_lines(spec["lines"], size=size, hand=hand)["visual_lines"]
            pages.append({"image": hand.render_text_image(visual, **spec["style"])})
    hand.build_pdf(target, pages)
    result = account(target)
    result["geometry"] = geometry
    return result


# ==================== ② 语法尺：不借 app/ 的独立复量 ====================


def _raw_page_operators(page) -> str:
    """把这一页的绘制算子解压成文本（pypdf 层，与 loader 的判定彼此独立）。"""
    parts: list[str] = []
    contents = page.get("/Contents")
    if contents is None:
        return ""
    resolved = getattr(contents, "get_object", lambda: contents)()
    refs = resolved if isinstance(resolved, list) else [resolved]
    for ref in refs:
        obj = getattr(ref, "get_object", lambda: ref)()
        data = obj.get_data() if hasattr(obj, "get_data") else bytes(obj)
        parts.append(data.decode("latin-1", "replace"))
    return "\n".join(parts)


def account(path: Path) -> dict:
    """一份件的账：字节 sha256 + 逐页零文本层 + 逐页位图对象 + 逐页算子里有没有 Tj。"""
    from pypdf import PdfReader

    target = Path(path)
    raw = target.read_bytes()
    reader = PdfReader(str(target))
    rows: list[dict] = []
    for index, page in enumerate(reader.pages, start=1):
        layer = (page.extract_text() or "").strip()
        ops = _raw_page_operators(page)
        resources = page.get("/Resources") or {}
        xobjects = (resources.get("/XObject") if hasattr(resources, "get") else None) or {}
        subtypes = sorted(
            {
                str(item.get("/Subtype", "") if hasattr(item, "get") else "")
                for item in (xobjects.values() if hasattr(xobjects, "values") else [])
            }
        )
        rows.append(
            {
                "page": index,
                "text_layer_chars": len("".join(layer.split())),
                "text_layer_sample": layer[:24],
                "draw_operators": {"BT": ops.count("BT"), "Tj": ops.count("Tj")},
                "xobject_subtypes": subtypes,
                "mediabox": [float(value) for value in page.mediabox],
            }
        )
    digest = hashlib.sha256(raw).hexdigest()
    return {
        "path": target.relative_to(REPO_ROOT).as_posix() if _inside_repo(target) else str(target),
        "bytes": len(raw),
        "sha256": digest,
        "sha256_12": digest[:12],
        "page_count": len(rows),
        "zero_text_layer_on_every_page": all(row["text_layer_chars"] == 0 for row in rows),
        "no_text_draw_operator_on_every_page": all(
            row["draw_operators"] == {"BT": 0, "Tj": 0} for row in rows
        ),
        "image_object_on_every_page": all(
            any(sub == "/Image" for sub in row["xobject_subtypes"]) for row in rows
        ),
        "pages": rows,
    }


def _inside_repo(target: Path) -> bool:
    try:
        target.relative_to(REPO_ROOT)
    except ValueError:
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R599 合成扫描件发生器（只写 docs/testing/fixtures/）")
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / FIXTURE_RELPATH),
        help=f"落盘路径，缺省 {FIXTURE_RELPATH.as_posix()}",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="不造件，只对盘上已有的件复量语法尺",
    )
    parser.add_argument(
        "--geometry-only",
        action="store_true",
        help="不落盘，只交回折行与几何账（判据① 的『句尾不许被裁』那一格）",
    )
    args = parser.parse_args(argv)

    target = Path(args.out)
    assert_no_statistics_in_the_pixels()
    result = {
        "tool": "scripts/r599_synthetic_scan.py",
        "mode": "geometry" if args.geometry_only else ("verify" if args.verify_only else "build"),
        "source_line_count": len(page_lines()),
        "statistics_offenders": statistics_offenders(),
    }
    if args.geometry_only:
        result["geometry"] = page_geometry(samples())
    elif args.verify_only:
        if not target.is_file():
            raise SystemExit(f"--verify-only 要的是盘上已有的件，{target} 不存在")
        refuse_forbidden_targets(target)
        result["fixture"] = account(target)
    else:
        result["fixture"] = build_fixture(target)
        result["recheck_after_build"] = account(target)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
