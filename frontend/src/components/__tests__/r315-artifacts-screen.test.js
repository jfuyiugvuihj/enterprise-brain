/**
 * R315 · 「交成果」归位：一枚早就在树里的组件拿到自己的位置，而它自己一个字节都没被改
 *
 * 这枚文件量的五件事，各有各自的出处（判据编号沿用总控派工）：
 *  ② 🔴 ArtifactList.vue 对本基点 dc47119（R509 并树那一笔，授权动它的单号写在下面）零改动 —— 锚点按记名提交现算，不就地重录今天的值；
 *     壳也不许「顺手」给它加 prop：挂载那一枚标签必须仍然不带任何属性。
 *  ③ 🔴 不许把它从 DataPanel.vue 摘掉：数据那一屏继续有它，两屏共用一枚组件 = 同一份账。
 *  ⑤ 🔴 壳不许长出第二本账 —— 尺子写成形状判据（扫壳源码，命中即红）。理由照 R316 判据③：
 *     数出来的「这一页几件」会被读成全集，而分页与全集只有 ArtifactList 自己知道。
 *  ⑥ 六枚一级屏真的可达：路由表派生出它、按角色派生入口带上它、深链 /artifacts 真渲染出壳、
 *     老屏名那一族没被当成新屏重复登记；App.vue 不需要为本单改一个字。
 *  ⑦ 预算：零新色值、零裸 <button>（用 r288 那枚量具现数，不另写一份数法）、零外部 URL、
 *     零 localStorage、零自造句子（壳不 import 错误字典，也就新增不出一句错误文案）。
 *
 * 环境仍是 node + @vue/server-renderer（本仓没有 jsdom / @vue/test-utils，也不许 npm i）：
 * 渲染腿出的是真 HTML，接线腿钉的是源码形状，两条各量各的，谁都不假装验过自己验不了的那一半。
 *
 * 反证刀（跑完按 sha256 复原，不留在树里）：
 *   刀1 摘掉 /artifacts 那条路由 → 本文件的深链与导航派生两条当场红（routes.test.js 另有一组）。
 *   刀2 让壳自己 api.get('/artifacts') 拉一遍 → 判据⑤ 那把尺子红。
 *   刀3 navigation 里少一枚 → 判据④ 的定长钉红；它若不红就是钉写成了包含式。
 *   刀4 给 ArtifactList.vue 加一个空格 → 判据② 两枚红（numstat 与 sha256）。
 *   刀5 把 <ArtifactList /> 从 DataPanel.vue 摘掉 → 判据③ 红。
 */
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { renderToString } from '@vue/server-renderer'

import ArtifactsPanel from '../ArtifactsPanel.vue'
import { countNativeButtons } from './r288-native-button-scan.js'
import { LEGACY_FEED_NAMES } from '../../router/feed-tabs.js'
import {
  ADMINISTRATOR_ROLE,
  createAppRouter,
  navigation,
  navigationForRole,
  routes,
  screenIds,
  screenRouteIds,
} from '../../router/index.js'

/** 本单基点：总控派工指定的那一枚提交。判据② 的锚记的是这个名字，不是抄下来的 sha。 */
const BASE_COMMIT = 'dc47119'
const ARTIFACT_LIST_REL = 'frontend/src/components/ArtifactList.vue'
const DATA_PANEL_REL = 'frontend/src/components/DataPanel.vue'

// 本件在 src/components/__tests__/ 下，退四级到仓库根，git 命令一律在那里跑。
const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..')

