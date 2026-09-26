"""R276 判据④/⑤：向量库口径钉必须**真咬**，而且不能误咬。

这枚钉要防的是同一件事的两头：把 Chroma 写成最终架构是假话，把它写成已下线同样是假话
（AGENTS.md「向量库口径已定」那条明令）。所以用例分三组：

1. `test_the_repository_passes_its_own_wording_pin` —— 今天的仓必须绿（R276 改完的口径）；
2. 摘钉组 —— 把受管文档的目标态改回"向量库＝Chroma"、把声明整行删掉、把 Chroma 写成已
   退役，三种都要红，并且**必须报出文件名**（判据④要的就是这一条）；
3. 误咬组 —— "出现 chroma 这个词"不是罪（实测记录里它合法出现成千次）、引号里的旧原句不
   算断言、新增文档绕不过去（不许窄到只扫一枚文件）。

全程离线：只读 `docs/**` 与本件自己写进 `tmp_path` 的临时树，不碰真文档、不连库、不起服务。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_vector_wording.py"

_spec = importlib.util.spec_from_file_location("check_vector_wording", SCRIPT)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)

#: R276 的受管文档清单（跟进单 §101.12 原文）。它们一枚都不许被豁免清单吞掉。
MANAGED_DOCS = (
    "docs/current-functionality-2026-09-10.md",
    "docs/system-architecture-2026-09-17.md",
    "docs/system-design-2026-09-16.md",
    "docs/version-roadmap-and-next-week-plan-2026-09-22.md",
    "docs/api/contract-v1.md",
    "docs/deployment/backup-restore.md",
    "docs/deployment/memory-fallback-and-multi-instance-boundaries.md",
    "docs/documents/ownership-and-authorization.md",
    "docs/frontend-plan-2026-09-14.md",
    "docs/perf/enterprise-env-matrix.md",
)

#: 一枚合格的口径样板：目标态 + 真实位置同段给全。
COMPLIANT = """# 存储口径

