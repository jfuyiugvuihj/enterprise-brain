"""R152 结案时具名上报的两笔文档欠账，加上三根防再漂的焊条（全离线：不连库、不打模型、不起服务）。

欠账本身：R152 把 ``POST/GET /api/v1/feedback/document`` 与 ``RAG_ACTIVITY_PRIOR`` 落进主干，
却没进 ``docs/api/contract-v1.md``、没进两份 env 示例。执行层禁碰 docs，所以那两笔由总控补写。

为什么补完还得钉住（R142 的原话在这里同样成立）：**没人读的散文一定会第二次漂。** 这一枚钉读三件事：

  ① 开关名与取值一律从 ``app/rag/retriever.py`` 现取，示例里写下的值必须落在"代码认作开"的那一侧，
     且两份示例不许各写一套；
  ② 契约那段里**每一个数字都由常量现算**（一枚采纳值多少、榜首两名差多少、能挪几个名次），
     改 ``ACTIVITY_PRIOR_MAX_SHIFT_RANKS`` / ``ACTIVITY_PRIOR_SIGNAL_GAIN`` 而不改散文，本钉当场红——
     散文不许替功能粉饰（R153 之后先验的单位是名次，旧的 ``ACTIVITY_PRIOR_WEIGHT`` 已退役）;
  ③ 契约的码表与 ``feedback.py`` 真会抛的码同源（AST 现抠，零手抄）：多列一枚就是替后端开洞。

另有一条 R120 的旧账顺手钉住：写在 env 示例里的旋钮必须真能到达跑检索的进程，否则它就是装饰。
"""
import ast
import re
from pathlib import Path

import pytest
import yaml

from app.rag import retriever

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DOC = ROOT / "docs" / "api" / "contract-v1.md"
FEEDBACK_PY = ROOT / "app" / "api" / "v1" / "feedback.py"
CHAT_PY = ROOT / "app" / "api" / "v1" / "chat.py"
COMPOSE = ROOT / "docker-compose.yml"
ENV_SAMPLES = (ROOT / ".env.example", ROOT / "deploy" / ".env.server.example")

SECTION_HEADING = "## Document Activity Feedback"
#: 那几个进程真的会走检索排序，所以旋钮必须到得了它们
RETRIEVING_SERVICES = ("backend", "worker", "scheduler")
CODE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _text(path: Path) -> str:
    assert path.exists(), f"{path.relative_to(ROOT)} 不在了"
    return path.read_text(encoding="utf-8-sig")


def _documented(path: Path) -> dict[str, str]:
    """按两份示例的真实读法解析：注释行不算，最后一次赋值赢。"""
    values: dict[str, str] = {}
    for line in _text(path).replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        values[name.strip()] = value.strip()
    return values


def _section() -> str:
    text = _text(CONTRACT_DOC)
    start = text.find(SECTION_HEADING)
    assert start != -1, f"契约里找不到 {SECTION_HEADING!r} 这一节：改名可以，请连本钉一起改"
    tail = text[start + len(SECTION_HEADING):]
    end = re.search(r"^## ", tail, re.MULTILINE)
    section = text[start:start + len(SECTION_HEADING) + (end.start() if end else len(tail))]
    assert len(section) > 800, "这一节短得不对劲，后面每枚钉都会变成空响"
    return section


def _score(rank: int) -> float:
    return 1.0 / (retriever.ACTIVITY_PRIOR_RANK_BASE + rank)


#: R153 之后一起量的腿宽：出厂那条（从 chat.py 现抠）再加两条明显更宽的。界的定义就是
#: 「这几处必须同一个数」——旧写法（分值相加）在 5 名腿上走 4 名、在 40 名腿上走 19 名，
#: 拿任何一处理成的散文都会在下一次换腿宽时变成假话。
MEASURED_LEG_WIDTHS = (5, 12, 40)


