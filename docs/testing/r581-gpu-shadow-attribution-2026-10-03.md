# R581 · GPU「Docker vGPU 影子」正面归因写进在册开窗前置闸（10-03）

单号 R581｜工作树 `be-r581`（基点 `dfc057b`，本席不 commit）｜解释器 = 主树 `.venv` + `-X utf8`
判据全文在 `docs/handoff/2026-09-15-backend-followup-requests.md` §153 四｜本篇是交回纸：逐判据读数（改前 vs 改后）＋九枚反证＋未跑的格子。

## 0 一句话

```text
改前：gpu_apps 只认「这枚计算进程的可执行文件在不在仓库里」=> 容器一用卡就 FAIL
      （pid=4 是 Windows System，这台机上它永远在）
改后：gpu_apps 三分法 CLEAN／ATTRIBUTED／FOREIGN，放行必须走完四腿可失败断言，任何一腿问不到落 UNMEASURED
```

🔴 本格不治任何时延读数：A①／A④ 一格都不因本笔变绿。「不证时延干净」那句是**码内固定输出**，不只是纸面声明。

## 1 本机现取的形状（10-03 09:5x–11:0x，全程只读 `nvidia-smi`／`docker exec`）

```text
宿主   4, [Insufficient Permissions], GPU-0e7f33ad-cc4a-7a1a-e9a4-7dd69f9032ab, [N/A]
容器   50983 / 51023（10:0x）→ 53524 / 53701（10:3x），一律 [Not Found]，同一枚 gpu_uuid，used_memory [N/A]
       readlink /proc/<pid>/exe -> /usr/lib/ollama/llama-server      容器内 ps -> llama-server
宿主进程表  Get-CimInstance Win32_Process -Filter "ProcessId=4" -> Name=System，ExecutablePath 空
显存         1 MiB（09:5x 空表那一刻）→ 5208~5640 MiB（模型在显存里那一刻）
```

三处**必须写进设计**的实测事实（前两处推翻队列 v2 那套姿势的写法）：

1. `used_memory` 本机恒为 `[N/A]`（WDDM）=> 归因不能拿显存做凭据，槽位只认 `gpu_uuid`；
   这条腿读空一律 UNMEASURED，不假装它存在。
2. 容器侧 `nvidia-smi` **自己也叫不出名字**（交回 `[Not Found]`）=>「同名」的真凭据是容器内
   `/proc/<pid>/exe`。队列 v2 那套只数行数（`n = len(lines) > 0`）就放行 —— 收进来时改成能点名。
3. 匿名行有两种拼法：宿主 `[Insufficient Permissions]`、容器 `[Not Found]`。名册只写前者就会把后者
   当成「可解析名」→ 误判 FOREIGN。已按实测两枚一起收（`test_a` 逐字钉这两行）。

## 2 逐判据交数

### ① 三分法 + 可失败归因链（真源：新 `scripts/r581_gpu_attribution.py`）

```text
L1 影子    宿主行的 process_name 读不出（匿名名，本机两种拼法：[Insufficient Permissions] 与容器侧
           [Not Found]）-> 这个 pid 必须能在宿主进程表里点到名，再按这个次序被认领：
             ① 名字在宿主代理名册（system／vmmem／vmmemcompute／com.docker.backend.exe；本机现取证过
                的只有 System）—— 名册内即认，因为 vmmem 一类宿主代理本来就跑在仓库外，要求它落在树里
                会把自家形状判成 FOREIGN；
             ② 名册外，但进程表给出的 ExecutablePath 落在自家三棵树里（宿主直装的那一族）。
           两样都不满足 -> FOREIGN（反解出仓库外的可执行文件／名册外的进程名）；进程表点不到名 -> UNMEASURED
           🔴 名册只认**树路径**不认文件名（CE-9：放宽到文件名就会把宿主直装的 ollama 当成自家）
L2 容器    docker ps 点得到且在跑的 ollama 容器（缺省 enterprise-brain-ollama-1，可用
           R581_OLLAMA_CONTAINER 或 --container 改口）+ 容器内 nvidia-smi rc=0
           docker ps 跑不成 -> UNMEASURED；问得到却没有在跑的 ollama 容器 -> FOREIGN（无人认领）
L3 同槽    每一枚影子行的 gpu_uuid 必须出现在容器侧计算进程的 gpu_uuid 集合里
           影子行 gpu_uuid 读空 -> UNMEASURED；容器侧不认领这个槽 -> FOREIGN；容器侧零计算行 -> FOREIGN
L4 同名    同槽那一格上容器侧必须能叫出至少一枚计算进程的名字（nvidia-smi 直接给名，或容器内
           /proc/<pid>/exe 解析出可执行文件）-> 一枚都叫不出 -> UNMEASURED
```

