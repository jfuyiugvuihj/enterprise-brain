# -*- coding: utf-8 -*-
"""R382 · 本班那把"不许翻默认值"的形状钉：读数单留下的五条静态约束。

本单是取证单，不是改架构的单，所以它的验收里有几条"今天成立、但下一个人可以悄悄做掉"的
约束：出厂默认仍是 chroma（`app/rag/indexing.py` 那一行）、没有任何配置面被本班偷偷接上
pgvector 读（一切 `.env*`/compose/deploy 里不许有一行把它赋成非 chroma 的生效位赋值；09-28 随 R408 收窄：注释掉的样例不算；10-03 随 R617 第二次收窄：只判**入树**的配置面，见下一段）、本班自己的测量件只允许
进程内翻开关且必须收尾（只经 `os.environ` 赋值 + `pop`/`del`）、对遗留引擎只允许动元数据
不允许动向量（`upsert(`/`.add(`/`.delete(` 零命中）、报告是拼出来的而不是手抄出来的
（占位符不残留）。这些都不该靠本单报告的自述维持，所以钉成静态件。

范围全部离线：读文件文本，不 import 产品代码、不起服务、不连库、不碰 `chroma_db/**`。

10-03 第二次收窄（R617 · 业主本机文件豁免）
    上面那句"一切配置面"原本按盘面 glob 取值，于是把 `deploy/.env.server` 也扫了进来。那枚文件
    命中 `.gitignore:11`，**永远不会入树**：它是业主为**自己这台机器**切读路径写的落盘，与出厂裁定
    不冲突——`INDEX_BACKEND_DEFAULT` 仍是 chroma，入树的配置面里没有一处把它赋成非 chroma 生效位。
    本钉要判的是**树里的东西**会不会被悄悄翻默认，所以取值判定的范围收成「git 跟踪的名单 ∩ 盘面
    glob」。划范围只用 `git ls-files -z` 这一枚尺（口径二选一，不混用 ignore 判定来划范围）：它只读
    索引，不 import 产品代码、不起服务、不联网、不改盘，仍在上面那句"离线"的口径里——与 r453 拿
    `docker compose config` 只渲文件同一类取数。`-z` 不是讲究：本树有 99 枚非 ASCII 路径，默认的
    quotepath 会把它们写成八进制转义，两头对不上就是一枚会误放行的坑。
    豁免的前提由本件自己钉死（`test_owner_local_env_file_stays_untracked_and_under_the_rule` 与
    `test_every_path_that_left_the_scope_is_currently_ignored`）：谁哪天把它 `git add -f` 进索引，或删掉
    ignore 那一行，那格立刻回红，不用任何人再想起来改尺。判据本身一字未动——**在范围内**的赋值行
    值不是 chroma 就红；出厂默认那两枚断言、进程内翻开关必须收尾、遗留引擎只许动元数据、报告不手抄
    这四条一格没松。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

INDEXING = REPO / "app" / "rag" / "indexing.py"
SCRIPTS = sorted((REPO / "scripts").glob("r382_*.py"))
REPORTS = sorted((REPO / "docs" / "perf").glob("r382-*.md"))

#: 一切"部署会看见"的配置面。`.env` 在个别工作树里不存在，所以只扫在场的那些；在场还不够——
#: 取值判定只看 git 跟踪的那份名单（10-03 R617 收窄，口径与理由见模块 docstring）。
CONFIG_GLOBS = (".env*", "docker-compose*.yml", "deploy/.env*", "deploy/*.yml", "setup.sh")

#: 本次收窄唯一豁免的那枚本机文件：业主为自己这台机器切读路径写的落盘，ignore 罩着、不入树。
OWNER_LOCAL_ENV = "deploy/.env.server"

SWITCH = "INDEX_BACKEND"

#: 引号字符类。写成常量是为了躲开"raw 串里嵌转义引号"这枚把语法炸掉的坑。
Q = r"[\x27\"]"

SETTER = re.compile(r"(?m)^(\s*)os\.environ\[" + Q + SWITCH + Q + r"\]\s*=")
POP = re.compile(r"os\.environ\.pop\(" + Q + SWITCH + Q)
DELET = re.compile(r"del\s+os\.environ\[" + Q + SWITCH + Q + r"\]")
ENV_WRITE = re.compile(r"\.env[\w.\x2D\x2F]*" + Q + r"\s*,\s*" + Q + r"w")
VECTOR_WRITE = re.compile(r"\.(upsert|add|delete)\s*\(")
METADATA_STAMP = re.compile(r"collection\.update\s*\(")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def git_bytes(*args: str) -> bytes:
    """只读地跑完一枚 git 命令并交回 stdout：不 import 产品代码、不起服务、不联网、不改盘。"""
    proc = subprocess.run(("git", "-C", str(REPO)) + args, capture_output=True)
    assert proc.returncode == 0, "git %s rc=%s：%s" % (
        " ".join(args), proc.returncode, proc.stderr.decode("utf-8", "replace").strip()[:200])
    return proc.stdout


def tracked_paths() -> set[str]:
    """git 索引里的那份名单＝「入树」的名单——本件划范围只用这一枚尺。"""
    return {entry.decode("utf-8", "surrogateescape")
            for entry in git_bytes("ls-files", "-z").split(b"\x00") if entry}


def is_ignored(relative: str) -> bool:
    """这枚路径此刻是否被 ignore 规则罩着（`--no-index`＝只看规则本身，不受跟踪态影响）。

    只用来**验豁免的前提**（下面两枚钉子），不参与划范围——划范围只看 tracked。两枚前提分开咬，
    谁破谁红，归因才清楚。
    """
    proc = subprocess.run(
        ("git", "-C", str(REPO), "check-ignore", "--no-index", "-q", "--", relative),
        capture_output=True)
    assert proc.returncode in (0, 1), "git check-ignore 用法不对 rc=%s" % proc.returncode
    return proc.returncode == 0


def relative_name(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def label(path: Path) -> str:
    """报告用的名字：树里的给相对路径，tmp 里的（反证钉喂的假件）给文件名。"""
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.name


def disk_config_surfaces() -> list[Path]:
    """盘面 glob 命中的在场文件＝收窄前的老范围，留着它才能钉"掉出去的东西凭什么掉出去"。"""
    found: set[Path] = set()
    for pattern in CONFIG_GLOBS:
        found.update(REPO.glob(pattern))
    return sorted(p for p in found if p.is_file())


def config_surfaces() -> list[Path]:
    """取值判定的范围＝盘面 glob ∩ git 跟踪名单（10-03 R617 收窄）。"""
    tracked = tracked_paths()
    return [path for path in disk_config_surfaces() if relative_name(path) in tracked]


def switched_values(paths) -> list[str]:
    """把每一枚配置面过一遍生效位赋值，交回"值不是 chroma"的读数——判据一字未动。"""
    switched = []
    for path in paths:
        for match in EFFECTIVE_SET.finditer(read(path)):
            value = effective_value(match.group(1))
            if value != "chroma":
                switched.append(label(path) + " -> " + repr(value))
    return switched


def test_factory_default_still_reads_from_the_retiring_engine() -> None:
    """出厂那行不许被翻：它一翻，本单所有"对照腿"的基线就不存在了。"""
    source = read(INDEXING)
    assert re.search(r'(?m)^INDEX_BACKEND_DEFAULT\s*=\s*"chroma"\s*$', source), (
        "app/rag/indexing.py 的 INDEX_BACKEND_DEFAULT 不再是 chroma：本单的对照基线作废"
    )
    assert re.search(r"(?m)^INDEX_BACKEND\s*=\s*INDEX_BACKEND_DEFAULT\s*$", source), (
        "模块常量 INDEX_BACKEND 不再回落到出厂默认，读后端解析次序已改，本单结论要重量"
    )


#: 生效位赋值。行首只允许空白或 YAML 短横，键名后紧跟 = 或 :，注释行不算——
#: 这一枚是 09-28 收窄的产物，形状本身就是判据，所以写成常量而不是塞进函数里。
EFFECTIVE_SET = re.compile(r"(?m)^[ \t]*(?:-[ \t]+)?" + SWITCH + r"[ \t]*[=:][ \t]*(.*)$")


def effective_value(rest: str) -> str:
    """把赋值行右侧收成一个值：剥掉行尾注释与引号。空串表示"赋了个空值"。"""
    return rest.split(" #", 1)[0].strip().strip("\x27\x22")


def test_no_deployment_surface_switches_the_read_backend() -> None:
    """配置面不许有一行生效位赋值把读后端翻走；注释里提一句键名不算落盘。

    09-28 第十二格续·收窄记录（总控裁定，随 R408 并树落地）：本钉原本一律「键名零命中」，
    于是连 `# INDEX_BACKEND=chroma` 这种**注释掉的、值就是出厂默认**的样例都判红，
    配置面因此永远不许对这一枚闸说一句人话——R408 实测 BASE 16 passed / AFTER 1 failed，
    冲突属实（影子树复现，不是采信自述）。放开的是"提一嘴"，没放开的是"翻默认"：
    **任何一行真赋值都必须把值写回 chroma**，写 pgvector、写空、写错别字一律当场红。
    同口径另有 R408 那枚行为化钉从真函数嘴里咬住（read_backend() 缺省仍是 chroma、
    pgvector_reads_enabled() 为假），两把不互相替代。对 `INDEX_BACKEND_DEFAULT`
    的那两枚断言一字未动，"出厂默认没被翻"这句话仍然由它把关。

    10-03 第二次收窄记录（R617，总控裁定）：这格把 `deploy/.env.server` 判红了。那枚文件命中
    `.gitignore:11`，是业主为本机切读路径落的盘（一枚非默认生效位赋值），不入树、也就不是"部署会看见的配置面"。
    放开的是**不入树的本机文件**，没放开的是**树里翻默认**：范围现在只看 git 跟踪的名单，跟踪件里
    任何一行生效位赋值不是 chroma 照样当场红。豁免不是空口白话——它的前提由
    `test_owner_local_env_file_stays_untracked_and_under_the_rule` 钉死，文件一进索引或 ignore 规则一删
    就红；`test_counter_evidence_a_flipping_surface_inside_the_scope_still_goes_red` 再证判据没被改软。
    """
    surfaces = config_surfaces()
    assert surfaces, "没找到任何配置面文件，本钉无从判定"
    switched = switched_values(surfaces)
    assert not switched, "这些配置面把读后端真的翻了（生效位赋值不是 chroma）：" + str(switched)


def test_owner_local_env_file_stays_untracked_and_under_the_rule() -> None:
    """🔴 上面那格收窄的前提钉：`deploy/.env.server` 此刻仍不入索引，且仍被 ignore 规则罩着。

    豁免只在这两件事同时成立时才成立，所以两件事分开咬：
    ① 有人 `git add -f` 它 ⇒ 第一枚断言当场红；同时它已经回到 `config_surfaces()` 的范围里，
       "不许有一行生效位赋值把读后端翻走"立刻对它重新生效，不用人再想起来改尺。
    ② 有人删掉 `.gitignore:11` 那一行 ⇒ 第二枚红：规则一没，下一句 `git add .` 就会把业主本机那份
       pgvector 赋值扫进树里，这枚空档必须有人签字才许留。
    本钉与那枚文件在不在磁盘上无关（`--no-index` 只看规则），在任何一棵树上都真跑，不是 skip。
    """
    assert OWNER_LOCAL_ENV not in tracked_paths(), (
        OWNER_LOCAL_ENV + " 被 add 进索引了 ⇒ 本机文件豁免作废：它现在是入树配置面，必须回到"
        "「不许有一行生效位赋值把读后端翻走」那把尺底下")
    assert is_ignored(OWNER_LOCAL_ENV), (
        ".gitignore 里罩着 " + OWNER_LOCAL_ENV + " 的规则没了 ⇒ 豁免的前提不成立：要么恢复规则，"
        "要么显式把这枚文件当入树配置面处理")
    #: 第二枚断言不能是空尺：同一枚探测器对一枚什么规则都没罩的路径必须说"没罩"。
    #: （本单禁止改 .gitignore，所以"删掉那一行"没法真做，这里改证探测器本身会咬。）
    assert not is_ignored("r617-no-rule-covers-this-file.txt"), (
        "check-ignore 探测器失灵：没有任何规则罩着的路径它也说罩着 ⇒ 前提②是空尺")


def test_every_path_that_left_the_scope_is_currently_ignored() -> None:
    """掉出范围的每一枚在场配置面，都必须同时满足「不入索引 ＋ 被 ignore 罩着」。

    这枚防的是"收窄写着写着变成一把更大的尺"：不许按路径名字放过，也不许某一格整块不再扫。
    树里没有本机文件时循环没有对象（真跑，不是 skip）。
    """
    tracked = tracked_paths()
    for path in disk_config_surfaces():
        name = relative_name(path)
        if name in tracked:
            continue
        assert is_ignored(name), (
            name + " 既不在索引里、也没被 ignore 规则罩住，却掉出了本钉的取值范围")


def test_the_narrowed_scope_still_covers_the_tracked_surfaces() -> None:
    """收窄不许顺手把范围掏空：入树那几枚必须仍在场上，`deploy/.env*` 这一格不许整块消失。"""
    names = {relative_name(path) for path in config_surfaces()}
    for required in (".env.example", "docker-compose.yml", "deploy/.env.server.example"):
        assert required in names, required + " 掉出了取值范围：本钉被掏空了"
    assert any(name.startswith("deploy/.env") for name in names), (
        "deploy/.env* 整格被排除了——豁免的是那一枚本机文件，不是这一格")


def test_counter_evidence_a_flipping_surface_inside_the_scope_still_goes_red(tmp_path: Path) -> None:
    """反证：这次动的是**范围**，不是判据。把一枚真把默认翻走的配置面喂进同一把尺，必须报。

    四条形状一起核（tmp 里造，不动树上的在册件）：YAML 冒号赋值翻走必须报；等号赋值翻走必须报；
    值就是 chroma 必须不报；注释掉的 pgvector 必须不报（09-28 R408 那格收窄不能被我带歪）。
    """
    flipped = tmp_path / "compose.flipped.yml"
    flipped.write_text(
        "services:\n  backend:\n    environment:\n      INDEX_BACKEND: pgvector\n",
        encoding="utf-8")
    assert switched_values([flipped]) == ["compose.flipped.yml -> 'pgvector'"], (
        "范围收窄之后判据失灵了：范围里一枚 pgvector 赋值没被咬住")
    eq_form = tmp_path / "env.eq"
    eq_form.write_text("INDEX_BACKEND=pgvector\n", encoding="utf-8")
    assert switched_values([eq_form]), "等号形态的翻默认没被咬住"
    back = tmp_path / "env.chroma"
    back.write_text("INDEX_BACKEND=chroma\n", encoding="utf-8")
    assert switched_values([back]) == [], "值就是出厂默认的赋值不该被报"
    commented = tmp_path / "env.comment"
    commented.write_text("# INDEX_BACKEND=pgvector\n", encoding="utf-8")
    assert switched_values([commented]) == [], (
        "注释行被算成落盘了：09-28 R408 那格收窄的形状不能退回去")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_measurement_scripts_switch_in_process_and_in_pairs(script: Path) -> None:
    """开关只准进程内翻，而且设与收尾必须同件成对出现。

    派工词允许两种手法：进程内 `os.environ`，或 `docker exec`/`--env` 注入。本钉不去禁后者，
    它钉的是另一件更要紧的：本班既已选了进程内那条路，就不许留下"设了不收"的脏环境——那会让
    同一进程里后跑的那一腿冒充成对照腿。真正的落盘禁止由上面两枚钉（配置面零命中、不写 .env）
    把关。
    """
    source = read(script)
    setters = SETTER.findall(source)
    cleared = bool(POP.search(source) or DELET.search(source))
    if not setters:
        assert not cleared, script.name + " 清了开关却从没设过，形状不对"
        return
    assert cleared, script.name + " 设了 " + SWITCH + " 却没收尾，进程内会留下脏环境"


def test_scripts_never_write_an_env_file() -> None:
    """任何以 `.env` 为落点的写模式都不许出现在测量件里。"""
    offenders = [p.name for p in SCRIPTS if ENV_WRITE.search(read(p))]
    assert not offenders, "这些测量件在写 .env：" + str(offenders)


def test_legacy_engine_is_only_stamped_never_rewritten() -> None:
    """向量一个字节都不许动：动了，报告 §2.4 那份召回读数当场作废。"""
    offenders = [p.name for p in SCRIPTS if VECTOR_WRITE.search(read(p))]
    assert not offenders, "这些测量件会对遗留引擎做向量级写：" + str(offenders)
    stamped = sorted(p.name for p in SCRIPTS if METADATA_STAMP.search(read(p)))
    assert stamped == ["r382_matched_corpus.py"], (
        "只允许同形对照那一件动元数据，实际：" + str(stamped)
    )


def test_report_is_assembled_not_hand_pasted() -> None:
    """报告必须由生成件拼出来：占位符不残留、纯 CRLF、无 BOM、无裸 LF。"""
    assert REPORTS, "docs/perf 下没有 r382 报告，本钉无从判定"
    for report in REPORTS:
        raw = report.read_bytes()
        assert raw[:3] != b"\xef\xbb\xbf", report.name + " 带 BOM"
        text = raw.decode("utf-8")
        assert "{{" not in text, (
            report.name + " 还留着未注入的表格占位符：跑 r382_assemble.py"
        )
        assert raw.count(b"\n") == raw.count(b"\r\n"), report.name + " 含裸 LF"