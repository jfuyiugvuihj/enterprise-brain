# -*- coding: utf-8 -*-
"""R648 判据① 的「真库并发腿」—— ``document_activity_signals`` 在真 PG 上的打点读数。

R46 立案到今天，这张表只在大模型嘴里见过真库：在册 R525 量到的是「0 行 ⇒ 无可读」，所以
**两枚以上真连接同时打同一枚 filename** 这件事一次都没量过。本件把 2026-10-04 的真腿读数
（``R648_REAL_PG=on`` 亲跑，命令原文逐枚抄在
docs/testing/r648-real-pg-concurrency-2026-10-04.md）钉成机器事实：默认态只复算快照的内部对平，
一枚库都不连；复跑闸开着就当场重跑并逐格对账。🔴 全程没有 ``skip`` 可用——关着的那一格必须
回显式「未量到」＋原因码。

## 打的是哪台 PG（派工词第 3 条点名的三枚读数）

``current_database()=eb_r59_sandbox`` / ``inet_server_addr():port=127.0.0.1:5432`` /
``server_version=16.15 (Debian 16.15-1.pgdg12+2)``，数据目录 ``/var/lib/postgresql/data``：
容器内那台 PG（``enterprise-brain-postgres-1``）。🔴 该容器的 ``PortBindings`` 是 ``{}`` ⇒
宿主 5432 上 listened 的那枚一定是**野 PG**（R525 的面 B，连 ``schema_migrations`` 都没有），
直连它得到的必然是假绿 ⇒ 本件唯一的连接通道是 ``docker exec`` 进容器再走 TCP，
且一律带 ``-h 127.0.0.1``：容器内 unix socket 姿势下 ``inet_server_addr()`` 恒 NULL，
拿它自证「打的是哪台」等于没自证。
"""
from __future__ import annotations

from _r648_gauge_harness import REAL_PG_OPT_IN, load_gauge

SNAPSHOT_TAKEN = "2026-10-04"
IDENT_SERVER_VERSION = "16.15 (Debian 16.15-1.pgdg12+2)"

