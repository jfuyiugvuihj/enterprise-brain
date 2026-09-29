# R499 · 一枚既有的跨件顺序依赖：会话归属谓词被实例影子遮蔽（2026-09-29）

范围：tests-only，全程离线（进程内 TestClient，零起服务 / 零模型 / 零库）。工作树 `be-r499`，基点
`092fb34`（detached，进门 dirty=0，`git merge-base --is-ancestor 092fb34 HEAD` rc=0 现取）。
执行层不 commit、不 push、不建分支；本单货由总控验收后代提交。

## 1. 病灶与最小复现（一对件 + 一句顺序）

```
python -m pytest tests/test_r397_read_legs_refuse_a_missing_table.py tests/test_r179_chat_denials.py \
    -o addopts= -p no:cacheprovider -q --tb=short
```

修前（本树与主树、以及控制跑 `be-r496@438d67d` 三处同一读数）：

```
1 failed, 64 passed
FAILED tests/test_r179_chat_denials.py::test_the_ownership_predicate_stays_the_single_source_of_truth
  AssertionError: chat.py 没走 is_owned_by：归属判定被就地抄了第二份
  assert [] == ['r179-session-mine']
tests\test_r179_chat_denials.py:256: AssertionError
```

顺序反过来（r179 在前）65 passed。全量门按字母序 r179 也排在 r397 之前，所以门里今天不炸——它是
**潜伏**的：显式点名两枚件、按失败清单 re-run、换分发口径，任一条都会把它炸成假红（事故 #81 那一族）。
最小复现甚至可以再缩一枚格：`pytest tests/test_r397_...py tests/test_r179_...py::test_the_ownership_predicate_stays_the_single_source_of_truth`
同样红。

## 2. 根因（逐枚取证之后才动手）

探针件（跑完即删，未进树）排在 r397 之后现读：

| 假设 | 现读 | 结论 |
| --- | --- | --- |
| `sys.modules["app.storage.sessions"]` 被 r397 换过（`importlib.reload`） | 探针 `id(module)` 与 `sys.modules` 里那枚相同；r397 全文零 `importlib`/`reload` | 否 |
| `SessionRegistry` 类对象被换 | `type(chat.session_registry) is session_storage.SessionRegistry` → True | 否 |
| 注册表单例被换 | `chat.session_registry is session_storage.session_registry` → True | 否 |
| r397 装 overlay / 走 R253 影子根 | r397 全文零 `_temp_edit_overlay` 导入 | 否 |
| r397 改了 `DATABASE_URL` / env 未复原，动到 R56、R134 两枚闸门 | r397 只有 `monkeypatch.setenv("APP_ENV", ...)`；跑后探针 `os.environ["APP_ENV"]` → None，`ENTERPRISE_BRAIN_PYTEST_CHROMA_DIR` 仍在场，R56 那格 `blocked connect attempts to host model port: 0` 两形未变 | 否 |
| **共享单例上长出一份实例影子** | r397 跑后 `vars(chat.session_registry)` = `['_lock', '_records', 'is_owned_by', 'metadata_path']`，出厂实例 = `['_lock', '_records', 'metadata_path']`；多出来那枚 = `<bound method SessionRegistry.is_owned_by of <SessionRegistry object>>` | **是** |

机理：`tests/test_r397_read_legs_refuse_a_missing_table.py:175`（基点原文）把归属谓词打在**实例**上——
`monkeypatch.setattr(chat.session_registry, "is_owned_by", lambda *_a, **_k: True)`。pytest 9.1.1 的
`MonkeyPatch.setattr`（`.venv/Lib/site-packages/_pytest/monkeypatch.py`）只在 target 是**类**时才
`oldval = target.__dict__.get(name, NOTSET)`（源码注释："avoid class descriptors like
staticmethod/classmethod"）；对实例它取的是 `getattr` 出来的**绑定方法**。`undo()` 里
`if value is not NOTSET: setattr(obj, name, value)`，于是把那份绑定方法**写回实例 `__dict__`**。
teardown 之后实例字典里永久留着 `is_owned_by`，从此遮蔽 `SessionRegistry.is_owned_by`，而
`tests/test_r179_chat_denials.py:253` 的桩正打在类属性上——`seen` 读不到调用，`assert [] ==
['r179-session-mine']`。

