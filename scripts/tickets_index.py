#!/usr/bin/env python3
"""R679 - docs/tickets/index.tsv 的唯一生成器与校验尺（派生账，禁止手改）。

状态一律由 git 现查得出：有并树提交 = LANDED，工单文件在而树里无提交 = QUEUED。
本尺只读 `git log` 与盘上文件，绝不读工作区脏净（AGENTS.md 病根处置②③／事故 #96 #107）。
坐标一律 文件::符号 形态，本文件与产物都不写行号。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

FOLLOWUP = "docs/handoff/2026-09-15-backend-followup-requests.md"
BOARD = "docs/handoff/2026-09-15-orchestration-board.md"
TICKETS_DIR = "docs/tickets"
INDEX_NAME = "index.tsv"
COLUMNS = ("号", "状态", "写域", "基点", "凭据出处")
SEP = "\t"

LANDED = "LANDED"
QUEUED = "QUEUED"
NO_FILE_PROVENANCE = "无工单文件·凭并树提交"
HAND_PROVENANCE = "总控亲签工单·无机器字段"

EXIT_OK = 0
EXIT_DRIFT = 2
EXIT_SHAPE = 3
EXIT_STATUS = 4
EXIT_VERBATIM = 5

NUMBER_CHAIN = r"R\d+(?:\s*[\uff0b+]\s*R\d+)*"
CHAIN_HEAD = re.compile(r"^(" + NUMBER_CHAIN + r")([^：:]*)")
FENCE_OPEN = re.compile(r'^```verbatim source="([^"]+)"[ \t]*$')
FIELD_NUMBER = re.compile(r"^\*\*号\*\*[：:]\s*(R\d+)\s*$")
FIELD_BASE = re.compile(r"^\*\*基点\*\*[：:]\s*(\S+)\s*$")
FIELD_DOMAIN = re.compile(r"^\*\*写域\*\*[：:]\s*$")
BULLET_TICK = re.compile(r"^\s*-\s+`([^`]+)`")
SECTION_HEADING = re.compile(r"^#{2,3}\s*写域")
FILE_NUMBER = re.compile(r"^(R\d+)")
BACKTICK_TOKEN = re.compile(r"`([^`\n]+)`")
LINE_POINTER = re.compile(r"[\w\-./\\]+\.(?:py|md|tsv|json|toml|ya?ml|sh|sql|csv)[:]\d")


class SpecError(Exception):
    """工单里的机器字段或出处谓词不合法。"""


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise SpecError(f"git {' '.join(args)} 失败 rc={proc.returncode}：{proc.stderr.strip()}")
    return proc.stdout


def landing_numbers(subject: str) -> list[str]:
    """并树提交标题 -> 本枚落地的单号；形状之外的（保活／并树后的账）不算。"""
    match = CHAIN_HEAD.match(subject)
    if not match:
        return []
    tail = match.group(2)
    if "尚未" in tail:
        return []
    for hit in re.finditer("并树", tail):
        if hit.start() > 24:
            continue
        if "未" in tail[max(0, hit.start() - 2):hit.start()]:
            continue
        if tail[hit.end():hit.end() + 1] in ("后", "随"):
            continue
        return [n.strip() for n in re.split(r"\s*[\uff0b+]\s*", match.group(1))]
    return []


def landing_commits(repo: Path) -> dict[str, tuple[str, str]]:
    """号 -> 最新一枚并树提交（sha, 标题）。只跑 git log，不碰工作区状态。"""
    table: dict[str, tuple[str, str]] = {}
    for line in git(repo, "log", "--pretty=format:%H\x01%s").split("\n"):
        if "\x01" not in line:
            continue
        sha, subject = line.split("\x01", 1)
        for number in landing_numbers(subject):
            table.setdefault(number, (sha, subject))
    return table


def read_source(repo: Path, rel: str) -> str:
    path = repo / rel
    if not path.is_file():
        raise SpecError(f"出处源文件不存在：{rel}")
    return path.read_text(encoding="utf-8")


def s21_table_cells(text: str, number: str, column: str) -> list[str]:
    """在表头第一格为「单号」的那一张表里找 RNNN 行；别的表里的同号行不算。

    账面里这些表在行间留了空行，所以空行不切断表块，正文才切断。
    """
    rows: list[str] = []
    block: list[str] = []

    def scan(block_lines: list[str]) -> None:
        header = None
        for line in block_lines:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if header is None:
                if len(cells) >= 2 and cells[0] == "单号" and column in cells:
                    header = cells
                continue
            if cells and cells[0] == f"**{number}**" and len(cells) == len(header):
                rows.append(cells[header.index(column)])

    for line in text.split("\n"):
        if line.startswith("|") or not line.strip():
            block.append(line)
            continue
        if block:
            scan(block)
            block = []
    if block:
        scan(block)
    return rows


def paren_after(text: str, anchor: str) -> list[str]:
    hits = []
    start = 0
    while True:
        at = text.find(anchor, start)
        if at < 0:
            return hits
        open_at = text.find("\uff08", at + len(anchor))
        if open_at < 0:
            return hits
        depth = 0
        for i in range(open_at, len(text)):
            ch = text[i]
            if ch == "\uff08":
                depth += 1
            elif ch == "\uff09":
                depth -= 1
                if depth == 0:
                    hits.append(text[open_at + 1:i])
                    break
        start = at + len(anchor)


def extract_source(repo: Path, spec: str) -> str:
    parts = spec.split("::")
    kind = parts[0] if parts else ""
    if kind == "S21CELL" and len(parts) == 4:
        rows = s21_table_cells(read_source(repo, parts[1]), parts[2], parts[3])
        if len(rows) != 1:
            raise SpecError(f"出处谓词命中 {len(rows)} 枚（要恰好 1 枚）：{spec}")
        return rows[0]
    if kind == "LINE" and len(parts) == 3:
        lines = [l for l in read_source(repo, parts[1]).split("\n") if parts[2] in l]
        if len(lines) != 1:
            raise SpecError(f"出处谓词命中 {len(lines)} 行（要恰好 1 行）：{spec}")
        return lines[0].rstrip()
    if kind == "PAREN" and len(parts) == 3:
        rows = paren_after(read_source(repo, parts[1]), parts[2])
        if len(rows) != 1:
            raise SpecError(f"出处谓词命中 {len(rows)} 枚括号（要恰好 1 枚）：{spec}")
        return rows[0]
    raise SpecError(f"出处谓词形状不认识（S21CELL／LINE／PAREN）：{spec}")

class Ticket:
    """一枚 docs/tickets/RNNN*.md 的机器可读形状。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        text = path.read_text(encoding="utf-8")
        self.lines = text.split("\n")
        self.specs: list[str] = []
        self.blocks: list[str] = []
        self._read_blocks()
        found_number = None
        found_base = "-"
        found_domain: list[str] = []
        for line in self.lines:
            match = FIELD_NUMBER.match(line)
            if match:
                found_number = match.group(1)
                continue
            match = FIELD_BASE.match(line)
            if match:
                found_base = match.group(1)
                continue
            if FIELD_DOMAIN.match(line):
                found_domain = self._bullets_after(self.lines.index(line))
        self.hand_signed = found_number is None
        stem = FILE_NUMBER.match(path.name)
        if self.hand_signed:
            if not stem:
                raise SpecError(f"{path.name}: 既无机器字段 **号**，文件名也没有 R 号，尺读不出这一枚")
            self.number = stem.group(1)
            self.base = "-"
            self.domain = self._domain_from_section()
            if self.specs:
                raise SpecError(f"{path.name}: 亲签单不许带 verbatim 出处块（机器字段缺失）")
            self.provenance = HAND_PROVENANCE
        else:
            self.number = found_number
            if stem and stem.group(1) != found_number:
                raise SpecError(f"{path.name}: 文件名说 {stem.group(1)}，机器字段说 {found_number}")
            self.base = found_base
            self.domain = found_domain
            if not self.domain:
                raise SpecError(f"{path.name}: **写域**： 段落里没有反引号路径")
            self.provenance = self.specs[0] if self.specs else "无出处块"
        if not self.hand_signed and len(self.specs) != len(self.blocks):
            raise SpecError(f"{path.name}: 出处块与围栏数量不等（{len(self.specs)} vs {len(self.blocks)}）")

    def _read_blocks(self) -> None:
        index = 0
        while index < len(self.lines):
            match = FENCE_OPEN.match(self.lines[index])
            if not match:
                index += 1
                continue
            self.specs.append(match.group(1))
            body: list[str] = []
            index += 1
            while index < len(self.lines) and self.lines[index] != "```":
                body.append(self.lines[index])
                index += 1
            if index >= len(self.lines):
                raise SpecError(f"{path.name}: verbatim 围栏没有闭合")
            self.blocks.append("\n".join(body))
            index += 1

    def _bullets_after(self, start: int) -> list[str]:
        items: list[str] = []
        for line in self.lines[start + 1:]:
            if line.startswith("#"):
                break
            match = BULLET_TICK.match(line)
            if match:
                items.append(match.group(1))
        return items

    def _domain_from_section(self) -> list[str]:
        """亲签单的写域：取「## 写域」那一节里的反引号路径（bullet 或 inline 都算）。"""
        items: list[str] = []
        inside = False
        for line in self.lines:
            if SECTION_HEADING.match(line):
                inside = True
                continue
            if not inside:
                continue
            if line.startswith("#"):
                break
            for token in BACKTICK_TOKEN.findall(line):
                if token not in items:
                    items.append(token)
        return items

    def naked_lines(self) -> list[str]:
        """去掉 verbatim 围栏之后的正文（行号棘轮只量这一部分）。"""
        out: list[str] = []
        inside = False
        for line in self.lines:
            if FENCE_OPEN.match(line):
                inside = True
                continue
            if inside:
                if line == "```":
                    inside = False
                continue
            out.append(line)
        return out


