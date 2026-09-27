# -*- coding: utf-8 -*-
r"""R346：那本按行号钉的账改由符号账现算，并且当场抓下一位。

病灶（逐条实测，不采信自述）：``tests/test_r238_bare_connect_ratchet.py`` 里 R254 事故重放那枚
用例，旧 :540 拿"现场扫描 + 行号口径"比 ``LEGACY_LINE_LEDGER``——十五枚**手抄**的 ``path:line``。
R330 并树（eec7ced）在 ``app/common/monitoring.py::_probe_postgres`` 上方进了 21 行，``:381``
漂成 ``:402`` ⇒ 开工时那件 ``1 failed / 32 passed``，从 09-26 挂到 09-27，两班都没点过
``test_r238``（本仓一天内第二枚"门红了两班没人发现"，第一枚是 R339 @957c7d2）。同笔抓到第二枚
同类雷：``test_the_real_prose_site_is_not_double_counted`` 手抄 ``auth.py:301``（正向半句：有人
加一行就假红）与 ``auth.py:364``（负向半句：行号一漂就成永真）。

修法（结构性出路 a + b，都不靠改数字）：活的那本行号账由符号账现算（``line_ledger()``）；手抄
十五格降级为纯历史 ``HISTORICAL_LINE_LEDGER``，只被 ``drift_report()`` 逐格回答"哪个文件哪一格
漂了几行"，不再进任何断言。三枚硬钉与"插 481 行旧账必红"那出戏一格没松。本件是它的看守：

  ① 两腿互校：``line_ledger()``（符号身份 → 现场 → 行号）与 ``readings(..., line_number_identity)``
     （落点 → 行号）必须给出同一批格子。两条腿互相算不出对方，所以相等不是同义反复。
  ② 历史账逐格归得着人：路径必须仍是那枚符号身份所在的文件；漂多少都允许，说不通（现场扫不到、
     或那一枚跑到别的文件去了）就点名报，不许退化成"集合不等"。
  ③ 任何被记账文件正上方插 500 行 ⇒ 符号账一字未动、三枚硬钉绿、行号账自己跟上、漂移报告报得出
     新位置；同一轮里再拿"插行之前的现场"比"插行之后的现场"，必须看见旧口径少一格、多一格
     ——那句"必然对不上"只能由现场比现场说，不能由手抄历史说（15 枚逐文件参数化）。
  ④ 更狠的一枚：把棘轮**整件**（30 枚裸用例 + 3 枚参数化 = 33 个实例）搬到被插了 500 行的树上跑一遍，
     今天零失败。以后谁再往那件里抄一枚行号进断言，不必等下一班并树，本枚当场点名。
  ⑤ 反证全部落地成用例，不是"应该会红"：把派生腿换成一份**手抄的今天**⇒ 事故重放与两腿互校一起红
     （要证的是"手抄"本身不行，不是"09-26 那几个数不行"）；只把漂了那一格改成今天的数 ⇒ 今天
     对得上，再插一行就红（同一枚雷换引信）；把 ``line_number_identity`` 与 ``ledger_identity``
     悄悄合一 ⇒ 事故重放与两腿互校一起红。
  ⑥ 静态三枚：两本件里唯一允许出现的裸 ``path:line`` 字面量只能是那十五枚历史记录；历史记录这个
     符号在棘轮件里只许被 ``drift_report()`` 读；两本件的任何断言都不许把历史账与现场读数放进
     同一枚 Compare——**等号与不等号都算**（``!=`` 今天恒真，一次大段删除就把它变成新的假红），
    改名也躲不过：``FORGED = set(HISTORICAL)`` 这一腿是第二班自查时实测到的漏（X5），已补。

第二班（同日退回后重做）记一笔，因为这枚件自己差点又变成病灶：上一版 ``:313`` 那枚反证钉写的是
"把基点手抄的十五格改掉 monitoring 那一格，再与今天的现场相等"，R345 并树（``d4e5706``）在
``app/api/v1/alerts.py`` 上方进了几行，那格从 ``:45`` 漂到 ``:52``，**我自己的件**在主树 HEAD 上
炸成 ``Extra items ...:45 / ...:52``——基点绿、主树红，正是"把基点当事实"。所以 ⑤ 里两枚手抄账
现在一律从今天的现场派生再冻结（``today = readings(pristine, line_number_identity)``），
``HISTORICAL`` 在本件里只剩历史素材一个身份：读它、拿它造漂移样本、拿它讲地雷史，绝不进比对。

盘上一个字节都不动：所有变异都落在内存里的源码字典上（R253 的口径），本件对被跟踪文件零写口。
"""
import ast
import re
from functools import partial
from pathlib import Path

