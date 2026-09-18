"""R44 判据①：热集覆盖面 —— 分母是评测集里那 105 题，不是自造题号。

口径（写死在这里，免得下次换人重新解释）：

* **分母**：tests/fixtures/business_evaluation_100.jsonl 与 business_evaluation_30.jsonl
  合并去重后的 **105** 道题（两份文件的 id 交集非空，30 那份是 100 那份的子集）。
* **语料**：**入了版本控制**的 documents/*.txt（.pdf 不参与 —— 本单不许动解析链，也不许为了
  让数字好看少喂文档）。这里刻意不取目录列表：documents/ 按设计兼作上传落地区（H16），主树实测
  115 个 txt 里只有 95 个入库，那 20 个上传产物把 chunk 数从 379 顶到 37 483，于是"整批语料
  都在预算内"这个前提会随这台机器传过什么而漂移 —— 而它正是下面两条判据成立的条件。取 git
  清单与 R72（f396866）同一口径。评测集不带权限标注，所以这一趟跑的是 where=None 的最坏情况：
  任何一条冷条目都可能被召回，热集必须整批常驻才敢服务。
* **"命中热集"**：这一题的检索由热集给出、没有回穿外部向量库（search 全程 0 次 query 调用）。
  不是"热集里有相关文档"，也不是"分数够高"，就是服务/没服务二值。

这一份不 import 其它测试模块（tests/ 没有 __init__.py，跨用例文件 import 不是本仓的既有
写法），所以 embedding 桩在这里再写一遍，判定逻辑仍然只在 app/rag 里有一份。
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from app.rag import hot_index as hi
from app.rag import retriever as retriever_module
from app.rag.retriever import DocumentRetriever

#: 从测试文件自身位置回溯到仓库根，不依赖调用时的 cwd。
REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures"
DOCUMENT_ROOT = REPO_ROOT / "documents"
EXPECTED_QUESTIONS = 105


def evaluation_questions() -> list:
    """合并两份评测集，按 id 去重排序 —— 分母就是它，105。"""
    by_id = {}
    for path in sorted(FIXTURE_ROOT.glob("business_evaluation_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            by_id[row["id"]] = row
    return [by_id[key] for key in sorted(by_id, key=lambda key: (len(key), key))]


def tracked_corpus() -> list:
    """documents/ 里**入了版本控制**的那批 txt —— 不是目录列表。

    本机实测：目录列表 115 个 / 入库 95 个，喂进向量库是 37 483 个 chunk 对 379 个。用目录
    列表时同一份代码在干净树上全绿、在接过上传的主树上当场红，而这条红没有信息量：它测的是这
    台机器传过什么，不是热集能不能覆盖语料。
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--", "documents"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        check=False,
    )
    assert listing.returncode == 0, f"git ls-files 未能列出语料：{listing.stderr!r}"
    names = sorted(item.decode("utf-8") for item in listing.stdout.split(b"\0") if item)
    files = [REPO_ROOT / name for name in names if name.endswith(".txt")]
    assert files, "版本化语料清单为空，这个覆盖率没有意义"
    missing = [str(path) for path in files if not path.is_file()]
    assert not missing, f"git 认为已入库、盘上却不在：{missing}"
    return files


def _hash_vector(text: str, dim: int) -> list:
    vector = [0.0] * dim
    data = str(text).encode("utf-8")
    for position in range(0, len(data), 3):
        digest = int.from_bytes(hashlib.md5(data[position:position + 3]).digest()[:4], "big")
        vector[digest % dim] += 1.0 + (digest % 7) / 10.0
    return vector if any(vector) else [1.0] + [0.0] * (dim - 1)


class _Store:
    """真 chromadb + 确定性 embedding 桩，外加"这一趟穿了几次外部库"的计数器。"""

    def __init__(self, tmp_path, monkeypatch, *, max_chunks: int):
        self.monkeypatch = monkeypatch
        monkeypatch.setattr(retriever_module.OllamaEmbeddings, "_call_api",
                            lambda _self, text: _hash_vector(
                                str(text), retriever_module.EMBEDDING_DIM))
        index = hi.HotSetIndex(max_chunks=max_chunks, roster_ttl_seconds=3600.0)
        monkeypatch.setattr(hi, "_HOT_INDEX", index)
        hi.reset_hot_index_diagnostics()
        self.index = index
        self.retriever = DocumentRetriever(chroma_dir=str(tmp_path / "chroma"))
        self.outer_reads = 0
        self.outer_queries = 0
        target = self.retriever.collection
        store = self
        real_get, real_query = target.get, target.query

        def get(*args, **kwargs):
            store.outer_reads += 1
            return real_get(*args, **kwargs)

        def query(*args, **kwargs):
            store.outer_queries += 1
            return real_query(*args, **kwargs)

        target.get, target.query = get, query

    def add_document(self, filename: str, content: str):
        self.retriever.add_document(filename, content, classification=1, department="")

    def search(self, question: str, k: int = 5) -> list:
        self.outer_reads = self.outer_queries = 0
        return self.retriever.search(question, k=k)


def _keys(hits: list) -> list:
    return [(hit["source"], hit["chunk_index"]) for hit in hits]


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    monkeypatch = pytest.MonkeyPatch()
    store = _Store(tmp_path_factory.mktemp("r44coverage"), monkeypatch,
                   max_chunks=hi.DEFAULT_MAX_CHUNKS)
    files = tracked_corpus()
    assert len(files) >= 80, f"版本化语料清单不对，只读到 {len(files)} 个 txt"
    for path in files:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
        if content:
            store.add_document(path.name, content)
    store.corpus_files = len(files)
    yield store
    monkeypatch.undo()


