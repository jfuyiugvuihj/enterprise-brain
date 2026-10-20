/**
 * R369 · 量具完整性 · r360 那本账换尺之后的尾巴钉
 *
 * 本件不测后端，也不测 lib 层，它只测【那把尺本身还成不成立】。
 *
 * 背景：r360-user-writes.test.js 从 `git show HEAD` 现读后端源码当事实源，里面有形状不同的两把
 * 取体尺。outletBody 按「下一枚顶格 @router.」收口 —— 那是路由文件的形状；storeFunctionBody 按
 * 「下一枚顶格 def 」收口 —— 这才是 app/common/auth.py 该有的形状：那文件里一枚 @router. 都没有，
 * 用前者量一枚函数，量到的是「本函数往后整个文件剩余部分」，于是排除式断言会误伤隔壁函数，白名单
 * 尺会把别人体内的字面量当成本函数的规则读（r360:128-134 已把理由写死）。R360 只换了两处调用点就
 * 收工，剩下的 STORE 读取仍挂着旧尺；R369 把它们全部换成 storeFunctionBody。本件钉住「换完」这个
 * 状态不许回退，并钉住新尺确实收了口 —— 而不是只换了个 helper 名字。
 *
 * 手法照仓里规矩：
 *  ① 对 app/** 一律 git show HEAD，绝不 readFileSync 工作树（r360:9-11 同一条教训：工作树那一份
 *     可能与判据所依据的版本不同，读它就是「永远绿」的假绿）。
 *  ② 读 r360-user-writes.test.js 走工作树 —— 它正是本件的被测物，扫的就是它此刻长什么样。
 *  ③ 期望清单全部从源码当场派生：outlet 变量取自 ENDPOINTS，函数名取自路由体里 auth.X( 的引用。
 *     本件不抄任何一枚别处给的计数，也不写死站点数 —— 上一班的派工词就把站点数写错过。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const REPO_REF = 'HEAD'

function showAtRef(path) {
  let text
  try {
    text = execFileSync('git', ['show', `${REPO_REF}:${path}`], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  } catch (cause) {
    throw new Error(`读不到真源 ${REPO_REF}:${path}（git show 失败：${cause.message}）。量具的账不许降级，这里必须红。`)
  }
  if (!text.trim()) throw new Error(`git show ${REPO_REF}:${path} 返回空内容，无法对账。`)
  return text.replace(/\r\n/g, '\n')
}

const API = showAtRef('app/api/v1/auth.py')
const STORE = showAtRef('app/common/auth.py')

/** 被测物：那本账此刻的源码。读工作树是允许的 —— 它本身就是被扫的前端代码。 */
const LEDGER = readFileSync(new URL('./r360-user-writes.test.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n')

const STORE_TOP_DEFS = [...STORE.matchAll(/^def ([A-Za-z_0-9]+)/gm)].map(item => item[1])

/** 取一枚 helper 自己的源码文本：本件量的是尺子的形状，不是它的返回值。 */
function helperText(source, name) {
  const start = source.indexOf(`function ${name}(`)
  if (start < 0) throw new Error(`r360 里认不出 ${name}：那把尺被删了或改了名，本件的账落空。`)
  const end = source.indexOf('\n}', start)
  if (end < 0) throw new Error(`${name} 的函数体收不到尾，量具的形状钉落空。`)
  return source.slice(start, end)
}

/** (?<!function ) 排掉定义那一行，否则 helper 自己会被算成一次调用。 */
const OUTLET_CALL_ARGS = [...LEDGER.matchAll(/(?<!function )outletBody\(([^)]*)\)/g)].map(item => item[1].trim())
const STORE_CALL_ARGS = [...LEDGER.matchAll(/(?<!function )storeFunctionBody\(([^)]*)\)/g)].map(item => item[1].trim())

/** 一枚参数里能读到的每一枚字符串字面量都算：三元链的每一支都是一次可读。 */
const namesOf = argList => [...new Set(argList.flatMap(arg => [...arg.matchAll(/'([A-Za-z_][A-Za-z_0-9]*)'/g)].map(item => item[1])))]

/** 对照尺：旧形状（按下一枚顶格 @router. 收口）。本件只用它证明旧尺会漏，不用它替代生产尺。 */
function routeShapeBody(src, head) {
  const start = src.indexOf(head)
  if (start < 0) throw new Error(`对照尺找不到 ${head}：路由文件换了形状，本件要重新取证。`)
  const rest = src.slice(start + head.length)
  const next = rest.search(/^@router\./m)
  return next < 0 ? rest : rest.slice(0, next)
}

/**
 * 生产那枚 storeFunctionBody 硬绑模块常量 STORE（r360:135-142），喂不进假源码；本件要在后端零
 * 改动的前提下试刀，只能在这里另写一枚同形状的局部尺 —— 起点 `def <name>(`、收口 /^def /m 逐字对应。
 */
