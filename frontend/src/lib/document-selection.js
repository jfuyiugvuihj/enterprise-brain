const scopeHeader = /^仅依据以下文件((?:《[^》\r\n]+》)+)回答：\n/

export function normalizeDocumentNames(names) {
  return [...new Set((Array.isArray(names) ? names : [])
    .filter(name => typeof name === 'string').map(name => name.trim()).filter(Boolean))]
}

export function documentNamesFromQuestion(question) {
  const header = String(question || '').match(scopeHeader)
  return header ? [...header[1].matchAll(/《([^》]+)》/g)].map(match => match[1]) : []
}

export function documentQuestion(question, names) {
  const text = String(question || '').replace(scopeHeader, '')
  const files = normalizeDocumentNames(names)
  return files.length ? `仅依据以下文件${files.map(name => `《${name}》`).join('')}回答：\n${text}` : text
}
