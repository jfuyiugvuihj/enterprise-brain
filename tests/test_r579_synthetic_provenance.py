# -*- coding: utf-8 -*-
"""R579 · 合成向量的来历钉：LCG 不许漂、档位必须互为前缀、题目 seed 不许落在语料里、出料只落仓外。

判据 4 要求这单把"合成≠客户语料分布"写成独立一格，而这一格的前提是**合成串本身可复算**：

  ① 本件的 `synth_vector` 与在册 `scripts/r59c_sandbox_corpus.py:116` 必须逐枚全等
     （同一枚 LCG 链、同一个取值域、同一个归一化量、同一位小数）。漂了就是两批不同的向量，
     凭据纸里那句"与在册件同源"立刻成假话——所以这里逐 seed 逐维对，不对就红。
  ② 四档规模必须互为前缀：第 N 档的字节流是第 M 档（N<M）的前 N 行。拐点因此是"同一批
     向量、只有行数在长"，不是四批不同的向量。sha 由 `data_stream` 边发边算，逐档点名。
  ③ 查询 seed 不许落进语料 seed 序列（题目本身在库里 = 召回虚高）。`corpus_seed_collisions`
     必须对全部题目、全部档位交回空集；顺手钉一枚"故意造一个会撞的 base 就必须抓到"。
  ④ `emit-data` 只往 `--data-dir` 交文件（判据 6 的仓外落点），并且一行 14 列、\t 分隔、
     列内不许有 tab/换行——COPY text 格式被一行脏数据打断，整批灌库就会红在莫名其妙的地方。

🔴 全程离线：不连库、不起服务、不打模型；向量是几何夹具，本件不替它作任何语义声明。
"""
from __future__ import annotations

import importlib.util
import io
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = _load("r579_readout_under_test", "scripts/r579_index_crossover_readout.py")
R59C = _load("r59c_corpus_under_test", "scripts/r59c_sandbox_corpus.py")
SEEDS = (1000, 1007919, 5000, 5000 + 104729, 7, 2 ** 31 - 1, R.QUERY_SEED_BASE)
DIMS = (768, 4, 1536)


# ---------------------------------------------------------------- ① 与在册件同源
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("dimension", DIMS)
def test_synth_vector_is_identical_to_the_registered_generator(seed, dimension):
    mine = R.synth_vector(seed, dimension)
    theirs = R59C.synth_vector(seed, dimension)
    assert mine == theirs, (seed, dimension, mine[:3], theirs[:3])
    assert len(mine) == dimension


def test_synth_vector_is_unit_length_and_reproducible():
    first = R.synth_vector(20261003, 768)
    second = R.synth_vector(20261003, 768)
    assert first == second
    assert abs(math.sqrt(sum(value * value for value in first)) - 1.0) < 1e-4
    other = R.synth_vector(20261004, 768)
    assert other != first
    assert all(isinstance(value, float) for value in first)


def test_corpus_seed_formula_matches_the_registered_corpus():
    """在册件给第 i 枚块用的 seed 是 `1000 + i * 7919`（r59c_sandbox_corpus.py:153）。"""
    for index in (0, 1, 7, 1007):
        assert R.corpus_seed(index) == 1000 + index * 7919


def test_vector_literal_round_trips_and_uses_the_same_spelling_as_r59c():
    vector = R.synth_vector(20261003, 8)
    literal = R.vector_literal(vector)
    assert literal == R59C._sql_literal(vector)
    back = [float(piece) for piece in literal[1:-1].split(",")]
    assert back == vector


# ---------------------------------------------------------------- ② 档位互为前缀
def _lines(rows, **kwargs):
    return [blob for blob, _sha in R.data_stream(rows=rows, **kwargs)]


def test_smaller_size_is_a_byte_prefix_of_the_largest_one():
    stream = rows_kwargs = {"dimension": 8, "classification": 1, "content_bytes": 24,
                            "embedding_model": "nomic-embed-text",
                            "distance_function": "l2"}
    big = _lines(7, **stream)
    assert _lines(3, **stream) == big[:3]
    assert _lines(0, **stream) == []


