<script>
import { errorDetail, isPermissionDenied } from '../lib/http'
import { errorCodeOf } from '../lib/errcodes'

/**
 * 行级可见范围「只裁掉一部分」那一格（R191 · Bohr 交工第⑥格挂账）。
 *
 * 这句话在这里定义、也只在这里定义：DataPanel 的统计行与本弹窗的预览行是同一件事的两张脸。
 * R186 让面板开始说「全表 120 行中，当前账号可见的 40 行」，而弹窗打开仍只报
 * 「40 行预览」—— 把一部分说成全部（R163 归的 B 类），客户一开弹窗就抓到。两处各写一套
 * 迟早漂成两句互相打架的真话，所以句子只有这一枚出处。
 *
 * 三个不许：
 *   ① 不许数行：两个数一律来自后端 preview.row_scope 的 rows_in / rows_visible
 *      （app/api/v1/data.py::_row_scope_status 构形、:319 挂上），一枚 rows.length 都不参与；
 *   ② 不许猜因由：code 非空（row_scope_denied / no_visible_rows）就是后端自己的裁决，那一支
 *      的句子归后端的 message（走本组件已有的 error prop），这里一个字都不补 —— 只裁掉一部分
 *      的情形 code 恒为空串（契约 docs/api/contract-v1.md「Dataset Row-Level Visibility」）；
 *   ③ 不许越界说话：rows_in === rows_visible（含两者皆 0 的真空表）与读不到 row_scope 的载荷
 *      （上传回包、旧响应）一律空串，产物字节与本格装上之前逐字相同。
 */
export function rowScopeVisibleNote(scope) {
  if (!scope) return ''
  const rowsIn = scopeRowCount(scope.rows_in)
  const rowsVisible = scopeRowCount(scope.rows_visible)
  if (String(scope.code || '') !== '') return ''
  if (rowsIn > 0 && rowsVisible > 0 && rowsVisible < rowsIn) {
    return `全表 ${rowsIn} 行中，当前账号可见的 ${rowsVisible} 行`
  }
  return ''
}

/** 计数只认正整数：后端给 int，界面上不许出现 NaN、负数或小数冒充行数。 */
function scopeRowCount(value) {
  const count = Number(value)
  return Number.isFinite(count) && count > 0 ? Math.trunc(count) : 0
}

/**
 * R314 · 「依据 / 相关制度」这一格的全部判据（图谱撤下一级入口之后的承接面）。
 *
 * 计划书 docs/frontend-plan-2026-09-14.md 撤图谱一级入口时写的是「降为文档预览『依据 /
 * 相关制度』子视图」，而承接面一直没装上：员工读一篇制度，屏幕上没有任何一处告诉他这篇与
 * 别的文档登记过什么关系，那层关系只能去另一屏手输主体/关系/客体才看得到。
 *
 * 四条口径，逐条对上工单判据：
 *   ① 认文档只认整名（去空白、ASCII 大小写折叠后逐字相等）。「员工手册」与「员工手册.pdf」
 *      是两篇文档，差一个字也不许挂到这篇头上（判据②）；认不出来就走空那一支。
 *   ② 取数只有 GET /knowledge-graph/relations 一把读法，与 GraphPanel 同一个路径：R348 起带上
 *      ?document=，值是本篇登记名的原文（判据①）。服务端那一腿命中任一端，所以这篇出现在
 *      客体位的关系也照样回来 —— 这正是 R344 之前只能全量拉回浏览器里筛的原因。发出去的名字
 *      一律不归一：归一是服务端那把尺子的活，前端先归一遍就是两套口径同时活着。客户端那道整名
 *      判定留着当 belt，它与服务端那把尺子逐条同判（钉在 R344 的成对样本上，见 r348 件），哪天
 *      不同判当场红，而不是静默把行丢成「没有关联」。密级与部门一律不在这里重算，本屏只显示
 *      服务端裁过之后交回来的行（判据④）。
 *   ③ idle / loading / failed / empty / matched 各说各的话，读失败绝不落到 empty 那一支
 *      （判据③，与 GraphPanel 里「取不到就摆失败态」同一条不变量）。
 *   ④ 界面不产出任何统计量与推断：只把行摊开，不数「共几条」，不猜某条关系成不成立（判据⑤）。
 */

/** 文档名的比对形状：整名相等才算同一篇，空白与 ASCII 大小写不参与。 */
export function documentIdentityKey(value) {
  const text = String(value ?? '').replace(/\s+/g, '')
  return text.toLowerCase()
}

/** 状态词只翻后端在册的四枚值；翻不出就把服务器给的那个字原样带出，不替它编级别。 */
const RELATION_STATUS_WORDS = {
  candidate: '本人登记，还没核对',
  confirmed: '登记者已确认',
  promoted: '已核实并提升为口径',
  rejected: '已被驳回',
}

export function relationStatusWord(status) {
  const raw = String(status ?? '').trim()
  if (!raw) return ''
  return RELATION_STATUS_WORDS[raw] || raw
}

/** 登记时间只取日期那一段；不是日期形状就原样带出，不替后端格式化它没给的东西。 */
function relationDate(value) {
  const raw = String(value ?? '').trim()
  return /^\d{4}-\d{2}-\d{2}/.test(raw) ? raw.slice(0, 10) : raw
}

/** 对端文档名：登记时漏填就明说漏填，不许留一格空白让人猜。 */
function otherDocumentName(value) {
  const raw = String(value ?? '').trim()
  return raw ? `《${raw}》` : '（登记时没填文档名）'
}

