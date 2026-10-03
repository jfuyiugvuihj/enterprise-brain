"""R596 判据③：后端镜像自带那四枚 postgres 客户端工具——**静态**证明。

R587 在生产容器里逐枚问过 ``command -v psql`` / ``pg_dump`` / ``pg_restore`` / ``pg_dumpall``，
四枚全部 MISSING，而 PG 侧 ``SELECT version()`` 是 ``PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2)``。
⇒ 任何走 subprocess 调 ``pg_*`` 的备份/恢复路径在这台机上**结构性跑不起来**，不是参数没配好。

本文件因此一律只读文本，一次容器都不碰：把"某一次 ``command -v`` 在容器里跑得通"写成常驻
判据，就是 R593 刚治过的那枚病（一次演练当性质）。要判的性质是"**镜像里装的是哪一枚包、
大版本对不对**"，这个只在 Dockerfile 里，也在 Dockerfile 里就够。

R608 更正（10-03）：镜像里的客户端从 PGDG 的 16 换成 Debian 归档里的 17（PGDG 在这台机与任何
客户内网都取不到，重建当场死），钉的不变量随之由「大版本相等」改成「不低于服务端、只装一枚、不用
metapackage」。文件名保留 R596 那枚是为了不把历史账撕开——它现在守的是那四枚工具与那条不变量。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

from scripts import backup_database as backup_module
from scripts import restore_database as restore_module

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE = ROOT / "docker-compose.yml"

#: R587 在生产容器里逐枚问过的那四枚；postgresql-client-<major> 就是交这四枚的包。
EXPECTED_TOOLS = ("psql", "pg_dump", "pg_restore", "pg_dumpall")
_FLAGS = re.compile(r"^--?\S*")


def _dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _instructions() -> list[str]:
    """把续行拼回一整枚指令，并剥掉注释行：判的是装了什么，不是散文提了什么。"""
    joined: list[str] = []
    buffer = ""
    for line in _dockerfile_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if not buffer:
                continue
        buffer += (" " + stripped).strip()
        if stripped.endswith("\\"):
            buffer = buffer[:-1]
            continue
        joined.append(buffer)
        buffer = ""
    if buffer:
        joined.append(buffer)
    return joined


#: 具名 build arg 的取值：R608 之后装的那一枚写成 postgresql-client-${PG_CLIENT_MAJOR}，
#: 包名里带着 arg 名，所以先把 ARG name=default 读出来代进去，才谈得上"数字写在文件里"。
def _build_arg_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for instruction in _instructions():
        matched = re.match(r"^ARG\s+(\w+)=(\S+)$", instruction)
        if matched:
            values[matched.group(1)] = matched.group(2)
    return values


def _resolve_args(token: str) -> str:
    for name, value in _build_arg_values().items():
        token = token.replace("${" + name + "}", value)
    return token



def _installed_packages() -> list[str]:
    """所有 ``apt-get install`` 真吃进去的包名（标志与 ``$opts`` 一律剥掉）。"""
    packages: list[str] = []
    for instruction in _instructions():
        for chunk in instruction.split("apt-get install"):
            if chunk is instruction:
                continue
            for token in chunk.replace(";", " ").split():
                if not token or _FLAGS.match(token) or token.startswith("$"):
                    continue
                packages.append(_resolve_args(token))
    return packages


def _client_major_in_image() -> str:
    majors = {name.rsplit("-", 1)[1] for name in _installed_packages()
              if name.startswith("postgresql-client")}
    assert len(majors) == 1, f"镜像里出现了几枚 postgresql-client 大版本：{sorted(majors)}"
    return majors.pop()


def _server_major_in_the_stack() -> str:
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    image = services["postgres"]["image"]
    matched = re.search(r"pg(\d+)$", image)
    assert matched, f"compose 里的 postgres 镜像名取不出大版本：{image}"
    return matched.group(1)


# ---------------------------------------------------------------------------
# 判据③：包在、大版本对得上、不带第二枚客户端
# ---------------------------------------------------------------------------

def test_the_image_installs_a_version_pinned_postgresql_client() -> None:
    packages = _installed_packages()

    pinned = [name for name in packages if re.fullmatch(r"postgresql-client-\d+", name)]
    assert pinned, packages
    assert "postgresql-client" not in packages, (
        "装了不带版本的 metapackage：它解析成发行版此刻顺手带的那一枚，那个数字不写在 Dockerfile 里")


def test_the_client_major_is_not_older_than_the_postgres_the_stack_runs() -> None:
    """pg_dump 只肯打不大于自己的服务端：客户端大版本必须**不低于** pgvector/pgvector:pgNN。

    R608（10-03）把这格从「相等」放宽成「不低于」。按相等钉等于把镜像永远钉在一枚装不出来的包上：
    16 的客户端只有 PGDG 出，而 PGDG 在这台机与任何客户内网都取不到（见 Dockerfile 那段）。
    放宽的凭据不是推理，是同一小时的现取——pg_dump 17.11 打 16.15 的服务端交回 79,899,932 B
    custom 归档，pg_dumpall --globals-only rc=0。收紧的那一半仍然有牙：客户端比服务端老就是
    R596 抓到的那枚病，本钉当场红。
    """
    assert int(_client_major_in_image()) >= int(_server_major_in_the_stack()), (
        "compose 抬了服务端而镜像里还是旧客户端：备份腿会在版本检查上当场死")


def test_no_second_postgresql_client_major_is_pulled_in() -> None:
    majors = {name.rsplit("-", 1)[1] for name in _installed_packages()
              if name.startswith("postgresql-client-")}
    assert len(majors) == 1, sorted(majors)
    assert int(next(iter(majors))) >= int(_server_major_in_the_stack()), sorted(majors)


def test_the_four_tools_the_finding_asked_for_are_the_ones_that_package_ships() -> None:
    """R587 问的四枚要在场，代码也不许问到第五枚没人装的工具。"""
    text = _dockerfile_text()
    for tool in EXPECTED_TOOLS:
        assert re.search(r"\b" + tool + r"\b", text), tool + " 没在镜像注释里点名：为什么装这枚包会失账"
    reached = set(_cli_executables())
    assert reached <= set(EXPECTED_TOOLS), f"CLI 伸手要了一枚不在册的工具：{sorted(reached)}"
    assert reached, "两枚 CLI 一枚工具名都取不出来：那这枚钉是在空转"


def _cli_executables() -> list[str]:
    """两枚出厂 CLI 默认伸手要的可执行名：只认 argparse 的 ``default=`` 那一级。"""
    found: list[str] = []
    for module in (backup_module, restore_module):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "add_argument":
                continue
            flags = [arg.value for arg in node.args if isinstance(arg, ast.Constant)]
            if not any(flag.lstrip("-").replace("_", "-").endswith(("pg-dump", "pg-restore", "psql"))
                       for flag in flags):
                continue
            for keyword in node.keywords:
                if keyword.arg == "default" and isinstance(keyword.value, ast.Constant):
                    found.append(str(keyword.value.value))
    return found


# ---------------------------------------------------------------------------
# 拿得到、验得过：路径、签名、镜像内网可替换
# ---------------------------------------------------------------------------

def test_the_container_path_still_reaches_the_directory_the_tools_install_into() -> None:
    """postgresql-client-<major> 把 psql/pg_dump 放进 /usr/bin；这枚镜像自己钉过 PATH。

    ENV PATH 里少 /usr/bin 的话，包装上了也照样 ``command -v`` 取空——那才是真缺件的形状。
    """
    env_lines = [line for line in _instructions() if line.startswith("ENV ")]
    path_line = [line for line in env_lines if "PATH=" in line]
    assert path_line, "镜像不再声明 PATH：那这枚钉该重新想清楚容器里能不能取到工具"
    assert "/usr/bin" in path_line[0], path_line[0]


def test_the_client_comes_from_the_archive_the_mirror_arg_already_reaches() -> None:
    """R608：客户端出自 base 发行版自己的归档，不再另开一道 PGDG 出站。

    原格钉的是「PGDG 仓库要过验签、代号要现取」，那两句在没有 PGDG 仓库之后自动失去对象；
    留下的性质是：不许再出现这台机/客户内网取不到的出站，也不许用任何关掉验签的写法。
    """
    code = " ".join(_instructions())  # 只判指令，不判散文：R608 的注释里必须能写下被禁掉的那两个域名

    for banned in ("apt.postgresql.org", "www.postgresql.org", "postgresql-pgdg"):
        assert banned not in code, banned + "：这层重新引入了一道内网取不到的构建期出站"
    for banned in ("trusted=yes", "apt-key", "--allow-untrusted", "--force-yes"):
        assert banned not in code, banned + "：仓库不过验签就等于没验"
    assert "ARG PG_CLIENT_MAJOR=" in code, "客户端大版本不再是具名 arg：换档要改代码"
    assert "postgresql-client-${PG_CLIENT_MAJOR}" in code, "装的那一枚不再由那枚 arg 决定"


def test_the_build_egress_stays_behind_named_arguments_and_adds_no_downloader() -> None:
    """仓内那枚 airgap 闸只认 APT_MIRROR / PIP_INDEX_URL 两道口子；本单不许开第三道口子。

    R608 之后这一层不需要第三条口子：客户端就在 base 发行版的归档里，跟着 APT_MIRROR 走。
    仍然不许引入 curl / wget / git clone（``scripts/check_airgap_readiness.py`` 把这三枚当未
    登记的出站），也不许在构建期自己 urllib 抓东西。
    """
    text = _dockerfile_text()

    for needle in ("ARG PG_CLIENT_MAJOR=", "ARG APT_MIRROR=", "ARG PIP_INDEX_URL="):
        assert needle in text, needle + " 少了这道口子"
    for banned in ("curl ", "wget ", "git clone", "addcontextfiles"):
        assert banned not in text, banned + "：未在 airgap 登记表里的出站方式"
    assert "urlretrieve" not in text, (
        "构建期又开始自己抓东西了：R608 之后这层只许走 apt，登记表里没有第二条出站")