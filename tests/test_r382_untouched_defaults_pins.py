# -*- coding: utf-8 -*-
"""R382 · 本班那把"不许翻默认值"的形状钉：读数单留下的五条静态约束。

本单是取证单，不是改架构的单，所以它的验收里有几条"今天成立、但下一个人可以悄悄做掉"的
约束：出厂默认仍是 chroma（`app/rag/indexing.py` 那一行）、没有任何配置面被本班偷偷接上
pgvector 读（一切 `.env*`/compose/deploy 里 `INDEX_BACKEND` 零命中）、本班自己的测量件只允许
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


def test_no_deployment_surface_mentions_the_switch() -> None:
    """配置面零命中：切读至今是一次都没落盘的动作，本班也没替它落盘。"""
    surfaces = config_surfaces()
    assert surfaces, "没找到任何配置面文件，本钉无从判定"
    dirty = [p.relative_to(REPO).as_posix() for p in surfaces if SWITCH in read(p)]
    assert not dirty, "这些配置面出现了 " + SWITCH + "（本单一律不许落盘）：" + str(dirty)


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