def ticket_files(tickets: Path) -> list[Path]:
    return sorted(p for p in tickets.glob("R*.md") if p.is_file())


def build_rows(repo: Path, tickets: Path) -> tuple[list[Ticket], list[list[str]]]:
    cards = [Ticket(path) for path in ticket_files(tickets)]
    table = landing_commits(repo)
    by_number = {card.number: card for card in cards}
    rows: list[list[str]] = []
    for number in sorted(set(by_number) | set(table), key=lambda n: int(n[1:])):
        card = by_number.get(number)
        if number in table:
            sha = table[number][0]
            status = LANDED
            base = sha[:12]
            provenance = card.provenance if card else NO_FILE_PROVENANCE
        else:
            if card is None:
                continue
            status = QUEUED
            base = card.base
            provenance = card.provenance
        domain = ", ".join(card.domain) if card and card.domain else "-"
        rows.append([number, status, domain, base, provenance])
    return cards, rows


def render(rows: list[list[str]]) -> str:
    lines = [SEP.join(COLUMNS)]
    lines.extend(SEP.join(row) for row in rows)
    return "\n".join(lines) + "\n"


def parse_tsv(text: str) -> list[list[str]]:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    rows = []
    for line in lines[1:]:
        cells = line.split(SEP)
        if len(cells) != len(COLUMNS):
            raise SpecError(f"索引行字段数不是 {len(COLUMNS)} 枚：{line[:60]}")
        rows.append(cells)
    return rows