const CURRENT_DOC_WORD = '这篇文档'

/**
 * 把服务端交回来的关系行摊成「这篇文档认得出自己那一头」的行。
 * role：source = 这篇在主体位；target = 这篇在客体位；both = 两端都是这篇。
 * 摊平之后模板只读自己的字段，后端那几枚裸字段名一个字符都不上屏。
 */
export function relationsAboutDocument(filename, relations) {
  const key = documentIdentityKey(filename)
  if (!key) return []
  const rows = []
  const list = Array.isArray(relations) ? relations : []
  list.forEach((item, index) => {
    if (!item || typeof item !== 'object') return
    const subject = String(item.source_entity ?? '').trim()
    const object = String(item.target ?? '').trim()
    const isSubject = !!subject && documentIdentityKey(subject) === key
    const isObject = !!object && documentIdentityKey(object) === key
    if (!isSubject && !isObject) return
    rows.push({
      rowKey: String(item.relation_id ?? '').trim() || 'relation-row-' + index,
      role: isSubject && isObject ? 'both' : isSubject ? 'source' : 'target',
      leftName: isSubject ? CURRENT_DOC_WORD : otherDocumentName(subject),
      rightName: isObject ? CURRENT_DOC_WORD : otherDocumentName(object),
      // R343 · 对端那一头的裸名字：「这篇文档」自己那一头留空，永远不可能是可点的那一枚。
      leftTarget: isSubject ? '' : subject,
      rightTarget: isObject ? '' : object,
      linkWord: String(item.relation ?? '').trim() || '（登记时没填关系）',
      evidence: String(item.source ?? '').trim(),
      statusWord: relationStatusWord(item.status),
      author: String(item.owner_id ?? '').trim(),
      registeredOn: relationDate(item.created_at),
    })
  })
  return rows
}

/** 五枚面的初值：还没开口之前，这一格一个字也不许替员工下结论。 */
const RELATED_DOCS_IDLE = { face: 'idle', rows: [], message: '', denied: false }

/**
 * 关系表那一枚读法的 URL（R348）：只带本篇登记名的原文，且只带这一枚过滤参数。
 * 只做 URL 编码，不做归一 —— 去空白与折叠大小写是服务端 document_identity_key 的活，
 * 前端要是先归一再发，同一篇文档就有了两把尺子；服务端那腿按任一端命中，客体位也认。
 */
export function relationsListingUrl(name) {
  return `/knowledge-graph/relations?document=${encodeURIComponent(String(name ?? ''))}`
}

/**
 * 读一次「这篇文档的关联」：出口只有 failed / empty / matched 三种。
 * fetchRelations 抛错、以及回的东西根本不是数组，都算 failed —— 把读失败画成「没有关联」
 * 是本项目反复被抓的那类假话，所以这里从返回值上就把两支分开，不给它们共用一张脸。
 * R348：登记名原文递给取数腿，筛由服务端做。服务端筛过之后交回空数组说的是「这篇没登记过
 * 关联」，那一支仍是 empty；读失败与形状不对仍是 failed。两件事不许因为「后端会筛」就并成一支。
 */
export async function readDocumentRelations(filename, fetchRelations) {
  try {
    const list = await fetchRelations(filename)
    if (!Array.isArray(list)) {
      return { ...RELATED_DOCS_IDLE, face: 'failed', message: '关系列表返回的数据结构不对，未能加载。' }
    }
    const rows = relationsAboutDocument(filename, list)
    if (rows.length) return { ...RELATED_DOCS_IDLE, face: 'matched', rows }
    return { ...RELATED_DOCS_IDLE, face: 'empty' }
  } catch (err) {
    const denied = isPermissionDenied(err)
    return {
      ...RELATED_DOCS_IDLE,
      face: 'failed',
      denied,
      message: denied
        ? '当前账号看不到这些关联登记，请联系管理员开通。'
        : errorDetail(err, '服务没有给出原因，稍后再试一次。'),
    }
  }
}

/**
 * 这一格的状态机：idle → loading →（failed | empty | matched）。
 * ref 由 <script setup> 递进来，于是每一次转场都能被测试真跑一遍，而不是只钉源码形状。
 * token 防的是「换了一篇文档，屏上还挂着上一篇的结论」：换了名字或重新打开，迟到的回包一律丢掉。
 */
export function createRelatedDocsStore({ ref, fetchRelations }) {
  const state = ref({ ...RELATED_DOCS_IDLE })
  let token = 0

  async function load(filename) {
    const mine = ++token
    const name = String(filename ?? '').trim()
    if (!name) {
      state.value = { ...RELATED_DOCS_IDLE }
      return
    }
    state.value = { ...RELATED_DOCS_IDLE, face: 'loading' }
    const next = await readDocumentRelations(name, fetchRelations)
    if (mine !== token) return
    state.value = next
  }

  function reset() {
    token += 1
    state.value = { ...RELATED_DOCS_IDLE }
  }

  return { state, load, reset }
}

