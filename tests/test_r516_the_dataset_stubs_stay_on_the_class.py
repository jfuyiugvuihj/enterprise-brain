# -*- coding: utf-8 -*-
r"""R516 · 实例桩影子债第二批：`dataset_registry` 一族 8 枚 + `upsert` 打在实例上 3 枚改到类目标。

## 这单治什么

R508 第一轮治掉 `bind` 那三枚之后，在同一张账（`docs/testing/r508-instance-shadow-debt-2026-09-29.md`）
里留下两类同族形状：名册 §3 结论 2 的三枚 `upsert`（名字已经在契约集合里）与结论 3 点名的八枚
`dataset_registry`（目标是 app 模块级单例，与 R499 那一炸同形）。本单照 R508 的既有做法把桩从**实例**
改到**类**：断言一字未动、枚数未增未减（逐枚改前改后各单跑一次，见下面「09-29 现取的读数」）。

| # | 件:行（基点 `85572c1`） | 改前目标 | 改后目标 | 属性名 |
| --- | --- | --- | --- | --- |
| 1 | `tests/test_r112_prompt_packing.py:587` | `dataset_storage.dataset_registry` | `dataset_storage.DatasetRegistry` | `get_active_by_filename` |
| 2 | `tests/test_r112_prompt_packing.py:1105` | 同上 | 同上 | 同上 |
| 3 | `tests/test_r122_stub_honesty.py:269` | 同上 | 同上 | 同上 |
| 4 | `tests/test_r185_text_columns_single_path.py:69` | 同上 | 同上 | 同上 |
| 5 | `tests/test_r189_label_column_from_query.py:80` | 同上 | 同上 | 同上 |
| 6 | `tests/test_r342_trend_undated_exit.py:175` | `data.dataset_registry` | `"app.storage.datasets.DatasetRegistry.active_records"` | `active_records` |
| 7 | `tests/test_r451_open_section_header.py:141` | `dataset_storage.dataset_registry` | `dataset_storage.DatasetRegistry` | `get_active_by_filename` |
| 8 | `tests/test_r462_query_data_tuple_keys.py:70` | 同上 | 同上 | 同上 |
| 9 | `tests/test_r103_graph_unconfigured_exit.py:126` | `graph._store` | `JsonPersistenceAdapter` | `upsert` |
| 10 | `tests/test_r103_graph_unconfigured_exit.py:256` | `store` | `JsonPersistenceAdapter` | `upsert` |
| 11 | `tests/test_r106_open_platform_unconfigured_exit.py:115` | `store` | `JsonPersistenceAdapter` | `upsert` |
| 12 | `tests/test_r192_ranking_count_and_empty_numeric.py:391`（**本单新增第 12 枚**，理由见下） | `dataset_storage.dataset_registry` | `dataset_storage.DatasetRegistry` | `get_active_by_filename` |

第 12 枚不在 R508 名册上，是**运行期那格审计量出来的**：`tests/test_r192_...py:386` 那枚
`install(owner, name, value)` 用裸 `setattr` 装桩、又用 `setattr(owner, name, getattr(owner, name))`
还原，所以 teardown 之后进程级 `dataset_registry.__dict__` 里永久多出一枚绑定方法影子。静态尺子看不
见它（既不是 `monkeypatch.setattr` 也不是属性赋值表达式），而 09-29 现取的探针读数里它确实漏
（`vars(dataset_registry)` 多出 `get_active_by_filename`）。它不修，本单那八枚改到类上就是**假绿**：
r192 排在同一枚 worker 里跑过之后，那份实例影子会遮蔽类级桩，`get_active_by_filename` 读回真方法。

## 在册静态格怎么拦的、走的哪条出路

`tests/test_r508_the_bind_stub_stays_on_the_class.py` 里那格
`test_no_test_file_patches_a_class_patched_contract_onto_a_module_singleton` 的判据是「凡已打在 app 类上
的名字，不许再打在 app 模块级单例上」。本单只要把**任何一枚**改到类上，`get_active_by_filename` 立刻
进契约名集合，剩下打在 `dataset_registry` 上的桩当场全红——09-29 现取：只把
`tests/test_r122_stub_honesty.py` 一枚退回基点写法，那格就红着点名其余七枚。它给的出路只有一条：
**改到类目标**。本单把十一枚一起改完，那格重新绿（本件
`test_the_registered_grid_is_green_on_the_tree_it_punishes` 现跑它两格判据**本体**自证，不复制断言）。
同件那格冻结账 `KNOWN_LOCAL_DEBTS` 在册的是「`upsert` 打在测试局部对象上的
三枚」，本单把三枚一起治干净，所以那张账按事实清空——**只清账不摘牙**：`fresh = seen - 账` 与
`seen == 账` 两格都还在，账空了以后任何一枚新的同族形状进来照样红，比原来严（原来容两枚在册）。

## 本件交的三样

1. **静态全仓扫描（收紧过的尺子）**：`tests/**.py` 里所有能把桩装上去的写法——
   `X.setattr(obj, "name", v)` / `X.setattr("mod.Cls.attr", v)` / `patch("mod.Cls.attr", v)` /
   `patch.object(obj, "name", v)` / `obj.attr = v`——目标解析成 app 模块级单例（含裸名与
   `X.fn()` 两格，R508 §4 的盲区）且属性名确实是那枚类的方法 ⇒ 记一枚。交回的数：
   基点 `85572c1` **28 枚**（`singleton` 27 + `X.fn()` 现取形 1）→ 本单治后 **19 枚**（18 + 1）：
   本单这一族落在非类目标上的一共 **12 枚**（名册 11 + r192），其中 9 枚原本被这格数进单例账
   （8 枚 `dataset_registry` + r192 那枚助手函数裸 `setattr`），另 3 枚 `upsert` 的目标
   （`graph._store` / `store`）在这把尺子上解析不出来、本来就不在单例账里——账目分开记，不是一句
   「治了 12 枚」糊过去。逐枚点名在 `SINGLETON_METHOD_STUB_ROSTER`，基数由 R516 交付里那条
   `git show 85572c1:<path>` 全仓重扫脚本现取（不是拿 R508 那把旧尺子的 2210 改的）。
2. **运行期审计**：把名册那一族所在的 11 枚件（含 `test_r80`：`upsert` 的类级契约就长在它身上）
   在**同一枚子进程**里按盘上的字整跑一遍；探针在每枚用例 teardown 之后读被盯对象的 `__dict__`，
   凡是类上本来就有的名字多出来就是漏，并按文件名归账（不赌 pytest 的次序）。正控**不落临时文件**
   ——09-29 实测：把正控放到仓库外，内层会话的 rootdir 跟着落出去，`conftest.py` 那套 Chroma 改道
   钉一概不装，工作树里被跟踪的 `chroma_db/chroma.sqlite3` 就地写脏、R134 闸门当场指名本件。改由探针
   在收尾**现装两枚影子**（一枚进程级共享单例、一枚一次性实例）：量不到 2/2 就是这格腿空转。
   交回的读数：正控 2/2，且共享单例那枚同时被**真名**那格监视器看见（`real_watched_it_too`：两格
   监视器不通气就红），本单这一族漏 **0** 枚。这腿今天交前炸过两回，两回都是**审计腿自己红**、不是被
   审计的件红——腿不许把自己的毛病读成「零枚漏点」：①`__import__("app.storage.datasets")` 交回的是
   **头**那一枚包而不是叶子模块，身份复核在收尾钩子里抛 `AttributeError` ⇒ 内层会话 rc=1、审计读不到
   数（改走 `importlib.import_module`）；②正控装在共享单例上，同一枚影子被真名那格也报了一次 ⇒ 读数
   从 2 枚变 3 枚（分开记账，并把「真名那格也看见了」升成一枚判据）。
3. **反证刀两把**：①把四枚代表件（`r112:587` 单例名 / `r342:175` 两参点分串 / `r192:391` 助手函数
   裸 `setattr` / `r106:115` 目标解析不出来的 `store`）里任意一枚退回实例桩 ⇒ 本件静态腿当场点名它；
   R508 那两格谁红逐枚记在 `SITES.tooth`，不是一句「当场红」糊过去的：`r112` 让单例格红、`r106` 让
   冻结账红，而 `r342`/`r192` 那两形在册两格照旧绿——只有本单收紧后的腿咬得住（如实记，不给尺子贴金）。
   红句原文随窗交回；
   ②**摘掉运行期那格腿**（把重放清单改成空）⇒ 在册那格 `test_the_runtime_leg_measured_what_it_claims`
   当场红（它钉的是「量过什么」，不是「报了几枚」）。变异只落 `tests/_temp_edit_overlay.py` 那台影子根，
   盘上的被跟踪文件全程只读，出门逐枚核对 sha16 报 `restored=True`。

## 09-29 现取的读数（逐枚单跑，探针读 `vars(app.storage.datasets.dataset_registry)`）

| 件 | 改前单跑 | 改前 `vars()` 多出 | 改后单跑 | 改后 `vars()` 多出 |
| --- | --- | --- | --- | --- |
| `test_r112_prompt_packing.py` | 75 passed | `get_active_by_filename` 🔴 | 75 passed | 无 |
| `test_r122_stub_honesty.py` | 7 passed | `get_active_by_filename` 🔴 | 7 passed | 无 |
| `test_r185_text_columns_single_path.py` | 12 passed | `get_active_by_filename` 🔴 | 12 passed | 无 |
| `test_r189_label_column_from_query.py` | 12 passed | `get_active_by_filename` 🔴 | 12 passed | 无 |
| `test_r342_trend_undated_exit.py` | 25 passed | 无（`data.dataset_registry` 被本件夹具换成 tmp 实例，影子出不了本件） | 25 passed | 无 |
| `test_r451_open_section_header.py` | 11 passed | `get_active_by_filename` 🔴 | 11 passed | 无 |
| `test_r462_query_data_tuple_keys.py` | 6 passed | `get_active_by_filename` 🔴 | 6 passed | 无 |
| `test_r192_ranking_count_and_empty_numeric.py` | 16 passed | `get_active_by_filename` 🔴（静态尺子看不见的那一枚） | 16 passed | 无 |
| `test_r103_graph_unconfigured_exit.py` | 8 passed | 影子落在 `_STORE["store"]` 那一枚，收尾 `configure_app_store("")` 重造 store 才没外溢（运气，不是设计） | 8 passed | 无 |
| `test_r106_open_platform_unconfigured_exit.py` | 7 passed | 同上 | 7 passed | 无 |

全程离线：子进程里跑的仍是各件自己那套进程内 TestClient；零起服务、零模型、零库写、不 commit。
"""
from __future__ import annotations

