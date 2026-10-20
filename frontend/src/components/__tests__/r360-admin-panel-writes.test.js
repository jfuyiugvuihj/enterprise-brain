/**
 * R360 判据甲·乙·丙·丁·戊·己·庚 · 「账号与角色」屏壳的写路径真渲染钉
 *
 * 手法照 r316-admin-panel.test.js：环境仍是 node + @vue/server-renderer（仓里没有 jsdom），
 * 只 mock lib/http.js 那一枚共享 axios 实例，先真跑取数与写入，再把同一份 bindings 渲染成
 * 真 HTML。于是这里量的是屏上真的画出了什么、真的发出去了哪几发，不是源码里长得像那么回事。
 *
 * 辛那五把刀里属于本件的四把，各自钉在这里：
 *   ① 摘掉「写完重读」→ 「写完必须再发那一枚 GET」与「对表那一句话说的是重读的结果」当场红；
 *   ② 把 403 画成空名册 → 「写失败那张脸说的是不向你开放」与「同一屏同时留着名册那几行」红；
 *   ③ 删掉确认步 → 「打开删除对话框那一刻一枚 DELETE 都没发」红（发了就立刻红，不用等下一步）；
 *   ⑤ 少注册一枚原语 → 渲染产物里数不到 class="ui-button"，或数出 <uidialog> 这种未知标签，红。
 * 每把跑完按 sha256 复原，红数记在收工回执里。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { errorText } from '../../lib/errcodes'
import {
  USER_COLUMNS,
  USERS_CONFLICT_TITLE,
  USERS_DENIED_TITLE,
  USERS_DENIED_WHERE,
  USERS_EMPTY_TITLE,
  USERS_INVALID_TITLE,
  USERS_NOT_FOUND_TITLE,
  USERS_PATH,
  USERS_STORAGE_TITLE,
  USERS_UNADDRESSABLE_TITLE,
  USERS_UNAUTHORIZED_TITLE,
  USER_CREATE_PATH,
  USER_WRITE_CREATE,
  USER_WRITE_DELETE,
  USER_WRITE_DEPARTMENT,
  USER_WRITE_PASSWORD,
  USER_DEPARTMENT_PATH,
  USER_PASSWORD_PATH,
} from '../../lib/users'
import { countNativeButtons } from './r288-native-button-scan.js'
import { findNativeDialogs } from './r288-native-dialog-scan.js'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }
})

import { http } from '../../lib/http'
import AdminPanel from '../AdminPanel.vue'

const source = () => readFileSync(new URL('../AdminPanel.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
/**
 * 屏壳的 @click 接线表 —— 辛③那把刀改的就是这一格，所以这里必须有它专职的那枚钉子。
 *
 * 取证口径先说清：仓里没有 jsdom，也没有 @vue/test-utils，而 vitest 里编译出来的 SFC
 * 只有 ssrRender（没有客户端 render），SSR 又不序列化事件监听。于是「这颗钮点下去走到
 * 哪一步」在这一件里只能从模板的绑定表取证，不能靠真点击。为了让它只会红、不会假绿，
 * 这里上了两道保险：
 *   一、解析出来的 @click 枚数必须等于源码里的枚数 —— 漏解析一枚就红，绝不沉默放行；
 *   二、断言全写成禁止式：动作条那几枚只准绑 openDialog(...)，提交函数只准长在
 *       它对应的那一枚 UiDialog 里面。谁绕过确认步，这两条里至少一条当场红。
 */
function clickTags(text) {
  const found = []
  const tagRe = /<([A-Za-z][\w.-]*)((?:"[^"]*"|'[^']*'|[^<>"'])*)>/g
  let match
  while ((match = tagRe.exec(text)) !== null) {
    const click = /(?:^|\s)@click(?:\.[a-z]+)*="([^"]*)"/.exec(match[2])
    if (!click) continue
    const testid = /(?:^|\s)data-testid="([^"]*)"/.exec(match[2])
    found.push({ tag: match[1], testid: testid ? testid[1] : '', click: click[1], index: match.index })
  }
  return found
}

const clickMap = text => Object.fromEntries(clickTags(text).filter(item => item.testid).map(item => [item.testid, item.click]))

