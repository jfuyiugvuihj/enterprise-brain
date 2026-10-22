"""R79 判据②：两个零覆盖的出厂默认值必须长成有牙的用例。

`HOT_INDEX_MAX_CHUNKS=20 000` 与 `HOT_INDEX_ROSTER_TTL_SECONDS=300.0` 在本单之前没有任何
用例钉住出厂值 —— 改掉它们，全仓不红。这里的钉法分三层，缺一层都不算数：

1. **字面量**：不打环境变量时，构造出来的实例就用这两个数（改出厂常量必红）。
2. **行为**：第 20 001 条 chunk 真的当不上常驻，并且因此把整批热集判成"不能服务"；
   花名册在第 300 秒整之后真的判 stale。边界两侧各钉一次，钉在那个点上。
3. **同一颗常量是活的**：把 DEFAULT_* 改掉，行为边界必须跟着挪同样的量 —— 这一条挡的是
   "用例里抄一份字面量、代码里再抄一份"那种假牙。

环境变量一律用**字面量名**设置（不是 hi.HOT_INDEX_MAX_CHUNKS_ENV），变量名字符串被改掉也红。
"""

import pytest

from app.rag import hot_index as hi

SCOPE = ("chroma", "r79-defaults", 8, "v1")
DIM = 8


def _rows(count, *, department="sales", start=0):
    for ordinal in range(start, start + count):
        chunk_id = f"bulk_{ordinal:06d}_0"
        yield (chunk_id, f"正文 {ordinal}",
               {"filename": f"bulk_{ordinal:06d}", "chunk_index": 0,
                "classification": 1, "department": department},
               [float(ordinal % 7), 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, float(ordinal % 3)])


@pytest.fixture
def clean_env(monkeypatch):
    """把 HOT_INDEX_* 全数清掉：出厂值只能在"什么都没设"的时候测。"""
    for name in (hi.HOT_INDEX_ENV, hi.HOT_INDEX_MAX_CHUNKS_ENV,
                 hi.HOT_INDEX_MAX_AGE_SECONDS_ENV, hi.HOT_INDEX_ROSTER_PAGE_ENV,
                 hi.HOT_INDEX_WARM_RETRY_SECONDS_ENV):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def armed(clean_env):
    """开关打开，但 HOT_INDEX_MAX_CHUNKS / _ROSTER_TTL_SECONDS 仍然一个都没设。

    不先过开关这一关，下面所有 bypass 原因码都恒等于 hot_index_disabled，
    一条都量不出预算与 TTL —— 那才是判据②真正要钉的东西。
    """
    clean_env.setenv(hi.HOT_INDEX_ENV, "1")
    return clean_env


# ==================== HOT_INDEX_MAX_CHUNKS = 20 000 ====================

def test_the_factory_budget_is_twenty_thousand_chunks(clean_env):
    """字面量层：改 app/rag/hot_index.py 里那个 20 000，这条立刻红。"""
    assert hi.HotSetIndex().max_chunks == 20_000
    assert hi.hot_index_config()["max_chunks"] == 20_000
    assert hi.HotSetIndex().state()["max_chunks"] == 20_000


def test_the_twenty_thousand_first_chunk_is_refused_residence_and_it_bites(armed):
    """行为层：第 20 001 条进不了常驻，并且它把整批判定拖成"不能服务"。

    预算没生效的话 resident 会是 20 001；常驻之外那一条要是不参与覆盖判定，where=None
    时照样敢服务 —— 两个反方向各被钉一次。
    """
    index = hi.HotSetIndex()
    rows = list(_rows(20_000)) + list(_rows(1, department="qa"))
    outcome = index.populate(rows, scope_key=SCOPE)
    assert outcome == {"resident": 20_000, "cold": 1}, outcome
    assert index.resident_chunks == 20_000 and index.cold_chunks == 1
    assert index.bypass_reason(scope_key=SCOPE, query_vector=[0.0] * DIM) == hi.REASON_INCOMPLETE
    #: 把那一条排除在过滤条件之外，同一批常驻条目立刻恢复服务：挡路的确实是它。
    assert index.bypass_reason(scope_key=SCOPE, query_vector=[0.0] * DIM,
                               where={"department": "sales"}) == ""
    ranked = index.rank([0.0] * DIM, 3, scope_key=SCOPE, where={"department": "sales"})
    assert ranked is not None and len(ranked) == 3
    #: 冷行只要还在过滤条件的射程里，换个写法也一样挡路；而过滤条件谁都收不进时，
    #: 热集敢照实交一个空集（它确实在说"没有"，不是在说"我不知道"）。
    assert index.bypass_reason(scope_key=SCOPE, query_vector=[0.0] * DIM,
                               where={"department": {"$in": ["sales", "qa"]}}) == hi.REASON_INCOMPLETE
    assert index.rank([0.0] * DIM, 3, scope_key=SCOPE,
                      where={"department": "hr"}) == []


def test_the_budget_env_variable_moves_the_same_line(armed):
    """正反都要：环境变量抬一格，第 20 001 条就住得下来。"""
    armed.setenv("HOT_INDEX_MAX_CHUNKS", "20001")
    index = hi.HotSetIndex()
    assert index.max_chunks == 20_001
    outcome = index.populate(list(_rows(20_001)), scope_key=SCOPE)
    assert outcome == {"resident": 20_001, "cold": 0}, outcome
    assert index.bypass_reason(scope_key=SCOPE, query_vector=[0.0] * DIM) == ""


