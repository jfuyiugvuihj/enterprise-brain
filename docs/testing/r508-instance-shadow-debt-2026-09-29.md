# R508 · 实例桩影子债的全仓账（2026-09-29）

基点 `8857a8d`（R499 并树那一笔），工作树 `C:/Users/fengx/PycharmProjects/be-r500`，起单 dirty=0。
本单只治 R499 纸上点名的三枚 `bind`；其余同族形状一律进这张账排队，一枚没动。

## 1. 病灶与治法（改前一律 `git show 8857a8d:<path>`，不拿 `HEAD` 当改前）

pytest 9.1.1 的 `MonkeyPatch.setattr` 只在 target 是**类**时走 `target.__dict__.get(name)` 取旧值；
对实例它取 `getattr` 出来的绑定方法，`undo()` 再把它 `setattr` 回实例 `__dict__`。teardown 之后那枚
对象永久多出一份方法影子，从此遮蔽类属性——后面任何一枚打在类上的桩都读不到调用，跳文件次序假红。

| 件:行（基点） | 改前 | 改后（盘上现在） |
| --- | --- | --- |
| `tests/test_r384_migrations_first_refuses_at_the_ask_exit.py:266` | `monkeypatch.setattr(chat.session_registry, "bind", _spy)` | `monkeypatch.setattr("app.storage.sessions.SessionRegistry.bind", lambda self, *_a, **_k: _spy())` |
| `tests/test_routing_intent_and_terminal_state.py:81` | `monkeypatch.setattr(chat.session_registry, "bind", lambda *a, **k: None)` | `monkeypatch.setattr("app.storage.sessions.SessionRegistry.bind", lambda self, *_a, **_k: None)` |
| `tests/test_sse_sources.py:284` | `monkeypatch.setattr(chat.session_registry, "bind", lambda *a, **k: None)` | `monkeypatch.setattr(SessionRegistry, "bind", lambda self, *_a, **_k: None)` |

三枚都只换桩目标：断言一字未动、枚数未增未减，`_spy` 记录器本体也没碰（类目标多收一枚 `self`，
用一行 lambda 转接）。前两枚走 pytest 的两参点分串形式 `setattr("mod.Cls.attr", value)`，pytest 会把
`Cls` 解析成类对象，走 `__dict__` 那条干净路径；第三枚那件本来就 `from app.storage.sessions import
SessionRegistry`，直接用类对象。

### 改前三枚单跑的现读（探针在 `pytest_sessionfinish` 读 `vars(session_storage.session_registry)`）

| 件 | 单跑 | 共享单例 `vars()` | 判定 |
| --- | --- | --- | --- |
| `test_r384_migrations_first_refuses_at_the_ask_exit.py` | 26 passed | `['_lock', '_records', 'bind', 'metadata_path']` | 影子漏在**进程级单例**上，🔴 |
| `test_routing_intent_and_terminal_state.py` | 7 passed | `['_lock', '_records', 'bind', 'metadata_path']` | 同上，🔴 |
| `test_sse_sources.py` | 14 passed / 4 skipped | `['_lock', '_records', 'metadata_path']` | 干净：`patch_offline`（`:136`）先把 `chat.session_registry` 换成一枚 tmp 实例，影子落在那枚一次性对象上，出不了本件 |

所以 R499 纸上那句「三枚现读 `vars(chat.session_registry)` 都多出 `bind`」只有前两枚成立，
第三枚同形但今天不外溢。本单照样把它改到类上（同族形状不留第二份），危级在这张账里分开记。

## 2. 尺子（与在册静态格 `tests/test_r508_the_bind_stub_stays_on_the_class.py` 同源）

- 形状：`setattr(target, "name", value)` 三参形式 + pytest 的两参点分串 `setattr("mod.Cls.attr", value)`。
- 目标种类：`class`（末段是 app 里定义的类名）/ `singleton`（`<模块别名>.<app 模块级单例名>`）/ `module`（末段是本件导入的模块）/ `local`（其余，多半是件内自造对象）。
- 契约名 = 凡把桩打在 app **类**上的属性名，全派生，不写死名单。
- 「把方法打在实例上」= 目标种类是 `singleton`/`local` 且属性名在 app 里确实是某枚类的方法。