#: 真腿快照（逐格取自量具产物，进程号一类随跑次漂移的格剔掉后留在册）。
BOOKED = {
    "identity": {
        "show_server_version": "16.15 (Debian 16.15-1.pgdg12+2)",
        "container_port_bindings": "{}",
        "container_publishes_host_port": False,
        "databases_on_this_server": [
            "eb_r59_sandbox",
            "enterprise_brain",
            "postgres",
            "template0",
            "template1"
        ],
        "database_is_sandbox_family": True,
        "production_names_present": [
            "enterprise_brain",
            "postgres",
            "template0",
            "template1"
        ],
        "over_tcp": {
            "database": "eb_r59_sandbox",
            "inet_addr": "127.0.0.1/32",
            "inet_port": "5432",
            "server_version": "16.15 (Debian 16.15-1.pgdg12+2)",
            "data_directory": "/var/lib/postgresql/data"
        },
        "over_unix_socket": {
            "database": "eb_r59_sandbox",
            "inet_addr": "NULL",
            "inet_port": "NULL"
        }
    },
    "baseline": {
        "row_count": 0,
        "r648_rows": 0,
        "relation": "document_activity_signals",
        "database": "eb_r59_sandbox"
    },
    "concurrency": {
        "shape": "product_upsert_single_statement",
        "filename": "r648_concurrency_primary.md",
        "rows_before_wave": {
            "accepted_count": 0,
            "rejected_count": 0
        },
        "sessions": 8,
        "statements_per_session": 10,
        "concurrent_backends": 8,
        "expected": {
            "accepted_count": 80,
            "rejected_count": 80
        },
        "observed": {
            "accepted_count": 80,
            "rejected_count": 80
        },
        "lost_updates": [],
        "row_count": 1,
        "session_rc": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
        ],
        "distinct_backend_pids": 8
    },
    "read_then_write": {
        "shape": "client_read_then_write",
        "filename": "r648_control_read_then_write.md",
        "seed_rc": 0,
        "base": {
            "accepted_count": 1,
            "rejected_count": 0
        },
        "expected": {
            "accepted_count": 2,
            "rejected_count": 1
        },
        "observed": {
            "accepted_count": 1,
            "rejected_count": 1
        },
        "lost_updates": [
            {
                "column": "accepted_count",
                "expected": 2,
                "observed": 1,
                "missing": 1
            }
        ],
        "both_sessions_read_the_same_base": True,
        "concurrent_backends": 2,
        "session_rc": [
            0,
            0
        ],
        "victims_named": [
            {
                "lost_column": "accepted_count",
                "missing": 1,
                "expected_landed": 1,
                "actually_landed": 0,
                "victim_session": "S_A",
                "overwritten_by_session": "S_B",
                "landed_readings": {
                    "accepted_count": 0,
                    "rejected_count": 1
                }
            }
        ]
    },
    "mixed_columns": {
        "filename": "r648_mixed_columns.md",
        "unmarked_filename": "r648_never_marked.md",
        "sessions": 4,
        "rounds_per_session": 6,
        "concurrent_backends": 4,
        "expected": {
            "accepted_count": 12,
            "rejected_count": 12
        },
        "observed": {
            "accepted_count": 12,
            "rejected_count": 12
        },
        "lost_updates": [],
        "net_value": 0,
        "both_columns_nonzero": True,
        "read_back_through_product_reader": {
            "accepted": 12,
            "rejected": 12
        },
        "unmarked_row_absent_from_priors": True,
        "prior_value_at_net_zero_and_at_no_signal": {
            "five_five": 0.0,
            "zero_zero": 0.0,
            "absent": 0.0
        },
        "session_rc": [
            0,
            0,
            0,
            0
        ]
    },
    "timestamps": {
        "filename": "r648_timestamps.md",
        "waves": 4,
        "first_signal_at_rewritten": False,
        "first_signal_at_constant": True,
        "last_signal_at_monotonic_non_decreasing": True,
        "last_at_least_first": True,
        "max_backwards_step_ms": 0,
        "product_upsert_touches_first_signal_at": False,
        "row": {
            "accepted_count": 7,
            "rejected_count": 3
        },
        "expected_row": {
            "accepted_count": 7,
            "rejected_count": 3
        },
        "lost_updates": []
    },
    "constraints": {
        "zero_zero_probe_filename": "r648_probe_zero_zero.md",
        "zero_zero_rc": 3,
        "zero_zero_refused": True,
        "zero_zero_constraint_named_in_stderr": True,
        "rows_after_refusal": 0,
        "booked_constraint_names": [
            "document_activity_signals_accepted_check",
            "document_activity_signals_filename_length_check",
            "document_activity_signals_not_empty_check",
            "document_activity_signals_rejected_check"
        ],
        "booked_names_missing_live": [],
        "primary_key_count": 1,
        "unvalidated_constraints": [],
        "live_constraints": [
            {
                "conname": "document_activity_signals_accepted_check",
                "contype": "c",
                "convalidated": True
            },
            {
                "conname": "document_activity_signals_filename_length_check",
                "contype": "c",
                "convalidated": True
            },
            {
                "conname": "document_activity_signals_not_empty_check",
                "contype": "c",
                "convalidated": True
            },
            {
                "conname": "document_activity_signals_pkey",
                "contype": "p",
                "convalidated": True
            },
            {
                "conname": "document_activity_signals_rejected_check",
                "contype": "c",
                "convalidated": True
            }
        ]
    },
    "order": {
        "fake_name_map_pairs": 8,
        "fake_name_map_is_injective": True,
        "distinct_real_filenames": 8,
        "relabeled_concentration": {
            "5": 2,
            "12": 5,
            "40": 8
        },
        "signal_targets": [
            {
                "filename": "r648_doc01.md",
                "accepted": 10,
                "rejected": 7,
                "ranks": [
                    2,
                    13,
                    20,
                    31
                ]
            },
            {
                "filename": "r648_doc03.md",
                "accepted": 1,
                "rejected": 0,
                "ranks": [
                    7
                ]
            },
            {
                "filename": "r648_doc04.md",
                "accepted": 0,
                "rejected": 4,
                "ranks": [
                    10
                ]
            }
        ],
        "rows_seen_by_product_reader": 7,
        "ann_row_count": 40,
        "displacement": {
            "5": {
                "width": 5,
                "distinct_filenames": 2,
                "carriers_noted": 5,
                "max_abs_places_moved": 1,
                "carriers_shifted": 2,
                "bound_booked": 1,
                "bound_constant_in_module": 1,
                "within_bound": True,
                "no_signal_returns_same_object": True
            },
            "12": {
                "width": 12,
                "distinct_filenames": 5,
                "carriers_noted": 12,
                "max_abs_places_moved": 1,
                "carriers_shifted": 6,
                "bound_booked": 1,
                "bound_constant_in_module": 1,
                "within_bound": True,
                "no_signal_returns_same_object": True
            },
            "40": {
                "width": 40,
                "distinct_filenames": 8,
                "carriers_noted": 40,
                "max_abs_places_moved": 1,
                "carriers_shifted": 22,
                "bound_booked": 1,
                "bound_constant_in_module": 1,
                "within_bound": True,
                "no_signal_returns_same_object": True
            }
        }
    },
    "cleanup": {
        "delete_rc": 0,
        "deleted_echo": "DELETE 7",
        "r648_rows_before": 0,
        "r648_rows_after": 0,
        "total_rows_before": 0,
        "row_count": 0,
        "rows_returned_to_original": True
    }
}

