# 数据分析文件列表 Implementation Plan

> **⚠️ 状态（2026-09-15 标注）**：**已实现并交付**——`DataPanel.vue` 的上传、列表、预览、下载链路真实，后端有 `/data-files` 目录接口。
> 本文件仅作历史切片存档。其产出的「数据文件列表」入口已在 2026-09-14 的裁定中与文档合并为**「喂料」**视图，见 `docs/frontend-plan-2026-09-14.md` §2。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为数据分析模块增加可持久查看、选择、预览和下载的 Excel/CSV 文件列表。

**Architecture:** 后端在现有 `DATA_DIR` 基础上提供文件目录接口，复用已有的安全文件名、预览和下载逻辑。前端 `DataPanel.vue` 增加文件列表状态和选择状态，上传成功后刷新列表并加载新文件，保持现有数据画像和预览弹窗。

**Tech Stack:** FastAPI、pandas、Vue 3、Axios、pytest、Vite。

## Global Constraints

- 数据分析只管理 `.xlsx`、`.xls`、`.csv`，不进入知识库索引。
- 所有路径必须经过现有 `_safe_data_filename` 或目录边界校验。
- 上传失败不能清除已有文件列表或当前预览。
- 前端显示加载中、空列表和解析失败状态。
- 不修改现有知识库上传、删除和预览行为。

---

### Task 1: Add Data File Listing API

**Files:**
- Modify: `C:\Users\fengx\PycharmProjects\企业智脑\app\api\v1\data.py`
- Test: `C:\Users\fengx\PycharmProjects\企业智脑\tests\test_data_file_catalog.py`

**Interfaces:**
- Produces `GET /api/v1/data-files`.
- Returns `{"files": [{"filename": str, "size": int, "size_label": str, "modified_at": str, "extension": str}]}`.

- [x] **Step 1: Write the failing test**

Add tests that monkeypatch `data.DATA_DIR`, create one `.xlsx`, one `.csv`, and one unsupported `.txt`, then assert only supported files are returned with metadata and newest-first ordering:

```python
def test_list_data_files_filters_formats_and_returns_metadata(tmp_path, monkeypatch):
    from app.api.v1 import data

    monkeypatch.setattr(data, "DATA_DIR", str(tmp_path))
    (tmp_path / "old.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "new.xlsx").write_bytes(b"placeholder")
    (tmp_path / "ignore.txt").write_text("ignore", encoding="utf-8")

    result = data.list_data_files()

    assert [item["filename"] for item in result["files"]] == ["new.xlsx", "old.csv"]
    assert result["files"][0]["extension"] == ".xlsx"
    assert result["files"][0]["size"] > 0
    assert result["files"][0]["size_label"]
    assert result["files"][0]["modified_at"]
```

- [x] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest tests/test_data_file_catalog.py::test_list_data_files_filters_formats_and_returns_metadata -v
```

Expected: FAIL because `list_data_files` does not exist.

- [x] **Step 3: Write minimal implementation**

Add a small formatter and route:

```python
DATA_EXTENSIONS = {".xlsx", ".xls", ".csv"}

def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"

