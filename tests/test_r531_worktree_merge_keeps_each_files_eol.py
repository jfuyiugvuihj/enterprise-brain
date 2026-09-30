"""R531 铺树器的牙（总控自修·09-30）。

它守的是「把执行层工作树搬进主树」这一步的行尾归位：本仓主树是混排的——`git show HEAD:` 里的
blob 是 LF，而磁盘在 `core.autocrlf=true` 下检出成 CRLF；部分 `docs/**` 的磁盘形态也是 LF。
整片拷贝铺树会把 CRLF 混进 LF 本，当场踩响逐字节钉（`tests/test_r469_readout_is_generated.py`
09-30 现取就是这么红的：blob 237481 字节无 CR、盘上 244675 字节）。

判据：
 ① `detect()` 认得四态，且「纯 LF」绝不能被判成 mixed（本席第一版就写错了这一格，用例把它钉住）；
 ② `normalize()` 双向可逆且幂等：CRLF→lf→crlf 字节数还原，无尾换行不被补出来；
 ③ 混合行尾的源文件必须被拒（`apply_paths` 的 REJECT 路径），不许「挑一种多数」硬写；
 ④ 新件的惯例来自同目录同后缀在册件多数决，平票就拒绝搬（不许猜）；
 ⑤ `chroma_db/**` 这类永久脏项与临时目录默认不进清单。
反证三把：K1 把 detect 的纯 LF 分支拆掉 / K2 让 normalize 无条件补尾换行 / K3 让平票默认选 CRLF。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("r531_worktree_merge", ROOT / "scripts" / "r531_worktree_merge.py")
merger = importlib.util.module_from_spec(_SPEC)
import sys
sys.modules[_SPEC.name] = merger
_SPEC.loader.exec_module(merger)


def test_a_pure_lf_is_not_mixed():
    assert merger.detect(b"a\nb\nc\n") == "lf"
    assert merger.detect(b"a\r\nb\r\n") == "crlf"
    assert merger.detect(b"a\r\nb\nc\n") == "mixed"
    assert merger.detect(b"") == "empty"
    assert merger.detect(b"no newline at all") == "empty"


def test_b_normalize_round_trips_both_ways():
    crlf = b"one\r\ntwo\r\n"
    as_lf = merger.normalize(crlf, "lf")
    assert as_lf == b"one\ntwo\n"
    assert merger.normalize(as_lf, "crlf") == crlf
    mixed = b"one\r\ntwo\nthree\r\n"
    assert merger.normalize(mixed, "lf") == b"one\ntwo\nthree\n"
    assert merger.normalize(merger.normalize(mixed, "lf"), "lf") == b"one\ntwo\nthree\n"


def test_c_missing_trailing_newline_is_not_invented():
    assert merger.normalize(b"a\nb", "lf") == b"a\nb"
    assert merger.normalize(b"a\r\nb", "crlf") == b"a\r\nb"


def test_d_a_mixed_source_is_rejected_not_guessed(tmp_path, monkeypatch, capsys):
    tree = tmp_path / "be-fake"
    (tree / "app").mkdir(parents=True)
    (tree / "app" / "x.py").write_bytes(b"a\r\nb\nc\n")
    monkeypatch.setattr(merger, "blob_convention", lambda path: "lf")
    assert merger.apply_paths(tree, ["app/x.py"]) == 1
    out = capsys.readouterr().out
    assert "REJECT" in out and "行尾混合" in out
    assert not (ROOT / "app" / "x.py").exists()


def test_e_new_file_convention_comes_from_siblings_and_a_tie_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(merger, "git", lambda cwd, *a: (0, "a.py\nb.py\nc.py\n"))
    seen = {"a.py": "lf", "b.py": "lf", "c.py": "crlf"}
    monkeypatch.setattr(merger, "blob_convention", lambda path: seen.get(path))
    conv, note = merger.sibling_convention("new.py")
    assert conv == "lf", note
    tie = {"a.py": "lf", "b.py": "crlf", "c.py": None}
    monkeypatch.setattr(merger, "blob_convention", lambda path: tie.get(path))
    conv2, note2 = merger.sibling_convention("new.py")
    assert conv2 is None, note2


def test_f_permanent_junk_never_enters_the_list(tmp_path, monkeypatch):
    tree = tmp_path / "be-fake"
    tree.mkdir()
    rows = [("M", "chroma_db/chroma.sqlite3"), ("M", "app/good.py"), ("??", "app/.tmp-r526/x.py"),
            ("??", "probe.txt"), ("M", "app/keep.py.r57bak"), ("??", "docs/testing/ok.md")]
    monkeypatch.setattr(merger, "porcelain", lambda t: rows)
    monkeypatch.setattr(merger, "blob_convention", lambda path: "lf")
    kept = [path for _, path, _, _ in merger.listable(tree)]
    assert kept == ["app/good.py", "docs/testing/ok.md"], kept
