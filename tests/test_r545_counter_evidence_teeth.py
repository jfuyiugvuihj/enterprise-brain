# -*- coding: utf-8 -*-
"""R545 的反证刀（R641 返工）：把这单交出去的那五枚判据逐枚摘掉一次，必须红；影子与写域的自证全在受控影子端。

机械沿用 R552/R585：影子只在内存里（源文从盘上读进字符串、归一 LF、改、写进 pytest 的
`tmp_path` 留痕、compile + exec 成另一枚模块），**绝不写回仓内**；影子模块的 ROOT 一律指回真仓，
否则红得没有道理；每把刀都先跑正控（同一套影子机械、`edits=()`）必须先绿，victim 才准算被咬中；
`_bite` 接 BaseException（`Failed: DID NOT RAISE` 继承的是 BaseException）。

R641 返工（10-04 总控亲跑退回的唯一原因）：旧 `test_z9c` 执行 `git status --porcelain`，然后断言**每一条**
未提交条目都必须落在本单写域内——等于把「整棵工作树此刻干不干净」当成常驻判据。主树常年脏着一枚被跟踪的
`chroma_db/chroma.sqlite3`（另有未跟踪 `.zcodeignore` 与业主作业目录），于是这枚牙在自己的树里绿、一搬进
主树必红。本周同族病第三次（#96 拿施工期盘面脏当永真判据／#107 拿旧账收席／R545 本枚）⇒ 硬红线。
返工后：写域自证搬到 `tmp_path` 里的受控影子仓（摆货必绿／往写域外塞 `app/poison.py` 必红／再复现主树那种
「别人的脏」以证货判据不受盘面支配）；「影子不落盘」改由 AST 静态证明＋影子端正控；`test_z9d` 是反同族病的
常驻闸——任何盘面状态读取器敢拿仓根当判定对象，本件当场红。

七把刀（逐枚点名 victim，全部住在 tests/test_r545_queue_failure_teeth.py）：
  K1 摘掉 `fail_or_retry` 里 `data["last_error"] = error` 那一行（判工词点名的那一枚刀）
     victim：test_a_dead_turn_carries_a_registered_reason_readable_on_the_terminal_payload
  K2 终态词表少认一枚：把写进状态键的 `"awaiting_approval"` 改成一枚契约里没有的字
     victim：test_the_terminal_vocabulary_is_derived_and_names_the_sixth_word
  K3 摘掉 dead_verdict 那一笔落账（两枚 dead 就被洗成一枚）
     victim：test_the_verdict_lands_on_the_durable_ledger_verbatim
  K4 把缺证折成零：`_absent()` 交 0 而不是 None
     victim：test_the_expired_row_speaks_nothing_and_the_probe_records_none
  K5 摘掉「产物落仓外」那道闸
     victim：test_the_probe_refuses_an_artifact_directory_inside_the_repo
  K6 摘掉 `overall()` 里「量不到优先于通过」那一支（rc=2 变 rc=0）
     victim：test_zero_never_comes_from_an_empty_window
  K7 把「原因码必须是在册稳定码」那一判钝化（发明一枚码也不红）
     victim：test_an_unregistered_reason_code_on_the_readout_reddens_the_dead_cell

全程离线：不打模型、不开端口、不起容器、不动生产 Redis、不连 PG、产品码零字节落盘。
跑法：
    python -m pytest tests/test_r545_counter_evidence_teeth.py -o addopts= -p no:cacheprovider -q
"""
from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import tests.test_r545_queue_failure_teeth as nails

REPO = Path(__file__).resolve().parents[1]
QUEUE_REL = "app/common/reliable_queue.py"
PROBE_REL = "scripts/r545_queue_failure_probe.py"
SHADOW_REPO_FILES = ("app/common/reliable_queue.py", "app/api/v1/chat.py",
                     "app/agents/contracts.py", "docs/api/contract-v1.md",
                     "scripts/eval_transport_ask_v2.py")


