# -*- coding: utf-8 -*-
r"""R398 · 三本守卫账重录之后，刀必须还咬得住（全离线，被跟踪文件全程只读）。

三格各自的性质（逐枚现场量，不采信自述）：

① 禁语闸撞在 R394 契约尾部。那一格写的是 `app/documents/catalog.py:357` 的
   `_schema_needs_migrations` 认哪一种异常，落笔用了「只认…前缀」。这枚闸当初为什么存在：
   R127 初稿把**追问触发**写成"七个 `startswith` 前缀的闭合清单"，那是 R126 之前的真相，
   R126 并树（触发词按族生长）之后就成了假话，而全仓没有一枚用例读那段散文——所以闸禁的是
   "把会生长的词表说成闭合清单"这个**形状**，不是禁提某枚常量。改法因此只换措辞、不动闸：
   旧句「只认 `:578` 那一句前缀」→ 新句「判的是 `:578` 抛出的那一句开头」，说的仍是同一件
   事实（一枚常量、一次 `startswith`），但它不再宣称任何**词表**闭合，往词表里加族也证不伪它。
   为什么不算绕：闸的正则、英文旧句、`closed prefix list` 那半条否定式钉全部一字未动
   （`test_the_r132_ruler_itself_is_untouched` 逐格核源码，符号级扫豁免形状），而 K-b 既咬回
   R394 那句旧措辞、也咬闸当初真正要禁的那句假话（把追问触发说成闭合前缀清单），两发都还红。

② R134 那枚"按目录开 Chroma 的收口只有一处可守"的清单被 R382 三枚取证件加长了三枚。
   三枚写的都是 `chromadb.PersistentClient(path=...)`，走的就是同一枚目录漏斗；改道打在工厂
   本身、属性查找发生在调用期，所以新收口自动落在罩子里——加长清单即可，规则不叠加。
   "同一枚漏斗"这句注释由 `test_the_r382_sites_reach_the_same_funnel` 现场抠 AST 证明，
   不靠自述。K-a 再塞一枚影子收口 ⇒ 清单钉当场指名它。
   两条边界照实记（不在本单里偷偷抹平）：罩子由 tests/conftest 在测试生命周期里装，脚本
   直跑本来就不归它管（R134 钉的一直是「测试期不写脏被跟踪的 ./chroma_db」）；而这枚 AST
   尺子只认 chromadb 的工厂，`scripts/r382_chroma_space.py:48` 那扇
   `sqlite3.connect(... mode=ro)` 的直连门它看不见——今天拿不到它写脏的证据（本单禁碰真库，
   也没有实测到 WAL/-shm 的形状），要不要另立一单交总控裁。

③ 路径账三格不同性质。`tests/test_r330_*.py`、`tests/test_r377_*.py` 是文档里的**省略式
   （glob）写法**——上一版解析口径的字符类不收 `*`，把引用切成 `tests/test_r330_` 这种文档
   里从没写过的残缺前缀，红的是解析、不是事实（两枚 glob 各指得到真文件）。修法是捕获带上
   通配符、按通配符核（指不到东西照样红，见 K-d）。第三枚
   `docs/perf/r387-label-lineage-2026-09-27.md` 那一枚不在本树盘上（R387 整单退回、交付件被主树
   `git clean -f` 撤出，R390 同树复工；09-27 晚些时候它随 R400 并了主树）。本件**不造**那枚
   文件，也不留手抄豁免名单，更不记"今天该有几枚在册"——那只守一件事的蕴含：**盘上没有的引用，
   必须能在看板里找到一行逐字含这枚完整路径、同一行挂着"未并树/在途/退回/复工"之一**；找不到
   就红，清单为空就是绿。（上一版"恰一枚"的计数断言被总控退回：那是拿今天的快照冒充不变量，
   别的单正常并树就把看守钉染红。）匹配键是整串路径，不是路径里那段单号——K-e (a)(b)(c)(d)
   四格与 `test_the_in_flight_pass_is_keyed_on_the_whole_path_not_a_ticket_number` 一起量。

零写入：变异只落 tmp 影子副本（R253 口径），每把刀进门取 sha、出门比 sha，进出同一个数。
"""
import ast
import hashlib
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

