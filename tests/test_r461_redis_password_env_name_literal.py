"""R461 · 字面量钉：开窗道里 Redis 口令的 env 名只许是 `REDIS_PASSWORD`（判据③）。

病根不是「有没有人写错」，是**两枚名字相近的口令至今没有一件东西把它们隔开**：
`REDIS_PASSWORD` 是 redis 的，`EB_EVAL_PASSWORD` 是跑分账号 `evalbot` 的登录口令
（看板 §3108 定档，走 `EVAL_PASSWORD` 那条道）。本班那枚手写开窗驱动取错了后者，
`redis-cli -a <错口令>` 把错误写进 stderr、stdout 空，下游 `wc -l` 数成 0 ⇒ 制度性假绿。

规则只咬一个形状：**一枚拿口令连 Redis 的件**里，出现在「口令位」上的 env 名如果不是
`REDIS_PASSWORD`，当场红。三格边界，逐格有钉：
  1 面：只扫 `scripts/*.py`（开窗道住这里）。`app/**` 走 `REDIS_URL` 注入且属本单禁域，
    不在面上 —— 扩面就会造出一枚永远咬不准的假门。
  2 位：「口令位」＝赋值给 `*password`／`*passwd`／`*pw` 的右值、`password=` 实参、
    名字以 password 结尾的函数的整个函数体。散文里提一句 `EB_EVAL_PASSWORD`（错误提示
    文案就是）不算位 —— 这一格正是「别把正确用法一并喊红」要求的那一格。
  3 豁免：同一件里确实还要登 evalbot 的，写一行 `R461-EVALBOT-CREDENTIAL` 并同段写明理由。
    令牌不许撒着写：令牌枚数不等于被豁免站点枚数 ⇒ 红（R453 同一口径）。

离线：只做 AST 读法与文本现读，不起子进程、不连任何 Redis。合成源落 tmp_path 影子件。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
#: 面：开窗道住在这里。app/** 与 frontend/** 是禁域，deploy/*.yml 的插值不属这枚钉。
LANE_DIR = REPO / "scripts"
GATE = LANE_DIR / "eval_window_answer_cache_gate.py"

ALLOWED_ENV = "REDIS_PASSWORD"
WRONG_ENV = "EB_EVAL_PASSWORD"
SANCTION = "R461-EVALBOT-CREDENTIAL"

#: 一枚件「拿口令连 Redis」的形状。文本级宽进面，再由「位」收出去。
REDIS_MARKER_RE = re.compile(
    r"redis-cli|redis\.Redis|StrictRedis|redis\.from_url|get_redis|RedisCli|requirepass")
#: env 名的形状：全大写、含 PASSWORD。句子与说明文字匹配不上（这就是「位」的收口）。
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*PASSWORD[A-Z0-9_]*$")
PASSWORD_TARGET_RE = re.compile(r"(password|passwd|_?pw)$", re.I)
PASSWORD_KEYWORDS = frozenset({"password", "passwd"})


def module_constants(tree: ast.Module) -> dict[str, str]:
    """模块级 `NAME = "字符串"`：换名那一格靠这张表追一跳。"""
    table: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant) \
                    and isinstance(node.value.value, str):
                table[target.id] = node.value.value
    return table


def names_in(subtree: ast.AST, constants: dict[str, str]) -> list[tuple[int, str]]:
    """从一枚子树里收出「像 env 名」的字符串：字面量，以及能查到值的模块级常量。"""
    found: list[tuple[int, str]] = []
    for node in ast.walk(subtree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and ENV_NAME_RE.match(node.value):
            found.append((node.lineno, node.value))
        elif isinstance(node, ast.Name) and ENV_NAME_RE.match(constants.get(node.id, "")):
            found.append((node.lineno, constants[node.id]))
    return found


def credential_positions(tree: ast.Module) -> list[dict]:
    """所有「口令位」：口令变量的右值、password= 实参、以 password 结尾的函数体。"""
    spots: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and PASSWORD_TARGET_RE.search(target.id):
                    spots.append({"line": node.lineno, "kind": "口令变量的右值", "expr": node.value})
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg in PASSWORD_KEYWORDS:
                    spots.append({"line": node.lineno, "kind": "password 实参", "expr": keyword.value})
        elif isinstance(node, ast.FunctionDef) and PASSWORD_TARGET_RE.search(node.name):
            spots.append({"line": node.lineno, "kind": "取口令的函数", "expr": node})
    return spots


def scan_source(source: str, name: str) -> list[dict]:
    """扫一枚件。不在面上（不连 redis）整件放行；令牌与站点不配也算违规。"""
    tokens = source.count(SANCTION)
    if not REDIS_MARKER_RE.search(source):
        return [] if tokens == 0 else [{"file": name, "line": 0, "kind": "豁免令牌撒着写",
                                       "env": f"令牌 {tokens} 枚 / 站点 0 枚"}]
    tree = ast.parse(source)
    constants = module_constants(tree)
    lines = source.splitlines()
    findings: list[dict] = []
    sanctioned = 0
    for spot in credential_positions(tree):
        for _line, env_name in names_in(spot["expr"], constants):
            if env_name == ALLOWED_ENV:
                continue
            window = "\n".join(lines[max(spot["line"] - 2, 0):spot["line"]])
            if SANCTION in window:
                sanctioned += 1
                continue
            findings.append({"file": name, "line": spot["line"], "kind": spot["kind"],
                             "env": env_name})
    if tokens != sanctioned:
        findings.append({"file": name, "line": 0, "kind": "豁免令牌撒着写",
                         "env": f"令牌 {tokens} 枚 / 站点 {sanctioned} 枚"})
    return findings


def lane_files() -> list[Path]:
    return sorted(LANE_DIR.glob("*.py"))


def scan_lane() -> list[dict]:
    findings: list[dict] = []
    for path in lane_files():
        findings.extend(scan_source(path.read_text(encoding="utf-8-sig"),
                                   str(path.relative_to(REPO))))
    return findings


def render(findings: list[dict]) -> str:
    return "; ".join(f"{item['file']}:{item['line']} {item['kind']} = {item['env']}"
                     for item in findings)


def shadow(tmp_path: Path, name: str, source: str) -> str:
    path = tmp_path / name
    path.write_text(source.lstrip("\n"), encoding="utf-8", newline="\r\n")
    return path.read_text(encoding="utf-8")


#: 本班现场那枚手写驱动的形：从表里取错名字，再拼进 docker exec 的 -e RG=。
DRIVER_SUBSCRIPT = """
import subprocess

