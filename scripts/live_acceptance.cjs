// playwright 只在 fe-trunk/frontend 装过（主树 node_modules 缺 devDeps），故允许用环境变量指路。
const PW = process.env.PLAYWRIGHT_MODULE || 'C:/Users/fengx/PycharmProjects/fe-trunk/frontend/node_modules/playwright';
const { chromium } = require(PW);
const fs = require('fs');
const OUT = 'C:/Users/fengx/PycharmProjects/企业智脑/docs/screenshots/live-2026-09-15';
const BASE = 'http://localhost/';
const NAV = ['总览', '文档', '数据', '洞察', '图谱', '审批', '对话'];
const FAKE = /undefined|NaN|\[object Object\]|null|N\/A|加载中|加载失败|请求失败|error|异常/i;
const report = { startedAt: new Date().toISOString(), runs: [] };

async function walk(role, user, pass) {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const consoleErrs = []; const netFails = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrs.push(m.text().slice(0, 200)); });
  page.on('requestfailed', (r) => netFails.push(r.url().slice(0, 120) + ' :: ' + (r.failure() || {}).errorText));
  page.on('response', (r) => { if (r.status() >= 400) netFails.push(r.url().slice(0, 120) + ' :: HTTP ' + r.status()); });
  const run = { role, user, steps: [], consoleErrs: null, netFails: null };

  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.screenshot({ path: `${OUT}/${role}-00-login.png`, fullPage: true });
  await page.fill('[data-testid="login-username"]', user);
  await page.fill('[data-testid="login-password"]', pass);
  await page.click('[data-testid="login-submit"]');
  await page.waitForSelector('[data-testid="sidebar"]', { timeout: 20000 }).catch(async () => {
    const e = await page.locator('[data-testid="login-error"]').innerText().catch(() => '');
    run.loginError = e;
  });
  await page.screenshot({ path: `${OUT}/${role}-01-after-login.png`, fullPage: true });
  const loggedIn = await page.locator('[data-testid="sidebar"]').count();

  for (let i = 0; i < NAV.length; i++) {
    const label = NAV[i];
    const t0 = Date.now();
    let clicked = false;
    try { await page.click(`[data-testid="sidebar"] .nav-item:has-text("${label}")`, { timeout: 5000 }); clicked = true; } catch (e) {}
    await page.waitForTimeout(1500);
    const txt = await page.locator('[data-testid="workspace"]').innerText().catch(() => '');
    const hits = [];
    for (const m of txt.matchAll(new RegExp(FAKE, 'gi'))) { hits.push(txt.slice(Math.max(0, m.index - 24), m.index + 36).replace(/\s+/g, ' ')); if (hits.length >= 4) break; }
    run.steps.push({
      label, clicked, ms: Date.now() - t0,
      chars: txt.length,
      controls: await page.locator('[data-testid="workspace"] button').count(),
      headings: (txt.split('\n').filter((s) => s.trim()).slice(0, 3)).join(' | ').slice(0, 90),
      fakeHits: hits.slice(0, 4),
      empty: txt.trim().length < 40,
    });
    await page.screenshot({ path: `${OUT}/${role}-${String(i + 2).padStart(2, '0')}-${label}.png`, fullPage: true });
  }
  run.consoleErrs = consoleErrs; run.netFails = [...new Set(netFails)]; run.loggedIn = !!loggedIn;
  await browser.close();
  return run;
}

(async () => {
  report.runs.push(await walk('staff', 'probe_r9_a', 'Probe!R9a2026'));
  report.runs.push(await walk('admin', 'probe_r9_admin', 'Probe!R9adm2026'));
  fs.writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 2));
  for (const r of report.runs) {
    console.log(`\n##### ${r.role} (${r.user}) logged_in=${r.loggedIn}  控制台报错=${r.consoleErrs.length}  失败请求=${r.netFails.length}`);
    for (const s of r.steps) {
      console.log(`  ${s.label}: clicked=${s.clicked} 文字量=${s.chars} 按钮=${s.controls} 空页=${s.empty} ${s.chars ? '' : ''} 首行="${s.headings}"`);
      if (s.fakeHits.length) console.log(`     假数据痕迹 -> ${JSON.stringify(s.fakeHits)}`);
    }
    if (r.netFails.length) console.log('  失败请求 -> ' + JSON.stringify(r.netFails.slice(0, 8)));
    if (r.consoleErrs.length) console.log('  控制台 -> ' + JSON.stringify(r.consoleErrs.slice(0, 6)));
  }
})();