/**
 * R343 · 「依据与相关制度」那一格里的对端文档要点得开（R314 的第二棒）。
 *
 * 病：R314 把对端的名字摊上了屏，但只是摊上屏 —— 员工想知道「这条依据的那份文件到底写了
 * 什么」，还得关掉预览、回文档列表自己搜。这一格把它改成就地可点开：在同一枚弹窗里换成对端
 * 那一篇的预览，并且回得来。
 *
 * 六条口径，逐条对上工单判据：
 *   ① 「对端确实是一篇文档」不由界面猜（判据①）：只认 GET /documents/catalog 交回来的那一份
 *      服务端已经裁过的名单，比对的尺子还是 R314 那枚整名 documentIdentityKey。名字像文件名、
 *      带扩展名都不算凭据 —— 对不上名单的一律留成纯文本，名单没读回来时也留成纯文本。
 *   ② 就地换 = 本组件自己的一层覆盖（判据②）：不开第二枚弹窗实例，props / emits 的对外契约
 *      一个字都不动，父组件不需要知道这一格存在过。
 *   ③ 回退用本组件的**一格栈**（判据③）：屏上永远只有「父组件打开的那一篇」与「从它出发点开的
 *      对端那一篇」两态，出口是抬头那枚「回到《…》」。没有路由跳转，也没有第二层历史 ——
 *      同一条依据链上跳两回，返回仍旧回到打开的那一篇，不做多级栈（那会与父组件的预览分叉）。
 *      同名 computed 盖住 props 的名字也是故意的：既有的预览分支链被 panel-states.test.js 钉在
 *      字面上（<UiLoadingState v-if="loading" 那一支、.preview-state.preview-error 那一支），
 *      改分支名就把别人的钉子铲了；盖住名字才能让那条链一个字不改就吃下「屏上这一篇」。
 *   ④ token 闸门与 R314 同一把尺子（判据④）：每一次 open 领一枚号，换目标 / 返回 / 关掉 /
 *      父组件换文档都把旧号作废；迟到的那一发既不上屏，也不许留下没人回收的对象 URL。
 *   ⑤ 跳转层五枚面互不顶替（判据⑤）：root / loading / ready / failed / unregistered。
 *      对端读不到（403、415、500、503、回包形状不对、缺正文）走 failed；404 那枚码走
 *      unregistered，它说的是「这个名字现在对不上库里的文档」，绝不是「这篇没有内容」。
 *   ⑥ 密级与部门仍然不在这里重算（判据⑥）：名单与预览都是服务端裁过之后交回来的东西，界面
 *      只比名字，不读、不判、不筛任何可见范围。
 *   ⑦ 取数代价（判据⑧）：目录一次「打开」只读一回，且只在真出现「对端不是这篇」的行时才读；
 *      跳一次 = 对端预览一发（PDF 再多一发正文，与父组件同一形状）+ 关联表那一发（R348 起带
 *      ?document=，一篇只有一发，多出来的那一枚过滤参数是服务端那腿）。新的一篇要有自己的关联，
 *      与父组件换文档同价：读法仍旧只有一枚，不许多出第二枚，也不许多带第二枚过滤参数。
 */

/** 后端在册的可预览种类只有这两枚（app/documents/preview.py），其余一律算读不到。 */
const PREVIEWABLE_KINDS = ['pdf', 'text']

/** 这一枚码在本屏只有一层意思：这个名字现在对不上库里任何一篇文档（404 的出口）。 */
const DOCUMENT_NOT_FOUND = 'resource_not_found'

/**
 * 预览回包 → 屏上能用的载荷；形状不对就回 null，由调用方摆「读不到」。
 * 两枚 kind 各自要求自己的正文：text 必须是字符串、pdf 必须带回正文块 —— 缺正文是读不到，
 * 不是「这篇是空的」。把读不到画成空内容正是判据⑤点名的那类假话。
 */
export function normalizePreviewPayload(filename, payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null
  const kind = String(payload.kind ?? '').trim()
  if (!PREVIEWABLE_KINDS.includes(kind)) return null
  if (kind === 'text' && typeof payload.text !== 'string') return null
  if (kind === 'pdf' && !payload.blob) return null
  return {
    filename: String(payload.filename ?? '').trim() || String(filename ?? '').trim(),
    kind,
    text: typeof payload.text === 'string' ? payload.text : '',
    truncated: Boolean(payload.truncated),
    blob: kind === 'pdf' ? payload.blob : null,
  }
}

/** 目录里的文档名：老部署回一串裸名字也接得住；认不出的形状就当没有这一行。 */
export function documentNamesFromCatalog(list) {
  const rows = Array.isArray(list) ? list : []
  const names = []
  rows.forEach(item => {
    const name = String(typeof item === 'string' ? item : (item && item.filename) ?? '').trim()
    if (name) names.push(name)
  })
  return names
}

/**
 * 对端那一行的名字 → 目录里登记的那一篇。认不出就回空串（判据①：认不出不许长出可点状），
 * 也不回「最像的那一枚」：近似名是另一篇，R314 那把整名尺子在这里量的是同一个东西。
 */
export function resolveCatalogName(name, names) {
  const key = documentIdentityKey(name)
  if (!key) return ''
  const list = Array.isArray(names) ? names : []
  const hit = list.find(item => documentIdentityKey(item) === key)
  return hit === undefined ? '' : String(hit)
}

/**
 * 把「可对端打开」标到 R314 摊好的行上：只加两枚动作字段，摊平的显示字段一个字不动。
 * 名单没读回来（还没读、读失败、读的是空库）时两枚都是空串 —— 那一行就维持 R314 今天的样子。
 */
