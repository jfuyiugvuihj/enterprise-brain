"""R461 · P-18 量具的行为钉与三把反证钉（判据①②）。

这枚件存在的理由只有一个：**认证失败时那份空 stdout 会被下游数成 0**，于是「开窗前该数必须
为 0」当场成立，库里实际还有 10 枚缓存键（runbook 订正三第 1 条＝09-25 第一次踩，本班 09-28
第二次踩，第二次是把 Redis 口令取成了跑分账号的 `EB_EVAL_PASSWORD`）。所以钉的不是「打印了
什么」，是「拿不到凭据时它敢不敢报数」。

全部离线：真连一律走替身。替身照 redis-cli 的回话形状做事 —— 口令不对就 `AUTH failed:
WRONGPASS`（stderr 那一支是本班现取的实际读数）或 `(error) NOAUTH Authentication required.`
（stdout 那一支，就是被 `| wc -l` 数成 0 的那一支），键空间是一枚 dict，收到没预期的命令就抛。
零容器、零网络、零模型，一个字的真 Redis 都不碰。

三把反证钉（判据②）各自摘掉一格，看红色落不落在本格上：
  a) 把口令 env 名换成 `EB_EVAL_PASSWORD`；
  b) 摘掉 `PING` 自证那格；
  c) 摘掉 `--check` 的「非 0 即拦」那格。
"""
from __future__ import annotations

import fnmatch
import importlib.util
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "eval_window_answer_cache_gate.py"

#: 两枚名字相近、用途完全不同的口令：本单病根就在这两枚上（看板 §3108 定档）。
REDIS_SECRET = "R" * 32
EVALBOT_SECRET = "E" * 24
#: 替身只认这一枚 ⇒ 任何「拿别的字符串来连」的形状都会落成认证失败。
SERVER_ACCEPTS = REDIS_SECRET

ANSWER_KEYS = [f"answer:{index:012d}" for index in range(10)]
OTHER_KEYS = ["ratelimit:user-1", "ratelimit:user-2", "ratelimit:user-3", "queue:job-1"]

#: 「N 枚」这种能被读成一条读数的形状：认证失败时它一个字都不许出现。
COUNT_SHAPE_RE = re.compile(r"\d+\s*枚")


def gate_source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def load_gate(tmp_path: Path, source: str, name: str = "gate_variant"):
    """把（可能被摘过牙的）源码落成件再导入：反证钉必须写真件里那一格，不许口头假设。"""
    path = tmp_path / f"{name}.py"
    path.write_text(source, encoding="utf-8", newline="\r\n")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mutate(source: str, old: str, new: str) -> str:
    """就地摘掉一格：目标必须唯一，摘错了就是一枚没咬着东西的假钉。"""
    assert source.count(old) == 1, f"反证目标在源里出现 {source.count(old)} 次，不是唯一一格：{old!r}"
    return source.replace(old, new)


def make_repo_root(tmp_path: Path, *, redis_line: bool = True) -> Path:
    """夹具：一枚长得像 deploy/.env.server 的件，两枚口令都在，值各不相同。"""
    root = tmp_path / "repo"
    deploy = root / "deploy"
    deploy.mkdir(parents=True, exist_ok=True)
    lines = []
    if redis_line:
        lines.append(f"REDIS_PASSWORD={REDIS_SECRET}")
    lines.append(f"EB_EVAL_PASSWORD={EVALBOT_SECRET}")
    (deploy / ".env.server").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


