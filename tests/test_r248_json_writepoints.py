"""R248 J-3 —— JSON 写点归零：那枚 sidecar 只剩"读一次"这一种用法。

判据是计数而不是印象：全仓 ``app/**`` 与 ``deploy/**`` 里，凡提到 ``artifact-metadata``
的文件，写形状（``open(..., "w"/"a")``、``os.fdopen``、``write_text``、``write_bytes``、
``json.dump(``、``os.replace``）的枚数必须为 **0**。读形状（``read_text``、``json.loads``）
允许存在——一次性导入本来就靠它。

三枚钉各挡一种糊法：

* ``test_the_sidecar_write_count_is_zero`` 按行从严：一枚提到 sidecar 的文件里出现写原语就
  算数，哪怕那一行看着像为别的东西写的。宁可假红，也不给"换个变量名躲过计数"留门。
* ``test_the_module_has_no_write_primitive_at_all`` 走 AST：把 ``import tempfile``、
  ``path.open("wb")`` 这类躲过文本匹配的形状一起抓；``path.open("rb")`` 这种读放行。
* ``test_the_lifecycle_trips_no_writer`` 是真跑一遍：把写原语换成只咬本次 tmp 的地雷，
  导入 + 登记 + get + list + 软删全程不许响，sidecar 字节与目录清单一枚不许变。
"""
import ast
import json
import os
import pathlib
import re
import tempfile
from pathlib import Path

from app.storage import artifacts as artifact_module
from app.storage.artifacts import ArtifactRegistry

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "app" / "storage" / "artifacts.py"
SCAN_ROOTS = ("app", "deploy")
SOURCE_SUFFIXES = frozenset({".py", ".sh", ".ps1", ".psm1", ".pyw"})
SIDECAR_TOKEN = "artifact-metadata"

WRITE_PATTERNS = (
    ("write_text", re.compile(r"\.write_text\s*\(")),
    ("write_bytes", re.compile(r"\.write_bytes\s*\(")),
    ("json.dump", re.compile(r"\bjson\.dump\s*\(")),
    ("open-write-mode", re.compile(r"\bopen\s*\([^)]*[\"'](w|a|x)[+bt]*[\"']")),
    ("fdopen-write-mode", re.compile(r"\bfdopen\s*\([^)]*[\"'](w|a|x)[+bt]*[\"']")),
    ("os.replace", re.compile(r"\bos\.replace\s*\(")),
    ("touch", re.compile(r"\.touch\s*\(")),
)

#: 模块级写原语（AST 形状）。认的是整个点号路径，所以 ``str.replace("Z", "+00:00")`` 不算
#: ``os.replace``；反过来 ``tempfile.mkstemp`` 这种"先建临时文件再换上去"的写法一枚都藏不住。
FORBIDDEN_DOTTED = {
    "os.replace",
    "os.rename",
    "os.unlink",
    "os.remove",
    "os.fdopen",
    "os.makedirs",
    "tempfile.mkstemp",
    "tempfile.NamedTemporaryFile",
    "tempfile.TemporaryFile",
    "shutil.move",
    "shutil.copyfile",
    "shutil.copy2",
    "json.dump",
}
FORBIDDEN_METHODS = {"write_text", "write_bytes", "touch", "truncate"}
FORBIDDEN_IMPORTS = {"tempfile", "shutil"}

#: 只认 "w"/"wb"/"r+"/"x+" 这一类模式串本身，所以 ``path.open("wb")`` 与 ``open(fd, "w")``
#: 两种写法都跑不掉；文件名、URL、``"rb"`` 一律全不匹配。
WRITE_MODE = re.compile(r"^(?:[wax][bt]?\+?|r\+[bt]?|\+r?)$")


def _sidecar_write_hits():
    """提到 sidecar 的源文件里，每一处写形状：``["app/...py:120 json.dump: ...", ...]``。"""
    hits = []
    for root in SCAN_ROOTS:
        directory = REPO / root
        assert directory.is_dir(), f"{root}/ 不在了，这枚计数钉的靶子变了"
        for path in sorted(item for item in directory.rglob("*") if item.is_file()):
            if path.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if SIDECAR_TOKEN not in text:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for name, pattern in WRITE_PATTERNS:
                    if pattern.search(line):
                        hits.append(
                            f"{path.relative_to(REPO).as_posix()}:{number} {name}: {stripped}"
                        )
    return hits


def _dotted(node):
    """``ast.Call.func`` 的点号路径；认不出宿主时只交回最后一段属性名。"""
    parts = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _write_primitives_in_module():
    """AST 级：``artifacts.py`` 里所有"会写/会毁文件"的调用形状与导入。"""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if str(alias.name or "").split(".")[0] in FORBIDDEN_IMPORTS:
                    found.append(f"line {node.lineno}: import {alias.name}")
            continue
        if not isinstance(node, ast.Call):
            continue
        dotted = _dotted(node.func)
        last = dotted.rsplit(".", 1)[-1]
        if dotted in FORBIDDEN_DOTTED or last in FORBIDDEN_METHODS:
            found.append(f"line {node.lineno}: {dotted}()")
        if last in {"open", "fdopen"}:
            candidates = [argument for argument in node.args if isinstance(argument, ast.Constant)]
            candidates += [
                keyword.value
                for keyword in node.keywords
                if keyword.arg in {"mode", "flags"} and isinstance(keyword.value, ast.Constant)
            ]
            for candidate in candidates:
                value = candidate.value
                if isinstance(value, str) and WRITE_MODE.match(value):
                    found.append(f"line {node.lineno}: {dotted}(mode={value!r})")
    return found


