"""仓库根 conftest.py —— 跟进单 R134：Chroma 沙箱不许只在 tests/ 里成立。

为什么需要这一枚文件（本机实测，主树与本树同形）：
  pytest 只沿「命令行参数的祖先链」加载 conftest.py。把 tests/ 之外的路径交给 pytest ——
  例如 `pytest app/api/v1/chat.py` —— 根本不加载 tests/conftest.py，而
  app/api/v1/chat.py:83 是模块级的 DocumentRetriever()：一 import 就朝被 git 跟踪的
  ./chroma_db 打开 chromadb.PersistentClient，chroma_db/chroma.sqlite3 当场写脏
  （尺寸 6 262 784 一字不变，sha256 由 0b8cb318a0e0ba18 变成 c43c3e8a950a64b1）。
  R53 的钉子装在 tests/conftest.py 的导入期，管不到这种起法；本文件把它抬到仓库根。

本文件只装「依赖级」的那半（PersistentClient 改道 + 工作树写回基线），不调
pin_retriever_default：那一步要 import app.rag.retriever，而那枚模块在 :19 就调
load_dotenv()，而本文件比 tests/conftest.py 先加载 —— 在这儿引 app 等于把 R70
「宿主的 .env 一个字都不许进测试进程」重新放开。app 级的默认值改写仍由
tests/conftest.py 装（它在同一文件里先把 load_dotenv 换成桩，顺序天然正确）。
这层分工不是靠注释维持的：tests/test_r134_chroma_writeback.py 里有一枚静态钉，
本文件若出现任何 app.* 导入会当场红。
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tests import _chroma_sandbox as chroma_sandbox_pins  # noqa: E402  -- 上面刚插好 sys.path

chroma_sandbox_pins.install_chroma_sandbox_pins(pin_retriever_default=False)


def pytest_report_header(config):
    """抬头露一次沙箱落点：子进程用例据此廉价证明「这种起法确实把钉子装上了」。"""
    return "R134 chroma sandbox: {}".format(chroma_sandbox_pins.CHROMA_SANDBOX_ROOT)