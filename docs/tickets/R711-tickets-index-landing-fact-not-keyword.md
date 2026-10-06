# R711 · 索引只从提交标题里的「并树」字面认落地号：标题写「订正」的真并树提交被判成 QUEUED

**号**：R711　**性质**：总控亲签（10-06 实测自撞：R707 真并树笔 `54e1f53` 的标题写「R707 订正 r688 口径」，`docs/tickets/index.tsv` 判 QUEUED，直到我追加凭据补记笔 `4147b6d` 才转 LANDED）　**基点**＝派工那一刻主树 HEAD 现取

## 病形现取

- `scripts/tickets_index.py::landing_numbers` 的规则：先匹配提交标题头部的号，再在标题剩余部分里找**「并树」字面**才认落地。⇒ 落地与否被判成了**提交词的措辞问题**，而不是 git 事实问题；这正好违背本目录的立目录理由（状态只由 `git log` 现查事实派生）。
- 现取凭据：`git show -s --format=%s 54e1f53` 不含「并树」；同批 `78a6568`（含「R695 并树」）判 LANDED。
- 加重一格：AGENTS ⑨ 的自指后果（一枚工单转 LANDED 只有在落树**之后**重生成才写得进），今天实测要跑**两遍** `--write` 才收得住（`4147b6d` 之后生成的索引仍写 QUEUED，`2baba78` 才转蓝）。

## 判据（每条可失败）

1. 落地判定改按**事实**：标题里出现本目录在册号 ＋ 该提交实际改了该工单写域内的文件（`git show --name-only` 现取），两者同时成立即 LANDED；「并树」字面不再作数。🔴 反证牙：造一枚只写标题不碰写域的提交 ⇒ 必须仍判 QUEUED；造一枚标题不含「并树」但碰了写域的提交 ⇒ 必须判 LANDED。
2. 自指那一格做成**可失败读数**：`python scripts/tickets_index.py --check` 在「刚并一枚、索引未重生成」这种盘面上必须点名是哪一号（今天的形状是 rc=2 一句总数），并把「重生成需要几遍」写成明面判据（理想＝一遍，做不到就在 `--check` 的出口里区分「待重生成」与「账脏」）。
3. 既有派生纪律不许放宽：`--verify` 的判据原文逐字符回读、行号棘轮、形状校验三格都要仍过；`python -m pytest tests/test_r680_* tests/test_r132_contract_followup_sync.py -q` 读数不许变差。
4. 交付：同名件两态（dirty／`git worktree add --detach` 干净检出）＋`scripts/tickets_index.py --verify` rc=0 前后对照＋凭据纸 `docs/testing/r711-<开工日>.md`。

## 写域（只许这些）

`scripts/tickets_index.py`／新增 `tests/test_r711_*.py`／`docs/tickets/R711-*.md`／`docs/tickets/index.tsv`／`docs/testing/r711-<开工日>.md`

## 禁区

产品码 `app/**`／`frontend/**`／`docs/handoff/**` 的既有前置行／评测集与判分器／夜窗量具 `scripts/r631_*`·`scripts/r636_*`·`scripts/eval_*`／容器·镜像·模型。🔴 本单**不许**新增读 markdown 的用例（红线：读 .md 的用例占比只降不升）。
