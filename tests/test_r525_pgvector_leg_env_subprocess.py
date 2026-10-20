# -*- coding: utf-8 -*-
"""R525 判据④ —— ``INDEX_BACKEND=pgvector`` 摆进子进程 env 跑同一份夹具：先验必须仍生效。

在册那枚覆盖只有 ``test_r46_activity_signals.py::test_every_leg_of_search_routes_through_the_prior``，
它是**读源码数接线次数**（``source.count("self._apply_activity_prior(") >= 4``）。今天有五条腿
在接（降级 / 热集 / PGVector / Chroma 语义 / 关键词兜底），所以把 PGVector 那一支单独摘掉，
计数从 5 掉到 4，**那枚在册覆盖照样绿**——这一格由
``tests/test_r525_counter_evidence_teeth.py`` 的 K1 当场量出来（与 R520 量出「属性钉对 K1 全盲」
同一族做法），本件负责把 PG 那一支的行为补上钉。

## 这一格里真与被顶替的分别是谁（不含糊）

* **真**：``INDEX_BACKEND=pgvector`` 由**子进程环境**提供（driver 里对这一枚开关一个 setattr
  都没有），``indexing.read_backend()`` / ``pgvector_reads_enabled()`` 现读它；``search()`` 走的
  是 ``app/rag/retriever.py`` 的 PGVector 那一支；命中字典由产品的 ``_hit_dicts`` 生成；先验
  接线、形状账（``answered_by``）与读腿计数（``pg_store.vector_read_diagnostics``）全是产品码。
* **顶替**：``pg_store.read_topk`` 这一枚网络出口。原因是两格硬约束叠在一起——宿主 psycopg
  够不到部署库（compose 不给 postgres 发布宿主端口，``tests/conftest.py`` 与此同口径，本单
  实测 ``172.18.0.7:5432`` connect timeout），而真 ANN 需要 query embedding ⇒ **打模型 ⇒ 本单
  禁**（今晚还要开 run10 窗）。顶回去的内容不是随手编的：它是本单量具在真库上**真跑过的 ANN
  名次**（``l2`` 算符、``ef_search=100``、真 filename / chunk_index / 距离）。
* 🔴 因此「真库 ANN 经 psycopg 端到端」这一格**未量到**，条件写在读数纸里，不当已达标。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from test_r525_displacement_on_real_ranks import REAL_WINDOWS, single_carrier_index
from test_r525_real_store_readings import REPO_ROOT, LEG_WIDTHS, signal_on

#: 一趟子进程跑三档腿宽：DocumentRetriever 只冷起一次（chroma 客户端每换一个目录都要冷起，
#: 实测一枚目录约十秒，三趟会把测试时间写成被测代码的成本）。
DRIVER = r'''
import json
import os
import sys

REPO, INPUT, OUTPUT, CHROMA_DIR = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
sys.path.insert(0, REPO)

from app.rag import indexing, pg_store
from app.rag import retriever as rt
from app.rag.retriever import DocumentRetriever

payload = json.loads(open(INPUT, encoding="utf-8").read())
observed = {"env_index_backend": os.environ.get("INDEX_BACKEND"),
            "read_backend": indexing.read_backend(),
            "pgvector_reads_enabled": indexing.pgvector_reads_enabled()}


class StubEmbedding:
    """常量向量：本单不许打模型，而这一格要验的是名次接线，不是向量算术。"""

    def embed_query(self, text):
        return [0.5] * rt.EMBEDDING_DIM


read_topk_calls = []
chroma_query_calls = []
_current_rows = []


def replayed_read_topk(**kwargs):
    """顶替那一枚网络出口：交回量具在真库上真跑过的那份 ANN 名次（逐行原样）。"""
    read_topk_calls.append({"k": int(kwargs["k"]), "where": kwargs.get("where")})
    return [dict(row) for row in _current_rows[: int(kwargs["k"])]]


pg_store.read_topk = replayed_read_topk


def instrument(instance):
    """数一数遗留引擎到底被问了几次（判据④「只在 Chroma 腿上生效」的正面拦阻）。"""
    real_query = instance.collection.query

    def counted_query(*args, **kwargs):
        chroma_query_calls.append(kwargs.get("n_results"))
        return real_query(*args, **kwargs)

    instance.collection.query = counted_query
    return instance


def make_retriever(priors, chroma_dir):
    instance = DocumentRetriever(chroma_dir=chroma_dir, activity_prior=lambda: dict(priors))
    instance.embedding = StubEmbedding()
    return instrument(instance)


results = {}
for position, width in enumerate(payload["widths"], start=1):
    case = payload["cases"][str(position)]
    _current_rows = case["rows"]
    read_topk_calls.clear()
    chroma_query_calls.clear()
    instance = make_retriever(case["priors"], CHROMA_DIR)
    pg_store.reset_vector_read_diagnostics()
    rt.reset_search_shape()
    hits = instance.search(case["query"], k=int(width))
    last = rt.search_shape_diagnostics()["last"] or {}
    results[str(width)] = {
        "order": [hit["source"] for hit in hits],
        "chunk_indexes": [hit["chunk_index"] for hit in hits],
        "answered_by": last.get("answered_by"),
        "leg": last.get("leg"),
        "rows_returned": last.get("rows_returned"),
        "read_diagnostics": pg_store.vector_read_diagnostics(),
        "read_topk_calls": list(read_topk_calls),
        "chroma_query_calls": list(chroma_query_calls),
        "moves": [(hit["source"], hit["chunk_index"],
                   (hit.get("activity_prior") or {}).get("places_moved", 0)) for hit in hits],
    }

# 对照态：同一份夹具把开关留回缺省（chroma），证明上面几跑不是夹具自带的。
os.environ.pop("INDEX_BACKEND", None)
read_topk_calls.clear()
chroma_query_calls.clear()
control_instance = make_retriever(payload["cases"]["1"]["priors"], CHROMA_DIR)
rt.reset_search_shape()
control_hits = control_instance.search(payload["cases"]["1"]["query"], k=int(payload["widths"][0]))
control = {"read_backend_now": indexing.read_backend(),
           "answered_by": (rt.search_shape_diagnostics()["last"] or {}).get("answered_by"),
           "n_hits": len(control_hits),
           "chroma_query_calls_total": len(chroma_query_calls),
           "read_topk_calls_total": len(read_topk_calls)}

open(OUTPUT, "w", encoding="utf-8", newline="\n").write(
    json.dumps({"env": observed, "widths": results, "control": control}, ensure_ascii=False))
'''


@pytest.fixture(scope="module")
def pgvector_leg_run(tmp_path_factory):
    """跑一趟子进程：三档腿宽共用同一份真库名次与同一枚环境开关。"""
    work = tmp_path_factory.mktemp("r525-pg-leg")
    cases = {}
    expectations = {}
    for position, width in enumerate(LEG_WIDTHS, start=1):
        rows = REAL_WINDOWS[width]
        index = single_carrier_index(rows)
        cases[str(position)] = {"rows": rows, "priors": signal_on(rows, index),
                                "query": "季度营收",
                                "target": [rows[index]["filename"], rows[index]["chunk_index"]]}
        expectations[width] = (index, cases[str(position)]["target"], position)

    input_path = work / "input.json"
    output_path = work / "output.json"
    driver_path = work / "driver.py"
    chroma_dir = work / "chroma"
    input_path.write_text(json.dumps({"widths": list(LEG_WIDTHS), "cases": cases},
                                     ensure_ascii=False), encoding="utf-8", newline="\n")
    driver_path.write_text(DRIVER, encoding="utf-8", newline="\n")
    env = {**os.environ, "INDEX_BACKEND": "pgvector", "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("RAG_ACTIVITY_PRIOR", None)
    proc = subprocess.run([sys.executable, str(driver_path), str(REPO_ROOT), str(input_path),
                           str(output_path), str(chroma_dir)], capture_output=True, text=True,
                          encoding="utf-8", env=env, timeout=600)
    assert proc.returncode == 0, (proc.stdout[-800:], proc.stderr[-1500:])
    assert output_path.exists(), "子进程没交回产物"
    reading = json.loads(output_path.read_text(encoding="utf-8"))
    return reading, expectations


# ==================== 环境那一跳 ====================

def test_the_subprocess_really_read_the_switch_from_its_environment(pgvector_leg_run):
    """🔴 这一跳必须是环境给的：driver 里对 ``INDEX_BACKEND`` 一个 setattr 都没有。"""
    reading, _ = pgvector_leg_run
    env = reading["env"]
    assert env["env_index_backend"] == "pgvector", env
    assert env["read_backend"] == "pgvector", env
    assert env["pgvector_reads_enabled"] is True, env


# ==================== :1503 那一支真答了 ====================

@pytest.mark.parametrize("width", LEG_WIDTHS)
def test_the_pgvector_leg_answers_and_chroma_is_never_asked(pgvector_leg_run, width):
    """读腿被问了一次、遗留引擎一次都没被问、形状账写的是 pgvector。"""
    reading, _ = pgvector_leg_run
    leg = reading["widths"][str(width)]
    assert leg["answered_by"] == "pgvector", leg
    assert leg["leg"] == "semantic", "换引擎不是降级：腿名必须仍是 semantic"
    assert leg["rows_returned"] == width, leg
    assert leg["read_diagnostics"]["answered"] == 1, leg["read_diagnostics"]
    assert leg["read_topk_calls"] == [{"k": width, "where": None}], leg["read_topk_calls"]
    assert leg["chroma_query_calls"] == [], (
        "PG 腿答了还去问遗留引擎 ⇒ 这一跑不算走 :1503：" + str(leg["chroma_query_calls"]))


# ==================== 先验在这一支上仍然生效 ====================

@pytest.mark.parametrize("width", LEG_WIDTHS)
def test_the_prior_still_moves_ranks_on_the_pgvector_leg(pgvector_leg_run, width):
    """判据④的正身：切读之后先验照样改名次，买到一名，且名次与账对得上。

    🔴 如果接线只长在 Chroma 那一支上，这一枚当场红（PG 腿交回的次序与真库名次逐字相同）。
    """
    reading, expectations = pgvector_leg_run
    leg = reading["widths"][str(width)]
    index, (target_filename, target_chunk), _ = expectations[width]
    assert leg["order"][index - 1] == target_filename, (width, leg["order"])
    assert leg["chunk_indexes"][index - 1] == target_chunk, (width, leg["chunk_indexes"])
    moved = [(name, chunk, move) for name, chunk, move in leg["moves"] if move]
    assert moved and all(abs(move) == 1 for _, _, move in moved), (width, moved)
    promoted = [row for row in moved if row[2] == 1]
    assert len(promoted) == 1 and promoted[0][0] == target_filename, (width, moved)
    assert sorted(zip(leg["order"], leg["chunk_indexes"])) == sorted(
        (row["filename"], row["chunk_index"]) for row in REAL_WINDOWS[width]), (
        "切读不许多一枚候选或少一枚")


def test_the_control_run_stays_on_the_legacy_engine(pgvector_leg_run):
    """对照：把开关留回缺省，同一份夹具问的确实是另一条腿（否则上面几枚是自证）。"""
    reading, _ = pgvector_leg_run
    control = reading["control"]
    assert control["read_backend_now"] == "chroma", control
    assert control["answered_by"] == "chroma", control
    assert control["n_hits"] == 0, "新开的空 collection 答不出东西才对：" + str(control)
    assert control["chroma_query_calls_total"] == 1, control
    assert control["read_topk_calls_total"] == 0, control


def test_the_registered_source_count_pin_cannot_see_a_stripped_pg_exit():
    """在册那枚「数接线次数」的覆盖口径，今天量得出它看不见 PG 那一支被摘。

    这里不改动任何东西，只把 ``search()`` 源码里的接线次数现数一遍：五条腿在接 ⇒ 计数 5，
    而在册判据写的是 ``>= 4`` ⇒ 摘掉任何一支都照样过。
    """
    import inspect

    from app.rag import retriever as rt

    source = inspect.getsource(rt.DocumentRetriever.search)
    count = source.count("self._apply_activity_prior(")
    assert count == 5, "腿数变了：本件与那枚在册覆盖的口径都要跟着改（现在是 " + str(count) + "）"
    assert count - 1 >= 4, "摘掉 PGVector 那一支之后，在册那枚 >=4 判据仍然成立 ⇒ 它对该支全盲"
