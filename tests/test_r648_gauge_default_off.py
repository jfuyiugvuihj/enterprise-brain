# -*- coding: utf-8 -*-
"""R648 判据⑤ —— 出厂默认关那一格必须回**显式「未量到」＋原因码**，不许把未量到扮成绿。

在册口径（本单派工词第 5 条）：不许 ``pytest.skip``、不许 ``xfail``、不许「没设 env 就当通过」。
⇒ 本件的每一枚用例在默认态都真跑一遍量具，判的是「产物说了什么」：

* 九枚腿逐枚回 ``status="unmeasured"`` + 唯一原因码 ``r648_real_pg_opt_in_not_declared``；
* 未量到的格子里**一个测量键都没有**（``walk_measurement_keys`` 数出来是空 ⇒ 伪 0 无处藏）；
* 子进程出口装了绊线，默认态绊线**一枚都不响**（响一枚就是「常驻件偷偷连库」）；
* 库名/文件名/语句文本三道闸在连库之前就拦：生产库名、非 ``r648_`` 假名、写域外的语句
  全部当场拒绝，且拒绝时不带一次真往返。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from _r648_gauge_harness import GAUGE_PATH, Tripwire, load_gauge


def default_report(tmp_path, **kwargs):
    """用**影子端**跑默认态：量具原件一个字不动，产物里的格子里不许出现任何测量键。"""
    gauge = load_gauge(tmp_path, "default_off")
    return gauge, gauge.run_report(env={}, **kwargs)


def test_default_report_declares_every_leg_unmeasured_with_the_named_reason_code(tmp_path):
    gauge, report = default_report(tmp_path)
    assert report["opt_in"]["env"] == gauge.OPT_IN_ENV
    assert report["opt_in"]["declared"] is False
    assert report["opt_in"]["reason_code"] == gauge.REASON_GATE_OFF
    assert tuple(report["legs"]) == gauge.LEG_NAMES, "腿的清单不许悄悄增删"
    for name, leg in report["legs"].items():
        assert leg["status"] == "unmeasured", name
        assert leg["reason_code"] == gauge.REASON_GATE_OFF, name
        assert leg["note"], name + "：未量到那一格必须说一句为什么没量"
    assert report["transport_calls"] == 0


def test_unmeasured_cells_carry_no_measurement_keys_at_all(tmp_path):
    """🔴 判据⑤的字面形状：未量到的格子里没有数值键，所以连一枚伪 0 都写不出来。"""
    gauge, report = default_report(tmp_path)
    hits = gauge.walk_measurement_keys(report["legs"], path="legs")
    assert hits == [], "未量到的格子里出现了测量键：" + ", ".join(hits[:8])
    assert sorted(report.keys()) == ["commands", "database", "generated_at", "legs", "opt_in",
                                     "tool", "transport_calls"]


def test_the_tripwire_never_rings_while_the_gate_is_off(tmp_path):
    gauge = load_gauge(tmp_path, "tripwire_off")
    wire = Tripwire(gauge).install()
    report = gauge.run_report(env={})
    assert wire.fired == 0, "默认态发过子进程：" + "; ".join(wire.calls)
    assert all(leg["status"] == "unmeasured" for leg in report["legs"].values())


def test_the_same_tripwire_rings_the_moment_the_gate_is_opened(tmp_path):
    """正控的另一半：绊线本身不是空炮——闸门一开它就响，所以上一枚用例的 0 是真读数。"""
    gauge = load_gauge(tmp_path, "tripwire_on")
    wire = Tripwire(gauge).install()
    report = gauge.run_report(env={gauge.OPT_IN_ENV: "on"}, legs=("identity",))
    assert wire.fired >= 1, "闸门开着却一枚都没尝试连库 ⇒ 那枚 0 是空的"
    assert report["legs"]["identity"]["status"] != "unmeasured"


@pytest.mark.parametrize("raw,declared", [
    ("", False), (" ", False), ("off", False), ("0", False), ("no", False),
    ("false", False), ("TRUE", True), ("on", True), ("1", True), ("Yes", True),
])
def test_the_gate_opens_only_for_the_named_opt_in_values(tmp_path, raw, declared):
    gauge = load_gauge(tmp_path, "gate_values")
    assert gauge.gate_declared(env={gauge.OPT_IN_ENV: raw}) is declared
    assert gauge.gate_declared(env={}) is False
def test_production_database_names_are_refused_before_any_connection(tmp_path):
    """连库姿势的禁区：生产库名一字节不许打；沙盒那一族的形状以在册 r633 为准。"""
    gauge = load_gauge(tmp_path, "db_guard")
    for name in sorted(gauge.PRODUCTION_DB_NAMES):
        with pytest.raises(gauge.GaugeRefused) as caught:
            gauge.assert_sandbox_database(name)
        assert caught.value.reason_code == "production_database_refused"
    assert gauge.assert_sandbox_database("eb_r59_sandbox") == "eb_r59_sandbox"
    for name in ("eb_r648_sandbox", "eb_r60_drill"):
        assert gauge.assert_sandbox_database(name) == name
    with pytest.raises(gauge.GaugeRefused) as caught:
        gauge.assert_sandbox_database("enterprise_brain_pytest")
    assert caught.value.reason_code == "database_not_in_sandbox_family"


def test_only_r648_prefixed_fake_filenames_may_be_written(tmp_path):
    gauge = load_gauge(tmp_path, "name_guard")
    assert gauge.assert_fake_filename("r648_doc01.md") == "r648_doc01.md"
    for name in ("MYO_私有化部署手册.txt", "r648/../etc/passwd", "r648.md", "other.md",
                 "r648_upper_name.MD", "r648_" + "x" * 60 + ".md"):
        with pytest.raises(gauge.GaugeRefused) as caught:
            gauge.assert_fake_filename(name)
        assert caught.value.reason_code == "filename_not_r648_fake"


def test_write_gate_passes_the_product_statement_and_refuses_the_forbidden(tmp_path):
    """写域闸的正控 = 产品那条 UPSERT 原文必须过闸；反控 = 越界的语句逐枚点名原因码。"""
    gauge = load_gauge(tmp_path, "write_gate")
    upsert = gauge.upsert_statement("r648_doc01.md", 3, 0)
    assert gauge.assert_write_script_allowed(upsert + "\n") == upsert + "\n"
    refusals = {
        "写域外的表": "DELETE FROM chunk_vectors WHERE filename LIKE 'r648\\_%';",
        "改结构的语句": "DROP TABLE document_activity_signals; -- r648_probe.md",
        "真库里的真名": "DELETE FROM document_activity_signals"
                       " WHERE filename = 'MYO_私有化部署手册.txt';",
        "空脚本": "\n",
    }
    for label, script in refusals.items():
        with pytest.raises(gauge.GaugeRefused) as caught:
            gauge.assert_write_script_allowed(script)
        assert caught.value.reason_code, label


def test_read_gate_refuses_writes(tmp_path):
    gauge = load_gauge(tmp_path, "read_gate")
    assert gauge.assert_select_only("SELECT count(*) FROM document_activity_signals")
    for sql in ("UPDATE document_activity_signals SET accepted_count = 1",
                "DELETE FROM document_activity_signals",
                "SELECT 1; DROP TABLE document_activity_signals"):
        with pytest.raises(gauge.GaugeRefused) as caught:
            gauge.assert_select_only(sql)
        assert caught.value.reason_code in ("read_gate_statement", "read_gate_forbidden_word")
    with pytest.raises(gauge.GaugeRefused):
        gauge.assert_read_script_allowed("BEGIN; SELECT 1; DELETE FROM document_activity_signals;")


def test_the_gauge_sends_the_products_own_statements_and_no_second_copy(tmp_path):
    """口径只有一份：打点与读回的语句都从产品源码现读，量具里没有第二份文本。"""
    gauge = load_gauge(tmp_path, "single_source")
    upsert = gauge.product_upsert_sql()
    rendered = gauge.upsert_statement("r648_doc01.md", 2, 5)
    for fragment in ("INSERT INTO document_activity_signals AS s",
                     "ON CONFLICT (filename) DO UPDATE SET",
                     "accepted_count = s.accepted_count + EXCLUDED.accepted_count",
                     "rejected_count = s.rejected_count + EXCLUDED.rejected_count",
                     "last_signal_at = NOW()"):
        assert fragment in " ".join(upsert.split()), fragment
        assert fragment in rendered, fragment
    assert "%s" not in rendered
    assert "first_signal_at = s.first_signal_at" not in rendered
    assert gauge.product_upsert_touches_first_signal_at() is False
    select = gauge.product_signal_select()
    assert select == ("SELECT filename, accepted_count, rejected_count"
                      " FROM document_activity_signals")
    #: 🔴 「口径只有一份」的机器证明：量具源码里没有第二份手抄的产品语句。
    source = GAUGE_PATH.read_bytes().decode("utf-8-sig")
    for second_copy in ("ON CONFLICT (filename) DO UPDATE SET",
                        "SELECT filename, accepted_count, rejected_count FROM"):
        assert second_copy not in source, "量具里手抄了第二份产品语句：" + second_copy


def test_artifact_path_must_stay_outside_the_repo(tmp_path):
    gauge = load_gauge(tmp_path, "artifact")
    with pytest.raises(gauge.GaugeRefused) as caught:
        gauge.assert_artifact_path_outside_repo(GAUGE_PATH)
    assert caught.value.reason_code == "artifact_inside_repo"
    outside = Path(str(tmp_path)) / "readout.json"
    assert gauge.assert_artifact_path_outside_repo(outside) == outside.resolve()


def test_reset_scripts_stay_inside_the_write_domain(tmp_path):
    """清账脚本本体（不连库）：只 DELETE 那一枚假名，过闸后才发给 psql。"""
    gauge = load_gauge(tmp_path, "reset_static")
    names = ("r648_doc01.md", "r648_doc03.md")
    script = "\n".join("DELETE FROM document_activity_signals WHERE filename = "
                       + gauge.sql_literal(name) + ";" for name in names)
    assert gauge.assert_write_script_allowed(script) == script
    assert "LIKE" not in script
    for name in names:
        assert name in script