这不是产品码的毛病：`app/api/v1/chat.py:738` 与 `:3883` 都走 `session_registry.is_owned_by`，
`app/storage/sessions.py:148` 仍是唯一判定处，归属判定没有被就地抄第二份。**要动的只有污染方的打桩姿势**。

## 3. 修法

1. `tests/test_r397_read_legs_refuse_a_missing_table.py`
   - `:48` 新增 `from app.storage import sessions as session_storage`；
   - `:176-182` 把桩从实例改到**类**上（pytest 对类目标走 `__dict__`，undo 干净），并原地留一枚常驻牙
     `assert "is_owned_by" not in chat.session_registry.__dict__`。
2. `tests/test_r179_chat_denials.py` **一字未动**：两枚在册断言（`status_code == 404` 与
   `seen == [MINE_SESSION]`）保持原样；没有 `skip` / `xfail` / `serial`，没有 `addopts`，没动
   `scripts/run_gate.py`，没动评测集。
3. 新件 `tests/test_r499_the_ownership_predicate_survives_any_file_order.py`（6 格，见 §4）。

修后终态（同一枚探针形状，现读）：r397 跑完 `vars(chat.session_registry)` 回到出厂三枚，
`shadowed names = []`。

## 4. 判据实测读数（09-29 本树现取，解释器 = 主树 `.venv`，`-o addopts= -p no:cacheprovider -q`）

| # | 命令 | 读数 |
| --- | --- | --- |
| 判据① 形 A | `pytest r397 r179` | **65 passed**，0 failed（17.05 s） |
| 判据① 形 B | `pytest r179 r397` | **65 passed**，0 failed（11.30 s） |
| 判据① 加新件 | `pytest r397 r179 r499` | **71 passed**，0 failed（15.55 s） |
| 判据① 反序加新件 | `pytest r499 r384 r179 r397` | **97 passed**，0 failed（15.81 s）——证明 `bind` 那笔同族在册债不会把新牙误判成假红 |
| 新件单跑 | `pytest r499` | **6 passed**，0 failed（14.20 s） |
| 姿势件相邻 | `pytest r253_no_test_rewrites_a_tracked_file r466_mutation_does_not_leak r253_shadow_root_holds_the_mutation` | **28 passed**（35.51 s）——本件写盘形态与变异还原姿势都被这两枚在册钉认下 |
| 修前对照 | `pytest r397 r179`（改码前同树现取） | 1 failed / 64 passed，红句见 §1 |

新件六格：

- `:241` `test_the_predicate_contract_holds_on_both_sides_of_the_replay` — 顺序无关契约钉。在同一枚进程里
  先现跑 r179 那一格**本体**（绿），再重放 r397 的 `_world` 并让它出场，再跑一次（仍绿）。它不赌 pytest
  在盘上收集到的次序，所以门里怎么分发都验得到。
- `:256` `test_the_shared_singleton_carries_no_shadow_of_a_class_patched_predicate` — 运行期跨件牙：
  凡排在它之前跑完的件漏出实例影子就当场点名；另附两枚身份断言（类与单例都没被换），把 §2 的取证结论钉在场上。
- `:277` `test_no_test_file_patches_a_class_patched_predicate_onto_an_instance` — 静态牙：全仓
  `tests/test_*.py` 一次解析，把契约名打在非类目标上的每一处点名到文件行号，与次序无关。
- `:286` `test_the_revert_anchor_is_the_base_line_it_claims_to_be` — 基点自证：`092fb34` 必须是 HEAD 的
  祖先，且刀锚那一行确实长在基点那份文件里（不靠 `git show HEAD:` 那种会炸的形状）。
- `:296` `test_reverting_the_r397_line_goes_red_in_the_shadow_root` — 判据②那把刀（§5 K1）。
- `:338` `test_the_r397_in_place_catch_bites_on_an_already_shadowed_singleton` — 第二把刀（§5 K2）。

