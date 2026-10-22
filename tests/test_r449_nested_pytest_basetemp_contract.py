# -*- coding: utf-8 -*-
r"""R449 判据①②④：全仓每一处起嵌套 pytest 的地方，子会话都必须自带 --basetemp，且落点在父件 scratch 之内。

机理（跟进单 §123 第四节；病的本身在 tests/test_r449_shared_temp_root_is_the_hazard.py 里当场复现）：
不传 --basetemp 的嵌套会话会和父会话共用 `%TEMP%\pytest-of-<user>` 那一枚根，而每枚会话收尾都会剪
该根下的旧编号目录（`tmp_path_retention_count` 默认留最近 3 枚，`.lock` 一过期照剪不误）——并发态下
父会话正在用的 tmp_path 就在同一枚根里排队等剪。c18043f 态 `python scripts/run_gate.py`（自选 -n 6）
= 620.9 s / 1 failed，唯一红 tests/test_r163_matrix_teeth.py::test_r163_teeth_proven_by_a_real_pytest_run
（FileNotFoundError: ...\pytest-of-fengx\pytest-NNNN\popen-gw5\...\test_r159_cross_scope_matrix.py），
而同一棵树串行 44 passed / 17.57 s ⇒ 与树上代码无关：这是门自己造的一枚假红。

口径三条，逐条机检：

① 名册：起嵌套 pytest 的件必须逐枚在册。文件名与处数都由现读派生再对照名册，谁新增一处、
   谁漏传一处，报错当场点名（上一班就是枚数抄错，所以这里一个字都不手抄）。
② 形状：每一处的 argv 里必须出现 "--basetemp"，且它的值必须是 `str(r449_nested_basetemp(<父 scratch>))`；
   `<父 scratch>` 还得是所在函数的参数 —— 硬编码 %TEMP%、cwd、自建临时根都算「落在父件之外」。
   同名单元另跑一遍行为取证：把每一枚件里那台 `r449_nested_basetemp` 就地取出来 exec，
   证明它给的落点确实长在父 scratch 之内、且每枚子会话各一枚（并发不互踩）。
③ 唯一豁免：本单自己的复现件允许起「不传 --basetemp」的会话，前提是那枚函数自己把
   `PYTEST_DEBUG_TEMPROOT` 关进 tmp 笼子。复现病不许真去碰共享根。

🔴 判据②明令禁止「给这些件打串行标记 / 从门里摘出去 / @pytest.mark.serial」这类回避：那类做法
让病继续存在只是不再被看见。所以本件只做形状审计，不改任何一件的调度属性。
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
#: 影子取证（test_r449_..._by_a_real_pytest_run）会把名册件复制到 tmp 里改坏再让真 pytest 读一遍；
#: 不翻这枚环境变量就是真树。翻法只改读数，不改盘上任何一枚被跟踪件。
SITE_ROOT = Path(os.environ.get("R449_TESTS_ROOT") or str(REPO_ROOT / "tests"))
HELPER_NAME = "r449_nested_basetemp"

#: 现读名册：posix 相对路径 -> (允许当父 scratch 的形参名, 该件里起嵌套会话的处数)。
ROSTER: dict[str, tuple[tuple[str, ...], int]] = {
    "tests/fixtures/r305_refutation_driver.py": (("shadow",), 1),
    "tests/fixtures/r349_catalog_tail_probe_driver.py": (("shadow",), 1),
    "tests/fixtures/r356_r357_refutation_driver.py": (("shadow",), 1),
    "tests/fixtures/r364_refutation_driver.py": (("shadow",), 1),
    "tests/fixtures/r558_refutation_driver.py": (("shadow",), 1),
    "tests/test_r134_chroma_writeback.py": (("parent_scratch",), 1),
    "tests/test_r163_matrix_teeth.py": (("parent_scratch",), 1),
    "tests/test_r449_nested_pytest_basetemp_contract.py": (("parent_scratch",), 1),
    "tests/test_r449_shared_temp_root_is_the_hazard.py": (("parent_scratch",), 2),
    "tests/test_r516_the_dataset_stubs_stay_on_the_class.py": (("parent_scratch",), 1),
}

#: 判据③的豁免名单：只有本单的复现件能起不带 --basetemp 的嵌套会话，且必须自带笼子。
QUARANTINED_PROBES = frozenset({"tests/test_r449_shared_temp_root_is_the_hazard.py"})
QUARANTINE_MARKER = "PYTEST_DEBUG_TEMPROOT"
#: 文本层探针：与 AST 层互相核对，防止「起法藏在看不见的位置」。注释与 docstring 不算。
SPAWN_TEXT_RE = re.compile('-m["\\\']?\\s*,\\s*["\\\']pytest["\\\']|-m\\s+pytest\\b|pytest\\.main\\(|MiniRunner')
SUBPROCESS_METHODS = frozenset({"run", "Popen", "call", "check_call", "check_output"})

_SCAN_CACHE: dict[str, tuple[list[dict], list[str]]] = {}


def _segment(lines, node):
    """按行表切出一枚节点的源码。

    别用 ast.get_source_segment：它每调一次都要把整篇源码重切一遍，而本件对全仓每一枚
    含 pytest 字样的件都要切 —— 首版就是这么在门里读了 200 s 的。
    """
    if node.lineno == node.end_lineno:
        return lines[node.lineno - 1][node.col_offset:node.end_col_offset]
    parts = [lines[node.lineno - 1][node.col_offset:]]
    parts.extend(lines[node.lineno:node.end_lineno - 1])
    if node.end_col_offset:
        parts.append(lines[node.end_lineno - 1][:node.end_col_offset])
    return "".join(parts)


def _subprocess_calls(tree: ast.AST):
    """所有 subprocess / os.system 那类子进程调用（不看 argv），用来数「这枚函数起过子进程」。"""
    for node, stack in _scopes(tree):
        fn = node.func
        module = fn.value.id if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) else None
        if module == "subprocess" and fn.attr in SUBPROCESS_METHODS:
            yield node, stack
        elif module == "os" and fn.attr in ("system", "popen"):
            yield node, stack


def _visible_argv_list(node):
    """argv 的字面列表：``[...] + list(targets)`` 取最左那一段，看不见就交回 None。"""
    current = node
    while isinstance(current, ast.BinOp) and isinstance(current.op, ast.Add):
        current = current.left
    return current if isinstance(current, ast.List) else None


def _argv_of(node: ast.Call, call_src):
    """(起法种类, argv 元素)；种类为 None 表示这枚调用与嵌套 pytest 无关。

    只认两种证据：argv 里逐字排着 ``-m``/``pytest``（含 ``[...] + list(targets)`` 这一族），
    或者调用文本里就写着起法（此时 argv 是变量 ⇒ 种类 opaque，按「看不见」报一处，不留静默通道）。
    """
    fn = node.func
    module = fn.value.id if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) else None
    if module == "subprocess" and fn.attr in SUBPROCESS_METHODS:
        kind_key = "subprocess"
    elif module == "pytest" and fn.attr == "main":
        kind_key = "pytest.main"
    else:
        return None, None
    target = node.args[0] if node.args else None
    if target is None:
        for kw in node.keywords:
            if kw.arg in ("args", "cmd"):
                target = kw.value
    listing = _visible_argv_list(target) if target is not None else None
    if kind_key == "pytest.main":
        return ("pytest.main", listing.elts if listing is not None else [])
    if listing is not None:
        vals = [e.value if isinstance(e, ast.Constant) and isinstance(e.value, str) else None
                for e in listing.elts]
        if any(vals[i] == "-m" and vals[i + 1] == "pytest" for i in range(len(vals) - 1)):
            return ("subprocess", listing.elts)
        # 也认「直接拿 pytest 可执行文件起」这一族：argv 里出现一枚独立的 "pytest" 字符串
        if "pytest" in vals:
            return ("subprocess", listing.elts)
        return (None, None)
    return ("opaque:subprocess", []) if SPAWN_TEXT_RE.search(call_src()) else (None, None)


def _scopes(tree: ast.AST):
    """枚历每一枚 Call，附带它所在的函数（模块级则为 None）。"""

    def walk(node: ast.AST, stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Call):
                yield child, stack
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield from walk(child, stack + [child])
            else:
                yield from walk(child, stack)

    yield from walk(tree, [])


def scan(tests_root: Path):
    """现读全仓：返回 (每一处嵌套起会话的记录, 看不见/审计不了的起法)。"""
    key = str(tests_root)
    if key in _SCAN_CACHE:
        return _SCAN_CACHE[key]
    records: list[dict] = []
    blind: list[str] = []
    for path in sorted(tests_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = "tests/" + path.relative_to(tests_root).as_posix()
        if "pytest" not in text:
            continue
        tree = ast.parse(text, filename=str(path))
        lines = text.splitlines(keepends=True)
        file_records = []
        for call, stack in _scopes(tree):
            kind, elts = _argv_of(call, lambda node=call: _segment(lines, node))
            if kind is None:
                continue
            func = stack[-1] if stack else None
            file_records.append({
                "rel": rel,
                "path": path,
                "lineno": call.lineno,
                "end_lineno": getattr(call, "end_lineno", call.lineno) or call.lineno,
                "kind": kind,
                "elts": elts,
                "func": func,
                "func_name": func.name if func is not None else "<module>",
                "func_src": _segment(lines, func) if func is not None else "",
                "text": text,
            })
        for spawn_call, stack in _subprocess_calls(tree):
            if any(r["lineno"] == spawn_call.lineno for r in file_records):
                continue
            scope = stack[-1] if stack else None
            scope_src = _segment(lines, scope) if scope is not None else text
            if SPAWN_TEXT_RE.search(scope_src):
                line = scope.lineno if scope is not None else spawn_call.lineno
                blind.append(
                    f"{rel}:{line} 这枚函数里既写着起嵌套 pytest 的字面量，又有一处 argv 看不见形状的子进程调用"
                    f"（{spawn_call.lineno} 行）⇒ 这一处的 --basetemp 审计不了，改成像样的字面 argv 传法"
                )
        records.extend(file_records)
    records.sort(key=lambda r: (r["rel"], r["lineno"]))
    _SCAN_CACHE[key] = (records, blind)
    return records, blind


def roster_findings(tests_root: Path) -> list[str]:
    """判据①：名册必须与现读逐枚等值，枚数与文件名都不许手抄。"""
    records, blind = scan(tests_root)
    found: dict[str, int] = {}
    for record in records:
        found[record["rel"]] = found.get(record["rel"], 0) + 1
    findings = list(blind)
    for rel in sorted(set(found) - set(ROSTER)):
        findings.append(f"{rel} 新起了一处嵌套 pytest 却没进名册（判据①：补进 ROSTER 并给子会话 --basetemp）")
    for rel in sorted(set(ROSTER) - set(found)):
        findings.append(f"{rel} 在册，可现场再读已经找不到它起嵌套 pytest 了（名册过期，判据①）")
    for rel in sorted(set(found) & set(ROSTER)):
        expected = ROSTER[rel][1]
        if found[rel] != expected:
            findings.append(f"{rel} 起嵌套 pytest 的处数是 {found[rel]}，名册记的是 {expected}（判据①：处数也要对上）")
    return findings


def _unwrap_value(node: ast.expr):
    """剥掉 str(...) 外壳，拿到真正那枚 r449_nested_basetemp(...) 调用。"""
    current = node
    while (isinstance(current, ast.Call) and isinstance(current.func, ast.Name)
           and current.func.id == "str" and current.args):
        current = current.args[0]
    return current


def basetemp_findings(tests_root: Path) -> list[str]:
    """判据②：每一处都必须 --basetemp=<父 scratch 之内>，漏哪枚报哪枚；看不见形状的起法同样算一处。"""
    records, blind = scan(tests_root)
    findings: list[str] = list(blind)
    for record in records:
        rel, line = record["rel"], record["lineno"]
        if record["kind"].startswith("opaque"):
            findings.append(f"{rel}:{line} argv 不是字面列表，本钉看不见 --basetemp（判据②：改成像样的 argv 传法）")
            continue
        values = [e.value if isinstance(e, ast.Constant) and isinstance(e.value, str) else None
                  for e in record["elts"]]
        if "--basetemp" not in values:
            allowed = (rel in QUARANTINED_PROBES and QUARANTINE_MARKER in (record["func_src"] or ""))
            if not allowed:
                findings.append(f"{rel}:{line} 起嵌套 pytest 却没传 --basetemp（判据①：子会话必须收进父件 scratch）")
            continue
        index = values.index("--basetemp")
        if index + 1 >= len(record["elts"]):
            findings.append(f"{rel}:{line} --basetemp 后面没有值")
            continue
        value = _unwrap_value(record["elts"][index + 1])
        call_ok = (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                   and value.func.id == HELPER_NAME and bool(value.args))
        if not call_ok:
            findings.append(
                f"{rel}:{line} --basetemp 的值不是 {HELPER_NAME}(<父 scratch>) 的形状"
                f"（判据②：落点必须由父 scratch 派生，%TEMP%/cwd/自建临时根都算越界）"
            )
            continue
        base = value.args[0]
        if not isinstance(base, ast.Name):
            findings.append(f"{rel}:{line} {HELPER_NAME} 的第一枚实参不是变量名，看不见它是不是父 scratch")
            continue
        allowed_names = ROSTER.get(rel, ((), 0))[0]
        if base.id not in allowed_names:
            findings.append(
                f"{rel}:{line} {HELPER_NAME}({base.id}) 里的 {base.id} 不在该件认可的父 scratch 名单 {list(allowed_names)} 之内"
            )
            continue
        func = record["func"]
        params = {a.arg for a in func.args.args + func.args.kwonlyargs} if func is not None else set()
        if base.id not in params:
            findings.append(f"{rel}:{line} {base.id} 不是所在函数 {record['func_name']} 的参数，父 scratch 无从谈起")
    return findings


def extract_helper(tests_root: Path, rel: str):
    """把某一枚在册件里的 r449_nested_basetemp 摘出来 exec（不 import 那枚件，因此不碰 app/torch）。"""
    path = tests_root.parent / rel
    text = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(text, filename=str(path))
    func = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == HELPER_NAME), None)
    if func is None:
        raise AssertionError(f"{rel} 里没有 {HELPER_NAME} 那台落点派生器（判据②要求逐枚自带同形一件）")
    namespace: dict = {"Path": Path, "tempfile": tempfile, "os": os}
    exec(compile(ast.Module(body=[func], type_ignores=[]), str(path), "exec"), namespace)
    return path, namespace[HELPER_NAME]


def _shadow_site_root(dst: Path) -> Path:
    """把名册里的件逐枚复制进影子根：真树一个字都不动，改坏只改副本。"""
    root = dst / "tests"
    for rel in ROSTER:
        target = root / Path(rel).relative_to("tests")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / rel, target)
    return root


def _strip_basetemp(text: str) -> str:
    """摘刀：把 '"--basetemp", str(r449_nested_basetemp(...))' 整段抹掉，命中数不对就中止。"""
    stripped, hits = re.subn(
        r'"--basetemp",\s*str\(r449_nested_basetemp\([^)]*\)\)[,\s]*', "", text
    )
    if hits != 1:
        raise AssertionError(f"摘刀命中 {hits} 次（要求恰好 1 次），这枚反证造不出红")
    return stripped


# ==================================================================================== 判据①


def test_r449_roster_of_nested_pytest_sites_is_read_not_copied():
    findings = roster_findings(SITE_ROOT)
    assert findings == [], "嵌套 pytest 名册与现读不符：\n" + "\n".join(findings)
    records, _ = scan(SITE_ROOT)
    assert len({r["rel"] for r in records}) == len(ROSTER), "名册枚数与现读枚数不等"


# ==================================================================================== 判据②


def test_r449_every_nested_pytest_session_gets_its_own_basetemp():
    findings = basetemp_findings(SITE_ROOT)
    assert findings == [], "有起嵌套 pytest 的地方没把子会话 basetemp 收进父件 scratch：\n" + "\n".join(findings)


def test_r449_child_basetemp_helper_lands_inside_the_parent_scratch_in_every_site(tmp_path):
    for rel in sorted(ROSTER):
        _site_file, helper = extract_helper(SITE_ROOT, rel)
        parent = tmp_path / "r449-scratch" / rel.replace("/", "_")
        first = helper(parent)
        second = helper(parent)
        assert parent.is_dir(), f"{rel} 的 {HELPER_NAME} 没把父 scratch 立起来"
        assert first.is_dir(), f"{rel} 的 {HELPER_NAME} 没返回存在的目录"
        assert parent in first.parents, f"{rel} 的子会话 basetemp 落在了父 scratch 之外：{first}"
        assert first != second, f"{rel} 的两枚子会话共用一枚 basetemp，并发必互踩"
        assert first.parent == second.parent, f"{rel} 的子会话落点散开了，不在同一枚父 scratch 之下"


# ==================================================================================== 判据④ 的三把牙


def test_r449_nail_bites_when_a_site_drops_the_basetemp_flag(tmp_path):
    """牙一（判据④a）：摘掉 --basetemp 传参 ⇒ 报错必须点名那一枚件。"""
    root = _shadow_site_root(tmp_path)
    target = root / "test_r163_matrix_teeth.py"
    target.write_text(_strip_basetemp(target.read_text(encoding="utf-8")), encoding="utf-8")
    findings = basetemp_findings(root)
    assert len(findings) == 1, "摘了一处刀，读数却不是恰好一枚：" + str(findings)
    assert "test_r163_matrix_teeth.py" in findings[0], findings[0]
    assert "--basetemp" in findings[0], findings[0]
    assert roster_findings(root) == [], "摘刀不该动摇名册读数：" + str(roster_findings(root))


def test_r449_nail_bites_when_the_child_basetemp_leaves_the_parent_scratch(tmp_path):
    """牙二（判据④b）：子 basetemp 改到父 tmp_path 之外（这里改成 %TEMP% 直根）⇒ 红。"""
    root = _shadow_site_root(tmp_path)
    target = root / "test_r134_chroma_writeback.py"
    mutated = target.read_text(encoding="utf-8").replace(
        'str(r449_nested_basetemp(parent_scratch))', 'str(tempfile.gettempdir())'
    )
    assert mutated != target.read_text(encoding="utf-8"), "这枚变异没落地"
    target.write_text(mutated, encoding="utf-8")
    findings = basetemp_findings(root)
    assert len(findings) == 1, "只该抓到一处：" + str(findings)
    assert "test_r134_chroma_writeback.py" in findings[0], findings[0]
    assert "父 scratch" in findings[0], findings[0]


def test_r449_nail_bites_when_a_new_nested_pytest_site_appears_unnamed(tmp_path):
    """牙三（判据④c）：新长出一枚漏传的件 ⇒ 名册与形状两把都红，且都点名新件。"""
    root = _shadow_site_root(tmp_path)
    newcomer = root / "test_r449_synth_unfixed_site.py"
    newcomer.write_text(
        "import subprocess\nimport sys\n\n\n"
        "def _spawn(parent_scratch):\n"
        "    import tempfile\n\n"
        "    return subprocess.run(\n"
        '        [sys.executable, "-m", "pytest", "-q", "--no-header"],\n'
        "        cwd=str(parent_scratch), capture_output=True, text=True)\n",
        encoding="utf-8",
    )
    roster = roster_findings(root)
    assert any("test_r449_synth_unfixed_site.py" in f for f in roster), str(roster)
    shape = basetemp_findings(root)
    assert any("test_r449_synth_unfixed_site.py" in f for f in shape), str(shape)


def test_r449_nail_bites_when_an_unfixable_shape_is_used(tmp_path):
    """盲区闭合：argv 拼成变量（看不见形状）也算一处违规，本钉不给自己留静默通道。"""
    root = _shadow_site_root(tmp_path)
    (root / "test_r449_synth_opaque_argv.py").write_text(
        "import subprocess\n\n\n"
        "def _spawn(parent_scratch):\n"
        "    argv = [sys.executable, '-m', 'pytest', '-q']\n\n"
        "    return subprocess.run(argv, capture_output=True, text=True)\n",
        encoding="utf-8",
    )
    findings = basetemp_findings(root)
    assert any("test_r449_synth_opaque_argv.py" in f and "看不见" in f for f in findings), str(findings)


# ==================================================================================== 判据③：真跑一次


def _run_contract_copy(parent_scratch: Path, shadow: Path, site_root: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    env["R449_TESTS_ROOT"] = str(site_root)
    return subprocess.run(
        [
            sys.executable, "-m", "pytest", "tests/test_r449_nested_pytest_basetemp_contract.py",
            "-k", "every_nested_pytest_session_gets_its_own_basetemp",
            "-q", "--no-header", "-p", "no:randomly", "-p", "no:cacheprovider",
            "--basetemp", str(r449_nested_basetemp(parent_scratch)),
        ],
        cwd=str(shadow), capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=600,
    )


def r449_nested_basetemp(parent_scratch: Path) -> Path:
    """R449：每一枚嵌套 pytest 会话只用自己的 basetemp，落点必须在父件 scratch 之内。

    本件既审计别人也审计自己：两处真跑（对照 + 摘刀）都从这里取落点，因此也在判据②的形状之内。
    """
    root = Path(parent_scratch) / "r449-nested-basetemp"
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="child-", dir=str(root)))


def test_r449_teeth_proven_by_a_real_pytest_run(tmp_path):
    """把名册件复制进影子根、摘掉一处 --basetemp，让真 pytest 跑本件那一枚形状钉：必须红且点名。

    对照（同一枚影子根、一字未改）必须绿 —— 红只能由摘掉的那把刀带来，不是环境噪音。
    真树上的六枚件全程只被读取，收尾再核一次字节：本件一个字都不许写回去。
    """
    before = {rel: (REPO_ROOT / rel).read_bytes() for rel in ROSTER}
    clean_root = _shadow_site_root(tmp_path / "clean")
    green = _run_contract_copy(tmp_path, tmp_path / "clean", clean_root)
    assert green.returncode == 0 and "1 passed" in green.stdout, (
        "未改动的影子根里那枚形状钉必须绿：" + (green.stdout + green.stderr)[-2500:]
    )

    shadow = _shadow_site_root(tmp_path / "mutated")
    target = shadow / "test_r163_matrix_teeth.py"
    target.write_text(_strip_basetemp(target.read_text(encoding="utf-8")), encoding="utf-8")
    red = _run_contract_copy(tmp_path, tmp_path / "mutated", shadow)
    out = red.stdout + red.stderr
    assert red.returncode != 0, "摘掉 --basetemp 之后那枚形状钉居然还绿：" + out[-2500:]
    assert "1 failed" in out, out[-2500:]
    assert "test_r163_matrix_teeth.py" in out, "红了却没点名是哪枚件漏传：" + out[-2500:]
    assert "--basetemp" in out, "红了却没说是 --basetemp 那一处：" + out[-2500:]
    for rel, raw in before.items():
        assert (REPO_ROOT / rel).read_bytes() == raw, f"本件不许写被跟踪件：{rel}"