def test_hot_index_covers_the_evaluation_question_set(corpus, capsys):
    """①覆盖率 ≥95%，②一致性（同序同 id）在同一批题上一起钉。"""
    questions = evaluation_questions()
    assert len(questions) == EXPECTED_QUESTIONS, len(questions)

    corpus.index.reset(reason="coverage baseline pass")
    baselines = {}
    corpus.monkeypatch.delenv(hi.HOT_INDEX_ENV, raising=False)
    for row in questions:
        baselines[row["id"]] = corpus.search(row["question"])
    queries_off = corpus.outer_queries
    reads_off = corpus.outer_reads

    corpus.monkeypatch.setenv(hi.HOT_INDEX_ENV, "1")
    corpus.index.reset(reason="coverage hot pass")
    served = 0
    nonempty = 0
    identical = 0
    evidence = 0
    mismatches = []
    total_reads = 0
    total_queries = 0
    reads_of_one_warm = None
    for row in questions:
        before = hi.hot_index_diagnostics()["hits"]
        hits = corpus.search(row["question"])
        total_reads += corpus.outer_reads
        total_queries += corpus.outer_queries
        hot_served = hi.hot_index_diagnostics()["hits"] > before and corpus.outer_queries == 0
        if hot_served and reads_of_one_warm is None:
            # 第一次由热集服务之后累计下来的读库次数，就是一次完整暖机的开销；后面每一题都必须
            # 一次都不许多读 —— 钉的是"不是每题重跑整库回读"，与回读分成几页无关。
            reads_of_one_warm = total_reads
        served += int(hot_served)
        nonempty += int(hot_served and bool(hits))
        same = _keys(hits) == _keys(baselines[row["id"]])
        identical += int(same)
        if not same:
            mismatches.append((row["id"], row["question"],
                               _keys(baselines[row["id"]]), _keys(hits)))
        if hot_served and hits:
            wanted = [str(item) for item in (row.get("must_contain") or [])]
            if wanted and any(item in hit["content"] for item in wanted
                              for hit in hits):
                evidence += 1
    corpus.monkeypatch.delenv(hi.HOT_INDEX_ENV, raising=False)

    with capsys.disabled():
        print(f"\n[R44 判据①] 分母 = 评测集 distinct question = {len(questions)} 题")
        print(f"[R44 判据①] 语料 = documents/*.txt {corpus.corpus_files} 篇 → "
              f"向量库 {corpus.index.resident_chunks + corpus.index.cold_chunks} 个 chunk，"
              f"其中常驻 {corpus.index.resident_chunks}，冷表 {corpus.index.cold_chunks}")
        print(f"[R44 判据①] 热集覆盖率 = {served}/{len(questions)} "
              f"({served / len(questions) * 100:.1f}%)  判据 ≥95% (≥101/105)")
        print(f"[R44 判据①] 其中命中且非空 = {nonempty}/{len(questions)}；"
              f"命中里能直接看到 must_contain 期望证据 = {evidence}/{len(questions)}"
              "（旁证，不计入判据：embedding 是确定性哈希桩，排名不代表检索质量）")
        print(f"[R44 判据②] 与外部向量库逐条同序同 id = {identical}/{len(questions)}")
        print(f"[R44 省下的往返] 关闭态 105 题 = {len(questions) * 1} 次 query 调用"
              f"（末题实测 query={queries_off} get={reads_off}）；"
              f"开启态 105 题 = query {total_queries} 次 + get {total_reads} 次")
        for item in mismatches[:20]:
            print("[R44 差异]", item)
    assert mismatches == []
    assert identical == len(questions)
    assert served >= 101, f"覆盖率未达 95%: {served}/{len(questions)}"
    assert served == len(questions), "整批语料都在预算内，理论上应当全覆盖"
    assert total_queries == 0, total_queries
    # 原先钉的是 total_reads == 2，那个数只在"整库一次就读得完"时成立；回读一分页它就变成
    # 假判据。换成下面这条，钉的是意图本身：一整批 105 题只付一次暖机的读库代价。
    assert 0 < total_reads == reads_of_one_warm, (total_reads, reads_of_one_warm)


def test_coverage_drops_to_zero_when_the_budget_cannot_hold_the_corpus(tmp_path, monkeypatch):
    """覆盖面不是"永远 100%"的自证：预算装不下整批语料时，热集必须整体让路。

    这一条给判据①的分母同一个口径，但把 HOT_INDEX_MAX_CHUNKS 收到 3 个 chunk：
    覆盖率必须塌到 0，而且每题结果仍与外部库逐条同序同 id（近似结果集是不允许的）。
    """
    questions = evaluation_questions()
    store = _Store(tmp_path, monkeypatch, max_chunks=3)
    files = tracked_corpus()
    for path in files[:12]:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
        if content:
            store.add_document(path.name, content)
    served = 0
    identical = 0
    for row in questions:
        baseline = store.search(row["question"])
        monkeypatch.setenv(hi.HOT_INDEX_ENV, "1")
        hits = store.search(row["question"])
        served += int(store.outer_queries == 0)
        identical += int(_keys(hits) == _keys(baseline))
    monkeypatch.delenv(hi.HOT_INDEX_ENV, raising=False)
    with pytest.MonkeyPatch.context() as check:
        check.setenv(hi.HOT_INDEX_ENV, "1")
        reason = store.index.bypass_reason(
            query_vector=store.retriever.embedding.embed_query(questions[0]["question"]))
    assert store.index.resident_chunks == 3 and store.index.cold_chunks > 0
    assert served == 0, served
    assert identical == len(questions), identical
    assert reason == hi.REASON_INCOMPLETE
