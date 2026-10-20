#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R626 —— 遗留引擎「静默空召回」量具。🔴 只作遗留引擎取证，产品码不得 import 本文件。

它量的是什么（10-04 09:45 总控现取的形状）：同一份 105 题、同一枚 k=5、同一批向量，
PGVector 那一腿 105/105 每问都交回 5 名，遗留引擎那一腿有 21 问交回**空列表**——零报错、
零异常、零警告。归因探针已排掉三种解释：`collection.count()=1008` 数据在；
`get(include=["embeddings"])` 取回 1008 枚 768 维向量且非有限值 0 枚，向量在；把同批向量
原样 `add` 进临时集合后同样的查询立刻返回 5 条，口径在。剩下的只有持久卷里那枚 HNSW 索引
本身，它**静默**把候选交空。

为什么这是一枚量具而不是一条注释：出厂默认仍是遗留件（业主 10-03 裁「默认不翻」），所以没翻
`INDEX_BACKEND` 的客户装机，语义读答复走的就是这条会静默交空的腿。要把它当成客户可见的 P1
证据，就得有一枚**会红**的复跑件，而不是每班手写一遍"有 21 枚空"。

判据（退出码，逐枚有牙，见 tests/test_r626_legacy_silent_empty_teeth.py）：
  0 = 两腿都有命中，且 mean overlap@k 不低于 --min-mean-overlap（缺省 0.0，即只判静默空）
  1 = 🔴 静默空召回：某腿的库容 >= k 却对该题交回空列表 —— 这一枚码只允许由这一族症状发出
  2 = 前置不满足 / 量具自己没跑成（含"腿抛异常"，那是崩溃不是空召回），stderr 首行带前缀
  3 = 没有静默空，但 mean overlap@k 低于给定阈值（差异可判读，不到 P1）
阈值一律走参数：0.7238 那枚今天的读数**不烤进代码**，它属于取证纸不属于量具。

零变异纪律（这单硬要求，不是风格）：
* 绝不对真实卷开 PersistentClient。分清两件事：**复制源可以是现役卷**（`--snapshot-from`
  按字节 copytree 出副本，复制只是读），**打开目标绝不可以是现役卷**（`--chroma-dir` 指到
  仓根/容器根的 chroma_db 当场按前置码拒）。副本落在临时目录，产品客户端只认副本。
* 开库前后各做一次源目录内容清单（逐文件 sha256 折成一枚摘要），不等就按前置不满足收：本次
  不产出任何召回结论。计划书 §9.3 格⑤ 那条"只读打开会不会推进 mtime"至今既未证成也未证否，
  本量具因此不宣称机制，只报读数——它把这件事变成每次复跑都自查的一格。
* PG 腿只发 SELECT，会话在连接那一刻就设成 READ ONLY。

复用不平行：只读连接、集合打开、U1 距离判读、口径核对、语料级差集、题集装载、PG 召回语句全部
走 scripts/compare_vector_recall.py 的现成函数（按路径装载后复用，不抄第二份实现），所以本文件
里一枚 `PersistentClient`、一处 `open_connection`、一条 SQL 都不该出现——那也是在册棘轮
test_r238（裸 connect 全仓 15 枚）与 test_r134（开库收口名册）不许变长的原因。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 在册量具的位置：本文件每一条"怎么连、怎么开库、怎么比口径"都从它那儿读回来。
TOOL_RELATIVE = Path("scripts") / "compare_vector_recall.py"

EXIT_CLEAN = 0
EXIT_SILENT_EMPTY = 1
EXIT_PRECONDITION = 2
EXIT_LOW_OVERLAP = 3
#: 只在"装载在册量具这一步自己失败"时用（那时借不到它的前缀）。牙把它与
#: compare_vector_recall.PRECONDITION_PREFIX 钉成同一串值，谁改了一边就当场红。
PRECONDITION_PREFIX = "[前置不满足] "

LEG_CHROMA = "chroma"
LEG_PG = "pg"

_TOOL_MODULES: dict = {}


