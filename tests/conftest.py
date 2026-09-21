"""conftest: 共享 fixtures"""
import atexit
import inspect
import os
import shutil
import socket
import sys
import tempfile
import traceback
from types import SimpleNamespace
from urllib.parse import urlsplit

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


# ==================== 跟进单 R70：宿主的 .env 在测试期一个字都不许进进程 ====================
# 缺陷链（实测 09-18 13:2x，主树 @50aff1a，解释器 .venv\Scripts\python.exe；探针脚本在仓库外，未改 app/**）：
# R20 只钉了上面的 DATABASE_URL，依据是"load_dotenv() 不覆盖已存在的键"。那条依据只对 conftest
# 抢在 import 之前赋过值的键成立。app 侧有 5 个模块在 import 期调 load_dotenv()
# （nodes.py:10 / orchestrator.py:21 / auth.py:13 / model_handler.py:28 / retriever.py:19），
# 而 app/common/monitoring.py 的 build_health_snapshot() 要到**调用期**才懒加载 auth 与 retriever。
# 于是"先把模型变量擦干净、再打一次健康快照"的用例，会在打快照这一刻被宿主 .env 重新灌回真机模型名。
# 探针实测：delenv 四个模型变量 -> build_health_snapshot() -> os.environ["OLLAMA_MODEL"]
# == 'qwen2.5:14b'（主树 .env 的原值），调用栈记到 auth.py:13 与 retriever.py:19。
# 症状：test_model_discovery_selection.py::test_health_snapshot_reports_the_resolved_model_source
# 在主树稳定红（单独跑也红，与顺序无关），而 .env 不入版本库、子树里没有它，所以这条红**只在业主
# 机器上存在**，每个 Agent 在自己的树里复跑都是绿的 —— 全量基线长期对不上，它有份。
# 污染还是粘性的：一旦灌进来，OLLAMA_MODEL 常驻进程到会话结束，后面任何"干净环境"用例都能被带偏。
# 修法：把 load_dotenv 换成"只记账、不读文件"的桩。app 侧写的是 from dotenv import load_dotenv，
# 绑定发生在各自的 import 期，而 conftest 早于任何测试模块导入 app（本文件无顶层 app 导入），桩一定先装上。
# 真机验收入口 tests/_live_model.py 不靠 .env：它要操作方在 shell 里显式给 EB_OLLAMA_ACCEPTANCE，
# 模型名走 discovery 或 shell 变量，所以下面的闸门只在离线态生效，不挡总控自己的计时入口。
_LIVE_ACCEPTANCE_REQUESTED = (os.getenv("EB_OLLAMA_ACCEPTANCE") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
#: 测试期被拦下的 .env 读取企图，形如 ["auth.py:13", "retriever.py:19"]，供守卫用例取证。
DOTENV_BLOCKED: list[str] = []


def _block_dotenv_load(*args, **kwargs):
    """记录每一次 .env 读取企图，但一个字都不写进 os.environ。"""
    frame = inspect.stack()[1]
    DOTENV_BLOCKED.append(f"{os.path.basename(frame.filename)}:{frame.lineno}")
    return False


if not _LIVE_ACCEPTANCE_REQUESTED:
    import dotenv as _dotenv_module

    _dotenv_module.load_dotenv = _block_dotenv_load

# ==================== 跟进单 R56：测试期禁止真打宿主模型端口 ====================
# 缺陷链（实测 09-17 21:35，be-r14@5984696，解释器 C:\Users\fengx\PycharmProjects\企业智脑\
# .venv\Scripts\python.exe = py3.11.7 / chromadb 1.5.9；探针插件放在仓库外，未改 app/**）：
# 干净环境（LOCAL_MODEL_NAME 与 OLLAMA_MODEL 都不设）下
#   - 验收 7 文件（test_test_isolation_guards / test_prefiltering /
#     test_classification_fail_closed / test_approve_canonical_events / test_hitl_pending /
#     test_sse_sources / test_auth）在 collection 期就有 1 次 connect 打到 127.0.0.1:11434；
#   - 10 个模型相关文件的定点集合跑出 9 次 connect（分布在 8 个用例里）。
# 链路一（本单主案，导入期）：app/rag/retrieval_pipeline.py:34 与 app/api/v1/chat.py:74 的
#   模块级 ModelHandler() -> app/common/model_handler.py:47 get_local_model_settings()
#   -> app/common/model_config.py:175 _cached_discovery -> :99 discover_chat_model
#   -> :77 _fetch_registry -> :56 urllib.request.urlopen  =>  真开 socket 打宿主 Ollama。
# 链路二（同一端口，但不经过 model_config，本单的 transport 桩覆盖不到）：
#   app/rag/retriever.py:51-65 OllamaEmbeddings._call_api 自己 urlopen；
#   app/common/monitoring.py 的 Ollama 探针同理。这条腿由下面的 socket 闸门负责。
# 为什么钉子在导入期而不是 autouse fixture：链路一发生在 collection 期，那时任何 fixture
# 都还没跑（和 R53 改 __defaults__ 是同一个时间窗）。
# 为什么不能只 raise 一次：app/common/model_capabilities.py:95-100 的 except Exception 会把
# transport 异常洗成 available=False / error_code=model_unavailable，app/rag/retriever.py:62
# 同理洗成零向量，测试自己根本看不见那次 raise。所以闸门 = sticky 模块级记录（跨 except
# 存活）+ autouse 逐用例兜底断言（文件末尾 host_model_endpoint_tripwire）；import 期的违规
# 没有任何 fixture 能接住，另由 pytest_collection_finish 记一次 session error 保证退出码非 0。
# 危害定性：打 Ollama 属并发红线。任何一条线在跑端到端计时时，另一条线跑测试就会让那些
# 数字全部作废，而且事后无法分辨是哪条线干的。

#: 出厂默认端口，见 app/common/model_config.py:16 _DEFAULT_OLLAMA_BASE_URL。
DEFAULT_MODEL_PORT = 11434
#: 模型 base_url 的环境变量：端口可能被指到 11434 以外。
MODEL_BASE_URL_ENVS = ("OLLAMA_BASE_URL", "LOCAL_MODEL_BASE_URL")
#: 只拦回环：base_url 指向远端主机时那不属于"宿主 Ollama"，不在本单范围内。
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0", "::"})
#: 哨兵值：非空就让 model_config.py:166-173 走 configured 分支，压根不调 discovery。
TEST_LOCAL_MODEL_SENTINEL = "__eb_test_disabled__"
#: 违规归属用：不属于任何用例的阶段（collection / import / 用例之间）。
_COLLECTION_PHASE = "<collection/import>"

# 哨兵：现值为空（含未设、空串、纯空格）就赋值，调用方显式给的非空值一律不动。
# 这比裸 setdefault 严一点、比强制赋值宽一点，理由三条：
#   1) 与本文件既有的 PERSISTENCE_BACKEND / PERSISTENCE_FALLBACK_PATH 钉子同一招同一位置；
#   2) 不覆盖调用方显式指定的模型名：要真模型的定点验收（tests/_live_model.py 那一类）
#      仍以 setenv 为准，强制赋值会把它们静默改掉，而且那是总控自己的计时入口；
#   3) 空值必须补：LOCAL_MODEL_NAME= 这种空赋值在 shell 里很常见，裸 setdefault 会当成
#      "已设"放过，而 app/common/model_config.py:167 的 .strip() 正好把它当未设 => 缺陷照旧。
# 更要紧的是：哨兵从来不是安全边界。存量用例会在测试体内
# monkeypatch.delenv("LOCAL_MODEL_NAME")（tests/test_deployment_guards.py:224-225），
# 导入期赋值拦得住 import 期，拦不住运行期删除，所以下面的离线 transport 与 socket
# 闸门两道都必须装。
if not (os.environ.get("LOCAL_MODEL_NAME") or "").strip():
    os.environ["LOCAL_MODEL_NAME"] = TEST_LOCAL_MODEL_SENTINEL

#: 被闸门拦下的连接尝试。sticky：app 侧的 except Exception 吞异常吞不掉这条记录。
BLOCKED_MODEL_PORT_ATTEMPTS: list[dict] = []
#: 被离线 transport 桩挡掉的发现调用（没开 socket，只作取证，不参与判红）。
OFFLINE_DISCOVERY_CALLS: list[str] = []
#: collection/import 期就已经发生的违规，由 pytest_collection_finish 填。
COLLECTION_PHASE_VIOLATIONS: list[dict] = []
#: 发现桩被换掉后由 conftest 自愈重钉的次数。存量用例会在测试模块导入期
#: importlib.reload(model_config)（tests/test_private_model_routing.py:12），重跑模块 =
#: _fetch_registry 变回出厂实现，桩必须能自愈；这一条计数就是它发生过的证据。
DISCOVERY_PIN_REINSTALLED: list[dict] = []
#: 当前正在跑的用例 nodeid，用于把违规定位到调用栈与用例。
_CURRENT_TEST = [_COLLECTION_PHASE]
#: 上一个跑完的用例 nodeid，用于把"桩被谁弄丢"归到真凶名下。
_LAST_TEST = [_COLLECTION_PHASE]


class HostModelEndpointBlocked(ConnectionRefusedError):
    """测试期对宿主模型端口的连接尝试被闸门拦下。

    刻意继承 ConnectionRefusedError：语义与"Ollama 没在跑"逐字一致，app 侧
    except OSError / except Exception 的离线降级路径照旧走，于是本单不改 app/**
    也能保证既有用例的行为不变；拦下的证据保存在 BLOCKED_MODEL_PORT_ATTEMPTS。
    """


def _model_endpoint_ports() -> frozenset:
    """宿主模型端口清单。每次判断都重算：base_url 在用例里可能被 monkeypatch 改过。

    进闸的只有两种：出厂端口 11434（跟进单点名的宿主 Ollama），以及 base_url 的
    **主机本身就是回环**时它用的那个端口。base_url 指向远端主机时，那个端口号属于
    远端服务，本地同号端口不算宿主模型端口，不能误伤。
    """
    ports = {DEFAULT_MODEL_PORT}
    for name in MODEL_BASE_URL_ENVS:
        raw = (os.getenv(name) or "").strip()
        if not raw:
            continue
        try:
            parsed = urlsplit(raw if "//" in raw else "//" + raw)
        except ValueError:
            continue
        hostname = (parsed.hostname or "").strip().strip("[]").lower()
        if hostname not in LOOPBACK_HOSTS:
            continue
        if parsed.port:
            ports.add(int(parsed.port))
    return frozenset(ports)


def _host_port(address):
    """socket 地址元组里的 (host, port)；AF_UNIX 一类取不到就返回 (None, None)。"""
    if isinstance(address, tuple) and len(address) >= 2:
        try:
            return str(address[0]), int(address[1])
        except (TypeError, ValueError):
            return None, None
    return None, None


def _targets_host_model_endpoint(address) -> bool:
    """这条地址是不是宿主模型端口。纯谓词，自己绝不开 socket。"""
    host, port = _host_port(address)
    if host is None or port not in _model_endpoint_ports():
        return False
    return host.strip().strip("[]").lower() in LOOPBACK_HOSTS


def _record_blocked_attempt(kind: str, target: str) -> int:
    """先记账再抛：记账排在 raise 前面，异常被上层吞掉也不会丢证据。"""
    BLOCKED_MODEL_PORT_ATTEMPTS.append(
        {
            "kind": kind,
            "target": target,
            "test": _CURRENT_TEST[0],
            "stack": "".join(traceback.format_stack()[-30:-1]),
        }
    )
    return len(BLOCKED_MODEL_PORT_ATTEMPTS)


def _block_model_endpoint(kind: str, target: str):
    count = _record_blocked_attempt(kind, target)
    raise HostModelEndpointBlocked(
        f"[R56] 测试期禁止连接宿主模型端口: {kind} -> {target}"
        f" (本会话第 {count} 次, 当前用例 {_CURRENT_TEST[0]})"
    )


def _install_model_endpoint_tripwire() -> None:
    """在 socket 层装硬闸。

    主钩子是 socket.socket.connect：urllib、http.client、httpx（openai SDK 用的就是它）
    最后都要落到这里，而且它是类属性，即便装的时候 http.client 早已绑定了
    _create_connection 也一样生效。另外两个钩子只是补，有些库直接调
    socket.create_connection 或 connect_ex。
    """
    if getattr(socket.socket, "_eb_r56_tripwire", False):
        return
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection

    def guarded_connect(self, address, *args, **kwargs):
        if _targets_host_model_endpoint(address):
            host, port = _host_port(address)
            _block_model_endpoint("socket.socket.connect", f"{host}:{port}")
        return original_connect(self, address, *args, **kwargs)

    def guarded_connect_ex(self, address, *args, **kwargs):
        if _targets_host_model_endpoint(address):
            host, port = _host_port(address)
            _block_model_endpoint("socket.socket.connect_ex", f"{host}:{port}")
        return original_connect_ex(self, address, *args, **kwargs)

    def guarded_create_connection(address, *args, **kwargs):
        if _targets_host_model_endpoint(address):
            host, port = _host_port(address)
            _block_model_endpoint("socket.create_connection", f"{host}:{port}")
        return original_create_connection(address, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create_connection
    socket.socket._eb_r56_tripwire = True


_install_model_endpoint_tripwire()

# 装完当场自证。这几条都是纯谓词断言，本身不会开任何 socket，也不该留下记录。
assert getattr(socket.socket, "_eb_r56_tripwire", False) is True, "R56 闸门没装上"
assert socket.socket.connect.__name__ == "guarded_connect", "socket.socket.connect 钩子没生效"
assert _targets_host_model_endpoint(("127.0.0.1", DEFAULT_MODEL_PORT)), "闸门必须拦 127.0.0.1:11434"
assert _targets_host_model_endpoint(("localhost", DEFAULT_MODEL_PORT)), "闸门必须拦 localhost:11434"
assert _targets_host_model_endpoint(("::1", DEFAULT_MODEL_PORT)), "闸门必须拦 [::1]:11434"
# 端口清单每次连接重算：临时把 base_url 指到别的本地端口，闸门必须跟着走。
_BASE_URL_BACKUP = {name: os.environ.get(name) for name in MODEL_BASE_URL_ENVS}
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11435"
assert _targets_host_model_endpoint(("127.0.0.1", 11435)), (
    "OLLAMA_BASE_URL 指到的本地端口也要进闸"
)
assert not _targets_host_model_endpoint(("10.0.0.8", 11435)), (
    "base_url 指向远端主机时，本地同号端口不算宿主"
)
for _name, _value in _BASE_URL_BACKUP.items():
    if _value is None:
        os.environ.pop(_name, None)
    else:
        os.environ[_name] = _value
del _BASE_URL_BACKUP
assert not _targets_host_model_endpoint(("127.0.0.1", 1)), "R20 的 PG 钉子 127.0.0.1:1 不能被拦"
assert not _targets_host_model_endpoint(("10.0.0.8", 11434)), "远端模型主机不属于本单"
assert not _targets_host_model_endpoint(("127.0.0.1", 6379)), "非模型端口不能被拦"
assert not _targets_host_model_endpoint("/tmp/eb.sock"), "AF_UNIX 地址不参与判断"
assert not BLOCKED_MODEL_PORT_ATTEMPTS, "纯谓词检查不该留下任何连接尝试"


def _pin_offline_model_discovery():
    """把模型发现的 transport 钉成离线桩。

    只替换 _fetch_registry，不替换 discover_chat_model：后者是存量用例注入假 transport
    的入口（tests/test_model_discovery_selection.py:46/:75/:86 与
    tests/test_compute_wiring.py:69 都带 fetch= 参数在断言发现结果），整个替掉会让那些
    用例从此什么都测不到，属于用守卫吃掉真实覆盖。_fetch_registry 是这条链上唯一真的
    会 urlopen 的函数，钉住它就等于钉住整条发现路径的出口。
    """
    import app.common.model_config as model_config

    shipped = getattr(model_config, "_fetch_registry", None)
    if not callable(shipped):
        raise RuntimeError(
            "app/common/model_config.py 里没有可调用的 _fetch_registry，R56 无处可钉。"
        )

    def offline_registry_fetch(url, *args, **kwargs):
        OFFLINE_DISCOVERY_CALLS.append(str(url))
        raise ConnectionRefusedError(
            f"[R56] 测试期模型发现已钉成离线假 transport，不会开 socket: {url}"
        )

    model_config._fetch_registry = offline_registry_fetch
    if model_config._fetch_registry is shipped:
        raise RuntimeError("离线发现桩赋值之后没有生效（生产实现换了写法？）。")
    return SimpleNamespace(module=model_config, shipped=shipped, offline=offline_registry_fetch)


MODEL_DISCOVERY_PIN = _pin_offline_model_discovery()

assert MODEL_DISCOVERY_PIN.offline is not MODEL_DISCOVERY_PIN.shipped, "离线发现桩没生效"
assert (os.environ.get("LOCAL_MODEL_NAME") or "").strip(), "LOCAL_MODEL_NAME 钉子不能是空串"
assert not OFFLINE_DISCOVERY_CALLS, "发现桩只该在被调用时记录，装桩本身不该触发"

# ==================== 跟进单 R53 / R134：测试期把 Chroma 目录钉进临时沙箱 ====================
# 实现本体搬进 tests/_chroma_sandbox.py，因为 R134 查明：pytest 只沿「命令行参数的祖先链」加载
# conftest.py，把 tests/ 之外的路径交给 pytest（例如 `pytest app/api/v1/chat.py`）根本不加载本文件，
# 而 app/api/v1/chat.py 是模块级 DocumentRetriever()——一 import 就把被跟踪的 chroma.sqlite3 就地写脏。
# 所以实现只留一份，装载点两处：仓库根 conftest.py（任何起法都会加载）与本文件。分工由
# tests/test_r134_chroma_writeback.py 的静态钉守着：仓库根只装依赖级那半（PersistentClient 改道 +
# 写回基线），app 级的默认值改写仍留给本文件——改写要 import app.rag.retriever，而那枚模块 :19 就调
# load_dotenv()，在本文件把 .env 堵住（R70）之前引 app 等于把那道闸重新放开。
from tests import _chroma_sandbox as chroma_sandbox_pins

_path_within = chroma_sandbox_pins._path_within
_pin_chroma_sandbox_default = chroma_sandbox_pins._pin_chroma_sandbox_default
_discard_chroma_sandbox = chroma_sandbox_pins._discard_chroma_sandbox
_chroma_store_snapshot = chroma_sandbox_pins._chroma_store_snapshot
_chroma_writeback_violations = chroma_sandbox_pins._chroma_writeback_violations
_format_chroma_writeback = chroma_sandbox_pins._format_chroma_writeback
_pin_chroma_persistent_client = chroma_sandbox_pins._pin_chroma_persistent_client
note_current_test = chroma_sandbox_pins.note_current_test
writeback_violations_for = chroma_sandbox_pins.writeback_violations_for
CHROMA_SANDBOX_ROOT = chroma_sandbox_pins.CHROMA_SANDBOX_ROOT
CHROMA_SANDBOX = chroma_sandbox_pins.CHROMA_SANDBOX
KEEP_TEST_SANDBOXES = chroma_sandbox_pins.KEEP_TEST_SANDBOXES

# 必须在导入期动手：默认值挂在函数对象上，等测试模块 import 完 app 再改就晚了。
chroma_sandbox_pins.install_chroma_sandbox_pins(_PERSISTENCE_SANDBOX, pin_retriever_default=True)


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
        default_index=chroma_sandbox_pins.CHROMA_DIR_DEFAULT_INDEX,
        shipped_default=chroma_sandbox_pins.CHROMA_DIR_SHIPPED_DEFAULT,
        repo_root=chroma_sandbox_pins.CHROMA_REPO_ROOT,
        marker=os.environ["ENTERPRISE_BRAIN_PYTEST_CHROMA_DIR"],
    )


@pytest.fixture
def pin_chroma_sandbox_default():
    """把改写函数本身交给测试，用来验证它「签名不对就抛」而不是静默跳过。"""
    return _pin_chroma_sandbox_default


@pytest.fixture(autouse=True)
def chroma_writeback_tripwire(request):
    """R134 判据：逐用例比对工作树快照，被写过就红，并指名是哪一枚用例先写坏的。"""
    note_current_test(request.node.nodeid)
    yield
    problems = writeback_violations_for(
        request.node.nodeid,
        already_failed=bool(getattr(request.node, "_eb_r134_call_failed", False)),
    )
    if problems:
        pytest.fail(_format_chroma_writeback(problems, request.node.nodeid), pytrace=False)


@pytest.fixture(scope="session", autouse=True)
def chroma_writeback_session_guard():
    """会话收尾再量一次：抓最后一次用例之后（teardown、后台线程）才落盘的写回。"""
    yield
    problems = chroma_sandbox_pins._chroma_writeback_violations(
        chroma_sandbox_pins.CHROMA_WRITEBACK_BASELINE
    )
    if problems:
        raise AssertionError(_format_chroma_writeback(problems, "<会话收尾>"))


@pytest.fixture
def chroma_writeback_guard():
    """把 R134 的钉子与台账交给守卫/反证用例，用例不必去 import conftest。"""
    return SimpleNamespace(
        repo_root=chroma_sandbox_pins.CHROMA_REPO_ROOT,
        store_dir=chroma_sandbox_pins.CHROMA_REPO_STORE,
        sandbox_root=CHROMA_SANDBOX_ROOT,
        baseline=chroma_sandbox_pins.CHROMA_WRITEBACK_BASELINE,
        redirects=chroma_sandbox_pins.CHROMA_SANDBOX_REDIRECTS,
        calls=chroma_sandbox_pins.CHROMA_PERSISTENT_CLIENT_CALLS,
        violations=chroma_sandbox_pins.CHROMA_WRITEBACK_VIOLATIONS,
        parameter=chroma_sandbox_pins.CHROMA_CLIENT_PARAMETER,
        shipped=chroma_sandbox_pins.CHROMA_CLIENT_SHIPPED,
        pins=chroma_sandbox_pins,
        snapshot=_chroma_store_snapshot,
        diff=chroma_sandbox_pins._chroma_writeback_violations,
        pin=_pin_chroma_persistent_client,
        within=_path_within,
    )


# ==================== R56：逐用例兜底断言与取证 ====================


def _format_blocked_attempts(attempts) -> str:
    """把拦下的尝试连调用栈一起摊开，判红信息必须能定位到是谁开的 socket。"""
    lines = [f"R56 闸门在本用例内拦下 {len(attempts)} 次对宿主模型端口的连接尝试："]
    for index, attempt in enumerate(attempts, start=1):
        lines.append(f"  ({index}) 用例 {attempt['test']}")
        lines.append(f"      {attempt['kind']} -> {attempt['target']}")
        for line in attempt["stack"].splitlines():
            lines.append(f"        {line}")
    lines.append(
        "  app 里的 except Exception 会吞掉闸门的异常，但吞不掉这条记录。"
        "修法：模型名走 LOCAL_MODEL_NAME 配置，或给该路径注入假 transport，"
        "别让测试期去碰宿主模型端口。"
    )
    return "\n".join(lines)


def _ensure_model_discovery_pin(stage: str) -> bool:
    """幂等重钉离线发现桩，返回 True 表示这一次确实需要重钉。

    为什么不 fail 在 setup 上：一个用例把桩弄丢就让后面几百个用例全线 ERROR，
    等于用守卫去毒化会话，真凶反而被埋掉（实测这样产出过 40 个 ERROR）。
    这里改成"发现丢了就钉回去 + 记一笔"，保证任何时刻都不会出现没钉的状态，
    重钉次数进 terminal summary，异常不可能被静默吃掉。
    """
    module = MODEL_DISCOVERY_PIN.module
    if getattr(module, "_fetch_registry", None) is MODEL_DISCOVERY_PIN.offline:
        return False
    module._fetch_registry = MODEL_DISCOVERY_PIN.offline
    DISCOVERY_PIN_REINSTALLED.append(
        {"stage": stage, "test": _CURRENT_TEST[0], "previous": _LAST_TEST[0]}
    )
    return True


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """每个用例开跑前先确认桩还在。collection 期的 reload 也在这里被兜住。"""
    _ensure_model_discovery_pin("setup")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """记下 call 阶段是否已经红了：红了就不再补一次 teardown 失败，免得一缺陷两份噪音。"""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        setattr(item, "_eb_r56_call_failed", True)


def pytest_collection_finish(session):
    """collection/import 期的尝试没有 fixture 能接住，这里记一次 session error。

    这正是改前基线的形态：ModelHandler() 在 import 期就 urlopen，任何 autouse fixture
    都还没跑。只 raise 不记 session 的话，违规会被 app 的 except Exception 洗成绿色通过。
    """
    pending = [
        attempt
        for attempt in BLOCKED_MODEL_PORT_ATTEMPTS
        if attempt["test"] == _COLLECTION_PHASE
    ]
    if pending:
        COLLECTION_PHASE_VIOLATIONS.extend(pending)
        session.testsfailed += 1


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """判据③的可复现证据：blocked 这条计数在每次定点复跑里都必须为 0。"""
    terminalreporter.write_sep("=", "R56 宿主模型端口闸门")
    terminalreporter.write_line(f"python      = {sys.executable}")
    terminalreporter.write_line(f"base_prefix = {sys.base_prefix}")
    chromadb_module = sys.modules.get("chromadb")
    terminalreporter.write_line(
        "chromadb    = {}".format(
            getattr(chromadb_module, "__version__", "not imported")
            if chromadb_module is not None
            else "not imported"
        )
    )
    terminalreporter.write_line(
        "LOCAL_MODEL_NAME = "
        f"{os.environ.get('LOCAL_MODEL_NAME')!r} (conftest 哨兵 "
        f"{TEST_LOCAL_MODEL_SENTINEL!r})"
    )
    terminalreporter.write_line(
        f"blocked connect attempts to host model port: {len(BLOCKED_MODEL_PORT_ATTEMPTS)}"
    )
    terminalreporter.write_line(
        f"offline discovery stub calls (no socket opened): {len(OFFLINE_DISCOVERY_CALLS)}"
    )
    terminalreporter.write_line(
        f"discovery pin re-installed by conftest: {len(DISCOVERY_PIN_REINSTALLED)}"
    )
    if COLLECTION_PHASE_VIOLATIONS:
        terminalreporter.write_line(
            f"attempts during collection/import: {len(COLLECTION_PHASE_VIOLATIONS)}"
            "  -> 会话已记 1 次 error，退出码非 0"
        )
    for attempt in BLOCKED_MODEL_PORT_ATTEMPTS[:8]:
        terminalreporter.write_line(
            f"  {attempt['kind']} {attempt['target']} <- {attempt['test']}"
        )
    if len(BLOCKED_MODEL_PORT_ATTEMPTS) > 8:
        terminalreporter.write_line(
            f"  ... 其余 {len(BLOCKED_MODEL_PORT_ATTEMPTS) - 8} 条从略"
        )
    for record in DISCOVERY_PIN_REINSTALLED[:5]:
        terminalreporter.write_line(
            f"  re-pinned at {record['stage']}: 上一个用例 {record['previous']}"
        )

    violations = chroma_sandbox_pins.CHROMA_WRITEBACK_VIOLATIONS
    calls = chroma_sandbox_pins.CHROMA_PERSISTENT_CLIENT_CALLS
    redirected = [entry for entry in calls if entry["target"] != entry["requested"]]
    terminalreporter.write_sep("=", "R134 工作树 Chroma 写回闸门")
    terminalreporter.write_line(
        f"PersistentClient 调用: {len(calls)} 次，其中落点被改道出工作树: {len(redirected)} "
        f"次（{len(chroma_sandbox_pins.CHROMA_SANDBOX_REDIRECTS)} 个原路径）"
    )
    for entry in redirected[:8]:
        terminalreporter.write_line(
            f"  {entry['requested']} -> {entry['target']} <- {entry['test']}"
        )
    if len(redirected) > 8:
        terminalreporter.write_line(f"  ... 其余 {len(redirected) - 8} 条从略")
    terminalreporter.write_line(
        f"工作树 chroma_db 写回告警用例: {len(violations)} 枚"
        f"（会话基线 {len(chroma_sandbox_pins.CHROMA_WRITEBACK_BASELINE)} 个文件）"
    )
    for record in violations[:3]:
        terminalreporter.write_line(f"  {record['test']}: {record['problems'][:1]}")


@pytest.fixture(autouse=True)
def host_model_endpoint_tripwire(request):
    """R56 判据：sticky 记录 + 逐用例兜底断言。

    闸门的 raise 会被 app/common/model_capabilities.py:95-100 那样的 except Exception
    吞掉，所以每个用例收尾还要按 sticky 记录再判一次。这样"只 raise 一次"的写法
    不可能蒙混过关，而且新用例违规会在它自己名下变红，不需要跑全量去事后数连接。
    """
    _ensure_model_discovery_pin("fixture")
    _CURRENT_TEST[0] = request.node.nodeid
    _LAST_TEST[0] = request.node.nodeid
    mark = len(BLOCKED_MODEL_PORT_ATTEMPTS)
    # 发现缓存跨用例复用会把上一条线的结果带到这一条线，钉成每条用例自己算一次。
    MODEL_DISCOVERY_PIN.module.reset_model_discovery_cache()
    yield
    new_attempts = BLOCKED_MODEL_PORT_ATTEMPTS[mark:]
    _CURRENT_TEST[0] = _COLLECTION_PHASE
    MODEL_DISCOVERY_PIN.module.reset_model_discovery_cache()
    # 收尾再确认一次桩：用例内部 reload / 直接赋值都在这里被纠回来。
    _ensure_model_discovery_pin("teardown")
    if new_attempts and not getattr(request.node, "_eb_r56_call_failed", False):
        pytest.fail(_format_blocked_attempts(new_attempts), pytrace=False)


@pytest.fixture
def offline_ollama_embeddings(monkeypatch):
    """把 OllamaEmbeddings 的 HTTP 调用钉成离线兜底，一次 socket 都不开。

    宿主端口上有第二条腿不经过 model_config，本单的发现桩覆盖不到：
    app/rag/retriever.py:51-65 的 OllamaEmbeddings._call_api 自己
    urlopen(OLLAMA_BASE + "/api/embeddings")，异常被 :62 吞成零向量外加 30s cooldown；
    app/memory/long_term.py:129-139 构造 OllamaEmbeddings() 走的就是同一条腿。
    本 fixture 保留的正是那条兜底的结果（_fallback_embedding 就是它），所以测试输出与
    "宿主 Ollama 没在跑"逐字一致，而且从此与开发机上 Ollama 开没开无关；app/** 一个字
    没改，改的是测试侧的注入点。
    """
    from app.rag.retriever import OllamaEmbeddings

    monkeypatch.setattr(
        OllamaEmbeddings,
        "_call_api",
        lambda self, text: self._fallback_embedding(),
    )
    return OllamaEmbeddings


@pytest.fixture
def dotenv_guard():
    """把 R70 的桩与账本交给守卫用例，用例不必去 import conftest。"""
    return SimpleNamespace(
        stub=_block_dotenv_load,
        blocked=DOTENV_BLOCKED,
        live=_LIVE_ACCEPTANCE_REQUESTED,
        flag="EB_OLLAMA_ACCEPTANCE",
    )


@pytest.fixture
def model_endpoint_guard():
    """把 R56 的钉子与计数器交给反证用例，用例不必去 import conftest。"""
    return SimpleNamespace(
        host="127.0.0.1",
        port=DEFAULT_MODEL_PORT,
        sentinel=TEST_LOCAL_MODEL_SENTINEL,
        env_name="LOCAL_MODEL_NAME",
        blocked_attempts=BLOCKED_MODEL_PORT_ATTEMPTS,
        blocked_count=lambda: len(BLOCKED_MODEL_PORT_ATTEMPTS),
        offline_calls=OFFLINE_DISCOVERY_CALLS,
        reinstalled=DISCOVERY_PIN_REINSTALLED,
        targets=_targets_host_model_endpoint,
        ports=_model_endpoint_ports,
        tripwire_error=HostModelEndpointBlocked,
        shipped_registry_fetch=MODEL_DISCOVERY_PIN.shipped,
        offline_registry_fetch=MODEL_DISCOVERY_PIN.offline,
        model_config=MODEL_DISCOVERY_PIN.module,
    )