import test_r120_p3_collection_default as r120
import test_r132_contract_followup_sync as r132
import test_r134_chroma_writeback as r134
from tests import _chroma_sandbox as pins

REPO = Path(__file__).resolve().parents[1]
CONTRACT_REL = "docs/api/contract-v1.md"
R132_REL = "tests/test_r132_contract_followup_sync.py"
R134_REL = "tests/test_r134_chroma_writeback.py"
R120_REL = "tests/test_r120_p3_collection_default.py"
#: ① 撞闸的那一句（旧）与并树用的那一句（新），逐字取自 R394 那一节。
OLD_CLAUSE = "（`:357`，只认 `:578` 那一句前缀）"
NEW_CLAUSE = "（`:357`，判的是 `:578` 抛出的那一句开头）"
#: 闸的正则原文：本件不许它变，也不许给它加豁免。
BANNED_PATTERN_SOURCE = r"只认[^。\n]{0,24}前缀"
#: 追问词表那一句**原始假话**（R127 初稿的形状），K-b 拿它做第二发反证。
FOLLOWUP_LIE = "追问只认七个 startswith 前缀。"
#: ③ 今天真不在树里的那枚在途引用。
R387_CITATION = "docs/perf/r387-label-lineage-2026-09-27.md"
#: K-e (d) 那格用的「错字」样本：与上一格只差一个数字，名字里照样带着 r387 那枚单号——
#: 单号子串能骗过的放行，整串路径骗不过。
MUTATED_R387_CITATION = "docs/perf/r387-label-lineage-2026-09-28.md"
#: ② 因 R382 并进树而加长的三枚收口。
R382_FUNNEL_FILES = (
    "scripts/r382_chroma_space.py",
    "scripts/r382_index_scope.py",
    "scripts/r382_probe.py",
)
#: 影子手册的正文形状：§8 之后才被 `_runbook()` 收进来。
SHADOW_PLAN_HEAD = "# 影子计划书\n\n## 8. 影子手册（只在 tmp 里）\n\n"


def _sha16(*relative_paths: str) -> dict:
    """进门/出门各取一次：被跟踪文件在反证窗里必须一个字都不动。"""
    return {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest()[:16] for rel in relative_paths}


def _shadow_runbook(tmp_path: Path, monkeypatch, body: str) -> Path:
    plan = tmp_path / "shadow-plan.md"
    plan.write_text(SHADOW_PLAN_HEAD + body, encoding="utf-8")
    monkeypatch.setattr(r120, "PLAN_DOC", plan)
    return plan


# ==================== K-a：② 收口清单还咬得住新的目录漏斗 ====================