四态：`CLEAN`／`ATTRIBUTED`／`FOREIGN`／`UNMEASURED`；`PASSING=(CLEAN, ATTRIBUTED)`、
`BLOCKING=(FOREIGN, UNMEASURED)`；两元组出口 `attribute(state) -> (status, detail)` 供别的调用点改调。
在册件 `scripts/r530_run10_window_preflight.py` 只做词汇映射（CLEAN/ATTRIBUTED→PASS、FOREIGN/UNMEASURED→FAIL），
退出码契约 0/1/2 一字未动。放行长这样（10-03 真机现取，rc=0）：

```text
ATTRIBUTED｜匿名影子 1 枚已按四腿归给 enterprise-brain-ollama-1（Docker Desktop vGPU 的宿主代理影子）：
L1 影子＝pid=4 name=System＝名册内宿主代理（宿主进程表现取）
L2 容器＝enterprise-brain-ollama-1 在跑，容器内 nvidia-smi rc=0
L3 同槽＝影子槽 GPU-0e7f33ad-cc4a-7a1a-e9a4-7dd69f9032ab 容器侧在册（容器侧计算进程 1 枚）
L4 同名＝pid=53524 -> /usr/lib/ollama/llama-server
／🔴 本格只证「占卡的是自家容器」，不证时延干净，A(1)／A(4) 不许因此翻绿
```

### ② 「问不到」不许当「没有」

六枚问不到形状逐枚钉（`test_e_unaskable_legs_never_become_clean`）：nvidia-smi 跑不成／影子 pid 点不到名／
影子行没有 `gpu_uuid`／容器内 nvidia-smi 非零／容器侧一枚名字都叫不出／影子在位却整枚没查容器
—— 六枚全落 `UNMEASURED` 且 `blocking is True`。另有一枚不变量（在 `test_d` 的四枚摘法循环里）：
**影子还在时绝不许写 CLEAN**。

### ③ 默认行为不许放松（改前拦的，改后必须仍拦）

- 可解析名又不属自家树的计算行 → `FOREIGN`（`test_c`，用的就是 09-30 run10 那枚 anaconda3 下的
  `python.exe` 形状：`C:\Users\fengx\anaconda3\python.exe`）；
- 派工词指定的那一形 —— **进程内造一枚非容器所有的计算 pid**（把影子挪到 `GPU-00000000-…` 另一枚槽）
  → `FOREIGN`，读数点名「非容器所有的计算 pid」（`test_f`）；容器不在场、容器侧零计算行 → 同 `FOREIGN`；
- 端到端仍非零退出（`test_l`）；
- 自家名册**只认树不认文件名**：一枚 `C:\Program Files\ollama\ollama.exe` 仍是 FOREIGN（`test_c` 第三枚）。
  这条是施工时抓到的一处**潜在放松**：照抄队列 v2 的 `("ollama","enterprise-brain")` token，宿主原生
  ollama 就会被判成自家。已改成「这棵工作树／主树／跑分树」三枚绝对路径名册，容器内 `/proc` 解析出的
  名字不参与宿主所有权判定（CE-9：把 `ollama` 塞回名册 → `test_c` 当场红）。

### ④ 归因真源只写一处

同形判定（匿名名册、影子→容器→同槽→同名、四态映射）只存在于 `scripts/r581_gpu_attribution.py`。
在册件里 `read_gpu_apps()` 只剩一枚委托出口，`evaluate()` 里那九行同形判定已删净；
`test_j_registered_gate_keeps_no_second_gpu_judgement` 用源码钉收口：不许出现
`insufficient permissions`／`not found`／`UNREADABLE`／`SHADOW_HOST_OWNERS`／自拼的 `--query-compute-apps`，
且 `snap.gpu_apps` 只许出现一枚。

### ⑤ 在册那枚同名件 + `--json` 面

