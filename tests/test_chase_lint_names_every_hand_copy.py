"""CHASE-2026-10-06 段 B 的牙：手抄坐标棘轮自己得能被咬住。

形状照 tests/test_r132_contract_followup_sync.py 抄：全离线、不 import app、单跑亚秒级。
本件也进了尺自己的扫描范围（自咬），所以这里**一枚字面坐标都不许出现**——要造形状就用拼接，
让尺去判那枚拼出来的串，而不是让读者在源码里读到一个假行号。
"""
import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = "scripts/lint_hand_copied_coordinates.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("chase_lint", REPO / TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LINT = load_tool()


def hand_copy_token():
    """拼出一枚越界坐标的字面形状（本件源码里没有这枚字面量，靠尺去认拼出来的串）。"""
    return "app" + "/" + "demo" + "." + "py" + LINT.COLON + "1234"


def make_scope(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts").mkdir()
    return tmp_path


def write(path, body):
    """写字节而不是写文本：Windows 的文本模式会把 body 里显式的 \r\n 再转义一遍，
    行位翻倍之后，牙就会把一个正确的行号读成别处（本班实测 3 行读成 5 行）。"""
    path.write_bytes(body.encode("utf-8"))
    return path


def test_the_live_tree_sits_exactly_on_the_ratchet(tmp_path=None):
    """双向棘轮：超预算要红，**降了不重取基线也要红**——留着旧数就是拿旧账装新盘面。"""
    per_file, total = LINT.scan(REPO)
    assert total == LINT.HAND_COPY_BUDGET, (
        "现取 %d 枚 vs 预算 %d 枚：改这一格必须在提交词里逐枚点名是谁降的" % (total, LINT.HAND_COPY_BUDGET))
    assert len(per_file) > 0, "受管范围里一枚都没认出＝这把尺今天没在量东西"


def test_a_single_added_hand_copy_pushes_over_the_budget(tmp_path):
    root = make_scope(tmp_path)
    victim = write(root / "tests" / "test_victim.py",
                   "EXPECTED = " + repr(hand_copy_token()) + "\n")
    per_file, total = LINT.scan(root)
    assert total == 1, "新种一枚手抄坐标却读不到：" + str(victim)
    assert list(per_file)[0].replace("\\", "/").endswith("tests/test_victim.py")


def test_prose_is_not_judged_but_data_is(tmp_path):
    """docstring 与注释里写出处不驱动判等；只有落进字符串常量的才算越界。"""
    root = make_scope(tmp_path)
    body = (
        '"""叙事件：见 ' + hand_copy_token() + ' 那一格（这是文档字符串，不该红）。"""\r\n'
        "# 注释里也写 " + hand_copy_token() + " —— 人话，不该红\r\n"
        "CITED = " + repr(hand_copy_token()) + "\r\n"
    )
    write(root / "scripts" / "carrier.py", body)
    per_file, total = LINT.scan(root)
    assert total == 1, "把叙事也当成判据数据了：现取 " + str(total) + " 枚"
    carrier = "scripts" + "\\" + "carrier.py"
    expect = 1 + next(i for i, line in enumerate(body.splitlines()) if line.startswith("CITED"))
    assert per_file[carrier][0][0] == expect, (per_file[carrier], expect)


def test_the_pattern_does_not_flag_its_own_source(tmp_path):
    """尺自己的源码在扫描范围内（自咬）：正则的字面形状不能被它自己认成坐标。"""
    assert LINT.LITERAL_CITE.search(LINT.LITERAL_CITE.pattern) is None
    for rel in (TOOL, "tests/test_chase_lint_names_every_hand_copy.py"):
        hits = LINT.hits_in_file(REPO / rel)
        assert hits == [], rel + " 里长出字面坐标：" + str(hits[:3])


def test_an_unparseable_file_refuses_instead_of_passing(tmp_path):
    root = make_scope(tmp_path)
    write(root / "scripts" / "broken.py", "def oops(:\n")
    try:
        LINT.scan(root)
    except SyntaxError as exc:
        assert "broken.py" in str(exc), "拒绝却没点名是哪枚文件：" + str(exc)
    else:
        raise AssertionError("解析不动却被静默跳过——死锚比没锚更坏")


def _run_cli(root, extra):
    """跑一次尺，cwd 固定在受管仓库、量的是 --root 给的那棵树（cwd 不决定量什么）。"""
    return subprocess.run([sys.executable, str(REPO / TOOL), "--check", "--report",
                           "--root", str(root)] + extra,
                          cwd=str(REPO), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def _book_budget():
    """从尺的源码里现取那枚常量，不手抄数字进牙。"""
    payload = ast.parse((REPO / TOOL).read_text(encoding="utf-8"))
    for node in ast.walk(payload):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "HAND_COPY_BUDGET":
            return node.value.value
    raise AssertionError("读不到棘轮常量，牙拒绝猜")


def test_the_cli_exits_zero_within_and_four_over(tmp_path):
    """两态都要量：线以下绿、线以上红，只测一面就是单面判据（原判据只测了红那一面）。"""
    root = make_scope(tmp_path)
    write(root / "tests" / "one.py", "X = " + repr(hand_copy_token()) + "\n")
    write(root / "tests" / "two.py", "Y = " + repr(hand_copy_token()) + "\n")
    budget = _book_budget()
    within = _run_cli(root, [])
    assert within.returncode == LINT.RC_CLEAN, within.stdout + within.stderr
    assert "现取=2" in within.stdout and "预算=" + str(budget) in within.stdout
    over = _run_cli(root, ["--budget", "1"])
    assert over.returncode == LINT.RC_OVER_BUDGET, over.stdout + over.stderr
    assert "判定=OVER" in over.stdout and "预算=1" in over.stdout
    assert "越界文件=2" in over.stdout, over.stdout

def test_an_empty_scope_aborts_with_a_named_rc(tmp_path):
    out = subprocess.run([sys.executable, str(REPO / TOOL), "--check",
                        "--root", str(tmp_path)], cwd=str(REPO),
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert out.returncode == LINT.RC_NO_SCOPE, out.stdout + out.stderr
    assert "没在量东西" in out.stderr