@pytest.fixture(scope="module")
def funnel_shadow_root(tmp_path_factory):
    """`app/` 与 `scripts/` 整棵**复制**进 tmp：不硬链接，硬链接共享 inode 会改到盘上那枚。"""
    root = tmp_path_factory.mktemp("r398-funnel")
    for folder in ("app", "scripts"):
        shutil.copytree(REPO / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def test_ka_a_new_directory_funnel_is_named_on_the_spot(funnel_shadow_root):
    before = _sha16(R134_REL, "scripts/rebuild_index.py")
    shadow_site = funnel_shadow_root / "scripts" / "r398_shadow_funnel.py"
    shadow_site.write_text(
        "import chromadb\n\n"
        "def open_store(path):\n"
        "    return chromadb.PersistentClient(path=path)\n",
        encoding="utf-8",
    )
    stub = SimpleNamespace(repo_root=str(funnel_shadow_root))
    with pytest.raises(AssertionError) as raised:
        r134.test_there_is_still_only_one_directory_funnel_to_guard(stub)
    message = str(raised.value)
    assert "scripts/r398_shadow_funnel.py:4:PersistentClient" in message, message
    # 对照：同一枚桩、同一枚用例，指回真树必须是绿的——红只能是我塞进去的那枚收口带来的。
    r134.test_there_is_still_only_one_directory_funnel_to_guard(SimpleNamespace(repo_root=str(REPO)))
    assert len(r134.DIRECTORY_FUNNEL_LEDGER) == 8, "清单枚数变了：判据②要求逐枚点名，不许改成数一变就放行"
    assert _sha16(R134_REL, "scripts/rebuild_index.py") == before, "反证窗写脏了被跟踪文件"
    print(f"K-a 进/出 sha16 {before[R134_REL]} -> {_sha16(R134_REL)[R134_REL]}；咬住 r398_shadow_funnel.py:4")


def test_the_r382_sites_reach_the_same_funnel():
    """② 的事实半边：三枚 r382 收口与 R134 的改道**同一形状**，所以加长清单就够了。"""
    assert pins.CHROMA_CLIENT_PARAMETER in {"path", "persist_directory"}, pins.CHROMA_CLIENT_PARAMETER
    for relative in R382_FUNNEL_FILES:
        tree = ast.parse((REPO / relative).read_text(encoding="utf-8"))
        aliases = {
            (spec.asname or spec.name.split(".")[0])
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for spec in node.names
            if spec.name == "chromadb" or spec.name.startswith("chromadb.")
        }
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "PersistentClient"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in aliases
        ]
        assert len(calls) == 1, f"{relative} 的开库调用数不是 1：{[c.lineno for c in calls]}"
        call = calls[0]
        delivered = bool(call.args) or any(
            keyword.arg in {"path", "persist_directory"} for keyword in call.keywords
        )
        assert delivered, f"{relative}:{call.lineno} 的目录没走位置参数也没走 {pins.CHROMA_CLIENT_PARAMETER}"
        assert f"{relative}:PersistentClient" in r134.DIRECTORY_FUNNEL_LEDGER, relative


# ==================== K-b：① 禁语闸一字未动，而且两发都还咬 ====================

def test_kb_the_banned_wording_still_bites_in_both_domains(tmp_path, monkeypatch):
    before = _sha16(CONTRACT_REL, R132_REL)
    text = (REPO / CONTRACT_REL).read_text(encoding="utf-8")
    assert text.count(NEW_CLAUSE) == 1, "新句在主树里不唯一：定点替换的锚点塌了"
    assert OLD_CLAUSE not in text, "旧句还在盘上：①没改口"

    shadow = tmp_path / "contract-v1.md"
    for label, mutated in (("R394 旧句", text.replace(NEW_CLAUSE, OLD_CLAUSE)),
                           ("追问词表闭合", text.replace(NEW_CLAUSE, FOLLOWUP_LIE))):
        shadow.write_text(mutated, encoding="utf-8")
        monkeypatch.setattr(r132, "CONTRACT_DOC", shadow)
        with pytest.raises(AssertionError) as raised:
            r132.test_the_closed_prefix_wording_never_comes_back()
        assert "只认" in str(raised.value), f"{label} 这一发没咬住：{raised.value}"
    # 对照：盘上今天的措辞，同一枚用例必须是绿的。
    monkeypatch.setattr(r132, "CONTRACT_DOC", REPO / CONTRACT_REL)
    r132.test_the_closed_prefix_wording_never_comes_back()
    assert _sha16(CONTRACT_REL, R132_REL) == before, "反证窗写脏了被跟踪文件"
    print(f"K-b 进/出 sha16 {before[CONTRACT_REL]} -> {_sha16(CONTRACT_REL)[CONTRACT_REL]}；两发都咬住")


