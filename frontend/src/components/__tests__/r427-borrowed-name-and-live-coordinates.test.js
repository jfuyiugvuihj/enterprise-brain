/**
 * R427 · 借名屏同族病（六处改口）＋ 五处死坐标引用（现读推导对账），五组独立腿
 *
 * 要治的病（业主 09-28 派工，接 `Hume`/R421 与 `Beauvoir`/R423 已定的口径）：
 *   甲族「借名屏」——文案把界面上不存在的那一格当对象名。屏上没有一枚叫那三个字的格子，侧栏里也
 *   没有那枚屏名（跟进单 G17 已把它从屏名位退下），句子却拿它当招牌，还替后端宣布它跑了哪条腿。
 *   本单治的六处（逐枚现读取证后才动）：
 *     GraphPanel.vue:123 / ApprovalPanel.vue:96 / ApprovalPanel.vue:197 / ApprovalPanel.vue:240
 *     / lib/provenance.js:119 / DocumentPreviewModal.vue:379
 *   乙族「死坐标」——手抄行号已经指到别处去了。本单治的五处引用（旧值 -> 真值，全部现场推导；
 *   业主 09-28 二次裁定把 r293 的 :35 与 :46 两枚并入本单，同尺、同族账、零插行零删行）：
 *     r197-turn-key-inheritance.test.js:293  sessions.js:814（今天是一枚空行）-> :128
 *     tests/test_r210_break_replaces_the_screen.py:6  sessions.js:491（那是 answer.headline 的
 *       注解，写的恰恰是「整段替换而不是追加」）-> :529
 *     r293-cancel-requested-persist.test.js:53  ChatPanel.vue:767 -> :806、:702 -> :740、
 *       lib/sessions.js:159 -> :153（:159 今天是 rememberScroll 里那一发 syncActive() 调用，
 *       看着像活的，其实是下一环；:63 与 :76 本来就对，一字节未动）
 *     r293-cancel-requested-persist.test.js:35  ChatPanel.vue:743 -> :786、:748-755 ->
 *       :793-798（:743 今天是 flushScroll 尾上的 scrollSaveTimer = null，:748-755 那一段
 *       今天归 onScroll 与 onVisibilityChange，跟 loadSessions / restoreActive 两腿不相干）
 *     r293-cancel-requested-persist.test.js:46  ChatPanel.vue:1317 -> :1365（:1317 今天是
 *       dictionarySentence 的函数头，取的是错误码字典句，不是排队脸）
 *   🔴 同一本件 :6 里那一对同族坐标（ChatPanel.vue:1309 那条守卫 / :1317 那一腿）现读同样已死
 *   ——守卫真值 :1357、queueFace 真值 :1365——但它不在本轮批准的射程里，只报不改；戊组因此
 *   刻意不断言 :6：本单没治它，它坏了不该红，它留着也不该绿。
 *
 * 五组断言，缺一组都不算收口：
 *   甲 六处改口逐枚在位：旧句在源里 0 命中、新句在位；改口不许只是换个说法又留一份。
 *   乙 可达性逐枚：新句真绑在屏上某一格 —— 图谱与审批页拿 SSR 真产物，出处那一格与预览跳转层
 *     拿【真函数跑出来的读数】再加模板那一行的 data-testid；注解不算证据。
 *   丙 在册钉零放宽：本单改的六句里，被既存用例逐字钉着的锚片段一枚都没被洗掉；那十枚钉自己的
 *     断言原文也仍逐字在位。放宽看守钉等于把病灶换个地方再埋一次。
 *   丁 阻塞账（棘轮 5 枚）：另外五处同族病灶今天【改不了】，不是漏做 —— 每一句都被一枚不在本单
 *     写域里的在册钉逐字钉着（钉的原文在本件列得出）。枚数现扫现取：多一枚是回退，少一枚说明
 *     挡路的那枚钉已改口、这一单该重开。
 *   戊 五处死坐标引用逐枚对账：注释声称的数字必须等于在目标文件里当场推导的那一行，被引那一行还得
 *     真写着锚串；旧值不许抄回来（0 命中按短语取面，不拿裸数字满件扫——:6 那一对本单没治，
 *     它留着是诚实账，不该因为本件扫裸数字而红）；引用本身不许删（删了等于下一个人再踩一遍）。
 *
 * 反证怎么算红：
 *   刀一 把六句里任何一句改回旧话 => 甲组那一枚当场红，乙组（真产物／派生读数）同时红；
 *   刀二 改口时把「说不出超没超标」「是此刻取不到」「它不办理审批」「对不上这一篇文档」任一锚片段
 *          洗掉 => 丙组红，r247 / insight-alerts / r174 / r343 也同时红（双向咬住）；
 *   刀三 顺手把 ApprovalPanel.vue:91 或 :276 那两句也改了（它们不在本单射程）=> 丙组与丁组一起红；
 *   刀四 借名句抄出新位置（文案里多出第六枚）=> 丁组棘轮红；把阻塞账删短一行 => 丁组第二条红；
 *   刀五 把五处坐标的数字改回旧值 => 戊组「旧值 0 命中」红；把引用整句删掉躲检查 => 戊组「引用仍在
 *          原位」红；目标文件挪了行而不改注释 => 戊组「声称 == 推导」红（这正是要的形状：宁可红，不撒谎）。
 *          对着 :35 / :46 同样成立：抄回 743、748-755、1317 那三个数 => 戊组第四、第五枚当场红。
 *
 * 真源口径与 r416 / r420 同一式：坐标【声称】的数字读工作树（本单就是来改它的），坐标【指向】的
 * 目标文件一律 git show HEAD:<path> 现取 —— 工作树可能停在分支点，拿它对账等于永远绿的假绿。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { h, ref } from 'vue'
import { renderToString } from '@vue/server-renderer'
import ApprovalPanel from '../ApprovalPanel.vue'
import DocumentPreviewModal, { createPreviewNavStore } from '../DocumentPreviewModal.vue'
import GraphPanel from '../GraphPanel.vue'
import { sourcesFace } from '../../lib/provenance'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const GRAPH = read('../GraphPanel.vue')
const APPROVAL = read('../ApprovalPanel.vue')
const PROVENANCE = read('../../lib/provenance.js')
const PREVIEW = read('../DocumentPreviewModal.vue')
const SOURCE_CARD = read('../SourceCard.vue')
const R197 = read('./r197-turn-key-inheritance.test.js')
const R293 = read('./r293-cancel-requested-persist.test.js')
const R210 = read('../../../../tests/test_r210_break_replaces_the_screen.py')
const render = component => renderToString(h({ render: () => h(component) }))
const BORROWED = '知识库'

/** 改口之后那六句的字面：逐枚从源里当场抠出来，本件不抄第二份。 */
const NEW_COPY = {
  'GraphPanel.vue:123': /description="(这一格[^"]*)"/.exec(GRAPH)[1],
  'ApprovalPanel.vue:96': /return '([^']*说不出超没超标[^']*)'/.exec(APPROVAL)[1],
  'ApprovalPanel.vue:197': /<p>(这是一台报销政策自查工具[^<]*)<\/p>/.exec(APPROVAL)[1],
  'ApprovalPanel.vue:240': /(这一格没有「标准」输入框[^<]*)/.exec(APPROVAL)[1].trim(),
  'provenance.js:119': /reason: '([^']*可点开的资料出处[^']*)',/.exec(PROVENANCE)[1],
  'DocumentPreviewModal.vue:379': /message: `([^`]*)`/.exec(PREVIEW)[1],
}

// ==================== 甲 · 六处改口逐枚在位 ====================

describe('R427甲 · 六处借名句改口：旧句零命中，新句在位', () => {
  it('那八段旧话一枚都不许留在射程内的源里：改口不是又抄一份', () => {
    const dead = [
      '关系是从已登记的制度与指标里长出来的',
      '先有一条就能看到连线',
      '现在从知识库里取不到比的那个数',
      '知识库恢复后点「重新预审」再取一次',
      '看金额按【服务端从知识库取到的标准】',
      '它的出处都由服务端从知识库里取',
      '下面的回答不来自知识库',
      '知识库里现在对不上这一篇文档',
    ]
    const corpus = [GRAPH, APPROVAL, PROVENANCE, PREVIEW].join('\n')
    for (const sentence of dead) {
      expect(corpus, '这一句旧话又回来了：' + sentence).not.toContain(sentence)
    }
  })

  it('六句里再没有那枚借来的招牌，也不许是空的一句', () => {
    for (const [spot, copy] of Object.entries(NEW_COPY)) {
      expect(copy, '这一格又把那枚屏名当对象名了：' + spot).not.toContain(BORROWED)
      expect(copy.length, '这一句是空的：' + spot).toBeGreaterThan(8)
    }
  })

  it('新句都不替后端宣布它跑了哪条腿（R423 乙组同一把尺）', () => {
    for (const [spot, copy] of Object.entries(NEW_COPY)) {
      expect(copy, '这一句替后端报腿名：' + spot).not.toMatch(/检索|知识库|索引/)
    }
  })
})

// ==================== 乙 · 可达性 ====================

describe('R427乙 · 每句都真绑在屏上某一格（注解不算证据）', () => {
  it('图谱空态那张脸：SSR 真产物画的就是新句（GraphPanel.vue:120-124 那一枚 UiEmptyState）', async () => {
    const html = await render(GraphPanel)
    expect(html).toContain('data-testid="ui-empty-state"')
    expect(html).toContain(NEW_COPY['GraphPanel.vue:123'])
    expect(html).not.toContain('连线')
  })

  it('审批页首屏：:197 那句与 :240 那句都真上屏，后者绑在 data-testid="approval-standard-source-hint"', async () => {
    const html = await render(ApprovalPanel)
    expect(html).toContain(NEW_COPY['ApprovalPanel.vue:197'])
    expect(APPROVAL).toMatch(/<p class="source-hint" data-testid="approval-standard-source-hint">/)
    expect(html).toMatch(/data-testid="approval-standard-source-hint"/)
    expect(html).toContain(NEW_COPY['ApprovalPanel.vue:240'])
  })

  it('降级那张脸：:96 那句由 failureCopy 交给 UiErrorState 的 description（ApprovalPanel.vue:252-255）', () => {
    expect(APPROVAL).toMatch(/const failureCopy = computed\(\(\) => \{[\s\S]*?return '这一屏没有拿到/)
    expect(APPROVAL).toMatch(/<UiErrorState\s+v-if="failed"[\s\S]{0,120}:description="failureCopy"/)
  })

  it('出处那一格：sourcesFace 现派生的 reason 就是新句，而它由 data-testid="source-reason" 画（SourceCard.vue:88）', () => {
    const face = sourcesFace({ rows: [], hitCount: 0, hiddenCount: 0, scopeReasonCode: '' })
    expect(face.kind).toBe('none')
    expect(face.reason).toBe(NEW_COPY['provenance.js:119'])
    expect(SOURCE_CARD).toMatch(/<p v-if="face\.reason" class="source-reason" data-testid="source-reason">\{\{ face\.reason \}\}<\/p>/)
  })

  it('预览那一格：真状态机跑出 unregistered 面的 message 就是新句，而它由 data-testid="r343-face-nav-unregistered" 画', async () => {
    const missing = { response: { status: 404, data: { detail: 'resource_not_found' } }, message: 'Request failed with status code 404' }
    const store = createPreviewNavStore({
      ref,
      fetchPreview: async () => { throw missing },
      createObjectUrl: () => '',
      revokeObjectUrl: () => {},
    })
    await store.open('报销制度.pdf')
    expect(store.state.value.face).toBe('unregistered')
    expect(store.state.value.message).toBe(NEW_COPY['DocumentPreviewModal.vue:379'].replace('${name}', '报销制度.pdf'))
    expect(PREVIEW).toMatch(/const navMessage = computed\(\(\) => previewNav\.state\.value\.message\)/)
    expect(PREVIEW).toMatch(/<div v-else-if="navUnregistered"[\s\S]*?data-testid="r343-face-nav-unregistered">\{\{ navUnregistered \}\}<\/div>/)
  })
})

// ==================== 丙 · 在册钉一枚都没被放宽 ====================

/** 被既存用例逐字钉着的锚片段：本单改的那几句必须仍然带着它们，钉自己的原文也必须还在。 */
const KEPT_ANCHORS = [
  ['ApprovalPanel.vue:96', '说不出超没超标', './r247-approval-mount-dedupe.test.js', "expect(html).toContain('说不出超没超标')"],
  ['ApprovalPanel.vue:96', '是此刻取不到', './r247-approval-mount-dedupe.test.js', "expect(html).toContain('是此刻取不到')"],
  ['ApprovalPanel.vue:197', '它不办理审批', './insight-alerts.test.js', "'审批与待办', '它不办理审批'"],
  ['ApprovalPanel.vue:197', '它不办理审批', './r174-screen-name.test.js', "'自查工具，不是审批', '它不办理审批'"],
  ['DocumentPreviewModal.vue:379', '对不上这一篇文档', './r343-open-related-document.test.js', "const UNREGISTERED_COPY = '对不上这一篇文档'"],
]

describe('R427丙 · 在册钉零放宽：锚片段仍在，钉原文也仍在', () => {
  it('本单改口的三句，被钉的锚片段逐枚仍在位，挡路那几枚钉自己那行字面未动', () => {
    expect(KEPT_ANCHORS).toHaveLength(5)
    for (const [spot, anchor, pinFile, pinText] of KEPT_ANCHORS) {
      expect(NEW_COPY[spot], '锚片段被本单洗掉了：' + anchor + '（在 ' + spot + '）').toContain(anchor)
      expect(read(pinFile), '那一枚在册钉被放宽或摘掉了：' + pinFile + '「' + anchor + '」').toContain(pinText)
    }
  })

  it('本单没碰的锚同样原样在位：r237 四枚、r247 两枚、r168 一枚、r195 一枚、r277 一枚', () => {
    for (const [pinFile, pinText] of [
      ['./r237-r40-standard-auto.test.js', "expect(panel).toContain('由服务端从知识库检索')"],
      ['./r237-r40-standard-auto.test.js', "expect(line[0].text).toContain('服务端从知识库检索')"],
      ['./r237-r40-standard-auto.test.js', "expect(html).not.toContain('上面的标准是服务端从知识库检索出来的那一个数')"],
      ['./r237-r40-standard-auto.test.js', "expect(html).toContain('上方那一屏挂起待办读的是服务端真账本')"],
      ['./r168-hitl-decision.test.js', 'expect(s).toMatch(/上方那一屏挂起待办读的是服务端真账本/)'],
      ['./r247-approval-mount-dedupe.test.js', "expect(first).toContain('服务端从知识库检索')"],
      ['./r247-approval-mount-dedupe.test.js', "expect(html).toContain('切回这一屏没有重新问知识库')"],
      ['./r247-approval-mount-dedupe.test.js', "expect(html).toContain('知识库取不到报销标准')"],
      ['./r277-approval-selfcheck-truth.test.js', "expect(html).toContain('知识库取不到报销标准')"],
      ['./r195-source-feedback.test.js', "expect(text).toContain('本轮没有检索到可用文档')"],
    ]) {
      expect(read(pinFile), '那一枚在册钉被本单顺手放宽了：' + pinText).toContain(pinText)
    }
  })

  it('反向自证：那五句被钉的原文确实还长在屏上（放宽钉与改产品必须一起红）', () => {
    expect(APPROVAL).toContain('由服务端从知识库检索后随结论一起回')
    expect(APPROVAL).toContain('上面的标准是服务端从知识库检索出来的那一个数')
    expect(APPROVAL).toContain('上方那一屏挂起待办读的是服务端真账本')
    expect(PROVENANCE).toContain('本轮没有检索到可用文档')
  })
})

// ==================== 丁 · 阻塞账（棘轮） ====================

/** 剥注释才叫文案：注解里叙述那枚旧叫法是历史账，不上屏（与 R421 乙 / R423 甲 同一把尺）。 */
const copyOf = text => text.split('\n')
  .filter(line => !line.trim().startsWith('//') && !line.trim().startsWith('*') && !line.trim().startsWith('/*'))
  .map(line => line.split(' // ')[0])
  .join('\n')
  .replace(/<!--[\s\S]*?-->/g, '')

/** 五处改不了的同族病灶：每一句都被一枚不在本单写域里的在册钉逐字钉着。 */
const BLOCKED = [
  ['../GraphPanel.vue', '知识库里还没有已登记的关系', [
    ['./panel-states.test.js', "expect(html).toContain('知识库里还没有已登记的关系')"],
    ['./v7-fake-data.test.js', "expect(html).toContain('知识库里还没有已登记的关系')"],
  ]],
  ['../ApprovalPanel.vue', '知识库取不到报销标准', [
    ['./r247-approval-mount-dedupe.test.js', "expect(html).toContain('知识库取不到报销标准')"],
    ['./r277-approval-selfcheck-truth.test.js', "expect(html).toContain('知识库取不到报销标准')"],
  ]],
  ['../ApprovalPanel.vue', '切回这一屏没有重新问知识库', [
    ['./r247-approval-mount-dedupe.test.js', "expect(html).toContain('切回这一屏没有重新问知识库')"],
  ]],
  ['../ApprovalPanel.vue', '由服务端从知识库检索后随结论一起回', [
    ['./r237-r40-standard-auto.test.js', "expect(panel).toContain('由服务端从知识库检索')"],
    ['./r168-hitl-decision.test.js', 'expect(s).toMatch(/上方那一屏挂起待办读的是服务端真账本/)'],
  ]],
  ['../ApprovalPanel.vue', '上面的标准是服务端从知识库检索出来的那一个数', [
    ['./r237-r40-standard-auto.test.js', "expect(line[0].text).toContain('服务端从知识库检索')"],
    ['./r247-approval-mount-dedupe.test.js', "expect(first).toContain('服务端从知识库检索')"],
  ]],
]

const dirtyLines = [GRAPH, APPROVAL, PROVENANCE, PREVIEW]
  .flatMap(text => copyOf(text).split('\n'))
  .filter(line => line.includes(BORROWED))

describe('R427丁 · 阻塞账：五处病灶今天改不了，是被钉住的，不是漏做', () => {
  it('射程内四枚文件的文案里，那枚借来的招牌现扫现取 = 5 枚：多一枚是回退，少一枚是这本账该重开', () => {
    const occurrences = dirtyLines.reduce((sum, line) => sum + (line.match(new RegExp(BORROWED, 'g')) || []).length, 0)
    expect(occurrences, '文案里那枚屏名现取 ' + occurrences + ' 枚，账上是 5 枚').toBe(5)
    expect(dirtyLines, '那五枚屏名不落在五行上：账形变了').toHaveLength(5)
    expect(BLOCKED, '阻塞账的枚数与本件自述不等').toHaveLength(5)
  })

  it('逐枚点名：病灶句仍在产品里，挡路的那枚钉原文也仍在它的件里', () => {
    for (const [productFile, sentence, pins] of BLOCKED) {
      expect(read(productFile), '这一句已被别单改口，本账过期：' + sentence).toContain(sentence)
      expect(dirtyLines.some(line => line.includes(sentence)), '这一句不在现扫的脏行里，账与扫描不等：' + sentence).toBe(true)
      for (const [pinFile, pinText] of pins) {
        expect(read(pinFile), '挡路的那枚钉已改口，本账过期：' + pinFile).toContain(pinText)
      }
    }
  })

  it('审批页文案里那枚屏名只许活在挡路的四句里：本单改口没多留一枚，也没多删一枚', () => {
    expect(copyOf(APPROVAL).split('\n').filter(line => line.includes(BORROWED))).toHaveLength(4)
  })
})

// ==================== 戊 · 五处死坐标引用 ====================

const SESSIONS = 'frontend/src/lib/sessions.js'
const CHAT = 'frontend/src/components/ChatPanel.vue'

function headLines(repoPath) {
  let text
  try {
    text = execFileSync('git', ['show', 'HEAD:' + repoPath], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  } catch (cause) {
    throw new Error('读不到真源 HEAD:' + repoPath + '（git show 失败：' + cause.message + '）。行号对账不许降级成 skip。')
  }
  if (!String(text).trim()) throw new Error('git show HEAD:' + repoPath + ' 返回空内容，无法对账。')
  return String(text).replace(/\r\n/g, '\n').split('\n')
}

/** 当场推导：从 from 行起找到第一条写着锚串的行（1-based）。找不到就抛，这条账必须红。 */
function derived(repoPath, pattern, label, from = 0) {
  const lines = headLines(repoPath)
  const search = new RegExp(pattern)
  for (let index = from; index < lines.length; index += 1) {
    if (search.test(lines[index])) return { line: index + 1, text: lines[index].trim(), lines }
  }
  throw new Error('现读推导落空：' + label + '（' + repoPath + ' 找 /' + pattern + '/，从第 ' + (from + 1) + ' 行数起）')
}

const APPEND = derived(SESSIONS, '^\\s*else msg\\.content = ', 'text 帧的追加分支')
const RESTORE = derived(SESSIONS, '^export function restoreActive\\(', 'restoreActive 的函数头')
const ASSIGN = derived(SESSIONS, '^\\s*messages\\.value = entry \\?', 'restoreActive 里整份换掉 messages.value 那一行', RESTORE.line)
const SCROLL = derived(SESSIONS, '^export function rememberScroll\\(', 'rememberScroll 的函数头')
const SYNC = derived(SESSIONS, '^export function syncActive\\(', 'syncActive 的函数头')
const PERSIST = derived(SESSIONS, '^ {2}persist\\(\\)$', 'syncActive 里那一发 persist', SYNC.line)
const UNMOUNTED = derived(CHAT, '^onUnmounted\\(\\(\\) => \\{$', 'ChatPanel 的 onUnmounted')
const FLUSH = derived(CHAT, '^function flushScroll\\(\\) \\{$', 'ChatPanel 的 flushScroll 函数头')
const MOUNTED = derived(CHAT, '^onMounted\\(\\(\\) => \\{$', 'ChatPanel 的 onMounted')
const QUEUED = derived(CHAT, '^ {2}restoreQueuedTurns\\(\\)$', 'onMounted 里那一发 restoreQueuedTurns', MOUNTED.line)
const LOAD = derived(CHAT, '^ {4}const storedActive = loadSessions\\(\\)$', 'onMounted 里的 loadSessions 那一腿', QUEUED.line)
const PULL = derived(CHAT, '^ {2}if \\(!messages\\.value\\.length && !linked\\) restoreActive', 'onMounted 里的 restoreActive 那一腿', LOAD.line)
const QF = derived(CHAT, '^ {4}face = msg\\.queue \\? queueFace\\(msg\\.queue\\) : null$', '刷新那一腿读的 queueFace(msg.queue)')
const GUARD = derived(CHAT, '^ {2}\\} else if \\(read && !QUEUE_SETTLED\\.includes\\(read\\.status\\)$', '读数那格的守卫（r293:6 引的正是它，本单不碰）')

describe('R427戊 · 五处死坐标引用逐枚对账：声称的数字必须等于当场推导', () => {
  it('r197:293 声称 sessions.js:' + ASSIGN.line + ' —— 那一行真写着整份换掉 messages.value；旧值 814 已不在件里', () => {
    expect(ASSIGN.text).toBe('messages.value = entry ? [...entry.messages] : []')
    expect(RESTORE.text).toContain('export function restoreActive(')
    expect(R197).toContain('messages.value（sessions.js:' + ASSIGN.line + '）')
    expect(R197).not.toMatch(/sessions\.js:814/)
  })

  it('test_r210:6 声称 sessions.js:' + APPEND.line + ' —— 那一行就是追加分支本体；旧值 491 指的却是「不是追加」', () => {
    expect(APPEND.text).toMatch(/^else msg\.content = /)
    expect(R210).toContain('sessions.js:' + APPEND.line + '`` 的**追加**分支')
    expect(R210).not.toMatch(/sessions\.js:491/)
    expect(headLines(SESSIONS)[490]).not.toMatch(/else msg\.content = /)
    expect(headLines(SESSIONS)[490]).toContain('替换而不是追加')
  })

  it('r293:53 那条通道五枚坐标逐枚相等（:' + UNMOUNTED.line + ' -> :' + FLUSH.line + ' -> :' + SCROLL.line + ' -> :' + SYNC.line + ' -> :' + PERSIST.line + '）', () => {
    expect(R293).toContain('ChatPanel.vue:' + UNMOUNTED.line + ' onUnmounted -> :' + FLUSH.line + ' flushScroll -> lib/sessions.js:' + SCROLL.line)
    expect(R293).toContain('rememberScroll -> :' + SYNC.line + ' syncActive -> :' + PERSIST.line + ' persist')
    // 🔴 这三格原来钉的是「函数头 + 一枚写死的行距」（+4 / +5 / +6）。行距是别人插一行就会失效的东西：
    // 09-28 的 R458 在 onUnmounted 块里加了一发 clearRecheckFaceTimer()，+4 当场被打成假红（本席现取 flushScroll() 在 :894）。
    // 改口成按块形状推导——「这一发的函数体里必须恰好有那一枚调用」：调用消失即红，挪远挪近不红。强度只升不降。
    const callsIn = (head, callee) => {
      let depth = 0
      const body = []
      for (let i = head.line - 1; i < head.lines.length; i++) {
        const line = head.lines[i]
        if (i > head.line - 1) body.push(line)
        for (const ch of line) {
          if (ch === '{') depth += 1
          else if (ch === '}') depth -= 1
        }
        if (i > head.line - 1 && depth <= 0) break
      }
      return body.filter((l) => l.trim() === callee).length
    }
    expect(callsIn(UNMOUNTED, 'flushScroll()'), 'onUnmounted 那一块里 flushScroll() 必须恰好一发（摘掉它这一格就要红）').toBe(1)
    expect(callsIn(FLUSH, 'rememberScroll()'), 'flushScroll 那一块里 rememberScroll() 必须恰好一发').toBe(1)
    expect(callsIn(SCROLL, 'syncActive()'), 'rememberScroll 那一块里 syncActive() 必须恰好一发').toBe(1)
    expect(SCROLL.lines[SCROLL.line - 1 + 6]).toContain('syncActive')
    expect(SYNC.lines[PERSIST.line - 1].trim()).toBe('persist()')
    expect(R293).not.toMatch(/ChatPanel\.vue:767/)
    expect(R293).not.toMatch(/:702 flushScroll/)
    expect(R293).not.toMatch(/lib\/sessions\.js:159/)
  })

  it('r293:35 声称 ChatPanel.vue:' + QUEUED.line + ' 对 :' + LOAD.line + '-' + PULL.line + ' —— 先后顺序也得真成立；旧值 743 / 748-755 已从这一句退场', () => {
    expect(R293).toContain('（ChatPanel.vue:' + QUEUED.line + ' 对 :' + LOAD.line + '-' + PULL.line + '）→ 刷新那一轮')
    expect(MOUNTED.text).toBe('onMounted(() => {')
    expect(QUEUED.text).toBe('restoreQueuedTurns()')
    expect(LOAD.text).toBe('const storedActive = loadSessions()')
    expect(PULL.text).toBe('if (!messages.value.length && !linked) restoreActive(activeId.value)')
    expect(QUEUED.line).toBeGreaterThan(MOUNTED.line)
    expect(QUEUED.line).toBeLessThan(LOAD.line)
    expect(LOAD.line).toBeLessThan(PULL.line)
    expect(R293).not.toMatch(/ChatPanel\.vue:743 对/)
    expect(R293).not.toMatch(/:748-755/)
  })

  it('r293:46 声称 :' + QF.line + ' 的 queueFace(msg.queue) —— 它就在 !read 那一支里、守卫（:' + GUARD.line + '）之后；旧值 1317 在这一句里已 0 命中', () => {
    expect(R293).toContain('走 :' + QF.line + ' 的 queueFace(msg.queue)，本来就没经过面板自持那一份')
    expect(QF.text).toBe('face = msg.queue ? queueFace(msg.queue) : null')
    expect(QF.line).toBeGreaterThan(GUARD.line)
    expect(QF.lines[QF.line - 1 - 5].trim()).toBe('} else if (!read) {')
    expect(R293).not.toMatch(/走 :1317 的 queueFace/)
  })

  it('反向自证：五处引用都还在原位——把它们删掉躲检查同样算红', () => {
    expect(R197).toMatch(/restoreActive\(\) 那样整份换掉 messages\.value（sessions\.js:\d+）/)
    expect(R210).toMatch(/``frontend\/src\/lib\/sessions\.js:\d+`` 的\*\*追加\*\*分支/)
    expect(R293).toMatch(/掩盖它的是这条通道：ChatPanel\.vue:\d+ onUnmounted -> :\d+ flushScroll -> lib\/sessions\.js:\d+/)
    expect(R293).toMatch(/（ChatPanel\.vue:\d+ 对 :\d+-\d+）→ 刷新那一轮/)
    expect(R293).toMatch(/走 :\d+ 的 queueFace\(msg\.queue\)/)
  })

  it('旧值今天确实指着别处（本单不是猜的；而且只断「那一行不是它声称的那一格」，不断「那一行具体是什么」——后者会被下一笔并树的形态改动打成假红，本组今天就是被 :743 与 :1317 那两枚具体字面量绊倒的）：814 仍是空行、:767 不是 onUnmounted、:702 不是 flushScroll、:743 不是 restoreQueuedTurns、:1317 不是 queueFace 那一腿', () => {
    expect(headLines(SESSIONS)[813].trim(), 'sessions.js:814 今天不再是空行：那枚旧坐标已经换了事').toBe('')
    expect(headLines(CHAT)[766]).not.toMatch(/onUnmounted/)
    expect(headLines(CHAT)[701]).not.toMatch(/flushScroll/)
    expect(headLines(CHAT)[742], 'ChatPanel.vue:743 今天又指着 restoreQueuedTurns 了：那枚旧坐标已经换了事').not.toMatch(/restoreQueuedTurns\(\)/)
    expect(headLines(CHAT)[747]).not.toMatch(/loadSessions\(\)/)
    expect(headLines(CHAT)[754]).not.toMatch(/restoreActive\(/)
    expect(headLines(CHAT)[1316], 'ChatPanel.vue:1317 今天又指着 queueFace 了：那枚旧坐标已经换了事').not.toMatch(/queueFace\(msg\.queue\)/)
  })
})
