# -*- coding: utf-8 -*-
"""R580 —— A④「逐类不退化」的第一次**逐类**归因：run13（Chroma 读腿）→ run14（pgvector 读腿）

===== 这一格为什么一直翻不了绿 =====
``docs/handoff/2026-09-23-v1-acceptance-record.md`` §3 的 A④ 那一行记的是 run6：
「口径冲突 0.4211 → 0.3158（19 题掉 2 题），其余十族零退步、五族进步」⇒ ❌，并明写
「第二次由本判据抓到真退化（首次 run4 doc-19）⇒ 不许拿"总分涨了"抵账，需归因单」。
归因单欠的是**逐类那一刀**：总控已经做过全表逐题复算（翻分 10↓／6↑＝16 枚散 8 类），
本件不重做那一遍，只做它下面一层——把翻分按 ``category``／``tier`` 两维切开，并把每一处
下降证到题级。🔴 本格只交数与判据对照，A④ 翻不翻绿由总控裁：``verdicts`` 里只有
「达／不达／不可判」三档，每档带自己的凭据，一枚"翻绿"都不许出现。

===== 唯一变量（现读对账，不假设） =====
run13／run14 同镜像 revision、同题集 sha256、各 105 枚，两窗 ``index_backend`` 一枚空
（＝缺省 Chroma 读腿）一枚 ``pgvector``。这三件事本件都从 ``*.window.json`` 现读：
revision 对不上、题集 sha 对不上、或窗记里的 sha 与现场重算的 ``--fixture`` sha 不等、
或两窗读后端**没换过** ⇒ 「唯一变量＝向量库读腿」这句前提就破了 ⇒ ``ReconcileError``（rc=2）。
唯一的例外是同一枚文件跟自己比（``pairing.mode = "self-control"``）：那是正控，
它本来就不该有翻分，也不该拿它说读腿的事。

===== 尺（一枚都不新造；另写一套"算不算对"就是平行实现） =====
* 判对错：``app/quality/eval.py`` 的 ``_is_correct``（写本件时在该文件 :67，``must_contain``
  逐枚全含）。🔴 本件只经模块属性 ``quality_eval._is_correct(...)`` 调用它，不复制判据。
* 两把尺的分母账：同模块 ``derive_scorability``（:279）＋ ``correctness_subset_ruler``（:321），
  处置值由 ``row_disposition``（:204）现读题源里的 ``r401.disposition``。
  🔴 总控本板上那两句数（甲案扣除 19 枚／分母 86）本件一个都不抄，全部现算并三向对账。
* 批准账本：同模块 ``load_approval_ledger``（:76）＋ ``summarize_approval_ledger``（:99），
  kind 三枚常量 ``APPROVAL_KIND``／``APPROVAL_FAILED_KIND``／``HITL_PRE_KIND`` 原样取用。
* 题号→行（同题多轮取最大 attempt）：``scripts/r518_a2_lane_attribution.py`` 的
  ``rows_by_id``（:136），本件不另写一本折叠账。
* 检索腿读数：在册量具 ``scripts/r59_recall_compare.py`` 交回的 ``p3-parity.json``——
  每题两腿各自 top-k 的 id 集合、「本腿有对腿无」的那几枚、以及本腿交回几行。

===== 四类归因（判据②：四类之外不许出现新类） =====
``检索腿``   该题 evidence/source 集合在两窗不同，**且**差异能对上 PG 与 Chroma 各自的 top-k：
             T1＝赢的那一窗独有的载锚引证恰好落在「本腿独有」集合里；
             T2＝输的那一窗引证为空，且它那一腿在 parity 上就是 0 行、对腿有行。
``生成措辞`` 引证集合在两窗逐枚相同（chunk 级），或锚词在两窗都不在任何引证摘录里（它压根
             不是被"引"出来的）而 parity 说两腿候选集同一枚都没换 ⇒ 只能出在生成措辞上。
``分母口径`` 这一枚属于「未答完」（在册 kind ``error_event``）或「hitl 批准失败」
             （``APPROVAL_FAILED_KIND``）那一族：翻的不是尺，是分母。
``量具取不到`` 以上四条都证不到 ⇒ 写"未量到"并点名为什么（哪一格缺、缺谁的读数），不猜。
🔴 判定顺序就是上面这个顺序，且每一步都把原始读数留在 ``evidence`` 里，可核对、可复查。

===== 纪律 =====
只读：三本账与题集一律只读打开，本件一个字节都不往输入里写；不打模型、不开容器、
不动 PG（``be-r575``／``be-r579`` 正在库里做演练，撞上去两单都废）。"""

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
for _extra_path in (str(REPO_ROOT), str(SCRIPT_DIR)):
    if _extra_path not in sys.path:
        sys.path.insert(0, _extra_path)

from app.quality import eval as quality_eval  # noqa: E402  在册尺：只经模块属性调用
import r518_a2_lane_attribution as lane  # noqa: E402  rows_by_id：题号→行的在册读法

#: 在册判据范围：A④ 看的是全 105 枚（docs/testing 从 run9 起就这么钉）。本件拿它当**对账尺**，
#: 不当结论；任何一窗题数不等于它就直接拒绝出数（rc=3），不许按缺的行出分母。
EXPECTED_TOTAL_IN_BOOK = 105

#: 题集（评测集）在仓内、只读，钉死件不许改一字。
DEFAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"

#: 「逐类」的两个维度就是题集里已有的那两列，本件不新造第三维。
DIM_CATEGORY = "category"
DIM_TIER = "tier"
DIMS = (DIM_CATEGORY, DIM_TIER)
#: 与 ``evaluate_evaluation_set`` 的 ``category_metrics`` 同一个缺省名，不另起一格。
UNCLASSIFIED = "未分类"

#: 四类（判据②）。纸上的四枚名字，一枚不许多、一枚不许少。
CLASS_LEG = "检索腿"
CLASS_WORDING = "生成措辞"
CLASS_DENOM = "分母口径"
CLASS_UNMEASURED = "量具取不到"
CLASS_ORDER = (CLASS_LEG, CLASS_WORDING, CLASS_DENOM, CLASS_UNMEASURED)

#: 「未答完」那一族的在册 kind（采集器吐 error 帧，answers 里是预制占位串）。
ERROR_EVENT_KIND = "error_event"
#: 分母口径族＝未答完 ∪ hitl 批准失败。两枚 kind 一枚在册常量、一枚本件对在册 kind 的命名。
DENOM_KINDS = (ERROR_EVENT_KIND, quality_eval.APPROVAL_FAILED_KIND)

#: 读后端 → parity 里那两腿的键前缀。"" 是 ``INDEX_BACKEND`` 的缺省＝Chroma 读腿。
LEG_PREFIX = {"chroma": "chroma", "": "chroma", "pgvector": "pg"}
LEG_OTHER = {"chroma": "pg", "pg": "chroma"}

#: 归因代码（进纸面的每一枚都是派生出来的，没有一枚是手抄的结论）。
CODE_DENOM = "DENOM-{kind}"
CODE_LEG_T1 = "T1-CARRIER-IN-OWN-LEG-ONLY-TOPK"
CODE_LEG_T2 = "T2-EMPTY-CITATION-OWN-LEG-ZERO-ROWS"
CODE_WORD_CHUNK_SAME = "CITATIONS-IDENTICAL-CHUNK-LEVEL"
CODE_WORD_ANCHOR_POOL_SAME = "ANCHOR-NOT-A-QUOTATION-BOTH-WINDOWS-LEG-POOL-IDENTICAL"
CODE_UNMEASURED_OUTSIDE = "CARRIER-OUTSIDE-BOTH-LEG-TOPK"
CODE_UNMEASURED_DOWNSTREAM = "CARRIER-IN-BOTH-LEG-TOPK-DOWNSTREAM-SELECTION"
CODE_UNMEASURED_PARTIAL = "CARRIER-ONLY-PARTIALLY-MAPPED-TO-OWN-LEG"
CODE_UNMEASURED_EMPTY_WITH_ROWS = "EMPTY-CITATION-BUT-OWN-LEG-RETURNED-ROWS"
CODE_UNMEASURED_POOL_DIFFERS = "ANCHOR-NOT-A-QUOTATION-LEG-POOL-DIFFERS"
CODE_UNMEASURED_NO_PARITY = "NO-PARITY-READOUT"
CODE_UNMEASURED_CARRIERS_SAME = "CARRIERS-IDENTICAL-BUT-CITATIONS-DIFFER"
CODE_UNMEASURED_OTHER = "NO-MEASURED-PATH-TO-A-CLASS"

EXIT_OK = 0
EXIT_RECONCILE = 2
EXIT_REFUSE = 3

#: 读数缺如时的三枚字样：纸面只写"未量到"，不写猜测。
NOT_MEASURED = "未量到"
NOT_PROVIDED = "未交"


class ReconcileError(RuntimeError):
    """对账不上：两窗不构成「唯一变量＝读腿」的对照，或分桶／在册报告破了算式 ⇒ rc=2。"""


