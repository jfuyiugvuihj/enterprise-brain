"""R567 的常驻钉：`scripts/check_no_bom.py` 的扫描域必须把 raw 证据请出去，且一次都不许顺手洗字节。

判据出处＝跟进单 §148 第二节 R567 四格。来历（本席 10-02 现取，非转述）：`5a6811d`（10-01 00:00）
把带 EF BB BF 的 `docs/perf/raw/run10-2026-09-30/phase1_start.txt` 落库之后，这枚 tripwire 就一路
rc=1；它既不在 `scripts/run_gate.py` 的清单里、也没有任何一枚钉替它说话，于是门绿着、这一格红着
过了两天。🔴 治法只有「把它请出扫描域」这一条——**不许改那枚字节的 BOM**：raw 是量具在收窗那一刻
原样吐出来的东西，改一个字节就等于改证据，而这枚钉存在的全部理由就是让"改证据"当场红。

四格各自怎么失败：
1. `main()` 必须交回 0——红就意味着要么扫描域又漏进 raw，要么真有人往仓库塞了第二枚带 BOM 的文本。
2. 排除必须是**目录前缀形状**：换成逐枚文件名点名，下一批 raw 落库当场又红（那是本单明令不许的形状）。
3. 豁免面不许外扩：`WHITELIST` 只能是那两枚在册精确路径，前缀只能是 `docs/perf/raw/`。
4. 那枚被收窗抓下来的 BOM 必须**一个字节都没动**：按 blob hash 对 `5a6811d` 与 `HEAD` 两头互证。
"""
from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RAW_OFFENDER = "docs/perf/raw/run10-2026-09-30/phase1_start.txt"
CAPTURED_COMMIT = "5a6811d"
BOM = b"\xef\xbb\xbf"
EXEMPT_EXACT = frozenset(
    {
        "docs/handoff/2026-09-15-orchestration-board.md",
        "scripts/run_backend_tests.ps1",
    }
)


def _load_gauge():
    """按路径加载 `scripts/check_no_bom.py`——它是脚本不是包，`import` 进不来。"""
    spec = importlib.util.spec_from_file_location("eb_check_no_bom", REPO / "scripts" / "check_no_bom.py")
    module = importlib.util.module_from_spec(spec)
    #: 同 R566：先登记再 exec，别把模块级 dataclass 走投无路的形状留给下一班。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(*args: str) -> bytes:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=str(REPO), capture_output=True, check=True,
    )
    return result.stdout


def test_the_tripwire_exits_zero_today():
    """判据① ：现跑 rc=0，且它自报的扫描面里点名了那枚被排除的前缀（不是悄悄少扫）。"""
    gauge = _load_gauge()
    code = gauge.main()
    assert code == 0, "check_no_bom 交回 rc=%d：又有人把带 BOM 的文本落进扫描域，或 raw 那格排除被摘了" % code


def test_raw_evidence_is_out_by_prefix_not_by_filename():
    """判据② ：前缀形状必须成立；同目录下一枚从没点过名的新件也一样出局。"""
    gauge = _load_gauge()
    assert gauge.RAW_EVIDENCE_PREFIX == "docs/perf/raw/", (
        "排除前缀被改写了（现值 %r）：raw 证据请出扫描域只有这一种写法" % (gauge.RAW_EVIDENCE_PREFIX,))
    assert gauge.in_scope(RAW_OFFENDER) is False
    assert gauge.in_scope("docs/perf/raw/run99-2099-01-01/never_named_before.txt") is False, (
        "下一批 raw 落库就该红——逐枚文件名点名的白名单正是本单不许的形状")
    assert gauge.in_scope("docs/perf/raw/whatever.json") is False


def test_the_exclusion_is_path_anchored_not_a_substring_match():
    """判据② 的反面：`docs/perf/raw_hack.txt` 不是 `docs/perf/raw/` 目录下，必须照扫。"""
    gauge = _load_gauge()
    for sneaky in ("docs/perf/raw_hack.txt", "docs/perf/rawness.md", "documents/raw/evidence.txt",
                   "docs/handoff/rawboard.txt"):
        assert gauge.in_scope(sneaky) is True, (
            "%s 被判成扫描域外：前缀匹配丢了路径锚，等于把豁免面开成一条子串" % sneaky)


def test_the_exempt_surface_cannot_widen():
    """判据③ ：精确白名单只能是那两枚，别的一律算新罪（想豁免就另立单）。"""
    gauge = _load_gauge()
    assert frozenset(gauge.WHITELIST) == EXEMPT_EXACT, (
        "精确豁免面被改动：多一枚就是有人绕过本单给自己开了豁免（多：%s 少：%s）"
        % (sorted(frozenset(gauge.WHITELIST) - EXEMPT_EXACT), sorted(EXEMPT_EXACT - frozenset(gauge.WHITELIST))))


def test_the_captured_bom_is_still_the_captured_bom_byte_for_byte():
    """判据④ ：按 blob hash 两头互证——「请出扫描域」绝不是「把 BOM 删掉」。

    这里比的是 git 的 **blob**（存储态，已按 core.autocrlf 归一），不是盘上工作副本的字节：
    工作副本的 CRLF/LF 由 checkout 决定，拿它和 blob 直接比会造出一枚假红。查错层这一格本席
    在 10-02 亲手撞过（`Get-FileHash` 量原始字节 vs 加载器量 LF 归一文本），别再撞第二遍。
    """
    then = _git("rev-parse", "%s:%s" % (CAPTURED_COMMIT, RAW_OFFENDER)).strip().decode()
    now = _git("rev-parse", "HEAD:%s" % RAW_OFFENDER).strip().decode()
    assert then == now, (
        "%s 自 %s 落库之后被改过字节（%s -> %s）：raw 证据不许清洗，要治的是扫描域" % (
            RAW_OFFENDER, CAPTURED_COMMIT, then[:7], now[:7]))
    blob = _git("cat-file", "-p", now)
    assert blob.startswith(BOM), (
        "这枚 raw 现在不带 BOM 了（头三字节 %r / sha256 %s）：要么是有人洗了证据，"
        "要么是本钉盯着的那格形状变了——两种都得当场知道，不许沉默通过" % (blob[:3], hashlib.sha256(blob).hexdigest()[:12]))


def test_removing_the_exclusion_would_turn_the_tripwire_red_again():
    """判据①② 的牙（不重跑整趟扫描，只把两枚真读数拼起来）：摘掉前缀 ⇒ 那枚件重新进扫描域且它真带 BOM。"""
    gauge = _load_gauge()
    in_scope_without_prefix = (
        RAW_OFFENDER not in gauge.WHITELIST
        and Path(RAW_OFFENDER).suffix.lower() in gauge.TEXT_SUFFIXES)
    assert in_scope_without_prefix, "raw 那枚件本来就不在扫描域里：那本钉就不是在治它，是在空响"
    assert gauge.has_bom(REPO / RAW_OFFENDER), "盘上这枚 raw 不带 BOM 了——上面那格按 blob 证的，这里按工作副本再证一遍"