"""R462 · 展平 tuple 键那一层的本体钉（跟进单 §133 五判据「修成字符串键」的下半条）。

病历原文（09-28 云窗真机 · report-11）：执行失败: keys must be str, int, float, bool or None, not tuple

本件只钉 tools._flatten_query_tuple_keys / _flatten_query_key 两枚函数：
① 两枚不同的原键撞成同一枚字符串时当场抛，不合并、不覆盖、不咽；
② 非 tuple 键（str/int/float/bool/None）与所有**值**原样交回，键型一个都不改；
③ 深层（dict 套 list 套 dict）的 tuple 键同样够得着，只有一层那种是假修。

端到端那一格（真 safe_query → 真 json.dumps → 模型读到的文本）在
tests/test_r462_query_data_tuple_keys.py，本件不重复起数据腿。
"""
import pytest

from app.agents import tools


def test_two_keys_flattening_to_one_string_are_refused_not_merged():
    """判据①：展平必须是一对一的，撞键就抛。

    成分里带着连接符 " | " 时，两枚不同的元组会拼出同一枚字符串：
    ("华北 | 东", "Q1") 与 ("华北", "东 | Q1") 都展成 "华北 | 东 | Q1"。静默合并就是
    拿一行数字冒充两行。摘掉 _flatten_query_tuple_keys 里那格 origin 守卫，这一发红相
    消失、交回的 dict 只剩一枚键——那是把假数据钉成"通过"。
    """
    raw = {("华北 | 东", "Q1"): 10.0, ("华北", "东 | Q1"): 20.0}

    with pytest.raises(ValueError) as caught:
        tools._flatten_query_tuple_keys(raw)

    text = str(caught.value)
    assert "拒绝合并" in text, text
    assert repr(("华北 | 东", "Q1")) in text and repr(("华北", "东 | Q1")) in text, text
    assert repr("华北 | 东 | Q1") in text, text


def test_distinct_tuples_both_survive_the_flattening():
    """判据① 的正控：不撞键时一枚都不许少（守卫不是"少发一条"的开关）。"""
    raw = {("华北", "Q1"): 10.0, ("华北", "Q2"): 20.0, ("华东", "Q1"): 30.0}

    flat = tools._flatten_query_tuple_keys(raw)

    assert list(flat) == ["华北 | Q1", "华北 | Q2", "华东 | Q1"], flat
    assert list(flat.values()) == [10.0, 20.0, 30.0], flat


def test_a_tuple_key_colliding_with_a_plain_string_key_is_refused():
    """判据① 的第二形：元组展平后与本来就在位的字符串键同名，也算撞。

    这一发不许靠"后写覆盖前写"过关——那等于悄悄删掉一条真数据。
    """
    with pytest.raises(ValueError) as caught:
        tools._flatten_query_tuple_keys({"华北 | Q1": 1.0, ("华北", "Q1"): 2.0})

    assert "拒绝合并" in str(caught.value), caught.value


@pytest.mark.parametrize("key", [1, 2.5, True, None, "华北", 2024])
def test_non_tuple_key_types_are_left_exactly_alone(key):
    """判据②：只有元组动手。int/float/bool/None/str 键的**类型**必须原样在位。

    把 _flatten_query_key 改成无条件 str(key)，这一发红在键型上——json.dumps 自己会把
    int 键烤成字符串，本层多此一举就是把两种键洗成一种，将来读回来对不上账。
    """
    flat = tools._flatten_query_tuple_keys({key: "v"})

    assert len(flat) == 1, flat
    returned = next(iter(flat))
    assert type(returned) is type(key) and returned == key, (returned, key)


def test_scalar_values_and_non_tuple_containers_pass_through():
    """判据② 的下半条：值一个都不重建，只有 dict/list 两类容器会被重搭。"""
    assert tools._flatten_query_tuple_keys(3.0) == 3.0
    assert tools._flatten_query_tuple_keys("华北") == "华北"
    assert tools._flatten_query_tuple_keys(None) is None
    assert tools._flatten_query_tuple_keys([]) == []
    assert tools._flatten_query_tuple_keys({}) == {}

    #: 元组**值**不在本单病灶里（json.dumps 本来就把它渲染成数组），重建它才是顺手改形状。
    flat = tools._flatten_query_tuple_keys({("华北", "Q1"): ("甲", 1)})
    assert flat == {"华北 | Q1": ("甲", 1)}, flat
    assert isinstance(flat["华北 | Q1"], tuple), flat


def test_tuple_keys_deeper_in_the_structure_are_reached():
    """判据③：深层也要够得着，只展平最外层是假修。

    pandas 交不出这一形，但 safe_query 跑的是模型写的任意表达式，records 套 dict 再套
    多级索引这一族今天就在射程里。把递归那一格拆掉，这一发红在 "a | b"。
    """
    raw = {"outer": {("a", "b"): [{"inner": {("c", "d"): 1}}]}}

    flat = tools._flatten_query_tuple_keys(raw)

    assert flat == {"outer": {"a | b": [{"inner": {"c | d": 1}}]}}, flat


def test_flatten_key_joins_levels_in_order_without_inventing_names():
    """层级顺序原样保留；本层造不出索引名，就不许编一个出来。

    to_dict() 那一刻索引名已经丢了（真源在 app/tools/excel.py，不在本单写域），
    所以 "华北 | Q1" 是**值**的连接，"区域=华北" 那种带名字的键是假话——本钉挡住它。
    """
    assert tools._flatten_query_key(("华北", "Q1")) == "华北 | Q1"
    assert tools._flatten_query_key(("华北",)) == "华北"
    assert tools._flatten_query_key(("华北", "Q1", 2025)) == "华北 | Q1 | 2025"
    assert tools._flatten_query_key(5) == 5