def diff_rows(expected: list[list[str]], actual: list[list[str]]) -> list[str]:
    problems: list[str] = []
    if len(expected) != len(actual):
        problems.append(f"枚数不合：现算 {len(expected)} 枚，盘上 {len(actual)} 枚")
    for position, want in enumerate(expected, start=2):
        if position - 2 >= len(actual):
            problems.append(f"索引第 {position} 行缺件：{' | '.join(want)}")
            continue
        got = actual[position - 2]
        if want != got:
            fields = [f"{name}：{w}!={g}" for name, w, g in zip(COLUMNS, want, got) if w != g]
            problems.append(f"索引第 {position} 行（{want[0]}）差在 {'；'.join(fields)}")
    seen = {row[0] for row in actual}
    for position, got in enumerate(actual, start=2):
        if position - 2 >= len(expected) and got[0] not in seen:
            problems.append(f"索引第 {position} 行是多出来的手改货：{got[0]}")
    return problems


def resolve_commit(repo: Path, sha: str) -> bool:
    proc = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
                          capture_output=True, text=True, encoding="utf-8")
    return proc.returncode == 0

def check_shape(repo: Path, tickets: Path) -> list[str]:
    problems: list[str] = []
    try:
        cards = [Ticket(path) for path in ticket_files(tickets)]
    except SpecError as error:
        return [f"工单形状读不出来：{error}"]
    for card in cards:
        if not re.match(r"^R\d+$", card.number):
            problems.append(f"{card.path.name}: 号不合法：{card.number}")
        for spec in card.specs:
            try:
                text = extract_source(repo, spec)
            except SpecError as error:
                problems.append(f"{card.number}: {error}")
                continue
            if not text.strip():
                problems.append(f"{card.number}: 出处谓词抄出来是空的：{spec}")
    return problems