class StandInRedis:
    """替身的 redis-cli：口令不对就一切按认证失败回；键空间是 dict，DEL 逐枚点名才删。"""

    def __init__(self, accepts: str = SERVER_ACCEPTS, keys=ANSWER_KEYS + OTHER_KEYS, *,
                 auth_error_to_stderr: bool = True, delete_removes: bool = True,
                 collateral: str | None = None) -> None:
        self.accepts = accepts
        self.keys = {key: "v" for key in keys}
        self.auth_error_to_stderr = auth_error_to_stderr
        self.delete_removes = delete_removes
        self.collateral = collateral
        self.calls: list[list[str]] = []

    def transport(self, container: str, supplied: str, argv: list[str]) -> tuple[int, str, str]:
        self.calls.append(list(argv))
        if supplied != self.accepts:
            if self.auth_error_to_stderr:
                return 0, "", "AUTH failed: WRONGPASS invalid username-password pair or user is disabled.\n"
            # 假零那一支（本班第一次踩的形状）：错误全在 stdout，stderr 干净，rc=0，
            # 扫描交出空 stdout、dbsize 交出 0 —— 每个数都长得像「已经清干净了」。
            if argv[0] == "ping":
                return 0, "(error) NOAUTH Authentication required.\n", ""
            if argv[0] == "dbsize":
                return 0, "0\n", ""
            return 0, "", ""
        if argv[0] == "ping":
            return 0, "PONG\n", ""
        if argv[0] == "--scan":
            pattern = argv[argv.index("--pattern") + 1] if "--pattern" in argv else "*"
            names = sorted(key for key in self.keys if fnmatch.fnmatchcase(key, pattern))
            return 0, "".join(name + "\n" for name in names), ""
        if argv[0] == "dbsize":
            return 0, f"{len(self.keys)}\n", ""
        if argv[0] == "DEL":
            removed = 0
            for key in argv[1:]:
                if key in self.keys and self.delete_removes:
                    del self.keys[key]
                    removed += 1
            if self.collateral and self.collateral in self.keys:
                del self.keys[self.collateral]
            return 0, f"{removed}\n", ""
        raise AssertionError(f"替身收到了没预期的命令：{argv}")

    def families_touched(self) -> list[str]:
        return sorted(call[0] for call in self.calls)