import ast
import contextlib
import functools
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest

from tests import _temp_edit_overlay as overlay

REPO = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO / "tests"
APP_DIR = REPO / "app"
THIS_FILE = TESTS_DIR / "test_r516_the_dataset_stubs_stay_on_the_class.py"
GRID_FILE = TESTS_DIR / "test_r508_the_bind_stub_stays_on_the_class.py"

#: 改前一律从这枚基点取，不许拿 `HEAD` 当改前；下面那格用 `merge-base --is-ancestor` 自证。
BASE_SHA = "85572c1"

FAMILY_RED = "本单治的这一族桩，一枚也不许再打在实例上"
LEDGER_RED = "进程级单例上的方法桩名册过期了（治法：改到类目标，参照 SITES 那十二行）"
RUNTIME_RED = "跑完这一族所在的件之后，进程级单例上不许留任何一枚方法影子"
LEG_RED = "运行期审计腿没有量它声称量过的东西"
GRID_RED = "在册静态格（R508）没有跟着本单一起变绿"

IMPL_IMPORT = "    from app.storage.persistence import JsonPersistenceAdapter"
PYTEST_MIN_TESTS = 195

# ------------------------------------------------------------------ 名册：十二枚落点

Site = __import__("collections").namedtuple("Site", "key rel attr lineno base now tooth tail")

_OLD_LOOKUP = '    monkeypatch.setattr(dataset_storage.dataset_registry, "get_active_by_filename", lambda filename: None)'
_NEW_LOOKUP = '    monkeypatch.setattr(dataset_storage.DatasetRegistry, "get_active_by_filename", lambda self, filename: None)'
_OLD_INSTALL = '    install(dataset_storage.dataset_registry, "get_active_by_filename", lambda filename: None)'
_NEW_INSTALL = '    install(dataset_storage.DatasetRegistry, "get_active_by_filename", lambda self, filename: None)'
_OLD_TREND = ("    monkeypatch.setattr(",
              '        data.dataset_registry, "active_records",',
              "        lambda: [")
_NEW_TREND = ("    monkeypatch.setattr(",
              '        "app.storage.datasets.DatasetRegistry.active_records",',
              "        lambda self: [")
