#!/usr/bin/env python3
"""R454：一窗多判据的形状窗计划器（跟进单 §128 二节判据②）。

病灶（跟进单 §128 二节原文）：五道门的格是**分扇窗**跑的——run9 相 1 全量串行 111.2 分钟、
run9c 只跑队列道 20 枚，一扇窗只拿一两格就收工，剩下的格下一班再开一次窗，
同一批题被反复重放，墙钟全花在重复上。本件把「本班要判的格集合」压成**一扇窗**的多相计划。

三条硬规矩（判据②）：
1. 一次请求只出一扇窗：`plan_window()` 返回的 `windows` 恒为 1 枚；同一批格要开第二扇
   直接 `DuplicateWindowError`——planner 自己不许生成第二扇。
2. 分数与时延类格不在形状窗范围内：被点名请求就拒（`ScopeViolation`），读数表里无条件写下这句话。
   凭据＝跟进单 §128 三节那句「时延类判据要样本 ≥100，只有形状类格可以走子集」。
3. 批准次数是算出来的：逐枚取上一窗 sidecar 的 `approval_rounds`，不按族拍脑袋。
   —— run9 现场（本文件不写死，现读 `docs/testing/sidecar-run9.jsonl`）：`approval` 族 6 枚
   一枚都没触发批准轮，触发的是 report/chart/tool/insight/scope。

相的划分不是口味：`REPORT_LANE_VIA_QUEUE` 一开，报告档的回答就变成整段取回，
A②「流式逐字无缺」必然读成 `(text_frames, max_stream_frames) = (1, 1)`——D 三格与 A②
在同一轮里物理互斥（runbook「两相一窗」那节写死）。所以一扇窗内允许多**相**，
每相一套开关状态，相之间必须复跑 P-18；被相逼出来的重复题号在计划里单列，不藏。

全程离线：只读仓内文本文件，零模型、零网络、零容器、不起服务、不动电源方案。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

BANK_REL = "tests/fixtures/business_evaluation_100.jsonl"
#: 文件名里的 30 是派工写域锁死的名字，改不得；内容自 09-28 返工起是 SUBSET_SIZE 行
#: （现值 33）。以件内 §二 的逐行账为准，不以文件名上的数字为准。
SUBSET_REL = "docs/testing/bank-shape-subset-30.jsonl"
EVIDENCE_REL = "docs/testing/sidecar-run9.jsonl"
READOUT_REL = "docs/testing/shape-window-readout-2026-09-28.md"
#: R453（Leibniz）的读数名册本体。这张表只许 import 过来用，抄第二份就是两本账，
#: 而两本账的交集今天实测＝0 枚（总控 09-28 现取），真开窗时对面会把本计划判红。
R453_ROSTER_REL = "scripts/eval_cloud_window_readout.py"

FAMILY_FLOOR = 2
#: 返工令第 5 条：report 族配额 3 抬到 12——D 三格要跑满报告档那 12 枚，
#: 与 runbook「两相一窗」相 2 的 12 枚同口径；approval 仍按原判据①留 3 枚。
FAMILY_FLOOR_OVERRIDES = {"approval": 3, "report": 12}
#: 子集规模＝族配额之和，算式写死在这儿：
#:   report 12 ＋ approval 3 ＋ 其余 9 族（chart/chat/data/insight/metric/scope/tool/unsupported/doc）各 2 ＝ 12 + 3 + 18 ＝ 33
#: 30 装不下 33 枚最低配额，硬留在 30 就是让 report 的新配额落空，所以抬到 33。
#: 最低配额之外不再按比例加抽：形状窗买的是「每一族的形状都出现过一次」，
#: 多抽 doc/metric 只加墙钟不加形状覆盖——那正是本单要治的病。
SUBSET_SIZE = 33
FAMILIES = ("approval", "chart", "chat", "data", "doc", "insight", "metric", "report",
            "scope", "tool", "unsupported")

SCOPE_SENTENCE = "分数与时延类格不在形状窗范围内"

#: sidecar 里那一枚批准轮数读数位（它是**算料键名**，不是 R453 的格名）。
#: 计划里的批准次数就是逐枚加它，所以这一位的归属必须能反查回名册，不能当野数据用。
LEDGER_FIELD = "approval_rounds"
AUTO_APPROVE_SENTENCE = ("自动批准只允许打在评测容器＋评测账号那一条路径，"
                         "生产/演示路径一个字不碰")
UNVERIFIED = "未验"

STREAM_PHASE = "相1-流式道"
QUEUE_PHASE = "相2-队列道"


class PlannerError(Exception):
    """本件所有可预期失败的基类，消息里必须带教学句。"""


class ScopeViolation(PlannerError):
    """分数或时延类格被请求进形状窗。"""


class DuplicateWindowError(PlannerError):
    """同一批格开第二扇窗。"""


class SubsetError(PlannerError):
    """子集 bank 不合格：外来 id、改字、族覆盖不足。"""


class RosterError(PlannerError):
    """绑定落在 R453 名册之外：两本账从此对不上，开窗当场会被对面判红。"""


class ReadoutError(PlannerError):
    """读数表骨架不合格：未验格被写成过、缺行、多行。"""


@dataclass(frozen=True)
class Cell:
    cid: str
    label: str
    gate: str
    shape: bool
    switches: tuple
    families: tuple
    surface: str
    blocker: str
    why_shape: str
    #: 不变量格（如零重试零哨兵）读的是「每一 play」，它自己不点题；
    #: 让它点题会把整子集全拖进队列相，重复播放翻倍——正是本单要治的病。
    drives_questions: bool = True
    #: 这一枚判据格靠 R453 名册里的哪几格读数来证。空元组＝名册里没有任何一格能证它，
    #: 那它今天必须落进 unattainable_here（返工令第 3 条：不许硬凑映射）。
    r453_cells: tuple = ()
    #: 这一枚判据格「必须同时读到」的读数位：事件名在场 ≠ 载荷非空。
    #: 帧账的 event_tally 只存事件名不存载荷，一条 `sources: []` 空列表在只认事件名那一格
    #: 照样过；D 判据要的是「引用可查回」，空引用不是可查回。供给这些读数位的名册格
    #: 一律由 `r453_reading_fields()` 现读对面件，本件不落第二份清单，也不写死枚数。
    r453_payload_fields: tuple = ()

    @property
    def needs_all_families(self) -> bool:
        return not self.families


CELLS: dict = {}


def _cell(**kwargs) -> Cell:
    item = Cell(**kwargs)
    CELLS[item.cid] = item
    return item


# ---- 形状类格（本班可请求）----
A2 = _cell(
    cid="A2-stream-verbatim",
    label="A② 流式逐字无缺",
    gate="A",
    shape=True,
    switches=(("REPORT_LANE_VIA_QUEUE", "off"),),
    families=(),
    surface="帧账 sidecar-frames：text 事件数 >1 且逐字比对无缺字（missing_chars=extra_chars=0）",
    blocker="",
    why_shape="形状格：判的是「逐片到达」这个形状，与分数无关",
    r453_cells=("frame_shape", )
)
C_PRIV = _cell(
    cid="C-overprivilege",
    label="C 越权",
    gate="C",
    shape=True,
    switches=(("REPORT_LANE_VIA_QUEUE", "off"),),
    families=("scope",),
    surface="sidecar kind/终答 + 跨部门权限题的拒绝形状",
    blocker="production-labels",
    why_shape="形状格：判的是「拒了没有、拒的时候说了什么」",
    r453_cells=("escalation_annotation", "error_class_shape", )
)
C_CACHE = _cell(
    cid="C-cache-annotation",
    label="C 缓存命中显式标注",
    gate="C",
    shape=True,
    switches=(("REPORT_LANE_VIA_QUEUE", "off"),),
    families=(),
    surface="transport 的 cached 位：命中即 raise 停窗（本树现取 scripts/eval_transport_ask_v2.py:818-819）",
    blocker="cache-hit-probe",
    why_shape="形状格：判的是「命中了有没有喊」",
    r453_cells=("escalation_annotation", )
)
D_RETRIEVE = _cell(
    cid="D-report-retrievable",
    label="D 报告档可查回",
    gate="D",
    shape=True,
    switches=(("REPORT_LANE_VIA_QUEUE", "on"),),
    families=("report",),
    surface="GET /api/v1/queue/status/{request_id} 的 sources_present（路由 app/api/v1/chat.py:4882；量具折槽 scripts/eval_transport_ask_v2.py:932）",
    blocker="",
    why_shape="形状格：判的是「那份报告能不能再查回来」",
    r453_cells=("queue_readback", )
)
D_USAGE = _cell(
    cid="D-usage-nonzero",
    label="D usage 非零",
    gate="D",
    shape=True,
    switches=(("REPORT_LANE_VIA_QUEUE", "on"),),
    families=("report",),
    surface="GET /api/v1/queue/status/{request_id} 响应体的 usage 六枚槽（量具点名 scripts/eval_transport_ask_v2.py:869、折槽 :935-941）",
    blocker="",
    why_shape="形状格：判的是「这格有没有值」，不是值多大",
    r453_cells=("usage_fields_present", )
)
D_SOURCES = _cell(
    cid="D-sources-in-stream",
    label="D sources 事件在流里",
    gate="D",
    shape=True,
    switches=(("REPORT_LANE_VIA_QUEUE", "on"),),
    families=("report",),
    surface="帧账 events 里的 sources 事件名＋引用载荷形状（`sources: []` 空列表不算可查回）",
    blocker="",
    why_shape="形状格：判的是「流里有没有这一枚事件、引用载荷是不是非空的形状」",
    r453_cells=("event_surface", "citation_shape", ),
    r453_payload_fields=("sources_present", "sources_shape", )
)
GUARD = _cell(
    cid="zero-retry-zero-sentry",
    label="零重试零哨兵",
    gate="护栏",
    shape=True,
    switches=(),
    families=(),
    surface="sidecar 逐枚 attempt==1 且 sentinel is False",
    blocker="",
    why_shape="形状格：逐枚不变量，两相的每一 play 都要判",
    drives_questions=False,
    r453_cells=("retry_sentinel_shape", )
)

# ---- 分数与时延类格（形状窗一律拒绝，判据②硬规矩第 2 条）----
A1_LATENCY = _cell(
    cid="A1-end-to-end-p95",
    label="A① 端到端 ≤90 s（p95/时延）",
    gate="A",
    shape=False,
    switches=(),
    families=(),
    surface="帧账 wall_ms 逐题复算，样本需 ≥100 枚",
    blocker="",
    why_shape="时延类格：本机全量每冻结点一次，不走子集",
)
A4_SCORE = _cell(
    cid="A4-category-score",
    label="A④ 逐类分数不退化",
    gate="A",
    shape=False,
    switches=(),
    families=(),
    surface="evaluation-report.json 的 category_metrics",
    blocker="",
    why_shape="分数类格：与 run6 可比性要求全 105 题同开关态",
)
C_SCORE = _cell(
    cid="C-bank-score-no-regression",
    label="C 评测集分数不退化",
    gate="C",
    shape=False,
    switches=(),
    families=(),
    surface="evaluation-report.json 的 correctness/evidence",
    blocker="",
    why_shape="分数类格：子集分数与全量分数不同径，不许混报",
)
AGG_SCORE = _cell(
    cid="aggregate-correctness",
    label="整表 correctness/evidence 分数",
    gate="A",
    shape=False,
    switches=(),
    families=(),
    surface="evaluation-report.json 抬头",
    blocker="",
    why_shape="分数类格：子集那几十枚的总分不能当全量 105 枚的总分用",
)

#: ==================== R453 名册：唯一来源是 import ====================
#:
#: 返工令第 1 条钉的是这件事：本件的判据格名与 R453 那本名册的全部读数格名交集＝0，
#: 两单合起来等于零。所以这里的格名**一个都不许自己定义**——名册从对面件现读，
#: 绑定值逐枚回表对；对不上就走 RosterError，不许静默通过（判据②）。


def load_r453(path_text: str = R453_ROSTER_REL):
    """按路径装载 R453 的读数名册件本身（不是抄它的表）。

    对面件在导入期只做两件事：拼一张 CELLS 表、按别名建 REGISTRY（:168-175），
    零 IO、零网络、零容器，所以可以安全地在本件 import 期就拉起来对账。
    """
    target = REPO_ROOT / path_text
    spec = importlib.util.spec_from_file_location("eval_cloud_window_readout", target)
    if spec is None:
        raise RosterError(f"读不到 R453 名册件：{target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


R453 = load_r453()
#: 名册的三张派生表：全部从 import 出来的 CELLS/CLOUD_CELLS 现算，本件不写第二份。
R453_ROSTER = tuple(row["cell"] for row in R453.CELLS)
R453_SHAPE_KIND = "shape"
R453_ROSTER_BY_CELL = {row["cell"]: row for row in R453.CELLS}
R453_CLOUD_CELLS = tuple(R453.CLOUD_CELLS)
R453_LOCAL_ONLY_CELLS = tuple(R453.LOCAL_ONLY_CELLS)


def r453_cell_names() -> tuple:
    "名册里全部在册格名（现算自对面件，不在本件落第二份清单）。"
    return tuple(R453_ROSTER)


def r453_reading_fields(cell_name: str) -> tuple:
    "一枚名册格实际吃哪些读数位：取对面件登记的别名表，本件同样不抄。"
    row = R453_ROSTER_BY_CELL.get(cell_name)
    return tuple(row["aliases"]) if row else ()


#: 一枚判据格的「在场」与「形状」至少要由两枚名册格分着证；同一格一手包办分不出空载荷。
REQUIRED_FIELD_SUPPLIERS_MIN = 2
#: 读数表里那一行的开头标记：validate_readout 按它核对覆盖有没有落账（不是按格名猜）。
COVERAGE_MARKER = "读数位覆盖"


def r453_field_coverage(item: Cell) -> dict:
    """声明的读数位在名册里由谁供给、缺哪几枚、这一枚判据今天准不准闭格。"""
    suppliers = {}
    for field in item.r453_payload_fields:
        suppliers[field] = [name for name in item.r453_cells
                            if field in r453_reading_fields(name)]
    owners = sorted({name for names in suppliers.values() for name in names})
    missing = [field for field, names in suppliers.items() if not names]
    return {
        "fields": list(item.r453_payload_fields),
        "suppliers": suppliers,
        "missing": missing,
        "owner_count": len(owners),
        "closable": bool(item.r453_payload_fields) and not missing
        and len(owners) >= REQUIRED_FIELD_SUPPLIERS_MIN,
    }


def _check_payload_coverage(item: Cell, problems: list) -> None:
    """没凑齐读数位、或同一格一手包办 ⇒ 记一条问题（返工补令：关掉「在场但为空」那枚假绿）。"""
    if not (item.shape and item.r453_payload_fields):
        return
    coverage = r453_field_coverage(item)
    if coverage["missing"]:
        problems.append(f"判据格 {item.cid} 的读数位没凑齐：缺 "
                        f"{'、'.join(coverage['missing'])}——「事件在场」证不了「引用非空」，"
                        f"空引用会被读成可查回")
    elif coverage["owner_count"] < REQUIRED_FIELD_SUPPLIERS_MIN:
        problems.append(f"判据格 {item.cid} 的在场与形状由同一枚名册格一手包办："
                        f"{owners_hint(coverage)}——一手包办分不出空载荷，"
                        f"至少要 {REQUIRED_FIELD_SUPPLIERS_MIN} 枚分着证")


def owners_hint(coverage: dict) -> str:
    return "、".join(sorted({name for names in coverage["suppliers"].values() for name in names}))


def r453_binding(item: Cell) -> tuple:
    """校验一枚格绑的每格名都在名册里；表外一格名 ⇒ RosterError。"""
    for name in item.r453_cells:
        if name not in R453_ROSTER_BY_CELL:
            raise RosterError(
                f"判据格 {item.cid} 绑了名册外的读数格 {name!r}：在册格名只许从 "
                f"{R453_ROSTER_REL} 的 CELLS 现读，抄写或臆造都算红")
    return item.r453_cells


def validate_catalog_binding(cells=None) -> dict:
    """整本 catalog 逐枚对名册，并把「形状格的绑定必须云端可读、被拒格的绑定必须本机专属」钉死。

    这一层是两单接口的真牙：R453 把全册格按 kind 分成 shape/latency/score，
    本件把格分成"形状窗内"与"分数与时延类"。两边分家必须一致——
    我的形状格若绑到对面的 latency/score 格，就等于一边说可云端读、一边把它塞进形状窗。
    """
    binding = {}
    problems = []
    for item in (cells if cells is not None else list(CELLS.values())):
        names = r453_binding(item)
        binding[item.cid] = list(names)
        kinds = {R453_ROSTER_BY_CELL[n]["kind"] for n in names}
        if item.shape:
            wrong = sorted(n for n in names if n not in R453_CLOUD_CELLS)
            if wrong:
                problems.append(f"形状格 {item.cid} 绑了非云端可读的读数格：{'、'.join(wrong)}")
        else:
            wrong = sorted(n for n in names if n not in R453_LOCAL_ONLY_CELLS)
            if wrong:
                problems.append(f"被拒的分数/时延格 {item.cid} 绑了云端可读格：{'、'.join(wrong)}")
        if item.shape and names and kinds and kinds != {R453_SHAPE_KIND}:
            problems.append(f"形状格 {item.cid} 绑到的读数格里有非 shape 种："
                            f"{sorted(kinds - {R453_SHAPE_KIND})}")
        _check_payload_coverage(item, problems)
    if problems:
        raise RosterError("；".join(problems))
    return binding


def r453_unreferenced_cloud_cells() -> list:
    """反向覆盖度（返工令第 4 条）：云端可读格里没被任何 r453_cells 引用的那些。

    报出来是为了"开窗不白读"：这一窗不消费的云端可读格，总控要能一眼看见，
    别让 R453 接线件白准备一摞读数位。
    """
    used = {name for item in CELLS.values() for name in item.r453_cells}
    return [name for name in R453_CLOUD_CELLS if name not in used]


def r453_ledger_binding() -> dict:
    """批准台账那枚算料位归名册里哪一格：拿对面件自己的 REGISTRY 反查（含别名表）。"""
    row = R453.resolve(LEDGER_FIELD)
    return {LEDGER_FIELD: row["cell"] if row else None}


def r453_unproven_shape_cells() -> list:
    """名册里没有任何一格能证的形状格（返工令第 3 条），不许硬凑映射，只能认缺。"""
    return [item.cid for item in CELLS.values() if item.shape and not item.r453_cells]


R453_BINDING = validate_catalog_binding()

SHAPE_CELLS = tuple(c for c in CELLS if CELLS[c].shape)
OUT_OF_SCOPE_CELLS = tuple(c for c in CELLS if not CELLS[c].shape)

BLOCKER_REASONS = {
    "production-labels": (
        "生产 department/classification 现值为空（AGENTS.md pgvector 格③：欠业主侧 "
        "A1 users.department 回填＋A3 密级标签回填，H13 未裁）⇒ 本机拿不到「客户数据上的隔离」"
        "这一形，沙盒合成标签不在此窗"),
    "cache-hit-probe": (
        "P-18 要求开窗前 Redis answer:* 计数为 0（runbook 前置第 8 步），命中即 raise 停窗"
        "⇒ 本窗按纪律只能拿到「零命中」这一负形，正形需要总控另裁一枚探针臂"),
}


@dataclass
class MachineProfile:
    """这台机的能力位。默认值就是今天的真实状态，不是乐观假设。"""

    name: str = "local-shape-window"
    production_labels_backfilled: bool = False
    cache_hit_probe_allowed: bool = False
    sample_cap: int = SUBSET_SIZE

    def blocked_cells(self) -> dict:
        out = {}
        for cid, item in CELLS.items():
            if not item.shape:
                continue
            if item.blocker == "production-labels" and not self.production_labels_backfilled:
                out[cid] = BLOCKER_REASONS[item.blocker]
            elif item.blocker == "cache-hit-probe" and not self.cache_hit_probe_allowed:
                out[cid] = BLOCKER_REASONS[item.blocker]
        return out


def sha256_16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def family_of(qid: str) -> str:
    return qid.split("-", 1)[0]


def line_id(raw: bytes) -> str:
    """取一行里的 id：紧凑写法直接按字节找，找不到再按 JSON 解一次。

    为什么兜这一层：外来 id 若被重新序列化过（冒号后带空格），只认紧凑写法就会把
    "哪一枚题"报成"这一坨字节"，红是红了，账上读不出题号——少一枚可追的凭据。
    """
    marker = b'"id:"'
    start = raw.find(marker)
    if start >= 0:
        rest = raw[start + len(marker):]
        stop = rest.find(b'"')
        if stop >= 0:
            return rest[:stop].decode("utf-8")
    try:
        return str(json.loads(raw.decode("utf-8")).get("id", ""))
    except (ValueError, UnicodeDecodeError):
        return ""


def load_bank_lines(path: Path) -> list:
    """按 keepends 读原始字节行：本体是 CRLF，一个字都不许在转换里漂掉。"""
    raw = path.read_bytes()
    return [line for line in raw.splitlines(keepends=True) if line.strip()]


def bank_index(bank_lines: list) -> dict:
    out = {}
    for line in bank_lines:
        qid = line_id(line)
        if qid in out:
            raise SubsetError(f"题源本体里 id {qid} 出现两次，本体自己就不能定锚")
        out[qid] = line
    return out


def bank_ids(bank_lines: list) -> list:
    return [line_id(line) for line in bank_lines]


def load_approval_evidence(path: Path) -> dict:
    """上一窗 sidecar 的逐枚批准轮数：批准次数的唯一算料。"""
    out = {}
    if not path.exists():
        return out
    for text in path.read_text(encoding="utf-8").splitlines():
        if not text.strip():
            continue
        row = json.loads(text)
        out[str(row.get("id", ""))] = int(row.get("approval_rounds") or 0)
    return out


# ==================== 判据①：分层子集的选取与逐行等值 ====================


def allocate_families(ids: list, total: int = SUBSET_SIZE) -> dict:
    """先给每族 FAMILY_FLOOR 枚，approval/report 抬到 3 枚，余量按族大小做除法优势分配。

    规则先写死再取数，不做人工挑选题面：这样「谁进子集」可复算，
    也免得把子集挑成一组专门好过的题。
    """
    counts = {}
    for qid in ids:
        counts[family_of(qid)] = counts.get(family_of(qid), 0) + 1
    for fam in sorted(counts):
        if fam not in FAMILIES:
            raise SubsetError(f"题源里冒出未登记的族 {fam}，先改 FAMILIES 再谈分层")
    alloc = {fam: FAMILY_FLOOR for fam in FAMILIES}
    for fam, floor in FAMILY_FLOOR_OVERRIDES.items():
        alloc[fam] = max(alloc[fam], floor)
    used = sum(alloc.values())
    if used > total:
        raise SubsetError(f"族最低配额之和 {used} 已超子集规模 {total}，分层规则本身不成立")
    remaining = total - used
    # 除法优势（d'Hondt）逐枚加：比值 = 族大小 /（当前已分 + 1），并列先大族再字母序。
    for _ in range(remaining):
        best = max(
            FAMILIES,
            key=lambda fam: (counts.get(fam, 0) / (alloc[fam] + 1), counts.get(fam, 0),
                             tuple(-ord(ch) for ch in fam)),
        )
        if counts.get(best, 0) <= alloc[best]:
            raise SubsetError(f"族 {best} 已被抽干，余量无处安放：分层规则要重开")
        alloc[best] += 1
    return alloc


def select_ids(ids: list, alloc: dict) -> list:
    """族内等距系统抽样（含首末两枚），保持题源顺序输出。

    为什么等距而不是「取前 k 枚」：题源每一族都是按难度与形状排的，取前 k 枚会把子集
    烤在族的开头那一档，尾巴那几枚难形（run9 的 report-12 / scope-05 就在尾巴）永远进不了窗。
    """
    picked = []
    for fam in FAMILIES:
        members = [qid for qid in ids if family_of(qid) == fam]
        want = alloc[fam]
        if want > len(members):
            raise SubsetError(f"族 {fam} 只有 {len(members)} 枚，却要抽 {want} 枚")
        if want == 1:
            picked.append(members[0])
            continue
        last = len(members) - 1
        for index in range(want):
            position = int((index * last + 0.5) / (want - 1))
            picked.append(members[position])
    order = {qid: position for position, qid in enumerate(ids)}
    return sorted(dict.fromkeys(picked), key=lambda qid: order[qid])


def emit_subset(bank_lines: list, picked: list) -> bytes:
    index = bank_index(bank_lines)
    return b"".join(index[qid] for qid in picked)


def compare_subset(bank_lines: list, subset_raw: bytes) -> dict:
    """逐行比对「子集那一行 == 本体那一行」，字节级，含行尾 CRLF。"""
    index = bank_index(bank_lines)
    subset_lines = [line for line in subset_raw.splitlines(keepends=True) if line.strip()]
    seen = []
    counted = []
    rows = []
    foreign = []
    mutated = []
    for line in subset_lines:
        qid = line_id(line)
        counted.append(qid)
        if qid not in index:
            foreign.append(qid or line[:40].decode("utf-8", "replace"))
            rows.append({"id": qid, "equal": False, "why": "id 不在题源本体 105 枚里"})
            continue
        if qid in seen:
            rows.append({"id": qid, "equal": False, "why": "同一枚 id 在子集里出现两次"})
            mutated.append(qid)
            continue
        seen.append(qid)
        equal = line == index[qid]
        if not equal:
            mutated.append(qid)
        rows.append({
            "id": qid,
            "equal": equal,
            "why": "" if equal else f"与本体该行字节不等（子集 {len(line)} B / 本体 {len(index[qid])} B）",
        })
    duplicates = [qid for qid in seen if seen.count(qid) > 1]
    return {
        "rows": rows,
        "count": len(subset_lines),
        "subset_bytes": len(subset_raw),
        "bank_total": len(bank_lines),
        "bank_bytes": sum(len(line) for line in bank_lines),
        "evidence_bytes": 0,
        "equal": sum(1 for row in rows if row["equal"]),
        "foreign": foreign,
        "mutated": mutated,
        "duplicates": duplicates,
        # 按子集里实际出现的 id 数族（含外来行）：这样成员检查与配额
        # 检查各管各的——换一行同族外来 id 只会触碰成员这一把钉，不会顺带把配额也撞红。
        "families": {fam: sum(1 for qid in counted if family_of(qid) == fam) for fam in FAMILIES},
    }


def validate_subset(bank_lines: list, subset_raw: bytes, size: int = SUBSET_SIZE) -> dict:
    report = compare_subset(bank_lines, subset_raw)
    problems = []
    if report["count"] != size:
        problems.append(f"子集共 {report['count']} 行，判据要求 {size} 行")
    if report["foreign"]:
        problems.append("子集里出现不在本体 105 枚里的 id：" + "、".join(report["foreign"]))
    if report["mutated"]:
        problems.append("子集里有行与本体不等值（改了一个字也算改）：" + "、".join(report["mutated"]))
    if report["duplicates"]:
        problems.append("子集里 id 重复：" + "、".join(sorted(set(report["duplicates"]))))
    for fam, floor in _floors():
        got = report["families"].get(fam, 0)
        if got < floor:
            problems.append(f"族 {fam} 只有 {got} 枚，判据要求至少 {floor} 枚")
    if problems:
        raise SubsetError("；".join(problems))
    return report


def _floors():
    floors = {fam: FAMILY_FLOOR for fam in FAMILIES}
    floors.update(FAMILY_FLOOR_OVERRIDES)
    return list(floors.items())


# ==================== 判据②：一扇窗的多相计划 ====================


def resolve_cell(cid: str) -> Cell:
    item = CELLS.get(cid)
    if item is None:
        raise PlannerError(f"未登记的格 {cid}；在册形状格＝{'、'.join(SHAPE_CELLS)}")
    if not item.shape:
        raise ScopeViolation(
            f"{SCOPE_SENTENCE}：{cid}（{item.label}）是{item.why_shape}，"
            f"必须本机全量每冻结点一次，不许塞进形状窗")
    return item


def roster_gap_reasons(items: list) -> dict:
    """名册证不了的形状格：点名缺哪一处读数，不硬凑映射（返工令第 3 条）。"""
    out = {}
    for item in items:
        if item.shape and not item.r453_cells:
            out[item.cid] = (
                f"R453 名册 {len(R453_ROSTER)} 枚读数格里没有任何一格能证这一格；缺的读数位＝"
                f"{item.surface}。按返工令不许硬凑映射，等对面件登记出能读它的那一格再谈")
    return out


def plan_window(cell_ids: list, *, bank_lines: list, subset_raw: bytes,
                evidence: dict, profile: MachineProfile,
                evidence_sha16: str = "") -> dict:
    requested = list(dict.fromkeys(cell_ids))
    if not requested:
        raise PlannerError("本班要判的格集合为空：没有格就别开窗")
    cells = [resolve_cell(cid) for cid in requested]

    comparison = compare_subset(bank_lines, subset_raw)
    subset_ids = [row["id"] for row in comparison["rows"] if row["equal"]]

    phases = []
    order = {qid: position for position, qid in enumerate(subset_ids)}
    invariants = [c for c in cells if not c.switches]  # 随每一相播放，自己不点题
    for name, switches in ((STREAM_PHASE, (("REPORT_LANE_VIA_QUEUE", "off"),)),
                           (QUEUE_PHASE, (("REPORT_LANE_VIA_QUEUE", "on"),))):
        drivers = [c for c in cells if c.switches == switches and c.drives_questions]
        if not drivers:
            continue  # 没有专属出题格就不开这一相，不变量格挂在真实存在的相上
        members = [c for c in cells if c.switches == switches] + invariants
        wanted = set()
        for c in drivers:
            if c.needs_all_families:
                wanted.update(subset_ids)
            else:
                wanted.update(qid for qid in subset_ids if family_of(qid) in c.families)
        questions = sorted(wanted, key=lambda qid: order[qid])
        phases.append({
            "phase": name,
            "switches": dict(switches),
            "cells": [c.cid for c in members],
            "question_ids": questions,
            "approval_rounds_planned": sum(evidence.get(qid, 0) for qid in questions),
            "approval_question_ids": [qid for qid in questions if evidence.get(qid, 0)],
        })
    if not phases:
        # 只剩不变量格（例如本班只判「零重试零哨兵」）：落在默认开关态的流式道上，
        # 由它自己点全子集，否则这一格无处可读。
        if invariants:
            phases.append({
                "phase": STREAM_PHASE,
                "switches": {"REPORT_LANE_VIA_QUEUE": "off"},
                "cells": [c.cid for c in invariants],
                "question_ids": list(subset_ids),
                "approval_rounds_planned": sum(evidence.get(qid, 0) for qid in subset_ids),
                "approval_question_ids": [qid for qid in subset_ids if evidence.get(qid, 0)],
            })
        else:
            raise PlannerError("请求的格没有一相能安放：检查 switches 定义")

    plays = sum(len(phase["question_ids"]) for phase in phases)
    tally = {}
    for phase in phases:
        for qid in phase["question_ids"]:
            tally[qid] = tally.get(qid, 0) + 1
    plan = {
        "profile": profile.name,
        "subset_size": len(subset_ids),
        "cells": [c.cid for c in cells],
        "cell_labels": {c.cid: c.label for c in cells},
        "windows": [{
            "window_id": "shape-window-1",
            "bank_sha16": hashlib.sha256(b"".join(bank_lines)).hexdigest()[:16],
            "subset_sha16": hashlib.sha256(subset_raw).hexdigest()[:16],
            "evidence_sha16": evidence_sha16,
            "phases": phases,
            "question_plays": plays,
            "unique_questions": len(subset_ids),
            "replayed_question_ids": sorted(q for q, n in tally.items() if n > 1),
            "approvals_planned_total": sum(p["approval_rounds_planned"] for p in phases),
            "approvals_per_phase": {p["phase"]: p["approval_rounds_planned"] for p in phases},
        }],
        "cell_phases": {c.cid: [p["phase"] for p in phases if c.cid in p["cells"]]
                        for c in cells},
        "cell_question_ids": _cell_questions(cells, phases, subset_ids),
        "r453_binding": {c.cid: list(r453_binding(c)) for c in cells},
        "r453_payload_coverage": {c.cid: r453_field_coverage(c) for c in cells
                                  if c.r453_payload_fields},
        "r453_roster_snapshot": {
            "path": R453_ROSTER_REL,
            "sha16": sha256_16(REPO_ROOT / R453_ROSTER_REL),
            "cells_total": len(R453_ROSTER),
            "cloud_readable": len(R453_CLOUD_CELLS),
            "local_only": len(R453_LOCAL_ONLY_CELLS),
        },
        "r453_cloud_unreferenced": r453_unreferenced_cloud_cells(),
        "r453_local_only_out_of_scope": list(R453_LOCAL_ONLY_CELLS),
        "r453_unproven_shape_cells": sorted(roster_gap_reasons(cells)),
        "r453_ledger_binding": r453_ledger_binding(),
        "unattainable_here": dict(profile.blocked_cells(), **roster_gap_reasons(cells)),
        "out_of_scope_statement": SCOPE_SENTENCE,
        "out_of_scope_cells": list(OUT_OF_SCOPE_CELLS),
        "auto_approve_boundary": AUTO_APPROVE_SENTENCE,
    }
    # 每格归属：不变量格（无开关要求）落在两相；其余只落在自己那一相。
    for phases_of_cell in plan["cell_phases"].values():
        if not phases_of_cell:
            raise PlannerError("有格没被任何相安放，相划分逻辑要重开")
    validate_plan(plan)
    return plan


def _cell_questions(cells: list, phases: list, subset_ids: list) -> dict:
    """每格自己吃哪几枚题：族限定格只吃本族那几枚，不变量格吃它归属相里的每一 play。

    这一位不是装饰——把「越权格计划题数」写成整相那几十枚，就是替它吹了一张它没吃的题面。
    """
    out = {}
    for c in cells:
        picked = []
        for phase in phases:
            if c.cid not in phase["cells"]:
                continue
            if c.needs_all_families:
                picked.extend(phase["question_ids"])
            else:
                picked.extend(q for q in phase["question_ids"] if family_of(q) in c.families)
        out[c.cid] = sorted(dict.fromkeys(picked), key=lambda q: subset_ids.index(q))
    return out


def open_second_window(plan: dict, cell_ids: list) -> dict:
    """判据②硬规矩第 1 条：同一批格只允许出现一次开窗。"""
    placed = set(plan["cells"])
    asked = set(cell_ids)
    clash = sorted(placed & asked)
    if clash:
        raise DuplicateWindowError(
            f"这些格已经在 shape-window-1 里判过，不许为同一批格再开一扇窗：{'、'.join(clash)}"
            f"（病灶正是「一扇窗只拿一两格，剩下的下一班再开窗」——跟进单 §128 二节）")
    return plan


def validate_plan(plan: dict) -> None:
    windows = plan.get("windows") or []
    if len(windows) != 1:
        raise DuplicateWindowError(
            f"planner 交出 {len(windows)} 扇窗，判据②要求一扇窗内多相、窗数恒为 1")
    seen = {}
    for cell_id in plan["cells"]:
        if cell_id in seen:
            raise PlannerError(f"格 {cell_id} 在一次请求里出现两次")
        seen[cell_id] = True
    for cell_id in plan["cell_phases"]:
        if cell_id not in seen:
            raise PlannerError(f"归属表里有未请求的格 {cell_id}")
    for window in windows:
        for phase in window["phases"]:
            for cell_id in phase["cells"]:
                if cell_id not in seen:
                    raise PlannerError(f"相 {phase['phase']} 塞进了未请求的格 {cell_id}")
        for cell_id in sorted({c for p in window["phases"] for c in p["cells"]}):
            placements = [p["phase"] for p in window["phases"] if cell_id in p["cells"]]
            if CELLS[cell_id].switches and len(placements) > 1:
                raise PlannerError(
                    f"格 {cell_id} 在同一扇窗里被 {len(placements)} 枚相认领（{placements}）："
                    f"它有开关要求，一扇窗里只能落一相，否则同一批格判了两遍")
    binding = plan.get("r453_binding") or {}
    for cell_id in plan["cells"]:
        if binding.get(cell_id):
            continue
        if cell_id not in plan.get("unattainable_here", {}):
            raise RosterError(
                f"格 {cell_id} 既没绑到 R453 名册里的读数格，又没进 unattainable_here："
                f"这就是两单接口脱开的原样，不许静默通过")
    coverage = plan.get("r453_payload_coverage") or {}
    fresh = {}
    for cid in plan["cells"]:
        declared = CELLS[cid]
        if declared.r453_payload_fields:
            fresh[cid] = r453_field_coverage(declared)
    if coverage != fresh:
        raise RosterError("r453_payload_coverage 与现算的名册覆盖不等：报的是抄本，不是现读")
    for cid, item_coverage in fresh.items():
        if not item_coverage["closable"] and cid not in plan.get("unattainable_here", {}):
            raise RosterError(
                f"格 {cid} 的读数位没凑齐（缺 {item_coverage['missing']}、供给 "
                f"{item_coverage['owner_count']} 枚）：既不进 unattainable_here，"
                f"又不声明拿不了，就想把这枚格当过判——空引用不许这么过")
    unref = plan.get("r453_cloud_unreferenced")
    if unref is None:
        raise RosterError("计划里没有 r453_cloud_unreferenced 这一位：反向覆盖度必须能报出来")
    if sorted(unref) != sorted(r453_unreferenced_cloud_cells()):
        raise RosterError("r453_cloud_unreferenced 与现算的名册差集不等：报的是抄本，不是现读")
    if SCOPE_SENTENCE not in json.dumps(plan, ensure_ascii=False):
        raise ScopeViolation(f"计划里必须显式写下「{SCOPE_SENTENCE}」")


# ==================== 判据③：读数表骨架 ====================


def render_readout(plan: dict, *, bank_rel: str, subset_rel: str, evidence_rel: str,
                   comparison: dict, alloc: dict, picked: list) -> str:
    window = plan["windows"][0]
    lines = []
    lines.append("# 形状窗读数表（2026-09-28）· 由 `scripts/eval_window_planner.py` 生成")
    lines.append("")
    lines.append("> 本文件是**骨架**，不是读数。判据③：没拿到的格一律写「未验」——不写 0、"
                 "不写「应该没问题」、不抄上一班。本班零模型、零容器、不起服务，"
                 "所以下表每一枚格的读数列全部为「未验」，开窗由总控执行。")
    lines.append("")
    lines.append("## 一、输入件（路径与 sha256 前 16 位）")
    lines.append("")
    lines.append("| 件 | 路径 | sha256 前 16 位 | 字节数 | 角色 |")
    lines.append("|---|---|---|---|---|")
    lines.append(f"| 题源本体 | `{bank_rel}` | `{window['bank_sha16']}` | "
                 f"{comparison['bank_bytes']} | 105 枚在册题，只读，一个字节不许改 |")
    lines.append(f"| 形状子集 | `{subset_rel}` | `{window['subset_sha16']}` | "
                 f"{comparison['subset_bytes']} | {comparison['count']} 枚分层子集（本体 {comparison['bank_total']} 枚在册），逐行字节等值于本体 |")
    lines.append(f"| 批准算料 | `{evidence_rel}` | `{window['evidence_sha16']}` | "
                 f"{comparison['evidence_bytes']} | 上一窗逐枚 `approval_rounds`，批准次数由它算 |")
    lines.append("")
    lines.append("## 二、子集逐行比对（判据①的凭据）")
    lines.append("")
    lines.append(f"- 子集行数：{comparison['count']}；与本体**字节级等值**：{comparison['equal']}/"
                 f"{comparison['count']}")
    lines.append(f"- 外来 id（不在本体 105 枚里）：{len(comparison['foreign'])} 枚"
                 + ("" if not comparison["foreign"] else "：" + "、".join(comparison["foreign"])))
    lines.append(f"- 被改动的行：{len(comparison['mutated'])} 枚"
                 + ("" if not comparison["mutated"] else "：" + "、".join(comparison["mutated"])))
    lines.append("- 比对口径：`splitlines(keepends=True)` 取原始字节行，本体行尾是 CRLF，"
                 "整行含行尾一起比——所以「重序列化加个空格」也算改题。")
    lines.append("")
    lines.append("## 三、11 族分布（分层账）")
    lines.append("")
    lines.append("| 族 | 本体枚数 | 子集枚数 | 最低配额 |")
    lines.append("|---|---|---|---|")
    for fam in FAMILIES:
        lines.append(f"| {fam} | {alloc['bank_counts'][fam]} | "
                     f"{comparison['families'].get(fam, 0)} | {alloc['floors'][fam]} |")
    lines.append(f"| 合计 | {alloc['bank_total']} | {comparison['count']} | — |")
    lines.append("")
    lines.append(f"- `approval` 族 {comparison['families'].get('approval', 0)} 枚、"
                 f"`report` 族 {comparison['families'].get('report', 0)} 枚"
                 "（判据①要求各至少 3 枚）")
    lines.append("- 子集题序（题源顺序）：" + "、".join(picked))
    lines.append("")
    lines.append("## 四、一扇窗计划（判据②输出）")
    lines.append("")
    lines.append(f"- 窗数：**1**（`{window['window_id']}`）。同一批格只允许出现一次开窗，"
                 "planner 自己不许生成第二扇。")
    lines.append(f"- 相数：{len(window['phases'])}。相的划分来自开关态互斥："
                 "`REPORT_LANE_VIA_QUEUE` 一开，报告档整段取回，A② 必被洗成假红（runbook「两相一窗」）。")
    lines.append("- 相之间必须复跑 P-18（Redis `answer:*` 归零），否则相 2 命中缓存，D 三格读的是缓存不是队列道。")
    lines.append("")
    lines.append("| 相 | 开关态 | 题数 | 题序 | 计划批准轮 |")
    lines.append("|---|---|---|---|---|")
    for phase in window["phases"]:
        switches = "、".join(f"{k}={v}" for k, v in phase["switches"].items()) or "—"
        order = "、".join(phase["question_ids"])
        lines.append(f"| {phase['phase']} | {switches} | {len(phase['question_ids'])} | "
                     f"{order} | {phase['approval_rounds_planned']} |")
    lines.append("")
    lines.append(f"- 总播放次数：{window['question_plays']}（唯一题号 "
                 f"{window['unique_questions']} 枚）；因相开关不同而重复播放的题号："
                 + ("、".join(window["replayed_question_ids"]) or "无"))
    lines.append(f"- **算出来的批准次数：{window['approvals_planned_total']} 轮**"
                 f"（逐相：" + "；".join(f"{k}＝{v}" for k, v in
                                    window["approvals_per_phase"].items()) + "）")
    lines.append("- 批准次数的算料＝上一窗 sidecar 逐枚 `approval_rounds`，不是按族猜。"
                 "反例已在本机抓到：`approval` 族 6 枚在 run9 里一枚都没触发批准轮，"
                 "触发的是 report/chart/tool/insight/scope——按族猜会把批准次数算错。")
    lines.append(f"- 🔴 {AUTO_APPROVE_SENTENCE}（业主 09-28 授权①的边界）。")
    lines.append("- 批准人与批准次数要落进本表：开窗执行时逐相记 `approved_by=评测账号`、"
                 "`approval_rounds=实际值`，与计划值不一致就是新事实，得写进读数不许改计划掩盖。")
    lines.append("")
    lines.append("## 五、格归属与读数（判据③主体）")
    lines.append("")
    lines.append("| 格 | 名称 | 归属相 | 取数面 | 计划题数 | 读数 |")
    lines.append("|---|---|---|---|---|---|")
    for cell_id in plan["cells"]:
        item = CELLS[cell_id]
        owner = "＋".join(plan["cell_phases"][cell_id])
        lines.append(f"| {cell_id} | {item.label} | {owner} | {item.surface} | "
                     f"{len(plan['cell_question_ids'][cell_id])} | {UNVERIFIED} |")
    lines.append("")
    for cid in [c for c in plan["cells"] if not CELLS[c].drives_questions]:
        plays_here = sum(len(p["question_ids"]) for p in window["phases"] if cid in p["cells"])
        lines.append(
            f"- {CELLS[cid].label}：这一格读的是「每一 play」，所以按 {plays_here} 次播放逐枚判，"
            f"重复播放的那几枚再判一遍；上表题数列给的是唯一题号 "
            f"{len(plan['cell_question_ids'][cid])} 枚。")
    lines.append("")
    lines.append("")
    lines.append("## 六、与 R453 读数名册的接口（两单合起来才算一次开窗）")
    lines.append("")
    snap = plan["r453_roster_snapshot"]
    lines.append(f"- 名册唯一来源：`{snap['path']}`（sha256 前 16 位 `{snap['sha16']}`，"
                 f"在册读数格 {snap['cells_total']} 枚，其中云端可读 {snap['cloud_readable']} 枚、"
                 "本机专属 " + str(snap["local_only"]) + " 枚）。本件的格名**全部从这张表 import**，"
                 "不落第二份清单——两单今天格名交集＝0 那次事故就是这么来的。")
    lines.append("")
    lines.append("| 判据格 | 名称 | 绑到名册里的哪几格 | 那几格实际吃的读数位 | 名册登记的锚 |")
    lines.append("|---|---|---|---|---|")
    for cell_id in plan["cells"]:
        item = CELLS[cell_id]
        names = plan["r453_binding"][cell_id]
        fields = []
        anchors = []
        for name in names:
            fields.extend(r453_reading_fields(name))
            row = R453_ROSTER_BY_CELL[name]
            if row["anchor"] not in anchors:
                anchors.append(row["anchor"])
        lines.append(f"| {cell_id} | {item.label} | {'、'.join(names) or '（名册里没有能证它的格）'} | "
                     f"{'、'.join(fields) or '无'} | {'；'.join(anchors) or '无'} |")
    lines.append("")
    for cell_id, item_coverage in plan.get("r453_payload_coverage", {}).items():
        detail = "、".join("{}←{}".format(field, "、".join(names) or "名册里没有")
                          for field, names in item_coverage["suppliers"].items())
        lines.append(f"- {COVERAGE_MARKER}（关「在场但为空」那枚假绿）：`{cell_id}` 声明必须同时读到 "
                     f"{detail}；供给的名册格 {item_coverage['owner_count']} 枚，缺位＝"
                     f"{'、'.join(item_coverage['missing']) or '无'}，今天"
                     f"{'准按这一组读数闭格' if item_coverage['closable'] else '不许读成过——只能记拿不了'}。")
    lines.append("")
    gaps = plan["r453_unproven_shape_cells"]
    if gaps:
        lines.append("- 🔴 名册证不了的格：" + "、".join(gaps)
                     + "——已按返工令第 3 条落进「这台机拿不了的格」，逐枚点名缺哪一处读数，不硬凑映射。")
    else:
        lines.append("- 名册证不了的格：**无**。本班请求的每一枚形状格都能在名册里找到至少一格真能读它"
                     "（这一位是算出来的：`r453_unproven_shape_cells`，不是态度）。")
    lines.append("")
    unref = plan["r453_cloud_unreferenced"]
    if unref:
        lines.append(f"- 反向覆盖度：云端可读 {snap['cloud_readable']} 枚里，本窗**一枚判据格都没引用**的有 "
                     f"{len(unref)} 枚——" + "、".join(unref) + "。")
        for name in unref:
            row = R453_ROSTER_BY_CELL[name]
            ledger_of = [field for field in r453_reading_fields(name)
                         if plan["r453_ledger_binding"].get(field) == name]
            lines.append(f"  - {name}（{row['gate']}）：名册记的是「{row['why']}」，"
                         f"读数位 {'、'.join(r453_reading_fields(name)) or '未登记'}。"
                         + (f"本窗的**批准台账**按名册认领它：读的是 {'、'.join(ledger_of)} "
                            "这一枚算料位（算料，不判格），所以它仍留在未引用清单里——"
                            "没有任何一枚判据格拿它当证据。"
                            if ledger_of else
                            "本窗不消费它；要在一扇窗里顺手读，就得把它挂到某枚判据格的 "
                            "r453_cells 上，或另立一枚判据格——不许悄悄读了又不记账。"))
    else:
        lines.append("- 反向覆盖度：云端可读格全部被本窗的判据格引用，没有白读的那一格。")
    lines.append("")
    lines.append(f"- 名册里本机专属那 {snap['local_only']} 枚（时延与分数两族）整体不在形状窗：与 §八 "
                 "拒绝清单同一口径，两侧分家必须一致，`validate_catalog_binding()` 逐枚对表。")
    lines.append("")
    lines.append("## 七、这台机拿不了的格（planner 判的，不是态度）")
    lines.append("")
    if plan["unattainable_here"]:
        lines.append("| 格 | 名称 | 拿不了的原因 | 读数 |")
        lines.append("|---|---|---|---|")
        for cell_id, reason in plan["unattainable_here"].items():
            lines.append(f"| {cell_id} | {CELLS[cell_id].label} | {reason} | {UNVERIFIED} |")
    else:
        lines.append("- 无：本机能力位允许判出本班请求的每一枚格。")
    lines.append("")
    lines.append("## 八、形状窗范围之外（判据②硬规矩第 2 条）")
    lines.append("")
    lines.append(f"- {SCOPE_SENTENCE}。下列格被 planner 直接拒绝，不是「暂缓」：")
    lines.append("")
    lines.append("| 格 | 名称 | 为什么不在形状窗 | 只能怎么拿 |")
    lines.append("|---|---|---|---|")
    for cell_id in plan["out_of_scope_cells"]:
        item = CELLS[cell_id]
        lines.append(f"| {cell_id} | {item.label} | {item.why_shape} | 本机全量 105 枚，"
                     "每冻结点一次；时延类另需样本 ≥100 |")
    lines.append("")
    lines.append("## 九、机器可读计划（planner 原样吐出，validate_readout 按它核对）")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(plan, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    return "\n".join(lines) + "\n"


FORBIDDEN_READING_TOKENS = ("✅", "PASS", "pass", "过", "成立", "没问题", "应该", "绿")


def validate_readout(markdown: str, plan: dict) -> dict:
    """未验格被写成过 ⇒ 红。同时核对窗数、范围声明、自动批准边界句。"""
    problems = []
    rows = {}
    for raw_line in markdown.splitlines():
        if not raw_line.startswith("| "):
            continue
        cols = [c.strip() for c in raw_line.strip().strip("|").split("|")]
        # 只认「格归属与读数」那一枚表：六列（格/名称/归属相/取数面/计划题数/读数）。
        # 「拿不了的格」那张表同名列第一格但只有四列，混进来会把一行合法读数报成重复行。
        if len(cols) == 6 and cols[0] in plan["cells"]:
            if cols[0] in rows:
                problems.append(f"格 {cols[0]} 在读数表里出现两次")
            rows[cols[0]] = cols
    for cell_id in plan["cells"]:
        if cell_id not in rows:
            problems.append(f"格 {cell_id} 在读数表里没有行")
            continue
        reading = rows[cell_id][-1]
        if reading != UNVERIFIED:
            problems.append(f"格 {cell_id} 的读数列是「{reading}」，未拿到的格必须写「{UNVERIFIED}」")
        for token in FORBIDDEN_READING_TOKENS:
            if token in reading:
                problems.append(f"格 {cell_id} 的读数列含禁用词「{token}」")
    if any(any(ch.isdigit() for ch in cols[-1]) for cols in rows.values()):
        problems.append("读数列出现数字（未拿到的格不写 0，也不写 0/30）")
    windows = markdown.count("window_id")
    if windows != 1:
        problems.append(f"读数表里出现 {windows} 枚 window_id，判据②要求一扇窗")
    # 接口一节：五列表（判据格/名称/绑到名册哪几格/读数位/锚）里每枚请求格都要有一行。
    binding_rows = {}
    for raw_line in markdown.splitlines():
        if not raw_line.startswith("| "):
            continue
        cols = [c.strip() for c in raw_line.strip().strip("|").split("|")]
        if len(cols) == 5 and cols[0] in plan["cells"]:
            binding_rows[cols[0]] = cols
    for cell_id in plan["cells"]:
        if cell_id not in binding_rows:
            problems.append(f"接口表里没有格 {cell_id} 的行：这一格与 R453 名册的关系没落账")
        elif plan["r453_binding"][cell_id] and "名册里没有能证它的格" in binding_rows[cell_id][-1]:
            problems.append(f"格 {cell_id} 明明绑到了名册格，接口表却写「没有能证它的格」")
    for name in plan["r453_cloud_unreferenced"]:
        if name not in markdown:
            problems.append(f"没被引用的云端可读格 {name} 没在读数表里点名：反向覆盖度失守")
    for cell_id in plan.get("r453_payload_coverage") or {}:
        hit = [line for line in markdown.splitlines()
               if line.startswith("- " + COVERAGE_MARKER) and cell_id in line]
        if not hit:
            problems.append(f"格 {cell_id} 的{COVERAGE_MARKER}那一行没落进读数表：空引用假绿没人记账")
    if SCOPE_SENTENCE not in markdown:
        problems.append(f"读数表少了那句硬点名：{SCOPE_SENTENCE}")
    if AUTO_APPROVE_SENTENCE not in markdown:
        problems.append(f"读数表少了自动批准边界句：{AUTO_APPROVE_SENTENCE}")
    if problems:
        raise ReadoutError("；".join(problems))
    return {"rows": len(rows), "cells": len(plan["cells"])}


# ==================== CLI ====================


def _rel(path: Path, raw: str) -> str:
    """读数表里一律用正斜杠相对路径：同一条计划在别的机器上要可比对，路径写法不许两样。"""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="R454 形状窗计划器（一窗多判据）")
    parser.add_argument("--cells", default=",".join(SHAPE_CELLS))
    parser.add_argument("--bank", default=str(REPO_ROOT / BANK_REL))
    parser.add_argument("--subset", default=str(REPO_ROOT / SUBSET_REL))
    parser.add_argument("--evidence", default=str(REPO_ROOT / EVIDENCE_REL))
    parser.add_argument("--out", default=str(REPO_ROOT / READOUT_REL))
    parser.add_argument("--emit-subset", action="store_true",
                        help="按分层规则从本体逐字节抽出子集并写盘（只写 --subset）")
    parser.add_argument("--check", action="store_true", help="只校验在册件，不写盘")
    parser.add_argument("--profile-production-labels", action="store_true")
    parser.add_argument("--profile-cache-probe", action="store_true")
    parser.add_argument("--json", action="store_true", help="把计划打到 stdout")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    bank_path = Path(args.bank)
    subset_path = Path(args.subset)
    bank_lines = load_bank_lines(bank_path)
    ids = bank_ids(bank_lines)
    alloc = allocate_families(ids)
    alloc_view = {"bank_counts": {}, "floors": dict(_floors()), "bank_total": len(ids)}
    for qid in ids:
        fam = family_of(qid)
        alloc_view["bank_counts"][fam] = alloc_view["bank_counts"].get(fam, 0) + 1
    picked = select_ids(ids, alloc)

    if args.emit_subset:
        subset_path.write_bytes(emit_subset(bank_lines, picked))

    if not subset_path.exists():
        raise SubsetError(f"子集件不存在：{subset_path}（先跑 --emit-subset）")
    subset_raw = subset_path.read_bytes()
    comparison = validate_subset(bank_lines, subset_raw)
    evidence_path = Path(args.evidence)
    evidence_raw = evidence_path.read_bytes() if evidence_path.exists() else b""
    comparison["evidence_bytes"] = len(evidence_raw)
    if args.check:
        print(json.dumps({"equal": f"{comparison['equal']}/{comparison['count']}",
                          "families": comparison["families"]}, ensure_ascii=False))
        return 0

    plan = plan_window(
        [c.strip() for c in args.cells.split(",") if c.strip()],
        bank_lines=bank_lines,
        subset_raw=subset_raw,
        evidence=load_approval_evidence(evidence_path),
        evidence_sha16=sha256_16(evidence_path),
        profile=MachineProfile(
            production_labels_backfilled=args.profile_production_labels,
            cache_hit_probe_allowed=args.profile_cache_probe,
        ),
    )
    markdown = render_readout(
        plan,
        bank_rel=_rel(bank_path, args.bank),
        subset_rel=_rel(subset_path, args.subset),
        evidence_rel=_rel(Path(args.evidence), args.evidence),
        comparison=comparison,
        alloc=alloc_view,
        picked=picked,
    )
    validate_readout(markdown, plan)
    Path(args.out).write_text(markdown, encoding="utf-8", newline="\n")
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        window = plan["windows"][0]
        print(f"windows=1 phases={len(window['phases'])} plays={window['question_plays']} "
              f"approvals={window['approvals_planned_total']} "
              f"unattainable={len(plan['unattainable_here'])} out={len(plan['out_of_scope_cells'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
