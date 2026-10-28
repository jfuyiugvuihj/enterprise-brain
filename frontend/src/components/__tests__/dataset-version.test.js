import { beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
vi.mock('../../lib/http', async original => ({ ...await original(), http: { post: vi.fn() } }))
import { http } from '../../lib/http'
import DatasetVersionPanel from '../DatasetVersionPanel.vue'
const target = { filename: '经营数据.csv', version_id: 'finance:v1', classification: '2', owner_id: 'owner', department_ids: ['finance'] }
async function panel() {
  let bindings
  const emit = vi.fn()
  await renderToString(h(defineComponent({ setup() {
    bindings = DatasetVersionPanel.setup({ target, disabled: false }, { emit, expose() {} })
    return () => null
  } })))
  return { b: bindings, emit }
}
const choose = b => {
  b.chooseReplacement()
  b.handleFileChange({ target: { files: [new File(['replacement'], 'new-copy.csv', { type: 'text/csv' })] } })
}
beforeEach(() => http.post.mockReset())
it('取消不上传，确认使用目标文件名和原版本，保持文件内容与密级设置独立', async () => {
  const { b, emit } = await panel()
  choose(b)
  b.cancelUpdate()
  await b.confirmUpdate()
  expect(http.post).not.toHaveBeenCalled()
  choose(b)
  http.post.mockResolvedValue({ status: 200, data: { filename: target.filename, version_id: 'finance:v2' } })
  await b.confirmUpdate()
  const [url, form] = http.post.mock.calls[0]
  expect(url).toBe('/upload-excel')
  expect(form.get('new_version')).toBe('true')
  expect(form.get('expected_version_id')).toBe(target.version_id)
  expect(form.get('classification')).toBeNull()
  expect(form.get('file').name).toBe(target.filename)
  expect(await form.get('file').text()).toBe('replacement')
  expect(b.resultMessage.value).toContain('finance:v2')
  expect(emit).toHaveBeenCalledWith('completed', target.filename)
})
it('冲突、索引失败和结果未知分别说明，不能自动重发或报告成功', async () => {
  for (const [error, text] of [[{ response: { status: 409 } }, '版本已变化'],
    [{ response: { status: 503 } }, '上一版本仍保留'], [new Error('offline'), '结果暂时无法确认']]) {
    const { b, emit } = await panel()
    choose(b)
    http.post.mockRejectedValueOnce(error)
    const before = http.post.mock.calls.length
    await b.confirmUpdate()
    expect(http.post.mock.calls.length).toBe(before + 1)
    expect(b.errorMessage.value).toContain(text)
    expect(b.resultMessage.value).toBe('')
    expect(emit).not.toHaveBeenCalled()
  }
})
