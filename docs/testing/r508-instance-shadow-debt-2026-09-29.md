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

- §3 名册里 73 枚同族形状一枚没治（写域只给了那三枚 `bind`）；其中 §3 结论 2 那 3 枚是今天唯一和契约名重叠的，留给下一单。 **→ R516 已治那三枚 `upsert`，其余同族见 §8.5。**
- `dataset_registry` 那一族没有配「打在类上」的对照桩，所以在册静态格对它是**空转**状态：真要是
  哪天出事，得靠运行期审计那格抓——那一格今天只重放本单这三枚件，没把 8 枚 dataset 件也重放一遍。
  **→ R516 已把这一族九枚 + 三枚 `upsert` 全部改到类目标，对照桩与运行期重放都补上了（§8.1/§8.6）。**
- §4 两处盲区只写在纸上，尺子本身没收紧。
- 本单的复跑只用同一枚 venv（`企业智脑/.venv`）与本树码；没有跑全量门，门内是否还有别的次序组合
  会把这族病炸出来，只有总控独担那一遍才知道。

## 8. R516 第二批（2026-09-29 续，基点 `85572c1`）

工作树 `C:/Users/fengx/PycharmProjects/be-r516`，起单 dirty=0。写域＝名册 §3 结论 2 的三枚 `upsert`
＋结论 3 点名的八枚 `dataset_registry`，另加**一枚运行期量出来的第 12 处**（`test_r192:391`，理由见
§8.2）；断言一字未动、逐枚枚数未增未减。新增牙在 `tests/test_r516_the_dataset_stubs_stay_on_the_class.py`。

### 8.1 落点（改前一律 `git show 85572c1:<path>`）

| # | 件:行（基点） | 改前目标 | 改后目标（盘上现在） | 属性名 |
| --- | --- | --- | --- | --- |
| 1 | `tests/test_r112_prompt_packing.py:587` | `dataset_storage.dataset_registry` | `dataset_storage.DatasetRegistry` | `get_active_by_filename` |
| 2 | `tests/test_r112_prompt_packing.py:1105` | 同上 | 同上 | `get_active_by_filename` |
| 3 | `tests/test_r122_stub_honesty.py:269` | 同上 | 同上 | `get_active_by_filename` |
| 4 | `tests/test_r185_text_columns_single_path.py:69` | 同上 | 同上 | `get_active_by_filename` |
| 5 | `tests/test_r189_label_column_from_query.py:80` | 同上 | 同上 | `get_active_by_filename` |
| 6 | `tests/test_r342_trend_undated_exit.py:175` | `data.dataset_registry` | `"app.storage.datasets.DatasetRegistry.active_records"`（两参点分串） | `active_records` |
| 7 | `tests/test_r451_open_section_header.py:141` | `dataset_storage.dataset_registry` | `dataset_storage.DatasetRegistry` | `get_active_by_filename` |
| 8 | `tests/test_r462_query_data_tuple_keys.py:70` | 同上 | 同上 | `get_active_by_filename` |
| 9 | `tests/test_r103_graph_unconfigured_exit.py:126` | `graph._store` | `JsonPersistenceAdapter`（类对象） | `upsert` |
| 10 | `tests/test_r103_graph_unconfigured_exit.py:256` | `store` | 同上 | `upsert` |
| 11 | `tests/test_r106_open_platform_unconfigured_exit.py:115` | `store` | 同上 | `upsert` |
| 12 | `tests/test_r192_ranking_count_and_empty_numeric.py:391`（**名册外，本单量出来收的**） | `install(dataset_storage.dataset_registry, ...)` | `install(dataset_storage.DatasetRegistry, ...)` | `get_active_by_filename` |

九枚 `dataset_registry` 与三枚 `upsert` 都只换挂载目标；类目标多收一枚 `self`，用 lambda 首参转接。
`r103:163`/`r103:222`（`graph.add_relation`，件内自造对象）**本单不收**，理由记在 §8.5。

### 8.2 第 12 枚凭哪条收进来