```text
tests/test_r530_window_preflight_pins_the_opening_conditions.py：本笔零改动
  · 归一化换行后盘面＝HEAD blob 同 sha 452b7cd60f69（11:0x 现读两枚相同）；git status --porcelain 对它交回空
    🔴 别拿 pins.py 那行「逐字节相同 False」当罪证：它比的是原始字节（盘面恒 CRLF vs blob 恒 LF，
    core.autocrlf=true 下必然 False）；真凭据＝归一化后的同 sha ＋ porcelain 交回空
  · 改前 collect-only = 12 枚 -> 改后 12 passed，逐枚同名同序（pins.py 逐枚点名 SAME），断言一字未放宽
--json 面键集：改前 {check, detail, status} -> 改后 {check, detail, status, verdict}（只增不减）
  改后这枚是真跑出来的：checks=7，每枚 item 恰为四键；逐枚 check 名改前＝改后同序：
  provenance · answer_cache · keep_awake · gpu_apps · foreign_python · eval_tree · env_flags
  改前那枚的出处说清楚（不当场假称跑过）：扫 HEAD blob 字面量（全文只有一处 json.dumps 出口）＋对一行
  git diff（旧行 "check": n, "status": s, "detail": d）；🔴 没在树外真跑旧件——拷到 %TEMP% 跑时它 ROOT
  就指向 %TEMP%，第一枚 provenance 子进程起不来，--json 一个字都不输出（rc=1、stdout 空）
  test_k 把这份契约钉住：七格一枚不少、顺序不变、每枚恰为 {check,status,detail,verdict}
```

### ⑥ `scripts/eval_window_shard_driver.py` 那几行：本笔**不改**，理由与转出项

现读：driver 里 `gpu`／`nvidia`／`preflight` 各 0 次命中 —— 它没有 GPU 判据。它的闸是
`check_read_path`（读路径）＋`FINGERPRINT_KEYS` 五项指纹（镜像 revision ∧ 容器 `INDEX_BACKEND` ∧
fixture sha256 ∧ transport spec ∧ `shard_size`）＋覆盖闸。三条理由：

1. **语义不同**：driver 的 REFUSE 是「这些片是在另一种条件下采的，不许混库」（复用判据），
   P-20 的 FAIL 是「此刻不能开窗」（时刻判据）。焊在一起，将来任一侧改口都会污染另一侧的钉。
2. **形状不对**：driver 是逐片循环，归因要问 `nvidia-smi` + 宿主进程表 + 两三次 `docker exec`；
   放进片级循环＝每片重问一次环境，而「开窗时干净」与「第 37 片时干净」本来不是同一件事，
   只会制造中途变红的假失败（正是要避免的那一形）。
3. **写集**：driver 被 `tests/test_r570_window_shard_driver.py`（35 枚）逐格钉着，本单不许顺手改它的判据落点。

⇒ 结论：driver 不该调，**也不存在「默默留两套」**——它本来没判 GPU。真正并存的第二套在仓外：

- 🔴 **R581-T1（总控·队列侧）**：队列那枚 `gpu_clean()`（仓外的 `queue_v2.py`，路径见 §5-6）可整枚删掉，换成
  ```python
  sys.path.insert(0, str(MAIN / "scripts")); import r581_gpu_attribution as g
  v = g.classify(g.collect()); ok, why = (not v.blocking, v.detail)
  ```
  仓外件本席未动（写域外，且它会改到在跑的队列）。**总控动手之前那件事仍有两套判定**，这条账由落地时销。
- **R581-T2（总控·裁）**：若将来要在开窗后复查 GPU，请落在「逐窗一次」（P-20 与窗内自复核各调一次
  `attribute()`），别落进 driver 的片级循环；要加就另立单补钉。
- **R581-T3（总控·环境）**：`env_flags`／`answer_cache` 两格在任何 `be-*` 工作树上必红，因为
  `deploy/.env.server` 是业主文件、未进 git，工作树里没有它。P-20 若要支持非主树运行，需要一枚
  `--root/--env-file` 旋钮 —— 不属本单判据，故未动，登记在此。

## 3 两态如实（判据 ⑤ 要的那句：本格到底靠什么判的 CLEAN）

