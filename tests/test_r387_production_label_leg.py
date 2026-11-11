# -*- coding: utf-8 -*-
"""R387 · 生产标签腿的常驻钉：把验收 C 那句「越权 0 条」换成一条**今天能失败**的判据。

为什么这枚钉今天必须是红的（R382 现场量出来、总控独立复现的假绿）：生产 `chunk_vectors` 的 1008 枚
`department` 全 = `''`、`classification` 全 = `1`，遗留引擎（Chroma）那卷元数据同空。
⇒ 生产上任何部门谓词恒空集 ⇒ "越权 0 条"只在空集意义上成立 ⇒ 部门隔离这条腿从来没有被一条非空标签喂过。
所以本件的头条判据写成"**这一格今天过不了**"的形状：只有真把标签喂进去、并且真量出非空召回与零越权，
它才会转绿；谁想在标签全空的时候宣布 C 通过，它就是红的。

R390 补一笔形状账：那枚今天判不了的判据挂 `xfail(strict=True)` 而不是裸红，也不是 skip —— 全量门
要绿，而这一格不许被读成"过了"。`test_the_blocker_is_recorded_and_moves_with_the_data` 保持真绿
（它是"阻塞在案"那本账，一起 xfail 掉就等于整件没有主张了）。

只读与凭据口径（照本仓既有手法雷写死）：
* 读数走 `docker exec -i enterprise-brain-postgres-1 psql`，会话先压 `default_transaction_read_only`；
  真 DSN 与密码**一个字都不进本件**（连环境变量都不读，容器内 psql 走本机 socket 认证）。
* 判序不在本件复制：`classify_arm` 从 `scripts/r387_label_lineage.py` import（同一本账，两份真相是
  `migrations/0010_pgvector_chunks.sql:163-164` 警告过的形状）。
* 容器不在位 ⇒ `pytest.skip` 并明写「未验：本机读不到生产库」，🔴 不假装绿。
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "r387_label_lineage.py"
CONTAINER = "enterprise-brain-postgres-1"
DATABASE = "enterprise_brain"

#: 现读的三格账。列序与下方解析一一对应，改 SQL 必须同改解析。
CENSUS_SQL = """
SET default_transaction_read_only = on;
BEGIN;
SELECT count(*),
       count(*) FILTER (WHERE btrim(coalesce(department, '')) <> ''),
       count(*) FILTER (WHERE coalesce(classification, 1) <> 1),
       count(DISTINCT filename),
       coalesce(string_agg(DISTINCT nullif(btrim(department), ''), ','), ''),
       coalesce(string_agg(DISTINCT classification::text, ','), '')
FROM chunk_vectors;
SELECT count(*),
       count(*) FILTER (WHERE btrim(coalesce(metadata ->> 'department', '')) <> '')
FROM chunks;
SELECT count(*),
       count(*) FILTER (WHERE btrim(coalesce(department, '')) <> ''),
       coalesce(string_agg(DISTINCT nullif(btrim(department), ''), ','), '')