名册 §3 结论 3 那句「`dataset_registry` 那一族 8 枚是下一单的最佳目标」是**旧尺子的读数**：那把尺子只
认 `monkeypatch.setattr`／`patch`／属性赋值三形，而 `tests/test_r192_ranking_count_and_empty_numeric.py:386`
的助手函数 `install(owner, name, value)` 是**通用三参调用形**——裸 `setattr` 装桩、再用
`setattr(owner, name, getattr(owner, name))` 还原，teardown 之后进程级 `dataset_registry.__dict__`
里永久多出一枚绑定方法影子（09-29 探针现读：单跑该件后 `vars(dataset_registry)` 多出
`get_active_by_filename`）。它不修，本单那九枚改到类上就是**假绿**：r192 在同一枚 worker 里跑过之后，
那份实例影子会遮蔽类级桩，`get_active_by_filename` 读回真方法，两形合跑按次序出假红。所以它不是
「顺手多治一枚」，而是这一族能不能算治干净的**前置条件**。

### 8.3 在册静态格确实拦了人，走的是它自己给的出路

- 拦停现读（中间态证据）：只把 `tests/test_r122_stub_honesty.py` 一枚退回基点写法，
  `test_no_test_file_patches_a_class_patched_contract_onto_a_module_singleton` 当场红并点名其余七枚
  ——`get_active_by_filename` 一进契约名集合，留在单例上的桩全暴露。
- 出路：改到类目标。治后 `_class_patched_names` 15 → 17（新增 `get_active_by_filename`、
  `active_records`），`_singleton_patches == []`、`_local_patches == []`。
- 同件那格冻结账 `KNOWN_LOCAL_DEBTS` 原在册两枚（`r103`/`r106` 的 `upsert`）。本单把那三枚改到类上之后
  账目按事实**清空**：`fresh = seen - 账` 与 `seen == 账` 两半判据都还在，账空了以后任何一枚新的
  「契约名打在局部对象上」照样红——**只清账不摘牙，清空比原来严**（原来容两枚）。
- 没删格、没改弱、没 skip/xfail。R516 另交一格现跑 R508 那两格判据**本体**（不复制断言）自证：
  `tests/test_r516_the_dataset_stubs_stay_on_the_class.py::test_the_registered_grid_is_green_on_the_tree_it_punishes`。

### 8.4 尺子收紧之后的全仓读数（§4 那两处盲区已一并收掉）

扫的写法（`tests/**.py` 全 AST，不认正则之外的形状）：`X.setattr(obj,"n",v)` /
`X.setattr("mod.Cls.n",v)` / `patch("mod.Cls.n",v)` / `patch.object(obj,"n",v)` /
`X.patch("n",target=obj)` / `obj.n = v` / 通用三参调用形 `f(obj,"n",v)`。目标解析三张**派生**表：
app 里定义的类名（跨模块）、模块级 `x = Cls(...)` 单例名→类名、`def fn(): return x` 顺 return 追一层
——`chat.model_handler`、`stage_timing.default_stage_ledger()` 这类 §4 说「静态尺子判成 local」的形状，
今天起能被认成 `singleton` / `singleton-call`。基数由 `git show 85572c1:tests/**` 全仓重扫现取，
**不与 §2 那列（旧尺子，2209/2210）直接可比**。

| 口径 | 基点 `85572c1` | 本单治后（盘上） |
| --- | --- | --- |
| AST 里能装桩的形状总数 | 3167 | 3186 |
| `class` 目标 | 41 | 53 |
| `singleton`（含裸名 6、`X.fn()` 现取 1） | 36 | 27 |
| 本族（三个名字）打在非类目标上 | 12 | **0** |
| 打在进程级单例上的**方法**桩 | 28 | **19** |

那 28 → 19 的差额是 9 枚（八枚 `dataset_registry` ＋ r192 那枚裸 `setattr`）；三枚 `upsert` 的目标
（`graph._store` / `store`）在这把尺子上解析不出来，本来就不在单例账里——账目分开记，不写成「治了 12 枚」。

