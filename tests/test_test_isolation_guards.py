"""跟进单 R53 的守卫测试：pytest 期间 Chroma 只允许落在临时沙箱里。

生产侧 app/rag/retriever.py 的 DocumentRetriever.__init__ 默认 chroma_dir="./chroma_db"
是相对路径，而 pytest 的 cwd 就是仓库根，所以无参构造会把向量库写进工作树里被 git 跟踪的
./chroma_db。tests/conftest.py 在导入期把这份默认值钉进临时目录，本文件钉住这个事实。

读这些测试时要注意一条写法上的硬要求：凡是可能真的去构造 DocumentRetriever 的测试，都必须
先过 pinned_chroma_dir 这道门。一旦 conftest 的改写被删掉或失效，门会当场 fail，绝不允许带着
"./chroma_db" 往下走到实例化——否则守卫测试自己就成了污染源，判据②立刻失守。
"""
import os

import pytest

from app.rag.retriever import DocumentRetriever

# app/rag/retriever.py:89 的出厂默认值，也就是 R53 要拦的那个相对路径。
SHIPPED_RELATIVE_DEFAULT = "./chroma_db"


def _path_within(parent: str, child: str) -> bool:
    """child 是否位于 parent 之内（含相等），两边都按绝对路径规范化后比较。"""
    parent = os.path.normcase(os.path.abspath(parent))
    child = os.path.normcase(os.path.abspath(child))
    return child == parent or child.startswith(parent + os.sep)


def _working_tree_chroma_snapshot(repo_root: str):
    """工作树 ./chroma_db 的只读快照：文件数、总字节、最新修改时间。"""
    target = os.path.join(repo_root, "chroma_db")
    if not os.path.isdir(target):
        return None
    paths = [
        os.path.join(root, name)
        for root, _dirs, names in os.walk(target)
        for name in names
    ]
    stats = [(os.path.getmtime(path), os.path.getsize(path)) for path in paths]
    return (
        len(stats),
        sum(size for _mtime, size in stats),
        max((mtime for mtime, _size in stats), default=0.0),
    )


@pytest.fixture
def pinned_chroma_dir(chroma_sandbox) -> str:
    """确认 chroma_dir 默认值真的被钉进沙箱；没钉住就当场失败，且在任何构造之前。"""
    default = DocumentRetriever.__init__.__defaults__[chroma_sandbox.default_index]
    assert isinstance(default, str), f"chroma_dir 的默认值不再是字符串，而是 {default!r}"
    assert default != chroma_sandbox.shipped_default, (
        "chroma_dir 的默认值又变回出厂的相对路径了：conftest 的导入期改写没有生效，"
        "这一次 pytest 会直接写工作树的 ./chroma_db（R53 要拦的就是它）。"
    )
    assert os.path.isabs(default), f"钉住之后的 chroma_dir 默认值必须是绝对路径，实际 {default!r}"
    assert default == chroma_sandbox.path, (
        f"chroma_dir 默认值 {default!r} 不是 conftest 声明的沙箱 {chroma_sandbox.path!r}"
    )
    assert default == chroma_sandbox.marker, (
        "交叉标记 ENTERPRISE_BRAIN_PYTEST_CHROMA_DIR 与实际默认值不一致："
        "改写很可能被 except 静默吞掉了。"
    )
    assert _path_within(chroma_sandbox.root, default), "钉住的路径不在沙箱根目录之下"
    assert not _path_within(chroma_sandbox.repo_root, default), (
        f"沙箱路径 {default!r} 落在工作树 {chroma_sandbox.repo_root!r} 里，等于没隔离"
    )
    return default


def test_shipped_default_is_the_relative_working_tree_path(chroma_sandbox):
    """前提校验：生产代码里那个默认值仍然是相对路径，R53 才有存在的必要。"""
    assert chroma_sandbox.shipped_default == SHIPPED_RELATIVE_DEFAULT
    assert not os.path.isabs(chroma_sandbox.shipped_default)
    assert _path_within(chroma_sandbox.repo_root, chroma_sandbox.shipped_default), (
        "相对默认值应当解析到工作树内，否则本单的前提已经变了"
    )


