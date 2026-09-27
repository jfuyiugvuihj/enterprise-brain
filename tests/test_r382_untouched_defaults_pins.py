# -*- coding: utf-8 -*-
"""R382 · 本班那把"不许翻默认值"的形状钉：读数单留下的五条静态约束。

本单是取证单，不是改架构的单，所以它的验收里有几条"今天成立、但下一个人可以悄悄做掉"的
约束：出厂默认仍是 chroma（`app/rag/indexing.py` 那一行）、没有任何配置面被本班偷偷接上
pgvector 读（一切 `.env*`/compose/deploy 里不许有一行把它赋成非 chroma 的生效位赋值；09-28 随 R408 收窄：注释掉的样例不算）、本班自己的测量件只允许
进程内翻开关且必须收尾（只经 `os.environ` 赋值 + `pop`/`del`）、对遗留引擎只允许动元数据
不允许动向量（`upsert(`/`.add(`/`.delete(` 零命中）、报告是拼出来的而不是手抄出来的
（占位符不残留）。这些都不该靠本单报告的自述维持，所以钉成静态件。

范围全部离线：读文件文本，不 import 产品代码、不起服务、不连库、不碰 `chroma_db/**`。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

INDEXING = REPO / "app" / "rag" / "indexing.py"
SCRIPTS = sorted((REPO / "scripts").glob("r382_*.py"))
REPORTS = sorted((REPO / "docs" / "perf").glob("r382-*.md"))

#: 一切"部署会看见"的配置面。`.env` 在个别工作树里不存在，所以只扫在场的那些。
CONFIG_GLOBS = (".env*", "docker-compose*.yml", "deploy/.env*", "deploy/*.yml", "setup.sh")

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


def config_surfaces() -> list[Path]:
    found: set[Path] = set()
    for pattern in CONFIG_GLOBS:
        found.update(REPO.glob(pattern))
    return sorted(p for p in found if p.is_file())


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
    """
    surfaces = config_surfaces()
    assert surfaces, "没找到任何配置面文件，本钉无从判定"
    switched = []
    for path in surfaces:
        for match in EFFECTIVE_SET.finditer(read(path)):
            value = effective_value(match.group(1))
            if value != "chroma":
                switched.append(path.relative_to(REPO).as_posix() + " -> " + repr(value))
    assert not switched, "这些配置面把读后端真的翻了（生效位赋值不是 chroma）：" + str(switched)


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