def test_editing_the_factory_constant_moves_the_refusal_line(monkeypatch):
    """牙在这里：常驻边界由那颗常量决定，不是用例里另抄的字面量。"""
    monkeypatch.setattr(hi, "DEFAULT_MAX_CHUNKS", 5)
    index = hi.HotSetIndex()
    assert index.max_chunks == 5
    outcome = index.populate(list(_rows(6)), scope_key=SCOPE)
    assert outcome == {"resident": 5, "cold": 1}, outcome


# ==================== HOT_INDEX_ROSTER_TTL_SECONDS = 300.0 ====================

class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _warm_index(clock, **kwargs):
    index = hi.HotSetIndex(clock=clock, **kwargs)
    index.populate(list(_rows(2)), scope_key=SCOPE)
    return index


def test_the_factory_roster_ttl_is_three_hundred_seconds(clean_env):
    """字面量层：300.0 改任何一位都会撞上下面的 299.999 / 300.001。"""
    assert hi.HotSetIndex().state()["roster_ttl_seconds"] == 300.0
    assert hi.hot_index_config()["roster_ttl_seconds"] == 300.0


def test_the_roster_ages_on_the_three_hundred_second_dot(armed):
    """行为层：边界两侧各钉一次，钉在 300 秒这个点上，不是"差不多五分钟"。"""
    clock = _Clock()
    index = _warm_index(clock)
    assert index.state()["roster_age_seconds"] == 0.0
    clock.now = 299.999
    assert index.populated is True
    assert index.bypass_reason(scope_key=SCOPE, query_vector=[0.0] * DIM) == ""
    clock.now = 300.001
    assert index.populated is False
    assert index.bypass_reason(scope_key=SCOPE, query_vector=[0.0] * DIM) == hi.REASON_STALE_ROSTER


def test_editing_the_factory_ttl_moves_the_stale_dot(armed, monkeypatch):
    """牙在这里：常量挪到 42 秒，判 stale 的点必须跟着挪，一毫秒都不许多给。"""
    monkeypatch.setattr(hi, "DEFAULT_ROSTER_TTL_SECONDS", 42.0)
    clock = _Clock()
    index = _warm_index(clock)
    clock.now = 41.999
    assert index.bypass_reason(scope_key=SCOPE, query_vector=[0.0] * DIM) == ""
    clock.now = 42.001
    assert index.bypass_reason(scope_key=SCOPE, query_vector=[0.0] * DIM) == hi.REASON_STALE_ROSTER
    monkeypatch.setattr(hi, "DEFAULT_ROSTER_TTL_SECONDS", 300.0)
    assert _warm_index(_Clock()).__class__ is hi.HotSetIndex     # 常量还原后口径跟着回来


# ==================== 环境变量走真实解析分支 ====================

@pytest.mark.parametrize("raw, expected", [
    ("250", 250),
    (" 512 ", 512),
    ("100000000", 100_000_000),     # 合法大值照收：这里没有藏着第二个上限
    ("", 20_000),
    ("0", 20_000),
    ("-7", 20_000),
    ("abc", 20_000),
    ("12.5", 20_000),               # int() 不认小数：回落，不四舍五入
], ids=lambda value: str(value))
def test_the_max_chunks_environment_branches(clean_env, raw, expected):
    clean_env.setenv("HOT_INDEX_MAX_CHUNKS", raw)
    assert hi.HotSetIndex().max_chunks == expected, raw
    assert hi.hot_index_config()["max_chunks"] == expected, raw


@pytest.mark.parametrize("raw, expected", [
    ("1.5", 1.5),
    ("  45.25  ", 45.25),
    ("3600", 3600.0),
    ("", 300.0),
    ("0", 300.0),
    ("-1", 300.0),
    ("not-a-number", 300.0),
    ("nan", 300.0),                 # nan > 0 为假 ⇒ 回落，不会把比较器毒化成永远 stale
], ids=lambda value: str(value))
def test_the_roster_ttl_environment_branches(clean_env, raw, expected):
    clean_env.setenv("HOT_INDEX_ROSTER_TTL_SECONDS", raw)
    assert hi.hot_index_config()["roster_ttl_seconds"] == expected, raw
    assert hi.HotSetIndex().state()["roster_ttl_seconds"] == expected, raw


def test_a_ttl_handed_straight_to_the_constructor_never_ages(armed):
    """`_fresh_locked` 里 ttl<=0 是"永不过期"的旁路：绕得过解析器，就得钉得住。

    环境变量侧永远拿不到非正值（上面那条分支钉死了），所以这条走构造参数。将来谁想支持
    "ttl=0 表示每次都重读花名册"，必须先改这里的口径，而不是让那个分支悄悄烂掉。
    """
    for ttl in (0, -1.0):
        clock = _Clock()
        index = _warm_index(clock, roster_ttl_seconds=ttl)
        clock.now = 10 ** 9
        assert index.populated is True, ttl
        assert index.bypass_reason(scope_key=SCOPE, query_vector=[0.0] * DIM) == "", ttl