| 口径 | 基点 `8857a8d` | 治后（本树盘上） |
| --- | --- | --- |
| setattr 形状总数 | 2209 | 2210 |
| class 目标 | 29 | 32 |
| singleton 目标 | 11 | 8 |
| module 目标 | 1760 | 1761 |
| local 目标 | 409 | 409 |
| 契约名枚数 | 14 | 15（新增 `bind`） |
| 打在非类目标上的**方法**桩 | 76 | 73 |

口径说明：两列都含本单新钉自身——`tests/test_r508_the_bind_stub_stays_on_the_class.py` 里那一枚
`mp.setattr(cache, "get_redis", ...)` 是模块目标桩，只往 `module` 那一格加一；它不往 `singleton`/`local` 两格添任何一枚方法桩。基点那一列的 76 = 治后的 73 + 本单治掉的三枚 `bind`。

## 3. 治后全册：仍然打在非类目标上的方法桩（73 枚，逐枚点名）

排队用的名册，本单**一枚没动**。`契约名` 那一列 = 这个名字今天已经有别的件打在类上（那就是 R499 那一炸的当量）。

| # | 文件:行 | 目标 | 方法名 | 种类 | 契约名 | 对象存活域 / 危级 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `tests/test_r112_prompt_packing.py:587` | `dataset_storage.dataset_registry` | `get_active_by_filename` | `singleton` | 否 | 🔴 进程级单例（app/storage/datasets.py `dataset_registry = DatasetRegistry(...)`） |
| 2 | `tests/test_r112_prompt_packing.py:1105` | `dataset_storage.dataset_registry` | `get_active_by_filename` | `singleton` | 否 | 🔴 进程级单例（app/storage/datasets.py `dataset_registry = DatasetRegistry(...)`） |
| 3 | `tests/test_r122_stub_honesty.py:269` | `dataset_storage.dataset_registry` | `get_active_by_filename` | `singleton` | 否 | 🔴 进程级单例（app/storage/datasets.py `dataset_registry = DatasetRegistry(...)`） |
| 4 | `tests/test_r185_text_columns_single_path.py:69` | `dataset_storage.dataset_registry` | `get_active_by_filename` | `singleton` | 否 | 🔴 进程级单例（app/storage/datasets.py `dataset_registry = DatasetRegistry(...)`） |
| 5 | `tests/test_r189_label_column_from_query.py:80` | `dataset_storage.dataset_registry` | `get_active_by_filename` | `singleton` | 否 | 🔴 进程级单例（app/storage/datasets.py `dataset_registry = DatasetRegistry(...)`） |
| 6 | `tests/test_r342_trend_undated_exit.py:175` | `data.dataset_registry` | `active_records` | `singleton` | 否 | 🔴 进程级单例（app/storage/datasets.py `dataset_registry = DatasetRegistry(...)`） |
| 7 | `tests/test_r451_open_section_header.py:141` | `dataset_storage.dataset_registry` | `get_active_by_filename` | `singleton` | 否 | 🔴 进程级单例（app/storage/datasets.py `dataset_registry = DatasetRegistry(...)`） |
| 8 | `tests/test_r462_query_data_tuple_keys.py:70` | `dataset_storage.dataset_registry` | `get_active_by_filename` | `singleton` | 否 | 🔴 进程级单例（app/storage/datasets.py `dataset_registry = DatasetRegistry(...)`） |
| 9 | `tests/test_document_delete_catalog.py:108` | `chat.retriever` | `delete_document` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:98 `retriever = DocumentRetriever()`） |
| 10 | `tests/test_document_delete_catalog.py:377` | `chat.retriever` | `delete_document` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:98 `retriever = DocumentRetriever()`） |
| 11 | `tests/test_document_delete_catalog.py:461` | `chat.retriever` | `delete_document` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:98 `retriever = DocumentRetriever()`） |
| 12 | `tests/test_document_delete_catalog.py:519` | `chat.retriever` | `delete_document` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:98 `retriever = DocumentRetriever()`） |
| 13 | `tests/test_document_index_publication.py:651` | `publisher.registry` | `publish` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 14 | `tests/test_document_ownership.py:405` | `chat.retriever` | `delete_document` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:98 `retriever = DocumentRetriever()`） |
| 15 | `tests/test_index_publication.py:137` | `registry` | `publish` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 16 | `tests/test_knowledge_graph_verification.py:254` | `graph` | `_reject_in_memory_write` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 17 | `tests/test_prefiltering.py:789` | `type(collection)` | `query` | `local` | 否 | ⚪ 其实是**类目标**（现取类型），不是实例影子 |
| 18 | `tests/test_private_model_routing.py:98` | `retrieval_pipeline.model` | `chat` | `local` | 否 | 🔴 进程级单例（app/rag/retrieval_pipeline.py:36 `model = ModelHandler()`） |
| 19 | `tests/test_r103_graph_unconfigured_exit.py:126` | `graph._store` | `upsert` | `local` | **是** | ⚪ KnowledgeGraph 是件内自造的（r103:124 `_mount_graph(monkeypatch, KnowledgeGraph())`），影子出不了本件 |
| 20 | `tests/test_r103_graph_unconfigured_exit.py:163` | `graph` | `add_relation` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 21 | `tests/test_r103_graph_unconfigured_exit.py:222` | `graph` | `add_relation` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 22 | `tests/test_r103_graph_unconfigured_exit.py:256` | `store` | `upsert` | `local` | **是** | 🟠 进程级字典里那一枚（app/common/open_platform.py:38 `_STORE`，:143 造 `JsonPersistenceAdapter`）；配置路径一变就重造，影子随之消失 |
| 23 | `tests/test_r105_slo_contract.py:449` | `socket.socket` | `__init__` | `local` | 否 | ⚪ 其实是**类目标**（stdlib 的 `socket.socket`，静态尺子看不见 stdlib），不是实例影子 |
| 24 | `tests/test_r106_open_platform_unconfigured_exit.py:115` | `store` | `upsert` | `local` | **是** | 🟠 进程级字典里那一枚（app/common/open_platform.py:38 `_STORE`，:143 造 `JsonPersistenceAdapter`）；配置路径一变就重造，影子随之消失 |
| 25 | `tests/test_r109_rewrite_offline_guard.py:69` | `chat.model_handler` | `chat` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:99 `model_handler = ModelHandler()`） |
| 26 | `tests/test_r109_rewrite_offline_guard.py:305` | `chat.model_handler` | `chat` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:99 `model_handler = ModelHandler()`） |
| 27 | `tests/test_r126_rewrite_prev_turn.py:75` | `chat.model_handler` | `chat` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:99 `model_handler = ModelHandler()`） |
| 28 | `tests/test_r126_rewrite_prev_turn.py:119` | `chat.model_handler` | `chat` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:99 `model_handler = ModelHandler()`） |
| 29 | `tests/test_r130_text_unencodable_is_named_refusal.py:565` | `mirror` | `build_rows` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 30 | `tests/test_r141_lane_behavior.py:494` | `chat.model_handler` | `chat` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:99 `model_handler = ModelHandler()`） |
| 31 | `tests/test_r141_lane_behavior.py:660` | `chat.model_handler` | `chat` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:99 `model_handler = ModelHandler()`） |
| 32 | `tests/test_r172_lane_across_hitl.py:161` | `chat.model_handler` | `chat` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:99 `model_handler = ModelHandler()`） |
| 33 | `tests/test_r194_queue_denials_and_flat_list.py:366` | `chat.retriever` | `list_documents` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:98 `retriever = DocumentRetriever()`） |
| 34 | `tests/test_r194_queue_denials_and_flat_list.py:426` | `chat.retriever` | `list_documents` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:98 `retriever = DocumentRetriever()`） |
| 35 | `tests/test_r200_restricted_single_source.py:396` | `chat.retriever` | `list_documents` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:98 `retriever = DocumentRetriever()`） |
| 36 | `tests/test_r29_thinking_tax.py:258` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 37 | `tests/test_r29_thinking_tax.py:302` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 38 | `tests/test_r29_thinking_tax.py:316` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 39 | `tests/test_r29_thinking_tax.py:338` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 40 | `tests/test_r29_thinking_tax.py:362` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 41 | `tests/test_r29_thinking_tax.py:1086` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 42 | `tests/test_r32_lane_contract.py:160` | `chat.model_handler` | `chat` | `local` | 否 | 🔴 进程级单例（app/api/v1/chat.py:99 `model_handler = ModelHandler()`） |
| 43 | `tests/test_r38_cached_tokens_honesty.py:57` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 44 | `tests/test_r38_native_input_tokens.py:107` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 45 | `tests/test_r43a_native_cached_tokens.py:106` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 46 | `tests/test_r44_hot_index_chroma.py:499` | `harness.index` | `rank` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 47 | `tests/test_r50_incremental_index.py:331` | `library.retriever.collection` | `get` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 48 | `tests/test_r50_resumable_rebuild.py:722` | `live.registry` | `publish` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 49 | `tests/test_r51_observation_is_passive.py:471` | `stage_timing.default_stage_ledger()` | `report` | `local` | 否 | 🔴 进程级单例（app/common/stage_timing.py:846 返回模块级 `default_ledger`） |
| 50 | `tests/test_r51_observation_is_passive.py:511` | `socket.socket` | `__init__` | `local` | 否 | ⚪ 其实是**类目标**（stdlib 的 `socket.socket`，静态尺子看不见 stdlib），不是实例影子 |
| 51 | `tests/test_r592_chat_entry_routes_by_the_switch.py:195` | `instance.embedding` | `embed_query` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 52 | `tests/test_r592_one_knob_one_default.py:246` | `instance.embedding` | `embed_query` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 53 | `tests/test_r592_permission_order_on_the_pg_leg.py:245` | `instance.embedding` | `embed_query` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 54 | `tests/test_r59_chroma_untouched_on_pg_reads.py:156` | `instance.embedding` | `embed_query` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 55 | `tests/test_r59_pg_zero_rows_degrade.py:182` | `instance.embedding` | `embed_query` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 56 | `tests/test_r59_pg_zero_rows_degrade.py:317` | `instance.embedding` | `embed_query` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 57 | `tests/test_r59_pg_zero_rows_degrade.py:357` | `instance.embedding` | `embed_query` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 58 | `tests/test_r59_where_parity.py:353` | `instance.embedding` | `embed_query` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 59 | `tests/test_r59b_pg_read_switch.py:144` | `instance.embedding` | `embed_query` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 60 | `tests/test_r92_rewrite_thinking.py:201` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 61 | `tests/test_r92_rewrite_thinking.py:227` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 62 | `tests/test_r92_rewrite_thinking.py:248` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 63 | `tests/test_r92_rewrite_thinking.py:283` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 64 | `tests/test_r92_rewrite_thinking.py:300` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 65 | `tests/test_r92_rewrite_thinking.py:316` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 66 | `tests/test_r92_rewrite_thinking.py:336` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 67 | `tests/test_r92_rewrite_thinking.py:358` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 68 | `tests/test_r92_rewrite_thinking.py:372` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 69 | `tests/test_r92_rewrite_thinking.py:596` | `handler` | `_native_chat_request` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 70 | `tests/test_r94_eval_evidence_coverage.py:130` | `socket.socket` | `__init__` | `local` | 否 | ⚪ 其实是**类目标**（stdlib 的 `socket.socket`，静态尺子看不见 stdlib），不是实例影子 |
| 71 | `tests/test_resource_delete_cascade.py:361` | `artifact_store.registry` | `soft_delete` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |
| 72 | `tests/test_response_hygiene.py:369` | `intelligence._graph` | `add_relation` | `local` | 否 | 🔴 进程级单例（app/api/v1/intelligence.py:41 `_graph = KnowledgeGraph()`） |
| 73 | `tests/test_retrieval_pipeline_fallback.py:15` | `pipeline.bm25` | `build_index` | `local` | 否 | ⚪ 件内自造对象（目标是本件里的局部名字），影子出不了本件 |

