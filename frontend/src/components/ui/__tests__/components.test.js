import { describe, expect, it } from 'vitest'
import { h, defineComponent } from 'vue'
import { renderToString } from '@vue/server-renderer'
import UiSelect from '../UiSelect.vue'
import UiButton from '../UiButton.vue'
import UiField from '../UiField.vue'
import UiTabs from '../UiTabs.vue'
import UiTable from '../UiTable.vue'
import UiToast from '../UiToast.vue'
import UiToastHost from '../UiToastHost.vue'
import UiDialog from '../UiDialog.vue'
import UiUpload from '../UiUpload.vue'

const render = (component, props = {}, slots) => {
  const Host = defineComponent({
    render() {
      return h(component, props, slots)
    },
  })
  return renderToString(h(Host))
}

describe('UiButton', () => {
  it('渲染文字与变体，primary 只用强调色 token 类名', async () => {
    const html = await render(UiButton, { variant: 'primary', label: '确认执行' })
    expect(html).toContain('ui-button--primary')
    expect(html).toContain('type="button"')
    expect(html).toContain('确认执行')
    expect(html).not.toMatch(/#[0-9a-f]{3,8}/i)
  })

  it('loading 与 disabled 都不可点，并给出 aria-busy', async () => {
    const html = await render(UiButton, { label: '上传', loading: true })
    expect(html).toContain('disabled')
    expect(html).toContain('aria-busy="true"')
    expect(html).toContain('ui-button--busy')
  })
})

describe('UiField', () => {
  it('label 与 input 通过 id 绑定，正文 14px 档', async () => {
    const html = await render(UiField, { label: '部门', modelValue: '财务部', hint: '按组织架构填写' })
    expect(html).toMatch(/<label class="ui-field__label" for="(ui-field-[^"]+)"/)
    expect(html).toContain('id="ui-field-')
    expect(html).toContain('value="财务部"')
    expect(html).toContain('按组织架构填写')
  })

  it('错误态补 aria-invalid / aria-describedby / role=alert，并保留错误码小字', async () => {
    const html = await render(UiField, {
      label: '部门',
      error: '请先选择部门范围，再生成这项结果。',
      codeLabel: '错误码：department_scope_required',
    })
    expect(html).toContain('aria-invalid="true"')
    expect(html).toContain('aria-describedby="')
    expect(html).toContain('role="alert"')
    expect(html).toContain('ui-field--invalid')
    expect(html).toContain('请先选择部门范围，再生成这项结果。')
    expect(html).toContain('错误码：department_scope_required')
  })

  it('multiline 出 textarea，rows 生效', async () => {
    const html = await render(UiField, { label: '备注', multiline: true, rows: 5 })
    expect(html).toContain('<textarea')
    expect(html).toContain('rows="5"')
  })
})

describe('UiSelect', () => {
  const options = [
    { label: '市场部', value: 'mkt' },
    { label: '财务部', value: 'fin', disabled: true },
    { label: '运营部', value: 'ops' },
  ]

  it('收起态是 combobox，未选中显示占位文案', async () => {
    const html = await render(UiSelect, { label: '部门', options, modelValue: '' })
    expect(html).toContain('role="combobox"')
    expect(html).toContain('aria-expanded="false"')
    expect(html).toContain('aria-haspopup="listbox"')
    expect(html).toContain('ui-select__value--muted')
    expect(html).toContain('请选择')
    expect(html).not.toContain('role="listbox"')
  })

  it('展开态是 listbox，选中项 aria-selected=true、禁用项 aria-disabled', async () => {
    const html = await render(UiSelect, { label: '部门', options, modelValue: 'mkt', expanded: true })
    expect(html).toContain('role="listbox"')
    expect(html).toContain('aria-expanded="true"')
    expect(html).toContain('aria-selected="true"')
    expect(html).toContain('aria-disabled="true"')
    expect(html).toContain('市场部')
    expect(html).toContain('运营部')
  })

  it('空选项时给出空态文案而不是空白下拉', async () => {
    const html = await render(UiSelect, { label: '部门', options: [], expanded: true, emptyText: '没有可选项' })
    expect(html).toContain('ui-select__empty')
    expect(html).toContain('没有可选项')
  })
})

