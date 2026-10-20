-- R46 差格 a · 点击与浏览：出处有没有被人真的看过，记在这里。
--
-- 跟进单 §21 给 R46 立的三条判据里，这一路吃的是同两条：①「有信号后排序变化可测」与
-- ③「只存计数不存内容」，禁止项还是那句「不得把用户问题原文写进新表」。区别在于
-- 0011 记的是**结论**（这篇被采信过还是被驳回过），本表记的是**动作**（哪一个人在哪一道题
-- 里，把第几名的那一条出处点开看过、还是展开看过）。动作是事件流水，不是净值，所以这里
-- 一行一枚事件，不做成一列计数：做成计数就丢掉了「谁在哪一轮点的」，而下一段要说的
-- 去重恰恰需要它。
--
-- 🔴 载荷里没有的位置，比有的位置更重要。本表七列：身份、题号、文档名、名次、事件类型、
-- 时刻、代理键。没有 query / question / prompt / answer / excerpt / note / snippet，
-- 也没有任何一列装得下一段自由文本——判据钉在「存不下」上，不是钉在「每次写入都记得清洗」
-- 上（0011 已经说过一次理由：靠自觉的那一类会在下一个调用点忘掉的）。三枚文本列各自还带
-- 形状 CHECK：thread_id 只认 id 字符集（不含空格、不含换行、不含中日韩，问题原文**结构上
-- 塞不进这一列**），username 由服务端从鉴权主体取值、请求体压根没有这一格，filename 沿
-- 0011 的 512 上界再加一枚「不许带控制字符」。
--
-- 为什么这一路**要**存身份，而 0011 刻意不存：0011 那张表回答的是「这篇在这套部署里被
-- 采信过没有」，排序读它，而排序不读「谁」，多一列身份只会多一个隐私面，所以它不存。
-- 本表不一样，这里有两条真读它的理由，缺一条这半张单就不成立：
--   ① 判据③要的「跨用户读别人的点击账必须拒」——没有身份列，这句话连说都说不出来；
--   ② 下面那枚 UNIQUE 去重——不按人分组，同一个人连点二十次就能把一篇顶进窗口首位，
--      那正是 0011 记账里被点名、留给强度校准单的旧缺陷。排序仍然一个字都不读 username：
--      app/rag/retriever.py 里那条聚合 SELECT 的列清单是 filename 与两枚 COUNT，
--      身份进不了排序，这一点由同名用例钉着。
--
-- UNIQUE (username, thread_id, filename, event_type) 是有意的第四道闸：同一个人、同一道题、
-- 同一条出处、同一种动作，只算一次事实。它**不是**按人限额（限额是「一天能点几枚」，
-- 那格欠业主裁定，本表不治），它是「一次动作＝一枚事件」这条语义的实体。写侧配
-- ON CONFLICT DO NOTHING，重复打点在库里落不下第二行，也就刷不出分数。
--
-- 保留期不写死在这里：这张表会长，而「留多久」是隐私与调参之间的取舍，属业主裁定
-- （与上面那枚限额同一格）。本表只保证留下来的每一行都不含内容。

CREATE TABLE IF NOT EXISTS document_engagement_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- 谁：服务端从鉴权主体取，请求体没有这一格（见上）。长度上界比文件名那一列更紧。
    username TEXT NOT NULL,
    -- 哪一道题：会话内的轮次标识（前端 turnKey 那一族：m<mid> 或 <session>#<index>）。
    -- 这枚字符集是「存不下原文」的实体：没有空格、没有换行、没有中日韩，只认 id 用得上的字。
    thread_id TEXT NOT NULL,
    -- 哪一枚出处：与 0011 同一个键，排序侧靠它把两路信号并到同一篇文档上。
    filename TEXT NOT NULL,
    -- 第几名次：打点那一刻它在这条腿里的位次，1 起。SMALLINT 加上下界，不是给分数用的，
    -- 是给「点的是榜首还是第五名」这件事留一份可查的形状；先验当前不读它（见回执的未验格子）。
    result_rank SMALLINT NOT NULL,
    -- 事件类型：封闭枚举，click＝点开那一条出处，view＝展开那一条的详情看过。
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 1) 名次非负且有界：与 0011「计数非负」同族的一条，只是这里计数换成了位次。
    CONSTRAINT document_engagement_events_rank_check
        CHECK (result_rank >= 1 AND result_rank <= 100),
    -- 2) 事件类型只认两值。想加第三种就得再排一枚 migration 改这枚 CHECK，
    --    而不是往这一列里塞一段自由文本——形状 CHECK 把这扇门从库里关上。
    CONSTRAINT document_engagement_events_event_type_check
        CHECK (event_type IN ('click', 'view')),
    -- 3) 三枚文本列各带硬上界，且都不许带首尾空白与控制字符（换行＝原文最常见的形状）。
    --    与 0011 那条 length(btrim(filename)) > 0 AND length(filename) <= 512 同值同形。
    CONSTRAINT document_engagement_events_username_check
        CHECK (username = btrim(username) AND length(username) BETWEEN 1 AND 64
               AND username !~ '[[:cntrl:]]'),
    CONSTRAINT document_engagement_events_thread_id_check
        CHECK (thread_id ~ '^[A-Za-z0-9_.:#-]{1,128}$'),
    CONSTRAINT document_engagement_events_filename_check
        CHECK (filename = btrim(filename) AND length(filename) BETWEEN 1 AND 512
               AND filename !~ '[[:cntrl:]]'),
    -- 4) 「一次动作＝一枚事件」：同一人对同一道题的同一条出处，同一枚动作只算一次。
    CONSTRAINT document_engagement_events_once_per_actor_turn_source
        UNIQUE (username, thread_id, filename, event_type)
);

-- 两条读腿各配一枚索引，与 0011「每次取整张表」不同：这张表按事件增长，不是按文档。
-- filename 那一枚给排序侧的聚合 GROUP BY；(username, occurred_at DESC) 那一枚给
-- 「我自己的点击账」这条读腿——它永远按人取最近若干条，不建它就会在流水上全表扫。
CREATE INDEX IF NOT EXISTS document_engagement_events_filename_idx
    ON document_engagement_events (filename);

CREATE INDEX IF NOT EXISTS document_engagement_events_username_idx
    ON document_engagement_events (username, occurred_at DESC);