export function markOpenableRelations(rows, names) {
  const list = Array.isArray(rows) ? rows : []
  return list.map(item => {
    const row = item && typeof item === 'object' ? item : {}
    return {
      ...row,
      leftOpen: resolveCatalogName(row.leftTarget, names),
      rightOpen: resolveCatalogName(row.rightTarget, names),
    }
  })
}

/** 跳转层的初值：屏上还是父组件打开的那一篇，这一层一个字都不覆盖。 */
export const PREVIEW_NAV_ROOT = { face: 'root', doc: null, message: '', denied: false }

/** 跳转层没跳到任何一篇时的形状：显示层不必到处判 null。 */
const NAV_NO_DOC = { filename: '', kind: '', text: '', truncated: false, blobUrl: '' }

/**
 * 屏上那一篇 = 跳转层那一屏；没跳过才是父组件递进来的那一篇（判据②③）。
 * 六枚字段一次算完：模板吃的是这一枚的产物，props 与 emits 的对外契约一个字都不动。
 * 三枚非 root 的面各自占死自己的出口 —— 换过去的那一篇读不到时，既不许回落到父组件
 * 那一篇的正文，也不许借它的错误句子冒充（那两句话说的是两篇不同的文档）。
 */
export function previewScreenView(nav, root) {
  const state = nav && typeof nav === 'object' ? nav : PREVIEW_NAV_ROOT
  const base = root && typeof root === 'object' ? root : {}
  if (state.face === 'root') {
    return {
      filename: String(base.filename ?? ''),
      kind: String(base.kind ?? ''),
      text: String(base.text ?? ''),
      blobUrl: String(base.blobUrl ?? ''),
      loading: Boolean(base.loading),
      error: String(base.error ?? ''),
    }
  }
  const doc = state.doc || NAV_NO_DOC
  const ready = state.face === 'ready'
  return {
    filename: String(doc.filename ?? ''),
    kind: ready ? String(doc.kind ?? '') : '',
    text: ready ? String(doc.text ?? '') : '',
    blobUrl: ready ? String(doc.blobUrl ?? '') : '',
    loading: state.face === 'loading',
    error: '',
  }
}

/**
 * 这一跳的状态机：root →（点对端）loading →（ready | failed | unregistered）→（返回）root。
 * 闸门与 R314 同形：每次开口领一枚号，作废之后那一发连对象 URL 都不许创建 ——
 * 迟到的回包上不了屏，也不会在浏览器里留下一枚没人回收的 blob。
 */
export function createPreviewNavStore({ ref, fetchPreview, createObjectUrl, revokeObjectUrl }) {
  const state = ref({ ...PREVIEW_NAV_ROOT })
  let token = 0
  let heldUrl = ''

  function release() {
    if (!heldUrl) return
    const url = heldUrl
    heldUrl = ''
    if (typeof revokeObjectUrl === 'function') revokeObjectUrl(url)
  }

  function refuse(target, message, denied) {
    state.value = { face: 'failed', doc: target, message, denied: !!denied }
  }

  async function open(filename) {
    const mine = ++token
    const name = String(filename ?? '').trim()
    if (!name) return false
    release()
    const target = { ...NAV_NO_DOC, filename: name }
    state.value = { ...PREVIEW_NAV_ROOT, face: 'loading', doc: target }
    let payload = null
    let failure = null
    try {
      payload = await fetchPreview(name)
    } catch (err) {
      failure = err
    }
    if (mine !== token) return false
    if (failure) {
      const denied = isPermissionDenied(failure)
      const missing = !denied && errorCodeOf(failure) === DOCUMENT_NOT_FOUND
      state.value = missing
        ? {
            face: 'unregistered',
            doc: target,
            denied: false,
            message: `《${name}》这一行登记的是名字，知识库里现在对不上这一篇文档。`,
          }
        : {
            face: 'failed',
            doc: target,
            denied,
            message: denied
              ? '这个账号打不开这篇文档，请联系管理员开通。'
              : errorDetail(failure, '这篇文档的预览没读到，稍后再试一次。'),
          }
      return true
    }
    const doc = normalizePreviewPayload(name, payload)
    if (!doc) {
      refuse(target, '预览返回的数据结构不对，未能加载。', false)
      return true
    }
    let blobUrl = ''
    if (doc.kind === 'pdf') {
      blobUrl = typeof createObjectUrl === 'function' ? String(createObjectUrl(doc.blob) ?? '') : ''
      if (!blobUrl) {
        refuse(target, '这篇 PDF 的正文没能换成本地可读的字节，未能加载。', false)
        return true
      }
    }
    heldUrl = blobUrl
    state.value = { face: 'ready', doc: { ...doc, blobUrl }, message: '', denied: false }
    return true
  }

  function leave() {
    token += 1
    release()
    state.value = { ...PREVIEW_NAV_ROOT }
  }

  /** 用户按「回到《…》」：屏上换回父组件打开的那一篇。 */
  function back() {
    leave()
  }

  /** 父组件换文档或关掉弹窗：连带把这一层的账清干净，迟到的一发作废。 */
  function reset() {
    leave()
  }

  return { state, open, back, reset }
}

/**
 * 名单那一发：一次「打开」只读一回（判据⑧）。
 * 读失败不自己重试，也不替谁下结论 —— 名单没有，对端那一行就还是纯文本，界面加一句说明。
 */