```text
09:5x  首枚现取：宿主与容器两侧 --query-compute-apps 都交回空表，显存 1 MiB
       => 这一刻改前的格子也会 PASS（"GPU 计算进程 0 枚"），派工词 09:4x 那句就是这个形状；
          改后的码在这一刻报 CLEAN，读数明写「GPU 计算进程 0 枚…没有匿名影子需要归因」
09:57  改前在册件整件现取：rc=1、五格 FAIL，gpu_apps 原文——
       [P-20] FAIL gpu_apps 外来进程占着 GPU，A(1) 的 p95 时延读数不可采信：pid=4 exe=[Insufficient Permissions]
10:11  改后同一枚闸、同一台机、影子在场：
       [P-20] PASS gpu_apps ATTRIBUTED｜匿名影子 1 枚已按四腿归给 enterprise-brain-ollama-1…
10:16  --json 复现：gpu_apps status=PASS verdict=ATTRIBUTED（其余四格见 §5）
10:29  独立再取一次真源 CLI：ATTRIBUTED，rc=0（容器侧换成了 pid=53524，四腿仍全通）
10:42  影子消失（模型 unloaded）：真源 CLI = CLEAN，rc=0
10:44  在册件同机复取：gpu_apps = PASS / verdict=CLEAN；nvidia-smi 计算表只剩表头，显存 1 MiB
       本格现读 = CLEAN｜GPU 计算进程 0 枚（nvidia-smi rc=0 点名零枚），没有匿名影子需要归因
       => 这一眼的放行凭据是「rc=0 且真点名零枚」，不是「问不到」；问不到那一形在码里走 UNMEASURED -> FAIL
11:06  影子回潮（模型重新载进显存）：真源 CLI 又报 ATTRIBUTED，rc=0，四腿逐枚点名；容器侧 pid 换成
       166／376（容器命名空间内的号），L4 两枚都 -> /usr/lib/ollama/llama-server
       => 同一次交回里 CLEAN 与 ATTRIBUTED 各现取到两枚（09:5x／10:42／10:44 = CLEAN，10:11／10:29／11:06 = ATTRIBUTED）
          格子跟着真实占卡表来去：既不因 pid=4 恒红，也不因「问不到」恒绿
```

⇒ **本格两态都现取过，而且当场翻回来过**：影子在场（10:11／10:29／11:06）报 `ATTRIBUTED`，凭四腿现取凭据（容器在跑 ∧
同槽在册 ∧ `/proc/<pid>/exe` 叫得出 `llama-server`），四腿逐枚点名就在读数里；影子不在（10:42／10:44）报 `CLEAN`，
凭的是 `nvidia-smi` **rc=0 且真点名零枚**。**两态都不是「看着不像负载」，两态也都不证时延**，A①／A④ 一格不因本笔翻绿。

## 4 反证（九枚摘法：victim 全名 + 摘什么 → 哪枚红 + 摘前摘后 sha 相同）

```text
victim A = scripts/r581_gpu_attribution.py         摘前/还原后 sha256[:12] = 22c42f625f50 / 22c42f625f50 相同
victim B = scripts/r530_run10_window_preflight.py  摘前/还原后 sha256[:12] = 769a1392d5b4 / 769a1392d5b4 相同
（还原方式＝逐字节写回原二进制；九枚的「摘前 sha ＝ 还原后 sha」全部 True）

CE-1  摘 L4：容器侧一枚名字都叫不出也放行        A  -> test_d, test_e 红           2 failed / 11 passed
CE-2  把「nvidia-smi 问不到」当没有负载          A  -> test_e 红                   1 failed / 12 passed
CE-3  可解析的外来计算进程不再拦窗                A  -> test_c, test_i 红           2 failed / 11 passed
CE-4  在册件里偷塞回第二份同形判定                B  -> test_j 红                   1 failed / 24 passed
CE-5  --json 面摘掉 detail 与 verdict 两枚键      B  -> test_k 红                   1 failed / 12 passed
CE-6  在册件断掉真源 import（改回自己判）          B  -> 14 枚红（在册件 10 枚 + 本单 test_i/j/k/l）14 failed / 11 passed
CE-7  摘 L1：名册外进程名/仓库外路径也算影子      A  -> test_g, test_m 红           2 failed / 11 passed
CE-8  把 UNMEASURED 摘出拦窗集合（问不到＝放行）  A  -> test_d, test_e, test_h 红   3 failed / 10 passed
CE-9  自家名册放宽到文件名（多收一枚 ollama）      A  -> test_c 红                   1 failed / 12 passed
```

🔴 **本笔实测踩到一枚反证件自己的坑（照实记）**：10:4x 一枚早先的反证跑批中途异常退出，把
`scripts/r581_gpu_attribution.py` **留在了摘除态**（`if foreign:` 被换成 `if False:`，22505 B／sha `0aa9a4bf376b`），
而它自己打印的「摘前＝还原后 sha 相同」是**针对那次异常前读到的原件**，所以盘面已经脏了而读数看不出来。
后果不轻：那一态正是「可解析的外来计算进程不再拦窗」，也就是判据 3 被静默关掉。
已用跑批前的备份逐字节还原（`22c42f625f50`，`if foreign:` 1 处、`if False:` 0 处），还原后复跑 66 passed，
再把九枚反证**在同一棵树上重跑一遍**：九枚的「摘前 sha＝还原后 sha」全 True，且九枚的失败枚数与红枚名字与本表逐枚一致。
⇒ 教训：**反证跑批结束后必须现读盘面 sha 与原件对账**，别只信它自己打印的还原标志；这条已加进下面的复跑清单。

