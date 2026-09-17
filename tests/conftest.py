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

# 跟进单 R20（docs/handoff/2026-09-15-backend-followup-requests.md §16）：
# 测试期一律不得触达宿主 PostgreSQL。app.common.auth 等模块在 import 期就用
# os.getenv("DATABASE_URL", ...) 固化了连接串，并且 auth 在导入时会真连一次、
# 建一次表，所以这个变量必须在本文件（早于任何测试模块导入 app）被钉住，
# 放进 fixture 已经太晚。dotenv.load_dotenv() 不覆盖已存在的环境变量，
# 因此 .env 里的真实凭据没有机会再被读进来。
# 这个串不可能落到宿主 5432：主机写死 127.0.0.1，端口是保留端口 1（本机宿主的
# PostgreSQL 实测由原生 postgres.exe 监听 5432，Docker 容器根本没发布宿主端口），
# 库名带 _pytest 后缀，auth 随即退回它自己的离线分支。
# connect_timeout=1 不是安全设定，只是让这次注定失败的探测快点结束：实测不写它时
# psycopg 要挂到操作系统 TCP 超时（本机约 130s）才抛 ConnectionTimeout，会把整个
# 测试会话拖慢两分钟以上。
TEST_DATABASE_URL = (
    "postgresql://enterprise_brain_pytest@127.0.0.1:1/enterprise_brain_pytest"
    "?connect_timeout=1"
)

assert TEST_DATABASE_URL.startswith("postgresql://"), "the pin must stay a parseable DSN"
assert "127.0.0.1:1/" in TEST_DATABASE_URL, "the pin must aim at the reserved port 1"
assert ":5432" not in TEST_DATABASE_URL and "localhost" not in TEST_DATABASE_URL, (
    "the test DATABASE_URL must never point at the host PostgreSQL port"
)
assert "connect_timeout=1" in TEST_DATABASE_URL, "the failed probe must fail fast, not hang"

os.environ["DATABASE_URL"] = TEST_DATABASE_URL


@pytest.fixture(scope="session", autouse=True)
def clean_persistence_sandbox():
    """Run the whole suite against the sandbox above, then discard it."""
    yield
    shutil.rmtree(_PERSISTENCE_SANDBOX, ignore_errors=True)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """The only DSN an app module may resolve during a test session (R20)."""
    return TEST_DATABASE_URL