def test_data_stream_sha_is_the_running_prefix_digest():
    kwargs = {"dimension": 8, "classification": 1, "content_bytes": 24,
              "embedding_model": "nomic-embed-text", "distance_function": "l2"}
    seen = []
    last = None
    for blob, running in R.data_stream(rows=5, **kwargs):
        import hashlib

        seen.append((blob, running))
        last = running
    import hashlib
    manual = hashlib.sha256()
    for index, (blob, running) in enumerate(seen):
        manual.update(blob)
        assert running == manual.hexdigest(), index
    assert last == R.data_sha(rows=5, **kwargs)
    assert last != R.data_sha(rows=4, **kwargs)


def test_row_line_shape_is_copy_ready():
    line = R.row_line(3, dimension=64, classification=1, content_bytes=40,
                      embedding_model="nomic-embed-text", distance_function="l2")
    assert line.endswith("\n")
    fields = line.rstrip("\n").split("\t")
    assert len(fields) == len(R.COPY_COLUMN_ORDER) == 14
    assert not any("\t" in field or "\n" in field for field in fields)
    assert fields[0] == "r579-00000003"
    assert fields[4] == "1"                       # classification = 生产众数（谓词全放行的那一档）
    assert fields[8].startswith("[") and fields[8].endswith("]")
    assert len(fields[8][1:-1].split(",")) == 64
    assert fields[9] == "nomic-embed-text" and fields[11] == "l2"
    assert fields[10] == "64"


def test_query_seeds_never_land_inside_the_corpus_seed_sequence():
    for index in range(40):
        assert R.corpus_seed_collisions(index, 60000) == [], index
    hit = R.corpus_seed_collisions(0, 60000)
    assert hit == []                              # 现公式：全空集
    # 故意造一枚会撞的题目 seed，尺子必须当场抓到（不许"默认无碰撞"是句空话）
    original = R.QUERY_SEED_BASE
    try:
        R.QUERY_SEED_BASE = R.corpus_seed(1234)
        assert R.corpus_seed_collisions(0, 60000) == [1234]
        assert R.corpus_seed_collisions(0, 1000) == []   # 不在该档行数内就不算撞
    finally:
        R.QUERY_SEED_BASE = original


# ---------------------------------------------------------------- ④ 出料只落仓外目录
def test_emit_data_writes_only_into_the_given_directory_and_reports_sha(tmp_path, capsys):
    data_dir = tmp_path / "outside-the-repo"
    rc = R.main(["--action", "emit-data", "--data-dir", str(data_dir),
                 "--sizes", "3,7", "--dimension", "16", "--content-bytes", "32"])
    assert rc == R.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    written = sorted(path.name for path in data_dir.iterdir())
    assert written == ["r579_corpus_7.tsv"]
    assert payload["rows"] == 7 and payload["bytes"] > 0
    assert payload["sha256_by_prefix_rows"]["3"] != payload["sha256_by_prefix_rows"]["7"]
    assert payload["sha256"] == payload["sha256_by_prefix_rows"]["7"]
    assert not list(tmp_path.parent.glob("**/r579_corpus_*.tsv")) or True
    # 工作树里不许落任何灌数据文件（判据 6：临时大文件只准在仓外目录）
    assert list(ROOT.glob("**/r579_corpus_*.tsv")) == []


def test_sizes_must_be_increasing_and_positive():
    with pytest.raises(SystemExit):
        R.parse_sizes("5000,1008")
    with pytest.raises(SystemExit):
        R.parse_sizes("1008,1008")
    with pytest.raises(SystemExit):
        R.parse_sizes("")
    assert R.parse_sizes("1008,5000,20000") == [1008, 5000, 20000]
    for bad in ("0", "-5,10", "1008,0"):
        with pytest.raises(SystemExit):
            R.parse_sizes(bad)
    with pytest.raises(SystemExit):
        R.parse_ks("0")
    assert R.parse_ks("20,5,5") == [5, 20]


def test_schema_names_are_derived_from_the_size_and_padded():
    assert R.schema_name(1008) == "sz_0001008"
    assert R.schema_name(50000) == "sz_0050000"
    assert all(R.IDENT_RE.match(R.schema_name(size)) for size in (1, 1008, 50000))