/** 一枚 UiDialog 从开标签到它自己那一枚闭合的源码区间：四枚互不嵌套，所以第一个闭合就是它自己的。 */
function dialogRange(text, model) {
  const open = new RegExp('<UiDialog[^>]*v-model="' + model + '"').exec(text)
  if (!open) throw new Error('模板里找不到 ' + model + ' 那一枚 UiDialog')
  const close = text.indexOf('</UiDialog>', open.index)
  if (close < 0) throw new Error(model + ' 那一枚 UiDialog 没有闭合')
  return [open.index, close]
}

function row(overrides = {}) {
  return { id: 7, username: 'baiye', role: 'admin', department: 'finance', created_at: '2026-09-01T10:00:00+08:00', ...overrides }
}

const ok = (rows) => ({ status: 200, data: { users: rows } })
const accepted = (extra = {}) => ({ status: 200, data: { status: 'ok', ...extra } })
const failure = (code, detail) => ({ response: { status: code, data: { detail } }, status: code })

/**
 * 路由表：读那一枚 GET 永远答名册，写按 verb 答 reply（reply 是一枚 failure() 时就抛，
 * 与 axios 真行为一致）。calls 是全量流水，「写完又读了没有」「确认之前发没发」都读它。
 */
function stubRoutes({ roster = [row()], reply = accepted() } = {}) {
  const calls = []
  let reads = 0
  http.get.mockImplementation(async (url) => {
    if (url !== USERS_PATH) throw new Error(`这一屏只该读那一条路径，收到 ${url}`)
    calls.push(['get', url])
    reads += 1
    return ok(typeof roster === 'function' ? roster() : roster)
  })
  for (const verb of ['post', 'put', 'delete']) {
    http[verb].mockImplementation(async (url, body) => {
      calls.push([verb, url, body])
      if (reply && reply.status && reply.response) throw reply
      return reply
    })
  }
  return { calls, readCount: () => reads }
}

async function mountedPanel() {
  let bindings = null
  const Host = {
    name: 'R360Probe',
    setup(props, ctx) {
      bindings = AdminPanel.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Host))
  return bindings
}

const render = bindings => renderToString(h({ ...AdminPanel, setup: () => bindings }))

