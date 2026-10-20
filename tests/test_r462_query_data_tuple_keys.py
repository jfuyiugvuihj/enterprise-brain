"""R462 · query_data 这条腿不许拿 tuple 当 JSON 的键（跟进单 §133 五判据）。

病历（09-28 云窗真机 · report-11）：容器日志原文
    执行失败: keys must be str, int, float, bool or None, not tuple
员工那一侧看到的那一句是 deploy/queue_worker.py 的 REPORT_TURN_FAILURE_TEXT
「本轮未产出任何结论，请重试或补充数据范围。」——报告档在队列里跑完，正文只剩兜底桩。

复现到的真抛点是 app/agents/tools.py 里那一次 json.dumps（改前 :1400）；造键处在
app/tools/excel.py::safe_query 交回结构的那一刻：
  - :476 Series.to_dict() —— df.groupby(['区域','季度'])['销售额'].sum() 那一族；
  - :474 DataFrame.to_dict(orient="records") —— df.groupby('区域').agg({'销售额': ['sum','mean']}) 那一族。
两族交回的键都是元组，而 json.dumps 的 default= 只作用于值，所以那一句当场抛、
整条腿连带整轮问答一起死。造键那两行不在本单写域，本层的 JSON 契约出口就是
那一行 dumps，所以修在这里：进 dumps 之前把层级元组展成字符串键。

本件钉三格：① 两族真道负载交回字符串键且每一枚数值都在位（不缺一行、不并两行）；
② 没有 tuple 键的负载，交出去的 JSON 与改前逐字节相同（本单不顺手改在绿路径的形状）；
③ 那一行 dumps 既没有被 try 兜住，也没有 skipkeys，键的展平由 _flatten_query_tuple_keys
做——把"只是把异常压掉"那一类修法当场钉红。
"""
import ast
import inspect
import json

import pandas as pd
import pytest

from app.agents import tools

#: 与 report-11 同形的最小表：两级 groupby 与 agg 多聚合都出得了 tuple 键。
FRAME = pd.DataFrame(
    {
        "区域": ["华北", "华北", "华东", "华东"],
        "季度": ["Q1", "Q2", "Q1", "Q2"],
        "销售额": [10.0, 20.0, 30.0, 40.0],
        "年份": [2024, 2024, 2025, 2025],
    }
)

GROUP_TWO_LEVEL = "df.groupby(['区域','季度'])['销售额'].sum()"
AGG_MULTI = "df.groupby('区域').agg({'销售额': ['sum', 'mean']})"
SINGLE_LEVEL = "df.groupby('区域')['销售额'].sum()"
#: 单级整数索引：json.dumps 本来就认 int 键，本单一个字都不许动它。
INT_KEY = "df.groupby('年份')['销售额'].sum()"


def _tool_config():
    """带真身份与证据袋的 config：query_data 要先过授权那一关才走得到序列化那一步。"""
    from app.agents.evidence import new_evidence_bag
    from app.common.identity import Principal

    identity = {"username": "r462", "role": "admin", "department": "财务部"}
    conf = dict(identity)
    conf["principal"] = Principal.from_user(identity, auth_source="agent")
    conf["evidence_bag"] = new_evidence_bag()
    conf["thread_id"] = "thread-r462"
    conf["worker"] = "data"
    conf["step_id"] = "r462:worker:query"
    return {"configurable": conf}


def _run_query_leg(monkeypatch, code):
    """把数据腿的读文件与行级过滤钉成一张真表，其余（safe_query、装箱、json 序列化）全真跑。"""
    import app.common.rbac as rbac
    import app.tools.excel as excel
    from app.storage import datasets as dataset_storage

    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "8192")
    monkeypatch.setattr(tools, "_authorized_dataset_files", lambda config: ([("费用明细.xlsx", "p")], None))
    monkeypatch.setattr(dataset_storage.DatasetRegistry, "get_active_by_filename", lambda self, filename: None)
    monkeypatch.setattr(tools, "_record_dataset_evidence", lambda config, filename, df: None)
    monkeypatch.setattr(excel, "load_excel", lambda path: FRAME)
    monkeypatch.setattr(
        rbac,
        "filter_dataframe_rows_with_scope",
        lambda df, role=None, department=None: (df, {"rows_in": int(df.shape[0]), "rows_out": int(df.shape[0])}),
    )
    monkeypatch.setattr(tools, "_llm_pandas_code", lambda df, query: code)
    return tools._query_data("各区域各季度销售额", _tool_config())


def _payload_text(out):
    """从「📊 x.xlsx 查询结果:」那一整块里取出模型实际读到的 JSON 文本。"""
    assert out.startswith("📊 费用明细.xlsx 查询结果:"), out
    assert tools.PACK_TRUNCATION_MARK not in out, out
    return out.split("查询结果:", 1)[1].strip()