### 读这张账的三条结论

1. **今天就会炸的：0 枚。** 本单治掉的三枚是仅有把「契约名 + 进程级单例」两件事同时占住的桩。
2. **同族且名字已经进契约集合的：3 枚** —— `tests/test_r103_graph_unconfigured_exit.py:126`、
   `tests/test_r103_graph_unconfigured_exit.py:256`、`tests/test_r106_open_platform_unconfigured_exit.py:115`
   都把 `upsert` 打在实例上，而 `upsert` 今天已经被 `tests/test_r80_app_identity_collision.py:603` 打在
   `JsonPersistenceAdapter` 类上。实测两对同跑仍绿（`r103+r80` 24 passed、`r106+r80` 23 passed，09-29 现取）：
   `:126` 那一枚的影子落在件内自造的 `KnowledgeGraph()._store` 上，本来就出不了本件；`:256` 与 `:115` 落在
   `_STORE["store"]` 那一枚跨件存活的对象上，今天没炸只因为配置路径一变就重造 store、影子跟着旧对象一起被丢掉——
   **这是运气，不是设计**：谁把 `_STORE` 的重造路径改成复用，这两枚就会变成 R499 那一炸。
3. **`dataset_registry` 那一族 8 枚是下一单的最佳目标**：目标是 app 模块级单例（与 R499 同形），
   只是 `get_active_by_filename` / `active_records` 今天还没有人打在 `DatasetRegistry` 类上，所以不炸。
   在册静态格已经把这条线钉住：一旦有人先打在类上，任何一枚打在 `dataset_registry` 上的桩当场红。