/** SSR 会把引号与尖括号转义：要比对后端原话就得先解回来（比对的是屏上真画出来的那几个字）。 */
const unescape = text => text
  .replace(/&#39;/g, "'")
  .replace(/&quot;/g, '"')
  .replace(/&lt;/g, '<')
  .replace(/&gt;/g, '>')
  .replace(/&amp;/g, '&')

const visibleText = html => html
  .replace(/<!--[\s\S]*?-->/g, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()

const buttonLabels = html => [...html.matchAll(/<span class="ui-button__label">([\s\S]*?)<\/span>/g)]
  .map(match => match[1].replace(/<[^>]+>/g, '').trim())

const cellTexts = html => [...html.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)]
  .map(match => match[1].replace(/<[^>]+>/g, '').replace(/<!--[\s\S]*?-->/g, '').replace(/\s+/g, ' ').trim())

const flush = async () => {
  for (let i = 0; i < 8; i += 1) await Promise.resolve()
  await new Promise(resolve => setTimeout(resolve, 0))
}

/** 装好路由、真读一次、把屏渲染出来：所有写路径的用例都从这块屏出发。 */
async function readyPanel(options = {}) {
  const stub = stubRoutes(options)
  const bindings = await mountedPanel()
  await bindings.loadRoster()
  await flush()
  return { bindings, stub, html: await render(bindings) }
}

/** 选一名操作对象：屏上的写动作全部落在这枚账号上（选项只可能来自名册那几行）。 */
async function pickTarget(bindings, username = 'baiye') {
  bindings.targetName.value = username
  await flush()
}

beforeEach(() => {
  for (const verb of ['get', 'post', 'put', 'delete']) http[verb].mockReset()
})

describe('R360甲 · 四枚出口逐枚接通，每一枚只发自己那一枚', () => {
  it('开通账号 = POST /users：请求体就是后端 CreateUserRequest 那四格，别一枚都不许多发', async () => {
    const { bindings, stub } = await readyPanel()
    bindings.openDialog(USER_WRITE_CREATE)
    bindings.form.username = 'newbie'
    bindings.form.password = 'secret6'
    bindings.form.role = 'staff'
    bindings.form.department = 'finance'
    await bindings.submitCreate()
    await flush()
    expect(stub.calls.filter(call => call[0] === 'post')).toEqual([
      ['post', USER_CREATE_PATH, { username: 'newbie', password: 'secret6', role: 'staff', department: 'finance' }],
    ])
    expect(stub.calls.filter(call => call[0] === 'put')).toEqual([])
    expect(stub.calls.filter(call => call[0] === 'delete')).toEqual([])
  })

  it('改密码 = PUT /users/password：三格键名逐字等于后端模型，且这一屏没有「跳过现由密码」的那一枚按钮', async () => {
    const { bindings, stub } = await readyPanel()
    await pickTarget(bindings)
    bindings.openDialog(USER_WRITE_PASSWORD)
    bindings.form.oldPassword = 'old666'
    bindings.form.newPassword = 'fresh99'
    await bindings.submitPassword()
    await flush()
    expect(stub.calls.filter(call => call[0] === 'put')).toEqual([
      ['put', USER_PASSWORD_PATH, { username: 'baiye', old_password: 'old666', new_password: 'fresh99' }],
    ])
    const html = await render(bindings)
    for (const label of buttonLabels(html)) {
      expect(label).not.toMatch(/重置|跳过|免密/)
    }
  })

  it('调部门 = PUT /users/department：清空也要显式发那一格，不能少发（少发后端读成「这轮没说」）', async () => {
    const first = await readyPanel()
    await pickTarget(first.bindings)
    first.bindings.openDialog(USER_WRITE_DEPARTMENT)
    first.bindings.form.department = 'ops'
    await first.bindings.submitDepartment()
    await flush()
    expect(first.stub.calls.filter(call => call[0] === 'put')).toEqual([
      ['put', USER_DEPARTMENT_PATH, { username: 'baiye', department: 'ops' }],
    ])
    const second = await readyPanel()
    await pickTarget(second.bindings)
    second.bindings.openDialog(USER_WRITE_DEPARTMENT)
    second.bindings.form.department = ''
    await second.bindings.submitDepartment()
    await flush()
    const body = second.stub.calls.find(call => call[0] === 'put')[2]
    expect(Object.keys(body)).toContain('department')
    expect(body.department).toBe('')
  })

  it('删除 = DELETE /users/{编号}：编号取自名册那一行，不是前端数出来的第几行', async () => {
    const { bindings, stub } = await readyPanel({ roster: [row(), row({ id: 12, username: 'chen' })] })
    await pickTarget(bindings, 'chen')
    bindings.openDialog(USER_WRITE_DELETE)
    await bindings.confirmDelete()
    await flush()
    expect(stub.calls.filter(call => call[0] === 'delete').map(call => [call[0], call[1]])).toEqual([['delete', '/users/12']])
  })

  it('名册那一行没编号：界面上就删不了这一枚，一句「没有编号」说清，不发请求也不假称删掉了', async () => {
    const { bindings, stub } = await readyPanel({ roster: [row({ id: null })] })
    await pickTarget(bindings)
    bindings.openDialog(USER_WRITE_DELETE)
    const opened = await render(bindings)
    expect(opened).toContain(USERS_UNADDRESSABLE_TITLE)
    await bindings.confirmDelete()
    await flush()
    expect(stub.calls.filter(call => call[0] === 'delete')).toEqual([])
  })
})

describe('R360乙 · 不乐观：写完一律重读，屏上不留「看着像成功了」的残影', () => {
  it('四枚出口每一枚之后都再发那一枚 GET（辛①：把重读摘掉，这四条一起红）', async () => {
    const runs = [
      async (bindings) => { bindings.openDialog(USER_WRITE_CREATE); bindings.form.username = 'newbie'; bindings.form.password = 'secret6'; bindings.form.role = 'staff'; await bindings.submitCreate() },
      async (bindings) => { await pickTarget(bindings); bindings.openDialog(USER_WRITE_PASSWORD); bindings.form.oldPassword = 'old666'; bindings.form.newPassword = 'fresh99'; await bindings.submitPassword() },
      async (bindings) => { await pickTarget(bindings); bindings.openDialog(USER_WRITE_DEPARTMENT); bindings.form.department = 'ops'; await bindings.submitDepartment() },
      async (bindings) => { await pickTarget(bindings); bindings.openDialog(USER_WRITE_DELETE); await bindings.confirmDelete() },
    ]
    for (const run of runs) {
      const { bindings, stub } = await readyPanel({ reply: accepted({ changed: true }) })
      const before = stub.readCount()
      await run(bindings)
      await flush()
      expect(stub.readCount(), '这一枚出口写完没重读名册').toBe(before + 1)
    }
  })

  it('写失败也一样重读：名册不许停在写之前那一份上', async () => {
    const { bindings, stub } = await readyPanel({ reply: failure(403, 'permission_denied') })
    const before = stub.readCount()
    bindings.openDialog(USER_WRITE_CREATE)
    bindings.form.username = 'newbie'
    bindings.form.password = 'secret6'
    bindings.form.role = 'staff'
    await bindings.submitCreate()
    await flush()
    expect(stub.readCount()).toBe(before + 1)
  })

  it('屏上那几行只可能来自重读的回包：表单里填的那一枚新账号，后端没回就不许出现在表里', async () => {
    const { bindings } = await readyPanel()
    bindings.openDialog(USER_WRITE_CREATE)
    bindings.form.username = 'newbie'
    bindings.form.password = 'secret6'
    bindings.form.role = 'staff'
    await bindings.submitCreate()
    await flush()
    const html = await render(bindings)
    // 这一份 stub 的名册自始至终只有 baiye：后端没回 newbie，屏上就不能有 newbie 那一行
    expect(cellTexts(html)).not.toContain('newbie')
    expect(visibleText(html)).toContain('但重新读回的名册里没有 newbie 这一枚账号')
    expect(html).toContain('admin-users-rows')
  })

  it('对表那一句与回执同时摆着：后端说 200 而名册不支持时，屏上不能只剩「已开通」', async () => {
    const { bindings } = await readyPanel()
    bindings.openDialog(USER_WRITE_CREATE)
    bindings.form.username = 'newbie'
    bindings.form.password = 'secret6'
    bindings.form.role = 'staff'
    await bindings.submitCreate()
    await flush()
    const text = visibleText(await render(bindings))
    expect(text).toContain('账号已开通')
    expect(text).toContain('后端这一发回的是 200')
  })

  it('屏壳里没有本地改那一行的写法：push / splice / 直接赋 rows 一格都不许有（结构钉）', () => {
    const code = source()
      .replace(/<!--[\s\S]*?-->/g, ' ')
      .replace(/\/\*[\s\S]*?\*\//g, ' ')
      .replace(/(^|[\s;:{}])\/\/[^\n]*/g, '$1')
    expect(code).not.toMatch(/rows\.value\.(push|splice|unshift|pop)/)
    expect(code).not.toMatch(/view\.value\.rows\s*=/)
    expect(code).not.toMatch(/\.sort\(\)/)
  })
})

describe('R360丙 · 失败脸逐枚分开、各有出处（辛②的主场）', () => {
  /** 写失败时名册照常答回去：这样屏上同时有「名册那几行」与「这一发没成」两句真话，谁也不顶掉谁。 */
  async function writeFaced(err) {
    const { bindings } = await readyPanel({ reply: err })
    bindings.openDialog(USER_WRITE_CREATE)
    bindings.form.username = 'newbie'
    bindings.form.password = 'secret6'
    bindings.form.role = 'staff'
    await bindings.submitCreate()
    await flush()
    return { bindings, html: await render(bindings) }
  }

  it('403：说的是「这一屏不向你开放」+ 下一步去哪，绝不塌成「名册里没有账号」，也不挂重试', async () => {
    const { html } = await writeFaced(failure(403, 'permission_denied'))
    expect(html).toContain('data-testid="write-failure"')
    expect(html).toContain('data-testid="ui-error-state"')
    expect(html).toContain(USERS_DENIED_TITLE)
    expect(visibleText(html)).toContain(errorText('permission_denied'))
    expect(visibleText(html)).toContain(USERS_DENIED_WHERE)
    // 🔴 这一条就是辛②那把刀：把 403 画成空名册，这里立刻红
    expect(visibleText(html)).not.toContain(USERS_EMPTY_TITLE)
    expect(html).not.toContain('data-testid="admin-users-empty"')
    expect(html).toContain('data-testid="admin-users-rows"')
    expect(html).not.toContain('data-testid="ui-error-retry"')
  })

  it('后端真发的那句散文形状（authorization.py 把 reason code 括在正文里）画的是同一张脸', async () => {
    const { html } = await writeFaced(failure(403, '权限不足: users:manage (permission_denied)'))
    expect(html).toContain(USERS_DENIED_TITLE)
    expect(html).not.toMatch(/permission_denied/)
  })

  it('401 是登录失效，另一句；与 403 与空态都不同名同句', async () => {
    const { html } = await writeFaced(failure(401, 'authentication_required'))
    expect(html).toContain(USERS_UNAUTHORIZED_TITLE)
    expect(html).not.toContain(USERS_DENIED_TITLE)
    expect(visibleText(html)).not.toContain(USERS_EMPTY_TITLE)
  })

  it('409 冲突有它自己的那一张（后端今天发不出这一枚，界面试探到它就照这一张说）', async () => {
    const { html } = await writeFaced(failure(409, 'conflict'))
    expect(html).toContain(USERS_CONFLICT_TITLE)
    expect(html).not.toContain(USERS_DENIED_TITLE)
    expect(html).not.toContain(USERS_EMPTY_TITLE)
  })

  it('404 说的是「这一枚账号找不到」，不是「名册里没有账号」，也不是「没有权限」', async () => {
    const { html } = await writeFaced(failure(404, '用户不存在'))
    expect(html).toContain(USERS_NOT_FOUND_TITLE)
    expect(html).not.toContain(USERS_EMPTY_TITLE)
    expect(html).not.toContain(USERS_DENIED_TITLE)
  })

  it('422 与 400 归「后端没有收下这一发」，而后端那句原话占人话位：重名就说重名', async () => {
    const invalid = await writeFaced(failure(422, [{ loc: ['body', 'username'], msg: 'Field required', type: 'missing' }]))
    expect(invalid.html).toContain(USERS_INVALID_TITLE)
    expect(invalid.html).not.toContain(USERS_EMPTY_TITLE)
    const dup = await writeFaced(failure(400, "用户 'baiye' 已存在"))
    expect(dup.html).toContain(USERS_INVALID_TITLE)
    expect(unescape(visibleText(dup.html))).toContain("用户 'baiye' 已存在")
    expect(dup.html).not.toContain(USERS_CONFLICT_TITLE)
  })

  it('503 存储没就绪：不画成「没有用户」，也不挂重试按钮（errcodes.js:99-107 那三条理由的界面那一半）', async () => {
    const { html } = await writeFaced(failure(503, 'storage_unavailable'))
    expect(html).toContain(USERS_STORAGE_TITLE)
    expect(visibleText(html)).not.toContain(USERS_EMPTY_TITLE)
    expect(html).not.toContain('data-testid="ui-error-retry"')
    expect(visibleText(html)).toContain(errorText('storage_unavailable'))
  })

  it('连不上服务也是独立的一张：说的是这一步没成交，不是名册空了', async () => {
    const { bindings } = await readyPanel({ reply: new Error('Network Error') })
    bindings.openDialog(USER_WRITE_CREATE)
    bindings.form.username = 'newbie'
    bindings.form.password = 'secret6'
    bindings.form.role = 'staff'
    await bindings.submitCreate()
    await flush()
    const text = visibleText(await render(bindings))
    expect(text).toContain('这一步没成交')
    expect(text).not.toContain(USERS_EMPTY_TITLE)
  })

  it('写失败的六张脸两两不同句：把任何两张并成一句，这一条当场红', async () => {
    const seen = []
    for (const err of [
      failure(403, 'permission_denied'),
      failure(401, 'authentication_required'),
      failure(409, 'conflict'),
      failure(404, '用户不存在'),
      failure(400, '原密码错误'),
      failure(503, 'storage_unavailable'),
      new Error('Network Error'),
    ]) {
      const { bindings } = await readyPanel({ reply: err })
      bindings.openDialog(USER_WRITE_CREATE)
      bindings.form.username = 'newbie'
      bindings.form.password = 'secret6'
      bindings.form.role = 'staff'
      await bindings.submitCreate()
      await flush()
      const html = await render(bindings)
      const block = /data-testid="write-failure"[\s\S]*?(?=<\/section>)/.exec(html)
      expect(block, '失败脸压根没画出来').toBeTruthy()
      seen.push(visibleText(block[0]))
    }
    expect(new Set(seen).size, '两张写失败脸被画成了同一句').toBe(seen.length)
  })

  it('预检没过那一发都不发：界面上只说后端真要求的那一句，不多设一道前端自己的门', async () => {
    const { bindings, stub } = await readyPanel()
    bindings.openDialog(USER_WRITE_CREATE)
    bindings.form.username = 'newbie'
    bindings.form.password = '12345'
    bindings.form.role = 'staff'
    await bindings.submitCreate()
    await flush()
    expect(stub.calls.filter(call => call[0] !== 'get')).toEqual([])
    const html = await render(bindings)
    expect(visibleText(html)).toContain('密码至少要 6 位')
    expect(bindings.dlgCreate.value).toBe(true)
  })

  it('后端没规则的字段一律放行：中文账号名带空格也照样发出去，不替它挑字符集', async () => {
    const { bindings, stub } = await readyPanel()
    bindings.openDialog(USER_WRITE_CREATE)
    bindings.form.username = ' 张三 fin '
    bindings.form.password = 'secret6'
    bindings.form.role = 'staff'
    bindings.form.department = '财务 一部'
    await bindings.submitCreate()
    await flush()
    const sent = stub.calls.find(call => call[0] === 'post')[2]
    expect(sent.username).toBe(' 张三 fin ')
    expect(sent.department).toBe('财务 一部')
  })
})

describe('R360丁 · 删除那一步有确认，且确认句点名是谁', () => {
  it('打开删除对话框那一刻一枚 DELETE 都没发；确认之后才发那一枚（辛③）', async () => {
    const { bindings, stub } = await readyPanel()
    await pickTarget(bindings)
    bindings.openDialog(USER_WRITE_DELETE)
    await flush()
    expect(stub.calls.filter(call => call[0] === 'delete')).toEqual([])
    const opened = await render(bindings)
    expect(opened).toContain('data-testid="ui-dialog"')
    expect(visibleText(opened)).toContain('baiye')
    expect(visibleText(opened)).toContain('名册编号 7')
    expect(visibleText(opened)).toContain('不可逆')
    await bindings.confirmDelete()
    await flush()
    expect(stub.calls.filter(call => call[0] === 'delete').map(call => [call[0], call[1]])).toEqual([['delete', '/users/7']])
  })

  it('取消那一枚把对话框收起来，仍然一枚 DELETE 不发', async () => {
    const { bindings, stub } = await readyPanel()
    await pickTarget(bindings)
    bindings.openDialog(USER_WRITE_DELETE)
    bindings.closeDialogs()
    await flush()
    expect(stub.calls.filter(call => call[0] === 'delete')).toEqual([])
    expect(bindings.dlgDelete.value).toBe(false)
  })

  it('零枚原生对话框调用点（R288 那枚量具现数）：屏壳里 confirm / alert / prompt 命中数必须是 0', () => {
    expect(findNativeDialogs(source())).toEqual([])
  })

  it('遮罩与焦点归 UiDialog：屏壳不自造 role=dialog 的第三种写法', async () => {
    const { bindings } = await readyPanel()
    await pickTarget(bindings)
    bindings.openDialog(USER_WRITE_DELETE)
    const html = await render(bindings)
    expect((html.match(/role="dialog"/g) || []).length).toBe(1)
  })

  it('动作条那四颗钮只可能走向 openDialog：谁绕过确认步直接绑提交函数，这一条当场红（辛③）', () => {
    const text = source()
    const tags = clickTags(text)
    // 解析器自己的完整性：一枚 @click 都不许漏（漏一枚就等于把刀藏在盲区里）
    expect(tags.length).toBe((text.match(/@click/g) || []).length)
    const map = clickMap(text)
    expect(map['reload-users']).toBe('loadRoster')
    for (const testid of ['open-create', 'open-password', 'open-department', 'open-delete']) {
      expect(map[testid], testid + ' 这一颗必须存在').toBeTruthy()
      expect(map[testid].startsWith('openDialog('), testid + ' 只准走向 openDialog').toBe(true)
    }
    expect(map['open-delete']).toBe('openDialog(USER_WRITE_DELETE)')
    for (const item of tags.filter(entry => entry.testid.startsWith('open-'))) {
      expect(item.click, item.testid + ' 不许直接落到提交/删除那一步').not.toMatch(/confirm|submit|runWrite|Delete/)
    }
  })

  it('每一枚提交点只长在它自己那枚对话框里：绕过确认步的那一格接线，这里也红', () => {
    const text = source()
    const tags = clickTags(text)
    const pairs = [
      ['dlgCreate', 'submitCreate', 'submit-create'],
      ['dlgPassword', 'submitPassword', 'submit-password'],
      ['dlgDepartment', 'submitDepartment', 'submit-department'],
      ['dlgDelete', 'confirmDelete', 'confirm-delete'],
    ]
    for (const [model, fn, testid] of pairs) {
      const hits = tags.filter(item => item.click.includes(fn))
      expect(hits.length, fn + ' 在整块模板里只准被点一次').toBe(1)
      const [from, to] = dialogRange(text, model)
      expect(hits[0].index).toBeGreaterThan(from)
      expect(hits[0].index).toBeLessThan(to)
      expect(clickMap(text)[testid]).toBe(fn)
    }
  })
})

describe('R360戊 · R316 那一族一字未退，动作全部走 ui 原语', () => {
  /** 读那一发答不上来的四种场合：屏壳必须一张写控件都不画。 */
  async function readFaced(outcome) {
    http.get.mockImplementation(async () => {
      // 200 但回包读不出行是一发「答得上来却读不出」的应答，不是抛错：那张脸也得走这条路量
      if (outcome && outcome.status === 200) return outcome
      throw outcome
    })
    for (const verb of ['post', 'put', 'delete']) {
      http[verb].mockImplementation(async () => { throw new Error('读没答上来时这一屏不许发写请求') })
    }
    const bindings = await mountedPanel()
    await bindings.loadRoster()
    await flush()
    return { bindings, html: await render(bindings) }
  }

  it('403 / 401 / 503 / 回包读不出行那四张脸上，动作条一格都不画；ready 与 empty 才画', async () => {
    for (const err of [
      failure(403, 'permission_denied'),
      failure(401, 'authentication_required'),
      failure(503, 'storage_unavailable'),
      { response: { status: 200, data: {} }, status: 200 },
    ]) {
      const { html } = await readFaced(err)
      expect(html).not.toContain('admin-user-actions')
      expect(buttonLabels(html).filter(label => /开通|改密码|调部门|删除账号/.test(label))).toEqual([])
    }
    const ready = await readyPanel()
    expect(ready.html).toContain('admin-user-actions')
    const empty = await readyPanel({ roster: [] })
    expect(empty.html).toContain('admin-user-actions')
    expect(empty.html).toContain(USERS_EMPTY_TITLE)
  })

  it('模板用的八枚原语全部在 script setup 块里 import：少注册一枚就靠渲染产物数类名抓（辛⑤）', async () => {
    const text = source()
    const setupBlock = /<script setup>([\s\S]*?)<\/script>/.exec(text)[1]
    const used = ['UiButton', 'UiDialog', 'UiEmptyState', 'UiErrorState', 'UiField', 'UiLoadingState', 'UiSelect', 'UiTable']
    for (const name of used) {
      expect(setupBlock, `${name} 没在 script setup 块里 import`).toContain(name)
      expect(text, `模板里用了 ${name} 却没在 setup 块里引`).toContain(`<${name}`)
    }
    expect(setupBlock).toMatch(/import \{[^}]*\bUiButton\b[^}]*\} from '\.\/ui'/)
    const { bindings } = await readyPanel()
    await pickTarget(bindings)
    for (const kind of [USER_WRITE_CREATE, USER_WRITE_PASSWORD, USER_WRITE_DEPARTMENT, USER_WRITE_DELETE]) {
      bindings.openDialog(kind)
      const html = await render(bindings)
      expect(html, `${kind} 那枚对话框没画出 ui-button 类`).toContain('class="ui-button')
      expect(html).toContain('class="ui-dialog')
      expect(html).not.toMatch(/<uidialog|<uifield|<uiselect|<uibutton|<uitable|<uierrorstate|<uiemptystate|<uiloadingstate/i)
      bindings.closeDialogs()
    }
  })

  it('屏上不画后端没有的那几枚动作：停用、启用、一键重置、换角色、改名，一帧都不许有', async () => {
    const { bindings } = await readyPanel()
    await pickTarget(bindings)
    for (const kind of [USER_WRITE_CREATE, USER_WRITE_PASSWORD, USER_WRITE_DEPARTMENT, USER_WRITE_DELETE]) {
      bindings.openDialog(kind)
      const labels = buttonLabels(await render(bindings))
      for (const label of labels) {
        expect(label, `屏上画了一枚后端没有的动作：${label}`).not.toMatch(/停用|启用|恢复|一键重置|免密|换角色|改角色|改名/)
      }
      bindings.closeDialogs()
    }
    const all = buttonLabels(await render(bindings))
    expect(all.filter(label => /开通账号|改密码|调部门|删除账号|确认删除|提交/.test(label)).length).toBeGreaterThan(0)
  })

  it('名册那一族一字未退：列仍只取自回包那五枚键，屏壳不数 rows.length，也没有第二份屏名', async () => {
    const { bindings, html } = await readyPanel({ roster: [row(), row({ id: 8, username: 'chen' })] })
    expect(cellTexts(html)).toHaveLength(USER_COLUMNS.length * 2)
    const code = source().replace(/<!--[\s\S]*?-->/g, ' ').replace(/\/\*[\s\S]*?\*\//g, ' ')
    expect(code).not.toMatch(/rows\.value\.length|rows\.length/)
    expect(code).not.toContain('nav-admin')
    expect(visibleText(html)).not.toMatch(/共\s*\d+\s*(人|个|名)|账号总数|人数|占比|活跃度|在岗/)
    expect(html).not.toMatch(/<h3/)
    await pickTarget(bindings)
    bindings.openDialog(USER_WRITE_CREATE)
    expect(cellTexts(await render(bindings))).toHaveLength(USER_COLUMNS.length * 2)
  })
})

describe('R360己 · 视觉预算与庚 · 运行时边界', () => {
  it('零枚裸 <button>（R288 那枚量具现数）', () => {
    expect(countNativeButtons(source())).toBe(0)
  })

  it('一枚新色值都不许多写：屏壳没有样式块，也没有 hex / rgba() / hsl()', () => {
    const text = source()
    expect(text).not.toMatch(/<style/)
    expect(text).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(text).not.toMatch(/rgba?\(|hsla?\(/)
  })

  it('排版只借 theme.css 既有类：屏壳不写内联 style，也不碰 var(--*)', () => {
    const text = source()
    expect(text).not.toMatch(/:style=|style="[^"]*:/)
    expect(text).not.toContain('var(--')
  })

  it('零外部请求：运行一次完整写路径，fetch 一次都没被碰过（只用那枚共享 axios 实例）', async () => {
    const spy = vi.fn(() => { throw new Error('这一屏不许绕过 lib/http.js 自己发请求') })
    const previous = globalThis.fetch
    globalThis.fetch = spy
    try {
      const { bindings } = await readyPanel()
      bindings.openDialog(USER_WRITE_CREATE)
      bindings.form.username = 'newbie'
      bindings.form.password = 'secret6'
      bindings.form.role = 'staff'
      await bindings.submitCreate()
      await flush()
      await render(bindings)
      expect(spy).not.toHaveBeenCalled()
      expect(source()).not.toMatch(/\bfetch\(/)
    } finally {
      globalThis.fetch = previous
    }
  })

  it('零 localStorage / sessionStorage：源码里一格都没有，运行期也没被碰过', async () => {
    const code = source().replace(/<!--[\s\S]*?-->/g, ' ').replace(/\/\*[\s\S]*?\*\//g, ' ')
    expect(code).not.toMatch(/localStorage|sessionStorage/)
    const lib = readFileSync(new URL('../../lib/users.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
      .replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/(^|[\s;:{}])\/\/[^\n]*/g, '$1')
    expect(lib).not.toMatch(/localStorage|sessionStorage/)
  })

  it('码名不上人话位：写失败那几屏里，snake_case 只可能出现在「错误码：」那行小字里', async () => {
    for (const err of [failure(403, 'permission_denied'), failure(503, 'storage_unavailable'), failure(400, 'production_user_store_unavailable')]) {
      const { bindings } = await readyPanel({ reply: err })
      bindings.openDialog(USER_WRITE_CREATE)
      bindings.form.username = 'newbie'
      bindings.form.password = 'secret6'
      bindings.form.role = 'staff'
      await bindings.submitCreate()
      await flush()
      const html = await render(bindings)
      const stripped = html.replace(/<p class="ui-error-state__code"[\s\S]*?<\/p>/g, ' ')
      expect(visibleText(stripped), '裸码名上了人话位').not.toMatch(/[a-z][a-z0-9]*_[a-z0-9_]+/)
    }
  })
})