import pytest

#: 直接用 pytest 的名字导入那枚棘轮件：这样它的断言带重写（红的时候能看见两本账差在哪一格），
#: 本件也就不必自己再抄一份"为什么不等"的翻译。tests/ 由 conftest 拼进 sys.path。
import test_r238_bare_connect_ratchet as r238

REPO_ROOT = Path(__file__).resolve().parents[1]
SELF_PATH = Path(__file__).resolve()
RATCHET_PATH = Path(r238.__file__).resolve()
MONITORING = "app/common/monitoring.py"
MONITORING_IDENTITY = "app/common/monitoring.py::_probe_postgres#0"
PROBE_TARGETS = [MONITORING, "app/api/v1/chat.py"]
PAD = 500
BARE_CELL = re.compile(r"^[\w./+\-]+\.py:\d+$")
HISTORY_NAMES = {"HISTORICAL_LINE_LEDGER", "HISTORICAL", "LEGACY_LINE_LEDGER"}
LIVE_READINGS = {
    "readings",
    "line_ledger",
    "booked",
    "drift_report",
    "repo_sources",
    "scan_source",
    "splitlines",
    "read_text",
}
#: 豁免的形状用拼出来的常量：免得本件自己的源码文本撞上按 AST 取证的那枚扫描（判据⑤）。
SKIP_TAIL = ("skip", "skip" + "if", "x" + "fail")
LEDGER_ARGS = ("allow" + "_list", "ex" + "empt", "exemptions", "ignore", "exclude")

BASELINE = r238.BASELINE
HISTORICAL = r238.HISTORICAL_LINE_LEDGER
BOOKED_PATHS = tuple(sorted({entry.partition("::")[0] for entry in BASELINE}))

assert len(BASELINE) == len(HISTORICAL) == len(BOOKED_PATHS) == 15, BOOKED_PATHS
assert RATCHET_PATH.name == "test_r238_bare_connect_ratchet.py", RATCHET_PATH


@pytest.fixture(scope="module")
def pristine():
    """盘上这一棵的读数。变异一律 ``dict(sources, **{...})`` 往上叠，不回写。"""
    return r238.repo_sources()


def _crowd(sources, rel, count=PAD):
    """在 ``rel`` 那枚落点正上方插 ``count`` 行注释噪声（只在内存里）。交回 (新源码表, 被害者)。"""
    hits = sorted((hit for hit in r238.booked(sources).values() if hit.rel == rel),
                  key=lambda hit: hit.line)
    assert hits, rel
    victim = hits[0]
    return dict(sources, **{rel: r238._pad_above(sources[rel], victim.line, count, rel)}), victim


def _two_legs_agree(sources):
    """①两腿互校本身。把口径悄悄合一（⑤第三把）时，红的就是它。"""
    derived = set(r238.line_ledger(sources))
    direct = r238.readings(sources, identity=r238.line_number_identity)
    assert derived == direct, f"派生腿与原始腿对不上，差 {len(derived ^ direct)} 格：{sorted(derived ^ direct)}"
    return derived