def first_difference(want: str, got: str) -> int:
    for position, (a, b) in enumerate(zip(want, got)):
        if a != b:
            return position
    return min(len(want), len(got))


def check_verbatim(repo: Path, cards: list[Ticket]) -> list[str]:
    problems: list[str] = []
    for card in cards:
        for position, (spec, block) in enumerate(zip(card.specs, card.blocks), start=1):
            label = f"{card.number} 第 {position} 块（出处 {spec}）"
            try:
                source = extract_source(repo, spec)
            except SpecError as error:
                problems.append(f"{label}: {error}")
                continue
            if source == block:
                continue
            at = first_difference(source, block)
            problems.append(
                f"{label} 被改了字：自第 {at + 1} 个字符起与源文件不合（源里是 {source[at:at + 24]!r}，"
                f"盘上是 {block[at:at + 24]!r}）")
    return problems


def check_status(repo: Path, tickets: Path, index_text: str) -> tuple[list[str], list[list[str]]]:
    problems: list[str] = []
    _, expected = build_rows(repo, tickets)
    try:
        actual = parse_tsv(index_text)
    except SpecError as error:
        return [f"索引形状不合：{error}"], expected
    problems.extend(diff_rows(expected, actual))
    for row in actual:
        base = row[3]
        if base == "-":
            continue
        if not re.match(r"^[0-9a-f]{7,40}$", base):
            problems.append(f"{row[0]}: 基点不是 sha 也不是 '-'：{base}")
            continue
        if not resolve_commit(repo, base):
            problems.append(f"{row[0]}: 索引写的基点 {base} 在 git 里现取不到任何提交")
    return problems, expected


def check_drift(tickets: Path, index_text: str, regenerated: str) -> list[str]:
    if index_text == regenerated:
        return []
    if index_text.replace("\r\n", "\n") == regenerated.replace("\r\n", "\n"):
        print("提示：盘上那份与现跑产物只差行尾（core.autocrlf 在 checkout 时改的），内容逐行相等")
        return []
    want = regenerated.split("\n")
    got = index_text.split("\n")
    problems = []
    for position in range(max(len(want), len(got))):
        line = position + 1
        left = want[position] if position < len(want) else "<没有这一行>"
        right = got[position] if position < len(got) else "<没有这一行>"
        if left != right:
            problems.append(f"索引第 {line} 行不等：现算 [{left}] 盘上 [{right}]")
    problems.insert(0, f"索引是生成物，盘上那份与现跑生成器不等（{len(index_text.encode('utf-8'))} B vs "
                       f"{len(regenerated.encode('utf-8'))} B）")
    return problems


def check_pointers(repo: Path, tickets: Path, cards: list[Ticket]) -> list[str]:
    """行号禁令（AGENTS.md 病根处置③）：只量本单货，不啃 verbatim 围栏里的源文。"""
    problems: list[str] = []
    for card in cards:
        for line in card.naked_lines():
            hit = LINE_POINTER.search(line)
            if hit:
                problems.append(f"{card.number}: {card.path.name} 正文里出现行号坐标 {hit.group(0)!r}")
    index = tickets / INDEX_NAME
    if index.is_file():
        for line in index.read_text(encoding="utf-8").split("\n"):
            hit = LINE_POINTER.search(line)
            if hit:
                problems.append(f"索引本体出现行号坐标 {hit.group(0)!r}：{line[:60]}")
    return problems


def report(stage: str, problems: list[str]) -> int:
    if not problems:
        print(f"[{stage}] 过")
        return EXIT_OK
    print(f"[{stage}] 红，共 {len(problems)} 条：")
    for problem in problems:
        print(f"  - {problem}")
    return len(problems)


def command_write(repo: Path, tickets: Path) -> int:
    cards, rows = build_rows(repo, tickets)
    text = render(rows)
    index = tickets / INDEX_NAME
    index.write_bytes(text.encode("utf-8"))
    landed = sum(1 for row in rows if row[1] == LANDED)
    print(f"写出 {index}：{len(rows)} 行／{len(text.encode('utf-8'))} B／LANDED {landed} QUEUED {len(rows) - landed}"
          f"／工单文件 {len(cards)} 枚")
    return EXIT_OK


