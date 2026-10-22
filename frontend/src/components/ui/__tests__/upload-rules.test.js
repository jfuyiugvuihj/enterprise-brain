import { describe, expect, it } from 'vitest'
import { formatBytes, isAcceptable, parseAccept, validateFiles } from '../upload-rules.js'

const file = (name, size, type = '') => ({ name, size, type })

describe('accept 解析', () => {
  it('扩展名与 MIME 分开收', () => {
    expect(parseAccept('.pdf, application/pdf , .docx')).toEqual({ extensions: ['pdf', 'docx'], mimetypes: ['application/pdf'] })
    expect(parseAccept('')).toEqual({ extensions: [], mimetypes: [] })
  })

  it('MIME 通配符按前缀匹配', () => {
    expect(isAcceptable(file('a.png', 10, 'image/png'), 'image/*')).toBe(true)
    expect(isAcceptable(file('a.pdf', 10, 'application/pdf'), 'image/*')).toBe(false)
  })

  it('accept 为空即不限制', () => {
    expect(isAcceptable(file('a.zip', 10), '')).toBe(true)
  })
})

describe('一次选取的批量校验', () => {
  it('类型不符挡下并回 unsupported_file', () => {
    const { accepted, rejected } = validateFiles([file('预算.xlsx', 100), file('木马.exe', 100)], { accept: '.xlsx,.pdf' })
    expect(accepted).toHaveLength(1)
    expect(rejected[0].code).toBe('unsupported_file')
    expect(rejected[0].file.name).toBe('木马.exe')
  })

  it('超过大小限制回 upload_too_large（能被 normalizeError 归一）', () => {
    const { rejected } = validateFiles([file('大表.csv', 30 * 1024 * 1024)], { maxSizeMb: 20 })
    expect(rejected[0].code).toBe('upload_too_large')
  })

  it('单选模式多塞的那几个挡下', () => {
    const { accepted, rejected } = validateFiles([file('a.pdf', 10), file('b.pdf', 10)], { accept: '.pdf', multiple: false })
    expect(accepted).toHaveLength(1)
    expect(rejected[0].code).toBe('validation_error')
  })

  it('FileList 与空输入都能吃', () => {
    const list = { 0: file('a.pdf', 10), length: 1 }
    expect(validateFiles(list, { accept: '.pdf' }).accepted).toHaveLength(1)
    expect(validateFiles(null, {})).toEqual({ accepted: [], rejected: [] })
  })

  it('没有约束时全部放行', () => {
    expect(validateFiles([file('a.bin', 5)], {}).accepted).toHaveLength(1)
  })
})

describe('体积显示', () => {
  it('保留一位小数，整十往上取整', () => {
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(20480)).toBe('20 KB')
    expect(formatBytes(2 * 1024 * 1024, 'MB')).toBe('2.0 MB')
  })

  it('脏数据返回空串而不是 NaN', () => {
    expect(formatBytes(undefined)).toBe('')
    expect(formatBytes(-1)).toBe('')
  })
})