CONTAINER = "enterprise-brain-redis-1"


def count_cached(values):
    password = values['EB_EVAL_PASSWORD']
    inner = 'redis-cli --no-auth-warning -a "$RG" --scan --pattern "answer:*" | wc -l'
    return subprocess.run(['docker', 'exec', '-e', 'RG=' + password, CONTAINER, 'sh', '-lc', inner])
"""

#: redis-py 的形：password= 实参直接指到跑分账号那枚。
DRIVER_CONSTRUCTOR = """
import os

import redis


def connect():
    return redis.Redis(host='127.0.0.1', port=6379, password=os.environ['EB_EVAL_PASSWORD'])
"""

#: 常量换名的形（＝反证 a 对量具本人做的事）：名字藏在模块级常量里，要追一跳才咬得到。
DRIVER_CONST_HOP = """
import redis

REDIS_PASSWORD_ENV = 'EB_EVAL_PASSWORD'


def read_redis_password(values):
    return values[REDIS_PASSWORD_ENV]


def connect(values):
    return redis.Redis(password=read_redis_password(values))
"""

#: 正确用法：登 evalbot 用 EB_EVAL_PASSWORD，这件一个字都不碰 redis ⇒ 不许红。
LOGIN_LANE = """
import os

import requests


def login(base):
    password = os.environ['EB_EVAL_PASSWORD']
    return requests.post(base + '/api/v1/login', json={'username': 'evalbot', 'password': password})
"""

#: 同一件两边都要：redis 用 REDIS_PASSWORD，evalbot 那行写明豁免令牌 ⇒ 绿，且令牌与站点相配。
SPLIT_LANE_SANCTIONED = """
import os

import redis
import requests


def connect():
    return redis.Redis(password=os.environ['REDIS_PASSWORD'])


def login(base):
    # R461-EVALBOT-CREDENTIAL：这一枚是跑分账号 evalbot 的登录口令，不连 redis
    password = os.environ['EB_EVAL_PASSWORD']
    return requests.post(base + '/login', json={'password': password})
"""

#: 只有令牌没有站点：拿它洗白别处，当场红。
STRAY_SANCTION_TOKEN = """
import redis


def connect():
    # R461-EVALBOT-CREDENTIAL
    return redis.Redis(password=os.environ['REDIS_PASSWORD'])
