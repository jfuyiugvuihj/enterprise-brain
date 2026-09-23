"""Chroma 测试沙箱的钉子本体：跟进单 R53（默认值改写）与 R134（PersistentClient 改道）。

为什么单独一枚文件、而不是留在 tests/conftest.py 里：R53 的钉子过去只在 tests/conftest.py 的
导入期动手，而「把 tests/ 之外的路径交给 pytest」（例如 `pytest app/api/v1/chat.py`）根本不加载
那个文件 —— 而 app/api/v1/chat.py:83 是模块级的 DocumentRetriever()。本机实测一次
`python -m pytest --collect-only app/api/v1/chat.py` 就把被跟踪的 chroma_db/chroma.sqlite3
就地写脏：尺寸 6 262 784 一字不变，sha256 由 0b8cb318a0e0ba18 变成 c43c3e8a950a64b1。
所以实现只留这一份，装载点两处：仓库根的 conftest.py（任何起法都会加载它）与 tests/conftest.py；
install_chroma_sandbox_pins() 自带幂等，重复装载不叠第二层壳、不开第二个沙箱。
两处的装载范围不同：仓库根只装依赖级改道，app 级的默认值改写仍留给 tests/conftest.py，
因为后者要先把 .env 堵住（R70）才轮得上引 app。

归因指纹（09-21 实测，工作树 chroma_db 处于 HEAD 态、chroma.sqlite3 6 262 784 B）：把被跟踪
的库「就地打开一次再关」，三条路——裸 import 后构造 DocumentRetriever()、
`pytest --noconftest app/api/v1/chat.py`、直接 PersistentClient(path=<仓库>/chroma_db)——
落盘内容逐位相同，sha256 前 16 位恒为 c43c3e8a950a64b1；同一进程里就地开两次则是
25ec5089604ae037；而一次全量跑（把本文件的改道关掉、只剩 R53 的默认值改写）是 0 次改动。
所以「脏文件的指纹」能把两件事分开：某枚没装闸门的进程开了一回库，与套件把库写坏了。
be-r119 那次（同尺寸、c43c3e8a…）属于前者；判据① 与那枚 git 态用例守的是后者。


本文件不 import conftest、也不注册 fixture：钉子是给「任何 pytest 进程」用的，
fixture 那层皮留在 tests/conftest.py。写回快照比的是 (size, mtime_ns)：一次同尺寸的回写
只有 mtime 看得见；而本机实测 NTFS 的 mtime 粒度粗到同一 tick 内两次写入差值为 0，
所以「同 tick 同尺寸回写」是这枚守卫的公开下限 —— 验收判据因此还要再读一次 git diff。
"""
import atexit
import hashlib
import inspect
import os
import shutil
import tempfile


# ==================== 模块级状态 ====================
#: 「现在在跑哪枚用例」的水位，由 tests/conftest.py 的逐用例 fixture 喂；改道台账靠它指名到人。
_CURRENT_CHROMA_TEST = ["<collection/import>"]
#: 写回账本（可变对象，conftest 与守卫用例直接读这里）；改道台账在下面的 R134 段里声明。
CHROMA_WRITEBACK_VIOLATIONS: list[dict] = []
_CHROMA_REPORTED_FILES: set[str] = set()
#: 这三枚 + 基线是「钉完才知道」的值，由 install_chroma_sandbox_pins() 填。
CHROMA_DIR_DEFAULT_INDEX = None
CHROMA_DIR_SHIPPED_DEFAULT = None
CHROMA_CLIENT_PARAMETER = None
CHROMA_CLIENT_SHIPPED = None
CHROMA_WRITEBACK_BASELINE: dict = {}
PINS_INSTALLED = False


def note_current_test(nodeid: str) -> None:
    """记一笔当前用例，让改道台账能指名到人。"""
    _CURRENT_CHROMA_TEST[0] = nodeid


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