function git(args) {
  try {
    return execFileSync('git', args, { cwd: REPO_ROOT, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  } catch (cause) {
    throw new Error('git ' + args.join(' ') + ' 失败：' + cause.message + '。零改动这条判据不许降级成 skip。')
  }
}

/** 取锚点上的 blob 原物（Buffer）；读不到就抛红，不静默放行。 */
function blobAt(anchor, relPath) {
  try {
    return execFileSync('git', ['show', anchor + ':' + relPath], { cwd: REPO_ROOT, maxBuffer: 64 * 1024 * 1024 })
  } catch (cause) {
    throw new Error('读不到 ' + anchor + ':' + relPath + '（git show 失败：' + cause.message + '）')
  }
}

/** 换行符归一：本仓 core.autocrlf=true ⇒ 锚点存 LF、工作树 CRLF，其余字节逐位比。 */
const toLf = text => text.replace(/\r\n/g, '\n')
const shaOf = buffer => createHash('sha256').update(buffer).digest('hex')

/**
 * 判据②③ 的尺子：派生 + 记名锚点 + 漂移自校。
 * 对锚点 numstat 为空才算零改动；不空时先分清「谁改的」再报错：
 *   · 差异来自已提交（锚点之后有单子动过它）→ 报错里点名那些提交，要求把锚点推进并写明授权 ——
 *     🔴 不许就地重录内容或 sha，那正是看板 §4CX.2 那一族「手抄账腐烂」的复发写法；
 *   · 差异来自未提交的工作树 → 本单越界，直接红。
 */
function expectZeroDrift(relPath, rule) {
  const numstat = git(['diff', '--numstat', BASE_COMMIT, '--', relPath]).trim()
  if (numstat) {
    const since = git(['log', '--format=%h %s', BASE_COMMIT + '..HEAD', '--', relPath]).trim()
    throw new Error(since
      ? relPath + ' 与锚点 ' + BASE_COMMIT + ' 对不上，差异来自这些已提交的单：\n' + since
        + '\n把 BASE_COMMIT 推进到最后一枚并写明哪一单授权动了它；就地重录内容或 sha 等于把同一枚雷再埋一遍。'
      : relPath + ' 在工作树里被改了（还没提交）：\n' + numstat + '\n' + rule)
  }
  expect(numstat, relPath + ' 对基点的 numstat 应为空').toBe('')
}

const readSrc = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const shellSource = () => readSrc('../ArtifactsPanel.vue')
const dataPanelSource = () => readSrc('../DataPanel.vue')
const appSource = () => readSrc('../../App.vue')

/** 剥掉不画上屏的注释：模板注释、块注释、行注释（口径同 r136 / r316 那两枚 helper）。 */
function withoutComments(text) {
  return text
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[\s;:{}])\/\/[^\n]*/g, '$1')
}
const shellCode = () => withoutComments(shellSource())