#: 内部对平用：本单真写过哪几枚假名（别让「DELETE 7」变成一句无主的话）。
FAKE_NAMES_WRITTEN = (
    "r648_concurrency_primary.md", "r648_control_read_then_write.md", "r648_mixed_columns.md",
    "r648_timestamps.md", "r648_doc01.md", "r648_doc03.md", "r648_doc04.md",
)
FAKE_NAMES_NEVER_WRITTEN = ("r648_never_marked.md", "r648_probe_zero_zero.md")


def booked(name) -> dict:
    return BOOKED[name]


def test_the_three_named_identity_readings_say_which_server_was_hit():
    leg = booked("identity")
    tcp = leg["over_tcp"]
    assert tcp["database"] == "eb_r59_sandbox"
    assert tcp["inet_addr"] == "127.0.0.1/32"
    assert tcp["inet_port"] == "5432"
    assert tcp["server_version"] == IDENT_SERVER_VERSION
    assert tcp["data_directory"] == "/var/lib/postgresql/data"
    assert leg["show_server_version"] == IDENT_SERVER_VERSION
    assert leg["database_is_sandbox_family"] is True


def test_the_host_port_that_is_not_published_is_the_wild_postgres_traps_proof():
    """野 PG 那一坑的机器凭据：容器没发布宿主端口 ⇒ 宿主 5432 上的一定是另一台服务器。"""
    leg = booked("identity")
    assert leg["container_publishes_host_port"] is False
    assert leg["container_port_bindings"] == "{}"
    assert "enterprise_brain" in leg["databases_on_this_server"]
    assert leg["production_names_present"] == ["enterprise_brain", "postgres", "template0",
                                               "template1"]
    socket = leg["over_unix_socket"]
    assert (socket["inet_addr"], socket["inet_port"]) == ("NULL", "NULL")


def test_the_concurrency_leg_adds_up_column_by_column_with_no_lost_update():
    leg = booked("concurrency")
    assert leg["shape"] == "product_upsert_single_statement"
    assert leg["sessions"] >= 2 and leg["concurrent_backends"] >= 2
    assert leg["distinct_backend_pids"] == leg["sessions"], "backend pid 逐枚点名：连接数不是嘴上说的"
    assert leg["expected"] == leg["observed"]
    assert leg["lost_updates"] == [], "判据①①：读后写那一族必须被抓到，UPSERT 这一族一枚都不许丢"
    assert leg["expected"]["accepted_count"] == leg["sessions"] * leg["statements_per_session"]
    assert leg["expected"]["rejected_count"] == leg["sessions"] * leg["statements_per_session"]
    assert leg["rows_before_wave"] == {"accepted_count": 0, "rejected_count": 0}
    assert leg["row_count"] == 1, "filename 是 PK：一行不多一行不少"
    assert leg["session_rc"] == [0] * leg["sessions"]