def test_default_is_pinned_before_any_test_imports_app(chroma_sandbox, pinned_chroma_dir):
    """改写发生在 conftest 导入期：默认值、标记环境变量、实例三者必须一致。"""
    assert pinned_chroma_dir == chroma_sandbox.path
    assert os.environ["ENTERPRISE_BRAIN_PYTEST_CHROMA_DIR"] == chroma_sandbox.path
    assert os.path.isdir(chroma_sandbox.root), "沙箱根目录应当由 conftest 在导入期建好"


def test_no_keyword_only_default_can_bypass_the_pin(pinned_chroma_dir):
    """keyword-only 默认值走 __kwdefaults__，钉 __defaults__ 拦不住它——必须为空。"""
    kwdefaults = DocumentRetriever.__init__.__kwdefaults__ or {}
    assert "chroma_dir" not in kwdefaults, (
        "chroma_dir 变成了带默认值的 keyword-only 参数，__defaults__ 改写会失效"
    )


def test_constructing_a_retriever_writes_only_into_the_sandbox(
    chroma_sandbox, pinned_chroma_dir
):
    """真走一次无参构造：目录、文件都只可能出现在沙箱里，工作树 ./chroma_db 分毫不动。"""
    before = _working_tree_chroma_snapshot(chroma_sandbox.repo_root)

    retriever = DocumentRetriever()

    assert retriever.chroma_dir == pinned_chroma_dir
    assert os.path.isabs(retriever.chroma_dir)
    assert _path_within(chroma_sandbox.root, retriever.chroma_dir)
    assert os.path.isdir(retriever.chroma_dir), "PersistentClient 应当在沙箱里建好了目录"
    assert os.listdir(retriever.chroma_dir), "沙箱里应当留下 chroma 生成的文件"
    if before is not None:
        assert _working_tree_chroma_snapshot(chroma_sandbox.repo_root) == before, (
            "工作树的 ./chroma_db 被写动了，判据②会失守"
        )


def test_pinning_fails_loudly_when_the_signature_moves(
    pin_chroma_sandbox_default, chroma_sandbox, tmp_path
):
    """签名对不上时必须抛错，而不是静默跳过——静默跳过等于本单白做。"""

    class RenamedParameter:
        def __init__(self, vector_dir: str = SHIPPED_RELATIVE_DEFAULT):
            self.vector_dir = vector_dir

    class KeywordOnlyParameter:
        def __init__(self, *, chroma_dir: str = SHIPPED_RELATIVE_DEFAULT):
            self.chroma_dir = chroma_dir

    class SlotWrapperInit:
        pass

    target = str(tmp_path / "chroma_sandbox")
    for klass in (RenamedParameter, KeywordOnlyParameter, SlotWrapperInit):
        with pytest.raises(RuntimeError):
            pin_chroma_sandbox_default(target, klass)

    class ExtraTrailingDefault:
        def __init__(self, chroma_dir: str = SHIPPED_RELATIVE_DEFAULT, tenant: str = "default"):
            self.chroma_dir = chroma_dir
            self.tenant = tenant

    class LeadingRequiredArgument:
        def __init__(self, name: str, chroma_dir: str = SHIPPED_RELATIVE_DEFAULT):
            self.name = name
            self.chroma_dir = chroma_dir

    index, original = pin_chroma_sandbox_default(target, ExtraTrailingDefault)
    assert (index, original) == (0, SHIPPED_RELATIVE_DEFAULT)
    assert ExtraTrailingDefault.__init__.__defaults__ == (
        os.path.abspath(target),
        "default",
    ), "只有 chroma_dir 该被改写，后面的默认值必须原样保留"

    index, original = pin_chroma_sandbox_default(target, LeadingRequiredArgument)
    assert (index, original) == (0, SHIPPED_RELATIVE_DEFAULT)
    assert LeadingRequiredArgument.__init__.__defaults__ == (os.path.abspath(target),)

    assert DocumentRetriever.__init__.__defaults__[
        chroma_sandbox.default_index
    ] == chroma_sandbox.path, "拿假类做的实验不允许动到真检索器的钉住结果"