_OLD_GRAPH_STORE = '    monkeypatch.setattr(graph._store, "upsert", fail_upsert)'
_OLD_STORE = '    monkeypatch.setattr(store, "upsert", fail_upsert)'
_NEW_STORE = '    monkeypatch.setattr(JsonPersistenceAdapter, "upsert", fail_upsert)'
#: 消歧用的下一行原文（同名改动在一枚件里落了两枚时，刀才切得准）。
_TAIL_IF_STUB = "    if stub_dataset_evidence:"
_TAIL_LOAD_FRAMES = '    monkeypatch.setattr(excel, "load_excel", lambda path: frames[path])'
_TAIL_RETURN_GRAPH = "    return graph"
_TAIL_TRY = "    try:"
_TAIL_RETURN_REGISTRY = "    return registry"

#: `tooth` = 把这枚退回实例桩之后，**R508 在册那两格**里该红的那一格；`mine` = 那两格照样绿
#: （名字退出契约集合，或那把尺子根本不认这种写法），只有本单收紧之后的静态腿咬得住。
#: `tail` = 消歧用的下一行：同名改动在一枚件里落了两枚时（r112 的两枚、r103 的两枚），刀才切得准。
SITES = (
    Site("r112:587", "tests/test_r112_prompt_packing.py", "get_active_by_filename", 587,
         (_OLD_LOOKUP,), (_NEW_LOOKUP,), "singleton", _TAIL_IF_STUB),
    Site("r112:1105", "tests/test_r112_prompt_packing.py", "get_active_by_filename", 1105,
         (_OLD_LOOKUP,), (_NEW_LOOKUP,), "singleton", _TAIL_LOAD_FRAMES),
    Site("r122:269", "tests/test_r122_stub_honesty.py", "get_active_by_filename", 269,
         (_OLD_LOOKUP,), (_NEW_LOOKUP,), "singleton", ""),
    Site("r185:69", "tests/test_r185_text_columns_single_path.py", "get_active_by_filename", 69,
         (_OLD_LOOKUP,), (_NEW_LOOKUP,), "singleton", ""),
    Site("r189:80", "tests/test_r189_label_column_from_query.py", "get_active_by_filename", 80,
         (_OLD_LOOKUP,), (_NEW_LOOKUP,), "singleton", ""),
    Site("r342:175", "tests/test_r342_trend_undated_exit.py", "active_records", 175,
         _OLD_TREND, _NEW_TREND, "mine", ""),
    Site("r451:141", "tests/test_r451_open_section_header.py", "get_active_by_filename", 141,
         (_OLD_LOOKUP,), (_NEW_LOOKUP,), "singleton", ""),
    Site("r462:70", "tests/test_r462_query_data_tuple_keys.py", "get_active_by_filename", 70,
         (_OLD_LOOKUP,), (_NEW_LOOKUP,), "singleton", ""),
    Site("r192:391", "tests/test_r192_ranking_count_and_empty_numeric.py", "get_active_by_filename", 391,
         (_OLD_INSTALL,), (_NEW_INSTALL,), "mine", ""),
    Site("r103:126", "tests/test_r103_graph_unconfigured_exit.py", "upsert", 126,
         (_OLD_GRAPH_STORE,), (_NEW_STORE,), "local", _TAIL_RETURN_GRAPH),
    Site("r103:256", "tests/test_r103_graph_unconfigured_exit.py", "upsert", 256,
         (_OLD_STORE,), (_NEW_STORE,), "local", _TAIL_TRY),
    Site("r106:115", "tests/test_r106_open_platform_unconfigured_exit.py", "upsert", 115,
         (_OLD_STORE,), (_NEW_STORE,), "local", _TAIL_RETURN_REGISTRY),
)

#: 本单治的名字：全部由 SITES 派生，不写死名单。
FAMILY = frozenset(site.attr for site in SITES)

#: 运行期那格在同一枚子进程里整跑的件：十二枚落点所在的十枚 + `test_r80`（`upsert` 的类级契约就
#: 长在它身上，两族桩必须能在同一枚进程里共处）。正控由 `_nested_audit` 现造，排最后跑。
REPLAY_FILES = (
    "tests/test_r112_prompt_packing.py",
    "tests/test_r122_stub_honesty.py",
    "tests/test_r185_text_columns_single_path.py",
    "tests/test_r189_label_column_from_query.py",
    "tests/test_r342_trend_undated_exit.py",
    "tests/test_r451_open_section_header.py",
    "tests/test_r462_query_data_tuple_keys.py",
    "tests/test_r192_ranking_count_and_empty_numeric.py",
    "tests/test_r103_graph_unconfigured_exit.py",
    "tests/test_r106_open_platform_unconfigured_exit.py",
    "tests/test_r80_app_identity_collision.py",
)

#: 反证刀①的代表件：四种形状各一枚（单例名 + 已在契约集合 / 点分串 + 名字唯一一枚类级桩 /
#: 助手函数裸 `setattr` 那形 / 目标解析不出来的 `store`）。其余八枚与代表件同字同形，
#: 由 `test_the_base_lines_...` 与静态腿逐枚钉住，不重复开窗。
KNIFE_SITES = ("r112:587", "r342:175", "r192:391", "r106:115")

#: 收紧尺子在全仓量到的「打在进程级单例上的方法桩」：基点 `85572c1` 28 枚 -> 本单治后 19 枚
#: （28 = `singleton` 27 + `singleton-call` 1；本单从这张账里划掉 9 枚，见上面 §1 那一段）。
#: 键 = (件, 目标原文, 属性名)，含重复（同一枚件里同形多枚），不按行号钉：别人在这些件里加删行
#: 不至于把这张账撑成假红，而等号那一半又保证账不许偷偷变短。
SINGLETON_METHOD_STUB_ROSTER = (
    ("tests/test_document_delete_catalog.py", "chat.retriever", "delete_document"),
    ("tests/test_document_delete_catalog.py", "chat.retriever", "delete_document"),
    ("tests/test_document_delete_catalog.py", "chat.retriever", "delete_document"),
    ("tests/test_document_delete_catalog.py", "chat.retriever", "delete_document"),
    ("tests/test_document_ownership.py", "chat.retriever", "delete_document"),
    ("tests/test_private_model_routing.py", "retrieval_pipeline.model", "chat"),
    ("tests/test_r109_rewrite_offline_guard.py", "chat.model_handler", "chat"),
    ("tests/test_r109_rewrite_offline_guard.py", "chat.model_handler", "chat"),
    ("tests/test_r126_rewrite_prev_turn.py", "chat.model_handler", "chat"),
    ("tests/test_r126_rewrite_prev_turn.py", "chat.model_handler", "chat"),
    ("tests/test_r141_lane_behavior.py", "chat.model_handler", "chat"),
    ("tests/test_r141_lane_behavior.py", "chat.model_handler", "chat"),
    ("tests/test_r172_lane_across_hitl.py", "chat.model_handler", "chat"),
    ("tests/test_r194_queue_denials_and_flat_list.py", "chat.retriever", "list_documents"),
    ("tests/test_r194_queue_denials_and_flat_list.py", "chat.retriever", "list_documents"),
    ("tests/test_r200_restricted_single_source.py", "chat.retriever", "list_documents"),
    ("tests/test_r32_lane_contract.py", "chat.model_handler", "chat"),
    ("tests/test_r51_observation_is_passive.py", "stage_timing.default_stage_ledger()", "report"),
    ("tests/test_response_hygiene.py", "intelligence._graph", "add_relation"),
)