def _places_a_single_acceptance_crosses(leg_width: int = 40, *, signal: str = "accepted") -> int:
    """一枚信号过真函数能把那条命中挪几个名次（绝对值），在指定宽度的腿上量。

    原尺（R152 立的）是手算：把 ``activity_prior_value`` 加进 ``1/(60+rank)`` 再问它能越过谁——
    那量的正是"分值等效几名"，也就是 R153 要消灭的那种随拥挤度漂移的读数。现在改成调
    ``rank_hits_by_activity`` 本体、读它自己写下的 ``places_moved``：量的是代码实际做的事，
    不是散文以为它做的事。
    """
    # 放在**能动的那个位置**上量：一枚采纳要从不利的末尾往上顶，一枚驳回要从有利的榜首往下掉。
    # 把驳回记在末尾那条上会得到 0，而那 0 不是界松了，是它脚底下已经没有人了——那种量法拦不住漂移。
    spot = leg_width - 1 if signal == "accepted" else 0
    hits = [{"source": "doc-%d.pdf" % index} for index in range(leg_width)]
    hits[spot]["source"] = "hot.pdf"
    counts = {"accepted": 1, "rejected": 0} if signal == "accepted" else {"accepted": 0, "rejected": 1}
    ranked = retriever.rank_hits_by_activity(hits, {"hot.pdf": counts})
    marked = [hit for hit in ranked if isinstance(hit, dict) and hit.get("source") == "hot.pdf"]
    assert len(marked) == 1, "命中在结果里丢了：候选进出一个都不动那句已经不成立"
    assert "activity_prior" in marked[0], "有信号的命中没被注记，places_moved 无从可量"
    return abs(int(marked[0]["activity_prior"]["places_moved"]))


# ==================== ① 开关：名字、取值、两份示例同色 ====================


@pytest.mark.parametrize("sample", ENV_SAMPLES, ids=lambda p: p.name)
def test_the_documented_switch_value_is_the_value_the_code_treats_as_on(sample, monkeypatch):
    """示例必须写下这个开关，且写的那个值真能被代码读成"开"。"""
    documented = _documented(sample).get(retriever.ACTIVITY_PRIOR_ENV)
    assert documented is not None, (
        f"{sample.relative_to(ROOT)} 没写 {retriever.ACTIVITY_PRIOR_ENV}：操作者无从知道有这根旋钮，"
        "也无从退回（R152 的文档欠账，跟进单 §77）"
    )
    assert documented.lower() not in retriever.ACTIVITY_PRIOR_OFF_VALUES, (
        f"{sample.relative_to(ROOT)} 把开关写成 {documented!r}，而代码的默认是开——示例与默认相反，"
        "就是照文档装出来的第二种行为（R30 的口径）"
    )
    monkeypatch.setenv(retriever.ACTIVITY_PRIOR_ENV, documented)
    assert retriever.activity_prior_enabled() is True
    monkeypatch.setenv(retriever.ACTIVITY_PRIOR_ENV, "off")
    assert retriever.activity_prior_enabled() is False, "退回路径也得是活的，否则示例那句是空的"


def test_the_two_samples_agree_about_the_switch():
    """两份文档各写一套数 = 一台机器两种行为。"""
    values = {_documented(sample).get(retriever.ACTIVITY_PRIOR_ENV) for sample in ENV_SAMPLES}
    assert len(values) == 1 and None not in values, f"两份示例读成 {values}"


def test_the_switch_reaches_the_processes_that_rank():
    """R120 的旧账：env 示例里的旋钮必须真能到容器，不能只写在纸上。"""
    services = yaml.safe_load(_text(COMPOSE))["services"]
    for name in RETRIEVING_SERVICES:
        forwarded = services[name].get("environment") or {}
        env_files = services[name].get("env_file") or []
        if isinstance(env_files, dict):
            env_files = [env_files.get("path")]
        whole_file = any(str(item).endswith("deploy/.env.server") for item in env_files)
        assert whole_file or retriever.ACTIVITY_PRIOR_ENV in forwarded, (
            f"{name} 既没整份读入 deploy/.env.server，也没单独透传这个开关，"
            "示例里那一行就到不了它"
        )


# ==================== ② 散文里的数字必须由常量现算 ====================