CE-4 那一枚值得单独点名：偷塞第二份判定时，**在册那 12 枚全绿**（24 passed 里含着 12 枚），
只有本单新钉的 `test_j` 咬得住 —— 这就是判据 4 需要一枚源码钉的原因。
判据 3 的正证（不是摘法）另记 `test_f`：进程内把影子挪到容器不认领的槽 ⇒ `FOREIGN`＋点名
「非容器所有的计算 pid」；未起真负载、未打模型。

## 5 🔴 与派工词不符／需订正的现取事实（逐枚点名）

1. **「8 格全 PASS」对不上：在册件只产 7 格。** 09:57（改前）与 10:16（改后）两枚 `--json` 都交回
   provenance／answer_cache／keep_awake／gpu_apps／foreign_python／eval_tree／env_flags 七枚；
   文本面是 7 行 + 1 行 verdict。最可能是那句把 verdict 行算成了一格（本席无法复原 09:4x 那一眼）。
2. **派工词开头那句「已是 rc=0／8 格全 PASS」在本树复现不出来**：改前整件 rc=1／五格 FAIL，改后 rc=1／四格 FAIL
   （gpu_apps 从 FAIL 转 PASS）。那四格与 GPU 那一格无关，出处逐枚现取：
   - `provenance`：镜像 `revision=63c36dd`、`built_at=unknown`，落后本树 `dfc057b` 两枚
     （`git rev-list --count 63c36dd..HEAD` = 2），逐文件 byte check 交回 FAIL；§153 那句「镜像 fd90f30
     落后主树 6 笔」已过期（这中间镜像被重打过）。修它＝总控那次 build migrate，本席未动。
   - `answer_cache` rc=2：`[P-18] REDIS_PASSWORD 取不到：…\be-r581\deploy\.env.server 不存在（口令只认这一枚件）`。
   - `env_flags`：同一原因 —— 这棵工作树里没有业主的 `deploy/.env.server`（未跟踪），两枚开关读成 `<未设>`。
     🔴 业主文件一个字节未碰；这两格要真读必须在主树。
   - `foreign_python`：09:57 那一眼有 eval／collect／r575 诸在途子工在跑 → FAIL；10:16 那一眼已 PASS。
   11:1x 复取**又 FAIL**，点名的是主树 `.venv` 解释器在跑本席自己的 pytest／反证子进程。
   🔴 这不是本笔造成的，而是一族结构性假红：`in_repo()` 比的是**本树** ROOT（`be-r581`），而派工词规定的
   解释器在主树（`企业智脑\.venv`）⇒ 在任何 `be-*` 工作树上用主树解释器跑测试，这格必被自己污染。
   与 R581-T3 同一族（工作树里没有业主 env ⇒ `answer_cache`／`env_flags` 必红）；开窗真判要在主树跑。
3. **「在册那 11 枚」实为 12 枚**（第 12 枚 `test_r530_create_time_collects_with_one_clock_not_the_dotnet_epoch`
   系 R549 加）。本单按「同名集同数」执行：改前 12、改后 12、逐枚同名同序。
4. **派工词那句「这台机上 pid=4 永远在 ⇒ 那一格永远红」要收窄**：pid=4 永远在，但那枚**匿名计算行只在
   容器真占着 GPU 时出现** —— 09:5x 两侧交回空表（显存 1 MiB），10:0x 起 `4, [Insufficient Permissions]`
   在册；10:42、10:44 两枚复取时它又消失（占卡表只剩表头，显存 1 MiB）。⇒ 旧判据是「模型一载进显存就
   永远红」，不是「永远红」——影子随模型进出显存而来去，本格在 CLEAN／ATTRIBUTED 之间切换。两态原件都在本纸 §3。
5. **收队列 v2 那套时纠了两处偏**（不是照抄）：容器侧从「数行数」改成「叫得出名字」；槽位从「不看」
   改成 `gpu_uuid` 硬比。原委见 §1 第 2、3 条。