# ==================== 跟进单 R134：测试期任何指向工作树 Chroma 的入口一律改道 ====================
# R53 只改写了 DocumentRetriever 的 chroma_dir 默认值，绕得开它的四条入口一条都没被管住：
#   1) scripts/rebuild_index.py:292 open_census_store() 的落点常量 ROOT/"chroma_db" ——
#      --status 走的就是它（scripts/rebuild_index.py:1183），而它刻意不用 DocumentRetriever；
#   2) 同一行前面的 CHROMA_DIR 环境变量分支；
#   3) scripts/compare_vector_recall.py:76 --chroma-dir 的默认值 "./chroma_db"（相对 cwd，
#      而 pytest 的 cwd 就是仓库根），:185 再 chromadb.PersistentClient(path=...)；
#   4) 任何把工作树内绝对路径当实参传进来的调用。
# 实测（2026-09-21 本树 @9cdbef2，chromadb 1.5.9）：不带任何参数调一次 open_census_store() ——
# 纯只读普查、不碰 embedder —— 就把被跟踪的 chroma_db/chroma.sqlite3 原地改写：字节数
# 6 262 784 不变，sha256 由 0b8cb318a0e0ba18 变成 c43c3e8a950a64b1，git status 当场报 M。
# 所以「它只是读一下」不是豁免理由：Chroma 一开目录就往 sqlite 落 WAL 并回写，
# 被跟踪的二进制立刻脏掉，而任何人顺手一次 git add -A 就是上百 MB 入库。
# 修法沿用 R53 那一招：在 conftest 导入期动手，app/** 与 scripts/** 一个字都不改，钉在唯一的
# 收口上。全仓五处 PersistentClient 调用（app/rag/retriever.py:875、scripts/rebuild_index.py:302、
# scripts/compare_vector_recall.py:186、scripts/diag_r162_chroma_zero_rows.py:498（只开仓外副本）、
# tests/test_r125_status_vector_census.py:384）写的都是
# chromadb.PersistentClient(...) —— 属性查找发生在调用期，所以包这一层同时盖住上面四条路。
# 工作树之外的目录（tmp_path 等）原样放行：本单只关心仓库里那批被跟踪的文件。

CHROMA_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CHROMA_REPO_STORE = os.path.join(CHROMA_REPO_ROOT, "chroma_db")
#: 原路径 -> 沙箱落点，以及逐次调用台账（谁在哪个用例里想把 Chroma 开进工作树）。
CHROMA_SANDBOX_REDIRECTS: dict[str, str] = {}
CHROMA_PERSISTENT_CLIENT_CALLS: list[dict] = []


