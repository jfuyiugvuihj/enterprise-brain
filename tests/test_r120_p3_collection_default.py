"""R120 任务 3 的前置：P3 手册里每一条"照做就能跑"的话，都得对得上真源。

`scripts/compare_vector_recall.py` 从落树那天起一行都没在真库上跑过（看板 R58 行），所以它的
**默认值从来没被现实检验过一次**。本班把它拿去写手册，先读了一遍参数，读到两处会当场卡住的：

* ``--collection`` 默认 ``enterprise_brain`` —— 那是 Postgres 的库名（compose 里
  ``POSTGRES_DB:-enterprise_brain``）。Chroma 这边生产在写的集合叫 ``enterprise_docs``
  （``app/rag/retriever.py:484``）。照手册第一步就会死在 ``open_chroma()`` 的"取不到
  collection"上，退出码 2，一个字节的对比结论都不产出。
* PG 侧把内积记成 ``ip``，脚本与 Chroma 记成 ``inner_product``。默认口径 l2 撞不上，但谁一旦
  真用 ip，脚本会报一条假的"[前置不满足] …先核对 0010"，把业主支去改一个没写错的地方。

根因不是这两个名字，是"工具与手册各写各的，没人钉"。所以这里把默认值钉回写入侧、把距离拼法
钉回 0010 的 CHECK 允许集、把手册钉回可复制的命令与前缀，全部只读源码与 argparse 默认值 ——
一条真库都不连，一个 Chroma 目录都不新建。
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "compare_vector_recall.py"
RETRIEVER_PATH = ROOT / "app" / "rag" / "retriever.py"
MIGRATION_0010 = ROOT / "migrations" / "0010_pgvector_chunks.sql"
COMPOSE = ROOT / "docker-compose.yml"
PLAN_DOC = ROOT / "docs" / "handoff" / "2026-09-17-pgvector-adoption-plan.md"
ENV_SAMPLES = (ROOT / ".env.example", ROOT / "deploy" / ".env.server.example")

#: 手册按设计要提到业主机器上才有的文件。它们不进仓，所以不能拿仓库存在性去要求它们。
OPERATOR_SIDE = frozenset({"deploy/.env.server", ".env"})


def _load_script():
    spec = importlib.util.spec_from_file_location("r120_compare_vector_recall", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()


def _compose_document() -> dict:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8-sig"))
    assert isinstance(document, dict), "docker-compose.yml must stay a mapping"
    return document


def _collection_names_in_retriever() -> set[str]:
    """写入侧 get_or_create_collection(...) 里出现的字面量集合。"""
    tree = ast.parse(RETRIEVER_PATH.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Attribute) and function.attr == "get_or_create_collection":
            for argument in list(node.args) + [keyword.value for keyword in node.keywords]:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    names.add(argument.value)
    return names


def _retriever_chroma_dir_default() -> str:
    tree = ast.parse(RETRIEVER_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "DocumentRetriever":
            for item in node.body:
                if not (isinstance(item, ast.FunctionDef) and item.name == "__init__"):
                    continue
                defaults = item.args.defaults
                for argument, default in zip(item.args.args[len(item.args.args) - len(defaults):],
                                             defaults):
                    if argument.arg == "chroma_dir" and isinstance(default, ast.Constant):
                        return str(default.value)
    raise AssertionError("DocumentRetriever.__init__ lost its chroma_dir default")


def _runbook() -> str:
    text = PLAN_DOC.read_text(encoding="utf-8")
    start = text.find("\n## 8. ")
    assert start != -1, "计划文档里没有 §8：P3 手册整节不见了"
    return text[start:]


def _allowed_distance_functions() -> set[str]:
    sql = MIGRATION_0010.read_text(encoding="utf-8")
    allowed: set[str] = set()
    for clause in re.findall(r"distance_function IN \(([^)]*)\)", sql):
        allowed.update(re.findall(r"'([^']+)'", clause))
    assert allowed, "0010 里找不到 distance_function 的 CHECK 允许集，钉子无处可钉"
    return allowed


# --------------------------------------------------------------- 集合名 / 目录名对得上真源


def test_the_write_path_creates_exactly_one_collection_name():
    """先钉"只有一个名字"：有两个就先统一，再谈脚本默认值写谁。"""
    names = _collection_names_in_retriever()

    assert len(names) == 1, (
        "写入侧出现了不止一个 Chroma 集合名 " + repr(sorted(names))
        + "：compare_vector_recall 的默认值与 §8 手册都得跟着改，先去 retriever 收口"
    )


def test_the_scripts_default_collection_is_the_one_the_writer_creates():
    created = _collection_names_in_retriever().pop()

    assert SCRIPT.parse_args([]).collection == created, (
        "compare_vector_recall 默认比的是另一个集合，读出来的是"
        "『enterprise_brain 里有没有』而不是『生产语料里有没有』"
    )


def test_the_default_collection_is_not_the_postgres_database_name():
    """库名与集合名长得像，抄错过一次，就把"不许相等"也钉上。"""
    declared = _compose_document()["services"]["postgres"]["environment"]["POSTGRES_DB"]
    fallback = re.fullmatch(r"\$\{POSTGRES_DB:-([^}]+)\}", str(declared))
    assert fallback, declared

    assert SCRIPT.parse_args([]).collection != fallback.group(1)


def test_the_scripts_default_chroma_dir_is_the_directory_the_writer_opens():
    """脚本默认目录 == retriever 默认目录 == compose 挂进容器的那个 /app 下的路径。"""
    default = SCRIPT.parse_args([]).chroma_dir

    assert default == _retriever_chroma_dir_default()
    targets = [entry.split(":")[-1]
               for entry in _compose_document()["services"]["backend"]["volumes"]]
    assert "/app/" + re.sub(r"^\./", "", default) in targets, targets


def test_nothing_in_the_delivery_surface_renames_those_two_defaults():
    """手册里"不传也默认对"这句话，前提是交付面没有别处偷偷改名。改名就要同时改 §8。"""
    for path in (COMPOSE, *ENV_SAMPLES):
        text = path.read_text(encoding="utf-8-sig")
        for name in ("CHROMA_COLLECTION", "CHROMA_DIR"):
            assert not re.search(rf"^\s*{name}\b", text, re.MULTILINE), (
                f"{path.name} 开始设置 {name}：§8 手册与脚本默认值要同时核一遍"
                "（migrations 与 deploy 那两处是有意的例外吗？）"
            )


# ------------------------------------------------------------------ 距离算符的两种拼法


def test_every_distance_function_0010_allows_has_an_operator_here():
    allowed = _allowed_distance_functions()

    assert allowed == {"l2", "cosine", "ip"}, sorted(allowed)
    for stored in sorted(allowed):
        assert SCRIPT.canonical_distance(stored) in SCRIPT.DISTANCE_OPERATORS, stored


def test_the_script_and_the_library_disagree_by_spelling_not_by_arithmetic():
    assert SCRIPT.canonical_distance("ip") == "inner_product"
    assert SCRIPT.canonical_distance("l2") == "l2"
    assert SCRIPT.canonical_distance("cosine") == "cosine"
    assert SCRIPT.canonical_distance(" L2 ") == "l2"
    assert SCRIPT.canonical_distance("") == ""


def test_an_unrecognised_distance_function_cannot_invent_an_operator():
    """认不出来就原样返回：宁可停在"两侧不一致 ⇒ 退出码 2"，也不许凑出一个算符继续比。"""
    for junk in ("", "l1", "euclid", "inner_product2", "0"):
        assert SCRIPT.canonical_distance(junk) not in SCRIPT.DISTANCE_OPERATORS, junk


def test_the_default_fixture_list_is_the_two_shipped_question_sets():
    """§8.8 说"默认两份＝135 题"，两份题集的名字就钉在这里。"""
    assert SCRIPT.DEFAULT_FIXTURES == (
        "tests/fixtures/business_evaluation_30.jsonl",
        "tests/fixtures/business_evaluation_100.jsonl",
    )
    for relative in SCRIPT.DEFAULT_FIXTURES:
        assert (ROOT / relative).is_file(), relative


# ---------------------------------------------------------------- §8 手册自身与真源一致


def test_the_runbook_names_every_step_that_has_to_happen_in_order():
    runbook = _runbook()
    required = (
        "## 8. P3 执行手册",
        "docker compose --env-file deploy/.env.server -f docker-compose.yml",
        "$DC stop backend worker scheduler",
        "VECTOR_DUAL_WRITE=on",
        "printenv VECTOR_DUAL_WRITE",
        "scripts/rebuild_index.py --status",
        "--confirm-scope",
        "compare_vector_recall.py --skip-questions",
        "--collection enterprise_docs",
        "--chroma-dir /app/chroma_db",
        "schema_migrations ORDER BY version",
        "vector_scope WHERE schema_version = 1",
        "hnsw:space",
        "all_zero_rows",
        "zero_vectors_before",
        "check_eval_evidence_coverage.py",
        "index_version_id_null",
        "### 8.9 跑完交什么给总控",
    )
    missing = [needle for needle in required if needle not in runbook]

    assert not missing, "§8 少了照着做就跑不通的一步：" + repr(missing)


def test_the_runbook_order_is_stop_write_then_rebuild_then_compare():
    runbook = _runbook()
    stop = runbook.index("$DC stop backend worker scheduler")
    rebuild = runbook.index("scripts/rebuild_index.py --apply")
    compare = runbook.index("compare_vector_recall.py --skip-questions")
    questions = runbook.index("--fixture tests/fixtures/business_evaluation_100.jsonl")

    assert stop < rebuild < compare < questions, (stop, rebuild, compare, questions)


def test_the_runbooks_command_prefix_is_the_one_compose_documents():
    prefix = "docker compose --env-file deploy/.env.server -f docker-compose.yml"
    header = "\n".join(COMPOSE.read_text(encoding="utf-8-sig").splitlines()[:20])

    assert prefix in header, "compose 顶部那条权威调用式变了，§8 的 $DC 得跟着改"
    assert prefix in _runbook()


def test_every_repository_path_named_in_the_runbook_exists():
    """文案缺陷的同一族守卫：手册里写出来的文件/脚本路径，必须真在仓里。"""
    pattern = re.compile(
        r"`((?:app|scripts|migrations|tests|docs|deploy)/[A-Za-z0-9_./-]+)")
    referenced = {match.group(1) for match in pattern.finditer(_runbook())}
    assert referenced, "手册里一个仓库路径都没提到，说明这条守卫被掏空了"

    missing = sorted(
        relative for relative in referenced
        if relative not in OPERATOR_SIDE and not (ROOT / relative).exists()
    )
    assert not missing, "§8 引用了不存在的路径：" + repr(missing)


def test_the_runbook_keeps_the_read_path_out_of_this_ticket():
    runbook = _runbook()

    assert "不切读" in runbook
    assert "R59" in runbook
    assert "不动 `app/rag/retrieval_pipeline.py`" in runbook, (
        "§8 必须明写切读属 R59：本单的边界就是只打通通路"
    )
    assert "改 `frontend/" not in runbook