### 8.5 今天还剩 19 枚：逐枚点名，以及它们为什么今天不炸

冻结在 `SINGLETON_METHOD_STUB_ROSTER`（等号＋fresh 两半，多一枚少一枚都红）：

| 名字 | 目标（进程级单例） | 枚数 | 落点 |
| --- | --- | --- | --- |
| `chat` | `chat.model_handler`（`app/api/v1/chat.py:99`） | 8 | `test_r109:69/:305`、`test_r126:75/:119`、`test_r141:494/:660`、`test_r172:161`、`test_r32:160` |
| `delete_document` | `chat.retriever`（`app/api/v1/chat.py:98`） | 5 | `test_document_delete_catalog.py:108/:377/:461/:519`、`test_document_ownership.py:405` |
| `list_documents` | `chat.retriever` | 3 | `test_r194_queue_denials_and_flat_list.py:366/:426`、`test_r200_restricted_single_source.py:396` |
| `chat` | `retrieval_pipeline.model`（`app/rag/retrieval_pipeline.py:36`） | 1 | `test_private_model_routing.py:98` |
| `report` | `stage_timing.default_stage_ledger()`（`app/common/stage_timing.py:846`） | 1 | `test_r51_observation_is_passive.py:471` |
| `add_relation` | `intelligence._graph`（`app/api/v1/intelligence.py`） | 1 | `test_response_hygiene.py:369` |

**为什么不炸（现读，不是推测）**：09-29 全仓扫「打在类目标上的桩」，进契约集合的名字只有
`bind`、`upsert`、`get_active_by_filename`、`active_records`（加上其他件的类级桩共 17 枚名字），
`chat` / `delete_document` / `list_documents` / `report` / `add_relation` **一枚类级桩都没有**——
所以既没有类属性可被实例影子遮蔽（R499 那一炸的当量为零），R508 的单例格与本件的家族格也都不认它们。
`test_r51:511`/`test_r105:449` 那两枚 `socket.socket.__init__` 仍是 stdlib 类目标，不在本账。

**这 19 枚就是下一单的靶**：谁给这五枚名字里任何一枚配上第一枚类级桩，R508 那两格（单例格／已清空的
冻结账）与本件的家族格会当场逐枚点名——在 R508 旧尺子上它们是 `local`、在本件新尺子上是
`singleton`，两把都躲不掉。同批还得一起收 §3 结论 2 之外那两枚 `tests/test_r103_graph_unconfigured_exit.py:163`
与 `:222`：本单**故意不收**它们，因为把 `add_relation` 打上 `KnowledgeGraph` 类会让它立刻进契约集合，
而 `tests/test_response_hygiene.py:369`（进程级单例 `intelligence._graph`）不在本单写域——收了就是
拿别人的账换自己的绿。要么下一单把这两枚与那 19 枚一起治，要么一枚都别动。

### 8.6 运行期审计腿交的读数（执行层自报，09-29 现取）

11 枚件（十枚落点件＋`test_r80`，`upsert` 的类级契约长在它身上）在**同一枚子进程**里按盘上的字整跑，
探针每枚用例 teardown 读 `vars(obj) ∩ 类上本来就有的名字`，按文件名归账、不赌次序：
件 11 枚 / 用例 195 枚 / 现造 store 75 枚 / 正控装 2 量到 2 / 本族漏点 **0** 枚；
身份复核 `identity_ok=True`。两把反证刀都咬：

- 刀①（退回实例桩）：`r112:587` ⇒ 本件点名 + R508 **单例格**红；`r106:115` ⇒ R508 **冻结账**红
  （红句原文：`打在测试局部对象上的同族形状多了新账：[('tests/test_r106_open_platform_unconfigured_exit.py', 'upsert')]（治法：改到类目标，参照 SITES 那三行）`）；
  `r342:175`、`r192:391` ⇒ R508 那两格照旧绿，只有本件收紧后的腿点名（`r192` 那枚形如
  `(391, 'three-arg-call', 'singleton')`）——旧尺子看不见它，这一格如实记在 `SITES.tooth`。
