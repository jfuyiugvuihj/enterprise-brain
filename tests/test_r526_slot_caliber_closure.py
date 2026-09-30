# -*- coding: utf-8 -*-
"""R526 · 三档 SLO「口径闭环」钉：契约那几行与观测面必须同字，并且一枚数都不许发。

对判据的哪一条（派工词 R526）：
  ① 每枚数字格都能指向「量具脚本名 + 原始读数文件路径 + 达成条件」三件，缺任一件即红；
  ② 不发布数值：未实测的秒数 = 不可承诺 —— 这一条本身被写成能跑的牙，不是一句态度；
  ③ 同源算术：观测面报出的口径与契约散文逐字同源（同一枚量具名、同一套单位映射、同一副脊柱）；
  ④ §4 的 目标 格仍全部「待真机样本」；谁把它填成数字又拿不出 docs/perf/raw/ 凭据 ⇒ 当场红；
  ⑥ run10 收窗之后的交接表在册：每一枚族都点名 了谁、按什么命令、附什么凭据。

🔴 本文件不出现任何一枚秒数 / token 数 / 分数。反证要用的伪造值只在
``tests/test_r526_counter_evidence_teeth.py`` 里，且只喂 tmp_path 上的影子副本，永不落纸。

形状：每条判据都写成「纯函数 + 返回违规清单」，正向用例断言清单为空；反证刀把同一批纯函数喂
 mutated 输入，断言清单非空且点到那一格。刀口与牙共用一枚代码，不留「刀有牙、钉没牙」的缝。
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

from app.api.v1 import observability

REPO = Path(__file__).resolve().parents[1]
CONTRACT_DOC = REPO / "docs" / "api" / "contract-v1.md"
R453_ROSTER = REPO / "scripts" / "eval_cloud_window_readout.py"

SLO_SECTION_TITLE = "## Three-Tier SLO Contract (2026-09-20, R105 甲半)"
CALIBER_TITLE = "### 4b. Caliber cells"
HANDOFF_TITLE = "#### run10 收窗之后的交接"
PENDING_TEXT = "「待真机样本」"
UNROSTERED = "未在册（不许拿相近枚名走私）"
CALIBER_CELLS = 7
HANDOFF_CELLS = 6
TARGET_CELLS = 5
WINDOW_PLACEHOLDER = "{window}"
FORGERY_START = "# --- 伪造弹药"
FORGERY_END = "# --- 弹药结束 ---"
YES = "是"
NO = "否"

#: 「一格被填成了数」的字面形状：带单位的量级，或一枚小数。
#: 🔴 名字里带的数字（``p95_ms`` / ``R453`` / ``run10`` / ``sha256`` / ``1-based``）不算量级：
#: 前面是字母、点或短横的一律不咬，所以这枚尺既咬得住伪造的秒数，也不会把口径自己的名字当罪证。
MAGNITUDE = re.compile(
    r"(?<![\w.\-])\d+(?:[.,]\d+)?\s*"
    r"(?:ms|毫秒|µs|s\b|秒|tokens?\b|token|％|%|准确率|正确性|分数|correctness|accuracy)",
    re.IGNORECASE,
)
DECIMAL = re.compile(r"(?<![\w.\-])\d+\.\d+")


# ==================== 取数：契约、观测面、名册（都现读，不缓存抄本） ====================


def contract_text() -> str:
    return CONTRACT_DOC.read_text(encoding="utf-8")


def slice_from(text: str, start_title: str, stop_patterns) -> str:
    """按字面锚点切一段。🔴 本仓的纸是 CRLF + 混排，行号与 rg 报的行号不同源，一律不用行号。"""
    start = text.index(start_title)
    stops = [pattern.search(text, start + len(start_title)) for pattern in stop_patterns]
    ends = [match.start() for match in stops if match]
    return text[start : min(ends) if ends else len(text)]


def slo_section(text: str) -> str:
    return slice_from(text, SLO_SECTION_TITLE, [re.compile(r"^## ", re.MULTILINE)])


def caliber_section(text: str) -> str:
    return slice_from(
        text, CALIBER_TITLE, [re.compile(r"^### ", re.MULTILINE), re.compile(r"^## ", re.MULTILINE)]
    )


def table_rows(section_text: str, *, cells: int):
    rows = []
    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        found = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(found) != cells:
            continue
        if all(cell and set(cell) <= set("-: ") for cell in found):
            continue
        if found[0] in {"槽位", "档", "家族"}:
            continue
        rows.append(found)
    return rows


def render(value) -> str:
    """契约表格单元格的落纸形状：竖线换成斜杠，空白压平。与生成时同一条规则。"""
    return str(value or "").replace("|", "/").replace("\r", " ").replace("\n", " ").strip()


def caliber() -> dict:
    return observability.slo_slot_caliber()


def expected_row_cells(item) -> tuple:
    return (
        render(item["instrument"]),
        render("%s · %s" % (item["raw_readout"], item["raw_field"])),
        render(item["condition"]),
        render(item["roster_cell"] or UNROSTERED),
        YES if item["window_admissible"] else NO,
        render(item["prerequisite"]),
    )


def row_covers(cell_zero: str, slot_id: str) -> bool:
    return "`%s`" % slot_id in cell_zero


def map_rows_to_slots(section_text: str, slots):
    """把 §4b 的每一行摊到它覆盖的槽位上；重行、漏行、凭空多行都在这儿露出来。"""
    rows = table_rows(section_text, cells=CALIBER_CELLS)
    mapped: dict[str, tuple] = {}
    collisions = []
    for cells in rows:
        hits = [item["slot"] for item in slots if row_covers(cells[0], item["slot"])]
        if not hits:
            collisions.append(("行指向一枚不存在的槽位", cells[0]))
            continue
        for slot in hits:
            if slot in mapped:
                collisions.append(("同一枚槽位被两行各说一遍", slot))
            mapped[slot] = tuple(cells[1:])
    return rows, mapped, collisions


@pytest.fixture(scope="module")
def r453_cells():
    """R453 那本名册（格名与 kind / cloud 的唯一来源）。件在 import 期零 IO，可以安全拉起来。"""
    spec = importlib.util.spec_from_file_location("r526_eval_cloud_window_readout", R453_ROSTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {row["cell"]: row for row in module.CELLS}

# ==================== 判据的纯函数面（正向用例与反证刀共用同一枚代码） ====================

REPO_PATH = re.compile(r"(?:scripts|app|frontend|docs|deploy|migrations)/[\w./\-]+?\.(?:py|md|jsonl|json|js|vue|sql)")


def find_magnitudes(text: str):
    """把「一格被填成了数」的字面形状抓出来：带单位的量级 + 任何小数。"""
    return [match.group(0) for match in MAGNITUDE.finditer(text)] + [
        match.group(0) for match in DECIMAL.finditer(text)
    ]


def caliber_fields(item) -> dict:
    return {
        "量具": item["instrument"],
        "原始读数件": item["raw_readout"],
        "取哪一格": item["raw_field"],
        "达成条件": item["condition"],
        "在册格名": item["roster_cell"],
        "落数前欠": item["prerequisite"],
        "分母": item["denominator"],
    }


def check_legs(cal: dict):
    """判据①：三件齐全，一件都不许空着混过去。"""
    bad = []
    missing = sorted(set(derived_slot_ids()) - {item["slot"] for item in cal["slots"]})
    if missing:
        bad.append("有槽位没口径：%s" % missing)
    if cal["uncalibrated"]:
        bad.append("有槽位没口径：%s" % cal["uncalibrated"])
    if cal["orphan"]:
        bad.append("有口径挂在已不存在的槽位上（改名只动了一边）：%s" % cal["orphan"])
    ids = [item["slot"] for item in cal["slots"]]
    if len(ids) != len(set(ids)):
        bad.append("槽位重名：%s" % sorted({slot for slot in ids if ids.count(slot) > 1}))
    for item in cal["slots"]:
        for leg, value in caliber_fields(item).items():
            # 在册格名与「落数前欠」不是三件本身：前者是单位映射，后者是欠账清单。
            if leg in {"在册格名", "落数前欠"}:
                continue
            if not str(value).strip():
                bad.append("%s：缺「%s」那一件" % (item["slot"], leg))
        if item["target"] is not None:
            bad.append("%s：target 被写成了 %r —— 本单只钉口径" % (item["slot"], item["target"]))
        if item["target_status"] != observability.SLO_TARGET_PENDING:
            bad.append("%s：target_status 不是 %s" % (item["slot"], observability.SLO_TARGET_PENDING))
    return bad


def check_instruments_on_disk(cal: dict, root: Path = REPO):
    """量具必须是仓里真有的件：引用一枚 Temp 里的脚本 = 零凭据（run9 的分档表就这么丢的）。"""
    bad = []
    for item in cal["slots"]:
        for path in item["instrument_paths"]:
            if not (root / path).is_file():
                bad.append("%s：量具件不在仓内：%s" % (item["slot"], path))
        for text in (item["instrument"], item["prerequisite"]):
            for match in REPO_PATH.finditer(str(text)):
                if not (root / match.group(0)).exists():
                    bad.append("%s：口径引用了一枚仓外/不存在的件：%s" % (item["slot"], match.group(0)))
    return bad


def check_reference_fields(cal: dict, root: Path = REPO):
    """说得出字段名不算本事：上一窗的真件里必须逐行真有那一格，否则这枚量具是空头支票。"""
    bad = []
    seen = {}
    for item in cal["slots"]:
        reference = item["reference_readout"]
        if not reference:
            continue
        seen.setdefault((reference, item["reference_field"]), []).append(item["slot"])
    for (reference, field), slots in seen.items():
        path = root / reference
        if not path.is_file():
            bad.append("%s：参照件不存在：%s" % ("/".join(slots), reference))
            continue
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not rows:
            bad.append("%s：参照件是空的：%s" % ("/".join(slots), reference))
            continue
        missing = [index for index, row in enumerate(rows) if field not in row]
        if missing:
            bad.append("%s：量具 %s 并不产出 `%s`（参照件缺 %d 行）" % ("/".join(slots), reference, field, len(missing)))
    return bad


def check_doc_agreement(text: str, cal: dict):
    """判据③：观测面报出的每一格与契约散文逐字同一套词，不许出现第二套口径。"""
    bad = []
    section = caliber_section(text)
    rows, mapped, collisions = map_rows_to_slots(section, cal["slots"])
    bad.extend("%s：%s" % (kind, victim) for kind, victim in collisions)
    if not rows:
        bad.append("§4b 的口径表一行都没解析出来（锚点或列数被动过 —— 这是死牙的形状，不是干净）")
    ids = {item["slot"] for item in cal["slots"]}
    for slot in sorted(ids - set(mapped)):
        bad.append("%s：契约 §4b 里没有这一行的散文" % slot)
    for slot in sorted(set(mapped) - ids):
        bad.append("散文里有一枚在册之外槽位：%s" % slot)
    for item in cal["slots"]:
        cells = mapped.get(item["slot"])
        if cells is None:
            continue
        want = expected_row_cells(item)
        if tuple(cells) != want:
            for name, got, expected in zip(
                ("量具", "原始读数件·字段", "达成条件", "在册格名", "本窗可取材", "落数前欠"), cells, want
            ):
                if got != expected:
                    bad.append("%s：%s 一列散文与观测面分家（散文抄成了第二套）" % (item["slot"], name))
    return bad


def check_spine_is_one(cal: dict):
    """判据③的下半场：一副脊柱，逐格只换分母。谁在某一格里另写一套算术，这儿红。"""
    bad = []
    spine = cal["spine"]
    if len(spine) < 2:
        return ["脊柱少于两条：共享算术没落进代码"]
    for item in cal["slots"]:
        condition = item["condition"]
        if not condition.startswith(spine[0] % item["denominator"]):
            bad.append("%s：达成条件的开头不是脊柱第一条（分母被换掉了）" % item["slot"])
        for line in spine[1:]:
            if line not in condition:
                bad.append("%s：达成条件里丢了脊柱的一条：%s" % (item["slot"], line[:24]))
        if condition.count("MIN_SLO_SAMPLES") != 1:
            bad.append("%s：样本门被复制了（只许出现一次，且只以名字出现）" % item["slot"])
        if condition.count(cal["percentile_source"]) != 1:
            bad.append("%s：排名件的名字不是只出现一次 —— 有第二套算术的味儿" % item["slot"])
    return bad

def check_no_numbers(text: str, cal: dict):
    """判据②：本单交付面里一枚实测数都不许出现，形状是「未实测的秒数 = 不可承诺」。"""
    bad = []
    for offender in find_magnitudes(caliber_section(text)):
        bad.append("§4b 散文里出现了一枚量级：%r" % offender)
    for item in cal["slots"]:
        for leg, value in caliber_fields(item).items():
            for offender in find_magnitudes(str(value)):
                bad.append("%s：「%s」那一件里出现了一枚量级：%r" % (item["slot"], leg, offender))
    for line in cal["spine"]:
        for offender in find_magnitudes(line):
            bad.append("脊柱里出现了一枚量级：%r" % offender)
    for name in ("sample_floor",):
        if str(cal[name]).isdigit():
            bad.append("观测面把样本门抄成了数字：%s" % cal[name])
    if any(item["target"] is not None for item in cal["slots"]):
        bad.append("有 target 被填了：本单只钉口径")
    return bad


def target_rows(text: str):
    """§4 那张「每格现在写着什么」的表：五列、首列是裸档名（与 R105/R32 同一枚解析口径）。"""
    lanes = {tier.lane for tier in observability.slo_tiers()}
    return [
        row for row in table_rows(slo_section(text), cells=TARGET_CELLS) if row[0].strip("`") in lanes
    ]


def fillable(item) -> bool:
    """把观测面那句「派生不手写」在测试端再算一遍：两遍不一致就是有人把旗帜手举了。"""
    return bool(
        item["window_admissible"]
        and item["reader_landed"]
        and item["roster_cell"]
        and not item["prerequisite"]
        and item["raw_readout"]
        and item["raw_field"]
        and item["instrument"]
        and item["instrument_paths"]
    )


def evidence_backed(item, cal, root: Path = REPO):
    """一枚格今天到底有没有落进仓的凭据件：占位符没换成实名 = 没有凭据。"""
    posix = str(item["raw_readout"]).replace("\\", "/")
    if WINDOW_PLACEHOLDER in posix:
        return False
    if not any(posix.startswith(dir_) for dir_ in cal["evidence_dirs"]):
        return False
    if not (root / posix.split("（")[0].strip().split(" ")[0]).is_file():
        return False
    return fillable(item)


def check_targets_pending(text: str, cal: dict):
    """判据④：乙半没交之前，§4 的 目标 列必须还至少有一枚「待真机样本」；偷填而拿不出凭据即红。"""
    bad = []
    rows = target_rows(text)
    metric_slots = [item for item in cal["slots"] if ".stage." not in item["slot"]]
    if len(rows) != len(metric_slots):
        bad.append("§4 的数字格行数与观测面派生的档位格数不等：%d vs %d" % (len(rows), len(metric_slots)))
    by_slot = {item["slot"]: item for item in metric_slots}
    pending = 0
    for row in rows:
        lane = row[0].strip("`")
        metric = re.findall(r"`([^`]+)`", row[1])
        slot = "%s.%s" % (lane, metric[0] if metric else row[1])
        cell = row[-1]
        if cell == PENDING_TEXT:
            pending += 1
            continue
        item = by_slot.get(slot)
        if item is None:
            bad.append("§4 里有一枚观测面没有的格子：%s" % slot)
            continue
        if cell and not find_magnitudes(cell):
            bad.append("%s：目标格被填成了非量级的东西（%r）——要么待真机样本，要么实测数" % (slot, cell))
        if not evidence_backed(item, cal):
            bad.append(
                "%s：目标格被填成了 %r，但拿不出在册凭据件（量具/读数件/样本门任缺一件）" % (slot, cell)
            )
    if pending < 1:
        bad.append("§4 的目标格里一枚「待真机样本」都不剩：乙半没交之前这不可能")
    return bad


def check_roster_cells(cal: dict, roster: dict):
    """判据③的单位映射：数值格只准挂在名册里 kind=latency 且 cloud=False 的那一枚格上。"""
    bad = []
    for item in cal["slots"]:
        name = item["roster_cell"]
        if not name:
            continue
        row = roster.get(name)
        if row is None:
            bad.append("%s：在册格名 %r 在 R453 名册里不存在" % (item["slot"], name))
            continue
        if row["kind"] != "latency":
            bad.append("%s：%s 不是时延族格（kind=%s），数值格不许挂它" % (item["slot"], name, row["kind"]))
        if row["cloud"]:
            bad.append("%s：%s 可在云端形状窗读，数值必本机 ⇒ 不许当这格的凭据" % (item["slot"], name))
        if "caliber=local-full" not in item["condition"]:
            bad.append("%s：挂着只许本机的在册格，条件里却没写 caliber=local-full" % item["slot"])
    return bad


def check_handoff(text: str, cal: dict):
    """判据⑥：run10 收窗之后谁落哪一格、按什么命令、附什么凭据，逐族点名，不许留白。"""
    bad = []
    section = caliber_section(text)
    rows = table_rows(section, cells=HANDOFF_CELLS)
    families = {item["family"].split("-")[0] for item in cal["slots"]}
    named = {row[0].strip("*") for row in rows}
    for family in sorted(families - named):
        bad.append("交接表里没有家族 %s 那一行（乙半要重新发明一遍才落得了数）" % family)
    for family in sorted(named - families):
        bad.append("交接表里有一枚在册之外的家族：%s" % family)
    for row in rows:
        if "python scripts/" not in row[4]:
            bad.append("交接表 %s 那一行没给可跑的命令，只给了散文" % row[0])
        for token in ("sha256", "caliber=local-full"):
            if token not in row[5]:
                bad.append("交接表 %s 那一行的凭据格里没有 %s" % (row[0], token))
        if not row[2].strip():
            bad.append("交接表 %s 那一行没写是谁" % row[0])
    if HANDOFF_TITLE not in section:
        bad.append("§4b 里没有 run10 交接表那一节")
    return bad


def check_response_addressing(text: str, cal: dict):
    """寻址同源：槽位在回执里的那一格由 §4 的模板长出来，本单不发明第四种叫法。"""
    bad = []
    codes = re.findall(r"`([^`]+)`", slo_section(text).split(CALIBER_TITLE)[0])
    metric_templates = [code for code in codes if ".numbers.<name>" in code]
    stage_templates = [code for code in codes if ".stage_numbers.<stage>.{" in code]
    if len(metric_templates) != 1:
        return ["§4 里 numbers 的寻址模板不唯一：%s" % metric_templates]
    if len(stage_templates) != 1:
        return ["§4 里 stage_numbers 的寻址模板不唯一：%s" % stage_templates]

    spelled = [part.strip() for part in re.findall(r"\{([^}]*)\}", stage_templates[0])[0].split(",")]
    if sorted(spelled) != sorted(observability.SLO_STAGE_QUANTILES):
        bad.append("每段那两枚分位与 §4 那句不同源：%s vs %s" % (spelled, list(observability.SLO_STAGE_QUANTILES)))
    for item in cal["slots"]:
        lane, _, tail = item["slot"].partition(".")
        if tail.startswith("stage."):
            _, stage, quantile = tail.split(".")
            want = (
                stage_templates[0]
                .replace("[lane]", "[%s]" % lane)
                .replace("<stage>", stage)
                .replace("{%s}" % ",".join(spelled), quantile)
            )
        else:
            want = metric_templates[0].replace("[lane]", "[%s]" % lane).replace("<name>", tail)
        if item["response_path"] != want:
            bad.append("%s：回执寻址与 §4 模板不同源（%s ≠ %s）" % (item["slot"], item["response_path"], want))
    return bad


def check_caliber(text: str, cal: dict, roster: dict | None = None):
    """一把抓：反证刀只需要把这枚函数喂 mutated 输入，正向用例也用它。"""
    violations = []
    violations.extend(check_legs(cal))
    violations.extend(check_instruments_on_disk(cal))
    violations.extend(check_reference_fields(cal))
    violations.extend(check_doc_agreement(text, cal))
    violations.extend(check_spine_is_one(cal))
    violations.extend(check_no_numbers(text, cal))
    violations.extend(check_targets_pending(text, cal))
    violations.extend(check_response_addressing(text, cal))
    if roster is not None:
        violations.extend(check_roster_cells(cal, roster))
    violations.extend(check_handoff(text, cal))
    return violations

# ==================== 正向用例：清单必须为空 ====================


def derived_slot_ids():
    """槽位宇宙由 ``slo_tiers()`` 长出来：枚数不抄常数，改名动一边就露馅。"""
    ids = []
    for tier in observability.slo_tiers():
        for metric in tier.metrics:
            ids.append("%s.%s" % (tier.lane, metric.name))
        for stage in tier.stages:
            for quantile in observability.SLO_STAGE_QUANTILES:
                ids.append("%s.stage.%s.%s" % (tier.lane, stage, quantile))
    return ids


def test_the_caliber_covers_every_derived_slot() -> None:
    """判据①的结构面：一枚不多、一枚不少。"""
    cal = caliber()
    assert sorted(item["slot"] for item in cal["slots"]) == sorted(derived_slot_ids())
    assert cal["uncalibrated"] == []
    assert cal["orphan"] == []
    assert cal["schema"] == "r526.slo-caliber/1"


def test_no_slot_is_missing_a_leg() -> None:
    """判据①：量具 / 原始读数件 / 达成条件，缺一件就红。"""
    assert check_legs(caliber()) == []


def test_the_instruments_are_files_in_the_repository() -> None:
    """判据①的一半诚实：引用的件必须在仓里，Temp 里的件不算量具。"""
    assert check_instruments_on_disk(caliber()) == []


def test_the_named_field_really_comes_out_of_the_reference_readout() -> None:
    """格子里写「取哪一格」，就得在上一窗那枚真件里逐行取得出。"""
    assert check_reference_fields(caliber()) == []


def test_the_contract_row_and_the_module_are_the_same_words() -> None:
    """判据③：散文是渲染，不是第二套口径。"""
    assert check_doc_agreement(contract_text(), caliber()) == []


def test_the_spine_is_written_once_and_plugged_per_slot() -> None:
    """判据③的下半场：一副脊柱 + 本格分母，样本门与排名件只以名字出现。"""
    cal = caliber()
    assert check_spine_is_one(cal) == []
    assert cal["sample_floor"] == "MIN_SLO_SAMPLES"
    assert cal["percentile_source"] == observability.SLO_PERCENTILE_SOURCE


def test_the_may_fill_flag_is_derived_not_declared() -> None:
    """`may_fill_from_window` 是算出来的：观测面写的旗帜与三件本身必须一致。"""
    for item in caliber()["slots"]:
        assert item["may_fill_from_window"] == fillable(item), item["slot"]


def test_the_caliber_publishes_no_measured_number() -> None:
    """判据②：未实测的秒数 = 不可承诺，这条写成了能跑的牙。"""
    text = contract_text()
    bad = check_no_numbers(text, caliber())
    assert bad == [], bad


def test_this_file_itself_publishes_no_numbers() -> None:
    """本单的牙自己先过一遍尺：这枚钉文件里不许藏着任何一枚量级。"""
    source = Path(__file__).resolve().read_text(encoding="utf-8")
    start, end = source.rindex(FORGERY_START), source.rindex(FORGERY_END)
    scanned = source[:start] + source[end:]
    assert find_magnitudes(scanned) == []
    # 弹药清单本身确实装着会被咬住的东西 —— 排除的理由就是它必须被排除。
    assert find_magnitudes(source[start:end])


def test_the_number_scanner_is_not_a_dead_tooth() -> None:
    """判据⑤的正控前置：先证明这枚尺会咬，再拿它当牙。"""
    # --- 伪造弹药（只喂影子的副本，永不落纸，也排除在下一枚自扫用例之外）---
    should_bite = [
        "p95 = 90 s",
        "端到端 154510.722 ms 收窗",
        "首屏 800毫秒",
        "correctness = 0.94",
        "输出 512 tokens",
        "准确率 0.2381",
    ]
    # --- 弹药结束 ---
    for sample in should_bite:
        assert find_magnitudes(sample), sample
    must_not_bite = [
        "p95_ms",
        "p50_ms",
        "MIN_SLO_SAMPLES",
        "R453 裁定（b）",
        "docs/testing/sidecar-run10.jsonl",
        "sha256",
        "nearest rank: the value at ceil(n * q), 1-based",
        "app/api/v1/observability.py::read_stage_latency",
        "2026-09-30",
        "P-18",
        "§4b",
        "{p50_ms,p95_ms}",
    ]
    for sample in must_not_bite:
        assert find_magnitudes(sample) == [], sample


def test_the_target_column_still_says_awaiting_real_samples() -> None:
    """判据④：乙半没交之前 §4 的目标格必须还挂着「待真机样本」，且不许被偷填。"""
    assert check_targets_pending(contract_text(), caliber()) == []


def test_the_roster_cell_mapping_is_the_registered_one(r453_cells) -> None:
    """判据③的单位映射：数值格只认名册里 kind=latency、cloud=False 的那一枚格。"""
    assert check_roster_cells(caliber(), r453_cells) == []


def test_the_run10_handoff_table_is_complete() -> None:
    """判据⑥：每一族都有「谁 / 命令 / 凭据」，乙半不用重新发明。"""
    assert check_handoff(contract_text(), caliber()) == []


def test_the_document_claim_about_today_matches_the_code() -> None:
    """散文说「今天一枚都落不了数」，代码就得真是这样；变了就得同时改散文。"""
    cal = caliber()
    section = caliber_section(contract_text())
    claim = "今天每一枚派生出来的 `may_fill_from_window` 都是 `False`"
    fillable = [item["slot"] for item in cal["slots"] if item["may_fill_from_window"]]
    if claim in section:
        assert fillable == [], "散文还写着全不可填，代码已经能填：%s" % fillable
    else:
        assert fillable, "散文的「今天全不可填」那句被删了，但代码里也没有一枚可填 —— 该把那句留回来"


def test_the_caliber_never_invents_a_blocker() -> None:
    """本单只引用 §6 那本名册里的 blocker 枚名，一枚都不新造。"""
    book = set(observability.SLO_BLOCKERS)
    for item in caliber()["slots"]:
        codes = [block["code"] for block in item["blockers"]]
        assert codes, item["slot"]
        assert set(codes) <= book, (item["slot"], sorted(set(codes) - book))
    assert "lane_attribution_absent" in book


def test_the_slots_are_addressed_the_way_the_document_addresses_them() -> None:
    """寻址同源：每段两枚的分位名、numbers / stage_numbers 两条路径，都由 §4 的模板派生。"""
    assert check_response_addressing(contract_text(), caliber()) == []


def test_the_observation_surface_does_not_reach_into_the_response() -> None:
    """写域纪律：口径面可机读，但没接进回执 —— 加键＝改形状，不属本单。"""
    import inspect

    for name in ("slo_readout", "read_slo"):
        source = inspect.getsource(getattr(observability, name))
        assert "slo_slot_caliber" not in source, name
    assert list(inspect.signature(observability.read_slo).parameters) == ["request"]


def test_the_caliber_is_machine_readable_json() -> None:
    """「可查询描述」的意思：一次调用交出整张表，且逐格带着 target=None。"""
    payload = json.dumps(caliber(), ensure_ascii=False, default=str)
    assert "r526.slo-caliber/1" in payload
    assert all(item["target"] is None for item in caliber()["slots"])
    assert all(item["target_status"] == observability.SLO_TARGET_PENDING for item in caliber()["slots"])


def test_the_full_suite_of_checks_is_empty_on_the_shipped_tree(r453_cells) -> None:
    """一把抓：以上所有牙在真盘面上一起跑，结论必须是零违规。"""
    assert check_caliber(contract_text(), caliber(), r453_cells) == []