def test_the_prose_reports_measured_figures_not_advertised_ones():
    """契约里那几个数（一枚采纳值多少、头两名差多少、最多挪几名）与代码算出来的一致。"""
    section = _section()

    one_acceptance = retriever.activity_prior_value({"accepted": 1, "rejected": 0})
    head_gap = _score(1) - _score(2)
    bound = retriever.ACTIVITY_PRIOR_MAX_SHIFT_RANKS
    gain = retriever.ACTIVITY_PRIOR_SIGNAL_GAIN
    measured = {_places_a_single_acceptance_crosses(width) for width in MEASURED_LEG_WIDTHS}

    assert measured == {bound}, f"过真函数现量到 {sorted(measured)}，常量却写着 {bound}：界不在代码里"
    assert "%.4f" % one_acceptance in section, (
        f"散文里那枚'一枚采纳的名次强度'与代码算出的 {one_acceptance!r} 对不上：改了常量不改散文就是假话"
    )
    assert "%.5f" % head_gap in section, (
        f"散文里那枚'榜首两名的分差'与代码算出的 {head_gap!r} 对不上"
    )
    assert f"{bound} rank" in section, f"散文不再写出实测的位移上界 {bound} rank：强度只许按量出来的数陈述"
    assert f"ACTIVITY_PRIOR_MAX_SHIFT_RANKS = {bound}" in section, "散文不再指名那根界的出处常量"
    assert f"ACTIVITY_PRIOR_SIGNAL_GAIN = {gain}" in section, "散文不再指名每枚信号的增益常量"
    assert "ACTIVITY_PRIOR_WEIGHT" not in section, (
        "散文还在引用 R153 退役的那枚权重：单位已从分值换成名次，旧数留着就是替功能粉饰"
    )


def test_the_prose_admits_the_prior_spans_a_whole_shipped_leg():
    """🔴 这枚钉的名字在 R153 之后是**反的**，留着名字是为了留住它拦的那句假话。

    原断言（跟进单 §77 立的）：``places >= min(leg_widths)``——拦的是"散文把先验说成挪一点点"，
    因为当时一枚采纳确实横跨整条腿（5 名的腿走 4 名）。R153 把位移钉成 1 名之后那句不再真，
    照抄会让本钉永远红（现量 1 < 5），所以按 R58 / R147 的先例连名带断言一起改口，记账：

    - 不夸大：位移必须**等于**界，且在几种腿宽上**同一个数**（旧写法随拥挤度漂，这一条从前拦不住）；
    - 不缩小：界必须**严格大于 0**，且正负两侧都现量——否则"开关开着但其实一序未动"这种装饰没人发现得了；
    - 不手抄：腿宽清单仍从 ``chat.py`` 的 ``search(k=…)`` 用 AST 现抠，一枚都不许少。

    三件合起来比原来那一件更难满足，断言强度未降。
    """
    section = _section()

    leg_widths = _shipped_leg_widths()
    assert leg_widths, "chat.py 里的 search(...) 不再带 k= 实参，腿宽得换个地方量（连这里一起改）"
    bound = retriever.ACTIVITY_PRIOR_MAX_SHIFT_RANKS
    widths = sorted(set(leg_widths) | set(MEASURED_LEG_WIDTHS))
    upward = {width: _places_a_single_acceptance_crosses(width) for width in widths}
    downward = {width: _places_a_single_acceptance_crosses(width, signal="rejected") for width in widths}

    assert bound > 0, "界为 0 等于关掉这个特性，契约那句「排名读回来当先验」就该整段删掉"
    assert set(upward.values()) == {bound}, f"一枚采纳的位移随腿宽漂了：{upward}"
    assert set(downward.values()) == {bound}, f"一枚驳回的位移随腿宽漂了：{downward}"
    assert f"measured as {bound} place at leg widths" in section, (
        f"散文不再写出实测位移与它量过的腿宽（现量 {upward}）：只许报量过的数"
    )
    for width in widths:
        assert re.search(r"\b%d\b" % width, section), f"契约不再提到它量过的腿宽 {width}"
    for width in leg_widths:
        assert f"k={width}" in section, f"契约不再写出腿宽 k={width}"