# ---- 刀口（逐枚原文锚点；锚点漂了本件当场红，见 test_z8）----
CUT_K1 = ('            data["last_error"] = error\n',
          '            pass  # 摘刀：成因不再落进重试账本\n')
CUT_K2 = ('            self.redis.set(self._status_key(request_id), "awaiting_approval")\n',
          '            self.redis.set(self._status_key(request_id), "parked_for_approval")\n')
CUT_K3 = ('                data[DEAD_VERDICT_LEDGER_KEY] = {"reason": str(error), '
          '"retryable": bool(retryable)}\n',
          '                pass  # 摘刀：终局判定不落账\n')
CUT_K4 = ('    return {"value": None, "speaks": SPEAKS_CANNOT, "absent_path": path, "note": note}\n',
          '    return {"value": 0, "speaks": SPEAKS_CANNOT, "absent_path": path, "note": note}\n')
CUT_K5 = ('    if is_inside_repo(out, repo):\n', '    if False and is_inside_repo(out, repo):\n')
CUT_K6 = ('    if UNMEASURED in verdicts:\n        return 2\n',
          '    if False:\n        return 2\n')
CUT_K7 = ('        elif entry["reason_is_stable_code"] is False:\n', '        elif False:\n')

KNIVES = {
    "K1": {"target": QUEUE_REL, "mode": "queue", "edits": (CUT_K1,),
           "victim": "test_a_dead_turn_carries_a_registered_reason_readable_on_the_terminal_payload"},
    "K2": {"target": QUEUE_REL, "mode": "derive", "edits": (CUT_K2,),
           "victim": "test_the_terminal_vocabulary_is_derived_and_names_the_sixth_word"},
    "K3": {"target": QUEUE_REL, "mode": "queue", "edits": (CUT_K3,),
           "victim": "test_the_verdict_lands_on_the_durable_ledger_verbatim"},
    "K4": {"target": PROBE_REL, "mode": "probe", "edits": (CUT_K4,),
           "victim": "test_the_expired_row_speaks_nothing_and_the_probe_records_none"},
    "K5": {"target": PROBE_REL, "mode": "probe", "edits": (CUT_K5,),
           "victim": "test_the_probe_refuses_an_artifact_directory_inside_the_repo"},
    "K6": {"target": PROBE_REL, "mode": "probe", "edits": (CUT_K6,),
           "victim": "test_zero_never_comes_from_an_empty_window"},
    "K7": {"target": PROBE_REL, "mode": "probe", "edits": (CUT_K7,),
           "victim": "test_an_unregistered_reason_code_on_the_readout_reddens_the_dead_cell"},
}


