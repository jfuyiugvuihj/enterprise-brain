# R714 · `app/api/v1/data.py` 拿 `str(exc) == …` 认拒绝（同一族形状：用类型而不是原句）

**号**：R714　**性质**：总控亲签（R710 执行层停下交回件 ③）　**基点**＝派工那一刻主树 HEAD 现取　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 一手事实（R710 现读，凭据纸 `docs/testing/r710-2026-10-06.md` 第五节）

- 那格叫 `_OWNER_SCOPE_ERROR`，比较的是**数据集**那一条拒绝原句。R710 给属主拒绝配了名字（`app/storage/artifacts.py::ArtifactOwnerScopeMissing`），也**没碰**这条腿的成败——但今天盘上同一族形状有两处：一处认类型、一处认原句。
- 认原句的罪不在「今天能不能过」，在原句一改（改标点都算）它就静默失效：失效之后越权面读起来像成功。

## 判据（每条可失败）

1. 改按异常类型认（`ArtifactOwnerScopeMissing` 或 dataset 侧的对应具名类型），盘上不再留任何一处 `str(exc) ==` 比拒绝句的写法；判据形态＝`rg` 谓词现取零命中（派工词里给出谓词原文），不许写行号。
2. 反证牙两枚：① 造一枚「同类型、不同原句」的拒绝 ⇒ 钉必须仍认得出（今天的写法在这里必红）；② 造一枚「同原句、不同类型」的冒牌 ⇒ 必须不认。
3. 隔离判定不许放宽：dataset 侧那一条的既有语义一字不动，本单只换认法；不许顺手把 R716 那一格（生产 `users.department` 全空）拿来翻绿。
4. 卫兵不许坏：`tests/test_r439_assembly_never_fakes_a_label.py`／`tests/test_r710_export_leg_tells_a_refusal_honestly.py` 复跑仍绿；`tickets_index.py --verify` rc=0；控制符各 0。
5. 交付：同名件两态读数＋未跟踪逐枚点名＋凭据纸 `docs/testing/r714-<开工日>.md`。

## 写域（只许这些）

`app/api/v1/data.py`（只许那一处认拒绝的写法）／新增 `tests/test_r714_*.py`／`docs/tickets/R714-*.md`／`docs/testing/r714-<开工日>.md`

## 禁区（踩线即退回）

`app/storage/artifacts.py`（R710 已并）／`app/api/v1/chat.py`／`frontend/**`／评测夹具与夜窗量具／`docs/handoff/**`／主树任何路径。
