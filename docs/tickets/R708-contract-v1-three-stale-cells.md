# R708 · `docs/api/contract-v1.md` 三处过期 + 伪造 .xlsx 的 500 要落账（docs-only）

**号**：R708　**性质**：总控亲写（R700 并树时执行层 Mill 现读取回，禁区文件它没动）　**基点**＝开工那一刻主树 HEAD 现取　**执行时机**：🔴 排在 R702 之后——`docs/api/contract-v1.md` 此刻归 Schrodinger（R702 新键同步），两席同文件即写域冲突。

## 病形现取（R700 并树时现取，读数记在提交词与席纸）

1. R306 那一节仍写着旧形状，与 R700 落地的 `app/documents/knowledge_ingest.py` 那条入库腿对不上。
2. S5 兼容注记还挂着已经在树上改掉的行为。
3. Dataset File Delivery 那一节没点名 `app/api/v1/data.py::guard_dataset_name_conflict`：伪造 `.xlsx`（扩展名与内容不符）今天的真读数是 **400**，账面还留着 500 那一说。

## 判据（每条可失败）

1. 三处逐格改口，坐标一律 `文件::符号`；改完 `python scripts/lint_hand_copied_coordinates.py --check` rc=0、`python scripts/r638_doc_pointer_ruler.py` rc=0。
2. 契约一致性由在册尺证明，不由本单新增读 markdown 的用例证明：`python -m pytest tests/test_r132_contract_followup_sync.py -q` 仍绿；🔴 本单**禁止新增任何读 .md 的用例**（红线指标：读 markdown 的用例占比只降不升）。
3. 500→400 那一格必须写「现取读数 + 量具路径」，不许写「应当返回」；错误码字面与 `app/api/v1/data.py` 现读一致。
4. 交付：改动前后逐格点名 + 三枚尺的 rc + 控制符各 0 枚。

## 写域（只许这些）

`docs/api/contract-v1.md`／`docs/tickets/R708-*.md`／`docs/testing/r708-<开工日>.md`

## 禁区

产品码任何路径／`tests/**`（本单不新增钉子）／`frontend/**`／`docs/handoff/**` 的既有前置行／容器·镜像·模型·GPU。
