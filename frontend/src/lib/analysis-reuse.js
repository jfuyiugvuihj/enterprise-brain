const fieldNames = value => (Array.isArray(value) ? value : [])
  .map(field => typeof field === 'string' ? field : field?.name || field?.column)
  .filter(name => typeof name === 'string' && name.length)

export function analysisReuseDraft(record, preview) {
  if (record?.status !== 'completed') throw new Error('只能复用已完成的计算')
  const question = record?.parameters?.query
  if (typeof question !== 'string' || !question.trim()) throw new Error('原计算没有可复用的问题')
  const filename = record?.parameters?.filename
  if (!filename || filename !== preview?.filename) throw new Error('只能复用同名数据文件的其他版本')
  if (!preview?.version_id) throw new Error('当前数据版本未提供版本标识')

  const expected = fieldNames(record?.result?.columns)
  const required = expected.length ? expected : fieldNames(record?.result?.analysis_scope?.units)
  if (!required.length) throw new Error('旧计算未记录可核对字段，无法验证复用')
  const available = new Set(fieldNames(preview?.profile?.columns || preview?.columns))
  if (!available.size) throw new Error('当前数据版本没有可核对字段')
  const missing = required.find(name => !available.has(name))
  if (missing) throw new Error(`当前数据版本缺少字段「${missing}」，无法复用`)

  return { question, filename, version_id: preview.version_id }
}