/** 页级屏名的全站唯一画法：header.panel-head 里第一枚 <h3>（与 R136 判据① 同一条口径）。 */
const PAGE_TITLE_RE = /<header\b[^>]*class="[^"]*\bpanel-head\b[^"]*"[^>]*>[\s\S]*?<h3\b[^>]*>([^<]*)<\/h3>/

const artifactsRoute = routes.find(route => route.name === 'artifacts')
const navIds = navigation.map(item => item.id)

async function routerAt(location) {
  const router = createAppRouter({ history: createMemoryHistory() })
  await router.push(location)
  return router
}

/** 渲染时收集 Vue 的告警：盲区（Failed to resolve component）必须现抓，不许靠「用例绿了」。 */
async function renderCapturingWarnings(component) {
  const lines = []
  const originalWarn = console.warn
  const originalError = console.error
  console.warn = (...args) => lines.push(args.join(' '))
  console.error = (...args) => lines.push(args.join(' '))
  try {
    return { html: await renderToString(h(component)), warnings: lines }
  } finally {
    console.warn = originalWarn
    console.error = originalError
  }
}


/** 一枚 Buffer 里没跟上 CR 的换行数（本仓工作树惯例是 CRLF）。 */
function loneLineFeeds(buffer) {
  let lone = 0
  for (let i = 0; i < buffer.length; i += 1) {
    if (buffer[i] === 0x0a && (i === 0 || buffer[i - 1] !== 0x0d)) lone += 1
  }
  return lone
}

/** src/components 下真的挂载了 <ArtifactList …> 的文件名（剥注释，防「注释里提一嘴」也算挂载）。 */
function artifactListMountSites() {
  const dir = new URL('../', import.meta.url)
  return readdirSync(dir)
    .filter(name => name.endsWith('.vue'))
    .filter(name => /<ArtifactList\b/.test(withoutComments(readFileSync(new URL(name, dir), 'utf8').replace(/\r\n/g, '\n'))))
    .sort()
}

describe('R315 判据① · /artifacts 是一屏，写法逐字照 /admin 那枚先例', () => {
  it('路由表里恰好一条 /artifacts：字面 path、字面 name、meta.screen、屏名「交成果」、图标现成', () => {
    expect(artifactsRoute, '路由表里没有「交成果」这一屏了').toBeTruthy()
    expect(routes.filter(route => route.name === 'artifacts')).toHaveLength(1)
    expect(routes.filter(route => route.path === '/artifacts')).toHaveLength(1)
    expect(artifactsRoute.path).toBe('/artifacts')
    expect(artifactsRoute.component, '/artifacts 挂的不是那枚壳').toBe(ArtifactsPanel)
    expect(artifactsRoute.meta.screen).toBe(true)
    expect(artifactsRoute.meta.title).toBe('交成果')
    expect(artifactsRoute.meta.icon).toMatch(/^M/)
  })

  it('不自造第三种形状：写法与 /admin 同为「字面 path + 字面 name + 组件 + meta」，且不写 primary / administratorOnly', () => {
    const source = readSrc('../../router/index.js')
    expect(source).toMatch(/path: '\/artifacts',\n\s*name: 'artifacts',\n\s*component: ArtifactsPanel,/)
    // 先例本身也钉一次：下一位要是把 /admin 那格换了写法，这两条一起红，说明尺子该跟着改口
    expect(source).toMatch(/path: '\/admin',\n\s*name: 'admin',\n\s*component: AdminPanel,/)
    // 这一屏对所有人都派生入口 ⇒ 走默认一级（不写 primary:false），也不是管理员独占屏
    expect(artifactsRoute.meta.primary, '这一屏被写成了非一级').toBeUndefined()
    expect(artifactsRoute.meta.administratorOnly, '这一屏被误登记成管理员独占').toBeUndefined()
  })

  it('壳就是给那枚组件一个页面位置：挂载恰一枚，而且不带任何 prop（判据② 的「顺手加 prop」这一刀）', () => {
    const mounts = shellCode().match(/<ArtifactList\b[^>]*>/g) || []
    expect(mounts, '壳里的挂载点不是恰好一枚').toHaveLength(1)
    expect(mounts[0], '挂载那枚标签被加了属性：壳不许给 ArtifactList 加 prop / ref / 事件').toBe('<ArtifactList />')
    expect(shellCode()).not.toMatch(/defineProps|defineEmits|\bprops\b|\bemit\(/)
  })

  it('页级屏名只有这一枚，且逐字等于 meta.title（屏名真源仍然只在路由表那一格）', () => {
    const code = shellCode()
    expect(code.match(/<h3\b/g) || [], '壳里的页级屏名不止一句').toHaveLength(1)
    const head = PAGE_TITLE_RE.exec(code)
    expect(head, '壳的屏名没写在 header.panel-head 的 <h3> 里（全站唯一画法）').toBeTruthy()
    expect(head[1].trim(), '页内那句与 meta.title 不是一份字').toBe(artifactsRoute.meta.title)
  })
})

describe('R315 判据② · ArtifactList.vue 一个字节都没被改', () => {
  it('锚点提交解析得到，而且就在本工作树的历史里（锚断了必须红，不许 skip 成装饰）', () => {
    expect(git(['rev-parse', '--verify', BASE_COMMIT + '^{commit}']).trim()).toMatch(/^[0-9a-f]{40}$/)
    let inside = true
    try {
      git(['merge-base', '--is-ancestor', BASE_COMMIT, 'HEAD'])
    } catch {
      inside = false
    }
    expect(inside, '锚点 ' + BASE_COMMIT + ' 不在 HEAD 的历史里，这把尺子得换地方立').toBe(true)
  })

  it('对基点的 numstat 为空：改它一个字节就红，包括还没提交的那一半', () => {
    expectZeroDrift(
      ARTIFACT_LIST_REL,
      '判据②：ArtifactList.vue 本单一个字节都不许改（分页、删除、重试、四张脸都在它自己手里）。',
    )
  })

  it('逐字节对账：工作树与锚点 blob 归一换行后同一份 sha256（现算，不比抄下来的常量）', () => {
    const anchorSha = shaOf(Buffer.from(toLf(blobAt(BASE_COMMIT, ARTIFACT_LIST_REL).toString('utf8')), 'utf8'))
    const worktreeSha = shaOf(Buffer.from(toLf(readFileSync(join(REPO_ROOT, ARTIFACT_LIST_REL)).toString('utf8')), 'utf8'))
    expect(worktreeSha, '工作树里那份与锚点 ' + BASE_COMMIT + ' 不是同一份字节').toBe(anchorSha)
  })

  it('工作树里那一份仍是纯 CRLF（本仓 autocrlf=true，锚点存 LF；交上来纯 LF 是给总控添归一化的活）', () => {
    const bytes = readFileSync(join(REPO_ROOT, ARTIFACT_LIST_REL))
    expect(loneLineFeeds(bytes), 'ArtifactList.vue 里出现了没跟上 CR 的换行').toBe(0)
    expect(bytes.length).toBeGreaterThan(0)
  })
})

describe('R315 判据③ · 也没把它从「喂料 → 数据」那一屏摘掉', () => {
  it('DataPanel.vue 继续挂着它：挂载恰一枚，摘掉即红（刀5）', () => {
    const mounts = withoutComments(dataPanelSource()).match(/<ArtifactList\b[^>]*>/g) || []
    expect(mounts, '「数据」那一屏没有分析产物了：员工会从正在用的地方找不到东西').toHaveLength(1)
    expect(mounts[0]).toBe('<ArtifactList />')
  })

  it('全仓挂载点恰好这两处：同一份账两屏共用，第三处得先写明理由再改这条', () => {
    expect(artifactListMountSites()).toEqual(['ArtifactsPanel.vue', 'DataPanel.vue'])
  })
})

describe('R315 判据⑤ · 壳不许长出第二本账（尺子是形状判据）', () => {
  it('壳不取数：取数出口一枚都没有，import 也只认识 ArtifactList', () => {
    const code = shellCode()
    for (const banned of ['api.get', 'http.get', 'http.post', 'http.request', 'http.delete', 'authedFetch', 'fetchArtifactBlob', 'fetch(', 'axios', 'lib/http', 'lib/artifacts', 'lib/users', 'lib/dashboard', 'onMounted', 'onUnmounted', 'watch(']) {
      expect(code, '壳里出现了取数出口：' + banned).not.toContain(banned)
    }
    expect(code.match(/\.get\(/g) || [], '壳里还有别的 .get(').toHaveLength(0)
    const imports = [...code.matchAll(/^import\b[^\n]*from\s+'([^']+)'/gm)].map(line => line[1])
    expect(imports, '壳的 import 名单变了：它只该认识 ArtifactList 这一枚').toEqual(['./ArtifactList.vue'])
  })

  it('壳不数账：不数条数、不判分页到底、一个动态值都不画上屏', () => {
    const code = shellCode()
    for (const banned of ['.length', 'total', 'hasMore', 'has_more', 'offset', 'limit', 'ARTIFACT_PAGE_SIZE', 'reduce(', 'filter(', 'count', 'size']) {
      expect(code, '壳里自己数了：' + banned + ' —— 数出来的「这一页几件」会被读成全集').not.toContain(banned)
    }
    // 更硬的一条：壳里一个插值都没有。统计量没有落脚点，「顺手做个头部计数」就无处下笔。
    expect(code.match(/\{\{[\s\S]*?\}\}/g) || [], '壳里画出了动态值').toHaveLength(0)
    expect(code.match(/共\s*\d*\s*[枚项件]|合计|总数/g) || [], '壳里出现了自算的总数').toHaveLength(0)
  })
})

describe('R315 判据⑦ · 预算：色值 / 按钮 / URL / 存储 / 句子', () => {
  it('零新色值：壳不带 <style>，也不写 hex / rgb / var(--…) —— 排版全部走 theme.css 既有类', () => {
    const code = shellCode()
    expect(code).not.toContain('<style')
    expect(code).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(code).not.toMatch(/\brgba?\(|\bhsla?\(|\bvar\(--/)
  })

  it('零外部 URL、零本地存储：连注释都不许带（私有化部署，数据不出这台机器）', () => {
    const source = shellSource()
    expect(source).not.toMatch(/https?:\/\/|\bwww\./i)
    expect(source).not.toMatch(/localStorage|sessionStorage|document\.cookie/)
  })

  it('零自造句子：壳不 import 错误字典，也就不新增不出一句错误文案；屏上也不许夹码名', () => {
    const code = shellCode()
    expect(code).not.toMatch(/errcodes|errorText|normalizeError|codes\[/)
    expect(code.match(/\b[a-z][a-z0-9]*(_[a-z0-9]+)+/g) || [], '壳的正文里夹了 snake_case 码名').toEqual([])
  })

  it('零裸 <button>：用 r288 那枚量具现数，不另写一份数法', () => {
    expect(countNativeButtons(shellSource())).toBe(0)
  })
})

describe('R315 判据⑥ · 六枚一级屏真的可达', () => {
  it('一级入口从路由表派生出这六枚，最后一枚就是它（定长逐字相等，刀3 撞这一条）', () => {
    expect(navIds).toEqual(['overview', 'feed', 'insights', 'approval', 'chat', 'artifacts'])
    expect(screenIds).toEqual(navIds)
    expect(navigation[navigation.length - 1]).toEqual({ id: 'artifacts', label: '交成果', icon: artifactsRoute.meta.icon })
  })

  // R399 往「管理员那一档」再加一枚入口（运行留痕）：换的是名单本身，不是断言强度 —— 其余角色
  // 那六枚仍然定长逐字相等，管理员那一档仍然逐字相等且只多管理员屏那一族，没换成包含式。
  // R505 再往同一档加三枚（服务等级目标 / 评测报告 / 审计事件）：走的还是上面那条先例 ——
  // 加长的是名单本身，断言一字不降（仍是定长逐字相等 + 定长计数 + 逐枚 not.toContain），
  // 没有一枚换成包含式；非管理员那一档仍然一枚管理员屏都拿不到。
  const ADMIN_ONLY_SCREEN_IDS = ['admin', 'traces', 'slo', 'evaluations', 'audit-events']
  it('按角色派生入口那把尺子带上它：其余角色就这六枚，管理员那一档只多管理员屏那一族', () => {
    for (const role of ['staff', 'manager', 'auditor', 'editor', '', undefined, null]) {
      expect(navigationForRole(role).map(item => item.id), '角色 ' + String(role) + ' 看到的入口不是这六枚').toEqual(['overview', 'feed', 'insights', 'approval', 'chat', 'artifacts'])
    }
    const forAdmin = navigationForRole(ADMINISTRATOR_ROLE)
    expect(forAdmin.map(item => item.id)).toEqual([...(['overview', 'feed', 'insights', 'approval', 'chat', 'artifacts']), ...ADMIN_ONLY_SCREEN_IDS])
    expect(forAdmin).toHaveLength(navIds.length + ADMIN_ONLY_SCREEN_IDS.length)
    const staffIds = navigationForRole('staff').map(item => item.id)
    for (const adminOnlyId of ADMIN_ONLY_SCREEN_IDS) {
      expect(staffIds, '员工侧栏长出了管理员屏入口：' + adminOnlyId).not.toContain(adminOnlyId)
    }
  })

  it('深链 /artifacts 直接进能渲染：解析到这一屏，HTML 与直接渲染那枚壳逐字相同', async () => {
    const router = await routerAt('/artifacts')
    expect(router.currentRoute.value.name, '/artifacts 没落在这一屏上（多半是掉进了通配兜底）').toBe('artifacts')
    const resolved = router.resolve('/artifacts')
    const last = resolved.matched[resolved.matched.length - 1]
    expect(last.components.default, '/artifacts 挂的不是那枚壳').toBe(ArtifactsPanel)
    expect(resolved.meta.title).toBe('交成果')
    const viaRoute = await renderToString(h(last.components.default))
    expect(viaRoute.length).toBeGreaterThan(50)
    expect(viaRoute).toBe(await renderToString(h(ArtifactsPanel)))
  })

  it('挂载不是假的：渲染时没有一句 Failed to resolve component，ArtifactList 真上了屏', async () => {
    const { html, warnings } = await renderCapturingWarnings(ArtifactsPanel)
    expect(warnings.filter(line => /Failed to resolve component/.test(line)), '组件没解析就画了个空标签 —— 这是盲区假绿').toEqual([])
    expect(html).toContain('data-testid="artifact-list"')
    expect(html).not.toMatch(/<artifactlist[\s>]/i)
    expect(html).toContain('分析产物')
    const head = PAGE_TITLE_RE.exec(html)
    expect(head, '渲染产物里没有 panel-head 的 <h3>').toBeTruthy()
    expect(head[1].trim()).toBe(artifactsRoute.meta.title)
  })

  it('老屏名那一族没被当成新屏重复登记：docs / data 仍是入口不是屏，非一级的定长名单一枚未增', () => {
    expect(LEGACY_FEED_NAMES).toEqual(['docs', 'data'])
    expect(LEGACY_FEED_NAMES).not.toContain('artifacts')
    expect(routes.filter(route => route.meta?.screen && LEGACY_FEED_NAMES.includes(String(route.name)))).toHaveLength(0)
    // 屏的全集里，非一级的只有图谱、「账号与角色」、R399 的「运行留痕」与 R505 的三枚管理员屏，
    // 再加上那两枚老屏名 —— 定长逐字相等，多一枚少一枚都红。
    expect(screenRouteIds.filter(id => !screenIds.includes(id))).toEqual(['profile', 'graph', 'admin', 'traces', 'slo', 'evaluations', 'audit-events', 'docs', 'data'])
    expect(artifactsRoute.redirect, '「交成果」不该是重定向，它是一屏').toBeUndefined()
  })

  it('App.vue 不为第六枚入口改一个字：侧栏仍只从 navigationForRole 派生，壳层没手写入口', () => {
    const app = appSource()
    expect(app).toMatch(/import \{[^}]*\bnavigationForRole\b[^}]*\} from '\.\/router'/)
    const loops = app.match(/v-for="item in [^"]*"/g) || []
    expect(loops, '侧栏入口清单换了画法就得先改量具，不许放过第二处清单').toHaveLength(1)
    expect(loops[0]).toBe('v-for="item in navigationForRole(userRole)"')
    // 第六枚入口是派生出来的：壳层要是把它的 data-testid 写死，就有了第二套真源
    expect(app).not.toContain('nav-artifacts')
    expect(app).not.toMatch(/const navigation = \[/)
  })
})

describe('R315 交付卫生 · 换行符', () => {
  it('本单写过的每一枚文件都是纯 CRLF（本仓工作树惯例，autocrlf=true）', () => {
    // 上一班就有单子交上来是纯 LF，总控入库前手工归一化。这条钉把它拦在门外：
    // 只数「没跟上 CR 的换行」，混着写与整份 LF 两种走法都红。
    const delivered = [
      'frontend/src/components/ArtifactsPanel.vue',
      'frontend/src/components/__tests__/r315-artifacts-screen.test.js',
      'frontend/src/router/index.js',
      'frontend/src/router/__tests__/routes.test.js',
      'frontend/src/router/__tests__/r136-screen-names.test.js',
      'frontend/src/router/__tests__/r136-feed-merge.test.js',
      'frontend/src/__tests__/navigation.test.js',
    ]
    for (const rel of delivered) {
      const bytes = readFileSync(join(REPO_ROOT, rel))
      expect(bytes.length, rel + ' 读不到或是空文件').toBeGreaterThan(0)
      expect(loneLineFeeds(bytes), rel + ' 里有纯 LF 换行').toBe(0)
    }
  })
})

