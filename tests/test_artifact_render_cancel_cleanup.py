"""Real rendering and PG registry; inject interruption timing or audit failure."""
import json
import threading
from pathlib import Path
from uuid import uuid4
import pytest
from test_r462_query_data_tuple_keys import query_files
from test_alert_scan_scope import alert_pg


@pytest.mark.parametrize('kind', ['chart', 'report'])
@pytest.mark.parametrize('interruption', ['cancel', 'audit'])
def test_render_interruption_cleans_only_unregistered_files(monkeypatch, query_files, kind, interruption):
    from app.agents import tools
    from app.tools import chart, export
    from app.storage.artifacts import artifact_registry
    module = chart if kind == 'chart' else export
    name = 'bar_chart' if kind == 'chart' else 'generate_pdf_report'
    monkeypatch.setattr(module, 'STATIC_DIR' if kind == 'chart' else 'EXPORT_DIR', str(artifact_registry.root))
    principal = query_files['configurable']['principal']
    marker = threading.Event()
    config = {'configurable': {'principal': principal, 'cancel_event': marker,
        'thread_id': uuid4().hex, 'request_id': uuid4().hex}}
    paths, real = [], getattr(module, name)
    def render(*args, **kw):
        path = real(*args, **kw)
        paths.append(path)
        if len(paths) == 2 and interruption == 'cancel': marker.set()
        return path
    monkeypatch.setattr(module, name, render)
    def invoke():
        if kind == 'chart': return tools._generate_chart('bar', config, labels=['一月', '二月'], values=[10, 20])
        return tools._export_report('合成费用报告', json.dumps([{'type': 'summary', 'cards': []},
            {'type': 'text', 'content': '合成核对'}], ensure_ascii=False), config)
    before = len(artifact_registry.list_active(owner_id=principal.user_id))
    assert '已生成' in invoke()
    if interruption == 'audit':
        def audit_failure(*args, **kw): raise RuntimeError('controlled post-registration audit outage')
        monkeypatch.setattr('app.common.audit.record_audit', audit_failure)
    assert '已生成' not in invoke()
    assert len(paths) == 2 and Path(paths[0]).is_file()
    assert Path(paths[1]).exists() == (interruption == 'audit')
    assert len(artifact_registry.list_active(owner_id=principal.user_id)) == before + (2 if interruption == 'audit' else 1)