class RefuseError(RuntimeError):
    """这一窗读不出：题数≠在册分母、题号重了、账里有半行 ⇒ 宁可不出数，rc=3。"""


def _sha256(path):
    """整本文件的 sha256（只读打开）：题集对账与摘前摘后逐字节留痕都用它。"""
    with io.open(str(path), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _label_of(answers_path):
    """从 ``<label>-answers.jsonl`` 反推标签：侧车／报告／窗记三本都按同名兄弟件去找。"""
    stem = Path(answers_path).name
    for suffix in ("-answers.jsonl", ".answers.jsonl", "-answers.json"):
        if stem.endswith(suffix):
            return stem[:-len(suffix)]
    return Path(stem).stem


def _sibling(answers_path, suffix):
    return Path(answers_path).resolve().parent / (_label_of(answers_path) + suffix)


def read_jsonl(path, what):
    """逐行读一本 jsonl。🔴 只读打开；半行／坏行一律当"这一窗读不出"，不许静默跳过。

    在册 ``load_approval_ledger`` 对侧车是「半行跳过」的口径（它不是一条记录），那是采集侧
    的既有纪律；answers 不一样，少一枚就意味着 105 枚的判据范围破了，所以这里不跳。
    """
    path = Path(path)
    if not path.is_file():
        raise RefuseError(what + " 不存在：" + str(path))
    rows = []
    with io.open(str(path), encoding="utf-8-sig") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError as error:
                raise RefuseError(what + " 第 " + str(number) + " 行不是完整 JSON ⇒ 这一窗不许按"
                                  "「答完了」出分母：" + str(error))
            if not isinstance(row, dict):
                raise RefuseError(what + " 第 " + str(number) + " 行不是对象")
            rows.append(row)
    return rows


def read_json_object(path, what):
    """读一本 json（窗记／报告）：交了就必须在，没交就回 ``None`` 由调用方记"未交"。"""
    if not path:
        return None
    path = Path(path)
    if not path.is_file():
        return None
    with io.open(str(path), encoding="utf-8-sig") as handle:
        try:
            return json.load(handle)
        except ValueError as error:
            raise RefuseError(what + " 读不出（" + str(path) + "）：" + str(error))


def load_fixture_rows(path):
    """题集：``category``／``tier`` 两列是 A④「逐类」的两个维度，缺题号或题号重了都没法点名。"""
    rows = read_jsonl(path, "题集（评测集）")
    by_id = {}
    for number, row in enumerate(rows, 1):
        row_id = str(row.get("id", "") or "").strip()
        if not row_id:
            raise RefuseError("题集第 " + str(number) + " 行没有题号 ⇒ 逐类归因没法点名")
        if row_id in by_id:
            raise RefuseError("题集里题号重了：" + row_id)
        by_id[row_id] = row
    return rows, by_id


def index_answers(rows, fixture_ids, label, expect_total):
    """把一窗 answers 收成题号→行。🔴 题数不等于在册判据范围就直接拒绝（判据①的硬面）。"""
    if len(rows) != expect_total:
        raise RefuseError(label + " 这一窗只有 " + str(len(rows)) + " 枚，A④ 的在册判据范围是 "
                          + str(expect_total) + " 枚 ⇒ 直接拒绝出数（不许按缺的行出分母）")
    by_id = {}
    for row in rows:
        row_id = str(row.get("id", "") or "").strip()
        if not row_id:
            raise RefuseError(label + " 里有一枚没有题号 ⇒ 没法跟题集逐枚点名")
        if row_id in by_id:
            raise RefuseError(label + " 里题号 " + row_id + " 出现两枚 ⇒ 读不出哪一枚才是终答")
        by_id[row_id] = row
    extra = sorted(set(by_id) - set(fixture_ids))
    missing = sorted(set(fixture_ids) - set(by_id))
    if extra or missing:
        raise RefuseError(label + " 与题集不同源：题集里没有的＝" + ("、".join(extra) or "无")
                          + " ／ 题集有而这一窗缺的＝" + ("、".join(missing) or "无"))
    return by_id


def score_window(fixture_rows, answers_by_id):
    """🔴 全件唯一的判分点：逐枚现判，只经在册尺 ``quality_eval._is_correct`` 这一枚调用。

    走模块属性是为了让"摘掉在册尺"这件事必须能反映到本件的数上（反证刀 e 钉的就是这一格）；
    在本件里另写一套"算不算对"就是平行实现，判据②明令禁止。
    """
    correct = {}
    results = []
    for row in fixture_rows:
        row_id = str(row.get("id"))
        result = answers_by_id[row_id]
        ok = bool(quality_eval._is_correct(row, result))
        correct[row_id] = ok
        results.append({"row": row, "result": result, "correct": ok})
    return correct, results


def read_window(label, answers_path, sidecar_path, report_path, window_path, expect_total):
    """一窗四本账一次读齐：answers 必须有，侧车／报告／窗记缺了就如实记"未交"。"""
    rows = read_jsonl(answers_path, label + " 的 answers")
    ledger, ledger_collapsed = lane.rows_by_id(sidecar_path) if sidecar_path else (None, 0)
    return {
        "label": label,
        "answers_path": str(answers_path),
        "sidecar_path": str(sidecar_path) if sidecar_path and Path(sidecar_path).is_file() else None,
        "report_path": str(report_path) if report_path and Path(report_path).is_file() else None,
        "window_path": str(window_path) if window_path and Path(window_path).is_file() else None,
        "answers": rows,
        "sha256": _sha256(answers_path),
        "ledger": ledger,
        "ledger_collapsed": ledger_collapsed,
        "window": read_json_object(window_path, label + " 的窗记"),
        "report": read_json_object(report_path, label + " 的报告"),
        "expect_total": expect_total,
    }


def pairing_gate(win_a, win_b, fixture_sha, backend_claims):
    """把「唯一变量＝向量库读腿」这句前提钉成可失败的对账，本件不对它做任何假设。"""
    label_a, label_b = win_a["label"], win_b["label"]
    a, b = win_a["window"], win_b["window"]
    if a is None or b is None:
        raise ReconcileError("窗记（``*.window.json``）没交齐：" + "、".join(
            lab for lab, win in ((label_a, a), (label_b, b)) if win is None)
            + " ⇒ revision／fixture_sha256／index_backend 三格读不出，这份对照不许用"
            "（「没读数」不等于「没差异」）")
    problems = []
    for lab, key in ((label_a, "index_backend"), (label_b, "index_backend")):
        if key not in (a if lab == label_a else b):
            problems.append(lab + " 的窗记里没有 " + key + " 那一格 ⇒ 读后端没读数")
    if str(a.get("revision", "")) != str(b.get("revision", "")):
        problems.append("镜像 revision 不同：" + str(a.get("revision")) + " vs " + str(b.get("revision")))
    recorded = {label_a: str(a.get("fixture_sha256", "")), label_b: str(b.get("fixture_sha256", ""))}
    for lab, value in recorded.items():
        if value.lower() != fixture_sha.lower():
            problems.append(lab + " 窗记里的题集 sha 与现场重算不等：" + (value or NOT_MEASURED)
                            + " vs " + fixture_sha)
    backend_a = str(a.get("index_backend", ""))
    backend_b = str(b.get("index_backend", ""))
    for lab, claim, read in ((label_a, backend_claims[0], backend_a),
                             (label_b, backend_claims[1], backend_b)):
        if claim is not None and str(claim) != read:
            problems.append(lab + " 纸面声明的读后端＝" + repr(str(claim)) + " 与窗记现读＝"
                            + repr(read) + " 矛盾")
    self_control = win_a["sha256"] == win_b["sha256"]
    if not self_control and backend_a == backend_b:
        problems.append("两窗 index_backend 相同（" + (backend_a or "(空串＝缺省 Chroma 读腿)")
                        + "）⇒ 读后端没换过，翻分没法归给读腿这一刀")
    for key in ("transport", "shard_size", "container"):
        if str(a.get(key, "")) != str(b.get(key, "")):
            problems.append("混淆因子：" + key + " 两窗不同——" + str(a.get(key)) + " vs "
                            + str(b.get(key)) + " ⇒ 这就不是一枚变量的对照了")
    for lab, win in ((label_a, a), (label_b, b)):
        if win.get("dry_run"):
            problems.append(lab + " 是 dry_run 窗记 ⇒ 这一窗没有真答案")
        if win.get("probe_ok") is False:
            problems.append(lab + " 的 probe_ok＝False：" + json.dumps(win.get("probe_errors"),
                                                                      ensure_ascii=False))
    if problems:
        raise ReconcileError("；".join(problems))
    return {
        "mode": "self-control" if self_control else "a-vs-b",
        "revision": str(a.get("revision", NOT_MEASURED)),
        "fixture_sha256": fixture_sha,
        "index_backend_a": backend_a,
        "index_backend_b": backend_b,
        "backend_a_note": "空串＝INDEX_BACKEND 未设＝缺省 Chroma 读腿" if backend_a == "" else "",
        "transport": str(a.get("transport", NOT_MEASURED)),
        "shard_size": a.get("shard_size"),
        "container": str(a.get("container", NOT_MEASURED)),
        "started_at_a": a.get("started_at"),
        "started_at_b": b.get("started_at"),
    }


def load_parity(path, fixture_ids):
    """在册量具 ``r59_recall_compare`` 的读数：缺文件就回 None，归因会掉进"量具取不到"。"""
    if not path or not Path(path).is_file():
        return None
    with io.open(str(path), encoding="utf-8-sig") as handle:
        try:
            doc = json.load(handle)
        except ValueError as error:
            raise RefuseError("parity 读不出（" + str(path) + "）：" + str(error))
    questions = doc.get("questions")
    if not isinstance(questions, list):
        raise ReconcileError("parity 里没有 questions 列表：" + str(path))
    by_id = {}
    for row in questions:
        row_id = str(row.get("id", "") or "")
        if row_id in by_id:
            raise ReconcileError("parity 里题号重了：" + row_id)
        by_id[row_id] = row
    extra = sorted(set(by_id) - set(fixture_ids))
    missing = sorted(set(fixture_ids) - set(by_id))
    if extra or missing:
        raise ReconcileError("parity 与题集不同源：多＝" + ("、".join(extra) or "无")
                             + " ／ 缺＝" + ("、".join(missing) or "无"))
    meta = doc.get("meta") or {}
    return {
        "path": str(path),
        "tool": str(meta.get("tool", NOT_MEASURED)),
        "generated_at": meta.get("generated_at"),
        "k": meta.get("k"),
        "n": len(by_id),
        "by_id": by_id,
        "summary": doc.get("summary") or {},
    }


def leg_readout(parity_row, backend, label, k=None):
    """把 parity 那一格切成"本腿"读数：top-k、本腿独有、本腿交回几行。"""
    if parity_row is None:
        return None
    prefix = LEG_PREFIX.get(str(backend))
    if prefix is None:
        raise ReconcileError(label + " 的 index_backend＝" + repr(str(backend))
                             + " 不在册（chroma／空串／pgvector）⇒ 引证差异没法对到具体的腿上")
    other = LEG_OTHER[prefix]
    return {
        "leg": prefix, "k": k,
        "topk_ids": [str(item) for item in (parity_row.get(prefix + "_ids") or [])],
        "only_ids": [str(item) for item in (parity_row.get(prefix + "_only_ids") or [])],
        "other_only_ids": [str(item) for item in (parity_row.get(other + "_only_ids") or [])],
        "rows": int(parity_row.get(prefix + "_rows") or 0),
        "other_rows": int(parity_row.get(other + "_rows") or 0),
        "same_set": parity_row.get("same_set"),
        "overlap": parity_row.get("overlap"),
    }

def _head(text, limit=80):
    """纸面点名用的答案头部：折叠换行、限长，只为核对，不参与任何判定。"""
    flat = " ".join(str(text).split())
    return flat[:limit] + ("…" if len(flat) > limit else "")


def citation_view(result):
    """把一行的引证切成两把钥匙。

    ``chunk_key`` ＝ ``文件名#chunk=N``（判据②要的"文件名#chunk 级"差异就用它点名）；
    ``leg_id`` ＝ ``文件名_N``，与在册量具 ``r59_recall_compare`` 的 id 格式逐字一致，
    引证才能对到 PG／Chroma 各自的 top-k 上。🔴 这两个格式是本件唯一的"新造"，造的是
    对账的钥匙，不是判据：判据一枚都不在这文件里。
    """
    items = []
    for event in (result.get("evidence") or []):
        if not isinstance(event, dict):
            continue
        source = str(event.get("source", ""))
        chunk = event.get("chunk_index")
        try:
            chunk_n = int(chunk)
        except (TypeError, ValueError):
            chunk_n = None
        tail = "?" if chunk_n is None else str(chunk_n)
        items.append({
            "source": source,
            "chunk_index": chunk_n,
            "chunk_key": source + "#chunk=" + tail,
            "leg_id": source + "_" + tail,
            "worker": str(event.get("worker", "")),
            "excerpt": str(event.get("excerpt") or ""),
            "source_id": str(event.get("source_id") or ""),
        })
    return items


def carriers_of(citations, anchors):
    """载锚引证＝摘录里逐字含着锚词的那几枚：它才回答"这句话是被哪一枚引证承住的"。"""
    carriers = []
    for item in citations:
        hits = [anchor for anchor in anchors if anchor and anchor in item["excerpt"]]
        if hits:
            carrier = dict(item)
            carrier["anchors"] = hits
            carriers.append(carrier)
    return carriers


def classify_flip(row, hi, lo):
    """把一枚翻分归进四类之一（判据②），并交出可核对的证据。返回 ``(类别, 代码, 证据)``。

    ``hi`` ＝ 这一枚判对的那一窗，``lo`` ＝ 判错的那一窗。归因问的是"谁掉下去了"，
    所以两窗的名字在这里按赢／输排，不按 run 号排；纸面每一枚都会把 label 一起交出来。
    """
    anchors = [str(term) for term in (row.get("must_contain") or [])]
    chunk_hi = [item["chunk_key"] for item in hi["citations"]]
    chunk_lo = [item["chunk_key"] for item in lo["citations"]]
    carrier_hi_ids = sorted(item["leg_id"] for item in hi["carriers"])
    carrier_lo_ids = sorted(item["leg_id"] for item in lo["carriers"])
    delta = sorted(set(carrier_hi_ids) - set(carrier_lo_ids))
    leg_hi, leg_lo = hi["leg"], lo["leg"]
    base = {
        "hi_label": hi["label"], "lo_label": lo["label"],
        "hi_backend": hi["backend"], "lo_backend": lo["backend"],
        "hi_citations": chunk_hi, "lo_citations": chunk_lo,
        "hi_evidence_n": len(chunk_hi), "lo_evidence_n": len(chunk_lo),
        "only_in_hi_citations": sorted(set(chunk_hi) - set(chunk_lo)),
        "only_in_lo_citations": sorted(set(chunk_lo) - set(chunk_hi)),
        "citations_identical_chunk_level": sorted(chunk_hi) == sorted(chunk_lo),
        "citations_identical_order": chunk_hi == chunk_lo,
        "hi_carriers": carrier_hi_ids, "lo_carriers": carrier_lo_ids,
        "carrier_delta_hi_only": delta,
        "anchor_not_a_quotation_both_windows": not carrier_hi_ids and not carrier_lo_ids,
        "hi_kind": hi["kind"], "lo_kind": lo["kind"],
        "hi_leg": leg_hi, "lo_leg": leg_lo,
        "anchors": anchors,
    }

    # ① 分母口径：这一枚属于「未答完」或「hitl 批准失败」那一族，翻的不是尺，是分母。
    denom_kinds = [kind for kind in (lo["kind"], hi["kind"]) if kind in DENOM_KINDS]
    if denom_kinds:
        family = {}
        for side in (lo, hi):
            ledger = side.get("sidecar") or {}
            text = quality_eval._answer_text(side["result"])
            family[side["label"]] = {
                "kind": side["kind"],
                "sentinel": ledger.get("sentinel"),
                "pre_kind": ledger.get("pre_kind"),
                "approved": ledger.get("approved"),
                "approval_rounds": ledger.get("approval_rounds"),
                "approval_http_status": ledger.get("approval_http_status"),
                "approval_error": ledger.get("approval_error"),
                "ledger_answer_chars": ledger.get("answer_chars"),
                "answer_chars": len(text),
                "evidence_n": len(side["citations"]),
                "answer_head": _head(text),
            }
        evidence = dict(base, denom_family=family,
                        note="在册 kind 把这枚记成 " + str(denom_kinds[0])
                             + " ⇒ 它不在「本轮答完了」那一格里；两窗的扣除集合见 denominator_account")
        return CLASS_DENOM, CODE_DENOM.format(kind=denom_kinds[0]), evidence

    # ② 检索腿 T1：赢的那一窗独有的载锚引证，恰好落在「本腿 top-k 有、对腿 top-k 没有」里。
    if delta and leg_hi is not None and set(delta) <= set(leg_hi["only_ids"]):
        evidence = dict(base,
                        leg_claim="这一枚能承住答案的引证，只有本腿（" + leg_hi["leg"]
                                  + "）的 top-" + str(leg_hi["k"])
                                  + " 里有，对腿（" + (leg_lo["leg"] if leg_lo else "?") + "）一枚都没交",
                        hi_leg_only_ids=leg_hi["only_ids"],
                        lo_leg_only_ids=leg_lo["only_ids"] if leg_lo else None)
        return CLASS_LEG, CODE_LEG_T1, evidence

    # ③ 检索腿 T2：输的那一窗引证为空，而它那一腿在 parity 上就是 0 行、对腿有行。
    if (not chunk_lo) and leg_lo is not None and leg_hi is not None \
            and leg_lo["rows"] == 0 and leg_hi["rows"] > 0:
        evidence = dict(base,
                        leg_claim="空引证的方向与读后端一致：" + leg_lo["leg"] + " 腿交回 "
                                  + str(leg_lo["rows"]) + " 行，" + leg_hi["leg"] + " 腿交回 "
                                  + str(leg_hi["rows"]) + " 行",
                        asymmetry="与读腿故事同向（本腿 0 行 ⇒ 检索腿）")
        return CLASS_LEG, CODE_LEG_T2, evidence

    # ④ 生成措辞：引证集合逐枚相同，或锚词压根不是被"引"出来的而两腿候选集没换。
    if sorted(chunk_hi) == sorted(chunk_lo):
        evidence = dict(base, wording_claim="两窗引证在 chunk 级逐枚相同（只换了措辞才有这种形状）")
        return CLASS_WORDING, CODE_WORD_CHUNK_SAME, evidence
    if (not carrier_hi_ids) and (not carrier_lo_ids) and leg_hi is not None \
            and leg_hi["same_set"] is True:
        evidence = dict(base, wording_claim="锚词在两窗的任何摘录里都不逐字存在（它不是被引出来的），"
                                           "而 parity 说两腿的候选集合一枚都没换 ⇒ 只能出在生成措辞")
        return CLASS_WORDING, CODE_WORD_ANCHOR_POOL_SAME, evidence

    # ⑤ 量具取不到：上面四条都证不到，就写"未量到"，并点名缺的是哪一格读数。
    if (not chunk_lo) and leg_lo is not None and leg_lo["rows"] > 0:
        return CLASS_UNMEASURED, CODE_UNMEASURED_EMPTY_WITH_ROWS, dict(
            base, note="输的那一窗一枚引证都没交，而它那一腿（" + leg_lo["leg"] + "）在 parity 上"
                       "明明交回 " + str(leg_lo["rows"]) + " 行 ⇒ 空引证发生在检索之后的那一段，"
                       "本量具（原始问题的单腿 top-k）量不到它，不许折给读腿")
    if delta and leg_hi is not None:
        hi_topk = set(leg_hi["topk_ids"])
        lo_topk = set(leg_lo["topk_ids"]) if leg_lo is not None else set()
        only_hi = set(leg_hi["only_ids"])
        in_both = sorted(set(delta) & hi_topk & lo_topk)
        in_only_hi = sorted(set(delta) & only_hi)
        outside = sorted(set(delta) - hi_topk - lo_topk)
        if set(delta) <= set(outside) and outside:
            code = CODE_UNMEASURED_OUTSIDE
            note = "载锚引证的差异枚（" + "、".join(delta) + "）在两腿各自的 top-k 里都没有 ⇒ " \
                   "它不是这一刀切出来的候选，本量具没法把它归给读腿"
        elif in_only_hi and outside:
            code = CODE_UNMEASURED_PARTIAL
            note = "差异枚里只有 " + "、".join(in_only_hi) + " 落在本腿独有集合，" \
                   + "、".join(outside) + " 两腿都没有 ⇒ 只映射到一半，剩下的未量到"
        elif in_only_hi:
            code = CODE_UNMEASURED_PARTIAL
            note = "差异枚部分落在本腿独有集合（" + "、".join(in_only_hi) + "），T1 的全含条件没满足"
        elif in_both:
            code = CODE_UNMEASURED_DOWNSTREAM
            note = "载锚引证两腿的 top-k 都有（" + "、".join(in_both) + "），只有一窗把它引了出来 " \
                   "⇒ 差异在检索之后的选取/装配那一段，不在读后端这一刀上，本量具量不到"
        else:
            code = CODE_UNMEASURED_OTHER
            note = "有载锚引证差异，但落点既不在本腿独有也不在两腿共有 ⇒ 未量到"
        evidence = dict(base, delta_outside_both_legs=outside, delta_in_both_leg_topk=in_both,
                        delta_in_hi_leg_only=in_only_hi, note=note)
        return CLASS_UNMEASURED, code, evidence
    if (not carrier_hi_ids) and (not carrier_lo_ids):
        if leg_hi is None:
            code, note = CODE_UNMEASURED_NO_PARITY, "没交 parity 读数 ⇒ 两腿候选集有没有换没法读"
        else:
            code, note = CODE_UNMEASURED_POOL_DIFFERS, \
                "锚词在两窗摘录里都不逐字存在，而 parity 说两腿候选集合**不**同" \
                "（same_set=" + json.dumps(leg_hi["same_set"]) + "）⇒ 措辞与读腿都没法单独证到"
        return CLASS_UNMEASURED, code, dict(base, note=note)
    if leg_hi is None:
        return CLASS_UNMEASURED, CODE_UNMEASURED_NO_PARITY, dict(
            base, note="没交 parity 读数 ⇒ 引证差异没法对到 PG／Chroma 各自的 top-k")
    return CLASS_UNMEASURED, CODE_UNMEASURED_CARRIERS_SAME, dict(
        base, note="两窗的载锚引证同一枚都没多同一枚都没少，但引证集合在 chunk 级不同 ⇒ "
                   "掉下去的那一枚不是载锚引证，本量具没法归因")

def attach_question_facts(win, fixture_rows, parity):
    """给这一窗的每题配上尺之外的四格读数：引证、载锚引证、在册 kind、本腿 top-k。"""
    facts = {}
    ledger = win["ledger"] or {}
    for row in fixture_rows:
        row_id = str(row.get("id"))
        result = win["answers_by_id"][row_id]
        citations = citation_view(result)
        anchors = [str(term) for term in (row.get("must_contain") or [])]
        side = ledger.get(row_id)
        facts[row_id] = {
            "label": win["label"], "backend": win["backend"], "result": result,
            "citations": citations, "carriers": carriers_of(citations, anchors),
            "kind": (side or {}).get("kind") if side else None,
            "kind_available": bool(side), "sidecar": side,
            "leg": leg_readout(parity["by_id"].get(row_id), win["backend"], win["label"],
                               parity["k"])
                   if parity is not None else None,
        }
    win["q"] = facts
    return win


def build_flips(fixture_rows, win_a, win_b, label_a, label_b):
    """两窗逐枚对判分结果：只有"一窗对一窗错"才算翻分，两窗同对同错的枚不进这张表。"""
    flips = []
    for row in fixture_rows:
        row_id = str(row.get("id"))
        ok_a, ok_b = win_a["correct"][row_id], win_b["correct"][row_id]
        if ok_a == ok_b:
            continue
        down = ok_a and not ok_b
        hi, lo = (win_a["q"][row_id], win_b["q"][row_id]) if down else (win_b["q"][row_id], win_a["q"][row_id])
        cls, code, evidence = classify_flip(row, hi, lo)
        if down:
            evidence["diff_a_only"] = evidence["only_in_hi_citations"]
            evidence["diff_b_only"] = evidence["only_in_lo_citations"]
        else:
            evidence["diff_a_only"] = evidence["only_in_lo_citations"]
            evidence["diff_b_only"] = evidence["only_in_hi_citations"]
        if cls not in CLASS_ORDER:
            raise ReconcileError(row_id + " 的归因掉出了四类之外：" + str(cls) + "（判据②禁止新类）")
        flips.append({
            "id": row_id,
            "direction": "down" if down else "up",
            DIM_CATEGORY: str(row.get(DIM_CATEGORY) or UNCLASSIFIED),
            DIM_TIER: str(row.get(DIM_TIER) or UNCLASSIFIED),
            "correct_a": ok_a, "correct_b": ok_b,
            "class": cls, "code": code, "evidence": evidence,
        })
    return flips


def _class_tally(items):
    return {cls: sum(1 for item in items if item["class"] == cls) for cls in CLASS_ORDER}


def _fmt_score(value):
    return NOT_MEASURED if value is None else format(value, ".4f")


def bucket_verdict(bucket, label_a, label_b):
    """三档形状：不达（桶分数下降）／不可判（没降但还有没证清的退步题）／达（零退步或退步全在措辞与分母）。"""
    a, b = bucket[label_a], bucket[label_b]
    down = [item for item in bucket["flips"] if item["direction"] == "down"]
    up = [item for item in bucket["flips"] if item["direction"] == "up"]
    tally = _class_tally(down)
    tally_str = "／".join(cls + str(tally[cls]) for cls in CLASS_ORDER if tally[cls]) or "无退步题"
    basis = (label_a + " " + str(a["correct_n"]) + "/" + str(a["denom"]) + " = " + _fmt_score(a["score"])
             + " → " + label_b + " " + str(b["correct_n"]) + "/" + str(b["denom"]) + " = "
             + _fmt_score(b["score"]) + "；Δcorrect_n=" + str(bucket["delta_correct_n"])
             + " Δscore=" + format(bucket["delta_score"], "+.4f")
             + "；退步 " + str(len(down)) + " 枚（" + tally_str + "）进步 " + str(len(up)) + " 枚")
    if b["score"] < a["score"]:
        return "不达", basis + " ⇒ 桶分数下降，退步题号：" + ("、".join(item["id"] for item in down) or "无")
    if any(item["class"] in (CLASS_UNMEASURED, CLASS_LEG) for item in down):
        unreadable = [item["id"] for item in down if item["class"] in (CLASS_UNMEASURED, CLASS_LEG)]
        return "不可判", basis + " ⇒ 分数没降，但 " + "、".join(unreadable) + " 这" + str(len(unreadable)) \
               + " 枚退步还证不到任何一族，本格只交数不替它下结论"
    if down:
        return "达", basis + " ⇒ 退步题（" + "、".join(item["id"] for item in down) + "）全部落在" \
               "生成措辞／分母口径两族，且被同桶的进步题抵住，桶分数不降"
    return "达", basis + " ⇒ 桶内零退步"


def bucketize(dim, fixture_rows, derived, windows, labels, flips):
    """按一维分桶：每桶交 n／correct_n／分母／分数（两把尺都交），并做守恒闸（判据①）。"""
    deducted = set(derived["deducted_ids"])
    buckets = {}
    for row in fixture_rows:
        key = str(row.get(dim) or UNCLASSIFIED)
        bucket = buckets.setdefault(key, {"name": key, "n": 0, "ids": [], "scorable_ids": [],
                                          "deducted_ids": []})
        row_id = str(row.get("id"))
        bucket["ids"].append(row_id)
        if row_id in deducted:
            bucket["deducted_ids"].append(row_id)
        else:
            bucket["scorable_ids"].append(row_id)
        bucket["n"] = len(bucket["ids"])
    for label, win in zip(labels, windows):
        for bucket in buckets.values():
            correct_n = sum(1 for row_id in bucket["ids"] if win["correct"][row_id])
            scorable_correct = sum(1 for row_id in bucket["scorable_ids"] if win["correct"][row_id])
            bucket[label] = {
                "correct_n": correct_n, "denom": bucket["n"],
                "score": round(correct_n / bucket["n"], 4) if bucket["n"] else 0.0,
                "scorable_correct_n": scorable_correct,
                "scorable_denom": len(bucket["scorable_ids"]),
                "scorable_score": round(scorable_correct / len(bucket["scorable_ids"]), 4)
                                 if bucket["scorable_ids"] else None,
                "evidence_empty_n": sum(1 for row_id in bucket["ids"] if not win["q"][row_id]["citations"]),
            }
    out = []
    for bucket in buckets.values():
        bucket["deducted_n"] = len(bucket["deducted_ids"])
        a, b = bucket[labels[0]], bucket[labels[1]]
        bucket["delta_correct_n"] = b["correct_n"] - a["correct_n"]
        bucket["delta_score"] = round(b["score"] - a["score"], 4)
        bucket["delta_scorable_score"] = None if (a["scorable_score"] is None
                                                  or b["scorable_score"] is None) \
            else round(b["scorable_score"] - a["scorable_score"], 4)
        bucket["direction"] = "down" if bucket["delta_score"] < 0 else \
            ("up" if bucket["delta_score"] > 0 else "flat")
        bucket["flips"] = [{"id": item["id"], "direction": item["direction"],
                            "class": item["class"], "code": item["code"],
                            DIM_CATEGORY: item[DIM_CATEGORY], DIM_TIER: item[DIM_TIER]}
                           for item in flips if item[dim] == bucket["name"]]
        bucket["down_flip_ids"] = [item["id"] for item in bucket["flips"] if item["direction"] == "down"]
        bucket["down_flip_classes"] = _class_tally(
            [item for item in bucket["flips"] if item["direction"] == "down"])
        bucket["up_flip_classes"] = _class_tally(
            [item for item in bucket["flips"] if item["direction"] == "up"])
        bucket["verdict"], bucket["verdict_basis"] = bucket_verdict(bucket, labels[0], labels[1])
        out.append(bucket)
    out.sort(key=lambda item: (-item["n"], item["name"]))
    total = sum(bucket["n"] for bucket in out)
    ids = [row_id for bucket in out for row_id in bucket["ids"]]
    if total != len(fixture_rows):
        raise ReconcileError(dim + " 分桶不守恒：Σn＝" + str(total) + " 而题数＝"
                             + str(len(fixture_rows)))
    if len(ids) != len(set(ids)):
        raise ReconcileError(dim + " 分桶重了题：同一枚出现在两桶里")
    return out, total


def denominator_account(fixture_rows, derived, windows, labels):
    """甲案扣除集合两窗相同与否：题源派生那一格与每窗的未答完/批准失败集合，全部现读。"""
    from_reports = {}
    problems = []
    for label, win in zip(labels, windows):
        report = win.get("report") or {}
        block = report.get(quality_eval.SCORABLE_SUBSET_REPORT_KEY) or {}
        if not report:
            from_reports[label] = {"state": NOT_PROVIDED}
            continue
        ids = sorted(str(item) for item in (block.get("deducted_ids") or []))
        from_reports[label] = {"state": "read", "deducted_n": block.get("deducted_n"),
                               "denominator_rows": block.get("denominator_rows"), "deducted_ids": ids}
        if ids != sorted(derived["deducted_ids"]):
            problems.append(label + " 报告上的扣除清单与现场重算不同源："
                            + "、".join(sorted(set(ids) ^ set(derived["deducted_ids"]))) or label)
        if block.get("deducted_n") != derived["deducted_n"]:
            problems.append(label + " 报告上的扣除枚数 " + str(block.get("deducted_n")) + " ≠ 现算 "
                            + str(derived["deducted_n"]))
        if block.get("denominator_rows") != derived["denominator_rows"]:
            problems.append(label + " 报告上的分母 " + str(block.get("denominator_rows")) + " ≠ 现算 "
                            + str(derived["denominator_rows"]))
    if problems:
        raise ReconcileError("甲案扣除集合三向对账不上：" + "；".join(problems))
    per_window = {}
    for label, win in zip(labels, windows):
        ledger = win["ledger"]
        if ledger is None:
            per_window[label] = {"state": NOT_PROVIDED}
            continue
        summary = quality_eval.summarize_approval_ledger(fixture_rows, ledger)
        error_ids = sorted(row_id for row_id, side in ledger.items()
                           if side.get("kind") == ERROR_EVENT_KIND)
        uncompleted = sorted(set(error_ids) | set(summary["approval_failed_ids"]))
        per_window[label] = {
            "state": "read",
            "ledger_rows": summary["ledger_rows"],
            "hitl_pre_n": summary["hitl_pre_n"], "hitl_pre_ids": summary["hitl_pre_ids"],
            "approved_final_n": summary["approved_final_n"],
            "approved_final_ids": summary["approved_final_ids"],
            "approval_failed_n": summary["approval_failed_n"],
            "approval_failed_ids": summary["approval_failed_ids"],
            "error_event_n": len(error_ids), "error_event_ids": error_ids,
            "uncompleted_or_failed_n": len(uncompleted),
            "uncompleted_or_failed_ids": uncompleted,
            "attempts_gt_1_ids": sorted(row_id for row_id, side in ledger.items()
                                        if (side.get("attempt") or 1) > 1),
            "ledger_rows_not_in_fixture": summary["ledger_rows_not_in_fixture"],
        }
    diffs = {}
    if len(labels) == 2 and all(per_window[label]["state"] == "read" for label in labels):
        for key in ("hitl_pre_ids", "approved_final_ids", "approval_failed_ids", "error_event_ids",
                    "uncompleted_or_failed_ids", "attempts_gt_1_ids"):
            a_set = set(per_window[labels[0]][key])
            b_set = set(per_window[labels[1]][key])
            if a_set != b_set:
                diffs[key] = {"only_in_" + labels[0]: sorted(a_set - b_set),
                              "only_in_" + labels[1]: sorted(b_set - a_set)}
    return {
        "fixture_derived": {"deducted_n": derived["deducted_n"],
                            "denominator_rows": derived["denominator_rows"],
                            "deducted_ids": sorted(derived["deducted_ids"]),
                            "basis": derived["basis"], "rule": derived["rule"]},
        "per_report": from_reports,
        "identical_across_windows_by_fixture": all(
            value.get("deducted_ids", sorted(derived["deducted_ids"])) == sorted(derived["deducted_ids"])
            for value in from_reports.values() if value.get("state") == "read"),
        "per_window_run_sets": per_window,
        "run_set_window_diffs": diffs,
        "note": "题源派生那一格（丙案＝从 correctness 分母点名扣除）两窗必然同一份：两窗共用同一枚"
                " sha256 的题集，本件仍逐窗现读对账，不抄纸面句数。真正会随窗变的是"
                "「未答完／批准失败」那一族，它的两窗差异在 run_set_window_diffs 里逐枚点名。",
    }


def reconcile_with_report(label, win, derived, category_buckets, expect_total):
    """拿在册报告当独立见证：总数、尺一、尺二、逐族分数与 total 全对一遍，破一枚就 rc=2。"""
    report = win.get("report")
    if not report:
        return {"state": NOT_PROVIDED, "note": "没交 " + label + " 的报告 ⇒ 这一窗只跟题集对账"}
    problems = []
    if report.get("total") != expect_total:
        problems.append("报告 total＝" + str(report.get("total")) + " ≠ 在册判据范围 "
                        + str(expect_total))
    recomputed = round(sum(1 for value in win["correct"].values() if value) / expect_total, 4)
    if report.get("answer_correctness") != recomputed:
        problems.append("尺一：报告 answer_correctness＝" + str(report.get("answer_correctness"))
                        + " ≠ 本件用在册尺现算 " + str(recomputed))
    subset = quality_eval.correctness_subset_ruler(win["results"], derived)
    if report.get(quality_eval.SUBSET_RULER_KEY) != subset[quality_eval.SUBSET_RULER_KEY]:
        problems.append("尺二：报告 " + str(report.get(quality_eval.SUBSET_RULER_KEY))
                        + " ≠ 现算 " + str(subset[quality_eval.SUBSET_RULER_KEY]))
    metrics = report.get("category_metrics") or {}
    checked = 0
    for bucket in category_buckets:
        cell = metrics.get(bucket["name"])
        if cell is None:
            problems.append("报告的 category_metrics 里没有「" + bucket["name"] + "」这一族")
            continue
        checked += 1
        if cell.get("total") != bucket["n"]:
            problems.append(bucket["name"] + "：报告 total＝" + str(cell.get("total"))
                            + " ≠ 分桶 n＝" + str(bucket["n"]))
        if round(float(cell.get("correctness") or 0.0), 4) != bucket[label]["score"]:
            problems.append(bucket["name"] + "：报告 correctness＝" + str(cell.get("correctness"))
                            + " ≠ 分桶 " + _fmt_score(bucket[label]["score"]))
    extra = sorted(set(metrics) - {bucket["name"] for bucket in category_buckets})
    if extra:
        problems.append("报告里有本件分桶没有的族：" + "、".join(extra))
    if problems:
        raise ReconcileError(label + " 与在册报告对账不上：" + "；".join(problems))
    return {"state": "matched", "answer_correctness": recomputed,
            "scorable_subset": subset[quality_eval.SUBSET_RULER_KEY],
            "categories_checked": checked, "evidence_coverage": report.get("evidence_coverage")}

def read_pair(answers_a, answers_b, fixture, sidecar_a=None, sidecar_b=None, report_a=None,
              report_b=None, window_a=None, window_b=None, parity=None,
              expect_total=EXPECTED_TOTAL_IN_BOOK, backend_a=None, backend_b=None):
    """主读法：四本账 × 两窗 → 尺现判 → 两维分桶 → 翻分逐题归因 → 三向对账。"""
    labels = (_label_of(answers_a), _label_of(answers_b))
    fixture_sha = _sha256(fixture)
    fixture_rows, fixture_by_id = load_fixture_rows(fixture)
    if len(fixture_rows) != expect_total:
        raise RefuseError("题集只有 " + str(len(fixture_rows)) + " 枚，而 A④ 的在册判据范围是 "
                          + str(expect_total) + " 枚 ⇒ 这份题集出不了那一格的数")
    wins = [read_window(label, path, sidecar, report, window, expect_total)
            for label, path, sidecar, report, window in (
                (labels[0], answers_a, sidecar_a, report_a, window_a),
                (labels[1], answers_b, sidecar_b, report_b, window_b))]
    for win in wins:
        win["answers_by_id"] = index_answers(win["answers"], set(fixture_by_id), win["label"],
                                             expect_total)
        win["correct"], win["results"] = score_window(fixture_rows, win["answers_by_id"])
    pairing = pairing_gate(wins[0], wins[1], fixture_sha, (backend_a, backend_b))
    wins[0]["backend"], wins[1]["backend"] = pairing["index_backend_a"], pairing["index_backend_b"]
    parity_doc = load_parity(parity, set(fixture_by_id))
    for win in wins:
        attach_question_facts(win, fixture_rows, parity_doc)
    derived = quality_eval.derive_scorability(fixture_rows)
    flips = build_flips(fixture_rows, wins[0], wins[1], labels[0], labels[1])
    buckets = {}
    conservation = {}
    for dim in DIMS:
        buckets[dim], conserved = bucketize(dim, fixture_rows, derived, wins, labels, flips)
        conservation[dim] = {"sum_n": conserved, "fixture_rows": len(fixture_rows),
                             "expect_total": expect_total,
                             "ok": conserved == len(fixture_rows) == expect_total}
        if not conservation[dim]["ok"]:
            raise ReconcileError(dim + " 分桶不守恒：Σn＝" + str(conserved) + "／题集＝"
                                 + str(len(fixture_rows)) + "／在册判据范围＝" + str(expect_total))
    denominator = denominator_account(fixture_rows, derived, wins, labels)
    crosscheck = {label: reconcile_with_report(label, win, derived, buckets[DIM_CATEGORY],
                                               expect_total)
                  for label, win in zip(labels, wins)}

    leg_zero = {None: [], "chroma": [], "pg": []}
    if parity_doc is not None:
        for prefix in ("chroma", "pg"):
            leg_zero[prefix] = sorted(row_id for row_id, item in parity_doc["by_id"].items()
                                      if int(item.get(prefix + "_rows") or 0) == 0)
        for flip in flips:
            for side in ("hi", "lo"):
                facts = flip["evidence"][side + "_leg"]
                if facts is not None:
                    flip["evidence"][side + "_leg_zero_rows"] = facts["rows"] == 0
            flip["evidence"]["in_chroma_zero_family"] = flip["id"] in leg_zero["chroma"]
            flip["evidence"]["in_pg_zero_family"] = flip["id"] in leg_zero["pg"]

    evidence_disagreements = []
    kind_missing = []
    for win in wins:
        if win["ledger"] is None:
            kind_missing.append(win["label"])
            continue
        for row_id, side in win["ledger"].items():
            if side.get("evidence_n") is None or not win["q"].get(row_id):
                continue
            if int(side["evidence_n"]) != len(win["q"][row_id]["citations"]):
                evidence_disagreements.append({"label": win["label"], "id": row_id,
                                               "ledger_evidence_n": int(side["evidence_n"]),
                                               "answers_evidence_n": len(win["q"][row_id]["citations"])})
    down_flips = [item for item in flips if item["direction"] == "down"]
    return {
        "tool": "scripts/r580_per_class_attribution.py",
        "labels": {"a": labels[0], "b": labels[1]},
        "inputs": {"fixture": {"path": str(fixture), "lines": len(fixture_rows),
                               "sha256": fixture_sha,
                               "dims": {dim: len({str(row.get(dim) or UNCLASSIFIED)
                                                  for row in fixture_rows}) for dim in DIMS}},
                   "parity": ({"path": parity_doc["path"], "tool": parity_doc["tool"],
                               "generated_at": parity_doc["generated_at"], "k": parity_doc["k"],
                               "n": parity_doc["n"],
                               "summary": {key: parity_doc["summary"].get(key) for key in
                                           ("questions", "same_set", "differing_set",
                                            "questions_zero_overlap", "mean_overlap_ratio",
                                            "chroma_zero_rows", "pg_zero_rows",
                                            "pg_index_vs_exact_same_set",
                                            "chroma_index_vs_exact_same_set")}}
                          if parity_doc is not None else {"state": NOT_PROVIDED}),
                   "windows": [{"label": win["label"], "answers": win["answers_path"],
                                "answers_lines": len(win["answers"]), "answers_sha256": win["sha256"],
                                "sidecar": win["sidecar_path"] or NOT_PROVIDED,
                                "sidecar_rows": len(win["ledger"]) if win["ledger"] is not None else None,
                                "sidecar_collapsed": win["ledger_collapsed"],
                                "report": win["report_path"] or NOT_PROVIDED,
                                "window": win["window_path"] or NOT_PROVIDED,
                                "backend": win["backend"],
                                "correct_n": sum(1 for value in win["correct"].values() if value),
                                "total": expect_total,
                                "score": round(sum(1 for value in win["correct"].values() if value)
                                              / expect_total, 4),
                                "evidence_empty_n": sum(1 for row_id in fixture_by_id
                                                        if not win["q"][row_id]["citations"])}
                               for win in wins]},
        "pairing": pairing,
        "conservation": conservation,
        "headline": {"flips_n": len(flips),
                     "down_n": len(down_flips),
                     "up_n": len(flips) - len(down_flips),
                     "down_ids": sorted(item["id"] for item in down_flips),
                     "up_ids": sorted(item["id"] for item in flips if item["direction"] == "up"),
                     "down_by_category": sorted({item[DIM_CATEGORY] for item in down_flips}),
                     "flips_by_category": sorted({item[DIM_CATEGORY] for item in flips}),
                     "class_totals": _class_tally(flips),
                     "down_class_totals": _class_tally(down_flips)},
        "buckets": {dim: [{key: value for key, value in bucket.items() if key != "ids"}
                          for bucket in buckets[dim]] for dim in DIMS},
        "bucket_membership": {dim: {bucket["name"]: bucket["ids"] for bucket in buckets[dim]}
                              for dim in DIMS},
        "verdicts": {dim: [{"name": bucket["name"], "verdict": bucket["verdict"],
                            "basis": bucket["verdict_basis"]} for bucket in buckets[dim]]
                     for dim in DIMS},
        "flips": flips,
        "denominator_account": denominator,
        "report_crosscheck": crosscheck,
        "leg_zero_rows": {key: value for key, value in leg_zero.items() if key},
        "diagnostics": {"evidence_n_disagreements": evidence_disagreements,
                        "sidecar_not_provided": kind_missing,
                        "kind_missing_n": sum(1 for win in wins for row_id in fixture_by_id
                                              if not win["q"][row_id]["kind_available"]),
                        "note": "kind_missing_n 只说明侧车缺了几枚，不参与判定；分母口径那一族"
                                "只有拿到在册 kind 才证得到"},
        "a4_scope_note": "本格只交数：verdicts 的三档（达／不达／不可判）是对 A④ 判据的逐桶对照，"
                         "整格达标与否由总控裁，本件无权宣布任何一档算整格通过。",
    }


def _tally_text(tally):
    """把一类计数念成"检索腿1／量具取不到2"，全零就交一个短横。"""
    return "／".join(cls + str(tally[cls]) for cls in CLASS_ORDER if tally.get(cls)) or "-"


def _bucket_line(label_a, label_b, bucket):
    name = bucket["name"]
    a, b = bucket[label_a], bucket[label_b]
    tally = _tally_text(bucket.get("down_flip_classes", {}))
    up_tally = _tally_text(bucket.get("up_flip_classes", {}))
    return ("| " + name + " | " + str(bucket["n"]) + " | "
            + str(a["correct_n"]) + "/" + str(a["denom"]) + "=" + _fmt_score(a["score"]) + " | "
            + str(b["correct_n"]) + "/" + str(b["denom"]) + "=" + _fmt_score(b["score"]) + " | "
            + str(a["scorable_correct_n"]) + "/" + str(a["scorable_denom"]) + "="
            + _fmt_score(a["scorable_score"]) + " | "
            + str(b["scorable_correct_n"]) + "/" + str(b["scorable_denom"]) + "="
            + _fmt_score(b["scorable_score"]) + " | "
            + format(bucket["delta_correct_n"], "+d") + " " + format(bucket["delta_score"], "+.4f")
            + " " + bucket["direction"] + " | " + tally + " | " + up_tally + " | "
            + bucket["verdict"] + " |")


BUCKET_HEADER = ("| 桶 | n | a: correct/denom=score | b: correct/denom=score | "
                 "a: 可判子集 | b: 可判子集 | Δcorrect Δscore 方向 | 退步归因 | 进步归因 | 档 |")


def _leg_brief(leg):
    if not leg:
        return NOT_MEASURED
    return (leg["leg"] + "腿 top-" + str(leg["k"]) + "＝[" + ",".join(leg["topk_ids"])
            + "] 本腿独有＝[" + ",".join(leg["only_ids"]) + "] 本腿行数＝" + str(leg["rows"])
            + " same_set＝" + json.dumps(leg["same_set"], ensure_ascii=False))


def render(result, show_rows=True):
    """纸面交回：两维分桶表＋逐题点名（chunk 级差异）＋甲案扣除集合现读＋逐桶档＋对账留痕。"""
    label_a, label_b = result["labels"]["a"], result["labels"]["b"]
    wins = {item["label"]: item for item in result["inputs"]["windows"]}
    pairing = result["pairing"]
    headline = result["headline"]
    lines = ["[r580] A④ 逐类归因：a＝" + label_a + "（index_backend＝"
             + json.dumps(pairing["index_backend_a"], ensure_ascii=False) + "，"
             + (pairing["backend_a_note"] or "在册读后端名") + "）→ b＝" + label_b
             + "（index_backend＝" + json.dumps(pairing["index_backend_b"], ensure_ascii=False) + "）",
             "[r580] 尺＝app/quality/eval.py::_is_correct（在册那一把，经模块属性调用，本件不另写）"]
    lines.append("[r580] 输入逐枚现读：")
    for item in result["inputs"]["windows"]:
        lines.append("        " + item["label"] + " answers＝" + item["answers"] + " 行数＝"
                     + str(item["answers_lines"]) + " sha256[:12]＝" + item["answers_sha256"][:12]
                     + " 尺一＝" + str(item["correct_n"]) + "/" + str(item["total"]) + "="
                     + _fmt_score(item["score"]) + " 空引证＝" + str(item["evidence_empty_n"]) + " 枚")
        lines.append("                侧车＝" + str(item["sidecar"]) + "（" + str(item["sidecar_rows"])
                     + " 行，折叠＝" + str(item["sidecar_collapsed"]) + "） 报告＝"
                     + str(item["report"]) + " 窗记＝" + str(item["window"]))
    fixture = result["inputs"]["fixture"]
    lines.append("        题集＝" + fixture["path"] + " 行数＝" + str(fixture["lines"])
                 + " sha256＝" + fixture["sha256"])
    parity = result["inputs"]["parity"]
    if parity.get("state") == NOT_PROVIDED:
        lines.append("        parity＝未交 ⇒ 检索腿一类一律落进量具取不到（不许猜）")
    else:
        lines.append("        parity＝" + parity["path"] + "（" + parity["tool"] + "，k＝"
                     + str(parity["k"]) + "，题数＝" + str(parity["n"]) + "，generated_at＝"
                     + str(parity["generated_at"]) + "） summary＝"
                     + json.dumps(parity["summary"], ensure_ascii=False, sort_keys=True))
    lines.append("[r580] 对照前提（现读，不假设）：mode＝" + pairing["mode"] + " revision＝"
                 + pairing["revision"] + " transport＝" + pairing["transport"] + " shard_size＝"
                 + str(pairing["shard_size"]) + " container＝" + pairing["container"]
                 + " 起窗 a＝" + str(pairing["started_at_a"]) + " b＝" + str(pairing["started_at_b"]))
    lines.append("[r580] 翻分 " + str(headline["flips_n"]) + " 枚＝退步 " + str(headline["down_n"])
                 + "／进步 " + str(headline["up_n"]) + "，散在 " + str(len(headline["flips_by_category"]))
                 + " 个族；退步归因合计＝" + "／".join(cls + str(headline["down_class_totals"][cls])
                                                     for cls in CLASS_ORDER))
    for dim in DIMS:
        lines.append("")
        lines.append("[r580] 分桶表（" + dim + "）：a＝" + label_a + "，b＝" + label_b)
        lines.append(BUCKET_HEADER)
        for bucket in result["buckets"][dim]:
            lines.append(_bucket_line(label_a, label_b, bucket))
        conserved = sum(bucket["n"] for bucket in result["buckets"][dim])
        check = result["conservation"][dim]
        lines.append("[r580] 守恒：" + dim + " Σn＝" + str(conserved) + "／题集＝"
                     + str(check["fixture_rows"]) + "／在册判据范围＝" + str(check["expect_total"])
                     + " ⇒ " + ("ok" if check["ok"] else "破了（rc≠0）")
                     + "；桶数＝" + str(len(result["buckets"][dim])))
        lines.append("[r580] 分数下降的桶：" + ("、".join(bucket["name"] for bucket in
                                                        result["buckets"][dim]
                                                        if bucket["direction"] == "down") or "无"))
    if show_rows:
        lines.append("")
        lines.append("[r580] 退步逐题点名（" + label_a + " 判对 → " + label_b + " 判错）：")
        for flip in result["flips"]:
            if flip["direction"] != "down":
                continue
            lines.append("  " + flip["id"] + "｜族＝" + flip[DIM_CATEGORY] + "｜档＝" + flip[DIM_TIER]
                         + "｜归因＝" + flip["class"] + "｜代码＝" + flip["code"])
            lines.append("        锚词＝" + json.dumps(flip["evidence"]["anchors"], ensure_ascii=False))
            lines.append("        " + label_a + " 引证（chunk 级）＝"
                         + json.dumps(flip["evidence"]["hi_citations" if flip["evidence"]["hi_label"]
                                                          == label_a else "lo_citations"],
                                      ensure_ascii=False))
            lines.append("        " + label_b + " 引证（chunk 级）＝"
                         + json.dumps(flip["evidence"]["lo_citations" if flip["evidence"]["hi_label"]
                                                          == label_a else "hi_citations"],
                                      ensure_ascii=False))
            lines.append("        只在 " + label_a + "＝" + json.dumps(flip["evidence"]["diff_a_only"],
                                                                      ensure_ascii=False)
                         + " 只在 " + label_b + "＝" + json.dumps(flip["evidence"]["diff_b_only"],
                                                                 ensure_ascii=False))
            lines.append("        载锚引证差（赢的一窗独有）＝"
                         + json.dumps(flip["evidence"]["carrier_delta_hi_only"], ensure_ascii=False)
                         + " 两窗引证集合相同＝" + json.dumps(
                             flip["evidence"]["citations_identical_chunk_level"]))
            lines.append("        本腿读数：" + _leg_brief(flip["evidence"]["hi_leg"]))
            lines.append("        对腿读数：" + _leg_brief(flip["evidence"]["lo_leg"]))
            if flip["class"] == CLASS_LEG or flip["evidence"].get("note") \
                    or flip["evidence"].get("leg_claim") or flip["evidence"].get("wording_claim"):
                lines.append("        说理：" + str(flip["evidence"].get("leg_claim")
                                                   or flip["evidence"].get("wording_claim")
                                                   or flip["evidence"].get("note")))
            lines.append("        在册 kind：a＝" + str(flip["evidence"]["lo_kind" if
                                                        flip["evidence"]["hi_label"] == label_a
                                                        else "hi_kind"]) + " b＝"
                         + str(flip["evidence"]["hi_kind" if flip["evidence"]["hi_label"] == label_a
                                else "lo_kind"])
                         + "｜属 Chroma 空返回 21 族＝" + json.dumps(flip["evidence"].get(
                             "in_chroma_zero_family"), ensure_ascii=False)
                         + " 属 PG 空返回族＝" + json.dumps(flip["evidence"].get("in_pg_zero_family"),
                                                          ensure_ascii=False))
        lines.append("")
        lines.append("[r580] 进步逐题点名（" + label_a + " 判错 → " + label_b + " 判对）：")
        for flip in result["flips"]:
            if flip["direction"] != "up":
                continue
            lines.append("  " + flip["id"] + "｜族＝" + flip[DIM_CATEGORY] + "｜档＝" + flip[DIM_TIER]
                         + "｜归因＝" + flip["class"] + "｜代码＝" + flip["code"]
                         + "｜载锚引证差＝" + json.dumps(flip["evidence"]["carrier_delta_hi_only"],
                                                       ensure_ascii=False))
            lines.append("        只在 " + label_a + "＝" + json.dumps(flip["evidence"]["diff_a_only"],
                                                                      ensure_ascii=False)
                         + " 只在 " + label_b + "＝" + json.dumps(flip["evidence"]["diff_b_only"],
                                                                 ensure_ascii=False))
            lines.append("        说理：" + str(flip["evidence"].get("leg_claim")
                                               or flip["evidence"].get("wording_claim")
                                               or flip["evidence"].get("note")
                                               or flip["evidence"].get("wording_claim")))
    lines.append("")
    lines.append("[r580] 甲案扣除集合现读（判据③：一枚都不抄总控的句数）：")
    account = result["denominator_account"]
    derived_block = account["fixture_derived"]
    lines.append("        题源派生（现读 derive_scorability）：扣除＝" + str(derived_block["deducted_n"])
                 + " 枚／进分母＝" + str(derived_block["denominator_rows"]) + " 枚")
    lines.append("        逐枚点名＝" + json.dumps(derived_block["deducted_ids"], ensure_ascii=False))
    for label, cell in account["per_report"].items():
        lines.append("        " + label + " 报告上那格＝" + json.dumps(cell, ensure_ascii=False)[:400])
    lines.append("        两窗扣除清单与现算全等＝" + json.dumps(
        account["identical_across_windows_by_fixture"], ensure_ascii=False) + "（同一份题集 ⇒ 按构造相同；本件仍逐窗现读）")
    for label, cell in account["per_window_run_sets"].items():
        lines.append("        " + label + " 未答完／批准失败现读＝" + json.dumps(cell, ensure_ascii=False))
    lines.append("        两窗之间会变的那几格差异＝" + json.dumps(account["run_set_window_diffs"],
                                                                  ensure_ascii=False))
    lines.append("        说明：" + account["note"])
    lines.append("")
    lines.append("[r580] 与在册报告对账（独立见证）：" + json.dumps(result["report_crosscheck"],
                                                                   ensure_ascii=False))
    lines.append("[r580] 空返回两腿读数：chroma 腿 0 行的题＝"
                 + json.dumps(result["leg_zero_rows"].get("chroma", []), ensure_ascii=False))
    lines.append("[r580] 诊断（不参与判定）：" + json.dumps(
        {"evidence_n_disagreements": result["diagnostics"]["evidence_n_disagreements"],
         "sidecar_not_provided": result["diagnostics"]["sidecar_not_provided"],
         "kind_missing_n": result["diagnostics"]["kind_missing_n"]}, ensure_ascii=False))
    lines.append("")
    lines.append("[r580] 逐桶档（达／不达／不可判＋凭据）：")
    for dim in DIMS:
        lines.append("        维度＝" + dim)
        for cell in result["verdicts"][dim]:
            lines.append("        " + cell["name"] + "：" + cell["verdict"] + "｜" + cell["basis"])
    lines.append("")
    lines.append("[r580] " + result["a4_scope_note"])
    return lines

class _Parser(argparse.ArgumentParser):
    """用法错（没点 answers、认不出的 ``--format``）一律按"拒绝出数"出门。

    🔴 argparse 自己用 rc=2 报用法错，而 2 在本件里是"对账不上"的专号——两种意思不能共用一枚码：
    拿错参数跑出来的 2 会被下游读成"两窗不构成对照"，那是另一种假话。
    """

    def error(self, message):
        sys.stderr.write("用法错（rc=" + str(EXIT_REFUSE) + "＝拒绝出数，不是对账不上）：" + str(message) + "\n")
        raise SystemExit(EXIT_REFUSE)


def build_parser():
    parser = _Parser(
        description="R580：把 A④「逐类不退化」的退步按 category／tier 两维切开并证到题级（只读、离线）")
    parser.add_argument("--answers-a", required=True, help="基线那一窗的 answers jsonl（A④ 里＝切读之前）")
    parser.add_argument("--answers-b", required=True, help="对照那一窗的 answers jsonl（A④ 里＝切读之后）")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE),
                        help="题集（只读）：category／tier 两列是分桶依据，must_contain 是在册尺的锚词")
    parser.add_argument("--sidecar-a", help="默认取 answers 同名兄弟件 <label>-sidecar.jsonl")
    parser.add_argument("--sidecar-b")
    parser.add_argument("--report-a", help="默认取 <label>-report.json（在册报告，用作独立见证）")
    parser.add_argument("--report-b")
    parser.add_argument("--window-a", help="默认取 <label>.window.json（读后端那一格的唯一真源）")
    parser.add_argument("--window-b")
    parser.add_argument("--parity", help="在册量具 r59_recall_compare 的对读读数（默认取 answers 同目录的 p3-parity.json）")
    parser.add_argument("--backend-a", help="纸面声明的读后端；与窗记现读不一致 ⇒ rc=2")
    parser.add_argument("--backend-b")
    parser.add_argument("--expect-total", type=int, default=EXPECTED_TOTAL_IN_BOOK,
                        help="在册判据范围；任何一窗题数≠它 ⇒ 直接拒绝出数（rc=3）")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--no-rows", action="store_true", help="只交两维分桶表与对账，不交逐题点名")
    parser.add_argument("--out", default=None, help="json 读数落盘的位置（只写这一枚新文件，输入一律只读）")
    return parser


