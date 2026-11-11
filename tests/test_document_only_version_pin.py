"""A selected document cannot silently switch versions during a follow-up."""

from app.agents.task_review import (
    document_selection_context, legacy_document_selection_unpinned, requested_documents_valid,
)
from langchain_core.messages import AIMessage, HumanMessage


def test_document_only_followup_preserves_first_selected_version(monkeypatch):
    versions = {'policy.md': 1}
    monkeypatch.setattr('app.documents.catalog.latest_document_version',
                        lambda name: {'filename': name, 'version': versions[name], 'department': 'finance',
                                      'classification': 1})
    first = document_selection_context(['policy.md'], {})
    assert first['requested_documents'] == [{'filename': 'policy.md', 'version_id': '1'}]

    versions['policy.md'] = 2
    followup = document_selection_context(['policy.md'], first)
    assert followup == first


def test_document_only_new_selection_can_use_new_version(monkeypatch):
    monkeypatch.setattr('app.documents.catalog.latest_document_version',
                        lambda name: {'filename': name, 'version': 2})
    assert document_selection_context(['policy.md'], {})['requested_documents'][0]['version_id'] == '2'
    assert document_selection_context([], {'requested_documents': [{'filename': 'policy.md', 'version_id': '1'}]}) == {}


def test_changed_version_is_rejected_before_old_task_reads_it(monkeypatch):
    monkeypatch.setattr('app.documents.catalog.latest_document_version',
                        lambda name: {'filename': name, 'version': 2, 'department': 'finance',
                                      'classification': 1})
    monkeypatch.setattr('app.rag.filters.resolve_document_retrieval_scope',
                        lambda principal: type('Scope', (), {'allows': lambda self, version: True})())
    pinned = {'requested_documents': [{'filename': 'policy.md', 'version_id': '1'}]}
    assert not requested_documents_valid(pinned, object())


def test_selected_document_requires_a_doc_read_even_if_supervisor_answers():
    from app.agents.orchestrator import route_main

    state = {'messages': [HumanMessage(content='仅依据以下文件《policy.md》回答：\n唯一标识是什么？'),
                          AIMessage(content='旧版本标识是 V1')],
             'document_selection': {'requested_documents': [{'filename': 'policy.md', 'version_id': '2'}]},
             'worker_results': {}, 'agent_results': {}, 'plan': []}
    routed = route_main(state, {'configurable': {'document_filenames': ['policy.md']}})
    assert any(getattr(item, 'node', None) == 'doc' for item in routed)


def test_legacy_document_question_without_a_version_must_start_new_task():
    previous = {'messages': [HumanMessage(content='仅依据以下文件《policy.md》回答：\n旧问题')]}
    assert legacy_document_selection_unpinned(previous)
    assert not legacy_document_selection_unpinned({'messages': [HumanMessage(content='普通问题')]})
