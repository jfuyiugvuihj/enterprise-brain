"""R453 判据② · 默认路径零影响：sha 基线钉＋零引用钉＋docker 交叉钉。

判据原文：不带 `-f` 时 backend 的 env 集合必须与今天**逐格相同**，做成 sha 基线钉。
这里钉了两把尺，一把不够：
① 名集合 sha —— 少一格、多一格、改名，都当场漂；
② 名值配对 sha —— 只改值（「顺手把默认也指到云端」那一类）在第一把尺下是**看不见**的，
   第二把尺盯的就是它。两把都对 `docker-compose.yml` 里 backend 那一段静态渲染取数，
   渲染规则＝YAML `<<` 合并后的 `environment` 键，值原样参与（compose 文件里全是
   `${VAR:?…}`／`${VAR:-…}` 形态，没有密钥）。

🔴 这台机的 docker 可能在跑也可能没在跑，所以：
- 静态渲染两把尺**不依赖 daemon**，任何时候都真跑；
- `docker compose config` 只做**文件渲染**，不建容器、不起服务，用作交叉钉；不可用时
  当场 `skip` 并把原因打出来，绝不当成通过。

`deploy/.env.server` 是业主文件（gitignore 里，工作树通常没有）：本件只读它的**键名**，
一个值都不读、不打印；文件不在场时第二组基线明写 skip。
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

BASE_COMPOSE = REPO / "docker-compose.yml"
OVERRIDE = REPO / "deploy" / "compose.cloud-eval.yaml"
DEPLOYMENT_ENV = REPO / "deploy" / ".env.server"
SERVICE = "backend"

#: 判据①点名的四枚。override 只许动它们，`-f` 那一路加进来的名字也只能是它们。
FOUR = frozenset({
    "LOCAL_MODEL_BASE_URL",
    "LOCAL_MODEL_NAME",
    "LOCAL_MODEL_API_KEY",
    "MODEL_CONTEXT_TOKENS",
})

#: 默认路径不许引用这枚 override 的任何纸面。
DEFAULT_SURFACES = (
    BASE_COMPOSE,
    REPO / "docker-compose.dev.yml",
    REPO / "deploy" / "docker-compose.server.yml",
    REPO / "deploy" / "docker-compose.tls.yml",
    REPO / "deploy" / ".env.server.example",
    REPO / ".env.example",
    REPO / "deploy" / "README.server.md",
)

#: 09-28 在基点上现取的基线（渲染口径见模块 docstring；改默认路径＝连这两枚一起改口）。
COMPOSE_DECLARED_NAMES_SHA = "053969b82c552e6a6089240f775b21404326d4e21d88f2a875e6d97702be973e"
COMPOSE_DECLARED_PAIRS_SHA = "e88f4feaf54cbe73c26994628916347b81720d07dd58a406cb011eea7aba1c32"

#: 业主 env 键集在场时的完整名集合基线（09-28 从主树 deploy/.env.server 现取，只取键名）。
EFFECTIVE_NAMES_SHA_WITH_DEPLOYMENT_ENV = "febad196851e250a5c4422c8bb6f9ac376101abfdbb4c42f1da8395449a44d0a"

ENV_ASSIGNMENT = re.compile(r"^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=")


def sha256_of(lines) -> str:
    canonical = "\n".join(sorted(lines)).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def env_file_names(path: Path) -> set[str]:
    """读一枚 env 文件的**键名**。值一概不看、不打印、不参与断言。"""
    names = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = ENV_ASSIGNMENT.match(line)
        if match:
            names.add(match.group(1))
    return names


def service_environment(*documents: dict) -> dict:
    """按 compose 的覆盖次序合并 backend 的 environment（后一枚赢同名键）。"""
    merged: dict[str, str] = {}
    for document in documents:
        service = (document.get("services") or {}).get(SERVICE) or {}
        environment = service.get("environment") or {}
        for key, value in environment.items():
            merged[key] = "" if value is None else str(value)
    return merged


def service_env_files(*documents: dict) -> list[str]:
    files: list[str] = []
    for document in documents:
        service = (document.get("services") or {}).get(SERVICE) or {}
        for entry in service.get("env_file") or []:
            files.append(str(entry.get("path") if isinstance(entry, dict) else entry))
    return files


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def static_render(project_dir: Path, compose_paths) -> dict:
    """静态渲染：compose 声明的 env（名与值）＋ env_file 指到的键名。

    compose 语义里 `environment` 赢过 `env_file`，但**名集合**是两者的并集，容器实际拿到的
    就是并集；`docker compose config` 也是这么把 env_file 摊进 environment 的（09-28 实测）。
    """
    documents = [load(path) for path in compose_paths]
    environment = service_environment(*documents)
    declared_names = set(environment)
    resolved: dict[str, bool] = {}
    env_names: set[str] = set()
    for reference in service_env_files(*documents):
        target = (project_dir / reference).resolve()
        if target.is_file():
            resolved[reference] = True
            env_names |= env_file_names(target)
        else:
            resolved[reference] = False
    return {
        "declared_names": declared_names,
        "declared_pairs": ["%s=%s" % (key, value) for key, value in environment.items()],
        "env_files": resolved,
        "env_file_names": env_names,
        "effective_names": declared_names | env_names,
    }


def names_sha(lines) -> str:
    return sha256_of(lines)


def docker_compose_reason() -> str | None:
    """返回不可用的原因（None＝可用）。判据不许把「跑不起来」写成通过。"""
    try:
        proc = subprocess.run(["docker", "compose", "version"],
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return "docker compose 取不到：%r" % (exc,)
    if proc.returncode != 0:
        return "docker compose version rc=%s：%s" % (
            proc.returncode, (proc.stderr or proc.stdout).strip()[:200])
    return None


def docker_backend_env_names(project_dir: Path, compose_paths, env_file: str,
                             shell_env=None) -> list[str]:
    cmd = ["docker", "compose", "--env-file", env_file]
    for path in compose_paths:
        cmd += ["-f", str(Path(path).relative_to(project_dir))]
    cmd += ["config", "--format", "json"]
    # 只在这四枚上盖住进程环境，其余照原样带过去：把 env 整体换掉会让 docker 找不到
    # 自己的 compose 插件，报一口「unknown flag」假账（09-28 本树踩过）。
    env = dict(os.environ)
    env.update({"LOCAL_MODEL_BASE_URL": "https://cloud.invalid/v1",
                "LOCAL_MODEL_NAME": "cloud-model",
                "LOCAL_MODEL_API_KEY": "operator-shell-value",
                "MODEL_CONTEXT_TOKENS": "32768"})
    env.update(shell_env or {})
    proc = subprocess.run(cmd, cwd=str(project_dir), capture_output=True, text=True,
                          encoding="utf-8", env=env)
    assert proc.returncode == 0, "docker compose config rc=%s：%s" % (
        proc.returncode, proc.stderr.strip()[:400])
    rendered = json_of(proc.stdout)["services"][SERVICE]["environment"]
    return sorted(rendered)


def json_of(text: str) -> dict:
    import json as _json
    return _json.loads(text)


def sandbox(compose_paths=(BASE_COMPOSE,)) -> tuple[Path, list[Path]]:
    """把 compose 树复制到 tmp，配一枚**只含假值**的 deploy/.env.server 做语义对照。

    交叉钉要证的是「本件的静态渲染＝compose 自己的渲染」，那跟业主文件里的真值无关，
    所以这里用假值文件；真值在场时的对照另有专门一枚用例。
    """
    tmp = Path(tempfile.mkdtemp(prefix="r453-"))
    (tmp / "deploy").mkdir(parents=True, exist_ok=True)
    copies = []
    for source in compose_paths:
        target = tmp / source.name if source.parent == REPO else tmp / "deploy" / source.name
        shutil.copyfile(source, target)
        copies.append(target)
    (tmp / "deploy" / ".env.server").write_text(
        "POSTGRES_USER=u\nPOSTGRES_PASSWORD=p\nREDIS_PASSWORD=r\n"
        "EMBEDDING_DIMENSION=768\nEMBEDDING_MODEL=m\n"
        "CORS_ALLOW_ORIGINS=http://127.0.0.1:8001\n"
        "LOCAL_MODEL_NAME=envfile-model\nLOCAL_MODEL_API_KEY=envfile-key\n"
        "LOCAL_MODEL_BASE_URL=http://ollama:11434/v1\nMODEL_CONTEXT_TOKENS=4096\n",
        encoding="utf-8")
    return tmp, copies


# ------------------------------------------------------------------ ② 之静态基线（不依赖 daemon）
def test_the_default_backend_env_name_set_is_the_pinned_baseline() -> None:
    render = static_render(REPO, (BASE_COMPOSE,))
    assert names_sha(render["declared_names"]) == COMPOSE_DECLARED_NAMES_SHA, (
        "默认路径 backend 的 env 名集合漂了：现在的名集=%s" % sorted(render["declared_names"]))


def test_the_default_backend_env_name_value_pairs_are_the_pinned_baseline() -> None:
    """值也钉：把默认那三条改指云端，名集合不变，只有这一把尺咬得住。"""
    render = static_render(REPO, (BASE_COMPOSE,))
    assert names_sha(render["declared_pairs"]) == COMPOSE_DECLARED_PAIRS_SHA, (
        "默认路径 backend 的 env 名值配对漂了（有人顺手改了默认指向？）")


def test_the_default_leg_still_reads_the_local_model_server() -> None:
    environment = service_environment(load(BASE_COMPOSE))
    assert environment["LOCAL_MODEL_BASE_URL"] == "http://ollama:11434/v1"
    assert environment["OLLAMA_BASE_URL"] == "http://ollama:11434"


def test_no_default_surface_mentions_the_cloud_override() -> None:
    """默认路径的每一页纸都必须认不出这枚 override（与反证钉共用同一把检测器）。"""
    for path in DEFAULT_SURFACES:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig")
        assert not mentions_override(text), (
            "%s 引用了云端 override，默认路径就不再是默认路径" % path.name)
        if path.suffix in (".yml", ".yaml"):
            assert not compose_includes_override(text), (
                "%s 里有 include 段：它会把 override 自动吸进默认路径" % path.name)


def test_the_effective_name_set_baseline_when_the_deployment_env_file_is_present() -> None:
    if not DEPLOYMENT_ENV.is_file():
        pytest.skip(
            "deploy/.env.server 不在本工作树（业主文件，gitignore 之外不入树）："
            "有效名集合基线只能在有它的树上核，这里明写 skip，不当成通过")
    render = static_render(REPO, (BASE_COMPOSE,))
    assert all(render["env_files"].values()), "env_file 声明了却取不到：%s" % render["env_files"]
    assert names_sha(render["effective_names"]) == EFFECTIVE_NAMES_SHA_WITH_DEPLOYMENT_ENV, (
        "业主 env 的键集变了 ⇒ 默认路径的有效 env 集合变了，需要重新对表并显式改口")


# ------------------------------------------------------------------ ② 之 docker 交叉钉
def test_docker_render_matches_the_static_render_for_the_default_path() -> None:
    reason = docker_compose_reason()
    if reason:
        pytest.skip("docker 不可用，交叉钉不成立（不当成通过）：%s" % reason)
    tmp, copies = sandbox()
    got = docker_backend_env_names(tmp, copies, "deploy/.env.server")
    expected = sorted(static_render(tmp, tuple(copies))["effective_names"])
    assert got == expected, (
        "静态渲染与 compose 自己渲染的 backend env 名集合不一致：docker=%s 静态=%s" % (got, expected))


def test_docker_render_with_the_override_adds_no_name_and_moves_only_the_four() -> None:
    reason = docker_compose_reason()
    if reason:
        pytest.skip("docker 不可用，交叉钉不成立（不当成通过）：%s" % reason)
    tmp, copies = sandbox()
    shutil.copyfile(OVERRIDE, tmp / "deploy" / OVERRIDE.name)
    override_path = tmp / "deploy" / OVERRIDE.name
    default_names = docker_backend_env_names(tmp, copies, "deploy/.env.server")
    window_names = docker_backend_env_names(tmp, copies + [override_path], "deploy/.env.server")
    assert set(window_names) - set(default_names) <= FOUR, (
        "开窗那一路冒出了第四枚之外的名字：%s" % sorted(set(window_names) - set(default_names)))
    assert set(default_names) - set(window_names) == set(), (
        "加 override 反而让默认格消失了：%s" % sorted(set(default_names) - set(window_names)))
    static = static_render(tmp, tuple(copies) + (override_path,))
    assert sorted(static["effective_names"]) == window_names, "静态渲染没算上 override 的那四枚"


def test_docker_render_with_the_real_deployment_env_file_matches_the_static_effective_set() -> None:
    """业主 env 在场时，用 compose 自己的解析核本件的键名解析器（只比名，不比值）。"""
    if not DEPLOYMENT_ENV.is_file():
        pytest.skip("deploy/.env.server 不在本树（业主文件不入树），这枚对照无从取数，明写 skip")
    reason = docker_compose_reason()
    if reason:
        pytest.skip("docker 不可用，交叉钉不成立（不当成通过）：%s" % reason)
    got = docker_backend_env_names(REPO, (BASE_COMPOSE,), "deploy/.env.server")
    expected = sorted(static_render(REPO, (BASE_COMPOSE,))["effective_names"])
    assert got == expected, (
        "键名解析器与 compose 不一致：docker=%s 静态=%s" % (
            sorted(set(got) ^ set(expected)), "对称差见前"))


def test_the_override_itself_declares_no_env_file_and_no_new_service() -> None:
    document = load(OVERRIDE)
    assert service_env_files(document) == [], (
        "override 里另起 env_file 就等于把业主的键集换掉，判据②的基线作废")
    assert set(document["services"]) == {SERVICE}


# ------------------------------------------------------------------ 反证钉（tmp 里改，不动树上的在册件）
def mentions_override(text: str) -> bool:
    """这一页纸有没有点名这枚 override（任何形态：-f、注释里的引用、脚本里的硬编码）。"""
    return "compose.cloud-eval" in text


def compose_includes_override(text: str) -> bool:
    """compose 文件的 include 段：它会把 override 自动吸进默认路径，一个字都不用写 -f。"""
    return bool(re.search(r"(?m)^\s*include\s*:", text))


def default_path_pulls_in_the_override(text: str) -> bool:
    """默认路径被污染的两种方式，合成一把检测器——反证钉与在册钉共用它，不分两套。"""
    return mentions_override(text) or compose_includes_override(text)


def test_counter_evidence_an_include_in_the_base_breaks_the_default_isolation() -> None:
    """把 override 挂进默认路径（include）⇒ 隔离钉必须认出来，在册那枚基线则一动不动。"""
    shipped = BASE_COMPOSE.read_text(encoding="utf-8-sig")
    assert not default_path_pulls_in_the_override(shipped), (
        "今天的 docker-compose.yml 就已经把 override 吸进默认路径了，判据②前提不成立")
    mutated = shipped + "\ninclude:\n  - deploy/compose.cloud-eval.yaml\n"
    assert default_path_pulls_in_the_override(mutated), (
        "摘掉隔离判据的形状：include 挂上去了，检测器却没咬到")


def test_counter_evidence_a_cloud_default_moves_the_pairs_sha_but_not_the_names_sha() -> None:
    """「顺手把默认也指到云端」：名集合不动、值动——只有配对尺咬得住。"""
    tmp, copies = sandbox()
    original = copies[0].read_text(encoding="utf-8")
    mutated = original.replace("LOCAL_MODEL_BASE_URL: http://ollama:11434/v1",
                               "LOCAL_MODEL_BASE_URL: https://cloud.invalid/v1")
    assert mutated != original, "锚文本没命中，反证不成立"
    copies[0].write_text(mutated, encoding="utf-8")
    before = static_render(REPO, (BASE_COMPOSE,))
    after = static_render(tmp, tuple(copies))
    assert names_sha(after["declared_names"]) == COMPOSE_DECLARED_NAMES_SHA, (
        "这把尺本来就看不见值改动——所以配对钉不是可选的")
    assert names_sha(after["declared_pairs"]) != names_sha(before["declared_pairs"])
    assert names_sha(before["declared_pairs"]) == COMPOSE_DECLARED_PAIRS_SHA


def test_counter_evidence_a_renamed_env_cell_moves_the_names_sha() -> None:
    tmp, copies = sandbox()
    original = copies[0].read_text(encoding="utf-8")
    mutated = original.replace("OLLAMA_BASE_URL: http://ollama:11434",
                               "OLLAMA_BASE_URLX: http://ollama:11434")
    assert mutated != original
    copies[0].write_text(mutated, encoding="utf-8")
    assert names_sha(static_render(tmp, tuple(copies))["declared_names"]) != COMPOSE_DECLARED_NAMES_SHA
    assert names_sha(static_render(REPO, (BASE_COMPOSE,))["declared_names"]) == COMPOSE_DECLARED_NAMES_SHA


def test_counter_evidence_an_extra_env_name_in_the_override_is_not_four_only() -> None:
    """第五枚 env 混进 override ⇒ 「只动四枚」那把尺必须只报出它，不报别的。"""
    shipped = service_environment(load(BASE_COMPOSE), load(OVERRIDE))
    document = load(OVERRIDE)
    #: 拿判据④点名的那枚 1536 当探针：它在默认路径里根本不存在，加进来必须只报出它自己。
    extra = "MODEL_MIN_ANSWER_TOKENS"
    assert extra not in service_environment(load(BASE_COMPOSE)), (
        "探针失效：默认路径已经声明了 %s，这枚反证就无从分辨" % extra)
    document["services"][SERVICE]["environment"][extra] = "${%s:?mutant}" % extra
    mutant = service_environment(load(BASE_COMPOSE), document)
    assert set(mutant) - set(shipped) == {extra}, (
        "多出来的是这枚吗？实测 %s" % sorted(set(mutant) - set(shipped)))
    assert names_sha(["%s=%s" % kv for kv in mutant.items()]) != names_sha(
        ["%s=%s" % kv for kv in shipped.items()]), "配对尺也必须跟着漂"
    assert FOUR <= set(shipped), "在册四枚本身都得在合并结果里"
