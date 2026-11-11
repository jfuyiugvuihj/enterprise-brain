"""R299 · 0016 与生命周期词表：首装必绿、两份拼写同源，以及判据⑦里那两枚迁移反证。

判据⑥要的是「新迁移要能过 test_r120_clean_install_first_boot.py 那一族迁移版本钉」。本文件因此
不去复制那族钉的判法，而是直接借它已经建好的那台 PostgreSQL 替身（FreshSession：它真的记账、真的
按语句比对目录，不是"回一句成功"的桩），把一枚**空账**喂给 apply_migrations，看它能不能一路走到
0016 并把 0016 的摘要记进 schema_migrations。跑不完就是首装不绿，与本文件同源的五枚尾号引信
（0016 那一格由本单施工方改口）也已经先红给你看了。

判据⑦点名两枚必须"摘掉就红"的反证，本文件负责迁移那两枚：

- 漏装（0016 在盘上但清单里没有它）=> loader 当场拒，而不是安静地少跑一版；
- 序号错位（0016 与 0015 撞了同一个号）=> loader 当场拒，而不是按文件名顺序蒙混过去。

两枚都在一份临时副本上做，生产目录一个字节都不动 —— 反证要的是"这一格有牙"，不是"把仓库弄坏"。
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest
from app.db import migrations as mig
from app.notifications import contracts
from test_document_catalog_sync import split_statements
from test_r120_clean_install_first_boot import (
    COMPOSE_DEFAULT_DATABASE,
    FreshSession,
    _declared_from_the_sample,
)
from test_r183_184_migration_pair import _COMMENT_LINE
from test_r349_catalog_tail_ledger import CATALOG_TAIL_VERSION

REPO = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO / 'migrations'
NEW_VERSION = '0016'
NEW_FILENAME = '0016_notification_states.sql'
NEW_NAME = 'notification_states'
TABLE = 'notification_states'

#: 生命周期词表在 DDL 里的那一枚 CHECK。抠不出来必须抛：解析器回空等于让"两边都空"恒真。
_STATE_CHECK = re.compile(
    r"CONSTRAINT\s+notification_states_state_check\s+CHECK\s*\(\s*state\s+IN\s*\((?P<words>[^)]*)\)",
    re.IGNORECASE | re.DOTALL,
)
_ROW_WRITING = re.compile(
    r"^\s*(insert|update|delete|merge|truncate|copy|do|call|grant|revoke|drop)\b",
    re.IGNORECASE,
)


def _catalog_copy(
    target: Path,
    *,
    drop_manifest_entry: bool = False,
    rename: tuple[str, str] = (),
    move_manifest_entry: bool = False,
) -> Path:
    """把整册迁移目录复制到临时位置，并按需制造一枚缺陷。生产目录只读。"""
    target.mkdir(parents=True, exist_ok=True)
    for path in MIGRATIONS_DIR.glob('*.sql'):
        name = path.name
        if rename and name == rename[0]:
            name = rename[1]
        (target / name).write_bytes(path.read_bytes())
    manifest = json.loads((MIGRATIONS_DIR / 'manifest.json').read_text(encoding='utf-8'))
    if drop_manifest_entry:
        manifest.pop(NEW_FILENAME, None)
    if move_manifest_entry and rename:
        # 连清单一起改变号：先让盘与清单自洽，才轮得上「版本重复」那道闸门。
        manifest[rename[1]] = manifest.pop(rename[0])
    (target / 'manifest.json').write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8'
    )
    return target


def _new_migration_sql() -> str:
    return (MIGRATIONS_DIR / NEW_FILENAME).read_text(encoding='utf-8')


def _check_words(sql: str) -> set[str]:
    match = _STATE_CHECK.search(sql)
    if match is None:
        raise AssertionError('0016 里没有那枚 state CHECK：词表对判不能降级成恒真')
    return {piece.strip().strip(chr(39)) for piece in match.group('words').split(',') if piece.strip()}


def _vocab(sql: str) -> set[str]:
    """读 DDL 抠出的封闭集，与产品侧词表逐字比对：多一枚少一枚都抛。

    这一枚是判据⑦里词表反证的落点：摘掉 contracts.NOTIFICATION_STATES 的一枚词，
    或把 0016 的 CHECK 抹掉一枚词，两边就对不上，两个方向都必须红。
    """
    admitted = _check_words(sql)
    if admitted != set(contracts.NOTIFICATION_STATES):
        raise AssertionError(
            f'DDL admits {sorted(admitted)} but the code writes'
            f' {sorted(contracts.NOTIFICATION_STATES)}'
        )
    return admitted


# ---------------------------------------------------------------- 判据 ① / ⑥：目录与清单


def test_0016_is_registered_as_the_catalog_tail_and_loads():
    versions = [item.version for item in mig.MIGRATIONS]

    assert versions == [
        f'{number:04d}' for number in range(1, int(CATALOG_TAIL_VERSION) + 1)
    ], versions
    assert NEW_VERSION in versions, '本件的主题版 0016 不许被人从目录里摘走'
    assert versions[-1] == CATALOG_TAIL_VERSION, (
        '尾号数字只在 tests/test_r349_catalog_tail_ledger.py 写死一枚；改口去那一处，别改本件'
    )
    registered = next(item for item in mig.MIGRATIONS if item.version == NEW_VERSION)
    assert registered.name == NEW_NAME
    assert mig.discover_migrations() == mig.MIGRATIONS, '清单校验不过的目录不该被 loader 认下来'


def test_the_recorded_digest_is_the_exact_bytes_on_disk():
    manifest = json.loads((MIGRATIONS_DIR / 'manifest.json').read_text(encoding='utf-8'))
    text = (MIGRATIONS_DIR / NEW_FILENAME).read_text(encoding='utf-8')
    registered = next(item for item in mig.MIGRATIONS if item.version == NEW_VERSION)

    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    assert manifest[NEW_FILENAME] == digest == registered.checksum, (
        '0016 的落盘字节、清单摘要与 loader 登记的三份必须同字'
    )


def test_the_landed_check_admits_exactly_the_states_the_code_can_write():
    """DDL 的封闭集 == contracts.NOTIFICATION_STATES。多一枚少一枚都红，两个方向都算。

    与 0014/tests/test_r251_alert_disposal.py 同一族判法：表里能写什么，产品侧就必须只允许什么。
    unread 不许出现在任何一侧 —— 它是"没有行"，不是一次写。
    """
    admitted = _vocab(_new_migration_sql())

    assert contracts.STATE_UNREAD not in admitted
    assert contracts.STATE_UNREAD not in contracts.NOTIFICATION_STATES


def test_the_migration_ships_no_row_writing_and_nothing_dropped():
    """本版只建表与建索引：没有 INSERT/UPDATE/DROP，也没有 TRUNCATE。

    一行生命周期记录由迁移写下，等于替某个人说了一句他没做过的事（0014 文件头同一条理由）。
    """
    body = _COMMENT_LINE.sub('-', _new_migration_sql())
    statements = [item for item in split_statements(body) if item.strip()]

    assert statements, '0016 切不出语句：这枚判据不能空转'
    offending = [item.strip()[:60] for item in statements if _ROW_WRITING.match(item.strip())]
    assert offending == [], '迁移在写数据或删东西：' + json.dumps(offending, ensure_ascii=False)
    assert sum('CREATE TABLE' in item.upper() for item in statements) == 1
    assert 'IF NOT EXISTS' in statements[0].upper()


# ---------------------------------------------------------------- 判据 ⑥：干净首装走到 0016


def test_a_clean_first_boot_applies_every_version_through_0016(monkeypatch):
    """空账 + 真 runner：0016 必须被 apply 并且按同一枚摘要记进账本（目录尾号另有其主）。

    借 r120 那台替身而不是自己搓一枚：它会为认不出的语句报错，也不会替谁把"没跑到"说成"跑过了"。
    0010 那两枚 embedding 声明由夹具补齐 —— 首装到不了 0016 的唯一正当原因必须是本版的错。
    """
    # 成对声明取自示例文件本身：干净首装跑不到 0016 的唯一正当原因，只能是本版出错。
    sample = _declared_from_the_sample()
    for name, value in sample.items():
        monkeypatch.setenv(name, value)
    session = FreshSession(database=COMPOSE_DEFAULT_DATABASE, ledger={})

    applied = mig.apply_migrations(session, COMPOSE_DEFAULT_DATABASE)

    assert [item.version for item in applied] == [item.version for item in mig.MIGRATIONS]
    # R509 排了 0017 之后，"本版的 0016 被 apply" 与 "它是目录尾号" 是两件事，必须分开钉：
    # 尾号只由 tests/test_r349_catalog_tail_ledger.py 那枚账本判，本件判自己那一版真落进了库。
    assert NEW_VERSION in session.applied, session.applied
    assert session.applied[-1] == CATALOG_TAIL_VERSION, session.applied
    recorded = session.ledger[NEW_VERSION]
    assert recorded == next(item.checksum for item in mig.MIGRATIONS if item.version == NEW_VERSION)
    created = [sql for sql in session.executed_sql if 'CREATE TABLE IF NOT EXISTS notification_states' in sql]
    assert len(created) == 1, '0016 的建表语句必须真的发出去过且只发一次'
    assert any('notification_states_reader_key UNIQUE' in sql for sql in created)


def test_a_reapplied_catalog_records_nothing_new_for_0016(monkeypatch):
    """二跑幂等：账本里已经有 0016 时，runner 一枚都不该再发。"""
    for name, value in _declared_from_the_sample().items():
        monkeypatch.setenv(name, value)
    ledger = {item.version: item.checksum for item in mig.MIGRATIONS}
    session = FreshSession(database=COMPOSE_DEFAULT_DATABASE, ledger=ledger)

    applied = mig.apply_migrations(session, COMPOSE_DEFAULT_DATABASE)

    assert applied == []
    assert session.applied == []
    assert session.ledger == ledger


# ---------------------------------------------------------------- 判据 ⑦：两枚迁移反证


def test_counter_evidence_a_an_unregistered_migration_is_refused_not_skipped(tmp_path):
    """漏装反证：0016 在盘上而清单里没有它 => loader 拒，启动期那道闸门也拒。

    这就是 app/main.py 的 _verify_migration_catalog 在生产起进程时替运维挡下的那一格；摘掉登记
    不会"少一版而已"，整套应用起不来 —— 所以「迁移没装上」不可能被读成「已经装好了」。
    """
    copy = _catalog_copy(tmp_path, drop_manifest_entry=True)

    with pytest.raises(ValueError) as caught:
        mig.discover_migrations(copy)

    message = str(caught.value)
    assert 'migration manifest mismatch' in message, message
    assert NEW_FILENAME in message, '拒绝必须点名是哪一版没登记：' + message


def test_counter_evidence_b_a_misnumbered_migration_is_refused(tmp_path):
    """序号错位反证：把 0016 改名成又一个 0015 => 版本重复当场拒，而不是按名字排序蒙混。

    同一枚副本里再做一次反向缺陷（登记了但盘上没有），两条都指回 0016 —— 少装与错装是同一枚
    闸门的两侧，只做一侧的钉等于半个闸门。
    """
    clash = _catalog_copy(
        tmp_path / 'clash',
        rename=(NEW_FILENAME, '0015_notification_states.sql'),
        move_manifest_entry=True,
    )
    with pytest.raises(ValueError) as duplicated:
        mig.discover_migrations(clash)
    assert 'duplicate migration version' in str(duplicated.value)

    gone = _catalog_copy(tmp_path / 'gone')
    (gone / NEW_FILENAME).unlink()
    with pytest.raises(ValueError) as missing:
        mig.discover_migrations(gone)
    assert 'missing files' in str(missing.value)
    assert NEW_FILENAME in str(missing.value)


def test_counter_evidence_c_a_check_that_loses_a_word_breaks_the_vocabulary_pin():
    """词表同源的牙齿：从副本里的 CHECK 抹掉一枚词，对判必须当场不认。

    生产迁移一个字节都不动。这一格要证明的是上面那枚断言不是"两边恰好都写死了同一个字面量"，
    而是真的在读 DDL —— 把 dismissed 从 CHECK 里删掉，它就该红。
    """
    mutated = _new_migration_sql().replace(
        "CHECK (state IN ('read', 'dismissed'))", "CHECK (state IN ('read'))"
    )
    assert mutated != _new_migration_sql(), '替换没命中：这枚反证就没牙'

    with pytest.raises(AssertionError):
        _vocab(mutated)