# ------------------------------------------------------------------ 静态腿：收紧过的全仓尺子

Row = __import__("collections").namedtuple("Row", "rel lineno form target attr kind cls")

#: 认「把桩装上去」的写法；`raw-assign`（`obj.attr = value`）是手工还原的埋点形，另算一格，
#: 由运行期那腿负责（r310/r337/r354 拿它包装自己那枚一次性 registry，不该混进桩的账）。
_STUB_FORMS = ("setattr", "setattr-dotted", "patch-dotted", "patch-object", "three-arg-call")


@functools.lru_cache(maxsize=1)
def _app_shape():
    """三张派生表，全从 `app/**` 源码读、零导入：类名->方法名；模块级单例名->类名；函数名->它 return 的单例名。

    与 R508 那把尺子的三处差别都是**加严**（正是纸上 §4 邀请下一单收紧的那两格 + 一枚同类）：

    * 类表跨模块建：R508 只认「同一文件里定义的类」，所以 `chat.retriever = DocumentRetriever()`
      这一族在它眼里是 `local`，在这里是 `singleton`；
    * 裸名单例（`setattr(dataset_registry, "chat", ...)`）算单例，R508 判成 `module`；
    * `X.fn()` 顺着 return 追一层（`stage_timing.default_stage_ledger()`），R508 判成 `local`。
    """
    trees = {path: ast.parse(path.read_text(encoding="utf-8")) for path in sorted(APP_DIR.rglob("*.py"))}
    classes: dict = {}
    singletons: dict = {}
    returns: dict = {}
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.setdefault(node.name, set()).update(
                    child.name for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)))
    for tree in trees.values():
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                func = node.value.func
                cname = (func.id if isinstance(func, ast.Name)
                         else (func.attr if isinstance(func, ast.Attribute) else ""))
                if cname in classes:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            singletons.setdefault(target.id, cname)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names = {ret.value.id for ret in ast.walk(node)
                         if isinstance(ret, ast.Return) and isinstance(ret.value, ast.Name)}
                if names:
                    returns.setdefault(node.name, set()).update(names)
    return classes, singletons, returns


def _classify(target: str) -> tuple:
    classes, singletons, returns = _app_shape()
    parts = target.split(".")
    last = parts[-1]
    if last.endswith("()"):
        hit = sorted(returns.get(last[:-2], set()) & set(singletons))
        return ("singleton-call", singletons[hit[0]]) if hit else ("other", "")
    if last in classes:
        return ("class", last)
    if last in singletons:
        return ("singleton-bare" if len(parts) == 1 else "singleton", singletons[last])
    return ("other", "")


def _rows(rel: str, text: str) -> tuple:
    """一份字节里所有认得出的装桩写法（不做筛选，判据在调用方那一格）。

    认五种形：`X.setattr(obj, "n", v)` / `X.setattr("mod.Cls.n", v)` / `patch("mod.Cls.n", v)` /
    `patch.object(obj, "n", v)` / `obj.n = v`；再加一枚**通用形**：任何三参调用 `f(obj, "n", v)`
    ——r192 那件自己的 `install(owner, name, value)` 就走这条路，R508 的尺子根本不认这种写法。
    """
    out: list = []

    def emit(lineno, form, target, attr):
        target = target.strip()
        kind, cls = _classify(target)
        out.append(Row(rel, lineno, form, target, attr, kind, cls))

    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
            if name == "setattr" and node.args:
                head = node.args[0]
                if len(node.args) == 2 and isinstance(head, ast.Constant) and isinstance(head.value, str) \
                        and "." in head.value.strip():
                    dotted, attr = head.value.strip().rsplit(".", 1)
                    emit(node.lineno, "setattr-dotted", dotted, attr)
                elif len(node.args) >= 3 and isinstance(node.args[1], ast.Constant) \
                        and isinstance(node.args[1].value, str):
                    emit(node.lineno, "setattr",
                         (head.value if isinstance(head, ast.Constant) and isinstance(head.value, str)
                          else ast.unparse(head)), node.args[1].value)
            if name == "patch" and node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str) and "." in node.args[0].value.strip():
                dotted, attr = node.args[0].value.strip().rsplit(".", 1)
                emit(node.lineno, "patch-dotted", dotted, attr)
            if name == "object" and len(node.args) >= 3 and isinstance(node.args[1], ast.Constant) \
                    and isinstance(node.args[1].value, str):
                emit(node.lineno, "patch-object", ast.unparse(node.args[0]), node.args[1].value)
            if len(node.args) >= 3 and isinstance(node.args[1], ast.Constant) \
                    and isinstance(node.args[1].value, str):
                emit(node.lineno, "three-arg-call", ast.unparse(node.args[0]), node.args[1].value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, (ast.Name, ast.Attribute)):
                    emit(node.lineno, "raw-assign", ast.unparse(target.value), target.attr)
    dedup: dict = {}
    for row in out:                     # 同一处写法被通用形各认一次，只留一条
        dedup.setdefault((row.rel, row.lineno, row.target, row.attr), row)
    return tuple(dedup.values())


@functools.lru_cache(maxsize=None)
def _rows_in_one_file(rel: str, text: str) -> tuple:
    return _rows(rel, text)


def _all_rows() -> tuple:
    rows: list = []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        try:
            rows.extend(_rows_in_one_file(rel, overlay.authoritative_text(rel)))
        except SyntaxError:             # pragma: no cover - 语法不合法的件本来也跑不起来
            continue
    return tuple(rows)


def _stub_rows(rows=None) -> list:
    rows = _all_rows() if rows is None else rows
    return [row for row in rows if row.form in _STUB_FORMS]