def _chroma_store_snapshot(target_dir: str = CHROMA_REPO_STORE) -> dict:
    """递归快照：相对路径 -> (字节数, mtime_ns)。只 stat，不读内容、不调 git、不联网。

    mtime_ns 是这里的承重项：上面那次 census 实测「尺寸一字不变而内容被回写」，
    只比字节数的快照会漏掉它。
    """
    if not os.path.isdir(target_dir):
        return {}
    snapshot = {}
    for root, _dirs, names in os.walk(target_dir):
        for name in names:
            path = os.path.join(root, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue  # 另一个进程正在换文件：下一轮快照会看到它
            snapshot[os.path.relpath(path, target_dir).replace(os.sep, "/")] = (
                stat.st_size,
                stat.st_mtime_ns,
            )
    return snapshot


def _chroma_writeback_violations(baseline: dict, current: dict | None = None,
                                 target_dir: str = CHROMA_REPO_STORE) -> list[str]:
    """两份快照比成人话：谁新建、谁被删、谁被动过。空列表 == 这批文件没被写过。"""
    observed = _chroma_store_snapshot(target_dir) if current is None else current
    problems = []
    for rel in sorted(set(baseline) | set(observed)):
        before, after = baseline.get(rel), observed.get(rel)
        if before is None:
            problems.append(f"{rel}: 本次会话新建，{after[0]} B")
        elif after is None:
            problems.append(f"{rel}: 本次会话被删除，原 {before[0]} B")
        elif before != after:
            problems.append(
                f"{rel}: 尺寸 {before[0]} -> {after[0]} B，mtime_ns {before[1]} -> {after[1]}"
            )
    return problems


def _chroma_redirect_target(absolute: str, settings=None) -> str:
    """工作树内某个 Chroma 目录在沙箱里的落点；同一（原路径, settings）恒映射同一处。

    恒映射不是讲究，是 Chroma 自己的规矩：一个目录只允许一个写者、一套 settings，
    映射飘忽会把同一个测试的两步拆到两个库里，做出一个假失败。
    settings 也进哈希，是因为改道会把两条本来互不相干的仓库路径并到同一个落点：
    scripts/rebuild_index.py:302 带 Settings(anonymized_telemetry=False)，而
    scripts/compare_vector_recall.py:185 什么也不带 —— 实测评测两侧同开会撞出
    ValueError("An instance of Chroma already exists ... with different settings")，
    那是改道自己造出来的假失败，不是被测代码的问题。
    """
    relative = os.path.relpath(absolute, CHROMA_REPO_ROOT).replace(os.sep, "/")
    slug = relative.replace("/", "+").replace(":", "_").strip() or "store"
    fingerprint = f"{relative}\x00{settings!r}".encode("utf-8")
    digest = hashlib.sha1(fingerprint).hexdigest()[:10]
    return os.path.join(CHROMA_SANDBOX_ROOT, "redirected", f"{slug}-{digest}")


def _chroma_path_parameter(client_factory) -> str:
    """收口函数第一个参数的名字；对不上就抛，绝不静默放行（R53 同一条纪律）。"""
    parameters = [
        parameter
        for parameter in inspect.signature(client_factory).parameters.values()
        if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]
    if not parameters:
        raise RuntimeError(
            "chromadb.PersistentClient 一个位置参数都没有，R134 无法确认目录实参的位置。"
        )
    name = parameters[0].name
    if name not in {"path", "persist_directory"}:
        raise RuntimeError(
            f"chromadb.PersistentClient 的第一个参数是 {name!r}，不像一个目录收口；"
            "R134 拒绝猜落点。生产/依赖换了写法就改钉新的收口，而不是放过它。"
        )
    return name


def _pin_chroma_persistent_client(sandbox_root: str, repo_root: str, module=None):
    """把解析到工作树之内的 PersistentClient 目录实参改道进沙箱。

    拿不到收口就抛 RuntimeError：静默跳过等于本单白做 —— 每次 pytest 又会去写被跟踪的
    ./chroma_db。返回 (收口参数名, 被包掉的原始工厂)，守卫用例靠它核对钉子本身。
    """
    if module is None:
        import chromadb

        module = chromadb
    original = getattr(module, "PersistentClient", None)
    if not callable(original):
        raise RuntimeError(
            f"{getattr(module, '__name__', module)!r} 上的 PersistentClient 不可调用"
            f"（实际 {original!r}）：R134 无处可钉，不许放过工作树里的向量库。"
        )
    if getattr(original, "_enterprise_brain_chroma_redirect", False):
        # 幂等：同一进程里重复安装不许叠第二层壳，参数名从壳上取回。
        return getattr(original, "_enterprise_brain_chroma_parameter", "path"), original
    parameter = _chroma_path_parameter(original)

    def guarded(*args, **kwargs):
        requested = args[0] if args else kwargs.get(parameter)
        resolved = None
        if requested is not None:
            try:
                resolved = os.path.abspath(str(requested))
            except (TypeError, ValueError):
                resolved = None
        if resolved is not None and _path_within(repo_root, resolved):
            settings_value = (
                kwargs["settings"] if "settings" in kwargs
                else (args[1] if len(args) > 1 else None)
            )
            target = _chroma_redirect_target(resolved, settings_value)
            CHROMA_SANDBOX_REDIRECTS[resolved] = target
            CHROMA_PERSISTENT_CLIENT_CALLS.append(
                {"test": _CURRENT_CHROMA_TEST[0], "requested": resolved,
                 "target": target, "redirected": True}
            )
            if args:
                return original(target, *args[1:], **kwargs)
            kwargs[parameter] = target
            return original(**kwargs)
        CHROMA_PERSISTENT_CLIENT_CALLS.append(
            {"test": _CURRENT_CHROMA_TEST[0], "requested": resolved, "target": None,
             "redirected": False}
        )
        return original(*args, **kwargs)

    guarded.__doc__ = original.__doc__
    guarded._enterprise_brain_chroma_parameter = parameter
    guarded.__wrapped__ = original
    guarded._enterprise_brain_chroma_redirect = True
    module.PersistentClient = guarded
    return parameter, original


def _format_chroma_writeback(problems: list[str], nodeid: str) -> str:
    """判红信息必须指名是哪一枚文件、哪一枚用例，并说清下一步往哪查。"""
    lines = [
        "R134 闸门：本次 pytest 会话写动了工作树里被跟踪的 ./chroma_db"
        f"（首次指名用例 {nodeid}）。"
    ]
    lines.extend(f"  - {problem}" for problem in problems)
    lines.append(
        "  被跟踪的向量库一旦被写脏，任何人顺手一次 git add -A 就是上百 MB 二进制入库。"
    )
    lines.append(
        "  修法：测试里的 Chroma 目录一律走 tmp_path 或 CHROMA_SANDBOX；新出现的入口"
        "（默认值、显式实参、脚本常量、CHROMA_DIR）必须补进 conftest 的"
        " _pin_chroma_persistent_client 收口。"
    )
    lines.append(
        "  取证：CHROMA_SANDBOX_REDIRECTS 与 CHROMA_PERSISTENT_CLIENT_CALLS 记下了"
        "每一次改道的原路径与用例名。"
    )
    return "\n".join(lines)


def writeback_violations_for(nodeid: str, already_failed: bool = False) -> list[str]:
    """量一次工作树快照并记账；该报的才返回，没问题返回空表。

    同一批脏文件只报一次：一次写回之后每条用例都会「看见」它，逐条再红只是噪音；
    脏项集合变大（又写脏了别的文件）就补报一次。用例自己已经红了就不再补一份噪音。
    """
    problems = _chroma_writeback_violations(CHROMA_WRITEBACK_BASELINE)
    if not problems:
        return []
    names = {problem.split(":", 1)[0] for problem in problems}
    CHROMA_WRITEBACK_VIOLATIONS.append({"test": nodeid, "problems": problems})
    if already_failed or names <= _CHROMA_REPORTED_FILES:
        return []
    _CHROMA_REPORTED_FILES.update(names)
    return problems


def install_chroma_sandbox_pins(
    persistence_sandbox: str | None = None, pin_retriever_default: bool = True
) -> None:
    """装上 R53 的默认值改写与 R134 的 PersistentClient 改道：必须在导入期调用。

    pin_retriever_default=False 是给仓库根那一侧用的：改写 chroma_dir 的默认值要
    import app.rag.retriever，而那枚模块在 :19 就调 load_dotenv()。仓库根的 conftest.py
    比 tests/conftest.py 先加载，在那儿引 app 等于把 R70「宿主的 .env 一个字都不许
    进测试进程」重新放开（tests/conftest.py:66-73 把这条链路写死在注释里）。所以仓库根
    只装依赖级的那半（PersistentClient 改道 + 写回基线），app 级的那半仍留给
    tests/conftest.py；这一分工由 tests/test_r134_chroma_writeback.py 的静态钉守着。

    拿不到钉子就抛 RuntimeError —— 这两枚单子的同一条纪律：静默跳过等于白做。
    persistence_sandbox 只有 tests/conftest.py 那一侧传得进来（仓库根没有这个概念），
    幂等重入时这条交叉断言照样执行，不许第二次装载把它吞掉。
    """
    global PINS_INSTALLED
    global CHROMA_DIR_DEFAULT_INDEX, CHROMA_DIR_SHIPPED_DEFAULT
    global CHROMA_CLIENT_PARAMETER, CHROMA_CLIENT_SHIPPED, CHROMA_WRITEBACK_BASELINE

    #: 幂等重入也要把这两条交叉检查走完：第二枚装载点（tests/conftest.py）传进来的
    #: persistence_sandbox 是仓库根那一侧拿不到的信息，不许因为「已经钉过了」就吞掉。
    if pin_retriever_default and CHROMA_DIR_DEFAULT_INDEX is None:
        CHROMA_DIR_DEFAULT_INDEX, CHROMA_DIR_SHIPPED_DEFAULT = _pin_chroma_sandbox_default(
            CHROMA_SANDBOX
        )
    assert os.path.isabs(CHROMA_SANDBOX), "the Chroma sandbox must be an absolute path"
    assert CHROMA_DIR_DEFAULT_INDEX is None or isinstance(CHROMA_DIR_SHIPPED_DEFAULT, str), (
        "chroma_dir 的出厂默认值必须是路径字符串"
    )
    if persistence_sandbox is not None:
        assert CHROMA_SANDBOX_ROOT != persistence_sandbox, (
            "Chroma 沙箱要与持久化沙箱分开，便于分别取证"
        )
    # 交叉标记：守卫测试靠它确认改写真的发生了，而不是在 except 分支里被静默跳过。
    os.environ["ENTERPRISE_BRAIN_PYTEST_CHROMA_DIR"] = CHROMA_SANDBOX
    if PINS_INSTALLED:
        return  # 幂等：不叠第二层壳、不再开临时沙箱、也不重复登记 atexit
    # --collect-only 这类调用不会走到 fixture 拆除，沙箱目录就交给 atexit 收尾。
    atexit.register(_discard_chroma_sandbox)

    CHROMA_CLIENT_PARAMETER, CHROMA_CLIENT_SHIPPED = _pin_chroma_persistent_client(
        CHROMA_SANDBOX_ROOT, CHROMA_REPO_ROOT
    )
    assert CHROMA_CLIENT_PARAMETER in {"path", "persist_directory"}, "收口参数名必须钉准"
    assert not getattr(CHROMA_CLIENT_SHIPPED, "_enterprise_brain_chroma_redirect", False), (
        "台账里存的必须是收口本体，不是它自己包的壳，否则反证用例证不到东西。"
    )
    # 再往上看一层：装的壳真的挂在模块属性上才算数。后面若有人重新 import 并覆盖这个
    # 属性，这一行会当场把会话钉死，而不是让工作树的 chroma_db 悄悄脏掉。
    import chromadb

    assert getattr(chromadb.PersistentClient, "_enterprise_brain_chroma_redirect", False) is True, (
        "R134 的改道壳没有挂在 chromadb.PersistentClient 上：钉子被后面的导入洗掉了。"
    )

    #: 会话基线在任何用例开跑之前量一次；之后只比「有没有被动过」，不比「脏不脏」——
    #: 接班时工作树本来就脏（主树此刻六枚全脏）也不会误报，那种脏进的是基线。
    CHROMA_WRITEBACK_BASELINE = _chroma_store_snapshot()
    PINS_INSTALLED = True