def command_check(repo: Path, tickets: Path) -> int:
    index = tickets / INDEX_NAME
    if not index.is_file():
        print(f"[判据 1] 红：盘上没有 {index}，先跑 --write")
        return EXIT_DRIFT
    _, rows = build_rows(repo, tickets)
    problems = check_drift(tickets, index.read_text(encoding="utf-8"), render(rows))
    return EXIT_OK if report("判据 1 · 重跑生成器逐字节对盘", problems) == EXIT_OK else EXIT_DRIFT


def command_verify(repo: Path, tickets: Path) -> int:
    index = tickets / INDEX_NAME
    if not index.is_file():
        print(f"[verify] 红：盘上没有 {index}")
        return EXIT_SHAPE
    codes = {EXIT_SHAPE: "形状", EXIT_STATUS: "状态", EXIT_VERBATIM: "判据原文", EXIT_DRIFT: "逐字节"}
    stages = [
        ("工单形状与出处谓词（判据 3）", lambda: check_shape(repo, tickets), EXIT_SHAPE),
        ("状态由 git 现查（判据 2）", lambda: check_status(repo, tickets, index.read_text(encoding="utf-8"))[0], EXIT_STATUS),
        ("判据原文逐字符回读源文件（判据 3·5）", lambda: check_verbatim(repo, [Ticket(p) for p in ticket_files(tickets)]), EXIT_VERBATIM),
        ("重跑生成器逐字节对盘（判据 1）", lambda: check_drift(tickets, index.read_text(encoding="utf-8"),
                                                            render(build_rows(repo, tickets)[1])), EXIT_DRIFT),
        ("行号棘轮（交付第 5 条）", lambda: check_pointers(repo, tickets, [Ticket(p) for p in ticket_files(tickets)]), EXIT_SHAPE),
    ]
    cards, rows = build_rows(repo, tickets)
    blocks = sum(len(card.specs) for card in cards)
    print(f"盘面读数：工单文件 {len(cards)} 枚（亲签 {len([c for c in cards if c.hand_signed])} 枚）／"
          f"索引 {len(rows)} 行／逐字块 {blocks} 枚")
    for label, runner, code in stages:
        problems = runner()
        if report(label, problems) != EXIT_OK:
            print(f"退出码 {code}（{codes[code]}）")
            return code
    print("全部判据过，退出码 0")
    return EXIT_OK


def command_cost(repo: Path, tickets: Path) -> int:
    followup = (repo / FOLLOWUP).read_bytes()
    board = (repo / BOARD).read_bytes()
    index = (tickets / INDEX_NAME).read_bytes()
    machine = [p for p in ticket_files(tickets) if Ticket(p).specs]
    if not machine:
        print("没有带逐字块的工单，取不到单枚样本")
        return EXIT_SHAPE
    sample = max(machine, key=lambda p: p.stat().st_size)
    before = len(followup) + len(board)
    after = len(index) + sample.stat().st_size
    print(f"改前必读＝跟进单 {len(followup)} B ＋看板 {len(board)} B ＝ {before} B")
    print(f"改后必读＝index.tsv {len(index)} B ＋单枚工单 {sample.name} {sample.stat().st_size} B ＝ {after} B")
    print(f"倍数＝{before / after:.1f}x（省下 {before - after} B）")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="docs/tickets/index.tsv 的派生生成器与校验尺")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="生成 index.tsv")
    group.add_argument("--check", action="store_true", help="判据 1：现跑产物逐字节对盘")
    group.add_argument("--verify", action="store_true", help="判据 1·2·3·5 全部校验")
    group.add_argument("--cost", action="store_true", help="判据 6：每班开工必读字节数改前／改后")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]), help="取 git 与源文件的那棵树")
    parser.add_argument("--tickets-dir", default=None, help="反证牙用：指一份 docs/tickets 的盘上副本")
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    tickets = Path(args.tickets_dir).resolve() if args.tickets_dir else repo / TICKETS_DIR
    if not tickets.is_dir():
        print(f"目录不存在：{tickets}")
        return EXIT_SHAPE
    try:
        if args.write:
            return command_write(repo, tickets)
        if args.check:
            return command_check(repo, tickets)
        if args.verify:
            return command_verify(repo, tickets)
        return command_cost(repo, tickets)
    except SpecError as error:
        print(f"形状红：{error}")
        return EXIT_SHAPE


if __name__ == "__main__":
    sys.exit(main())