def _family_hits() -> list:
    """本单治的三个名字，还长在非类目标上的每一枚（目标解析不出来也算：`store` 那一族就是解析不出来的）。"""
    return [row for row in _stub_rows() if row.attr in FAMILY and row.kind != "class"]


def _singleton_stub_rows() -> list:
    """目标能确定落在 app 模块级单例上、且属性名确实是那枚类的方法：名册那一格的口径。"""
    classes, _singletons, _returns = _app_shape()
    return [row for row in _stub_rows()
            if row.kind.startswith("singleton") and row.attr in classes.get(row.cls, set())]


# ------------------------------------------------------- 在册那格 R508 判据的把手

def _module_from_text(text: str, path: Path, alias: str):
    """把一份字节装成一枚一次性模块对象：`__file__` 指向真身，报错行列号与盘上同形。"""
    module = types.ModuleType(alias)
    module.__file__ = str(path)
    module.__dict__["__name__"] = alias
    exec(compile(text, str(path), "exec"), module.__dict__)
    return module


def _grid_view():
    """现取在册静态格那一件：窗内读影子副本的变异版，窗外读盘上的字。"""
    rel = GRID_FILE.relative_to(REPO).as_posix()
    return _module_from_text(overlay.authoritative_text(rel), GRID_FILE, "r516_grid_view")


GRID_CELLS = (
    ("singleton", "test_no_test_file_patches_a_class_patched_contract_onto_a_module_singleton"),
    ("local", "test_the_local_instance_stub_ledger_has_no_second_entry"),
)


def _grid_verdicts() -> dict:
    """现跑 R508 那两格判据**本体**（不复制断言）：绿的交回 None，红的交回那枚 AssertionError。"""
    grid = _grid_view()
    verdicts: dict = {}
    for key, cell in GRID_CELLS:
        try:
            getattr(grid, cell)()
        except AssertionError as caught:
            verdicts[key] = caught
        else:
            verdicts[key] = None
    return verdicts

# ------------------------------------------------- 运行期腿：一枚子进程里整跑这一族

PROBE_SOURCE = """
import importlib
import json
import os
import tempfile
from pathlib import Path

import pytest

MODULES = {}
EVENTS = []
WATCH = []
CREATED = []
SEEN = {}
RUN = {}
SELF_TEST = {"planted": [], "caught": [], "error": ""}


def shadow_names(obj):
    owned = set()
    for base in type(obj).__mro__:
        owned.update(vars(base))
    return sorted((set(vars(obj)) & owned) - {"__init__"})


def attr_getter(obj):
    return lambda: [obj]


def module_attr(label, name):
    def getter():
        return [getattr(MODULES[label], name, None)]
    return getter


def graph_getter(which):
    def getter():
        graph = getattr(MODULES["intelligence"], "_graph", None)
        if graph is None:
            return []
        return [graph._store] if which == "store" else [graph]
    return getter


def open_platform_getter():
    store = MODULES["open_platform"]._STORE.get("store")
    return [store] if store is not None else []


def created_getter():
    return list(CREATED)


def check(where, filename):
    RUN[filename] = RUN.get(filename, 0) + 1
    for label, getter in WATCH:
        try:
            objects = [obj for obj in getter() if obj is not None]
        except Exception:
            continue
        for obj in objects:
            key = (label, id(obj))
            names = set(shadow_names(obj))
            known = SEEN.setdefault(key, set())
            for name in sorted(names - known):
                EVENTS.append({"file": filename, "where": where, "object": label,
                               "cls": type(obj).__name__, "shadow": name})
            known |= names


def self_test():
    \"\"\"正控：现装一枚影子进去，尺子必须当场量到——量不到就是这格腿空转了。

    两枚对象各装一次：进程级共享单例（本单那一族真正的落点）与一枚一次性实例（证明逐对象的
    delta 追踪不是一枚全局计数器）。装完立刻单独 `check` 一次，事件记在 `<self-test>` 名下，
    不混进任何一枚件的读数里。
    \"\"\"
    from app.storage import datasets as ds

    objects = [("dataset_registry", ds.dataset_registry)]
    try:
        root = Path(tempfile.mkdtemp(prefix="r516-selftest-"))
        objects.append(("scratch_registry", ds.DatasetRegistry(
            root=root, metadata_path=root / ".dataset-metadata.json",
            store=ds.InMemoryDatasetTableStore())))
    except Exception as exc:                       # 造不出来也要如实记下，不许静默少一枚
        SELF_TEST["error"] = "%s: %r" % (type(exc).__name__, exc)
    for label, obj in objects:
        WATCH.append((label + "-selftest", attr_getter(obj)))
        obj.get_active_by_filename = lambda *args, **kwargs: None
        SELF_TEST["planted"].append([label + "-selftest", "get_active_by_filename"])
    check("self-test", "<self-test>")
    seen_events = [[event["object"], event["shadow"]] for event in EVENTS
                   if event["file"] == "<self-test>"]
    SELF_TEST["caught"] = [row for row in seen_events if row[0].endswith("-selftest")]
    # 同一枚进程级共享单例同时挂在真名那格监视器上：两格都看见，才说明这不是枚全局计数器。
    SELF_TEST["real_watched_it_too"] = (
        ["dataset_registry", "get_active_by_filename"] in seen_events)


def pytest_configure(config):
    for label, module_name in (("datasets", "app.storage.datasets"),
                               ("sessions", "app.storage.sessions"),
                               ("chat", "app.api.v1.chat"),
                               ("pipeline", "app.rag.retrieval_pipeline"),
                               ("stage_timing", "app.common.stage_timing"),
                               ("intelligence", "app.api.v1.intelligence"),
                               ("open_platform", "app.common.open_platform"),
                               ("persistence", "app.storage.persistence")):
        MODULES[label] = __import__(module_name, fromlist=["__name__"])

    WATCH.append(("dataset_registry", module_attr("datasets", "dataset_registry")))
    WATCH.append(("session_registry", module_attr("sessions", "session_registry")))
    WATCH.append(("chat_model_handler", module_attr("chat", "model_handler")))
    WATCH.append(("chat_retriever", module_attr("chat", "retriever")))
    WATCH.append(("pipeline_model", module_attr("pipeline", "model")))
    WATCH.append(("default_ledger", module_attr("stage_timing", "default_ledger")))
    WATCH.append(("intelligence_graph", graph_getter("graph")))
    WATCH.append(("intelligence_store", graph_getter("store")))
    WATCH.append(("open_platform_store", open_platform_getter))
    WATCH.append(("created_adapter", created_getter))

    persistence = MODULES["persistence"]
    original = persistence.JsonPersistenceAdapter.__dict__["__init__"]

    def __init__(self, *args, **kwargs):
        original(self, *args, **kwargs)
        CREATED.append(self)

    persistence.JsonPersistenceAdapter.__init__ = __init__
    check("session-start", "<startup>")


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item):
    check(item.name, Path(str(item.fspath)).name)


def pytest_sessionfinish(session, exitstatus):
    try:
        self_test()
    except Exception as exc:                        # 正控自己炸了也要交回原文，不许静默
        SELF_TEST["error"] = "%s: %r" % (type(exc).__name__, exc)
    check("session-finish", "<session-finish>")
    target = os.environ.get("R516_AUDIT_JSON")
    if target:
        Path(target).write_text(json.dumps({"events": EVENTS, "run": RUN,
                                           "adapters": len(CREATED),
                                           "watched": sorted({label for label, _ in WATCH}),
                                           "self_test": SELF_TEST,
                                            # 身份复核必须走 `importlib.import_module`：`__import__("app.storage.datasets")`
                                            # 交回的是**头**那一枚包（`app`）而不是叶子模块，没有这一行就没有身份复核。
                                            "identity_ok": MODULES["datasets"].dataset_registry
                                            is importlib.import_module("app.storage.datasets").dataset_registry,
                                           "exitstatus": str(exitstatus)}, ensure_ascii=False),
                                encoding="utf-8")
"""


