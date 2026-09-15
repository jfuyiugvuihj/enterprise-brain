from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_document_upload_recovers_token_from_local_storage():
    source = (ROOT / "frontend" / "src" / "components" / "DocPanel.vue").read_text(
        encoding="utf-8"
    )

    # 重指向（2026-09-15 集成后）：面板不再自己读 localStorage，token 统一由全站唯一
    # 的 HTTP 入口提供——行为没丢，位置变了。
    #   frontend/src/lib/http.js:7   export const TOKEN_KEY = 'eb_token'
    #   frontend/src/lib/http.js:34  return localStorage.getItem(TOKEN_KEY) || ''
    http_source = (ROOT / "frontend" / "src" / "lib" / "http.js").read_text(encoding="utf-8")

    assert "import { http, errorDetail } from '../lib/http'" in source
    assert "await http.post('/upload'" in source
    assert "export const TOKEN_KEY = 'eb_token'" in http_source
    assert "localStorage.getItem(TOKEN_KEY)" in http_source


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
    # 重指向：队列项改由工厂产出，但仍是 reactive（进度定时器依赖它的响应式）
    #   DocPanel.vue:50 function createUploadItem(file) / :51 return reactive({ / :151 调用点
    assert "function createUploadItem(file) {" in source
    assert "return reactive({" in source
    assert "const item = createUploadItem(file)" in source
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
    # 原先钉「await loadDocs() 至少出现 4 次」。loadDocuments→loadDocs 改名后真实值是 3
    # （DocPanel.vue:147 批量收尾 / :177 单文件成功分支 / :230 删除之后）。
    # 次数本身不是不变量，「刷新发生在成功分支内、且不发生在失败分支内」才是，
    # 故改成位置检查，另保留下限 3 钉住三处刷新都还在。
    upload_fn = source.split("async function uploadSingleFile(file) {", 1)[1]
    upload_fn = upload_fn.split("\nfunction onFileInput", 1)[0]
    success_path, sep, failure_path = upload_fn.partition("  } catch (err) {")
    assert sep, "uploadSingleFile 的 catch 分支不见了"
    assert "await loadDocs()" in success_path
    assert success_path.index("item.msg = res.data.message") < success_path.rindex("await loadDocs()")
    assert "await loadDocs()" not in failure_path
    assert source.count("await loadDocs()") >= 3
    assert "params: { _ts: Date.now() }" in source


def test_document_upload_uses_unique_queue_keys_for_multiple_files():
    source = (ROOT / "frontend" / "src" / "components" / "DocPanel.vue").read_text(
        encoding="utf-8"
    )

    assert 'id: `${Date.now()}-${Math.random().toString(36).slice(2)}`' in source
    assert ':key="item.id"' in source
