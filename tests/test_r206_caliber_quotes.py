"""R206：被引证的「那句口径原话」必须逐字出现在正文里。

病灶与凭据在 docs/testing/a4-metric-conflict-attribution-2026-09-24.md：口径冲突族
run5 → run6 correctness 0.4211 → 0.3158，而同族 evidence_coverage 反升 0.3684 → 0.5263
——「检索命中了那枚片段、答案没把原话带进正文」正是这个形状。

本件全程离线：不发 HTTP、不起服务、不打真模型、不改评测集。三样东西都是真的：

* 「模型」是一枚**假 provider**：它按 run6 实测到的失败方式交回同义改写，其中一枚就是把
  markdown 粗体插进原话中间（「费用以**入账月归属**」）——交回时判分器判错，走完 synthesize
  腿之后逐字命中；
* 片段是**真片段**：正文取自入了版本控制的 documents/制度与口径登记表.txt，本件不抄第二份；
* 判分器是**线上那一枚**：app.quality.eval._is_correct，逐字子串匹配，没另造尺子。

最后两件把 run6 那 13 道失败题逐题跑一遍（喂 run6 记录里的答案与引证片段），机器可验地
产出「转绿 / 不转绿＋归因」那张表——判据② 要的就是这张表，不是一句笼统解释。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage

REPO_ROOT = Path(__file__).resolve().parents[1]
ANSWERS_RUN6 = REPO_ROOT / "docs" / "testing" / "answers-run6.jsonl"
FIXTURE_105 = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"
CALIBER_DOC = REPO_ROOT / "documents" / "制度与口径登记表.txt"

#: 判据① 那对互斥口径。题号取自评测集，两枚短语逐字取自语料——本件一个字都不新造。
FINANCE_QUESTION = "财务部把这笔报销费用算进哪个月？"
MARKETING_QUESTION = "市场部把这笔报销费用算进哪个月？"
ACCRUAL_WORDING = "费用以入账月归属"
OCCURRENCE_WORDING = "费用以发生月归属"


def caliber_fragment() -> str:
    """登记表里 cp-04 那一枚片段：两行互斥口径，逐字来自语料。

    取「行」而不是按字数掐一块：检索回来的单位本就是切块产物（切块尺子住在
    app/rag/retriever.py，chunk_size=500），本件不发明第二把尺，也不把语料抄成第二份。
    """
    rows = [
        line.strip()
        for line in CALIBER_DOC.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("| cp-04 |")
    ]
    assert len(rows) == 2, f"登记表 cp-04 应该正好两行：{rows}"
    return "\n".join(rows)


def cited_state(question: str, answer: str, excerpt: str, **evidence_over) -> dict:
    """拼一发「检索命中片段 + 模型交回同义改写」的最小现场。

    evidence 这一格是**工具边界在装箱之后**记下的账，所以本件喂它的就是模型真读到过的那
    一份正文；provenance_status / permission_checked 两格留给调用方改，用来验诚实性边界。
    """
    evidence = {
        "source_type": "document",
        "source_name": "制度与口径登记表.txt",
        "source_id": "制度与口径登记表.txt#chunk=5",
        "excerpt": excerpt,
        "provenance_status": "verified",
        "permission_checked": True,
    }
    evidence.update(evidence_over)
    return {
        "messages": [HumanMessage(content=question)],
        "worker_results": {"doc": answer},
        "agent_results": {"doc": {"worker": "doc", "status": "success", "answer": answer,
                                  "evidence": [evidence]}},
    }


def run_synthesize(state: dict) -> str:
    from app.agents.nodes import synthesize

    return synthesize(state)["final_answer"]


def guard_quotes(body: str) -> list:
    """只取「口径原文」那一段里的引证行。

    不这么切不行：run6 metric-10 那份答案自己就写过一枚 "> **费用归属期间…" 引用块，
    按 "> " 全收会把模型的话当成守卫补写的话。
    """
    from app.rag.retrieval_pipeline import CALIBER_QUOTE_LABEL

    marker = body.find(CALIBER_QUOTE_LABEL)
    if marker < 0:
        return []
    return [line[2:] for line in body[marker:].splitlines() if line.startswith("> ")]


def judged(question_row: dict, text: str) -> bool:
    """用线上那枚判分器判，不另造第二套。"""
    from app.quality.eval import _is_correct

    return _is_correct(question_row, {"answer": text})


# ==================== 判据①：一对互斥口径，两道题各命中各自的原话 ====================

def test_the_conflicting_pair_each_lands_on_its_own_wording():
    """同一对冲突口径的两道题，都必须命中**自己那一侧**的原话，且不串味。

    「不串味」才是这条判据的牙齿：只要求「原话进正文」的话，把登记表那一块整片倒进答案
    也能过——那判据① 就成了摆设。所以这里两侧各断言一次「有自己、无对方」。
    """
    fragment = caliber_fragment()
    paraphrase = "财务部按凭证过账的月份来归这笔费用，也就是入账的那个月。"

    finance = run_synthesize(cited_state(FINANCE_QUESTION, paraphrase, fragment))
    marketing = run_synthesize(cited_state(MARKETING_QUESTION, paraphrase, fragment))

    assert judged({"must_contain": [ACCRUAL_WORDING]}, finance)
    assert judged({"must_contain": [OCCURRENCE_WORDING]}, marketing)
    assert OCCURRENCE_WORDING not in finance, "财务部答案里串进了市场部那一侧的原话"
    assert ACCRUAL_WORDING not in marketing, "市场部答案里串进了财务部那一侧的原话"
    assert finance != marketing, "两道题交回同一份文字 ⇒ 选句根本没按题面分侧"


def test_the_carried_line_is_the_fragments_own_bytes_not_a_rewrite():
    """补进正文的每一行都必须能在被引证片段里逐字找到——同义改写不算「原话」。"""
    from app.rag.retrieval_pipeline import CALIBER_QUOTE_LABEL

    fragment = caliber_fragment()
    paraphrase = "按入账月份归。"
    body = run_synthesize(cited_state(FINANCE_QUESTION, paraphrase, fragment))

    assert body.startswith(paraphrase), "守卫改写了模型写的字：它只许往末尾追加"
    assert CALIBER_QUOTE_LABEL in body[len(paraphrase):]
    carried = guard_quotes(body)
    assert carried, "没有逐字引证行"
    for line in carried:
        assert line in fragment, f"这一行不是片段里的原话：{line}"


def test_the_run6_shape_bold_inside_the_quote_fails_before_and_passes_after():
    """run6 metric-10 的真实形状：意思说对了，粗体把原话从中间切断 ⇒ 判分器判错。

    这条先把「尺子没坏」钉住：同一段文字，不经守卫必须判错，走完守卫必须判对。
    """
    from app.quality.eval import _is_correct

    row = {"must_contain": [ACCRUAL_WORDING]}
    run6_answer = (
        "> **费用归属期间（财务部）**：费用以**入账月归属**，"
        "按**凭证过账期间**确定所属月份。"
    )
    assert not _is_correct(row, {"answer": run6_answer}), "夹具根本不判错，那就不是在复现 run6"

    guarded = run_synthesize(cited_state(FINANCE_QUESTION, run6_answer, caliber_fragment()))
    assert _is_correct(row, {"answer": guarded}), "守卫没能把被粗体切断的那句原话逐字补回正文"


# ==================== 边界：守卫只在有真出处时开口，且只追加 ====================

def test_a_fragment_that_is_not_a_registered_row_keeps_the_answer_untouched():
    """散文句不是「登记口径」：认不出登记行时本腿一个字都不加。

    这一条守的是「硬门只许加，不许把别的族改出新形状」——语料里 cp-0x/t-0x 之外的句子多得
    是，见词就补会把终答变成复读机。
    """
    from app.agents.nodes import synthesize

    prose = "本表每季度核对一次，由财务部牵头，各归口部门确认；核对结果记入本表修订记录。"
    result = synthesize(cited_state(FINANCE_QUESTION, prose[:8], prose))
    assert result["final_answer"] == prose[:8]
    assert "worker_results" not in result, "一个字都没补，却回写了 worker_results"


def test_unverified_or_unpermitted_fragments_cannot_feed_the_guard():
    """出处没核过或没过权限 ⇒ 它的原话不许被抬进正文当「引证」。"""
    fragment = caliber_fragment()
    for over in ({"provenance_status": "inferred"}, {"permission_checked": False}):
        body = run_synthesize(cited_state(FINANCE_QUESTION, "按入账月归。", fragment, **over))
        assert ACCRUAL_WORDING not in body, over


def test_a_question_that_is_not_about_a_caliber_stays_silent():
    """问的是别的角度（住宿费标准），登记表里那几行不许被拖进答案。"""
    body = run_synthesize(cited_state("住宿费标准是多少？", "500元/晚。", caliber_fragment()))
    assert body == "500元/晚。"


def test_appending_keeps_the_settled_answer_a_prefix():
    """R203 的收端契约：已发出去的每一枚流式帧都必须是终答的前缀。

    守卫改的是 worker_results 里**最后**那条腿的尾巴，所以「补写前的终答」必须仍是
    「补写后的终答」的前缀。往中间插字会当场破这条——那一格正是 R210 在守的 prefix_breaks。
    """
    from app.agents.nodes import synthesize

    state = cited_state(FINANCE_QUESTION, "按入账月份归这笔费用。", caliber_fragment())
    settled_before = "\n\n".join(str(v).strip() for v in state["worker_results"].values())

    result = synthesize(state)
    settled_after = "\n\n".join(str(v).strip() for v in result["worker_results"].values())
    assert settled_after.startswith(settled_before), "追加位置不对，已发出的帧不再是终答的前缀"
    assert result["final_answer"] == settled_after, "终答与 worker_results 折出来的文字不一致"


def test_multi_worker_rounds_keep_every_leg_in_the_rewritten_map():
    """多腿那一轮：收端是拿 worker_results 整张覆盖的，回写只带一条腿会把别的腿洗掉。"""
    from app.agents.nodes import synthesize

    state = cited_state(FINANCE_QUESTION, "按入账月份归这笔费用。", caliber_fragment())
    state["worker_results"]["data"] = "本月合计 12 万元。"
    state["agent_results"]["data"] = {"worker": "data", "status": "success",
                                      "answer": "本月合计 12 万元。", "evidence": []}

    result = synthesize(state)
    assert list(result["worker_results"]) == ["doc", "data"], result["worker_results"]
    assert "__reset__" not in result["worker_results"], "state 合并协议的记法漏进了收端"
    assert "本月合计 12 万元。" in result["final_answer"]
    assert "本月合计 12 万元。" in result["worker_results"]["data"], "别的腿被改了字"


def test_the_boxing_side_is_the_single_source_of_the_caliber_rule():
    """「哪一句才算口径原话」只有 app/rag 那一处说法，nodes.py 不许抄第二份。"""
    import inspect

    import app.agents.nodes as nodes
    import app.rag.retrieval_pipeline as pipeline

    assert hasattr(pipeline, "select_caliber_quotes")
    source = inspect.getsource(nodes._carry_caliber_quotes)
    assert ACCRUAL_WORDING not in source, "守卫里写死了语料字面 ⇒ 换一份制度文件就失效"
    assert "must_contain" not in source, "守卫读评测集词条＝拿答案倒推判据"


def test_a_row_cut_in_half_by_the_excerpt_limit_is_not_offerable():
    """出处摘录有 400 字上限：落在边界上被切一半的那一行，不许当「原话」补进正文。

    这不是假想的形状——run6 metric-10 那枚摘录就停在「…分母取利润表主营业务成」上，
    尾巴是一枚半行。本单修的正是「原话被切断」，修法自己再往正文里补一次半行就是假修。
    复测的两侧都要有：整行在位时补得进（上面几件），行尾被裁时补不进（这一件）。
    """
    from app.rag.retrieval_pipeline import select_caliber_quotes

    fragment = caliber_fragment()
    marketing_row = [line for line in fragment.splitlines() if OCCURRENCE_WORDING in line][0]
    amputated = fragment.replace(marketing_row, marketing_row[:-8])

    picked = select_caliber_quotes([{"text": amputated, "source": "x"}], MARKETING_QUESTION)
    assert [item["line"] for item in picked] != [marketing_row], "半行被当成原话补了出去"
    for item in picked:
        assert item["line"].endswith(("|", "。")), item["line"]

    whole = select_caliber_quotes([{"text": fragment, "source": "x"}], MARKETING_QUESTION)
    assert [item["line"] for item in whole] == [marketing_row], "整行在位时反而补不进了"


# ==================== 与收端、装箱侧的契约 ====================

def test_both_readers_of_the_final_answer_carry_the_line():
    """两个读终答的收端必须都拿到这句原话——这一条就是"为什么要回写 worker_results"。

    app/api/v1/chat.py 的 _select_final_answer **优先** worker_results（非空即用它），
    app/agents/orchestrator.py 的 _final_of 优先 final_answer。守卫只改后者的话，走 HTTP
    的那一条腿（评测采集与聊天都是）一个字都看不见——本件不 import chat.py 的判分旁路，
    直接用它自己那枚函数。
    """
    from app.agents.nodes import synthesize
    from app.agents.orchestrator import _final_of
    from app.api.v1.chat import select_final_answer

    state = cited_state(FINANCE_QUESTION, "按凭证过账那个月归。", caliber_fragment())
    result = synthesize(state)

    assert ACCRUAL_WORDING in select_final_answer(
        final_answer=result["final_answer"], worker_results=result.get("worker_results")), \
        "HTTP 收端没拿到原话：守卫被 _select_final_answer 的优先级洗掉了"
    assert ACCRUAL_WORDING in _final_of(result), "编排收端没拿到原话"


def test_the_chunking_ruler_and_the_packing_ruler_are_the_same_number():
    """切块那把尺与装箱那把尺必须是同一个数，否则整行口径会在进 prompt 之前被裁断。

    这是本单在**装箱侧**真正能钉住的那件事，也是它不去动现网装箱的理由：
    一条命中的正文按 DOC_HIT_CONTENT_CHARS 硬切，而块是按 app/rag/retriever.py 的
    chunk_size 切出来的。今天两把尺都是 500，实测全库 379 块最长 499 字 ⇒ 裁不断任何一行
    登记口径（这一件就是量这个的）。哪天有人把 chunk_size 调大而不改另一把，登记表后半段
    那些"cp-06/07/08"就会成批变成"检索命中了、原话进不了正文"——正是 run6 那一族的病。
    与其现在就动读路径去冒重写现网的风险，不如把这枚耦合钉在测试里：它红了再改装箱。
    """
    import re
    from pathlib import Path

    from app.rag.retrieval_pipeline import DOC_HIT_CONTENT_CHARS

    source = (REPO_ROOT / "app" / "rag" / "retriever.py").read_text(encoding="utf-8")
    sizes = [int(n) for n in re.findall(r"chunk_size=(\d+)", source)]
    assert sizes, "切块尺寸读不到了：这一件的位置也变了，去看 retriever 的 splitter"
    assert set(sizes) == {DOC_HIT_CONTENT_CHARS}, (
        f"切块 chunk_size={sizes} 与装箱 DOC_HIT_CONTENT_CHARS={DOC_HIT_CONTENT_CHARS} 不再是"
        "同一个数 ⇒ 整行登记口径会被裁成半行，本单那一族退化会以另一种形状回来")

    from langchain_text_splitters import RecursiveCharacterTextSplitter

    separators = ["\n\n", "\n", "。", "；", "　", " ", ""]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=DOC_HIT_CONTENT_CHARS, chunk_overlap=50, separators=separators)
    tracked = [CALIBER_DOC]
    longest = max(len(chunk) for path in tracked
                  for chunk in splitter.split_text(path.read_text(encoding="utf-8")))
    assert longest <= DOC_HIT_CONTENT_CHARS, (path.name, longest)
    # 而且这块里每一行登记口径都完整可读：守卫认得出的行，模型也一定看得见
    rows = [line.strip() for line in CALIBER_DOC.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("| cp-")]
    for chunk in splitter.split_text(CALIBER_DOC.read_text(encoding="utf-8")):
        for line in rows:
            if line[:24] in chunk:
                assert line in chunk, f"这一行登记口径被切块切断了：{line[:40]}"


# ==================== run6 十三道失败题：逐题处置表（判据② 的那张表） ====================

#: 归因码是闭集，逐题只许挂一枚。三枚的边界都机器判得出，不是形容词：前两枚讲的是
#: 「原话有没有到得了正文这一步」，第三枚才是本腿的活。
MISSING_REASONS = {
    "no_cited_fragment": "这一轮一个字都没被引证（evidence_n=0）：守卫没有原文可保",
    "phrase_never_retrieved": "有引证片段，但那枚口径行不在其中：病灶在召回与名次",
    "carried_but_not_in_body": "口径行就在被引证的片段里，正文却没带它：本腿的地盘",
}


def _run6_rows():
    answers = {}
    for line in ANSWERS_RUN6.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            row = json.loads(line)
            answers[str(row.get("id"))] = row
    fixture = {}
    for line in FIXTURE_105.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            fixture[str(row.get("id"))] = row
    return answers, fixture


def _state_of(run6_row: dict, question_row: dict) -> dict:
    """把 run6 那一发的答案与引证片段搬进一发真 state（原件只读，一个字不改）。"""
    evidence = [
        {
            "source_type": "document",
            "source_name": str(item.get("source") or ""),
            "source_id": str(item.get("source_id") or ""),
            "excerpt": str(item.get("excerpt") or ""),
            "provenance_status": str(item.get("provenance_status") or "verified"),
            "permission_checked": bool(item.get("permission_checked", True)),
        }
        for item in (run6_row.get("evidence") or [])
    ]
    answer = str(run6_row.get("answer") or "")
    return {
        "messages": [HumanMessage(content=str(question_row.get("question") or ""))],
        "worker_results": {"doc": answer},
        "agent_results": {"doc": {"worker": "doc", "status": "success", "answer": answer,
                                  "evidence": evidence}},
    }


def _why_the_phrase_was_missing(run6_row: dict, question_row: dict) -> str:
    phrase = str((question_row.get("must_contain") or [""])[0])
    excerpts = [str(item.get("excerpt") or "") for item in (run6_row.get("evidence") or [])]
    if not excerpts:
        return "no_cited_fragment"
    if not any(phrase in text for text in excerpts):
        return "phrase_never_retrieved"
    return "carried_but_not_in_body"


@pytest.mark.skipif(not ANSWERS_RUN6.exists(), reason="run6 原件不在本树（只读，不许伪造）")
def test_run6_failure_disposition_table():
    """13 道失败题逐题过一遍真守卫：该转绿的必须转绿，不转绿的必须挂着那一枚归因码。

    这张表是**算出来的**不是写出来的：每题喂 run6 记录里那一发的答案与引证片段，跑真
    synthesize，再用线上那枚 _is_correct 判。转绿三题（metric-05/10/18）的归因码全是
    carried_but_not_in_body——原话本就送到了模型眼前；其余十题一枚都不是本腿的活：八题这一轮
    根本没引证到口径行（派工与知识库腿，R206a 的地盘），两题引证到的片段里没有那一行
    （召回与名次）。这一枚闭集把它们的差别逐题摊开，也把守卫的手脚量了出来。
    """
    answers, fixture = _run6_rows()
    family = [row for row in fixture.values() if row.get("category") == "口径冲突"]
    failures = [row for row in sorted(family, key=lambda r: r["id"])
                if not judged(row, str(answers[row["id"]].get("answer") or ""))]
    assert len(failures) == 13, [row["id"] for row in failures]

    turned_green, stayed_red, stayed_appended = {}, {}, {}
    for row in failures:
        run6_row = answers[row["id"]]
        before = str(run6_row.get("answer") or "").strip()
        reason = _why_the_phrase_was_missing(run6_row, row)
        assert reason in MISSING_REASONS, reason

        body = run_synthesize(_state_of(run6_row, row))
        assert body.startswith(before), f"{row['id']}：守卫改写了 run6 那份文字"
        excerpts = [str(item.get("excerpt") or "") for item in (run6_row.get("evidence") or [])]
        appended = guard_quotes(body)
        # 补进去的每一行都必须是被引证片段里的原语：不许编，哪怕这一题根本救不回来
        assert all(any(line in text for text in excerpts) for line in appended), row["id"]

        if judged(row, body):
            turned_green[row["id"]] = reason
        else:
            stayed_red[row["id"]] = reason
            stayed_appended[row["id"]] = bool(appended)

    assert sorted(turned_green) == ["metric-05", "metric-10", "metric-18"], turned_green
    assert set(turned_green.values()) == {"carried_but_not_in_body"}, turned_green
    assert sorted(stayed_red) == ["metric-04", "metric-07", "metric-08", "metric-11",
                                  "metric-12", "metric-13", "metric-14", "metric-15",
                                  "metric-16", "metric-17"], stayed_red
    codes = sorted(stayed_red.values())
    assert codes.count("no_cited_fragment") == 8, stayed_red
    assert codes.count("phrase_never_retrieved") == 2, stayed_red
    assert "carried_but_not_in_body" not in codes, "还有一题本腿能救却没救起来"
    # 无引证可保的八题，守卫一个字都没加；两题「片段里没有那一行」的，只有 metric-08 追加了
    # 同族另一条登记行（t-02 退款是否计入费用）——它缺的 cp-03 销售部那一行压根没被引证到，
    # 守卫按字面重合只能挑到手边最像的那一句。追加是逐字真原话，但救不了这题：选侧不在这条腿。
    assert sorted(key for key, hit in stayed_appended.items() if hit) == ["metric-08"], stayed_appended


@pytest.mark.skipif(not ANSWERS_RUN6.exists(), reason="run6 原件不在本树（只读，不许伪造）")
def test_the_three_green_rows_each_quote_their_own_registered_line():
    """转绿的三题，补进去那一行必须能在**它自己的**被引证片段里逐字找到，且各带各的口径。"""
    answers, fixture = _run6_rows()
    expected = {
        "metric-05": "活跃客户按登录活跃客户数",
        "metric-10": ACCRUAL_WORDING,
        "metric-18": "里程碑以提交验收视为完成",
    }
    for row_id, phrase in expected.items():
        run6_row = answers[row_id]
        body = run_synthesize(_state_of(run6_row, fixture[row_id]))
        quoted = guard_quotes(body)
        assert quoted and phrase in quoted[-1], (row_id, quoted)
        excerpts = [str(item.get("excerpt") or "") for item in (run6_row.get("evidence") or [])]
        sourced = [text for text in excerpts if all(line in text for line in quoted)]
        assert sourced, f"{row_id}：补进正文的行不在任何被引证片段里，那是编的"