def test_the_r132_ruler_itself_is_untouched():
    """判据①的另一半：不许放宽正则、不许加豁免名单——逐格核源码，不核自述。"""
    source = (REPO / R132_REL).read_text(encoding="utf-8")
    tree = ast.parse(source)
    constants = {
        node.targets[0].id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    pattern = constants["DEAD_CHINESE_PATTERN"]
    assert isinstance(pattern, ast.Call) and pattern.func.attr == "compile"
    assert pattern.args[0].value == BANNED_PATTERN_SOURCE, ast.unparse(pattern)
    assert tuple(
        element.value for element in constants["DEAD_ENGLISH_PHRASES"].elts
    ) == ("starts with one of",)
    assert constants["CLOSED_LIST_PHRASE"].value == "closed prefix list"

    guard = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "test_the_closed_prefix_wording_never_comes_back"
    )
    shape = [type(statement).__name__ for statement in guard.body if not isinstance(statement, ast.Expr)
             or not isinstance(statement.value, ast.Constant)]
    assert set(shape) <= {"Import", "Assign", "ListComp", "Assert"}, shape
    assert any(isinstance(node, ast.Assert) for node in guard.body)
    branches = [
        type(node).__name__ for node in ast.walk(guard) if isinstance(node, (ast.If, ast.Try))
    ]
    assert branches == [], f"禁语闸里长出了分支或兜底形状：{branches}"
    identifiers = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    identifiers |= {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    offenders = sorted(
        name
        for name in identifiers
        if any(token in name.upper() for token in ("EXEMPT", "ALLOW", "WAIVE", "SKIP", "IGNORE"))
    )
    assert offenders == [], f"禁语闸里长出了豁免形状的符号：{offenders}"


# ==================== K-c / K-d / K-e：③ 路径账的三种形状各咬一发 ====================

def test_kc_a_typoed_literal_path_is_still_named(tmp_path, monkeypatch):
    before = _sha16(R120_REL)
    fake = "scripts/the-shadow-script-that-was-never-written.py"
    _shadow_runbook(tmp_path, monkeypatch, f"照着做：`{fake}` --status。\n")
    with pytest.raises(AssertionError) as raised:
        r120.test_every_repository_path_named_in_the_runbook_exists()
    assert fake in str(raised.value), raised.value
    assert _sha16(R120_REL) == before
    print(f"K-c 进/出 sha16 {before[R120_REL]}；指名 {fake}")


def test_kd_a_glob_that_points_at_nothing_is_named(tmp_path, monkeypatch):
    before = _sha16(R120_REL)
    ghost = "tests/test-shadow-never-written-*.py"
    _shadow_runbook(tmp_path, monkeypatch, f"用例见 `{ghost}`。\n")
    with pytest.raises(AssertionError) as raised:
        r120.test_every_repository_path_named_in_the_runbook_exists()
    assert ghost in str(raised.value), raised.value
    # 对照：真指得到文件的省略式写法必须绿（今天主树里那两枚就是这个形状）。
    _shadow_runbook(tmp_path, monkeypatch, "`tests/test_r330_*.py`、`tests/test_r377_*.py` 两枚在册。\n")
    r120.test_every_repository_path_named_in_the_runbook_exists()
    assert _sha16(R120_REL) == before
    print(f"K-d 进/出 sha16 {before[R120_REL]}；空 glob 咬住、真 glob 放行")


def test_ke_the_in_flight_citation_is_derived_from_the_board_and_expires_by_itself(
    tmp_path, monkeypatch
):
    """③ 的放行四格，全在影子树里量，盘上的字一枚都不动。

    (a) 看板逐字记下这枚完整路径 + 状态词，文件还没到位 ⇒ 放行；
    (b) 看板改口"已并树"、文件仍不在盘上 ⇒ 红（放行不许悬空）；
    (c) 文件到位 ⇒ 绿，且不需要谁回来删登记（"文件到位后不许还红"就是这一格）；
    (d) 引用写错一个字（名字里仍带着单号、看板那一行没有这个完整串）⇒ 红。
    """
    before = _sha16(R120_REL, "docs/handoff/2026-09-15-orchestration-board.md")
    root = tmp_path / "tree"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "compare_vector_recall.py").write_text("# 影子\n", encoding="utf-8")
    board = tmp_path / "board.md"
    monkeypatch.setattr(r120, "ROOT", root)
    monkeypatch.setattr(r120, "BOARD", board)
    cited = f"先跑 `scripts/compare_vector_recall.py`，出处 `{R387_CITATION}`。\n"
    whole_path_row = (
        f"| ``Goodall`` | **R387** 取证件 | `be-r387` | 交付件 {R387_CITATION} 🟠 整单退回·未并树 |\n"
    )

    board.write_text(whole_path_row, encoding="utf-8")
    _shadow_runbook(tmp_path, monkeypatch, cited)
    r120.test_every_repository_path_named_in_the_runbook_exists()

    board.write_text(
        f"| ``Popper`` | **R390** 交付件 {R387_CITATION} ✅ 已并树 `69e0035` |\n", encoding="utf-8")
    with pytest.raises(AssertionError) as raised:
        r120.test_every_repository_path_named_in_the_runbook_exists()
    assert R387_CITATION in str(raised.value), raised.value

    landed = root / R387_CITATION
    landed.parent.mkdir(parents=True)
    landed.write_text("# 交付件到位\n", encoding="utf-8")
    r120.test_every_repository_path_named_in_the_runbook_exists()

    board.write_text(whole_path_row, encoding="utf-8")
    _shadow_runbook(tmp_path, monkeypatch, f"出处 `{MUTATED_R387_CITATION}`。\n")
    with pytest.raises(AssertionError) as raised:
        r120.test_every_repository_path_named_in_the_runbook_exists()
    assert MUTATED_R387_CITATION in str(raised.value), raised.value
    assert r120._in_flight_board_line(MUTATED_R387_CITATION) is None, "错字路径借到了放行"
    assert _sha16(R120_REL, "docs/handoff/2026-09-15-orchestration-board.md") == before
    print(f"K-e 进/出 sha16 {before[R120_REL]}；(a) 放行 (b) 改口即红 (c) 到位即绿 (d) 错字即红")


