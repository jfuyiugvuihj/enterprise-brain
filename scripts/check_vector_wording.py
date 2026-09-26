#!/usr/bin/env python3
"""R276 机器钉：向量库口径 —— PGVector 是生产向量库，Chroma 是退役中的遗留件。

为什么要有这一枚（业主 09-24 定案，AGENTS.md 已改写，架构与功能文档没跟上）：
    定案之后仍然有人拿着旧文档问"为什么现在还是 Chroma 不是 pgvector"，因为订正前的
    `docs/system-architecture-2026-09-17.md:242` 把 Chroma 写成"当前唯一运行时向量读写方"，
    订正前的 `docs/current-functionality-2026-09-10.md` 还列着"没有把向量同步进 PostgreSQL
    的机制" —— 那两句话都是假的。改一轮文档只能管一次，所以把它做成可复跑的钉：本钉在
    R276 动笔前先跑出 10 处违规（涉及 3 枚文件），动笔后归零。

它咬什么（三条规则，全部只匹配"断言"，见下面的"引号不算断言"）：
    W1 目标态声明：一枚文档只要在**同一行**里既提"向量库/向量存储/vector store"又提
       Chroma 或 PGVector（=它对向量存储表了态），全文就必须有一行同时给出 `pgvector`
       与 生产/定案/目标存储/退役 之一。缺了 ⇒ 报 `missing_target_state`，并指名文件。
    W2 禁句：断言行里出现"向量库＝Chroma""Chroma 是当前唯一读写方""Chroma 是最终/生产
       架构""PGVector 只是目标""向量读写 100% 走 Chroma""PGVector 只有 schema 骨架"
       （把 Chroma 写成架构、把定案写成还在讨论），或"Chroma 已下线/已退役""向量库已切换
       完成"（把话说过头）⇒ 报对应的 banned 规则，清单在 `BANNED`。**两头都咬**：
       AGENTS.md 同一条明令它既不许写成最终架构，也不许写成已下线 —— 它今天仍在提供读服务。
    W3 真实位置：凡给了 W1 目标态声明的文档，必须同时有一行写今天的真实位置
       （读路径仍在 Chroma / 切读 R59 / 停写退役 R60 / 双写 / 遗留 / 过渡 / 在途 任一）
       ⇒ 缺了 ⇒ 报 `missing_real_position`。只写目标态的文档会让读者以为已经切完。

引号不算断言（这是设计，不是漏洞的一半）：`「…」`、`“…”`、`` `…` `` 与 ``` 围栏内的文字
    在匹配前被剥掉。理由：订正记录必须引用被推翻的旧原句（`docs/current-functionality-2026-09-10.md`
    §39 那张表逐条引着旧假话），不许把这种引用判成违规。代价见下面的盲区第 1 条。

它拦不住什么（诚实写盲区；别把这枚钉当成"口径已全覆盖"）：
    1. 把假话写进引号（`「…」` / `“…”` / 行内码）或 ``` 围栏里当"别人说过的话"引用 ——
       本钉认为那是记录，不是断言。markdown 表格**不在**豁免之内：口径表正是假话最爱待的地方。
    2. 只看措辞，不看事实。一句话语法合规而内容错（"1008 枚"写成"1080 枚"、双写其实没开、
       行号指错）它一概读不出来。开关真值与向量条数不在钉的半径内。
    3. 不用"向量库/向量存储/vector store"这些词的说法不触发 W1，例如"向量存在 X 里"、
       "embedding 落在 Chroma"、"语义检索走 Chroma"。W2 的 `BANNED` 是**有限枚举**
       （现 9 条，全部来自本仓出现过的真实句式），新造的说法不在内。
    4. 禁令与元叙述被豁免：命中片段**之内**出现 不许/不能/不得/禁止/不要/严禁/避免/防止/
       不应/写成/写作 时 W2 放过（"不许把 Chroma 写成最终架构"是正确的口径，不是违规）。
       代价有两半：同一段里"前半句禁令 + 后半句假话"能整条过关；而否定词长在**上一行**时
       也读不到 —— 订正前 `docs/current-functionality-2026-09-10.md` 那句
       "将 Chroma 中现有向量自动同步到 PostgreSQL 的机制"就藏在上一行写着"当前没有发现
       以下生产实现"的列表里，本钉当时不响，是人读出来改掉的。
    5. 扫描范围只有 `docs/**` 的 `.md` 加 `AGENTS.md`，再减去下面的豁免清单。`README.md`、
       `frontend/**` 里的界面文案、`app/**` 的代码与注释、`*.py` docstring 全都不在半径内 ——
       代码里读路径到底走哪，得由 `tests/test_r231_no_half_switch.py` 那类件管，不归本钉。
    6. 整枚不提向量库的新文档，本钉保持沉默：沉默不等于正确，只是它没有可判的对象。
    7. 豁免是按路径前缀整枚生效的，一枚文档进了豁免清单就完全不被看。清单之所以存在以及
       它可能被人加长，由 tests/test_r276_vector_wording_pin.py 里的钉管着（受管文档一旦
       被写进豁免清单，那枚用例当场红）。

只读：本脚本不写任何文件、不连数据库、不起服务、不打模型。
退出码：0 = 全部通过；1 = 有违规（逐行输出文件名 + 规则名 + 行号）；2 = 扫描本身失败
（根目录不存在、文件读不出来），此时不输出"通过"的结论。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 按路径前缀整枚豁免（相对仓库根，POSIX 拼法）。每一条都是"里面写 Chroma 是合法记录"：
#:   docs/handoff/    —— 派工账本与实测记录（跟进单、计划书、看板），改它就是造假
#:   docs/testing/    —— 跑分明细与读数
#:   docs/perf/raw/   —— 原始 jsonl/tsv 读数
#:   docs/superpowers/ —— 计划书 §10 已明令过期的历史计划书
#:   -revision-log.md —— 按日冻结的修订账（里面 09-10 那句旧口径是当时的记录）
EXEMPT_PREFIXES = (
    "docs/handoff/",
    "docs/testing/",
    "docs/perf/raw/",
    "docs/superpowers/",
)
EXEMPT_SUFFIXES = ("-revision-log.md",)

#: 额外纳入扫描的仓库根文件：AGENTS.md 就是本钉口径的来源，它自己也得站在口径上。
EXTRA_DOCS = ("AGENTS.md",)

#: 引号 / 行内代码 —— 剥掉之后再匹配（"引号不算断言"）。
QUOTED = re.compile(r"「[^」]*」|“[^”]*”|`[^`\n]*`")

FENCE_MARK = "```"

#: W1 触发：同一行里既谈"向量库/向量存储"又点名 Chroma 或 PGVector。
STORE_WORD = re.compile(r"向量库|向量存储|vector\s+(?:store|database|db)", re.IGNORECASE)
ENGINE_WORD = re.compile(r"chroma|pgvector", re.IGNORECASE)

#: W1 要求的声明：一行里同时有 pgvector 与"生产/定案/目标存储/退役"。
DECLARATION_ENGINE = re.compile(r"pgvector", re.IGNORECASE)
DECLARATION_ROLE = re.compile(r"生产|定案|目标存储|退役")

#: W3 要求的真实位置：任意一行给出今天读路径/切换状态的说法。
REAL_POSITION = re.compile(
    r"读路径|读取路径|read\s+path|尚未切|未切|切读|停写|遗留|过渡|在途|双写|影子读"
)

#: 禁令与元叙述屏蔽（盲区第 4 条），两半各有分工：
#:   PROHIBITION        —— 命中片段**之内**带禁令或"写成/写作"，按元叙述放过；
#:   PREFIX_PROHIBITION —— 片段之前是"不得把 / 不许将"这一类**禁令动词 + 把字句**也放过，
#:                         因为那枚禁句正是被当宾语引用出来的（"不许写『向量库＝Chroma』"）。
#: 不做整行屏蔽：整行屏蔽会把"当前仍以 Chroma 为主要向量检索实现，不能把目标架构写成
#: 当前能力"这种**前半句假话 + 后半句禁令**一起放过，而那半假话恰恰是要咬的东西。
PROHIBITION = re.compile(
    r"不许|不能|不得|禁止|不要|严禁|避免|防止|不应|不建议|不宜|误写|写成|写作|不[把将]"
)
PREFIX_PROHIBITION = re.compile(
    r"(?:不许|不能|不得|禁止|不要|严禁|避免|防止|不应|不宜)\s*[把将]"
)

#: W2 禁句清单：(规则名, 编译后的式子, 说明)。式子一律在"剥掉引号与围栏"的断言文本上匹配。
BANNED: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "chroma_declared_as_the_vector_store",
        re.compile(
            r"(?:生产向量库|向量库|向量存储|vector\s*(?:store|database))"
            r"(?:[^。\n]{0,12}[=＝是为]|[^|\n]{0,4}\|[^|\n]{0,4})"
            r"\s*(?:当前的?|现在的?|唯一的?|主要的?|最终的?|生产)?\s*chroma",
            re.IGNORECASE,
        ),
        "把向量库本身等于 Chroma（业主 09-24 已定案为 PostgreSQL + PGVector）",
    ),
    (
        "chroma_declared_final_or_production_architecture",
        re.compile(
            r"chroma[^。\n]{0,24}(?:最终|长期|未来的?|目标态?|生产)(?:生产)?(?:架构|向量库|向量存储)",
            re.IGNORECASE,
        ),
        "把 Chroma 写成最终/生产架构",
    ),
    (
        "chroma_declared_only_runtime_reader_writer",
        re.compile(
            r"chroma\s*(?:是|为|仍是|依然是)\s*(?:当前|现在|今天)?\s*(?:唯一|主要)"
            r"[^。\n]{0,12}(?:读写方|读路径|向量库|向量存储|实现)",
            re.IGNORECASE,
        ),
        "把 Chroma 写成唯一/主要运行时读写方（双写已在跑，这句今天不成立）",
    ),
    (
        "chroma_declared_decommissioned",
        re.compile(
            r"chroma\s*(?:已经|已|现已|业已)\s*(?:下线|退役|停用|废弃|移除|删除)"
            r"|(?:已|已经)\s*(?:将)?\s*chroma\s*(?:下线|退役|停用|废弃)",
            re.IGNORECASE,
        ),
        "把 Chroma 写成已下线/已退役（它今天仍在提供读服务，这句同样是假话）",
    ),
    (
        "switch_declared_completed",
        re.compile(
            r"(?:向量库|切读|向量迁移)\s*已\s*(?:完成|切换完成|经切换完成)"
            r"|已\s*(?:完成|经)\s*(?:向量库|切读|pgvector)\s*(?:切换|迁移)"
            r"|(?:切换|迁移)\s*(?:已经|已)\s*完成[^。\n]{0,8}(?:向量库|切读|pgvector)",
            re.IGNORECASE,
        ),
        "把切换说成已完成（切读单 R59 在途、停写退役 R60 未开工）",
    ),
    (
        "pgvector_demoted_to_a_merely_goal",
        re.compile(
            r"pgvector\s*(?:只是|仅是|仅仅是|仍是|仍属于)\s*(?:的)?(?:生产)?(?:目标|未来|设想|待办)",
            re.IGNORECASE,
        ),
        "把 PGVector 说成只是目标（09-24 已定案为生产向量库，没完成的只是切换这一步）",
    ),
    (
        "vector_readwrite_declared_all_on_chroma",
        re.compile(
            r"向量[^。\n]{0,10}(?:读写|读取|检索)[^。\n]{0,10}100\s*%\s*走\s*chroma",
            re.IGNORECASE,
        ),
        "把向量读写说成 100% 走 Chroma（双写已在跑，写侧这句今天不成立）",
    ),
    (
        "pgvector_declared_unwired_skeleton",
        re.compile(
            r"pgvector[^。\n]{0,16}(?:仅有\s*schema|只有\s*schema|schema 骨架|运行时未接线|无写入方)",
            re.IGNORECASE,
        ),
        "把 PGVector 说成只有 schema 骨架、运行时未接线（0010 已给定向量列并建 HNSW，双写在写）",
    ),
    (
        "vector_store_migration_still_optional",
        re.compile(
            r"根据[^。\n]{0,12}决定[^。\n]{0,6}(?:是否)?\s*迁移\s*pgvector",
            re.IGNORECASE,
        ),
        "把迁 PGVector 写成按部署规模再决定（09-24 已定案，不再由规模决定）",
    ),
)


class Finding:
    """一枚违规：文件 + 规则名 + 行号 + 原文摘要。文件名是判据④要求的输出。"""

    __slots__ = ("path", "rule", "line_number", "excerpt", "detail")

    def __init__(self, path: str, rule: str, line_number: int, excerpt: str, detail: str):
        self.path = path
        self.rule = rule
        self.line_number = line_number
        self.excerpt = excerpt
        self.detail = detail

    def __str__(self) -> str:
        where = f"{self.path}:{self.line_number}" if self.line_number > 0 else self.path
        return f"FAIL {where} [{self.rule}] {self.detail}\n     > {self.excerpt}"

    def __repr__(self) -> str:  # 让 pytest 的失败信息直接可读
        return str(self)


def is_exempt(relative: str) -> bool:
    """豁免判定：证据/账本类文件整枚不看（盲区第 7 条）。"""
    normalized = relative.replace("\\", "/")
    return normalized.startswith(EXEMPT_PREFIXES) or normalized.endswith(EXEMPT_SUFFIXES)


def discover(root: Path) -> list[Path]:
    """受检文档集合：docs/**.md（减豁免）+ AGENTS.md。按排序返回，保证可复现。"""
    found: list[str] = []
    docs = root / "docs"
    if docs.is_dir():
        found.extend(str(p.relative_to(root)) for p in docs.rglob("*.md"))
    for extra in EXTRA_DOCS:
        if (root / extra).is_file():
            found.append(extra)
    return sorted(
        root / name for name in found if not is_exempt(name.replace("\\", "/"))
    )


def assertion_lines(text: str) -> list[tuple[int, str]]:
    """把文档切成"断言行"：围栏之外，每行剥掉引号与行内代码。行号保持 1 基。"""
    lines: list[tuple[int, str]] = []
    inside_fence = False
    for number, raw in enumerate(text.splitlines(), start=1):
        if raw.lstrip().startswith(FENCE_MARK):
            inside_fence = not inside_fence
            continue
        if inside_fence:
            continue
        lines.append((number, QUOTED.sub(" ", raw)))
    return lines


def check_document(root: Path, path: Path) -> list[Finding]:
    """一枚文档的三条规则。返回空表 = 这枚文档口径合格。"""
    relative = path.relative_to(root).as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:  # 读不出来就让它红，不当成"通过"
        return [Finding(relative, "unreadable", 0, type(exc).__name__, "无法读取，口径无法判定")]

    lines = assertion_lines(text)
    findings: list[Finding] = []

    talks_about_vector_store = False
    has_declaration = False
    has_real_position = False
    for number, line in lines:
        if STORE_WORD.search(line) and ENGINE_WORD.search(line):
            talks_about_vector_store = True
        if DECLARATION_ENGINE.search(line) and DECLARATION_ROLE.search(line):
            has_declaration = True
        if REAL_POSITION.search(line):
            has_real_position = True
        for rule, pattern, detail in BANNED:
            match = pattern.search(line)
            if match is None:
                continue
            #: 片段之内看元叙述，片段之前只认"禁令 + 把字句"这一种引用形。
            #: 代价（盲区第 4 条）：禁令与假话分句写在一起时，前半句假话会整条放过。
            if PROHIBITION.search(match.group(0)):
                continue
            if PREFIX_PROHIBITION.search(line[: match.start()]):
                continue
            findings.append(
                Finding(relative, rule, number, line.strip()[:160], detail)
            )

    if talks_about_vector_store and not has_declaration:
        findings.append(
            Finding(
                relative,
                "missing_target_state",
                0,
                "全文没有一行同时给出 PGVector 与 生产/定案/目标存储/退役",
                "对向量库表态却没写目标态（定案：生产向量库 = PostgreSQL + PGVector）",
            )
        )
    if has_declaration and not has_real_position:
        findings.append(
            Finding(
                relative,
                "missing_real_position",
                0,
                "全文没有一行交代今天的读路径/切换状态",
                "只写目标态会让读者以为已经切完（真实位置：读路径仍在 Chroma，R59 在途、R60 未开工）",
            )
        )
    return findings


def check(root: Path) -> list[Finding]:
    """整仓扫描。"""
    root = root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"not a repository root: {root}")
    findings: list[Finding] = []
    for path in discover(root):
        findings.extend(check_document(root, path))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="R276 向量库口径钉：PGVector 是生产向量库，Chroma 是退役中的遗留件。"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="扫描根（默认仓库根）；用例用它可以指向临时树，不碰真文档。",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="连通过的文件也逐枚列出来，便于确认覆盖面。",
    )
    args = parser.parse_args(argv)

    try:
        documents = discover(args.root.resolve())
        findings = check(args.root)
    except (NotADirectoryError, OSError) as exc:
        print(f"ERROR 扫描失败：{exc}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"扫描 {len(documents)} 枚文档（豁免清单见文件头）")
        for path in documents:
            print(f"  - {path.relative_to(args.root.resolve()).as_posix()}")

    for finding in findings:
        print(str(finding))

    if findings:
        print(
            f"\n向量库口径钉：{len(findings)} 处违规，涉及 "
            f"{len({f.path for f in findings})} 枚文件。"
        )
        return 1

    print(
        f"向量库口径钉：{len(documents)} 枚文档全部通过"
        "（目标态 = PostgreSQL + PGVector；Chroma 只许以退役中的遗留件身份出现）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