@functools.lru_cache(maxsize=1)
def _nested_audit():
    """把 `REPLAY_FILES` 整跑在一枚子进程里：探针读身份（`vars()`），不读文本，也不赌次序。

    目标一律是仓内的被跟踪件——正控不放成临时文件（那会让内层会话的 rootdir 落到仓库外，
    `tests/conftest.py` 与仓库根 conftest 的 Chroma 改道钉一概不装，工作树里被跟踪的
    `chroma_db/chroma.sqlite3` 就地写脏：09-29 实测过，R134 闸门当场指名本件的摘腿那一枚用例）。
    清单被摘空时兜底跑本件自己那一枚纯断言用例：内层会话照样得绿，而「量过什么」那格必须红。
    """
    targets = [str(REPO / rel) for rel in REPLAY_FILES] or [
        "%s::test_the_roster_names_twelve_sites_and_the_family_derives_three_names" % THIS_FILE]
    workdir = Path(tempfile.mkdtemp(prefix="r516-audit-"))
    plugin_dir = workdir / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "r516_shadow_probe.py").write_text(PROBE_SOURCE, encoding="utf-8")
    audit_json = workdir / "audit.json"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(plugin_dir)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    env["R516_AUDIT_JSON"] = str(audit_json)
    for noisy in ("PYTEST_CURRENT_TEST", "PYTEST_XDIST_WORKER", "PYTEST_XDIST_TESTRUNUID"):
        env.pop(noisy, None)
    command = [sys.executable, "-m", "pytest", *targets,
               "-q", "--no-header", "-p", "r516_shadow_probe", "-p", "no:cacheprovider"]
    proc = subprocess.run(command, cwd=str(REPO), env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=2400)
    assert proc.returncode == 0, (
        "整跑这一族所在的件就没绿，审计腿不能在这种情况下报零：\n"
        "---- 内层 stdout 尾 ----\n%s\n---- 内层 stderr 尾 ----\n%s" % (
            (proc.stdout or "")[-1500:], (proc.stderr or "")[-2500:]))
    report = json.loads(audit_json.read_text(encoding="utf-8"))
    report["replay_names"] = tuple(Path(rel).name for rel in REPLAY_FILES)
    report["workdir"] = str(workdir)
    return report


def _leaks(report: dict) -> list:
    """探针量到的、落在这十枚件里、且属本单这一族名字的影子漏点（正控那枚记在 `<self-test>` 名下）。"""
    return [event for event in report["events"]
            if event["file"] in report["replay_names"] and event["shadow"] in FAMILY]

# ---------------------------------------------------------------------------- 判据

def test_the_roster_names_twelve_sites_and_the_family_derives_three_names():
    """名册自证：8 枚 `dataset_registry` + 3 枚 `upsert` = R508 纸上点名的十一枚，第 12 枚是本单量出来的。"""
    assert len(SITES) == 12, "落点枚数变了：本单的账要一起改"
    assert FAMILY == frozenset({"get_active_by_filename", "active_records", "upsert"}), FAMILY
    assert sum(1 for site in SITES if site.attr == "get_active_by_filename") == 8
    assert sum(1 for site in SITES if site.attr == "active_records") == 1
    assert sum(1 for site in SITES if site.attr == "upsert") == 3
    assert {site.rel for site in SITES} == {rel for rel in REPLAY_FILES if "test_r80" not in rel}, (
        "重放清单与落点清单对不上")
    assert set(KNIFE_SITES) <= {site.key for site in SITES}
    assert len(SINGLETON_METHOD_STUB_ROSTER) == 19, SINGLETON_METHOD_STUB_ROSTER


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                         text=True, encoding="utf-8")
    assert out.returncode == 0, "git %s rc=%s：%s" % (" ".join(args), out.returncode, out.stderr)
    return out.stdout


def test_the_base_lines_are_the_ones_the_roster_names():
    """逐枚自证：改前那一行确实长在基点的那一行上，盘上已换成类目标，且换的只有目标与多收一枚 `self`。"""
    _git("merge-base", "--is-ancestor", BASE_SHA, "HEAD")
    for site in SITES:
        base_lines = _git("show", "%s:%s" % (BASE_SHA, site.rel)).replace("\r\n", "\n").split("\n")
        assert base_lines[site.lineno - 1].strip() == site.base[0].strip(), (
            "%s 在基点 %s 的第 %d 行不是名册那一枚：%r" % (
                site.rel, BASE_SHA, site.lineno, base_lines[site.lineno - 1]))
        disk = overlay.authoritative_text(site.rel).replace("\r\n", "\n")
        joined_base = "\n".join(site.base)
        joined_now = "\n".join(site.now)
        assert joined_base not in disk, "%s 盘上还留着实例桩那一行：%r" % (site.rel, site.base[0])
        assert joined_now in disk, "%s 盘上没有声称的改后原文：%r" % (site.rel, joined_now)
        assert site.attr in joined_now, (site.key, joined_now)
    from app.storage import datasets

    assert callable(datasets.DatasetRegistry.get_active_by_filename)
    assert callable(datasets.DatasetRegistry.active_records)
    from app.storage.persistence import JsonPersistenceAdapter

    assert callable(JsonPersistenceAdapter.upsert)


