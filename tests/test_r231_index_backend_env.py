"""R231 判据①②④：`INDEX_BACKEND` 从今天起是一枚真旋钮，不再是一行只能改代码的字面量。

本文件只问开关本身，全程不连库、不打 Ollama、不开服务：断言都落在 `read_backend()` /
`pgvector_reads_enabled()` 这两枚判定上，外加一句"任何输入都不许答出没登记过的引擎"。
真正的"翻过去之后读腿发 SQL"由判据③那份件与现场实测负责，本文件不重复演一遍。

两枚反证钉在这里，逐条写在 docstring 里：

- 摘掉 env 钩子（`read_backend` 只读常量）—— ① 那几枚当场红。
- 把优先级反过来（常量赢）—— `test_the_environment_outranks_the_module_constant` 红。

每一枚用例都从 `clean_env` 起步：先把环境里的 `INDEX_BACKEND` 摘掉、再把常量放回 shipped
值。这不是仪式感 —— 加了钩子之后，"这台机器恰好有一行 env"就足以让任何一条断言换个答案，
所以前置必须写在脸上（R231 交回单判据③那条实测：机器上有 pgvector 时 R59b 两枚默认态钉当场红）。
"""

import logging

import pytest

from app.rag import indexing

#: 那句告警逐字抄一遍，判据④要求它的语义不许变味。这里**不**从 INDEX_BACKENDS /
#: INDEX_BACKEND_DEFAULT 反推：反推出来的断言对任何拼法都成立，就没有齿。
TYPO_WARNING = ("[Indexing] INDEX_BACKEND='pg_vetcor' is not one of "
                "['chroma', 'pgvector']; reads stay on chroma.")


@pytest.fixture
def clean_env(monkeypatch):
    """起点＝"这台机器从没提过这枚开关"：env 摘掉，常量放回 shipped 值。"""
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.INDEX_BACKEND_DEFAULT)
    return monkeypatch


# ------------------------------------------------------------------ 旋钮的身份与默认态


def test_the_environment_spelling_is_the_switch_itself(clean_env):
    """旋钮的名字必须就是 INDEX_BACKEND：操作者往 env 里写的正是这一串，多个前缀就翻不动。"""
    assert indexing.INDEX_BACKEND_ENV == "INDEX_BACKEND"


def test_the_shipped_state_still_answers_the_legacy_engine(clean_env):
    """判据②的现场版：什么都不设，读路径必须仍在 chroma，且两枚字面量一个字没被翻过。"""
    assert indexing.INDEX_BACKEND_DEFAULT == "chroma"
    assert indexing.PGVECTOR_BACKEND == "pgvector"
    assert indexing.INDEX_BACKEND == indexing.INDEX_BACKEND_DEFAULT
    assert indexing.read_backend() == "chroma"
    assert indexing.pgvector_reads_enabled() is False


# ------------------------------------------------------------------ ①：旋钮真的生效


def test_the_env_moves_the_reads_at_call_time_not_at_import(clean_env):
    """本模块在收集阶段就被 import 了 —— 设完 env 答案当场跟着变，才证明没在 import 期固化。

    摘掉 `read_backend` 里那句 `os.getenv(INDEX_BACKEND_ENV, ...)`：这条立刻红，而且红在
    第二行（"设了 env 仍答 chroma"），正是 R59c 量具要抓的"假合闸"形状。
    """
    assert indexing.read_backend() == "chroma"

    clean_env.setenv(indexing.INDEX_BACKEND_ENV, "pgvector")

    assert indexing.read_backend() == "pgvector"
    assert indexing.pgvector_reads_enabled() is True

    clean_env.setenv(indexing.INDEX_BACKEND_ENV, "chroma")

    assert indexing.read_backend() == "chroma"
    assert indexing.pgvector_reads_enabled() is False


def test_removing_the_env_line_is_the_rollback(clean_env):
    """回滚 = 删掉那一行：摘掉 env 之后必须回到 shipped 引擎，不需要重启前的任何补偿。"""
    clean_env.setenv(indexing.INDEX_BACKEND_ENV, "pgvector")
    assert indexing.read_backend() == "pgvector"

    clean_env.delenv(indexing.INDEX_BACKEND_ENV)

    assert indexing.read_backend() == indexing.INDEX_BACKEND_DEFAULT
    assert indexing.pgvector_reads_enabled() is False


def test_setting_only_the_constant_still_moves_the_reads(clean_env):
    """老路不许断：R59b 那批钉就是这么用的 —— 不设 env、只改模块常量，读路径照样跟着走。"""
    clean_env.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)

    assert indexing.read_backend() == "pgvector"
    assert indexing.pgvector_reads_enabled() is True


