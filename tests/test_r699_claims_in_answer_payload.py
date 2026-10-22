"""R699 · 答案件带上 claims：判分器早就在逐条读，缺的是产品侧不肯交断言。

判据 2 的三枚牙，一枚一个形状：

① ``test_an_unsupported_assertion_gives_the_rate_a_denominator`` —— 喂一条无证据支撑的断言，
   ``provenance.unsupported_claims`` 必须非空且 ``unsupported_claim_rate`` 必须大于 0；
② ``test_counter_evidence_laundering_supported_turns_tooth_one_red`` —— 把所有 ``supported``
   强置 True（盘上真改：改的是影子副本里那一枚 ``app/agents/evidence.py``，被跟踪文件全程只读），
   ①那枚正文必须红，并点名是哪条断言被洗白；
③ ``test_clearing_claims_is_refused_as_a_zero_denominator`` —— 把 ``claims`` 清空，产品侧的
   拒绝点必须当场拒绝并写明 NOT_MEASURED／分母为零，不许交一枚 0.0 冒充达标。

全部离线：合成证据袋加合成夹具。不打模型、不打索引、不读在册夹具，也不改判分器与采集器一字节
（判据 3：那两枚件本单只调用，改它们换来的绿一律退回）。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from inspect import getsource
from pathlib import Path

import pytest

from app.agents.contracts import (
    CLAIMS_MEASURED,
    CLAIMS_NOT_MEASURED,
    AgentResult,
    Claim,
    Evidence,
)
from app.agents.evidence import (
    CLAIM_SUPPORT_CONTAINMENT_FLOOR,
    ClaimsDenominatorError,
    aggregate_agent_result,
    atomize_answer_claims,
    build_agent_result,
    build_answer_claims,
    claim_support_scan,
    claims_denominator_state,
    eval_payload_for_answer,
    new_evidence_bag,
    record_document_hits,
    require_measured_claims_denominator,
)
from app.quality import eval as scorer

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_MODULE_SOURCE = Path(__file__).resolve()
EVIDENCE_SOURCE = REPO_ROOT / "app" / "agents" / "evidence.py"
COLLECTOR_SOURCE = REPO_ROOT / "scripts" / "collect_evaluation_answers.py"

#: 合成题面：一条被本轮 chunk 撑住的断言，加一条本轮证据里一个字都没有的断言。
_DOC_SOURCE = "差旅制度.pdf"
_DOC_CHUNK = 3
_DOC_REF = f"{_DOC_SOURCE}#chunk={_DOC_CHUNK}"
_DOC_EXCERPT = "员工国内差旅的住宿与餐费合并计算，单次报销上限为 5000 元，超出部分需提供审批单。"
_SUPPORTED_ASSERTION = "单次报销上限为 5000 元"
_WASHED_ASSERTION = "超出上限的部分可由财务总监口头豁免"
_ANSWER = f"{_SUPPORTED_ASSERTION}。{_WASHED_ASSERTION}。"
_FIXTURE_ROW = {
    "id": "r699-offline-01",
    "question": "差旅报销的单次上限是多少？",
    "must_contain": ["5000"],
    "requires_evidence": True,
    "category": "制度问答",
}

#: 反证刀口：产品侧唯一的定夺点。这一枚行被改成「无条件 True」就是判据 1 点名退回的假账形状，
#: 所以它必须逐字唯一命中 —— 命中不到就说明代码形状变了，刀会空响。
SUPPORT_DECISION_LINE = "supported=bool(refs) and ratio >= CLAIM_SUPPORT_CONTAINMENT_FLOOR,"
LAUNDERED_DECISION_LINE = "supported=True,"

#: 反证走影子副本道（在册规矩 R253：被跟踪文件全程只读，变异只落副本）。
#: 这一列文件恰好是「产品造 claims」与「判分器读 claims」两条腿的全部依赖，实测可离线 import。
SHADOW_MIRROR = (
    "app/__init__.py",
    "app/agents/__init__.py",
    "app/agents/contracts.py",
    "app/agents/evidence.py",
    "app/common/__init__.py",
    "app/common/logger.py",
    "app/common/model_budget.py",
    "app/quality/eval.py",
)

VICTIM_SOURCE = '''
"""R699 反证刀的受试体：在影子副本里跑判据 2① 那一枚正文，一个字节都不另写。"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

