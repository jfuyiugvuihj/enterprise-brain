from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_document_upload_recovers_token_from_local_storage():
    source = (ROOT / "frontend" / "src" / "components" / "DocPanel.vue").read_text(
        encoding="utf-8"
    )

    assert 'localStorage.getItem("eb_token")' in source


def test_document_upload_shows_an_animated_progress_indicator():
    source = (ROOT / "frontend" / "src" / "components" / "DocPanel.vue").read_text(
        encoding="utf-8"
    )

    assert 'class="sr-only" role="status">正在解析入库<' in source
    assert 'class="upload-progress-ring"' in source
    assert 'aria-hidden="true"' in source
    assert 'class="upload-progress-ring"\n          aria-hidden="true"' in source
    assert 'class="upload-progress-ring"\n          role="status"' not in source
    assert "@keyframes upload-progress-spin" in source


def test_document_upload_reports_real_upload_progress_and_processing_phase():
    source = (ROOT / "frontend" / "src" / "components" / "DocPanel.vue").read_text(
        encoding="utf-8"
    )

    assert "progress: 0" in source
    assert "phase: 'uploading'" in source
    assert "onUploadProgress" in source
    assert "item.progress" in source
    assert "item.phase = 'processing'" in source


def test_document_upload_has_progress_fallback_when_browser_hides_total_size():
    source = (ROOT / "frontend" / "src" / "components" / "DocPanel.vue").read_text(
        encoding="utf-8"
    )

    assert "import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'" in source
    assert "const item = reactive({" in source
    assert "startProgressTimer(item)" in source
    assert "if (event.total)" in source
    assert "if (!event.total || event.loaded >= event.total)" in source
    assert "const limit = item.phase === 'processing' ? 99 : 60" in source
    assert "async function uploadFilesParallel(files)" in source
    assert "await Promise.allSettled(tasks)" in source


def test_document_upload_marks_success_as_complete():
    source = (ROOT / "frontend" / "src" / "components" / "DocPanel.vue").read_text(
        encoding="utf-8"
    )

    assert "item.progress = 100" in source
    assert "item.phase = 'done'" in source
    assert 'class="upload-progress-bar"' in source
    assert "{{ item.progress }}%" in source
    assert "item.phase === 'done' ? '上传完成'" in source


def test_document_upload_refreshes_the_list_after_each_successful_response():
    source = (ROOT / "frontend" / "src" / "components" / "DocPanel.vue").read_text(
        encoding="utf-8"
    )

    assert "item.msg = res.data.message || '上传完成'" in source
    assert source.count("await loadDocs()") >= 4
    assert "params: { _ts: Date.now() }" in source


def test_document_upload_uses_unique_queue_keys_for_multiple_files():
    source = (ROOT / "frontend" / "src" / "components" / "DocPanel.vue").read_text(
        encoding="utf-8"
    )

    assert 'id: `${Date.now()}-${Math.random().toString(36).slice(2)}`' in source
    assert ':key="item.id"' in source
