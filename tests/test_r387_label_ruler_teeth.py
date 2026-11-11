# -*- coding: utf-8 -*-
"""R387 · 标签量具的下牙：把「越权 0 条」这句会在空集上假绿的话，钉成一条能量出未验的判据。

病灶（R382 现场量出、总控独立复现）：生产 `chunk_vectors` 那 1008 枚 `department` 全 = `''`、
`classification` 全 = `1`，遗留引擎（Chroma）那卷元数据同空。于是任何部门谓词在真库上是**恒空集**，
"越权 0 条"就在空集意义上成立 —— 部门隔离这条腿从来没有被任何一条非空标签喂过。

本件不连库、不起服务、不打模型：它钉的是**量具本身**。`scripts/r387_label_lineage.py` 是判据的唯一之家，
本件从那里 import，不复制第二套判序，也不另抄一份行号 —— 那正是 `migrations` 里那句 COMMENT 警告过的第二本账：两处各写一遍，改一处留一处，最后谁都不知道自己读的是哪一本。

八把刀，逐条都是"摘掉守卫它必须咬"的形状：
①标签全空 + 召回非空 + 越权 0 ⇒ 必须未验（而且必须与朴素判法分歧 —— 分歧就是那颗假绿）；
②标签齐 + 召回 0 行 ⇒ 必须未验（0 越权 / 0 召回是同一个空集）；
③只有一枚部门 / ④只有一档密级 ⇒ 必须未验（没有选择性就等于没测）；
⑤主体侧没有部门 ⇒ 必须未验（那一臂测的不是部门隔离）；
⑥真有越权 ⇒ 必须"不通过"，且优先级压过一切未验理由（安全问题不许被"未验"盖掉）；
⑦一条真臂 ⇒ 必须已验（防止把量具改成永远红的观察钉）；
⑧引用点不腐：每一跳的行号由锚块现读派生 —— 锚不唯一、或表与现读不符，当场红。
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: 变异检验用的唯一挂钩：把量具指到一份"摘掉守卫"的副本上。
#: 平时不设这个变量，SCRIPT 就是仓库里那一枚 —— 本钉不因为它而改变判定口径。
SCRIPT = Path(os.getenv("R387_LABEL_TOOL") or (REPO / "scripts" / "r387_label_lineage.py"))


def _load_module():
    spec = importlib.util.spec_from_file_location("r387_label_lineage", SCRIPT)
    assert spec and spec.loader, f"无法加载量具：{SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    # dataclass(frozen=True) 在 @dataclass 展开时要回查 sys.modules[cls.__module__]，
    # 手工 importlib 不注册就会炸成 NoneType.__dict__，这不是量具的缺陷，是加载器的。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


R387 = _load_module()

ArmReading = R387.ArmReading
classify_arm = R387.classify_arm
naive_verdict = R387.naive_verdict
VERIFIED = R387.VERIFIED
FAILED = R387.FAILED
UNVERIFIED = R387.UNVERIFIED


def arm(**overrides) -> ArmReading:
    """一条**本来能判**的臂：四枚部门、三档密级、召回非空、越权为零。

    各把刀都只从这里改一格，改出来的分歧就必须由那一格解释，而不是由别处的巧合解释。
    """
    base = {
        "name": "fin-arm",
        "principal_departments": ("财务",),
        "principal_clearance": 2,
        "corpus_labelled_chunks": 900,
        "corpus_departments": ("财务", "人力资源", "研发", "销售"),
        "corpus_classifications": ("1", "2", "3"),
        "recalled": 60,
        "breaches": 0,
    }
    base.update(overrides)
    return ArmReading(**base)


# ---------------------------------------------------------------- 刀①：生产今天的形状

def test_all_empty_labels_with_nonempty_recall_is_unverified_not_passed() -> None:
    """生产实测形状（1008 枚全空标签、召回非空、越权 0）必须判成未验。

    这就是 R382 那一格：`hr-c1` 臂两侧 12/12 裁空、四臂越权 0/0，看着全绿。
    """
    production = arm(corpus_labelled_chunks=0, corpus_departments=(), corpus_classifications=("1",),
                     recalled=1008, breaches=0)
    verdict = classify_arm(production)
    assert verdict["verdict"] == UNVERIFIED, (
        "标签全空却被判成 " + str(verdict["verdict"]) + "：那句「越权 0 条」又会变成空集意义上的通过")
    assert verdict["reason"] == R387.REASON_NO_LABELLED_CHUNK, verdict


def test_the_guarded_and_the_naive_ruler_must_disagree_on_empty_labels() -> None:
    """🔴 本件真正的下牙：同一份读数，朴素判法（只看 breaches）说已验，守卫说未验。

    谁把 `corpus_labelled_chunks` 那一格守卫摘掉，`classify_arm` 就退回朴素判法，
    这条钉当场红 —— 它测的不是"今天数据长什么样"，而是"量具还记不记得空集不是证据"。
    """
    production = arm(corpus_labelled_chunks=0, corpus_departments=(), corpus_classifications=("1",),
                     recalled=1008, breaches=0)
    guarded = classify_arm(production)["verdict"]
    naive = naive_verdict(production)["verdict"]
    assert naive == VERIFIED, (
        "朴素判法不再说已验：说明 breaches 那一条也被改过，对照基线消失了，本件无从判定假绿")
    assert guarded != naive, "守卫与朴素判法在这一份读数上重合 ⇒ 空标签守卫已经是装饰"


# ---------------------------------------------------------------- 刀②：空返回不是隔离

def test_zero_recall_arm_is_unverified_even_with_rich_labels() -> None:
    """标签齐、越权 0、但一条都没召回 ⇒ 未验。0 越权与 0 召回是同一个空集。"""
    verdict = classify_arm(arm(recalled=0, breaches=0))
    assert verdict["verdict"] == UNVERIFIED, verdict
    assert verdict["reason"] == R387.REASON_EMPTY_RETURN, verdict


# ---------------------------------------------------------------- 刀③④：选择性两轴

def test_single_department_corpus_is_unverified() -> None:
    verdict = classify_arm(arm(corpus_departments=("财务",)))
    assert verdict["verdict"] == UNVERIFIED, verdict
    assert verdict["reason"] == R387.REASON_NO_DEPARTMENT_SELECTIVITY, verdict


def test_single_classification_corpus_is_unverified() -> None:
    verdict = classify_arm(arm(corpus_classifications=("1",)))
    assert verdict["verdict"] == UNVERIFIED, verdict
    assert verdict["reason"] == R387.REASON_NO_CLASSIFICATION_SELECTIVITY, verdict


# ---------------------------------------------------------------- 刀⑤：主体侧也要有料

def test_principal_without_department_is_unverified_not_trusted() -> None:
    """主体没有部门 ⇒ 未验。`app/rag/filters.py` 对这种账号是直接 raise（authorization_unavailable），
    管理员那一档根本不发部门谓词（`departments=None`）—— 两种都不是"部门隔离被测过了"。"""
    verdict = classify_arm(arm(principal_departments=()))
    assert verdict["verdict"] == UNVERIFIED, verdict
    assert verdict["reason"] == R387.REASON_PRINCIPAL_UNSCOPED, verdict


# ---------------------------------------------------------------- 刀⑥：越权压过一切

def test_a_real_breach_fails_and_outranks_every_unverified_reason() -> None:
    """越权 > 未验：安全问题不能被"这一格还没量"盖过去。

    这份读数同时带着标签全空 —— 如果判序反了，它会说"未验"，于是越权被吞掉。
    """
    verdict = classify_arm(arm(corpus_labelled_chunks=0, corpus_departments=(), recalled=1008, breaches=1))
    assert verdict["verdict"] == FAILED, verdict
    assert verdict["reason"] == R387.REASON_BREACH, verdict


# ---------------------------------------------------------------- 刀⑦：不许改成永远红

def test_an_arm_with_real_labels_and_real_recall_is_verified() -> None:
    """反证的反证：一条真有选择性、真有召回、真零越权的臂必须能判成已验。

    没有这一条，任何人都可以把量具改成"一律未验"来假装严谨 —— 那同样是一枚没有牙的钉。
    """
    verdict = classify_arm(arm())
    assert verdict["verdict"] == VERIFIED, verdict


# ---------------------------------------------------------------- 判序不许被重排

def test_guard_order_is_breach_then_principal_then_labels_then_selectivity_then_recall() -> None:
    """六条守卫各占一格、顺序唯一。多一条或少一条都红。

    这条钉的形状是"逐项破坏"：把某一条守卫要成立的前提改成不成立，判词必须换到那一格的原因码。
    """
    expectations = (
        (arm(breaches=1), R387.REASON_BREACH),
        (arm(principal_departments=(), breaches=1), R387.REASON_BREACH),
        (arm(principal_departments=()), R387.REASON_PRINCIPAL_UNSCOPED),
        (arm(corpus_labelled_chunks=0), R387.REASON_NO_LABELLED_CHUNK),
        (arm(corpus_departments=("财务",)), R387.REASON_NO_DEPARTMENT_SELECTIVITY),
        (arm(corpus_classifications=("1",)), R387.REASON_NO_CLASSIFICATION_SELECTIVITY),
        (arm(recalled=0), R387.REASON_EMPTY_RETURN),
        (arm(), "标签非空、两轴都有选择性、召回非空且零越权"),
    )
    seen: list = []
    for candidate, expected in expectations:
        verdict = classify_arm(candidate)
        assert verdict["reason"] == expected, (
            f"读数 {candidate.name}/{candidate.corpus_labelled_chunks}/"
            f"{candidate.corpus_departments}/{candidate.corpus_classifications}/"
            f"{candidate.recalled}/{candidate.breaches} 判成 {verdict['reason']!r}，期望 {expected!r}")
        seen.append(verdict["verdict"])
    assert seen.count(UNVERIFIED) == 5, seen
    assert seen.count(FAILED) == 2, seen
    assert seen.count(VERIFIED) == 1, seen


# ---------------------------------------------------------------- 只读 posture

def test_the_tool_issues_no_writes_by_construction() -> None:
    """取证件的 SQL 面只许有 SELECT：出现任何写语句，本件当场红。"""
    source = Path(SCRIPT).read_text(encoding="utf-8")
    statements = " ".join(R387.PG_STATEMENTS.values()) + " ".join(R387.CHROMA_STATEMENTS.values())
    forbidden = ("INSERT", "UPDATE", "DELETE", "ALTER", "CREATE", "DROP", "TRUNCATE", "COPY", "GRANT")
    found = sorted({word for word in forbidden if re.search(r"\b" + word + r"\b", statements)})
    assert not found, "读数语句里出现写动作：" + str(found)
    assert "SET default_transaction_read_only = on" in source, "PG 侧没压会话只读"
    assert "mode=ro" in source and "PRAGMA query_only" in source, "遗留引擎侧没走只读打开"
    assert "import chromadb" not in source and "PersistentClient(" not in source, (
        "取证件不许走 chromadb 客户端：它会动遗留卷的 mtime 与 WAL，而 AGENTS.md 明令 "
        "Chroma 是退役中的遗留件，本单不得新增任何 Chroma 写点")


def test_pg_leg_refuses_the_wrong_database() -> None:
    """`--expect-database` 闸门必须真在：把别人的库读成生产是本仓的老事故形状。"""
    source = Path(SCRIPT).read_text(encoding="utf-8")
    assert "attached != expect_database" in source, "库名闸门被摘掉了"
    assert "ABORT" in source, "闸门不放行时必须点名 ABORT"


# ---------------------------------------------------------------- 刀⑧：引用点不腐（派生版）

#: 🔴 锚块的家只有一处：`scripts/r387_label_lineage.py::LINEAGE_SITES`。本件**不再另立一张 token 表** ——
#: 另立一张就是"抄来的字面量"病复发：一处改了另一处照旧绿。下面所有断言的锚都从量具现取。
#: 本件唯一自持的主张是这一枚表：文档 §1 表里每一跳「至少有几格带着自己的锚」。
#: 口径数的是文档表那一格里的锚数（内层引用也算一格）；这里是"至少几格"，不是行号。
MIN_TABLE_CELLS = {5: 5, 6: 4, 7: 5, 10: 3, 12: 3}

DOC_LINEAGE = REPO / "docs" / "perf" / "r387-label-lineage-2026-09-27.md"
ROW_PATTERN = re.compile(r"^\| (\d+) \| ")
KEY_PATTERN = re.compile(r"\{(\w+)\}")
LITERAL_CITE = re.compile(r":\d{2,}")
PROSE_CITE = re.compile(r"([A-Za-z0-9_./-]+[.](?:py|vue|sql)):`?(\d+)(?:-(\d+))?`?")



def doc_lineage_cells() -> dict:
    """取文档 §1 那张血缘表里逐跳"站点"格 —— 也就是**表里印的字面量**。"""
    text = DOC_LINEAGE.read_bytes().decode("utf-8").split("\r\n")
    start = [i for i, line in enumerate(text) if line.startswith("## 1. 判据①")]
    assert start, "文档里找不到 §1 那张血缘表"
    cells = {}
    for line in text[start[0] + 1:]:
        if line.startswith("## "):
            break
        match = ROW_PATTERN.match(line)
        if not match:
            continue
        seq = int(match.group(1))
        assert seq not in cells, f"§1 表里第 {seq} 跳出现了两行：这张表自己就有两本账"
        cells[seq] = line.split("|")[3].strip()
    return cells


def hop_keys(seq: int) -> list:
    """这一跳在 site、note、文档表三处模板里一共引用了哪几枚锚（按出现顺序去重）。"""
    template = next(h for h in R387.LINEAGE_TEMPLATES if h["seq"] == seq)
    keys = (KEY_PATTERN.findall(str(template["site"])) + KEY_PATTERN.findall(str(template["note"]))
            + KEY_PATTERN.findall(R387.HOP_DOC_CELLS[seq]))
    return list(dict.fromkeys(keys))


def fresh_cites(keys) -> dict:
    """绕开 import 期缓存，现场再解一遍：量具要是缓存了一库旧数，这一步就对不上。"""
    out = {}
    for key in keys:
        _file, first, last = R387.resolve_site(key, REPO)
        out[key] = str(first) if first == last else "%d-%d" % (first, last)
    return out


def own_anchor_hits(file: str, anchor: tuple) -> list:
    """本件自己数一遍锚（固定串 + 逐行 strip）：量具的解析器要是有洞，这一枚兜住。"""
    offset, block = anchor
    want = [line.strip() for line in block]
    lines = [line.strip() for line in (REPO / file).read_text(encoding="utf-8").splitlines()]
    return [i + 1 + offset for i in range(len(lines) - len(want) + 1) if lines[i:i + len(want)] == want]


#: 血缘表的 site 串按人话写：同一文件的第二处只写 "::<起>-<止>" 这种形状，不重复文件名。
#: 所以这里要让文件名往后继承，否则合法写法会被读成"没有 cite"。
SITE_PATTERN = re.compile(r"([A-Za-z0-9_./]+[.](?:py|sql)):(\d+)(?:-(\d+))?")
BARE_PATTERN = re.compile(r":(\d+)(?:-(\d+))?")


def cited_sites(site: str) -> list:
    """把 site 串拆成 [(file, start, end)]，文件名沿用最近一次出现的那一枚。"""
    found = []
    current = ""
    index = 0
    while index < len(site):
        match = SITE_PATTERN.match(site, index)
        if match:
            current = match.group(1)
            found.append((current, int(match.group(2)), int(match.group(3) or match.group(2))))
            index = match.end()
            continue
        bare = BARE_PATTERN.match(site[index:])
        if bare and current:
            found.append((current, int(bare.group(1)), int(bare.group(2) or bare.group(1))))
            index += bare.end()
            continue
        index += 1
    return found


@pytest.mark.parametrize("hop", R387.LINEAGE_HOPS, ids=lambda hop: str(hop["seq"]))
def test_every_lineage_hop_cites_a_file_that_still_exists(hop: dict) -> None:
    """判据①的每一跳都得点得出文件：文件没了＝这一跳的证据被搬家，结论要重量。"""
    sites = cited_sites(hop["site"])
    assert sites, f"第 {hop['seq']} 跳没有点出任何 file:line：{hop['site']}"
    for name, line, _end in sites:
        path = REPO / name
        assert path.is_file(), f"第 {hop['seq']} 跳引用的文件不在树里：{name}"
        total = len(path.read_text(encoding="utf-8").splitlines())
        assert int(line) <= total, f"{name}:{line} 越界（本文件只有 {total} 行）—— 行号已腐"


@pytest.mark.parametrize("seq", sorted(R387.HOP_DOC_CELLS), ids=str)
def test_lineage_site_is_derived_and_matches_the_doc_table(seq: int) -> None:
    """🔴 刀⑧正文（派生版，两条硬牙，零容差）。

    (a) 量具**现场解出**的行号 == 文档 §1 表里印的行号：`chat.py` 被并树撑长时表跟着走，
        谁手改表里那串数字，这一格当场红，红句直接端出"表里印 X、现读 Y"与是哪一跳；
    (b) 这一跳引用的每一枚锚，在被引文件里**恰枚一枚**命中：0 枚 = 那一格已经不在原处，
        ≥2 枚 = 锚不再是唯一锚 —— 两种都不许靠"±6 行容差"或"取第一次命中"糊过去。
    """
    keys = hop_keys(seq)
    assert keys, f"第 {seq} 跳没有引用任何锚：它那串行号是从哪儿来的？"
    for key in keys:
        file, start, end = R387.LINEAGE_SITES[key]
        for label, anchor in (("起点", start), ("终点", end)):
            if anchor is None:
                continue
            found = own_anchor_hits(file, anchor)
            assert len(found) == 1, (
                f"第 {seq} 跳的 {key} {label}锚在 {file} 里命中 {len(found)} 枚 {found}："
                + ("那一格已腐（不在原处）" if not found else
                   "凭据不再是唯一锚 —— 取第一次命中就是把血缘指到别人身上"))
    printed = doc_lineage_cells()[seq]
    derived = R387.HOP_DOC_CELLS[seq].format_map(fresh_cites(keys))
    assert R387.LINEAGE_DOC_CELLS[seq] == derived, (
        f"第 {seq} 跳：量具 import 期的缓存 {R387.LINEAGE_DOC_CELLS[seq]} 与本件现场解出的 {derived} 不一致")
    assert printed == derived, (
        f"第 {seq} 跳：表里印 {printed}、现读 {derived} —— 改表只有一处可改："
        "跑 `python scripts/r387_label_lineage.py --emit-doc-cells` 重落地，不许手改数字")


def test_multi_site_hops_give_every_site_its_own_anchor() -> None:
    """🔴 表里每一格数字各配一枚自己的锚，不许只咬第一格（跳 5/6/7/10/12 的洞在这里补）。

    上一班自陈「后几格实际上没被牙咬住」—— 那是 ±6 行容差留下的洞。这里三问：
    ① 同一枚锚不许在同一格里出现两次：一枚锚冒充两格 = 假格；
    ② 表里这一跳至少有该跳应有的那么多格：少一格就是那一格没人咬；
    ③ 同一跳各格解出来的行号两两不同：两格解到同一个数，其中一枚必然是装饰。
    """
    for template in R387.LINEAGE_TEMPLATES:
        seq = template["seq"]
        site_keys = KEY_PATTERN.findall(str(template["site"]))
        note_keys = KEY_PATTERN.findall(str(template["note"]))
        cell_keys = KEY_PATTERN.findall(R387.HOP_DOC_CELLS[seq])
        assert site_keys or note_keys, f"第 {seq} 跳的模板一枚锚都没引用"
        assert set(site_keys) <= set(cell_keys), (
            f"第 {seq} 跳：site 引用的锚在文档表里找不到出处 " + str(sorted(set(site_keys) - set(cell_keys))))
        for label, keys, text in (("site", site_keys, str(template["site"])),
                                  ("note", note_keys, str(template["note"])),
                                  ("文档表", cell_keys, R387.HOP_DOC_CELLS[seq])):
            for key in keys:
                assert text.count("{" + key + "}") == 1, (
                    f"第 {seq} 跳的 {label} 把 {key} 复用成两格：那是拿一枚锚冒充两格的证据")
        floor = MIN_TABLE_CELLS.get(seq, 1)
        assert len(set(cell_keys)) >= floor, (
            f"第 {seq} 跳表里只有 {len(set(cell_keys))} 格带锚，少于该跳应有的 {floor} 格 —— 有格没被咬住")
        numbers = [value for value in fresh_cites(cell_keys).values()]
        assert len(set(numbers)) == len(numbers), (
            f"第 {seq} 跳有两格解到同一个行号 " + str(numbers) + " —— 其中一枚是装饰")


def one_of(lines, needle):
    hits = [i for i, line in enumerate(lines) if needle in line]
    assert len(hits) == 1, "文档里 " + needle + " 命中 " + str(len(hits)) + " 枚"
    return hits[0]


def section_one_body() -> list:
    """取文档 §1 那张表**之下**、到下一节标题之前的正文行 —— 那里也写着行号。"""
    lines = DOC_LINEAGE.read_bytes().decode("utf-8").split("\r\n")
    start = one_of(lines, "## 1. 判据①")
    out = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if line.startswith("| ") or set(line.strip()) <= set("+-: "):
            continue
        out.append(line)
    return out


def derived_values_by_file() -> dict:
    """每枚锚的现读值，按「全路径」与「裸文件名」两个键索引 —— 正文里两种写法都有。"""
    out = {}
    for key, (file, _start, _end) in R387.LINEAGE_SITES.items():
        _name, first, last = R387.resolve_site(key, REPO)
        rendered = str(first) if first == last else "%d-%d" % (first, last)
        for name in {file, file.rsplit("/", 1)[-1]}:
            out.setdefault(name, set()).add(rendered)
    return out


def test_the_prose_under_the_table_quotes_derived_numbers() -> None:
    """🔴 表下的正文可以写行号，但只许写**现读得到的那一个**：漂一枚就红。

    派生化之后还剩一处会自己长出旧账 —— 人写的正文。这一格把它并进同一本账：
    正文里每一枚「文件名 + 冒号 + 行号」都必须能在锚块现读值里找到同名同值的那一枚，
    找不到就是有人手抄了一份正在过期的数（R391 打红三枚用的就是这个形状）。
    """
    values = derived_values_by_file()
    checked = 0
    for line in section_one_body():
        for name, first, last in PROSE_CITE.findall(line):
            want = first if not last or last == first else first + "-" + last
            assert name in values, "正文引用了没有锚的文件：" + name
            assert want in values[name], (
                "正文里 " + name + " 的 " + want + " 不是现读值（现读只有 "
                + "、".join(sorted(values[name])) + "）—— 表要重落地，正文要跟着改")
            checked += 1
    assert checked >= 10, "正文里只认出 " + str(checked) + " 枚引用：这一格今天没在量东西"


def test_the_anchor_table_and_the_templates_share_one_ledger() -> None:
    """🔴 锚块表与模板引用互覆：多一枚是养闲，少一枚是漏钉。

    死锚比没锚更坏：它让下一班数出"四十六枚锚"这种漂亮数字，却没人知道其中几枚的
    引用点已经在上一班改表时被删掉了。两头都查才算同一本账。
    """
    referenced = set()
    for template in R387.LINEAGE_TEMPLATES:
        referenced.update(KEY_PATTERN.findall(str(template["site"])))
        referenced.update(KEY_PATTERN.findall(str(template["note"])))
    for cell in R387.HOP_DOC_CELLS.values():
        referenced.update(KEY_PATTERN.findall(cell))
    registered = set(R387.LINEAGE_SITES)
    dead = sorted(registered - referenced)
    ghosts = sorted(referenced - registered)
    assert not dead, "锚块表里有没人引用的死锚：" + str(dead)
    assert not ghosts, "模板引用了不存在的锚：" + str(ghosts)


def test_no_lineage_anchor_is_stale_or_ambiguous() -> None:
    """🔴 全局闸：量具自己记下的锚失效清单必须为空 —— 一枚都不许腐、不许撞。

    这一格与逐跳那枚分开红：某一枚锚腐时它只该打红自己那一跳（外加本闸），
    不许把 12 跳全淹成一片红 —— 那等于又把信号废一遍。
    """
    assert len(R387.LINEAGE_SITES) >= 12, "锚块比这一跳表还短：那是删了格没删引用"
    assert not R387.LINEAGE_ANCHOR_FAILURES, "锚失效清单不为空：" + " / ".join(R387.LINEAGE_ANCHOR_FAILURES)


def test_the_ruler_and_the_tool_carry_no_literal_line_numbers() -> None:
    """🔴 行号只能活在一处：量具与本件里不许出现"抄来的行号"字面量。

    这是 §8.5 那格"与本件上一版逐字节相等"的替代自证 —— 相不相等不是重点，
    重点是这两枚件里再没有一枚「文件名 + 冒号 + 数字」的写法，也就没有第二本可对不上的账。
    被引文件被并树撑长时只有派生的那些数跟着走，字面量不会。
    """
    clip = 72
    for rel in ("scripts/r387_label_lineage.py", "tests/test_r387_label_ruler_teeth.py"):
        src = (REPO / rel).read_bytes().decode("utf-8")
        bad = [(i + 1, line.strip()[0:clip]) for i, line in enumerate(src.split("\r\n")) if LITERAL_CITE.search(line)]
        assert not bad, rel + " 里又长出抄来的行号字面量：" + str(bad[0:5])
    for template in R387.LINEAGE_TEMPLATES:
        assert not LITERAL_CITE.search(str(template["site"])), f"第 {template['seq']} 跳 site 模板带数字"
        assert not LITERAL_CITE.search(str(template["note"])), f"第 {template['seq']} 跳 note 模板带数字"
    for seq, cell in R387.HOP_DOC_CELLS.items():
        assert not LITERAL_CITE.search(cell), f"文档表模板第 {seq} 行带数字"


@pytest.mark.parametrize("duplicating", [True, False], ids=["two-hits", "zero-hits"])
def test_the_deriver_has_no_first_hit_fallback(tmp_path: Path, duplicating: bool) -> None:
    """🔴 "命中不唯一就不许出数"是真分支：插一份副本行 ⇒ 抛；把那一格删掉 ⇒ 也抛。

    这里不许留"取第一次命中"那条路：并树往中间插一段长得像的代码是常事，那时候
    取第一枚等于把整条血缘表指到别人身上 —— 比红更糟。
    全程用 tmp_path 里的假文件，不碰仓库里任何被引文件。
    """
    key = "hop2"
    file, start, _end = R387.LINEAGE_SITES[key]
    block = [line.strip() for line in start[1]]
    filler = ["filler-line-that-is-not-an-anchor"]
    if duplicating:
        body = filler + block + filler + block + filler
    else:
        body = filler + ["the line that used to sit here has been deleted"] + filler
    fake = tmp_path.joinpath(*file.split("/"))
    fake.parent.mkdir(parents=True, exist_ok=True)
    fake.write_bytes("\r\n".join(body).encode("utf-8"))
    expected = 2 if duplicating else 0
    assert len(R387.anchor_lines(file, start, tmp_path)) == expected, "假文件本身没造出想要的那个形状"
    with pytest.raises(R387.AnchorNotUnique) as err:
        R387.resolve_site(key, tmp_path)
    message = str(err.value)
    if duplicating:
        assert "命中 2 枚" in message and "唯一锚" in message, message
    else:
        assert "命中 0 枚" in message and "已腐" in message, message



def test_lineage_names_the_first_hop_that_drops_a_true_value() -> None:
    """判据①要求点名"第一个把真值丢掉的那一跳"，且它是接口那一跳之后的服务端覆盖。"""
    assert R387.FIRST_TRUTH_LOST_AT == 2
    assert R387.REAL_BREAK_POINT_AT == 4
    kinds = {hop["seq"]: hop["kind"] for hop in R387.LINEAGE_HOPS}
    assert kinds[2] == "hardcoded", "第 2 跳不再是覆盖：判据①的点名要重下"
    assert kinds[11] == "default", "第 11 跳（chunk_vectors 落库）不再复制上游元数据：判据③要重裁"
    assert len(R387.LINEAGE_HOPS) >= 12, "血缘链被截短了：逐跳行号表不成立"