6. 队列 v2 在 `%TEMP%/eb-rescue/R570/queue_v2.py`（`%TEMP%` 展开为
   `C:\Users\fengx\AppData\Local\Temp\eb-rescue\R570\queue_v2.py`）——仓外，本席只读过、未改过。

## 6 怎么复跑（测试全程离线；真机取证只读）

```text
PY = C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe
# 本单一手四件（不碰 docker／nvidia-smi／模型；conftest 两枚闸门现读 0 次越界）
$PY -X utf8 -m pytest tests/test_r581_gpu_shadow_attribution.py `
    tests/test_r530_window_preflight_pins_the_opening_conditions.py `
    tests/test_r566_keep_awake_horizon_is_measured_not_parsed.py `
    tests/test_r570_window_shard_driver.py `
    -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r581_all -q     # -> 66 passed
# 现取（只读）
$PY -X utf8 scripts/r581_gpu_attribution.py --json                     # -> rc=0；读数两态：影子在=ATTRIBUTED（10:29 实测）／占卡表真空=CLEAN（10:44 实测）
$PY -X utf8 scripts/r530_run10_window_preflight.py --need-minutes 90    # -> gpu_apps PASS（ATTRIBUTED 或 CLEAN，见§3），整件 rc=1（§5-2）
# 反证跑批之后【必查盘面】（本笔真踩到的坑，见 §4）：跑完再量一次 sha，必须回到
#   22c42f625f50（真源）／769a1392d5b4（在册件）／ccbe383d2b2e（新钉）——不还原等于把判据 3 关了交回去
# 量具三枚（都在仓外 %TEMP%，不落仓）：r581tools\shape.py（CRLF/BOM/裸CR）、pins.py（同名件对账）、ce3.py（九枚反证）
```

形状现读（本笔四枚件）：`bareLF=0／loneCR=0／CRLF 单形／BOM=False`。
施工过程里真踩到派工词预告的那枚坑：第一次批量补丁用模板字符串插值，把 26 枚裸 LF 混进在册件
（`git diff` 当场报「LF will be replaced by CRLF」）=> 已把整枚件归一化回 CRLF 单形并复量；此后落盘
只走「占位符→真字符→统一换行」这一条路。

## 7 没跑的格子（照实写「未跑」）

- `python scripts/run_gate.py` 全量门：**未跑**（派工词禁止跑门／禁 `-n`）。本单只跑了 §6 那四枚件的
  单跑（66 passed），并树后的全量归总控按同一 HEAD 复跑并与看板最新绿票对账。
- 真起一枚非容器 CUDA 负载去撞 FOREIGN：**未跑**（不许打模型／不许改环境）=> 判据 3 那一格是**进程内造影子**
  证的；真机外来负载那一形状沿 09-30 run10 的 `pid=13640 anaconda3 python train.py --device cuda` 历史现读。
- `SHADOW_HOST_OWNERS` 名册里 `vmmem`／`vmmemcompute`／`com.docker.backend.exe` 三枚：**本机未证到**
  （现取只证过 `System`）。名册外一律 FOREIGN —— 方向是宁可红，不会假绿；真撞上再补凭据。
- 影子的时间维（多轮采样、容器 pid 生命周期竞态）：**未跑**。已知的形状是容器 pid 在两次调用之间换掉
  （50983/51023 → 53524/53701 → 166/376 三枚现取，11:06 那枚已是容器命名空间内的号），此时同槽仍有可点名者 ⇒ 仍 ATTRIBUTED；若一枚都不剩 → UNMEASURED。
  没做过 20×120 s 级采样，别拿这段当凭据。
- `provenance`／`answer_cache`／`env_flags` 三格在主树里的真读数：**未验**（本席只在 be-r581 现取，
  本树缺业主 env 文件，这三格在 `be-*` 树上必红）。
- 队列 v2 那套的退役：**未做**（仓外无写权，见 R581-T1）。
- A①／A④、run13/run14 的任何时延读数：**未读未改**，本笔一格不翻绿。
- 主树 `企业智脑`：**一字未动**。

## 8 写集

本笔写集只有四枚：新 `scripts/r581_gpu_attribution.py`（真源）、新
`tests/test_r581_gpu_shadow_attribution.py`（13 枚）、新本纸，加在册
`scripts/r530_run10_window_preflight.py`（+37／−23）。在册同名件与 driver 一字未动；
未 commit、未 push、未动容器、未打模型。盘面现读（HEAD／numstat／未跟踪清单／逐枚 sha256 前 12）见交回消息。
