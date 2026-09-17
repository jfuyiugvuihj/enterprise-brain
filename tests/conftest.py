"""conftest: 共享 fixtures"""
import atexit
import inspect
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

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


# ==================== 跟进单 R53：测试期把 Chroma 目录钉进临时沙箱 ====================
# app/rag/retriever.py:89 的默认参数是相对路径 "./chroma_db"，__init__ 第 90 行立刻
# os.makedirs(chroma_dir)，第 190-191 行再 chromadb.PersistentClient(path=chroma_dir)。
# pytest 的 cwd 就是仓库根，所以 app/rag/retrieval_pipeline.py:142、:174 那两处无参
# DocumentRetriever() 会把向量库直接写进工作树里已被 git 跟踪的 ./chroma_db。
# 和上面的 PERSISTENCE_*、DATABASE_URL 同一招：必须在 conftest 导入期动手，因为默认值挂在
# 函数对象上，等测试模块 import 完 app 再改就晚了。本单不改 app/ 的签名，也不新增生产环境变量。
CHROMA_SANDBOX_ROOT = tempfile.mkdtemp(prefix="enterprise-brain-tests-chroma-")
CHROMA_SANDBOX = os.path.join(CHROMA_SANDBOX_ROOT, "chroma_db")
# EB_TEST_KEEP_SANDBOX=1 只用于取证：跑完保留沙箱，好让人核对 Chroma 确实落在临时目录。
KEEP_TEST_SANDBOXES = os.environ.get("EB_TEST_KEEP_SANDBOX", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _positional_default_names(init) -> list[str]:
    """__init__ 上带默认值的位置参数名，顺序与 __defaults__ 尾部对齐。"""
    parameters = list(inspect.signature(init).parameters.values())
    if not parameters or parameters[0].name != "self":
        raise RuntimeError(f"{init!r} 不像普通的实例 __init__，无法定位 chroma_dir 默认值")
    names = []
    for parameter in parameters[1:]:
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if parameter.kind is parameter.KEYWORD_ONLY or parameter.default is parameter.empty:
            continue
        names.append(parameter.name)
    return names


def _chroma_default_index(init) -> int:
    """chroma_dir 在 __init__.__defaults__ 里的下标；签名一变就抛，绝不静默跳过。"""
    names = _positional_default_names(init)
    if "chroma_dir" not in names:
        raise RuntimeError(
            "DocumentRetriever.__init__ 的签名里找不到带默认值的 chroma_dir"
            f"（实际带默认值的位置参数={names}）。R53 拒绝在目录没钉死的情况下跑测试。"
        )
    defaults = init.__defaults__ or ()
    if len(defaults) != len(names):
        raise RuntimeError(
            f"__defaults__ 有 {len(defaults)} 项，签名声明的带默认值位置参数有 {len(names)} 项 {names}，"
            "两者无法对应；R53 拒绝猜测下标。"
        )
    # __defaults__ 与签名里「带默认值的位置参数」从后往前一一对应：
    # names[-1] <-> defaults[-1]，所以偏移量是两边长度的差。当前两者等长，偏移恒为 0，
    # 写成通式是为了万一以后 chroma_dir 后面又多了别的带默认值参数，也不会钉错位置。
    return names.index("chroma_dir") - (len(names) - len(defaults))


def _pin_chroma_sandbox_default(sandbox_dir: str, retriever_class=None):
    """把 DocumentRetriever 的 chroma_dir 默认值改写成沙箱绝对路径。

    拿不到目标就抛 RuntimeError：静默跳过等于本单白做——每次 pytest 又会去写工作树的
    ./chroma_db。返回 (defaults 下标, 被替换掉的出厂默认值)。
    """
    if retriever_class is None:
        # 只有 conftest 会在测试模块之前 import app，改写发生在这一行之前才有效。
        import app.rag.retriever as rag_retriever

        retriever_class = getattr(rag_retriever, "DocumentRetriever", None)
        if retriever_class is None:
            raise RuntimeError("app.rag.retriever 里没有 DocumentRetriever，R53 无处可钉。")
    init = getattr(retriever_class, "__init__", None)
    if not callable(init):
        raise RuntimeError(f"{retriever_class!r} 没有可调用的 __init__，R53 无处可钉。")
    index = _chroma_default_index(init)
    original = init.__defaults__[index]
    if not isinstance(original, str):
        raise RuntimeError(f"chroma_dir 的默认值不是路径字符串，而是 {original!r}。")
    sandbox = os.path.abspath(str(sandbox_dir))
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if _path_within(repo_root, sandbox):
        raise RuntimeError(f"Chroma 沙箱不能落在工作树里：{sandbox}")
    pinned = list(init.__defaults__)
    pinned[index] = sandbox
    try:
        init.__defaults__ = tuple(pinned)
    except (AttributeError, TypeError) as exc:
        raise RuntimeError(
            f"改写 {retriever_class.__name__}.__init__.__defaults__ 失败：{exc}；"
            "生产实现换了写法，R53 需要改用别的钩子，而不是放过它。"
        ) from exc
    if init.__defaults__[index] != sandbox:
        raise RuntimeError("Chroma 沙箱默认值改写之后没有生效。")
    return index, original


def _path_within(parent: str, child: str) -> bool:
    """child 是否位于 parent 之内（含相等）。两个参数都按绝对路径规范化后比较。"""
    parent = os.path.normcase(os.path.abspath(parent))
    child = os.path.normcase(os.path.abspath(child))
    return child == parent or child.startswith(parent + os.sep)


def _discard_chroma_sandbox() -> str | None:
    """尽力删掉本次会话的 Chroma 沙箱，删不掉就把路径返回出去，绝不静默。

    Windows 上 chromadb 会一直攥着 chroma.sqlite3 的文件句柄，连
    SharedSystemClient.clear_system_cache() 都不释放，所以会话结束时的清理只能尽力而为：
    最坏情况是 %TEMP% 里留下一个一百多 KB 的目录，工作树的 ./chroma_db 始终不受影响。
    """
    if KEEP_TEST_SANDBOXES:
        return None
    shutil.rmtree(CHROMA_SANDBOX_ROOT, ignore_errors=True)
    return CHROMA_SANDBOX_ROOT if os.path.isdir(CHROMA_SANDBOX_ROOT) else None


CHROMA_DIR_DEFAULT_INDEX, CHROMA_DIR_SHIPPED_DEFAULT = _pin_chroma_sandbox_default(
    CHROMA_SANDBOX
)

assert os.path.isabs(CHROMA_SANDBOX), "the Chroma sandbox must be an absolute path"
assert isinstance(CHROMA_DIR_SHIPPED_DEFAULT, str), "chroma_dir 的出厂默认值必须是路径字符串"
assert CHROMA_SANDBOX_ROOT != _PERSISTENCE_SANDBOX, "Chroma 沙箱要与持久化沙箱分开，便于分别取证"
# 交叉标记：守卫测试靠它确认改写真的发生了，而不是在 except 分支里被静默跳过。
os.environ["ENTERPRISE_BRAIN_PYTEST_CHROMA_DIR"] = CHROMA_SANDBOX
# --collect-only 这类调用不会走到 fixture 拆除，沙箱目录就交给 atexit 收尾。
atexit.register(_discard_chroma_sandbox)


@pytest.fixture(scope="session", autouse=True)
def clean_persistence_sandbox():
    """Run the whole suite against the sandboxes above, then discard them."""
    yield
    shutil.rmtree(_PERSISTENCE_SANDBOX, ignore_errors=True)
    if KEEP_TEST_SANDBOXES:
        print(f"[R53] chroma sandbox retained at {CHROMA_SANDBOX_ROOT}")
    else:
        leftover = _discard_chroma_sandbox()
        if leftover:
            print(f"[R53] chroma sandbox left behind (chromadb still holds the sqlite handle): {leftover}")


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """The only DSN an app module may resolve during a test session (R20)."""
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def chroma_sandbox():
    """R53 的沙箱信息：目录、被改写参数的下标、出厂默认值，供守卫测试核对。"""
    return SimpleNamespace(
        root=CHROMA_SANDBOX_ROOT,
        path=CHROMA_SANDBOX,
        default_index=CHROMA_DIR_DEFAULT_INDEX,
        shipped_default=CHROMA_DIR_SHIPPED_DEFAULT,
        repo_root=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        marker=os.environ["ENTERPRISE_BRAIN_PYTEST_CHROMA_DIR"],
    )


@pytest.fixture
def pin_chroma_sandbox_default():
    """把改写函数本身交给测试，用来验证它「签名不对就抛」而不是静默跳过。"""
    return _pin_chroma_sandbox_default