## 4. 尺子自己的两处盲区（下一单若接手，请连这两处一起收紧）

- `chat.retriever` / `chat.model_handler` / `intelligence._graph` / `default_stage_ledger()` /
  `retrieval_pipeline.model` / `_STORE["store"]` 都是**跨件存活**的进程级对象，但它们的写法不在
  「同一文件里 `X = 本文件类(...)`」这一枚形状里，静态尺子把目标判成 `local`。上表用人工存活域补了标注。
- `socket.socket` / `type(collection)` / `io.open` / `builtins.open` 其实不是实例影子（一枚是 stdlib 类、
  一枚是现取类型、两枚是模块目标），静态尺子看不见 stdlib，只能靠上表那一列标注区分。
  因此「契约名打在局部对象上」那枚冻结账里，`__init__` 这类名字一旦被谁打在 app 类上，
  `socket.socket.__init__` 那两枚会误入账——今天没有这枚契约名，账是稳的；写下来是为了让接手的人知道边界。

## 5. 附带发现：本单自己踩到的一枚跨件全局态（已在本件里治干净）

把 7 枚件按乱序同跑时，`tests/test_routing_intent_and_terminal_state.py::test_unproductive_turn_fails_instead_of_completing`
红成 `{"detail":"idempotency_key_required"}`。取证结论：**红的是本单新钉的重放，不是那枚件本身**——
`app/common/cache.py::check_rate_limit` 用的 `ratelimit:admin` 是一枚进程级 sorted set（60 秒窗口、每分钟 10 次），
本件在一枚进程里把三枚件的真实 `/ask` 请求重放十几遍，把 `admin` 的额度吃光，排在后面的 routing 撞上
「超限」道，`/ask` 改走可靠队列入队分支，而那枚件的载荷不带 `idempotency_key` → 400。
这就是 R499 那一族病的另一个 lever（跨件进程级全局态），只是这次的污染方是本单自己。
治法：`_quarantine_cache_state` 在每一枚重放里把 `cache.get_redis` 改道到一次性实例（模块目标，undo 干净，
进程级那一枚一个字节不动），限流计数与答案缓存都溅不到共享那枚上。改道之后两形都绿（见 §6）。

