"""R552 的钉：铺树器交给新件的那一版行尾，必须等于「这枚 blob 被 git 检出之后盘上的那一版」。

判据不是「一律 CRLF」。那只是把今天的读数抄进代码：这台机 core.autocrlf=true 且没有
.gitattributes，它今天确实算出 CRLF；同一枚函数在 core.autocrlf=input 的机器上必须算出 LF，
在 -text 或二进制上必须算出「原样字节」——否则它就不是一条不变式，而是一枚硬编码。

每条格的正解都由 git 自己交回：把一枚已入库的文件删掉再 `git checkout --` 它，数盘上那版的
CR，再拿同一套生效规则问决策函数（`checkout_form`）。摘掉 R552 那处修复，第三格当场红——
因为 siblings 数的是 blob 行尾，而本仓文本件的 blob 恒为 LF（现取 siblings 读数里
crlf 零枚），铺出来的 LF 与检出后的 CRLF 不同形。
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("r531_worktree_merge_r552",
                                               REPO / "scripts" / "r531_worktree_merge.py")
merger = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = merger
_SPEC.loader.exec_module(merger)

LF_BODY = b"alpha\nbeta\ngamma\n"


def _run(root, *args):
    done = subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    assert done.returncode == 0, (args, done.stdout, done.stderr)
    return (done.stdout or "").strip()


def _fixture(tmp_path, name, autocrlf="true", attributes=None):
    """一枚离线的最小仓：文本件按 LF 写盘入库，siblings 也全是 LF 本。"""
    root = tmp_path / name
    (root / "tests").mkdir(parents=True)
    _run(root, "init", "-q")
    _run(root, "config", "user.name", "r552")
    _run(root, "config", "user.email", "r552@example.invalid")
    _run(root, "config", "core.autocrlf", autocrlf)
    if attributes is not None:
        (root / ".gitattributes").write_text(attributes, encoding="utf-8")
    for i in range(3):
        (root / "tests" / ("sibling_%d.py" % i)).write_bytes(b"x = %d\n" % i)
    (root / "tests" / "keeper.py").write_bytes(LF_BODY)
    _run(root, "add", "-A")
    _run(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture")
    return root


def _observed_checkout(root, rel):
    """正解：删掉再 `git checkout --`，数回来那一版的行尾（并自证还原成同一枚字节）。"""
    path = root / rel
    path.unlink()
    _run(root, "checkout", "--", rel)
    first = path.read_bytes()
    path.unlink()
    _run(root, "checkout", "--", rel)
    again = path.read_bytes()
    # 自证基线只能取「检出这件事本身」，不能取我写进 fixture 的那一份：09-30 23:57 首跑就红在这一格
    # ——`assert b'alpha\r\nbeta\r\ngamma\r\n' == b'alpha\nbeta\ngamma\n'`，git 从 LF blob 检出成
    # CRLF 是**正确行为**，我却拿写入时的 LF 当基线，等于把被判的形状当成 fixture 坏了。
    assert again == first, rel + "：两次 git checkout 交回不同字节，这格的正解不可信"
    return merger.detect(first)


def test_a_decision_equals_observed_checkout_in_every_shape(tmp_path, monkeypatch):
    """六枚盘面：autocrlf 三态 × 属性三态。决策必须与 git 实测的检出形态同形。"""
    cases = [
        ("true", None),
        ("input", None),
        ("false", None),
        ("true", "*.py -text\n"),
        ("true", "*.py text eol=lf\n"),
        ("input", "*.py text eol=crlf\n"),
    ]
    for index, (autocrlf, attributes) in enumerate(cases):
        root = _fixture(tmp_path, ("shape%d" % index), autocrlf, attributes)
        # 决策函数问的是 merger.ROOT 那套生效规则，所以每一枚盘面都要把 ROOT 指到当枚 fixture，
        # 否则六格全都在拿本仓的配置复算，正解（fixture 实测）与决策根本不在同一枚仓里问。
        monkeypatch.setattr(merger, "ROOT", root)
        observed = _observed_checkout(root, "tests/keeper.py")
        decided, note = merger.checkout_form("tests/keeper.py", LF_BODY)
        if decided == "asis":
            assert observed == merger.detect(LF_BODY), (autocrlf, attributes, decided, observed, note)
        else:
            assert observed == decided, (autocrlf, attributes, decided, observed, note)
        assert note.startswith("检出形态="), note


def test_b_this_boxs_effective_rules_reproduce_the_decision(tmp_path):
    """把**本机生效的**那套规则搬进 fixture 复算一遍：不许拿今天的字面量当不变式。"""
    autocrlf = merger.git_config("core.autocrlf")
    root = _fixture(tmp_path, "asis", autocrlf or "false")
    rel = "tests/keeper.py"
    # 这一格故意不搬 ROOT：决策要按**本仓真实生效**的那套规则问 git，
    # fixture 只负责把那套规则复现一遍并交出实测正解。
    observed = _observed_checkout(root, rel)
    decided, note = merger.checkout_form(rel, LF_BODY)
    if decided == "asis":
        assert observed == merger.detect(LF_BODY), (autocrlf, decided, observed, note)
    else:
        assert observed == decided, (autocrlf, decided, observed, note)


def test_c_a_landed_new_file_is_exactly_what_checkout_would_give(tmp_path, monkeypatch):
    """端到端（判据④）：经 --apply 落到主树的那枚新件字节，必须等于它入库后被检出的字节。"""
    root = _fixture(tmp_path, "main", "true")
    tree = tmp_path / "be-fake"
    (tree / "tests").mkdir(parents=True)
    (tree / "tests" / "brand_new.py").write_bytes(b"first\nsecond\nthird\n")
    monkeypatch.setattr(merger, "ROOT", root)
    assert merger.apply_paths(tree, ["tests/brand_new.py"]) == 0
    laid = (root / "tests" / "brand_new.py").read_bytes()
    _run(root, "add", "tests/brand_new.py")
    _run(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "landed")
    _run(root, "checkout", "--", "tests/brand_new.py")
    (root / "tests" / "brand_new.py").unlink()
    _run(root, "checkout", "--", "tests/brand_new.py")
    assert (root / "tests" / "brand_new.py").read_bytes() == laid, "落盘形态不等于检出形态"
    assert merger.detect(laid) == "crlf", merger.detect(laid)


def test_d_binary_and_minus_text_new_files_land_verbatim(tmp_path, monkeypatch):
    """asis 那一格：git 检出不做转换，铺树器也不许动字节（顺手统一＝把 xlsx 改坏）。"""
    root = _fixture(tmp_path, "main", "true", "*.bin -text\n")
    tree = tmp_path / "be-fake"
    (tree / "tests").mkdir(parents=True)
    payload = b"PK\x03\x04\x00\x00\nline1\nline2\n"  # 纯 LF＋NUL：混行尾的源件会被 apply_paths 按规矩先拒掉
    (tree / "tests" / "payload.bin").write_bytes(payload)
    monkeypatch.setattr(merger, "ROOT", root)
    assert merger.apply_paths(tree, ["tests/payload.bin"]) == 0
    assert (root / "tests" / "payload.bin").read_bytes() == payload


def test_e_siblings_stay_a_diagnosis_and_the_in_book_rule_still_wins(tmp_path, monkeypatch, capsys):
    """新件一格由检出形态决定，siblings 只留痕；在册件仍按盘上那一版（判据③⑥）。"""
    root = _fixture(tmp_path, "main", "true")
    (root / "tests" / "keeper.py").write_bytes(b"disk\r\nform\r\n")
    tree = tmp_path / "be-fake"
    (tree / "tests").mkdir(parents=True)
    (tree / "tests" / "brand_new.py").write_bytes(b"first\nsecond\n")
    (tree / "tests" / "keeper.py").write_bytes(b"new\r\ncontent\r\n")
    monkeypatch.setattr(merger, "ROOT", root)
    assert merger.apply_paths(tree, ["tests/brand_new.py", "tests/keeper.py"]) == 0
    printed = capsys.readouterr().out
    assert "只作诊断，不决策" in printed, printed
    assert "检出形态=crlf" in printed, printed
    assert merger.detect((root / "tests" / "brand_new.py").read_bytes()) == "crlf"
    assert merger.detect((root / "tests" / "keeper.py").read_bytes()) == "crlf"
    assert (root / "tests" / "keeper.py").read_bytes() == b"new\r\ncontent\r\n"