export function createDocumentNameStore({ ref, fetchNames }) {
  const state = ref({ face: 'idle', names: [] })
  let token = 0
  let pending = null

  function load() {
    if (pending) return pending
    const mine = ++token
    state.value = { ...state.value, face: 'loading' }
    pending = (async () => {
      let names = null
      try {
        names = await fetchNames()
      } catch {
        names = null
      }
      if (mine !== token) return
      state.value = Array.isArray(names) ? { face: 'ready', names } : { face: 'failed', names: [] }
    })()
    return pending
  }

  function reset() {
    token += 1
    pending = null
    state.value = { face: 'idle', names: [] }
  }

  return { state, load, reset }
}
</script>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../lib/api'
import { UiButton, UiEmptyState, UiErrorState, UiLoadingState } from './ui'

const props = defineProps({
  open: Boolean,
  filename: {
    type: String,
    default: ''
  },
  kind: {
    type: String,
    default: 'text'
  },
  text: {
    type: String,
    default: ''
  },
  blobUrl: {
    type: String,
    default: ''
  },
  columns: {
    type: Array,
    default: () => []
  },
  rows: {
    type: Array,
    default: () => []
  },
  loading: Boolean,
  error: {
    type: String,
    default: ''
  },
  truncated: Boolean,
  // R191：后端 preview.row_scope 的原样载荷（rows_in / rows_visible / code / reason_code）。
  // 缺席（null）= 这一份响应没有行级判定可说，弹窗照旧一个字都不插。
  rowScope: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close', 'download'])

const rowScopeNote = computed(() => rowScopeVisibleNote(props.rowScope))
// 分隔符由这一格自己带上：后端两数相等（或读不到 row_scope）时它是空串，
// 预览那一行的产物字节与本格装上之前逐字相同（R191 判据②）。
const rowScopeSuffix = computed(() => (rowScopeNote.value ? ` · ${rowScopeNote.value}` : ''))

// R314 · 「依据 / 相关制度」这一格，R348 收口：还是 GraphPanel 那枚读法、那一发，只是第一次
// 把本篇登记名的原文带给服务端（relationsListingUrl 只做 URL 编码，归一是服务端的尺子）。
// 客户端那道整名判定留着当 belt，它与服务端同判由 r348 件拿 R344 的成对样本逐条钉死。
async function fetchRelationRows(documentName) {
  const response = await api.get(relationsListingUrl(documentName))
  return response?.data?.relations
}

const relatedDocs = createRelatedDocsStore({ ref, fetchRelations: fetchRelationRows })
const relatedFace = computed(() => relatedDocs.state.value.face)
const relatedRows = computed(() => relatedDocs.state.value.rows)
const relatedMessage = computed(() => relatedDocs.state.value.message)
const relatedDenied = computed(() => relatedDocs.state.value.denied)
const relatedBusy = computed(() => relatedFace.value === 'loading')

// R343 · 目录名单：「对端确实是一篇文档」的唯一凭据。界面不按名字形状猜它是文档还是人名，
// 只把对端整名与这份服务端裁过的名单用 R314 那枚尺子逐字比（判据①⑥）。
const documentNames = createDocumentNameStore({ ref, fetchNames: fetchDocumentNames })
const catalogBlind = computed(() => documentNames.state.value.face === 'failed')
const openableRows = computed(() => markOpenableRelations(relatedRows.value, documentNames.state.value.names))

// R343 · 就地换预览的那一层：只在本组件里长出一格栈，不开第二枚弹窗，也不动对外契约。
const previewNav = createPreviewNavStore({
  ref,
  fetchPreview: fetchRelatedPreview,
  createObjectUrl: blob => URL.createObjectURL(blob),
  revokeObjectUrl: url => URL.revokeObjectURL(url),
})
const navFace = computed(() => previewNav.state.value.face)
const navActive = computed(() => navFace.value !== 'root')
const navReady = computed(() => navFace.value === 'ready')
const navFailed = computed(() => navFace.value === 'failed')
const navDenied = computed(() => previewNav.state.value.denied)
const navMessage = computed(() => previewNav.state.value.message)
const navDoc = computed(() => previewNav.state.value.doc || NAV_NO_DOC)
const navUnregistered = computed(() => (navFace.value === 'unregistered' ? navMessage.value : ''))
const returnLabel = computed(() => `回到《${props.filename}》`)

// 屏上这一篇的六枚字段一次算完（previewScreenView 是纯函数，甲组直接跑它）。
// 这几枚 computed 与 props 同名是刻意的：既有的预览分支链钉在别人测试件的字面上，
// 盖住名字才能让那条链一个字不改就吃下「屏上这一篇」（判据②③，父组件零改动）。
const view = computed(() => previewScreenView(previewNav.state.value, props))
const filename = computed(() => view.value.filename)
const kind = computed(() => view.value.kind)
const text = computed(() => view.value.text)
const blobUrl = computed(() => view.value.blobUrl)
const loading = computed(() => view.value.loading)
const error = computed(() => view.value.error)

/**
 * R343 新增的两处读法都走 lib/http 那一枚全站实例（同一个 token、同一条 401 出口），
 * 只是写在 request 通道上：R314 的钉子把「取数只有一把」钉在字面上 —— 全文件只许留一枚
 * get 调用，那一枚就是关联表的全量读法（不带过滤参数）。这一格不去改别人钉的件，
 * 也不为对端发明第二套关系读法：屏上换的那一篇要的名单与正文，走同一枚实例的 request。
 */
async function fetchDocumentNames() {
  const response = await api.request({ method: 'get', url: '/documents/catalog' })
  return documentNamesFromCatalog(response?.data?.documents)
}

/** 对端那一篇的预览：与父组件同一形状 —— 正文一发，PDF 再多一发字节。 */
async function fetchRelatedPreview(name) {
  const response = await api.request({ method: 'get', url: `/documents/${encodeURIComponent(name)}/preview` })
  const payload = response?.data
  if (String(payload?.kind ?? '').trim() !== 'pdf') return payload
  const file = await api.request({
    method: 'get',
    url: `/documents/${encodeURIComponent(name)}/file`,
    responseType: 'blob',
    params: { inline: true },
  })
  return { ...payload, blob: file?.data }
}

/** 点对端那一行：就地换成那一篇，关联表也跟着换成那一篇的（同一把尺子的两条腿）。 */
function openRelatedDocument(name) {
  const target = resolveCatalogName(name, documentNames.state.value.names)
  if (!target) return
  previewNav.open(target)
  readRelatedDocs()
}

/** 回到父组件打开的那一篇：一格栈只有这一格，出口就是抬头那枚「回到《…》」。 */
function backToOpenedDocument() {
  if (!navActive.value) return
  previewNav.back()
  readRelatedDocs()
}

/** 对端读不到那张脸的重试：无权限不给，与 R314 同一个分叉。 */
function retryRelatedPreview() {
  if (navDenied.value) return
  previewNav.open(navDoc.value.filename)
}

function readRelatedDocs() {
  relatedDocs.load(filename.value)
}

// 弹窗开一次读一次：这一格不缓存上一轮的结论，也不在一篇文档的名字下面摆另一篇的关系。
// 关掉即清空（重开先回到「未加载」），换文档时 store 里的 token 会把迟到的回包丢掉。
// 两枚源分开写：watch 一个每次新建的数组等于每次都算「变了」，预览的 loading/text 一变就重发一发。
// R343：父组件换文档或关掉弹窗，就地换的那一层与名单一起作废 —— 陈的结论一个字节都不留。
watch([() => props.open, () => props.filename], ([open, filename]) => {
  previewNav.reset()
  documentNames.reset()
  if (!open) {
    relatedDocs.reset()
    return
  }
  relatedDocs.load(filename)
})

// 只有真出现「对端不是这篇」的行，才值得为它读一回目录；一篇关联都没有就别多打一发（判据⑧）。
watch(relatedRows, rows => {
  if (rows.some(row => row.leftTarget || row.rightTarget)) documentNames.load()
})

// 卸载兜底：这一层自己造的对象 URL 只有这一层认得，组件没了它也必须没（判据⑧的副作用面）。
onBeforeUnmount(() => {
  previewNav.reset()
})

// SSR 不跑 onMounted：这一支只补「挂载时就已经是打开的」那种父组件，真浏览器里才成立。
onMounted(() => {
  if (props.open) relatedDocs.load(props.filename)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="preview-modal">
      <div v-if="open" class="preview-overlay" @click.self="emit('close')">
        <section class="preview-container" role="dialog" aria-modal="true" :aria-label="filename">
          <header class="preview-header">
            <div class="preview-heading">
              <strong>{{ filename }}</strong>
              <span v-if="navActive && !navReady">对端那一篇</span>
              <span v-else-if="kind === 'pdf'">PDF 阅读</span>
              <span v-else-if="kind === 'table'">数据预览</span>
              <span v-else>文本预览</span>
            </div>
            <div class="preview-actions">
              <!-- R343 · 一格栈的出口：回到父组件打开的那一篇，回的是哪一篇就写在按钮上（判据③⑦）。 -->
              <UiButton
                v-if="navActive"
                class="preview-btn"
                type="button"
                variant="ghost"
                :label="returnLabel"
                :aria-label="returnLabel"
                data-testid="r343-back-to-opened"
                @click="backToOpenedDocument"
              />
              <!-- 下载这一腿归父组件，而父组件只认它自己打开的那一篇：跳过去的那一发不摆下载，
                   免得点下去拿到的是别一篇（判据②不许改对外契约，所以收掉的是按钮本身）。 -->
              <UiButton v-if="!navActive" class="preview-btn" type="button" label="下载" data-testid="preview-download" @click="emit('download')" />
              <UiButton class="preview-close" type="button" variant="ghost" aria-label="关闭" label="×" data-testid="preview-close-x" @click="emit('close')" />
            </div>
          </header>

          <div class="preview-body">
            <UiLoadingState v-if="loading" label="正在加载预览..." variant="block" />
            <div v-else-if="error" class="preview-state preview-error">{{ error }}</div>
            <!--
              R343 · 对端那一篇读不到（403 / 415 / 500 / 503 / 回包形状不对 / 缺正文）走这张脸，
              无权限与真坏了在标题上分叉，且只有真坏了才给再打开一次。
            -->
            <div v-else-if="navFailed" class="preview-state" data-testid="r343-face-nav-failed">
              <UiErrorState
                :title="navDenied ? '这个账号打不开这篇对端文档' : '这篇对端文档的预览没读到'"
                :description="navMessage"
                :retryable="!navDenied"
                retry-text="再打开一次"
                dense
                @retry="retryRelatedPreview"
              />
            </div>
            <!-- R343 · 对端登记的名字这会儿对不上库里的文档：另一张脸，绝不说「这篇没有内容」。 -->
            <div v-else-if="navUnregistered" class="preview-state preview-unregistered" data-testid="r343-face-nav-unregistered">{{ navUnregistered }}</div>
            <iframe
              v-else-if="kind === 'pdf' && blobUrl"
              class="pdf-frame"
              :src="blobUrl"
              :title="filename"
            ></iframe>
            <pre v-else-if="kind === 'text'" class="text-preview">{{ text }}</pre>
            <div v-else-if="kind === 'table'" class="table-preview" data-preview>
              <div class="table-meta">
                <span>{{ rows.length }} 行预览{{ rowScopeSuffix }}</span>
                <span v-if="truncated">仅显示前 100 行</span>
              </div>
              <div v-if="!rows.length" class="preview-state">暂无数据</div>
              <div v-else class="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th v-for="column in columns" :key="column">{{ column }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, rowIndex) in rows" :key="rowIndex">
                      <td v-for="column in columns" :key="column">
                        {{ row[column] === null || row[column] === undefined ? '' : row[column] }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!--
            R314 · 图谱撤下一级入口之后由这一格承接：员工读一篇制度时就地看到「这篇和哪些
            文档登记过关系、是谁登记的」，不必去另一屏手输三元组。
            五枚面各说各的话：还没查 / 正在查 / 没查到 / 没查到对得上名字的 / 查到了。
            密级与部门不在这里重算，这一格只摆服务端裁过之后交回来的行。
          -->
          <aside class="related-docs" data-testid="document-relations" aria-label="依据与相关制度">
            <div class="related-docs-head">
              <h4>依据与相关制度</h4>
              <span>别人登记过的、文档名与这篇完全相同的关联</span>
            </div>

            <!-- 名单没读回来的那一刻，对端那一行只能看名字：这里明说，不许装作已经判过了。 -->
            <p v-if="catalogBlind" class="related-docs-note" data-testid="r343-catalog-blind">
              这会儿对不上库里的文档名单，对端先只能看名字，点不开。
            </p>

            <UiLoadingState
              v-if="relatedFace === 'loading'"
              label="正在查这篇文档的关联..."
              :rows="2"
              size="sm"
              dense
            />
            <p v-else-if="relatedFace === 'idle'" class="related-docs-note" data-testid="r314-face-idle">
              还没有去查这篇文档的关联。
            </p>
            <UiErrorState
              v-else-if="relatedFace === 'failed'"
              :title="relatedDenied ? '这个账号看不到关联登记' : '这篇文档的关联没查到'"
              :description="relatedMessage"
              :retryable="!relatedDenied"
              retry-text="重新加载"
              :busy="relatedBusy"
              dense
              data-testid="r314-face-failed"
              @retry="readRelatedDocs"
            />
            <UiEmptyState
              v-else-if="relatedFace === 'empty'"
              title="登记的关联里，没有文档名与这篇相同的"
              description="关联要有人一条条登记，登记过之后就会出现在这里。"
              dense
              data-testid="r314-face-empty"
            />
            <ul v-else class="related-docs-list" data-testid="r314-face-matched">
              <li v-for="row in openableRows" :key="row.rowKey" class="related-docs-item">
                <div class="related-docs-triple">
                  <!--
                    R343 · 判据①：对端这一头只有「整名对得上库里那一篇」才长成可点的控件，
                    对不上（人名、制度编号那类实体、没填名字、名单没读回来）一律留成纯文本。
                    判据⑦：可点那一枚是 components/ui 的真按钮，焦点可得，且说出点的是哪一篇。
                  -->
                  <UiButton
                    v-if="row.leftOpen"
                    class="related-docs-open"
                    type="button"
                    size="sm"
                    variant="ghost"
                    :label="row.leftName"
                    :aria-label="'打开这一篇：' + row.leftName"
                    data-testid="r343-open-document"
                    @click="openRelatedDocument(row.leftOpen)"
                  />
                  <strong v-if="!row.leftOpen" :class="{ 'is-current': row.role !== 'target' }">{{ row.leftName }}</strong>
                  <span class="related-docs-link">{{ row.linkWord }}</span>
                  <UiButton
                    v-if="row.rightOpen"
                    class="related-docs-open"
                    type="button"
                    size="sm"
                    variant="ghost"
                    :label="row.rightName"
                    :aria-label="'打开这一篇：' + row.rightName"
                    data-testid="r343-open-document"
                    @click="openRelatedDocument(row.rightOpen)"
                  />
                  <strong v-if="!row.rightOpen" :class="{ 'is-current': row.role !== 'source' }">{{ row.rightName }}</strong>
                </div>
                <div class="related-docs-meta">
                  <span>依据：{{ row.evidence || '登记时没填' }}</span>
                  <span v-if="row.statusWord">状态：{{ row.statusWord }}</span>
                  <span v-if="row.author">登记账号：{{ row.author }}</span>
                  <span v-if="row.registeredOn">登记于 {{ row.registeredOn }}</span>
                </div>
              </li>
            </ul>
          </aside>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: color-mix(in srgb, var(--legacy-veil) 82%, transparent);
  backdrop-filter: blur(4px);
}

.preview-container {
  width: min(1100px, 96vw);
  height: min(820px, 92vh);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--legacy-night-2);
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--legacy-steel) 18%, transparent);
  box-shadow: 0 24px 80px color-mix(in srgb, var(--legacy-void) 42%, transparent);
}

.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
  border-bottom: 1px solid color-mix(in srgb, var(--legacy-steel) 16%, transparent);
}

