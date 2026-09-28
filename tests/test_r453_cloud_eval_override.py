"""R453 判据①＋④ · `deploy/compose.cloud-eval.yaml` 的形状钉、密钥钉与禁域钉。

判据原文（跟进单 §128 第一节）要的是三件事，每一件都得有牙，不能只是态度：
① 这枚 override 只覆盖 backend 的 `LOCAL_MODEL_BASE_URL`／`LOCAL_MODEL_API_KEY`／
   `LOCAL_MODEL_NAME` 与 `MODEL_CONTEXT_TOKENS`；密钥一律以 `${LOCAL_MODEL_API_KEY}` 形式从
   **进程环境**注入 —— 文件里出现任何密钥形状的字面量＝没收工；
④ 禁域：不碰 `deploy/.env.server`（业主文件）· 不碰 `docker-compose.yml` 本体 · 不碰
   `MODEL_MIN_ANSWER_TOKENS` 那枚 1536 · 不碰 `app/**`·`frontend/**` · 不碰在册量具
   `scripts/eval_transport_ask_v2.py`。这里的钉是「`git status` 盘面」而不是自述。
   红线只画在**本单的写入**上，不画在工作树的干净程度上：主树常年挂着
   `?? %SystemDrive%/...`、`?? -`、`?? .zcodeignore`、`?? 课程实践-.../` 这类永久脏项
   （删它们只归业主），并树那一刻还并存别的单的新文件。早先那枚「任何未跟踪条目都算
   越界」的钉钉错了量，09-28 验收退回（并进主树＝永久红）。现在的形状：声明过的交付清单
   逐枚在盘＋带本单签名的未跟踪条目必须归位写域（别人的单与业主垃圾一律不管）＋被跟踪
   文件走「在册件 M/D 钉」与「全集 sha256 基线（跑前／跑后逐枚等值）」，一律不依赖未跟踪态。
   🔴 摘牙一律在临时副本树（`shadow_repo`）里造漂移：09-28 本单一度往仓库原件
   `docker-compose.yml` 插空格做实验⇒ 越界退回（那格值一坏，每个容器的模型腿当场断，
   而且是运行时才炸的形状）。仓里 `tests/test_r253_no_test_rewrites_a_tracked_file.py`
   钉的就是「测试不许原地改写被跟踪文件」，本件的每枚反证跑完还要现读真树摘要自证没碰它。

底座那四条锚点（模型腿本来就是 OpenAI 兼容）也在本件里现读一遍：锚点漂了要停下报，
不许把「行号会漂」当成免检理由 —— 所以钉的是**符号在场**，行号只在失败消息里现算现打。

全部离线：读文件文本，不 import 产品代码、不起服务、不连库、不动容器。可失败钉见
`test_counter_evidence_*`：每把都把被测行为摘掉一次，红的必须是本件自己的钉。
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

OVERRIDE = REPO / "deploy" / "compose.cloud-eval.yaml"
BASE_COMPOSE = REPO / "docker-compose.yml"
PRODUCTION_OVERLAYS = (
    REPO / "deploy" / "docker-compose.server.yml",
    REPO / "deploy" / "docker-compose.tls.yml",
    REPO / "docker-compose.dev.yml",
)

#: 判据①点名的四枚，一枚不多一枚不少。
ALLOWED_KEYS = frozenset({
    "LOCAL_MODEL_BASE_URL",
    "LOCAL_MODEL_NAME",
    "LOCAL_MODEL_API_KEY",
    "MODEL_CONTEXT_TOKENS",
})

#: 只许「从进程环境注入且变量名与键名同名」这一种写法。
INJECTION = re.compile(r"^\$\{(?P<name>[A-Z0-9_]+):\?[^}]*\}$")

#: 判据④里点名的禁域。`git status` 盘面出现其中任何一枚的改动＝越界。
FORBIDDEN_PATHS = (
    "app",
    "frontend",
    "docker-compose.yml",
    "deploy/docker-compose.server.yml",
    "deploy/docker-compose.tls.yml",
    "deploy/.env.server.example",
    "deploy/.env.server",
    "scripts/eval_transport_ask_v2.py",
    "scripts/run_gate.py",
    "tests/test_evaluation_report.py",
    "pyproject.toml",
    "docs/testing",
)

#: 本单声明的交付清单（正账）：一枚不许缺，名下多出来的一枚必须先进清单。
DELIVERED_FILES = (
    "deploy/compose.cloud-eval.yaml",
    "scripts/eval_cloud_window_readout.py",
    "tests/test_r453_cloud_eval_override.py",
    "tests/test_r453_cloud_shape_caliber.py",
    "tests/test_r453_default_env_baseline.py",
    "tests/test_r453_nested_pytest_selection_guard.py",
)

#: 判据①写域三枚：两枚整文件＋一枚前缀（只有钉允许在同一前缀下长新枚）。
WRITE_DOMAIN_FILES = ("deploy/compose.cloud-eval.yaml", "scripts/eval_cloud_window_readout.py")
WRITE_DOMAIN_PREFIXES = ("tests/test_r453_",)
#: 旧钉（09-28 退回那枚）把两枚整文件也当「前缀」放过：`compose.cloud-eval.yaml.draft`
#: 因此漏网。本件按整文件等值收，留这份历史值只为反证能对照旧形状。
RETIRED_ALLOWED_PREFIXES = WRITE_DOMAIN_FILES + WRITE_DOMAIN_PREFIXES

#: 本单的签名：未跟踪条目名里带其中任何一枚，就是本单的手笔，必须归位到写域里。
TICKET_SIGNATURES = ("r453", "cloud_eval", "cloud_window", "compose.cloud-eval",
                     "eval_cloud_window")

#: 别人的单的编号（rNNN 而不是 r453）：带着别人编号的条目不归本钉管。
FOREIGN_TICKET = re.compile(r"(?<![\dA-Za-z])r(?!453)\d{3}(?!\d)")

#: 在册件（本单一枚都不许动的既有被跟踪文件）：M/D 钉与 sha 基线逐枚点名的就是这些。
REGISTERED_FILES = (
    "docker-compose.yml",
    "deploy/.env.server.example",
    ".env.example",
    "deploy/docker-compose.server.yml",
    "scripts/eval_transport_ask_v2.py",
    "scripts/run_gate.py",
    "tests/test_evaluation_report.py",
    "app/agents/nodes.py",
    "app/common/model_config.py",
    "app/common/model_handler.py",
    "pyproject.toml",
    "AGENTS.md",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def override_document() -> dict:
    return yaml.safe_load(read(OVERRIDE))


def backend_environment(document: dict) -> dict:
    services = document.get("services") or {}
    backend = services.get("backend") or {}
    return backend.get("environment") or {}


def secret_shaped_literals(text: str) -> list[str]:
    """密钥形状的字面量。先把 `${VAR:?...}` 注入位抹掉，剩下的才算字面量。

    三把尺：① `sk-` 这类已知密钥前缀打头的一串；② 长度 ≥20、字母与数字都有的连续 token
    （base64／随机 hex 的共同形状）—— 带下划线的标识符、带斜杠的路径、纯字母的散文词、
    纯数字的日期与全大写的 env 名都不算，否则注释里一句 `tests/test_r453_*` 就能把钉咬偏；
    ③ `Bearer` 后面跟一串。命中任何一把都按没收工处理。
    """
    bare = re.sub(r"\$\{[^}]*\}", " ", text)
    hits: list[str] = []
    for match in re.finditer(r"\bsk-[A-Za-z0-9_\-]{6,}", bare):
        hits.append("key-prefix literal: " + match.group(0)[:12] + "...")
    for match in re.finditer(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{10,}", bare):
        hits.append("bearer token: " + match.group(0)[:12] + "...")
    for token in re.findall(r"\b[A-Za-z0-9+/=]{20,}\b", bare):
        if "_" in token or token.isupper():
            continue
        digits = sum(ch.isdigit() for ch in token)
        letters = sum(ch.isalpha() for ch in token)
        if digits and letters and digits * 6 >= len(token):
            hits.append("random-shaped literal: " + token[:12] + "...")
    return hits


def external_hosts(text: str) -> list[str]:
    """写进文件的公网 URL 字面量。注入位里的 `${...}` 不是 URL，先把整段抹掉。"""
    bare = re.sub(r"\$\{[^}]*\}", " ", text)
    return [m.group(1) for m in re.finditer(r"https?://([A-Za-z0-9.\-]+)", bare)]


def inline_values(environment: dict) -> list[str]:
    """environment 里不是「进程环境注入」形态的键（＝把值写死在文件里）。"""
    bad = []
    for key, value in environment.items():
        if not isinstance(value, str) or not INJECTION.match(value):
            bad.append(key)
    return bad


def git_status_porcelain(root: Path = REPO) -> list[str]:
    """盘面现读。root 默认是真树；反证一律传影子根，不许在真树上造漂移。"""
    proc = subprocess.run(
        ["git", "-c", "core.quotePath=false", "status", "--porcelain",
         "--untracked-files=all"],
        cwd=str(root), capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, "取不到 git 盘面：" + proc.stderr[:200]
    return [line for line in proc.stdout.splitlines() if line.strip()]


def dirty_forbidden_paths(entries: list[str]) -> list[str]:
    """盘面里落到禁域的条目。未跟踪的新文件不算越界（禁域文件本来就在版本控制里）。"""
    dirty = []
    for line in entries:
        state, path = line[:2].strip(), line[3:].strip().replace("\\", "/")
        if state == "??":
            continue
        for forbidden in FORBIDDEN_PATHS:
            if path == forbidden or path.startswith(forbidden + "/"):
                dirty.append("%s %s" % (state, path))
                break
    return dirty


def untracked_paths(entries: list[str]) -> list[str]:
    """盘面里的未跟踪条目（只作为签名筛的输入，绝不拿来当越界判据）。"""
    return [line[3:].strip().replace("\\", "/") for line in entries if line[:2].strip() == "??"]


def inside_write_domain(path: str) -> bool:
    """写域归位判断：整文件必须逐字等值，只有 tests/test_r453_ 允许前缀匹配。"""
    return path in WRITE_DOMAIN_FILES or path.startswith(WRITE_DOMAIN_PREFIXES)


def ticket_signed_strays(entries: list[str]) -> list[str]:
    """带本单签名、却不落在写域三枚前缀里的未跟踪条目＝本单自己写歪了的手笔。

    别人的单（名里带 rNNN 而不是 r453）与业主侧永久垃圾一律不判：本钉的对象是「本单的
    写入归不归位」，不是「这棵树干净不干净」。
    """
    strays = []
    for path in untracked_paths(entries):
        if inside_write_domain(path):
            continue
        lowered = path.lower()
        if FOREIGN_TICKET.search(lowered):
            continue
        if any(sign in lowered for sign in TICKET_SIGNATURES):
            strays.append(path)
    return strays


def registered_modifications(entries: list[str]) -> list[str]:
    """在册件的 M/D/R/C/T 盘面，逐枚点名（git 自己比字节，autocrlf 不会造出假红）。"""
    hits = []
    for line in entries:
        state = line[:2].strip()
        if state == "??":
            continue
        raw = line[3:].strip().replace("\\", "/")
        for side in [part.strip() for part in raw.split("->")] or [raw]:
            if side in REGISTERED_FILES:
                hits.append("%s %s" % (state, side))
                break
    return hits


def tracked_paths(root: Path = REPO) -> list[str]:
    """被跟踪文件全集。core.quotePath=false 必须带：否则非 ASCII 路径会被转义成假缺失。"""
    proc = subprocess.run(
        ["git", "-c", "core.quotePath=false", "ls-files"],
        cwd=str(root), capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, "取不到被跟踪清单：" + proc.stderr[:200]
    return sorted(line for line in proc.stdout.splitlines() if line.strip())


def sha256_at(rel: str, root: Path = REPO) -> str:
    path = root / rel
    return "ABSENT" if not path.is_file() else hashlib.sha256(path.read_bytes()).hexdigest()


def tracked_manifest(root: Path = REPO) -> dict[str, str]:
    """全集逐枚 sha256（工作树字节）。实测 1277 枚约 0.1 s，够得起每轮跑两次。"""
    return {rel: sha256_at(rel, root) for rel in tracked_paths(root)}


def digest_of(manifest: dict[str, str]) -> str:
    """全集摘要：先把 (路径, 读数) 排序再拼，枚序不稳不许影响读数。"""
    blob = "".join("%s\t%s\n" % (rel, sha) for rel, sha in sorted(manifest.items()))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def manifest_offenders(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """跑前／跑后逐枚比对，漂了的点名并带上两枚读数前缀。"""
    offenders = []
    for rel in sorted(set(before) | set(after)):
        left = before.get(rel, "MISSING-AT-RUN-START")
        right = after.get(rel, "MISSING-AT-ASSERT")
        if left != right:
            offenders.append("%s %s->%s" % (rel, left[:16], right[:16]))
    return offenders


#: 真树的跑前读数：反证在影子根里造漂移时，用它证明真树一个字节都没被碰过。
RUN_START_TREE_SHA = digest_of(tracked_manifest(REPO))

#: 跑前读数：本件被 import 的那一刻（＝这一轮测试开跑之前）的全集摘要。
MANIFEST_AT_RUN_START = tracked_manifest()
DIGEST_AT_RUN_START = digest_of(MANIFEST_AT_RUN_START)


def symbol_line(path: Path, pattern: str) -> int | None:
    """现算符号所在行号，只用于失败消息与报告，绝不当断言的常数。"""
    for number, line in enumerate(read(path).splitlines(), start=1):
        if re.search(pattern, line):
            return number
    return None


# ------------------------------------------------------------------ 判据① 本体
def test_the_override_exists_and_parses_as_a_compose_fragment() -> None:
    assert OVERRIDE.is_file(), "缺件：deploy/compose.cloud-eval.yaml 没落盘"
    document = override_document()
    assert isinstance(document, dict) and document, "override 必须是能解析的 YAML 映射"


def test_it_overrides_the_backend_service_and_nothing_else() -> None:
    document = override_document()
    assert set(document) == {"services"}, "顶层只许 services，实测 %s" % sorted(document)
    assert set(document["services"]) == {"backend"}, (
        "判据①只管 backend；worker／scheduler／ollama 一起改就超出授权面")
    assert set(document["services"]["backend"]) == {"environment"}, (
        "backend 段只许 environment 一格；加 ports／volumes／restart 就是在改栈的形状")


def test_the_four_env_names_are_exactly_the_covered_set() -> None:
    environment = backend_environment(override_document())
    assert set(environment) == set(ALLOWED_KEYS), (
        "判据①点名四枚 env，多一枚就是越界（多的：%s，少的：%s）" % (
            sorted(set(environment) - ALLOWED_KEYS), sorted(ALLOWED_KEYS - set(environment))))


@pytest.mark.parametrize("forbidden_key", [
    "MODEL_MIN_ANSWER_TOKENS",
    "SCHEDULER_ENABLED",
    "VECTOR_DUAL_WRITE",
    "INDEX_BACKEND",
    "CORS_ALLOW_ORIGINS",
])
def test_forbidden_tunables_never_appear_in_the_override(forbidden_key: str) -> None:
    """1536 那枚、以及「顺手把读后端／调度也改了」那一类，一律不许进这页纸。"""
    assert forbidden_key not in backend_environment(override_document())
    assert not re.search(r"(?m)^\s*" + forbidden_key + r"\s*[:=]", read(OVERRIDE))


def test_every_value_is_a_process_environment_injection() -> None:
    environment = backend_environment(override_document())
    bad = inline_values(environment)
    assert not bad, "这些格把值写死在文件里，没有从进程环境注入：%s" % sorted(bad)
    for key, value in environment.items():
        match = INJECTION.match(value)
        assert match, "%s 不是 ${VAR:?...} 形态：%r" % (key, value)
        assert match.group("name") == key, "%s 注入的却是别枚变量：%s" % (key, match.group("name"))


def test_no_secret_shaped_literal_anywhere_in_the_file() -> None:
    hits = secret_shaped_literals(read(OVERRIDE))
    assert not hits, "判据①：文件里出现密钥形状字面量＝没收工。命中：%s" % hits


def test_the_override_ships_no_external_host_literal() -> None:
    assert not external_hosts(read(OVERRIDE)), (
        "override 里不许写死任何主机名：云端地址由开窗时的进程环境给，"
        "落进文件就成了一枚『默认指向外部』的口子（AGENTS.md：远程回退默认关闭）")


# ------------------------------------------------------------------ 反证钉（每把摘掉一次被测行为）
@pytest.mark.parametrize("fake", [
    "      LOCAL_MODEL_API_KEY: sk-abc123def456ghi789\n",
    "      LOCAL_MODEL_API_KEY: \"sk-live-9f8a7b6c5d4e3f2a1b\"\n",
    "      LOCAL_MODEL_API_KEY: d9f8a7b6c5e4d3f2a1b0c9d8e7f6a5b4\n",
])
def test_counter_evidence_a_secret_literal_turns_the_secret_guard_red(fake: str) -> None:
    """摘掉「密钥只从进程环境注入」这道行为 ⇒ 本件那枚钉必须当场红，否则它是空响。"""
    mutated = read(OVERRIDE) + fake
    assert secret_shaped_literals(mutated), "把密钥字面量塞进 override，检测器却没咬到"
    assert secret_shaped_literals(read(OVERRIDE)) == []


def test_counter_evidence_an_inline_value_turns_the_injection_guard_red() -> None:
    document = override_document()
    document["services"]["backend"]["environment"]["LOCAL_MODEL_API_KEY"] = "plain-inline-key"
    assert inline_values(backend_environment(document)) == ["LOCAL_MODEL_API_KEY"], (
        "把注入改成写死，形态钉却没咬到——那枚钉是空的")


@pytest.mark.parametrize("extra", ["MODEL_MIN_ANSWER_TOKENS", "SCHEDULER_ENABLED"])
def test_counter_evidence_a_fifth_env_key_turns_the_allowed_set_guard_red(extra: str) -> None:
    document = override_document()
    document["services"]["backend"]["environment"][extra] = "${%s:?mutant}" % extra
    keys = set(backend_environment(document))
    assert keys - ALLOWED_KEYS == {extra}, (
        "第五枚 env 加进来，允许集合钉必须把它点出来，实测差集 %s" % sorted(keys - ALLOWED_KEYS))


def test_counter_evidence_a_public_host_turns_the_host_guard_red() -> None:
    mutated = read(OVERRIDE).replace(
        "${LOCAL_MODEL_BASE_URL:?", "https://api.public-cloud.example.com/v1 ${LOCAL_MODEL_BASE_URL:?")
    assert external_hosts(mutated), "写死一个公网主机，主机钉却没咬到"
    assert external_hosts(read(OVERRIDE)) == []


def test_counter_evidence_a_wider_service_block_turns_the_shape_guard_red() -> None:
    document = override_document()
    document["services"]["worker"] = {"environment": {"LOCAL_MODEL_NAME": "${LOCAL_MODEL_NAME:?x}"}}
    assert set(document["services"]) - {"backend"} == {"worker"}, (
        "override 顺手把 worker 也指到云端，形状钉必须认出这一枚多出来的服务")


def test_counter_evidence_the_git_forbidden_path_guard_bites_on_a_dirty_app_tree() -> None:
    dirty = dirty_forbidden_paths([" M app/agents/nodes.py", "?? deploy/compose.cloud-eval.yaml"])
    assert dirty == ["M app/agents/nodes.py"], (
        "禁域被改（app/**）时盘面钉必须红；未跟踪的新文件不该被它误伤：%s" % dirty)


# ------------------------------------------------------------------ 判据④ 盘面（现取，不采信自述）
def test_forbidden_domain_files_are_unmodified_in_this_worktree() -> None:
    dirty = dirty_forbidden_paths(git_status_porcelain())
    assert not dirty, (
        "判据④禁域被动过：%s（app/**·frontend/**·docker-compose 本体·业主 env 样例·"
        "在册量具 eval_transport_ask_v2.py·评测集目录都不在本单写域）" % dirty)


def test_the_declared_delivery_list_is_all_on_disk() -> None:
    """交付清单是正账：声明过的逐枚必须在盘上；名下多出来的一枚必须先进清单。

    这条只看本单自己的名字（tests/test_r453_ 那一格），不看别人的单、不看业主的永久脏项。
    """
    missing = [rel for rel in DELIVERED_FILES if not (REPO / rel).is_file()]
    assert not missing, "声明过的交付件不在盘上：%s" % missing
    undeclared = [path for path in untracked_paths(git_status_porcelain())
                  if path.startswith("tests/test_r453_") and path not in DELIVERED_FILES]
    assert not undeclared, "本单名下多出一枚没进清单的钉：%s" % undeclared
    outside = [rel for rel in DELIVERED_FILES if not inside_write_domain(rel)]
    assert not outside, "交付清单里有不在写域内的路径（清单或写域漂了）：%s" % outside
    assert set(DELIVERED_FILES) == set(WRITE_DOMAIN_FILES) | {
        rel for rel in DELIVERED_FILES if rel.startswith("tests/test_r453_")}, (
        "写域两枚整文件与清单不一致：%s" % sorted(set(DELIVERED_FILES) ^ (
            set(WRITE_DOMAIN_FILES) | {r for r in DELIVERED_FILES if r.startswith("tests/test_r453_")})))


def test_no_ticket_signed_write_lands_outside_the_write_domain() -> None:
    """签名可辨是本单的手笔 ⇒ 必须落在写域三枚前缀里；别人的单与业主垃圾一律不管。"""
    strays = ticket_signed_strays(git_status_porcelain())
    assert not strays, "带本单签名的新文件长在写域之外：%s" % strays


def test_registered_in_book_files_carry_no_modification_or_deletion() -> None:
    """在册件零改动（M/D/R/C/T 逐枚点名）。判据对象是被跟踪态，与未跟踪垃圾无关。"""
    hits = registered_modifications(git_status_porcelain())
    assert not hits, "在册件被改动：%s" % hits


def test_the_tracked_sha256_baseline_is_unchanged_from_run_start_to_assert() -> None:
    """跑前（本件 import 那一刻）与跑后（断言此刻）各取一次全集摘要，逐枚等值。

    拦的是「这一轮里有人改了在册文件」，不是「这棵树别人也用过」：读数只跟 import 之后的
    自己比。全仓被跟踪件里没有任何一枚是被测试写到盘上的（影子树一律落 tmp_path，09-28 现
    扫：唯一五处写盘全在 tmp 影子根里），所以这条不会因别人的测试造出假红。
    """
    now = tracked_manifest()
    offenders = manifest_offenders(MANIFEST_AT_RUN_START, now)
    assert not offenders, (
        "跑前／跑后 sha256 基线不等值，被跟踪文件在这一轮里被改过：%s" % offenders[:8])
    assert digest_of(now) == DIGEST_AT_RUN_START, "逐枚没漂而全集摘要漂了：排序不稳，会漏报"


def test_the_sha_baseline_covers_enough_files_to_have_teeth() -> None:
    """基线钉不许空响：全集必须够大、在册件必须一枚枚在摘要里、摘要对枚序不敏感。"""
    absent = [rel for rel in REGISTERED_FILES if rel not in MANIFEST_AT_RUN_START]
    assert not absent, "在册件不在被跟踪全集里（清单漂了或它没进版本控制）：%s" % absent
    assert len(MANIFEST_AT_RUN_START) >= 1000, (
        "被跟踪全集只有 %d 枚，这枚钉近乎空响" % len(MANIFEST_AT_RUN_START))
    reversed_view = dict(reversed(list(MANIFEST_AT_RUN_START.items())))
    assert digest_of(reversed_view) == DIGEST_AT_RUN_START, "摘要跟着枚序漂了"
    assert re.fullmatch(r"[0-9a-f]{64}", DIGEST_AT_RUN_START), DIGEST_AT_RUN_START


# ------------------------------------------------------------------ 判据② 的栈面补充（默认腿不许被谁挪走）
def test_no_other_compose_surface_re_points_the_model_leg() -> None:
    """全栈里只有本单这枚 override 允许动模型腿，而且只以「从进程环境注入」的方式动。

    `docker-compose.yml` 必须把 backend 指在本机那一条腿上；生产／dev overlay 不许出现
    `LOCAL_MODEL_BASE_URL` —— 它们一出现，「远程回退默认关闭」这条就 quietly 破了。
    """
    surfaces = (BASE_COMPOSE,) + tuple(path for path in PRODUCTION_OVERLAYS if path.is_file())
    assert len(surfaces) >= 2, "对照面太少，这枚钉近乎空响：%s" % [p.name for p in surfaces]
    for path in surfaces:
        document = yaml.safe_load(read(path)) or {}
        services = document.get("services") or {}
        backend = services.get("backend") or {}
        environment = backend.get("environment") or {}
        if path == BASE_COMPOSE:
            assert environment.get("LOCAL_MODEL_BASE_URL") == "http://ollama:11434/v1", (
                "默认路径的模型腿不再指着本机那一条，判据②的前提作废")
        else:
            assert "LOCAL_MODEL_BASE_URL" not in environment, (
                "%s 挪动了模型腿的指向，而它不在本单授权面里" % path.name)


# ------------------------------------------------------------------ 底座锚点（现读，漂了就报）
def test_the_model_leg_anchors_the_ticket_relies_on_are_still_true() -> None:
    """判据的「换 env 不改架构」这句话靠四个符号；符号没了，本单前提就不成立。"""
    nodes = REPO / "app" / "agents" / "nodes.py"
    config = REPO / "app" / "common" / "model_config.py"
    handler = REPO / "app" / "common" / "model_handler.py"
    checks = (
        (nodes, r"^from langchain_openai import ChatOpenAI", "ChatOpenAI 导入"),
        (nodes, r'"local-openai-compatible"', "provider 判定"),
        (config, r'os\.getenv\("LOCAL_MODEL_BASE_URL"\)', "LOCAL_MODEL_BASE_URL 读点"),
        (config, r'os\.getenv\("LOCAL_MODEL_NAME"\)', "LOCAL_MODEL_NAME 读点"),
        (config, r'os\.getenv\("LOCAL_MODEL_API_KEY", "local"\)', "LOCAL_MODEL_API_KEY 缺省 local"),
        (handler, r"class _NativeChatUnsupported", "原生腿不支持这一支"),
        (handler, r"except _NativeChatUnsupported as exc:", "退回兼容腿那一支"),
    )
    missing = [label for path, pattern, label in checks if symbol_line(path, pattern) is None]
    assert not missing, "判据锚点已漂（符号不在）：%s" % missing



# ------------------------------------------------------------------ 盘面钉自己的反证（09-28 返工补）
#: 被摘掉的那半条旧钉（把任何未跟踪条目都判成越界）。留在文件里只为一件事：让反证能证明
#: 新形状是**有意**不收环境垃圾，而不是漏写。守卫力由签名筛＋在册件 M/D＋sha 基线三处接住。
def retired_shape_extras(entries: list[str]) -> list[str]:
    extras = []
    for path in untracked_paths(entries):
        if not path.startswith(RETIRED_ALLOWED_PREFIXES):
            extras.append(path)
    return extras


SHADOW_SEED_FILES = (
    "docker-compose.yml",
    "scripts/eval_transport_ask_v2.py",
    "tests/test_evaluation_report.py",
    "pyproject.toml",
)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, "影子根里 git %s 失败：%s" % (" ".join(args), proc.stderr[:200])
    return proc.stdout


def shadow_repo(tmp_path: Path) -> Path:
    """临时副本树：git init 之后按字节带上几枚在册件，漂移只许在这棵树里造。

    09-28 本单一度拿真树原件做摘牙实验（往 docker-compose.yml 插空格）⇒ 越界退回。
    仓里那枚 tests/test_r253_no_test_rewrites_a_tracked_file.py 钉的就是这条规矩：测试不许
    原地改写被跟踪文件。本件的读数一律走影子根，真树只读，红数照样取得出来。
    """
    root = tmp_path / "shadow-tree"
    root.mkdir(parents=True, exist_ok=True)
    for rel in SHADOW_SEED_FILES:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO / rel).read_bytes())
    _git(root, "init", "-q", "--initial-branch", "main")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=r453-shadow", "-c", "user.email=r453@shadow.invalid",
         "commit", "-q", "-m", "shadow seed")
    return root

#: 主树常年挂着的永久脏项（业主侧）＋并树那一刻并存的别人的单：本钉一律不管。
ENVIRONMENT_NOISE = [
    "?? %SystemDrive%/ProgramData/Microsoft/Windows/Caches/IndexedDB.db",
    "?? -",
    "?? .zcodeignore",
    "?? 课程实践-企业智脑/README.md",
    "?? scripts/eval_window_planner.py",
    "?? docs/testing/bank-shape-subset-30.jsonl",
    "?? docs/testing/shape-window-readout-2026-09-28.md",
    "?? tests/test_r454_window_planner.py",
    "?? docs/handoff/2026-09-28-board.md",
]


@pytest.mark.parametrize("entry", ENVIRONMENT_NOISE)
def test_counter_evidence_environment_noise_is_not_this_pins_business(entry: str) -> None:
    """别人的单与业主垃圾不许红：旧钉正是把它们判红才退回的（并树即永久红）。"""
    assert ticket_signed_strays([entry]) == [], "%s 不是本单的手笔，签名筛却把它判越界" % entry
    assert retired_shape_extras([entry]), (
        "这枚噪声旧钉会判越界、新钉不收——若旧钉读数也空了，本反证就是空响")


@pytest.mark.parametrize("entry,sign", [
    ("?? docs/testing/r453-shadow.md", "r453"),
    ("?? deploy/.env.server.r453.bak", "r453"),
    ("?? scripts/eval_cloud_window_readout.wip.py", "eval_cloud_window"),
    ("?? scripts/cloud_eval_probe.py", "cloud_eval"),
    ("?? deploy/compose.cloud-eval.yaml.draft", "compose.cloud-eval"),
])
def test_counter_evidence_a_signed_stray_outside_the_write_domain_is_named(entry: str, sign: str) -> None:
    """本单的手笔写歪一处，签名筛必须点名——这条就是旧钉原来想拦的那件事。"""
    path = entry[3:].strip().replace("\\", "/")
    assert ticket_signed_strays([entry]) == [path], (
        "带 %s 签名的新文件落在写域之外却没被点名" % sign)


def test_counter_evidence_an_undeclared_extra_nail_is_named() -> None:
    """名下多一枚没进清单的 test_r453_* ⇒ 清单钉点名；清单里那几枚不许被它误伤。"""
    for rel in DELIVERED_FILES:
        if rel.startswith("tests/test_r453_"):
            assert [p for p in untracked_paths(["?? " + rel])
                    if p.startswith("tests/test_r453_") and p not in DELIVERED_FILES] == []
    stray = "?? tests/test_r453_undeclared_extra.py"
    named = [p for p in untracked_paths([stray])
             if p.startswith("tests/test_r453_") and p not in DELIVERED_FILES]
    assert named == ["tests/test_r453_undeclared_extra.py"], (
        "多一枚没声明的钉，清单钉却没点名：%s" % named)


def test_counter_evidence_a_dirty_instrument_is_named_by_the_registered_guard() -> None:
    """在册量具被顺手改一格 ⇒ 在册件 M/D 钉点名；本单自己的未跟踪新文件不许被它误伤。"""
    entries = [" M scripts/eval_transport_ask_v2.py", "?? tests/test_r453_cloud_eval_override.py"]
    assert registered_modifications(entries) == ["M scripts/eval_transport_ask_v2.py"], (
        "在册件被改了却没点名，或者未跟踪的新文件被误伤了")


def test_counter_evidence_a_touched_tracked_file_moves_the_baseline() -> None:
    """sha 基线摘牙：改一枚在册件的读数 ⇒ 逐枚比对必须点名它，全集摘要必须跟着漂。"""
    victim = "docker-compose.yml"
    assert victim in MANIFEST_AT_RUN_START, "在册件不在全集摘要里，这枚反证空响"
    mutated = dict(MANIFEST_AT_RUN_START)
    mutated[victim] = hashlib.sha256(b"docker-compose.yml plus one stray space").hexdigest()
    offenders = manifest_offenders(MANIFEST_AT_RUN_START, mutated)
    assert len(offenders) == 1 and offenders[0].startswith(victim + " "), offenders
    assert digest_of(mutated) != DIGEST_AT_RUN_START, "逐枚漂了而摘要没漂：这枚钉会漏报"


def test_counter_evidence_a_deleted_tracked_file_is_named_not_shrugged_off() -> None:
    """被跟踪文件被删（ABSENT）同样要点名，不许当成「少一枚」混过去。"""
    mutated = dict(MANIFEST_AT_RUN_START)
    victim = "app/common/model_handler.py"
    mutated[victim] = "ABSENT"
    offenders = manifest_offenders(MANIFEST_AT_RUN_START, mutated)
    assert len(offenders) == 1 and victim in offenders[0], offenders
    assert registered_modifications([" D " + victim]) == ["D " + victim], "删除未被在册件点名"


def test_counter_evidence_a_drift_in_a_shadow_copy_turns_the_disk_pins_red(tmp_path: Path) -> None:
    """摘牙的正确形状：在影子副本树里往 docker-compose.yml 插一格 ⇒ 盘面三枚各自点名。

    真树只读：这一形跑完，真树的全集摘要必须与跑前逐字相等——红要红在副本的漂移上，
    不许红在「我把仓库原件改了」上（09-28 越界那一笔换成的就是这个形）。
    """
    root = shadow_repo(tmp_path)
    assert registered_modifications(git_status_porcelain(root)) == [], "影子根一开就脏，反证空响"
    before = tracked_manifest(root)
    victim = "docker-compose.yml"
    original = (root / victim).read_bytes()
    drifted = original.replace(b"      LOCAL_MODEL_BASE_URL: http://ollama:11434/v1",
                               b"      LOCAL_MODEL_BASE_URL: http://ollama:11434 /v1", 1)
    assert drifted != original, "影子根里那一格没插进空格：这份副本与判据②的锚点漂了"
    (root / victim).write_bytes(drifted)
    entries = git_status_porcelain(root)
    assert registered_modifications(entries) == ["M " + victim], registered_modifications(entries)
    assert dirty_forbidden_paths(entries) == ["M " + victim], dirty_forbidden_paths(entries)
    offenders = manifest_offenders(before, tracked_manifest(root))
    assert len(offenders) == 1 and offenders[0].startswith(victim + " "), offenders
    assert digest_of(before) != digest_of(tracked_manifest(root)), "逐枚漂了而摘要没漂：会漏报"
    assert ticket_signed_strays(entries) == [], "被跟踪文件的改动不归签名筛管，各钉各的面"
    assert digest_of(tracked_manifest(REPO)) == RUN_START_TREE_SHA, (
        "反证说是在影子根里造漂移，真树却被碰脏了——这正是不许拿原件做实验的理由")


def test_counter_evidence_a_shadow_tree_full_of_foreign_junk_stays_green(tmp_path: Path) -> None:
    """影子根里造一堆无关未跟踪条目（业主永久脏项＋别人的单）⇒ 一枚都不许红。

    这正是 09-28 退回那枚错形的病灶：它把这些都判成越界，并进主树就是永久红。
    """
    root = shadow_repo(tmp_path)
    junk = (
        "%SystemDrive%/ProgramData/Microsoft/Windows/Caches/IndexedDB.db",
        "-",
        ".zcodeignore",
        "课程实践-企业智脑/README.md",
        "tests/test_r454_window_planner.py",
        "scripts/eval_window_planner.py",
        "docs/testing/bank-shape-subset-30.jsonl",
        "docs/testing/shape-window-readout-2026-09-28.md",
    )
    for rel in junk:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("别人的手笔，与本单无关\n", encoding="utf-8")
    entries = git_status_porcelain(root)
    seen = untracked_paths(entries)
    assert len(seen) == len(junk), "影子根没造起这 %d 枚噪声，实测 %s" % (len(junk), seen)
    assert ticket_signed_strays(entries) == [], ticket_signed_strays(entries)
    assert registered_modifications(entries) == [], registered_modifications(entries)
    assert manifest_offenders(tracked_manifest(root), tracked_manifest(root)) == []
    assert digest_of(tracked_manifest(REPO)) == RUN_START_TREE_SHA, "真树被这枚反证碰过"
    flagged = retired_shape_extras(entries)
    assert len(flagged) == len(junk), (
        "旧钉本该把这 %d 枚噪声全判越界，读不满说明这枚反证是空响：%s" % (len(junk), flagged))