def test_the_ticket_added_no_duplicated_import():
    """本单给三处补的 `JsonPersistenceAdapter` 导入：一枚落点配一枚，多一枚就是复制粘贴事故。"""
    tally: dict = {}
    for site in SITES:
        if site.attr == "upsert":
            tally[site.rel] = tally.get(site.rel, 0) + 1
    assert tally == {"tests/test_r103_graph_unconfigured_exit.py": 2,
                     "tests/test_r106_open_platform_unconfigured_exit.py": 1}, tally
    for rel, want in tally.items():
        lines = overlay.authoritative_text(rel).replace("\r\n", "\n").split("\n")
        got = sum(1 for line in lines if line == IMPL_IMPORT)
        assert got == want, "%s 里那枚导入出现 %d 次（要 %d 次）" % (rel, got, want)


def test_no_family_stub_hits_an_instance_any_more():
    """静态那半枚牙：本单治的三个名字，一枚也不许再打在非类目标上（目标解析不出来照样算）。"""
    hits = _family_hits()
    assert not hits, FAMILY_RED + "：\n" + "\n".join(
        "%s:%s %s target=%s attr=%s kind=%s" % (row.rel, row.lineno, row.form, row.target,
                                                row.attr, row.kind) for row in hits)


def test_the_singleton_ledger_is_the_one_this_ticket_measured():
    """全仓量出来交回名册的那格：进程级单例上的方法桩，基点 28 枚 -> 本单治后 19 枚，逐枚点名。

    这一格不判零：剩下那 19 枚属别的族（`chat.retriever` / `chat.model_handler` /
    `retrieval_pipeline.model` / `stage_timing.default_stage_ledger()` / `intelligence._graph`），
    写域不在本单。它判的是**账不许漂**：多一枚当场红，少一枚也当场红——治干净了就把它从账里划掉。
    """
    seen = sorted((row.rel, row.target, row.attr) for row in _singleton_stub_rows())
    expected = sorted(SINGLETON_METHOD_STUB_ROSTER)
    fresh = sorted(set(seen) - set(expected))
    assert not fresh, LEDGER_RED + "：" + repr(fresh)
    assert seen == expected, "名册对不上，纸上的账过期了：现读 %d 枚 / 在册 %d 枚\n%s" % (
        len(seen), len(expected), "\n".join(seen))
    assert not [row for row in _singleton_stub_rows() if row.attr in FAMILY], (
        FAMILY_RED + "（这一族还留在名册里）")
    print("[r516] 进程级单例上的方法桩：现读 %d 枚（基点 85572c1 现扫 28 枚，本单划掉 9 枚），"
          "其中本单这一族 0 枚" % len(seen))

# --------------------------------------------------------------- 运行期那格（子进程整跑）

def test_the_replayed_files_leave_no_method_shadow_on_the_shared_singletons():
    """名册那一族所在的件整跑在一枚子进程里，teardown 之后进程级单例上不许多出任何一枚方法影子。

    量的是身份不是文本：`vars(obj) ∩ 类上本来就有的名字`。正控（那枚故意把桩打在实例上的件）排在
    最后跑，所以它既不遮蔽本单任何一枚类级桩，又单独证明这把尺子还在测量——它的读数由下面那格钉。
    """
    report = _nested_audit()
    leaks = _leaks(report)
    assert not leaks, RUNTIME_RED + "：\n" + "\n".join(
        "%s 跑完 %s 之后 %s(%s) 上多出方法影子 %r" % (
            event["file"], event["where"], event["object"], event["cls"], event["shadow"])
        for event in leaks)
    print("[r516] 整跑 %d 枚件 / %d 枚用例：本族方法影子漏点 %d 枚" % (
        len(report["replay_names"]), sum(report["run"].values()), len(leaks)))


def test_the_runtime_leg_measured_what_it_claims():
    """审计腿不许空转：它必须真跑过名册那些件、真见过临时 store，而正控那一枚必须量到漏。

    这格是第二把刀的靶子——把重放清单摘成空，这格当场红：它钉的是「量过什么」，不是「报了几枚」，
    所以摘腿与谎报 0 都过不去。
    """
    report = _nested_audit()
    assert report["identity_ok"] is True, "%s：探针读的那枚不是模块上的进程级单例" % LEG_RED
    ran = set(report["run"])
    assert ran >= set(report["replay_names"]), (
        LEG_RED + "：重放清单里的件没跑全，缺 " + repr(sorted(set(report["replay_names"]) - ran)))
    executed = sum(count for name, count in report["run"].items() if name in report["replay_names"])
    assert executed >= PYTEST_MIN_TESTS, (
        "%s：这一族只跑了 %d 枚用例（名册上的件合计 %d 枚）" % (LEG_RED, executed, PYTEST_MIN_TESTS))
    self_test = report["self_test"]
    assert self_test["error"] == "", "%s：正控自己就炸了：%s" % (LEG_RED, self_test["error"])
    assert sorted(self_test["caught"]) == sorted(self_test["planted"]) == sorted([
        ["dataset_registry-selftest", "get_active_by_filename"],
        ["scratch_registry-selftest", "get_active_by_filename"]]), (
        "%s：正控装了 %r 枚影子、尺子只量到 %r 枚" % (LEG_RED, self_test["planted"], self_test["caught"]))
    assert self_test["real_watched_it_too"] is True, (
        "%s：正控在进程级共享单例上装了影子，真名那格监视器却没看见——两格不通气" % LEG_RED)
    assert report["adapters"] > 0, (
        "%s：整跑这一族没造出任何一枚 store，说明 store 那格监视器接不上" % LEG_RED)
    assert set(report["watched"]) >= {"dataset_registry", "created_adapter", "open_platform_store"}, (
        "%s：探针盯的对象少了一族：%r" % (LEG_RED, report["watched"]))
    assert report["exitstatus"] == "0", "内层那一跑没绿：审计腿不能在这种情况下读数"
    print("[r516] 审计腿读数：清单 %d 枚件（探针另记 %d 枚伪名字：startup/session-finish/<self-test>）"
        " / 用例 %d 枚 / store %d 枚 / 正控装 %d 量到 %d / 本族漏点 %d 枚" % (
        len(report["replay_names"]), len(ran), executed, report["adapters"],
        len(self_test["planted"]), len(self_test["caught"]), len(_leaks(report))))