- 刀②（摘掉运行期腿）：把重放清单摘成空 ⇒ `test_the_runtime_leg_measured_what_it_claims` 红，
  红句原文：`运行期审计腿没有量它声称量过的东西：这一族只跑了 0 枚用例（名册上的件合计 195 枚）`。
  变异只落 `tests/_temp_edit_overlay.py` 影子根，窗尾 `restored=True`、`shadow_clean=True`。

这腿今天交前自己炸过两回，都记进本件 docstring（腿不许把自己的毛病读成「零枚漏点」）：
①`__import__("app.storage.datasets")` 交回的是**头**那一枚包而不是叶子模块，身份复核在收尾钩子里抛
`AttributeError` ⇒ 内层会话 rc=1；②正控装在共享单例上，同一枚影子被「真名那格」监视器又报了一次
⇒ 读数 2 枚变 3 枚。修法把 caught 按标签分账，并把「真名那格也看见了」升成一枚判据（`real_watched_it_too`）。

### 8.7 附：本单顺手发现的三件纸账误差

1. §3 结论 3 那句「8 枚」漏了 r192 那一形（旧尺子看不见），本单收进账并写清凭据（§8.2）。
2. 五枚件的**工作树 EOL 被写成了纯 LF**（`r112`/`r185`/`r189`/`r451`/`r462`，09-29 现读 CRLF=0），
   与仓内 CRLF 约定相反——字节精确改写时按 dominant EOL 写回的这一步本来就该有。已全部还原 CRLF，
   `git diff` 仍只有本单那 23 增 18 删。
3. §2 那列 76 = 73 + 3 的口径只覆盖旧尺子；换成 §8.4 的尺子之后同仓读数是 28（基点）/19（治后），
   两把尺子的数字不要混着引用。
### 8.8 订正（本单自己制造的一枚纸面/盘面事故，09-29 23:0x 总控取证）

- 本单在字节精确改写 `tests/test_r508_the_bind_stub_stays_on_the_class.py` 时，误把成品写成另一枚
  文件名 `test_r508_the_bind_stub_stay_on_the_class.py`（少一枚 `s`）。两枚一度同时在盘上、字节相同，
  NTFS 在两个近名条目之间摇摆，于是出现「`git status` 同一瞬间既报 `D`（原名）又报 `??`（少 s 名）」、
  以及按原名 `open()`/`Test-Path` 报 ENOENT、而 `os.listdir` 仍列得出名字这类怪读数。
  后果是实的：那枚在册静态格靠 `THIS_FILE = TESTS_DIR / "test_r508_the_bind_stub_stays_on_the_class.py"`
  把自己从全仓扫描里剔出去，名字一失配，自剔除指向一枚不存在的文件 ⇒ 这把尺子当时量的不是它自称的东西。
- 处置：**不留新名字**。全部编辑已落回被跟踪的原名那枚（452 行，含 §8.3 那句 R516 订正与清空的
  `KNOWN_LOCAL_DEBTS`，sha16 `55cde150617f92b1`），少 s 那枚已删除（删除前逐字节比对确认两枚相同）。
  因此本纸 :34 / :51 / :173 三处对 `tests/test_r508_the_bind_stub_stays_on_the_class.py` 的指涉
  **仍然成立，一字未改**；`docs/testing/r515-frame-caliber-twin-returns-none.md` 同理。
- 教训（写给下一位做字节精确改写的人）：改在册钉件时**目标文件名一律从 `git ls-files` 现取**，
  不要手抄路径字符串；本仓同名近邻（`..._stays_...` / `..._stay_...`、r508 / r516）真的会撞。
  另：本轮为查该 ENOENT 而误起过一枚全仓 collect，把工作树里被跟踪的 `chroma_db/chroma.sqlite3`
  写脏过一次，已 `git checkout HEAD -- chroma_db/chroma.sqlite3` 就地还原；后续再出现的该枚 dirty
  按总控口径视为跑测试带的噪声——不提交、不清理、不拿它当判据。
