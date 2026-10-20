import { describe, it, expect } from 'vitest'
import { documentQuestion, documentNamesFromQuestion, normalizeDocumentNames } from './document-selection'
import { activeId, activeDataFilename, backendSessionMessages, adoptBackendSession, newSession, referenceDocuments, resetSessions, restoreActive, syncActive } from './sessions'

describe('selected document scope', () => {
  it('restores the joint selection from authorized server history in a new browser', () => {
    resetSessions()
    const read = backendSessionMessages({ messages: [{ role: 'assistant', content: '200，单位未标注',
      task_selection: { dataFilename: '费用.csv', documentFilenames: ['制度.pdf'] } }] })
    adoptBackendSession('joint-task', read.messages)
    expect(activeDataFilename.value).toBe('费用.csv')
    expect(referenceDocuments.value).toEqual(['制度.pdf'])
  })
  it('keeps every selected file in an exclusive question and restores it from server history', () => {
    const names = ['制度.pdf', '明细.csv']
    const question = documentQuestion('比较两份资料', names)
    expect(question).toBe('仅依据以下文件《制度.pdf》《明细.csv》回答：\n比较两份资料')
    expect(documentNamesFromQuestion(question)).toEqual(names)
  })
  it('does not duplicate scope on follow-up or retain a removed file', () => {
    const old = documentQuestion('说明差异', ['制度.pdf', '明细.csv'])
    expect(documentQuestion(old, ['明细.csv'])).toBe(documentQuestion('说明差异', ['明细.csv']))
    expect(documentQuestion(old, [])).toBe('说明差异')
  })
  it('deduplicates names and leaves a freely typed question intact', () => {
    expect(normalizeDocumentNames([' A.pdf ', 'A.pdf', '', null, 'B.txt'])).toEqual(['A.pdf', 'B.txt'])
    expect(documentQuestion('请根据《其他.pdf》回答', [])).toBe('请根据《其他.pdf》回答')
    expect(documentNamesFromQuestion('请根据《其他.pdf》回答')).toEqual([])
  })
  it('keeps selection per task and does not revive explicitly cleared history', () => {
    resetSessions()
    adoptBackendSession('selected-task', [{ role: 'user', content: documentQuestion('比较', ['A.pdf', 'B.pdf']) }])
    expect(referenceDocuments.value).toEqual(['A.pdf', 'B.pdf'])
    referenceDocuments.value = ['B.pdf']
    syncActive()
    newSession()
    expect(referenceDocuments.value).toEqual([])
    activeId.value = 'selected-task'
    restoreActive('selected-task')
    expect(referenceDocuments.value).toEqual(['B.pdf'])
    referenceDocuments.value = []
    syncActive()
    adoptBackendSession('selected-task', [{ role: 'user', content: documentQuestion('比较', ['A.pdf', 'B.pdf']) }])
    expect(referenceDocuments.value).toEqual([])
    resetSessions()
  })
})