def test_two_level_groupby_hands_the_model_string_keys(monkeypatch):
    """判据① 之一：两级 groupby 的 Series 不再把元组键送进 json.dumps。

    摘掉 app/agents/tools.py 那次 dumps 之前的 _flatten_query_tuple_keys，这一发当场红在
    TypeError: keys must be str, int, float, bool or None, not tuple（本单复现的原文）。
    """
    payload = json.loads(_payload_text(_run_query_leg(monkeypatch, GROUP_TWO_LEVEL)))

    assert all(isinstance(key, str) for key in payload), payload
    assert payload == {
        "华北 | Q1": 10.0,
        "华北 | Q2": 20.0,
        "华东 | Q1": 30.0,
        "华东 | Q2": 40.0,
    }, "四行数值必须逐枚在位：缺一行是丢数据，并两行是造假"


def test_multiindex_columns_records_hands_the_model_string_keys(monkeypatch):
    """判据① 之二：agg 多聚合落进 records 的列级元组键，同一把尺治。

    这一族改前交回的是 [{('销售额', 'sum'): 70.0, ...}] ——键是元组，dumps 一样炸。
    """
    payload = json.loads(_payload_text(_run_query_leg(monkeypatch, AGG_MULTI)))

    assert isinstance(payload, list) and len(payload) == 2, payload
    assert all(isinstance(key, str) for row in payload for key in row), payload
    assert payload == [
        {"销售额 | sum": 70.0, "销售额 | mean": 35.0},
        {"销售额 | sum": 30.0, "销售额 | mean": 15.0},
    ], "每一行是一区域：华北 70/35、华东 30/15，不许错位"


@pytest.mark.parametrize("code", [SINGLE_LEVEL, INT_KEY])
def test_key_shapes_without_tuples_are_untouched(monkeypatch, code):
    """判据②：本来就能序列化的负载，交出去的 JSON 与改前逐字节相同。

    期望值不抄字符串，而是拿同一张表真跑一遍 safe_query、按改前那一行 dumps 原样序列化。
    诚实记一句边界：这一枚抓不住"把所有键都 str() 化"（json 本来就把 int 键写成字符串，
    两种键出来的 JSON 逐字节相同，实测 刀5 里这一发仍是绿的）；那一格由
    tests/test_r462_tuple_key_flattening.py 的键型钉守着。本单治的是元组，不是"所有奇怪的键"。
    """
    from app.tools.excel import safe_query

    raw = safe_query(FRAME.copy(), code)["result"]
    assert all(not isinstance(key, tuple) for key in raw), raw

    out = _run_query_leg(monkeypatch, code)

    assert _payload_text(out) == json.dumps(raw, ensure_ascii=False, default=str)


def test_the_serialization_is_fixed_at_the_key_layer_not_by_swallowing():
    """判据③：那一行 dumps 必须由展平键的那一枚函数供料，且不在任何 try 里面。

    钉形状不钉行号：_query_data 的源码里 json.dumps 恰一枚；它的首参必须是
    _flatten_query_tuple_keys 的调用；不许出现 skipkeys；整个函数体里没有任何 try
    把它兜住——加 try/except 或 skipkeys=True 都是把"算错了"洗成"少一列"，那比炸更坏。
    """
    tree = ast.parse(inspect.getsource(tools._query_data))
    dumps_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "dumps"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "json"
    ]
    assert len(dumps_calls) == 1, [ast.dump(node) for node in dumps_calls]
    call = dumps_calls[0]

    assert call.args, "首参必须显式是展平之后的结构"
    fed = call.args[0]
    assert isinstance(fed, ast.Call) and isinstance(fed.func, ast.Name), ast.dump(fed)
    assert fed.func.id == "_flatten_query_tuple_keys", ast.dump(fed)

    assert not any(keyword.arg == "skipkeys" for keyword in call.keywords), call
    inside_try = [
        node for node in ast.walk(tree) if isinstance(node, ast.Try) and any(sub is call for sub in ast.walk(node))
    ]
    assert not inside_try, "序列化失败必须原样上抛，不许就地咽下去"


def test_default_str_alone_does_not_fix_tuple_keys():
    """反掩盖钉：跟进单里被点名的那条捷径（加 default=str）实测救不了键。

    这一枚不测本仓代码，测的是 json 的事实——它同时说明本单那一行 default=str（改前就在，
    管的是值）没有被当成修法，也没有被摘掉。
    """
    raw = {("华北", "Q1"): 10.0}

    with pytest.raises(TypeError) as caught:
        json.dumps(raw, ensure_ascii=False, default=str)
    assert "keys must be str" in str(caught.value)

    flat = tools._flatten_query_tuple_keys(raw)
    assert json.dumps(flat, ensure_ascii=False, default=str) == '{"华北 | Q1": 10.0}'
