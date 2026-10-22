-- R46 · 活动信号计数：检索排序要读的那份先验存在这里。
--
-- 跟进单 §21 给 R46 立的三条判据里，隐私那条原文是「只存计数不存内容」，禁止项是
-- 「不得把用户问题原文写进新表」。这张表的列清单就是那条判据的实体：一列文档标识、
-- 两列计数、两列时间，没有 query / question / answer / excerpt / note，也没有任何一列
-- 装得下一段自由文本。判据因此钉在「存不下」上，而不是钉在「每次写入都记得清洗」上——
-- 后者会在下一个调用点忘掉的。
--
-- 粒度是 filename，不是 (filename, user_id)：先验回答的是「这篇文档在这套部署里被采信
-- 过还是被驳回过」，那是文档的属性，不是某个人的历史。按人存就要多带一列身份，而排序
-- 恰恰不读它——多出来的那一列只会变成新的隐私面。「谁在什么时候打的点」由
-- app/common/audit.py 的审计流水回答（它本来就记 principal / action / resource），本表
-- 不复制一份平行账。
--
-- 键选 filename 而不是 document_version_id：检索命中字典（app/rag/retriever.py 的
-- _hit_dicts）拿得出来的只有 source（= filename）与 chunk_index，向量库那一侧没有版本
-- 列。用版本键就得让排序先去解析当前版本，那条链路一断先验就静默失效，比不准更糟。
-- 代价是新版本继承旧版本的先验，这是有意的：内容会重入库，而「这类问题该引用哪篇」的
-- 信任本来就跨版本；业主要清账就 DELETE 这一行，不需要再出一枚 migration。
--
-- 长度为 0 的行不留：表里出现一行就意味着真有人打过点。这条 CHECK 顺带把「先建一张
-- 空表占位、等以后再接」的形态挡在库外——R46 判据⑥不许那种假完成。

CREATE TABLE IF NOT EXISTS document_activity_signals (
    filename TEXT PRIMARY KEY,

    -- 采纳与驳回分开记，不做成一列净值：净值为 0 有两种完全不同的来历（没人打过点，
    -- 和打点的人一人一半）。这笔收益要说准：排序当前给两者的分值**相同**（净值 0 ⇒ 先验 0，
    -- 见 app/rag/retriever.py 的 activity_prior_value），分开记买到的是"可分辨"而不是
    -- "不同权重"——读回的计数与命中上的 activity_prior 注记仍能把 0/0 与 5/5 说成两件
    -- 事，而一列净值从一开始就把这个区别抹掉，将来谁要给争议样本另设权重也就没了原料。
    accepted_count BIGINT NOT NULL DEFAULT 0,
    rejected_count BIGINT NOT NULL DEFAULT 0,

    first_signal_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_signal_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT document_activity_signals_accepted_check
        CHECK (accepted_count >= 0),
    CONSTRAINT document_activity_signals_rejected_check
        CHECK (rejected_count >= 0),
    -- 见上面「长度为 0 的行不留」。
    CONSTRAINT document_activity_signals_not_empty_check
        CHECK (accepted_count + rejected_count > 0),
    -- 隐私边界的第二道：key 列也设上界。文档名来自入库时的文件名，远小于这个数；
    -- 真有人把一段问题原文塞进 filename 位置，这里会拦，而不是等到排序去截断。
    CONSTRAINT document_activity_signals_filename_length_check
        CHECK (length(btrim(filename)) > 0 AND length(filename) <= 512)
);

-- 不另建索引：读取方每次取整张表（至多每篇文档一行，与库容量同阶，且远小于 documents），
-- 用来算先验的开销本来就是一次全表扫，PK 已覆盖按文档的点查。