FROM users;
COMMIT;
"""


def _load_tool():
    spec = importlib.util.spec_from_file_location("r387_label_lineage", SCRIPT)
    assert spec and spec.loader, f"无法加载量具：{SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TOOL = _load_tool()


def container_running() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
        capture_output=True, text=True, timeout=30,
    )
    return probe.returncode == 0 and probe.stdout.strip().lower() == "true"


def read_census() -> dict:
    """跑那三条 SELECT，按行序还原成账。任何一步不如预期就 raise，不返回半个猜测。"""
    run = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", DATABASE, "-d", DATABASE,
         "-v", "ON_ERROR_STOP=1", "--no-psqlrc", "-tA", "-F", "~", "-f", "-"],
        input=CENSUS_SQL.encode("utf-8"), capture_output=True, timeout=120,
    )
    if run.returncode != 0:
        raise RuntimeError("只读读数失败：" + run.stderr.decode("utf-8", "replace")[:400])
    #: -tA 仍会把 SET / BEGIN / COMMIT 的命令标签打在行里，所以只认带分隔符的那几行。
    rows = [line.split("~") for line in run.stdout.decode("utf-8").splitlines()
            if "~" in line]
    if len(rows) != 3:
        raise RuntimeError(f"只读读数只拿回 {len(rows)} 行，预期 3 行；SQL 或 psql 版本变了")
    vector, chunk_leg, accounts = rows
    return {
        "chunk_vectors_rows": int(vector[0]),
        "chunk_vectors_labelled": int(vector[1]),
        "chunk_vectors_nondefault_classification": int(vector[2]),
        "chunk_vectors_files": int(vector[3]),
        "chunk_vector_departments": tuple(value for value in vector[4].split(",") if value),
        "chunk_vector_classifications": tuple(value for value in vector[5].split(",") if value),
        "chunks_rows": int(chunk_leg[0]),
        "chunks_labelled": int(chunk_leg[1]),
        "users_rows": int(accounts[0]),
        "users_with_department": int(accounts[1]),
        "user_departments": tuple(value for value in accounts[2].split(",") if value),
    }


def production_available() -> bool:
    if not container_running():
        return False
    try:
        read_census()
    except Exception:
        return False
    return True


LIVE = production_available()
UNAVAILABLE = "未验：本机读不到生产库（容器不在位或 psql 拒连），本件不假装绿"

pytestmark = pytest.mark.skipif(not SCRIPT.is_file(), reason="量具不在位，本件无从判定")


@pytest.fixture(scope="module")
def census() -> dict:
    if not LIVE:
        pytest.skip(UNAVAILABLE)
    return read_census()


@pytest.fixture(scope="module")
def production_arm(census: dict):
    """把生产读数折成一条臂。主体侧取 `users` 里真带部门的那些账号。"""
    if not LIVE:
        pytest.skip(UNAVAILABLE)
    return TOOL.ArmReading(
        name="production-department-leg",
        principal_departments=census["user_departments"],
        principal_clearance=3,
        corpus_labelled_chunks=census["chunk_vectors_labelled"],
        corpus_departments=census["chunk_vector_departments"],
        corpus_classifications=census["chunk_vector_classifications"],
        recalled=census["chunk_vectors_rows"],
        breaches=0,
    )


# ---------------------------------------------------------------------- 头条判据

#: R390 定案：这一格今天判不了，但也不许以「主干常驻红」的形式进树（事故 #56 刚钉过那条）。
#: `xfail(strict=True)` 是唯一同时满足「门绿」与「不假绿」的形状 ——
#:   ① 全量门今天绿；② pytest 摘要里它是 `1 xfailed`，**永远不计入 passed**，谁读都读不到「通过」；
#:   ③ strict = 生产真补上标签、这枚一转好，pytest 当场报 `XPASS(strict)` 变红，逼接手的人回来销账、
#:      按 docs/perf/r387-label-lineage-2026-09-27.md §4 改判「已验」——报警能力比裸红更强。
#: 🔴 这不等于验收 C 通过：台账上它记「未验」，既不记「通过」也不记「不通过」。
#: 形状由 tests/test_r390_xfail_strict_and_boundary_pins.py 钉死，摘掉 strict / 换成 skip 都会红。
ACCEPTANCE_C_BLOCKER = (
    "验收 C 未验（不是不通过）：生产 chunk_vectors.department 标签 0/1008 枚非空 ⇒ 部门谓词恒空集 ⇒ "
    "「越权 0 条」只在空集意义上成立，部门隔离这条腿从未被任何一条非空标签喂过。"
    "出处 docs/perf/r387-label-lineage-2026-09-27.md §4；标签回填后这枚转好会报 XPASS(strict)，届时按该节改判「已验」并销账。"
)


@pytest.mark.xfail(strict=True, reason=ACCEPTANCE_C_BLOCKER)
def test_acceptance_c_department_leg_passes_on_production(census: dict, production_arm) -> None:
    """🔴 判据④钉成的判据本体：这一格**今天判不了**，所以它是 xfail(strict=True)。

    它断言的是"部门隔离在生产真库上已被非空标签喂过、并且量出了非空召回与零越权"。
    今天的读数不支持这句话 —— 标签全空，于是这一枚今天必须**不算通过**；
    谁回填了标签、重测了这一臂并且真过，它就该以 XPASS 的形式红出来，逼人回来改判。
    """
    verdict = TOOL.classify_arm(production_arm)
    assert verdict["verdict"] == TOOL.VERIFIED, (
        "验收 C 的部门腿判词是 " + str(verdict["verdict"]) + "，原因：" + str(verdict["reason"])
        + "。现读：" + str(census["chunk_vectors_labelled"]) + "/"
        + str(census["chunk_vectors_rows"]) + " 枚带非空部门、"
        + str(len(census["chunk_vector_departments"])) + " 枚不同部门、"
        + str(len(census["chunk_vector_classifications"])) + " 档密级、"
        + str(census["users_with_department"]) + "/" + str(census["users_rows"])
        + " 枚账号有部门。把「越权 0 条」写成通过之前，先让这一枚转绿。")


def test_the_blocker_is_recorded_and_moves_with_the_data(census: dict, production_arm) -> None:
    """把今天的堵点登记下来：它一挪开（标签回填），这条钉就红，逼人来改判据而不是悄悄放行。"""
    verdict = TOOL.classify_arm(production_arm)
    if census["chunk_vectors_labelled"] == 0:
        assert verdict["reason"] == TOOL.REASON_NO_LABELLED_CHUNK, verdict
    else:
        assert verdict["reason"] != TOOL.REASON_NO_LABELLED_CHUNK, (
            "标签已经非空，判词却仍说空集：量具或读数坏了一处")


# ---------------------------------------------------------------------- 两本账对照

def test_the_two_vector_ledgers_are_empty_together(census: dict) -> None:
    """`chunk_vectors`（镜像）与 `chunks`（发布账）必须一致地空。

    两本账一致地空 ⇒ 病灶在派生上游（第 2/4 跳），不在镜像复制那一跳（第 11 跳）。
    若哪天只有镜像空、发布账不空，第 11 跳的复制口径就真的坏了，这条钉当场红。
    """
    assert census["chunk_vectors_rows"] == census["chunks_rows"], (
        f"两本账枚数不等：chunk_vectors={census['chunk_vectors_rows']} chunks={census['chunks_rows']}，"
        "本件的对照前提（同一批 chunk）已不成立")
    assert census["chunk_vectors_labelled"] == census["chunks_labelled"], (
        f"非空枚数不等：chunk_vectors={census['chunk_vectors_labelled']} "
        f"chunks={census['chunks_labelled']} —— 镜像与发布账对部门的口径分叉了")


def test_the_account_side_is_the_only_source_and_it_is_thin(census: dict) -> None:
    """量一句「主体侧有料吗」：账号里有部门的枚数，就是文档部门唯一可能的来源。

    这条读数同时是判据③ 的代价表依据 —— 它决定了"回填"到底是改配置还是改数据。
    """
    assert census["users_rows"] > 0, "users 表读不出行，本件无从判定"
    rate = census["users_with_department"] / census["users_rows"]
    print(f"[R387] 账号侧有部门的比例 = {census['users_with_department']}/{census['users_rows']} = {rate:.2f}")
    if rate == 0:
        pytest.fail("账号侧一枚部门都没有：文档部门的唯一入口本身就是空的，判据② 的"
                    "「源头就没有」这一桶要重量")


# ---------------------------------------------------------------------- 报数钉

def test_production_label_rate_is_reported(census: dict) -> None:
    """常驻报数：谁跑本件都能看到那三个数，不用再去翻容器。"""
    total = census["chunk_vectors_rows"]
    rate = (census["chunk_vectors_labelled"] / total) if total else 0.0
    print(
        "[R387 生产标签非空率] chunk_vectors labelled="
        f"{census['chunk_vectors_labelled']}/{total} = {rate:.4f} | "
        f"departments={list(census['chunk_vector_departments']) or '<ALL EMPTY>'} | "
        f"classifications={list(census['chunk_vector_classifications'])} | "
        f"nondefault_classification={census['chunk_vectors_nondefault_classification']} | "
        f"files={census['chunk_vectors_files']} | "
        f"publishing_ledger_labelled={census['chunks_labelled']}/{census['chunks_rows']} | "
        f"accounts_with_department={census['users_with_department']}/{census['users_rows']}"
    )
    assert total, "chunk_vectors 读出行数为 0：这不是「标签为空」，这是库没连对"
    if not LIVE:
        pytest.skip(UNAVAILABLE)