def test_the_environment_outranks_the_module_constant(clean_env):
    """两者同时给且不一致时谁来答：env 赢。这一格是设计裁决，判据③不许留白。

    理由在交回单第 4 节：旋钮的意义是"部署能盖过镜像"，包括将来代码默认值翻成 pgvector
    之后操作者仍能用一行 env 退回来。代价也写在同一处 —— 一台 shell 里残留
    `INDEX_BACKEND` 的机器会盖过代码，连测试运行也不例外，所以 `clean_env` 是必需的。
    把优先级反过来：这两行立刻红。
    """
    clean_env.setenv(indexing.INDEX_BACKEND_ENV, "pgvector")
    clean_env.setattr(indexing, "INDEX_BACKEND", "chroma")
    assert indexing.read_backend() == "pgvector"

    clean_env.setenv(indexing.INDEX_BACKEND_ENV, "chroma")
    clean_env.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    assert indexing.read_backend() == "chroma"
    assert indexing.pgvector_reads_enabled() is False


# ------------------------------------------------------------------ ④：形状与非法值


@pytest.mark.parametrize("raw", ["PGVECTOR", " pgvector ", "\tPgVector\n", "CHROMA", " Chroma "])
def test_case_and_padding_are_normalized_without_a_warning(clean_env, raw, caplog):
    """`" PGVECTOR "` 是操作者手边最常见的形状：认，并且不许为大小写与空格吵一句。"""
    clean_env.setenv(indexing.INDEX_BACKEND_ENV, raw)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        answer = indexing.read_backend()

    assert answer == raw.strip().lower()
    assert not [item for item in caplog.records if item.levelno >= logging.WARNING], (
        caplog.messages)


@pytest.mark.parametrize("raw", ["", " ", "\t"])
def test_a_blank_env_is_nothing_said(clean_env, raw, caplog):
    """`INDEX_BACKEND=`（占一行没值）是"我把它去掉了"的写法，不是拼错 —— 与 VECTOR_DUAL_WRITE 同口径。"""
    clean_env.setenv(indexing.INDEX_BACKEND_ENV, raw)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        assert indexing.read_backend() == "chroma"

    assert not [item for item in caplog.records if item.levelno >= logging.WARNING], (
        caplog.messages)


def test_a_blank_env_leaves_the_constant_in_charge(clean_env):
    """空 env 落回常量，而不是落回默认：否则"改常量"这条老路会被一行空环境值悄悄掐断。"""
    clean_env.setenv(indexing.INDEX_BACKEND_ENV, "")
    clean_env.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)

    assert indexing.read_backend() == "pgvector"
    assert indexing.pgvector_reads_enabled() is True


@pytest.mark.parametrize("raw", ["pg_vetcor", "postgres", "pgvector2", "vector", "1", "true",
                                 "pgvector,chroma", "pgvector;chroma"])
def test_an_unknown_env_value_stays_on_the_shipped_engine_and_says_so(clean_env, raw, caplog):
    """认不出来的值不许悄悄试另一个引擎：回落 shipped 引擎 + 落一句告警（判据④）。"""
    clean_env.setenv(indexing.INDEX_BACKEND_ENV, raw)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        assert indexing.read_backend() == "chroma"
        assert indexing.pgvector_reads_enabled() is False

    expected = ("[Indexing] INDEX_BACKEND=%r is not one of ['chroma', 'pgvector']; "
                "reads stay on chroma." % raw)
    assert expected in caplog.messages, caplog.messages


def test_the_r59b_warning_sentence_is_byte_for_byte_the_same(clean_env, caplog):
    """那句 R59b 就有的告警一个字没改：拼错的值、告警的措辞、回落到哪，全按原样。"""
    clean_env.setenv(indexing.INDEX_BACKEND_ENV, "pg_vetcor")

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        assert indexing.read_backend() == "chroma"

    assert TYPO_WARNING in caplog.messages, caplog.messages


def test_an_unknown_env_value_is_not_rescued_by_the_constant(clean_env, caplog):
    """env 拼错时常量不许救场：这时候操作者的意图已经是未知数，只有 shipped 引擎算诚实。"""
    clean_env.setenv(indexing.INDEX_BACKEND_ENV, "pg_vetcor")
    clean_env.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        assert indexing.read_backend() == "chroma"

    assert TYPO_WARNING in caplog.messages, caplog.messages


@pytest.mark.parametrize("raw", ["pgvector", "PGVECTOR", "bogus", "", " ", "0", None])
def test_the_resolver_never_answers_an_unregistered_engine(clean_env, raw):
    """无论喂什么，出口只能是 INDEX_BACKENDS 里那两个值 —— 版本台账那句
    `if backend not in INDEX_BACKENDS: raise` 才永远不会被自家发布路径踩到。
    """
    if raw is None:
        clean_env.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    else:
        clean_env.setenv(indexing.INDEX_BACKEND_ENV, raw)

    assert indexing.read_backend() in indexing.INDEX_BACKENDS
    assert indexing.pgvector_reads_enabled() is (indexing.read_backend() == "pgvector")