.preview-heading {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.preview-heading strong {
  overflow: hidden;
  color: var(--ink);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-heading span {
  flex-shrink: 0;
  color: var(--legacy-ink-steel);
  font-size: 12px;
}

.preview-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.preview-btn,
.preview-close {
  border: 1px solid color-mix(in srgb, var(--legacy-steel) 22%, transparent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--legacy-paper) 4%, transparent);
  color: var(--legacy-tint-azure);
  cursor: pointer;
  font: inherit;
}

.preview-btn {
  padding: 6px 12px;
  font-size: 12px;
}

.preview-btn:hover {
  border-color: var(--legacy-periwinkle-strong);
  color: var(--legacy-periwinkle-mid);
}

.preview-close {
  width: 30px;
  height: 30px;
  font-size: 20px;
  line-height: 1;
}

.preview-close:hover {
  background: color-mix(in srgb, var(--legacy-periwinkle-strong) 12%, transparent);
}

.preview-body {
  flex: 1;
  min-height: 0;
  background: var(--legacy-night-1);
}

.preview-state {
  display: grid;
  height: 100%;
  place-items: center;
  padding: 24px;
  color: var(--legacy-ink-steel);
  font-size: 13px;
}

.preview-error {
  color: var(--legacy-coral);
}

/* R343 · 对端登记的名字对不上库里那一篇：中性档，与上面那枚珊瑚色的「读不到」分成两张脸。 */
.preview-unregistered {
  color: var(--legacy-ink-steel);
}

.pdf-frame {
  width: 100%;
  height: 100%;
  border: 0;
  background: var(--legacy-slate-dark);
}

.text-preview {
  height: 100%;
  margin: 0;
  overflow: auto;
  padding: 24px;
  color: var(--legacy-tint-azure-soft);
  background: var(--legacy-night-3);
  font: 13px/1.75 Consolas, "Microsoft YaHei", monospace;
  white-space: pre-wrap;
  word-break: break-word;
}

.table-preview {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 16px;
}

.table-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 10px;
  color: var(--legacy-ink-steel);
  font-size: 12px;
}

