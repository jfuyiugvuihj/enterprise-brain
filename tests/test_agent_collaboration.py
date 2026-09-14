from app.agents.contracts import AgentResult, Evidence, MetricContext
from app.agents.critic import review_agent_results
from app.agents.planner import build_task_plan
from langchain_core.messages import AIMessage, HumanMessage


def test_agent_result_keeps_evidence_metrics_and_confidence_label():
    result = AgentResult(
        worker="doc",
        status="success",
        answer="超出住宿费标准的部分由员工个人承担。",
        evidence=[
            Evidence(
                source_type="document",
                source_name="差旅费报销制度.pdf",
                locator="第3页",
                excerpt="超出住宿标准的部分由个人承担。",
            )
        ],
        confidence=0.88,
        confidence_label="引用充分",
    )

    assert result.worker == "doc"
    assert result.evidence[0].locator == "第3页"
    assert result.confidence_label == "引用充分"


def test_critic_accepts_consistent_results_with_evidence():
    results = [
        AgentResult(
            worker="doc",
            status="success",
            answer="住宿费标准为500元/晚。",
            evidence=[
                Evidence(
                    source_type="document",
                    source_name="差旅费报销制度.pdf",
                    locator="第3页",
                    excerpt="住宿费标准为500元/晚。",
                )
            ],
            metrics=[
                MetricContext(
                    metric_name="住宿费标准",
                    definition="公司制度规定的单晚住宿上限",
                    unit="元/晚",
                )
            ],
        ),
        AgentResult(
            worker="data",
            status="success",
            answer="市场部本月住宿费为650元/晚。",
            evidence=[
                Evidence(
                    source_type="table",
                    source_name="2026_business_analysis_test.xlsx",
                    locator="Sheet1!住宿费",
                    excerpt="市场部住宿费：650",
                )
            ],
        ),
    ]

    review = review_agent_results(results)

    assert review.passed is True
    assert review.recommended_action == "accept"
    assert review.confidence >= 0.75
    assert review.issues == []


def test_critic_requests_retry_when_result_has_no_evidence():
    review = review_agent_results(
        [
            AgentResult(
                worker="data",
                status="success",
                answer="本月费用增长了23%。",
            )
        ]
    )

    assert review.passed is False
    assert review.recommended_action == "retry_retrieval"
    assert review.missing_evidence


def test_planner_creates_parallel_tasks_for_combined_business_question():
    tasks = build_task_plan(
        "分析市场部本月差旅费用，结合住宿费制度判断超标责任，并生成趋势图和审批建议"
    )

    workers = {task["worker"] for task in tasks}
    assert {"data", "doc", "chart", "approval"} <= workers
    assert len({task["task_id"] for task in tasks}) == len(tasks)
    assert all(task["status"] == "pending" for task in tasks)


def test_reflect_node_persists_critic_review_in_graph_state():
    from app.agents.nodes import reflect_node

    result = AgentResult(
        worker="doc",
        status="success",
        answer="制度结论",
        evidence=[
            Evidence(
                source_type="document",
                source_name="制度.pdf",
                locator="第1页",
                excerpt="制度原文",
            )
        ],
    )
    state = {
        "messages": [
            HumanMessage(content="制度问题"),
            AIMessage(content="制度结论"),
        ],
        "agent_results": {"doc": result.model_dump()},
        "reflect_count": 0,
    }

    update = reflect_node(state)

    assert update["review_result"]["passed"] is True
    assert update["review_result"]["recommended_action"] == "accept"
    assert update["retry_count"] == 0


def _dispatch_rounds(question, tasks, max_rounds=6):
    """Drive ``route_main`` until every planned step has been dispatched once.

    Each dispatched worker is marked as completed, which is what the graph does between
    supersteps, so the next round sees the dependency layer as satisfied.
    """
    from app.agents.orchestrator import route_main

    done: dict[str, str] = {}
    rounds: list[set[str]] = []
    for _ in range(max_rounds):
        result = route_main(
            {
                "messages": [HumanMessage(content=question), AIMessage(content="")],
                "plan": tasks,
                "worker_results": done,
            }
        )
        if isinstance(result, str):
            break
        nodes = {getattr(item, "node", None) for item in result if hasattr(item, "node")}
        if not nodes:
            break
        rounds.append(nodes)
        for node in nodes:
            done[node] = f"{node} 已完成"
    return rounds


def test_route_main_uses_planner_workers_for_combined_question():
    """多步计划按依赖分层派发：先分析与检索，图表留到依赖就绪后的单独一轮。

    ``chart``/``export`` 在编译时带 ``interrupt_before``，只要它们出现在待发集合里，
    整个 superstep 会在任何任务执行前停下，同批 doc/data 的结果一起丢失。浏览器验收
    里看到的 ``worker_count: 0`` + 空正文就是这么来的，所以旧版"一轮全派发"不是
    契约而是缺陷。
    """
    question = "分析市场部本月差旅费用，结合住宿费制度判断超标责任，并生成趋势图"
    rounds = _dispatch_rounds(question, build_task_plan(question))

    assert rounds[0] == {"data", "doc"}
    assert "chart" not in rounds[0]
    assert set().union(*rounds) >= {"data", "doc", "chart", "approval"}
    chart_round = next(index for index, nodes in enumerate(rounds) if "chart" in nodes)
    assert chart_round > 0
    assert rounds[chart_round] == {"chart"}


def test_route_main_includes_approval_worker_for_approval_question():
    """审批预审要等证据检索完成的那一轮之后才派发，不能在同一 superstep 里空跑。"""
    from app.agents.orchestrator import route_main

    question = "单笔报销金额达到5000元和20000元时，分别需要谁审批，并说明制度依据？"
    tasks = [
        {"worker": "doc", "task_id": "doc-1", "status": "pending", "depends_on": []},
        {"worker": "approval", "task_id": "approval-1", "status": "pending", "depends_on": []},
    ]

    first = route_main(
        {
            "messages": [HumanMessage(content=question), AIMessage(content="")],
            "plan": tasks,
        }
    )
    assert any(getattr(item, "node", None) == "doc" for item in first)
    assert not any(getattr(item, "node", None) == "approval" for item in first)

    rounds = _dispatch_rounds(question, tasks)
    assert rounds[0] == {"doc"}
    assert {"approval"} in rounds
