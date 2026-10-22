from app.common.identity import Principal


def test_retrieval_debug_report_records_scope_versions_and_trace(tmp_path):
    from app.rag.debug import run_retrieval_debug
    from app.trace.store import TraceStore

    class Pipeline:
        def search_for_principal(self, query, principal, top_k):
            assert principal.username == "alice"
            assert top_k == 3
            return [
                {
                    "content": "finance policy",
                    "source": "policy.pdf",
                    "classification": 2,
                    "department": "finance",
                    "_score": 0.91,
                }
            ], ["finance reimbursement policy"]

    principal = Principal(
        user_id="u-1",
        username="alice",
        permissions=["document.read"],
        department="finance",
        clearance=2,
    )
    trace_store = TraceStore(tmp_path / "trace.jsonl")

    report = run_retrieval_debug(
        "policy",
        principal,
        pipeline=Pipeline(),
        trace_store=trace_store,
        trace_id="trace-1",
        request_id="req-1",
        index_version_id="idx-2026-09-12",
        strategy_version="hybrid-v1",
        top_k=3,
    )

    assert report["index_version_id"] == "idx-2026-09-12"
    assert report["strategy_version"] == "hybrid-v1"
    assert report["permission_filter"] == {
        "$and": [
            {"classification": {"$in": [1, 2]}},
            {"department": {"$in": ["finance"]}},
        ]
    }
    assert report["rewrites"] == ["finance reimbursement policy"]
    assert report["stages"][-1]["name"] == "reranked"
    assert report["stages"][-1]["candidate_count"] == 1
    assert report["results"][0]["permission_checked"] is True

    replay = trace_store.replay("trace-1")
    assert replay[0]["event_type"] == "retrieval.completed"
    assert replay[0]["payload"]["index_version_id"] == "idx-2026-09-12"


def test_retrieval_debug_report_propagates_scope_errors_before_pipeline_runs(tmp_path):
    from app.rag.debug import run_retrieval_debug
    from app.rag.filters import RetrievalScopeError

    class Pipeline:
        def search_for_principal(self, query, principal, top_k):
            raise AssertionError("pipeline should not run without retrieval scope")

    try:
        run_retrieval_debug(
            "policy",
            None,
            pipeline=Pipeline(),
            trace_store=None,
            trace_id="trace-1",
            request_id="req-1",
        )
    except RetrievalScopeError as exc:
        assert exc.code == "authentication_required"
    else:
        raise AssertionError("anonymous debug retrieval must be rejected")
