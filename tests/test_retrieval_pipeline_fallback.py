def test_cross_encoder_missing_does_not_break_pipeline_preload(monkeypatch):
    from app.rag import retrieval_pipeline

    monkeypatch.setattr(retrieval_pipeline, "CrossEncoder", None)

    reranker = retrieval_pipeline.CrossEncoderReranker(model_path="dummy-model")
    reranker._load_model()

    assert reranker._model is None
    assert reranker.rerank("查询制度", [{"content": "制度一"}, {"content": "制度二"}], top_k=1) == [
        {"content": "制度一"},
    ]

    pipeline = retrieval_pipeline.RetrievalPipeline()
    monkeypatch.setattr(pipeline.bm25, "build_index", lambda: None)

    pipeline.preload()


def test_cross_encoder_fallback_keeps_top_k_behavior(monkeypatch):
    from app.rag import retrieval_pipeline

    monkeypatch.setattr(retrieval_pipeline, "CrossEncoder", None)

    reranker = retrieval_pipeline.CrossEncoderReranker(model_path="dummy-model")
    docs = [
        {"content": "第一条制度", "source": "a.txt"},
        {"content": "第二条制度", "source": "b.txt"},
    ]

    ranked = reranker.rerank("制度", docs, top_k=1)

    assert ranked == docs[:1]