describe('UiTable', () => {
  const columns = [
    { key: 'department', label: '部门', sortable: true },
    { key: 'amount', label: '金额', align: 'right', sortable: true },
  ]
  const rows = [
    { department: '市场部', amount: 12600 },
    { department: '财务部', amount: 9800 },
    { department: '运营部', amount: 4200 },
  ]

  it('用真 table + 表头 aria-sort，数值列走等宽数字', async () => {
    const html = await render(UiTable, { columns, rows, sort: { key: 'amount', order: 'desc' }, ariaLabel: '费用明细' })
    expect(html).toContain('<table')
    expect(html).toContain('<th')
    expect(html).toContain('aria-sort="descending"')
    expect(html).toContain('ui-table__td--mono')
    expect(html).toContain('市场部')
  })

  it('空数据集渲染空态行文案，不渲染空白表格体', async () => {
    const html = await render(UiTable, { columns, rows: [], emptyText: '今天没有需要确认的高风险动作' })
    expect(html).toContain('ui-table__empty')
    expect(html).toContain('今天没有需要确认的高风险动作')
  })

  it('loading 时是骨架行而不是转圈', async () => {
    const html = await render(UiTable, { columns, rows: [], loading: true })
    expect(html).toContain('ui-table__row--skeleton')
    expect(html).toContain('ui-table__skeleton')
    expect(html).not.toContain('ui-table__empty')
  })
})

describe('UiTabs', () => {
  const items = [
    { id: 'chat', label: '对话' },
    { id: 'data', label: '数据' },
    { id: 'admin', label: '管理', disabled: true },
  ]

  it('输出 tablist + aria-selected + roving tabindex', async () => {
    const html = await render(UiTabs, { items, modelValue: 'chat', ariaLabel: '工作区' })
    expect(html).toContain('role="tablist"')
    expect(html).toContain('aria-orientation="horizontal"')
    expect(html).toContain('role="tab"')
    expect(html).toContain('aria-selected="true"')
    expect(html).toContain('tabindex="0"')
    expect(html).toContain('aria-disabled')
    const inactive = html.match(/class="ui-tabs__tab"[^>]*tabindex="-1"/g) || []
    expect(inactive.length).toBe(1)
  })

  it('没有条目时给空态文案', async () => {
    const html = await render(UiTabs, { items: [], emptyText: '没有可切换的内容' })
    expect(html).toContain('ui-tabs__empty')
    expect(html).toContain('没有可切换的内容')
  })
})

describe('UiDialog', () => {
  it('关闭时不往文档里留任何节点', async () => {
    const html = await render(UiDialog, { modelValue: false, title: '确认执行' })
    expect(html).not.toContain('role="dialog"')
    expect(html).not.toContain('确认执行')
  })

  it('打开时是 aria-modal 对话框，标题用 aria-labelledby 关联', async () => {
    const html = await render(UiDialog, { modelValue: true, title: '确认执行', description: '这一步会写入经营数据。' })
    expect(html).toContain('role="dialog"')
    expect(html).toContain('aria-modal="true"')
    expect(html).toContain('aria-labelledby="ui-dialog-title"')
    expect(html).toContain('id="ui-dialog-title"')
    expect(html).toContain('aria-label="关闭"')
    expect(html).toContain('这一步会写入经营数据。')
  })
})

describe('UiToast / UiToastHost', () => {
  it('danger 走 role=alert，未知码小字保留在原句之外', async () => {
    const html = await render(UiToast, {
      tone: 'danger',
      message: '文件已收到，但没能进入知识库，请稍后重试。',
      codeLabel: '错误码：index_publish_failed',
      retryable: true,
    })
    expect(html).toContain('role="alert"')
    expect(html).toContain('ui-toast--danger')
    expect(html).toContain('重试')
    expect(html).toContain('错误码：index_publish_failed')
  })

  it('info 走 role=status，不抢读屏', async () => {
    const html = await render(UiToast, { tone: 'info', message: '已保存' })
    expect(html).toContain('role="status"')
    expect(html).not.toContain('重试')
  })

  it('队列清空后 host 里没有 toast 卡片', async () => {
    const html = await render(UiToastHost)
    expect(html).toContain('ui-toast-host')
    expect(html).not.toContain('ui-toast--')
  })
})

describe('UiUpload', () => {
  it('未选文件时是空态文案 + 选择按钮，且带 accept 约束', async () => {
    const html = await render(UiUpload, { accept: '.pdf,.docx', maxSizeMb: 20, items: [] })
    expect(html).toContain('ui-upload__empty')
    expect(html).toContain('还没有选择文件')
    expect(html).toContain('accept=".pdf,.docx"')
    expect(html).toContain('可传 .pdf / .docx')
    expect(html).toContain('单个不超过 20MB')
  })

  it('清单项显示进度条与 aria-valuenow，失败项转成未成功文案', async () => {
    const html = await render(UiUpload, {
      items: [
        { name: '预算表.xlsx', size: 20480, status: 'uploading', progress: 40 },
        { name: '制度.docx', error: '文件内容没能解析成功，请检查文件是否损坏或受保护。' },
      ],
    })
    expect(html).toContain('ui-upload__bar')
    expect(html).toContain('aria-valuenow="40"')
    expect(html).toContain('预算表.xlsx')
    expect(html).toContain('20 KB')
    expect(html).toContain('ui-upload__status--failed')
    expect(html).toContain('重试')
  })
})
