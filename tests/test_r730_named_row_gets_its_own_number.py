r"""B18 · 问句点名一行，屏上那个数必须是那一行的数（R730）。

病形现读（10-08 09:5x）：夹具表 41 行，最后一行 项目=走查标记425273 / 数值=1325273，
问「它里面「走查标记425273」这一行的数值是多少」，屏上答「数值为 3，对应数据行：
项目=月度差旅425273-01」——把表里第一行当成了被点名的那一行。`_answer_query` 那四段里
没有一段是"照问句点名的值取行"，这一发只落到兜底预览；而预览每行只印一枚 `label_col`
（这张表挑中的是「部门」，41 行全是「市场部」），被点名的那一行在 prompt 里根本没有身份。

断言走真产物：`_answer_query` 交出去的那段话就是模型看得见的那一份，不钉源码形状。

反证（本文件负责具名，跑完逐字还原）：把 `_answer_query` 里那一圈
`for hit_column, hit_value, hit_frame in _named_row_hits(...)` 摘掉 ⇒ 前 3 枚当场红
（`3 failed, 1 passed`），第 4 枚（防过度触发）在摘与不摘两种状态下都绿——它钉的是
"提一个部门不等于点名一行"，正是本段不许越界的那一格。
"""

import io

import pandas as pd

from app.agents.tools import _answer_query
from app.tools.excel import select_text_columns

NONCE = "425273"
MARKER = "走查标记" + NONCE
TRUE_VALUE = str(900000 + int(NONCE))
FIRST_ROW_VALUE = "3"


def _frame():
    grid = ["部门,项目,数值"]
    grid += ["市场部,月度差旅%s-%02d,%d" % (NONCE, index, index * 3) for index in range(1, 41)]
    grid.append("市场部," + MARKER + "," + TRUE_VALUE)
    df = pd.read_csv(io.StringIO("\n".join(grid)))
    return df, df.select_dtypes(include=["number"]).columns.tolist(), select_text_columns(df)


def _text(query):
    df, numeric, textual = _frame()
    return "\n".join(_answer_query(df, query, numeric, textual))


def test_a_row_named_in_quotes_returns_its_own_number():
    """引号里点名一行 ⇒ 交出去的那段话带着那一行的真值，而不是表里第一行的那个数。"""
    answer = _text(
        "公司知识库里有一张表叫 b18-" + NONCE + ".csv，它里面「" + MARKER
        + "」这一行的数值是多少？请给出来源文件名。"
    )
    assert TRUE_VALUE in answer
    assert MARKER in answer
    assert "数值为 " + FIRST_ROW_VALUE not in answer


def test_a_row_named_without_quotes_still_returns_its_own_number():
    """客户不打引号也认得：整值相等这一条通路就够，不需要引号。"""
    answer = _text(MARKER + " 这一行的数值是多少")
    assert TRUE_VALUE in answer
    assert MARKER in answer


def test_extra_words_inside_the_quotes_do_not_lose_the_row():
    """「走查标记425273这一行」——引号里多打了三个字，那一行也要连名带数一起交回去。

    真值单独出现不算数：兜底预览按数值降序，最大的那一个数恰好就是它，可那一段印的是
    「部门=市场部: 数值=1325273」，41 行全是市场部，模型照样分不出这是哪一行。
    所以这一枚同时钉名字与数：被点名的那一行必须**带着自己的名字**出现在 prompt 里。
    """
    answer = _text("请只回答「" + MARKER + "这一行」的数值")
    assert TRUE_VALUE in answer
    assert MARKER in answer


def test_mentioning_a_department_is_not_mistaken_for_naming_a_row():
    """「市场部的数值合计是多少」挑走整张表 41 行里的 41 行——那不是点名一行。

    这一格钉的是本段不许越界：按维度切一刀归分组汇总那一段管，点名行这一段不许插话，
    否则每张按部门切的表都会多出一段客户没要的料，把已经很挤的 prompt 预算吃掉。
    """
    answer = _text("市场部的数值合计是多少")
    assert "问句点名的行" not in answer
