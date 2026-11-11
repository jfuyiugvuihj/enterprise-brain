# -*- coding: utf-8 -*-
"""R400 · 派生账的两把常驻牙：并树插行不许把它打烂，锚点改名不许让它出账。

病根（派工词点的那一族）：`64b3f3c`（R391）往 `app/api/v1/chat.py` 里加了 10 行，
上一班手抄在血缘表里的那批行号当场红 —— 施工在旧基点取行号，必被后续并树打红。
出路按 `00945a9`（R346）的手法：行号一律运行时派生。今天落地在
`scripts/r387_label_lineage.py::LINEAGE_SITES`（46 枚锚，`rg -F` 语义：逐行 strip 后连续固定串），
文档 §1 表那一格由 `--emit-doc-cells` 重落地。🔴 r346 与 r238 两枚件本件一个字都不碰。

R387 自己的逐跳钉（`tests/test_r387_label_ruler_teeth.py`）已经管"表与现读等不等"。
本件只补它没有的三枚形状：

① **插一整段还走得通吗**（K1 常驻化）：影子树里给 `chat.py` 上方插 500 行噪声 ⇒
   46 枚锚仍逐枚唯一命中；非 `chat.py` 的 cite 一字不变；`chat.py` 的 cite 整体 +500。
   ⇒ 重落地是纯机械，不需要任何人做行号算术。这同时是"容差不是替代品"的正证：
   容差会让整体 +6 悄悄**过关**，而表里那批数已经错了 6 行 —— 那是把假绿写进尺子。
② **只有真受影响的跳才咬**：同一棵影子上引用 `chat.py` 的跳应当红且红句带现读数，
   没引用的跳不许陪红（陪红＝信号作废）。
③ **锚点改名不许出账**（K2 常驻化）：把第 2 跳那一格的代码改个属性名 ⇒ 量具当场记
   `LINEAGE_ANCHOR_FAILURES`、`main()` 与 `--emit-doc-cells` 都在连库/出数之前 `rc=3`、
   stdout 一个字节都不出，表里那一格端失效标记而不是旧数。🔴 静默跳过算假绿。
④ **不许长回去**：这两枚件里读不出容差/豁免形状的旋钮，也读不出"±N"字样；
   `_one_hit` 的两条抛（0 枚、≥2 枚）按 AST 钉在，摘掉任何一条都红。

全程只在 `tmp_path` 的影子里变异，盘上一行都不改；不连库、不起服务、不打模型。
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

#: 逐跳那本账的解析器只有一枚：本件按名字 import 它，不另抄一份表解析（那是第二本账）。
import test_r387_label_ruler_teeth as teeth

REPO = Path(__file__).resolve().parents[1]
TOOL_REL = "scripts/r387_label_lineage.py"
TEETH_REL = "tests/test_r387_label_ruler_teeth.py"
DOC_REL = "docs/perf/r387-label-lineage-2026-09-27.md"
CHAT = "app/api/v1/chat.py"

#: 插多少行不重要，重要的是它比旧口径那 6 行容差大 —— 500 是 R346 用过的同一把尺寸。
SHIFT = 500
PAD = "# R400-K1 影子噪声行，只活在 tmp_path 里"

#: 被禁的旋钮形状。名字要整枚相等才算（`INDEX_STATUS_EXCLUDED` 那种在册符号不是豁免）。
#: 常量用拼接写出来，免得本件自己的文本撞上自己的扫描。
BANNED_NAMES = {"tolerance", "window", "within", "slack", "fudge", "offset_ok",
                "allow" + "_list", "allowlist", "ex" + "empt", "exemptions",
                "ex" + "clude", "ig" + "nore", "skip_ids"}
PLUS_MINUS = chr(0x00b1)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, "无法加载量具：" + str(path)
    module = importlib.util.module_from_spec(spec)
    #: frozen dataclass 要回查 sys.modules[cls.__module__]，手工 importlib 不注册就炸。
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_shadow(path: Path, name: str, root: Path):
    """加载影子量具，并把它 import 期推下去的东西收回来。

    量具自己会在 import 时 `sys.path.insert(0, ROOT)`，影子的 ROOT 是 tmp 目录；
    不收口的话，同一枚 pytest worker 里后到的 `import app...` 会命中影子那枚**桩件**
    （它 `open_connection` 是直接 raise 的），把别人的件变成假红。收工顺序：先摘路径，
    再按 `__file__` 落在影子里这一条判据摘模块 —— 真 `app/**` 已经在 sys.modules 里的不动。
    """
    before = list(sys.path)
    loaded = {}
    try:
        module = _load(path, name)
        for key, value in list(sys.modules.items()):
            filename = getattr(value, "__file__", "") or ""
            if key.split(".")[0] == "app" and str(root) in Path(filename).as_posix():
                loaded[key] = value
        return module
    finally:
        sys.path[:] = before
        for key in loaded:
            sys.modules.pop(key, None)


TOOL = _load(REPO / TOOL_REL, "r400_lineage_tool")


def cited_files() -> list:
    return sorted({site[0] for site in TOOL.LINEAGE_SITES.values()})


def cite_value(key: str, root: Path) -> str:
    """把一枚锚解成表里那种写法：单行就 `123`，跨行就 `123-456`。"""
    _file, first, last = TOOL.resolve_site(key, root)
    return str(first) if first == last else "%d-%d" % (first, last)


def today_cells() -> dict:
    return {key: cite_value(key, REPO) for key in TOOL.LINEAGE_SITES}


def rendered_cell(seq: int, root: Path) -> str:
    """按模板渲染某一跳的 site 格：与量具渲染文档表走的是同一条路，不抄第二份。"""
    keys = teeth.hop_keys(seq)
    return TOOL.HOP_DOC_CELLS[seq].format_map({key: cite_value(key, root) for key in keys})


# ------------------------------------------------------------------ 影子树夹具

@pytest.fixture()
def shadow(tmp_path: Path) -> Path:
    """把被引文件按字节搬进 tmp 再叠变异：盘上那一棵一个字都不动。"""
    root = tmp_path / "shadow"
    (root / "scripts").mkdir(parents=True)
    (root / "docs" / "perf").mkdir(parents=True)
    (root / TOOL_REL).write_bytes((REPO / TOOL_REL).read_bytes())
    (root / DOC_REL).write_bytes((REPO / DOC_REL).read_bytes())
    for rel in cited_files():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO / rel).read_bytes())
    #: 量具 import 期就要那枚唯一边界：影子里放一枚同签名桩，本件因此一律不碰库。
    for pkg in ("app", "app/db"):
        (root / pkg).mkdir(parents=True, exist_ok=True)
        (root / pkg / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "db" / "connection.py").write_text(
        "def open_connection(settings):\n"
        "    raise RuntimeError('影子树不连库')\n\n"
        "def parse_database_settings(url):\n"
        "    return url\n", encoding="utf-8")
    return root


def pad_top(root: Path, rel: str) -> None:
    path = root / rel
    body = path.read_bytes().decode("utf-8")
    path.write_bytes(((PAD + "\r\n") * SHIFT + body).encode("utf-8"))


# ------------------------------------------------------------------ ① ② K1 插行

def test_the_ledger_is_unique_on_the_pristine_tree() -> None:
    """开工前提：今天的树上 46 枚锚逐枚唯一命中，锚失效清单为空。"""
    assert len(TOOL.LINEAGE_SITES) >= 40, "锚块比血缘表还短：那是删了格没删引用"
    assert not TOOL.LINEAGE_ANCHOR_FAILURES, "锚失效清单不为空：" + str(TOOL.LINEAGE_ANCHOR_FAILURES)


def test_a_bulk_insertion_above_the_sites_keeps_every_anchor_unique(shadow: Path) -> None:
    """🔴 插 500 行之后 46 枚锚仍逐枚唯一命中：派生账吃得住"并树把文件撑长"这一族。"""
    pad_top(shadow, CHAT)
    _cites, failures = TOOL.resolve_cites(shadow)
    assert not failures, "插行之后锚读不出了：" + str(failures)


def test_the_shift_lands_on_exactly_the_cited_file_and_is_mechanical(shadow: Path) -> None:
    """🔴 只有被插那枚文件的 cite 动，且动的量 == 插的行数：重落地不需要任何算术。

    这一枚就是"抄来的行号必被后续并树打红"的正面解法 —— 数从来就不是人写的，
    所以并树撑长文件时没有一处需要人来改。
    """
    before = today_cells()
    pad_top(shadow, CHAT)

    def shift(cell: str) -> str:
        return re.sub(r"\d+", lambda match: str(int(match.group(0)) + SHIFT), cell)

    moved = kept = 0
    for key, value in before.items():
        fresh = cite_value(key, shadow)
        if TOOL.LINEAGE_SITES[key][0] == CHAT:
            assert fresh == shift(value), key + "：插行后现读 " + fresh + "，应为 " + shift(value)
            moved += 1
        else:
            assert fresh == value, key + "：没被插行的 cite 自己动了 " + value + " -> " + fresh
            kept += 1
    assert moved >= 8, "只有 " + str(moved) + " 格 cite 跟着动：这一族今天没在量东西"
    assert kept >= 20, "受检的非插行 cite 只有 " + str(kept) + " 格，不足以免于巧合"


def test_only_the_hops_that_cite_the_shifted_file_go_red(shadow: Path) -> None:
    """🔴 表没重落地时该红的才红，红的那几跳必须端得出现读数。

    陪红等于把信号作废一遍：某一枚锚漂了，只该打红引用它的那几跳 —— 上一班那三枚红
    就是靠"整表全红 + 一句行号必须重取"把这件事糊过去的。
    """
    printed = teeth.doc_lineage_cells()
    pad_top(shadow, CHAT)
    chat_hops = {seq for seq in printed if CHAT in rendered_cell(seq, shadow) or CHAT in printed[seq]}
    for seq in sorted(printed):
        derived = rendered_cell(seq, REPO)
        if seq in chat_hops:
            stale = rendered_cell(seq, shadow)
            assert stale != printed[seq], (
                "第 " + str(seq) + " 跳引用了被插行的文件，表里却还判同值：这格的牙是装饰")
            assert printed[seq] == derived, (
                "第 " + str(seq) + " 跳：影子之外的表与本件重解的现读都不等，本件口径已腐")
        else:
            assert printed[seq] == rendered_cell(seq, shadow), (
                "第 " + str(seq) + " 跳没引用被插行的文件，却在插行后红了：陪红")


# ------------------------------------------------------------------ ③ K2 改名

def test_a_renamed_anchor_site_is_named_not_skipped(shadow: Path,
                                                   capsys: pytest.CaptureFixture) -> None:
    """🔴 把锚点那一格改个属性名：量具必须点名、不许出数、连库之前 ABORT。

    派工词那句"静默跳过算假绿，比红更坏"就是这个形状：取第一次命中、悄悄留旧数、
    或者干脆少一行不吭声，三种都比当场红坏。这里一起钉住。
    """
    path = shadow / CHAT
    body = path.read_bytes().decode("utf-8")
    anchor_line = TOOL.LINEAGE_SITES["hop2"][1][1][0]
    assert body.count(anchor_line) == 1, "影子树里那一格不唯一，本刀白插"
    path.write_bytes(body.replace(anchor_line,
                                  anchor_line.replace('"department"', '"dept"')).encode("utf-8"))
    stale = cite_value("hop2", REPO)

    tool = _load_shadow(shadow / TOOL_REL, "r400_shadow_tool_k2", shadow)
    assert tool.LINEAGE_ANCHOR_FAILURES, "锚已腐，量具却一声不吭：这就是假绿"
    assert any("hop2" in item for item in tool.LINEAGE_ANCHOR_FAILURES), str(tool.LINEAGE_ANCHOR_FAILURES)

    with pytest.raises(tool.AnchorNotUnique) as err:
        tool.resolve_site("hop2", shadow)
    assert "命中 0 枚" in str(err.value), str(err.value)

    code = tool.main(["--no-db", "--documents-dir", str(shadow)])
    caught = capsys.readouterr()
    assert code == 3, "带着腐锚出了账，rc = " + str(code) + "（定案要 ABORT 的那一枚）"
    assert not caught.out.strip(), "ABORT 之前 stdout 还吐了数：腐锚被当成读数交了出去"
    assert "ABORT" in caught.err and "hop2" in caught.err, caught.err
    #: 表里印的是渲染后的那一格（`HOP_DOC_CELLS` 是带占位符的模板，不是成品）。
    cell = tool.LINEAGE_DOC_CELLS[2]
    assert "<锚失效:hop2>" in cell, "表里那一格退回了旧数：" + cell
    assert stale not in cell, "腐锚那一格还把上一班的行号端了出去"


def test_the_emit_command_refuses_to_number_a_rotten_anchor(shadow: Path,
                                                            capsys: pytest.CaptureFixture) -> None:
    """重落地那条腿也拿不到数：同一棵腐锚影子里 `--emit-doc-cells` 一样 rc=3。

    钉的是"改表只有一处可改"这句话真成立 —— 它不会在你看不见的地方把旧数写回表里。
    """
    path = shadow / CHAT
    body = path.read_bytes().decode("utf-8")
    anchor_line = TOOL.LINEAGE_SITES["hop5f"][1][1][0]
    assert body.count(anchor_line) == 1, "影子树里那一格不唯一，本刀白插"
    path.write_bytes(body.replace(anchor_line, anchor_line.replace("classification", "classifxn")).encode("utf-8"))

    tool = _load_shadow(shadow / TOOL_REL, "r400_shadow_tool_emit", shadow)
    code = tool.main(["--emit-doc-cells"])
    caught = capsys.readouterr()
    assert code == 3, "rc = " + str(code) + "：腐锚还能出表？"
    assert "ABORT" in caught.err and "hop5f" in caught.err, caught.err
    assert cite_value("hop2", shadow) == cite_value("hop2", REPO), "只改了第 5 跳，第 2 跳的锚不该一起腐"


# ------------------------------------------------------------------ ④ 不许长回去

def executable_strings(tree: ast.AST) -> list:
    """可执行字符串常量：docstring 不算 —— 讲这段历史的散文允许写那两个符号。"""
    doc_nodes = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            head = body[0]
            if isinstance(head, ast.Expr) and isinstance(head.value, ast.Constant) \
                    and isinstance(head.value.value, str):
                doc_nodes.add(id(head.value))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_nodes]


def names_in(tree: ast.AST) -> set:
    found = set()
    for node in ast.walk(tree):
        for attribute in ("id", "attr", "arg"):
            value = getattr(node, attribute, None)
            if isinstance(value, str):
                found.add(value)
        if isinstance(node, ast.keyword) and node.arg:
            found.add(node.arg)
    return found


def anchor_guards(tree: ast.AST, function: str) -> list:
    """枚枚 `if ...: raise AnchorNotUnique(...)`：抛挂在哪一条件上，才是这条牙的本体。"""
    body = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function)
    guards = []
    for node in ast.walk(body):
        if not isinstance(node, ast.If):
            continue
        if any(isinstance(child, ast.Raise) and isinstance(child.exc, ast.Call)
               and getattr(child.exc.func, "id", "") == "AnchorNotUnique" for child in ast.walk(node)):
            guards.append(ast.unparse(node.test))
    return guards


@pytest.mark.parametrize("rel", [TOOL_REL, TEETH_REL], ids=lambda rel: Path(rel).name)
def test_no_tolerance_or_exemption_knob_survives_in_the_ledger_files(rel: str) -> None:
    """🔴 反退化的闸：这两枚件里不许再长出"容差 / 豁免清单"那一类旋钮。

    病是这么来的：容差让 6 行以内的漂移**静默过关**，于是表里那批数悄悄过期，
    攒到 10 行才红 —— 红的时候已经没人记得哪一格对哪一格（R391 就是这么打的）。
    派生化之后没有这个旋钮；本闸保证下一班也不会为省事把它加回来。
    """
    tree = ast.parse((REPO / rel).read_bytes().decode("utf-8"))
    bad_names = sorted(BANNED_NAMES & names_in(tree))
    plusminus = [value[:56] for value in executable_strings(tree) if PLUS_MINUS in value]
    assert not bad_names, rel + " 里长出容差/豁免形状的旋钮：" + str(bad_names)
    assert not plusminus, rel + " 的可执行字符串里又出现 ± 口径：" + str(plusminus)


def test_the_no_first_hit_branches_are_both_still_there() -> None:
    """`_one_hit` 的两条抛（0 枚 / ≥2 枚）一枚都不许摘：摘掉任何一条就是"取第一次命中"。"""
    tree = ast.parse((REPO / TOOL_REL).read_bytes().decode("utf-8"))
    conditions = anchor_guards(tree, "_one_hit")
    assert len(conditions) >= 2, (
        "抛只剩 " + str(len(conditions)) + " 枚：腐锚或撞锚有一条被悄悄放过了")
    assert any(text == "not hits" for text in conditions), conditions
    assert any(text == "len(hits) > 1" for text in conditions), conditions


def first_number(cell: str) -> int:
    return int(re.search(r"\d+", cell).group(0))


@pytest.mark.parametrize("drift", [1, 3, 6, 7, 10])
def test_a_tolerance_ruler_lets_a_small_drift_pass_while_the_table_lies(tmp_path: Path,
                                                                        drift: int) -> None:
    """🔴 本班为什么没有"容差"这个旋钮：同一批真锚、同一棵影子树，两种口径各量一遍。

    旧 `±6` 那族口径在漂移 1..6 行时**放绿**，而文档表里那批数已经错着同样多行 ——
    它就是"表在说谎、门是绿的"那台发生器。R391 的 `+10` 之所以终于报出来，不是因为
    量具懂了什么，只是因为它越过了容差。派生口径两边都真：锚照旧唯一命中，
    表与现读不等就当场红，并且红句直接端出新数（另两枚钉在 R387 的件里）。
    """
    root = tmp_path / "s"
    (root / CHAT).parent.mkdir(parents=True, exist_ok=True)
    (root / CHAT).write_bytes(("# R400 影子行\r\n" * drift
                               + (REPO / CHAT).read_bytes().decode("utf-8")).encode("utf-8"))
    keys = [key for key, (file, _start, _end) in TOOL.LINEAGE_SITES.items() if file == CHAT]
    assert len(keys) >= 8, "只有 " + str(len(keys)) + " 枚 chat 锚，本枚无从对照"
    passes = [abs(first_number(cite_value(key, root)) - first_number(cite_value(key, REPO))) <= 6
              for key in keys]
    lies = [cite_value(key, root) != cite_value(key, REPO) for key in keys]
    assert all(lies), "派生口径没看见漂移：那它也不是牙"
    assert all(passes) is (drift <= 6), (drift, passes)