def _ratchet_cases():
    """把棘轮件里每枚 ``test_*`` 摊平成 (标签, 无参可调用)：参数化那枚也要跑到，不许漏。"""
    cases = []
    for name, fn in sorted(vars(r238).items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        marks = [mark for mark in getattr(fn, "pytestmark", []) if mark.name == "parametrize"]
        assert len(marks) <= 1, f"{name} 的参数化形状超出本件的跑法"
        if not marks:
            assert fn.__code__.co_argcount == 0, (
                f"{name} 要 fixture，本件的跑法覆盖不到：把它改成自取参数，"
                "或在 _ratchet_cases() 里补一枚能喂 fixture 的跑法——别放行漏掉"
            )
            cases.append((name, fn))
            continue
        argnames, argvalues = marks[0].args
        assert isinstance(argnames, str) and "," not in argnames, argnames
        cases.extend((f"{name}[{value}]", partial(fn, **{argnames: value})) for value in argvalues)
    return cases


def _why(exc):
    """非重写路径上 ``AssertionError`` 可能不带正文：那就把出事那一行的原文交回去。"""
    text = str(exc).strip()
    if text:
        return text.splitlines()[0][:240]
    frame = exc.__traceback__
    while frame is not None and frame.tb_next is not None:
        frame = frame.tb_next
    if frame is None:
        return repr(exc)
    source = Path(frame.tb_frame.f_code.co_filename).read_text(encoding="utf-8").splitlines()
    return f"{frame.tb_frame.f_code.co_name}:{frame.tb_lineno} {source[frame.tb_lineno - 1].strip()}"


def _bare_cells_in(path):
    return [node.value for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and BARE_CELL.match(node.value)]


def _test_bodies_of(tree):
    return [node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")]


def _live_bound_names(body):
    """一枚函数体里"被现场读数喂出来的局部名字"（``rows = drift_report(...)`` 这种）。

    只看字面嵌套会漏：把现场读数先赋给一个局部变量，再拿它去比手抄历史，形状一模一样。
    """
    bound = set()
    for node in ast.walk(body):
        if not isinstance(node, ast.Assign):
            continue
        _names, calls = _names_and_calls(node.value)
        if calls & LIVE_READINGS:
            bound.update(target.id for target in node.targets if isinstance(target, ast.Name))
    return bound


def _history_aliases(tree):
    """历史账的**别名闭包**：``FORGED = set(HISTORICAL)`` 这类改名后的手抄账也算历史侧。

    判据③自查时实测到的漏：尺子原来只认 ``HISTORY_NAMES`` 里那几个字面符号名，给那本账改个
    名就从尺子底下走过去了。所以先对整件跑一次赋值传播（迭代到不动点），再拿去判 Compare。
    """
    known = set(HISTORY_NAMES)
    while True:
        grown = set(known)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            used = {child.id for child in ast.walk(node.value) if isinstance(child, ast.Name)}
            if used & known:
                grown.update(target.id for target in node.targets if isinstance(target, ast.Name))
        if grown == known:
            return known - HISTORY_NAMES
        known = grown


def _names_and_calls(node):
    names, calls = set(), set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Call):
            target = child.func
            if isinstance(target, ast.Attribute):
                calls.add(target.attr)
            elif isinstance(target, ast.Name):
                calls.add(target.id)
    return names, calls


# --------------------------------------------------------------------------- ① 派生腿
def test_the_line_ledger_is_derived_from_the_symbol_ledger(pristine):
    """行号账每一格都由符号身份现算：两条腿互相算不出对方，所以相等是真判据。"""
    cells = r238.line_ledger(pristine)
    sites = r238.booked(pristine)

    assert len(cells) == len(BASELINE) == 15, sorted(cells)
    assert cells == {sites[entry].location: entry for entry in BASELINE}, sorted(cells.items())
    assert _two_legs_agree(pristine) == set(cells)
    assert all("::" in entry for entry in BASELINE), BASELINE
    assert all(re.search(r":\d+$", location) for location in cells), sorted(cells)


def test_the_line_ledger_follows_a_site_it_must_book(pristine):
    """派生腿认现场不认抄数：那一枚被顶下去 500 行，账上那一格跟着搬，别格一格不动。"""
    before = r238.line_ledger(pristine)
    crowded, victim = _crowd(pristine, MONITORING)
    after = r238.line_ledger(crowded)
    moved_key = f"{MONITORING}:{victim.line + PAD}"

    assert after[moved_key] == victim.identity, sorted(after)
    assert moved_key not in before
    assert {key: value for key, value in after.items() if not key.startswith(f"{MONITORING}:")} == {
        key: value for key, value in before.items() if not key.startswith(f"{MONITORING}:")
    }


# --------------------------------------------------------------------------- ② 历史账逐格可解释
def test_the_historical_record_still_explains_every_cell(pristine):
    """十五格历史逐格归得着人：路径一致、身份在账、今天的行号是现算的（允许漂，不许说不通）。"""
    rows = r238.drift_report(pristine)
    sites = r238.booked(pristine)

    assert len(rows) == len(BASELINE)
    assert [row["identity"] for row in rows] == list(BASELINE)
    # 每一格报回来的历史格子，路径必须就是它那枚符号身份所在的文件：两侧都是历史素材，不碰现场
    for row in rows:
        assert row["cell"].startswith(row["identity"].partition("::")[0] + ":"), row
    for row in rows:
        hit = sites[row["identity"]]
        assert row["path"] == hit.rel == row["identity"].partition("::")[0], row
        assert (row["line"], row["drift"]) == (hit.line, hit.line - row["recorded"]), row

    drifted = r238.drift_lines(rows)
    assert len(drifted) == sum(1 for row in rows if row["drift"]), drifted
    for row in rows:
        if not row["drift"]:
            continue
        line = next(item for item in drifted if row["identity"] in item)
        assert str(row["recorded"]) in line and str(row["line"]) in line, line
        assert f"{row['drift']} 行" in line, line


def test_a_cell_that_cannot_be_explained_is_named_not_just_unequal(pristine):
    """②要的那句"哪个文件哪一格"：真迁走一枚而不删账，报的是那一格，不是一片集合不等。

    报文里只认**不会漂的东西**：身份与路径。那一格今天在第几行是现场量，拿它去比报文（报文
    里躺着的是历史记数）就是 R346 的病灶本身，本枚因此不写这种断言。
    """
    rel = "app/common/auth.py"
    victim = next(hit for hit in r238.booked(pristine).values() if hit.rel == rel)
    migrated = dict(pristine, **{rel: r238._migrate(pristine[rel], victim.line)})

    with pytest.raises(AssertionError) as excinfo:
        r238.drift_report(migrated)
    message = str(excinfo.value)
    assert "说不通" in message and victim.identity in message, message
    assert f"{rel}:" in message, message
    assert "Extra items" not in message, message

    with pytest.raises(AssertionError) as excinfo:
        r238.line_ledger(migrated)
    assert victim.identity in str(excinfo.value), str(excinfo.value)


def test_the_drift_report_tolerates_a_shift_it_can_explain(pristine):
    """漂移容差不是照着 :381→:402 调出来的：整体再挪 37 行仍然一格不红，只报得出 -37。"""
    sites = r238.booked(pristine)
    exact = tuple(sites[identity].location for identity in BASELINE)
    future = tuple(f"{loc.rpartition(':')[0]}:{int(loc.rpartition(':')[2]) + 37}" for loc in exact)
    rows = r238.drift_report(pristine, historical=future)

    assert [row["drift"] for row in rows] == [-37] * 15, rows
    report = "\n".join(r238.drift_lines(rows))
    assert len(r238.drift_lines(rows)) == 15 and "-37 行" in report and MONITORING in report, report
    assert [row["cell"] for row in rows] == list(future)

    # 反过来也一样：把历史账整体换成"今天的位置"，就没有任何一格需要报漂
    assert r238.drift_lines(r238.drift_report(pristine, historical=exact)) == []


def test_two_histories_that_stay_unaligned_are_reported_as_such(pristine):
    """历史与符号账不同序 / 逐格错位：报"该怎么补"，不许静默少比一格或比错人。"""
    with pytest.raises(AssertionError) as excinfo:
        r238.drift_report(pristine, historical=HISTORICAL[:-1])
    message = str(excinfo.value)
    assert "不同序" in message and "删一行就绿" in message, message

    wrong = HISTORICAL[:-1] + (MONITORING + ":1",)
    with pytest.raises(AssertionError) as excinfo:
        r238.drift_report(pristine, historical=wrong)
    assert "逐格错位" in str(excinfo.value), str(excinfo.value)


# --------------------------------------------------------------------------- ③④ 插 500 行
@pytest.mark.parametrize("rel", BOOKED_PATHS)
def test_five_hundred_lines_above_a_booked_file_keeps_the_gate_green(rel, pristine):
    """判据③④：任何被跟踪的记账文件上方进 500 行 ⇒ 账自己跟上，并且报得出去向。

    "默默红成一堆集合不等"不接受：这里既没有集合不等（三枚硬钉全绿、符号账一字未动），
    也有原因（``drift_report`` 说得出那一格今天在第几行、净漂几行）。
    """
    crowded, victim = _crowd(pristine, rel)
    moved = r238.booked(crowded)

    assert set(moved) == set(BASELINE), sorted(moved.keys() ^ set(BASELINE))
    r238._all_three_green(crowded)
    assert moved[victim.identity].line == victim.line + PAD, moved[victim.identity]
    assert _two_legs_agree(crowded) == set(r238.line_ledger(crowded))

    row = next(item for item in r238.drift_report(crowded) if item["path"] == rel)
    report = "\n".join(r238.drift_lines(r238.drift_report(crowded)))
    assert row["line"] == victim.line + PAD, row
    assert rel in report and str(row["line"]) in report and f"{row['drift']} 行" in report, report

    # 行号口径此刻确实变了：少一格、多一格，少的正是被害者原来那一格。这句是"现场 vs 现场"，
    # 不是"现场 vs 手抄历史"——后者本身就会漂，漂了就变成我上一班犯的那枚假红。
    before = r238.readings(pristine, identity=r238.line_number_identity)
    direct = r238.readings(crowded, identity=r238.line_number_identity)
    assert direct != before
    assert before - direct == {f"{rel}:{victim.line}"}, (rel, sorted(before ^ direct))
    assert direct - before == {f"{rel}:{victim.line + PAD}"}, (rel, sorted(before ^ direct))


@pytest.mark.parametrize("target_rel", PROBE_TARGETS)
def test_the_whole_ratchet_still_passes_on_a_tree_that_gained_five_hundred_lines(
    target_rel, pristine, monkeypatch
):
    """判据④正面答案：整件棘轮搬到"某文件上方多了 500 行"的树上，今天必须零失败。

    这枚就是"抓下一位"的那只手：以后谁再往 ``test_r238_*`` 里抄一枚行号进任何断言，不必等
    下一班并树，本枚当场点名。上一班那 21 行要是撞上它，红的是这一枚。
    """
    crowded, victim = _crowd(pristine, target_rel)
    cases = _ratchet_cases()
    assert len(cases) >= 33, [label for label, _ in cases]  # 30 枚裸用例 + 3 枚参数化

    monkeypatch.setattr(r238, "repo_sources", lambda: crowded)
    failed = []
    for label, run in cases:
        try:
            run()
        except Exception as exc:  # noqa: BLE001 —— 任何一枚出事都要进读数，静默即漏判
            failed.append(f"{label}: {_why(exc)}")

    assert not failed, (
        f"{victim.location} 被 500 行噪声顶到 :{victim.line + PAD} 之后仍然红，"
        f"棘轮里这些用例在拿会漂的东西当判据：\n  " + "\n  ".join(failed)
    )


# --------------------------------------------------------------------------- ⑤ 反证落地
@pytest.mark.parametrize("target_rel", PROBE_TARGETS)
def test_a_hand_copied_ledger_reddens_the_replay_and_the_cross_check(target_rel, pristine, monkeypatch):
    """⑤第一把：把派生腿摘掉、换成一份**手抄的今天**⇒ 事故重放与两腿互校一起红。

    为什么手抄今天而不是抄历史上那十五格：那本"完美的今日手抄账"在今天的树上完全正确，
    它照样会在下一枚并树红——要证的是"手抄"这件事本身不行，不是"09-26 那几个数不行"。
    """
    crowded, _victim = _crowd(pristine, target_rel)
    today = r238.readings(pristine, identity=r238.line_number_identity)
    hand = {cell: cell.partition(":")[0] for cell in today}
    assert set(hand) == today, sorted(set(hand) ^ today)  # 手抄今天当然对得上：价值全在下面两步

    monkeypatch.setattr(r238, "repo_sources", lambda: crowded)
    monkeypatch.setattr(r238, "line_ledger", lambda sources, baseline=None: dict(hand))
    with pytest.raises(AssertionError):
        r238.test_the_r254_incident_replays_green_under_the_new_ledger_and_red_under_the_old()
    with pytest.raises(AssertionError):
        _two_legs_agree(crowded)


@pytest.mark.parametrize("target_rel", PROBE_TARGETS)
def test_editing_the_number_instead_of_deriving_it_defers_the_same_red(target_rel, pristine):
    """⑤第二把：只把漂了的那一格改成今天的数，不算修好——它只是把同一枚红推给下一位。

    这份"改口以后的手抄账"同样从今天的现场派生（``today``），不从任何基点字面量来：上一班
    我就是拿基点抄来的十五格去比主树现场，R345 在 ``alerts.py`` 上方进了几行，那枚反证钉
    自己先炸成 ``:45 vs :52``——门里最坏的一种红：它长得像别人的错。
    """
    hand = set(r238.readings(pristine, identity=r238.line_number_identity))
    assert hand == r238.readings(pristine, identity=r238.line_number_identity)

    crowded, victim = _crowd(pristine, target_rel)
    deferred = r238.readings(crowded, identity=r238.line_number_identity)

    assert hand != deferred
    assert hand - deferred == {f"{victim.rel}:{victim.line}"}, (victim, sorted(hand ^ deferred))
    assert deferred - hand == {f"{victim.rel}:{victim.line + PAD}"}, (victim, sorted(hand ^ deferred))
    assert _two_legs_agree(crowded) == deferred


def _raises(run):
    """跑一枚用例，只问它红没红（正文交给调用方自己去截）。"""
    try:
        run()
    except Exception:  # noqa: BLE001 —— 这里要的就是"出事"这件事本身
        return True
    return False


def test_quietly_merging_the_two_identities_reddens_replay_and_cross_check(pristine, monkeypatch):
    """⑤第三把：``line_number_identity`` 悄悄等于 ``ledger_identity`` ⇒ 事故重放与互校一起红。"""
    assert r238.line_number_identity is not r238.ledger_identity
    probe = r238.booked(pristine)[MONITORING_IDENTITY]
    assert r238.line_number_identity(*probe[:5]) != r238.ledger_identity(*probe[:5])

    monkeypatch.setattr(r238, "line_number_identity", r238.ledger_identity)
    with pytest.raises(AssertionError):
        r238.test_the_r254_incident_replays_green_under_the_new_ledger_and_red_under_the_old()
    with pytest.raises(AssertionError) as excinfo:
        _two_legs_agree(pristine)
    assert "派生腿与原始腿对不上" in str(excinfo.value), str(excinfo.value)

    # 合一以后红的不止这一枚：整件棘轮里靠"两种身份不一样"活着的那几枚一起倒下，读数记在交回里
    red = [label for label, run in _ratchet_cases() if _raises(run)]
    assert "test_the_r254_incident_replays_green_under_the_new_ledger_and_red_under_the_old" in red, red


def test_the_r254_replay_demo_itself_still_has_its_teeth(pristine, monkeypatch):
    """判据③：那出戏还得能实测出来——插 481 行 ⇒ 行号身份红、符号身份绿。本枚亲自跑一遍。"""
    monkeypatch.setattr(r238, "repo_sources", lambda: pristine)
    r238.test_the_r254_incident_replays_green_under_the_new_ledger_and_red_under_the_old()


# --------------------------------------------------------------------------- ⑥ 静态：不许再抄
@pytest.mark.parametrize("path", [RATCHET_PATH, SELF_PATH])
def test_the_only_bare_line_cells_left_are_the_historical_record(path):
    """两本件里裸 ``path:line`` 字面量只许是那十五枚历史：再抄一枚进代码就是判据②禁的交差。"""
    cells = _bare_cells_in(path)

    assert set(cells) <= set(HISTORICAL), sorted(set(cells) - set(HISTORICAL))
    if path == RATCHET_PATH:
        assert sorted(cells) == sorted(HISTORICAL), sorted(cells)
    else:
        assert cells == [], cells


def test_the_historical_record_is_read_by_drift_report_alone():
    """历史记录在棘轮件里只许被 ``drift_report()`` 读：进任何别处（尤其断言）都是拿历史比现场。

    本件不在这枚钉的范围里：它拿历史账当**探针输入**（造漂移、造错位、造"手改数字"的对照），
    那类用法染不红门；真正禁的"现场读数 == 抄下来的数"由下面那枚按 Compare 钉。
    """
    tree = ast.parse(RATCHET_PATH.read_text(encoding="utf-8"))
    readers = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        loaded = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
        if loaded & HISTORY_NAMES:
            readers.append(node.name)

    assert readers == ["drift_report"], readers


def test_no_test_here_compares_a_live_reading_with_the_history():
    """两本件都不许再出现"冻结的字面量 ⟷ 今天的现场"这种比对，等号与不等号一律算。

    判据③的形状自查：一枚 Compare 里只要一侧出现历史账符号（``HISTORICAL`` 那族名字），
    另一侧出现现场读数调用（``readings`` / ``line_ledger`` / ``booked`` / ``splitlines``
    / ``read_text`` 这一族）、**或者出现被现场读数喂出来的局部变量**，当场红。两层都要：
    上一版我把现场读数先赋给局部变量再去比历史账，只盯字面嵌套的尺子量不到。
    为什么连 ``!=`` 也禁：不等号今天恒真，一次大段删除就能把它变成假红——同一枚病换个方向发作。
    """
    offenders = [f"{path.name} 的 {item}"
                 for path in (RATCHET_PATH, SELF_PATH)
                 for item in _history_live_compares(path.read_text(encoding="utf-8"))]

    assert offenders == [], f"这些断言又在拿历史记录比现场读数（两侧都不许）：{offenders}"


def _history_live_compares(source: str):
    """形状规则本身（跑在任意源码文本上）：交回"函数名:行号"清单。

    历史侧认"字面符号名 + 别名闭包"，现场侧认"读数调用 + 被读数喂出来的局部变量"，两层都要。
    """
    found = []
    tree = ast.parse(source)
    history = HISTORY_NAMES | _history_aliases(tree)
    for function in _test_bodies_of(tree):
        live_names = _live_bound_names(function)
        for compare in (node for node in ast.walk(function) if isinstance(node, ast.Compare)):
            names, calls = _names_and_calls(compare)
            if names & history and (calls & LIVE_READINGS or names & live_names):
                found.append(f"{function.name}:{compare.lineno}")
    return found


#: 五种形状，尺子必须量出前四种、放过最后一种。
SHAPE_DIRECT = """def test_direct():
    assert set(HISTORICAL) == readings(sources, identity=line_number_identity)
"""
SHAPE_INDIRECT = """def test_indirect():
    today = readings(sources, identity=line_number_identity)
    assert set(HISTORICAL) == today
"""
SHAPE_NEGATED = """def test_negated():
    today = readings(sources, identity=line_number_identity)
    assert set(HISTORICAL) != today
"""
SHAPE_ALIASED = """FORGED = set(HISTORICAL)


def test_aliased():
    today = readings(sources, identity=line_number_identity)
    assert FORGED == today
"""
SHAPE_LEGAL = """def test_legal():
    rows = drift_report(sources)
    assert [row["identity"] for row in rows] == list(BASELINE)
    cells = _bare_cells_in(path)
    assert set(cells) <= set(HISTORICAL)
    message = str(excinfo.value)
    assert victim.identity in message
"""


def test_the_shape_ruler_itself_catches_the_shape_it_bans():
    """上一班就是栽在"先赋值、再比对"这一步：只盯字面嵌套的尺量不到，所以尺子自己得自证。"""
    assert [item.partition(":")[0] for item in _history_live_compares(SHAPE_DIRECT)] == ["test_direct"]
    assert [item.partition(":")[0] for item in _history_live_compares(SHAPE_INDIRECT)] == ["test_indirect"]
    assert [item.partition(":")[0] for item in _history_live_compares(SHAPE_NEGATED)] == ["test_negated"]
    # 别名腿：改个名以后比对两侧都不再出现 HISTORICAL 字样——这一腿原来漏着
    assert [item.partition(":")[0] for item in _history_live_compares(SHAPE_ALIASED)] == ["test_aliased"]
    assert _history_live_compares(SHAPE_LEGAL) == []


def _dotted(node):
    """``pytest.mark.skipif`` 这种链的完整点号名；链根不是名字就交空串。"""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def test_neither_file_opens_an_exemption_for_the_ratchet():
    """判据⑤：两本件都没有豁免入口——不 skip、不 xfail，也没有"豁免名单"这种参数或形参。

    本仓已经为这件事立过专门的尺（``test_r253`` 那两枚），所以这里按 AST 取证：只认代码里的
    属性链与形参名，不拿正文当证据，也不给任何一格开口子。
    """
    offenders = []
    for path in (RATCHET_PATH, SELF_PATH):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and _dotted(node).rpartition(".")[2] in SKIP_TAIL:
                offenders.append(f"{path.name}:{node.lineno} {_dotted(node)}")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                offenders.extend(
                    f"{path.name}:{node.lineno} {node.name} 的形参 {arg}"
                    for arg in (a.arg for a in node.args.args) if arg in LEDGER_ARGS
                )
            elif isinstance(node, ast.keyword) and node.arg in LEDGER_ARGS:
                offenders.append(f"{path.name}:{node.lineno} 实参 {node.arg}")

    assert offenders == [], "这枚门是靠豁免过关的：" + " / ".join(offenders)