def load_recall_tool():
    """按文件路径装载 scripts/compare_vector_recall.py，并缓存这一次装载。

    为什么不 `import compare_vector_recall`：scripts/ 不在包路径里，在册件（test_r269、
    test_r157、test_r120）一律用 `spec_from_file_location` 装载，本文件跟同一个形状，
    免得为了一枚退役量具去动 packaging。
    """
    cached = _TOOL_MODULES.get("tool")
    if cached is not None:
        return cached
    path = ROOT / TOOL_RELATIVE
    if not path.is_file():
        print(PRECONDITION_PREFIX + "在册量具不在位：" + str(path) + "（本量具不复制它的实现）",
              file=sys.stderr, flush=True)
        raise SystemExit(EXIT_PRECONDITION)
    spec = importlib.util.spec_from_file_location("r626_compare_vector_recall", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _TOOL_MODULES["tool"] = module
    return module


def precondition_failed(reason: str):
    """前置不满足的唯一出口：走在册量具那枚函数，不自造第二份语义。"""
    load_recall_tool().fail_precondition(str(reason))


# --------------------------------------------------------------------- 单题度量
def overlap_at_k(left_ids, right_ids, k: int) -> float:
    """overlap@k ＝ 两腿名次集合的交集枚数 ÷ k。

    分母用**请求的名次数 k**而不是并集：并集会把"空列表"读成 0/5，把"少返回"读成 3/7，
    两件事在同一列里分不开。这一单要的读法是"105 题平均吃回了几成候选"，所以按 k 归一；
    jaccard 同时交回，与在册件 r382_leg_compare.py 的旧拼法对得上账，免得多铸一把尺。
    """
    width = int(k)
    if width <= 0:
        return 0.0
    shared = set(left_ids or ()) & set(right_ids or ())
    return len(shared) / width


def jaccard(left_ids, right_ids) -> float:
    union = set(left_ids or ()) | set(right_ids or ())
    if not union:
        return 1.0
    return len(set(left_ids or ()) & set(right_ids or ())) / len(union)


def is_silent_empty(returned: int, leg_size: int, k: int) -> bool:
    """承重的判空格：库容够交回 k 名，这一腿却一名都不交。

    🔴 `leg_size >= k` 这一半不许摘：库里本来就不足 k 枚时交回空表是**语料稀缺**不是引擎坏了
    （1008 枚存量上问 5 名却拿回 0 名才是病）。把这一格摘掉，21 枚空列表就被折成"结果少"，
    静默空召回混进 0 号出口——本文件的全部价值在这一行，牙咬的也是这一行。
    """
    return int(returned) == 0 and int(leg_size) >= int(k)


def _search(leg, vector, k: int, errors: list) -> list:
    """腿自己抛出来的东西不当成"空召回"：那是量具没跑成，记进 errors 交给前置出口。"""
    try:
        return [str(item) for item in leg.search(vector, k)]
    except Exception as exc:  # noqa: BLE001 - 崩溃与静默空必须分账，混了就等于造假
        errors.append({"leg": leg.name, "error": type(exc).__name__ + ": " + str(exc)})
        return []


def run_probe(questions, *, embed, chroma, pg, k: int) -> dict:
    """逐题对照两腿。`questions` 用 compare_vector_recall.load_questions 的三元组形状。

    腿是注入的：真跑给 ChromaLeg / PgLeg，用例给假腿。判据不在注入之后改主意。
    """
    width = int(k)
    rows = []
    errors: list = []
    for source, question_id, question in questions:
        row_errors: list = []
        vector: list = []
        try:
            vector = list(embed(question))
        except Exception as exc:  # noqa: BLE001 - 模型不在场按"没跑成"记，不按空召回记
            row_errors.append({"leg": "embed", "error": type(exc).__name__ + ": " + str(exc)})
        chroma_ids = _search(chroma, vector, width, row_errors) if vector else []
        pg_ids = _search(pg, vector, width, row_errors) if vector else []
        empty_legs = []
        if not row_errors:
            if is_silent_empty(len(chroma_ids), chroma.size(), width):
                empty_legs.append(LEG_CHROMA)
            if is_silent_empty(len(pg_ids), pg.size(), width):
                empty_legs.append(LEG_PG)
        errors.extend(row_errors)
        rows.append({
            "source": source,
            "id": question_id,
            "question": question,
            "chroma_ids": chroma_ids,
            "pg_ids": pg_ids,
            "chroma_returned": len(chroma_ids),
            "pg_returned": len(pg_ids),
            "empty_flag": bool(empty_legs),
            "empty_legs": empty_legs,
            "overlap_at_k": round(overlap_at_k(chroma_ids, pg_ids, width), 6),
            "jaccard": round(jaccard(chroma_ids, pg_ids), 6),
            "exact_order_match": chroma_ids == pg_ids,
            "scarcity_empty": (not row_errors) and (
                (len(chroma_ids) == 0 and chroma.size() < width)
                or (len(pg_ids) == 0 and pg.size() < width)),
            "error": "; ".join(item["error"] for item in row_errors) or None,
        })
    return {
        "k": width,
        "questions": rows,
        "legs": {LEG_CHROMA: {"name": LEG_CHROMA, "size": int(chroma.size())},
                 LEG_PG: {"name": LEG_PG, "size": int(pg.size())}},
        "errors": errors,
        "summary": summarize(rows, k=width, chroma_size=int(chroma.size()),
                             pg_size=int(pg.size()), error_count=len(errors)),
    }


def summarize(rows, *, k: int, chroma_size: int, pg_size: int, error_count: int = 0) -> dict:
    """汇总。字段名就是交回口径，改名等于改判据，所以一次定死，逐枚有出处。"""
    total = len(rows)
    empty_chroma = [row["id"] for row in rows if LEG_CHROMA in row["empty_legs"]]
    empty_pg = [row["id"] for row in rows if LEG_PG in row["empty_legs"]]
    agreements = sum(1 for row in rows if row["exact_order_match"])
    return {
        "questions": total,
        "k": int(k),
        "chroma_size": int(chroma_size),
        "pg_size": int(pg_size),
        #: 交回三件硬指标：空召回各腿枚数、平均重合率、名次全等率。
        "empty_chroma_count": len(empty_chroma),
        "empty_pg_count": len(empty_pg),
        "empty_chroma_ids": empty_chroma,
        "empty_pg_ids": empty_pg,
        #: 与静默空分账的另一格：库容不足 k 的空返回，读它不许读成引擎坏了。
        "thin_corpus_empty_count": sum(1 for row in rows if row["scarcity_empty"]),
        "mean_overlap_at_k": (round(sum(row["overlap_at_k"] for row in rows) / total, 6)
                              if total else None),
        "mean_jaccard": (round(sum(row["jaccard"] for row in rows) / total, 6)
                        if total else None),
        "exact_leg_agreement": {
            "count": agreements,
            "questions": total,
            "ratio": round(agreements / total, 6) if total else None,
            "definition": "chroma_ids == pg_ids（逐名次相等，不是集合相等）",
        },
        "error_count": int(error_count),
    }


def classify(summary, *, min_mean_overlap: float) -> tuple:
    """把读数折成退出码。顺序是刻意的：静默空召回优先于重合率，谁也不许把谁洗掉。"""
    if summary["empty_chroma_count"] or summary["empty_pg_count"]:
        return EXIT_SILENT_EMPTY, [
            "静默空召回：" + LEG_CHROMA + " " + str(summary["empty_chroma_count"])
            + " 题 / " + LEG_PG + " " + str(summary["empty_pg_count"])
            + " 题（库容 >= k 却交回空列表）"]
    mean = summary["mean_overlap_at_k"]
    if mean is None:
        return EXIT_PRECONDITION, ["一题都没量到，重合率无从判定"]
    if mean < float(min_mean_overlap):
        return EXIT_LOW_OVERLAP, ["mean overlap@%s = %s 低于给定阈值 %s"
                                  % (summary["k"], mean, min_mean_overlap)]
    return EXIT_CLEAN, ["无静默空召回，mean overlap@%s = %s 不低于阈值 %s"
                        % (summary["k"], mean, min_mean_overlap)]


def require_no_leg_errors(tool, result) -> None:
    """腿抛异常 ＝ 量具没跑成（码 2），既不是静默空（码 1）也不是差异（码 3）。

    这一格是本单最容易造假话的地方：把异常顺手读成"返回 0 枚"，21 枚的真症状就能替任意多的
    崩溃打掩护。所以它在判据之前先出口，并把抛出的名字逐枚点名。
    """
    errors = result.get("errors") or []
    if errors:
        tool.fail_precondition("有腿在计算中抛出异常，本次不产出召回结论："
                               + json.dumps(errors[:5], ensure_ascii=False))


# --------------------------------------------------------------------------- 腿
class ChromaLeg:
    """遗留引擎那一腿：只读 `query`，库容取 `collection.count()`（判空格的第一枚分母）。"""

    name = LEG_CHROMA

    def __init__(self, collection, *, size=None):
        self.collection = collection
        self._size = int(collection.count()) if size is None else int(size)

    def size(self) -> int:
        return self._size

    def search(self, vector, k: int) -> list:
        hit = self.collection.query(query_embeddings=[list(vector)], n_results=int(k)) or {}
        return [str(item) for item in ((hit.get("ids") or [[]])[0] or [])]


class PgLeg:
    """PGVector 那一腿：召回语句走 compare_vector_recall.pg_recall()，本类不自带一条 SQL。"""

    name = LEG_PG

    def __init__(self, tool, connection, *, vector_table: str, operator: str, size: int):
        self.tool = tool
        self.connection = connection
        self.vector_table = str(vector_table)
        self.operator = str(operator)
        self._size = int(size)

    def size(self) -> int:
        return self._size

    def search(self, vector, k: int) -> list:
        literal = "[" + ",".join(repr(float(value)) for value in vector) + "]"
        return list(self.tool.pg_recall(self.connection, vector_table=self.vector_table,
                                        operator=self.operator, literal=literal, k=int(k)))


# --------------------------------------------------------------- 零变异 plumbing
#: 现役卷在仓库根/容器根下的那一枚目录名（容器里 ROOT=/app，同一判据命中 /app/chroma_db）。
LIVE_VOLUME_ROOT = "chroma_db"


def is_live_volume(path) -> bool:
    """认出"那枚还在给装机提供读服务的现役卷"：仓根的 chroma_db/ 与容器里的 /app/chroma_db。

    判的是路径不是存在性——调用方还没碰文件系统之前就得先拒。反过来写会逼用例为了测这一格
    去工作树里造一枚目录，那是本仓明令禁止的写口形状（test_r253 咬的就是这类）。
    """
    candidate = Path(str(path)).expanduser()
    try:
        relative = candidate.relative_to(ROOT)
    except ValueError:
        return False
    return bool(relative.parts) and relative.parts[0] == LIVE_VOLUME_ROOT


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def volume_inventory(directory) -> dict:
    """内容清单：逐文件 sha256 折成一枚总摘要。只看字节不看 mtime（时间戳会自己动，字节不会）。"""
    base = Path(str(directory))
    if not base.is_dir():
        precondition_failed("目录不存在，无从做清单：" + str(base))
    entries = []
    total = 0
    for path in sorted(item for item in base.rglob("*") if item.is_file()):
        size = path.stat().st_size
        total += size
        entries.append("%s:%d:%s" % (path.relative_to(base).as_posix(), size, _sha256_file(path)))
    return {"files": len(entries), "bytes": total,
            "digest": hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()}


def inventories_match(before: dict, after: dict) -> bool:
    """源卷前后是否逐字节同一份。只比 digest：files/bytes 相等而内容换过也算动过。"""
    return str(before.get("digest")) == str(after.get("digest"))


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
    except ValueError:
        return False
    return True


def snapshot_volume(source, staging, *, copier=None) -> Path:
    """按字节把源卷复制到 `staging` 之下并返回副本路径；源目录一个字节都不写。

    🔴 复制源**可以**是现役卷（`/app/chroma_db` 正是本单要快照的那一枚）——复制只是读；
    被禁的是"把现役卷交给产品客户端打开"，那一格由 chroma_dir_for_run() 守。
    ``copier`` 是留给用例的接缝：钉"源可以是现役卷、落点必须在仓外"这一对事实，
    不必真去复制 8 MB 卷。
    """
    src = Path(str(source)).expanduser().resolve()
    if not src.is_dir():
        precondition_failed("要快照的目录不存在：" + str(src) + "（不要新建）")
    stage = Path(str(staging)).expanduser().resolve()
    target = stage / ("r626-snapshot-" + src.name)
    if _is_within(target, src):
        precondition_failed("快照落点落在源卷里面，拒绝自抄：" + str(target) + " ⊂ " + str(src))
    stage.mkdir(parents=True, exist_ok=True)
    if target.exists():
        precondition_failed("快照落点已存在，拒绝覆盖：" + str(target))
    (copier or shutil.copytree)(src, target)
    return target


def remove_snapshot(snapshot) -> None:
    """删掉本量具自己造的快照：只允许删 snapshot_volume() 交回来的那个落点。"""
    if snapshot is None:
        return
    shutil.rmtree(str(snapshot), ignore_errors=True)


def chroma_dir_for_run(args, staging) -> tuple:
    """决定读哪一枚目录，并交回"这枚目录是不是本单造的快照"。

    两把口子互斥且都必须显式：`--snapshot-from` 由本单复制后读副本；`--chroma-dir` 只接
    调用方**已经**快照好的副本。任何一枚指到现役卷都当场拒——绝不学 compare_vector_recall
    那样留一枚会按 cwd 落进工作树的默认卷（R134 那枚病灶）。
    """
    if bool(args.snapshot_from) == bool(args.chroma_dir):
        precondition_failed("--snapshot-from 与 --chroma-dir 必须且只能给一枚："
                            "本量具没有「打开默认卷」这一档")
    if args.snapshot_from:
        opened = snapshot_volume(args.snapshot_from, staging)
        if is_live_volume(opened):
            precondition_failed("快照落点仍指在现役卷上，拒开：" + str(opened))
        return opened, True
    directory = Path(str(args.chroma_dir)).expanduser().resolve()
    if is_live_volume(directory):
        precondition_failed("--chroma-dir 指向现役卷：" + str(directory)
                            + "；本量具只读快照副本，现役卷只许当 --snapshot-from 的复制源")
    if not directory.is_dir():
        precondition_failed("快照副本目录不存在：" + str(directory))
    return directory, False


# ------------------------------------------------------------------- 人读与机读
def render_human(result, *, show_all: bool = False) -> str:
    """人读输出：先给汇总，再点名每一枚空召回题，最后逐题（默认只印有差异的）。"""
    summary = result["summary"]
    lines = ["-- R626 遗留引擎静默空召回：k=%s，题数=%s，chroma 库容=%s，pg 库容=%s --"
             % (summary["k"], summary["questions"], summary["chroma_size"],
                summary["pg_size"])]
    for key in ("empty_chroma_count", "empty_pg_count", "thin_corpus_empty_count",
                "mean_overlap_at_k", "mean_jaccard", "error_count"):
        lines.append("%-26s %s" % (key, summary[key]))
    agreement = summary["exact_leg_agreement"]
    lines.append("%-26s %s/%s = %s（%s）" % ("exact_leg_agreement", agreement["count"],
                                             agreement["questions"], agreement["ratio"],
                                             agreement["definition"]))
    if summary["empty_chroma_ids"]:
        lines.append("-- 🔴 静默空召回（chroma 腿交回空列表）题号 --")
        lines.append("    " + " ".join(summary["empty_chroma_ids"]))
    if summary["empty_pg_ids"]:
        lines.append("-- 🔴 静默空召回（pg 腿交回空列表）题号 --")
        lines.append("    " + " ".join(summary["empty_pg_ids"]))
    lines.append("-- 逐题 --")
    for row in result["questions"]:
        if row["empty_flag"] or show_all or not row["exact_order_match"]:
            lines.append("%s %s empty=%s overlap=%.4f chroma=%d/%d pg=%d/%d" % (
                row["id"] or row["question"][:16], "EMPTY" if row["empty_flag"] else "diff ",
                ",".join(row["empty_legs"]) or "-", row["overlap_at_k"], row["chroma_returned"],
                summary["k"], row["pg_returned"], summary["k"]))
            if show_all:
                lines.append("    chroma: " + repr(row["chroma_ids"]))
                lines.append("    pg    : " + repr(row["pg_ids"]))
    return "\n".join(lines)


def render_markdown(result, *, code: int, reasons) -> str:
    """人读表格：每行一题，判空格与重合率同排，读的人不需要再算第二遍。"""
    summary = result["summary"]
    lines = ["# R626 遗留引擎静默空召回读数（k=%s，%s 题）" % (summary["k"],
                                                                summary["questions"]),
             "",
             "| 指标 | 读数 |",
             "|---|---|",
             "| empty_chroma_count | %s |" % summary["empty_chroma_count"],
             "| empty_pg_count | %s |" % summary["empty_pg_count"],
             "| mean_overlap_at_k | %s |" % summary["mean_overlap_at_k"],
             "| exact_leg_agreement | %s/%s = %s |" % (summary["exact_leg_agreement"]["count"],
                                                       summary["exact_leg_agreement"]["questions"],
                                                       summary["exact_leg_agreement"]["ratio"]),
             "| 库容（chroma / pg） | %s / %s |" % (summary["chroma_size"], summary["pg_size"]),
             "| 退出码 | %s |" % code,
             "",
             "判读：" + "；".join(reasons),
             "",
             "| id | question | chroma_ids | pg_ids | empty_flag | overlap_at_k |",
             "|---|---|---|---|---|---|"]
    for row in result["questions"]:
        question = str(row["question"]).replace("|", "\\|")
        if len(question) > 40:
            question = question[:40] + "…"
        lines.append("| %s | %s | %s | %s | %s | %.4f |" % (
            row["id"], question, " ".join(row["chroma_ids"]) or "（空）",
            " ".join(row["pg_ids"]) or "（空）",
            ",".join(row["empty_legs"]) or "-", row["overlap_at_k"]))
    return "\n".join(lines) + "\n"


def write_outputs(result, *, json_path, md_path, code: int, reasons) -> None:
    """机读 json 与人读 md 各写一份；两枚都是本单的交付面，缺一枚都不算交回。

    判据（退出码与原因串）写进**两份**产物：只把人读那份标红，第二天就会有人拿机读件
    算出"零差异"——同一份读数两套结论，正是这一族病。
    """
    enriched = dict(result)
    enriched["verdict"] = {"exit_code": int(code), "reasons": list(reasons)}
    if json_path:
        Path(str(json_path)).write_text(
            json.dumps(enriched, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8", newline="\n")
        print("机读已写出：" + str(json_path))
    if md_path:
        Path(str(md_path)).write_text(render_markdown(enriched, code=code, reasons=reasons),
                                      encoding="utf-8", newline="\n")
        print("人读已写出：" + str(md_path))


# --------------------------------------------------------------------- 命令行
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="R626 遗留引擎静默空召回量具（只读快照副本，绝不开现役卷；产品码不得依赖本文件）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 干净 / 1 静默空召回 / 2 前置不满足 / 3 重合率低于阈值。"
               "1 号在本量具专指静默空召回，与 compare_vector_recall 的"
               "1 号（检出差异）语义不同，两份产物不许塞进同一张分诊表。")
    parser.add_argument("--snapshot-from", default=None,
                        help="现役卷目录：本脚本只按字节复制出副本再读，绝不原地打开它")
    parser.add_argument("--chroma-dir", default=None,
                        help="调用方已经快照好的副本；与 --snapshot-from 二选一，没有默认卷")
    parser.add_argument("--staging", default=None,
                        help="快照落点的父目录（缺省进系统临时目录），只在 --snapshot-from 时用")
    parser.add_argument("--keep-snapshot", action="store_true",
                        help="跑完保留副本目录（默认删掉自己造的那一份）")
    parser.add_argument("--collection", default=None,
                        help="缺省读 compare_vector_recall 的同一枚默认值，不抄字符串（R120 同族病）")
    parser.add_argument("--vector-table", default=None)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--fixture", action="append", default=None,
                        help="题集 jsonl，可重复；缺省用在册量具的同一批题")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 题（冒烟用），0 表示全跑")
    parser.add_argument("--min-mean-overlap", type=float, default=0.0,
                        help="重合率门槛，走参数：今天的读数不进代码")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--all", action="store_true", help="逐题全打，不只打有差异的")
    parser.add_argument("--out", default=None, help="机读 json 落点")
    parser.add_argument("--md", default=None, help="人读表格落点")
    args = parser.parse_args(argv)
    if args.k < 1:
        precondition_failed("--k 至少 1 枚，拿到了也不构成召回判据：" + str(args.k))
    return args


def probe(argv=None) -> int:
    """真跑装配：口径核对 → 快照 → 语料级差集 → 逐题两腿 → 判据 → 两份产物。

    前置不满足一律借 compare_vector_recall 的出口（同一个前缀、同一个 2 号），
    这样照退出码分诊的自动化不必认第二种"没跑成"。
    """
    args = parse_args(argv)
    tool = load_recall_tool()
    if tool.EXIT_PRECONDITION != EXIT_PRECONDITION:
        print(PRECONDITION_PREFIX + "在册量具的 2 号语义与本量具不一致，两份产物不再同源",
              file=sys.stderr, flush=True)
        raise SystemExit(EXIT_PRECONDITION)
    if tool.PRECONDITION_PREFIX != PRECONDITION_PREFIX:
        print(PRECONDITION_PREFIX + "在册量具的前缀与本量具不一致，两份产物不再同源",
              file=sys.stderr, flush=True)
        raise SystemExit(EXIT_PRECONDITION)
    if args.min_mean_overlap < 0:
        precondition_failed("--min-mean-overlap 不能是负数：" + str(args.min_mean_overlap))

    defaults = tool.parse_args([])
    collection_name = args.collection or defaults.collection
    vector_table = tool._safe_table(args.vector_table or defaults.vector_table)
    fixture_paths = args.fixture or list(tool.DEFAULT_FIXTURES)
    questions = tool.load_questions(fixture_paths)
    if args.limit:
        questions = questions[:int(args.limit)]
    if not questions:
        precondition_failed("题集里一道题都没有：" + " ".join(str(p) for p in fixture_paths))

    staging = Path(args.staging) if args.staging else Path(tempfile.gettempdir()) / (
        "r626-" + str(os.getpid()))
    source = Path(str(args.snapshot_from)).expanduser().resolve() if args.snapshot_from else None

    # 先验卷再连库：拒开现役卷这一格，必须在一台没起 PostgreSQL 的机器上也问得出来。
    # 复制源照样做前后清单（R269 §8 那把 sha256 前后对账的配方）：现役卷只能被读，不能被开。
    before = volume_inventory(source) if source is not None else None
    snapshot, made_snapshot = chroma_dir_for_run(args, staging)
    connection = None
    try:
        print("-- 读的是副本：" + str(snapshot)
              + ("（本单快照自 " + str(source) + "）" if made_snapshot else "（调用方给的快照）")
              + " --")
        collection = tool.open_chroma(str(snapshot), collection_name)
        space, u1 = tool.resolve_chroma_distance(collection)
        connection = tool.connect_read_only(
            args.database_url or tool.pg_store.resolve_database_url())
        scope = tool.read_scope(connection, vector_table)
        if space != tool.canonical_distance(scope["distance_function"]):
            precondition_failed("距离口径两侧不一致（副本距离=" + str(space)
                                + "，vector_scope 声明=" + str(scope["distance_function"])
                                + "）：这一格根本没测起来，不出空召回结论")
        drift = tool.corpus_drift(connection, collection, vector_table=vector_table, scope=scope)
        if drift["only_in_pg"] or drift["only_in_chroma"]:
            print("[warn] 语料级差集非空：only_in_pg=%d only_in_chroma=%d，两腿本来不完全同库，"
                  "空召回读数要连着这一格一起读"
                  % (len(drift["only_in_pg"]), len(drift["only_in_chroma"])))

        from app.rag.retriever import OllamaEmbeddings  # 要发 embedding：延后 import

        embedder = OllamaEmbeddings()

        def embed(question):
            vector = list(embedder.embed_query(question))
            if len(vector) != int(scope["dimension"]):
                precondition_failed(
                    "查询向量 " + str(len(vector)) + " 维与 vector_scope 声明的 "
                    + str(scope["dimension"]) + " 维不符：错宽的查询在遗留引擎上同样可能静默交空，"
                    "那是量具自己的错位，不是引擎的病（R22 口径）")
            return vector

        chroma = ChromaLeg(collection, size=collection.count())
        pg = PgLeg(tool, connection, vector_table=vector_table,
                   operator=tool.DISTANCE_OPERATORS[space], size=drift["pg_vectors"])
        result = run_probe(questions, embed=embed, chroma=chroma, pg=pg, k=args.k)
        after = volume_inventory(source) if source is not None else None
        result["details"] = {
            "scope": scope,
            "collection": collection_name,
            "vector_table": vector_table,
            "chroma_space": space,
            "u1": {"source": u1.get("source"), "sampled": u1.get("sampled"),
                   "probes": u1.get("probes"), "reason": u1.get("reason")},
            "corpus_drift": {key: (len(value) if isinstance(value, list) else value)
                             for key, value in drift.items()},
            "snapshot": str(snapshot),
            "source_volume": str(source) if source is not None else None,
            "source_inventory_before": before,
            "source_inventory_after": after,
            "source_mutated": (None if before is None else not inventories_match(before, after)),
            "fixtures": [str(path) for path in fixture_paths],
            "min_mean_overlap": float(args.min_mean_overlap),
            "note": "本量具不读 INDEX_BACKEND：两腿都显式问，旋钮翻没翻都问得出空召回",
        }
        if result["details"]["source_mutated"]:
            precondition_failed("源卷在读取前后不再是同一份字节（before="
                                + str(before["digest"])[:16] + " after="
                                + str(after["digest"])[:16] + "）：本次不产出空召回结论")

        require_no_leg_errors(tool, result)
        code, reasons = classify(result["summary"], min_mean_overlap=args.min_mean_overlap)
        print("\n".join(reasons))
        print(render_human(result, show_all=args.all))
        write_outputs(result, json_path=args.out, md_path=args.md, code=code, reasons=reasons)
        return code
    finally:
        if made_snapshot and snapshot is not None and not args.keep_snapshot:
            remove_snapshot(snapshot)
        if connection is not None:
            connection.close()


def main(argv=None) -> int:
    try:
        return probe(argv)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - "没跑成"不许冒领 1 号或 3 号
        message = ("量具自身异常终止：" + type(exc).__name__ + ": " + str(exc)
                   + "（本次没有产出任何空召回结论）")
        try:
            load_recall_tool().fail_precondition(message)
        except SystemExit:
            raise
        except Exception:  # pragma: no cover - 在册量具连装载都失败
            print(PRECONDITION_PREFIX + message, file=sys.stderr, flush=True)
            raise SystemExit(EXIT_PRECONDITION)
        raise SystemExit(EXIT_PRECONDITION)


if __name__ == "__main__":
    raise SystemExit(main())