## 6. 读数

以下都是**执行层自报**（基点 `8857a8d`，本树盘上态）：

- `tests/test_r508_the_bind_stub_stays_on_the_class.py` 单跑：9 passed
- 两形复跑（同 7 枚件）：
  - 正序 `r384 → routing → sse → r508 → r499 → r179 → r397`：127 passed / 4 skipped
  - 乱序 `r397 → r179 → r499 → r508 → sse → routing → r384`：127 passed / 4 skipped
- 反证刀三枚全咬：把其中任意一枚退回实例桩 ⇒ 运行期审计与静态格同时红，窗尾 `restored=True`、
  盘上文件 sha16 恒定（红句原文随交付交回）。
- 没跑 `scripts/run_gate.py`（本单令下禁跑），没起服务、没碰容器、没打模型、没连库写、没 commit。

## 7. 没做到的

- §3 名册里 73 枚同族形状一枚没治（写域只给了那三枚 `bind`）；其中 §3 结论 2 那 3 枚是今天唯一和契约名重叠的，留给下一单。
- `dataset_registry` 那一族没有配「打在类上」的对照桩，所以在册静态格对它是**空转**状态：真要是
  哪天出事，得靠运行期审计那格抓——那一格今天只重放本单这三枚件，没把 8 枚 dataset 件也重放一遍。
- §4 两处盲区只写在纸上，尺子本身没收紧。
- 本单的复跑只用同一枚 venv（`企业智脑/.venv`）与本树码；没有跑全量门，门内是否还有别的次序组合
  会把这族病炸出来，只有总控独担那一遍才知道。

