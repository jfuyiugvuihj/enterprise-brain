import { classificationLabel } from './provenance'

export const FILE_CLASSIFICATION_LEVELS = [1, 2, 3]

export function fileClassificationLevel(row) {
  const value = row?.classification_level ?? row?.classification
  if (value === null || value === undefined || value === '') return null
  const level = Number(value)
  return Number.isInteger(level) && level >= 1 && level <= 4 ? level : null
}

export function filterFileClassification(rows, filter) {
  if (!filter) return rows
  return rows.filter(row => filter === 'unknown'
    ? fileClassificationLevel(row) === null : fileClassificationLevel(row) === Number(filter))
}

export function fileAccessLabel(row) {
  const level = fileClassificationLevel(row)
  const visibility = typeof row?.visibility === 'string' ? row.visibility.trim() : ''
  if (visibility === 'enterprise_shared') {
    return `${level === null ? '密级未登记' : classificationLabel(String(level))} · 企业内共享`
  }
  const departments = Array.isArray(row?.department_ids) ? row.department_ids.filter(Boolean) : []
  if (!departments.length && row?.department) departments.push(row.department)
  return `${level === null ? '密级未登记' : classificationLabel(String(level))} · ${departments.length ? '部门范围：' + departments.join('、') : '部门范围未登记'}`
}