def invoke(module, tmp_path: Path, argv: list[str], stand: StandInRedis, capsys):
    """起量具并收退出码＋stdout＋stderr：反证钉要看的是整张脸，不只是退出码。"""
    root = make_repo_root(tmp_path)
    rc = module.main(["--repo-root", str(root)] + list(argv), transport=stand.transport)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def test_the_gate_is_the_in_tree_entry_point() -> None:
    """判据①：仓内入口件必须在位，口令行的名字必须是 REDIS_PASSWORD。"""
    assert SCRIPT.is_file(), SCRIPT
    spec = importlib.util.spec_from_file_location("gate_in_tree", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.REDIS_PASSWORD_ENV == "REDIS_PASSWORD"
    assert module.ENV_FILE_RELATIVE == Path("deploy") / ".env.server"
    assert set(module.BANNED_COMMANDS) == {"flushall", "flushdb"}


def test_password_only_comes_from_the_env_file_not_the_process_environment(
        tmp_path: Path, capsys, monkeypatch) -> None:
    """判据①：口令只认 deploy/.env.server。进程环境里摆一枚同名也不许读（读了就是又放开那条道）。"""
    monkeypatch.setenv("REDIS_PASSWORD", EVALBOT_SECRET)
    root = make_repo_root(tmp_path, redis_line=False)
    stand = StandInRedis()
    rc = load_gate(tmp_path, gate_source()).main(
        ["--check", "--repo-root", str(root)], transport=stand.transport)
    captured = capsys.readouterr()
    assert rc != 0, "件里没有 REDIS_PASSWORD，进程环境里那枚不该被读到"
    assert "REDIS_PASSWORD 取不到" in captured.err
    assert not stand.calls, "口令都没取到就不该发出一条 redis 命令"


def test_missing_env_file_exits_nonzero(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "repo"
    (missing / "deploy").mkdir(parents=True)
    stand = StandInRedis()
    rc = load_gate(tmp_path, gate_source()).main(
        ["--check", "--repo-root", str(missing)], transport=stand.transport)
    captured = capsys.readouterr()
    assert rc != 0
    assert COUNT_SHAPE_RE.search(captured.out + captured.err) is None
    assert not stand.calls


def test_auth_failure_on_stderr_is_never_read_as_a_count(tmp_path: Path, capsys) -> None:
    """本班 09-28 那一支：redis-cli 把 WRONGPASS 写进 stderr ⇒ 停在这格，一个数都不报。"""
    stand = StandInRedis(accepts="another-redis-that-is-not-this-one")
    rc, out, err = invoke(load_gate(tmp_path, gate_source()), tmp_path, ["--check"], stand, capsys)
    assert rc != 0
    assert "WRONGPASS" in err and "stderr" in err, err
    assert COUNT_SHAPE_RE.search(out + err) is None, f"认证失败却报了枚数：{out + err}"
    assert "verdict: PASS" not in out + err


def test_ping_guard_refuses_the_fake_zero_shape(tmp_path: Path, capsys) -> None:
    """判据②第一道牙：NOAUTH 走 stdout、stderr 干净、扫描交出空 —— 只有 PING 能救这一格。"""
    stand = StandInRedis(accepts="another-redis-that-is-not-this-one", auth_error_to_stderr=False)
    rc, out, err = invoke(load_gate(tmp_path, gate_source()), tmp_path, ["--check"], stand, capsys)
    assert rc != 0
    assert "不是 'PONG'" in out, out
    assert COUNT_SHAPE_RE.search(out + err) is None, f"PING 没过却报了枚数：{out}"
    assert stand.families_touched() == ["ping"], "牙没过还去扫描：扫描出来的零就是假零"


def test_check_mode_passes_on_a_clean_cache(tmp_path: Path, capsys) -> None:
    stand = StandInRedis(keys=list(OTHER_KEYS))
    rc, out, _ = invoke(load_gate(tmp_path, gate_source()), tmp_path, ["--check"], stand, capsys)
    assert rc == 0, out
    assert "PING = PONG" in out and "answer:* = 0 枚" in out
    assert not any(call[0] == "DEL" for call in stand.calls)


def test_check_mode_refuses_a_warm_cache_without_deleting(tmp_path: Path, capsys) -> None:
    """判据③：--check 只判不清。带着 10 枚缓存必须拦下，而且不许自己动手清（自清自绿）。"""
    stand = StandInRedis()
    rc, out, _ = invoke(load_gate(tmp_path, gate_source()), tmp_path, ["--check"], stand, capsys)
    assert rc != 0, out
    assert "answer:* = 10 枚" in out and "不许开窗" in out, out
    assert not any(call[0] == "DEL" for call in stand.calls), "--check 模式不许发 DEL"
    assert len(stand.keys) == 14, "--check 动数据了"


def test_clear_mode_deletes_answer_keys_only(tmp_path: Path, capsys) -> None:
    """判据③：默认模式逐枚点名删 answer:*，别的族一枚不少。"""
    stand = StandInRedis()
    rc, out, _ = invoke(load_gate(tmp_path, gate_source()), tmp_path, [], stand, capsys)
    assert rc == 0, out
    assert sorted(stand.keys) == sorted(OTHER_KEYS), f"别的键被碰了：{sorted(stand.keys)}"
    dels = [call for call in stand.calls if call[0] == "DEL"]
    assert dels, "清缓存必须发 DEL"
    for call in dels:
        assert all(key.startswith("answer:") for key in call[1:]), call
        assert len(call) - 1 == 10, call
    assert "未发 FLUSHALL/FLUSHDB" in out
    assert "queue=1 ratelimit=3" in out, f"旁证·其它键族没打出来：{out}"
    assert "复扫 0 枚" in out and "verdict: PASS" in out


def test_clear_mode_reports_both_sides_of_the_side_evidence(tmp_path: Path, capsys) -> None:
    """判据④旁证：清前清后各报一次其它键族，两行都在、读数一致，才算自证没碰它们。"""
    stand = StandInRedis()
    rc, out, _ = invoke(load_gate(tmp_path, gate_source()), tmp_path, [], stand, capsys)
    assert rc == 0, out
    assert "旁证·其它键族 清前 = queue=1 ratelimit=3" in out, out
    assert "旁证·其它键族 清后 = queue=1 ratelimit=3" in out, out


def test_recount_that_stays_nonzero_redens(tmp_path: Path, capsys) -> None:
    """判据④：DEL 之后复扫仍非 0（这里模拟删不动）⇒ 非零退出，不许读成「已清」。"""
    stand = StandInRedis(delete_removes=False)
    rc, out, _ = invoke(load_gate(tmp_path, gate_source()), tmp_path, [], stand, capsys)
    assert rc != 0, out
    assert "复扫仍有 10 枚" in out and "没清干净" in out, out
    assert "verdict: PASS" not in out


def test_collateral_key_family_shrink_redens(tmp_path: Path, capsys) -> None:
    """判据④：别的族在这一趟里少了一枚 ⇒ 「只删了 answer:*」这句就是假的，拦下。"""
    stand = StandInRedis(collateral="queue:job-1")
    rc, out, _ = invoke(load_gate(tmp_path, gate_source()), tmp_path, [], stand, capsys)
    assert rc != 0, out
    assert "queue 1->0" in out and "别的键族在这一趟里变少了" in out, out
    assert "verdict: PASS" not in out


def test_unsafe_answer_key_shape_is_refused_before_any_delete(tmp_path: Path, capsys) -> None:
    """扫描里冒出带空格的键 ⇒ 不许按这个名字点名删（DEL 的参数表是拼出来的）。"""
    stand = StandInRedis(keys=["answer:bad key", "answer:ok0000000000"])
    rc, out, err = invoke(load_gate(tmp_path, gate_source()), tmp_path, [], stand, capsys)
    assert rc != 0
    assert "形状不对的答案键" in err, err
    assert not any(call[0] == "DEL" for call in stand.calls)


def test_flushall_is_refused_by_the_client(tmp_path: Path) -> None:
    """判据③：连直发 FLUSHALL 都过不了这一层，替身也就永远收不到那两条。"""
    gate = load_gate(tmp_path, gate_source())
    stand = StandInRedis()
    client = gate.RedisCli(secret=REDIS_SECRET, transport=stand.transport)
    with pytest.raises(gate.GateError, match="禁发 FLUSHALL"):
        client._run(["FLUSHALL"])
    with pytest.raises(gate.GateError, match="禁发 FLUSHDB"):
        client._run(["FLUSHDB"])
    assert not stand.calls


def test_two_scans_that_disagree_stop_the_judgement(tmp_path: Path, capsys) -> None:
    """两枚读数（--scan --pattern 与全库扫描）对不上 ⇒ 扫描本身不可信，不判（rc=2）。"""
    gate = load_gate(tmp_path, gate_source())

    def lying_transport(container, supplied, argv):
        if argv[0] == "ping":
            return 0, "PONG\n", ""
        if argv[0] == "--scan" and "--pattern" in argv:
            return 0, "answer:aaaa\nanswer:bbbb\n", ""
        if argv[0] == "--scan":
            return 0, "answer:aaaa\n", ""
        return 0, "2\n", ""

    root = make_repo_root(tmp_path)
    rc = gate.main(["--check", "--repo-root", str(root)], transport=lying_transport)
    captured = capsys.readouterr()
    assert rc != 0
    assert "两枚读数不一致" in captured.err, captured.err


def test_counter_evidence_a_swapping_the_password_env_name_reddens_without_a_count(
        tmp_path: Path, capsys) -> None:
    """反证 a：把口令 env 名换成跑分账号那枚 ⇒ 非零退出，且输出里不许有任何「N 枚」的形状。

    这正是本班 09-28 现场：`EB_EVAL_PASSWORD`（len=24）拿去连 redis，`WRONGPASS` 进 stderr，
    下游 `... | wc -l` 交出 0，纸面判据「开窗前该数必须为 0」当场成立。
    """
    swapped = mutate(gate_source(),
                     'REDIS_PASSWORD_ENV = "REDIS_PASSWORD"',
                     'REDIS_PASSWORD_ENV = "EB_EVAL_PASSWORD"')
    stand = StandInRedis()
    rc, out, err = invoke(load_gate(tmp_path, swapped), tmp_path, ["--check"], stand, capsys)
    assert rc != 0, f"取错口令却退了 0：{out}{err}"
    assert "口令=EB_EVAL_PASSWORD len=24" in out, "没自证用的是哪一枚 env 名，读数就无从追认"
    assert COUNT_SHAPE_RE.search(out + err) is None, f"认证没通过却报了枚数：{out}{err}"
    assert "verdict: PASS" not in out + err
    # 对照腿：同一枚夹具、同一台只认 REDIS_PASSWORD 的替身，在树的件是绿的 ⇒ 红在换名这一格。
    control = StandInRedis(keys=list(OTHER_KEYS))
    clean_rc, clean_out, _ = invoke(load_gate(tmp_path, gate_source()), tmp_path, ["--check"],
                                    control, capsys)
    assert clean_rc == 0, f"对照腿不绿，这台替身或这枚夹具本身有问题：{clean_out}"


def test_counter_evidence_b_removing_the_ping_guard_opens_the_fake_zero(
        tmp_path: Path, capsys) -> None:
    """反证 b：摘掉「PING 不等于 PONG 就停」这一格 ⇒ 在树的件红，摘了牙的件绿得发假。

    那枚绿的形状就是病灶原文：认证失败的零被当成「缓存已清」，打印 0 枚并判 PASS。
    """
    in_tree = StandInRedis(accepts="another-redis-that-is-not-this-one", auth_error_to_stderr=False)
    broken_rc, broken_out, _ = invoke(load_gate(tmp_path, gate_source()), tmp_path, ["--check"],
                                      in_tree, capsys)
    assert broken_rc != 0 and "不是 'PONG'" in broken_out, broken_out
    naked_source = mutate(gate_source(), '    if ping != "PONG":', '    if False:')
    naked = StandInRedis(accepts="another-redis-that-is-not-this-one", auth_error_to_stderr=False)
    naked_rc, naked_out, _ = invoke(load_gate(tmp_path, naked_source), tmp_path, ["--check"],
                                    naked, capsys)
    assert naked_rc == 0, f"摘掉 PING 自证后仍然非零，说明拦下来的是别的格：{naked_out}"
    assert "answer:* = 0 枚" in naked_out and "verdict: PASS" in naked_out, naked_out


def test_counter_evidence_c_removing_the_check_refusal_lets_a_warm_window_pass(
        tmp_path: Path, capsys) -> None:
    """反证 c：摆 10 枚假 answer:* 键 ⇒ 在树的件用 --check 拦下「带着缓存开窗」；摘掉那格就放行。"""
    warm = StandInRedis()
    rc, out, _ = invoke(load_gate(tmp_path, gate_source()), tmp_path, ["--check"], warm, capsys)
    assert rc != 0 and "库里带着 10 枚答案缓存" in out, out
    naked_source = mutate(gate_source(), "        if before.answer_count:", "        if False:")
    naked = StandInRedis()
    naked_rc, naked_out, _ = invoke(load_gate(tmp_path, naked_source), tmp_path, ["--check"],
                                    naked, capsys)
    assert naked_rc == 0, f"摘掉拦停这一格后仍然非零，红色不在本格：{naked_out}"
    assert "verdict: PASS" in naked_out, naked_out


def test_counter_evidence_mutations_target_three_distinct_cells() -> None:
    """三把钉子摘的是三格不同的东西：源里各出现一次，且互不相同。"""
    source = gate_source()
    cells = [
        'REDIS_PASSWORD_ENV = "REDIS_PASSWORD"',
        '    if ping != "PONG":',
        "        if before.answer_count:",
    ]
    assert len(set(cells)) == 3
    for cell in cells:
        assert source.count(cell) == 1, cell
