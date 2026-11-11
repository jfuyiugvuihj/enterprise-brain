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


class _BoomEncoder:
    """代表一次会失败的模型加载：容器里没有外网时就是这种结果。"""

    calls: list = []

    def __init__(self, model_path, device=None):
        type(self).calls.append(model_path)
        raise OSError("huggingface.co unreachable")


def _reset_calls():
    _BoomEncoder.calls = []


def test_reranker_load_failure_degrades_instead_of_raising(monkeypatch):
    """预加载曾经直接把进程打死：缺模型必须退回 RRF，而不是抛到 startup。"""
    from app.rag import retrieval_pipeline

    _reset_calls()
    monkeypatch.setattr(retrieval_pipeline, "CrossEncoder", _BoomEncoder)
    monkeypatch.setenv("RERANKER_ALLOW_DOWNLOAD", "1")

    reranker = retrieval_pipeline.CrossEncoderReranker(model_path="BAAI/bge-reranker-base")
    reranker._load_model()

    assert reranker._model is None
    assert reranker.unavailable_reason.startswith("reranker_load_failed:")
    docs = [{"content": "第一条"}, {"content": "第二条"}]
    assert reranker.rerank("制度", docs, top_k=1) == docs[:1]

    # 失败被锁存：后续请求不再重复付出一次超时代价
    reranker._load_model()
    assert len(_BoomEncoder.calls) == 1


def test_reranker_does_not_touch_the_network_by_default(monkeypatch):
    """私有化部署的默认必须是离线：没有本地模型就不构造 CrossEncoder。"""
    from app.rag import retrieval_pipeline

    _reset_calls()
    monkeypatch.setattr(retrieval_pipeline, "CrossEncoder", _BoomEncoder)
    monkeypatch.delenv("RERANKER_ALLOW_DOWNLOAD", raising=False)

    reranker = retrieval_pipeline.CrossEncoderReranker(model_path="BAAI/bge-reranker-base")
    reranker._load_model()

    assert _BoomEncoder.calls == []
    assert reranker.unavailable_reason == "reranker_model_not_local"
    assert reranker._model is None


def test_reranker_uses_a_mounted_model_dir(monkeypatch, tmp_path):
    """挂载卷里的模型目录通过 RERANKER_MODEL_DIR 指定。"""
    from app.rag import retrieval_pipeline

    model_dir = tmp_path / "bge-reranker-base"
    model_dir.mkdir()
    monkeypatch.setenv("RERANKER_MODEL_DIR", str(model_dir))

    seen = []

    class _OkEncoder:
        def __init__(self, model_path, device=None):
            seen.append((model_path, device))
            self.model_path = model_path

    monkeypatch.setattr(retrieval_pipeline, "CrossEncoder", _OkEncoder)

    reranker = retrieval_pipeline.CrossEncoderReranker()

    assert reranker.model_path == str(model_dir)
    reranker._load_model()
    assert seen == [(str(model_dir), "cpu")]
    assert reranker.unavailable_reason == ""