| 向量 | **PostgreSQL + PGVector（生产向量库·业主 09-24 定案）**；Chroma = 退役中的遗留件，今天仍在提供读服务（切读单 R59 在途） |
"""


def _tree(tmp_path: Path, docs: dict[str, str]) -> Path:
    """把若干文档写进一棵临时树，用来模拟"新增一枚文档"，不碰工作树。"""
    for name, text in docs.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return tmp_path


def _copy_managed(tmp_path: Path, relative: str) -> Path:
    """把一枚真受管文档拷进临时树再改：摘钉只作用于副本，工作树一个字都不动。"""
    source = ROOT / relative
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    return target


def _rules(findings) -> set[str]:
    return {finding.rule for finding in findings}


def _paths(findings) -> set[str]:
    return {finding.path for finding in findings}


# ---------------------------------------------------------------- 今天的仓必须绿


def test_the_repository_passes_its_own_wording_pin() -> None:
    assert checker.check(ROOT) == []


def test_every_managed_doc_is_inside_the_scanned_set() -> None:
    discovered = {
        path.relative_to(ROOT).as_posix() for path in checker.discover(ROOT)
    }
    assert set(MANAGED_DOCS) <= discovered, sorted(set(MANAGED_DOCS) - discovered)


def test_the_exempt_list_only_covers_evidence_records() -> None:
    # 豁免清单只许指向日志/读数/账本类目录，且一枚受管文档都不许落在里面。
    assert all(prefix.startswith("docs/") for prefix in checker.EXEMPT_PREFIXES)
    for managed in MANAGED_DOCS:
        assert not checker.is_exempt(managed), managed


# ---------------------------------------------------------------- 摘钉：三种都要红


def test_writing_the_vector_store_back_as_chroma_is_bitten(tmp_path) -> None:
    relative = "docs/system-design-2026-09-16.md"
    copied = _copy_managed(tmp_path, relative)
    text = copied.read_text(encoding="utf-8")
    assert "生产向量库·业主 09-24 定案" in text  # 钉住前提：改的就是那句目标态
    mutated = text.replace(
        "**PostgreSQL + PGVector（生产向量库·业主 09-24 定案）**；Chroma = 退役中的遗留件",
        "**向量库＝Chroma（生产架构）**",
        1,
    )
    assert mutated != text
    copied.write_text(mutated, encoding="utf-8", newline="\n")

    findings = checker.check(tmp_path)
    assert "chroma_declared_as_the_vector_store" in _rules(findings)
    assert _paths(findings) == {relative}  # 判据④：必须报出文件名


def test_deleting_the_target_state_declaration_is_bitten(tmp_path) -> None:
    relative = "docs/system-architecture-2026-09-17.md"
    copied = _copy_managed(tmp_path, relative)
    lines = copied.read_text(encoding="utf-8").splitlines()
    kept = [
        line
        for line in lines
        if not (
            checker.DECLARATION_ENGINE.search(line)
            and checker.DECLARATION_ROLE.search(line)
        )
    ]
    assert len(kept) < len(lines)  # 前提：这枚文档原本是有声明行的
    copied.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")

    findings = checker.check(tmp_path)
    assert "missing_target_state" in _rules(findings)
    assert relative in _paths(findings)


def test_claiming_chroma_is_already_retired_is_bitten_too(tmp_path) -> None:
    # 反方向的假话同样要红：Chroma 今天仍在提供读服务。
    tree = _tree(
        tmp_path,
        {
            "docs/retired.md": (
                COMPLIANT
                + "\n- Chroma 已下线，向量库已切换完成。\n"
            )
        },
    )
    findings = checker.check(tree)
    assert {"chroma_declared_decommissioned", "switch_declared_completed"} <= _rules(findings)
    assert _paths(findings) == {"docs/retired.md"}


def test_a_brand_new_doc_cannot_slip_past_the_pin(tmp_path) -> None:
    # 判据④：不许窄到"只扫一枚文件"——新目录里的新文档一样被抓。
    tree = _tree(
        tmp_path,
        {
            "docs/deep/newcomer/notes.md": "| 向量库 | Chroma |\n",
            "docs/deep/other.md": COMPLIANT,
        },
    )
    findings = checker.check(tree)
    assert _paths(findings) == {"docs/deep/newcomer/notes.md"}
    assert {"chroma_declared_as_the_vector_store", "missing_target_state"} <= _rules(findings)


def test_main_exits_one_and_prints_the_offending_file(tmp_path, capsys) -> None:
    tree = _tree(tmp_path, {"docs/bad.md": "| 向量库 | Chroma |\n"})
    assert checker.main(["--root", str(tree)]) == 1
    printed = capsys.readouterr().out
    assert "docs/bad.md" in printed
    assert "chroma_declared_as_the_vector_store" in printed


def test_main_exits_zero_on_a_clean_tree(tmp_path, capsys) -> None:
    tree = _tree(tmp_path, {"docs/good.md": COMPLIANT})
    assert checker.main(["--root", str(tree)]) == 0
    assert "全部通过" in capsys.readouterr().out


def test_a_missing_root_is_a_scan_failure_not_a_pass(tmp_path, capsys) -> None:
    missing = tmp_path / "nope"
    assert checker.main(["--root", str(missing)]) == 2
    assert "扫描失败" in capsys.readouterr().err


# ---------------------------------------------------------------- 误咬：这些都不许红


def test_the_word_chroma_appearing_hundreds_of_times_is_not_an_error(tmp_path) -> None:
    body = "\n".join(f"- Chroma 读数第 {i} 条：命中 {i} 行" for i in range(400))
    tree = _tree(tmp_path, {"docs/measured.md": COMPLIANT + "\n" + body + "\n"})
    assert checker.check(tree) == []


def test_quoted_legacy_wording_is_read_as_a_record_not_an_assertion(tmp_path) -> None:
    # §39 那张订正表必须能引用被推翻的旧原句，否则订正记录本身就过不了门。
    quoted = (
        COMPLIANT
        + "\n| 本文原句 | 今天 |\n|---|---|\n"
        + "| 「当前仍以 Chroma 为主要向量检索实现，PGVector 只是生产目标」"
        + "「向量读写 100% 走 Chroma」 | 已按定案改写 |\n"
    )
    tree = _tree(tmp_path, {"docs/correction.md": quoted})
    assert checker.check(tree) == []


def test_prohibition_sentences_about_the_wording_are_not_violations(tmp_path) -> None:
    banned_note = (
        COMPLIANT
        + "\n- 不许把 Chroma 写成最终架构，也不能写成已下线。\n"
        + "- 新文档一律不得把向量库＝Chroma 当成现状。\n"
    )
    tree = _tree(tmp_path, {"docs/rules.md": banned_note})
    assert checker.check(tree) == []


def test_a_doc_that_never_names_the_vector_store_stays_silent(tmp_path) -> None:
    # 盲区第 6 条：没有可判的对象时本钉不响，别指望它替你发现"没写口径"的文档。
    tree = _tree(tmp_path, {"docs/unrelated.md": "# 前端计划\n\n- 本轮不改动 `frontend/`。\n"})
    assert checker.check(tree) == []


# ---------------------------------------------------------------- 形状钉：规则清单不许烂掉


def test_the_banned_list_covers_both_directions() -> None:
    rules = {name for name, _pattern, _detail in checker.BANNED}
    assert "chroma_declared_as_the_vector_store" in rules
    assert "chroma_declared_decommissioned" in rules  # 反方向的假话也在清单里
    assert len(rules) == len(checker.BANNED)


def test_assertion_lines_strip_fences_and_keep_line_numbers() -> None:
    text = "甲\n```\n向量库 = Chroma\n```\n乙\n"
    assert checker.assertion_lines(text) == [(1, "甲"), (5, "乙")]