"""


def test_the_lane_surface_is_not_empty_and_holds_the_gate() -> None:
    """面不许空转：开窗道得有件，且新量具真在面上 —— 否则下面所有的绿都是 vacuous。"""
    files = lane_files()
    assert len(files) >= 10, f"面上只有 {len(files)} 枚件，扫描面塌了"
    assert GATE in files, "量具不在开窗道面上，这枚钉就咬不到它自己"


def test_in_tree_lane_is_clean() -> None:
    """判据③现状：在树的开窗道里没有任何「把 EB_EVAL_PASSWORD 当 Redis 口令」的形状。"""
    findings = scan_lane()
    assert findings == [], f"开窗道里连 redis 的口令名不对：{render(findings)}"


def test_the_gate_itself_is_green_and_names_the_trap_in_prose() -> None:
    """量具本人在面上且判绿：它引用的 env 名只有 REDIS_PASSWORD；错名字只出现在警告文案里。"""
    source = GATE.read_text(encoding="utf-8")
    assert scan_source(source, GATE.name) == []
    assert 'REDIS_PASSWORD_ENV = "REDIS_PASSWORD"' in source
    assert WRONG_ENV in source, "件里应当写明那枚相近的错名字（作为警告文案），但它不是口令位"


def test_counter_evidence_renaming_the_gates_own_constant_reddens_the_literal() -> None:
    """反证：把量具的口令 env 名换成跑分账号那枚 ⇒ 字面量钉当场点名（追常量那一跳就是牙）。"""
    source = GATE.read_text(encoding="utf-8")
    assert source.count('REDIS_PASSWORD_ENV = "REDIS_PASSWORD"') == 1
    mutated = source.replace('REDIS_PASSWORD_ENV = "REDIS_PASSWORD"',
                             'REDIS_PASSWORD_ENV = "EB_EVAL_PASSWORD"')
    findings = scan_source(mutated, GATE.name)
    assert findings, "换了名却读不出违规：这枚钉没咬着常量那一跳"
    assert {item["env"] for item in findings} == {WRONG_ENV}, render(findings)
    assert {item["kind"] for item in findings} == {"取口令的函数"}, render(findings)


def test_counter_evidence_hand_written_driver_shapes_are_named(tmp_path: Path) -> None:
    """三枚手写驱动的形状（下标取口令／构造函数实参／常量换名）各自点名一枚，红线带上位置。"""
    shapes = {"subscript": DRIVER_SUBSCRIPT, "constructor": DRIVER_CONSTRUCTOR,
              "const_hop": DRIVER_CONST_HOP}
    for name, template in shapes.items():
        source = shadow(tmp_path, f"driver_{name}.py", template)
        findings = scan_source(source, f"driver_{name}.py")
        assert len(findings) == 1, f"{name} 应当红一枚，实测 {render(findings)}"
        assert findings[0]["env"] == WRONG_ENV, findings
        assert findings[0]["line"] > 0, findings


def test_no_overbite_the_evalbot_login_lane_stays_green(tmp_path: Path) -> None:
    """🔴 不许扩面：登 evalbot 用 EB_EVAL_PASSWORD 是正确用法，这件不连 redis ⇒ 必须绿。"""
    source = shadow(tmp_path, "login_lane.py", LOGIN_LANE)
    assert scan_source(source, "login_lane.py") == []


def test_no_overbite_a_lane_that_needs_both_is_sanctionable(tmp_path: Path) -> None:
    """同一件既要 redis 又要登 evalbot：写明豁免令牌就绿，令牌枚数与站点枚数相配。"""
    source = shadow(tmp_path, "split_lane.py", SPLIT_LANE_SANCTIONED)
    assert scan_source(source, "split_lane.py") == []


def test_counter_evidence_a_stray_sanction_token_launderes_nothing(tmp_path: Path) -> None:
    """令牌不许撒着写：写了令牌却没有对应站点 ⇒ 当场红（R453 同一口径）。"""
    source = shadow(tmp_path, "launder.py", STRAY_SANCTION_TOKEN)
    findings = scan_source(source, "launder.py")
    assert len(findings) == 1, findings
    assert findings[0]["kind"] == "豁免令牌撒着写", findings


def test_counter_evidence_the_prose_mention_is_not_a_credential_position(tmp_path: Path) -> None:
    """警告文案里出现错名字不许红：那不是「拿它连 redis」的形状，红了就是造假日门。"""
    source = shadow(tmp_path, "prose.py", """
import os

import redis

HINT = '别用 EB_EVAL_PASSWORD，那是跑分账号的口令'


def connect(values):
    return redis.Redis(password=values['REDIS_PASSWORD'])
""")
    assert scan_source(source, "prose.py") == []
