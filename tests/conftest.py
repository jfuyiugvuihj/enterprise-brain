"""conftest: 共享 fixtures"""
import os
import shutil
import sys
import tempfile

import pytest

# 确保项目根在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 测试期把 JSON 持久化账本重定向到临时目录。
# app.storage.artifacts 与 app.storage.datasets 在 import 期就调用
# build_persistence_adapter() 固化了路径，所以环境变量必须在本文件
# 导入 app 之前设置，放进 fixture 已经太晚。
_PERSISTENCE_SANDBOX = tempfile.mkdtemp(prefix="enterprise-brain-tests-")
os.environ.setdefault("PERSISTENCE_BACKEND", "json")
os.environ.setdefault(
    "PERSISTENCE_FALLBACK_PATH",
    os.path.join(_PERSISTENCE_SANDBOX, "persistence.json"),
)


@pytest.fixture(scope="session", autouse=True)
def clean_persistence_sandbox():
    """Run the whole suite against the sandbox above, then discard it."""
    yield
    shutil.rmtree(_PERSISTENCE_SANDBOX, ignore_errors=True)