def _pathlib_owner(method):
    """``write_text`` 挂在 ``Path`` 还是 ``PurePath`` 上，跟着解释器版本走。"""
    for cls in (pathlib.Path, pathlib.PurePath):
        if method in vars(cls):
            return cls
    raise AssertionError(f"pathlib.{method} 找不到宿主类，这枚地雷就白埋了")


def _install_write_tripwires(monkeypatch, tmp_path):
    """把写原语换成只咬"落在本次 tmp 之下 / 提到 sidecar"的地雷。

    刻意不碰 ``builtins.open`` 与 ``os.fdopen``：那两枚在测试进程里到处被用，误伤会把红报成
    假话。它们的形状由 :func:`_write_primitives_in_module` 从 AST 里抓，两枚钉合起来才叫
    "写不出去"。
    """
    prefix = str(tmp_path.resolve()).lower()

    def explodes(value):
        text = str(value if value is not None else "").lower()
        if not text:
            return False
        return text if (SIDECAR_TOKEN in text or text.startswith(prefix)) else False

    def tripwire(name, real, targets):
        def call(*args, **kwargs):
            for value in targets(*args, **kwargs):
                verdict = explodes(value)
                if verdict:
                    raise AssertionError(f"R248 J-3：{name} 想写 {verdict} —— JSON 写点归零破了")
            return real(*args, **kwargs)

        return call

    monkeypatch.setattr(
        tempfile,
        "mkstemp",
        tripwire(
            "tempfile.mkstemp",
            tempfile.mkstemp,
            lambda *args, **kwargs: [
                kwargs.get("prefix"),
                args[0] if args else None,
                kwargs.get("dir"),
                args[2] if len(args) > 2 else None,
            ],
        ),
    )
    monkeypatch.setattr(
        os,
        "replace",
        tripwire(
            "os.replace",
            os.replace,
            lambda *args, **kwargs: [args[1] if len(args) > 1 else kwargs.get("dst")],
        ),
    )
    for method in ("write_text", "write_bytes"):
        owner = _pathlib_owner(method)
        monkeypatch.setattr(
            owner,
            method,
            tripwire(f"{owner.__name__}.{method}", getattr(owner, method), lambda self, *a, **k: [self]),
        )
    monkeypatch.setattr(
        json,
        "dump",
        tripwire("json.dump", json.dump, lambda obj, fp, *a, **k: [getattr(fp, "name", None)]),
    )


def _legacy_entry(root, name="legacy-chart.png"):
    """造一枚 sidecar 条目，并把两枚正文都先落到盘上（地雷装好之前落，之后一枚不许写）。

    正文必须真存在：``list_active`` 认"字节还在"，缺文件的记录进不了清单，那一枚断言就会
    报出一条与写点无关的红。
    """
    path = root / name
    path.write_bytes(b"\x89PNG legacy bytes")
    (root / "revenue.png").write_bytes(b"\x89PNG chart bytes")
    return {
        "artifact_id": "legacy-1",
        "artifact_type": "chart",
        "owner_id": "keeper",
        "department_ids": ["finance"],
        "classification": "internal",
        "visibility": "private",
        "storage_path": str(path),
        "filename": path.name,
        "content_sha256": "c" * 64,
        "status": "active",
        "created_at": "2026-09-01T00:00:00+00:00",
        "expires_at": None,
        "source_version_id": None,
    }


def _principal():
    from app.agents.contracts import Principal

    return Principal.from_user(
        {"id": "keeper", "username": "keeper", "role": "manager", "department": "finance"}
    )


def test_the_sidecar_write_count_is_zero():
    hits = _sidecar_write_hits()

    assert hits == [], f"JSON 写点回来了，计数 = {len(hits)}：\n" + "\n".join(hits)


def test_the_module_has_no_write_primitive_at_all():
    primitives = _write_primitives_in_module()

    assert primitives == [], "artifacts.py 里出现了写文件的形状：" + "; ".join(primitives)


def test_the_read_leg_still_exists():
    """计数为 0 不许是"把一次性导入一起删了"换来的：读这一条必须还在。"""
    source = MODULE.read_text(encoding="utf-8")

    assert ".read_text(" in source, "sidecar 的导入读路径被删了"
    assert hasattr(ArtifactRegistry, "_import_legacy_metadata")
    assert artifact_module.LEGACY_METADATA_NAME == ".artifact-metadata.json"


def test_the_lifecycle_trips_no_writer(tmp_path, monkeypatch):
    root = tmp_path / "static"
    root.mkdir()
    sidecar = tmp_path / "sidecar.json"
    entry = _legacy_entry(root)
    fresh = root / "revenue.png"
    sidecar.write_text(json.dumps({"artifacts": [entry]}), encoding="utf-8")
    before_bytes = sidecar.read_bytes()
    before_listing = sorted(item.name for item in tmp_path.iterdir())
    _install_write_tripwires(monkeypatch, tmp_path)

    registry = ArtifactRegistry(root, metadata_path=sidecar)
    imported = registry.get("legacy-1")
    record = registry.register(fresh, artifact_type="chart", principal=_principal())
    listed = registry.list_active()
    registry.get(record.artifact_id)

    assert imported is not None and imported.owner_id == "keeper"
    assert [item.artifact_id for item in listed] == [record.artifact_id, "legacy-1"]
    assert registry.soft_delete(record.artifact_id) is True
    assert registry.get(record.artifact_id).status == "deleted"
    assert sidecar.read_bytes() == before_bytes, "登记改写了 sidecar 的字节"
    assert sorted(item.name for item in tmp_path.iterdir()) == before_listing, "生命周期多落了文件"


def test_the_module_no_longer_owns_a_save_leg():
    """``_save`` 整枚消失：留着它哪怕今天没人调，下一次接线就有人调。"""
    assert not hasattr(ArtifactRegistry, "_save")
    assert not hasattr(ArtifactRegistry, "_load")