function defShapeBody(src, name) {
  const head = `def ${name}(`
  const start = src.indexOf(head)
  if (start < 0) throw new Error(`局部尺读不到 ${head}：形状变了必须重新取证。`)
  const rest = src.slice(start + head.length)
  const next = rest.search(/^def /m)
  return next < 0 ? rest : rest.slice(0, next)
}

/** 账本自己声明的那四枚写出口：outlet 变量与 decorator 成对取回，不抄字面量。 */
const LEDGER_OUTLETS = [...LEDGER.matchAll(/outlet: (USER_WRITE_[A-Z_]+),\n\s*decorator: '([^']+)'/g)]
  .map(item => ({ outletVar: item[1], decorator: item[2] }))

/** 后端路由体当场把这枚出口的活交给了 app/common/auth.py 里的哪几枚函数。 */
function delegatedStoreNames(decorator) {
  const body = routeShapeBody(API, decorator)
  return [...new Set([...body.matchAll(/auth\.([A-Za-z_][A-Za-z_0-9]*)\(/g)].map(item => item[1]))]
}

/** 账本里那枚三元链：显式分支 + 兜底那一名。 */
const TERNARY_ARG = STORE_CALL_ARGS.find(arg => arg.includes('endpoint.outlet ===')) || ''
const TERNARY_BRANCHES = [...TERNARY_ARG.matchAll(/endpoint\.outlet === (USER_WRITE_[A-Z_]+) \? '([A-Za-z_][A-Za-z_0-9]*)'/g)]
  .map(item => ({ outletVar: item[1], storeName: item[2] }))
const TERNARY_FALLBACK = (/ : '([A-Za-z_][A-Za-z_0-9]*)'$/.exec(TERNARY_ARG) || [])[1]

describe('R369甲 · 按 @router. 收口的那把尺不再越界到 app/common/auth.py', () => {
  it('账本里 outletBody(STORE 一枚不剩，余下每枚 outletBody 的第一参数仍全是 API', () => {
    expect([...LEDGER.matchAll(/outletBody\(\s*STORE/g)].length)
      .toBe(0)
    expect(OUTLET_CALL_ARGS.length).toBeGreaterThan(0)
    const firstArgs = [...new Set(OUTLET_CALL_ARGS.map(arg => arg.split(',')[0].trim()))]
    expect(firstArgs).toEqual(['API'])
  })

  it('两把尺都还在，各自收口锚没被换：outletBody 认 @router.，storeFunctionBody 认顶格 def', () => {
    const outlet = helperText(LEDGER, 'outletBody')
    const store = helperText(LEDGER, 'storeFunctionBody')
    expect(outlet).toContain('/^@router')
    expect(outlet).toContain('/m)')
    expect(outlet).not.toContain('/^def')
    expect(store).toContain('/^def /m')
    expect(store).not.toContain('@router')
    // 新尺必须仍从 `def <name>(` 起量：起点也换了就不是同一枚函数
    expect(store).toContain('def ${name}')
    expect(store).toContain('STORE.indexOf(head)')
  })

  it('三元链把 ENDPOINTS 那几枚 outlet 一一映射到后端真在的顶格函数，一枚不许静默落到兜底', () => {
    expect(LEDGER_OUTLETS.length).toBeGreaterThan(0)
    expect(TERNARY_BRANCHES.length).toBeGreaterThan(0)
    expect(TERNARY_FALLBACK).toBeTruthy()
    // 兜底那一名的归属从路由体反查：谁的出口调了它，它就代表谁
    const fallbackOwners = LEDGER_OUTLETS
      .filter(item => delegatedStoreNames(item.decorator).includes(TERNARY_FALLBACK))
      .map(item => item.outletVar)
    expect(fallbackOwners).toHaveLength(1)
    const covered = [...new Set([...TERNARY_BRANCHES.map(item => item.outletVar), ...fallbackOwners])]
    const declared = [...new Set(LEDGER_OUTLETS.map(item => item.outletVar))].sort()
    expect(covered.sort()).toEqual(declared)
    // 无幽灵：链上每一枚目标都得在后端真有一枚顶格 def
    for (const branch of TERNARY_BRANCHES) {
      expect(STORE_TOP_DEFS, `链上把 ${branch.outletVar} 指向 ${branch.storeName}，可 app/common/auth.py 里没有这枚顶格函数`).toContain(branch.storeName)
    }
    for (const arg of STORE_CALL_ARGS) {
      for (const name of namesOf([arg])) {
        expect(STORE_TOP_DEFS, `账本让 storeFunctionBody 去读 ${name}，后端却没有这枚顶格函数`).toContain(name)
      }
    }
    // 下界从派生清单来，不抄任何一枚外部计数
    expect(STORE_CALL_ARGS.length).toBeGreaterThanOrEqual(LEDGER_OUTLETS.length)
  })
})

describe('R369乙 · 尺子自己证明它收了口', () => {
  const head = 'def create_user('
  const toEnd = STORE.slice(STORE.indexOf(head))
  const ownBody = defShapeBody(STORE, 'create_user')
  const foreignToplevelDefs = STORE_TOP_DEFS.filter(name => name !== 'create_user')

  it('create_user 的体严格短于「从签名一路读到文件末尾」，量的是它自己那一格', () => {
    expect(ownBody.length).toBeLessThan(toEnd.length)
    expect(toEnd.length).toBeGreaterThan(0)
  })

  it('该体内一枚别的顶格 def 声明都没有（逐枚点名）', () => {
    const declaredInside = [...ownBody.matchAll(/^def ([A-Za-z_0-9]+)\(/gm)].map(item => item[1])
    expect(declaredInside).toEqual([])
    for (const name of foreignToplevelDefs) {
      const leaked = declaredInside.includes(name)
      expect(leaked, `换尺之后 create_user 的体里仍写着别枚函数的顶格声明 def ${name}(`).toBe(false)
    }
  })

  it('对照：同一枚函数交给旧尺量，会整枚漏进隔壁函数（换尺不是换个名字）', () => {
    const leaked = [...routeShapeBody(STORE, head).matchAll(/^def ([A-Za-z_0-9]+)\(/gm)].map(item => item[1])
    expect(leaked.length).toBeGreaterThan(0)
    for (const name of leaked) {
      expect(foreignToplevelDefs, `旧尺漏进来一枚不在账上的顶格函数 ${name}`).toContain(name)
    }
    expect(routeShapeBody(STORE, head).length).toBeGreaterThan(ownBody.length)
  })
})

describe('R369丙 · 可注入的形状尺：必红刀与必绿演进', () => {
  const baseLines = [
    'def create_user(username: str, password: str):',
    '    """store 层自己的规则"""',
    '    if len(password) < 6:',
    '        return False, "密码至少 6 位"',
    '    OWN_MARKER = True',
    '',
    'def get_user(username: str):',
    '    NEIGHBOUR_MARKER = True',
    '    return None',
    '',
  ]
  const fakeStore = lines => lines.join('\n')

  it('必红刀：体内再多长出一枚顶格 def，新尺当场截断，旧尺在这一刀上就是漏', () => {
    const src = fakeStore([...baseLines, 'def late_arrival(x: int):', '    EXTRA_MARKER = True', '    return x', ''])
    const tight = defShapeBody(src, 'create_user')
    expect(tight).toContain('OWN_MARKER')
    expect(tight).not.toContain('NEIGHBOUR_MARKER')
    expect(tight).not.toContain('EXTRA_MARKER')
    const loose = routeShapeBody(src, 'def create_user(')
    expect(loose).toContain('NEIGHBOUR_MARKER')
    expect(loose).toContain('EXTRA_MARKER')
    expect(loose.length).toBeGreaterThan(tight.length)
  })

  it('必绿演进：签名多一枚 kwarg、体内多一枚解释行，收口点纹丝不动', () => {
    const evolved = [...baseLines]
    evolved[0] = 'def create_user(username: str, password: str, role: str = "staff"):'
    evolved.splice(2, 0, '    # 演进：加一枚解释行，不改变任何规则')
    evolved.splice(6, 0, '    ANOTHER_OWN_LINE = 1')
    const src = fakeStore(evolved)
    const body = defShapeBody(src, 'create_user')
    expect(body).toContain('role: str = "staff"')
    expect(body).toContain('ANOTHER_OWN_LINE')
    expect(body).toContain('OWN_MARKER')
    expect(body).not.toContain('NEIGHBOUR_MARKER')
    // 截断点仍精确落在下一枚顶格 def 的第一枚字符上
    const headEnd = src.indexOf('def create_user(') + 'def create_user('.length
    expect(src.slice(headEnd + body.length, headEnd + body.length + 13)).toBe('def get_user(')
  })

  it('形状边界：缩进的嵌套 def 不是收口点，内函数仍算本函数自己的一部分', () => {
    const nested = [...baseLines]
    nested.splice(4, 0, '    def helper(inner: str):', '        NESTED_MARKER = inner', '        return NESTED_MARKER')
    const src = fakeStore(nested)
    const body = defShapeBody(src, 'create_user')
    expect(body).toContain('NESTED_MARKER')
    expect(body).toContain('OWN_MARKER')
    expect(body).not.toContain('NEIGHBOUR_MARKER')
  })
})