.table-scroll {
  flex: 1;
  overflow: auto;
  border: 1px solid color-mix(in srgb, var(--legacy-steel) 16%, transparent);
  background: var(--legacy-night-4);
}

table {
  width: 100%;
  min-width: max-content;
  border-collapse: collapse;
  font-size: 12px;
}

th,
td {
  min-width: 120px;
  max-width: 280px;
  padding: 9px 12px;
  border-right: 1px solid color-mix(in srgb, var(--legacy-steel) 12%, transparent);
  border-bottom: 1px solid color-mix(in srgb, var(--legacy-steel) 12%, transparent);
  text-align: left;
  vertical-align: top;
  white-space: nowrap;
}

th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--legacy-aqua-night);
  color: var(--legacy-mint);
  font-weight: 600;
}

td {
  color: var(--legacy-tint-azure);
}

tr:hover td {
  background: color-mix(in srgb, var(--legacy-periwinkle-strong) 8%, transparent);
}

/* R314 · 「依据 / 相关制度」这一格：贴在预览正文下面的一条抽屉，只借既有的深色档与中性字色。 */
.related-docs {
  flex-shrink: 0;
  max-height: 34%;
  overflow-y: auto;
  padding: 12px 18px 16px;
  border-top: 1px solid color-mix(in srgb, var(--legacy-steel) 16%, transparent);
  background: var(--legacy-night-2);
}