def resolve_arguments(args):
    """把没点名的兄弟件按标签补齐：``<label>-sidecar.jsonl``／``<label>-report.json``／``<label>.window.json``。"""
    answers_a, answers_b = Path(args.answers_a), Path(args.answers_b)
    return {
        "answers_a": str(answers_a), "answers_b": str(answers_b), "fixture": args.fixture,
        "sidecar_a": args.sidecar_a or str(_sibling(answers_a, "-sidecar.jsonl")),
        "sidecar_b": args.sidecar_b or str(_sibling(answers_b, "-sidecar.jsonl")),
        "report_a": args.report_a or str(_sibling(answers_a, "-report.json")),
        "report_b": args.report_b or str(_sibling(answers_b, "-report.json")),
        "window_a": args.window_a or str(_sibling(answers_a, ".window.json")),
        "window_b": args.window_b or str(_sibling(answers_b, ".window.json")),
        "parity": args.parity if args.parity is not None \
            else str(answers_b.resolve().parent / "p3-parity.json"),
        "backend_a": args.backend_a, "backend_b": args.backend_b,
        "expect_total": args.expect_total,
    }


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = read_pair(**resolve_arguments(args))
    except RefuseError as error:
        print("[r580][拒绝出数 rc=3] " + str(error))
        return EXIT_REFUSE
    except ReconcileError as error:
        print("[r580][对账不上 rc=2] " + str(error))
        return EXIT_RECONCILE
    if args.format == "json":
        payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=False)
        if args.out:
            with io.open(args.out, "w", encoding="utf-8", newline="") as handle:
                handle.write(payload)
            print("[r580] 读数落盘＝" + str(args.out) + " sha256[:12]＝" + _sha256(args.out)[:12])
        else:
            print(payload)
    else:
        for line in render(result, show_rows=not args.no_rows):
            print(line)
    code = EXIT_OK
    for dim in DIMS:
        if not result["conservation"][dim]["ok"]:
            print("[r580][对账不上 rc=2] " + dim + " 的分桶没守恒到在册判据范围")
            code = EXIT_RECONCILE
    if result["diagnostics"]["evidence_n_disagreements"]:
        print("[r580][警告] 侧车 evidence_n 与 answers 引证枚数对不上的枚数＝"
              + str(len(result["diagnostics"]["evidence_n_disagreements"])) + "（不改 rc，纸面点名）")
    return code


if __name__ == "__main__":
    sys.exit(main())