def test_the_read_then_write_shape_actually_loses_an_update_and_names_the_victim():
    """K1 的正反两面：同一套判据打在「先 SELECT 再 UPDATE」上必须红，且点名丢了哪一枚。"""
    leg = booked("read_then_write")
    assert leg["shape"] == "client_read_then_write"
    assert leg["base"] == {"accepted_count": 1, "rejected_count": 0}
    assert leg["expected"] == {"accepted_count": 2, "rejected_count": 1}
    assert leg["observed"] == {"accepted_count": 1, "rejected_count": 1}
    assert leg["both_sessions_read_the_same_base"] is True
    assert leg["concurrent_backends"] >= 2
    assert len(leg["lost_updates"]) == 1
    victim = leg["victims_named"][0]
    assert victim["lost_column"] == "accepted_count"
    assert victim["missing"] == 1 and victim["actually_landed"] == 0
    assert victim["victim_session"] == "S_A" and victim["overwritten_by_session"] == "S_B"
    assert leg["session_rc"] == [0, 0], "两枚会话都没报错：丢的是更新，不是连接"
def test_the_two_columns_are_not_a_single_net_value_on_the_real_store():
    """迁移注释那句「0/0 与 5/5 是两件事」今天有了真库读数：净值 0、两列各 12。"""
    leg = booked("mixed_columns")
    assert leg["concurrent_backends"] >= 2
    assert leg["expected"] == leg["observed"] == {"accepted_count": 12, "rejected_count": 12}
    assert leg["net_value"] == 0
    assert leg["both_columns_nonzero"] is True
    assert leg["read_back_through_product_reader"] == {"accepted": 12, "rejected": 12}
    assert leg["unmarked_row_absent_from_priors"] is True
    #: 两列分开买到的是「可分辨」，不是「另一档权重」：R153 之后两者的分值仍相同。
    assert leg["prior_value_at_net_zero_and_at_no_signal"] == {
        "five_five": 0.0, "zero_zero": 0.0, "absent": 0.0}
    assert leg["lost_updates"] == []


def test_first_signal_at_survives_later_signals_and_last_only_moves_forward():
    leg = booked("timestamps")
    assert leg["waves"] == 4
    assert leg["first_signal_at_rewritten"] is False
    assert leg["first_signal_at_constant"] is True
    assert leg["last_signal_at_monotonic_non_decreasing"] is True
    assert leg["last_at_least_first"] is True
    assert leg["max_backwards_step_ms"] == 0
    assert leg["product_upsert_touches_first_signal_at"] is False
    assert leg["row"] == leg["expected_row"] == {"accepted_count": 7, "rejected_count": 3}
    assert leg["lost_updates"] == []


def test_the_zero_zero_row_is_refused_by_the_constraint_that_0011_books():
    leg = booked("constraints")
    assert leg["zero_zero_rc"] != 0 and leg["zero_zero_refused"] is True
    assert leg["zero_zero_constraint_named_in_stderr"] is True
    assert leg["rows_after_refusal"] == 0
    assert leg["primary_key_count"] == 1
    assert leg["unvalidated_constraints"] == []
    assert leg["booked_names_missing_live"] == []
    assert leg["booked_constraint_names"] == [
        "document_activity_signals_accepted_check",
        "document_activity_signals_filename_length_check",
        "document_activity_signals_not_empty_check",
        "document_activity_signals_rejected_check",
    ]
    live = {item["conname"] for item in leg["live_constraints"]}
    assert live == set(leg["booked_constraint_names"]) | {"document_activity_signals_pkey"}
    assert len(leg["live_constraints"]) == 5