def _shipped_leg_widths() -> list[int]:
    """AST 抠 chat.py 里 retriever.search(...) 的 k 实参：零手抄，也不引用行号。"""
    widths = []
    for node in ast.walk(ast.parse(_text(CHAT_PY))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "search":
            for keyword in node.keywords:
                if keyword.arg == "k" and isinstance(keyword.value, ast.Constant):
                    if isinstance(keyword.value.value, int):
                        widths.append(keyword.value.value)
    return sorted(set(widths))


# ==================== ③ 码表与路由同源 ====================


def _raised_pairs() -> list[tuple[int, str]]:
    """``HTTPException(status_code=N, detail="字面量")`` 的全部组合。"""
    pairs: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(_text(FEEDBACK_PY))):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "HTTPException"):
            continue
        status = detail = None
        for keyword in node.keywords:
            if keyword.arg == "status_code" and isinstance(keyword.value, ast.Constant):
                status = keyword.value.value
            if keyword.arg == "detail" and isinstance(keyword.value, ast.Constant):
                detail = keyword.value.value
        if isinstance(status, int) and isinstance(detail, str):
            pairs.append((status, detail))
    assert pairs, "feedback.py 里抠不出任何一枚带字面量 detail 的 HTTPException，形状变了"
    return pairs


def _raised_statuses() -> set[int]:
    """状态码不分 detail 是不是字面量：403 那两枚的 detail 是变量，状态码仍然是真抛出来的。"""
    statuses = set()
    for node in ast.walk(ast.parse(_text(FEEDBACK_PY))):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "HTTPException"):
            continue
        for keyword in node.keywords:
            if keyword.arg == "status_code" and isinstance(keyword.value, ast.Constant):
                if isinstance(keyword.value.value, int):
                    statuses.add(keyword.value.value)
    assert statuses, "feedback.py 里抠不出一枚状态码，本钉会退化成恒真"
    return statuses


def _vocabulary() -> set[str]:
    """本模块所有 snake_case 字符串字面量：detail 是变量时（403 那两枚）也从这里认。"""
    words = set()
    for node in ast.walk(ast.parse(_text(FEEDBACK_PY))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if CODE_NAME.match(value):
                words.add(value)
    return words


def _documented_rows() -> list[tuple[int, str]]:
    rows = []
    for line in _section().splitlines():
        match = re.match(r"^\|\s*(\d{3})\s*\|(.+)\|", line.strip())
        if match:
            for code in re.findall(r"`([a-z][a-z0-9_]*)`", match.group(2)):
                rows.append((int(match.group(1)), code))
    assert rows, "契约那张码表解析出零行，对账不能降级成恒真"
    return rows


def test_the_contract_table_matches_the_routes_actual_codes():
    """表里不许有路由给不出的码，也不许漏掉路由真会抛的码。"""
    raised = set(_raised_pairs())
    documented = set(_documented_rows())
    vocabulary = _vocabulary()

    statuses = _raised_statuses()
    invented = sorted((status, code) for status, code in documented if status not in statuses)
    assert invented == [], f"契约写了路由根本不抛的状态码：{invented}"
    missing = sorted(raised - documented)
    assert missing == [], f"路由会抛、契约却没记账：{missing}"
    for status, code in documented:
        assert code in vocabulary or status == 403, (
            f"{status} 的 {code!r} 不在 feedback.py 的字面量里：契约在替后端开洞"
        )


def test_the_privacy_claim_points_at_a_real_migration():
    """"只存计数"这句必须指着那张真表，不能只是散文。"""
    section = _section()

    assert "migrations/0011" in section, "隐私判据不再指名它的实体"
    migration = ROOT / "migrations" / "0011_document_activity_signals.sql"
    assert migration.exists(), "0011 不见了，那段契约就成了空头支票"
    sql = re.sub(r"--[^\n]*", "", migration.read_text(encoding="utf-8-sig"))
    columns = re.findall(r"^\s{4}([a-z_]+)\s+([A-Z]+)", sql, re.MULTILINE)
    assert columns, "0011 的列定义抠空了：隐私判据不许钉在空集合上"
    text_columns = sorted(name for name, kind in columns if kind == "TEXT")
    assert text_columns == ["filename"], (
        f"「存不下」只在这张表除了文档标识再没有第二枚自由文本列时才成立，现在是 {text_columns}"
    )
    forbidden = {"query", "question", "answer", "excerpt", "note", "payload", "body", "content", "user_id"}
    grown = sorted(forbidden & {name for name, _ in columns})
    assert grown == [], f"计数表长出了内容列或身份列：{grown}——判据③与「不按人存」那句都得重读"