def _text(rel: str) -> str:
    return (REPO / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")


def _apply(text: str, edits) -> str:
    out = text
    for old, new in edits:
        if out.count(old) != 1:
            raise AssertionError("刀口没落在唯一一处：%r（命中 %d 枚）" % (old[:48], out.count(old)))
        out = out.replace(old, new, 1)
    return out


def _exec_module(name: str, source_text: str, where: Path, root: Path | None = None):
    """写进 tmp_path 留痕 → compile → exec 成另一枚模块；仓内那枚源文一个字节都不动。"""
    where.mkdir(parents=True, exist_ok=True)
    path = where / (name + ".py")
    path.write_text(source_text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # 先登记再 exec：dataclass 的字段解析要回 sys.modules 找 cls.__module__（QueueMessage 就是 dataclass）
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if root is not None and hasattr(module, "ROOT"):
        module.ROOT = root
    return module


def _shadow_repo(tmp_path: Path, edits) -> Path:
    """把派生面要读的五枚源文搬进影子仓，只改 K2 那一处字面量，其余逐字节原样。"""
    root = tmp_path / "shadow-repo"
    for rel in SHADOW_REPO_FILES:
        text = _text(rel)
        if rel == QUEUE_REL:
            text = _apply(text, edits)
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def _arm(knife: str, tmp_path: Path, monkeypatch, *, bite: bool):
    """装刀：把影子类／影子仓／影子量具接到在册钉的命名空间上；`bite=False` 就是正控。"""
    spec = KNIVES[knife]
    edits = spec["edits"] if bite else ()
    if spec["mode"] == "queue":
        shadow = _exec_module("r545_mutant_queue_" + knife, _apply(_text(QUEUE_REL), edits), tmp_path)
        monkeypatch.setattr(nails, "ReliableQueue", shadow.ReliableQueue)
        monkeypatch.setattr(nails, "reliable_queue", shadow)
        return
    if spec["mode"] == "derive":
        root = _shadow_repo(tmp_path, edits)
        real = nails.PROBE.derive_vocabulary
        monkeypatch.setattr(nails.PROBE, "derive_vocabulary",
                            lambda repo=None, contract_text=None: real(repo=root))
        return
    probe = _exec_module("r545_mutant_probe_" + knife, _apply(_text(PROBE_REL), edits), tmp_path,
                         root=nails.PROBE.ROOT)
    monkeypatch.setattr(nails, "PROBE", probe)


def _run_victim(knife: str, tmp_path: Path):
    victim = getattr(nails, KNIVES[knife]["victim"])
    signature = list(victim.__code__.co_varnames[:victim.__code__.co_argcount])
    if "tmp_path" in signature:
        victim(tmp_path)
    else:
        victim()


def _bite(knife: str, tmp_path: Path, monkeypatch) -> bool:
    _arm(knife, tmp_path, monkeypatch, bite=True)
    try:
        _run_victim(knife, tmp_path / "bite")
    except BaseException:  # noqa: BLE001 - Failed: DID NOT RAISE 继承的是 BaseException
        return True
    return False


@pytest.mark.parametrize("knife", sorted(KNIVES))
def test_the_positive_control_stays_green(knife, tmp_path, monkeypatch):
    """同一套影子机械、刀口不落（edits=())：victim 必须先绿，否则后面的红没有道理。"""
    _arm(knife, tmp_path / "control", monkeypatch, bite=False)
    _run_victim(knife, tmp_path / "control")


@pytest.mark.parametrize("knife", sorted(KNIVES))
def test_each_knife_reddens_its_named_victim(knife, tmp_path, monkeypatch):
    assert _bite(knife, tmp_path, monkeypatch), (
        "刀 %s 没咬中 %s：那一格判据其实没有牙" % (knife, KNIVES[knife]["victim"]))


def test_z8_every_blade_anchor_is_still_exactly_one_hit_in_the_shipped_bytes():
    """锚点在册：产品字节与量具字节里每一处刀口仍旧只命中一枚（漂了就红，不许默默失刀）。"""
    for knife, spec in sorted(KNIVES.items()):
        text = _text(spec["target"])
        for old, _new in spec["edits"]:
            assert text.count(old) == 1, "%s 的刀口在 %s 里命中 %d 枚" % (knife, spec["target"],
                                                                            text.count(old))


def test_z8b_the_two_deads_stay_tellable_apart_after_the_blade_set():
    """K1/K3 两把刀各咬各的：摘 last_error 只让成因哑，摘 verdict 只让终局判定哑。"""
    queue, request_id = nails._queue("blade-split")
    queue.reserve()
    queue.fail_or_retry(request_id, nails.CONTEXT_CODE, retryable=False)
    ledger = nails.json.loads(queue.redis.get(queue._message_key(request_id)))
    assert ledger["last_error"] == nails.CONTEXT_CODE
    assert ledger["dead_verdict"] == {"reason": nails.CONTEXT_CODE, "retryable": False}


# ==================== R641 返工：写域与影子的自证全在受控影子端（不看此刻盘面） ====================

#: 本单写域（工单原文点名六枚前缀：r545 与 r641 两代都算）。
ALLOWED_DOMAIN_PREFIXES = ("scripts/r545_", "scripts/r641_", "tests/test_r545_",
                           "tests/test_r641_", "docs/testing/r545-", "docs/testing/r641-")

#: 本单点名的货 = 交付三样（量具 + 两枚牙 + 取证纸），逐枚点名，不靠全盘扫描去「发现」自己交了什么。
SHIPMENT = ("scripts/r545_queue_failure_probe.py",
            "tests/test_r545_queue_failure_teeth.py",
            "tests/test_r545_counter_evidence_teeth.py",
            "docs/testing/r545-queue-failure-probe-2026-10-04.md")

#: 反证机械的影子工件该长什么样；主树那种「别人的脏」永远不匹配它。
SHADOW_LEAK_RE = re.compile(r"r545_mutant|shadow-repo|shadow_repo|_r545_probe_K", re.IGNORECASE)

#: 盘面状态读取器：读的是「此刻这棵树干不干净」，不是「本单的货在不在位」。
STATE_READERS = frozenset({"untracked_entries", "tracked_modifications", "uncommitted_entries",
                           "domain_violations", "shadow_artifact_leaks"})
#: 同一族里改走 git 命令的写法（读到这些旗标就按盘面读取器对待）。
GIT_STATE_FLAGS = ("--porcelain", "ls-files", "diff", "rev-list")
#: 写句柄的名字：出现仓根就是「影子要往仓里落」的形状。分两族——路径对象上的方法，
#: 以及 os/shutil 那两枚宿主下的文件系统函数。str.replace／decode().replace 不是写句柄，
#: 把它当病抓会让判定面自己变疯牙（本席 10-04 第一版就踩了：`_text` 里那一枚 replace 被误点名）。
PATH_WRITE_METHODS = frozenset({"write_text", "write_bytes", "mkdir", "touch", "unlink", "rmdir"})
FS_WRITE_FUNCTIONS = frozenset({"open", "makedirs", "rmtree", "copy", "copyfile", "copytree",
                                "move", "replace", "rename"})
FS_MODULE_HOSTS = frozenset({"os", "shutil"})


def _git(repo_dir, *args: str) -> str:
    """git 只在受控影子仓里跑；仓根一枚都不许进来（谁进来谁红，见 test_z9d）。"""
    if shutil.which("git") is None:
        pytest.skip("git 不可用：影子仓建不起来，这一格明写跳过而不是判过")
    done = subprocess.run(["git", "-C", str(Path(repo_dir)), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert done.returncode == 0, "git %s rc=%d：%s" % (
        " ".join(args), done.returncode, done.stderr.strip())
    return done.stdout


def _normalised(lines) -> list:
    return sorted({str(item).replace("\\", "/").strip().strip('"') for item in lines if str(item).strip()})


def untracked_entries(repo_dir) -> list:
    """未提交清单只认 git 那一枚 ls-files --others --exclude-standard：被 ignore 遮住的不算货。"""
    return _normalised(_git(repo_dir, "ls-files", "--others", "--exclude-standard").splitlines())


def tracked_modifications(repo_dir) -> list:
    return _normalised(_git(repo_dir, "diff", "--name-only", "HEAD").splitlines())


def uncommitted_entries(repo_dir) -> list:
    return sorted(set(untracked_entries(repo_dir)) | set(tracked_modifications(repo_dir)))


def domain_violations(entries, allowed=ALLOWED_DOMAIN_PREFIXES) -> list:
    """纯函数：落在写域外的条目名。判定对象永远是影子仓的清单，不是此刻的真树。"""
    return [entry for entry in entries if not str(entry).startswith(tuple(allowed))]


def shipment_check(shipment=SHIPMENT, root=None, allowed=ALLOWED_DOMAIN_PREFIXES) -> dict:
    """货判据：逐枚点名「在不在位」+「在不在写域内」。全盘零条目永远不是判据。"""
    base = Path(root) if root is not None else REPO
    per_goods = [{"path": rel, "exists": (base / rel).is_file(),
                  "inside_write_domain": str(rel).startswith(tuple(allowed))} for rel in shipment]
    offenders = [item["path"] for item in per_goods
                 if not (item["exists"] and item["inside_write_domain"])]
    return {"per_goods": per_goods, "offenders": offenders}


def shadow_artifact_leaks(repo_root) -> list:
    """受控根里扫一遍反证机械的影子工件名；只走 scripts/tests/docs 三处，不碰 .venv 那枚 Junction。"""
    root = Path(repo_root)
    hits = []
    for rel in ("scripts", "tests", "docs"):
        base = root / rel
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_symlink() or ".venv" in path.parts or not path.is_file():
                continue
            if SHADOW_LEAK_RE.search(path.name):
                hits.append(str(path.relative_to(root)).replace("\\", "/"))
    return sorted(hits)


def _callee_name(node):
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _literal_blob(node) -> str:
    return " ".join(str(item.value) for item in ast.walk(node) if isinstance(item, ast.Constant))


def _live_root_names(node):
    return {item.id for item in ast.walk(node) if isinstance(item, ast.Name)} & {"REPO", "PROBE_PATH"}


def _is_write_call(node) -> bool:
    if isinstance(node.func, ast.Name):
        return node.func.id in FS_WRITE_FUNCTIONS
    if isinstance(node.func, ast.Attribute):
        if node.func.attr in PATH_WRITE_METHODS:
            return True
        host = node.func.value
        return (isinstance(host, ast.Name) and host.id in FS_MODULE_HOSTS
                and node.func.attr in FS_WRITE_FUNCTIONS)
    return False


def _top_level_functions(source: str) -> set:
    """毒有没有真落进源文，看 AST 里多没多出那一枚函数名——不数串，免得把注释与字面量算进来。"""
    return {node.name for node in ast.parse(source).body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def live_checkout_gates(source: str) -> list:
    """AST 现取：盘面状态读取器一旦被喂仓根，就是「把整棵树此刻脏不脏当判据」的那一枚病。"""
    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        callee = _callee_name(node)
        reads_state = callee in STATE_READERS or (
            callee in {"run", "Popen", "check_output", "check_call"}
            and any(flag in _literal_blob(node) for flag in GIT_STATE_FLAGS))
        if not reads_state:
            continue
        roots = _live_root_names(node)
        if roots:
            out.append("%d:%s(%s)" % (node.lineno, callee, ",".join(sorted(roots))))
    return out


def repo_rooted_writes(source: str) -> list:
    """AST 现取：写句柄的实参里出现仓根 = 影子往仓里落盘的那一形（旧 z9 想防的就是它）。"""
    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not _is_write_call(node):
            continue
        roots = _live_root_names(node)
        if roots:
            out.append("%d:%s(%s)" % (node.lineno, _callee_name(node), ",".join(sorted(roots))))
    return out

def _domain_shadow(where: Path, state: str, shipment=SHIPMENT) -> Path:
    """一枚受控影子仓：自己有 HEAD、有 .gitignore、有被跟踪的 chroma_db/chroma.sqlite3。

    state 只决定往里摆什么条目，判定面一枚不变：
      goods_in_domain                 —— 只摆本单的货（未提交，全在写域内）
      poison_outside_domain           —— 同上，再往写域外塞一枚 app/poison.py
      foreign_dirt_like_the_main_tree —— 同上，再把主树那种「别人的脏」原样复现
    """
    root = where / "domain-shadow"
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    for key, value in (("user.email", "r641@shadow.invalid"), ("user.name", "R641 shadow"),
                       ("core.autocrlf", "false"), ("core.quotePath", "false")):
        _git(root, "config", key, value)
    seeded = {"README.md": "受控影子仓：只为量写域判定而存在。\n",
              ".gitignore": "*.log\nbuild/\n",
              "app/__init__.py": "",
              "chroma_db/chroma.sqlite3": "seed\n"}
    for rel, body in seeded.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "shadow base")
    for rel in shipment:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("影子货：只验清单与写域，不验内容。\n", encoding="utf-8")
    ignored = root / "build" / "r545_mutant_probe_K1.py"
    ignored.parent.mkdir(parents=True, exist_ok=True)
    ignored.write_text("被 .gitignore 遮住，不该进清单。\n", encoding="utf-8")
    if state == "poison_outside_domain":
        (root / "app" / "poison.py").write_text("# 写域外的一枚\n", encoding="utf-8")
    elif state == "foreign_dirt_like_the_main_tree":
        (root / "chroma_db" / "chroma.sqlite3").write_text("dirty by another agent\n", encoding="utf-8")
        (root / ".zcodeignore").write_text("x\n", encoding="utf-8")
        job = root / "作业目录"
        job.mkdir(parents=True, exist_ok=True)
        (job / "README.md").write_text("业主作业目录\n", encoding="utf-8")
    return root


@pytest.mark.parametrize("state", ("goods_in_domain", "poison_outside_domain",
                                   "foreign_dirt_like_the_main_tree"))

def test_z9c_the_write_domain_is_proved_on_a_controlled_shadow_repo(state, tmp_path):
    """R641 返工：写域自证不看「整棵树此刻干不干净」，改看受控影子仓的三个态。

    旧写法执行 git status --porcelain 并要求每一条未提交条目都落在本单写域内，于是这枚牙在自己的
    树里绿、一搬进主树必红（主树常年脏着一枚被跟踪的 chroma_db/chroma.sqlite3，另有未跟踪
    .zcodeignore 与业主作业目录）。返工后判定面只对着本席自己造的影子仓，货判据逐枚点名。
    """
    root = _domain_shadow(tmp_path, state)
    entries = uncommitted_entries(root)
    violations = domain_violations(entries)
    goods = shipment_check(root=root)
    assert (root / "build" / "r545_mutant_probe_K1.py").is_file(), "影子端连 ignored 条目都摆不进，这格白测"
    assert "build/r545_mutant_probe_K1.py" not in entries, "exclude-standard 没生效：清单里混进了被 ignore 的件"
    assert goods["offenders"] == [], json.dumps(goods["per_goods"], ensure_ascii=False)
    if state == "goods_in_domain":
        assert untracked_entries(root) == sorted(SHIPMENT)
        assert tracked_modifications(root) == []
        assert violations == []
        assert domain_violations(SHIPMENT) == []
        # 活性正控：同一枚判定面遇到写域外的条目必须点名（旧 z9c 缺的正是这一格）
        assert domain_violations(("app/poison.py",)) == ["app/poison.py"]
    elif state == "poison_outside_domain":
        assert violations == ["app/poison.py"], violations
        assert "app/poison.py" in untracked_entries(root)
    else:
        assert set(violations) == {"chroma_db/chroma.sqlite3", ".zcodeignore", "作业目录/README.md"}, violations
        assert goods["offenders"] == [], "主树那种脏一进来，货判据就跟着红 = 旧 z9c 的病没治好"


def test_z9d_no_checker_may_gate_on_the_live_checkout_state():
    """反同族病的常驻闸（#96 拿施工期盘面脏当永真判据／#107 拿旧账收席／R545 z9c 拿整棵树当判据）。

    盘面状态读取器与 git 状态命令一律不许拿仓根当判定对象；闸自己也上毒验一遍活性。
    """
    source = Path(__file__).read_bytes().decode("utf-8")
    for path in (Path(__file__), Path(nails.__file__)):
        offenders = live_checkout_gates(path.read_bytes().decode("utf-8"))
        assert offenders == [], "%s 把盘面状态当成了判据：" % path.name + ", ".join(offenders)
    poison = "_poison_gates_on_the_whole_tree"
    mutant = source.replace("def _domain_shadow(",
                            "def " + poison + "():\n"
                            "    assert domain_violations(uncommitted_entries(REPO)) == []\n\n\n"
                            "def _domain_shadow(", 1)
    assert mutant != source, "锚点漂了：这一格没能把毒拼进源文"
    assert poison not in _top_level_functions(source), "毒本来就在？这一格测了个寂寞"
    assert poison in _top_level_functions(mutant), "毒没落成一枚真函数（只落进字符串里不算）"
    bit = live_checkout_gates(mutant)
    assert bit and any("REPO" in site for site in bit), ("闸钝了：影子端塞进仓根也没揪出来", bit)

def test_z9_the_shadow_machinery_leaves_its_tracks_under_tmp_only(tmp_path):
    """旧 z9 拿「被跟踪件此刻的 sha」当判据（别的班一改产品码就假红）；返工成静态证明 + 活性毒。"""
    source = Path(__file__).read_bytes().decode("utf-8")
    assert repo_rooted_writes(source) == [], repo_rooted_writes(source)
    poison = "_poison_writes_into_the_repo"
    mutant = source.replace("def _normalised(",
                            "def " + poison + "():\n"
                            '    (REPO / "scripts" / "r545_mutant_probe_K1.py").write_text("x")\n\n\n'
                            "def _normalised(", 1)
    assert mutant != source, "锚点漂了：这一格没能把毒拼进源文"
    assert poison not in _top_level_functions(source), "毒本来就在？这一格测了个寂寞"
    assert poison in _top_level_functions(mutant), "毒没落成一枚真函数（只落进字符串里不算）"
    assert repo_rooted_writes(mutant), "静态证明钝了：往仓根写文件也没揪出来"
    shadow = _exec_module("r545_mutant_probe_K9", _apply(_text(PROBE_REL), ()), tmp_path)
    emitted = sorted(str(path.relative_to(tmp_path)).replace("\\", "/")
                     for path in Path(tmp_path).rglob("r545_mutant_probe_K9.py"))
    assert emitted == ["r545_mutant_probe_K9.py"], emitted
    assert hasattr(shadow, "derive_vocabulary")
    assert shadow_artifact_leaks(tmp_path) == [], "影子工件落进了 scripts/tests/docs 那一形"

@pytest.mark.parametrize("state", ("clean_shadow_root", "planted_shadow_leak"))
def test_z9b_the_leak_scanner_is_proved_on_a_controlled_root(state, tmp_path):
    """影子不落盘那格判据的活性：同一枚扫描器，摆货必红、不摆必绿——它只对着受控根跑。"""
    root = tmp_path / ("leak-shadow-" + state)
    for rel in ("scripts", "tests", "docs"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    planted = root / "scripts" / "r545_mutant_probe_K1.py"
    if state == "planted_shadow_leak":
        planted.write_text("# 反证机械的影子漏进仓的那一形\n", encoding="utf-8")
        assert shadow_artifact_leaks(root) == ["scripts/r545_mutant_probe_K1.py"]
    else:
        assert shadow_artifact_leaks(root) == []
        assert not planted.exists()


def test_z9e_the_named_shipment_is_present_and_inside_the_domain():
    """这一格在任何一棵树上都同色：它逐枚点名本单的货，不看盘面上有多少条目。"""
    report = shipment_check()
    assert [item["path"] for item in report["per_goods"]] == list(SHIPMENT)
    assert report["offenders"] == [], json.dumps(report["per_goods"], ensure_ascii=False)
    assert all(item["exists"] and item["inside_write_domain"] for item in report["per_goods"])
    for outside in ("app/poison.py", "frontend/index.html", "docs/handoff/2026-09-17-human-gates.md"):
        assert domain_violations((outside,)) == [outside], outside
    for inside in ("scripts/r641_probe.py", "tests/test_r641_teeth.py", "docs/testing/r641-notes.md"):
        assert domain_violations((inside,)) == [], inside