def test_the_legs_leave_the_relation_exactly_where_they_found_it():
    clean, base = booked("cleanup"), booked("baseline")
    assert base["row_count"] == 0 and base["r648_rows"] == 0
    assert clean["delete_rc"] == 0
    assert clean["row_count"] == base["row_count"]
    assert clean["r648_rows_after"] == base["r648_rows"]
    assert clean["rows_returned_to_original"] is True
    names = {booked("concurrency")["filename"], booked("read_then_write")["filename"],
             booked("mixed_columns")["filename"], booked("timestamps")["filename"]}
    names |= {item["filename"] for item in booked("order")["signal_targets"]}
    assert sorted(names) == sorted(FAKE_NAMES_WRITTEN)
    assert clean["deleted_echo"] == "DELETE " + str(len(FAKE_NAMES_WRITTEN))
    for never in FAKE_NAMES_NEVER_WRITTEN:
        assert never not in names, never + " 一格都不该落库"


def test_the_snapshot_internally_adds_up():
    """一本账不许两句话：会漂移的格（进程号、毫秒、耗时）已剔掉，留下的必须互相配平。"""
    order = booked("order")
    assert order["rows_seen_by_product_reader"] == len(FAKE_NAMES_WRITTEN)
    assert order["ann_row_count"] == 40
    assert order["fake_name_map_is_injective"] is True
    assert order["fake_name_map_pairs"] == order["distinct_real_filenames"] == 8
    assert order["relabeled_concentration"] == {"5": 2, "12": 5, "40": 8}
    for width, readings in order["displacement"].items():
        assert readings["max_abs_places_moved"] <= readings["bound_booked"] == 1, width
        assert readings["bound_constant_in_module"] == 1, width
    mixed = booked("mixed_columns")
    assert mixed["net_value"] == (mixed["observed"]["accepted_count"]
                                  - mixed["observed"]["rejected_count"])
    concurrency = booked("concurrency")
    assert concurrency["observed"]["accepted_count"] == concurrency["observed"]["rejected_count"]


def test_the_live_real_pg_reproduces_the_booked_concurrency_readings(tmp_path):
    """复跑闸：开着逐格对账（含并发与丢更新两族），关着交回显式「未量到」＋原因码。"""
    gauge = load_gauge(tmp_path, "concurrency_live")
    if not REAL_PG_OPT_IN:
        report = gauge.run_report(env={})
        assert report["transport_calls"] == 0
        for name, leg in report["legs"].items():
            assert leg["status"] == "unmeasured", name
            assert leg["reason_code"] == gauge.REASON_GATE_OFF, name
        assert gauge.walk_measurement_keys(report["legs"], path="legs") == []
        return
    report = gauge.run_report()
    legs = report["legs"]
    assert {name: leg["status"] for name, leg in legs.items()} == {
        name: "measured" for name in gauge.LEG_NAMES}
    for name in ("identity", "concurrency", "read_then_write", "mixed_columns", "timestamps",
                 "constraints", "cleanup", "baseline"):
        live = legs[name]
        assert live["status"] == "measured", name
    assert legs["identity"]["over_tcp"]["database"] == "eb_r59_sandbox"
    assert legs["identity"]["show_server_version"] == IDENT_SERVER_VERSION
    assert legs["identity"]["container_publishes_host_port"] is False
    upsert = legs["concurrency"]
    assert upsert["expected"] == upsert["observed"] and upsert["lost_updates"] == []
    assert upsert["row_count"] == 1 and upsert["concurrent_backends"] >= 2
    control = legs["read_then_write"]
    assert len(control["lost_updates"]) == 1
    assert control["victims_named"][0]["victim_session"] == "S_A"
    assert control["both_sessions_read_the_same_base"] is True
    assert legs["mixed_columns"]["net_value"] == 0
    assert legs["mixed_columns"]["both_columns_nonzero"] is True
    assert legs["timestamps"]["first_signal_at_constant"] is True
    assert legs["constraints"]["zero_zero_refused"] is True
    assert legs["cleanup"]["rows_returned_to_original"] is True, legs["cleanup"]