**契约名是派生的，不是写死的**：`_class_patched_names()`（`:156`）扫全仓 `tests/**`，凡
`setattr(<...>SessionRegistry, "<名字>", ...)` 就打进集合。今天 = {`is_owned_by`}。将来谁再往这枚类上
加一种类级契约（`bind`、`get_active`……），那两枚牙自动把它纳入尺子——这正是「对未来又长出一枚跨件
全局态也有牙」的落点，而不是一句「请保持顺序」的祈祷。

## 5. 反证刀表

| 刀 | 落点 | 姿势 | 咬住 | 读数 |
| --- | --- | --- | --- | --- |
| K1 | `tests/test_r397_read_legs_refuse_a_missing_table.py` 里 `_world` 修好的那四行代码 → 退回基点 `092fb34` 那一行原文 | `overlay.ShadowEdit`（`execs_module = False`）＋ `r466.install_mutation`：变异只落 %TEMP% 影子副本，窗内只把变异的 `_world` 装进**本件自己按路径装载的视图模块**，不碰 `sys.modules` 里 pytest 收的那枚 | `r179::test_the_ownership_predicate_stays_the_single_source_of_truth`（本体，非复制断言） | 窗内先现读 `shadowed == ['is_owned_by']`（否则判「刀在空转」），当场红句原文 `chat.py 没走 is_owned_by：归属判定被就地抄了第二份`；盘上 sha16 `77752eca3ae19eb1 -> 77752eca3ae19eb1`，`restored=True`、`shadow_clean=True`、`tracked-file-untouched`；出门 `_restore_instance_dict` 收回影子，再跑同一格回绿 |
| K2 | 不动盘：手工伪造 K1 已证明会漏出的那枚形状 `vars(registry)["is_owned_by"] = <bound method>` | 显式 setup/teardown（`snapshot` + `finally` 还原） | r397 原地那枚常驻牙（`:181-182`） | `_world` 自己当场抛出，消息含「就地抄的影子」；出门影子收回，`_instance_shadows` 回到 snapshot 形状 |

两把刀都在 `pytest` 运行里跑，不是纸面描述；两枚「刀在空转」的守卫断言（`shadowed == [PREDICATE]`、
`isinstance(caught, AssertionError)`）使 K1 无法退化成假证明。

同族在册债（本单写域外，只在纸上点名，不动手）：`bind` 同样被三枚件打在实例上，teardown 后现读
`vars(chat.session_registry)` 多出 `'bind'`——`tests/test_r384_migrations_first_refuses_at_the_ask_exit.py:266`、
`tests/test_routing_intent_and_terminal_state.py:81`、`tests/test_sse_sources.py:284`。今天没有任何契约打在
类上的 `bind`，所以它不炸；一旦有人那样打，§4 那两枚牙会当场点名这三枚。要不要现在就改成类上打桩，请总控裁。

## 6. 没做到 / 留给总控

- **全量门没跑**：同窗有别的 Agent，明令禁止，未跑 `scripts/run_gate.py`。并树后请总控按同一 HEAD
  复跑并与看板最新绿票对账（枚数随每笔并树变化，别拿历史数字当尺）。
- **dirty 态与干净树两遍**：本件只交出 dirty 态读数（apply 未 commit）；`git commit` 之后的干净树复跑
  归总控，尤其要覆盖 `tests/test_r499_*` 与 `tests/test_r253_no_test_rewrites_a_tracked_file.py`
  （后者扫 `tests/**/*.py`，会把这枚新件一起扫进去）。
- 新件在 `-n 6 --dist loadfile` 下的并发形状只做了静态推演：它开影子窗时会在本 worker 复刻一份 `app/**`
  （R253 既有开销），且不与别的件共享窗口对象；未实测并行跑分。
- 产品侧零改动（按工单：根因不在 `app/**`，取证见 §2）。

## 7. 硬不变量复核（出门现取）

- `rg -c classification_blocked app/` → 0 命中（见交回单）。
- 新件零 Chroma 依赖、零 Chroma 写点；PGVector 仍是生产向量库口径，本件不碰读后端。
- `git status --porcelain` 出门只有两枚：`M tests/test_r397_read_legs_refuse_a_missing_table.py`
  与 `?? tests/test_r499_the_ownership_predicate_survives_any_file_order.py`（加本这份文档），
  探针件 `tests/_r499_probe_tmp.py` 已删。