SHADOW_ROOT = Path(__file__).resolve().parent
if str(SHADOW_ROOT) not in sys.path:
    sys.path.insert(0, str(SHADOW_ROOT))

TEST_MODULE = sys.argv[1]
spec = importlib.util.spec_from_file_location("r699_tooth_under_test", TEST_MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

try:
    readings = module.tooth_one_readings(Path(tempfile.mkdtemp(prefix="r699-victim-")))
except AssertionError as laundering:
    print("VICTIM_RED::" + str(laundering))
    raise SystemExit(1)
print("VICTIM_GREEN::" + json.dumps(readings, ensure_ascii=False, default=str))
'''


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _document_bag(excerpt: str = _DOC_EXCERPT, source: str = _DOC_SOURCE, chunk: int = _DOC_CHUNK) -> dict:
    bag = new_evidence_bag()
    record_document_hits(bag, query="差旅报销的单次上限", hits=[
        {"source": source, "content": excerpt, "chunk_index": chunk, "_score": 0.81},
    ])
    return bag


def _answer_result() -> AgentResult:
    return build_agent_result(worker="doc", answer=_ANSWER, bag=_document_bag())


def _load_collector():
    """按文件路径载采集器本尊（判据 3：它只被调用，不被复制，也不被改）。"""
    spec = importlib.util.spec_from_file_location("r699_collector", COLLECTOR_SOURCE)
    assert spec is not None and spec.loader is not None, "载不到采集器：%s" % COLLECTOR_SOURCE
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _collected_line(result: AgentResult) -> dict:
    """答案件 → 采集器认的那一行：搬运规则一个字节都不新写，直接用在册那枚 ``build_answer``。"""
    return _load_collector().build_answer(
        _FIXTURE_ROW,
        eval_payload_for_answer(result),
        measured_ms=900.0,
        answer_source="r699-offline",
    )


def _scored_report(line: dict, fixture_dir: Path) -> dict:
    fixture = fixture_dir / "r699-offline-fixture.jsonl"
    fixture.write_text(json.dumps(_FIXTURE_ROW, ensure_ascii=False) + "\n", encoding="utf-8")
    return scorer.evaluate_evaluation_set(fixture, lambda row: line)


def tooth_one_readings(fixture_dir: Path) -> dict:
    """判据 2① 的正文（无 pytest 依赖，反证刀跑的就是这一份）。

    🔴 每一条红话都必须点名被洗白的那枚断言：判据 2② 要求「红了还说得出是谁被洗白」。
    """
    result = _answer_result()
    assert len(result.claims) >= 2, (
        f"两句答案只交出 {len(result.claims)} 枚断言：claims 没有逐条原子化，"
        f"「{_WASHED_ASSERTION}」这一条被并进了别的断言里")
    line = _collected_line(result)
    assert "claims" in line, (
        f"采集器那一行没带 claims 键：产品交出的 {len(result.claims)} 枚断言在半路被丢了，"
        f"无证据的那一条是「{_WASHED_ASSERTION}」")
    provenance = scorer.evaluate_provenance(line)
    assert provenance["unsupported_claims"] == [_WASHED_ASSERTION], (
        f"无证据支撑的断言没有被判成 unsupported —— 被洗白的是「{_WASHED_ASSERTION}」，"
        f"本轮证据只有 {_DOC_REF}；实到 unsupported_claims={provenance['unsupported_claims']}")
    report = _scored_report(line, fixture_dir)
    assert report["unsupported_claim_rate"] > 0, (
        f"分母明明活着，unsupported_claim_rate 还是 {report['unsupported_claim_rate']}："
        f"被洗白的断言是「{_WASHED_ASSERTION}」")
    return {
        "claims_n": len(result.claims),
        "unsupported": provenance["unsupported_claims"],
        "rate": report["unsupported_claim_rate"],
        "evidence_coverage": provenance["evidence_coverage"],
    }


def test_an_unsupported_assertion_gives_the_rate_a_denominator(tmp_path: Path) -> None:
    """牙一（判据 2①）：一条无证据断言 ⇒ unsupported_claims 非空且 rate 大于 0。"""
    readings = tooth_one_readings(tmp_path)
    assert readings["unsupported"] == [_WASHED_ASSERTION]
    assert readings["rate"] > 0, readings


def test_the_answer_contract_publishes_the_claims_cell() -> None:
    """判据 1：``claims`` 这一格必须在答案契约里，且交得出①文本②布尔③具体出处。"""
    assert "claims" in AgentResult.model_fields, "答案契约里没有 claims 这一格：C④ 的分母还是零"
    assert set(Claim.model_fields) >= {"text", "supported", "evidence_refs"}, Claim.model_fields
    result = _answer_result()
    supported = [claim for claim in result.claims if claim.supported]
    assert [claim.text for claim in supported] == [_SUPPORTED_ASSERTION], result.claims
    for claim in supported:
        assert claim.evidence_refs, f"supported=True 却没有指认证据：{claim.text}"
        assert all(re.search(r"#chunk=\d+$", ref) for ref in claim.evidence_refs), claim.evidence_refs
    assert _DOC_REF in supported[0].evidence_refs, supported[0].evidence_refs


def test_claims_are_atomized_one_assertion_per_row() -> None:
    """判据 1 的「逐条」：一段多句正文要切出多枚断言，编号碎片不许冒充一条。"""
    answer = (
        f"{_SUPPORTED_ASSERTION}。预算调整需提前三个工作日申请。"
        "1. 附件清单见制度第三章\n- 第四章另计"
    )
    assertions = atomize_answer_claims(answer)
    assert len(assertions) >= 4, assertions
    assert "1" not in assertions and "V1" not in assertions, assertions
    assert atomize_answer_claims("") == [], "空正文不该交出断言"
    assert atomize_answer_claims("是。") == ["是。"], "切不出可用断言时必须整段兜底，绝不交零枚"


def test_a_citation_marker_is_not_a_witness() -> None:
    """判据 1 的红线：引用标记只指路不背书；带不带标记，判定必须一模一样。"""
    bare = "超出上限的部分可由财务总监口头豁免"
    marked = f"{bare} [来源: {_DOC_SOURCE}]"
    evidence = build_answer_claims(marked, _answer_result().evidence)
    assert [claim.supported for claim in evidence] == [False], evidence
    assert claim_support_scan(bare, _answer_result().evidence) == claim_support_scan(
        marked, _answer_result().evidence), "引用标记改变了判定：这一枚就是假账通道"


def test_a_bare_number_in_a_true_half_sentence_is_still_a_hallucination() -> None:
    """半句真话配一枚假数字：字面重叠够高也不许过 —— 数字必须在同一条证据里逐字见到。"""
    forged = "单次报销上限为 8800 元，超出部分需提供审批单"
    claims = build_answer_claims(forged, _answer_result().evidence)
    assert [claim.supported for claim in claims] == [False], claims
    assert claims[0].support_ratio >= CLAIM_SUPPORT_CONTAINMENT_FLOOR, (
        f"这一条字面重叠本就够高，靠的必须是数字闸门：{claims[0]}")


def test_aggregate_judges_the_final_answer_against_merged_evidence() -> None:
    """终答那一轮的 ``supported`` 由合并后的本轮证据决定（两条腿的袋都在场才算本轮）。"""
    doc_leg = build_agent_result(worker="doc", answer=_SUPPORTED_ASSERTION, bag=_document_bag())
    policy_leg = build_agent_result(worker="rule", answer="", bag=None)
    turn = aggregate_agent_result(
        {"doc": doc_leg, "rule": policy_leg},
        answer=f"{_SUPPORTED_ASSERTION}。{_WASHED_ASSERTION}。",
        request_id="r699-offline",
    )
    by_text = {claim.text: claim for claim in turn.claims}
    assert by_text[_SUPPORTED_ASSERTION].supported is True, by_text[_SUPPORTED_ASSERTION]
    assert by_text[_WASHED_ASSERTION].supported is False, by_text[_WASHED_ASSERTION]
    assert turn.request_id == "r699-offline"


def test_clearing_claims_is_refused_as_a_zero_denominator(monkeypatch, tmp_path: Path) -> None:
    """牙三（判据 2③）：claims 被清空 ⇒ 拒绝点当场拒绝并写明 NOT_MEASURED／分母为零。

    判分器与采集器一字节不许改，所以「零分母不许翻绿」这一格只能落在产品侧：本函数同时把
    那枚假绿当场量出来给本单看 —— 清空 claims 之后 ``unsupported_claim_rate`` 就是 0.0。
    """
    line = _collected_line(_answer_result())
    assert [claim["supported"] for claim in line["claims"]] == [True, False], line["claims"]
    monkeypatch.setattr("app.agents.evidence.build_answer_claims", lambda answer, evidence: [])
    #: 定夺点被摘掉之后，产品侧连货都发不出来 —— 拒绝发生在构造那一刻，不在下游。
    with pytest.raises(ClaimsDenominatorError) as refusal:
        build_agent_result(worker="doc", answer=_ANSWER, bag=_document_bag())
    note = str(refusal.value)
    assert CLAIMS_NOT_MEASURED in note and "分母为零" in note, note

    laundered = dict(line, claims=[])
    assert scorer.evaluate_provenance(laundered)["unsupported_claims"] == []
    fake_green = _scored_report(laundered, tmp_path)["unsupported_claim_rate"]
    assert fake_green == 0.0, f"清空 claims 之后量到的不是那枚假 0.0：{fake_green}"
    assert claims_denominator_state(laundered["answer"], laundered["claims"]) == CLAIMS_NOT_MEASURED
    with pytest.raises(ClaimsDenominatorError):
        require_measured_claims_denominator(laundered["answer"], laundered["claims"])


def test_an_empty_answer_has_no_denominator_and_says_so() -> None:
    """没有正文就没有分母：那一格写 NOT_MEASURED，不拒绝发货（拒绝的是有正文却零枚）。"""
    assert claims_denominator_state("", []) == CLAIMS_NOT_MEASURED
    require_measured_claims_denominator("", [], worker="doc")
    assert claims_denominator_state("有正文", [Claim(text="有正文", supported=False)]) == CLAIMS_MEASURED


def test_the_scorer_reads_exactly_the_keys_the_product_publishes() -> None:
    """契约双向钉：判分器按字面读的键名，产品侧一枚都不能少、也不能各写一套。"""
    ruler = getsource(scorer.evaluate_provenance)
    for key in ('"claims"', '"supported"', '"text"', '"unsupported_claims"'):
        assert key in ruler, f"判分器不再读 {key}：本单的键名契约要先跟着改，不许静默失配"
    payload = eval_payload_for_answer(_answer_result())
    assert set(payload) >= {"answer", "evidence", "claims"}, payload.keys()
    assert all(set(claim) >= {"text", "supported"} for claim in payload["claims"]), payload["claims"]


def test_claims_assembly_costs_no_io_on_the_hot_path() -> None:
    """判据 5：组装断言是纯内存搬运 —— AST 现读，不许它碰任何一次 IO。"""
    forbidden = {"httpx", "requests", "socket", "subprocess", "sqlite3", "redis", "chromadb"}
    tree = ast.parse(EVIDENCE_SOURCE.read_text(encoding="utf-8"))
    wanted = {
        "atomize_answer_claims", "claim_support_scan", "build_answer_claims",
        "require_measured_claims_denominator", "eval_payload_for_answer",
    }
    seen: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in wanted:
            continue
        seen.add(node.name)
        names = {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}
        attributes = {item.value.id for item in ast.walk(node)
                      if isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name)}
        hit = names & forbidden or attributes & forbidden
        assert not hit, f"{node.name} 在热路径上引用了 {sorted(hit)}"
    assert seen == wanted, f"少了函数，本钉没量到：{sorted(wanted - seen)}"


def _shadow_root(root: Path) -> Path:
    """复刻一棵最小影子根：副本必须与在盘源码逐字节相同，否则刀砍的就不是真码。"""
    shadow = root / "shadow"
    for rel in SHADOW_MIRROR:
        target = shadow / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / rel, target)
    (shadow / "r699_tooth_victim.py").write_text(VICTIM_SOURCE, encoding="utf-8")
    return shadow


def _run_victim(shadow: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(shadow), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(
        [sys.executable, str(shadow / "r699_tooth_victim.py"), str(TEST_MODULE_SOURCE)],
        cwd=str(shadow), env=env, capture_output=True, text=True, encoding="utf-8", timeout=180,
    )


def test_counter_evidence_laundering_supported_turns_tooth_one_red(tmp_path: Path) -> None:
    """牙二（判据 2②）：把所有 ``supported`` 强置 True ⇒ 牙一必须红，并点名被洗白的断言。

    盘上真改走影子副本道：被跟踪的 ``app/agents/evidence.py`` 全程只读，本钉收尾还要现查它
    一枚字节都没动过（禁区）。还原＝把副本重新按在盘源码逐字节覆写。
    """
    tracked = _sha256(EVIDENCE_SOURCE)
    source = EVIDENCE_SOURCE.read_text(encoding="utf-8")
    assert source.count(SUPPORT_DECISION_LINE) == 1, (
        "定夺那一枚行不再逐字唯一命中：刀会空响，先改这枚钉的刀口，别改产品")
    shadow = _shadow_root(tmp_path)
    copy_ = shadow / "app" / "agents" / "evidence.py"
    assert _sha256(copy_) == tracked, "影子副本与在盘源码不同字节：刀砍的不是真码"

    clean = _run_victim(shadow)
    assert clean.returncode == 0, f"干净副本里牙一就不绿，反证基线站不住：{clean.stdout}{clean.stderr}"

    copy_.write_text(source.replace(SUPPORT_DECISION_LINE, LAUNDERED_DECISION_LINE), encoding="utf-8")
    assert _sha256(copy_) != tracked, "洗白没落到盘上：这一刀是空的"
    red = _run_victim(shadow)
    assert red.returncode != 0, (
        f"把所有 supported 强置 True，牙一还绿着 —— 那枚牙不咬东西：{red.stdout}")
    output = f"{red.stdout}{red.stderr}"
    assert "VICTIM_RED::" in output, f"受试体不是以断言失败收尾的：{output[-400:]}"
    assert _WASHED_ASSERTION in output, f"红了却没点名被洗白的断言：{output[-400:]}"

    shutil.copyfile(EVIDENCE_SOURCE, copy_)
    assert _sha256(copy_) == tracked, "跑完没还原：影子里留了一枚洗白的产品码"
    assert _sha256(EVIDENCE_SOURCE) == tracked, "反证刀动了被跟踪文件：判据 3 的禁区"
    restored = _run_victim(shadow)
    assert restored.returncode == 0, f"还原之后牙一还不绿：{restored.stdout}{restored.stderr}"