.related-docs-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 8px;
}

.related-docs-head h4 {
  margin: 0;
  color: var(--ink);
  font-size: 13px;
  font-weight: 600;
}

.related-docs-head span {
  color: var(--legacy-ink-steel);
  font-size: 11px;
}

.related-docs-note {
  margin: 0;
  color: var(--legacy-ink-steel);
  font-size: 12px;
}

.related-docs-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.related-docs-item {
  padding: 9px 11px;
  border: 1px solid color-mix(in srgb, var(--legacy-steel) 12%, transparent);
  border-radius: 6px;
  background: var(--legacy-night-4);
}

.related-docs-triple {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--legacy-tint-azure);
  font-size: 12px;
}

.related-docs-triple .is-current {
  color: var(--legacy-mint);
}

/*
 * R343 · 对端那一行的可点出口：名字本身就是一枚真按钮（components/ui 的 UiButton），
 * 这里只把它收进行内的字号与高度，颜色继续走既有 token。
 */
.related-docs-open {
  min-height: 0;
  padding: 0 4px;
  border: 0;
  border-radius: 4px;
  color: var(--legacy-tint-azure);
  font-size: 12px;
  font-weight: 600;
  text-decoration: underline;
}

.related-docs-open:hover:not(:disabled) {
  color: var(--legacy-periwinkle-mid);
  background: color-mix(in srgb, var(--legacy-periwinkle-strong) 12%, transparent);
}

.related-docs-link {
  color: var(--legacy-ink-steel);
  font-size: 11px;
}

.related-docs-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 6px;
  color: var(--legacy-ink-steel);
  font-size: 11px;
}

.preview-modal-enter-active,
.preview-modal-leave-active {
  transition: opacity 0.18s ease;
}

.preview-modal-enter-active .preview-container,
.preview-modal-leave-active .preview-container {
  transition: transform 0.18s ease;
}

.preview-modal-enter-from,
.preview-modal-leave-to {
  opacity: 0;
}

.preview-modal-enter-from .preview-container {
  transform: translateY(10px) scale(0.98);
}
</style>