def test_the_registered_grid_is_green_on_the_tree_it_punishes():
    """出路走完的自证：R508 在册那两格判据**本体**，在盘上这一版字上必须两格都绿。

    本单不是绕开那枚静态格变绿的：`_grid_verdicts()` 现跑它的两格（不复制断言），读的是
    `tests/_temp_edit_overlay.py` 交回的权威字。谁把哪一枚退回实例桩，这格当场红，刀①同时点名该红的是哪一格。
    """
    verdicts = _grid_verdicts()
    red = {key: str(value).splitlines()[0] for key, value in verdicts.items()
           if value is not None}
    assert not red, "R508 在册那两格在盘上这一版字上还是红的：" + repr(red)
    print("[r516] R508 在册两格（单例格 / 冻结账）现跑读数：全绿")

# ------------------------------------------------------------------ 反证刀两把



def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


class _R516Edit(overlay.ShadowEdit):
    """把一枚落点退回实例桩：锚点命中不是恰好一处就整片不落；变异文本先过 `compile()`。"""

    tag = "r516"
    execs_module = False

    def __init__(self, path, edits) -> None:
        super().__init__(path)
        self.edits = [(tuple(old), tuple(new)) for old, new in edits]

    def mutate(self, text: str) -> str:
        nl = _newline(text)
        mutated = text
        for old, new in self.edits:
            needle = nl.join(old)
            hits = mutated.count(needle)
            assert hits == 1, ("%s 里锚点命中 %d 处（要求恰好 1 处）：%r —— 变异整体不落"
                               % (self.path.name, hits, old[0]))
            mutated = mutated.replace(needle, nl.join(new), 1)
        compile(mutated, str(self.path), "exec")
        return mutated


class _NeuterAuditEdit(overlay.ShadowEdit):
    """第二把刀的变异：把本件那枚重放清单摘成空 tuple，也就是「审计腿不再量名册那些件」。"""

    tag = "r516-leg"
    execs_module = False
    head = "REPLAY_FILES = ("

    def mutate(self, text: str) -> str:
        nl = _newline(text)
        lines = text.split(nl)
        starts = [index for index, line in enumerate(lines) if line == self.head]
        assert len(starts) == 1, "重放清单那格的锚点命中 %d 处（要求恰好 1 处）" % len(starts)
        start = starts[0]
        end = next(index for index in range(start + 1, len(lines)) if lines[index] == ")")
        mutated = nl.join(lines[:start] + ["REPLAY_FILES = ()"] + lines[end + 1:])
        compile(mutated, str(self.path), "exec")
        return mutated


@pytest.mark.parametrize("site_key", KNIFE_SITES)
def test_reverting_a_family_site_to_an_instance_stub_goes_red(site_key):
    """刀①：把代表件退回实例桩 ⇒ 本件的静态腿必须点名它；在册那两格按各枚形状如实分开验。

    四枚代表件覆盖四种形状，读数如实分开：`get_active_by_filename` 那五枚同名的兄弟仍在类上，所以
    退回任意一枚，R508 的单例格当场红；`upsert` 打在 `store` 上的那枚走冻结账那一格；而 `r342`
    （`active_records` 全仓只有这一枚类级桩）与 `r192`（裸 `setattr` 助手，R508 的尺子根本不认这形）
    退回实例桩时**在册那两格照旧绿**——那两枚正是本单把尺子收紧之后才咬得住的，纸上 §4 记的就是它。
    """
    site = next(item for item in SITES if item.key == site_key)
    rel = site.rel
    before = overlay.sha16_of_bytes((REPO / rel).read_bytes())
    tail = (site.tail,) if site.tail else ()
    with _R516Edit(REPO / rel, ((tuple(site.now) + tail, tuple(site.base) + tail),)) as info:
        named = [row for row in _family_hits() if row.rel == rel]
        assert named, "退回实例桩之后本件静态腿没点名 %s：%r" % (rel, _family_hits())
        assert any(row.attr == site.attr for row in named), (site_key, named)
        verdicts = _grid_verdicts()
        if site.tooth == "singleton":
            assert isinstance(verdicts["singleton"], AssertionError), (
                "退回实例桩之后 R508 的单例格还绿：这把刀在空转（%s）" % rel)
        elif site.tooth == "local":
            assert isinstance(verdicts["local"], AssertionError), (
                "退回实例桩之后 R508 的冻结账还绿：这把刀在空转（%s）" % rel)
        else:
            assert all(verdict is None for verdict in verdicts.values()), (
                "%s 这形本该是 R508 那两格的盲区，现在它们红了：账要重记" % rel)
        print("[r516] 反证（%s / tooth=%s）本件点名 %r；在册读数 %s" % (
            site.key, site.tooth, [(row.lineno, row.form, row.kind) for row in named],
            {key: (str(verdict).splitlines()[0] if isinstance(verdict, AssertionError) else verdict)
             for key, verdict in verdicts.items()}))
    assert overlay.sha16_of_bytes((REPO / rel).read_bytes()) == before, "反证窗碰到了真树上的 %s" % rel
    assert info["restored"] is True, "盘上那枚件的字节在窗内被动过"
    assert info["shadow_clean"] is True, "影子副本没回到盘上的字"
    assert not _family_hits(), "刀收干净之后本件静态腿还红"


def test_removing_the_runtime_leg_goes_red():
    """刀②：摘掉运行期审计腿 ⇒ 在册那格「腿量过什么」当场红；腿装回去之后它自己还得绿。"""
    rel = THIS_FILE.relative_to(REPO).as_posix()
    before = overlay.sha16_of_bytes(THIS_FILE.read_bytes())
    with _NeuterAuditEdit(THIS_FILE) as info:
        view = _module_from_text(overlay.authoritative_text(rel), THIS_FILE, "r516_neutered_view")
        try:
            view.test_the_runtime_leg_measured_what_it_claims()
            caught = None
        except AssertionError as exc:
            caught = exc
        assert caught is not None, "摘掉运行期审计腿之后，那格「腿量过什么」还绿：这把刀在空转"
        assert LEG_RED in str(caught), str(caught)
        print("[r516] 摘腿红句原文：%r" % str(caught).splitlines()[0])
    assert overlay.sha16_of_bytes(THIS_FILE.read_bytes()) == before, "反证窗碰到了真树上的本件"
    assert info["restored"] is True and info["shadow_clean"] is True
    test_the_runtime_leg_measured_what_it_claims()