def test_the_in_flight_pass_is_keyed_on_the_whole_path_not_a_ticket_number(tmp_path, monkeypatch):
    """放行只认整串路径：同一份看板，逐字含它才给，改一个字不给，光有单号也不给。

    这一枚不记账面数量（数量是快照，别人正常并树就会把它染红），只记形状：样本从计划书里
    现抠（不硬编码今天有几枚、是哪几枚），逐枚配一行影子看板账，正反面在同一份数据上同时
    成立；最后一发是 ⑨ 自报那道口子的关门钉——那一行只有单号和状态词、没有完整路径。
    """
    tokens = sorted(
        token
        for token in {match.group(1) for match in r120.PATH_CITATION.finditer(r120._runbook())}
        if token not in r120.OPERATOR_SIDE
    )
    assert tokens, "路径账被掏空了：一枚样本都没有，本枚看守就是空转"
    board = tmp_path / "board.md"
    monkeypatch.setattr(r120, "BOARD", board)
    for token in tokens:
        mutant = token[:-1] + ("x" if token[-1] != "x" else "y")
        assert mutant != token
        board.write_text(f"| ``R398`` | 影子账 | 交付件 {token} 未并树 |\n", encoding="utf-8")
        assert r120._in_flight_board_line(token) is not None, token
        assert r120._in_flight_board_line(mutant) is None, (token, mutant)
    board.write_text(
        "| ``Goodall`` | **R387** 取证件 | `be-r387` | 🟠 整单退回·未并树 |\n", encoding="utf-8")
    assert r120._in_flight_board_line(R387_CITATION) is None, "单号子串又成了放行理由：整串路径才是键"