@router.get("/data-files")
async def list_data_files():
    directory = Path(DATA_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    files = []
    for path in directory.iterdir():
        if not path.is_file() or path.suffix.lower() not in DATA_EXTENSIONS:
            continue
        stat = path.stat()
        files.append({
            "filename": path.name,
            "size": stat.st_size,
            "size_label": _format_size(stat.st_size),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            "extension": path.suffix.lower(),
        })
    files.sort(key=lambda item: item["modified_at"], reverse=True)
    return {"files": files}
```

- [x] **Step 4: Run test to verify it passes**

Run:

```powershell
pytest tests/test_data_file_catalog.py::test_list_data_files_filters_formats_and_returns_metadata -v
```

Expected: PASS.

### Task 2: Add Frontend File List State

**Files:**
- Modify: `C:\Users\fengx\PycharmProjects\企业智脑\frontend\src\components\DataPanel.vue`
- Test: `C:\Users\fengx\PycharmProjects\企业智脑\tests\test_data_file_catalog.py`

**Interfaces:**
- Consumes `GET /api/v1/data-files`.
- Reuses `GET /api/v1/data-files/{filename}/preview`.
- Keeps `dataFile` as the selected filename and `applyDataPreview` as the preview state updater.

- [x] **Step 1: Write the failing source-contract tests**

Add assertions that the component contains the list endpoint, file list state, loading/empty copy, and refresh after upload:

```python
def test_data_panel_has_file_catalog_and_refreshes_after_upload():
    source = (ROOT / "frontend" / "src" / "components" / "DataPanel.vue").read_text(encoding="utf-8")

    assert "data-files" in source
    assert "dataFiles" in source
    assert "loadDataFiles" in source
    assert "暂无数据文件" in source
    assert "await loadDataFiles()" in source
```

- [x] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest tests/test_data_file_catalog.py::test_data_panel_has_file_catalog_and_refreshes_after_upload -v
```

Expected: FAIL because the current component has no file catalog state or loader.

- [x] **Step 3: Implement the frontend catalog**

Add:

```javascript
const dataFiles = ref([])
const filesLoading = ref(false)
const filesError = ref('')

async function loadDataFiles(selectFilename = '') {
  filesLoading.value = true
  filesError.value = ''
  try {
    const res = await axios.get(`${API}/data-files`, { params: { _ts: Date.now() } })
    dataFiles.value = res.data.files || []
    const next = selectFilename || dataFile.value || dataFiles.value[0]?.filename || ''
    if (next) await selectDataFile(next)
  } catch (err) {
    filesError.value = err.response?.data?.detail || err.message || '数据文件列表加载失败'
  } finally {
    filesLoading.value = false
  }
}

async function selectDataFile(filename) {
  dataFile.value = filename
  const res = await axios.get(
    `${API}/data-files/${encodeURIComponent(filename)}/preview`,
    { params: { _ts: Date.now() } }
  )
  applyDataPreview(res.data)
}
```

Call `loadDataFiles()` from `onMounted`, call `await loadDataFiles(file.name)` after upload, and render a list before the profile card. Each file row must call `selectDataFile(file.filename)` and show filename, extension, size, and modified time. Include visible loading, empty, and error states.

- [x] **Step 4: Run source-contract test**

Run:

```powershell
pytest tests/test_data_file_catalog.py::test_data_panel_has_file_catalog_and_refreshes_after_upload -v
```

Expected: PASS.

### Task 3: Verify Integration

**Files:**
- Modify: `C:\Users\fengx\PycharmProjects\企业智脑\tests\test_data_file_catalog.py`

- [x] **Step 1: Add API behavior checks**

Verify an empty temporary directory returns `{"files": []}` and an existing `2026_business_analysis_test.xlsx` is listed by the running API.

- [x] **Step 2: Run focused backend tests**

Run:

```powershell
pytest tests/test_data_file_catalog.py tests/test_file_preview.py -v
```

Expected: PASS.

- [x] **Step 3: Build the frontend**

Run:

```powershell
npm run build
```

Working directory:

```text
C:\Users\fengx\PycharmProjects\企业智脑\frontend
```

Expected: exit code 0.

- [x] **Step 4: Verify the running API**

Use the admin token to call:

```text
GET http://localhost:8001/api/v1/data-files
GET http://localhost:8001/api/v1/data-files/2026_business_analysis_test.xlsx/preview
```

Expected: both return HTTP 200; the preview contains 6 rows and 8 columns.

- [x] **Step 5: Verify the browser UI**

In the frontend, open “数据分析”, confirm the file row appears, click it, and confirm the data profile and preview actions are visible. Refresh the page and confirm the file row remains.
